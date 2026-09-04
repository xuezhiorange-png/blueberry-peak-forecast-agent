"""Tests for S3-B pairing package and trusted authority infrastructure R1."""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from backend.app.forecast_quality.enums import FrozenVersion, SupportedQuantile
from backend.app.forecast_quality.exceptions import S3DecimalAssertionError
from backend.app.forecast_quality.quantile_coverage import (
    _ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSIONS,
    TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1,
    TrainValidationCoveragePartitionAuthority,
    assess_train_validation_coverage_execution,
)
from backend.app.forecast_quality.schemas import BreakdownSpec, S3BindingRow, S3EvaluationInput
from backend.app.forecast_quality.train_val_pairing import (
    ACCEPTED_TRAIN_PARTITION_IDENTITY,
    ACCEPTED_VALIDATION_PARTITION_IDENTITY,
    EXACT_ACTUAL_PAIRING_POLICY_VERSION_NOT_ISSUED,
    EXACT_ACTUAL_PAIRING_POLICY_VERSION_STATUS,
    FROZEN_EXACT_ACTUAL_PAIRING_RULE,
    ISSUED_EXACT_ACTUAL_PAIRING_POLICY_VERSIONS,
    TRAIN_VAL_PAIRING_POLICY_V1,
    PartitionIdentity,
    TrainValPairingPackageInvariantError,
    build_candidate_train_validation_pairing_package,
    build_pairing_package_semantic_payload,
    compute_pairing_package_identity_hashes,
    validate_pairing_package_candidate_invariants,
    validate_pairing_package_invariants,
    verify_pairing_package_hash_replay,
)
from backend.app.forecast_quality.train_val_pairing_policy_registry import (
    TrustedIssuedPairingPolicyRegistry,
    build_candidate_policy_record,
)
from backend.app.forecast_quality.train_val_trusted_registry import (
    PRODUCTION_TRUSTED_ISSUED_AUTHORITY_REGISTRY,
    PRODUCTION_TRUSTED_PUBLISHED_PAIRING_PACKAGE_REGISTRY,
    TrustedIssuedAuthorityRegistry,
    TrustedPublishedPairingPackageRegistry,
    build_candidate_authority_record,
    verify_authority_record_hash_replay,
    verify_train_validation_coverage_authority,
)
from backend.app.s3_daily_rowset.registry import (
    V0_3_S3_ACTUALS_AUTHORITY,
    V0_3_S3_FORECASTS_AUTHORITY,
)

_SPEC = BreakdownSpec(7, "farm-a", "subfarm-a", "variety-a", "season-2025", "model-a")
_FORECAST_CUTOFF_AUTHORITY = "d" * 64
_TEST_EXACT_ACTUAL_PAIRING_POLICY_VERSION = "test-exact-actual-policy-v1"


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


def _evaluation(
    rows: list[S3BindingRow] | None = None,
    row_set_hash: str = "a" * 64,
) -> S3EvaluationInput:
    return S3EvaluationInput(
        rows if rows is not None else [_row()],
        "s2-run-a",
        "s2-manifest-a",
        row_set_hash,
        FrozenVersion.METRIC_INPUT_MASK_V1,
        FrozenVersion.NAIVE_BASELINE_POLICY_V1,
    )


def _candidate_package(
    *,
    partition: str = "TRAIN",
    partition_identity: PartitionIdentity = ACCEPTED_TRAIN_PARTITION_IDENTITY,
    evaluation: S3EvaluationInput | None = None,
) -> object:
    return build_candidate_train_validation_pairing_package(
        partition=partition,
        partition_identity=partition_identity,
        evaluation_input=evaluation or _evaluation(),
        forecast_cutoff_authority_identity=_FORECAST_CUTOFF_AUTHORITY,
        exact_actual_pairing_policy_version=EXACT_ACTUAL_PAIRING_POLICY_VERSION_NOT_ISSUED,
        pairing_policy_version=TRAIN_VAL_PAIRING_POLICY_V1,
    )


def _partition_authority(
    package: object,
    *,
    authority_record_identity: str = "c" * 64,
    schema_version: str = TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1,
) -> TrainValidationCoveragePartitionAuthority:
    return TrainValidationCoveragePartitionAuthority(
        authority_record_identity=authority_record_identity,
        schema_version=schema_version,
        pairing_package_identity=package.pairing_package_identity,
        s2_binding_row_set_hash=package.s2_binding_row_set_hash,
        permitted_partitions=(package.partition,),
    )


