from __future__ import annotations

import asyncio
import os
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

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
    validate_import,
    validation_errors,
)
from backend.app.actual_harvest_import.models import (
    ActualHarvestImportBatchModel,
    ActualHarvestImportRecordModel,
)
from backend.app.actual_harvest_import.schemas import ActualHarvestImportRecordInput
from backend.app.actual_harvest_import.validation_models import (
    ActualHarvestMappingPolicyRegistryModel,
    ActualHarvestMappingRegistryEntryModel,
    ActualHarvestMappingSnapshotModel,
    ActualHarvestValidationAttemptModel,
    ActualHarvestValidationErrorModel,
    ActualHarvestValidationLineageBasisMemberModel,
    ActualHarvestValidationLineageBasisModel,
    ActualHarvestValidationLineageEdgeModel,
    ActualHarvestValidationLineageNodeModel,
    ActualHarvestValidationMappingEvidenceModel,
    ActualHarvestValidationRecordModel,
    ActualHarvestValidationResultModel,
    ActualHarvestValidationRunModel,
)
from backend.app.actual_harvest_import.validation_service import (
    begin_validation,
    build_validation_evidence,
    create_mapping_registry,
    finalize_validation,
    renew_validation_attempt_lease,
    seal_mapping_registry,
)
from backend.app.db.session import AsyncSessionMaker
from backend.app.models.master_data import Farm, Season, Subfarm, Variety
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
    async def delete_validation_evidence(session, run_ids: list[int]) -> None:
        if not run_ids:
            return
        basis_ids = list(
            await session.scalars(
                sa.select(ActualHarvestValidationLineageBasisModel.id).where(
                    ActualHarvestValidationLineageBasisModel.validation_run_id.in_(run_ids)
                )
            )
        )
        await session.execute(
            delete(ActualHarvestValidationLineageBasisMemberModel).where(
                ActualHarvestValidationLineageBasisMemberModel.basis_id.in_(basis_ids)
            )
        )
        for model in (
            ActualHarvestMappingSnapshotModel,
            ActualHarvestValidationErrorModel,
            ActualHarvestValidationLineageEdgeModel,
            ActualHarvestValidationLineageNodeModel,
            ActualHarvestValidationRecordModel,
            ActualHarvestValidationMappingEvidenceModel,
            ActualHarvestValidationResultModel,
            ActualHarvestValidationAttemptModel,
        ):
            await session.execute(delete(model).where(model.validation_run_id.in_(run_ids)))
        await session.execute(
            delete(ActualHarvestValidationLineageBasisModel).where(
                ActualHarvestValidationLineageBasisModel.id.in_(basis_ids)
            )
        )

    batch_id: int | None
    async with AsyncSessionMaker() as session:
        async with session.begin():
            batch_id = await session.scalar(
                sa.select(ActualHarvestImportBatchModel.id).where(
                    ActualHarvestImportBatchModel.external_batch_id == external_batch_id
                )
            )
            if batch_id is None:
                return
            run_ids = list(
                await session.scalars(
                    sa.select(ActualHarvestValidationRunModel.id).where(
                        ActualHarvestValidationRunModel.batch_id == batch_id
                    )
                )
            )
            await delete_validation_evidence(session, run_ids)

    # Commit child-row cleanup separately, then re-read the parent rows in a
    # fresh transaction. This avoids a concurrent validation worker's final
    # evidence commit being hidden by the cleanup transaction snapshot.
    async with AsyncSessionMaker() as session:
        async with session.begin():
            batch_id = await session.scalar(
                sa.select(ActualHarvestImportBatchModel.id).where(
                    ActualHarvestImportBatchModel.external_batch_id == external_batch_id
                )
            )
            if batch_id is None:
                return
            run_ids = list(
                await session.scalars(
                    sa.select(ActualHarvestValidationRunModel.id).where(
                        ActualHarvestValidationRunModel.batch_id == batch_id
                    )
                )
            )
            await delete_validation_evidence(session, run_ids)
            await session.execute(
                delete(ActualHarvestValidationRunModel).where(
                    ActualHarvestValidationRunModel.id.in_(run_ids)
                )
            )
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


