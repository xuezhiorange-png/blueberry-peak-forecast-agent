"""Training-only selection and frozen Stage-A R2 model helpers.

This module never loads benchmark rows. Benchmark scoring is a separate runner
phase entered only after a self-hashed final model artifact has been written.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any

QUANTUM = Decimal("0.000001")
TRAINING_SEASONS = frozenset({"2023-2024", "2024-2025"})
ALLOWED_CANDIDATES = frozenset(
    {"GLOBAL_POOLED_YIELD", "SHRINKAGE_BASE_YIELD", "REGULARIZED_BASE_EFFECT"}
)


class R2ExperimentError(ValueError):
    """Raised when a frozen R2 input or model-selection gate fails closed."""


def decimal_value(value: Any, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise R2ExperimentError(f"INVALID_DECIMAL:{field}") from exc
    if not parsed.is_finite():
        raise R2ExperimentError(f"NONFINITE_DECIMAL:{field}")
    return parsed


def decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise R2ExperimentError("NONFINITE_DECIMAL_OUTPUT")
    return format(value, "f")


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


def validate_training_dataset_hash(payload: bytes, expected_sha256: str) -> str:
    actual = sha256_bytes(payload)
    if actual != expected_sha256:
        raise R2ExperimentError("BLOCKED_TRAINING_DATASET_DRIFT")
    return actual


def _row_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return str(row["base_id"]), str(row["season"])


def validate_training_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    keys = [_row_key(row) for row in rows]
    if len(keys) != 37 or len(set(keys)) != 37:
        raise R2ExperimentError("TRAINING_COHORT_MUST_BE_37_UNIQUE_BASE_SEASONS")
    if any(season not in TRAINING_SEASONS for _, season in keys):
        raise R2ExperimentError("OOT_OR_UNAUTHORIZED_SEASON_IN_TRAINING_ROWS")
    counts = {
        season: sum(1 for _, row_season in keys if row_season == season)
        for season in sorted(TRAINING_SEASONS)
    }
    if counts != {"2023-2024": 15, "2024-2025": 22}:
        raise R2ExperimentError("TRAINING_SEASON_COUNTS_DRIFT")
    if any(str(row.get("strict_training_eligible", "true")).lower() != "true" for row in rows):
        raise R2ExperimentError("BLOCKED_TRAINING_ROW_INCLUDED")
    for row in rows:
        if decimal_value(row["area_mu"], "area_mu") <= 0:
            raise R2ExperimentError("NONPOSITIVE_TRAINING_AREA")
        if decimal_value(row["season_total_quantity_kg"], "season_total") <= 0:
            raise R2ExperimentError("NONPOSITIVE_TRAINING_SEASON_TOTAL")


def grouped_leave_one_base_out_folds(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return deterministic folds where every season of a Base has one role."""
    bases = sorted({str(row["base_id"]) for row in rows})
    if len(bases) < 2:
        raise R2ExperimentError("GROUPED_CV_REQUIRES_MULTIPLE_BASES")
    folds: list[dict[str, Any]] = []
    for index, validation_base in enumerate(bases, start=1):
        training = [row for row in rows if str(row["base_id"]) != validation_base]
        validation = [row for row in rows if str(row["base_id"]) == validation_base]
        training_bases = {str(row["base_id"]) for row in training}
        if validation_base in training_bases or not validation:
            raise R2ExperimentError("GROUPED_CV_BASE_LEAKAGE")
        folds.append(
            {
                "fold_id": f"LOBO_{index:02d}",
                "training_rows": training,
                "validation_rows": validation,
                "training_base_ids": sorted(training_bases),
                "validation_base_ids": [validation_base],
            }
        )
    return folds


def pooled_training_yield(rows: Sequence[Mapping[str, Any]]) -> Decimal:
    ordered = sorted(rows, key=lambda item: (str(item["season"]), str(item["base_id"])))
    total = Decimal(0)
    area = Decimal(0)
    for row in ordered:
        total += decimal_value(row["season_total_quantity_kg"], "season_total")
        area += decimal_value(row["area_mu"], "area_mu")
    if not rows or area <= 0:
        raise R2ExperimentError("EMPTY_OR_ZERO_AREA_TRAINING_PARTITION")
    with localcontext() as context:
        # Match the frozen S8 Stage-A pooled fallback calculation exactly.
        context.prec = 40
        return total / area


