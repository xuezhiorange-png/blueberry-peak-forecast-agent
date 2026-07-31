from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_import.api_errors import (
    ActualHarvestApiError,
    ActualHarvestApiErrorCode,
)
from backend.app.actual_harvest_import.api_policy import API_POLICY
from backend.app.actual_harvest_import.api_schemas import (
    ActualHarvestApiAppendRecordsRequest,
    ActualHarvestApiBatchSummary,
    ActualHarvestApiCreateImportRequest,
    ActualHarvestApiRecordOutput,
)
from backend.app.actual_harvest_import.canonical_hashes import (
    API_TRANSPORT_HASH_POLICY_VERSION,
    CANONICAL_BATCH_HASH_POLICY_VERSION,
    SEAL_MANIFEST_POLICY_VERSION,
)
from backend.app.actual_harvest_import.lifecycle_persistence import (
    append_records as persist_append_records,
)
from backend.app.actual_harvest_import.lifecycle_persistence import (
    cancel_batch as persist_cancel_batch,
)
from backend.app.actual_harvest_import.lifecycle_persistence import (
    create_batch as persist_create_batch,
)
from backend.app.actual_harvest_import.lifecycle_persistence import (
    get_batch as persist_get_batch,
)
from backend.app.actual_harvest_import.lifecycle_persistence import (
    list_records_page as persist_list_records_page,
)
from backend.app.actual_harvest_import.lifecycle_persistence import (
    seal_batch as persist_seal_batch,
)
from backend.app.actual_harvest_import.schemas import (
    CanonicalActualHarvestImportBatch,
    CanonicalActualHarvestImportRecord,
)
from backend.app.actual_harvest_import.validation_service import (
    current_validation_summary,
    decode_error_page_token,
    encode_error_page_token,
    list_validation_errors,
)
from backend.app.actual_harvest_import.validation_service import (
    validate_import as run_validation,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _summary(batch: CanonicalActualHarvestImportBatch) -> ActualHarvestApiBatchSummary:
    return ActualHarvestApiBatchSummary(
        import_id=batch.import_id,
        status=batch.status.value,
        import_channel=batch.import_channel.value,
        source_system=batch.source_system,
        source_dataset=batch.source_dataset,
        source_version=batch.source_version,
        external_batch_id=batch.external_batch_id,
        idempotency_key=batch.idempotency_key,
        submitted_by_identity=batch.submitted_by_identity,
        expected_record_count_or_null=batch.expected_record_count_or_null,
        uploaded_record_count=batch.uploaded_record_count,
        record_count=batch.record_count,
        valid_record_count=batch.valid_record_count,
        invalid_record_count=batch.invalid_record_count,
        committed_record_count=batch.committed_record_count,
        seal_status=batch.seal_status.value,
        sealed_record_count_or_null=batch.sealed_record_count_or_null,
        sealed_at_or_null=batch.sealed_at_or_null,
        sealed_by_identity_or_null=batch.sealed_by_identity_or_null,
        server_raw_payload_hash_or_null=batch.server_raw_payload_hash_or_null,
        canonical_batch_hash_or_null=batch.canonical_batch_hash_or_null,
        seal_manifest_hash_or_null=batch.seal_manifest_hash_or_null,
        created_at=batch.created_at,
    )


def _decode_token(token: str, import_id: str) -> tuple[str, str, int, str]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        if (
            payload.get("v") != 1
            or payload.get("import_id") != import_id
            or not isinstance(payload.get("last"), list)
            or len(payload["last"]) != 4
        ):
            raise ValueError
        source_system, logical_id, revision_number, revision_id = payload["last"]
        if not all(isinstance(value, str) for value in (source_system, logical_id, revision_id)):
            raise ValueError
        if not isinstance(revision_number, int):
            raise ValueError
        return source_system, logical_id, revision_number, revision_id
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.API_REQUEST_INVALID,
            "pagination token is invalid",
            status_code=400,
        ) from exc


def _encode_token(import_id: str, record: CanonicalActualHarvestImportRecord) -> str:
    payload = {
        "v": 1,
        "import_id": import_id,
        "last": [
            record.source_system,
            record.external_logical_record_id,
            record.revision_number,
            record.external_revision_id,
        ],
    }
    return base64.urlsafe_b64encode(canonical_json_dumps(payload).encode()).decode().rstrip("=")


def validate_page_size(page_size: int) -> None:
    if not 1 <= page_size <= API_POLICY.max_page_size:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.API_PAGE_SIZE_INVALID,
            "page size is outside the supported range",
            status_code=400,
        )


async def create_import(
    session: AsyncSession,
    request: ActualHarvestApiCreateImportRequest,
    *,
    clock: Clock = utc_now,
    replay_identity_hash: str | None = None,
) -> tuple[ActualHarvestApiBatchSummary, bool]:
    batch, reused = await session.run_sync(
        lambda sync_session: persist_create_batch(
            sync_session,
            request,
            import_id=uuid4().hex,
            now=clock(),
            replay_identity_hash=replay_identity_hash,
        )
    )
    return _summary(batch), reused


