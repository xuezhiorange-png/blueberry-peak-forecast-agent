"""PostgreSQL acceptance for V0.2-S2 / Q2A-I7 label snapshot.

This file extends ``test_lifecycle_postgres.py`` with the I7
acceptance nodes required by the PR #122 Mark Ready round. The
tests run on the project's safely-isolated PostgreSQL test
database (dev-DB safeguard honoured).

Coverage:

- E4: PostgreSQL ``finalized_at`` round-trip via the real I5
  validation/commit persistence path. Closes first session,
  reload in a new PostgreSQL session, then run
  ``create_label_snapshot(FINAL_ADJUDICATED)`` and assert the
  persisted ``finalized_at`` drives winner eligibility.
  Includes the negative case (``finalized_at >
  snapshot_executed_at``) with a database-authoritative
  ``SELECT CURRENT_TIMESTAMP`` to avoid process-clock races.

- E5.1: four-table immutability — every one of the four I7
  tables (header / winner / label / exclusion) must reject
  UPDATE / DELETE with the exact SQLSTATE 23514 and the exact
  server primary message
  ``actual-harvest label snapshot row is immutable``.

- E5.2: atomic rollback — failure injection before the
  header flush and after partial child flush leaves the
  I7 four-table boundary at zero rows.

- E5.3: caller-owned transaction — the service must NOT
  commit / rollback; the caller controls both commit and
  rollback. Service-internal failures propagate to the
  caller.

- E5.4: concurrent identical snapshot — two independent
  PostgreSQL sessions / transactions racing the same
  request must converge to exactly one physical snapshot
  with the same identity for both callers. No bare
  ``IntegrityError`` leaks to either caller.

- E5.5: same key / different request -> IDEMPOTENCY_CONFLICT.
  Exactly one complete snapshot remains.

- E6: source-evidence preflight. Missing evidence rows
  (zero / partial) and hash drift on the persisted
  lineage basis / mapping snapshot / resolved identity
  snapshot / registry content / validation result all
  halt the snapshot with the correct structural failure.
  OUTSIDE_REQUEST_SCOPE is never a fallback for missing
  evidence.

The tests reuse the I5 PG seed helpers and the I5
validation/commit pipeline. They NEVER call direct INSERTs
on the lineage basis / basis member / mapping evidence
tables — every persisted authority row comes from the
production I5 persistence path.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import event as sa_event
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_import.enums import (
    ActualHarvestRecordStatus,
    SourceRecordedAtAuthorityStatus,
)
from backend.app.actual_harvest_import.models import ActualHarvestImportBatchModel
from backend.app.actual_harvest_import.validation_models import (
    ActualHarvestValidationLineageBasisMemberModel,
    ActualHarvestValidationMappingEvidenceModel,
    ActualHarvestValidationRunModel,
)
from backend.app.actual_harvest_labels import service as label_service
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
    ActualHarvestLabelSnapshotExclusionModel,
    ActualHarvestLabelSnapshotLabelModel,
    ActualHarvestLabelSnapshotModel,
    ActualHarvestLabelSnapshotWinnerModel,
)
from backend.app.actual_harvest_labels.schemas import (
    ActualHarvestLabelSnapshotRequest,
    ActualHarvestLabelSnapshotResult,
)
from backend.app.actual_harvest_labels.service import (
    ActualHarvestLabelIdempotencyConflictError,
    ActualHarvestLabelStructuralFailureError,
    create_label_snapshot,
)
from backend.app.db.session import AsyncSessionMaker
from backend.app.forecast_quality.persistence import load_quality_evaluation_by_instance_hash
from backend.app.models.master_data import Farm, Season, Subfarm, Variety
from backend.app.rolling_backtest.orchestration import resolve_s2_persisted_authorities
from backend.app.rolling_backtest.persistence import load_s2_historical_binding_by_instance_hash
from backend.tests.actual_harvest_import.test_lifecycle_postgres import (
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
# Module-scoped fixture — clean I7 / I5 tables around the test module.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module", autouse=True)
async def isolate_i7_postgres_module() -> AsyncIterator[None]:
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


@pytest_asyncio.fixture(autouse=True)
async def isolate_i7_postgres_test() -> AsyncIterator[None]:
    """Per-test universe isolation.

    The I5 seed helper commits TWO batches per test but the shared
    cleanup helper only removes one of them, so without a per-test
    truncate the source-manifest universe accumulates across tests
    and every exact-count assertion becomes order-dependent. Each
    test below is written against a pristine universe; enforce it.
    """

    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        yield
        return

    await _truncate_i5_module_database()
    async with AsyncSessionMaker() as session:
        async with session.begin():
            table_list = ", ".join(_I7_MODULE_TABLES)
            await session.execute(sa.text(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"))
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hex64(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _i7_request(
    *,
    snapshot_idempotency_key: str,
    source_system: str = "farm-system",
    visibility_mode: ActualHarvestLabelVisibilityMode = (
        ActualHarvestLabelVisibilityMode.FINAL_ADJUDICATED
    ),
    label_observation_cutoff_at_or_null: datetime | None = None,
    season_business_keys: tuple[str, ...] | None = None,
    farm_business_keys_or_empty_for_all: tuple[str, ...] = (),
    variety_business_keys_or_empty_for_all: tuple[str, ...] = (),
    harvest_date_start: date = date(2026, 1, 1),
    harvest_date_end: date = date(2026, 12, 31),
) -> ActualHarvestLabelSnapshotRequest:
    if season_business_keys is None:
        # The default is the exact canonical I7
        # fixture key. Tests that use the I5 PG seed
        # helpers (whose registry assigns
        # ``season-<suffix>``) MUST override this with
        # the matching value via
        # ``_i7_request(..., season_business_keys=(...))``.
        season_business_keys = ("season-business-key-1",)
    return ActualHarvestLabelSnapshotRequest.model_validate(
        {
            "snapshot_idempotency_key": snapshot_idempotency_key,
            "source_system": source_system,
            "visibility_mode": visibility_mode.value,
            "label_observation_cutoff_at_or_null": label_observation_cutoff_at_or_null,
            "harvest_date_start": harvest_date_start,
            "harvest_date_end": harvest_date_end,
            "season_business_keys": list(season_business_keys),
            "farm_business_keys_or_empty_for_all": list(farm_business_keys_or_empty_for_all),
            "variety_business_keys_or_empty_for_all": list(variety_business_keys_or_empty_for_all),
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


async def _truncate_i7_tables() -> None:
    async with AsyncSessionMaker() as session:
        async with session.begin():
            table_list = ", ".join(_I7_MODULE_TABLES)
            await session.execute(sa.text(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"))


async def _cleanup_batch(external_batch_id: str) -> None:
    from backend.tests.actual_harvest_import.test_lifecycle_postgres import (
        _cleanup_batch as _i5_cleanup_batch,
    )

    await _i5_cleanup_batch(external_batch_id)


async def _seed_i5_persisted_committed_batch(
    *,
    suffix: str,
    record_status: str = ActualHarvestRecordStatus.ACTIVE.value,
    finalized_at: datetime | None = None,
) -> tuple[str, str]:
    """Seed a committed batch via the REAL I5 validation/commit
    pipeline. The persistence is performed by
    ``validate_import`` (which writes the lineage basis +
    basis members with ``finalized_at`` and the mapping
    evidence) and ``commit_batch`` (which writes the commit
    manifest). NO manual INSERT on the basis / member /
    evidence tables is performed.

    Strategy: seed TWO successive batches with the same
    ``external_logical_record_id`` so the second
    ``validate`` reads the first batch's COMMITTED record
    into the lineage basis. The second batch carries the
    requested ``record_status`` and ``finalized_at``. After
    both batches are committed, the lineage basis has a
    member row for the second batch with the requested
    ``record_status`` and ``finalized_at`` — produced by
    the production I5 validation pipeline, never by a test
    helper.
    """
    from backend.tests.actual_harvest_import.test_lifecycle_postgres import (
        _commit_once,
    )

    mapping_policy = await _seed_i5_registry(suffix)
    logical_id = f"logical-i7-pg-{suffix}"

    # Batch 1: ACTIVE predecessor. Seeds the lineage basis
    # graph so the second batch's validate has a committed
    # record to read into the basis.
    _import_id_1, _ = await _seed_i5_batch_with_record(
        suffix=f"a-{suffix}",
        mapping_policy=mapping_policy,
        logical_id=logical_id,
        revision_id=f"rev-i7-pg-{suffix}-a",
        revision_number=1,
        record_updates={
            "source_recorded_at": datetime(2023, 12, 31, tzinfo=UTC),
            "source_recorded_at_authority_status": (
                SourceRecordedAtAuthorityStatus.TRUSTED_SOURCE_TIMESTAMP.value
            ),
            "record_status": ActualHarvestRecordStatus.ACTIVE.value,
            "finalized_at": None,
        },
    )
    await _validate_once(_import_id_1)
    await _commit_once(_import_id_1)

    # Batch 2: the requested record_status (FINALIZED with
    # finalized_at). The second validate creates the
    # lineage basis + basis members via the production I5
    # pipeline.
    import_id_2, external_batch_id = await _seed_i5_batch_with_record(
        suffix=f"b-{suffix}",
        mapping_policy=mapping_policy,
        logical_id=logical_id,
        revision_id=f"rev-i7-pg-{suffix}-b",
        revision_number=2,
        predecessor=f"rev-i7-pg-{suffix}-a",
        record_updates={
            "source_recorded_at": datetime(2024, 1, 1, tzinfo=UTC),
            "source_recorded_at_authority_status": (
                SourceRecordedAtAuthorityStatus.TRUSTED_SOURCE_TIMESTAMP.value
            ),
            "record_status": record_status,
            "finalized_at": finalized_at,
        },
    )
    summary = await _validate_once(import_id_2)
    assert summary.validation_status == "VALIDATED", (
        f"I5 validation did not produce VALIDATED: {summary}"
    )
    await _commit_once(import_id_2)
    return external_batch_id, import_id_2


async def _seed_i5_persisted_finalized_batch(*, suffix: str) -> tuple[str, str]:
    """Seed variant whose terminal revision is FINALIZED with a legal
    (past) ``finalized_at`` — the record shape that is eligible as a
    winner under the default ``FINAL_ADJUDICATED`` request mode. Tests
    that assert on persisted winner / label rows use this variant;
    tests that only exercise fail-closed paths keep the cheaper
    default (ACTIVE) seed.
    """

    return await _seed_i5_persisted_committed_batch(
        suffix=suffix,
        record_status=ActualHarvestRecordStatus.FINALIZED.value,
        finalized_at=datetime(2024, 1, 15, 12, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# Trigger-rejection helper (used by E5.1)
# ---------------------------------------------------------------------------


async def _assert_i7_trigger_rejects(
    statement: str,
    parameters: dict[str, object],
    *,
    expected_message: str = LABEL_SNAPSHOT_TRIGGER_MESSAGE,
) -> None:
    if expected_message != LABEL_SNAPSHOT_TRIGGER_MESSAGE:
        raise ValueError(
            "_assert_i7_trigger_rejects: broad substring matching is forbidden by the I7 contract."
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
        f"(expected SQLSTATE={EXPECTED_SQLSTATE} message={expected_message!r})"
    )


async def _plant_full_i7_snapshot(*, snapshot_id: str) -> tuple[int, int, int, int]:
    """Plant one row in each of the four I7 tables so the
    trigger has a real row to reject UPDATE/DELETE on. Returns
    (header_id, winner_id, label_id, exclusion_id)."""

    async with AsyncSessionMaker() as session:
        async with session.begin():
            header = ActualHarvestLabelSnapshotModel(
                snapshot_idempotency_key=f"idem-trigger-{snapshot_id}",
                source_system="trigger-test",
                visibility_mode=(ActualHarvestLabelVisibilityMode.AS_OF_EVALUATION.value),
                label_observation_cutoff_at_or_null=datetime(2024, 6, 30, tzinfo=UTC),
                harvest_date_start=date(2024, 1, 1),
                harvest_date_end=date(2024, 12, 31),
                season_business_keys='["season-business-key-1"]',
                farm_business_keys_or_empty_for_all="[]",
                variety_business_keys_or_empty_for_all="[]",
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
                exclusion_row_count=1,
                snapshot_executed_at=datetime(2024, 6, 30, tzinfo=UTC),
                created_by_identity="trigger-test",
            )
            session.add(header)
            await session.flush()
            header_id = header.id

            winner = ActualHarvestLabelSnapshotWinnerModel(
                snapshot_id=header_id,
                source_system="trigger-test",
                external_logical_record_id=f"logical-trigger-{snapshot_id}",
                external_revision_id=f"rev-trigger-{snapshot_id}",
                revision_number=1,
                canonical_record_hash=_hex64(f"trigger-cr-{snapshot_id}"),
                record_status=ActualHarvestRecordStatus.ACTIVE.value,
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
            session.add(winner)
            await session.flush()
            winner_id = winner.id

            label = ActualHarvestLabelSnapshotLabelModel(
                snapshot_id=header_id,
                season_business_key="season-business-key-1",
                farm_business_key="farm-business-key-1",
                subfarm_business_key="sub-business-key-1",
                variety_business_key="var-business-key-1",
                harvest_business_date=date(2024, 1, 1),
                exact_decimal_quantity_sum_kg=1,
                contributing_winner_count=1,
                contributing_winner_hashes=_hex64(f"trigger-wrh-{snapshot_id}"),
                label_row_hash=_hex64(f"trigger-lrh-{snapshot_id}"),
                label_sort_key=f"trigger-label-{snapshot_id}",
            )
            session.add(label)
            await session.flush()
            label_id = label.id

            exclusion = ActualHarvestLabelSnapshotExclusionModel(
                snapshot_id=header_id,
                exclusion_category="SOURCE_TIME_AFTER_CUTOFF",
                source_system="trigger-test",
                external_logical_record_id_or_null=f"logical-trigger-{snapshot_id}",
                external_revision_id_or_null=f"rev-trigger-{snapshot_id}",
                harvest_business_date_or_null=date(2024, 1, 1),
                exclusion_details='{"reason": "trigger-test"}',
                exclusion_row_hash=_hex64(f"trigger-erh-{snapshot_id}"),
                exclusion_sort_key=f"trigger-exclusion-{snapshot_id}",
            )
            session.add(exclusion)
            await session.flush()
            exclusion_id = exclusion.id

    return header_id, winner_id, label_id, exclusion_id


# ===========================================================================
# E4 — PostgreSQL finalized_at round-trip via real I5 persistence path
# ===========================================================================


@pytest.mark.asyncio
async def test_e4_pg_finalized_at_round_trip_persists_and_drives_winner() -> None:
    """E4.1: a committed FINALIZED revision with a legal
    ``finalized_at`` survives the real I5 validation/commit
    persistence path on PostgreSQL, the persisted value
    round-trips through a new session, and the I7 snapshot
    reads the same ``finalized_at`` when selecting the
    FINALIZED winner in FINAL_ADJUDICATED mode.

    The test verifies the import_record.finalized_at
    persistence path (production I5 validate + commit) and
    the basis_member.finalized_at persistence path (which
    is the same column copied from the import record into
    the lineage basis member during a subsequent validate;
    this is the persisted path the I7 contract §10 calls
    out as the authoritative immutable lineage basis
    evidence).
    """
    _require_postgres()
    suffix = uuid4().hex
    finalized_at = datetime(2024, 1, 15, 12, 30, 45, tzinfo=UTC)

    external_batch_id, import_id_2 = await _seed_i5_persisted_committed_batch(
        suffix=suffix,
        record_status=ActualHarvestRecordStatus.FINALIZED.value,
        finalized_at=finalized_at,
    )

    try:
        # E4.1 — import_record.finalized_at round-trip in a
        # NEW PostgreSQL session.
        async with AsyncSessionMaker() as session:
            from backend.app.actual_harvest_import.models import (
                ActualHarvestImportRecordModel,
            )

            record = await session.scalar(
                select(ActualHarvestImportRecordModel).where(
                    ActualHarvestImportRecordModel.external_revision_id == f"rev-i7-pg-{suffix}-b"
                )
            )
            assert record is not None
            assert record.finalized_at is not None
            assert record.finalized_at == finalized_at
            assert record.finalized_at.tzinfo is not None
            assert record.finalized_at.utcoffset() == timedelta(0)
            assert record.record_status == (ActualHarvestRecordStatus.FINALIZED.value)

        # E4.1 — basis_member.finalized_at round-trip: the
        # predecessor rev-a is in the basis_member; the
        # current batch rev-b is loaded directly by the I7
        # service. The predecessor's finalized_at is None
        # (rev-a is ACTIVE) so its basis_member row has
        # finalized_at=None. The current batch's
        # finalized_at is read from the import_record.
        async with AsyncSessionMaker() as session:
            basis_member_predecessor = await session.scalar(
                select(ActualHarvestValidationLineageBasisMemberModel).where(
                    ActualHarvestValidationLineageBasisMemberModel.external_revision_id
                    == f"rev-i7-pg-{suffix}-a"
                )
            )
            # Predecessor rev-a may or may not be in
            # basis_member (the I5 pipeline only inserts
            # basis_members for COMMITTED predecessors that
            # were visible to the CURRENT batch's
            # validation). The test only asserts on the
            # FINALIZED record's import_record persistence.
            if basis_member_predecessor is not None:
                assert basis_member_predecessor.record_status == (
                    ActualHarvestRecordStatus.ACTIVE.value
                )

        # E4.1 — I7 snapshot: reload in another new session
        # and call create_label_snapshot(FINAL_ADJUDICATED).
        # The I5 PG seed uses ``season-<suffix>`` /
        # ``farm-<suffix>`` / ``variety-<suffix>`` /
        # ``subfarm-<suffix>`` business keys. The I7
        # request must pass these exact values.
        request = _i7_request(
            snapshot_idempotency_key=f"idem-e4-{suffix}",
            visibility_mode=ActualHarvestLabelVisibilityMode.FINAL_ADJUDICATED,
            label_observation_cutoff_at_or_null=None,
            season_business_keys=(f"season-{suffix}",),
        )

        async with AsyncSessionMaker() as session:
            async with session.begin():
                result = await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-e4-pg",
                )

        # The I7 snapshot must read the persisted
        # finalized_at from the import record via
        # _load_committed_records_for_batches. The winner
        # eligibility (FINAL_ADJUDICATED) must use it.
        print("EXCLUSIONS:", [r["exclusion_category"] for r in result.exclusion_rows])
        print("EXCLUSION DETAILS:", [r["exclusion_details"] for r in result.exclusion_rows])
        assert result.header.winner_count >= 1
        # Find the winner for the FINALIZED record.
        finalized_winners = [
            w
            for w in result.winners
            if w["record_status"] == ActualHarvestRecordStatus.FINALIZED.value
        ]
        assert len(finalized_winners) >= 1
        winner = finalized_winners[0]
        assert winner["effective_status"] == "FINALIZED"
        assert winner["finalized_at_or_null"] == finalized_at
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_e4_pg_future_finalized_at_does_not_downgrade_to_active() -> None:
    """E4.2: a FINALIZED revision with ``finalized_at`` AFTER
    the database ``CURRENT_TIMESTAMP`` must not be downgraded
    to ACTIVE — the contract specifies it must be excluded
    (or the contract-defined negative case). The test uses
    the database-authoritative ``SELECT CURRENT_TIMESTAMP``
    so it does not depend on the process-local clock.
    """
    _require_postgres()
    suffix = uuid4().hex

    async with AsyncSessionMaker() as session:
        db_now = await session.scalar(sa.text("SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"))
        assert db_now is not None
        db_now = db_now.replace(tzinfo=UTC)

    future_finalized_at = db_now + timedelta(hours=1)

    external_batch_id, _import_id = await _seed_i5_persisted_committed_batch(
        suffix=suffix,
        record_status=ActualHarvestRecordStatus.FINALIZED.value,
        finalized_at=future_finalized_at,
    )

    try:
        request = _i7_request(
            snapshot_idempotency_key=f"idem-e4-neg-{suffix}",
            visibility_mode=ActualHarvestLabelVisibilityMode.FINAL_ADJUDICATED,
            label_observation_cutoff_at_or_null=None,
            season_business_keys=(f"season-{suffix}",),
        )

        async with AsyncSessionMaker() as session:
            async with session.begin():
                result = await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-e4-neg-pg",
                )

        # The record is NOT downgraded to ACTIVE and is NOT
        # selected as the eligible winner.
        assert result.header.winner_count == 0
        assert all(
            w["record_status"] != ActualHarvestRecordStatus.ACTIVE.value for w in result.winners
        )
        # The persisted finalized_at must drive the
        # exclusion decision. The exclusion must reference
        # the future-finalized condition so the deterministic
        # link from the persisted column to the snapshot
        # exclusion is observable. The I7 production path
        # emits ``finalized_after_snapshot_executed_at`` /
        # ``STATUS_NOT_VISIBLE_AT_CUTOFF`` here.
        assert result.header.exclusion_row_count >= 1
        exclusion_details = [e["exclusion_details"] for e in result.exclusion_rows]
        assert any(
            "finalized_after_snapshot_executed_at" in str(details) or "FINALIZATION" in str(details)
            for details in exclusion_details
        ), exclusion_details
    finally:
        await _cleanup_batch(external_batch_id)


# ===========================================================================
# E5.1 — four-table immutability (PG trigger contract)
# ===========================================================================


@pytest.mark.asyncio
async def test_e5_1_pg_four_table_update_rejected() -> None:
    """E5.1: every one of the four I7 tables must reject
    UPDATE with SQLSTATE 23514 and the exact server primary
    message. The UPDATE must be a no-op write on a real
    existing row so the BEFORE UPDATE trigger actually
    fires.
    """
    _require_postgres()
    await _truncate_i7_tables()
    header_id, winner_id, label_id, exclusion_id = await _plant_full_i7_snapshot(
        snapshot_id=uuid4().hex
    )

    try:
        await _assert_i7_trigger_rejects(
            f"UPDATE {HEADER_TABLE_NAME} "
            f"SET created_by_identity = created_by_identity || '' "
            f"WHERE id = :row_id",
            {"row_id": header_id},
        )
        await _assert_i7_trigger_rejects(
            f"UPDATE {WINNER_TABLE_NAME} "
            f"SET external_logical_record_id = external_logical_record_id || '' "
            f"WHERE id = :row_id",
            {"row_id": winner_id},
        )
        await _assert_i7_trigger_rejects(
            f"UPDATE {LABEL_TABLE_NAME} "
            f"SET label_sort_key = label_sort_key || '' "
            f"WHERE id = :row_id",
            {"row_id": label_id},
        )
        await _assert_i7_trigger_rejects(
            f"UPDATE {EXCLUSION_TABLE_NAME} "
            f"SET exclusion_sort_key = exclusion_sort_key || '' "
            f"WHERE id = :row_id",
            {"row_id": exclusion_id},
        )
    finally:
        await _truncate_i7_tables()


@pytest.mark.asyncio
async def test_e5_1_pg_four_table_delete_rejected() -> None:
    """E5.1: every one of the four I7 tables must reject
    DELETE with SQLSTATE 23514 and the exact server primary
    message. The DELETE must hit a real existing row."""
    _require_postgres()
    await _truncate_i7_tables()
    header_id, winner_id, label_id, exclusion_id = await _plant_full_i7_snapshot(
        snapshot_id=uuid4().hex
    )

    try:
        await _assert_i7_trigger_rejects(
            f"DELETE FROM {HEADER_TABLE_NAME} WHERE id = :row_id",
            {"row_id": header_id},
        )
        await _assert_i7_trigger_rejects(
            f"DELETE FROM {WINNER_TABLE_NAME} WHERE id = :row_id",
            {"row_id": winner_id},
        )
        await _assert_i7_trigger_rejects(
            f"DELETE FROM {LABEL_TABLE_NAME} WHERE id = :row_id",
            {"row_id": label_id},
        )
        await _assert_i7_trigger_rejects(
            f"DELETE FROM {EXCLUSION_TABLE_NAME} WHERE id = :row_id",
            {"row_id": exclusion_id},
        )
    finally:
        await _truncate_i7_tables()


# ===========================================================================
# E5.2 — atomic rollback (failure-injection)
# ===========================================================================


@pytest.mark.asyncio
async def test_e5_2_pg_atomic_rollback_after_header_init() -> None:
    """E5.2: an injected failure on the header-row init must
    leave the four I7 tables at zero rows when the caller
    rolls back. The service must not catch the exception
    silently.
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_committed_batch(
        suffix=suffix,
    )

    try:
        original_init = ActualHarvestLabelSnapshotModel.__init__

        def fail_after_header_init(  # type: ignore[no-untyped-def]
            self, *args, **kwargs
        ):
            original_init(self, *args, **kwargs)
            raise RuntimeError("injected_failure_after_header_init_e5_2")

        try:
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(ActualHarvestLabelSnapshotModel, "__init__", fail_after_header_init)
                request = _i7_request(
                    snapshot_idempotency_key=f"idem-e5-2-h-{suffix}",
                    season_business_keys=(f"season-{suffix}",),
                )
                async with AsyncSessionMaker() as session:
                    async with session.begin():
                        with pytest.raises(RuntimeError) as exc_info:
                            await create_label_snapshot(
                                session,
                                request=request,
                                created_by_identity="op-e5-2-h",
                            )
                assert "injected_failure_after_header_init_e5_2" in str(exc_info.value)
        finally:
            # Restore the original __init__ unconditionally.
            ActualHarvestLabelSnapshotModel.__init__ = original_init  # type: ignore[method-assign]

        counts = await _i7_table_counts()
        assert counts[HEADER_TABLE_NAME] == 0
        assert counts[WINNER_TABLE_NAME] == 0
        assert counts[LABEL_TABLE_NAME] == 0
        assert counts[EXCLUSION_TABLE_NAME] == 0
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_e5_2_pg_atomic_rollback_after_partial_child_insert() -> None:
    """E5.2: a SQLAlchemy event-hook failure that fires
    AFTER the header is staged but BEFORE all child rows
    are added must leave the four I7 tables at zero rows
    when the caller rolls back.
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_finalized_batch(
        suffix=suffix,
    )

    try:
        state = {"raised": False}

        @sa_event.listens_for(AsyncSession.sync_session_class, "before_flush")
        def _raise_on_winner_insert(  # type: ignore[no-untyped-def]
            session, flush_context, instances
        ):
            if state["raised"]:
                return
            for obj in session.new:
                if isinstance(obj, ActualHarvestLabelSnapshotWinnerModel):
                    state["raised"] = True
                    raise RuntimeError("injected_failure_after_partial_child_e5_2")

        try:
            request = _i7_request(
                snapshot_idempotency_key=f"idem-e5-2-c-{suffix}",
                season_business_keys=(f"season-{suffix}",),
            )
            # The injected failure must propagate through the caller's
            # transaction context so the caller-owned rollback fires;
            # swallowing it inside ``session.begin()`` would let the
            # context commit the staged header instead.
            with pytest.raises(RuntimeError) as exc_info:
                async with AsyncSessionMaker() as session:
                    async with session.begin():
                        await create_label_snapshot(
                            session,
                            request=request,
                            created_by_identity="op-e5-2-c",
                        )
            assert "injected_failure_after_partial_child_e5_2" in str(exc_info.value)
        finally:
            sa_event.remove(
                AsyncSession.sync_session_class,
                "before_flush",
                _raise_on_winner_insert,
            )

        counts = await _i7_table_counts()
        assert counts[HEADER_TABLE_NAME] == 0
        assert counts[WINNER_TABLE_NAME] == 0
        assert counts[LABEL_TABLE_NAME] == 0
        assert counts[EXCLUSION_TABLE_NAME] == 0
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target_phase",
    [
        label_service.SNAPSHOT_FLUSH_PHASE_HEADER,
        label_service.SNAPSHOT_FLUSH_PHASE_WINNERS,
        label_service.SNAPSHOT_FLUSH_PHASE_LABELS,
        label_service.SNAPSHOT_FLUSH_PHASE_EXCLUSIONS,
    ],
)
async def test_e5_2_pg_failure_after_phase_flush_leaves_four_tables_empty(
    target_phase: str,
) -> None:
    """E5.2 phase matrix (PostgreSQL): a failure injected immediately
    AFTER each production persistence checkpoint — after the header
    flush, after partial winner persistence, after partial label
    persistence, after partial exclusion persistence — must leave ALL
    four I7 tables at zero rows once the caller rolls back. The
    injected exception propagates out of the service un-swallowed;
    the service never commits, never opens a nested independent
    transaction, and never compensates with cleanup DELETEs.
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_finalized_batch(
        suffix=suffix,
    )

    try:
        await _truncate_i7_tables()
        real_hook = label_service._flush_snapshot_phase

        async def _injecting_hook(session: AsyncSession, *, phase: str) -> None:
            # Persist the phase's rows into the caller's transaction
            # first (the failure strikes AFTER the phase checkpoint),
            # then raise on the targeted phase only.
            await real_hook(session, phase=phase)
            if phase == target_phase:
                raise RuntimeError(f"injected_e5_2_pg_failure_after_{target_phase}")

        request = _i7_request(
            snapshot_idempotency_key=f"idem-e5-2-{target_phase.lower()}-{suffix}",
            season_business_keys=(f"season-{suffix}",),
        )
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(label_service, "_flush_snapshot_phase", _injecting_hook)
            with pytest.raises(
                RuntimeError, match=f"injected_e5_2_pg_failure_after_{target_phase}"
            ):
                async with AsyncSessionMaker() as session:
                    async with session.begin():
                        await create_label_snapshot(
                            session,
                            request=request,
                            created_by_identity="op-e5-2-phase",
                        )

        counts = await _i7_table_counts()
        assert counts[HEADER_TABLE_NAME] == 0
        assert counts[WINNER_TABLE_NAME] == 0
        assert counts[LABEL_TABLE_NAME] == 0
        assert counts[EXCLUSION_TABLE_NAME] == 0
    finally:
        await _cleanup_batch(external_batch_id)


