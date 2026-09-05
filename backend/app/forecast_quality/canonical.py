from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from enum import Enum
from typing import Any

from .enums import FrozenVersion, MetricStatus
from .exceptions import (
    S3CanonicalIdentityConflictError,
    S3ContractInvariantViolationError,
    S3DecimalAssertionError,
    S3StructuralDuplicateError,
)
from .schemas import (
    BaselineRequest,
    BaselineResult,
    BaselineSourceSnapshot,
    BreakdownSpec,
    DailyMetricResult,
    S3BindingRow,
    S3EvaluationInput,
)

DECIMAL_QUANTUM = Decimal("0.000001")
BASELINE_SCHEMA_VERSION = "v0.2-s3-baseline-v1"
BASELINE_GRAIN = "SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_TARGET_DATE"
BASELINE_HORIZON_RULE = "TARGET_DATE_ENCODES_HORIZON"

BASELINE_CANONICAL_ROOT_FIELDS = (
    "schema_version",
    "s2_run_identity",
    "s2_manifest_identity",
    "s2_binding_row_set_hash",
    "baseline_source_snapshot_identity",
    "baseline_source_snapshot_hash",
    "baseline_source_row_set_hash",
    "baseline_source_visibility_manifest_hash",
    "baseline_source_visibility_cutoff_at",
    "baseline_policy_version",
    "season_analog_mapping_policy_version",
    "prior_season_identity",
    "baseline_grain",
    "baseline_horizon_rule",
    "breakdown_dimensions",
    "s2_total_binding_row_count",
    "s2_comparable_binding_row_count",
    "s2_excluded_binding_row_count",
    "s2_not_computable_binding_row_count",
    "coverage_ratio",
    "metric_input_mask_policy_version",
    "metric_input_mask_hash",
    "metric_input_row_count",
    "metric_input_quantile",
    "unique_actual_physical_row_count",
    "per_breakdown_cell",
)