async def append_import_records(
    session: AsyncSession,
    import_id: str,
    request: ActualHarvestApiAppendRecordsRequest,
    *,
    clock: Clock = utc_now,
) -> tuple[ActualHarvestApiBatchSummary, tuple[ActualHarvestApiRecordOutput, ...], bool]:
    batch, records, reused = await session.run_sync(
        lambda sync_session: persist_append_records(
            sync_session,
            import_id=import_id,
            records=request.records,
            now=clock(),
        )
    )
    return (
        _summary(batch),
        tuple(
            ActualHarvestApiRecordOutput.model_validate(record.model_dump(mode="python"))
            for record in records
        ),
        reused,
    )


async def get_import(
    session: AsyncSession,
    import_id: str,
) -> ActualHarvestApiBatchSummary:
    batch = await session.run_sync(lambda sync_session: persist_get_batch(sync_session, import_id))
    if batch is None:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_FOUND,
            "actual-harvest import batch was not found",
            status_code=404,
        )
    return _summary(batch)


async def preview_import(
    session: AsyncSession,
    import_id: str,
    *,
    page_size: int,
    page_token: str | None,
) -> tuple[ActualHarvestApiBatchSummary, tuple[ActualHarvestApiRecordOutput, ...], str | None]:
    validate_page_size(page_size)
    after = None if page_token is None else _decode_token(page_token, import_id)
    batch, rows = await session.run_sync(
        lambda sync_session: (
            persist_get_batch(sync_session, import_id),
            persist_list_records_page(
                sync_session,
                import_id=import_id,
                page_size=page_size,
                after=after,
            ),
        )
    )
    if batch is None:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_FOUND,
            "actual-harvest import batch was not found",
            status_code=404,
        )
    has_next = len(rows) > page_size
    page = rows[:page_size]
    next_token = _encode_token(import_id, page[-1]) if has_next and page else None
    return (
        _summary(batch),
        tuple(
            ActualHarvestApiRecordOutput.model_validate(record.model_dump(mode="python"))
            for record in page
        ),
        next_token,
    )


async def seal_import(
    session: AsyncSession,
    import_id: str,
    *,
    actor_identity: str,
    clock: Clock = utc_now,
) -> ActualHarvestApiBatchSummary:
    batch = await session.run_sync(
        lambda sync_session: persist_seal_batch(
            sync_session,
            import_id=import_id,
            sealed_by_identity=actor_identity,
            now=clock(),
        )
    )
    return _summary(batch)


async def cancel_import(
    session: AsyncSession,
    import_id: str,
    *,
    clock: Clock = utc_now,
) -> ActualHarvestApiBatchSummary:
    batch = await session.run_sync(
        lambda sync_session: persist_cancel_batch(
            sync_session,
            import_id=import_id,
            now=clock(),
        )
    )
    return _summary(batch)


async def validate_import(
    session: AsyncSession,
    import_id: str,
    *,
    clock: Clock = utc_now,
) -> Any:
    return await run_validation(session, import_id=import_id, now=clock())


async def validation_summary(session: AsyncSession, import_id: str) -> Any:
    return await session.run_sync(
        lambda sync_session: current_validation_summary(sync_session, import_id)
    )


async def validation_errors(
    session: AsyncSession,
    import_id: str,
    *,
    page_size: int,
    page_token: str | None,
) -> tuple[Any, tuple[dict[str, Any], ...], str | None]:
    validate_page_size(page_size)

    def _list(sync_session: Any) -> tuple[Any, tuple[dict[str, Any], ...], str | None]:
        summary = current_validation_summary(sync_session, import_id)
        after = None
        if page_token is not None:
            if summary.validation_run_identity is None:
                raise ActualHarvestApiError(
                    ActualHarvestApiErrorCode.API_REQUEST_INVALID,
                    "error page token is invalid",
                    status_code=400,
                )
            after = decode_error_page_token(page_token, summary.validation_run_identity)
        summary, errors, last = list_validation_errors(
            sync_session,
            import_id=import_id,
            page_size=page_size,
            after_sort_key=after,
        )
        next_token = (
            encode_error_page_token(summary.validation_run_identity, last)
            if last is not None and summary.validation_run_identity is not None
            else None
        )
        return summary, errors, next_token

    return await session.run_sync(_list)


__all__ = [
    "API_TRANSPORT_HASH_POLICY_VERSION",
    "CANONICAL_BATCH_HASH_POLICY_VERSION",
    "SEAL_MANIFEST_POLICY_VERSION",
    "append_import_records",
    "cancel_import",
    "create_import",
    "get_import",
    "preview_import",
    "seal_import",
    "utc_now",
    "validate_import",
    "validation_errors",
    "validation_summary",
]
