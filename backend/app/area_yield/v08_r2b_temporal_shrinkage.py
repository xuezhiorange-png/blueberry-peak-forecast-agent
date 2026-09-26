"""Leakage-gated temporal validation for the frozen V0.8 R2B yield candidates."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from decimal import Decimal, localcontext
from typing import Any

TRAIN_SEASON = "2023-2024"
VALIDATION_SEASON = "2024-2025"
FORBIDDEN_SEASON = "2025-2026"
EXPECTED_DATASET_SHA256 = "72363ec56dae682fba80ccf984a6fedb2c57425e1fbdcea8b8fca10aca0b5aba"
ALLOWED_LAMBDAS = tuple(Decimal(value) for value in ("0.25", "0.5", "1", "2", "4", "8"))


class R2BExperimentError(ValueError):
    """A fail-closed R2B contract or input validation error."""


def decimal_value(value: Any, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise R2BExperimentError(f"INVALID_DECIMAL:{field}") from exc
    if not parsed.is_finite():
        raise R2BExperimentError(f"NONFINITE_DECIMAL:{field}")
    return parsed


def decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise R2BExperimentError("NONFINITE_DECIMAL_OUTPUT")
    return format(value, "f")


def validate_dataset_hash(payload: bytes, expected_sha256: str = EXPECTED_DATASET_SHA256) -> str:
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected_sha256:
        raise R2BExperimentError("BLOCKED_TRAINING_DATASET_DRIFT")
    return actual


def project_rows_before_freeze(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Project train labels and validation covariates without touching validation labels.

    The 2025-2026 gate runs immediately after reading only the season identifier.
    Validation projection never indexes quantity or yield fields.
    """
    train_rows: list[dict[str, str]] = []
    validation_rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for source in rows:
        season = str(source["season"])
        if season == FORBIDDEN_SEASON:
            raise R2BExperimentError("BLOCKED_2025_2026_ACCESS")
        if season not in {TRAIN_SEASON, VALIDATION_SEASON}:
            raise R2BExperimentError("BLOCKED_UNAUTHORIZED_SEASON")
        base_id = str(source["base_id"])
        key = (base_id, season)
        if key in seen:
            raise R2BExperimentError("DUPLICATE_BASE_SEASON_KEY")
        seen.add(key)
        name = str(source["canonical_base_name"])
        area = decimal_value(source["area_mu"], "area_mu")
        if area <= 0:
            raise R2BExperimentError("NONPOSITIVE_AREA")
        strict_flag = str(source.get("strict_training_eligible", "true")).lower()
        if strict_flag != "true":
            raise R2BExperimentError("BLOCKED_INELIGIBLE_CANONICAL_ROW")

        projected = {
            "base_id": base_id,
            "canonical_base_name": name,
            "season": season,
            "area_mu": decimal_text(area),
        }
        if season == TRAIN_SEASON:
            total = decimal_value(source["season_total_quantity_kg"], "season_total_quantity_kg")
            if total <= 0:
                raise R2BExperimentError("NONPOSITIVE_TRAINING_QUANTITY")
            with localcontext() as context:
                context.prec = 60
                projected["season_total_quantity_kg"] = decimal_text(total)
                projected["yield_kg_per_mu"] = decimal_text(total / area)
            for field in (
                "area_authority_id",
                "area_authority_sha256",
                "quantity_authority_id",
                "quantity_authority_sha256",
                "identity_authority_id",
                "identity_authority_sha256",
                "source_signature",
                "eligibility_signature",
            ):
                if field in source:
                    projected[field] = str(source[field])
            train_rows.append(projected)
        else:
            # Intentionally do not access season_total_quantity_kg or yield_kg_per_mu here.
            for field in (
                "area_authority_id",
                "area_authority_sha256",
                "quantity_authority_id",
                "quantity_authority_sha256",
                "identity_authority_id",
                "identity_authority_sha256",
                "source_signature",
                "eligibility_signature",
            ):
                if field in source:
                    projected[field] = str(source[field])
            validation_rows.append(projected)

    train_rows.sort(key=lambda row: (row["season"], row["base_id"]))
    validation_rows.sort(key=lambda row: (row["season"], row["base_id"]))
    return train_rows, validation_rows


