"""REST transport for persisted S6 operational peak runs."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.forecast_quality.operational_peak import (
    OperationalPeakForecastError,
    OperationalPeakForecastRequest,
)
from backend.app.forecast_quality.operational_peak_application import (
    execute_operational_peak_forecast_run,
)
from backend.app.forecast_quality.operational_peak_authority import (
    OperationalPeakAuthorityError,
)
from backend.app.forecast_quality.operational_peak_persistence import (
    OperationalPeakPersistenceConflictError,
    OperationalPeakPersistenceIntegrityError,
    OperationalPeakRerunScopeMismatch,
    OperationalPeakRunNotFoundError,
    OperationalPeakRunRepository,
    OperationalPeakWriteFailure,
)
from backend.app.forecast_quality.operational_peak_schemas import (
    CreateOperationalPeakRun,
    OperationalPeakDailyRows,
    OperationalPeakHistoryQuery,
    OperationalPeakRunHistory,
    SavedOperationalPeakRun,
)
from backend.app.trial import TrialActorDep, TrialApiError, _require_forecast_permission


class OperationalPeakRunRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse(status_code=422, content={"code": "INVALID_REQUEST"})
            except OperationalPeakAuthorityError as exc:
                return JSONResponse(
                    status_code=503,
                    content={"code": exc.code, "reason": exc.reason},
                )
            except OperationalPeakForecastError as exc:
                status = 422 if exc.code in {"INVALID_REQUEST", "UNREGISTERED_BASE"} else 503
                return JSONResponse(
                    status_code=status,
                    content={"code": exc.code, "reason": exc.reason},
                )
            except (
                OperationalPeakRerunScopeMismatch,
                OperationalPeakPersistenceConflictError,
                OperationalPeakPersistenceIntegrityError,
                OperationalPeakRunNotFoundError,
                OperationalPeakWriteFailure,
            ) as exc:
                return JSONResponse(status_code=exc.status_code, content={"code": exc.code})
            except TrialApiError as exc:
                return JSONResponse(status_code=exc.status_code, content={"code": exc.code.value})
            except SQLAlchemyError:
                return JSONResponse(
                    status_code=503,
                    content={"code": "OPERATIONAL_PEAK_WRITE_FAILURE"},
                )

        return handle


router = APIRouter(route_class=OperationalPeakRunRoute)
Session = Annotated[AsyncSession, Depends(get_db_session)]


def _validate_run_id(run_id: int) -> None:
    if run_id <= 0:
        raise OperationalPeakForecastError("INVALID_REQUEST", "run_id must be positive")


@router.post("", response_model=SavedOperationalPeakRun)
async def create_run(
    body: CreateOperationalPeakRun,
    session: Session,
    actor: TrialActorDep,
) -> SavedOperationalPeakRun:
    _require_forecast_permission(actor, "may_create_forecast")
    request = OperationalPeakForecastRequest.from_mapping(body.model_dump())
    async with session.begin():
        return await execute_operational_peak_forecast_run(
            session,
            request,
            rerun_of_run_id=body.rerun_of_run_id,
        )


@router.get("", response_model=OperationalPeakRunHistory)
async def history(
    session: Session,
    actor: TrialActorDep,
    base_id: str | None = None,
    target_season: str | None = None,
    policy_version: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
) -> OperationalPeakRunHistory:
    _require_forecast_permission(actor, "may_read_forecast")
    query = OperationalPeakHistoryQuery(
        base_id=base_id,
        target_season=target_season,
        policy_version=policy_version,
        limit=limit,
        cursor=cursor,
    )
    try:
        return await OperationalPeakRunRepository(session).history(**query.model_dump())
    except ValueError as exc:
        raise OperationalPeakForecastError("INVALID_REQUEST", "INVALID_HISTORY_QUERY") from exc


@router.get("/{run_id}/daily", response_model=OperationalPeakDailyRows)
async def daily(
    run_id: int,
    session: Session,
    actor: TrialActorDep,
) -> OperationalPeakDailyRows:
    _require_forecast_permission(actor, "may_read_forecast")
    _validate_run_id(run_id)
    return await OperationalPeakRunRepository(session).daily(run_id)


@router.get("/{run_id}", response_model=SavedOperationalPeakRun)
async def get_run(
    run_id: int,
    session: Session,
    actor: TrialActorDep,
) -> SavedOperationalPeakRun:
    _require_forecast_permission(actor, "may_read_forecast")
    _validate_run_id(run_id)
    return await OperationalPeakRunRepository(session).get(run_id)


__all__ = ["router"]
