"""Load persisted S2 forecast binding authority for live pairing materialization."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.core_forecast import (
    CoreForecastCodeAuthorityModel,
    CoreForecastDailyRowModel,
    CoreForecastRunModel,
)
from backend.app.models.harvest_state import HarvestStateDailyMemberRowModel, HarvestStateRun
from backend.app.models.residual_model import (
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.rolling_backtest.orchestration import _task9_member_identity_hash
from backend.app.rolling_backtest.schemas import S2ForecastAuthorityBundle

ForecastQuantile = Literal["P50", "P80", "P90"]

_SYNTHETIC_SINGLE_CHAR_HEX = frozenset(ch * 64 for ch in "0123456789abcdef")


def _as_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _visible_at_or_before(value: datetime | None, cutoff_at: datetime) -> bool:
    if value is None:
        return False
    return _as_utc_aware(value) <= _as_utc_aware(cutoff_at)


def is_synthetic_forecast_authority(bundle: S2ForecastAuthorityBundle) -> bool:
    """Reject engineering placeholder hashes on live production paths."""
    hashes = (
        bundle.forecast_run_identity_hash,
        bundle.daily_row_identity_hash,
        bundle.task9_authority_identity_hash,
        bundle.task9_member_identity_hash,
        bundle.task10_authority_identity_hash,
        bundle.task10_model_identity_hash,
        bundle.task10_replay_identity_hash,
        bundle.task10_prediction_row_identity_hash,
        bundle.forecast_code_identity,
        bundle.build_artifact_hash,
        bundle.config_bundle_hash,
    )
    return any(item in _SYNTHETIC_SINGLE_CHAR_HEX for item in hashes)


def _resolve_core_forecast_run(
    session: Session,
    *,
    forecast_cutoff_at: datetime,
    task8_forecast_run_id: int,
) -> CoreForecastRunModel | None:
    core_runs = list(
        session.scalars(
            select(CoreForecastRunModel).where(
                CoreForecastRunModel.status == "completed",
                CoreForecastRunModel.forecast_effective_cutoff_at == forecast_cutoff_at,
                CoreForecastRunModel.completed_at <= forecast_cutoff_at,
                CoreForecastRunModel.task8_forecast_run_id == task8_forecast_run_id,
            )
        ).all()
    )
    if len(core_runs) != 1:
        return None
    core_run = core_runs[0]
    if (
        core_run.code_authority_id is None
        or core_run.code_authority_hash is None
        or core_run.forecast_effective_cutoff_at is None
    ):
        return None
    return core_run


def _resolve_exact_core_daily_row(
    session: Session,
    *,
    core_run: CoreForecastRunModel,
    target_date: date,
    forecast_quantile: ForecastQuantile,
    farm_id: int,
    subfarm_id: int,
    variety_id: int,
) -> CoreForecastDailyRowModel | None:
    matching_rows = list(
        session.scalars(
            select(CoreForecastDailyRowModel).where(
                CoreForecastDailyRowModel.core_forecast_run_id == core_run.id,
                CoreForecastDailyRowModel.date == target_date,
                CoreForecastDailyRowModel.forecast_quantile == forecast_quantile,
                CoreForecastDailyRowModel.farm_id == farm_id,
                CoreForecastDailyRowModel.subfarm_id == subfarm_id,
                CoreForecastDailyRowModel.variety_id == variety_id,
                CoreForecastDailyRowModel.destination_factory_id == core_run.destination_factory_id,
            )
        ).all()
    )
    if len(matching_rows) != 1:
        return None
    return matching_rows[0]


def _resolve_exact_task9_member(
    session: Session,
    *,
    task9_run_id: int,
    target_date: date,
    forecast_quantile: ForecastQuantile,
    farm_id: int,
    subfarm_id: int,
    variety_id: int,
    destination_factory_id: int,
) -> HarvestStateDailyMemberRowModel | None:
    matching_members = list(
        session.scalars(
            select(HarvestStateDailyMemberRowModel).where(
                HarvestStateDailyMemberRowModel.harvest_state_run_id == task9_run_id,
                HarvestStateDailyMemberRowModel.state_date == target_date,
                HarvestStateDailyMemberRowModel.forecast_quantile == forecast_quantile,
                HarvestStateDailyMemberRowModel.farm_id == farm_id,
                HarvestStateDailyMemberRowModel.subfarm_id == subfarm_id,
                HarvestStateDailyMemberRowModel.variety_id == variety_id,
                HarvestStateDailyMemberRowModel.destination_factory_id == destination_factory_id,
            )
        ).all()
    )
    if len(matching_members) != 1:
        return None
    return matching_members[0]


def _resolve_exact_task10_prediction(
    session: Session,
    *,
    task9_run_id: int,
    forecast_cutoff_at: datetime,
    target_date: date,
    horizon_days: int,
    destination_factory_id: int,
) -> tuple[ResidualModelPredictionRun, ResidualModelPredictionRow, ResidualModelTrainingRun] | None:
    prediction_runs = list(
        session.scalars(
            select(ResidualModelPredictionRun).where(
                ResidualModelPredictionRun.task9_run_id == task9_run_id,
                ResidualModelPredictionRun.execution_status == "completed",
                ResidualModelPredictionRun.completed_at.is_not(None),
                ResidualModelPredictionRun.completed_at <= forecast_cutoff_at,
            )
        ).all()
    )
    matching_runs: list[
        tuple[ResidualModelPredictionRun, ResidualModelPredictionRow, ResidualModelTrainingRun]
    ] = []
    for prediction_run in prediction_runs:
        if prediction_run.training_run_id is None:
            continue
        training_run = session.get(ResidualModelTrainingRun, prediction_run.training_run_id)
        if training_run is None or training_run.finished_at is None:
            continue
        if not _visible_at_or_before(training_run.finished_at, forecast_cutoff_at):
            continue
        matching_rows = list(
            session.scalars(
                select(ResidualModelPredictionRow).where(
                    ResidualModelPredictionRow.prediction_run_id == prediction_run.id,
                    ResidualModelPredictionRow.arrival_local_date == target_date,
                    ResidualModelPredictionRow.forecast_horizon_days == horizon_days,
                    ResidualModelPredictionRow.destination_factory_id == destination_factory_id,
                )
            ).all()
        )
        if len(matching_rows) != 1:
            continue
        matching_runs.append((prediction_run, matching_rows[0], training_run))
    if len(matching_runs) != 1:
        return None
    return matching_runs[0]


def load_persisted_forecast_binding_authority(
    session: Session,
    *,
    forecast_cutoff_at: datetime,
    task8_forecast_run_id: int,
    target_date: date,
    forecast_quantile: ForecastQuantile,
    horizon_days: int,
    farm_id: int,
    subfarm_id: int,
    variety_id: int,
) -> S2ForecastAuthorityBundle | None:
    """Load the exact persisted S2ForecastAuthorityBundle for one binding row."""
    core_run = _resolve_core_forecast_run(
        session,
        forecast_cutoff_at=forecast_cutoff_at,
        task8_forecast_run_id=task8_forecast_run_id,
    )
    if core_run is None:
        return None

    core_row = _resolve_exact_core_daily_row(
        session,
        core_run=core_run,
        target_date=target_date,
        forecast_quantile=forecast_quantile,
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        variety_id=variety_id,
    )
    if core_row is None:
        return None

    code_authority = session.get(CoreForecastCodeAuthorityModel, core_run.code_authority_id)
    task9_run = session.get(HarvestStateRun, core_run.task9_harvest_state_run_id)
    if code_authority is None or task9_run is None:
        return None
    if task9_run.result_hash != core_run.task9_result_hash:
        return None

    task9_member = _resolve_exact_task9_member(
        session,
        task9_run_id=task9_run.id,
        target_date=target_date,
        forecast_quantile=forecast_quantile,
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        variety_id=variety_id,
        destination_factory_id=core_run.destination_factory_id,
    )
    if task9_member is None:
        return None

    task10_match = _resolve_exact_task10_prediction(
        session,
        task9_run_id=task9_run.id,
        forecast_cutoff_at=forecast_cutoff_at,
        target_date=target_date,
        horizon_days=horizon_days,
        destination_factory_id=core_run.destination_factory_id,
    )
    if task10_match is None:
        return None
    prediction_run, prediction_row, training_run = task10_match

    bundle = S2ForecastAuthorityBundle(
        forecast_run_identity_hash=core_run.result_hash,
        daily_row_identity_hash=core_row.row_hash,
        task9_authority_identity_hash=task9_run.result_hash,
        task9_member_identity_hash=_task9_member_identity_hash(task9_member),
        task10_authority_identity_hash=prediction_run.prediction_hash,
        task10_model_identity_hash=training_run.training_signature,
        task10_replay_identity_hash=prediction_run.prediction_input_signature,
        task10_prediction_row_identity_hash=prediction_row.prediction_row_hash,
        historical_code_authority_id=code_authority.id,
        forecast_code_identity=code_authority.authority_hash,
        historical_code_identity=code_authority.source_commit_sha,
        build_artifact_hash=code_authority.build_artifact_hash,
        config_bundle_hash=code_authority.config_bundle_hash,
        model_identity=core_run.task8_artifact_hash,
        parameter_identity=core_row.marketable_policy_hash,
        data_identity=core_run.forecast_input_hash,
        available_at=_as_utc_aware(task9_run.forecast_effective_cutoff_at or forecast_cutoff_at),
        task10_model_available_at=_as_utc_aware(
            training_run.finished_at if training_run.finished_at is not None else forecast_cutoff_at
        ),
        historical_code_available_at=_as_utc_aware(code_authority.available_at),
    )
    if is_synthetic_forecast_authority(bundle):
        return None
    return bundle
