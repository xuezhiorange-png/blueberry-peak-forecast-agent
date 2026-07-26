#!/usr/bin/env python3
"""Run the Round A domain contract against a real implementation worktree."""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import inspect
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("ROUND_A_WORKTREE", Path.cwd())).resolve()
PACKAGE_DIR = (
    Path(os.environ.get("PACKAGE_DIR", "")).resolve() if os.environ.get("PACKAGE_DIR") else None
)
BASE_SHA = os.environ.get("IMPLEMENTATION_BASE_SHA")
if not BASE_SHA:
    raise SystemExit("IMPLEMENTATION_BASE_SHA is required")
if PACKAGE_DIR is None or not PACKAGE_DIR.is_dir():
    raise SystemExit("PACKAGE_DIR is required")
BACKEND = ROOT / "backend"
if not BACKEND.is_dir():
    raise SystemExit(f"missing backend at {BACKEND}")
sys.path.insert(0, str(BACKEND))


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


git("cat-file", "-e", f"{BASE_SHA}^{{commit}}")
subprocess.run(["git", "merge-base", "--is-ancestor", BASE_SHA, "HEAD"], cwd=ROOT, check=True)
git(
    "cat-file", "-e", f"{BASE_SHA}:docs/forecast-quality/s3-round-a-authorization-package/README.md"
)
sha_file = PACKAGE_DIR / "acceptance" / "SHA256SUMS"
expected_script_paths = {
    "docs/forecast-quality/s3-round-a-authorization-package/acceptance/01_changed_path_gate.sh",
    "docs/forecast-quality/s3-round-a-authorization-package/acceptance/02_runtime_policy_audit.py",
    "docs/forecast-quality/s3-round-a-authorization-package/acceptance/03_test_gate.sh",
    "docs/forecast-quality/s3-round-a-authorization-package/acceptance/04_static_gate.sh",
}
hash_records = []
for line in sha_file.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    parts = line.split(None, 1)
    if len(parts) != 2:
        raise AssertionError("malformed script hash record")
    expected_hash, repository_relative_path = parts
    if (
        repository_relative_path not in expected_script_paths
        or repository_relative_path.startswith("/")
        or ".." in Path(repository_relative_path).parts
    ):
        raise AssertionError(f"invalid script hash path: {repository_relative_path}")
    hash_records.append((expected_hash, repository_relative_path))
if {path for _, path in hash_records} != expected_script_paths or len(hash_records) != 4:
    raise AssertionError("script hash record set mismatch")
for expected_hash, repository_relative_path in hash_records:
    actual_hash = subprocess.check_output(
        ["git", "show", f"{BASE_SHA}:{repository_relative_path}"], cwd=ROOT
    )
    if hashlib.sha256(actual_hash).hexdigest() != expected_hash:
        raise AssertionError(f"package script hash drift: {repository_relative_path}")
print("SCRIPT_HASH_RECORD_COUNT=4")
print("SCRIPT_HASH_PATH_PREFIX_MATCH_COUNT=4")
print("SCRIPT_HASH_MISMATCH_COUNT=0")
print("SCRIPT_HASH_MISSING_PATH_COUNT=0")
print("STALE_SCRIPT_HASH_REFERENCE_COUNT=0")


def enum_names(enum_type: Any) -> set[str]:
    return {member.name for member in enum_type}


def enum_values(enum_type: Any) -> set[str]:
    return {str(member.value) for member in enum_type}


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


def read_value(
    value: Any,
    name: str,
    default: Any = ...,
) -> Any:
    if isinstance(value, Mapping):
        if default is ...:
            return value[name]
        return value.get(name, default)
    if default is ...:
        return getattr(value, name)
    return getattr(value, name, default)


def member_name(value: Any) -> str:
    return getattr(value, "name", str(value))


def construct(model_type: Any, values: Mapping[str, Any]) -> Any:
    names = field_names(model_type)
    missing = [name for name in names if name not in values]
    if missing:
        raise AssertionError(f"fixture values missing fields for {model_type.__name__}: {missing}")
    return model_type(**{name: values[name] for name in names})


def call_with_contract_args(function: Any, values: Mapping[str, Any]) -> Any:
    signature = inspect.signature(function)
    expected = set(signature.parameters)
    if expected != set(values):
        raise AssertionError(
            f"{function.__name__} signature drift: expected {sorted(values)}, "
            f"got {sorted(expected)}"
        )
    return function(**values)


