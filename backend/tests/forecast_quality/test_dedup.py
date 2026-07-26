from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from backend.app.forecast_quality.aggregation import aggregate_daily_forecasts
from backend.app.forecast_quality.canonical import build_actual_physical_registry
from backend.app.forecast_quality.enums import SupportedQuantile
from backend.app.forecast_quality.exceptions import S3StructuralDuplicateError
from backend.app.forecast_quality.schemas import S3BindingRow


def _row(key: str, physical: str) -> S3BindingRow:
    return S3BindingRow(
        key,
        physical,
        f"actual-{physical}",
        Decimal("1"),
        Decimal("1"),
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


def test_duplicate_forecast_and_conflicting_actual_keys_fail_closed() -> None:
    row = _row("forecast", "physical")
    with pytest.raises(S3StructuralDuplicateError):
        aggregate_daily_forecasts([row, row])
    conflicting = _row("other", "physical")
    conflicting = S3BindingRow(
        conflicting.forecast_business_key,
        conflicting.actual_physical_key,
        "different",
        conflicting.forecast_value_kg,
        conflicting.actual_value_kg,
        conflicting.forecast_quantile,
        conflicting.forecast_horizon_days,
        conflicting.forecast_target_date,
        conflicting.forecast_cutoff_at,
        conflicting.s2_status,
        conflicting.season_business_key,
        conflicting.farm_business_key,
        conflicting.subfarm_business_key,
        conflicting.variety_business_key,
        conflicting.model_identity,
        conflicting.actual_visibility_timestamp,
    )
    with pytest.raises(S3StructuralDuplicateError):
        build_actual_physical_registry([row, conflicting])