def _yield_by_base(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[Decimal]]:
    result: dict[str, list[Decimal]] = defaultdict(list)
    for row in sorted(rows, key=lambda item: (str(item["base_id"]), str(item["season"]))):
        with localcontext() as context:
            context.prec = 60
            result[str(row["base_id"])].append(
                decimal_value(row["season_total_quantity_kg"], "season_total")
                / decimal_value(row["area_mu"], "area_mu")
            )
    return result


def fit_stage_a(
    rows: Sequence[Mapping[str, Any]], candidate: str, hyperparameter: Decimal | None
) -> dict[str, Any]:
    """Fit one predeclared Stage-A candidate using only the supplied rows."""
    if candidate not in ALLOWED_CANDIDATES:
        raise R2ExperimentError("UNAUTHORIZED_STAGE_A_CANDIDATE")
    if not rows:
        raise R2ExperimentError("EMPTY_STAGE_A_FIT_ROWS")
    global_yield = pooled_training_yield(rows)
    grouped = _yield_by_base(rows)

    if candidate == "GLOBAL_POOLED_YIELD":
        if hyperparameter is not None:
            raise R2ExperimentError("GLOBAL_CANDIDATE_HAS_NO_HYPERPARAMETER")
        return {
            "candidate": candidate,
            "hyperparameter": "NONE",
            "global_yield_kg_per_mu": decimal_text(global_yield),
            "base_yield_kg_per_mu": {},
            "base_support": {base: len(values) for base, values in sorted(grouped.items())},
        }

    if candidate == "SHRINKAGE_BASE_YIELD":
        if hyperparameter is None or hyperparameter <= 0:
            raise R2ExperimentError("SHRINKAGE_LAMBDA_MUST_BE_POSITIVE")
        estimates: dict[str, str] = {}
        weights: dict[str, str] = {}
        supports: dict[str, int] = {}
        for base, yields in sorted(grouped.items()):
            count = len(yields)
            weight = Decimal(count) / (Decimal(count) + hyperparameter)
            with localcontext() as context:
                context.prec = 60
                base_mean = sum(yields, Decimal(0)) / Decimal(count)
                estimate = weight * base_mean + (Decimal(1) - weight) * global_yield
            estimates[base] = decimal_text(estimate)
            weights[base] = decimal_text(weight)
            supports[base] = count
        return {
            "candidate": candidate,
            "hyperparameter": decimal_text(hyperparameter),
            "global_yield_kg_per_mu": decimal_text(global_yield),
            "base_yield_kg_per_mu": estimates,
            "base_support": supports,
            "shrinkage_weights": weights,
        }

    if hyperparameter is None or hyperparameter <= 0:
        raise R2ExperimentError("RIDGE_ALPHA_MUST_BE_POSITIVE")
    return _fit_regularized_base_effect(rows, hyperparameter)


