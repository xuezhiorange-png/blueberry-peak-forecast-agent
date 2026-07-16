from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.actual_harvest_import.enums import (
    ActualHarvestBatchSealStatus,
    ActualHarvestImportBatchStatus,
    ActualHarvestImportChannel,
    ActualHarvestMissingRecordSemantics,
    ActualHarvestPhysicalEvent,
    ActualHarvestQuantityBasis,
    ActualHarvestQuantityUnit,
    ActualHarvestRecordStatus,
    SourceRecordedAtAuthorityStatus,
)
from backend.app.actual_harvest_import.models import (
    ActualHarvestImportBatchModel,
    ActualHarvestImportRecordModel,
)
from backend.app.actual_harvest_import.persistence import (
    ActualHarvestImportRepository,
    ActualHarvestPersistenceConflict,
)
from backend.app.actual_harvest_import.schemas import (
    ActualHarvestSourceSemanticsAttestation,
    CanonicalActualHarvestImportBatch,
    CanonicalActualHarvestImportRecord,
)
from backend.app.db.base import Base

pytestmark = [pytest.mark.unit, pytest.mark.contract]


_NOW = datetime(2026, 7, 15, 8, 30, tzinfo=UTC)


def _batch(*, import_id: str = "opaque-import-1") -> CanonicalActualHarvestImportBatch:
    return CanonicalActualHarvestImportBatch(
        import_id=import_id,
        import_channel=ActualHarvestImportChannel.CSV,
        source_system="farm-system",
        source_dataset="actual-harvest",
        source_version="2026-07",
        external_batch_id="batch-1",
        idempotency_key="idempotency-1",
        submitted_at=_NOW,
        import_received_at=_NOW,
        ingested_at=_NOW,
        submitted_by_identity="operator-1",
        expected_record_count_or_null=2,
        uploaded_record_count=2,
        sealed_record_count_or_null=None,
        sealed_at_or_null=None,
        sealed_by_identity_or_null=None,
        seal_status=ActualHarvestBatchSealStatus.UNSEALED,
        server_raw_payload_hash_or_null=None,
        canonical_batch_hash_or_null=None,
        seal_manifest_hash_or_null=None,
        source_file_name_or_null="harvest.csv",
        source_file_hash_or_null="c" * 64,
        raw_payload_hash="b" * 64,
        schema_version="actual-harvest-v1",
        mapping_policy_version="mapping-v1",
        validation_policy_version="validation-v1",
        source_semantics_attestation=ActualHarvestSourceSemanticsAttestation(
            attestation_version="attestation-v1",
            physical_event=ActualHarvestPhysicalEvent.FARM_PICK,
            quantity_basis=ActualHarvestQuantityBasis.OBSERVED_WEIGHT,
            quantity_unit=ActualHarvestQuantityUnit.KG,
            missing_record_semantics=ActualHarvestMissingRecordSemantics.UNKNOWN_NOT_ZERO,
        ),
        source_semantics_attestation_hash="a" * 64,
        status=ActualHarvestImportBatchStatus.RECEIVED,
        record_count=0,
        valid_record_count=0,
        invalid_record_count=0,
        committed_record_count=0,
        created_at=_NOW,
        validated_at_or_null=None,
        committed_at_or_null=None,
    )


def _record(
    *,
    logical_id: str = "logical-1",
    revision_id: str = "revision-1",
    revision_number: int = 1,
    source_row_number: int | None = 1,
    quantity: Decimal = Decimal("0.000001"),
) -> CanonicalActualHarvestImportRecord:
    return CanonicalActualHarvestImportRecord(
        external_logical_record_id=logical_id,
        external_revision_id=revision_id,
        source_system="farm-system",
        external_batch_id="batch-1",
        harvest_business_date=date(2026, 7, 14),
        farm_code="farm-1",
        subfarm_or_plot_code="plot-1",
        variety_code="variety-1",
        actual_harvest_quantity_kg=quantity,
        source_recorded_at=_NOW,
        source_recorded_at_authority_status=SourceRecordedAtAuthorityStatus.TRUSTED_SOURCE_TIMESTAMP,
        source_recorded_at_authority_reference_or_null="source-row-1",
        import_received_at=_NOW,
        ingested_at=_NOW,
        revision_number=revision_number,
        record_status=ActualHarvestRecordStatus.ACTIVE,
        supersedes_external_revision_id=None if revision_number == 1 else "revision-1",
        season_code="2026",
        farm_timezone="Asia/Shanghai",
        revised_at=_NOW,
        finalized_at=None,
        source_row_number=source_row_number,
        source_sheet_name="July",
        source_note="observed at farm",
    )


@pytest.fixture
def session_factory() -> sessionmaker[Session]:
    engine = sa.create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(
        engine,
        tables=[
            ActualHarvestImportBatchModel.__table__,
            ActualHarvestImportRecordModel.__table__,
        ],
    )
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_batch_and_record_round_trip_is_complete_and_exact(
    session_factory: sessionmaker[Session],
) -> None:
    repository = ActualHarvestImportRepository()
    with session_factory() as session:
        expected_batch = _batch()
        expected_record = _record()
        created_batch = repository.create_batch(session, expected_batch)
        created_records = repository.insert_records(
            session,
            import_id=expected_batch.import_id,
            records=[expected_record],
        )

        assert created_batch == expected_batch
        assert created_records == (expected_record,)
        assert repository.get_batch_by_import_id(session, "opaque-import-1") == expected_batch
        assert (
            repository.get_batch_by_idempotency_key(
                session,
                source_system="farm-system",
                idempotency_key="idempotency-1",
            )
            == expected_batch
        )
        assert repository.list_records_by_import_id(session, "opaque-import-1") == (
            expected_record,
        )
        assert (
            repository.get_record_by_revision_key(
                session,
                source_system="farm-system",
                external_revision_id="revision-1",
            )
            == expected_record
        )
        assert created_records[0].actual_harvest_quantity_kg == Decimal("0.000001")
        assert created_records[0].source_recorded_at == _NOW


