from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import cast

from backend.app.residual_model.canonical import canonical_payload_hash
from backend.app.residual_model.config import ResidualModelConfig
from backend.app.residual_model.dataset import (
    build_prediction_matrix,
    build_training_matrix,
    summarize_manifest,
    training_signature,
)
from backend.app.residual_model.manifest import manifest_hash
from backend.app.residual_model.metrics import (
    empirical_coverage,
    pinball_loss,
    quantile_crossing_count,
    residual_mae,
)
from backend.app.residual_model.model import (
    TrainedResidualEstimators,
    predict_quantiles,
    serialize_quantile_artifacts,
    train_quantile_estimators,
)
from backend.app.residual_model.projection import project_corrected_quantiles
from backend.app.residual_model.schemas import (
    CategoryEncoding,
    FeatureValue,
    FeatureVisibilityAudit,
    ResidualPredictionExecutionResult,
    ResidualPredictionRow,
    ResidualTrainingExecutionResult,
    ResidualTrainingManifestRow,
)


def _aggregate_feature_audit(rows: list[ResidualTrainingManifestRow]) -> dict[str, object]:
    status_counts: Counter[str] = Counter()
    blockers: Counter[str] = Counter()
    for row in rows:
        if row.feature_visibility_audit is not None:
            status_counts[f"audit_status::{row.feature_visibility_audit.status.value}"] += 1
            for issue in row.feature_visibility_audit.blockers:
                blockers[issue.code.value] += 1
        for feature in row.feature_values:
            status_counts["feature_values"] += 1
            if feature.value is None:
                status_counts["missing_values"] += 1
    return {
        "row_count": len(rows),
        "feature_value_count": status_counts["feature_values"],
        "missing_value_count": status_counts["missing_values"],
        "blocker_counts": dict(sorted(blockers.items())),
    }


def train_residual_model_from_manifest(
    *,
    rows: list[ResidualTrainingManifestRow],
    config: ResidualModelConfig,
) -> ResidualTrainingExecutionResult:
    summary = summarize_manifest(rows)
    manifest_digest = manifest_hash(rows)
    signature = training_signature(
        config_hash=config.config_hash,
        manifest_hash=manifest_digest,
        rows=rows,
    )
    blockers: list[str] = []
    eligibility_reasons: list[str] = []
    sample_count = int(summary["included_row_count"])
    distinct_season_count = int(summary["distinct_season_count"])
    distinct_factory_count = int(summary["distinct_factory_count"])
    if sample_count < config.rules.eligibility.min_training_rows:
        eligibility_reasons.append("insufficient_training_rows")
    if distinct_season_count < config.rules.eligibility.min_seasons:
        eligibility_reasons.append("insufficient_training_seasons")
    if distinct_factory_count < config.rules.eligibility.min_factories:
        eligibility_reasons.append("insufficient_training_factories")
    if sample_count == 0:
        blockers.append("no_included_training_rows")
    for row in rows:
        if not row.include:
            continue
        if (
            row.feature_visibility_audit is not None
            and row.feature_visibility_audit.status == "blocked"
        ):
            blockers.append("feature_visibility_audit_blocked")
            break

    input_snapshot = {
        "manifest_summary": summary,
        "manifest_hash": manifest_digest,
        "training_signature": signature,
        "config_snapshot": config.snapshot,
    }
    if blockers:
        return ResidualTrainingExecutionResult(
            execution_status="blocked",
            eligibility_status="not_evaluated",
            model_family=config.rules.model_family,
            model_version=config.rules.model_version,
            feature_schema_version=config.rules.feature_schema_version,
            artifact_schema_version=config.rules.artifact_schema_version,
            training_signature=signature,
            config_hash=config.config_hash,
            manifest_hash=manifest_digest,
            sample_count=sample_count,
            distinct_season_count=distinct_season_count,
            distinct_factory_count=distinct_factory_count,
            warnings=(),
            blockers=tuple(blockers),
            feature_audit_summary=_aggregate_feature_audit(rows),
            metrics={},
            eligibility_reasons=tuple(eligibility_reasons),
            input_snapshot=input_snapshot,
            artifacts=(),
        )
    if eligibility_reasons:
        return ResidualTrainingExecutionResult(
            execution_status="completed",
            eligibility_status="ineligible",
            model_family=config.rules.model_family,
            model_version=config.rules.model_version,
            feature_schema_version=config.rules.feature_schema_version,
            artifact_schema_version=config.rules.artifact_schema_version,
            training_signature=signature,
            config_hash=config.config_hash,
            manifest_hash=manifest_digest,
            sample_count=sample_count,
            distinct_season_count=distinct_season_count,
            distinct_factory_count=distinct_factory_count,
            warnings=(),
            blockers=(),
            feature_audit_summary=_aggregate_feature_audit(rows),
            metrics={},
            eligibility_reasons=tuple(eligibility_reasons),
            input_snapshot=input_snapshot,
            artifacts=(),
        )

    features, labels, weights, feature_names, category_encodings = build_training_matrix(
        rows,
        config=config,
    )
    estimators = train_quantile_estimators(
        config=config,
        features=features,
        labels=labels,
        sample_weight=weights,
    )
    predicted_p50, predicted_p80, predicted_p90 = predict_quantiles(
        estimators=estimators,
        features=features,
    )
    actuals = [Decimal(str(item)) for item in labels.tolist()]
    pred50 = [Decimal(str(item)) for item in predicted_p50.tolist()]
    pred80 = [Decimal(str(item)) for item in predicted_p80.tolist()]
    pred90 = [Decimal(str(item)) for item in predicted_p90.tolist()]
    metrics = {
        "residual_mae": residual_mae(actuals, pred50),
        "structural_daily_wmape": None,
        "corrected_daily_wmape": None,
        "pinball_loss_p50": pinball_loss(actuals, pred50, quantile=Decimal("0.5")),
        "pinball_loss_p80": pinball_loss(actuals, pred80, quantile=Decimal("0.8")),
        "pinball_loss_p90": pinball_loss(actuals, pred90, quantile=Decimal("0.9")),
        "empirical_coverage_p80": empirical_coverage(actuals=actuals, lower=pred50, upper=pred80),
        "empirical_coverage_p90": empirical_coverage(actuals=actuals, lower=pred50, upper=pred90),
        "quantile_crossing_count_raw": quantile_crossing_count(p50=pred50, p80=pred80, p90=pred90),
        "fallback_rate": Decimal("0"),
        "feature_names": feature_names,
    }
    artifacts = serialize_quantile_artifacts(
        estimators=estimators,
        config=config,
        training_signature=signature,
        manifest_hash=manifest_digest,
        category_encodings=category_encodings,
    )
    return ResidualTrainingExecutionResult(
        execution_status="completed",
        eligibility_status="eligible",
        model_family=config.rules.model_family,
        model_version=config.rules.model_version,
        feature_schema_version=config.rules.feature_schema_version,
        artifact_schema_version=config.rules.artifact_schema_version,
        training_signature=signature,
        config_hash=config.config_hash,
        manifest_hash=manifest_digest,
        sample_count=sample_count,
        distinct_season_count=distinct_season_count,
        distinct_factory_count=distinct_factory_count,
        warnings=(),
        blockers=(),
        feature_audit_summary=_aggregate_feature_audit(rows),
        metrics=cast(dict[str, object], metrics),
        eligibility_reasons=tuple(eligibility_reasons),
        input_snapshot=input_snapshot,
        artifacts=artifacts,
    )


