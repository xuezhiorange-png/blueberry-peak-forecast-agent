"""Empirical upper-quantile coverage for P50/P80/P90 on frozen S3 binding rows.

This module implements the S3 contract coverage formula only. It does not
compute S1 binding ``coverage_ratio`` (comparable/total binding rows).
"""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .canonical import canonical_json_bytes, compute_metric_input_mask_hash
from .enums import FrozenVersion, MetricStatus, ReasonCode, SupportedQuantile
from .exceptions import S3ContractInvariantViolationError
from .schemas import BreakdownSpec, MetricValueCell, S3BindingRow, S3EvaluationInput

_KNOWN_S2_STATUSES = frozenset({"COMPARABLE", "EXCLUDED", "NOT_COMPARABLE", "NOT_COMPUTABLE"})
_COVERAGE_METRIC_NAMES: dict[SupportedQuantile, str] = {
    SupportedQuantile.P50: "p50_upper_coverage",
    SupportedQuantile.P80: "p80_upper_coverage",
    SupportedQuantile.P90: "p90_upper_coverage",
}
_TRAIN_VAL_SPLITS = frozenset({"TRAIN", "VALIDATION"})
TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1 = (
    "v0.2-s3-train-val-coverage-partition-authority-v1"
)
_ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSIONS: frozenset[str] = frozenset()


@dataclass(frozen=True)
class TrainValidationCoveragePartitionAuthority:
    """Typed partition authority bound to a lawful TRAIN/VALIDATION pairing package.

    Instances are accepted only when ``schema_version`` is issued by a future
    coverage-execution grant and all binding fields match the supplied
    ``S3EvaluationInput``. Caller-supplied labels alone are never sufficient.
    """

    schema_version: str
    pairing_package_identity: str
    s2_binding_row_set_hash: str
    permitted_partitions: tuple[str, ...]


def _is_sha256(value: str) -> bool:
    return (
        len(value) == 64
        and value.lower() == value
        and all(char in "0123456789abcdef" for char in value)
    )


def _train_validation_execution_blocker(
    evaluation_input: S3EvaluationInput | None,
    breakdown_specs: tuple[BreakdownSpec, ...],
    partition_authority: TrainValidationCoveragePartitionAuthority | None,
) -> str | None:
    if evaluation_input is None or not evaluation_input.rows:
        return "NO_LEGAL_TRAIN_VALIDATION_S3_BINDING_PAIRING_PACKAGE"
    if not breakdown_specs:
        return "NO_TRAIN_VALIDATION_BREAKDOWN_SPECS"
    if partition_authority is None:
        return "TRAIN_VALIDATION_PARTITION_AUTHORITY_MISSING"
    if not isinstance(partition_authority, TrainValidationCoveragePartitionAuthority):
        return "TRAIN_VALIDATION_PARTITION_AUTHORITY_UNBOUND"
    if (
        not partition_authority.schema_version.strip()
        or not partition_authority.pairing_package_identity.strip()
        or not partition_authority.s2_binding_row_set_hash.strip()
        or not partition_authority.permitted_partitions
    ):
        return "TRAIN_VALIDATION_PARTITION_AUTHORITY_UNBOUND"
    if not _is_sha256(partition_authority.pairing_package_identity):
        return "TRAIN_VALIDATION_PARTITION_AUTHORITY_UNBOUND"
    if not _is_sha256(partition_authority.s2_binding_row_set_hash):
        return "TRAIN_VALIDATION_PARTITION_AUTHORITY_UNBOUND"
    if partition_authority.s2_binding_row_set_hash != evaluation_input.s2_binding_row_set_hash:
        return "TRAIN_VALIDATION_PARTITION_AUTHORITY_BINDING_MISMATCH"
    partitions = frozenset(partition_authority.permitted_partitions)
    if "TEST" in partitions:
        return "TEST_PARTITION_AUTHORITY_FORBIDDEN"
    if not partitions <= _TRAIN_VAL_SPLITS:
        return "NON_TRAIN_VALIDATION_SPLIT_PRESENT"
    if partition_authority.schema_version not in _ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSIONS:
        return "TRAIN_VALIDATION_PARTITION_AUTHORITY_NOT_ISSUED"
    return None


def _quantize(value: Decimal) -> Decimal:
    from decimal import ROUND_HALF_EVEN

    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)


