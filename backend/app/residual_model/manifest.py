from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from backend.app.residual_model.canonical import canonical_json_value, sha256_hex
from backend.app.residual_model.enums import ResidualSplit
from backend.app.residual_model.schemas import (
    FeatureValue,
    FeatureVisibilityAudit,
    FinalTargetActualsAuthoritySnapshot,
    FinalTargetTrainingManifestRow,
    ResidualTrainingManifestRow,
)


def sort_feature_values(values: Iterable[FeatureValue]) -> tuple[FeatureValue, ...]:
    return tuple(
        sorted(
            values,
            key=lambda item: (
                item.feature_name,
                item.observation_date or "",
                item.source_version,
                item.source_available_at,
                item.known_at,
            ),
        )
    )


def manifest_row_payload(row: ResidualTrainingManifestRow) -> dict[str, Any]:
    return {
        "season_id": row.season_id,
        "destination_factory_id": row.destination_factory_id,
        "task9_run_id": row.task9_run_id,
        "task9_result_hash": row.task9_result_hash,
        "as_of_date": row.as_of_date,
        "target_arrival_local_date": row.target_arrival_local_date,
        "forecast_horizon_days": row.forecast_horizon_days,
        "label_actual_snapshot": row.label_actual_snapshot.model_dump(mode="json"),
        "feature_actual_snapshot": row.feature_actual_snapshot.model_dump(mode="json"),
        "observed_effective_receipt_kg": row.observed_effective_receipt_kg,
        "structural_p50_kg": row.structural_p50_kg,
        "structural_p80_kg": row.structural_p80_kg,
        "structural_p90_kg": row.structural_p90_kg,
        "residual_label_kg": row.residual_label_kg,
        "feature_values": [
            item.model_dump(mode="json") for item in sort_feature_values(row.feature_values)
        ],
        "feature_visibility_audit": (
            row.feature_visibility_audit.model_dump(mode="json")
            if row.feature_visibility_audit is not None
            else None
        ),
        "feature_vector_hash": row.feature_vector_hash,
        "feature_visibility_audit_hash": row.feature_visibility_audit_hash,
        "split": row.split.value,
        "include": row.include,
        "sample_weight": row.sample_weight,
        "exclusion_reason": row.exclusion_reason,
        "source_refs": sorted(row.source_refs),
    }


def manifest_row_sort_key(row: ResidualTrainingManifestRow) -> tuple[object, ...]:
    return (
        row.as_of_date,
        row.target_arrival_local_date,
        row.destination_factory_id,
        row.task9_run_id,
        row.label_actual_snapshot.build_run_id,
        row.feature_actual_snapshot.build_run_id,
        row.feature_vector_hash,
    )


def manifest_hash(rows: Iterable[ResidualTrainingManifestRow]) -> str:
    payload = [manifest_row_payload(row) for row in sorted(rows, key=manifest_row_sort_key)]
    return sha256_hex(canonical_json_value(payload))


def final_target_manifest_row_payload(row: FinalTargetTrainingManifestRow) -> dict[str, Any]:
    return {
        "prediction_target_kind": "FINAL_TARGET_QUANTILE",
        "season_id": row.season_id,
        "farm_id": row.farm_id,
        "subfarm_id": row.subfarm_id,
        "variety_id": row.variety_id,
        "harvest_business_date": row.harvest_business_date,
        "forecast_cutoff_at": row.forecast_cutoff_at,
        "forecast_horizon_days": row.forecast_horizon_days,
        "actual_harvest_quantity_kg": row.actual_harvest_quantity_kg,
        "actuals_authority": row.actuals_authority.model_dump(mode="json"),
        "feature_values": [
            item.model_dump(mode="json") for item in sort_feature_values(row.feature_values)
        ],
        "feature_visibility_audit": (
            row.feature_visibility_audit.model_dump(mode="json")
            if row.feature_visibility_audit is not None
            else None
        ),
        "feature_vector_hash": row.feature_vector_hash,
        "feature_visibility_audit_hash": row.feature_visibility_audit_hash,
        "split": row.split.value,
        "include": row.include,
        "sample_weight": row.sample_weight,
        "exclusion_reason": row.exclusion_reason,
        "source_refs": sorted(row.source_refs),
    }


def final_target_manifest_row_sort_key(row: FinalTargetTrainingManifestRow) -> tuple[object, ...]:
    return (
        row.harvest_business_date,
        row.forecast_cutoff_at,
        row.farm_id,
        row.subfarm_id,
        row.variety_id,
        row.season_id,
        row.feature_vector_hash,
    )


def final_target_manifest_hash(rows: Iterable[FinalTargetTrainingManifestRow]) -> str:
    payload = [
        final_target_manifest_row_payload(row)
        for row in sorted(rows, key=final_target_manifest_row_sort_key)
    ]
    return sha256_hex(canonical_json_value(payload))


def final_target_manifest_row_from_payload(
    payload: dict[str, Any],
) -> FinalTargetTrainingManifestRow:
    feature_values = tuple(
        FeatureValue.model_validate(item) for item in payload.get("feature_values", [])
    )
    raw_audit = payload.get("feature_visibility_audit")
    feature_visibility_audit = (
        FeatureVisibilityAudit.model_validate(raw_audit) if raw_audit is not None else None
    )
    return FinalTargetTrainingManifestRow(
        season_id=payload["season_id"],
        farm_id=payload["farm_id"],
        subfarm_id=payload["subfarm_id"],
        variety_id=payload["variety_id"],
        harvest_business_date=payload["harvest_business_date"],
        forecast_cutoff_at=payload["forecast_cutoff_at"],
        forecast_horizon_days=payload["forecast_horizon_days"],
        actual_harvest_quantity_kg=payload["actual_harvest_quantity_kg"],
        actuals_authority=FinalTargetActualsAuthoritySnapshot.model_validate(
            payload["actuals_authority"]
        ),
        feature_values=feature_values,
        feature_visibility_audit=feature_visibility_audit,
        feature_vector_hash=payload["feature_vector_hash"],
        feature_visibility_audit_hash=payload["feature_visibility_audit_hash"],
        split=ResidualSplit(payload["split"]),
        include=payload["include"],
        sample_weight=payload["sample_weight"],
        exclusion_reason=payload.get("exclusion_reason"),
        source_refs=tuple(payload.get("source_refs", [])),
    )
