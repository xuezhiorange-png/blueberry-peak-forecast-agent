"""Tests for S3-B pairing policy dual issuance R1."""

from __future__ import annotations

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
    EXACT_ACTUAL_PAIRING_POLICY_ISSUANCE_GRANT_ID,
    GENERAL_PAIRING_POLICY_ISSUANCE_GRANT_ID,
    GENERAL_PAIRING_POLICY_SEMANTIC_AUTHORITY_ID,
    GENERAL_PAIRING_POLICY_SEMANTIC_AUTHORITY_VERSION,
    PRODUCTION_ISSUED_EXACT_ACTUAL_PAIRING_POLICY_RECORD,
    PRODUCTION_ISSUED_GENERAL_PAIRING_POLICY_RECORD,
    PRODUCTION_TRUSTED_ISSUED_PAIRING_POLICY_REGISTRY,
    TrustedIssuedPairingPolicyRegistry,
    build_candidate_policy_record,
    verify_issued_pairing_policy,
    verify_policy_record_hash_replay,
)
from backend.app.forecast_quality.train_val_trusted_registry import (
    _ISSUED_PAIRING_POLICY_VERSIONS,
    PRODUCTION_TRUSTED_ISSUED_AUTHORITY_REGISTRY,
    PRODUCTION_TRUSTED_PUBLISHED_PAIRING_PACKAGE_REGISTRY,
)

_CANONICAL_PARTITIONS = ("TRAIN", "VALIDATION")


def test_a_exact_version_status_issued() -> None:
    assert EXACT_ACTUAL_PAIRING_POLICY_V1 == "v0-3-s3-b-exact-actual-pairing-policy-v1"
    assert EXACT_ACTUAL_PAIRING_POLICY_VERSION_STATUS == "ISSUED"


def test_b_production_registry_dual_issued() -> None:
    assert PRODUCTION_TRUSTED_ISSUED_PAIRING_POLICY_REGISTRY.count() == 2


def test_c_general_policy_verifies_in_production() -> None:
    blocker = verify_issued_pairing_policy(
        TRAIN_VAL_PAIRING_POLICY_V1,
        "TRAIN_VAL_BINDING_PAIRING",
        registry=PRODUCTION_TRUSTED_ISSUED_PAIRING_POLICY_REGISTRY,
    )
    assert blocker is None


def test_d_exact_policy_verifies_in_production() -> None:
    blocker = verify_issued_pairing_policy(
        EXACT_ACTUAL_PAIRING_POLICY_V1,
        "EXACT_ACTUAL_PAIRING",
        registry=PRODUCTION_TRUSTED_ISSUED_PAIRING_POLICY_REGISTRY,
    )
    assert blocker is None


def test_e_general_allowlist_populated() -> None:
    assert _ISSUED_PAIRING_POLICY_VERSIONS == frozenset({TRAIN_VAL_PAIRING_POLICY_V1})


def test_f_exact_allowlist_populated() -> None:
    assert ISSUED_EXACT_ACTUAL_PAIRING_POLICY_VERSIONS == frozenset(
        {EXACT_ACTUAL_PAIRING_POLICY_V1}
    )


def test_g_dual_gate_registry_only_insufficient_for_general() -> None:
    assert (
        verify_issued_pairing_policy(
            TRAIN_VAL_PAIRING_POLICY_V1,
            "TRAIN_VAL_BINDING_PAIRING",
            registry=PRODUCTION_TRUSTED_ISSUED_PAIRING_POLICY_REGISTRY,
        )
        is None
    )
    assert TRAIN_VAL_PAIRING_POLICY_V1 not in frozenset()


def test_h_dual_gate_allowlist_only_insufficient_for_general() -> None:
    assert TRAIN_VAL_PAIRING_POLICY_V1 in _ISSUED_PAIRING_POLICY_VERSIONS
    blocker = verify_issued_pairing_policy(
        TRAIN_VAL_PAIRING_POLICY_V1,
        "TRAIN_VAL_BINDING_PAIRING",
        registry=TrustedIssuedPairingPolicyRegistry(),
    )
    assert blocker == "TRAIN_VALIDATION_PAIRING_POLICY_NOT_ISSUED"


def test_i_dual_gate_registry_only_insufficient_for_exact() -> None:
    assert (
        verify_issued_pairing_policy(
            EXACT_ACTUAL_PAIRING_POLICY_V1,
            "EXACT_ACTUAL_PAIRING",
            registry=PRODUCTION_TRUSTED_ISSUED_PAIRING_POLICY_REGISTRY,
        )
        is None
    )
    assert EXACT_ACTUAL_PAIRING_POLICY_V1 not in frozenset()


