from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.actual_harvest_import.models import (
    ActualHarvestImportBatchModel,
    ActualHarvestImportRecordModel,
)
from backend.app.actual_harvest_import.schemas import (
    CanonicalActualHarvestImportBatch,
    CanonicalActualHarvestImportRecord,
)


class ActualHarvestPersistenceError(RuntimeError):
    """Base class for deterministic staging persistence failures."""


class ActualHarvestPersistenceConflict(ActualHarvestPersistenceError):
    """The database rejected a duplicate or inconsistent staging identity."""


class ActualHarvestPersistenceNotFound(ActualHarvestPersistenceError):
    """A required staging parent or record was not found."""


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _batch_to_model(batch: CanonicalActualHarvestImportBatch) -> ActualHarvestImportBatchModel:
    attestation = batch.source_semantics_attestation
    return ActualHarvestImportBatchModel(
        import_id=batch.import_id,
        import_channel=_value(batch.import_channel),
        source_system=batch.source_system,
        source_dataset=batch.source_dataset,
        source_version=batch.source_version,
        external_batch_id=batch.external_batch_id,
        idempotency_key=batch.idempotency_key,
        submitted_at=batch.submitted_at,
        import_received_at=batch.import_received_at,
        ingested_at=batch.ingested_at,
        submitted_by_identity=batch.submitted_by_identity,
        expected_record_count_or_null=batch.expected_record_count_or_null,
        uploaded_record_count=batch.uploaded_record_count,
        sealed_record_count_or_null=batch.sealed_record_count_or_null,
        sealed_at_or_null=batch.sealed_at_or_null,
        sealed_by_identity_or_null=batch.sealed_by_identity_or_null,
        seal_status=_value(batch.seal_status),
        server_raw_payload_hash_or_null=batch.server_raw_payload_hash_or_null,
        canonical_batch_hash_or_null=batch.canonical_batch_hash_or_null,
        seal_manifest_hash_or_null=batch.seal_manifest_hash_or_null,
        source_file_name_or_null=batch.source_file_name_or_null,
        source_file_hash_or_null=batch.source_file_hash_or_null,
        raw_payload_hash=batch.raw_payload_hash,
        schema_version=batch.schema_version,
        mapping_policy_version=batch.mapping_policy_version,
        validation_policy_version=batch.validation_policy_version,
        source_semantics_attestation_version=attestation.attestation_version,
        source_semantics_physical_event=_value(attestation.physical_event),
        source_semantics_quantity_basis=_value(attestation.quantity_basis),
        source_semantics_quantity_unit=_value(attestation.quantity_unit),
        source_semantics_missing_record_semantics=_value(attestation.missing_record_semantics),
        source_semantics_attestation_hash=batch.source_semantics_attestation_hash,
        status=_value(batch.status),
        record_count=batch.record_count,
        valid_record_count=batch.valid_record_count,
        invalid_record_count=batch.invalid_record_count,
        committed_record_count=batch.committed_record_count,
        created_at=batch.created_at,
        validated_at_or_null=batch.validated_at_or_null,
        committed_at_or_null=batch.committed_at_or_null,
    )


def _record_to_model(
    record: CanonicalActualHarvestImportRecord,
    *,
    batch_id: int,
) -> ActualHarvestImportRecordModel:
    return ActualHarvestImportRecordModel(
        batch_id=batch_id,
        external_logical_record_id=record.external_logical_record_id,
        external_revision_id=record.external_revision_id,
        source_system=record.source_system,
        external_batch_id=record.external_batch_id,
        harvest_business_date=record.harvest_business_date,
        farm_code=record.farm_code,
        subfarm_or_plot_code=record.subfarm_or_plot_code,
        variety_code=record.variety_code,
        actual_harvest_quantity_kg=record.actual_harvest_quantity_kg,
        source_recorded_at=record.source_recorded_at,
        source_recorded_at_authority_status=_value(record.source_recorded_at_authority_status),
        source_recorded_at_authority_reference_or_null=(
            record.source_recorded_at_authority_reference_or_null
        ),
        import_received_at=record.import_received_at,
        ingested_at=record.ingested_at,
        revision_number=record.revision_number,
        record_status=_value(record.record_status),
        supersedes_external_revision_id=record.supersedes_external_revision_id,
        season_code=record.season_code,
        farm_timezone=record.farm_timezone,
        revised_at=record.revised_at,
        finalized_at=record.finalized_at,
        source_row_number=record.source_row_number,
        source_sheet_name=record.source_sheet_name,
        source_note=record.source_note,
    )


