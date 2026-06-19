from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import AppSettings, get_settings
from backend.app.core.version import APP_VERSION
from backend.app.db.session import get_db_session
from backend.app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/live", response_model=HealthResponse)
async def health_live(settings: Annotated[AppSettings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(status="live", service=settings.app_name, version=APP_VERSION)


@router.get("/ready", response_model=HealthResponse)
async def health_ready(
    settings: Annotated[AppSettings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> HealthResponse:
    try:
        result = await session.execute(text("SELECT 1"))
        if result.scalar_one() != 1:
            raise RuntimeError("database readiness query returned an unexpected result")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database is not ready",
        ) from exc

    return HealthResponse(status="ready", service=settings.app_name, version=APP_VERSION)
