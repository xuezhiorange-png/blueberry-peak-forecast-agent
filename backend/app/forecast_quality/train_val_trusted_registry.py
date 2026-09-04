"""Trusted TRAIN/VALIDATION pairing package and authority registries (contract R1).

Production registries are empty. Verification is fail-closed and registry-backed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from .train_val_pairing import (
    ISSUED_EXACT_ACTUAL_PAIRING_POLICY_VERSIONS,
    TRAIN_VAL_PAIRING_POLICY_V1,
    TrainValidationS3BindingPairingPackage,
    TrainValPairingPackageInvariantError,
    _validate_pairing_package_core_invariants,
    compute_two_stage_identity_hashes,
    verify_pairing_package_hash_replay,
    verify_two_stage_identity_excluded_from_preimage,
)
from .train_val_pairing_policy_registry import (
    PRODUCTION_TRUSTED_ISSUED_PAIRING_POLICY_REGISTRY,
    TrustedIssuedPairingPolicyRegistry,
    verify_issued_pairing_policy,
)

if TYPE_CHECKING:
    from .quantile_coverage import TrainValidationCoveragePartitionAuthority
    from .schemas import S3EvaluationInput

_AUTHORITY_RECORD_IDENTITY_FIELD = "authority_record_identity"
_AUTHORITY_RECORD_CANONICAL_HASH_FIELD = "canonical_hash"

_TRAIN_VAL_SPLITS = frozenset({"TRAIN", "VALIDATION"})

# General pairing policy allowlist populated by dual issuance grant R1.
_ISSUED_PAIRING_POLICY_VERSIONS: frozenset[str] = frozenset({TRAIN_VAL_PAIRING_POLICY_V1})


@dataclass(frozen=True)
class IssuedTrainValidationCoverageAuthorityRecord:
    authority_record_identity: str
    schema_version: str
    pairing_package_identity: str
    s2_binding_row_set_hash: str
    permitted_partitions: tuple[str, ...]
    pairing_policy_version: str
    issuer_identity_or_version: str
    canonical_hash: str


def build_authority_record_semantic_payload(
    record: IssuedTrainValidationCoverageAuthorityRecord,
    *,
    authority_record_identity: str = "",
    canonical_hash: str = "",
) -> dict[str, object]:
    return {
        "authority_record_identity": authority_record_identity,
        "schema_version": record.schema_version,
        "pairing_package_identity": record.pairing_package_identity,
        "s2_binding_row_set_hash": record.s2_binding_row_set_hash,
        "permitted_partitions": list(record.permitted_partitions),
        "pairing_policy_version": record.pairing_policy_version,
        "issuer_identity_or_version": record.issuer_identity_or_version,
        "canonical_hash": canonical_hash,
    }


def compute_authority_record_identity_hashes(
    record: IssuedTrainValidationCoverageAuthorityRecord,
) -> tuple[str, str]:
    semantic = build_authority_record_semantic_payload(record)
    return compute_two_stage_identity_hashes(
        semantic_payload=semantic,
        identity_field=_AUTHORITY_RECORD_IDENTITY_FIELD,
        canonical_hash_field=_AUTHORITY_RECORD_CANONICAL_HASH_FIELD,
    )


def verify_authority_record_hash_replay(
    record: IssuedTrainValidationCoverageAuthorityRecord,
) -> bool:
    semantic = build_authority_record_semantic_payload(
        record,
        authority_record_identity=record.authority_record_identity,
        canonical_hash="",
    )
    return verify_two_stage_identity_excluded_from_preimage(
        semantic_payload=semantic,
        identity_field=_AUTHORITY_RECORD_IDENTITY_FIELD,
        canonical_hash_field=_AUTHORITY_RECORD_CANONICAL_HASH_FIELD,
        expected_identity=record.authority_record_identity,
        expected_canonical_hash=record.canonical_hash,
    )


def _immutable_record_snapshot(records: Mapping[str, object]) -> Mapping[str, object]:
    """Defensive copy wrapped in a read-only mapping proxy."""

    return MappingProxyType(dict(records))


@dataclass(frozen=True)
class TrustedPublishedPairingPackageRegistry:
    """Immutable lookup registry for published pairing packages."""

    _records: Mapping[str, TrainValidationS3BindingPairingPackage]

    def __init__(
        self,
        records: Mapping[str, TrainValidationS3BindingPairingPackage] | None = None,
    ) -> None:
        object.__setattr__(self, "_records", _immutable_record_snapshot(records or {}))

    def lookup(
        self, pairing_package_identity: str
    ) -> TrainValidationS3BindingPairingPackage | None:
        return self._records.get(pairing_package_identity)

    def count(self) -> int:
        return len(self._records)


@dataclass(frozen=True)
class TrustedIssuedAuthorityRegistry:
    """Immutable lookup registry for issued authority records."""

    _records: Mapping[str, IssuedTrainValidationCoverageAuthorityRecord]

    def __init__(
        self,
        records: Mapping[str, IssuedTrainValidationCoverageAuthorityRecord] | None = None,
    ) -> None:
        object.__setattr__(self, "_records", _immutable_record_snapshot(records or {}))

    def lookup(
        self, authority_record_identity: str
    ) -> IssuedTrainValidationCoverageAuthorityRecord | None:
        return self._records.get(authority_record_identity)

    def count(self) -> int:
        return len(self._records)


PRODUCTION_TRUSTED_PUBLISHED_PAIRING_PACKAGE_REGISTRY = TrustedPublishedPairingPackageRegistry()
PRODUCTION_TRUSTED_ISSUED_AUTHORITY_REGISTRY = TrustedIssuedAuthorityRegistry()


def _is_sha256(value: str) -> bool:
    return (
        len(value) == 64
        and value.lower() == value
        and all(char in "0123456789abcdef" for char in value)
    )


def verify_train_validation_coverage_authority(
    evaluation_input: S3EvaluationInput,
    partition_authority: TrainValidationCoveragePartitionAuthority,
    *,
    published_registry: TrustedPublishedPairingPackageRegistry,
    issued_registry: TrustedIssuedAuthorityRegistry,
    issued_schema_versions: frozenset[str],
    issued_pairing_policy_versions: frozenset[str] = _ISSUED_PAIRING_POLICY_VERSIONS,
    issued_exact_actual_pairing_policy_versions: frozenset[str] = (
        ISSUED_EXACT_ACTUAL_PAIRING_POLICY_VERSIONS
    ),
    issued_policy_registry: TrustedIssuedPairingPolicyRegistry = (
        PRODUCTION_TRUSTED_ISSUED_PAIRING_POLICY_REGISTRY
    ),
) -> str | None:
    """Return a blocker reason or None when the full authority chain is proven."""

    if partition_authority.schema_version not in issued_schema_versions:
        return "TRAIN_VALIDATION_PARTITION_AUTHORITY_NOT_ISSUED"

    record_identity = partition_authority.authority_record_identity.strip()
    if not record_identity or not _is_sha256(record_identity):
        return "TRAIN_VALIDATION_AUTHORITY_RECORD_IDENTITY_MISSING"

    issued_record = issued_registry.lookup(record_identity)
    if issued_record is None:
        return "TRAIN_VALIDATION_AUTHORITY_RECORD_NOT_FOUND"

    if not verify_authority_record_hash_replay(issued_record):
        return "TRAIN_VALIDATION_AUTHORITY_RECORD_HASH_MISMATCH"

    if partition_authority.schema_version != issued_record.schema_version:
        return "TRAIN_VALIDATION_AUTHORITY_RECORD_HASH_MISMATCH"

    if partition_authority.pairing_package_identity != issued_record.pairing_package_identity:
        return "TRAIN_VALIDATION_AUTHORITY_RECORD_HASH_MISMATCH"

    if partition_authority.s2_binding_row_set_hash != issued_record.s2_binding_row_set_hash:
        return "TRAIN_VALIDATION_AUTHORITY_RECORD_HASH_MISMATCH"

    if tuple(partition_authority.permitted_partitions) != issued_record.permitted_partitions:
        return "TRAIN_VALIDATION_AUTHORITY_RECORD_HASH_MISMATCH"

    published_package = published_registry.lookup(issued_record.pairing_package_identity)
    if published_package is None:
        return "TRAIN_VALIDATION_PAIRING_PACKAGE_NOT_PUBLISHED"

    if not verify_pairing_package_hash_replay(published_package):
        return "TRAIN_VALIDATION_PAIRING_PACKAGE_HASH_MISMATCH"

    try:
        _validate_pairing_package_core_invariants(published_package)
    except TrainValPairingPackageInvariantError:
        return "TRAIN_VALIDATION_PAIRING_PACKAGE_INVARIANT_VIOLATION"

    exact_policy_version = published_package.exact_actual_pairing_policy_version.strip()
    exact_policy_blocker = verify_issued_pairing_policy(
        exact_policy_version,
        "EXACT_ACTUAL_PAIRING",
        registry=issued_policy_registry,
    )
    if exact_policy_blocker is not None:
        return exact_policy_blocker
    if not exact_policy_version:
        return "TRAIN_VALIDATION_EXACT_ACTUAL_PAIRING_POLICY_NOT_ISSUED"
    if exact_policy_version not in issued_exact_actual_pairing_policy_versions:
        return "TRAIN_VALIDATION_EXACT_ACTUAL_PAIRING_POLICY_NOT_ISSUED"

    if published_package.pairing_package_identity != issued_record.pairing_package_identity:
        return "TRAIN_VALIDATION_PAIRING_PACKAGE_HASH_MISMATCH"

    if published_package.s2_binding_row_set_hash != issued_record.s2_binding_row_set_hash:
        return "TRAIN_VALIDATION_PAIRING_PACKAGE_HASH_MISMATCH"

    if published_package.pairing_policy_version != issued_record.pairing_policy_version:
        return "TRAIN_VALIDATION_PAIRING_POLICY_MISMATCH"

    general_policy_blocker = verify_issued_pairing_policy(
        published_package.pairing_policy_version,
        "TRAIN_VAL_BINDING_PAIRING",
        registry=issued_policy_registry,
    )
    if general_policy_blocker is not None:
        return general_policy_blocker

    if published_package.pairing_policy_version not in issued_pairing_policy_versions:
        return "TRAIN_VALIDATION_PAIRING_POLICY_NOT_ISSUED"

    if evaluation_input.s2_binding_row_set_hash != published_package.s2_binding_row_set_hash:
        return "TRAIN_VALIDATION_PARTITION_AUTHORITY_BINDING_MISMATCH"

    if evaluation_input.s2_binding_row_set_hash != partition_authority.s2_binding_row_set_hash:
        return "TRAIN_VALIDATION_PARTITION_AUTHORITY_BINDING_MISMATCH"

    partitions = frozenset(partition_authority.permitted_partitions)
    if "TEST" in partitions:
        return "TEST_PARTITION_AUTHORITY_FORBIDDEN"
    if not partitions <= _TRAIN_VAL_SPLITS:
        return "NON_TRAIN_VALIDATION_SPLIT_PRESENT"

    if published_package.partition not in partitions:
        return "TRAIN_VALIDATION_PARTITION_AUTHORITY_BINDING_MISMATCH"

    return None


def build_candidate_authority_record(
    *,
    schema_version: str,
    pairing_package_identity: str,
    s2_binding_row_set_hash: str,
    permitted_partitions: tuple[str, ...],
    pairing_policy_version: str = TRAIN_VAL_PAIRING_POLICY_V1,
    issuer_identity_or_version: str,
) -> IssuedTrainValidationCoverageAuthorityRecord:
    """Build a structurally valid authority record without publishing it."""

    candidate = IssuedTrainValidationCoverageAuthorityRecord(
        authority_record_identity="",
        schema_version=schema_version,
        pairing_package_identity=pairing_package_identity,
        s2_binding_row_set_hash=s2_binding_row_set_hash,
        permitted_partitions=permitted_partitions,
        pairing_policy_version=pairing_policy_version,
        issuer_identity_or_version=issuer_identity_or_version,
        canonical_hash="",
    )
    authority_record_identity, canonical_hash = compute_authority_record_identity_hashes(candidate)
    return IssuedTrainValidationCoverageAuthorityRecord(
        authority_record_identity=authority_record_identity,
        schema_version=candidate.schema_version,
        pairing_package_identity=candidate.pairing_package_identity,
        s2_binding_row_set_hash=candidate.s2_binding_row_set_hash,
        permitted_partitions=candidate.permitted_partitions,
        pairing_policy_version=candidate.pairing_policy_version,
        issuer_identity_or_version=candidate.issuer_identity_or_version,
        canonical_hash=canonical_hash,
    )


__all__ = [
    "IssuedTrainValidationCoverageAuthorityRecord",
    "PRODUCTION_TRUSTED_ISSUED_AUTHORITY_REGISTRY",
    "PRODUCTION_TRUSTED_PUBLISHED_PAIRING_PACKAGE_REGISTRY",
    "TrustedIssuedAuthorityRegistry",
    "TrustedPublishedPairingPackageRegistry",
    "build_authority_record_semantic_payload",
    "build_candidate_authority_record",
    "compute_authority_record_identity_hashes",
    "verify_authority_record_hash_replay",
    "verify_train_validation_coverage_authority",
]
