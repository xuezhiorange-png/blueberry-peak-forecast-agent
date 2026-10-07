"""Permission-preserving REST adapter; no reconciliation logic in transport."""

from collections.abc import Callable, Coroutine
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.forecast_intelligence.application import (
    current_hierarchy,
    execute_hierarchical_run,
)
from backend.app.forecast_intelligence.errors import HierarchicalForecastError
from backend.app.forecast_intelligence.persistence import HierarchicalRunRepository
from backend.app.forecast_intelligence.schemas import (
    CreateHierarchicalRun,
    HierarchicalDailyRows,
    HierarchicalHistoryQuery,
    HierarchicalRunHistory,
    SavedHierarchicalRun,
)
from backend.app.trial import TrialActorDep, TrialApiError, _require_forecast_permission


class HierarchicalRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse(status_code=422, content={"code": "INVALID_REQUEST"})
            except HierarchicalForecastError as exc:
                return JSONResponse(status_code=exc.status_code, content={"code": exc.code})
            except TrialApiError as exc:
                return JSONResponse(status_code=exc.status_code, content={"code": str(exc.code)})
            except Exception:
                return JSONResponse(
                    status_code=503, content={"code": "HIERARCHICAL_FORECAST_WRITE_FAILURE"}
                )

        return handle


router = APIRouter(route_class=HierarchicalRoute)
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("/hierarchical-forecast-runs", response_model=SavedHierarchicalRun)
async def create_run(
    body: CreateHierarchicalRun, session: Session, actor: TrialActorDep
) -> SavedHierarchicalRun:
    _require_forecast_permission(actor, "may_create_forecast")
    async with session.begin():
        return await execute_hierarchical_run(session, body)


@router.get("/hierarchical-forecast-runs", response_model=HierarchicalRunHistory)
async def history(
    session: Session,
    actor: TrialActorDep,
    target_entity_type: Literal["REGION", "COMPANY"] | None = None,
    target_entity_id: str | None = None,
    target_season: str | None = None,
    origin_date: date | None = None,
    reconciliation_policy_version: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
) -> HierarchicalRunHistory:
    _require_forecast_permission(actor, "may_read_forecast")
    query = HierarchicalHistoryQuery(
        target_entity_type=target_entity_type,
        target_entity_id=target_entity_id,
        target_season=target_season,
        origin_date=origin_date,
        reconciliation_policy_version=reconciliation_policy_version,
        limit=limit,
        cursor=cursor,
    )
    return await HierarchicalRunRepository(session).history(query)


@router.get("/hierarchical-forecast-runs/{run_id}", response_model=SavedHierarchicalRun)
async def get_run(run_id: int, session: Session, actor: TrialActorDep) -> SavedHierarchicalRun:
    _require_forecast_permission(actor, "may_read_forecast")
    return await HierarchicalRunRepository(session).get(run_id)


@router.get("/hierarchical-forecast-runs/{run_id}/daily", response_model=HierarchicalDailyRows)
async def daily(run_id: int, session: Session, actor: TrialActorDep) -> HierarchicalDailyRows:
    _require_forecast_permission(actor, "may_read_forecast")
    return await HierarchicalRunRepository(session).daily(run_id)


@router.get("/hierarchical-forecast-hierarchy")
async def hierarchy(actor: TrialActorDep) -> dict[str, Any]:
    _require_forecast_permission(actor, "may_read_forecast")
    return current_hierarchy()
