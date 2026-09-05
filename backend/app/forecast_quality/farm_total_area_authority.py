"""Farm-total area authority package (V0.3 Farm-total data plane)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from backend.app.forecast_quality.canonical import (
    canonical_json_bytes,
    emit_s3_area_mu,
)
from backend.app.forecast_quality.exceptions import (
    S3ContractInvariantViolationError,
    S3DecimalAssertionError,
    S3StructuralDuplicateError,
)
from backend.app.forecast_quality.farm_total_policy import (
    AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
    FARM_TOTAL_AREA_AUTHORITY_SCHEMA_VERSION,
    FARM_TOTAL_AREA_POLICY_VERSION,
    FARM_TOTAL_MAPPING_POLICY_VERSION,
    FARM_TOTAL_PRIOR_AREA_SOURCE_SEASON,
    FARM_TOTAL_TARGET_SEASON,
)


class FarmTotalAreaAuthorityLoadError(S3ContractInvariantViolationError):
    """Raised when an area authority package fails validation."""


class FarmTotalAreaAuthorityBlocker(StrEnum):
    NONE = "NONE"
    SCHEMA_VERSION_MISMATCH = "SCHEMA_VERSION_MISMATCH"
    POLICY_VERSION_MISMATCH = "POLICY_VERSION_MISMATCH"
    DUPLICATE_BASELINE_GROUP = "DUPLICATE_BASELINE_GROUP"
    NON_POSITIVE_AREA = "NON_POSITIVE_AREA"
    NATIVE_FLOAT_REJECTED = "NATIVE_FLOAT_REJECTED"
    INVALID_AUTHORITY_CLASS = "INVALID_AUTHORITY_CLASS"
    ROW_HASH_MISMATCH = "ROW_HASH_MISMATCH"
    CANONICAL_HASH_MISMATCH = "CANONICAL_HASH_MISMATCH"
    AUTHORITY_SET_HASH_MISMATCH = "AUTHORITY_SET_HASH_MISMATCH"


@dataclass(frozen=True, slots=True)
class FarmTotalAreaAuthorityRow:
    baseline_farm_group_key: str
    source_farm_business_keys: tuple[str, ...]
    area_mu: Decimal
    area_authority_class: str
    area_source_season: str
    area_source_identity: str
    area_source_hash: str
    mapping_policy_version: str
    mapping_identity_hash: str
    source_row_refs: tuple[str, ...]
    row_hash: str


@dataclass(frozen=True, slots=True)
class FarmTotalAreaAuthorityPackage:
    schema_version: str
    policy_version: str
    source_season: str
    target_season: str
    mapping_policy_version: str
    source_file_hashes: tuple[tuple[str, str], ...]
    rows: tuple[FarmTotalAreaAuthorityRow, ...]
    area_authority_set_sha256: str
    canonical_hash: str


def _parse_decimal_field(value: Any, field_name: str) -> Decimal:
    if isinstance(value, float):
        raise S3DecimalAssertionError(f"{field_name} native float is forbidden")
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, str):
        parsed = Decimal(value)
    elif isinstance(value, int):
        parsed = Decimal(value)
    else:
        raise S3DecimalAssertionError(f"{field_name} must be Decimal-serializable")
    if not parsed.is_finite() or parsed <= 0:
        raise FarmTotalAreaAuthorityLoadError(f"{field_name} must be > 0")
    return parsed


def compute_area_authority_row_hash(row: FarmTotalAreaAuthorityRow) -> str:
    payload = {
        "baseline_farm_group_key": row.baseline_farm_group_key,
        "source_farm_business_keys": list(row.source_farm_business_keys),
        "area_mu": emit_s3_area_mu(row.area_mu),
        "area_authority_class": row.area_authority_class,
        "area_source_season": row.area_source_season,
        "area_source_identity": row.area_source_identity,
        "area_source_hash": row.area_source_hash,
        "mapping_policy_version": row.mapping_policy_version,
        "mapping_identity_hash": row.mapping_identity_hash,
        "source_row_refs": list(row.source_row_refs),
        "row_hash": "",
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_area_authority_row(
    *,
    baseline_farm_group_key: str,
    source_farm_business_keys: tuple[str, ...],
    area_mu: Decimal,
    area_authority_class: str,
    area_source_season: str,
    area_source_identity: str,
    area_source_hash: str,
    mapping_policy_version: str,
    mapping_identity_hash: str,
    source_row_refs: tuple[str, ...],
) -> FarmTotalAreaAuthorityRow:
    if not isinstance(area_mu, Decimal) or not area_mu.is_finite() or area_mu <= 0:
        raise FarmTotalAreaAuthorityLoadError("area_mu must be a positive finite Decimal")
    if area_authority_class != AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY:
        raise FarmTotalAreaAuthorityLoadError(
            f"R1 only supports {AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY}"
        )

    row = FarmTotalAreaAuthorityRow(
        baseline_farm_group_key=baseline_farm_group_key,
        source_farm_business_keys=source_farm_business_keys,
        area_mu=area_mu,
        area_authority_class=area_authority_class,
        area_source_season=area_source_season,
        area_source_identity=area_source_identity,
        area_source_hash=area_source_hash,
        mapping_policy_version=mapping_policy_version,
        mapping_identity_hash=mapping_identity_hash,
        source_row_refs=source_row_refs,
        row_hash="",
    )
    row_hash = compute_area_authority_row_hash(row)
    return FarmTotalAreaAuthorityRow(
        baseline_farm_group_key=row.baseline_farm_group_key,
        source_farm_business_keys=row.source_farm_business_keys,
        area_mu=row.area_mu,
        area_authority_class=row.area_authority_class,
        area_source_season=row.area_source_season,
        area_source_identity=row.area_source_identity,
        area_source_hash=row.area_source_hash,
        mapping_policy_version=row.mapping_policy_version,
        mapping_identity_hash=row.mapping_identity_hash,
        source_row_refs=row.source_row_refs,
        row_hash=row_hash,
    )


def compute_area_authority_set_sha256(rows: tuple[FarmTotalAreaAuthorityRow, ...]) -> str:
    ordered = sorted(rows, key=lambda r: r.baseline_farm_group_key)
    payload = [
        {
            "baseline_farm_group_key": row.baseline_farm_group_key,
            "source_farm_business_keys": list(row.source_farm_business_keys),
            "area_mu": emit_s3_area_mu(row.area_mu),
            "area_authority_class": row.area_authority_class,
            "area_source_season": row.area_source_season,
            "area_source_identity": row.area_source_identity,
            "area_source_hash": row.area_source_hash,
            "mapping_policy_version": row.mapping_policy_version,
            "mapping_identity_hash": row.mapping_identity_hash,
            "source_row_refs": list(row.source_row_refs),
            "row_hash": row.row_hash,
        }
        for row in ordered
    ]
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_area_authority_package(
    *,
    rows: tuple[FarmTotalAreaAuthorityRow, ...],
    source_file_hashes: tuple[tuple[str, str], ...],
    mapping_policy_version: str = FARM_TOTAL_MAPPING_POLICY_VERSION,
    mapping_identity_hash: str,
    source_season: str = FARM_TOTAL_PRIOR_AREA_SOURCE_SEASON,
    target_season: str = FARM_TOTAL_TARGET_SEASON,
) -> FarmTotalAreaAuthorityPackage:
    area_authority_set_sha256 = compute_area_authority_set_sha256(rows)
    ordered_hashes = sorted(source_file_hashes, key=lambda item: item[0])
    semantic: dict[str, Any] = {
        "schema_version": FARM_TOTAL_AREA_AUTHORITY_SCHEMA_VERSION,
        "policy_version": FARM_TOTAL_AREA_POLICY_VERSION,
        "source_season": source_season,
        "target_season": target_season,
        "mapping_policy_version": mapping_policy_version,
        "source_file_hashes": {name: digest for name, digest in ordered_hashes},
        "rows": [
            {
                "baseline_farm_group_key": row.baseline_farm_group_key,
                "source_farm_business_keys": list(row.source_farm_business_keys),
                "area_mu": emit_s3_area_mu(row.area_mu),
                "area_authority_class": row.area_authority_class,
                "area_source_season": row.area_source_season,
                "area_source_identity": row.area_source_identity,
                "area_source_hash": row.area_source_hash,
                "mapping_policy_version": row.mapping_policy_version,
                "mapping_identity_hash": row.mapping_identity_hash,
                "source_row_refs": list(row.source_row_refs),
                "row_hash": row.row_hash,
            }
            for row in sorted(rows, key=lambda r: r.baseline_farm_group_key)
        ],
        "area_authority_set_sha256": area_authority_set_sha256,
        "canonical_hash": "",
    }
    canonical_hash = hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()
    return FarmTotalAreaAuthorityPackage(
        schema_version=FARM_TOTAL_AREA_AUTHORITY_SCHEMA_VERSION,
        policy_version=FARM_TOTAL_AREA_POLICY_VERSION,
        source_season=source_season,
        target_season=target_season,
        mapping_policy_version=mapping_policy_version,
        source_file_hashes=tuple(ordered_hashes),
        rows=rows,
        area_authority_set_sha256=area_authority_set_sha256,
        canonical_hash=canonical_hash,
    )


def area_authority_package_to_payload(package: FarmTotalAreaAuthorityPackage) -> dict[str, Any]:
    return {
        "schema_version": package.schema_version,
        "policy_version": package.policy_version,
        "source_season": package.source_season,
        "target_season": package.target_season,
        "mapping_policy_version": package.mapping_policy_version,
        "source_file_hashes": {name: digest for name, digest in package.source_file_hashes},
        "rows": [
            {
                "baseline_farm_group_key": row.baseline_farm_group_key,
                "source_farm_business_keys": list(row.source_farm_business_keys),
                "area_mu": emit_s3_area_mu(row.area_mu),
                "area_authority_class": row.area_authority_class,
                "area_source_season": row.area_source_season,
                "area_source_identity": row.area_source_identity,
                "area_source_hash": row.area_source_hash,
                "mapping_policy_version": row.mapping_policy_version,
                "mapping_identity_hash": row.mapping_identity_hash,
                "source_row_refs": list(row.source_row_refs),
                "row_hash": row.row_hash,
            }
            for row in sorted(package.rows, key=lambda r: r.baseline_farm_group_key)
        ],
        "area_authority_set_sha256": package.area_authority_set_sha256,
        "canonical_hash": package.canonical_hash,
    }


def load_area_authority_package(payload: dict[str, Any]) -> FarmTotalAreaAuthorityPackage:
    blocker, package = validate_area_authority_package_payload(payload)
    if blocker != FarmTotalAreaAuthorityBlocker.NONE or package is None:
        raise FarmTotalAreaAuthorityLoadError(f"area authority package invalid: {blocker}")
    return package


def validate_area_authority_package_payload(
    payload: dict[str, Any],
) -> tuple[FarmTotalAreaAuthorityBlocker, FarmTotalAreaAuthorityPackage | None]:
    if payload.get("schema_version") != FARM_TOTAL_AREA_AUTHORITY_SCHEMA_VERSION:
        return FarmTotalAreaAuthorityBlocker.SCHEMA_VERSION_MISMATCH, None
    if payload.get("policy_version") != FARM_TOTAL_AREA_POLICY_VERSION:
        return FarmTotalAreaAuthorityBlocker.POLICY_VERSION_MISMATCH, None

    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        return FarmTotalAreaAuthorityBlocker.DUPLICATE_BASELINE_GROUP, None

    rows: list[FarmTotalAreaAuthorityRow] = []
    seen_groups: set[str] = set()

    for raw in raw_rows:
        if not isinstance(raw, dict):
            return FarmTotalAreaAuthorityBlocker.DUPLICATE_BASELINE_GROUP, None
        group_key = raw.get("baseline_farm_group_key")
        if not isinstance(group_key, str) or not group_key:
            return FarmTotalAreaAuthorityBlocker.DUPLICATE_BASELINE_GROUP, None
        if group_key in seen_groups:
            return FarmTotalAreaAuthorityBlocker.DUPLICATE_BASELINE_GROUP, None
        seen_groups.add(group_key)

        try:
            area_mu = _parse_decimal_field(raw.get("area_mu"), "area_mu")
        except (S3DecimalAssertionError, FarmTotalAreaAuthorityLoadError):
            if isinstance(raw.get("area_mu"), float):
                return FarmTotalAreaAuthorityBlocker.NATIVE_FLOAT_REJECTED, None
            return FarmTotalAreaAuthorityBlocker.NON_POSITIVE_AREA, None

        authority_class = raw.get("area_authority_class")
        if authority_class != AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY:
            return FarmTotalAreaAuthorityBlocker.INVALID_AUTHORITY_CLASS, None

        source_keys = raw.get("source_farm_business_keys")
        if not isinstance(source_keys, list) or not source_keys:
            return FarmTotalAreaAuthorityBlocker.DUPLICATE_BASELINE_GROUP, None

        row = FarmTotalAreaAuthorityRow(
            baseline_farm_group_key=group_key,
            source_farm_business_keys=tuple(sorted(str(k) for k in source_keys)),
            area_mu=area_mu,
            area_authority_class=str(authority_class),
            area_source_season=str(raw.get("area_source_season", "")),
            area_source_identity=str(raw.get("area_source_identity", "")),
            area_source_hash=str(raw.get("area_source_hash", "")),
            mapping_policy_version=str(raw.get("mapping_policy_version", "")),
            mapping_identity_hash=str(raw.get("mapping_identity_hash", "")),
            source_row_refs=tuple(sorted(str(r) for r in raw.get("source_row_refs", []))),
            row_hash=str(raw.get("row_hash", "")),
        )
        expected_row_hash = compute_area_authority_row_hash(row)
        if row.row_hash != expected_row_hash:
            return FarmTotalAreaAuthorityBlocker.ROW_HASH_MISMATCH, None
        rows.append(row)

    ordered_rows = tuple(sorted(rows, key=lambda r: r.baseline_farm_group_key))
    authority_set_sha256 = compute_area_authority_set_sha256(ordered_rows)
    if payload.get("area_authority_set_sha256") != authority_set_sha256:
        return FarmTotalAreaAuthorityBlocker.AUTHORITY_SET_HASH_MISMATCH, None

    raw_hashes = payload.get("source_file_hashes", {})
    if not isinstance(raw_hashes, dict):
        return FarmTotalAreaAuthorityBlocker.CANONICAL_HASH_MISMATCH, None
    source_file_hashes = tuple(sorted((str(k), str(v)) for k, v in raw_hashes.items()))

    package = build_area_authority_package(
        rows=ordered_rows,
        source_file_hashes=source_file_hashes,
        mapping_policy_version=str(payload.get("mapping_policy_version", "")),
        mapping_identity_hash=str(ordered_rows[0].mapping_identity_hash if ordered_rows else ""),
        source_season=str(payload.get("source_season", "")),
        target_season=str(payload.get("target_season", "")),
    )
    if package.canonical_hash != str(payload.get("canonical_hash", "")):
        return FarmTotalAreaAuthorityBlocker.CANONICAL_HASH_MISMATCH, None

    return FarmTotalAreaAuthorityBlocker.NONE, package


def area_by_baseline_group(
    package: FarmTotalAreaAuthorityPackage,
) -> dict[str, FarmTotalAreaAuthorityRow]:
    lookup: dict[str, FarmTotalAreaAuthorityRow] = {}
    for row in package.rows:
        if row.baseline_farm_group_key in lookup:
            raise S3StructuralDuplicateError(
                f"duplicate area authority for {row.baseline_farm_group_key}"
            )
        lookup[row.baseline_farm_group_key] = row
    return lookup
