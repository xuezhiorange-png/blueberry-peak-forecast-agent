from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.actual_harvest_import.api_errors import (
    ActualHarvestApiError,
    ActualHarvestApiErrorCode,
)
from backend.app.actual_harvest_import.api_schemas import (
    ActualHarvestApiCreateImportRequest,
    ActualHarvestApiRecordInput,
)
from backend.app.actual_harvest_import.canonical_hashes import (
    compute_canonical_batch_hash,
    compute_canonical_record_hash,
    compute_create_payload_hash,
    compute_seal_manifest_hash,
    compute_server_raw_payload_hash,
)
from backend.app.actual_harvest_import.enums import (
    ActualHarvestBatchSealStatus,
    ActualHarvestImportBatchStatus,
)
from backend.app.actual_harvest_import.models import (
    ActualHarvestImportBatchModel,
    ActualHarvestImportRecordModel,
)
from backend.app.actual_harvest_import.persistence import (
    ActualHarvestPersistenceConflict,
    _batch_to_schema,
    _record_to_model,
    _record_to_schema,
)
from backend.app.actual_harvest_import.schemas import (
    ActualHarvestImportBatchInput,
    CanonicalActualHarvestImportBatch,
    CanonicalActualHarvestImportRecord,
)


def _api_error(
    code: ActualHarvestApiErrorCode,
    message: str,
    status_code: int,
    *,
    details: dict[str, Any] | None = None,
) -> ActualHarvestApiError:
    return ActualHarvestApiError(code, message, status_code=status_code, details=details)


def _batch_input(batch: CanonicalActualHarvestImportBatch) -> ActualHarvestImportBatchInput:
    return ActualHarvestImportBatchInput.model_validate(
        {
            "import_channel": batch.import_channel,
            "source_system": batch.source_system,
            "source_dataset": batch.source_dataset,
            "source_version": batch.source_version,
            "external_batch_id": batch.external_batch_id,
            "idempotency_key": batch.idempotency_key,
            "submitted_at": batch.submitted_at,
            "submitted_by_identity": batch.submitted_by_identity,
            "expected_record_count_or_null": batch.expected_record_count_or_null,
            "source_file_name_or_null": batch.source_file_name_or_null,
            "source_file_hash_or_null": batch.source_file_hash_or_null,
            "raw_payload_hash": batch.raw_payload_hash,
            "schema_version": batch.schema_version,
            "mapping_policy_version": batch.mapping_policy_version,
            "validation_policy_version": batch.validation_policy_version,
            "source_semantics_attestation": batch.source_semantics_attestation,
            "source_semantics_attestation_hash": batch.source_semantics_attestation_hash,
        }
    )


def _lock_batch(session: Session, import_id: str) -> ActualHarvestImportBatchModel:
    batch = session.scalar(
        select(ActualHarvestImportBatchModel)
        .where(ActualHarvestImportBatchModel.import_id == import_id)
        .with_for_update()
    )
    if batch is None:
        raise _api_error(
            ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_FOUND,
            "actual-harvest import batch was not found",
            404,
        )
    return batch


def _all_records(session: Session, batch_id: int) -> tuple[CanonicalActualHarvestImportRecord, ...]:
    rows = session.scalars(
        select(ActualHarvestImportRecordModel)
        .where(ActualHarvestImportRecordModel.batch_id == batch_id)
        .order_by(
            ActualHarvestImportRecordModel.source_system,
            ActualHarvestImportRecordModel.external_logical_record_id,
            ActualHarvestImportRecordModel.revision_number,
            ActualHarvestImportRecordModel.external_revision_id,
            ActualHarvestImportRecordModel.id,
        )
    ).all()
    return tuple(_record_to_schema(row) for row in rows)


def _batch_payload_matches(
    existing: CanonicalActualHarvestImportBatch,
    request: ActualHarvestApiCreateImportRequest,
) -> bool:
    return compute_create_payload_hash(_batch_input(existing)) == compute_create_payload_hash(
        request
    )