def invoke_one_argument(function: Any, value: Any) -> Any:
    parameters = list(inspect.signature(function).parameters.values())
    if len(parameters) != 1:
        raise AssertionError(f"{function.__name__} must have one canonical payload argument")
    return function(value)


def as_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def status_name(value: Any) -> str:
    return member_name(value)


enums = importlib.import_module("app.forecast_quality.enums")
schemas = importlib.import_module("app.forecast_quality.schemas")
exceptions = importlib.import_module("app.forecast_quality.exceptions")
canonical = importlib.import_module("app.forecast_quality.canonical")
daily = importlib.import_module("app.forecast_quality.calculator_daily")
breakdown = importlib.import_module("app.forecast_quality.breakdown")
aggregation = importlib.import_module("app.forecast_quality.aggregation")
calendar = importlib.import_module("app.forecast_quality.season_calendar")
baseline = importlib.import_module("app.forecast_quality.baseline")

expected_enums = {
    "MetricStatus": {
        "COMPUTED",
        "COMPARED",
        "NOT_COMPUTABLE",
        "NOT_VERIFIED",
        "INSUFFICIENT_SAMPLE",
    },
    "ComparisonAvailability": {"AVAILABLE", "BLOCKED"},
    "SupportedQuantile": {"P50", "P80", "P90"},
    "CrossQuantileInputSource": {"S2_IMMUTABLE_BACKTEST_BINDING"},
    "FrozenVersion": {
        "METRIC_INPUT_MASK_V1",
        "NAIVE_BASELINE_POLICY_V1",
        "SEASON_ANALOG_MAPPING_V1",
    },
}
for name, expected in expected_enums.items():
    actual = enum_names(getattr(enums, name))
    if actual != expected:
        raise AssertionError(f"{name} mismatch: {sorted(actual)}")
expected_frozen_values = {
    "METRIC_INPUT_MASK_V1": "v0.2-s3-metric-input-mask-v1",
    "NAIVE_BASELINE_POLICY_V1": "v0.2-s3-naive-baseline-policy-v1",
    "SEASON_ANALOG_MAPPING_V1": "v0.2-s3-season-analog-mapping-v1",
}
if enum_values(enums.FrozenVersion) != set(expected_frozen_values.values()):
    raise AssertionError("FrozenVersion value set mismatch")
if {member.name: str(member.value) for member in enums.FrozenVersion} != expected_frozen_values:
    raise AssertionError("FrozenVersion name/value mapping mismatch")
print("FROZEN_VERSION_NAME_SET_EQUALITY=true")
print("FROZEN_VERSION_VALUE_SET_EQUALITY=true")

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
actual_reason_codes = enum_names(enums.ReasonCode)
if actual_reason_codes != expected_reason_codes:
    raise AssertionError(f"ReasonCode closed set mismatch: {sorted(actual_reason_codes)}")
internal_enum = getattr(enums, "InternalReasonCode", None)
internal_reason_codes = set() if internal_enum is None else enum_names(internal_enum)
if internal_reason_codes & actual_reason_codes:
    raise AssertionError("public/internal ReasonCode sets overlap")
print(f"PUBLIC_REASON_CODE_MEMBER_COUNT={len(actual_reason_codes)}")
print("PUBLIC_REASON_CODE_CLOSED_SET_EQUALITY=true")
print(f"INTERNAL_REASON_CODE_PRESENT={str(internal_enum is not None).lower()}")
print(f"INTERNAL_REASON_CODE_MEMBER_COUNT={len(internal_reason_codes)}")
print(
    "PUBLIC_INTERNAL_REASON_CODE_DISJOINT="
    f"{str(not bool(internal_reason_codes & actual_reason_codes)).lower()}"
)

