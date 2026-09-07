"""Synthetic tests for the S3-C legal backtest package implementation.

The 35 contract themes covered here are:

1 exact package and partition binding; 2 row-order invariance; 3 exact
target-key pairing; 4 duplicate target rejection; 5 missing actual rejection;
6 TEST exclusion; 7 sealed TEST state; 8 missing pairing rejection; 9
untrusted pairing rejection; 10 missing authority rejection; 11 untrusted
authority rejection; 12 row-set binding; 13 cross-partition overlap; 14
missing exact actual; 15 missing forecast authority; 16 PIT visibility; 17
empty cutoff set; 18 incomplete cutoff set; 19 cutoff identity; 20 native
float rejection; 21 source identity; 22 partition identity; 23 deterministic
package identity; 24 two-stage self-reference; 25 package tamper detection;
26 generic unresolved branch; 27 generic REQUIRED=false branch; 28 generic
REQUIRED=true unavailable branch; 29 immutable diagnostics; 30 no TEST
access; 31 no executor; 32 no comparison result; 33 no MAPE/bias/coverage;
34 no peak/cumulative metrics; 35 deterministic fail-closed behavior.
"""

from __future__ import annotations

import dataclasses
import inspect
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

import backend.app.forecast_quality.s3_legal_backtest_package as legal_module
from backend.app.forecast_quality.enums import FrozenVersion, SupportedQuantile
from backend.app.forecast_quality.quantile_coverage import (
    TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1,
    TrainValidationCoveragePartitionAuthority,
)
from backend.app.forecast_quality.s3_legal_backtest_package import (
    FORECAST_SELECTION_POLICY,
    TEST_PARTITION_STATUS_SEALED_ABSENT,
    GenericIncumbentForecastArtifactRequirement,
    S3GenericIncumbentForecastArtifactRequirement,
    S3LegalBacktestForecastCutoff,
    S3LegalBacktestForecastCutoffSet,
    S3LegalBacktestPackageBlocker,
    S3LegalBacktestPackageResult,
    S3LegalBacktestPackageStatus,
    _build_s3_legal_backtest_package_with_registries,
    build_s3_legal_backtest_package,
    build_s3_legal_backtest_package_semantic_payload,
    compute_forecast_cutoff_set_identity_sha256,
    compute_s3_legal_backtest_package_identity_hashes,
    verify_s3_legal_backtest_package_hash_replay,
)
from backend.app.forecast_quality.schemas import S3BindingRow, S3EvaluationInput
from backend.app.forecast_quality.train_val_pairing import (
    ACCEPTED_SOURCE_DATASET_IDENTITY,
    ACCEPTED_TRAIN_PARTITION_IDENTITY,
    ACCEPTED_VALIDATION_PARTITION_IDENTITY,
    EXACT_ACTUAL_PAIRING_POLICY_V1,
    TRAIN_VAL_PAIRING_POLICY_V1,
    PartitionIdentity,
    build_candidate_train_validation_pairing_package,
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
    build_candidate_authority_record,
)
from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    OFFICIAL_TRAIN_ROW_COUNT,
    OFFICIAL_VALIDATION_ROW_COUNT,
)

_CUTOFF = datetime(2026, 2, 16, tzinfo=UTC)
_LATER_CUTOFF = _CUTOFF + timedelta(days=1)
_CUTOFF_AUTHORITY = "d" * 64
_MODEL = legal_module.REVIEWED_MODEL_ID
_SCHEMA = TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1


def _row(
    *,
    prefix: str,
    farm: str,
    actual: str = "9",
    cutoff: datetime = _CUTOFF,
    forecast: str = "10",
) -> S3BindingRow:
    return S3BindingRow(
        forecast_business_key=f"forecast-{prefix}",
        actual_physical_key=f"physical-{prefix}",
        stable_actual_identity=f"stable-{prefix}",
        forecast_value_kg=Decimal(forecast),
        actual_value_kg=Decimal(actual),
        forecast_quantile=SupportedQuantile.P50,
        forecast_horizon_days=7,
        forecast_target_date=date(2026, 2, 23),
        forecast_cutoff_at=cutoff,
        s2_status="COMPARABLE",
        season_business_key="season-2025",
        farm_business_key=farm,
        subfarm_business_key="subfarm-a",
        variety_business_key="variety-a",
        model_identity=_MODEL,
        actual_visibility_timestamp=cutoff,
    )


