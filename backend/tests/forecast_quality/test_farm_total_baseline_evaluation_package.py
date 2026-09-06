"""Unit tests for the deterministic Farm-total baseline evaluation package."""

from __future__ import annotations

import dataclasses
import re
from datetime import date
from decimal import Decimal
from typing import Literal

import pytest

from backend.app.forecast_quality.farm_total_baseline_estimator import (
    FarmTotalBaselineDerivationBlocker,
    FarmTotalBaselineDerivationError,
    FarmTotalBaselineTargetKey,
    FarmTotalBaselineTargetStatus,
)
from backend.app.forecast_quality.farm_total_baseline_evaluation_package import (
    FARM_TOTAL_BASELINE_ESTIMATOR_SEMANTIC_IDENTITY_SHA256,
    FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_SCHEMA_VERSION,
    FarmTotalBaselineEvaluationPackage,
    FarmTotalBaselineEvaluationPackageBlocker,
    FarmTotalBaselineEvaluationPackageError,
    build_farm_total_baseline_evaluation_package,
    build_farm_total_validation_target_keys,
    compute_farm_total_baseline_estimator_state_sha256,
    compute_farm_total_baseline_evaluation_package_sha256,
    compute_farm_total_baseline_point_set_sha256,
    compute_farm_total_baseline_prediction_identity_sha256,
    compute_farm_total_baseline_target_identity_set_sha256,
    compute_farm_total_baseline_target_outcome_set_sha256,
)
from backend.app.forecast_quality.farm_total_dataset import (
    FarmTotalDatasetDiagnostics,
    FarmTotalDatasetRow,
    FarmTotalPartitionDataset,
    FarmTotalTrainingDataset,
    FarmTotalValidationDataset,
    compute_partition_dataset_sha256,
)
from backend.app.forecast_quality.farm_total_policy import (
    AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
)

SEASON = "2025~2026"
SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _synthetic_row(
    *,
    group: str,
    harvest_date: date,
    quantity_kg: Decimal,
    area_mu: Decimal = Decimal("100.0"),
    partition: Literal["TRAIN", "VALIDATION"] = "TRAIN",
    season: str = SEASON,
    row_hash: str | None = None,
) -> FarmTotalDatasetRow:
    resolved_row_hash = row_hash or f"row-{group}-{harvest_date.isoformat()}-{partition}"
    return FarmTotalDatasetRow(
        season_business_key=season,
        baseline_farm_group_key=group,
        harvest_business_date=harvest_date,
        partition=partition,
        area_mu=area_mu,
        area_authority_class=AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
        actual_harvest_quantity_kg=quantity_kg,
        actual_harvest_kg_per_mu=quantity_kg / area_mu,
        source_actual_row_count=1,
        source_farm_business_keys=(f"farm-{group}",),
        area_authority_row_hash=f"area-hash-{group}",
        actual_projection_hash=f"proj-{group}-{harvest_date.isoformat()}",
        row_hash=resolved_row_hash,
    )


def _synthetic_diagnostics(
    *,
    partition: Literal["TRAIN", "VALIDATION", "TRAIN_PLUS_VALIDATION_AUDIT"],
    row_count: int,
    farm_group_count: int,
    date_count: int,
) -> FarmTotalDatasetDiagnostics:
    return FarmTotalDatasetDiagnostics(
        partition=partition,
        farm_group_count=farm_group_count,
        date_count=date_count,
        row_count=row_count,
        total_area_mu="100.0",
        total_actual_harvest_kg="0",
        kg_per_mu_min=None,
        kg_per_mu_p25=None,
        kg_per_mu_median=None,
        kg_per_mu_p75=None,
        kg_per_mu_max=None,
    )


def _train_dataset(
    rows: tuple[FarmTotalDatasetRow, ...],
    dataset_sha256: str | None = None,
) -> FarmTotalTrainingDataset:
    sha = dataset_sha256 or compute_partition_dataset_sha256(rows)
    groups = {row.baseline_farm_group_key for row in rows}
    dates = {row.harvest_business_date for row in rows}
    return FarmTotalTrainingDataset(
        partition_dataset=FarmTotalPartitionDataset(
            partition="TRAIN",
            schema_version="test-schema",
            rows=rows,
            dataset_sha256=sha,
        ),
        diagnostics=_synthetic_diagnostics(
            partition="TRAIN",
            row_count=len(rows),
            farm_group_count=len(groups),
            date_count=len(dates),
        ),
    )