def test_j_dual_gate_allowlist_only_insufficient_for_exact() -> None:
    registry = TrustedIssuedPairingPolicyRegistry()
    blocker = verify_issued_pairing_policy(
        EXACT_ACTUAL_PAIRING_POLICY_V1,
        "EXACT_ACTUAL_PAIRING",
        registry=registry,
    )
    assert blocker == "TRAIN_VALIDATION_EXACT_ACTUAL_PAIRING_POLICY_NOT_ISSUED"
    assert EXACT_ACTUAL_PAIRING_POLICY_V1 in ISSUED_EXACT_ACTUAL_PAIRING_POLICY_VERSIONS


def test_k_production_seal_coverage_still_blocked() -> None:
    assert PRODUCTION_TRUSTED_PUBLISHED_PAIRING_PACKAGE_REGISTRY.count() == 0
    assert PRODUCTION_TRUSTED_ISSUED_AUTHORITY_REGISTRY.count() == 0
    assessment = assess_train_validation_coverage_execution(
        None,
        breakdown_specs=(),
        partition_authority=None,
    )
    assert assessment.execution_status == "NOT_COMPUTABLE_OR_BLOCKED"


def test_l_grant_ids_on_production_records() -> None:
    general = PRODUCTION_ISSUED_GENERAL_PAIRING_POLICY_RECORD
    exact = PRODUCTION_ISSUED_EXACT_ACTUAL_PAIRING_POLICY_RECORD
    assert general.issuer_identity_or_version == GENERAL_PAIRING_POLICY_ISSUANCE_GRANT_ID
    assert exact.issuer_identity_or_version == EXACT_ACTUAL_PAIRING_POLICY_ISSUANCE_GRANT_ID


def test_m_production_record_hash_replay() -> None:
    assert verify_policy_record_hash_replay(PRODUCTION_ISSUED_GENERAL_PAIRING_POLICY_RECORD)
    assert verify_policy_record_hash_replay(PRODUCTION_ISSUED_EXACT_ACTUAL_PAIRING_POLICY_RECORD)


def test_n_production_records_match_canonical_semantics() -> None:
    general = PRODUCTION_ISSUED_GENERAL_PAIRING_POLICY_RECORD
    exact = PRODUCTION_ISSUED_EXACT_ACTUAL_PAIRING_POLICY_RECORD
    assert general.policy_kind == "TRAIN_VAL_BINDING_PAIRING"
    assert general.policy_version == TRAIN_VAL_PAIRING_POLICY_V1
    assert general.semantic_rule_or_authority == GENERAL_PAIRING_POLICY_SEMANTIC_AUTHORITY_ID
    assert general.semantic_authority_version == GENERAL_PAIRING_POLICY_SEMANTIC_AUTHORITY_VERSION
    assert general.permitted_partitions == _CANONICAL_PARTITIONS
    assert exact.policy_kind == "EXACT_ACTUAL_PAIRING"
    assert exact.policy_version == EXACT_ACTUAL_PAIRING_POLICY_V1
    assert exact.semantic_rule_or_authority == FROZEN_EXACT_ACTUAL_PAIRING_RULE
    assert exact.semantic_authority_version is None
    assert exact.permitted_partitions == _CANONICAL_PARTITIONS


def test_production_records_deterministic_rebuild() -> None:
    rebuilt_general = build_candidate_policy_record(
        policy_kind="TRAIN_VAL_BINDING_PAIRING",
        policy_version=TRAIN_VAL_PAIRING_POLICY_V1,
        issuer_identity_or_version=GENERAL_PAIRING_POLICY_ISSUANCE_GRANT_ID,
    )
    rebuilt_exact = build_candidate_policy_record(
        policy_kind="EXACT_ACTUAL_PAIRING",
        policy_version=EXACT_ACTUAL_PAIRING_POLICY_V1,
        issuer_identity_or_version=EXACT_ACTUAL_PAIRING_POLICY_ISSUANCE_GRANT_ID,
    )
    assert rebuilt_general == PRODUCTION_ISSUED_GENERAL_PAIRING_POLICY_RECORD
    assert rebuilt_exact == PRODUCTION_ISSUED_EXACT_ACTUAL_PAIRING_POLICY_RECORD
