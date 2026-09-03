"""Persisted replay-training authority reconstruction helpers.

These helpers are intentionally shared by the replay-trained execution path
and the prediction-time authority gate.  Keeping the conversion and dataset
identity algorithm in one place prevents caller-provided replay context from
being mistaken for the persisted Task 12 dataset authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, cast

from backend.app.harvest_state.canonical import canonical_decimal_string
from backend.app.models.residual_model import ResidualModelManifestRow
from backend.app.residual_model.canonical import canonical_payload_hash
from backend.app.residual_model.manifest import sort_feature_values
from backend.app.residual_model.schemas import (
    FeatureValue,
    FeatureVisibilityAudit,
    FinalTargetTrainingManifestRow,
    ResidualTrainingManifestRow,
)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def manifest_row_from_model(row: ResidualModelManifestRow) -> ResidualTrainingManifestRow:
    """Rebuild the canonical manifest row model from persisted columns."""

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


def normalized_numeric(value: object) -> str:
    return format(Decimal(str(value)).normalize(), "f")


def actual_input_rows(
    rows: Sequence[ResidualTrainingManifestRow],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Build the production Task 12 training and label identity rows."""

    training_rows = [
        {
            "observation_date": row.as_of_date.isoformat(),
            "value": normalized_numeric(row.observed_effective_receipt_kg),
        }
        for row in rows
    ]
    label_rows = [
        {
            "observation_date": row.target_arrival_local_date.isoformat(),
            "label_availability_date": row.label_actual_snapshot.source_cutoff.date().isoformat(),
            "value": normalized_numeric(row.observed_effective_receipt_kg),
        }
        for row in rows
    ]
    return training_rows, label_rows


def _datetime_string(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware datetime is required")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _json_safe(value: object) -> object:
    if isinstance(value, datetime):
        return _datetime_string(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return canonical_decimal_string(value)
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, tuple | list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _stable_manifest_row_payload(row: ResidualTrainingManifestRow) -> dict[str, object]:
    """Build the manifest payload while retaining Decimal values until JSON-safe conversion."""

    feature_values: list[dict[str, object]] = []
    for item in sort_feature_values(row.feature_values):
        feature_payload = item.model_dump(mode="python")
        raw_value = feature_payload.get("value")
        if isinstance(raw_value, str):
            try:
                feature_payload["value"] = canonical_decimal_string(Decimal(raw_value))
            except InvalidOperation:
                pass
        feature_values.append(feature_payload)

    return {
        "season_id": row.season_id,
        "destination_factory_id": row.destination_factory_id,
        "task9_run_id": row.task9_run_id,
        "task9_result_hash": row.task9_result_hash,
        "as_of_date": row.as_of_date,
        "target_arrival_local_date": row.target_arrival_local_date,
        "forecast_horizon_days": row.forecast_horizon_days,
        "label_actual_snapshot": row.label_actual_snapshot.model_dump(mode="python"),
        "feature_actual_snapshot": row.feature_actual_snapshot.model_dump(mode="python"),
        "observed_effective_receipt_kg": row.observed_effective_receipt_kg,
        "structural_p50_kg": row.structural_p50_kg,
        "structural_p80_kg": row.structural_p80_kg,
        "structural_p90_kg": row.structural_p90_kg,
        "residual_label_kg": row.residual_label_kg,
        "feature_values": feature_values,
        "feature_visibility_audit": (
            row.feature_visibility_audit.model_dump(mode="python")
            if row.feature_visibility_audit is not None
            else None
        ),
        "feature_vector_hash": row.feature_vector_hash,
        "feature_visibility_audit_hash": row.feature_visibility_audit_hash,
        "split": row.split,
        "include": row.include,
        "sample_weight": row.sample_weight,
        "exclusion_reason": row.exclusion_reason,
        "source_refs": sorted(row.source_refs),
    }


def actual_manifest_payload(
    rows: Sequence[ResidualTrainingManifestRow],
) -> list[dict[str, object]]:
    return [cast(dict[str, object], _json_safe(_stable_manifest_row_payload(row))) for row in rows]


def dataset_identity(
    *,
    training_rows: Sequence[Mapping[str, object]],
    label_rows: Sequence[Mapping[str, object]],
    manifest_rows: Sequence[Mapping[str, object]],
) -> str:
    return canonical_payload_hash(
        {
            "training_rows": list(training_rows),
            "label_rows": list(label_rows),
            "manifest_rows": list(manifest_rows),
        }
    )


def final_target_actual_input_rows(
    rows: Sequence[FinalTargetTrainingManifestRow],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    training_rows = [
        {
            "harvest_business_date": row.harvest_business_date.isoformat(),
            "value": normalized_numeric(row.actual_harvest_quantity_kg),
        }
        for row in rows
    ]
    label_rows = [
        {
            "harvest_business_date": row.harvest_business_date.isoformat(),
            "label_availability_date": row.forecast_cutoff_at.date().isoformat(),
            "value": normalized_numeric(row.actual_harvest_quantity_kg),
        }
        for row in rows
    ]
    return training_rows, label_rows


def final_target_manifest_payload(
    rows: Sequence[FinalTargetTrainingManifestRow],
) -> list[dict[str, object]]:
    from backend.app.residual_model.manifest import final_target_manifest_row_payload

    return [
        cast(
            dict[str, object],
            _json_safe(final_target_manifest_row_payload(row)),
        )
        for row in rows
    ]


def final_target_dataset_identity(
    *,
    training_rows: Sequence[Mapping[str, object]],
    label_rows: Sequence[Mapping[str, object]],
    manifest_rows: Sequence[Mapping[str, object]],
    prediction_target_kind: str,
    s2_authority_identity: str,
) -> str:
    return canonical_payload_hash(
        {
            "prediction_target_kind": prediction_target_kind,
            "s2_authority_identity": s2_authority_identity,
            "training_rows": list(training_rows),
            "label_rows": list(label_rows),
            "manifest_rows": list(manifest_rows),
        }
    )