def _validation_dataset(
    rows: tuple[FarmTotalDatasetRow, ...],
    *,
    partition: Literal["TRAIN", "VALIDATION"] = "VALIDATION",
    dataset_sha256: str | None = None,
) -> FarmTotalValidationDataset:
    sha = dataset_sha256 or compute_partition_dataset_sha256(rows)
    groups = {row.baseline_farm_group_key for row in rows}
    dates = {row.harvest_business_date for row in rows}
    return FarmTotalValidationDataset(
        partition_dataset=FarmTotalPartitionDataset(
            partition=partition,
            schema_version="test-schema",
            rows=rows,
            dataset_sha256=sha,
        ),
        diagnostics=_synthetic_diagnostics(
            partition=partition,
            row_count=len(rows),
            farm_group_count=len(groups),
            date_count=len(dates),
        ),
    )


def _five_train_rows(
    group: str,
    quantities: tuple[Decimal, Decimal, Decimal, Decimal, Decimal],
) -> tuple[FarmTotalDatasetRow, ...]:
    return tuple(
        _synthetic_row(
            group=group,
            harvest_date=date(2025, 9, index + 1),
            quantity_kg=quantity,
            partition="TRAIN",
        )
        for index, quantity in enumerate(quantities)
    )


def _low_five_train_rows(group: str = "g1") -> tuple[FarmTotalDatasetRow, ...]:
    return _five_train_rows(
        group,
        (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")),
    )


def _high_five_train_rows(group: str = "g1") -> tuple[FarmTotalDatasetRow, ...]:
    return _five_train_rows(
        group,
        (Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("50")),
    )


def _five_validation_rows(
    group: str,
    quantities: tuple[Decimal, Decimal, Decimal, Decimal, Decimal],
    *,
    dataset_sha256: str | None = None,
) -> FarmTotalValidationDataset:
    rows = tuple(
        _synthetic_row(
            group=group,
            harvest_date=date(2025, 9, index + 1),
            quantity_kg=quantity,
            partition="VALIDATION",
        )
        for index, quantity in enumerate(quantities)
    )
    return _validation_dataset(rows, dataset_sha256=dataset_sha256)


def _build_package(
    train_rows: tuple[FarmTotalDatasetRow, ...],
    validation_rows: tuple[FarmTotalDatasetRow, ...],
    *,
    train_dataset_sha256: str | None = None,
    validation_dataset_sha256: str | None = None,
) -> FarmTotalBaselineEvaluationPackage:
    return build_farm_total_baseline_evaluation_package(
        train_dataset=_train_dataset(train_rows, dataset_sha256=train_dataset_sha256),
        validation_dataset=_validation_dataset(
            validation_rows,
            dataset_sha256=validation_dataset_sha256,
        ),
    )


# A. TARGET CONSTRUCTION


def test_validation_rows_produce_identity_only_target_keys() -> None:
    validation = _five_validation_rows(
        "g1",
        (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")),
    )
    target_set = build_farm_total_validation_target_keys(validation)
    assert len(target_set.target_keys) == 5
    assert all(isinstance(key, FarmTotalBaselineTargetKey) for key in target_set.target_keys)


def test_target_key_has_no_actual_harvest_quantity_field() -> None:
    fields = {field.name for field in dataclasses.fields(FarmTotalBaselineTargetKey)}
    assert "actual_harvest_quantity_kg" not in fields


def test_target_key_has_no_area_mu_field() -> None:
    fields = {field.name for field in dataclasses.fields(FarmTotalBaselineTargetKey)}
    assert "area_mu" not in fields


def test_target_order_is_deterministic() -> None:
    rows = (
        _synthetic_row(
            group="zeta",
            harvest_date=date(2025, 9, 3),
            quantity_kg=Decimal("3"),
            partition="VALIDATION",
        ),
        _synthetic_row(
            group="alpha",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("1"),
            partition="VALIDATION",
        ),
        _synthetic_row(
            group="alpha",
            harvest_date=date(2025, 9, 2),
            quantity_kg=Decimal("2"),
            partition="VALIDATION",
        ),
    )
    target_set = build_farm_total_validation_target_keys(_validation_dataset(rows))
    assert [
        (key.baseline_farm_group_key, key.harvest_business_date) for key in target_set.target_keys
    ] == [
        ("alpha", date(2025, 9, 1)),
        ("alpha", date(2025, 9, 2)),
        ("zeta", date(2025, 9, 3)),
    ]


def test_outer_train_partition_fails_with_non_validation_partition() -> None:
    rows = _five_train_rows(
        "g1",
        (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")),
    )
    with pytest.raises(FarmTotalBaselineEvaluationPackageError) as exc_info:
        build_farm_total_validation_target_keys(_validation_dataset(rows, partition="TRAIN"))
    assert (
        exc_info.value.blocker is FarmTotalBaselineEvaluationPackageBlocker.NON_VALIDATION_PARTITION
    )


def test_inner_train_row_fails_with_non_validation_row_partition() -> None:
    rows = (
        *_five_train_rows(
            "g1",
            (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")),
        ),
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 6),
            quantity_kg=Decimal("6"),
            partition="TRAIN",
        ),
    )
    validation_rows = tuple(
        _synthetic_row(
            group=row.baseline_farm_group_key,
            harvest_date=row.harvest_business_date,
            quantity_kg=row.actual_harvest_quantity_kg,
            partition="VALIDATION",
        )
        for row in rows[:5]
    ) + (rows[5],)
    with pytest.raises(FarmTotalBaselineEvaluationPackageError) as exc_info:
        build_farm_total_validation_target_keys(_validation_dataset(validation_rows))
    assert (
        exc_info.value.blocker
        is FarmTotalBaselineEvaluationPackageBlocker.NON_VALIDATION_ROW_PARTITION
    )


def test_duplicate_target_identity_fails_closed() -> None:
    rows = (
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("1"),
            partition="VALIDATION",
        ),
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("9"),
            partition="VALIDATION",
            row_hash="duplicate-row",
        ),
    )
    with pytest.raises(FarmTotalBaselineEvaluationPackageError) as exc_info:
        build_farm_total_validation_target_keys(_validation_dataset(rows))
    assert (
        exc_info.value.blocker
        is FarmTotalBaselineEvaluationPackageBlocker.DUPLICATE_VALIDATION_TARGET_KEY
    )