def _evaluation(rows: tuple[S3BindingRow, ...], prefix: str) -> S3EvaluationInput:
    return S3EvaluationInput(
        rows=rows,
        s2_run_identity=f"{prefix}-run",
        s2_manifest_identity=f"{prefix}-manifest",
        s2_binding_row_set_hash=compute_s3_binding_row_set_hash(rows),
        metric_policy_version=FrozenVersion.METRIC_INPUT_MASK_V1,
        baseline_policy_version=FrozenVersion.NAIVE_BASELINE_POLICY_V1,
    )


@dataclasses.dataclass(frozen=True)
class _Fixture:
    materialization: TrainValidationPairingMaterializationResult
    train_authority: TrainValidationCoveragePartitionAuthority
    validation_authority: TrainValidationCoveragePartitionAuthority
    published_registry: TrustedPublishedPairingPackageRegistry
    issued_registry: TrustedIssuedAuthorityRegistry
    cutoff_set: S3LegalBacktestForecastCutoffSet


def _fixture(
    *,
    train_rows: tuple[S3BindingRow, ...] | None = None,
    validation_rows: tuple[S3BindingRow, ...] | None = None,
    train_partition_identity: PartitionIdentity = ACCEPTED_TRAIN_PARTITION_IDENTITY,
    validation_partition_identity: PartitionIdentity = ACCEPTED_VALIDATION_PARTITION_IDENTITY,
) -> _Fixture:
    train_rows = train_rows or (
        _row(prefix="train-0", farm="farm-train-0"),
        _row(prefix="train-1", farm="farm-train-1", actual="12", forecast="15"),
    )
    validation_rows = validation_rows or (
        _row(prefix="validation-0", farm="farm-validation-0"),
        _row(
            prefix="validation-1",
            farm="farm-validation-1",
            actual="20",
            forecast="25",
        ),
    )
    train_input = _evaluation(train_rows, "train")
    validation_input = _evaluation(validation_rows, "validation")
    train_package = build_candidate_train_validation_pairing_package(
        partition="TRAIN",
        partition_identity=train_partition_identity,
        evaluation_input=train_input,
        forecast_cutoff_authority_identity=_CUTOFF_AUTHORITY,
        exact_actual_pairing_policy_version=EXACT_ACTUAL_PAIRING_POLICY_V1,
        pairing_policy_version=TRAIN_VAL_PAIRING_POLICY_V1,
    )
    validation_package = build_candidate_train_validation_pairing_package(
        partition="VALIDATION",
        partition_identity=validation_partition_identity,
        evaluation_input=validation_input,
        forecast_cutoff_authority_identity=_CUTOFF_AUTHORITY,
        exact_actual_pairing_policy_version=EXACT_ACTUAL_PAIRING_POLICY_V1,
        pairing_policy_version=TRAIN_VAL_PAIRING_POLICY_V1,
    )
    train_record = build_candidate_authority_record(
        schema_version=_SCHEMA,
        pairing_package_identity=train_package.pairing_package_identity,
        s2_binding_row_set_hash=train_package.s2_binding_row_set_hash,
        permitted_partitions=("TRAIN",),
        issuer_identity_or_version="synthetic-test-issuer-v1",
    )
    validation_record = build_candidate_authority_record(
        schema_version=_SCHEMA,
        pairing_package_identity=validation_package.pairing_package_identity,
        s2_binding_row_set_hash=validation_package.s2_binding_row_set_hash,
        permitted_partitions=("VALIDATION",),
        issuer_identity_or_version="synthetic-test-issuer-v1",
    )
    train_authority = TrainValidationCoveragePartitionAuthority(
        authority_record_identity=train_record.authority_record_identity,
        schema_version=_SCHEMA,
        pairing_package_identity=train_package.pairing_package_identity,
        s2_binding_row_set_hash=train_package.s2_binding_row_set_hash,
        permitted_partitions=("TRAIN",),
    )
    validation_authority = TrainValidationCoveragePartitionAuthority(
        authority_record_identity=validation_record.authority_record_identity,
        schema_version=_SCHEMA,
        pairing_package_identity=validation_package.pairing_package_identity,
        s2_binding_row_set_hash=validation_package.s2_binding_row_set_hash,
        permitted_partitions=("VALIDATION",),
    )
    materialization = TrainValidationPairingMaterializationResult(
        completed=True,
        blocker=TrainValidationPairingMaterializationBlocker.NONE,
        train_evaluation_input=train_input,
        validation_evaluation_input=validation_input,
        train_pairing_package=train_package,
        validation_pairing_package=validation_package,
    )
    cutoff_set = S3LegalBacktestForecastCutoffSet.from_members(
        (
            S3LegalBacktestForecastCutoff(
                forecast_cutoff_at=_CUTOFF,
                model_identity=_MODEL,
                selection_policy=FORECAST_SELECTION_POLICY,
                forecast_authority_identity=_CUTOFF_AUTHORITY,
            ),
        )
    )
    train_source_row = MaterializableRow(
        season="season-2025",
        farm="farm-source",
        subfarm="subfarm-source",
        variety="variety-source",
        harvest_business_date=ACCEPTED_TRAIN_PARTITION_IDENTITY.partition_start_date,
        actual_harvest_quantity_kg=Decimal("1"),
        source_row_identity="source-train-start",
        cleaned_row_identity="cleaned-train-start",
        pit_visibility_identity="pit-train-start",
        revision_winner_identity="revision-train-start",
    )
    train_source_end = dataclasses.replace(
        train_source_row,
        harvest_business_date=ACCEPTED_TRAIN_PARTITION_IDENTITY.partition_end_date,
        source_row_identity="source-train-end",
    )
    validation_source_row = dataclasses.replace(
        train_source_row,
        harvest_business_date=ACCEPTED_VALIDATION_PARTITION_IDENTITY.partition_start_date,
        source_row_identity="source-validation-start",
    )
    validation_source_end = dataclasses.replace(
        validation_source_row,
        harvest_business_date=ACCEPTED_VALIDATION_PARTITION_IDENTITY.partition_end_date,
        source_row_identity="source-validation-end",
    )
    official_partitions = OfficialPartitionRows(
        train_rows=(train_source_row,)
        + (train_source_row,) * (OFFICIAL_TRAIN_ROW_COUNT - 2)
        + (train_source_end,),
        validation_rows=(validation_source_row,)
        + (validation_source_row,) * (OFFICIAL_VALIDATION_ROW_COUNT - 2)
        + (validation_source_end,),
        train_content_sha256=ACCEPTED_TRAIN_PARTITION_IDENTITY.content_sha256,
        validation_content_sha256=ACCEPTED_VALIDATION_PARTITION_IDENTITY.content_sha256,
    )
    materialization = dataclasses.replace(
        materialization,
        official_partitions=official_partitions,
    )
    return _Fixture(
        materialization=materialization,
        train_authority=train_authority,
        validation_authority=validation_authority,
        published_registry=TrustedPublishedPairingPackageRegistry(
            {
                train_package.pairing_package_identity: train_package,
                validation_package.pairing_package_identity: validation_package,
            }
        ),
        issued_registry=TrustedIssuedAuthorityRegistry(
            {
                train_record.authority_record_identity: train_record,
                validation_record.authority_record_identity: validation_record,
            }
        ),
        cutoff_set=cutoff_set,
    )


