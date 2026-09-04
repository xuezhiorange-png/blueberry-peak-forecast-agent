"""TRAIN/VALIDATION S3 binding pairing package infrastructure (contract R1).

Implements typed envelope, two-stage identity hashing, candidate builder, and
package invariant validation. Does not publish packages or issue authorities.
"""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from backend.app.s3_daily_rowset.registry import (
    V0_3_S3_ACTUALS_AUTHORITY,
    V0_3_S3_FORECASTS_AUTHORITY,
)
from backend.app.s3_daily_rowset.schemas import (
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_VERSION,
    EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
)

from .canonical import canonical_json_bytes
from .exceptions import S3ContractInvariantViolationError, S3DecimalAssertionError
from .schemas import S3BindingRow, S3EvaluationInput

TRAIN_VAL_PAIRING_PACKAGE_SCHEMA_V1 = "v0-3-s3-b-train-val-binding-pairing-package-v1"
TRAIN_VAL_PAIRING_POLICY_V1 = "v0-3-s3-b-train-val-binding-pairing-policy-v1"
EXACT_ACTUAL_PAIRING_POLICY_V1 = "v0-2-exact-actual-paired-v1"

_TRAIN_VAL_PARTITIONS = frozenset({"TRAIN", "VALIDATION"})
_PAIRING_PACKAGE_IDENTITY_FIELD = "pairing_package_identity"
_PAIRING_PACKAGE_CANONICAL_HASH_FIELD = "canonical_hash"


class TrainValPairingPackageInvariantError(S3ContractInvariantViolationError):
    """Raised when a pairing package violates frozen contract invariants."""


def _is_sha256(value: str) -> bool:
    return (
        len(value) == 64
        and value.lower() == value
        and all(char in "0123456789abcdef" for char in value)
    )


def compute_two_stage_identity_hashes(
    *,
    semantic_payload: dict[str, Any],
    identity_field: str,
    canonical_hash_field: str,
) -> tuple[str, str]:
    """Compute identity and canonical hashes with no self-reference."""

    identity_preimage = dict(semantic_payload)
    identity_preimage[identity_field] = ""
    identity_preimage[canonical_hash_field] = ""
    identity = hashlib.sha256(canonical_json_bytes(identity_preimage)).hexdigest()

    canonical_preimage = dict(semantic_payload)
    canonical_preimage[identity_field] = identity
    canonical_preimage[canonical_hash_field] = ""
    canonical_hash = hashlib.sha256(canonical_json_bytes(canonical_preimage)).hexdigest()
    return identity, canonical_hash


def verify_two_stage_identity_excluded_from_preimage(
    *,
    semantic_payload: dict[str, Any],
    identity_field: str,
    canonical_hash_field: str,
    expected_identity: str,
    expected_canonical_hash: str,
) -> bool:
    """Return True when both hashes replay from ``semantic_payload``."""

    identity_preimage = dict(semantic_payload)
    identity_preimage[identity_field] = ""
    identity_preimage[canonical_hash_field] = ""
    recomputed_identity = hashlib.sha256(canonical_json_bytes(identity_preimage)).hexdigest()
    if recomputed_identity != expected_identity:
        return False

    canonical_preimage = dict(semantic_payload)
    canonical_preimage[identity_field] = expected_identity
    canonical_preimage[canonical_hash_field] = ""
    recomputed_canonical = hashlib.sha256(canonical_json_bytes(canonical_preimage)).hexdigest()
    return recomputed_canonical == expected_canonical_hash


@dataclass(frozen=True)
class SourceDatasetIdentity:
    dataset_id: str
    dataset_version: str
    materialized_dataset_identity_sha256: str


@dataclass(frozen=True)
class PartitionIdentity:
    partition_name: Literal["TRAIN", "VALIDATION"]
    partition_identity_sha256: str
    content_sha256: str
    partition_start_date: date
    partition_end_date: date


ACCEPTED_SOURCE_DATASET_IDENTITY = SourceDatasetIdentity(
    dataset_id=EXPECTED_DATASET_ID,
    dataset_version=EXPECTED_DATASET_VERSION,
    materialized_dataset_identity_sha256=EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
)


@dataclass(frozen=True)
class TrainValidationS3BindingPairingPackage:
    schema_version: str
    pairing_package_identity: str
    partition: Literal["TRAIN", "VALIDATION"]
    source_dataset_identity: SourceDatasetIdentity
    partition_identity: PartitionIdentity
    s2_run_identity: str
    s2_manifest_identity: str
    s2_binding_row_set_hash: str
    forecast_authority_identity: str
    actuals_authority_identity: str
    forecast_cutoff_authority_identity: str
    exact_actual_pairing_policy_version: str
    pairing_policy_version: str
    evaluation_input: S3EvaluationInput
    canonical_hash: str


