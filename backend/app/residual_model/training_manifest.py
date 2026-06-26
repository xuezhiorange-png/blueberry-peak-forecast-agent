from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import cast

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.harvest_state.persistence import load_harvest_state_output_by_id
from backend.app.harvest_state.schemas import Task9ACompletedOutput
from backend.app.models.analytics import AnalyticsBuildRun, FactReceiptDaily
from backend.app.models.master_data import Factory, Holiday, Season
from backend.app.residual_model.canonical import canonical_payload_hash
from backend.app.residual_model.feature_registry import build_feature_registry
from backend.app.residual_model.projection import calculate_residual_label
from backend.app.residual_model.schemas import (
    AnalyticsActualSnapshot,
    FeatureValue,
    ResidualTrainingManifestRow,
    ResidualTrainingSampleSpec,
)
from backend.app.residual_model.structural import aggregate_structural_arrivals
from backend.app.residual_model.visibility import audit_feature_visibility


class ResidualManifestBuildError(RuntimeError):
    pass


def _as_of_cutoff(as_of_date: date) -> datetime:
    return datetime.combine(as_of_date, time.max, tzinfo=UTC)


def _as_of_date_from_task9_output(output: Task9ACompletedOutput) -> date:
    raw = output.input_snapshot.get("as_of_date")
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        return date.fromisoformat(raw)
    raise ResidualManifestBuildError("Task 9 input_snapshot is missing a valid as_of_date")


async def _load_completed_build_run(
    session: AsyncSession,
    *,
    build_run_id: int,
) -> AnalyticsBuildRun:
    build_run = await session.get(AnalyticsBuildRun, build_run_id)
    if build_run is None:
        raise ResidualManifestBuildError(f"AnalyticsBuildRun {build_run_id} was not found")
    if build_run.status != "completed":
        raise ResidualManifestBuildError(
            f"AnalyticsBuildRun {build_run_id} must be completed for Task 10"
        )
    return build_run


async def _load_season(
    session: AsyncSession,
    *,
    season_id: int,
) -> Season:
    season = await session.get(Season, season_id)
    if season is None:
        raise ResidualManifestBuildError(f"Season {season_id} was not found")
    return season


async def _load_fact_map(
    session: AsyncSession,
    *,
    build_run_id: int,
) -> dict[tuple[int, date], Decimal]:
    statement: Select[tuple[int, date, Decimal]] = select(
        FactReceiptDaily.factory_id,
        FactReceiptDaily.receipt_date,
        FactReceiptDaily.weight_kg,
    ).where(FactReceiptDaily.build_run_id == build_run_id)
    rows = (await session.execute(statement)).all()
    fact_map: dict[tuple[int, date], Decimal] = {}
    for factory_id, receipt_date, weight_kg in rows:
        fact_map[(factory_id, receipt_date)] = weight_kg
    return fact_map


async def _load_factory_ids_with_any_fact(
    session: AsyncSession,
    *,
    build_run_id: int,
) -> set[int]:
    rows = (
        await session.execute(
            select(FactReceiptDaily.factory_id)
            .where(FactReceiptDaily.build_run_id == build_run_id)
            .distinct()
        )
    ).all()
    return {factory_id for (factory_id,) in rows}


async def _load_factory(
    session: AsyncSession,
    *,
    factory_id: int,
) -> Factory:
    factory = await session.get(Factory, factory_id)
    if factory is None:
        raise ResidualManifestBuildError(f"Factory {factory_id} was not found")
    return factory


async def _load_spring_festival_dates(
    session: AsyncSession,
    *,
    season_id: int,
) -> set[date]:
    rows = (
        await session.execute(
            select(Holiday.start_date, Holiday.end_date)
            .where(
                Holiday.season_id == season_id,
                Holiday.active.is_(True),
                Holiday.code == "spring_festival",
            )
            .order_by(Holiday.start_date.asc(), Holiday.id.asc())
        )
    ).all()
    values: set[date] = set()
    for start_date, end_date in rows:
        cursor = start_date
        while cursor <= end_date:
            values.add(cursor)
            cursor += timedelta(days=1)
    return values


def _snapshot_from_build_run(build_run: AnalyticsBuildRun) -> AnalyticsActualSnapshot:
    return AnalyticsActualSnapshot(
        build_run_id=build_run.id,
        source_max_raw_id=build_run.source_max_raw_id,
        aggregation_version=build_run.aggregation_version,
        config_hash=build_run.config_hash,
        source_cutoff=build_run.finished_at or build_run.started_at,
    )


