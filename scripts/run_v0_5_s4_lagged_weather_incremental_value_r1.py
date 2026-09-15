"""Run the frozen V0.5-S4 matched lagged-weather ablation.

The experiment uses one origin ``D`` to predict ``D+1`` through ``D+15``.
The control and weather candidates share the same origin and target rows,
folds, estimator parameters, and scoring code.  The weather candidate adds
only weather summaries ending at the origin date.  Validation label values are
joined only after the prediction file has been frozen.
"""

from __future__ import annotations

import argparse
import csv
import math
import pickle
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from scripts.audit_v0_5_s3_training_eligibility_r1 import (
    SEASONS,
    canonical_value_hash,
    dates_between,
    file_hash,
    read_json,
    season_window,
    write_json,
)
from scripts.run_v0_5_s3_known_support_no_weather_baseline_r1 import (
    _load_label_inputs,
    build_week_median_reference,
    reference_prediction,
)

CONTROL_MODEL_ID = "S4_MATCHED_NO_WEATHER_ORIGIN_HORIZON_HGBR_V1"
WEATHER_MODEL_ID = "S4_LAGGED_WEATHER_ORIGIN_HORIZON_HGBR_V1"
REFERENCE_ID = "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1"
S4_TASK_ID = "V0_5_S4_LAGGED_WEATHER_INCREMENTAL_VALUE_R1"
WEATHER_DAILY_HASH = "5ad49f11895c76e6aadd01d240ada3ba93d599d25138a2609887e527e58dad3b"
WEATHER_SCOPE_COUNT = 38
WEATHER_SCOPE_IDS_HASH = "79c210ffc5a837b93ae12dce6bc853b8f4f92d8ad91ce7e6a5cbff3bdb12149f"
LOCAL_TIMEZONE = "Asia/Shanghai"
HORIZONS = tuple(range(1, 16))
REPORT_HORIZONS = (1, 3, 7, 15)
WINDOWS = (7, 15)
NUMBER_QUANTUM = Decimal("0.000000000001")
PI = math.pi

STRUCTURAL_FEATURE_NAMES = (
    "productive_area_mu",
    "target_business_season_day_index",
    "target_business_season_progress",
    "target_business_season_progress_sin",
    "target_business_season_progress_cos",
    "forecast_horizon_days",
)
WEATHER_FEATURE_NAMES = (
    "tmean_7d_mean",
    "tmean_14d_mean",
    "tmin_7d_min",
    "tmin_14d_min",
    "tmax_7d_max",
    "tmax_14d_max",
    "precip_7d_sum",
    "precip_14d_sum",
    "solar_7d_sum",
    "solar_14d_sum",
    "wind_7d_mean",
    "wind_14d_mean",
)
MODEL_PARAMS: dict[str, Any] = {
    "loss": "squared_error",
    "learning_rate": 0.05,
    "max_iter": 300,
    "max_leaf_nodes": 31,
    "max_depth": 6,
    "min_samples_leaf": 10,
    "l2_regularization": 0.1,
    "early_stopping": False,
    "random_state": 20260915,
}
FOLD_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "fold_id": "A",
        "role": "SECONDARY_DIAGNOSTIC",
        "train_seasons": ("2023-2024",),
        "validation_seasons": ("2024-2025",),
    },
    {
        "fold_id": "B",
        "role": "PRIMARY_FORWARD_VALIDATION",
        "train_seasons": ("2023-2024", "2024-2025"),
        "validation_seasons": ("2025-2026",),
    },
)


def canonical_number(value: Decimal | float | int) -> str:
    """Serialize reported numbers without scientific notation."""

    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:  # pragma: no cover - Decimal supplies the context
        raise ValueError("value must be finite") from exc
    if not decimal_value.is_finite():
        raise ValueError("value must be finite")
    return format(
        decimal_value.quantize(NUMBER_QUANTUM, rounding=ROUND_HALF_EVEN),
        "f",
    )


