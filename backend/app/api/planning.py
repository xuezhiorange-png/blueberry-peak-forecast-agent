from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.planning.config import (
    ParameterInferenceConfig,
    load_parameter_inference_config,
)
from backend.app.planning.schemas import ParameterInferenceExecutionResult
from backend.app.planning.service import (
    _result_payload,
    create_minimal_planning_task,
    load_minimal_planning_task_result,
)
from backend.app.schemas.planning import MinimalPlanningTaskCreate, PlanningTaskResponse

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def _config_path() -> Path:
    return Path("configs/parameter_inference.yaml")


def _load_config() -> ParameterInferenceConfig:
    return load_parameter_inference_config(_config_path())


def _response_payload(
    result: ParameterInferenceExecutionResult,
) -> PlanningTaskResponse:
    return PlanningTaskResponse.model_validate(_result_payload(result))


@router.post("/tasks", response_model=PlanningTaskResponse)
async def create_task(
    payload: MinimalPlanningTaskCreate,
    session: SessionDep,
) -> PlanningTaskResponse:
    try:
        result = await create_minimal_planning_task(
            session,
            payload=payload.model_dump(mode="json"),
            config=_load_config(),
            dry_run=False,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return _response_payload(result)


@router.get("/tasks/{task_id}", response_model=PlanningTaskResponse)
async def get_task(task_id: int, session: SessionDep) -> PlanningTaskResponse:
    try:
        result = await load_minimal_planning_task_result(
            session,
            task_id=task_id,
            config=_load_config(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _response_payload(result)
