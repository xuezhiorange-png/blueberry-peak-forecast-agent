"""Load persisted S2 forecast binding authority for live pairing materialization."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.core_forecast import (
    CoreForecastCodeAuthorityModel,
    CoreForecastDailyRowModel,
    CoreForecastRunModel,
)
from backend.app.models.harvest_state import HarvestStateDailyMemberRowModel, HarvestStateRun
from backend.app.models.maturity import MaturityDailyPredictionModel, MaturityForecastRun
from backend.app.models.residual_model import (
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.rolling_backtest.orchestration import _task9_member_identity_hash
from backend.app.rolling_backtest.resolution import task8_daily_prediction_payload_hash
from backend.app.rolling_backtest.schemas import S2ForecastAuthorityBundle

_SYNTHETIC_SINGLE_CHAR_HEX = frozenset(ch * 64 for ch in "0123456789abcdef")


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


def load_persisted_forecast_binding_authority(
    session: Session,
    *,
    forecast_cutoff_at: datetime,
    task8_forecast_run_id: int | None = None,
) -> S2ForecastAuthorityBundle | None:
    """Load a persisted S2ForecastAuthorityBundle visible at ``forecast_cutoff_at``."""
    core_runs = list(
        session.scalars(
            select(CoreForecastRunModel).where(
                CoreForecastRunModel.status == "completed",
                CoreForecastRunModel.forecast_effective_cutoff_at == forecast_cutoff_at,
                CoreForecastRunModel.completed_at <= forecast_cutoff_at,
            )
        ).all()
    )
    if task8_forecast_run_id is not None:
        core_runs = [
            run for run in core_runs if run.task8_forecast_run_id == task8_forecast_run_id
        ]
    if len(core_runs) != 1:
        return None
    core_run = core_runs[0]
    if (
        core_run.code_authority_id is None
        or core_run.code_authority_hash is None
        or core_run.forecast_effective_cutoff_at is None
    ):
        return None

    code_authority = session.get(CoreForecastCodeAuthorityModel, core_run.code_authority_id)
    task9_run = session.get(HarvestStateRun, core_run.task9_harvest_state_run_id)
    if code_authority is None or task9_run is None:
        return None
    if task9_run.result_hash != core_run.task9_result_hash:
        return None

    prediction_runs = list(
        session.scalars(
            select(ResidualModelPredictionRun).where(
                ResidualModelPredictionRun.task9_run_id == core_run.task9_harvest_state_run_id,
                ResidualModelPredictionRun.execution_status == "completed",
                ResidualModelPredictionRun.completed_at.is_not(None),
                ResidualModelPredictionRun.completed_at <= forecast_cutoff_at,
            )
        ).all()
    )
    if len(prediction_runs) != 1:
        return None
    prediction_run = prediction_runs[0]
    if prediction_run.training_run_id is None:
        return None
    training_run = session.get(ResidualModelTrainingRun, prediction_run.training_run_id)
    if training_run is None or training_run.finished_at is None:
        return None
    if training_run.finished_at > forecast_cutoff_at:
        return None

    prediction_row = session.scalar(
        select(ResidualModelPredictionRow)
        .where(ResidualModelPredictionRow.prediction_run_id == prediction_run.id)
        .order_by(ResidualModelPredictionRow.arrival_local_date.asc())
        .limit(1)
    )
    core_daily_row = session.scalar(
        select(CoreForecastDailyRowModel)
        .where(CoreForecastDailyRowModel.core_forecast_run_id == core_run.id)
        .order_by(
            CoreForecastDailyRowModel.date.asc(),
            CoreForecastDailyRowModel.forecast_quantile.asc(),
        )
        .limit(1)
    )
    task9_member = session.scalar(
        select(HarvestStateDailyMemberRowModel)
        .where(HarvestStateDailyMemberRowModel.harvest_state_run_id == task9_run.id)
        .order_by(
            HarvestStateDailyMemberRowModel.state_date.asc(),
            HarvestStateDailyMemberRowModel.forecast_quantile.asc(),
            HarvestStateDailyMemberRowModel.id.asc(),
        )
        .limit(1)
    )
    if prediction_row is None or core_daily_row is None or task9_member is None:
        return None

    task8_run = session.get(MaturityForecastRun, core_run.task8_forecast_run_id)
    task8_daily = session.scalar(
        select(MaturityDailyPredictionModel)
        .where(
            MaturityDailyPredictionModel.forecast_run_id == core_run.task8_forecast_run_id,
            MaturityDailyPredictionModel.created_at <= forecast_cutoff_at,
        )
        .order_by(MaturityDailyPredictionModel.prediction_date.asc())
        .limit(1)
    )
    if task8_run is None or task8_daily is None:
        return None

    daily_row_identity_hash = task8_daily_prediction_payload_hash(
        task8_daily,
        forecast_source_signature=task8_run.source_signature,
    )
    bundle = S2ForecastAuthorityBundle(
        forecast_run_identity_hash=core_run.result_hash,
        daily_row_identity_hash=daily_row_identity_hash,
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
        parameter_identity=core_daily_row.marketable_policy_hash,
        data_identity=core_run.forecast_input_hash,
        available_at=task9_run.forecast_effective_cutoff_at or forecast_cutoff_at,
        task10_model_available_at=training_run.finished_at,
        historical_code_available_at=code_authority.available_at,
    )
    if is_synthetic_forecast_authority(bundle):
        return None
    return bundle