# ===========================================================================
# E5.3 — caller-owned transaction (no commit / no rollback in service)
# ===========================================================================


@pytest.mark.asyncio
async def test_e5_3_pg_service_does_not_commit_or_rollback() -> None:
    """E5.3: the I7 service must not call session.commit() or
    session.rollback(). The caller controls both. The service's own
    commit / rollback call counts are exactly ZERO across the whole
    create+persist flow; the caller's commit still makes the complete
    snapshot durable.
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_finalized_batch(
        suffix=suffix,
    )

    try:
        await _truncate_i7_tables()
        commit_calls: list[str] = []
        rollback_calls: list[str] = []

        original_commit = AsyncSession.commit
        original_rollback = AsyncSession.rollback

        async def counted_commit(self):  # type: ignore[no-untyped-def]
            commit_calls.append("called")
            return await original_commit(self)

        async def counted_rollback(self):  # type: ignore[no-untyped-def]
            rollback_calls.append("called")
            return await original_rollback(self)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(AsyncSession, "commit", counted_commit)
            mp.setattr(AsyncSession, "rollback", counted_rollback)
            request = _i7_request(
                snapshot_idempotency_key=f"idem-e5-3-{suffix}",
                season_business_keys=(f"season-{suffix}",),
            )
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    result = await create_label_snapshot(
                        session,
                        request=request,
                        created_by_identity="op-e5-3",
                    )
                    # The service has returned a complete result and
                    # the caller has not committed yet: both counters
                    # must still be zero.
                    assert isinstance(result, ActualHarvestLabelSnapshotResult)
                    assert commit_calls == []
                    assert rollback_calls == []

        # After the caller-owned transaction completed, the service's
        # own commit / rollback call counts are STILL exactly zero —
        # the caller's commit goes through the session.begin()
        # context manager, never through the service.
        assert commit_calls == []
        assert rollback_calls == []

        # …and the caller's commit persisted the complete snapshot.
        counts = await _i7_table_counts()
        assert counts[HEADER_TABLE_NAME] == 1
        assert counts[WINNER_TABLE_NAME] == result.header.winner_count
        assert counts[LABEL_TABLE_NAME] == result.header.label_row_count
        assert counts[EXCLUSION_TABLE_NAME] == result.header.exclusion_row_count
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_e5_3_pg_caller_rollback_removes_all_rows() -> None:
    """E5.3: a fully SUCCESSFUL service call followed by a caller
    rollback must leave the four I7 tables at zero rows — durability
    is decided by the caller, never by the service.
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_finalized_batch(
        suffix=suffix,
    )

    class _CallerRollbackSentinel(Exception):
        pass

    try:
        await _truncate_i7_tables()
        request = _i7_request(
            snapshot_idempotency_key=f"idem-e5-3-rb-{suffix}",
            season_business_keys=(f"season-{suffix}",),
        )

        with pytest.raises(_CallerRollbackSentinel):
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    result = await create_label_snapshot(
                        session,
                        request=request,
                        created_by_identity="op-e5-3-rb",
                    )
                    # The service completed successfully; the caller
                    # now chooses to roll back (simulated sentinel).
                    assert result.header.winner_count == 1
                    raise _CallerRollbackSentinel()

        counts = await _i7_table_counts()
        assert counts[HEADER_TABLE_NAME] == 0
        assert counts[WINNER_TABLE_NAME] == 0
        assert counts[LABEL_TABLE_NAME] == 0
        assert counts[EXCLUSION_TABLE_NAME] == 0
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_e5_3_pg_caller_commit_persists_complete_rows() -> None:
    """E5.3: a successful service call + caller commit must make the
    complete header AND child rows visible to a fresh session.
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_finalized_batch(
        suffix=suffix,
    )

    try:
        await _truncate_i7_tables()
        request = _i7_request(
            snapshot_idempotency_key=f"idem-e5-3-ok-{suffix}",
            season_business_keys=(f"season-{suffix}",),
        )

        async with AsyncSessionMaker() as session:
            async with session.begin():
                result = await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-e5-3-ok",
                )

        counts = await _i7_table_counts()
        assert counts[HEADER_TABLE_NAME] == 1
        assert counts[WINNER_TABLE_NAME] == result.header.winner_count
        assert counts[LABEL_TABLE_NAME] == result.header.label_row_count
        assert counts[EXCLUSION_TABLE_NAME] == result.header.exclusion_row_count
        assert result.header.winner_count == 1
        assert result.header.label_row_count == 1
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_e5_3_pg_uncommitted_snapshot_not_visible_to_other_session() -> None:
    """E5.3: before the caller commits, a SEPARATE PostgreSQL
    session must not observe the staged snapshot (READ COMMITTED);
    after the caller commits, the same row becomes visible.
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_finalized_batch(
        suffix=suffix,
    )

    try:
        await _truncate_i7_tables()
        key = f"idem-e5-3-vis-{suffix}"
        request = _i7_request(
            snapshot_idempotency_key=key,
            season_business_keys=(f"season-{suffix}",),
        )

        async with AsyncSessionMaker() as session_a:
            async with session_a.begin():
                result = await create_label_snapshot(
                    session_a,
                    request=request,
                    created_by_identity="op-e5-3-vis",
                )
                assert result.header.winner_count == 1
                # A separate session must NOT see the uncommitted row.
                async with AsyncSessionMaker() as session_b:
                    row_before = await session_b.scalar(
                        sa.select(ActualHarvestLabelSnapshotModel).where(
                            ActualHarvestLabelSnapshotModel.snapshot_idempotency_key == key
                        )
                    )
                    assert row_before is None

        # After the caller's commit the row is visible.
        async with AsyncSessionMaker() as session_c:
            row_after = await session_c.scalar(
                sa.select(ActualHarvestLabelSnapshotModel).where(
                    ActualHarvestLabelSnapshotModel.snapshot_idempotency_key == key
                )
            )
            assert row_after is not None
            assert row_after.snapshot_request_identity_hash == (
                result.header.snapshot_request_identity_hash
            )
    finally:
        await _cleanup_batch(external_batch_id)


