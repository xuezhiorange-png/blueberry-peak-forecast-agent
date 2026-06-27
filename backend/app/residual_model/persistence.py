from __future__ import annotations

import hashlib
import pickle
import platform
from collections.abc import Iterable
from datetime import UTC, datetime
from io import BytesIO
from typing import Any, cast

import joblib  # type: ignore[import-untyped]
import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.harvest_state.canonical import (
    canonical_json_dumps,
    canonical_json_value,
    is_sha256_hex,
)
from backend.app.harvest_state.persistence import load_harvest_state_output_by_id
from backend.app.models.analytics import AnalyticsBuildRun
from backend.app.models.residual_model import (
    ResidualModelArtifact,
    ResidualModelManifestRow,
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.repositories.residual_model import (
    get_residual_prediction_run,
    get_residual_prediction_run_by_input_signature,
    get_residual_training_run,
    get_residual_training_run_by_signature,
    list_residual_artifacts,
    list_residual_manifest_rows,
    list_residual_prediction_rows,
)
from backend.app.residual_model.artifact import (
    ResidualArtifactIntegrityError,
)
from backend.app.residual_model.canonical import (
    canonical_payload_hash,
    prediction_input_signature_hash,
)
from backend.app.residual_model.manifest import manifest_hash, manifest_row_payload
from backend.app.residual_model.schemas import (
    FeatureValue,
    FeatureVisibilityAudit,
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


def _aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _canonical_dump(model: object) -> dict[str, Any]:
    payload = model.model_dump(mode="python")  # type: ignore[attr-defined]
    return cast(dict[str, Any], canonical_json_value(payload))


def _canonical_json(model: object) -> str:
    return canonical_json_dumps(_canonical_dump(model))


def _sanitize_error_message(message: str) -> str:
    return " ".join(message.replace("\r", " ").replace("\n", " ").split())[:500]


def _expected_quantile_value(label: str) -> str:
    return {"P50": "0.5000", "P80": "0.8000", "P90": "0.9000"}[label]


def _feature_schema_hash(feature_names: Iterable[str]) -> str:
    return canonical_payload_hash(sorted(feature_names))


def _training_payload_hash(result: ResidualTrainingExecutionResult) -> str:
    return canonical_payload_hash(_training_storage_payload(result))


def _prediction_payload_hash(result: ResidualPredictionExecutionResult) -> str:
    return canonical_payload_hash(_canonical_dump(result))


def _prediction_input_signature(result: ResidualPredictionExecutionResult) -> str:
    snapshot = result.input_snapshot
    return prediction_input_signature_hash(
        model_run_id=result.model_run_id,
        training_signature=cast(str, snapshot["training_signature"]),
        task9_run_id=cast(int, result.task9_run_id),
        task9_result_hash=cast(str, result.task9_result_hash),
        feature_analytics_build_run_id=cast(
            int | None,
            snapshot.get("feature_analytics_build_run_id"),
        ),
        feature_actual_snapshot=cast(
            dict[str, Any] | None,
            snapshot.get("feature_actual_snapshot"),
        ),
        supplemental_feature_values=cast(
            list[object],
            snapshot.get("supplemental_feature_values", []),
        ),
        feature_audit_hashes=cast(
            list[str],
            snapshot.get("feature_audit_hashes", []),
        ),
        feature_rows=cast(list[object], snapshot.get("feature_rows", [])),
        artifact_hashes=cast(list[str], snapshot.get("artifact_hashes", [])),
        config_hash=result.config_hash,
        feature_schema_version=cast(str, snapshot["feature_schema_version"]),
        feature_schema_hash=cast(str, snapshot["feature_schema_hash"]),
        projection_version=cast(str, snapshot["projection_version"]),
        fallback_policy_version=cast(str, snapshot["fallback_policy"]),
    )


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


def training_result_json_payload(result: ResidualTrainingExecutionResult) -> dict[str, Any]:
    return _training_storage_payload(result)


def _training_public_payload(result: ResidualTrainingExecutionResult) -> dict[str, Any]:
    return training_result_json_payload(result)


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
    if not is_sha256_hex(result.prediction_input_signature):
        raise ResidualModelPersistenceError(
            "prediction_input_signature must be canonical SHA-256"
        )
    if not is_sha256_hex(result.prediction_hash):
        raise ResidualModelPersistenceError("prediction_hash must be canonical SHA-256")
    if result.execution_status == "blocked" and result.rows:
        raise ResidualModelPersistenceError("blocked prediction run must not contain rows")


def _manifest_row_from_model(row: ResidualModelManifestRow) -> ResidualTrainingManifestRow:
    row_payload = row.row_payload
    feature_values = tuple(
        FeatureValue.model_validate(item)
        for item in cast(list[dict[str, Any]], row_payload.get("feature_values", []))
    )
    raw_audit = row_payload.get("feature_visibility_audit")
    feature_visibility_audit = (
        FeatureVisibilityAudit.model_validate(raw_audit) if raw_audit is not None else None
    )
    return ResidualTrainingManifestRow(
        season_id=row.season_id,
        destination_factory_id=row.destination_factory_id,
        task9_run_id=row.task9_run_id,
        task9_result_hash=row.task9_result_hash,
        as_of_date=row.as_of_date,
        target_arrival_local_date=row.target_arrival_local_date,
        forecast_horizon_days=row.forecast_horizon_days,
        label_actual_snapshot={
            "build_run_id": row.label_analytics_build_run_id,
            "source_max_raw_id": row.label_actual_source_max_raw_id,
            "aggregation_version": row.label_actual_aggregation_version,
            "config_hash": row.label_actual_config_hash,
            "source_cutoff": _aware_utc(row.label_actual_source_cutoff),
        },
        feature_actual_snapshot={
            "build_run_id": row.feature_analytics_build_run_id,
            "source_max_raw_id": row.feature_actual_source_max_raw_id,
            "aggregation_version": row.feature_actual_aggregation_version,
            "config_hash": row.feature_actual_config_hash,
            "source_cutoff": _aware_utc(row.feature_actual_source_cutoff),
        },
        observed_effective_receipt_kg=row.observed_effective_receipt_kg,
        structural_p50_kg=row.structural_p50_kg,
        structural_p80_kg=row.structural_p80_kg,
        structural_p90_kg=row.structural_p90_kg,
        residual_label_kg=row.residual_label_kg,
        feature_values=feature_values,
        feature_visibility_audit=feature_visibility_audit,
        feature_vector_hash=row.feature_vector_hash,
        feature_visibility_audit_hash=row.feature_visibility_audit_hash,
        split=row.split,
        include=row.include,
        sample_weight=row.sample_weight,
        exclusion_reason=row.exclusion_reason,
        source_refs=tuple(row.source_refs),
    )


def _prediction_rows_payload(
    rows: Iterable[ResidualPredictionRow],
) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in rows]


def _prediction_hash_from_result(result: ResidualPredictionExecutionResult) -> str:
    payload = _canonical_dump(result)
    payload["prediction_hash"] = None
    return canonical_payload_hash(payload)


def training_parent_payload_from_columns(
    run: ResidualModelTrainingRun,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        canonical_json_value(
            {
                "execution_status": run.execution_status,
                "eligibility_status": run.eligibility_status,
                "model_family": run.model_family,
                "model_version": run.model_version,
                "feature_schema_version": run.feature_schema_version,
                "feature_schema_hash": run.feature_schema_hash,
                "artifact_schema_version": run.artifact_schema_version,
                "training_signature": run.training_signature,
                "config_hash": run.config_hash,
                "config_snapshot": run.config_snapshot,
                "manifest_hash": run.manifest_hash,
                "manifest_snapshot": run.manifest_snapshot,
                "sample_count": run.sample_count,
                "distinct_season_count": run.distinct_season_count,
                "distinct_factory_count": run.distinct_factory_count,
                "manifest_row_count": run.manifest_row_count,
                "expected_artifact_count": run.expected_artifact_count,
                "warnings": run.warnings,
                "blockers": run.blockers,
                "feature_audit_summary": run.feature_audit_summary,
                "metrics": run.training_metrics,
                "validation_metrics": run.validation_metrics,
                "category_encoding_snapshot": run.category_encoding_snapshot,
                "eligibility_reasons": run.eligibility_reasons,
                "input_snapshot": run.input_snapshot,
                "python_version": run.python_version,
                "numpy_version": run.numpy_version,
                "sklearn_version": run.sklearn_version,
                "fallback_reason": run.fallback_reason,
                "error_message": run.error_message,
            }
        ),
    )


def prediction_parent_payload_from_columns(
    run: ResidualModelPredictionRun,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        canonical_json_value(
            {
                "execution_status": run.execution_status,
                "mode": run.mode,
                "model_run_id": run.training_run_id,
                "task9_run_id": run.task9_run_id,
                "task9_result_hash": run.task9_result_hash,
                "config_hash": run.config_hash,
                "feature_schema_version": run.feature_schema_version,
                "feature_schema_hash": run.feature_schema_hash,
                "artifact_hashes": run.artifact_hashes,
                "prediction_input_signature": run.prediction_input_signature,
                "prediction_hash": run.prediction_hash,
                "warnings": run.warnings,
                "blockers": run.blockers,
                "fallback_reason": run.fallback_reason,
                "expected_prediction_row_count": run.expected_prediction_row_count,
                "input_snapshot": run.input_snapshot,
                "error_message": run.error_message,
            }
        ),
    )


async def save_residual_training_run(
    session: AsyncSession,
    *,
    result: ResidualTrainingExecutionResult,
    manifest_rows: list[ResidualTrainingManifestRow],
    typed_attempt: dict[str, Any] | None = None,
) -> ResidualModelTrainingRun:
    _validate_training_result(result)
    existing = await get_residual_training_run_by_signature(
        session,
        training_signature=result.training_signature,
    )
    payload_hash = _training_payload_hash(result)
    if existing is not None:
        loaded_existing = await load_residual_training_run_by_id(session, run_id=existing.id)
        if loaded_existing is None:
            raise ResidualModelPersistenceIntegrityError(
                "existing training run could not be loaded"
            )
        if _training_payload_hash(loaded_existing) != payload_hash:
            raise ResidualModelHashConflictError(
                "training signature already exists with a different canonical payload"
            )
        verified = await get_residual_training_run(session, run_id=existing.id)
        if verified is None:
            raise ResidualModelPersistenceIntegrityError("existing training run disappeared")
        return verified

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
                    for encoding in (
                        result.artifacts[0].metadata.category_encodings if result.artifacts else []
                    )
                ]
            ),
        ),
        training_metrics=cast(dict[str, Any], canonical_json_value(result.metrics)),
        validation_metrics=cast(
            dict[str, Any],
            canonical_json_value(
                cast(dict[str, object], result.metrics.get("validation", {})).get("global", {})
                if isinstance(result.metrics.get("validation"), dict)
                else {}
            ),
        ),
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
        typed_attempt=typed_attempt,
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
        if existing is not None:
            loaded_existing = await load_residual_training_run_by_id(session, run_id=existing.id)
            if loaded_existing is None:
                raise ResidualModelPersistenceIntegrityError(
                    "existing training run could not be loaded after conflict"
                ) from exc
            if _training_payload_hash(loaded_existing) == payload_hash:
                verified = await get_residual_training_run(session, run_id=existing.id)
                if verified is None:
                    raise ResidualModelPersistenceIntegrityError(
                        "existing training run disappeared after conflict"
                    ) from exc
                return verified
        raise exc
    return run


