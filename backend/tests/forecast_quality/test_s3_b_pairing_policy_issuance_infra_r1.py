"""Tests for S3-B pairing policy issuance infrastructure R1."""

from __future__ import annotations

import dataclasses

import pytest

from backend.app.forecast_quality.quantile_coverage import (
    assess_train_validation_coverage_execution,
)
from backend.app.forecast_quality.train_val_pairing import (
    EXACT_ACTUAL_PAIRING_POLICY_V1,
    EXACT_ACTUAL_PAIRING_POLICY_VERSION_STATUS,
    FROZEN_EXACT_ACTUAL_PAIRING_RULE,
    ISSUED_EXACT_ACTUAL_PAIRING_POLICY_VERSIONS,
    TRAIN_VAL_PAIRING_POLICY_V1,
)
from backend.app.forecast_quality.train_val_pairing_policy_registry import (
    GENERAL_PAIRING_POLICY_SEMANTIC_AUTHORITY_ID,
    GENERAL_PAIRING_POLICY_SEMANTIC_AUTHORITY_SOURCE,
    PRODUCTION_TRUSTED_ISSUED_PAIRING_POLICY_REGISTRY,
    IssuedPairingPolicyRecord,
    TrustedIssuedPairingPolicyRegistry,
    TrustedPairingPolicyRegistryConstructionError,
    build_candidate_policy_record,
    compute_policy_record_identity_hashes,
    verify_issued_pairing_policy,
    verify_policy_record_hash_replay,
)
from backend.app.forecast_quality.train_val_trusted_registry import (
    _ISSUED_PAIRING_POLICY_VERSIONS,
)

_CANONICAL_PARTITIONS = ("TRAIN", "VALIDATION")


def _general_record(
    *,
    policy_version: str = TRAIN_VAL_PAIRING_POLICY_V1,
    issuer_identity_or_version: str = "test-issuer-v1",
) -> IssuedPairingPolicyRecord:
    return build_candidate_policy_record(
        policy_kind="TRAIN_VAL_BINDING_PAIRING",
        policy_version=policy_version,
        issuer_identity_or_version=issuer_identity_or_version,
    )


def _exact_record(
    *,
    policy_version: str = EXACT_ACTUAL_PAIRING_POLICY_V1,
    issuer_identity_or_version: str = "test-issuer-v1",
) -> IssuedPairingPolicyRecord:
    return build_candidate_policy_record(
        policy_kind="EXACT_ACTUAL_PAIRING",
        policy_version=policy_version,
        issuer_identity_or_version=issuer_identity_or_version,
    )


def test_a_exact_version_constant() -> None:
    assert EXACT_ACTUAL_PAIRING_POLICY_V1 == "v0-3-s3-b-exact-actual-pairing-policy-v1"
    assert EXACT_ACTUAL_PAIRING_POLICY_VERSION_STATUS == "NOT_ISSUED"


def test_b_deterministic_record_replay() -> None:
    first = _general_record()
    second = _general_record()
    assert first.policy_record_identity == second.policy_record_identity
    assert first.canonical_hash == second.canonical_hash
    assert verify_policy_record_hash_replay(first)


def test_c_tamper_detection() -> None:
    record = _general_record()
    tamper_fields = [
        ("policy_kind", "EXACT_ACTUAL_PAIRING"),
        ("policy_version", "tampered-version-v1"),
        ("semantic_rule_or_authority", "WRONG_SEMANTIC"),
        ("issuer_identity_or_version", "forged-issuer"),
        ("permitted_partitions", ("TEST",)),
    ]
    for field_name, tampered_value in tamper_fields:
        tampered = dataclasses.replace(record, **{field_name: tampered_value})
        assert not verify_policy_record_hash_replay(tampered)


def test_d_registry_defensive_copy() -> None:
    record = _general_record()
    source = {record.policy_record_identity: record}
    registry = TrustedIssuedPairingPolicyRegistry(source)
    assert registry.count() == 1
    source.clear()
    assert registry.count() == 1