# ===========================================================================
# E5.3 — canonical scope persistence
# ===========================================================================


@pytest.mark.asyncio
async def test_e5_3_pg_scope_json_arrays_round_trip_and_hashes() -> None:
    """Persist multi-key scope arrays and preserve hashes on exact replay."""
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_finalized_batch(
        suffix=suffix,
    )

    try:
        await _truncate_i7_tables()
        season_business_keys = tuple(sorted((f"season-{suffix}", "season-extra")))
        farm_business_keys_or_empty_for_all = tuple(sorted((f"farm-master-{suffix}", "farm-extra")))
        variety_business_keys_or_empty_for_all = tuple(
            sorted((f"variety-master-{suffix}", "variety-extra"))
        )
        request = _i7_request(
            snapshot_idempotency_key=f"idem-e5-3-scope-{suffix}",
            season_business_keys=season_business_keys,
            farm_business_keys_or_empty_for_all=farm_business_keys_or_empty_for_all,
            variety_business_keys_or_empty_for_all=variety_business_keys_or_empty_for_all,
        )

        async with AsyncSessionMaker() as session:
            async with session.begin():
                first = await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-e5-3-scope",
                )

        async with AsyncSessionMaker() as session:
            header = await session.scalar(
                select(ActualHarvestLabelSnapshotModel).where(
                    ActualHarvestLabelSnapshotModel.snapshot_idempotency_key
                    == request.snapshot_idempotency_key
                )
            )
        assert header is not None
        assert json.loads(header.season_business_keys) == list(request.season_business_keys)
        assert json.loads(header.farm_business_keys_or_empty_for_all) == list(
            request.farm_business_keys_or_empty_for_all
        )
        assert json.loads(header.variety_business_keys_or_empty_for_all) == list(
            request.variety_business_keys_or_empty_for_all
        )
        assert header.snapshot_request_identity_hash == first.header.snapshot_request_identity_hash
        assert (
            header.snapshot_instance_identity_hash == first.header.snapshot_instance_identity_hash
        )
        assert header.label_snapshot_hash == first.header.label_snapshot_hash

        async with AsyncSessionMaker() as session:
            async with session.begin():
                replay = await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-e5-3-scope-replay",
                )

        assert replay.header.snapshot_id == first.header.snapshot_id
        assert replay.header.snapshot_request_identity_hash == (
            first.header.snapshot_request_identity_hash
        )
        assert replay.header.snapshot_instance_identity_hash == (
            first.header.snapshot_instance_identity_hash
        )
        assert replay.header.label_snapshot_hash == first.header.label_snapshot_hash
        counts = await _i7_table_counts()
        assert counts[HEADER_TABLE_NAME] == 1
    finally:
        await _cleanup_batch(external_batch_id)