def validate_temporal_cohorts(
    train_rows: Sequence[Mapping[str, Any]], validation_rows: Sequence[Mapping[str, Any]]
) -> dict[str, int]:
    train_keys = {(str(row["base_id"]), str(row["season"])) for row in train_rows}
    validation_keys = {(str(row["base_id"]), str(row["season"])) for row in validation_rows}
    if train_keys & validation_keys:
        raise R2BExperimentError("BLOCKED_TEMPORAL_COHORT_MISMATCH:OVERLAPPING_BASE_SEASON")
    if any(season != TRAIN_SEASON for _, season in train_keys):
        raise R2BExperimentError("BLOCKED_TEMPORAL_COHORT_MISMATCH:TRAIN_SEASON")
    if any(season != VALIDATION_SEASON for _, season in validation_keys):
        raise R2BExperimentError("BLOCKED_TEMPORAL_COHORT_MISMATCH:VALIDATION_SEASON")
    train_bases = {base for base, _ in train_keys}
    validation_bases = {base for base, _ in validation_keys}
    support_1 = train_bases & validation_bases
    support_0 = validation_bases - train_bases
    counts = {
        "train_count": len(train_keys),
        "validation_count": len(validation_keys),
        "unique_base_count": len(train_bases | validation_bases),
        "support_1_count": len(support_1),
        "support_0_count": len(support_0),
        "overlap_count": len(support_1),
    }
    if counts != {
        "train_count": 15,
        "validation_count": 22,
        "unique_base_count": 26,
        "support_1_count": 11,
        "support_0_count": 11,
        "overlap_count": 11,
    }:
        raise R2BExperimentError("BLOCKED_TEMPORAL_COHORT_MISMATCH")
    return counts


def pooled_training_yield(train_rows: Sequence[Mapping[str, Any]]) -> Decimal:
    """Use S8's area-weighted pooled aggregation on the explicit 2023-24 partition only."""
    if not train_rows:
        raise R2BExperimentError("EMPTY_TRAIN_SEASON")
    quantity = Decimal(0)
    area = Decimal(0)
    for row in sorted(train_rows, key=lambda item: (str(item["season"]), str(item["base_id"]))):
        if str(row["season"]) != TRAIN_SEASON:
            raise R2BExperimentError("VALIDATION_LABEL_FORBIDDEN_IN_GLOBAL_YIELD")
        quantity += decimal_value(row["season_total_quantity_kg"], "season_total_quantity_kg")
        area += decimal_value(row["area_mu"], "area_mu")
    if area <= 0:
        raise R2BExperimentError("NONPOSITIVE_TRAIN_AREA_SUM")
    with localcontext() as context:
        context.prec = 60
        estimate = quantity / area
    return estimate


def validate_lambda_grid(lambdas: Sequence[Decimal]) -> None:
    if tuple(lambdas) != ALLOWED_LAMBDAS:
        raise R2BExperimentError("BLOCKED_LAMBDA_GRID_DRIFT")


def build_candidate_predictions(
    train_rows: Sequence[Mapping[str, Any]],
    validation_rows: Sequence[Mapping[str, Any]],
    lambdas: Sequence[Decimal] = ALLOWED_LAMBDAS,
) -> list[dict[str, str]]:
    validate_lambda_grid(lambdas)
    global_yield = pooled_training_yield(train_rows)
    history: dict[str, Decimal] = {}
    for row in train_rows:
        if str(row["season"]) != TRAIN_SEASON:
            raise R2BExperimentError("NON_TRAIN_SEASON_IN_BASE_HISTORY")
        base = str(row["base_id"])
        area = decimal_value(row["area_mu"], "train_area_mu")
        total = decimal_value(row["season_total_quantity_kg"], "train_quantity_kg")
        if base in history:
            raise R2BExperimentError("MULTIPLE_TRAIN_SEASONS_NOT_ALLOWED_IN_R2B")
        with localcontext() as context:
            context.prec = 60
            history[base] = total / area

    predictions: list[dict[str, str]] = []
    for row in sorted(validation_rows, key=lambda item: str(item["base_id"])):
        if str(row["season"]) != VALIDATION_SEASON:
            raise R2BExperimentError("NON_VALIDATION_ROW_IN_PREDICTIONS")
        base = str(row["base_id"])
        area = decimal_value(row["area_mu"], "validation_area_mu")
        base_yield = history.get(base)
        support = 1 if base_yield is not None else 0
        with localcontext() as context:
            context.prec = 60
            global_total = global_yield * area
            base_yield_for_prediction = global_yield if base_yield is None else base_yield
            base_specific_total = base_yield_for_prediction * area
        output = {
            "base_id": base,
            "canonical_base_name": str(row["canonical_base_name"]),
            "season": VALIDATION_SEASON,
            "support_group": f"SUPPORT_{support}",
            "support_count": str(support),
            "validation_area_mu": decimal_text(area),
            "global_yield": decimal_text(global_yield),
            "global_predicted_total": decimal_text(global_total),
            "base_historical_yield": "" if base_yield is None else decimal_text(base_yield),
            "base_specific_predicted_yield": decimal_text(
                global_yield if base_yield is None else base_yield
            ),
            "base_specific_predicted_total": decimal_text(base_specific_total),
        }
        for lam in ALLOWED_LAMBDAS:
            with localcontext() as context:
                context.prec = 60
                weight = Decimal(0) if support == 0 else Decimal(support) / (Decimal(support) + lam)
                shrunk_yield = (
                    global_yield
                    if base_yield is None
                    else weight * base_yield + (Decimal(1) - weight) * global_yield
                )
                predicted_total = shrunk_yield * area
            suffix = str(lam).replace(".", "_")
            output[f"lambda_{suffix}_weight"] = decimal_text(weight)
            output[f"lambda_{suffix}_yield"] = decimal_text(shrunk_yield)
            output[f"lambda_{suffix}_predicted_total"] = decimal_text(predicted_total)
        predictions.append(output)
    validate_support_zero_parity(predictions)
    return predictions


