from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import delete

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
    seal_import,
)
from backend.app.actual_harvest_import.models import (
    ActualHarvestImportBatchModel,
    ActualHarvestImportRecordModel,
)
from backend.app.actual_harvest_import.schemas import ActualHarvestImportRecordInput
from backend.app.db.session import AsyncSessionMaker
from backend.tests.actual_harvest_import.test_api_schemas import (
    _create_payload,
    _record_payload,
)
from backend.tests.db.profile import assert_safe_postgres_test_identity

pytestmark = [pytest.mark.postgres, pytest.mark.integration]


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")
    assert_safe_postgres_test_identity(env=None)


async def _create_once(payload: dict[str, object]) -> str:
    request = ActualHarvestApiCreateImportRequest.model_validate(payload)
    async with AsyncSessionMaker() as session:
        async with session.begin():
            batch, _ = await create_import(session, request)
            return batch.import_id


async def _seed_batch(*, expected_record_count: int | None) -> tuple[str, str]:
    suffix = uuid4().hex
    payload = _create_payload()
    payload["external_batch_id"] = f"i4-pg-lifecycle-{suffix}"
    payload["idempotency_key"] = f"i4-pg-lifecycle-{suffix}"
    payload["expected_record_count_or_null"] = expected_record_count
    request = ActualHarvestApiCreateImportRequest.model_validate(payload)
    async with AsyncSessionMaker() as session:
        async with session.begin():
            batch, reused = await create_import(session, request)
            assert not reused
    return batch.import_id, request.external_batch_id


def _record_for_batch(external_batch_id: str) -> ActualHarvestApiRecordInput:
    payload = _record_payload()
    payload["external_batch_id"] = external_batch_id
    payload["external_logical_record_id"] = f"logical-{uuid4().hex}"
    payload["external_revision_id"] = f"revision-{uuid4().hex}"
    return ActualHarvestApiRecordInput.model_validate(payload)


async def _cleanup_batch(external_batch_id: str) -> None:
    async with AsyncSessionMaker() as session:
        async with session.begin():
            batch_id = await session.scalar(
                sa.select(ActualHarvestImportBatchModel.id).where(
                    ActualHarvestImportBatchModel.external_batch_id == external_batch_id
                )
            )
            if batch_id is None:
                return
            await session.execute(
                delete(ActualHarvestImportRecordModel).where(
                    ActualHarvestImportRecordModel.batch_id == batch_id
                )
            )
            await session.execute(
                delete(ActualHarvestImportBatchModel).where(
                    ActualHarvestImportBatchModel.id == batch_id
                )
            )


async def _batch_state(
    external_batch_id: str,
) -> tuple[ActualHarvestImportBatchModel, int]:
    async with AsyncSessionMaker() as session:
        batch = await session.scalar(
            sa.select(ActualHarvestImportBatchModel).where(
                ActualHarvestImportBatchModel.external_batch_id == external_batch_id
            )
        )
        assert batch is not None
        record_count = await session.scalar(
            sa.select(sa.func.count())
            .select_from(ActualHarvestImportRecordModel)
            .where(ActualHarvestImportRecordModel.batch_id == batch.id)
        )
        return batch, int(record_count or 0)


async def _record_canonical_state(
    external_batch_id: str,
) -> tuple[tuple[str, object], ...]:
    async with AsyncSessionMaker() as session:
        record = await session.scalar(
            sa.select(ActualHarvestImportRecordModel)
            .where(ActualHarvestImportRecordModel.external_batch_id == external_batch_id)
            .order_by(ActualHarvestImportRecordModel.id)
        )
        assert record is not None
        canonical_fields = tuple(
            field_name
            for field_name in ActualHarvestImportRecordInput.model_fields
            if field_name not in {"source_row_number", "source_sheet_name"}
        )
        canonical_record = ActualHarvestImportRecordInput.model_validate(
            {field_name: getattr(record, field_name) for field_name in canonical_fields}
        )
        return tuple(canonical_record.model_dump(mode="json").items())


async def _race_two(first, second):
    start = asyncio.Event()
    ready = (asyncio.Event(), asyncio.Event())

    async def run(operation, ready_event):
        ready_event.set()
        await start.wait()
        return await operation()

    tasks = (
        asyncio.create_task(run(first, ready[0])),
        asyncio.create_task(run(second, ready[1])),
    )
    await asyncio.gather(*(event.wait() for event in ready))
    start.set()
    return await asyncio.gather(*tasks)


async def _append_once(import_id: str, record: ActualHarvestApiRecordInput):
    try:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                batch, _, reused = await append_import_records(
                    session,
                    import_id,
                    ActualHarvestApiAppendRecordsRequest(records=(record,)),
                )
                return ("ok", batch, reused)
    except ActualHarvestApiError as exc:
        return ("error", exc.code.value, False)


async def _seal_once(import_id: str):
    try:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                batch = await seal_import(session, import_id, actor_identity="operator-1")
                return ("ok", batch)
    except ActualHarvestApiError as exc:
        return ("error", exc.code.value)


async def _cancel_once(import_id: str):
    try:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                batch = await cancel_import(session, import_id)
                return ("ok", batch)
    except ActualHarvestApiError as exc:
        return ("error", exc.code.value)


