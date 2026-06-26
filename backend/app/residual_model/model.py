from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import joblib  # type: ignore[import-untyped]
import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor

from backend.app.residual_model.canonical import canonical_payload_hash, sha256_hex
from backend.app.residual_model.config import ResidualModelConfig
from backend.app.residual_model.schemas import (
    CategoryEncoding,
    PersistableResidualArtifact,
    ResidualArtifactMetadata,
)


@dataclass(frozen=True)
class TrainedResidualEstimators:
    p50: HistGradientBoostingRegressor
    p80: HistGradientBoostingRegressor
    p90: HistGradientBoostingRegressor


def _estimator(config: ResidualModelConfig, *, quantile: float) -> HistGradientBoostingRegressor:
    rules = config.rules.estimator
    return HistGradientBoostingRegressor(
        loss="quantile",
        quantile=quantile,
        learning_rate=rules.learning_rate,
        max_iter=rules.max_iter,
        max_leaf_nodes=rules.max_leaf_nodes,
        max_depth=rules.max_depth,
        min_samples_leaf=rules.min_samples_leaf,
        l2_regularization=rules.l2_regularization,
        early_stopping=rules.early_stopping,
        validation_fraction=rules.validation_fraction,
        n_iter_no_change=rules.n_iter_no_change,
        tol=rules.tol,
        random_state=config.rules.random_seed,
    )


def train_quantile_estimators(
    *,
    config: ResidualModelConfig,
    features: np.ndarray,
    labels: np.ndarray,
    sample_weight: np.ndarray | None = None,
) -> TrainedResidualEstimators:
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
    p50 = _estimator(config, quantile=0.5)
    p80 = _estimator(config, quantile=0.8)
    p90 = _estimator(config, quantile=0.9)
    p50.fit(features, labels, sample_weight=sample_weight)
    p80.fit(features, labels, sample_weight=sample_weight)
    p90.fit(features, labels, sample_weight=sample_weight)
    return TrainedResidualEstimators(p50=p50, p80=p80, p90=p90)


def predict_quantiles(
    *,
    estimators: TrainedResidualEstimators,
    features: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (
        estimators.p50.predict(features),
        estimators.p80.predict(features),
        estimators.p90.predict(features),
    )


def serialize_estimator(estimator: HistGradientBoostingRegressor) -> bytes:
    buffer = BytesIO()
    joblib.dump(estimator, buffer)
    return buffer.getvalue()


def build_artifact_metadata(
    *,
    quantile_label: str,
    config: ResidualModelConfig,
    training_signature: str,
    manifest_hash: str,
    artifact_bytes: bytes,
    category_encodings: list[CategoryEncoding],
) -> ResidualArtifactMetadata:
    binary_sha256 = sha256_hex(artifact_bytes.hex())
    metadata_payload: dict[str, Any] = {
        "artifact_schema_version": config.rules.artifact_schema_version,
        "model_family": config.rules.model_family,
        "model_version": config.rules.model_version,
        "feature_schema_version": config.rules.feature_schema_version,
        "category_encoding_version": config.rules.categorical_encoding_version,
        "projection_version": config.rules.projection_version,
        "config_hash": config.config_hash,
        "training_signature": training_signature,
        "manifest_hash": manifest_hash,
        "quantiles": list(config.rules.quantiles),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "sklearn_version": sklearn.__version__,
        "created_by_service_version": config.rules.model_version,
        "binary_format": "joblib_bundle",
        "binary_sha256": binary_sha256,
        "category_encodings": [item.model_dump(mode="json") for item in category_encodings],
    }
    metadata_sha256 = canonical_payload_hash(metadata_payload)
    return ResidualArtifactMetadata(
        **metadata_payload,
        quantile_label=quantile_label,
        metadata_sha256=metadata_sha256,
    )


def serialize_quantile_artifacts(
    *,
    estimators: TrainedResidualEstimators,
    config: ResidualModelConfig,
    training_signature: str,
    manifest_hash: str,
    category_encodings: list[CategoryEncoding],
) -> tuple[PersistableResidualArtifact, ...]:
    artifacts: list[PersistableResidualArtifact] = []
    for quantile_label, estimator in (
        ("P50", estimators.p50),
        ("P80", estimators.p80),
        ("P90", estimators.p90),
    ):
        artifact_bytes = serialize_estimator(estimator)
        artifacts.append(
            PersistableResidualArtifact(
                quantile_label=quantile_label,
                artifact_bytes=artifact_bytes,
                metadata=build_artifact_metadata(
                    quantile_label=quantile_label,
                    config=config,
                    training_signature=training_signature,
                    manifest_hash=manifest_hash,
                    artifact_bytes=artifact_bytes,
                    category_encodings=category_encodings,
                ),
            )
        )
    return tuple(artifacts)