def validate_support_zero_parity(predictions: Sequence[Mapping[str, Any]]) -> int:
    support_zero = [row for row in predictions if row["support_group"] == "SUPPORT_0"]
    if len(support_zero) != 11:
        raise R2BExperimentError("SUPPORT_0_COHORT_COUNT_MISMATCH")
    fields = ["global_predicted_total", "base_specific_predicted_total"] + [
        f"lambda_{str(lam).replace('.', '_')}_predicted_total" for lam in ALLOWED_LAMBDAS
    ]
    for row in support_zero:
        values = {decimal_value(row[field], field) for field in fields}
        if len(values) != 1:
            raise R2BExperimentError("SUPPORT_0_CANDIDATE_PREDICTION_PARITY_FAILED")
    return len(support_zero)


def candidate_metrics(
    predictions: Sequence[Mapping[str, Any]],
    actuals: Mapping[str, Decimal],
    predicted_total_field: str,
    *,
    support_group: str | None = None,
) -> dict[str, str | int]:
    selected = [
        row
        for row in predictions
        if support_group is None or str(row["support_group"]) == support_group
    ]
    if not selected:
        raise R2BExperimentError("EMPTY_SCORING_COHORT")
    actual_values = [
        decimal_value(actuals[str(row["base_id"])], "actual_total") for row in selected
    ]
    actual_sum = sum(actual_values, Decimal(0))
    if actual_sum <= 0:
        raise R2BExperimentError("NONPOSITIVE_WAPE_DENOMINATOR")
    errors: list[Decimal] = []
    apes: list[Decimal] = []
    signed_errors: list[Decimal] = []
    for row, actual in zip(selected, actual_values, strict=True):
        predicted = decimal_value(row[predicted_total_field], predicted_total_field)
        signed = predicted - actual
        errors.append(abs(signed))
        signed_errors.append(signed)
        with localcontext() as context:
            context.prec = 60
            apes.append(abs(signed) / actual)
    with localcontext() as context:
        context.prec = 60
        wape = sum(errors, Decimal(0)) / actual_sum
        mae = sum(errors, Decimal(0)) / Decimal(len(errors))
        bias = sum(signed_errors, Decimal(0))
        bias_ratio = bias / actual_sum
    return {
        "row_count": len(selected),
        "actual_denominator_kg": decimal_text(actual_sum),
        "wape": decimal_text(wape),
        "mae_kg": decimal_text(mae),
        "median_ape": decimal_text(_median(apes)),
        "bias_kg": decimal_text(bias),
        "bias_ratio": decimal_text(bias_ratio),
    }


