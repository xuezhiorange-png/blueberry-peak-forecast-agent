"""V0.3-S2 Lane A canonical hash helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from hashlib import sha256
from typing import Any

from backend.app.rolling_backtest.canonical import canonical_json_dumps
from backend.app.s2_materialized_dataset.lane_a.schemas import (
    RawImportBatchIdentityInput,
    RawSourceArtifactIdentityInput,
    SourceRowBusinessContent,
    SourceRowLineageInput,
)

S2_CANONICAL_SERIALIZATION_PROFILE = "v0-3-s2-materialized-identity-canonical-v1"
SOURCE_ARTIFACT_IDENTITY_HASH_POLICY_VERSION = "v0-3-s2-source-artifact-identity-hash-v1"
RAW_IMPORT_BATCH_IDENTITY_HASH_POLICY_VERSION = "v0-3-s2-raw-import-batch-identity-hash-v1"
RAW_IMPORT_BATCH_CONTENT_HASH_POLICY_VERSION = "v0-3-s2-raw-import-batch-content-hash-v1"
SOURCE_ROW_IDENTITY_HASH_POLICY_VERSION = "v0-3-s2-source-row-identity-hash-v1"
SOURCE_ROW_CONTENT_HASH_POLICY_VERSION = "v0-3-s2-source-row-content-hash-v1"


def _digest(value: Mapping[str, Any]) -> str:
    return sha256(canonical_json_dumps(dict(value)).encode("utf-8")).hexdigest()


def compute_source_artifact_sha256(artifact_bytes: bytes) -> str:
    return sha256(artifact_bytes).hexdigest()


def source_artifact_identity_payload(
    *,
    artifact_input: RawSourceArtifactIdentityInput,
) -> dict[str, Any]:
    return {
        "canonical_serialization_profile": S2_CANONICAL_SERIALIZATION_PROFILE,
        "policy_version": SOURCE_ARTIFACT_IDENTITY_HASH_POLICY_VERSION,
        "identity_kind": "RAW_SOURCE_ARTIFACT_IDENTITY",
        "stable_inputs": {
            "source_system": artifact_input.source_system,
            "source_dataset": artifact_input.source_dataset,
            "source_version": artifact_input.source_version,
            "source_snapshot_reference": artifact_input.source_snapshot_reference,
            "source_object_identity": artifact_input.source_object_identity,
            "source_artifact_sequence": artifact_input.source_artifact_sequence,
        },
        "version_fields": {
            "source_version": artifact_input.source_version,
            "schema_version": artifact_input.schema_version,
            "mapping_policy_version": artifact_input.mapping_policy_version,
            "source_artifact_identity_version": artifact_input.source_artifact_identity_version,
        },
        "lineage_fields": {
            "source_owner_attestation": artifact_input.source_owner_attestation,
            "cohort_manifest_reference": artifact_input.cohort_manifest_reference,
            "custody_record_reference": artifact_input.custody_record_reference,
            "storage_locator_hash": artifact_input.storage_locator_hash,
        },
    }


def compute_raw_source_artifact_identity_hash(
    *,
    artifact_input: RawSourceArtifactIdentityInput,
) -> str:
    return _digest(source_artifact_identity_payload(artifact_input=artifact_input))


def compute_source_row_content_hash(*, business_content: SourceRowBusinessContent) -> str:
    return _digest(
        {
            "canonical_serialization_profile": S2_CANONICAL_SERIALIZATION_PROFILE,
            "policy_version": SOURCE_ROW_CONTENT_HASH_POLICY_VERSION,
            "business_content": business_content.model_dump(mode="python"),
        }
    )


def source_row_identity_payload(
    *,
    artifact_identity_hash: str,
    row_input: SourceRowLineageInput,
) -> dict[str, Any]:
    return {
        "canonical_serialization_profile": S2_CANONICAL_SERIALIZATION_PROFILE,
        "policy_version": SOURCE_ROW_IDENTITY_HASH_POLICY_VERSION,
        "identity_kind": "SOURCE_ROW_IDENTITY",
        "stable_inputs": {
            "raw_source_artifact_identity": artifact_identity_hash,
            "external_logical_record_id": row_input.external_logical_record_id,
            "external_revision_id": row_input.external_revision_id,
            "revision_number": row_input.revision_number,
            "source_system": row_input.source_system,
        },
        "version_fields": {
            "source_row_identity_version": row_input.source_row_identity_version,
            "schema_version": row_input.schema_version,
            "source_version": row_input.source_version,
        },
        "lineage_fields": {
            "source_column_mapping_snapshot_hash": row_input.source_column_mapping_snapshot_hash,
        },
    }


def compute_source_row_identity_hash(
    *,
    artifact_identity_hash: str,
    row_input: SourceRowLineageInput,
) -> str:
    return _digest(
        source_row_identity_payload(
            artifact_identity_hash=artifact_identity_hash,
            row_input=row_input,
        )
    )


def _source_row_sort_key(row: Mapping[str, object]) -> tuple[str, str, int, str]:
    revision_number = row["revision_number"]
    if not isinstance(revision_number, int):
        raise TypeError("revision_number must be an int")
    return (
        str(row["source_system"]),
        str(row["external_logical_record_id"]),
        revision_number,
        str(row["external_revision_id"]),
    )


def ordered_source_row_content_hashes(
    source_row_identities: Iterable[Mapping[str, object]],
) -> tuple[str, ...]:
    return tuple(
        str(item["content_sha256"])
        for item in sorted(source_row_identities, key=_source_row_sort_key)
    )


def raw_import_batch_content_payload(
    *,
    ordered_row_content_hashes: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "canonical_serialization_profile": S2_CANONICAL_SERIALIZATION_PROFILE,
        "policy_version": RAW_IMPORT_BATCH_CONTENT_HASH_POLICY_VERSION,
        "identity_kind": "RAW_IMPORT_BATCH_CONTENT",
        "ordered_source_row_content_hashes": ordered_row_content_hashes,
    }


def compute_raw_import_batch_content_sha256(
    *,
    ordered_row_content_hashes: tuple[str, ...],
) -> str:
    return _digest(
        raw_import_batch_content_payload(
            ordered_row_content_hashes=ordered_row_content_hashes,
        )
    )


def raw_import_batch_identity_payload(
    *,
    batch_input: RawImportBatchIdentityInput,
    raw_source_artifact_identity_hash: str,
    ordered_row_content_hashes: tuple[str, ...],
    ordered_row_identity_hashes: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "canonical_serialization_profile": S2_CANONICAL_SERIALIZATION_PROFILE,
        "policy_version": RAW_IMPORT_BATCH_IDENTITY_HASH_POLICY_VERSION,
        "identity_kind": "RAW_IMPORT_BATCH_IDENTITY",
        "stable_inputs": {
            "raw_source_artifact_identity": raw_source_artifact_identity_hash,
            "external_batch_id": batch_input.external_batch_id,
            "source_system": batch_input.source_system,
            "source_dataset": batch_input.source_dataset,
            "raw_payload_hash": batch_input.raw_payload_hash,
        },
        "version_fields": {
            "import_policy_version": batch_input.import_policy_version,
            "schema_version": batch_input.schema_version,
            "mapping_policy_version": batch_input.mapping_policy_version,
            "validation_policy_version": batch_input.validation_policy_version,
        },
        "lineage_fields": {
            "raw_source_artifact_identity": raw_source_artifact_identity_hash,
            "source_cohort_id": batch_input.source_cohort_id,
            "source_row_identity_set": ordered_row_identity_hashes,
            "import_request_identity": batch_input.import_request_identity,
        },
        "ordered_source_row_content_hashes": ordered_row_content_hashes,
    }


def compute_raw_import_batch_identity_hash(
    *,
    batch_input: RawImportBatchIdentityInput,
    raw_source_artifact_identity_hash: str,
    ordered_row_content_hashes: tuple[str, ...],
    ordered_row_identity_hashes: tuple[str, ...],
) -> str:
    return _digest(
        raw_import_batch_identity_payload(
            batch_input=batch_input,
            raw_source_artifact_identity_hash=raw_source_artifact_identity_hash,
            ordered_row_content_hashes=ordered_row_content_hashes,
            ordered_row_identity_hashes=ordered_row_identity_hashes,
        )
    )
