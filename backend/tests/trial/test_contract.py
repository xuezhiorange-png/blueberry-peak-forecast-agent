from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.trial import (
    TrialForecastCreateRequest,
    TrialForecastDailyCurveResponse,
    TrialForecastDailyRow,
    TrialQualityReportCreateRequest,
    serialize_csv,
)


def test_page_dto_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        TrialForecastCreateRequest.model_validate(
            {
                "season_business_key": "season",
                "farm_business_keys": ["farm"],
                "subfarm_business_keys": ["subfarm"],
                "variety_business_keys": ["variety"],
                "requested_horizons_days": [7],
                "forecast_quantiles": ["P50"],
                "forecast_cutoff_at": "2026-07-29T08:00:00Z",
                "label_observation_cutoff_at_or_null": None,
                "request_idempotency_key": "key",
                "model_identity": "model",
                "parameter_version": "parameter",
                "policy_versions": {"forecast": "v1"},
                "database_id": 1,
            }
        )


def test_native_float_is_not_accepted_for_canonical_forecast_quantity() -> None:
    with pytest.raises(ValidationError):
        TrialForecastDailyRow(
            target_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
            p50_value_kg=1.25,
            p80_value_kg=Decimal("2"),
            p90_value_kg=Decimal("3"),
            row_status="COMPLETED",
        )


def test_timezone_aware_timestamps_are_required() -> None:
    with pytest.raises(ValidationError):
        TrialForecastDailyCurveResponse(
            run_id="run",
            forecast_cutoff_at=datetime(2026, 7, 29),
            rows=(),
        )
    with pytest.raises(ValidationError):
        TrialQualityReportCreateRequest(
            forecast_run_id="run",
            actual_label_snapshot_identity="snapshot",
            forecast_cutoff_at=datetime(2026, 7, 29, tzinfo=UTC),
            label_observation_cutoff_at=datetime(2026, 7, 29),
            forecast_horizon_days=7,
            quality_policy_version="quality-v1",
            baseline_policy_version="baseline-v1",
            request_idempotency_key="key",
        )


def test_csv_formula_injection_is_escaped_and_decimal_format_is_fixed() -> None:
    content = serialize_csv(
        ("label", "quantity"),
        (("=SUM(A1:A2)", Decimal("1.2")), ("safe", Decimal("0.0000005"))),
    ).decode("utf-8")
    assert "'=SUM(A1:A2),1.200000" in content
    assert "safe,0.000000" in content