def _matches_breakdown(row: S3BindingRow, breakdown_spec: BreakdownSpec) -> bool:
    return all(
        getattr(row, field) == getattr(breakdown_spec, field)
        for field in (
            "forecast_horizon_days",
            "farm_business_key",
            "subfarm_business_key",
            "variety_business_key",
            "season_business_key",
            "model_identity",
        )
    )


def _is_exact_actual_paired(row: S3BindingRow) -> bool:
    forecast = row.forecast_value_kg
    actual = row.actual_value_kg
    if row.actual_physical_key is None or row.stable_actual_identity is None:
        return False
    if forecast is None or actual is None:
        return False
    if isinstance(forecast, float) or isinstance(actual, float):
        return False
    if not isinstance(forecast, Decimal) or not isinstance(actual, Decimal):
        return False
    return forecast.is_finite() and actual.is_finite()


def _coverage_mask_predicate(quantile: SupportedQuantile) -> str:
    return f"S2_STATUS_COMPARABLE AND FORECAST_QUANTILE_{quantile.value} AND EXACT_ACTUAL_PAIRED"


def _masked_rows(
    evaluation_input: S3EvaluationInput,
    breakdown_spec: BreakdownSpec,
    quantile: SupportedQuantile,
) -> list[S3BindingRow]:
    for row in evaluation_input.rows:
        if row.s2_status not in _KNOWN_S2_STATUSES:
            raise S3ContractInvariantViolationError(f"unknown S2 status: {row.s2_status}")
    return [
        row
        for row in evaluation_input.rows
        if row.s2_status == "COMPARABLE"
        and row.forecast_quantile == quantile
        and _is_exact_actual_paired(row)
        and _matches_breakdown(row, breakdown_spec)
    ]


@dataclass(frozen=True)
class QuantileUpperCoverageResult:
    metric_name: str
    forecast_quantile: SupportedQuantile
    breakdown_identity: dict[str, str | int]
    s2_binding_row_set_hash: str
    metric_input_mask_policy_version: FrozenVersion
    metric_input_mask_hash: str
    coverage_comparable_row_count: int
    covered_count: int
    metric_value: Decimal | None
    metric_status: MetricStatus
    reason_code: ReasonCode
    numerator: Decimal | None
    denominator: Decimal | None
    metric_cell: MetricValueCell
    canonical_hash: str


def compute_upper_quantile_coverage(
    evaluation_input: S3EvaluationInput,
    breakdown_spec: BreakdownSpec,
    quantile: SupportedQuantile,
) -> QuantileUpperCoverageResult:
    """Compute one empirical upper-quantile coverage cell for ``quantile``."""

    masked = _masked_rows(evaluation_input, breakdown_spec, quantile)
    denominator_count = len(masked)
    covered_count = 0
    for row in masked:
        actual = row.actual_value_kg
        forecast = row.forecast_value_kg
        if actual is not None and forecast is not None and actual <= forecast:
            covered_count += 1
    breakdown_identity: dict[str, str | int] = {
        "season_business_key": breakdown_spec.season_business_key,
        "farm_business_key": breakdown_spec.farm_business_key,
        "subfarm_business_key": breakdown_spec.subfarm_business_key,
        "variety_business_key": breakdown_spec.variety_business_key,
        "model_identity": breakdown_spec.model_identity,
        "forecast_horizon_days": breakdown_spec.forecast_horizon_days,
    }
    mask = {
        "metric_input_mask_policy_version": FrozenVersion.METRIC_INPUT_MASK_V1.value,
        "s2_status_predicate": "S2_STATUS_COMPARABLE",
        "forecast_quantile_predicate": quantile.value,
        "actual_pair_predicate": "EXACT_ACTUAL_PAIRED",
        "coverage_mask_predicate": _coverage_mask_predicate(quantile),
        "breakdown_identity": breakdown_identity,
        "source_row_set_identity": evaluation_input.s2_binding_row_set_hash,
    }
    mask_hash = compute_metric_input_mask_hash(mask)
    numerator = Decimal(covered_count)
    denominator = Decimal(denominator_count)
    if denominator_count == 0:
        coverage = None
        status = MetricStatus.NOT_COMPUTABLE
        reason = ReasonCode.NO_S2_BINDING_ROWS
    else:
        coverage = _quantize(numerator / denominator)
        status = MetricStatus.COMPUTED
        reason = ReasonCode.NONE
    metric_name = _COVERAGE_METRIC_NAMES[quantile]
    cell = MetricValueCell(
        metric_name=metric_name,
        metric_value=coverage,
        metric_status=status,
        reason_code=reason,
        numerator=numerator if denominator_count else None,
        denominator=denominator if denominator_count else None,
        mape_eligible_row_count=0,
        mape_zero_actual_row_count=0,
    )
    result = QuantileUpperCoverageResult(
        metric_name=metric_name,
        forecast_quantile=quantile,
        breakdown_identity=breakdown_identity,
        s2_binding_row_set_hash=evaluation_input.s2_binding_row_set_hash,
        metric_input_mask_policy_version=FrozenVersion.METRIC_INPUT_MASK_V1,
        metric_input_mask_hash=mask_hash,
        coverage_comparable_row_count=denominator_count,
        covered_count=covered_count,
        metric_value=coverage,
        metric_status=status,
        reason_code=reason,
        numerator=cell.numerator,
        denominator=cell.denominator,
        metric_cell=cell,
        canonical_hash="",
    )
    payload = dataclasses.asdict(result)
    payload["canonical_hash"] = ""
    canonical_hash = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return dataclasses.replace(result, canonical_hash=canonical_hash)