def _rehash_package(package: object, **changes: object) -> object:
    updated = dataclasses.replace(package, **changes)
    identity, canonical = compute_pairing_package_identity_hashes(updated)
    return dataclasses.replace(
        updated,
        pairing_package_identity=identity,
        canonical_hash=canonical,
    )


def _test_policy_registry(
    *,
    general_version: str = TRAIN_VAL_PAIRING_POLICY_V1,
    exact_version: str = _TEST_EXACT_ACTUAL_PAIRING_POLICY_VERSION,
) -> TrustedIssuedPairingPolicyRegistry:
    general = build_candidate_policy_record(
        policy_kind="TRAIN_VAL_BINDING_PAIRING",
        policy_version=general_version,
        issuer_identity_or_version="test-issuer-v1",
    )
    exact = build_candidate_policy_record(
        policy_kind="EXACT_ACTUAL_PAIRING",
        policy_version=exact_version,
        issuer_identity_or_version="test-issuer-v1",
    )
    return TrustedIssuedPairingPolicyRegistry(
        {
            general.policy_record_identity: general,
            exact.policy_record_identity: exact,
        }
    )


def _full_verifier_blocker(
    package: object,
    *,
    evaluation_input: S3EvaluationInput | None = None,
    exact_policy_version: str = _TEST_EXACT_ACTUAL_PAIRING_POLICY_VERSION,
    issued_exact: frozenset[str] | None = None,
) -> str | None:
    published_package = _rehash_package(
        package,
        exact_actual_pairing_policy_version=exact_policy_version,
    )
    record = build_candidate_authority_record(
        schema_version=TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1,
        pairing_package_identity=published_package.pairing_package_identity,
        s2_binding_row_set_hash=published_package.s2_binding_row_set_hash,
        permitted_partitions=(published_package.partition,),
        issuer_identity_or_version="issuer-v1",
    )
    authority = _partition_authority(
        published_package,
        authority_record_identity=record.authority_record_identity,
    )
    return verify_train_validation_coverage_authority(
        evaluation_input or published_package.evaluation_input,
        authority,
        published_registry=TrustedPublishedPairingPackageRegistry(
            {published_package.pairing_package_identity: published_package}
        ),
        issued_registry=TrustedIssuedAuthorityRegistry({record.authority_record_identity: record}),
        issued_schema_versions=frozenset({TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1}),
        issued_pairing_policy_versions=frozenset({TRAIN_VAL_PAIRING_POLICY_V1}),
        issued_exact_actual_pairing_policy_versions=issued_exact
        or frozenset({exact_policy_version}),
        issued_policy_registry=_test_policy_registry(exact_version=exact_policy_version),
    )


def test_a_package_deterministic_replay() -> None:
    first = _candidate_package()
    second = _candidate_package()

    assert first.pairing_package_identity == second.pairing_package_identity
    assert first.canonical_hash == second.canonical_hash
    assert verify_pairing_package_hash_replay(first)


def test_b_self_reference_safety() -> None:
    package = _candidate_package()
    identity_preimage = build_pairing_package_semantic_payload(
        package,
        pairing_package_identity="",
        canonical_hash="",
    )
    assert identity_preimage["pairing_package_identity"] == ""
    assert identity_preimage["canonical_hash"] == ""

    wrong_identity_preimage = build_pairing_package_semantic_payload(
        package,
        pairing_package_identity=package.pairing_package_identity,
        canonical_hash="",
    )
    recomputed = compute_pairing_package_identity_hashes(
        dataclasses.replace(package, pairing_package_identity="", canonical_hash="")
    )[0]
    assert recomputed == package.pairing_package_identity
    assert wrong_identity_preimage["pairing_package_identity"] != ""


def test_c_package_tamper_detection() -> None:
    package = _candidate_package()
    tamper_fields = [
        (
            "source_dataset_identity",
            dataclasses.replace(package.source_dataset_identity, dataset_id="other"),
        ),
        ("partition_identity", ACCEPTED_VALIDATION_PARTITION_IDENTITY),
        ("actuals_authority_identity", "wrong"),
        ("forecast_authority_identity", "wrong"),
        ("forecast_cutoff_authority_identity", "e" * 64),
        ("s2_run_identity", "different-run"),
        ("s2_manifest_identity", "different-manifest"),
        ("s2_binding_row_set_hash", "f" * 64),
        ("pairing_policy_version", "other-policy"),
        (
            "evaluation_input",
            dataclasses.replace(package.evaluation_input, s2_run_identity="different-run"),
        ),
    ]
    for field_name, tampered_value in tamper_fields:
        tampered = dataclasses.replace(package, **{field_name: tampered_value})
        identity, canonical = compute_pairing_package_identity_hashes(tampered)
        assert identity != package.pairing_package_identity or canonical != package.canonical_hash


