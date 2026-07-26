from datetime import UTC, date, datetime
from decimal import Decimal

from backend.app.forecast_quality.calculator_daily import compute_daily_metrics
from backend.app.forecast_quality.enums import FrozenVersion, ReasonCode, SupportedQuantile
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