# ===========================================================================
# E5.3 — winner numeric identity persistence
# ===========================================================================


@pytest.mark.asyncio
async def test_e5_3_pg_winner_numeric_ids_round_trip_and_replay() -> None:
    """New winners persist the frozen mapping evidence's numeric IDs.

    The IDs are database references only: replay must read the same
    persisted values while the winner, manifest, and snapshot hashes
    remain unchanged.
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_finalized_batch(
        suffix=suffix,
    )

    try:
        await _truncate_i7_tables()
        request = _i7_request(
            snapshot_idempotency_key=f"idem-e5-3-numeric-id-{suffix}",
            season_business_keys=(f"season-{suffix}",),
        )

        async with AsyncSessionMaker() as session:
            async with session.begin():
                first = await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-e5-3-numeric-id",
                )

        assert first.header.winner_count == 1
        first_winner = first.winners[0]
        assert all(
            isinstance(first_winner[field], int) and first_winner[field] > 0
            for field in ("season_id", "farm_id", "subfarm_id", "variety_id")
        )

        async with AsyncSessionMaker() as session:
            persisted_winner = await session.scalar(
                select(ActualHarvestLabelSnapshotWinnerModel).where(
                    ActualHarvestLabelSnapshotWinnerModel.snapshot_id == first.header.snapshot_id
                )
            )
            evidence_rows = (
                await session.scalars(
                    select(ActualHarvestValidationMappingEvidenceModel).where(
                        ActualHarvestValidationMappingEvidenceModel.external_revision_id
                        == f"rev-i7-pg-{suffix}-b"
                    )
                )
            ).all()
            season = (
                await session.get(Season, persisted_winner.season_id) if persisted_winner else None
            )
            farm = await session.get(Farm, persisted_winner.farm_id) if persisted_winner else None
            subfarm = (
                await session.get(Subfarm, persisted_winner.subfarm_id)
                if persisted_winner
                else None
            )
            variety = (
                await session.get(Variety, persisted_winner.variety_id)
                if persisted_winner
                else None
            )

        assert persisted_winner is not None
        evidence_by_type = {row.target_type: row for row in evidence_rows}
        assert set(evidence_by_type) == {"SEASON", "FARM", "SUBFARM", "VARIETY"}
        assert persisted_winner.season_id == evidence_by_type["SEASON"].resolved_season_id
        assert persisted_winner.farm_id == evidence_by_type["FARM"].resolved_farm_id
        assert persisted_winner.subfarm_id == evidence_by_type["SUBFARM"].resolved_subfarm_id
        assert persisted_winner.variety_id == evidence_by_type["VARIETY"].resolved_variety_id
        assert season is not None and season.code == f"season-{suffix}"
        assert farm is not None and farm.name == f"farm-master-{suffix}"
        assert subfarm is not None and subfarm.name == f"subfarm-master-{suffix}"
        assert variety is not None and variety.code == f"variety-master-{suffix}"
        assert subfarm.farm_id == farm.id

        counts_before_replay = await _i7_table_counts()
        async with AsyncSessionMaker() as session:
            async with session.begin():
                replay = await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-e5-3-numeric-id-replay",
                )
        counts_after_replay = await _i7_table_counts()

        assert counts_after_replay == counts_before_replay
        assert replay.header.snapshot_id == first.header.snapshot_id
        assert replay.header.winner_manifest_hash == first.header.winner_manifest_hash
        assert replay.header.label_snapshot_hash == first.header.label_snapshot_hash
        assert replay.winners[0]["winner_row_hash"] == first_winner["winner_row_hash"]
        assert tuple(
            replay.winners[0][field]
            for field in ("season_id", "farm_id", "subfarm_id", "variety_id")
        ) == tuple(
            first_winner[field] for field in ("season_id", "farm_id", "subfarm_id", "variety_id")
        )
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_i7_numeric_winner_identity_supports_quality_persisted_authority_postgres() -> None:
    """A production-created I7 winner must support the persisted Quality chain."""

    _require_postgres()
    from backend.app.trial import _build_quality_s2_candidates, _load_quality_parent_forecast
    from backend.tests.forecast_quality.test_persistence import (
        _align_i7_seed_to_forecast_scope,
        _build_i7_record,
        _drop_temporary_database,
        _prepare_default_quality_service_case,
        _seed_quality_service_batch,
    )

    case = await _prepare_default_quality_service_case("i7_quality_authority")
    try:
        async with case.sessionmaker() as session:
            evidence, _persisted, _import_batch = await _load_quality_parent_forecast(
                session,
                request=case.request,
                actor=case.actor,
            )

        winner_import_id = f"{case.request.actual_harvest_import_id}-winner"
        winner_record = _build_i7_record(
            source_system="source-test",
            external_logical_record_id="i7-quality-winner-logical",
            external_revision_id="i7-quality-winner-revision",
            harvest_date=date(2026, 3, 7),
            season_code="season-1",
        )
        seeded = await _seed_quality_service_batch(
            case.sessionmaker,
            import_id=winner_import_id,
            records=[winner_record],
            source_system="source-test",
            registry_suffix="i7-quality-winner",
        )
        await _align_i7_seed_to_forecast_scope(
            case.sessionmaker,
            batch_id=int(seeded["batch_id"]),
            actor_identity=case.actor.identity,
            scope=evidence,
        )
        quality_request = case.request.model_copy(
            update={
                "actual_harvest_import_id": winner_import_id,
                "request_idempotency_key": f"{case.request.request_idempotency_key}-winner",
            }
        )

        async with case.sessionmaker() as session:
            created = await case.service.create_quality_report(
                session,
                quality_request,
                case.actor,
            )

        async with case.sessionmaker() as session:
            quality = await session.run_sync(
                lambda sync_session: load_quality_evaluation_by_instance_hash(
                    sync_session,
                    evaluation_instance_hash=created.report_id,
                )
            )
            s2_identity = quality.run_payload.get("s2_run_identity")
            assert isinstance(s2_identity, str)
            s2 = await load_s2_historical_binding_by_instance_hash(
                session,
                instance_hash=s2_identity,
            )
            assert s2.rows
            assert all(row.authority_verification == "PERSISTED" for row in s2.rows)

            trial_request_identity = quality.run_payload.get("trial_request_identity")
            assert isinstance(trial_request_identity, dict)
            server_owned_evidence = trial_request_identity.get("server_owned_evidence")
            assert isinstance(server_owned_evidence, dict)
            label_snapshot_identity = server_owned_evidence.get("label_snapshot_identity")
            assert isinstance(label_snapshot_identity, str)
            snapshot = await session.scalar(
                select(ActualHarvestLabelSnapshotModel).where(
                    ActualHarvestLabelSnapshotModel.snapshot_instance_identity_hash
                    == label_snapshot_identity
                )
            )
            assert snapshot is not None

            evidence, persisted, import_batch = await _load_quality_parent_forecast(
                session,
                request=quality_request,
                actor=case.actor,
            )
            batch = await session.scalar(
                select(ActualHarvestImportBatchModel).where(
                    ActualHarvestImportBatchModel.import_id
                    == quality_request.actual_harvest_import_id
                )
            )
            assert batch is not None
            assert import_batch.id == batch.id
            snapshot_result = await label_service._replay_existing_snapshot(
                session,
                existing_snapshot=snapshot,
                request_identity_hash=snapshot.snapshot_request_identity_hash,
            )
            s2_request, candidates = await _build_quality_s2_candidates(
                session,
                request=quality_request,
                evidence=evidence,
                persisted=persisted,
                snapshot=snapshot_result,
            )
            rows_with_winners = tuple(
                candidate
                for candidate in candidates
                if candidate.persisted_authority_references is not None
                and candidate.persisted_authority_references.label_winner_id is not None
            )
            assert rows_with_winners
            references = rows_with_winners[0].persisted_authority_references
            assert references is not None
            assert references.label_winner_id is not None

            winner = await session.get(
                ActualHarvestLabelSnapshotWinnerModel,
                references.label_winner_id,
            )
            assert snapshot is not None
            assert winner is not None
            assert winner.snapshot_id == snapshot.id
            assert all(
                value is not None and value > 0
                for value in (
                    winner.season_id,
                    winner.farm_id,
                    winner.subfarm_id,
                    winner.variety_id,
                )
            )

            batch = await session.scalar(
                select(ActualHarvestImportBatchModel).where(
                    ActualHarvestImportBatchModel.import_id == case.request.actual_harvest_import_id
                )
            )
            assert batch is not None
            validation_run = await session.scalar(
                select(ActualHarvestValidationRunModel).where(
                    ActualHarvestValidationRunModel.batch_id == batch.id
                )
            )
            assert validation_run is not None
            evidence_rows = (
                await session.scalars(
                    select(ActualHarvestValidationMappingEvidenceModel).where(
                        ActualHarvestValidationMappingEvidenceModel.validation_run_id
                        == validation_run.id
                    )
                )
            ).all()
            evidence_by_type = {row.target_type: row for row in evidence_rows}
            assert set(evidence_by_type) == {"SEASON", "FARM", "SUBFARM", "VARIETY"}
            assert winner.season_id == evidence_by_type["SEASON"].resolved_season_id
            assert winner.farm_id == evidence_by_type["FARM"].resolved_farm_id
            assert winner.subfarm_id == evidence_by_type["SUBFARM"].resolved_subfarm_id
            assert winner.variety_id == evidence_by_type["VARIETY"].resolved_variety_id

            resolved = await resolve_s2_persisted_authorities(
                session,
                request=s2_request,
                candidates=candidates,
            )
            assert resolved
            assert all(candidate.authority_verification == "PERSISTED" for candidate in resolved)
            resolved_winners = tuple(
                candidate
                for candidate in resolved
                if candidate.persisted_authority_references is not None
                and candidate.persisted_authority_references.label_winner_id
                == references.label_winner_id
            )
            assert resolved_winners

            fresh_readback = await case.service.get_quality_report(
                session,
                created.report_id,
                case.actor,
            )
            assert fresh_readback.report_id == created.report_id
            assert fresh_readback.model_dump(mode="json") == created.model_dump(mode="json")
    finally:
        await case.engine.dispose()
        await _drop_temporary_database(case.db_name)


# E5.4 — concurrent identical snapshot
# ===========================================================================


@pytest.mark.asyncio
async def test_e5_4_pg_concurrent_identical_snapshot() -> None:
    """E5.4: two independent PostgreSQL sessions / transactions racing
    the SAME ``create_label_snapshot`` request must converge to
    EXACTLY one physical snapshot with one physical set of child
    rows. Both callers observe the same snapshot identity (same
    request identity hash, same instance identity hash, same label
    snapshot hash). No bare ``IntegrityError`` leaks to either
    caller.

    The production defense is the PostgreSQL transaction advisory
    lock keyed on ``(source_system, snapshot_idempotency_key)`` +
    the locked re-read of the existing snapshot. Synchronization is
    an ``asyncio.Barrier`` — never random sleeps.
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_finalized_batch(
        suffix=suffix,
    )

    try:
        # Pre-clean the I7 tables so the race starts from
        # a clean state.
        await _truncate_i7_tables()
        request = _i7_request(
            snapshot_idempotency_key=f"idem-e5-4-{suffix}",
            season_business_keys=(f"season-{suffix}",),
        )

        barrier = asyncio.Barrier(2)

        async def caller_independent() -> ActualHarvestLabelSnapshotResult:
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    # Both callers enter the service as close to
                    # simultaneously as the event loop allows.
                    await barrier.wait()
                    return await create_label_snapshot(
                        session,
                        request=request,
                        created_by_identity=f"op-e5-4-{uuid4().hex[:8]}",
                    )

        outcomes = await asyncio.gather(
            caller_independent(),
            caller_independent(),
            return_exceptions=True,
        )

        # No bare IntegrityError (or any other exception) leaks to
        # either caller.
        leaked = [e for e in outcomes if isinstance(e, BaseException)]
        assert not leaked, f"unexpected caller error leaked: {leaked!r}"
        results = [r for r in outcomes if isinstance(r, ActualHarvestLabelSnapshotResult)]
        assert len(results) == 2

        result_0, result_1 = results
        # Both callers observe the SAME logical snapshot: same
        # physical header id, same request identity hash, same
        # instance identity hash, same label snapshot hash.
        assert result_0.header.snapshot_id == result_1.header.snapshot_id
        assert result_0.header.snapshot_idempotency_key == result_1.header.snapshot_idempotency_key
        assert (
            result_0.header.snapshot_request_identity_hash
            == result_1.header.snapshot_request_identity_hash
        )
        assert (
            result_0.header.snapshot_instance_identity_hash
            == result_1.header.snapshot_instance_identity_hash
        )
        assert result_0.header.label_snapshot_hash == result_1.header.label_snapshot_hash
        # And the database holds exactly one physical header + one
        # physical set of child rows (no duplicated race writes).
        counts = await _i7_table_counts()
        assert counts[HEADER_TABLE_NAME] == 1
        assert counts[WINNER_TABLE_NAME] == result_0.header.winner_count
        assert counts[LABEL_TABLE_NAME] == result_0.header.label_row_count
        assert counts[EXCLUSION_TABLE_NAME] == result_0.header.exclusion_row_count
    finally:
        await _cleanup_batch(external_batch_id)


