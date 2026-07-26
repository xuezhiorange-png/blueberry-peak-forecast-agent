from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from backend.app.forecast_quality.canonical import build_actual_physical_registry
from backend.app.forecast_quality.enums import SupportedQuantile
from backend.app.forecast_quality.exceptions import S3StructuralDuplicateError
from backend.app.forecast_quality.schemas import S3BindingRow


def _row(
    quantile: SupportedQuantile, identity: str = "actual-a", value: str = "10"
) -> S3BindingRow:
    return S3BindingRow(
        forecast_business_key=f"forecast-{quantile.value}",
        actual_physical_key="physical-a",
        stable_actual_identity=identity,
        forecast_value_kg=Decimal("1"),
        actual_value_kg=Decimal(value),
        forecast_quantile=quantile,
        forecast_horizon_days=7,
        forecast_target_date=date(2025, 2, 10),
        forecast_cutoff_at=datetime(2025, 2, 1, tzinfo=UTC),
        s2_status="COMPARABLE",
        season_business_key="season-2025",
        farm_business_key="farm-a",
        subfarm_business_key="subfarm-a",
        variety_business_key="variety-a",
        model_identity="model-a",
        actual_visibility_timestamp=datetime(2025, 2, 1, tzinfo=UTC),
    )


def test_cross_quantile_actual_is_registered_once() -> None:
    result = build_actual_physical_registry(
        [_row(SupportedQuantile.P50), _row(SupportedQuantile.P80), _row(SupportedQuantile.P90)]
    )
    assert result["forecast_row_count_before"] == 3
    assert result["forecast_row_count_after"] == 3
    assert result["unique_actual_physical_row_count"] == 1


def test_conflicting_actual_identity_and_value_fail_closed() -> None:
    with pytest.raises(S3StructuralDuplicateError):
        build_actual_physical_registry(
            [_row(SupportedQuantile.P50), _row(SupportedQuantile.P80, "other")]
        )
    with pytest.raises(S3StructuralDuplicateError):
        build_actual_physical_registry(
            [_row(SupportedQuantile.P50), _row(SupportedQuantile.P80, value="11")]
        )
