from __future__ import annotations

import numpy as np
import pytest

from backend.app.residual_model.artifact import (
    ResidualArtifactValidationError,
    load_trusted_quantile_estimator,
)
from backend.app.residual_model.config import load_residual_model_config
from backend.app.residual_model.model import serialize_quantile_artifacts, train_quantile_estimators
from backend.tests.residual_model.support import residual_model_config_path


def _artifact():
    config = load_residual_model_config(residual_model_config_path())
    features = np.array([[1.0], [2.0], [3.0], [4.0]])
    labels = np.array([1.0, 2.0, 3.0, 4.0])
    estimators = train_quantile_estimators(config=config, features=features, labels=labels)
    artifact = serialize_quantile_artifacts(
        estimators=estimators,
        config=config,
        training_signature="a" * 64,
        manifest_hash="b" * 64,
        feature_schema_hash="c" * 64,
        category_encodings=[],
    )[0]
    return config, artifact


def test_load_trusted_quantile_estimator() -> None:
    config, artifact = _artifact()

    estimator = load_trusted_quantile_estimator(
        artifact=artifact,
        expected_model_family=config.rules.model_family,
        expected_model_version=config.rules.model_version,
        expected_artifact_schema_version=config.rules.artifact_schema_version,
        expected_feature_schema_version=config.rules.feature_schema_version,
        expected_feature_schema_hash="c" * 64,
        expected_config_hash=config.config_hash,
        expected_training_signature="a" * 64,
        expected_manifest_hash="b" * 64,
        expected_quantile_label="P50",
    )

    assert estimator.loss == "quantile"
    assert estimator.quantile == 0.5


def test_artifact_hash_validation() -> None:
    config, artifact = _artifact()
    broken = artifact.model_copy(update={"artifact_bytes": artifact.artifact_bytes + b"broken"})

    with pytest.raises(ResidualArtifactValidationError, match="sha256"):
        load_trusted_quantile_estimator(
            artifact=broken,
            expected_model_family=config.rules.model_family,
            expected_model_version=config.rules.model_version,
            expected_artifact_schema_version=config.rules.artifact_schema_version,
            expected_feature_schema_version=config.rules.feature_schema_version,
            expected_feature_schema_hash="c" * 64,
            expected_config_hash=config.config_hash,
            expected_training_signature="a" * 64,
            expected_manifest_hash="b" * 64,
            expected_quantile_label="P50",
        )


def test_artifact_schema_version_validation() -> None:
    config, artifact = _artifact()

    with pytest.raises(ResidualArtifactValidationError, match="schema version"):
        load_trusted_quantile_estimator(
            artifact=artifact,
            expected_model_family=config.rules.model_family,
            expected_model_version=config.rules.model_version,
            expected_artifact_schema_version="task10-artifact-v2",
            expected_feature_schema_version=config.rules.feature_schema_version,
            expected_feature_schema_hash="c" * 64,
            expected_config_hash=config.config_hash,
            expected_training_signature="a" * 64,
            expected_manifest_hash="b" * 64,
            expected_quantile_label="P50",
        )