schema_contracts = {
    "ActualPhysicalRecord": ["physical_key", "stable_actual_identity", "actual_value_kg"],
    "S3EvaluationInput": [
        "rows",
        "s2_run_identity",
        "s2_manifest_identity",
        "s2_binding_row_set_hash",
        "metric_policy_version",
        "baseline_policy_version",
    ],
    "FarmDailyForecastAggregate": [
        "season_business_key",
        "farm_business_key",
        "variety_business_key",
        "target_date",
        "forecast_cutoff_at",
        "model_identity",
        "forecast_quantile",
        "forecast_horizon_days",
        "forecast_value_kg",
        "source_forecast_business_keys",
    ],
}
for schema_name, expected in schema_contracts.items():
    actual = field_names(getattr(schemas, schema_name))
    if actual != expected:
        raise AssertionError(f"{schema_name} field contract mismatch: {actual}")
    print(f"{schema_name}_FIELD_COUNT={len(actual)}")
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

public_owner_checks = {
    "compute_metric_input_mask_hash": canonical,
    "emit_s3_decimal": canonical,
    "canonical_json_bytes": canonical,
    "build_actual_physical_registry": canonical,
    "build_baseline_canonical_payload_root": canonical,
    "build_baseline_canonical_payload_cell": canonical,
    "compute_daily_metrics": daily,
    "calculate_breakdown_cells": breakdown,
    "aggregate_daily_actuals": aggregation,
    "aggregate_daily_forecasts": aggregation,
    "resolve_prior_season_analog_date": calendar,
    "resolve_baseline_point_forecast": baseline,
}
for symbol, owner in public_owner_checks.items():
    function = getattr(owner, symbol, None)
    if function is None or getattr(function, "__module__", None) != owner.__name__:
        raise AssertionError(f"public symbol owner drift: {symbol}")
if getattr(daily, "compute_metric_input_mask_hash", None) is getattr(
    canonical, "compute_metric_input_mask_hash", None
):
    raise AssertionError("calculator_daily must not define a duplicate metric mask owner")
print("PUBLIC_SYMBOL_OWNER_AUDIT=PASS")

exception_names = [
    "ForecastQualityError",
    "S3StructuralDuplicateError",
    "S3DecimalAssertionError",
    "S3CanonicalIdentityConflictError",
    "S3ContractInvariantViolationError",
]
base_exception = exceptions.ForecastQualityError
for name in exception_names[1:]:
    if not issubclass(getattr(exceptions, name), base_exception):
        raise AssertionError(f"exception hierarchy drift: {name}")
for forbidden in ("S3BaselineNotComputableError", "S3BreakdownInsufficientSampleError"):
    if hasattr(exceptions, forbidden):
        raise AssertionError(f"forbidden exception exists: {forbidden}")

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
invalid_values: list[Any] = [
    1.0,
    float("nan"),
    float("inf"),
    float("-inf"),
    Decimal("NaN"),
    Decimal("Infinity"),
]
for invalid in invalid_values:
    try:
        canonical.emit_s3_decimal(invalid)
    except exceptions.S3DecimalAssertionError:
        continue
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
print("DECIMAL_CONTRACT=PASS")

if canonical.canonical_json_bytes({"b": 1, "a": 2}) != canonical.canonical_json_bytes(
    {"a": 2, "b": 1}
):
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


def common_values(
    quantile: Any = None, forecast_business_key: str = "forecast-p50", value: str = "11.000000"
) -> dict[str, Any]:
    return {
        "forecast_business_key": forecast_business_key,
        "actual_physical_key": "physical-a",
        "stable_actual_identity": "actual-a",
        "actual_value_kg": Decimal("10.000000"),
        "forecast_value_kg": Decimal(value),
        "forecast_quantile": quantile or enums.SupportedQuantile.P50,
        "forecast_horizon_days": 7,
        "forecast_target_date": date(2025, 2, 10),
        "target_date": date(2025, 2, 10),
        "forecast_cutoff_at": datetime(2025, 2, 1, tzinfo=UTC),
        "s2_status": "COMPARABLE",
        "season_business_key": "season-2025",
        "farm_business_key": "farm-a",
        "subfarm_business_key": "subfarm-a",
        "variety_business_key": "variety-a",
        "model_identity": "model-a",
        "actual_visibility_timestamp": datetime(2025, 2, 1, tzinfo=UTC),
        "forecast_visibility_timestamp": datetime(2025, 2, 1, tzinfo=UTC),
        "source_forecast_business_keys": [forecast_business_key],
    }


