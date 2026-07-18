from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.actual_harvest_import.api_errors import ActualHarvestApiError
from backend.app.actual_harvest_import.api_policy import ActualHarvestRequestBodyLimitMiddleware
from backend.app.api.actual_harvest_imports import router as actual_harvest_import_router
from backend.app.api.harvest_state import router as harvest_state_router
from backend.app.api.health import router as health_router
from backend.app.api.master_data import router as master_data_router
from backend.app.api.maturity import router as maturity_router
from backend.app.api.planning import router as planning_router
from backend.app.api.production_plans import router as production_plan_router
from backend.app.api.residual_model import router as residual_model_router
from backend.app.api.rolling_backtest_replay_trained import (
    router as rolling_backtest_replay_trained_router,
)
from backend.app.api.weather import router as weather_router
from backend.app.core.config import AppSettings, get_settings
from backend.app.core.version import APP_VERSION
from backend.app.db import session as db_session
from backend.app.schemas.harvest_state import HarvestStateErrorResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await db_session.dispose_db_engine()


def _is_harvest_state_path(path: str) -> bool:
    return path == "/api/v1/harvest-state" or path.startswith("/api/v1/harvest-state/")


def _is_replay_trained_path(path: str) -> bool:
    return path == "/api/v1/rolling-backtest/replay-trained-predictions" or path.startswith(
        "/api/v1/rolling-backtest/replay-trained-predictions/"
    )


def _is_actual_harvest_path(path: str) -> bool:
    return path == "/api/v1/actual-harvest" or path.startswith("/api/v1/actual-harvest/")


def create_app(settings: AppSettings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(title=app_settings.app_name, version=APP_VERSION, lifespan=lifespan)
    app.state.settings = app_settings
    app.add_middleware(ActualHarvestRequestBodyLimitMiddleware)

    @app.exception_handler(ActualHarvestApiError)
    async def _handle_actual_harvest_api_error(
        request: Request,
        exc: ActualHarvestApiError,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "request_id": None,
                "status": "ERROR",
                "data_or_null": None,
                "errors": [
                    {
                        "code": exc.code.value,
                        "message_template_id": exc.code.value,
                        "details": exc.details,
                    }
                ],
                "warnings": [],
                "pagination_or_null": None,
                "canonical_hashes": {},
                "provenance": {"api_policy_version": "actual-harvest-api-policy-v1"},
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        if _is_replay_trained_path(request.url.path):
            return JSONResponse(
                status_code=422,
                content={
                    "error": {
                        "code": "TASK012_REPLAY_TRAINED_INPUT_INVALID",
                        "message": "Replay-trained request is invalid.",
                        "blocker": None,
                        "identity": {},
                    }
                },
            )
        if _is_actual_harvest_path(request.url.path):
            error_code = "API_REQUEST_INVALID"
            if any(
                marker in str(item.get("msg", "")).lower()
                for item in exc.errors()
                for marker in ("server-generated", "source file metadata")
            ):
                error_code = "SERVER_GENERATED_FIELD_SUPPLIED"
            return JSONResponse(
                status_code=422,
                content={
                    "request_id": request.headers.get("x-request-id"),
                    "status": "ERROR",
                    "data_or_null": None,
                    "errors": [
                        {
                            "code": error_code,
                            "message_template_id": error_code,
                            "details": {},
                        }
                    ],
                    "warnings": [],
                    "pagination_or_null": None,
                    "canonical_hashes": {},
                    "provenance": {"api_policy_version": "actual-harvest-api-policy-v1"},
                },
            )
        if not _is_harvest_state_path(request.url.path):
            return await request_validation_exception_handler(request, exc)
        return JSONResponse(
            status_code=422,
            content=HarvestStateErrorResponse(
                error={
                    "code": "HARVEST_STATE_DELIVERY_INPUT_ERROR",
                    "message": "Harvest-state request is invalid.",
                }
            ).model_dump(mode="json"),
        )

    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: app_settings

    app.include_router(health_router, prefix="/health", tags=["health"])
    app.include_router(
        actual_harvest_import_router,
        prefix="/api/v1/actual-harvest",
        tags=["actual-harvest-import"],
    )
    app.include_router(harvest_state_router, prefix="/api/v1/harvest-state", tags=["harvest-state"])
    app.include_router(master_data_router, prefix="/api/v1/master-data", tags=["master-data"])
    app.include_router(planning_router, prefix="/planning", tags=["planning"])
    app.include_router(production_plan_router, prefix="/planning", tags=["production-plans"])
    app.include_router(weather_router, prefix="/planning", tags=["weather"])
    app.include_router(maturity_router, prefix="/planning", tags=["maturity"])
    app.include_router(
        residual_model_router,
        prefix="/api/v1/residual-model",
        tags=["residual-model"],
    )
    app.include_router(
        rolling_backtest_replay_trained_router,
        prefix="/api/v1/rolling-backtest",
        tags=["rolling-backtest", "task-012"],
    )
    return app


app = create_app()