async def _seed_i5_registry(suffix: str, *, seal: bool = True) -> str:
    mapping_policy = f"mapping-i5-{suffix}"
    async with AsyncSessionMaker() as session:
        async with session.begin():
            await session.run_sync(
                lambda sync_session: _seed_i5_registry_sync(
                    sync_session,
                    suffix=suffix,
                    mapping_policy=mapping_policy,
                    seal=seal,
                )
            )
    return mapping_policy


async def _cleanup_registry(mapping_policy: str) -> None:
    async with AsyncSessionMaker() as session:
        async with session.begin():
            registry = await session.scalar(
                sa.select(ActualHarvestMappingPolicyRegistryModel).where(
                    ActualHarvestMappingPolicyRegistryModel.mapping_policy_version == mapping_policy
                )
            )
            if registry is None:
                return
            await session.execute(
                delete(ActualHarvestMappingRegistryEntryModel).where(
                    ActualHarvestMappingRegistryEntryModel.registry_id == registry.id
                )
            )
            await session.delete(registry)


def _seed_i5_registry_sync(
    sync_session, *, suffix: str, mapping_policy: str, seal: bool = True
) -> None:
    farm = Farm(name=f"farm-master-{suffix}")
    sync_session.add_all(
        [
            Season(
                code=f"season-{suffix}",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
            ),
            farm,
            Variety(code=f"variety-master-{suffix}", name=f"Variety Master {suffix}"),
        ]
    )
    sync_session.flush()
    sync_session.add(Subfarm(farm_id=farm.id, name=f"subfarm-master-{suffix}"))
    create_mapping_registry(
        sync_session,
        registry_version=f"registry-{suffix}",
        source_system="farm-system",
        mapping_policy_version=mapping_policy,
        entries=(
            {
                "source_field": "season_code",
                "source_code": "2026",
                "target_type": "SEASON",
                "target_business_key": f"season-{suffix}",
            },
            {
                "source_field": "farm_code",
                "source_code": "farm-1",
                "target_type": "FARM",
                "target_business_key": f"farm-master-{suffix}",
            },
            {
                "source_field": "subfarm_or_plot_code",
                "source_code": "plot-1",
                "target_type": "SUBFARM",
                "target_business_key": f"subfarm-master-{suffix}",
                "target_parent_business_key": f"farm-master-{suffix}",
            },
            {
                "source_field": "variety_code",
                "source_code": "variety-1",
                "target_type": "VARIETY",
                "target_business_key": f"variety-master-{suffix}",
            },
        ),
        now=datetime.now(UTC),
    )
    if seal:
        seal_mapping_registry(
            sync_session, mapping_policy_version=mapping_policy, now=datetime.now(UTC)
        )


async def _validate_once(import_id: str):
    async with AsyncSessionMaker() as session:
        return await validate_import(session, import_id)


async def _validate_or_in_progress(import_id: str):
    try:
        return ("ok", await _validate_once(import_id))
    except ActualHarvestApiError as exc:
        return ("error", exc.code.value)


async def _seed_i5_batch(*, suffix: str, mapping_policy: str) -> tuple[str, str]:
    payload = _create_payload()
    payload["external_batch_id"] = f"i5-pg-{suffix}"
    payload["idempotency_key"] = f"i5-pg-{suffix}"
    payload["mapping_policy_version"] = mapping_policy
    payload["expected_record_count_or_null"] = 1
    request = ActualHarvestApiCreateImportRequest.model_validate(payload)
    async with AsyncSessionMaker() as session:
        async with session.begin():
            batch, _ = await create_import(session, request)
        record = _record_for_batch(request.external_batch_id)
        async with session.begin():
            await append_import_records(
                session,
                batch.import_id,
                ActualHarvestApiAppendRecordsRequest(records=(record,)),
            )
        async with session.begin():
            await seal_import(session, batch.import_id, actor_identity="operator-1")
    return batch.import_id, request.external_batch_id