def _legal_result(
    fixture: _Fixture,
    *,
    materialization: TrainValidationPairingMaterializationResult | None = None,
    train_authority: TrainValidationCoveragePartitionAuthority | None = None,
    validation_authority: TrainValidationCoveragePartitionAuthority | None = None,
    cutoff_set: S3LegalBacktestForecastCutoffSet
    | tuple[S3LegalBacktestForecastCutoff, ...]
    | None = None,
    cutoff_set_complete: bool = True,
    generic_requirement: S3GenericIncumbentForecastArtifactRequirement | None = None,
    test_partition_status: str = TEST_PARTITION_STATUS_SEALED_ABSENT,
    use_fixture_authorities: bool = True,
) -> S3LegalBacktestPackageResult:
    selected_cutoff_set = fixture.cutoff_set if cutoff_set is None else cutoff_set
    return _build_s3_legal_backtest_package_with_registries(
        pairing_materialization=materialization or fixture.materialization,
        train_partition_authority=(
            fixture.train_authority
            if use_fixture_authorities and train_authority is None
            else train_authority
        ),
        validation_partition_authority=(
            fixture.validation_authority
            if use_fixture_authorities and validation_authority is None
            else validation_authority
        ),
        forecast_cutoff_set=selected_cutoff_set,
        published_registry=fixture.published_registry,
        issued_registry=fixture.issued_registry,
        issued_schema_versions=frozenset({_SCHEMA}),
        cutoff_set_complete=cutoff_set_complete,
        generic_artifact_requirement=generic_requirement,
        test_partition_status=test_partition_status,
    )