def _batch_to_schema(model: ActualHarvestImportBatchModel) -> CanonicalActualHarvestImportBatch:
    return CanonicalActualHarvestImportBatch.model_validate(
        {
            "import_id": model.import_id,
            "import_channel": model.import_channel,
            "source_system": model.source_system,
            "source_dataset": model.source_dataset,
            "source_version": model.source_version,
            "external_batch_id": model.external_batch_id,
            "idempotency_key": model.idempotency_key,
            "submitted_at": model.submitted_at,
            "import_received_at": model.import_received_at,
            "ingested_at": model.ingested_at,
            "submitted_by_identity": model.submitted_by_identity,
            "expected_record_count_or_null": model.expected_record_count_or_null,
            "uploaded_record_count": model.uploaded_record_count,
            "sealed_record_count_or_null": model.sealed_record_count_or_null,
            "sealed_at_or_null": model.sealed_at_or_null,
            "sealed_by_identity_or_null": model.sealed_by_identity_or_null,
            "seal_status": model.seal_status,
            "server_raw_payload_hash_or_null": model.server_raw_payload_hash_or_null,
            "canonical_batch_hash_or_null": model.canonical_batch_hash_or_null,
            "seal_manifest_hash_or_null": model.seal_manifest_hash_or_null,
            "source_file_name_or_null": model.source_file_name_or_null,
            "source_file_hash_or_null": model.source_file_hash_or_null,
            "raw_payload_hash": model.raw_payload_hash,
            "schema_version": model.schema_version,
            "mapping_policy_version": model.mapping_policy_version,
            "validation_policy_version": model.validation_policy_version,
            "source_semantics_attestation": {
                "attestation_version": model.source_semantics_attestation_version,
                "physical_event": model.source_semantics_physical_event,
                "quantity_basis": model.source_semantics_quantity_basis,
                "quantity_unit": model.source_semantics_quantity_unit,
                "missing_record_semantics": model.source_semantics_missing_record_semantics,
            },
            "source_semantics_attestation_hash": model.source_semantics_attestation_hash,
            "status": model.status,
            "record_count": model.record_count,
            "valid_record_count": model.valid_record_count,
            "invalid_record_count": model.invalid_record_count,
            "committed_record_count": model.committed_record_count,
            "created_at": model.created_at,
            "validated_at_or_null": model.validated_at_or_null,
            "committed_at_or_null": model.committed_at_or_null,
        }
    )


def _record_to_schema(model: ActualHarvestImportRecordModel) -> CanonicalActualHarvestImportRecord:
    return CanonicalActualHarvestImportRecord.model_validate(
        {
            "external_logical_record_id": model.external_logical_record_id,
            "external_revision_id": model.external_revision_id,
            "source_system": model.source_system,
            "external_batch_id": model.external_batch_id,
            "harvest_business_date": model.harvest_business_date,
            "farm_code": model.farm_code,
            "subfarm_or_plot_code": model.subfarm_or_plot_code,
            "variety_code": model.variety_code,
            "actual_harvest_quantity_kg": model.actual_harvest_quantity_kg,
            "source_recorded_at": model.source_recorded_at,
            "source_recorded_at_authority_status": model.source_recorded_at_authority_status,
            "source_recorded_at_authority_reference_or_null": (
                model.source_recorded_at_authority_reference_or_null
            ),
            "import_received_at": model.import_received_at,
            "ingested_at": model.ingested_at,
            "revision_number": model.revision_number,
            "record_status": model.record_status,
            "supersedes_external_revision_id": model.supersedes_external_revision_id,
            "season_code": model.season_code,
            "farm_timezone": model.farm_timezone,
            "revised_at": model.revised_at,
            "finalized_at": model.finalized_at,
            "source_row_number": model.source_row_number,
            "source_sheet_name": model.source_sheet_name,
            "source_note": model.source_note,
        }
    )


