"""Confirmed-export shape experiment. UNKNOWN labels never become zero or fit targets.

Metrics describe known recorded-ledger shares, not unobserved biological season truth.
Prediction always covers a fixed full calendar; no validation-label alignment or scaling.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

import numpy as np
import sklearn
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from backend.app.area_yield.data import digest
from backend.app.area_yield.shape_r3 import harmonics, normalize, season_calendar


def labels(rows: list[dict[str, str]]) -> list[float | None]:
    values = [Decimal(r["quantity"]) if r["quantity"] != "" else None for r in rows]
    if any(v is not None and (not v.is_finite() or v < 0) for v in values):
        raise ValueError("invalid label")
    total = sum((v for v in values if v is not None), Decimal(0))
    if total <= 0:
        raise ValueError("no positive recorded total")
    return [float(v / total) if v is not None else None for v in values]


def fit(curves: dict[str, list[dict[str, str]]], season: str, kind: str) -> dict[str, Any]:
    if season != "2023-2024" or not curves or kind not in {"ridge", "empirical"}:
        raise ValueError("unauthorized training season/model")
    calendar = season_calendar(season)
    index = {d: i / len(calendar) for i, d in enumerate(calendar)}
    positions, y, weights = [], [], []
    per_position: dict[float, list[float]] = defaultdict(list)
    counts = []
    for farm, rows in sorted(curves.items()):
        dates = [date.fromisoformat(r["date"]) for r in rows]
        if len(set(dates)) != len(dates) or any(d not in index for d in dates):
            raise ValueError("future label or duplicate training day")
        if any(r["farm"] != farm for r in rows):
            raise ValueError("farm mismatch")
        shares = labels(rows)
        count = sum(v is not None for v in shares)
        counts.append(count)
        for d, value in zip(dates, shares, strict=True):
            if value is not None:
                positions.append(index[d])
                y.append(value)
                weights.append(1 / count)
                per_position[index[d]].append(value)
    model: dict[str, Any] = {
        "kind": kind,
        "training_season": season,
        "train_hash": digest(curves),
        "farm_count": len(curves),
        "known_training_rows": len(y),
        "calendar": "JULY_01_THROUGH_JUNE_30",
        "prediction_quantity": "SHARE_ONLY",
        "sklearn_version": sklearn.__version__,
        "numpy_version": np.__version__,
    }
    if kind == "empirical":
        model["positions"] = sorted(per_position)
        model["values"] = [float(np.mean(per_position[p])) for p in model["positions"]]
        model["gap_policy"] = "PREDICTION_INTERPOLATION_NOT_LABEL_IMPUTATION"
    else:
        x = harmonics(positions)
        scaler = StandardScaler().fit(x)
        sample_weights = np.asarray(weights) * np.mean(counts)
        reg = Ridge(alpha=10.0, solver="svd").fit(
            scaler.transform(x), y, sample_weight=sample_weights
        )
        model.update(
            mean=scaler.mean_.tolist(),
            scale=scaler.scale_.tolist(),
            coefficients=reg.coef_.tolist(),
            intercept=float(reg.intercept_),
            alpha=10.0,
        )
    model["hash"] = digest(model)
    return model


def predict(model: dict[str, Any], season: str) -> list[float]:
    if digest({k: v for k, v in model.items() if k != "hash"}) != model["hash"]:
        raise ValueError("model hash mismatch")
    if int(season[:4]) <= int(model["training_season"][:4]):
        raise ValueError("prediction must follow training season")
    days = len(season_calendar(season))
    positions = np.arange(days) / days
    if model["kind"] == "empirical":
        values = np.interp(positions, model["positions"], model["values"])
    else:
        values = ((harmonics(positions) - model["mean"]) / model["scale"]) @ model[
            "coefficients"
        ] + model["intercept"]
    return normalize(values.tolist())


def metrics(
    days: list[date], actual: list[float | None], prediction: list[float]
) -> dict[str, Any]:
    if len(days) != len(actual) or len(days) != len(prediction):
        raise ValueError("non comparable")
    known = [i for i, v in enumerate(actual) if v is not None]
    if not known or any((b - a).days != 1 for a, b in zip(days, days[1:], strict=False)):
        raise ValueError("no known labels or noncontinuous calendar")
    a = {i: float(actual[i]) for i in known}  # type: ignore[arg-type]
    ai = max(known, key=lambda i: a[i])
    pi = max(range(len(prediction)), key=lambda i: prediction[i])
    windows = [i for i in range(len(days) - 6) if all(j in a for j in range(i, i + 7))]
    if not windows:
        raise ValueError("no complete seven-day label window")
    aj = max(windows, key=lambda i: sum(a[j] for j in range(i, i + 7)))
    pj = max(range(len(days) - 6), key=lambda i: sum(prediction[i : i + 7]))
    error = sum(abs(a[i] - prediction[i]) for i in known)
    return {
        "known_rows": len(known),
        "unknown_rows": len(days) - len(known),
        "complete_7day_label_windows": len(windows),
        "actual_peak_date": str(days[ai]),
        "predicted_peak_date": str(days[pi]),
        "peak_date_error_days": abs((days[ai] - days[pi]).days),
        "actual_7day_start": str(days[aj]),
        "predicted_7day_start": str(days[pj]),
        "rolling_7day_window_shift_days": abs((days[aj] - days[pj]).days),
        "daily_share_mae": error / len(known),
        "daily_share_wape": error / sum(a.values()),
        "peak_share_error": abs(a[ai] - prediction[pi]),
        "seven_day_share_error": abs(
            sum(a[j] for j in range(aj, aj + 7)) - sum(prediction[pj : pj + 7])
        ),
        "unknown_prediction_mass": sum(prediction[i] for i in range(len(days)) if i not in a),
        "predicted_peak_has_known_label": pi in a,
        "predicted_7day_has_complete_labels": pj in windows,
        "metric_scope": "KNOWN_RECORDED_LEDGER_LABELS_ONLY_UNKNOWN_DAYS_NOT_ZERO",
        "unobserved_full_season_peak_truth_proven": False,
    }


def macro(rows: list[dict[str, Any]]) -> dict[str, Any]:
    peak = [r["peak_date_error_days"] for r in rows]
    shift = [r["rolling_7day_window_shift_days"] for r in rows]
    return {
        "farm_count": len(rows),
        "median_peak_date_error_days": float(np.median(peak)),
        "mean_peak_date_error_days": float(np.mean(peak)),
        "p90_peak_date_error_days": float(np.quantile(peak, 0.9, method="linear")),
        "median_7day_shift_days": float(np.median(shift)),
        "mean_7day_shift_days": float(np.mean(shift)),
        "daily_share_mae": float(np.mean([r["daily_share_mae"] for r in rows])),
        "daily_share_wape": float(np.mean([r["daily_share_wape"] for r in rows])),
        "farms_peak_error_le_7": sum(v <= 7 for v in peak),
        "farms_peak_error_le_14": sum(v <= 14 for v in peak),
        "farms_peak_error_gt_30": sum(v > 30 for v in peak),
    }
