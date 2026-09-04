"""Load persisted S2 forecast binding authority for live pairing materialization."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.app.models.core_forecast import CoreForecastDailyRowModel, CoreForecastRunModel
from backend.app.models.harvest_state import HarvestStateDailyMemberRowModel
from backend.app.rolling_backtest.persisted_forecast_authority import (
    ForecastQuantile,
    _resolve_exact_core_daily_row_sync,
    build_canonical_s2_forecast_authority_bundle,
    resolve_persisted_forecast_binding_refs,
    validate_persisted_forecast_authority_chain,
)
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
    return _resolve_exact_core_daily_row_sync(
        session,
        core_run=core_run,
        target_date=target_date,
        forecast_quantile=forecast_quantile,
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        variety_id=variety_id,
    )


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


async def load_persisted_forecast_binding_authority(
    session: AsyncSession,
    *,
    forecast_cutoff_at: datetime,
    task8_forecast_run_id: int,
    target_date: date,
    forecast_quantile: ForecastQuantile,
    horizon_days: int,
    farm_id: int,
    subfarm_id: int,
    variety_id: int,
    task10_prediction_run_id: int | None,
) -> S2ForecastAuthorityBundle | None:
    """Load one exact persisted authority bundle using the shared canonical validator."""
    if task10_prediction_run_id is None:
        return None
    refs = await resolve_persisted_forecast_binding_refs(
        session,
        forecast_cutoff_at=forecast_cutoff_at,
        task8_forecast_run_id=task8_forecast_run_id,
        target_date=target_date,
        forecast_quantile=forecast_quantile,
        horizon_days=horizon_days,
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        variety_id=variety_id,
        task10_prediction_run_id=task10_prediction_run_id,
    )
    if refs is None:
        return None
    try:
        resolution = await validate_persisted_forecast_authority_chain(
            session,
            refs=refs,
            forecast_cutoff_at=forecast_cutoff_at,
            target_date=target_date,
            horizon_days=horizon_days,
        )
    except ValueError:
        return None
    bundle = build_canonical_s2_forecast_authority_bundle(resolution)
    if is_synthetic_forecast_authority(bundle):
        return None
    return bundle
