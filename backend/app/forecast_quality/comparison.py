"""Round C model-versus-baseline comparison domain.

This module is intentionally the only owner of Round C comparison symbols.  It
consumes the immutable S3 binding rows and explicit baseline evidence records;
it never discovers evidence from persistence or associates rows by position.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum
from typing import Any

from .calculator_daily import compute_daily_metrics
from .canonical import canonical_json_bytes
from .enums import (
    ComparisonAvailability,
    FrozenVersion,
    MetricStatus,
    ReasonCode,
    SupportedQuantile,
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

COMPARISON_POLICY_VERSION = "v0.2-s3-comparison-policy-v1"
COMPARISON_RESULT_SCHEMA_VERSION = "v0.2-s3-comparison-result-v1"
BASELINE_MEMBER_SET_SCHEMA_VERSION = "v0.2-s3-comparison-baseline-member-set-v1"
COMPARISON_RESULT_SET_SCHEMA_VERSION = "v0.2-s3-comparison-result-set-v2"
ROUND_C_PERSISTENCE_SCHEMA_VERSION = "v0.2-s3-quality-persistence-v2"
LEGACY_PERSISTENCE_SCHEMA_VERSION = "v0.2-s3-quality-persistence-v1"
DECIMAL_QUANTUM = Decimal("0.000001")
MIN_COMPARABLE_ROWS_FOR_REPORTING = 10


class ComparisonName(StrEnum):
    DAILY_MAE_DELTA = "daily_mae_delta"
    DAILY_WAPE_DELTA = "daily_wape_delta"
    DAILY_SMAPE_DELTA = "daily_smape_delta"
    DAILY_MAPE_DELTA = "daily_mape_delta"
    ABSOLUTE_BIAS_MAGNITUDE_DELTA = "absolute_bias_magnitude_delta"
    SIGNED_BIAS_DELTA = "signed_bias_delta"
    P80_COVERAGE_DELTA = "p80_coverage_delta"
    P90_COVERAGE_DELTA = "p90_coverage_delta"
    BASELINE_P80_P90_PEAK_COMPARISON = "baseline_p80_p90_peak_comparison"
    INTERVAL_WIDTH_DELTA = "interval_width_delta"


# Metric name mapping: comparison delta → Round A calculator cell name.  Round C
# reuses the Round A daily metric calculator as the single source of truth for
# MAE / WAPE / sMAPE / MAPE / bias.  No local formula may exist.
_ROUND_A_CALCULATOR_METRIC_NAMES: dict[ComparisonName, str] = {
    ComparisonName.DAILY_MAE_DELTA: "daily_mae",
    ComparisonName.DAILY_WAPE_DELTA: "daily_wape",
    ComparisonName.DAILY_SMAPE_DELTA: "daily_smape",
    ComparisonName.DAILY_MAPE_DELTA: "daily_mape",
    ComparisonName.SIGNED_BIAS_DELTA: "daily_bias_kg",
}


# ComparisonName values that come from a calculator cell.  Names not listed
# here (e.g. ABSOLUTE_BIAS_MAGNITUDE_DELTA = |signed_bias|) must be derived
# from a calculator cell via the HALF_EVEN projection rule below.
_CALCULATOR_DERIVED_NAMES: frozenset[ComparisonName] = frozenset(
    _ROUND_A_CALCULATOR_METRIC_NAMES
)


class ComparisonContractError(ValueError):
    """A structural or contract error in the comparison input graph."""


class ComparisonStructuralFailure(ComparisonContractError):
    """The comparison graph is duplicate, contradictory, or self-inconsistent."""


@dataclass(frozen=True)
class ComparisonInputRow:
    """Validated row-level input used by the common-set calculation."""

    comparison_daily_key: dict[str, Any]
    forecast_value_kg: Decimal | None
    actual_value_kg: Decimal | None
    s2_status: str


@dataclass(frozen=True)
class ComparisonBaselineRecord:
    request: BaselineRequest
    snapshot: BaselineSourceSnapshot
    result: BaselineResult


@dataclass(frozen=True)
class ComparisonResult:
    schema_version: str
    comparison_policy_version: str
    comparison_name: ComparisonName
    comparison_availability: ComparisonAvailability
    metric_status: MetricStatus
    reason_code: ReasonCode
    model_identity: str
    baseline_member_identity_set: list[dict[str, Any]]
    baseline_member_set_hash: str
    normalized_breakdown_identity: dict[str, Any]
    forecast_horizon_days: int
    model_value: Decimal | None
    baseline_value: Decimal | None
    delta_value: Decimal | None
    model_input_row_count: int
    baseline_input_row_count: int
    common_comparable_row_count: int
    model_only_row_count: int
    baseline_only_row_count: int
    excluded_row_count: int
    not_computable_row_count: int
    external_blocker: str | None
    frozen_limitation: str | None
    comparison_key_hash: str
    canonical_payload: dict[str, Any]
    canonical_hash: str


def _json_ready(value: Any) -> Any:
    return __import__("json").loads(canonical_json_bytes(value).decode("utf-8"))


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _six_axis_identity(spec: BreakdownSpec) -> dict[str, Any]:
    return {
        "forecast_horizon_days": spec.forecast_horizon_days,
        "farm_business_key": spec.farm_business_key,
        "subfarm_business_key": spec.subfarm_business_key,
        "variety_business_key": spec.variety_business_key,
        "season_business_key": spec.season_business_key,
        "model_identity": spec.model_identity,
    }


def _daily_key(
    *,
    current_target_date: date,
    current_forecast_cutoff_at: datetime,
    farm_business_key: str,
    subfarm_business_key: str,
    variety_business_key: str,
    metric_policy_version: Any,
    baseline_policy_version: Any,
) -> dict[str, Any]:
    return {
        "current_target_date": current_target_date.isoformat(),
        "current_forecast_cutoff_at": current_forecast_cutoff_at.isoformat(),
        "farm_business_key": farm_business_key,
        "subfarm_business_key": subfarm_business_key,
        "variety_business_key": variety_business_key,
        "metric_policy_version": _enum_value(metric_policy_version),
        "baseline_policy_version": _enum_value(baseline_policy_version),
    }


def _daily_key_bytes(key: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(key)


def _model_daily_key(row: S3BindingRow, evaluation_input: S3EvaluationInput) -> dict[str, Any]:
    return _daily_key(
        current_target_date=row.forecast_target_date,
        current_forecast_cutoff_at=row.forecast_cutoff_at,
        farm_business_key=row.farm_business_key,
        subfarm_business_key=row.subfarm_business_key,
        variety_business_key=row.variety_business_key,
        metric_policy_version=evaluation_input.metric_policy_version,
        baseline_policy_version=evaluation_input.baseline_policy_version,
    )


def _validate_key_shape(key: Any, field: str) -> dict[str, Any]:
    if not isinstance(key, Mapping):
        raise ComparisonStructuralFailure(f"{field} must be a JSON object")
    expected = {
        "current_target_date",
        "current_forecast_cutoff_at",
        "farm_business_key",
        "subfarm_business_key",
        "variety_business_key",
        "metric_policy_version",
        "baseline_policy_version",
    }
    if set(key) != expected:
        raise ComparisonStructuralFailure(f"{field} must contain exactly seven keys")
    return dict(key)


def _baseline_member(record: ComparisonBaselineRecord) -> tuple[dict[str, Any], dict[str, Any]]:
    request = record.request
    snapshot = record.snapshot
    result = record.result
    if _enum_value(request.requested_quantile) != "P50":
        raise ComparisonContractError("BASELINE_QUANTILE=P50 is required")
    if _enum_value(result.baseline_quantile) != "P50":
        raise ComparisonContractError("baseline result quantile must be P50")
    if not isinstance(request.current_forecast_cutoff_at, datetime):
        raise ComparisonContractError("baseline cutoff must be a datetime")
    if request.current_forecast_cutoff_at.tzinfo is None:
        raise ComparisonContractError("baseline cutoff must be timezone-aware")
    request_payload = _json_ready(dataclasses.asdict(request))
    request_hash = _hash(request_payload)
    result_hash = _enum_value(result.canonical_hash)
    if (
        not isinstance(result_hash, str)
        or len(result_hash) != 64
        or result_hash.lower() != result_hash
        or any(char not in "0123456789abcdef" for char in result_hash)
    ):
        raise ComparisonContractError("baseline result canonical hash must be lowercase SHA-256")
    member_key = _daily_key(
        current_target_date=request.current_target_date,
        current_forecast_cutoff_at=request.current_forecast_cutoff_at,
        farm_business_key=request.farm_business_key,
        subfarm_business_key=request.subfarm_business_key,
        variety_business_key=request.variety_business_key,
        metric_policy_version=request.metric_policy_version,
        baseline_policy_version=request.baseline_policy_version,
    )
    member = {
        "comparison_daily_key": member_key,
        "baseline_request_hash": request_hash,
        "baseline_result_hash": result_hash,
        "baseline_source_snapshot_identity": snapshot.source_snapshot_identity,
        "baseline_source_snapshot_hash": snapshot.source_snapshot_hash,
        "baseline_source_row_set_hash": snapshot.source_row_set_hash,
        "visibility_manifest_hash": snapshot.visibility_manifest_hash,
        "baseline_policy_version": _enum_value(request.baseline_policy_version),
    }
    return member, member_key


def _member_set(records: Sequence[ComparisonBaselineRecord]) -> tuple[list[dict[str, Any]], str]:
    if not records:
        raise ComparisonStructuralFailure("baseline member set must be nonempty")
    members: list[dict[str, Any]] = []
    seen: set[bytes] = set()
    for record in records:
        member, key = _baseline_member(record)
        key_bytes = _daily_key_bytes(key)
        if key_bytes in seen:
            raise ComparisonStructuralFailure("duplicate baseline semantic daily key")
        seen.add(key_bytes)
        members.append(member)
    members.sort(key=lambda item: _daily_key_bytes(item["comparison_daily_key"]))
    payload = {
        "members": members,
        "schema_version": BASELINE_MEMBER_SET_SCHEMA_VERSION,
    }
    return members, _hash(payload)


def _validate_baseline_against_spec(
    record: ComparisonBaselineRecord,
    breakdown_spec: BreakdownSpec,
) -> None:
    request = record.request
    if not (
        request.current_season_start <= request.current_target_date <= request.current_season_end
    ):
        raise ComparisonContractError("current_target_date is outside declared current season")
    for field in ("farm_business_key", "subfarm_business_key", "variety_business_key"):
        if getattr(request, field) != getattr(breakdown_spec, field):
            raise ComparisonContractError("baseline identity conflicts with breakdown cell")
    if _enum_value(request.metric_policy_version) == "":
        raise ComparisonContractError("baseline metric policy is required")
    if _enum_value(request.baseline_policy_version) == "":
        raise ComparisonContractError("baseline policy is required")


def _validate_model_rows(
    evaluation_input: S3EvaluationInput,
    breakdown_spec: BreakdownSpec,
) -> dict[bytes, S3BindingRow]:
    candidates: dict[bytes, S3BindingRow] = {}
    for row in evaluation_input.rows:
        if row.forecast_quantile != SupportedQuantile.P50:
            continue
        if any(
            getattr(row, field) != getattr(breakdown_spec, field)
            for field in (
                "forecast_horizon_days",
                "farm_business_key",
                "subfarm_business_key",
                "variety_business_key",
                "season_business_key",
                "model_identity",
            )
        ):
            continue
        key = _model_daily_key(row, evaluation_input)
        key_bytes = _daily_key_bytes(key)
        if key_bytes in candidates:
            raise ComparisonStructuralFailure("duplicate or contradictory model semantic daily key")
        candidates[key_bytes] = row
    return candidates


def _baseline_record_map(
    records: Sequence[ComparisonBaselineRecord],
) -> dict[bytes, ComparisonBaselineRecord]:
    result: dict[bytes, ComparisonBaselineRecord] = {}
    for record in records:
        member, key = _baseline_member(record)
        key_bytes = _daily_key_bytes(key)
        if key_bytes in result:
            raise ComparisonStructuralFailure("duplicate or contradictory baseline evidence")
        result[key_bytes] = record
    return result


def _numeric_baseline(record: ComparisonBaselineRecord) -> bool:
    return (
        record.result.metric_status == MetricStatus.COMPUTED
        and record.result.baseline_point_forecast_kg is not None
    )


def _numeric_model(row: S3BindingRow) -> bool:
    return (
        row.s2_status == "COMPARABLE"
        and row.forecast_value_kg is not None
        and row.actual_value_kg is not None
    )


def _calculator_cell_value(
    result: DailyMetricResult,
    cell_name: str,
) -> tuple[Decimal | None, ReasonCode | None]:
    """Read a canonical metric value out of a Round A calculator result.

    Returns (value, reason).  ``value`` is the calculator-quantized value
    (``DECIMAL_QUANTUM``).  ``reason`` is propagated from the calculator cell
    so downstream truth-table comparisons match the database ``reason_code``.
    """
    for cell in result.metric_cells:
        if cell.metric_name == cell_name:
            return cell.metric_value, cell.reason_code
    raise ComparisonContractError(
        f"Round A calculator did not emit expected cell '{cell_name}'"
    )


def _calculator_inputs(
    rows: Sequence[S3BindingRow],
    *,
    side: str,
    baseline_lookup: Mapping[bytes, ComparisonBaselineRecord],
    model_keys: set[bytes],
    evaluation_input: S3EvaluationInput,
) -> S3EvaluationInput:
    """Build a calculator S3EvaluationInput for one side (model or baseline).

    Each side calls ``compute_daily_metrics`` on its own forecast series but
    always against the same actuals.  ``baseline_lookup`` and ``model_keys``
    constrain rows to the COMMON_COMPARABLE_SET (excluded/not_computable
    rows are dropped on the calculator side too).
    """
    rebuilt: list[S3BindingRow] = []
    for row in rows:
        key = _daily_key_bytes(_model_daily_key(row, evaluation_input))
        baseline_record = baseline_lookup.get(key)
        if row.s2_status in {"EXCLUDED", "NOT_COMPARABLE"}:
            continue
        if baseline_record is None:
            continue
        if key not in model_keys:
            continue
        if not _numeric_baseline(baseline_record):
            continue
        if not _numeric_model(row):
            continue
        if side == "baseline":
            forecast = baseline_record.result.baseline_point_forecast_kg
            assert forecast is not None
        else:
            forecast = row.forecast_value_kg
            assert forecast is not None
        rebuilt.append(dataclasses.replace(row, forecast_value_kg=forecast))
    return dataclasses.replace(evaluation_input, rows=tuple(rebuilt))


_ROW_TEMPLATE_INPUT = S3EvaluationInput(
    rows=(),
    s2_run_identity="round-c-side-template",
    s2_manifest_identity="round-c-side-template",
    s2_binding_row_set_hash="round-c-side-template",
    metric_policy_version=FrozenVersion.METRIC_INPUT_MASK_V1,
    baseline_policy_version=FrozenVersion.SEASON_ANALOG_MAPPING_V1,
)


def _baseline_round_trip_replay(
    records: Sequence[ComparisonBaselineRecord],
) -> None:
    """Recompute and verify BaselineResult.canonical_hash for every record.

    Each ``BaselineResult`` carries an embedded ``canonical_hash`` that was
    sealed when the evidence was built.  Comparison arithmetic may only run
    after every supplied record has been replayed and matched.  Any drift
    between the replayed payload hash and the stored ``canonical_hash``
    (e.g. forecast value tampered after sealing) raises
    :class:`ComparisonStructuralFailure`.

    Quantile and snapshot identity checks raise :class:`ComparisonContractError`
    because they reflect evidence-shape errors, not replay failures.
    """
    for record in records:
        result = record.result
        if result.baseline_quantile != SupportedQuantile.P50.value:
            raise ComparisonContractError(
                f"BASELINE_QUANTILE=P50 is required (got "
                f"{result.baseline_quantile!r})"
            )
        if not result.source_snapshot_identity:
            raise ComparisonContractError(
                "BaselineResult.source_snapshot_identity is empty"
            )
        if not result.source_snapshot_hash:
            raise ComparisonContractError(
                "BaselineResult.source_snapshot_hash is empty"
            )
        if not result.source_row_set_hash:
            raise ComparisonContractError(
                "BaselineResult.source_row_set_hash is empty"
            )
        if not result.visibility_manifest_hash:
            raise ComparisonContractError(
                "BaselineResult.visibility_manifest_hash is empty"
            )
        payload = dataclasses.asdict(result)
        payload["canonical_hash"] = ""
        replayed = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        if replayed != result.canonical_hash:
            raise ComparisonStructuralFailure(
                f"BaselineResult canonical_hash replay failed for "
                f"{result.source_snapshot_identity}"
            )


def _half_even_delta(
    model_value: Decimal | None,
    baseline_value: Decimal | None,
) -> Decimal | None:
    """Apply the HALF_EVEN projection oracle.

    The brief mandates that ``delta_value`` equal ``quantize(model - baseline,
    DECIMAL_QUANTUM, ROUND_HALF_EVEN)``.  This is the only projection rule
    Round C arithmetic is allowed to use.
    """
    if model_value is None or baseline_value is None:
        return None
    return (model_value - baseline_value).quantize(DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN)


def _round_c_metric_outputs(
    rows: Sequence[S3BindingRow],
    breakdown_spec: BreakdownSpec,
    baseline_records: Sequence[ComparisonBaselineRecord],
    model_keys: set[bytes],
    evaluation_input: S3EvaluationInput,
) -> dict[ComparisonName, tuple[Decimal | None, ReasonCode | None]]:
    """Compute Round A calculator outputs for both sides and project to deltas.

    Calls :func:`compute_daily_metrics` once per side (model / baseline) on
    the COMMON_COMPARABLE_SET rows.  Reads canonical values from the
    calculator cells, applies the HALF_EVEN projection oracle, and emits
    one output per ComparisonName.  Local metric formulas are forbidden.
    """
    baseline_lookup = _baseline_record_map(baseline_records)
    model_calculator_input = _calculator_inputs(
        rows,
        side="model",
        baseline_lookup=baseline_lookup,
        model_keys=model_keys,
        evaluation_input=evaluation_input,
    )
    baseline_calculator_input = _calculator_inputs(
        rows,
        side="baseline",
        baseline_lookup=baseline_lookup,
        model_keys=model_keys,
        evaluation_input=evaluation_input,
    )
    model_result = compute_daily_metrics(model_calculator_input, breakdown_spec)
    baseline_result = compute_daily_metrics(baseline_calculator_input, breakdown_spec)
    common_row_count = len(model_calculator_input.rows)
    output: dict[ComparisonName, tuple[Decimal | None, ReasonCode | None]] = {}
    for name in (
        ComparisonName.DAILY_MAE_DELTA,
        ComparisonName.DAILY_WAPE_DELTA,
        ComparisonName.DAILY_SMAPE_DELTA,
        ComparisonName.DAILY_MAPE_DELTA,
        ComparisonName.ABSOLUTE_BIAS_MAGNITUDE_DELTA,
        ComparisonName.SIGNED_BIAS_DELTA,
    ):
        if common_row_count == 0:
            # Round C collapses every calculator cell reason (WAPE_DENOMINATOR_ZERO,
            # NO_MAPE_ELIGIBLE_ROWS, etc.) to NO_S2_BINDING_ROWS when no rows are
            # comparable.  Domain surface is uniform across the six daily deltas.
            output[name] = (None, ReasonCode.NO_S2_BINDING_ROWS)
            continue
        if name == ComparisonName.ABSOLUTE_BIAS_MAGNITUDE_DELTA:
            signed_model_value, _ = _calculator_cell_value(
                model_result, _ROUND_A_CALCULATOR_METRIC_NAMES[
                    ComparisonName.SIGNED_BIAS_DELTA
                ]
            )
            signed_baseline_value, _ = _calculator_cell_value(
                baseline_result, _ROUND_A_CALCULATOR_METRIC_NAMES[
                    ComparisonName.SIGNED_BIAS_DELTA
                ]
            )
            if signed_model_value is None or signed_baseline_value is None:
                output[name] = (None, ReasonCode.NO_S2_BINDING_ROWS)
                continue
            model_value = abs(signed_model_value).quantize(
                DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN
            )
            baseline_value = abs(signed_baseline_value).quantize(
                DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN
            )
            delta_value = _half_even_delta(model_value, baseline_value)
            output[name] = (delta_value, None if delta_value is not None else ReasonCode.NO_S2_BINDING_ROWS)
            continue
        cell_name = _ROUND_A_CALCULATOR_METRIC_NAMES[name]
        model_value, _ = _calculator_cell_value(model_result, cell_name)
        baseline_value, _ = _calculator_cell_value(
            baseline_result, cell_name
        )
        delta_value = _half_even_delta(model_value, baseline_value)
        if delta_value is None:
            # When the calculator side itself rejected (zero denominators,
            # no eligible rows, etc.) propagate the calculator cell reason
            # verbatim.  Only the empty-common-row path collapses to
            # NO_S2_BINDING_ROWS to keep the Round C domain surface uniform.
            calculator_reason = (
                _calculator_cell_value(model_result, cell_name)[1]
                or _calculator_cell_value(baseline_result, cell_name)[1]
            )
            output[name] = (None, calculator_reason or ReasonCode.NO_S2_BINDING_ROWS)
        else:
            output[name] = (delta_value, None)
    return output


def _round_c_side_values(
    rows: Sequence[S3BindingRow],
    breakdown_spec: BreakdownSpec,
    baseline_records: Sequence[ComparisonBaselineRecord],
    model_keys: set[bytes],
    evaluation_input: S3EvaluationInput,
) -> tuple[
    dict[ComparisonName, Decimal | None],
    dict[ComparisonName, Decimal | None],
]:
    """Return (model_canonical_values, baseline_canonical_values).

    Each side reads canonical values straight from the Round A calculator;
    no projection or quantization step is applied here because the
    calculator already emits ``DECIMAL_QUANTUM``-aligned values.  These
    populate ``ComparisonResult.model_value`` / ``ComparisonResult.baseline_value``
    so the relational projection stores the exact canonical numbers that
    produced the delta.
    """
    baseline_lookup = _baseline_record_map(baseline_records)
    model_input = _calculator_inputs(
        rows,
        side="model",
        baseline_lookup=baseline_lookup,
        model_keys=model_keys,
        evaluation_input=evaluation_input,
    )
    baseline_input = _calculator_inputs(
        rows,
        side="baseline",
        baseline_lookup=baseline_lookup,
        model_keys=model_keys,
        evaluation_input=evaluation_input,
    )
    model_result = compute_daily_metrics(model_input, breakdown_spec)
    baseline_result = compute_daily_metrics(baseline_input, breakdown_spec)
    model_values: dict[ComparisonName, Decimal | None] = {}
    baseline_values: dict[ComparisonName, Decimal | None] = {}
    for name in (
        ComparisonName.DAILY_MAE_DELTA,
        ComparisonName.DAILY_WAPE_DELTA,
        ComparisonName.DAILY_SMAPE_DELTA,
        ComparisonName.DAILY_MAPE_DELTA,
        ComparisonName.SIGNED_BIAS_DELTA,
    ):
        cell_name = _ROUND_A_CALCULATOR_METRIC_NAMES[name]
        model_value, _ = _calculator_cell_value(model_result, cell_name)
        baseline_value, _ = _calculator_cell_value(baseline_result, cell_name)
        model_values[name] = model_value
        baseline_values[name] = baseline_value
    signed_model_value, _ = _calculator_cell_value(
        model_result, _ROUND_A_CALCULATOR_METRIC_NAMES[ComparisonName.SIGNED_BIAS_DELTA]
    )
    signed_baseline_value, _ = _calculator_cell_value(
        baseline_result, _ROUND_A_CALCULATOR_METRIC_NAMES[ComparisonName.SIGNED_BIAS_DELTA]
    )
    model_values[ComparisonName.ABSOLUTE_BIAS_MAGNITUDE_DELTA] = (
        abs(signed_model_value).quantize(DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN)
        if signed_model_value is not None
        else None
    )
    baseline_values[ComparisonName.ABSOLUTE_BIAS_MAGNITUDE_DELTA] = (
        abs(signed_baseline_value).quantize(DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN)
        if signed_baseline_value is not None
        else None
    )
    return model_values, baseline_values


def _status_for(
    name: ComparisonName,
    value: Decimal | None,
    reason: ReasonCode | None,
    common_count: int,
) -> tuple[MetricStatus, ReasonCode, ComparisonAvailability]:
    if value is None or reason is not None:
        return (
            MetricStatus.NOT_COMPUTABLE,
            reason or ReasonCode.NO_S2_BINDING_ROWS,
            ComparisonAvailability.AVAILABLE,
        )
    if common_count < MIN_COMPARABLE_ROWS_FOR_REPORTING:
        return (
            MetricStatus.INSUFFICIENT_SAMPLE,
            ReasonCode.BELOW_MINIMUM,
            ComparisonAvailability.AVAILABLE,
        )
    if name == ComparisonName.SIGNED_BIAS_DELTA:
        return (
            MetricStatus.COMPARED,
            ReasonCode.SIGNED_DIRECTION_ONLY,
            ComparisonAvailability.AVAILABLE,
        )
    return MetricStatus.COMPUTED, ReasonCode.NONE, ComparisonAvailability.AVAILABLE


def _comparison_key_hash(
    *,
    name: ComparisonName,
    baseline_member_set_hash: str,
    normalized_breakdown_identity: Mapping[str, Any],
) -> str:
    return _hash(
        {
            "comparison_result_schema_version": COMPARISON_RESULT_SCHEMA_VERSION,
            "comparison_policy_version": COMPARISON_POLICY_VERSION,
            "comparison_name": name.value,
            "baseline_member_set_hash": baseline_member_set_hash,
            "normalized_breakdown_identity": dict(normalized_breakdown_identity),
        }
    )


def _make_result(
    *,
    name: ComparisonName,
    model_value: Decimal | None,
    baseline_value: Decimal | None,
    delta_value: Decimal | None,
    metric_status: MetricStatus,
    reason_code: ReasonCode,
    availability: ComparisonAvailability,
    identity: dict[str, Any],
    members: list[dict[str, Any]],
    member_set_hash: str,
    counts: Mapping[str, int],
) -> ComparisonResult:
    key_hash = _comparison_key_hash(
        name=name,
        baseline_member_set_hash=member_set_hash,
        normalized_breakdown_identity=identity,
    )
    result = ComparisonResult(
        schema_version=COMPARISON_RESULT_SCHEMA_VERSION,
        comparison_policy_version=COMPARISON_POLICY_VERSION,
        comparison_name=name,
        comparison_availability=availability,
        metric_status=metric_status,
        reason_code=reason_code,
        model_identity=str(identity["model_identity"]),
        baseline_member_identity_set=members,
        baseline_member_set_hash=member_set_hash,
        normalized_breakdown_identity=identity,
        forecast_horizon_days=int(identity["forecast_horizon_days"]),
        model_value=None if model_value is None else _quantize(model_value),
        baseline_value=None if baseline_value is None else _quantize(baseline_value),
        delta_value=None if delta_value is None else _quantize(delta_value),
        model_input_row_count=counts["model_input_row_count"],
        baseline_input_row_count=counts["baseline_input_row_count"],
        common_comparable_row_count=counts["common_comparable_row_count"],
        model_only_row_count=counts["model_only_row_count"],
        baseline_only_row_count=counts["baseline_only_row_count"],
        excluded_row_count=counts["excluded_row_count"],
        not_computable_row_count=counts["not_computable_row_count"],
        external_blocker=None,
        frozen_limitation=None,
        comparison_key_hash=key_hash,
        canonical_payload={},
        canonical_hash="",
    )
    payload = _json_ready(dataclasses.asdict(result))
    payload["comparison_name"] = name.value
    payload["comparison_availability"] = availability.value
    payload["metric_status"] = metric_status.value
    payload["reason_code"] = reason_code.value
    payload["persistence_schema_version"] = ROUND_C_PERSISTENCE_SCHEMA_VERSION
    payload["comparison_key_hash"] = key_hash
    canonical_hash = _hash(payload)
    return dataclasses.replace(result, canonical_payload=payload, canonical_hash=canonical_hash)


def _make_blocked_result(
    *,
    name: ComparisonName,
    reason: ReasonCode,
    identity: dict[str, Any],
    members: list[dict[str, Any]],
    member_set_hash: str,
    counts: Mapping[str, int],
) -> ComparisonResult:
    key_hash = _comparison_key_hash(
        name=name,
        baseline_member_set_hash=member_set_hash,
        normalized_breakdown_identity=identity,
    )
    result = _make_result(
        name=name,
        model_value=None,
        baseline_value=None,
        delta_value=None,
        metric_status=MetricStatus.NOT_COMPUTABLE,
        reason_code=reason,
        availability=ComparisonAvailability.BLOCKED,
        identity=identity,
        members=members,
        member_set_hash=member_set_hash,
        counts=counts,
    )
    payload = dict(result.canonical_payload)
    payload["frozen_limitation"] = reason.value
    payload["external_blocker"] = None
    return dataclasses.replace(
        result,
        frozen_limitation=reason.value,
        canonical_payload=payload,
        canonical_hash=_hash(payload),
        comparison_key_hash=key_hash,
    )


def compute_model_baseline_comparisons(
    *,
    evaluation_input: S3EvaluationInput,
    breakdown_spec: BreakdownSpec,
    baseline_records: Sequence[ComparisonBaselineRecord],
) -> tuple[ComparisonResult, ...]:
    """Compute the complete ten-record comparison set for one breakdown cell."""
    if not baseline_records:
        raise ComparisonStructuralFailure("baseline member set must be nonempty")
    for record in baseline_records:
        _validate_baseline_against_spec(record, breakdown_spec)
    _baseline_round_trip_replay(baseline_records)
    members, member_set_hash = _member_set(baseline_records)
    model_rows = _validate_model_rows(evaluation_input, breakdown_spec)
    baseline_map = _baseline_record_map(baseline_records)
    for record in baseline_records:
        _, baseline_key = _baseline_member(record)
        if _daily_key_bytes(baseline_key) in model_rows:
            continue
        matching_target = [
            row
            for row in model_rows.values()
            if row.forecast_target_date.isoformat() == baseline_key["current_target_date"]
            and row.farm_business_key == baseline_key["farm_business_key"]
            and row.subfarm_business_key == baseline_key["subfarm_business_key"]
            and row.variety_business_key == baseline_key["variety_business_key"]
        ]
        if matching_target:
            raise ComparisonStructuralFailure(
                "baseline daily identity cutoff or policy projection mismatch"
            )
    model_keys = set(model_rows)
    baseline_keys = set(baseline_map)
    all_keys = model_keys | baseline_keys
    common_rows: list[tuple[Decimal, Decimal, Decimal]] = []
    excluded = 0
    not_computable = 0
    model_only = 0
    baseline_only = 0
    for key in sorted(all_keys):
        model = model_rows.get(key)
        baseline = baseline_map.get(key)
        if model is not None and model.s2_status in {"EXCLUDED", "NOT_COMPARABLE"}:
            excluded += 1
            continue
        if model is not None and not _numeric_model(model):
            not_computable += 1
            continue
        if baseline is not None and not _numeric_baseline(baseline):
            if model is not None:
                not_computable += 1
            else:
                baseline_only += 1
            continue
        if model is not None and baseline is not None:
            assert model.forecast_value_kg is not None
            assert model.actual_value_kg is not None
            assert baseline.result.baseline_point_forecast_kg is not None
            common_rows.append(
                (
                    model.forecast_value_kg,
                    baseline.result.baseline_point_forecast_kg,
                    model.actual_value_kg,
                )
            )
        elif model is not None:
            model_only += 1
        else:
            baseline_only += 1
    counts = {
        "model_input_row_count": len(model_rows),
        "baseline_input_row_count": len(baseline_map),
        "common_comparable_row_count": len(common_rows),
        "model_only_row_count": model_only,
        "baseline_only_row_count": baseline_only,
        "excluded_row_count": excluded,
        "not_computable_row_count": not_computable,
    }
    if len(all_keys) != (
        counts["common_comparable_row_count"]
        + model_only
        + baseline_only
        + excluded
        + not_computable
    ):
        raise ComparisonStructuralFailure("comparison common-set counters do not close")
    if len(common_rows) > len(model_rows) or len(common_rows) > len(baseline_map):
        raise ComparisonStructuralFailure("common-set counter exceeds input counter")
    identity = _six_axis_identity(breakdown_spec)
    metric_values = _round_c_metric_outputs(
        rows=tuple(model_rows.values()),
        breakdown_spec=breakdown_spec,
        baseline_records=baseline_records,
        model_keys=set(model_rows),
        evaluation_input=evaluation_input,
    )
    canonical_model_values, canonical_baseline_values = _round_c_side_values(
        rows=tuple(model_rows.values()),
        breakdown_spec=breakdown_spec,
        baseline_records=baseline_records,
        model_keys=set(model_rows),
        evaluation_input=evaluation_input,
    )
    results: list[ComparisonResult] = []
    for name in (
        ComparisonName.DAILY_MAE_DELTA,
        ComparisonName.DAILY_WAPE_DELTA,
        ComparisonName.DAILY_SMAPE_DELTA,
        ComparisonName.DAILY_MAPE_DELTA,
        ComparisonName.ABSOLUTE_BIAS_MAGNITUDE_DELTA,
        ComparisonName.SIGNED_BIAS_DELTA,
    ):
        value, reason = metric_values[name]
        status, final_reason, availability = _status_for(name, value, reason, len(common_rows))
        baseline_value = canonical_baseline_values.get(name)
        model_value = canonical_model_values.get(name)
        results.append(
            _make_result(
                name=name,
                model_value=model_value,
                baseline_value=baseline_value,
                delta_value=value,
                metric_status=status,
                reason_code=final_reason,
                availability=availability,
                identity=identity,
                members=members,
                member_set_hash=member_set_hash,
                counts=counts,
            )
        )
    results.extend(
        [
            _make_blocked_result(
                name=ComparisonName.P80_COVERAGE_DELTA,
                reason=ReasonCode.BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED,
                identity=identity,
                members=members,
                member_set_hash=member_set_hash,
                counts=counts,
            ),
            _make_blocked_result(
                name=ComparisonName.P90_COVERAGE_DELTA,
                reason=ReasonCode.BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED,
                identity=identity,
                members=members,
                member_set_hash=member_set_hash,
                counts=counts,
            ),
            _make_blocked_result(
                name=ComparisonName.BASELINE_P80_P90_PEAK_COMPARISON,
                reason=ReasonCode.BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED,
                identity=identity,
                members=members,
                member_set_hash=member_set_hash,
                counts=counts,
            ),
            _make_blocked_result(
                name=ComparisonName.INTERVAL_WIDTH_DELTA,
                reason=ReasonCode.PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE,
                identity=identity,
                members=members,
                member_set_hash=member_set_hash,
                counts=counts,
            ),
        ]
    )
    return tuple(results)


def build_comparison_result_set_payload(canonical_hashes: Sequence[str]) -> dict[str, Any]:
    hashes = sorted(canonical_hashes)
    if len(set(hashes)) != len(hashes):
        raise ComparisonContractError("comparison result hash set contains duplicates")
    for value in hashes:
        if (
            len(value) != 64
            or value.lower() != value
            or any(char not in "0123456789abcdef" for char in value)
        ):
            raise ComparisonContractError("comparison result set contains malformed hash")
    return {
        "record_count": len(hashes),
        "records": hashes,
        "schema_version": COMPARISON_RESULT_SET_SCHEMA_VERSION,
    }


def compute_comparison_result_set_hash(canonical_hashes: Sequence[str]) -> str:
    return _hash(build_comparison_result_set_payload(canonical_hashes))


__all__ = [
    "BASELINE_MEMBER_SET_SCHEMA_VERSION",
    "COMPARISON_POLICY_VERSION",
    "COMPARISON_RESULT_SCHEMA_VERSION",
    "COMPARISON_RESULT_SET_SCHEMA_VERSION",
    "ComparisonAvailability",
    "ComparisonBaselineRecord",
    "ComparisonContractError",
    "ComparisonInputRow",
    "ComparisonName",
    "ComparisonResult",
    "ComparisonStructuralFailure",
    "build_comparison_result_set_payload",
    "compute_comparison_result_set_hash",
    "compute_model_baseline_comparisons",
]
