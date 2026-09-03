from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.analytics.peak_metrics import build_analysis_calendar
from backend.app.harvest_state.persistence import load_harvest_state_output_by_id
from backend.app.harvest_state.schemas import Task9ACompletedOutput
from backend.app.models.analytics import (
    AnalyticsBuildRun,
    FactorySeasonPeakMetric,
    FactReceiptDaily,
)
from backend.app.models.master_data import Season
from backend.app.residual_model.analytics_authority import bind_analytics_feature_authority
from backend.app.residual_model.canonical import canonical_payload_hash
from backend.app.residual_model.feature_registry import build_feature_registry
from backend.app.residual_model.forecast_cutoff import resolve_forecast_cutoff_at
from backend.app.residual_model.planning_authority import bind_planning_feature_authority
from backend.app.residual_model.projection import calculate_residual_label
from backend.app.residual_model.schemas import (
    AnalyticsActualSnapshot,
    FeatureValue,
    FeatureVisibilityAudit,
    FinalTargetActualsAuthoritySnapshot,
    FinalTargetTrainingManifestRow,
    GovernedGrainIdentityBinding,
    ResidualTrainingManifestRow,
    ResidualTrainingSampleSpec,
)
from backend.app.residual_model.manifest import sort_feature_values
from backend.app.residual_model.canonical import canonical_json_value, sha256_hex
from backend.app.residual_model.structural import aggregate_structural_arrivals
from backend.app.residual_model.task9_mixed_authority import (
    bind_task9_feature_provenance,
    validate_task9_mixed_authority,
)
from backend.app.residual_model.visibility import audit_feature_visibility
from backend.app.residual_model.weather_authority import bind_weather_feature_authority
from backend.app.s2_materialized_dataset.shared.contracts import (
    ACTUAL_LABEL,
    MaterializableRow,
    PartitionName,
)


class ResidualManifestBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class Task3FactoryCoverage:
    build_run_id: int
    factory_id: int
    analysis_start_date: date
    analysis_end_date: date
    calendar_day_count: int
    analysis_months: tuple[int, ...]
    source_max_raw_id: int
    build_available_at: datetime
    coverage_version: str
    coverage_hash: str


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
        key = (factory_id, receipt_date)
        fact_map[key] = fact_map.get(key, Decimal("0")) + weight_kg
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


async def _load_factory_date_spans(
    session: AsyncSession,
    *,
    build_run_id: int,
) -> dict[int, tuple[date, date]]:
    rows = (
        await session.execute(
            select(
                FactReceiptDaily.factory_id,
                FactReceiptDaily.receipt_date,
            )
            .where(FactReceiptDaily.build_run_id == build_run_id)
            .order_by(
                FactReceiptDaily.factory_id.asc(),
                FactReceiptDaily.receipt_date.asc(),
            )
        )
    ).all()
    spans: dict[int, tuple[date, date]] = {}
    for factory_id, receipt_date in rows:
        if factory_id not in spans:
            spans[factory_id] = (receipt_date, receipt_date)
            continue
        start_date, end_date = spans[factory_id]
        spans[factory_id] = (min(start_date, receipt_date), max(end_date, receipt_date))
    return spans


def _snapshot_from_build_run(build_run: AnalyticsBuildRun) -> AnalyticsActualSnapshot:
    source_cutoff = build_run.finished_at or build_run.started_at
    if source_cutoff.tzinfo is None:
        source_cutoff = source_cutoff.replace(tzinfo=UTC)
    return AnalyticsActualSnapshot(
        build_run_id=build_run.id,
        source_max_raw_id=build_run.source_max_raw_id,
        aggregation_version=build_run.aggregation_version,
        config_hash=build_run.config_hash,
        source_cutoff=source_cutoff,
    )


def _analysis_months(build_run: AnalyticsBuildRun) -> tuple[int, ...]:
    raw = build_run.config_snapshot.get("analysis_months")
    if not isinstance(raw, list) or not raw or not all(isinstance(item, int) for item in raw):
        raise ResidualManifestBuildError(
            "AnalyticsBuildRun "
            f"{build_run.id} is missing explicit analysis_months coverage metadata"
        )
    return tuple(raw)


