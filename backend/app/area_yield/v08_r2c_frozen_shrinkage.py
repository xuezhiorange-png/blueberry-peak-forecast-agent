"""Frozen V0.8-R2C Stage A shrinkage fit and replay metrics.

This module deliberately accepts only the frozen training rows, target-area
covariates, and the already-frozen S8 Stage B artifact. Benchmark actuals are
handled by the orchestration script after prediction files have been sealed.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any

TRAINING_SEASONS = ("2023-2024", "2024-2025")
BENCHMARK_SEASON = "2025-2026"
FROZEN_LAMBDA = Decimal("1")
EXPECTED_TRAINING_ROWS = 37
EXPECTED_TRAINING_SEASON_COUNTS = {"2023-2024": 15, "2024-2025": 22}
EXPECTED_STAGE_B_SHAPE_SHA256 = "7ae53f5888947053057071f9b097e38b03bb8112a41de972b8e2d51fd311cb2e"
QUANTUM = Decimal("0.000001")
CALCULATION_PRECISION = 40


class R2CExperimentError(ValueError):
    """Raised when a frozen R2C cohort or prediction contract is violated."""


def decimal_value(value: Any, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise R2CExperimentError(f"INVALID_DECIMAL:{field}") from exc
    if not parsed.is_finite():
        raise R2CExperimentError(f"NONFINITE_DECIMAL:{field}")
    return parsed


def decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise R2CExperimentError("NONFINITE_DECIMAL_OUTPUT")
    return format(value, "f")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_training_cohort(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    season_counts: dict[str, int] = defaultdict(int)
    keys: set[tuple[str, str]] = set()
    bases: set[str] = set()
    for row in rows:
        season = str(row.get("season", ""))
        if season == BENCHMARK_SEASON:
            raise R2CExperimentError("BENCHMARK_SEASON_FORBIDDEN_IN_TRAINING")
        if season not in TRAINING_SEASONS:
            raise R2CExperimentError(f"UNAUTHORIZED_TRAINING_SEASON:{season}")
        if str(row.get("strict_training_eligible", "true")).lower() != "true":
            raise R2CExperimentError("BLOCKED_TRAINING_ROW_INCLUDED")
        base_id = str(row.get("base_id", ""))
        if not base_id:
            raise R2CExperimentError("TRAINING_BASE_ID_MISSING")
        key = (base_id, season)
        if key in keys:
            raise R2CExperimentError("DUPLICATE_TRAINING_BASE_SEASON")
        keys.add(key)
        bases.add(base_id)
        area = decimal_value(row.get("area_mu"), "training_area_mu")
        quantity = decimal_value(row.get("season_total_quantity_kg"), "training_total_kg")
        if area <= 0 or quantity < 0:
            raise R2CExperimentError("INVALID_TRAINING_TARGET")
        season_counts[season] += 1
    normalized_counts = {season: season_counts.get(season, 0) for season in TRAINING_SEASONS}
    if len(rows) != EXPECTED_TRAINING_ROWS or normalized_counts != EXPECTED_TRAINING_SEASON_COUNTS:
        raise R2CExperimentError("TRAINING_COHORT_COUNT_MISMATCH")
    return {
        "row_count": len(rows),
        "season_counts": normalized_counts,
        "unique_base_count": len(bases),
        "blocked_rows_included": 0,
    }


def shrinkage_weight(support_count: int, lambda_value: Decimal = FROZEN_LAMBDA) -> Decimal:
    if support_count < 0:
        raise R2CExperimentError("NEGATIVE_TRAINING_SUPPORT")
    if lambda_value != FROZEN_LAMBDA:
        raise R2CExperimentError("LAMBDA_NOT_FROZEN_TO_ONE")
    with localcontext() as context:
        context.prec = 60
        return Decimal(support_count) / (Decimal(support_count) + lambda_value)


def build_shrinkage_model(
    training_rows: Sequence[Mapping[str, Any]],
    training_dataset_sha256: str,
    *,
    lambda_value: Decimal = FROZEN_LAMBDA,
) -> dict[str, Any]:
    if lambda_value != FROZEN_LAMBDA:
        raise R2CExperimentError("LAMBDA_NOT_FROZEN_TO_ONE")
    if len(training_dataset_sha256) != 64:
        raise R2CExperimentError("TRAINING_DATASET_SHA256_INVALID")
    cohort = validate_training_cohort(training_rows)
    quantities: list[Decimal] = []
    areas: list[Decimal] = []
    yields_by_base: dict[str, list[Decimal]] = defaultdict(list)
    seasons_by_base: dict[str, list[str]] = defaultdict(list)
    for row in sorted(
        training_rows, key=lambda value: (str(value["season"]), str(value["base_id"]))
    ):
        area = decimal_value(row["area_mu"], "training_area_mu")
        quantity = decimal_value(row["season_total_quantity_kg"], "training_total_kg")
        with localcontext() as context:
            context.prec = CALCULATION_PRECISION
            season_yield = quantity / area
        base_id = str(row["base_id"])
        yields_by_base[base_id].append(season_yield)
        seasons_by_base[base_id].append(str(row["season"]))
        areas.append(area)
        quantities.append(quantity)
    with localcontext() as context:
        context.prec = CALCULATION_PRECISION
        global_yield = sum(quantities, Decimal(0)) / sum(areas, Decimal(0))
        base_yields = {
            base_id: decimal_text(sum(values, Decimal(0)) / Decimal(len(values)))
            for base_id, values in sorted(yields_by_base.items())
        }
    payload: dict[str, Any] = {
        "model_id": "V0_8_R2C_AREA_SCALED_LAMBDA_1_SHRINKAGE_R1",
        "model_family": "SHRINKAGE_BASE_YIELD",
        "lambda": "1",
        "formula": "BASE_MEAN*n/(n+1)+GLOBAL_POOLED_YIELD/(n+1)",
        "base_mean_yield_policy": "ARITHMETIC_MEAN_OF_ELIGIBLE_BASE_SEASON_YIELDS_KG_PER_MU",
        "global_yield_aggregation_policy": (
            "SUM_TRAINING_SEASON_TOTAL_KG_DIVIDED_BY_SUM_TRAINING_AREA_MU"
        ),
        "training_dataset_sha256": training_dataset_sha256,
        "training_row_count": cohort["row_count"],
        "training_season_counts": cohort["season_counts"],
        "training_unique_base_count": cohort["unique_base_count"],
        "training_seasons": list(TRAINING_SEASONS),
        "global_yield_kg_per_mu": decimal_text(global_yield),
        "training_area_sum_mu": decimal_text(sum(areas, Decimal(0))),
        "training_quantity_sum_kg": decimal_text(sum(quantities, Decimal(0))),
        "base_yield_kg_per_mu": base_yields,
        "base_support_count": {
            base_id: len(yields) for base_id, yields in sorted(yields_by_base.items())
        },
        "base_training_seasons": {
            base_id: sorted(seasons) for base_id, seasons in sorted(seasons_by_base.items())
        },
        "benchmark_labels_used": False,
        "randomness": "NONE",
    }
    payload["artifact_sha256"] = sha256_bytes(canonical_json_bytes(payload))
    return payload


def verify_shrinkage_model(model: Mapping[str, Any]) -> None:
    payload = dict(model)
    actual = str(payload.pop("artifact_sha256", ""))
    if not actual or sha256_bytes(canonical_json_bytes(payload)) != actual:
        raise R2CExperimentError("STAGE_A_MODEL_ARTIFACT_HASH_INVALID")
    if model.get("lambda") != "1" or model.get("benchmark_labels_used") is not False:
        raise R2CExperimentError("STAGE_A_MODEL_FREEZE_CONTRACT_INVALID")


def predict_shrunk_yield(model: Mapping[str, Any], base_id: str) -> Decimal:
    verify_shrinkage_model(model)
    global_yield = decimal_value(model["global_yield_kg_per_mu"], "global_yield")
    support = int(model["base_support_count"].get(base_id, 0))
    if support == 0:
        return global_yield
    base_mean = decimal_value(model["base_yield_kg_per_mu"][base_id], "base_mean_yield")
    weight = shrinkage_weight(support)
    with localcontext() as context:
        context.prec = CALCULATION_PRECISION
        return weight * base_mean + (Decimal(1) - weight) * global_yield


def predict_shrunk_total(
    model: Mapping[str, Any], base_id: str, area_mu: Decimal
) -> dict[str, str]:
    verify_shrinkage_model(model)
    if area_mu <= 0:
        raise R2CExperimentError("NONPOSITIVE_TARGET_AREA")
    yield_value = predict_shrunk_yield(model, base_id)
    with localcontext() as context:
        context.prec = CALCULATION_PRECISION
        total = (yield_value * area_mu).quantize(QUANTUM, rounding=ROUND_HALF_EVEN)
    return {
        "predicted_yield_kg_per_mu": decimal_text(yield_value),
        "predicted_total_kg": decimal_text(total),
    }


def percentile(values: Sequence[Decimal], quantile: Decimal) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = Decimal(len(ordered) - 1) * quantile
    lower_index = int(rank)
    fraction = rank - Decimal(lower_index)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def error_metrics(actual: Sequence[Decimal], predicted: Sequence[Decimal]) -> dict[str, Any]:
    if not actual or len(actual) != len(predicted):
        raise R2CExperimentError("METRIC_FIXED_COHORT_INVALID")
    absolute_errors = [abs(pred - truth) for truth, pred in zip(actual, predicted, strict=True)]
    signed_errors = [pred - truth for truth, pred in zip(actual, predicted, strict=True)]
    actual_sum = sum(actual, Decimal(0))
    predicted_sum = sum(predicted, Decimal(0))
    if actual_sum <= 0:
        raise R2CExperimentError("METRIC_ACTUAL_DENOMINATOR_NOT_POSITIVE")
    ape = [
        error / truth for error, truth in zip(absolute_errors, actual, strict=True) if truth != 0
    ]
    median_ape = percentile(ape, Decimal("0.5"))
    bias_sum = sum(signed_errors, Decimal(0))
    return {
        "n": len(actual),
        "actual_sum_kg": decimal_text(actual_sum),
        "predicted_sum_kg": decimal_text(predicted_sum),
        "absolute_error_sum_kg": decimal_text(sum(absolute_errors, Decimal(0))),
        "wape": decimal_text(sum(absolute_errors, Decimal(0)) / actual_sum),
        "mae_kg": decimal_text(sum(absolute_errors, Decimal(0)) / Decimal(len(actual))),
        "median_ape_excluding_zero_actual": (
            decimal_text(median_ape) if median_ape is not None else "NOT_COMPUTABLE"
        ),
        "bias_sum_kg": decimal_text(bias_sum),
        "bias_ratio": decimal_text(bias_sum / actual_sum),
        "overpredict_count": sum(
            pred > truth for truth, pred in zip(actual, predicted, strict=True)
        ),
        "underpredict_count": sum(
            pred < truth for truth, pred in zip(actual, predicted, strict=True)
        ),
        "tie_count": sum(pred == truth for truth, pred in zip(actual, predicted, strict=True)),
    }


def win_loss_counts(
    actual: Mapping[str, Decimal],
    candidate: Mapping[str, Decimal],
    comparator: Mapping[str, Decimal],
) -> dict[str, int]:
    if set(actual) != set(candidate) or set(actual) != set(comparator):
        raise R2CExperimentError("WIN_LOSS_COHORT_MISMATCH")
    candidate_wins = sum(
        abs(candidate[key] - actual[key]) < abs(comparator[key] - actual[key]) for key in actual
    )
    comparator_wins = sum(
        abs(candidate[key] - actual[key]) > abs(comparator[key] - actual[key]) for key in actual
    )
    return {
        "candidate_lower_abs_error_count": candidate_wins,
        "comparator_lower_abs_error_count": comparator_wins,
        "tie_count": len(actual) - candidate_wins - comparator_wins,
    }


def validate_support_zero_parity(
    rows: Sequence[Mapping[str, Any]], *, global_key: str, shrinkage_key: str
) -> int:
    support_zero = [row for row in rows if int(row["support_count"]) == 0]
    for row in support_zero:
        if decimal_value(row[global_key], global_key) != decimal_value(
            row[shrinkage_key], shrinkage_key
        ):
            raise R2CExperimentError("SUPPORT_ZERO_GLOBAL_PREDICTION_PARITY_FAILED")
    return len(support_zero)


def verify_daily_sum(
    daily_rows: Sequence[Mapping[str, Any]],
    season_total_by_base: Mapping[str, Decimal],
) -> int:
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for row in daily_rows:
        base_id = str(row["base_id"])
        totals[base_id] += decimal_value(row["predicted_daily_quantity_kg"], "daily_prediction")
    if set(totals) != set(season_total_by_base):
        raise R2CExperimentError("PREDICTED_DAILY_BASE_COHORT_MISMATCH")
    mismatches = [
        base_id for base_id, total in totals.items() if total != season_total_by_base[base_id]
    ]
    if mismatches:
        raise R2CExperimentError("PREDICTED_DAILY_SUM_RECONCILIATION_FAILED")
    return len(totals)


def daily_predictions_from_frozen_shape(
    total_rows: Sequence[Mapping[str, Any]],
    frozen_shape_rows: Sequence[Mapping[str, Any]],
    *,
    model_id: str,
    model_artifact_sha256: str,
) -> list[dict[str, str]]:
    """Scale the pinned S8 Base×date shares without fitting or changing Stage B."""
    from backend.app.area_yield.v08_r2_stage_a import stage_b_shape_hash

    totals = {str(row["base_id"]): row for row in total_rows}
    if len(totals) != len(total_rows) or not totals:
        raise R2CExperimentError("DAILY_PREDICTION_TOTAL_COHORT_INVALID")
    shape_hash = stage_b_shape_hash(frozen_shape_rows)
    if shape_hash != EXPECTED_STAGE_B_SHAPE_SHA256:
        raise R2CExperimentError("BLOCKED_STAGE_B_DRIFT")
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in frozen_shape_rows:
        base_id = str(row["base_id"])
        if base_id not in totals or str(row.get("season")) != BENCHMARK_SEASON:
            raise R2CExperimentError("FROZEN_SHAPE_COHORT_MISMATCH")
        grouped[base_id].append(row)
    if set(grouped) != set(totals):
        raise R2CExperimentError("FROZEN_SHAPE_BASE_COHORT_MISMATCH")

    output: list[dict[str, str]] = []
    expected_dates: list[str] | None = None
    for base_id in sorted(totals):
        base_rows = sorted(grouped[base_id], key=lambda item: str(item["date"]))
        dates = [str(row["date"]) for row in base_rows]
        if expected_dates is None:
            expected_dates = dates
        elif dates != expected_dates:
            raise R2CExperimentError("FROZEN_SHAPE_DATE_COHORT_MISMATCH")
        shares = [decimal_value(row["predicted_share"], "frozen_daily_share") for row in base_rows]
        if not shares or any(share < 0 for share in shares):
            raise R2CExperimentError("FROZEN_SHAPE_INVALID_SHARE")
        with localcontext() as context:
            context.prec = 60
            if abs(sum(shares, Decimal(0)) - Decimal(1)) > Decimal("1e-30"):
                raise R2CExperimentError("FROZEN_SHAPE_NOT_NORMALIZED")
        total_row = totals[base_id]
        total = decimal_value(total_row["predicted_season_total_kg"], "predicted_total")
        emitted: list[Decimal] = []
        for share in shares[:-1]:
            emitted.append((total * share).quantize(QUANTUM, rounding=ROUND_HALF_EVEN))
        emitted.append(total - sum(emitted, Decimal(0)))
        if sum(emitted, Decimal(0)) != total or any(value < 0 for value in emitted):
            raise R2CExperimentError("PREDICTED_DAILY_MASS_BALANCE_FAILED")
        for source, share, quantity in zip(base_rows, shares, emitted, strict=True):
            output.append(
                {
                    "model_id": model_id,
                    "base_id": base_id,
                    "canonical_base_name": str(total_row["canonical_base_name"]),
                    "season": BENCHMARK_SEASON,
                    "date": str(source["date"]),
                    "target_area_mu": str(total_row["target_area_mu"]),
                    "predicted_season_total_kg": decimal_text(total),
                    "predicted_daily_quantity_kg": decimal_text(quantity),
                    "predicted_share": decimal_text(share),
                    "model_artifact_sha256": model_artifact_sha256,
                }
            )
    return output


def validate_prediction_season(rows: Sequence[Mapping[str, Any]]) -> None:
    if any(str(row.get("season")) != BENCHMARK_SEASON for row in rows):
        raise R2CExperimentError("NON_BENCHMARK_ROW_IN_PREDICTIONS")
    keys = [(str(row["base_id"]), str(row["season"])) for row in rows]
    if len(keys) != len(set(keys)):
        raise R2CExperimentError("DUPLICATE_BENCHMARK_PREDICTION")