async def _seed_i5_batch_with_record(
    *,
    suffix: str,
    mapping_policy: str,
    logical_id: str,
    revision_id: str,
    revision_number: int = 1,
    predecessor: str | None = None,
    record_updates: dict[str, object] | None = None,
) -> tuple[str, str]:
    payload = _create_payload()
    payload["external_batch_id"] = f"i5-pg-record-{suffix}"
    payload["idempotency_key"] = f"i5-pg-record-{suffix}"
    payload["mapping_policy_version"] = mapping_policy
    payload["expected_record_count_or_null"] = 1
    request = ActualHarvestApiCreateImportRequest.model_validate(payload)
    async with AsyncSessionMaker() as session:
        async with session.begin():
            batch, _ = await create_import(session, request)
        record_updates = record_updates or {}
        record = _record_for_batch(request.external_batch_id).model_copy(
            update={
                "external_logical_record_id": logical_id,
                "external_revision_id": revision_id,
                "revision_number": revision_number,
                "supersedes_external_revision_id": predecessor,
                **record_updates,
            }
        )
        async with session.begin():
            await append_import_records(
                session,
                batch.import_id,
                ActualHarvestApiAppendRecordsRequest(records=(record,)),
            )
        async with session.begin():
            await seal_import(session, batch.import_id, actor_identity="operator-1")
    return batch.import_id, request.external_batch_id


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


@pytest.mark.asyncio
async def test_postgres_i5_identical_validate_replays_immutable_result() -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    import_id, external_batch_id = await _seed_i5_batch(
        suffix=suffix,
        mapping_policy=mapping_policy,
    )
    try:
        first, second = await asyncio.gather(
            _validate_or_in_progress(import_id),
            _validate_or_in_progress(import_id),
        )
        assert {first[0], second[0]} == {"ok", "error"}
        successful_result = first[1] if first[0] == "ok" else second[1]
        failed_result = first[1] if first[0] == "error" else second[1]
        assert failed_result == "VALIDATION_IN_PROGRESS"
        assert successful_result.validation_status == "VALIDATED"
        replay = await _validate_once(import_id)
        assert replay.validation_result_hash == successful_result.validation_result_hash
        assert replay.lineage_graph_hash == successful_result.lineage_graph_hash
        assert replay.committed_lineage_basis_hash == successful_result.committed_lineage_basis_hash
        async with AsyncSessionMaker() as session:
            batch = await session.scalar(
                sa.select(ActualHarvestImportBatchModel).where(
                    ActualHarvestImportBatchModel.import_id == import_id
                )
            )
            assert batch is not None
            assert batch.status == "VALIDATED"
            run_count = await session.scalar(
                sa.select(sa.func.count())
                .select_from(ActualHarvestValidationRunModel)
                .where(ActualHarvestValidationRunModel.batch_id == batch.id)
            )
            assert run_count == 1
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_postgres_i5_cancel_validated_preserves_validation_evidence() -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    import_id, external_batch_id = await _seed_i5_batch(
        suffix=suffix,
        mapping_policy=mapping_policy,
    )
    try:
        validation = await _validate_once(import_id)
        async with AsyncSessionMaker() as session:
            async with session.begin():
                cancelled = await cancel_import(session, import_id)
            assert cancelled.status == "CANCELLED"
            batch = await session.scalar(
                sa.select(ActualHarvestImportBatchModel).where(
                    ActualHarvestImportBatchModel.import_id == import_id
                )
            )
            assert batch is not None
            run = await session.scalar(
                sa.select(ActualHarvestValidationRunModel).where(
                    ActualHarvestValidationRunModel.batch_id == batch.id,
                    ActualHarvestValidationRunModel.is_current.is_(True),
                )
            )
            assert run is not None
            assert run.validation_result_hash == validation.validation_result_hash
            assert run.lineage_graph_hash == validation.lineage_graph_hash
            assert run.committed_lineage_basis_hash == validation.committed_lineage_basis_hash
            with pytest.raises(ActualHarvestApiError) as exc_info:
                await validate_import(session, import_id)
            assert exc_info.value.code.value == "IMPORT_BATCH_CANCELLED"
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_postgres_i5_validate_cancel_race_has_one_serialized_outcome() -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    import_id, external_batch_id = await _seed_i5_batch(
        suffix=suffix,
        mapping_policy=mapping_policy,
    )
    try:
        validation_result, cancel_result = await _race_two(
            lambda: _validate_or_in_progress(import_id),
            lambda: _cancel_once(import_id),
        )
        batch, persisted_count = await _batch_state(external_batch_id)
        assert persisted_count == batch.record_count == batch.uploaded_record_count == 1
        if cancel_result[0] == "ok":
            assert validation_result == ("error", "IMPORT_BATCH_CANCELLED")
            assert batch.status == "CANCELLED"
        else:
            assert cancel_result == ("error", "IMPORT_BATCH_CANNOT_CANCEL")
            assert validation_result[0] == "ok"
            assert batch.status == "VALIDATED"
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_postgres_i5_validation_failed_cancel_preserves_all_evidence() -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    import_id, external_batch_id = await _seed_i5_batch_with_record(
        suffix=suffix,
        mapping_policy=mapping_policy,
        logical_id=f"logical-failed-{suffix}",
        revision_id=f"revision-failed-{suffix}",
        record_updates={"farm_code": "unknown-farm", "variety_code": "unknown-variety"},
    )
    try:
        validation = await _validate_once(import_id)
        assert validation.validation_status == "VALIDATION_FAILED"
        async with AsyncSessionMaker() as session:
            async with session.begin():
                cancelled = await cancel_import(session, import_id)
            assert cancelled.status == "CANCELLED"
            batch = await session.scalar(
                sa.select(ActualHarvestImportBatchModel).where(
                    ActualHarvestImportBatchModel.import_id == import_id
                )
            )
            assert batch is not None
            run = await session.scalar(
                sa.select(ActualHarvestValidationRunModel).where(
                    ActualHarvestValidationRunModel.batch_id == batch.id,
                    ActualHarvestValidationRunModel.is_current.is_(True),
                )
            )
            assert run is not None
            assert run.status == "VALIDATION_FAILED"
            assert run.validation_result_hash == validation.validation_result_hash
            assert run.lineage_graph_hash == validation.lineage_graph_hash
            assert run.committed_lineage_basis_hash == validation.committed_lineage_basis_hash
            evidence_count = await session.scalar(
                sa.select(sa.func.count())
                .select_from(ActualHarvestValidationMappingEvidenceModel)
                .where(ActualHarvestValidationMappingEvidenceModel.validation_run_id == run.id)
            )
            error_count = await session.scalar(
                sa.select(sa.func.count())
                .select_from(ActualHarvestValidationErrorModel)
                .where(ActualHarvestValidationErrorModel.validation_run_id == run.id)
            )
            assert evidence_count == 2
            assert error_count >= 2
            with pytest.raises(ActualHarvestApiError) as exc_info:
                await validate_import(session, import_id)
            assert exc_info.value.code.value == "IMPORT_BATCH_CANCELLED"
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_postgres_i5_draft_registry_is_rejected() -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix, seal=False)
    import_id, external_batch_id = await _seed_i5_batch(
        suffix=suffix,
        mapping_policy=mapping_policy,
    )
    try:
        result = await _validate_or_in_progress(import_id)
        assert result == ("error", "IDENTITY_MAPPING_REGISTRY_NOT_SEALED")
        batch, _ = await _batch_state(external_batch_id)
        assert batch.status == "SEALED"
    finally:
        await _cleanup_batch(external_batch_id)
        await _cleanup_registry(mapping_policy)


