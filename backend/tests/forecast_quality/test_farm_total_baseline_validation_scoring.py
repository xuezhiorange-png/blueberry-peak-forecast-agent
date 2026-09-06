"""Synthetic contract tests for Farm-total baseline VALIDATION scoring."""

from __future__ import annotations

import dataclasses
import inspect
from datetime import date
from decimal import Decimal
from typing import Literal

import pytest

from backend.app.forecast_quality import farm_total_baseline_validation_scoring as scoring
from backend.app.forecast_quality.canonical import canonical_json_bytes
from backend.app.forecast_quality.farm_total_baseline_estimator import (
    FarmTotalBaselinePoint,
    FarmTotalBaselineProjectionResult,
)
from backend.app.forecast_quality.farm_total_baseline_evaluation_package import (
    FarmTotalBaselineEvaluationPackage,
    build_farm_total_baseline_evaluation_package,
    compute_farm_total_baseline_evaluation_package_sha256,
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
PARTITION = Literal["TRAIN", "VALIDATION"]


def _row(
    *,
    group: str,
    harvest_date: date,
    quantity: Decimal,
    partition: PARTITION,
    area_mu: Decimal = Decimal("100"),
) -> FarmTotalDatasetRow:
    return FarmTotalDatasetRow(
        season_business_key=SEASON,
        baseline_farm_group_key=group,
        harvest_business_date=harvest_date,
        partition=partition,
        area_mu=area_mu,
        area_authority_class=AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
        actual_harvest_quantity_kg=quantity,
        actual_harvest_kg_per_mu=quantity / area_mu,
        source_actual_row_count=1,
        source_farm_business_keys=(f"farm-{group}",),
        area_authority_row_hash=f"area-{group}",
        actual_projection_hash=f"projection-{group}-{harvest_date.isoformat()}",
        row_hash=f"row-{group}-{harvest_date.isoformat()}-{partition}",
    )


def _row_key(row: FarmTotalDatasetRow) -> tuple[str, str, date]:
    return (
        row.season_business_key,
        row.baseline_farm_group_key,
        row.harvest_business_date,
    )


def _diagnostics(
    *,
    partition: Literal["TRAIN", "VALIDATION"],
    rows: tuple[FarmTotalDatasetRow, ...],
) -> FarmTotalDatasetDiagnostics:
    return FarmTotalDatasetDiagnostics(
        partition=partition,
        farm_group_count=len({row.baseline_farm_group_key for row in rows}),
        date_count=len({row.harvest_business_date for row in rows}),
        row_count=len(rows),
        total_area_mu="100",
        total_actual_harvest_kg="0",
        kg_per_mu_min=None,
        kg_per_mu_p25=None,
        kg_per_mu_median=None,
        kg_per_mu_p75=None,
        kg_per_mu_max=None,
    )


def _train_dataset(rows: tuple[FarmTotalDatasetRow, ...]) -> FarmTotalTrainingDataset:
    ordered = tuple(sorted(rows, key=_row_key))
    return FarmTotalTrainingDataset(
        partition_dataset=FarmTotalPartitionDataset(
            partition="TRAIN",
            schema_version="synthetic-test-schema",
            rows=ordered,
            dataset_sha256=compute_partition_dataset_sha256(ordered),
        ),
        diagnostics=_diagnostics(partition="TRAIN", rows=ordered),
    )


def _validation_dataset(
    rows: tuple[FarmTotalDatasetRow, ...],
    *,
    dataset_sha256: str | None = None,
    partition: Literal["TRAIN", "VALIDATION"] = "VALIDATION",
) -> FarmTotalValidationDataset:
    ordered = tuple(sorted(rows, key=_row_key))
    resolved_sha = dataset_sha256 or compute_partition_dataset_sha256(ordered)
    return FarmTotalValidationDataset(
        partition_dataset=FarmTotalPartitionDataset(
            partition=partition,
            schema_version="synthetic-test-schema",
            rows=rows,
            dataset_sha256=resolved_sha,
        ),
        diagnostics=_diagnostics(partition=partition, rows=ordered),
    )


def _five_train_rows(
    group: str = "g1",
    quantities: tuple[Decimal, Decimal, Decimal, Decimal, Decimal] = (
        Decimal("10"),
        Decimal("20"),
        Decimal("30"),
        Decimal("40"),
        Decimal("50"),
    ),
) -> tuple[FarmTotalDatasetRow, ...]:
    return tuple(
        _row(
            group=group,
            harvest_date=date(2025, 9, index + 1),
            quantity=quantity,
            partition="TRAIN",
        )
        for index, quantity in enumerate(quantities)
    )


def _base_validation_rows() -> tuple[FarmTotalDatasetRow, ...]:
    return (
        _row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity=Decimal("20"),
            partition="VALIDATION",
        ),
        _row(
            group="g1",
            harvest_date=date(2025, 9, 2),
            quantity=Decimal("40"),
            partition="VALIDATION",
        ),
    )


