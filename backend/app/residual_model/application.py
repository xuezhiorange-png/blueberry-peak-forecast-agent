from __future__ import annotations

from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.db.session import AsyncSessionMaker
from backend.app.repositories.residual_model import (
    complete_residual_execution_attempt,
    create_residual_execution_attempt,
    fail_residual_execution_attempt,
    get_residual_training_run,
    list_residual_artifacts,
    update_residual_execution_attempt_stage,
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


def _sanitize_error_message(exc: Exception) -> str:
    raw_message = " ".join(str(exc).replace("\r", " ").replace("\n", " ").split())
    if raw_message:
        return f"{exc.__class__.__name__}: {raw_message}"[:500]
    return exc.__class__.__name__


async def _create_attempt(
    *,
    session: AsyncSession,
    attempt_type: str,
    current_stage: str,
    requested_inputs: dict[str, object],
    config_identity: dict[str, object],
    upstream_requested_ids: dict[str, object],
    blockers: list[str] | None = None,
) -> int:
    async with _attempt_sessionmaker(session=session)() as attempt_session:
        attempt = await create_residual_execution_attempt(
            attempt_session,
            attempt_type=attempt_type,
            execution_status="running",
            current_stage=current_stage,
            requested_inputs=requested_inputs,
            config_identity=config_identity,
            upstream_requested_ids=upstream_requested_ids,
            blockers=blockers,
        )
        await attempt_session.commit()
        return attempt.id


def _attempt_sessionmaker(
    *,
    session: AsyncSession,
) -> async_sessionmaker[AsyncSession]:
    bind = session.bind
    if bind is None:
        return AsyncSessionMaker
    return async_sessionmaker(bind=bind, class_=AsyncSession, expire_on_commit=False)


async def _update_attempt_stage(
    *,
    session: AsyncSession,
    attempt_id: int | None,
    current_stage: str,
) -> None:
    if attempt_id is None:
        return
    async with _attempt_sessionmaker(session=session)() as attempt_session:
        await update_residual_execution_attempt_stage(
            attempt_session,
            attempt_id=attempt_id,
            current_stage=current_stage,
        )
        await attempt_session.commit()


async def _complete_attempt(
    *,
    session: AsyncSession,
    attempt_id: int | None,
    linked_training_run_id: int | None = None,
    linked_prediction_run_id: int | None = None,
) -> None:
    if attempt_id is None:
        return
    async with _attempt_sessionmaker(session=session)() as attempt_session:
        await complete_residual_execution_attempt(
            attempt_session,
            attempt_id=attempt_id,
            linked_training_run_id=linked_training_run_id,
            linked_prediction_run_id=linked_prediction_run_id,
        )
        await attempt_session.commit()


async def _fail_attempt(
    *,
    session: AsyncSession,
    attempt_id: int | None,
    current_stage: str,
    exc: Exception,
) -> None:
    if attempt_id is None:
        return
    async with _attempt_sessionmaker(session=session)() as attempt_session:
        await update_residual_execution_attempt_stage(
            attempt_session,
            attempt_id=attempt_id,
            current_stage=current_stage,
        )
        await fail_residual_execution_attempt(
            attempt_session,
            attempt_id=attempt_id,
            sanitized_error=_sanitize_error_message(exc),
        )
        await attempt_session.commit()


def _raise_training_error(exc: Exception) -> RuntimeError:
    if isinstance(exc, ResidualTrainingApplicationIntegrityError):
        return exc
    return ResidualTrainingApplicationIntegrityError(str(exc))


def _raise_prediction_error(exc: Exception) -> RuntimeError:
    if isinstance(exc, ResidualPredictionApplicationIntegrityError):
        return exc
    if isinstance(exc, ResidualTrainingApplicationIntegrityError):
        return exc
    return ResidualPredictionApplicationIntegrityError(str(exc))


def _training_run_fallback_reason(
    training_run: Any,
) -> str | None:
    if training_run.execution_status == "blocked":
        return "model_blocked"
    if (
        training_run.execution_status == "completed"
        and training_run.eligibility_status != "eligible"
    ):
        return "model_not_eligible"
    return None


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
        "feature_rows": [[item.model_dump(mode="json") for item in row] for row in feature_rows],
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
    attempt_id: int | None = await _create_attempt(
        session=session,
        attempt_type="training",
        current_stage="manifest_build",
        requested_inputs={
            "sample_count": len(samples),
            "splits": [sample.split.value for sample in samples],
        },
        config_identity={
            "model_family": config.rules.model_family,
            "model_version": config.rules.model_version,
            "config_hash": config.config_hash,
        },
        upstream_requested_ids={
            "task9_run_ids": sorted({sample.task9_run_id for sample in samples}),
            "label_analytics_build_run_ids": sorted(
                {sample.label_analytics_build_run_id for sample in samples}
            ),
            "feature_analytics_build_run_ids": sorted(
                {sample.feature_analytics_build_run_id for sample in samples}
            ),
        },
    )
    current_stage = "manifest_build"
    try:
        manifest_rows = await build_residual_training_manifest(session, samples=samples)
        current_stage = "model_training"
        await _update_attempt_stage(
            session=session,
            attempt_id=attempt_id,
            current_stage=current_stage,
        )
        result = train_residual_model_from_manifest(rows=manifest_rows, config=config)
        current_stage = "persistence"
        await _update_attempt_stage(
            session=session,
            attempt_id=attempt_id,
            current_stage=current_stage,
        )
        run = await save_residual_training_run(
            session,
            result=result,
            manifest_rows=manifest_rows,
        )
        current_stage = "reload_integrity"
        await _update_attempt_stage(
            session=session,
            attempt_id=attempt_id,
            current_stage=current_stage,
        )
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
        await _complete_attempt(
            session=session,
            attempt_id=attempt_id,
            linked_training_run_id=run.id,
        )
        return loaded, run.id
    except Exception as exc:
        await session.rollback()
        await _fail_attempt(
            session=session,
            attempt_id=attempt_id,
            current_stage=current_stage,
            exc=exc,
        )
        raise _raise_training_error(exc) from exc


async def execute_residual_prediction(
    session: AsyncSession,
    *,
    request: ResidualPredictionRequest,
) -> tuple[ResidualPredictionExecutionResult, int]:
    attempt_id: int | None = await _create_attempt(
        session=session,
        attempt_type="prediction",
        current_stage="training_load",
        requested_inputs=request.model_dump(mode="json"),
        config_identity={
            "model_run_id": request.model_run_id,
            "feature_analytics_build_run_id": request.feature_analytics_build_run_id,
        },
        upstream_requested_ids={
            "model_run_id": request.model_run_id,
            "task9_run_id": request.task9_run_id,
            "feature_analytics_build_run_id": request.feature_analytics_build_run_id,
        },
    )
    current_stage = "training_load"
    try:
        training_run_row = await get_residual_training_run(session, run_id=request.model_run_id)
        if training_run_row is None:
            raise ResidualTrainingApplicationIntegrityError("Residual training run was not found")
        if training_run_row.execution_status == "running":
            raise ResidualTrainingApplicationIntegrityError("Residual training run is running")
        if training_run_row.execution_status == "failed":
            raise ResidualTrainingApplicationIntegrityError("Residual training run is failed")
        model_run: ResidualTrainingExecutionResult | None
        preload_artifact_error: Exception | None = None
        try:
            model_run = await load_residual_training_run_by_id(session, run_id=request.model_run_id)
        except (
            ResidualArtifactIntegrityError,
            ResidualModelPersistenceIntegrityError,
        ) as exc:
            model_run = None
            preload_artifact_error = exc
        if model_run is None and preload_artifact_error is None:
            raise ResidualTrainingApplicationIntegrityError("Residual training run was not found")

        current_stage = "feature_build"
        await _update_attempt_stage(
            session=session,
            attempt_id=attempt_id,
            current_stage=current_stage,
        )
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
        if preload_artifact_error is not None and training_run_row.eligibility_status == "eligible":
            current_stage = "artifact_identity_load"
            await _update_attempt_stage(
                session=session,
                attempt_id=attempt_id,
                current_stage=current_stage,
            )
            try:
                training_artifact_rows = await list_residual_artifacts(
                    session,
                    training_run_id=training_run_row.id,
                )
            except SQLAlchemyError as exc:
                raise ResidualPredictionApplicationIntegrityError(
                    "Authoritative residual artifact identities could not be loaded"
                ) from exc
            artifact_hashes = [item.artifact_sha256 for item in training_artifact_rows]

        model_run_snapshot = (
            model_run.input_snapshot if model_run is not None else training_run_row.input_snapshot
        )
        config = load_residual_model_config_from_snapshot(model_run_snapshot["config_snapshot"])
        result: ResidualPredictionExecutionResult
        fallback_reason: str | None = None
        feature_names: list[str] = []
        category_encodings: list[Any] = []
        estimators: TrainedResidualEstimators | None = None

        training_run_fallback_reason = _training_run_fallback_reason(training_run_row)
        if training_run_fallback_reason is not None:
            fallback_reason = training_run_fallback_reason
        elif preload_artifact_error is not None or model_run is None:
            fallback_reason = "artifact_validation_failed"
        elif blockers:
            fallback_reason = "feature_visibility_failed"
        else:
            current_stage = "artifact_identity_load"
            await _update_attempt_stage(
                session=session,
                attempt_id=attempt_id,
                current_stage=current_stage,
            )
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
            current_stage = "artifact_validation"
            await _update_attempt_stage(
                session=session,
                attempt_id=attempt_id,
                current_stage=current_stage,
            )
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
                            artifact=next(
                                item for item in artifacts if item.quantile_label == "P50"
                            ),
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
                            artifact=next(
                                item for item in artifacts if item.quantile_label == "P80"
                            ),
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
                            artifact=next(
                                item for item in artifacts if item.quantile_label == "P90"
                            ),
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
                feature_snapshot.model_dump(mode="json") if feature_snapshot is not None else None
            ),
            feature_audits=feature_audits,
            artifact_hashes=artifact_hashes,
            feature_rows=feature_rows,
        ) | {
            "task9_result_hash": task9_output.result_hash,
            "prediction_as_of_date": str(task9_output.input_snapshot["as_of_date"]),
        }

        current_stage = "prediction"
        await _update_attempt_stage(
            session=session,
            attempt_id=attempt_id,
            current_stage=current_stage,
        )
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

        current_stage = "persistence"
        await _update_attempt_stage(
            session=session,
            attempt_id=attempt_id,
            current_stage=current_stage,
        )
        run = await save_residual_prediction_run(
            session,
            result=result,
            feature_schema_version=training_run_row.feature_schema_version,
            feature_schema_hash=training_run_row.feature_schema_hash,
            artifact_hashes=artifact_hashes,
        )
        current_stage = "reload_integrity"
        await _update_attempt_stage(
            session=session,
            attempt_id=attempt_id,
            current_stage=current_stage,
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
        await _complete_attempt(
            session=session,
            attempt_id=attempt_id,
            linked_prediction_run_id=run.id,
        )
        return loaded, run.id
    except Exception as exc:
        await session.rollback()
        await _fail_attempt(
            session=session,
            attempt_id=attempt_id,
            current_stage=current_stage,
            exc=exc,
        )
        raise _raise_prediction_error(exc) from exc
