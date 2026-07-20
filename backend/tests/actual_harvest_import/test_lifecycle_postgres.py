from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import delete
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_import import validation_service as validation_service_module
from backend.app.actual_harvest_import.api_auth import ActualHarvestActorContext
from backend.app.actual_harvest_import.api_errors import (
    ActualHarvestApiError,
    ActualHarvestApiErrorCode,
)
from backend.app.actual_harvest_import.api_schemas import (
    ActualHarvestApiAppendRecordsRequest,
    ActualHarvestApiCreateImportRequest,
    ActualHarvestApiRecordInput,
)
from backend.app.actual_harvest_import.canonical_hashes import compute_canonical_record_hash
from backend.app.actual_harvest_import.commit_models import (
    ActualHarvestCommitManifestModel,
)
from backend.app.actual_harvest_import.commit_service import (
    CommitResult,
)
from backend.app.actual_harvest_import.commit_service import (
    commit_batch as _commit_service_fn,
)
from backend.app.actual_harvest_import.enums import (
    ActualHarvestImportBatchStatus,
    ActualHarvestImportChannel,
    ActualHarvestRecordStatus,
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
from backend.app.actual_harvest_import.validation_hashes import digest
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

# PR #117 formal review B1 fix: deterministic trigger rejection attribution.
# The previous helper swallowed any DBAPIError, which let connection
# failures, malformed SQL, missing relations, permission errors, and
# SQLSTATE 23514 with a different message all count as proof that the
# sealed-registry trigger rejected the statement. The migration raises
# the rejection with ERRCODE = 'check_violation' (SQLSTATE 23514) and a
# stable server primary message per trigger; this module pins BOTH the
# SQLSTATE and the exact server primary message before accepting the
# exception as expected trigger behaviour.
EXPECTED_SQLSTATE = "23514"
REGISTRY_TRIGGER_MESSAGE = "sealed mapping registry is immutable"
ENTRY_TRIGGER_MESSAGE = "sealed mapping registry entries are immutable"


class I5TriggerTarget(StrEnum):
    """Which sealed-registry trigger the test expects to enforce rejection."""

    REGISTRY = "registry"
    ENTRY = "entry"


def _trigger_message(target: I5TriggerTarget) -> str:
    if target is I5TriggerTarget.REGISTRY:
        return REGISTRY_TRIGGER_MESSAGE
    return ENTRY_TRIGGER_MESSAGE


def _chain_exceptions(exc: BaseException) -> list[BaseException]:
    """Walk an exception chain deterministically (cause/context/__cause__)."""

    seen: set[int] = set()
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        cause = current.__cause__ or current.__context__
        if cause is None or id(cause) in seen:
            break
        current = cause
    return chain


def _extract_sqlstate(exc: BaseException) -> str | None:
    """Best-effort extraction of a SQLSTATE from a SQLAlchemy/asyncpg chain."""

    for candidate in _chain_exceptions(exc):
        sqlstate = getattr(candidate, "sqlstate", None)
        if isinstance(sqlstate, str) and sqlstate:
            return sqlstate
        pgcode = getattr(candidate, "pgcode", None)
        if isinstance(pgcode, str) and pgcode:
            return pgcode
        diag = getattr(candidate, "diag", None)
        if diag is not None:
            diag_sqlstate = getattr(diag, "sqlstate", None)
            if isinstance(diag_sqlstate, str) and diag_sqlstate:
                return diag_sqlstate
        args = getattr(candidate, "args", ())
        if args and isinstance(args[0], str) and len(args[0]) >= 5 and args[0][:5].isdigit():
            return args[0][:5]
    return None


def _extract_server_message(exc: BaseException) -> str | None:
    """Best-effort extraction of the server primary message."""

    for candidate in _chain_exceptions(exc):
        message = getattr(candidate, "message", None)
        if isinstance(message, str) and message:
            return message
        diag = getattr(candidate, "diag", None)
        if diag is not None:
            diag_message = getattr(diag, "message_primary", None) or getattr(diag, "message", None)
            if isinstance(diag_message, str) and diag_message:
                return diag_message
    return None


def _raise_unexpected_dbapi_error(exc: BaseException, *, sqlstate: str | None) -> None:
    """Surface the original DBAPIError with diagnostic context attached.

    Some DBAPIError subclasses (e.g. SQLAlchemy's asyncpg-wrapped
    IntegrityError) require positional ``params`` and ``orig``
    arguments and refuse to be re-constructed with a single message
    string. To stay fail-closed without coupling this helper to any
    particular DBAPIError constructor, we re-raise the *original*
    exception object unchanged but first attach the diagnostic
    message as an ``args[-1]`` suffix so pytest's traceback and the
    CI step summary surface the same SQLSTATE / message data.
    """

    diagnostic = (
        f"unexpected DBAPIError while asserting sealed-registry trigger "
        f"rejection: sqlstate={sqlstate!r} exc={type(exc).__name__}"
    )
    original_args = tuple(getattr(exc, "args", ()))
    new_args = original_args + (diagnostic,) if original_args else (diagnostic,)
    try:
        exc.args = new_args  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive against frozen exceptions
        pass
    raise exc


pytestmark = [pytest.mark.postgres, pytest.mark.integration]


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")
    assert_safe_postgres_test_identity(env=None)


_I5_MODULE_TRUNCATE_TABLES = (
    "actual_harvest_import_batch",
    "actual_harvest_mapping_policy_registry",
    "dim_subfarm",
    "dim_variety",
    "dim_farm",
    "dim_season",
)

_I5_MODULE_EVIDENCE_TABLES = (
    "actual_harvest_import_batch",
    "actual_harvest_import_record",
    "actual_harvest_mapping_policy_registry",
    "actual_harvest_mapping_registry_entry",
    "actual_harvest_validation_run",
    "actual_harvest_validation_result",
    "actual_harvest_validation_error",
    "actual_harvest_mapping_snapshot",
    "actual_harvest_validation_mapping_evidence",
    "actual_harvest_validation_lineage_node",
    "actual_harvest_validation_lineage_edge",
    "actual_harvest_validation_lineage_basis",
    "actual_harvest_validation_lineage_basis_member",
    "dim_subfarm",
    "dim_variety",
    "dim_farm",
    "dim_season",
)


async def _truncate_i5_module_database() -> None:
    """Release I5-owned PostgreSQL fixtures without bypassing triggers."""
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        return
    if os.getenv("APP_ENV") != "test":
        raise RuntimeError("I5 PostgreSQL cleanup requires APP_ENV=test")
    assert_safe_postgres_test_identity(env=None)

    table_list = ", ".join(_I5_MODULE_TRUNCATE_TABLES)
    async with AsyncSessionMaker() as session:
        try:
            async with session.begin():
                await session.execute(sa.text(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"))
        except BaseException:
            await session.rollback()
            raise


async def _i5_module_table_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    async with AsyncSessionMaker() as session:
        for table_name in _I5_MODULE_EVIDENCE_TABLES:
            value = await session.scalar(sa.text(f"SELECT COUNT(*) FROM {table_name}"))
            counts[table_name] = int(value or 0)
    return counts


async def _assert_i5_trigger_rejects(
    statement: str,
    parameters: dict[str, object],
    *,
    expected_message: str,
) -> None:
    """Assert a forbidden mutation is rejected by a sealed-registry trigger.

    B1 fix: requires BOTH SQLSTATE 23514 AND an exact match against the
    expected server primary message. Any other DBAPIError (connection
    failure, malformed SQL, missing relation, permission error, SQLSTATE
    23514 with a different message, etc.) is re-raised so the test fails
    closed. The matched exception message MUST be supplied explicitly by
    the caller; broad substring matching of "immutable" is forbidden by
    the PR #117 B1 deterministic-attribution contract.
    """

    if expected_message not in (REGISTRY_TRIGGER_MESSAGE, ENTRY_TRIGGER_MESSAGE):
        raise ValueError(
            "_assert_i5_trigger_rejects: expected_message must be one of "
            f"{REGISTRY_TRIGGER_MESSAGE!r} or {ENTRY_TRIGGER_MESSAGE!r}; "
            "broad substring matching is forbidden by the PR #117 B1 contract."
        )

    try:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await session.execute(sa.text(statement), parameters)
    except DBAPIError as exc:
        sqlstate = _extract_sqlstate(exc)
        server_message = _extract_server_message(exc)
        if sqlstate == EXPECTED_SQLSTATE and server_message == expected_message:
            return
        _raise_unexpected_dbapi_error(exc, sqlstate=sqlstate)
    raise AssertionError(
        "sealed-registry trigger accepted a forbidden mutation "
        f"(expected SQLSTATE={EXPECTED_SQLSTATE} message={expected_message!r})"
    )


@pytest_asyncio.fixture(scope="module", autouse=True)
async def isolate_i5_postgres_module() -> AsyncIterator[None]:
    """Own this module's committed PostgreSQL fixture data in shared CI DB."""
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        yield
        return

    await _truncate_i5_module_database()
    try:
        yield
    finally:
        await _truncate_i5_module_database()


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


_PROTECTED_IMPORT_RECORD_STATUSES = frozenset(
    {
        ActualHarvestImportBatchStatus.SEALED.value,
        ActualHarvestImportBatchStatus.VALIDATING.value,
        ActualHarvestImportBatchStatus.VALIDATED.value,
        ActualHarvestImportBatchStatus.COMMITTED.value,
    }
)


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
            # Lock the parent batch row for the duration of this
            # transaction so a concurrent commit/cancel cannot promote
            # the batch into a protected status between the status
            # check and the evidence delete below. PROTECTED_STATUS
            # batches are left for the module-scoped TRUNCATE...
            # CASCADE teardown to remove.
            batch = await session.scalar(
                sa.select(ActualHarvestImportBatchModel)
                .where(ActualHarvestImportBatchModel.external_batch_id == external_batch_id)
                .with_for_update()
            )
            if batch is None:
                return
            if batch.status in _PROTECTED_IMPORT_RECORD_STATUSES:
                return
            batch_id = batch.id
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
    # PROTECTED_STATUS_RECHECK: a concurrent commit could have promoted
    # the batch into a protected status between transaction 1 and 2, so
    # the second check is mandatory before deleting records (which the
    # immutability trigger would otherwise reject).
    async with AsyncSessionMaker() as session:
        async with session.begin():
            batch = await session.scalar(
                sa.select(ActualHarvestImportBatchModel)
                .where(ActualHarvestImportBatchModel.external_batch_id == external_batch_id)
                .with_for_update()
            )
            if batch is None:
                return
            if batch.status in _PROTECTED_IMPORT_RECORD_STATUSES:
                return
            batch_id = batch.id
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
            if registry.status == "SEALED":
                # The PostgreSQL immutability trigger must also protect test
                # cleanup. The isolated CI database is discarded after the
                # shard, so never disable the trigger or bypass it here.
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
    seal: bool = True,
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
        if seal:
            async with session.begin():
                await seal_import(session, batch.import_id, actor_identity="operator-1")
    return batch.import_id, request.external_batch_id


async def _seed_i5_batch_with_records(
    *,
    suffix: str,
    mapping_policy: str,
    record_specs: tuple[dict[str, object], ...],
) -> tuple[str, str]:
    payload = _create_payload()
    payload["external_batch_id"] = f"i5-pg-records-{suffix}"
    payload["idempotency_key"] = f"i5-pg-records-{suffix}"
    payload["mapping_policy_version"] = mapping_policy
    payload["expected_record_count_or_null"] = len(record_specs)
    request = ActualHarvestApiCreateImportRequest.model_validate(payload)
    async with AsyncSessionMaker() as session:
        async with session.begin():
            batch, _ = await create_import(session, request)
        records = tuple(
            _record_for_batch(request.external_batch_id).model_copy(update=spec)
            for spec in record_specs
        )
        async with session.begin():
            await append_import_records(
                session,
                batch.import_id,
                ActualHarvestApiAppendRecordsRequest(records=records),
            )
        async with session.begin():
            await seal_import(session, batch.import_id, actor_identity="operator-1")
    return batch.import_id, request.external_batch_id


async def _validation_error_codes(import_id: str) -> set[str]:
    async with AsyncSessionMaker() as session:
        _summary, page, token = await validation_errors(
            session, import_id, page_size=100, page_token=None
        )
        rows = list(page)
        while token is not None:
            _summary, page, token = await validation_errors(
                session, import_id, page_size=100, page_token=token
            )
            rows.extend(page)
        return {row["error_code"] for row in rows}


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
async def test_postgres_i5_successful_validation_writes_complete_evidence_set() -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    import_id, external_batch_id = await _seed_i5_batch(
        suffix=f"complete-evidence-{suffix}",
        mapping_policy=mapping_policy,
    )
    try:
        result = await _validate_once(import_id)
        assert result.validation_status == "VALIDATED"
        async with AsyncSessionMaker() as session:
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
            expected_counts = {
                ActualHarvestMappingSnapshotModel: 1,
                ActualHarvestValidationResultModel: 1,
                ActualHarvestValidationRecordModel: 1,
                ActualHarvestValidationMappingEvidenceModel: 4,
                ActualHarvestValidationLineageNodeModel: 1,
                ActualHarvestValidationLineageBasisModel: 1,
            }
            for model, expected_count in expected_counts.items():
                assert (
                    await session.scalar(
                        sa.select(sa.func.count())
                        .select_from(model)
                        .where(model.validation_run_id == run.id)
                    )
                    == expected_count
                )
            assert (
                await session.scalar(
                    sa.select(sa.func.count())
                    .select_from(ActualHarvestValidationLineageEdgeModel)
                    .where(ActualHarvestValidationLineageEdgeModel.validation_run_id == run.id)
                )
                == 0
            )
    finally:
        await _cleanup_batch(external_batch_id)
        await _cleanup_registry(mapping_policy)


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
async def test_postgres_i5_registry_seal_and_validate_are_serialized() -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix, seal=False)
    import_id, external_batch_id = await _seed_i5_batch(
        suffix=f"registry-race-{suffix}",
        mapping_policy=mapping_policy,
    )
    barrier = asyncio.Barrier(2)

    async def seal() -> str:
        await barrier.wait()
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await session.run_sync(
                    lambda sync_session: seal_mapping_registry(
                        sync_session,
                        mapping_policy_version=mapping_policy,
                        now=datetime.now(UTC),
                    )
                )
        return "SEALED"

    async def validate() -> tuple[str, str]:
        await barrier.wait()
        return await _validate_or_in_progress(import_id)

    try:
        seal_result, validation_result = await asyncio.gather(seal(), validate())
        assert seal_result == "SEALED"
        assert validation_result[0] in {"error", "ok"}
        if validation_result[0] == "error":
            assert validation_result[1] == "IDENTITY_MAPPING_REGISTRY_NOT_SEALED"
            batch, _ = await _batch_state(external_batch_id)
            assert batch.status == "SEALED"
        else:
            batch, _ = await _batch_state(external_batch_id)
            assert batch.status in {"VALIDATED", "VALIDATION_FAILED"}
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
            assert second.attempt_generation == first.attempt_generation + 1
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
async def test_postgres_i5_committed_revision_identity_same_payload_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    history_id, history_external = await _seed_i5_batch_with_record(
        suffix=f"history-collision-{suffix}",
        mapping_policy=mapping_policy,
        logical_id=f"logical-history-{suffix}",
        revision_id=f"revision-history-{suffix}",
    )
    current_id, current_external = await _seed_i5_batch_with_record(
        suffix=f"current-collision-{suffix}",
        mapping_policy=mapping_policy,
        logical_id=f"logical-current-{suffix}",
        revision_id=f"revision-current-{suffix}",
    )
    try:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await session.execute(
                    sa.update(ActualHarvestImportBatchModel)
                    .where(ActualHarvestImportBatchModel.import_id == history_id)
                    .values(status="COMMITTED")
                )
            current_row = await session.scalar(
                sa.select(ActualHarvestImportRecordModel).where(
                    ActualHarvestImportRecordModel.external_batch_id == current_external
                )
            )
            assert current_row is not None
            canonical_fields = tuple(
                field_name
                for field_name in ActualHarvestImportRecordInput.model_fields
                if field_name not in {"source_row_number", "source_sheet_name"}
            )
            current_record = ActualHarvestImportRecordInput.model_validate(
                {field_name: getattr(current_row, field_name) for field_name in canonical_fields}
            )
            collision_member = {
                "source_system": current_record.source_system,
                "committed_batch_ref": f"{current_record.source_system}:{history_external}",
                "external_logical_record_id": current_record.external_logical_record_id,
                "external_revision_id": current_record.external_revision_id,
                "revision_number": current_record.revision_number,
                "canonical_record_hash": compute_canonical_record_hash(current_record),
                "predecessor_revision_id": current_record.supersedes_external_revision_id,
                "record_status": current_record.record_status.value,
                "source_recorded_at": current_record.source_recorded_at,
                "source_recorded_at_authority_status": (
                    current_record.source_recorded_at_authority_status.value
                ),
            }

        history_before, history_count_before = await _batch_state(history_external)
        assert history_before.status == "COMMITTED"
        history_canonical_before = await _record_canonical_state(history_external)
        # I2's global source/revision uniqueness prevents a natural duplicate
        # row from being persisted. Inject the equivalent committed basis
        # snapshot so the real PostgreSQL validation/finalization path still
        # proves the I5 defensive collision gate.
        monkeypatch.setattr(
            validation_service_module,
            "_current_basis",
            lambda _session, _batch: ("c" * 64, (collision_member,)),
        )
        result = await _validate_once(current_id)
        assert result.validation_status == "VALIDATION_FAILED"
        assert result.error_count == 1

        async with AsyncSessionMaker() as session:
            current_batch = await session.scalar(
                sa.select(ActualHarvestImportBatchModel).where(
                    ActualHarvestImportBatchModel.import_id == current_id
                )
            )
            assert current_batch is not None
            run = await session.scalar(
                sa.select(ActualHarvestValidationRunModel).where(
                    ActualHarvestValidationRunModel.batch_id == current_batch.id,
                    ActualHarvestValidationRunModel.is_current.is_(True),
                )
            )
            assert run is not None
            errors = list(
                await session.scalars(
                    sa.select(ActualHarvestValidationErrorModel).where(
                        ActualHarvestValidationErrorModel.validation_run_id == run.id
                    )
                )
            )
            assert len(errors) == 1
            assert errors[0].error_code == "REVISION_IDENTITY_CONFLICT"
            assert errors[0].record_index == 1
            assert errors[0].field_path == "external_revision_id"
            assert errors[0].sanitized_details == (
                '{"authority":"COMMITTED_SOURCE_REVISION_HISTORY"}'
            )
            record_evidence = await session.scalar(
                sa.select(ActualHarvestValidationRecordModel).where(
                    ActualHarvestValidationRecordModel.validation_run_id == run.id
                )
            )
            assert record_evidence is not None and not record_evidence.is_valid
            nodes = list(
                await session.scalars(
                    sa.select(ActualHarvestValidationLineageNodeModel).where(
                        ActualHarvestValidationLineageNodeModel.validation_run_id == run.id
                    )
                )
            )
            assert any(node.origin == "COMMITTED_HISTORY_REVISION" for node in nodes)
            assert not any(
                node.origin == "CURRENT_BATCH_REVISION"
                and node.external_revision_id == current_record.external_revision_id
                for node in nodes
            )

        history_after, history_count_after = await _batch_state(history_external)
        assert history_after.status == "COMMITTED"
        assert history_count_after == history_count_before == 1
        assert await _record_canonical_state(history_external) == history_canonical_before
    finally:
        await _cleanup_batch(current_external)
        await _cleanup_batch(history_external)
        await _cleanup_registry(mapping_policy)


@pytest.mark.asyncio
async def test_postgres_i5_committed_revision_collision_binds_current_record_regardless_of_sort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    history_id, history_external = await _seed_i5_batch_with_record(
        suffix=f"history-sort-{suffix}",
        mapping_policy=mapping_policy,
        logical_id=f"z-committed-history-{suffix}",
        revision_id=f"revision-history-sort-{suffix}",
    )
    current_id, current_external = await _seed_i5_batch_with_record(
        suffix=f"current-sort-{suffix}",
        mapping_policy=mapping_policy,
        logical_id=f"a-current-collision-{suffix}",
        revision_id=f"revision-current-sort-{suffix}",
    )
    try:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await session.execute(
                    sa.update(ActualHarvestImportBatchModel)
                    .where(ActualHarvestImportBatchModel.import_id == history_id)
                    .values(status="COMMITTED")
                )
            current_row = await session.scalar(
                sa.select(ActualHarvestImportRecordModel).where(
                    ActualHarvestImportRecordModel.external_batch_id == current_external
                )
            )
            assert current_row is not None
            canonical_fields = tuple(
                field_name
                for field_name in ActualHarvestImportRecordInput.model_fields
                if field_name not in {"source_row_number", "source_sheet_name"}
            )
            current_record = ActualHarvestImportRecordInput.model_validate(
                {field_name: getattr(current_row, field_name) for field_name in canonical_fields}
            )
            committed_collision = current_record.model_copy(
                update={
                    "external_batch_id": history_external,
                    "external_logical_record_id": f"z-committed-history-{suffix}",
                }
            )
            collision_member = {
                "source_system": committed_collision.source_system,
                "committed_batch_ref": f"{current_record.source_system}:{history_external}",
                "external_logical_record_id": committed_collision.external_logical_record_id,
                "external_revision_id": current_record.external_revision_id,
                "revision_number": committed_collision.revision_number,
                "canonical_record_hash": compute_canonical_record_hash(committed_collision),
                "predecessor_revision_id": committed_collision.supersedes_external_revision_id,
                "record_status": committed_collision.record_status.value,
                "source_recorded_at": committed_collision.source_recorded_at,
                "source_recorded_at_authority_status": (
                    committed_collision.source_recorded_at_authority_status.value
                ),
            }

        history_before, history_count_before = await _batch_state(history_external)
        history_canonical_before = await _record_canonical_state(history_external)
        monkeypatch.setattr(
            validation_service_module,
            "_current_basis",
            lambda _session, _batch: ("c" * 64, (collision_member,)),
        )
        result = await _validate_once(current_id)
        assert result.validation_status == "VALIDATION_FAILED"

        async with AsyncSessionMaker() as session:
            current_batch = await session.scalar(
                sa.select(ActualHarvestImportBatchModel).where(
                    ActualHarvestImportBatchModel.import_id == current_id
                )
            )
            assert current_batch is not None
            run = await session.scalar(
                sa.select(ActualHarvestValidationRunModel).where(
                    ActualHarvestValidationRunModel.batch_id == current_batch.id,
                    ActualHarvestValidationRunModel.is_current.is_(True),
                )
            )
            assert run is not None
            errors = list(
                await session.scalars(
                    sa.select(ActualHarvestValidationErrorModel).where(
                        ActualHarvestValidationErrorModel.validation_run_id == run.id
                    )
                )
            )
            collision_errors = [
                error for error in errors if error.error_code == "REVISION_IDENTITY_CONFLICT"
            ]
            assert len(collision_errors) == 1
            assert collision_errors[0].record_index == 1
            assert (
                collision_errors[0].external_logical_record_id
                == current_record.external_logical_record_id
            )
            assert collision_errors[0].external_revision_id == current_record.external_revision_id
            assert collision_errors[0].field_path == "external_revision_id"
            assert collision_errors[0].sanitized_details == (
                '{"authority":"COMMITTED_SOURCE_REVISION_HISTORY"}'
            )
            current_evidence = await session.scalar(
                sa.select(ActualHarvestValidationRecordModel).where(
                    ActualHarvestValidationRecordModel.validation_run_id == run.id,
                    ActualHarvestValidationRecordModel.record_index == 1,
                )
            )
            assert current_evidence is not None and not current_evidence.is_valid
            nodes = list(
                await session.scalars(
                    sa.select(ActualHarvestValidationLineageNodeModel).where(
                        ActualHarvestValidationLineageNodeModel.validation_run_id == run.id
                    )
                )
            )
            assert any(
                node.origin == "COMMITTED_HISTORY_REVISION"
                and node.external_logical_record_id
                == committed_collision.external_logical_record_id
                for node in nodes
            )
            assert not any(
                node.origin == "CURRENT_BATCH_REVISION"
                and node.external_revision_id == current_record.external_revision_id
                for node in nodes
            )

        history_after, history_count_after = await _batch_state(history_external)
        assert history_after.status == history_before.status == "COMMITTED"
        assert history_count_after == history_count_before == 1
        assert await _record_canonical_state(history_external) == history_canonical_before
    finally:
        await _cleanup_batch(current_external)
        await _cleanup_batch(history_external)
        await _cleanup_registry(mapping_policy)


@pytest.mark.asyncio
async def test_postgres_i5_identical_error_payload_is_persisted_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    import_id, external_batch_id = await _seed_i5_batch_with_records(
        suffix=f"error-dedup-{suffix}",
        mapping_policy=mapping_policy,
        record_specs=(
            {
                "external_logical_record_id": f"logical-error-dedup-1-{suffix}",
                "external_revision_id": f"revision-error-dedup-1-{suffix}",
                "farm_code": "missing-farm-1",
                "variety_code": "missing-variety-1",
            },
            {
                "external_logical_record_id": f"logical-error-dedup-2-{suffix}",
                "external_revision_id": f"revision-error-dedup-2-{suffix}",
                "farm_code": "missing-farm-2",
                "variety_code": "missing-variety-2",
            },
        ),
    )
    try:
        candidate_calls: list[tuple[dict[str, object], ...]] = []
        candidate_values: list[tuple[object, ...]] = []
        original_sorted_errors = validation_service_module._sorted_errors

        def capture_candidates(values):
            payloads = tuple(value.payload() for value in values)
            if any(payload["error_code"] == "BATCH_RECORD_COUNT_MISMATCH" for payload in payloads):
                candidate_calls.append(payloads)
                candidate_values.append(tuple(values))
            return original_sorted_errors(values)

        monkeypatch.setattr(validation_service_module, "_sorted_errors", capture_candidates)
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await session.execute(
                    sa.update(ActualHarvestImportBatchModel)
                    .where(ActualHarvestImportBatchModel.import_id == import_id)
                    .values(
                        record_count=0,
                        uploaded_record_count=0,
                        expected_record_count_or_null=3,
                    )
                )

        result = await _validate_once(import_id)
        assert result.validation_status == "VALIDATION_FAILED"
        assert candidate_calls
        duplicate_candidates = [
            payload
            for call in candidate_calls
            for payload in call
            if payload["error_code"] == "BATCH_RECORD_COUNT_MISMATCH"
        ]
        assert len(duplicate_candidates) >= 2
        assert len({repr(payload) for payload in duplicate_candidates}) == 1
        assert candidate_values
        forward = original_sorted_errors(list(candidate_values[0]))
        reverse = original_sorted_errors(list(reversed(candidate_values[0])))
        assert [value.payload() for value in forward] == [value.payload() for value in reverse]

        async with AsyncSessionMaker() as session:
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
            result_row = await session.scalar(
                sa.select(ActualHarvestValidationResultModel).where(
                    ActualHarvestValidationResultModel.validation_run_id == run.id
                )
            )
            persisted_errors = list(
                await session.scalars(
                    sa.select(ActualHarvestValidationErrorModel).where(
                        ActualHarvestValidationErrorModel.validation_run_id == run.id
                    )
                )
            )
            assert result_row is not None
            assert len(persisted_errors) == 5
            assert len({error.error_hash for error in persisted_errors}) == 5
            assert {error.error_code for error in persisted_errors} == {
                "BATCH_RECORD_COUNT_MISMATCH",
                "IDENTITY_MAPPING_NOT_FOUND",
            }
            assert {error.field_path for error in persisted_errors} == {
                None,
                "farm_code",
                "variety_code",
            }
            assert {error.record_index for error in persisted_errors} == {None, 1, 2}
            assert run.error_count == result_row.error_count == len(persisted_errors)
            assert batch.invalid_record_count == 2
            assert run.error_count != batch.invalid_record_count
            assert result.error_count == len(persisted_errors) == 5
            pages: list[dict[str, object]] = []
            _summary, page, token = await validation_errors(
                session, import_id, page_size=2, page_token=None
            )
            pages.extend(page)
            while token is not None:
                _summary, page, token = await validation_errors(
                    session, import_id, page_size=2, page_token=token
                )
                pages.extend(page)
            assert len(pages) == len(persisted_errors) == 5
            assert len({digest(row) for row in pages}) == 5
            assert {row["error_code"] for row in pages} == {
                "BATCH_RECORD_COUNT_MISMATCH",
                "IDENTITY_MAPPING_NOT_FOUND",
            }
            assert result_row.validation_result_hash == run.validation_result_hash
    finally:
        await _cleanup_batch(external_batch_id)
        await _cleanup_registry(mapping_policy)


@pytest.mark.asyncio
async def test_postgres_i5_error_persistence_failure_rolls_back_all_final_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    import_id, external_batch_id = await _seed_i5_batch_with_record(
        suffix=f"error-rollback-{suffix}",
        mapping_policy=mapping_policy,
        logical_id=f"logical-error-rollback-{suffix}",
        revision_id=f"revision-error-rollback-{suffix}",
        record_updates={"farm_code": "missing-farm-rollback"},
    )
    try:
        original_finalize = validation_service_module.finalize_validation

        def fail_after_finalization(session, *, evidence, now):
            status = original_finalize(session, evidence=evidence, now=now)
            assert status == "VALIDATION_FAILED"
            raise RuntimeError("injected validation evidence persistence failure")

        monkeypatch.setattr(
            validation_service_module, "finalize_validation", fail_after_finalization
        )
        with pytest.raises(RuntimeError, match="injected validation evidence persistence failure"):
            await _validate_once(import_id)

        async with AsyncSessionMaker() as session:
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
            assert batch.status == "VALIDATING"
            assert run.status == "VALIDATING"
            assert run.validation_result_hash is None
            assert run.completed_at is None
            assert run.valid_count == 0
            assert run.invalid_count == 0
            assert run.error_count == 0
            assert run.warning_count == 0

            evidence_tables = (
                ActualHarvestValidationResultModel,
                ActualHarvestValidationRecordModel,
                ActualHarvestMappingSnapshotModel,
                ActualHarvestValidationMappingEvidenceModel,
                ActualHarvestValidationErrorModel,
                ActualHarvestValidationLineageNodeModel,
                ActualHarvestValidationLineageEdgeModel,
                ActualHarvestValidationLineageBasisModel,
            )
            for model in evidence_tables:
                count = await session.scalar(
                    sa.select(sa.func.count())
                    .select_from(model)
                    .where(model.validation_run_id == run.id)
                )
                assert count == 0, model.__tablename__
            basis_member_count = await session.scalar(
                sa.select(sa.func.count())
                .select_from(ActualHarvestValidationLineageBasisMemberModel)
                .join(
                    ActualHarvestValidationLineageBasisModel,
                    ActualHarvestValidationLineageBasisMemberModel.basis_id
                    == ActualHarvestValidationLineageBasisModel.id,
                )
                .where(ActualHarvestValidationLineageBasisModel.validation_run_id == run.id)
            )
            assert basis_member_count == 0
    finally:
        await _cleanup_batch(external_batch_id)
        await _cleanup_registry(mapping_policy)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_id", "expected_code"),
    [
        pytest.param("missing_predecessor", "REVISION_PREDECESSOR_MISSING"),
        pytest.param("validated_predecessor", "REVISION_PREDECESSOR_MISSING"),
        pytest.param("cancelled_predecessor", "REVISION_PREDECESSOR_MISSING"),
        pytest.param("revision_number_discontinuity", "REVISION_NUMBER_CONFLICT"),
        pytest.param("multiple_successors", "REVISION_MULTIPLE_SUCCESSORS"),
        pytest.param("lineage_cycle", "REVISION_LINEAGE_CYCLE"),
        pytest.param("logical_record_mismatch", "REVISION_LOGICAL_RECORD_MISMATCH"),
        pytest.param("multiple_structural_terminals", "MULTIPLE_TERMINAL_REVISIONS"),
        pytest.param("multiple_finalized_terminals", "MULTIPLE_TERMINAL_REVISIONS"),
        pytest.param("corrected_without_successor", "INVALID_RECORD_STATUS"),
    ],
)
async def test_postgres_i5_lineage_rejection_matrix(case_id: str, expected_code: str) -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    history_external: str | None = None
    logical_id = f"logical-lineage-{suffix}"
    predecessor = f"revision-predecessor-{suffix}"
    if case_id == "missing_predecessor":
        record_specs = (
            {
                "external_logical_record_id": logical_id,
                "external_revision_id": f"revision-child-{suffix}",
                "revision_number": 2,
                "supersedes_external_revision_id": predecessor,
            },
        )
    elif case_id in {"validated_predecessor", "cancelled_predecessor"}:
        _history_id, history_external = await _seed_i5_batch_with_record(
            suffix=f"history-{case_id}-{suffix}",
            mapping_policy=mapping_policy,
            logical_id=logical_id,
            revision_id=predecessor,
        )
        history_status = "VALIDATED" if case_id == "validated_predecessor" else "CANCELLED"
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await session.execute(
                    sa.update(ActualHarvestImportBatchModel)
                    .where(ActualHarvestImportBatchModel.external_batch_id == history_external)
                    .values(status=history_status)
                )
        record_specs = (
            {
                "external_logical_record_id": logical_id,
                "external_revision_id": f"revision-child-{suffix}",
                "revision_number": 2,
                "supersedes_external_revision_id": predecessor,
            },
        )
    elif case_id == "revision_number_discontinuity":
        record_specs = (
            {
                "external_logical_record_id": logical_id,
                "external_revision_id": predecessor,
                "revision_number": 1,
            },
            {
                "external_logical_record_id": logical_id,
                "external_revision_id": f"revision-three-{suffix}",
                "revision_number": 3,
                "supersedes_external_revision_id": predecessor,
            },
        )
    elif case_id == "multiple_successors":
        record_specs = (
            {
                "external_logical_record_id": logical_id,
                "external_revision_id": predecessor,
                "revision_number": 1,
            },
            {
                "external_logical_record_id": logical_id,
                "external_revision_id": f"revision-two-a-{suffix}",
                "revision_number": 2,
                "supersedes_external_revision_id": predecessor,
            },
            {
                "external_logical_record_id": logical_id,
                "external_revision_id": f"revision-two-b-{suffix}",
                "revision_number": 3,
                "supersedes_external_revision_id": predecessor,
            },
        )
    elif case_id == "lineage_cycle":
        first = f"revision-cycle-a-{suffix}"
        second = f"revision-cycle-b-{suffix}"
        record_specs = (
            {
                "external_logical_record_id": logical_id,
                "external_revision_id": first,
                "revision_number": 2,
                "supersedes_external_revision_id": second,
            },
            {
                "external_logical_record_id": logical_id,
                "external_revision_id": second,
                "revision_number": 3,
                "supersedes_external_revision_id": first,
            },
        )
    elif case_id == "logical_record_mismatch":
        record_specs = (
            {
                "external_logical_record_id": logical_id,
                "external_revision_id": predecessor,
                "revision_number": 1,
            },
            {
                "external_logical_record_id": f"other-logical-{suffix}",
                "external_revision_id": f"revision-child-{suffix}",
                "revision_number": 2,
                "supersedes_external_revision_id": predecessor,
            },
        )
    elif case_id in {"multiple_structural_terminals", "multiple_finalized_terminals"}:
        record_status = (
            ActualHarvestRecordStatus.FINALIZED
            if case_id == "multiple_finalized_terminals"
            else ActualHarvestRecordStatus.ACTIVE
        )
        record_specs = (
            {
                "external_logical_record_id": logical_id,
                "external_revision_id": f"revision-terminal-a-{suffix}",
                "revision_number": 1,
                "record_status": record_status,
            },
            {
                "external_logical_record_id": logical_id,
                "external_revision_id": f"revision-terminal-b-{suffix}",
                "revision_number": 2,
                "supersedes_external_revision_id": f"missing-terminal-predecessor-{suffix}",
                "record_status": record_status,
            },
        )
    else:
        record_specs = (
            {
                "external_logical_record_id": logical_id,
                "external_revision_id": f"revision-corrected-{suffix}",
                "revision_number": 1,
                "record_status": ActualHarvestRecordStatus.CORRECTED,
            },
        )
    import_id, external_batch_id = await _seed_i5_batch_with_records(
        suffix=f"matrix-{case_id}-{suffix}",
        mapping_policy=mapping_policy,
        record_specs=record_specs,
    )
    try:
        result = await _validate_once(import_id)
        assert result.validation_status == "VALIDATION_FAILED"
        assert expected_code in await _validation_error_codes(import_id)
    finally:
        await _cleanup_batch(external_batch_id)
        if history_external is not None:
            await _cleanup_batch(history_external)
        await _cleanup_registry(mapping_policy)


@pytest.mark.asyncio
async def test_postgres_i5_duplicate_revision_number_is_rejected_by_staging_identity() -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    logical_id = f"logical-duplicate-number-{suffix}"
    import_id, external_batch_id = await _seed_i5_batch_with_record(
        suffix=f"duplicate-number-{suffix}",
        mapping_policy=mapping_policy,
        logical_id=logical_id,
        revision_id=f"revision-one-{suffix}",
        seal=False,
    )
    try:
        # I2's immutable staging identity constraint rejects duplicate
        # (source, logical record, revision number) before sealing.
        conflicting = _record_for_batch(external_batch_id).model_copy(
            update={
                "external_logical_record_id": logical_id,
                "external_revision_id": f"revision-two-{suffix}",
                "revision_number": 1,
            }
        )
        with pytest.raises(ActualHarvestApiError) as exc_info:
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    await append_import_records(
                        session,
                        import_id,
                        ActualHarvestApiAppendRecordsRequest(records=(conflicting,)),
                    )
        assert exc_info.value.code.value == "REVISION_IDENTITY_CONFLICT"
        batch, persisted_count = await _batch_state(external_batch_id)
        assert batch.status == "UPLOADING"
        assert persisted_count == 1
        assert batch.record_count == batch.uploaded_record_count == 1
    finally:
        await _cleanup_batch(external_batch_id)
        await _cleanup_registry(mapping_policy)


@pytest.mark.asyncio
async def test_postgres_i5_same_revision_identity_different_payload_is_rejected_atomically() -> (
    None
):
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    import_id, external_batch_id = await _seed_batch(expected_record_count=1)
    try:
        record = _record_for_batch(external_batch_id).model_copy(
            update={
                "external_logical_record_id": f"logical-conflict-{suffix}",
                "external_revision_id": f"revision-conflict-{suffix}",
            }
        )
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await append_import_records(
                    session,
                    import_id,
                    ActualHarvestApiAppendRecordsRequest(records=(record,)),
                )
        conflicting = record.model_copy(update={"source_note": "different payload"})
        async with AsyncSessionMaker() as session:
            with pytest.raises(ActualHarvestApiError) as exc_info:
                async with session.begin():
                    await append_import_records(
                        session,
                        import_id,
                        ActualHarvestApiAppendRecordsRequest(records=(conflicting,)),
                    )
            assert exc_info.value.code.value == "REVISION_IDENTITY_CONFLICT"
        batch, persisted_count = await _batch_state(external_batch_id)
        assert persisted_count == 1
        assert batch.record_count == batch.uploaded_record_count == 1
    finally:
        await _cleanup_batch(external_batch_id)
        await _cleanup_registry(mapping_policy)


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


@pytest.mark.asyncio
async def test_postgres_i5_error_pagination_is_bounded_ordered_and_instance_bound() -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    first_id, first_external = await _seed_i5_batch_with_records(
        suffix=f"errors-first-{suffix}",
        mapping_policy=mapping_policy,
        record_specs=tuple(
            {
                "external_logical_record_id": f"logical-error-{suffix}-{index}",
                "external_revision_id": f"revision-error-{suffix}-{index}",
                "farm_code": f"unknown-farm-{index}",
                "variety_code": f"unknown-variety-{index}",
            }
            for index in range(3)
        ),
    )
    second_id, second_external = await _seed_i5_batch_with_record(
        suffix=f"errors-second-{suffix}",
        mapping_policy=mapping_policy,
        logical_id=f"logical-error-second-{suffix}",
        revision_id=f"revision-error-second-{suffix}",
        record_updates={
            "farm_code": "unknown-farm-second",
            "variety_code": "unknown-variety-second",
        },
    )
    try:
        first_result = await _validate_once(first_id)
        second_result = await _validate_once(second_id)
        assert (
            first_result.validation_status == second_result.validation_status == "VALIDATION_FAILED"
        )
        keys: list[tuple[int, str, str, str, str]] = []
        rows: list[dict[str, object]] = []
        token: str | None = None
        page_count = 0
        async with AsyncSessionMaker() as session:
            while True:
                summary, page, token = await validation_errors(
                    session, first_id, page_size=1, page_token=token
                )
                page_count += 1
                rows.extend(page)
                keys.extend(
                    (
                        row["record_index"],
                        row["external_logical_record_id"],
                        row["external_revision_id"],
                        row["field_path"] or "",
                        row["error_code"],
                    )
                    for row in page
                )
                if token is None:
                    break
            assert page_count > 1
            assert keys == sorted(keys)
            assert len(keys) == len(set(keys))
            assert all("id" not in row["details"] for row in rows)
            assert all("sql" not in str(row["details"]).lower() for row in rows)
            first_summary, first_page, first_token = await validation_errors(
                session, first_id, page_size=1, page_token=None
            )
            assert first_page and first_token is not None
            assert first_summary.validation_run_identity is not None
            with pytest.raises(ActualHarvestApiError) as foreign_info:
                await validation_errors(session, second_id, page_size=1, page_token=first_token)
            assert foreign_info.value.code.value == "API_REQUEST_INVALID"
            with pytest.raises(ActualHarvestApiError) as malformed_info:
                await validation_errors(session, first_id, page_size=1, page_token="not-a-token")
            assert malformed_info.value.code.value == "API_REQUEST_INVALID"
    finally:
        await _cleanup_batch(first_external)
        await _cleanup_batch(second_external)
        await _cleanup_registry(mapping_policy)


@pytest.mark.asyncio
async def test_postgres_i5_0019_catalog_and_registry_contract_is_exact() -> None:
    _require_postgres()
    suffix = uuid4().hex
    sealed_policy = await _seed_i5_registry(f"catalog-sealed-{suffix}")
    draft_policy = await _seed_i5_registry(f"catalog-draft-{suffix}", seal=False)

    index_names = (
        "ix_actual_harvest_mapping_entry_lookup",
        "ix_actual_harvest_validation_run_current",
        "uq_actual_harvest_validation_run_current",
        "ix_actual_harvest_validation_record_page",
        "ix_actual_harvest_validation_mapping_evidence_record",
        "ix_actual_harvest_validation_error_page",
        "ix_actual_harvest_validation_basis_member_sort",
    )
    expected_indexes = {
        "ix_actual_harvest_mapping_entry_lookup": (
            "actual_harvest_mapping_registry_entry",
            False,
            "(registry_id, source_field, source_code)",
            None,
        ),
        "ix_actual_harvest_validation_run_current": (
            "actual_harvest_validation_run",
            False,
            "(batch_id, is_current)",
            None,
        ),
        "uq_actual_harvest_validation_run_current": (
            "actual_harvest_validation_run",
            True,
            "(batch_id)",
            "is_current=true",
        ),
        "ix_actual_harvest_validation_record_page": (
            "actual_harvest_validation_record",
            False,
            "(validation_run_id, record_index)",
            None,
        ),
        "ix_actual_harvest_validation_mapping_evidence_record": (
            "actual_harvest_validation_mapping_evidence",
            False,
            "(validation_run_id, record_index)",
            None,
        ),
        "ix_actual_harvest_validation_error_page": (
            "actual_harvest_validation_error",
            False,
            "(validation_run_id, sort_key)",
            None,
        ),
        "ix_actual_harvest_validation_basis_member_sort": (
            "actual_harvest_validation_lineage_basis_member",
            False,
            "(basis_id, member_sort_key)",
            None,
        ),
    }
    try:
        async with AsyncSessionMaker() as session:
            rows = (
                (
                    await session.execute(
                        sa.text(
                            """
                        SELECT c.relname AS index_name, t.relname AS table_name,
                               i.indisunique, pg_get_indexdef(c.oid) AS indexdef,
                               pg_get_expr(i.indpred, i.indrelid) AS predicate
                        FROM pg_class c
                        JOIN pg_index i ON i.indexrelid = c.oid
                        JOIN pg_class t ON t.oid = i.indrelid
                        WHERE c.relname IN :names
                        """
                        ).bindparams(sa.bindparam("names", expanding=True)),
                        {"names": list(index_names)},
                    )
                )
                .mappings()
                .all()
            )
            actual_indexes = {row["index_name"]: row for row in rows}
            assert set(actual_indexes) == set(expected_indexes)
            for name, (table_name, unique, columns, predicate) in expected_indexes.items():
                row = actual_indexes[name]
                assert row["table_name"] == table_name
                assert bool(row["indisunique"]) is unique
                assert columns in row["indexdef"]
                actual_predicate = (row["predicate"] or "").replace(" ", "")
                while actual_predicate.startswith("(") and actual_predicate.endswith(")"):
                    actual_predicate = actual_predicate[1:-1]
                assert actual_predicate == (predicate or "").replace(" ", "")

            trigger_rows = (
                (
                    await session.execute(
                        sa.text(
                            """
                        SELECT tg.tgname, rel.relname AS table_name, proc.proname,
                               tg.tgtype, pg_get_triggerdef(tg.oid) AS triggerdef,
                               pg_get_functiondef(proc.oid) AS functiondef
                        FROM pg_trigger tg
                        JOIN pg_class rel ON rel.oid = tg.tgrelid
                        JOIN pg_proc proc ON proc.oid = tg.tgfoid
                        WHERE NOT tg.tgisinternal
                          AND tg.tgname IN (
                            'trg_actual_harvest_sealed_registry_immutable',
                            'trg_actual_harvest_sealed_registry_entry_immutable'
                          )
                        """
                        )
                    )
                )
                .mappings()
                .all()
            )
            triggers = {row["tgname"]: row for row in trigger_rows}
            assert set(triggers) == {
                "trg_actual_harvest_sealed_registry_immutable",
                "trg_actual_harvest_sealed_registry_entry_immutable",
            }
            registry_trigger = triggers["trg_actual_harvest_sealed_registry_immutable"]
            assert registry_trigger["table_name"] == "actual_harvest_mapping_policy_registry"
            assert registry_trigger["proname"] == "actual_harvest_reject_sealed_registry_mutation"
            assert registry_trigger["tgtype"] & 2 == 2
            assert registry_trigger["tgtype"] & 16 == 16
            assert registry_trigger["tgtype"] & 8 == 8
            assert "actual_harvest_mapping_policy_registry" in registry_trigger["triggerdef"]
            assert (
                "actual_harvest_reject_sealed_registry_mutation" in registry_trigger["functiondef"]
            )
            entry_trigger = triggers["trg_actual_harvest_sealed_registry_entry_immutable"]
            assert entry_trigger["table_name"] == "actual_harvest_mapping_registry_entry"
            assert entry_trigger["proname"] == (
                "actual_harvest_reject_sealed_registry_entry_mutation"
            )
            assert entry_trigger["tgtype"] & 2 == 2
            assert entry_trigger["tgtype"] & 4 == 4
            assert entry_trigger["tgtype"] & 16 == 16
            assert entry_trigger["tgtype"] & 8 == 8

            function_rows = (
                (
                    await session.execute(
                        sa.text(
                            """
                        SELECT proname, pg_get_functiondef(oid) AS functiondef
                        FROM pg_proc
                        WHERE proname IN (
                          'actual_harvest_reject_sealed_registry_mutation',
                          'actual_harvest_reject_sealed_registry_entry_mutation'
                        )
                        """
                        )
                    )
                )
                .mappings()
                .all()
            )
            assert {row["proname"] for row in function_rows} == {
                "actual_harvest_reject_sealed_registry_mutation",
                "actual_harvest_reject_sealed_registry_entry_mutation",
            }

        async def expect_rejected(statement: str, params: dict[str, object] | None = None) -> None:
            async with AsyncSessionMaker() as mutation_session:
                try:
                    async with mutation_session.begin():
                        await mutation_session.execute(sa.text(statement), params or {})
                except IntegrityError:
                    return
            raise AssertionError("sealed registry mutation was accepted")

        async with AsyncSessionMaker() as session:
            row = (
                await session.execute(
                    sa.text(
                        """
                    SELECT registry.id AS registry_id, entry.id AS entry_id
                    FROM actual_harvest_mapping_policy_registry registry
                    JOIN actual_harvest_mapping_registry_entry entry
                      ON entry.registry_id = registry.id
                    WHERE registry.mapping_policy_version = :policy
                    ORDER BY entry.id
                    LIMIT 1
                    """
                    ),
                    {"policy": sealed_policy},
                )
            ).first()
            assert row is not None
            registry_id, entry_id = row
        await expect_rejected(
            "UPDATE actual_harvest_mapping_policy_registry SET status = 'DRAFT' WHERE id = :id",
            {"id": registry_id},
        )
        await expect_rejected(
            "DELETE FROM actual_harvest_mapping_policy_registry WHERE id = :id",
            {"id": registry_id},
        )
        await expect_rejected(
            "INSERT INTO actual_harvest_mapping_registry_entry "
            "(registry_id, source_field, source_code, target_type, "
            "target_business_key, entry_hash) "
            "VALUES (:registry_id, 'farm_code', 'new', 'FARM', 'new', :hash)",
            {"registry_id": registry_id, "hash": "f" * 64},
        )
        await expect_rejected(
            "UPDATE actual_harvest_mapping_registry_entry "
            "SET source_code = 'changed' WHERE id = :id",
            {"id": entry_id},
        )
        await expect_rejected(
            "DELETE FROM actual_harvest_mapping_registry_entry WHERE id = :id",
            {"id": entry_id},
        )

        async with AsyncSessionMaker() as session:
            row = (
                await session.execute(
                    sa.text(
                        """
                        SELECT registry.id AS registry_id, entry.id AS entry_id
                        FROM actual_harvest_mapping_policy_registry registry
                        JOIN actual_harvest_mapping_registry_entry entry
                          ON entry.registry_id = registry.id
                        WHERE registry.mapping_policy_version = :policy
                        ORDER BY entry.id
                        LIMIT 1
                        """
                    ),
                    {"policy": draft_policy},
                )
            ).first()
            assert row is not None
            draft_registry_id, draft_entry_id = row
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await session.execute(
                    sa.text(
                        "UPDATE actual_harvest_mapping_registry_entry "
                        "SET source_code = 'draft-changed' WHERE id = :id"
                    ),
                    {"id": draft_entry_id},
                )
                await session.execute(
                    sa.text(
                        "UPDATE actual_harvest_mapping_policy_registry "
                        "SET entry_count = entry_count WHERE id = :id"
                    ),
                    {"id": draft_registry_id},
                )
    finally:
        await _cleanup_registry(sealed_policy)
        await _cleanup_registry(draft_policy)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "drift_kind",
    [
        pytest.param("wrong_fencing_token", id="wrong_fencing_token_cannot_finalize"),
        pytest.param("wrong_attempt_generation", id="wrong_attempt_generation_cannot_finalize"),
        pytest.param("expired_attempt", id="expired_attempt_cannot_finalize_without_reclaim"),
        pytest.param("committed_basis", id="committed_basis_drift_rejects_finalization"),
        pytest.param("registry", id="registry_hash_drift_rejects_finalization"),
        pytest.param("record_manifest", id="record_manifest_drift_rejects_finalization"),
        pytest.param("seal", id="seal_manifest_drift_rejects_finalization"),
    ],
)
async def test_postgres_i5_attempt_fencing_and_drift_matrix(drift_kind: str) -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    import_id, external_batch_id = await _seed_i5_batch_with_record(
        suffix=suffix,
        mapping_policy=mapping_policy,
        logical_id=f"logical-drift-{suffix}",
        revision_id=f"revision-drift-{suffix}",
    )
    try:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                start = await session.run_sync(
                    lambda sync_session: begin_validation(
                        sync_session, import_id=import_id, now=datetime.now(UTC)
                    )
                )
            assert start.run_id is not None and start.attempt_id is not None
            evidence = await session.run_sync(
                lambda sync_session: build_validation_evidence(
                    sync_session, run_id=start.run_id, attempt_id=start.attempt_id
                )
            )
            await session.rollback()

        if drift_kind in {"wrong_fencing_token", "wrong_attempt_generation", "expired_attempt"}:
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    attempt = await session.scalar(
                        sa.select(ActualHarvestValidationAttemptModel).where(
                            ActualHarvestValidationAttemptModel.attempt_id == start.attempt_id
                        )
                    )
                    assert attempt is not None
                    if drift_kind == "wrong_fencing_token":
                        evidence = replace(evidence, fencing_token="f" * 32)
                    elif drift_kind == "wrong_attempt_generation":
                        evidence = replace(
                            evidence,
                            attempt_generation=evidence.attempt_generation + 1,
                        )
                    else:
                        attempt.lease_expires_at = datetime(2000, 1, 1, tzinfo=UTC)
        elif drift_kind == "committed_basis":
            evidence = replace(evidence, committed_lineage_basis_hash="f" * 64)
        elif drift_kind == "registry":
            evidence = replace(evidence, registry_content_hash="f" * 64)
        elif drift_kind == "record_manifest":
            evidence = replace(evidence, record_manifest_hash="f" * 64)
        elif drift_kind == "seal":
            evidence = replace(evidence, seal_manifest_hash="f" * 64)

        async with AsyncSessionMaker() as session:
            async with session.begin():
                result = await session.run_sync(
                    lambda sync_session: finalize_validation(
                        sync_session, evidence=evidence, now=datetime.now(UTC)
                    )
                )
                assert result == "STALE"
            batch = await session.scalar(
                sa.select(ActualHarvestImportBatchModel).where(
                    ActualHarvestImportBatchModel.import_id == import_id
                )
            )
            expected_batch_status = (
                "VALIDATING" if drift_kind == "wrong_attempt_generation" else "SEALED"
            )
            assert batch is not None and batch.status == expected_batch_status
            assert (
                await session.scalar(
                    sa.select(sa.func.count()).select_from(ActualHarvestValidationResultModel)
                )
                == 0
            )
    finally:
        await _cleanup_batch(external_batch_id)
        await _cleanup_registry(mapping_policy)


