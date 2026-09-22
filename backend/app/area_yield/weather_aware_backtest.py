"""V0.7-S3 leakage-safe weather-aware rolling OOT experiment.

This module is intentionally an experiment boundary, not a replacement for
the V0.5 forecast service.  It builds one canonical daily target row for a
``base_id + forecast_origin + target_date`` identity and fits two frozen Ridge
variants on the same rows:

* Model A: ten calendar/area features;
* Model B1: the same ten features plus the eighteen S2 Lane-A weather fields.

The public functions keep validation labels out of row construction and
prediction sealing.  Scoring consumes a separately supplied actual authority
only after the caller has sealed both prediction payloads.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from backend.app.area_yield.data import digest
from backend.app.area_yield.formal_multi_season_validation import (
    ActualDay,
    BusinessBoundary,
    business_calendar,
)
from backend.app.area_yield.weather_features import (
    PRIMARY_FEATURES,
    WEATHER_FEATURE_POLICY_VERSION,
    WeatherDailyObservation,
    WeatherFeatureError,
    build_feature_row,
)

MODEL_A_S3 = "AREA_DAILY_RIDGE_V1_ROLLING_OOT_NO_WEATHER"
MODEL_B1 = "AREA_DAILY_RIDGE_V1_PLUS_LEAKAGE_SAFE_WEATHER_FEATURES"
MODEL_FAMILY = "RIDGE_LEAST_SQUARES"
ALPHA = Decimal("10.000000")
INTERCEPT_UNPENALIZED = True
NONNEGATIVE_OUTPUT_CLIP = True
SOLVER = "numpy.linalg.solve"
FORECAST_ORIGIN_POLICY = "ROLLING_DAILY_LOCAL_DAY_START"
FORECAST_ORIGIN_TIMEZONE = "Asia/Shanghai"
TARGET_GRANULARITY = "DAILY"
TARGET_LABEL = "ACTUAL_DAILY_HARVEST_KG"
TARGET_ROW_IDENTITY = "base_id+forecast_origin+target_date"
HORIZONS = {"H1": 1, "H7": 7, "H15": 15}
HORIZON_TARGET_TYPES = {
    "H1": "DAILY_VECTOR_LENGTH_1",
    "H7": "DAILY_VECTOR_LENGTH_7",
    "H15": "DAILY_VECTOR_LENGTH_15",
}
BASE_FEATURES = (
    "reference_area_mu_div_1000",
    "season_progress",
    "sin_1",
    "cos_1",
    "sin_2",
    "cos_2",
    "area_x_sin_1",
    "area_x_cos_1",
    "area_x_sin_2",
    "area_x_cos_2",
)
FEATURE_NAMES_A = BASE_FEATURES
FEATURE_NAMES_B = BASE_FEATURES + tuple(PRIMARY_FEATURES)
WEATHER_FEATURE_COUNT = len(PRIMARY_FEATURES)
FEATURE_COUNT_A = len(FEATURE_NAMES_A)
FEATURE_COUNT_B = len(FEATURE_NAMES_B)
WEATHER_SOURCE = "ERA5_LAND"
WEATHER_ROLE = "HISTORICAL_REALIZED_OBSERVATION"
WEATHER_LANE = "PAST_OBSERVED_WEATHER"
ERA5_FORECAST_TIME_KNOWN_AT_STATUS = "NOT_ESTABLISHED"
TZ = ZoneInfo(FORECAST_ORIGIN_TIMEZONE)
_DECIMAL_QUANTUM = Decimal("0.000000000001")


class WeatherAwareBacktestError(ValueError):
    """Raised when a frozen S3 contract cannot be established."""


def _text(value: Decimal) -> str:
    if not value.is_finite():
        raise WeatherAwareBacktestError("NONFINITE_DECIMAL")
    return format(value, "f")


def _finite_float(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise WeatherAwareBacktestError(f"INVALID_FEATURE_VALUE:{field}") from exc
    if not math.isfinite(result):
        raise WeatherAwareBacktestError(f"NONFINITE_FEATURE_VALUE:{field}")
    return result


def _origin_for(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=TZ)


def target_row_key(*, base_id: str, forecast_origin: datetime, target_date: date) -> str:
    if not base_id:
        raise WeatherAwareBacktestError("BASE_ID_REQUIRED")
    if forecast_origin.tzinfo is None or forecast_origin.utcoffset() is None:
        raise WeatherAwareBacktestError("FORECAST_ORIGIN_MUST_BE_TIMEZONE_AWARE")
    origin = forecast_origin.astimezone(TZ)
    if origin.time() != time.min:
        raise WeatherAwareBacktestError("FORECAST_ORIGIN_NOT_LOCAL_DAY_START")
    if target_date < origin.date():
        raise WeatherAwareBacktestError("TARGET_DATE_BEFORE_ORIGIN")
    return "+".join((base_id, origin.isoformat(), target_date.isoformat()))


@dataclass(frozen=True, slots=True)
class RollingTargetRow:
    """One canonical target row; actual labels are optional by design."""

    key: str
    base_id: str
    base_name: str
    season: str
    forecast_origin: str
    target_date: date
    lead_day: int
    reference_area_mu: Decimal
    feature_values: tuple[tuple[str, str], ...]
    weather_feature_hash: str
    weather_source: str = WEATHER_SOURCE
    weather_lane: str = WEATHER_LANE
    feature_policy_version: str = WEATHER_FEATURE_POLICY_VERSION

    @property
    def features(self) -> dict[str, str]:
        return dict(self.feature_values)

    def payload(self) -> dict[str, Any]:
        return {
            "target_row_key": self.key,
            "base_id": self.base_id,
            "base_name": self.base_name,
            "season": self.season,
            "forecast_origin": self.forecast_origin,
            "target_date": self.target_date.isoformat(),
            "lead_day": self.lead_day,
            "reference_area_mu": _text(self.reference_area_mu),
            "feature_values": self.features,
            "weather_feature_hash": self.weather_feature_hash,
            "weather_source": self.weather_source,
            "weather_lane": self.weather_lane,
            "feature_policy_version": self.feature_policy_version,
        }


@dataclass(frozen=True, slots=True)
class RidgeArtifact:
    """Deterministic coefficient artifact for one fold and feature schema."""

    model_id: str
    fold_id: str
    feature_names: tuple[str, ...]
    alpha: str
    intercept_unpenalized: bool
    nonnegative_output_clip: bool
    solver: str
    feature_means: tuple[str, ...]
    feature_scales: tuple[str, ...]
    coefficients: tuple[str, ...]
    intercept: str
    training_row_keys: tuple[str, ...]
    training_label_hash: str
    training_input_hash: str
    artifact_hash: str

    def payload_without_hash(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "fold_id": self.fold_id,
            "feature_names": list(self.feature_names),
            "alpha": self.alpha,
            "intercept_unpenalized": self.intercept_unpenalized,
            "nonnegative_output_clip": self.nonnegative_output_clip,
            "solver": self.solver,
            "feature_means": list(self.feature_means),
            "feature_scales": list(self.feature_scales),
            "coefficients": list(self.coefficients),
            "intercept": self.intercept,
            "training_row_keys": list(self.training_row_keys),
            "training_label_hash": self.training_label_hash,
            "training_input_hash": self.training_input_hash,
        }

    def payload(self) -> dict[str, Any]:
        return {**self.payload_without_hash(), "artifact_hash": self.artifact_hash}

    def predict(self, row: RollingTargetRow) -> Decimal:
        raw_values = feature_vector(row, self.feature_names)
        values = tuple(
            (value - float(mean)) / float(scale)
            for value, mean, scale in zip(
                raw_values, self.feature_means, self.feature_scales, strict=True
            )
        )
        result = float(self.intercept) + sum(
            float(coefficient) * value
            for coefficient, value in zip(self.coefficients, values, strict=True)
        )
        if not math.isfinite(result):
            raise WeatherAwareBacktestError("NONFINITE_MODEL_OUTPUT")
        if NONNEGATIVE_OUTPUT_CLIP:
            result = max(0.0, result)
        return Decimal(format(result, ".12f"))


def _feature_row_values(row: RollingTargetRow) -> dict[str, float]:
    return {name: _finite_float(value, name) for name, value in row.features.items()}


def feature_vector(row: RollingTargetRow, feature_names: Sequence[str]) -> tuple[float, ...]:
    values = _feature_row_values(row)
    missing = [name for name in feature_names if name not in values]
    if missing:
        raise WeatherAwareBacktestError(f"FEATURES_MISSING:{','.join(missing)}")
    return tuple(values[name] for name in feature_names)


def _base_feature_values(
    *, reference_area_mu: Decimal, target_date: date, boundary: BusinessBoundary
) -> dict[str, str]:
    if reference_area_mu <= 0 or not reference_area_mu.is_finite():
        raise WeatherAwareBacktestError("REFERENCE_AREA_INVALID")
    span = (boundary.end - boundary.start).days
    if span <= 0:
        raise WeatherAwareBacktestError("BUSINESS_BOUNDARY_INVALID")
    progress = (target_date - boundary.start).days / span
    area = float(reference_area_mu / Decimal("1000"))
    angle_1 = 2.0 * math.pi * progress
    angle_2 = 4.0 * math.pi * progress
    values = {
        "reference_area_mu_div_1000": area,
        "season_progress": progress,
        "sin_1": math.sin(angle_1),
        "cos_1": math.cos(angle_1),
        "sin_2": math.sin(angle_2),
        "cos_2": math.cos(angle_2),
        "area_x_sin_1": area * math.sin(angle_1),
        "area_x_cos_1": area * math.cos(angle_1),
        "area_x_sin_2": area * math.sin(angle_2),
        "area_x_cos_2": area * math.cos(angle_2),
    }
    return {key: format(value, ".17g") for key, value in values.items()}


def _weather_by_name(feature_row: Any) -> dict[str, str]:
    features = getattr(feature_row, "features", None)
    if not isinstance(features, dict):
        raise WeatherAwareBacktestError("WEATHER_FEATURE_ROW_INVALID")
    return {str(key): str(value) for key, value in features.items()}


def _weather_index(
    observations: Iterable[WeatherDailyObservation],
) -> dict[str, tuple[WeatherDailyObservation, ...]]:
    grouped: dict[str, list[WeatherDailyObservation]] = defaultdict(list)
    seen: set[tuple[str, date]] = set()
    for observation in observations:
        key = (observation.base_id, observation.local_date)
        if key in seen:
            raise WeatherAwareBacktestError(f"DUPLICATE_WEATHER_ROW:{key[0]}:{key[1]}")
        seen.add(key)
        grouped[observation.base_id].append(observation)
    return {
        base_id: tuple(sorted(rows, key=lambda row: row.local_date))
        for base_id, rows in grouped.items()
    }


def build_rolling_rows(
    *,
    season: str,
    base_scope: Sequence[Mapping[str, Any]],
    observations: Iterable[WeatherDailyObservation],
    source_dataset_hash: str,
    boundary: BusinessBoundary,
) -> tuple[tuple[RollingTargetRow, ...], dict[str, Any]]:
    """Build all weather-eligible daily target rows without reading labels."""

    if boundary.season != season:
        raise WeatherAwareBacktestError("BOUNDARY_SEASON_MISMATCH")
    weather = _weather_index(observations)
    calendar = business_calendar(season, boundary)
    rows: list[RollingTargetRow] = []
    candidate_origin_count = len(calendar) * len(base_scope)
    weather_eligible_origin_count = 0
    incomplete_by_base: dict[str, int] = defaultdict(int)
    for base in sorted(base_scope, key=lambda item: str(item["base_id"])):
        base_id = str(base["base_id"])
        base_name = str(base.get("canonical_base_name", base_id))
        area = Decimal(str(base.get("productive_area_mu", "0")))
        base_observations = weather.get(base_id, ())
        for origin_day in calendar:
            origin = _origin_for(origin_day)
            try:
                context = build_feature_row(
                    observations=base_observations,
                    base_id=base_id,
                    forecast_origin=origin,
                    target_start=origin_day,
                    target_end=origin_day,
                    source_dataset_hash=source_dataset_hash,
                )
            except WeatherFeatureError as exc:
                if str(exc) == "HISTORICAL_WEATHER_WINDOW_INCOMPLETE":
                    incomplete_by_base[base_id] += 1
                    continue
                raise
            weather_eligible_origin_count += 1
            weather_values = _weather_by_name(context)
            for target_day in calendar:
                lead_day = (target_day - origin_day).days
                if lead_day < 0 or lead_day > 14:
                    continue
                key = target_row_key(
                    base_id=base_id,
                    forecast_origin=origin,
                    target_date=target_day,
                )
                feature_values = {
                    **_base_feature_values(
                        reference_area_mu=area,
                        target_date=target_day,
                        boundary=boundary,
                    ),
                    **weather_values,
                }
                rows.append(
                    RollingTargetRow(
                        key=key,
                        base_id=base_id,
                        base_name=base_name,
                        season=season,
                        forecast_origin=origin.isoformat(),
                        target_date=target_day,
                        lead_day=lead_day,
                        reference_area_mu=area,
                        feature_values=tuple(sorted(feature_values.items())),
                        weather_feature_hash=context.feature_hash,
                    )
                )
    rows.sort(key=lambda row: (row.base_id, row.forecast_origin, row.target_date))
    keys = [row.key for row in rows]
    if len(keys) != len(set(keys)):
        raise WeatherAwareBacktestError("DUPLICATE_TARGET_ROW_KEY")
    return tuple(rows), {
        "season": season,
        "candidate_origin_count": candidate_origin_count,
        "weather_eligible_origin_count": weather_eligible_origin_count,
        "weather_ineligible_origin_count": candidate_origin_count - weather_eligible_origin_count,
        "weather_ineligible_reason": "NOT_ELIGIBLE_INCOMPLETE_30DAY_WINDOW",
        "incomplete_origin_count_by_base": dict(sorted(incomplete_by_base.items())),
        "prediction_target_row_count": len(rows),
        "weather_source": WEATHER_SOURCE,
        "weather_lane": WEATHER_LANE,
        "source_dataset_hash": source_dataset_hash,
        "information_cutoff": "MAX_SOURCE_OBSERVATION_LOCAL_DATE=ORIGIN_LOCAL_DATE_MINUS_1",
    }


def rows_with_known_labels(
    rows: Iterable[RollingTargetRow],
    actual_by_base: Mapping[str, Sequence[ActualDay]],
) -> tuple[tuple[RollingTargetRow, Decimal], ...]:
    """Attach only known/confirmed actuals for training; never fill missing."""

    actual_index = {
        (base_id, actual.day): actual
        for base_id, values in actual_by_base.items()
        for actual in values
    }
    result: list[tuple[RollingTargetRow, Decimal]] = []
    for row in rows:
        actual = actual_index.get((row.base_id, row.target_date))
        if actual is None or actual.quantity_kg is None:
            continue
        if actual.status not in {"KNOWN_MAPPED_SUBTOTAL", "CONFIRMED_ZERO"}:
            continue
        result.append((row, actual.quantity_kg))
    return tuple(result)


def _label_hash(rows: Sequence[tuple[RollingTargetRow, Decimal]]) -> str:
    return digest(
        [
            {"target_row_key": row.key, "actual_daily_kg": _text(label)}
            for row, label in sorted(rows, key=lambda item: item[0].key)
        ]
    )


def fit_ridge_artifact(
    *,
    model_id: str,
    fold_id: str,
    rows: Sequence[tuple[RollingTargetRow, Decimal]],
    feature_names: Sequence[str],
    training_input_hash: str,
) -> RidgeArtifact:
    """Fit exactly one frozen Ridge normal equation on training rows."""

    if not rows:
        raise WeatherAwareBacktestError("NO_TRAINING_ROWS")
    ordered = tuple(sorted(rows, key=lambda item: item[0].key))
    matrix = np.asarray([feature_vector(row, feature_names) for row, _ in ordered], dtype=float)
    labels = np.asarray([float(label) for _, label in ordered], dtype=float)
    if not np.isfinite(matrix).all() or not np.isfinite(labels).all():
        raise WeatherAwareBacktestError("NONFINITE_TRAINING_VALUE")
    means = matrix.mean(axis=0)
    scales = matrix.std(axis=0)
    scales = np.where(scales == 0.0, 1.0, scales)
    standardized = (matrix - means) / scales
    design = np.column_stack((np.ones(len(standardized)), standardized))
    regularizer = np.zeros((design.shape[1], design.shape[1]), dtype=float)
    regularizer[1:, 1:] = float(ALPHA) * np.eye(len(feature_names))
    coefficients = np.linalg.solve(design.T @ design + regularizer, design.T @ labels)
    if not np.isfinite(coefficients).all():
        raise WeatherAwareBacktestError("NONFINITE_MODEL_ARTIFACT")
    coeff_text = tuple(format(float(value), ".17g") for value in coefficients[1:])
    intercept = format(float(coefficients[0]), ".17g")
    mean_text = tuple(format(float(value), ".17g") for value in means)
    scale_text = tuple(format(float(value), ".17g") for value in scales)
    training_label_hash = _label_hash(ordered)
    payload = {
        "model_id": model_id,
        "fold_id": fold_id,
        "feature_names": list(feature_names),
        "alpha": _text(ALPHA),
        "intercept_unpenalized": INTERCEPT_UNPENALIZED,
        "nonnegative_output_clip": NONNEGATIVE_OUTPUT_CLIP,
        "solver": SOLVER,
        "standardization": "TRAIN_ONLY_STANDARD_SCALER_POPULATION_STD",
        "feature_means": list(mean_text),
        "feature_scales": list(scale_text),
        "coefficients": list(coeff_text),
        "intercept": intercept,
        "training_row_keys": [row.key for row, _ in ordered],
        "training_label_hash": training_label_hash,
        "training_input_hash": training_input_hash,
    }
    return RidgeArtifact(
        model_id=model_id,
        fold_id=fold_id,
        feature_names=tuple(feature_names),
        alpha=_text(ALPHA),
        intercept_unpenalized=INTERCEPT_UNPENALIZED,
        nonnegative_output_clip=NONNEGATIVE_OUTPUT_CLIP,
        solver=SOLVER,
        feature_means=mean_text,
        feature_scales=scale_text,
        coefficients=coeff_text,
        intercept=intercept,
        training_row_keys=tuple(row.key for row, _ in ordered),
        training_label_hash=training_label_hash,
        training_input_hash=training_input_hash,
        artifact_hash=digest(payload),
    )


def seal_predictions(
    *,
    fold_id: str,
    validation_season: str,
    rows: Sequence[RollingTargetRow],
    model_a: RidgeArtifact,
    model_b: RidgeArtifact,
    boundary: BusinessBoundary,
    train_row_keys: Sequence[str],
) -> dict[str, Any]:
    """Seal A/B outputs before any validation labels are passed to scoring."""

    ordered = tuple(sorted(rows, key=lambda row: row.key))
    prediction_rows = [
        {
            **row.payload(),
            "model_a_predicted_daily_kg": _text(model_a.predict(row)),
            "model_b_predicted_daily_kg": _text(model_b.predict(row)),
        }
        for row in ordered
    ]
    model_a_hash = digest(
        [
            {
                "target_row_key": row["target_row_key"],
                "prediction": row["model_a_predicted_daily_kg"],
            }
            for row in prediction_rows
        ]
    )
    model_b_hash = digest(
        [
            {
                "target_row_key": row["target_row_key"],
                "prediction": row["model_b_predicted_daily_kg"],
            }
            for row in prediction_rows
        ]
    )
    manifest = {
        "fold_id": fold_id,
        "validation_season": validation_season,
        "model_a_id": model_a.model_id,
        "model_b_id": model_b.model_id,
        "model_a_artifact_hash": model_a.artifact_hash,
        "model_b_artifact_hash": model_b.artifact_hash,
        "train_row_keys_hash": digest(sorted(train_row_keys)),
        "validation_target_row_count": len(prediction_rows),
        "validation_target_row_keys_hash": digest(
            [row["target_row_key"] for row in prediction_rows]
        ),
        "business_boundary": boundary.payload(),
        "forecast_origin_policy": FORECAST_ORIGIN_POLICY,
        "target_granularity": TARGET_GRANULARITY,
        "target_label": TARGET_LABEL,
        "target_row_identity": TARGET_ROW_IDENTITY,
        "weather_source": WEATHER_SOURCE,
        "weather_lane": WEATHER_LANE,
        "validation_labels_read": False,
        "predictions_sealed_before_validation_label_scoring": True,
        "model_a_prediction_hash": model_a_hash,
        "model_b_prediction_hash": model_b_hash,
        "algorithm_changed": False,
        "feature_search": False,
        "hyperparameter_search": False,
    }
    return {
        "manifest": {**manifest, "artifact_manifest_hash": digest(manifest)},
        "predictions": prediction_rows,
    }


def _metric_rows(rows: Sequence[Mapping[str, Any]], *, model_key: str) -> dict[str, Any]:
    if not rows:
        return {
            "status": "NOT_COMPUTABLE_NO_COMPARABLE_ROWS",
            "sample_count": 0,
        }
    actuals = [Decimal(str(row["actual_daily_kg"])) for row in rows]
    predictions = [Decimal(str(row[model_key])) for row in rows]
    signed = [prediction - actual for prediction, actual in zip(predictions, actuals, strict=True)]
    absolute = [abs(value) for value in signed]
    denominator = sum(actuals, Decimal(0))
    return {
        "status": "COMPUTABLE",
        "sample_count": len(rows),
        "mae_kg": _text(sum(absolute, Decimal(0)) / Decimal(len(rows))),
        "pooled_wape": (
            _text(sum(absolute, Decimal(0)) / denominator)
            if denominator > 0
            else "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR"
        ),
        "bias_kg": _text(sum(signed, Decimal(0)) / Decimal(len(rows))),
        "bias_definition": "MEAN_PREDICTED_MINUS_ACTUAL; POSITIVE_OVERPREDICTION",
        "pooled_actual_kg": _text(denominator),
        "pooled_absolute_error_kg": _text(sum(absolute, Decimal(0))),
        "error_distribution_abs_kg": _error_distribution(absolute),
    }


def _error_distribution(values: Sequence[Decimal]) -> dict[str, str | None]:
    if not values:
        return {"median": None, "p75": None, "p90": None, "max": None}
    ordered = sorted(values)

    def percentile(fraction: Decimal) -> Decimal:
        position = fraction * Decimal(len(ordered) - 1)
        low = int(position)
        high = min(low + 1, len(ordered) - 1)
        return ordered[low] + (position - Decimal(low)) * (ordered[high] - ordered[low])

    return {
        "median": _text(percentile(Decimal("0.5"))),
        "p75": _text(percentile(Decimal("0.75"))),
        "p90": _text(percentile(Decimal("0.9"))),
        "max": _text(max(ordered)),
    }


def _complete_horizon_rows(
    rows: Sequence[Mapping[str, Any]], *, horizon_days: int, boundary: BusinessBoundary
) -> list[dict[str, Any]]:
    by_origin: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        origin = datetime.fromisoformat(str(row["forecast_origin"])).date()
        if origin + timedelta(days=horizon_days - 1) <= boundary.end:
            by_origin[(str(row["base_id"]), str(row["forecast_origin"]))].append(row)
    return [
        dict(row)
        for key in sorted(by_origin)
        if len({int(item["lead_day"]) for item in by_origin[key]}) == horizon_days
        for row in by_origin[key]
        if int(row["lead_day"]) < horizon_days
    ]


def _cumulative_metrics(
    rows: Sequence[Mapping[str, Any]], *, horizon_days: int, model_key: str
) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["base_id"]), str(row["forecast_origin"]))].append(row)
    windows: list[dict[str, Decimal]] = []
    for key in sorted(grouped):
        values = sorted(grouped[key], key=lambda row: int(row["lead_day"]))
        if len(values) != horizon_days or {int(row["lead_day"]) for row in values} != set(
            range(horizon_days)
        ):
            continue
        actual = sum((Decimal(str(row["actual_daily_kg"])) for row in values), Decimal(0))
        predicted = sum((Decimal(str(row[model_key])) for row in values), Decimal(0))
        windows.append({"actual": actual, "predicted": predicted})
    if not windows:
        return {
            "status": "NOT_COMPUTABLE_INCOMPLETE_TARGET_WINDOW",
            "complete_view_count": 0,
        }
    absolute = [abs(item["predicted"] - item["actual"]) for item in windows]
    actuals = [item["actual"] for item in windows]
    denominator = sum(actuals, Decimal(0))
    return {
        "status": "COMPUTABLE",
        "complete_view_count": len(windows),
        "pooled_wape": (
            _text(sum(absolute, Decimal(0)) / denominator)
            if denominator > 0
            else "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR"
        ),
        "pooled_absolute_error_kg": _text(sum(absolute, Decimal(0))),
        "pooled_actual_kg": _text(denominator),
    }


def score_predictions(
    *,
    sealed_predictions: Sequence[Mapping[str, Any]],
    actual_by_base: Mapping[str, Sequence[ActualDay]],
    boundary: BusinessBoundary,
) -> dict[str, Any]:
    """Reveal actuals and score only rows with explicit known/zero labels."""

    actual_index = {
        (base_id, actual.day): actual
        for base_id, values in actual_by_base.items()
        for actual in values
    }
    scored: list[dict[str, Any]] = []
    unscored = 0
    status_counts: dict[str, int] = defaultdict(int)
    for prediction in sorted(sealed_predictions, key=lambda row: str(row["target_row_key"])):
        key = (str(prediction["base_id"]), date.fromisoformat(str(prediction["target_date"])))
        actual = actual_index.get(key)
        if (
            actual is None
            or actual.quantity_kg is None
            or actual.status
            not in {
                "KNOWN_MAPPED_SUBTOTAL",
                "CONFIRMED_ZERO",
            }
        ):
            unscored += 1
            status_counts[actual.status if actual is not None else "ACTUAL_MISSING"] += 1
            continue
        scored.append(
            {
                **dict(prediction),
                "actual_daily_kg": _text(actual.quantity_kg),
                "actual_status": actual.status,
                "actual_source_hash": actual.source_hash,
            }
        )
    views: dict[str, list[dict[str, Any]]] = {}
    for horizon, days in HORIZONS.items():
        candidate = [row for row in scored if int(row["lead_day"]) < days]
        views[horizon] = _complete_horizon_rows(
            candidate,
            horizon_days=days,
            boundary=boundary,
        )
    model_summaries: dict[str, Any] = {}
    for model_key, model_id in (
        ("model_a_predicted_daily_kg", MODEL_A_S3),
        ("model_b_predicted_daily_kg", MODEL_B1),
    ):
        horizons: dict[str, Any] = {}
        for horizon, rows in views.items():
            summary = _metric_rows(rows, model_key=model_key)
            summary["cumulative"] = _cumulative_metrics(
                rows,
                horizon_days=HORIZONS[horizon],
                model_key=model_key,
            )
            by_lead = {
                str(lead): _metric_rows(
                    [row for row in rows if int(row["lead_day"]) == lead],
                    model_key=model_key,
                )
                for lead in range(HORIZONS[horizon])
            }
            summary["per_lead_day"] = by_lead
            horizons[horizon] = summary
        model_summaries[model_id] = {
            "horizons": horizons,
            "feature_count": FEATURE_COUNT_B if model_id == MODEL_B1 else FEATURE_COUNT_A,
        }
    deltas: dict[str, Any] = {}
    for horizon in HORIZONS:
        a = model_summaries[MODEL_A_S3]["horizons"][horizon]
        b = model_summaries[MODEL_B1]["horizons"][horizon]

        def delta(field: str, left: Mapping[str, Any], right: Mapping[str, Any]) -> str | None:
            av = left.get(field)
            bv = right.get(field)
            if not isinstance(av, str) or not isinstance(bv, str):
                return None
            if av.startswith("NOT_COMPUTABLE") or bv.startswith("NOT_COMPUTABLE"):
                return None
            return _text(Decimal(bv) - Decimal(av))

        deltas[horizon] = {
            "wape_delta_b_minus_a": delta("pooled_wape", a, b),
            "mae_delta_b_minus_a": delta("mae_kg", a, b),
            "bias_delta_b_minus_a": delta("bias_kg", a, b),
        }
    return {
        "scored_rows": scored,
        "scored_row_count": len(scored),
        "unscored_row_count": unscored,
        "unscored_status_counts": dict(sorted(status_counts.items())),
        "models": model_summaries,
        "deltas": deltas,
        "horizon_view_counts": {horizon: len(rows) for horizon, rows in views.items()},
        "metric_policy": {
            "wape": "POOLED_ABSOLUTE_ERROR_OVER_POOLED_ACTUAL",
            "mae": "MEAN_ABSOLUTE_ERROR_OVER_COMPARABLE_ROWS",
            "bias": "MEAN_PREDICTED_MINUS_ACTUAL; POSITIVE_OVERPREDICTION",
            "missing_actual": "NOT_COMPARABLE_ACTUAL_MISSING_OR_UNKNOWN",
            "confirmed_zero": "COMPARABLE_ACTUAL",
            "date_metrics": "NOT_APPLICABLE_DAILY_TARGET_ROW_TASK",
        },
        "boundary": boundary.payload(),
    }


def aggregate_scored_rows(
    *,
    scored_predictions: Sequence[Mapping[str, Any]],
    boundaries: Mapping[str, BusinessBoundary],
) -> dict[str, Any]:
    """Aggregate scored rows from multiple folds with pooled denominators."""

    by_season: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in scored_predictions:
        by_season[str(row["season"])].append(dict(row))
    views: dict[str, list[dict[str, Any]]] = {}
    for horizon, days in HORIZONS.items():
        rows: list[dict[str, Any]] = []
        for season in sorted(by_season):
            candidate = [row for row in by_season[season] if int(row["lead_day"]) < days]
            rows.extend(
                _complete_horizon_rows(
                    candidate,
                    horizon_days=days,
                    boundary=boundaries[season],
                )
            )
        views[horizon] = rows
    models: dict[str, Any] = {}
    for model_key, model_id, feature_count in (
        ("model_a_predicted_daily_kg", MODEL_A_S3, FEATURE_COUNT_A),
        ("model_b_predicted_daily_kg", MODEL_B1, FEATURE_COUNT_B),
    ):
        horizons: dict[str, Any] = {}
        for horizon, rows in views.items():
            summary = _metric_rows(rows, model_key=model_key)
            summary["cumulative"] = _cumulative_metrics(
                rows,
                horizon_days=HORIZONS[horizon],
                model_key=model_key,
            )
            summary["per_lead_day"] = {
                str(lead): _metric_rows(
                    [row for row in rows if int(row["lead_day"]) == lead],
                    model_key=model_key,
                )
                for lead in range(HORIZONS[horizon])
            }
            horizons[horizon] = summary
        models[model_id] = {"horizons": horizons, "feature_count": feature_count}
    deltas: dict[str, Any] = {}
    for horizon in HORIZONS:
        left = models[MODEL_A_S3]["horizons"][horizon]
        right = models[MODEL_B1]["horizons"][horizon]

        def delta(field: str, a: Mapping[str, Any], b: Mapping[str, Any]) -> str | None:
            av = a.get(field)
            bv = b.get(field)
            if not isinstance(av, str) or not isinstance(bv, str):
                return None
            if av.startswith("NOT_COMPUTABLE") or bv.startswith("NOT_COMPUTABLE"):
                return None
            return _text(Decimal(bv) - Decimal(av))

        deltas[horizon] = {
            "wape_delta_b_minus_a": delta("pooled_wape", left, right),
            "mae_delta_b_minus_a": delta("mae_kg", left, right),
            "bias_delta_b_minus_a": delta("bias_kg", left, right),
        }
    return {
        "scored_row_count": len(scored_predictions),
        "models": models,
        "deltas": deltas,
        "horizon_view_counts": {horizon: len(rows) for horizon, rows in views.items()},
        "boundaries": {
            season: boundary.payload() for season, boundary in sorted(boundaries.items())
        },
    }


def weather_sensitivity(
    *, row: RollingTargetRow, model_a: RidgeArtifact, model_b: RidgeArtifact
) -> dict[str, bool]:
    """Prove only B reacts to a legal weather-value mutation."""

    original = row.features
    replacement = dict(original)
    weather_name = PRIMARY_FEATURES[0]
    replacement[weather_name] = format(float(replacement[weather_name]) + 1.0, ".17g")
    mutated = RollingTargetRow(
        key=row.key,
        base_id=row.base_id,
        base_name=row.base_name,
        season=row.season,
        forecast_origin=row.forecast_origin,
        target_date=row.target_date,
        lead_day=row.lead_day,
        reference_area_mu=row.reference_area_mu,
        feature_values=tuple(sorted(replacement.items())),
        weather_feature_hash=digest(replacement),
    )
    return {
        "model_b_weather_sensitivity_pass": model_b.predict(row) != model_b.predict(mutated),
        "model_a_weather_invariance_pass": model_a.predict(row) == model_a.predict(mutated),
    }


def weather_sensitivity_prediction_set(
    *,
    rows: Sequence[RollingTargetRow],
    model_a: RidgeArtifact,
    model_b: RidgeArtifact,
    weather_feature: str = PRIMARY_FEATURES[0],
    delta: Decimal = Decimal("1.0"),
) -> dict[str, Any]:
    """Prove weather sensitivity on a complete sealed prediction row set.

    This is an inference-only acceptance probe. It reuses the already fitted
    artifacts and mutates one frozen weather feature on every validation row;
    it never reads validation labels and never refits either model. Hashing
    the complete prediction set avoids a false negative caused by a single
    row's non-negative output clipping.
    """

    if not rows:
        raise WeatherAwareBacktestError("NO_PREDICTION_ROWS_FOR_SENSITIVITY")
    if weather_feature not in PRIMARY_FEATURES:
        raise WeatherAwareBacktestError("WEATHER_FEATURE_NOT_IN_FROZEN_SCHEMA")
    ordered = tuple(sorted(rows, key=lambda row: row.key))

    def mutate(row: RollingTargetRow) -> RollingTargetRow:
        original = row.features
        if weather_feature not in original:
            raise WeatherAwareBacktestError("WEATHER_FEATURE_MISSING_FROM_ROW")
        replacement = dict(original)
        replacement[weather_feature] = format(
            _finite_float(replacement[weather_feature], weather_feature)
            + _finite_float(delta, "weather_mutation_delta"),
            ".17g",
        )
        return RollingTargetRow(
            key=row.key,
            base_id=row.base_id,
            base_name=row.base_name,
            season=row.season,
            forecast_origin=row.forecast_origin,
            target_date=row.target_date,
            lead_day=row.lead_day,
            reference_area_mu=row.reference_area_mu,
            feature_values=tuple(sorted(replacement.items())),
            weather_feature_hash=digest(replacement),
            weather_source=row.weather_source,
            weather_lane=row.weather_lane,
            feature_policy_version=row.feature_policy_version,
        )

    mutated = tuple(mutate(row) for row in ordered)
    for original, changed in zip(ordered, mutated, strict=True):
        if (
            original.key,
            original.base_id,
            original.forecast_origin,
            original.target_date,
            original.lead_day,
        ) != (
            changed.key,
            changed.base_id,
            changed.forecast_origin,
            changed.target_date,
            changed.lead_day,
        ):
            raise WeatherAwareBacktestError("SENSITIVITY_TARGET_IDENTITY_CHANGED")
        if any(original.features[name] != changed.features[name] for name in FEATURE_NAMES_A):
            raise WeatherAwareBacktestError("SENSITIVITY_BASE_FEATURE_CHANGED")

    def prediction_hash(model: RidgeArtifact, prediction_rows: Sequence[RollingTargetRow]) -> str:
        return digest(
            [
                {
                    "target_row_key": row.key,
                    "prediction": _text(model.predict(row)),
                }
                for row in prediction_rows
            ]
        )

    model_a_baseline_hash = prediction_hash(model_a, ordered)
    model_a_mutated_hash = prediction_hash(model_a, mutated)
    model_b_baseline_hash = prediction_hash(model_b, ordered)
    model_b_mutated_hash = prediction_hash(model_b, mutated)
    return {
        "row_count": len(ordered),
        "mutated_weather_feature": weather_feature,
        "mutation_delta": _text(delta),
        "model_a_baseline_prediction_hash": model_a_baseline_hash,
        "model_a_mutated_weather_prediction_hash": model_a_mutated_hash,
        "model_b_baseline_prediction_hash": model_b_baseline_hash,
        "model_b_mutated_weather_prediction_hash": model_b_mutated_hash,
        "model_a_weather_invariance_pass": model_a_baseline_hash == model_a_mutated_hash,
        "model_b_weather_sensitivity_pass": model_b_baseline_hash != model_b_mutated_hash,
    }


def dataset_manifest(
    rows: Iterable[RollingTargetRow], *, source_dataset_hash: str
) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: row.key)
    payload = {
        "row_count": len(ordered),
        "target_row_identity": TARGET_ROW_IDENTITY,
        "rows_hash": digest([row.payload() for row in ordered]),
        "source_dataset_hash": source_dataset_hash,
        "weather_feature_policy_version": WEATHER_FEATURE_POLICY_VERSION,
        "feature_names_a": list(FEATURE_NAMES_A),
        "feature_names_b": list(FEATURE_NAMES_B),
        "duplicate_target_label_weighting_allowed": False,
    }
    return {**payload, "manifest_hash": digest(payload)}


def assert_feature_contract() -> None:
    if FEATURE_COUNT_A != 10 or FEATURE_COUNT_B != 28 or WEATHER_FEATURE_COUNT != 18:
        raise WeatherAwareBacktestError("FROZEN_FEATURE_COUNT_MISMATCH")
    if tuple(FEATURE_NAMES_B[:10]) != tuple(FEATURE_NAMES_A):
        raise WeatherAwareBacktestError("MODEL_A_B_BASE_FEATURE_SCHEMA_MISMATCH")
    if HORIZON_TARGET_TYPES != {
        "H1": "DAILY_VECTOR_LENGTH_1",
        "H7": "DAILY_VECTOR_LENGTH_7",
        "H15": "DAILY_VECTOR_LENGTH_15",
    }:
        raise WeatherAwareBacktestError("HORIZON_CONTRACT_MISMATCH")


__all__ = [
    "ALPHA",
    "BASE_FEATURES",
    "FEATURE_COUNT_A",
    "FEATURE_COUNT_B",
    "FEATURE_NAMES_A",
    "FEATURE_NAMES_B",
    "FORECAST_ORIGIN_POLICY",
    "HORIZON_TARGET_TYPES",
    "HORIZONS",
    "MODEL_A_S3",
    "MODEL_B1",
    "MODEL_FAMILY",
    "NONNEGATIVE_OUTPUT_CLIP",
    "PRIMARY_FEATURES",
    "RidgeArtifact",
    "RollingTargetRow",
    "SOLVER",
    "TARGET_GRANULARITY",
    "TARGET_LABEL",
    "TARGET_ROW_IDENTITY",
    "WEATHER_FEATURE_COUNT",
    "WEATHER_LANE",
    "WEATHER_SOURCE",
    "WeatherAwareBacktestError",
    "build_rolling_rows",
    "dataset_manifest",
    "feature_vector",
    "fit_ridge_artifact",
    "rows_with_known_labels",
    "score_predictions",
    "seal_predictions",
    "target_row_key",
    "weather_sensitivity",
    "weather_sensitivity_prediction_set",
]