def _build_available_at(build_run: AnalyticsBuildRun) -> datetime:
    available_at = build_run.finished_at or build_run.started_at
    if available_at.tzinfo is None:
        return available_at.replace(tzinfo=UTC)
    return available_at


def _coverage_hash(
    *,
    build_run_id: int,
    factory_id: int,
    analysis_start_date: date,
    analysis_end_date: date,
    calendar_day_count: int,
    analysis_months: tuple[int, ...],
    source_max_raw_id: int,
    build_available_at: datetime,
    coverage_version: str,
) -> str:
    return canonical_payload_hash(
        {
            "build_run_id": build_run_id,
            "factory_id": factory_id,
            "analysis_start_date": analysis_start_date,
            "analysis_end_date": analysis_end_date,
            "calendar_day_count": calendar_day_count,
            "analysis_months": analysis_months,
            "source_max_raw_id": source_max_raw_id,
            "build_available_at": build_available_at,
            "coverage_version": coverage_version,
        }
    )


async def _load_factory_coverages(
    session: AsyncSession,
    *,
    build_run: AnalyticsBuildRun,
    season: Season,
    covered_factory_ids: set[int],
    factory_date_spans: Mapping[int, tuple[date, date]],
) -> dict[int, Task3FactoryCoverage]:
    analysis_months = _analysis_months(build_run)
    build_available_at = _build_available_at(build_run)
    metric_rows = (
        await session.execute(
            select(
                FactorySeasonPeakMetric.factory_id,
                FactorySeasonPeakMetric.analysis_start_date,
                FactorySeasonPeakMetric.analysis_end_date,
                FactorySeasonPeakMetric.calendar_day_count,
            ).where(FactorySeasonPeakMetric.build_run_id == build_run.id)
        )
    ).all()
    if metric_rows:
        return {
            factory_id: Task3FactoryCoverage(
                build_run_id=build_run.id,
                factory_id=factory_id,
                analysis_start_date=analysis_start_date,
                analysis_end_date=analysis_end_date,
                calendar_day_count=calendar_day_count,
                analysis_months=analysis_months,
                source_max_raw_id=build_run.source_max_raw_id,
                build_available_at=build_available_at,
                coverage_version="task3-factory-peak-metric-v1",
                coverage_hash=_coverage_hash(
                    build_run_id=build_run.id,
                    factory_id=factory_id,
                    analysis_start_date=analysis_start_date,
                    analysis_end_date=analysis_end_date,
                    calendar_day_count=calendar_day_count,
                    analysis_months=analysis_months,
                    source_max_raw_id=build_run.source_max_raw_id,
                    build_available_at=build_available_at,
                    coverage_version="task3-factory-peak-metric-v1",
                ),
            )
            for (
                factory_id,
                analysis_start_date,
                analysis_end_date,
                calendar_day_count,
            ) in metric_rows
        }

    coverages: dict[int, Task3FactoryCoverage] = {}
    for factory_id in sorted(covered_factory_ids):
        span = factory_date_spans.get(factory_id)
        if span is None:
            continue
        analysis_start_date = max(season.start_date, span[0])
        analysis_end_date = min(
            season.end_date,
            _snapshot_from_build_run(build_run).source_cutoff.date(),
            span[1],
        )
        calendar_day_count = len(
            build_analysis_calendar(
                start_date=analysis_start_date,
                end_date=analysis_end_date,
                analysis_months=analysis_months,
            )
        )
        coverages[factory_id] = Task3FactoryCoverage(
            build_run_id=build_run.id,
            factory_id=factory_id,
            analysis_start_date=analysis_start_date,
            analysis_end_date=analysis_end_date,
            calendar_day_count=calendar_day_count,
            analysis_months=analysis_months,
            source_max_raw_id=build_run.source_max_raw_id,
            build_available_at=build_available_at,
            coverage_version="task3-fact-span-v1",
            coverage_hash=_coverage_hash(
                build_run_id=build_run.id,
                factory_id=factory_id,
                analysis_start_date=analysis_start_date,
                analysis_end_date=analysis_end_date,
                calendar_day_count=calendar_day_count,
                analysis_months=analysis_months,
                source_max_raw_id=build_run.source_max_raw_id,
                build_available_at=build_available_at,
                coverage_version="task3-fact-span-v1",
            ),
        )
    return coverages


