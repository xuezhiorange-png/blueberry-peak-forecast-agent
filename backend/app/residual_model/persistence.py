from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.harvest_state.canonical import (
    canonical_json_dumps,
    canonical_json_value,
    is_sha256_hex,
)
from backend.app.models.residual_model import (
    ResidualModelArtifact,
    ResidualModelManifestRow,
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.repositories.residual_model import (
    get_residual_prediction_run,
    get_residual_prediction_run_by_input_hash,
    get_residual_training_run,
    get_residual_training_run_by_signature,
    list_residual_artifacts,
    list_residual_prediction_rows,
)
from backend.app.residual_model.canonical import canonical_payload_hash
from backend.app.residual_model.manifest import manifest_row_payload
from backend.app.residual_model.schemas import (
    PersistableResidualArtifact,
    ResidualArtifactMetadata,
    ResidualPredictionExecutionResult,
    ResidualPredictionRow,
    ResidualTrainingExecutionResult,
    ResidualTrainingManifestRow,
)


class ResidualModelPersistenceError(RuntimeError):
    pass


class ResidualModelHashConflictError(ResidualModelPersistenceError):
    pass


class ResidualModelPersistenceIntegrityError(ResidualModelPersistenceError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _canonical_dump(model: object) -> dict[str, Any]:
    payload = model.model_dump(mode="python")  # type: ignore[attr-defined]
    return cast(dict[str, Any], canonical_json_value(payload))


def _canonical_json(model: object) -> str:
    return canonical_json_dumps(_canonical_dump(model))


def _sanitize_error_message(message: str) -> str:
    return " ".join(message.replace("\r", " ").replace("\n", " ").split())[:500]


def _feature_schema_hash(feature_names: Iterable[str]) -> str:
    return canonical_payload_hash(sorted(feature_names))


def _training_payload_hash(result: ResidualTrainingExecutionResult) -> str:
    return canonical_payload_hash(_training_storage_payload(result))


def _prediction_payload_hash(result: ResidualPredictionExecutionResult) -> str:
    return canonical_payload_hash(_canonical_dump(result))


def _training_storage_payload(result: ResidualTrainingExecutionResult) -> dict[str, Any]:
    payload = result.model_dump(mode="python", exclude={"artifacts"})
    payload["artifacts"] = [
        {
            "quantile_label": artifact.quantile_label,
            "artifact_sha256": artifact.metadata.binary_sha256,
            "metadata": artifact.metadata.model_dump(mode="python"),
        }
        for artifact in result.artifacts
    ]
    return cast(dict[str, Any], canonical_json_value(payload))


def _validate_training_result(result: ResidualTrainingExecutionResult) -> None:
    if not is_sha256_hex(result.training_signature):
        raise ResidualModelPersistenceError("training_signature must be canonical SHA-256")
    if not is_sha256_hex(result.config_hash):
        raise ResidualModelPersistenceError("config_hash must be canonical SHA-256")
    if not is_sha256_hex(result.manifest_hash):
        raise ResidualModelPersistenceError("manifest_hash must be canonical SHA-256")
    if result.execution_status == "completed" and result.eligibility_status == "eligible":
        if len(result.artifacts) != 3:
            raise ResidualModelPersistenceError(
                "eligible training run must contain three artifacts"
            )
    else:
        if result.artifacts:
            raise ResidualModelPersistenceError(
                "non-eligible training run must not contain persisted artifacts"
            )
    for artifact in result.artifacts:
        if not is_sha256_hex(artifact.metadata.binary_sha256):
            raise ResidualModelPersistenceError("artifact binary_sha256 must be canonical SHA-256")


def _validate_prediction_result(result: ResidualPredictionExecutionResult) -> None:
    if not is_sha256_hex(result.config_hash):
        raise ResidualModelPersistenceError("prediction config_hash must be canonical SHA-256")
    if not is_sha256_hex(result.prediction_hash):
        raise ResidualModelPersistenceError("prediction_hash must be canonical SHA-256")
    if result.execution_status == "blocked" and result.rows:
        raise ResidualModelPersistenceError("blocked prediction run must not contain rows")


async def save_residual_training_run(
    session: AsyncSession,
    *,
    result: ResidualTrainingExecutionResult,
    manifest_rows: list[ResidualTrainingManifestRow],
) -> ResidualModelTrainingRun:
    _validate_training_result(result)
    existing = await get_residual_training_run_by_signature(
        session,
        training_signature=result.training_signature,
    )
    payload_hash = _training_payload_hash(result)
    if existing is not None:
        if existing.canonical_payload_hash != payload_hash:
            raise ResidualModelHashConflictError(
                "training signature already exists with a different canonical payload"
            )
        return existing

    feature_schema_hash = _feature_schema_hash(
        cast(list[str], result.metrics.get("feature_names", []))
    )
    run = ResidualModelTrainingRun(
        execution_status=result.execution_status,
        eligibility_status=result.eligibility_status,
        model_family=result.model_family,
        model_version=result.model_version,
        feature_schema_version=result.feature_schema_version,
        feature_schema_hash=feature_schema_hash,
        artifact_schema_version=result.artifact_schema_version,
        training_signature=result.training_signature,
        config_hash=result.config_hash,
        config_snapshot=cast(
            dict[str, Any],
            canonical_json_value(result.input_snapshot["config_snapshot"]),
        ),
        manifest_hash=result.manifest_hash,
        manifest_snapshot=cast(
            dict[str, Any],
            canonical_json_value(
                {
                    "rows": [manifest_row_payload(row) for row in manifest_rows],
                    "summary": result.input_snapshot["manifest_summary"],
                }
            ),
        ),
        feature_audit_summary=cast(
            dict[str, Any],
            canonical_json_value(result.feature_audit_summary),
        ),
        category_encoding_snapshot=cast(
            list[dict[str, Any]],
            canonical_json_value(
                [
                    encoding.model_dump(mode="json")
                    for artifact in result.artifacts
                    for encoding in artifact.metadata.category_encodings
                ]
            ),
        ),
        training_metrics=cast(dict[str, Any], canonical_json_value(result.metrics)),
        validation_metrics={},
        eligibility_reasons=cast(list[str], canonical_json_value(list(result.eligibility_reasons))),
        warnings=cast(list[str], canonical_json_value(list(result.warnings))),
        blockers=cast(list[str], canonical_json_value(list(result.blockers))),
        fallback_reason=None,
        input_snapshot=cast(dict[str, Any], canonical_json_value(result.input_snapshot)),
        canonical_output=_training_storage_payload(result),
        canonical_payload_hash=payload_hash,
        sample_count=result.sample_count,
        distinct_season_count=result.distinct_season_count,
        distinct_factory_count=result.distinct_factory_count,
        manifest_row_count=len(manifest_rows),
        expected_artifact_count=len(result.artifacts),
        python_version=result.artifacts[0].metadata.python_version if result.artifacts else "n/a",
        numpy_version=result.artifacts[0].metadata.numpy_version if result.artifacts else "n/a",
        sklearn_version=result.artifacts[0].metadata.sklearn_version if result.artifacts else "n/a",
        finished_at=(
            _now() if result.execution_status in {"completed", "blocked", "failed"} else None
        ),
        error_message=None,
    )
    session.add(run)
    try:
        await session.flush()
        session.add_all(
            [
                ResidualModelManifestRow(
                    training_run_id=run.id,
                    row_index=index,
                    split=row.split.value,
                    include=row.include,
                    season_id=row.season_id,
                    destination_factory_id=row.destination_factory_id,
                    task9_run_id=row.task9_run_id,
                    task9_result_hash=row.task9_result_hash,
                    as_of_date=row.as_of_date,
                    target_arrival_local_date=row.target_arrival_local_date,
                    forecast_horizon_days=row.forecast_horizon_days,
                    label_analytics_build_run_id=row.label_actual_snapshot.build_run_id,
                    label_actual_source_max_raw_id=row.label_actual_snapshot.source_max_raw_id,
                    label_actual_aggregation_version=row.label_actual_snapshot.aggregation_version,
                    label_actual_config_hash=row.label_actual_snapshot.config_hash,
                    label_actual_source_cutoff=row.label_actual_snapshot.source_cutoff,
                    feature_analytics_build_run_id=row.feature_actual_snapshot.build_run_id,
                    feature_actual_source_max_raw_id=row.feature_actual_snapshot.source_max_raw_id,
                    feature_actual_aggregation_version=row.feature_actual_snapshot.aggregation_version,
                    feature_actual_config_hash=row.feature_actual_snapshot.config_hash,
                    feature_actual_source_cutoff=row.feature_actual_snapshot.source_cutoff,
                    observed_effective_receipt_kg=row.observed_effective_receipt_kg,
                    structural_p50_kg=row.structural_p50_kg,
                    structural_p80_kg=row.structural_p80_kg,
                    structural_p90_kg=row.structural_p90_kg,
                    residual_label_kg=row.residual_label_kg,
                    sample_weight=row.sample_weight,
                    feature_vector_hash=row.feature_vector_hash,
                    feature_visibility_audit_hash=row.feature_visibility_audit_hash,
                    exclusion_reason=row.exclusion_reason,
                    source_refs=cast(list[str], canonical_json_value(list(row.source_refs))),
                    row_payload=cast(
                        dict[str, Any],
                        canonical_json_value(manifest_row_payload(row)),
                    ),
                )
                for index, row in enumerate(manifest_rows, start=1)
            ]
        )
        session.add_all(
            [
                _artifact_model(
                    training_run_id=run.id,
                    feature_schema_hash=feature_schema_hash,
                    config_hash=result.config_hash,
                    artifact=artifact,
                )
                for artifact in result.artifacts
            ]
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        existing = await get_residual_training_run_by_signature(
            session,
            training_signature=result.training_signature,
        )
        if existing is not None and existing.canonical_payload_hash == payload_hash:
            return existing
        raise exc
    return run


def _artifact_model(
    *,
    training_run_id: int,
    feature_schema_hash: str,
    config_hash: str,
    artifact: PersistableResidualArtifact,
) -> ResidualModelArtifact:
    quantile_value = {"P50": "0.5000", "P80": "0.8000", "P90": "0.9000"}[artifact.quantile_label]
    return ResidualModelArtifact(
        training_run_id=training_run_id,
        quantile_label=artifact.quantile_label,
        artifact_format=artifact.metadata.binary_format,
        artifact_schema_version=artifact.metadata.artifact_schema_version,
        estimator_type="HistGradientBoostingRegressor",
        loss_name="quantile",
        quantile_value=quantile_value,
        artifact_bytes=artifact.artifact_bytes,
        artifact_sha256=artifact.metadata.binary_sha256,
        feature_schema_version=artifact.metadata.feature_schema_version,
        feature_schema_hash=feature_schema_hash,
        config_hash=config_hash,
        trusted_internal_source=True,
        artifact_metadata_json=cast(
            dict[str, Any],
            canonical_json_value(artifact.metadata.model_dump(mode="json")),
        ),
        python_version=artifact.metadata.python_version,
        numpy_version=artifact.metadata.numpy_version,
        sklearn_version=artifact.metadata.sklearn_version,
    )


async def load_residual_training_run_by_id(
    session: AsyncSession,
    *,
    run_id: int,
) -> ResidualTrainingExecutionResult | None:
    run = await get_residual_training_run(session, run_id=run_id)
    if run is None:
        return None
    artifacts = await list_residual_artifacts(session, training_run_id=run_id)
    payload = dict(run.canonical_output)
    payload["artifacts"] = [
        {
            "quantile_label": item.quantile_label,
            "artifact_bytes": item.artifact_bytes,
            "metadata": item.artifact_metadata_json,
        }
        for item in artifacts
    ]
    return ResidualTrainingExecutionResult.model_validate(payload)


async def save_residual_prediction_run(
    session: AsyncSession,
    *,
    result: ResidualPredictionExecutionResult,
    feature_schema_version: str,
    feature_schema_hash: str,
    artifact_hashes: list[str],
) -> ResidualModelPredictionRun:
    _validate_prediction_result(result)
    existing = await get_residual_prediction_run_by_input_hash(
        session,
        input_hash=result.prediction_hash,
    )
    payload_hash = _prediction_payload_hash(result)
    if existing is not None:
        if existing.canonical_payload_hash != payload_hash:
            raise ResidualModelHashConflictError(
                "prediction signature already exists with a different canonical payload"
            )
        return existing
    run = ResidualModelPredictionRun(
        training_run_id=result.model_run_id,
        task9_run_id=cast(int, result.task9_run_id),
        task9_result_hash=cast(str, result.task9_result_hash),
        execution_status=result.execution_status,
        mode=result.mode,
        config_hash=result.config_hash,
        feature_schema_version=feature_schema_version,
        feature_schema_hash=feature_schema_hash,
        artifact_hashes=cast(list[str], canonical_json_value(artifact_hashes)),
        input_hash=result.prediction_hash,
        prediction_hash=result.prediction_hash,
        feature_audit={},
        warnings=cast(list[str], canonical_json_value(list(result.warnings))),
        blockers=cast(list[str], canonical_json_value(list(result.blockers))),
        fallback_reason=result.fallback_reason,
        expected_prediction_row_count=len(result.rows),
        input_snapshot=cast(dict[str, Any], canonical_json_value(result.input_snapshot)),
        canonical_output=cast(dict[str, Any], canonical_json_value(result.model_dump(mode="json"))),
        canonical_payload_hash=payload_hash,
        completed_at=(
            _now() if result.execution_status in {"completed", "blocked", "failed"} else None
        ),
        error_message=None,
    )
    session.add(run)
    try:
        await session.flush()
        session.add_all(
            [
                ResidualModelPredictionRow(
                    prediction_run_id=run.id,
                    model_run_id=row.model_run_id,
                    task9_run_id=row.task9_run_id,
                    task9_result_hash=row.task9_result_hash,
                    destination_factory_id=row.destination_factory_id,
                    arrival_local_date=row.arrival_local_date,
                    forecast_horizon_days=row.forecast_horizon_days,
                    structural_p50_kg=row.structural_p50_kg,
                    structural_p80_kg=row.structural_p80_kg,
                    structural_p90_kg=row.structural_p90_kg,
                    raw_residual_p50_kg=row.raw_residual_p50_kg,
                    raw_residual_p80_kg=row.raw_residual_p80_kg,
                    raw_residual_p90_kg=row.raw_residual_p90_kg,
                    corrected_raw_p50_kg=row.corrected_raw_p50_kg,
                    corrected_raw_p80_kg=row.corrected_raw_p80_kg,
                    corrected_raw_p90_kg=row.corrected_raw_p90_kg,
                    corrected_p50_kg=row.corrected_p50_kg,
                    corrected_p80_kg=row.corrected_p80_kg,
                    corrected_p90_kg=row.corrected_p90_kg,
                    nonnegative_projection_applied=row.nonnegative_projection_applied,
                    quantile_projection_applied=row.quantile_projection_applied,
                    projection_reasons=cast(
                        list[str],
                        canonical_json_value(row.projection_reasons),
                    ),
                    feature_vector_hash=row.feature_vector_hash,
                    feature_audit_hash=row.feature_audit_hash,
                    prediction_row_hash=row.prediction_hash,
                    mode=row.mode,
                )
                for row in result.rows
            ]
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        existing = await get_residual_prediction_run_by_input_hash(
            session,
            input_hash=result.prediction_hash,
        )
        if existing is not None and existing.canonical_payload_hash == payload_hash:
            return existing
        raise exc
    return run


async def load_residual_prediction_run_by_id(
    session: AsyncSession,
    *,
    run_id: int,
) -> ResidualPredictionExecutionResult | None:
    run = await get_residual_prediction_run(session, run_id=run_id)
    if run is None:
        return None
    return ResidualPredictionExecutionResult.model_validate(run.canonical_output)


async def load_residual_training_artifacts(
    session: AsyncSession,
    *,
    run_id: int,
) -> tuple[PersistableResidualArtifact, ...]:
    artifacts = await list_residual_artifacts(session, training_run_id=run_id)
    return tuple(
        PersistableResidualArtifact(
            quantile_label=item.quantile_label,
            artifact_bytes=item.artifact_bytes,
            metadata=ResidualArtifactMetadata.model_validate(item.artifact_metadata_json),
        )
        for item in artifacts
    )


async def load_residual_prediction_rows_by_run_id(
    session: AsyncSession,
    *,
    run_id: int,
) -> tuple[ResidualPredictionRow, ...]:
    rows = await list_residual_prediction_rows(session, prediction_run_id=run_id)
    return tuple(
        ResidualPredictionRow.model_validate(
            {
                "model_run_id": row.model_run_id or 0,
                "prediction_run_id": row.prediction_run_id,
                "task9_run_id": row.task9_run_id,
                "task9_result_hash": row.task9_result_hash,
                "destination_factory_id": row.destination_factory_id,
                "arrival_local_date": row.arrival_local_date,
                "forecast_horizon_days": row.forecast_horizon_days,
                "structural_p50_kg": row.structural_p50_kg,
                "structural_p80_kg": row.structural_p80_kg,
                "structural_p90_kg": row.structural_p90_kg,
                "raw_residual_p50_kg": row.raw_residual_p50_kg,
                "raw_residual_p80_kg": row.raw_residual_p80_kg,
                "raw_residual_p90_kg": row.raw_residual_p90_kg,
                "corrected_raw_p50_kg": row.corrected_raw_p50_kg,
                "corrected_raw_p80_kg": row.corrected_raw_p80_kg,
                "corrected_raw_p90_kg": row.corrected_raw_p90_kg,
                "corrected_p50_kg": row.corrected_p50_kg,
                "corrected_p80_kg": row.corrected_p80_kg,
                "corrected_p90_kg": row.corrected_p90_kg,
                "nonnegative_projection_applied": row.nonnegative_projection_applied,
                "quantile_projection_applied": row.quantile_projection_applied,
                "projection_reasons": row.projection_reasons,
                "feature_vector_hash": row.feature_vector_hash,
                "feature_audit_hash": row.feature_audit_hash,
                "prediction_hash": row.prediction_row_hash,
                "mode": row.mode,
            }
        )
        for row in rows
    )