def create_batch(
    session: Session,
    request: ActualHarvestApiCreateImportRequest,
    *,
    import_id: str,
    now: datetime,
) -> tuple[CanonicalActualHarvestImportBatch, bool]:
    batch = CanonicalActualHarvestImportBatch.model_validate(
        {
            **request.model_dump(mode="python"),
            "import_id": import_id,
            "import_received_at": now,
            "ingested_at": now,
            "uploaded_record_count": 0,
            "sealed_record_count_or_null": None,
            "sealed_at_or_null": None,
            "sealed_by_identity_or_null": None,
            "seal_status": ActualHarvestBatchSealStatus.UNSEALED,
            "server_raw_payload_hash_or_null": None,
            "canonical_batch_hash_or_null": None,
            "seal_manifest_hash_or_null": None,
            "status": ActualHarvestImportBatchStatus.UPLOADING,
            "record_count": 0,
            "valid_record_count": 0,
            "invalid_record_count": 0,
            "committed_record_count": 0,
            "created_at": now,
            "validated_at_or_null": None,
            "committed_at_or_null": None,
        }
    )
    try:
        with session.begin_nested():
            session.add(
                ActualHarvestImportBatchModel(
                    **{
                        key: value
                        for key, value in {
                            **batch.model_dump(mode="python"),
                            "import_channel": batch.import_channel.value,
                            "seal_status": batch.seal_status.value,
                            "status": batch.status.value,
                            "source_semantics_attestation_version": (
                                batch.source_semantics_attestation.attestation_version
                            ),
                            "source_semantics_physical_event": (
                                batch.source_semantics_attestation.physical_event.value
                            ),
                            "source_semantics_quantity_basis": (
                                batch.source_semantics_attestation.quantity_basis.value
                            ),
                            "source_semantics_quantity_unit": (
                                batch.source_semantics_attestation.quantity_unit.value
                            ),
                            "source_semantics_missing_record_semantics": (
                                batch.source_semantics_attestation.missing_record_semantics.value
                            ),
                            "source_semantics_attestation": None,
                        }.items()
                        if key != "source_semantics_attestation"
                    }
                )
            )
            session.flush()
    except IntegrityError as exc:
        existing = session.scalar(
            select(ActualHarvestImportBatchModel).where(
                ActualHarvestImportBatchModel.source_system == request.source_system,
                ActualHarvestImportBatchModel.idempotency_key == request.idempotency_key,
            )
        )
        if existing is not None:
            existing_schema = _batch_to_schema(existing)
            if _batch_payload_matches(existing_schema, request):
                return existing_schema, True
            raise _api_error(
                ActualHarvestApiErrorCode.IDEMPOTENCY_KEY_CONFLICT,
                "idempotency key already identifies a different import",
                409,
            ) from exc
        raise _api_error(
            ActualHarvestApiErrorCode.EXTERNAL_BATCH_ID_CONFLICT,
            "external batch identity already exists",
            409,
        ) from exc
    model = session.scalar(
        select(ActualHarvestImportBatchModel).where(
            ActualHarvestImportBatchModel.import_id == import_id
        )
    )
    if model is None:
        raise _api_error(
            ActualHarvestApiErrorCode.API_INTEGRITY_ERROR,
            "created import could not be reloaded",
            500,
        )
    return _batch_to_schema(model), False


def get_batch(session: Session, import_id: str) -> CanonicalActualHarvestImportBatch | None:
    model = session.scalar(
        select(ActualHarvestImportBatchModel).where(
            ActualHarvestImportBatchModel.import_id == import_id
        )
    )
    return None if model is None else _batch_to_schema(model)


