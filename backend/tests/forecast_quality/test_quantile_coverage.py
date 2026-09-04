"""Tests for empirical upper-quantile coverage (S3-B coverage execution R1)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal

from backend.app.forecast_quality.calculator_daily import compute_daily_metrics
from backend.app.forecast_quality.enums import (
    FrozenVersion,
    MetricStatus,
    ReasonCode,
    SupportedQuantile,
)
from backend.app.forecast_quality.quantile_coverage import (
    assess_train_validation_coverage_execution,
    compute_upper_quantile_coverage,
    compute_upper_quantile_coverage_bundle,
)
from backend.app.forecast_quality.schemas import BreakdownSpec, S3BindingRow, S3EvaluationInput

_SPEC = BreakdownSpec(7, "farm-a", "subfarm-a", "variety-a", "season-2025", "model-a")


def _evaluation(rows: list[S3BindingRow]) -> S3EvaluationInput:
    return S3EvaluationInput(
        rows,
        "s2-run-a",
        "s2-manifest-a",
        "a" * 64,
        FrozenVersion.METRIC_INPUT_MASK_V1,
        FrozenVersion.NAIVE_BASELINE_POLICY_V1,
    )


def _row(
    index: int,
    *,
    quantile: SupportedQuantile = SupportedQuantile.P50,
    forecast: str = "10",
    actual: str = "9",
    status: str = "COMPARABLE",
    paired: bool = True,
    horizon: int = 7,
) -> S3BindingRow:
    return S3BindingRow(
        f"forecast-{index}",
        f"physical-{index}" if paired else None,
        f"actual-{index}" if paired else None,
        Decimal(forecast) if paired else None,
        Decimal(actual) if paired else None,
        quantile,
        horizon,
        date(2025, 2, 10),
        datetime(2025, 2, 1, tzinfo=UTC),
        status,
        "season-2025",
        "farm-a",
        "subfarm-a",
        "variety-a",
        "model-a",
        datetime(2025, 2, 1, tzinfo=UTC),
    )


def test_a_normal_coverage_for_p50_p80_p90() -> None:
    rows = [
        _row(0, quantile=SupportedQuantile.P50, forecast="10", actual="9"),
        _row(1, quantile=SupportedQuantile.P50, forecast="8", actual="10"),
        _row(2, quantile=SupportedQuantile.P80, forecast="12", actual="11"),
        _row(3, quantile=SupportedQuantile.P80, forecast="9", actual="10"),
        _row(4, quantile=SupportedQuantile.P90, forecast="15", actual="14"),
        _row(5, quantile=SupportedQuantile.P90, forecast="10", actual="12"),
    ]
    evaluation = _evaluation(rows)
    p50, p80, p90 = compute_upper_quantile_coverage_bundle(evaluation, _SPEC)

    assert p50.metric_status is MetricStatus.COMPUTED
    assert p50.covered_count == 1
    assert p50.coverage_comparable_row_count == 2
    assert p50.metric_value == Decimal("0.500000")

    assert p80.metric_status is MetricStatus.COMPUTED
    assert p80.covered_count == 1
    assert p80.metric_value == Decimal("0.500000")

    assert p90.metric_status is MetricStatus.COMPUTED
    assert p90.covered_count == 1
    assert p90.metric_value == Decimal("0.500000")


def test_b_exact_pairing_required() -> None:
    unpaired = _row(0, paired=False)
    result = compute_upper_quantile_coverage(_evaluation([unpaired]), _SPEC, SupportedQuantile.P50)

    assert result.metric_status is MetricStatus.NOT_COMPUTABLE
    assert result.metric_value is None
    assert result.coverage_comparable_row_count == 0


def test_c_denominator_zero_is_not_computable_without_coercing_zero() -> None:
    result = compute_upper_quantile_coverage(_evaluation([]), _SPEC, SupportedQuantile.P50)

    assert result.metric_status is MetricStatus.NOT_COMPUTABLE
    assert result.reason_code is ReasonCode.NO_S2_BINDING_ROWS
    assert result.metric_value is None
    assert result.numerator is None
    assert result.denominator is None


def test_d_quantile_isolation() -> None:
    rows = [
        _row(0, quantile=SupportedQuantile.P50, forecast="10", actual="9"),
        _row(1, quantile=SupportedQuantile.P80, forecast="20", actual="5"),
        _row(2, quantile=SupportedQuantile.P90, forecast="30", actual="5"),
    ]
    p50 = compute_upper_quantile_coverage(_evaluation(rows), _SPEC, SupportedQuantile.P50)

    assert p50.covered_count == 1
    assert p50.coverage_comparable_row_count == 1
    assert p50.metric_value == Decimal("1.000000")


def test_e_status_isolation_excludes_non_comparable_rows() -> None:
    rows = [
        _row(0, forecast="10", actual="9"),
        dataclasses.replace(_row(1), s2_status="EXCLUDED"),
        dataclasses.replace(_row(2), s2_status="NOT_COMPARABLE"),
        dataclasses.replace(_row(3), s2_status="NOT_COMPUTABLE"),
    ]
    result = compute_upper_quantile_coverage(_evaluation(rows), _SPEC, SupportedQuantile.P50)

    assert result.coverage_comparable_row_count == 1
    assert result.covered_count == 1


def test_f_boundary_actual_equals_forecast_counts_in_numerator() -> None:
    row = _row(0, forecast="10", actual="10")
    result = compute_upper_quantile_coverage(_evaluation([row]), _SPEC, SupportedQuantile.P50)

    assert result.covered_count == 1
    assert result.metric_value == Decimal("1.000000")


def test_g_deterministic_hash_replay() -> None:
    rows = [_row(0, forecast="10", actual="9"), _row(1, forecast="8", actual="10")]
    first = compute_upper_quantile_coverage(_evaluation(rows), _SPEC, SupportedQuantile.P50)
    second = compute_upper_quantile_coverage(_evaluation(rows), _SPEC, SupportedQuantile.P50)

    assert first == second
    assert first.canonical_hash == second.canonical_hash
    assert first.metric_input_mask_hash == second.metric_input_mask_hash


def test_h_no_cross_contamination_with_s1_coverage_ratio() -> None:
    rows = [
        _row(0, quantile=SupportedQuantile.P50, forecast="10", actual="9"),
        dataclasses.replace(_row(1), s2_status="EXCLUDED"),
        _row(2, quantile=SupportedQuantile.P80, forecast="12", actual="11"),
    ]
    evaluation = _evaluation(rows)
    daily = compute_daily_metrics(evaluation, _SPEC)
    coverage = compute_upper_quantile_coverage(evaluation, _SPEC, SupportedQuantile.P50)

    assert daily.coverage_ratio == Decimal("0.5")
    assert coverage.metric_value == Decimal("1.000000")
    assert coverage.metric_name == "p50_upper_coverage"


def test_train_validation_execution_blocked_without_legal_pairing_package() -> None:
    assessment = assess_train_validation_coverage_execution(None)

    assert assessment.implementation_complete is True
    assert assessment.execution_status == "NOT_COMPUTABLE_OR_BLOCKED"
    assert assessment.blocker_reason == "NO_LEGAL_TRAIN_VALIDATION_S3_BINDING_PAIRING_PACKAGE"
    assert assessment.test_remains_sealed is True
    assert assessment.results == ()


def test_train_validation_execution_runs_on_supplied_package() -> None:
    rows = [_row(0, forecast="10", actual="9")]
    assessment = assess_train_validation_coverage_execution(
        _evaluation(rows),
        breakdown_specs=(_SPEC,),
        split_labels=("TRAIN",),
    )

    assert assessment.execution_status == "EXECUTED"
    assert len(assessment.results) == 3
    assert assessment.results[0].metric_name == "p50_upper_coverage"


def test_train_validation_execution_rejects_non_train_validation_splits() -> None:
    assessment = assess_train_validation_coverage_execution(
        _evaluation([_row(0)]),
        breakdown_specs=(_SPEC,),
        split_labels=("TEST",),
    )

    assert assessment.execution_status == "NOT_COMPUTABLE_OR_BLOCKED"
    assert assessment.blocker_reason == "NON_TRAIN_VALIDATION_SPLIT_PRESENT"


def test_rejects_native_float_values() -> None:
    row = _row(0)
    bad = dataclasses.replace(row, actual_value_kg=9.0)  # type: ignore[arg-type]
    result = compute_upper_quantile_coverage(_evaluation([bad]), _SPEC, SupportedQuantile.P50)

    assert result.metric_status is MetricStatus.NOT_COMPUTABLE
