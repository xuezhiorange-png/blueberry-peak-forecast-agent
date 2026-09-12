"""Comparable point errors and canonical strict-calendar seven-day peak diagnostics."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from backend.app.area_yield.data import fixed
from backend.app.core_forecast.metrics import compute_point_series_metrics


def summaries(dates: list[date], quantities: list[Decimal]) -> dict[str, Any]:
    if len(dates) != len(quantities) or len(dates) < 7:
        raise ValueError("seven-day complete curve required")
    if any(b != a + timedelta(days=1) for a, b in zip(dates, dates[1:], strict=False)):
        raise ValueError("noncontinuous curve")
    metric = compute_point_series_metrics(
        [(day, int(value * 1_000_000)) for day, value in zip(dates, quantities, strict=True)],
        quantile="P50",
    )
    result = metric.model_dump(mode="json")
    return {
        "total_kg": fixed(sum(quantities, Decimal(0))),
        "single_day_peak": result["single_day_peak"],
        "rolling_7day_peak": result["sustained_7day_peak"],
        "interpretation": "POINT_ONLY_NOT_CALIBRATED_QUANTILES",
    }


def compare(rows: list[dict[str, str]], predictions: list[Decimal]) -> dict[str, Any]:
    if len(rows) != len(predictions) or not rows:
        raise ValueError("comparable surface mismatch")
    known = [
        (Decimal(r["actual_kg"]), p)
        for r, p in zip(rows, predictions, strict=True)
        if r["actual_kg"] != ""
    ]
    denominator = sum((a for a, _ in known), Decimal(0))
    absolute = sum((abs(a - p) for a, p in known), Decimal(0))
    result: dict[str, Any] = {
        "comparable_rows": len(known),
        "missing_label_rows": len(rows) - len(known),
        "daily_mae_kg": fixed(absolute / len(known)) if known else None,
        "daily_wape": fixed(absolute / denominator) if denominator > 0 else None,
        "wape_reason": "COMPUTED" if denominator > 0 else "ZERO_ACTUAL_DENOMINATOR",
        "window_total_absolute_error_kg": None,
        "window_total_relative_error": None,
        "single_day_peak_absolute_error_kg": None,
        "single_day_peak_date_error_days": None,
        "rolling_7day_peak_absolute_error_kg": None,
        "rolling_7day_window_shift_days": None,
        "window_metrics_status": "NOT_COMPUTABLE_MISSING_LABELS",
        "full_season": False,
    }
    dates = [date.fromisoformat(r["date"]) for r in rows]
    continuous = all(b == a + timedelta(days=1) for a, b in zip(dates, dates[1:], strict=False))
    if len(known) != len(rows) or not continuous or len(rows) < 7:
        return result
    actual = summaries(dates, [a for a, _ in known])
    predicted = summaries(dates, predictions)
    error = abs(Decimal(actual["total_kg"]) - Decimal(predicted["total_kg"]))
    result.update(
        {
            "window_metrics_status": "COMPUTED_COMPLETE_PARTIAL_SEASON_WINDOW",
            "window_total_absolute_error_kg": fixed(error),
            "window_total_relative_error": fixed(error / denominator) if denominator > 0 else None,
            "actual": actual,
            "predicted": predicted,
        }
    )
    for key, quantity, datekey, errorkey, shiftkey in (
        (
            "single_day_peak",
            "quantity_kg",
            "date",
            "single_day_peak_absolute_error_kg",
            "single_day_peak_date_error_days",
        ),
        (
            "rolling_7day_peak",
            "cumulative_quantity_kg",
            "start_date",
            "rolling_7day_peak_absolute_error_kg",
            "rolling_7day_window_shift_days",
        ),
    ):
        result[errorkey] = fixed(
            abs(Decimal(actual[key][quantity]) - Decimal(predicted[key][quantity]))
        )
        result[shiftkey] = abs(
            (
                date.fromisoformat(actual[key][datekey])
                - date.fromisoformat(predicted[key][datekey])
            ).days
        )
    return result
