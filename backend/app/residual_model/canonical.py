from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast

from backend.app.harvest_state.canonical import (
    canonical_decimal_string,
    canonical_json_dumps,
    canonical_json_value,
    parse_decimal,
    quantize_quantity,
    quantize_ratio,
    sha256_hex,
)

JsonValue = (
    None
    | str
    | bool
    | int
    | float
    | list["JsonValue"]
    | dict[str, "JsonValue"]
)


def canonical_payload_hash(payload: object) -> str:
    return sha256_hex(payload)


def canonical_iso_date(value: date) -> str:
    return value.isoformat()


def canonical_iso_datetime(value: datetime) -> str:
    return value.isoformat()


def prediction_input_signature_payload(
    *,
    model_run_id: int | None,
    training_signature: str,
    task9_run_id: int,
    task9_result_hash: str,
    feature_analytics_build_run_id: int | None,
    feature_actual_snapshot: Mapping[str, Any] | None,
    supplemental_feature_values: Sequence[object],
    feature_audit_hashes: Sequence[str],
    feature_rows: Sequence[object],
    artifact_hashes: Sequence[str],
    config_hash: str,
    feature_schema_version: str,
    feature_schema_hash: str,
    projection_version: str,
    fallback_policy_version: str,
) -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        canonical_json_value(
        {
            "model_run_id": model_run_id,
            "training_signature": training_signature,
            "task9_run_id": task9_run_id,
            "task9_result_hash": task9_result_hash,
            "feature_analytics_build_run_id": feature_analytics_build_run_id,
            "feature_actual_snapshot": feature_actual_snapshot,
            "supplemental_feature_values": list(supplemental_feature_values),
            "feature_audit_hashes": list(feature_audit_hashes),
            "feature_rows": list(feature_rows),
            "artifact_hashes": list(artifact_hashes),
            "config_hash": config_hash,
            "feature_schema_version": feature_schema_version,
            "feature_schema_hash": feature_schema_hash,
            "projection_version": projection_version,
            "fallback_policy_version": fallback_policy_version,
        }
        ),
    )


def prediction_input_signature_hash(
    *,
    model_run_id: int | None,
    training_signature: str,
    task9_run_id: int,
    task9_result_hash: str,
    feature_analytics_build_run_id: int | None,
    feature_actual_snapshot: Mapping[str, Any] | None,
    supplemental_feature_values: Sequence[object],
    feature_audit_hashes: Sequence[str],
    feature_rows: Sequence[object],
    artifact_hashes: Sequence[str],
    config_hash: str,
    feature_schema_version: str,
    feature_schema_hash: str,
    projection_version: str,
    fallback_policy_version: str,
) -> str:
    return canonical_payload_hash(
        prediction_input_signature_payload(
            model_run_id=model_run_id,
            training_signature=training_signature,
            task9_run_id=task9_run_id,
            task9_result_hash=task9_result_hash,
            feature_analytics_build_run_id=feature_analytics_build_run_id,
            feature_actual_snapshot=feature_actual_snapshot,
            supplemental_feature_values=supplemental_feature_values,
            feature_audit_hashes=feature_audit_hashes,
            feature_rows=feature_rows,
            artifact_hashes=artifact_hashes,
            config_hash=config_hash,
            feature_schema_version=feature_schema_version,
            feature_schema_hash=feature_schema_hash,
            projection_version=projection_version,
            fallback_policy_version=fallback_policy_version,
        )
    )


__all__ = [
    "JsonValue",
    "canonical_decimal_string",
    "canonical_iso_date",
    "canonical_iso_datetime",
    "canonical_json_dumps",
    "canonical_json_value",
    "canonical_payload_hash",
    "prediction_input_signature_hash",
    "prediction_input_signature_payload",
    "parse_decimal",
    "quantize_quantity",
    "quantize_ratio",
    "sha256_hex",
    "Decimal",
    "Any",
]