def test_01_production_wrapper_is_blocked_by_current_authority_state() -> None:
    fixture = _fixture()
    before = (
        PRODUCTION_TRUSTED_PUBLISHED_PAIRING_PACKAGE_REGISTRY.count(),
        PRODUCTION_TRUSTED_ISSUED_AUTHORITY_REGISTRY.count(),
    )
    result = build_s3_legal_backtest_package(
        pairing_materialization=fixture.materialization,
        train_partition_authority=fixture.train_authority,
        validation_partition_authority=fixture.validation_authority,
        forecast_cutoff_set=fixture.cutoff_set,
    )
    after = (
        PRODUCTION_TRUSTED_PUBLISHED_PAIRING_PACKAGE_REGISTRY.count(),
        PRODUCTION_TRUSTED_ISSUED_AUTHORITY_REGISTRY.count(),
    )
    assert result.status is S3LegalBacktestPackageStatus.BLOCKED
    assert (
        S3LegalBacktestPackageBlocker.HISTORICAL_CUTOFF_SET_INCOMPLETE.value in result.blocker_codes
    )
    assert (
        S3LegalBacktestPackageBlocker.GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIREMENT_UNRESOLVED.value
        in result.blocker_codes
    )
    assert before == after == (0, 0)


def test_02_hypothetical_legal_fixture_is_legal() -> None:
    fixture = _fixture()
    result = _legal_result(fixture)
    assert result.status is S3LegalBacktestPackageStatus.LEGAL
    assert result.package is not None
    assert result.blocker_codes == ()


def test_03_source_and_partition_identity_are_bound() -> None:
    fixture = _fixture()
    train_package = fixture.materialization.train_pairing_package
    validation_package = fixture.materialization.validation_pairing_package
    assert train_package is not None
    assert validation_package is not None
    assert train_package.source_dataset_identity == ACCEPTED_SOURCE_DATASET_IDENTITY
    assert train_package.partition_identity == ACCEPTED_TRAIN_PARTITION_IDENTITY
    assert validation_package.partition_identity == ACCEPTED_VALIDATION_PARTITION_IDENTITY


def test_04_row_order_does_not_change_package_semantics() -> None:
    fixture = _fixture()
    validation_input = fixture.materialization.validation_evaluation_input
    assert validation_input is not None
    reordered = dataclasses.replace(
        fixture.materialization,
        validation_evaluation_input=dataclasses.replace(
            validation_input,
            rows=tuple(reversed(tuple(validation_input.rows))),
        ),
    )
    first = _legal_result(fixture)
    second = _legal_result(fixture, materialization=reordered)
    assert first.status is second.status is S3LegalBacktestPackageStatus.LEGAL
    assert first.package is not None and second.package is not None
    assert first.package.package_identity_sha256 == second.package.package_identity_sha256


def test_05_exact_target_key_duplicate_fails_closed() -> None:
    first = _row(prefix="validation-duplicate", farm="farm-validation")
    fixture = _fixture(
        validation_rows=(
            first,
            dataclasses.replace(first, forecast_business_key=first.forecast_business_key),
        ),
    )
    result = _legal_result(fixture)
    assert result.status is S3LegalBacktestPackageStatus.BLOCKED
    assert S3LegalBacktestPackageBlocker.MISSING_EXACT_ACTUAL_PAIRING.value in result.blocker_codes


def test_06_missing_exact_actual_fails_closed() -> None:
    fixture = _fixture()
    package = fixture.materialization.validation_pairing_package
    assert package is not None
    row = package.evaluation_input.rows[0]
    replacement = dataclasses.replace(
        row,
        actual_physical_key=None,
        stable_actual_identity=None,
        actual_value_kg=None,
    )
    validation_input = dataclasses.replace(
        package.evaluation_input,
        rows=(replacement,) + tuple(package.evaluation_input.rows[1:]),
    )
    tampered_package = dataclasses.replace(package, evaluation_input=validation_input)
    materialization = dataclasses.replace(
        fixture.materialization,
        validation_pairing_package=tampered_package,
    )
    result = _legal_result(fixture, materialization=materialization)
    assert S3LegalBacktestPackageBlocker.MISSING_EXACT_ACTUAL_PAIRING.value in result.blocker_codes


def test_07_test_partition_presence_and_sealing_fail_closed() -> None:
    fixture = _fixture()
    result = _legal_result(
        fixture,
        materialization=dataclasses.replace(
            fixture.materialization,
            test_row_count=1,
        ),
        test_partition_status="PRESENT",
    )
    assert S3LegalBacktestPackageBlocker.TEST_PARTITION_PRESENT.value in result.blocker_codes
    assert S3LegalBacktestPackageBlocker.TEST_NOT_SEALED.value in result.blocker_codes


