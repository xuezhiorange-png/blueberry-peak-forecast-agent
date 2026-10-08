"""GET-only transport for the shared Forecast Intelligence read service."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_import.api_auth import (
    ActualHarvestActorContext,
    require_actor_scope,
)
from backend.app.actual_harvest_import.api_errors import ActualHarvestApiError
from backend.app.actual_harvest_import.enums import ActualHarvestImportChannel
from backend.app.db.session import get_db_session
from backend.app.forecast_intelligence.read_schemas import (
    CurveData,
    ForecastReadQuery,
    HierarchyData,
    OverviewData,
    QualityData,
    QualityReadQuery,
    ReadError,
    ReadModel,
    ReadResponse,
)
from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.trial import TrialActorDep


def _error(code: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "schema_version": "V0_17_FORECAST_INTELLIGENCE_READ_R1",
            "status": "AUTHORITY_MISMATCH" if status_code == 409 else "ERROR",
            "code": code,
            "data": None,
        },
    )


class ForecastIntelligenceReadRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            if len(request.scope.get("query_string", b"")) > 8192:
                return _error("INVALID_REQUEST", 422)
            try:
                return await original(request)
            except RequestValidationError:
                return _error("INVALID_REQUEST", 422)
            except ReadError as exc:
                return _error(exc.code, exc.status_code)
            except ActualHarvestApiError as exc:
                return _error(
                    "FORBIDDEN" if exc.status_code == 403 else "AUTHORIZATION_UNAVAILABLE",
                    exc.status_code,
                )
            except HTTPException as exc:
                return _error(
                    "UNAUTHENTICATED"
                    if exc.status_code == 401
                    else "FORBIDDEN"
                    if exc.status_code == 403
                    else "READ_UNAVAILABLE",
                    exc.status_code,
                )
            except SQLAlchemyError:
                return _error("PERSISTENCE_UNAVAILABLE", 503)
            except Exception:
                return _error("READ_UNAVAILABLE", 503)

        return handle


router = APIRouter(route_class=ForecastIntelligenceReadRoute)
Session = Annotated[AsyncSession, Depends(get_db_session)]
Selection = Annotated[ForecastReadQuery, Query()]


def _permission(actor: ActualHarvestActorContext, name: str) -> None:
    if not actor.identity.strip():
        raise ReadError("UNAUTHENTICATED", 401)
    require_actor_scope(
        actor,
        source_system=next(iter(sorted(actor.allowed_source_systems)), ""),
        channel=ActualHarvestImportChannel.API,
        permission=name,
    )


def get_read_service(session: Session) -> ForecastIntelligenceReadService:
    return ForecastIntelligenceReadService(session)


Service = Annotated[ForecastIntelligenceReadService, Depends(get_read_service)]


@router.get("/overview", response_model=ReadResponse[OverviewData])
async def overview(
    query: Selection, service: Service, actor: TrialActorDep
) -> ReadResponse[OverviewData]:
    _permission(actor, "may_read_forecast")
    return await service.overview(query)


@router.get("/curve", response_model=ReadResponse[CurveData])
async def curve(
    query: Selection, service: Service, actor: TrialActorDep
) -> ReadResponse[CurveData]:
    _permission(actor, "may_read_forecast")
    return await service.curve(query)


@router.get("/hierarchy", response_model=ReadResponse[HierarchyData])
async def hierarchy(
    query: Selection, service: Service, actor: TrialActorDep
) -> ReadResponse[HierarchyData]:
    _permission(actor, "may_read_forecast")
    return await service.hierarchy(query)


@router.get("/uncertainty", response_model=ReadResponse[ReadModel])
async def uncertainty(
    query: Selection, service: Service, actor: TrialActorDep
) -> ReadResponse[ReadModel]:
    _permission(actor, "may_read_forecast")
    return await service.uncertainty(query)


@router.get("/attribution", response_model=ReadResponse[ReadModel])
async def attribution(
    query: Selection, service: Service, actor: TrialActorDep
) -> ReadResponse[ReadModel]:
    _permission(actor, "may_read_forecast")
    return await service.attribution(query)


@router.get("/quality", response_model=ReadResponse[QualityData])
async def quality(
    query: Annotated[QualityReadQuery, Query()], service: Service, actor: TrialActorDep
) -> ReadResponse[QualityData]:
    _permission(actor, "may_read_quality")
    return await service.quality(query)