def test_empty_validation_target_set_produces_deterministic_empty_package() -> None:
    validation = _validation_dataset(())
    target_set = build_farm_total_validation_target_keys(validation)
    assert target_set.target_keys == ()
    package = build_farm_total_baseline_evaluation_package(
        train_dataset=_train_dataset(_five_train_rows("g1", (Decimal("1"),) * 5)),
        validation_dataset=validation,
    )
    assert package.target_count == 0
    assert package.emitted_point_count == 0
    assert package.blocked_target_count == 0
    assert package.diagnostics.ready_target_count == 0


# B. ESTIMATOR ORCHESTRATION


def test_supported_train_group_emits_correct_median_baseline() -> None:
    train_rows = _five_train_rows(
        "g1",
        (Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("50")),
    )
    validation_rows = (
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("999"),
            partition="VALIDATION",
        ),
    )
    package = _build_package(train_rows, validation_rows)
    assert package.projection_result.points[0].baseline_harvest_quantity_kg == Decimal("30")


def test_insufficient_train_support_preserves_blocker_outcome() -> None:
    train_rows = (
        _synthetic_row(group="weak", harvest_date=date(2025, 9, 1), quantity_kg=Decimal("1")),
        _synthetic_row(group="weak", harvest_date=date(2025, 9, 2), quantity_kg=Decimal("2")),
    )
    validation_rows = (
        _synthetic_row(
            group="weak",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("100"),
            partition="VALIDATION",
        ),
    )
    package = _build_package(train_rows, validation_rows)
    assert package.projection_result.points == ()
    assert (
        package.projection_result.target_outcomes[0].status
        is FarmTotalBaselineTargetStatus.INSUFFICIENT_TRAIN_SUPPORT
    )


