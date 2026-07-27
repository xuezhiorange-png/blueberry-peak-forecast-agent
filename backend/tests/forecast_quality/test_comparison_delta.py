"""Round C daily delta semantics and status propagation."""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from backend.app.forecast_quality.comparison import (
    ComparisonName,
    compute_model_baseline_comparisons,
)
from backend.app.forecast_quality.enums import MetricStatus, ReasonCode
from backend.tests.forecast_quality.test_comparison_point import _records

pytestmark = pytest.mark.postgres


def test_positive_negative_and_zero_delta_semantics() -> None:
    for suffix, baseline_value, expected_delta in (
        ("positive", Decimal("9"), Decimal("1.000000")),
        ("negative", Decimal("11"), Decimal("-1.000000")),
        ("tie", Decimal("10"), Decimal("0.000000")),
    ):
        input_data, spec, records = _records(suffix, count=10)
        records = tuple(
            dataclasses.replace(
                record,
                result=dataclasses.replace(
                    record.result,
                    baseline_point_forecast_kg=baseline_value,
                ),
            )
            for record in records
        )
        # Rebuild the source hashes after changing only the evidence value is
        # intentionally unnecessary for the domain contract; persistence
        # performs the full BaselineResult canonical replay check.
        results = compute_model_baseline_comparisons(
            evaluation_input=input_data, breakdown_spec=spec, baseline_records=records
        )
        mae = next(
            item for item in results if item.comparison_name is ComparisonName.DAILY_MAE_DELTA
        )
        assert mae.delta_value == expected_delta
        assert mae.metric_status is MetricStatus.COMPUTED
        assert mae.reason_code is ReasonCode.NONE


def test_one_to_nine_common_rows_are_insufficient_sample() -> None:
    input_data, spec, records = _records("insufficient", count=5)
    results = compute_model_baseline_comparisons(
        evaluation_input=input_data, breakdown_spec=spec, baseline_records=records
    )
    daily = results[:6]
    assert all(item.metric_status is MetricStatus.INSUFFICIENT_SAMPLE for item in daily)
    assert all(item.reason_code is ReasonCode.BELOW_MINIMUM for item in daily)
    assert all(item.delta_value is not None for item in daily)


def test_wape_zero_and_mape_no_eligible_rows_are_available_not_blocked() -> None:
    input_data, spec, records = _records("zero-denominators", count=10)
    rows = tuple(dataclasses.replace(row, actual_value_kg=Decimal("0")) for row in input_data.rows)
    input_data = dataclasses.replace(input_data, rows=rows)
    results = compute_model_baseline_comparisons(
        evaluation_input=input_data, breakdown_spec=spec, baseline_records=records
    )
    wape = next(item for item in results if item.comparison_name is ComparisonName.DAILY_WAPE_DELTA)
    mape = next(item for item in results if item.comparison_name is ComparisonName.DAILY_MAPE_DELTA)
    assert wape.metric_status is MetricStatus.NOT_COMPUTABLE
    assert wape.reason_code is ReasonCode.WAPE_DENOMINATOR_ZERO
    assert mape.metric_status is MetricStatus.NOT_COMPUTABLE
    assert mape.reason_code is ReasonCode.NO_MAPE_ELIGIBLE_ROWS
    assert wape.comparison_availability.value == "AVAILABLE"
    assert mape.comparison_availability.value == "AVAILABLE"