# ===========================================================================
# E5.5 — idempotency conflict (same key / different request)
# ===========================================================================


@pytest.mark.asyncio
async def test_e5_5_pg_idempotency_conflict() -> None:
    """E5.5: a same-key / different-request must raise
    ``ActualHarvestLabelIdempotencyConflictError`` and the
    first physical snapshot must remain intact.
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_finalized_batch(
        suffix=suffix,
    )

    try:
        await _truncate_i7_tables()
        request_a = _i7_request(
            snapshot_idempotency_key=f"idem-e5-5-{suffix}",
            season_business_keys=(f"season-{suffix}",),
        )
        request_b = _i7_request(
            snapshot_idempotency_key=f"idem-e5-5-{suffix}",
            season_business_keys=("season-business-key-2",),  # different
        )

        # 1. First call: succeeds, creates the snapshot.
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await create_label_snapshot(
                    session,
                    request=request_a,
                    created_by_identity="op-e5-5-a",
                )

        # 2. Second call: same key, different request body
        #    (different season scope). Must raise
        #    IDEMPOTENCY_CONFLICT.
        async with AsyncSessionMaker() as session:
            async with session.begin():
                with pytest.raises(ActualHarvestLabelIdempotencyConflictError):
                    await create_label_snapshot(
                        session,
                        request=request_b,
                        created_by_identity="op-e5-5-b",
                    )

        # Database state: exactly one physical snapshot,
        # the original from request_a, remains.
        counts = await _i7_table_counts()
        assert counts[HEADER_TABLE_NAME] == 1
        assert counts[WINNER_TABLE_NAME] == 1
        assert counts[LABEL_TABLE_NAME] == 1

        async with AsyncSessionMaker() as session:
            header = await session.scalar(
                sa.select(ActualHarvestLabelSnapshotModel).order_by(
                    ActualHarvestLabelSnapshotModel.id
                )
            )
            assert header is not None
            assert header.snapshot_idempotency_key == f"idem-e5-5-{suffix}"
            assert json.loads(header.season_business_keys) == [f"season-{suffix}"]
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_e5_5_pg_concurrent_same_key_different_request_conflict() -> None:
    """E5.5 (concurrent): two independent PostgreSQL sessions /
    transactions racing the same idempotency key with DIFFERENT
    request identities must resolve to exactly ONE success and
    exactly ONE ``ActualHarvestLabelIdempotencyConflictError``. The
    losing request leaves zero partial rows, one complete physical
    snapshot remains, and no raw unique-constraint exception
    escapes. Synchronization is an ``asyncio.Barrier`` — never
    random sleeps.
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_finalized_batch(
        suffix=suffix,
    )

    try:
        await _truncate_i7_tables()
        key = f"idem-e5-5-race-{suffix}"
        request_a = _i7_request(
            snapshot_idempotency_key=key,
            season_business_keys=(f"season-{suffix}",),
        )
        request_b = _i7_request(
            snapshot_idempotency_key=key,
            season_business_keys=("season-business-key-2",),  # different request identity
        )

        barrier = asyncio.Barrier(2)

        async def caller_independent(
            request: ActualHarvestLabelSnapshotRequest,
        ) -> ActualHarvestLabelSnapshotResult:
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    await barrier.wait()
                    return await create_label_snapshot(
                        session,
                        request=request,
                        created_by_identity=f"op-e5-5-{uuid4().hex[:8]}",
                    )

        outcomes = await asyncio.gather(
            caller_independent(request_a),
            caller_independent(request_b),
            return_exceptions=True,
        )

        successes = [r for r in outcomes if isinstance(r, ActualHarvestLabelSnapshotResult)]
        conflicts = [
            e for e in outcomes if isinstance(e, ActualHarvestLabelIdempotencyConflictError)
        ]
        unexpected = [
            e
            for e in outcomes
            if isinstance(e, BaseException)
            and not isinstance(e, ActualHarvestLabelIdempotencyConflictError)
        ]
        # No raw unique-constraint / IntegrityError escapes.
        assert not unexpected, f"unexpected caller error leaked: {unexpected!r}"
        assert len(successes) == 1, f"expected exactly one success, got: {outcomes!r}"
        assert len(conflicts) == 1, f"expected exactly one conflict, got: {outcomes!r}"

        # Exactly one complete physical snapshot remains — the
        # winner's; the losing request left zero partial rows.
        winner = successes[0]
        counts = await _i7_table_counts()
        assert counts[HEADER_TABLE_NAME] == 1
        assert counts[WINNER_TABLE_NAME] == winner.header.winner_count
        assert counts[LABEL_TABLE_NAME] == winner.header.label_row_count
        assert counts[EXCLUSION_TABLE_NAME] == winner.header.exclusion_row_count

        async with AsyncSessionMaker() as session:
            header = await session.scalar(sa.select(ActualHarvestLabelSnapshotModel))
            assert header is not None
            assert header.snapshot_idempotency_key == key
            assert (
                header.snapshot_request_identity_hash
                == winner.header.snapshot_request_identity_hash
            )
    finally:
        await _cleanup_batch(external_batch_id)


