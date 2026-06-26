from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.repositories.residual_model import get_residual_training_run
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
    model_run: ResidualTrainingExecutionResult,
    feature_snapshot: dict[str, Any] | None,
    feature_audits: list[FeatureVisibilityAudit],
    artifact_hashes: list[str],
    feature_rows: list[tuple[FeatureValue, ...]],
    fallback_reason: str | None,
) -> dict[str, Any]:
    return {
        "model_run_id": request.model_run_id,
        "training_signature": model_run.training_signature,
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
        "feature_schema_version": model_run.feature_schema_version,
        "config_hash": model_run.config_hash,
        "artifact_hashes": artifact_hashes,
        "projection_version": model_run.input_snapshot["config_snapshot"]["projection"]["version"],
        "fallback_policy": model_run.input_snapshot["config_snapshot"]["categorical_encoding"][
            "unknown_policy"
        ],
        "fallback_reason": fallback_reason,
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
    model_run = await load_residual_training_run_by_id(session, run_id=request.model_run_id)
    if training_run_row is None or model_run is None:
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
    config = load_residual_model_config_from_snapshot(model_run.input_snapshot["config_snapshot"])
    result: ResidualPredictionExecutionResult

    if (
        model_run.execution_status != "completed"
        or model_run.eligibility_status != "eligible"
        or blockers
    ):
        result = structural_only_prediction(
            model_run_id=training_run_row.id,
            task9_run_id=request.task9_run_id,
            task9_result_hash=task9_output.result_hash,
            config_hash=training_run_row.config_hash,
            structural_rows=structural_rows,
            fallback_reason=(
                "feature_visibility_failed"
                if blockers
                else "model_not_eligible"
            ),
        )
    else:
        try:
            artifacts = await load_residual_training_artifacts(session, run_id=training_run_row.id)
            artifact_hashes = [item.metadata.binary_sha256 for item in artifacts]
            if len(artifacts) != 3:
                result = structural_only_prediction(
                    model_run_id=training_run_row.id,
                    task9_run_id=request.task9_run_id,
                    task9_result_hash=task9_output.result_hash,
                    config_hash=training_run_row.config_hash,
                    structural_rows=structural_rows,
                    fallback_reason="artifact_count_mismatch",
                )
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
                )
        except (ResidualArtifactValidationError, ResidualModelPersistenceIntegrityError):
            result = structural_only_prediction(
                model_run_id=training_run_row.id,
                task9_run_id=request.task9_run_id,
                task9_result_hash=task9_output.result_hash,
                config_hash=training_run_row.config_hash,
                structural_rows=structural_rows,
                fallback_reason="artifact_validation_failed",
            )

    if warnings or blockers:
        result = result.model_copy(
            update={
                "warnings": tuple(sorted(set(result.warnings) | set(warnings))),
                "blockers": tuple(sorted(set(result.blockers) | set(blockers))),
            }
        )
    result = result.model_copy(
        update={
            "task9_result_hash": task9_output.result_hash,
            "input_snapshot": _prediction_input_snapshot(
                request=request,
                model_run=model_run,
                feature_snapshot=(
                    feature_snapshot.model_dump(mode="json")
                    if feature_snapshot is not None
                    else None
                ),
                feature_audits=feature_audits,
                artifact_hashes=artifact_hashes,
                feature_rows=feature_rows,
                fallback_reason=result.fallback_reason,
            )
            | {"task9_result_hash": task9_output.result_hash},
        }
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
