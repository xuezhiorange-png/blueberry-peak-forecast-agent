"""Learn daily kg/mu; area is a proportional scale, not a plan feature.

JSON stores learned coefficients, not executable pickle. No label-taking prediction API.
"""

import math
from datetime import date
from decimal import Decimal
from typing import Any

import numpy as np
import sklearn
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from backend.app.area_yield.data import digest, fixed

FEATURES = ["sin1", "cos1", "sin2", "cos2"]


def features(day: date) -> list[float]:
    year = day.year if day.month >= 10 else day.year - 1
    start, end = date(year, 10, 1), date(year + 1, 10, 1)
    phase = (day - start).days / (end - start).days
    return [f(2 * math.pi * k * phase) for k in (1, 2) for f in (math.sin, math.cos)]


def fit_model(rows: list[dict[str, str]], kind: str, cutoff: date, scope_id: str) -> dict[str, Any]:
    if kind not in {"baseline", "ridge"} or not rows:
        raise ValueError("unknown model or empty training")
    x, y = [], []
    keys: set[tuple[str, str]] = set()
    for row in rows:
        day = date.fromisoformat(row["date"])
        if day > cutoff:
            raise ValueError("training beyond cutoff")
        if row["scope_id"] != scope_id:
            raise ValueError("training scope mismatch")
        key = (row["scope_id"], row["date"])
        if key in keys:
            raise ValueError("duplicate training day")
        keys.add(key)
        if not row["actual_kg"]:
            continue
        area, quantity = Decimal(row["area_mu"]), Decimal(row["actual_kg"])
        if not area.is_finite() or area <= 0 or not quantity.is_finite() or quantity < 0:
            raise ValueError("invalid training authority")
        x.append(features(day))
        y.append(float(quantity / area))
    if not y:
        raise ValueError("no known training labels")
    model: dict[str, Any] = {
        "schema": "area-yield-point-v1",
        "kind": kind,
        "scope_id": scope_id,
        "training_cutoff": cutoff.isoformat(),
        "training_rows_hash": digest(rows),
        "training_count": len(y),
        "feature_names": FEATURES if kind == "ridge" else [],
        "calendar": "OCTOBER_01_THROUGH_SEPTEMBER_30",
        "area_assumption": "PROPORTIONAL_UNVERIFIED_EXTRAPOLATION",
        "known_training_areas_mu": sorted({r["area_mu"] for r in rows}),
        "random_seed": 0,
        "numpy_version": np.__version__,
        "sklearn_version": sklearn.__version__,
        "point_only": True,
        "rounding": "KG_6DP_HALF_EVEN_AFTER_NONNEGATIVE_CLIP",
    }
    if kind == "baseline":
        # Constant density is an honest train-only distribution; never a copied future curve.
        model["mean_kg_per_mu_day"] = float(np.mean(y))
    else:
        scaler = StandardScaler().fit(x)
        regressor = Ridge(alpha=10.0, solver="svd").fit(scaler.transform(x), y)
        model.update(
            {
                "alpha": 10.0,
                "scaler_mean": scaler.mean_.tolist(),
                "scaler_scale": scaler.scale_.tolist(),
                "coefficients": regressor.coef_.tolist(),
                "intercept": float(regressor.intercept_),
            }
        )
    model["model_version"] = digest(model)
    return model


def predict(
    model: dict[str, Any], dates: list[date], area: Decimal, scope_id: str
) -> list[Decimal]:
    if not area.is_finite() or area <= 0:
        raise ValueError("area must be positive finite")
    if model["scope_id"] != scope_id:
        raise ValueError("untrained reference scope")
    preimage = {key: value for key, value in model.items() if key != "model_version"}
    if digest(preimage) != model["model_version"]:
        raise ValueError("model integrity mismatch")
    if model["schema"] != "area-yield-point-v1":
        raise ValueError("model schema mismatch")
    if any(day <= date.fromisoformat(model["training_cutoff"]) for day in dates):
        raise ValueError("prediction not after training cutoff")
    values = []
    for day in dates:
        if model["kind"] == "baseline":
            value = model["mean_kg_per_mu_day"]
        elif model["kind"] == "ridge" and model["feature_names"] == FEATURES:
            value = model["intercept"] + sum(
                (x - mean) / scale * coef
                for x, mean, scale, coef in zip(
                    features(day),
                    model["scaler_mean"],
                    model["scaler_scale"],
                    model["coefficients"],
                    strict=True,
                )
            )
        else:
            raise ValueError("unknown features/model")
        if not math.isfinite(value):
            raise ValueError("non-finite prediction")
        values.append(Decimal(fixed(Decimal(str(max(0.0, value))) * area)))
    return values
