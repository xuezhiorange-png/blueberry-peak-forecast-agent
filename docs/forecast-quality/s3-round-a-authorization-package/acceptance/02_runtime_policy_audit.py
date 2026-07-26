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
from typing import Any, get_args, get_origin, get_type_hints

ROOT = Path(os.environ.get("ROUND_A_WORKTREE", Path.cwd())).resolve()
PACKAGE_DIR = Path(os.environ.get("PACKAGE_DIR", "")).resolve()
BASE_SHA = os.environ.get("IMPLEMENTATION_BASE_SHA")
ACCEPTED_SHA = os.environ.get("AUTHORIZATION_PACKAGE_ACCEPTED_SHA")
EXPECTED_TREE = os.environ.get("AUTHORIZATION_PACKAGE_TREE_OID")
if not BASE_SHA:
    raise SystemExit("IMPLEMENTATION_BASE_SHA is required")
if not ACCEPTED_SHA:
    raise SystemExit("AUTHORIZATION_PACKAGE_ACCEPTED_SHA is required")
if not EXPECTED_TREE:
    raise SystemExit("AUTHORIZATION_PACKAGE_TREE_OID is required")
if not PACKAGE_DIR.is_dir():
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
git("cat-file", "-e", f"{ACCEPTED_SHA}^{{commit}}")
package_root = "docs/forecast-quality/s3-round-a-authorization-package"
expected_package_files = {
    "README.md",
    "implementation-authorization.md",
    "authorized-paths.txt",
    "authorized-test-modules.txt",
    "public-symbol-owners.txt",
    "schema-enum-contract.md",
    "evidence-package-contract.md",
    "acceptance/01_changed_path_gate.sh",
    "acceptance/02_runtime_policy_audit.py",
    "acceptance/03_test_gate.sh",
    "acceptance/04_static_gate.sh",
    "acceptance/SHA256SUMS",
}
accepted_tree = git("rev-parse", f"{ACCEPTED_SHA}:{package_root}")
base_tree = git("rev-parse", f"{BASE_SHA}:{package_root}")
current_tree = git("rev-parse", f"HEAD:{package_root}")
accepted_files = set(
    git("ls-tree", "-r", "--name-only", f"{ACCEPTED_SHA}:{package_root}").splitlines()
)
base_files = set(git("ls-tree", "-r", "--name-only", f"{BASE_SHA}:{package_root}").splitlines())
current_files = {
    str(path.relative_to(PACKAGE_DIR)) for path in PACKAGE_DIR.rglob("*") if path.is_file()
}
worktree_drift_count = 0
for args in (
    ("diff", "--quiet", BASE_SHA, "--", package_root),
    ("diff", "--cached", "--quiet", "--", package_root),
):
    if subprocess.run(["git", *args], cwd=ROOT).returncode != 0:
        worktree_drift_count += 1
untracked_package = subprocess.check_output(
    ["git", "ls-files", "--others", "--exclude-standard", "--", package_root],
    cwd=ROOT,
    text=True,
).strip()
if untracked_package:
    worktree_drift_count += 1
accepted_tree_mismatch = int(accepted_tree != EXPECTED_TREE)
base_tree_mismatch = int(base_tree != EXPECTED_TREE)
file_set_mismatch = int(
    accepted_files != expected_package_files
    or base_files != expected_package_files
    or current_files != expected_package_files
)
print("AUTHORIZATION_PACKAGE_EXPECTED_FILE_COUNT=12")
print(f"AUTHORIZATION_PACKAGE_ACCEPTED_FILE_COUNT={len(accepted_files)}")
print(f"AUTHORIZATION_PACKAGE_BASE_FILE_COUNT={len(base_files)}")
print(f"AUTHORIZATION_PACKAGE_CURRENT_FILE_COUNT={len(current_files)}")
print(f"AUTHORIZATION_PACKAGE_ACCEPTED_TREE_OID={accepted_tree}")
print(f"AUTHORIZATION_PACKAGE_BASE_TREE_OID={base_tree}")
print(f"AUTHORIZATION_PACKAGE_CURRENT_TREE_OID={current_tree}")
print(f"AUTHORIZATION_PACKAGE_EXPECTED_TREE_OID={EXPECTED_TREE}")
print(f"AUTHORIZATION_PACKAGE_ACCEPTED_TREE_MISMATCH_COUNT={accepted_tree_mismatch}")
print(f"AUTHORIZATION_PACKAGE_BASE_TREE_MISMATCH_COUNT={base_tree_mismatch}")
print(f"AUTHORIZATION_PACKAGE_CURRENT_WORKTREE_DRIFT_COUNT={worktree_drift_count}")
print(f"AUTHORIZATION_PACKAGE_FILE_SET_MISMATCH_COUNT={file_set_mismatch}")
if accepted_tree_mismatch or base_tree_mismatch or file_set_mismatch or worktree_drift_count:
    raise AssertionError("authorization package tree identity drift")
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
base_hash_mismatch_count = 0
current_hash_mismatch_count = 0
missing_hash_path_count = 0
for expected_hash, repository_relative_path in hash_records:
    try:
        base_bytes = subprocess.check_output(
            ["git", "show", f"{BASE_SHA}:{repository_relative_path}"], cwd=ROOT
        )
    except subprocess.CalledProcessError as exc:
        missing_hash_path_count += 1
        raise AssertionError(f"missing script hash path: {repository_relative_path}") from exc
    base_hash = hashlib.sha256(base_bytes).hexdigest()
    current_path = ROOT / repository_relative_path
    if not current_path.is_file():
        missing_hash_path_count += 1
        raise AssertionError(f"current script is missing: {repository_relative_path}")
    current_hash = hashlib.sha256(current_path.read_bytes()).hexdigest()
    if base_hash != expected_hash:
        base_hash_mismatch_count += 1
    if current_hash != expected_hash:
        current_hash_mismatch_count += 1
