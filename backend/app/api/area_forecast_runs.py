"""Explicit run persistence endpoints; stateless trial forecast remains unchanged."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.area_yield.product import AreaDrivenForecastRequest, DailyAreaForecast
from backend.app.area_yield.product_errors import (
    AreaForecastAuthorityError,
    AreaForecastRequestError,
)
from backend.app.area_yield.run_application import execute_area_forecast_run
from backend.app.area_yield.run_persistence import (
    AreaForecastPersistenceConflictError,
    AreaForecastPersistenceIntegrityError,
    AreaForecastRunNotFoundError,
    AreaForecastRunRepository,
    AreaForecastWriteFailure,
)
from backend.app.area_yield.run_schemas import (
    AreaRunHistory,
    CreateAreaForecastRun,
    SavedAreaForecastRun,
)
from backend.app.db.session import get_db_session
from backend.app.trial import TrialActorDep, TrialApiError, _require_forecast_permission


class AreaRunRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await original(request)
            except (AreaForecastRequestError, AreaForecastAuthorityError) as exc:
                return JSONResponse(
                    status_code=exc.status_code, content={"code": exc.code, "reason": exc.reason}
                )
            except (
                AreaForecastPersistenceConflictError,
                AreaForecastPersistenceIntegrityError,
                AreaForecastRunNotFoundError,
                AreaForecastWriteFailure,
            ) as exc:
                return JSONResponse(status_code=exc.status_code, content={"code": exc.code})
            except TrialApiError as exc:
                return JSONResponse(status_code=exc.status_code, content={"code": exc.code.value})
            except SQLAlchemyError:
                return JSONResponse(
                    status_code=503, content={"code": "AREA_FORECAST_WRITE_FAILURE"}
                )

        return handle


router = APIRouter(route_class=AreaRunRoute)
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("", response_model=SavedAreaForecastRun)
async def create_run(
    body: CreateAreaForecastRun, session: Session, actor: TrialActorDep
) -> SavedAreaForecastRun:
    _require_forecast_permission(actor, "may_create_forecast")
    request = AreaDrivenForecastRequest.model_validate(body.model_dump(exclude={"rerun_of_run_id"}))
    async with session.begin():
        result = await execute_area_forecast_run(
            session, request, rerun_of_run_id=body.rerun_of_run_id
        )
    return result


@router.get("", response_model=AreaRunHistory)
async def history(
    session: Session,
    actor: TrialActorDep,
    canonical_farm: str | None = None,
    target_season: str | None = None,
    forecast_policy_version: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
) -> AreaRunHistory:
    _require_forecast_permission(actor, "may_read_forecast")
    try:
        return await AreaForecastRunRepository(session).history(
            canonical_farm=canonical_farm,
            target_season=target_season,
            forecast_policy_version=forecast_policy_version,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        from backend.app.area_yield.product_errors import AreaForecastInputError

        raise AreaForecastInputError("INVALID_HISTORY_QUERY") from exc


@router.get("/{run_id}", response_model=SavedAreaForecastRun)
async def get_run(run_id: int, session: Session, actor: TrialActorDep) -> SavedAreaForecastRun:
    _require_forecast_permission(actor, "may_read_forecast")
    return await AreaForecastRunRepository(session).get(run_id)


@router.get("/{run_id}/daily", response_model=list[DailyAreaForecast])
async def get_daily(run_id: int, session: Session, actor: TrialActorDep) -> list[DailyAreaForecast]:
    _require_forecast_permission(actor, "may_read_forecast")
    return (await AreaForecastRunRepository(session).get(run_id)).result.daily_forecast