def compute_upper_quantile_coverage_bundle(
    evaluation_input: S3EvaluationInput,
    breakdown_spec: BreakdownSpec,
) -> tuple[QuantileUpperCoverageResult, QuantileUpperCoverageResult, QuantileUpperCoverageResult]:
    return (
        compute_upper_quantile_coverage(evaluation_input, breakdown_spec, SupportedQuantile.P50),
        compute_upper_quantile_coverage(evaluation_input, breakdown_spec, SupportedQuantile.P80),
        compute_upper_quantile_coverage(evaluation_input, breakdown_spec, SupportedQuantile.P90),
    )


@dataclass(frozen=True)
class TrainValCoverageExecutionAssessment:
    """Formal execution disposition for TRAIN/VALIDATION empirical coverage."""

    implementation_complete: Literal[True]
    execution_status: Literal["EXECUTED", "NOT_COMPUTABLE_OR_BLOCKED"]
    blocker_reason: str | None
    train_validation_only: bool
    test_remains_sealed: Literal[True]
    results: tuple[QuantileUpperCoverageResult, ...]


def assess_train_validation_coverage_execution(
    evaluation_input: S3EvaluationInput | None,
    *,
    breakdown_specs: tuple[BreakdownSpec, ...] = (),
    partition_authority: TrainValidationCoveragePartitionAuthority | None = None,
) -> TrainValCoverageExecutionAssessment:
    """Attempt lawful TRAIN/VALIDATION coverage execution when authority exists.

    Execution is fail-closed: a typed ``TrainValidationCoveragePartitionAuthority``
    bound to the pairing package and evaluation row-set hash is required. Main
    currently issues no partition authorities, so execution remains blocked.
    """

    blocker = _train_validation_execution_blocker(
        evaluation_input,
        breakdown_specs,
        partition_authority,
    )
    if blocker is not None:
        return TrainValCoverageExecutionAssessment(
            implementation_complete=True,
            execution_status="NOT_COMPUTABLE_OR_BLOCKED",
            blocker_reason=blocker,
            train_validation_only=blocker != "NON_TRAIN_VALIDATION_SPLIT_PRESENT",
            test_remains_sealed=True,
            results=(),
        )
    assert evaluation_input is not None
    results = [
        compute_upper_quantile_coverage(evaluation_input, spec, quantile)
        for spec in breakdown_specs
        for quantile in SupportedQuantile
    ]
    return TrainValCoverageExecutionAssessment(
        implementation_complete=True,
        execution_status="EXECUTED",
        blocker_reason=None,
        train_validation_only=True,
        test_remains_sealed=True,
        results=tuple(results),
    )


__all__ = [
    "QuantileUpperCoverageResult",
    "TrainValCoverageExecutionAssessment",
    "TrainValidationCoveragePartitionAuthority",
    "TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1",
    "assess_train_validation_coverage_execution",
    "compute_upper_quantile_coverage",
    "compute_upper_quantile_coverage_bundle",
]