def append_records(
    session: Session,
    *,
    import_id: str,
    records: tuple[ActualHarvestApiRecordInput, ...],
    now: datetime,
) -> tuple[CanonicalActualHarvestImportBatch, tuple[CanonicalActualHarvestImportRecord, ...], bool]:
    batch_model = _lock_batch(session, import_id)
    if batch_model.status == ActualHarvestImportBatchStatus.CANCELLED.value:
        raise _api_error(
            ActualHarvestApiErrorCode.IMPORT_BATCH_CANCELLED,
            "import is cancelled",
            409,
        )
    if batch_model.status == ActualHarvestImportBatchStatus.SEALED.value:
        raise _api_error(
            ActualHarvestApiErrorCode.BATCH_MUTATION_AFTER_SEAL,
            "sealed imports cannot be mutated",
            409,
        )
    if (
        batch_model.status != ActualHarvestImportBatchStatus.UPLOADING.value
        or batch_model.seal_status != ActualHarvestBatchSealStatus.UNSEALED.value
    ):
        raise _api_error(
            ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_UPLOADING,
            "import is not accepting records",
            409,
        )

    if any(
        record.source_system != batch_model.source_system
        or record.external_batch_id != batch_model.external_batch_id
        for record in records
    ):
        raise _api_error(
            ActualHarvestApiErrorCode.REVISION_IDENTITY_CONFLICT,
            "record source identity does not match import",
            409,
        )

    revision_keys = [(record.source_system, record.external_revision_id) for record in records]
    if len(set(revision_keys)) != len(revision_keys):
        raise _api_error(
            ActualHarvestApiErrorCode.REVISION_IDENTITY_CONFLICT,
            "append page contains duplicate revision identities",
            409,
        )
    existing_rows = session.scalars(
        select(ActualHarvestImportRecordModel).where(
            or_(
                *(
                    (ActualHarvestImportRecordModel.source_system == source_system)
                    & (ActualHarvestImportRecordModel.external_revision_id == revision_id)
                    for source_system, revision_id in revision_keys
                )
            )
        )
    ).all()
    existing_by_key = {(row.source_system, row.external_revision_id): row for row in existing_rows}
    if existing_by_key:
        if any(row.batch_id != batch_model.id for row in existing_by_key.values()):
            raise _api_error(
                ActualHarvestApiErrorCode.REVISION_IDENTITY_CONFLICT,
                "revision identity already belongs to another import",
                409,
            )
        if len(existing_by_key) != len(records):
            raise _api_error(
                ActualHarvestApiErrorCode.REVISION_IDENTITY_CONFLICT,
                "append page partially overlaps existing revisions",
                409,
            )
        persisted = tuple(_record_to_schema(existing_by_key[key]) for key in revision_keys)
        if all(
            compute_canonical_record_hash(left) == compute_canonical_record_hash(right)
            for left, right in zip(persisted, records, strict=True)
        ):
            return _batch_to_schema(batch_model), persisted, True
        raise _api_error(
            ActualHarvestApiErrorCode.REVISION_IDENTITY_CONFLICT,
            "revision identity already identifies different content",
            409,
        )

    canonical_records = tuple(
        CanonicalActualHarvestImportRecord.model_validate(
            {
                **record.model_dump(mode="python"),
                "import_received_at": now,
                "ingested_at": now,
                "source_row_number": None,
                "source_sheet_name": None,
            }
        )
        for record in records
    )
    try:
        models = tuple(
            _record_to_model(record, batch_id=batch_model.id) for record in canonical_records
        )
        session.add_all(models)
        session.flush()
    except (IntegrityError, ActualHarvestPersistenceConflict) as exc:
        raise _api_error(
            ActualHarvestApiErrorCode.REVISION_IDENTITY_CONFLICT,
            "record identity conflicts with existing data",
            409,
        ) from exc
    batch_model.uploaded_record_count += len(models)
    batch_model.record_count += len(models)
    batch_model.valid_record_count = 0
    batch_model.invalid_record_count = 0
    batch_model.committed_record_count = 0
    session.flush()
    return _batch_to_schema(batch_model), tuple(_record_to_schema(model) for model in models), False


def seal_batch(
    session: Session,
    *,
    import_id: str,
    sealed_by_identity: str,
    now: datetime,
) -> CanonicalActualHarvestImportBatch:
    batch_model = _lock_batch(session, import_id)
    if batch_model.status == ActualHarvestImportBatchStatus.CANCELLED.value:
        raise _api_error(
            ActualHarvestApiErrorCode.IMPORT_BATCH_CANCELLED,
            "import is cancelled",
            409,
        )
    if batch_model.status == ActualHarvestImportBatchStatus.SEALED.value:
        if batch_model.sealed_by_identity_or_null != sealed_by_identity:
            raise _api_error(
                ActualHarvestApiErrorCode.BATCH_SEAL_HASH_CONFLICT,
                "sealed import was finalized by a different actor",
                409,
            )
        return _batch_to_schema(batch_model)
    if (
        batch_model.status != ActualHarvestImportBatchStatus.UPLOADING.value
        or batch_model.seal_status != ActualHarvestBatchSealStatus.UNSEALED.value
    ):
        raise _api_error(
            ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_UPLOADING,
            "only an unsealed uploading import can be sealed",
            409,
        )
    batch = _batch_to_schema(batch_model)
    records = _all_records(session, batch_model.id)
    if batch.expected_record_count_or_null is not None and (
        len(records) != batch.expected_record_count_or_null
    ):
        raise _api_error(
            ActualHarvestApiErrorCode.BATCH_RECORD_COUNT_MISMATCH,
            "uploaded record count does not match expected count",
            409,
            details={"expected_record_count": batch.expected_record_count_or_null},
        )
    raw_hash = compute_server_raw_payload_hash(_batch_input(batch), records)
    canonical_hash = compute_canonical_batch_hash(batch, records)
    batch_model.server_raw_payload_hash_or_null = raw_hash
    batch_model.canonical_batch_hash_or_null = canonical_hash
    manifest_input = batch.model_copy(
        update={
            "server_raw_payload_hash_or_null": raw_hash,
            "canonical_batch_hash_or_null": canonical_hash,
            "sealed_record_count_or_null": len(records),
            "sealed_at_or_null": now,
            "sealed_by_identity_or_null": sealed_by_identity,
            "seal_status": ActualHarvestBatchSealStatus.SEALED,
            "seal_manifest_hash_or_null": "0" * 64,
        }
    )
    seal_manifest_hash = compute_seal_manifest_hash(manifest_input, records)
    batch_model.sealed_record_count_or_null = len(records)
    batch_model.sealed_at_or_null = now
    batch_model.sealed_by_identity_or_null = sealed_by_identity
    batch_model.seal_manifest_hash_or_null = seal_manifest_hash
    batch_model.seal_status = ActualHarvestBatchSealStatus.SEALED.value
    batch_model.status = ActualHarvestImportBatchStatus.SEALED.value
    session.flush()
    return _batch_to_schema(batch_model)


