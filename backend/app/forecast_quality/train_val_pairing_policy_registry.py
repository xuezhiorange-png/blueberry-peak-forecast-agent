"""Trusted issued pairing policy registry infrastructure (contract R1).

Production registry is empty. Verification is fail-closed and registry-backed.
Does not issue policies or populate production allowlists.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from .train_val_pairing import (
    EXACT_ACTUAL_PAIRING_POLICY_V1,
    FROZEN_EXACT_ACTUAL_PAIRING_RULE,
    TRAIN_VAL_PAIRING_POLICY_V1,
    compute_two_stage_identity_hashes,
    verify_two_stage_identity_excluded_from_preimage,
)

PolicyKind = Literal["TRAIN_VAL_BINDING_PAIRING", "EXACT_ACTUAL_PAIRING"]

_POLICY_RECORD_IDENTITY_FIELD = "policy_record_identity"
_POLICY_RECORD_CANONICAL_HASH_FIELD = "canonical_hash"

# Canonical contract authority from docs/v0-3/s3/s3-b-pairing-policy-authority-contract.md
PAIRING_POLICY_AUTHORITY_CONTRACT_ID = "V0_3_S3_B_PAIRING_POLICY_AUTHORITY_CONTRACT"
PAIRING_POLICY_AUTHORITY_CONTRACT_VERSION = "v0-3-s3-b-pairing-policy-authority-contract-v1"
PAIRING_POLICY_AUTHORITY_CONTRACT_PATH = "docs/v0-3/s3/s3-b-pairing-policy-authority-contract.md"

GENERAL_PAIRING_POLICY_SEMANTIC_AUTHORITY_SOURCE = PAIRING_POLICY_AUTHORITY_CONTRACT_PATH
GENERAL_PAIRING_POLICY_SEMANTIC_AUTHORITY_ID = PAIRING_POLICY_AUTHORITY_CONTRACT_ID
GENERAL_PAIRING_POLICY_SEMANTIC_AUTHORITY_VERSION = PAIRING_POLICY_AUTHORITY_CONTRACT_VERSION

_CANONICAL_PERMITTED_PARTITIONS: tuple[str, ...] = ("TRAIN", "VALIDATION")

_CANONICAL_SEMANTIC_BY_KIND: dict[PolicyKind, str] = {
    "TRAIN_VAL_BINDING_PAIRING": GENERAL_PAIRING_POLICY_SEMANTIC_AUTHORITY_ID,
    "EXACT_ACTUAL_PAIRING": FROZEN_EXACT_ACTUAL_PAIRING_RULE,
}

_CANONICAL_SEMANTIC_AUTHORITY_VERSION_BY_KIND: dict[PolicyKind, str | None] = {
    "TRAIN_VAL_BINDING_PAIRING": GENERAL_PAIRING_POLICY_SEMANTIC_AUTHORITY_VERSION,
    "EXACT_ACTUAL_PAIRING": None,
}

_CANONICAL_VERSION_BY_KIND: dict[PolicyKind, str] = {
    "TRAIN_VAL_BINDING_PAIRING": TRAIN_VAL_PAIRING_POLICY_V1,
    "EXACT_ACTUAL_PAIRING": EXACT_ACTUAL_PAIRING_POLICY_V1,
}


class TrustedPairingPolicyRegistryConstructionError(ValueError):
    """Raised when trusted policy registry inputs violate contract invariants."""


@dataclass(frozen=True)
class IssuedPairingPolicyRecord:
    policy_record_identity: str
    policy_kind: PolicyKind
    policy_version: str
    semantic_rule_or_authority: str
    semantic_authority_version: str | None
    issuer_identity_or_version: str
    permitted_partitions: tuple[str, ...]
    canonical_hash: str


def build_policy_record_semantic_payload(
    record: IssuedPairingPolicyRecord,
    *,
    policy_record_identity: str = "",
    canonical_hash: str = "",
) -> dict[str, object]:
    return {
        "policy_record_identity": policy_record_identity,
        "policy_kind": record.policy_kind,
        "policy_version": record.policy_version,
        "semantic_rule_or_authority": record.semantic_rule_or_authority,
        "semantic_authority_version": record.semantic_authority_version,
        "issuer_identity_or_version": record.issuer_identity_or_version,
        "permitted_partitions": list(record.permitted_partitions),
        "canonical_hash": canonical_hash,
    }


def compute_policy_record_identity_hashes(
    record: IssuedPairingPolicyRecord,
) -> tuple[str, str]:
    semantic = build_policy_record_semantic_payload(record)
    return compute_two_stage_identity_hashes(
        semantic_payload=semantic,
        identity_field=_POLICY_RECORD_IDENTITY_FIELD,
        canonical_hash_field=_POLICY_RECORD_CANONICAL_HASH_FIELD,
    )


def verify_policy_record_hash_replay(record: IssuedPairingPolicyRecord) -> bool:
    semantic = build_policy_record_semantic_payload(
        record,
        policy_record_identity=record.policy_record_identity,
        canonical_hash="",
    )
    return verify_two_stage_identity_excluded_from_preimage(
        semantic_payload=semantic,
        identity_field=_POLICY_RECORD_IDENTITY_FIELD,
        canonical_hash_field=_POLICY_RECORD_CANONICAL_HASH_FIELD,
        expected_identity=record.policy_record_identity,
        expected_canonical_hash=record.canonical_hash,
    )


def _immutable_record_snapshot[K, V](records: Mapping[K, V]) -> Mapping[K, V]:
    return MappingProxyType(dict(records))


def _canonical_semantic_for_kind(policy_kind: PolicyKind) -> str:
    return _CANONICAL_SEMANTIC_BY_KIND[policy_kind]


def _canonical_semantic_authority_version_for_kind(policy_kind: PolicyKind) -> str | None:
    return _CANONICAL_SEMANTIC_AUTHORITY_VERSION_BY_KIND[policy_kind]


def _canonical_permitted_partitions_for_kind(policy_kind: PolicyKind) -> tuple[str, ...]:
    return _CANONICAL_PERMITTED_PARTITIONS


def _semantic_authority_matches(record: IssuedPairingPolicyRecord) -> bool:
    return record.semantic_rule_or_authority == _canonical_semantic_for_kind(record.policy_kind)


def _semantic_authority_version_matches(record: IssuedPairingPolicyRecord) -> bool:
    return record.semantic_authority_version == _canonical_semantic_authority_version_for_kind(
        record.policy_kind
    )


def _permitted_partitions_match(record: IssuedPairingPolicyRecord) -> bool:
    return tuple(record.permitted_partitions) == _canonical_permitted_partitions_for_kind(
        record.policy_kind
    )


def _validate_registry_inputs(records: Mapping[str, IssuedPairingPolicyRecord]) -> None:
    seen_version_kind: set[tuple[str, PolicyKind]] = set()
    for mapping_key, record in records.items():
        if mapping_key != record.policy_record_identity:
            raise TrustedPairingPolicyRegistryConstructionError(
                "mapping key must equal record policy_record_identity"
            )
        version_kind = (record.policy_version, record.policy_kind)
        if version_kind in seen_version_kind:
            raise TrustedPairingPolicyRegistryConstructionError(
                "duplicate policy_version and policy_kind in registry"
            )
        seen_version_kind.add(version_kind)


@dataclass(frozen=True)
class TrustedIssuedPairingPolicyRegistry:
    """Immutable lookup registry for issued pairing policy records."""

    _records_by_identity: Mapping[str, IssuedPairingPolicyRecord]
    _records_by_version_kind: Mapping[tuple[str, PolicyKind], IssuedPairingPolicyRecord]

    def __init__(
        self,
        records: Mapping[str, IssuedPairingPolicyRecord] | None = None,
    ) -> None:
        snapshot = dict(records or {})
        _validate_registry_inputs(snapshot)
        by_version_kind = {
            (record.policy_version, record.policy_kind): record for record in snapshot.values()
        }
        object.__setattr__(self, "_records_by_identity", _immutable_record_snapshot(snapshot))
        object.__setattr__(
            self,
            "_records_by_version_kind",
            _immutable_record_snapshot(by_version_kind),
        )

    def lookup(self, policy_record_identity: str) -> IssuedPairingPolicyRecord | None:
        return self._records_by_identity.get(policy_record_identity)

    def lookup_by_policy_version(
        self,
        policy_version: str,
        policy_kind: PolicyKind,
    ) -> IssuedPairingPolicyRecord | None:
        record = self._records_by_version_kind.get((policy_version, policy_kind))
        if record is None:
            return None
        if self.lookup(record.policy_record_identity) != record:
            return None
        return record

    def count(self) -> int:
        return len(self._records_by_identity)


PRODUCTION_TRUSTED_ISSUED_PAIRING_POLICY_REGISTRY = TrustedIssuedPairingPolicyRegistry()


def verify_issued_pairing_policy(
    policy_version: str,
    expected_kind: PolicyKind,
    *,
    registry: TrustedIssuedPairingPolicyRegistry,
) -> str | None:
    """Return a blocker reason or None when the policy is registry-proven issued."""

    version = policy_version.strip()
    if not version:
        if expected_kind == "EXACT_ACTUAL_PAIRING":
            return "TRAIN_VALIDATION_EXACT_ACTUAL_PAIRING_POLICY_NOT_ISSUED"
        return "TRAIN_VALIDATION_PAIRING_POLICY_NOT_ISSUED"

    canonical_version = _CANONICAL_VERSION_BY_KIND.get(expected_kind)
    if canonical_version is None or version != canonical_version:
        if expected_kind == "EXACT_ACTUAL_PAIRING":
            return "TRAIN_VALIDATION_EXACT_ACTUAL_PAIRING_POLICY_NOT_ISSUED"
        return "TRAIN_VALIDATION_PAIRING_POLICY_NOT_ISSUED"

    record = registry.lookup_by_policy_version(version, expected_kind)
    if record is None:
        if expected_kind == "EXACT_ACTUAL_PAIRING":
            return "TRAIN_VALIDATION_EXACT_ACTUAL_PAIRING_POLICY_NOT_ISSUED"
        return "TRAIN_VALIDATION_PAIRING_POLICY_NOT_ISSUED"

    if not verify_policy_record_hash_replay(record):
        return "TRAIN_VALIDATION_PAIRING_POLICY_HASH_MISMATCH"

    if record.policy_kind != expected_kind:
        return "TRAIN_VALIDATION_PAIRING_POLICY_KIND_MISMATCH"

    if record.policy_version != version:
        return "TRAIN_VALIDATION_PAIRING_POLICY_NOT_ISSUED"

    if not _semantic_authority_matches(record):
        return "TRAIN_VALIDATION_PAIRING_POLICY_SEMANTIC_MISMATCH"

    if not _semantic_authority_version_matches(record):
        return "TRAIN_VALIDATION_PAIRING_POLICY_SEMANTIC_MISMATCH"

    if not _permitted_partitions_match(record):
        return "TRAIN_VALIDATION_PAIRING_POLICY_SEMANTIC_MISMATCH"

    return None


def build_candidate_policy_record(
    *,
    policy_kind: PolicyKind,
    policy_version: str,
    issuer_identity_or_version: str,
    semantic_rule_or_authority: str | None = None,
    semantic_authority_version: str | None = None,
    permitted_partitions: tuple[str, ...] | None = None,
) -> IssuedPairingPolicyRecord:
    """Build a structurally valid candidate policy record without issuing it."""

    resolved_semantic = (
        _canonical_semantic_for_kind(policy_kind)
        if semantic_rule_or_authority is None
        else semantic_rule_or_authority
    )
    if semantic_authority_version is None:
        resolved_semantic_version = _canonical_semantic_authority_version_for_kind(policy_kind)
    else:
        resolved_semantic_version = semantic_authority_version
    resolved_partitions = (
        _canonical_permitted_partitions_for_kind(policy_kind)
        if permitted_partitions is None
        else permitted_partitions
    )
    candidate = IssuedPairingPolicyRecord(
        policy_record_identity="",
        policy_kind=policy_kind,
        policy_version=policy_version,
        semantic_rule_or_authority=resolved_semantic,
        semantic_authority_version=resolved_semantic_version,
        issuer_identity_or_version=issuer_identity_or_version,
        permitted_partitions=resolved_partitions,
        canonical_hash="",
    )
    policy_record_identity, canonical_hash = compute_policy_record_identity_hashes(candidate)
    return IssuedPairingPolicyRecord(
        policy_record_identity=policy_record_identity,
        policy_kind=candidate.policy_kind,
        policy_version=candidate.policy_version,
        semantic_rule_or_authority=candidate.semantic_rule_or_authority,
        semantic_authority_version=candidate.semantic_authority_version,
        issuer_identity_or_version=candidate.issuer_identity_or_version,
        permitted_partitions=candidate.permitted_partitions,
        canonical_hash=canonical_hash,
    )


def canonical_policy_version_for_kind(policy_kind: PolicyKind) -> str:
    return _CANONICAL_VERSION_BY_KIND[policy_kind]


__all__ = [
    "GENERAL_PAIRING_POLICY_SEMANTIC_AUTHORITY_ID",
    "GENERAL_PAIRING_POLICY_SEMANTIC_AUTHORITY_SOURCE",
    "GENERAL_PAIRING_POLICY_SEMANTIC_AUTHORITY_VERSION",
    "IssuedPairingPolicyRecord",
    "PAIRING_POLICY_AUTHORITY_CONTRACT_ID",
    "PAIRING_POLICY_AUTHORITY_CONTRACT_PATH",
    "PAIRING_POLICY_AUTHORITY_CONTRACT_VERSION",
    "PolicyKind",
    "PRODUCTION_TRUSTED_ISSUED_PAIRING_POLICY_REGISTRY",
    "TrustedIssuedPairingPolicyRegistry",
    "TrustedPairingPolicyRegistryConstructionError",
    "build_candidate_policy_record",
    "build_policy_record_semantic_payload",
    "canonical_policy_version_for_kind",
    "compute_policy_record_identity_hashes",
    "verify_issued_pairing_policy",
    "verify_policy_record_hash_replay",
]