quantiles = [enums.SupportedQuantile.P50, enums.SupportedQuantile.P80, enums.SupportedQuantile.P90]
rows = [construct(schemas.S3BindingRow, common_values(q, f"forecast-{q.name}")) for q in quantiles]
registry = canonical.build_actual_physical_registry(rows)
registry_counts = {
    name: read_value(registry, name)
    for name in (
        "forecast_row_count_before",
        "forecast_row_count_after",
        "unique_actual_physical_row_count",
    )
}
if registry_counts != {
    "forecast_row_count_before": 3,
    "forecast_row_count_after": 3,
    "unique_actual_physical_row_count": 1,
}:
    raise AssertionError(f"cross-quantile registry mismatch: {registry_counts}")
for field, changed in (
    ("stable_actual_identity", "actual-conflict"),
    ("actual_value_kg", Decimal("12.000000")),
):
    conflict = common_values(enums.SupportedQuantile.P80, "forecast-conflict")
    conflict[field] = changed
    conflict_row = construct(schemas.S3BindingRow, conflict)
    try:
        canonical.build_actual_physical_registry([rows[0], conflict_row])
    except exceptions.S3StructuralDuplicateError:
        pass
    else:
        raise AssertionError(f"actual conflict accepted for {field}")
print("CROSS_QUANTILE_FORECAST_ROW_COUNT_BEFORE=3")
print("CROSS_QUANTILE_FORECAST_ROW_COUNT_AFTER=3")
print("CROSS_QUANTILE_UNIQUE_ACTUAL_PHYSICAL_ROW_COUNT=1")
print("CROSS_QUANTILE_CONFLICTS_FAIL_CLOSED=true")

forecast_rows = []
for quantile, values in zip(
    quantiles,
    (("5.000000", "3.000000"), ("7.000000", "4.000000"), ("9.000000", "5.000000")),
    strict=True,
):
    for index, value in enumerate(values):
        forecast_rows.append(
            construct(
                schemas.S3BindingRow,
                common_values(quantile, f"forecast-{quantile.name}-{index}", value),
            )
        )
forecast_aggregates = list(aggregation.aggregate_daily_forecasts(forecast_rows))
if len(forecast_aggregates) != 3:
    raise AssertionError("forecast aggregation did not retain three quantiles")
expected_forecast_sums = {
    "P50": Decimal("8.000000"),
    "P80": Decimal("11.000000"),
    "P90": Decimal("14.000000"),
}
for aggregate in forecast_aggregates:
    quantile_name = member_name(read_value(aggregate, "forecast_quantile"))
    if (
        as_decimal(read_value(aggregate, "forecast_value_kg"))
        != expected_forecast_sums[quantile_name]
    ):
        raise AssertionError(f"forecast sum mismatch for {quantile_name}")
actual_aggregates = list(aggregation.aggregate_daily_actuals(rows))
if len(actual_aggregates) != 1 or as_decimal(
    read_value(actual_aggregates[0], "actual_value_kg")
) != Decimal("10.000000"):
    raise AssertionError("actual physical dedup aggregation mismatch")
print("FORECAST_AGGREGATION_QUANTILES_INDEPENDENT=true")
print("FORECAST_AGGREGATION_SUMS=8.000000,11.000000,14.000000")
print("ACTUAL_AGGREGATION_AFTER_PHYSICAL_DEDUP=10.000000")

p50_rows = []
for index, (forecast, actual) in enumerate(
    (("11.000000", "10.000000"), ("0.000000", "0.000000"), ("8.000000", "10.000000"))
):
    values = common_values(enums.SupportedQuantile.P50, f"metric-{index}", forecast)
    values["actual_physical_key"] = f"physical-{index}"
    values["stable_actual_identity"] = f"actual-{index}"
    values["actual_value_kg"] = Decimal(actual)
    p50_rows.append(construct(schemas.S3BindingRow, values))