def test_d_test_partition_rejected() -> None:
    with pytest.raises(TrainValPairingPackageInvariantError):
        build_candidate_train_validation_pairing_package(
            partition="TEST",  # type: ignore[arg-type]
            partition_identity=ACCEPTED_TRAIN_PARTITION_IDENTITY,
            evaluation_input=_evaluation(),
            forecast_cutoff_authority_identity=_FORECAST_CUTOFF_AUTHORITY,
        )


def test_e_row_set_binding_mismatch_rejected() -> None:
    package = _candidate_package()
    tampered = dataclasses.replace(package, s2_binding_row_set_hash="b" * 64)
    with pytest.raises(TrainValPairingPackageInvariantError):
        validate_pairing_package_invariants(tampered)


def test_f_native_float_rejected() -> None:
    bad_row = dataclasses.replace(_row(), actual_value_kg=9.0)  # type: ignore[arg-type]
    with pytest.raises(S3DecimalAssertionError):
        build_candidate_train_validation_pairing_package(
            partition="TRAIN",
            partition_identity=ACCEPTED_TRAIN_PARTITION_IDENTITY,
            evaluation_input=_evaluation([bad_row]),
            forecast_cutoff_authority_identity=_FORECAST_CUTOFF_AUTHORITY,
        )


def test_g_authority_record_deterministic_replay() -> None:
    package = _candidate_package()
    first = build_candidate_authority_record(
        schema_version=TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1,
        pairing_package_identity=package.pairing_package_identity,
        s2_binding_row_set_hash=package.s2_binding_row_set_hash,
        permitted_partitions=("TRAIN",),
        issuer_identity_or_version="issuer-v1",
    )
    second = build_candidate_authority_record(
        schema_version=TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1,
        pairing_package_identity=package.pairing_package_identity,
        s2_binding_row_set_hash=package.s2_binding_row_set_hash,
        permitted_partitions=("TRAIN",),
        issuer_identity_or_version="issuer-v1",
    )
    assert first == second
    assert verify_authority_record_hash_replay(first)


def test_h_authority_record_tamper_detection() -> None:
    package = _candidate_package()
    record = build_candidate_authority_record(
        schema_version=TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1,
        pairing_package_identity=package.pairing_package_identity,
        s2_binding_row_set_hash=package.s2_binding_row_set_hash,
        permitted_partitions=("TRAIN",),
        issuer_identity_or_version="issuer-v1",
    )
    tampered = dataclasses.replace(record, pairing_package_identity="f" * 64)
    assert not verify_authority_record_hash_replay(tampered)


@pytest.mark.parametrize(
    "issued_schema_versions",
    [frozenset({TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1})],
)
def test_i_schema_allowlist_alone_insufficient(issued_schema_versions: frozenset[str]) -> None:
    package = _candidate_package()
    record = build_candidate_authority_record(
        schema_version=TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1,
        pairing_package_identity=package.pairing_package_identity,
        s2_binding_row_set_hash=package.s2_binding_row_set_hash,
        permitted_partitions=("TRAIN",),
        issuer_identity_or_version="issuer-v1",
    )
    authority = _partition_authority(
        package,
        authority_record_identity=record.authority_record_identity,
    )
    blocker = verify_train_validation_coverage_authority(
        package.evaluation_input,
        authority,
        published_registry=TrustedPublishedPairingPackageRegistry(),
        issued_registry=TrustedIssuedAuthorityRegistry(),
        issued_schema_versions=issued_schema_versions,
    )
    assert blocker == "TRAIN_VALIDATION_AUTHORITY_RECORD_NOT_FOUND"


def test_j_authority_record_present_package_missing() -> None:
    package = _candidate_package()
    record = build_candidate_authority_record(
        schema_version=TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1,
        pairing_package_identity=package.pairing_package_identity,
        s2_binding_row_set_hash=package.s2_binding_row_set_hash,
        permitted_partitions=("TRAIN",),
        issuer_identity_or_version="issuer-v1",
    )
    authority = _partition_authority(
        package,
        authority_record_identity=record.authority_record_identity,
    )
    issued = TrustedIssuedAuthorityRegistry({record.authority_record_identity: record})
    blocker = verify_train_validation_coverage_authority(
        package.evaluation_input,
        authority,
        published_registry=TrustedPublishedPairingPackageRegistry(),
        issued_registry=issued,
        issued_schema_versions=frozenset({TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1}),
    )
    assert blocker == "TRAIN_VALIDATION_PAIRING_PACKAGE_NOT_PUBLISHED"


