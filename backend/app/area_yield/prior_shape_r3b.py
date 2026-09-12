"""Zero-tuning same-farm carry-forward and conditional-support evaluation.

Reuses R3A's frozen July season position and prediction-only interpolation.
No validation-dependent alignment, fitting or modification of model outputs.
"""

import math
from datetime import date
from typing import Any, cast

import numpy as np

from backend.app.area_yield.confirmed_shape_r3a import fit, metrics, predict


def carry_forward(farm: str, rows: list[dict[str, str]]) -> list[float]:
    return predict(fit({farm: rows}, "2023-2024", "empirical"), "2024-2025")


def conditional_metrics(
    days: list[date], actual: list[float | None], prediction: list[float]
) -> dict[str, Any]:
    if any(not math.isfinite(v) or v < 0 for v in prediction) or any(
        v is not None and (not math.isfinite(v) or v < 0) for v in actual
    ):
        raise ValueError("invalid share")
    result = metrics(days, actual, prediction)
    known = [i for i, v in enumerate(actual) if v is not None]
    at = sum(cast(float, actual[i]) for i in known)
    pt = sum(prediction[i] for i in known)
    if at <= 0 or pt <= 0:
        result.update(known_support_mae=None, known_support_wape=None)
    else:
        error = sum(abs(cast(float, actual[i]) / at - prediction[i] / pt) for i in known)
        result.update(known_support_mae=error / len(known), known_support_wape=error)
    if not result["predicted_peak_has_known_label"]:
        result["peak_date_error_days"] = None
    if not result["predicted_7day_has_complete_labels"]:
        result["rolling_7day_window_shift_days"] = None
    result["not_computable_representation"] = "null"
    result["conditional_normalization_changes_prediction"] = False
    return result


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"farm_count": len(rows)}
    for key in (
        "peak_date_error_days",
        "rolling_7day_window_shift_days",
        "known_support_mae",
        "known_support_wape",
        "unknown_prediction_mass",
    ):
        values = [r[key] for r in rows if r[key] is not None]
        result[key] = {
            "mean": float(np.mean(values)) if values else None,
            "median": float(np.median(values)) if values else None,
            "computable_farms": len(values),
        }
    return result


def select(macros: dict[str, Any], count: int) -> str:
    a, b = macros["ridge"], macros["prior"]
    keys = (
        "peak_date_error_days",
        "rolling_7day_window_shift_days",
        "known_support_mae",
        "known_support_wape",
    )
    if any(m[k]["computable_farms"] != count for m in (a, b) for k in keys):
        return "NO_CLEAR_WINNER"
    improved = all(b[k]["mean"] < a[k]["mean"] for k in keys[:2]) and all(
        b[k]["mean"] <= a[k]["mean"] for k in keys[2:]
    )
    return "SAME_FARM_SHAPE_IMPROVED" if improved else "GLOBAL_RIDGE_REMAINS_BEST"