BASELINE_CANONICAL_CELL_FIELDS = (
    "baseline_point_forecast_kg",
    "s2_total_binding_row_count",
    "s2_comparable_binding_row_count",
    "s2_excluded_binding_row_count",
    "s2_not_computable_binding_row_count",
    "coverage_ratio",
    "metric_input_mask_policy_version",
    "metric_input_mask_hash",
    "metric_input_row_count",
    "metric_input_quantile",
    "unique_actual_physical_row_count",
    "mape_eligible_row_count",
    "mape_zero_actual_row_count",
    "metric_status",
    "reason_code",
)


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, Decimal):
        return emit_s3_decimal(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise S3ContractInvariantViolationError("datetime must be timezone-aware")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _json_value(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_json_value(item) for item in value)
    if isinstance(value, float):
        raise S3DecimalAssertionError("native float is not a business value")
    return value


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        _json_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def emit_s3_decimal(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise S3DecimalAssertionError("S3 numeric output requires a finite Decimal")
    try:
        return format(value.quantize(DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN), "f")
    except (InvalidOperation, ValueError) as exc:
        raise S3DecimalAssertionError("Decimal cannot be quantized") from exc


def emit_s3_area_mu(value: Decimal) -> str:
    """Serialize farm area without lossy kg-scale quantization."""
    if not isinstance(value, Decimal) or not value.is_finite():
        raise S3DecimalAssertionError("S3 area output requires a finite Decimal")
    return format(value, "f")


def compute_metric_input_mask_hash(mask: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(mask)).hexdigest()


def _identity_from_row(row: S3BindingRow) -> tuple[str, str, Decimal]:
    if (
        row.actual_physical_key is None
        or row.stable_actual_identity is None
        or row.actual_value_kg is None
    ):
        raise S3StructuralDuplicateError("comparable row lacks exact actual identity")
    if not isinstance(row.actual_value_kg, Decimal) or not row.actual_value_kg.is_finite():
        raise S3DecimalAssertionError("actual value must be finite Decimal")
    return row.actual_physical_key, row.stable_actual_identity, row.actual_value_kg


def build_actual_physical_registry(rows: Sequence[S3BindingRow]) -> dict[str, Any]:
    records: dict[str, tuple[str, Decimal]] = {}
    for row in rows:
        physical_key, stable_identity, actual_value = _identity_from_row(row)
        previous = records.get(physical_key)
        if previous is not None and previous != (stable_identity, actual_value):
            raise S3StructuralDuplicateError("conflicting actual physical record")
        records[physical_key] = (stable_identity, actual_value)
    return {
        "records": {
            key: {"stable_actual_identity": identity, "actual_value_kg": value}
            for key, (identity, value) in sorted(records.items())
        },
        "forecast_row_count_before": len(rows),
        "forecast_row_count_after": len(rows),
        "unique_actual_physical_row_count": len(records),
    }


def _require_nonempty(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise S3CanonicalIdentityConflictError(f"{field} is missing")


def _validate_metric_result(metric_result: DailyMetricResult) -> None:
    for field in (
        "s2_run_identity",
        "s2_manifest_identity",
        "s2_binding_row_set_hash",
        "metric_input_mask_hash",
    ):
        _require_nonempty(getattr(metric_result, field), field)
    total = metric_result.s2_total_binding_row_count
    if total == 0 and metric_result.coverage_ratio is not None:
        raise S3ContractInvariantViolationError("zero rows require null coverage")
    if total != 0 and metric_result.coverage_ratio is None:
        raise S3ContractInvariantViolationError("nonzero rows require coverage")
    if metric_result.metric_input_mask_policy_version != FrozenVersion.METRIC_INPUT_MASK_V1:
        raise S3ContractInvariantViolationError("metric mask policy drift")


def _validate_baseline_result(result: BaselineResult) -> None:
    for field in (
        "source_snapshot_identity",
        "source_snapshot_hash",
        "source_row_set_hash",
        "visibility_manifest_hash",
    ):
        _require_nonempty(getattr(result, field), field)
    computed = result.metric_status == MetricStatus.COMPUTED
    if computed != (result.baseline_point_forecast_kg is not None):
        raise S3ContractInvariantViolationError("baseline value/status nullability drift")
    if result.metric_status is None or result.reason_code is None:
        raise S3ContractInvariantViolationError("baseline status/reason is required")


def _cell_payload(
    baseline_result: BaselineResult, metric_result: DailyMetricResult
) -> dict[str, Any]:
    _validate_metric_result(metric_result)
    _validate_baseline_result(baseline_result)
    return {
        "baseline_point_forecast_kg": baseline_result.baseline_point_forecast_kg,
        "s2_total_binding_row_count": metric_result.s2_total_binding_row_count,
        "s2_comparable_binding_row_count": metric_result.s2_comparable_binding_row_count,
        "s2_excluded_binding_row_count": metric_result.s2_excluded_binding_row_count,
        "s2_not_computable_binding_row_count": metric_result.s2_not_computable_binding_row_count,
        "coverage_ratio": metric_result.coverage_ratio,
        "metric_input_mask_policy_version": metric_result.metric_input_mask_policy_version,
        "metric_input_mask_hash": metric_result.metric_input_mask_hash,
        "metric_input_row_count": metric_result.metric_input_row_count,
        "metric_input_quantile": metric_result.metric_input_quantile,
        "unique_actual_physical_row_count": metric_result.unique_actual_physical_row_count,
        "mape_eligible_row_count": metric_result.mape_eligible_row_count,
        "mape_zero_actual_row_count": metric_result.mape_zero_actual_row_count,
        "metric_status": baseline_result.metric_status,
        "reason_code": baseline_result.reason_code,
    }


def build_baseline_canonical_payload_cell(
    *, baseline_result: BaselineResult, metric_result: DailyMetricResult
) -> dict[str, Any]:
    payload = _cell_payload(baseline_result, metric_result)
    if tuple(payload) != BASELINE_CANONICAL_CELL_FIELDS:
        raise S3ContractInvariantViolationError("cell field order drift")
    return payload


def _six_axis_identity(spec: BreakdownSpec) -> dict[str, Any]:
    return {
        "forecast_horizon_days": spec.forecast_horizon_days,
        "farm_business_key": spec.farm_business_key,
        "subfarm_business_key": spec.subfarm_business_key,
        "variety_business_key": spec.variety_business_key,
        "season_business_key": spec.season_business_key,
        "model_identity": spec.model_identity,
    }


def build_baseline_canonical_payload_root(
    *,
    evaluation_input: S3EvaluationInput,
    baseline_request: BaselineRequest,
    source_snapshot: BaselineSourceSnapshot,
    baseline_result: BaselineResult,
    metric_result: DailyMetricResult,
    breakdown_spec: BreakdownSpec,
    per_breakdown_cell: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    _validate_metric_result(metric_result)
    _validate_baseline_result(baseline_result)
    for field in (
        "s2_run_identity",
        "s2_manifest_identity",
        "s2_binding_row_set_hash",
        "prior_season_identity",
        "source_snapshot_identity",
        "source_snapshot_hash",
        "source_row_set_hash",
        "visibility_manifest_hash",
    ):
        source = getattr(evaluation_input, field, None)
        if source is None:
            source = getattr(baseline_request, field, None)
        if source is None:
            source = getattr(source_snapshot, field, None)
        _require_nonempty(source, field)
    if metric_result.metric_policy_version is None:
        raise S3ContractInvariantViolationError("metric policy is required")
    if metric_result.s2_total_binding_row_count == 0:
        if metric_result.coverage_ratio is not None:
            raise S3ContractInvariantViolationError("zero rows require null root coverage")
    elif metric_result.coverage_ratio is None:
        raise S3ContractInvariantViolationError("nonzero rows require root coverage")
    payload = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "s2_run_identity": evaluation_input.s2_run_identity,
        "s2_manifest_identity": evaluation_input.s2_manifest_identity,
        "s2_binding_row_set_hash": evaluation_input.s2_binding_row_set_hash,
        "baseline_source_snapshot_identity": source_snapshot.source_snapshot_identity,
        "baseline_source_snapshot_hash": source_snapshot.source_snapshot_hash,
        "baseline_source_row_set_hash": source_snapshot.source_row_set_hash,
        "baseline_source_visibility_manifest_hash": source_snapshot.visibility_manifest_hash,
        "baseline_source_visibility_cutoff_at": source_snapshot.visibility_cutoff_at,
        "baseline_policy_version": baseline_request.baseline_policy_version,
        "season_analog_mapping_policy_version": (
            source_snapshot.season_analog_mapping_policy_version
        ),
        "prior_season_identity": baseline_request.prior_season_identity,
        "baseline_grain": BASELINE_GRAIN,
        "baseline_horizon_rule": BASELINE_HORIZON_RULE,
        "breakdown_dimensions": _six_axis_identity(breakdown_spec),
        "s2_total_binding_row_count": metric_result.s2_total_binding_row_count,
        "s2_comparable_binding_row_count": metric_result.s2_comparable_binding_row_count,
        "s2_excluded_binding_row_count": metric_result.s2_excluded_binding_row_count,
        "s2_not_computable_binding_row_count": metric_result.s2_not_computable_binding_row_count,
        "coverage_ratio": metric_result.coverage_ratio,
        "metric_input_mask_policy_version": metric_result.metric_input_mask_policy_version,
        "metric_input_mask_hash": metric_result.metric_input_mask_hash,
        "metric_input_row_count": metric_result.metric_input_row_count,
        "metric_input_quantile": metric_result.metric_input_quantile,
        "unique_actual_physical_row_count": metric_result.unique_actual_physical_row_count,
        "per_breakdown_cell": list(per_breakdown_cell),
    }
    if tuple(payload) != BASELINE_CANONICAL_ROOT_FIELDS:
        raise S3ContractInvariantViolationError("root field order drift")
    return payload
