from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.db.session import AsyncSessionMaker
from backend.app.harvest_state.canonical import canonical_json_value
from backend.app.repositories.harvest_state import get_harvest_state_run
from backend.app.repositories.residual_model import (
    complete_residual_execution_attempt,
    create_residual_execution_attempt,
    fail_residual_execution_attempt,
    get_residual_training_run,
    list_residual_artifacts,
    list_residual_manifest_rows,
    update_residual_execution_attempt_stage,
)
from backend.app.residual_model.artifact import (
    ResidualArtifactValidationError,
    load_trusted_quantile_estimator,
)
from backend.app.residual_model.config import (
    FINAL_TARGET_MODEL_FAMILY,
    ResidualModelConfig,
    is_final_target_quantile_config,
    load_residual_model_config_from_snapshot,
)
from backend.app.residual_model.forecast_cutoff import (
    ForecastCutoffResolutionError,
    resolve_forecast_cutoff_at,
)
from backend.app.residual_model.manifest import manifest_hash as legacy_manifest_hash
from backend.app.residual_model.model import TrainedResidualEstimators
from backend.app.residual_model.persistence import (
    ResidualArtifactIntegrityError,
    ResidualModelPersistenceIntegrityError,
    load_residual_prediction_run_by_id,
    load_residual_training_artifacts,
    load_residual_training_run_by_id,
    prediction_results_business_compatible,
    save_residual_prediction_run,
    save_residual_training_run,
)
from backend.app.residual_model.prediction_features import build_prediction_feature_rows
from backend.app.residual_model.replay_training_authority import (
    actual_input_rows,
    actual_manifest_payload,
    dataset_identity,
    final_target_actual_input_rows,
    final_target_dataset_identity,
    final_target_manifest_payload,
    manifest_row_from_model,
)
from backend.app.residual_model.schemas import (
    FeatureValue,
    FeatureVisibilityAudit,
    FinalTargetPredictionRequest,
    FinalTargetTrainingManifestRow,
    ResidualPredictionExecutionResult,
    ResidualPredictionRequest,
    ResidualTrainingExecutionResult,
    ResidualTrainingSampleSpec,
)
from backend.app.residual_model.service import (
    predict_residual_correction,
    run_final_target_quantile_prediction,
    structural_only_prediction,
    train_residual_model_from_manifest,
)
from backend.app.residual_model.training_manifest import (
    build_residual_training_manifest,
    final_target_manifest_hash,
    final_target_manifest_row_from_payload,
)


class ResidualTrainingApplicationIntegrityError(RuntimeError):
    pass


class ResidualPredictionApplicationIntegrityError(RuntimeError):
    pass


class ResidualModelAuthorityMode(StrEnum):
    HISTORICALLY_AVAILABLE_MODEL = "historically_available_model"
    REPLAY_TRAINED_MODEL = "replay_trained_model"


class ResidualModelVersionNotVisibleError(ResidualPredictionApplicationIntegrityError):
    """Raised when a persisted residual model is not visible at the forecast cutoff."""

    code = "MODEL_VERSION_NOT_VISIBLE"

    def __init__(self, detail: str) -> None:
        super().__init__(f"{self.code}: {detail}")


class ResidualReplayTrainedAuthorityError(ResidualPredictionApplicationIntegrityError):
    """Raised when replay-trained exemption lacks persisted Task 12 authority."""

    code = "REPLAY_TRAINED_AUTHORITY_NOT_PERSISTED"

    def __init__(self, detail: str) -> None:
        super().__init__(f"{self.code}: {detail}")


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


def _normalize_authority_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _authority_timestamp_iso(value: datetime | None) -> str | None:
    normalized = _normalize_authority_timestamp(value)
    return normalized.isoformat() if normalized is not None else None


def _resolve_model_authority_mode(
    model_policy: ResidualModelAuthorityMode | str,
) -> ResidualModelAuthorityMode:
    try:
        return ResidualModelAuthorityMode(model_policy)
    except (TypeError, ValueError) as exc:
        raise ResidualPredictionApplicationIntegrityError(
            "model_policy must be historically_available_model or replay_trained_model"
        ) from exc


def _persisted_replay_context(training_run: Any) -> Mapping[str, Any]:
    snapshot = training_run.input_snapshot
    if not isinstance(snapshot, Mapping):
        raise ResidualReplayTrainedAuthorityError(
            "persisted residual training input_snapshot is not an object"
        )
    context = snapshot.get("task12_replay")
    if not isinstance(context, Mapping):
        raise ResidualReplayTrainedAuthorityError(
            "persisted residual training run has no task12_replay provenance"
        )
    return context


