from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal

import pytest

from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload
from backend.app.s4_experiment import (
    EXPERIMENT_PLAN_VERSION,
    FROZEN_CANDIDATE_REGISTRY,
    GUARDRAIL_POLICY_HASH,
    GUARDRAIL_POLICY_VERSION,
    METRIC_CONTRACT_VERSION,
    PRIMARY_SELECTION_METRIC,
    S4_A_EXPERIMENT_PLAN_HASH_BOUND,
    BreakdownCellEvidence,
    CandidateEligibilityResult,
    CandidateExecutionGateRequest,
    CoverageQualityEvidence,
    MetricObservation,
    canonical_guardrail_policy,
    check_candidate_execution_gate,
    compare_calibration_distance,
    compare_lower_is_better,
    evaluate_candidate_guardrails,
)


def _metric(name: str, value: str) -> MetricObservation:
    return MetricObservation.computed(name, Decimal(value))


def _coverage_quality() -> CoverageQualityEvidence:
    return CoverageQualityEvidence(
        coverage_ratio=_metric("coverage_ratio", "1.000000"),
        valid_included_canonical_group_coverage=_metric(
            "valid_included_canonical_group_coverage", "1.000000"
        ),
        missing_data_proportion=_metric("missing_data_proportion", "0.000000"),
        breakdown_cells=(BreakdownCellEvidence("all-six-axes", 10),),
    )


def _lower_pairs() -> dict[str, tuple[MetricObservation, MetricObservation]]:
    return {
        metric_name: (_metric(metric_name, "1.000000"), _metric(metric_name, "2.000000"))
        for metric_name in (
            "daily_mae",
            "cumulative_absolute_error_kg",
            "single_day_peak_quantity_absolute_error_kg_q",
            "sustained_7day_quantity_absolute_error_kg_q",
        )
    }


def _complete_guardrails() -> CandidateEligibilityResult:
    return evaluate_candidate_guardrails(
        candidate_primary_metric=_metric(PRIMARY_SELECTION_METRIC, "0.400000"),
        incumbent_primary_metric=_metric(PRIMARY_SELECTION_METRIC, "0.500000"),
        lower_is_better_metrics=_lower_pairs(),
        candidate_p80_coverage=_metric("P80_COVERAGE", "0.790000"),
        incumbent_p80_coverage=_metric("P80_COVERAGE", "0.750000"),
        candidate_p90_coverage=_metric("P90_COVERAGE", "0.890000"),
        incumbent_p90_coverage=_metric("P90_COVERAGE", "0.850000"),
        coverage_quality=_coverage_quality(),
    )


def _gate_request() -> CandidateExecutionGateRequest:
    return CandidateExecutionGateRequest(
        experiment_plan_version=EXPERIMENT_PLAN_VERSION,
        experiment_plan_hash=S4_A_EXPERIMENT_PLAN_HASH_BOUND,
        guardrail_policy_version=GUARDRAIL_POLICY_VERSION,
        guardrail_policy_hash=GUARDRAIL_POLICY_HASH,
        candidate_id="01_parameter_calibration",
        candidate_run_ordinal=1,
        candidate_planned_run_count=4,
        candidate_actual_run_count=0,
        global_actual_evaluation_count=0,
        train_dataset_identity="train-identity",
        validation_dataset_identity="validation-identity",
        metric_contract_version=METRIC_CONTRACT_VERSION,
        test_access_requested=False,
        test_sealed=True,
        parameter_manifest_hash="p" * 64,
        code_commit_sha="c" * 40,
        random_seed=17,
        evaluation_id="evaluation-1",
        candidate_execution_manifest_frozen=True,
        candidate_registry=FROZEN_CANDIDATE_REGISTRY,
    )


def test_lower_is_better_guardrail_better_is_pass() -> None:
    result = compare_lower_is_better(
        "daily_mae",
        _metric("daily_mae", "1.000000"),
        _metric("daily_mae", "2.000000"),
    )
    assert (result.status, result.reason_code) == ("PASS", "LOWER_THAN_INCUMBENT")


def test_lower_is_better_guardrail_equality_is_pass() -> None:
    result = compare_lower_is_better(
        "daily_mae",
        _metric("daily_mae", "2.000000"),
        _metric("daily_mae", "2.000000"),
    )
    assert (result.status, result.reason_code) == ("PASS", "EQUAL_TO_INCUMBENT")


def test_smallest_decimal_regression_is_fail() -> None:
    result = compare_lower_is_better(
        "daily_mae",
        _metric("daily_mae", "2.000001"),
        _metric("daily_mae", "2.000000"),
    )
    assert (result.status, result.reason_code) == ("FAIL", "HIGHER_THAN_INCUMBENT")


