from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from backend.app.area_yield.formal_multi_season_validation import BusinessBoundary
from backend.app.area_yield.weather_value_conclusion import (
    ALLOWED_WEATHER_INCREMENTAL_VALUE,
    _per_base_comparison,
    compare_metrics,
    complete_horizon_views,
)

BOUNDARY = BusinessBoundary(
    season="2025-2026",
    start=date(2025, 1, 1),
    end=date(2025, 1, 31),
    authority_source="test",
    authority_hash="a" * 64,
    policy="TEST",
)


def _row(
    *,
    base_id: str,
    target_date: date,
    lead_day: int,
    actual: str,
    model_a: str,
    model_b: str,
    origin: date | None = None,
) -> dict[str, str | int]:
    origin_day = origin or target_date - timedelta(days=lead_day)
    return {
        "base_id": base_id,
        "base_name": base_id,
        "season": BOUNDARY.season,
        "forecast_origin": datetime.combine(origin_day, datetime.min.time())
        .astimezone()
        .isoformat(),
        "target_date": target_date.isoformat(),
        "lead_day": lead_day,
        "actual_daily_kg": actual,
        "model_a_predicted_daily_kg": model_a,
        "model_b_predicted_daily_kg": model_b,
    }


@pytest.mark.unit
def test_delta_relative_improvement_and_bias_magnitude_use_frozen_signs() -> None:
    rows = [
        _row(
            base_id="base-a",
            target_date=date(2025, 1, 1),
            lead_day=0,
            actual="100",
            model_a="120",
            model_b="105",
        ),
        _row(
            base_id="base-a",
            target_date=date(2025, 1, 2),
            lead_day=0,
            actual="100",
            model_a="100",
            model_b="105",
        ),
    ]
    result = compare_metrics(rows)
    assert result["absolute_delta"]["daily_wape_b_minus_a"] == "-0.05"
    assert result["relative_improvement"]["daily_wape"] == "0.5"
    assert result["bias_magnitude_delta"] == "-5"
    assert result["model_a"]["bias_kg"] == "10"
    assert result["model_b"]["bias_kg"] == "5"


@pytest.mark.unit
def test_pooled_wape_is_not_the_mean_of_base_wapes() -> None:
    rows = [
        _row(
            base_id="large",
            target_date=date(2025, 1, 1),
            lead_day=0,
            actual="1000",
            model_a="1100",
            model_b="1000",
        ),
        _row(
            base_id="small",
            target_date=date(2025, 1, 1),
            lead_day=0,
            actual="10",
            model_a="20",
            model_b="0",
        ),
    ]
    result = compare_metrics(rows)
    assert result["model_a"]["pooled_wape"] == "0.1089108910891089108910891089"
    assert result["model_b"]["pooled_wape"] == "0.009900990099009900990099009901"
    assert result["model_a"]["pooled_wape"] != "1.05"


@pytest.mark.unit
def test_incomplete_horizon_is_excluded_without_zero_fill() -> None:
    rows = [
        _row(
            base_id="complete",
            target_date=date(2025, 1, 1) + timedelta(days=lead),
            lead_day=lead,
            actual="10",
            model_a="12",
            model_b="11",
            origin=date(2025, 1, 1),
        )
        for lead in range(7)
    ]
    rows.append(
        _row(
            base_id="incomplete",
            target_date=date(2025, 1, 10),
            lead_day=0,
            actual="100",
            model_a="90",
            model_b="95",
        )
    )
    views = complete_horizon_views(rows, boundary=BOUNDARY)
    assert len(views["H7"]) == 7
    assert {row["base_id"] for row in views["H7"]} == {"complete"}


@pytest.mark.unit
def test_error_reduction_decomposition_and_leave_out_do_not_refit() -> None:
    rows = [
        _row(
            base_id=base_id,
            target_date=date(2025, 1, 1),
            lead_day=0,
            actual=actual,
            model_a=model_a,
            model_b=model_b,
        )
        for base_id, actual, model_a, model_b in (
            ("base-a", "100", "120", "105"),
            ("base-b", "10", "20", "0"),
        )
    ]
    comparison = compare_metrics(rows)
    per_base = _per_base_comparison(
        all_rows=rows,
        view_rows=rows,
        comparison=comparison,
    )
    contribution = per_base["contributions"]
    assert contribution["error_reduction_decomposition_pass"] is True
    assert contribution["top1_positive_contribution_share"] == "1"
    assert contribution["leave_top1"]["refit"] is False
    assert contribution["leave_top2"]["refit"] is False


@pytest.mark.unit
def test_same_input_produces_same_comparison_and_classification_vocabulary_is_frozen() -> None:
    rows = [
        _row(
            base_id="base-a",
            target_date=date(2025, 1, 1),
            lead_day=0,
            actual="100",
            model_a="110",
            model_b="105",
        )
    ]
    assert compare_metrics(rows) == compare_metrics(rows)
    assert ALLOWED_WEATHER_INCREMENTAL_VALUE == frozenset(
        {
            "SUPPORTED_BY_HISTORICAL_OOT_EVIDENCE",
            "NOT_DEMONSTRATED",
            "UNSTABLE_ACROSS_SEASONS",
            "INCONCLUSIVE",
        }
    )
