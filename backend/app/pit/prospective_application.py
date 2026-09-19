"""Application boundary for V0.6-S4 prospective evidence assessment."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.pit.canonical import hash_payload
from backend.app.pit.evaluation import ActualDailyRecord
from backend.app.pit.evaluation_models import ForecastEvaluation
from backend.app.pit.models import AreaRevision, ForecastRunSnapshot, WeatherForecastSnapshot
from backend.app.pit.prospective_persistence import ProspectiveValidationRepository
from backend.app.pit.prospective_validation import (
    MODEL_A_IDENTITY,
    MODEL_A_TEMPORAL_MODEL,
    MODEL_A_TOTAL_MODEL,
    EvaluationEvidence,
    S4AssessmentComputation,
    WeatherDiagnosticRow,
    build_assessment,
    build_prospective_eligibility,
)


def _evaluation_evidence(model: ForecastEvaluation) -> EvaluationEvidence:
    return EvaluationEvidence(
        evaluation_id=model.evaluation_id,
        forecast_run_id=model.forecast_run_id,
        base_id=model.base_id,
        actual_coverage_status=model.actual_coverage_status,
        season_total_metrics=model.season_total_metrics,
        daily_metrics=model.daily_metrics,
        single_day_peak_metrics=model.single_day_peak_metrics,
        rolling_7day_peak_metrics=model.rolling_7day_peak_metrics,
        weather_metrics=model.weather_metrics,
    )


def _frozen_model_hash(
    snapshots: Sequence[ForecastRunSnapshot],
    eligible_run_ids: set[str],
) -> str | None:
    bindings: list[dict[str, object]] = []
    for snapshot in snapshots:
        if snapshot.forecast_run_id not in eligible_run_ids:
            continue
        if snapshot.total_model_id != MODEL_A_TOTAL_MODEL:
            raise ValueError("MODEL_A_TOTAL_MODEL_MISMATCH")
        if snapshot.temporal_model_id != MODEL_A_TEMPORAL_MODEL:
            raise ValueError("MODEL_A_TEMPORAL_MODEL_MISMATCH")
        bindings.append(
            {
                "forecast_run_id": snapshot.forecast_run_id,
                "total_model_id": snapshot.total_model_id,
                "temporal_model_id": snapshot.temporal_model_id,
                "model_artifact_hashes": snapshot.model_artifact_hashes,
            }
        )
    if not bindings:
        return None
    bindings.sort(key=lambda item: str(item.get("forecast_run_id")))
    return hash_payload(
        {
            "model_a_identity": MODEL_A_IDENTITY,
            "bindings": bindings,
        }
    )


async def run_prospective_validation_assessment(
    session: AsyncSession,
    *,
    evaluation_created_at: datetime,
    actual_records_by_run: Mapping[str, Sequence[ActualDailyRecord]] | None = None,
    stable_history_base_ids: Sequence[str] = (),
) -> S4AssessmentComputation:
    """Build and persist S4 evidence without committing the caller's transaction.

    The actual-record mapping is an explicit input owned by the existing
    actual-harvest authority adapter.  Omitting it is fail-closed and produces
    an auditable insufficient-evidence assessment; it never reads hindsight
    data from an alternate source.
    """

    actual_records_by_run = actual_records_by_run or {}
    snapshots = list(
        await session.scalars(
            select(ForecastRunSnapshot).order_by(ForecastRunSnapshot.forecast_run_id)
        )
    )
    evaluations = list(
        await session.scalars(select(ForecastEvaluation).order_by(ForecastEvaluation.evaluation_id))
    )
    evaluation_evidence = tuple(_evaluation_evidence(item) for item in evaluations)
    weather_models = list(await session.scalars(select(WeatherForecastSnapshot)))
    weather_by_id = {item.weather_snapshot_id: item for item in weather_models}
    area_ids = {snapshot.area_revision_id for snapshot in snapshots}
    area_models = list(
        await session.scalars(
            select(AreaRevision).where(AreaRevision.area_revision_id.in_(area_ids))
        )
    )
    area_by_id = {item.area_revision_id: item for item in area_models}
    registry = []
    for snapshot in snapshots:
        weather = tuple(
            weather_by_id[item]
            for item in sorted(snapshot.weather_snapshot_ids)
            if item in weather_by_id
        )
        registry.append(
            build_prospective_eligibility(
                snapshot,
                actual_records_by_run.get(snapshot.forecast_run_id, ()),
                evaluation_created_at=evaluation_created_at,
                actual_coverage_status=next(
                    (
                        item.actual_coverage_status
                        for item in evaluation_evidence
                        if item.forecast_run_id == snapshot.forecast_run_id
                    ),
                    None,
                ),
                area_revision=area_by_id.get(snapshot.area_revision_id),
                weather_snapshots=weather,
            )
        )

    evaluation_run_ids = {item.forecast_run_id for item in evaluation_evidence}
    registry = [
        replace(
            item,
            prospective_eligible=False,
            ineligibility_reasons=tuple(
                sorted((*item.ineligibility_reasons, "S3_EVALUATION_NOT_FOUND"))
            ),
        )
        if item.prospective_eligible and item.forecast_run_id not in evaluation_run_ids
        else item
        for item in registry
    ]
    eligible_run_ids = {item.forecast_run_id for item in registry if item.prospective_eligible}
    diagnostic_rows: list[WeatherDiagnosticRow] = []
    for evaluation in evaluation_evidence:
        if evaluation.forecast_run_id not in eligible_run_ids:
            continue
        peak = evaluation.single_day_peak_metrics
        if peak.get("status") != "COMPUTABLE":
            continue
        residual = peak.get("peak_date_error_days")
        if residual is None:
            continue
        snapshot = next(
            item for item in snapshots if item.forecast_run_id == evaluation.forecast_run_id
        )
        for weather_id in sorted(snapshot.weather_snapshot_ids):
            weather_snapshot = weather_by_id.get(weather_id)
            if weather_snapshot is None:
                continue
            diagnostic_rows.append(
                WeatherDiagnosticRow(
                    forecast_run_id=evaluation.forecast_run_id,
                    base_id=evaluation.base_id,
                    horizon_hours=weather_snapshot.forecast_horizon_hours,
                    temperature_signal=weather_snapshot.temperature_mean,
                    precipitation_signal=weather_snapshot.precipitation,
                    timing_residual_days=_decimal(residual),
                )
            )
    computation = build_assessment(
        eligibility=registry,
        evaluations=evaluation_evidence,
        weather_diagnostic_rows=diagnostic_rows,
        created_at=evaluation_created_at,
        stable_history_base_ids=stable_history_base_ids,
        model_a_hash=_frozen_model_hash(
            snapshots,
            {item.forecast_run_id for item in registry if item.prospective_eligible},
        ),
    )
    await ProspectiveValidationRepository(session).save(computation)
    return computation


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


__all__ = ["run_prospective_validation_assessment"]