def _source_dataset_identity_payload(identity: SourceDatasetIdentity) -> dict[str, str]:
    return {
        "dataset_id": identity.dataset_id,
        "dataset_version": identity.dataset_version,
        "materialized_dataset_identity_sha256": identity.materialized_dataset_identity_sha256,
    }


def _partition_identity_payload(identity: PartitionIdentity) -> dict[str, str]:
    return {
        "partition_name": identity.partition_name,
        "partition_identity_sha256": identity.partition_identity_sha256,
        "content_sha256": identity.content_sha256,
        "partition_start_date": identity.partition_start_date.isoformat(),
        "partition_end_date": identity.partition_end_date.isoformat(),
    }


def _evaluation_input_payload(evaluation_input: S3EvaluationInput) -> dict[str, Any]:
    return {
        "rows": [dataclasses.asdict(row) for row in evaluation_input.rows],
        "s2_run_identity": evaluation_input.s2_run_identity,
        "s2_manifest_identity": evaluation_input.s2_manifest_identity,
        "s2_binding_row_set_hash": evaluation_input.s2_binding_row_set_hash,
        "metric_policy_version": evaluation_input.metric_policy_version,
        "baseline_policy_version": evaluation_input.baseline_policy_version,
    }


def build_pairing_package_semantic_payload(
    package: TrainValidationS3BindingPairingPackage,
    *,
    pairing_package_identity: str = "",
    canonical_hash: str = "",
) -> dict[str, Any]:
    """Build canonical semantic payload for pairing package hash replay."""

    return {
        "schema_version": package.schema_version,
        "pairing_package_identity": pairing_package_identity,
        "canonical_hash": canonical_hash,
        "partition": package.partition,
        "source_dataset_identity": _source_dataset_identity_payload(
            package.source_dataset_identity
        ),
        "partition_identity": _partition_identity_payload(package.partition_identity),
        "s2_run_identity": package.s2_run_identity,
        "s2_manifest_identity": package.s2_manifest_identity,
        "s2_binding_row_set_hash": package.s2_binding_row_set_hash,
        "forecast_authority_identity": package.forecast_authority_identity,
        "actuals_authority_identity": package.actuals_authority_identity,
        "forecast_cutoff_authority_identity": package.forecast_cutoff_authority_identity,
        "exact_actual_pairing_policy_version": package.exact_actual_pairing_policy_version,
        "pairing_policy_version": package.pairing_policy_version,
        "evaluation_input": _evaluation_input_payload(package.evaluation_input),
    }


def compute_pairing_package_identity_hashes(
    package: TrainValidationS3BindingPairingPackage,
) -> tuple[str, str]:
    semantic = build_pairing_package_semantic_payload(package)
    return compute_two_stage_identity_hashes(
        semantic_payload=semantic,
        identity_field=_PAIRING_PACKAGE_IDENTITY_FIELD,
        canonical_hash_field=_PAIRING_PACKAGE_CANONICAL_HASH_FIELD,
    )


def verify_pairing_package_hash_replay(package: TrainValidationS3BindingPairingPackage) -> bool:
    semantic = build_pairing_package_semantic_payload(
        package,
        pairing_package_identity=package.pairing_package_identity,
        canonical_hash="",
    )
    return verify_two_stage_identity_excluded_from_preimage(
        semantic_payload=semantic,
        identity_field=_PAIRING_PACKAGE_IDENTITY_FIELD,
        canonical_hash_field=_PAIRING_PACKAGE_CANONICAL_HASH_FIELD,
        expected_identity=package.pairing_package_identity,
        expected_canonical_hash=package.canonical_hash,
    )


def _assert_no_native_float_in_rows(rows: tuple[S3BindingRow, ...] | list[S3BindingRow]) -> None:
    decimal_fields = ("forecast_value_kg", "actual_value_kg")
    for row in rows:
        for field in decimal_fields:
            value = getattr(row, field)
            if isinstance(value, float):
                raise S3DecimalAssertionError("native float is not a business value")


def validate_pairing_package_invariants(
    package: TrainValidationS3BindingPairingPackage,
) -> None:
    """Fail-closed invariant checks for a candidate or published package."""

    if package.partition not in _TRAIN_VAL_PARTITIONS:
        raise TrainValPairingPackageInvariantError("TEST or unknown partition forbidden")
    if package.partition_identity.partition_name != package.partition:
        raise TrainValPairingPackageInvariantError("partition identity name mismatch")
    if package.source_dataset_identity != ACCEPTED_SOURCE_DATASET_IDENTITY:
        raise TrainValPairingPackageInvariantError("source dataset identity mismatch")
    if package.actuals_authority_identity != V0_3_S3_ACTUALS_AUTHORITY:
        raise TrainValPairingPackageInvariantError("actuals authority identity mismatch")
    if package.forecast_authority_identity != V0_3_S3_FORECASTS_AUTHORITY:
        raise TrainValPairingPackageInvariantError("forecast authority identity mismatch")
    if not package.forecast_cutoff_authority_identity.strip():
        raise TrainValPairingPackageInvariantError("forecast cutoff authority missing")
    if not _is_sha256(package.forecast_cutoff_authority_identity):
        raise TrainValPairingPackageInvariantError("forecast cutoff authority invalid")
    for field_name, expected in (
        ("s2_run_identity", package.evaluation_input.s2_run_identity),
        ("s2_manifest_identity", package.evaluation_input.s2_manifest_identity),
        ("s2_binding_row_set_hash", package.evaluation_input.s2_binding_row_set_hash),
    ):
        package_value = getattr(package, field_name)
        if package_value != expected:
            raise TrainValPairingPackageInvariantError(f"{field_name} binding mismatch")
    _assert_no_native_float_in_rows(tuple(package.evaluation_input.rows))