def _package_and_validation(
    *,
    train_rows: tuple[FarmTotalDatasetRow, ...] | None = None,
    validation_rows: tuple[FarmTotalDatasetRow, ...] | None = None,
) -> tuple[FarmTotalBaselineEvaluationPackage, FarmTotalValidationDataset]:
    train = _train_dataset(train_rows if train_rows is not None else _five_train_rows())
    validation = _validation_dataset(
        validation_rows if validation_rows is not None else _base_validation_rows()
    )
    package = build_farm_total_baseline_evaluation_package(
        train_dataset=train,
        validation_dataset=validation,
    )
    return package, validation


def _rebind_validation_dataset_sha(
    package: FarmTotalBaselineEvaluationPackage,
    validation_dataset_sha256: str,
) -> FarmTotalBaselineEvaluationPackage:
    package_sha256 = compute_farm_total_baseline_evaluation_package_sha256(
        train_dataset_sha256=package.train_dataset_sha256,
        validation_dataset_sha256=validation_dataset_sha256,
        estimator_state_sha256=package.estimator_state_sha256,
        target_identity_set_sha256=package.target_identity_set_sha256,
        baseline_point_set_sha256=package.baseline_point_set_sha256,
        target_outcome_set_sha256=package.target_outcome_set_sha256,
        prediction_identity_sha256=package.prediction_identity_sha256,
        target_count=package.target_count,
        emitted_point_count=package.emitted_point_count,
        blocked_target_count=package.blocked_target_count,
    )
    return dataclasses.replace(
        package,
        validation_dataset_sha256=validation_dataset_sha256,
        package_sha256=package_sha256,
    )


def _score(
    *,
    train_rows: tuple[FarmTotalDatasetRow, ...] | None = None,
    validation_rows: tuple[FarmTotalDatasetRow, ...] | None = None,
) -> scoring.FarmTotalBaselineValidationScorePackage:
    package, validation = _package_and_validation(
        train_rows=train_rows,
        validation_rows=validation_rows,
    )
    return scoring.score_farm_total_baseline_validation(
        evaluation_package=package,
        validation_dataset=validation,
    )


def _error(
    package: FarmTotalBaselineEvaluationPackage,
    validation: FarmTotalValidationDataset,
) -> scoring.FarmTotalBaselineValidationScoringError:
    with pytest.raises(scoring.FarmTotalBaselineValidationScoringError) as exc_info:
        scoring.score_farm_total_baseline_validation(
            evaluation_package=package,
            validation_dataset=validation,
        )
    return exc_info.value


# 1. exact package/validation dataset hash binding
def test_exact_package_validation_dataset_hash_binding() -> None:
    package, validation = _package_and_validation()
    wrong_declared = dataclasses.replace(
        validation.partition_dataset,
        dataset_sha256="0" * 64,
    )
    wrong_validation = dataclasses.replace(validation, partition_dataset=wrong_declared)
    error = _error(package, wrong_validation)
    assert (
        error.blocker
        is scoring.FarmTotalBaselineValidationScoringBlocker.VALIDATION_DATASET_IDENTITY_MISMATCH
    )


# 2. row-order invariance
def test_row_order_invariance() -> None:
    package, validation = _package_and_validation()
    shuffled = dataclasses.replace(
        validation.partition_dataset,
        rows=tuple(reversed(validation.partition_dataset.rows)),
    )
    shuffled_validation = dataclasses.replace(validation, partition_dataset=shuffled)
    assert scoring.score_farm_total_baseline_validation(
        evaluation_package=package,
        validation_dataset=validation,
    ) == scoring.score_farm_total_baseline_validation(
        evaluation_package=package,
        validation_dataset=shuffled_validation,
    )