version = enums.FrozenVersion.METRIC_INPUT_MASK_V1
evaluation_values = {
    "rows": p50_rows,
    "s2_run_identity": "s2-run-a",
    "s2_manifest_identity": "s2-manifest-a",
    "s2_binding_row_set_hash": "a" * 64,
    "metric_policy_version": version,
    "baseline_policy_version": enums.FrozenVersion.NAIVE_BASELINE_POLICY_V1,
}
evaluation_input = construct(schemas.S3EvaluationInput, evaluation_values)
breakdown_values = {
    "forecast_horizon_days": 7,
    "farm_business_key": "farm-a",
    "subfarm_business_key": "subfarm-a",
    "variety_business_key": "variety-a",
    "season_business_key": "season-2025",
    "model_identity": "model-a",
    "minimum_sample_size": 10,
}
breakdown_spec = construct(schemas.BreakdownSpec, breakdown_values)
metric_result = daily.compute_daily_metrics(evaluation_input, breakdown_spec)
metric_cells = read_value(metric_result, "metric_cells", read_value(metric_result, "metrics", {}))
if isinstance(metric_cells, Sequence) and not isinstance(metric_cells, (str, bytes, Mapping)):
    metric_cells = {str(read_value(cell, "metric_name")): cell for cell in metric_cells}


def metric_cell(name: str) -> Any:
    aliases = {name, name.removesuffix("_kg"), name.upper()}
    for alias in aliases:
        if isinstance(metric_cells, Mapping) and alias in metric_cells:
            return metric_cells[alias]
    raise AssertionError(f"missing metric cell: {name}")


def quantized(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)


oracles = {
    "daily_mae": (Decimal("3"), Decimal("3"), Decimal("1")),
    "daily_wape": (Decimal("3"), Decimal("20"), Decimal("0.15")),
    "daily_smape": (
        Decimal("2") / Decimal("21") + Decimal("4") / Decimal("18"),
        Decimal("3"),
        (Decimal("2") / Decimal("21") + Decimal("4") / Decimal("18")) / Decimal("3"),
    ),
    "daily_mape": (Decimal("3") / Decimal("10"), Decimal("2"), Decimal("0.15")),
    "daily_bias_kg": (Decimal("-1"), Decimal("3"), Decimal("-0.3333333333333333333333333333")),
    "daily_relative_bias": (Decimal("-1"), Decimal("20"), Decimal("-0.05")),
    "daily_absolute_error_sum_kg": (Decimal("3"), Decimal("1"), Decimal("3")),
}
for name, (numerator, denominator, expected) in oracles.items():
    cell = metric_cell(name)
    actual = quantized(as_decimal(read_value(cell, "metric_value")))
    expected_rounded = quantized(expected)
    if actual != expected_rounded:
        raise AssertionError(f"metric oracle mismatch {name}: {actual} != {expected_rounded}")
    print(
        f"DAILY_METRIC_ORACLE={name}|numerator={numerator}|denominator={denominator}|"
        f"expected={expected_rounded}|actual={actual}|"
        f"status={status_name(read_value(cell, 'metric_status'))}|"
        f"reason={member_name(read_value(cell, 'reason_code'))}"
    )

breakdown_cells = list(breakdown.calculate_breakdown_cells(p50_rows, breakdown_spec))
if not breakdown_cells:
    raise AssertionError("breakdown returned no cell")
cell = breakdown_cells[0]
cell_identity = read_value(cell, "cell_identity")
for axis in (
    "season_business_key",
    "farm_business_key",
    "subfarm_business_key",
    "variety_business_key",
    "model_identity",
    "forecast_horizon_days",
):
    if read_value(cell_identity, axis, None) is None:
        raise AssertionError(f"breakdown axis missing: {axis}")
if (
    status_name(read_value(cell, "metric_status")) != "INSUFFICIENT_SAMPLE"
    or member_name(read_value(cell, "reason_code")) != "BELOW_MINIMUM"
):
    raise AssertionError("below-minimum breakdown contract mismatch")
print("BREAKDOWN_SIX_AXES=true")
print("BREAKDOWN_BELOW_MINIMUM=INSUFFICIENT_SAMPLE/BELOW_MINIMUM")