def test_08_missing_pairing_packages_fail_closed() -> None:
    fixture = _fixture()
    result = _legal_result(
        fixture,
        materialization=dataclasses.replace(
            fixture.materialization,
            train_pairing_package=None,
            validation_pairing_package=None,
        ),
        train_authority=None,
        validation_authority=None,
    )
    assert S3LegalBacktestPackageBlocker.TRAIN_PAIRING_PACKAGE_MISSING.value in result.blocker_codes
    assert (
        S3LegalBacktestPackageBlocker.VALIDATION_PAIRING_PACKAGE_MISSING.value
        in result.blocker_codes
    )


def test_09_untrusted_pairing_registry_fails_closed() -> None:
    fixture = _fixture()
    empty_fixture = dataclasses.replace(
        fixture,
        published_registry=TrustedPublishedPairingPackageRegistry(),
    )
    result = _build_s3_legal_backtest_package_with_registries(
        pairing_materialization=empty_fixture.materialization,
        train_partition_authority=empty_fixture.train_authority,
        validation_partition_authority=empty_fixture.validation_authority,
        forecast_cutoff_set=empty_fixture.cutoff_set,
        published_registry=empty_fixture.published_registry,
        issued_registry=empty_fixture.issued_registry,
        issued_schema_versions=frozenset({_SCHEMA}),
    )
    assert S3LegalBacktestPackageBlocker.TRAIN_AUTHORITY_NOT_TRUSTED.value in result.blocker_codes


def test_10_missing_authority_records_fail_closed() -> None:
    fixture = _fixture()
    result = _legal_result(
        fixture,
        train_authority=None,
        validation_authority=None,
        use_fixture_authorities=False,
    )
    assert (
        S3LegalBacktestPackageBlocker.TRAIN_AUTHORITY_RECORD_MISSING.value in result.blocker_codes
    )
    assert (
        S3LegalBacktestPackageBlocker.VALIDATION_AUTHORITY_RECORD_MISSING.value
        in result.blocker_codes
    )


def test_11_wrong_authority_binding_is_not_trusted() -> None:
    fixture = _fixture()
    train_package = fixture.materialization.train_pairing_package
    assert train_package is not None
    wrong = dataclasses.replace(
        fixture.validation_authority,
        pairing_package_identity=train_package.pairing_package_identity,
    )
    result = _legal_result(fixture, validation_authority=wrong)
    assert (
        S3LegalBacktestPackageBlocker.VALIDATION_AUTHORITY_NOT_TRUSTED.value in result.blocker_codes
    )


def test_12_s2_row_set_hash_mismatch_fails_closed() -> None:
    fixture = _fixture()
    train_input = fixture.materialization.train_evaluation_input
    assert train_input is not None
    tampered = dataclasses.replace(train_input, s2_binding_row_set_hash="e" * 64)
    result = _legal_result(
        fixture,
        materialization=dataclasses.replace(
            fixture.materialization,
            train_evaluation_input=tampered,
        ),
    )
    assert (
        S3LegalBacktestPackageBlocker.S2_BINDING_ROW_SET_HASH_MISMATCH.value in result.blocker_codes
    )


def test_13_cross_partition_overlap_fails_closed() -> None:
    fixture = _fixture()
    result = _legal_result(
        fixture,
        materialization=dataclasses.replace(
            fixture.materialization,
            cross_partition_row_count=1,
        ),
    )
    assert S3LegalBacktestPackageBlocker.CROSS_PARTITION_ROW_OVERLAP.value in result.blocker_codes


def test_14_missing_forecast_binding_authority_fails_closed() -> None:
    fixture = _fixture()
    package = fixture.materialization.train_pairing_package
    assert package is not None
    tampered = dataclasses.replace(package, forecast_cutoff_authority_identity="")
    result = _legal_result(
        fixture,
        materialization=dataclasses.replace(
            fixture.materialization,
            train_pairing_package=tampered,
        ),
    )
    assert (
        S3LegalBacktestPackageBlocker.MISSING_EXACT_FORECAST_BINDING_AUTHORITY.value
        in result.blocker_codes
    )