@pytest.mark.asyncio
async def test_postgres_i5_sealed_registry_entry_mutation_is_rejected() -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = f"mapping-i5-{suffix}"
    async with AsyncSessionMaker() as session:
        await session.begin()
        try:
            await session.run_sync(
                lambda sync_session: _seed_i5_registry_sync(
                    sync_session,
                    suffix=suffix,
                    mapping_policy=mapping_policy,
                )
            )
            entry = await session.scalar(
                sa.select(ActualHarvestMappingRegistryEntryModel)
                .join(
                    ActualHarvestMappingPolicyRegistryModel,
                    ActualHarvestMappingPolicyRegistryModel.id
                    == ActualHarvestMappingRegistryEntryModel.registry_id,
                )
                .where(
                    ActualHarvestMappingPolicyRegistryModel.mapping_policy_version == mapping_policy
                )
            )
            assert entry is not None
            entry.source_code = "mutated-after-seal"
            with pytest.raises(IntegrityError):
                await session.flush()
        finally:
            await session.rollback()


@pytest.mark.asyncio
async def test_postgres_i5_heartbeat_renewal_and_expired_attempt_cannot_finalize() -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    import_id, external_batch_id = await _seed_i5_batch(
        suffix=suffix,
        mapping_policy=mapping_policy,
    )
    try:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                start = await session.run_sync(
                    lambda sync_session: begin_validation(
                        sync_session, import_id=import_id, now=datetime.now(UTC)
                    )
                )
            assert start.kind == "execute"
            assert start.run_id is not None
            assert start.attempt_id is not None
            assert start.attempt_generation is not None
            assert start.fencing_token is not None
            async with session.begin():
                heartbeat = await session.run_sync(
                    lambda sync_session: renew_validation_attempt_lease(
                        sync_session,
                        validation_run_id=start.run_id,
                        attempt_id=start.attempt_id,
                        attempt_generation=start.attempt_generation,
                        fencing_token=start.fencing_token,
                    )
                )
            async with session.begin():
                evidence = await session.run_sync(
                    lambda sync_session: build_validation_evidence(
                        sync_session,
                        run_id=start.run_id,
                        attempt_id=start.attempt_id,
                    )
                )
            async with session.begin():
                await session.execute(
                    sa.update(ActualHarvestValidationAttemptModel)
                    .where(ActualHarvestValidationAttemptModel.attempt_id == start.attempt_id)
                    .values(lease_expires_at=datetime(2000, 1, 1, tzinfo=UTC))
                )
            async with session.begin():
                result = await session.run_sync(
                    lambda sync_session: finalize_validation(
                        sync_session,
                        evidence=evidence,
                        now=heartbeat,
                    )
                )
            assert result == "STALE"
            batch = await session.scalar(
                sa.select(ActualHarvestImportBatchModel).where(
                    ActualHarvestImportBatchModel.import_id == import_id
                )
            )
            assert batch is not None
            assert batch.status == "SEALED"
            result_count = await session.scalar(
                sa.select(sa.func.count())
                .select_from(ActualHarvestValidationResultModel)
                .join(
                    ActualHarvestValidationRunModel,
                    ActualHarvestValidationRunModel.id
                    == ActualHarvestValidationResultModel.validation_run_id,
                )
                .where(ActualHarvestValidationRunModel.batch_id == batch.id)
            )
            assert result_count == 0
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_postgres_i5_old_worker_cannot_demote_new_attempt_state() -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    import_id, external_batch_id = await _seed_i5_batch(
        suffix=suffix,
        mapping_policy=mapping_policy,
    )
    try:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                first = await session.run_sync(
                    lambda sync_session: begin_validation(
                        sync_session, import_id=import_id, now=datetime.now(UTC)
                    )
                )
            assert first.run_id is not None and first.attempt_id is not None
            async with session.begin():
                evidence = await session.run_sync(
                    lambda sync_session: build_validation_evidence(
                        sync_session,
                        run_id=first.run_id,
                        attempt_id=first.attempt_id,
                    )
                )
            async with session.begin():
                await session.execute(
                    sa.update(ActualHarvestValidationAttemptModel)
                    .where(ActualHarvestValidationAttemptModel.attempt_id == first.attempt_id)
                    .values(lease_expires_at=datetime(2000, 1, 1, tzinfo=UTC))
                )
            async with session.begin():
                second = await session.run_sync(
                    lambda sync_session: begin_validation(
                        sync_session, import_id=import_id, now=datetime.now(UTC)
                    )
                )
            assert second.kind == "execute"
            assert second.attempt_id != first.attempt_id
            async with session.begin():
                result = await session.run_sync(
                    lambda sync_session: finalize_validation(
                        sync_session,
                        evidence=evidence,
                        now=datetime.now(UTC),
                    )
                )
            assert result == "STALE"
            batch = await session.scalar(
                sa.select(ActualHarvestImportBatchModel).where(
                    ActualHarvestImportBatchModel.import_id == import_id
                )
            )
            run = await session.scalar(
                sa.select(ActualHarvestValidationRunModel).where(
                    ActualHarvestValidationRunModel.batch_id == batch.id,
                    ActualHarvestValidationRunModel.is_current.is_(True),
                )
            )
            assert batch is not None and run is not None
            assert batch.status == "VALIDATING"
            assert run.active_attempt_id == second.attempt_id
            assert run.is_current
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_postgres_i5_committed_history_predecessor_is_in_validation_basis() -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    logical_id = f"logical-shared-{suffix}"
    first_revision = f"revision-first-{suffix}"
    second_revision = f"revision-second-{suffix}"
    first_id, first_external = await _seed_i5_batch_with_record(
        suffix=f"first-{suffix}",
        mapping_policy=mapping_policy,
        logical_id=logical_id,
        revision_id=first_revision,
    )
    second_id, second_external = await _seed_i5_batch_with_record(
        suffix=f"second-{suffix}",
        mapping_policy=mapping_policy,
        logical_id=logical_id,
        revision_id=second_revision,
        revision_number=2,
        predecessor=first_revision,
    )
    try:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await session.execute(
                    sa.update(ActualHarvestImportBatchModel)
                    .where(ActualHarvestImportBatchModel.import_id == first_id)
                    .values(status="COMMITTED")
                )
        result = await _validate_once(second_id)
        assert result.validation_status == "VALIDATED"
        async with AsyncSessionMaker() as session:
            basis = await session.scalar(
                sa.select(ActualHarvestValidationLineageBasisModel)
                .join(
                    ActualHarvestValidationRunModel,
                    ActualHarvestValidationRunModel.id
                    == ActualHarvestValidationLineageBasisModel.validation_run_id,
                )
                .where(
                    ActualHarvestValidationRunModel.batch_id
                    == (
                        await session.scalar(
                            sa.select(ActualHarvestImportBatchModel.id).where(
                                ActualHarvestImportBatchModel.import_id == second_id
                            )
                        )
                    )
                )
            )
            assert basis is not None
            member_count = await session.scalar(
                sa.select(sa.func.count())
                .select_from(ActualHarvestValidationLineageBasisMemberModel)
                .where(ActualHarvestValidationLineageBasisMemberModel.basis_id == basis.id)
            )
            assert member_count == 1
    finally:
        await _cleanup_batch(first_external)
        await _cleanup_batch(second_external)