@pytest.mark.asyncio
async def test_postgres_i4_concurrent_identical_create_has_one_batch() -> None:
    _require_postgres()
    payload = _create_payload()
    suffix = uuid4().hex
    payload["external_batch_id"] = f"i4-pg-{suffix}"
    payload["idempotency_key"] = f"i4-pg-{suffix}"
    external_batch_id = payload["external_batch_id"]
    try:
        first_id, second_id = await asyncio.gather(
            _create_once(payload.copy()),
            _create_once(payload.copy()),
        )
        assert first_id == second_id
        async with AsyncSessionMaker() as session:
            count = await session.scalar(
                sa.select(sa.func.count())
                .select_from(ActualHarvestImportBatchModel)
                .where(ActualHarvestImportBatchModel.external_batch_id == external_batch_id)
            )
            assert count == 1
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_postgres_i4_concurrent_identical_append_has_one_page_and_counts_once() -> None:
    _require_postgres()
    import_id, external_batch_id = await _seed_batch(expected_record_count=1)
    record = _record_for_batch(external_batch_id)
    try:
        first, second = await _race_two(
            lambda: _append_once(import_id, record),
            lambda: _append_once(import_id, record),
        )
        assert {first[0], second[0]} == {"ok"}
        assert {first[2], second[2]} == {False, True}
        batch, persisted_count = await _batch_state(external_batch_id)
        assert persisted_count == 1
        assert batch.record_count == 1
        assert batch.uploaded_record_count == 1
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_postgres_i4_append_vs_seal_is_serialized() -> None:
    _require_postgres()
    import_id, external_batch_id = await _seed_batch(expected_record_count=None)
    record = _record_for_batch(external_batch_id)
    try:
        append_result, seal_result = await _race_two(
            lambda: _append_once(import_id, record),
            lambda: _seal_once(import_id),
        )
        assert seal_result[0] == "ok"
        batch, persisted_count = await _batch_state(external_batch_id)
        assert batch.status == "SEALED"
        assert batch.record_count == persisted_count
        assert batch.uploaded_record_count == persisted_count
        if append_result[0] == "ok":
            assert append_result[1].record_count == 1
            assert seal_result[1].sealed_record_count_or_null == 1
            assert persisted_count == 1
        else:
            assert append_result[1] == "BATCH_MUTATION_AFTER_SEAL"
            assert seal_result[1].sealed_record_count_or_null == 0
            assert persisted_count == 0
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_postgres_i4_append_vs_cancel_is_serialized() -> None:
    _require_postgres()
    import_id, external_batch_id = await _seed_batch(expected_record_count=None)
    record = _record_for_batch(external_batch_id)
    try:
        append_result, cancel_result = await _race_two(
            lambda: _append_once(import_id, record),
            lambda: _cancel_once(import_id),
        )
        assert cancel_result[0] == "ok"
        batch, persisted_count = await _batch_state(external_batch_id)
        assert batch.status == "CANCELLED"
        assert batch.record_count == persisted_count
        assert batch.uploaded_record_count == persisted_count
        if append_result[0] == "ok":
            assert persisted_count == 1
        else:
            assert append_result[1] == "IMPORT_BATCH_CANCELLED"
            assert persisted_count == 0
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_postgres_i4_seal_vs_cancel_preserves_records_and_seal_evidence() -> None:
    _require_postgres()
    import_id, external_batch_id = await _seed_batch(expected_record_count=None)
    record = _record_for_batch(external_batch_id)
    try:
        append_result = await _append_once(import_id, record)
        assert append_result[0] == "ok"
        assert append_result[2] is False
        before_record = await _record_canonical_state(external_batch_id)
        before_batch, before_record_count = await _batch_state(external_batch_id)
        before_counts = (
            before_batch.record_count,
            before_batch.uploaded_record_count,
        )
        assert before_record_count == 1
        assert before_counts == (1, 1)

        seal_result, cancel_result = await _race_two(
            lambda: _seal_once(import_id),
            lambda: _cancel_once(import_id),
        )
        assert cancel_result[0] == "ok"
        batch, persisted_count = await _batch_state(external_batch_id)
        assert batch.status == "CANCELLED"
        assert persisted_count == batch.record_count == batch.uploaded_record_count == 1
        assert (batch.record_count, batch.uploaded_record_count) == before_counts
        assert await _record_canonical_state(external_batch_id) == before_record
        if seal_result[0] == "ok":
            sealed = seal_result[1]
            assert batch.sealed_record_count_or_null == sealed.sealed_record_count_or_null == 1
            assert batch.server_raw_payload_hash_or_null == sealed.server_raw_payload_hash_or_null
            assert batch.canonical_batch_hash_or_null == sealed.canonical_batch_hash_or_null
            assert batch.seal_manifest_hash_or_null == sealed.seal_manifest_hash_or_null
            assert batch.sealed_at_or_null == sealed.sealed_at_or_null
            assert batch.sealed_by_identity_or_null == sealed.sealed_by_identity_or_null
        else:
            assert seal_result[1] == "IMPORT_BATCH_CANCELLED"
            assert batch.sealed_record_count_or_null is None
            assert batch.server_raw_payload_hash_or_null is None
            assert batch.canonical_batch_hash_or_null is None
            assert batch.seal_manifest_hash_or_null is None
            assert batch.sealed_at_or_null is None
            assert batch.sealed_by_identity_or_null is None
    finally:
        await _cleanup_batch(external_batch_id)