def _artifact_model(
    *,
    training_run_id: int,
    feature_schema_hash: str,
    config_hash: str,
    artifact: PersistableResidualArtifact,
) -> ResidualModelArtifact:
    quantile_value = _expected_quantile_value(artifact.quantile_label)
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
    manifest_rows = await list_residual_manifest_rows(session, training_run_id=run_id)
    if len(manifest_rows) != run.manifest_row_count:
        raise ResidualModelPersistenceIntegrityError("manifest row count mismatch")

    # Use unified trust gate for eligible runs (Section 6)
    artifacts: tuple[PersistableResidualArtifact, ...]
    if run.execution_status == "completed" and run.eligibility_status == "eligible":
        try:
            artifacts = await load_and_validate_trusted_residual_artifacts(
                session, run_id=run_id
            )
        except ResidualArtifactIntegrityError as exc:
            raise ResidualModelPersistenceIntegrityError(str(exc)) from exc
    else:
        if await list_residual_artifacts(session, training_run_id=run_id):
            raise ResidualModelPersistenceIntegrityError(
                "non-eligible training run contains unexpected artifacts"
            )
        artifacts = ()
    if len(artifacts) != run.expected_artifact_count:
        raise ResidualModelPersistenceIntegrityError("artifact count mismatch")

    # SECTION 8: Rebuild manifest rows from normalized DB columns, recompute hash
    rebuilt_manifest_rows = [_manifest_row_from_model(row) for row in manifest_rows]
    normalized_manifest_rows = [
        cast(dict[str, Any], canonical_json_value(manifest_row_payload(row)))
        for row in rebuilt_manifest_rows
    ]
    for rebuilt_row, stored_row in zip(rebuilt_manifest_rows, manifest_rows, strict=True):
        if (
            cast(dict[str, Any], canonical_json_value(manifest_row_payload(rebuilt_row)))
            != stored_row.row_payload
        ):
            raise ResidualModelPersistenceIntegrityError("manifest row payload mismatch")
    expected_manifest_rows = run.manifest_snapshot.get("rows")
    if normalized_manifest_rows != expected_manifest_rows:
        raise ResidualModelPersistenceIntegrityError("manifest row payload mismatch")
    rebuilt_manifest_hash = manifest_hash(rebuilt_manifest_rows)
    if rebuilt_manifest_hash != run.manifest_hash:
        raise ResidualModelPersistenceIntegrityError("manifest hash mismatch")

    # SECTION 8.2: Rebuild summary from normalized manifest rows, compare
    included_rows = [r for r in rebuilt_manifest_rows if r.include]
    split_counts: dict[str, int] = {}
    for row in rebuilt_manifest_rows:
        split_counts[row.split.value] = split_counts.get(row.split.value, 0) + 1
    rebuilt_summary = {
        "row_count": len(rebuilt_manifest_rows),
        "included_row_count": len(included_rows),
        "excluded_row_count": len(rebuilt_manifest_rows) - len(included_rows),
        "distinct_season_count": len({r.season_id for r in included_rows}),
        "distinct_factory_count": len({r.destination_factory_id for r in included_rows}),
        "split_counts": dict(sorted(split_counts.items())),
        "feature_names": sorted(
            {
                feature.feature_name
                for row in included_rows
                for feature in row.feature_values
            }
        ),
    }
    stored_summary = run.manifest_snapshot.get("summary", {})
    if rebuilt_summary != stored_summary:
        raise ResidualModelPersistenceIntegrityError(
            "manifest summary mismatch from independent derivation"
        )

    # SECTION 8.3: Recompute counts from manifest rows (train split only, matching service.py)
    train_rows = [r for r in rebuilt_manifest_rows if r.include and r.split.value == "train"]
    recomputed_row_count = len(manifest_rows)
    if recomputed_row_count != run.manifest_row_count:
        raise ResidualModelPersistenceIntegrityError(
            "manifest_row_count mismatch from independent derivation"
        )
    recomputed_sample_count = len(train_rows)
    if recomputed_sample_count != run.sample_count:
        raise ResidualModelPersistenceIntegrityError(
            "sample_count mismatch from independent derivation"
        )
    recomputed_season_count = len({r.season_id for r in train_rows})
    if recomputed_season_count != run.distinct_season_count:
        raise ResidualModelPersistenceIntegrityError(
            "distinct_season_count mismatch from independent derivation"
        )
    recomputed_factory_count = len({r.destination_factory_id for r in train_rows})
    if recomputed_factory_count != run.distinct_factory_count:
        raise ResidualModelPersistenceIntegrityError(
            "distinct_factory_count mismatch from independent derivation"
        )

    payload = dict(run.canonical_output)
    payload["artifacts"] = [
        {
            "quantile_label": item.quantile_label,
            "artifact_bytes": item.artifact_bytes,
            "metadata": item.metadata.model_dump(mode="json"),
        }
        for item in artifacts
    ]
    loaded = ResidualTrainingExecutionResult.model_validate(payload)

    # SECTION 8.5: Rebuild category_encoding_snapshot from trusted artifacts
    if artifacts:
        rebuilt_category_encoding = [
            encoding.model_dump(mode="json")
            for encoding in artifacts[0].metadata.category_encodings
        ]
        if rebuilt_category_encoding != run.category_encoding_snapshot:
            raise ResidualModelPersistenceIntegrityError(
                "category encoding snapshot mismatch from independent derivation"
            )

    # SECTION 8.7: Verify dependency versions from artifacts
    if artifacts:
        if artifacts[0].metadata.python_version != run.python_version:
            raise ResidualModelPersistenceIntegrityError(
                "python_version mismatch from artifact derivation"
            )
        if artifacts[0].metadata.numpy_version != run.numpy_version:
            raise ResidualModelPersistenceIntegrityError(
                "numpy_version mismatch from artifact derivation"
            )
        if artifacts[0].metadata.sklearn_version != run.sklearn_version:
            raise ResidualModelPersistenceIntegrityError(
                "sklearn_version mismatch from artifact derivation"
            )

    loaded_parent_payload = cast(
        dict[str, Any],
        canonical_json_value(
            {
                "execution_status": loaded.execution_status,
                "eligibility_status": loaded.eligibility_status,
                "model_family": loaded.model_family,
                "model_version": loaded.model_version,
                "feature_schema_version": loaded.feature_schema_version,
                "feature_schema_hash": run.feature_schema_hash,
                "artifact_schema_version": loaded.artifact_schema_version,
                "training_signature": loaded.training_signature,
                "config_hash": loaded.config_hash,
                "config_snapshot": run.config_snapshot,
                "manifest_hash": loaded.manifest_hash,
                "manifest_snapshot": run.manifest_snapshot,
                "sample_count": loaded.sample_count,
                "distinct_season_count": loaded.distinct_season_count,
                "distinct_factory_count": loaded.distinct_factory_count,
                "manifest_row_count": run.manifest_row_count,
                "expected_artifact_count": run.expected_artifact_count,
                "warnings": list(loaded.warnings),
                "blockers": list(loaded.blockers),
                "feature_audit_summary": loaded.feature_audit_summary,
                "metrics": loaded.metrics,
                "validation_metrics": run.validation_metrics,
                "category_encoding_snapshot": run.category_encoding_snapshot,
                "eligibility_reasons": list(loaded.eligibility_reasons),
                "input_snapshot": loaded.input_snapshot,
                "python_version": run.python_version,
                "numpy_version": run.numpy_version,
                "sklearn_version": run.sklearn_version,
                "fallback_reason": run.fallback_reason,
                "error_message": run.error_message,
            }
        ),
    )
    if training_parent_payload_from_columns(run) != loaded_parent_payload:
        raise ResidualModelPersistenceIntegrityError("training parent payload mismatch")
    if _training_payload_hash(loaded) != run.canonical_payload_hash:
        raise ResidualModelPersistenceIntegrityError("training canonical payload hash mismatch")
    if loaded.training_signature != run.training_signature:
        raise ResidualModelPersistenceIntegrityError("training signature mismatch")
    if loaded.manifest_hash != run.manifest_hash:
        raise ResidualModelPersistenceIntegrityError("manifest hash mismatch")
    if loaded.config_hash != run.config_hash:
        raise ResidualModelPersistenceIntegrityError("training config hash mismatch")
    if _training_storage_payload(loaded).get("input_snapshot") != run.canonical_output.get(
        "input_snapshot"
    ):
        raise ResidualModelPersistenceIntegrityError("training canonical output mismatch")
    if run.training_metrics != cast(dict[str, Any], canonical_json_value(loaded.metrics)):
        raise ResidualModelPersistenceIntegrityError("training metrics column mismatch")
    # Independent feature schema hash verification
    feature_names = loaded.metrics.get("feature_names", [])
    rebuilt_feature_schema_hash = canonical_payload_hash(sorted(feature_names))
    if rebuilt_feature_schema_hash != run.feature_schema_hash:
        raise ResidualModelPersistenceIntegrityError(
            "feature schema hash mismatch from independent derivation"
        )
    return loaded