def test_e_direct_registry_mutation_rejected() -> None:
    record = _general_record()
    registry = TrustedIssuedPairingPolicyRegistry({record.policy_record_identity: record})
    with pytest.raises(TypeError):
        registry._records_by_identity["forged"] = _general_record()  # type: ignore[index]


def test_f_general_policy_constant_not_issued_in_production() -> None:
    blocker = verify_issued_pairing_policy(
        TRAIN_VAL_PAIRING_POLICY_V1,
        "TRAIN_VAL_BINDING_PAIRING",
        registry=PRODUCTION_TRUSTED_ISSUED_PAIRING_POLICY_REGISTRY,
    )
    assert blocker == "TRAIN_VALIDATION_PAIRING_POLICY_NOT_ISSUED"


def test_g_exact_policy_constant_not_issued_in_production() -> None:
    blocker = verify_issued_pairing_policy(
        EXACT_ACTUAL_PAIRING_POLICY_V1,
        "EXACT_ACTUAL_PAIRING",
        registry=PRODUCTION_TRUSTED_ISSUED_PAIRING_POLICY_REGISTRY,
    )
    assert blocker == "TRAIN_VALIDATION_EXACT_ACTUAL_PAIRING_POLICY_NOT_ISSUED"


def test_h_caller_crafted_record_without_registry_membership() -> None:
    crafted = _general_record()
    blocker = verify_issued_pairing_policy(
        crafted.policy_version,
        "TRAIN_VAL_BINDING_PAIRING",
        registry=TrustedIssuedPairingPolicyRegistry(),
    )
    assert blocker == "TRAIN_VALIDATION_PAIRING_POLICY_NOT_ISSUED"


def test_i_wrong_policy_kind_rejected() -> None:
    general = _general_record()
    registry = TrustedIssuedPairingPolicyRegistry({general.policy_record_identity: general})
    blocker = verify_issued_pairing_policy(
        TRAIN_VAL_PAIRING_POLICY_V1,
        "EXACT_ACTUAL_PAIRING",
        registry=registry,
    )
    assert blocker == "TRAIN_VALIDATION_EXACT_ACTUAL_PAIRING_POLICY_NOT_ISSUED"


def test_j_semantic_authority_mismatch_rejected() -> None:
    candidate = IssuedPairingPolicyRecord(
        policy_record_identity="",
        policy_kind="EXACT_ACTUAL_PAIRING",
        policy_version=EXACT_ACTUAL_PAIRING_POLICY_V1,
        semantic_rule_or_authority="WRONG_SEMANTIC",
        issuer_identity_or_version="test-issuer-v1",
        permitted_partitions=_CANONICAL_PARTITIONS,
        canonical_hash="",
    )
    identity, canonical = compute_policy_record_identity_hashes(candidate)
    forged = dataclasses.replace(
        candidate,
        policy_record_identity=identity,
        canonical_hash=canonical,
    )
    assert verify_policy_record_hash_replay(forged)
    registry = TrustedIssuedPairingPolicyRegistry({identity: forged})
    blocker = verify_issued_pairing_policy(
        EXACT_ACTUAL_PAIRING_POLICY_V1,
        "EXACT_ACTUAL_PAIRING",
        registry=registry,
    )
    assert blocker == "TRAIN_VALIDATION_PAIRING_POLICY_SEMANTIC_MISMATCH"


def test_k_production_seal() -> None:
    assert PRODUCTION_TRUSTED_ISSUED_PAIRING_POLICY_REGISTRY.count() == 0
    assert _ISSUED_PAIRING_POLICY_VERSIONS == frozenset()
    assert ISSUED_EXACT_ACTUAL_PAIRING_POLICY_VERSIONS == frozenset()
    assessment = assess_train_validation_coverage_execution(
        None,
        breakdown_specs=(),
        partition_authority=None,
    )
    assert assessment.execution_status == "NOT_COMPUTABLE_OR_BLOCKED"


