"""Baseline Farm Group mapping authority package (V0.3 Farm-total data plane)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from backend.app.forecast_quality.canonical import canonical_json_bytes
from backend.app.forecast_quality.exceptions import (
    S3ContractInvariantViolationError,
    S3StructuralDuplicateError,
)
from backend.app.forecast_quality.farm_total_policy import (
    CONFLICT_EXCLUDED_BASELINE_FARM_GROUPS,
    EXCLUSION_REASON_TEMPORAL_CONFLICT,
    FARM_TOTAL_AREA_POLICY_VERSION,
    FARM_TOTAL_MAPPING_POLICY_VERSION,
    FARM_TOTAL_MAPPING_SCHEMA_VERSION,
    FARM_TOTAL_TARGET_SEASON,
)
from backend.app.s3_daily_rowset.schemas import (
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_VERSION,
    EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
)

FarmGroupExclusionStatus = Literal["ELIGIBLE", "EXCLUDED_CONFLICT"]


class FarmGroupMappingLoadError(S3ContractInvariantViolationError):
    """Raised when a mapping package fails validation."""


class FarmGroupMappingBlocker(StrEnum):
    NONE = "NONE"
    SCHEMA_VERSION_MISMATCH = "SCHEMA_VERSION_MISMATCH"
    POLICY_VERSION_MISMATCH = "POLICY_VERSION_MISMATCH"
    MAPPING_POLICY_VERSION_MISMATCH = "MAPPING_POLICY_VERSION_MISMATCH"
    MAPPING_TARGET_SEASON_MISMATCH = "MAPPING_TARGET_SEASON_MISMATCH"
    MAPPING_SOURCE_DATASET_ID_MISMATCH = "MAPPING_SOURCE_DATASET_ID_MISMATCH"
    MAPPING_SOURCE_DATASET_VERSION_MISMATCH = "MAPPING_SOURCE_DATASET_VERSION_MISMATCH"
    MAPPING_MATERIALIZED_IDENTITY_MISMATCH = "MAPPING_MATERIALIZED_IDENTITY_MISMATCH"
    DUPLICATE_BASELINE_GROUP = "DUPLICATE_BASELINE_GROUP"
    DUPLICATE_SOURCE_FARM_KEY = "DUPLICATE_SOURCE_FARM_KEY"
    EMPTY_SOURCE_FARM_KEYS = "EMPTY_SOURCE_FARM_KEYS"
    CONFLICT_GROUP_NOT_EXCLUDED = "CONFLICT_GROUP_NOT_EXCLUDED"
    EXCLUDED_GROUP_MISSING_REASON = "EXCLUDED_GROUP_MISSING_REASON"
    CANONICAL_HASH_MISMATCH = "CANONICAL_HASH_MISMATCH"
    MAPPING_SET_HASH_MISMATCH = "MAPPING_SET_HASH_MISMATCH"


@dataclass(frozen=True, slots=True)
class FarmGroupMappingRow:
    baseline_farm_group_key: str
    source_farm_business_keys: tuple[str, ...]
    mapping_relationship_type: str
    exclusion_status: FarmGroupExclusionStatus
    exclusion_reason: str | None
    row_hash: str


@dataclass(frozen=True, slots=True)
class FarmGroupMappingPackage:
    schema_version: str
    policy_version: str
    mapping_policy_version: str
    target_season: str
    source_dataset_id: str
    source_dataset_version: str
    materialized_dataset_identity_sha256: str
    rows: tuple[FarmGroupMappingRow, ...]
    mapping_set_sha256: str
    canonical_hash: str


def _row_semantic_payload(row: FarmGroupMappingRow) -> dict[str, Any]:
    return {
        "baseline_farm_group_key": row.baseline_farm_group_key,
        "source_farm_business_keys": list(row.source_farm_business_keys),
        "mapping_relationship_type": row.mapping_relationship_type,
        "exclusion_status": row.exclusion_status,
        "exclusion_reason": row.exclusion_reason,
    }


def compute_mapping_row_hash(row: FarmGroupMappingRow) -> str:
    payload = _row_semantic_payload(row)
    payload["row_hash"] = ""
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_mapping_row(
    *,
    baseline_farm_group_key: str,
    source_farm_business_keys: tuple[str, ...],
    mapping_relationship_type: str,
    exclusion_status: FarmGroupExclusionStatus,
    exclusion_reason: str | None,
) -> FarmGroupMappingRow:
    if baseline_farm_group_key in CONFLICT_EXCLUDED_BASELINE_FARM_GROUPS:
        if exclusion_status != "EXCLUDED_CONFLICT":
            raise FarmGroupMappingLoadError(
                f"conflict group {baseline_farm_group_key} must be EXCLUDED_CONFLICT"
            )
        if exclusion_reason != EXCLUSION_REASON_TEMPORAL_CONFLICT:
            raise FarmGroupMappingLoadError(
                f"conflict group {baseline_farm_group_key} requires temporal conflict reason"
            )
    elif exclusion_status != "ELIGIBLE":
        raise FarmGroupMappingLoadError(
            f"non-conflict group {baseline_farm_group_key} must be ELIGIBLE"
        )

    semantic = {
        "baseline_farm_group_key": baseline_farm_group_key,
        "source_farm_business_keys": list(source_farm_business_keys),
        "mapping_relationship_type": mapping_relationship_type,
        "exclusion_status": exclusion_status,
        "exclusion_reason": exclusion_reason,
        "row_hash": "",
    }
    row_hash = hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()
    return FarmGroupMappingRow(
        baseline_farm_group_key=baseline_farm_group_key,
        source_farm_business_keys=source_farm_business_keys,
        mapping_relationship_type=mapping_relationship_type,
        exclusion_status=exclusion_status,
        exclusion_reason=exclusion_reason,
        row_hash=row_hash,
    )


def compute_mapping_set_sha256(rows: tuple[FarmGroupMappingRow, ...]) -> str:
    ordered = sorted(rows, key=lambda r: r.baseline_farm_group_key)
    payload = [
        {
            "baseline_farm_group_key": row.baseline_farm_group_key,
            "source_farm_business_keys": list(row.source_farm_business_keys),
            "mapping_relationship_type": row.mapping_relationship_type,
            "exclusion_status": row.exclusion_status,
            "exclusion_reason": row.exclusion_reason,
            "row_hash": row.row_hash,
        }
        for row in ordered
    ]
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_mapping_package(
    *,
    rows: tuple[FarmGroupMappingRow, ...],
    mapping_policy_version: str = FARM_TOTAL_MAPPING_POLICY_VERSION,
    target_season: str = FARM_TOTAL_TARGET_SEASON,
) -> FarmGroupMappingPackage:
    mapping_set_sha256 = compute_mapping_set_sha256(rows)
    semantic: dict[str, Any] = {
        "schema_version": FARM_TOTAL_MAPPING_SCHEMA_VERSION,
        "policy_version": FARM_TOTAL_AREA_POLICY_VERSION,
        "mapping_policy_version": mapping_policy_version,
        "target_season": target_season,
        "source_dataset_id": EXPECTED_DATASET_ID,
        "source_dataset_version": EXPECTED_DATASET_VERSION,
        "materialized_dataset_identity_sha256": EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
        "rows": [
            {
                "baseline_farm_group_key": row.baseline_farm_group_key,
                "source_farm_business_keys": list(row.source_farm_business_keys),
                "mapping_relationship_type": row.mapping_relationship_type,
                "exclusion_status": row.exclusion_status,
                "exclusion_reason": row.exclusion_reason,
                "row_hash": row.row_hash,
            }
            for row in sorted(rows, key=lambda r: r.baseline_farm_group_key)
        ],
        "mapping_set_sha256": mapping_set_sha256,
        "canonical_hash": "",
    }
    canonical_hash = hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()
    return FarmGroupMappingPackage(
        schema_version=FARM_TOTAL_MAPPING_SCHEMA_VERSION,
        policy_version=semantic["policy_version"],
        mapping_policy_version=mapping_policy_version,
        target_season=target_season,
        source_dataset_id=EXPECTED_DATASET_ID,
        source_dataset_version=EXPECTED_DATASET_VERSION,
        materialized_dataset_identity_sha256=EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
        rows=rows,
        mapping_set_sha256=mapping_set_sha256,
        canonical_hash=canonical_hash,
    )


def mapping_package_to_payload(package: FarmGroupMappingPackage) -> dict[str, Any]:
    return {
        "schema_version": package.schema_version,
        "policy_version": package.policy_version,
        "mapping_policy_version": package.mapping_policy_version,
        "target_season": package.target_season,
        "source_dataset_id": package.source_dataset_id,
        "source_dataset_version": package.source_dataset_version,
        "materialized_dataset_identity_sha256": package.materialized_dataset_identity_sha256,
        "rows": [
            {
                "baseline_farm_group_key": row.baseline_farm_group_key,
                "source_farm_business_keys": list(row.source_farm_business_keys),
                "mapping_relationship_type": row.mapping_relationship_type,
                "exclusion_status": row.exclusion_status,
                "exclusion_reason": row.exclusion_reason,
                "row_hash": row.row_hash,
            }
            for row in sorted(package.rows, key=lambda r: r.baseline_farm_group_key)
        ],
        "mapping_set_sha256": package.mapping_set_sha256,
        "canonical_hash": package.canonical_hash,
    }


def load_mapping_package(payload: dict[str, Any]) -> FarmGroupMappingPackage:
    blocker, package = validate_mapping_package_payload(payload)
    if blocker != FarmGroupMappingBlocker.NONE or package is None:
        raise FarmGroupMappingLoadError(f"mapping package invalid: {blocker}")
    return package


def validate_mapping_package_payload(
    payload: dict[str, Any],
) -> tuple[FarmGroupMappingBlocker, FarmGroupMappingPackage | None]:
    if payload.get("schema_version") != FARM_TOTAL_MAPPING_SCHEMA_VERSION:
        return FarmGroupMappingBlocker.SCHEMA_VERSION_MISMATCH, None

    if payload.get("policy_version") != FARM_TOTAL_AREA_POLICY_VERSION:
        return FarmGroupMappingBlocker.POLICY_VERSION_MISMATCH, None

    if payload.get("mapping_policy_version") != FARM_TOTAL_MAPPING_POLICY_VERSION:
        return FarmGroupMappingBlocker.MAPPING_POLICY_VERSION_MISMATCH, None

    if payload.get("target_season") != FARM_TOTAL_TARGET_SEASON:
        return FarmGroupMappingBlocker.MAPPING_TARGET_SEASON_MISMATCH, None

    if payload.get("source_dataset_id") != EXPECTED_DATASET_ID:
        return FarmGroupMappingBlocker.MAPPING_SOURCE_DATASET_ID_MISMATCH, None

    if payload.get("source_dataset_version") != EXPECTED_DATASET_VERSION:
        return FarmGroupMappingBlocker.MAPPING_SOURCE_DATASET_VERSION_MISMATCH, None

    if (
        payload.get("materialized_dataset_identity_sha256")
        != EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256
    ):
        return FarmGroupMappingBlocker.MAPPING_MATERIALIZED_IDENTITY_MISMATCH, None

    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        return FarmGroupMappingBlocker.EMPTY_SOURCE_FARM_KEYS, None

    rows: list[FarmGroupMappingRow] = []
    seen_groups: set[str] = set()
    seen_source_farms: set[str] = set()

    for raw in raw_rows:
        if not isinstance(raw, dict):
            return FarmGroupMappingBlocker.EMPTY_SOURCE_FARM_KEYS, None
        group_key = raw.get("baseline_farm_group_key")
        source_keys = raw.get("source_farm_business_keys")
        if not isinstance(group_key, str) or not group_key:
            return FarmGroupMappingBlocker.EMPTY_SOURCE_FARM_KEYS, None
        if group_key in seen_groups:
            return FarmGroupMappingBlocker.DUPLICATE_BASELINE_GROUP, None
        seen_groups.add(group_key)

        if not isinstance(source_keys, list) or not source_keys:
            return FarmGroupMappingBlocker.EMPTY_SOURCE_FARM_KEYS, None
        normalized_keys = tuple(sorted(str(k) for k in source_keys))
        for farm_key in normalized_keys:
            if farm_key in seen_source_farms:
                return FarmGroupMappingBlocker.DUPLICATE_SOURCE_FARM_KEY, None
            seen_source_farms.add(farm_key)

        exclusion_status = raw.get("exclusion_status")
        exclusion_reason = raw.get("exclusion_reason")
        if group_key in CONFLICT_EXCLUDED_BASELINE_FARM_GROUPS:
            if exclusion_status != "EXCLUDED_CONFLICT":
                return FarmGroupMappingBlocker.CONFLICT_GROUP_NOT_EXCLUDED, None
            if exclusion_reason != EXCLUSION_REASON_TEMPORAL_CONFLICT:
                return FarmGroupMappingBlocker.EXCLUDED_GROUP_MISSING_REASON, None
        elif exclusion_status != "ELIGIBLE":
            return FarmGroupMappingBlocker.EXCLUDED_GROUP_MISSING_REASON, None

        row = FarmGroupMappingRow(
            baseline_farm_group_key=group_key,
            source_farm_business_keys=normalized_keys,
            mapping_relationship_type=str(raw.get("mapping_relationship_type", "UNRESOLVED")),
            exclusion_status=exclusion_status,
            exclusion_reason=exclusion_reason,
            row_hash=str(raw.get("row_hash", "")),
        )
        expected_row_hash = compute_mapping_row_hash(row)
        if row.row_hash != expected_row_hash:
            return FarmGroupMappingBlocker.CANONICAL_HASH_MISMATCH, None
        rows.append(row)

    ordered_rows = tuple(sorted(rows, key=lambda r: r.baseline_farm_group_key))
    mapping_set_sha256 = compute_mapping_set_sha256(ordered_rows)
    if payload.get("mapping_set_sha256") != mapping_set_sha256:
        return FarmGroupMappingBlocker.MAPPING_SET_HASH_MISMATCH, None

    package = FarmGroupMappingPackage(
        schema_version=str(payload["schema_version"]),
        policy_version=str(payload["policy_version"]),
        mapping_policy_version=str(payload.get("mapping_policy_version", "")),
        target_season=str(payload.get("target_season", "")),
        source_dataset_id=str(payload.get("source_dataset_id", "")),
        source_dataset_version=str(payload.get("source_dataset_version", "")),
        materialized_dataset_identity_sha256=str(
            payload.get("materialized_dataset_identity_sha256", "")
        ),
        rows=ordered_rows,
        mapping_set_sha256=mapping_set_sha256,
        canonical_hash=str(payload.get("canonical_hash", "")),
    )
    expected_canonical = build_mapping_package(
        rows=ordered_rows,
        mapping_policy_version=package.mapping_policy_version,
        target_season=package.target_season,
    ).canonical_hash
    if package.canonical_hash != expected_canonical:
        return FarmGroupMappingBlocker.CANONICAL_HASH_MISMATCH, None

    return FarmGroupMappingBlocker.NONE, package


def farm_to_baseline_group_lookup(
    package: FarmGroupMappingPackage,
) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for row in package.rows:
        if row.exclusion_status != "ELIGIBLE":
            continue
        for farm_key in row.source_farm_business_keys:
            if farm_key in lookup:
                raise S3StructuralDuplicateError(
                    f"source farm {farm_key} maps to multiple baseline groups"
                )
            lookup[farm_key] = row.baseline_farm_group_key
    return lookup


def eligible_mapping_rows(package: FarmGroupMappingPackage) -> tuple[FarmGroupMappingRow, ...]:
    return tuple(row for row in package.rows if row.exclusion_status == "ELIGIBLE")