def select_candidate(support1_summaries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Select by exact support-1 WAPE; exact ties use frozen simplicity/bias/shrinkage order."""
    if not support1_summaries:
        raise R2BExperimentError("EMPTY_PRIMARY_CANDIDATE_SET")

    def key(summary: Mapping[str, Any]) -> tuple[Decimal, int, Decimal, Decimal]:
        candidate = str(summary["candidate"])
        complexity = {
            "GLOBAL_POOLED_YIELD": 0,
            "BASE_SPECIFIC_NO_SHRINKAGE": 1,
            "SHRINKAGE_BASE_YIELD": 2,
        }.get(candidate)
        if complexity is None:
            raise R2BExperimentError("UNAUTHORIZED_SELECTION_CANDIDATE")
        lam = (
            Decimal(0)
            if str(summary.get("lambda", "NONE")) == "NONE"
            else decimal_value(summary["lambda"], "lambda")
        )
        return (
            decimal_value(summary["wape"], "primary_wape"),
            complexity,
            abs(decimal_value(summary["bias_kg"], "bias_kg")),
            -lam,
        )

    ranked = [(key(summary), summary) for summary in support1_summaries]
    return dict(min(ranked, key=lambda item: item[0])[1])


def win_loss_counts(
    predictions: Sequence[Mapping[str, Any]],
    actuals: Mapping[str, Decimal],
    candidate_field: str,
    comparator_field: str,
    *,
    support_group: str = "SUPPORT_1",
) -> dict[str, int]:
    counts = {"candidate_lower_error": 0, "comparator_lower_error": 0, "tie": 0}
    for row in predictions:
        if row["support_group"] != support_group:
            continue
        actual = decimal_value(actuals[str(row["base_id"])], "actual_total")
        candidate_error = abs(decimal_value(row[candidate_field], candidate_field) - actual)
        comparator_error = abs(decimal_value(row[comparator_field], comparator_field) - actual)
        if candidate_error < comparator_error:
            counts["candidate_lower_error"] += 1
        elif candidate_error > comparator_error:
            counts["comparator_lower_error"] += 1
        else:
            counts["tie"] += 1
    return counts


def history_diagnostics(
    predictions: Sequence[Mapping[str, Any]], actuals: Mapping[str, Decimal]
) -> dict[str, str | int]:
    history_closer = global_closer = tie = persistent = 0
    historical_yields: list[Decimal] = []
    next_yields: list[Decimal] = []
    for row in predictions:
        if row["support_group"] != "SUPPORT_1":
            continue
        base = str(row["base_id"])
        with localcontext() as context:
            context.prec = 60
            actual_yield = decimal_value(actuals[base], "actual_total") / decimal_value(
                row["validation_area_mu"], "validation_area_mu"
            )
        historical_yield = decimal_value(row["base_historical_yield"], "base_historical_yield")
        global_yield = decimal_value(row["global_yield"], "global_yield")
        historical_distance = abs(actual_yield - historical_yield)
        global_distance = abs(actual_yield - global_yield)
        if historical_distance < global_distance:
            history_closer += 1
        elif historical_distance > global_distance:
            global_closer += 1
        else:
            tie += 1
        historical_deviation = historical_yield - global_yield
        next_deviation = actual_yield - global_yield
        if (
            historical_deviation != 0
            and next_deviation != 0
            and ((historical_deviation > 0) == (next_deviation > 0))
        ):
            persistent += 1
        historical_yields.append(historical_yield)
        next_yields.append(actual_yield)
    if len(historical_yields) != 11:
        raise R2BExperimentError("SUPPORT_1_DIAGNOSTIC_COHORT_COUNT_MISMATCH")
    with localcontext() as context:
        context.prec = 60
        persistence_rate = Decimal(persistent) / Decimal(11)
    return {
        "base_history_closer_count": history_closer,
        "global_yield_closer_count": global_closer,
        "history_global_tie_count": tie,
        "direction_persistence_count": persistent,
        "direction_persistence_rate": decimal_text(persistence_rate),
        "pearson": decimal_text(_pearson(historical_yields, next_yields)),
        "spearman": decimal_text(_spearman(historical_yields, next_yields)),
        "correlation_n": len(historical_yields),
    }


def _median(values: Sequence[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    with localcontext() as context:
        context.prec = 60
        return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _pearson(left: Sequence[Decimal], right: Sequence[Decimal]) -> Decimal:
    if len(left) != len(right) or len(left) < 2:
        raise R2BExperimentError("CORRELATION_INPUT_COUNT_MISMATCH")
    count = Decimal(len(left))
    sum_x = sum(left, Decimal(0))
    sum_y = sum(right, Decimal(0))
    sum_x2 = sum((value * value for value in left), Decimal(0))
    sum_y2 = sum((value * value for value in right), Decimal(0))
    sum_xy = sum((x * y for x, y in zip(left, right, strict=True)), Decimal(0))
    numerator = count * sum_xy - sum_x * sum_y
    variance_x = count * sum_x2 - sum_x * sum_x
    variance_y = count * sum_y2 - sum_y * sum_y
    if variance_x <= 0 or variance_y <= 0:
        raise R2BExperimentError("UNDEFINED_CORRELATION")
    with localcontext() as context:
        context.prec = 60
        return numerator / (variance_x * variance_y).sqrt()


def _rank(values: Sequence[Decimal]) -> list[Decimal]:
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    ranks = [Decimal(0)] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        average_rank = (Decimal(index + 1) + Decimal(end)) / Decimal(2)
        for position in range(index, end):
            ranks[ordered[position][0]] = average_rank
        index = end
    return ranks


def _spearman(left: Sequence[Decimal], right: Sequence[Decimal]) -> Decimal:
    return _pearson(_rank(left), _rank(right))