@pytest.mark.asyncio
async def test_postgres_i5_injected_finalization_failure_writes_no_partial_evidence() -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    import_id, external_batch_id = await _seed_i5_batch_with_record(
        suffix=suffix,
        mapping_policy=mapping_policy,
        logical_id=f"logical-rollback-{suffix}",
        revision_id=f"revision-rollback-{suffix}",
    )
    try:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                start = await session.run_sync(
                    lambda sync_session: begin_validation(
                        sync_session, import_id=import_id, now=datetime.now(UTC)
                    )
                )
            evidence = await session.run_sync(
                lambda sync_session: build_validation_evidence(
                    sync_session, run_id=start.run_id, attempt_id=start.attempt_id
                )
            )
            await session.rollback()
            async with session.begin():
                await session.execute(
                    sa.text(
                        "UPDATE actual_harvest_validation_attempt "
                        "SET fencing_token = :fencing_token "
                        "WHERE attempt_id = :attempt_id"
                    ),
                    {"attempt_id": evidence.attempt_id, "fencing_token": "f" * 32},
                )
                result = await session.run_sync(
                    lambda sync_session: finalize_validation(
                        sync_session, evidence=evidence, now=datetime.now(UTC)
                    )
                )
                assert result == "STALE"
            await session.rollback()
            batch = await session.scalar(
                sa.select(ActualHarvestImportBatchModel).where(
                    ActualHarvestImportBatchModel.import_id == import_id
                )
            )
            assert batch is not None and batch.status == "SEALED"
            assert (
                await session.scalar(
                    sa.select(sa.func.count())
                    .select_from(ActualHarvestValidationResultModel)
                    .join(
                        ActualHarvestValidationRunModel,
                        ActualHarvestValidationRunModel.id
                        == ActualHarvestValidationResultModel.validation_run_id,
                    )
                    .where(ActualHarvestValidationRunModel.batch_id == batch.id)
                )
                == 0
            )
    finally:
        await _cleanup_batch(external_batch_id)
        await _cleanup_registry(mapping_policy)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["mapping", "lineage"])