def structural_only_prediction(
    *,
    model_run_id: int | None,
    task9_run_id: int,
    task9_result_hash: str,
    config_hash: str,
    structural_rows: list[dict[str, object]],
    fallback_reason: str,
) -> ResidualPredictionExecutionResult:
    rows: list[ResidualPredictionRow] = []
    for index, item in enumerate(structural_rows, start=1):
        prediction_hash = f"{index:064x}"
        structural_p50 = Decimal(str(item["structural_p50_kg"]))
        structural_p80 = Decimal(str(item["structural_p80_kg"]))
        structural_p90 = Decimal(str(item["structural_p90_kg"]))
        row_payload = {
            "model_run_id": model_run_id or 0,
            "prediction_run_id": 0,
            "task9_run_id": task9_run_id,
            "task9_result_hash": task9_result_hash,
            "destination_factory_id": item["destination_factory_id"],
            "arrival_local_date": item["arrival_local_date"],
            "forecast_horizon_days": item["forecast_horizon_days"],
            "structural_p50_kg": structural_p50,
            "structural_p80_kg": structural_p80,
            "structural_p90_kg": structural_p90,
            "raw_residual_p50_kg": Decimal("0"),
            "raw_residual_p80_kg": Decimal("0"),
            "raw_residual_p90_kg": Decimal("0"),
            "corrected_raw_p50_kg": structural_p50,
            "corrected_raw_p80_kg": structural_p80,
            "corrected_raw_p90_kg": structural_p90,
            "corrected_p50_kg": structural_p50,
            "corrected_p80_kg": structural_p80,
            "corrected_p90_kg": structural_p90,
            "nonnegative_projection_applied": False,
            "quantile_projection_applied": False,
            "projection_reasons": [],
            "feature_vector_hash": "0" * 64,
            "feature_audit_hash": "0" * 64,
            "prediction_hash": prediction_hash,
            "mode": "structural_only",
        }
        rows.append(ResidualPredictionRow.model_validate(row_payload))
    snapshot = {
        "task9_run_id": task9_run_id,
        "task9_result_hash": task9_result_hash,
        "structural_row_count": len(structural_rows),
    }
    prediction_hash = "0" * 64 if not rows else rows[0].prediction_hash
    return ResidualPredictionExecutionResult(
        execution_status="completed",
        mode="structural_only",
        model_run_id=model_run_id,
        task9_run_id=task9_run_id,
        task9_result_hash=task9_result_hash,
        config_hash=config_hash,
        prediction_hash=prediction_hash,
        warnings=(),
        blockers=(),
        fallback_reason=fallback_reason,
        rows=tuple(rows),
        input_snapshot=snapshot,
    )


