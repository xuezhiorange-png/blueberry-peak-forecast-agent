from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_import.api_auth import (
    ActorDep,
    ActualHarvestActorContext,
    require_actor_scope,
)
from backend.app.actual_harvest_import.api_errors import (
    ActualHarvestApiError,
    ActualHarvestApiErrorCode,
)
from backend.app.actual_harvest_import.api_schemas import (
    ActualHarvestApiAppendRecordsRequest,
    ActualHarvestApiBatchSummary,
    ActualHarvestApiCancelRequest,
    ActualHarvestApiCreateImportRequest,
    ActualHarvestApiEnvelope,
    ActualHarvestApiSealRequest,
)
from backend.app.actual_harvest_import.enums import ActualHarvestImportChannel
from backend.app.actual_harvest_import.lifecycle import (
    append_import_records,
    cancel_import,
    create_import,
    get_import,
    preview_import,
    seal_import,
)
from backend.app.db.session import get_db_session

router = APIRouter()
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def _request_id(request: Request) -> str:
    candidate = request.headers.get("x-request-id")
    if candidate and len(candidate) <= 128 and candidate.isascii() and candidate.isprintable():
        return candidate
    return uuid4().hex


def _ok(
    request_id: str,
    data: object,
    *,
    status_code: int = 200,
    pagination: object | None = None,
    hashes: dict[str, str] | None = None,
) -> JSONResponse:
    envelope = ActualHarvestApiEnvelope(
        request_id=request_id,
        status="OK",
        data_or_null=data,
        pagination_or_null=pagination,
        canonical_hashes=hashes or {},
        provenance={"api_policy_version": "actual-harvest-api-policy-v1"},
    )
    return JSONResponse(status_code=status_code, content=envelope.model_dump(mode="json"))


def _error(request_id: str, error: ActualHarvestApiError) -> JSONResponse:
    envelope = ActualHarvestApiEnvelope(
        request_id=request_id,
        status="ERROR",
        data_or_null=None,
        errors=(
            {
                "code": error.code.value,
                "message_template_id": error.code.value,
                "details": error.details,
            },
        ),
        provenance={"api_policy_version": "actual-harvest-api-policy-v1"},
    )
    return JSONResponse(status_code=error.status_code, content=envelope.model_dump(mode="json"))


async def _run_mutation[ResultT](
    session: AsyncSession,
    operation: Callable[[], Awaitable[ResultT]],
) -> ResultT:
    if session.in_transaction():
        try:
            result = await operation()
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise
    async with session.begin():
        return await operation()


async def _load_scoped_batch(
    session: AsyncSession,
    import_id: str,
    actor: ActualHarvestActorContext,
    permission: str,
) -> ActualHarvestApiBatchSummary:
    batch = await get_import(session, import_id)
    if (
        batch.source_system not in actor.allowed_source_systems
        or ActualHarvestImportChannel.API not in actor.allowed_channels
    ):
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_FOUND,
            "actual-harvest import batch was not found",
            status_code=404,
        )
    require_actor_scope(
        actor,
        source_system=batch.source_system,
        channel=ActualHarvestImportChannel.API,
        permission=permission,
        submitted_by_identity=batch.submitted_by_identity,
        hide_identity_mismatch=True,
    )
    return batch


@router.post(
    "/imports",
    operation_id="createActualHarvestImport",
    response_model=None,
)
async def create_actual_harvest_import(
    request: Request,
    body: ActualHarvestApiCreateImportRequest,
    actor: ActorDep,
    session: SessionDep,
) -> JSONResponse:
    request_id = _request_id(request)
    try:
        require_actor_scope(
            actor,
            source_system=body.source_system,
            channel=body.import_channel,
            permission="may_create",
            submitted_by_identity=body.submitted_by_identity,
        )
        summary, reused = await _run_mutation(
            session,
            lambda: create_import(session, body),
        )
        return _ok(
            request_id,
            {"batch": summary, "reused_existing_import": reused},
            status_code=200 if reused else 201,
        )
    except ActualHarvestApiError as error:
        return _error(request_id, error)


@router.post(
    "/imports/{import_id}/records",
    operation_id="appendActualHarvestImportRecords",
    response_model=None,
)
async def append_actual_harvest_import_records(
    import_id: str,
    request: Request,
    body: ActualHarvestApiAppendRecordsRequest,
    actor: ActorDep,
    session: SessionDep,
) -> JSONResponse:
    request_id = _request_id(request)
    try:
        await _load_scoped_batch(session, import_id, actor, "may_append")
        summary, records, reused = await _run_mutation(
            session,
            lambda: append_import_records(session, import_id, body),
        )
        del records
        return _ok(
            request_id,
            {
                "batch": summary,
                "reused_existing_page": reused,
            },
        )
    except ActualHarvestApiError as error:
        return _error(request_id, error)


@router.get(
    "/imports/{import_id}",
    operation_id="getActualHarvestImport",
    response_model=None,
)
async def get_actual_harvest_import(
    import_id: str,
    request: Request,
    actor: ActorDep,
    session: SessionDep,
) -> JSONResponse:
    request_id = _request_id(request)
    try:
        batch = await _load_scoped_batch(session, import_id, actor, "may_preview")
        return _ok(request_id, {"batch": batch})
    except ActualHarvestApiError as error:
        return _error(request_id, error)


@router.get(
    "/imports/{import_id}/preview",
    operation_id="previewActualHarvestImport",
    response_model=None,
)
async def preview_actual_harvest_import(
    import_id: str,
    request: Request,
    actor: ActorDep,
    session: SessionDep,
    page_size: int = Query(default=50),
    page_token: str | None = Query(default=None, max_length=2048),
) -> JSONResponse:
    request_id = _request_id(request)
    try:
        batch = await _load_scoped_batch(session, import_id, actor, "may_preview")
        summary, records, next_token = await preview_import(
            session,
            import_id,
            page_size=page_size,
            page_token=page_token,
        )
        del batch
        return _ok(
            request_id,
            {
                "batch": summary,
                "records": records,
                "validation_status": "NOT_RUN",
                "active_label_created": False,
            },
            pagination={"page_size": page_size, "next_page_token": next_token},
        )
    except ActualHarvestApiError as error:
        return _error(request_id, error)


@router.post(
    "/imports/{import_id}/seal",
    operation_id="sealActualHarvestImport",
    response_model=None,
)
async def seal_actual_harvest_import(
    import_id: str,
    request: Request,
    body: ActualHarvestApiSealRequest,
    actor: ActorDep,
    session: SessionDep,
) -> JSONResponse:
    request_id = _request_id(request)
    try:
        del body
        batch = await _load_scoped_batch(session, import_id, actor, "may_seal")
        summary = await _run_mutation(
            session,
            lambda: seal_import(session, import_id, actor_identity=actor.identity),
        )
        del batch
        return _ok(request_id, {"batch": summary})
    except ActualHarvestApiError as error:
        return _error(request_id, error)


@router.post(
    "/imports/{import_id}/cancel",
    operation_id="cancelActualHarvestImport",
    response_model=None,
)
async def cancel_actual_harvest_import(
    import_id: str,
    request: Request,
    body: ActualHarvestApiCancelRequest,
    actor: ActorDep,
    session: SessionDep,
) -> JSONResponse:
    request_id = _request_id(request)
    try:
        del body
        batch = await _load_scoped_batch(session, import_id, actor, "may_cancel")
        summary = await _run_mutation(
            session,
            lambda: cancel_import(session, import_id),
        )
        del batch
        return _ok(request_id, {"batch": summary})
    except ActualHarvestApiError as error:
        return _error(request_id, error)


__all__ = ["router"]