def build_candidate_train_validation_pairing_package(
    *,
    partition: Literal["TRAIN", "VALIDATION"],
    partition_identity: PartitionIdentity,
    evaluation_input: S3EvaluationInput,
    forecast_cutoff_authority_identity: str,
    exact_actual_pairing_policy_version: str = EXACT_ACTUAL_PAIRING_POLICY_V1,
    pairing_policy_version: str = TRAIN_VAL_PAIRING_POLICY_V1,
    schema_version: str = TRAIN_VAL_PAIRING_PACKAGE_SCHEMA_V1,
    source_dataset_identity: SourceDatasetIdentity = ACCEPTED_SOURCE_DATASET_IDENTITY,
    forecast_authority_identity: str = V0_3_S3_FORECASTS_AUTHORITY,
    actuals_authority_identity: str = V0_3_S3_ACTUALS_AUTHORITY,
) -> TrainValidationS3BindingPairingPackage:
    """Build a structurally valid candidate package without publishing it."""

    if partition not in _TRAIN_VAL_PARTITIONS:
        raise TrainValPairingPackageInvariantError("TEST or unknown partition forbidden")
    _assert_no_native_float_in_rows(tuple(evaluation_input.rows))

    candidate = TrainValidationS3BindingPairingPackage(
        schema_version=schema_version,
        pairing_package_identity="",
        partition=partition,
        source_dataset_identity=source_dataset_identity,
        partition_identity=partition_identity,
        s2_run_identity=evaluation_input.s2_run_identity,
        s2_manifest_identity=evaluation_input.s2_manifest_identity,
        s2_binding_row_set_hash=evaluation_input.s2_binding_row_set_hash,
        forecast_authority_identity=forecast_authority_identity,
        actuals_authority_identity=actuals_authority_identity,
        forecast_cutoff_authority_identity=forecast_cutoff_authority_identity,
        exact_actual_pairing_policy_version=exact_actual_pairing_policy_version,
        pairing_policy_version=pairing_policy_version,
        evaluation_input=evaluation_input,
        canonical_hash="",
    )
    validate_pairing_package_invariants(candidate)
    pairing_package_identity, canonical_hash = compute_pairing_package_identity_hashes(candidate)
    return TrainValidationS3BindingPairingPackage(
        schema_version=candidate.schema_version,
        pairing_package_identity=pairing_package_identity,
        partition=candidate.partition,
        source_dataset_identity=candidate.source_dataset_identity,
        partition_identity=candidate.partition_identity,
        s2_run_identity=candidate.s2_run_identity,
        s2_manifest_identity=candidate.s2_manifest_identity,
        s2_binding_row_set_hash=candidate.s2_binding_row_set_hash,
        forecast_authority_identity=candidate.forecast_authority_identity,
        actuals_authority_identity=candidate.actuals_authority_identity,
        forecast_cutoff_authority_identity=candidate.forecast_cutoff_authority_identity,
        exact_actual_pairing_policy_version=candidate.exact_actual_pairing_policy_version,
        pairing_policy_version=candidate.pairing_policy_version,
        evaluation_input=candidate.evaluation_input,
        canonical_hash=canonical_hash,
    )


__all__ = [
    "ACCEPTED_SOURCE_DATASET_IDENTITY",
    "EXACT_ACTUAL_PAIRING_POLICY_V1",
    "PartitionIdentity",
    "SourceDatasetIdentity",
    "TRAIN_VAL_PAIRING_PACKAGE_SCHEMA_V1",
    "TRAIN_VAL_PAIRING_POLICY_V1",
    "TrainValPairingPackageInvariantError",
    "TrainValidationS3BindingPairingPackage",
    "build_candidate_train_validation_pairing_package",
    "build_pairing_package_semantic_payload",
    "compute_pairing_package_identity_hashes",
    "compute_two_stage_identity_hashes",
    "validate_pairing_package_invariants",
    "verify_pairing_package_hash_replay",
    "verify_two_stage_identity_excluded_from_preimage",
]
