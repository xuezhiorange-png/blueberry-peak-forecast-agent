"""One locked area-size regression; no weather, label lookup or model search.

Season total means the existing July 1--April 15 business window, never the
untruncated natural season. Both models learn their common shape from train only.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from backend.app.area_yield.data import digest
from backend.app.area_yield.v08_s8_training_backtest import derive_peaks, validate_curve

QUANTUM = Decimal("0.000001")


def number(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except ArithmeticError as exc:
        raise ValueError("missing/invalid quantity") from exc
    if not result.is_finite() or result < 0 or result != result.quantize(QUANTUM):
        raise ValueError("nonfinite, negative or excess-precision quantity")
    return result


def audit(rows: list[dict[str, str]], daily: list[dict[str, str]]) -> dict[str, Any]:
    """Fail closed on a mismatched season/Base, missing area or missing day."""
    lookup = {(r["base_id"], r["season"]): r for r in rows}
    if not rows or len(lookup) != len(rows):
        raise ValueError("empty or duplicate Base-season")
    curves: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["season"] not in {"2023-2024", "2024-2025"}:
            raise ValueError("forbidden source season")
        if number(row["area_mu"]) <= 0:
            raise ValueError("nonpositive historical area")
        if (
            row.get("strict_training_eligible") != "true"
            or row.get("daily_curve_available") != "true"
        ):
            raise ValueError("ineligible historical sample")
        if any(
            not row.get(key)
            for key in ("area_authority_id", "quantity_authority_id", "identity_authority_id")
        ):
            raise ValueError("unproven authority")
    for row in daily:
        key = row["base_id"], row["season"]
        if key not in lookup:
            raise ValueError("unmatched historical area/season identity")
        number(row["new_quantity_kg"])
        curves[key].append(row)
    for key, row in lookup.items():
        validate_curve(
            sorted(curves[key], key=lambda r: r["date"]),
            season=key[1],
            expected_total=number(row["season_total_quantity_kg"]),
        )
    return {
        "SEASON_COUNT": len({r["season"] for r in rows}),
        "FARM_OR_BASE_COUNT": len({r["base_id"] for r in rows}),
        "TOTAL_HARVEST_ROWS": len(daily),
        "ROW_GRAIN": "CANONICAL_BASE_SEASON_DAY_NOT_RAW_RECEIPT_ROW",
        "AREA_MATCHED_ROWS": len(daily),
        "AREA_UNMATCHED_ROWS": 0,
        "VALID_TRAINING_SAMPLE_COUNT": len(rows),
        "ZERO_QUANTITY_ROW_COUNT": sum(number(r["new_quantity_kg"]) == 0 for r in daily),
        "AUTHORIZED_ZERO_ROW_COUNT": sum(
            r["new_completeness_status"] == "AUTHORIZED_ZERO" for r in daily
        ),
        "MISSING_QUANTITY_ROW_COUNT": 0,
        "AREA_MATCHED_SAMPLE_COUNT": len(rows),
        "AREA_UNMATCHED_SAMPLE_COUNT": 0,
        "scope": "only supplied eligible nonsealed training-pool files; not all raw business data",
        "historical_pit_availability": "NOT_PROVEN",
    }


def fit(
    rows: list[dict[str, str]],
    daily: list[dict[str, str]],
    *,
    kind: str,
    identity: dict[str, Any],
    created_at: str,
) -> dict[str, Any]:
    if kind not in {"baseline", "candidate"} or any(r["season"] != "2023-2024" for r in rows):
        raise ValueError("locked training season or model family invalid")
    audit(rows, daily)
    rows = sorted(rows, key=lambda r: (r["season"], r["base_id"]))
    areas = [number(r["area_mu"]) for r in rows]
    totals = [number(r["season_total_quantity_kg"]) for r in rows]
    if any(q <= 0 for q in totals):
        raise ValueError("zero season total cannot define log yield/normalized shape")
    xs = [math.log(float(a)) for a in areas]
    ys = [math.log(float(q / a)) for q, a in zip(totals, areas, strict=True)]
    x_mean, y_mean = math.fsum(xs) / len(xs), math.fsum(ys) / len(ys)
    beta = math.fsum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True)) / (
        math.fsum((x - x_mean) ** 2 for x in xs) + 1.0
    )
    q_lookup = {(r["base_id"], r["season"]): number(r["season_total_quantity_kg"]) for r in rows}
    profile: dict[str, list[float]] = defaultdict(list)
    for row in sorted(daily, key=lambda r: (r["season"], r["base_id"], r["date"])):
        profile[row["date"][5:]].append(
            float(number(row["new_quantity_kg"]) / q_lookup[(row["base_id"], row["season"])])
        )
    model = {
        "model_id": f"NEXT_AREA_SIZE_20261002_R1_{kind.upper()}",
        "model_family": kind,
        "model_version": "1",
        "model_role": "RESEARCH_CANDIDATE",
        "created_at": created_at,
        "training_identity": identity,
        "training_seasons": ["2023-2024"],
        "training_sample_count": len(rows),
        "training_area_range_mu": [str(min(areas)), str(max(areas))],
        "training_bases": sorted({r["base_id"] for r in rows}),
        "parameters": {
            "pooled_yield": str(sum(totals) / sum(areas)),
            "mean_log_area": x_mean,
            "alpha": y_mean,
            "beta": beta,
            "penalty": 1.0,
        },
        "curve_parameters": {
            day: math.fsum(values) / len(values) for day, values in sorted(profile.items())
        },
        "target_definition": "JULY01_APRIL15_BUSINESS_WINDOW_TOTAL_NOT_NATURAL_FULL_SEASON",
        "quantity_precision": "0.000001kg_HALF_EVEN",
        "features": ["log_area_mu"] if kind == "candidate" else [],
        "weather_used": False,
        "holdout_used_for_fit": False,
    }
    model["artifact_hash"] = digest(model)
    return model


def predict(
    model: dict[str, Any],
    area_mu: str,
    season_start_year: int,
    base_id: str,
    *,
    area_unit: str = "mu",
) -> dict[str, Any]:
    payload = dict(model)
    if payload.pop("artifact_hash", None) != digest(payload):
        raise ValueError("artifact hash mismatch")
    if area_unit != "mu":
        raise ValueError("area unit must be mu")
    area = number(area_mu)
    if area <= 0:
        raise ValueError("area must be positive")
    if type(season_start_year) is not int or not 2024 <= season_start_year <= 9998:
        raise ValueError("target season must follow training season")
    parameters = model["parameters"]
    if model["model_family"] == "baseline":
        yield_value = Decimal(parameters["pooled_yield"])
    elif model["model_family"] == "candidate":
        try:
            yield_value = Decimal(
                str(
                    math.exp(
                        parameters["alpha"]
                        + parameters["beta"] * (math.log(float(area)) - parameters["mean_log_area"])
                    )
                )
            )
        except (OverflowError, ValueError) as exc:
            raise ValueError("unsupported numerical area extrapolation") from exc
    else:
        raise ValueError("unsupported model family")
    total = (area * yield_value).quantize(QUANTUM, rounding=ROUND_HALF_EVEN)
    start, end = date(season_start_year, 7, 1), date(season_start_year + 1, 4, 15)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    profile = model["curve_parameters"]
    if any(d.strftime("%m-%d") not in profile for d in days):
        raise ValueError("calendar date unsupported; no missing-day imputation")
    shares = [Decimal(str(profile[d.strftime("%m-%d")])) for d in days]
    mass = sum(shares)
    if mass <= 0:
        raise ValueError("no shape mass")
    quantities = [
        (total * share / mass).quantize(QUANTUM, rounding=ROUND_HALF_EVEN) for share in shares
    ]
    pivot = shares.index(max(shares))
    quantities[pivot] += total - sum(quantities)
    if any(q < 0 for q in quantities) or sum(quantities) != total:
        raise ValueError("quantity conservation failed")
    daily = [
        {"date": d.isoformat(), "predicted_daily_quantity_kg": str(q)}
        for d, q in zip(days, quantities, strict=True)
    ]
    low, high = map(Decimal, model["training_area_range_mu"])
    warnings = [
        "RESEARCH_ONLY",
        "NOT_FULL_NATURAL_SEASON",
        "ONE_REUSED_FORWARD_SEASON_NOT_UNSEEN_VALIDATION",
        "LINEAR_BASELINE_AREA_SCALING_NOT_BUSINESS_VALIDATED",
    ]
    if not low <= area <= high:
        warnings.append("AREA_EXTRAPOLATION_NOT_VALIDATED")
    if base_id not in model["training_bases"]:
        warnings.append("BASE_OUTSIDE_TRAINING_COVERAGE")
    result = {
        "target_area_mu": str(area),
        "target_season": f"{season_start_year}-{season_start_year + 1}",
        "base_id": base_id,
        "predicted_season_total_kg": str(total),
        "daily_curve": daily,
        "peaks": derive_peaks(daily),
        "model_id": model["model_id"],
        "artifact_hash": model["artifact_hash"],
        "area_position": "INTERPOLATION" if low <= area <= high else "EXTRAPOLATION",
        "training_area_range_mu": model["training_area_range_mu"],
        "mode": "TEST_ONLY",
        "applicability_notes": warnings,
        "production_use_approved": False,
        "prospective_accuracy_validated": False,
    }
    result["result_hash"] = digest(result)
    return result