def test_unseen_validation_group_preserves_unseen_group_outcome() -> None:
    train_rows = _five_train_rows(
        "known",
        (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")),
    )
    validation_rows = (
        _synthetic_row(
            group="missing",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("1"),
            partition="VALIDATION",
        ),
    )
    package = _build_package(train_rows, validation_rows)
    assert package.projection_result.points == ()
    assert (
        package.projection_result.target_outcomes[0].status
        is FarmTotalBaselineTargetStatus.UNSEEN_GROUP
    )


def test_supported_and_blocked_groups_coexist_without_global_failure() -> None:
    train_rows = (
        *_five_train_rows(
            "strong",
            (Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("50")),
        ),
        _synthetic_row(group="weak", harvest_date=date(2025, 9, 1), quantity_kg=Decimal("1")),
    )
    validation_rows = (
        _synthetic_row(
            group="strong",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("1"),
            partition="VALIDATION",
        ),
        _synthetic_row(
            group="weak",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("2"),
            partition="VALIDATION",
        ),
    )
    package = _build_package(train_rows, validation_rows)
    outcomes = {
        outcome.target_key.baseline_farm_group_key: outcome.status
        for outcome in package.projection_result.target_outcomes
    }
    assert outcomes["strong"] is FarmTotalBaselineTargetStatus.READY
    assert outcomes["weak"] is FarmTotalBaselineTargetStatus.INSUFFICIENT_TRAIN_SUPPORT
    assert len(package.projection_result.points) == 1


def test_no_cross_group_pooling() -> None:
    train_rows = (
        *_five_train_rows(
            "g1",
            (Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1")),
        ),
        *_five_train_rows(
            "g2",
            (Decimal("9"), Decimal("9"), Decimal("9"), Decimal("9"), Decimal("9")),
        ),
    )
    validation_rows = (
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("1"),
            partition="VALIDATION",
        ),
        _synthetic_row(
            group="g2",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("9"),
            partition="VALIDATION",
        ),
    )
    package = _build_package(train_rows, validation_rows)
    by_group = {
        point.baseline_farm_group_key: point.baseline_harvest_quantity_kg
        for point in package.projection_result.points
    }
    assert by_group["g1"] == Decimal("1")
    assert by_group["g2"] == Decimal("9")


def test_no_missing_date_synthesis() -> None:
    train_rows = _five_train_rows(
        "g1",
        (Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("50")),
    )
    validation_rows = (
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 2),
            quantity_kg=Decimal("1"),
            partition="VALIDATION",
        ),
    )
    package = _build_package(train_rows, validation_rows)
    assert len(package.projection_result.points) == 1
    assert package.projection_result.points[0].harvest_business_date == date(2025, 9, 2)


# C. VALIDATION LEAKAGE


def _leakage_pair() -> tuple[FarmTotalBaselineEvaluationPackage, FarmTotalBaselineEvaluationPackage]:
    train_rows = _five_train_rows(
        "g1",
        (Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("50")),
    )
    validation_a_rows = (
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("999"),
            partition="VALIDATION",
            row_hash="validation-a",
        ),
    )
    validation_b_rows = (
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("1"),
            partition="VALIDATION",
            row_hash="validation-b",
        ),
    )
    train = _train_dataset(train_rows)
    validation_a = _validation_dataset(validation_a_rows, dataset_sha256="validation-sha-a")
    validation_b = _validation_dataset(validation_b_rows, dataset_sha256="validation-sha-b")
    return (
        build_farm_total_baseline_evaluation_package(
            train_dataset=train,
            validation_dataset=validation_a,
        ),
        build_farm_total_baseline_evaluation_package(
            train_dataset=train,
            validation_dataset=validation_b,
        ),
    )


def test_identical_identity_different_actual_produces_identical_target_keys() -> None:
    package_a, package_b = _leakage_pair()
    assert package_a.target_keys == package_b.target_keys


def test_identical_identity_different_actual_produces_identical_baseline_points() -> None:
    package_a, package_b = _leakage_pair()
    assert package_a.projection_result.points == package_b.projection_result.points


def test_identical_identity_different_actual_produces_identical_target_identity_hash() -> None:
    package_a, package_b = _leakage_pair()
    assert package_a.target_identity_set_sha256 == package_b.target_identity_set_sha256


def test_identical_identity_different_actual_produces_identical_baseline_point_hash() -> None:
    package_a, package_b = _leakage_pair()
    assert package_a.baseline_point_set_sha256 == package_b.baseline_point_set_sha256


def test_identical_identity_different_actual_produces_identical_target_outcome_hash() -> None:
    package_a, package_b = _leakage_pair()
    assert package_a.target_outcome_set_sha256 == package_b.target_outcome_set_sha256


