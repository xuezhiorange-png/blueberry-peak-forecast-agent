from datetime import UTC, date, datetime
from decimal import Decimal

from backend.app.forecast_quality.calculator_daily import compute_daily_metrics
from backend.app.forecast_quality.enums import FrozenVersion, ReasonCode, SupportedQuantile
from backend.app.forecast_quality.schemas import BreakdownSpec, S3BindingRow, S3EvaluationInput


def test_zero_denominators_are_statuses_not_exceptions() -> None:
    row = S3BindingRow(
        "forecast",
        "physical",
        "actual",
        Decimal("1"),
        Decimal("0"),
        SupportedQuantile.P50,
        7,
        date(2025, 2, 10),
        datetime(2025, 2, 1, tzinfo=UTC),
        "COMPARABLE",
        "season",
        "farm",
        "subfarm",
        "variety",
        "model",
        datetime(2025, 2, 1, tzinfo=UTC),
    )
    result = compute_daily_metrics(
        S3EvaluationInput(
            [row],
            "run",
            "manifest",
            "a" * 64,
            FrozenVersion.METRIC_INPUT_MASK_V1,
            FrozenVersion.NAIVE_BASELINE_POLICY_V1,
        ),
        BreakdownSpec(7, "farm", "subfarm", "variety", "season", "model"),
    )
    cells = {item.metric_name: item for item in result.metric_cells}
    assert cells["daily_wape"].reason_code is ReasonCode.WAPE_DENOMINATOR_ZERO
    assert cells["daily_relative_bias"].reason_code is ReasonCode.RELATIVE_BIAS_DENOMINATOR_ZERO
    assert cells["daily_mape"].reason_code is ReasonCode.NO_MAPE_ELIGIBLE_ROWS
