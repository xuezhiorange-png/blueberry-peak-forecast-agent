from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from backend.app.residual_model.canonical import canonical_json_value, sha256_hex
from backend.app.residual_model.schemas import FeatureValue, ResidualTrainingManifestRow


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
            item.model_dump(mode="json")
            for item in sort_feature_values(row.feature_values)
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
    payload = [
        manifest_row_payload(row)
        for row in sorted(rows, key=manifest_row_sort_key)
    ]
    return sha256_hex(canonical_json_value(payload))