def test_identical_identity_different_actual_produces_identical_prediction_identity() -> None:
    package_a, package_b = _leakage_pair()
    assert package_a.prediction_identity_sha256 == package_b.prediction_identity_sha256


def test_identical_identity_different_actual_has_different_validation_dataset_sha() -> None:
    package_a, package_b = _leakage_pair()
    assert package_a.validation_dataset_sha256 != package_b.validation_dataset_sha256


def test_identical_identity_different_actual_has_different_package_sha() -> None:
    package_a, package_b = _leakage_pair()
    assert package_a.package_sha256 != package_b.package_sha256


# D. TRAIN DEPENDENCY


def test_changing_train_actual_quantities_changes_estimator_median() -> None:
    validation_rows = (
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("1"),
            partition="VALIDATION",
        ),
    )
    package_low = _build_package(_low_five_train_rows(), validation_rows)
    package_high = _build_package(_high_five_train_rows(), validation_rows)
    assert (
        package_low.projection_result.points[0].baseline_harvest_quantity_kg
        != package_high.projection_result.points[0].baseline_harvest_quantity_kg
    )


def test_changing_train_actual_quantities_changes_estimator_state_sha256() -> None:
    validation_rows = (
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("1"),
            partition="VALIDATION",
        ),
    )
    package_low = _build_package(_low_five_train_rows(), validation_rows)
    package_high = _build_package(_high_five_train_rows(), validation_rows)
    assert package_low.estimator_state_sha256 != package_high.estimator_state_sha256


def test_changing_train_actual_quantities_changes_baseline_point_set_sha256() -> None:
    validation_rows = (
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("1"),
            partition="VALIDATION",
        ),
    )
    package_low = _build_package(_low_five_train_rows(), validation_rows)
    package_high = _build_package(_high_five_train_rows(), validation_rows)
    assert package_low.baseline_point_set_sha256 != package_high.baseline_point_set_sha256


def test_changing_train_actual_quantities_changes_prediction_identity_sha256() -> None:
    validation_rows = (
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("1"),
            partition="VALIDATION",
        ),
    )
    package_low = _build_package(_low_five_train_rows(), validation_rows)
    package_high = _build_package(_high_five_train_rows(), validation_rows)
    assert package_low.prediction_identity_sha256 != package_high.prediction_identity_sha256


def test_changing_train_area_mu_only_does_not_alter_baseline_points() -> None:
    train_rows = tuple(
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, index + 1),
            quantity_kg=quantity,
            area_mu=Decimal(str((index + 1) * 100)),
            partition="TRAIN",
        )
        for index, quantity in enumerate(
            (Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("50"))
        )
    )
    validation_rows = (
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("1"),
            partition="VALIDATION",
        ),
    )
    package = _build_package(train_rows, validation_rows)
    assert package.projection_result.points[0].baseline_harvest_quantity_kg == Decimal("30")


# E. HASH / REPLAY


def _reference_package() -> FarmTotalBaselineEvaluationPackage:
    train_rows = _five_train_rows(
        "g1",
        (Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("50")),
    )
    validation_rows = (
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("1"),
            partition="VALIDATION",
        ),
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 2),
            quantity_kg=Decimal("2"),
            partition="VALIDATION",
        ),
    )
    return _build_package(train_rows, validation_rows)


def test_estimator_state_sha256_replay_equality() -> None:
    package = _reference_package()
    replay = compute_farm_total_baseline_estimator_state_sha256(package.estimator_state)
    assert replay == package.estimator_state_sha256


def test_target_identity_set_sha256_replay_equality() -> None:
    package = _reference_package()
    replay = compute_farm_total_baseline_target_identity_set_sha256(package.target_keys)
    assert replay == package.target_identity_set_sha256


def test_baseline_point_set_sha256_replay_equality() -> None:
    package = _reference_package()
    replay = compute_farm_total_baseline_point_set_sha256(package.projection_result.points)
    assert replay == package.baseline_point_set_sha256


def test_target_outcome_set_sha256_replay_equality() -> None:
    package = _reference_package()
    replay = compute_farm_total_baseline_target_outcome_set_sha256(
        package.projection_result.target_outcomes
    )
    assert replay == package.target_outcome_set_sha256


