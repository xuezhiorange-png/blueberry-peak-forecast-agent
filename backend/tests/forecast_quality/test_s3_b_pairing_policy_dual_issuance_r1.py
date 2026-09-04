"""Tests for S3-B pairing policy dual issuance R1."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from backend.app.forecast_quality.enums import FrozenVersion, SupportedQuantile
from backend.app.forecast_quality.quantile_coverage import (
    TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1,
    TrainValidationCoveragePartitionAuthority,
    assess_train_validation_coverage_execution,
)
from backend.app.forecast_quality.schemas import S3BindingRow, S3EvaluationInput
from backend.app.forecast_quality.train_val_pairing import (
    ACCEPTED_TRAIN_PARTITION_IDENTITY,
    EXACT_ACTUAL_PAIRING_POLICY_V1,
    EXACT_ACTUAL_PAIRING_POLICY_VERSION_STATUS,
    FROZEN_EXACT_ACTUAL_PAIRING_RULE,
    ISSUED_EXACT_ACTUAL_PAIRING_POLICY_VERSIONS,
    TRAIN_VAL_PAIRING_POLICY_V1,
    build_candidate_train_validation_pairing_package,
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
    TrustedIssuedAuthorityRegistry,
    TrustedPublishedPairingPackageRegistry,
    build_candidate_authority_record,
    verify_train_validation_coverage_authority,
)

_CANONICAL_PARTITIONS = ("TRAIN", "VALIDATION")
_FORECAST_CUTOFF_AUTHORITY = "d" * 64


def _row(index: int = 0) -> S3BindingRow:
    return S3BindingRow(
        f"forecast-{index}",
        f"physical-{index}",
        f"actual-{index}",
        Decimal("10"),
        Decimal("9"),
        SupportedQuantile.P50,
        7,
        date(2025, 2, 10),
        datetime(2025, 2, 1, tzinfo=UTC),
        "COMPARABLE",
        "season-2025",
        "farm-a",
        "subfarm-a",
        "variety-a",
        "model-a",
        datetime(2025, 2, 1, tzinfo=UTC),
    )


def _evaluation(row_set_hash: str = "a" * 64) -> S3EvaluationInput:
    return S3EvaluationInput(
        [_row()],
        "s2-run-a",
        "s2-manifest-a",
        row_set_hash,
        FrozenVersion.METRIC_INPUT_MASK_V1,
        FrozenVersion.NAIVE_BASELINE_POLICY_V1,
    )


def _candidate_package() -> object:
    return build_candidate_train_validation_pairing_package(
        partition="TRAIN",
        partition_identity=ACCEPTED_TRAIN_PARTITION_IDENTITY,
        evaluation_input=_evaluation(),
        forecast_cutoff_authority_identity=_FORECAST_CUTOFF_AUTHORITY,
        exact_actual_pairing_policy_version=EXACT_ACTUAL_PAIRING_POLICY_V1,
        pairing_policy_version=TRAIN_VAL_PAIRING_POLICY_V1,
    )


def _partition_authority(
    package: object,
    *,
    authority_record_identity: str,
) -> TrainValidationCoveragePartitionAuthority:
    return TrainValidationCoveragePartitionAuthority(
        authority_record_identity=authority_record_identity,
        schema_version=TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1,
        pairing_package_identity=package.pairing_package_identity,
        s2_binding_row_set_hash=package.s2_binding_row_set_hash,
        permitted_partitions=(package.partition,),
    )


def _full_verifier_blocker(
    *,
    issued_pairing_policy_versions: frozenset[str],
    issued_exact_actual_pairing_policy_versions: frozenset[str],
    issued_policy_registry: TrustedIssuedPairingPolicyRegistry,
) -> str | None:
    package = _candidate_package()
    record = build_candidate_authority_record(
        schema_version=TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1,
        pairing_package_identity=package.pairing_package_identity,
        s2_binding_row_set_hash=package.s2_binding_row_set_hash,
        permitted_partitions=(package.partition,),
        issuer_identity_or_version="issuer-v1",
    )
    authority = _partition_authority(
        package,
        authority_record_identity=record.authority_record_identity,
    )
    return verify_train_validation_coverage_authority(
        package.evaluation_input,
        authority,
        published_registry=TrustedPublishedPairingPackageRegistry(
            {package.pairing_package_identity: package}
        ),
        issued_registry=TrustedIssuedAuthorityRegistry({record.authority_record_identity: record}),
        issued_schema_versions=frozenset({TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1}),
        issued_pairing_policy_versions=issued_pairing_policy_versions,
        issued_exact_actual_pairing_policy_versions=issued_exact_actual_pairing_policy_versions,
        issued_policy_registry=issued_policy_registry,
    )


def _registry_with_general_only() -> TrustedIssuedPairingPolicyRegistry:
    return TrustedIssuedPairingPolicyRegistry(
        {
            PRODUCTION_ISSUED_GENERAL_PAIRING_POLICY_RECORD.policy_record_identity: (
                PRODUCTION_ISSUED_GENERAL_PAIRING_POLICY_RECORD
            ),
        }
    )


def _registry_with_exact_only() -> TrustedIssuedPairingPolicyRegistry:
    return TrustedIssuedPairingPolicyRegistry(
        {
            PRODUCTION_ISSUED_EXACT_ACTUAL_PAIRING_POLICY_RECORD.policy_record_identity: (
                PRODUCTION_ISSUED_EXACT_ACTUAL_PAIRING_POLICY_RECORD
            ),
        }
    )


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
    blocker = _full_verifier_blocker(
        issued_pairing_policy_versions=frozenset(),
        issued_exact_actual_pairing_policy_versions=frozenset({EXACT_ACTUAL_PAIRING_POLICY_V1}),
        issued_policy_registry=PRODUCTION_TRUSTED_ISSUED_PAIRING_POLICY_REGISTRY,
    )
    assert blocker == "TRAIN_VALIDATION_PAIRING_POLICY_NOT_ISSUED"


def test_h_dual_gate_allowlist_only_insufficient_for_general() -> None:
    blocker = _full_verifier_blocker(
        issued_pairing_policy_versions=frozenset({TRAIN_VAL_PAIRING_POLICY_V1}),
        issued_exact_actual_pairing_policy_versions=frozenset({EXACT_ACTUAL_PAIRING_POLICY_V1}),
        issued_policy_registry=_registry_with_exact_only(),
    )
    assert blocker == "TRAIN_VALIDATION_PAIRING_POLICY_NOT_ISSUED"


def test_i_dual_gate_registry_only_insufficient_for_exact() -> None:
    blocker = _full_verifier_blocker(
        issued_pairing_policy_versions=frozenset({TRAIN_VAL_PAIRING_POLICY_V1}),
        issued_exact_actual_pairing_policy_versions=frozenset(),
        issued_policy_registry=PRODUCTION_TRUSTED_ISSUED_PAIRING_POLICY_REGISTRY,
    )
    assert blocker == "TRAIN_VALIDATION_EXACT_ACTUAL_PAIRING_POLICY_NOT_ISSUED"


def test_j_dual_gate_allowlist_only_insufficient_for_exact() -> None:
    blocker = _full_verifier_blocker(
        issued_pairing_policy_versions=frozenset({TRAIN_VAL_PAIRING_POLICY_V1}),
        issued_exact_actual_pairing_policy_versions=frozenset({EXACT_ACTUAL_PAIRING_POLICY_V1}),
        issued_policy_registry=_registry_with_general_only(),
    )
    assert blocker == "TRAIN_VALIDATION_EXACT_ACTUAL_PAIRING_POLICY_NOT_ISSUED"


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
