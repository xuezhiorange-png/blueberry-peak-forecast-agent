from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from backend.app.residual_model.canonical import (
    canonical_json_value,
    canonical_payload_hash,
    prediction_input_signature_hash,
)
from backend.app.residual_model.config import ResidualModelConfig
from backend.app.residual_model.dataset import (
    build_prediction_matrix,
    build_training_matrix,
    summarize_manifest,
    training_signature,
)
from backend.app.residual_model.feature_registry import feature_definition_map
from backend.app.residual_model.manifest import manifest_hash
from backend.app.residual_model.metrics import (
    empirical_coverage,
    pinball_loss,
    quantile_crossing_count,
    residual_mae,
    wmape,
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
    ProjectionResult,
    ResidualPredictionExecutionResult,
    ResidualPredictionRow,
    ResidualTrainingExecutionResult,
    ResidualTrainingManifestRow,
)


@dataclass(frozen=True)
class ResidualRowDecision:
    fallback_reason: str | None
    feature_vector_hash: str
    feature_audit_hash: str
    mode: str


def _split_rows(
    rows: list[ResidualTrainingManifestRow],
    split: str,
) -> list[ResidualTrainingManifestRow]:
    return [row for row in rows if row.include and row.split.value == split]


def _observed_receipts(rows: list[ResidualTrainingManifestRow]) -> list[Decimal]:
    return [row.observed_effective_receipt_kg for row in rows]


def _structural_p50(rows: list[ResidualTrainingManifestRow]) -> list[Decimal]:
    return [row.structural_p50_kg for row in rows]


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _feature_schema_hash(feature_names: list[str]) -> str:
    return canonical_payload_hash(sorted(feature_names))


def _projection_payloads(
    *,
    rows: Sequence[ResidualTrainingManifestRow],
    residual_p50: Sequence[Decimal],
    residual_p80: Sequence[Decimal],
    residual_p90: Sequence[Decimal],
) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for row, p50, p80, p90 in zip(rows, residual_p50, residual_p80, residual_p90, strict=True):
        projection = project_corrected_quantiles(
            structural_arrival_p50_kg=row.structural_p50_kg,
            predicted_residual_p50_kg=p50,
            predicted_residual_p80_kg=p80,
            predicted_residual_p90_kg=p90,
        )
        payloads.append(
            {
                "row": row,
                "projection": projection,
                "residual_p50": p50,
                "residual_p80": p80,
                "residual_p90": p90,
            }
        )
    return payloads


def _row_decision(
    *,
    feature_values: Sequence[FeatureValue],
    audit: FeatureVisibilityAudit | None,
    category_encodings: Sequence[CategoryEncoding],
    config: ResidualModelConfig,
) -> ResidualRowDecision:
    definitions = feature_definition_map()
    encoding_map = {item.feature_name: item for item in category_encodings}
    feature_map = {item.feature_name: item.value for item in feature_values}
    fallback_reason: str | None = None
    if audit is not None and audit.status.value == "blocked":
        fallback_reason = "feature_visibility_failed"
    else:
        for feature_name, definition in definitions.items():
            value = feature_map.get(feature_name)
            if value is None and definition.missing_policy.value == "block":
                fallback_reason = "required_feature_missing"
                break
            encoding = encoding_map.get(feature_name)
            if (
                encoding is not None
                and isinstance(value, str)
                and value not in encoding.ordered_known_categories
                and config.rules.categorical_unknown_policy == "structural_only_fallback"
            ):
                fallback_reason = "unknown_category"
                break
    return ResidualRowDecision(
        fallback_reason=fallback_reason,
        feature_vector_hash=canonical_payload_hash(
            [item.model_dump(mode="json") for item in feature_values]
        ),
        feature_audit_hash=(audit.audit_hash if audit is not None else canonical_payload_hash([])),
        mode="structural_only" if fallback_reason is not None else "residual_corrected",
    )


