from datetime import UTC, date, datetime
from decimal import Decimal

from backend.app.forecast_quality.calculator_daily import compute_daily_metrics
from backend.app.forecast_quality.enums import FrozenVersion, ReasonCode, SupportedQuantile
from backend.app.forecast_quality.schemas import BreakdownSpec, S3BindingRow, S3EvaluationInput


def test_mape_excludes_zero_actual_but_keeps_audit_count() -> None:
    def row(index: int, actual: str) -> S3BindingRow:
        return S3BindingRow(
            f"forecast-{index}",
            f"physical-{index}",
            f"actual-{index}",
            Decimal("1"),
            Decimal(actual),
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
            [row(0, "0"), row(1, "10")],
            "run",
            "manifest",
            "a" * 64,
            FrozenVersion.METRIC_INPUT_MASK_V1,
            FrozenVersion.NAIVE_BASELINE_POLICY_V1,
        ),
        BreakdownSpec(7, "farm", "subfarm", "variety", "season", "model"),
    )
    cell = {item.metric_name: item for item in result.metric_cells}["daily_mape"]
    assert cell.metric_status.name == "COMPUTED"
    assert cell.reason_code is ReasonCode.NONE
    assert cell.mape_eligible_row_count == 1
    assert cell.mape_zero_actual_row_count == 1
