from __future__ import annotations

from io import BytesIO

import joblib  # type: ignore[import-untyped]
import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor

from backend.app.residual_model.canonical import sha256_hex
from backend.app.residual_model.schemas import PersistableResidualArtifact


class ResidualArtifactValidationError(RuntimeError):
    pass


def load_trusted_quantile_estimator(
    *,
    artifact: PersistableResidualArtifact,
    expected_model_family: str,
    expected_artifact_schema_version: str,
    expected_feature_schema_version: str,
    expected_config_hash: str,
    expected_quantile_label: str,
) -> HistGradientBoostingRegressor:
    metadata = artifact.metadata
    if metadata.model_family != expected_model_family:
        raise ResidualArtifactValidationError("artifact model_family mismatch")
    if metadata.artifact_schema_version != expected_artifact_schema_version:
        raise ResidualArtifactValidationError("artifact schema version mismatch")
    if metadata.feature_schema_version != expected_feature_schema_version:
        raise ResidualArtifactValidationError("artifact feature schema version mismatch")
    if metadata.config_hash != expected_config_hash:
        raise ResidualArtifactValidationError("artifact config hash mismatch")
    if metadata.quantile_label != expected_quantile_label:
        raise ResidualArtifactValidationError("artifact quantile label mismatch")
    if metadata.binary_sha256 != sha256_hex(artifact.artifact_bytes.hex()):
        raise ResidualArtifactValidationError("artifact bytes sha256 mismatch")
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
    return loaded
