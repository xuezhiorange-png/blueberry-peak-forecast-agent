from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from backend.app.forecast_quality.aggregation import (
    aggregate_daily_actuals,
    aggregate_daily_forecasts,
)
from backend.app.forecast_quality.enums import SupportedQuantile
from backend.app.forecast_quality.exceptions import S3StructuralDuplicateError
from backend.app.forecast_quality.schemas import S3BindingRow


def _row(key: str, quantile: SupportedQuantile, value: str, physical: str) -> S3BindingRow:
    return S3BindingRow(
        forecast_business_key=key,
        actual_physical_key=physical,
        stable_actual_identity=f"actual-{physical}",
        forecast_value_kg=Decimal(value),
        actual_value_kg=Decimal("10"),
        forecast_quantile=quantile,
        forecast_horizon_days=7,
        forecast_target_date=date(2025, 2, 10),
        forecast_cutoff_at=datetime(2025, 2, 1, tzinfo=UTC),
        s2_status="COMPARABLE",
        season_business_key="season-2025",
        farm_business_key="farm-a",
        subfarm_business_key=f"sub-{key}",
        variety_business_key="variety-a",
        model_identity="model-a",
        actual_visibility_timestamp=datetime(2025, 2, 1, tzinfo=UTC),
    )


def test_farm_aggregation_preserves_quantiles_and_sums_subfarms() -> None:
    rows = [
        _row("p50-a", SupportedQuantile.P50, "5", "physical-a"),
        _row("p50-b", SupportedQuantile.P50, "3", "physical-b"),
        _row("p80-a", SupportedQuantile.P80, "7", "physical-c"),
        _row("p90-a", SupportedQuantile.P90, "9", "physical-d"),
    ]
    result = aggregate_daily_forecasts(rows)
    assert {item.forecast_quantile for item in result} == {
        SupportedQuantile.P50,
        SupportedQuantile.P80,
        SupportedQuantile.P90,
    }
    assert {item.forecast_quantile: item.forecast_value_kg for item in result} == {
        SupportedQuantile.P50: Decimal("8"),
        SupportedQuantile.P80: Decimal("7"),
        SupportedQuantile.P90: Decimal("9"),
    }
    actual = aggregate_daily_actuals(rows)
    assert actual[0].actual_value_kg == Decimal("40")


def test_duplicate_forecast_key_is_structural_failure() -> None:
    row = _row("duplicate", SupportedQuantile.P50, "1", "physical-a")
    with pytest.raises(S3StructuralDuplicateError):
        aggregate_daily_forecasts([row, row])
