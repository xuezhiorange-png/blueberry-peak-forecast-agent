"""Bounded, non-persistent decision requests over the shared application service."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError

from backend.app.actual_harvest_import.api_errors import ActualHarvestApiError
from backend.app.api.forecast_intelligence_read import _permission, get_read_service
from backend.app.forecast_intelligence.decision_schemas import (
    BODY_LIMIT,
    BusinessLossExposure,
    ComparisonData,
    ComparisonRequest,
    CostSelection,
    DecisionResponse,
    SimulationRequest,
    SimulationResult,
)
from backend.app.forecast_intelligence.decision_service import DecisionSupportService
from backend.app.forecast_intelligence.read_schemas import ReadError, ReadModel
from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.trial import TrialActorDep


def decision_error(code: str, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "schema_version": "V0_17_S2_DECISION_SUPPORT_API_R1",
            "status": "AUTHORITY_MISMATCH" if status == 409 else "ERROR",
            "code": code,
            "data": None,
        },
    )


class DecisionRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            if len(request.scope.get("query_string", b"")) > 8192:
                return decision_error("INVALID_REQUEST", 422)
            if request.method == "POST":
                body = bytearray()
                async for chunk in request.stream():
                    if len(body) + len(chunk) > BODY_LIMIT:
                        return decision_error("REQUEST_BODY_TOO_LARGE", 413)
                    body.extend(chunk)
                request._body = bytes(body)
            try:
                return await original(request)
            except RequestValidationError:
                return decision_error("INVALID_REQUEST", 422)
            except ReadError as exc:
                return decision_error(exc.code, exc.status_code)
            except ActualHarvestApiError as exc:
                return decision_error(
                    "FORBIDDEN" if exc.status_code == 403 else "AUTHORIZATION_UNAVAILABLE",
                    exc.status_code,
                )
            except HTTPException as exc:
                return decision_error(
                    "UNAUTHENTICATED"
                    if exc.status_code == 401
                    else "FORBIDDEN"
                    if exc.status_code == 403
                    else "DECISION_UNAVAILABLE",
                    exc.status_code,
                )
            except SQLAlchemyError:
                return decision_error("PERSISTENCE_UNAVAILABLE", 503)
            except Exception:
                return decision_error("DECISION_UNAVAILABLE", 503)

        return handle


def get_decision_service(
    reader: Annotated[ForecastIntelligenceReadService, Depends(get_read_service)],
) -> DecisionSupportService:
    return DecisionSupportService(reader)


def request_schema(model: type[ReadModel]) -> dict[str, Any]:
    """Inline Pydantic request definitions for a two-phase domain validation API."""
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})

    def expand(value: Any) -> Any:
        if isinstance(value, list):
            return [expand(v) for v in value]
        if isinstance(value, dict):
            if "$ref" in value:
                return expand(definitions[value["$ref"].rsplit("/", 1)[-1]])
            if "propertyName" in value and "mapping" in value:
                # Definitions are inlined; stale #/$defs discriminator references are not valid.
                return {"propertyName": value["propertyName"]}
            return {k: expand(v) for k, v in value.items()}
        return value

    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": expand(schema)}},
        }
    }


Service = Annotated[DecisionSupportService, Depends(get_decision_service)]
router = APIRouter(route_class=DecisionRoute)


@router.get("/business-loss", response_model=DecisionResponse[BusinessLossExposure])
async def business_loss(
    selection: Annotated[CostSelection, Query()], service: Service, actor: TrialActorDep
) -> DecisionResponse[BusinessLossExposure]:
    _permission(actor, "may_read_forecast")
    return service.business_loss(selection)


@router.post(
    "/simulate-capacity",
    response_model=DecisionResponse[SimulationResult],
    openapi_extra=request_schema(SimulationRequest),
)
async def simulate_capacity(
    service: Service, actor: TrialActorDep, payload: Annotated[dict[str, Any], Body()]
) -> DecisionResponse[SimulationResult]:
    _permission(actor, "may_read_forecast")
    return await service.simulate(payload)


@router.post(
    "/compare-capacity-scenarios",
    response_model=DecisionResponse[ComparisonData],
    openapi_extra=request_schema(ComparisonRequest),
)
async def compare_capacity_scenarios(
    service: Service, actor: TrialActorDep, payload: Annotated[dict[str, Any], Body()]
) -> DecisionResponse[ComparisonData]:
    _permission(actor, "may_read_forecast")
    return await service.compare(payload)
