"""Section 12: Missing regression tests — artifact integrity tests.

Tests that the unified artifact trust gate (load_and_validate_trusted_residual_artifacts)
correctly detects various corruption patterns.
"""

from __future__ import annotations

import hashlib
import json
from io import BytesIO

import joblib
import numpy as np
import pytest
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.models.residual_model import (
    ResidualModelArtifact,
    ResidualModelExecutionAttempt,
    ResidualModelManifestRow,
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.repositories.residual_model import list_residual_artifacts
from backend.app.residual_model.artifact import (
    ResidualArtifactIntegrityError,
    load_trusted_quantile_estimator,
)
from backend.app.residual_model.canonical import canonical_payload_hash
from backend.app.residual_model.config import load_residual_model_config
from backend.app.residual_model.model import (
    serialize_quantile_artifacts,
    train_quantile_estimators,
)
from backend.app.residual_model.persistence import (
    load_and_validate_trusted_residual_artifacts,
    save_residual_training_run,
)
from backend.app.residual_model.schemas import PersistableResidualArtifact
from backend.tests.residual_model.support import residual_model_config_path
from backend.tests.residual_model.test_persistence import (
    _eligible_training,
)

RESIDUAL_TABLES = [
    ResidualModelTrainingRun.__table__,
    ResidualModelManifestRow.__table__,
    ResidualModelArtifact.__table__,
    ResidualModelPredictionRun.__table__,
    ResidualModelPredictionRow.__table__,
    ResidualModelExecutionAttempt.__table__,
]


@pytest.fixture
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: ResidualModelTrainingRun.metadata.create_all(
                sync_conn, tables=RESIDUAL_TABLES
            )
        )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


def _artifact() -> PersistableResidualArtifact:
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
    return artifact


def _config():
    return load_residual_model_config(residual_model_config_path())


# ── 1. Coordinated DB/metadata hash mutation ──────────────────────────────


@pytest.mark.asyncio
async def test_artifact_coordinated_db_and_metadata_hash_mutation(
    sqlite_session: AsyncSession,
) -> None:
    """Both artifact_bytes AND artifact_sha256 are modified together
    (consistent with each other but different from original).
    """
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    assert run.id > 0

    await sqlite_session.execute(
        text(
            "UPDATE residual_model_artifact "
            "SET artifact_bytes = :new_bytes, "
            "    artifact_sha256 = :new_sha "
            "WHERE training_run_id = :run_id AND quantile_label = 'P50'"
        ),
        {
            "new_bytes": b"corrupted-consistent-bytes",
            "new_sha": hashlib.sha256(b"corrupted-consistent-bytes").hexdigest(),
            "run_id": run.id,
        },
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualArtifactIntegrityError):
        await load_and_validate_trusted_residual_artifacts(sqlite_session, run_id=run.id)


# ── 2. Invalid bytes (valid SHA but invalid joblib bytes) ─────────────────


