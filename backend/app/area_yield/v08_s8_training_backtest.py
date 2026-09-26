"""Deterministic V0.8-S8 two-stage area-yield training and OOT scoring.

The training API accepts only the frozen training dataset and its daily curves.
OOT labels are loaded by the orchestration script only after predictions have
been serialized and sealed.  Row-level inputs and outputs remain private.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from typing import Any

QUANTUM = Decimal("0.000001")
TRAINING_SEASONS = ("2023-2024", "2024-2025")
OOT_SEASON = "2025-2026"
TARGET_START = date(2025, 7, 22)
TARGET_END = date(2026, 4, 15)
ACCEPTED_DAILY_COMPLETENESS = frozenset({"COMPLETE_MAPPED_MEMBERS", "AUTHORIZED_ZERO"})


class S8BacktestError(ValueError):
    """Raised when a frozen S8 cohort or authority gate is not satisfied."""


def decimal_value(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise S8BacktestError(f"INVALID_DECIMAL:{field}") from exc
    if not result.is_finite():
        raise S8BacktestError(f"NONFINITE_DECIMAL:{field}")
    return result


def decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise S8BacktestError("NONFINITE_DECIMAL_OUTPUT")
    return format(value, "f")


def quantize_quantity(value: Decimal) -> Decimal:
    return value.quantize(QUANTUM, rounding=ROUND_HALF_EVEN)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_bytes(fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=list(fieldnames),
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_cell(row.get(key)) for key in fieldnames})
    return stream.getvalue().encode("utf-8")


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_private_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_bytes(payload)
    path.chmod(0o600)


def write_private_json(path: Path, value: Any) -> None:
    write_private_bytes(path, canonical_json_bytes(value) + b"\n")


def season_calendar(season: str) -> list[date]:
    if season == "2023-2024":
        start, end = date(2023, 7, 1), date(2024, 4, 15)
    elif season == "2024-2025":
        start, end = date(2024, 7, 1), date(2025, 4, 15)
    elif season == OOT_SEASON:
        start, end = TARGET_START, TARGET_END
    else:
        raise S8BacktestError(f"UNAUTHORIZED_SEASON:{season}")
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _is_true(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def _key(row: Mapping[str, Any]) -> tuple[str, str]:
    return str(row["base_id"]), str(row["season"])


def _stable_digest(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def validate_training_cohort(
    training_rows: Sequence[Mapping[str, Any]],
    oot_rows: Sequence[Mapping[str, Any]],
    *,
    expected_training_count: int = 37,
    expected_oot_count: int = 39,
) -> None:
    train_keys = [_key(row) for row in training_rows]
    oot_keys = [_key(row) for row in oot_rows]
    if (
        len(train_keys) != expected_training_count
        or len(set(train_keys)) != expected_training_count
    ):
        raise S8BacktestError("TRAINING_COHORT_MUST_BE_EXACTLY_37_UNIQUE_BASE_SEASONS")
    if len(oot_keys) != expected_oot_count or len(set(oot_keys)) != expected_oot_count:
        raise S8BacktestError("OOT_COHORT_MUST_BE_EXACTLY_39_UNIQUE_BASE_SEASONS")
    if set(train_keys) & set(oot_keys):
        raise S8BacktestError("TRAIN_OOT_BASE_SEASON_OVERLAP")
    if any(season not in TRAINING_SEASONS for _, season in train_keys):
        raise S8BacktestError("OOT_SEASON_FOUND_IN_TRAINING_ROWS")
    if any(season != OOT_SEASON for _, season in oot_keys):
        raise S8BacktestError("NON_OOT_SEASON_FOUND_IN_OOT_ROWS")
    if max(season for _, season in train_keys) >= OOT_SEASON:
        raise S8BacktestError("TRAINING_SEASON_NOT_BEFORE_OOT")


def _validate_training_rows(training_rows: Sequence[Mapping[str, Any]]) -> None:
    keys = [_key(row) for row in training_rows]
    if len(keys) != 37 or len(set(keys)) != 37:
        raise S8BacktestError("TRAINING_DATASET_ROW_COUNT_OR_DUPLICATE_KEY_INVALID")
    if any(row["season"] not in TRAINING_SEASONS for row in training_rows):
        raise S8BacktestError("OOT_LABEL_FORBIDDEN_IN_TRAINING_DATASET")
    season_counts = {
        season: sum(1 for row in training_rows if row["season"] == season)
        for season in TRAINING_SEASONS
    }
    if season_counts != {"2023-2024": 15, "2024-2025": 22}:
        raise S8BacktestError("TRAINING_SEASON_COUNTS_MISMATCH")
    if any(not _is_true(row.get("daily_curve_available")) for row in training_rows):
        raise S8BacktestError("TRAINING_DAILY_CURVE_MISSING")
    if any(
        "strict_training_eligible" in row and not _is_true(row["strict_training_eligible"])
        for row in training_rows
    ):
        raise S8BacktestError("BLOCKED_TRAINING_ROW_IN_COHORT")
    for row in training_rows:
        if decimal_value(row["area_mu"], "area_mu") <= 0:
            raise S8BacktestError("NONPOSITIVE_TRAINING_AREA")
        if decimal_value(row["season_total_quantity_kg"], "season_total") < 0:
            raise S8BacktestError("NEGATIVE_TRAINING_SEASON_TOTAL")


def validate_curve(
    rows: Sequence[Mapping[str, Any]],
    *,
    season: str,
    expected_total: Decimal | None = None,
) -> None:
    expected_days = season_calendar(season)
    parsed_days = [date.fromisoformat(str(row["date"])) for row in rows]
    if parsed_days != expected_days:
        raise S8BacktestError(f"DAILY_CURVE_NOT_COMPLETE_OR_CANONICALLY_SORTED:{season}")
    for row in rows:
        if not _is_true(row.get("authority_eligible_daily", True)):
            raise S8BacktestError("UNAUTHORIZED_DAILY_QUANTITY_IN_CURVE")
        completeness = str(
            row.get("new_completeness_status", row.get("daily_completeness_status", ""))
        )
        if completeness and completeness not in ACCEPTED_DAILY_COMPLETENESS:
            raise S8BacktestError(f"INCOMPLETE_DAILY_QUANTITY:{completeness}")
        quantity = decimal_value(
            row.get("new_quantity_kg", row.get("actual_quantity_kg")), "daily_quantity"
        )
        if quantity < 0:
            raise S8BacktestError("NEGATIVE_DAILY_QUANTITY")
    if expected_total is not None:
        actual_sum = sum(
            (
                decimal_value(
                    row.get("new_quantity_kg", row.get("actual_quantity_kg")), "daily_quantity"
                )
                for row in rows
            ),
            Decimal(0),
        )
        if actual_sum != expected_total:
            raise S8BacktestError("DAILY_SUM_SEASON_TOTAL_MISMATCH")


def fit_two_stage_model(
    training_rows: Sequence[Mapping[str, Any]],
    training_daily_rows: Sequence[Mapping[str, Any]],
    *,
    config_sha256: str,
    training_code_sha256: str,
    training_dataset_sha256: str,
    training_daily_sha256: str,
) -> dict[str, Any]:
    """Fit base-level mean yield and pooled calendar-day share from train only."""
    _validate_training_rows(training_rows)
    train_keys = {_key(row) for row in training_rows}
    curves: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in training_daily_rows:
        if str(row["season"]) not in TRAINING_SEASONS:
            raise S8BacktestError("OOT_DAILY_LABEL_FORBIDDEN_IN_TRAINING_CURVES")
        key = _key(row)
        if key not in train_keys:
            raise S8BacktestError("NON_ELIGIBLE_TRAINING_CURVE_ROW")
        curves[key].append(row)

    quantity_sum = Decimal(0)
    area_sum = Decimal(0)
    yields_by_base: dict[str, list[Decimal]] = defaultdict(list)
    for row in sorted(training_rows, key=lambda item: (str(item["season"]), str(item["base_id"]))):
        key = _key(row)
        area = decimal_value(row["area_mu"], "area_mu")
        total = decimal_value(row["season_total_quantity_kg"], "season_total")
        if area <= 0:
            raise S8BacktestError("NONPOSITIVE_TRAINING_AREA")
        curve = curves.get(key, [])
        validate_curve(curve, season=key[1], expected_total=total)
        with localcontext() as context:
            context.prec = 40
            yield_value = total / area
        yields_by_base[key[0]].append(yield_value)
        quantity_sum += total
        area_sum += area
    if set(curves) != train_keys:
        raise S8BacktestError("TRAINING_CURVE_COHORT_MISMATCH")
    if area_sum <= 0:
        raise S8BacktestError("ZERO_TRAINING_AREA_SUM")
    with localcontext() as context:
        context.prec = 40
        pooled_yield = quantity_sum / area_sum

    base_yields: dict[str, str] = {}
    for base_id, values in sorted(yields_by_base.items()):
        with localcontext() as context:
            context.prec = 40
            base_yields[base_id] = decimal_text(sum(values, Decimal(0)) / Decimal(len(values)))

    shares_by_month_day: dict[str, list[Decimal]] = defaultdict(list)
    for row in sorted(training_rows, key=lambda item: (str(item["season"]), str(item["base_id"]))):
        key = _key(row)
        total = decimal_value(row["season_total_quantity_kg"], "season_total")
        if total <= 0:
            raise S8BacktestError("ZERO_SEASON_TOTAL_CANNOT_DEFINE_NORMALIZED_SHAPE")
        with localcontext() as context:
            context.prec = 40
            for day_row in curves[key]:
                day = date.fromisoformat(str(day_row["date"]))
                quantity = decimal_value(day_row["new_quantity_kg"], "daily_quantity")
                shares_by_month_day[day.strftime("%m-%d")].append(quantity / total)

    target_days = season_calendar(OOT_SEASON)
    target_raw: list[Decimal] = []
    target_keys: list[str] = []
    with localcontext() as context:
        context.prec = 40
        for day in target_days:
            month_day = day.strftime("%m-%d")
            month_day_values = shares_by_month_day.get(month_day)
            if not month_day_values:
                raise S8BacktestError(f"TRAINING_PROFILE_DATE_MISSING:{month_day}")
            target_keys.append(month_day)
            target_raw.append(sum(month_day_values, Decimal(0)) / Decimal(len(month_day_values)))
        selected_sum = sum(target_raw, Decimal(0))
        if selected_sum <= 0:
            raise S8BacktestError("TRAINING_PROFILE_HAS_NO_TARGET_WINDOW_MASS")
        normalized_profile = [value / selected_sum for value in target_raw]
        normalized_profile[-1] = Decimal(1) - sum(normalized_profile[:-1], Decimal(0))
    with localcontext() as context:
        context.prec = 60
        normalized_sum = sum(normalized_profile, Decimal(0))
    if abs(normalized_sum - Decimal(1)) > Decimal("1e-30"):
        raise S8BacktestError("TRAINING_PROFILE_NORMALIZATION_FAILED")
    profile_by_month_day = {
        key: decimal_text(value) for key, value in zip(target_keys, normalized_profile, strict=True)
    }

    payload: dict[str, Any] = {
        "model_id": "V0_8_AREA_SCALED_BASE_YIELD_AND_SHARED_DAILY_SHAPE_R1",
        "model_family": "BASE_SPECIFIC_MEAN_HISTORICAL_YIELD_SCALED_BY_TARGET_AREA",
        "architecture": "TWO_STAGE_TOTAL_AND_NORMALIZED_DAILY_SHAPE",
        "training_seasons": list(TRAINING_SEASONS),
        "training_row_count": len(training_rows),
        "training_unique_base_count": len(yields_by_base),
        "training_row_keys": [
            f"{base_id}+{season}"
            for base_id, season in sorted(train_keys, key=lambda key: (key[1], key[0]))
        ],
        "training_dataset_sha256": training_dataset_sha256,
        "training_daily_curve_sha256": training_daily_sha256,
        "configuration_sha256": config_sha256,
        "training_code_sha256": training_code_sha256,
        "stage_a": {
            "per_base_estimator": "ARITHMETIC_MEAN_OF_ELIGIBLE_BASE_SEASON_YIELDS_KG_PER_MU",
            "base_yield_kg_per_mu": base_yields,
            "unseen_base_fallback": "POOLED_TRAINING_TOTAL_DIVIDED_BY_POOLED_TRAINING_AREA",
            "pooled_training_yield_kg_per_mu": decimal_text(pooled_yield),
            "training_quantity_sum_kg": decimal_text(quantity_sum),
            "training_area_sum_mu": decimal_text(area_sum),
        },
        "stage_b": {
            "profile_method": (
                "EQUAL_WEIGHT_MEAN_OF_STRICT_TRAINING_BASE_SEASON_NORMALIZED_SHARES_BY_MONTH_DAY"
            ),
            "profile_base_season_count": len(training_rows),
            "target_start": TARGET_START.isoformat(),
            "target_end": TARGET_END.isoformat(),
            "target_day_count": len(target_days),
            "profile_by_month_day": profile_by_month_day,
        },
        "randomness": "NONE",
        "weather_used": False,
        "oot_labels_used": False,
        "artifact_hash": "",
    }
    payload.pop("artifact_hash")
    payload["artifact_hash"] = _stable_digest(payload)
    return payload


def verify_model_artifact(model: Mapping[str, Any]) -> None:
    payload = dict(model)
    artifact_hash = str(payload.pop("artifact_hash", ""))
    if not artifact_hash or _stable_digest(payload) != artifact_hash:
        raise S8BacktestError("MODEL_ARTIFACT_HASH_INVALID")
    if model.get("oot_labels_used") is not False:
        raise S8BacktestError("MODEL_ARTIFACT_CLAIMS_OOT_LABEL_USE")


def predict_season_total(
    model: Mapping[str, Any], *, base_id: str, area_mu: Decimal, use_base_yield: bool = True
) -> dict[str, str]:
    verify_model_artifact(model)
    if area_mu <= 0:
        raise S8BacktestError("NONPOSITIVE_TARGET_AREA")
    stage_a = model["stage_a"]
    yield_map = stage_a["base_yield_kg_per_mu"] if use_base_yield else {}
    yield_value = decimal_value(
        yield_map.get(base_id, stage_a["pooled_training_yield_kg_per_mu"]),
        "predicted_yield_kg_per_mu",
    )
    basis = (
        "BASE_TRAINING_MEAN_YIELD"
        if base_id in yield_map and use_base_yield
        else "POOLED_TRAINING_YIELD_FALLBACK"
    )
    predicted = quantize_quantity(area_mu * yield_value)
    return {
        "predicted_season_total_kg": decimal_text(predicted),
        "predicted_yield_kg_per_mu": decimal_text(yield_value),
        "prediction_basis": basis,
    }


def compose_daily_curve(
    *, model: Mapping[str, Any], predicted_total_kg: Decimal, season: str = OOT_SEASON
) -> list[dict[str, str]]:
    verify_model_artifact(model)
    days = season_calendar(season)
    profile = model["stage_b"]["profile_by_month_day"]
    shares = [decimal_value(profile[day.strftime("%m-%d")], "daily_share") for day in days]
    with localcontext() as context:
        context.prec = 60
        share_sum = sum(shares, Decimal(0))
    if any(share < 0 for share in shares) or abs(share_sum - Decimal(1)) > Decimal("1e-30"):
        raise S8BacktestError("PREDICTED_DAILY_SHARES_NOT_NORMALIZED")
    quantities: list[Decimal] = []
    for share in shares[:-1]:
        quantities.append(quantize_quantity(predicted_total_kg * share))
    quantities.append(predicted_total_kg - sum(quantities, Decimal(0)))
    if any(quantity < 0 for quantity in quantities):
        raise S8BacktestError("NEGATIVE_PREDICTED_DAILY_QUANTITY")
    if sum(quantities, Decimal(0)) != predicted_total_kg:
        raise S8BacktestError("PREDICTED_DAILY_MASS_BALANCE_FAILED")
    return [
        {
            "date": day.isoformat(),
            "predicted_daily_quantity_kg": decimal_text(quantity),
            "predicted_share": decimal_text(share),
        }
        for day, quantity, share in zip(days, quantities, shares, strict=True)
    ]


def _earliest_max_index(values: Sequence[Decimal]) -> int:
    if not values:
        raise S8BacktestError("EMPTY_PEAK_SERIES")
    maximum = max(values)
    return next(index for index, value in enumerate(values) if value == maximum)


def derive_peaks(daily_rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    dates = [date.fromisoformat(str(row["date"])) for row in daily_rows]
    quantities = [
        decimal_value(
            row.get("predicted_daily_quantity_kg", row.get("actual_quantity_kg")),
            "peak_daily_quantity",
        )
        for row in daily_rows
    ]
    if not dates or any(
        dates[index + 1] - dates[index] != timedelta(days=1) for index in range(len(dates) - 1)
    ):
        raise S8BacktestError("PEAK_SERIES_DATES_NOT_CONSECUTIVE")
    daily_index = _earliest_max_index(quantities)
    if len(quantities) < 7:
        raise S8BacktestError("ROLLING7_REQUIRES_SEVEN_DAYS")
    rolling = [
        sum(quantities[start : start + 7], Decimal(0)) for start in range(len(quantities) - 6)
    ]
    rolling_index = _earliest_max_index(rolling)
    return {
        "single_day_peak_date": dates[daily_index].isoformat(),
        "single_day_peak_quantity_kg": decimal_text(quantities[daily_index]),
        "rolling7_start_date": dates[rolling_index].isoformat(),
        "rolling7_end_date": (dates[rolling_index] + timedelta(days=6)).isoformat(),
        "rolling7_peak_quantity_kg": decimal_text(rolling[rolling_index]),
    }


def percentile(values: Sequence[Decimal], quantile: Decimal) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = Decimal(len(ordered) - 1) * quantile
    lower = int(rank)
    fraction = rank - Decimal(lower)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def numeric_distribution(values: Sequence[Decimal]) -> dict[str, str | int | None]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "p25": None,
            "median": None,
            "p75": None,
            "p90": None,
            "max": None,
        }
    return {
        "count": len(values),
        "min": decimal_text(min(values)),
        "p25": decimal_text(percentile(values, Decimal("0.25")) or Decimal(0)),
        "median": decimal_text(percentile(values, Decimal("0.5")) or Decimal(0)),
        "p75": decimal_text(percentile(values, Decimal("0.75")) or Decimal(0)),
        "p90": decimal_text(percentile(values, Decimal("0.9")) or Decimal(0)),
        "max": decimal_text(max(values)),
    }


def _error_metrics(actual: Sequence[Decimal], predicted: Sequence[Decimal]) -> dict[str, Any]:
    if len(actual) != len(predicted) or not actual:
        raise S8BacktestError("METRIC_COHORT_LENGTH_INVALID")
    abs_errors = [abs(pred - act) for pred, act in zip(predicted, actual, strict=True)]
    signed_errors = [pred - act for pred, act in zip(predicted, actual, strict=True)]
    actual_sum = sum(actual, Decimal(0))
    predicted_sum = sum(predicted, Decimal(0))
    error_sum = sum(abs_errors, Decimal(0))
    bias_sum = sum(signed_errors, Decimal(0))
    wape = error_sum / actual_sum if actual_sum > 0 else None
    ape = [error / act for error, act in zip(abs_errors, actual, strict=True) if act != 0]
    median_ape = percentile(ape, Decimal("0.5"))
    return {
        "n": len(actual),
        "actual_sum": decimal_text(actual_sum),
        "predicted_sum": decimal_text(predicted_sum),
        "absolute_error_sum": decimal_text(error_sum),
        "wape": decimal_text(wape)
        if wape is not None
        else "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR",
        "mae": decimal_text(error_sum / Decimal(len(actual))),
        "bias_mean_predicted_minus_actual": decimal_text(bias_sum / Decimal(len(actual))),
        "bias_sum_predicted_minus_actual": decimal_text(bias_sum),
        "median_ape_excluding_zero_actual": decimal_text(median_ape)
        if median_ape is not None
        else "NOT_COMPUTABLE_NO_NONZERO_ACTUAL",
        "zero_actual_count": sum(value == 0 for value in actual),
        "absolute_error_distribution": numeric_distribution(abs_errors),
    }


def _per_base_error(
    model_rows: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    actual_key: str,
    predicted_key: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for base_id, rows in model_rows.items():
        actual = [decimal_value(row[actual_key], actual_key) for row in rows]
        predicted = [decimal_value(row[predicted_key], predicted_key) for row in rows]
        result[base_id] = _error_metrics(actual, predicted)
    return result


def score_model_daily(
    prediction_rows: Sequence[Mapping[str, Any]],
    actual_by_base: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    by_base: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in prediction_rows:
        by_base[str(row["base_id"])].append(dict(row))
    if set(by_base) != set(actual_by_base):
        raise S8BacktestError("DAILY_SCORING_BASE_COHORT_MISMATCH")
    pooled_rows: list[dict[str, Any]] = []
    by_base_peaks: dict[str, dict[str, str]] = {}
    for base_id in sorted(by_base):
        predictions = sorted(by_base[base_id], key=lambda row: str(row["date"]))
        actuals = sorted(actual_by_base[base_id], key=lambda row: str(row["date"]))
        if [row["date"] for row in predictions] != [row["date"] for row in actuals]:
            raise S8BacktestError("DAILY_SCORING_DATE_COHORT_MISMATCH")
        merged: list[dict[str, Any]] = []
        for pred, act in zip(predictions, actuals, strict=True):
            merged_row = {
                **pred,
                "actual_quantity_kg": decimal_text(
                    decimal_value(act["actual_quantity_kg"], "actual_quantity")
                ),
            }
            merged.append(merged_row)
            pooled_rows.append(merged_row)
        by_base[base_id] = merged
        validate_curve(
            [
                {
                    "date": row["date"],
                    "new_quantity_kg": row["actual_quantity_kg"],
                    "new_completeness_status": row.get(
                        "actual_completeness_status", "AUTHORIZED_ZERO"
                    ),
                    "authority_eligible_daily": True,
                }
                for row in merged
            ],
            season=OOT_SEASON,
        )
        actual_peak = derive_peaks(
            [
                {"date": row["date"], "actual_quantity_kg": row["actual_quantity_kg"]}
                for row in merged
            ]
        )
        predicted_peak = derive_peaks(merged)
        by_base_peaks[base_id] = {
            "actual_peak_date": actual_peak["single_day_peak_date"],
            "actual_peak_quantity_kg": actual_peak["single_day_peak_quantity_kg"],
            "predicted_peak_date": predicted_peak["single_day_peak_date"],
            "predicted_peak_quantity_kg": predicted_peak["single_day_peak_quantity_kg"],
            "actual_rolling7_start_date": actual_peak["rolling7_start_date"],
            "actual_rolling7_end_date": actual_peak["rolling7_end_date"],
            "actual_rolling7_peak_quantity_kg": actual_peak["rolling7_peak_quantity_kg"],
            "predicted_rolling7_start_date": predicted_peak["rolling7_start_date"],
            "predicted_rolling7_end_date": predicted_peak["rolling7_end_date"],
            "predicted_rolling7_peak_quantity_kg": predicted_peak["rolling7_peak_quantity_kg"],
        }
    actual = [decimal_value(row["actual_quantity_kg"], "actual") for row in pooled_rows]
    predicted = [
        decimal_value(row["predicted_daily_quantity_kg"], "predicted") for row in pooled_rows
    ]
    per_base = _per_base_error(
        {
            base_id: [
                {
                    "actual_quantity_kg": row["actual_quantity_kg"],
                    "predicted_daily_quantity_kg": row["predicted_daily_quantity_kg"],
                }
                for row in rows
            ]
            for base_id, rows in by_base.items()
        },
        actual_key="actual_quantity_kg",
        predicted_key="predicted_daily_quantity_kg",
    )
    peak_date_errors: list[Decimal] = []
    peak_quantity_actual: list[Decimal] = []
    peak_quantity_predicted: list[Decimal] = []
    rolling_date_errors: list[Decimal] = []
    rolling_quantity_actual: list[Decimal] = []
    rolling_quantity_predicted: list[Decimal] = []
    for metrics in by_base_peaks.values():
        peak_date_errors.append(
            Decimal(
                abs(
                    (
                        date.fromisoformat(metrics["predicted_peak_date"])
                        - date.fromisoformat(metrics["actual_peak_date"])
                    ).days
                )
            )
        )
        peak_quantity_actual.append(
            decimal_value(metrics["actual_peak_quantity_kg"], "actual_peak")
        )
        peak_quantity_predicted.append(
            decimal_value(metrics["predicted_peak_quantity_kg"], "predicted_peak")
        )
        rolling_date_errors.append(
            Decimal(
                abs(
                    (
                        date.fromisoformat(metrics["predicted_rolling7_start_date"])
                        - date.fromisoformat(metrics["actual_rolling7_start_date"])
                    ).days
                )
            )
        )
        rolling_quantity_actual.append(
            decimal_value(metrics["actual_rolling7_peak_quantity_kg"], "actual_rolling7")
        )
        rolling_quantity_predicted.append(
            decimal_value(metrics["predicted_rolling7_peak_quantity_kg"], "predicted_rolling7")
        )
    return {
        "row_count": len(pooled_rows),
        "base_count": len(by_base),
        "daily": _error_metrics(actual, predicted),
        "per_base_daily_wape_distribution": numeric_distribution(
            [
                decimal_value(metrics["wape"], "base_wape")
                for metrics in per_base.values()
                if isinstance(metrics.get("wape"), str)
                and not str(metrics["wape"]).startswith("NOT_")
            ]
        ),
        "per_base_daily": per_base,
        "single_day_peak": {
            **_error_metrics(peak_quantity_actual, peak_quantity_predicted),
            "date_mae_days": decimal_text(
                sum(peak_date_errors, Decimal(0)) / Decimal(len(peak_date_errors))
            ),
            "date_error_distribution_days": numeric_distribution(peak_date_errors),
        },
        "rolling7_peak": {
            **_error_metrics(rolling_quantity_actual, rolling_quantity_predicted),
            "start_date_mae_days": decimal_text(
                sum(rolling_date_errors, Decimal(0)) / Decimal(len(rolling_date_errors))
            ),
            "start_date_error_distribution_days": numeric_distribution(rolling_date_errors),
        },
        "per_base_peak_truth_and_predictions": by_base_peaks,
    }


def score_season_totals(
    actual_by_base: Mapping[str, Decimal], predicted_by_model: Mapping[str, Mapping[str, Decimal]]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for model_id, predicted_by_base in sorted(predicted_by_model.items()):
        if set(predicted_by_base) != set(actual_by_base):
            raise S8BacktestError(f"SEASON_TOTAL_COHORT_MISMATCH:{model_id}")
        base_ids = sorted(actual_by_base)
        actual = [actual_by_base[base_id] for base_id in base_ids]
        predicted = [predicted_by_base[base_id] for base_id in base_ids]
        metrics = _error_metrics(actual, predicted)
        ape_by_base: list[Decimal] = []
        per_base: dict[str, dict[str, str]] = {}
        for base_id in base_ids:
            error = abs(predicted_by_base[base_id] - actual_by_base[base_id])
            ape = error / actual_by_base[base_id] if actual_by_base[base_id] != 0 else None
            if ape is not None:
                ape_by_base.append(ape)
            per_base[base_id] = {
                "actual_total_kg": decimal_text(actual_by_base[base_id]),
                "predicted_total_kg": decimal_text(predicted_by_base[base_id]),
                "absolute_error_kg": decimal_text(error),
                "absolute_percentage_error": decimal_text(ape)
                if ape is not None
                else "NOT_COMPUTABLE_ZERO_ACTUAL",
            }
        errors = sorted(
            (
                {
                    "base_id": base_id,
                    "absolute_error_kg": decimal_text(
                        abs(predicted_by_base[base_id] - actual_by_base[base_id])
                    ),
                    "actual_total_kg": decimal_text(actual_by_base[base_id]),
                    "predicted_total_kg": decimal_text(predicted_by_base[base_id]),
                }
                for base_id in base_ids
            ),
            key=lambda row: (-Decimal(row["absolute_error_kg"]), row["base_id"]),
        )
        median_ape = percentile(ape_by_base, Decimal("0.5"))
        metrics["median_ape"] = (
            decimal_text(median_ape)
            if median_ape is not None
            else "NOT_COMPUTABLE_NO_NONZERO_ACTUAL"
        )
        metrics["per_base_absolute_percentage_error_distribution"] = numeric_distribution(
            ape_by_base
        )
        metrics["per_base"] = per_base
        metrics["worst_five"] = errors[:5]
        result[model_id] = metrics
    return result


def signed_metric_delta(candidate: Any, comparator: Any) -> str:
    if not isinstance(candidate, str) or not isinstance(comparator, str):
        return "NOT_AVAILABLE"
    if candidate.startswith("NOT_") or comparator.startswith("NOT_"):
        return "NOT_AVAILABLE"
    return decimal_text(
        decimal_value(candidate, "candidate_metric")
        - decimal_value(comparator, "comparator_metric")
    )