def test_contract_grounded_semantic_authority() -> None:
    exact = _exact_record()
    assert exact.semantic_rule_or_authority == FROZEN_EXACT_ACTUAL_PAIRING_RULE
    general = _general_record()
    assert general.semantic_rule_or_authority == GENERAL_PAIRING_POLICY_SEMANTIC_AUTHORITY_ID
    assert (
        GENERAL_PAIRING_POLICY_SEMANTIC_AUTHORITY_SOURCE
        == "docs/v0-3/s3/s3-b-pairing-policy-authority-contract.md"
    )
    assert general.permitted_partitions == _CANONICAL_PARTITIONS
    assert exact.permitted_partitions == _CANONICAL_PARTITIONS


def test_registry_wrong_mapping_key_rejected() -> None:
    record = _general_record()
    with pytest.raises(TrustedPairingPolicyRegistryConstructionError):
        TrustedIssuedPairingPolicyRegistry({"wrong-key": record})


def test_registry_duplicate_version_kind_rejected() -> None:
    first = _general_record()
    second = build_candidate_policy_record(
        policy_kind="TRAIN_VAL_BINDING_PAIRING",
        policy_version=TRAIN_VAL_PAIRING_POLICY_V1,
        issuer_identity_or_version="other-issuer-v1",
    )
    with pytest.raises(TrustedPairingPolicyRegistryConstructionError):
        TrustedIssuedPairingPolicyRegistry(
            {
                first.policy_record_identity: first,
                second.policy_record_identity: second,
            }
        )


def test_registry_lookup_by_version_requires_identity_membership() -> None:
    record = _general_record()
    registry = TrustedIssuedPairingPolicyRegistry({record.policy_record_identity: record})
    looked_up = registry.lookup_by_policy_version(
        TRAIN_VAL_PAIRING_POLICY_V1,
        "TRAIN_VAL_BINDING_PAIRING",
    )
    assert looked_up == record
    assert registry.lookup(record.policy_record_identity) == record


def test_arbitrary_general_policy_version_not_issued_even_in_registry() -> None:
    invented = build_candidate_policy_record(
        policy_kind="TRAIN_VAL_BINDING_PAIRING",
        policy_version="caller-invented-v99",
        issuer_identity_or_version="test-issuer-v1",
    )
    registry = TrustedIssuedPairingPolicyRegistry({invented.policy_record_identity: invented})
    blocker = verify_issued_pairing_policy(
        "caller-invented-v99",
        "TRAIN_VAL_BINDING_PAIRING",
        registry=registry,
    )
    assert blocker == "TRAIN_VALIDATION_PAIRING_POLICY_NOT_ISSUED"


def test_arbitrary_exact_policy_version_not_issued_even_in_registry() -> None:
    invented = build_candidate_policy_record(
        policy_kind="EXACT_ACTUAL_PAIRING",
        policy_version="caller-invented-exact-v99",
        issuer_identity_or_version="test-issuer-v1",
    )
    registry = TrustedIssuedPairingPolicyRegistry({invented.policy_record_identity: invented})
    blocker = verify_issued_pairing_policy(
        "caller-invented-exact-v99",
        "EXACT_ACTUAL_PAIRING",
        registry=registry,
    )
    assert blocker == "TRAIN_VALIDATION_EXACT_ACTUAL_PAIRING_POLICY_NOT_ISSUED"


def test_candidate_empty_semantic_not_silently_defaulted() -> None:
    record = build_candidate_policy_record(
        policy_kind="TRAIN_VAL_BINDING_PAIRING",
        policy_version=TRAIN_VAL_PAIRING_POLICY_V1,
        issuer_identity_or_version="test-issuer-v1",
        semantic_rule_or_authority="",
    )
    assert record.semantic_rule_or_authority == ""


def test_candidate_empty_partitions_not_silently_defaulted() -> None:
    record = build_candidate_policy_record(
        policy_kind="TRAIN_VAL_BINDING_PAIRING",
        policy_version=TRAIN_VAL_PAIRING_POLICY_V1,
        issuer_identity_or_version="test-issuer-v1",
        permitted_partitions=(),
    )
    assert record.permitted_partitions == ()