async def test_postgres_i5_injected_evidence_failure_rolls_back_all_evidence(
    failure_kind: str,
) -> None:
    _require_postgres()
    suffix = uuid4().hex
    mapping_policy = await _seed_i5_registry(suffix)
    import_id, external_batch_id = await _seed_i5_batch(
        suffix=f"evidence-failure-{failure_kind}-{suffix}",
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
            async with session.begin():
                evidence = await session.run_sync(
                    lambda sync_session: build_validation_evidence(
                        sync_session,
                        run_id=start.run_id,
                        attempt_id=start.attempt_id,
                    )
                )
            if failure_kind == "mapping":
                evidence = replace(evidence, mapping_snapshot_hash="invalid")
            else:
                assert evidence.nodes
                nodes = (dict(evidence.nodes[0], node_hash="invalid"), *evidence.nodes[1:])
                evidence = replace(evidence, nodes=nodes)
            with pytest.raises(IntegrityError):
                async with session.begin():
                    await session.run_sync(
                        lambda sync_session: finalize_validation(
                            sync_session, evidence=evidence, now=datetime.now(UTC)
                        )
                    )
        async with AsyncSessionMaker() as session:
            batch = await session.scalar(
                sa.select(ActualHarvestImportBatchModel).where(
                    ActualHarvestImportBatchModel.import_id == import_id
                )
            )
            assert batch is not None and batch.status == "VALIDATING"
            assert (
                await session.scalar(
                    sa.select(sa.func.count())
                    .select_from(ActualHarvestValidationResultModel)
                    .join(
                        ActualHarvestValidationRunModel,
                        ActualHarvestValidationRunModel.id
                        == ActualHarvestValidationResultModel.validation_run_id,
                    )
                    .where(ActualHarvestValidationRunModel.batch_id == batch.id)
                )
                == 0
            )
    finally:
        await _cleanup_batch(external_batch_id)
        await _cleanup_registry(mapping_policy)


# ---------------------------------------------------------------------------
# v0.2-S1 atomic commit (PostgreSQL)
# ---------------------------------------------------------------------------


async def _s1_actor() -> ActualHarvestActorContext:
    """Build a fully-privileged commit actor for S1 tests."""
    return ActualHarvestActorContext(
        identity="operator-1",
        allowed_source_systems=frozenset({"i5-domain-1", "farm-system"}),
        allowed_channels=frozenset({ActualHarvestImportChannel.API}),
        may_commit=True,
    )


async def _current_run_instance_identity_hash(session: AsyncSession, import_id: str) -> str:
    """Read the current VALIDATED validation run's instance_identity_hash.

    Used by the S1 tests to discover the value that
    commit_batch() will require in its request body. Accepts an
    already-open AsyncSession (the test owns its caller-bound
    transaction) so the helper does NOT open a second session
    against the same connection pool. BatchModel source is the
    canonical models module (not validation_models), matching
    the rest of the file.
    """
    value = await session.scalar(
        sa.select(ActualHarvestValidationRunModel.instance_identity_hash)
        .join(
            ActualHarvestImportBatchModel,
            ActualHarvestValidationRunModel.batch_id == ActualHarvestImportBatchModel.id,
        )
        .where(
            ActualHarvestImportBatchModel.import_id == import_id,
            ActualHarvestValidationRunModel.is_current.is_(True),
        )
    )
    assert value is not None
    return value


async def _commit_once(import_id: str) -> CommitResult:
    """Invoke commit_batch on the given import and return the result.

    Each call opens its own caller-owned transaction. The batch must
    already be in VALIDATED state with a current validation run.
    """
    from backend.app.db.session import AsyncSessionMaker as _ASM

    async with _ASM() as session:
        async with session.begin():
            validation_run_instance_identity_hash = await _current_run_instance_identity_hash(
                session, import_id
            )
            return await _commit_service_fn(
                session,
                import_id=import_id,
                validation_run_instance_identity_hash=(validation_run_instance_identity_hash),
                actor=await _s1_actor(),
            )


async def _commit_or_error(
    import_id: str,
) -> tuple[str, object]:
    """B7 wrapper: invoke commit_once and capture either the
    successful CommitResult or the ActualHarvestApiError code.

    Returns ("ok", CommitResult) on success, ("error", error_code)
    on any ActualHarvestApiError raised by the commit service.
    """
    try:
        return ("ok", await _commit_once(import_id))
    except ActualHarvestApiError as exc:
        return ("error", exc.code)


# These tests exercise the S1 atomic commit contract against a real
# PostgreSQL database. They prove:
#   - commit vs commit produces exactly one manifest and is idempotent on
#     exact replay (zero additional write)
#   - cancel vs commit produces exactly one terminal outcome
#   - commit_manifest immutability is enforced by the PostgreSQL trigger
#   - sealed-or-committed import records cannot be mutated
#   - injected flush failures roll back the manifest + batch update
# They are tagged @pytest.mark.postgres and gated by
# RUN_POSTGRES_INTEGRATION=1 so the SQLite unit tests stay fast.


async def _s1_seed_validated_batch(*, suffix: str) -> tuple[str, str]:
    """Seed a fully-validated batch (registry + batch + records +
    validation_run + validation_result + mapping_snapshot) so the
    commit service can be invoked against it.

    Reuses `_seed_i5_registry` so the mapping policy is actually
    registered (and sealed) in the mapping_policy_registry / entries
    tables before validation looks it up. Previously this helper built
    a synthetic `s1-mapping-{suffix}` string that was never inserted
    into the registry, causing
    "mapping policy version is not registered" during `_validate_once`.
    """
    mapping_policy = await _seed_i5_registry(suffix)
    import_id, external_batch_id = await _seed_i5_batch(
        suffix=suffix, mapping_policy=mapping_policy
    )
    await _validate_once(import_id)
    return import_id, external_batch_id


@pytest.mark.asyncio
async def test_postgres_s1_commit_vs_commit_produces_one_manifest() -> None:
    """B6: Two CONCURRENT commits on the same batch must produce exactly
    one manifest row. The race is started by ``_race_two`` which opens
    two independent session/transactions via two ``_commit_once`` calls;
    the second call must observe the first's commit and return
    reused_existing_commit=True with the same commit_manifest_hash.

    This is the real serialisation proof — not a sequential exact
    replay (that contract is owned by
    ``test_postgres_s1_commit_vs_commit_does_not_write_additional_manifest``).
    """
    _require_postgres()
    suffix = uuid4().hex
    import_id, external_batch_id = await _s1_seed_validated_batch(suffix=suffix)

    first_result, second_result = await _race_two(
        lambda: _commit_once(import_id),
        lambda: _commit_once(import_id),
    )

    # Both calls must have succeeded.
    assert isinstance(first_result, CommitResult)
    assert isinstance(second_result, CommitResult)
    # Exactly one of them is the original commit; the other is a
    # zero-write exact replay. Order is non-deterministic.
    flags = sorted(
        [bool(first_result.reused_existing_commit), bool(second_result.reused_existing_commit)]
    )
    assert flags == [False, True], (
        f"expected exactly one fresh + one replay commit, got flags={flags}"
    )
    # Both must attest the same commit_manifest_hash.
    assert first_result.commit_manifest_hash == second_result.commit_manifest_hash

    # Exactly one manifest row in the database, and the batch must
    # be in COMMITTED state with the correct record count.
    async with AsyncSessionMaker() as session:
        manifest_count = await session.scalar(
            sa.select(sa.func.count())
            .select_from(ActualHarvestCommitManifestModel)
            .join(
                ActualHarvestImportBatchModel,
                ActualHarvestCommitManifestModel.batch_id == ActualHarvestImportBatchModel.id,
            )
            .where(ActualHarvestImportBatchModel.import_id == import_id)
        )
    assert manifest_count == 1

    batch, record_count = await _batch_state(external_batch_id)
    assert batch.status == ActualHarvestImportBatchStatus.COMMITTED.value
    assert batch.committed_record_count == batch.record_count
    assert record_count == batch.record_count


@pytest.mark.asyncio
async def test_postgres_s1_commit_vs_commit_does_not_write_additional_manifest() -> None:
    """After the first commit, the second commit must not add a second
    manifest row (zero write on exact replay). Combined with the
    previous test this proves the count stays at 1 across replays.
    """
    _require_postgres()
    suffix = uuid4().hex
    import_id, _ = await _s1_seed_validated_batch(suffix=suffix)
    await _commit_once(import_id)
    await _commit_once(import_id)
    await _commit_once(import_id)
    async with AsyncSessionMaker() as session:
        manifest_count = await session.scalar(
            sa.select(sa.func.count())
            .select_from(ActualHarvestCommitManifestModel)
            .join(
                ActualHarvestImportBatchModel,
                ActualHarvestCommitManifestModel.batch_id == ActualHarvestImportBatchModel.id,
            )
            .where(ActualHarvestImportBatchModel.import_id == import_id)
        )
    assert manifest_count == 1


@pytest.mark.asyncio
async def test_postgres_s1_cancel_then_commit_produces_one_terminal_outcome() -> None:
    """B7: CONCURRENT cancel vs commit on a VALIDATED batch must
    produce exactly one terminal outcome, serialized by the
    batch row lock. The race is started by ``_race_two`` so the
    two operations run on independent session/transactions.

    Only two outcomes are legal:
      - COMMITTED wins: batch.status == COMMITTED, manifest_count == 1,
        commit returns ("ok", ...), cancel returns ("error", code).
      - CANCELLED wins: batch.status == CANCELLED, manifest_count == 0,
        cancel returns ("ok", ...), commit returns
        ("error", IMPORT_BATCH_NOT_VALIDATED).
    """
    _require_postgres()
    suffix = uuid4().hex
    import_id, external_batch_id = await _s1_seed_validated_batch(suffix=suffix)

    cancel_result, commit_result = await _race_two(
        lambda: _cancel_once(import_id),
        lambda: _commit_or_error(import_id),
    )

    # The race returns ("ok", batch) for cancel and ("ok", CommitResult)
    # for commit-or ("error", code) for any error.
    cancel_outcome, cancel_payload = cancel_result
    commit_outcome, commit_payload = commit_result
    assert cancel_outcome in {"ok", "error"}
    assert commit_outcome in {"ok", "error"}

    # Re-read final state and manifest count.
    batch, record_count = await _batch_state(external_batch_id)
    async with AsyncSessionMaker() as session:
        manifest_count = await session.scalar(
            sa.select(sa.func.count())
            .select_from(ActualHarvestCommitManifestModel)
            .where(
                ActualHarvestCommitManifestModel.batch_id
                == await session.scalar(
                    sa.select(ActualHarvestImportBatchModel.id).where(
                        ActualHarvestImportBatchModel.import_id == import_id
                    )
                )
            )
        )

    if batch.status == ActualHarvestImportBatchStatus.COMMITTED.value:
        # COMMITTED won.
        assert commit_outcome == "ok", (
            f"expected commit ok when batch is COMMITTED, got {commit_result!r}"
        )
        assert cancel_outcome == "error", (
            f"expected cancel to be rejected when batch is COMMITTED, got {cancel_result!r}"
        )
        assert manifest_count == 1
        assert batch.committed_record_count == batch.record_count
        assert record_count == batch.record_count
    elif batch.status == ActualHarvestImportBatchStatus.CANCELLED.value:
        # CANCELLED won.
        assert cancel_outcome == "ok", (
            f"expected cancel ok when batch is CANCELLED, got {cancel_result!r}"
        )
        assert commit_outcome == "error", (
            f"expected commit to be rejected when batch is CANCELLED, got {commit_result!r}"
        )
        assert commit_payload == ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_VALIDATED, (
            f"expected IMPORT_BATCH_NOT_VALIDATED, got {commit_payload!r}"
        )
        assert manifest_count == 0
    else:
        raise AssertionError(
            f"batch must be in a terminal state after race, got status={batch.status!r}"
        )


@pytest.mark.asyncio
async def test_postgres_s1_commit_manifest_update_rejected() -> None:
    """B8: The commit_manifest immutability trigger must reject direct
    UPDATE on the manifest table with EXACT SQLSTATE 23514 and the
    full server message "actual-harvest commit manifest is immutable".
    Substring matching is not sufficient.
    """
    _require_postgres()
    suffix = uuid4().hex
    import_id, _ = await _s1_seed_validated_batch(suffix=suffix)
    result = await _commit_once(import_id)

    async with AsyncSessionMaker() as session:
        async with session.begin():
            with pytest.raises(DBAPIError) as excinfo:
                await session.execute(
                    sa.text(
                        "UPDATE actual_harvest_commit_manifest "
                        "SET committed_record_count = 99 "
                        "WHERE commit_manifest_hash = :h"
                    ),
                    {"h": result.commit_manifest_hash},
                )
        chain = _chain_exceptions(excinfo.value)
        sqlstate = next(
            (s for e in chain if (s := _extract_sqlstate(e))),
            None,
        )
        message = next(
            (m for e in chain if (m := _extract_server_message(e))),
            "",
        )
        assert sqlstate == "23514", (
            f"expected SQLSTATE 23514 from manifest UPDATE trigger, "
            f"got sqlstate={sqlstate!r} message={message!r}"
        )
        assert message == "actual-harvest commit manifest is immutable", (
            f"expected exact server message, got {message!r}"
        )


@pytest.mark.asyncio
async def test_postgres_s1_commit_manifest_delete_rejected() -> None:
    """B8: The commit_manifest immutability trigger must reject direct
    DELETE on the manifest table with EXACT SQLSTATE 23514 and the
    full server message "actual-harvest commit manifest is immutable".
    """
    _require_postgres()
    suffix = uuid4().hex
    import_id, _ = await _s1_seed_validated_batch(suffix=suffix)
    result = await _commit_once(import_id)

    async with AsyncSessionMaker() as session:
        async with session.begin():
            with pytest.raises(DBAPIError) as excinfo:
                await session.execute(
                    sa.text(
                        "DELETE FROM actual_harvest_commit_manifest WHERE commit_manifest_hash = :h"
                    ),
                    {"h": result.commit_manifest_hash},
                )
        chain = _chain_exceptions(excinfo.value)
        sqlstate = next(
            (s for e in chain if (s := _extract_sqlstate(e))),
            None,
        )
        message = next(
            (m for e in chain if (m := _extract_server_message(e))),
            "",
        )
        assert sqlstate == "23514", (
            f"expected SQLSTATE 23514 from manifest DELETE trigger, "
            f"got sqlstate={sqlstate!r} message={message!r}"
        )
        assert message == "actual-harvest commit manifest is immutable", (
            f"expected exact server message, got {message!r}"
        )


@pytest.mark.asyncio
async def test_postgres_s1_committed_record_update_rejected() -> None:
    """B8: A committed import record must be immutable. Both UPDATE and
    DELETE on a record whose parent batch is COMMITTED/SEALED/VALIDATED
    are rejected by the database-level trigger with EXACT SQLSTATE 23514
    and the full server message
    "actual-harvest import record is immutable after seal".

    The two operations are run on independent session/transactions
    because the first failure aborts the current PostgreSQL transaction.
    """
    _require_postgres()
    suffix = uuid4().hex
    import_id, _ = await _s1_seed_validated_batch(suffix=suffix)
    await _commit_once(import_id)

    # Resolve a real record PK (NOT source_row_number, which is
    # server-owned/NULL under the API transport path, and would
    # silently match zero rows and bypass the immutability trigger).
    async with AsyncSessionMaker() as session:
        record_id = await session.scalar(
            sa.select(ActualHarvestImportRecordModel.id)
            .join(
                ActualHarvestImportBatchModel,
                ActualHarvestImportRecordModel.batch_id == ActualHarvestImportBatchModel.id,
            )
            .where(ActualHarvestImportBatchModel.import_id == import_id)
            .order_by(ActualHarvestImportRecordModel.id)
            .limit(1)
        )
    assert record_id is not None, f"no committed record found for import_id={import_id!r}"

    # UPDATE on the committed record. Uses an independent session/
    # transaction because the failure aborts the current PostgreSQL
    # transaction; assertions must run on the rejected excinfo.
    async with AsyncSessionMaker() as session:
        async with session.begin():
            with pytest.raises(DBAPIError) as excinfo:
                await session.execute(
                    sa.text(
                        "UPDATE actual_harvest_import_record "
                        "SET actual_harvest_quantity_kg = 0 "
                        "WHERE id = :record_id"
                    ),
                    {"record_id": record_id},
                )
        chain = _chain_exceptions(excinfo.value)
        sqlstate = next(
            (s for e in chain if (s := _extract_sqlstate(e))),
            None,
        )
        message = next(
            (m for e in chain if (m := _extract_server_message(e))),
            "",
        )
        assert sqlstate == "23514", (
            f"expected SQLSTATE 23514 from record UPDATE trigger, "
            f"got sqlstate={sqlstate!r} message={message!r}"
        )
        assert message == "actual-harvest import record is immutable after seal", (
            f"expected exact server message, got {message!r}"
        )

    # DELETE on the committed record. Use a NEW session because the
    # UPDATE's failure aborted the previous PostgreSQL transaction.
    async with AsyncSessionMaker() as session:
        async with session.begin():
            with pytest.raises(DBAPIError) as excinfo:
                await session.execute(
                    sa.text("DELETE FROM actual_harvest_import_record WHERE id = :record_id"),
                    {"record_id": record_id},
                )
        chain = _chain_exceptions(excinfo.value)
        sqlstate = next(
            (s for e in chain if (s := _extract_sqlstate(e))),
            None,
        )
        message = next(
            (m for e in chain if (m := _extract_server_message(e))),
            "",
        )
        assert sqlstate == "23514", (
            f"expected SQLSTATE 23514 from record DELETE trigger, "
            f"got sqlstate={sqlstate!r} message={message!r}"
        )
        assert message == "actual-harvest import record is immutable after seal", (
            f"expected exact server message, got {message!r}"
        )


@pytest.mark.asyncio
async def test_postgres_s1_post_manifest_insert_failure_rolls_back() -> None:
    """B4: When a flush failure is injected AFTER the commit_manifest
    INSERT fires, the caller-owned transaction must roll back atomically:
    the batch stays in VALIDATED state with committed_record_count=0
    and committed_at_or_null=NULL, and no commit_manifest row remains.

    The injection point is ``after_insert`` on ActualHarvestCommitManifestModel
    so the failure proves a post-INSERT transaction-context unwinds
    correctly (a ``before_insert`` listener would only prove the
    listener fires before the INSERT, not that the row is present in
    the transaction and then rolled back).
    """
    _require_postgres()
    suffix = uuid4().hex
    import_id, external_batch_id = await _s1_seed_validated_batch(suffix=suffix)

    from sqlalchemy import event as _sa_event

    def _explode_after_manifest_insert(
        _mapper: object, _connection: object, target: object
    ) -> None:
        if isinstance(target, ActualHarvestCommitManifestModel):
            raise RuntimeError("simulated post-manifest insert failure")

    _sa_event.listen(
        ActualHarvestCommitManifestModel,
        "after_insert",
        _explode_after_manifest_insert,
    )
    try:
        # The pytest.raises must wrap the transaction context so the
        # failure's transaction-context unwind is the proof of rollback.
        with pytest.raises(RuntimeError, match="simulated post-manifest insert failure"):
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    validation_hash = await _current_run_instance_identity_hash(session, import_id)
                    await _commit_service_fn(
                        session,
                        import_id=import_id,
                        validation_run_instance_identity_hash=validation_hash,
                        actor=await _s1_actor(),
                    )
    finally:
        _sa_event.remove(
            ActualHarvestCommitManifestModel,
            "after_insert",
            _explode_after_manifest_insert,
        )

    # After the failure, the batch must still be in VALIDATED, no
    # commit_manifest row should exist, and committed_at_or_null
    # must remain NULL (B4 explicitly requires this).
    batch, record_count = await _batch_state(external_batch_id)
    assert batch.status == ActualHarvestImportBatchStatus.VALIDATED.value
    assert batch.committed_record_count == 0
    assert batch.committed_at_or_null is None
    assert record_count == batch.record_count

    async with AsyncSessionMaker() as session:
        manifest_count = await session.scalar(
            sa.select(sa.func.count())
            .select_from(ActualHarvestCommitManifestModel)
            .where(
                ActualHarvestCommitManifestModel.batch_id
                == await session.scalar(
                    sa.select(ActualHarvestImportBatchModel.id).where(
                        ActualHarvestImportBatchModel.import_id == import_id
                    )
                )
            )
        )
    assert manifest_count == 0


@pytest.mark.asyncio
async def test_postgres_i5_module_cleanup_releases_master_ids_for_downstream_suites() -> None:
    """Prove this module releases committed fixtures for the shared canary DB."""
    _require_postgres()
    suffix = uuid4().hex
    leaked_policy = await _seed_i5_registry(f"cleanup-leak-{suffix}")
    import_id, _external_batch_id = await _seed_i5_batch(
        suffix=f"cleanup-leak-{suffix}",
        mapping_policy=leaked_policy,
    )
    validation = await _validate_once(import_id)
    assert validation.validation_status == "VALIDATED"

    before_counts = await _i5_module_table_counts()
    for table_name in (
        "actual_harvest_import_batch",
        "actual_harvest_mapping_policy_registry",
        "actual_harvest_validation_run",
        "actual_harvest_validation_result",
        "actual_harvest_mapping_snapshot",
        "actual_harvest_validation_mapping_evidence",
        "dim_subfarm",
        "dim_variety",
        "dim_farm",
        "dim_season",
    ):
        assert before_counts[table_name] > 0

    await _truncate_i5_module_database()
    first_cleanup_counts = await _i5_module_table_counts()
    assert all(value == 0 for value in first_cleanup_counts.values())

    await _truncate_i5_module_database()
    second_cleanup_counts = await _i5_module_table_counts()
    assert second_cleanup_counts == first_cleanup_counts

    fixed_registry_policy = f"cleanup-fixed-{suffix}"
    async with AsyncSessionMaker() as session:
        async with session.begin():
            session.add_all(
                [
                    Farm(id=1, name="downstream-farm"),
                    Season(
                        id=1,
                        code="downstream-season",
                        start_date=date(2026, 1, 1),
                        end_date=date(2026, 12, 31),
                    ),
                    Variety(id=101, code="downstream-variety", name="Downstream Variety"),
                    Subfarm(id=1, farm_id=1, name="downstream-subfarm"),
                ]
            )

    async with AsyncSessionMaker() as session:
        async with session.begin():
            await session.run_sync(
                lambda sync_session: create_mapping_registry(
                    sync_session,
                    registry_version=f"cleanup-registry-{suffix}",
                    source_system="farm-system",
                    mapping_policy_version=fixed_registry_policy,
                    entries=(
                        {
                            "source_field": "season_code",
                            "source_code": "2026",
                            "target_type": "SEASON",
                            "target_business_key": "downstream-season",
                        },
                        {
                            "source_field": "farm_code",
                            "source_code": "farm-1",
                            "target_type": "FARM",
                            "target_business_key": "downstream-farm",
                        },
                        {
                            "source_field": "subfarm_or_plot_code",
                            "source_code": "plot-1",
                            "target_type": "SUBFARM",
                            "target_business_key": "downstream-subfarm",
                            "target_parent_business_key": "downstream-farm",
                        },
                        {
                            "source_field": "variety_code",
                            "source_code": "variety-1",
                            "target_type": "VARIETY",
                            "target_business_key": "downstream-variety",
                        },
                    ),
                    now=datetime.now(UTC),
                )
            )
            await session.run_sync(
                lambda sync_session: seal_mapping_registry(
                    sync_session,
                    mapping_policy_version=fixed_registry_policy,
                    now=datetime.now(UTC),
                )
            )

    async with AsyncSessionMaker() as session:
        registry = await session.scalar(
            sa.select(ActualHarvestMappingPolicyRegistryModel).where(
                ActualHarvestMappingPolicyRegistryModel.mapping_policy_version
                == fixed_registry_policy
            )
        )
        assert registry is not None and registry.status == "SEALED"
        entry = await session.scalar(
            sa.select(ActualHarvestMappingRegistryEntryModel).where(
                ActualHarvestMappingRegistryEntryModel.registry_id == registry.id
            )
        )
        assert entry is not None
        registry_id = registry.id
        entry_id = entry.id

        trigger_rows = (
            await session.execute(
                sa.text(
                    "SELECT t.tgname, p.proname "
                    "FROM pg_trigger AS t "
                    "JOIN pg_class AS c ON c.oid = t.tgrelid "
                    "JOIN pg_proc AS p ON p.oid = t.tgfoid "
                    "WHERE NOT t.tgisinternal "
                    "AND t.tgname IN ("
                    "'trg_actual_harvest_sealed_registry_immutable', "
                    "'trg_actual_harvest_sealed_registry_entry_immutable')"
                )
            )
        ).all()
        assert dict(trigger_rows) == {
            "trg_actual_harvest_sealed_registry_immutable": (
                "actual_harvest_reject_sealed_registry_mutation"
            ),
            "trg_actual_harvest_sealed_registry_entry_immutable": (
                "actual_harvest_reject_sealed_registry_entry_mutation"
            ),
        }

    await _assert_i5_trigger_rejects(
        "UPDATE actual_harvest_mapping_policy_registry "
        "SET entry_count = entry_count WHERE id = :id",
        {"id": registry_id},
        expected_message=REGISTRY_TRIGGER_MESSAGE,
    )
    await _assert_i5_trigger_rejects(
        "DELETE FROM actual_harvest_mapping_policy_registry WHERE id = :id",
        {"id": registry_id},
        expected_message=REGISTRY_TRIGGER_MESSAGE,
    )
    await _assert_i5_trigger_rejects(
        "INSERT INTO actual_harvest_mapping_registry_entry "
        "(registry_id, source_field, source_code, target_type, "
        "target_business_key, entry_hash) "
        "VALUES (:registry_id, 'farm_code', 'forbidden', 'FARM', "
        "'downstream-farm', :entry_hash)",
        {"registry_id": registry_id, "entry_hash": "a" * 64},
        expected_message=ENTRY_TRIGGER_MESSAGE,
    )
    await _assert_i5_trigger_rejects(
        "UPDATE actual_harvest_mapping_registry_entry SET source_code = 'forbidden' WHERE id = :id",
        {"id": entry_id},
        expected_message=ENTRY_TRIGGER_MESSAGE,
    )
    await _assert_i5_trigger_rejects(
        "DELETE FROM actual_harvest_mapping_registry_entry WHERE id = :id",
        {"id": entry_id},
        expected_message=ENTRY_TRIGGER_MESSAGE,
    )

    async with AsyncSessionMaker() as session:
        assert (
            await session.scalar(sa.select(sa.func.count()).select_from(Farm).where(Farm.id == 1))
            == 1
        )
        assert (
            await session.scalar(
                sa.select(sa.func.count())
                .select_from(Subfarm)
                .where(Subfarm.id == 1, Subfarm.farm_id == 1)
            )
            == 1
        )
        assert (
            await session.scalar(
                sa.select(sa.func.count()).select_from(Season).where(Season.id == 1)
            )
            == 1
        )
        assert (
            await session.scalar(
                sa.select(sa.func.count()).select_from(Variety).where(Variety.id == 101)
            )
            == 1
        )


# PR #117 formal review B1 fix: negative acceptance.
# The deterministic-attribution contract is enforced by re-raising any
# DBAPIError that does not match BOTH the SQLSTATE (23514) AND the
# expected server primary message. The negative cases below exercise
# (a) a different SQLSTATE (22012 — division by zero) and (b) the SAME
# SQLSTATE 23514 with a wrong message ("unrelated check violation"),
# proving that SQLSTATE alone is insufficient and that broad substring
# matching of "immutable" cannot masquerade as expected behaviour.
#
# The negative cases run BEFORE any per-test sealed-registry seeding
# so they exercise the helper in isolation against the shared
# postgres-domain-1 isolated database, without depending on
# module-scoped fixture data. The final positive rejection uses an
# ad-hoc sealed registry seeded with a uuid-suffixed mapping policy
# rather than the standard _seed_i5_registry helper, so this test does
# not depend on or mutate dim_farm / dim_season / dim_variety /
# dim_subfarm master rows that other modules in the shard rely on.
async def _probe_helper_extracts_real_sqlstate_and_message() -> tuple[str, str]:
    """Round-trip an asyncpg DBAPIError through the helper extractors.

    This guarantees the helper introspects the *real* SQLAlchemy +
    asyncpg exception chain (sqlstate attribute on the asyncpg error and
    message attribute on the same), rather than a fabricated mock. The
    probe deliberately targets a deterministic PostgreSQL error so the
    extraction can be asserted with exact values, not runner-specific
    repr or memory addresses.
    """

    async with AsyncSessionMaker() as session:
        try:
            async with session.begin():
                await session.execute(sa.text("SELECT 1 / 0"))
        except DBAPIError as exc:
            sqlstate = _extract_sqlstate(exc)
            server_message = _extract_server_message(exc)
            return sqlstate or "", server_message or ""
    raise AssertionError("probe did not produce a DBAPIError; SQLAlchemy+asyncpg chain unreachable")


async def _b1_seed_sealed_registry() -> int:
    """Seed a sealed mapping registry without touching master data tables.

    The standard I5 test helpers insert Farm / Season / Variety /
    Subfarm master rows and rely on autoincrement for their primary
    keys. The postgres-domain-1 isolated database is shared across
    many tests, so a primary-key collision on dim_farm (id=1) is
    likely after the I5 module cleanup has run. This helper inserts
    a sealed mapping registry + entry without any master-data
    dependency, so the post-cleanup shared database is never
    expected to have collisions on Farm.id=1.
    """

    suffix = uuid4().hex
    mapping_policy = f"b1-negative-acceptance-{suffix}"
    registry_version = f"b1-negative-acceptance-registry-{suffix}"
    source_system = "b1-negative-acceptance"

    async with AsyncSessionMaker() as session:
        async with session.begin():
            await session.run_sync(
                lambda sync_session: _b1_create_sealed_registry_sync(
                    sync_session,
                    mapping_policy=mapping_policy,
                    registry_version=registry_version,
                    source_system=source_system,
                )
            )

    async with AsyncSessionMaker() as session:
        registry_id = await session.scalar(
            sa.select(ActualHarvestMappingPolicyRegistryModel.id).where(
                ActualHarvestMappingPolicyRegistryModel.mapping_policy_version == mapping_policy
            )
        )
    assert registry_id is not None
    return registry_id


def _b1_create_sealed_registry_sync(
    sync_session, *, mapping_policy: str, registry_version: str, source_system: str
) -> None:
    """Insert a sealed registry + entry, no master-data writes.

    The entry uses target_business_key + target_type only; the
    sealed-registry trigger does not require the target to exist in
    any master-data table, so the entry insertion is sufficient for
    the B1 acceptance test to issue a real sealed-registry UPDATE
    rejection.
    """

    from backend.app.actual_harvest_import.validation_service import (
        create_mapping_registry,
        seal_mapping_registry,
    )

    create_mapping_registry(
        sync_session,
        registry_version=registry_version,
        source_system=source_system,
        mapping_policy_version=mapping_policy,
        entries=(
            {
                "source_field": "b1_negative_source",
                "source_code": f"b1-negative-{uuid4().hex}",
                "target_type": "SEASON",
                "target_business_key": f"b1-negative-{uuid4().hex}",
            },
        ),
        now=datetime.now(UTC),
    )
    seal_mapping_registry(
        sync_session, mapping_policy_version=mapping_policy, now=datetime.now(UTC)
    )


@pytest.mark.asyncio
async def test_postgres_i5_trigger_rejection_helper_rejects_unrelated_dbapi_errors() -> None:
    """B1 negative acceptance: the helper must re-raise unrelated DBAPIError.

    Two independent negative cases are exercised:
    Case A — different SQLSTATE (22012 division by zero). The helper MUST
    re-raise the DBAPIError because the SQLSTATE does not match 23514.
    Case B — same SQLSTATE 23514 with a wrong message ("unrelated check
    violation" raised by a DO block). The helper MUST re-raise because
    the server message does not match the expected sealed-registry
    message. This proves that SQLSTATE 23514 alone is insufficient and
    broad substring matching of "immutable" cannot pass.

    The test also asserts that the real SQLAlchemy + asyncpg exception
    chain exposes sqlstate and message attributes used by the
    deterministic-attribution helpers (no mock-based evidence).

    After both negative cases aborted their transactions, a final
    positive rejection against a real sealed registry (seeded by this
    test, not by the module fixture) verifies that the helper
    continues to enforce the deterministic-attribution contract and
    that no aborted-transaction state leaked between cases.
    """

    _require_postgres()

    # Round-trip a real DBAPIError through the helper extractors so the
    # assertion below does not rely on runner-specific repr, memory
    # addresses, or full exception wrappers.
    probe_sqlstate, probe_message = await _probe_helper_extracts_real_sqlstate_and_message()
    assert probe_sqlstate == "22012", (
        "expected SQLSTATE 22012 from SELECT 1 / 0, "
        f"helper extracted sqlstate={probe_sqlstate!r} message={probe_message!r}"
    )
    assert probe_message, (
        "expected a non-empty server primary message from SELECT 1 / 0, "
        f"helper extracted message={probe_message!r}"
    )

    # Case A — different SQLSTATE; helper must re-raise the DBAPIError.
    with pytest.raises(DBAPIError):
        await _assert_i5_trigger_rejects(
            "SELECT 1 / 0",
            {},
            expected_message=REGISTRY_TRIGGER_MESSAGE,
        )

    # Case B — same SQLSTATE 23514 with a different message; helper
    # must re-raise the DBAPIError. The DO block deliberately raises a
    # check_violation with a non-sealed-registry message so we can
    # prove the message discriminator is doing real work.
    with pytest.raises(DBAPIError):
        await _assert_i5_trigger_rejects(
            "DO $$\n"
            "BEGIN\n"
            "RAISE EXCEPTION 'unrelated check violation'\n"
            "USING ERRCODE = 'check_violation';\n"
            "END\n"
            "$$",
            {},
            expected_message=REGISTRY_TRIGGER_MESSAGE,
        )

    # Final positive check: a real sealed-registry UPDATE rejection
    # must still be accepted by the helper, proving no aborted
    # transaction state leaked and the deterministic-attribution
    # contract is unchanged after the negative cases.
    registry_id = await _b1_seed_sealed_registry()
    await _assert_i5_trigger_rejects(
        "UPDATE actual_harvest_mapping_policy_registry "
        "SET entry_count = entry_count WHERE id = :id",
        {"id": registry_id},
        expected_message=REGISTRY_TRIGGER_MESSAGE,
    )