# 3. exact target-key pairing
def test_exact_target_key_pairing() -> None:
    train_rows = _five_train_rows("g1") + _five_train_rows(
        "g2",
        (Decimal("100"),) * 5,
    )
    validation_rows = (
        _row(
            group="g2",
            harvest_date=date(2025, 9, 1),
            quantity=Decimal("100"),
            partition="VALIDATION",
        ),
        _row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity=Decimal("30"),
            partition="VALIDATION",
        ),
    )
    score = _score(train_rows=train_rows, validation_rows=validation_rows)
    assert score.metric_cells[0].metric_value == Decimal("0")
    assert score.diagnostics.comparable_target_count == 2


# 4. duplicate validation target fail closed
def test_duplicate_validation_target_fail_closed() -> None:
    package, validation = _package_and_validation(
        validation_rows=(_base_validation_rows()[0],),
    )
    duplicate_rows = validation.partition_dataset.rows + (
        dataclasses.replace(validation.partition_dataset.rows[0], row_hash="duplicate"),
    )
    duplicate_sha = compute_partition_dataset_sha256(tuple(sorted(duplicate_rows, key=_row_key)))
    duplicate_validation = _validation_dataset(duplicate_rows, dataset_sha256=duplicate_sha)
    rebound_package = _rebind_validation_dataset_sha(package, duplicate_sha)
    error = _error(rebound_package, duplicate_validation)
    assert (
        error.blocker
        is scoring.FarmTotalBaselineValidationScoringBlocker.DUPLICATE_VALIDATION_TARGET_KEY
    )


# 5. missing READY actual fail closed
def test_missing_ready_actual_fail_closed() -> None:
    package, validation = _package_and_validation(
        validation_rows=(_base_validation_rows()[0],),
    )
    missing_row = dataclasses.replace(
        validation.partition_dataset.rows[0],
        actual_harvest_quantity_kg=None,  # type: ignore[arg-type]
    )
    missing_validation = _validation_dataset(
        (missing_row,),
        dataset_sha256=validation.partition_dataset.dataset_sha256,
    )
    error = _error(package, missing_validation)
    assert error.blocker is scoring.FarmTotalBaselineValidationScoringBlocker.READY_ACTUAL_MISSING


# 6. negative_validation_actual_fail_closed
def test_negative_validation_actual_fail_closed() -> None:
    negative_rows = (
        _row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity=Decimal("-1"),
            partition="VALIDATION",
        ),
    )
    package, validation = _package_and_validation(validation_rows=negative_rows)
    error = _error(package, validation)
    assert (
        error.blocker
        is scoring.FarmTotalBaselineValidationScoringBlocker.NEGATIVE_VALIDATION_ACTUAL
    )
    assert error.reason_code == "NEGATIVE_VALIDATION_ACTUAL"
    assert error.negative_validation_actual_count == 1
    assert "1" not in str(error) or str(error) == "NEGATIVE_VALIDATION_ACTUAL"


# 7. missing READY baseline point fail closed
def test_missing_ready_baseline_point_fail_closed() -> None:
    package, validation = _package_and_validation(
        validation_rows=(_base_validation_rows()[0],),
    )
    outcome = package.projection_result.target_outcomes[0]
    missing_point_outcome = dataclasses.replace(outcome, point=None)
    projection = dataclasses.replace(
        package.projection_result,
        target_outcomes=(missing_point_outcome,),
    )
    tampered_package = dataclasses.replace(package, projection_result=projection)
    error = _error(tampered_package, validation)
    assert (
        error.blocker
        is scoring.FarmTotalBaselineValidationScoringBlocker.READY_BASELINE_POINT_MISSING
    )


# 8. blocked targets excluded from arithmetic but retained in counters
def test_blocked_targets_excluded_from_arithmetic_but_retained_in_counters() -> None:
    train_rows = (
        _five_train_rows("ready")
        + _five_train_rows(
            "weak",
            (Decimal("1"),) * 5,
        )[:2]
    )
    validation_rows = (
        _row(
            group="ready",
            harvest_date=date(2025, 9, 1),
            quantity=Decimal("30"),
            partition="VALIDATION",
        ),
        _row(
            group="weak",
            harvest_date=date(2025, 9, 1),
            quantity=Decimal("999"),
            partition="VALIDATION",
        ),
    )
    score = _score(train_rows=train_rows, validation_rows=validation_rows)
    assert score.diagnostics.target_count == 2
    assert score.diagnostics.comparable_target_count == 1
    assert score.diagnostics.blocked_target_count == 1
    assert score.diagnostics.insufficient_train_support_target_count == 1
    assert score.metric_cells[0].metric_value == Decimal("0")