class ActualHarvestImportRepository:
    """Append/read-only repository using a caller-owned SQLAlchemy Session."""

    def create_batch(
        self,
        session: Session,
        batch: CanonicalActualHarvestImportBatch,
    ) -> CanonicalActualHarvestImportBatch:
        model = _batch_to_model(batch)
        session.add(model)
        try:
            session.flush()
        except IntegrityError as exc:
            raise ActualHarvestPersistenceConflict(
                "actual harvest import batch identity conflicts with existing data"
            ) from exc
        return _batch_to_schema(model)

    def get_batch_by_import_id(
        self,
        session: Session,
        import_id: str,
    ) -> CanonicalActualHarvestImportBatch | None:
        model = session.scalar(
            select(ActualHarvestImportBatchModel).where(
                ActualHarvestImportBatchModel.import_id == import_id
            )
        )
        return None if model is None else _batch_to_schema(model)

    def get_batch_by_idempotency_key(
        self,
        session: Session,
        *,
        source_system: str,
        idempotency_key: str,
    ) -> CanonicalActualHarvestImportBatch | None:
        model = session.scalar(
            select(ActualHarvestImportBatchModel).where(
                ActualHarvestImportBatchModel.source_system == source_system,
                ActualHarvestImportBatchModel.idempotency_key == idempotency_key,
            )
        )
        return None if model is None else _batch_to_schema(model)

    def insert_records(
        self,
        session: Session,
        *,
        import_id: str,
        records: Iterable[CanonicalActualHarvestImportRecord],
    ) -> tuple[CanonicalActualHarvestImportRecord, ...]:
        batch_model = session.scalar(
            select(ActualHarvestImportBatchModel).where(
                ActualHarvestImportBatchModel.import_id == import_id
            )
        )
        if batch_model is None:
            raise ActualHarvestPersistenceNotFound(
                f"actual harvest import batch {import_id!r} was not found"
            )
        record_values = tuple(records)
        for record in record_values:
            if (
                record.source_system != batch_model.source_system
                or record.external_batch_id != batch_model.external_batch_id
            ):
                raise ActualHarvestPersistenceConflict(
                    "record source identity does not match its staging batch"
                )
        models = tuple(
            _record_to_model(record, batch_id=batch_model.id) for record in record_values
        )
        session.add_all(models)
        try:
            session.flush()
        except IntegrityError as exc:
            raise ActualHarvestPersistenceConflict(
                "actual harvest import record identity conflicts with existing data"
            ) from exc
        return tuple(_record_to_schema(model) for model in models)

    def list_records_by_import_id(
        self,
        session: Session,
        import_id: str,
    ) -> tuple[CanonicalActualHarvestImportRecord, ...]:
        rows = session.scalars(
            select(ActualHarvestImportRecordModel)
            .join(
                ActualHarvestImportBatchModel,
                ActualHarvestImportRecordModel.batch_id == ActualHarvestImportBatchModel.id,
            )
            .where(ActualHarvestImportBatchModel.import_id == import_id)
            .order_by(
                ActualHarvestImportRecordModel.external_logical_record_id,
                ActualHarvestImportRecordModel.revision_number,
                ActualHarvestImportRecordModel.external_revision_id,
                ActualHarvestImportRecordModel.id,
            )
        ).all()
        return tuple(_record_to_schema(row) for row in rows)

    def get_record_by_revision_key(
        self,
        session: Session,
        *,
        source_system: str,
        external_revision_id: str,
    ) -> CanonicalActualHarvestImportRecord | None:
        model = session.scalar(
            select(ActualHarvestImportRecordModel).where(
                ActualHarvestImportRecordModel.source_system == source_system,
                ActualHarvestImportRecordModel.external_revision_id == external_revision_id,
            )
        )
        return None if model is None else _record_to_schema(model)


__all__ = [
    "ActualHarvestImportRepository",
    "ActualHarvestPersistenceConflict",
    "ActualHarvestPersistenceError",
    "ActualHarvestPersistenceNotFound",
]