def test_15_forecast_outside_declared_cutoff_is_not_pit_visible() -> None:
    fixture = _fixture()
    package = fixture.materialization.validation_pairing_package
    assert package is not None
    row = package.evaluation_input.rows[0]
    later_row = dataclasses.replace(row, forecast_cutoff_at=_LATER_CUTOFF)
    validation_input = dataclasses.replace(
        package.evaluation_input,
        rows=(later_row,) + tuple(package.evaluation_input.rows[1:]),
    )
    tampered_package = dataclasses.replace(package, evaluation_input=validation_input)
    result = _legal_result(
        fixture,
        materialization=dataclasses.replace(
            fixture.materialization,
            validation_pairing_package=tampered_package,
        ),
    )
    assert (
        S3LegalBacktestPackageBlocker.FORECAST_VALUE_NOT_PIT_VISIBLE.value in result.blocker_codes
    )


def test_16_empty_cutoff_set_is_blocked() -> None:
    fixture = _fixture()
    empty = S3LegalBacktestForecastCutoffSet.from_members(())
    result = _legal_result(fixture, cutoff_set=empty)
    assert S3LegalBacktestPackageBlocker.HISTORICAL_CUTOFF_SET_EMPTY.value in result.blocker_codes


def test_17_incomplete_cutoff_set_is_blocked() -> None:
    fixture = _fixture()
    result = _legal_result(fixture, cutoff_set_complete=False)
    assert (
        S3LegalBacktestPackageBlocker.HISTORICAL_CUTOFF_SET_INCOMPLETE.value in result.blocker_codes
    )


def test_18_cutoff_set_identity_replays_and_tamper_fails() -> None:
    fixture = _fixture()
    assert (
        compute_forecast_cutoff_set_identity_sha256(fixture.cutoff_set.members)
        == fixture.cutoff_set.identity_sha256
    )
    tampered = dataclasses.replace(fixture.cutoff_set, identity_sha256="a" * 64)
    result = _legal_result(fixture, cutoff_set=tampered)
    assert (
        S3LegalBacktestPackageBlocker.HISTORICAL_CUTOFF_SET_IDENTITY_MISMATCH.value
        in result.blocker_codes
    )


def test_19_native_float_is_a_structural_blocker() -> None:
    fixture = _fixture()
    package = fixture.materialization.train_pairing_package
    assert package is not None
    row = package.evaluation_input.rows[0]
    float_row = dataclasses.replace(row, forecast_value_kg=1.0)  # type: ignore[arg-type]
    tampered_package = dataclasses.replace(
        package,
        evaluation_input=dataclasses.replace(
            package.evaluation_input,
            rows=(float_row,) + tuple(package.evaluation_input.rows[1:]),
        ),
    )
    result = _legal_result(
        fixture,
        materialization=dataclasses.replace(
            fixture.materialization,
            train_pairing_package=tampered_package,
        ),
    )
    assert S3LegalBacktestPackageBlocker.NATIVE_FLOAT_FORBIDDEN.value in result.blocker_codes


def test_20_partition_identity_tamper_fails_closed() -> None:
    fixture = _fixture()
    package = fixture.materialization.validation_pairing_package
    assert package is not None
    tampered = dataclasses.replace(package, partition_identity=ACCEPTED_TRAIN_PARTITION_IDENTITY)
    result = _legal_result(
        fixture,
        materialization=dataclasses.replace(
            fixture.materialization,
            validation_pairing_package=tampered,
        ),
    )
    assert (
        S3LegalBacktestPackageBlocker.VALIDATION_PARTITION_IDENTITY_MISMATCH.value
        in result.blocker_codes
    )


def test_21_source_identity_tamper_fails_closed() -> None:
    fixture = _fixture()
    package = fixture.materialization.train_pairing_package
    assert package is not None
    wrong_source = dataclasses.replace(
        package.source_dataset_identity,
        dataset_version="untrusted-version",
    )
    tampered = dataclasses.replace(package, source_dataset_identity=wrong_source)
    result = _legal_result(
        fixture,
        materialization=dataclasses.replace(
            fixture.materialization,
            train_pairing_package=tampered,
        ),
    )
    assert (
        S3LegalBacktestPackageBlocker.SOURCE_DATASET_IDENTITY_MISMATCH.value in result.blocker_codes
    )


def test_22_package_identity_is_deterministic() -> None:
    first = _legal_result(_fixture())
    second = _legal_result(_fixture())
    assert first.package == second.package
    assert first.package is not None
    assert verify_s3_legal_backtest_package_hash_replay(first.package)


