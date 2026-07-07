from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.harvest_state.application import (
    HarvestStateDeliveryConflictError,
    HarvestStateDeliveryError,
    HarvestStateDeliveryInputError,
    HarvestStateDeliveryIntegrityError,
    HarvestStateRunNotFoundError,
    execute_harvest_state_run,
    get_harvest_state_run_by_id,
    get_harvest_state_run_by_result_hash,
)
from backend.app.harvest_state.reports import (
    render_harvest_state_csv_report,
    render_harvest_state_json_report,
)
from backend.app.harvest_state.schemas import Task9ARequest
from backend.app.schemas.harvest_state import HarvestStateErrorResponse, HarvestStateRunEnvelope

router = APIRouter()
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
HashPath = Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")]
_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": HarvestStateErrorResponse},
    409: {"model": HarvestStateErrorResponse},
    422: {"model": HarvestStateErrorResponse},
    500: {"model": HarvestStateErrorResponse},
}


def _error_response(
    *,
    code: str,
    message: str,
    status_code: int,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=HarvestStateErrorResponse(error={"code": code, "message": message}).model_dump(
            mode="json"
        ),
    )


def _map_error(exc: HarvestStateDeliveryError) -> JSONResponse:
    if isinstance(exc, HarvestStateDeliveryInputError):
        return _error_response(code=exc.code, message=exc.message, status_code=422)
    if isinstance(exc, HarvestStateRunNotFoundError):
        return _error_response(code=exc.code, message=exc.message, status_code=404)
    if isinstance(exc, HarvestStateDeliveryConflictError):
        return _error_response(code=exc.code, message=exc.message, status_code=409)
    if isinstance(exc, HarvestStateDeliveryIntegrityError):
        return _error_response(code=exc.code, message=exc.message, status_code=500)
    return _error_response(code=exc.code, message=exc.message, status_code=500)


@router.post(
    "/runs",
    response_model=HarvestStateRunEnvelope,
    operation_id="createHarvestStateRun",
    responses=_ERROR_RESPONSES,
)
async def create_harvest_state_run(
    payload: Task9ARequest,
    session: SessionDep,
) -> HarvestStateRunEnvelope | JSONResponse:
    try:
        return await execute_harvest_state_run(session, request=payload)
    except HarvestStateDeliveryError as exc:
        return _map_error(exc)


@router.get(
    "/runs/{run_id}",
    response_model=HarvestStateRunEnvelope,
    operation_id="getHarvestStateRunById",
    responses=_ERROR_RESPONSES,
)
async def read_harvest_state_run(
    run_id: int,
    session: SessionDep,
) -> HarvestStateRunEnvelope | JSONResponse:
    try:
        return await get_harvest_state_run_by_id(session, run_id=run_id)
    except HarvestStateDeliveryError as exc:
        return _map_error(exc)


@router.get(
    "/runs/by-result-hash/{result_hash}",
    response_model=HarvestStateRunEnvelope,
    operation_id="getHarvestStateRunByResultHash",
    responses=_ERROR_RESPONSES,
)
async def read_harvest_state_run_by_hash(
    result_hash: HashPath,
    session: SessionDep,
) -> HarvestStateRunEnvelope | JSONResponse:
    try:
        return await get_harvest_state_run_by_result_hash(session, result_hash=result_hash)
    except HarvestStateDeliveryError as exc:
        return _map_error(exc)


@router.get(
    "/runs/{run_id}/report.json",
    operation_id="downloadHarvestStateJsonReport",
    response_class=Response,
    responses={
        200: {"content": {"application/json": {}}},
        **_ERROR_RESPONSES,
    },
)
async def download_harvest_state_json_report(
    run_id: int,
    session: SessionDep,
) -> Response:
    try:
        envelope = await get_harvest_state_run_by_id(session, run_id=run_id)
    except HarvestStateDeliveryError as exc:
        return _map_error(exc)
    return Response(
        content=render_harvest_state_json_report(
            run_id=envelope.run_id,
            created_at=envelope.created_at,
            output=envelope.output,
        ),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="harvest-state-run-{run_id}.json"'},
    )


@router.get(
    "/runs/{run_id}/report.csv",
    operation_id="downloadHarvestStateCsvReport",
    response_class=Response,
    responses={
        200: {"content": {"application/zip": {}}},
        **_ERROR_RESPONSES,
    },
)
async def download_harvest_state_csv_report(
    run_id: int,
    session: SessionDep,
) -> Response:
    try:
        envelope = await get_harvest_state_run_by_id(session, run_id=run_id)
    except HarvestStateDeliveryError as exc:
        return _map_error(exc)
    return Response(
        content=render_harvest_state_csv_report(
            run_id=envelope.run_id,
            created_at=envelope.created_at,
            output=envelope.output,
        ),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="harvest-state-run-{run_id}.zip"'},
    )
