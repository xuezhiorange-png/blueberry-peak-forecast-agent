"""Hash helpers for Lane D materialized partitions, manifests, and identities."""

from __future__ import annotations

import hashlib
from datetime import date

from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload
from backend.app.s2_materialized_dataset.shared.contracts import (
    BUILDER_VERSION,
    CANONICAL_GRAIN,
    PARTITION_DATE_FIELD,
    SOURCE_COHORT_ID,
    SPLIT_POLICY_VERSION,
    TARGET_DECISION,
    MaterializableRow,
    PartitionName,
)


def content_sha256(content_bytes: bytes) -> str:
    return hashlib.sha256(content_bytes).hexdigest()


def manifest_sha256(manifest_payload: dict[str, object]) -> str:
    excluded = {
        "manifest_sha256",
        "build_started_at",
        "build_completed_at",
    }
    control_payload = {key: value for key, value in manifest_payload.items() if key not in excluded}
    return sha256_payload(control_payload)


def manifest_control_payload(manifest_payload: dict[str, object]) -> str:
    excluded = {
        "manifest_sha256",
        "build_started_at",
        "build_completed_at",
    }
    control_payload = {key: value for key, value in manifest_payload.items() if key not in excluded}
    return canonical_json_dumps(control_payload)


def _policy_versions_payload(
    *,
    raw_policy_version: str,
    cleaning_policy_version: str,
    correction_policy_version: str,
    exclusion_policy_version: str,
    visibility_policy_version: str,
    revision_winner_policy_version: str,
) -> dict[str, str]:
    return {
        "cleaning_policy_version": cleaning_policy_version,
        "correction_policy_version": correction_policy_version,
        "exclusion_policy_version": exclusion_policy_version,
        "raw_policy_version": raw_policy_version,
        "revision_winner_policy_version": revision_winner_policy_version,
        "split_policy_version": SPLIT_POLICY_VERSION,
        "visibility_policy_version": visibility_policy_version,
    }


def dataset_identity_reference(*, dataset_id: str, dataset_version: str) -> dict[str, str]:
    """Stable dataset identity reference bound into partition identity inputs."""
    return {
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "source_cohort_id": SOURCE_COHORT_ID,
    }


def partition_row_identities(
    rows: tuple[MaterializableRow, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    cleaned = tuple(row.cleaned_row_identity for row in rows)
    pit = tuple(row.pit_visibility_identity for row in rows)
    return cleaned, pit


def materialized_partition_identity_sha256(
    *,
    dataset_id: str,
    dataset_version: str,
    partition_name: PartitionName,
    partition_start_date: date,
    partition_end_date: date,
    ordered_cleaned_row_identities: tuple[str, ...],
    ordered_pit_visibility_identities: tuple[str, ...],
) -> str:
    """§4.12 identity over stable inputs and lineage fields, not content bytes."""
    payload = {
        **dataset_identity_reference(dataset_id=dataset_id, dataset_version=dataset_version),
        "canonical_grain": CANONICAL_GRAIN,
        "ordered_cleaned_row_identities": list(ordered_cleaned_row_identities),
        "ordered_pit_visibility_identities": list(ordered_pit_visibility_identities),
        "partition_date_field": PARTITION_DATE_FIELD,
        "partition_end_date": partition_end_date,
        "partition_name": partition_name,
        "partition_start_date": partition_start_date,
        "split_membership_decision": "HARVEST_BUSINESS_DATE_INCLUSIVE_RANGE",
        "split_policy_version": SPLIT_POLICY_VERSION,
        "target_decision": TARGET_DECISION,
    }
    return sha256_payload(payload)


def materialized_dataset_identity_sha256(
    *,
    dataset_id: str,
    dataset_version: str,
    raw_policy_version: str,
    cleaning_policy_version: str,
    correction_policy_version: str,
    exclusion_policy_version: str,
    visibility_policy_version: str,
    revision_winner_policy_version: str,
    ordered_partition_identities: tuple[str, ...],
    ordered_partition_content_hashes: tuple[str, ...],
) -> str:
    """§4.11 CONTENT_SHA256 over control payload and ordered partition identities."""
    payload = {
        **dataset_identity_reference(dataset_id=dataset_id, dataset_version=dataset_version),
        "builder_version": BUILDER_VERSION,
        "canonical_grain": CANONICAL_GRAIN,
        "ordered_partition_content_hashes": list(ordered_partition_content_hashes),
        "ordered_partition_identities": list(ordered_partition_identities),
        "target_decision": TARGET_DECISION,
        **_policy_versions_payload(
            raw_policy_version=raw_policy_version,
            cleaning_policy_version=cleaning_policy_version,
            correction_policy_version=correction_policy_version,
            exclusion_policy_version=exclusion_policy_version,
            visibility_policy_version=visibility_policy_version,
            revision_winner_policy_version=revision_winner_policy_version,
        ),
    }
    return sha256_payload(payload)
