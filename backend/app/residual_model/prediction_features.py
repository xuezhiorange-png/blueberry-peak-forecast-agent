from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.analytics.peak_metrics import build_analysis_calendar
from backend.app.harvest_state.persistence import load_harvest_state_output_by_id
from backend.app.harvest_state.schemas import Task9ACompletedOutput
from backend.app.models.analytics import AnalyticsBuildRun
from backend.app.residual_model.feature_registry import build_feature_registry
from backend.app.residual_model.schemas import (
    AnalyticsActualSnapshot,
    FeatureValue,
    FeatureVisibilityAudit,
)
from backend.app.residual_model.structural import aggregate_structural_arrivals
from backend.app.residual_model.training_manifest import (
    _analysis_months,
    _as_of_cutoff,
    _as_of_date_from_task9_output,
    _load_completed_build_run,
    _load_fact_map,
    _load_factory_coverages,
    _load_factory_date_spans,
    _load_factory_ids_with_any_fact,
    _load_season,
    _mean,
    _missing_feature_value,
    _receipt_value,
    _snapshot_from_build_run,
    _structural_cumulative_to_as_of,
    _supplemental_map,
    _task9_holiday_snapshot,
)
from backend.app.residual_model.visibility import audit_feature_visibility


class ResidualPredictionFeatureBuildError(RuntimeError):
    pass


def _snapshot_or_none(build_run: AnalyticsBuildRun | None) -> AnalyticsActualSnapshot | None:
    if build_run is None:
        return None
    return _snapshot_from_build_run(build_run)