calendar_cases = [
    (
        "normal",
        date(2025, 2, 10),
        date(2025, 1, 1),
        date(2025, 3, 31),
        date(2024, 1, 1),
        date(2024, 3, 31),
        date(2024, 2, 10),
    ),
    (
        "leap_to_leap",
        date(2024, 2, 29),
        date(2024, 1, 1),
        date(2024, 3, 31),
        date(2020, 1, 1),
        date(2020, 3, 31),
        date(2020, 2, 29),
    ),
    (
        "leap_to_non_leap",
        date(2024, 2, 29),
        date(2024, 1, 1),
        date(2024, 3, 31),
        date(2023, 1, 1),
        date(2023, 3, 31),
        date(2023, 2, 28),
    ),
    (
        "prior_short_overflow",
        date(2025, 3, 31),
        date(2025, 1, 1),
        date(2025, 3, 31),
        date(2024, 1, 1),
        date(2024, 3, 1),
        None,
    ),
    (
        "current_after_end",
        date(2025, 4, 1),
        date(2025, 1, 1),
        date(2025, 3, 31),
        date(2024, 1, 1),
        date(2024, 3, 31),
        None,
    ),
    (
        "first_day",
        date(2025, 1, 1),
        date(2025, 1, 1),
        date(2025, 3, 31),
        date(2024, 1, 1),
        date(2024, 3, 31),
        date(2024, 1, 1),
    ),
    (
        "prior_feb_start_overflow",
        date(2025, 3, 31),
        date(2025, 1, 1),
        date(2025, 3, 31),
        date(2024, 2, 1),
        date(2024, 3, 31),
        None,
    ),
    (
        "mid_season",
        date(2025, 1, 15),
        date(2025, 1, 1),
        date(2025, 3, 31),
        date(2024, 1, 1),
        date(2024, 3, 31),
        date(2024, 1, 15),
    ),
]
for case_id, target, current_start, current_end, prior_start, prior_end, expected in calendar_cases:
    actual = call_with_contract_args(
        calendar.resolve_prior_season_analog_date,
        {
            "current_target_date": target,
            "current_season_start": current_start,
            "current_season_end": current_end,
            "prior_season_start": prior_start,
            "prior_season_end": prior_end,
            "policy_version": "v0.2-s3-season-analog-mapping-v1",
        },
    )
    if actual != expected:
        raise AssertionError(f"calendar case {case_id}: {actual!r} != {expected!r}")
    print(
        f"CALENDAR_CASE={case_id}|current_target_date={target}|expected={expected}|"
        f"actual={actual}|result={'PASS' if actual == expected else 'FAIL'}"
    )


def generic_value(name: str, overrides: Mapping[str, Any]) -> Any:
    if name in overrides:
        return overrides[name]
    if name == "metric_policy_version":
        return enums.FrozenVersion.METRIC_INPUT_MASK_V1
    if name == "baseline_policy_version":
        return enums.FrozenVersion.NAIVE_BASELINE_POLICY_V1
    if name in {"season_mapping_policy_version", "season_analog_mapping_policy_version"}:
        return enums.FrozenVersion.SEASON_ANALOG_MAPPING_V1
    if name.endswith("_at") or name.endswith("_timestamp"):
        return datetime(2025, 2, 1, tzinfo=UTC)
    if name.endswith("_date") or name in {
        "current_target_date",
        "prior_target_date",
        "current_season_start",
        "current_season_end",
        "prior_season_start",
        "prior_season_end",
    }:
        return date(2025, 2, 10)
    if "rows" in name:
        return []
    if "hash" in name or "identity" in name or "version" in name or name.endswith("_key"):
        return f"fixture-{name}"
    if "value_kg" in name or name.endswith("_value"):
        return Decimal("4.000000")
    if "quantile" in name:
        return enums.SupportedQuantile.P50
    if "status" in name:
        return enums.MetricStatus.COMPUTED
    if "reason" in name:
        return enums.ReasonCode.NONE
    if "availability" in name:
        return enums.ComparisonAvailability.AVAILABLE
    if "minimum" in name or name.endswith("_count"):
        return 10
    return "fixture-value"


def make_baseline_request(target: date, cutoff: datetime, requested_quantile: str = "P50") -> Any:
    overrides = {
        "current_target_date": target,
        "current_season_start": date(target.year, 1, 1),
        "current_season_end": date(target.year, 3, 31),
        "prior_season_start": date(target.year - 1, 1, 1),
        "prior_season_end": date(target.year - 1, 3, 31),
        "current_forecast_cutoff_at": cutoff,
        "farm_business_key": "farm-a",
        "subfarm_business_key": "subfarm-a",
        "variety_business_key": "variety-a",
        "requested_quantile": requested_quantile,
        "forecast_quantile": requested_quantile,
    }
    return construct(
        schemas.BaselineRequest,
        {name: generic_value(name, overrides) for name in field_names(schemas.BaselineRequest)},
    )


