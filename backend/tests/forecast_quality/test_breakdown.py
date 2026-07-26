from datetime import UTC, date, datetime
from decimal import Decimal

from backend.app.forecast_quality.breakdown import calculate_breakdown_cells
from backend.app.forecast_quality.enums import MetricStatus, ReasonCode, SupportedQuantile
from backend.app.forecast_quality.schemas import BreakdownSpec, S3BindingRow


def _spec() -> BreakdownSpec:
    return BreakdownSpec(7, "farm-a", "subfarm-a", "variety-a", "season-2025", "model-a")


def _row(index: int) -> S3BindingRow:
    return S3BindingRow(
        f"forecast-{index}",
        f"physical-{index}",
        f"actual-{index}",
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


def test_breakdown_has_all_six_axes_and_stable_identity() -> None:
    first = calculate_breakdown_cells([_row(1)] * 10, _spec())[0]
    second = calculate_breakdown_cells([_row(1)] * 10, _spec())[0]
    assert first["metric_status"] is MetricStatus.COMPUTED
    assert first["reason_code"] is ReasonCode.NONE
    assert first["cell_identity"] == second["cell_identity"]
    assert set(first["cell_identity"]) == {
        "season_business_key",
        "farm_business_key",
        "subfarm_business_key",
        "variety_business_key",
        "model_identity",
        "forecast_horizon_days",
    }
