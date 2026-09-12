from datetime import date, timedelta

import pytest

from backend.app.area_yield.prior_shape_r3b import (
    aggregate,
    carry_forward,
    conditional_metrics,
    select,
)


def test_carry_forward_is_train_only_deterministic_and_normalized():
    rows = [
        {"farm": "A", "date": f"2023-07-{i:02}", "quantity": "" if i == 2 else str(i)}
        for i in range(1, 10)
    ]
    before = [dict(r) for r in rows]
    result = carry_forward("A", rows)
    assert result == carry_forward("A", rows)
    assert sum(result) == pytest.approx(1)
    assert min(result) >= 0
    assert rows == before
    with pytest.raises(ValueError):
        carry_forward("B", rows)
    with pytest.raises(ValueError):
        carry_forward("A", [{**rows[0], "date": "2025-01-01"}])


def test_conditional_normalization_is_evaluation_only():
    days = [date(2024, 7, 1) + timedelta(days=i) for i in range(14)]
    pred = [0.5] + [0.5 / 13] * 13
    before = pred.copy()
    result = conditional_metrics(days, [None] + [1 / 13] * 13, pred)
    assert result["known_support_wape"] == pytest.approx(0)
    assert result["peak_date_error_days"] is None
    assert result["rolling_7day_window_shift_days"] is None
    assert result["unknown_prediction_mass"] == pytest.approx(0.5)
    assert pred == before


def test_complete_window_tie_break_and_zero_support():
    days = [date(2024, 7, 1) + timedelta(days=i) for i in range(14)]
    result = conditional_metrics(days, [1 / 14] * 14, [1 / 14] * 14)
    assert result["predicted_peak_date"] == "2024-07-01"
    assert result["predicted_7day_start"] == "2024-07-01"
    assert result["peak_date_error_days"] == 0
    result = conditional_metrics(days, [None] + [1 / 13] * 13, [1.0] + [0.0] * 13)
    assert result["known_support_wape"] is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0])
def test_invalid_prediction_rejected(bad):
    days = [date(2024, 7, 1) + timedelta(days=i) for i in range(14)]
    with pytest.raises(ValueError):
        conditional_metrics(days, [1 / 14] * 14, [bad] + [1 / 14] * 13)


def test_unavailable_peak_cannot_silently_issue_winner():
    def row(peak):
        return {
            "peak_date_error_days": peak,
            "rolling_7day_window_shift_days": peak,
            "known_support_mae": 0.1,
            "known_support_wape": 0.5,
            "unknown_prediction_mass": 0.1,
        }

    macros = {"ridge": aggregate([row(20)] * 3), "prior": aggregate([row(2), row(3), row(None)])}
    assert macros["prior"]["peak_date_error_days"]["computable_farms"] == 2
    assert select(macros, 3) == "NO_CLEAR_WINNER"
    macros["prior"] = aggregate([row(2)] * 3)
    assert select(macros, 3) == "SAME_FARM_SHAPE_IMPROVED"
    macros["prior"] = aggregate([row(20)] * 3)
    assert select(macros, 3) == "GLOBAL_RIDGE_REMAINS_BEST"