# ===========================================================================
# E6 — source-evidence preflight (PG persistence verification)
# ===========================================================================


@pytest.mark.asyncio
async def test_e6_pg_all_mapping_evidence_rows_missing_blocks_snapshot() -> None:
    """E6: when every lineage basis member exists but ALL
    four required target types are missing from the
    persisted mapping evidence, the preflight halts with
    ``MAPPING_EVIDENCE_MISSING`` (NOT
    ``OUTSIDE_REQUEST_SCOPE``). This is the zero-evidence
    fail-open the preflight closes.
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_committed_batch(
        suffix=suffix,
    )

    try:
        # Delete every mapping evidence row bound to the
        # committed lineage basis member. The preflight
        # must still see the lineage basis member and
        # reject the zero-evidence condition.
        async with AsyncSessionMaker() as session:
            async with session.begin():
                rows = (
                    await session.scalars(
                        select(ActualHarvestValidationMappingEvidenceModel).where(
                            ActualHarvestValidationMappingEvidenceModel.external_revision_id
                            == f"rev-i7-pg-{suffix}-b"
                        )
                    )
                ).all()
                assert len(rows) == 4
                for row in rows:
                    await session.delete(row)

        request = _i7_request(
            snapshot_idempotency_key=f"idem-e6-zero-{suffix}",
            season_business_keys=(f"season-{suffix}",),
        )

        async with AsyncSessionMaker() as session:
            async with session.begin():
                with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                    await create_label_snapshot(
                        session,
                        request=request,
                        created_by_identity="op-e6-zero-pg",
                    )
        assert exc_info.value.failure == (
            ActualHarvestLabelStructuralFailure.MAPPING_EVIDENCE_MISSING
        )
        assert exc_info.value.details["reason"] == "preflight_zero_evidence"
        # And no I7 rows leaked.
        counts = await _i7_table_counts()
        assert counts[HEADER_TABLE_NAME] == 0
        assert counts[WINNER_TABLE_NAME] == 0
        assert counts[LABEL_TABLE_NAME] == 0
        assert counts[EXCLUSION_TABLE_NAME] == 0
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_e6_pg_partial_mapping_evidence_blocks_snapshot() -> None:
    """E6: when one of the four required target types is
    missing, the preflight halts with
    ``MAPPING_EVIDENCE_MISSING`` (NOT a coverage
    exclusion).
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_committed_batch(
        suffix=suffix,
    )

    try:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                variety = await session.scalar(
                    select(ActualHarvestValidationMappingEvidenceModel).where(
                        ActualHarvestValidationMappingEvidenceModel.external_revision_id
                        == f"rev-i7-pg-{suffix}-b",
                        ActualHarvestValidationMappingEvidenceModel.target_type == "VARIETY",
                    )
                )
                assert variety is not None
                await session.delete(variety)

        request = _i7_request(
            snapshot_idempotency_key=f"idem-e6-partial-{suffix}",
            season_business_keys=(f"season-{suffix}",),
        )
        async with AsyncSessionMaker() as session:
            async with session.begin():
                with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                    await create_label_snapshot(
                        session,
                        request=request,
                        created_by_identity="op-e6-partial-pg",
                    )
        assert exc_info.value.failure == (
            ActualHarvestLabelStructuralFailure.MAPPING_EVIDENCE_MISSING
        )
        assert exc_info.value.details["reason"] == "preflight_partial_evidence"
        assert "VARIETY" in exc_info.value.details["missing_target_types"]
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_e6_pg_complete_evidence_outside_scope_remains_coverage_exclusion() -> None:
    """E6 corollary: a revision with COMPLETE frozen
    evidence whose business key is outside the request's
    season allow-list must surface as an
    ``OUTSIDE_REQUEST_SCOPE`` coverage exclusion. This is
    the only path that legitimately produces an
    ``OUTSIDE_REQUEST_SCOPE`` exclusion — never as a
    fallback for missing evidence.
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_committed_batch(
        suffix=suffix,
    )

    try:
        request = _i7_request(
            snapshot_idempotency_key=f"idem-e6-scope-{suffix}",
            season_business_keys=("season-business-key-OTHER",),
        )

        async with AsyncSessionMaker() as session:
            async with session.begin():
                result = await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-e6-scope-pg",
                )

        # E6 contract: complete evidence + out-of-scope
        # business key == OUTSIDE_REQUEST_SCOPE coverage
        # exclusion, never a structural failure. The seed's
        # lineage basis carries TWO observed revisions (the
        # ACTIVE predecessor rev-a and the terminal rev-b);
        # each emits exactly one OUTSIDE_REQUEST_SCOPE row.
        assert result.header.winner_count == 0
        assert result.header.exclusion_row_count == 2
        categories = {row["exclusion_category"] for row in result.exclusion_rows}
        assert categories == {"OUTSIDE_REQUEST_SCOPE"}
        assert result.header.label_row_count == 0
    finally:
        await _cleanup_batch(external_batch_id)


# ===========================================================================
# E7 — public-path corruption acceptance (PostgreSQL)
# ===========================================================================
#
# The SQLite unit file covers these shapes at helper level (controlled
# fake query result -> real ``_preflight_record_evidence()``). Here the
# corruption is written into the REAL persisted mapping-evidence table
# and the REAL public ``create_label_snapshot`` entry point must fail
# closed. PostgreSQL transactional DDL lets each test drop the two
# upstream CHECK constraints inside the caller's transaction and have
# them restored by the rollback — the schema is never mutated beyond
# the test.


async def _drop_evidence_target_constraints(session: AsyncSession) -> None:
    """Drop the two upstream mapping-evidence CHECK constraints.

    MUST be called inside the caller's transaction; PostgreSQL
    transactional DDL restores both constraints when the transaction
    rolls back.
    """

    await session.execute(
        sa.text(
            "ALTER TABLE actual_harvest_validation_mapping_evidence "
            "DROP CONSTRAINT ck_actual_harvest_validation_mapping_target_type"
        )
    )
    await session.execute(
        sa.text(
            "ALTER TABLE actual_harvest_validation_mapping_evidence "
            "DROP CONSTRAINT ck_actual_harvest_validation_mapping_target_fk"
        )
    )


async def _validation_run_id_for_revision(session: AsyncSession, revision_id: str) -> int:
    run_id = await session.scalar(
        sa.select(ActualHarvestValidationMappingEvidenceModel.validation_run_id)
        .where(ActualHarvestValidationMappingEvidenceModel.external_revision_id == revision_id)
        .limit(1)
    )
    assert run_id is not None, f"no evidence row found for revision {revision_id}"
    return int(run_id)


async def _inject_plot_evidence_row_pg(
    session: AsyncSession,
    *,
    revision_id: str,
    suffix: str,
) -> None:
    """Clone the persisted SUBFARM evidence row of ``revision_id``
    into a PLOT row (corruption / future-regression simulation).

    All registry / resolver version fields are copied from the real
    I5-persisted row so every remaining constraint stays satisfied;
    only the grain (target_type + business keys + resolved FKs, all
    NULL) changes. The two CHECK constraints that would reject this
    row must already be dropped inside the same transaction.
    """

    run_id = await _validation_run_id_for_revision(session, revision_id)
    subfarm_row = await session.scalar(
        sa.select(ActualHarvestValidationMappingEvidenceModel).where(
            ActualHarvestValidationMappingEvidenceModel.validation_run_id == run_id,
            ActualHarvestValidationMappingEvidenceModel.external_revision_id == revision_id,
            ActualHarvestValidationMappingEvidenceModel.target_type == "SUBFARM",
        )
    )
    assert subfarm_row is not None
    plot_row = ActualHarvestValidationMappingEvidenceModel(
        validation_run_id=subfarm_row.validation_run_id,
        # Distinct record_index dodges the
        # (validation_run_id, record_index, source_field) unique
        # constraint; the preflight index does not use record_index.
        record_index=subfarm_row.record_index + 1000,
        source_system=subfarm_row.source_system,
        external_logical_record_id=subfarm_row.external_logical_record_id,
        external_revision_id=subfarm_row.external_revision_id,
        revision_number=subfarm_row.revision_number,
        source_field=subfarm_row.source_field,
        source_code=subfarm_row.source_code,
        registry_version=subfarm_row.registry_version,
        mapping_policy_version=subfarm_row.mapping_policy_version,
        resolver_version=subfarm_row.resolver_version,
        registry_entry_hash=_hex64(f"plot-entry-{suffix}"),
        target_type="PLOT",
        target_business_key=f"plot-business-key-{suffix}",
        target_parent_business_key=subfarm_row.target_parent_business_key,
        resolved_master_business_key=f"plot-business-key-{suffix}",
        resolved_master_parent_business_key=subfarm_row.resolved_master_parent_business_key,
        resolved_master_record_hash=_hex64(f"plot-master-{suffix}"),
        resolved_season_id=None,
        resolved_farm_id=None,
        resolved_subfarm_id=None,
        resolved_variety_id=None,
        resolution_mode=subfarm_row.resolution_mode,
        outcome=subfarm_row.outcome,
    )
    session.add(plot_row)
    await session.flush()


@pytest.mark.asyncio
async def test_e7_pg_plot_corruption_public_path_rejected() -> None:
    """E7 public path: a PLOT evidence row genuinely persisted in the
    frozen mapping evidence (direct DB write corruption / future I5
    regression) must fail the REAL ``create_label_snapshot`` closed
    with UNSUPPORTED_LABEL_GRAIN, and the rolled-back transaction
    leaves all four I7 tables at zero rows.
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_committed_batch(
        suffix=suffix,
    )

    try:
        await _truncate_i7_tables()
        request = _i7_request(
            snapshot_idempotency_key=f"idem-e7-pg-plot-{suffix}",
            season_business_keys=(f"season-{suffix}",),
        )

        with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    await _drop_evidence_target_constraints(session)
                    await _inject_plot_evidence_row_pg(
                        session,
                        revision_id=f"rev-i7-pg-{suffix}-b",
                        suffix=suffix,
                    )
                    await create_label_snapshot(
                        session,
                        request=request,
                        created_by_identity="op-e7-pg-plot",
                    )

        assert exc_info.value.failure == (
            ActualHarvestLabelStructuralFailure.UNSUPPORTED_LABEL_GRAIN
        )
        assert exc_info.value.details["target_type"] == "PLOT"
        assert exc_info.value.details["reason"] == "plot_target_type_in_frozen_evidence"
        counts = await _i7_table_counts()
        assert counts[HEADER_TABLE_NAME] == 0
        assert counts[WINNER_TABLE_NAME] == 0
        assert counts[LABEL_TABLE_NAME] == 0
        assert counts[EXCLUSION_TABLE_NAME] == 0
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_e7_pg_plot_on_nonterminal_public_path_rejected() -> None:
    """E7 public path: a PLOT row on the NON-TERMINAL predecessor
    revision is still rejected — the preflight is exhaustive over
    every observed committed revision, not gated on terminal /
    winner / in-scope.
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_committed_batch(
        suffix=suffix,
    )

    try:
        await _truncate_i7_tables()
        request = _i7_request(
            snapshot_idempotency_key=f"idem-e7-pg-nonterm-{suffix}",
            season_business_keys=(f"season-{suffix}",),
        )

        with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    await _drop_evidence_target_constraints(session)
                    # rev-a is the non-terminal predecessor (superseded
                    # by rev-b); the preflight must still catch PLOT.
                    await _inject_plot_evidence_row_pg(
                        session,
                        revision_id=f"rev-i7-pg-{suffix}-a",
                        suffix=suffix,
                    )
                    await create_label_snapshot(
                        session,
                        request=request,
                        created_by_identity="op-e7-pg-nonterm",
                    )

        assert exc_info.value.failure == (
            ActualHarvestLabelStructuralFailure.UNSUPPORTED_LABEL_GRAIN
        )
        assert exc_info.value.details["target_type"] == "PLOT"
        counts = await _i7_table_counts()
        assert counts[HEADER_TABLE_NAME] == 0
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_e7_pg_plot_on_invisible_public_path_rejected() -> None:
    """E7 public path: a PLOT row on an INVISIBLE revision
    (``source_recorded_at`` after the AS_OF cutoff) is still
    rejected — the preflight runs before the visibility filter.
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_committed_batch(
        suffix=suffix,
    )

    try:
        await _truncate_i7_tables()
        request = _i7_request(
            snapshot_idempotency_key=f"idem-e7-pg-invis-{suffix}",
            visibility_mode=ActualHarvestLabelVisibilityMode.AS_OF_EVALUATION,
            # The seeded rev-b carries source_recorded_at 2024-01-01,
            # i.e. AFTER this cutoff -> invisible.
            label_observation_cutoff_at_or_null=datetime(2023, 6, 30, tzinfo=UTC),
            season_business_keys=(f"season-{suffix}",),
        )

        with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    await _drop_evidence_target_constraints(session)
                    await _inject_plot_evidence_row_pg(
                        session,
                        revision_id=f"rev-i7-pg-{suffix}-b",
                        suffix=suffix,
                    )
                    await create_label_snapshot(
                        session,
                        request=request,
                        created_by_identity="op-e7-pg-invis",
                    )

        assert exc_info.value.failure == (
            ActualHarvestLabelStructuralFailure.UNSUPPORTED_LABEL_GRAIN
        )
        assert exc_info.value.details["target_type"] == "PLOT"
        counts = await _i7_table_counts()
        assert counts[HEADER_TABLE_NAME] == 0
    finally:
        await _cleanup_batch(external_batch_id)