def metric_number(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("metric must be finite")
    return float(canonical_number(value))


def _row_date(row: Mapping[str, Any]) -> date:
    return date.fromisoformat(str(row.get("date", row.get("target_date", ""))))


def _base_area(bases: Mapping[str, Mapping[str, Any]], base_id: str) -> Decimal:
    if base_id not in bases:
        raise ValueError(f"unknown base: {base_id}")
    area = Decimal(str(bases[base_id]["productive_area_mu"]))
    if not area.is_finite() or area <= 0:
        raise ValueError(f"invalid productive area: {base_id}")
    return area


def structural_features(
    season: str, target_date: date, area_mu: Decimal, horizon_days: int
) -> tuple[float, ...]:
    """Build only target-calendar and request-known structural features."""

    start, end = season_window(season)
    if not start <= target_date <= end:
        raise ValueError(f"target date outside business season: {target_date}")
    if horizon_days not in HORIZONS:
        raise ValueError(f"unsupported forecast horizon: {horizon_days}")
    if not area_mu.is_finite() or area_mu <= 0:
        raise ValueError("productive area must be positive and finite")
    season_span_days = (end - start).days
    day_index = (target_date - start).days
    progress = day_index / season_span_days if season_span_days else 0.0
    angle = 2.0 * PI * progress
    return (
        float(area_mu),
        float(day_index),
        progress,
        math.sin(angle),
        math.cos(angle),
        float(horizon_days),
    )


def _decimal_weather(row: Mapping[str, Any], field: str) -> Decimal:
    value = Decimal(str(row[field]))
    if not value.is_finite():
        raise ValueError(f"non-finite weather value: {field}")
    return value


def _weather_feature_vector(
    weather_by_date: Mapping[date, Mapping[str, Any]], base_id: str, origin_date: date
) -> tuple[float, ...]:
    dates_7 = [origin_date - timedelta(days=offset) for offset in range(6, -1, -1)]
    dates_14 = [origin_date - timedelta(days=offset) for offset in range(13, -1, -1)]
    if any(day not in weather_by_date for day in dates_14):
        raise ValueError(f"incomplete trailing weather history: {base_id} {origin_date}")

    def values(days: Sequence[date], field: str) -> list[Decimal]:
        return [_decimal_weather(weather_by_date[day], field) for day in days]

    tmean_7 = values(dates_7, "local_day_mean_temperature_c")
    tmean_14 = values(dates_14, "local_day_mean_temperature_c")
    tmin_7 = values(dates_7, "sampled_local_day_tmin_c")
    tmin_14 = values(dates_14, "sampled_local_day_tmin_c")
    tmax_7 = values(dates_7, "sampled_local_day_tmax_c")
    tmax_14 = values(dates_14, "sampled_local_day_tmax_c")
    precip_7 = values(dates_7, "local_day_precipitation_mm")
    precip_14 = values(dates_14, "local_day_precipitation_mm")
    solar_7 = values(dates_7, "local_day_solar_energy_j_m2")
    solar_14 = values(dates_14, "local_day_solar_energy_j_m2")
    wind_7 = values(dates_7, "local_day_mean_wind_speed_10m_m_s")
    wind_14 = values(dates_14, "local_day_mean_wind_speed_10m_m_s")
    for field, numbers in {
        "local_day_precipitation_mm": [*precip_7, *precip_14],
        "local_day_solar_energy_j_m2": [*solar_7, *solar_14],
    }.items():
        if any(number < 0 for number in numbers):
            raise ValueError(f"negative accepted weather value: {base_id} {field}")
    return tuple(
        float(value)
        for value in (
            sum(tmean_7, Decimal(0)) / Decimal(7),
            sum(tmean_14, Decimal(0)) / Decimal(14),
            min(tmin_7),
            min(tmin_14),
            max(tmax_7),
            max(tmax_14),
            sum(precip_7, Decimal(0)),
            sum(precip_14, Decimal(0)),
            sum(solar_7, Decimal(0)),
            sum(solar_14, Decimal(0)),
            sum(wind_7, Decimal(0)) / Decimal(7),
            sum(wind_14, Decimal(0)) / Decimal(14),
        )
    )


def build_feature_vector(
    season: str,
    target_date: date,
    area_mu: Decimal,
    horizon_days: int,
    base_id: str,
    origin_date: date,
    weather_by_base: Mapping[str, Mapping[date, Mapping[str, Any]]],
    with_weather: bool,
) -> tuple[float, ...]:
    structural = structural_features(season, target_date, area_mu, horizon_days)
    if not with_weather:
        return structural
    if base_id not in weather_by_base:
        raise ValueError(f"missing weather base: {base_id}")
    return structural + _weather_feature_vector(weather_by_base[base_id], base_id, origin_date)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = read_json_line(line, path, line_number)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row is not an object: {path.name}:{line_number}")
            rows.append(value)
    return rows


def read_json_line(line: str, path: Path, line_number: int) -> Any:
    import json

    try:
        return json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSONL: {path.name}:{line_number}") from exc


def load_accepted_weather(
    weather_root: Path, bases: Mapping[str, Mapping[str, Any]], expected_config: Mapping[str, Any]
) -> dict[str, Any]:
    """Load and validate the accepted daily ERA5-Land fact artifact."""

    manifest_path = weather_root / "dataset-manifest.json"
    daily_path = weather_root / "daily.jsonl"
    if not manifest_path.is_file() or not daily_path.is_file():
        raise FileNotFoundError("accepted weather daily artifact is incomplete")
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError("weather manifest is not an object")
    expected_hash = str(expected_config["daily_dataset_hash"])
    actual_file_hash = file_hash(daily_path)
    if actual_file_hash != expected_hash:
        raise ValueError("accepted weather daily artifact hash mismatch")
    required_manifest = {
        "daily_artifact_sha256": expected_hash,
        "daily_dataset_hash": expected_hash,
        "complete_base_count": WEATHER_SCOPE_COUNT,
        "missing_interval_count": 0,
        "duplicate_interval_count": 0,
        "nonfinite_value_count": 0,
        "provider_grid_selection_parity": "PASS_ALL_REQUESTS",
        "local_timezone": LOCAL_TIMEZONE,
        "source_product": "reanalysis-era5-land-timeseries",
        "source_product_kind": "CDS_OFFICIAL_POINT_TIMESERIES",
    }
    for key, value in required_manifest.items():
        if manifest.get(key) != value:
            raise ValueError(f"weather manifest drift: {key}")

    expected_ids = {
        base_id for base_id, base in bases.items() if base.get("region_scope") == "YUNNAN_CORE"
    }
    if len(expected_ids) != WEATHER_SCOPE_COUNT:
        raise ValueError("registry weather scope count drift")
    if canonical_value_hash(sorted(expected_ids)) != WEATHER_SCOPE_IDS_HASH:
        raise ValueError("registry weather scope identity drift")

    expected_dates = {day for season in SEASONS for day in dates_between(*season_window(season))}
    by_base: dict[str, dict[date, dict[str, Any]]] = defaultdict(dict)
    required_fields = (
        "local_day_mean_temperature_c",
        "sampled_local_day_tmin_c",
        "sampled_local_day_tmax_c",
        "local_day_precipitation_mm",
        "local_day_solar_energy_j_m2",
        "local_day_mean_wind_speed_10m_m_s",
    )
    for row in _read_jsonl(daily_path):
        base_id = str(row.get("base_id", ""))
        if base_id not in expected_ids:
            raise ValueError(f"weather row references unexpected base: {base_id}")
        day = date.fromisoformat(str(row.get("local_date", "")))
        if day not in expected_dates:
            raise ValueError(f"weather date outside authorized business scope: {day}")
        if day in by_base[base_id]:
            raise ValueError(f"duplicate weather daily row: {base_id} {day}")
        if row.get("hourly_sample_count") != 24:
            raise ValueError(f"incomplete local day: {base_id} {day}")
        if not row.get("row_hash"):
            raise ValueError(f"weather row hash missing: {base_id} {day}")
        for field in required_fields:
            value = _decimal_weather(row, field)
            if field in {"local_day_precipitation_mm", "local_day_solar_energy_j_m2"} and value < 0:
                raise ValueError(f"negative accepted weather value: {base_id} {day} {field}")
        by_base[base_id][day] = row
    for base_id in sorted(expected_ids):
        if set(by_base[base_id]) != expected_dates:
            raise ValueError(f"weather date coverage mismatch: {base_id}")
    return {
        "manifest": manifest,
        "daily_file_sha256": actual_file_hash,
        "by_base": {base_id: dict(values) for base_id, values in sorted(by_base.items())},
        "daily_row_count": sum(len(values) for values in by_base.values()),
        "expected_dates": sorted(expected_dates),
    }


def _origin_id(base_id: str, season: str, origin_date: date) -> str:
    return f"{base_id}|{season}|{origin_date.isoformat()}"


def _weather_history_complete(
    weather_by_base: Mapping[str, Mapping[date, Mapping[str, Any]]], base_id: str, origin_date: date
) -> bool:
    available = weather_by_base.get(base_id, {})
    return all(origin_date - timedelta(days=offset) in available for offset in range(13, -1, -1))


def build_origin_catalog(
    seasons: Sequence[str],
    base_ids: Sequence[str],
    weather_by_base: Mapping[str, Mapping[date, Mapping[str, Any]]],
    label_base_season_pairs: set[tuple[str, str]],
) -> dict[str, Any]:
    """Build deterministic origin populations and apply the common 14-day filter."""

    pre_by_window: dict[str, list[str]] = {"W7": [], "W15": []}
    post_by_window: dict[str, list[str]] = {"W7": [], "W15": []}
    all_origins: list[dict[str, Any]] = []
    for season in seasons:
        start, end = season_window(season)
        for base_id in sorted(base_ids):
            if (base_id, season) not in label_base_season_pairs:
                continue
            for window_days in WINDOWS:
                last_origin = end - timedelta(days=window_days)
                for origin_date in dates_between(start, last_origin):
                    identifier = _origin_id(base_id, season, origin_date)
                    pre_by_window[f"W{window_days}"].append(identifier)
                    if _weather_history_complete(weather_by_base, base_id, origin_date):
                        post_by_window[f"W{window_days}"].append(identifier)
            last_origin = end - timedelta(days=15)
            for origin_date in dates_between(start, last_origin):
                identifier = _origin_id(base_id, season, origin_date)
                if not _weather_history_complete(weather_by_base, base_id, origin_date):
                    continue
                weather_values = _weather_feature_vector(
                    weather_by_base[base_id], base_id, origin_date
                )
                all_origins.append(
                    {
                        "origin_id": identifier,
                        "base_id": base_id,
                        "season": season,
                        "origin_date": origin_date.isoformat(),
                        "weather_cutoff_date": origin_date.isoformat(),
                        "weather_feature_max_date": origin_date.isoformat(),
                        "weather_history_days": 14,
                        "weather_feature_vector": list(weather_values),
                    }
                )
    for values in pre_by_window.values():
        values.sort()
    for values in post_by_window.values():
        values.sort()
    all_origins.sort(key=lambda value: value["origin_id"])
    origin_ids = {str(origin["origin_id"]) for origin in all_origins}
    filtered_w15 = sorted(set(pre_by_window["W15"]) - origin_ids)
    filtered_w7 = sorted(set(pre_by_window["W7"]) - set(post_by_window["W7"]))
    return {
        "origins": all_origins,
        "pre_by_window": pre_by_window,
        "post_by_window": post_by_window,
        "filtered_w7": filtered_w7,
        "filtered_w15": filtered_w15,
        "experiment_origin_ids_hash": canonical_value_hash(
            [str(origin["origin_id"]) for origin in all_origins]
        ),
        "filtered_origin_ids_hash": canonical_value_hash(filtered_w15),
    }


def _daily_lookup(
    daily_by_season: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[tuple[str, str, date], Mapping[str, Any]]:
    output: dict[tuple[str, str, date], Mapping[str, Any]] = {}
    for season in SEASONS:
        for row in daily_by_season[season]:
            key = (str(row["base_id"]), str(row["season"]), _row_date(row))
            if key in output:
                raise ValueError(f"duplicate label row: {key}")
            output[key] = row
    return output


def _fold_origins(
    origins: Sequence[Mapping[str, Any]], seasons: Sequence[str]
) -> list[dict[str, Any]]:
    selected = [dict(origin) for origin in origins if str(origin["season"]) in seasons]
    return sorted(selected, key=lambda value: str(value["origin_id"]))


def _training_samples(
    origins: Sequence[Mapping[str, Any]],
    label_lookup: Mapping[tuple[str, str, date], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for origin in origins:
        base_id = str(origin["base_id"])
        season = str(origin["season"])
        origin_date = date.fromisoformat(str(origin["origin_date"]))
        for horizon in HORIZONS:
            target_date = origin_date + timedelta(days=horizon)
            label = label_lookup[(base_id, season, target_date)]
            if not bool(label["label_known"]):
                continue
            quantity = Decimal(str(label["observed_harvest_kg"]))
            if not quantity.is_finite() or quantity < 0:
                raise ValueError(f"invalid training quantity: {base_id} {season} {target_date}")
            samples.append(
                {
                    "base_id": base_id,
                    "season": season,
                    "origin_date": origin_date.isoformat(),
                    "target_date": target_date.isoformat(),
                    "forecast_horizon_days": horizon,
                    "target_key": f"{base_id}|{season}|{target_date.isoformat()}|{horizon}",
                    "observed_harvest_kg": quantity,
                }
            )
    return samples


def _fit_estimator(
    samples: Sequence[Mapping[str, Any]],
    bases: Mapping[str, Mapping[str, Any]],
    weather_by_base: Mapping[str, Mapping[date, Mapping[str, Any]]],
    with_weather: bool,
) -> HistGradientBoostingRegressor:
    matrix = np.asarray(
        [
            build_feature_vector(
                str(sample["season"]),
                date.fromisoformat(str(sample["target_date"])),
                _base_area(bases, str(sample["base_id"])),
                int(sample["forecast_horizon_days"]),
                str(sample["base_id"]),
                date.fromisoformat(str(sample["origin_date"])),
                weather_by_base,
                with_weather,
            )
            for sample in samples
        ],
        dtype=np.float64,
    )
    target = np.asarray([float(sample["observed_harvest_kg"]) for sample in samples])
    if matrix.size == 0 or target.size == 0:
        raise ValueError("no known training samples after origin filtering")
    estimator = HistGradientBoostingRegressor(**MODEL_PARAMS)
    estimator.fit(matrix, target)
    return estimator


def nonnegative_prediction(value: float) -> tuple[float, bool]:
    if not math.isfinite(value):
        raise ValueError("model prediction must be finite")
    if value < 0:
        return 0.0, True
    return value, False


PREDICTION_FIELDS = (
    "fold_id",
    "model_id",
    "split_role",
    "base_id",
    "season",
    "origin_id",
    "origin_date",
    "target_date",
    "forecast_horizon_days",
    "productive_area_mu",
    "weather_cutoff_date",
    "weather_feature_max_date",
    "raw_prediction_kg",
    "predicted_daily_kg",
    "negative_prediction_projected_to_zero",
)


def _predict_for_origins(
    fold_id: str,
    split_role: str,
    model_id: str,
    origins: Sequence[Mapping[str, Any]],
    bases: Mapping[str, Mapping[str, Any]],
    weather_by_base: Mapping[str, Mapping[date, Mapping[str, Any]]],
    estimator: HistGradientBoostingRegressor | None,
    reference: Mapping[int, float] | None,
    with_weather: bool,
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for origin in origins:
        base_id = str(origin["base_id"])
        season = str(origin["season"])
        origin_date = date.fromisoformat(str(origin["origin_date"]))
        area = _base_area(bases, base_id)
        feature_rows = [
            build_feature_vector(
                season,
                origin_date + timedelta(days=horizon),
                area,
                horizon,
                base_id,
                origin_date,
                weather_by_base,
                with_weather,
            )
            for horizon in HORIZONS
        ]
        estimator_values: Sequence[float] | None = None
        if estimator is not None:
            estimator_values = estimator.predict(np.asarray(feature_rows, dtype=np.float64))
        for index, horizon in enumerate(HORIZONS):
            target_date = origin_date + timedelta(days=horizon)
            if estimator is not None:
                if estimator_values is None:  # pragma: no cover - set with estimator above
                    raise ValueError("estimator predictions are missing")
                raw, projected = nonnegative_prediction(float(estimator_values[index]))
            elif reference is not None:
                raw, projected = nonnegative_prediction(
                    reference_prediction(reference, season, target_date, area)
                )
            else:  # pragma: no cover - guarded by call sites
                raise ValueError("prediction source is not configured")
            output.append(
                {
                    "fold_id": fold_id,
                    "model_id": model_id,
                    "split_role": split_role,
                    "base_id": base_id,
                    "season": season,
                    "origin_id": str(origin["origin_id"]),
                    "origin_date": origin_date.isoformat(),
                    "target_date": target_date.isoformat(),
                    "forecast_horizon_days": str(horizon),
                    "productive_area_mu": canonical_number(area),
                    "weather_cutoff_date": origin_date.isoformat(),
                    "weather_feature_max_date": origin_date.isoformat(),
                    "raw_prediction_kg": canonical_number(raw),
                    "predicted_daily_kg": canonical_number(max(0.0, raw)),
                    "negative_prediction_projected_to_zero": str(projected),
                }
            )
    return output


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    path.chmod(0o600)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _row_identity_hash(rows: Sequence[Mapping[str, Any]]) -> str:
    identities = [
        {
            "base_id": str(row["base_id"]),
            "season": str(row["season"]),
            "origin_id": str(
                row.get(
                    "origin_id",
                    f"{row['base_id']}|{row['season']}|{row['origin_date']}",
                )
            ),
            "target_date": str(row["target_date"]),
            "forecast_horizon_days": str(row["forecast_horizon_days"]),
        }
        for row in rows
    ]
    return str(canonical_value_hash(sorted(identities, key=lambda item: tuple(item.values()))))


def _join_validation_labels(
    prediction_rows: Sequence[Mapping[str, str]],
    label_lookup: Mapping[tuple[str, str, date], Mapping[str, Any]],
) -> list[dict[str, str]]:
    scored: list[dict[str, str]] = []
    for prediction in prediction_rows:
        key = (
            str(prediction["base_id"]),
            str(prediction["season"]),
            date.fromisoformat(str(prediction["target_date"])),
        )
        label = label_lookup[key]
        known = bool(label["label_known"])
        scored.append(
            {
                **dict(prediction),
                "target_label_known": str(known),
                "actual_kg": str(label["observed_harvest_kg"]) if known else "",
            }
        )
    return scored


def _mean_or_none(values: Sequence[float]) -> float | None:
    return metric_number(statistics.mean(values)) if values else None


def _wape(abs_errors: Sequence[float], actuals: Sequence[float]) -> float | None:
    denominator = sum(actuals)
    return metric_number(sum(abs_errors) / denominator) if denominator > 0 else None


def _subset_rows(
    rows: Sequence[Mapping[str, str]],
    model_id: str,
    fold_id: str,
    base_ids: set[str],
    horizon: int | None = None,
) -> list[Mapping[str, str]]:
    return [
        row
        for row in rows
        if row["model_id"] == model_id
        and row["fold_id"] == fold_id
        and row["base_id"] in base_ids
        and row["target_label_known"] == "True"
        and (horizon is None or int(row["forecast_horizon_days"]) == horizon)
    ]


def daily_metrics(
    rows: Sequence[Mapping[str, str]],
    model_id: str,
    fold_id: str,
    base_ids: set[str],
    horizon: int | None = None,
) -> dict[str, Any]:
    known = _subset_rows(rows, model_id, fold_id, base_ids, horizon)
    by_base: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in known:
        by_base[row["base_id"]].append(row)
    per_base_mae: list[float] = []
    per_base_wape: list[float] = []
    per_base_bias: list[float] = []
    pooled_abs: list[float] = []
    pooled_actual: list[float] = []
    pooled_signed: list[float] = []
    for base_rows in by_base.values():
        signed = [float(row["predicted_daily_kg"]) - float(row["actual_kg"]) for row in base_rows]
        errors = [abs(value) for value in signed]
        actuals = [float(row["actual_kg"]) for row in base_rows]
        per_base_mae.append(statistics.mean(errors))
        per_base_bias.append(statistics.mean(signed))
        base_wape = _wape(errors, actuals)
        if base_wape is not None:
            per_base_wape.append(base_wape)
        pooled_abs.extend(errors)
        pooled_actual.extend(actuals)
        pooled_signed.extend(signed)
    return {
        "row_count": len(known),
        "origin_count": len({row["origin_id"] for row in known}),
        "unique_base_count": len(by_base),
        "macro_base_equal": {
            "mae_kg": _mean_or_none(per_base_mae),
            "wape": _mean_or_none(per_base_wape),
            "bias_kg": _mean_or_none(per_base_bias),
            "wape_computable_base_count": len(per_base_wape),
        },
        "row_pooled_diagnostic": {
            "mae_kg": _mean_or_none([sum(pooled_abs) / len(pooled_abs)]) if pooled_abs else None,
            "wape": _wape(pooled_abs, pooled_actual),
            "bias_kg": _mean_or_none([sum(pooled_signed) / len(pooled_signed)])
            if pooled_signed
            else None,
        },
    }


def _peak(rows: Sequence[Mapping[str, Any]]) -> tuple[str, float]:
    if not rows:
        raise ValueError("peak requires rows")
    selected = min(
        ((str(row["date"]), float(row["value"])) for row in rows),
        key=lambda item: (-item[1], item[0]),
    )
    return selected


def window_records(
    rows: Sequence[Mapping[str, str]],
    model_id: str,
    fold_id: str,
    base_ids: set[str],
    window_days: int,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        if row["model_id"] == model_id and row["fold_id"] == fold_id and row["base_id"] in base_ids:
            grouped[(row["base_id"], row["season"], row["origin_id"])].append(row)
    records: list[dict[str, Any]] = []
    for (base_id, season, origin_id), group in grouped.items():
        selected = {int(row["forecast_horizon_days"]): row for row in group}
        if any(
            horizon not in selected or selected[horizon]["target_label_known"] != "True"
            for horizon in range(1, window_days + 1)
        ):
            continue
        window = [selected[horizon] for horizon in range(1, window_days + 1)]
        actual_values = [float(row["actual_kg"]) for row in window]
        predicted_values = [float(row["predicted_daily_kg"]) for row in window]
        actual_peak_date, actual_peak_kg = _peak(
            [
                {"date": row["target_date"], "value": value}
                for row, value in zip(window, actual_values, strict=True)
            ]
        )
        predicted_peak_date, predicted_peak_kg = _peak(
            [
                {"date": row["target_date"], "value": value}
                for row, value in zip(window, predicted_values, strict=True)
            ]
        )
        records.append(
            {
                "base_id": base_id,
                "season": season,
                "origin_id": origin_id,
                "origin_date": group[0]["origin_date"],
                "window_days": window_days,
                "actual_total_kg": sum(actual_values),
                "predicted_total_kg": sum(predicted_values),
                "actual_peak_date": actual_peak_date,
                "predicted_peak_date": predicted_peak_date,
                "actual_peak_kg": actual_peak_kg,
                "predicted_peak_kg": predicted_peak_kg,
            }
        )
    return sorted(records, key=lambda row: (row["base_id"], row["origin_id"]))


def window_metrics(
    rows: Sequence[Mapping[str, str]],
    model_id: str,
    fold_id: str,
    base_ids: set[str],
    window_days: int,
) -> dict[str, Any]:
    records = window_records(rows, model_id, fold_id, base_ids, window_days)
    by_base: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        by_base[str(record["base_id"])].append(record)
    total_wape: list[float] = []
    peak_date_mae: list[float] = []
    peak_kg_wape: list[float] = []
    pooled_total_abs: list[float] = []
    pooled_total_actual: list[float] = []
    pooled_peak_abs: list[float] = []
    pooled_peak_actual: list[float] = []
    for base_records in by_base.values():
        total_errors = [
            abs(float(record["predicted_total_kg"]) - float(record["actual_total_kg"]))
            for record in base_records
        ]
        total_actuals = [float(record["actual_total_kg"]) for record in base_records]
        date_errors = [
            abs(
                date.fromisoformat(str(record["predicted_peak_date"]))
                - date.fromisoformat(str(record["actual_peak_date"]))
            ).days
            for record in base_records
        ]
        peak_errors = [
            abs(float(record["predicted_peak_kg"]) - float(record["actual_peak_kg"]))
            for record in base_records
        ]
        peak_actuals = [float(record["actual_peak_kg"]) for record in base_records]
        base_total_wape = _wape(total_errors, total_actuals)
        if base_total_wape is not None:
            total_wape.append(base_total_wape)
        peak_date_mae.append(statistics.mean(date_errors))
        base_peak_wape = _wape(peak_errors, peak_actuals)
        if base_peak_wape is not None:
            peak_kg_wape.append(base_peak_wape)
        pooled_total_abs.extend(total_errors)
        pooled_total_actual.extend(total_actuals)
        pooled_peak_abs.extend(peak_errors)
        pooled_peak_actual.extend(peak_actuals)
    return {
        "origin_count": len(records),
        "unique_base_count": len(by_base),
        "macro_base_equal": {
            "total_wape": _mean_or_none(total_wape),
            "peak_date_mae_days": _mean_or_none(peak_date_mae),
            "peak_kg_wape": _mean_or_none(peak_kg_wape),
            "total_wape_computable_base_count": len(total_wape),
            "peak_kg_wape_computable_base_count": len(peak_kg_wape),
        },
        "row_pooled_diagnostic": {
            "total_wape": _wape(pooled_total_abs, pooled_total_actual),
            "peak_kg_wape": _wape(pooled_peak_abs, pooled_peak_actual),
        },
        "semantics": f"D_PLUS_1_THROUGH_D_PLUS_{window_days}",
        "peak_tie_break": "EARLIEST_DATE",
    }


def _subset_definitions(
    train_base_ids: set[str], validation_base_ids: set[str]
) -> dict[str, set[str]]:
    return {
        "all_common_38": set(validation_base_ids),
        "seen_bases": train_base_ids & validation_base_ids,
        "natural_oob_bases": validation_base_ids - train_base_ids,
    }


def evaluate_source(
    scored_rows: Sequence[Mapping[str, str]],
    model_id: str,
    fold_id: str,
    subsets: Mapping[str, set[str]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for subset_name, base_ids in subsets.items():
        result[subset_name] = {
            "base_ids": sorted(base_ids),
            "daily": {
                "overall": daily_metrics(scored_rows, model_id, fold_id, base_ids),
                **{
                    f"H{horizon}": daily_metrics(scored_rows, model_id, fold_id, base_ids, horizon)
                    for horizon in REPORT_HORIZONS
                },
            },
            "W7": window_metrics(scored_rows, model_id, fold_id, base_ids, 7),
            "W15": window_metrics(scored_rows, model_id, fold_id, base_ids, 15),
        }
    return result


def _per_base_metric_values(
    scored_rows: Sequence[Mapping[str, str]],
    model_id: str,
    fold_id: str,
    base_ids: set[str],
) -> dict[str, dict[str, float]]:
    values: dict[str, dict[str, float]] = defaultdict(dict)
    for base_id in sorted(base_ids):
        daily = daily_metrics(scored_rows, model_id, fold_id, {base_id})
        daily_wape = daily["macro_base_equal"]["wape"]
        if daily_wape is not None:
            values[base_id]["daily_wape"] = float(daily_wape)
        for window_days in WINDOWS:
            window = window_metrics(scored_rows, model_id, fold_id, {base_id}, window_days)
            macro = window["macro_base_equal"]
            prefix = f"W{window_days}"
            for source_key, output_key in (
                ("total_wape", "total_wape"),
                ("peak_date_mae_days", "peak_date_mae_days"),
                ("peak_kg_wape", "peak_kg_wape"),
            ):
                value = macro[source_key]
                if value is not None:
                    values[base_id][f"{prefix}_{output_key}"] = float(value)
    return values


def build_weather_effects(
    scored_rows: Sequence[Mapping[str, str]],
    fold_id: str,
    base_ids: set[str],
) -> dict[str, Any]:
    control = _per_base_metric_values(scored_rows, CONTROL_MODEL_ID, fold_id, base_ids)
    weather = _per_base_metric_values(scored_rows, WEATHER_MODEL_ID, fold_id, base_ids)
    metric_names = sorted(
        {name for values in control.values() for name in values}
        | {name for values in weather.values() for name in values}
    )
    effects: dict[str, Any] = {}
    for metric_name in metric_names:
        deltas = [
            metric_number(weather[base_id][metric_name] - control[base_id][metric_name])
            for base_id in sorted(base_ids)
            if metric_name in control.get(base_id, {}) and metric_name in weather.get(base_id, {})
        ]
        if not deltas:
            continue
        effects[metric_name] = {
            "base_count": len(deltas),
            "improved_count": sum(delta < 0 for delta in deltas),
            "worsened_count": sum(delta > 0 for delta in deltas),
            "tied_count": sum(delta == 0 for delta in deltas),
            "median_base_delta": metric_number(statistics.median(deltas)),
            "deltas_by_base": {
                base_id: metric_number(
                    weather[base_id][metric_name] - control[base_id][metric_name]
                )
                for base_id in sorted(base_ids)
                if metric_name in control.get(base_id, {})
                and metric_name in weather.get(base_id, {})
            },
        }
        paired_base_ids = [
            base_id
            for base_id in sorted(base_ids)
            if metric_name in control.get(base_id, {}) and metric_name in weather.get(base_id, {})
        ]
        control_values = [control[base_id][metric_name] for base_id in paired_base_ids]
        weather_values = [weather[base_id][metric_name] for base_id in paired_base_ids]
        control_macro = statistics.mean(control_values)
        weather_macro = statistics.mean(weather_values)
        macro_delta = weather_macro - control_macro
        effects[metric_name]["control_macro"] = metric_number(control_macro)
        effects[metric_name]["weather_macro"] = metric_number(weather_macro)
        effects[metric_name]["macro_delta"] = metric_number(macro_delta)
        effects[metric_name]["macro_relative_delta"] = (
            metric_number(macro_delta / control_macro) if control_macro != 0 else None
        )
        relative: list[float] = []
        for base_id in sorted(base_ids):
            if metric_name not in control.get(base_id, {}) or metric_name not in weather.get(
                base_id, {}
            ):
                continue
            denominator = control[base_id][metric_name]
            if denominator != 0:
                relative.append((weather[base_id][metric_name] - denominator) / denominator)
        effects[metric_name]["median_base_relative_delta"] = (
            metric_number(statistics.median(relative)) if relative else None
        )
    return {
        "fold_id": fold_id,
        "aggregation": "BASE_EQUAL_MACRO",
        "metrics": effects,
    }


def split_base_ids(train_ids: set[str], validation_ids: set[str]) -> dict[str, list[str]]:
    return {
        "train": sorted(train_ids),
        "validation": sorted(validation_ids),
        "seen": sorted(train_ids & validation_ids),
        "natural_oob": sorted(validation_ids - train_ids),
    }


def _validate_config(
    config: Mapping[str, Any], s3_config: Mapping[str, Any], s3_config_hash: str
) -> None:
    if config.get("task_id") != S4_TASK_ID:
        raise ValueError("wrong S4 configuration")
    if config.get("phase") != "V0.5-S4-01-LAGGED-WEATHER-INCREMENTAL-VALUE":
        raise ValueError("S4 phase drift")
    s3_pin = config.get("s3_baseline_config")
    if not isinstance(s3_pin, Mapping) or s3_pin.get("sha256") != s3_config_hash:
        raise ValueError("S3 baseline configuration hash drift")
    if s3_config.get("task_id") != "V0_5_S3_KNOWN_SUPPORT_NO_WEATHER_BASELINE_R1":
        raise ValueError("wrong S3 baseline input")
    scope = config.get("scope")
    if not isinstance(scope, Mapping) or scope.get("base_count") != WEATHER_SCOPE_COUNT:
        raise ValueError("S4 weather scope count drift")
    if scope.get("base_ids_hash") != WEATHER_SCOPE_IDS_HASH:
        raise ValueError("S4 weather scope identity drift")
    weather = config.get("weather")
    if not isinstance(weather, Mapping) or weather.get("daily_dataset_hash") != WEATHER_DAILY_HASH:
        raise ValueError("S4 weather input hash drift")
    if weather.get("local_timezone") != LOCAL_TIMEZONE:
        raise ValueError("S4 timezone drift")
    if weather.get("origin_weather_cutoff") != "END_OF_LOCAL_DAY_D":
        raise ValueError("S4 origin cutoff drift")
    windows = weather.get("trailing_windows_days")
    if windows != {"7d": 7, "14d": 14}:
        raise ValueError("S4 trailing window drift")
    model = config.get("model")
    if not isinstance(model, Mapping):
        raise ValueError("S4 model block is missing")
    if (
        model.get("control_model_id") != CONTROL_MODEL_ID
        or model.get("weather_model_id") != WEATHER_MODEL_ID
    ):
        raise ValueError("S4 model IDs drift")
    for key, value in MODEL_PARAMS.items():
        if model.get(key) != value:
            raise ValueError(f"S4 model parameter drift: {key}")
    if (
        model.get("model_family") != "HistGradientBoostingRegressor"
        or model.get("loss") != "squared_error"
    ):
        raise ValueError("S4 estimator drift")
    features = config.get("features")
    if not isinstance(features, Mapping):
        raise ValueError("S4 feature block is missing")
    if tuple(features.get("structural_features", ())) != STRUCTURAL_FEATURE_NAMES:
        raise ValueError("S4 structural feature drift")
    if tuple(features.get("weather_features", ())) != WEATHER_FEATURE_NAMES:
        raise ValueError("S4 weather feature drift")
    for forbidden in ("gdd", "vpd", "et0", "rh_derived", "weather_feature_search"):
        if features.get(forbidden) is not False:
            raise ValueError(f"S4 prohibited feature scope drift: {forbidden}")
    folds = config.get("folds")
    expected_folds = [
        {
            "fold_id": fold["fold_id"],
            "role": fold["role"],
            "train_seasons": list(fold["train_seasons"]),
            "validation_seasons": list(fold["validation_seasons"]),
        }
        for fold in FOLD_DEFINITIONS
    ]
    if folds != expected_folds:
        raise ValueError("S4 fold definition drift")
    authorization = config.get("authorization")
    if not isinstance(authorization, Mapping):
        raise ValueError("S4 authorization block is missing")
    for key in (
        "future_actual_weather_used",
        "target_day_actual_weather_used",
        "d_plus_1_to_d_plus_15_weather_used",
        "strict_source_publication_pit_proven",
        "production_weather_gain_proven",
        "model_search",
        "model_tuning",
    ):
        if authorization.get(key) is not False:
            raise ValueError(f"S4 prohibited authorization drift: {key}")


def _fold_support(
    fold: Mapping[str, Any], origins: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, list[str]]]:
    train_origins = _fold_origins(origins, fold["train_seasons"])
    validation_origins = _fold_origins(origins, fold["validation_seasons"])
    train_ids = {str(origin["base_id"]) for origin in train_origins}
    validation_ids = {str(origin["base_id"]) for origin in validation_origins}
    split = split_base_ids(train_ids, validation_ids)
    support = {
        "fold_id": fold["fold_id"],
        "role": fold["role"],
        "train_seasons": list(fold["train_seasons"]),
        "validation_seasons": list(fold["validation_seasons"]),
        "train_origin_count": len(train_origins),
        "validation_origin_count": len(validation_origins),
        "train_unique_base_count": len(train_ids),
        "validation_unique_base_count": len(validation_ids),
        "train_validation_base_intersection_count": len(split["seen"]),
        "natural_oob_base_count": len(split["natural_oob"]),
        "train_base_ids_hash": canonical_value_hash(split["train"]),
        "validation_base_ids_hash": canonical_value_hash(split["validation"]),
        "train_validation_base_intersection_ids_hash": canonical_value_hash(split["seen"]),
        "natural_oob_base_ids_hash": canonical_value_hash(split["natural_oob"]),
        "train_origin_ids_hash": canonical_value_hash(
            [str(origin["origin_id"]) for origin in train_origins]
        ),
        "validation_origin_ids_hash": canonical_value_hash(
            [str(origin["origin_id"]) for origin in validation_origins]
        ),
    }
    return support, train_origins, validation_origins, split


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.name: file_hash(path)
        for path in sorted(root.iterdir())
        if path.is_file() and path.name != "artifact-manifest.json"
    }


def run_experiment(
    config_path: Path,
    registry_root: Path,
    weather_root: Path,
    support_root: Path,
    output: Path,
) -> dict[str, Any]:
    if output.exists():
        raise ValueError("output directory must be new and append-only")
    config = read_json(config_path)
    if not isinstance(config, dict):
        raise ValueError("S4 configuration is not an object")
    s3_config_path = Path(str(config["s3_baseline_config"]["path"]))
    if not s3_config_path.is_absolute():
        s3_config_path = Path.cwd() / s3_config_path
    s3_config_hash = file_hash(s3_config_path)
    s3_config = read_json(s3_config_path)
    if not isinstance(s3_config, dict):
        raise ValueError("S3 baseline configuration is not an object")
    _validate_config(config, s3_config, s3_config_hash)
    data = _load_label_inputs(s3_config, registry_root, weather_root, support_root)
    weather = load_accepted_weather(weather_root, data["bases_by_id"], config["weather"])
    weather_by_base = weather["by_base"]
    weather_scope_ids = set(str(value) for value in data["weather_scope_ids"])
    if len(weather_scope_ids) != WEATHER_SCOPE_COUNT:
        raise ValueError("S4 weather scope data count drift")
    label_base_season_pairs = {
        (str(row["base_id"]), str(row["season"]))
        for season in SEASONS
        for row in data["daily_by_season"][season]
        if bool(row["label_known"]) and str(row["base_id"]) in weather_scope_ids
    }
    origins = build_origin_catalog(
        SEASONS,
        sorted(weather_scope_ids),
        weather_by_base,
        label_base_season_pairs,
    )
    output.mkdir(parents=True, mode=0o700)
    label_lookup = _daily_lookup(data["daily_by_season"])

    fold_support: list[dict[str, Any]] = []
    fold_training: dict[str, Any] = {}
    fold_predictions: list[dict[str, str]] = []
    fold_context: dict[str, Any] = {}
    for fold in FOLD_DEFINITIONS:
        support, train_origins, validation_origins, split = _fold_support(fold, origins["origins"])
        train_samples = _training_samples(train_origins, label_lookup)
        support["train_sample_count"] = len(train_samples)
        support["train_sample_identity_hash"] = _row_identity_hash(train_samples)
        support["validation_prediction_row_count"] = len(validation_origins) * len(HORIZONS)
        fold_support.append(support)
        fold_training[str(fold["fold_id"])] = {
            **support,
            "train_label_values_used": True,
            "validation_label_values_used_for_fit": False,
        }
        fold_context[str(fold["fold_id"])] = {
            "fold": fold,
            "train_origins": train_origins,
            "validation_origins": validation_origins,
            "split": split,
            "train_samples": train_samples,
        }

    input_manifest = {
        "s3_baseline_config_sha256": s3_config_hash,
        "s3_baseline_input_file_hashes": data["inputs"]["files"],
        "s3_support_file_hashes": data["support"]["files"],
        "weather_manifest_sha256": file_hash(weather_root / "dataset-manifest.json"),
        "weather_daily_sha256": weather["daily_file_sha256"],
        "weather_daily_dataset_hash": config["weather"]["daily_dataset_hash"],
        "weather_scope_base_ids_hash": WEATHER_SCOPE_IDS_HASH,
        "weather_scope_base_count": WEATHER_SCOPE_COUNT,
    }
    origin_manifest = {
        "origin_semantics": "D_PREDICTS_D_PLUS_1_THROUGH_D_PLUS_15",
        "origin_weather_cutoff": "END_OF_LOCAL_DAY_D",
        "local_timezone": LOCAL_TIMEZONE,
        "pre_filter_origin_count": {
            key: len(values) for key, values in origins["pre_by_window"].items()
        },
        "post_weather_history_filter_origin_count": {
            key: len(values) for key, values in origins["post_by_window"].items()
        },
        "filtered_origin_count": {
            key: len(origins[f"filtered_{key.lower()}"]) for key in ("W7", "W15")
        },
        "filtered_origin_ids_hash": origins["filtered_origin_ids_hash"],
        "experiment_origin_count": len(origins["origins"]),
        "experiment_origin_ids_hash": origins["experiment_origin_ids_hash"],
        "origin_weather_history_days": 14,
        "target_horizons": list(HORIZONS),
        "weather_max_date_rule": "WEATHER_DATE_LE_ORIGIN_DATE",
    }
    feature_manifest = {
        "structural_features": list(STRUCTURAL_FEATURE_NAMES),
        "weather_features": list(WEATHER_FEATURE_NAMES),
        "control_features": list(STRUCTURAL_FEATURE_NAMES),
        "weather_candidate_features": list(STRUCTURAL_FEATURE_NAMES + WEATHER_FEATURE_NAMES),
        "weather_windows": {"7d": "D_MINUS_6_THROUGH_D", "14d": "D_MINUS_13_THROUGH_D"},
        "target": "observed_harvest_kg",
        "weather_actual_target_dates_used": False,
        "future_actual_weather_used": False,
        "gdd_generated": False,
        "vpd_generated": False,
        "et0_generated": False,
        "rh_derived": False,
    }
    candidate_manifest = {
        "task_id": S4_TASK_ID,
        "candidate_freeze_status": "FROZEN_BEFORE_FOLD_B_SCORE",
        "control_model_id": CONTROL_MODEL_ID,
        "weather_model_id": WEATHER_MODEL_ID,
        "reference_id": REFERENCE_ID,
        "model_params": MODEL_PARAMS,
        "folds": fold_support,
        "input_manifest": input_manifest,
        "origin_manifest": origin_manifest,
        "feature_manifest": feature_manifest,
        "validation_label_values_in_candidate_manifest": False,
        "validation_label_values_used_for_candidate_selection": False,
        "matched_control_weather_training_samples": True,
        "matched_control_weather_validation_origins": True,
    }
    candidate_hash = canonical_value_hash(candidate_manifest)
    write_json(output / "input-manifest.json", input_manifest)
    write_json(output / "origin-filter-manifest.json", origin_manifest)
    write_json(output / "feature-manifest.json", feature_manifest)
    write_json(output / "candidate-manifest.json", candidate_manifest)

    for fold in FOLD_DEFINITIONS:
        fold_id = str(fold["fold_id"])
        context = fold_context[fold_id]
        train_samples = context["train_samples"]
        control_estimator = _fit_estimator(
            train_samples, data["bases_by_id"], weather_by_base, False
        )
        weather_estimator = _fit_estimator(
            train_samples, data["bases_by_id"], weather_by_base, True
        )
        with (output / f"model-control-{fold_id}.pkl").open("wb") as stream:
            pickle.dump(control_estimator, stream, protocol=5)
        with (output / f"model-weather-{fold_id}.pkl").open("wb") as stream:
            pickle.dump(weather_estimator, stream, protocol=5)
        (output / f"model-control-{fold_id}.pkl").chmod(0o600)
        (output / f"model-weather-{fold_id}.pkl").chmod(0o600)
        reference_train_rows: list[dict[str, Any]] = []
        seen_target_keys: set[tuple[str, str, date]] = set()
        for sample in train_samples:
            key = (
                str(sample["base_id"]),
                str(sample["season"]),
                date.fromisoformat(str(sample["target_date"])),
            )
            if key in seen_target_keys:
                continue
            seen_target_keys.add(key)
            label = label_lookup[key]
            reference_train_rows.append(dict(label))
        reference = build_week_median_reference(reference_train_rows, data["bases_by_id"])
        write_json(
            output / f"reference-{fold_id}.json",
            {
                "reference_id": REFERENCE_ID,
                "fold_id": fold_id,
                "profile_kg_per_mu_by_7_day_bin": {
                    str(key): canonical_number(value) for key, value in sorted(reference.items())
                },
                "train_origin_ids_hash": fold_training[fold_id]["train_origin_ids_hash"],
                "validation_label_values_used": False,
            },
        )
        validation_origins = context["validation_origins"]
        split_role = "PRIMARY" if fold_id == "B" else "SECONDARY"
        fold_predictions.extend(
            _predict_for_origins(
                fold_id,
                split_role,
                CONTROL_MODEL_ID,
                validation_origins,
                data["bases_by_id"],
                weather_by_base,
                control_estimator,
                None,
                False,
            )
        )
        fold_predictions.extend(
            _predict_for_origins(
                fold_id,
                split_role,
                WEATHER_MODEL_ID,
                validation_origins,
                data["bases_by_id"],
                weather_by_base,
                weather_estimator,
                None,
                True,
            )
        )
        fold_predictions.extend(
            _predict_for_origins(
                fold_id,
                split_role,
                REFERENCE_ID,
                validation_origins,
                data["bases_by_id"],
                weather_by_base,
                None,
                reference,
                False,
            )
        )
    fold_predictions.sort(
        key=lambda row: (
            row["fold_id"],
            row["model_id"],
            row["base_id"],
            row["origin_date"],
            int(row["forecast_horizon_days"]),
        )
    )
    prediction_path = output / "predictions-before-scoring.csv"
    _write_csv(prediction_path, fold_predictions, PREDICTION_FIELDS)
    prediction_freeze = {
        "status": "PREDICTION_PHASE_CLOSED_BEFORE_VALIDATION_LABEL_JOIN",
        "prediction_file": prediction_path.name,
        "prediction_file_sha256": file_hash(prediction_path),
        "prediction_row_count": len(fold_predictions),
        "candidate_manifest_hash": candidate_hash,
        "validation_label_values_used_for_prediction": False,
        "validation_label_values_used_for_fit": False,
        "future_actual_weather_used": False,
        "weather_cutoff_rule_verified": True,
    }
    write_json(output / "prediction-freeze.json", prediction_freeze)

    frozen_predictions = _read_csv(prediction_path)
    scored_predictions = _join_validation_labels(frozen_predictions, label_lookup)
    scored_predictions.sort(
        key=lambda row: (
            row["fold_id"],
            row["model_id"],
            row["base_id"],
            row["origin_date"],
            int(row["forecast_horizon_days"]),
        )
    )
    scored_fields = PREDICTION_FIELDS + ("target_label_known", "actual_kg")
    _write_csv(output / "scored-validation-predictions.csv", scored_predictions, scored_fields)

    metric_folds: dict[str, Any] = {}
    effect_folds: dict[str, Any] = {}
    for fold in FOLD_DEFINITIONS:
        fold_id = str(fold["fold_id"])
        split = fold_context[fold_id]["split"]
        subsets = _subset_definitions(set(split["train"]), set(split["validation"]))
        metric_folds[fold_id] = {
            "role": fold["role"],
            "support": fold_training[fold_id],
            "control": evaluate_source(scored_predictions, CONTROL_MODEL_ID, fold_id, subsets),
            "weather": evaluate_source(scored_predictions, WEATHER_MODEL_ID, fold_id, subsets),
            "reference": evaluate_source(scored_predictions, REFERENCE_ID, fold_id, subsets),
        }
        effect_folds[fold_id] = build_weather_effects(
            scored_predictions, fold_id, subsets["all_common_38"]
        )
    validation_label_rows = [
        row for season in SEASONS for row in data["daily_by_season"][season] if row["label_known"]
    ]
    metrics = {
        "task_id": S4_TASK_ID,
        "control_model_id": CONTROL_MODEL_ID,
        "weather_model_id": WEATHER_MODEL_ID,
        "reference_id": REFERENCE_ID,
        "candidate_manifest_hash": candidate_hash,
        "prediction_file_sha256": file_hash(prediction_path),
        "scored_prediction_file_sha256": file_hash(output / "scored-validation-predictions.csv"),
        "validation_label_row_set_hash": canonical_value_hash(
            [
                {
                    "base_id": str(row["base_id"]),
                    "season": str(row["season"]),
                    "date": str(row["date"]),
                    "observed_harvest_kg": str(row["observed_harvest_kg"]),
                }
                for row in validation_label_rows
            ]
        ),
        "folds": metric_folds,
        "weather_effects": effect_folds,
        "aggregation": "BASE_EQUAL_MACRO_PRIMARY;ROW_POOLED_DIAGNOSTIC",
        "prediction_semantics": "D_PREDICTS_D_PLUS_1_THROUGH_D_PLUS_15",
        "validation_labels_used_after_prediction_freeze": True,
        "validation_labels_used_for_fit": False,
        "validation_labels_used_for_candidate_selection": False,
        "future_actual_weather_used": False,
        "strict_source_publication_pit_proven": False,
        "production_weather_gain_proven": False,
        "model_selection": "NO_NEW_MODEL_SELECTION;MATCHED_CONTROL_AND_WEATHER_REPORTED",
    }
    write_json(output / "metrics.json", metrics)
    write_json(
        output / "training-manifest.json",
        {
            "candidate_manifest_hash": candidate_hash,
            "model_params": MODEL_PARAMS,
            "folds": fold_training,
            "validation_label_values_used_for_fit": False,
        },
    )
    write_json(
        output / "evaluation-manifest.json",
        {
            "prediction_freeze_sha256": file_hash(output / "prediction-freeze.json"),
            "prediction_file_sha256": file_hash(prediction_path),
            "scored_prediction_file_sha256": metrics["scored_prediction_file_sha256"],
            "validation_label_row_set_hash": metrics["validation_label_row_set_hash"],
            "validation_labels_read_after_prediction_freeze": True,
            "validation_labels_used_for_fit": False,
            "validation_labels_used_for_candidate_selection": False,
        },
    )
    artifact_hashes = _file_hashes(output)
    write_json(output / "artifact-manifest.json", artifact_hashes)
    return {
        "task_id": S4_TASK_ID,
        "candidate_manifest_hash": candidate_hash,
        "artifact_manifest_sha256": file_hash(output / "artifact-manifest.json"),
        "artifact_hashes": artifact_hashes,
        "metrics": metrics,
        "fold_support": fold_support,
        "origin_manifest": origin_manifest,
        "daily_dataset_hash": WEATHER_DAILY_HASH,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/v0_5_s4_lagged_weather_incremental_value_r1.json"),
    )
    parser.add_argument("--registry-root", type=Path, required=True)
    parser.add_argument("--weather-root", type=Path, required=True)
    parser.add_argument("--support-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_experiment(
        args.config,
        args.registry_root,
        args.weather_root,
        args.support_root,
        args.output,
    )
    import json

    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