def _parse_persisted_authority_timestamp(
    value: object,
    *,
    require_timezone_aware: bool = False,
) -> datetime | None:
    if isinstance(value, datetime):
        if require_timezone_aware and (value.tzinfo is None or value.utcoffset() is None):
            return None
        return _normalize_authority_timestamp(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if require_timezone_aware and (parsed.tzinfo is None or parsed.utcoffset() is None):
        return None
    return _normalize_authority_timestamp(parsed)


def _require_persisted_replay_context_parity(
    *,
    training_run: Any,
    input_snapshot_context: Mapping[str, Any],
) -> None:
    typed_attempt = training_run.typed_attempt
    if not isinstance(typed_attempt, Mapping):
        raise ResidualReplayTrainedAuthorityError(
            "persisted residual training run has no typed Task 12 provenance"
        )
    typed_context = typed_attempt.get("task12_replay")
    if not isinstance(typed_context, Mapping):
        raise ResidualReplayTrainedAuthorityError(
            "persisted residual training run typed attempt has no task12_replay provenance"
        )
    if canonical_json_value(dict(input_snapshot_context)) != canonical_json_value(
        dict(typed_context)
    ):
        raise ResidualReplayTrainedAuthorityError(
            "persisted Task 12 input_snapshot and typed_attempt provenance differ"
        )


async def _require_persisted_replay_authority(
    *,
    session: AsyncSession,
    training_run: Any,
    task9_run: Any,
    task9_run_id: int,
    forecast_cutoff_at: datetime,
) -> None:
    try:
        persisted_training_run = await get_residual_training_run(
            session,
            run_id=training_run.id,
        )
    except SQLAlchemyError as exc:
        raise ResidualReplayTrainedAuthorityError(
            "persisted residual training run could not be reloaded"
        ) from exc
    if persisted_training_run is None:
        raise ResidualReplayTrainedAuthorityError(
            "persisted residual training run could not be reloaded"
        )
    training_run = persisted_training_run
    if task9_run.is_replay is not True:
        raise ResidualReplayTrainedAuthorityError(
            "replay-trained exemption requires a persisted replay Task 9 run"
        )

    context = _persisted_replay_context(training_run)
    _require_persisted_replay_context_parity(
        training_run=training_run,
        input_snapshot_context=context,
    )
    if context.get("model_policy") != ResidualModelAuthorityMode.REPLAY_TRAINED_MODEL.value:
        raise ResidualReplayTrainedAuthorityError(
            "persisted Task 12 provenance does not identify replay_trained_model"
        )
    if context.get("is_replay") is not True:
        raise ResidualReplayTrainedAuthorityError(
            "persisted Task 12 provenance is not marked as replay"
        )
    if context.get("task9_run_id") != task9_run_id:
        raise ResidualReplayTrainedAuthorityError(
            "persisted Task 12 provenance is bound to a different Task 9 run"
        )
    if context.get("task9_result_hash") != task9_run.result_hash:
        raise ResidualReplayTrainedAuthorityError(
            "persisted Task 12 provenance is bound to a different Task 9 result"
        )
    persisted_cutoff_at = _parse_persisted_authority_timestamp(context.get("forecast_cutoff_at"))
    if persisted_cutoff_at != forecast_cutoff_at:
        raise ResidualReplayTrainedAuthorityError(
            "persisted Task 12 forecast cutoff does not match Task 9 authority"
        )
    training_cutoff_at = _parse_persisted_authority_timestamp(
        context.get("training_cutoff_at"),
        require_timezone_aware=True,
    )
    if training_cutoff_at is None:
        raise ResidualReplayTrainedAuthorityError(
            "persisted Task 12 training cutoff is missing or not timezone-aware"
        )
    if training_cutoff_at > forecast_cutoff_at:
        raise ResidualReplayTrainedAuthorityError(
            "persisted Task 12 training cutoff is after the forecast cutoff"
        )
    if context.get("training_manifest_hash") != training_run.manifest_hash:
        raise ResidualReplayTrainedAuthorityError(
            "persisted Task 12 training manifest hash does not match the training run"
        )
    if context.get("task10_manifest_hash") != training_run.manifest_hash:
        raise ResidualReplayTrainedAuthorityError(
            "persisted Task 12 manifest hash does not match the training run"
        )
    if context.get("model_config_hash") != training_run.config_hash:
        raise ResidualReplayTrainedAuthorityError(
            "persisted Task 12 model config hash does not match the training run"
        )
    if context.get("task10_config_hash") != training_run.config_hash:
        raise ResidualReplayTrainedAuthorityError(
            "persisted Task 12 config hash does not match the training run"
        )

    try:
        if training_run.input_snapshot.get("prediction_target_kind") == "FINAL_TARGET_QUANTILE":
            snapshot_payloads = cast(
                list[dict[str, Any]],
                training_run.manifest_snapshot.get("rows", []),
            )
            final_rows = [
                final_target_manifest_row_from_payload(payload) for payload in snapshot_payloads
            ]
            if training_run.manifest_row_count != 0:
                raise ValueError("final-target training run must have zero legacy child rows")
            if final_target_manifest_hash(final_rows) != training_run.manifest_hash:
                raise ValueError("final-target manifest snapshot hash mismatch")
            for final_manifest_row in final_rows:
                if final_manifest_row.forecast_cutoff_at > forecast_cutoff_at:
                    raise ResidualReplayTrainedAuthorityError(
                        "final-target forecast cutoff precedes feature visibility"
                    )
            persisted_manifest_payload = final_target_manifest_payload(final_rows)
            persisted_training_rows, persisted_label_rows = final_target_actual_input_rows(
                final_rows
            )
            recomputed_dataset_hash = final_target_dataset_identity(
                training_rows=persisted_training_rows,
                label_rows=persisted_label_rows,
                manifest_rows=persisted_manifest_payload,
                prediction_target_kind="FINAL_TARGET_QUANTILE",
                s2_authority_identity=cast(
                    str,
                    training_run.input_snapshot.get("s2_authority_identity", ""),
                ),
            )
        else:
            persisted_manifest_rows = await list_residual_manifest_rows(
                session,
                training_run_id=training_run.id,
            )
            if len(persisted_manifest_rows) != training_run.manifest_row_count:
                raise ValueError("persisted manifest row count does not match the training run")
            legacy_manifest_rows = [manifest_row_from_model(row) for row in persisted_manifest_rows]
            training_cutoff_date = training_cutoff_at.date()
            for legacy_manifest_row in legacy_manifest_rows:
                if legacy_manifest_row.as_of_date > training_cutoff_date:
                    raise ResidualReplayTrainedAuthorityError(
                        "persisted Task 12 training observation is after the training cutoff"
                    )
                label_cutoff_date = legacy_manifest_row.label_actual_snapshot.source_cutoff.date()
                if label_cutoff_date > training_cutoff_date:
                    raise ResidualReplayTrainedAuthorityError(
                        "persisted Task 12 label availability is after the training cutoff"
                    )

            recomputed_manifest_hash = legacy_manifest_hash(legacy_manifest_rows)
            if recomputed_manifest_hash != training_run.manifest_hash:
                raise ResidualReplayTrainedAuthorityError(
                    "persisted Task 12 manifest rows do not match the training manifest hash"
                )
            persisted_manifest_payload = actual_manifest_payload(legacy_manifest_rows)
            persisted_training_rows, persisted_label_rows = actual_input_rows(legacy_manifest_rows)
            recomputed_dataset_hash = dataset_identity(
                training_rows=persisted_training_rows,
                label_rows=persisted_label_rows,
                manifest_rows=persisted_manifest_payload,
            )
    except ResidualReplayTrainedAuthorityError:
        raise
    except Exception as exc:
        raise ResidualReplayTrainedAuthorityError(
            "persisted Task 12 manifest rows could not be reconstructed"
        ) from exc

    if context.get("training_dataset_hash") != recomputed_dataset_hash:
        raise ResidualReplayTrainedAuthorityError(
            "persisted Task 12 dataset hash does not match the persisted manifest rows"
        )
    for field in ("task12_policy_version", "replay_attempt_id", "replay_node_id", "scenario_id"):
        value = context.get(field)
        if not isinstance(value, str) or not value:
            raise ResidualReplayTrainedAuthorityError(
                f"persisted Task 12 provenance is missing {field}"
            )


async def _resolve_residual_model_visibility(
    session: AsyncSession,
    *,
    training_run: Any,
    task9_run_id: int,
    model_policy: ResidualModelAuthorityMode,
) -> tuple[datetime, list[Any]]:
    """Resolve the shared forecast cutoff and gate persisted model visibility."""

    task9_run = await get_harvest_state_run(session, run_id=task9_run_id)
    if task9_run is None:
        raise ResidualPredictionApplicationIntegrityError(
            f"HarvestStateRun {task9_run_id} was not found while resolving forecast cutoff"
        )
    try:
        forecast_cutoff_at = await resolve_forecast_cutoff_at(
            session,
            task9_run_id=task9_run_id,
            as_of_date=task9_run.as_of_date,
        )
    except ForecastCutoffResolutionError as exc:
        raise ResidualPredictionApplicationIntegrityError(str(exc)) from exc

    if model_policy is ResidualModelAuthorityMode.REPLAY_TRAINED_MODEL:
        await _require_persisted_replay_authority(
            session=session,
            training_run=training_run,
            task9_run=task9_run,
            task9_run_id=task9_run_id,
            forecast_cutoff_at=forecast_cutoff_at,
        )

    try:
        artifact_rows = (
            await list_residual_artifacts(session, training_run_id=training_run.id)
            if training_run.eligibility_status == "eligible"
            else []
        )
    except SQLAlchemyError as exc:
        raise ResidualPredictionApplicationIntegrityError(
            "Authoritative residual artifact identities could not be loaded"
        ) from exc

    if model_policy is ResidualModelAuthorityMode.REPLAY_TRAINED_MODEL:
        # Replay-trained artifacts are created by the replay execution after
        # the historical cutoff. Replay service validation owns their
        # training-cutoff, manifest, and identity authority instead.
        return forecast_cutoff_at, artifact_rows

    training_finished_at = _normalize_authority_timestamp(training_run.finished_at)
    if training_finished_at is None or training_finished_at > forecast_cutoff_at:
        raise ResidualModelVersionNotVisibleError(
            "persisted residual training run is not visible at the forecast cutoff"
        )

    for artifact in artifact_rows:
        artifact_created_at = _normalize_authority_timestamp(artifact.created_at)
        if artifact_created_at is None or artifact_created_at > forecast_cutoff_at:
            raise ResidualModelVersionNotVisibleError(
                "persisted residual model artifact is not visible at the forecast cutoff"
            )

    return forecast_cutoff_at, artifact_rows


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
    execution_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = {
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
    if execution_context:
        snapshot.update(
            {
                key: value
                for key, value in execution_context.items()
                if key != "model_artifact_visibility"
            }
        )
    return snapshot


async def execute_residual_training(
    session: AsyncSession,
    *,
    samples: list[ResidualTrainingSampleSpec],
    config: ResidualModelConfig,
    execution_context: dict[str, Any] | None = None,
    typed_attempt: dict[str, Any] | None = None,
) -> tuple[ResidualTrainingExecutionResult, int]:
    attempt_id: int | None = await _create_attempt(
        session=session,
        attempt_type="training",
        current_stage="manifest_build",
        requested_inputs={
            "sample_count": len(samples),
            "splits": [sample.split.value for sample in samples],
            "execution_context": execution_context or {},
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
        if execution_context:
            result = result.model_copy(
                update={
                    "input_snapshot": {
                        **result.input_snapshot,
                        **execution_context,
                    }
                }
            )
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
            typed_attempt=typed_attempt,
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


async def execute_final_target_training(
    session: AsyncSession,
    *,
    final_target_rows: list[FinalTargetTrainingManifestRow],
    config: ResidualModelConfig,
    execution_context: dict[str, Any] | None = None,
    typed_attempt: dict[str, Any] | None = None,
) -> tuple[ResidualTrainingExecutionResult, int]:
    from backend.app.residual_model.config import is_final_target_quantile_config
    from backend.app.residual_model.service import train_final_target_model_from_manifest

    if not is_final_target_quantile_config(config):
        raise ResidualTrainingApplicationIntegrityError(
            "execute_final_target_training requires FINAL_TARGET_QUANTILE config"
        )
    attempt_id: int | None = await _create_attempt(
        session=session,
        attempt_type="training",
        current_stage="model_training",
        requested_inputs={
            "row_count": len(final_target_rows),
            "prediction_target_kind": "FINAL_TARGET_QUANTILE",
            "execution_context": execution_context or {},
        },
        config_identity={
            "model_family": config.rules.model_family,
            "model_version": config.rules.model_version,
            "config_hash": config.config_hash,
            "prediction_target_kind": config.rules.prediction_target_kind.value,
        },
        upstream_requested_ids={},
    )
    current_stage = "model_training"
    try:
        result = train_final_target_model_from_manifest(rows=final_target_rows, config=config)
        if execution_context:
            result = result.model_copy(
                update={
                    "input_snapshot": {
                        **result.input_snapshot,
                        **execution_context,
                    }
                }
            )
        current_stage = "persistence"
        await _update_attempt_stage(
            session=session,
            attempt_id=attempt_id,
            current_stage=current_stage,
        )
        run = await save_residual_training_run(
            session,
            result=result,
            final_target_manifest_rows=final_target_rows,
            typed_attempt=typed_attempt,
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
                "Final-target training run was saved but could not be reloaded"
            )
        if loaded.training_signature != result.training_signature:
            raise ResidualTrainingApplicationIntegrityError(
                "Reloaded final-target training run does not match the saved training signature"
            )
        if loaded.manifest_hash != result.manifest_hash or loaded.config_hash != result.config_hash:
            raise ResidualTrainingApplicationIntegrityError(
                "Reloaded final-target training run failed manifest/config parity checks"
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


async def execute_final_target_prediction(
    session: AsyncSession,
    *,
    request: FinalTargetPredictionRequest,
    execution_context: dict[str, Any] | None = None,
    typed_attempt: dict[str, Any] | None = None,
) -> tuple[ResidualPredictionExecutionResult, int]:
    """Execute a governed final-target quantile prediction lane end-to-end."""

    attempt_id: int | None = await _create_attempt(
        session=session,
        attempt_type="prediction",
        current_stage="training_load",
        requested_inputs={
            "model_run_id": request.model_run_id,
            "forecast_cutoff_at": request.forecast_cutoff_at.isoformat(),
            "prediction_row_count": len(request.prediction_rows),
            "prediction_target_kind": "FINAL_TARGET_QUANTILE",
            "execution_context": execution_context or {},
        },
        config_identity={
            "model_run_id": request.model_run_id,
            "prediction_target_kind": "FINAL_TARGET_QUANTILE",
        },
        upstream_requested_ids={"model_run_id": request.model_run_id},
    )
    current_stage = "training_load"
    try:
        training_run_row = await get_residual_training_run(session, run_id=request.model_run_id)
        if training_run_row is None:
            raise ResidualPredictionApplicationIntegrityError(
                "Final-target training run was not found"
            )
        if training_run_row.input_snapshot.get("prediction_target_kind") != "FINAL_TARGET_QUANTILE":
            raise ResidualPredictionApplicationIntegrityError(
                "training run is not a FINAL_TARGET_QUANTILE lane"
            )
        if training_run_row.model_family != FINAL_TARGET_MODEL_FAMILY:
            raise ResidualPredictionApplicationIntegrityError(
                "legacy model_family rejected by final-target prediction lane"
            )
        if training_run_row.execution_status != "completed":
            raise ResidualPredictionApplicationIntegrityError(
                "final-target training run must be completed, "
                f"got {training_run_row.execution_status}"
            )
        if training_run_row.eligibility_status != "eligible":
            raise ResidualPredictionApplicationIntegrityError(
                "final-target prediction requires an eligible training run"
            )
        model_run = await load_residual_training_run_by_id(session, run_id=request.model_run_id)
        if model_run is None:
            raise ResidualPredictionApplicationIntegrityError(
                "Final-target training run could not be loaded with artifacts"
            )
        config = load_residual_model_config_from_snapshot(
            model_run.input_snapshot["config_snapshot"]
        )
        if not is_final_target_quantile_config(config):
            raise ResidualPredictionApplicationIntegrityError(
                "final-target config snapshot does not match FINAL_TARGET_QUANTILE lane"
            )
        current_stage = "artifact_identity_load"
        await _update_attempt_stage(
            session=session,
            attempt_id=attempt_id,
            current_stage=current_stage,
        )
        artifact_rows = await list_residual_artifacts(
            session,
            training_run_id=training_run_row.id,
        )
        artifact_hashes = [item.artifact_sha256 for item in artifact_rows]
        artifacts = await load_residual_training_artifacts(
            session,
            run_id=training_run_row.id,
            artifacts_rows=tuple(artifact_rows),
        )
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
        feature_names = list(model_run.metrics.get("feature_names", []))
        prediction_rows = list(request.prediction_rows)
        for row in prediction_rows:
            if row.forecast_cutoff_at != request.forecast_cutoff_at:
                raise ResidualPredictionApplicationIntegrityError(
                    "prediction row forecast_cutoff_at must match request forecast_cutoff_at"
                )
        current_stage = "prediction"
        await _update_attempt_stage(
            session=session,
            attempt_id=attempt_id,
            current_stage=current_stage,
        )
        result = run_final_target_quantile_prediction(
            model_run_id=training_run_row.id,
            training_signature=training_run_row.training_signature,
            manifest_hash_value=training_run_row.manifest_hash,
            config=config,
            feature_names=feature_names,
            category_encodings=artifacts[0].metadata.category_encodings,
            artifact_hashes=artifact_hashes,
            forecast_cutoff_at=request.forecast_cutoff_at,
            prediction_rows=prediction_rows,
            estimators=estimators,
            artifacts=artifacts,
        )
        if execution_context:
            result = result.model_copy(
                update={
                    "input_snapshot": {
                        **result.input_snapshot,
                        **execution_context,
                    }
                }
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
            typed_attempt=typed_attempt,
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
                "Final-target prediction run was saved but could not be reloaded"
            )
        if not prediction_results_business_compatible(loaded, result):
            raise ResidualPredictionApplicationIntegrityError(
                "Reloaded final-target prediction run failed parity checks"
            )
        for final_target_row in loaded.final_target_rows:
            if (
                final_target_row.model_run_id != training_run_row.id
                or final_target_row.prediction_run_id != run.id
            ):
                raise ResidualPredictionApplicationIntegrityError(
                    "Reloaded final-target prediction rows lack persisted run identity"
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


async def execute_residual_prediction(
    session: AsyncSession,
    *,
    request: ResidualPredictionRequest,
    model_policy: ResidualModelAuthorityMode | str = (
        ResidualModelAuthorityMode.HISTORICALLY_AVAILABLE_MODEL
    ),
    execution_context: dict[str, Any] | None = None,
    typed_attempt: dict[str, Any] | None = None,
) -> tuple[ResidualPredictionExecutionResult, int]:
    resolved_model_policy = _resolve_model_authority_mode(model_policy)
    attempt_id: int | None = await _create_attempt(
        session=session,
        attempt_type="prediction",
        current_stage="training_load",
        requested_inputs={
            **request.model_dump(mode="json"),
            "model_policy": resolved_model_policy.value,
            "execution_context": execution_context or {},
        },
        config_identity={
            "model_run_id": request.model_run_id,
            "feature_analytics_build_run_id": request.feature_analytics_build_run_id,
            "model_policy": resolved_model_policy.value,
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
        current_stage = "model_visibility"
        await _update_attempt_stage(
            session=session,
            attempt_id=attempt_id,
            current_stage=current_stage,
        )
        forecast_cutoff_at, artifact_rows = await _resolve_residual_model_visibility(
            session,
            training_run=training_run_row,
            task9_run_id=request.task9_run_id,
            model_policy=resolved_model_policy,
        )
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

        artifact_hashes = [item.artifact_sha256 for item in artifact_rows]
        if preload_artifact_error is not None and training_run_row.eligibility_status == "eligible":
            current_stage = "artifact_identity_load"
            await _update_attempt_stage(
                session=session,
                attempt_id=attempt_id,
                current_stage=current_stage,
            )

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

        model_artifact_visibility = {
            "policy_version": "residual-model-artifact-availability-v1",
            "mode": resolved_model_policy.value,
            "forecast_cutoff_at": forecast_cutoff_at.isoformat(),
            "training_run_id": training_run_row.id,
            "training_run_finished_at": _authority_timestamp_iso(training_run_row.finished_at),
            "artifact_authorities": [
                {
                    "quantile_label": artifact.quantile_label,
                    "artifact_sha256": artifact.artifact_sha256,
                    "created_at": _authority_timestamp_iso(artifact.created_at),
                }
                for artifact in artifact_rows
            ],
        }
        prediction_typed_attempt = dict(typed_attempt or {})
        # This audit evidence is DB-derived and intentionally lives outside
        # the canonical prediction input identity.  Caller-supplied metadata
        # cannot override the authority snapshot.
        prediction_typed_attempt["model_artifact_visibility"] = model_artifact_visibility
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
            execution_context=execution_context,
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
            typed_attempt=prediction_typed_attempt,
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
        if not prediction_results_business_compatible(loaded, result):
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
