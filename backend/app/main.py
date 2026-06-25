from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.api.harvest_state import router as harvest_state_router
from backend.app.api.health import router as health_router
from backend.app.api.master_data import router as master_data_router
from backend.app.api.maturity import router as maturity_router
from backend.app.api.planning import router as planning_router
from backend.app.api.production_plans import router as production_plan_router
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


def create_app(settings: AppSettings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(title=app_settings.app_name, version=APP_VERSION, lifespan=lifespan)
    app.state.settings = app_settings

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
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
    app.include_router(harvest_state_router, prefix="/api/v1/harvest-state", tags=["harvest-state"])
    app.include_router(master_data_router, prefix="/api/v1/master-data", tags=["master-data"])
    app.include_router(planning_router, prefix="/planning", tags=["planning"])
    app.include_router(production_plan_router, prefix="/planning", tags=["production-plans"])
    app.include_router(weather_router, prefix="/planning", tags=["weather"])
    app.include_router(maturity_router, prefix="/planning", tags=["maturity"])
    return app


app = create_app()
