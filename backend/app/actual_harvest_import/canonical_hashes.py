from __future__ import annotations

from collections.abc import Iterable, Mapping
from hashlib import sha256
from typing import Any

from pydantic import BaseModel

from backend.app.actual_harvest_import.api_schemas import ActualHarvestApiRecordInput
from backend.app.actual_harvest_import.schemas import (
    ActualHarvestImportBatchInput,
    CanonicalActualHarvestImportBatch,
    CanonicalActualHarvestImportRecord,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps

API_TRANSPORT_HASH_POLICY_VERSION = "actual-harvest-api-transport-hash-v1"
CANONICAL_BATCH_HASH_POLICY_VERSION = "actual-harvest-canonical-batch-hash-v1"
SEAL_MANIFEST_POLICY_VERSION = "actual-harvest-seal-manifest-v1"


def _digest(value: object) -> str:
    return sha256(canonical_json_dumps(value).encode("utf-8")).hexdigest()


def _model_value(model: BaseModel, *, exclude: set[str] | None = None) -> dict[str, Any]:
    value = model.model_dump(mode="python", exclude=exclude or set())
    if not isinstance(value, dict):
        raise TypeError("canonical payload model must produce an object")
    return value


def canonical_record_payload(
    record: ActualHarvestApiRecordInput | CanonicalActualHarvestImportRecord,
) -> dict[str, Any]:
    return _model_value(
        record,
        exclude={"import_received_at", "ingested_at", "source_row_number", "source_sheet_name"},
    )


def ordered_records(
    records: Iterable[CanonicalActualHarvestImportRecord],
) -> tuple[CanonicalActualHarvestImportRecord, ...]:
    return tuple(
        sorted(
            records,
            key=lambda record: (
                record.source_system,
                record.external_logical_record_id,
                record.revision_number,
                record.external_revision_id,
            ),
        )
    )


def compute_canonical_record_hash(
    record: ActualHarvestApiRecordInput | CanonicalActualHarvestImportRecord,
) -> str:
    return _digest(
        {
            "policy_version": API_TRANSPORT_HASH_POLICY_VERSION,
            "record": canonical_record_payload(record),
        }
    )


def canonical_create_payload(request: ActualHarvestImportBatchInput) -> dict[str, Any]:
    return _model_value(request)


def compute_create_payload_hash(request: ActualHarvestImportBatchInput) -> str:
    return _digest(
        {
            "policy_version": API_TRANSPORT_HASH_POLICY_VERSION,
            "create": canonical_create_payload(request),
        }
    )


def compute_server_raw_payload_hash(
    request: ActualHarvestImportBatchInput,
    records: Iterable[CanonicalActualHarvestImportRecord],
) -> str:
    ordered = ordered_records(records)
    return _digest(
        {
            "policy_version": API_TRANSPORT_HASH_POLICY_VERSION,
            "create": canonical_create_payload(request),
            "records": [canonical_record_payload(record) for record in ordered],
        }
    )


def _batch_business_payload(
    batch: CanonicalActualHarvestImportBatch,
    records: tuple[CanonicalActualHarvestImportRecord, ...],
) -> Mapping[str, Any]:
    return {
        "policy_version": CANONICAL_BATCH_HASH_POLICY_VERSION,
        "source_system": batch.source_system,
        "source_dataset": batch.source_dataset,
        "source_version": batch.source_version,
        "external_batch_id": batch.external_batch_id,
        "raw_payload_hash": batch.raw_payload_hash,
        "source_semantics_attestation": batch.source_semantics_attestation.model_dump(
            mode="python"
        ),
        "source_semantics_attestation_hash": batch.source_semantics_attestation_hash,
        "schema_version": batch.schema_version,
        "mapping_policy_version": batch.mapping_policy_version,
        "validation_policy_version": batch.validation_policy_version,
        "record_hashes": [compute_canonical_record_hash(record) for record in records],
        "record_count": len(records),
    }


def compute_canonical_batch_hash(
    batch: CanonicalActualHarvestImportBatch,
    records: Iterable[CanonicalActualHarvestImportRecord],
) -> str:
    ordered = ordered_records(records)
    return _digest(_batch_business_payload(batch, ordered))


def compute_seal_manifest_hash(
    batch: CanonicalActualHarvestImportBatch,
    records: Iterable[CanonicalActualHarvestImportRecord],
) -> str:
    ordered = ordered_records(records)
    return _digest(
        {
            "policy_version": SEAL_MANIFEST_POLICY_VERSION,
            "import_id": batch.import_id,
            "source_system": batch.source_system,
            "external_batch_id": batch.external_batch_id,
            "uploaded_record_count": batch.uploaded_record_count,
            "sealed_record_count": len(ordered),
            "expected_record_count_or_null": batch.expected_record_count_or_null,
            "server_raw_payload_hash": batch.server_raw_payload_hash_or_null,
            "canonical_batch_hash": batch.canonical_batch_hash_or_null,
            "raw_payload_hash": batch.raw_payload_hash,
            "source_semantics_attestation_hash": batch.source_semantics_attestation_hash,
            "schema_version": batch.schema_version,
            "mapping_policy_version": batch.mapping_policy_version,
            "validation_policy_version": batch.validation_policy_version,
            "record_hashes": [compute_canonical_record_hash(record) for record in ordered],
        }
    )


__all__ = [
    "API_TRANSPORT_HASH_POLICY_VERSION",
    "CANONICAL_BATCH_HASH_POLICY_VERSION",
    "SEAL_MANIFEST_POLICY_VERSION",
    "canonical_create_payload",
    "canonical_record_payload",
    "compute_canonical_batch_hash",
    "compute_canonical_record_hash",
    "compute_create_payload_hash",
    "compute_seal_manifest_hash",
    "compute_server_raw_payload_hash",
    "ordered_records",
]
