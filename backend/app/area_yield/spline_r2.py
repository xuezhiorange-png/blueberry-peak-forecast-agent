"""Single-season train-fold spline density; JSON BSpline persistence, no target labels."""

from datetime import date
from decimal import Decimal
from typing import Any

import numpy as np
import scipy  # type: ignore[import-untyped]
import sklearn
from scipy.interpolate import BSpline  # type: ignore[import-untyped]
from sklearn.linear_model import Ridge
from sklearn.preprocessing import SplineTransformer, StandardScaler

from backend.app.area_yield.data import digest, fixed


def position(day: date) -> float:
    year = day.year if day.month >= 10 else day.year - 1
    start, end = date(year, 10, 1), date(year + 1, 10, 1)
    return (day - start).days / (end - start).days


def fit(rows: list[dict[str, str]], cutoff: date, scope: str) -> dict[str, Any]:
    x, y = [], []
    seen: set[str] = set()
    for row in rows:
        day = date.fromisoformat(row["date"])
        if day > cutoff:
            raise ValueError("training beyond cutoff")
        if row["scope_id"] != scope or row["date"] in seen:
            raise ValueError("scope mismatch or duplicate day")
        seen.add(row["date"])
        if not row["actual_kg"]:
            continue
        area, actual = Decimal(row["area_mu"]), Decimal(row["actual_kg"])
        if not area.is_finite() or area <= 0 or not actual.is_finite() or actual < 0:
            raise ValueError("invalid training quantity/area")
        x.append([position(day)])
        y.append(float(actual / area))
    if len(x) < 6:
        raise ValueError("insufficient spline training positions")
    transform = SplineTransformer(
        n_knots=6, degree=3, include_bias=False, knots="uniform", extrapolation="linear"
    ).fit(x)
    design = transform.transform(x)
    scale = StandardScaler().fit(design)
    reg = Ridge(alpha=10.0, solver="svd").fit(scale.transform(design), y)
    spline = transform.bsplines_[0]
    model: dict[str, Any] = {
        "schema": "single-season-spline-r2",
        "kind": "spline",
        "scope_id": scope,
        "training_cutoff": cutoff.isoformat(),
        "training_count": len(y),
        "training_rows_hash": digest(rows),
        "number_of_knots": 6,
        "degree": 3,
        "include_bias": False,
        "alpha": 10.0,
        "extrapolation": "linear",
        "knots_policy": "UNIFORM_TRAIN_POSITION_MIN_MAX_ONLY",
        "bspline_t": spline.t.tolist(),
        "bspline_c": spline.c.tolist(),
        "scaler_mean": scale.mean_.tolist(),
        "scaler_scale": scale.scale_.tolist(),
        "coefficients": reg.coef_.tolist(),
        "intercept": float(reg.intercept_),
        "training_position_min": min(v[0] for v in x),
        "training_position_max": max(v[0] for v in x),
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "sklearn_version": sklearn.__version__,
        "random_state": 0,
        "feature": "NORMALIZED_OCTOBER_01_SEASON_POSITION",
        "area_scaling_policy": "LINEAR_BUSINESS_ASSUMPTION",
        "area_scaling_validated": False,
        "point_only": True,
    }
    model["model_version"] = digest(model)
    return model


def basis(model: dict[str, Any], positions: Any) -> Any:
    # Reproduce sklearn's public linear BSpline boundary policy, not polynomial continuation.
    spline = BSpline(model["bspline_t"], model["bspline_c"], model["degree"], extrapolate=False)
    x = np.asarray(positions, dtype=float)
    left, right = spline.t[spline.k], spline.t[-spline.k - 1]
    clipped = np.clip(x, left, right)
    values = spline(clipped) + spline.derivative()(clipped) * (x - clipped)[:, None]
    return values[:, :-1]  # include_bias=False, identical to fitted SplineTransformer.


def predict(model: dict[str, Any], dates: list[date], area: Decimal, scope: str) -> list[Decimal]:
    if digest({k: v for k, v in model.items() if k != "model_version"}) != model["model_version"]:
        raise ValueError("model integrity mismatch")
    if model["schema"] != "single-season-spline-r2" or model["scope_id"] != scope:
        raise ValueError("unsupported model or reference scope")
    if not area.is_finite() or area <= 0:
        raise ValueError("positive finite area required")
    if any(day <= date.fromisoformat(model["training_cutoff"]) for day in dates):
        raise ValueError("prediction must follow training cutoff")
    return project(model, dates, area)


def project(model: dict[str, Any], dates: list[date], area: Decimal) -> list[Decimal]:
    """Internal design projection, also used for explicitly non-evaluation fitted values."""
    design = basis(model, [position(day) for day in dates])
    standardized = (design - np.asarray(model["scaler_mean"])) / np.asarray(model["scaler_scale"])
    values = standardized @ np.asarray(model["coefficients"]) + model["intercept"]
    if not np.all(np.isfinite(values)):
        raise ValueError("non-finite spline output")
    return [Decimal(fixed(Decimal(str(max(0.0, float(v)))) * area)) for v in values]