def test_k_package_present_binding_mismatch() -> None:
    package = _candidate_package()
    mismatched_evaluation = dataclasses.replace(
        package.evaluation_input,
        s2_binding_row_set_hash="f" * 64,
    )
    blocker = _full_verifier_blocker(
        package,
        evaluation_input=mismatched_evaluation,
    )
    assert blocker == "TRAIN_VALIDATION_PARTITION_AUTHORITY_BINDING_MISMATCH"


def test_l_caller_crafted_authority_without_registry_record_blocked() -> None:
    package = _candidate_package()
    authority = _partition_authority(package)
    blocker = verify_train_validation_coverage_authority(
        package.evaluation_input,
        authority,
        published_registry=TrustedPublishedPairingPackageRegistry(
            {package.pairing_package_identity: package}
        ),
        issued_registry=TrustedIssuedAuthorityRegistry(),
        issued_schema_versions=frozenset({TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1}),
    )
    assert blocker == "TRAIN_VALIDATION_AUTHORITY_RECORD_NOT_FOUND"


def test_m_production_registries_empty_blocks_formal_execution() -> None:
    package = _candidate_package()
    record = build_candidate_authority_record(
        schema_version=TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1,
        pairing_package_identity=package.pairing_package_identity,
        s2_binding_row_set_hash=package.s2_binding_row_set_hash,
        permitted_partitions=("TRAIN",),
        issuer_identity_or_version="issuer-v1",
    )
    assessment = assess_train_validation_coverage_execution(
        package.evaluation_input,
        breakdown_specs=(_SPEC,),
        partition_authority=_partition_authority(
            package,
            authority_record_identity=record.authority_record_identity,
        ),
    )
    assert assessment.execution_status == "NOT_COMPUTABLE_OR_BLOCKED"
    assert assessment.results == ()
    assert assessment.blocker_reason == "TRAIN_VALIDATION_PARTITION_AUTHORITY_NOT_ISSUED"
    assert _ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSIONS == frozenset()


def test_n_coverage_regression_unchanged() -> None:
    from backend.app.forecast_quality.quantile_coverage import compute_upper_quantile_coverage

    row = _row()
    result = compute_upper_quantile_coverage(_evaluation([row]), _SPEC, SupportedQuantile.P50)
    assert result.covered_count == 1
    assert result.metric_value == Decimal("1.000000")


def test_accepted_authorities_bound_in_candidate() -> None:
    package = _candidate_package()
    assert package.actuals_authority_identity == V0_3_S3_ACTUALS_AUTHORITY
    assert package.forecast_authority_identity == V0_3_S3_FORECASTS_AUTHORITY


def test_exact_actual_pairing_policy_version_not_invented_on_main() -> None:
    assert EXACT_ACTUAL_PAIRING_POLICY_VERSION_STATUS == "NOT_ISSUED"
    assert EXACT_ACTUAL_PAIRING_POLICY_VERSION_NOT_ISSUED == ""
    assert FROZEN_EXACT_ACTUAL_PAIRING_RULE == "EXACT_ACTUAL_PAIRED"
    package = _candidate_package()
    assert package.exact_actual_pairing_policy_version == ""


def test_registry_source_mapping_mutation_does_not_change_snapshot() -> None:
    package = _candidate_package()
    source: dict[str, object] = {package.pairing_package_identity: package}
    registry = TrustedPublishedPairingPackageRegistry(source)
    assert registry.count() == 1
    source["f" * 64] = package
    assert registry.count() == 1


def test_registry_direct_backing_mutation_rejected() -> None:
    package = _candidate_package()
    registry = TrustedPublishedPairingPackageRegistry({package.pairing_package_identity: package})
    with pytest.raises(TypeError):
        registry._records[package.pairing_package_identity] = package  # type: ignore[index]


def test_production_registries_remain_empty() -> None:
    assert PRODUCTION_TRUSTED_PUBLISHED_PAIRING_PACKAGE_REGISTRY.count() == 0
    assert PRODUCTION_TRUSTED_ISSUED_AUTHORITY_REGISTRY.count() == 0