def _fit_regularized_base_effect(
    rows: Sequence[Mapping[str, Any]], alpha: Decimal
) -> dict[str, Any]:
    """Fit log-yield intercept plus ridge-penalized Base indicators.

    Area-normalized observation weights make the intercept an area-aware pooled
    yield when Base effects are fully regularized. The intercept is unpenalized.
    """
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - environment-level blocker
        raise R2ExperimentError("NUMPY_REQUIRED_FOR_REGULARIZED_BASE_EFFECT") from exc

    ordered = sorted(rows, key=lambda item: (str(item["base_id"]), str(item["season"])))
    bases = sorted({str(row["base_id"]) for row in ordered})
    base_column = {base: index + 1 for index, base in enumerate(bases)}
    areas = [float(decimal_value(row["area_mu"], "area_mu")) for row in ordered]
    mean_area = sum(areas) / len(areas)
    weights = np.asarray([area / mean_area for area in areas], dtype=np.float64)
    design = np.zeros((len(ordered), len(bases) + 1), dtype=np.float64)
    targets = np.zeros(len(ordered), dtype=np.float64)
    for row_index, row in enumerate(ordered):
        design[row_index, 0] = 1.0
        design[row_index, base_column[str(row["base_id"])]] = 1.0
        total = float(decimal_value(row["season_total_quantity_kg"], "season_total"))
        area = float(decimal_value(row["area_mu"], "area_mu"))
        if total <= 0 or area <= 0:
            raise R2ExperimentError("LOG_YIELD_REQUIRES_POSITIVE_TRAINING_VALUES")
        targets[row_index] = math.log(total / area)
    weighted_design = design * weights[:, None]
    gram = design.T @ weighted_design
    gram[1:, 1:] += float(alpha) * np.eye(len(bases), dtype=np.float64)
    right = design.T @ (weights * targets)
    try:
        coefficients = np.linalg.solve(gram, right)
    except np.linalg.LinAlgError as exc:
        raise R2ExperimentError("REGULARIZED_BASE_EFFECT_SOLVER_FAILED") from exc
    if not np.isfinite(coefficients).all():
        raise R2ExperimentError("REGULARIZED_BASE_EFFECT_NONFINITE_COEFFICIENT")
    intercept = float(coefficients[0])
    effects = {base: float(coefficients[base_column[base]]) for base in bases}
    support = {base: len(grouped) for base, grouped in sorted(_yield_by_base(ordered).items())}
    return {
        "candidate": "REGULARIZED_BASE_EFFECT",
        "hyperparameter": decimal_text(alpha),
        "global_yield_kg_per_mu": _float_decimal_text(math.exp(intercept)),
        "log_yield_intercept": _float_decimal_text(intercept),
        "base_log_yield_effects": {
            base: _float_decimal_text(value) for base, value in sorted(effects.items())
        },
        "base_support": support,
        "solver": "numpy.linalg.solve",
        "feature_schema": ["intercept", *[f"base_id:{base}" for base in bases]],
        "intercept_unpenalized": True,
        "base_effect_penalty": "L2_RIDGE",
        "area_weighting": "AREA_MU_DIVIDED_BY_MEAN_TRAINING_AREA_MU",
        "target_transform": "NATURAL_LOG_YIELD_KG_PER_MU",
    }


def _float_decimal_text(value: float) -> str:
    if not math.isfinite(value):
        raise R2ExperimentError("NONFINITE_FLOAT_MODEL_PARAMETER")
    return format(Decimal(format(value, ".17g")), "f")


def predict_yield(model: Mapping[str, Any], base_id: str) -> Decimal:
    candidate = str(model["candidate"])
    global_yield = decimal_value(model["global_yield_kg_per_mu"], "global_yield")
    if candidate in {"GLOBAL_POOLED_YIELD", "SHRINKAGE_BASE_YIELD"}:
        value = model.get("base_yield_kg_per_mu", {}).get(base_id, global_yield)
        return decimal_value(value, "predicted_yield")
    if candidate == "REGULARIZED_BASE_EFFECT":
        intercept = float(model["log_yield_intercept"])
        effect = float(model["base_log_yield_effects"].get(base_id, "0"))
        return decimal_value(_float_decimal_text(math.exp(intercept + effect)), "predicted_yield")
    raise R2ExperimentError("UNAUTHORIZED_STAGE_A_CANDIDATE")


def _total_metrics(actual: Sequence[Decimal], predicted: Sequence[Decimal]) -> dict[str, Decimal]:
    if not actual or len(actual) != len(predicted):
        raise R2ExperimentError("CV_METRIC_COHORT_EMPTY_OR_MISMATCHED")
    abs_errors = [abs(pred - truth) for truth, pred in zip(actual, predicted, strict=True)]
    signed = [pred - truth for truth, pred in zip(actual, predicted, strict=True)]
    actual_sum = sum(actual, Decimal(0))
    if actual_sum <= 0:
        raise R2ExperimentError("CV_WAPE_DENOMINATOR_NOT_POSITIVE")
    apes = sorted(
        abs_error / truth for truth, abs_error in zip(actual, abs_errors, strict=True) if truth != 0
    )
    middle = len(apes) // 2
    median_ape = apes[middle] if len(apes) % 2 else (apes[middle - 1] + apes[middle]) / Decimal(2)
    return {
        "wape": sum(abs_errors, Decimal(0)) / actual_sum,
        "mae": sum(abs_errors, Decimal(0)) / Decimal(len(actual)),
        "bias_kg": sum(signed, Decimal(0)),
        "median_ape": median_ape,
    }


