"""Frozen Base10 model-family research. No database, weather or production access."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from typing import Any

import numpy as np

from backend.app.area_yield.v015_research_cohort import digest
from backend.app.area_yield.weather_aware_backtest import (
    BASE_FEATURES,
    RollingTargetRow,
    fit_ridge_artifact,
)

SEED = 15015
EXPECTED_COUNTS = {"TRAIN": 4125, "VALIDATION": 6028, "EXPOSED_OOT": 9867}
SEASONS = {"TRAIN": "2023-2024", "VALIDATION": "2024-2025", "EXPOSED_OOT": "2025-2026"}
RIDGE_CONFIG: dict[str, Any] = {
    "family": "RIDGE_LEAST_SQUARES",
    "alpha": "10.000000",
    "intercept_unpenalized": True,
    "standardization": "TRAIN_ONLY_STANDARD_SCALER_POPULATION_STD",
    "zero_std_policy": "SCALE_1",
    "solver": "numpy.linalg.solve",
    "nonnegative_output_clip": True,
}
CB_COMMON: dict[str, Any] = {
    "loss_function": "RMSE",
    "bootstrap_type": "No",
    "random_strength": 0,
    "grow_policy": "SymmetricTree",
    "random_seed": SEED,
    "thread_count": 1,
    "allow_writing_files": False,
    "verbose": False,
    "task_type": "CPU",
}
LGB_COMMON: dict[str, Any] = {
    "objective": "regression_l2",
    "subsample": 1.0,
    "colsample_bytree": 1.0,
    "reg_alpha": 0,
    "deterministic": True,
    "force_col_wise": True,
    "random_state": SEED,
    "seed": SEED,
    "data_random_seed": SEED,
    "feature_fraction_seed": SEED,
    "bagging_seed": SEED,
    "drop_seed": SEED,
    "extra_seed": SEED,
    "objective_seed": SEED,
    "n_jobs": 1,
    "verbosity": -1,
    "device_type": "cpu",
}
CANDIDATES: dict[str, dict[str, Any]] = {
    "RIDGE": RIDGE_CONFIG,
    "CB1": {**CB_COMMON, "depth": 4, "iterations": 400, "learning_rate": 0.05, "l2_leaf_reg": 5},
    "CB2": {**CB_COMMON, "depth": 6, "iterations": 600, "learning_rate": 0.03, "l2_leaf_reg": 10},
    "CB3": {**CB_COMMON, "depth": 8, "iterations": 400, "learning_rate": 0.03, "l2_leaf_reg": 10},
    "LGB1": {
        **LGB_COMMON,
        "num_leaves": 15,
        "max_depth": 5,
        "n_estimators": 400,
        "learning_rate": 0.05,
        "min_child_samples": 50,
        "reg_lambda": 5,
    },
    "LGB2": {
        **LGB_COMMON,
        "num_leaves": 31,
        "max_depth": 7,
        "n_estimators": 600,
        "learning_rate": 0.03,
        "min_child_samples": 50,
        "reg_lambda": 10,
    },
    "LGB3": {
        **LGB_COMMON,
        "num_leaves": 63,
        "max_depth": 8,
        "n_estimators": 400,
        "learning_rate": 0.03,
        "min_child_samples": 100,
        "reg_lambda": 10,
    },
}


def access_allowed(phase: str, split: str, *, labels: bool) -> bool:
    allowed = {
        "A": ({"TRAIN", "VALIDATION"}, {"TRAIN"}),
        "B": ({"VALIDATION"}, {"VALIDATION"}),
        "FINAL": ({"TRAIN", "VALIDATION", "EXPOSED_OOT"}, {"TRAIN", "VALIDATION"}),
        "SCORE": ({"EXPOSED_OOT"}, {"EXPOSED_OOT"}),
    }
    return phase in allowed and split in allowed[phase][int(labels)]


def flatten_features(rows: list[dict[str, Any]]) -> tuple[Any, list[str]]:
    values, keys = [], []
    for row in sorted(rows, key=lambda r: r["row_key"]):
        if row["season"] != SEASONS.get(row["split"]):
            raise ValueError("UNAUTHORIZED_SEASON")
        if len(row["base10"]) != 15 or len(row["target_dates"]) != 15:
            raise ValueError("BASE10_SCHEMA")
        if any(row["missing_mask"]):
            raise ValueError("BASE10_MISSING")
        for lead, vector in enumerate(row["base10"], 1):
            if set(vector) != set(BASE_FEATURES):
                raise ValueError("BASE10_SCHEMA")
            values.append([float(vector[name]) for name in BASE_FEATURES])
            keys.append(f"{row['row_key']}#D{lead:02}")
    matrix = np.asarray(values, dtype=float)
    if matrix.shape != (len(rows) * 15, 10) or len(set(keys)) != len(keys):
        raise ValueError("COMMON_ROWSET")
    if not np.isfinite(matrix).all():
        raise ValueError("NONFINITE_FEATURE")
    return matrix, keys


def normalize_predictions(values: Any) -> list[str]:
    result = []
    for value in values:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("MODEL_OUTPUT_INVALID")
        result.append(format(max(0.0, number), ".12f"))
    return result


def ridge_rows(rows: list[dict[str, Any]]) -> list[RollingTargetRow]:
    result = []
    for row in sorted(rows, key=lambda r: r["row_key"]):
        for lead, vector in enumerate(row["base10"], 1):
            result.append(
                RollingTargetRow(
                    key=f"{row['row_key']}#D{lead:02}",
                    base_id=row["base_id"],
                    base_name="",
                    season=row["season"],
                    forecast_origin=row["forecast_origin"],
                    target_date=date.fromisoformat(row["target_dates"][lead - 1]),
                    lead_day=lead,
                    reference_area_mu=Decimal(vector[BASE_FEATURES[0]]) * 1000,
                    feature_values=tuple((name, vector[name]) for name in BASE_FEATURES),
                    weather_feature_hash="",
                    weather_source="NONE",
                    weather_lane="NONE",
                    feature_policy_version="V0_15_BASE10_ONLY",
                )
            )
    return result


@dataclass
class FittedModel:
    candidate: str
    artifact: Any

    def predict(self, rows: list[dict[str, Any]]) -> list[str]:
        matrix, _ = flatten_features(rows)
        if self.candidate == "RIDGE":
            return [format(self.artifact.predict(row), ".12f") for row in ridge_rows(rows)]
        return normalize_predictions(self.artifact.predict(matrix))


def fit_model(candidate: str, rows: list[dict[str, Any]], labels: list[Any]) -> FittedModel:
    if candidate not in CANDIDATES:
        raise ValueError("CANDIDATE_NOT_FROZEN")
    matrix, keys = flatten_features(rows)
    y = np.asarray(labels, dtype=float)
    if len(y) != len(keys) or not np.isfinite(y).all() or np.any(y < 0):
        raise ValueError("TRAINING_LABEL_INVALID")
    if candidate == "RIDGE":
        # Reuse the authoritative normal equation, train-only population scaler,
        # unpenalized intercept and frozen alpha; never fit a replacement Ridge.
        artifact = fit_ridge_artifact(
            model_id="V0_15_BASE10_RIDGE",
            fold_id="S3_RESEARCH",
            rows=list(zip(ridge_rows(rows), [Decimal(str(v)) for v in labels], strict=True)),
            feature_names=BASE_FEATURES,
            training_input_hash=digest(keys),
        )
    elif candidate.startswith("CB"):
        from catboost import CatBoostRegressor

        artifact = CatBoostRegressor(**CANDIDATES[candidate])
        artifact.fit(matrix, y)  # No validation labels, eval_set or early stopping.
    else:
        from lightgbm import LGBMRegressor

        artifact = LGBMRegressor(**CANDIDATES[candidate])
        artifact.fit(matrix, y)
    return FittedModel(candidate, artifact)


def verify_seal(seal: dict[str, Any]) -> None:
    if seal.get("labels_read") is not False or seal.get("seal_hash") != digest(
        {k: v for k, v in seal.items() if k != "seal_hash"}
    ):
        raise ValueError("PREDICTION_SEAL_INVALID")


def ratio(a: Decimal, b: Decimal) -> str | None:
    return str(a / b) if b > 0 else None


def score(
    rows: list[dict[str, Any]],
    predictions: list[list[str]],
    labels: list[list[str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not rows or len(rows) != len(predictions) or len(rows) != len(labels):
        raise ValueError("COMMON_ROWSET")
    with localcontext() as ctx:
        ctx.prec = 50
        return _score(rows, predictions, labels)


def _score(
    rows: list[dict[str, Any]],
    predictions: list[list[str]],
    labels: list[list[str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    zero = Decimal(0)
    absolute = [zero] * 15
    actual = [zero] * 15
    signed = zero
    cumulative = {7: zero, 15: zero}
    peaks = dict(single_quantity=zero, single_date=zero, rolling_quantity=zero, rolling_date=zero)
    shape, shape_denom, shape_bad = zero, zero, 0
    bases: dict[str, Any] = {}
    for row, pv, av in zip(rows, predictions, labels, strict=True):
        if len(pv) != 15 or len(av) != 15:
            raise ValueError("COMMON_ROWSET")
        p, a = list(map(Decimal, pv)), list(map(Decimal, av))
        if any(not v.is_finite() or v < 0 for v in p + a):
            raise ValueError("MODEL_OUTPUT_INVALID")
        base = bases.setdefault(
            row["base_id"], {"error7": zero, "error15": zero, "actual7": zero, "actual15": zero}
        )
        for i in range(15):
            error = abs(p[i] - a[i])
            absolute[i] += error
            actual[i] += a[i]
            signed += p[i] - a[i]
            base["error15"] += error
            base["actual15"] += a[i]
            if i < 7:
                base["error7"] += error
                base["actual7"] += a[i]
        for horizon in (7, 15):
            cumulative[horizon] += abs(sum(p[:horizon], zero) - sum(a[:horizon], zero))
        pi, ai = p.index(max(p)), a.index(max(a))
        pr = [sum(p[i : i + 7], zero) for i in range(9)]
        ar = [sum(a[i : i + 7], zero) for i in range(9)]
        peaks["single_quantity"] += abs(max(p) - max(a))
        peaks["single_date"] += abs(pi - ai)
        peaks["rolling_quantity"] += abs(max(pr) - max(ar))
        peaks["rolling_date"] += abs(pr.index(max(pr)) - ar.index(max(ar)))
        q, qhat = sum(a, zero), sum(p, zero)
        if q > 0 and qhat > 0:
            shape += sum((abs(v * q / qhat - u) for v, u in zip(p, a, strict=True)), zero)
            shape_denom += q
        else:
            shape_bad += 1
    n = Decimal(len(rows))
    error_total, actual_total = sum(absolute, zero), sum(actual, zero)
    result = {
        "origin_count": len(rows),
        "target_row_count": len(rows) * 15,
        "DAILY_WAPE": ratio(error_total, actual_total),
        "DAILY_MAE_KG": str(error_total / (n * 15)),
        "BIAS_KG": str(signed / (n * 15)),
        "TOTAL_SIGNED_BIAS_KG": str(signed),
        "H7_DAILY_WAPE": ratio(sum(absolute[:7], zero), sum(actual[:7], zero)),
        "H15_DAILY_WAPE": ratio(error_total, actual_total),
        "H7_CUMULATIVE_WAPE": ratio(cumulative[7], sum(actual[:7], zero)),
        "H15_CUMULATIVE_WAPE": ratio(cumulative[15], actual_total),
        "SINGLE_DAY_PEAK_QUANTITY_MAE_KG": str(peaks["single_quantity"] / n),
        "SINGLE_DAY_PEAK_DATE_MAE_DAYS": str(peaks["single_date"] / n),
        "ROLLING7_PEAK_QUANTITY_MAE_KG": str(peaks["rolling_quantity"] / n),
        "ROLLING7_PEAK_START_DATE_MAE_DAYS": str(peaks["rolling_date"] / n),
        "CURVE_SHAPE_ERROR": ratio(shape, shape_denom) if not shape_bad else None,
        "curve_shape_undefined_origin_count": shape_bad,
        "lead_day_metrics": [
            {"lead": i + 1, "WAPE": ratio(absolute[i], actual[i]), "MAE_KG": str(absolute[i] / n)}
            for i in range(15)
        ],
    }
    return result, {k: {name: str(v) for name, v in b.items()} for k, b in bases.items()}


def complexity(candidate: str) -> tuple[int, ...]:
    c = CANDIDATES[candidate]
    return (
        (c["depth"], c["iterations"])
        if candidate.startswith("CB")
        else (c["num_leaves"], c["max_depth"], c["n_estimators"])
    )


def select_candidate(metrics: dict[str, dict[str, Any]], *, split: str = "VALIDATION") -> str:
    if split != "VALIDATION":
        raise ValueError("VALIDATION_ONLY")
    if not metrics or any(k not in CANDIDATES or k == "RIDGE" for k in metrics):
        raise ValueError("CANDIDATE_NOT_FROZEN")
    return min(
        metrics,
        key=lambda k: (
            Decimal(metrics[k]["H15_DAILY_WAPE"]),
            Decimal(metrics[k]["H7_DAILY_WAPE"]),
            Decimal(metrics[k]["DAILY_MAE_KG"]),
            complexity(k),
            k,
        ),
    )


def direction(
    tree_v: dict[str, Any], ridge_v: dict[str, Any], tree_o: dict[str, Any], ridge_o: dict[str, Any]
) -> str:
    improvements = [
        Decimal(tree[k]) < Decimal(ridge[k])
        for tree, ridge in ((tree_v, ridge_v), (tree_o, ridge_o))
        for k in ("H7_DAILY_WAPE", "H15_DAILY_WAPE")
    ]
    return (
        "SUPPORTED_DIRECTION"
        if all(improvements)
        else ("MIXED" if any(improvements) else "NOT_SUPPORTED_DIRECTION")
    )
