"""Small deterministic components for the V0.10 mechanism-informed experiment.

This module deliberately builds on the accepted Task 7 weather projection and
Task 8 shared-spline maturity model.  Its logistic timing curve is a
training-derived calendar proxy inspired by the reviewed cumulative-maturity
equation; it is not a direct physiological observation or a calibrated
V0.9 biological parameter.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from backend.app.area_yield.weather_features import (
    PRIMARY_FEATURES,
    WEATHER_FEATURE_POLICY_VERSION,
    WeatherDailyObservation,
    WeatherFeatureError,
    build_feature_row,
)

RIDGE_ALPHA_TOTAL = 10.0
RIDGE_ALPHA_DAILY = 50.0
DAILY_LOG_RATIO_CLIP = 3.0
WEATHER_FEATURE_VERSION = WEATHER_FEATURE_POLICY_VERSION
LOCAL_TZ = ZoneInfo("Asia/Shanghai")


class MechanismModelError(ValueError):
    """Raised when a frozen experiment input or deterministic fit is invalid."""


@dataclass(frozen=True, slots=True)
class RidgeFit:
    """Canonical train-only standardized ridge fit."""

    feature_names: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    alpha: float

    def payload(self) -> dict[str, Any]:
        return {
            "feature_names": list(self.feature_names),
            "means": [_float_text(value) for value in self.means],
            "scales": [_float_text(value) for value in self.scales],
            "coefficients": [_float_text(value) for value in self.coefficients],
            "intercept": _float_text(self.intercept),
            "alpha": _float_text(self.alpha),
            "solver": "NUMPY_NORMAL_EQUATION_STANDARDIZED_RIDGE",
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> RidgeFit:
        result = cls(
            feature_names=tuple(str(value) for value in payload["feature_names"]),
            means=tuple(float(value) for value in payload["means"]),
            scales=tuple(float(value) for value in payload["scales"]),
            coefficients=tuple(float(value) for value in payload["coefficients"]),
            intercept=float(payload["intercept"]),
            alpha=float(payload["alpha"]),
        )
        if (
            not result.feature_names
            or len(set(result.feature_names)) != len(result.feature_names)
            or not all(
                len(values) == len(result.feature_names)
                for values in (result.means, result.scales, result.coefficients)
            )
            or any(value <= 0 for value in result.scales)
            or not all(
                math.isfinite(value)
                for values in (
                    result.means,
                    result.scales,
                    result.coefficients,
                    (result.intercept, result.alpha),
                )
                for value in values
            )
        ):
            raise MechanismModelError("RIDGE_ARTIFACT_SCHEMA_INVALID")
        return result

    def predict(self, row: Mapping[str, float]) -> float:
        missing = [name for name in self.feature_names if name not in row]
        if missing:
            raise MechanismModelError(f"MODEL_FEATURE_MISSING:{','.join(missing)}")
        values = np.asarray([float(row[name]) for name in self.feature_names], dtype=float)
        means = np.asarray(self.means, dtype=float)
        scales = np.asarray(self.scales, dtype=float)
        coefficients = np.asarray(self.coefficients, dtype=float)
        if not np.isfinite(values).all():
            raise MechanismModelError("NONFINITE_MODEL_FEATURE")
        result = self.intercept + float(np.dot((values - means) / scales, coefficients))
        if not math.isfinite(result):
            raise MechanismModelError("NONFINITE_MODEL_PREDICTION")
        return result


def load_ridge_model_from_artifact(payload: bytes, *, fitted_parameter_key: str) -> RidgeFit:
    """Reload one frozen ridge component from serialized model-artifact bytes."""

    try:
        artifact = json.loads(payload)
        fitted_parameters = artifact["fitted_parameters"]
        model_payload = fitted_parameters[fitted_parameter_key]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise MechanismModelError("MODEL_ARTIFACT_COMPONENT_MISSING") from exc
    if not isinstance(artifact, Mapping) or not isinstance(model_payload, Mapping):
        raise MechanismModelError("MODEL_ARTIFACT_SCHEMA_INVALID")
    return RidgeFit.from_payload(model_payload)


def _float_text(value: float) -> str:
    if not math.isfinite(value):
        raise MechanismModelError("NONFINITE_MODEL_NUMBER")
    return format(value, ".17g")


def fit_ridge(
    feature_rows: Sequence[Mapping[str, float]],
    targets: Sequence[float],
    *,
    feature_names: Sequence[str],
    alpha: float,
) -> RidgeFit:
    """Fit deterministic ridge with train-only population standardization."""

    names = tuple(feature_names)
    if not feature_rows or len(feature_rows) != len(targets) or not names:
        raise MechanismModelError("RIDGE_TRAINING_SHAPE_INVALID")
    matrix = np.asarray([[float(row[name]) for name in names] for row in feature_rows], dtype=float)
    labels = np.asarray([float(value) for value in targets], dtype=float)
    if not np.isfinite(matrix).all() or not np.isfinite(labels).all():
        raise MechanismModelError("NONFINITE_RIDGE_TRAINING_VALUE")
    means = matrix.mean(axis=0)
    scales = matrix.std(axis=0)
    scales = np.where(scales == 0.0, 1.0, scales)
    standardized = (matrix - means) / scales
    design = np.column_stack((np.ones(len(standardized)), standardized))
    penalty = np.eye(design.shape[1], dtype=float) * float(alpha)
    penalty[0, 0] = 0.0
    try:
        weights = np.linalg.solve(design.T @ design + penalty, design.T @ labels)
    except np.linalg.LinAlgError as exc:
        raise MechanismModelError("RIDGE_SOLVE_FAILED") from exc
    if not np.isfinite(weights).all():
        raise MechanismModelError("NONFINITE_RIDGE_COEFFICIENT")
    return RidgeFit(
        feature_names=names,
        means=tuple(float(value) for value in means),
        scales=tuple(float(value) for value in scales),
        coefficients=tuple(float(value) for value in weights[1:]),
        intercept=float(weights[0]),
        alpha=float(alpha),
    )


def fit_logistic_calendar_proxy(
    curves: Sequence[Sequence[tuple[int, float]]],
) -> tuple[float, float]:
    """Estimate only the calendar-axis median/width of training harvest curves."""

    quantile_days: dict[float, list[int]] = {0.25: [], 0.5: [], 0.75: []}
    for curve in curves:
        ordered = sorted((int(day), float(share)) for day, share in curve)
        total = sum(max(share, 0.0) for _, share in ordered)
        if total <= 0:
            continue
        cumulative = 0.0
        found: dict[float, int] = {}
        for day, share in ordered:
            cumulative += max(share, 0.0) / total
            for quantile in quantile_days:
                if quantile not in found and cumulative >= quantile:
                    found[quantile] = day
        for quantile, day in found.items():
            quantile_days[quantile].append(day)
    if any(not values for values in quantile_days.values()):
        raise MechanismModelError("INSUFFICIENT_TRAINING_CURVES_FOR_TIMING_PROXY")
    medians = quantile_days[0.5]
    lower = quantile_days[0.25]
    upper = quantile_days[0.75]
    median_day = sum(medians) / len(medians)
    interquartile_days = sum(upper) / len(upper) - sum(lower) / len(lower)
    scale_days = max(5.0, interquartile_days / (2.0 * math.log(3.0)))
    return median_day, scale_days


def logistic_calendar_shape(
    day_offsets: Sequence[int], *, median_day: float, scale_days: float
) -> tuple[float, ...]:
    """Return normalized nonnegative increments of a calendar maturity proxy."""

    if not day_offsets or scale_days <= 0:
        raise MechanismModelError("CALENDAR_PROXY_SUPPORT_INVALID")
    density: list[float] = []
    for day in day_offsets:
        z = max(-60.0, min(60.0, (float(day) - median_day) / scale_days))
        cumulative = 1.0 / (1.0 + math.exp(-z))
        density.append(cumulative * (1.0 - cumulative) / scale_days)
    return normalize_nonnegative(density)


def normalize_nonnegative(values: Sequence[float]) -> tuple[float, ...]:
    if not values or any(not math.isfinite(float(value)) or value < 0 for value in values):
        raise MechanismModelError("NONNEGATIVE_SHAPE_INVALID")
    total = sum(float(value) for value in values)
    if total <= 0:
        raise MechanismModelError("SHAPE_HAS_NO_MASS")
    normalized = [float(value) / total for value in values]
    normalized[-1] += 1.0 - sum(normalized)
    if any(value < 0 for value in normalized) or abs(sum(normalized) - 1.0) > 1e-12:
        raise MechanismModelError("SHAPE_NORMALIZATION_FAILED")
    return tuple(normalized)


def weather_feature_row(
    observations: Sequence[WeatherDailyObservation],
    *,
    base_id: str,
    day: date,
    source_dataset_hash: str,
) -> dict[str, float] | None:
    """Reuse the Task 7 past-weather feature builder for one calendar day."""

    origin = datetime.combine(day, time.min, tzinfo=LOCAL_TZ)
    try:
        feature_row = build_feature_row(
            observations=observations,
            base_id=base_id,
            forecast_origin=origin,
            target_start=day,
            target_end=day,
            source_dataset_hash=source_dataset_hash,
        )
    except WeatherFeatureError as exc:
        if str(exc) == "HISTORICAL_WEATHER_WINDOW_INCOMPLETE":
            return None
        raise MechanismModelError(f"TASK7_WEATHER_FEATURE_INVALID:{exc}") from exc
    return {name: float(value) for name, value in feature_row.features.items()}


def weather_season_summary(
    observations: Sequence[WeatherDailyObservation], *, start: date, end: date
) -> dict[str, float]:
    """Summarize accepted daily ERA5 rows over an explicit season window."""

    selected = [item for item in observations if start <= item.local_date <= end]
    expected = (end - start).days + 1
    by_day = {item.local_date: item for item in selected}
    if len(by_day) != expected:
        raise MechanismModelError(
            f"WEATHER_SEASON_WINDOW_INCOMPLETE:{start.isoformat()}:{end.isoformat()}"
        )
    rows = list(by_day.values())
    count = float(len(rows))
    return {
        "season_mean_temperature_c": sum(float(row.mean_temperature_c) for row in rows) / count,
        "season_mean_tmin_c": sum(float(row.tmin_c) for row in rows) / count,
        "season_mean_tmax_c": sum(float(row.tmax_c) for row in rows) / count,
        "season_precipitation_total_mm": sum(float(row.precipitation_mm) for row in rows),
        "season_mean_solar_mj_m2": sum(float(row.solar_energy_j_m2) / 1_000_000.0 for row in rows)
        / count,
        "season_mean_wind_speed_m_s": sum(float(row.wind_speed_m_s) for row in rows) / count,
    }


def training_only_climatology(
    observations: Sequence[WeatherDailyObservation],
    *,
    target_base_ids: Sequence[str],
    calendar_start: date,
    target_start: date,
    target_end: date,
    training_dataset_hash: str,
) -> tuple[dict[str, tuple[WeatherDailyObservation, ...]], dict[str, str]]:
    """Build Base/day-of-year mean weather from training seasons only.

    The supplied observations must already be filtered to training seasons.
    A Base-specific profile is preferred; the training-cohort day-of-year mean
    is an explicit fallback for a Base with no corresponding profile.
    """

    by_base_month: dict[tuple[str, str], list[WeatherDailyObservation]] = defaultdict(list)
    by_month: dict[str, list[WeatherDailyObservation]] = defaultdict(list)
    for item in observations:
        month_day = item.local_date.strftime("%m-%d")
        by_base_month[(item.base_id, month_day)].append(item)
        by_month[month_day].append(item)
    calendar_end = target_end
    result: dict[str, tuple[WeatherDailyObservation, ...]] = {}
    basis: dict[str, str] = {}
    for base_id in sorted(set(target_base_ids)):
        generated: list[WeatherDailyObservation] = []
        used_base_profile = True
        day = calendar_start
        while day <= calendar_end:
            month_day = day.strftime("%m-%d")
            source_rows = by_base_month.get((base_id, month_day), [])
            if not source_rows:
                source_rows = by_month.get(month_day, [])
                used_base_profile = False
            if not source_rows:
                raise MechanismModelError(f"TRAINING_CLIMATOLOGY_DAY_MISSING:{month_day}")
            denominator = Decimal(len(source_rows))
            means = {
                field: sum((getattr(row, field) for row in source_rows), Decimal(0)) / denominator
                for field in (
                    "mean_temperature_c",
                    "tmin_c",
                    "tmax_c",
                    "precipitation_mm",
                    "solar_energy_j_m2",
                    "wind_speed_m_s",
                )
            }
            values = {
                "base_id": base_id,
                "local_date": day.isoformat(),
                **means,
            }
            row_hash_payload = "|".join(
                [
                    base_id,
                    day.isoformat(),
                    *(
                        format(values[key], "f")
                        for key in values
                        if key not in {"base_id", "local_date"}
                    ),
                ]
            )
            generated.append(
                WeatherDailyObservation(
                    base_id=base_id,
                    local_date=day,
                    mean_temperature_c=means["mean_temperature_c"],
                    tmin_c=means["tmin_c"],
                    tmax_c=means["tmax_c"],
                    precipitation_mm=means["precipitation_mm"],
                    solar_energy_j_m2=means["solar_energy_j_m2"],
                    wind_speed_m_s=means["wind_speed_m_s"],
                    source_row_hash=hashlib.sha256(row_hash_payload.encode("utf-8")).hexdigest(),
                    source_dataset_hash=training_dataset_hash,
                )
            )
            day += timedelta(days=1)
        result[base_id] = tuple(generated)
        basis[base_id] = (
            "TRAINING_BASE_DOY_MEAN" if used_base_profile else "TRAINING_COHORT_DOY_MEAN"
        )
    return result, basis


def task7_daily_feature_names() -> tuple[str, ...]:
    return tuple(PRIMARY_FEATURES)


def season_progress_features(day: date, *, start: date, end: date) -> dict[str, float]:
    span = (end - start).days
    if span <= 0 or not start <= day <= end:
        raise MechanismModelError("SEASON_PROGRESS_DAY_OUTSIDE_BOUNDARY")
    progress = (day - start).days / span
    angle_one = 2.0 * math.pi * progress
    angle_two = 4.0 * math.pi * progress
    return {
        "season_progress": progress,
        "season_sin_1": math.sin(angle_one),
        "season_cos_1": math.cos(angle_one),
        "season_sin_2": math.sin(angle_two),
        "season_cos_2": math.cos(angle_two),
    }


def task8_shared_shape(
    training_curves: Sequence[Sequence[Mapping[str, Any]]],
    *,
    season_starts: Mapping[str, date],
    support_days: Sequence[int],
) -> tuple[float, ...]:
    """Fit the existing Task 8 shared spline over training normalized shares."""

    from backend.app.maturity.model import fit_shared_curve

    relative_days: list[int] = []
    shares: list[Decimal] = []
    weights: list[Decimal] = []
    for curve in training_curves:
        total = sum((Decimal(str(row["new_quantity_kg"])) for row in curve), Decimal(0))
        if total <= 0:
            continue
        if not curve:
            continue
        season = str(curve[0]["season"])
        anchor = season_starts[season]
        for row in curve:
            day = date.fromisoformat(str(row["date"]))
            relative_days.append((day - anchor).days)
            shares.append(Decimal(str(row["new_quantity_kg"])) / total)
            weights.append(Decimal(1))
    fitted = fit_shared_curve(
        relative_days=tuple(relative_days),
        shares=tuple(shares),
        sample_weights=tuple(weights),
        support_days=tuple(int(day) for day in support_days),
        spline_degree=3,
        spline_knot_count=6,
        ridge_alpha=Decimal("0.10"),
    )
    return normalize_nonnegative([float(value) for value in fitted])