def test_missing_guardrail_is_blocked() -> None:
    pairs = _lower_pairs()
    pairs.pop("daily_mae")
    result = evaluate_candidate_guardrails(
        candidate_primary_metric=_metric(PRIMARY_SELECTION_METRIC, "0.4"),
        incumbent_primary_metric=_metric(PRIMARY_SELECTION_METRIC, "0.5"),
        lower_is_better_metrics=pairs,
        candidate_p80_coverage=_metric("P80_COVERAGE", "0.79"),
        incumbent_p80_coverage=_metric("P80_COVERAGE", "0.75"),
        candidate_p90_coverage=_metric("P90_COVERAGE", "0.89"),
        incumbent_p90_coverage=_metric("P90_COVERAGE", "0.85"),
        coverage_quality=_coverage_quality(),
    )
    assert result.status == "BLOCKED"
    assert "MISSING_REQUIRED_GUARDRAIL" in result.reason_codes


def test_not_computable_guardrail_is_blocked() -> None:
    result = compare_lower_is_better(
        "daily_mae",
        MetricObservation.not_computable("daily_mae"),
        _metric("daily_mae", "2.000000"),
    )
    assert (result.status, result.reason_code) == ("BLOCKED", "NOT_COMPUTABLE")


def test_insufficient_required_breakdown_evidence_is_blocked() -> None:
    evidence = replace(
        _coverage_quality(),
        breakdown_cells=(BreakdownCellEvidence("farm-a", 9),),
    )
    coverage_result = evaluate_candidate_guardrails(
        candidate_primary_metric=_metric(PRIMARY_SELECTION_METRIC, "0.4"),
        incumbent_primary_metric=_metric(PRIMARY_SELECTION_METRIC, "0.5"),
        lower_is_better_metrics=_lower_pairs(),
        candidate_p80_coverage=_metric("P80_COVERAGE", "0.79"),
        incumbent_p80_coverage=_metric("P80_COVERAGE", "0.75"),
        candidate_p90_coverage=_metric("P90_COVERAGE", "0.89"),
        incumbent_p90_coverage=_metric("P90_COVERAGE", "0.85"),
        coverage_quality=evidence,
    )
    assert coverage_result.status == "BLOCKED"
    assert "BELOW_MINIMUM" in coverage_result.reason_codes


def test_p80_closer_to_nominal_is_pass() -> None:
    result = compare_calibration_distance(
        "P80_COVERAGE",
        _metric("P80_COVERAGE", "0.79"),
        _metric("P80_COVERAGE", "0.75"),
        Decimal("0.80"),
    )
    assert (result.status, result.reason_code) == ("PASS", "CLOSER_TO_NOMINAL")


def test_p80_equal_calibration_distance_is_pass() -> None:
    result = compare_calibration_distance(
        "P80_COVERAGE",
        _metric("P80_COVERAGE", "0.85"),
        _metric("P80_COVERAGE", "0.75"),
        Decimal("0.80"),
    )
    assert (result.status, result.reason_code) == ("PASS", "EQUAL_DISTANCE_TO_NOMINAL")


def test_p80_farther_from_nominal_is_fail() -> None:
    result = compare_calibration_distance(
        "P80_COVERAGE",
        _metric("P80_COVERAGE", "0.70"),
        _metric("P80_COVERAGE", "0.75"),
        Decimal("0.80"),
    )
    assert (result.status, result.reason_code) == ("FAIL", "FARTHER_FROM_NOMINAL")


def test_p90_closer_to_nominal_is_pass() -> None:
    result = compare_calibration_distance(
        "P90_COVERAGE",
        _metric("P90_COVERAGE", "0.89"),
        _metric("P90_COVERAGE", "0.85"),
        Decimal("0.90"),
    )
    assert (result.status, result.reason_code) == ("PASS", "CLOSER_TO_NOMINAL")


def test_p90_equal_calibration_distance_is_pass() -> None:
    result = compare_calibration_distance(
        "P90_COVERAGE",
        _metric("P90_COVERAGE", "0.95"),
        _metric("P90_COVERAGE", "0.85"),
        Decimal("0.90"),
    )
    assert (result.status, result.reason_code) == ("PASS", "EQUAL_DISTANCE_TO_NOMINAL")


def test_p90_farther_from_nominal_is_fail() -> None:
    result = compare_calibration_distance(
        "P90_COVERAGE",
        _metric("P90_COVERAGE", "0.80"),
        _metric("P90_COVERAGE", "0.85"),
        Decimal("0.90"),
    )
    assert (result.status, result.reason_code) == ("FAIL", "FARTHER_FROM_NOMINAL")


def test_native_float_is_rejected() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        MetricObservation.computed("daily_wape", 0.4)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Decimal"):
        compare_calibration_distance(
            "P80_COVERAGE",
            _metric("P80_COVERAGE", "0.80"),
            _metric("P80_COVERAGE", "0.80"),
            0.80,  # type: ignore[arg-type]
        )


