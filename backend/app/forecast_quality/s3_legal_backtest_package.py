"""Deterministic, fail-closed S3-C legal backtest package construction.

This module only validates and packages already materialized TRAIN and
VALIDATION pairing inputs.  It does not obtain data, publish pairing
packages, issue authority records, execute a backtest, calculate metrics, or
access TEST.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from backend.app.forecast_quality.canonical import canonical_json_bytes
from backend.app.forecast_quality.quantile_coverage import (
    _ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSIONS,
    TrainValidationCoveragePartitionAuthority,
)
from backend.app.forecast_quality.schemas import S3BindingRow, S3EvaluationInput
from backend.app.forecast_quality.train_val_pairing import (
    ACCEPTED_SOURCE_DATASET_IDENTITY,
    ACCEPTED_TRAIN_PARTITION_IDENTITY,
    ACCEPTED_VALIDATION_PARTITION_IDENTITY,
    EXACT_ACTUAL_PAIRING_POLICY_V1,
    PartitionIdentity,
    SourceDatasetIdentity,
    TrainValidationS3BindingPairingPackage,
    compute_two_stage_identity_hashes,
    validate_published_pairing_package_invariants,
    verify_pairing_package_hash_replay,
    verify_two_stage_identity_excluded_from_preimage,
)
from backend.app.forecast_quality.train_val_pairing_materialization import (
    OfficialPartitionRows,
    TrainValidationPairingMaterializationBlocker,
    TrainValidationPairingMaterializationResult,
    compute_s3_binding_row_set_hash,
)
from backend.app.forecast_quality.train_val_trusted_registry import (
    PRODUCTION_TRUSTED_ISSUED_AUTHORITY_REGISTRY,
    PRODUCTION_TRUSTED_PUBLISHED_PAIRING_PACKAGE_REGISTRY,
    TrustedIssuedAuthorityRegistry,
    TrustedPublishedPairingPackageRegistry,
    verify_train_validation_coverage_authority,
)
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    OFFICIAL_TRAIN_ROW_COUNT,
    OFFICIAL_VALIDATION_ROW_COUNT,
)

S3_LEGAL_BACKTEST_PACKAGE_SCHEMA_VERSION = "v0-3-s3-c-legal-backtest-package-v1"
S3_LEGAL_BACKTEST_PACKAGE_IMPLEMENTATION_VERSION = (
    "v0-3-s3-c-legal-backtest-package-implementation-r1"
)
LEGAL_BACKTEST_PACKAGE_STATUS_VALUES = ("LEGAL", "BLOCKED")
TEST_PARTITION_STATUS_SEALED_ABSENT = "SEALED_ABSENT"
MISSING_DAY_POLICY_UNKNOWN_NOT_ZERO = "UNKNOWN_NOT_ZERO"
POINT_IN_TIME_VISIBILITY_POLICY = "SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT"
FORECAST_SELECTION_POLICY = "historical_observed_pit_visible_unique_grain_forecast_run"
REVIEWED_MODEL_ID = "V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF"


class S3LegalBacktestPackageStatus(StrEnum):
    LEGAL = "LEGAL"
    BLOCKED = "BLOCKED"


class S3LegalBacktestPackageBlocker(StrEnum):
    SOURCE_DATASET_IDENTITY_MISMATCH = "SOURCE_DATASET_IDENTITY_MISMATCH"
    TRAIN_PARTITION_IDENTITY_MISMATCH = "TRAIN_PARTITION_IDENTITY_MISMATCH"
    VALIDATION_PARTITION_IDENTITY_MISMATCH = "VALIDATION_PARTITION_IDENTITY_MISMATCH"
    TEST_PARTITION_PRESENT = "TEST_PARTITION_PRESENT"
    TEST_NOT_SEALED = "TEST_NOT_SEALED"
    TRAIN_PAIRING_PACKAGE_MISSING = "TRAIN_PAIRING_PACKAGE_MISSING"
    VALIDATION_PAIRING_PACKAGE_MISSING = "VALIDATION_PAIRING_PACKAGE_MISSING"
    TRAIN_PAIRING_PACKAGE_IDENTITY_INVALID = "TRAIN_PAIRING_PACKAGE_IDENTITY_INVALID"
    VALIDATION_PAIRING_PACKAGE_IDENTITY_INVALID = "VALIDATION_PAIRING_PACKAGE_IDENTITY_INVALID"
    TRAIN_AUTHORITY_RECORD_MISSING = "TRAIN_AUTHORITY_RECORD_MISSING"
    VALIDATION_AUTHORITY_RECORD_MISSING = "VALIDATION_AUTHORITY_RECORD_MISSING"
    TRAIN_AUTHORITY_NOT_TRUSTED = "TRAIN_AUTHORITY_NOT_TRUSTED"
    VALIDATION_AUTHORITY_NOT_TRUSTED = "VALIDATION_AUTHORITY_NOT_TRUSTED"
    S2_BINDING_ROW_SET_HASH_MISMATCH = "S2_BINDING_ROW_SET_HASH_MISMATCH"
    CROSS_PARTITION_ROW_OVERLAP = "CROSS_PARTITION_ROW_OVERLAP"
    MISSING_EXACT_ACTUAL_PAIRING = "MISSING_EXACT_ACTUAL_PAIRING"
    MISSING_EXACT_FORECAST_BINDING_AUTHORITY = "MISSING_EXACT_FORECAST_BINDING_AUTHORITY"
    FORECAST_VALUE_NOT_PIT_VISIBLE = "FORECAST_VALUE_NOT_PIT_VISIBLE"
    HISTORICAL_CUTOFF_SET_EMPTY = "HISTORICAL_CUTOFF_SET_EMPTY"
    HISTORICAL_CUTOFF_SET_INCOMPLETE = "HISTORICAL_CUTOFF_SET_INCOMPLETE"
    HISTORICAL_CUTOFF_SET_IDENTITY_MISMATCH = "HISTORICAL_CUTOFF_SET_IDENTITY_MISMATCH"
    NATIVE_FLOAT_FORBIDDEN = "NATIVE_FLOAT_FORBIDDEN"
    PACKAGE_IDENTITY_MISMATCH = "PACKAGE_IDENTITY_MISMATCH"
    PACKAGE_CANONICAL_HASH_MISMATCH = "PACKAGE_CANONICAL_HASH_MISMATCH"
    GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIREMENT_UNRESOLVED = (
        "GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIREMENT_UNRESOLVED"
    )
    GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIRED_BUT_NOT_AVAILABLE = (
        "GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIRED_BUT_NOT_AVAILABLE"
    )
    LEGAL_BACKTEST_PACKAGE_NOT_IMPLEMENTED = "LEGAL_BACKTEST_PACKAGE_NOT_IMPLEMENTED"


class GenericIncumbentForecastArtifactRequirement(StrEnum):
    UNRESOLVED_BLOCKING = "UNRESOLVED_BLOCKING"
    REQUIRED_FALSE = "REQUIRED_FALSE"
    REQUIRED_TRUE = "REQUIRED_TRUE"


@dataclass(frozen=True, slots=True)
class S3LegalBacktestForecastCutoff:
    """One declared cutoff member in the legal package cutoff set."""

    forecast_cutoff_at: datetime
    model_identity: str
    selection_policy: str
    forecast_authority_identity: str


@dataclass(frozen=True, slots=True)
class S3LegalBacktestForecastCutoffSet:
    """Cutoff members plus their caller-declared replay identity."""

    members: tuple[S3LegalBacktestForecastCutoff, ...]
    identity_sha256: str

    @classmethod
    def from_members(
        cls, members: Sequence[S3LegalBacktestForecastCutoff]
    ) -> S3LegalBacktestForecastCutoffSet:
        normalized = tuple(members)
        return cls(
            members=normalized,
            identity_sha256=compute_forecast_cutoff_set_identity_sha256(normalized),
        )


@dataclass(frozen=True, slots=True)
class S3GenericIncumbentForecastArtifactRequirement:
    """Governed tri-state artifact decision.

    The production entry point always supplies the unresolved state.  This
    carrier is accepted by the private fixture builder only so tests can
    exercise the future REQUIRED=false and REQUIRED=true branches without a
    public caller bypass.
    """

    requirement: GenericIncumbentForecastArtifactRequirement
    artifact_identity_sha256: str | None = None
    binding_identity_sha256: str | None = None
    provenance_identity_sha256: str | None = None
    replay_verified: bool = False


@dataclass(frozen=True, slots=True)
class S3LegalBacktestPackageDiagnostics:
    status: S3LegalBacktestPackageStatus
    blocker_codes: tuple[str, ...]
    blocker_count: int
    train_source_row_count: int
    validation_source_row_count: int
    train_binding_row_count: int
    validation_binding_row_count: int
    train_comparable_row_count: int
    validation_comparable_row_count: int
    cutoff_member_count: int
    cross_partition_row_overlap_count: int
    test_row_count: int
    test_partition_status: str
    generic_artifact_requirement: str


@dataclass(frozen=True, slots=True)
class S3LegalBacktestPackage:
    schema_version: str
    package_identity_sha256: str
    canonical_hash_sha256: str
    source_dataset_identity: SourceDatasetIdentity
    train_partition_identity: PartitionIdentity
    validation_partition_identity: PartitionIdentity
    train_pairing_package_identity: str
    validation_pairing_package_identity: str
    train_authority_record_identity: str
    validation_authority_record_identity: str
    train_evaluation_input_identity: str
    validation_evaluation_input_identity: str
    forecast_authority_identity: str
    in_scope_forecast_cutoff_set: tuple[S3LegalBacktestForecastCutoff, ...]
    in_scope_forecast_cutoff_set_identity_sha256: str
    forecast_cutoff_authority_identity: str
    model_identity: str
    evaluation_window: Mapping[str, str]
    point_in_time_visibility_policy: str
    exact_actual_pairing_policy: str
    missing_day_policy: str
    diagnostics: S3LegalBacktestPackageDiagnostics
    test_partition_status: str

    @property
    def package_sha256(self) -> str:
        return self.package_identity_sha256

    @property
    def canonical_hash(self) -> str:
        return self.canonical_hash_sha256


@dataclass(frozen=True, slots=True)
class S3LegalBacktestPackageResult:
    status: S3LegalBacktestPackageStatus
    package: S3LegalBacktestPackage | None
    diagnostics: S3LegalBacktestPackageDiagnostics

    @property
    def blocker_codes(self) -> tuple[str, ...]:
        return self.diagnostics.blocker_codes

    @property
    def blocker(self) -> str | None:
        return self.blocker_codes[0] if self.blocker_codes else None

    @property
    def legal_package(self) -> S3LegalBacktestPackage | None:
        return self.package


_BLOCKER_ORDER = tuple(S3LegalBacktestPackageBlocker)
_SHA256_HEX_LENGTH = 64
_COMPARABLE_STATUS = "COMPARABLE"
_TRAIN_VALIDATION_PARTITIONS = frozenset({"TRAIN", "VALIDATION"})


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _SHA256_HEX_LENGTH
        and value.lower() == value
        and all(char in "0123456789abcdef" for char in value)
    )


def _ordered_blockers(
    blockers: set[S3LegalBacktestPackageBlocker],
) -> tuple[str, ...]:
    return tuple(code.value for code in _BLOCKER_ORDER if code in blockers)


def _cutoff_member_payload(
    member: S3LegalBacktestForecastCutoff,
) -> dict[str, str]:
    if not isinstance(member.forecast_cutoff_at, datetime):
        raise ValueError("cutoff timestamp type is invalid")
    if member.forecast_cutoff_at.tzinfo is None:
        raise ValueError("cutoff timestamp must be timezone-aware")
    return {
        "forecast_cutoff_at": member.forecast_cutoff_at.isoformat(),
        "model_identity": member.model_identity,
        "selection_policy": member.selection_policy,
        "forecast_authority_identity": member.forecast_authority_identity,
    }


def compute_forecast_cutoff_set_identity_sha256(
    members: Sequence[S3LegalBacktestForecastCutoff],
) -> str:
    """Hash the canonical ordered cutoff members with no hidden members."""

    payload_members = [_cutoff_member_payload(member) for member in members]
    payload_members.sort(
        key=lambda member: (
            member["forecast_cutoff_at"],
            member["model_identity"],
            member["selection_policy"],
            member["forecast_authority_identity"],
        )
    )
    return hashlib.sha256(canonical_json_bytes({"cutoff_members": payload_members})).hexdigest()


def _normalize_cutoff_set(
    cutoff_set: S3LegalBacktestForecastCutoffSet | Sequence[S3LegalBacktestForecastCutoff],
) -> tuple[tuple[S3LegalBacktestForecastCutoff, ...], str, bool]:
    if isinstance(cutoff_set, S3LegalBacktestForecastCutoffSet):
        members = tuple(cutoff_set.members)
        declared_identity = cutoff_set.identity_sha256
    else:
        members = tuple(cutoff_set)
        declared_identity = compute_forecast_cutoff_set_identity_sha256(members)
    recomputed_identity = compute_forecast_cutoff_set_identity_sha256(members)
    return members, declared_identity, declared_identity == recomputed_identity


def _source_dataset_payload(identity: SourceDatasetIdentity) -> dict[str, str]:
    return {
        "dataset_id": identity.dataset_id,
        "dataset_version": identity.dataset_version,
        "materialized_dataset_identity_sha256": (identity.materialized_dataset_identity_sha256),
    }


def _partition_identity_payload(identity: PartitionIdentity) -> dict[str, str]:
    return {
        "partition_name": identity.partition_name,
        "partition_identity_sha256": identity.partition_identity_sha256,
        "content_sha256": identity.content_sha256,
        "partition_start_date": identity.partition_start_date.isoformat(),
        "partition_end_date": identity.partition_end_date.isoformat(),
    }


def _cutoff_set_payload(
    members: Sequence[S3LegalBacktestForecastCutoff],
) -> list[dict[str, str]]:
    return [
        _cutoff_member_payload(member)
        for member in sorted(
            members,
            key=lambda member: (
                member.forecast_cutoff_at.isoformat(),
                member.model_identity,
                member.selection_policy,
                member.forecast_authority_identity,
            ),
        )
    ]


def _diagnostics_payload(
    diagnostics: S3LegalBacktestPackageDiagnostics,
) -> dict[str, Any]:
    return {
        "status": diagnostics.status,
        "blocker_codes": list(diagnostics.blocker_codes),
        "blocker_count": diagnostics.blocker_count,
        "train_source_row_count": diagnostics.train_source_row_count,
        "validation_source_row_count": diagnostics.validation_source_row_count,
        "train_binding_row_count": diagnostics.train_binding_row_count,
        "validation_binding_row_count": diagnostics.validation_binding_row_count,
        "train_comparable_row_count": diagnostics.train_comparable_row_count,
        "validation_comparable_row_count": diagnostics.validation_comparable_row_count,
        "cutoff_member_count": diagnostics.cutoff_member_count,
        "cross_partition_row_overlap_count": diagnostics.cross_partition_row_overlap_count,
        "test_row_count": diagnostics.test_row_count,
        "test_partition_status": diagnostics.test_partition_status,
        "generic_artifact_requirement": diagnostics.generic_artifact_requirement,
    }


def build_s3_legal_backtest_package_semantic_payload(
    package: S3LegalBacktestPackage,
    *,
    package_identity_sha256: str = "",
    canonical_hash_sha256: str = "",
) -> dict[str, Any]:
    """Return the complete two-stage package semantic payload."""

    return {
        "schema_version": package.schema_version,
        "package_identity_sha256": package_identity_sha256,
        "canonical_hash_sha256": canonical_hash_sha256,
        "source_dataset_identity": _source_dataset_payload(package.source_dataset_identity),
        "train_partition_identity": _partition_identity_payload(package.train_partition_identity),
        "validation_partition_identity": _partition_identity_payload(
            package.validation_partition_identity
        ),
        "train_pairing_package_identity": package.train_pairing_package_identity,
        "validation_pairing_package_identity": (package.validation_pairing_package_identity),
        "train_authority_record_identity": package.train_authority_record_identity,
        "validation_authority_record_identity": (package.validation_authority_record_identity),
        "train_evaluation_input_identity": package.train_evaluation_input_identity,
        "validation_evaluation_input_identity": (package.validation_evaluation_input_identity),
        "forecast_authority_identity": package.forecast_authority_identity,
        "in_scope_forecast_cutoff_set": _cutoff_set_payload(package.in_scope_forecast_cutoff_set),
        "in_scope_forecast_cutoff_set_identity_sha256": (
            package.in_scope_forecast_cutoff_set_identity_sha256
        ),
        "forecast_cutoff_authority_identity": (package.forecast_cutoff_authority_identity),
        "model_identity": package.model_identity,
        "evaluation_window": dict(package.evaluation_window),
        "point_in_time_visibility_policy": package.point_in_time_visibility_policy,
        "exact_actual_pairing_policy": package.exact_actual_pairing_policy,
        "missing_day_policy": package.missing_day_policy,
        "diagnostics": _diagnostics_payload(package.diagnostics),
        "test_partition_status": package.test_partition_status,
    }


def compute_s3_legal_backtest_package_identity_hashes(
    package: S3LegalBacktestPackage,
) -> tuple[str, str]:
    semantic = build_s3_legal_backtest_package_semantic_payload(package)
    return compute_two_stage_identity_hashes(
        semantic_payload=semantic,
        identity_field="package_identity_sha256",
        canonical_hash_field="canonical_hash_sha256",
    )


def verify_s3_legal_backtest_package_hash_replay(
    package: S3LegalBacktestPackage,
) -> bool:
    semantic = build_s3_legal_backtest_package_semantic_payload(
        package,
        package_identity_sha256=package.package_identity_sha256,
        canonical_hash_sha256="",
    )
    return verify_two_stage_identity_excluded_from_preimage(
        semantic_payload=semantic,
        identity_field="package_identity_sha256",
        canonical_hash_field="canonical_hash_sha256",
        expected_identity=package.package_identity_sha256,
        expected_canonical_hash=package.canonical_hash_sha256,
    )


def _evaluation_input_identity(evaluation_input: S3EvaluationInput) -> str:
    rows = sorted(
        (row for row in evaluation_input.rows),
        key=lambda row: row.forecast_business_key,
    )
    payload = {
        "rows": [
            {
                "forecast_business_key": row.forecast_business_key,
                "actual_physical_key": row.actual_physical_key,
                "stable_actual_identity": row.stable_actual_identity,
                "forecast_value_kg": row.forecast_value_kg,
                "actual_value_kg": row.actual_value_kg,
                "forecast_quantile": row.forecast_quantile,
                "forecast_horizon_days": row.forecast_horizon_days,
                "forecast_target_date": row.forecast_target_date,
                "forecast_cutoff_at": row.forecast_cutoff_at,
                "s2_status": row.s2_status,
                "season_business_key": row.season_business_key,
                "farm_business_key": row.farm_business_key,
                "subfarm_business_key": row.subfarm_business_key,
                "variety_business_key": row.variety_business_key,
                "model_identity": row.model_identity,
                "actual_visibility_timestamp": row.actual_visibility_timestamp,
            }
            for row in rows
        ],
        "s2_run_identity": evaluation_input.s2_run_identity,
        "s2_manifest_identity": evaluation_input.s2_manifest_identity,
        "s2_binding_row_set_hash": evaluation_input.s2_binding_row_set_hash,
        "metric_policy_version": evaluation_input.metric_policy_version,
        "baseline_policy_version": evaluation_input.baseline_policy_version,
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _rows_for_package(
    package: TrainValidationS3BindingPairingPackage | None,
) -> tuple[S3BindingRow, ...]:
    if package is None:
        return ()
    try:
        return tuple(package.evaluation_input.rows)
    except (AttributeError, TypeError):
        return ()


def _has_native_float(rows: Sequence[S3BindingRow]) -> bool:
    for row in rows:
        if isinstance(row, S3BindingRow):
            if isinstance(row.forecast_value_kg, float) or isinstance(row.actual_value_kg, float):
                return True
        else:
            return True
    return False


def _comparable_row_count(rows: Sequence[S3BindingRow]) -> int:
    return sum(1 for row in rows if row.s2_status == _COMPARABLE_STATUS)


def _partition_snapshot_counts(
    official_partitions: OfficialPartitionRows | None,
) -> tuple[int, int]:
    if official_partitions is None:
        return 0, 0
    return len(official_partitions.train_rows), len(official_partitions.validation_rows)


def _validate_partition_snapshot(
    *,
    official_partitions: OfficialPartitionRows | None,
    expected: PartitionIdentity,
    expected_row_count: int,
    partition: Literal["TRAIN", "VALIDATION"],
    blockers: set[S3LegalBacktestPackageBlocker],
) -> None:
    if official_partitions is None:
        blockers.add(
            S3LegalBacktestPackageBlocker.TRAIN_PARTITION_IDENTITY_MISMATCH
            if partition == "TRAIN"
            else S3LegalBacktestPackageBlocker.VALIDATION_PARTITION_IDENTITY_MISMATCH
        )
        return
    rows = (
        official_partitions.train_rows
        if partition == "TRAIN"
        else official_partitions.validation_rows
    )
    declared_content = (
        official_partitions.train_content_sha256
        if partition == "TRAIN"
        else official_partitions.validation_content_sha256
    )
    if len(rows) != expected_row_count or declared_content != expected.content_sha256:
        blockers.add(
            S3LegalBacktestPackageBlocker.TRAIN_PARTITION_IDENTITY_MISMATCH
            if partition == "TRAIN"
            else S3LegalBacktestPackageBlocker.VALIDATION_PARTITION_IDENTITY_MISMATCH
        )
        return
    if rows:
        dates = [row.harvest_business_date for row in rows]
        if min(dates) != expected.partition_start_date or max(dates) != expected.partition_end_date:
            blockers.add(
                S3LegalBacktestPackageBlocker.TRAIN_PARTITION_IDENTITY_MISMATCH
                if partition == "TRAIN"
                else S3LegalBacktestPackageBlocker.VALIDATION_PARTITION_IDENTITY_MISMATCH
            )
    if any(isinstance(row.actual_harvest_quantity_kg, float) for row in rows):
        blockers.add(S3LegalBacktestPackageBlocker.NATIVE_FLOAT_FORBIDDEN)


def _validate_pairing_package(
    *,
    package: TrainValidationS3BindingPairingPackage | None,
    evaluation_input: S3EvaluationInput | None,
    expected_partition: Literal["TRAIN", "VALIDATION"],
    blockers: set[S3LegalBacktestPackageBlocker],
) -> tuple[S3BindingRow, ...]:
    missing_code = (
        S3LegalBacktestPackageBlocker.TRAIN_PAIRING_PACKAGE_MISSING
        if expected_partition == "TRAIN"
        else S3LegalBacktestPackageBlocker.VALIDATION_PAIRING_PACKAGE_MISSING
    )
    invalid_code = (
        S3LegalBacktestPackageBlocker.TRAIN_PAIRING_PACKAGE_IDENTITY_INVALID
        if expected_partition == "TRAIN"
        else S3LegalBacktestPackageBlocker.VALIDATION_PAIRING_PACKAGE_IDENTITY_INVALID
    )
    if package is None:
        blockers.add(missing_code)
        return ()
    try:
        raw_rows = tuple(package.evaluation_input.rows)
        if _has_native_float(raw_rows):
            blockers.add(S3LegalBacktestPackageBlocker.NATIVE_FLOAT_FORBIDDEN)
        if package.partition != expected_partition:
            blockers.add(
                S3LegalBacktestPackageBlocker.TRAIN_PARTITION_IDENTITY_MISMATCH
                if expected_partition == "TRAIN"
                else S3LegalBacktestPackageBlocker.VALIDATION_PARTITION_IDENTITY_MISMATCH
            )
        expected_identity = (
            ACCEPTED_TRAIN_PARTITION_IDENTITY
            if expected_partition == "TRAIN"
            else ACCEPTED_VALIDATION_PARTITION_IDENTITY
        )
        if package.partition_identity != expected_identity:
            blockers.add(
                S3LegalBacktestPackageBlocker.TRAIN_PARTITION_IDENTITY_MISMATCH
                if expected_partition == "TRAIN"
                else S3LegalBacktestPackageBlocker.VALIDATION_PARTITION_IDENTITY_MISMATCH
            )
        if package.source_dataset_identity != ACCEPTED_SOURCE_DATASET_IDENTITY:
            blockers.add(S3LegalBacktestPackageBlocker.SOURCE_DATASET_IDENTITY_MISMATCH)
        if not verify_pairing_package_hash_replay(package):
            blockers.add(invalid_code)
        try:
            validate_published_pairing_package_invariants(package)
        except Exception:
            blockers.add(invalid_code)
        package_input = package.evaluation_input
        if evaluation_input is not None:
            if package_input.s2_binding_row_set_hash != evaluation_input.s2_binding_row_set_hash:
                blockers.add(S3LegalBacktestPackageBlocker.S2_BINDING_ROW_SET_HASH_MISMATCH)
        for field_name in (
            "s2_run_identity",
            "s2_manifest_identity",
            "s2_binding_row_set_hash",
        ):
            if getattr(package, field_name) != getattr(package_input, field_name):
                blockers.add(S3LegalBacktestPackageBlocker.S2_BINDING_ROW_SET_HASH_MISMATCH)
        if not _is_sha256(package.s2_binding_row_set_hash):
            blockers.add(invalid_code)
        rows = tuple(package_input.rows)
        try:
            if compute_s3_binding_row_set_hash(rows) != package.s2_binding_row_set_hash:
                blockers.add(S3LegalBacktestPackageBlocker.S2_BINDING_ROW_SET_HASH_MISMATCH)
        except Exception:
            if _has_native_float(rows):
                blockers.add(S3LegalBacktestPackageBlocker.NATIVE_FLOAT_FORBIDDEN)
            else:
                blockers.add(invalid_code)
    except Exception:
        blockers.add(invalid_code)
        return ()
    if _has_native_float(rows):
        blockers.add(S3LegalBacktestPackageBlocker.NATIVE_FLOAT_FORBIDDEN)
    return rows


def _authority_is_missing(
    authority: TrainValidationCoveragePartitionAuthority | None,
) -> bool:
    if authority is None:
        return True
    return not isinstance(authority, TrainValidationCoveragePartitionAuthority)


def _validate_authority(
    *,
    authority: TrainValidationCoveragePartitionAuthority | None,
    evaluation_input: S3EvaluationInput | None,
    package: TrainValidationS3BindingPairingPackage | None,
    expected_partition: Literal["TRAIN", "VALIDATION"],
    context: _LegalBacktestAuthorityContext,
    blockers: set[S3LegalBacktestPackageBlocker],
) -> None:
    missing_code = (
        S3LegalBacktestPackageBlocker.TRAIN_AUTHORITY_RECORD_MISSING
        if expected_partition == "TRAIN"
        else S3LegalBacktestPackageBlocker.VALIDATION_AUTHORITY_RECORD_MISSING
    )
    untrusted_code = (
        S3LegalBacktestPackageBlocker.TRAIN_AUTHORITY_NOT_TRUSTED
        if expected_partition == "TRAIN"
        else S3LegalBacktestPackageBlocker.VALIDATION_AUTHORITY_NOT_TRUSTED
    )
    if _authority_is_missing(authority):
        blockers.add(missing_code)
        return
    if package is None or evaluation_input is None:
        blockers.add(untrusted_code)
        return
    assert authority is not None
    try:
        reason = verify_train_validation_coverage_authority(
            evaluation_input,
            authority,
            published_registry=context.published_registry,
            issued_registry=context.issued_registry,
            issued_schema_versions=context.issued_schema_versions,
        )
    except Exception:
        reason = "AUTHORITY_VERIFICATION_ERROR"
    if reason is not None:
        if reason == "TRAIN_VALIDATION_AUTHORITY_RECORD_IDENTITY_MISSING":
            blockers.add(missing_code)
        else:
            blockers.add(untrusted_code)
    if authority.pairing_package_identity != package.pairing_package_identity:
        blockers.add(untrusted_code)
    if authority.s2_binding_row_set_hash != package.s2_binding_row_set_hash:
        blockers.add(S3LegalBacktestPackageBlocker.S2_BINDING_ROW_SET_HASH_MISMATCH)
        blockers.add(untrusted_code)
    if tuple(authority.permitted_partitions) != (expected_partition,):
        blockers.add(untrusted_code)
    if "TEST" in tuple(authority.permitted_partitions):
        blockers.add(S3LegalBacktestPackageBlocker.TEST_PARTITION_PRESENT)


def _row_identity(row: S3BindingRow) -> tuple[Any, ...]:
    return (
        row.season_business_key,
        row.farm_business_key,
        row.subfarm_business_key,
        row.variety_business_key,
        row.forecast_target_date,
        row.forecast_cutoff_at,
        row.model_identity,
        row.forecast_quantile,
        row.forecast_horizon_days,
        row.forecast_business_key,
    )


def _validate_actual_pairing(
    rows: Sequence[S3BindingRow],
    blockers: set[S3LegalBacktestPackageBlocker],
) -> None:
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        if not isinstance(row, S3BindingRow):
            blockers.add(S3LegalBacktestPackageBlocker.MISSING_EXACT_ACTUAL_PAIRING)
            continue
        identity = _row_identity(row)
        if identity in seen:
            blockers.add(S3LegalBacktestPackageBlocker.MISSING_EXACT_ACTUAL_PAIRING)
        seen.add(identity)
        if row.s2_status != _COMPARABLE_STATUS:
            continue
        if (
            row.actual_physical_key is None
            or row.stable_actual_identity is None
            or row.actual_value_kg is None
        ):
            blockers.add(S3LegalBacktestPackageBlocker.MISSING_EXACT_ACTUAL_PAIRING)
            continue
        if not hasattr(row.actual_value_kg, "is_finite"):
            blockers.add(S3LegalBacktestPackageBlocker.MISSING_EXACT_ACTUAL_PAIRING)
        elif not row.actual_value_kg.is_finite():
            blockers.add(S3LegalBacktestPackageBlocker.MISSING_EXACT_ACTUAL_PAIRING)


def _validate_forecast_binding_and_pit(
    *,
    rows: Sequence[S3BindingRow],
    cutoff_members: Sequence[S3LegalBacktestForecastCutoff],
    forecast_cutoff_authority_identity: str,
    model_identity: str,
    blockers: set[S3LegalBacktestPackageBlocker],
) -> None:
    member_keys = {
        (
            member.forecast_cutoff_at,
            member.model_identity,
            member.forecast_authority_identity,
        )
        for member in cutoff_members
    }
    for row in rows:
        if not isinstance(row, S3BindingRow) or row.s2_status != _COMPARABLE_STATUS:
            continue
        if (
            row.forecast_value_kg is None
            or not isinstance(row.forecast_business_key, str)
            or not row.forecast_business_key
            or not isinstance(row.forecast_cutoff_at, datetime)
            or row.forecast_cutoff_at.tzinfo is None
            or not row.model_identity
        ):
            blockers.add(S3LegalBacktestPackageBlocker.MISSING_EXACT_FORECAST_BINDING_AUTHORITY)
            continue
        if row.model_identity != model_identity:
            blockers.add(S3LegalBacktestPackageBlocker.FORECAST_VALUE_NOT_PIT_VISIBLE)
        if (
            row.forecast_cutoff_at,
            row.model_identity,
            forecast_cutoff_authority_identity,
        ) not in member_keys:
            blockers.add(S3LegalBacktestPackageBlocker.FORECAST_VALUE_NOT_PIT_VISIBLE)


def _validate_cross_partition_overlap(
    *,
    materialization: TrainValidationPairingMaterializationResult | None,
    train_rows: Sequence[S3BindingRow],
    validation_rows: Sequence[S3BindingRow],
) -> int:
    declared = materialization.cross_partition_row_count if materialization else 0
    train_physical = {
        row.actual_physical_key
        for row in train_rows
        if isinstance(row, S3BindingRow) and row.actual_physical_key is not None
    }
    validation_physical = {
        row.actual_physical_key
        for row in validation_rows
        if isinstance(row, S3BindingRow) and row.actual_physical_key is not None
    }
    train_stable = {
        row.stable_actual_identity
        for row in train_rows
        if isinstance(row, S3BindingRow) and row.stable_actual_identity is not None
    }
    validation_stable = {
        row.stable_actual_identity
        for row in validation_rows
        if isinstance(row, S3BindingRow) and row.stable_actual_identity is not None
    }
    return max(
        declared,
        len(train_physical & validation_physical),
        len(train_stable & validation_stable),
    )


def _validate_generic_artifact_requirement(
    requirement: S3GenericIncumbentForecastArtifactRequirement,
    blockers: set[S3LegalBacktestPackageBlocker],
) -> None:
    if not isinstance(requirement, S3GenericIncumbentForecastArtifactRequirement):
        blockers.add(
            S3LegalBacktestPackageBlocker.GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIREMENT_UNRESOLVED
        )
        return
    if requirement.requirement == GenericIncumbentForecastArtifactRequirement.UNRESOLVED_BLOCKING:
        blockers.add(
            S3LegalBacktestPackageBlocker.GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIREMENT_UNRESOLVED
        )
    elif requirement.requirement == GenericIncumbentForecastArtifactRequirement.REQUIRED_TRUE:
        identities = (
            requirement.artifact_identity_sha256,
            requirement.binding_identity_sha256,
            requirement.provenance_identity_sha256,
        )
        if (
            not all(_is_sha256(identity) for identity in identities)
            or requirement.replay_verified is not True
        ):
            blockers.add(
                S3LegalBacktestPackageBlocker.GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIRED_BUT_NOT_AVAILABLE
            )
    elif requirement.requirement != GenericIncumbentForecastArtifactRequirement.REQUIRED_FALSE:
        blockers.add(
            S3LegalBacktestPackageBlocker.GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIREMENT_UNRESOLVED
        )


def _validate_cutoff_set(
    *,
    members: tuple[S3LegalBacktestForecastCutoff, ...],
    declared_identity: str,
    identity_matches: bool,
    complete: bool,
    blockers: set[S3LegalBacktestPackageBlocker],
) -> None:
    if not members:
        blockers.add(S3LegalBacktestPackageBlocker.HISTORICAL_CUTOFF_SET_EMPTY)
    if not identity_matches or not _is_sha256(declared_identity):
        blockers.add(S3LegalBacktestPackageBlocker.HISTORICAL_CUTOFF_SET_IDENTITY_MISMATCH)
    member_keys = [
        (
            member.forecast_cutoff_at,
            member.model_identity,
            member.selection_policy,
            member.forecast_authority_identity,
        )
        for member in members
    ]
    if len(member_keys) != len(set(member_keys)):
        blockers.add(S3LegalBacktestPackageBlocker.HISTORICAL_CUTOFF_SET_IDENTITY_MISMATCH)
    if not complete:
        blockers.add(S3LegalBacktestPackageBlocker.HISTORICAL_CUTOFF_SET_INCOMPLETE)


@dataclass(frozen=True, slots=True)
class _LegalBacktestAuthorityContext:
    published_registry: TrustedPublishedPairingPackageRegistry
    issued_registry: TrustedIssuedAuthorityRegistry
    issued_schema_versions: frozenset[str]
    cutoff_set_complete: bool
    generic_artifact_requirement: S3GenericIncumbentForecastArtifactRequirement


_PRODUCTION_AUTHORITY_CONTEXT = _LegalBacktestAuthorityContext(
    published_registry=PRODUCTION_TRUSTED_PUBLISHED_PAIRING_PACKAGE_REGISTRY,
    issued_registry=PRODUCTION_TRUSTED_ISSUED_AUTHORITY_REGISTRY,
    issued_schema_versions=_ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSIONS,
    cutoff_set_complete=False,
    generic_artifact_requirement=S3GenericIncumbentForecastArtifactRequirement(
        requirement=GenericIncumbentForecastArtifactRequirement.UNRESOLVED_BLOCKING
    ),
)


def _build_diagnostics(
    *,
    blockers: set[S3LegalBacktestPackageBlocker],
    official_partitions: OfficialPartitionRows | None,
    train_rows: Sequence[S3BindingRow],
    validation_rows: Sequence[S3BindingRow],
    cutoff_member_count: int,
    cross_partition_overlap_count: int,
    test_row_count: int,
    test_partition_status: str,
    generic_requirement: S3GenericIncumbentForecastArtifactRequirement,
) -> S3LegalBacktestPackageDiagnostics:
    blocker_codes = _ordered_blockers(blockers)
    status = (
        S3LegalBacktestPackageStatus.LEGAL
        if not blocker_codes
        else S3LegalBacktestPackageStatus.BLOCKED
    )
    train_source_count, validation_source_count = _partition_snapshot_counts(official_partitions)
    return S3LegalBacktestPackageDiagnostics(
        status=status,
        blocker_codes=blocker_codes,
        blocker_count=len(blocker_codes),
        train_source_row_count=train_source_count,
        validation_source_row_count=validation_source_count,
        train_binding_row_count=len(train_rows),
        validation_binding_row_count=len(validation_rows),
        train_comparable_row_count=_comparable_row_count(train_rows),
        validation_comparable_row_count=_comparable_row_count(validation_rows),
        cutoff_member_count=cutoff_member_count,
        cross_partition_row_overlap_count=cross_partition_overlap_count,
        test_row_count=test_row_count,
        test_partition_status=test_partition_status,
        generic_artifact_requirement=generic_requirement.requirement.value,
    )


def _build_package(
    *,
    train_package: TrainValidationS3BindingPairingPackage,
    validation_package: TrainValidationS3BindingPairingPackage,
    train_authority: TrainValidationCoveragePartitionAuthority,
    validation_authority: TrainValidationCoveragePartitionAuthority,
    train_input: S3EvaluationInput,
    validation_input: S3EvaluationInput,
    cutoff_members: tuple[S3LegalBacktestForecastCutoff, ...],
    cutoff_identity: str,
    diagnostics: S3LegalBacktestPackageDiagnostics,
    test_partition_status: str,
) -> S3LegalBacktestPackage:
    package = S3LegalBacktestPackage(
        schema_version=S3_LEGAL_BACKTEST_PACKAGE_SCHEMA_VERSION,
        package_identity_sha256="",
        canonical_hash_sha256="",
        source_dataset_identity=ACCEPTED_SOURCE_DATASET_IDENTITY,
        train_partition_identity=ACCEPTED_TRAIN_PARTITION_IDENTITY,
        validation_partition_identity=ACCEPTED_VALIDATION_PARTITION_IDENTITY,
        train_pairing_package_identity=train_package.pairing_package_identity,
        validation_pairing_package_identity=validation_package.pairing_package_identity,
        train_authority_record_identity=train_authority.authority_record_identity,
        validation_authority_record_identity=validation_authority.authority_record_identity,
        train_evaluation_input_identity=_evaluation_input_identity(train_input),
        validation_evaluation_input_identity=_evaluation_input_identity(validation_input),
        forecast_authority_identity=train_package.forecast_authority_identity,
        in_scope_forecast_cutoff_set=cutoff_members,
        in_scope_forecast_cutoff_set_identity_sha256=cutoff_identity,
        forecast_cutoff_authority_identity=(train_package.forecast_cutoff_authority_identity),
        model_identity=REVIEWED_MODEL_ID,
        evaluation_window={
            "partition_policy": "SOURCE_002_TRAIN_THEN_VALIDATION",
            "train_start_date": ACCEPTED_TRAIN_PARTITION_IDENTITY.partition_start_date.isoformat(),
            "train_end_date": ACCEPTED_TRAIN_PARTITION_IDENTITY.partition_end_date.isoformat(),
            "validation_start_date": (
                ACCEPTED_VALIDATION_PARTITION_IDENTITY.partition_start_date.isoformat()
            ),
            "validation_end_date": (
                ACCEPTED_VALIDATION_PARTITION_IDENTITY.partition_end_date.isoformat()
            ),
        },
        point_in_time_visibility_policy=POINT_IN_TIME_VISIBILITY_POLICY,
        exact_actual_pairing_policy=EXACT_ACTUAL_PAIRING_POLICY_V1,
        missing_day_policy=MISSING_DAY_POLICY_UNKNOWN_NOT_ZERO,
        diagnostics=diagnostics,
        test_partition_status=test_partition_status,
    )
    identity, canonical_hash = compute_s3_legal_backtest_package_identity_hashes(package)
    return S3LegalBacktestPackage(
        schema_version=package.schema_version,
        package_identity_sha256=identity,
        canonical_hash_sha256=canonical_hash,
        source_dataset_identity=package.source_dataset_identity,
        train_partition_identity=package.train_partition_identity,
        validation_partition_identity=package.validation_partition_identity,
        train_pairing_package_identity=package.train_pairing_package_identity,
        validation_pairing_package_identity=package.validation_pairing_package_identity,
        train_authority_record_identity=package.train_authority_record_identity,
        validation_authority_record_identity=package.validation_authority_record_identity,
        train_evaluation_input_identity=package.train_evaluation_input_identity,
        validation_evaluation_input_identity=package.validation_evaluation_input_identity,
        forecast_authority_identity=package.forecast_authority_identity,
        in_scope_forecast_cutoff_set=package.in_scope_forecast_cutoff_set,
        in_scope_forecast_cutoff_set_identity_sha256=(
            package.in_scope_forecast_cutoff_set_identity_sha256
        ),
        forecast_cutoff_authority_identity=package.forecast_cutoff_authority_identity,
        model_identity=package.model_identity,
        evaluation_window=package.evaluation_window,
        point_in_time_visibility_policy=package.point_in_time_visibility_policy,
        exact_actual_pairing_policy=package.exact_actual_pairing_policy,
        missing_day_policy=package.missing_day_policy,
        diagnostics=package.diagnostics,
        test_partition_status=package.test_partition_status,
    )


def _build_s3_legal_backtest_package_with_context(
    *,
    pairing_materialization: TrainValidationPairingMaterializationResult | None,
    train_partition_authority: TrainValidationCoveragePartitionAuthority | None,
    validation_partition_authority: TrainValidationCoveragePartitionAuthority | None,
    forecast_cutoff_set: S3LegalBacktestForecastCutoffSet | Sequence[S3LegalBacktestForecastCutoff],
    context: _LegalBacktestAuthorityContext,
    test_partition_status: str = TEST_PARTITION_STATUS_SEALED_ABSENT,
) -> S3LegalBacktestPackageResult:
    """Internal constructor used by the production wrapper and unit fixtures."""

    blockers: set[S3LegalBacktestPackageBlocker] = set()
    materialization = pairing_materialization
    train_package = materialization.train_pairing_package if materialization else None
    validation_package = materialization.validation_pairing_package if materialization else None
    train_input = materialization.train_evaluation_input if materialization else None
    validation_input = materialization.validation_evaluation_input if materialization else None

    if materialization is not None and (
        not materialization.completed
        or materialization.blocker is not TrainValidationPairingMaterializationBlocker.NONE
    ):
        blockers.add(S3LegalBacktestPackageBlocker.TRAIN_PAIRING_PACKAGE_IDENTITY_INVALID)
        blockers.add(S3LegalBacktestPackageBlocker.VALIDATION_PAIRING_PACKAGE_IDENTITY_INVALID)
    train_rows = _validate_pairing_package(
        package=train_package,
        evaluation_input=train_input,
        expected_partition="TRAIN",
        blockers=blockers,
    )
    validation_rows = _validate_pairing_package(
        package=validation_package,
        evaluation_input=validation_input,
        expected_partition="VALIDATION",
        blockers=blockers,
    )

    _validate_partition_snapshot(
        official_partitions=materialization.official_partitions if materialization else None,
        expected=ACCEPTED_TRAIN_PARTITION_IDENTITY,
        expected_row_count=OFFICIAL_TRAIN_ROW_COUNT,
        partition="TRAIN",
        blockers=blockers,
    )
    _validate_partition_snapshot(
        official_partitions=materialization.official_partitions if materialization else None,
        expected=ACCEPTED_VALIDATION_PARTITION_IDENTITY,
        expected_row_count=OFFICIAL_VALIDATION_ROW_COUNT,
        partition="VALIDATION",
        blockers=blockers,
    )

    if test_partition_status != TEST_PARTITION_STATUS_SEALED_ABSENT:
        blockers.add(S3LegalBacktestPackageBlocker.TEST_NOT_SEALED)
    if materialization is not None and materialization.test_row_count:
        blockers.add(S3LegalBacktestPackageBlocker.TEST_PARTITION_PRESENT)

    _validate_authority(
        authority=train_partition_authority,
        evaluation_input=train_package.evaluation_input if train_package else train_input,
        package=train_package,
        expected_partition="TRAIN",
        context=context,
        blockers=blockers,
    )
    _validate_authority(
        authority=validation_partition_authority,
        evaluation_input=validation_package.evaluation_input
        if validation_package
        else validation_input,
        package=validation_package,
        expected_partition="VALIDATION",
        context=context,
        blockers=blockers,
    )

    if (
        train_package is not None
        and validation_package is not None
        and train_package.forecast_authority_identity
        != validation_package.forecast_authority_identity
    ):
        blockers.add(S3LegalBacktestPackageBlocker.MISSING_EXACT_FORECAST_BINDING_AUTHORITY)
    if (
        train_package is not None
        and validation_package is not None
        and train_package.forecast_cutoff_authority_identity
        != validation_package.forecast_cutoff_authority_identity
    ):
        blockers.add(S3LegalBacktestPackageBlocker.MISSING_EXACT_FORECAST_BINDING_AUTHORITY)

    overlap_count = _validate_cross_partition_overlap(
        materialization=materialization,
        train_rows=train_rows,
        validation_rows=validation_rows,
    )
    if overlap_count:
        blockers.add(S3LegalBacktestPackageBlocker.CROSS_PARTITION_ROW_OVERLAP)

    _validate_actual_pairing(train_rows, blockers)
    _validate_actual_pairing(validation_rows, blockers)

    try:
        cutoff_members, cutoff_identity, cutoff_identity_matches = _normalize_cutoff_set(
            forecast_cutoff_set
        )
    except Exception:
        cutoff_members, cutoff_identity, cutoff_identity_matches = (), "", False
    _validate_cutoff_set(
        members=cutoff_members,
        declared_identity=cutoff_identity,
        identity_matches=cutoff_identity_matches,
        complete=context.cutoff_set_complete,
        blockers=blockers,
    )

    forecast_cutoff_authority_identity = (
        train_package.forecast_cutoff_authority_identity if train_package is not None else ""
    )
    _validate_forecast_binding_and_pit(
        rows=tuple(train_rows) + tuple(validation_rows),
        cutoff_members=cutoff_members,
        forecast_cutoff_authority_identity=forecast_cutoff_authority_identity,
        model_identity=REVIEWED_MODEL_ID,
        blockers=blockers,
    )
    _validate_generic_artifact_requirement(context.generic_artifact_requirement, blockers)

    diagnostics = _build_diagnostics(
        blockers=blockers,
        official_partitions=materialization.official_partitions if materialization else None,
        train_rows=train_rows,
        validation_rows=validation_rows,
        cutoff_member_count=len(cutoff_members),
        cross_partition_overlap_count=overlap_count,
        test_row_count=materialization.test_row_count if materialization else 0,
        test_partition_status=test_partition_status,
        generic_requirement=context.generic_artifact_requirement,
    )
    if blockers or train_package is None or validation_package is None:
        return S3LegalBacktestPackageResult(
            status=S3LegalBacktestPackageStatus.BLOCKED,
            package=None,
            diagnostics=diagnostics,
        )

    train_input = train_package.evaluation_input
    validation_input = validation_package.evaluation_input
    assert train_partition_authority is not None
    assert validation_partition_authority is not None
    package = _build_package(
        train_package=train_package,
        validation_package=validation_package,
        train_authority=train_partition_authority,
        validation_authority=validation_partition_authority,
        train_input=train_input,
        validation_input=validation_input,
        cutoff_members=cutoff_members,
        cutoff_identity=cutoff_identity,
        diagnostics=diagnostics,
        test_partition_status=test_partition_status,
    )
    if not verify_s3_legal_backtest_package_hash_replay(package):
        final_diagnostics = S3LegalBacktestPackageDiagnostics(
            status=S3LegalBacktestPackageStatus.BLOCKED,
            blocker_codes=(S3LegalBacktestPackageBlocker.PACKAGE_CANONICAL_HASH_MISMATCH.value,),
            blocker_count=1,
            train_source_row_count=diagnostics.train_source_row_count,
            validation_source_row_count=diagnostics.validation_source_row_count,
            train_binding_row_count=diagnostics.train_binding_row_count,
            validation_binding_row_count=diagnostics.validation_binding_row_count,
            train_comparable_row_count=diagnostics.train_comparable_row_count,
            validation_comparable_row_count=diagnostics.validation_comparable_row_count,
            cutoff_member_count=diagnostics.cutoff_member_count,
            cross_partition_row_overlap_count=diagnostics.cross_partition_row_overlap_count,
            test_row_count=diagnostics.test_row_count,
            test_partition_status=diagnostics.test_partition_status,
            generic_artifact_requirement=diagnostics.generic_artifact_requirement,
        )
        return S3LegalBacktestPackageResult(
            status=S3LegalBacktestPackageStatus.BLOCKED,
            package=None,
            diagnostics=final_diagnostics,
        )
    return S3LegalBacktestPackageResult(
        status=S3LegalBacktestPackageStatus.LEGAL,
        package=package,
        diagnostics=diagnostics,
    )


def _build_s3_legal_backtest_package_with_registries(
    *,
    pairing_materialization: TrainValidationPairingMaterializationResult,
    train_partition_authority: TrainValidationCoveragePartitionAuthority | None,
    validation_partition_authority: TrainValidationCoveragePartitionAuthority | None,
    forecast_cutoff_set: S3LegalBacktestForecastCutoffSet | Sequence[S3LegalBacktestForecastCutoff],
    published_registry: TrustedPublishedPairingPackageRegistry,
    issued_registry: TrustedIssuedAuthorityRegistry,
    issued_schema_versions: frozenset[str],
    cutoff_set_complete: bool = True,
    generic_artifact_requirement: S3GenericIncumbentForecastArtifactRequirement | None = None,
    test_partition_status: str = TEST_PARTITION_STATUS_SEALED_ABSENT,
) -> S3LegalBacktestPackageResult:
    """Test-only in-memory authority context for hypothetical legal paths."""

    context = _LegalBacktestAuthorityContext(
        published_registry=published_registry,
        issued_registry=issued_registry,
        issued_schema_versions=issued_schema_versions,
        cutoff_set_complete=cutoff_set_complete,
        generic_artifact_requirement=generic_artifact_requirement
        or S3GenericIncumbentForecastArtifactRequirement(
            requirement=GenericIncumbentForecastArtifactRequirement.REQUIRED_FALSE
        ),
    )
    return _build_s3_legal_backtest_package_with_context(
        pairing_materialization=pairing_materialization,
        train_partition_authority=train_partition_authority,
        validation_partition_authority=validation_partition_authority,
        forecast_cutoff_set=forecast_cutoff_set,
        context=context,
        test_partition_status=test_partition_status,
    )


def build_s3_legal_backtest_package(
    *,
    pairing_materialization: TrainValidationPairingMaterializationResult | None = None,
    train_materialization: TrainValidationPairingMaterializationResult | None = None,
    validation_materialization: TrainValidationPairingMaterializationResult | None = None,
    train_partition_authority: TrainValidationCoveragePartitionAuthority | None = None,
    validation_partition_authority: TrainValidationCoveragePartitionAuthority | None = None,
    forecast_cutoff_set: S3LegalBacktestForecastCutoffSet
    | Sequence[S3LegalBacktestForecastCutoff] = (),
    test_partition_status: str = TEST_PARTITION_STATUS_SEALED_ABSENT,
) -> S3LegalBacktestPackageResult:
    """Build a production legal-package result using only trusted registries.

    The current production context intentionally has no issued partition
    authority schema versions and no complete cutoff-set authority.  Therefore
    this entry point is expected to return BLOCKED until those independent
    gates are resolved.  The compatibility materialization names accept the
    current combined result without inventing a second producer result.
    """

    combined = pairing_materialization
    if combined is None:
        if (
            train_materialization is not None
            and validation_materialization is not None
            and train_materialization is validation_materialization
        ):
            combined = train_materialization
        elif train_materialization is not None and validation_materialization is None:
            combined = train_materialization
        elif validation_materialization is not None and train_materialization is None:
            combined = validation_materialization
    return _build_s3_legal_backtest_package_with_context(
        pairing_materialization=combined,
        train_partition_authority=train_partition_authority,
        validation_partition_authority=validation_partition_authority,
        forecast_cutoff_set=forecast_cutoff_set,
        context=_PRODUCTION_AUTHORITY_CONTEXT,
        test_partition_status=test_partition_status,
    )


__all__ = [
    "FORECAST_SELECTION_POLICY",
    "GenericIncumbentForecastArtifactRequirement",
    "LEGAL_BACKTEST_PACKAGE_STATUS_VALUES",
    "MISSING_DAY_POLICY_UNKNOWN_NOT_ZERO",
    "POINT_IN_TIME_VISIBILITY_POLICY",
    "REVIEWED_MODEL_ID",
    "S3GenericIncumbentForecastArtifactRequirement",
    "S3LegalBacktestForecastCutoff",
    "S3LegalBacktestForecastCutoffSet",
    "S3LegalBacktestPackage",
    "S3LegalBacktestPackageBlocker",
    "S3LegalBacktestPackageDiagnostics",
    "S3LegalBacktestPackageResult",
    "S3LegalBacktestPackageStatus",
    "S3_LEGAL_BACKTEST_PACKAGE_IMPLEMENTATION_VERSION",
    "S3_LEGAL_BACKTEST_PACKAGE_SCHEMA_VERSION",
    "TEST_PARTITION_STATUS_SEALED_ABSENT",
    "build_s3_legal_backtest_package",
    "build_s3_legal_backtest_package_semantic_payload",
    "compute_forecast_cutoff_set_identity_sha256",
    "compute_s3_legal_backtest_package_identity_hashes",
    "verify_s3_legal_backtest_package_hash_replay",
]
