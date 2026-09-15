"""Train and score the frozen V0.5-S3 known-support no-weather baseline.

This runner deliberately consumes the reviewed S3 label ledger rather than raw
business workbooks.  It validates the corrected R3 support evidence first, freezes the
candidate definition before fitting, writes predictions before reading label
values for scoring, and keeps the two forward folds independent.  No weather
value is loaded as a feature and no full-season label is inferred.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import pickle
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from scripts.audit_v0_5_s3_training_eligibility_r1 import (
    SEASONS,
    build_daily_eligibility,
    build_source_calendar,
    build_support_count_evidence,
    build_window_rows,
    canonical_value_hash,
    dates_between,
    file_hash,
    load_inputs,
    read_json,
    season_window,
    write_json,
)

MODEL_ID = "NO_WEATHER_HGBR_DAILY_V1"
REFERENCE_ID = "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1"
FEATURE_NAMES = (
    "productive_area_mu",
    "business_season_day_index",
    "business_season_progress",
    "business_season_progress_sin",
    "business_season_progress_cos",
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
NUMBER_QUANTUM = Decimal("0.000000000001")
PI = math.pi

FOLD_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "fold_id": "A",
        "role": "SECONDARY_STABILITY_DIAGNOSTIC",
        "train_seasons": ("2023-2024",),
        "validation_seasons": ("2024-2025",),
        "expected_train_base_count": 9,
        "expected_validation_base_count": 25,
        "expected_intersection_base_count": 9,
        "expected_natural_oob_base_count": 16,
    },
    {
        "fold_id": "B",
        "role": "PRIMARY_FORWARD_VALIDATION",
        "train_seasons": ("2023-2024", "2024-2025"),
        "validation_seasons": ("2025-2026",),
        "expected_train_base_count": 25,
        "expected_validation_base_count": 39,
        "expected_intersection_base_count": 25,
        "expected_natural_oob_base_count": 14,
    },
)

SUPPORT_COUNTS: dict[str, dict[str, int]] = {
    "2023-2024": {"daily": 2106, "W7": 1728, "W15": 1620},
    "2024-2025": {"daily": 7025, "W7": 6300, "W15": 5875},
    "2025-2026": {"daily": 8892, "W7": 8346, "W15": 8034},
}


def canonical_number(value: Decimal | float | int) -> str:
    """Serialize finite numeric output with a fixed decimal representation."""

    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:  # pragma: no cover - Decimal gives the useful error
        raise ValueError("value must be finite") from exc
    if not decimal_value.is_finite():
        raise ValueError("value must be finite")
    return format(
        decimal_value.quantize(NUMBER_QUANTUM, rounding=ROUND_HALF_EVEN),
        "f",
    )


def metric_number(value: float) -> float:
    """Round only serialized metrics, never estimator features or targets."""

    if not math.isfinite(value):
        raise ValueError("metric must be finite")
    return float(canonical_number(value))


def feature_values(season: str, target_date: date, area_mu: Decimal) -> tuple[float, ...]:
    """Return the complete, future-label-free feature vector for one day."""

    start, end = season_window(season)
    if not start <= target_date <= end:
        raise ValueError(f"target date outside business season: {target_date}")
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
    )


def nonnegative_prediction(value: float) -> tuple[float, bool]:
    if not math.isfinite(value):
        raise ValueError("model prediction must be finite")
    if value < 0:
        return 0.0, True
    return value, False


def nearest_available_bin(target_bin: int, available_bins: Sequence[int]) -> int:
    if not available_bins:
        raise ValueError("reference profile has no trained bins")
    return min(available_bins, key=lambda candidate: (abs(candidate - target_bin), candidate))


def _row_date(row: Mapping[str, Any]) -> date:
    return date.fromisoformat(str(row["date"]))


def _base_area(bases: Mapping[str, Mapping[str, Any]], base_id: str) -> Decimal:
    if base_id not in bases:
        raise ValueError(f"unknown base in label data: {base_id}")
    value = Decimal(str(bases[base_id]["productive_area_mu"]))
    if not value.is_finite() or value <= 0:
        raise ValueError(f"invalid productive area for base: {base_id}")
    return value


def build_week_median_reference(
    train_rows: Sequence[Mapping[str, Any]],
    bases: Mapping[str, Mapping[str, Any]],
) -> dict[int, float]:
    """Build per-base 7-day-bin kg/mu means and take their base-equal median."""

    by_base_bin: dict[str, dict[int, list[float]]] = {}
    for row in train_rows:
        if not bool(row["label_known"]):
            continue
        base_id = str(row["base_id"])
        season = str(row["season"])
        day_index = (_row_date(row) - season_window(season)[0]).days
        bin_id = day_index // 7
        area = _base_area(bases, base_id)
        quantity = Decimal(str(row["observed_harvest_kg"]))
        if not quantity.is_finite() or quantity < 0:
            raise ValueError(f"invalid training quantity: {base_id} {row['date']}")
        by_base_bin.setdefault(base_id, {}).setdefault(bin_id, []).append(float(quantity / area))

    profile: dict[int, float] = {}
    all_bins = sorted({bin_id for values in by_base_bin.values() for bin_id in values})
    for bin_id in all_bins:
        per_base_means = [
            statistics.mean(values[bin_id]) for values in by_base_bin.values() if bin_id in values
        ]
        if per_base_means:
            profile[bin_id] = metric_number(statistics.median(per_base_means))
    if not profile:
        raise ValueError("no known training labels for reference profile")
    return profile


def reference_prediction(
    reference: Mapping[int, float], season: str, target_date: date, area_mu: Decimal
) -> float:
    day_index = (target_date - season_window(season)[0]).days
    target_bin = day_index // 7
    selected_bin = nearest_available_bin(target_bin, sorted(reference))
    return float(area_mu) * reference[selected_bin]


def split_base_ids(train_ids: set[str], validation_ids: set[str]) -> dict[str, list[str]]:
    return {
        "train": sorted(train_ids),
        "validation": sorted(validation_ids),
        "seen": sorted(train_ids & validation_ids),
        "natural_oob": sorted(validation_ids - train_ids),
    }


def window_peak(rows: Sequence[Mapping[str, Any]]) -> tuple[str, Decimal]:
    if not rows:
        raise ValueError("cannot find a peak in an empty window")
    return min(
        ((str(row["date"]), Decimal(str(row["value"]))) for row in rows),
        key=lambda item: (-item[1], item[0]),
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    path.chmod(0o600)


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.name: file_hash(path)
        for path in sorted(root.iterdir())
        if path.is_file() and path.name != "artifact-manifest.json"
    }


def _load_support_evidence(support_root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    replay = support_root / "replay-1"
    paths = {
        "artifact_manifest": replay / "artifact-manifest.json",
        "summary": replay / "summary.json",
        "support_counts": replay / "support-counts-by-season.json",
        "forward_folds": replay / "forward-fold-support.json",
    }
    expected = {
        "artifact_manifest": config["input_contract"]["r3_support_artifact_manifest_sha256"],
        "summary": config["input_contract"]["r3_support_summary_sha256"],
        "support_counts": config["input_contract"]["r3_support_counts_sha256"],
        "forward_folds": config["input_contract"]["r3_forward_fold_support_sha256"],
    }
    for role, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"missing R3 support evidence: {role}")
        actual = file_hash(path)
        if actual != expected[role]:
            raise ValueError(f"R3 support evidence hash mismatch: {role}")

    artifact_manifest = read_json(paths["artifact_manifest"])
    if not isinstance(artifact_manifest, dict):
        raise ValueError("R3 artifact manifest is not an object")
    for name, expected_hash in artifact_manifest.items():
        path = replay / str(name)
        if not path.is_file() or file_hash(path) != expected_hash:
            raise ValueError(f"R3 artifact manifest mismatch: {name}")

    summary = read_json(paths["summary"])
    support_counts = read_json(paths["support_counts"])
    forward_folds = read_json(paths["forward_folds"])
    aggregate = config["input_contract"]
    checks = {
        "daily_known_support_row_count": aggregate["known_support_row_count"],
        "daily_known_support_unique_base_count": aggregate["known_support_unique_base_count"],
        "daily_known_support_base_season_count": aggregate["known_support_base_season_count"],
        "W7_eligible_origin_count": aggregate["w7_origin_count"],
        "W7_eligible_unique_base_count": aggregate["w7_unique_base_count"],
        "W7_eligible_base_season_count": aggregate["w7_base_season_count"],
        "W15_eligible_origin_count": aggregate["w15_origin_count"],
        "W15_eligible_unique_base_count": aggregate["w15_unique_base_count"],
        "W15_eligible_base_season_count": aggregate["w15_base_season_count"],
    }
    if any(summary.get(field) != value for field, value in checks.items()):
        raise ValueError("R3 support summary count drift")
    if summary.get("current_base_registry_hash") != aggregate["registry_payload_hash"]:
        raise ValueError("R3 support registry hash drift")
    if support_counts.get("by_season") is None or forward_folds.get("folds") is None:
        raise ValueError("R3 support evidence is incomplete")
    scope = summary.get("known_support_scope")
    if not isinstance(scope, dict):
        raise ValueError("R3 support scope evidence is incomplete")
    if scope.get("active_registry_base_count") != 39:
        raise ValueError("R3 active registry base count drift")
    if scope.get("known_support_base_count") != aggregate["known_support_unique_base_count"]:
        raise ValueError("R3 known-support base count drift")
    if scope.get("known_support_ids_hash") != aggregate["known_support_base_ids_hash"]:
        raise ValueError("R3 known-support ID hash drift")
    if scope.get("yunnan_core_base_count") != aggregate["weather_scope_base_count"]:
        raise ValueError("R3 weather-scope base count drift")
    if scope.get("yunnan_core_ids_hash") != aggregate["weather_scope_base_ids_hash"]:
        raise ValueError("R3 weather-scope ID hash drift")
    for season, expected_counts in SUPPORT_COUNTS.items():
        season_counts = support_counts["by_season"][season]
        if season_counts["daily_known_support"]["row_or_origin_count"] != expected_counts["daily"]:
            raise ValueError(f"R3 daily support count drift: {season}")
        for kind in ("W7", "W15"):
            if season_counts[kind]["row_or_origin_count"] != expected_counts[kind]:
                raise ValueError(f"R3 {kind} support count drift: {season}")
    fold_b = next(
        (fold for fold in forward_folds["folds"] if fold.get("fold_id") == "B"),
        None,
    )
    if fold_b is None:
        raise ValueError("R3 Fold B support evidence is missing")
    fold_b_daily = fold_b["metrics"]["daily_known_support"]
    if (
        fold_b_daily.get("train_unique_base_count") != 25
        or fold_b_daily.get("validation_unique_base_count") != 39
        or fold_b_daily.get("train_validation_base_intersection_count") != 25
    ):
        raise ValueError("R3 Fold B support scope drift")
    return {
        "artifact_manifest": artifact_manifest,
        "summary": summary,
        "support_counts": support_counts,
        "forward_folds": forward_folds,
        "files": {role: file_hash(path) for role, path in paths.items()},
    }


def _load_label_inputs(
    config: Mapping[str, Any], registry_root: Path, weather_root: Path, support_root: Path
) -> dict[str, Any]:
    support = _load_support_evidence(support_root, config)
    inputs = load_inputs(dict(config), registry_root, weather_root)
    bases_by_id = {str(base["base_id"]): base for base in inputs["bases"]}
    source_calendars: dict[str, list[dict[str, Any]]] = {}
    daily_by_season: dict[str, list[dict[str, Any]]] = {}
    window_rows: list[dict[str, Any]] = []
    for season in SEASONS:
        source = inputs["source_specs"][season]
        source_start = date.fromisoformat(source["date_min"])
        source_end = date.fromisoformat(source["date_max"])
        calendar_rows = build_source_calendar(
            season, inputs["base_ids"], inputs["ledger_by_key"], source_start, source_end
        )
        source_calendars[season] = calendar_rows
        daily_by_season[season] = build_daily_eligibility(
            season,
            inputs["bases"],
            inputs["ledger_by_key"],
            calendar_rows,
            source_start,
            source_end,
        )
        window_rows.extend(build_window_rows(daily_by_season[season], season, 7))
        window_rows.extend(build_window_rows(daily_by_season[season], season, 15))

    rebuilt_counts = build_support_count_evidence(daily_by_season, window_rows)
    for season, expected in SUPPORT_COUNTS.items():
        actual = rebuilt_counts["by_season"][season]
        if actual["daily_known_support"]["row_or_origin_count"] != expected["daily"]:
            raise ValueError(f"daily support count drift: {season}")
        for kind in ("W7", "W15"):
            if actual[kind]["row_or_origin_count"] != expected[kind]:
                raise ValueError(f"{kind} support count drift: {season}")

    active_base_ids = set(inputs["base_ids"])
    known_base_ids = {
        str(row["base_id"])
        for season in SEASONS
        for row in daily_by_season[season]
        if row["label_known"]
    }
    weather_scope_ids = {
        base_id
        for base_id, base in bases_by_id.items()
        if base.get("region_scope") == "YUNNAN_CORE"
    }
    if known_base_ids != active_base_ids:
        raise ValueError("known-support IDs do not equal the corrected active registry IDs")
    if len(known_base_ids) != config["input_contract"]["known_support_unique_base_count"]:
        raise ValueError("known-support base count drift")
    if (
        canonical_value_hash(sorted(known_base_ids))
        != config["input_contract"]["known_support_base_ids_hash"]
    ):
        raise ValueError("known-support ID hash drift")
    if not weather_scope_ids <= known_base_ids:
        raise ValueError("weather scope contains a base without known support")
    if len(weather_scope_ids) != config["input_contract"]["weather_scope_base_count"]:
        raise ValueError("weather scope base count drift")
    if (
        canonical_value_hash(sorted(weather_scope_ids))
        != config["input_contract"]["weather_scope_base_ids_hash"]
    ):
        raise ValueError("weather scope ID hash drift")

    return {
        "inputs": inputs,
        "support": support,
        "bases_by_id": bases_by_id,
        "source_calendars": source_calendars,
        "daily_by_season": daily_by_season,
        "window_rows": window_rows,
        "known_base_ids": sorted(known_base_ids),
        "weather_scope_ids": sorted(weather_scope_ids),
        "rebuilt_support_counts": rebuilt_counts,
    }


def _known_rows(
    daily_by_season: Mapping[str, Sequence[Mapping[str, Any]]], seasons: Sequence[str]
) -> list[dict[str, Any]]:
    return [
        dict(row)
        for season in seasons
        for row in daily_by_season[season]
        if bool(row["label_known"])
    ]


def _all_rows(
    daily_by_season: Mapping[str, Sequence[Mapping[str, Any]]], seasons: Sequence[str]
) -> list[dict[str, Any]]:
    return [dict(row) for season in seasons for row in daily_by_season[season]]


def _row_set_hash(rows: Sequence[Mapping[str, Any]], include_label: bool) -> str:
    identities: list[dict[str, str]] = []
    for row in rows:
        item = {
            "base_id": str(row["base_id"]),
            "season": str(row["season"]),
            "date": str(row.get("date", row.get("target_date", ""))),
        }
        if include_label:
            item["observed_harvest_kg"] = str(row.get("observed_harvest_kg", ""))
        identities.append(item)
    return canonical_value_hash(sorted(identities, key=lambda value: tuple(value.values())))


def _fit_model(
    train_rows: Sequence[Mapping[str, Any]], bases: Mapping[str, Mapping[str, Any]]
) -> Any:
    matrix = np.asarray(
        [
            feature_values(
                str(row["season"]),
                _row_date(row),
                _base_area(bases, str(row["base_id"])),
            )
            for row in train_rows
        ],
        dtype=np.float64,
    )
    target = np.asarray(
        [float(Decimal(str(row["observed_harvest_kg"]))) for row in train_rows],
        dtype=np.float64,
    )
    if matrix.size == 0 or target.size == 0:
        raise ValueError("no known rows available for model fit")
    estimator = HistGradientBoostingRegressor(**MODEL_PARAMS)
    estimator.fit(matrix, target)
    return estimator


def _model_prediction(
    estimator: Any, season: str, target_date: date, area: Decimal
) -> tuple[float, bool]:
    values = np.asarray([feature_values(season, target_date, area)], dtype=np.float64)
    raw = float(estimator.predict(values)[0])
    return nonnegative_prediction(raw)


PREDICTION_FIELDS = (
    "fold_id",
    "model_id",
    "split_role",
    "base_id",
    "canonical_base_name",
    "season",
    "target_date",
    "business_season_day_index",
    "productive_area_mu",
    "label_state",
    "label_known",
    "raw_prediction_kg",
    "predicted_daily_kg",
    "negative_prediction_projected_to_zero",
)


def _prediction_rows(
    fold_id: str,
    model_id: str,
    validation_rows: Sequence[Mapping[str, Any]],
    validation_base_ids: Sequence[str],
    split: Mapping[str, Sequence[str]],
    bases: Mapping[str, Mapping[str, Any]],
    estimator: Any | None,
    reference: Mapping[int, float] | None,
) -> list[dict[str, str]]:
    rows_by_base: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in validation_rows:
        rows_by_base[str(row["base_id"])].append(row)
    seen = set(split["seen"])
    output: list[dict[str, str]] = []
    for base_id in sorted(validation_base_ids):
        base = bases[base_id]
        area = _base_area(bases, base_id)
        role = "SEEN" if base_id in seen else "NATURAL_OOB"
        ordered_rows = sorted(rows_by_base[base_id], key=lambda item: str(item["date"]))
        estimator_predictions: Sequence[float] | None = None
        if estimator is not None:
            matrix = np.asarray(
                [feature_values(str(row["season"]), _row_date(row), area) for row in ordered_rows],
                dtype=np.float64,
            )
            estimator_predictions = estimator.predict(matrix)
        for row_index, row in enumerate(ordered_rows):
            season = str(row["season"])
            target_date = _row_date(row)
            if estimator is not None:
                raw, projected = nonnegative_prediction(float(estimator_predictions[row_index]))
            elif reference is not None:
                raw = reference_prediction(reference, season, target_date, area)
                raw, projected = nonnegative_prediction(raw)
            else:  # pragma: no cover - callers must select exactly one source
                raise ValueError("prediction source is not configured")
            day_index = (target_date - season_window(season)[0]).days
            output.append(
                {
                    "fold_id": fold_id,
                    "model_id": model_id,
                    "split_role": role,
                    "base_id": base_id,
                    "canonical_base_name": str(base["canonical_base_name"]),
                    "season": season,
                    "target_date": target_date.isoformat(),
                    "business_season_day_index": canonical_number(day_index),
                    "productive_area_mu": canonical_number(area),
                    "label_state": str(row["label_state"]),
                    "label_known": str(bool(row["label_known"])),
                    "raw_prediction_kg": canonical_number(raw),
                    "predicted_daily_kg": canonical_number(max(0.0, raw)),
                    "negative_prediction_projected_to_zero": str(projected),
                }
            )
    return output


def _prediction_label_join(
    prediction_rows: Sequence[Mapping[str, str]],
    daily_by_season: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, str]]:
    labels = {
        (str(row["base_id"]), str(row["season"]), str(row["date"])): row
        for season in SEASONS
        for row in daily_by_season[season]
    }
    scored: list[dict[str, str]] = []
    for row in prediction_rows:
        key = (row["base_id"], row["season"], row["target_date"])
        label = labels[key]
        scored.append(
            {
                **dict(row),
                "actual_kg": (
                    str(label["observed_harvest_kg"]) if bool(label["label_known"]) else ""
                ),
            }
        )
    return scored


def _mean_or_none(values: Sequence[float]) -> float | None:
    return metric_number(statistics.mean(values)) if values else None


def _wape_or_none(abs_errors: Sequence[float], actuals: Sequence[float]) -> float | None:
    denominator = sum(actuals)
    if denominator <= 0:
        return None
    return metric_number(sum(abs_errors) / denominator)


def _daily_metrics(
    rows: Sequence[Mapping[str, str]], source_id: str, base_ids: set[str]
) -> dict[str, Any]:
    known = [
        row
        for row in rows
        if row["model_id"] == source_id
        and row["base_id"] in base_ids
        and row["label_known"] == "True"
    ]
    by_base: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in known:
        by_base[row["base_id"]].append(row)
    per_base_mae: list[float] = []
    per_base_wape: list[float] = []
    per_base_bias: list[float] = []
    abs_errors: list[float] = []
    actuals: list[float] = []
    signed_errors: list[float] = []
    for base_rows in by_base.values():
        signed = [float(row["predicted_daily_kg"]) - float(row["actual_kg"]) for row in base_rows]
        errors = [abs(error) for error in signed]
        values = [float(row["actual_kg"]) for row in base_rows]
        per_base_mae.append(statistics.mean(errors))
        per_base_bias.append(statistics.mean(signed))
        base_wape = _wape_or_none(errors, values)
        if base_wape is not None:
            per_base_wape.append(base_wape)
        abs_errors.extend(errors)
        actuals.extend(values)
        signed_errors.extend(signed)
    return {
        "row_count": len(known),
        "unique_base_count": len(by_base),
        "macro_base_equal": {
            "mae_kg": _mean_or_none(per_base_mae),
            "wape": _mean_or_none(per_base_wape),
            "bias_kg": _mean_or_none(per_base_bias),
            "wape_computable_base_count": len(per_base_wape),
        },
        "row_pooled_diagnostic": {
            "mae_kg": _mean_or_none([sum(abs_errors) / len(abs_errors)]) if abs_errors else None,
            "wape": _wape_or_none(abs_errors, actuals),
            "bias_kg": _mean_or_none([sum(signed_errors) / len(signed_errors)])
            if signed_errors
            else None,
        },
    }


def _window_metric_rows(
    scored_rows: Sequence[Mapping[str, str]],
    source_id: str,
    fold_id: str,
    window_rows: Sequence[Mapping[str, Any]],
    validation_seasons: Sequence[str],
    validation_base_ids: set[str],
    window_days: int,
) -> list[dict[str, Any]]:
    predictions = {
        (row["base_id"], row["season"], row["target_date"]): float(row["predicted_daily_kg"])
        for row in scored_rows
        if row["model_id"] == source_id and row["fold_id"] == fold_id
    }
    actuals = {
        (row["base_id"], row["season"], row["target_date"]): float(row["actual_kg"])
        for row in scored_rows
        if row["model_id"] == source_id
        and row["fold_id"] == fold_id
        and row["label_known"] == "True"
    }
    output: list[dict[str, Any]] = []
    for window in window_rows:
        if (
            str(window["season"]) not in validation_seasons
            or str(window["base_id"]) not in validation_base_ids
            or int(window["window_days"]) != window_days
            or window["window_evaluation_status"] != "EXACT_COMPUTABLE"
        ):
            continue
        start = date.fromisoformat(str(window["window_start"]))
        end = date.fromisoformat(str(window["window_end"]))
        window_dates = dates_between(start, end)
        pred_values = [
            predictions[(str(window["base_id"]), str(window["season"]), day.isoformat())]
            for day in window_dates
        ]
        # The ledger's window total is not sufficient for a date peak.  The
        # caller supplies the actual daily values through the scored rows.
        actual_values = [
            actuals.get((str(window["base_id"]), str(window["season"]), day.isoformat()))
            for day in window_dates
        ]
        if any(value is None for value in actual_values):
            raise ValueError("complete window has no complete scored label join")
        actual_values = [float(value) for value in actual_values if value is not None]
        actual_peak_date, actual_peak_value = window_peak(
            [
                {"date": day.isoformat(), "value": canonical_number(value)}
                for day, value in zip(window_dates, actual_values, strict=True)
            ]
        )
        predicted_peak_date, predicted_peak_value = window_peak(
            [
                {"date": day.isoformat(), "value": canonical_number(value)}
                for day, value in zip(window_dates, pred_values, strict=True)
            ]
        )
        output.append(
            {
                "base_id": str(window["base_id"]),
                "season": str(window["season"]),
                "origin_date": str(window["origin_date"]),
                "window_days": window_days,
                "actual_total_kg": sum(actual_values),
                "predicted_total_kg": sum(pred_values),
                "actual_peak_date": actual_peak_date,
                "predicted_peak_date": predicted_peak_date,
                "actual_peak_kg": float(actual_peak_value),
                "predicted_peak_kg": float(predicted_peak_value),
            }
        )
    return output


def _window_metrics(
    scored_rows: Sequence[Mapping[str, str]],
    source_id: str,
    fold_id: str,
    window_rows: Sequence[Mapping[str, Any]],
    validation_seasons: Sequence[str],
    validation_base_ids: set[str],
    window_days: int,
) -> dict[str, Any]:
    records = _window_metric_rows(
        scored_rows,
        source_id,
        fold_id,
        window_rows,
        validation_seasons,
        validation_base_ids,
        window_days,
    )
    by_base: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in records:
        by_base[str(row["base_id"])].append(row)
    total_mae: list[float] = []
    total_wape: list[float] = []
    peak_date_mae: list[float] = []
    peak_kg_wape: list[float] = []
    pooled_total_abs: list[float] = []
    pooled_total_actual: list[float] = []
    pooled_peak_abs: list[float] = []
    pooled_peak_actual: list[float] = []
    for base_records in by_base.values():
        total_errors = [
            abs(float(row["predicted_total_kg"]) - float(row["actual_total_kg"]))
            for row in base_records
        ]
        totals = [float(row["actual_total_kg"]) for row in base_records]
        dates_error = [
            abs(
                (
                    date.fromisoformat(str(row["predicted_peak_date"]))
                    - date.fromisoformat(str(row["actual_peak_date"]))
                ).days
            )
            for row in base_records
        ]
        peak_errors = [
            abs(float(row["predicted_peak_kg"]) - float(row["actual_peak_kg"]))
            for row in base_records
        ]
        peak_values = [float(row["actual_peak_kg"]) for row in base_records]
        total_mae.append(statistics.mean(total_errors))
        base_total_wape = _wape_or_none(total_errors, totals)
        if base_total_wape is not None:
            total_wape.append(base_total_wape)
        peak_date_mae.append(statistics.mean(dates_error))
        base_peak_wape = _wape_or_none(peak_errors, peak_values)
        if base_peak_wape is not None:
            peak_kg_wape.append(base_peak_wape)
        pooled_total_abs.extend(total_errors)
        pooled_total_actual.extend(totals)
        pooled_peak_abs.extend(peak_errors)
        pooled_peak_actual.extend(peak_values)
    return {
        "origin_count": len(records),
        "unique_base_count": len(by_base),
        "macro_base_equal": {
            "total_mae_kg": _mean_or_none(total_mae),
            "total_wape": _mean_or_none(total_wape),
            "peak_date_mae_days": _mean_or_none(peak_date_mae),
            "peak_kg_wape": _mean_or_none(peak_kg_wape),
            "wape_computable_base_count": len(total_wape),
            "peak_kg_wape_computable_base_count": len(peak_kg_wape),
        },
        "row_pooled_diagnostic": {
            "total_wape": _wape_or_none(pooled_total_abs, pooled_total_actual),
            "peak_kg_wape": _wape_or_none(pooled_peak_abs, pooled_peak_actual),
        },
        "window_semantics": f"D_PLUS_1_THROUGH_D_PLUS_{window_days}",
        "tie_break": "EARLIEST_DATE",
    }


def _evaluate_source(
    scored_rows: Sequence[Mapping[str, str]],
    source_id: str,
    fold: Mapping[str, Any],
    split: Mapping[str, Sequence[str]],
    window_rows: Sequence[Mapping[str, Any]],
    weather_scope_ids: set[str],
) -> dict[str, Any]:
    validation_seasons = tuple(str(value) for value in fold["validation_seasons"])
    validation_base_ids = {
        row["base_id"]
        for row in scored_rows
        if (
            row["model_id"] == source_id
            and row["fold_id"] == fold["fold_id"]
            and row["label_known"] == "True"
        )
    }
    subsets = {
        "all": set(validation_base_ids),
        "seen": set(split["seen"]),
        "natural_oob": set(split["natural_oob"]),
        "common_weather_scope": set(validation_base_ids) & weather_scope_ids,
    }
    result: dict[str, Any] = {}
    for name, base_ids in subsets.items():
        result[name] = {
            "base_ids": sorted(base_ids),
            "daily": _daily_metrics(scored_rows, source_id, base_ids),
            "W7": _window_metrics(
                scored_rows,
                source_id,
                str(fold["fold_id"]),
                window_rows,
                validation_seasons,
                base_ids,
                7,
            ),
            "W15": _window_metrics(
                scored_rows,
                source_id,
                str(fold["fold_id"]),
                window_rows,
                validation_seasons,
                base_ids,
                15,
            ),
        }
    return result


def _fold_support_manifest(
    fold: Mapping[str, Any],
    daily_by_season: Mapping[str, Sequence[Mapping[str, Any]]],
    window_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    train_rows = _known_rows(daily_by_season, fold["train_seasons"])
    validation_rows = _known_rows(daily_by_season, fold["validation_seasons"])
    train_ids = {str(row["base_id"]) for row in train_rows}
    validation_ids = {str(row["base_id"]) for row in validation_rows}
    split = split_base_ids(train_ids, validation_ids)
    if len(train_ids) != fold["expected_train_base_count"]:
        raise ValueError(f"{fold['fold_id']} training base gate failed")
    if len(validation_ids) != fold["expected_validation_base_count"]:
        raise ValueError(f"{fold['fold_id']} validation base gate failed")
    if len(split["seen"]) != fold["expected_intersection_base_count"]:
        raise ValueError(f"{fold['fold_id']} intersection base gate failed")
    if len(split["natural_oob"]) != fold["expected_natural_oob_base_count"]:
        raise ValueError(f"{fold['fold_id']} natural OOB base gate failed")
    support: dict[str, Any] = {
        "fold_id": fold["fold_id"],
        "role": fold["role"],
        "train_seasons": list(fold["train_seasons"]),
        "validation_seasons": list(fold["validation_seasons"]),
        "train_known_row_count": len(train_rows),
        "validation_known_row_count": len(validation_rows),
        "train_unique_base_count": len(train_ids),
        "validation_unique_base_count": len(validation_ids),
        "train_unique_base_season_count": len(
            {f"{row['base_id']}|{row['season']}" for row in train_rows}
        ),
        "validation_unique_base_season_count": len(
            {f"{row['base_id']}|{row['season']}" for row in validation_rows}
        ),
        "train_validation_base_intersection_count": len(split["seen"]),
        "natural_oob_base_count": len(split["natural_oob"]),
        "train_base_ids_hash": canonical_value_hash(split["train"]),
        "validation_base_ids_hash": canonical_value_hash(split["validation"]),
        "train_validation_base_intersection_ids_hash": canonical_value_hash(split["seen"]),
        "natural_oob_base_ids_hash": canonical_value_hash(split["natural_oob"]),
        "train_row_set_hash": _row_set_hash(train_rows, include_label=True),
        "validation_row_set_identity_hash": _row_set_hash(validation_rows, include_label=False),
        "W7_validation_origin_count": sum(
            str(row["season"]) in fold["validation_seasons"]
            and row["base_id"] in validation_ids
            and int(row["window_days"]) == 7
            and row["window_evaluation_status"] == "EXACT_COMPUTABLE"
            for row in window_rows
        ),
        "W15_validation_origin_count": sum(
            str(row["season"]) in fold["validation_seasons"]
            and row["base_id"] in validation_ids
            and int(row["window_days"]) == 15
            and row["window_evaluation_status"] == "EXACT_COMPUTABLE"
            for row in window_rows
        ),
    }
    return support, train_rows, validation_rows


def _candidate_manifest(
    config: Mapping[str, Any],
    data: Mapping[str, Any],
    fold_support: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    inputs = data["inputs"]
    return {
        "task_id": config["task_id"],
        "phase": config["phase"],
        "candidate_freeze_status": "FROZEN_BEFORE_FIT_AND_EVALUATION",
        "model": config["model"],
        "features": config["features"],
        "reference": config["reference"],
        "folds": list(fold_support),
        "input_file_hashes": inputs["files"],
        "r3_support_file_hashes": data["support"]["files"],
        "registry_payload_hash": inputs["registry"]["hash"],
        "known_support_base_ids_hash": canonical_value_hash(data["known_base_ids"]),
        "weather_scope_base_ids_hash": canonical_value_hash(data["weather_scope_ids"]),
        "weather_values_used_as_features": False,
        "validation_label_values_in_candidate_manifest": False,
    }


def _validate_frozen_config(config: Mapping[str, Any]) -> None:
    """Reject configuration drift instead of silently changing the experiment."""

    model = config.get("model")
    if not isinstance(model, Mapping) or model.get("model_id") != MODEL_ID:
        raise ValueError("frozen S3 model configuration drift")
    for name, expected in MODEL_PARAMS.items():
        if model.get(name) != expected:
            raise ValueError(f"frozen S3 model parameter drift: {name}")
    if model.get("known_labels_only") is not True:
        raise ValueError("S3 model must use known labels only")
    features = config.get("features")
    if (
        not isinstance(features, Mapping)
        or tuple(features.get("feature_names", ())) != FEATURE_NAMES
    ):
        raise ValueError("frozen S3 feature configuration drift")
    if (
        features.get("weather_features") is not False
        or features.get("future_target_features") is not False
    ):
        raise ValueError("S3 feature boundary drift")
    reference = config.get("reference")
    if not isinstance(reference, Mapping) or reference.get("reference_id") != REFERENCE_ID:
        raise ValueError("frozen S3 reference configuration drift")
    folds = config.get("folds")
    expected_folds = [
        {
            **dict(fold),
            "train_seasons": list(fold["train_seasons"]),
            "validation_seasons": list(fold["validation_seasons"]),
        }
        for fold in FOLD_DEFINITIONS
    ]
    if folds != expected_folds:
        raise ValueError("frozen S3 fold configuration drift")
    authorization = config.get("authorization")
    if not isinstance(authorization, Mapping):
        raise ValueError("missing S3 authorization block")
    if authorization.get("known_support_daily_model_training") is not True:
        raise ValueError("known-support daily training is not authorized")
    for key in (
        "full_season_total_or_yield_model",
        "weather_features",
        "weather_model_training",
        "climate_zone_features",
        "s4_weather_ablation",
    ):
        if authorization.get(key) is not False:
            raise ValueError(f"S3 prohibited scope drift: {key}")


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
    if config.get("task_id") != "V0_5_S3_KNOWN_SUPPORT_NO_WEATHER_BASELINE_R1":
        raise ValueError("wrong S3 baseline configuration")
    _validate_frozen_config(config)
    data = _load_label_inputs(config, registry_root, weather_root, support_root)
    output.mkdir(parents=True, mode=0o700)

    fold_support: list[dict[str, Any]] = []
    fold_training: dict[str, dict[str, Any]] = {}
    fold_models: dict[str, Any] = {}
    fold_references: dict[str, dict[int, float]] = {}
    fold_predictions: list[dict[str, str]] = []
    fold_validation_rows: dict[str, list[dict[str, Any]]] = {}
    fold_splits: dict[str, dict[str, list[str]]] = {}
    for fold in FOLD_DEFINITIONS:
        support, train_rows, validation_rows = _fold_support_manifest(
            fold, data["daily_by_season"], data["window_rows"]
        )
        fold_support.append(support)
        split = split_base_ids(
            {str(row["base_id"]) for row in train_rows},
            {str(row["base_id"]) for row in validation_rows},
        )
        fold_splits[str(fold["fold_id"])] = split
        fold_training[str(fold["fold_id"])] = support
        fold_validation_rows[str(fold["fold_id"])] = validation_rows

    candidate = _candidate_manifest(config, data, fold_support)
    candidate_hash = canonical_value_hash(candidate)
    write_json(output / "candidate-manifest.json", candidate)

    write_json(output / "model-config.json", {"model_id": MODEL_ID, **config["model"]})
    write_json(
        output / "feature-schema.json",
        {
            "feature_names": list(FEATURE_NAMES),
            "feature_source": "calendar_and_requested_area_only",
            "weather_features": False,
            "future_target_features": False,
        },
    )
    write_json(
        output / "input-manifest.json",
        {
            "registry_payload_hash": data["inputs"]["registry"]["hash"],
            "input_file_hashes": data["inputs"]["files"],
            "r3_support_file_hashes": data["support"]["files"],
            "known_support_base_ids_hash": canonical_value_hash(data["known_base_ids"]),
            "weather_scope_base_ids_hash": canonical_value_hash(data["weather_scope_ids"]),
            "weather_values_used": False,
        },
    )

    for fold in FOLD_DEFINITIONS:
        fold_id = str(fold["fold_id"])
        train_rows = _known_rows(data["daily_by_season"], fold["train_seasons"])
        validation_rows = fold_validation_rows[fold_id]
        validation_base_ids = sorted({str(row["base_id"]) for row in validation_rows})
        estimator = _fit_model(train_rows, data["bases_by_id"])
        fold_models[fold_id] = estimator
        model_path = output / f"model-hgbr-{fold_id}.pkl"
        with model_path.open("wb") as stream:
            pickle.dump(estimator, stream, protocol=5)
        model_path.chmod(0o600)
        reference = build_week_median_reference(train_rows, data["bases_by_id"])
        fold_references[fold_id] = reference
        write_json(
            output / f"reference-{fold_id}.json",
            {
                "reference_id": REFERENCE_ID,
                "fold_id": fold_id,
                "profile_kg_per_mu_by_7_day_bin": {
                    str(key): canonical_number(value) for key, value in sorted(reference.items())
                },
                "available_bins": sorted(reference),
                "missing_bin_policy": config["reference"]["missing_bin_policy"],
                "train_row_set_hash": fold_training[fold_id]["train_row_set_hash"],
                "validation_labels_used": False,
            },
        )
        fold_predictions.extend(
            _prediction_rows(
                fold_id,
                MODEL_ID,
                validation_rows,
                validation_base_ids,
                fold_splits[fold_id],
                data["bases_by_id"],
                estimator,
                None,
            )
        )
        fold_predictions.extend(
            _prediction_rows(
                fold_id,
                REFERENCE_ID,
                validation_rows,
                validation_base_ids,
                fold_splits[fold_id],
                data["bases_by_id"],
                None,
                reference,
            )
        )

    fold_predictions.sort(
        key=lambda row: (
            row["fold_id"],
            row["model_id"],
            row["base_id"],
            row["target_date"],
        )
    )
    prediction_path = output / "predictions-before-scoring.csv"
    _write_csv(prediction_path, fold_predictions, PREDICTION_FIELDS)
    prediction_freeze = {
        "status": "PREDICTION_PHASE_CLOSED_BEFORE_LABEL_SCORING",
        "prediction_file": prediction_path.name,
        "prediction_file_sha256": file_hash(prediction_path),
        "prediction_row_count": len(fold_predictions),
        "candidate_manifest_hash": candidate_hash,
        "validation_label_values_in_prediction_phase": False,
    }
    write_json(output / "prediction-freeze.json", prediction_freeze)

    # The scoring phase reopens only the frozen prediction file and then joins
    # the reviewed validation ledger.  No estimator is called below this line.
    frozen_predictions = _read_csv(prediction_path)
    scored_predictions = _prediction_label_join(frozen_predictions, data["daily_by_season"])
    scored_predictions.sort(
        key=lambda row: (
            row["fold_id"],
            row["model_id"],
            row["base_id"],
            row["target_date"],
        )
    )
    scored_fields = tuple(PREDICTION_FIELDS) + ("actual_kg",)
    _write_csv(output / "scored-validation-predictions.csv", scored_predictions, scored_fields)

    metric_folds: dict[str, Any] = {}
    for fold, support in zip(FOLD_DEFINITIONS, fold_support, strict=True):
        fold_id = str(fold["fold_id"])
        sources = {
            MODEL_ID: _evaluate_source(
                scored_predictions,
                MODEL_ID,
                fold,
                fold_splits[fold_id],
                data["window_rows"],
                set(data["weather_scope_ids"]),
            ),
            REFERENCE_ID: _evaluate_source(
                scored_predictions,
                REFERENCE_ID,
                fold,
                fold_splits[fold_id],
                data["window_rows"],
                set(data["weather_scope_ids"]),
            ),
        }
        metric_folds[fold_id] = {
            "role": fold["role"],
            "support": support,
            "sources": sources,
        }

    label_rows = [
        row for season in SEASONS for row in data["daily_by_season"][season] if row["label_known"]
    ]
    metrics = {
        "task_id": config["task_id"],
        "model_id": MODEL_ID,
        "reference_id": REFERENCE_ID,
        "candidate_manifest_hash": candidate_hash,
        "prediction_file_sha256": file_hash(prediction_path),
        "scored_prediction_file_sha256": file_hash(output / "scored-validation-predictions.csv"),
        "validation_label_row_set_hash": _row_set_hash(label_rows, include_label=True),
        "folds": metric_folds,
        "aggregation": "BASE_EQUAL_MACRO_PRIMARY;_ROW_POOLED_DIAGNOSTIC",
        "validation_labels_used_after_prediction_freeze": True,
        "weather_features_used": False,
        "model_selection": "NO_NEW_MODEL_SELECTION;HGBR_AND_REFERENCE_REPORTED",
    }
    write_json(output / "metrics.json", metrics)
    write_json(
        output / "evaluation-manifest.json",
        {
            "prediction_freeze_hash": file_hash(output / "prediction-freeze.json"),
            "prediction_file_sha256": file_hash(prediction_path),
            "scored_prediction_file_sha256": file_hash(
                output / "scored-validation-predictions.csv"
            ),
            "validation_label_row_set_hash": metrics["validation_label_row_set_hash"],
            "validation_labels_read_after_prediction_freeze": True,
            "validation_labels_used_for_fit": False,
            "validation_labels_used_for_candidate_selection": False,
        },
    )
    write_json(
        output / "training-manifest.json",
        {"candidate_manifest_hash": candidate_hash, "folds": fold_training},
    )
    artifact_hashes = _file_hashes(output)
    write_json(output / "artifact-manifest.json", artifact_hashes)
    return {
        "candidate_manifest_hash": candidate_hash,
        "artifact_manifest_hash": file_hash(output / "artifact-manifest.json"),
        "artifact_hashes": artifact_hashes,
        "metrics": metrics,
        "fold_support": fold_support,
        "model_file_hashes": {
            fold_id: file_hash(output / f"model-hgbr-{fold_id}.pkl") for fold_id in ("A", "B")
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/v0_5_s3_known_support_no_weather_baseline_r1.json"),
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
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
