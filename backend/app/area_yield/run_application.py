"""Explicit persisted execution: one authority read, no stateless-path side effects."""

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.area_yield.product import AreaDrivenForecastRequest
from backend.app.area_yield.product_authority import forecast_with_authority, load_authority
from backend.app.area_yield.run_persistence import (
    AreaForecastRerunScopeMismatch,
    AreaForecastRunRepository,
    execution_hash,
)
from backend.app.area_yield.run_schemas import SavedAreaForecastRun, same_rerun_scope
from backend.app.area_yield.shape_r3 import season_calendar


async def execute_area_forecast_run(
    session: AsyncSession, request: AreaDrivenForecastRequest, *, rerun_of_run_id: int | None = None
) -> SavedAreaForecastRun:
    """Caller owns begin/commit/rollback; repository only flushes within a savepoint."""
    authority = load_authority()
    snapshot = request.model_dump(mode="json")
    identity = execution_hash(snapshot, authority["hash"])
    repository = AreaForecastRunRepository(session)
    if rerun_of_run_id is not None:
        parent = await repository.get(rerun_of_run_id)
        # Use the product's exact authorized alias map and calendar, never fuzzy identity
        # or a second authority load/forecast. Validate even when identity already exists.
        calendar = season_calendar(request.target_season)
        if not same_rerun_scope(
            parent.result,
            canonical_farm=authority.get("aliases", {}).get(request.farm, request.farm),
            target_season=request.target_season,
            season_start=request.season_start or calendar[0],
            season_end=request.season_end or calendar[-1],
        ):
            raise AreaForecastRerunScopeMismatch("RERUN_SCOPE_MISMATCH")
    existing = await repository.existing(identity, snapshot)
    if existing:
        return existing
    result = forecast_with_authority(request, authority)
    return await repository.save(snapshot, result, identity, rerun_of_run_id)
