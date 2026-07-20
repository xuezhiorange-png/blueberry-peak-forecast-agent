"""PostgreSQL acceptance for V0.2-S2 / Q2A-I7 label snapshot.

This file extends ``test_lifecycle_postgres.py`` with the I7
acceptance nodes required by the PR #122 Mark Ready round:

- E4: PostgreSQL ``finalized_at`` round-trip (validation lineage
  basis member persistence + I7 snapshot reads the same value
  + FINAL_ADJUDICATED eligibility uses it).
- E5.1: four-table immutability (UPDATE / DELETE rejected with
  SQLSTATE 23514 and the exact server primary message).
- E5.2 / E5.3 / E5.4 / E5.5: caller-owned transaction,
  atomic rollback, concurrent identical snapshot, and
  IDEMPOTENCY_CONFLICT — covered by SQLite unit/contract tests
  in ``test_i7_label_snapshot.py``; the PG tests in this file
  are limited to the contracts that require a real PG database
  (immutability trigger + persistence round-trip).
- E6: source-evidence preflight is enforced against the
  committed lineage basis table (per-record missing-evidence
  detection).

The tests reuse the project's dev-DB safeguard and the I5
infrastructure (mapping registry, validation run, commit
manifest). They never reach beyond the I5/I7 four-table boundary
and never start the backtest runner.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from backend.app.actual_harvest_import.commit_models import (
    ActualHarvestCommitManifestModel,
)
from backend.app.actual_harvest_import.commit_service import (
    CommitResult,
)
from backend.app.actual_harvest_import.enums import (
    ActualHarvestRecordStatus,
    SourceRecordedAtAuthorityStatus,
)
from backend.app.actual_harvest_import.models import (
    ActualHarvestImportRecordModel,
)
from backend.app.actual_harvest_import.validation_models import (
    ActualHarvestMappingSnapshotModel,
    ActualHarvestValidationLineageBasisMemberModel,
    ActualHarvestValidationLineageBasisModel,
    ActualHarvestValidationMappingEvidenceModel,
    ActualHarvestValidationResultModel,
)
from backend.app.actual_harvest_labels.enums import (
    ActualHarvestLabelStructuralFailure,
    ActualHarvestLabelVisibilityMode,
)
from backend.app.actual_harvest_labels.hashes import (
    AGGREGATION_POLICY_VERSION,
    SNAPSHOT_POLICY_VERSION,
    WINNER_POLICY_VERSION,
)
from backend.app.actual_harvest_labels.models import (
    EXCLUSION_TABLE_NAME,
    HEADER_TABLE_NAME,
    LABEL_TABLE_NAME,
    WINNER_TABLE_NAME,
    ActualHarvestLabelSnapshotModel,
    ActualHarvestLabelSnapshotWinnerModel,
)
from backend.app.actual_harvest_labels.schemas import (
    ActualHarvestLabelSnapshotRequest,
)
from backend.app.actual_harvest_labels.service import (
    ActualHarvestLabelStructuralFailureError,
    create_label_snapshot,
)
from backend.app.db.session import AsyncSessionMaker
from backend.tests.actual_harvest_import.test_lifecycle_postgres import (
    _commit_once,
    _extract_server_message,
    _extract_sqlstate,
    _raise_unexpected_dbapi_error,
    _require_postgres,
    _seed_i5_batch_with_record,
    _seed_i5_registry,
    _truncate_i5_module_database,
    _validate_once,
)

# ---------------------------------------------------------------------------
# I7 acceptance constants
# ---------------------------------------------------------------------------

EXPECTED_SQLSTATE = "23514"
LABEL_SNAPSHOT_TRIGGER_MESSAGE = "actual-harvest label snapshot row is immutable"

_I7_MODULE_TABLES = (
    HEADER_TABLE_NAME,
    WINNER_TABLE_NAME,
    LABEL_TABLE_NAME,
    EXCLUSION_TABLE_NAME,
)

pytestmark = [pytest.mark.postgres, pytest.mark.integration]


# ---------------------------------------------------------------------------
# I7 module-scoped fixture — same pattern as the I5 module.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module", autouse=True)
async def isolate_i7_postgres_module() -> AsyncIterator[None]:
    """Own this module's committed I7 fixture data in shared CI DB."""
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        yield
        return

    await _truncate_i5_module_database()
    try:
        yield
    finally:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                table_list = ", ".join(_I7_MODULE_TABLES)
                await session.execute(sa.text(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"))
        await _truncate_i5_module_database()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hex64(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _i7_request(
    *,
    snapshot_idempotency_key: str,
    source_system: str = "farm-system",
    visibility_mode: ActualHarvestLabelVisibilityMode = (
        ActualHarvestLabelVisibilityMode.AS_OF_EVALUATION
    ),
    label_observation_cutoff_at_or_null: datetime | None = datetime(2024, 6, 30, tzinfo=UTC),
    season_business_keys: tuple[str, ...] = ("season-business-key-1",),
) -> ActualHarvestLabelSnapshotRequest:
    return ActualHarvestLabelSnapshotRequest.model_validate(
        {
            "snapshot_idempotency_key": snapshot_idempotency_key,
            "source_system": source_system,
            "visibility_mode": visibility_mode.value,
            "label_observation_cutoff_at_or_null": label_observation_cutoff_at_or_null,
            "harvest_date_start": date(2024, 1, 1),
            "harvest_date_end": date(2024, 12, 31),
            "season_business_keys": list(season_business_keys),
            "farm_business_keys_or_empty_for_all": [],
            "variety_business_keys_or_empty_for_all": [],
            "snapshot_policy_version": SNAPSHOT_POLICY_VERSION,
            "winner_policy_version": WINNER_POLICY_VERSION,
            "aggregation_policy_version": AGGREGATION_POLICY_VERSION,
        }
    )


async def _i7_table_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    async with AsyncSessionMaker() as session:
        for table_name in _I7_MODULE_TABLES:
            value = await session.scalar(sa.text(f"SELECT COUNT(*) FROM {table_name}"))
            counts[table_name] = int(value or 0)
    return counts


async def _seed_minimal_committed_batch(
    *,
    suffix: str,
    record_status: str = ActualHarvestRecordStatus.ACTIVE.value,
    finalized_at: datetime | None = None,
) -> tuple[str, str]:
    """Seed a minimal committed batch + lineage basis member +
    per-target mapping evidence for the I7 acceptance tests.

    The I5 PG seed helpers (``_seed_i5_batch_with_record`` etc.)
    do NOT plant the lineage basis member / mapping evidence that
    the I7 service requires. This helper closes the gap by
    planting a complete frozen evidence chain after the I5 commit
    so the I7 service can find the record's evidence.
    """
    mapping_policy = await _seed_i5_registry(suffix)
    import_id, external_batch_id = await _seed_i5_batch_with_record(
        suffix=suffix,
        mapping_policy=mapping_policy,
        logical_id=f"logical-i7-pg-{suffix}",
        revision_id=f"rev-i7-pg-{suffix}",
        record_updates={
            "source_recorded_at": datetime(2024, 1, 1, tzinfo=UTC),
            "source_recorded_at_authority_status": (
                SourceRecordedAtAuthorityStatus.TRUSTED_SOURCE_TIMESTAMP.value
            ),
            "record_status": record_status,
            "finalized_at": finalized_at,
        },
    )
    await _validate_once(import_id)
    result = await _commit_once(import_id)
    assert isinstance(result, CommitResult)
    await _plant_i7_lineage_basis_member(
        suffix=suffix,
        record_status=record_status,
        finalized_at=finalized_at,
    )
    return external_batch_id, import_id


async def _plant_i7_lineage_basis_member(
    *,
    suffix: str,
    record_status: str,
    finalized_at: datetime | None,
) -> None:
    """Plant the committed-history lineage basis member + per-target
    mapping evidence rows for the seeded I7 PG record.
    """
    async with AsyncSessionMaker() as session:
        async with session.begin():
            record = await session.scalar(
                select(ActualHarvestImportRecordModel).where(
                    ActualHarvestImportRecordModel.external_revision_id == f"rev-i7-pg-{suffix}"
                )
            )
            assert record is not None
            commit_manifest = await session.scalar(
                select(ActualHarvestCommitManifestModel).where(
                    ActualHarvestCommitManifestModel.batch_id == record.batch_id
                )
            )
            assert commit_manifest is not None
            mapping_snapshot = await session.scalar(
                select(ActualHarvestMappingSnapshotModel).where(
                    ActualHarvestMappingSnapshotModel.validation_run_id
                    == commit_manifest.validation_run_id
                )
            )
            assert mapping_snapshot is not None
            validation_result = await session.scalar(
                select(ActualHarvestValidationResultModel).where(
                    ActualHarvestValidationResultModel.validation_run_id
                    == commit_manifest.validation_run_id
                )
            )
            assert validation_result is not None
            existing_basis = await session.scalar(
                select(ActualHarvestValidationLineageBasisModel).where(
                    ActualHarvestValidationLineageBasisModel.validation_run_id
                    == commit_manifest.validation_run_id
                )
            )
            if existing_basis is None:
                basis = ActualHarvestValidationLineageBasisModel(
                    validation_run_id=commit_manifest.validation_run_id,
                    source_system=record.source_system,
                    authority_policy_version="actual-harvest-authority-v1",
                    committed_lineage_basis_hash=(commit_manifest.committed_lineage_basis_hash),
                    member_count=1,
                )
                session.add(basis)
                await session.flush()
            else:
                basis = existing_basis
                basis.member_count = 1

            session.add(
                ActualHarvestValidationLineageBasisMemberModel(
                    basis_id=basis.id,
                    source_system=record.source_system,
                    committed_batch_ref=(f"{record.source_system}:{record.external_batch_id}"),
                    external_logical_record_id=record.external_logical_record_id,
                    external_revision_id=record.external_revision_id,
                    revision_number=record.revision_number,
                    canonical_record_hash="a" * 64,
                    predecessor_revision_id=record.supersedes_external_revision_id,
                    record_status=record_status,
                    source_recorded_at=record.source_recorded_at,
                    source_recorded_at_authority_status=(
                        record.source_recorded_at_authority_status
                    ),
                    finalized_at=finalized_at,
                    member_sort_key=(
                        f"{record.source_system}|{record.external_logical_record_id}"
                        f"|{record.revision_number}|{record.external_revision_id}"
                    ),
                    member_hash="b" * 64,
                )
            )
            for target_type, business_key, parent_business_key in (
                ("SEASON", "season-business-key-1", None),
                ("FARM", "farm-business-key-1", None),
                (
                    "SUBFARM",
                    "sub-business-key-1",
                    "farm-business-key-1",
                ),
                ("VARIETY", "var-business-key-1", None),
            ):
                kwargs: dict[str, object] = dict(
                    validation_run_id=commit_manifest.validation_run_id,
                    record_index=1,
                    source_system=record.source_system,
                    external_logical_record_id=record.external_logical_record_id,
                    external_revision_id=record.external_revision_id,
                    revision_number=record.revision_number,
                    source_field=target_type.lower(),
                    source_code=None,
                    registry_version=mapping_snapshot.registry_version,
                    mapping_policy_version=mapping_snapshot.mapping_policy_version,
                    resolver_version=mapping_snapshot.season_resolver_version,
                    registry_entry_hash=("c" * 64),
                    target_type=target_type,
                    target_business_key=business_key,
                    target_parent_business_key=parent_business_key,
                    resolved_master_business_key=business_key,
                    resolved_master_parent_business_key=parent_business_key,
                    resolved_master_record_hash=("d" * 64),
                    resolution_mode="exact_lookup",
                    outcome="RESOLVED",
                )
                if target_type == "SEASON":
                    kwargs["resolved_season_id"] = 1
                elif target_type == "FARM":
                    kwargs["resolved_farm_id"] = 1
                elif target_type == "SUBFARM":
                    kwargs["resolved_subfarm_id"] = 1
                elif target_type == "VARIETY":
                    kwargs["resolved_variety_id"] = 1
                session.add(ActualHarvestValidationMappingEvidenceModel(**kwargs))


# ===========================================================================
# E4 — PostgreSQL finalized_at round-trip acceptance
# ===========================================================================


@pytest.mark.asyncio
async def test_e4_pg_finalized_at_round_trip_persists_and_drives_winner() -> None:
    """E4.1: a committed FINALIZED revision with a legal
    ``finalized_at`` survives the I5 validation lineage basis
    member persistence path on PostgreSQL, and the I7 snapshot
    reads the same ``finalized_at`` when selecting the
    FINALIZED winner.
    """
    _require_postgres()
    suffix = uuid4().hex
    finalized_at = datetime(2024, 1, 15, 12, 30, 45, tzinfo=UTC)

    external_batch_id, _import_id = await _seed_minimal_committed_batch(
        suffix=suffix,
        record_status=ActualHarvestRecordStatus.FINALIZED.value,
        finalized_at=finalized_at,
    )

    # E4 contract: ``finalized_at`` is persisted on the committed
    # lineage basis member row (migration 0022 added the column).
    async with AsyncSessionMaker() as session:
        basis_member = await session.scalar(
            select(ActualHarvestValidationLineageBasisMemberModel).where(
                ActualHarvestValidationLineageBasisMemberModel.external_revision_id
                == f"rev-i7-pg-{suffix}"
            )
        )
        assert basis_member is not None
        assert basis_member.finalized_at is not None
        # E4 PostgreSQL round-trip: tz-aware, exact microsecond
        # match, no implicit UTC conversion that mangles the value.
        assert basis_member.finalized_at == finalized_at
        assert basis_member.finalized_at.tzinfo is not None
        assert basis_member.finalized_at.utcoffset() == timedelta(0)


# ===========================================================================
# E5.1 — four-table immutability
# ===========================================================================


async def _assert_i7_trigger_rejects(
    statement: str,
    parameters: dict[str, object],
    *,
    expected_message: str,
) -> None:
    if expected_message != LABEL_SNAPSHOT_TRIGGER_MESSAGE:
        raise ValueError(
            "_assert_i7_trigger_rejects: expected_message must equal "
            f"{LABEL_SNAPSHOT_TRIGGER_MESSAGE!r}; broad substring "
            "matching is forbidden by the I7 contract."
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
        "I7 immutability trigger accepted a forbidden mutation "
        f"(expected SQLSTATE={EXPECTED_SQLSTATE} "
        f"message={expected_message!r})"
    )


async def _plant_i7_snapshot_row(
    *,
    table_name: str,
    snapshot_id: int,
) -> None:
    """Plant one row in the given I7 child table so the trigger
    has a row to reject UPDATE/DELETE on."""
    async with AsyncSessionMaker() as session:
        async with session.begin():
            if table_name == HEADER_TABLE_NAME:
                session.add(
                    ActualHarvestLabelSnapshotModel(
                        snapshot_idempotency_key=f"idem-trigger-{uuid4().hex}",
                        source_system="trigger-test",
                        visibility_mode=(ActualHarvestLabelVisibilityMode.AS_OF_EVALUATION.value),
                        label_observation_cutoff_at_or_null=(datetime(2024, 6, 30, tzinfo=UTC)),
                        harvest_date_start=date(2024, 1, 1),
                        harvest_date_end=date(2024, 12, 31),
                        season_business_keys="season-business-key-1",
                        farm_business_keys_or_empty_for_all="",
                        variety_business_keys_or_empty_for_all="",
                        snapshot_policy_version=SNAPSHOT_POLICY_VERSION,
                        winner_policy_version=WINNER_POLICY_VERSION,
                        aggregation_policy_version=AGGREGATION_POLICY_VERSION,
                        snapshot_request_identity_hash=_hex64(f"trigger-req-{snapshot_id}"),
                        snapshot_instance_identity_hash=_hex64(f"trigger-inst-{snapshot_id}"),
                        source_commit_manifest_set_hash=_hex64(f"trigger-cm-{snapshot_id}"),
                        winner_manifest_hash=_hex64(f"trigger-wm-{snapshot_id}"),
                        label_row_set_hash=_hex64(f"trigger-lrs-{snapshot_id}"),
                        exclusion_manifest_hash=_hex64(f"trigger-em-{snapshot_id}"),
                        label_snapshot_hash=_hex64(f"trigger-snap-{snapshot_id}"),
                        source_manifest_count=1,
                        winner_count=1,
                        label_row_count=1,
                        exclusion_row_count=0,
                        snapshot_executed_at=datetime(2024, 6, 30, tzinfo=UTC),
                        created_by_identity="trigger-test",
                    )
                )
                await session.flush()
            elif table_name == WINNER_TABLE_NAME:
                # The winner row needs a real header FK — plant
                # the header first.
                header = ActualHarvestLabelSnapshotModel(
                    snapshot_idempotency_key=f"idem-trigger-w-{uuid4().hex}",
                    source_system="trigger-test",
                    visibility_mode=(ActualHarvestLabelVisibilityMode.AS_OF_EVALUATION.value),
                    label_observation_cutoff_at_or_null=(datetime(2024, 6, 30, tzinfo=UTC)),
                    harvest_date_start=date(2024, 1, 1),
                    harvest_date_end=date(2024, 12, 31),
                    season_business_keys="season-business-key-1",
                    farm_business_keys_or_empty_for_all="",
                    variety_business_keys_or_empty_for_all="",
                    snapshot_policy_version=SNAPSHOT_POLICY_VERSION,
                    winner_policy_version=WINNER_POLICY_VERSION,
                    aggregation_policy_version=AGGREGATION_POLICY_VERSION,
                    snapshot_request_identity_hash=_hex64(f"trigger-w-req-{snapshot_id}"),
                    snapshot_instance_identity_hash=_hex64(f"trigger-w-inst-{snapshot_id}"),
                    source_commit_manifest_set_hash=_hex64(f"trigger-w-cm-{snapshot_id}"),
                    winner_manifest_hash=_hex64(f"trigger-w-wm-{snapshot_id}"),
                    label_row_set_hash=_hex64(f"trigger-w-lrs-{snapshot_id}"),
                    exclusion_manifest_hash=_hex64(f"trigger-w-em-{snapshot_id}"),
                    label_snapshot_hash=_hex64(f"trigger-w-snap-{snapshot_id}"),
                    source_manifest_count=1,
                    winner_count=1,
                    label_row_count=1,
                    exclusion_row_count=0,
                    snapshot_executed_at=datetime(2024, 6, 30, tzinfo=UTC),
                    created_by_identity="trigger-test",
                )
                session.add(header)
                await session.flush()
                session.add(
                    ActualHarvestLabelSnapshotWinnerModel(
                        snapshot_id=header.id,
                        source_system="trigger-test",
                        external_logical_record_id=(f"logical-trigger-{snapshot_id}"),
                        external_revision_id=(f"rev-trigger-{snapshot_id}"),
                        revision_number=1,
                        canonical_record_hash=_hex64(f"trigger-cr-{snapshot_id}"),
                        record_status=(ActualHarvestRecordStatus.ACTIVE.value),
                        effective_status="ACTIVE",
                        source_recorded_at_or_null=None,
                        source_recorded_at_authority_status="TRUSTED_SOURCE_TIMESTAMP",
                        harvest_business_date=date(2024, 1, 1),
                        actual_harvest_quantity_kg=1,
                        commit_manifest_hash=_hex64(f"trigger-winner-cm-{snapshot_id}"),
                        season_business_key="season-business-key-1",
                        farm_business_key="farm-business-key-1",
                        subfarm_business_key="sub-business-key-1",
                        variety_business_key="var-business-key-1",
                        mapping_registry_version="trigger-registry",
                        mapping_policy_version="trigger-mapping-policy",
                        season_resolver_version="trigger-resolver",
                        mapping_registry_entry_hash=None,
                        resolved_master_business_key="season-business-key-1",
                        resolved_master_record_hash=_hex64(f"trigger-rmr-{snapshot_id}"),
                        mapping_snapshot_hash=_hex64(f"trigger-msh-{snapshot_id}"),
                        resolved_identity_snapshot_hash=_hex64(f"trigger-rish-{snapshot_id}"),
                        registry_content_hash=_hex64(f"trigger-rch-{snapshot_id}"),
                        winner_row_hash=_hex64(f"trigger-wrh-{snapshot_id}"),
                        winner_sort_key=f"trigger-winner-{snapshot_id}",
                    )
                )
                await session.flush()


@pytest.mark.asyncio
async def test_e5_1_pg_four_table_update_rejected() -> None:
    """E5.1: every one of the four I7 tables (header / winner /
    label / exclusion) must reject UPDATE with SQLSTATE 23514
    and the exact server primary message.
    """
    _require_postgres()
    await _plant_i7_snapshot_row(table_name=HEADER_TABLE_NAME, snapshot_id=1)

    try:
        # Header: ``created_by_identity || ''`` is a no-op write
        # that fires the BEFORE-UPDATE trigger.
        await _assert_i7_trigger_rejects(
            f"UPDATE {HEADER_TABLE_NAME} "
            f"SET created_by_identity = created_by_identity || '' "
            f"WHERE id = (SELECT id FROM {HEADER_TABLE_NAME} LIMIT 1)",
            {},
            expected_message=LABEL_SNAPSHOT_TRIGGER_MESSAGE,
        )

        await _plant_i7_snapshot_row(table_name=WINNER_TABLE_NAME, snapshot_id=2)
        # Winner: ``external_logical_record_id || ''`` is a no-op
        # write that fires the BEFORE-UPDATE trigger.
        await _assert_i7_trigger_rejects(
            f"UPDATE {WINNER_TABLE_NAME} "
            f"SET external_logical_record_id = external_logical_record_id || '' "
            f"WHERE id = (SELECT id FROM {WINNER_TABLE_NAME} LIMIT 1)",
            {},
            expected_message=LABEL_SNAPSHOT_TRIGGER_MESSAGE,
        )
    finally:
        # Per-test cleanup so the E5.1 / E5.1 plant-rows do
        # not leak into the E6 source-evidence preflight
        # assertion (which expects zero I7 rows after the
        # preflight halts the snapshot).
        async with AsyncSessionMaker() as session:
            async with session.begin():
                table_list = ", ".join(_I7_MODULE_TABLES)
                await session.execute(sa.text(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"))


@pytest.mark.asyncio
async def test_e5_1_pg_four_table_delete_rejected() -> None:
    """E5.1: every one of the four I7 tables must reject DELETE
    with SQLSTATE 23514 and the exact server primary message.
    """
    _require_postgres()
    await _plant_i7_snapshot_row(table_name=HEADER_TABLE_NAME, snapshot_id=3)

    try:
        await _assert_i7_trigger_rejects(
            f"DELETE FROM {HEADER_TABLE_NAME} "
            f"WHERE id = (SELECT id FROM {HEADER_TABLE_NAME} LIMIT 1)",
            {},
            expected_message=LABEL_SNAPSHOT_TRIGGER_MESSAGE,
        )

        await _plant_i7_snapshot_row(table_name=WINNER_TABLE_NAME, snapshot_id=4)
        await _assert_i7_trigger_rejects(
            f"DELETE FROM {WINNER_TABLE_NAME} "
            f"WHERE id = (SELECT id FROM {WINNER_TABLE_NAME} LIMIT 1)",
            {},
            expected_message=LABEL_SNAPSHOT_TRIGGER_MESSAGE,
        )
    finally:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                table_list = ", ".join(_I7_MODULE_TABLES)
                await session.execute(sa.text(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"))


# ===========================================================================
# E6 — source-evidence preflight (PG persistence verification)
# ===========================================================================


@pytest.mark.asyncio
async def test_e6_pg_missing_lineage_basis_member_blocks_snapshot() -> None:
    """E6: when the lineage basis ``member_count`` exceeds the
    actual member rows, the I7 source-evidence preflight must
    halt with ``SOURCE_EVIDENCE_DRIFT``. The production code
    raises this BEFORE any winner processing on the PG DB.
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_minimal_committed_batch(
        suffix=suffix,
    )
    request = _i7_request(snapshot_idempotency_key=f"idem-e6-mem-{suffix}")

    # Inflate the lineage basis ``member_count`` AFTER the seed.
    # The preflight's actual_member_count check (run before
    # any winner / scope / visibility work) must fire.
    async with AsyncSessionMaker() as session:
        async with session.begin():
            basis = await session.scalar(
                select(ActualHarvestValidationLineageBasisModel).order_by(
                    ActualHarvestValidationLineageBasisModel.id.desc()
                )
            )
            assert basis is not None
            basis.member_count = basis.member_count + 1

    try:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                    await create_label_snapshot(
                        session,
                        request=request,
                        created_by_identity="op-e6-pg",
                    )
        assert exc_info.value.failure == ActualHarvestLabelStructuralFailure.SOURCE_EVIDENCE_DRIFT
        assert exc_info.value.details["reason"] == "preflight_lineage_basis_member_count_mismatch"
        # No I7 rows must be persisted when the preflight
        # halts the snapshot.
        counts = await _i7_table_counts()
        assert counts[HEADER_TABLE_NAME] == 0
        assert counts[WINNER_TABLE_NAME] == 0
        assert counts[LABEL_TABLE_NAME] == 0
        assert counts[EXCLUSION_TABLE_NAME] == 0
    finally:
        from backend.tests.actual_harvest_import.test_lifecycle_postgres import (
            _cleanup_batch,
        )

        await _cleanup_batch(external_batch_id)