def cancel_batch(
    session: Session,
    *,
    import_id: str,
    now: datetime,
) -> CanonicalActualHarvestImportBatch:
    del now
    batch_model = _lock_batch(session, import_id)
    allowed_statuses = {
        ActualHarvestImportBatchStatus.RECEIVED.value,
        ActualHarvestImportBatchStatus.UPLOADING.value,
        ActualHarvestImportBatchStatus.SEALED.value,
        ActualHarvestImportBatchStatus.CANCELLED.value,
    }
    if batch_model.status not in allowed_statuses:
        raise _api_error(
            ActualHarvestApiErrorCode.IMPORT_BATCH_CANNOT_CANCEL,
            "import is in a state that cannot be cancelled",
            409,
        )
    if batch_model.status != ActualHarvestImportBatchStatus.CANCELLED.value:
        batch_model.status = ActualHarvestImportBatchStatus.CANCELLED.value
        session.flush()
    return _batch_to_schema(batch_model)


def list_records_page(
    session: Session,
    *,
    import_id: str,
    page_size: int,
    after: tuple[str, str, int, str] | None,
) -> tuple[CanonicalActualHarvestImportRecord, ...]:
    batch = session.scalar(
        select(ActualHarvestImportBatchModel).where(
            ActualHarvestImportBatchModel.import_id == import_id
        )
    )
    if batch is None:
        raise _api_error(ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_FOUND, "import not found", 404)
    query = select(ActualHarvestImportRecordModel).where(
        ActualHarvestImportRecordModel.batch_id == batch.id
    )
    order_columns = (
        ActualHarvestImportRecordModel.source_system,
        ActualHarvestImportRecordModel.external_logical_record_id,
        ActualHarvestImportRecordModel.revision_number,
        ActualHarvestImportRecordModel.external_revision_id,
        ActualHarvestImportRecordModel.id,
    )
    query = query.order_by(*order_columns)
    if after is not None:
        source_system, logical_id, revision_number, revision_id = after
        query = query.where(
            or_(
                ActualHarvestImportRecordModel.source_system > source_system,
                (ActualHarvestImportRecordModel.source_system == source_system)
                & (ActualHarvestImportRecordModel.external_logical_record_id > logical_id),
                (ActualHarvestImportRecordModel.source_system == source_system)
                & (ActualHarvestImportRecordModel.external_logical_record_id == logical_id)
                & (ActualHarvestImportRecordModel.revision_number > revision_number),
                (ActualHarvestImportRecordModel.source_system == source_system)
                & (ActualHarvestImportRecordModel.external_logical_record_id == logical_id)
                & (ActualHarvestImportRecordModel.revision_number == revision_number)
                & (ActualHarvestImportRecordModel.external_revision_id > revision_id),
            )
        )
    rows = session.scalars(query.limit(page_size + 1)).all()
    return tuple(_record_to_schema(row) for row in rows)


__all__ = [
    "append_records",
    "cancel_batch",
    "create_batch",
    "get_batch",
    "list_records_page",
    "seal_batch",
]
