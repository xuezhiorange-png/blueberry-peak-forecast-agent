from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.repositories.residual_model import (
    complete_residual_execution_attempt,
    create_residual_execution_attempt,
    fail_residual_execution_attempt,
    get_residual_training_run,
    list_residual_artifacts,
    update_residual_execution_attempt_stage,
)
from backend.app.residual_model.artifact import (
    ResidualArtifactIntegrityError,
    load_trusted_quantile_estimator,
)
from backend.app.residual_model.config import (
    ResidualModelConfig,
    load_residual_model_config_from_snapshot,
)
from backend.app.residual_model.model import TrainedResidualEstimators
from backend.app.residual_model.persistence import (
    ResidualModelPersistenceIntegrityError,
    load_and_validate_trusted_residual_artifacts,
    load_residual_prediction_run_by_id,
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


def _sanitize_error(exc: Exception) -> str:
    """Strip absolute paths and traceback details, keep error type + message."""
    msg = " ".join(str(exc).replace("\r", " ").replace("\n", " ").split())[:500]
    return f"{type(exc).__name__}: {msg}"


def _prediction_input_snapshot(
    *,
    request: ResidualPredictionRequest,
    training_run_row: Any,
    feature_snapshot: dict[str, Any] | None,
    feature_audits: list[FeatureVisibilityAudit],
    artifact_hashes: list[str],
    feature_rows: list[tuple[FeatureValue, ...]],
) -> dict[str, Any]:
    return {
        "model_run_id": request.model_run_id,
        "training_signature": training_run_row.training_signature,
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
        "feature_schema_version": training_run_row.feature_schema_version,
        "feature_schema_hash": training_run_row.feature_schema_hash,
        "config_hash": training_run_row.config_hash,
        "artifact_hashes": artifact_hashes,
        "projection_version": training_run_row.config_snapshot["projection"]["version"],
        "fallback_policy": training_run_row.config_snapshot["categorical_encoding"][
            "unknown_policy"
        ],
    }


async def execute_residual_training(
    session: AsyncSession,
    *,
    samples: list[ResidualTrainingSampleSpec],
    config: ResidualModelConfig,
) -> tuple[ResidualTrainingExecutionResult, int]:
    """Execute residual training with Section 6 attempt lifecycle."""
    # SECTION 6: Persist attempt record BEFORE manifest build
    attempt = await create_residual_execution_attempt(
        session,
        attempt_type="training",
        execution_status="running",
        current_stage="manifest_build",
        requested_inputs={
            "sample_count": len(samples),
            "season_ids": list({s.task9_run_id for s in samples}),
        },
        config_identity={
            "model_family": config.rules.model_family,
            "model_version": config.rules.model_version,
            "config_hash": config.config_hash,
        },
        upstream_requested_ids={
            "task9_run_ids": list({s.task9_run_id for s in samples}),
            "label_analytics_build_run_ids": list(
                {s.label_analytics_build_run_id for s in samples}
            ),
            "feature_analytics_build_run_ids": list(
                {s.feature_analytics_build_run_id for s in samples}
            ),
        },
    )
    attempt_id = attempt.id

    try:
        manifest_rows = await build_residual_training_manifest(session, samples=samples)
        await update_residual_execution_attempt_stage(
            session, attempt_id=attempt_id, current_stage="model_training"
        )

        result = train_residual_model_from_manifest(rows=manifest_rows, config=config)

        await update_residual_execution_attempt_stage(
            session, attempt_id=attempt_id, current_stage="persistence"
        )

        run = await save_residual_training_run(
            session, result=result, manifest_rows=manifest_rows
        )

        await update_residual_execution_attempt_stage(
            session, attempt_id=attempt_id, current_stage="reload_integrity"
        )

        loaded = await load_residual_training_run_by_id(session, run_id=run.id)
        if loaded is None:
            await fail_residual_execution_attempt(
                session,
                attempt_id=attempt_id,
                sanitized_error="ResidualTrainingApplicationIntegrityError: "
                "Residual training run was saved but could not be reloaded",
            )
            raise ResidualTrainingApplicationIntegrityError(
                "Residual training run was saved but could not be reloaded"
            )
        if loaded.training_signature != result.training_signature:
            await fail_residual_execution_attempt(
                session,
                attempt_id=attempt_id,
                sanitized_error="ResidualTrainingApplicationIntegrityError: "
                "Reloaded residual training run does not match the saved training signature",
            )
            raise ResidualTrainingApplicationIntegrityError(
                "Reloaded residual training run does not match the saved training signature"
            )
        if loaded.manifest_hash != result.manifest_hash or loaded.config_hash != result.config_hash:
            await fail_residual_execution_attempt(
                session,
                attempt_id=attempt_id,
                sanitized_error="ResidualTrainingApplicationIntegrityError: "
                "Reloaded residual training run failed manifest/config parity checks",
            )
            raise ResidualTrainingApplicationIntegrityError(
                "Reloaded residual training run failed manifest/config parity checks"
            )
        if (
            loaded.execution_status == "completed"
            and loaded.eligibility_status == "eligible"
            and len(loaded.artifacts) != 3
        ):
            await fail_residual_execution_attempt(
                session,
                attempt_id=attempt_id,
                sanitized_error="ResidualModelPersistenceIntegrityError: "
                "Eligible residual training run reloaded without three quantile artifacts",
            )
            raise ResidualModelPersistenceIntegrityError(
                "Eligible residual training run reloaded without three quantile artifacts"
            )

        # SECTION 6: Finalize attempt as completed, linked to run
        await complete_residual_execution_attempt(
            session,
            attempt_id=attempt_id,
            linked_training_run_id=run.id,
        )
        await session.commit()

        return loaded, run.id

    except Exception as exc:
        sanitized = _sanitize_error(exc)
        try:
            await fail_residual_execution_attempt(
                session,
                attempt_id=attempt_id,
                sanitized_error=sanitized,
            )
            await session.commit()
        except Exception:
            await session.rollback()
        raise


async def execute_residual_prediction(
    session: AsyncSession,
    *,
    request: ResidualPredictionRequest,
) -> tuple[ResidualPredictionExecutionResult, int]:
    """Execute residual prediction with Section 6 attempt lifecycle.

    Uses the unified artifact trust gate (Section 6): catches
    ResidualArtifactIntegrityError for structural_only fallback.
    """
    # SECTION 6: Persist attempt record BEFORE training load
    attempt = await create_residual_execution_attempt(
        session,
        attempt_type="prediction",
        execution_status="running",
        current_stage="training_load",
        requested_inputs={
            "model_run_id": request.model_run_id,
            "task9_run_id": request.task9_run_id,
            "feature_analytics_build_run_id": request.feature_analytics_build_run_id,
            "supplemental_feature_value_count": len(request.supplemental_feature_values),
        },
        config_identity={},
        upstream_requested_ids={
            "task9_run_id": request.task9_run_id,
            "feature_analytics_build_run_id": request.feature_analytics_build_run_id,
        },
    )
    attempt_id = attempt.id

    try:
        await update_residual_execution_attempt_stage(
            session, attempt_id=attempt_id, current_stage="task9_load"
        )

        training_run_row = await get_residual_training_run(session, run_id=request.model_run_id)
        if training_run_row is None:
            await fail_residual_execution_attempt(
                session,
                attempt_id=attempt_id,
                sanitized_error="ResidualTrainingApplicationIntegrityError: "
                f"Residual training run {request.model_run_id} was not found",
            )
            raise ResidualTrainingApplicationIntegrityError(
                f"Residual training run {request.model_run_id} was not found"
            )

        # SECTION 5: Freeze the non-eligible/blocked training prediction state matrix.
        # - running / failed → raise typed error (NOT structural_only)
        # - blocked           → structural_only with model_blocked
        # - completed+ineligible → structural_only with model_not_eligible
        # - completed+eligible (no blockers) → try residual_corrected
        if training_run_row.execution_status == "running":
            await fail_residual_execution_attempt(
                session,
                attempt_id=attempt_id,
                sanitized_error="ResidualTrainingApplicationIntegrityError: "
                f"Cannot predict from training run {training_run_row.id}: "
                "execution_status is 'running'",
            )
            raise ResidualTrainingApplicationIntegrityError(
                f"Cannot predict from training run {training_run_row.id}: "
                f"execution_status is 'running'"
            )
        if training_run_row.execution_status == "failed":
            await fail_residual_execution_attempt(
                session,
                attempt_id=attempt_id,
                sanitized_error="ResidualTrainingApplicationIntegrityError: "
                f"Cannot predict from training run {training_run_row.id}: "
                "execution_status is 'failed'",
            )
            raise ResidualTrainingApplicationIntegrityError(
                f"Cannot predict from training run {training_run_row.id}: "
                f"execution_status is 'failed'"
            )

        await update_residual_execution_attempt_stage(
            session, attempt_id=attempt_id, current_stage="feature_build"
        )

        try:
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
        except Exception as exc:
            sanitized = _sanitize_error(exc)
            await fail_residual_execution_attempt(
                session,
                attempt_id=attempt_id,
                sanitized_error=sanitized,
            )
            await session.commit()
            raise

        # Phase 1: Get training metadata from DB row (safe, no artifact loading)
        model_family = training_run_row.model_family
        model_version = training_run_row.model_version
        feature_schema_version = training_run_row.feature_schema_version
        feature_schema_hash = training_run_row.feature_schema_hash
        config_hash = training_run_row.config_hash
        training_signature = training_run_row.training_signature
        manifest_hash = training_run_row.manifest_hash

        config = load_residual_model_config_from_snapshot(training_run_row.config_snapshot)

        artifact_hashes: list[str] = []
        result: ResidualPredictionExecutionResult
        fallback_reason: str | None = None
        feature_names: list[str] = []
        category_encodings: list[Any] = []
        estimators: TrainedResidualEstimators | None = None

        # SECTION 5: Determine fallback_reason from training run state
        # Priority: training run state > feature blockers
        if training_run_row.execution_status == "blocked":
            fallback_reason = "model_blocked"
        elif training_run_row.eligibility_status == "ineligible":
            fallback_reason = "model_not_eligible"
        elif blockers:
            fallback_reason = "feature_visibility_failed"
        else:
            # Phase 1b: Freeze artifact DB identities before trust gate (S4)
            # Load SHA-256 hashes from authoritative artifact DB rows regardless
            # of trust gate outcome, so structural-only fallback records correct
            # artifact identities for persistence parity.
            await update_residual_execution_attempt_stage(
                session, attempt_id=attempt_id, current_stage="artifact_identity_load"
            )
            try:
                training_artifact_rows = await list_residual_artifacts(
                    session, training_run_id=training_run_row.id
                )
                artifact_hashes = [a.artifact_sha256 for a in training_artifact_rows]
            except Exception:
                artifact_hashes = []

            # Phase 2: Try unified artifact trust gate (Section 6)
            await update_residual_execution_attempt_stage(
                session, attempt_id=attempt_id, current_stage="artifact_trust_validation"
            )
            try:
                artifacts = await load_and_validate_trusted_residual_artifacts(
                    session, run_id=training_run_row.id
                )
                artifact_hashes = [item.metadata.binary_sha256 for item in artifacts]
                if len(artifacts) != 3:
                    fallback_reason = "artifact_count_mismatch"
                else:
                    estimators = TrainedResidualEstimators(
                        p50=load_trusted_quantile_estimator(
                            artifact=next(
                                item for item in artifacts if item.quantile_label == "P50"
                            ),
                            expected_model_family=model_family,
                            expected_model_version=model_version,
                            expected_artifact_schema_version=training_run_row.artifact_schema_version,
                            expected_feature_schema_version=feature_schema_version,
                            expected_feature_schema_hash=feature_schema_hash,
                            expected_config_hash=config_hash,
                            expected_training_signature=training_signature,
                            expected_manifest_hash=manifest_hash,
                            expected_quantile_label="P50",
                        ),
                        p80=load_trusted_quantile_estimator(
                            artifact=next(
                                item for item in artifacts if item.quantile_label == "P80"
                            ),
                            expected_model_family=model_family,
                            expected_model_version=model_version,
                            expected_artifact_schema_version=training_run_row.artifact_schema_version,
                            expected_feature_schema_version=feature_schema_version,
                            expected_feature_schema_hash=feature_schema_hash,
                            expected_config_hash=config_hash,
                            expected_training_signature=training_signature,
                            expected_manifest_hash=manifest_hash,
                            expected_quantile_label="P80",
                        ),
                        p90=load_trusted_quantile_estimator(
                            artifact=next(
                                item for item in artifacts if item.quantile_label == "P90"
                            ),
                            expected_model_family=model_family,
                            expected_model_version=model_version,
                            expected_artifact_schema_version=training_run_row.artifact_schema_version,
                            expected_feature_schema_version=feature_schema_version,
                            expected_feature_schema_hash=feature_schema_hash,
                            expected_config_hash=config_hash,
                            expected_training_signature=training_signature,
                            expected_manifest_hash=manifest_hash,
                            expected_quantile_label="P90",
                        ),
                    )
                    category_encodings = artifacts[0].metadata.category_encodings
                    feature_names = list(
                        training_run_row.training_metrics.get("feature_names", [])
                    )
                    fallback_reason = None
            except (ResidualArtifactIntegrityError, ResidualModelPersistenceIntegrityError):
                fallback_reason = "artifact_validation_failed"

        input_snapshot = _prediction_input_snapshot(
            request=request,
            training_run_row=training_run_row,
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
                config_hash=config_hash,
                structural_rows=structural_rows,
                fallback_reason=fallback_reason,
                warnings=warnings,
                blockers=blockers,
                input_snapshot=input_snapshot,
            )
        else:
            if estimators is None:
                await fail_residual_execution_attempt(
                    session,
                    attempt_id=attempt_id,
                    sanitized_error="ResidualPredictionApplicationIntegrityError: "
                    "Residual prediction estimators were not resolved for residual_corrected mode",
                )
                raise ResidualPredictionApplicationIntegrityError(
                    "Residual prediction estimators were not resolved for residual_corrected mode"
                )
            await update_residual_execution_attempt_stage(
                session, attempt_id=attempt_id, current_stage="estimator_prediction"
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

        await update_residual_execution_attempt_stage(
            session, attempt_id=attempt_id, current_stage="persistence"
        )
        run = await save_residual_prediction_run(
            session,
            result=result,
            feature_schema_version=feature_schema_version,
            feature_schema_hash=feature_schema_hash,
            artifact_hashes=artifact_hashes,
        )

        await update_residual_execution_attempt_stage(
            session, attempt_id=attempt_id, current_stage="reload_integrity"
        )
        loaded = await load_residual_prediction_run_by_id(session, run_id=run.id)
        if loaded is None:
            await fail_residual_execution_attempt(
                session,
                attempt_id=attempt_id,
                sanitized_error="ResidualPredictionApplicationIntegrityError: "
                "Residual prediction run was saved but could not be reloaded",
            )
            raise ResidualPredictionApplicationIntegrityError(
                "Residual prediction run was saved but could not be reloaded"
            )
        if loaded.model_dump(mode="json") != result.model_dump(mode="json"):
            await fail_residual_execution_attempt(
                session,
                attempt_id=attempt_id,
                sanitized_error="ResidualPredictionApplicationIntegrityError: "
                "Reloaded residual prediction run failed parity checks",
            )
            raise ResidualPredictionApplicationIntegrityError(
                "Reloaded residual prediction run failed parity checks"
            )

        # SECTION 6: Finalize attempt as completed, linked to run
        await complete_residual_execution_attempt(
            session,
            attempt_id=attempt_id,
            linked_prediction_run_id=run.id,
        )
        await session.commit()

        return loaded, run.id

    except Exception as exc:
        sanitized = _sanitize_error(exc)
        try:
            await fail_residual_execution_attempt(
                session,
                attempt_id=attempt_id,
                sanitized_error=sanitized,
            )
            await session.commit()
        except Exception:
            await session.rollback()
        raise