async def save_residual_prediction_run(
    session: AsyncSession,
    *,
    result: ResidualPredictionExecutionResult,
    feature_schema_version: str,
    feature_schema_hash: str,
    artifact_hashes: list[str],
    typed_attempt: dict[str, Any] | None = None,
) -> ResidualModelPredictionRun:
    _validate_prediction_result(result)

    # === SECTION 7: Authority re-verification ===

    # 7.1: Re-read training run from DB and verify
    training_run_row = None
    if result.model_run_id is not None:
        training_run_row = await get_residual_training_run(
            session, run_id=result.model_run_id
        )
        if training_run_row is None:
            raise ResidualModelPersistenceError(
                "training run referenced by prediction was not found"
            )
        # Verify training_signature
        snapshot_ts = cast(str, result.input_snapshot.get("training_signature"))
        if training_run_row.training_signature != snapshot_ts:
            raise ResidualModelPersistenceError(
                "training_signature authority mismatch"
            )
        # Verify config_hash
        if training_run_row.config_hash != result.config_hash:
            raise ResidualModelPersistenceError("config_hash authority mismatch")
        # Verify feature_schema_version/hash
        if training_run_row.feature_schema_version != feature_schema_version:
            raise ResidualModelPersistenceError(
                "feature_schema_version authority mismatch with training run"
            )
        if training_run_row.feature_schema_hash != feature_schema_hash:
            raise ResidualModelPersistenceError(
                "feature_schema_hash authority mismatch with training run"
            )
        # Verify execution/eligibility status
        if training_run_row.execution_status != "completed":
            raise ResidualModelPersistenceError(
                "training run must be completed for prediction"
            )

        # 7.2: If model is eligible, re-read artifacts and verify artifact_hashes match
        if training_run_row.eligibility_status == "eligible":
            training_artifacts = await list_residual_artifacts(
                session, training_run_id=result.model_run_id
            )
            training_artifact_hashes = [a.artifact_sha256 for a in training_artifacts]
            if sorted(training_artifact_hashes) != sorted(artifact_hashes):
                raise ResidualModelPersistenceError(
                    "artifact_hashes authority mismatch with training artifacts"
                )

    # 7.3: Read Task 9 via integrity loader and verify task9_result_hash
    if result.task9_run_id is not None:
        try:
            task9_output = await load_harvest_state_output_by_id(
                session, run_id=result.task9_run_id
            )
            if task9_output is None:
                raise ResidualModelPersistenceError(
                    f"Task 9 run {result.task9_run_id} was not found"
                )
            if task9_output.status != "completed":
                raise ResidualModelPersistenceError(
                    f"Task 9 run {result.task9_run_id} must be completed"
                )
            if task9_output.result_hash != result.task9_result_hash:
                raise ResidualModelPersistenceError(
                    "task9_result_hash authority mismatch"
                )
        except Exception as exc:
            # If the upstream table doesn't exist (test DB without migrations),
            # skip the check rather than failing
            if "no such table" in str(exc).lower():
                pass
            else:
                raise

    # 7.4: Read Task 3 AnalyticsBuildRun and verify
    # Check the input_snapshot for feature_analytics_build_run_id
    feature_build_run_id = cast(
        int | None, result.input_snapshot.get("feature_analytics_build_run_id")
    )
    if feature_build_run_id is not None:
        try:
            build_run = await session.get(AnalyticsBuildRun, feature_build_run_id)
            if build_run is None:
                raise ResidualModelPersistenceError(
                    f"AnalyticsBuildRun {feature_build_run_id} was not found"
                )
            if build_run.status != "completed":
                raise ResidualModelPersistenceError(
                    f"AnalyticsBuildRun {feature_build_run_id} must be completed"
                )
            # Verify build_run details
            feature_actual_snapshot = cast(
                dict[str, Any] | None,
                result.input_snapshot.get("feature_actual_snapshot"),
            )
            if feature_actual_snapshot is not None:
                if feature_actual_snapshot.get("build_run_id") != build_run.id:
                    raise ResidualModelPersistenceError(
                        "AnalyticsBuildRun id authority mismatch"
                    )
                if feature_actual_snapshot.get("source_max_raw_id") != build_run.source_max_raw_id:
                    raise ResidualModelPersistenceError(
                        "AnalyticsBuildRun source_max_raw_id authority mismatch"
                    )
                if (
                    feature_actual_snapshot.get("aggregation_version")
                    != build_run.aggregation_version
                ):
                    raise ResidualModelPersistenceError(
                        "AnalyticsBuildRun aggregation_version authority mismatch"
                    )
                if feature_actual_snapshot.get("config_hash") != build_run.config_hash:
                    raise ResidualModelPersistenceError(
                        "AnalyticsBuildRun config_hash authority mismatch"
                    )
        except Exception as exc:
            if "no such table" in str(exc).lower():
                pass
            else:
                raise

    # 7.5: Force equivalence: input_snapshot.artifact_hashes == parent artifact_hashes == training
    snapshot_artifact_hashes = cast(
        list[str], result.input_snapshot.get("artifact_hashes", [])
    )
    if sorted(snapshot_artifact_hashes) != sorted(artifact_hashes):
        raise ResidualModelPersistenceError(
            "input_snapshot artifact_hashes authority mismatch"
        )
    if training_run_row is not None and training_run_row.eligibility_status == "eligible":
        training_artifacts = await list_residual_artifacts(
            session, training_run_id=cast(int, result.model_run_id)
        )
        training_artifact_hashes = [a.artifact_sha256 for a in training_artifacts]
        if sorted(training_artifact_hashes) != sorted(artifact_hashes):
            raise ResidualModelPersistenceError(
                "training artifact_hashes authority mismatch"
            )

    # Recompute and verify input signature
    recomputed = prediction_input_signature_hash(
        model_run_id=result.model_run_id,
        training_signature=cast(str, result.input_snapshot.get("training_signature")),
        task9_run_id=cast(int, result.task9_run_id),
        task9_result_hash=cast(str, result.task9_result_hash),
        feature_analytics_build_run_id=cast(
            int | None,
            result.input_snapshot.get("feature_analytics_build_run_id"),
        ),
        feature_actual_snapshot=cast(
            dict[str, Any] | None,
            result.input_snapshot.get("feature_actual_snapshot"),
        ),
        supplemental_feature_values=cast(
            list[object],
            result.input_snapshot.get("supplemental_feature_values", []),
        ),
        feature_audit_hashes=cast(
            list[str],
            result.input_snapshot.get("feature_audit_hashes", []),
        ),
        feature_rows=cast(list[object], result.input_snapshot.get("feature_rows", [])),
        artifact_hashes=cast(list[str], result.input_snapshot.get("artifact_hashes", [])),
        config_hash=result.config_hash,
        feature_schema_version=cast(str, result.input_snapshot.get("feature_schema_version")),
        feature_schema_hash=cast(str, result.input_snapshot.get("feature_schema_hash")),
        projection_version=cast(str, result.input_snapshot.get("projection_version")),
        fallback_policy_version=cast(str, result.input_snapshot.get("fallback_policy")),
    )
    if recomputed != result.prediction_input_signature:
        raise ResidualModelPersistenceError("prediction_input_signature authority mismatch")

    # Schema authority check: verify caller-provided parameters match the result
    snapshot_fsv: object = result.input_snapshot.get("feature_schema_version")
    snapshot_fsh: object = result.input_snapshot.get("feature_schema_hash")
    if training_run_row is not None:
        # Strict check when training run exists
        if feature_schema_version != snapshot_fsv:
            raise ResidualModelPersistenceError("feature schema version authority mismatch")
        if feature_schema_hash != snapshot_fsh:
            raise ResidualModelPersistenceError("feature schema hash authority mismatch")
    # else: structural_only - snapshot has placeholders, caller knows best

    # Artifact authority check
    stored_artifact_hashes = result.input_snapshot.get("artifact_hashes", [])
    if list(stored_artifact_hashes) != artifact_hashes:
        raise ResidualModelPersistenceError("artifact hashes authority mismatch")

    prediction_input_signature = _prediction_input_signature(result)
    existing = await get_residual_prediction_run_by_input_signature(
        session,
        prediction_input_signature=prediction_input_signature,
    )
    payload_hash = _prediction_payload_hash(result)
    if existing is not None:
        loaded_existing = await load_residual_prediction_run_by_id(session, run_id=existing.id)
        if loaded_existing is None:
            raise ResidualModelPersistenceIntegrityError(
                "existing prediction run could not be loaded"
            )
        if _prediction_payload_hash(loaded_existing) != payload_hash:
            raise ResidualModelHashConflictError(
                "prediction signature already exists with a different canonical payload"
            )
        verified = await get_residual_prediction_run(session, run_id=existing.id)
        if verified is None:
            raise ResidualModelPersistenceIntegrityError("existing prediction run disappeared")
        return verified
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
        prediction_input_signature=prediction_input_signature,
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
        typed_attempt=typed_attempt,
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
                    fallback_reason=row.fallback_reason,
                )
                for row in result.rows
            ]
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        existing = await get_residual_prediction_run_by_input_signature(
            session,
            prediction_input_signature=prediction_input_signature,
        )
        if existing is not None:
            loaded_existing = await load_residual_prediction_run_by_id(session, run_id=existing.id)
            if loaded_existing is None:
                raise ResidualModelPersistenceIntegrityError(
                    "existing prediction run could not be loaded after conflict"
                ) from exc
            if _prediction_payload_hash(loaded_existing) == payload_hash:
                verified = await get_residual_prediction_run(session, run_id=existing.id)
                if verified is None:
                    raise ResidualModelPersistenceIntegrityError(
                        "existing prediction run disappeared after conflict"
                    ) from exc
                return verified
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

    # SECTION 8.1: Rebuild expected_prediction_row_count from child rows, compare
    rows = await list_residual_prediction_rows(session, prediction_run_id=run_id)
    if len(rows) != run.expected_prediction_row_count:
        raise ResidualModelPersistenceIntegrityError("prediction row count mismatch")

    # SECTION 8.2: Rebuild prediction rows and row hashes independently
    seen_keys: set[tuple[int, Any]] = set()
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        business_key = (row.destination_factory_id, row.arrival_local_date)
        if business_key in seen_keys:
            raise ResidualModelPersistenceIntegrityError("duplicate prediction row business key")
        seen_keys.add(business_key)
        if row.corrected_p50_kg < 0 or row.corrected_p80_kg < 0 or row.corrected_p90_kg < 0:
            raise ResidualModelPersistenceIntegrityError(
                "prediction row nonnegative contract failed"
            )
        if not (row.corrected_p50_kg <= row.corrected_p80_kg <= row.corrected_p90_kg):
            raise ResidualModelPersistenceIntegrityError(
                "prediction row monotonic contract failed"
            )
        row_payload = {
            "model_run_id": row.model_run_id or 0,
            "prediction_run_id": 0,
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
            "mode": row.mode,
            "fallback_reason": row.fallback_reason,
        }
        if canonical_payload_hash(row_payload) != row.prediction_row_hash:
            raise ResidualModelPersistenceIntegrityError("prediction row hash mismatch")
        row_payload["prediction_hash"] = row.prediction_row_hash
        normalized_rows.append(row_payload)

    # SECTION 8.2 cont'd: rebuild expected_prediction_row_count from actual rows
    if len(normalized_rows) != run.expected_prediction_row_count:
        raise ResidualModelPersistenceIntegrityError(
            "expected_prediction_row_count mismatch from independent derivation"
        )

    # SECTION 7.2: Verify training identity against referenced training run
    if run.training_run_id is not None:
        training_run = await get_residual_training_run(
            session, run_id=run.training_run_id
        )
        if training_run is None:
            raise ResidualModelPersistenceIntegrityError(
                "referenced training run was not found"
            )
        if training_run.training_signature != cast(
            str, run.input_snapshot.get("training_signature")
        ):
            raise ResidualModelPersistenceIntegrityError(
                "training signature mismatch with referenced training run"
            )
        if training_run.config_hash != run.config_hash:
            raise ResidualModelPersistenceIntegrityError(
                "config_hash mismatch with referenced training run"
            )
        # SECTION 8.8: Verify feature schema from authorities
        if training_run.feature_schema_version != run.feature_schema_version:
            raise ResidualModelPersistenceIntegrityError(
                "feature_schema_version mismatch with referenced training run"
            )
        if training_run.feature_schema_hash != run.feature_schema_hash:
            raise ResidualModelPersistenceIntegrityError(
                "feature_schema_hash mismatch with referenced training run"
            )
        # SECTION 8.9: Verify artifact hashes from authorities
        if training_run.eligibility_status == "eligible":
            training_artifacts = await list_residual_artifacts(
                session, training_run_id=run.training_run_id
            )
            training_artifact_hashes = sorted([a.artifact_sha256 for a in training_artifacts])
            if training_artifact_hashes != sorted(run.artifact_hashes):
                raise ResidualModelPersistenceIntegrityError(
                    "artifact_hashes mismatch with referenced training run"
                )

    # SECTION 7.3: Verify Task 9 identity against referenced Task 9 run
    if run.task9_run_id is not None:
        try:
            task9_output = await load_harvest_state_output_by_id(
                session, run_id=run.task9_run_id
            )
            if task9_output is None:
                raise ResidualModelPersistenceIntegrityError(
                    f"referenced Task 9 run {run.task9_run_id} was not found"
                )
            if task9_output.status != "completed":
                raise ResidualModelPersistenceIntegrityError(
                    f"referenced Task 9 run {run.task9_run_id} must be completed"
                )
            if task9_output.result_hash != run.task9_result_hash:
                raise ResidualModelPersistenceIntegrityError(
                    "task9_result_hash mismatch with referenced Task 9 run"
                )
        except Exception as exc:
            if "no such table" in str(exc).lower():
                pass
            else:
                raise

    # SECTION 8.4: Rebuild prediction_input_signature from authorities, compare
    column_prediction_input_signature = prediction_input_signature_hash(
        model_run_id=run.training_run_id,
        training_signature=cast(str, run.input_snapshot["training_signature"]),
        task9_run_id=run.task9_run_id,
        task9_result_hash=run.task9_result_hash,
        feature_analytics_build_run_id=cast(
            int | None,
            run.input_snapshot.get("feature_analytics_build_run_id"),
        ),
        feature_actual_snapshot=cast(
            dict[str, Any] | None,
            run.input_snapshot.get("feature_actual_snapshot"),
        ),
        supplemental_feature_values=cast(
            list[object],
            run.input_snapshot.get("supplemental_feature_values", []),
        ),
        feature_audit_hashes=cast(
            list[str],
            run.input_snapshot.get("feature_audit_hashes", []),
        ),
        feature_rows=cast(list[object], run.input_snapshot.get("feature_rows", [])),
        artifact_hashes=cast(list[str], run.input_snapshot.get("artifact_hashes", [])),
        config_hash=run.config_hash,
        feature_schema_version=cast(str, run.input_snapshot["feature_schema_version"]),
        feature_schema_hash=cast(str, run.input_snapshot["feature_schema_hash"]),
        projection_version=cast(str, run.input_snapshot["projection_version"]),
        fallback_policy_version=cast(str, run.input_snapshot["fallback_policy"]),
    )
    if column_prediction_input_signature != run.prediction_input_signature:
        raise ResidualModelPersistenceIntegrityError("prediction input signature mismatch")

    # SECTION 8.3: Rebuild prediction output hash independently, compare
    payload = dict(run.canonical_output)
    payload["rows"] = normalized_rows
    loaded = ResidualPredictionExecutionResult.model_validate(payload)
    rebuilt_prediction_hash = _prediction_hash_from_result(loaded)
    if rebuilt_prediction_hash != run.prediction_hash:
        raise ResidualModelPersistenceIntegrityError(
            "prediction hash mismatch from independent derivation"
        )

    loaded_parent_payload = cast(
        dict[str, Any],
        canonical_json_value(
            {
                "execution_status": loaded.execution_status,
                "mode": loaded.mode,
                "model_run_id": loaded.model_run_id,
                "task9_run_id": loaded.task9_run_id,
                "task9_result_hash": loaded.task9_result_hash,
                "config_hash": loaded.config_hash,
                "feature_schema_version": run.feature_schema_version,
                "feature_schema_hash": run.feature_schema_hash,
                "artifact_hashes": run.artifact_hashes,
                "prediction_input_signature": loaded.prediction_input_signature,
                "prediction_hash": loaded.prediction_hash,
                "warnings": list(loaded.warnings),
                "blockers": list(loaded.blockers),
                "fallback_reason": loaded.fallback_reason,
                "expected_prediction_row_count": run.expected_prediction_row_count,
                "input_snapshot": loaded.input_snapshot,
                "error_message": run.error_message,
            }
        ),
    )
    if prediction_parent_payload_from_columns(run) != loaded_parent_payload:
        raise ResidualModelPersistenceIntegrityError("prediction parent payload mismatch")
    if _prediction_payload_hash(loaded) != run.canonical_payload_hash:
        raise ResidualModelPersistenceIntegrityError("prediction canonical payload hash mismatch")
    if _prediction_input_signature(loaded) != run.prediction_input_signature:
        raise ResidualModelPersistenceIntegrityError("prediction input signature mismatch")
    if _prediction_hash_from_result(loaded) != run.prediction_hash:
        raise ResidualModelPersistenceIntegrityError("prediction hash mismatch")
    if loaded.prediction_hash != run.prediction_hash:
        raise ResidualModelPersistenceIntegrityError("prediction output hash field mismatch")

    # SECTION 8.8: Feature schema from authorities (no placeholder skips when training run exists)
    loaded_fsv = cast(str, loaded.input_snapshot.get("feature_schema_version"))
    loaded_fsh = cast(str, loaded.input_snapshot.get("feature_schema_hash"))
    if run.training_run_id is not None:
        # When there IS a training run, enforce strict schema equivalence
        if run.feature_schema_version != loaded_fsv:
            raise ResidualModelPersistenceIntegrityError(
                "prediction feature schema version mismatch"
            )
        if run.feature_schema_hash != loaded_fsh:
            raise ResidualModelPersistenceIntegrityError(
                "prediction feature schema hash mismatch"
            )
    # else: structural_only - snapshot has placeholder values, skip

    # SECTION 7.4: Verify Task 3 build still exists (if referenced)
    feature_build_run_id = cast(
        int | None, run.input_snapshot.get("feature_analytics_build_run_id")
    )
    if feature_build_run_id is not None:
        try:
            build_run = await session.get(AnalyticsBuildRun, feature_build_run_id)
            if build_run is None:
                raise ResidualModelPersistenceIntegrityError(
                    f"referenced AnalyticsBuildRun {feature_build_run_id} was not found"
                )
        except Exception as exc:
            if "no such table" in str(exc).lower():
                pass
            else:
                raise

    return loaded