@pytest.mark.asyncio
async def test_postgres_i5_uncommitted_batch_is_excluded_from_lineage_basis() -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    logical_id = f"logical-uncommitted-{suffix}"
    first_revision = f"revision-uncommitted-{suffix}"
    first_id, first_external = await _seed_i5_batch_with_record(
        suffix=f"first-{suffix}",
        mapping_policy=mapping_policy,
        logical_id=logical_id,
        revision_id=first_revision,
    )
    second_id, second_external = await _seed_i5_batch_with_record(
        suffix=f"second-{suffix}",
        mapping_policy=mapping_policy,
        logical_id=logical_id,
        revision_id=f"revision-child-{suffix}",
        revision_number=2,
        predecessor=first_revision,
    )
    try:
        result = await _validate_once(second_id)
        assert result.validation_status == "VALIDATION_FAILED"
        async with AsyncSessionMaker() as session:
            error = await session.scalar(
                sa.select(ActualHarvestValidationErrorModel)
                .join(
                    ActualHarvestValidationRunModel,
                    ActualHarvestValidationRunModel.id
                    == ActualHarvestValidationErrorModel.validation_run_id,
                )
                .where(
                    ActualHarvestValidationRunModel.batch_id
                    == (
                        await session.scalar(
                            sa.select(ActualHarvestImportBatchModel.id).where(
                                ActualHarvestImportBatchModel.import_id == second_id
                            )
                        )
                    ),
                    ActualHarvestValidationErrorModel.error_code == "REVISION_PREDECESSOR_MISSING",
                )
            )
            assert error is not None
    finally:
        await _cleanup_batch(first_external)
        await _cleanup_batch(second_external)


