from __future__ import annotations

from pathlib import Path

import numpy as np


def test_quantile_estimators_use_correct_quantiles() -> None:
    from backend.app.residual_model.config import load_residual_model_config
    from backend.app.residual_model.model import train_quantile_estimators

    config = load_residual_model_config(
        Path("/Users/charles/Documents/智能agent开发/configs/residual_model.yaml")
    )
    features = np.array([[1.0], [2.0], [3.0], [4.0]])
    labels = np.array([1.0, 2.0, 3.0, 4.0])
    estimators = train_quantile_estimators(
        config=config,
        features=features,
        labels=labels,
    )

    assert estimators.p50.loss == "quantile"
    assert estimators.p50.quantile == 0.5
    assert estimators.p80.quantile == 0.8
    assert estimators.p90.quantile == 0.9


def test_resolved_config_contains_all_estimator_parameters() -> None:
    from backend.app.residual_model.config import load_residual_model_config
    from backend.app.residual_model.model import (
        serialize_quantile_artifacts,
        train_quantile_estimators,
    )

    config = load_residual_model_config(
        Path("/Users/charles/Documents/智能agent开发/configs/residual_model.yaml")
    )
    features = np.array([[1.0], [2.0], [3.0], [4.0]])
    labels = np.array([1.0, 2.0, 3.0, 4.0])
    estimators = train_quantile_estimators(
        config=config,
        features=features,
        labels=labels,
    )
    artifacts = serialize_quantile_artifacts(
        estimators=estimators,
        config=config,
        training_signature="a" * 64,
        manifest_hash="b" * 64,
        category_encodings=[],
    )
    metadata = artifacts[0].metadata

    assert metadata.model_family == "hist_gradient_boosting_quantile"
    assert metadata.feature_schema_version == "task10-features-v1"
    assert metadata.binary_format == "joblib_bundle"
    assert metadata.quantile_label == "P50"
    assert len(metadata.metadata_sha256) == 64