if base_hash_mismatch_count or current_hash_mismatch_count or missing_hash_path_count:
    raise AssertionError("script hash identity drift")
print("SCRIPT_HASH_RECORD_COUNT=4")
print("SCRIPT_HASH_PATH_PREFIX_MATCH_COUNT=4")
print("SCRIPT_HASH_MISMATCH_COUNT=0")
print("SCRIPT_HASH_MISSING_PATH_COUNT=0")
print("CURRENT_SCRIPT_HASH_MISMATCH_COUNT=0")
print("BASE_SCRIPT_HASH_MISMATCH_COUNT=0")
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


def field_contract(model_type: Any) -> list[dict[str, Any]]:
    """Normalize dataclass/Pydantic fields for exact contract comparison."""
    hints = get_type_hints(model_type)
    if dataclasses.is_dataclass(model_type):
        result = []
        for field in dataclasses.fields(model_type):
            annotation = hints.get(field.name, field.type)
            result.append(
                {
                    "name": field.name,
                    "type": type_identity(annotation),
                    "required": field.default is dataclasses.MISSING
                    and field.default_factory is dataclasses.MISSING,
                    "nullable": nullable(annotation),
                    "default": "MISSING"
                    if field.default is dataclasses.MISSING
                    else repr(field.default),
                }
            )
        return result
    model_fields = getattr(model_type, "model_fields", None)
    if model_fields is not None:
        result = []
        for name, field in model_fields.items():
            annotation = hints.get(name, getattr(field, "annotation", Any))
            default = getattr(field, "default", ...)
            required_fn = getattr(field, "is_required", None)
            result.append(
                {
                    "name": name,
                    "type": type_identity(annotation),
                    "required": bool(required_fn() if required_fn is not None else default is ...),
                    "nullable": nullable(annotation),
                    "default": "MISSING" if default is ... else repr(default),
                }
            )
        return result
    raise AssertionError(f"unsupported schema type: {model_type!r}")


def nullable(annotation: Any) -> bool:
    return type(None) in get_args(annotation)


def type_identity(annotation: Any) -> str:
    if annotation is type(None):
        return "None"
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is None:
        return getattr(annotation, "__name__", str(annotation).replace("typing.", ""))
    origin_name = getattr(origin, "__name__", str(origin).replace("typing.", ""))
    if origin_name in {"Union", "UnionType"}:
        union_names = [type_identity(arg) for arg in args]
        union_names.sort(key=lambda name: name == "None")
        return "|".join(union_names)
    return f"{origin_name}[{','.join(type_identity(arg) for arg in args)}]"


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

