from __future__ import annotations

from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.repositories.residual_model import (
    get_residual_training_run,
    list_residual_artifacts,
)
from backend.app.residual_model.artifact import (
    ResidualArtifactValidationError,
    load_trusted_quantile_estimator,
)
from backend.app.residual_model.config import (
    ResidualModelConfig,
    load_residual_model_config_from_snapshot,
)
from backend.app.residual_model.model import TrainedResidualEstimators
from backend.app.residual_model.persistence import (
    ResidualArtifactIntegrityError,
    ResidualModelPersistenceIntegrityError,
    load_residual_prediction_run_by_id,
    load_residual_training_artifacts,
    load_residual_training_run_by_id,
    save_residual_prediction_run,
    save_residual_training_run,
)
from backend.app.residual_model.prediction_features import build_prediction_feature_rows
from backend.app.residual_model.schemas import (
    FeatureValue,
    FeatureVisibilityAudit,
    ResidualPredictionExecutionResult,
    ResidualPredictionRequest,
    ResidualTrainingExecutionResult,
    ResidualTrainingSampleSpec,
)
from backend.app.residual_model.service import (
    predict_residual_correction,
    structural_only_prediction,
    train_residual_model_from_manifest,
)
from backend.app.residual_model.training_manifest import build_residual_training_manifest


class ResidualTrainingApplicationIntegrityError(RuntimeError):
    pass


class ResidualPredictionApplicationIntegrityError(RuntimeError):
    pass


def _prediction_input_snapshot(
    *,
    request: ResidualPredictionRequest,
    training_signature: str,
    feature_schema_version: str,
    feature_schema_hash: str,
    config_hash: str,
    config_snapshot: dict[str, Any],
    feature_snapshot: dict[str, Any] | None,
    feature_audits: list[FeatureVisibilityAudit],
    artifact_hashes: list[str],
    feature_rows: list[tuple[FeatureValue, ...]],
) -> dict[str, Any]:
    return {
        "model_run_id": request.model_run_id,
        "training_signature": training_signature,
        "task9_run_id": request.task9_run_id,
        "task9_result_hash": None,
        "feature_analytics_build_run_id": request.feature_analytics_build_run_id,
        "feature_actual_snapshot": feature_snapshot,
        "supplemental_feature_values": [
            value.model_dump(mode="json") for value in request.supplemental_feature_values
        ],
        "feature_audit_hashes": [audit.audit_hash for audit in feature_audits],
        "feature_rows": [
            [item.model_dump(mode="json") for item in row] for row in feature_rows
        ],
        "feature_schema_version": feature_schema_version,
        "feature_schema_hash": feature_schema_hash,
        "config_hash": config_hash,
        "artifact_hashes": artifact_hashes,
        "projection_version": config_snapshot["projection"]["version"],
        "fallback_policy": config_snapshot["categorical_encoding"]["unknown_policy"],
    }


async def execute_residual_training(
    session: AsyncSession,
    *,
    samples: list[ResidualTrainingSampleSpec],
    config: ResidualModelConfig,
) -> tuple[ResidualTrainingExecutionResult, int]:
    manifest_rows = await build_residual_training_manifest(session, samples=samples)
    result = train_residual_model_from_manifest(rows=manifest_rows, config=config)
    run = await save_residual_training_run(session, result=result, manifest_rows=manifest_rows)
    loaded = await load_residual_training_run_by_id(session, run_id=run.id)
    if loaded is None:
        raise ResidualTrainingApplicationIntegrityError(
            "Residual training run was saved but could not be reloaded"
        )
    if loaded.training_signature != result.training_signature:
        raise ResidualTrainingApplicationIntegrityError(
            "Reloaded residual training run does not match the saved training signature"
        )
    if loaded.manifest_hash != result.manifest_hash or loaded.config_hash != result.config_hash:
        raise ResidualTrainingApplicationIntegrityError(
            "Reloaded residual training run failed manifest/config parity checks"
        )
    if (
        loaded.execution_status == "completed"
        and loaded.eligibility_status == "eligible"
        and len(loaded.artifacts) != 3
    ):
        raise ResidualModelPersistenceIntegrityError(
            "Eligible residual training run reloaded without three quantile artifacts"
        )
    return loaded, run.id