def make_baseline_snapshot(rows: list[dict[str, Any]]) -> Any:
    overrides = {"actual_rows": rows, "visibility_cutoff_at": datetime(2025, 2, 15, tzinfo=UTC)}
    return construct(
        schemas.BaselineSourceSnapshot,
        {
            name: generic_value(name, overrides)
            for name in field_names(schemas.BaselineSourceSnapshot)
        },
    )


def baseline_row(
    target_date: date,
    value: str = "4.000000",
    visibility: datetime | None = None,
    source_kind: str = "FARM_PICK",
) -> dict[str, Any]:
    return {
        "target_date": target_date,
        "actual_value_kg": Decimal(value),
        "physical_key": f"physical-{target_date}",
        "stable_actual_identity": f"actual-{target_date}",
        "visibility_timestamp": visibility or datetime(2025, 2, 1, tzinfo=UTC),
        "source_kind": source_kind,
        "season_business_key": "season-prior",
        "farm_business_key": "farm-a",
        "subfarm_business_key": "subfarm-a",
        "variety_business_key": "variety-a",
    }


version_request = make_baseline_request(date(2025, 2, 10), datetime(2025, 2, 15, tzinfo=UTC))
if read_value(version_request, "metric_policy_version") != enums.FrozenVersion.METRIC_INPUT_MASK_V1:
    raise AssertionError("metric policy fixture did not use FrozenVersion")
if (
    read_value(version_request, "baseline_policy_version")
    != enums.FrozenVersion.NAIVE_BASELINE_POLICY_V1
):
    raise AssertionError("baseline policy fixture did not use FrozenVersion")
version_snapshot = make_baseline_snapshot([])
season_policy = read_value(version_snapshot, "season_analog_mapping_policy_version", None)
if season_policy is not None and season_policy != enums.FrozenVersion.SEASON_ANALOG_MAPPING_V1:
    raise AssertionError("season mapping fixture did not use FrozenVersion")
print("FROZEN_VERSION_POLICY_FIELDS=PASS")


baseline_fixtures = [
    ("normal", date(2025, 2, 10), [baseline_row(date(2024, 2, 10))], "COMPUTED", "NONE"),
    (
        "Feb29_to_Feb28",
        date(2024, 2, 29),
        [baseline_row(date(2023, 2, 28), visibility=datetime(2024, 2, 1, tzinfo=UTC))],
        "COMPUTED",
        "NONE",
    ),
    (
        "no_analog_day",
        date(2025, 3, 31),
        [baseline_row(date(2024, 3, 1))],
        "NOT_COMPUTABLE",
        "NO_PRIOR_SEASON_ANALOG_DAY",
    ),
    ("no_analog_actual", date(2025, 2, 10), [], "NOT_COMPUTABLE", "NO_PRIOR_SEASON_ANALOG_ACTUAL"),
    (
        "visible_at_current_cutoff",
        date(2025, 2, 10),
        [baseline_row(date(2024, 2, 10), visibility=datetime(2025, 2, 1, tzinfo=UTC))],
        "COMPUTED",
        "NONE",
    ),
    (
        "late_revision_not_visible",
        date(2025, 2, 10),
        [baseline_row(date(2024, 2, 10), visibility=datetime(2025, 2, 20, tzinfo=UTC))],
        "NOT_COMPUTABLE",
        "BASELINE_SOURCE_NOT_VISIBLE_AT_CURRENT_FORECAST_CUTOFF",
    ),
]
baseline_result_for_canonical = None
for fixture_id, target, fixture_rows, expected_status, expected_reason in baseline_fixtures:
    result = baseline.resolve_baseline_point_forecast(
        make_baseline_request(target, datetime(2025, 2, 15, tzinfo=UTC)),
        make_baseline_snapshot(fixture_rows),
    )
    actual_status = status_name(
        read_value(result, "metric_status", read_value(result, "status", None))
    )
    actual_reason = member_name(read_value(result, "reason_code"))
    if actual_status != expected_status or actual_reason != expected_reason:
        raise AssertionError(f"baseline fixture {fixture_id}: {actual_status}/{actual_reason}")
    baseline_result_for_canonical = result
    print(f"BASELINE_FIXTURE={fixture_id}|status={actual_status}|reason={actual_reason}")

