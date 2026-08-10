from __future__ import annotations

from datetime import UTC, date, datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.repositories.harvest_state import get_harvest_state_run


class ForecastCutoffResolutionError(RuntimeError):
    """Raised when the forecast-side point-in-time cutoff cannot be resolved."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def normalize_forecast_cutoff_at(value: datetime) -> datetime:
    """Return a forecast cutoff in the canonical UTC representation."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _legacy_non_replay_cutoff(as_of_date: date) -> datetime:
    """Preserve legacy EOD semantics only for non-replay executions."""

    return datetime.combine(as_of_date, time.max, tzinfo=UTC)


async def resolve_forecast_cutoff_at(
    session: AsyncSession,
    *,
    task9_run_id: int,
    as_of_date: date,
) -> datetime:
    """Resolve the exact forecast-side visibility cutoff for a Task 9 run.

    Replay rows must carry the persisted effective cutoff. Historical
    non-replay rows may use the legacy end-of-day compatibility value until
    they are migrated to explicit forecast cutoff metadata.
    """

    run = await get_harvest_state_run(session, run_id=task9_run_id)
    if run is None:
        raise ForecastCutoffResolutionError(
            "FORECAST_RUN_NOT_FOUND",
            f"HarvestStateRun {task9_run_id} was not found while resolving forecast cutoff",
        )

    if run.forecast_effective_cutoff_at is not None:
        return normalize_forecast_cutoff_at(run.forecast_effective_cutoff_at)

    if run.is_replay is True:
        raise ForecastCutoffResolutionError(
            "REPLAY_FORECAST_EFFECTIVE_CUTOFF_MISSING",
            "replay Task 9 run has no persisted forecast_effective_cutoff_at",
        )

    return _legacy_non_replay_cutoff(as_of_date)