async def execute_residual_prediction(
    session: AsyncSession,
    *,
    request: ResidualPredictionRequest,
) -> tuple[ResidualPredictionExecutionResult, int]:
    training_run_row = await get_residual_training_run(session, run_id=request.model_run_id)
    if training_run_row is None:
        raise ResidualPredictionApplicationIntegrityError("Residual training run was not found")
    model_run: ResidualTrainingExecutionResult | None
    preload_artifact_error: ResidualArtifactIntegrityError | None = None
    try:
        model_run = await load_residual_training_run_by_id(session, run_id=request.model_run_id)
    except ResidualArtifactIntegrityError as exc:
        model_run = None
        preload_artifact_error = exc
    if model_run is None and preload_artifact_error is None:
        raise ResidualPredictionApplicationIntegrityError("Residual training run was not found")

    (
        task9_output,
        structural_rows,
        feature_rows,
        feature_audits,
        warnings,
        blockers,
        feature_snapshot,
    ) = await build_prediction_feature_rows(
        session,
        task9_run_id=request.task9_run_id,
        feature_analytics_build_run_id=request.feature_analytics_build_run_id,
        supplemental_feature_values=request.supplemental_feature_values,
    )

    artifact_hashes: list[str] = []
    model_run_snapshot = (
        model_run.input_snapshot
        if model_run is not None
        else training_run_row.input_snapshot
    )
    config = load_residual_model_config_from_snapshot(model_run_snapshot["config_snapshot"])
    result: ResidualPredictionExecutionResult
    fallback_reason: str | None = None
    feature_names: list[str] = []
    category_encodings: list[Any] = []
    estimators: TrainedResidualEstimators | None = None

    if (
        preload_artifact_error is not None
        or model_run is None
        or model_run.execution_status != "completed"
        or model_run.eligibility_status != "eligible"
        or blockers
    ):
        if blockers:
            fallback_reason = "feature_visibility_failed"
        elif preload_artifact_error is not None:
            fallback_reason = "artifact_validation_failed"
        else:
            fallback_reason = "model_not_eligible"
    else:
        try:
            artifact_rows = await list_residual_artifacts(
                session,
                training_run_id=training_run_row.id,
            )
        except SQLAlchemyError as exc:
            raise ResidualPredictionApplicationIntegrityError(
                "Authoritative residual artifact identities could not be loaded"
            ) from exc
        artifact_hashes = [item.artifact_sha256 for item in artifact_rows]
        try:
            artifacts = await load_residual_training_artifacts(
                session,
                run_id=training_run_row.id,
                artifacts_rows=tuple(artifact_rows),
            )
            if len(artifacts) != 3:
                fallback_reason = "artifact_count_mismatch"
            else:
                estimators = TrainedResidualEstimators(
                    p50=load_trusted_quantile_estimator(
                        artifact=next(item for item in artifacts if item.quantile_label == "P50"),
                        expected_model_family=training_run_row.model_family,
                        expected_model_version=training_run_row.model_version,
                        expected_artifact_schema_version=training_run_row.artifact_schema_version,
                        expected_feature_schema_version=training_run_row.feature_schema_version,
                        expected_feature_schema_hash=training_run_row.feature_schema_hash,
                        expected_config_hash=training_run_row.config_hash,
                        expected_training_signature=model_run.training_signature,
                        expected_manifest_hash=model_run.manifest_hash,
                        expected_quantile_label="P50",
                    ),
                    p80=load_trusted_quantile_estimator(
                        artifact=next(item for item in artifacts if item.quantile_label == "P80"),
                        expected_model_family=training_run_row.model_family,
                        expected_model_version=training_run_row.model_version,
                        expected_artifact_schema_version=training_run_row.artifact_schema_version,
                        expected_feature_schema_version=training_run_row.feature_schema_version,
                        expected_feature_schema_hash=training_run_row.feature_schema_hash,
                        expected_config_hash=training_run_row.config_hash,
                        expected_training_signature=model_run.training_signature,
                        expected_manifest_hash=model_run.manifest_hash,
                        expected_quantile_label="P80",
                    ),
                    p90=load_trusted_quantile_estimator(
                        artifact=next(item for item in artifacts if item.quantile_label == "P90"),
                        expected_model_family=training_run_row.model_family,
                        expected_model_version=training_run_row.model_version,
                        expected_artifact_schema_version=training_run_row.artifact_schema_version,
                        expected_feature_schema_version=training_run_row.feature_schema_version,
                        expected_feature_schema_hash=training_run_row.feature_schema_hash,
                        expected_config_hash=training_run_row.config_hash,
                        expected_training_signature=model_run.training_signature,
                        expected_manifest_hash=model_run.manifest_hash,
                        expected_quantile_label="P90",
                    ),
                )
                category_encodings = artifacts[0].metadata.category_encodings
                feature_names = list(model_run.metrics.get("feature_names", []))
                fallback_reason = None
        except (
            ResidualArtifactValidationError,
            ResidualArtifactIntegrityError,
            ResidualModelPersistenceIntegrityError,
        ):
            fallback_reason = "artifact_validation_failed"

    input_snapshot = _prediction_input_snapshot(
        request=request,
        training_signature=training_run_row.training_signature,
        feature_schema_version=training_run_row.feature_schema_version,
        feature_schema_hash=training_run_row.feature_schema_hash,
        config_hash=training_run_row.config_hash,
        config_snapshot=training_run_row.config_snapshot,
        feature_snapshot=(
            feature_snapshot.model_dump(mode="json")
            if feature_snapshot is not None
            else None
        ),
        feature_audits=feature_audits,
        artifact_hashes=artifact_hashes,
        feature_rows=feature_rows,
    ) | {"task9_result_hash": task9_output.result_hash}

    if fallback_reason is not None:
        result = structural_only_prediction(
            model_run_id=training_run_row.id,
            task9_run_id=request.task9_run_id,
            task9_result_hash=task9_output.result_hash,
            config_hash=training_run_row.config_hash,
            structural_rows=structural_rows,
            fallback_reason=fallback_reason,
            warnings=warnings,
            blockers=blockers,
            input_snapshot=input_snapshot,
        )
    else:
        if estimators is None:
            raise ResidualPredictionApplicationIntegrityError(
                "Residual prediction estimators were not resolved for residual_corrected mode"
            )
        result = predict_residual_correction(
            model_run_id=training_run_row.id,
            task9_run_id=request.task9_run_id,
            task9_result_hash=task9_output.result_hash,
            config=config,
            feature_names=feature_names,
            category_encodings=category_encodings,
            structural_rows=structural_rows,
            feature_rows=feature_rows,
            feature_audits=feature_audits,
            estimators=estimators,
            warnings=warnings,
            blockers=blockers,
            fallback_reason=None,
            input_snapshot=input_snapshot,
        )

    run = await save_residual_prediction_run(
        session,
        result=result,
        feature_schema_version=training_run_row.feature_schema_version,
        feature_schema_hash=training_run_row.feature_schema_hash,
        artifact_hashes=artifact_hashes,
    )
    loaded = await load_residual_prediction_run_by_id(session, run_id=run.id)
    if loaded is None:
        raise ResidualPredictionApplicationIntegrityError(
            "Residual prediction run was saved but could not be reloaded"
        )
    if loaded.model_dump(mode="json") != result.model_dump(mode="json"):
        raise ResidualPredictionApplicationIntegrityError(
            "Reloaded residual prediction run failed parity checks"
        )
    return loaded, run.id