# 9. target count closure
def test_target_count_closure() -> None:
    score = _score()
    diagnostics = score.diagnostics
    assert diagnostics.target_count == (
        diagnostics.comparable_target_count + diagnostics.blocked_target_count
    )


# 10. comparable count equals READY count
def test_comparable_count_equals_ready_count() -> None:
    score = _score()
    assert score.diagnostics.comparable_target_count == score.diagnostics.ready_target_count


# 11. MAE hand-computed example
def test_mae_hand_computed_example() -> None:
    score = _score()
    mae = score.metric_cells[0]
    assert mae.metric_name == "MAE"
    assert mae.metric_value == Decimal("10.000000")
    assert mae.numerator == Decimal("20.000000")
    assert mae.denominator == Decimal("2.000000")


# 12. WAPE hand-computed example
def test_wape_hand_computed_example() -> None:
    score = _score()
    wape = score.metric_cells[1]
    assert wape.metric_name == "WAPE"
    assert wape.metric_value == Decimal("0.333333")
    assert wape.numerator == Decimal("20.000000")
    assert wape.denominator == Decimal("60.000000")


# 13. sMAPE hand-computed example
def test_smape_hand_computed_example() -> None:
    score = _score()
    smape = score.metric_cells[2]
    assert smape.metric_name == "SMAPE"
    assert smape.metric_value == Decimal("0.342857")
    assert smape.numerator == Decimal("0.685714")
    assert smape.denominator == Decimal("2.000000")


# 14. sMAPE zero/zero term equals zero
def test_smape_zero_zero_term_equals_zero() -> None:
    zero_train = _five_train_rows("g1", (Decimal("0"),) * 5)
    zero_validation = (
        _row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity=Decimal("0"),
            partition="VALIDATION",
        ),
    )
    score = _score(train_rows=zero_train, validation_rows=zero_validation)
    assert score.metric_cells[2].metric_value == Decimal("0.000000")
    assert score.metric_cells[2].numerator == Decimal("0.000000")


# 15. zero comparable targets => metrics NOT_COMPUTABLE
def test_zero_comparable_targets_are_not_computable() -> None:
    score = _score(validation_rows=())
    assert score.diagnostics.comparable_target_count == 0
    assert all(
        cell.metric_status is scoring.FarmTotalBaselineValidationMetricStatus.NOT_COMPUTABLE
        for cell in score.metric_cells
    )
    assert all(cell.metric_value is None for cell in score.metric_cells)


# 16. WAPE zero denominator => WAPE NOT_COMPUTABLE
def test_wape_zero_denominator_is_not_computable() -> None:
    zero_train = _five_train_rows("g1", (Decimal("10"),) * 5)
    zero_validation = (
        _row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity=Decimal("0"),
            partition="VALIDATION",
        ),
    )
    score = _score(train_rows=zero_train, validation_rows=zero_validation)
    wape = score.metric_cells[1]
    assert wape.metric_status is scoring.FarmTotalBaselineValidationMetricStatus.NOT_COMPUTABLE
    assert wape.reason_code is scoring.FarmTotalBaselineValidationMetricReason.WAPE_DENOMINATOR_ZERO
    assert wape.metric_value is None


# 17. Decimal-only arithmetic
def test_decimal_only_arithmetic() -> None:
    score = _score()
    for cell in score.metric_cells:
        for value in (cell.metric_value, cell.numerator, cell.denominator):
            assert value is None or isinstance(value, Decimal)


# 18. native float rejected/not used
def test_native_float_rejected_not_used() -> None:
    package, validation = _package_and_validation(
        validation_rows=(_base_validation_rows()[0],),
    )
    float_row = dataclasses.replace(
        validation.partition_dataset.rows[0],
        actual_harvest_quantity_kg=1.5,  # type: ignore[arg-type]
    )
    float_validation = _validation_dataset(
        (float_row,),
        dataset_sha256=validation.partition_dataset.dataset_sha256,
    )
    error = _error(package, float_validation)
    assert (
        error.blocker
        is scoring.FarmTotalBaselineValidationScoringBlocker.INVALID_VALIDATION_ACTUAL_DECIMAL
    )


# 19. deterministic target-actual-set hash
def test_deterministic_target_actual_set_hash() -> None:
    score_a = _score()
    score_b = _score()
    assert score_a.scoring_target_actual_set_sha256 == score_b.scoring_target_actual_set_sha256