def test_prediction_identity_sha256_replay_equality() -> None:
    package = _reference_package()
    replay = compute_farm_total_baseline_prediction_identity_sha256(
        train_dataset_sha256=package.train_dataset_sha256,
        estimator_state_sha256=package.estimator_state_sha256,
        target_identity_set_sha256=package.target_identity_set_sha256,
        baseline_point_set_sha256=package.baseline_point_set_sha256,
        target_outcome_set_sha256=package.target_outcome_set_sha256,
    )
    assert replay == package.prediction_identity_sha256


def test_package_sha256_replay_equality() -> None:
    package = _reference_package()
    replay = compute_farm_total_baseline_evaluation_package_sha256(
        train_dataset_sha256=package.train_dataset_sha256,
        validation_dataset_sha256=package.validation_dataset_sha256,
        estimator_state_sha256=package.estimator_state_sha256,
        target_identity_set_sha256=package.target_identity_set_sha256,
        baseline_point_set_sha256=package.baseline_point_set_sha256,
        target_outcome_set_sha256=package.target_outcome_set_sha256,
        prediction_identity_sha256=package.prediction_identity_sha256,
        target_count=package.target_count,
        emitted_point_count=package.emitted_point_count,
        blocked_target_count=package.blocked_target_count,
    )
    assert replay == package.package_sha256


def test_row_order_permutation_with_fixed_provenance_does_not_change_semantics() -> None:
    train_rows = _five_train_rows(
        "g1",
        (Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("50")),
    )
    validation_rows = (
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("1"),
            partition="VALIDATION",
        ),
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 2),
            quantity_kg=Decimal("2"),
            partition="VALIDATION",
        ),
    )
    fixed_train_sha = "fixed-train-sha"
    fixed_validation_sha = "fixed-validation-sha"
    package_a = _build_package(
        train_rows,
        validation_rows,
        train_dataset_sha256=fixed_train_sha,
        validation_dataset_sha256=fixed_validation_sha,
    )
    shuffled_validation = (validation_rows[1], validation_rows[0])
    package_b = _build_package(
        train_rows,
        shuffled_validation,
        train_dataset_sha256=fixed_train_sha,
        validation_dataset_sha256=fixed_validation_sha,
    )
    assert package_a.target_keys == package_b.target_keys
    assert package_a.prediction_identity_sha256 == package_b.prediction_identity_sha256
    assert package_a.package_sha256 == package_b.package_sha256


# F. OUTPUT / DIAGNOSTICS


def test_emitted_baseline_quantity_is_decimal() -> None:
    package = _reference_package()
    assert isinstance(
        package.projection_result.points[0].baseline_harvest_quantity_kg,
        Decimal,
    )


def test_no_p80_p90_fields_on_package_surface() -> None:
    package_fields = {
        field.name for field in dataclasses.fields(FarmTotalBaselineEvaluationPackage)
    }
    forbidden = {name for name in package_fields if "p80" in name.lower() or "p90" in name.lower()}
    assert forbidden == set()


def test_no_metric_result_fields_on_package_surface() -> None:
    package_fields = {
        field.name for field in dataclasses.fields(FarmTotalBaselineEvaluationPackage)
    }
    forbidden = {
        name
        for name in package_fields
        if any(
            token in name.lower() for token in ("metric", "score", "mae", "wape", "mape", "bias")
        )
    }
    assert forbidden == set()


def test_blocked_outcomes_contain_no_numeric_baseline_point() -> None:
    train_rows = (
        _synthetic_row(group="weak", harvest_date=date(2025, 9, 1), quantity_kg=Decimal("1")),
        _synthetic_row(group="weak", harvest_date=date(2025, 9, 2), quantity_kg=Decimal("2")),
    )
    validation_rows = (
        _synthetic_row(
            group="weak",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("100"),
            partition="VALIDATION",
        ),
        _synthetic_row(
            group="missing",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("200"),
            partition="VALIDATION",
        ),
    )
    package = _build_package(train_rows, validation_rows)
    assert package.projection_result.points == ()
    assert all(outcome.point is None for outcome in package.projection_result.target_outcomes)


def test_diagnostics_invariants_hold_for_all_ready() -> None:
    package = _reference_package()
    diagnostics = package.diagnostics
    assert diagnostics.target_count == len(package.target_keys)
    assert diagnostics.emitted_point_count == len(package.projection_result.points)
    assert diagnostics.target_count == diagnostics.ready_target_count
    assert diagnostics.emitted_point_count == diagnostics.ready_target_count
    assert diagnostics.blocked_target_count == 0


