"""Low-degree total-yield and harvest-timing components for V0.10 R3.

Season-total prediction and within-season timing are independent fits. The
total layer cannot see daily curve targets; the timing layer consumes
normalized curves and cannot change a season-total prediction.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from backend.app.area_yield.v0_10_mechanism_informed_model import (
    MechanismModelError,
    RidgeFit,
    fit_logistic_calendar_proxy,
    fit_ridge,
    logistic_calendar_shape,
    normalize_nonnegative,
)

TOTAL_WEATHER_FEATURES = {
    "WG1_TEMPERATURE": "season_mean_temperature_c",
    "WG2_PRECIPITATION": "season_precipitation_total_mm",
    "WG3_RADIATION": "season_mean_solar_mj_m2",
}
TIMING_WEATHER_FEATURES = {
    "WG1_TEMPERATURE": "season_mean_temperature_c",
    "WG2_PRECIPITATION": "season_precipitation_total_mm",
    "WG3_RADIATION": "season_mean_solar_mj_m2",
    "WG4_WIND": "season_mean_wind_speed_m_s",
    "WG5_SHORT_WINDOW": "w7_mean_temperature_c",
    "WG6_MEDIUM_WINDOW": "w14_mean_temperature_c",
}
TIMING_WEATHER_ORDER = tuple(TIMING_WEATHER_FEATURES)
RIDGE_ALPHA_TOTAL_R3 = 20.0
RIDGE_ALPHA_TIMING_R3 = 20.0
TIMING_MATERIAL_WORSENING_RELATIVE = 0.05
TIMING_SCORE_WEIGHTS = {
    "daily_wape": 0.50,
    "single_day_peak_timing_mae_days": 0.25,
    "rolling7_peak_timing_mae_days": 0.25,
}


class SimplificationError(ValueError):
    """Raised when grouped-fold inputs or layer contracts are invalid."""


@dataclass(frozen=True, slots=True)
class TotalFit:
    model_id: str
    pooled_yield_kg_per_mu: float | None
    feature_names: tuple[str, ...]
    ridge: RidgeFit | None

    @property
    def free_parameter_count(self) -> int:
        if self.ridge is None:
            return 1
        return 1 + len(self.ridge.feature_names)

    def payload(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "pooled_yield_kg_per_mu": self.pooled_yield_kg_per_mu,
            "feature_names": list(self.feature_names),
            "ridge": self.ridge.payload() if self.ridge is not None else None,
            "free_parameter_count": self.free_parameter_count,
        }


@dataclass(frozen=True, slots=True)
class TimingFit:
    model_id: str
    median_day: float
    scale_days: float
    weather_features: tuple[str, ...] = ()
    weather_shift: RidgeFit | None = None
    pooled_shape: tuple[float, ...] | None = None

    @property
    def free_parameter_count(self) -> int:
        if self.pooled_shape is not None:
            return 6
        return 2 + (len(self.weather_features) if self.weather_shift is not None else 0)

    def payload(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "median_day": format(self.median_day, ".17g"),
            "scale_days": format(self.scale_days, ".17g"),
            "weather_features": list(self.weather_features),
            "weather_shift": self.weather_shift.payload() if self.weather_shift else None,
            "pooled_shape": (
                [format(value, ".17g") for value in self.pooled_shape]
                if self.pooled_shape is not None
                else None
            ),
            "free_parameter_count": self.free_parameter_count,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> TimingFit:
        try:
            weather_shift_payload = payload.get("weather_shift")
            weather_shift = (
                RidgeFit.from_payload(weather_shift_payload)
                if isinstance(weather_shift_payload, Mapping)
                else None
            )
            shape_payload = payload.get("pooled_shape")
            pooled_shape = (
                tuple(float(value) for value in shape_payload)
                if isinstance(shape_payload, Sequence)
                and not isinstance(shape_payload, (str, bytes))
                else None
            )
            result = cls(
                model_id=str(payload["model_id"]),
                median_day=float(payload["median_day"]),
                scale_days=float(payload["scale_days"]),
                weather_features=tuple(str(value) for value in payload.get("weather_features", ())),
                weather_shift=weather_shift,
                pooled_shape=pooled_shape,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SimplificationError("TIMING_ARTIFACT_SCHEMA_INVALID") from exc
        numeric_values = (result.median_day, result.scale_days)
        if (
            not result.model_id
            or result.scale_days <= 0
            or not all(math.isfinite(value) for value in numeric_values)
            or (
                result.weather_shift is not None
                and result.weather_shift.feature_names != result.weather_features
            )
            or (
                result.pooled_shape is not None
                and (
                    not result.pooled_shape
                    or any(not math.isfinite(value) or value < 0 for value in result.pooled_shape)
                    or sum(result.pooled_shape) <= 0
                )
            )
        ):
            raise SimplificationError("TIMING_ARTIFACT_SCHEMA_INVALID")
        return result


def normalized_shares(values: Sequence[float]) -> tuple[float, ...]:
    if not values or any(not math.isfinite(float(value)) or float(value) < 0 for value in values):
        raise SimplificationError("DAILY_TARGET_CURVE_INVALID")
    total = sum(float(value) for value in values)
    if total <= 0:
        raise SimplificationError("DAILY_TARGET_CURVE_EMPTY")
    return normalize_nonnegative([float(value) / total for value in values])


def curve_median_day(shares: Sequence[float]) -> float:
    cumulative = 0.0
    for index, share in enumerate(shares):
        cumulative += float(share)
        if cumulative >= 0.5:
            return float(index)
    return float(len(shares) - 1)


def fit_total_t0(records: Sequence[Mapping[str, Any]]) -> TotalFit:
    """Fit area-weighted historical mean yield, with no timing features."""

    if not records:
        raise SimplificationError("TOTAL_T0_EMPTY_TRAINING_SET")
    area = sum(float(row["area"]) for row in records)
    quantity = sum(float(row["total"]) for row in records)
    if area <= 0 or quantity < 0:
        raise SimplificationError("TOTAL_T0_TRAINING_VALUES_INVALID")
    return TotalFit(
        model_id="TOTAL_T0_AREA_WEIGHTED_MEAN_YIELD",
        pooled_yield_kg_per_mu=quantity / area,
        feature_names=(),
        ridge=None,
    )


def fit_total_weather(
    records: Sequence[Mapping[str, Any]],
    feature_rows: Sequence[Mapping[str, float]],
    feature_names: Sequence[str],
) -> TotalFit:
    """Fit a small log-yield ridge; caller caps this layer at three features."""

    if len(feature_names) > 3:
        raise SimplificationError("TOTAL_MODEL_FEATURE_CAP_EXCEEDED")
    if len(records) != len(feature_rows) or not records or not feature_names:
        raise SimplificationError("TOTAL_T2_TRAINING_SHAPE_INVALID")
    if any(float(row["yield_value"]) <= 0 for row in records):
        raise SimplificationError("TOTAL_T2_NONPOSITIVE_YIELD")
    ridge = fit_ridge(
        feature_rows,
        [math.log(float(row["yield_value"])) for row in records],
        feature_names=feature_names,
        alpha=RIDGE_ALPHA_TOTAL_R3,
    )
    return TotalFit(
        model_id="TOTAL_T2_TRAINING_ONLY_CLIMATE_RIDGE",
        pooled_yield_kg_per_mu=None,
        feature_names=tuple(feature_names),
        ridge=ridge,
    )


def predict_yield(fit: TotalFit, features: Mapping[str, float] | None = None) -> float:
    if fit.ridge is None:
        if fit.pooled_yield_kg_per_mu is None:
            raise SimplificationError("TOTAL_T0_ARTIFACT_INVALID")
        return fit.pooled_yield_kg_per_mu
    if features is None:
        raise SimplificationError("TOTAL_MODEL_FEATURES_REQUIRED")
    value = math.exp(fit.ridge.predict(features))
    if not math.isfinite(value) or value < 0:
        raise SimplificationError("TOTAL_MODEL_PREDICTION_INVALID")
    return value


def fit_timing_s1(curves: Sequence[Sequence[float]]) -> TimingFit:
    """Fit a two-parameter smooth logistic timing proxy from training curves."""

    indexed = [
        [(index, float(share)) for index, share in enumerate(normalized_shares(curve))]
        for curve in curves
    ]
    median, scale = fit_logistic_calendar_proxy(indexed)
    return TimingFit(
        model_id="TIMING_S1_GLOBAL_LOGISTIC",
        median_day=median,
        scale_days=scale,
    )


def fit_timing_weather(
    curves: Sequence[Sequence[float]],
    weather_feature_rows: Sequence[Mapping[str, float]],
    *,
    feature_names: Sequence[str],
    model_id: str,
) -> TimingFit:
    """Fit one weather group as a regularized shift of the S1 median only."""

    if len(curves) != len(weather_feature_rows) or not curves or not feature_names:
        raise SimplificationError("TIMING_WEATHER_TRAINING_SHAPE_INVALID")
    base = fit_timing_s1(curves)
    residuals = [curve_median_day(normalized_shares(curve)) - base.median_day for curve in curves]
    ridge = fit_ridge(
        weather_feature_rows,
        residuals,
        feature_names=feature_names,
        alpha=RIDGE_ALPHA_TIMING_R3,
    )
    return TimingFit(
        model_id=model_id,
        median_day=base.median_day,
        scale_days=base.scale_days,
        weather_features=tuple(feature_names),
        weather_shift=ridge,
    )


def fit_timing_base_partial_pooling(
    curves_by_base: Mapping[str, Sequence[Sequence[float]]],
    *,
    shrinkage_strength: float = 2.0,
) -> tuple[TimingFit, dict[str, tuple[float, ...]]]:
    """Create shrunk Base-specific curves, retaining the global Task 8 spline."""

    all_curves = [curve for values in curves_by_base.values() for curve in values]
    if not all_curves or shrinkage_strength <= 0:
        raise SimplificationError("BASE_PARTIAL_POOLING_INPUT_INVALID")
    support = len(all_curves[0])
    if any(len(curve) != support for curve in all_curves):
        raise SimplificationError("BASE_PARTIAL_POOLING_SUPPORT_MISMATCH")
    global_curve = tuple(
        sum(normalized_shares(curve)[day] for curve in all_curves) / len(all_curves)
        for day in range(support)
    )
    global_curve = normalize_nonnegative(global_curve)
    pooled: dict[str, tuple[float, ...]] = {}
    for base_id, curves in curves_by_base.items():
        if not curves:
            continue
        base_curve = tuple(
            sum(normalized_shares(curve)[day] for curve in curves) / len(curves)
            for day in range(support)
        )
        weight = len(curves) / (len(curves) + shrinkage_strength)
        pooled[base_id] = normalize_nonnegative(
            [
                (1.0 - weight) * global_curve[day] + weight * base_curve[day]
                for day in range(support)
            ]
        )
    global_fit = fit_timing_s1(all_curves)
    med, scale = global_fit.median_day, global_fit.scale_days
    return (
        TimingFit(
            model_id="TIMING_BASE_PARTIAL_POOLING_SHRINKAGE_2",
            median_day=med,
            scale_days=scale,
            pooled_shape=global_curve,
        ),
        pooled,
    )


def predict_timing_shares(
    fit: TimingFit,
    support_length: int,
    *,
    weather_features: Mapping[str, float] | None = None,
    base_id: str | None = None,
    base_curves: Mapping[str, tuple[float, ...]] | None = None,
    support_offset: int = 0,
) -> tuple[float, ...]:
    if fit.pooled_shape is not None:
        source = (base_curves or {}).get(base_id or "", fit.pooled_shape)
        if support_offset < 0 or support_offset + support_length > len(source):
            raise SimplificationError("TIMING_POOLED_SHAPE_SUPPORT_INVALID")
        return normalize_nonnegative(source[support_offset : support_offset + support_length])
    median = fit.median_day
    if fit.weather_shift is not None:
        if not fit.weather_features or weather_features is None:
            raise SimplificationError("TIMING_WEATHER_FEATURES_REQUIRED")
        median += fit.weather_shift.predict(weather_features)
    offsets = tuple(range(support_offset, support_offset + support_length))
    return logistic_calendar_shape(offsets, median_day=median, scale_days=fit.scale_days)


def timing_score(metrics: Mapping[str, float]) -> float:
    span = float(metrics["support_days"])
    single_day_error = metrics.get(
        "single_day_peak_timing_mae_days",
        metrics.get("single_day_peak_timing_error_days"),
    )
    rolling7_error = metrics.get(
        "rolling7_peak_timing_mae_days",
        metrics.get("rolling7_peak_timing_error_days"),
    )
    if single_day_error is None or rolling7_error is None:
        raise SimplificationError("TIMING_SCORE_PEAK_METRIC_MISSING")
    return (
        TIMING_SCORE_WEIGHTS["daily_wape"] * float(metrics["daily_wape"])
        + TIMING_SCORE_WEIGHTS["single_day_peak_timing_mae_days"] * float(single_day_error) / span
        + TIMING_SCORE_WEIGHTS["rolling7_peak_timing_mae_days"] * float(rolling7_error) / span
    )


def fold_is_materially_worse(before: float, after: float) -> bool:
    return after > before * (1.0 + TIMING_MATERIAL_WORSENING_RELATIVE)


def season_dates(start: date, count: int) -> tuple[date, ...]:
    if count <= 0:
        raise SimplificationError("SEASON_SUPPORT_EMPTY")
    return tuple(start + timedelta(days=offset) for offset in range(count))


def ensure_finite_mapping(row: Mapping[str, Any], fields: Sequence[str]) -> dict[str, float]:
    result: dict[str, float] = {}
    for field in fields:
        try:
            value = float(row[field])
        except (KeyError, TypeError, ValueError) as exc:
            raise MechanismModelError(f"MODEL_FEATURE_INVALID:{field}") from exc
        if not math.isfinite(value):
            raise MechanismModelError(f"MODEL_FEATURE_INVALID:{field}")
        result[field] = value
    return result


def replay_model_artifact(
    artifact_bytes: bytes,
    *,
    prediction_area_mu: float,
    support_length: int,
    total_features: Mapping[str, float] | None = None,
    timing_features: Mapping[str, float] | None = None,
    support_offset: int = 0,
) -> dict[str, Any]:
    """Load the frozen two-layer artifact and replay one deterministic forecast."""

    try:
        artifact = json.loads(artifact_bytes)
        total_section = artifact["season_total_model"]
        total_payload = total_section["fit"]
        timing_section = artifact["timing_model"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SimplificationError("MODEL_ARTIFACT_SCHEMA_INVALID") from exc
    if (
        not isinstance(artifact, Mapping)
        or not isinstance(total_section, Mapping)
        or not isinstance(total_payload, Mapping)
        or not isinstance(timing_section, Mapping)
    ):
        raise SimplificationError("MODEL_ARTIFACT_SCHEMA_INVALID")
    if not math.isfinite(float(prediction_area_mu)) or prediction_area_mu <= 0:
        raise SimplificationError("PREDICTION_AREA_INVALID")
    if support_length <= 0 or support_offset < 0:
        raise SimplificationError("PREDICTION_SUPPORT_INVALID")

    ridge_payload = total_payload.get("ridge")
    ridge = RidgeFit.from_payload(ridge_payload) if isinstance(ridge_payload, Mapping) else None
    pooled_yield = total_payload.get("pooled_yield_kg_per_mu")
    total_fit = TotalFit(
        model_id=str(total_payload.get("model_id", total_section.get("model_id", ""))),
        pooled_yield_kg_per_mu=float(pooled_yield) if pooled_yield is not None else None,
        feature_names=tuple(str(value) for value in total_payload.get("feature_names", ())),
        ridge=ridge,
    )
    if not total_fit.model_id:
        raise SimplificationError("MODEL_ARTIFACT_SCHEMA_INVALID")
    yield_value = predict_yield(total_fit, total_features)
    total_value = yield_value * float(prediction_area_mu)

    global_shape_payload = timing_section.get("global_shape")
    if isinstance(global_shape_payload, Sequence) and not isinstance(
        global_shape_payload, (str, bytes)
    ):
        shape = tuple(float(value) for value in global_shape_payload)
        upper = support_offset + support_length
        if upper > len(shape):
            raise SimplificationError("TIMING_ARTIFACT_SUPPORT_INVALID")
        shares = normalize_nonnegative(shape[support_offset:upper])
    else:
        timing_payload = timing_section.get("fit")
        if not isinstance(timing_payload, Mapping):
            raise SimplificationError("MODEL_ARTIFACT_SCHEMA_INVALID")
        timing_fit = TimingFit.from_payload(timing_payload)
        shares = predict_timing_shares(
            timing_fit,
            support_length,
            weather_features=timing_features,
            support_offset=support_offset,
        )
    daily = tuple(total_value * share for share in shares)
    if not math.isclose(sum(daily), total_value, rel_tol=1e-12, abs_tol=1e-8):
        raise SimplificationError("MODEL_ARTIFACT_DAILY_CONSERVATION_FAILED")
    return {
        "season_total_model_id": str(total_section.get("model_id", total_fit.model_id)),
        "timing_model_id": str(timing_section.get("model_id", "")),
        "predicted_yield_kg_per_mu": yield_value,
        "predicted_season_total_kg": total_value,
        "daily_share": tuple(shares),
        "daily_quantity_kg": daily,
    }