def test_published_package_invariants_reverified_at_execution_gate() -> None:
    package = _candidate_package()
    forged = dataclasses.replace(package, actuals_authority_identity="forged-authority")
    identity, canonical = compute_pairing_package_identity_hashes(forged)
    forged = dataclasses.replace(
        forged,
        pairing_package_identity=identity,
        canonical_hash=canonical,
    )
    assert verify_pairing_package_hash_replay(forged)
    record = build_candidate_authority_record(
        schema_version=TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1,
        pairing_package_identity=forged.pairing_package_identity,
        s2_binding_row_set_hash=forged.s2_binding_row_set_hash,
        permitted_partitions=("TRAIN",),
        issuer_identity_or_version="issuer-v1",
    )
    authority = _partition_authority(
        forged,
        authority_record_identity=record.authority_record_identity,
    )
    blocker = verify_train_validation_coverage_authority(
        forged.evaluation_input,
        authority,
        published_registry=TrustedPublishedPairingPackageRegistry(
            {forged.pairing_package_identity: forged}
        ),
        issued_registry=TrustedIssuedAuthorityRegistry({record.authority_record_identity: record}),
        issued_schema_versions=frozenset({TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1}),
        issued_pairing_policy_versions=frozenset({TRAIN_VAL_PAIRING_POLICY_V1}),
    )
    assert blocker == "TRAIN_VALIDATION_PAIRING_PACKAGE_INVARIANT_VIOLATION"


def test_empty_exact_policy_blocks_published_execution() -> None:
    package = _candidate_package()
    record = build_candidate_authority_record(
        schema_version=TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1,
        pairing_package_identity=package.pairing_package_identity,
        s2_binding_row_set_hash=package.s2_binding_row_set_hash,
        permitted_partitions=("TRAIN",),
        issuer_identity_or_version="issuer-v1",
    )
    authority = _partition_authority(
        package,
        authority_record_identity=record.authority_record_identity,
    )
    blocker = verify_train_validation_coverage_authority(
        package.evaluation_input,
        authority,
        published_registry=TrustedPublishedPairingPackageRegistry(
            {package.pairing_package_identity: package}
        ),
        issued_registry=TrustedIssuedAuthorityRegistry({record.authority_record_identity: record}),
        issued_schema_versions=frozenset({TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1}),
        issued_pairing_policy_versions=frozenset({TRAIN_VAL_PAIRING_POLICY_V1}),
        issued_exact_actual_pairing_policy_versions=frozenset(
            {_TEST_EXACT_ACTUAL_PAIRING_POLICY_VERSION}
        ),
    )
    assert blocker == "TRAIN_VALIDATION_EXACT_ACTUAL_PAIRING_POLICY_NOT_ISSUED"


def test_unissued_non_empty_exact_policy_blocks_published_execution() -> None:
    package = _candidate_package()
    blocker = _full_verifier_blocker(
        package,
        exact_policy_version="unissued-exact-policy-v1",
        issued_exact=frozenset({_TEST_EXACT_ACTUAL_PAIRING_POLICY_VERSION}),
    )
    assert blocker == "TRAIN_VALIDATION_EXACT_ACTUAL_PAIRING_POLICY_NOT_ISSUED"


def test_forged_train_partition_identity_sha256_rejected() -> None:
    package = _candidate_package()
    forged = dataclasses.replace(
        package,
        partition_identity=dataclasses.replace(
            package.partition_identity,
            partition_identity_sha256="f" * 64,
        ),
    )
    with pytest.raises(TrainValPairingPackageInvariantError):
        validate_pairing_package_candidate_invariants(forged)


def test_forged_train_content_sha256_rejected() -> None:
    package = _candidate_package()
    forged = dataclasses.replace(
        package,
        partition_identity=dataclasses.replace(
            package.partition_identity,
            content_sha256="f" * 64,
        ),
    )
    with pytest.raises(TrainValPairingPackageInvariantError):
        validate_pairing_package_candidate_invariants(forged)


def test_forged_train_date_range_rejected() -> None:
    package = _candidate_package()
    forged = dataclasses.replace(
        package,
        partition_identity=dataclasses.replace(
            package.partition_identity,
            partition_end_date=date(2026, 2, 1),
        ),
    )
    with pytest.raises(TrainValPairingPackageInvariantError):
        validate_pairing_package_candidate_invariants(forged)


def test_forged_validation_partition_identity_sha256_rejected() -> None:
    package = _candidate_package(
        partition="VALIDATION",
        partition_identity=ACCEPTED_VALIDATION_PARTITION_IDENTITY,
    )
    forged = dataclasses.replace(
        package,
        partition_identity=dataclasses.replace(
            package.partition_identity,
            partition_identity_sha256="f" * 64,
        ),
    )
    with pytest.raises(TrainValPairingPackageInvariantError):
        validate_pairing_package_candidate_invariants(forged)


def test_production_exact_actual_pairing_policy_versions_empty() -> None:
    assert ISSUED_EXACT_ACTUAL_PAIRING_POLICY_VERSIONS == frozenset()
