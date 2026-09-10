"""Synthetic contract tests for the V3 sparse 7/14/21 selection surface."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s4_experiment import (
    FROZEN_CANDIDATE_REGISTRY,
    GUARDRAIL_POLICY_HASH,
    REQUIRED_BREAKDOWN_AXES,
    SPARSE_COMPLETE_WINDOW_METRICS,
    V2_GUARDRAIL_POLICY_HASH,
    V3_COMPLETE_DAILY_ROWSET_AUTHORITY,
    V3_EVALUATION_SURFACE_ID,
    V3_FORECAST_HORIZONS,
    V3_GUARDRAIL_POLICY_HASH,
    V3_GUARDRAIL_POLICY_VERSION,
    V3_MISSING_DAY_ZERO_FILL,
    BreakdownAxisEvidence,
    BreakdownCellEvidence,
    CandidateExecutionGateRequest,
    CoverageQualityEvidence,
    MetricObservation,
    canonical_guardrail_policy,
    canonical_guardrail_policy_v2,
    canonical_guardrail_policy_v3_sparse,
    check_candidate_execution_gate,
    evaluate_candidate_guardrails_v3_sparse,
)

IDENTITY = "a" * 64
COMMIT = "b" * 40


def _coverage() -> CoverageQualityEvidence:
    return CoverageQualityEvidence(
        coverage_ratio=MetricObservation.computed("coverage_ratio", Decimal("1")),
        valid_included_canonical_group_coverage=MetricObservation.computed(
            "valid_included_canonical_group_coverage", Decimal("1")
        ),
        missing_data_proportion=MetricObservation.computed("missing_data_proportion", Decimal("0")),
        breakdown_axes=tuple(
            BreakdownAxisEvidence(
                axis_name=axis,
                cells=(BreakdownCellEvidence(cell_id=f"{axis}-cell", comparable_rows=10),),
            )
            for axis in REQUIRED_BREAKDOWN_AXES
        ),
    )


def _complete_window_diagnostics() -> dict[str, tuple[MetricObservation, MetricObservation]]:
    return {
        name: (
            MetricObservation.not_computable(name),
            MetricObservation.not_computable(name),
        )
        for name in SPARSE_COMPLETE_WINDOW_METRICS
    }


def _evaluate(**overrides: object):
    values: dict[str, object] = {
        "candidate_primary_metric": MetricObservation.computed("daily_wape", Decimal("0.10")),
        "incumbent_primary_metric": MetricObservation.computed("daily_wape", Decimal("0.20")),
        "candidate_daily_mae": MetricObservation.computed("daily_mae", Decimal("1")),
        "incumbent_daily_mae": MetricObservation.computed("daily_mae", Decimal("2")),
        "candidate_p80_coverage": MetricObservation.computed("P80_COVERAGE", Decimal("0.8")),
        "incumbent_p80_coverage": MetricObservation.computed("P80_COVERAGE", Decimal("0.8")),
        "candidate_p90_coverage": MetricObservation.computed("P90_COVERAGE", Decimal("0.9")),
        "incumbent_p90_coverage": MetricObservation.computed("P90_COVERAGE", Decimal("0.9")),
        "coverage_quality": _coverage(),
        "complete_window_metrics": _complete_window_diagnostics(),
        "evaluation_surface_identity": V3_EVALUATION_SURFACE_ID,
        "forecast_horizons": V3_FORECAST_HORIZONS,
        "complete_daily_rowset_authority": V3_COMPLETE_DAILY_ROWSET_AUTHORITY,
        "missing_day_zero_fill": V3_MISSING_DAY_ZERO_FILL,
    }
    values.update(overrides)
    return evaluate_candidate_guardrails_v3_sparse(**values)  # type: ignore[arg-type]


def _gate_request(candidate_id: str = "04_yield_parameter") -> CandidateExecutionGateRequest:
    return CandidateExecutionGateRequest(
        experiment_plan_version="v0.3-experiment-plan-v2",
        experiment_plan_hash=("c2bfab4ec38b4ca640f62d061494961c5b49afe5b52fa675326aa80fdf5f8ad9"),
        guardrail_policy_version=V3_GUARDRAIL_POLICY_VERSION,
        guardrail_policy_hash=V3_GUARDRAIL_POLICY_HASH,
        candidate_id=candidate_id,
        candidate_run_ordinal=1,
        candidate_planned_run_count=4,
        candidate_actual_run_count=0,
        global_actual_evaluation_count=4,
        train_dataset_identity=IDENTITY,
        validation_dataset_identity="c" * 64,
        metric_contract_version="v0.3-metric-contract-v1",
        test_access_requested=False,
        test_sealed=True,
        parameter_manifest_hash="d" * 64,
        code_commit_sha=COMMIT,
        random_seed=20260624,
        evaluation_id="v3-readiness-only",
        candidate_execution_manifest_frozen=True,
        candidate_registry=FROZEN_CANDIDATE_REGISTRY,
        policy_payload=canonical_guardrail_policy_v3_sparse(),
        actual_label_set_identity=IDENTITY,
        exclusion_policy_identity=IDENTITY,
        cutoff_policy_identity=IDENTITY,
        forecast_horizon_set_identity=IDENTITY,
        metric_contract_identity=(
            "e3ff3221338863aa9128890c23e463e7a3868cd8dfc3e1b2c30c503c351a3acd"
        ),
        business_grain_set_identity=IDENTITY,
        common_comparable_set_identity=IDENTITY,
        evaluation_surface_identity=V3_EVALUATION_SURFACE_ID,
        forecast_horizons=V3_FORECAST_HORIZONS,
        complete_daily_rowset_authority=False,
        missing_day_zero_fill=False,
    )


def test_v1_guardrail_policy_hash_unchanged() -> None:
    assert sha256_payload(canonical_guardrail_policy()) == GUARDRAIL_POLICY_HASH


def test_v2_guardrail_policy_hash_unchanged() -> None:
    assert sha256_payload(canonical_guardrail_policy_v2()) == V2_GUARDRAIL_POLICY_HASH


def test_v3_sparse_guardrail_hash_deterministic() -> None:
    assert sha256_payload(canonical_guardrail_policy_v3_sparse()) == V3_GUARDRAIL_POLICY_HASH


def test_v3_surface_identity_is_frozen() -> None:
    assert V3_EVALUATION_SURFACE_ID == "V0_3_S4_SOURCE002_SPARSE_HORIZON_7_14_21_V1"
    assert V3_FORECAST_HORIZONS == (7, 14, 21)
    assert V3_COMPLETE_DAILY_ROWSET_AUTHORITY is False
    assert V3_MISSING_DAY_ZERO_FILL is False


def test_v3_requires_exact_horizons_7_14_21() -> None:
    result = _evaluate(forecast_horizons=(7, 14, 30))
    assert result.status == "BLOCKED"
    assert "FORECAST_HORIZONS_MISMATCH" in result.reason_codes


def test_v3_missing_surface_identity_blocks() -> None:
    result = _evaluate(evaluation_surface_identity=None)
    assert result.status == "BLOCKED"
    assert "EVALUATION_SURFACE_IDENTITY_MISSING" in result.reason_codes


def test_v3_wrong_surface_identity_blocks() -> None:
    result = _evaluate(evaluation_surface_identity="wrong-surface")
    assert result.status == "BLOCKED"
    assert "EVALUATION_SURFACE_IDENTITY_MISMATCH" in result.reason_codes


def test_v3_sparse_daily_wape_and_daily_mae_are_required() -> None:
    assert _evaluate().candidate_eligible is True
    assert (
        _evaluate(candidate_primary_metric=MetricObservation.not_computable("daily_wape")).status
        == "BLOCKED"
    )
    assert _evaluate(candidate_daily_mae=MetricObservation.missing("daily_mae")).status == "BLOCKED"


def test_v3_complete_window_metrics_remain_not_computable() -> None:
    result = _evaluate()
    assert {item.metric_name for item in result.diagnostics} == set(SPARSE_COMPLETE_WINDOW_METRICS)
    assert all(item.status == "NOT_COMPUTABLE" for item in result.diagnostics)


def test_v3_complete_window_metrics_are_diagnostic_only() -> None:
    result = _evaluate()
    assert result.status == "PASS"
    assert all(item.selection_blocking is False for item in result.diagnostics)
    assert all(item.diagnostic_only is True for item in result.diagnostics)


def test_v3_sparse_does_not_zero_fill_missing_days() -> None:
    result = _evaluate(missing_day_zero_fill=True)
    assert result.status == "BLOCKED"
    assert "MISSING_DAY_ZERO_FILL_FORBIDDEN" in result.reason_codes


def test_v3_daily_wape_equal_does_not_pass() -> None:
    result = _evaluate(
        candidate_primary_metric=MetricObservation.computed("daily_wape", Decimal("0.20"))
    )
    assert result.status == "FAIL"


def test_v3_daily_wape_worse_fails() -> None:
    result = _evaluate(
        candidate_primary_metric=MetricObservation.computed("daily_wape", Decimal("0.30"))
    )
    assert result.status == "FAIL"


def test_v3_daily_mae_worse_fails() -> None:
    result = _evaluate(candidate_daily_mae=MetricObservation.computed("daily_mae", Decimal("3")))
    assert result.status == "FAIL"


def test_v3_p80_and_p90_guardrails_remain_enforced() -> None:
    p80 = _evaluate(
        candidate_p80_coverage=MetricObservation.computed("P80_COVERAGE", Decimal("0.95"))
    )
    p90 = _evaluate(
        candidate_p90_coverage=MetricObservation.computed("P90_COVERAGE", Decimal("0.80"))
    )
    assert p80.status == "FAIL"
    assert p90.status == "FAIL"


def test_v3_coverage_guardrails_remain_enforced() -> None:
    evidence = _coverage()
    result = _evaluate(
        coverage_quality=replace(
            evidence,
            coverage_ratio=MetricObservation.computed("coverage_ratio", Decimal("0.89")),
        )
    )
    assert result.status == "FAIL"


def test_v3_breakdown_requirements_remain_enforced() -> None:
    evidence = _coverage()
    result = _evaluate(coverage_quality=replace(evidence, breakdown_axes=()))
    assert result.status == "BLOCKED"


def test_v3_valid_sparse_candidate_passes_with_diagnostic_complete_metrics() -> None:
    result = _evaluate()
    assert result.status == "PASS"
    assert result.candidate_eligible is True


def test_execution_gate_routes_v3_sparse_identity() -> None:
    result = check_candidate_execution_gate(_gate_request())
    assert result.allowed is True


def test_v3_execution_gate_rejects_v2_hash() -> None:
    result = check_candidate_execution_gate(
        replace(_gate_request(), guardrail_policy_hash=V2_GUARDRAIL_POLICY_HASH)
    )
    assert result.allowed is False
    assert "GUARDRAIL_POLICY_HASH_MISMATCH" in result.reason_codes


def test_c01_v3_rerun_forbidden() -> None:
    result = check_candidate_execution_gate(_gate_request("01_parameter_calibration"))
    assert result.allowed is False
    assert "CANDIDATE_01_RERUN_FORBIDDEN" in result.reason_codes


def test_c06_v3_blocked() -> None:
    result = check_candidate_execution_gate(_gate_request("06_weather_response"))
    assert result.allowed is False
    assert "CURRENT_WEATHER_AUTHORITY_REQUIRED" in result.reason_codes


def test_c08_v3_blocked() -> None:
    result = check_candidate_execution_gate(_gate_request("08_residual_feature"))
    assert result.allowed is False
    assert "V3_HISTORICAL_ONLY_FEATURE_MANIFEST_REQUIRED" in result.reason_codes


def test_v3_readiness_creates_no_started_event_and_budget_is_unchanged() -> None:
    request = _gate_request()
    result = check_candidate_execution_gate(request)
    assert result.allowed is True
    assert request.global_actual_evaluation_count == 4
    assert request.candidate_actual_run_count == 0
    assert request.candidate_run_ordinal == 1


def test_test_remains_sealed() -> None:
    assert _gate_request().test_access_requested is False
    assert _gate_request().test_sealed is True