def test_23_two_stage_identity_has_blank_self_references() -> None:
    result = _legal_result(_fixture())
    assert result.package is not None
    payload = build_s3_legal_backtest_package_semantic_payload(result.package)
    assert payload["package_identity_sha256"] == ""
    assert payload["canonical_hash_sha256"] == ""
    assert compute_s3_legal_backtest_package_identity_hashes(result.package) == (
        result.package.package_identity_sha256,
        result.package.canonical_hash_sha256,
    )


def test_24_package_canonical_hash_tamper_is_detected() -> None:
    result = _legal_result(_fixture())
    assert result.package is not None
    tampered = dataclasses.replace(result.package, canonical_hash_sha256="a" * 64)
    assert not verify_s3_legal_backtest_package_hash_replay(tampered)


def test_25_generic_unresolved_branch_is_blocking() -> None:
    fixture = _fixture()
    result = build_s3_legal_backtest_package(
        pairing_materialization=fixture.materialization,
        train_partition_authority=fixture.train_authority,
        validation_partition_authority=fixture.validation_authority,
        forecast_cutoff_set=fixture.cutoff_set,
    )
    assert (
        S3LegalBacktestPackageBlocker.GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIREMENT_UNRESOLVED.value
        in result.blocker_codes
    )


def test_26_generic_required_false_is_a_legal_noop() -> None:
    result = _legal_result(
        _fixture(),
        generic_requirement=S3GenericIncumbentForecastArtifactRequirement(
            requirement=GenericIncumbentForecastArtifactRequirement.REQUIRED_FALSE,
        ),
    )
    assert result.status is S3LegalBacktestPackageStatus.LEGAL


def test_27_generic_required_true_without_artifact_is_blocked() -> None:
    result = _legal_result(
        _fixture(),
        generic_requirement=S3GenericIncumbentForecastArtifactRequirement(
            requirement=GenericIncumbentForecastArtifactRequirement.REQUIRED_TRUE,
        ),
    )
    assert (
        S3LegalBacktestPackageBlocker.GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIRED_BUT_NOT_AVAILABLE.value
        in result.blocker_codes
    )


def test_28_generic_required_true_with_governed_identities_can_pass_fixture_gate() -> None:
    result = _legal_result(
        _fixture(),
        generic_requirement=S3GenericIncumbentForecastArtifactRequirement(
            requirement=GenericIncumbentForecastArtifactRequirement.REQUIRED_TRUE,
            artifact_identity_sha256="a" * 64,
            binding_identity_sha256="b" * 64,
            provenance_identity_sha256="c" * 64,
            replay_verified=True,
        ),
    )
    assert result.status is S3LegalBacktestPackageStatus.LEGAL


def test_29_diagnostics_are_aggregate_only() -> None:
    result = _legal_result(_fixture())
    assert result.package is not None
    diagnostics = result.package.diagnostics
    assert diagnostics.train_binding_row_count == 2
    assert diagnostics.validation_binding_row_count == 2
    assert "physical-validation-0" not in repr(diagnostics)
    assert "9" not in repr(diagnostics)


def test_30_test_access_is_not_part_of_the_module_surface() -> None:
    assert not hasattr(legal_module, "obtain_test_rows")
    assert TEST_PARTITION_STATUS_SEALED_ABSENT == "SEALED_ABSENT"


def test_31_no_s3_c_executor_is_imported_or_exposed() -> None:
    assert not hasattr(legal_module, "execute_s3_c_backtest")
    assert not hasattr(legal_module, "run_s3_c")
    source = inspect.getsource(legal_module)
    assert "asyncpg" not in source
    assert "create_async_engine" not in source


def test_32_no_metric_calculation_is_imported_or_exposed() -> None:
    assert not hasattr(legal_module, "compute_s3_metrics")
    assert not hasattr(legal_module, "execute_s3_metrics")
    assert "MetricValueCell" not in inspect.getsource(legal_module)


def test_33_no_s3_d_attribution_is_imported_or_exposed() -> None:
    assert not hasattr(legal_module, "execute_s3_d_attribution")
    assert not hasattr(legal_module, "build_s3_d_attribution")
    assert "attribution_matrix" not in inspect.getsource(legal_module)


def test_no_comparison_result_fields_are_published() -> None:
    result = _legal_result(_fixture())
    assert result.package is not None
    fields = {field.name for field in dataclasses.fields(result.package)}
    assert not any("comparison" in name or "incumbent" in name for name in fields)


