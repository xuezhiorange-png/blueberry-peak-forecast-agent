from datetime import UTC, date, datetime
from decimal import Decimal

from backend.app.forecast_quality.breakdown import calculate_breakdown_cells
from backend.app.forecast_quality.enums import MetricStatus, ReasonCode, SupportedQuantile
from backend.app.forecast_quality.schemas import BreakdownSpec, S3BindingRow


def test_fixed_minimum_keeps_small_cells() -> None:
    spec = BreakdownSpec(7, "farm-a", "subfarm-a", "variety-a", "season-2025", "model-a")
    row = S3BindingRow(
        "forecast",
        "physical",
        "actual",
        Decimal("1"),
        Decimal("1"),
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
    small = calculate_breakdown_cells([row] * 9, spec)[0]
    full = calculate_breakdown_cells([row] * 10, spec)[0]
    assert small["metric_status"] is MetricStatus.INSUFFICIENT_SAMPLE
    assert small["reason_code"] is ReasonCode.BELOW_MINIMUM
    assert full["metric_status"] is MetricStatus.COMPUTED
