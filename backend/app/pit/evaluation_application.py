"""Application service for V0.6-S3 evaluation.

The service reloads the immutable S1 forecast snapshot, reads its persisted
daily rows and weather snapshot identities, computes evaluation output, and
persists only a new S3 evaluation authority.  The caller owns the
transaction.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.pit.evaluation import (
    ActualDailyRecord,
    EvaluationMode,
    RealizedWeatherPoint,
    compute_forecast_actual_evaluation,
)
from backend.app.pit.evaluation_models import ForecastEvaluation
from backend.app.pit.evaluation_persistence import ForecastEvaluationRepository
from backend.app.pit.models import ForecastRunSnapshotDaily, RealizedWeatherObservation
from backend.app.pit.persistence import PITDataFoundationRepository


def _realized_weather_point(model: RealizedWeatherObservation) -> RealizedWeatherPoint:
    return RealizedWeatherPoint(
        base_id=model.base_id or model.location_id or "",
        observation_time=model.observation_time,
        temperature=model.temperature,
        precipitation=model.precipitation,
        known_at=model.known_at,
        observation_id=model.weather_observation_id,
        source_hash=model.payload_hash,
    )


async def load_realized_weather_observations(
    session: AsyncSession,
    *,
    observation_ids: Sequence[str],
) -> tuple[RealizedWeatherPoint, ...]:
    if not observation_ids:
        return ()
    models = list(
        await session.scalars(
            select(RealizedWeatherObservation).where(
                RealizedWeatherObservation.weather_observation_id.in_(sorted(set(observation_ids)))
            )
        )
    )
    by_id = {model.weather_observation_id: model for model in models}
    if set(by_id) != set(observation_ids):
        raise ValueError("REALIZED_WEATHER_AUTHORITY_NOT_FOUND")
    return tuple(
        _realized_weather_point(by_id[observation_id]) for observation_id in observation_ids
    )


async def evaluate_forecast_run(
    session: AsyncSession,
    *,
    forecast_run_id: str,
    actual_records: Sequence[ActualDailyRecord],
    evaluation_mode: EvaluationMode,
    evaluation_created_at: datetime,
    as_of_date: date | None = None,
    realized_weather_observations: Sequence[RealizedWeatherPoint] = (),
) -> ForecastEvaluation:
    """Persist one deterministic evaluation and return its repository.

    The returned row is a persisted authority, not a transport response; the
    service never changes the forecast snapshot.
    """

    pit_repository = PITDataFoundationRepository(session)
    snapshot = await pit_repository.get_forecast_run_snapshot(forecast_run_id)
    daily_rows = list(
        await session.scalars(
            select(ForecastRunSnapshotDaily)
            .where(ForecastRunSnapshotDaily.forecast_run_id == forecast_run_id)
            .order_by(ForecastRunSnapshotDaily.row_index)
        )
    )
    weather_snapshots = await pit_repository.visible_weather_forecast_snapshots(
        weather_snapshot_ids=snapshot.weather_snapshot_ids,
        forecast_created_at=snapshot.forecast_created_at,
    )
    computation = compute_forecast_actual_evaluation(
        forecast_snapshot=snapshot,
        forecast_daily_rows=daily_rows,
        actual_records=actual_records,
        evaluation_mode=evaluation_mode,
        as_of_date=as_of_date,
        evaluation_created_at=evaluation_created_at,
        realized_weather_observations=realized_weather_observations,
        forecast_weather_snapshots=weather_snapshots,
    )
    repository = ForecastEvaluationRepository(session)
    return await repository.save(computation)


__all__ = ["evaluate_forecast_run", "load_realized_weather_observations"]