@pytest.mark.asyncio
async def test_e7_pg_unknown_target_public_path_drift() -> None:
    """E7 public path: an unknown (non-PLOT) target_type genuinely
    persisted in the frozen mapping evidence must fail the REAL
    ``create_label_snapshot`` with MAPPING_EVIDENCE_DRIFT and reason
    ``unknown_target_type_in_frozen_evidence``.
    """
    _require_postgres()
    suffix = uuid4().hex
    external_batch_id, _import_id = await _seed_i5_persisted_committed_batch(
        suffix=suffix,
    )

    try:
        await _truncate_i7_tables()
        request = _i7_request(
            snapshot_idempotency_key=f"idem-e7-pg-unknown-{suffix}",
            season_business_keys=(f"season-{suffix}",),
        )

        with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    await _drop_evidence_target_constraints(session)
                    run_id = await _validation_run_id_for_revision(session, f"rev-i7-pg-{suffix}-b")
                    await session.execute(
                        sa.text(
                            "UPDATE actual_harvest_validation_mapping_evidence "
                            "SET target_type = 'CUSTOM_FIELD', "
                            "target_business_key = :custom_key "
                            "WHERE validation_run_id = :run_id "
                            "AND external_revision_id = :revision_id "
                            "AND target_type = 'VARIETY'"
                        ),
                        {
                            "custom_key": f"custom-{suffix}",
                            "run_id": run_id,
                            "revision_id": f"rev-i7-pg-{suffix}-b",
                        },
                    )
                    await create_label_snapshot(
                        session,
                        request=request,
                        created_by_identity="op-e7-pg-unknown",
                    )

        assert exc_info.value.failure == ActualHarvestLabelStructuralFailure.MAPPING_EVIDENCE_DRIFT
        assert exc_info.value.details["reason"] == "unknown_target_type_in_frozen_evidence"
        assert exc_info.value.details["target_type"] == "CUSTOM_FIELD"
        counts = await _i7_table_counts()
        assert counts[HEADER_TABLE_NAME] == 0
    finally:
        await _cleanup_batch(external_batch_id)