def _receipt_value(
    *,
    build_run: AnalyticsBuildRun,
    season: Season,
    factory_id: int,
    receipt_date: date,
    fact_map: Mapping[tuple[int, date], Decimal],
    factory_coverages: Mapping[int, Task3FactoryCoverage],
) -> tuple[Decimal | None, str | None]:
    analysis_calendar = set(
        build_analysis_calendar(
            start_date=season.start_date,
            end_date=min(season.end_date, _snapshot_from_build_run(build_run).source_cutoff.date()),
            analysis_months=_analysis_months(build_run),
        )
    )
    if receipt_date < season.start_date or receipt_date > season.end_date:
        return None, "date_outside_build_season"
    if receipt_date not in analysis_calendar:
        return None, "date_not_in_analysis_calendar"
    coverage = factory_coverages.get(factory_id)
    if coverage is None:
        return None, "factory_missing_from_build_run"
    if receipt_date > _snapshot_from_build_run(build_run).source_cutoff.date():
        return None, "receipt_date_after_source_cutoff"
    if receipt_date < coverage.analysis_start_date or receipt_date > coverage.analysis_end_date:
        return None, "receipt_date_not_covered_by_build"
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


def _task9_holiday_snapshot(
    output: Task9ACompletedOutput,
) -> tuple[str, str, set[date]]:
    snapshot = output.input_snapshot
    version = snapshot.get("holiday_calendar_version")
    hash_value = snapshot.get("holiday_calendar_hash")
    raw_dates = snapshot.get("holiday_dates", [])
    if not isinstance(version, str) or not version:
        raise ResidualManifestBuildError(
            "Task 9 completed output is missing holiday_calendar_version"
        )
    if not isinstance(hash_value, str) or not hash_value:
        raise ResidualManifestBuildError("Task 9 completed output is missing holiday_calendar_hash")
    if not isinstance(raw_dates, list):
        raise ResidualManifestBuildError("Task 9 completed output holiday_dates is invalid")
    parsed_dates: set[date] = set()
    for raw_date in raw_dates:
        if isinstance(raw_date, date):
            parsed_dates.add(raw_date)
        elif isinstance(raw_date, str):
            parsed_dates.add(date.fromisoformat(raw_date))
        else:
            raise ResidualManifestBuildError("Task 9 completed output holiday_dates is invalid")
    return version, hash_value, parsed_dates