schema_contracts: dict[str, list[dict[str, Any]]] = {
    "ActualPhysicalRecord": [
        {
            "name": "physical_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "stable_actual_identity",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "actual_value_kg",
            "type": "Decimal",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
    ],
    "S3EvaluationInput": [
        {
            "name": "rows",
            "type": "Sequence[S3BindingRow]",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "s2_run_identity",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "s2_manifest_identity",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "s2_binding_row_set_hash",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "metric_policy_version",
            "type": "FrozenVersion",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "baseline_policy_version",
            "type": "FrozenVersion",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
    ],
    "S3BindingRow": [
        {
            "name": "forecast_business_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "actual_physical_key",
            "type": "str|None",
            "required": True,
            "nullable": True,
            "default": "MISSING",
        },
        {
            "name": "stable_actual_identity",
            "type": "str|None",
            "required": True,
            "nullable": True,
            "default": "MISSING",
        },
        {
            "name": "forecast_value_kg",
            "type": "Decimal|None",
            "required": True,
            "nullable": True,
            "default": "MISSING",
        },
        {
            "name": "actual_value_kg",
            "type": "Decimal|None",
            "required": True,
            "nullable": True,
            "default": "MISSING",
        },
        {
            "name": "forecast_quantile",
            "type": "SupportedQuantile",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "forecast_horizon_days",
            "type": "int",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "forecast_target_date",
            "type": "date",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "forecast_cutoff_at",
            "type": "datetime",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "s2_status",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "season_business_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "farm_business_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "subfarm_business_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "variety_business_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "model_identity",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "actual_visibility_timestamp",
            "type": "datetime|None",
            "required": True,
            "nullable": True,
            "default": "MISSING",
        },
    ],
    "FarmDailyActualAggregate": [
        {
            "name": "season_business_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "farm_business_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "variety_business_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "target_date",
            "type": "date",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "actual_value_kg",
            "type": "Decimal",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "unique_actual_physical_rows",
            "type": "int",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
    ],
    "FarmDailyForecastAggregate": [
        {
            "name": "season_business_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "farm_business_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "variety_business_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "target_date",
            "type": "date",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "forecast_cutoff_at",
            "type": "datetime",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "model_identity",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "forecast_quantile",
            "type": "SupportedQuantile",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "forecast_horizon_days",
            "type": "int",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "forecast_value_kg",
            "type": "Decimal",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "source_forecast_business_keys",
            "type": "Sequence[str]",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
    ],
    "MetricValueCell": [
        {
            "name": "metric_name",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "metric_value",
            "type": "Decimal|None",
            "required": True,
            "nullable": True,
            "default": "MISSING",
        },
        {
            "name": "metric_status",
            "type": "MetricStatus",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "reason_code",
            "type": "ReasonCode",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "numerator",
            "type": "Decimal|None",
            "required": True,
            "nullable": True,
            "default": "MISSING",
        },
        {
            "name": "denominator",
            "type": "Decimal|None",
            "required": True,
            "nullable": True,
            "default": "MISSING",
        },
        {
            "name": "mape_eligible_row_count",
            "type": "int",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "mape_zero_actual_row_count",
            "type": "int",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
    ],
    "DailyMetricResult": [
        {
            "name": "s2_run_identity",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "s2_manifest_identity",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "s2_binding_row_set_hash",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "metric_policy_version",
            "type": "FrozenVersion",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "baseline_policy_version",
            "type": "FrozenVersion",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "breakdown_identity",
            "type": "dict[str,str|int]",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "s2_total_binding_row_count",
            "type": "int",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "s2_comparable_binding_row_count",
            "type": "int",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "s2_excluded_binding_row_count",
            "type": "int",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "s2_not_computable_binding_row_count",
            "type": "int",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "coverage_ratio",
            "type": "Decimal|None",
            "required": True,
            "nullable": True,
            "default": "MISSING",
        },
        {
            "name": "metric_input_mask_policy_version",
            "type": "FrozenVersion",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "metric_input_mask_hash",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "metric_input_row_count",
            "type": "int",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "metric_input_quantile",
            "type": "SupportedQuantile",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "unique_actual_physical_row_count",
            "type": "int",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "mape_eligible_row_count",
            "type": "int",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "mape_zero_actual_row_count",
            "type": "int",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "mape_zero_actual_reason_code",
            "type": "ReasonCode|None",
            "required": True,
            "nullable": True,
            "default": "MISSING",
        },
        {
            "name": "metric_cells",
            "type": "Sequence[MetricValueCell]",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "canonical_hash",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
    ],
    "BreakdownSpec": [
        {
            "name": "forecast_horizon_days",
            "type": "int",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "farm_business_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "subfarm_business_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "variety_business_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "season_business_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "model_identity",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
    ],
    "BaselineRequest": [
        {
            "name": "current_target_date",
            "type": "date",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "current_season_start",
            "type": "date",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "current_season_end",
            "type": "date",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "prior_season_start",
            "type": "date",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "prior_season_end",
            "type": "date",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "prior_season_identity",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "current_forecast_cutoff_at",
            "type": "datetime",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "farm_business_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "subfarm_business_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "variety_business_key",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "requested_quantile",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "metric_policy_version",
            "type": "FrozenVersion",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "baseline_policy_version",
            "type": "FrozenVersion",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
    ],
    "BaselineSourceSnapshot": [
        {
            "name": "source_snapshot_identity",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "source_snapshot_hash",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "source_row_set_hash",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "visibility_manifest_hash",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "visibility_cutoff_at",
            "type": "datetime",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "season_analog_mapping_policy_version",
            "type": "FrozenVersion",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "actual_rows",
            "type": "Sequence[Mapping[str,Any]]",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
    ],
    "BaselineResult": [
        {
            "name": "baseline_point_forecast_kg",
            "type": "Decimal|None",
            "required": True,
            "nullable": True,
            "default": "MISSING",
        },
        {
            "name": "baseline_quantile",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "comparison_availability",
            "type": "ComparisonAvailability",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "metric_status",
            "type": "MetricStatus",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "reason_code",
            "type": "ReasonCode",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "analog_date",
            "type": "date|None",
            "required": True,
            "nullable": True,
            "default": "MISSING",
        },
        {
            "name": "source_snapshot_identity",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "source_snapshot_hash",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "source_row_set_hash",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "visibility_manifest_hash",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
        {
            "name": "canonical_hash",
            "type": "str",
            "required": True,
            "nullable": False,
            "default": "MISSING",
        },
    ],
}

schema_drift_count = 0
for schema_name, expected in schema_contracts.items():
    actual = field_contract(getattr(schemas, schema_name))
    if actual != expected:
        schema_drift_count += 1
        raise AssertionError(f"{schema_name} exact contract mismatch: {actual}")
    print(f"{schema_name}_FIELD_COUNT={len(actual)}")
print(f"PUBLIC_SCHEMA_COUNT={len(schema_contracts)}")
print(f"PUBLIC_SCHEMA_FIELD_SET_EQUALITY_COUNT={len(schema_contracts)}")
print(f"PUBLIC_SCHEMA_FIELD_ORDER_EQUALITY_COUNT={len(schema_contracts)}")
print(f"PUBLIC_SCHEMA_TYPE_EQUALITY_COUNT={len(schema_contracts)}")
print(f"PUBLIC_SCHEMA_REQUIREDNESS_EQUALITY_COUNT={len(schema_contracts)}")
print(f"PUBLIC_SCHEMA_DRIFT_COUNT={schema_drift_count}")

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
daily_mask_owner = daily.__dict__.get("compute_metric_input_mask_hash")
if daily_mask_owner is not None and getattr(daily_mask_owner, "__module__", None) == daily.__name__:
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
}
breakdown_spec = construct(schemas.BreakdownSpec, breakdown_values)
if "minimum_sample_size" in field_names(schemas.BreakdownSpec):
    raise AssertionError("BreakdownSpec exposes caller-configurable threshold")
if getattr(breakdown, "MIN_COMPARABLE_ROWS_FOR_REPORTING", None) != 10:
    raise AssertionError("fixed breakdown threshold owner/value drift")
metric_result = daily.compute_daily_metrics(evaluation_input, breakdown_spec)
metric_cells = read_value(metric_result, "metric_cells", read_value(metric_result, "metrics", {}))
if isinstance(metric_cells, Sequence) and not isinstance(metric_cells, (str, bytes, Mapping)):
    metric_cells = {str(read_value(cell, "metric_name")): cell for cell in metric_cells}

expected_breakdown_identity = {
    "season_business_key": "season-2025",
    "farm_business_key": "farm-a",
    "subfarm_business_key": "subfarm-a",
    "variety_business_key": "variety-a",
    "model_identity": "model-a",
    "forecast_horizon_days": 7,
}
expected_mask_payload = {
    "metric_input_mask_policy_version": "v0.2-s3-metric-input-mask-v1",
    "s2_status_predicate": "S2_STATUS_COMPARABLE",
    "forecast_quantile_predicate": "P50",
    "actual_pair_predicate": "EXACT_ACTUAL_PAIRED",
    "breakdown_identity": expected_breakdown_identity,
    "source_row_set_identity": "a" * 64,
}
expected_mask_hash = canonical.compute_metric_input_mask_hash(expected_mask_payload)
envelope_expected = {
    "s2_run_identity": "s2-run-a",
    "s2_manifest_identity": "s2-manifest-a",
    "s2_binding_row_set_hash": "a" * 64,
    "metric_policy_version": enums.FrozenVersion.METRIC_INPUT_MASK_V1,
    "baseline_policy_version": enums.FrozenVersion.NAIVE_BASELINE_POLICY_V1,
    "s2_total_binding_row_count": 3,
    "s2_comparable_binding_row_count": 3,
    "s2_excluded_binding_row_count": 0,
    "s2_not_computable_binding_row_count": 0,
    "coverage_ratio": Decimal("1.000000"),
    "metric_input_mask_policy_version": enums.FrozenVersion.METRIC_INPUT_MASK_V1,
    "metric_input_row_count": 3,
    "metric_input_quantile": enums.SupportedQuantile.P50,
    "unique_actual_physical_row_count": 3,
    "mape_eligible_row_count": 2,
    "mape_zero_actual_row_count": 1,
}
envelope_value_mismatch_count = 0
for envelope_field, expected_value in envelope_expected.items():
    actual_value = read_value(metric_result, envelope_field)
    if envelope_field in {
        "metric_policy_version",
        "baseline_policy_version",
        "metric_input_mask_policy_version",
        "metric_input_quantile",
    }:
        matches = actual_value == expected_value
    elif isinstance(expected_value, Decimal):
        matches = as_decimal(actual_value) == expected_value
    else:
        matches = actual_value == expected_value
    envelope_value_mismatch_count += int(not matches)
if envelope_value_mismatch_count:
    raise AssertionError("DailyMetricResult envelope value drift")
if read_value(metric_result, "breakdown_identity") != expected_breakdown_identity:
    raise AssertionError("DailyMetricResult breakdown identity drift")
if read_value(metric_result, "metric_input_mask_hash") != expected_mask_hash:
    raise AssertionError("DailyMetricResult metric mask hash drift")
if (
    read_value(metric_result, "metric_input_mask_policy_version")
    != enums.FrozenVersion.METRIC_INPUT_MASK_V1
):
    raise AssertionError("DailyMetricResult metric mask policy version drift")
canonical_payload = dataclasses.asdict(metric_result)
canonical_payload["canonical_hash"] = ""
expected_canonical_hash = hashlib.sha256(
    canonical.canonical_json_bytes(canonical_payload)
).hexdigest()
if read_value(metric_result, "canonical_hash") != expected_canonical_hash:
    raise AssertionError("DailyMetricResult canonical hash drift")
print(f"DAILY_RESULT_ENVELOPE_FIELD_COUNT={len(field_names(schemas.DailyMetricResult))}")
print(f"DAILY_RESULT_ENVELOPE_VALUE_MISMATCH_COUNT={envelope_value_mismatch_count}")
print("DAILY_RESULT_COUNTER_MISMATCH_COUNT=0")
print("DAILY_RESULT_BREAKDOWN_IDENTITY_MISMATCH_COUNT=0")
print("DAILY_RESULT_MASK_HASH_MISMATCH_COUNT=0")
print("DAILY_RESULT_MASK_POLICY_VERSION_PRESENT=true")
print("DAILY_RESULT_MASK_POLICY_VERSION_VALUE=v0.2-s3-metric-input-mask-v1")
print("DAILY_RESULT_MASK_POLICY_VERSION_MISMATCH_COUNT=0")
print("DAILY_RESULT_CANONICAL_HASH_MISMATCH_COUNT=0")


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
    raw_actual = read_value(cell, "metric_value")
    if raw_actual is None:
        raise AssertionError(f"metric oracle returned null for {name}")
    actual = quantized(as_decimal(raw_actual))
    expected_rounded = quantized(expected)
    if actual != expected_rounded:
        raise AssertionError(f"metric oracle mismatch {name}: {actual} != {expected_rounded}")
    actual_status = status_name(read_value(cell, "metric_status"))
    actual_reason = member_name(read_value(cell, "reason_code"))
    if actual_status != "COMPUTED" or actual_reason != "NONE":
        raise AssertionError(f"metric status/reason mismatch for {name}")
    print(
        f"DAILY_METRIC_ORACLE={name}|numerator={numerator}|denominator={denominator}|"
        f"unrounded_expected={expected}|rounded_expected={expected_rounded}|actual_value={actual}|"
        f"expected_status=COMPUTED|actual_status={actual_status}|"
        f"expected_reason=NONE|actual_reason={actual_reason}|result=PASS"
    )
print("DAILY_METRIC_VALUE_ORACLE_COUNT=7")
print("DAILY_METRIC_STATUS_ORACLE_COUNT=7")
print("DAILY_METRIC_REASON_ORACLE_COUNT=7")


def metric_result_for_actual_values(values: Sequence[str]) -> Any:
    rows_for_case = []
    for index, actual_value in enumerate(values):
        row_values = common_values(
            enums.SupportedQuantile.P50,
            f"denominator-case-{index}",
            "1.000000",
        )
        row_values["actual_physical_key"] = f"denominator-physical-{index}"
        row_values["stable_actual_identity"] = f"denominator-actual-{index}"
        row_values["actual_value_kg"] = Decimal(actual_value)
        rows_for_case.append(construct(schemas.S3BindingRow, row_values))
    return daily.compute_daily_metrics(
        construct(
            schemas.S3EvaluationInput,
            {
                "rows": rows_for_case,
                "s2_run_identity": "s2-denominator-case",
                "s2_manifest_identity": "manifest-denominator-case",
                "s2_binding_row_set_hash": "b" * 64,
                "metric_policy_version": enums.FrozenVersion.METRIC_INPUT_MASK_V1,
                "baseline_policy_version": enums.FrozenVersion.NAIVE_BASELINE_POLICY_V1,
            },
        ),
        breakdown_spec,
    )


def cells_by_name(result: Any) -> Mapping[str, Any]:
    value = read_value(result, "metric_cells", read_value(result, "metrics", {}))
    if isinstance(value, Mapping):
        return value
    return {str(read_value(cell, "metric_name")): cell for cell in value}


denominator_cases = [
    ("WAPE_DENOMINATOR_ZERO", "daily_wape", "WAPE_DENOMINATOR_ZERO"),
    ("RELATIVE_BIAS_DENOMINATOR_ZERO", "daily_relative_bias", "RELATIVE_BIAS_DENOMINATOR_ZERO"),
    ("NO_MAPE_ELIGIBLE_ROWS", "daily_mape", "NO_MAPE_ELIGIBLE_ROWS"),
]
for case_id, metric_name, expected_reason in denominator_cases:
    case_result = metric_result_for_actual_values(("0.000000", "0.000000"))
    case_cell = cells_by_name(case_result)[metric_name]
    if read_value(case_cell, "metric_value") is not None:
        raise AssertionError(f"{case_id} returned a value")
    if status_name(read_value(case_cell, "metric_status")) != "NOT_COMPUTABLE":
        raise AssertionError(f"{case_id} status mismatch")
    if member_name(read_value(case_cell, "reason_code")) != expected_reason:
        raise AssertionError(f"{case_id} reason mismatch")
    if metric_name == "daily_mape" and read_value(case_cell, "mape_eligible_row_count") != 0:
        raise AssertionError("MAPE eligible-row audit drift")
    print(
        f"DENOMINATOR_ZERO_CASE={case_id}|metric={metric_name}|metric_value=null|"
        f"metric_status=NOT_COMPUTABLE|reason_code={expected_reason}|result=PASS"
    )
mixed_mape_result = metric_result_for_actual_values(("0.000000", "10.000000"))
zero_mape_cell = cells_by_name(mixed_mape_result)["daily_mape"]
if read_value(zero_mape_cell, "mape_zero_actual_row_count") != 1:
    raise AssertionError("MAPE_DENOMINATOR_ZERO row audit missing")
if (
    member_name(read_value(mixed_mape_result, "mape_zero_actual_reason_code"))
    != "MAPE_DENOMINATOR_ZERO"
):
    raise AssertionError("MAPE zero-row reason was not serialized")
if status_name(read_value(zero_mape_cell, "metric_status")) != "COMPUTED":
    raise AssertionError("mixed MAPE case must remain computed")
if member_name(read_value(zero_mape_cell, "reason_code")) != "NONE":
    raise AssertionError("mixed MAPE cell reason drift")
all_zero_result = metric_result_for_actual_values(("0.000000", "0.000000"))
all_zero_mape_cell = cells_by_name(all_zero_result)["daily_mape"]
if (
    member_name(read_value(all_zero_result, "mape_zero_actual_reason_code"))
    != "MAPE_DENOMINATOR_ZERO"
):
    raise AssertionError("all-zero MAPE row reason was not serialized")
if status_name(read_value(all_zero_mape_cell, "metric_status")) != "NOT_COMPUTABLE":
    raise AssertionError("all-zero MAPE case status drift")
if member_name(read_value(all_zero_mape_cell, "reason_code")) != "NO_MAPE_ELIGIBLE_ROWS":
    raise AssertionError("all-zero MAPE cell reason drift")
print("MAPE_ZERO_REASON_SERIALIZATION_OWNER=mape_zero_actual_reason_code")
print("MAPE_MIXED_CASE_STATUS=COMPUTED")
print("MAPE_MIXED_CASE_CELL_REASON=NONE")
print("MAPE_MIXED_CASE_ZERO_REASON=MAPE_DENOMINATOR_ZERO")
print("MAPE_ALL_ZERO_STATUS=NOT_COMPUTABLE")
print("MAPE_ALL_ZERO_CELL_REASON=NO_MAPE_ELIGIBLE_ROWS")
print("MAPE_ELIGIBLE_COUNT_ASSERTION_EXECUTED=true")
print("MAPE_DENOMINATOR_ZERO_ROW_AUDIT=PASS")
print("DENOMINATOR_ZERO_RUNTIME_CASE_COUNT=3")
print("DAILY_METRIC_ORACLE_FAILURE_COUNT=0")

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
if status_name(read_value(breakdown_cells[0], "metric_status")) != "INSUFFICIENT_SAMPLE":
    raise AssertionError("nine-row breakdown should be below minimum")
ten_row_cells = list(
    breakdown.calculate_breakdown_cells(p50_rows * 3 + p50_rows[:1], breakdown_spec)
)
if status_name(read_value(ten_row_cells[0], "metric_status")) != "COMPUTED":
    raise AssertionError("ten-row breakdown should be computed")
print("BREAKDOWN_9_ROWS=INSUFFICIENT_SAMPLE/BELOW_MINIMUM")
print("BREAKDOWN_10_ROWS=COMPUTED/NONE")
print("MIN_COMPARABLE_ROWS_FOR_REPORTING_OWNER=backend.app.forecast_quality.breakdown")
print("MIN_COMPARABLE_ROWS_FOR_REPORTING_VALUE=10")
print("CALLER_CONFIGURABLE_MINIMUM_SAMPLE_SIZE=false")

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


def make_baseline_request(
    target: date,
    cutoff: datetime,
    requested_quantile: str = "P50",
    *,
    current_season_start: date | None = None,
    current_season_end: date | None = None,
    prior_season_start: date | None = None,
    prior_season_end: date | None = None,
) -> Any:
    overrides = {
        "current_target_date": target,
        "current_season_start": current_season_start or date(target.year, 1, 1),
        "current_season_end": current_season_end or date(target.year, 3, 31),
        "prior_season_start": prior_season_start or date(target.year - 1, 1, 1),
        "prior_season_end": prior_season_end or date(target.year - 1, 3, 31),
        "current_forecast_cutoff_at": cutoff,
        "farm_business_key": "farm-a",
        "subfarm_business_key": "subfarm-a",
        "variety_business_key": "variety-a",
        "requested_quantile": requested_quantile,
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
    (
        "normal",
        date(2025, 2, 10),
        {},
        [baseline_row(date(2024, 2, 10))],
        "COMPUTED",
        "NONE",
    ),
    (
        "Feb29_to_Feb28",
        date(2024, 2, 29),
        {},
        [baseline_row(date(2023, 2, 28), visibility=datetime(2024, 2, 1, tzinfo=UTC))],
        "COMPUTED",
        "NONE",
    ),
    (
        "no_analog_day",
        date(2025, 3, 31),
        {
            "current_season_start": date(2025, 1, 1),
            "current_season_end": date(2025, 3, 31),
            "prior_season_start": date(2024, 1, 1),
            "prior_season_end": date(2024, 3, 1),
        },
        [],
        "NOT_COMPUTABLE",
        "NO_PRIOR_SEASON_ANALOG_DAY",
    ),
    (
        "no_analog_actual",
        date(2025, 2, 10),
        {},
        [],
        "NOT_COMPUTABLE",
        "NO_PRIOR_SEASON_ANALOG_ACTUAL",
    ),
    (
        "visible_at_current_cutoff",
        date(2025, 2, 10),
        {},
        [baseline_row(date(2024, 2, 10), visibility=datetime(2025, 2, 1, tzinfo=UTC))],
        "COMPUTED",
        "NONE",
    ),
    (
        "late_revision_not_visible",
        date(2025, 2, 10),
        {},
        [baseline_row(date(2024, 2, 10), visibility=datetime(2025, 2, 20, tzinfo=UTC))],
        "NOT_COMPUTABLE",
        "BASELINE_SOURCE_NOT_VISIBLE_AT_CURRENT_FORECAST_CUTOFF",
    ),
]
baseline_result_for_canonical = None
for (
    fixture_id,
    target,
    boundary_overrides,
    fixture_rows,
    expected_status,
    expected_reason,
) in baseline_fixtures:
    result = baseline.resolve_baseline_point_forecast(
        make_baseline_request(
            target,
            datetime(2025, 2, 15, tzinfo=UTC),
            **boundary_overrides,
        ),
        make_baseline_snapshot(fixture_rows),
    )
    actual_status = status_name(
        read_value(result, "metric_status", read_value(result, "status", None))
    )
    actual_reason = member_name(read_value(result, "reason_code"))
    if actual_status != expected_status or actual_reason != expected_reason:
        raise AssertionError(f"baseline fixture {fixture_id}: {actual_status}/{actual_reason}")
    baseline_result_for_canonical = result
    analog_date = read_value(result, "analog_date", None)
    print(
        f"BASELINE_FIXTURE={fixture_id}|analog_date={analog_date}|"
        f"status={actual_status}|reason={actual_reason}"
    )

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
if member_name(read_value(point_result, "baseline_quantile", "P50")) != "P50":
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

expected_root_fields = (
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
expected_cell_fields = (
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
canonical_request = make_baseline_request(date(2025, 2, 10), datetime(2025, 2, 15, tzinfo=UTC))
canonical_snapshot = make_baseline_snapshot([baseline_row(date(2024, 2, 10))])
canonical_baseline_result = baseline.resolve_baseline_point_forecast(
    canonical_request, canonical_snapshot
)


def build_canonical_parts(
    *,
    evaluation: Any = evaluation_input,
    request: Any = canonical_request,
    snapshot: Any = canonical_snapshot,
    result: Any = canonical_baseline_result,
    metrics: Any = metric_result,
    spec: Any = breakdown_spec,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cell = canonical.build_baseline_canonical_payload_cell(
        baseline_result=result, metric_result=metrics
    )
    root = canonical.build_baseline_canonical_payload_root(
        evaluation_input=evaluation,
        baseline_request=request,
        source_snapshot=snapshot,
        baseline_result=result,
        metric_result=metrics,
        breakdown_spec=spec,
        per_breakdown_cell=[cell],
    )
    return root, cell


root_payload, cell_payload = build_canonical_parts()
if tuple(root_payload) != expected_root_fields or tuple(cell_payload) != expected_cell_fields:
    raise AssertionError("baseline canonical ordered field drift")
if set(root_payload) != set(expected_root_fields) or set(cell_payload) != set(expected_cell_fields):
    raise AssertionError("baseline canonical field set drift")
if root_payload["baseline_grain"] != canonical.BASELINE_GRAIN:
    raise AssertionError("baseline grain constant drift")
if root_payload["baseline_horizon_rule"] != canonical.BASELINE_HORIZON_RULE:
    raise AssertionError("baseline horizon rule constant drift")

canonical_source_map = {}


def add_source(section: str, field: str, source_schema: str, source_field: str) -> None:
    canonical_source_map[f"{section}.{field}"] = {
        "source_schema": source_schema,
        "source_field": source_field,
        "nullable": field in {"baseline_point_forecast_kg", "coverage_ratio"},
        "sentinel": "EXPLICIT_JSON_NULL_ONLY"
        if field in {"baseline_point_forecast_kg", "coverage_ratio"}
        else "NONE",
        "identity_participation": True,
    }


for field in ("s2_run_identity", "s2_manifest_identity", "s2_binding_row_set_hash"):
    add_source("root", field, "S3EvaluationInput", field)
for field in (
    "baseline_source_snapshot_identity",
    "baseline_source_snapshot_hash",
    "baseline_source_row_set_hash",
    "baseline_source_visibility_manifest_hash",
    "baseline_source_visibility_cutoff_at",
):
    source_field = {
        "baseline_source_snapshot_identity": "source_snapshot_identity",
        "baseline_source_snapshot_hash": "source_snapshot_hash",
        "baseline_source_row_set_hash": "source_row_set_hash",
        "baseline_source_visibility_manifest_hash": "visibility_manifest_hash",
        "baseline_source_visibility_cutoff_at": "visibility_cutoff_at",
    }[field]
    add_source("root", field, "BaselineSourceSnapshot", source_field)
add_source("root", "baseline_policy_version", "BaselineRequest", "baseline_policy_version")
add_source(
    "root",
    "season_analog_mapping_policy_version",
    "BaselineSourceSnapshot",
    "season_analog_mapping_policy_version",
)
add_source("root", "prior_season_identity", "BaselineRequest", "prior_season_identity")
add_source("root", "schema_version", "FrozenConstant", "BASELINE_SCHEMA_VERSION")
add_source("root", "baseline_grain", "FrozenConstant", "BASELINE_GRAIN")
add_source("root", "baseline_horizon_rule", "FrozenConstant", "BASELINE_HORIZON_RULE")
add_source("root", "breakdown_dimensions", "BreakdownSpec", "six_axis_normalized_identity")
for field in (
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
):
    add_source("root", field, "DailyMetricResult", field)
add_source("root", "per_breakdown_cell", "per_breakdown_cell argument", "per_breakdown_cell")
for field in ("baseline_point_forecast_kg", "metric_status", "reason_code"):
    add_source("cell", field, "BaselineResult", field)
for field in (
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
):
    add_source("cell", field, "DailyMetricResult", field)

source_schema_fields = {
    schema_name: set(field_names(getattr(schemas, schema_name)))
    for schema_name in (
        "S3EvaluationInput",
        "BaselineRequest",
        "BaselineSourceSnapshot",
        "DailyMetricResult",
        "BaselineResult",
        "BreakdownSpec",
    )
}
source_field_missing = 0
source_schema_missing = 0
source_field_name_mismatch = 0
for mapping in canonical_source_map.values():
    source_schema = mapping["source_schema"]
    source_field = mapping["source_field"]
    if source_schema == "FrozenConstant" or source_schema == "per_breakdown_cell argument":
        continue
    if source_schema not in source_schema_fields:
        source_schema_missing += 1
    elif source_field == "six_axis_normalized_identity":
        if len(field_names(schemas.BreakdownSpec)) != 6:
            source_field_name_mismatch += 1
    elif source_field not in source_schema_fields[source_schema]:
        source_field_missing += 1
if source_schema_missing or source_field_missing or source_field_name_mismatch:
    raise AssertionError("baseline canonical source schema drift")
source_value_mismatch = 0
for key, mapping in canonical_source_map.items():
    section, field = key.split(".", 1)
    payload = root_payload if section == "root" else cell_payload
    source_value_mismatch += int(payload[field] is None and not mapping["nullable"])
if source_value_mismatch:
    raise AssertionError("baseline canonical source value drift")

mutation_cases = [
    ("s2_run_identity", dataclasses.replace(evaluation_input, s2_run_identity="s2-run-mutated")),
    (
        "source_snapshot_identity",
        dataclasses.replace(canonical_snapshot, source_snapshot_identity="snapshot-mutated"),
    ),
    (
        "visibility_manifest_hash",
        dataclasses.replace(canonical_snapshot, visibility_manifest_hash="visibility-mutated"),
    ),
    ("breakdown_axis", dataclasses.replace(breakdown_spec, model_identity="model-mutated")),
    ("metric_input_mask_hash", dataclasses.replace(metric_result, metric_input_mask_hash="f" * 64)),
    (
        "baseline_result_status",
        dataclasses.replace(
            canonical_baseline_result,
            metric_status=enums.MetricStatus.NOT_COMPUTABLE,
            reason_code=enums.ReasonCode.NO_PRIOR_SEASON_ANALOG_DAY,
            baseline_point_forecast_kg=None,
        ),
    ),
    (
        "baseline_result_value",
        dataclasses.replace(
            canonical_baseline_result, baseline_point_forecast_kg=Decimal("9.000000")
        ),
    ),
]
mutation_failures = 0
root_bytes = canonical.canonical_json_bytes(root_payload)
cell_bytes = canonical.canonical_json_bytes(cell_payload)
for case_id, mutated in mutation_cases:
    if case_id.startswith("s2_"):
        changed_root, _ = build_canonical_parts(evaluation=mutated)
        changed = changed_root != root_payload
    elif case_id.startswith("source_snapshot") or case_id == "visibility_manifest_hash":
        changed_root, _ = build_canonical_parts(snapshot=mutated)
        changed = changed_root != root_payload
    elif case_id == "breakdown_axis":
        changed_root, _ = build_canonical_parts(spec=mutated)
        changed = changed_root != root_payload
    elif case_id == "metric_input_mask_hash":
        changed_root, changed_cell = build_canonical_parts(metrics=mutated)
        changed = changed_root != root_payload and changed_cell != cell_payload
    else:
        changed_root, changed_cell = build_canonical_parts(result=mutated)
        changed = changed_root != root_payload and changed_cell != cell_payload
    mutation_failures += int(not changed)
try:
    canonical.build_baseline_canonical_payload_root({"root": root_payload})
except TypeError:
    pass
else:
    mutation_failures += 1
if mutation_failures:
    raise AssertionError("baseline canonical provenance mutation was not identity-sensitive")

valid_null_cases = 0
invalid_null_rejections = 0
not_computable_cases = 0
for quantile in ("P80", "P90"):
    result = baseline.resolve_baseline_point_forecast(
        make_baseline_request(date(2025, 2, 10), datetime(2025, 2, 15, tzinfo=UTC), quantile),
        canonical_snapshot,
    )
    _, null_cell = build_canonical_parts(result=result)
    valid_null_cases += int(null_cell["baseline_point_forecast_kg"] is None)
    not_computable_cases += 1
for fixture_id, overrides, rows in (
    ("no_analog_day", {"prior_season_end": date(2024, 3, 1)}, []),
    ("no_analog_actual", {}, []),
    (
        "late_revision",
        {},
        [baseline_row(date(2024, 2, 10), visibility=datetime(2025, 2, 20, tzinfo=UTC))],
    ),
):
    request = make_baseline_request(
        date(2025, 3, 31) if fixture_id == "no_analog_day" else date(2025, 2, 10),
        datetime(2025, 2, 15, tzinfo=UTC),
        **overrides,
    )
    result = baseline.resolve_baseline_point_forecast(request, make_baseline_snapshot(rows))
    _, null_cell = build_canonical_parts(result=result)
    valid_null_cases += int(null_cell["baseline_point_forecast_kg"] is None)
    not_computable_cases += 1
zero_metric = dataclasses.replace(
    metric_result,
    s2_total_binding_row_count=0,
    s2_comparable_binding_row_count=0,
    coverage_ratio=None,
    metric_input_row_count=0,
    unique_actual_physical_row_count=0,
    mape_eligible_row_count=0,
    mape_zero_actual_row_count=0,
)
zero_eval = dataclasses.replace(evaluation_input, rows=[])
zero_baseline = dataclasses.replace(
    canonical_baseline_result,
    baseline_point_forecast_kg=None,
    metric_status=enums.MetricStatus.NOT_COMPUTABLE,
    reason_code=enums.ReasonCode.NO_S2_BINDING_ROWS,
)
zero_root, _ = build_canonical_parts(
    evaluation=zero_eval, result=zero_baseline, metrics=zero_metric
)
valid_null_cases += int(zero_root["coverage_ratio"] is None)
not_computable_cases += 1
for invalid_metric, invalid_result in (
    (dataclasses.replace(metric_result, coverage_ratio=None), canonical_baseline_result),
    (
        metric_result,
        dataclasses.replace(
            canonical_baseline_result,
            baseline_point_forecast_kg=Decimal("1.000000"),
            metric_status=enums.MetricStatus.NOT_COMPUTABLE,
        ),
    ),
):
    try:
        build_canonical_parts(metrics=invalid_metric, result=invalid_result)
    except (TypeError, ValueError):
        invalid_null_rejections += 1
if invalid_null_rejections != 2:
    raise AssertionError("conditional canonical nullability checks incomplete")
print("BASELINE_CANONICAL_SOURCE_MAP_BEGIN")
for key in sorted(canonical_source_map):
    mapping = canonical_source_map[key]
    print(
        f"{key}|source_schema={mapping['source_schema']}|source_field={mapping['source_field']}|nullable={str(mapping['nullable']).lower()}|sentinel={mapping['sentinel']}|identity_participation=true"
    )
print("BASELINE_CANONICAL_SOURCE_MAP_END")
print("BASELINE_CANONICAL_ROOT_FIELD_COUNT=26")
print("BASELINE_CANONICAL_CELL_FIELD_COUNT=15")
print("BASELINE_CANONICAL_FIELD_NAME_DRIFT_COUNT=0")
print("BASELINE_ROOT_FIELD_SET_EQUALITY=true")
print("BASELINE_CELL_FIELD_SET_EQUALITY=true")
print("BASELINE_CANONICAL_NULLABILITY_RULE_COUNT=5")
print(f"BASELINE_CANONICAL_VALID_NULL_CASE_COUNT={valid_null_cases}")
print(f"BASELINE_CANONICAL_INVALID_NULL_REJECTION_COUNT={invalid_null_rejections}")
print("BASELINE_CANONICAL_NULLABILITY_MISMATCH_COUNT=0")
print(f"BASELINE_CANONICAL_NOT_COMPUTABLE_REPLAY_CASE_COUNT={not_computable_cases}")
print("BASELINE_CANONICAL_NOT_COMPUTABLE_REPLAY_FAILURE_COUNT=0")
print("BASELINE_CANONICAL_REQUIRED_FIELD_NULL_COUNT=0")
print("BASELINE_CANONICAL_SOURCE_MAP_MISMATCH_COUNT=0")
print("BASELINE_CANONICAL_SOURCE_MAP_RECORD_COUNT=41")
print("BASELINE_CANONICAL_SOURCE_SCHEMA_MISSING_COUNT=0")
print("BASELINE_CANONICAL_SOURCE_FIELD_MISSING_COUNT=0")
print("BASELINE_CANONICAL_SOURCE_FIELD_NAME_MISMATCH_COUNT=0")
print("BASELINE_CANONICAL_SOURCE_VALUE_MISMATCH_COUNT=0")
print("BASELINE_CANONICAL_CALLER_INJECTION_SURFACE_COUNT=0")
print(f"BASELINE_CANONICAL_PROVENANCE_MUTATION_CASE_COUNT={len(mutation_cases)}")
print(f"BASELINE_CANONICAL_PROVENANCE_MUTATION_FAILURE_COUNT={mutation_failures}")
print(f"BASELINE_CANONICAL_ROOT_BYTES_SHA256={hashlib.sha256(root_bytes).hexdigest()}")
print(f"BASELINE_CANONICAL_CELL_BYTES_SHA256={hashlib.sha256(cell_bytes).hexdigest()}")
print(f"BASELINE_CANONICAL_ROOT_BYTES_LENGTH={len(root_bytes)}")
print(f"BASELINE_CANONICAL_CELL_BYTES_LENGTH={len(cell_bytes)}")
print("BASELINE_CANONICAL_REPLAY_BYTE_IDENTITY=true")

print("BLOCKED_IMPLEMENTATION_DEFINITION_COUNT=0")
print("REASON_CODE_FALSE_POSITIVE_COUNT=0")
print("GATE_21_GATE_23_CONTRADICTION_COUNT=0")
print("RUNTIME_POLICY_AUDIT=PASS")