def _receipt_value(
    *,
    season: Season,
    factory_id: int,
    receipt_date: date,
    fact_map: Mapping[tuple[int, date], Decimal],
    covered_factory_ids: set[int],
) -> tuple[Decimal | None, str | None]:
    if receipt_date < season.start_date or receipt_date > season.end_date:
        return None, "date_outside_build_season"
    if factory_id not in covered_factory_ids:
        return None, "factory_missing_from_build_run"
    value = fact_map.get((factory_id, receipt_date))
    if value is not None:
        return value, None
    return Decimal("0"), None


def _mean(values: Sequence[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _supplemental_map(
    values: Sequence[FeatureValue],
) -> dict[str, FeatureValue]:
    seen: dict[str, FeatureValue] = {}
    for item in values:
        if item.feature_name in seen:
            raise ResidualManifestBuildError(
                f"Duplicate supplemental feature {item.feature_name!r} in manifest sample"
            )
        seen[item.feature_name] = item
    return seen


def _missing_feature_value(
    *,
    feature_name: str,
    as_of_date: date,
) -> FeatureValue:
    cutoff = _as_of_cutoff(as_of_date)
    return FeatureValue(
        feature_name=feature_name,
        value=None,
        known_at=cutoff,
        source_ref={"missing_feature": feature_name},
        source_version="task10-missing-v1",
        source_available_at=cutoff,
    )


def _feature_vector_hash(values: Sequence[FeatureValue]) -> str:
    return canonical_payload_hash([item.model_dump(mode="json") for item in values])


def _structural_cumulative_to_as_of(
    *,
    structural_rows: Sequence[dict[str, object]],
    destination_factory_id: int,
    as_of_date: date,
) -> Decimal:
    total = Decimal("0")
    for row in structural_rows:
        if row["destination_factory_id"] != destination_factory_id:
            continue
        arrival_local_date = cast(date, row["arrival_local_date"])
        if arrival_local_date <= as_of_date:
            total += cast(Decimal, row["structural_p50_kg"])
    return total


async def build_residual_training_manifest(
    session: AsyncSession,
    *,
    samples: Sequence[ResidualTrainingSampleSpec],
) -> list[ResidualTrainingManifestRow]:
    if not samples:
        return []

    manifest_rows: list[ResidualTrainingManifestRow] = []
    registry = build_feature_registry()

    for sample in sorted(
        samples,
        key=lambda item: (
            item.task9_run_id,
            item.label_analytics_build_run_id,
            item.feature_analytics_build_run_id,
            item.split.value,
        ),
    ):
        output = await load_harvest_state_output_by_id(session, run_id=sample.task9_run_id)
        if output is None:
            raise ResidualManifestBuildError(
                f"HarvestStateRun {sample.task9_run_id} was not found"
            )
        if output.status != "completed":
            raise ResidualManifestBuildError(
                f"HarvestStateRun {sample.task9_run_id} must be completed for Task 10"
            )

        structural_rows = aggregate_structural_arrivals(output)
        as_of_date = _as_of_date_from_task9_output(output)
        label_build_run = await _load_completed_build_run(
            session,
            build_run_id=sample.label_analytics_build_run_id,
        )
        feature_build_run = await _load_completed_build_run(
            session,
            build_run_id=sample.feature_analytics_build_run_id,
        )
        if label_build_run.season_id != feature_build_run.season_id:
            raise ResidualManifestBuildError(
                "Label and feature AnalyticsBuildRun records must belong to the same season"
            )
        label_season = await _load_season(session, season_id=label_build_run.season_id)
        feature_season = await _load_season(session, season_id=feature_build_run.season_id)

        label_fact_map = await _load_fact_map(session, build_run_id=label_build_run.id)
        feature_fact_map = await _load_fact_map(session, build_run_id=feature_build_run.id)
        label_factory_ids = await _load_factory_ids_with_any_fact(
            session,
            build_run_id=label_build_run.id,
        )
        feature_factory_ids = await _load_factory_ids_with_any_fact(
            session,
            build_run_id=feature_build_run.id,
        )
        spring_festival_dates = await _load_spring_festival_dates(
            session,
            season_id=label_build_run.season_id,
        )
        supplemental_features = _supplemental_map(sample.supplemental_feature_values)

        grouped_structural: dict[tuple[int, date], dict[str, object]] = {}
        for row in structural_rows:
            key = (
                cast(int, row["destination_factory_id"]),
                cast(date, row["arrival_local_date"]),
            )
            grouped_structural[key] = row

        for (destination_factory_id, arrival_local_date), structural_row in sorted(
            grouped_structural.items(),
            key=lambda item: (item[0][0], item[0][1]),
        ):
            factory = await _load_factory(session, factory_id=destination_factory_id)
            observed_receipt, label_missing_reason = _receipt_value(
                season=label_season,
                factory_id=destination_factory_id,
                receipt_date=arrival_local_date,
                fact_map=label_fact_map,
                covered_factory_ids=label_factory_ids,
            )
            actual_lag_1, feature_lag_1_reason = _receipt_value(
                season=feature_season,
                factory_id=destination_factory_id,
                receipt_date=as_of_date - timedelta(days=1),
                fact_map=feature_fact_map,
                covered_factory_ids=feature_factory_ids,
            )
            actual_lag_3, feature_lag_3_reason = _receipt_value(
                season=feature_season,
                factory_id=destination_factory_id,
                receipt_date=as_of_date - timedelta(days=3),
                fact_map=feature_fact_map,
                covered_factory_ids=feature_factory_ids,
            )
            actual_lag_7, feature_lag_7_reason = _receipt_value(
                season=feature_season,
                factory_id=destination_factory_id,
                receipt_date=as_of_date - timedelta(days=7),
                fact_map=feature_fact_map,
                covered_factory_ids=feature_factory_ids,
            )
            if observed_receipt is None:
                exclusion_reason = label_missing_reason
                observed_receipt_value = Decimal("0")
            else:
                exclusion_reason = sample.exclusion_reason
                observed_receipt_value = observed_receipt

            if actual_lag_1 is None or actual_lag_3 is None or actual_lag_7 is None:
                exclusion_reason = exclusion_reason or (
                    feature_lag_1_reason or feature_lag_3_reason or feature_lag_7_reason
                )

            rolling_3d_values = [
                _receipt_value(
                    season=feature_season,
                    factory_id=destination_factory_id,
                    receipt_date=as_of_date - timedelta(days=offset),
                    fact_map=feature_fact_map,
                    covered_factory_ids=feature_factory_ids,
                )[0]
                or Decimal("0")
                for offset in range(0, 3)
            ]
            rolling_7d_values = [
                _receipt_value(
                    season=feature_season,
                    factory_id=destination_factory_id,
                    receipt_date=as_of_date - timedelta(days=offset),
                    fact_map=feature_fact_map,
                    covered_factory_ids=feature_factory_ids,
                )[0]
                or Decimal("0")
                for offset in range(0, 7)
            ]
            actual_cumulative = sum(
                weight
                for (factory_id, receipt_date), weight in feature_fact_map.items()
                if factory_id == destination_factory_id and receipt_date <= as_of_date
            )
            structural_cumulative = _structural_cumulative_to_as_of(
                structural_rows=structural_rows,
                destination_factory_id=destination_factory_id,
                as_of_date=as_of_date,
            )

            cutoff = _as_of_cutoff(as_of_date)
            resolved_features: list[FeatureValue] = []
            for definition in registry:
                if definition.feature_name == "structural_arrival_p50_kg":
                    resolved_features.append(
                        FeatureValue(
                            feature_name=definition.feature_name,
                            value=structural_row["structural_p50_kg"],
                            known_at=cutoff,
                            source_ref={
                                "task9_run_id": sample.task9_run_id,
                                "task9_result_hash": output.result_hash,
                            },
                            source_version="task9-completed-v1",
                            source_available_at=cutoff,
                        )
                    )
                elif definition.feature_name == "structural_arrival_p80_kg":
                    resolved_features.append(
                        FeatureValue(
                            feature_name=definition.feature_name,
                            value=structural_row["structural_p80_kg"],
                            known_at=cutoff,
                            source_ref={
                                "task9_run_id": sample.task9_run_id,
                                "task9_result_hash": output.result_hash,
                            },
                            source_version="task9-completed-v1",
                            source_available_at=cutoff,
                        )
                    )
                elif definition.feature_name == "structural_arrival_p90_kg":
                    resolved_features.append(
                        FeatureValue(
                            feature_name=definition.feature_name,
                            value=cast(Decimal, structural_row["structural_p90_kg"]),
                            known_at=cutoff,
                            source_ref={
                                "task9_run_id": sample.task9_run_id,
                                "task9_result_hash": output.result_hash,
                            },
                            source_version="task9-completed-v1",
                            source_available_at=cutoff,
                        )
                    )
                elif definition.feature_name == "forecast_horizon_days":
                    resolved_features.append(
                        FeatureValue(
                            feature_name=definition.feature_name,
                            value=cast(int, structural_row["forecast_horizon_days"]),
                            known_at=cutoff,
                            source_ref={
                                "task9_run_id": sample.task9_run_id,
                                "task9_result_hash": output.result_hash,
                            },
                            source_version="task9-completed-v1",
                            source_available_at=cutoff,
                        )
                    )
                elif definition.feature_name == "actual_receipt_lag_1d_kg":
                    resolved_features.append(
                        FeatureValue(
                            feature_name=definition.feature_name,
                            value=actual_lag_1,
                            known_at=cutoff,
                            source_ref={"analytics_build_run_id": feature_build_run.id},
                            source_version=feature_build_run.aggregation_version,
                            source_available_at=_snapshot_from_build_run(
                                feature_build_run
                            ).source_cutoff,
                            observation_date=as_of_date - timedelta(days=1),
                        )
                    )
                elif definition.feature_name == "actual_receipt_lag_3d_kg":
                    resolved_features.append(
                        FeatureValue(
                            feature_name=definition.feature_name,
                            value=actual_lag_3,
                            known_at=cutoff,
                            source_ref={"analytics_build_run_id": feature_build_run.id},
                            source_version=feature_build_run.aggregation_version,
                            source_available_at=_snapshot_from_build_run(
                                feature_build_run
                            ).source_cutoff,
                            observation_date=as_of_date - timedelta(days=3),
                        )
                    )
                elif definition.feature_name == "actual_receipt_lag_7d_kg":
                    resolved_features.append(
                        FeatureValue(
                            feature_name=definition.feature_name,
                            value=actual_lag_7,
                            known_at=cutoff,
                            source_ref={"analytics_build_run_id": feature_build_run.id},
                            source_version=feature_build_run.aggregation_version,
                            source_available_at=_snapshot_from_build_run(
                                feature_build_run
                            ).source_cutoff,
                            observation_date=as_of_date - timedelta(days=7),
                        )
                    )
                elif definition.feature_name == "actual_receipt_rolling_3d_mean_kg":
                    resolved_features.append(
                        FeatureValue(
                            feature_name=definition.feature_name,
                            value=_mean(rolling_3d_values),
                            known_at=cutoff,
                            source_ref={"analytics_build_run_id": feature_build_run.id},
                            source_version=feature_build_run.aggregation_version,
                            source_available_at=_snapshot_from_build_run(
                                feature_build_run
                            ).source_cutoff,
                            observation_date=as_of_date - timedelta(days=1),
                        )
                    )
                elif definition.feature_name == "actual_receipt_rolling_7d_mean_kg":
                    resolved_features.append(
                        FeatureValue(
                            feature_name=definition.feature_name,
                            value=_mean(rolling_7d_values),
                            known_at=cutoff,
                            source_ref={"analytics_build_run_id": feature_build_run.id},
                            source_version=feature_build_run.aggregation_version,
                            source_available_at=_snapshot_from_build_run(
                                feature_build_run
                            ).source_cutoff,
                            observation_date=as_of_date - timedelta(days=1),
                        )
                    )
                elif definition.feature_name == "actual_receipt_cumulative_to_as_of_kg":
                    resolved_features.append(
                        FeatureValue(
                            feature_name=definition.feature_name,
                            value=actual_cumulative,
                            known_at=cutoff,
                            source_ref={"analytics_build_run_id": feature_build_run.id},
                            source_version=feature_build_run.aggregation_version,
                            source_available_at=_snapshot_from_build_run(
                                feature_build_run
                            ).source_cutoff,
                            observation_date=as_of_date - timedelta(days=1),
                        )
                    )
                elif definition.feature_name == "structural_cumulative_to_as_of_kg":
                    resolved_features.append(
                        FeatureValue(
                            feature_name=definition.feature_name,
                            value=structural_cumulative,
                            known_at=cutoff,
                            source_ref={
                                "task9_run_id": sample.task9_run_id,
                                "task9_result_hash": output.result_hash,
                            },
                            source_version="task9-completed-v1",
                            source_available_at=cutoff,
                            observation_date=as_of_date,
                        )
                    )
                elif definition.feature_name == "realized_cumulative_residual_to_as_of_kg":
                    resolved_features.append(
                        FeatureValue(
                            feature_name=definition.feature_name,
                            value=actual_cumulative - structural_cumulative,
                            known_at=cutoff,
                            source_ref={
                                "analytics_build_run_id": feature_build_run.id,
                                "task9_run_id": sample.task9_run_id,
                            },
                            source_version="task10-derived-v1",
                            source_available_at=cutoff,
                            observation_date=as_of_date - timedelta(days=1),
                        )
                    )
                elif definition.feature_name == "spring_festival_window_flag":
                    resolved_features.append(
                        FeatureValue(
                            feature_name=definition.feature_name,
                            value=arrival_local_date in spring_festival_dates,
                            known_at=cutoff,
                            source_ref={"season_id": label_build_run.season_id},
                            source_version="holiday-calendar-v1",
                            source_available_at=cutoff,
                            observation_date=arrival_local_date,
                        )
                    )
                elif definition.feature_name == "destination_factory_category":
                    resolved_features.append(
                        FeatureValue(
                            feature_name=definition.feature_name,
                            value=factory.region_name or factory.code or str(factory.id),
                            known_at=cutoff,
                            source_ref={"factory_id": factory.id},
                            source_version="master-data-v1",
                            source_available_at=cutoff,
                        )
                    )
                else:
                    resolved_features.append(
                        supplemental_features.get(
                            definition.feature_name,
                            _missing_feature_value(
                                feature_name=definition.feature_name,
                                as_of_date=as_of_date,
                            ),
                        )
                    )

            visibility_audit = audit_feature_visibility(
                features=resolved_features,
                as_of_date=as_of_date,
                for_training=True,
            )
            feature_hash = _feature_vector_hash(resolved_features)
            manifest_rows.append(
                ResidualTrainingManifestRow(
                    season_id=label_build_run.season_id,
                    destination_factory_id=destination_factory_id,
                    task9_run_id=sample.task9_run_id,
                    task9_result_hash=output.result_hash,
                    as_of_date=as_of_date,
                    target_arrival_local_date=arrival_local_date,
                    forecast_horizon_days=cast(int, structural_row["forecast_horizon_days"]),
                    label_actual_snapshot=_snapshot_from_build_run(label_build_run),
                    feature_actual_snapshot=_snapshot_from_build_run(feature_build_run),
                    observed_effective_receipt_kg=observed_receipt_value,
                    structural_p50_kg=cast(Decimal, structural_row["structural_p50_kg"]),
                    structural_p80_kg=cast(Decimal, structural_row["structural_p80_kg"]),
                    structural_p90_kg=cast(Decimal, structural_row["structural_p90_kg"]),
                    residual_label_kg=calculate_residual_label(
                        observed_effective_receipt_kg=observed_receipt_value,
                        structural_arrival_p50_kg=cast(
                            Decimal,
                            structural_row["structural_p50_kg"],
                        ),
                    ),
                    feature_values=tuple(resolved_features),
                    feature_visibility_audit=visibility_audit,
                    feature_vector_hash=feature_hash,
                    feature_visibility_audit_hash=visibility_audit.audit_hash,
                    split=sample.split,
                    include=sample.include and exclusion_reason is None,
                    sample_weight=sample.sample_weight,
                    exclusion_reason=exclusion_reason,
                    source_refs=tuple(
                        sorted(
                            {
                                f"task9_run:{sample.task9_run_id}",
                                f"task9_result_hash:{output.result_hash}",
                                f"label_build_run:{label_build_run.id}",
                                f"feature_build_run:{feature_build_run.id}",
                            }
                        )
                    ),
                )
            )

    return sorted(
        manifest_rows,
        key=lambda row: (
            row.season_id,
            row.destination_factory_id,
            row.as_of_date,
            row.target_arrival_local_date,
            row.task9_run_id,
            row.label_actual_snapshot.build_run_id,
            row.feature_actual_snapshot.build_run_id,
            row.split.value,
        ),
    )
