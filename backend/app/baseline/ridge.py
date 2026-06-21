from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from backend.app.baseline.config import BaselineConfig
from backend.app.baseline.metrics import evaluated_row, excluded_row
from backend.app.baseline.schemas import BacktestResultRow, BaselineSample

RIDGE_FEATURES = ("total_weight_kg", "variety_hhi", "farm_hhi", "subfarm_hhi")


def ridge_feature_vector(sample: BaselineSample) -> list[float]:
    return [
        float(sample.total_weight_kg),
        float(sample.variety_hhi),
        float(sample.farm_hhi),
        float(sample.subfarm_hhi),
    ]


def _fit_ridge(
    *,
    train_samples: list[BaselineSample],
    config: BaselineConfig,
) -> tuple[Pipeline, StandardScaler, Ridge]:
    x_train = np.array([ridge_feature_vector(sample) for sample in train_samples], dtype=float)
    y_train = np.array(
        [float(sample.stable_median_3d_peak_kg) for sample in train_samples], dtype=float
    )
    pipeline = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "ridge",
                Ridge(
                    alpha=config.rules.ridge.alpha,
                    fit_intercept=config.rules.ridge.fit_intercept,
                    random_state=config.rules.random_seed,
                ),
            ),
        ]
    )
    pipeline.fit(x_train, y_train)
    scaler = pipeline.named_steps["scaler"]
    ridge = pipeline.named_steps["ridge"]
    return pipeline, scaler, ridge


def _evaluate_ridge_fold(
    *,
    baseline_name: str,
    fold_key: str,
    test_samples: list[BaselineSample],
    train_samples: list[BaselineSample],
    config: BaselineConfig,
) -> list[BacktestResultRow]:
    rows: list[BacktestResultRow] = []
    eligible_train = [
        sample for sample in train_samples if sample.stable_median_3d_peak_kg > 0
    ]
    training_seasons = sorted({sample.season_code for sample in eligible_train})
    if len(eligible_train) < config.rules.evaluation.minimum_training_rows:
        for sample in test_samples:
            feature_values = ridge_feature_vector(sample)
            rows.append(
                excluded_row(
                    baseline_name=baseline_name,
                    target_season_id=sample.season_id,
                    target_season_code=sample.season_code,
                    factory_id=sample.factory_id,
                    factory_name=sample.factory_name,
                    fold_key=fold_key,
                    actual_stable_peak_kg=sample.stable_median_3d_peak_kg,
                    exclusion_reason="insufficient_training_rows",
                    training_season_codes=training_seasons,
                    input_features={
                        feature: value
                        for feature, value in zip(
                            RIDGE_FEATURES,
                            feature_values,
                            strict=True,
                        )
                    },
                )
            )
        return rows

    pipeline, scaler, ridge = _fit_ridge(train_samples=eligible_train, config=config)
    scaler_mean = list(np.asarray(scaler.mean_, dtype=float))
    scaler_scale = list(np.asarray(scaler.scale_, dtype=float))
    ridge_coefficients = list(np.asarray(ridge.coef_, dtype=float))
    ridge_intercept = float(ridge.intercept_)

    for sample in test_samples:
        feature_values = ridge_feature_vector(sample)
        if sample.stable_median_3d_peak_kg <= 0:
            rows.append(
                excluded_row(
                    baseline_name=baseline_name,
                    target_season_id=sample.season_id,
                    target_season_code=sample.season_code,
                    factory_id=sample.factory_id,
                    factory_name=sample.factory_name,
                    fold_key=fold_key,
                    actual_stable_peak_kg=sample.stable_median_3d_peak_kg,
                    exclusion_reason="non_positive_actual_peak",
                    training_season_codes=training_seasons,
                    input_features={
                        feature: value
                        for feature, value in zip(
                            RIDGE_FEATURES,
                            feature_values,
                            strict=True,
                        )
                    },
                    model_metadata={
                        "ridge_alpha": config.rules.ridge.alpha,
                        "scaler_mean": scaler_mean,
                        "scaler_scale": scaler_scale,
                        "ridge_coefficients": ridge_coefficients,
                        "ridge_intercept": ridge_intercept,
                        "training_row_count": len(eligible_train),
                    },
                )
            )
            continue
        prediction = Decimal(
            str(float(pipeline.predict(np.array([feature_values], dtype=float))[0]))
        )
        rows.append(
            evaluated_row(
                baseline_name=baseline_name,
                target_season_id=sample.season_id,
                target_season_code=sample.season_code,
                factory_id=sample.factory_id,
                factory_name=sample.factory_name,
                fold_key=fold_key,
                actual_stable_peak_kg=sample.stable_median_3d_peak_kg,
                predicted_stable_peak_kg=prediction,
                input_features={
                    feature: value
                    for feature, value in zip(
                        RIDGE_FEATURES,
                        feature_values,
                        strict=True,
                    )
                },
                training_season_codes=training_seasons,
                model_metadata={
                    "ridge_alpha": config.rules.ridge.alpha,
                    "fit_intercept": config.rules.ridge.fit_intercept,
                    "scaler_mean": scaler_mean,
                    "scaler_scale": scaler_scale,
                    "ridge_coefficients": ridge_coefficients,
                    "ridge_intercept": ridge_intercept,
                    "training_row_count": len(eligible_train),
                    "raw_prediction": float(prediction),
                },
            )
        )
    return rows


def _evaluate_by_groups(
    *,
    samples: list[BaselineSample],
    config: BaselineConfig,
    grouping_key: Callable[[BaselineSample], str],
    baseline_name: str,
) -> list[BacktestResultRow]:
    rows: list[BacktestResultRow] = []
    group_values: list[str] = []
    seen: set[str] = set()
    for sample in samples:
        key = grouping_key(sample)
        if key not in seen:
            seen.add(key)
            group_values.append(key)
    for group_value in group_values:
        test_samples = [sample for sample in samples if grouping_key(sample) == group_value]
        train_samples = [sample for sample in samples if grouping_key(sample) != group_value]
        rows.extend(
            _evaluate_ridge_fold(
                baseline_name=baseline_name,
                fold_key=group_value,
                test_samples=test_samples,
                train_samples=train_samples,
                config=config,
            )
        )
    return rows


def evaluate_ridge_loso(
    samples: list[BaselineSample],
    config: BaselineConfig,
) -> list[BacktestResultRow]:
    return _evaluate_by_groups(
        samples=samples,
        config=config,
        grouping_key=lambda sample: f"season:{sample.season_code}",
        baseline_name="ridge_structure",
    )


def evaluate_ridge_factory_holdout(
    samples: list[BaselineSample],
    config: BaselineConfig,
) -> list[BacktestResultRow]:
    return _evaluate_by_groups(
        samples=samples,
        config=config,
        grouping_key=lambda sample: f"factory:{sample.factory_id}",
        baseline_name="ridge_structure_factory_holdout",
    )