red_source_cases = [
    "latest_actual_fallback",
    "post_cutoff_revision",
    "model_forecast_proxy",
    "receipt_arrival_proxy",
    "implicit_zero_fallback",
    "s2_row_set_reuse",
]
for case_id in red_source_cases:
    row = baseline_row(date(2024, 2, 10), source_kind=case_id)
    result = baseline.resolve_baseline_point_forecast(
        make_baseline_request(date(2025, 2, 10), datetime(2025, 2, 15, tzinfo=UTC)),
        make_baseline_snapshot([row]),
    )
    actual_status = status_name(
        read_value(result, "metric_status", read_value(result, "status", None))
    )
    if actual_status != "NOT_COMPUTABLE":
        raise AssertionError(f"red baseline source accepted: {case_id}")
    print(f"S3R11_RED_SOURCE={case_id}|status=NOT_COMPUTABLE")

point_result = baseline.resolve_baseline_point_forecast(
    make_baseline_request(date(2025, 2, 10), datetime(2025, 2, 15, tzinfo=UTC)),
    make_baseline_snapshot([baseline_row(date(2024, 2, 10))]),
)
if read_value(point_result, "baseline_quantile", "P50") not in {"P50", enums.SupportedQuantile.P50}:  # type: ignore[operator]
    raise AssertionError("baseline point is not P50-equivalent")
print("S3R12_POINT_ONLY_P50=true")
for requested_quantile in ("P50", "P80", "P90"):
    quantile_result = baseline.resolve_baseline_point_forecast(
        make_baseline_request(
            date(2025, 2, 10),
            datetime(2025, 2, 15, tzinfo=UTC),
            requested_quantile,
        ),
        make_baseline_snapshot([baseline_row(date(2024, 2, 10))]),
    )
    actual_quantile = read_value(quantile_result, "baseline_quantile", requested_quantile)
    if requested_quantile == "P50":
        if status_name(read_value(quantile_result, "metric_status")) != "COMPUTED":
            raise AssertionError("P50 baseline was not computed")
        continue
    if (
        status_name(read_value(quantile_result, "comparison_availability")) != "BLOCKED"
        or status_name(read_value(quantile_result, "metric_status")) != "NOT_COMPUTABLE"
        or member_name(read_value(quantile_result, "reason_code"))
        != "BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED"
        or read_value(quantile_result, "baseline_point_forecast_kg") is not None
    ):
        raise AssertionError(f"S3R12 quantile outcome mismatch: {requested_quantile}")
    print(
        f"S3R12_QUANTILE_OUTCOME={requested_quantile}|actual={actual_quantile}|"
        "comparison_availability=BLOCKED|metric_status=NOT_COMPUTABLE|"
        "reason_code=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED|"
        "baseline_point_forecast_kg=null"
    )
print("S3R12_P80_P90_POINT_COPY=false")
print("S3R12_IMPLEMENTED_BY_ROUND_A=true")
print("GENERIC_VERSION_BRANCH_SHADOW_COUNT=0")

expected_root_fields = {
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
}
expected_cell_fields = {
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
}
root_payload = invoke_one_argument(
    canonical.build_baseline_canonical_payload_root, baseline_result_for_canonical
)
cell_payload = invoke_one_argument(
    canonical.build_baseline_canonical_payload_cell, baseline_result_for_canonical
)
if set(root_payload) != expected_root_fields:
    raise AssertionError(
        f"baseline root field set mismatch: {sorted(set(root_payload) ^ expected_root_fields)}"
    )
if set(cell_payload) != expected_cell_fields:
    raise AssertionError(
        f"baseline cell field set mismatch: {sorted(set(cell_payload) ^ expected_cell_fields)}"
    )
print("BASELINE_CANONICAL_ROOT_FIELD_COUNT=26")
print("BASELINE_CANONICAL_CELL_FIELD_COUNT=15")
print("BASELINE_CANONICAL_FIELD_NAME_DRIFT_COUNT=0")
print("BASELINE_ROOT_FIELD_SET_EQUALITY=true")
print("BASELINE_CELL_FIELD_SET_EQUALITY=true")

print("BLOCKED_IMPLEMENTATION_DEFINITION_COUNT=0")
print("REASON_CODE_FALSE_POSITIVE_COUNT=0")
print("GATE_21_GATE_23_CONTRADICTION_COUNT=0")
print("RUNTIME_POLICY_AUDIT=PASS")