def test_repository_is_append_read_only_and_does_not_own_transaction(
    session_factory: sessionmaker[Session],
) -> None:
    repository = ActualHarvestImportRepository()
    commit_count = 0
    rollback_count = 0

    def _after_commit(_: Session) -> None:
        nonlocal commit_count
        commit_count += 1

    def _after_rollback(_: Session) -> None:
        nonlocal rollback_count
        rollback_count += 1

    event.listen(Session, "after_commit", _after_commit)
    event.listen(Session, "after_rollback", _after_rollback)
    try:
        with session_factory() as session:
            repository.create_batch(session, _batch())
            assert (
                session.scalar(
                    sa.select(sa.func.count()).select_from(ActualHarvestImportBatchModel)
                )
                == 1
            )
            assert commit_count == 0
            assert not hasattr(repository, "update_batch")
            assert not hasattr(repository, "delete_batch")
            session.rollback()
            assert rollback_count == 1
            assert (
                session.scalar(
                    sa.select(sa.func.count()).select_from(ActualHarvestImportBatchModel)
                )
                == 0
            )
    finally:
        event.remove(Session, "after_commit", _after_commit)
        event.remove(Session, "after_rollback", _after_rollback)


def test_records_are_deterministically_ordered(
    session_factory: sessionmaker[Session],
) -> None:
    repository = ActualHarvestImportRepository()
    with session_factory() as session:
        repository.create_batch(session, _batch())
        repository.insert_records(
            session,
            import_id="opaque-import-1",
            records=[
                _record(logical_id="logical-2", revision_id="revision-2", source_row_number=2),
                _record(logical_id="logical-1", revision_id="revision-1", source_row_number=1),
            ],
        )
        records = repository.list_records_by_import_id(session, "opaque-import-1")
        assert [record.external_logical_record_id for record in records] == [
            "logical-1",
            "logical-2",
        ]


def test_database_constraints_reject_invalid_enum_hash_and_quantity(
    session_factory: sessionmaker[Session],
) -> None:
    repository = ActualHarvestImportRepository()
    with session_factory() as session:
        with pytest.raises(IntegrityError):
            session.execute(
                sa.insert(ActualHarvestImportBatchModel).values(
                    **{
                        "import_id": "invalid-enum",
                        "import_channel": "INVALID",
                        "source_system": "farm-system",
                        "source_dataset": "actual-harvest",
                        "source_version": "2026-07",
                        "external_batch_id": "batch-invalid",
                        "idempotency_key": "idempotency-invalid",
                        "submitted_at": _NOW,
                        "import_received_at": _NOW,
                        "ingested_at": _NOW,
                        "submitted_by_identity": "operator-1",
                        "uploaded_record_count": 0,
                        "seal_status": "UNSEALED",
                        "raw_payload_hash": "b" * 64,
                        "schema_version": "actual-harvest-v1",
                        "mapping_policy_version": "mapping-v1",
                        "validation_policy_version": "validation-v1",
                        "source_semantics_attestation_version": "attestation-v1",
                        "source_semantics_physical_event": "FARM_PICK",
                        "source_semantics_quantity_basis": "OBSERVED_WEIGHT",
                        "source_semantics_quantity_unit": "KG",
                        "source_semantics_missing_record_semantics": "UNKNOWN_NOT_ZERO",
                        "source_semantics_attestation_hash": "a" * 64,
                        "status": "RECEIVED",
                        "record_count": 0,
                        "valid_record_count": 0,
                        "invalid_record_count": 0,
                        "committed_record_count": 0,
                        "created_at": _NOW,
                    }
                )
            )
        session.rollback()

        repository.create_batch(session, _batch())
        bad_record = _record(quantity=Decimal("1.000000"))
        session.add(
            ActualHarvestImportRecordModel(
                **{
                    "batch_id": 1,
                    **bad_record.model_dump(),
                    "actual_harvest_quantity_kg": Decimal("-1"),
                    "source_recorded_at_authority_status": "MISSING",
                    "record_status": "ACTIVE",
                }
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()


def test_staging_tables_have_no_json_columns_and_have_composite_fk() -> None:
    batch_columns = ActualHarvestImportBatchModel.__table__.columns
    record_columns = ActualHarvestImportRecordModel.__table__.columns
    assert not any(isinstance(column.type, sa.JSON) for column in batch_columns)
    assert not any(isinstance(column.type, sa.JSON) for column in record_columns)
    assert isinstance(record_columns.actual_harvest_quantity_kg.type, sa.Numeric)
    assert record_columns.actual_harvest_quantity_kg.type.precision == 18
    assert record_columns.actual_harvest_quantity_kg.type.scale == 6
    foreign_key = next(iter(ActualHarvestImportRecordModel.__table__.foreign_key_constraints))
    assert foreign_key.ondelete == "RESTRICT"
    assert [column.name for column in foreign_key.columns] == [
        "batch_id",
        "source_system",
        "external_batch_id",
    ]


def test_mismatched_record_parent_identity_fails_closed(
    session_factory: sessionmaker[Session],
) -> None:
    repository = ActualHarvestImportRepository()
    with session_factory() as session:
        repository.create_batch(session, _batch())
        mismatched = _record().model_copy(update={"source_system": "other-system"})
        with pytest.raises(ActualHarvestPersistenceConflict):
            repository.insert_records(
                session,
                import_id="opaque-import-1",
                records=[mismatched],
            )
