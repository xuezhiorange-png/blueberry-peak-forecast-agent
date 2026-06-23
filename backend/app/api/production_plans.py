from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.planning.plan_config import ProductionPlanConfig, load_production_plan_config
from backend.app.planning.plan_schemas import (
    ProductionPlanIntervalConflictError,
    ProductionPlanNotFoundError,
    ProductionPlanUnavailableError,
    ProductionPlanValidationError,
    ProductionPlanVersionConflictError,
)
from backend.app.planning.plan_service import (
    _canonical_payload,
    create_plan_version,
    create_replacement_version,
    get_effective_plan,
    get_plan_version,
    list_plan_versions,
)
from backend.app.schemas.production_plans import (
    ProductionPlanCreate,
    ProductionPlanList,
    ProductionPlanRead,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def _config_path() -> Path:
    return Path("configs/production_plan.yaml")


def _load_config() -> ProductionPlanConfig:
    return load_production_plan_config(_config_path())


def _to_response(payload: dict[str, object]) -> ProductionPlanRead:
    return ProductionPlanRead.model_validate(payload)


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProductionPlanValidationError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, (ProductionPlanVersionConflictError, ProductionPlanIntervalConflictError)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, (ProductionPlanNotFoundError, ProductionPlanUnavailableError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal error")


@router.post(
    "/production-plans",
    response_model=ProductionPlanRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_plan(
    payload: ProductionPlanCreate,
    response: Response,
    session: SessionDep,
) -> ProductionPlanRead:
    try:
        result = await create_plan_version(
            session,
            payload=payload.model_dump(mode="python"),
            config=_load_config(),
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return _to_response(_canonical_payload(result.record))


@router.get("/production-plans/history", response_model=ProductionPlanList)
async def get_plan_history(
    session: SessionDep,
    farm_id: int = Query(),
    season_id: int = Query(),
    variety_id: int = Query(),
    subfarm_id: int | None = Query(default=None),
) -> ProductionPlanList:
    records = await list_plan_versions(
        session,
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        season_id=season_id,
        variety_id=variety_id,
        config=_load_config(),
    )
    items = [_to_response(_canonical_payload(record)) for record in records]
    return ProductionPlanList(items=items, total=len(items))


@router.get("/production-plans/effective", response_model=ProductionPlanRead)
async def get_effective(
    session: SessionDep,
    as_of_date: Annotated[date, Query()],
    farm_id: int = Query(),
    season_id: int = Query(),
    variety_id: int = Query(),
    subfarm_id: int | None = Query(default=None),
) -> ProductionPlanRead:
    try:
        record = await get_effective_plan(
            session,
            farm_id=farm_id,
            subfarm_id=subfarm_id,
            season_id=season_id,
            variety_id=variety_id,
            as_of_date=as_of_date,
            config=_load_config(),
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    return _to_response(_canonical_payload(record))


@router.get("/production-plans/{plan_id}", response_model=ProductionPlanRead)
async def get_plan(plan_id: int, session: SessionDep) -> ProductionPlanRead:
    try:
        record = await get_plan_version(session, plan_id=plan_id, config=_load_config())
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    return _to_response(_canonical_payload(record))


@router.post("/production-plans/{plan_id}/replace", response_model=ProductionPlanRead)
async def replace_plan(
    plan_id: int,
    payload: ProductionPlanCreate,
    session: SessionDep,
) -> ProductionPlanRead:
    try:
        result = await create_replacement_version(
            session,
            plan_id=plan_id,
            payload=payload.model_dump(mode="python"),
            config=_load_config(),
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    return _to_response(_canonical_payload(result.record))
