"""One convex conditional log-density family; portable deterministic research core.

No file reads, database, weather retrieval, or target lookup occurs in inference.
Context contains only the fitted training pool's past anonymous summaries.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
from scipy.interpolate import BSpline  # type: ignore[import-untyped]
from scipy.optimize import minimize  # type: ignore[import-untyped]
from scipy.special import logsumexp  # type: ignore[import-untyped]

Objective = Callable[[np.ndarray], tuple[float, np.ndarray]]

GAP_TOL = 1e-8
SOLVE_CACHE: dict[str, dict[str, Any]] = {}
GROUP_NAMES = {
    "H": [
        "latest_log_yield",
        "latest_canonical_P50",
        "latest_P90_minus_P10",
        "past_record_count",
        "H_missing",
    ],
    "W": [
        "past_climate_early_third_mean_c",
        "past_climate_middle_third_mean_c",
        "past_climate_late_third_mean_c",
        "past_climate_temperature_std_c",
        "W_missing",
    ],
    "V": ["past_share_Dx", "past_share_D2", "past_share_D12", "past_mapped_coverage", "V_missing"],
}


def groups(version: str) -> str:
    return {"CG0": "", "CGH": "H", "CGHW": "HW", "CGHWV": "HWV"}[version]


def positions(dates: list[str], season: str) -> np.ndarray:
    origin = date(int(season[:4]), 7, 1)
    return np.array([(date.fromisoformat(d) - origin).days for d in dates], dtype=int)


def basis(days: np.ndarray, count: int) -> np.ndarray:
    if count not in (4, 6) or np.any(days < 0) or np.any(days > 289):
        raise ValueError("INVALID_CANONICAL_BASIS")
    knots = np.r_[np.zeros(4), np.linspace(0, 1, count - 2)[1:-1], np.ones(4)]
    full = BSpline(knots, np.eye(count), 3, extrapolate=False)(days / 289)
    # Partition of unity makes the all-coefficient constant direction redundant.
    return np.asarray(full[:, :-1], dtype=float)


def softmax(score: np.ndarray) -> np.ndarray:
    return np.asarray(np.exp(score - logsumexp(score)), dtype=float)


def shape_predict(theta: list[float] | np.ndarray, b: np.ndarray, x: np.ndarray) -> np.ndarray:
    coefficients = np.asarray(theta).reshape(len(x) + 1, b.shape[1])
    return softmax(b @ (np.r_[1.0, x] @ coefficients))


def shape_objective(
    bases: list[np.ndarray], x: np.ndarray, targets: list[np.ndarray], lam: float
) -> Objective:
    if lam <= 0 or len(bases) != len(targets) or len(x) != len(targets) or not targets:
        raise ValueError("INVALID_SHAPE_OBJECTIVE")
    z = np.column_stack([np.ones(len(x)), x])
    nb = bases[0].shape[1]

    def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
        coef = theta.reshape(z.shape[1], nb)
        loss = 0.0
        gradient = np.zeros_like(coef)
        for b, features, truth in zip(bases, z, targets, strict=True):
            score = b @ (features @ coef)
            logp = score - logsumexp(score)
            loss -= float(truth @ logp) / len(x)
            gradient += np.outer(features, b.T @ (np.exp(logp) - truth)) / len(x)
        return loss + lam * float(theta @ theta) / 2, gradient.ravel() + lam * theta

    return objective


def total_objective(x: np.ndarray, area: np.ndarray, q: np.ndarray, lam: float) -> Objective:
    if q.sum() <= 0 or np.any(q < 0) or np.any(area <= 0) or lam <= 0:
        raise ValueError("INVALID_TOTAL_OBJECTIVE")
    truth = q / q.sum()

    def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
        score = np.log(area) + x @ beta
        logw = score - logsumexp(score)
        return (
            -float(truth @ logw) + lam * float(beta @ beta) / 2,
            x.T @ (np.exp(logw) - truth) + lam * beta,
        )

    return objective


def total_intercept(beta: np.ndarray, x: np.ndarray, area: np.ndarray, q: np.ndarray) -> float:
    return float(np.log(q.sum()) - logsumexp(np.log(area) + x @ beta))


def solve(objective: Objective, dimension: int, lam: float) -> dict[str, Any]:
    zero = np.zeros(dimension)
    initial = float(objective(zero)[0])
    attempts = []
    theta = zero
    for method in ("L-BFGS-B", "BFGS"):
        if dimension:
            options = {"maxiter": 600, "gtol": 1e-9}
            if method == "L-BFGS-B":
                options.update(ftol=1e-13, maxls=50)
            result = minimize(objective, theta, jac=True, method=method, options=options)
            theta = np.asarray(result.x)
            success, iterations, message = (
                bool(result.success),
                int(result.nit),
                str(result.message),
            )
        else:
            success, iterations, message = True, 0, "ZERO_ACTIVE_COEFFICIENTS"
        value, gradient = objective(theta)
        finite = math.isfinite(value) and np.isfinite(gradient).all() and np.isfinite(theta).all()
        gap = float(gradient @ gradient) / (2 * lam) if finite else math.inf
        accepted = finite and gap <= GAP_TOL and value <= initial + 1e-12
        attempts.append(
            {
                "method": method,
                "solver_success": success,
                "iterations": iterations,
                "message": message,
                "objective": value,
                "gradient_norm": float(np.linalg.norm(gradient)),
                "gap_bound": gap,
                "accepted": bool(accepted),
            }
        )
        if accepted:
            break
        if not np.isfinite(theta).all():
            theta = zero
    return {
        "theta": theta.tolist(),
        "initial_objective": initial,
        "objective": float(value),
        "gap_bound": gap,
        "accepted": bool(accepted),
        "attempts": attempts,
    }


def cached_solve(
    objective: Objective, dimension: int, lam: float, arrays: list[np.ndarray], layer: str
) -> dict[str, Any]:
    h = hashlib.sha256(f"{layer}|{dimension}|{lam}".encode())
    for array in arrays:
        h.update(str(array.shape).encode())
        h.update(np.asarray(array, dtype="<f8").tobytes())
    key = h.hexdigest()
    hit = key in SOLVE_CACHE
    if not hit:
        SOLVE_CACHE[key] = solve(objective, dimension, lam)
    return {**SOLVE_CACHE[key], "cache_hit": hit, "numerical_fit_id": key}


def mass_index(values: list[float] | np.ndarray, q: float) -> int:
    v = np.asarray(values)
    return min(len(v) - 1, int(np.searchsorted(np.cumsum(v) / v.sum(), q, side="left")))


def context(
    samples: list[dict[str, Any]], weather: dict[str, list[float]], mix: dict[str, list[float]]
) -> dict[str, Any]:
    seasons = sorted({s["season"] for s in samples})
    history = []
    for s in samples:
        if s["total"] <= 0:
            continue
        p = np.asarray(s["quantities"]) / s["total"]
        offset = positions(s["dates"][:1], s["season"])[0]
        history.append(
            {
                "base_id": s["base_id"],
                "season": s["season"],
                "values": [
                    math.log(s["total"] / s["area"]),
                    float(offset + mass_index(p, 0.5)),
                    float(mass_index(p, 0.9) - mass_index(p, 0.1)),
                ],
            }
        )
    return {
        "history": history,
        "seasons": seasons,
        "weather": {k: v for k, v in weather.items() if k.split("|")[1] in seasons},
        "mix": {k: v for k, v in mix.items() if k.split("|")[1] in seasons},
    }


def raw_features(
    query: dict[str, Any], ctx: dict[str, Any], version: str, included: str | None = None
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    chosen = groups(version) if included is None else included
    base, season = query["base_id"], query["season"]
    history = sorted(
        [r for r in ctx["history"] if r["base_id"] == base and r["season"] < season],
        key=lambda r: r["season"],
    )
    weather = [(s, ctx["weather"].get(base + "|" + s)) for s in ctx["seasons"] if s < season]
    weather = [(s, v) for s, v in weather if v is not None]
    mix = [(s, ctx["mix"].get(base + "|" + s)) for s in ctx["seasons"] if s < season]
    mix = [(s, v) for s, v in mix if v is not None]
    features: list[float] = []
    lineage: list[dict[str, Any]] = []
    for group in chosen:
        if group == "H":
            values = (
                history[-1]["values"] + [float(len(history))] if history else [np.nan] * 3 + [0.0]
            )
            source = [r["season"] for r in history]
            missing = not history
        elif group == "W":
            values = np.mean([v for _, v in weather], axis=0).tolist() if weather else [np.nan] * 4
            source = [s for s, _ in weather]
            missing = not weather
        else:
            values = mix[-1][1] if mix else [np.nan] * 4
            source = [mix[-1][0]] if mix else []
            missing = not mix
        values = list(values) + [float(missing)]
        features.extend(values)
        lineage.extend(
            {
                "base_id": base,
                "season": season,
                "group": group,
                "feature": name,
                "source_seasons": ";".join(source),
                "missing": missing,
                "source_role": "STRICTLY_EARLIER_IN_CURRENT_FIT_POOL",
            }
            for name in GROUP_NAMES[group]
        )
    return np.asarray(features, dtype=float), lineage


def fit_transform(raw: np.ndarray) -> dict[str, Any]:
    means = [float(np.mean(c[np.isfinite(c)])) if np.isfinite(c).any() else 0.0 for c in raw.T]
    filled = np.where(np.isfinite(raw), raw, np.asarray(means))
    sd = np.std(filled, axis=0)
    active = np.flatnonzero(sd > 1e-12).tolist()
    return {"means": means, "sd": sd.tolist(), "active": active}


def transform(raw: np.ndarray, state: dict[str, Any]) -> np.ndarray:
    means = np.asarray(state["means"])
    filled = np.where(np.isfinite(raw), raw, means)
    active = state["active"]
    return np.asarray((filled[:, active] - means[active]) / np.asarray(state["sd"])[active])


def quantities(total: float, p: np.ndarray) -> list[float]:
    if not math.isfinite(total) or total < 0 or not np.isfinite(p).all() or np.any(p < 0):
        raise ValueError("INVALID_PREDICTED_QUANTITY")
    amount = Decimal(str(total))
    values = [(amount * Decimal(str(v))).quantize(Decimal(".000001")) for v in p]
    values[-1] += amount.quantize(Decimal(".000001")) - sum(values)
    if any(v < 0 for v in values):
        raise ValueError("NEGATIVE_ROUNDING_RESIDUAL")
    return [float(v) for v in values]


def curve_stats(values: list[float] | np.ndarray) -> dict[str, Any]:
    a = np.asarray(values)
    if len(a) < 7:
        raise ValueError("COMPLETE_SEVEN_DAYS_REQUIRED")
    windows = np.convolve(a, np.ones(7), mode="valid")
    pi, wi = int(np.argmax(a)), int(np.argmax(windows))
    return {
        "total": math.fsum(a),
        "peak_index": pi,
        "peak_value": float(a[pi]),
        "peak7_index": wi,
        "peak7_value": float(windows[wi]),
        "peak_ties": int((a == a.max()).sum()),
        "peak7_ties": int((windows == windows.max()).sum()),
    }


def artifact_hash(model: dict[str, Any]) -> str:
    body = {k: v for k, v in model.items() if k != "artifact_hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, allow_nan=False).encode()).hexdigest()


def prepare(
    samples: list[dict[str, Any]],
    weather: dict[str, list[float]],
    mix: dict[str, list[float]],
    version: str,
    included: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not samples or len({(s["base_id"], s["season"]) for s in samples}) != len(samples):
        raise ValueError("INVALID_TRAINING_IDENTITY")
    for s in samples:
        values = np.asarray(s["quantities"])
        days = [date.fromisoformat(d) for d in s["dates"]]
        if (
            not math.isfinite(s["area"])
            or s["area"] <= 0
            or not days
            or len(days) != len(values)
            or not np.isfinite(values).all()
            or np.any(values < 0)
            or not math.isfinite(s["total"])
            or abs(math.fsum(values) - s["total"]) > 1e-6
            or any((b - a).days != 1 for a, b in zip(days, days[1:], strict=False))
        ):
            raise ValueError("INVALID_FROZEN_TRAINING_VALUES")
    ctx = context(samples, weather, mix)
    chosen = groups(version) if version != "M0" else ""
    chosen = chosen if included is None else included
    raw, lineage = [], []
    for s in samples:
        row, sources = raw_features(s, ctx, version, chosen)
        raw.append(row)
        lineage.extend(sources)
    values = np.array(raw).reshape(len(samples), len(chosen) * 5)
    state = fit_transform(values)
    return {
        "context": ctx,
        "transform": state,
        "included_groups": chosen,
        "x": transform(values, state),
        "raw": values,
    }, lineage


def fit_model(
    samples: list[dict[str, Any]],
    weather: dict[str, list[float]],
    mix: dict[str, list[float]],
    shape: dict[str, Any],
    total: dict[str, Any],
    m0_density: list[float],
    contract_hash: str,
    role: str = "DIAGNOSTIC_ONLY",
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    prepared, lineage = prepare(samples, weather, mix, shape["version"], shape.get("included"))
    x = prepared["x"]
    audits = []
    fitted_shape = dict(shape)
    if shape["version"] != "M0":
        valid = [i for i, s in enumerate(samples) if s["total"] > 0]
        bases = [
            basis(positions(samples[i]["dates"], samples[i]["season"]), shape["basis"])
            for i in valid
        ]
        targets = [np.asarray(samples[i]["quantities"]) / samples[i]["total"] for i in valid]
        objective = shape_objective(bases, x[valid], targets, shape["lambda"])
        fitted = cached_solve(
            objective,
            (x.shape[1] + 1) * (shape["basis"] - 1),
            shape["lambda"],
            [x[valid], *bases, *targets],
            "SHAPE",
        )
        audits.append({"layer": "SHAPE", **fitted})
        if not fitted["accepted"]:
            raise ValueError("SHAPE_NUMERICAL_UNVERIFIED")
        fitted_shape["theta"] = fitted["theta"]
    fitted_total = dict(total)
    area = np.array([s["area"] for s in samples])
    q = np.array([s["total"] for s in samples])
    if q.sum() <= 0:
        raise ValueError("TOTAL_ALL_ZERO_UNAVAILABLE")
    if total["version"] == "TY1":
        fitted = cached_solve(
            total_objective(x, area, q, total["lambda"]),
            x.shape[1],
            total["lambda"],
            [x, area, q],
            "TOTAL",
        )
        audits.append({"layer": "TOTAL", **fitted})
        if not fitted["accepted"]:
            raise ValueError("TOTAL_NUMERICAL_UNVERIFIED")
        fitted_total.update(
            beta=fitted["theta"],
            alpha=total_intercept(np.asarray(fitted["theta"]), x, area, q),
            training_loss_scale=float(q.sum()),
            raw_profile_constant=float(1 - np.log(q.sum())),
        )
    model = {
        "schema": "CONDITIONAL_GROWTH_RESEARCH_R1",
        "role": role,
        "contract_hash": contract_hash,
        "shape": fitted_shape,
        "total": fitted_total,
        "context": prepared["context"],
        "transform": prepared["transform"],
        "included_groups": prepared["included_groups"],
        "m0_density": m0_density,
        "pooled_yield": sum(s["total"] for s in samples) / sum(s["area"] for s in samples),
        "training_count": len(samples),
        "training_cutoff": max(d for s in samples for d in s["dates"]),
        "active_feature_names": [
            name
            for j, name in enumerate(
                [n for g in prepared["included_groups"] for n in GROUP_NAMES[g]]
            )
            if j in prepared["transform"]["active"]
        ],
    }
    model["artifact_hash"] = artifact_hash(model)
    return model, audits, lineage


def forecast(
    model: dict[str, Any], request: dict[str, Any], *, group_cv: bool = False
) -> dict[str, Any]:
    if model["artifact_hash"] != artifact_hash(model):
        raise ValueError("MODEL_HASH_INTEGRITY")
    year = int(request["target_season"][:4])
    start, end = (
        date.fromisoformat(request[k]) for k in ("forecast_start_date", "forecast_end_date")
    )
    area = float(request["target_area_mu"])
    if (
        not math.isfinite(area)
        or area <= 0
        or end < start
        or start < date(year, 7, 1)
        or end > date(year + 1, 4, 15)
        or (end - start).days < 6
        or (not group_cv and start <= date.fromisoformat(model["training_cutoff"]))
    ):
        raise ValueError("INVALID_FORECAST_REQUEST")
    dates = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    pos = positions(dates, request["target_season"])
    query = {"base_id": request["base_id"], "season": request["target_season"]}
    raw, provenance = raw_features(
        query, model["context"], model["shape"]["version"], model["included_groups"]
    )
    x = transform(raw.reshape(1, -1), model["transform"])[0]
    if model["shape"]["version"] == "M0":
        p = np.asarray(model["m0_density"])[pos]
        p = p / p.sum()
        p[-1] += 1 - float(p.sum())
    else:
        p = shape_predict(model["shape"]["theta"], basis(pos, model["shape"]["basis"]), x)
    total = (
        area * model["pooled_yield"]
        if model["total"]["version"] == "TY0"
        else (
            area * math.exp(model["total"]["alpha"] + float(x @ np.asarray(model["total"]["beta"])))
        )
    )
    kg = quantities(total, p)
    stats = curve_stats(kg)
    return {
        "base_id": request["base_id"],
        "season": request["target_season"],
        "dates": dates,
        "area": area,
        "shares": p.tolist(),
        "quantities": kg,
        "total": total,
        "single_day_peak": {"date": dates[stats["peak_index"]], "quantity_kg": stats["peak_value"]},
        "rolling_7day_peak": {
            "start_date": dates[stats["peak7_index"]],
            "end_date": dates[stats["peak7_index"] + 6],
            "quantity_kg": stats["peak7_value"],
        },
        "boundary_warning": stats["peak_index"] in (0, len(kg) - 1),
        "feature_provenance": provenance,
        "transformed_features": x.tolist(),
        "MODEL_ROLE": model["role"],
        "PRODUCTION_ACCURACY_APPROVED": False,
    }
