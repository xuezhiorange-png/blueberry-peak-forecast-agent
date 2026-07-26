#!/usr/bin/env bash
set -euo pipefail

PACKAGE_REPOSITORY_ROOT="docs/forecast-quality/s3-round-a-authorization-package"
SCRIPT_HASH_PREFIX="${PACKAGE_REPOSITORY_ROOT}/acceptance/"
SELF_PATH="${BASH_SOURCE[0]}"

parse_authorized_manifest() {
  local manifest="$1"
  awk -F ' \\| ' '
    $1 ~ /^backend\// && $2 == "CREATE" { print $1 }
  ' "${manifest}"
}

manifest_metadata_count() {
  grep -Ec '^[A-Z0-9_]+=.*$' "$1" || true
}

manifest_invalid_count() {
  awk -F ' \\| ' '
    /^[[:space:]]*#/ || /^[[:space:]]*$/ || /^[A-Z0-9_]+=.*$/ { next }
    !($1 ~ /^backend\// && $2 == "CREATE") { count++ }
    END { print count + 0 }
  ' "$1"
}

validate_hash_records() {
  local repo="$1"
  local base_sha="$2"
  local sha_file="$3"
  local record_count=0 prefix_count=0 mismatch_count=0 missing_count=0 stale_count=0
  local current_mismatch_count=0 base_mismatch_count=0
  local expected_paths=(
    "${SCRIPT_HASH_PREFIX}01_changed_path_gate.sh"
    "${SCRIPT_HASH_PREFIX}02_runtime_policy_audit.py"
    "${SCRIPT_HASH_PREFIX}03_test_gate.sh"
    "${SCRIPT_HASH_PREFIX}04_static_gate.sh"
  )
  local seen_file
  seen_file="$(mktemp "${TMPDIR:-/tmp}/s3-hash-seen.XXXXXX")"
  : >"${seen_file}"
  while IFS= read -r line; do
    [ -n "${line}" ] || continue
    if [[ ! "${line}" =~ ^([0-9a-f]{64})[[:space:]][[:space:]]([^[:space:]]+)$ ]]; then
      stale_count=$((stale_count + 1))
      continue
    fi
    local expected_hash="${BASH_REMATCH[1]}"
    local repository_relative_path="${BASH_REMATCH[2]}"
    record_count=$((record_count + 1))
    if [[ "${repository_relative_path}" == "${SCRIPT_HASH_PREFIX}"* ]] \
      && [[ "${repository_relative_path}" != /* ]] \
      && [[ "${repository_relative_path}" != *"../"* ]] \
      && [[ "${repository_relative_path}" != *"/.." ]]; then
      prefix_count=$((prefix_count + 1))
    else
      stale_count=$((stale_count + 1))
      continue
    fi
    printf '%s\n' "${repository_relative_path}" >>"${seen_file}"
    if ! git -C "${repo}" cat-file -e "${base_sha}:${repository_relative_path}" 2>/dev/null; then
      missing_count=$((missing_count + 1))
      continue
    fi
    local actual_hash
    actual_hash="$(git -C "${repo}" show "${base_sha}:${repository_relative_path}" | sha256sum | awk '{print $1}')"
    if [[ "${actual_hash}" != "${expected_hash}" ]]; then
      mismatch_count=$((mismatch_count + 1)); base_mismatch_count=$((base_mismatch_count + 1))
    fi
    current_path="${repo}/${repository_relative_path}"
    if [[ ! -f "${current_path}" ]]; then
      missing_count=$((missing_count + 1))
    elif [[ "$(sha256sum "${current_path}" | awk '{print $1}')" != "${expected_hash}" ]]; then
      mismatch_count=$((mismatch_count + 1)); current_mismatch_count=$((current_mismatch_count + 1))
    fi
  done <"${sha_file}"
  for expected_path in "${expected_paths[@]}"; do
    if ! grep -Fxq "${expected_path}" "${seen_file}"; then
      stale_count=$((stale_count + 1))
    fi
  done
  rm -f "${seen_file}"
  printf 'SCRIPT_HASH_RECORD_COUNT=%s\n' "${record_count}"
  printf 'SCRIPT_HASH_PATH_PREFIX_MATCH_COUNT=%s\n' "${prefix_count}"
  printf 'SCRIPT_HASH_MISMATCH_COUNT=%s\n' "${mismatch_count}"
  printf 'SCRIPT_HASH_MISSING_PATH_COUNT=%s\n' "${missing_count}"
  printf 'CURRENT_SCRIPT_HASH_MISMATCH_COUNT=%s\n' "${current_mismatch_count}"
  printf 'BASE_SCRIPT_HASH_MISMATCH_COUNT=%s\n' "${base_mismatch_count}"
  printf 'STALE_SCRIPT_HASH_REFERENCE_COUNT=%s\n' "${stale_count}"
  if [[ "${record_count}" == "4" && "${prefix_count}" == "4" \
    && "${mismatch_count}" == "0" && "${missing_count}" == "0" \
    && "${stale_count}" == "0" ]]; then
    return 0
  fi
  return 1
}

run_package_self_test() {
  local package_dir
  package_dir="$(cd "$(dirname "${SELF_PATH}")/.." && pwd)"
  local package_python="${package_dir}/acceptance/02_runtime_policy_audit.py"
  uv run ruff check "${package_python}"
  uv run ruff format --check "${package_python}"
  printf 'PACKAGE_PYTHON_RUFF_PATH_COUNT=1\n'
  printf 'PACKAGE_ROOT_RUFF_CHECK=PASS\n'
  printf 'PACKAGE_ROOT_RUFF_FORMAT_CHECK=PASS\n'
  local tmp
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/s3-round-a-package-self-test.XXXXXX")"
  trap "rm -rf '${tmp}'" EXIT
  local repo="${tmp}/fixture"
  git init -q "${repo}"
  git -C "${repo}" config user.email "fixture@example.invalid"
  git -C "${repo}" config user.name "Round A fixture"
  mkdir -p "${repo}/${PACKAGE_REPOSITORY_ROOT}"
  cp -R "${package_dir}/." "${repo}/${PACKAGE_REPOSITORY_ROOT}/"
  : >"${repo}/${PACKAGE_REPOSITORY_ROOT}/acceptance/SHA256SUMS"
  for script_name in 01_changed_path_gate.sh 02_runtime_policy_audit.py 03_test_gate.sh 04_static_gate.sh; do
    script_repo_path="${SCRIPT_HASH_PREFIX}${script_name}"
    script_hash="$(sha256sum "${repo}/${script_repo_path}" | awk '{print $1}')"
    printf '%s  %s\n' "${script_hash}" "${script_repo_path}" >>"${repo}/${PACKAGE_REPOSITORY_ROOT}/acceptance/SHA256SUMS"
  done
  cat >"${repo}/pyproject.toml" <<'EOF'
[project]
name = "round-a-fixture"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = ["pytest>=8.4.0", "ruff>=0.11.0", "mypy>=1.16.0"]
[tool.ruff]
line-length = 100
target-version = "py312"
[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "ASYNC"]
[tool.mypy]
python_version = "3.12"
strict = true
EOF
  cat >"${repo}/.gitignore" <<'EOF'
.venv/
__pycache__/
*.pyc
.ruff_cache/
.mypy_cache/
uv.lock
EOF
  git -C "${repo}" add "${PACKAGE_REPOSITORY_ROOT}"
  git -C "${repo}" add pyproject.toml
  git -C "${repo}" add .gitignore
  git -C "${repo}" commit -qm "fixture package base"
  local base_sha
  base_sha="$(git -C "${repo}" rev-parse HEAD)"

  local paths_file="${repo}/${PACKAGE_REPOSITORY_ROOT}/authorized-paths.txt"
  valid_paths=()
  while IFS= read -r path; do
    [ -n "${path}" ] && valid_paths+=("${path}")
  done < <(parse_authorized_manifest "${paths_file}")
  local metadata_count invalid_count metadata_parsed
  metadata_count="$(manifest_metadata_count "${paths_file}")"
  invalid_count="$(manifest_invalid_count "${paths_file}")"
  metadata_parsed=0
  for metadata in AUTHORIZED_CREATE_PATH_COUNT=26 AUTHORIZED_MODIFY_EXISTING_PATH_COUNT=0 AUTHORIZED_DELETE_PATH_COUNT=0 DUPLICATE_AUTHORIZED_PATH_COUNT=0; do
    if printf '%s\n' "${valid_paths[@]}" | grep -Fxq "${metadata}"; then
      metadata_parsed=$((metadata_parsed + 1))
    fi
  done
  test "${#valid_paths[@]}" = "26"
  test "${metadata_count}" = "4"
  test "${invalid_count}" = "0"
  test "${metadata_parsed}" = "0"

  validate_hash_records "${repo}" "${base_sha}" "${repo}/${PACKAGE_REPOSITORY_ROOT}/acceptance/SHA256SUMS" >/dev/null

  for path in "${valid_paths[@]}"; do
    mkdir -p "${repo}/$(dirname "${path}")"
    printf '# fixture\n' >"${repo}/${path}"
  done
  python3 - "${repo}" "${valid_paths[@]}" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

from textwrap import dedent

repo = Path(sys.argv[1])
valid_paths = sys.argv[2:]


def write(path: str, source: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    content = dedent(source).lstrip()
    if path.startswith("backend/app/"):
        content = "# mypy: ignore-errors\n" + content
    target.write_text(content, encoding="utf-8")


write("backend/app/forecast_quality/enums.py", '''
    from enum import Enum

    class MetricStatus(Enum):
        COMPUTED = "COMPUTED"
        COMPARED = "COMPARED"
        NOT_COMPUTABLE = "NOT_COMPUTABLE"
        NOT_VERIFIED = "NOT_VERIFIED"
        INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

    class ComparisonAvailability(Enum):
        AVAILABLE = "AVAILABLE"
        BLOCKED = "BLOCKED"

    class SupportedQuantile(Enum):
        P50 = "P50"
        P80 = "P80"
        P90 = "P90"

    class CrossQuantileInputSource(Enum):
        S2_IMMUTABLE_BACKTEST_BINDING = "S2_IMMUTABLE_BACKTEST_BINDING"

    class FrozenVersion(Enum):
        METRIC_INPUT_MASK_V1 = "v0.2-s3-metric-input-mask-v1"
        NAIVE_BASELINE_POLICY_V1 = "v0.2-s3-naive-baseline-policy-v1"
        SEASON_ANALOG_MAPPING_V1 = "v0.2-s3-season-analog-mapping-v1"

    class ReasonCode(Enum):
        NONE = "NONE"
        NO_MAPE_ELIGIBLE_ROWS = "NO_MAPE_ELIGIBLE_ROWS"
        MAPE_DENOMINATOR_ZERO = "MAPE_DENOMINATOR_ZERO"
        WAPE_DENOMINATOR_ZERO = "WAPE_DENOMINATOR_ZERO"
        RELATIVE_BIAS_DENOMINATOR_ZERO = "RELATIVE_BIAS_DENOMINATOR_ZERO"
        NO_COMPLETE_7DAY_WINDOW = "NO_COMPLETE_7DAY_WINDOW"
        QUANTILE_SEMANTICS_NOT_VERIFIED = "QUANTILE_SEMANTICS_NOT_VERIFIED"
        BELOW_MINIMUM = "BELOW_MINIMUM"
        BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED = "BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED"
        COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING = "COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING"
        SIGNED_DIRECTION_ONLY = "SIGNED_DIRECTION_ONLY"
        PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE = "PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE"
        NO_PRIOR_SEASON_ANALOG_DAY = "NO_PRIOR_SEASON_ANALOG_DAY"
        NO_PRIOR_SEASON_ANALOG_ACTUAL = "NO_PRIOR_SEASON_ANALOG_ACTUAL"
        BASELINE_SOURCE_NOT_VISIBLE_AT_CURRENT_FORECAST_CUTOFF = "BASELINE_SOURCE_NOT_VISIBLE_AT_CURRENT_FORECAST_CUTOFF"
        NO_S2_BINDING_ROWS = "NO_S2_BINDING_ROWS"
    ''')

write("backend/app/forecast_quality/exceptions.py", '''
    class ForecastQualityError(Exception):
        pass

    class S3StructuralDuplicateError(ForecastQualityError):
        pass

    class S3DecimalAssertionError(ForecastQualityError):
        pass

    class S3CanonicalIdentityConflictError(ForecastQualityError):
        pass

    class S3ContractInvariantViolationError(ForecastQualityError):
        pass
    ''')

write("backend/app/forecast_quality/schemas.py", '''
    from __future__ import annotations

    from collections.abc import Mapping, Sequence
    from dataclasses import dataclass
    from datetime import date, datetime
    from decimal import Decimal
    from typing import Any

    from .enums import ComparisonAvailability, FrozenVersion, MetricStatus, ReasonCode, SupportedQuantile

    @dataclass(frozen=True)
    class ActualPhysicalRecord:
        physical_key: str
        stable_actual_identity: str
        actual_value_kg: Decimal

    @dataclass(frozen=True)
    class S3EvaluationInput:
        rows: Sequence[S3BindingRow]
        s2_run_identity: str
        s2_manifest_identity: str
        s2_binding_row_set_hash: str
        metric_policy_version: FrozenVersion
        baseline_policy_version: FrozenVersion

    @dataclass(frozen=True)
    class S3BindingRow:
        forecast_business_key: str
        actual_physical_key: str | None
        stable_actual_identity: str | None
        forecast_value_kg: Decimal | None
        actual_value_kg: Decimal | None
        forecast_quantile: SupportedQuantile
        forecast_horizon_days: int
        forecast_target_date: date
        forecast_cutoff_at: datetime
        s2_status: str
        season_business_key: str
        farm_business_key: str
        subfarm_business_key: str
        variety_business_key: str
        model_identity: str
        actual_visibility_timestamp: datetime | None

    @dataclass(frozen=True)
    class FarmDailyActualAggregate:
        season_business_key: str
        farm_business_key: str
        variety_business_key: str
        target_date: date
        actual_value_kg: Decimal
        unique_actual_physical_rows: int

    @dataclass(frozen=True)
    class FarmDailyForecastAggregate:
        season_business_key: str
        farm_business_key: str
        variety_business_key: str
        target_date: date
        forecast_cutoff_at: datetime
        model_identity: str
        forecast_quantile: SupportedQuantile
        forecast_horizon_days: int
        forecast_value_kg: Decimal
        source_forecast_business_keys: Sequence[str]

    @dataclass(frozen=True)
    class MetricValueCell:
        metric_name: str
        metric_value: Decimal | None
        metric_status: MetricStatus
        reason_code: ReasonCode
        numerator: Decimal | None
        denominator: Decimal | None
        mape_eligible_row_count: int
        mape_zero_actual_row_count: int

    @dataclass(frozen=True)
    class DailyMetricResult:
        s2_run_identity: str
        s2_manifest_identity: str
        s2_binding_row_set_hash: str
        metric_policy_version: FrozenVersion
        baseline_policy_version: FrozenVersion
        breakdown_identity: dict[str, str | int]
        s2_total_binding_row_count: int
        s2_comparable_binding_row_count: int
        s2_excluded_binding_row_count: int
        s2_not_computable_binding_row_count: int
        coverage_ratio: Decimal | None
        metric_input_mask_hash: str
        metric_input_row_count: int
        metric_input_quantile: SupportedQuantile
        unique_actual_physical_row_count: int
        mape_eligible_row_count: int
        mape_zero_actual_row_count: int
        mape_zero_actual_reason_code: ReasonCode | None
        metric_cells: Sequence[MetricValueCell]
        canonical_hash: str

    @dataclass(frozen=True)
    class BreakdownSpec:
        forecast_horizon_days: int
        farm_business_key: str
        subfarm_business_key: str
        variety_business_key: str
        season_business_key: str
        model_identity: str

    @dataclass(frozen=True)
    class BaselineRequest:
        current_target_date: date
        current_season_start: date
        current_season_end: date
        prior_season_start: date
        prior_season_end: date
        current_forecast_cutoff_at: datetime
        farm_business_key: str
        subfarm_business_key: str
        variety_business_key: str
        requested_quantile: str
        metric_policy_version: FrozenVersion
        baseline_policy_version: FrozenVersion

    @dataclass(frozen=True)
    class BaselineSourceSnapshot:
        source_snapshot_identity: str
        source_snapshot_hash: str
        source_row_set_hash: str
        visibility_manifest_hash: str
        visibility_cutoff_at: datetime
        season_analog_mapping_policy_version: FrozenVersion
        actual_rows: Sequence[Mapping[str, Any]]

    @dataclass(frozen=True)
    class BaselineResult:
        baseline_point_forecast_kg: Decimal | None
        baseline_quantile: str
        comparison_availability: ComparisonAvailability
        metric_status: MetricStatus
        reason_code: ReasonCode
        analog_date: date | None
        source_snapshot_identity: str
        source_snapshot_hash: str
        source_row_set_hash: str
        visibility_manifest_hash: str
        canonical_hash: str
    ''')

write("backend/app/forecast_quality/canonical.py", '''
    from __future__ import annotations

    import hashlib
    import json
    from dataclasses import dataclass
    from decimal import ROUND_HALF_EVEN, Decimal
    from typing import Any

    from .exceptions import S3DecimalAssertionError, S3StructuralDuplicateError

    @dataclass(frozen=True)
    class Registry:
        forecast_row_count_before: int
        forecast_row_count_after: int
        unique_actual_physical_row_count: int

    def _value(row: Any, name: str) -> Any:
        return row[name] if isinstance(row, dict) else getattr(row, name)

    def canonical_json_bytes(value: Any) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()

    def emit_s3_decimal(value: Any) -> str:
        if type(value) is not Decimal or not value.is_finite():
            raise S3DecimalAssertionError("finite Decimal required")
        return format(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN), "f")

    def compute_metric_input_mask_hash(value: Any) -> str:
        return hashlib.sha256(canonical_json_bytes(value)).hexdigest()

    def build_actual_physical_registry(rows: list[Any]) -> Registry:
        identities: dict[str, tuple[str, Decimal]] = {}
        for row in rows:
            key = _value(row, "actual_physical_key")
            identity = _value(row, "stable_actual_identity")
            amount = _value(row, "actual_value_kg")
            if key in identities and identities[key] != (identity, amount):
                raise S3StructuralDuplicateError(key)
            identities[key] = (identity, amount)
        return Registry(len(rows), len(rows), len(identities))

    ROOT_FIELDS = (
        "schema_version", "s2_run_identity", "s2_manifest_identity", "s2_binding_row_set_hash",
        "baseline_source_snapshot_identity", "baseline_source_snapshot_hash", "baseline_source_row_set_hash",
        "baseline_source_visibility_manifest_hash", "baseline_source_visibility_cutoff_at",
        "baseline_policy_version", "season_analog_mapping_policy_version", "prior_season_identity",
        "baseline_grain", "baseline_horizon_rule", "breakdown_dimensions", "s2_total_binding_row_count",
        "s2_comparable_binding_row_count", "s2_excluded_binding_row_count",
        "s2_not_computable_binding_row_count", "coverage_ratio", "metric_input_mask_policy_version",
        "metric_input_mask_hash", "metric_input_row_count", "metric_input_quantile",
        "unique_actual_physical_row_count", "per_breakdown_cell")
    CELL_FIELDS = (
        "baseline_point_forecast_kg", "s2_total_binding_row_count", "s2_comparable_binding_row_count",
        "s2_excluded_binding_row_count", "s2_not_computable_binding_row_count", "coverage_ratio",
        "metric_input_mask_policy_version", "metric_input_mask_hash", "metric_input_row_count",
        "metric_input_quantile", "unique_actual_physical_row_count", "mape_eligible_row_count",
        "mape_zero_actual_row_count", "metric_status", "reason_code")

    def _canonical_section(context: Any, section: str, fields: tuple[str, ...]) -> dict[str, Any]:
        payload = dict(context[section])
        if tuple(payload) != fields or any(payload[field] is None for field in fields):
            raise ValueError(f"invalid canonical {section} context")
        return payload

    def build_baseline_canonical_payload_root(context: Any) -> dict[str, Any]:
        return _canonical_section(context, "root", ROOT_FIELDS)

    def build_baseline_canonical_payload_cell(context: Any) -> dict[str, Any]:
        return _canonical_section(context, "cell", CELL_FIELDS)
    ''')

write("backend/app/forecast_quality/aggregation.py", '''
    from __future__ import annotations

    from collections import defaultdict
    from decimal import Decimal
    from typing import Any

    from .canonical import build_actual_physical_registry
    from .exceptions import S3StructuralDuplicateError
    from .schemas import FarmDailyActualAggregate, FarmDailyForecastAggregate

    def _value(row: Any, name: str) -> Any:
        return row[name] if isinstance(row, dict) else getattr(row, name)

    def aggregate_daily_forecasts(rows: list[Any]) -> list[FarmDailyForecastAggregate]:
        grouped: dict[tuple[Any, ...], tuple[Decimal, list[str]]] = {}
        seen: set[str] = set()
        for row in rows:
            key = _value(row, "forecast_business_key")
            if key in seen:
                raise S3StructuralDuplicateError(key)
            seen.add(key)
            group = tuple(_value(row, name) for name in (
                "season_business_key", "farm_business_key", "variety_business_key", "forecast_target_date",
                "forecast_cutoff_at", "model_identity", "forecast_quantile", "forecast_horizon_days"))
            total, keys = grouped.get(group, (Decimal("0"), []))
            grouped[group] = (total + _value(row, "forecast_value_kg"), keys + [key])
        return [FarmDailyForecastAggregate(*group, total, keys) for group, (total, keys) in grouped.items()]

    def aggregate_daily_actuals(rows: list[Any]) -> list[FarmDailyActualAggregate]:
        registry = build_actual_physical_registry(rows)
        unique: dict[str, Any] = {}
        for row in rows:
            unique.setdefault(_value(row, "actual_physical_key"), row)
        if not unique:
            return []
        first = next(iter(unique.values()))
        total = sum((_value(row, "actual_value_kg") for row in unique.values()), Decimal("0"))
        return [FarmDailyActualAggregate(
            _value(first, "season_business_key"), _value(first, "farm_business_key"),
            _value(first, "variety_business_key"), _value(first, "forecast_target_date"), total,
            registry.unique_actual_physical_row_count)]
    ''')

write("backend/app/forecast_quality/calculator_daily.py", '''
    from __future__ import annotations

    import dataclasses
    import hashlib
    from decimal import Decimal
    from typing import Any

    from .canonical import canonical_json_bytes, compute_metric_input_mask_hash
    from .enums import FrozenVersion, MetricStatus, ReasonCode, SupportedQuantile
    from .schemas import DailyMetricResult, MetricValueCell

    def _value(row: Any, name: str) -> Any:
        return row[name] if isinstance(row, dict) else getattr(row, name)

    def _cell(name: str, value: Decimal | None, numerator: Decimal | None, denominator: Decimal | None,
              status: MetricStatus, reason: ReasonCode, eligible: int, zero: int) -> MetricValueCell:
        return MetricValueCell(name, value, status, reason, numerator, denominator, eligible, zero)

    def compute_daily_metrics(evaluation_input: Any, breakdown_spec: Any) -> DailyMetricResult:
        rows = list(_value(evaluation_input, "rows"))
        errors = [_value(row, "forecast_value_kg") - _value(row, "actual_value_kg") for row in rows]
        actuals = [_value(row, "actual_value_kg") for row in rows]
        abs_errors = [abs(error) for error in errors]
        abs_sum = sum(abs_errors, Decimal("0"))
        actual_sum = sum(actuals, Decimal("0"))
        eligible = [error / actual for error, actual in zip(abs_errors, actuals, strict=True) if actual != 0]
        zero_count = len(actuals) - len(eligible)
        smape_terms = [Decimal("0") if f == a == 0 else Decimal("2") * abs(f - a) / (f + a)
                       for f, a in zip((_value(row, "forecast_value_kg") for row in rows), actuals, strict=True)]
        cells = {
            "daily_mae": _cell("daily_mae", abs_sum / len(rows), abs_sum, Decimal(len(rows)), MetricStatus.COMPUTED, ReasonCode.NONE, len(rows), zero_count),
            "daily_wape": _cell("daily_wape", abs_sum / actual_sum, abs_sum, actual_sum, MetricStatus.COMPUTED, ReasonCode.NONE, len(rows), zero_count) if actual_sum else _cell("daily_wape", None, abs_sum, actual_sum, MetricStatus.NOT_COMPUTABLE, ReasonCode.WAPE_DENOMINATOR_ZERO, len(rows), zero_count),
            "daily_smape": _cell("daily_smape", sum(smape_terms, Decimal("0")) / len(rows), sum(smape_terms, Decimal("0")), Decimal(len(rows)), MetricStatus.COMPUTED, ReasonCode.NONE, len(rows), zero_count),
            "daily_mape": _cell("daily_mape", sum(eligible, Decimal("0")) / len(eligible), sum(eligible, Decimal("0")), Decimal(len(eligible)), MetricStatus.COMPUTED, ReasonCode.NONE, len(eligible), zero_count) if eligible else _cell("daily_mape", None, None, Decimal("0"), MetricStatus.NOT_COMPUTABLE, ReasonCode.NO_MAPE_ELIGIBLE_ROWS, 0, zero_count),
            "daily_bias_kg": _cell("daily_bias_kg", sum(errors, Decimal("0")) / len(rows), sum(errors, Decimal("0")), Decimal(len(rows)), MetricStatus.COMPUTED, ReasonCode.NONE, len(rows), zero_count),
            "daily_relative_bias": _cell("daily_relative_bias", sum(errors, Decimal("0")) / actual_sum, sum(errors, Decimal("0")), actual_sum, MetricStatus.COMPUTED, ReasonCode.NONE, len(rows), zero_count) if actual_sum else _cell("daily_relative_bias", None, sum(errors, Decimal("0")), actual_sum, MetricStatus.NOT_COMPUTABLE, ReasonCode.RELATIVE_BIAS_DENOMINATOR_ZERO, len(rows), zero_count),
            "daily_absolute_error_sum_kg": _cell("daily_absolute_error_sum_kg", abs_sum, abs_sum, Decimal("1"), MetricStatus.COMPUTED, ReasonCode.NONE, len(rows), zero_count),
        }
        zero_reason = ReasonCode.MAPE_DENOMINATOR_ZERO if zero_count else None
        breakdown_identity = {
            "season_business_key": _value(breakdown_spec, "season_business_key"),
            "farm_business_key": _value(breakdown_spec, "farm_business_key"),
            "subfarm_business_key": _value(breakdown_spec, "subfarm_business_key"),
            "variety_business_key": _value(breakdown_spec, "variety_business_key"),
            "model_identity": _value(breakdown_spec, "model_identity"),
            "forecast_horizon_days": _value(breakdown_spec, "forecast_horizon_days"),
        }
        mask_payload = {
            "metric_input_mask_policy_version": "v0.2-s3-metric-input-mask-v1",
            "s2_status_predicate": "S2_STATUS_COMPARABLE",
            "forecast_quantile_predicate": "P50",
            "actual_pair_predicate": "EXACT_ACTUAL_PAIRED",
            "breakdown_identity": breakdown_identity,
            "source_row_set_identity": _value(evaluation_input, "s2_binding_row_set_hash"),
        }
        result = DailyMetricResult(
            _value(evaluation_input, "s2_run_identity"), _value(evaluation_input, "s2_manifest_identity"),
            _value(evaluation_input, "s2_binding_row_set_hash"), FrozenVersion.METRIC_INPUT_MASK_V1,
            FrozenVersion.NAIVE_BASELINE_POLICY_V1, breakdown_identity,
            len(rows), len(rows), 0, 0, Decimal("1"), compute_metric_input_mask_hash(mask_payload),
            len(rows), SupportedQuantile.P50, len({str(_value(row, "actual_physical_key")) for row in rows}),
            len(eligible), zero_count, zero_reason, list(cells.values()), "")
        payload = dataclasses.asdict(result)
        payload["canonical_hash"] = ""
        return dataclasses.replace(
            result,
            canonical_hash=hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
        )
    ''')

write("backend/app/forecast_quality/breakdown.py", '''
    from dataclasses import dataclass

    from .enums import MetricStatus, ReasonCode

    @dataclass(frozen=True)
    class BreakdownCell:
        cell_identity: dict[str, str | int]
        metric_status: MetricStatus
        reason_code: ReasonCode

    MIN_COMPARABLE_ROWS_FOR_REPORTING = 10

    def calculate_breakdown_cells(rows, breakdown_spec):
        identity = {name: getattr(breakdown_spec, name) for name in (
            "season_business_key", "farm_business_key", "subfarm_business_key",
            "variety_business_key", "model_identity", "forecast_horizon_days")}
        if len(rows) < MIN_COMPARABLE_ROWS_FOR_REPORTING:
            return [BreakdownCell(identity, MetricStatus.INSUFFICIENT_SAMPLE, ReasonCode.BELOW_MINIMUM)]
        return [BreakdownCell(identity, MetricStatus.COMPUTED, ReasonCode.NONE)]
    ''')

write("backend/app/forecast_quality/season_calendar.py", '''
    from datetime import date, timedelta

    def deterministic_season_day_index(current_target_date, current_season_start, current_season_end):
        if current_target_date < current_season_start or current_target_date > current_season_end:
            return None
        return (current_target_date - current_season_start).days

    def resolve_prior_season_analog_date(current_target_date, current_season_start, current_season_end,
                                         prior_season_start, prior_season_end, policy_version):
        index = deterministic_season_day_index(current_target_date, current_season_start, current_season_end)
        if index is None or index >= (prior_season_end - prior_season_start).days + 1:
            return None
        candidate = prior_season_start + timedelta(days=index)
        if current_target_date.month == 2 and current_target_date.day == 29 and candidate.month == 2 and candidate.day == 29:
            return candidate
        if current_target_date.month == 2 and current_target_date.day == 29 and candidate.month == 3:
            return date(candidate.year, 2, 28)
        return candidate
    ''')

write("backend/app/forecast_quality/baseline.py", '''
    from __future__ import annotations

    from datetime import date
    from decimal import Decimal
    from .enums import ComparisonAvailability, MetricStatus, ReasonCode
    from .schemas import BaselineResult
    from .season_calendar import resolve_prior_season_analog_date

    def _value(row, name):
        return row[name] if isinstance(row, dict) else getattr(row, name)

    def resolve_baseline_point_forecast(request, source_snapshot):
        analog = resolve_prior_season_analog_date(
            request.current_target_date, request.current_season_start, request.current_season_end,
            request.prior_season_start, request.prior_season_end, request.baseline_policy_version)
        base = dict(
            baseline_quantile=request.requested_quantile,
            source_snapshot_identity=source_snapshot.source_snapshot_identity,
            source_snapshot_hash=source_snapshot.source_snapshot_hash,
            source_row_set_hash=source_snapshot.source_row_set_hash,
            visibility_manifest_hash=source_snapshot.visibility_manifest_hash,
            canonical_hash="fixture-baseline-result")
        if analog is None:
            return BaselineResult(None, **base, comparison_availability=ComparisonAvailability.BLOCKED,
                                  metric_status=MetricStatus.NOT_COMPUTABLE,
                                  reason_code=ReasonCode.NO_PRIOR_SEASON_ANALOG_DAY, analog_date=None)
        matching = [_row for _row in source_snapshot.actual_rows if _value(_row, "target_date") == analog]
        if not matching:
            return BaselineResult(None, **base, comparison_availability=ComparisonAvailability.BLOCKED,
                                  metric_status=MetricStatus.NOT_COMPUTABLE,
                                  reason_code=ReasonCode.NO_PRIOR_SEASON_ANALOG_ACTUAL, analog_date=analog)
        valid = [row for row in matching if _value(row, "source_kind") == "FARM_PICK"]
        visible = [row for row in valid if _value(row, "visibility_timestamp") <= request.current_forecast_cutoff_at]
        if not visible:
            return BaselineResult(None, **base, comparison_availability=ComparisonAvailability.BLOCKED,
                                  metric_status=MetricStatus.NOT_COMPUTABLE,
                                  reason_code=ReasonCode.BASELINE_SOURCE_NOT_VISIBLE_AT_CURRENT_FORECAST_CUTOFF,
                                  analog_date=analog)
        if request.requested_quantile in {"P80", "P90"}:
            return BaselineResult(None, **base, comparison_availability=ComparisonAvailability.BLOCKED,
                                  metric_status=MetricStatus.NOT_COMPUTABLE,
                                  reason_code=ReasonCode.BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED,
                                  analog_date=analog)
        return BaselineResult(_value(visible[0], "actual_value_kg"), "P50",
                              ComparisonAvailability.AVAILABLE, MetricStatus.COMPUTED, ReasonCode.NONE,
                              analog, **{key: base[key] for key in ("source_snapshot_identity", "source_snapshot_hash", "source_row_set_hash", "visibility_manifest_hash", "canonical_hash")})
    ''')

for path in valid_paths:
    if path.startswith("backend/tests/"):
        write(path, "def test_fixture_contract():\n    assert True\n")
PY
  (cd "${repo}" && uv run ruff format backend/app backend/tests && uv run ruff check --fix backend/app backend/tests)
  git -C "${repo}" add backend
  git -C "${repo}" commit -qm "fixture compliant implementation"
  local positive_head
  positive_head="$(git -C "${repo}" rev-parse HEAD)"
  local positive_gate_count=0
  IMPLEMENTATION_BASE_SHA="${base_sha}" ROUND_A_WORKTREE="${repo}" \
    PACKAGE_DIR="${repo}/${PACKAGE_REPOSITORY_ROOT}" PACKAGE_SELF_TEST_INTERNAL=1 \
    bash "${repo}/${SCRIPT_HASH_PREFIX}01_changed_path_gate.sh"
  positive_gate_count=$((positive_gate_count + 1))
  IMPLEMENTATION_BASE_SHA="${base_sha}" ROUND_A_WORKTREE="${repo}" \
    PACKAGE_DIR="${repo}/${PACKAGE_REPOSITORY_ROOT}" PACKAGE_SELF_TEST_INTERNAL=1 \
    uv run python "${repo}/${SCRIPT_HASH_PREFIX}02_runtime_policy_audit.py"
  positive_gate_count=$((positive_gate_count + 1))
  IMPLEMENTATION_BASE_SHA="${base_sha}" ROUND_A_WORKTREE="${repo}" \
    PACKAGE_DIR="${repo}/${PACKAGE_REPOSITORY_ROOT}" PACKAGE_SELF_TEST_INTERNAL=1 \
    bash "${repo}/${SCRIPT_HASH_PREFIX}03_test_gate.sh"
  positive_gate_count=$((positive_gate_count + 1))
  IMPLEMENTATION_BASE_SHA="${base_sha}" ROUND_A_WORKTREE="${repo}" \
    PACKAGE_DIR="${repo}/${PACKAGE_REPOSITORY_ROOT}" PACKAGE_SELF_TEST_INTERNAL=1 \
    bash "${repo}/${SCRIPT_HASH_PREFIX}04_static_gate.sh"
  positive_gate_count=$((positive_gate_count + 1))

  local negative_expected=0 unexpected_pass=0 negative_gate_count=0
  expect_fail() {
    local fixture_id="$1" gate_path="$2"
    shift 2
    negative_gate_count=$((negative_gate_count + 1))
    negative_expected=$((negative_expected + 1))
    local actual_exit_code=0
    set +e
    "$@" >/dev/null 2>&1
    actual_exit_code=$?
    set -e
    if [[ "${actual_exit_code}" == "0" ]]; then
      unexpected_pass=$((unexpected_pass + 1))
    fi
    printf 'NEGATIVE_FIXTURE=%s|gate=%s|exact_command=%q|expected_exit_nonzero=true|actual_exit_code=%s|result=%s\n' \
      "${fixture_id}" "${gate_path}" "$*" "${actual_exit_code}" \
      "$([[ "${actual_exit_code}" != "0" ]] && echo PASS || echo UNEXPECTED_PASS)"
  }

  clone_fixture() {
    local name="$1"
    local clone="${tmp}/${name}"
    git clone -q "${repo}" "${clone}"
    git -C "${clone}" checkout -q --detach "${positive_head}"
    printf '%s\n' "${clone}"
  }
  run_path_gate_expect_fail() {
    local fixture_id="$1" clone="$2"
    expect_fail "${fixture_id}" "01_changed_path_gate.sh" env IMPLEMENTATION_BASE_SHA="${base_sha}" ROUND_A_WORKTREE="${clone}" \
      PACKAGE_DIR="${clone}/${PACKAGE_REPOSITORY_ROOT}" PACKAGE_SELF_TEST_INTERNAL=1 \
      bash "${clone}/${SCRIPT_HASH_PREFIX}01_changed_path_gate.sh"
  }

  bad_hash_clone="$(clone_fixture bad-hash)"
  perl -0pi -e 's/^[0-9a-f]{64}/0000000000000000000000000000000000000000000000000000000000000000/' \
    "${bad_hash_clone}/${PACKAGE_REPOSITORY_ROOT}/acceptance/SHA256SUMS"
  run_path_gate_expect_fail bad-four-entry-script-hash "${bad_hash_clone}"

  missing_script_clone="$(clone_fixture missing-script)"
  rm "${missing_script_clone}/${SCRIPT_HASH_PREFIX}04_static_gate.sh"
  run_path_gate_expect_fail missing-script-blob "${missing_script_clone}"

  metadata_clone="$(clone_fixture metadata-record)"
  printf 'backend/not-a-create-record.py | INVALID | fixture\n' >> \
    "${metadata_clone}/${PACKAGE_REPOSITORY_ROOT}/authorized-paths.txt"
  run_path_gate_expect_fail invalid-manifest-record "${metadata_clone}"

  extra_path_clone="$(clone_fixture extra-path)"
  printf '# extra\n' >"${extra_path_clone}/backend/app/forecast_quality/path_27.py"
  run_path_gate_expect_fail twenty-seventh-path "${extra_path_clone}"

  blocked_path_clone="$(clone_fixture blocked-path)"
  mkdir -p "${blocked_path_clone}/backend/app/models"
  printf '# blocked\n' >"${blocked_path_clone}/backend/app/models/blocked.py"
  run_path_gate_expect_fail blocked-model-path "${blocked_path_clone}"

  zero_module_clone="$(clone_fixture zero-module)"
  : >"${zero_module_clone}/backend/tests/forecast_quality/test_aggregation.py"
  expect_fail zero-test-module "03_test_gate.sh" env IMPLEMENTATION_BASE_SHA="${base_sha}" ROUND_A_WORKTREE="${zero_module_clone}" \
    PACKAGE_DIR="${zero_module_clone}/${PACKAGE_REPOSITORY_ROOT}" PACKAGE_SELF_TEST_INTERNAL=1 \
    bash "${zero_module_clone}/${SCRIPT_HASH_PREFIX}03_test_gate.sh"

  root_drift_clone="$(clone_fixture root-drift)"
  cat >>"${root_drift_clone}/backend/app/forecast_quality/canonical.py" <<'PY'
def build_baseline_canonical_payload_root(result):
    return {"drift": None}
PY
  expect_fail baseline-root-field-drift "02_runtime_policy_audit.py" env IMPLEMENTATION_BASE_SHA="${base_sha}" ROUND_A_WORKTREE="${root_drift_clone}" \
    PACKAGE_DIR="${root_drift_clone}/${PACKAGE_REPOSITORY_ROOT}" PACKAGE_SELF_TEST_INTERNAL=1 \
    uv run python "${root_drift_clone}/${SCRIPT_HASH_PREFIX}02_runtime_policy_audit.py"

  cell_drift_clone="$(clone_fixture cell-drift)"
  cat >>"${cell_drift_clone}/backend/app/forecast_quality/canonical.py" <<'PY'
def build_baseline_canonical_payload_cell(result):
    return {"drift": None}
PY
  expect_fail baseline-cell-field-drift "02_runtime_policy_audit.py" env IMPLEMENTATION_BASE_SHA="${base_sha}" ROUND_A_WORKTREE="${cell_drift_clone}" \
    PACKAGE_DIR="${cell_drift_clone}/${PACKAGE_REPOSITORY_ROOT}" PACKAGE_SELF_TEST_INTERNAL=1 \
    uv run python "${cell_drift_clone}/${SCRIPT_HASH_PREFIX}02_runtime_policy_audit.py"

  version_clone="$(clone_fixture frozen-version)"
  perl -0pi -e 's/METRIC_INPUT_MASK_V1 = "v0\.2-s3-metric-input-mask-v1"/METRIC_INPUT_MASK_V1 = "wrong"/' \
    "${version_clone}/backend/app/forecast_quality/enums.py"
  expect_fail wrong-frozen-version "02_runtime_policy_audit.py" env IMPLEMENTATION_BASE_SHA="${base_sha}" ROUND_A_WORKTREE="${version_clone}" \
    PACKAGE_DIR="${version_clone}/${PACKAGE_REPOSITORY_ROOT}" PACKAGE_SELF_TEST_INTERNAL=1 \
    uv run python "${version_clone}/${SCRIPT_HASH_PREFIX}02_runtime_policy_audit.py"

  blocked_ast_clone="$(clone_fixture blocked-ast)"
  cat >>"${blocked_ast_clone}/backend/app/forecast_quality/aggregation.py" <<'PY'
def prediction_interval():
    return None
PY
  expect_fail blocked-ast-definition "04_static_gate.sh" env IMPLEMENTATION_BASE_SHA="${base_sha}" ROUND_A_WORKTREE="${blocked_ast_clone}" \
    PACKAGE_DIR="${blocked_ast_clone}/${PACKAGE_REPOSITORY_ROOT}" PACKAGE_SELF_TEST_INTERNAL=1 \
    bash "${blocked_ast_clone}/${SCRIPT_HASH_PREFIX}04_static_gate.sh"

  run_runtime_gate_expect_fail() {
    local fixture_id="$1" clone="$2"
    expect_fail "${fixture_id}" "02_runtime_policy_audit.py" env IMPLEMENTATION_BASE_SHA="${base_sha}" ROUND_A_WORKTREE="${clone}" \
      PACKAGE_DIR="${clone}/${PACKAGE_REPOSITORY_ROOT}" PACKAGE_SELF_TEST_INTERNAL=1 \
      uv run python "${clone}/${SCRIPT_HASH_PREFIX}02_runtime_policy_audit.py"
  }

  breakdown_schema_clone="$(clone_fixture breakdown-seventh-field)"
  perl -0pi -e 's/(model_identity: str\n)/$1        minimum_sample_size: int\n/' \
    "${breakdown_schema_clone}/backend/app/forecast_quality/schemas.py"
  run_runtime_gate_expect_fail breakdown-seventh-field "${breakdown_schema_clone}"

  canonical_none_clone="$(clone_fixture canonical-all-none)"
  cat >>"${canonical_none_clone}/backend/app/forecast_quality/canonical.py" <<'PY'
def build_baseline_canonical_payload_root(context):
    return {key: None for key in context["root"]}

def build_baseline_canonical_payload_cell(context):
    return {key: None for key in context["cell"]}
PY
  run_runtime_gate_expect_fail canonical-all-required-values-none "${canonical_none_clone}"

  canonical_run_clone="$(clone_fixture canonical-wrong-s2-run)"
  cat >>"${canonical_run_clone}/backend/app/forecast_quality/canonical.py" <<'PY'
def build_baseline_canonical_payload_root(context):
    payload = dict(context["root"])
    payload["s2_run_identity"] = "wrong-run"
    return payload
PY
  run_runtime_gate_expect_fail canonical-wrong-s2-run-identity "${canonical_run_clone}"

  canonical_rowset_clone="$(clone_fixture canonical-wrong-row-set)"
  cat >>"${canonical_rowset_clone}/backend/app/forecast_quality/canonical.py" <<'PY'
def build_baseline_canonical_payload_root(context):
    payload = dict(context["root"])
    payload["s2_binding_row_set_hash"] = "wrong-row-set"
    return payload
PY
  run_runtime_gate_expect_fail canonical-wrong-binding-row-set-hash "${canonical_rowset_clone}"

  canonical_source_clone="$(clone_fixture canonical-wrong-source-snapshot)"
  cat >>"${canonical_source_clone}/backend/app/forecast_quality/canonical.py" <<'PY'
def build_baseline_canonical_payload_root(context):
    payload = dict(context["root"])
    payload["baseline_source_snapshot_identity"] = "wrong-snapshot"
    return payload
PY
  run_runtime_gate_expect_fail canonical-wrong-source-snapshot-identity "${canonical_source_clone}"

  canonical_visibility_clone="$(clone_fixture canonical-wrong-visibility-hash)"
  cat >>"${canonical_visibility_clone}/backend/app/forecast_quality/canonical.py" <<'PY'
def build_baseline_canonical_payload_root(context):
    payload = dict(context["root"])
    payload["baseline_source_visibility_manifest_hash"] = "wrong-visibility"
    return payload
PY
  run_runtime_gate_expect_fail canonical-wrong-visibility-manifest-hash "${canonical_visibility_clone}"

  daily_counter_clone="$(clone_fixture daily-wrong-counter)"
  cat >>"${daily_counter_clone}/backend/app/forecast_quality/calculator_daily.py" <<'PY'
_round_a_original_compute_daily_metrics = compute_daily_metrics
def compute_daily_metrics(evaluation_input, breakdown_spec):
    result = _round_a_original_compute_daily_metrics(evaluation_input, breakdown_spec)
    return dataclasses.replace(
        result,
        s2_comparable_binding_row_count=result.s2_comparable_binding_row_count + 1,
    )
PY
  run_runtime_gate_expect_fail daily-result-wrong-counter "${daily_counter_clone}"

  daily_coverage_clone="$(clone_fixture daily-wrong-coverage)"
  cat >>"${daily_coverage_clone}/backend/app/forecast_quality/calculator_daily.py" <<'PY'
_round_a_original_compute_daily_metrics = compute_daily_metrics
def compute_daily_metrics(evaluation_input, breakdown_spec):
    result = _round_a_original_compute_daily_metrics(evaluation_input, breakdown_spec)
    return dataclasses.replace(result, coverage_ratio=Decimal("0.500000"))
PY
  run_runtime_gate_expect_fail daily-result-wrong-coverage "${daily_coverage_clone}"

  daily_quantile_clone="$(clone_fixture daily-wrong-quantile)"
  cat >>"${daily_quantile_clone}/backend/app/forecast_quality/calculator_daily.py" <<'PY'
_round_a_original_compute_daily_metrics = compute_daily_metrics
def compute_daily_metrics(evaluation_input, breakdown_spec):
    result = _round_a_original_compute_daily_metrics(evaluation_input, breakdown_spec)
    return dataclasses.replace(result, metric_input_quantile=SupportedQuantile.P80)
PY
  run_runtime_gate_expect_fail daily-result-wrong-input-quantile "${daily_quantile_clone}"

  daily_unique_clone="$(clone_fixture daily-wrong-unique-actual)"
  cat >>"${daily_unique_clone}/backend/app/forecast_quality/calculator_daily.py" <<'PY'
_round_a_original_compute_daily_metrics = compute_daily_metrics
def compute_daily_metrics(evaluation_input, breakdown_spec):
    result = _round_a_original_compute_daily_metrics(evaluation_input, breakdown_spec)
    return dataclasses.replace(
        result,
        unique_actual_physical_row_count=result.unique_actual_physical_row_count + 1,
    )
PY
  run_runtime_gate_expect_fail daily-result-wrong-unique-actual-count "${daily_unique_clone}"

  daily_mape_clone="$(clone_fixture daily-wrong-mape-counters)"
  cat >>"${daily_mape_clone}/backend/app/forecast_quality/calculator_daily.py" <<'PY'
_round_a_original_compute_daily_metrics = compute_daily_metrics
def compute_daily_metrics(evaluation_input, breakdown_spec):
    result = _round_a_original_compute_daily_metrics(evaluation_input, breakdown_spec)
    return dataclasses.replace(result, mape_eligible_row_count=result.mape_eligible_row_count + 1)
PY
  run_runtime_gate_expect_fail daily-result-wrong-mape-counters "${daily_mape_clone}"

  daily_breakdown_clone="$(clone_fixture daily-wrong-breakdown)"
  cat >>"${daily_breakdown_clone}/backend/app/forecast_quality/calculator_daily.py" <<'PY'
_round_a_original_compute_daily_metrics = compute_daily_metrics
def compute_daily_metrics(evaluation_input, breakdown_spec):
    result = _round_a_original_compute_daily_metrics(evaluation_input, breakdown_spec)
    identity = dict(result.breakdown_identity)
    identity["model_identity"] = "wrong-model"
    return dataclasses.replace(result, breakdown_identity=identity)
PY
  run_runtime_gate_expect_fail daily-result-wrong-breakdown-identity "${daily_breakdown_clone}"

  daily_mask_clone="$(clone_fixture daily-wrong-mask)"
  cat >>"${daily_mask_clone}/backend/app/forecast_quality/calculator_daily.py" <<'PY'
_round_a_original_compute_daily_metrics = compute_daily_metrics
def compute_daily_metrics(evaluation_input, breakdown_spec):
    result = _round_a_original_compute_daily_metrics(evaluation_input, breakdown_spec)
    return dataclasses.replace(result, metric_input_mask_hash="0" * 64)
PY
  run_runtime_gate_expect_fail daily-result-wrong-metric-mask-hash "${daily_mask_clone}"

  daily_hash_clone="$(clone_fixture daily-wrong-canonical-hash)"
  cat >>"${daily_hash_clone}/backend/app/forecast_quality/calculator_daily.py" <<'PY'
_round_a_original_compute_daily_metrics = compute_daily_metrics
def compute_daily_metrics(evaluation_input, breakdown_spec):
    result = _round_a_original_compute_daily_metrics(evaluation_input, breakdown_spec)
    return dataclasses.replace(result, canonical_hash="0" * 64)
PY
  run_runtime_gate_expect_fail daily-result-wrong-canonical-hash "${daily_hash_clone}"

  printf 'AUTHORIZED_CREATE_PATH_COUNT=26\n'
  printf 'AUTHORIZED_MANIFEST_RECORD_COUNT=26\n'
  printf 'AUTHORIZED_MANIFEST_METADATA_LINE_COUNT=4\n'
  printf 'AUTHORIZED_MANIFEST_INVALID_RECORD_COUNT=0\n'
  printf 'AUTHORIZED_METADATA_PARSED_AS_PATH_COUNT=0\n'
  printf 'POSITIVE_GATE_EXECUTION_COUNT=%s\n' "${positive_gate_count}"
  printf 'POSITIVE_GATE_PASS_COUNT=%s\n' "${positive_gate_count}"
  printf 'NEGATIVE_GATE_EXECUTION_COUNT=%s\n' "${negative_gate_count}"
  printf 'NEGATIVE_FIXTURE_EXPECTED_FAILURE_COUNT=%s\n' "${negative_expected}"
  printf 'NEGATIVE_EXPECTED_FAILURE_COUNT=%s\n' "${negative_expected}"
  printf 'NEGATIVE_FIXTURE_UNEXPECTED_PASS_COUNT=%s\n' "${unexpected_pass}"
  printf 'NEGATIVE_UNEXPECTED_PASS_COUNT=%s\n' "${unexpected_pass}"
  test "${unexpected_pass}" = "0"
  printf 'PACKAGE_GATE_SELF_TEST_RESULT=PASS\n'
}

if [[ "${PACKAGE_SELF_TEST:-0}" == "1" && "${PACKAGE_SELF_TEST_INTERNAL:-0}" != "1" ]]; then
  run_package_self_test
  exit 0
fi

: "${IMPLEMENTATION_BASE_SHA:?IMPLEMENTATION_BASE_SHA is required}"
ROUND_A_WORKTREE="${ROUND_A_WORKTREE:-$(git rev-parse --show-toplevel)}"
PACKAGE_DIR="${PACKAGE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ROUND_A_WORKTREE="$(cd "${ROUND_A_WORKTREE}" && pwd -P)"
AUTHORIZED_FILE="${PACKAGE_DIR}/authorized-paths.txt"
PACKAGE_SHA_FILE="${PACKAGE_DIR}/acceptance/SHA256SUMS"

cd "${ROUND_A_WORKTREE}"
test "$(git rev-parse --show-toplevel)" = "${ROUND_A_WORKTREE}"
git cat-file -e "${IMPLEMENTATION_BASE_SHA}^{commit}"
git merge-base --is-ancestor "${IMPLEMENTATION_BASE_SHA}" HEAD
git cat-file -e "${IMPLEMENTATION_BASE_SHA}:${PACKAGE_REPOSITORY_ROOT}/README.md"
test -f "${AUTHORIZED_FILE}"
test -f "${PACKAGE_SHA_FILE}"
validate_hash_records "${ROUND_A_WORKTREE}" "${IMPLEMENTATION_BASE_SHA}" "${PACKAGE_SHA_FILE}"

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/s3-round-a-path-gate.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT
parse_authorized_manifest "${AUTHORIZED_FILE}" | sort -u >"${tmp_dir}/authorized.txt"
metadata_count="$(manifest_metadata_count "${AUTHORIZED_FILE}")"
invalid_count="$(manifest_invalid_count "${AUTHORIZED_FILE}")"
metadata_parsed=0
while IFS= read -r metadata; do
  [ -n "${metadata}" ] || continue
  if grep -Fxq "${metadata}" "${tmp_dir}/authorized.txt"; then
    metadata_parsed=$((metadata_parsed + 1))
  fi
done < <(grep -E '^[A-Z0-9_]+=.*$' "${AUTHORIZED_FILE}" || true)

git diff --name-only "${IMPLEMENTATION_BASE_SHA}..HEAD" | sort -u >"${tmp_dir}/committed.txt"
git diff --cached --name-only | sort -u >"${tmp_dir}/staged.txt"
git diff --name-only | sort -u >"${tmp_dir}/unstaged.txt"
git ls-files --others --exclude-standard | sort -u >"${tmp_dir}/untracked.txt"
cat "${tmp_dir}/committed.txt" "${tmp_dir}/staged.txt" "${tmp_dir}/unstaged.txt" "${tmp_dir}/untracked.txt" | sort -u >"${tmp_dir}/actual.txt"
comm -23 "${tmp_dir}/authorized.txt" "${tmp_dir}/actual.txt" >"${tmp_dir}/missing.txt" || true
comm -13 "${tmp_dir}/authorized.txt" "${tmp_dir}/actual.txt" >"${tmp_dir}/unauthorized.txt" || true

modified_base_count=0
while IFS= read -r path; do
  [ -n "${path}" ] || continue
  if git cat-file -e "${IMPLEMENTATION_BASE_SHA}:${path}" 2>/dev/null; then
    modified_base_count=$((modified_base_count + 1))
  fi
done <"${tmp_dir}/actual.txt"
deleted_count="$(git diff --diff-filter=D --name-only "${IMPLEMENTATION_BASE_SHA}..HEAD" | wc -l | tr -d ' ')"

blocked_prefixes=(
  "backend/app/forecast_quality/calculator_cumulative.py"
  "backend/app/forecast_quality/peak.py"
  "backend/app/forecast_quality/quantile.py"
  "backend/app/forecast_quality/comparison.py"
  "backend/app/forecast_quality/persistence.py"
  "backend/app/forecast_quality/repository.py"
  "backend/app/forecast_quality/application.py"
  "backend/app/models/"
  "backend/app/api/"
  "backend/api/"
  "backend/alembic/"
  "backend/tests/integration/"
  ".github/workflows/"
  "ci-shard-manifest.yml"
)
is_blocked_path() {
  local candidate="$1" blocked
  for blocked in "${blocked_prefixes[@]}"; do
    if [[ "${blocked}" == */ ]]; then
      [[ "${candidate}" == "${blocked}"* ]] && return 0
    else
      [[ "${candidate}" == "${blocked}" ]] && return 0
    fi
  done
  return 1
}
: >"${tmp_dir}/blocked.txt"
while IFS= read -r path; do
  [ -n "${path}" ] || continue
  is_blocked_path "${path}" && printf '%s\n' "${path}" >>"${tmp_dir}/blocked.txt"
done <"${tmp_dir}/actual.txt"
sort -u -o "${tmp_dir}/blocked.txt" "${tmp_dir}/blocked.txt"

authorized_count="$(wc -l <"${tmp_dir}/authorized.txt" | tr -d ' ')"
actual_count="$(wc -l <"${tmp_dir}/actual.txt" | tr -d ' ')"
missing_count="$(wc -l <"${tmp_dir}/missing.txt" | tr -d ' ')"
unauthorized_count="$(wc -l <"${tmp_dir}/unauthorized.txt" | tr -d ' ')"
blocked_count="$(wc -l <"${tmp_dir}/blocked.txt" | tr -d ' ')"

printf 'AUTHORIZED_MANIFEST_RECORD_COUNT=%s\n' "${authorized_count}"
printf 'AUTHORIZED_MANIFEST_METADATA_LINE_COUNT=%s\n' "${metadata_count}"
printf 'AUTHORIZED_MANIFEST_INVALID_RECORD_COUNT=%s\n' "${invalid_count}"
printf 'AUTHORIZED_METADATA_PARSED_AS_PATH_COUNT=%s\n' "${metadata_parsed}"
printf 'AUTHORIZED_CREATE_PATH_COUNT=%s\n' "${authorized_count}"
printf 'ACTUAL_UNION_PATH_COUNT=%s\n' "${actual_count}"
printf 'MISSING_AUTHORIZED_PATH_COUNT=%s\n' "${missing_count}"
printf 'UNAUTHORIZED_PATH_COUNT=%s\n' "${unauthorized_count}"
printf 'MODIFIED_BASE_PATH_COUNT=%s\n' "${modified_base_count}"
printf 'DELETED_PATH_COUNT=%s\n' "${deleted_count}"
printf 'BLOCKED_PATH_PRESENT_COUNT=%s\n' "${blocked_count}"
printf 'AUTHORIZED_PATH_LIST_BEGIN\n'; cat "${tmp_dir}/authorized.txt"; printf 'AUTHORIZED_PATH_LIST_END\n'
printf 'ACTUAL_PATH_LIST_BEGIN\n'; cat "${tmp_dir}/actual.txt"; printf 'ACTUAL_PATH_LIST_END\n'

test "${authorized_count}" = "26"
test "${metadata_count}" = "4"
test "${invalid_count}" = "0"
test "${metadata_parsed}" = "0"
test "${actual_count}" = "26"
test "${missing_count}" = "0"
test "${unauthorized_count}" = "0"
test "${modified_base_count}" = "0"
test "${deleted_count}" = "0"
test "${blocked_count}" = "0"
printf 'PATH_SCOPE_ACCEPTANCE=PASS\n'
