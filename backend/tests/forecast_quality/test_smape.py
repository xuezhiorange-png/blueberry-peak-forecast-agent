from datetime import UTC, date, datetime
from decimal import Decimal

from backend.app.forecast_quality.calculator_daily import compute_daily_metrics
from backend.app.forecast_quality.enums import FrozenVersion, SupportedQuantile
from backend.app.forecast_quality.schemas import BreakdownSpec, S3BindingRow, S3EvaluationInput


def test_smape_double_zero_is_zero_contribution() -> None:
    row = S3BindingRow(
        "forecast",
        "physical",
        "actual",
        Decimal("0"),
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
    cell = {item.metric_name: item for item in result.metric_cells}["daily_smape"]
    assert cell.metric_value == Decimal("0.000000")