async def build_prediction_feature_rows(
    session: AsyncSession,
    *,
    task9_run_id: int,
    feature_analytics_build_run_id: int | None,
    supplemental_feature_values: Sequence[FeatureValue],
) -> tuple[
    Task9ACompletedOutput,
    list[dict[str, object]],
    list[tuple[FeatureValue, ...]],
    list[FeatureVisibilityAudit],
    list[str],
    list[str],
    AnalyticsActualSnapshot | None,
]:
    output = await load_harvest_state_output_by_id(session, run_id=task9_run_id)
    if output is None:
        raise ResidualPredictionFeatureBuildError(f"HarvestStateRun {task9_run_id} was not found")
    if output.status != "completed":
        raise ResidualPredictionFeatureBuildError(
            f"HarvestStateRun {task9_run_id} must be completed for residual prediction"
        )

    structural_rows = aggregate_structural_arrivals(output)
    as_of_date = _as_of_date_from_task9_output(output)
    cutoff = _as_of_cutoff(as_of_date)
    registry = build_feature_registry()
    supplemental_features = _supplemental_map(supplemental_feature_values)

    feature_build_run: AnalyticsBuildRun | None = None
    feature_season = None
    feature_fact_map: dict[tuple[int, date], Decimal] = {}
    feature_factory_coverages = {}
    feature_factory_spans: dict[int, tuple[date, date]] = {}
    holiday_calendar_version = "task9-missing-v1"
    holiday_calendar_hash = "0" * 64
    spring_festival_dates: set[date] = set()
    if feature_analytics_build_run_id is not None:
        feature_build_run = await _load_completed_build_run(
            session,
            build_run_id=feature_analytics_build_run_id,
        )
        feature_season = await _load_season(session, season_id=feature_build_run.season_id)
        feature_fact_map = await _load_fact_map(session, build_run_id=feature_build_run.id)
        feature_factory_ids = await _load_factory_ids_with_any_fact(
            session,
            build_run_id=feature_build_run.id,
        )
        feature_factory_spans = await _load_factory_date_spans(
            session,
            build_run_id=feature_build_run.id,
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

    feature_rows: list[tuple[FeatureValue, ...]] = []
    audits: list[FeatureVisibilityAudit] = []
    warnings: list[str] = []
    blockers: list[str] = []

    for structural_row in structural_rows:
        destination_factory_id = cast(int, structural_row["destination_factory_id"])
        arrival_local_date = cast(date, structural_row["arrival_local_date"])
        structural_cumulative = _structural_cumulative_to_as_of(
            structural_rows=structural_rows,
            destination_factory_id=destination_factory_id,
            as_of_date=as_of_date,
        )

        actual_lag_1: Decimal | None = None
        actual_lag_3: Decimal | None = None
        actual_lag_7: Decimal | None = None
        rolling_3d_mean: Decimal | None = None
        rolling_7d_mean: Decimal | None = None
        actual_cumulative: Decimal | None = None
        realized_cumulative_residual: Decimal | None = None
        if feature_build_run is not None and feature_season is not None:
            actual_lag_1, reason_1 = _receipt_value(
                build_run=feature_build_run,
                season=feature_season,
                factory_id=destination_factory_id,
                receipt_date=as_of_date - timedelta(days=1),
                fact_map=feature_fact_map,
                factory_coverages=feature_factory_coverages,
            )
            actual_lag_3, reason_3 = _receipt_value(
                build_run=feature_build_run,
                season=feature_season,
                factory_id=destination_factory_id,
                receipt_date=as_of_date - timedelta(days=3),
                fact_map=feature_fact_map,
                factory_coverages=feature_factory_coverages,
            )
            actual_lag_7, reason_7 = _receipt_value(
                build_run=feature_build_run,
                season=feature_season,
                factory_id=destination_factory_id,
                receipt_date=as_of_date - timedelta(days=7),
                fact_map=feature_fact_map,
                factory_coverages=feature_factory_coverages,
            )
            if reason_1 or reason_3 or reason_7:
                warnings.append(reason_1 or reason_3 or reason_7 or "unknown_feature_gap")
            rolling_3d_values = []
            rolling_3d_missing = False
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
                    warnings.append(reason or "unknown_feature_gap")
                    rolling_3d_missing = True
                    break
                rolling_3d_values.append(value)
            rolling_7d_values = []
            rolling_7d_missing = False
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
                    warnings.append(reason or "unknown_feature_gap")
                    rolling_7d_missing = True
                    break
                rolling_7d_values.append(value)
            rolling_3d_mean = None if rolling_3d_missing else _mean(rolling_3d_values)
            rolling_7d_mean = None if rolling_7d_missing else _mean(rolling_7d_values)
            cumulative_value = Decimal("0")
            cumulative_missing = False
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
                    warnings.append(reason or "unknown_feature_gap")
                    cumulative_missing = True
                    break
                cumulative_value += value
            actual_cumulative = None if cumulative_missing else cumulative_value
            realized_cumulative_residual = (
                None
                if actual_cumulative is None
                else actual_cumulative - structural_cumulative
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
                            "task9_run_id": task9_run_id,
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
                            "task9_run_id": task9_run_id,
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
                        value=structural_row["structural_p90_kg"],
                        known_at=cutoff,
                        source_ref={
                            "task9_run_id": task9_run_id,
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
                            "task9_run_id": task9_run_id,
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
                        source_ref={"analytics_build_run_id": feature_analytics_build_run_id},
                        source_version=(
                            feature_build_run.aggregation_version
                            if feature_build_run is not None
                            else "task10-missing-v1"
                        ),
                        source_available_at=(
                            _snapshot_from_build_run(feature_build_run).source_cutoff
                            if feature_build_run is not None
                            else cutoff
                        ),
                        observation_date=as_of_date - timedelta(days=1),
                    )
                )
            elif definition.feature_name == "actual_receipt_lag_3d_kg":
                resolved_features.append(
                    FeatureValue(
                        feature_name=definition.feature_name,
                        value=actual_lag_3,
                        known_at=cutoff,
                        source_ref={"analytics_build_run_id": feature_analytics_build_run_id},
                        source_version=(
                            feature_build_run.aggregation_version
                            if feature_build_run is not None
                            else "task10-missing-v1"
                        ),
                        source_available_at=(
                            _snapshot_from_build_run(feature_build_run).source_cutoff
                            if feature_build_run is not None
                            else cutoff
                        ),
                        observation_date=as_of_date - timedelta(days=3),
                    )
                )
            elif definition.feature_name == "actual_receipt_lag_7d_kg":
                resolved_features.append(
                    FeatureValue(
                        feature_name=definition.feature_name,
                        value=actual_lag_7,
                        known_at=cutoff,
                        source_ref={"analytics_build_run_id": feature_analytics_build_run_id},
                        source_version=(
                            feature_build_run.aggregation_version
                            if feature_build_run is not None
                            else "task10-missing-v1"
                        ),
                        source_available_at=(
                            _snapshot_from_build_run(feature_build_run).source_cutoff
                            if feature_build_run is not None
                            else cutoff
                        ),
                        observation_date=as_of_date - timedelta(days=7),
                    )
                )
            elif definition.feature_name == "actual_receipt_rolling_3d_mean_kg":
                resolved_features.append(
                    FeatureValue(
                        feature_name=definition.feature_name,
                        value=rolling_3d_mean,
                        known_at=cutoff,
                        source_ref={"analytics_build_run_id": feature_analytics_build_run_id},
                        source_version=(
                            feature_build_run.aggregation_version
                            if feature_build_run is not None
                            else "task10-missing-v1"
                        ),
                        source_available_at=(
                            _snapshot_from_build_run(feature_build_run).source_cutoff
                            if feature_build_run is not None
                            else cutoff
                        ),
                        observation_date=as_of_date - timedelta(days=1),
                    )
                )
            elif definition.feature_name == "actual_receipt_rolling_7d_mean_kg":
                resolved_features.append(
                    FeatureValue(
                        feature_name=definition.feature_name,
                        value=rolling_7d_mean,
                        known_at=cutoff,
                        source_ref={"analytics_build_run_id": feature_analytics_build_run_id},
                        source_version=(
                            feature_build_run.aggregation_version
                            if feature_build_run is not None
                            else "task10-missing-v1"
                        ),
                        source_available_at=(
                            _snapshot_from_build_run(feature_build_run).source_cutoff
                            if feature_build_run is not None
                            else cutoff
                        ),
                        observation_date=as_of_date - timedelta(days=1),
                    )
                )
            elif definition.feature_name == "actual_receipt_cumulative_to_as_of_kg":
                resolved_features.append(
                    FeatureValue(
                        feature_name=definition.feature_name,
                        value=actual_cumulative,
                        known_at=cutoff,
                        source_ref={"analytics_build_run_id": feature_analytics_build_run_id},
                        source_version=(
                            feature_build_run.aggregation_version
                            if feature_build_run is not None
                            else "task10-missing-v1"
                        ),
                        source_available_at=(
                            _snapshot_from_build_run(feature_build_run).source_cutoff
                            if feature_build_run is not None
                            else cutoff
                        ),
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
                            "task9_run_id": task9_run_id,
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
                        value=realized_cumulative_residual,
                        known_at=cutoff,
                        source_ref={
                            "analytics_build_run_id": feature_analytics_build_run_id,
                            "task9_run_id": task9_run_id,
                        },
                        source_version=(
                            "task10-derived-v1"
                            if feature_build_run is not None
                            else "task10-missing-v1"
                        ),
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
                            "task9_run_id": task9_run_id,
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
                            as_of_date=as_of_date,
                        ),
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

        audit = audit_feature_visibility(
            features=resolved_features,
            as_of_date=as_of_date,
            for_training=False,
        )
        if audit.status == "blocked":
            blockers.extend(sorted(issue.code.value for issue in audit.blockers))
        feature_rows.append(tuple(resolved_features))
        audits.append(audit)

    return (
        output,
        structural_rows,
        feature_rows,
        audits,
        sorted(set(warnings)),
        sorted(set(blockers)),
        _snapshot_or_none(feature_build_run),
    )
