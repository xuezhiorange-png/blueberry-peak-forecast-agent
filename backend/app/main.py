from fastapi import FastAPI

from backend.app.api.health import router as health_router
from backend.app.core.config import AppSettings, get_settings
from backend.app.core.version import APP_VERSION


def create_app(settings: AppSettings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(title=app_settings.app_name, version=APP_VERSION)
    app.state.settings = app_settings

    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: app_settings

    app.include_router(health_router, prefix="/health", tags=["health"])
    return app


app = create_app()