def _predict_residual_vectors(
    *,
    feature_rows: Sequence[tuple[FeatureValue, ...]],
    feature_audits: Sequence[FeatureVisibilityAudit | None],
    feature_names: list[str],
    category_encodings: Sequence[CategoryEncoding],
    config: ResidualModelConfig,
    estimators: TrainedResidualEstimators,
) -> tuple[list[Decimal], list[Decimal], list[Decimal], list[ResidualRowDecision]]:
    decisions = [
        _row_decision(
            feature_values=feature_values,
            audit=audit,
            category_encodings=category_encodings,
            config=config,
        )
        for feature_values, audit in zip(feature_rows, feature_audits, strict=True)
    ]
    estimated_indices = [
        index for index, decision in enumerate(decisions) if decision.fallback_reason is None
    ]
    residual_p50 = [Decimal("0")] * len(feature_rows)
    residual_p80 = [Decimal("0")] * len(feature_rows)
    residual_p90 = [Decimal("0")] * len(feature_rows)
    if estimated_indices:
        matrix = build_prediction_matrix(
            feature_rows=[feature_rows[index] for index in estimated_indices],
            feature_names=feature_names,
            category_encodings=list(category_encodings),
        )
        predicted_p50, predicted_p80, predicted_p90 = predict_quantiles(
            estimators=estimators,
            features=matrix,
        )
        for output_index, row_index in enumerate(estimated_indices):
            residual_p50[row_index] = Decimal(str(predicted_p50[output_index]))
            residual_p80[row_index] = Decimal(str(predicted_p80[output_index]))
            residual_p90[row_index] = Decimal(str(predicted_p90[output_index]))
    return residual_p50, residual_p80, residual_p90, decisions


def _metrics_from_projection_payloads(
    payloads: Sequence[dict[str, object]],
) -> dict[str, object]:
    rows = [cast(ResidualTrainingManifestRow, item["row"]) for item in payloads]
    if not rows:
        return {
            "row_count": 0,
            "residual_mae": None,
            "structural_daily_wmape": None,
            "corrected_daily_wmape": None,
            "pinball_loss_p50": None,
            "pinball_loss_p80": None,
            "pinball_loss_p90": None,
            "empirical_coverage_p80": None,
            "empirical_coverage_p90": None,
            "quantile_crossing_count_raw": 0,
            "quantile_crossing_count_projected": 0,
            "correction_magnitude_mean_kg": None,
            "fallback_row_count": 0,
            "evaluated_row_count": 0,
            "fallback_rate": Decimal("0"),
        }
    actual_receipts = [row.observed_effective_receipt_kg for row in rows]
    residual_labels = [row.residual_label_kg for row in rows]
    structural_p50 = [row.structural_p50_kg for row in rows]
    residual_p50 = [cast(Decimal, item["residual_p50"]) for item in payloads]
    projections = [cast(ProjectionResult, item["projection"]) for item in payloads]
    corrected_p50 = [item.corrected_p50_kg for item in projections]
    corrected_p80 = [item.corrected_p80_kg for item in projections]
    corrected_p90 = [item.corrected_p90_kg for item in projections]
    raw_p50 = [item.raw_p50_kg for item in projections]
    raw_p80 = [item.raw_p80_kg for item in projections]
    raw_p90 = [item.raw_p90_kg for item in projections]
    return {
        "row_count": len(rows),
        "residual_mae": residual_mae(residual_labels, residual_p50),
        "structural_daily_wmape": wmape(actual_receipts, structural_p50),
        "corrected_daily_wmape": wmape(actual_receipts, corrected_p50),
        "pinball_loss_p50": pinball_loss(actual_receipts, corrected_p50, quantile=Decimal("0.5")),
        "pinball_loss_p80": pinball_loss(actual_receipts, corrected_p80, quantile=Decimal("0.8")),
        "pinball_loss_p90": pinball_loss(actual_receipts, corrected_p90, quantile=Decimal("0.9")),
        "empirical_coverage_p80": empirical_coverage(
            actuals=actual_receipts,
            lower=corrected_p50,
            upper=corrected_p80,
        ),
        "empirical_coverage_p90": empirical_coverage(
            actuals=actual_receipts,
            lower=corrected_p50,
            upper=corrected_p90,
        ),
        "quantile_crossing_count_raw": quantile_crossing_count(
            p50=raw_p50,
            p80=raw_p80,
            p90=raw_p90,
        ),
        "quantile_crossing_count_projected": quantile_crossing_count(
            p50=corrected_p50,
            p80=corrected_p80,
            p90=corrected_p90,
        ),
        "correction_magnitude_mean_kg": residual_mae(
            [Decimal("0")] * len(residual_p50),
            [abs(item) for item in residual_p50],
        ),
        "fallback_row_count": 0,
        "evaluated_row_count": len(rows),
        "fallback_rate": Decimal("0"),
    }


