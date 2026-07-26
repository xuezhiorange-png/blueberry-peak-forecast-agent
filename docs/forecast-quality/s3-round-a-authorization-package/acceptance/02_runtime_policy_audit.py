#!/usr/bin/env python3
"""Execute the Round A domain contract against the implementation worktree."""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import math
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(os.environ.get("ROUND_A_WORKTREE", Path.cwd())).resolve()
BACKEND = ROOT / "backend"
if not BACKEND.is_dir():
    raise SystemExit(f"missing backend at {BACKEND}")
sys.path.insert(0, str(BACKEND))


def enum_names(enum_type: Any) -> set[str]:
    return {member.name for member in enum_type}


def field_names(model_type: Any) -> list[str]:
    if dataclasses.is_dataclass(model_type):
        return [field.name for field in dataclasses.fields(model_type)]
    model_fields = getattr(model_type, "model_fields", None)
    if model_fields is not None:
        return list(model_fields)
    fields = getattr(model_type, "__fields__", None)
    if fields is not None:
        return list(fields)
    annotations = getattr(model_type, "__annotations__", None)
    if annotations:
        return list(annotations)
    raise AssertionError(f"cannot inspect fields for {model_type!r}")


def read_value(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value[name]
    return getattr(value, name)


def member_name(value: Any) -> str:
    return getattr(value, "name", str(value))


def construct(model_type: Any, values: Mapping[str, Any]) -> Any:
    names = field_names(model_type)
    missing = [name for name in names if name not in values]
    if missing:
        raise AssertionError(f"fixture values missing fields for {model_type.__name__}: {missing}")
    payload = {name: values[name] for name in names}
    return model_type(**payload)


def call_with_contract_args(function: Any, values: Mapping[str, Any]) -> Any:
    signature = inspect.signature(function)
    expected = set(signature.parameters)
    if expected != set(values):
        raise AssertionError(
            f"{function.__name__} signature drift: expected {sorted(values)}, got {sorted(expected)}"
        )
    return function(**values)


enums = importlib.import_module("app.forecast_quality.enums")
schemas = importlib.import_module("app.forecast_quality.schemas")
exceptions = importlib.import_module("app.forecast_quality.exceptions")
canonical = importlib.import_module("app.forecast_quality.canonical")
daily = importlib.import_module("app.forecast_quality.calculator_daily")
calendar = importlib.import_module("app.forecast_quality.season_calendar")
baseline = importlib.import_module("app.forecast_quality.baseline")

expected_enums = {
    "MetricStatus": {"COMPUTED", "COMPARED", "NOT_COMPUTABLE", "NOT_VERIFIED", "INSUFFICIENT_SAMPLE"},
    "ComparisonAvailability": {"AVAILABLE", "BLOCKED"},
    "SupportedQuantile": {"P50", "P80", "P90"},
    "CrossQuantileInputSource": {"S2_IMMUTABLE_BACKTEST_BINDING"},
}
for name, expected in expected_enums.items():
    actual = enum_names(getattr(enums, name))
    if actual != expected:
        raise AssertionError(f"{name} mismatch: {sorted(actual)}")

expected_reason_codes = {
    "NONE",
    "NO_MAPE_ELIGIBLE_ROWS",
    "MAPE_DENOMINATOR_ZERO",
    "WAPE_DENOMINATOR_ZERO",
    "RELATIVE_BIAS_DENOMINATOR_ZERO",
    "NO_COMPLETE_7DAY_WINDOW",
    "QUANTILE_SEMANTICS_NOT_VERIFIED",
    "BELOW_MINIMUM",
    "BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED",
    "COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING",
    "SIGNED_DIRECTION_ONLY",
    "PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE",
    "NO_PRIOR_SEASON_ANALOG_DAY",
    "NO_PRIOR_SEASON_ANALOG_ACTUAL",
    "BASELINE_SOURCE_NOT_VISIBLE_AT_CURRENT_FORECAST_CUTOFF",
    "NO_S2_BINDING_ROWS",
}
if enum_names(enums.ReasonCode) != expected_reason_codes:
    raise AssertionError("ReasonCode closed set mismatch")
if hasattr(enums, "InternalReasonCode") and enum_names(enums.InternalReasonCode):
    if enum_names(enums.InternalReasonCode) & expected_reason_codes:
        raise AssertionError("public/internal ReasonCode sets overlap")

if field_names(schemas.ActualPhysicalRecord) != [
    "physical_key",
    "stable_actual_identity",
    "actual_value_kg",
]:
    raise AssertionError("ActualPhysicalRecord field contract mismatch")
if field_names(schemas.S3EvaluationInput) != [
    "rows",
    "s2_run_identity",
    "s2_manifest_identity",
    "s2_binding_row_set_hash",
    "metric_policy_version",
    "baseline_policy_version",
]:
    raise AssertionError("S3EvaluationInput field contract mismatch")
for schema_name in (
    "S3BindingRow",
    "FarmDailyActualAggregate",
    "DailyMetricResult",
    "MetricValueCell",
    "BreakdownSpec",
    "BaselineRequest",
    "BaselineSourceSnapshot",
    "BaselineResult",
):
    if not field_names(getattr(schemas, schema_name)):
        raise AssertionError(f"empty schema: {schema_name}")

if canonical.compute_metric_input_mask_hash.__module__ != "app.forecast_quality.canonical":
    raise AssertionError("metric mask hash owner drift")
if daily.compute_metric_input_mask_hash is not canonical.compute_metric_input_mask_hash:
    raise AssertionError("calculator_daily defines a duplicate metric mask hash")

decimal_cases = {
    "1": "1.000000",
    "1.2": "1.200000",
    "0.000001": "0.000001",
    "0.0000005": "0.000000",
}
for raw, expected in decimal_cases.items():
    actual = canonical.emit_s3_decimal(Decimal(raw))
    if actual != expected:
        raise AssertionError(f"Decimal emission {raw}: {actual!r} != {expected!r}")
for invalid in (1.0, float("nan"), float("inf")):
    try:
        canonical.emit_s3_decimal(invalid)
    except exceptions.S3DecimalAssertionError:
        pass
    else:
        raise AssertionError(f"invalid numeric accepted: {invalid!r}")
try:
    import numpy as np
except ImportError:
    np = None
if np is not None:
    try:
        canonical.emit_s3_decimal(np.float64(1.0))
    except exceptions.S3DecimalAssertionError:
        pass
    else:
        raise AssertionError("NumPy float accepted")

if canonical.canonical_json_bytes({"b": 1, "a": 2}) != canonical.canonical_json_bytes({"a": 2, "b": 1}):
    raise AssertionError("canonical JSON is order-dependent")
mask = {
    "metric_input_mask_policy_version": "v0.2-s3-metric-input-mask-v1",
    "s2_status_predicate": "S2_STATUS_COMPARABLE",
    "forecast_quantile_predicate": "P50",
    "actual_pair_predicate": "EXACT_ACTUAL_PAIRED",
    "breakdown_identity": {"farm_business_key": "farm-a"},
    "source_row_set_identity": "row-set-a",
}
mask_hash = canonical.compute_metric_input_mask_hash(mask)
if not isinstance(mask_hash, str) or len(mask_hash) != 64:
    raise AssertionError("invalid metric input mask hash")

quantiles = [enums.SupportedQuantile.P50, enums.SupportedQuantile.P80, enums.SupportedQuantile.P90]
common_row = {
    "actual_physical_key": "physical-a",
    "stable_actual_identity": "actual-a",
    "actual_value_kg": Decimal("10.000000"),
    "forecast_value_kg": Decimal("11.000000"),
    "forecast_horizon_days": 7,
    "forecast_target_date": date(2025, 2, 10),
    "forecast_cutoff_at": datetime(2025, 2, 1, tzinfo=timezone.utc),
    "s2_status": "COMPARABLE",
    "season_business_key": "season-2025",
    "farm_business_key": "farm-a",
    "subfarm_business_key": "subfarm-a",
    "variety_business_key": "variety-a",
    "model_identity": "model-a",
    "actual_visibility_timestamp": datetime(2025, 2, 1, tzinfo=timezone.utc),
}
rows = []
for quantile in quantiles:
    values = dict(common_row)
    values["forecast_business_key"] = f"forecast-{quantile.name}"
    values["forecast_quantile"] = quantile
    rows.append(construct(schemas.S3BindingRow, values))
registry = canonical.build_actual_physical_registry(rows)
if read_value(registry, "forecast_row_count_before") != 3:
    raise AssertionError("forecast rows were not retained before registry")
if read_value(registry, "forecast_row_count_after") != 3:
    raise AssertionError("forecast rows were not retained after registry")
if read_value(registry, "unique_actual_physical_row_count") != 1:
    raise AssertionError("actual physical row was not deduplicated")
for field, changed in (("stable_actual_identity", "actual-conflict"), ("actual_value_kg", Decimal("12.000000"))):
    conflict_values = dict(common_row)
    conflict_values["forecast_business_key"] = "forecast-conflict"
    conflict_values["forecast_quantile"] = enums.SupportedQuantile.P80
    conflict_values[field] = changed
    conflict_row = construct(schemas.S3BindingRow, conflict_values)
    try:
        canonical.build_actual_physical_registry([rows[0], conflict_row])
    except exceptions.S3StructuralDuplicateError:
        pass
    else:
        raise AssertionError(f"actual conflict accepted for {field}")

calendar_cases = [
    (date(2025, 2, 10), date(2025, 1, 1), date(2025, 3, 31), date(2024, 1, 1), date(2024, 3, 31), date(2024, 2, 10)),
    (date(2024, 2, 29), date(2024, 1, 1), date(2024, 3, 31), date(2023, 1, 1), date(2023, 3, 31), date(2023, 2, 28)),
    (date(2024, 2, 29), date(2024, 1, 1), date(2024, 3, 31), date(2020, 1, 1), date(2020, 3, 31), date(2020, 2, 29)),
    (date(2025, 3, 31), date(2025, 1, 1), date(2025, 3, 31), date(2024, 1, 1), date(2024, 3, 1), date(2024, 3, 1)),
    (date(2025, 4, 1), date(2025, 1, 1), date(2025, 3, 31), date(2024, 1, 1), date(2024, 3, 31), None),
    (date(2025, 1, 1), date(2025, 1, 1), date(2025, 3, 31), date(2024, 1, 1), date(2024, 3, 31), date(2024, 1, 1)),
    (date(2025, 3, 31), date(2025, 1, 1), date(2025, 3, 31), date(2024, 2, 1), date(2024, 3, 31), date(2024, 3, 31)),
    (date(2025, 1, 15), date(2025, 1, 1), date(2025, 3, 31), date(2024, 1, 1), date(2024, 3, 31), date(2024, 1, 15)),
]
for args in calendar_cases:
    actual = call_with_contract_args(
        calendar.resolve_prior_season_analog_date,
        {
            "current_target_date": args[0],
            "current_season_start": args[1],
            "current_season_end": args[2],
            "prior_season_start": args[3],
            "prior_season_end": args[4],
            "policy_version": "v0.2-s3-season-analog-mapping-v1",
        },
    )
    if actual != args[5]:
        raise AssertionError(f"calendar case mismatch: {actual!r} != {args[5]!r}")

print("PUBLIC_REASON_CODE_CLOSED_SET_EQUALITY=true")
print("ACTUAL_PHYSICAL_RECORD_FIELD_COUNT=3")
print("S3_EVALUATION_INPUT_FIELD_COUNT=6")
print("DECIMAL_POLICY_RUNTIME=PASS")
print("CANONICAL_OWNER_RUNTIME=PASS")
print("CROSS_QUANTILE_REGISTRY_RUNTIME=PASS")
print("SEASON_CALENDAR_CASE_COUNT=8")
print("RUNTIME_POLICY_AUDIT=PASS")