def test_diagnostics_invariants_hold_for_mixed_outcomes() -> None:
    train_rows = (
        *_five_train_rows(
            "strong",
            (Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("50")),
        ),
        _synthetic_row(group="weak", harvest_date=date(2025, 9, 1), quantity_kg=Decimal("1")),
    )
    validation_rows = (
        _synthetic_row(
            group="strong",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("1"),
            partition="VALIDATION",
        ),
        _synthetic_row(
            group="weak",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("2"),
            partition="VALIDATION",
        ),
        _synthetic_row(
            group="missing",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("3"),
            partition="VALIDATION",
        ),
    )
    package = _build_package(train_rows, validation_rows)
    diagnostics = package.diagnostics
    assert diagnostics.target_count == 3
    assert diagnostics.ready_target_count == 1
    assert diagnostics.insufficient_train_support_target_count == 1
    assert diagnostics.unseen_group_target_count == 1
    assert diagnostics.blocked_target_count == 2
    assert diagnostics.emitted_point_count == diagnostics.ready_target_count


def test_empty_target_diagnostics_are_all_zero() -> None:
    package = build_farm_total_baseline_evaluation_package(
        train_dataset=_train_dataset(_five_train_rows("g1", (Decimal("1"),) * 5)),
        validation_dataset=_validation_dataset(()),
    )
    diagnostics = package.diagnostics
    assert diagnostics.target_count == 0
    assert diagnostics.emitted_point_count == 0
    assert diagnostics.blocked_target_count == 0
    assert diagnostics.ready_target_count == 0
    assert diagnostics.insufficient_train_support_target_count == 0
    assert diagnostics.unseen_group_target_count == 0


def test_all_hash_outputs_are_lowercase_sha256_hex() -> None:
    package = _reference_package()
    for value in (
        package.estimator_state_sha256,
        package.target_identity_set_sha256,
        package.baseline_point_set_sha256,
        package.target_outcome_set_sha256,
        package.prediction_identity_sha256,
        package.package_sha256,
    ):
        assert SHA256_HEX_PATTERN.match(value)


# G. AUTHORITY / REGRESSION


def test_package_propagates_estimator_non_train_partition_failure() -> None:
    train_rows = _five_train_rows(
        "g1",
        (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")),
    )
    validation_rows = (
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("1"),
            partition="VALIDATION",
        ),
    )
    bad_train = FarmTotalTrainingDataset(
        partition_dataset=FarmTotalPartitionDataset(
            partition="VALIDATION",
            schema_version="test-schema",
            rows=train_rows,
            dataset_sha256="bad-train-sha",
        ),
        diagnostics=_synthetic_diagnostics(
            partition="VALIDATION",
            row_count=len(train_rows),
            farm_group_count=1,
            date_count=5,
        ),
    )
    with pytest.raises(FarmTotalBaselineDerivationError) as exc_info:
        build_farm_total_baseline_evaluation_package(
            train_dataset=bad_train,
            validation_dataset=_validation_dataset(validation_rows),
        )
    assert exc_info.value.blocker is FarmTotalBaselineDerivationBlocker.NON_TRAIN_PARTITION


def test_package_propagates_estimator_non_train_row_partition_failure() -> None:
    train_rows = (
        *_five_train_rows(
            "g1",
            (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")),
        )[:4],
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 6),
            quantity_kg=Decimal("999"),
            partition="VALIDATION",
        ),
    )
    validation_rows = (
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("1"),
            partition="VALIDATION",
        ),
    )
    with pytest.raises(FarmTotalBaselineDerivationError) as exc_info:
        build_farm_total_baseline_evaluation_package(
            train_dataset=_train_dataset(train_rows),
            validation_dataset=_validation_dataset(validation_rows),
        )
    assert exc_info.value.blocker is FarmTotalBaselineDerivationBlocker.NON_TRAIN_ROW_PARTITION


def test_frozen_schema_and_estimator_semantic_identity_constants() -> None:
    assert (
        FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_SCHEMA_VERSION
        == "v0-3-s3-farm-total-baseline-evaluation-package-v1"
    )
    assert (
        FARM_TOTAL_BASELINE_ESTIMATOR_SEMANTIC_IDENTITY_SHA256
        == "39722ff8e8a520813975cd7270b6453db388633bffee9c90fb12140440431463"
    )
