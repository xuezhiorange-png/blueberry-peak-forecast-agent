from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.actual_harvest_import.api_errors import ActualHarvestApiError
from backend.app.actual_harvest_import.api_schemas import (
    ActualHarvestApiAppendRecordsRequest,
    ActualHarvestApiCreateImportRequest,
    ActualHarvestApiRecordInput,
)
from backend.app.actual_harvest_import.lifecycle import (
    append_import_records,
    cancel_import,
    create_import,
    preview_import,
    seal_import,
)
from backend.tests.actual_harvest_import.test_api_schemas import _create_payload, _record_payload


def _request() -> ActualHarvestApiCreateImportRequest:
    return ActualHarvestApiCreateImportRequest.model_validate(_create_payload())


def _record() -> ActualHarvestApiRecordInput:
    return ActualHarvestApiRecordInput.model_validate(_record_payload())


@pytest.mark.asyncio
async def test_lifecycle_is_atomic_and_sealed_records_are_immutable(
    sqlite_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime(2026, 7, 18, 8, tzinfo=UTC)
    async with sqlite_session_maker() as session:
        async with session.begin():
            batch, reused = await create_import(session, _request(), clock=lambda: now)
        assert batch.status == "UPLOADING"
        assert not reused
        async with session.begin():
            batch, records, reused = await append_import_records(
                session,
                batch.import_id,
                ActualHarvestApiAppendRecordsRequest(records=(_record(),)),
                clock=lambda: now,
            )
        assert batch.record_count == 1
        assert len(records) == 1
        assert not reused
        async with session.begin():
            sealed = await seal_import(
                session,
                batch.import_id,
                actor_identity="operator-1",
                clock=lambda: now,
            )
        assert sealed.status == "SEALED"
        assert sealed.canonical_batch_hash_or_null is not None
        assert sealed.seal_manifest_hash_or_null is not None
        await session.rollback()
        summary, page, token = await preview_import(
            session,
            batch.import_id,
            page_size=50,
            page_token=None,
        )
        assert summary.status == "SEALED"
        assert len(page) == 1
        assert token is None
        await session.rollback()
        with pytest.raises(ActualHarvestApiError) as exc_info:
            async with session.begin():
                await append_import_records(
                    session,
                    batch.import_id,
                    ActualHarvestApiAppendRecordsRequest(records=(_record(),)),
                    clock=lambda: now,
                )
        assert exc_info.value.code.value == "BATCH_MUTATION_AFTER_SEAL"


@pytest.mark.asyncio
async def test_cancel_preserves_seal_evidence_and_repeated_cancel_is_idempotent(
    sqlite_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime(2026, 7, 18, 8, tzinfo=UTC)
    async with sqlite_session_maker() as session:
        async with session.begin():
            batch, _ = await create_import(session, _request(), clock=lambda: now)
        async with session.begin():
            batch, _, _ = await append_import_records(
                session,
                batch.import_id,
                ActualHarvestApiAppendRecordsRequest(records=(_record(),)),
                clock=lambda: now,
            )
        async with session.begin():
            batch = await seal_import(
                session,
                batch.import_id,
                actor_identity="operator-1",
                clock=lambda: now,
            )
        await session.rollback()
        async with session.begin():
            cancelled = await cancel_import(session, batch.import_id, clock=lambda: now)
        assert cancelled.status == "CANCELLED"
        assert cancelled.seal_manifest_hash_or_null == batch.seal_manifest_hash_or_null
        async with session.begin():
            repeated = await cancel_import(session, batch.import_id, clock=lambda: now)
        assert repeated.status == "CANCELLED"


@pytest.mark.asyncio
async def test_revision_identity_from_another_batch_is_not_replayed(
    sqlite_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime(2026, 7, 18, 8, tzinfo=UTC)
    first_request = _request()
    second_payload = _create_payload()
    second_payload.update(
        external_batch_id="batch-2",
        idempotency_key="key-2",
    )
    second_request = ActualHarvestApiCreateImportRequest.model_validate(second_payload)
    first_record = _record()
    second_record_payload = _record_payload()
    second_record_payload["external_batch_id"] = "batch-2"
    second_record = ActualHarvestApiRecordInput.model_validate(second_record_payload)

    async with sqlite_session_maker() as session:
        async with session.begin():
            first_batch, _ = await create_import(session, first_request, clock=lambda: now)
            await append_import_records(
                session,
                first_batch.import_id,
                ActualHarvestApiAppendRecordsRequest(records=(first_record,)),
                clock=lambda: now,
            )
        async with session.begin():
            second_batch, _ = await create_import(session, second_request, clock=lambda: now)
            with pytest.raises(ActualHarvestApiError) as exc_info:
                await append_import_records(
                    session,
                    second_batch.import_id,
                    ActualHarvestApiAppendRecordsRequest(records=(second_record,)),
                    clock=lambda: now,
                )
        assert exc_info.value.code.value == "REVISION_IDENTITY_CONFLICT"
        async with session.begin():
            second_summary, second_page, _ = await preview_import(
                session,
                second_batch.import_id,
                page_size=50,
                page_token=None,
            )
        assert second_summary.record_count == 0
        assert second_page == ()


@pytest.mark.asyncio
async def test_repeated_seal_by_different_actor_is_a_conflict(
    sqlite_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime(2026, 7, 18, 8, tzinfo=UTC)
    async with sqlite_session_maker() as session:
        async with session.begin():
            batch, _ = await create_import(session, _request(), clock=lambda: now)
            await append_import_records(
                session,
                batch.import_id,
                ActualHarvestApiAppendRecordsRequest(records=(_record(),)),
                clock=lambda: now,
            )
        async with session.begin():
            await seal_import(
                session,
                batch.import_id,
                actor_identity="operator-1",
                clock=lambda: now,
            )
        with pytest.raises(ActualHarvestApiError) as exc_info:
            async with session.begin():
                await seal_import(
                    session,
                    batch.import_id,
                    actor_identity="operator-2",
                    clock=lambda: now,
                )
        assert exc_info.value.code.value == "BATCH_SEAL_HASH_CONFLICT"