@pytest.mark.asyncio
async def test_postgres_i5_validation_errors_use_bounded_keyset_pagination() -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    import_id, external_batch_id = await _seed_i5_batch_with_record(
        suffix=suffix,
        mapping_policy=mapping_policy,
        logical_id=f"logical-errors-{suffix}",
        revision_id=f"revision-errors-{suffix}",
        record_updates={"farm_code": "unknown-farm", "variety_code": "unknown-variety"},
    )
    try:
        result = await _validate_once(import_id)
        assert result.validation_status == "VALIDATION_FAILED"
        async with AsyncSessionMaker() as session:
            first_summary, first_page, token = await validation_errors(
                session, import_id, page_size=1, page_token=None
            )
            assert first_summary.error_count >= 2
            assert len(first_page) == 1
            assert token is not None
            second_summary, second_page, final_token = await validation_errors(
                session, import_id, page_size=1, page_token=token
            )
            assert second_summary.validation_run_identity == first_summary.validation_run_identity
            assert len(second_page) == 1
            assert final_token is None or final_token != token
            assert (
                first_page[0]["record_index"],
                first_page[0]["field_path"],
            ) < (
                second_page[0]["record_index"],
                second_page[0]["field_path"],
            )
    finally:
        await _cleanup_batch(external_batch_id)
