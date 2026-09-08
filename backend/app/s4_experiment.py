"""Deterministic S4 guardrails and candidate execution preflight.

This module is deliberately independent from model execution.  It freezes the
common S4 comparison policy and provides pure in-memory checks that a future
candidate runner must pass before it can consume a validation budget unit.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal

from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload

GUARDRAIL_POLICY_VERSION: Final[str] = "v0.3-s4-guardrail-policy-v1"
S4_A_EXPERIMENT_PLAN_HASH_BOUND: Final[str] = (
    "9e223a02a1b38c028c230a45eb1fa8323f3c2247bb85e7b439f3351e51042500"
)
EXPERIMENT_PLAN_VERSION: Final[str] = "v0.3-experiment-plan-v1"
METRIC_CONTRACT_VERSION: Final[str] = "v0.3-metric-contract-v1"
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

GuardrailStatus = Literal["PASS", "FAIL", "BLOCKED"]
EvidenceStatus = Literal["COMPUTED", "NOT_COMPUTABLE", "MISSING", "INSUFFICIENT_SAMPLE"]
ExecutionGateStatus = Literal["ALLOWED", "BLOCKED"]

LOWER_IS_BETTER_GUARDRAILS: Final[tuple[str, ...]] = (
    "daily_mae",
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


@dataclass(frozen=True, slots=True)
class CoverageQualityEvidence:
    """The accepted S1 coverage/data-quality inputs for one candidate run."""

    coverage_ratio: MetricObservation
    valid_included_canonical_group_coverage: MetricObservation
    missing_data_proportion: MetricObservation
    breakdown_cells: tuple[BreakdownCellEvidence, ...] = ()
    no_silent_exclusion: bool = True


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

    def __post_init__(self) -> None:
        if self.status not in ("PASS", "FAIL", "BLOCKED"):
            raise ValueError("unsupported candidate eligibility status")
        if self.candidate_eligible != (self.status == "PASS"):
            raise ValueError("eligibility must be true only for a PASS result")


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
        },
        "paired_comparison": {
            "required": True,
            "unpaired_candidate_score_allowed": False,
            "common_comparable_set_required": True,
            "same_actual_label_rows_required": True,
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


GUARDRAIL_POLICY_HASH: Final[str] = sha256_payload(canonical_guardrail_policy())


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
) -> GuardrailResult | tuple[Decimal, Decimal]:
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

    values = _observation_values(PRIMARY_SELECTION_METRIC, candidate, incumbent)
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

    values = _observation_values(guardrail_id, candidate, incumbent)
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
    values = _observation_values(guardrail_id, candidate_coverage, incumbent_coverage)
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
    for cell in evidence.breakdown_cells:
        if cell.comparable_rows < MIN_COMPARABLE_ROWS_FOR_REPORTING:
            return GuardrailResult(guardrail_id, "BLOCKED", "BELOW_MINIMUM")
        if cell.metric_status != "COMPUTED":
            return GuardrailResult(guardrail_id, "BLOCKED", "INSUFFICIENT_REQUIRED_EVIDENCE")

    observations = (
        evidence.coverage_ratio,
        evidence.valid_included_canonical_group_coverage,
        evidence.missing_data_proportion,
    )
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


def _aggregate(results: tuple[GuardrailResult, ...]) -> CandidateEligibilityResult:
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


def check_candidate_execution_gate(
    request: CandidateExecutionGateRequest,
) -> CandidateExecutionGateResult:
    """Fail closed unless every S4-A identity and execution precondition matches."""

    reasons: list[str] = []
    if request.experiment_plan_version != EXPERIMENT_PLAN_VERSION:
        reasons.append("EXPERIMENT_PLAN_VERSION_MISMATCH")
    if request.experiment_plan_hash != S4_A_EXPERIMENT_PLAN_HASH_BOUND:
        reasons.append("EXPERIMENT_PLAN_HASH_MISMATCH")
    if request.guardrail_policy_version != GUARDRAIL_POLICY_VERSION:
        reasons.append("GUARDRAIL_POLICY_VERSION_MISMATCH")
    if request.guardrail_policy_hash != GUARDRAIL_POLICY_HASH:
        reasons.append("GUARDRAIL_POLICY_HASH_MISMATCH")
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
        type(request.global_actual_evaluation_count) is not int
        or request.global_actual_evaluation_count < 0
    ):
        reasons.append("INVALID_GLOBAL_EVALUATION_COUNT")
    elif request.global_actual_evaluation_count >= MAX_VALIDATION_EVALUATIONS:
        reasons.append("GLOBAL_VALIDATION_BUDGET_EXHAUSTED")
    if not _nonempty(request.train_dataset_identity):
        reasons.append("TRAIN_DATASET_IDENTITY_MISSING")
    if not _nonempty(request.validation_dataset_identity):
        reasons.append("VALIDATION_DATASET_IDENTITY_MISSING")
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
    if request.retry_of_evaluation_id is not None:
        if not _nonempty(request.retry_of_evaluation_id):
            reasons.append("RETRY_PARENT_ID_MISSING")
        elif request.retry_of_evaluation_id == request.evaluation_id:
            reasons.append("RETRY_REUSES_EVALUATION_ID")
    if not request.candidate_execution_manifest_frozen:
        reasons.append("EXECUTION_MANIFEST_NOT_FROZEN")
    if request.policy_payload is not None:
        try:
            canonical_json_dumps(request.policy_payload)
        except (TypeError, ValueError):
            reasons.append("NATIVE_FLOAT_OR_NON_CANONICAL_POLICY_PAYLOAD")
    ordered_reasons = tuple(dict.fromkeys(reasons))
    if ordered_reasons:
        return CandidateExecutionGateResult("BLOCKED", False, ordered_reasons)
    return CandidateExecutionGateResult("ALLOWED", True, ())


__all__ = [
    "CandidateEligibilityResult",
    "CandidateExecutionGateRequest",
    "CandidateExecutionGateResult",
    "CandidateRegistration",
    "CoverageQualityEvidence",
    "BreakdownCellEvidence",
    "EvidenceStatus",
    "FROZEN_CANDIDATE_REGISTRY",
    "GUARDRAIL_POLICY_HASH",
    "GUARDRAIL_POLICY_VERSION",
    "GuardrailResult",
    "GuardrailStatus",
    "MetricObservation",
    "check_candidate_execution_gate",
    "canonical_guardrail_policy",
    "compare_calibration_distance",
    "compare_lower_is_better",
    "compare_primary_metric",
    "evaluate_candidate_guardrails",
    "evaluate_coverage_quality_gate",
]
