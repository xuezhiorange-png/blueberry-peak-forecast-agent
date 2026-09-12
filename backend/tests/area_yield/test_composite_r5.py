from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.app.area_yield.composite_r5 import best, compose, evaluate
from backend.app.area_yield.evaluation import summaries


def test_composition_mass_balance_scaling_and_nonnegative():
    shape = [1 / 14] * 14
    a = compose("100", shape)
    b = compose("500", shape)
    assert abs(sum(a) - Decimal(100)) <= Decimal("0.000007")
    assert all(abs(y - 5 * x) <= Decimal("0.000003") for x, y in zip(a, b, strict=True))
    assert min(a) >= 0
    for invalid in ([float("nan")] * 14, [-1.0] * 14, [1.0] * 14):
        with pytest.raises(ValueError):
            compose("100", invalid)


def test_known_support_and_censored_peak():
    days = [date(2024, 7, 1) + timedelta(days=i) for i in range(14)]
    rows = [{"date": str(d), "quantity": "1" if i < 13 else ""} for i, d in enumerate(days)]
    shape = [0.0] * 13 + [1.0]
    result = evaluate(rows, "13", shape, "2024-07-01", "2024-07-13")
    assert result["peak_evaluation_status"] == "RIGHT_CENSORED"
    assert result["peak_date_error_days"] is None
    assert result["seven_day_shift_days"] is None
    assert result["daily_wape"] == "1.000000"


def test_no_tradeoff_forced_winner():
    rows = [
        {
            "composite": "A1",
            "total_rel_error": "0.1",
            "daily_wape": "0.2",
            "peak_date_error_days": 2,
            "seven_day_shift_days": 2,
        },
        {
            "composite": "B2",
            "total_rel_error": "0.2",
            "daily_wape": "0.1",
            "peak_date_error_days": 1,
            "seven_day_shift_days": 1,
        },
    ]
    assert best(rows) == "NO_CLEAR_WINNER"


def test_same_shape_changes_only_scale_and_preserves_canonical_timing():
    days = [date(2024, 7, 1) + timedelta(days=i) for i in range(14)]
    shape = [float(Decimal(i + 1) / 105) for i in range(14)]
    a = summaries(days, compose("100", shape))
    b = summaries(days, compose("500", shape))
    assert a["single_day_peak"]["date"] == b["single_day_peak"]["date"]
    assert a["rolling_7day_peak"]["start_date"] == b["rolling_7day_peak"]["start_date"]
    assert a["single_day_peak"]["date"] == "2024-07-14"
    assert a["rolling_7day_peak"]["start_date"] == "2024-07-08"


def test_same_total_across_shapes_and_no_label_calibration():
    days = [date(2024, 7, 1) + timedelta(days=i) for i in range(14)]
    rows = [{"date": str(d), "quantity": "1"} for d in days]
    first, second = [1 / 14] * 14, [0.0] * 13 + [1.0]
    a = evaluate(rows, "100", first, str(days[0]), str(days[-1]))
    b = evaluate(rows, "100", second, str(days[0]), str(days[-1]))
    assert a["total_rel_error"] == b["total_rel_error"]
    changed = evaluate(
        [{**r, "quantity": "100"} for r in rows], "100", first, str(days[0]), str(days[-1])
    )
    assert changed["predicted_total_kg"] == a["predicted_total_kg"]
    assert changed["predicted_peak_kg"] == a["predicted_peak_kg"]


@pytest.mark.parametrize("total", ["0", "-1", "NaN", "Infinity"])
def test_invalid_total_rejected(total):
    with pytest.raises(ValueError):
        compose(total, [1 / 14] * 14)