def _split_metrics(
    *,
    rows: Sequence[ResidualTrainingManifestRow],
    residual_p50: Sequence[Decimal],
    residual_p80: Sequence[Decimal],
    residual_p90: Sequence[Decimal],
    fallback_row_count: int = 0,
) -> dict[str, object]:
    payloads = _projection_payloads(
        rows=rows,
        residual_p50=residual_p50,
        residual_p80=residual_p80,
        residual_p90=residual_p90,
    )
    grouped_by_season: dict[str, list[dict[str, object]]] = {}
    grouped_by_factory: dict[str, list[dict[str, object]]] = {}
    for payload in payloads:
        row = cast(ResidualTrainingManifestRow, payload["row"])
        grouped_by_season.setdefault(str(row.season_id), []).append(payload)
        grouped_by_factory.setdefault(str(row.destination_factory_id), []).append(payload)
    global_metrics = _metrics_from_projection_payloads(payloads)
    evaluated_row_count = cast(int, global_metrics["evaluated_row_count"])
    global_metrics["fallback_row_count"] = fallback_row_count
    global_metrics["fallback_rate"] = (
        Decimal(fallback_row_count) / Decimal(evaluated_row_count)
        if evaluated_row_count > 0
        else Decimal("0")
    )
    return {
        "global": global_metrics,
        "per_season": {
            key: _metrics_from_projection_payloads(grouped_by_season[key])
            for key in sorted(grouped_by_season)
        },
        "per_factory": {
            key: _metrics_from_projection_payloads(grouped_by_factory[key])
            for key in sorted(grouped_by_factory)
        },
    }


def _prediction_row_sort_key(row_payload: dict[str, object]) -> tuple[object, ...]:
    return (
        row_payload["destination_factory_id"],
        row_payload["arrival_local_date"],
    )


