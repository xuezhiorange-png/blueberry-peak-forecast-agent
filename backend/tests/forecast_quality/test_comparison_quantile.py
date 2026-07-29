"""Round C quantile and blocked-surface comparison contracts."""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from backend.app.forecast_quality.comparison import (
    ComparisonContractError,
    ComparisonName,
    compute_model_baseline_comparisons,
)
from backend.app.forecast_quality.enums import ComparisonAvailability, MetricStatus, ReasonCode
from backend.tests.forecast_quality.test_comparison_point import (
    _baseline_record,
    _inputs,
    _records,
)

pytestmark = pytest.mark.postgres


def test_baseline_p80_is_rejected_for_daily_point_comparison() -> None:
    input_data, spec, records = _records("p80", count=1)
    record = records[0]
    with pytest.raises(ComparisonContractError, match="P50"):
        compute_model_baseline_comparisons(
            evaluation_input=input_data,
            breakdown_spec=spec,
            baseline_records=(
                dataclasses.replace(
                    record,
                    request=dataclasses.replace(record.request, requested_quantile="P80"),
                    result=dataclasses.replace(record.result, baseline_quantile="P80"),
                ),
            ),
        )


def test_zero_common_rows_are_available_not_blocked() -> None:
    input_data, spec = _inputs("zero-common", count=1)
    record = _baseline_record(
        input_data,
        spec,
        1,
        baseline_value=Decimal("9"),
    )
    results = compute_model_baseline_comparisons(
        evaluation_input=input_data,
        breakdown_spec=spec,
        baseline_records=(record,),
    )
    assert len(results) == 10
    daily = results[:6]
    assert all(item.comparison_availability is ComparisonAvailability.AVAILABLE for item in daily)
    assert all(item.metric_status is MetricStatus.NOT_COMPUTABLE for item in daily)
    assert all(item.reason_code is ReasonCode.NO_S2_BINDING_ROWS for item in daily)
    assert all(item.external_blocker is None and item.frozen_limitation is None for item in daily)


def test_s3r24c_is_frozen_without_numeric_baseline_quantiles() -> None:
    input_data, spec, records = _records("blocked", count=10)
    results = compute_model_baseline_comparisons(
        evaluation_input=input_data,
        breakdown_spec=spec,
        baseline_records=records,
    )
    blocked = {item.comparison_name: item for item in results[6:]}
    for name in (
        ComparisonName.P80_COVERAGE_DELTA,
        ComparisonName.P90_COVERAGE_DELTA,
        ComparisonName.BASELINE_P80_P90_PEAK_COMPARISON,
    ):
        item = blocked[name]
        assert item.comparison_availability is ComparisonAvailability.BLOCKED
        assert item.metric_status is MetricStatus.NOT_COMPUTABLE
        assert item.reason_code is ReasonCode.BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
        assert item.frozen_limitation == item.reason_code.value
        assert item.external_blocker is None
        assert item.delta_value is None
    interval = blocked[ComparisonName.INTERVAL_WIDTH_DELTA]
    assert interval.reason_code is ReasonCode.PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE
    assert interval.frozen_limitation == interval.reason_code.value
