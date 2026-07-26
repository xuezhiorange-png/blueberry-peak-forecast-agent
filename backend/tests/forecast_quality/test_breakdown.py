import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from backend.app.forecast_quality.breakdown import calculate_breakdown_cells
from backend.app.forecast_quality.enums import MetricStatus, ReasonCode, SupportedQuantile
from backend.app.forecast_quality.exceptions import S3ContractInvariantViolationError
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
    assert first["cell_identity_hash"] == second["cell_identity_hash"]
    assert first["s2_total_binding_row_count"] == 10
    assert first["s2_comparable_row_count"] == 10
    assert first["s2_excluded_row_count"] == 0
    assert first["s2_not_computable_row_count"] == 0
    assert first["coverage_ratio"] == Decimal("1")
    assert set(first["metric_values"]) == {
        "daily_mae",
        "daily_wape",
        "daily_smape",
        "daily_mape",
        "daily_bias_kg",
        "daily_relative_bias",
        "daily_absolute_error_sum_kg",
    }


def test_breakdown_ignores_rows_outside_all_six_axes_and_quantile() -> None:
    spec = _spec()
    matching = [_row(index) for index in range(10)]
    unrelated = [
        dataclasses.replace(_row(100), farm_business_key="farm-b"),
        S3BindingRow(
            "p80",
            "physical-p80",
            "actual-p80",
            Decimal("100"),
            Decimal("100"),
            SupportedQuantile.P80,
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
        ),
    ]
    baseline = calculate_breakdown_cells(matching, spec)[0]
    isolated = calculate_breakdown_cells(matching + unrelated, spec)[0]
    assert isolated == baseline


def test_unknown_matching_status_fails_closed() -> None:
    with pytest.raises(S3ContractInvariantViolationError):
        calculate_breakdown_cells(
            [dataclasses.replace(_row(1), s2_status="UNKNOWN")],
            _spec(),
        )
