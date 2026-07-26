import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from backend.app.forecast_quality.calculator_daily import compute_daily_metrics
from backend.app.forecast_quality.enums import FrozenVersion, ReasonCode, SupportedQuantile
from backend.app.forecast_quality.exceptions import S3ContractInvariantViolationError
from backend.app.forecast_quality.schemas import (
    BreakdownSpec,
    DailyMetricResult,
    S3BindingRow,
    S3EvaluationInput,
)


def _row(index: int, forecast: str, actual: str) -> S3BindingRow:
    return S3BindingRow(
        f"forecast-{index}",
        f"physical-{index}",
        f"actual-{index}",
        Decimal(forecast),
        Decimal(actual),
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


def _result(values: tuple[tuple[str, str], ...]) -> DailyMetricResult:
    evaluation = S3EvaluationInput(
        [_row(index, forecast, actual) for index, (forecast, actual) in enumerate(values)],
        "s2-run-a",
        "s2-manifest-a",
        "a" * 64,
        FrozenVersion.METRIC_INPUT_MASK_V1,
        FrozenVersion.NAIVE_BASELINE_POLICY_V1,
    )
    spec = BreakdownSpec(7, "farm-a", "subfarm-a", "variety-a", "season-2025", "model-a")
    return compute_daily_metrics(evaluation, spec)


def test_seven_daily_metrics_and_full_envelope() -> None:
    result = _result((("11", "10"), ("0", "0"), ("8", "10")))
    cells = {cell.metric_name: cell for cell in result.metric_cells}
    assert cells["daily_mae"].metric_value == Decimal("1.000000")
    assert cells["daily_wape"].metric_value == Decimal("0.150000")
    assert cells["daily_smape"].metric_value == Decimal("0.105820")
    assert cells["daily_mape"].metric_value == Decimal("0.150000")
    assert cells["daily_bias_kg"].metric_value == Decimal("-0.333333")
    assert cells["daily_relative_bias"].metric_value == Decimal("-0.050000")
    assert cells["daily_absolute_error_sum_kg"].metric_value == Decimal("3.000000")
    assert all(cell.metric_status.name == "COMPUTED" for cell in cells.values())
    assert all(cell.reason_code is ReasonCode.NONE for cell in cells.values())
    assert result.mape_zero_actual_reason_code is ReasonCode.MAPE_DENOMINATOR_ZERO
    assert result.canonical_hash


def test_s2_counters_use_only_the_exact_p50_six_axis_cell() -> None:
    spec = BreakdownSpec(7, "farm-a", "subfarm-a", "variety-a", "season-2025", "model-a")
    base = _row(0, "11", "10")
    rows = [
        base,
        dataclasses.replace(base, forecast_business_key="excluded", s2_status="EXCLUDED"),
        dataclasses.replace(
            base, forecast_business_key="not-comparable", s2_status="NOT_COMPARABLE"
        ),
        dataclasses.replace(
            base, forecast_business_key="not-computable", s2_status="NOT_COMPUTABLE"
        ),
        dataclasses.replace(
            base,
            forecast_business_key="p80",
            forecast_quantile=SupportedQuantile.P80,
            s2_status="COMPARABLE",
        ),
        dataclasses.replace(
            base,
            forecast_business_key="other-farm",
            farm_business_key="farm-b",
            s2_status="COMPARABLE",
        ),
    ]
    result = compute_daily_metrics(
        S3EvaluationInput(
            rows,
            "run",
            "manifest",
            "b" * 64,
            FrozenVersion.METRIC_INPUT_MASK_V1,
            FrozenVersion.NAIVE_BASELINE_POLICY_V1,
        ),
        spec,
    )
    assert result.s2_total_binding_row_count == 4
    assert result.s2_comparable_binding_row_count == 1
    assert result.s2_excluded_binding_row_count == 2
    assert result.s2_not_computable_binding_row_count == 1
    assert result.coverage_ratio == Decimal("0.25")
    assert result.metric_input_row_count == 1
    assert result.metric_input_quantile is SupportedQuantile.P50


def test_unknown_s2_status_fails_closed() -> None:
    row = dataclasses.replace(_row(0, "11", "10"), s2_status="UNKNOWN")
    with pytest.raises(S3ContractInvariantViolationError):
        compute_daily_metrics(
            S3EvaluationInput(
                [row],
                "run",
                "manifest",
                "c" * 64,
                FrozenVersion.METRIC_INPUT_MASK_V1,
                FrozenVersion.NAIVE_BASELINE_POLICY_V1,
            ),
            BreakdownSpec(7, "farm-a", "subfarm-a", "variety-a", "season-2025", "model-a"),
        )


def test_negative_actual_is_not_mape_eligible() -> None:
    result = _result((("1", "-2"), ("5", "4")))
    cell = {item.metric_name: item for item in result.metric_cells}["daily_mape"]
    assert cell.mape_eligible_row_count == 1
    assert cell.mape_zero_actual_row_count == 0


def test_fifty_row_daily_oracles_are_independently_reproducible() -> None:
    values = ([("11", "10")] * 25) + ([("18", "20")] * 25)
    first = _result(tuple(values))
    second = _result(tuple(values))
    cells = {cell.metric_name: cell for cell in first.metric_cells}
    expected = {
        "daily_mae": Decimal("1.500000"),
        "daily_wape": Decimal("0.100000"),
        "daily_smape": Decimal("0.100251"),
        "daily_mape": Decimal("0.100000"),
        "daily_bias_kg": Decimal("-0.500000"),
        "daily_relative_bias": Decimal("-0.033333"),
        "daily_absolute_error_sum_kg": Decimal("75.000000"),
    }
    assert {name: cell.metric_value for name, cell in cells.items()} == expected
    assert all(cell.metric_status is not None for cell in cells.values())
    assert all(cell.reason_code is ReasonCode.NONE for cell in cells.values())
    assert first.s2_total_binding_row_count == 50
    assert first.s2_comparable_binding_row_count == 50
    assert first.s2_excluded_binding_row_count == 0
    assert first.s2_not_computable_binding_row_count == 0
    assert first.coverage_ratio == Decimal("1")
    assert first.metric_input_row_count == 50
    assert first.mape_eligible_row_count == 50
    assert first.mape_zero_actual_row_count == 0
    assert first.metric_input_mask_hash == second.metric_input_mask_hash
    assert first.canonical_hash == second.canonical_hash