def finalize_prediction_result(
    *,
    execution_status: str,
    mode: str,
    model_run_id: int | None,
    task9_run_id: int,
    task9_result_hash: str,
    config_hash: str,
    warnings: Sequence[str],
    blockers: Sequence[str],
    fallback_reason: str | None,
    row_payloads: Sequence[dict[str, object]],
    input_snapshot: dict[str, object],
) -> ResidualPredictionExecutionResult:
    rows: list[ResidualPredictionRow] = []
    for payload in sorted(row_payloads, key=_prediction_row_sort_key):
        row_hash = canonical_payload_hash(payload)
        rows.append(ResidualPredictionRow.model_validate({**payload, "prediction_hash": row_hash}))
    normalized_input_snapshot = cast(dict[str, object], canonical_json_value(input_snapshot))
    prediction_input_signature = prediction_input_signature_hash(
        model_run_id=model_run_id,
        training_signature=cast(str, normalized_input_snapshot["training_signature"]),
        task9_run_id=task9_run_id,
        task9_result_hash=task9_result_hash,
        feature_analytics_build_run_id=cast(
            int | None,
            normalized_input_snapshot.get("feature_analytics_build_run_id"),
        ),
        feature_actual_snapshot=cast(
            dict[str, object] | None,
            normalized_input_snapshot.get("feature_actual_snapshot"),
        ),
        supplemental_feature_values=cast(
            list[object],
            normalized_input_snapshot.get("supplemental_feature_values", []),
        ),
        feature_audit_hashes=cast(
            list[str],
            normalized_input_snapshot.get("feature_audit_hashes", []),
        ),
        feature_rows=cast(
            list[object],
            normalized_input_snapshot.get("feature_rows", []),
        ),
        artifact_hashes=cast(
            list[str],
            normalized_input_snapshot.get("artifact_hashes", []),
        ),
        config_hash=config_hash,
        feature_schema_version=cast(
            str,
            normalized_input_snapshot["feature_schema_version"],
        ),
        feature_schema_hash=cast(
            str,
            normalized_input_snapshot["feature_schema_hash"],
        ),
        projection_version=cast(str, normalized_input_snapshot["projection_version"]),
        fallback_policy_version=cast(
            str,
            normalized_input_snapshot["fallback_policy"],
        ),
    )
    result_payload = {
        "execution_status": execution_status,
        "mode": mode,
        "model_run_id": model_run_id,
        "task9_run_id": task9_run_id,
        "task9_result_hash": task9_result_hash,
        "config_hash": config_hash,
        "prediction_input_signature": prediction_input_signature,
        "prediction_hash": None,
        "warnings": sorted(set(warnings)),
        "blockers": sorted(set(blockers)),
        "fallback_reason": fallback_reason,
        "rows": [
            cast(dict[str, object], canonical_json_value(row.model_dump(mode="python")))
            for row in rows
        ],
        "input_snapshot": normalized_input_snapshot,
    }
    prediction_hash = canonical_payload_hash(result_payload)
    return ResidualPredictionExecutionResult(
        execution_status=execution_status,
        mode=mode,
        model_run_id=model_run_id,
        task9_run_id=task9_run_id,
        task9_result_hash=task9_result_hash,
        config_hash=config_hash,
        prediction_input_signature=prediction_input_signature,
        prediction_hash=prediction_hash,
        warnings=tuple(cast(list[str], result_payload["warnings"])),
        blockers=tuple(cast(list[str], result_payload["blockers"])),
        fallback_reason=fallback_reason,
        rows=tuple(rows),
        input_snapshot=normalized_input_snapshot,
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
    train_rows = _split_rows(rows, "train")
    validation_rows = _split_rows(rows, "validation")
    test_rows = _split_rows(rows, "test")
    sample_count = len(train_rows)
    distinct_season_count = len({row.season_id for row in train_rows})
    distinct_factory_count = len({row.destination_factory_id for row in train_rows})
    train_seasons = {row.season_id for row in train_rows}
    validation_seasons = {row.season_id for row in validation_rows}
    test_seasons = {row.season_id for row in test_rows}
    if sample_count < config.rules.eligibility.min_training_rows:
        eligibility_reasons.append("insufficient_training_rows")
    if distinct_season_count < config.rules.eligibility.min_seasons:
        eligibility_reasons.append("insufficient_training_seasons")
    if distinct_factory_count < config.rules.eligibility.min_factories:
        eligibility_reasons.append("insufficient_training_factories")
    if config.rules.split_strategy == "leave_one_season_out":
        if not validation_rows or not validation_seasons:
            eligibility_reasons.append("missing_validation_season")
        if train_seasons.intersection(validation_seasons):
            eligibility_reasons.append("train_validation_season_overlap")
        if train_seasons.intersection(test_seasons):
            eligibility_reasons.append("train_test_season_overlap")
        if validation_rows and not validation_seasons.isdisjoint(test_seasons):
            eligibility_reasons.append("validation_test_season_overlap")
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
    pred50, pred80, pred90, train_decisions = _predict_residual_vectors(
        feature_rows=[row.feature_values for row in train_rows],
        feature_audits=[row.feature_visibility_audit for row in train_rows],
        feature_names=feature_names,
        category_encodings=category_encodings,
        config=config,
        estimators=estimators,
    )
    train_metrics = _split_metrics(
        rows=train_rows,
        residual_p50=pred50,
        residual_p80=pred80,
        residual_p90=pred90,
        fallback_row_count=sum(
            1 for decision in train_decisions if decision.fallback_reason is not None
        ),
    )
    metrics: dict[str, object] = {
        **cast(dict[str, object], train_metrics["global"]),
        "feature_names": feature_names,
        "feature_schema_hash": _feature_schema_hash(feature_names),
        "split_counts": {
            "train": len(train_rows),
            "validation": len(validation_rows),
            "test": len(test_rows),
        },
        "train": train_metrics,
        "validation": {},
        "test": {},
    }
    validation_global_metrics: dict[str, object] = {}
    if validation_rows:
        validation_pred50, validation_pred80, validation_pred90, validation_decisions = (
            _predict_residual_vectors(
                feature_rows=[row.feature_values for row in validation_rows],
                feature_audits=[row.feature_visibility_audit for row in validation_rows],
                feature_names=feature_names,
                category_encodings=category_encodings,
                config=config,
                estimators=estimators,
            )
        )
        validation_metrics = _split_metrics(
            rows=validation_rows,
            residual_p50=validation_pred50,
            residual_p80=validation_pred80,
            residual_p90=validation_pred90,
            fallback_row_count=sum(
                1
                for decision in validation_decisions
                if decision.fallback_reason is not None
            ),
        )
        metrics["validation"] = validation_metrics
        validation_global_metrics = cast(dict[str, object], validation_metrics["global"])
        validation_wmape = validation_global_metrics["corrected_daily_wmape"]
        structural_wmape = validation_global_metrics["structural_daily_wmape"]
        if (
            isinstance(validation_wmape, Decimal)
            and validation_wmape > Decimal(str(config.rules.eligibility.max_validation_wmape))
        ):
            eligibility_reasons.append("validation_wmape_above_threshold")
        if (
            config.rules.eligibility.require_improvement_over_structural
            and isinstance(validation_wmape, Decimal)
            and isinstance(structural_wmape, Decimal)
            and validation_wmape >= structural_wmape
        ):
            eligibility_reasons.append("no_validation_improvement_over_structural")
    if test_rows:
        test_pred50, test_pred80, test_pred90, test_decisions = _predict_residual_vectors(
            feature_rows=[row.feature_values for row in test_rows],
            feature_audits=[row.feature_visibility_audit for row in test_rows],
            feature_names=feature_names,
            category_encodings=category_encodings,
            config=config,
            estimators=estimators,
        )
        metrics["test"] = _split_metrics(
            rows=test_rows,
            residual_p50=test_pred50,
            residual_p80=test_pred80,
            residual_p90=test_pred90,
            fallback_row_count=sum(
                1 for decision in test_decisions if decision.fallback_reason is not None
            ),
        )
    fallback_rate = cast(
        Decimal | None,
        cast(dict[str, object], validation_global_metrics or train_metrics["global"]).get(
            "fallback_rate"
        ),
    ) or Decimal("0")
    if fallback_rate > Decimal(str(config.rules.eligibility.max_fallback_rate)):
        eligibility_reasons.append("fallback_rate_above_threshold")
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
            metrics=metrics,
            eligibility_reasons=tuple(eligibility_reasons),
            input_snapshot=input_snapshot,
            artifacts=(),
        )
    artifacts = serialize_quantile_artifacts(
        estimators=estimators,
        config=config,
        training_signature=signature,
        manifest_hash=manifest_digest,
        feature_schema_hash=_feature_schema_hash(feature_names),
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
        metrics=metrics,
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
    warnings: Sequence[str] = (),
    blockers: Sequence[str] = (),
    input_snapshot: dict[str, object] | None = None,
) -> ResidualPredictionExecutionResult:
    row_payloads: list[dict[str, object]] = []
    for item in structural_rows:
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
            "structural_p50_kg": _q(structural_p50),
            "structural_p80_kg": _q(structural_p80),
            "structural_p90_kg": _q(structural_p90),
            "raw_residual_p50_kg": _q(Decimal("0")),
            "raw_residual_p80_kg": _q(Decimal("0")),
            "raw_residual_p90_kg": _q(Decimal("0")),
            "corrected_raw_p50_kg": _q(structural_p50),
            "corrected_raw_p80_kg": _q(structural_p50),
            "corrected_raw_p90_kg": _q(structural_p50),
            "mode": "structural_only",
        }
        projection = project_corrected_quantiles(
            structural_arrival_p50_kg=structural_p50,
            predicted_residual_p50_kg=Decimal("0"),
            predicted_residual_p80_kg=Decimal("0"),
            predicted_residual_p90_kg=Decimal("0"),
        )
        row_payload.update(
            {
                "corrected_p50_kg": _q(projection.corrected_p50_kg),
                "corrected_p80_kg": _q(projection.corrected_p80_kg),
                "corrected_p90_kg": _q(projection.corrected_p90_kg),
                "nonnegative_projection_applied": projection.nonnegative_projection_applied,
                "quantile_projection_applied": projection.quantile_projection_applied,
                "projection_reasons": [reason.value for reason in projection.projection_reasons],
                "feature_vector_hash": canonical_payload_hash(
                    {
                        "mode": "structural_only",
                        "model_run_id": model_run_id,
                        "task9_run_id": task9_run_id,
                        "task9_result_hash": task9_result_hash,
                        "destination_factory_id": item["destination_factory_id"],
                        "arrival_local_date": item["arrival_local_date"],
                        "forecast_horizon_days": item["forecast_horizon_days"],
                    }
                ),
                "feature_audit_hash": canonical_payload_hash(
                    {
                        "mode": "structural_only",
                        "fallback_reason": fallback_reason,
                    }
                ),
            }
        )
        row_payloads.append(row_payload)
    snapshot = input_snapshot or {
        "task9_run_id": task9_run_id,
        "task9_result_hash": task9_result_hash,
        "structural_row_count": len(structural_rows),
        "model_run_id": model_run_id,
        "training_signature": "0" * 64,
        "feature_analytics_build_run_id": None,
        "feature_actual_snapshot": None,
        "supplemental_feature_values": [],
        "feature_audit_hashes": [],
        "feature_rows": [],
        "artifact_hashes": [],
        "feature_schema_version": "task10-features-v1",
        "feature_schema_hash": "0" * 64,
        "projection_version": "task10-projection-v1",
        "fallback_policy": "structural_only_fallback",
    }
    return finalize_prediction_result(
        execution_status="completed",
        mode="structural_only",
        model_run_id=model_run_id,
        task9_run_id=task9_run_id,
        task9_result_hash=task9_result_hash,
        config_hash=config_hash,
        warnings=warnings,
        blockers=blockers,
        fallback_reason=fallback_reason,
        row_payloads=row_payloads,
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
    warnings: Sequence[str] = (),
    blockers: Sequence[str] = (),
    input_snapshot: dict[str, object] | None = None,
) -> ResidualPredictionExecutionResult:
    predicted_p50, predicted_p80, predicted_p90, decisions = _predict_residual_vectors(
        feature_rows=feature_rows,
        feature_audits=feature_audits,
        feature_names=feature_names,
        category_encodings=category_encodings,
        config=config,
        estimators=estimators,
    )
    row_payloads: list[dict[str, object]] = []
    for index, (structural_row, decision) in enumerate(
        zip(structural_rows, decisions, strict=True),
        start=0,
    ):
        structural_p50 = Decimal(str(structural_row["structural_p50_kg"]))
        structural_p80 = Decimal(str(structural_row["structural_p80_kg"]))
        structural_p90 = Decimal(str(structural_row["structural_p90_kg"]))
        projection = project_corrected_quantiles(
            structural_arrival_p50_kg=structural_p50,
            predicted_residual_p50_kg=predicted_p50[index],
            predicted_residual_p80_kg=predicted_p80[index],
            predicted_residual_p90_kg=predicted_p90[index],
        )
        row_payload = {
            "model_run_id": model_run_id,
            "prediction_run_id": 0,
            "task9_run_id": task9_run_id,
            "task9_result_hash": task9_result_hash,
            "destination_factory_id": structural_row["destination_factory_id"],
            "arrival_local_date": structural_row["arrival_local_date"],
            "forecast_horizon_days": structural_row["forecast_horizon_days"],
            "structural_p50_kg": _q(structural_p50),
            "structural_p80_kg": _q(structural_p80),
            "structural_p90_kg": _q(structural_p90),
            "raw_residual_p50_kg": _q(projection.raw_p50_kg - structural_p50),
            "raw_residual_p80_kg": _q(projection.raw_p80_kg - structural_p50),
            "raw_residual_p90_kg": _q(projection.raw_p90_kg - structural_p50),
            "corrected_raw_p50_kg": _q(projection.raw_p50_kg),
            "corrected_raw_p80_kg": _q(projection.raw_p80_kg),
            "corrected_raw_p90_kg": _q(projection.raw_p90_kg),
            "corrected_p50_kg": _q(projection.corrected_p50_kg),
            "corrected_p80_kg": _q(projection.corrected_p80_kg),
            "corrected_p90_kg": _q(projection.corrected_p90_kg),
            "nonnegative_projection_applied": projection.nonnegative_projection_applied,
            "quantile_projection_applied": projection.quantile_projection_applied,
            "projection_reasons": [item.value for item in projection.projection_reasons],
            "feature_vector_hash": decision.feature_vector_hash,
            "feature_audit_hash": decision.feature_audit_hash,
            "mode": decision.mode,
        }
        row_payloads.append(row_payload)

    snapshot = input_snapshot or {
        "task9_run_id": task9_run_id,
        "task9_result_hash": task9_result_hash,
        "model_run_id": model_run_id,
        "feature_names": feature_names,
    }
    row_fallback_reasons = {
        decision.fallback_reason
        for decision in decisions
        if decision.fallback_reason is not None
    }
    resolved_fallback_reason = fallback_reason
    if resolved_fallback_reason is None and len(row_fallback_reasons) == 1:
        resolved_fallback_reason = next(iter(row_fallback_reasons))
    if resolved_fallback_reason is None and row_fallback_reasons:
        resolved_fallback_reason = "mixed_row_level_fallback"
    return finalize_prediction_result(
        execution_status="completed",
        mode=(
            "structural_only"
            if all(decision.fallback_reason is not None for decision in decisions)
            else "residual_corrected"
        ),
        model_run_id=model_run_id,
        task9_run_id=task9_run_id,
        task9_result_hash=task9_result_hash,
        config_hash=config.config_hash,
        warnings=warnings,
        blockers=blockers,
        fallback_reason=resolved_fallback_reason,
        row_payloads=row_payloads,
        input_snapshot=snapshot,
    )