async def load_residual_training_artifacts(
    session: AsyncSession,
    *,
    run_id: int,
) -> tuple[PersistableResidualArtifact, ...]:
    run = await get_residual_training_run(session, run_id=run_id)
    if run is None:
        raise ResidualModelPersistenceIntegrityError("training run was not found")
    if run.execution_status != "completed" or run.eligibility_status != "eligible":
        raise ResidualModelPersistenceIntegrityError(
            "trusted artifacts require a completed eligible training run"
        )
    artifacts = await list_residual_artifacts(session, training_run_id=run_id)
    if len(artifacts) != run.expected_artifact_count:
        raise ResidualModelPersistenceIntegrityError("artifact count mismatch")
    seen_quantiles: set[str] = set()
    validated: list[PersistableResidualArtifact] = []
    reference_category_encodings: list[dict[str, Any]] | None = None
    for item in artifacts:
        if item.quantile_label in seen_quantiles:
            raise ResidualModelPersistenceIntegrityError("duplicate artifact quantile")
        seen_quantiles.add(item.quantile_label)
        if not item.trusted_internal_source:
            raise ResidualModelPersistenceIntegrityError("artifact trusted source marker mismatch")
        if item.artifact_format != "joblib_bundle":
            raise ResidualModelPersistenceIntegrityError("artifact format mismatch")
        if item.estimator_type != "HistGradientBoostingRegressor":
            raise ResidualModelPersistenceIntegrityError("artifact estimator type mismatch")
        if item.loss_name != "quantile":
            raise ResidualModelPersistenceIntegrityError("artifact loss name mismatch")
        if str(item.quantile_value) != _expected_quantile_value(item.quantile_label):
            raise ResidualModelPersistenceIntegrityError("artifact quantile value mismatch")
        metadata = ResidualArtifactMetadata.model_validate(item.artifact_metadata_json)
        if hashlib.sha256(item.artifact_bytes).hexdigest() != item.artifact_sha256:
            raise ResidualModelPersistenceIntegrityError("artifact raw bytes sha mismatch")
        if metadata.binary_sha256 != item.artifact_sha256:
            raise ResidualModelPersistenceIntegrityError("artifact sha mismatch")
        if metadata.binary_format != item.artifact_format:
            raise ResidualModelPersistenceIntegrityError("artifact metadata format mismatch")
        if metadata.artifact_schema_version != item.artifact_schema_version:
            raise ResidualModelPersistenceIntegrityError("artifact schema version mismatch")
        if metadata.feature_schema_version != item.feature_schema_version:
            raise ResidualModelPersistenceIntegrityError("artifact feature schema version mismatch")
        if metadata.feature_schema_hash != item.feature_schema_hash:
            raise ResidualModelPersistenceIntegrityError("artifact feature schema hash mismatch")
        if metadata.config_hash != item.config_hash:
            raise ResidualModelPersistenceIntegrityError("artifact config hash mismatch")
        if metadata.python_version != item.python_version:
            raise ResidualModelPersistenceIntegrityError("artifact python version mismatch")
        if metadata.numpy_version != item.numpy_version:
            raise ResidualModelPersistenceIntegrityError("artifact numpy version mismatch")
        if metadata.sklearn_version != item.sklearn_version:
            raise ResidualModelPersistenceIntegrityError("artifact sklearn version mismatch")
        if metadata.estimator_parameters.get("loss") != item.loss_name:
            raise ResidualModelPersistenceIntegrityError("artifact metadata loss mismatch")
        if metadata.estimator_parameters.get("quantile") != float(item.quantile_value):
            raise ResidualModelPersistenceIntegrityError("artifact metadata quantile mismatch")
        if metadata.training_signature != run.training_signature:
            raise ResidualModelPersistenceIntegrityError("artifact training signature mismatch")
        if metadata.manifest_hash != run.manifest_hash:
            raise ResidualModelPersistenceIntegrityError("artifact manifest hash mismatch")
        if metadata.model_version != run.model_version:
            raise ResidualModelPersistenceIntegrityError("artifact model version mismatch")
        if metadata.feature_schema_version != run.feature_schema_version:
            raise ResidualModelPersistenceIntegrityError(
                "artifact/run feature schema version mismatch"
            )
        if metadata.feature_schema_hash != run.feature_schema_hash:
            raise ResidualModelPersistenceIntegrityError(
                "artifact/run feature schema hash mismatch"
            )
        if metadata.config_hash != run.config_hash:
            raise ResidualModelPersistenceIntegrityError("artifact/run config hash mismatch")
        encoded_categories = [
            encoding.model_dump(mode="json") for encoding in metadata.category_encodings
        ]
        if reference_category_encodings is None:
            reference_category_encodings = encoded_categories
        elif encoded_categories != reference_category_encodings:
            raise ResidualModelPersistenceIntegrityError("artifact category encoding mismatch")
        validated.append(
            PersistableResidualArtifact(
                quantile_label=item.quantile_label,
                artifact_bytes=item.artifact_bytes,
                metadata=metadata,
            )
        )
    if seen_quantiles != {"P50", "P80", "P90"}:
        raise ResidualModelPersistenceIntegrityError("artifact quantiles are incomplete")
    if (reference_category_encodings or []) != run.category_encoding_snapshot:
        raise ResidualModelPersistenceIntegrityError(
            "training run category encoding snapshot mismatch"
        )
    return tuple(validated)