def run_grouped_cv(
    rows: Sequence[Mapping[str, Any]],
    candidate_specs: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    """Evaluate fixed candidates using grouped LOBO and OOF season totals."""
    validate_training_rows(rows)
    folds = grouped_leave_one_base_out_folds(rows)
    fold_results: list[dict[str, str]] = []
    assignment: list[dict[str, str]] = []
    oof: dict[tuple[str, str, str, str], tuple[Decimal, Decimal]] = {}
    for fold in folds:
        fold_id = str(fold["fold_id"])
        validation_bases = set(fold["validation_base_ids"])
        for row in sorted(rows, key=lambda item: (str(item["season"]), str(item["base_id"]))):
            is_validation = str(row["base_id"]) in validation_bases
            assignment.append(
                {
                    "fold_id": fold_id,
                    "base_id": str(row["base_id"]),
                    "season": str(row["season"]),
                    "role": "VALIDATION" if is_validation else "TRAINING",
                }
            )
        validation_rows = fold["validation_rows"]
        for spec in candidate_specs:
            candidate = str(spec["model_candidate"])
            if candidate not in ALLOWED_CANDIDATES:
                raise R2ExperimentError("UNAUTHORIZED_STAGE_A_CANDIDATE")
            raw_hyperparameters = spec.get("hyperparameters", [None])
            for raw_parameter in raw_hyperparameters:
                parameter = (
                    None
                    if raw_parameter is None
                    else decimal_value(raw_parameter, "hyperparameter")
                )
                model = fit_stage_a(fold["training_rows"], candidate, parameter)
                actual_fold: list[Decimal] = []
                predicted_fold: list[Decimal] = []
                for row in validation_rows:
                    actual = decimal_value(row["season_total_quantity_kg"], "season_total")
                    area = decimal_value(row["area_mu"], "area_mu")
                    predicted = (area * predict_yield(model, str(row["base_id"]))).quantize(
                        QUANTUM, rounding=ROUND_HALF_EVEN
                    )
                    actual_fold.append(actual)
                    predicted_fold.append(predicted)
                    key = (
                        candidate,
                        model["hyperparameter"],
                        str(row["base_id"]),
                        str(row["season"]),
                    )
                    if key in oof:
                        raise R2ExperimentError("DUPLICATE_GROUPED_CV_OUT_OF_FOLD_ROW")
                    oof[key] = (actual, predicted)
                metrics = _total_metrics(actual_fold, predicted_fold)
                fold_results.append(
                    {
                        "model_candidate": candidate,
                        "hyperparameter": model["hyperparameter"],
                        "fold_id": fold_id,
                        "validation_base_count": str(len(validation_bases)),
                        "validation_row_count": str(len(validation_rows)),
                        "wape": decimal_text(metrics["wape"]),
                        "mae_kg": decimal_text(metrics["mae"]),
                        "bias_kg": decimal_text(metrics["bias_kg"]),
                        "median_ape": decimal_text(metrics["median_ape"]),
                    }
                )

    summary: list[dict[str, str]] = []
    for spec in candidate_specs:
        candidate = str(spec["model_candidate"])
        for raw_parameter in spec.get("hyperparameters", [None]):
            hyperparameter = (
                "NONE"
                if raw_parameter is None
                else decimal_text(decimal_value(raw_parameter, "hyperparameter"))
            )
            pair_rows = [
                value
                for (row_candidate, row_parameter, _, _), value in oof.items()
                if row_candidate == candidate and row_parameter == hyperparameter
            ]
            oof_actuals = [value[0] for value in pair_rows]
            oof_predictions = [value[1] for value in pair_rows]
            metrics = _total_metrics(oof_actuals, oof_predictions)
            folds_for_pair = [
                row
                for row in fold_results
                if row["model_candidate"] == candidate and row["hyperparameter"] == hyperparameter
            ]
            complexity = int(spec["complexity_rank"])
            summary.append(
                {
                    "model_candidate": candidate,
                    "hyperparameter": hyperparameter,
                    "cv_primary_metric": "GROUPED_CV_SEASON_TOTAL_WAPE",
                    "cv_wape": decimal_text(metrics["wape"]),
                    "mae_kg": decimal_text(metrics["mae"]),
                    "bias_kg": decimal_text(metrics["bias_kg"]),
                    "absolute_bias_kg": decimal_text(abs(metrics["bias_kg"])),
                    "median_ape": decimal_text(metrics["median_ape"]),
                    "fold_count": str(len(folds_for_pair)),
                    "validation_row_count": str(len(pair_rows)),
                    "complexity_rank": str(complexity),
                }
            )
    summary.sort(key=lambda row: (row["model_candidate"], row["hyperparameter"]))
    fold_results.sort(
        key=lambda row: (row["model_candidate"], row["hyperparameter"], row["fold_id"])
    )
    assignment.sort(key=lambda row: (row["fold_id"], row["season"], row["base_id"]))
    if len(oof) != len(rows) * sum(
        len(spec.get("hyperparameters", [None])) for spec in candidate_specs
    ):
        raise R2ExperimentError("GROUPED_CV_OUT_OF_FOLD_COVERAGE_MISMATCH")
    return assignment, fold_results, summary


def select_cv_candidate(
    summary: Sequence[Mapping[str, Any]], *, tie_tolerance: Decimal
) -> dict[str, Any]:
    if not summary or tie_tolerance < 0:
        raise R2ExperimentError("INVALID_CV_SELECTION_INPUT")
    parsed = [(row, decimal_value(row["cv_wape"], "cv_wape")) for row in summary]
    best_metric = min(metric for _, metric in parsed)
    tied = [row for row, metric in parsed if metric <= best_metric + tie_tolerance]
    selected = min(
        tied,
        key=lambda row: (
            int(row["complexity_rank"]),
            decimal_value(row["absolute_bias_kg"], "absolute_bias"),
            row["model_candidate"],
            _hyperparameter_simplicity(row["model_candidate"], row["hyperparameter"]),
        ),
    )
    return dict(selected)


def _hyperparameter_simplicity(candidate: str, hyperparameter: str) -> Decimal:
    if candidate == "SHRINKAGE_BASE_YIELD" and hyperparameter != "NONE":
        return -decimal_value(hyperparameter, "lambda")
    if candidate == "REGULARIZED_BASE_EFFECT" and hyperparameter != "NONE":
        return -decimal_value(hyperparameter, "alpha")
    return Decimal(0)


def build_final_stage_a_model(
    training_rows: Sequence[Mapping[str, Any]],
    candidate: str,
    hyperparameter: Decimal | None,
) -> dict[str, Any]:
    fitted = fit_stage_a(training_rows, candidate, hyperparameter)
    return fitted


def stage_b_shape_hash(rows: Sequence[Mapping[str, Any]]) -> str:
    canonical = [
        [
            str(row["base_id"]),
            str(row["date"]),
            format(decimal_value(row["predicted_share"], "predicted_share"), "f"),
        ]
        for row in sorted(rows, key=lambda item: (str(item["base_id"]), str(item["date"])))
    ]
    return sha256_bytes(canonical_json_bytes(canonical))


def validate_peak_date_invariance(
    r1_by_base: Mapping[str, Mapping[str, Any]],
    r2_by_base: Mapping[str, Mapping[str, Any]],
) -> tuple[int, int]:
    if set(r1_by_base) != set(r2_by_base):
        raise R2ExperimentError("PEAK_DATE_COHORT_MISMATCH")
    single_changed = sum(
        r1_by_base[base].get("single_day_peak_date") != r2_by_base[base].get("single_day_peak_date")
        for base in r1_by_base
    )
    rolling_changed = sum(
        r1_by_base[base].get("rolling7_start_date") != r2_by_base[base].get("rolling7_start_date")
        for base in r1_by_base
    )
    if single_changed or rolling_changed:
        raise R2ExperimentError("BLOCKED_STAGE_B_PEAK_DATE_DRIFT")
    return int(single_changed), int(rolling_changed)
