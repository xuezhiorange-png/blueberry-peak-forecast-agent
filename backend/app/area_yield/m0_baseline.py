"""Thin persistence/inference boundary for the existing corrected Task8 M0.

The integer-axis shared density is a learned model representation, not a
Base-indexed prediction table. Training delegates to the existing M0 fit.
"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.area_yield.base_product import AreaForecastProductRequest
from backend.app.area_yield.data import calendar, digest
from backend.app.area_yield.evaluation import summaries
from backend.app.area_yield.m0_frozen_kernels import _daily_quantities, _fit_shared_shape
from backend.app.area_yield.v0_10_mechanism_informed_model import normalize_nonnegative
from backend.app.area_yield.v0_10_model_simplification import fit_total_t0, predict_yield

MODEL_ID = "M0_CORRECTED_TASK8_SHARED_SPLINE"
SCHEMA = "M0_RESEARCH_BASELINE_ARTIFACT_R1"


def seal_model(model: dict[str, Any]) -> dict[str, Any]:
    result = {k: v for k, v in model.items() if k != "artifact_hash"}
    return {**result, "artifact_hash": digest(result)}


def validate_model(model: dict[str, Any]) -> None:
    if digest({k: v for k, v in model.items() if k != "artifact_hash"}) != model.get(
        "artifact_hash"
    ):
        raise ValueError("M0_ARTIFACT_INTEGRITY")
    if model.get("schema") != SCHEMA or model.get("model_id") != MODEL_ID:
        raise ValueError("M0_ARTIFACT_SCHEMA")
    shape = model["shared_shape"]
    if (
        len(shape) != model["support_days"]
        or not shape
        or any(not math.isfinite(float(v)) or float(v) < 0 for v in shape)
        or abs(sum(shape) - 1) > 1e-12
    ):
        raise ValueError("M0_ARTIFACT_SHAPE_INVALID")
    yield_value = float(model["pooled_yield_kg_per_mu"])
    if not math.isfinite(yield_value) or yield_value < 0:
        raise ValueError("M0_ARTIFACT_TOTAL_INVALID")
    if model["config"] != frozen_config():
        raise ValueError("M0_FROZEN_CONFIG_MISMATCH")


def frozen_config() -> dict[str, Any]:
    return {
        "total": "TOTAL_T0_AREA_WEIGHTED_MEAN_YIELD",
        "canonical_axis": "JULY_01_INTEGER_DAY",
        "support_days": 290,
        "spline_degree": 3,
        "spline_knots": 6,
        "ridge_alpha": 0.10,
        "include_bias": False,
        "fit_intercept": True,
        "extrapolation": "constant",
        "random_state": 0,
        "sample_weighting": "TASK8_OFFICIAL_EQUAL_DAILY_ROW",
        "boundary_variant": "B2_LOCAL_EMPIRICAL_TAIL_DERIVATIVE",
        "normalization": "EXISTING_TASK8_AND_CORRECTED_SIX_DECIMAL_CONTRACT",
        "quantity_serialization": "EXISTING_MICRO_KG_LAST_DAY_RESIDUAL",
        "support_extension": False,
    }


def fit(
    samples: list[dict[str, Any]], *, training_input_sha256: str, training_manifest_sha256: str
) -> dict[str, Any]:
    if not samples or len({s["group_id"] for s in samples}) != len(samples):
        raise ValueError("M0_INVALID_TRAINING_IDENTITY")
    for s in samples:
        area = float(s["area"])
        quantities = s["quantities"]
        dates = s["dates"]
        if (
            not math.isfinite(area)
            or area <= 0
            or len(dates) != len(quantities)
            or not dates
            or any(not math.isfinite(v) or v < 0 for v in quantities)
            or abs(math.fsum(quantities) - float(s["total"])) > 1e-6
            or dates != list(calendar(dates[0], dates[-1]))
        ):
            raise ValueError("M0_INVALID_TRAINING_VALUES")
    total_model = fit_total_t0(samples)
    shape, details = _fit_shared_shape(samples)
    return seal_model(
        {
            "schema": SCHEMA,
            "model_id": MODEL_ID,
            "model_role": "RESEARCH_BASELINE",
            "config": frozen_config(),
            "support_days": len(shape),
            "shared_shape": list(shape),
            "pooled_yield_kg_per_mu": predict_yield(total_model),
            "shape_fit_details": details,
            "training_base_season_count": len(samples),
            "training_group_ids": [s["group_id"] for s in samples],
            "training_seasons": sorted({s["season"] for s in samples}),
            "training_cutoff": max(d for s in samples for d in s["dates"]).isoformat(),
            "training_input_sha256": training_input_sha256,
            "training_manifest_sha256": training_manifest_sha256,
            "request_schema": "AreaForecastProductRequest",
            "point_only": True,
            "probability_calibration_established": False,
        }
    )


def save_model(path: Path, model: dict[str, Any]) -> None:
    import json

    validate_model(model)
    payload = (
        json.dumps(model, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    ).encode()
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("M0_REFUSE_OVERWRITE_EXISTING_ARTIFACT")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)


def load_model(path: Path) -> dict[str, Any]:
    import json

    model: dict[str, Any] = json.loads(path.read_text())
    validate_model(model)
    return model


def predict(model: dict[str, Any], request: AreaForecastProductRequest) -> dict[str, Any]:
    validate_model(model)
    year = int(request.target_season[:4])
    if year <= max(int(s[:4]) for s in model["training_seasons"]):
        raise ValueError("M0_PREDICTION_TRAINING_SEASON_OVERLAP")
    if request.forecast_start_date is None or request.forecast_end_date is None:
        raise ValueError("M0_EXPLICIT_AUTHORIZED_WINDOW_REQUIRED")
    start, end = request.forecast_start_date, request.forecast_end_date
    if start < date(year, 7, 1) or end > date(year + 1, 4, 15) or end < start:
        raise ValueError("M0_INVALID_FROZEN_SEASON_WINDOW")
    dates = calendar(start, end)
    if len(dates) < 7 or start <= date.fromisoformat(model["training_cutoff"]):
        raise ValueError("M0_INVALID_OR_TRAINING_OVERLAPPING_DATES")
    origin = date(year, 7, 1)
    positions = [(d - origin).days for d in dates]
    if max(positions) >= model["support_days"]:
        raise ValueError("M0_WINDOW_OUTSIDE_TRAINED_CANONICAL_SUPPORT")
    raw = [model["shared_shape"][i] for i in positions]
    if sum(raw) <= 0:
        raise ValueError("M0_ZERO_WINDOW_MASS")
    share = normalize_nonnegative(raw)
    total = float(request.target_area_mu) * float(model["pooled_yield_kg_per_mu"])
    if not math.isfinite(total):
        raise ValueError("M0_AREA_SCALING_OVERFLOW")
    values = [Decimal(str(v)) for v in _daily_quantities(total, share)]
    if any(v < 0 or not v.is_finite() for v in values):
        raise ValueError("M0_INVALID_DAILY_QUANTITIES")
    metric = summaries(dates, values)
    peak = metric["single_day_peak"]
    warnings = []
    if peak["date"] in {start.isoformat(), end.isoformat()}:
        warnings.append("SINGLE_PEAK_AT_OUTPUT_BOUNDARY")
    if metric["rolling_7day_peak"]["start_date"] == start.isoformat() or (
        metric["rolling_7day_peak"]["end_date"] == end.isoformat()
    ):
        warnings.append("ROLLING_7DAY_PEAK_TOUCHES_OUTPUT_BOUNDARY")
    return {
        "model_id": MODEL_ID,
        "artifact_hash": model["artifact_hash"],
        "base_id": request.base_id,
        "target_season": request.target_season,
        "target_area_mu": request.target_area_mu,
        "forecast_start_date": start.isoformat(),
        "forecast_end_date": end.isoformat(),
        "predicted_total_before_kg_rounding": total,
        "predicted_window_total_kg": metric["total_kg"],
        "daily_curve": [
            {"date": d.isoformat(), "predicted_quantity_kg": str(v), "normalized_share": p}
            for d, v, p in zip(dates, values, share, strict=True)
        ],
        "single_day_peak": peak,
        "rolling_7day_peak": metric["rolling_7day_peak"],
        "warnings": warnings,
        "metadata": {
            "MODEL_ROLE": "RESEARCH_BASELINE",
            "PRODUCTION_ACCURACY_APPROVED": False,
            "PROBABILITY_CALIBRATION_ESTABLISHED": False,
            "BASE_SPECIFIC_TIMING_MODE": "SHARED",
            "ACTUAL_MODEL_INPUTS_USED": [
                "target_area_mu",
                "target_season",
                "forecast_start_date",
                "forecast_end_date",
            ],
            "ACCEPTED_BUT_UNUSED_INPUTS": ["base_id", "base_name", "forecast_mode"],
            "unused_input_note": "Identifiers/mode do not enter numerical predictors",
            "weather_and_cultivar_fields": "Not accepted by request schema; not used by M0",
            "label_assumption": "ARRIVAL_EQUALS_HARVEST_EQUALS_MATURITY_PROXY",
            "total_target_definition": "CONDITIONAL_FROZEN_OUTPUT_WINDOW_TOTAL",
            "training_cutoff": model["training_cutoff"],
        },
    }
