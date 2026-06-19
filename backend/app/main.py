from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.health import router as health_router
from backend.app.core.config import AppSettings, get_settings
from backend.app.core.version import APP_VERSION
from backend.app.db import session as db_session


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await db_session.dispose_db_engine()


def create_app(settings: AppSettings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(title=app_settings.app_name, version=APP_VERSION, lifespan=lifespan)
    app.state.settings = app_settings

    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: app_settings

    app.include_router(health_router, prefix="/health", tags=["health"])
    return app


app = create_app()