@pytest.mark.parametrize(
    "forbidden_name",
    (
        "mape",
        "bias",
        "coverage",
        "p80",
        "p90",
        "peak",
        "cumulative",
        "pinball",
    ),
)
def test_forbidden_metric_families_are_absent(forbidden_name: str) -> None:
    result = _legal_result(_fixture())
    assert result.package is not None
    field_names = {field.name.lower() for field in dataclasses.fields(result.package)}
    assert not any(forbidden_name in name for name in field_names)


def test_fail_closed_result_is_deterministic() -> None:
    fixture = _fixture()
    materialization = dataclasses.replace(
        fixture.materialization,
        test_row_count=1,
        cross_partition_row_count=2,
    )
    first = _legal_result(fixture, materialization=materialization, test_partition_status="OPEN")
    second = _legal_result(fixture, materialization=materialization, test_partition_status="OPEN")
    assert first == second
    assert first.status is S3LegalBacktestPackageStatus.BLOCKED
    assert first.package is None
    assert first.blocker_codes == tuple(
        sorted(
            first.blocker_codes,
            key=lambda code: list(legal_module._BLOCKER_ORDER).index(
                S3LegalBacktestPackageBlocker(code)
            ),
        )
    )


def test_36_invalid_package_identity_is_not_accepted() -> None:
    fixture = _fixture()
    package = fixture.materialization.train_pairing_package
    assert package is not None
    tampered = dataclasses.replace(package, pairing_package_identity="a" * 64)
    result = _legal_result(
        fixture,
        materialization=dataclasses.replace(
            fixture.materialization,
            train_pairing_package=tampered,
        ),
    )
    assert (
        S3LegalBacktestPackageBlocker.TRAIN_PAIRING_PACKAGE_IDENTITY_INVALID.value
        in result.blocker_codes
    )


def test_37_incomplete_pairing_materialization_is_blocked() -> None:
    fixture = _fixture()
    result = _legal_result(
        fixture,
        materialization=dataclasses.replace(
            fixture.materialization,
            completed=False,
        ),
    )
    assert result.status is S3LegalBacktestPackageStatus.BLOCKED


def test_38_package_status_domain_has_no_partial_state() -> None:
    assert legal_module.LEGAL_BACKTEST_PACKAGE_STATUS_VALUES == ("LEGAL", "BLOCKED")
    assert set(legal_module.S3LegalBacktestPackageStatus) == {
        S3LegalBacktestPackageStatus.LEGAL,
        S3LegalBacktestPackageStatus.BLOCKED,
    }


def test_39_missing_days_are_not_zero_filled_by_package_builder() -> None:
    result = _legal_result(_fixture())
    assert result.package is not None
    assert result.package.missing_day_policy == "UNKNOWN_NOT_ZERO"
    assert "zero" not in repr(result.package.diagnostics).lower()


def test_40_forecast_cutoff_authority_identity_is_consistent_across_partitions() -> None:
    fixture = _fixture()
    train_package = fixture.materialization.train_pairing_package
    validation_package = fixture.materialization.validation_pairing_package
    assert train_package is not None
    assert validation_package is not None
    assert (
        train_package.forecast_cutoff_authority_identity
        == validation_package.forecast_cutoff_authority_identity
    )


def test_41_package_hash_payload_has_no_runtime_metadata() -> None:
    result = _legal_result(_fixture())
    assert result.package is not None
    payload = build_s3_legal_backtest_package_semantic_payload(result.package)
    text = str(payload)
    for forbidden in ("timestamp", "process_id", "filesystem", "worker", "database"):
        assert forbidden not in text


def test_42_no_native_float_conversion_is_present() -> None:
    source = inspect.getsource(legal_module)
    assert "Decimal(float" not in source
    assert ".from_float(" not in source


def test_43_authority_registries_are_immutable_inputs() -> None:
    fixture = _fixture()
    records = fixture.published_registry
    with pytest.raises(TypeError):
        records._records["new"] = fixture.materialization.train_pairing_package  # type: ignore[index]


def test_44_package_identity_perturbation_changes_replay_result() -> None:
    result = _legal_result(_fixture())
    assert result.package is not None
    changed = dataclasses.replace(
        result.package,
        model_identity="different-model",
    )
    assert not verify_s3_legal_backtest_package_hash_replay(changed)


def test_45_blocker_messages_are_codes_only() -> None:
    fixture = _fixture()
    result = _legal_result(
        fixture,
        materialization=dataclasses.replace(
            fixture.materialization,
            cross_partition_row_count=1,
        ),
    )
    assert all("season-" not in blocker for blocker in result.blocker_codes)
    assert all("physical-" not in blocker for blocker in result.blocker_codes)