# 20. deterministic scoring-input hash
def test_deterministic_scoring_input_hash() -> None:
    assert _score().scoring_input_sha256 == _score().scoring_input_sha256


# 21. deterministic metric-result-set hash
def test_deterministic_metric_result_set_hash() -> None:
    assert _score().metric_result_set_sha256 == _score().metric_result_set_sha256


# 22. deterministic score-package hash
def test_deterministic_score_package_hash() -> None:
    assert _score().score_package_sha256 == _score().score_package_sha256


# 23. validation actual perturbation changes scoring hashes/results
def test_validation_actual_perturbation_changes_hashes_and_results() -> None:
    score_a = _score()
    changed = tuple(
        dataclasses.replace(row, actual_harvest_quantity_kg=row.actual_harvest_quantity_kg + 1)
        for row in _base_validation_rows()
    )
    score_b = _score(validation_rows=changed)
    assert score_a.scoring_target_actual_set_sha256 != score_b.scoring_target_actual_set_sha256
    assert score_a.scoring_input_sha256 != score_b.scoring_input_sha256
    assert score_a.metric_result_set_sha256 != score_b.metric_result_set_sha256
    assert score_a.score_package_sha256 != score_b.score_package_sha256


# 24. baseline point perturbation changes scoring hashes/results
def test_baseline_point_perturbation_changes_hashes_and_results() -> None:
    score_a = _score()
    score_b = _score(
        train_rows=_five_train_rows(
            "g1",
            (Decimal("20"),) * 5,
        ),
    )
    assert score_a.baseline_point_set_sha256 != score_b.baseline_point_set_sha256
    assert score_a.scoring_input_sha256 != score_b.scoring_input_sha256
    assert score_a.metric_result_set_sha256 != score_b.metric_result_set_sha256
    assert score_a.score_package_sha256 != score_b.score_package_sha256


# 25. TRAIN-only unrelated mutation cannot directly alter validation actual set identity
def test_train_only_unrelated_mutation_cannot_alter_validation_actual_set_identity() -> None:
    score_a = _score()
    train_rows = tuple(
        dataclasses.replace(row, area_mu=Decimal("200")) for row in _five_train_rows()
    )
    score_b = _score(train_rows=train_rows)
    assert score_a.scoring_target_actual_set_sha256 == score_b.scoring_target_actual_set_sha256


# 26. no per-target values serialized into repository evidence-style public payload
def test_no_per_target_values_in_public_score_payload() -> None:
    score_payload = canonical_json_bytes(dataclasses.asdict(_score())).decode("utf-8")
    for token in (
        "actual_harvest_quantity_kg",
        "baseline_harvest_quantity_kg",
        "harvest_business_date",
        "target_key",
    ):
        assert token not in score_payload


# 27. no TEST access
def test_no_test_access() -> None:
    source = inspect.getsource(scoring)
    assert "test_content_bytes" not in source
    assert "TEST_BYTES" not in source
    assert "source_002" not in source.lower()


# 28. no incumbent import/use
def test_no_incumbent_import_or_use() -> None:
    source = inspect.getsource(scoring).lower()
    assert "incumbent" not in source
    assert "comparison" not in source


def _score_field_names() -> set[str]:
    return {
        field.name
        for cls in (
            scoring.FarmTotalBaselineValidationMetricCell,
            scoring.FarmTotalBaselineValidationScoreDiagnostics,
            scoring.FarmTotalBaselineValidationScorePackage,
        )
        for field in dataclasses.fields(cls)
    }


# 29. no comparison result fields
def test_no_comparison_result_fields() -> None:
    names = {name.lower() for name in _score_field_names()}
    assert not any("comparison" in name or "incumbent" in name for name in names)


# 30. no MAPE
def test_no_mape() -> None:
    assert [cell.metric_name for cell in _score().metric_cells] == ["MAE", "WAPE", "SMAPE"]
    assert "MAPE" not in _score_field_names()


# 31. no bias
def test_no_bias() -> None:
    assert not any("bias" in name.lower() for name in _score_field_names())


# 32. no coverage
def test_no_coverage() -> None:
    assert not any("coverage" in name.lower() for name in _score_field_names())


# 33. no P80/P90
def test_no_p80_p90() -> None:
    assert not any(name.lower() in {"p80", "p90"} for name in _score_field_names())


