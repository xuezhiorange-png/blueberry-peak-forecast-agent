"""V0.3-S2 Lane B identity and content hash helpers (contract §4.4–§4.8)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal
from hashlib import sha256
from typing import Any

from backend.app.rolling_backtest.canonical import canonical_json_dumps, canonical_json_value

S2_CANONICAL_SERIALIZATION_PROFILE = "v0-3-s2-materialized-identity-canonical-v1"

SYNTHETIC_RAW_SOURCE_ARTIFACT_IDENTITY_POLICY_VERSION = (
    "v0-3-s2-synthetic-raw-source-artifact-identity-v1"
)
SYNTHETIC_RAW_IMPORT_BATCH_IDENTITY_POLICY_VERSION = (
    "v0-3-s2-synthetic-raw-import-batch-identity-v1"
)
SYNTHETIC_SOURCE_ROW_IDENTITY_POLICY_VERSION = "v0-3-s2-synthetic-source-row-identity-v1"

CLEANING_POLICY_VERSION = "v0-3-s2-cleaning-policy-v1"
QUALITY_POLICY_VERSION = "v0-3-s2-quality-policy-v1"
CORRECTION_POLICY_VERSION = "v0-3-s2-correction-policy-v1"
EXCLUSION_POLICY_VERSION = "v0-3-s2-exclusion-policy-v1"
CLEANED_SCHEMA_VERSION = "v0-3-s2-cleaned-schema-v1"
CLEANING_PROJECTION_VERSION = "v0-3-s2-cleaning-projection-v1"
QUALITY_SCHEMA_VERSION = "v0-3-s2-quality-schema-v1"
CORRECTION_SCHEMA_VERSION = "v0-3-s2-correction-schema-v1"
EXCLUSION_SCHEMA_VERSION = "v0-3-s2-exclusion-schema-v1"
QUALITY_RULE_VERSION = "v0-3-s2-quality-rule-v1"

CLEANED_DATASET_VERSION_IDENTITY_POLICY_VERSION = "v0-3-s2-cleaned-dataset-version-identity-v1"
CLEANED_ROW_IDENTITY_POLICY_VERSION = "v0-3-s2-cleaned-row-identity-v1"
QUALITY_FINDING_IDENTITY_POLICY_VERSION = "v0-3-s2-quality-finding-identity-v1"
CORRECTION_LEDGER_ENTRY_IDENTITY_POLICY_VERSION = "v0-3-s2-correction-ledger-entry-identity-v1"
EXCLUSION_LEDGER_ENTRY_IDENTITY_POLICY_VERSION = "v0-3-s2-exclusion-ledger-entry-identity-v1"
QUALITY_REPORT_IDENTITY_POLICY_VERSION = "v0-3-s2-quality-report-identity-v1"
VALUE_DIGEST_POLICY_VERSION = "v0-3-s2-value-digest-v1"


def digest(value: object) -> str:
    return sha256(canonical_json_dumps(value).encode("utf-8")).hexdigest()


def _canonical_optional_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    encoded = canonical_json_value(value)
    if not isinstance(encoded, str):
        raise TypeError("canonical decimal encoding must be a string")
    return encoded


def compute_value_digest(*, field_name: str, value: Decimal | None) -> str:
    return digest(
        {
            "policy_version": VALUE_DIGEST_POLICY_VERSION,
            "field_name": field_name,
            "value": _canonical_optional_decimal(value),
        }
    )


def compute_canonical_grain_key_payload(
    *,
    season_business_key: str,
    farm_business_key: str,
    subfarm_business_key: str,
    variety_business_key: str,
    harvest_business_date: date,
) -> dict[str, Any]:
    return {
        "season_business_key": season_business_key,
        "farm_business_key": farm_business_key,
        "subfarm_business_key": subfarm_business_key,
        "variety_business_key": variety_business_key,
        "harvest_business_date": harvest_business_date.isoformat(),
    }


def compute_synthetic_raw_source_artifact_identity_hash(
    artifact: Mapping[str, Any],
) -> str:
    return digest(
        {
            "policy_version": SYNTHETIC_RAW_SOURCE_ARTIFACT_IDENTITY_POLICY_VERSION,
            "serialization_profile": S2_CANONICAL_SERIALIZATION_PROFILE,
            "stable_identity_inputs": {
                "source_system": artifact["source_system"],
                "source_dataset": artifact["source_dataset"],
                "source_version": artifact["source_version"],
                "source_snapshot_reference": artifact["source_snapshot_reference"],
                "source_object_identity": artifact["source_object_identity"],
                "source_artifact_sequence": artifact["source_artifact_sequence"],
            },
            "version_fields": {
                "source_version": artifact["source_version"],
                "schema_version": artifact["schema_version"],
                "mapping_policy_version": artifact["mapping_policy_version"],
                "source_artifact_identity_version": artifact["source_artifact_identity_version"],
            },
        }
    )


def compute_synthetic_raw_import_batch_identity_hash(
    batch: Mapping[str, Any],
) -> str:
    return digest(
        {
            "policy_version": SYNTHETIC_RAW_IMPORT_BATCH_IDENTITY_POLICY_VERSION,
            "serialization_profile": S2_CANONICAL_SERIALIZATION_PROFILE,
            "stable_identity_inputs": {
                "raw_source_artifact_identity": batch["raw_source_artifact_identity_hash"],
                "external_batch_id": batch["external_batch_id"],
                "source_system": batch["source_system"],
                "source_dataset": batch["source_dataset"],
                "raw_payload_hash": batch["raw_payload_hash"],
            },
            "version_fields": {
                "import_policy_version": batch["import_policy_version"],
                "schema_version": batch["schema_version"],
                "mapping_policy_version": batch["mapping_policy_version"],
                "validation_policy_version": batch["validation_policy_version"],
            },
            "lineage_fields": {
                "source_cohort_id": batch["source_cohort_id"],
            },
        }
    )


def compute_synthetic_source_row_identity_hash(row: Mapping[str, Any]) -> str:
    return digest(
        {
            "policy_version": SYNTHETIC_SOURCE_ROW_IDENTITY_POLICY_VERSION,
            "serialization_profile": S2_CANONICAL_SERIALIZATION_PROFILE,
            "stable_identity_inputs": {
                "raw_source_artifact_identity": row["raw_source_artifact_identity_hash"],
                "external_logical_record_id": row["external_logical_record_id"],
                "external_revision_id": row["external_revision_id"],
                "revision_number": row["revision_number"],
                "source_system": row["source_system"],
            },
            "version_fields": {
                "source_row_identity_version": row["source_row_identity_version"],
                "schema_version": row["schema_version"],
                "source_version": row["source_version"],
            },
            "lineage_fields": {
                "raw_import_batch_identity": row["raw_import_batch_identity_hash"],
                "source_sheet_name": row.get("source_sheet_name"),
                "source_row_number": row.get("source_row_number"),
            },
        }
    )


def compute_quality_report_identity_hash(
    *,
    cleaned_dataset_version_identity_hash: str,
    quality_policy_version: str,
    finding_identity_hashes: Iterable[str],
) -> str:
    ordered = tuple(sorted(finding_identity_hashes))
    return digest(
        {
            "policy_version": QUALITY_REPORT_IDENTITY_POLICY_VERSION,
            "cleaned_dataset_version_identity": cleaned_dataset_version_identity_hash,
            "quality_policy_version": quality_policy_version,
            "finding_identity_hashes": ordered,
        }
    )


def compute_quality_finding_identity_hash(
    *,
    cleaned_dataset_version_identity_hash: str,
    source_row_identity_hash: str,
    quality_rule_id: str,
    observed_field: str,
    finding_code: str,
    quality_policy_version: str,
    quality_rule_version: str,
    quality_schema_version: str,
    normalized_observed_value_identity: str,
    severity: str,
    rule_definition_hash: str,
) -> str:
    return digest(
        {
            "policy_version": QUALITY_FINDING_IDENTITY_POLICY_VERSION,
            "serialization_profile": S2_CANONICAL_SERIALIZATION_PROFILE,
            "stable_identity_inputs": {
                "cleaned_dataset_version_identity": cleaned_dataset_version_identity_hash,
                "source_row_identity": source_row_identity_hash,
                "quality_rule_id": quality_rule_id,
                "observed_field": observed_field,
                "finding_code": finding_code,
            },
            "version_fields": {
                "quality_policy_version": quality_policy_version,
                "quality_rule_version": quality_rule_version,
                "quality_schema_version": quality_schema_version,
            },
            "content": {
                "normalized_observed_value_identity": normalized_observed_value_identity,
                "severity": severity,
                "rule_definition_hash": rule_definition_hash,
            },
        }
    )


def compute_correction_ledger_entry_identity_hash(
    *,
    correction_event_id: str,
    cleaned_dataset_version_identity_hash: str,
    source_row_identity_hash: str,
    field_name: str,
    correction_policy_version: str,
    correction_schema_version: str,
    original_value_digest: str,
    corrected_value_digest: str,
    reason: str,
) -> str:
    return digest(
        {
            "policy_version": CORRECTION_LEDGER_ENTRY_IDENTITY_POLICY_VERSION,
            "serialization_profile": S2_CANONICAL_SERIALIZATION_PROFILE,
            "stable_identity_inputs": {
                "correction_event_id": correction_event_id,
                "cleaned_dataset_version_identity": cleaned_dataset_version_identity_hash,
                "source_row_identity": source_row_identity_hash,
                "field_name": field_name,
                "correction_policy_version": correction_policy_version,
            },
            "version_fields": {
                "correction_policy_version": correction_policy_version,
                "correction_schema_version": correction_schema_version,
            },
            "content": {
                "original_value_digest": original_value_digest,
                "corrected_value_digest": corrected_value_digest,
                "reason": reason,
            },
        }
    )


def compute_exclusion_ledger_entry_identity_hash(
    *,
    exclusion_event_id: str,
    cleaned_dataset_version_identity_hash: str,
    source_row_identity_hash: str,
    exclusion_code: str,
    exclusion_policy_version: str,
    exclusion_schema_version: str,
    exclusion_reason_reference: str,
    disposition: str = "EXCLUDED",
) -> str:
    return digest(
        {
            "policy_version": EXCLUSION_LEDGER_ENTRY_IDENTITY_POLICY_VERSION,
            "serialization_profile": S2_CANONICAL_SERIALIZATION_PROFILE,
            "stable_identity_inputs": {
                "exclusion_event_id": exclusion_event_id,
                "cleaned_dataset_version_identity": cleaned_dataset_version_identity_hash,
                "source_row_identity": source_row_identity_hash,
                "exclusion_code": exclusion_code,
                "exclusion_policy_version": exclusion_policy_version,
            },
            "version_fields": {
                "exclusion_policy_version": exclusion_policy_version,
                "exclusion_schema_version": exclusion_schema_version,
            },
            "content": {
                "exclusion_reason_reference": exclusion_reason_reference,
                "disposition": disposition,
            },
        }
    )


def compute_cleaned_row_content_hash(
    *,
    source_row_identity_hash: str,
    canonical_grain_key: Mapping[str, Any],
    cleaning_projection_version: str,
    cleaned_row_schema_version: str,
    cleaning_policy_version: str,
    correction_policy_version: str,
    exclusion_policy_version: str,
    source_actual_harvest_quantity_kg: Decimal | None,
    effective_actual_harvest_quantity_kg: Decimal | None,
    quantity_presence_status: str,
    is_excluded: bool,
    quality_finding_identity_hashes: Iterable[str],
    correction_ledger_entry_identity_hashes: Iterable[str],
    exclusion_ledger_entry_identity_hashes: Iterable[str],
) -> str:
    return digest(
        {
            "policy_version": CLEANED_ROW_IDENTITY_POLICY_VERSION,
            "serialization_profile": S2_CANONICAL_SERIALIZATION_PROFILE,
            "payload": {
                "source_row_identity": source_row_identity_hash,
                "canonical_grain_key": dict(canonical_grain_key),
                "cleaning_projection_version": cleaning_projection_version,
                "cleaned_row_schema_version": cleaned_row_schema_version,
                "cleaning_policy_version": cleaning_policy_version,
                "correction_policy_version": correction_policy_version,
                "exclusion_policy_version": exclusion_policy_version,
                "source_actual_harvest_quantity_kg": _canonical_optional_decimal(
                    source_actual_harvest_quantity_kg
                ),
                "effective_actual_harvest_quantity_kg": _canonical_optional_decimal(
                    effective_actual_harvest_quantity_kg
                ),
                "quantity_presence_status": quantity_presence_status,
                "is_excluded": is_excluded,
                "quality_finding_identity_hashes": tuple(sorted(quality_finding_identity_hashes)),
                "correction_ledger_entry_identity_hashes": tuple(
                    sorted(correction_ledger_entry_identity_hashes)
                ),
                "exclusion_ledger_entry_identity_hashes": tuple(
                    sorted(exclusion_ledger_entry_identity_hashes)
                ),
            },
        }
    )


def compute_cleaned_row_identity_hash(
    *,
    cleaned_dataset_version_identity_hash: str,
    source_row_identity_hash: str,
    canonical_grain_key: Mapping[str, Any],
    cleaning_projection_version: str,
    cleaned_row_schema_version: str,
    cleaning_policy_version: str,
    correction_policy_version: str,
    exclusion_policy_version: str,
    cleaned_row_content_hash: str,
) -> str:
    return digest(
        {
            "policy_version": CLEANED_ROW_IDENTITY_POLICY_VERSION,
            "serialization_profile": S2_CANONICAL_SERIALIZATION_PROFILE,
            "stable_identity_inputs": {
                "cleaned_dataset_version_identity": cleaned_dataset_version_identity_hash,
                "source_row_identity": source_row_identity_hash,
                "canonical_grain_key": dict(canonical_grain_key),
                "cleaning_projection_version": cleaning_projection_version,
            },
            "version_fields": {
                "cleaned_row_schema_version": cleaned_row_schema_version,
                "cleaning_policy_version": cleaning_policy_version,
                "correction_policy_version": correction_policy_version,
                "exclusion_policy_version": exclusion_policy_version,
            },
            "cleaned_row_content_hash": cleaned_row_content_hash,
        }
    )


def compute_cleaned_dataset_version_identity_hash(
    *,
    source_cohort_id: str,
    raw_import_batch_identity_hashes: Iterable[str],
    cleaning_policy_version: str,
    quality_policy_version: str,
    correction_policy_version: str,
    exclusion_policy_version: str,
    mapping_registry_hash: str,
    cleaned_schema_version: str,
) -> str:
    ordered_batches = tuple(sorted(raw_import_batch_identity_hashes))
    return digest(
        {
            "policy_version": CLEANED_DATASET_VERSION_IDENTITY_POLICY_VERSION,
            "serialization_profile": S2_CANONICAL_SERIALIZATION_PROFILE,
            "stable_identity_inputs": {
                "source_cohort_id": source_cohort_id,
                "ordered_raw_import_batch_identities": ordered_batches,
                "cleaning_policy_version": cleaning_policy_version,
                "quality_policy_version": quality_policy_version,
                "correction_policy_version": correction_policy_version,
                "exclusion_policy_version": exclusion_policy_version,
                "mapping_registry_hash": mapping_registry_hash,
            },
            "version_fields": {
                "cleaning_policy_version": cleaning_policy_version,
                "quality_policy_version": quality_policy_version,
                "correction_policy_version": correction_policy_version,
                "exclusion_policy_version": exclusion_policy_version,
                "cleaned_schema_version": cleaned_schema_version,
            },
        }
    )


def compute_cleaned_dataset_version_content_hash(
    *,
    cleaned_dataset_version_identity_hash: str,
    raw_source_artifact_identity_hashes: Iterable[str],
    raw_import_batch_identity_hashes: Iterable[str],
    source_row_identity_hashes: Iterable[str],
    quality_report_identity_hash: str,
    correction_ledger_identity_hashes: Iterable[str],
    exclusion_ledger_identity_hashes: Iterable[str],
    cleaned_row_content_hashes: Iterable[str],
) -> str:
    return digest(
        {
            "policy_version": CLEANED_DATASET_VERSION_IDENTITY_POLICY_VERSION,
            "serialization_profile": S2_CANONICAL_SERIALIZATION_PROFILE,
            "cleaned_dataset_version_identity": cleaned_dataset_version_identity_hash,
            "lineage_fields": {
                "raw_source_artifact_identities": tuple(
                    sorted(raw_source_artifact_identity_hashes)
                ),
                "raw_import_batch_identities": tuple(sorted(raw_import_batch_identity_hashes)),
                "source_row_identity_set": tuple(sorted(source_row_identity_hashes)),
                "quality_report_identity": quality_report_identity_hash,
                "ledger_identity_set": tuple(
                    sorted(
                        [
                            *correction_ledger_identity_hashes,
                            *exclusion_ledger_identity_hashes,
                        ]
                    )
                ),
            },
            "ordered_cleaned_row_content_hashes": tuple(sorted(cleaned_row_content_hashes)),
        }
    )
