"""Frozen component multiplication, canonical point metrics and censor-aware evaluation."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from backend.app.area_yield.censor_r3c import evaluation_status
from backend.app.area_yield.evaluation import compare, summaries
from backend.app.area_yield.total_yield_r4 import emit, positive


def compose(total: str, shares: list[float]) -> list[Decimal]:
    amount = positive(total)
    values = [Decimal(str(v)) for v in shares]
    if not values or any(not v.is_finite() or v < 0 for v in values):
        raise ValueError("invalid share")
    if abs(sum(values, Decimal(0)) - 1) > Decimal("1e-12"):
        raise ValueError("shape not normalized")
    result = [Decimal(emit(amount * v)) for v in values]
    tolerance = Decimal("0.0000005") * len(values) + amount * Decimal("1e-12")
    if abs(sum(result, Decimal(0)) - amount) > tolerance:
        raise ValueError("MASS_BALANCE_FAIL")
    return result


def evaluate(
    rows: list[dict[str, str]], total: str, shares: list[float], start: str, end: str
) -> dict[str, Any]:
    prediction = compose(total, shares)
    days = [date.fromisoformat(r["date"]) for r in rows]
    summary = summaries(days, prediction)
    points = compare([{**r, "actual_kg": r["quantity"]} for r in rows], prediction)
    actual = {i: Decimal(r["quantity"]) for i, r in enumerate(rows) if r["quantity"] != ""}
    if not actual or any(not v.is_finite() or v < 0 for v in actual.values()):
        raise ValueError("invalid labels")
    actual_total = sum(actual.values(), Decimal(0))
    if actual_total <= 0:
        raise ValueError("zero actual denominator")
    predicted_known = sum((prediction[i] for i in actual), Decimal(0))
    conditional = (
        sum(
            (abs(actual[i] / actual_total - prediction[i] / predicted_known) for i in actual),
            Decimal(0),
        )
        if predicted_known > 0
        else None
    )
    ai = max(actual, key=lambda i: actual[i])
    windows = [i for i in range(len(days) - 6) if all(j in actual for j in range(i, i + 7))]
    if not windows:
        raise ValueError("no complete actual seven-day window")
    aj = max(windows, key=lambda i: sum((actual[j] for j in range(i, i + 7)), Decimal(0)))
    peak, week = summary["single_day_peak"], summary["rolling_7day_peak"]
    pd, wd = date.fromisoformat(peak["date"]), date.fromisoformat(week["start_date"])
    pi, wi = days.index(pd), days.index(wd)
    cs, ce = date.fromisoformat(start), date.fromisoformat(end)
    ps = evaluation_status(pd, pd, cs, ce, pi in actual)
    ws = evaluation_status(wd, wd + timedelta(days=6), cs, ce, wi in windows)
    total_error = abs(positive(total) - actual_total)
    return {
        "predicted_total_kg": total,
        "actual_total_kg": emit(actual_total),
        "total_abs_error_kg": emit(total_error),
        "total_rel_error": emit(total_error / actual_total),
        "daily_mae_kg": points["daily_mae_kg"],
        "daily_wape": points["daily_wape"],
        "known_support_wape": emit(conditional) if conditional is not None else None,
        "known_rows": len(actual),
        "unknown_rows": len(rows) - len(actual),
        "predicted_peak_date": str(pd),
        "predicted_peak_kg": peak["quantity_kg"],
        "actual_peak_date": str(days[ai]),
        "actual_peak_kg": emit(actual[ai]),
        "peak_date_error_days": abs((pd - days[ai]).days) if ps == "EXACT_COMPUTABLE" else None,
        "peak_quantity_abs_error_kg": emit(abs(Decimal(peak["quantity_kg"]) - actual[ai]))
        if ps == "EXACT_COMPUTABLE"
        else None,
        "peak_evaluation_status": ps,
        "predicted_7day_start": str(wd),
        "predicted_7day_kg": week["cumulative_quantity_kg"],
        "actual_7day_start": str(days[aj]),
        "actual_7day_kg": emit(sum((actual[j] for j in range(aj, aj + 7)), Decimal(0))),
        "seven_day_shift_days": abs((wd - days[aj]).days) if ws == "EXACT_COMPUTABLE" else None,
        "seven_day_quantity_abs_error_kg": emit(
            abs(
                Decimal(week["cumulative_quantity_kg"])
                - sum((actual[j] for j in range(aj, aj + 7)), Decimal(0))
            )
        )
        if ws == "EXACT_COMPUTABLE"
        else None,
        "seven_day_evaluation_status": ws,
        "unknown_prediction_mass": str(
            sum((Decimal(str(shares[i])) for i in range(len(rows)) if i not in actual), Decimal(0))
        ),
        "daily_sum_kg": summary["total_kg"],
        "mass_balance_error_kg": emit(sum(prediction, Decimal(0)) - positive(total)),
        "mass_balance_pass": True,
    }


def best(rows: list[dict[str, Any]]) -> str:
    keys = ("total_rel_error", "daily_wape", "peak_date_error_days", "seven_day_shift_days")
    if any(r[k] is None for r in rows for k in keys):
        return "NO_CLEAR_WINNER"
    winners = []
    for r in rows:
        if all(
            all(Decimal(str(r[k])) <= Decimal(str(s[k])) for k in keys)
            and any(Decimal(str(r[k])) < Decimal(str(s[k])) for k in keys)
            for s in rows
            if s["composite"] != r["composite"]
        ):
            winners.append(r["composite"])
    return winners[0] if len(winners) == 1 else "NO_CLEAR_WINNER"
