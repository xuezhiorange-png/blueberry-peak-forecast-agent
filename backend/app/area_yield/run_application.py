"""Explicit persisted execution: one authority read, no stateless-path side effects."""

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.area_yield.product import AreaDrivenForecastRequest
from backend.app.area_yield.product_authority import forecast_with_authority, load_authority
from backend.app.area_yield.run_persistence import AreaForecastRunRepository, execution_hash
from backend.app.area_yield.run_schemas import SavedAreaForecastRun


async def execute_area_forecast_run(
    session: AsyncSession, request: AreaDrivenForecastRequest, *, rerun_of_run_id: int | None = None
) -> SavedAreaForecastRun:
    """Caller owns begin/commit/rollback; repository only flushes within a savepoint."""
    authority = load_authority()
    snapshot = request.model_dump(mode="json")
    identity = execution_hash(snapshot, authority["hash"])
    repository = AreaForecastRunRepository(session)
    existing = await repository.existing(identity, snapshot)
    if existing:
        return existing
    if rerun_of_run_id is not None:
        await repository.get(rerun_of_run_id)
    result = forecast_with_authority(request, authority)
    return await repository.save(snapshot, result, identity, rerun_of_run_id)