def test_artifact_invalid_bytes_valid_sha() -> None:
    """Artifact bytes are invalid joblib but SHA is computed correctly.
    load_trusted_quantile_estimator should fail during deserialization.
    """
    config = _config()
    artifact = _artifact()
    garbage_bytes = b"this is not a valid joblib file"
    valid_sha = hashlib.sha256(garbage_bytes).hexdigest()
    bad_artifact = artifact.model_copy(
        update={
            "artifact_bytes": garbage_bytes,
            "metadata": artifact.metadata.model_copy(
                update={
                    "binary_sha256": valid_sha,
                }
            ),
        }
    )

    with pytest.raises(ResidualArtifactIntegrityError):
        load_trusted_quantile_estimator(
            artifact=bad_artifact,
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


# ── 3. Wrong estimator type (valid joblib but wrong class) ────────────────


def test_artifact_wrong_estimator_type() -> None:
    """Valid joblib bytes containing a different estimator class."""
    config = _config()
    wrong_estimator = LinearRegression()
    wrong_estimator.fit([[1.0], [2.0]], [1.0, 2.0])
    wrong_buffer = BytesIO()
    joblib.dump(wrong_estimator, wrong_buffer)
    wrong_bytes = wrong_buffer.getvalue()
    wrong_sha = hashlib.sha256(wrong_bytes).hexdigest()

    valid_artifact = _artifact()
    bad_metadata = valid_artifact.metadata.model_copy(
        update={
            "binary_sha256": wrong_sha,
            "binary_format": "joblib_bundle",
        }
    )
    # Fix metadata_sha256 to make the metadata payload consistent
    fixed_metadata_sha = canonical_payload_hash(
        bad_metadata.model_dump(mode="python", exclude={"metadata_sha256"})
    )
    bad_metadata = bad_metadata.model_copy(
        update={
            "metadata_sha256": fixed_metadata_sha,
        }
    )
    bad_artifact = valid_artifact.model_copy(
        update={
            "artifact_bytes": wrong_bytes,
            "metadata": bad_metadata,
        }
    )

    with pytest.raises(ResidualArtifactIntegrityError):
        load_trusted_quantile_estimator(
            artifact=bad_artifact,
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


# ── 4. Wrong estimator parameters (valid estimator but wrong params) ──────


def test_artifact_wrong_estimator_parameters() -> None:
    """Valid HistGradientBoostingRegressor but with different parameters
    than what metadata claims.
    """
    config = _config()
    # Train with different params
    wrong_estimator = HistGradientBoostingRegressor(
        loss="quantile",
        quantile=0.5,
        learning_rate=0.5,
        max_iter=500,
        random_state=42,
    )
    wrong_estimator.fit([[1.0], [2.0]], [1.0, 2.0])
    wrong_buffer = BytesIO()
    joblib.dump(wrong_estimator, wrong_buffer)
    wrong_bytes = wrong_buffer.getvalue()
    wrong_sha = hashlib.sha256(wrong_bytes).hexdigest()

    valid_artifact = _artifact()
    metadata_that_claims_default = valid_artifact.metadata.model_copy(
        update={
            "binary_sha256": wrong_sha,
            "estimator_parameters": {
                **valid_artifact.metadata.estimator_parameters,
                "learning_rate": 0.1,
            },
        }
    )
    # Fix metadata_sha256 for consistent metadata payload
    fixed_metadata_sha = canonical_payload_hash(
        metadata_that_claims_default.model_dump(mode="python", exclude={"metadata_sha256"})
    )
    metadata_that_claims_default = metadata_that_claims_default.model_copy(
        update={
            "metadata_sha256": fixed_metadata_sha,
        }
    )
    bad_artifact = valid_artifact.model_copy(
        update={
            "artifact_bytes": wrong_bytes,
            "metadata": metadata_that_claims_default,
        }
    )

    with pytest.raises(ResidualArtifactIntegrityError, match="parameters"):
        load_trusted_quantile_estimator(
            artifact=bad_artifact,
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


# ── 5. Runtime version mismatch ──────────────────────────────────────────


def test_artifact_runtime_version_mismatch() -> None:
    """Artifact metadata claims a different sklearn version
    than the current runtime.
    """
    config = _config()
    valid_artifact = _artifact()

    bad_metadata = valid_artifact.metadata.model_copy(
        update={
            "sklearn_version": "0.24.0",
        }
    )
    fixed_metadata_sha = canonical_payload_hash(
        bad_metadata.model_dump(mode="python", exclude={"metadata_sha256"})
    )
    bad_metadata = bad_metadata.model_copy(
        update={
            "metadata_sha256": fixed_metadata_sha,
        }
    )
    bad_artifact = valid_artifact.model_copy(
        update={
            "metadata": bad_metadata,
        }
    )

    with pytest.raises(ResidualArtifactIntegrityError, match="sklearn"):
        load_trusted_quantile_estimator(
            artifact=bad_artifact,
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


# ── 6. Category encoding coordinated mutation ────────────────────────────


@pytest.mark.asyncio
async def test_artifact_category_encoding_coordinated_mutation(
    sqlite_session: AsyncSession,
) -> None:
    """Category encodings mutated in artifact metadata JSON and in
    the training run's category_encoding_snapshot consistently.
    """
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)

    artifacts = await list_residual_artifacts(sqlite_session, training_run_id=run.id)
    assert len(artifacts) == 3

    p50_artifact = next(a for a in artifacts if a.quantile_label == "P50")
    metadata = dict(p50_artifact.artifact_metadata_json)
    metadata["category_encodings"] = [
        {
            "feature_name": "destination_factory_category",
            "ordered_known_categories": ["north", "south", "east"],
            "unknown_bucket_code": 2,
            "missing_bucket_code": -1,
            "encoding_version": "v1",
        }
    ]
    metadata["metadata_sha256"] = canonical_payload_hash(
        {k: v for k, v in metadata.items() if k != "metadata_sha256"}
    )

    await sqlite_session.execute(
        text("UPDATE residual_model_artifact SET metadata = :metadata WHERE id = :artifact_id"),
        {
            "metadata": json.dumps(metadata),
            "artifact_id": p50_artifact.id,
        },
    )
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET category_encoding_snapshot = :encodings "
            "WHERE id = :run_id"
        ),
        {
            "encodings": json.dumps(metadata["category_encodings"]),
            "run_id": run.id,
        },
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualArtifactIntegrityError):
        await load_and_validate_trusted_residual_artifacts(sqlite_session, run_id=run.id)