def test_guardrail_policy_hash_replays_deterministically() -> None:
    payload = canonical_guardrail_policy()
    assert sha256_payload(payload) == GUARDRAIL_POLICY_HASH
    assert sha256_payload(json.loads(canonical_json_dumps(payload))) == GUARDRAIL_POLICY_HASH


def test_guardrail_policy_mutation_changes_hash() -> None:
    payload = canonical_guardrail_policy()
    primary_metric = payload["primary_metric"]
    assert isinstance(primary_metric, dict)
    primary_metric["tolerance"] = "ONE_MICRO_UNIT"
    assert sha256_payload(payload) != GUARDRAIL_POLICY_HASH


def test_unknown_candidate_is_rejected() -> None:
    result = check_candidate_execution_gate(
        replace(_gate_request(), candidate_id="09_unknown_candidate")
    )
    assert result.status == "BLOCKED"
    assert "UNKNOWN_CANDIDATE" in result.reason_codes


def test_candidate_run_ordinal_above_four_is_rejected() -> None:
    result = check_candidate_execution_gate(replace(_gate_request(), candidate_run_ordinal=5))
    assert result.status == "BLOCKED"
    assert "CANDIDATE_RUN_ORDINAL_EXCEEDS_LIMIT" in result.reason_codes


def test_candidate_budget_exhaustion_is_rejected() -> None:
    result = check_candidate_execution_gate(replace(_gate_request(), candidate_actual_run_count=4))
    assert result.status == "BLOCKED"
    assert "CANDIDATE_BUDGET_EXHAUSTED" in result.reason_codes


def test_global_budget_exhaustion_is_rejected() -> None:
    result = check_candidate_execution_gate(
        replace(_gate_request(), global_actual_evaluation_count=32)
    )
    assert result.status == "BLOCKED"
    assert "GLOBAL_VALIDATION_BUDGET_EXHAUSTED" in result.reason_codes


def test_plan_hash_mismatch_is_rejected() -> None:
    result = check_candidate_execution_gate(replace(_gate_request(), experiment_plan_hash="0" * 64))
    assert result.status == "BLOCKED"
    assert "EXPERIMENT_PLAN_HASH_MISMATCH" in result.reason_codes


def test_guardrail_policy_hash_mismatch_is_rejected() -> None:
    result = check_candidate_execution_gate(
        replace(_gate_request(), guardrail_policy_hash="0" * 64)
    )
    assert result.status == "BLOCKED"
    assert "GUARDRAIL_POLICY_HASH_MISMATCH" in result.reason_codes


def test_test_access_request_is_rejected() -> None:
    result = check_candidate_execution_gate(replace(_gate_request(), test_access_requested=True))
    assert result.status == "BLOCKED"
    assert "TEST_ACCESS_FORBIDDEN" in result.reason_codes


def test_missing_parameter_manifest_is_rejected() -> None:
    result = check_candidate_execution_gate(replace(_gate_request(), parameter_manifest_hash=None))
    assert result.status == "BLOCKED"
    assert "PARAMETER_MANIFEST_MISSING" in result.reason_codes


def test_retry_requires_distinct_evaluation_identity() -> None:
    result = check_candidate_execution_gate(
        replace(_gate_request(), retry_of_evaluation_id="evaluation-1")
    )
    assert result.status == "BLOCKED"
    assert "RETRY_REUSES_EVALUATION_ID" in result.reason_codes


def test_native_float_policy_payload_is_rejected_by_execution_gate() -> None:
    result = check_candidate_execution_gate(
        replace(_gate_request(), policy_payload={"calibration": 0.1})
    )
    assert result.status == "BLOCKED"
    assert "NATIVE_FLOAT_OR_NON_CANONICAL_POLICY_PAYLOAD" in result.reason_codes


def test_complete_guardrail_set_is_pass_and_candidate_eligible() -> None:
    result = _complete_guardrails()
    assert result.status == "PASS"
    assert result.candidate_eligible is True


def test_primary_metric_equality_is_not_improved_and_not_eligible() -> None:
    result = evaluate_candidate_guardrails(
        candidate_primary_metric=_metric(PRIMARY_SELECTION_METRIC, "0.5"),
        incumbent_primary_metric=_metric(PRIMARY_SELECTION_METRIC, "0.5"),
        lower_is_better_metrics=_lower_pairs(),
        candidate_p80_coverage=_metric("P80_COVERAGE", "0.79"),
        incumbent_p80_coverage=_metric("P80_COVERAGE", "0.75"),
        candidate_p90_coverage=_metric("P90_COVERAGE", "0.89"),
        incumbent_p90_coverage=_metric("P90_COVERAGE", "0.85"),
        coverage_quality=_coverage_quality(),
    )
    assert result.status == "FAIL"
    assert result.candidate_eligible is False
    assert "NOT_IMPROVED" in result.reason_codes