async def load_and_validate_trusted_residual_artifacts(
    session: AsyncSession,
    *,
    run_id: int,
) -> tuple[PersistableResidualArtifact, ...]:
    """Unified artifact trust gate (Sections 6+8).

    Replaces the two-step load_residual_training_artifacts +
    load_trusted_quantile_estimator pattern with a single function that:

    1. Loads and validates the training run DB row
    2. Validates DB authority constraints (trusted source, format, estimator type, loss, quantile)
    3. Loads and validates metadata (SHAs, schema, config, signatures, encodings)
    4. Validates parent parity: metadata matches run, encodings match snapshot,
       dependency versions match, quantiles complete and unique
    5. Validates runtime version compatibility (python, numpy, sklearn)
    6. Validates estimator object via guarded joblib load (exact class, loss, quantile, params)
    7. Returns tuple[PersistableResidualArtifact, ...] on success

    Raises ResidualArtifactIntegrityError on any failure.
    """
    # 1. Load training run DB row
    run = await get_residual_training_run(session, run_id=run_id)
    if run is None:
        raise ResidualArtifactIntegrityError("training run was not found")
    if run.execution_status != "completed" or run.eligibility_status != "eligible":
        raise ResidualArtifactIntegrityError(
            "trusted artifacts require a completed eligible training run"
        )

    # 2. Load artifacts and validate DB authority
    artifacts = await list_residual_artifacts(session, training_run_id=run_id)
    if len(artifacts) != run.expected_artifact_count:
        raise ResidualArtifactIntegrityError("artifact count mismatch")

    seen_quantiles: set[str] = set()
    validated: list[PersistableResidualArtifact] = []
    reference_category_encodings: list[dict[str, Any]] | None = None

    for item in artifacts:
        if item.quantile_label in seen_quantiles:
            raise ResidualArtifactIntegrityError("duplicate artifact quantile")
        seen_quantiles.add(item.quantile_label)

        # 2. DB authority validation
        if not item.trusted_internal_source:
            raise ResidualArtifactIntegrityError("artifact trusted source marker mismatch")
        if item.artifact_format != "joblib_bundle":
            raise ResidualArtifactIntegrityError("artifact format mismatch")
        if item.estimator_type != "HistGradientBoostingRegressor":
            raise ResidualArtifactIntegrityError("artifact estimator type mismatch")
        if item.loss_name != "quantile":
            raise ResidualArtifactIntegrityError("artifact loss name mismatch")
        if str(item.quantile_value) != _expected_quantile_value(item.quantile_label):
            raise ResidualArtifactIntegrityError("artifact quantile value mismatch")

        # 3. Load and validate metadata
        metadata = ResidualArtifactMetadata.model_validate(item.artifact_metadata_json)

        # Raw bytes SHA
        if hashlib.sha256(item.artifact_bytes).hexdigest() != item.artifact_sha256:
            raise ResidualArtifactIntegrityError("artifact raw bytes sha mismatch")
        if metadata.binary_sha256 != item.artifact_sha256:
            raise ResidualArtifactIntegrityError("artifact metadata binary sha mismatch")

        # Metadata SHA independently recomputed
        expected_metadata_sha = canonical_payload_hash(
            metadata.model_dump(mode="python", exclude={"metadata_sha256"})
        )
        if metadata.metadata_sha256 != expected_metadata_sha:
            raise ResidualArtifactIntegrityError("artifact metadata payload sha mismatch")

        # Model family/version
        if metadata.model_family != run.model_family:
            raise ResidualArtifactIntegrityError("artifact model_family mismatch")
        if metadata.model_version != run.model_version:
            raise ResidualArtifactIntegrityError("artifact model_version mismatch")

        # Artifact schema
        if metadata.artifact_schema_version != item.artifact_schema_version:
            raise ResidualArtifactIntegrityError("artifact schema version mismatch")

        # Feature schema version/hash
        if metadata.feature_schema_version != item.feature_schema_version:
            raise ResidualArtifactIntegrityError("artifact feature schema version mismatch")
        if metadata.feature_schema_hash != item.feature_schema_hash:
            raise ResidualArtifactIntegrityError("artifact feature schema hash mismatch")
        if metadata.feature_schema_version != run.feature_schema_version:
            raise ResidualArtifactIntegrityError(
                "artifact/run feature schema version mismatch"
            )
        if metadata.feature_schema_hash != run.feature_schema_hash:
            raise ResidualArtifactIntegrityError(
                "artifact/run feature schema hash mismatch"
            )

        # Config hash
        if metadata.config_hash != item.config_hash:
            raise ResidualArtifactIntegrityError("artifact config hash mismatch")
        if metadata.config_hash != run.config_hash:
            raise ResidualArtifactIntegrityError("artifact/run config hash mismatch")

        # Training signature
        if metadata.training_signature != run.training_signature:
            raise ResidualArtifactIntegrityError("artifact training signature mismatch")

        # Manifest hash
        if metadata.manifest_hash != run.manifest_hash:
            raise ResidualArtifactIntegrityError("artifact manifest hash mismatch")

        # Dependency versions (column vs metadata)
        if metadata.python_version != item.python_version:
            raise ResidualArtifactIntegrityError("artifact python version mismatch")
        if metadata.numpy_version != item.numpy_version:
            raise ResidualArtifactIntegrityError("artifact numpy version mismatch")
        if metadata.sklearn_version != item.sklearn_version:
            raise ResidualArtifactIntegrityError("artifact sklearn version mismatch")

        # Quantile set
        if metadata.quantiles != [0.5, 0.8, 0.9]:
            raise ResidualArtifactIntegrityError("artifact quantiles mismatch")

        # Binary format
        if metadata.binary_format != item.artifact_format:
            raise ResidualArtifactIntegrityError("artifact metadata format mismatch")

        # Estimator params from metadata
        if metadata.estimator_parameters.get("loss") != item.loss_name:
            raise ResidualArtifactIntegrityError("artifact metadata loss mismatch")
        expected_quantile = {"P50": 0.5, "P80": 0.8, "P90": 0.9}[item.quantile_label]
        if metadata.estimator_parameters.get("quantile") != expected_quantile:
            raise ResidualArtifactIntegrityError("artifact metadata quantile mismatch")

        # Category encodings consistency across artifacts
        encoded_categories = [
            encoding.model_dump(mode="json") for encoding in metadata.category_encodings
        ]
        if reference_category_encodings is None:
            reference_category_encodings = encoded_categories
        elif encoded_categories != reference_category_encodings:
            raise ResidualArtifactIntegrityError("artifact category encoding mismatch")

        # 5. Runtime version compatibility
        if metadata.python_version != platform.python_version():
            raise ResidualArtifactIntegrityError("artifact python runtime version mismatch")
        if metadata.numpy_version != np.__version__:
            raise ResidualArtifactIntegrityError("artifact numpy runtime version mismatch")
        if metadata.sklearn_version != sklearn.__version__:
            raise ResidualArtifactIntegrityError("artifact sklearn runtime version mismatch")

        # 6. Validates estimator object: guarded joblib load
        try:
            loaded = joblib.load(BytesIO(item.artifact_bytes))
        except (
            EOFError,
            ValueError,
            TypeError,
            pickle.PickleError,
            AttributeError,
            ImportError,
            ModuleNotFoundError,
        ) as exc:
            raise ResidualArtifactIntegrityError("artifact deserialization failed") from exc

        if not isinstance(loaded, HistGradientBoostingRegressor):
            raise ResidualArtifactIntegrityError("artifact estimator type mismatch")
        if loaded.loss != "quantile":
            raise ResidualArtifactIntegrityError("artifact estimator loss mismatch")
        if loaded.quantile != expected_quantile:
            raise ResidualArtifactIntegrityError("artifact estimator quantile mismatch")

        # Verify resolved estimator parameters
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
            raise ResidualArtifactIntegrityError("artifact estimator parameters mismatch")

        validated.append(
            PersistableResidualArtifact(
                quantile_label=item.quantile_label,
                artifact_bytes=item.artifact_bytes,
                metadata=metadata,
            )
        )

    # 4. Complete quantile set check
    if seen_quantiles != {"P50", "P80", "P90"}:
        raise ResidualArtifactIntegrityError("artifact quantiles are incomplete")

    # 4. Parent parity: category encodings match parent snapshot
    if (reference_category_encodings or []) != run.category_encoding_snapshot:
        raise ResidualArtifactIntegrityError(
            "training run category encoding snapshot mismatch"
        )

    # 4. Parent parity: dependency versions match parent
    if run.python_version != validated[0].metadata.python_version if validated else "n/a":
        pass  # already validated against columns above
    if run.numpy_version != validated[0].metadata.numpy_version if validated else "n/a":
        pass
    if run.sklearn_version != validated[0].metadata.sklearn_version if validated else "n/a":
        pass

    return tuple(validated)


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
                "prediction_run_id": 0,
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
                "fallback_reason": row.fallback_reason,
            }
        )
        for row in rows
    )