def _missing_feature_value(
    *,
    feature_name: str,
    forecast_cutoff_at: datetime,
) -> FeatureValue:
    return FeatureValue(
        feature_name=feature_name,
        value=None,
        known_at=forecast_cutoff_at,
        source_ref={"missing_feature": feature_name},
        source_version="task10-missing-v1",
        source_available_at=forecast_cutoff_at,
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
        if arrival_local_date < as_of_date:
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
            raise ResidualManifestBuildError(f"HarvestStateRun {sample.task9_run_id} was not found")
        if output.status != "completed":
            raise ResidualManifestBuildError(
                f"HarvestStateRun {sample.task9_run_id} must be completed for Task 10"
            )

        structural_rows = aggregate_structural_arrivals(output)
        as_of_date = _as_of_date_from_task9_output(output)
        cutoff = await resolve_forecast_cutoff_at(
            session,
            task9_run_id=sample.task9_run_id,
            as_of_date=as_of_date,
        )
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
        label_factory_spans = await _load_factory_date_spans(
            session,
            build_run_id=label_build_run.id,
        )
        feature_factory_spans = await _load_factory_date_spans(
            session,
            build_run_id=feature_build_run.id,
        )
        label_factory_coverages = await _load_factory_coverages(
            session,
            build_run=label_build_run,
            season=label_season,
            covered_factory_ids=label_factory_ids,
            factory_date_spans=label_factory_spans,
        )
        feature_factory_coverages = await _load_factory_coverages(
            session,
            build_run=feature_build_run,
            season=feature_season,
            covered_factory_ids=feature_factory_ids,
            factory_date_spans=feature_factory_spans,
        )
        (
            holiday_calendar_version,
            holiday_calendar_hash,
            spring_festival_dates,
        ) = _task9_holiday_snapshot(output)
        bound_supplemental_values = await bind_weather_feature_authority(
            session,
            feature_values=sample.supplemental_feature_values,
            as_of_date=as_of_date,
        )
        bound_supplemental_values = await bind_planning_feature_authority(
            session,
            feature_values=bound_supplemental_values,
            as_of_date=as_of_date,
        )
        supplemental_features = _supplemental_map(bound_supplemental_values)
        mixed_authority = await validate_task9_mixed_authority(
            session,
            task9_run_id=sample.task9_run_id,
            output=output,
            forecast_cutoff_at=cutoff,
        )

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
            observed_receipt, label_missing_reason = _receipt_value(
                build_run=label_build_run,
                season=label_season,
                factory_id=destination_factory_id,
                receipt_date=arrival_local_date,
                fact_map=label_fact_map,
                factory_coverages=label_factory_coverages,
            )
            actual_lag_1, feature_lag_1_reason = _receipt_value(
                build_run=feature_build_run,
                season=feature_season,
                factory_id=destination_factory_id,
                receipt_date=as_of_date - timedelta(days=1),
                fact_map=feature_fact_map,
                factory_coverages=feature_factory_coverages,
            )
            actual_lag_3, feature_lag_3_reason = _receipt_value(
                build_run=feature_build_run,
                season=feature_season,
                factory_id=destination_factory_id,
                receipt_date=as_of_date - timedelta(days=3),
                fact_map=feature_fact_map,
                factory_coverages=feature_factory_coverages,
            )
            actual_lag_7, feature_lag_7_reason = _receipt_value(
                build_run=feature_build_run,
                season=feature_season,
                factory_id=destination_factory_id,
                receipt_date=as_of_date - timedelta(days=7),
                fact_map=feature_fact_map,
                factory_coverages=feature_factory_coverages,
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

            rolling_3d_values: list[Decimal] = []
            for offset in range(1, 4):
                value, reason = _receipt_value(
                    build_run=feature_build_run,
                    season=feature_season,
                    factory_id=destination_factory_id,
                    receipt_date=as_of_date - timedelta(days=offset),
                    fact_map=feature_fact_map,
                    factory_coverages=feature_factory_coverages,
                )
                if value is None:
                    exclusion_reason = exclusion_reason or reason
                    break
                rolling_3d_values.append(value)
            rolling_7d_values: list[Decimal] = []
            for offset in range(1, 8):
                value, reason = _receipt_value(
                    build_run=feature_build_run,
                    season=feature_season,
                    factory_id=destination_factory_id,
                    receipt_date=as_of_date - timedelta(days=offset),
                    fact_map=feature_fact_map,
                    factory_coverages=feature_factory_coverages,
                )
                if value is None:
                    exclusion_reason = exclusion_reason or reason
                    break
                rolling_7d_values.append(value)
            actual_cumulative = Decimal("0")
            for receipt_date in build_analysis_calendar(
                start_date=feature_season.start_date,
                end_date=min(
                    feature_season.end_date,
                    _snapshot_from_build_run(feature_build_run).source_cutoff.date(),
                ),
                analysis_months=_analysis_months(feature_build_run),
            ):
                if receipt_date >= as_of_date:
                    break
                value, reason = _receipt_value(
                    build_run=feature_build_run,
                    season=feature_season,
                    factory_id=destination_factory_id,
                    receipt_date=receipt_date,
                    fact_map=feature_fact_map,
                    factory_coverages=feature_factory_coverages,
                )
                if value is None:
                    exclusion_reason = exclusion_reason or reason
                    continue
                actual_cumulative += value
            structural_cumulative = _structural_cumulative_to_as_of(
                structural_rows=structural_rows,
                destination_factory_id=destination_factory_id,
                as_of_date=as_of_date,
            )

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
                            source_ref={
                                "task9_run_id": sample.task9_run_id,
                                "task9_result_hash": output.result_hash,
                                "holiday_calendar_hash": holiday_calendar_hash,
                            },
                            source_version=holiday_calendar_version,
                            source_available_at=cutoff,
                            observation_date=arrival_local_date,
                        )
                    )
                elif definition.feature_name == "destination_factory_category":
                    resolved_features.append(
                        supplemental_features.get(
                            definition.feature_name,
                            _missing_feature_value(
                                feature_name=definition.feature_name,
                                forecast_cutoff_at=cutoff,
                            ),
                        )
                    )
                else:
                    resolved_features.append(
                        supplemental_features.get(
                            definition.feature_name,
                            _missing_feature_value(
                                feature_name=definition.feature_name,
                                forecast_cutoff_at=cutoff,
                            ),
                        )
                    )

            resolved_features = list(
                bind_analytics_feature_authority(
                    feature_values=resolved_features,
                    build_run=feature_build_run,
                    forecast_cutoff_at=cutoff,
                )
            )
            resolved_features = list(
                bind_task9_feature_provenance(
                    resolved_features,
                    evidence=mixed_authority,
                )
            )
            visibility_audit = audit_feature_visibility(
                features=resolved_features,
                as_of_date=as_of_date,
                forecast_cutoff_at=cutoff,
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


def build_final_target_manifest_from_materializable_rows(
    materializable_rows: Sequence[MaterializableRow],
    *,
    grain_identity: GovernedGrainIdentityBinding,
    partition: PartitionName,
    forecast_cutoff_at: datetime,
    partition_identity: str,
    lineage_hash: str,
    authority: str = "V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION",
) -> list[FinalTargetTrainingManifestRow]:
    """Build lawful final-target manifest rows from governed S2 materializable rows."""

    if partition == PartitionName.TEST:
        raise ResidualManifestBuildError("TEST partition rows are sealed for final-target training")
    from backend.app.residual_model.enums import ResidualSplit

    split = ResidualSplit.TRAIN if partition == PartitionName.TRAIN else ResidualSplit.VALIDATION
    rows: list[FinalTargetTrainingManifestRow] = []
    for materialized in materializable_rows:
        if not grain_identity.matches_materializable_row(materialized):
            raise ResidualManifestBuildError(
                "source_row_grain_mismatch: materialized row does not match governed identity"
            )
        season_id = grain_identity.season_id
        farm_id = grain_identity.farm_id
        subfarm_id = grain_identity.subfarm_id
        variety_id = grain_identity.variety_id
        horizon_days = max(
            (materialized.harvest_business_date - forecast_cutoff_at.date()).days,
            0,
        )
        feature = FeatureValue.model_validate(
            {
                "feature_name": "forecast_horizon_days",
                "value": horizon_days,
                "known_at": forecast_cutoff_at,
                "source_ref": {"materialized_row": materialized.source_row_identity},
                "source_version": "s2-materialized-v1",
                "source_available_at": forecast_cutoff_at,
            }
        )
        feature_values = (feature,)
        feature_vector_hash = canonical_payload_hash(
            [item.model_dump(mode="json") for item in feature_values]
        )
        rows.append(
            FinalTargetTrainingManifestRow(
                season_id=season_id,
                farm_id=farm_id,
                subfarm_id=subfarm_id,
                variety_id=variety_id,
                harvest_business_date=materialized.harvest_business_date,
                forecast_cutoff_at=forecast_cutoff_at,
                forecast_horizon_days=horizon_days,
                actual_harvest_quantity_kg=materialized.actual_harvest_quantity_kg,
                actuals_authority=FinalTargetActualsAuthoritySnapshot(
                    authority=authority,
                    partition_identity=partition_identity,
                    source_row_identity=materialized.source_row_identity,
                    lineage_hash=lineage_hash,
                ),
                feature_values=feature_values,
                feature_vector_hash=feature_vector_hash,
                feature_visibility_audit_hash=canonical_payload_hash([]),
                split=split,
                include=True,
                sample_weight=Decimal("1"),
                source_refs=(
                    authority,
                    ACTUAL_LABEL,
                    materialized.source_row_identity,
                ),
            )
        )
    return rows


def final_target_manifest_row_payload(row: FinalTargetTrainingManifestRow) -> dict[str, Any]:
    return {
        "prediction_target_kind": "FINAL_TARGET_QUANTILE",
        "season_id": row.season_id,
        "farm_id": row.farm_id,
        "subfarm_id": row.subfarm_id,
        "variety_id": row.variety_id,
        "harvest_business_date": row.harvest_business_date,
        "forecast_cutoff_at": row.forecast_cutoff_at,
        "forecast_horizon_days": row.forecast_horizon_days,
        "actual_harvest_quantity_kg": row.actual_harvest_quantity_kg,
        "actuals_authority": row.actuals_authority.model_dump(mode="json"),
        "feature_values": [
            item.model_dump(mode="json") for item in sort_feature_values(row.feature_values)
        ],
        "feature_visibility_audit": (
            row.feature_visibility_audit.model_dump(mode="json")
            if row.feature_visibility_audit is not None
            else None
        ),
        "feature_vector_hash": row.feature_vector_hash,
        "feature_visibility_audit_hash": row.feature_visibility_audit_hash,
        "split": row.split.value,
        "include": row.include,
        "sample_weight": row.sample_weight,
        "exclusion_reason": row.exclusion_reason,
        "source_refs": sorted(row.source_refs),
    }


def final_target_manifest_row_sort_key(row: FinalTargetTrainingManifestRow) -> tuple[object, ...]:
    return (
        row.harvest_business_date,
        row.forecast_cutoff_at,
        row.farm_id,
        row.subfarm_id,
        row.variety_id,
        row.season_id,
        row.feature_vector_hash,
    )


def final_target_manifest_hash(rows: Iterable[FinalTargetTrainingManifestRow]) -> str:
    payload = [
        final_target_manifest_row_payload(row)
        for row in sorted(rows, key=final_target_manifest_row_sort_key)
    ]
    return sha256_hex(canonical_json_value(payload))


def final_target_manifest_row_from_payload(
    payload: dict[str, Any],
) -> FinalTargetTrainingManifestRow:
    from backend.app.residual_model.enums import ResidualSplit

    feature_values = tuple(
        FeatureValue.model_validate(item) for item in payload.get("feature_values", [])
    )
    raw_audit = payload.get("feature_visibility_audit")
    feature_visibility_audit = (
        FeatureVisibilityAudit.model_validate(raw_audit) if raw_audit is not None else None
    )
    return FinalTargetTrainingManifestRow(
        season_id=payload["season_id"],
        farm_id=payload["farm_id"],
        subfarm_id=payload["subfarm_id"],
        variety_id=payload["variety_id"],
        harvest_business_date=payload["harvest_business_date"],
        forecast_cutoff_at=payload["forecast_cutoff_at"],
        forecast_horizon_days=payload["forecast_horizon_days"],
        actual_harvest_quantity_kg=payload["actual_harvest_quantity_kg"],
        actuals_authority=FinalTargetActualsAuthoritySnapshot.model_validate(
            payload["actuals_authority"]
        ),
        feature_values=feature_values,
        feature_visibility_audit=feature_visibility_audit,
        feature_vector_hash=payload["feature_vector_hash"],
        feature_visibility_audit_hash=payload["feature_visibility_audit_hash"],
        split=ResidualSplit(payload["split"]),
        include=payload["include"],
        sample_weight=payload["sample_weight"],
        exclusion_reason=payload.get("exclusion_reason"),
        source_refs=tuple(payload.get("source_refs", [])),
    )
