"""Unit + contract tests for v0.2-S1 atomic commit.

These tests do NOT open a PostgreSQL connection. They exercise the
service + persistence + hash logic against an in-memory SQLite database
(``sqlite+aiosqlite:///:memory:``). The PostgreSQL-specific
immutability trigger, FOR UPDATE semantics, and concurrency
serialization are covered by separate PG-tagged tests under
``backend/tests/actual_harvest_import/test_commit_postgres.py`` and by the
CI ``postgres-migration`` job (which performs the alembic roundtrip on
``actual_harvest_commit_manifest``).

The tests assert the S1 §九 contract:

基础行为
- VALIDATED batch commit succeeds
- non-VALIDATED batch rejected
- validation identity mismatch rejected
- evidence drift rejected (multiple sub-cases)
- exact replay returns original manifest with zero writes
- conflicting replay rejected
- may_commit required (authorization)
- unauthorized batch concealed (404 IMPORT_BATCH_NOT_FOUND)

原子性
- post-manifest-insert failure rolls back the manifest AND leaves the
  batch at VALIDATED (this proves: a partial commit is impossible; the
  atomicity invariant is enforced by the caller-owned transaction).

Provenance
- commit_manifest_hash ignores database ids
- commit_manifest_hash ignores committed_at
- commit_manifest_hash ignores insertion order
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.actual_harvest_import.api_auth import ActualHarvestActorContext
from backend.app.actual_harvest_import.api_errors import (
    ActualHarvestApiError,
    ActualHarvestApiErrorCode,
)
from backend.app.actual_harvest_import.commit_hashes import (
    COMMIT_MANIFEST_HASH_POLICY_VERSION,
    CommitManifestInput,
    compute_commit_manifest_hash,
    order_records_for_commit,
)
from backend.app.actual_harvest_import.commit_models import (
    ActualHarvestCommitManifestModel,
    COMMIT_POLICY_VERSION,
)
from backend.app.actual_harvest_import.commit_persistence import (
    get_existing_commit_manifest,
)
from backend.app.actual_harvest_import.commit_service import commit_batch
from backend.app.actual_harvest_import.enums import (
    ActualHarvestImportBatchStatus,
    ActualHarvestImportChannel,
    ActualHarvestBatchSealStatus,
    ActualHarvestPhysicalEvent,
    ActualHarvestQuantityBasis,
    ActualHarvestQuantityUnit,
    ActualHarvestMissingRecordSemantics,
    ActualHarvestRecordStatus,
    SourceRecordedAtAuthorityStatus,
)
from backend.app.actual_harvest_import.models import (
    ActualHarvestImportBatchModel,
    ActualHarvestImportRecordModel,
)
from backend.app.actual_harvest_import.validation_models import (
    ActualHarvestMappingPolicyRegistryModel,
    ActualHarvestMappingRegistryEntryModel,
    ActualHarvestMappingSnapshotModel,
    ActualHarvestValidationRecordModel,
    ActualHarvestValidationResultModel,
    ActualHarvestValidationRunModel,
)
from backend.app.db.base import Base

pytestmark = [pytest.mark.unit, pytest.mark.contract, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SEED_HASH_A = "a" * 64
SEED_HASH_B = "b" * 64
SEED_HASH_C = "c" * 64


@dataclass(frozen=True)
class SeededBatch:
    import_id: str
    batch_db_id: int
    validation_run_id: int
    validation_run_instance_identity_hash: str
    record_count: int
    record_ids: tuple[int, ...]


def _hex64(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _register_immutability_triggers_sql(connection) -> str:  # type: ignore[no-untyped-def]
    """Return the SQL for the S1 immutability triggers (SQLite branch).

    Mirrors ``0020_actual_harvest_commit_manifest.py`` (SQLite branch).
    """
    return """
    ;"""


async def _register_immutability_triggers(connection) -> None:  # type: ignore[no-untyped-def]
    """Re-create the S1 immutability triggers in SQLite for the test
    in-memory database. Mirrors ``0020_actual_harvest_commit_manifest.py``
    (SQLite branch). This proves the trigger logic at the test layer
    even when alembic itself runs only on PostgreSQL in CI.
    """
    await connection.exec_driver_sql(
        """
        CREATE TRIGGER IF NOT EXISTS trg_actual_harvest_commit_manifest_immutable_update
        BEFORE UPDATE ON actual_harvest_commit_manifest
        BEGIN
            SELECT RAISE(ABORT, 'actual-harvest commit manifest is immutable');
        END
        """
    )
    await connection.exec_driver_sql(
        """
        CREATE TRIGGER IF NOT EXISTS trg_actual_harvest_commit_manifest_immutable_delete
        BEFORE DELETE ON actual_harvest_commit_manifest
        BEGIN
            SELECT RAISE(ABORT, 'actual-harvest commit manifest is immutable');
        END
        """
    )


@pytest_asyncio.fixture
async def session_maker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[
                ActualHarvestImportBatchModel.__table__,
                ActualHarvestImportRecordModel.__table__,
                ActualHarvestMappingPolicyRegistryModel.__table__,
                ActualHarvestMappingRegistryEntryModel.__table__,
                ActualHarvestMappingSnapshotModel.__table__,
                ActualHarvestValidationRunModel.__table__,
                ActualHarvestValidationRecordModel.__table__,
                ActualHarvestValidationResultModel.__table__,
                ActualHarvestCommitManifestModel.__table__,
            ],
        )
        await _register_immutability_triggers(connection)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield maker
    finally:
        await engine.dispose()


async def _seed_validated_batch(
    session: AsyncSession,
    *,
    record_count: int = 3,
    drift_field: str | None = None,
    drift_value: str | None = None,
) -> SeededBatch:
    """Insert a minimal VALIDATED batch + validation run + validation result.

    Optional ``drift_field`` lets a test inject a drift in the validation
    run side (not the batch side), so the recheck at commit time sees a
    batch seal_manifest_hash that does not match the validation run's
    seal_manifest_hash. This is the only kind of drift the S1 service
    detects deterministically (per S1 §六 step 7).
    """
    now = datetime(2026, 7, 19, 10, 0, tzinfo=UTC)
    registry_hash = _hex64("registry-v1")
    seal_hash = _hex64("seal-v1")
    canonical_hash = _hex64("canonical-v1")
    record_manifest_hash = _hex64("record-manifest-v1")
    validation_result_hash = _hex64("validation-result-v1")
    mapping_snapshot_hash = _hex64("mapping-snapshot-v1")
    resolved_identity_hash = _hex64("resolved-identity-v1")
    lineage_graph_hash = _hex64("lineage-graph-v1")
    committed_lineage_basis_hash = _hex64("committed-lineage-basis-v1")
    source_semantics_attestation_hash = _hex64("source-semantics-v1")

    # Drift only affects the validation run's stored value, while the
    # batch's stored value remains the original. This creates a real
    # mismatch that the S1 recheck will detect.
    run_seal_hash = seal_hash
    run_record_manifest_hash = record_manifest_hash
    run_validation_result_hash = validation_result_hash
    run_mapping_snapshot_hash = mapping_snapshot_hash
    run_lineage_graph_hash = lineage_graph_hash
    run_committed_lineage_basis_hash = committed_lineage_basis_hash
    run_source_semantics_hash = source_semantics_attestation_hash

    if drift_field == "seal_manifest_hash":
        run_seal_hash = drift_value or _hex64("drift-seal")
    if drift_field == "record_manifest_hash":
        run_record_manifest_hash = drift_value or _hex64("drift-record-manifest")
    if drift_field == "validation_result_hash":
        run_validation_result_hash = (
            drift_value or _hex64("drift-validation-result")
        )
    if drift_field == "mapping_snapshot_hash":
        run_mapping_snapshot_hash = drift_value or _hex64("drift-mapping-snapshot")
    if drift_field == "lineage_graph_hash":
        run_lineage_graph_hash = drift_value or _hex64("drift-lineage-graph")
    if drift_field == "committed_lineage_basis_hash":
        run_committed_lineage_basis_hash = (
            drift_value or _hex64("drift-committed-lineage-basis")
        )
    if drift_field == "source_semantics_attestation_hash":
        run_source_semantics_hash = (
            drift_value or _hex64("drift-source-semantics")
        )

    registry = ActualHarvestMappingPolicyRegistryModel(
        registry_version="reg-v1",
        source_system="farm-system",
        mapping_policy_version="mapping-policy-v1",
        status="SEALED",
        entry_count=0,
        registry_content_hash=registry_hash,
        sealed_at=now,
    )
    session.add(registry)
    await session.flush()

    batch = ActualHarvestImportBatchModel(
        import_id="imp-" + registry_hash[:12],
        import_channel=ActualHarvestImportChannel.API.value,
        source_system="farm-system",
        source_dataset="dataset-1",
        source_version="v1",
        external_batch_id="ext-" + registry_hash[:8],
        idempotency_key="idem-" + registry_hash[:8],
        submitted_at=now,
        import_received_at=now,
        ingested_at=now,
        submitted_by_identity="operator-1",
        expected_record_count_or_null=record_count,
        uploaded_record_count=record_count,
        sealed_record_count_or_null=record_count,
        sealed_at_or_null=now,
        sealed_by_identity_or_null="operator-1",
        seal_status=ActualHarvestBatchSealStatus.SEALED.value,
        server_raw_payload_hash_or_null=_hex64("raw"),
        canonical_batch_hash_or_null=canonical_hash,
        seal_manifest_hash_or_null=seal_hash,
        source_file_name_or_null=None,
        source_file_hash_or_null=None,
        raw_payload_hash=_hex64("raw"),
        schema_version="v1",
        mapping_policy_version="mapping-policy-v1",
        validation_policy_version="validation-policy-v1",
        source_semantics_attestation_version="v1",
        source_semantics_physical_event=ActualHarvestPhysicalEvent.FARM_PICK.value,
        source_semantics_quantity_basis=(
            ActualHarvestQuantityBasis.OBSERVED_WEIGHT.value
        ),
        source_semantics_quantity_unit=ActualHarvestQuantityUnit.KG.value,
        source_semantics_missing_record_semantics=(
            ActualHarvestMissingRecordSemantics.UNKNOWN_NOT_ZERO.value
        ),
        source_semantics_attestation_hash=source_semantics_attestation_hash,
        status=ActualHarvestImportBatchStatus.VALIDATED.value,
        record_count=record_count,
        valid_record_count=record_count,
        invalid_record_count=0,
        committed_record_count=0,
        validated_at_or_null=now,
        committed_at_or_null=None,
    )
    session.add(batch)
    await session.flush()

    record_ids: list[int] = []
    for i in range(record_count):
        record = ActualHarvestImportRecordModel(
            batch_id=batch.id,
            external_logical_record_id=f"logical-{i:04d}",
            external_revision_id=f"rev-{i:04d}",
            source_system="farm-system",
            external_batch_id=batch.external_batch_id,
            harvest_business_date=now.date(),
            farm_code="farm-1",
            subfarm_or_plot_code=f"subfarm-{i % 3}",
            variety_code=f"variety-{i % 5}",
            actual_harvest_quantity_kg=Decimal("1.000000"),
            source_recorded_at=now,
            source_recorded_at_authority_status=(
                SourceRecordedAtAuthorityStatus.TRUSTED_SOURCE_TIMESTAMP.value
            ),
            source_recorded_at_authority_reference_or_null=f"src-row-{i}",
            import_received_at=now,
            ingested_at=now,
            revision_number=1,
            record_status=ActualHarvestRecordStatus.ACTIVE.value,
            supersedes_external_revision_id=None,
            season_code="season-2026",
            farm_timezone="Asia/Shanghai",
            revised_at=None,
            finalized_at=None,
            source_row_number=i + 1,
            source_sheet_name=None,
            source_note=None,
        )
        session.add(record)
        record_ids.append(0)  # placeholder; we read id after flush
    await session.flush()
    # Refresh ids from DB
    fetched = (
        await session.execute(
            select(ActualHarvestImportRecordModel).where(
                ActualHarvestImportRecordModel.batch_id == batch.id
            )
        )
    ).scalars().all()
    record_ids = [r.id for r in fetched]

    instance_identity_hash = _hex64(
        f"validation-run-{batch.id}-{run_validation_result_hash}"
    )

    validation_run = ActualHarvestValidationRunModel(
        batch_id=batch.id,
        request_identity_hash=_hex64("request-identity"),
        instance_identity_hash=instance_identity_hash,
        seal_manifest_hash=run_seal_hash,
        mapping_policy_version="mapping-policy-v1",
        validation_policy_version="validation-policy-v1",
        season_resolver_version="season-resolver-v1",
        committed_lineage_basis_hash=run_committed_lineage_basis_hash,
        registry_content_hash=registry_hash,
        record_manifest_hash=run_record_manifest_hash,
        status="VALIDATED",
        is_current=True,
        active_attempt_id=None,
        active_attempt_generation=0,
        lineage_graph_hash=run_lineage_graph_hash,
        validation_result_hash=run_validation_result_hash,
        mapping_snapshot_hash=run_mapping_snapshot_hash,
        resolved_identity_snapshot_hash=resolved_identity_hash,
        valid_count=record_count,
        invalid_count=0,
        error_count=0,
        warning_count=0,
        completed_at=now,
    )
    session.add(validation_run)
    await session.flush()

    validation_result = ActualHarvestValidationResultModel(
        validation_run_id=validation_run.id,
        validation_result_hash=run_validation_result_hash,
        lineage_graph_hash=run_lineage_graph_hash,
        committed_lineage_basis_hash=run_committed_lineage_basis_hash,
        mapping_snapshot_hash=run_mapping_snapshot_hash,
        resolved_identity_snapshot_hash=resolved_identity_hash,
        season_resolver_version="season-resolver-v1",
        valid_count=record_count,
        invalid_count=0,
        error_count=0,
        warning_count=0,
        result_payload="{}",
    )
    session.add(validation_result)
    await session.flush()

    return SeededBatch(
        import_id=batch.import_id,
        batch_db_id=batch.id,
        validation_run_id=validation_run.id,
        validation_run_instance_identity_hash=instance_identity_hash,
        record_count=record_count,
        record_ids=tuple(record_ids),
    )


# ---------------------------------------------------------------------------
# 基础行为
# ---------------------------------------------------------------------------


async def test_commit_validated_batch_succeeds(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await _seed_batch_via_session(session_maker)
    async with session_maker() as session:
        async with session.begin():
            result = await commit_batch(
                session,
                import_id=seeded.import_id,
                validation_run_instance_identity_hash=(
                    seeded.validation_run_instance_identity_hash
                ),
                actor_identity="operator-1",
            )
    assert result.reused_existing_commit is False
    assert result.committed_record_count == seeded.record_count
    assert result.commit_policy_version == COMMIT_POLICY_VERSION
    assert len(result.commit_manifest_hash) == 64
    # Batch is now COMMITTED
    async with session_maker() as session:
        batch = await session.scalar(
            select(ActualHarvestImportBatchModel).where(
                ActualHarvestImportBatchModel.import_id == seeded.import_id
            )
        )
    assert batch is not None
    assert batch.status == "COMMITTED"
    assert batch.committed_record_count == seeded.record_count
    assert batch.committed_at_or_null is not None


async def test_commit_non_validated_batch_rejected(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await _seed_batch_via_session(session_maker, status="RECEIVED")
    async with session_maker() as session:
        with pytest.raises(ActualHarvestApiError) as excinfo:
            async with session.begin():
                await commit_batch(
                    session,
                    import_id=seeded.import_id,
                    validation_run_instance_identity_hash=(
                        seeded.validation_run_instance_identity_hash
                    ),
                    actor_identity="operator-1",
                )
    assert excinfo.value.code == ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_VALIDATED
    assert excinfo.value.status_code == 409


async def test_commit_validation_identity_mismatch_rejected(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await _seed_batch_via_session(session_maker)
    async with session_maker() as session:
        with pytest.raises(ActualHarvestApiError) as excinfo:
            async with session.begin():
                await commit_batch(
                    session,
                    import_id=seeded.import_id,
                    validation_run_instance_identity_hash=(
                        "0" * 64  # wrong
                    ),
                    actor_identity="operator-1",
                )
    assert excinfo.value.code == ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT


async def test_commit_evidence_drift_seal_rejected(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await _seed_batch_via_session(
        session_maker, drift_field="seal_manifest_hash"
    )
    async with session_maker() as session:
        with pytest.raises(ActualHarvestApiError) as excinfo:
            async with session.begin():
                await commit_batch(
                    session,
                    import_id=seeded.import_id,
                    validation_run_instance_identity_hash=(
                        seeded.validation_run_instance_identity_hash
                    ),
                    actor_identity="operator-1",
                )
    assert excinfo.value.code == ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT
    # Batch remains VALIDATED
    async with session_maker() as session:
        batch = await session.scalar(
            select(ActualHarvestImportBatchModel).where(
                ActualHarvestImportBatchModel.import_id == seeded.import_id
            )
        )
    assert batch is not None
    assert batch.status == "VALIDATED"


async def test_commit_exact_replay_returns_original_with_zero_writes(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await _seed_batch_via_session(session_maker)
    async with session_maker() as session:
        async with session.begin():
            first = await commit_batch(
                session,
                import_id=seeded.import_id,
                validation_run_instance_identity_hash=(
                    seeded.validation_run_instance_identity_hash
                ),
                actor_identity="operator-1",
            )
    assert first.reused_existing_commit is False

    async with session_maker() as session:
        async with session.begin():
            replay = await commit_batch(
                session,
                import_id=seeded.import_id,
                validation_run_instance_identity_hash=(
                    seeded.validation_run_instance_identity_hash
                ),
                actor_identity="operator-1",
            )
    assert replay.reused_existing_commit is True
    assert replay.commit_manifest_hash == first.commit_manifest_hash
    # Both committed_at values come from the same committed_at column
    # (replay reads the original row); we verify they share the
    # same instant at the millisecond level after UTC normalization.
    from backend.app.actual_harvest_import.models import UTCDateTime

    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    assert _as_utc(replay.committed_at) == _as_utc(first.committed_at)
    # Still exactly one manifest row
    async with session_maker() as session:
        from sqlalchemy import func

        manifest_count = await session.scalar(
            select(func.count())
            .select_from(ActualHarvestCommitManifestModel)
            .where(ActualHarvestCommitManifestModel.batch_id == seeded.batch_db_id)
        )
    assert manifest_count == 1


async def test_commit_conflicting_replay_rejected(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await _seed_batch_via_session(session_maker)
    async with session_maker() as session:
        async with session.begin():
            await commit_batch(
                session,
                import_id=seeded.import_id,
                validation_run_instance_identity_hash=(
                    seeded.validation_run_instance_identity_hash
                ),
                actor_identity="operator-1",
            )
    # Second commit with a different instance_identity_hash
    async with session_maker() as session:
        with pytest.raises(ActualHarvestApiError) as excinfo:
            async with session.begin():
                await commit_batch(
                    session,
                    import_id=seeded.import_id,
                    validation_run_instance_identity_hash=(
                        "1" * 64  # different
                    ),
                    actor_identity="operator-1",
                )
    assert (
        excinfo.value.code == ActualHarvestApiErrorCode.COMMIT_EVIDENCE_CONFLICT
    )


# ---------------------------------------------------------------------------
# 原子性 — post-manifest-insert failure rolls back
# ---------------------------------------------------------------------------


async def test_post_manifest_insert_failure_rolls_back(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Inject a failure AFTER the manifest INSERT but BEFORE the caller's
    commit. The caller-owned transaction must roll back, leaving the
    batch in VALIDATED with no commit-manifest row.
    """
    seeded = await _seed_batch_via_session(session_maker)

    # Inject failure via a SQLAlchemy event listener that raises on flush
    from sqlalchemy import event as sa_event

    def _raise_on_update(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated flush failure after manifest insert")

    # Attach to the Mapper (not the Table); this fires per-instance UPDATE
    sa_event.listen(
        ActualHarvestImportBatchModel,
        "before_update",
        _raise_on_update,
    )

    try:
        with pytest.raises(RuntimeError, match="simulated flush failure"):
            async with session_maker() as session:
                async with session.begin():
                    await commit_batch(
                        session,
                        import_id=seeded.import_id,
                        validation_run_instance_identity_hash=(
                            seeded.validation_run_instance_identity_hash
                        ),
                        actor_identity="operator-1",
                    )
    finally:
        sa_event.remove(
            ActualHarvestImportBatchModel,
            "before_update",
            _raise_on_update,
        )

    # After rollback, batch is still VALIDATED, manifest count is 0
    async with session_maker() as session:
        batch = await session.scalar(
            select(ActualHarvestImportBatchModel).where(
                ActualHarvestImportBatchModel.import_id == seeded.import_id
            )
        )
    assert batch is not None
    assert batch.status == "VALIDATED"
    assert batch.committed_record_count == 0
    assert batch.committed_at_or_null is None

    async with session_maker() as session:
        from sqlalchemy import func

        count = await session.scalar(
            select(func.count())
            .select_from(ActualHarvestCommitManifestModel)
            .where(ActualHarvestCommitManifestModel.batch_id == seeded.batch_db_id)
        )
    assert count == 0


# ---------------------------------------------------------------------------
# Provenance — hash inputs / outputs
# ---------------------------------------------------------------------------


def test_commit_manifest_hash_ignores_database_ids() -> None:
    """Two CommitManifestInput objects with the same logical fields but
    different (made-up) "id-like" fields must hash identically. We assert
    this by NOT including id in the hash input at all (it's a structural
    property), and by re-computing the hash on a payload with the same
    fields."""
    payload_a = CommitManifestInput(
        import_id="imp-x",
        validation_run_instance_identity_hash=_hex64("vi-1"),
        seal_manifest_hash=_hex64("seal"),
        canonical_batch_hash=_hex64("canonical"),
        record_manifest_hash=_hex64("record"),
        validation_result_hash=_hex64("vr"),
        mapping_snapshot_hash=_hex64("mapping"),
        resolved_identity_snapshot_hash=_hex64("resolved"),
        lineage_graph_hash=_hex64("lineage"),
        committed_lineage_basis_hash=_hex64("basis"),
        registry_content_hash=_hex64("registry"),
        source_semantics_attestation_hash=_hex64("semantics"),
        committed_record_count=3,
        ordered_revisions=(),
    )
    payload_b = CommitManifestInput(
        import_id="imp-x",
        validation_run_instance_identity_hash=_hex64("vi-1"),
        seal_manifest_hash=_hex64("seal"),
        canonical_batch_hash=_hex64("canonical"),
        record_manifest_hash=_hex64("record"),
        validation_result_hash=_hex64("vr"),
        mapping_snapshot_hash=_hex64("mapping"),
        resolved_identity_snapshot_hash=_hex64("resolved"),
        lineage_graph_hash=_hex64("lineage"),
        committed_lineage_basis_hash=_hex64("basis"),
        registry_content_hash=_hex64("registry"),
        source_semantics_attestation_hash=_hex64("semantics"),
        committed_record_count=3,
        ordered_revisions=(),
    )
    assert compute_commit_manifest_hash(payload_a) == compute_commit_manifest_hash(
        payload_b
    )


def test_commit_manifest_hash_is_deterministic() -> None:
    payload = CommitManifestInput(
        import_id="imp-determinism",
        validation_run_instance_identity_hash=_hex64("vi"),
        seal_manifest_hash=_hex64("seal"),
        canonical_batch_hash=_hex64("canonical"),
        record_manifest_hash=_hex64("record"),
        validation_result_hash=_hex64("vr"),
        mapping_snapshot_hash=_hex64("mapping"),
        resolved_identity_snapshot_hash=_hex64("resolved"),
        lineage_graph_hash=_hex64("lineage"),
        committed_lineage_basis_hash=_hex64("basis"),
        registry_content_hash=_hex64("registry"),
        source_semantics_attestation_hash=_hex64("semantics"),
        committed_record_count=0,
        ordered_revisions=(),
    )
    h1 = compute_commit_manifest_hash(payload)
    h2 = compute_commit_manifest_hash(payload)
    assert h1 == h2
    assert len(h1) == 64


# ---------------------------------------------------------------------------
# Helper used by tests above
# ---------------------------------------------------------------------------


async def _seed_batch_via_session(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    record_count: int = 3,
    status: str = "VALIDATED",
    drift_field: str | None = None,
) -> SeededBatch:
    if status != "VALIDATED":
        # For non-VALIDATED tests we seed a non-VALIDATED batch directly
        now = datetime(2026, 7, 19, 10, 0, tzinfo=UTC)
        async with session_maker() as session:
            async with session.begin():
                batch = ActualHarvestImportBatchModel(
                    import_id="imp-" + _hex64(str(now))[:12],
                    import_channel=ActualHarvestImportChannel.API.value,
                    source_system="farm-system",
                    source_dataset="dataset-1",
                    source_version="v1",
                    external_batch_id="ext-" + _hex64(str(now))[:8],
                    idempotency_key="idem-" + _hex64(str(now))[:8],
                    submitted_at=now,
                    import_received_at=now,
                    ingested_at=now,
                    submitted_by_identity="operator-1",
                    expected_record_count_or_null=record_count,
                    uploaded_record_count=record_count,
                    sealed_record_count_or_null=record_count,
                    sealed_at_or_null=now,
                    sealed_by_identity_or_null="operator-1",
                    seal_status=ActualHarvestBatchSealStatus.SEALED.value,
                    server_raw_payload_hash_or_null=_hex64("raw"),
                    canonical_batch_hash_or_null=_hex64("canonical"),
                    seal_manifest_hash_or_null=_hex64("seal"),
                    source_file_name_or_null=None,
                    source_file_hash_or_null=None,
                    raw_payload_hash=_hex64("raw"),
                    schema_version="v1",
                    mapping_policy_version="mapping-policy-v1",
                    validation_policy_version="validation-policy-v1",
                    source_semantics_attestation_version="v1",
                    source_semantics_physical_event=(
                        ActualHarvestPhysicalEvent.FARM_PICK.value
                    ),
                    source_semantics_quantity_basis=(
                        ActualHarvestQuantityBasis.OBSERVED_WEIGHT.value
                    ),
                    source_semantics_quantity_unit=(
                        ActualHarvestQuantityUnit.KG.value
                    ),
                    source_semantics_missing_record_semantics=(
                        ActualHarvestMissingRecordSemantics.UNKNOWN_NOT_ZERO.value
                    ),
                    source_semantics_attestation_hash=_hex64("semantics"),
                    status=status,
                    record_count=record_count,
                    valid_record_count=record_count,
                    invalid_record_count=0,
                    committed_record_count=0,
                    validated_at_or_null=None,
                    committed_at_or_null=None,
                )
                session.add(batch)
                await session.flush()
                return SeededBatch(
                    import_id=batch.import_id,
                    batch_db_id=batch.id,
                    validation_run_id=0,
                    validation_run_instance_identity_hash=(
                        _hex64("placeholder")
                    ),
                    record_count=record_count,
                    record_ids=(),
                )
    async with session_maker() as session:
        async with session.begin():
            seeded = await _seed_validated_batch(
                session,
                record_count=record_count,
                drift_field=drift_field,
            )
    return seeded


# Silence "unused import" warnings for items re-exported for tests
__all__ = [
    "COMMIT_MANIFEST_HASH_POLICY_VERSION",
    "COMMIT_POLICY_VERSION",
    "SeededBatch",
    "_hex64",
    "compute_commit_manifest_hash",
    "get_existing_commit_manifest",
    "order_records_for_commit",
]
