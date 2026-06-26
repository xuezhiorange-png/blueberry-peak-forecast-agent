from __future__ import annotations

import hashlib
from io import BytesIO

import joblib  # type: ignore[import-untyped]
import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor

from backend.app.residual_model.canonical import canonical_payload_hash
from backend.app.residual_model.schemas import PersistableResidualArtifact


class ResidualArtifactValidationError(RuntimeError):
    pass


def _metadata_payload(artifact: PersistableResidualArtifact) -> dict[str, object]:
    return artifact.metadata.model_dump(mode="python", exclude={"metadata_sha256"})


def load_trusted_quantile_estimator(
    *,
    artifact: PersistableResidualArtifact,
    expected_model_family: str,
    expected_model_version: str,
    expected_artifact_schema_version: str,
    expected_feature_schema_version: str,
    expected_feature_schema_hash: str,
    expected_config_hash: str,
    expected_training_signature: str,
    expected_manifest_hash: str,
    expected_quantile_label: str,
) -> HistGradientBoostingRegressor:
    metadata = artifact.metadata
    if metadata.model_family != expected_model_family:
        raise ResidualArtifactValidationError("artifact model_family mismatch")
    if metadata.model_version != expected_model_version:
        raise ResidualArtifactValidationError("artifact model_version mismatch")
    if metadata.artifact_schema_version != expected_artifact_schema_version:
        raise ResidualArtifactValidationError("artifact schema version mismatch")
    if metadata.feature_schema_version != expected_feature_schema_version:
        raise ResidualArtifactValidationError("artifact feature schema version mismatch")
    if metadata.feature_schema_hash != expected_feature_schema_hash:
        raise ResidualArtifactValidationError("artifact feature schema hash mismatch")
    if metadata.config_hash != expected_config_hash:
        raise ResidualArtifactValidationError("artifact config hash mismatch")
    if metadata.training_signature != expected_training_signature:
        raise ResidualArtifactValidationError("artifact training signature mismatch")
    if metadata.manifest_hash != expected_manifest_hash:
        raise ResidualArtifactValidationError("artifact manifest hash mismatch")
    if metadata.quantile_label != expected_quantile_label:
        raise ResidualArtifactValidationError("artifact quantile label mismatch")
    if metadata.binary_format != "joblib_bundle":
        raise ResidualArtifactValidationError("artifact binary format mismatch")
    if metadata.binary_sha256 != hashlib.sha256(artifact.artifact_bytes).hexdigest():
        raise ResidualArtifactValidationError("artifact bytes sha256 mismatch")
    expected_metadata_sha = canonical_payload_hash(_metadata_payload(artifact))
    if metadata.metadata_sha256 != expected_metadata_sha:
        raise ResidualArtifactValidationError("artifact metadata payload mismatch")
    if metadata.sklearn_version != sklearn.__version__:
        raise ResidualArtifactValidationError("artifact sklearn version mismatch")
    if metadata.numpy_version != np.__version__:
        raise ResidualArtifactValidationError("artifact numpy version mismatch")

    loaded = joblib.load(BytesIO(artifact.artifact_bytes))
    if not isinstance(loaded, HistGradientBoostingRegressor):
        raise ResidualArtifactValidationError("artifact estimator type mismatch")
    if loaded.loss != "quantile":
        raise ResidualArtifactValidationError("artifact loss mismatch")
    expected_quantile = {"P50": 0.5, "P80": 0.8, "P90": 0.9}[expected_quantile_label]
    if loaded.quantile != expected_quantile:
        raise ResidualArtifactValidationError("artifact estimator quantile mismatch")
    expected_parameters = metadata.estimator_parameters
    loaded_parameters = {
        "loss": loaded.loss,
        "quantile": loaded.quantile,
        "learning_rate": loaded.learning_rate,
        "max_iter": loaded.max_iter,
        "max_leaf_nodes": loaded.max_leaf_nodes,
        "max_depth": loaded.max_depth,
        "min_samples_leaf": loaded.min_samples_leaf,
        "l2_regularization": loaded.l2_regularization,
        "early_stopping": loaded.early_stopping,
        "validation_fraction": loaded.validation_fraction,
        "n_iter_no_change": loaded.n_iter_no_change,
        "tol": loaded.tol,
        "random_state": loaded.random_state,
    }
    if loaded_parameters != expected_parameters:
        raise ResidualArtifactValidationError("artifact estimator parameters mismatch")
    return loaded