def predict_residual_correction(
    *,
    model_run_id: int,
    task9_run_id: int,
    task9_result_hash: str,
    config: ResidualModelConfig,
    feature_names: list[str],
    category_encodings: list[CategoryEncoding],
    structural_rows: list[dict[str, object]],
    feature_rows: list[tuple[FeatureValue, ...]],
    feature_audits: list[FeatureVisibilityAudit],
    estimators: TrainedResidualEstimators,
    fallback_reason: str | None = None,
) -> ResidualPredictionExecutionResult:
    matrix = build_prediction_matrix(
        feature_rows=feature_rows,
        feature_names=feature_names,
        category_encodings=category_encodings,
    )
    predicted_p50, predicted_p80, predicted_p90 = predict_quantiles(
        estimators=estimators,
        features=matrix,
    )
    rows: list[ResidualPredictionRow] = []
    for index, (structural_row, features, audit) in enumerate(
        zip(structural_rows, feature_rows, feature_audits, strict=True),
        start=1,
    ):
        structural_p50 = Decimal(str(structural_row["structural_p50_kg"]))
        structural_p80 = Decimal(str(structural_row["structural_p80_kg"]))
        structural_p90 = Decimal(str(structural_row["structural_p90_kg"]))
        projection = project_corrected_quantiles(
            structural_arrival_p50_kg=structural_p50,
            predicted_residual_p50_kg=Decimal(str(predicted_p50[index - 1])),
            predicted_residual_p80_kg=Decimal(str(predicted_p80[index - 1])),
            predicted_residual_p90_kg=Decimal(str(predicted_p90[index - 1])),
        )
        feature_vector_hash = canonical_payload_hash(
            [item.model_dump(mode="json") for item in features]
        )
        row_payload = {
            "model_run_id": model_run_id,
            "prediction_run_id": 0,
            "task9_run_id": task9_run_id,
            "task9_result_hash": task9_result_hash,
            "destination_factory_id": structural_row["destination_factory_id"],
            "arrival_local_date": structural_row["arrival_local_date"],
            "forecast_horizon_days": structural_row["forecast_horizon_days"],
            "structural_p50_kg": structural_p50,
            "structural_p80_kg": structural_p80,
            "structural_p90_kg": structural_p90,
            "raw_residual_p50_kg": projection.raw_p50_kg - structural_p50,
            "raw_residual_p80_kg": projection.raw_p80_kg - structural_p50,
            "raw_residual_p90_kg": projection.raw_p90_kg - structural_p50,
            "corrected_raw_p50_kg": projection.raw_p50_kg,
            "corrected_raw_p80_kg": projection.raw_p80_kg,
            "corrected_raw_p90_kg": projection.raw_p90_kg,
            "corrected_p50_kg": projection.corrected_p50_kg,
            "corrected_p80_kg": projection.corrected_p80_kg,
            "corrected_p90_kg": projection.corrected_p90_kg,
            "nonnegative_projection_applied": projection.nonnegative_projection_applied,
            "quantile_projection_applied": projection.quantile_projection_applied,
            "projection_reasons": [item.value for item in projection.projection_reasons],
            "feature_vector_hash": feature_vector_hash,
            "feature_audit_hash": audit.audit_hash,
            "mode": "residual_corrected",
        }
        row_hash = canonical_payload_hash(row_payload)
        row_payload["prediction_hash"] = row_hash
        rows.append(ResidualPredictionRow.model_validate(row_payload))

    snapshot = {
        "task9_run_id": task9_run_id,
        "task9_result_hash": task9_result_hash,
        "model_run_id": model_run_id,
        "feature_names": feature_names,
        "fallback_reason": fallback_reason,
    }
    result_payload = {
        "execution_status": "completed",
        "mode": "residual_corrected",
        "model_run_id": model_run_id,
        "task9_run_id": task9_run_id,
        "task9_result_hash": task9_result_hash,
        "config_hash": config.config_hash,
        "warnings": [],
        "blockers": [],
        "fallback_reason": fallback_reason,
        "rows": [row.model_dump(mode="json") for row in rows],
        "input_snapshot": snapshot,
    }
    prediction_hash = canonical_payload_hash(result_payload)
    return ResidualPredictionExecutionResult(
        execution_status="completed",
        mode="residual_corrected",
        model_run_id=model_run_id,
        task9_run_id=task9_run_id,
        task9_result_hash=task9_result_hash,
        config_hash=config.config_hash,
        prediction_hash=prediction_hash,
        warnings=(),
        blockers=(),
        fallback_reason=fallback_reason,
        rows=tuple(rows),
        input_snapshot=snapshot,
    )
