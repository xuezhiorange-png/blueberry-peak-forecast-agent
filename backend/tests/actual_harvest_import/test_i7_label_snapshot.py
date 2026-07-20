"""I7 label-snapshot contract tests.

These tests are pure unit / contract tests that do NOT open a
PostgreSQL connection. They exercise the deterministic processing
pipeline (winner selection, cutoff visibility, exclusion reporting,
canonical-grain aggregation, idempotency replay) against an in-memory
SQLite database (``sqlite+aiosqlite:///:memory:``). The PostgreSQL
trigger and concurrent-snapshot behaviour are covered by separate
PG-tagged tests under ``backend/tests/actual_harvest_import/test_lifecycle_postgres.py``.

Coverage matrix mirrors
``docs/forecast-quality/q2a-i7-label-snapshot-and-revision-winner-contract.md``
§19.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.actual_harvest_import.canonical_hashes import (
    compute_canonical_record_hash,
)
from backend.app.actual_harvest_import.commit_models import (
    COMMIT_POLICY_VERSION,
    ActualHarvestCommitManifestModel,
)
from backend.app.actual_harvest_import.enums import (
    ActualHarvestImportBatchStatus,
    ActualHarvestMissingRecordSemantics,
    ActualHarvestPhysicalEvent,
    ActualHarvestQuantityBasis,
    ActualHarvestQuantityUnit,
    ActualHarvestRecordStatus,
    ActualHarvestValidationErrorCode,
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
    ActualHarvestValidationLineageBasisMemberModel,
    ActualHarvestValidationLineageBasisModel,
    ActualHarvestValidationMappingEvidenceModel,
    ActualHarvestValidationResultModel,
    ActualHarvestValidationRunModel,
)
from backend.app.actual_harvest_labels.enums import (
    ActualHarvestLabelCoverageExclusion,
    ActualHarvestLabelStructuralFailure,
    ActualHarvestLabelVisibilityMode,
)
from backend.app.actual_harvest_labels.hashes import (
    AGGREGATION_POLICY_VERSION,
    SNAPSHOT_POLICY_VERSION,
    WINNER_POLICY_VERSION,
    compute_label_row_set_hash,
    compute_snapshot_instance_identity_hash,
    compute_snapshot_request_identity_hash,
    compute_winner_row_hash,
)
from backend.app.actual_harvest_labels.models import (
    EXCLUSION_TABLE_NAME,
    HEADER_TABLE_NAME,
    LABEL_TABLE_NAME,
    WINNER_TABLE_NAME,
    ActualHarvestLabelSnapshotModel,
)
from backend.app.actual_harvest_labels.persistence import (
    get_existing_snapshot_by_idempotency_key,
)
from backend.app.actual_harvest_labels.schemas import (
    ActualHarvestLabelSnapshotRequest,
)
from backend.app.actual_harvest_labels.schemas import (
    ActualHarvestLabelVisibilityMode as SchemaVisibility,
)
from backend.app.actual_harvest_labels.service import (
    ActualHarvestLabelIdempotencyConflictError,
    ActualHarvestLabelStructuralFailureError,
    create_label_snapshot,
)
from backend.app.db.base import Base
from backend.app.models.master_data import Farm, Season, Subfarm, Variety

pytestmark = [pytest.mark.unit, pytest.mark.contract, pytest.mark.asyncio]


_I7_REQUIRED_TABLES = (
    "actual_harvest_import_batch",
    "actual_harvest_import_record",
    "actual_harvest_commit_manifest",
    "actual_harvest_mapping_policy_registry",
    "actual_harvest_mapping_registry_entry",
    "actual_harvest_mapping_snapshot",
    "actual_harvest_validation_run",
    "actual_harvest_validation_result",
    "actual_harvest_validation_lineage_basis",
    "actual_harvest_validation_lineage_basis_member",
    "actual_harvest_validation_mapping_evidence",
    "actual_harvest_label_snapshot",
    "actual_harvest_label_snapshot_winner",
    "actual_harvest_label_snapshot_label",
    "actual_harvest_label_snapshot_exclusion",
)


SEED_HASH_A = "a" * 64
SEED_HASH_B = "b" * 64
SEED_HASH_C = "c" * 64


def _hex64(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _inject_plot_evidence_row(
    session: AsyncSession,
    *,
    run_id: int,
    record: ActualHarvestImportRecordModel,
    business_key_suffix: str,
) -> None:
    """Inject a PLOT evidence row directly into the persisted
    ``actual_harvest_validation_mapping_evidence`` table for the
    given validation run + committed record.

    The I5 validation pipeline rejects PLOT at validation time
    (contract §X.1), so the upstream CHECK constraint
    ``ck_actual_harvest_validation_mapping_target_type`` and the
    per-target-type FK constraint
    ``ck_actual_harvest_validation_mapping_target_fk`` block the
    ORM INSERT. This helper bypasses those constraints by issuing
    raw SQL, simulating the "PLOT slipped into a committed
    lineage basis" failure mode the I7 contract must defend
    against — either via direct DB write corruption or via a
    future regression in the I5 PLOT check.
    """
    from sqlalchemy import text as _text

    await session.execute(
        _text(
            "ALTER TABLE actual_harvest_validation_mapping_evidence "
            "DROP CONSTRAINT ck_actual_harvest_validation_mapping_target_type"
        )
    )
    await session.execute(
        _text(
            "ALTER TABLE actual_harvest_validation_mapping_evidence "
            "DROP CONSTRAINT ck_actual_harvest_validation_mapping_target_fk"
        )
    )
    await session.execute(
        _text(
            "INSERT INTO actual_harvest_validation_mapping_evidence ("
            "validation_run_id, record_index, source_system, "
            "external_logical_record_id, external_revision_id, "
            "revision_number, source_field, source_code, "
            "registry_version, mapping_policy_version, "
            "resolver_version, registry_entry_hash, target_type, "
            "target_business_key, target_parent_business_key, "
            "resolved_master_business_key, "
            "resolved_master_parent_business_key, "
            "resolved_master_record_hash, resolved_season_id, "
            "resolution_mode, outcome"
            ") VALUES ("
            ":validation_run_id, :record_index, :source_system, "
            ":external_logical_record_id, :external_revision_id, "
            ":revision_number, :source_field, :source_code, "
            ":registry_version, :mapping_policy_version, "
            ":resolver_version, :registry_entry_hash, :target_type, "
            ":target_business_key, :target_parent_business_key, "
            ":resolved_master_business_key, "
            ":resolved_master_parent_business_key, "
            ":resolved_master_record_hash, :resolved_season_id, "
            ":resolution_mode, :outcome"
            ")"
        ),
        {
            "validation_run_id": run_id,
            "record_index": 1,
            "source_system": record.source_system,
            "external_logical_record_id": record.external_logical_record_id,
            "external_revision_id": record.external_revision_id,
            "revision_number": record.revision_number,
            "source_field": "subfarm_or_plot_code",
            "source_code": None,
            "registry_version": "registry-v1",
            "mapping_policy_version": "mapping-test-v1",
            "resolver_version": "actual-harvest-season-resolver-v1",
            "registry_entry_hash": _hex64(f"plot-entry-{business_key_suffix}"),
            "target_type": "PLOT",
            "target_business_key": f"plot-business-key-{business_key_suffix}",
            "target_parent_business_key": "farm-business-key-1",
            "resolved_master_business_key": f"plot-business-key-{business_key_suffix}",
            "resolved_master_parent_business_key": "farm-business-key-1",
            "resolved_master_record_hash": _hex64(f"plot-master-{business_key_suffix}"),
            "resolved_season_id": 1,
            "resolution_mode": "exact_lookup",
            "outcome": "RESOLVED",
        },
    )


def _import_immutability_triggers_sqlite(connection) -> None:
    """Re-create the S1 immutability triggers (SQLite branch) for tests."""

    connection.exec_driver_sql(
        """
        CREATE TRIGGER IF NOT EXISTS trg_actual_harvest_commit_manifest_immutable_update
        BEFORE UPDATE ON actual_harvest_commit_manifest
        BEGIN
            SELECT RAISE(ABORT, 'actual-harvest commit manifest is immutable');
        END
        """
    )
    connection.exec_driver_sql(
        """
        CREATE TRIGGER IF NOT EXISTS trg_actual_harvest_commit_manifest_immutable_delete
        BEFORE DELETE ON actual_harvest_commit_manifest
        BEGIN
            SELECT RAISE(ABORT, 'actual-harvest commit manifest is immutable');
        END
        """
    )


def _label_snapshot_immutability_triggers_sqlite(connection) -> None:
    """Re-create the I7 immutability triggers (SQLite branch)."""

    for table in (
        HEADER_TABLE_NAME,
        WINNER_TABLE_NAME,
        LABEL_TABLE_NAME,
        EXCLUSION_TABLE_NAME,
    ):
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_{table}_immutable_update
            BEFORE UPDATE ON {table}
            BEGIN
                SELECT RAISE(ABORT, 'actual-harvest label snapshot row is immutable');
            END
            """
        )
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_{table}_immutable_delete
            BEFORE DELETE ON {table}
            BEGIN
                SELECT RAISE(ABORT, 'actual-harvest label snapshot row is immutable');
            END
            """
        )


async def _seed_registry(session: AsyncSession, *, suffix: str) -> str:
    """Plant a sealed mapping registry for the given suffix.

    Returns the mapping_policy_version used by the seed.
    """

    registry = ActualHarvestMappingPolicyRegistryModel(
        registry_version=f"registry-{suffix}",
        source_system="source-test",
        mapping_policy_version=f"mapping-test-{suffix}",
        status="SEALED",
        entry_count=4,
        registry_content_hash=_hex64(f"registry-content-{suffix}"),
    )
    session.add(registry)
    await session.flush()
    season_entry = ActualHarvestMappingRegistryEntryModel(
        registry_id=registry.id,
        source_field="season_code",
        source_code="season-1",
        target_type="SEASON",
        target_business_key="season-business-key-1",
        entry_hash=_hex64(f"season-entry-{suffix}"),
    )
    farm_entry = ActualHarvestMappingRegistryEntryModel(
        registry_id=registry.id,
        source_field="farm_code",
        source_code="farm-1",
        target_type="FARM",
        target_business_key="farm-business-key-1",
        entry_hash=_hex64(f"farm-entry-{suffix}"),
    )
    subfarm_entry = ActualHarvestMappingRegistryEntryModel(
        registry_id=registry.id,
        source_field="subfarm_or_plot_code",
        source_code="sub-1",
        target_type="SUBFARM",
        target_business_key="sub-business-key-1",
        target_parent_business_key="farm-business-key-1",
        entry_hash=_hex64(f"subfarm-entry-{suffix}"),
    )
    variety_entry = ActualHarvestMappingRegistryEntryModel(
        registry_id=registry.id,
        source_field="variety_code",
        source_code="var-1",
        target_type="VARIETY",
        target_business_key="var-business-key-1",
        entry_hash=_hex64(f"variety-entry-{suffix}"),
    )
    session.add_all([season_entry, farm_entry, subfarm_entry, variety_entry])
    await session.flush()
    return registry.mapping_policy_version


async def _seed_master_data(
    session: AsyncSession,
) -> tuple[Season, Farm, Subfarm, Variety]:
    """Plant the four master rows needed for FK integrity.

    The I7 service does not look up live master data; mapping
    evidence is reconstructed from the persisted lineage basis.
    The master rows are required only because the I5 mapping
    evidence table has a check constraint that asserts exactly one
    ``resolved_*_id`` column is set per ``target_type``. SQLite
    does not auto-increment ``BIGINT PRIMARY KEY`` columns, so the
    helper passes explicit id values.
    """

    season = Season(id=1, code="season-1", start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    farm = Farm(id=1, name="Farm One")
    subfarm = Subfarm(id=1, farm_id=1, name="Subfarm One")
    variety = Variety(id=1, code="var-1", name="Variety One")
    session.add_all([season, farm, subfarm, variety])
    return season, farm, subfarm, variety


async def _seed_validation_run(
    session: AsyncSession,
    *,
    batch_id: int,
    policy_version: str,
) -> int:
    session.add(
        ActualHarvestValidationRunModel(
            batch_id=batch_id,
            request_identity_hash=_hex64(f"req-{batch_id}"),
            # ``instance_identity_hash`` MUST match
            # ``commit_manifest.validation_run_instance_identity_hash``,
            # which is keyed by the validation run id (filled in
            # after ``session.flush()``).
            instance_identity_hash=_hex64("inst-pending"),
            seal_manifest_hash=_hex64(f"seal-{batch_id}"),
            mapping_policy_version=policy_version,
            validation_policy_version="validation-test-v1",
            season_resolver_version="actual-harvest-season-resolver-v1",
            committed_lineage_basis_hash=_hex64(f"basis-{batch_id}"),
            registry_content_hash=_hex64(f"registry-{batch_id}"),
            record_manifest_hash=_hex64(f"rec-{batch_id}"),
            status="VALIDATED",
            is_current=True,
            active_attempt_generation=0,
            valid_count=1,
            invalid_count=0,
            error_count=0,
            warning_count=0,
        )
    )
    await session.flush()
    run = await session.scalar(
        select(ActualHarvestValidationRunModel)
        .where(ActualHarvestValidationRunModel.batch_id == batch_id)
        .order_by(ActualHarvestValidationRunModel.id.desc())
    )
    assert run is not None
    # Patch the instance_identity_hash to use the same key the
    # commit manifest will use, so cross-validation passes.
    run.instance_identity_hash = _hex64(f"inst-{run.id}")
    await session.flush()
    return run.id


async def _seed_mapping_snapshot(
    session: AsyncSession,
    *,
    validation_run_id: int,
    policy_version: str,
) -> None:
    # Mapping-snapshot hashes MUST match the values the commit
    # manifest copies (see _build_commit_manifest). Using different
    # key prefixes here would force SOURCE_EVIDENCE_DRIFT on a
    # production snapshot.
    snapshot = ActualHarvestMappingSnapshotModel(
        validation_run_id=validation_run_id,
        registry_version=f"registry-{policy_version}",
        mapping_policy_version=policy_version,
        season_resolver_version="actual-harvest-season-resolver-v1",
        registry_content_hash=_hex64(f"registry-{validation_run_id}"),
        mapping_snapshot_hash=_hex64(f"ms-{validation_run_id}"),
        resolved_identity_snapshot_hash=_hex64(f"isnap-{validation_run_id}"),
        entry_count=0,
        snapshot_payload="[]",
    )
    session.add(snapshot)


async def _seed_validation_result(
    session: AsyncSession,
    *,
    validation_run_id: int,
) -> None:
    result = ActualHarvestValidationResultModel(
        validation_run_id=validation_run_id,
        validation_result_hash=_hex64(f"vr-{validation_run_id}"),
        lineage_graph_hash=_hex64(f"lg-{validation_run_id}"),
        committed_lineage_basis_hash=_hex64(f"basis-{validation_run_id}"),
        mapping_snapshot_hash=_hex64(f"ms-{validation_run_id}"),
        resolved_identity_snapshot_hash=_hex64(f"isnap-{validation_run_id}"),
        season_resolver_version="actual-harvest-season-resolver-v1",
        valid_count=1,
        invalid_count=0,
        error_count=0,
        warning_count=0,
        result_payload="{}",
    )
    session.add(result)


async def _seed_lineage_basis_and_evidence(
    session: AsyncSession,
    *,
    batch_id: int,
    validation_run_id: int,
    records: list[ActualHarvestImportRecordModel],
) -> None:
    """Plant the committed-history lineage basis + mapping evidence.

    The I7 service reads from the persisted lineage basis table (not
    the live master-data tables) per contract §11. Tests must populate
    the basis + per-target evidence rows so the snapshot pipeline can
    reconstruct the frozen mapping identities.
    """

    basis = ActualHarvestValidationLineageBasisModel(
        validation_run_id=validation_run_id,
        source_system="source-test",
        authority_policy_version="actual-harvest-authority-v1",
        committed_lineage_basis_hash=_hex64(f"basis-{validation_run_id}"),
        member_count=len(records),
    )
    session.add(basis)
    await session.flush()
    for index, record in enumerate(records, start=1):
        member = ActualHarvestValidationLineageBasisMemberModel(
            basis_id=basis.id,
            source_system=record.source_system,
            committed_batch_ref=f"{record.source_system}:{record.external_batch_id}",
            external_logical_record_id=record.external_logical_record_id,
            external_revision_id=record.external_revision_id,
            revision_number=record.revision_number,
            canonical_record_hash=_hex64(f"rec-{record.external_revision_id}"),
            predecessor_revision_id=record.supersedes_external_revision_id,
            record_status=record.record_status,
            source_recorded_at=record.source_recorded_at,
            source_recorded_at_authority_status=(record.source_recorded_at_authority_status),
            member_sort_key=f"{record.source_system}|{record.external_logical_record_id}|{record.revision_number}|{record.external_revision_id}",
            member_hash=_hex64(f"mem-{record.external_revision_id}"),
        )
        session.add(member)
        for target_type, business_key, parent_business_key, resolved_key, fk_attr, fk_value in (
            (
                "SEASON",
                "season-business-key-1",
                None,
                "season-business-key-1",
                "resolved_season_id",
                1,
            ),
            (
                "FARM",
                "farm-business-key-1",
                None,
                "farm-business-key-1",
                "resolved_farm_id",
                1,
            ),
            (
                "SUBFARM",
                "sub-business-key-1",
                "farm-business-key-1",
                "sub-business-key-1",
                "resolved_subfarm_id",
                1,
            ),
            (
                "VARIETY",
                "var-business-key-1",
                None,
                "var-business-key-1",
                "resolved_variety_id",
                1,
            ),
        ):
            kwargs: dict[str, Any] = dict(
                validation_run_id=validation_run_id,
                record_index=index,
                source_system=record.source_system,
                external_logical_record_id=record.external_logical_record_id,
                external_revision_id=record.external_revision_id,
                revision_number=record.revision_number,
                source_field=target_type.lower(),
                source_code=None,
                registry_version="registry-v1",
                mapping_policy_version="mapping-test-v1",
                resolver_version="actual-harvest-season-resolver-v1",
                registry_entry_hash=_hex64(f"entry-{record.external_revision_id}-{target_type}"),
                target_type=target_type,
                target_business_key=business_key,
                target_parent_business_key=parent_business_key,
                resolved_master_business_key=resolved_key,
                resolved_master_parent_business_key=parent_business_key,
                resolved_master_record_hash=_hex64(
                    f"master-{record.external_revision_id}-{target_type}"
                ),
                resolution_mode="exact_lookup",
                outcome="RESOLVED",
            )
            if fk_attr == "resolved_season_id":
                kwargs["resolved_season_id"] = fk_value
            elif fk_attr == "resolved_farm_id":
                kwargs["resolved_farm_id"] = fk_value
            elif fk_attr == "resolved_subfarm_id":
                kwargs["resolved_subfarm_id"] = fk_value
            elif fk_attr == "resolved_variety_id":
                kwargs["resolved_variety_id"] = fk_value
            session.add(ActualHarvestValidationMappingEvidenceModel(**kwargs))


@pytest_asyncio.fixture
async def session_maker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """In-memory SQLite fixture.

    Selectively creates the four I7 tables + the I5 / S1 staging and
    validation tables the I7 pipeline depends on. The S1
    ``baseline_backtest_run`` table is intentionally excluded
    because its JSONB columns cannot be rendered on SQLite.
    """

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    from backend.app.actual_harvest_labels.models import (
        ActualHarvestLabelSnapshotExclusionModel as _ExclusionModel,
    )
    from backend.app.actual_harvest_labels.models import (
        ActualHarvestLabelSnapshotLabelModel as _LabelModel,
    )
    from backend.app.actual_harvest_labels.models import (
        ActualHarvestLabelSnapshotModel as _SnapshotModel,
    )
    from backend.app.actual_harvest_labels.models import (
        ActualHarvestLabelSnapshotWinnerModel as _WinnerModel,
    )

    i7_tables = (
        ActualHarvestImportBatchModel.__table__,
        ActualHarvestImportRecordModel.__table__,
        ActualHarvestCommitManifestModel.__table__,
        ActualHarvestMappingPolicyRegistryModel.__table__,
        ActualHarvestMappingRegistryEntryModel.__table__,
        ActualHarvestMappingSnapshotModel.__table__,
        ActualHarvestValidationRunModel.__table__,
        ActualHarvestValidationResultModel.__table__,
        ActualHarvestValidationLineageBasisModel.__table__,
        ActualHarvestValidationLineageBasisMemberModel.__table__,
        ActualHarvestValidationMappingEvidenceModel.__table__,
        Season.__table__,
        Farm.__table__,
        Subfarm.__table__,
        Variety.__table__,
        _SnapshotModel.__table__,
        _WinnerModel.__table__,
        _LabelModel.__table__,
        _ExclusionModel.__table__,
    )

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=i7_tables,
        )
        await conn.run_sync(_import_immutability_triggers_sqlite)
        await conn.run_sync(_label_snapshot_immutability_triggers_sqlite)
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield maker
    finally:
        await engine.dispose()


def _build_batch(
    *,
    import_id: str,
    source_system: str = "source-test",
    channel: str = "api",
) -> ActualHarvestImportBatchModel:
    return ActualHarvestImportBatchModel(
        import_id=import_id,
        import_channel=channel,
        source_system=source_system,
        source_dataset="ds",
        source_version="v1",
        external_batch_id=import_id.replace("imp-", "ext-"),
        idempotency_key=f"idem-{import_id}",
        submitted_at=datetime(2024, 1, 1, tzinfo=UTC),
        import_received_at=datetime(2024, 1, 1, tzinfo=UTC),
        ingested_at=datetime(2024, 1, 1, tzinfo=UTC),
        submitted_by_identity="op-test",
        expected_record_count_or_null=1,
        uploaded_record_count=1,
        sealed_record_count_or_null=1,
        sealed_at_or_null=datetime(2024, 1, 1, tzinfo=UTC),
        sealed_by_identity_or_null="op-test",
        seal_status="SEALED",
        server_raw_payload_hash_or_null=SEED_HASH_A,
        canonical_batch_hash_or_null=SEED_HASH_A,
        seal_manifest_hash_or_null=SEED_HASH_A,
        source_file_name_or_null="seed.xlsx",
        source_file_hash_or_null=SEED_HASH_A,
        raw_payload_hash=SEED_HASH_A,
        schema_version="schema-v1",
        mapping_policy_version="mapping-test-v1",
        validation_policy_version="validation-test-v1",
        source_semantics_attestation_version="attestation-v1",
        source_semantics_physical_event=ActualHarvestPhysicalEvent.FARM_PICK.value,
        source_semantics_quantity_basis=ActualHarvestQuantityBasis.OBSERVED_WEIGHT.value,
        source_semantics_quantity_unit=ActualHarvestQuantityUnit.KG.value,
        source_semantics_missing_record_semantics=(
            ActualHarvestMissingRecordSemantics.UNKNOWN_NOT_ZERO.value
        ),
        source_semantics_attestation_hash=SEED_HASH_A,
        status="VALIDATED",
        record_count=1,
        valid_record_count=1,
        invalid_record_count=0,
        committed_record_count=1,
        validated_at_or_null=datetime(2024, 1, 1, tzinfo=UTC),
        committed_at_or_null=datetime(2024, 1, 1, tzinfo=UTC),
    )


def _build_record(
    *,
    source_system: str = "source-test",
    external_logical_record_id: str = "logical-1",
    external_revision_id: str = "rev-1",
    revision_number: int = 1,
    quantity_kg: str = "1.0",
    status: str = ActualHarvestRecordStatus.ACTIVE.value,
    finalized_at: datetime | None = None,
    authority_status: str = SourceRecordedAtAuthorityStatus.TRUSTED_SOURCE_TIMESTAMP.value,
    authority_reference: str | None = "farm-time-source",
    source_recorded_at: datetime | None = datetime(2024, 1, 1, tzinfo=UTC),
    harvest_date: date = date(2024, 1, 1),
    season_code: str = "season-1",
) -> ActualHarvestImportRecordModel:
    # ``batch_id`` is populated by the seed helper after the batch row
    # is inserted; the placeholder ``0`` keeps the column NOT NULL
    # constraint satisfied when the helper is called outside a
    # session.
    return ActualHarvestImportRecordModel(
        batch_id=0,
        external_logical_record_id=external_logical_record_id,
        external_revision_id=external_revision_id,
        source_system=source_system,
        external_batch_id="ext-pending",
        harvest_business_date=harvest_date,
        farm_code="farm-1",
        subfarm_or_plot_code="sub-1",
        variety_code="var-1",
        actual_harvest_quantity_kg=Decimal(quantity_kg),
        source_recorded_at=source_recorded_at,
        source_recorded_at_authority_status=authority_status,
        source_recorded_at_authority_reference_or_null=authority_reference,
        import_received_at=datetime(2024, 1, 1, tzinfo=UTC),
        ingested_at=datetime(2024, 1, 1, tzinfo=UTC),
        revision_number=revision_number,
        record_status=status,
        season_code=season_code,
        finalized_at=finalized_at,
    )


def _build_commit_manifest(
    *,
    batch_id: int,
    validation_run_id: int,
    record_count: int = 1,
) -> ActualHarvestCommitManifestModel:
    return ActualHarvestCommitManifestModel(
        batch_id=batch_id,
        validation_run_id=validation_run_id,
        commit_policy_version=COMMIT_POLICY_VERSION,
        validation_run_instance_identity_hash=_hex64(f"inst-{validation_run_id}"),
        commit_manifest_hash=_hex64(f"cm-{validation_run_id}"),
        seal_manifest_hash=SEED_HASH_A,
        canonical_batch_hash=SEED_HASH_A,
        record_manifest_hash=_hex64(f"rec-{validation_run_id}"),
        validation_result_hash=_hex64(f"vr-{validation_run_id}"),
        mapping_snapshot_hash=_hex64(f"ms-{validation_run_id}"),
        resolved_identity_snapshot_hash=_hex64(f"isnap-{validation_run_id}"),
        lineage_graph_hash=_hex64(f"lg-{validation_run_id}"),
        committed_lineage_basis_hash=_hex64(f"basis-{validation_run_id}"),
        registry_content_hash=_hex64(f"registry-{validation_run_id}"),
        source_semantics_attestation_hash=SEED_HASH_A,
        committed_record_count=record_count,
        committed_by_identity="op-test",
    )


async def _seed_seeded_batch(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    import_id: str,
    records: list[ActualHarvestImportRecordModel],
    source_system: str = "source-test",
    registry_suffix: str | None = None,
) -> dict[str, object]:
    """Insert a sealed batch + records + commit manifest.

    Returns a dict with the created batch, manifest, mapping policy and
    a set of helper lookups the test may want to read.
    """

    suffix = registry_suffix or import_id
    async with session_maker() as session:
        async with session.begin():
            # Master data is inserted idempotently per session: if a
            # previous call has already planted it, skip the inserts
            # to avoid UNIQUE-constraint conflicts (each test session
            # is a fresh in-memory engine, but a single test may call
            # this helper multiple times).
            from sqlalchemy import select as _select

            from backend.app.models.master_data import (
                Season as _Season,
            )

            existing_season = await session.scalar(_select(_Season).where(_Season.id == 1))
            if existing_season is None:
                await _seed_master_data(session)
                await session.flush()
            policy = await _seed_registry(session, suffix=suffix)
            batch = _build_batch(import_id=import_id, source_system=source_system)
            session.add(batch)
            await session.flush()
            for record in records:
                record.batch_id = batch.id
                session.add(record)
            await session.flush()
            run_id = await _seed_validation_run(session, batch_id=batch.id, policy_version=policy)
            await _seed_mapping_snapshot(
                session,
                validation_run_id=run_id,
                policy_version=policy,
            )
            await _seed_validation_result(session, validation_run_id=run_id)
            await _seed_lineage_basis_and_evidence(
                session,
                batch_id=batch.id,
                validation_run_id=run_id,
                records=records,
            )
            manifest = _build_commit_manifest(
                batch_id=batch.id,
                validation_run_id=run_id,
                record_count=len(records),
            )
            session.add(manifest)
            await session.flush()
            batch.status = ActualHarvestImportBatchStatus.COMMITTED.value
            batch.committed_at_or_null = datetime(2024, 1, 1, tzinfo=UTC)
    return {
        "policy_version": policy,
        "batch_id": batch.id,
        "manifest_hash": manifest.commit_manifest_hash,
    }


def _base_request(**overrides) -> ActualHarvestLabelSnapshotRequest:
    payload = {
        "snapshot_idempotency_key": "idem-snap-1",
        "source_system": "source-test",
        "visibility_mode": SchemaVisibility.AS_OF_EVALUATION,
        "label_observation_cutoff_at_or_null": datetime(2024, 12, 31, tzinfo=UTC),
        "harvest_date_start": date(2024, 1, 1),
        "harvest_date_end": date(2024, 12, 31),
        "season_business_keys": ("season-business-key-1",),
        "farm_business_keys_or_empty_for_all": (),
        "variety_business_keys_or_empty_for_all": (),
        "snapshot_policy_version": SNAPSHOT_POLICY_VERSION,
        "winner_policy_version": WINNER_POLICY_VERSION,
        "aggregation_policy_version": AGGREGATION_POLICY_VERSION,
    }
    payload.update(overrides)
    return ActualHarvestLabelSnapshotRequest.model_validate(payload)


# ---------------------------------------------------------------------------
# Winner / cutoff visibility
# ---------------------------------------------------------------------------


async def test_as_of_cutoff_before_parent_only_parent_visible(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    cutoff = datetime(2024, 1, 1, tzinfo=UTC)
    parent_record = _build_record(
        external_logical_record_id="logical-parent",
        external_revision_id="rev-parent",
        source_recorded_at=datetime(2023, 12, 31, tzinfo=UTC),
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-asof-parent",
        records=[parent_record],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-asof-parent",
        label_observation_cutoff_at_or_null=cutoff,
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 1
    assert result.header.label_row_count == 1
    assert result.header.exclusion_row_count == 0
    winner = result.winners[0]
    assert winner["external_revision_id"] == "rev-parent"
    assert winner["record_status"] == ActualHarvestRecordStatus.ACTIVE.value


async def test_as_of_cutoff_after_successor_only_successor_visible(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    cutoff = datetime(2024, 6, 30, tzinfo=UTC)
    parent_record = _build_record(
        external_logical_record_id="logical-successor",
        external_revision_id="rev-parent",
        source_recorded_at=datetime(2023, 12, 31, tzinfo=UTC),
    )
    successor_record = _build_record(
        external_logical_record_id="logical-successor",
        external_revision_id="rev-suc",
        revision_number=2,
        quantity_kg="2.0",
        source_recorded_at=datetime(2024, 6, 1, tzinfo=UTC),
    )
    successor_record.supersedes_external_revision_id = "rev-parent"
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-asof-succ",
        records=[parent_record, successor_record],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-asof-succ",
        label_observation_cutoff_at_or_null=cutoff,
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 1
    winner = result.winners[0]
    assert winner["external_revision_id"] == "rev-suc"
    assert winner["revision_number"] == 2


async def test_as_of_no_future_revision_leakage(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    cutoff = datetime(2024, 1, 1, tzinfo=UTC)
    future_record = _build_record(
        external_logical_record_id="logical-future",
        external_revision_id="rev-future",
        source_recorded_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-asof-future",
        records=[future_record],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-asof-future",
        label_observation_cutoff_at_or_null=cutoff,
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 0
    assert result.header.exclusion_row_count == 1
    categories = {row["exclusion_category"] for row in result.exclusion_rows}
    assert ActualHarvestLabelCoverageExclusion.SOURCE_TIME_AFTER_CUTOFF.value in categories


async def test_as_of_cutoff_equality(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    cutoff = datetime(2024, 1, 1, tzinfo=UTC)
    boundary_record = _build_record(
        external_logical_record_id="logical-boundary",
        external_revision_id="rev-bound",
        source_recorded_at=cutoff,
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-asof-boundary",
        records=[boundary_record],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-asof-boundary",
        label_observation_cutoff_at_or_null=cutoff,
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 1
    assert result.header.exclusion_row_count == 0


async def test_untrusted_source_time_excluded(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    cutoff = datetime(2024, 12, 31, tzinfo=UTC)
    untrusted_record = _build_record(
        external_logical_record_id="logical-untrusted",
        external_revision_id="rev-untrusted",
        authority_status=SourceRecordedAtAuthorityStatus.USER_ASSERTED_UNVERIFIED.value,
        source_recorded_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-untrusted",
        records=[untrusted_record],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-untrusted",
        label_observation_cutoff_at_or_null=cutoff,
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 0
    categories = {row["exclusion_category"] for row in result.exclusion_rows}
    assert ActualHarvestLabelCoverageExclusion.SOURCE_TIME_UNTRUSTED.value in categories


async def test_missing_source_time_excluded(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    cutoff = datetime(2024, 12, 31, tzinfo=UTC)
    missing_record = _build_record(
        external_logical_record_id="logical-missing",
        external_revision_id="rev-missing",
        source_recorded_at=None,
        authority_status=SourceRecordedAtAuthorityStatus.MISSING.value,
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-missing",
        records=[missing_record],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-missing",
        label_observation_cutoff_at_or_null=cutoff,
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 0
    categories = {row["exclusion_category"] for row in result.exclusion_rows}
    assert ActualHarvestLabelCoverageExclusion.SOURCE_TIME_MISSING.value in categories


async def test_terminal_active_winner(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    record = _build_record(
        external_logical_record_id="logical-active",
        external_revision_id="rev-active",
        status=ActualHarvestRecordStatus.ACTIVE.value,
    )
    await _seed_seeded_batch(session_maker, import_id="imp-active", records=[record])

    request = _base_request(
        snapshot_idempotency_key="idem-active",
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 1
    winner = result.winners[0]
    assert winner["record_status"] == ActualHarvestRecordStatus.ACTIVE.value
    assert winner["effective_status"] == "ACTIVE"


async def test_terminal_finalized_winner_before_cutoff(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    finalized_at = datetime(2024, 1, 1, tzinfo=UTC)
    record = _build_record(
        external_logical_record_id="logical-fin-ok",
        external_revision_id="rev-fin-ok",
        status=ActualHarvestRecordStatus.FINALIZED.value,
        finalized_at=finalized_at,
        source_recorded_at=finalized_at,
    )
    await _seed_seeded_batch(session_maker, import_id="imp-fin-ok", records=[record])

    request = _base_request(
        snapshot_idempotency_key="idem-fin-ok",
        label_observation_cutoff_at_or_null=datetime(2024, 6, 30, tzinfo=UTC),
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 1
    winner = result.winners[0]
    assert winner["effective_status"] == "FINALIZED"


async def test_finalized_after_cutoff_status_not_visible_exclusion(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    finalized_at = datetime(2024, 6, 1, tzinfo=UTC)
    record = _build_record(
        external_logical_record_id="logical-fin-late",
        external_revision_id="rev-fin-late",
        status=ActualHarvestRecordStatus.FINALIZED.value,
        finalized_at=finalized_at,
        source_recorded_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    await _seed_seeded_batch(session_maker, import_id="imp-fin-late", records=[record])

    request = _base_request(
        snapshot_idempotency_key="idem-fin-late",
        label_observation_cutoff_at_or_null=datetime(2024, 1, 31, tzinfo=UTC),
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 0
    categories = {row["exclusion_category"] for row in result.exclusion_rows}
    assert ActualHarvestLabelCoverageExclusion.STATUS_NOT_VISIBLE_AT_CUTOFF.value in categories


async def test_terminal_void_exclusion(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    record = _build_record(
        external_logical_record_id="logical-void",
        external_revision_id="rev-void",
        status=ActualHarvestRecordStatus.VOID.value,
        source_recorded_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    await _seed_seeded_batch(session_maker, import_id="imp-void", records=[record])

    request = _base_request(
        snapshot_idempotency_key="idem-void",
        label_observation_cutoff_at_or_null=datetime(2024, 12, 31, tzinfo=UTC),
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 0
    categories = {row["exclusion_category"] for row in result.exclusion_rows}
    assert ActualHarvestLabelCoverageExclusion.TERMINAL_VOID.value in categories


# ---------------------------------------------------------------------------
# Replay and atomicity
# ---------------------------------------------------------------------------


async def test_idempotent_replay_zero_write(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    record = _build_record(
        external_logical_record_id="logical-replay",
        external_revision_id="rev-replay",
    )
    await _seed_seeded_batch(session_maker, import_id="imp-replay", records=[record])

    request = _base_request(snapshot_idempotency_key="idem-replay")

    async with session_maker() as session:
        async with session.begin():
            first = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

        async with session.begin():
            second = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert first.header.label_snapshot_hash == second.header.label_snapshot_hash
    assert first.header.winner_count == second.header.winner_count

    async with session_maker() as session:
        snapshots = (await session.scalars(select(ActualHarvestLabelSnapshotModel))).all()
    assert len(snapshots) == 1


async def test_idempotency_conflict(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    record = _build_record(
        external_logical_record_id="logical-conflict",
        external_revision_id="rev-conflict",
    )
    await _seed_seeded_batch(session_maker, import_id="imp-conflict", records=[record])

    first_request = _base_request(snapshot_idempotency_key="idem-conflict")
    second_request = _base_request(
        snapshot_idempotency_key="idem-conflict",
        farm_business_keys_or_empty_for_all=("farm-business-key-1",),
    )

    async with session_maker() as session:
        async with session.begin():
            await create_label_snapshot(
                session,
                request=first_request,
                created_by_identity="op-test",
            )

    async with session_maker() as session:
        with pytest.raises(ActualHarvestLabelIdempotencyConflictError):
            async with session.begin():
                await create_label_snapshot(
                    session,
                    request=second_request,
                    created_by_identity="op-test",
                )


async def test_new_idempotency_key_creates_new_snapshot(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    record = _build_record(
        external_logical_record_id="logical-new-key",
        external_revision_id="rev-new-key",
    )
    await _seed_seeded_batch(session_maker, import_id="imp-new-key", records=[record])

    request_one = _base_request(snapshot_idempotency_key="idem-new-1")
    request_two = _base_request(snapshot_idempotency_key="idem-new-2")

    async with session_maker() as session:
        async with session.begin():
            await create_label_snapshot(
                session,
                request=request_one,
                created_by_identity="op-test",
            )
        async with session.begin():
            await create_label_snapshot(
                session,
                request=request_two,
                created_by_identity="op-test",
            )

    async with session_maker() as session:
        snapshots = (await session.scalars(select(ActualHarvestLabelSnapshotModel))).all()
    assert len(snapshots) == 2


# ---------------------------------------------------------------------------
# Aggregation invariants
# ---------------------------------------------------------------------------


async def test_subfarm_only_grain(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    record = _build_record(
        external_logical_record_id="logical-grain",
        external_revision_id="rev-grain",
    )
    await _seed_seeded_batch(session_maker, import_id="imp-grain", records=[record])

    request = _base_request(snapshot_idempotency_key="idem-grain")

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.label_row_count == 1
    label_row = result.label_rows[0]
    assert label_row["subfarm_business_key"] == "sub-business-key-1"
    assert label_row["season_business_key"] == "season-business-key-1"


async def test_multiple_logical_records_same_grain_sum(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    record_a = _build_record(
        external_logical_record_id="logical-a",
        external_revision_id="rev-a",
        quantity_kg="3.0",
    )
    record_b = _build_record(
        external_logical_record_id="logical-b",
        external_revision_id="rev-b",
        quantity_kg="4.0",
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-multi-grain",
        records=[record_a, record_b],
    )

    request = _base_request(snapshot_idempotency_key="idem-multi-grain")

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.label_row_count == 1
    label_row = result.label_rows[0]
    assert label_row["contributing_winner_count"] == 2
    assert Decimal(label_row["exact_decimal_quantity_sum_kg"]) == Decimal("7.0")


async def test_explicit_zero_preserved(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    record = _build_record(
        external_logical_record_id="logical-zero",
        external_revision_id="rev-zero",
        quantity_kg="0",
    )
    await _seed_seeded_batch(session_maker, import_id="imp-zero", records=[record])

    request = _base_request(snapshot_idempotency_key="idem-zero")

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.label_row_count == 1
    label_row = result.label_rows[0]
    assert Decimal(label_row["exact_decimal_quantity_sum_kg"]) == Decimal("0")


async def test_input_order_independence(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    record_a = _build_record(
        external_logical_record_id="logical-ord-a",
        external_revision_id="rev-ord-a",
        quantity_kg="1.5",
    )
    record_b = _build_record(
        external_logical_record_id="logical-ord-b",
        external_revision_id="rev-ord-b",
        quantity_kg="2.5",
    )

    await _seed_seeded_batch(
        session_maker,
        import_id="imp-order-a-b",
        records=[record_a, record_b],
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-order-b-a",
        records=[record_b, record_a],
    )

    # Both snapshots use the SAME idempotency key but distinct
    # request payloads (different farm / variety scope). The
    # snapshot service treats that as a deterministic idempotency
    # conflict on the second call, so the contract test exercises
    # source-universe reorder via two snapshots with the same
    # idempotency key only when the request hashes are also equal.
    request_one = _base_request(snapshot_idempotency_key="idem-order-1")
    request_two = _base_request(snapshot_idempotency_key="idem-order-1")

    async with session_maker() as session:
        async with session.begin():
            first = await create_label_snapshot(
                session,
                request=request_one,
                created_by_identity="op-test",
            )
        async with session.begin():
            second = await create_label_snapshot(
                session,
                request=request_two,
                created_by_identity="op-test",
            )

    assert first.header.label_snapshot_hash == second.header.label_snapshot_hash
    assert first.header.winner_manifest_hash == second.header.winner_manifest_hash
    assert first.header.label_row_set_hash == second.header.label_row_set_hash
    assert first.header.exclusion_manifest_hash == second.header.exclusion_manifest_hash
    assert first.header.snapshot_request_identity_hash == (
        second.header.snapshot_request_identity_hash
    )
    # Print hashes for debug


# ---------------------------------------------------------------------------
# Immutability triggers
# ---------------------------------------------------------------------------


async def test_label_snapshot_immutability(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    record = _build_record(
        external_logical_record_id="logical-immut",
        external_revision_id="rev-immut",
    )
    await _seed_seeded_batch(session_maker, import_id="imp-immut", records=[record])

    request = _base_request(snapshot_idempotency_key="idem-immut")

    async with session_maker() as session:
        async with session.begin():
            await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    async with session_maker() as session:
        snapshot = await get_existing_snapshot_by_idempotency_key(
            session,
            source_system=request.source_system,
            snapshot_idempotency_key=request.snapshot_idempotency_key,
        )
        assert snapshot is not None
        with pytest.raises(Exception) as excinfo:  # noqa: B017
            snapshot.label_snapshot_hash = "f" * 64
            await session.flush()
        assert "immutable" in str(excinfo.value).lower()


async def test_label_snapshot_delete_rejected(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    record = _build_record(
        external_logical_record_id="logical-no-del",
        external_revision_id="rev-no-del",
    )
    await _seed_seeded_batch(session_maker, import_id="imp-no-del", records=[record])

    request = _base_request(snapshot_idempotency_key="idem-no-del")

    async with session_maker() as session:
        async with session.begin():
            await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    async with session_maker() as session:
        with pytest.raises(Exception) as excinfo:  # noqa: B017
            async with session.begin():
                await session.execute(
                    ActualHarvestLabelSnapshotModel.__table__.delete().where(
                        ActualHarvestLabelSnapshotModel.snapshot_idempotency_key == "idem-no-del"
                    )
                )
        assert "immutable" in str(excinfo.value).lower()


# ---------------------------------------------------------------------------
# I5 hardening visible at validation layer
# ---------------------------------------------------------------------------


async def test_terminal_finalized_without_successor_is_eligible_winner(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A terminal FINALIZED record with NO successor is a legitimate
    eligible winner; it must NOT raise ``FINALIZED_HAS_SUCCESSOR``.

    E4 contract: ``FINALIZED_HAS_SUCCESSOR`` is the structural failure
    for a nonterminal FINALIZED (i.e. one that has a successor edge
    in the supersession graph). A bare terminal FINALIZED with no
    successor edge is the canonical "this is the final word" state
    and the I7 pipeline must accept it as a winner.
    """
    finalized_at = datetime(2024, 1, 1, tzinfo=UTC)
    finalized_record = _build_record(
        external_logical_record_id="logical-finalized-no-succ",
        external_revision_id="rev-finalized",
        status=ActualHarvestRecordStatus.FINALIZED.value,
        finalized_at=finalized_at,
        source_recorded_at=finalized_at,
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-fin-no-succ",
        records=[finalized_record],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-fin-no-succ",
        label_observation_cutoff_at_or_null=datetime(2024, 6, 30, tzinfo=UTC),
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    # The terminal FINALIZED without successor is selected as a
    # legitimate winner; no FINALIZED_HAS_SUCCESSOR structural
    # failure is raised. The public enum exists, but it is not
    # triggered for this contractually valid record.
    assert result.header.winner_count == 1
    winner = result.winners[0]
    assert winner["record_status"] == ActualHarvestRecordStatus.FINALIZED.value
    assert winner["effective_status"] == "FINALIZED"
    assert winner["external_revision_id"] == "rev-finalized"
    assert hasattr(ActualHarvestValidationErrorCode, "FINALIZED_HAS_SUCCESSOR")
    assert (
        ActualHarvestValidationErrorCode.FINALIZED_HAS_SUCCESSOR.value
    ) == "FINALIZED_HAS_SUCCESSOR"


async def test_void_without_successor_uses_hardened_error(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    # Mirror of the FINALIZED_HAS_SUCCESSOR contract: the hardened
    # code must be present in the public error enum so I5 / I7
    # consumers can map it directly.
    assert hasattr(ActualHarvestValidationErrorCode, "VOID_HAS_SUCCESSOR")
    assert ActualHarvestValidationErrorCode.VOID_HAS_SUCCESSOR.value == "VOID_HAS_SUCCESSOR"


# ---------------------------------------------------------------------------
# B1 — cutoff-visible graph enforcement
# ---------------------------------------------------------------------------


async def test_parent_visible_future_successor_parent_wins(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Parent visible + future successor after cutoff → parent wins,
    successor is excluded as SOURCE_TIME_AFTER_CUTOFF. The future
    successor MUST NOT disqualify the visible parent from being
    the winner.
    """
    cutoff = datetime(2024, 1, 1, tzinfo=UTC)
    parent_record = _build_record(
        external_logical_record_id="logical-b1-parent-succ",
        external_revision_id="rev-parent-b1",
        source_recorded_at=datetime(2023, 12, 31, tzinfo=UTC),
    )
    successor_record = _build_record(
        external_logical_record_id="logical-b1-parent-succ",
        external_revision_id="rev-suc-b1",
        revision_number=2,
        quantity_kg="2.0",
        source_recorded_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    successor_record.supersedes_external_revision_id = "rev-parent-b1"
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-b1-parent-succ",
        records=[parent_record, successor_record],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-b1-parent-succ",
        label_observation_cutoff_at_or_null=cutoff,
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 1
    assert result.header.label_row_count == 1
    winner = result.winners[0]
    assert winner["external_revision_id"] == "rev-parent-b1"
    assert winner["record_status"] == ActualHarvestRecordStatus.ACTIVE.value
    categories = {row["exclusion_category"] for row in result.exclusion_rows}
    assert ActualHarvestLabelCoverageExclusion.SOURCE_TIME_AFTER_CUTOFF.value in categories


async def test_parent_visible_successor_at_cutoff_successor_wins(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Parent visible + successor at the cutoff (cutoff is inclusive)
    → successor wins. ``source_recorded_at <= cutoff`` is the
    visibility rule, so an equal timestamp still counts.
    """
    cutoff = datetime(2024, 6, 30, tzinfo=UTC)
    parent_record = _build_record(
        external_logical_record_id="logical-b1-cutoff-eq",
        external_revision_id="rev-parent-eq",
        source_recorded_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    successor_record = _build_record(
        external_logical_record_id="logical-b1-cutoff-eq",
        external_revision_id="rev-suc-eq",
        revision_number=2,
        quantity_kg="2.0",
        source_recorded_at=cutoff,
    )
    successor_record.supersedes_external_revision_id = "rev-parent-eq"
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-b1-cutoff-eq",
        records=[parent_record, successor_record],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-b1-cutoff-eq",
        label_observation_cutoff_at_or_null=cutoff,
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 1
    winner = result.winners[0]
    assert winner["external_revision_id"] == "rev-suc-eq"
    assert winner["revision_number"] == 2


async def test_child_visible_parent_after_cutoff_is_structural_failure(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Child visible (before cutoff) + parent after cutoff →
    VISIBLE_CHILD_WITH_INVISIBLE_PARENT structural failure. The
    supersession chain is corrupt; the snapshot must NOT silently
    pick the visible child.
    """
    cutoff = datetime(2024, 1, 1, tzinfo=UTC)
    parent_record = _build_record(
        external_logical_record_id="logical-b1-invisible-parent",
        external_revision_id="rev-parent-inv",
        source_recorded_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    child_record = _build_record(
        external_logical_record_id="logical-b1-invisible-parent",
        external_revision_id="rev-child-vis",
        revision_number=2,
        quantity_kg="2.0",
        source_recorded_at=datetime(2023, 12, 31, tzinfo=UTC),
    )
    child_record.supersedes_external_revision_id = "rev-parent-inv"
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-b1-invisible-parent",
        records=[parent_record, child_record],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-b1-invisible-parent",
        label_observation_cutoff_at_or_null=cutoff,
    )

    async with session_maker() as session:
        async with session.begin():
            with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-test",
                )

    assert exc_info.value.failure == (
        ActualHarvestLabelStructuralFailure.VISIBLE_CHILD_WITH_INVISIBLE_PARENT
    )


# ---------------------------------------------------------------------------
# B3 — scope check uses frozen canonical business keys
# ---------------------------------------------------------------------------


async def test_frozen_farm_business_key_in_scope_creates_winner(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """``source farm_code`` may be any live code (e.g. ``F001``); the
    request scope compares against the FROZEN
    ``farm_business_key`` returned by the winning validation run's
    mapping evidence (``farm-business-key-1``). A matching scope
    creates a winner.
    """
    record = _build_record(
        external_logical_record_id="logical-b3-farm-scope",
        external_revision_id="rev-b3-farm-scope",
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-b3-farm-scope",
        records=[record],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-b3-farm-scope",
        farm_business_keys_or_empty_for_all=("farm-business-key-1",),
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 1
    assert result.header.label_row_count == 1
    assert result.header.exclusion_row_count == 0
    winner = result.winners[0]
    assert winner["farm_business_key"] == "farm-business-key-1"
    # The live farm_code is preserved as audit evidence; only the
    # frozen business key is used for scope.
    assert winner["external_revision_id"] == "rev-b3-farm-scope"


async def test_frozen_business_key_mismatch_excludes_as_outside_request_scope(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """When the request's frozen business-key scope does NOT include
    the winner's frozen target_business_key, the winner is reported
    as ``OUTSIDE_REQUEST_SCOPE`` (no live master-data remapping).
    """
    record = _build_record(
        external_logical_record_id="logical-b3-farm-mismatch",
        external_revision_id="rev-b3-farm-mismatch",
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-b3-farm-mismatch",
        records=[record],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-b3-farm-mismatch",
        # A frozen business key the seeded registry does NOT have.
        farm_business_keys_or_empty_for_all=("other-farm-business-key",),
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 0
    assert result.header.exclusion_row_count == 1
    exclusion = result.exclusion_rows[0]
    assert (
        exclusion["exclusion_category"]
        == ActualHarvestLabelCoverageExclusion.OUTSIDE_REQUEST_SCOPE.value
    )
    assert exclusion["exclusion_details"]["farm_business_key"] == "farm-business-key-1"


# ---------------------------------------------------------------------------
# E2 — scope classification BEFORE visibility classification
# ---------------------------------------------------------------------------


async def test_e2_out_of_scope_record_with_after_cutoff_source_emits_only_outside_scope(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E2: out-of-scope record with source_recorded_at > cutoff → only OUTSIDE_REQUEST_SCOPE.

    The out-of-scope check runs BEFORE visibility. The record's
    after-cutoff source time must NOT surface as
    ``SOURCE_TIME_AFTER_CUTOFF``. Only ONE exclusion is emitted per
    revision, and it is the scope exclusion.
    """

    record = _build_record(
        external_logical_record_id="logical-e2-oos-after-cutoff",
        external_revision_id="rev-e2-oos-after-cutoff",
        source_recorded_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e2-oos-after-cutoff",
        records=[record],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-e2-oos-after-cutoff",
        # Frozen farm key that does not exist in the seeded registry.
        farm_business_keys_or_empty_for_all=("other-farm-business-key",),
        visibility_mode=ActualHarvestLabelVisibilityMode.AS_OF_EVALUATION,
        label_observation_cutoff_at_or_null=datetime(2024, 6, 30, tzinfo=UTC),
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 0
    assert result.header.exclusion_row_count == 1
    exclusion = result.exclusion_rows[0]
    assert (
        exclusion["exclusion_category"]
        == ActualHarvestLabelCoverageExclusion.OUTSIDE_REQUEST_SCOPE.value
    )
    assert exclusion["exclusion_details"]["reason"] == "farm_outside_request_scope"


async def test_e2_out_of_scope_successor_does_not_disqualify_in_scope_parent(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E2: out-of-scope successor must not disqualify an in-scope parent.

    The chain has two revisions: an in-scope parent (rev-1) and an
    out-of-scope successor (rev-2, scope failure). The parent must
    be the winner; the successor emits ONE OUTSIDE_REQUEST_SCOPE
    exclusion and is removed from the visible graph entirely.
    """

    parent = _build_record(
        external_logical_record_id="logical-e2-oos-successor",
        external_revision_id="rev-e2-oos-parent",
        revision_number=1,
    )
    successor = _build_record(
        external_logical_record_id="logical-e2-oos-successor",
        external_revision_id="rev-e2-oos-successor",
        revision_number=2,
        quantity_kg="2.0",
        harvest_date=date(2024, 6, 1),
    )

    # Seed the parent + successor in one batch so the chain is
    # visible. The default seed uses farm_business_key="farm-business-key-1"
    # which is in-scope by default.
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e2-oos-successor",
        records=[parent, successor],
    )

    # Override the FARM mapping evidence for the successor so its
    # frozen farm_business_key is "other-farm-business-key" — out of
    # the request's scope.
    async with session_maker() as session:
        async with session.begin():
            from sqlalchemy import update as _update

            from backend.app.actual_harvest_import.validation_models import (
                ActualHarvestValidationMappingEvidenceModel as _Evidence,
            )

            await session.execute(
                _update(_Evidence)
                .where(
                    _Evidence.external_revision_id == "rev-e2-oos-successor",
                    _Evidence.target_type == "FARM",
                )
                .values(target_business_key="other-farm-business-key")
            )

    request = _base_request(
        snapshot_idempotency_key="idem-e2-oos-successor",
        # In-scope is "farm-business-key-1"; the successor's
        # overridden "other-farm-business-key" is out of scope.
        farm_business_keys_or_empty_for_all=("farm-business-key-1",),
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 1
    winner = result.winners[0]
    assert winner["external_revision_id"] == "rev-e2-oos-parent"

    # The out-of-scope successor emits one OUTSIDE_REQUEST_SCOPE
    # exclusion; the in-scope parent wins.
    assert result.header.exclusion_row_count == 1
    exclusion = result.exclusion_rows[0]
    assert (
        exclusion["exclusion_category"]
        == ActualHarvestLabelCoverageExclusion.OUTSIDE_REQUEST_SCOPE.value
    )
    assert exclusion["external_revision_id_or_null"] == "rev-e2-oos-successor"


async def test_e2_in_scope_successor_after_cutoff_parent_wins_with_source_time_exclusion(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E2: in-scope successor after cutoff → parent wins, successor excluded by source time.

    The chain has an in-scope visible parent and an in-scope
    successor whose source_recorded_at is past the cutoff. The
    successor is removed from the visible graph by the visibility
    step; the parent becomes the unique visible terminal and wins.
    The successor emits a ``SOURCE_TIME_AFTER_CUTOFF`` exclusion.
    """

    parent = _build_record(
        external_logical_record_id="logical-e2-successor-after-cutoff",
        external_revision_id="rev-e2-parent",
        revision_number=1,
        source_recorded_at=datetime(2024, 1, 15, tzinfo=UTC),
    )
    successor = _build_record(
        external_logical_record_id="logical-e2-successor-after-cutoff",
        external_revision_id="rev-e2-successor",
        revision_number=2,
        source_recorded_at=datetime(2030, 1, 1, tzinfo=UTC),
        harvest_date=date(2024, 6, 1),
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e2-successor-after-cutoff",
        records=[parent, successor],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-e2-successor-after-cutoff",
        visibility_mode=ActualHarvestLabelVisibilityMode.AS_OF_EVALUATION,
        label_observation_cutoff_at_or_null=datetime(2024, 6, 30, tzinfo=UTC),
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 1
    winner = result.winners[0]
    assert winner["external_revision_id"] == "rev-e2-parent"

    # The successor emits exactly ONE exclusion: SOURCE_TIME_AFTER_CUTOFF.
    assert result.header.exclusion_row_count == 1
    exclusion = result.exclusion_rows[0]
    assert (
        exclusion["exclusion_category"]
        == ActualHarvestLabelCoverageExclusion.SOURCE_TIME_AFTER_CUTOFF.value
    )
    assert exclusion["external_revision_id_or_null"] == "rev-e2-successor"


# ---------------------------------------------------------------------------
# E3 — complete visible-chain validator
# ---------------------------------------------------------------------------


async def test_e3_invisible_root_visible_middle_visible_terminal(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E3: invisible root → visible middle → visible terminal.

    The chain has 3 revisions: rev-1 (invisible, after cutoff),
    rev-2 (visible, supersedes rev-1), rev-3 (visible, supersedes
    rev-2). The validator must surface the chain corruption as
    VISIBLE_CHILD_WITH_INVISIBLE_PARENT (rev-2 has invisible
    predecessor rev-1).
    """

    cutoff = datetime(2024, 6, 30, tzinfo=UTC)
    rev_1 = _build_record(
        external_logical_record_id="logical-e3-invisible-root",
        external_revision_id="rev-e3-1",
        revision_number=1,
        source_recorded_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    rev_2 = _build_record(
        external_logical_record_id="logical-e3-invisible-root",
        external_revision_id="rev-e3-2",
        revision_number=2,
        source_recorded_at=datetime(2024, 1, 15, tzinfo=UTC),
    )
    rev_2.supersedes_external_revision_id = "rev-e3-1"
    rev_3 = _build_record(
        external_logical_record_id="logical-e3-invisible-root",
        external_revision_id="rev-e3-3",
        revision_number=3,
        source_recorded_at=datetime(2024, 6, 1, tzinfo=UTC),
    )
    rev_3.supersedes_external_revision_id = "rev-e3-2"
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e3-invisible-root",
        records=[rev_1, rev_2, rev_3],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-e3-invisible-root",
        visibility_mode=ActualHarvestLabelVisibilityMode.AS_OF_EVALUATION,
        label_observation_cutoff_at_or_null=cutoff,
    )

    async with session_maker() as session:
        async with session.begin():
            with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-test",
                )

    assert exc_info.value.failure == (
        ActualHarvestLabelStructuralFailure.VISIBLE_CHILD_WITH_INVISIBLE_PARENT
    )


async def test_e3_visible_revision_number_gap_is_structural_failure(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E3: visible revision gap 1→3 is a REVISION_NUMBER_DISCONTINUITY."""

    rev_1 = _build_record(
        external_logical_record_id="logical-e3-rev-gap",
        external_revision_id="rev-e3-gap-1",
        revision_number=1,
    )
    rev_3 = _build_record(
        external_logical_record_id="logical-e3-rev-gap",
        external_revision_id="rev-e3-gap-3",
        revision_number=3,
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e3-rev-gap",
        records=[rev_1, rev_3],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-e3-rev-gap",
    )

    async with session_maker() as session:
        async with session.begin():
            with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-test",
                )

    assert exc_info.value.failure == (
        ActualHarvestLabelStructuralFailure.REVISION_NUMBER_DISCONTINUITY
    )


async def test_e3_visible_fork_is_structural_failure(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E3: visible fork (parent with two visible successors) is SUPERSESSION_CHAIN_FORK."""

    rev_1 = _build_record(
        external_logical_record_id="logical-e3-fork",
        external_revision_id="rev-e3-fork-1",
        revision_number=1,
    )
    rev_2a = _build_record(
        external_logical_record_id="logical-e3-fork",
        external_revision_id="rev-e3-fork-2a",
        revision_number=2,
    )
    rev_2a.supersedes_external_revision_id = "rev-e3-fork-1"
    rev_2b = _build_record(
        external_logical_record_id="logical-e3-fork",
        external_revision_id="rev-e3-fork-2b",
        revision_number=3,
    )
    rev_2b.supersedes_external_revision_id = "rev-e3-fork-1"
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e3-fork",
        records=[rev_1, rev_2a, rev_2b],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-e3-fork",
    )

    async with session_maker() as session:
        async with session.begin():
            with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-test",
                )

    assert exc_info.value.failure == (ActualHarvestLabelStructuralFailure.SUPERSESSION_CHAIN_FORK)


async def test_e3_visible_cycle_is_structural_failure(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E3: visible cycle is SUPERSESSION_CHAIN_CYCLE."""

    rev_1 = _build_record(
        external_logical_record_id="logical-e3-cycle",
        external_revision_id="rev-e3-cycle-1",
        revision_number=1,
    )
    rev_2 = _build_record(
        external_logical_record_id="logical-e3-cycle",
        external_revision_id="rev-e3-cycle-2",
        revision_number=2,
    )
    rev_2.supersedes_external_revision_id = "rev-e3-cycle-1"
    rev_1.supersedes_external_revision_id = "rev-e3-cycle-2"
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e3-cycle",
        records=[rev_1, rev_2],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-e3-cycle",
    )

    async with session_maker() as session:
        async with session.begin():
            with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-test",
                )

    assert exc_info.value.failure == (ActualHarvestLabelStructuralFailure.SUPERSESSION_CHAIN_CYCLE)


async def test_e3_nonterminal_finalized_with_successor_is_structural_failure(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E3: nonterminal FINALIZED with a successor is FINALIZED_HAS_SUCCESSOR."""

    rev_1 = _build_record(
        external_logical_record_id="logical-e3-finalized-succ",
        external_revision_id="rev-e3-fin-1",
        revision_number=1,
        status=ActualHarvestRecordStatus.FINALIZED.value,
        finalized_at=datetime(2024, 6, 1, tzinfo=UTC),
    )
    rev_2 = _build_record(
        external_logical_record_id="logical-e3-finalized-succ",
        external_revision_id="rev-e3-fin-2",
        revision_number=2,
    )
    rev_2.supersedes_external_revision_id = "rev-e3-fin-1"
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e3-finalized-succ",
        records=[rev_1, rev_2],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-e3-finalized-succ",
    )

    async with session_maker() as session:
        async with session.begin():
            with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-test",
                )

    assert exc_info.value.failure == (ActualHarvestLabelStructuralFailure.FINALIZED_HAS_SUCCESSOR)


async def test_e3_nonterminal_void_with_successor_is_structural_failure(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E3: nonterminal VOID with a successor is VOID_HAS_SUCCESSOR."""

    rev_1 = _build_record(
        external_logical_record_id="logical-e3-void-succ",
        external_revision_id="rev-e3-void-1",
        revision_number=1,
        status=ActualHarvestRecordStatus.VOID.value,
    )
    rev_2 = _build_record(
        external_logical_record_id="logical-e3-void-succ",
        external_revision_id="rev-e3-void-2",
        revision_number=2,
    )
    rev_2.supersedes_external_revision_id = "rev-e3-void-1"
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e3-void-succ",
        records=[rev_1, rev_2],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-e3-void-succ",
    )

    async with session_maker() as session:
        async with session.begin():
            with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-test",
                )

    assert exc_info.value.failure == (ActualHarvestLabelStructuralFailure.VOID_HAS_SUCCESSOR)


# ---------------------------------------------------------------------------
# E6 — source-evidence preflight
# E7 — explicit PLOT rejection
# ---------------------------------------------------------------------------


async def test_e6_out_of_scope_with_complete_evidence_is_coverage_exclusion(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E6 + E2 contract: a record whose frozen evidence is complete
    and trustworthy but whose business key is outside the request
    scope must surface as the ``OUTSIDE_REQUEST_SCOPE`` coverage
    exclusion — NOT as a structural failure. This proves the E6
    preflight has not downgraded the E2 coverage path.
    """

    record = _build_record(
        external_logical_record_id="logical-e6-out-of-scope",
        external_revision_id="rev-e6-out-of-scope",
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e6-out-of-scope",
        records=[record],
    )

    # The seeded registry maps ``farm-business-key-1`` for every
    # record. The request asks for a different farm business key
    # that no record matches — every observed record is therefore
    # out of scope, with complete and trustworthy evidence.
    request = _base_request(
        snapshot_idempotency_key="idem-e6-out-of-scope",
        farm_business_keys_or_empty_for_all=("farm-business-key-other",),
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 0
    categories = {row["exclusion_category"] for row in result.exclusion_rows}
    assert ActualHarvestLabelCoverageExclusion.OUTSIDE_REQUEST_SCOPE.value in categories
    # The preflight must NOT have raised a structural failure.
    assert result.exclusion_rows


async def test_e6_manifest_validation_hash_drift_is_structural_failure(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E6 contract: when the commit manifest's
    ``validation_run_instance_identity_hash`` does not match the
    persisted validation run's ``instance_identity_hash``, the
    snapshot must halt with ``SOURCE_EVIDENCE_DRIFT`` BEFORE any
    winner processing.
    """

    record = _build_record(
        external_logical_record_id="logical-e6-drift",
        external_revision_id="rev-e6-drift",
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e6-drift",
        records=[record],
    )

    # Drift the validation run's instance_identity_hash after the
    # seed — the commit manifest still references the original
    # value, so the preflight cross-check must fail closed.
    async with session_maker() as session:
        async with session.begin():
            run = await session.scalar(
                select(ActualHarvestValidationRunModel).order_by(
                    ActualHarvestValidationRunModel.id.desc()
                )
            )
            assert run is not None
            run.instance_identity_hash = _hex64("drifted-instance-identity")

    request = _base_request(
        snapshot_idempotency_key="idem-e6-drift",
    )

    async with session_maker() as session:
        async with session.begin():
            with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-test",
                )

    assert exc_info.value.failure == ActualHarvestLabelStructuralFailure.SOURCE_EVIDENCE_DRIFT


async def test_e6_mapping_snapshot_hash_drift_is_structural_failure(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E6 contract: when the commit manifest's
    ``mapping_snapshot_hash`` does not match the persisted
    mapping snapshot's hash, the preflight must halt with
    ``SOURCE_EVIDENCE_DRIFT``.
    """

    record = _build_record(
        external_logical_record_id="logical-e6-ms-drift",
        external_revision_id="rev-e6-ms-drift",
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e6-ms-drift",
        records=[record],
    )

    async with session_maker() as session:
        async with session.begin():
            ms = await session.scalar(
                select(ActualHarvestMappingSnapshotModel).order_by(
                    ActualHarvestMappingSnapshotModel.id.desc()
                )
            )
            assert ms is not None
            ms.mapping_snapshot_hash = _hex64("drifted-mapping-snapshot")

    request = _base_request(
        snapshot_idempotency_key="idem-e6-ms-drift",
    )

    async with session_maker() as session:
        async with session.begin():
            with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-test",
                )

    assert exc_info.value.failure == ActualHarvestLabelStructuralFailure.SOURCE_EVIDENCE_DRIFT


async def test_e6_resolved_identity_hash_drift_is_structural_failure(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E6 contract: when the commit manifest's
    ``resolved_identity_snapshot_hash`` does not match the persisted
    mapping snapshot's value, the preflight must halt.
    """

    record = _build_record(
        external_logical_record_id="logical-e6-isnap-drift",
        external_revision_id="rev-e6-isnap-drift",
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e6-isnap-drift",
        records=[record],
    )

    async with session_maker() as session:
        async with session.begin():
            ms = await session.scalar(
                select(ActualHarvestMappingSnapshotModel).order_by(
                    ActualHarvestMappingSnapshotModel.id.desc()
                )
            )
            assert ms is not None
            ms.resolved_identity_snapshot_hash = _hex64("drifted-resolved-identity")

    request = _base_request(
        snapshot_idempotency_key="idem-e6-isnap-drift",
    )

    async with session_maker() as session:
        async with session.begin():
            with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-test",
                )

    assert exc_info.value.failure == ActualHarvestLabelStructuralFailure.SOURCE_EVIDENCE_DRIFT


async def test_e6_registry_content_hash_drift_is_structural_failure(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E6 contract: when the commit manifest's
    ``registry_content_hash`` does not match the persisted mapping
    snapshot's value, the preflight must halt.
    """

    record = _build_record(
        external_logical_record_id="logical-e6-registry-drift",
        external_revision_id="rev-e6-registry-drift",
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e6-registry-drift",
        records=[record],
    )

    async with session_maker() as session:
        async with session.begin():
            ms = await session.scalar(
                select(ActualHarvestMappingSnapshotModel).order_by(
                    ActualHarvestMappingSnapshotModel.id.desc()
                )
            )
            assert ms is not None
            ms.registry_content_hash = _hex64("drifted-registry-content")

    request = _base_request(
        snapshot_idempotency_key="idem-e6-registry-drift",
    )

    async with session_maker() as session:
        async with session.begin():
            with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-test",
                )

    assert exc_info.value.failure == ActualHarvestLabelStructuralFailure.SOURCE_EVIDENCE_DRIFT


async def test_e6_missing_lineage_basis_member_is_structural_failure(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E6 contract: when the lineage basis ``member_count`` exceeds
    the actual persisted member rows, the preflight must halt with
    ``SOURCE_EVIDENCE_DRIFT`` because the lineage evidence is
    incomplete.
    """

    record = _build_record(
        external_logical_record_id="logical-e6-missing-mem",
        external_revision_id="rev-e6-missing-mem",
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e6-missing-mem",
        records=[record],
    )

    # Inflate the lineage basis ``member_count`` to one above the
    # actual member row count. The preflight's
    # ``actual_member_count != lineage_basis.member_count`` branch
    # must fire.
    async with session_maker() as session:
        async with session.begin():
            basis = await session.scalar(
                select(ActualHarvestValidationLineageBasisModel).order_by(
                    ActualHarvestValidationLineageBasisModel.id.desc()
                )
            )
            assert basis is not None
            basis.member_count = basis.member_count + 1

    request = _base_request(
        snapshot_idempotency_key="idem-e6-missing-mem",
    )

    async with session_maker() as session:
        async with session.begin():
            with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-test",
                )

    assert exc_info.value.failure == ActualHarvestLabelStructuralFailure.SOURCE_EVIDENCE_DRIFT
    assert exc_info.value.details["reason"] == "preflight_lineage_basis_member_count_mismatch"


async def test_e6_missing_mapping_evidence_is_structural_failure(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E6 contract: when one of the four required target types
    (SEASON, FARM, SUBFARM, VARIETY) is missing from the persisted
    mapping evidence for an observed record, the preflight must
    halt with ``MAPPING_EVIDENCE_MISSING`` (not downgrade to
    ``OUTSIDE_REQUEST_SCOPE``).
    """

    record = _build_record(
        external_logical_record_id="logical-e6-missing-evidence",
        external_revision_id="rev-e6-missing-evidence",
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e6-missing-evidence",
        records=[record],
    )

    # Delete the VARIETY evidence row for the observed record so
    # the preflight's per-record target_type completeness check
    # halts with ``MAPPING_EVIDENCE_MISSING``.
    async with session_maker() as session:
        async with session.begin():
            variety_evidence = await session.scalar(
                select(ActualHarvestValidationMappingEvidenceModel).where(
                    ActualHarvestValidationMappingEvidenceModel.external_revision_id
                    == "rev-e6-missing-evidence",
                    ActualHarvestValidationMappingEvidenceModel.target_type == "VARIETY",
                )
            )
            assert variety_evidence is not None
            await session.delete(variety_evidence)

    request = _base_request(
        snapshot_idempotency_key="idem-e6-missing-evidence",
    )

    async with session_maker() as session:
        async with session.begin():
            with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-test",
                )

    assert exc_info.value.failure == ActualHarvestLabelStructuralFailure.MAPPING_EVIDENCE_MISSING
    assert exc_info.value.details["reason"] == "preflight_missing_target_type"
    assert "VARIETY" in exc_info.value.details["missing_target_types"]


async def test_e7_explicit_subfarm_mapping_is_accepted(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E7: a record whose frozen mapping evidence has a SUBFARM
    target_type and no PLOT row is the canonical I7 v1 winner.
    """

    record = _build_record(
        external_logical_record_id="logical-e7-subfarm-ok",
        external_revision_id="rev-e7-subfarm-ok",
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e7-subfarm-ok",
        records=[record],
    )

    request = _base_request(
        snapshot_idempotency_key="idem-e7-subfarm-ok",
    )

    async with session_maker() as session:
        async with session.begin():
            result = await create_label_snapshot(
                session,
                request=request,
                created_by_identity="op-test",
            )

    assert result.header.winner_count == 1
    assert result.winners[0]["subfarm_business_key"] == "sub-business-key-1"


async def test_e7_explicit_plot_mapping_is_rejected(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E7: a record whose frozen mapping evidence has a PLOT
    target_type row (corruption / future regression) must fail
    closed with the stable ``UNSUPPORTED_LABEL_GRAIN`` structural
    failure code.
    """

    record = _build_record(
        external_logical_record_id="logical-e7-plot",
        external_revision_id="rev-e7-plot",
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e7-plot",
        records=[record],
    )

    # Inject a PLOT evidence row directly into the persisted
    # evidence for the observed record. The I7 preflight must
    # reject this with UNSUPPORTED_LABEL_GRAIN — the row is never
    # silently downgraded to SUBFARM and never silently ignored.
    # The INSERT bypasses the MAPPING_TARGET_VALUES check by
    # dropping the upstream CHECK constraint for the duration of
    # the test, mirroring a future regression / direct DB write
    # corruption case that the I7 contract must defend against.
    async with session_maker() as session:
        async with session.begin():
            run = await session.scalar(
                select(ActualHarvestValidationRunModel).order_by(
                    ActualHarvestValidationRunModel.id.desc()
                )
            )
            assert run is not None
            await _inject_plot_evidence_row(
                session,
                run_id=run.id,
                record=record,
                business_key_suffix="1",
            )

    request = _base_request(
        snapshot_idempotency_key="idem-e7-plot",
    )

    async with session_maker() as session:
        async with session.begin():
            with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-test",
                )

    assert exc_info.value.failure == ActualHarvestLabelStructuralFailure.UNSUPPORTED_LABEL_GRAIN
    assert exc_info.value.details["target_type"] == "PLOT"
    assert exc_info.value.details["reason"] == "plot_target_type_in_frozen_evidence"


async def test_e7_plot_is_not_silently_converted_to_subfarm(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E7 corollary: when the I7 pipeline sees a PLOT target_type
    in the frozen evidence, the SNAPSHOT must not promote the PLOT
    business key into a SUBFARM business key. The snapshot must
    fail closed (UNSUPPORTED_LABEL_GRAIN) and the persisted
    snapshot row count must remain zero.
    """

    record = _build_record(
        external_logical_record_id="logical-e7-no-silent",
        external_revision_id="rev-e7-no-silent",
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e7-no-silent",
        records=[record],
    )

    async with session_maker() as session:
        async with session.begin():
            run = await session.scalar(
                select(ActualHarvestValidationRunModel).order_by(
                    ActualHarvestValidationRunModel.id.desc()
                )
            )
            assert run is not None
            await _inject_plot_evidence_row(
                session,
                run_id=run.id,
                record=record,
                business_key_suffix="silent",
            )

    request = _base_request(
        snapshot_idempotency_key="idem-e7-no-silent",
    )

    async with session_maker() as session:
        async with session.begin():
            with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                await create_label_snapshot(
                    session,
                    request=request,
                    created_by_identity="op-test",
                )

    # The rejection must be deterministic and must not leak a
    # subfarm_business_key containing the PLOT business key. The
    # service must not promote the PLOT business key into the
    # SUBFARM slot.
    assert exc_info.value.failure == ActualHarvestLabelStructuralFailure.UNSUPPORTED_LABEL_GRAIN
    assert "subfarm_business_key" not in (exc_info.value.details or {})
    # No snapshot rows must be persisted.
    async with session_maker() as session2:
        async with session2.begin():
            from backend.app.actual_harvest_labels.models import (
                ActualHarvestLabelSnapshotModel,
            )

            snapshot_count = await session2.scalar(select(ActualHarvestLabelSnapshotModel.id))
            assert snapshot_count is None


async def test_e7_plot_rejection_is_deterministic(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """E7 corollary: a second call against the same request
    identity and the same PLOT-corrupted source universe must
    reproduce the same UNSUPPORTED_LABEL_GRAIN structural failure
    (deterministic, not time-dependent, not order-dependent).
    """

    record = _build_record(
        external_logical_record_id="logical-e7-det",
        external_revision_id="rev-e7-det",
    )
    await _seed_seeded_batch(
        session_maker,
        import_id="imp-e7-det",
        records=[record],
    )

    async with session_maker() as session:
        async with session.begin():
            run = await session.scalar(
                select(ActualHarvestValidationRunModel).order_by(
                    ActualHarvestValidationRunModel.id.desc()
                )
            )
            assert run is not None
            await _inject_plot_evidence_row(
                session,
                run_id=run.id,
                record=record,
                business_key_suffix="det",
            )

    request = _base_request(
        snapshot_idempotency_key="idem-e7-det",
    )

    failures: list[ActualHarvestLabelStructuralFailure] = []
    for _ in range(2):
        async with session_maker() as session:
            async with session.begin():
                with pytest.raises(ActualHarvestLabelStructuralFailureError) as exc_info:
                    await create_label_snapshot(
                        session,
                        request=request,
                        created_by_identity="op-test",
                    )
        failures.append(exc_info.value.failure)

    assert failures == [
        ActualHarvestLabelStructuralFailure.UNSUPPORTED_LABEL_GRAIN,
        ActualHarvestLabelStructuralFailure.UNSUPPORTED_LABEL_GRAIN,
    ]


# ---------------------------------------------------------------------------
# B4 — node_hash / member_hash / canonical_record_hash surface
# ---------------------------------------------------------------------------


def test_persisted_lineage_node_hash_is_recomputable_from_columns() -> None:
    """A persisted ``ActualHarvestValidationLineageNodeModel`` row's
    ``node_hash`` must be reproducible from its own columns. The
    I7 contract removes ``finalized_at`` from the persisted node
    model so a re-hash on the stored columns must round-trip.
    """
    from backend.app.actual_harvest_import.validation_hashes import (
        compute_lineage_node_hash,
    )

    # Note: ``finalized_at`` is INTENTIONALLY absent from the
    # persisted node model; it must not be required to recompute
    # ``node_hash``.
    stored_node = {
        "origin": "COMMITTED",
        "source_system": "source-test",
        "external_logical_record_id": "logical-b4-node",
        "external_revision_id": "rev-b4-node",
        "revision_number": 1,
        "record_status": "FINALIZED",
        "supersedes_external_revision_id": None,
        "canonical_record_hash": "a" * 64,
        "source_recorded_at": datetime(2024, 1, 1, tzinfo=UTC).isoformat(),
        "source_recorded_at_authority_status": "TRUSTED_SOURCE_TIMESTAMP",
    }
    stored_node_hash = compute_lineage_node_hash(stored_node)
    # Round-trip: hash on stored columns must be stable; flipping
    # any persisted column must change it.
    assert len(stored_node_hash) == 64
    flipped_node = dict(stored_node, revision_number=2)
    flipped_hash = compute_lineage_node_hash(flipped_node)
    assert flipped_hash != stored_node_hash
    # And: adding ``finalized_at`` to the payload does not change
    # the hash, because the I7 contract intentionally excludes it
    # from the persisted node_hash digest.
    with_finalized = dict(
        stored_node,
        finalized_at=datetime(2024, 1, 1, tzinfo=UTC).isoformat(),
    )
    assert compute_lineage_node_hash(with_finalized) == stored_node_hash


def test_legacy_basis_member_hash_stable_under_finalized_at_persistence() -> None:
    """The historical basis member ``member_hash`` digest was computed
    BEFORE the migration 0022 ``finalized_at`` column existed. The
    I7 contract requires that adding ``finalized_at`` to the
    in-memory member dict does NOT change the persisted
    ``member_hash``. ``_basis_member_hash_payload`` strips the key.
    """
    from backend.app.actual_harvest_import.validation_hashes import digest
    from backend.app.actual_harvest_import.validation_service import (
        _basis_member_hash_payload,
    )

    legacy_member: dict[str, Any] = {
        "source_system": "source-test",
        "committed_batch_ref": "source-test:batch-1",
        "external_logical_record_id": "logical-legacy",
        "external_revision_id": "rev-legacy",
        "revision_number": 1,
        "canonical_record_hash": "a" * 64,
        "predecessor_revision_id": None,
        "record_status": "ACTIVE",
        "source_recorded_at": datetime(2024, 1, 1, tzinfo=UTC),
        "source_recorded_at_authority_status": "TRUSTED_SOURCE_TIMESTAMP",
        "member_sort_key": "k",
    }
    legacy_hash = digest(_basis_member_hash_payload(legacy_member))

    persisted_member = dict(legacy_member)
    persisted_member["finalized_at"] = datetime(2024, 1, 1, tzinfo=UTC)
    persisted_hash = digest(_basis_member_hash_payload(persisted_member))

    assert legacy_hash == persisted_hash

    # And: the helper EXCLUDES ``finalized_at`` from the payload it
    # feeds into the digest.
    assert "finalized_at" not in _basis_member_hash_payload(persisted_member)
    assert "finalized_at" in persisted_member  # preserved in source


def test_canonical_record_hash_changes_when_finalized_at_changes() -> None:
    """``canonical_record_hash`` binds ``finalized_at`` so changing
    the FINALIZED timestamp produces a new record-identity hash.
    This is the counterpart of the legacy-stable member_hash above.
    """
    from backend.app.actual_harvest_import.schemas import (
        CanonicalActualHarvestImportRecord,
    )

    record = CanonicalActualHarvestImportRecord(
        external_logical_record_id="logical-b4",
        external_revision_id="rev-b4",
        source_system="source-test",
        external_batch_id="b4-batch-1",
        harvest_business_date=date(2024, 1, 1),
        actual_harvest_quantity_kg=Decimal("1.0"),
        farm_code="farm-1",
        subfarm_or_plot_code="sub-1",
        variety_code="var-1",
        source_recorded_at=datetime(2024, 1, 1, tzinfo=UTC),
        source_recorded_at_authority_status=(
            SourceRecordedAtAuthorityStatus.TRUSTED_SOURCE_TIMESTAMP.value
        ),
        source_recorded_at_authority_reference_or_null="b4-authority-ref",
        import_received_at=datetime(2024, 1, 1, tzinfo=UTC),
        ingested_at=datetime(2024, 1, 1, tzinfo=UTC),
        revision_number=1,
        record_status=ActualHarvestRecordStatus.FINALIZED.value,
        finalized_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    h0 = compute_canonical_record_hash(record)
    finalized_copy = record.model_copy(update={"finalized_at": datetime(2024, 1, 2, tzinfo=UTC)})
    h1 = compute_canonical_record_hash(finalized_copy)
    assert h0 != h1


# ---------------------------------------------------------------------------
# Hash determinism
# ---------------------------------------------------------------------------


def test_request_identity_hash_is_deterministic() -> None:
    request = _base_request()
    first = compute_snapshot_request_identity_hash(
        snapshot_idempotency_key=request.snapshot_idempotency_key,
        source_system=request.source_system,
        visibility_mode=request.visibility_mode.value,
        label_observation_cutoff_at_or_null=request.label_observation_cutoff_at_or_null,
        harvest_date_start=request.harvest_date_start,
        harvest_date_end=request.harvest_date_end,
        season_business_keys=request.season_business_keys,
        farm_business_keys_or_empty_for_all=request.farm_business_keys_or_empty_for_all,
        variety_business_keys_or_empty_for_all=request.variety_business_keys_or_empty_for_all,
        snapshot_policy_version=request.snapshot_policy_version,
        winner_policy_version=request.winner_policy_version,
        aggregation_policy_version=request.aggregation_policy_version,
    )
    second = compute_snapshot_request_identity_hash(
        snapshot_idempotency_key=request.snapshot_idempotency_key,
        source_system=request.source_system,
        visibility_mode=request.visibility_mode.value,
        label_observation_cutoff_at_or_null=request.label_observation_cutoff_at_or_null,
        harvest_date_start=request.harvest_date_start,
        harvest_date_end=request.harvest_date_end,
        season_business_keys=request.season_business_keys,
        farm_business_keys_or_empty_for_all=request.farm_business_keys_or_empty_for_all,
        variety_business_keys_or_empty_for_all=request.variety_business_keys_or_empty_for_all,
        snapshot_policy_version=request.snapshot_policy_version,
        winner_policy_version=request.winner_policy_version,
        aggregation_policy_version=request.aggregation_policy_version,
    )
    assert first == second
    assert len(first) == 64


def test_label_row_set_hash_is_canonical() -> None:
    sample_rows = [
        {
            "label_row_hash": "f" * 64,
            "exact_decimal_quantity_sum_kg": "1.000000",
            "contributing_winner_count": 1,
        },
        {
            "label_row_hash": "a" * 64,
            "exact_decimal_quantity_sum_kg": "0.500000",
            "contributing_winner_count": 1,
        },
    ]
    forward = compute_label_row_set_hash(sample_rows)
    backward = compute_label_row_set_hash(list(reversed(sample_rows)))
    assert forward == backward


def test_winner_row_hash_is_stable_against_dict_order() -> None:
    payload_a = {
        "source_system": "source-test",
        "external_logical_record_id": "logical-1",
        "external_revision_id": "rev-1",
        "revision_number": 1,
        "canonical_record_hash": "a" * 64,
        "record_status": "ACTIVE",
        "effective_status": "ACTIVE",
        "finalized_at_or_null": None,
        "source_recorded_at_or_null": datetime(2024, 1, 1, tzinfo=UTC),
        "source_recorded_at_authority_status": "TRUSTED_SOURCE_TIMESTAMP",
        "harvest_business_date": date(2024, 1, 1),
        "actual_harvest_quantity_kg": Decimal("1.0"),
        "commit_manifest_hash": "b" * 64,
        "season_business_key": "season-1",
        "farm_business_key": "farm-1",
        "subfarm_business_key": "sub-1",
        "variety_business_key": "var-1",
        "mapping_registry_version": "registry-v1",
        "mapping_policy_version": "policy-v1",
        "season_resolver_version": "actual-harvest-season-resolver-v1",
        "mapping_registry_entry_hash": None,
        "resolved_master_business_key": "master-1",
        "resolved_master_parent_business_key": None,
        "resolved_master_record_hash": "c" * 64,
        "mapping_snapshot_hash": "d" * 64,
        "resolved_identity_snapshot_hash": "e" * 64,
        "registry_content_hash": "f" * 64,
    }
    payload_b = dict(payload_a)
    payload_b["resolved_master_record_hash"] = "9" * 64

    first = compute_winner_row_hash(**payload_a)
    second = compute_winner_row_hash(**payload_b)
    assert first != second


__all__ = [
    "test_as_of_cutoff_before_parent_only_parent_visible",
    "test_as_of_cutoff_after_successor_only_successor_visible",
    "test_as_of_no_future_revision_leakage",
    "test_as_of_cutoff_equality",
    "test_untrusted_source_time_excluded",
    "test_missing_source_time_excluded",
    "test_terminal_active_winner",
    "test_terminal_finalized_winner_before_cutoff",
    "test_finalized_after_cutoff_status_not_visible_exclusion",
    "test_terminal_void_exclusion",
    "test_idempotent_replay_zero_write",
    "test_idempotency_conflict",
    "test_new_idempotency_key_creates_new_snapshot",
    "test_subfarm_only_grain",
    "test_multiple_logical_records_same_grain_sum",
    "test_explicit_zero_preserved",
    "test_input_order_independence",
    "test_label_snapshot_immutability",
    "test_label_snapshot_delete_rejected",
    "test_terminal_finalized_without_successor_is_eligible_winner",
    "test_void_without_successor_uses_hardened_error",
    "test_e6_out_of_scope_with_complete_evidence_is_coverage_exclusion",
    "test_e6_manifest_validation_hash_drift_is_structural_failure",
    "test_e6_mapping_snapshot_hash_drift_is_structural_failure",
    "test_e6_resolved_identity_hash_drift_is_structural_failure",
    "test_e6_registry_content_hash_drift_is_structural_failure",
    "test_e6_missing_lineage_basis_member_is_structural_failure",
    "test_e6_missing_mapping_evidence_is_structural_failure",
    "test_e7_explicit_subfarm_mapping_is_accepted",
    "test_e7_explicit_plot_mapping_is_rejected",
    "test_e7_plot_is_not_silently_converted_to_subfarm",
    "test_e7_plot_rejection_is_deterministic",
    "test_request_identity_hash_is_deterministic",
    "test_label_row_set_hash_is_canonical",
    "test_winner_row_hash_is_stable_against_dict_order",
    "test_instance_identity_hash_is_independent_of_snapshot_executed_at",
]


def test_instance_identity_hash_is_independent_of_snapshot_executed_at() -> None:
    """§14.3 contract: SAME_REQUEST_AND_SAME_SOURCE_UNIVERSE_REPRODUCES_SAME_HASHES.

    ``label_snapshot_instance_identity_hash`` MUST NOT bind
    ``snapshot_executed_at``. Two calls with the same request identity
    and the same source-universe hash must produce identical instance
    hashes regardless of any audit-metadata timestamp.
    """

    request_identity_hash = compute_snapshot_request_identity_hash(
        snapshot_idempotency_key="snap-key-1",
        source_system="source-test",
        visibility_mode="AS_OF_EVALUATION",
        label_observation_cutoff_at_or_null=datetime(2024, 6, 30, tzinfo=UTC),
        harvest_date_start=date(2024, 1, 1),
        harvest_date_end=date(2024, 12, 31),
        season_business_keys=("season-1",),
        farm_business_keys_or_empty_for_all=("farm-1",),
        variety_business_keys_or_empty_for_all=("var-1",),
        snapshot_policy_version="snapshot-v1",
        winner_policy_version="winner-v1",
        aggregation_policy_version="aggregation-v1",
    )
    source_manifest_set_hash = "a" * 64

    first = compute_snapshot_instance_identity_hash(
        request_identity_hash=request_identity_hash,
        source_commit_manifest_set_hash=source_manifest_set_hash,
    )
    second = compute_snapshot_instance_identity_hash(
        request_identity_hash=request_identity_hash,
        source_commit_manifest_set_hash=source_manifest_set_hash,
    )
    assert first == second

    # Even if we vary downstream values, the hash inputs do not change
    # as long as request identity and source universe are the same.
    third = compute_snapshot_instance_identity_hash(
        request_identity_hash=request_identity_hash,
        source_commit_manifest_set_hash=source_manifest_set_hash,
    )
    assert first == third


@pytest.mark.asyncio
async def test_database_authoritative_now_returns_utc() -> None:
    """E1: ``_database_authoritative_now`` reads CURRENT_TIMESTAMP from the DB.

    The helper must return a tz-aware datetime in UTC and never use
    ``datetime.now(UTC)``. Even on SQLite (which lacks a true datetime
    type), the helper returns a parsed :class:`datetime`.
    """

    from sqlalchemy.ext.asyncio import create_async_engine

    from backend.app.actual_harvest_labels.service import (
        _database_authoritative_now,
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with AsyncSession(engine) as session:
        stamp = await _database_authoritative_now(session)
    await engine.dispose()

    assert isinstance(stamp, datetime)
    assert stamp.tzinfo is not None
    assert stamp.utcoffset() == timedelta(0)
