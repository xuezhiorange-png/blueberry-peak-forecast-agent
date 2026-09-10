"""Deterministic S4 guardrails and candidate execution preflight.

This module is deliberately independent from model execution.  It freezes the
common S4 comparison policy and provides pure in-memory checks that a future
candidate runner must pass before it can consume a validation budget unit.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal, cast

from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload

GUARDRAIL_POLICY_VERSION: Final[str] = "v0.3-s4-guardrail-policy-v1"
S4_A_EXPERIMENT_PLAN_HASH_BOUND: Final[str] = (
    "9e223a02a1b38c028c230a45eb1fa8323f3c2247bb85e7b439f3351e51042500"
)
EXPERIMENT_PLAN_VERSION: Final[str] = "v0.3-experiment-plan-v1"
EXPERIMENT_PLAN_V2_VERSION: Final[str] = "v0.3-experiment-plan-v2"
EXPERIMENT_PLAN_V2_HASH: Final[str] = (
    "c2bfab4ec38b4ca640f62d061494961c5b49afe5b52fa675326aa80fdf5f8ad9"
)
V2_GUARDRAIL_POLICY_VERSION: Final[str] = "v0.3-s4-guardrail-policy-v2"
V3_GUARDRAIL_POLICY_VERSION: Final[str] = "v0.3-s4-guardrail-policy-v3-sparse-horizon"
V4_GUARDRAIL_POLICY_VERSION: Final[str] = "v0.3-s4-guardrail-policy-v4-breakdown-reporting-floor"
V3_EVALUATION_SURFACE_ID: Final[str] = "V0_3_S4_SOURCE002_SPARSE_HORIZON_7_14_21_V1"
V3_FORECAST_HORIZONS: Final[tuple[int, ...]] = (7, 14, 21)
V3_COMPLETE_DAILY_ROWSET_AUTHORITY: Final[bool] = False
V3_MISSING_DAY_ZERO_FILL: Final[bool] = False
V4_PREDECESSOR_POLICY_VERSION: Final[str] = V3_GUARDRAIL_POLICY_VERSION
V2_HISTORICAL_DATA_ONLY: Final[bool] = True
V2_WEATHER_REQUIRED: Final[bool] = False
V2_PRODUCTION_PLAN_REQUIRED: Final[bool] = False
V2_TASK8_TASK9_REQUIRED: Final[bool] = False
V2_PROSPECTIVE_CAPTURE_REQUIRED: Final[bool] = False
V2_WALL_CLOCK_WAIT_REQUIRED: Final[bool] = False
V2_TEST_REMAINS_SEALED: Final[bool] = True
V2_FORECAST_HORIZONS: Final[tuple[int, ...]] = (7, 14, 21)
V2_CANDIDATE_06_EXECUTION_ELIGIBLE: Final[bool] = False
V2_CANDIDATE_08_EXECUTION_ELIGIBLE: Final[bool] = False
V2_CANDIDATE_01_RERUN_FORBIDDEN: Final[bool] = True
V2_LEGACY_RECONCILED_VALIDATION_DEBIT: Final[int] = 4
# Freeze-point evidence only. PostgreSQL remains the durable validation-budget authority.
V2_BUDGET_SNAPSHOT_CANONICAL_STARTED_COUNT: Final[int] = 0
V2_BUDGET_SNAPSHOT_EFFECTIVE_CONSUMED: Final[int] = 4
V2_BUDGET_SNAPSHOT_REMAINING_VALIDATION_EVALUATIONS: Final[int] = 28
METRIC_CONTRACT_VERSION: Final[str] = "v0.3-metric-contract-v1"
METRIC_CONTRACT_IDENTITY: Final[str] = (
    "e3ff3221338863aa9128890c23e463e7a3868cd8dfc3e1b2c30c503c351a3acd"
)
PRIMARY_SELECTION_METRIC: Final[str] = "daily_wape"
INCUMBENT_MODEL_ID: Final[str] = "V0_2_CURRENT_MODEL"
MAX_VALIDATION_EVALUATIONS: Final[int] = 32
MAX_RUNS_PER_CANDIDATE: Final[int] = 4
MINIMUM_COVERAGE_THRESHOLD: Final[Decimal] = Decimal("0.900000")
VALID_INCLUDED_CANONICAL_GROUP_COVERAGE_THRESHOLD: Final[Decimal] = Decimal("1.000000")
MISSING_DATA_PROPORTION_THRESHOLD: Final[Decimal] = Decimal("0.000000")
MIN_COMPARABLE_ROWS_FOR_REPORTING: Final[int] = 10
P80_NOMINAL_QUANTILE: Final[Decimal] = Decimal("0.80")
P90_NOMINAL_QUANTILE: Final[Decimal] = Decimal("0.90")
S1_METRIC_CONTRACT_AUTHORITY: Final[str] = "docs/forecast-quality/s3-quality-metrics-contract.md"

REQUIRED_BREAKDOWN_AXES: Final[tuple[str, ...]] = (
    "forecast_horizon_days",
    "farm_business_key",
    "subfarm_business_key",
    "variety_business_key",
    "season_business_key",
    "model_identity",
)
REQUIRED_BREAKDOWN_AXIS_COUNT: Final[int] = len(REQUIRED_BREAKDOWN_AXES)
RUN_ORDINAL_COUNT_RECONCILIATION_REQUIRED: Final[bool] = True
_SHA256_IDENTITY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
RETRY_INVOCATION_TYPES: Final[frozenset[str]] = frozenset(
    {"AUTOMATIC_RETRY", "MANUAL_RETRY", "OPERATOR_TRIGGERED_RERUN"}
)
VALIDATION_INVOCATION_TYPES: Final[frozenset[str]] = frozenset(
    {"NORMAL_RUN", *RETRY_INVOCATION_TYPES}
)

GuardrailStatus = Literal["PASS", "FAIL", "BLOCKED"]
EvidenceStatus = Literal["COMPUTED", "NOT_COMPUTABLE", "MISSING", "INSUFFICIENT_SAMPLE"]
ExecutionGateStatus = Literal["ALLOWED", "BLOCKED"]

LOWER_IS_BETTER_GUARDRAILS: Final[tuple[str, ...]] = (
    "daily_mae",
    "cumulative_absolute_error_kg",
    "single_day_peak_quantity_absolute_error_kg_q",
    "sustained_7day_quantity_absolute_error_kg_q",
)
SPARSE_COMPLETE_WINDOW_METRICS: Final[tuple[str, ...]] = (
    "cumulative_absolute_error_kg",
    "single_day_peak_quantity_absolute_error_kg_q",
    "sustained_7day_quantity_absolute_error_kg_q",
)


@dataclass(frozen=True, slots=True)
class CandidateRegistration:
    """The S4-A registration facts bound into the S4-B policy."""

    candidate_id: str
    candidate_family: str
    parent_model_id: str
    hypothesis: str
    authorized_change: str
    planned_run_count: int
    random_seed_policy: str
    selection_eligibility: str


FROZEN_CANDIDATE_REGISTRY: Final[tuple[CandidateRegistration, ...]] = (
    CandidateRegistration(
        "01_parameter_calibration",
        "PARAMETER_CALIBRATION",
        INCUMBENT_MODEL_ID,
        "parameter_calibration_reduces_primary_metric_without_guardrail_regression",
        "NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION",
        4,
        "FIXED_AND_RECORDED_PER_RUN",
        "REGISTERED_AND_GUARDRAIL_ELIGIBLE",
    ),
    CandidateRegistration(
        "02_quantile_calibration",
        "QUANTILE_CALIBRATION",
        INCUMBENT_MODEL_ID,
        "quantile_calibration_improves_p80_p90_coverage_without_point_metric_regression",
        "NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION",
        4,
        "FIXED_AND_RECORDED_PER_RUN",
        "REGISTERED_AND_GUARDRAIL_ELIGIBLE",
    ),
    CandidateRegistration(
        "03_phenology_offset",
        "PARAMETER_CALIBRATION",
        INCUMBENT_MODEL_ID,
        "versioned_phenology_offset_reduces_timing_error",
        "NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION",
        4,
        "FIXED_AND_RECORDED_PER_RUN",
        "REGISTERED_AND_GUARDRAIL_ELIGIBLE",
    ),
    CandidateRegistration(
        "04_yield_parameter",
        "PARAMETER_CALIBRATION",
        INCUMBENT_MODEL_ID,
        "versioned_yield_parameter_calibration_reduces_quantity_error",
        "NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION",
        4,
        "FIXED_AND_RECORDED_PER_RUN",
        "REGISTERED_AND_GUARDRAIL_ELIGIBLE",
    ),
    CandidateRegistration(
        "05_marketable_rate",
        "PARAMETER_CALIBRATION",
        INCUMBENT_MODEL_ID,
        "versioned_marketable_rate_calibration_reduces_marketable_quantity_error",
        "NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION",
        4,
        "FIXED_AND_RECORDED_PER_RUN",
        "REGISTERED_AND_GUARDRAIL_ELIGIBLE",
    ),
    CandidateRegistration(
        "06_weather_response",
        "STRUCTURAL_MODEL_CANDIDATE",
        INCUMBENT_MODEL_ID,
        "authorized_weather_response_features_reduce_residual_error",
        "NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION",
        4,
        "FIXED_AND_RECORDED_PER_RUN",
        "REGISTERED_AND_GUARDRAIL_ELIGIBLE",
    ),
    CandidateRegistration(
        "07_harvest_efficiency",
        "PARAMETER_CALIBRATION",
        INCUMBENT_MODEL_ID,
        "versioned_harvest_efficiency_calibration_reduces_peak_error",
        "NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION",
        4,
        "FIXED_AND_RECORDED_PER_RUN",
        "REGISTERED_AND_GUARDRAIL_ELIGIBLE",
    ),
    CandidateRegistration(
        "08_residual_feature",
        "STRUCTURAL_MODEL_CANDIDATE",
        INCUMBENT_MODEL_ID,
        "authorized_residual_features_reduce_unexplained_residual",
        "NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION",
        4,
        "FIXED_AND_RECORDED_PER_RUN",
        "REGISTERED_AND_GUARDRAIL_ELIGIBLE",
    ),
)


@dataclass(frozen=True, slots=True)
class MetricObservation:
    """A computed, missing, or non-computable comparison input."""

    metric_name: str
    status: EvidenceStatus
    value: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.metric_name:
            raise ValueError("metric_name is required")
        if self.status not in ("COMPUTED", "NOT_COMPUTABLE", "MISSING", "INSUFFICIENT_SAMPLE"):
            raise ValueError("unsupported metric evidence status")
        if self.value is not None:
            if type(self.value) is not Decimal:
                raise TypeError("metric values must be Decimal")
            if not self.value.is_finite():
                raise ValueError("metric values must be finite Decimal values")
        if self.status == "COMPUTED" and self.value is None:
            raise ValueError("COMPUTED metric evidence requires a Decimal value")

    @classmethod
    def computed(cls, metric_name: str, value: Decimal) -> MetricObservation:
        return cls(metric_name=metric_name, status="COMPUTED", value=value)

    @classmethod
    def missing(cls, metric_name: str) -> MetricObservation:
        return cls(metric_name=metric_name, status="MISSING")

    @classmethod
    def not_computable(cls, metric_name: str) -> MetricObservation:
        return cls(metric_name=metric_name, status="NOT_COMPUTABLE")

    @classmethod
    def insufficient_sample(cls, metric_name: str) -> MetricObservation:
        return cls(metric_name=metric_name, status="INSUFFICIENT_SAMPLE")


@dataclass(frozen=True, slots=True)
class BreakdownCellEvidence:
    """Required breakdown-cell evidence retained for coverage reporting."""

    cell_id: str
    comparable_rows: int
    metric_status: EvidenceStatus = "COMPUTED"
    # Raw metric/breakdown reason from the computation layer.  It is optional
    # for in-memory policy-only fixtures, but the canonical persistence gate
    # rejects an omitted value rather than inventing ``NONE``.
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not self.cell_id:
            raise ValueError("cell_id is required")
        if type(self.comparable_rows) is not int or self.comparable_rows < 0:
            raise ValueError("comparable_rows must be a non-negative integer")
        if self.metric_status not in (
            "COMPUTED",
            "NOT_COMPUTABLE",
            "MISSING",
            "INSUFFICIENT_SAMPLE",
        ):
            raise ValueError("unsupported breakdown metric status")
        if self.reason_code is not None and (
            not isinstance(self.reason_code, str) or not self.reason_code
        ):
            raise ValueError("reason_code must be a non-empty string when provided")


@dataclass(frozen=True, slots=True)
class BreakdownReportingDisposition:
    """Reporting-only status for one required breakdown cell.

    The S3 reporting floor is intentionally separate from candidate selection.
    A cell with fewer than ``MIN_COMPARABLE_ROWS_FOR_REPORTING`` rows remains
    in the report as insufficient sample evidence, but cannot by itself block
    the global candidate eligibility decision on the V4 policy.
    """

    reporting_status: EvidenceStatus
    reporting_reason: str
    selection_blocking: bool


def breakdown_reporting_disposition(cell: BreakdownCellEvidence) -> BreakdownReportingDisposition:
    """Classify a breakdown cell without dropping or altering its evidence."""

    if cell.comparable_rows < MIN_COMPARABLE_ROWS_FOR_REPORTING:
        return BreakdownReportingDisposition(
            reporting_status="INSUFFICIENT_SAMPLE",
            reporting_reason="BELOW_MINIMUM",
            selection_blocking=False,
        )
    if cell.metric_status != "COMPUTED":
        return BreakdownReportingDisposition(
            reporting_status=cell.metric_status,
            reporting_reason="INSUFFICIENT_REQUIRED_EVIDENCE",
            selection_blocking=True,
        )
    return BreakdownReportingDisposition(
        reporting_status="COMPUTED",
        reporting_reason="NONE",
        selection_blocking=False,
    )


@dataclass(frozen=True, slots=True)
class BreakdownAxisEvidence:
    """Evidence for one independently reported required breakdown axis."""

    axis_name: str
    cells: tuple[BreakdownCellEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not self.axis_name:
            raise ValueError("axis_name is required")


@dataclass(frozen=True, slots=True)
class CoverageQualityEvidence:
    """The accepted S1 coverage/data-quality inputs for one candidate run."""

    coverage_ratio: MetricObservation
    valid_included_canonical_group_coverage: MetricObservation
    missing_data_proportion: MetricObservation
    breakdown_axes: tuple[BreakdownAxisEvidence, ...] = ()
    no_silent_exclusion: bool = True


SELECTION_EVIDENCE_SCHEMA_VERSION: Final[str] = "v0.3-s4-selection-evidence-v1"
SELECTION_EVIDENCE_PROVENANCE_INCOMPLETE: Final[str] = "SELECTION_EVIDENCE_PROVENANCE_INCOMPLETE"


class SelectionEvidenceProvenanceError(ValueError):
    """Raised when a selection evidence payload cannot be replayed safely."""

    def __init__(self, detail: str = SELECTION_EVIDENCE_PROVENANCE_INCOMPLETE) -> None:
        super().__init__(f"{SELECTION_EVIDENCE_PROVENANCE_INCOMPLETE}:{detail}")


def _selection_metric_payload(observation: MetricObservation) -> dict[str, object]:
    return {
        "status": observation.status,
        "value": None if observation.value is None else format(observation.value, "f"),
    }


def _selection_metric_from_payload(
    payload: Mapping[str, object],
    *,
    metric_name: str,
) -> MetricObservation:
    status = payload.get("status")
    value = payload.get("value")
    if not isinstance(status, str) or status not in (
        "COMPUTED",
        "NOT_COMPUTABLE",
        "MISSING",
        "INSUFFICIENT_SAMPLE",
    ):
        raise SelectionEvidenceProvenanceError(f"{metric_name}:metric_status")
    if value is None:
        parsed_value: Decimal | None = None
    elif isinstance(value, str):
        try:
            parsed_value = Decimal(value)
        except Exception as exc:  # pragma: no cover - Decimal errors vary
            raise SelectionEvidenceProvenanceError(f"{metric_name}:metric_value") from exc
        if not parsed_value.is_finite():
            raise SelectionEvidenceProvenanceError(f"{metric_name}:metric_value")
    else:
        raise SelectionEvidenceProvenanceError(f"{metric_name}:metric_value")
    try:
        return MetricObservation(
            metric_name=metric_name,
            status=cast(EvidenceStatus, status),
            value=parsed_value,
        )
    except (TypeError, ValueError) as exc:
        raise SelectionEvidenceProvenanceError(f"{metric_name}:metric_observation") from exc


def build_coverage_quality_evidence_payload(
    evidence: CoverageQualityEvidence,
) -> dict[str, object]:
    """Serialize replayable S4 coverage evidence with every required cell.

    This is the write-time contract for future real S4 validation evidence. A
    compact axis summary is intentionally not representable here: the
    selection surface needs each axis, cell identity, comparable-row count,
    metric status, and the derived reporting disposition.
    """

    if not isinstance(evidence, CoverageQualityEvidence):
        raise SelectionEvidenceProvenanceError("coverage_quality_evidence:type")
    expected_metric_names = (
        "coverage_ratio",
        "valid_included_canonical_group_coverage",
        "missing_data_proportion",
    )
    observations = (
        evidence.coverage_ratio,
        evidence.valid_included_canonical_group_coverage,
        evidence.missing_data_proportion,
    )
    if tuple(item.metric_name for item in observations) != expected_metric_names:
        raise SelectionEvidenceProvenanceError("coverage_quality_evidence:metric_identity")
    if type(evidence.no_silent_exclusion) is not bool:
        raise SelectionEvidenceProvenanceError("coverage_quality_evidence:no_silent_exclusion")

    axes_by_name: dict[str, BreakdownAxisEvidence] = {}
    for axis in evidence.breakdown_axes:
        if axis.axis_name not in REQUIRED_BREAKDOWN_AXES:
            raise SelectionEvidenceProvenanceError(
                f"coverage_quality_evidence:unknown_axis:{axis.axis_name}"
            )
        if axis.axis_name in axes_by_name:
            raise SelectionEvidenceProvenanceError(
                f"coverage_quality_evidence:duplicate_axis:{axis.axis_name}"
            )
        if not axis.cells:
            raise SelectionEvidenceProvenanceError(
                f"coverage_quality_evidence:empty_axis:{axis.axis_name}"
            )
        axes_by_name[axis.axis_name] = axis
    if set(axes_by_name) != set(REQUIRED_BREAKDOWN_AXES):
        raise SelectionEvidenceProvenanceError("coverage_quality_evidence:required_axes")

    axes_payload: dict[str, object] = {}
    for axis_name in REQUIRED_BREAKDOWN_AXES:
        axis = axes_by_name[axis_name]
        seen_cell_ids: set[str] = set()
        cells_payload: list[dict[str, object]] = []
        for cell in axis.cells:
            if cell.cell_id in seen_cell_ids:
                raise SelectionEvidenceProvenanceError(
                    f"coverage_quality_evidence:duplicate_cell:{axis_name}:{cell.cell_id}"
                )
            if not isinstance(cell.reason_code, str) or not cell.reason_code:
                raise SelectionEvidenceProvenanceError(
                    f"coverage_quality_evidence:reason_code:{axis_name}:{cell.cell_id}"
                )
            seen_cell_ids.add(cell.cell_id)
            disposition = breakdown_reporting_disposition(cell)
            cells_payload.append(
                {
                    "axis_name": axis_name,
                    "cell_id": cell.cell_id,
                    "comparable_rows": cell.comparable_rows,
                    "metric_status": cell.metric_status,
                    "reason_code": cell.reason_code,
                    "reporting_status": disposition.reporting_status,
                    "reporting_reason": disposition.reporting_reason,
                    "selection_blocking": disposition.selection_blocking,
                }
            )
        axes_payload[axis_name] = {"axis_name": axis_name, "cells": cells_payload}

    return {
        "schema_version": SELECTION_EVIDENCE_SCHEMA_VERSION,
        "coverage_ratio": _selection_metric_payload(evidence.coverage_ratio)["value"],
        "coverage_ratio_status": evidence.coverage_ratio.status,
        "valid_included_canonical_group_coverage": _selection_metric_payload(
            evidence.valid_included_canonical_group_coverage
        )["value"],
        "valid_included_canonical_group_coverage_status": (
            evidence.valid_included_canonical_group_coverage.status
        ),
        "missing_data_proportion": _selection_metric_payload(evidence.missing_data_proportion)[
            "value"
        ],
        "missing_data_proportion_status": evidence.missing_data_proportion.status,
        "no_silent_exclusion": evidence.no_silent_exclusion,
        "summary_is_cell_evidence": False,
        "breakdown_axes": axes_payload,
    }


def parse_coverage_quality_evidence_payload(
    payload: Mapping[str, object],
) -> CoverageQualityEvidence:
    """Parse and validate the canonical cell-level coverage evidence payload."""

    if payload.get("schema_version") != SELECTION_EVIDENCE_SCHEMA_VERSION:
        raise SelectionEvidenceProvenanceError("coverage_quality_evidence:schema_version")
    if payload.get("summary_is_cell_evidence") is not False:
        raise SelectionEvidenceProvenanceError("coverage_quality_evidence:summary_only")
    no_silent_exclusion = payload.get("no_silent_exclusion")
    if type(no_silent_exclusion) is not bool:
        raise SelectionEvidenceProvenanceError("coverage_quality_evidence:no_silent_exclusion")

    scalar_specs = (
        ("coverage_ratio", "coverage_ratio_status"),
        (
            "valid_included_canonical_group_coverage",
            "valid_included_canonical_group_coverage_status",
        ),
        ("missing_data_proportion", "missing_data_proportion_status"),
    )
    observations: list[MetricObservation] = []
    for metric_name, status_field in scalar_specs:
        value = payload.get(metric_name)
        status = payload.get(status_field)
        observations.append(
            _selection_metric_from_payload(
                {"value": value, "status": status}, metric_name=metric_name
            )
        )

    axes_payload = payload.get("breakdown_axes")
    if not isinstance(axes_payload, Mapping):
        raise SelectionEvidenceProvenanceError("coverage_quality_evidence:breakdown_axes")
    if set(axes_payload) != set(REQUIRED_BREAKDOWN_AXES):
        raise SelectionEvidenceProvenanceError("coverage_quality_evidence:required_axes")

    axes: list[BreakdownAxisEvidence] = []
    for axis_name in REQUIRED_BREAKDOWN_AXES:
        axis_payload = axes_payload.get(axis_name)
        if not isinstance(axis_payload, Mapping):
            raise SelectionEvidenceProvenanceError(f"coverage_quality_evidence:axis:{axis_name}")
        if axis_payload.get("axis_name") != axis_name:
            raise SelectionEvidenceProvenanceError(
                f"coverage_quality_evidence:axis_identity:{axis_name}"
            )
        cells_payload = axis_payload.get("cells")
        if not isinstance(cells_payload, list) or not cells_payload:
            raise SelectionEvidenceProvenanceError(f"coverage_quality_evidence:cells:{axis_name}")
        cells: list[BreakdownCellEvidence] = []
        seen_cell_ids: set[str] = set()
        for cell_payload in cells_payload:
            if not isinstance(cell_payload, Mapping):
                raise SelectionEvidenceProvenanceError(
                    f"coverage_quality_evidence:cell:{axis_name}"
                )
            if cell_payload.get("axis_name") != axis_name:
                raise SelectionEvidenceProvenanceError(
                    f"coverage_quality_evidence:cell_axis:{axis_name}"
                )
            cell_id = cell_payload.get("cell_id")
            comparable_rows = cell_payload.get("comparable_rows")
            metric_status = cell_payload.get("metric_status")
            reason_code = cell_payload.get("reason_code")
            if not isinstance(cell_id, str) or not cell_id:
                raise SelectionEvidenceProvenanceError(
                    f"coverage_quality_evidence:cell_id:{axis_name}"
                )
            if cell_id in seen_cell_ids:
                raise SelectionEvidenceProvenanceError(
                    f"coverage_quality_evidence:duplicate_cell:{axis_name}:{cell_id}"
                )
            if type(comparable_rows) is not int or comparable_rows < 0:
                raise SelectionEvidenceProvenanceError(
                    f"coverage_quality_evidence:comparable_rows:{axis_name}:{cell_id}"
                )
            if not isinstance(metric_status, str):
                raise SelectionEvidenceProvenanceError(
                    f"coverage_quality_evidence:metric_status:{axis_name}:{cell_id}"
                )
            if not isinstance(reason_code, str) or not reason_code:
                raise SelectionEvidenceProvenanceError(
                    f"coverage_quality_evidence:reason_code:{axis_name}:{cell_id}"
                )
            try:
                cell = BreakdownCellEvidence(
                    cell_id=cell_id,
                    comparable_rows=comparable_rows,
                    metric_status=cast(EvidenceStatus, metric_status),
                    reason_code=reason_code,
                )
            except (TypeError, ValueError) as exc:
                raise SelectionEvidenceProvenanceError(
                    f"coverage_quality_evidence:cell:{axis_name}:{cell_id}"
                ) from exc
            disposition = breakdown_reporting_disposition(cell)
            if (
                cell_payload.get("reporting_status") != disposition.reporting_status
                or cell_payload.get("reporting_reason") != disposition.reporting_reason
                or cell_payload.get("selection_blocking") != disposition.selection_blocking
            ):
                raise SelectionEvidenceProvenanceError(
                    f"coverage_quality_evidence:reporting_disposition:{axis_name}:{cell_id}"
                )
            seen_cell_ids.add(cell_id)
            cells.append(cell)
        axes.append(BreakdownAxisEvidence(axis_name=axis_name, cells=tuple(cells)))

    return CoverageQualityEvidence(
        coverage_ratio=observations[0],
        valid_included_canonical_group_coverage=observations[1],
        missing_data_proportion=observations[2],
        breakdown_axes=tuple(axes),
        no_silent_exclusion=no_silent_exclusion,
    )


def validate_s4_selection_evidence_payload(evidence: Mapping[str, object]) -> None:
    """Fail closed before writing a future real-validation evidence artifact."""

    incumbent = evidence.get("INCUMBENT_METRICS")
    if not isinstance(incumbent, Mapping):
        raise SelectionEvidenceProvenanceError("INCUMBENT_METRICS")
    incumbent_quality = incumbent.get("coverage_quality_evidence")
    if not isinstance(incumbent_quality, Mapping):
        raise SelectionEvidenceProvenanceError("INCUMBENT_METRICS:coverage_quality_evidence")
    parse_coverage_quality_evidence_payload(incumbent_quality)

    runs = evidence.get("RUNS")
    if not isinstance(runs, list):
        raise SelectionEvidenceProvenanceError("RUNS")
    for index, run in enumerate(runs):
        if not isinstance(run, Mapping):
            raise SelectionEvidenceProvenanceError(f"RUNS[{index}]")
        metrics = run.get("candidate_metrics")
        if metrics is None:
            if run.get("eligibility_status") is not None:
                raise SelectionEvidenceProvenanceError(f"RUNS[{index}]:candidate_metrics")
            continue
        if not isinstance(metrics, Mapping):
            raise SelectionEvidenceProvenanceError(f"RUNS[{index}]:candidate_metrics")
        quality = metrics.get("coverage_quality_evidence")
        if not isinstance(quality, Mapping):
            raise SelectionEvidenceProvenanceError(f"RUNS[{index}]:coverage_quality_evidence")
        parse_coverage_quality_evidence_payload(quality)


@dataclass(frozen=True, slots=True)
class GuardrailResult:
    guardrail_id: str
    status: GuardrailStatus
    reason_code: str
    candidate_value: Decimal | None = None
    incumbent_value: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.guardrail_id or not self.reason_code:
            raise ValueError("guardrail_id and reason_code are required")
        if self.status not in ("PASS", "FAIL", "BLOCKED"):
            raise ValueError("unsupported guardrail status")
        for value in (self.candidate_value, self.incumbent_value):
            if value is not None:
                if type(value) is not Decimal:
                    raise TypeError("guardrail values must be Decimal")
                if not value.is_finite():
                    raise ValueError("guardrail values must be finite Decimal values")


@dataclass(frozen=True, slots=True)
class CandidateEligibilityResult:
    status: GuardrailStatus
    candidate_eligible: bool
    guardrails: tuple[GuardrailResult, ...]
    reason_codes: tuple[str, ...]
    diagnostics: tuple[DiagnosticMetricDisposition, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in ("PASS", "FAIL", "BLOCKED"):
            raise ValueError("unsupported candidate eligibility status")
        if self.candidate_eligible != (self.status == "PASS"):
            raise ValueError("eligibility must be true only for a PASS result")


@dataclass(frozen=True, slots=True)
class DiagnosticMetricDisposition:
    """A metric retained as evidence but excluded from sparse selection."""

    metric_name: str
    status: EvidenceStatus
    selection_blocking: bool
    diagnostic_only: bool
    reason_code: str

    def __post_init__(self) -> None:
        if not self.metric_name or not self.reason_code:
            raise ValueError("metric_name and reason_code are required")
        if self.status not in (
            "COMPUTED",
            "NOT_COMPUTABLE",
            "MISSING",
            "INSUFFICIENT_SAMPLE",
        ):
            raise ValueError("unsupported diagnostic metric status")


def canonical_guardrail_policy() -> dict[str, object]:
    """Return the complete S4-B policy preimage, excluding its derived hash."""

    return {
        "guardrail_policy_version": GUARDRAIL_POLICY_VERSION,
        "s4_a_experiment_plan_hash_bound": S4_A_EXPERIMENT_PLAN_HASH_BOUND,
        "experiment_plan_version": EXPERIMENT_PLAN_VERSION,
        "candidate_count": len(FROZEN_CANDIDATE_REGISTRY),
        "candidate_ids": [registration.candidate_id for registration in FROZEN_CANDIDATE_REGISTRY],
        "metric_contract_version": METRIC_CONTRACT_VERSION,
        "metric_contract_authority": S1_METRIC_CONTRACT_AUTHORITY,
        "metric_contract_identity": METRIC_CONTRACT_IDENTITY,
        "metric_identity_binding": {
            "primary": PRIMARY_SELECTION_METRIC,
            "lower_is_better_guardrails": list(LOWER_IS_BETTER_GUARDRAILS),
            "p80_coverage": "P80_COVERAGE",
            "p90_coverage": "P90_COVERAGE",
            "coverage_ratio": "coverage_ratio",
            "valid_included_canonical_group_coverage": ("valid_included_canonical_group_coverage"),
            "missing_data_proportion": "missing_data_proportion",
        },
        "candidate_registry": [
            {
                "candidate_id": registration.candidate_id,
                "candidate_family": registration.candidate_family,
                "parent_model_id": registration.parent_model_id,
                "hypothesis": registration.hypothesis,
                "authorized_change": registration.authorized_change,
                "planned_run_count": registration.planned_run_count,
                "random_seed_policy": registration.random_seed_policy,
                "selection_eligibility": registration.selection_eligibility,
            }
            for registration in FROZEN_CANDIDATE_REGISTRY
        ],
        "primary_metric": {
            "name": PRIMARY_SELECTION_METRIC,
            "direction": "LOWER_IS_BETTER",
            "required_relation": "CANDIDATE_STRICTLY_LESS_THAN_INCUMBENT",
            "equality_result": "NOT_IMPROVED",
            "worse_result": "FAIL",
            "not_computable_result": "BLOCKED",
            "tolerance": "ZERO",
        },
        "lower_is_better_guardrails": [
            {
                "metric_name": metric_name,
                "direction": "LOWER_IS_BETTER",
                "tolerance": "ZERO",
                "equal_to_incumbent": "PASS",
                "lower_than_incumbent": "PASS",
                "higher_than_incumbent": "FAIL",
                "not_computable": "BLOCKED",
                "missing": "BLOCKED",
            }
            for metric_name in LOWER_IS_BETTER_GUARDRAILS
        ],
        "quantile_coverage_guardrails": {
            "p80": {
                "nominal_quantile": P80_NOMINAL_QUANTILE,
                "transform": "ABS(P80_UPPER_COVERAGE - NOMINAL_QUANTILE)",
                "comparison": "CANDIDATE_DISTANCE_LESS_THAN_OR_EQUAL_TO_INCUMBENT",
                "tolerance": "ZERO",
            },
            "p90": {
                "nominal_quantile": P90_NOMINAL_QUANTILE,
                "transform": "ABS(P90_UPPER_COVERAGE - NOMINAL_QUANTILE)",
                "comparison": "CANDIDATE_DISTANCE_LESS_THAN_OR_EQUAL_TO_INCUMBENT",
                "tolerance": "ZERO",
            },
        },
        "coverage_and_data_quality": {
            "s1_minimum_coverage_status": "PASS",
            "minimum_coverage_threshold": MINIMUM_COVERAGE_THRESHOLD,
            "minimum_coverage_operator": "GREATER_THAN_OR_EQUAL",
            "valid_included_canonical_group_coverage_threshold": (
                VALID_INCLUDED_CANONICAL_GROUP_COVERAGE_THRESHOLD
            ),
            "missing_data_proportion_threshold": MISSING_DATA_PROPORTION_THRESHOLD,
            "no_silent_exclusion": True,
            "minimum_comparable_rows_for_reporting": MIN_COMPARABLE_ROWS_FOR_REPORTING,
            "required_breakdown_axes": list(REQUIRED_BREAKDOWN_AXES),
            "required_breakdown_axis_count": REQUIRED_BREAKDOWN_AXIS_COUNT,
            "all_required_breakdown_axes_must_be_present": True,
            "empty_breakdown_evidence": "BLOCKED",
            "unknown_breakdown_axis": "BLOCKED",
            "duplicate_breakdown_axis": "BLOCKED",
            "conflicting_breakdown_axis_evidence": "BLOCKED",
            "empty_required_breakdown_axis_cells": "BLOCKED",
            "below_minimum_cell": "BLOCKED",
            "non_computed_cell": "BLOCKED",
        },
        "paired_comparison": {
            "required": True,
            "unpaired_candidate_score_allowed": False,
            "common_comparable_set_required": True,
            "same_actual_label_rows_required": True,
            "same_train_dataset_required": True,
            "same_validation_dataset_required": True,
            "same_labels_required": True,
            "same_exclusion_policy_required": True,
            "same_cutoff_policy_required": True,
            "same_forecast_horizons_required": True,
            "same_metrics_required": True,
            "same_business_grains_required": True,
            "identity_fields": [
                "train_dataset_identity",
                "validation_dataset_identity",
                "actual_label_set_identity",
                "exclusion_policy_identity",
                "cutoff_policy_identity",
                "forecast_horizon_set_identity",
                "metric_contract_identity",
                "business_grain_set_identity",
                "common_comparable_set_identity",
            ],
            "identity_format": "64-character lowercase SHA-256",
            "incumbent_model_id": INCUMBENT_MODEL_ID,
            "farm_total_baseline_is_not_s4_incumbent": True,
        },
        "validation_budget": {
            "max_validation_evaluations": MAX_VALIDATION_EVALUATIONS,
            "max_runs_per_candidate": MAX_RUNS_PER_CANDIDATE,
            "paired_incumbent_reference_is_not_separately_triggerable": True,
            "separate_incumbent_only_validation_invocation_allowed": False,
            "one_candidate_run_one_ledger_row": True,
            "one_candidate_run_consumes_one_validation_evaluation": True,
            "run_ordinal_count_reconciliation_required": True,
            "candidate_run_ordinal_rule": "candidate_actual_run_count + 1",
            "retry_counts_as_new_candidate_run": True,
            "retry_requires_new_evaluation_id": True,
            "retry_requires_parent_in_prior_ledger": True,
            "prior_ledger_rows_are_immutable": True,
        },
        "fail_closed_aggregation": {
            "all_required_guardrails_must_pass": True,
            "blocked_precedence_over_fail": True,
            "any_guardrail_fails_candidate_eligibility_false": True,
            "any_required_guardrail_blocked_candidate_eligibility_false": True,
        },
        "multiple_comparison": {
            "adjustment": "HOLM_BONFERRONI_OVER_PREDECLARED_PRIMARY_METRIC_COMPARISONS",
            "requires_predeclared_candidate_set": True,
            "candidate_set_count": 8,
            "after_candidate_results": True,
            "before_final_selection": True,
            "uses_validation_only": True,
            "must_not_use_test": True,
            "primary_comparison_pvalue_protocol_status": ("NOT_YET_FROZEN_FOR_FINAL_SELECTION"),
        },
        "test_boundary": {
            "test_access_currently_authorized": False,
            "test_evaluation_authorized": False,
            "test_remains_sealed": True,
        },
        "execution_boundary": {
            "candidate_evaluation_count_at_freeze": 0,
            "candidate_01_execution_authorized": False,
            "candidate_01_parameter_manifest_frozen": False,
            "candidate_01_run_count": 0,
            "model_change_authorized": False,
            "parameter_change_authorized": False,
            "training_executed": False,
        },
    }


def canonical_guardrail_policy_v2() -> dict[str, object]:
    """Return the V2 policy without mutating the replayable V1 preimage.

    Metric and comparison semantics are inherited byte-for-byte from the V1
    policy payload.  Only the plan/policy identity and the historical-only
    execution overlay are changed for the current execution authority.
    """

    policy = canonical_guardrail_policy()
    policy["guardrail_policy_version"] = V2_GUARDRAIL_POLICY_VERSION
    policy["s4_a_experiment_plan_hash_bound"] = EXPERIMENT_PLAN_V2_HASH
    policy["experiment_plan_version"] = EXPERIMENT_PLAN_V2_VERSION
    policy["historical_only_execution_overlay"] = {
        "historical_data_only": V2_HISTORICAL_DATA_ONLY,
        "weather_required": V2_WEATHER_REQUIRED,
        "production_plan_required": V2_PRODUCTION_PLAN_REQUIRED,
        "task8_task9_required": V2_TASK8_TASK9_REQUIRED,
        "prospective_capture_required": V2_PROSPECTIVE_CAPTURE_REQUIRED,
        "wall_clock_wait_required": V2_WALL_CLOCK_WAIT_REQUIRED,
        "test_remains_sealed": V2_TEST_REMAINS_SEALED,
        "forecast_horizons": list(V2_FORECAST_HORIZONS),
        "candidate_01_rerun_forbidden": V2_CANDIDATE_01_RERUN_FORBIDDEN,
        "legacy_reconciled_validation_debit": V2_LEGACY_RECONCILED_VALIDATION_DEBIT,
        "candidate_06_execution_eligible": V2_CANDIDATE_06_EXECUTION_ELIGIBLE,
        "candidate_08_execution_eligible": V2_CANDIDATE_08_EXECUTION_ELIGIBLE,
        "candidate_06_blocker": "CURRENT_WEATHER_AUTHORITY_REQUIRED",
        "candidate_08_blocker": "V2_HISTORICAL_ONLY_FEATURE_MANIFEST_REQUIRED",
    }
    return policy


def canonical_guardrail_policy_v3_sparse() -> dict[str, object]:
    """Return the immutable V3 sparse-horizon selection-policy preimage.

    V1 and V2 remain replayable.  V3 inherits their metric and identity
    contract, then explicitly narrows the selection surface so complete-window
    metrics are diagnostic evidence rather than fabricated sparse guardrails.
    """

    policy = canonical_guardrail_policy_v2()
    policy["guardrail_policy_version"] = V3_GUARDRAIL_POLICY_VERSION
    policy["sparse_horizon_selection_overlay"] = {
        "experiment_plan_version": EXPERIMENT_PLAN_V2_VERSION,
        "experiment_plan_hash": EXPERIMENT_PLAN_V2_HASH,
        "evaluation_surface_id": V3_EVALUATION_SURFACE_ID,
        "forecast_horizons": list(V3_FORECAST_HORIZONS),
        "complete_daily_rowset_authority": V3_COMPLETE_DAILY_ROWSET_AUTHORITY,
        "missing_day_zero_fill": V3_MISSING_DAY_ZERO_FILL,
        "primary_selection_metric": PRIMARY_SELECTION_METRIC,
        "primary_direction": "LOWER_IS_BETTER",
        "primary_required_relation": "CANDIDATE_STRICTLY_LESS_THAN_INCUMBENT",
        "primary_tolerance": "ZERO",
        "point_guardrail": "daily_mae",
        "point_guardrail_relation": "CANDIDATE_LESS_THAN_OR_EQUAL_TO_INCUMBENT",
        "point_guardrail_tolerance": "ZERO",
        "diagnostic_only_complete_window_metrics": list(SPARSE_COMPLETE_WINDOW_METRICS),
        "diagnostic_reason": "COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE",
        "candidate_01_rerun_forbidden": V2_CANDIDATE_01_RERUN_FORBIDDEN,
        "candidate_06_execution_eligible": V2_CANDIDATE_06_EXECUTION_ELIGIBLE,
        "candidate_08_execution_eligible": V2_CANDIDATE_08_EXECUTION_ELIGIBLE,
    }
    return policy


def canonical_guardrail_policy_v4_breakdown_reporting() -> dict[str, object]:
    """Return the corrected V4 policy for sparse breakdown reporting.

    V4 is a new policy identity.  The predecessor V3 payload remains
    replayable and is never rewritten.  Only the interpretation of the
    already-required breakdown reporting floor changes: a small cell is
    retained as ``INSUFFICIENT_SAMPLE`` evidence and is not a global selection
    blocker.
    """

    policy = canonical_guardrail_policy_v3_sparse()
    policy["guardrail_policy_version"] = V4_GUARDRAIL_POLICY_VERSION
    policy["breakdown_reporting_floor_overlay"] = {
        "predecessor_policy_version": V4_PREDECESSOR_POLICY_VERSION,
        "predecessor_policy_hash": V3_GUARDRAIL_POLICY_HASH,
        "minimum_comparable_rows_for_reporting": MIN_COMPARABLE_ROWS_FOR_REPORTING,
        "reporting_floor_is_selection_threshold": False,
        "below_minimum_status": "INSUFFICIENT_SAMPLE",
        "below_minimum_reason": "BELOW_MINIMUM",
        "below_minimum_selection_blocking": False,
        "required_breakdown_axes": list(REQUIRED_BREAKDOWN_AXES),
        "all_cells_retained_for_reporting": True,
        "silent_exclusion_is_still_forbidden": True,
    }
    return policy


GUARDRAIL_POLICY_HASH: Final[str] = sha256_payload(canonical_guardrail_policy())
V2_GUARDRAIL_POLICY_HASH: Final[str] = sha256_payload(canonical_guardrail_policy_v2())
V3_GUARDRAIL_POLICY_HASH: Final[str] = sha256_payload(canonical_guardrail_policy_v3_sparse())
V4_GUARDRAIL_POLICY_HASH: Final[str] = sha256_payload(
    canonical_guardrail_policy_v4_breakdown_reporting()
)


def _blocked_result(
    guardrail_id: str,
    reason_code: str,
    candidate_value: Decimal | None = None,
    incumbent_value: Decimal | None = None,
) -> GuardrailResult:
    return GuardrailResult(
        guardrail_id=guardrail_id,
        status="BLOCKED",
        reason_code=reason_code,
        candidate_value=candidate_value,
        incumbent_value=incumbent_value,
    )


def _observation_values(
    guardrail_id: str,
    candidate: MetricObservation,
    incumbent: MetricObservation,
    expected_metric_name: str,
) -> GuardrailResult | tuple[Decimal, Decimal]:
    if (
        candidate.metric_name != expected_metric_name
        or incumbent.metric_name != expected_metric_name
    ):
        return _blocked_result(guardrail_id, "METRIC_IDENTITY_MISMATCH")
    if candidate.status != "COMPUTED" or incumbent.status != "COMPUTED":
        if "INSUFFICIENT_SAMPLE" in (candidate.status, incumbent.status):
            reason_code = "BELOW_MINIMUM"
        elif "MISSING" in (candidate.status, incumbent.status):
            reason_code = "MISSING_REQUIRED_EVIDENCE"
        else:
            reason_code = "NOT_COMPUTABLE"
        return _blocked_result(guardrail_id, reason_code, candidate.value, incumbent.value)
    if candidate.value is None or incumbent.value is None:
        return _blocked_result(guardrail_id, "MISSING_REQUIRED_EVIDENCE")
    return candidate.value, incumbent.value


def compare_primary_metric(
    candidate: MetricObservation,
    incumbent: MetricObservation,
) -> GuardrailResult:
    """Require a strict improvement in the lower-is-better primary metric."""

    values = _observation_values(
        PRIMARY_SELECTION_METRIC,
        candidate,
        incumbent,
        PRIMARY_SELECTION_METRIC,
    )
    if isinstance(values, GuardrailResult):
        return values
    candidate_value, incumbent_value = values
    if candidate_value < incumbent_value:
        return GuardrailResult(
            PRIMARY_SELECTION_METRIC,
            "PASS",
            "STRICTLY_LESS_THAN_INCUMBENT",
            candidate_value,
            incumbent_value,
        )
    if candidate_value == incumbent_value:
        return GuardrailResult(
            PRIMARY_SELECTION_METRIC,
            "FAIL",
            "NOT_IMPROVED",
            candidate_value,
            incumbent_value,
        )
    return GuardrailResult(
        PRIMARY_SELECTION_METRIC,
        "FAIL",
        "HIGHER_THAN_INCUMBENT",
        candidate_value,
        incumbent_value,
    )


def compare_lower_is_better(
    guardrail_id: str,
    candidate: MetricObservation,
    incumbent: MetricObservation,
) -> GuardrailResult:
    """Apply zero-tolerance non-regression for a lower-is-better metric."""

    if guardrail_id not in LOWER_IS_BETTER_GUARDRAILS:
        return _blocked_result(guardrail_id, "UNKNOWN_GUARDRAIL_ID")
    values = _observation_values(guardrail_id, candidate, incumbent, guardrail_id)
    if isinstance(values, GuardrailResult):
        return values
    candidate_value, incumbent_value = values
    if candidate_value <= incumbent_value:
        reason_code = (
            "EQUAL_TO_INCUMBENT" if candidate_value == incumbent_value else "LOWER_THAN_INCUMBENT"
        )
        return GuardrailResult(
            guardrail_id,
            "PASS",
            reason_code,
            candidate_value,
            incumbent_value,
        )
    return GuardrailResult(
        guardrail_id,
        "FAIL",
        "HIGHER_THAN_INCUMBENT",
        candidate_value,
        incumbent_value,
    )


def compare_calibration_distance(
    guardrail_id: str,
    candidate_coverage: MetricObservation,
    incumbent_coverage: MetricObservation,
    nominal_quantile: Decimal,
) -> GuardrailResult:
    """Compare distance from a verified upper-quantile nominal level."""

    if type(nominal_quantile) is not Decimal:
        raise TypeError("nominal quantile must be Decimal")
    if not nominal_quantile.is_finite():
        raise ValueError("nominal quantile must be finite")
    if guardrail_id == "P80_COVERAGE":
        expected_metric_name = "P80_COVERAGE"
        expected_nominal_quantile = P80_NOMINAL_QUANTILE
    elif guardrail_id == "P90_COVERAGE":
        expected_metric_name = "P90_COVERAGE"
        expected_nominal_quantile = P90_NOMINAL_QUANTILE
    else:
        return _blocked_result(guardrail_id, "UNKNOWN_GUARDRAIL_ID")
    if nominal_quantile != expected_nominal_quantile:
        return _blocked_result(guardrail_id, "NOMINAL_QUANTILE_MISMATCH")
    values = _observation_values(
        guardrail_id,
        candidate_coverage,
        incumbent_coverage,
        expected_metric_name,
    )
    if isinstance(values, GuardrailResult):
        return values
    candidate_value, incumbent_value = values
    if not (Decimal("0") <= candidate_value <= Decimal("1")):
        return _blocked_result(guardrail_id, "INVALID_COVERAGE", candidate_value, incumbent_value)
    if not (Decimal("0") <= incumbent_value <= Decimal("1")):
        return _blocked_result(guardrail_id, "INVALID_COVERAGE", candidate_value, incumbent_value)
    candidate_distance = abs(candidate_value - nominal_quantile)
    incumbent_distance = abs(incumbent_value - nominal_quantile)
    if candidate_distance <= incumbent_distance:
        reason_code = (
            "EQUAL_DISTANCE_TO_NOMINAL"
            if candidate_distance == incumbent_distance
            else "CLOSER_TO_NOMINAL"
        )
        return GuardrailResult(
            guardrail_id,
            "PASS",
            reason_code,
            candidate_distance,
            incumbent_distance,
        )
    return GuardrailResult(
        guardrail_id,
        "FAIL",
        "FARTHER_FROM_NOMINAL",
        candidate_distance,
        incumbent_distance,
    )


def evaluate_coverage_quality_gate(evidence: CoverageQualityEvidence) -> GuardrailResult:
    """Apply the accepted S1 coverage and data-quality policy."""

    guardrail_id = "coverage_and_data_quality"
    if not evidence.no_silent_exclusion:
        return GuardrailResult(guardrail_id, "FAIL", "SILENT_EXCLUSION_FORBIDDEN")

    if not evidence.breakdown_axes:
        return GuardrailResult(guardrail_id, "BLOCKED", "EMPTY_BREAKDOWN_EVIDENCE")
    axis_names = tuple(axis.axis_name for axis in evidence.breakdown_axes)
    unknown_axes = tuple(
        axis_name for axis_name in axis_names if axis_name not in REQUIRED_BREAKDOWN_AXES
    )
    if unknown_axes:
        return GuardrailResult(guardrail_id, "BLOCKED", "UNKNOWN_REQUIRED_BREAKDOWN_AXIS")
    if len(set(axis_names)) != len(axis_names):
        return GuardrailResult(guardrail_id, "BLOCKED", "DUPLICATE_REQUIRED_BREAKDOWN_AXIS")
    if set(axis_names) != set(REQUIRED_BREAKDOWN_AXES):
        return GuardrailResult(guardrail_id, "BLOCKED", "MISSING_REQUIRED_BREAKDOWN_AXIS")
    for axis in evidence.breakdown_axes:
        if not axis.cells:
            return GuardrailResult(guardrail_id, "BLOCKED", "EMPTY_REQUIRED_AXIS_CELLS")
        seen_cell_ids: dict[str, BreakdownCellEvidence] = {}
        for cell in axis.cells:
            prior_cell = seen_cell_ids.get(cell.cell_id)
            if prior_cell is not None and prior_cell != cell:
                return GuardrailResult(guardrail_id, "BLOCKED", "CONFLICTING_AXIS_EVIDENCE")
            if prior_cell is not None:
                return GuardrailResult(guardrail_id, "BLOCKED", "CONFLICTING_AXIS_EVIDENCE")
            seen_cell_ids[cell.cell_id] = cell
            if cell.comparable_rows < MIN_COMPARABLE_ROWS_FOR_REPORTING:
                return GuardrailResult(guardrail_id, "BLOCKED", "BELOW_MINIMUM")
            if cell.metric_status != "COMPUTED":
                return GuardrailResult(guardrail_id, "BLOCKED", "INSUFFICIENT_REQUIRED_EVIDENCE")

    observations = (
        evidence.coverage_ratio,
        evidence.valid_included_canonical_group_coverage,
        evidence.missing_data_proportion,
    )
    expected_names = (
        "coverage_ratio",
        "valid_included_canonical_group_coverage",
        "missing_data_proportion",
    )
    if any(
        observation.metric_name != expected_name
        for observation, expected_name in zip(observations, expected_names, strict=True)
    ):
        return GuardrailResult(guardrail_id, "BLOCKED", "METRIC_IDENTITY_MISMATCH")
    if any(observation.status != "COMPUTED" for observation in observations):
        return GuardrailResult(guardrail_id, "BLOCKED", "MISSING_REQUIRED_EVIDENCE")
    values = tuple(observation.value for observation in observations)
    if any(value is None for value in values):
        return GuardrailResult(guardrail_id, "BLOCKED", "MISSING_REQUIRED_EVIDENCE")
    coverage_ratio, valid_group_coverage, missing_proportion = values
    assert coverage_ratio is not None
    assert valid_group_coverage is not None
    assert missing_proportion is not None
    if coverage_ratio < MINIMUM_COVERAGE_THRESHOLD:
        return GuardrailResult(guardrail_id, "FAIL", "MINIMUM_COVERAGE_NOT_MET")
    if valid_group_coverage < VALID_INCLUDED_CANONICAL_GROUP_COVERAGE_THRESHOLD:
        return GuardrailResult(guardrail_id, "FAIL", "CANONICAL_GROUP_COVERAGE_NOT_MET")
    if missing_proportion > MISSING_DATA_PROPORTION_THRESHOLD:
        return GuardrailResult(guardrail_id, "FAIL", "MISSING_DATA_PROPORTION_EXCEEDED")
    return GuardrailResult(guardrail_id, "PASS", "S1_POLICY_SATISFIED")


def evaluate_coverage_quality_gate_v4_breakdown_reporting(
    evidence: CoverageQualityEvidence,
) -> GuardrailResult:
    """Apply V4 coverage/data-quality gates with a reporting-only cell floor.

    Required axes, cell identity integrity, complete evidence, coverage
    thresholds, and no-silent-exclusion remain selection gates.  Only the
    S3 reporting floor is non-blocking: cells below ten comparable rows are
    retained as ``INSUFFICIENT_SAMPLE``/``BELOW_MINIMUM`` evidence.
    """

    guardrail_id = "coverage_and_data_quality"
    if not evidence.no_silent_exclusion:
        return GuardrailResult(guardrail_id, "FAIL", "SILENT_EXCLUSION_FORBIDDEN")

    if not evidence.breakdown_axes:
        return GuardrailResult(guardrail_id, "BLOCKED", "EMPTY_BREAKDOWN_EVIDENCE")
    axis_names = tuple(axis.axis_name for axis in evidence.breakdown_axes)
    if any(axis_name not in REQUIRED_BREAKDOWN_AXES for axis_name in axis_names):
        return GuardrailResult(guardrail_id, "BLOCKED", "UNKNOWN_REQUIRED_BREAKDOWN_AXIS")
    if len(set(axis_names)) != len(axis_names):
        return GuardrailResult(guardrail_id, "BLOCKED", "DUPLICATE_REQUIRED_BREAKDOWN_AXIS")
    if set(axis_names) != set(REQUIRED_BREAKDOWN_AXES):
        return GuardrailResult(guardrail_id, "BLOCKED", "MISSING_REQUIRED_BREAKDOWN_AXIS")

    for axis in evidence.breakdown_axes:
        if not axis.cells:
            return GuardrailResult(guardrail_id, "BLOCKED", "EMPTY_REQUIRED_AXIS_CELLS")
        seen_cell_ids: dict[str, BreakdownCellEvidence] = {}
        for cell in axis.cells:
            prior_cell = seen_cell_ids.get(cell.cell_id)
            if prior_cell is not None:
                return GuardrailResult(guardrail_id, "BLOCKED", "CONFLICTING_AXIS_EVIDENCE")
            seen_cell_ids[cell.cell_id] = cell
            disposition = breakdown_reporting_disposition(cell)
            if disposition.selection_blocking:
                return GuardrailResult(
                    guardrail_id,
                    "BLOCKED",
                    disposition.reporting_reason,
                )

    observations = (
        evidence.coverage_ratio,
        evidence.valid_included_canonical_group_coverage,
        evidence.missing_data_proportion,
    )
    expected_names = (
        "coverage_ratio",
        "valid_included_canonical_group_coverage",
        "missing_data_proportion",
    )
    if any(
        observation.metric_name != expected_name
        for observation, expected_name in zip(observations, expected_names, strict=True)
    ):
        return GuardrailResult(guardrail_id, "BLOCKED", "METRIC_IDENTITY_MISMATCH")
    if any(observation.status != "COMPUTED" for observation in observations):
        return GuardrailResult(guardrail_id, "BLOCKED", "MISSING_REQUIRED_EVIDENCE")
    values = tuple(observation.value for observation in observations)
    if any(value is None for value in values):
        return GuardrailResult(guardrail_id, "BLOCKED", "MISSING_REQUIRED_EVIDENCE")
    coverage_ratio, valid_group_coverage, missing_proportion = values
    assert coverage_ratio is not None
    assert valid_group_coverage is not None
    assert missing_proportion is not None
    if coverage_ratio < MINIMUM_COVERAGE_THRESHOLD:
        return GuardrailResult(guardrail_id, "FAIL", "MINIMUM_COVERAGE_NOT_MET")
    if valid_group_coverage < VALID_INCLUDED_CANONICAL_GROUP_COVERAGE_THRESHOLD:
        return GuardrailResult(guardrail_id, "FAIL", "CANONICAL_GROUP_COVERAGE_NOT_MET")
    if missing_proportion > MISSING_DATA_PROPORTION_THRESHOLD:
        return GuardrailResult(guardrail_id, "FAIL", "MISSING_DATA_PROPORTION_EXCEEDED")
    return GuardrailResult(guardrail_id, "PASS", "S1_POLICY_SATISFIED")


def _aggregate(
    results: tuple[GuardrailResult, ...],
    *,
    diagnostics: tuple[DiagnosticMetricDisposition, ...] = (),
) -> CandidateEligibilityResult:
    blocked = tuple(result for result in results if result.status == "BLOCKED")
    failed = tuple(result for result in results if result.status == "FAIL")
    if blocked:
        status: GuardrailStatus = "BLOCKED"
    elif failed:
        status = "FAIL"
    else:
        status = "PASS"
    reason_codes = tuple(dict.fromkeys(result.reason_code for result in results))
    return CandidateEligibilityResult(
        status=status,
        candidate_eligible=status == "PASS",
        guardrails=results,
        reason_codes=reason_codes,
        diagnostics=diagnostics,
    )


def evaluate_candidate_guardrails(
    *,
    candidate_primary_metric: MetricObservation,
    incumbent_primary_metric: MetricObservation,
    lower_is_better_metrics: Mapping[str, tuple[MetricObservation, MetricObservation]],
    candidate_p80_coverage: MetricObservation,
    incumbent_p80_coverage: MetricObservation,
    candidate_p90_coverage: MetricObservation,
    incumbent_p90_coverage: MetricObservation,
    coverage_quality: CoverageQualityEvidence | None,
) -> CandidateEligibilityResult:
    """Evaluate every required S4 guardrail with BLOCKED precedence."""

    results: list[GuardrailResult] = [
        compare_primary_metric(candidate_primary_metric, incumbent_primary_metric)
    ]
    missing_metrics = [
        metric_name
        for metric_name in LOWER_IS_BETTER_GUARDRAILS
        if metric_name not in lower_is_better_metrics
    ]
    if missing_metrics:
        results.extend(
            _blocked_result(metric_name, "MISSING_REQUIRED_GUARDRAIL")
            for metric_name in missing_metrics
        )
    unexpected_metrics = sorted(set(lower_is_better_metrics).difference(LOWER_IS_BETTER_GUARDRAILS))
    if unexpected_metrics:
        results.append(_blocked_result("lower_is_better_metric_set", "UNEXPECTED_GUARDRAIL"))
    for metric_name in LOWER_IS_BETTER_GUARDRAILS:
        pair = lower_is_better_metrics.get(metric_name)
        if pair is not None:
            results.append(compare_lower_is_better(metric_name, pair[0], pair[1]))
    results.extend(
        (
            compare_calibration_distance(
                "P80_COVERAGE",
                candidate_p80_coverage,
                incumbent_p80_coverage,
                P80_NOMINAL_QUANTILE,
            ),
            compare_calibration_distance(
                "P90_COVERAGE",
                candidate_p90_coverage,
                incumbent_p90_coverage,
                P90_NOMINAL_QUANTILE,
            ),
        )
    )
    if coverage_quality is None:
        results.append(_blocked_result("coverage_and_data_quality", "MISSING_REQUIRED_EVIDENCE"))
    else:
        results.append(evaluate_coverage_quality_gate(coverage_quality))
    return _aggregate(tuple(results))


def _sparse_surface_blocked(reason_code: str) -> CandidateEligibilityResult:
    return _aggregate((_blocked_result("evaluation_surface", reason_code),))


def evaluate_candidate_guardrails_v3_sparse(
    *,
    candidate_primary_metric: MetricObservation,
    incumbent_primary_metric: MetricObservation,
    candidate_daily_mae: MetricObservation,
    incumbent_daily_mae: MetricObservation,
    candidate_p80_coverage: MetricObservation,
    incumbent_p80_coverage: MetricObservation,
    candidate_p90_coverage: MetricObservation,
    incumbent_p90_coverage: MetricObservation,
    coverage_quality: CoverageQualityEvidence | None,
    complete_window_metrics: Mapping[str, tuple[MetricObservation, MetricObservation]] | None,
    evaluation_surface_identity: str | None,
    forecast_horizons: Collection[int] | None,
    complete_daily_rowset_authority: bool | None,
    missing_day_zero_fill: bool | None,
) -> CandidateEligibilityResult:
    """Evaluate the frozen sparse 7/14/21 selection surface.

    Only daily WAPE, daily MAE, quantile calibration, and coverage/data-quality
    evidence can affect eligibility on this surface.  Complete-window metrics
    remain explicit NOT_COMPUTABLE diagnostics and are never zero-filled.
    """

    if evaluation_surface_identity is None:
        return _sparse_surface_blocked("EVALUATION_SURFACE_IDENTITY_MISSING")
    if evaluation_surface_identity != V3_EVALUATION_SURFACE_ID:
        return _sparse_surface_blocked("EVALUATION_SURFACE_IDENTITY_MISMATCH")
    if forecast_horizons is None:
        return _sparse_surface_blocked("FORECAST_HORIZONS_MISSING")
    if tuple(forecast_horizons) != V3_FORECAST_HORIZONS:
        return _sparse_surface_blocked("FORECAST_HORIZONS_MISMATCH")
    if complete_daily_rowset_authority is None:
        return _sparse_surface_blocked("COMPLETE_DAILY_ROWSET_AUTHORITY_MISSING")
    if complete_daily_rowset_authority is not V3_COMPLETE_DAILY_ROWSET_AUTHORITY:
        return _sparse_surface_blocked("SPARSE_SURFACE_REQUIRES_INCOMPLETE_DAILY_ROWSET")
    if missing_day_zero_fill is None:
        return _sparse_surface_blocked("MISSING_DAY_ZERO_FILL_POLICY_MISSING")
    if missing_day_zero_fill is not V3_MISSING_DAY_ZERO_FILL:
        return _sparse_surface_blocked("MISSING_DAY_ZERO_FILL_FORBIDDEN")

    if complete_window_metrics is None:
        return _sparse_surface_blocked("MISSING_COMPLETE_WINDOW_DIAGNOSTICS")
    missing_diagnostics = set(SPARSE_COMPLETE_WINDOW_METRICS).difference(complete_window_metrics)
    unexpected_diagnostics = set(complete_window_metrics).difference(SPARSE_COMPLETE_WINDOW_METRICS)
    if missing_diagnostics:
        return _sparse_surface_blocked("MISSING_COMPLETE_WINDOW_DIAGNOSTICS")
    if unexpected_diagnostics:
        return _sparse_surface_blocked("UNEXPECTED_COMPLETE_WINDOW_DIAGNOSTIC")

    diagnostics: list[DiagnosticMetricDisposition] = []
    for metric_name in SPARSE_COMPLETE_WINDOW_METRICS:
        candidate, incumbent = complete_window_metrics[metric_name]
        if (
            candidate.metric_name != metric_name
            or incumbent.metric_name != metric_name
            or candidate.status != "NOT_COMPUTABLE"
            or incumbent.status != "NOT_COMPUTABLE"
        ):
            return _sparse_surface_blocked("SPARSE_COMPLETE_WINDOW_METRIC_NOT_NOT_COMPUTABLE")
        diagnostics.append(
            DiagnosticMetricDisposition(
                metric_name=metric_name,
                status="NOT_COMPUTABLE",
                selection_blocking=False,
                diagnostic_only=True,
                reason_code="COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE",
            )
        )

    results = (
        compare_primary_metric(candidate_primary_metric, incumbent_primary_metric),
        compare_lower_is_better("daily_mae", candidate_daily_mae, incumbent_daily_mae),
        compare_calibration_distance(
            "P80_COVERAGE",
            candidate_p80_coverage,
            incumbent_p80_coverage,
            P80_NOMINAL_QUANTILE,
        ),
        compare_calibration_distance(
            "P90_COVERAGE",
            candidate_p90_coverage,
            incumbent_p90_coverage,
            P90_NOMINAL_QUANTILE,
        ),
        _blocked_result("coverage_and_data_quality", "MISSING_REQUIRED_EVIDENCE")
        if coverage_quality is None
        else evaluate_coverage_quality_gate(coverage_quality),
    )
    return _aggregate(tuple(results), diagnostics=tuple(diagnostics))


def evaluate_candidate_guardrails_v4_breakdown_reporting(
    *,
    candidate_primary_metric: MetricObservation,
    incumbent_primary_metric: MetricObservation,
    candidate_daily_mae: MetricObservation,
    incumbent_daily_mae: MetricObservation,
    candidate_p80_coverage: MetricObservation,
    incumbent_p80_coverage: MetricObservation,
    candidate_p90_coverage: MetricObservation,
    incumbent_p90_coverage: MetricObservation,
    coverage_quality: CoverageQualityEvidence | None,
    complete_window_metrics: Mapping[str, tuple[MetricObservation, MetricObservation]] | None,
    evaluation_surface_identity: str | None,
    forecast_horizons: Collection[int] | None,
    complete_daily_rowset_authority: bool | None,
    missing_day_zero_fill: bool | None,
) -> CandidateEligibilityResult:
    """Evaluate V4 sparse selection with a reporting-only breakdown floor.

    This is deliberately a new evaluator.  V1, V2, and V3 remain available
    for historical replay and retain their original hashes and behavior.
    """

    if evaluation_surface_identity is None:
        return _sparse_surface_blocked("EVALUATION_SURFACE_IDENTITY_MISSING")
    if evaluation_surface_identity != V3_EVALUATION_SURFACE_ID:
        return _sparse_surface_blocked("EVALUATION_SURFACE_IDENTITY_MISMATCH")
    if forecast_horizons is None:
        return _sparse_surface_blocked("FORECAST_HORIZONS_MISSING")
    if tuple(forecast_horizons) != V3_FORECAST_HORIZONS:
        return _sparse_surface_blocked("FORECAST_HORIZONS_MISMATCH")
    if complete_daily_rowset_authority is None:
        return _sparse_surface_blocked("COMPLETE_DAILY_ROWSET_AUTHORITY_MISSING")
    if complete_daily_rowset_authority is not V3_COMPLETE_DAILY_ROWSET_AUTHORITY:
        return _sparse_surface_blocked("SPARSE_SURFACE_REQUIRES_INCOMPLETE_DAILY_ROWSET")
    if missing_day_zero_fill is None:
        return _sparse_surface_blocked("MISSING_DAY_ZERO_FILL_POLICY_MISSING")
    if missing_day_zero_fill is not V3_MISSING_DAY_ZERO_FILL:
        return _sparse_surface_blocked("MISSING_DAY_ZERO_FILL_FORBIDDEN")

    if complete_window_metrics is None:
        return _sparse_surface_blocked("MISSING_COMPLETE_WINDOW_DIAGNOSTICS")
    missing_diagnostics = set(SPARSE_COMPLETE_WINDOW_METRICS).difference(complete_window_metrics)
    unexpected_diagnostics = set(complete_window_metrics).difference(SPARSE_COMPLETE_WINDOW_METRICS)
    if missing_diagnostics:
        return _sparse_surface_blocked("MISSING_COMPLETE_WINDOW_DIAGNOSTICS")
    if unexpected_diagnostics:
        return _sparse_surface_blocked("UNEXPECTED_COMPLETE_WINDOW_DIAGNOSTIC")

    diagnostics: list[DiagnosticMetricDisposition] = []
    for metric_name in SPARSE_COMPLETE_WINDOW_METRICS:
        candidate, incumbent = complete_window_metrics[metric_name]
        if (
            candidate.metric_name != metric_name
            or incumbent.metric_name != metric_name
            or candidate.status != "NOT_COMPUTABLE"
            or incumbent.status != "NOT_COMPUTABLE"
        ):
            return _sparse_surface_blocked("SPARSE_COMPLETE_WINDOW_METRIC_NOT_NOT_COMPUTABLE")
        diagnostics.append(
            DiagnosticMetricDisposition(
                metric_name=metric_name,
                status="NOT_COMPUTABLE",
                selection_blocking=False,
                diagnostic_only=True,
                reason_code="COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE",
            )
        )

    results = (
        compare_primary_metric(candidate_primary_metric, incumbent_primary_metric),
        compare_lower_is_better("daily_mae", candidate_daily_mae, incumbent_daily_mae),
        compare_calibration_distance(
            "P80_COVERAGE",
            candidate_p80_coverage,
            incumbent_p80_coverage,
            P80_NOMINAL_QUANTILE,
        ),
        compare_calibration_distance(
            "P90_COVERAGE",
            candidate_p90_coverage,
            incumbent_p90_coverage,
            P90_NOMINAL_QUANTILE,
        ),
        _blocked_result("coverage_and_data_quality", "MISSING_REQUIRED_EVIDENCE")
        if coverage_quality is None
        else evaluate_coverage_quality_gate_v4_breakdown_reporting(coverage_quality),
    )
    return _aggregate(tuple(results), diagnostics=tuple(diagnostics))


@dataclass(frozen=True, slots=True)
class CandidateExecutionGateRequest:
    """All identity and budget inputs needed before a future candidate run."""

    experiment_plan_version: str
    experiment_plan_hash: str
    guardrail_policy_version: str
    guardrail_policy_hash: str
    candidate_id: str
    candidate_run_ordinal: int
    candidate_planned_run_count: int
    candidate_actual_run_count: int
    global_actual_evaluation_count: int
    train_dataset_identity: str
    validation_dataset_identity: str
    metric_contract_version: str
    test_access_requested: bool
    test_sealed: bool
    parameter_manifest_hash: str | None
    code_commit_sha: str | None
    random_seed: int | None
    evaluation_id: str | None
    retry_of_evaluation_id: str | None = None
    candidate_execution_manifest_frozen: bool = False
    candidate_registry: tuple[CandidateRegistration, ...] | None = None
    policy_payload: object | None = None
    actual_label_set_identity: str | None = None
    exclusion_policy_identity: str | None = None
    cutoff_policy_identity: str | None = None
    forecast_horizon_set_identity: str | None = None
    metric_contract_identity: str | None = None
    business_grain_set_identity: str | None = None
    common_comparable_set_identity: str | None = None
    invocation_type: str = "NORMAL_RUN"
    prior_evaluation_ids: tuple[str, ...] = ()
    evaluation_surface_identity: str | None = None
    forecast_horizons: tuple[int, ...] | None = None
    complete_daily_rowset_authority: bool | None = None
    missing_day_zero_fill: bool | None = None


@dataclass(frozen=True, slots=True)
class CandidateExecutionGateResult:
    status: ExecutionGateStatus
    allowed: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status not in ("ALLOWED", "BLOCKED"):
            raise ValueError("unsupported execution gate status")
        if self.allowed != (self.status == "ALLOWED"):
            raise ValueError("execution gate allowed flag is inconsistent")


def _nonempty(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _canonical_identity(value: str | None) -> bool:
    return isinstance(value, str) and _SHA256_IDENTITY_PATTERN.fullmatch(value) is not None


def validate_s4_invocation_semantics(
    *,
    invocation_type: str,
    evaluation_id: str | None,
    retry_of_evaluation_id: str | None,
    prior_evaluation_ids: Collection[str],
) -> tuple[str, ...]:
    """Return the shared invocation/retry policy reasons used by S4-B.

    The execution gate and the durable validation-budget repository both call
    this function.  Keeping the vocabulary and retry-parent rules here avoids
    a persistence-specific policy that could accept an invocation the
    executable S4 gate would reject.
    """

    reasons: list[str] = []
    if invocation_type not in VALIDATION_INVOCATION_TYPES:
        reasons.append("INVOCATION_TYPE_INVALID")
    if evaluation_id is not None and evaluation_id in prior_evaluation_ids:
        reasons.append("EVALUATION_ID_REUSE_FORBIDDEN")
    is_retry = invocation_type in RETRY_INVOCATION_TYPES or retry_of_evaluation_id is not None
    if is_retry and retry_of_evaluation_id is None:
        reasons.append("RETRY_PARENT_ID_MISSING")
    if retry_of_evaluation_id is not None:
        if not _nonempty(retry_of_evaluation_id):
            reasons.append("RETRY_PARENT_ID_MISSING")
        elif retry_of_evaluation_id == evaluation_id:
            reasons.append("RETRY_REUSES_EVALUATION_ID")
        elif retry_of_evaluation_id not in prior_evaluation_ids:
            reasons.append("RETRY_PARENT_INVOCATION_NOT_FOUND")
    return tuple(dict.fromkeys(reasons))


def _check_candidate_execution_gate_for_policy(
    request: CandidateExecutionGateRequest,
    *,
    expected_experiment_plan_version: str,
    expected_experiment_plan_hash: str,
    expected_guardrail_policy_version: str,
    expected_guardrail_policy_hash: str,
    restricted_candidates: Mapping[str, str] | None = None,
    expected_evaluation_surface_identity: str | None = None,
    expected_forecast_horizons: tuple[int, ...] | None = None,
    expected_complete_daily_rowset_authority: bool | None = None,
    expected_missing_day_zero_fill: bool | None = None,
) -> CandidateExecutionGateResult:
    """Apply the common gate against one explicit immutable policy identity."""

    reasons: list[str] = []
    if request.experiment_plan_version != expected_experiment_plan_version:
        reasons.append("EXPERIMENT_PLAN_VERSION_MISMATCH")
    if request.experiment_plan_hash != expected_experiment_plan_hash:
        reasons.append("EXPERIMENT_PLAN_HASH_MISMATCH")
    if request.guardrail_policy_version != expected_guardrail_policy_version:
        reasons.append("GUARDRAIL_POLICY_VERSION_MISMATCH")
    if request.guardrail_policy_hash != expected_guardrail_policy_hash:
        reasons.append("GUARDRAIL_POLICY_HASH_MISMATCH")
    if expected_evaluation_surface_identity is not None:
        if request.evaluation_surface_identity is None:
            reasons.append("EVALUATION_SURFACE_IDENTITY_MISSING")
        elif request.evaluation_surface_identity != expected_evaluation_surface_identity:
            reasons.append("EVALUATION_SURFACE_IDENTITY_MISMATCH")
    if expected_forecast_horizons is not None:
        if request.forecast_horizons is None:
            reasons.append("FORECAST_HORIZONS_MISSING")
        elif request.forecast_horizons != expected_forecast_horizons:
            reasons.append("FORECAST_HORIZONS_MISMATCH")
    if expected_complete_daily_rowset_authority is not None:
        if request.complete_daily_rowset_authority is None:
            reasons.append("COMPLETE_DAILY_ROWSET_AUTHORITY_MISSING")
        elif (
            request.complete_daily_rowset_authority is not expected_complete_daily_rowset_authority
        ):
            reasons.append("COMPLETE_DAILY_ROWSET_AUTHORITY_MISMATCH")
    if expected_missing_day_zero_fill is not None:
        if request.missing_day_zero_fill is None:
            reasons.append("MISSING_DAY_ZERO_FILL_POLICY_MISSING")
        elif request.missing_day_zero_fill is not expected_missing_day_zero_fill:
            reasons.append("MISSING_DAY_ZERO_FILL_POLICY_MISMATCH")
    if request.candidate_registry != FROZEN_CANDIDATE_REGISTRY:
        reasons.append("CANDIDATE_REGISTRY_MISMATCH")
    registration = next(
        (item for item in FROZEN_CANDIDATE_REGISTRY if item.candidate_id == request.candidate_id),
        None,
    )
    if registration is None:
        reasons.append("UNKNOWN_CANDIDATE")
    elif request.candidate_planned_run_count != registration.planned_run_count:
        reasons.append("CANDIDATE_PLANNED_RUN_COUNT_MISMATCH")
    if type(request.candidate_run_ordinal) is not int or request.candidate_run_ordinal < 1:
        reasons.append("INVALID_CANDIDATE_RUN_ORDINAL")
    elif request.candidate_run_ordinal > MAX_RUNS_PER_CANDIDATE:
        reasons.append("CANDIDATE_RUN_ORDINAL_EXCEEDS_LIMIT")
    if (
        type(request.candidate_actual_run_count) is not int
        or request.candidate_actual_run_count < 0
    ):
        reasons.append("INVALID_CANDIDATE_RUN_COUNT")
    elif request.candidate_actual_run_count >= MAX_RUNS_PER_CANDIDATE:
        reasons.append("CANDIDATE_BUDGET_EXHAUSTED")
    if (
        type(request.candidate_run_ordinal) is int
        and request.candidate_run_ordinal >= 1
        and type(request.candidate_actual_run_count) is int
        and request.candidate_actual_run_count >= 0
        and request.candidate_actual_run_count < MAX_RUNS_PER_CANDIDATE
        and request.candidate_run_ordinal != request.candidate_actual_run_count + 1
    ):
        reasons.append("RUN_ORDINAL_COUNT_MISMATCH")
    if (
        type(request.global_actual_evaluation_count) is not int
        or request.global_actual_evaluation_count < 0
    ):
        reasons.append("INVALID_GLOBAL_EVALUATION_COUNT")
    elif request.global_actual_evaluation_count >= MAX_VALIDATION_EVALUATIONS:
        reasons.append("GLOBAL_VALIDATION_BUDGET_EXHAUSTED")
    pairing_identities = (
        ("train_dataset_identity", request.train_dataset_identity),
        ("validation_dataset_identity", request.validation_dataset_identity),
        ("actual_label_set_identity", request.actual_label_set_identity),
        ("exclusion_policy_identity", request.exclusion_policy_identity),
        ("cutoff_policy_identity", request.cutoff_policy_identity),
        ("forecast_horizon_set_identity", request.forecast_horizon_set_identity),
        ("business_grain_set_identity", request.business_grain_set_identity),
        ("common_comparable_set_identity", request.common_comparable_set_identity),
    )
    for field_name, value in pairing_identities:
        field_prefix = field_name.upper()
        if not _nonempty(value):
            reasons.append(f"{field_prefix}_MISSING")
        elif not _canonical_identity(value):
            reasons.append(f"{field_prefix}_MALFORMED")
    if not _nonempty(request.metric_contract_identity):
        reasons.append("METRIC_CONTRACT_IDENTITY_MISSING")
    elif request.metric_contract_identity != METRIC_CONTRACT_IDENTITY:
        reasons.append("METRIC_CONTRACT_IDENTITY_MISMATCH")
    if request.metric_contract_version != METRIC_CONTRACT_VERSION:
        reasons.append("METRIC_CONTRACT_VERSION_MISMATCH")
    if request.test_access_requested:
        reasons.append("TEST_ACCESS_FORBIDDEN")
    if not request.test_sealed:
        reasons.append("TEST_NOT_SEALED")
    if not _nonempty(request.parameter_manifest_hash):
        reasons.append("PARAMETER_MANIFEST_MISSING")
    if not _nonempty(request.code_commit_sha):
        reasons.append("CODE_COMMIT_SHA_MISSING")
    if type(request.random_seed) is not int:
        reasons.append("RANDOM_SEED_MISSING_OR_INVALID")
    if not _nonempty(request.evaluation_id):
        reasons.append("EVALUATION_ID_MISSING")
    reasons.extend(
        validate_s4_invocation_semantics(
            invocation_type=request.invocation_type,
            evaluation_id=request.evaluation_id,
            retry_of_evaluation_id=request.retry_of_evaluation_id,
            prior_evaluation_ids=request.prior_evaluation_ids,
        )
    )
    if not request.candidate_execution_manifest_frozen:
        reasons.append("EXECUTION_MANIFEST_NOT_FROZEN")
    if request.policy_payload is not None:
        try:
            canonical_json_dumps(request.policy_payload)
        except (TypeError, ValueError):
            reasons.append("NATIVE_FLOAT_OR_NON_CANONICAL_POLICY_PAYLOAD")
    if restricted_candidates is not None:
        blocker = restricted_candidates.get(request.candidate_id)
        if blocker is not None:
            reasons.append(blocker)
    ordered_reasons = tuple(dict.fromkeys(reasons))
    if ordered_reasons:
        return CandidateExecutionGateResult("BLOCKED", False, ordered_reasons)
    return CandidateExecutionGateResult("ALLOWED", True, ())


def check_candidate_execution_gate_v1(
    request: CandidateExecutionGateRequest,
) -> CandidateExecutionGateResult:
    """Evaluate a request against the immutable V1 execution authority."""

    return _check_candidate_execution_gate_for_policy(
        request,
        expected_experiment_plan_version=EXPERIMENT_PLAN_VERSION,
        expected_experiment_plan_hash=S4_A_EXPERIMENT_PLAN_HASH_BOUND,
        expected_guardrail_policy_version=GUARDRAIL_POLICY_VERSION,
        expected_guardrail_policy_hash=GUARDRAIL_POLICY_HASH,
    )


def check_candidate_execution_gate_v2(
    request: CandidateExecutionGateRequest,
) -> CandidateExecutionGateResult:
    """Evaluate a request against the current V2 historical-only authority."""

    return _check_candidate_execution_gate_for_policy(
        request,
        expected_experiment_plan_version=EXPERIMENT_PLAN_V2_VERSION,
        expected_experiment_plan_hash=EXPERIMENT_PLAN_V2_HASH,
        expected_guardrail_policy_version=V2_GUARDRAIL_POLICY_VERSION,
        expected_guardrail_policy_hash=V2_GUARDRAIL_POLICY_HASH,
        restricted_candidates={
            "01_parameter_calibration": "CANDIDATE_01_RERUN_FORBIDDEN",
            "06_weather_response": "CURRENT_WEATHER_AUTHORITY_REQUIRED",
            "08_residual_feature": "V2_HISTORICAL_ONLY_FEATURE_MANIFEST_REQUIRED",
        },
    )


def check_candidate_execution_gate_v3_sparse(
    request: CandidateExecutionGateRequest,
) -> CandidateExecutionGateResult:
    """Evaluate a request against the V3 sparse historical-only authority."""

    return _check_candidate_execution_gate_for_policy(
        request,
        expected_experiment_plan_version=EXPERIMENT_PLAN_V2_VERSION,
        expected_experiment_plan_hash=EXPERIMENT_PLAN_V2_HASH,
        expected_guardrail_policy_version=V3_GUARDRAIL_POLICY_VERSION,
        expected_guardrail_policy_hash=V3_GUARDRAIL_POLICY_HASH,
        expected_evaluation_surface_identity=V3_EVALUATION_SURFACE_ID,
        expected_forecast_horizons=V3_FORECAST_HORIZONS,
        expected_complete_daily_rowset_authority=V3_COMPLETE_DAILY_ROWSET_AUTHORITY,
        expected_missing_day_zero_fill=V3_MISSING_DAY_ZERO_FILL,
        restricted_candidates={
            "01_parameter_calibration": "CANDIDATE_01_RERUN_FORBIDDEN",
            "06_weather_response": "CURRENT_WEATHER_AUTHORITY_REQUIRED",
            "08_residual_feature": "V3_HISTORICAL_ONLY_FEATURE_MANIFEST_REQUIRED",
        },
    )


def check_candidate_execution_gate_v4_breakdown_reporting(
    request: CandidateExecutionGateRequest,
) -> CandidateExecutionGateResult:
    """Evaluate a request against the corrected V4 sparse policy identity."""

    return _check_candidate_execution_gate_for_policy(
        request,
        expected_experiment_plan_version=EXPERIMENT_PLAN_V2_VERSION,
        expected_experiment_plan_hash=EXPERIMENT_PLAN_V2_HASH,
        expected_guardrail_policy_version=V4_GUARDRAIL_POLICY_VERSION,
        expected_guardrail_policy_hash=V4_GUARDRAIL_POLICY_HASH,
        expected_evaluation_surface_identity=V3_EVALUATION_SURFACE_ID,
        expected_forecast_horizons=V3_FORECAST_HORIZONS,
        expected_complete_daily_rowset_authority=V3_COMPLETE_DAILY_ROWSET_AUTHORITY,
        expected_missing_day_zero_fill=V3_MISSING_DAY_ZERO_FILL,
        restricted_candidates={
            "01_parameter_calibration": "CANDIDATE_01_RERUN_FORBIDDEN",
            "06_weather_response": "CURRENT_WEATHER_AUTHORITY_REQUIRED",
            "08_residual_feature": "V4_HISTORICAL_ONLY_FEATURE_MANIFEST_REQUIRED",
        },
    )


def check_candidate_execution_gate(
    request: CandidateExecutionGateRequest,
) -> CandidateExecutionGateResult:
    """Dispatch explicitly versioned requests without changing the V1 API."""

    if request.guardrail_policy_version == V4_GUARDRAIL_POLICY_VERSION:
        return check_candidate_execution_gate_v4_breakdown_reporting(request)
    if request.guardrail_policy_version == V3_GUARDRAIL_POLICY_VERSION:
        return check_candidate_execution_gate_v3_sparse(request)
    if (
        request.experiment_plan_version == EXPERIMENT_PLAN_V2_VERSION
        or request.guardrail_policy_version == V2_GUARDRAIL_POLICY_VERSION
    ):
        return check_candidate_execution_gate_v2(request)
    return check_candidate_execution_gate_v1(request)


__all__ = [
    "CandidateEligibilityResult",
    "CandidateExecutionGateRequest",
    "CandidateExecutionGateResult",
    "CandidateRegistration",
    "CoverageQualityEvidence",
    "SELECTION_EVIDENCE_PROVENANCE_INCOMPLETE",
    "SELECTION_EVIDENCE_SCHEMA_VERSION",
    "SelectionEvidenceProvenanceError",
    "DiagnosticMetricDisposition",
    "BreakdownCellEvidence",
    "BreakdownAxisEvidence",
    "BreakdownReportingDisposition",
    "EvidenceStatus",
    "FROZEN_CANDIDATE_REGISTRY",
    "EXPERIMENT_PLAN_V2_HASH",
    "EXPERIMENT_PLAN_V2_VERSION",
    "GUARDRAIL_POLICY_HASH",
    "GUARDRAIL_POLICY_VERSION",
    "GuardrailResult",
    "GuardrailStatus",
    "MetricObservation",
    "METRIC_CONTRACT_IDENTITY",
    "V2_BUDGET_SNAPSHOT_CANONICAL_STARTED_COUNT",
    "V2_CANDIDATE_01_RERUN_FORBIDDEN",
    "V2_CANDIDATE_06_EXECUTION_ELIGIBLE",
    "V2_CANDIDATE_08_EXECUTION_ELIGIBLE",
    "V2_BUDGET_SNAPSHOT_EFFECTIVE_CONSUMED",
    "V2_FORECAST_HORIZONS",
    "V2_GUARDRAIL_POLICY_HASH",
    "V2_GUARDRAIL_POLICY_VERSION",
    "V2_HISTORICAL_DATA_ONLY",
    "V2_LEGACY_RECONCILED_VALIDATION_DEBIT",
    "V2_PRODUCTION_PLAN_REQUIRED",
    "V2_PROSPECTIVE_CAPTURE_REQUIRED",
    "V2_BUDGET_SNAPSHOT_REMAINING_VALIDATION_EVALUATIONS",
    "V2_TASK8_TASK9_REQUIRED",
    "V2_TEST_REMAINS_SEALED",
    "V2_WALL_CLOCK_WAIT_REQUIRED",
    "V2_WEATHER_REQUIRED",
    "V3_COMPLETE_DAILY_ROWSET_AUTHORITY",
    "V3_EVALUATION_SURFACE_ID",
    "V3_FORECAST_HORIZONS",
    "V3_GUARDRAIL_POLICY_HASH",
    "V3_GUARDRAIL_POLICY_VERSION",
    "V3_MISSING_DAY_ZERO_FILL",
    "V4_GUARDRAIL_POLICY_HASH",
    "V4_GUARDRAIL_POLICY_VERSION",
    "V4_PREDECESSOR_POLICY_VERSION",
    "SPARSE_COMPLETE_WINDOW_METRICS",
    "REQUIRED_BREAKDOWN_AXES",
    "REQUIRED_BREAKDOWN_AXIS_COUNT",
    "RETRY_INVOCATION_TYPES",
    "RUN_ORDINAL_COUNT_RECONCILIATION_REQUIRED",
    "VALIDATION_INVOCATION_TYPES",
    "check_candidate_execution_gate",
    "check_candidate_execution_gate_v1",
    "check_candidate_execution_gate_v2",
    "check_candidate_execution_gate_v3_sparse",
    "check_candidate_execution_gate_v4_breakdown_reporting",
    "canonical_guardrail_policy",
    "canonical_guardrail_policy_v2",
    "canonical_guardrail_policy_v3_sparse",
    "canonical_guardrail_policy_v4_breakdown_reporting",
    "compare_calibration_distance",
    "compare_lower_is_better",
    "compare_primary_metric",
    "evaluate_candidate_guardrails",
    "evaluate_candidate_guardrails_v3_sparse",
    "evaluate_candidate_guardrails_v4_breakdown_reporting",
    "evaluate_coverage_quality_gate",
    "evaluate_coverage_quality_gate_v4_breakdown_reporting",
    "breakdown_reporting_disposition",
    "build_coverage_quality_evidence_payload",
    "parse_coverage_quality_evidence_payload",
    "validate_s4_selection_evidence_payload",
    "validate_s4_invocation_semantics",
]