# 34. no peak/cumulative metrics
def test_no_peak_or_cumulative_metrics() -> None:
    forbidden = ("peak", "cumulative", "pinball")
    assert not any(token in name.lower() for name in _score_field_names() for token in forbidden)


# 35. fail-closed behavior deterministic
def test_fail_closed_behavior_is_deterministic() -> None:
    package, validation = _package_and_validation()
    tampered = dataclasses.replace(package, package_sha256="f" * 64)
    first = _error(tampered, validation)
    second = _error(tampered, validation)
    assert (first.blocker, first.reason_code) == (second.blocker, second.reason_code)
    assert (
        first.blocker is scoring.FarmTotalBaselineValidationScoringBlocker.PACKAGE_IDENTITY_MISMATCH
    )


def test_blocked_target_point_presence_fails_closed() -> None:
    train_rows = (
        *_five_train_rows("ready"),
        _row(
            group="weak",
            harvest_date=date(2025, 9, 1),
            quantity=Decimal("1"),
            partition="TRAIN",
        ),
    )
    validation_rows = (
        _row(
            group="weak",
            harvest_date=date(2025, 9, 1),
            quantity=Decimal("1"),
            partition="VALIDATION",
        ),
    )
    package, validation = _package_and_validation(
        train_rows=train_rows,
        validation_rows=validation_rows,
    )
    outcome = package.projection_result.target_outcomes[0]
    point = FarmTotalBaselinePoint(
        season_business_key=outcome.target_key.season_business_key,
        baseline_farm_group_key=outcome.target_key.baseline_farm_group_key,
        harvest_business_date=outcome.target_key.harvest_business_date,
        baseline_harvest_quantity_kg=Decimal("1"),
    )
    malicious_outcome = dataclasses.replace(outcome, point=point)
    malicious_projection = FarmTotalBaselineProjectionResult(
        points=(point,),
        target_outcomes=(malicious_outcome,),
    )
    malicious_package = dataclasses.replace(
        package,
        projection_result=malicious_projection,
    )
    error = _error(malicious_package, validation)
    assert (
        error.blocker
        is scoring.FarmTotalBaselineValidationScoringBlocker.BLOCKED_TARGET_POINT_PRESENT
    )


def test_target_count_diagnostic_tampering_fails_closed() -> None:
    package, validation = _package_and_validation()
    bad_diagnostics = dataclasses.replace(package.diagnostics, target_count=999)
    error = _error(dataclasses.replace(package, diagnostics=bad_diagnostics), validation)
    assert (
        error.blocker
        is scoring.FarmTotalBaselineValidationScoringBlocker.PACKAGE_DIAGNOSTIC_MISMATCH
    )


def test_invalid_package_identity_hash_fails_closed_without_row_values() -> None:
    package, validation = _package_and_validation()
    error = _error(dataclasses.replace(package, baseline_point_set_sha256="0" * 64), validation)
    assert (
        error.blocker is scoring.FarmTotalBaselineValidationScoringBlocker.PACKAGE_IDENTITY_MISMATCH
    )
    assert "30" not in str(error)


def test_validation_content_hash_mutation_fails_closed() -> None:
    package, validation = _package_and_validation()
    changed_row = dataclasses.replace(
        validation.partition_dataset.rows[0],
        row_hash="changed-row-hash",
    )
    changed = _validation_dataset(
        (changed_row, validation.partition_dataset.rows[1]),
        dataset_sha256=validation.partition_dataset.dataset_sha256,
    )
    error = _error(package, changed)
    assert error.blocker is (
        scoring.FarmTotalBaselineValidationScoringBlocker.VALIDATION_DATASET_CONTENT_HASH_MISMATCH
    )


def test_package_public_surface_has_no_raw_target_collection() -> None:
    names = _score_field_names()
    assert not any(name in {"target_keys", "points", "target_outcomes", "rows"} for name in names)


def test_metric_order_and_status_reason_families_are_frozen() -> None:
    score = _score()
    assert [cell.metric_name for cell in score.metric_cells] == ["MAE", "WAPE", "SMAPE"]
    assert {cell.metric_status.value for cell in score.metric_cells} <= {
        "COMPUTED",
        "NOT_COMPUTABLE",
    }
    assert {cell.reason_code.value for cell in score.metric_cells} <= {
        "NONE",
        "NO_COMPARABLE_TARGETS",
        "WAPE_DENOMINATOR_ZERO",
    }
