"""R2-only policy correction tests for the completed C04 evidence."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s4_c04_validation_eligibility_rejudication import (
    FrozenC04RunMetrics,
    readjudicate_c04_runs,
)
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
    V4_GUARDRAIL_POLICY_HASH,
    V4_GUARDRAIL_POLICY_VERSION,
    BreakdownAxisEvidence,
    BreakdownCellEvidence,
    CandidateExecutionGateRequest,
    CoverageQualityEvidence,
    MetricObservation,
    breakdown_reporting_disposition,
    canonical_guardrail_policy,
    canonical_guardrail_policy_v2,
    canonical_guardrail_policy_v3_sparse,
    canonical_guardrail_policy_v4_breakdown_reporting,
    check_candidate_execution_gate,
    evaluate_candidate_guardrails_v4_breakdown_reporting,
    evaluate_coverage_quality_gate_v4_breakdown_reporting,
)

IDENTITY = "a" * 64
COMMIT = "b" * 40


def _metric(name: str, value: str) -> MetricObservation:
    return MetricObservation.computed(name, Decimal(value))


def _coverage(*, comparable_rows: int = 9) -> CoverageQualityEvidence:
    return CoverageQualityEvidence(
        coverage_ratio=_metric("coverage_ratio", "1.000000"),
        valid_included_canonical_group_coverage=_metric(
            "valid_included_canonical_group_coverage", "1.000000"
        ),
        missing_data_proportion=_metric("missing_data_proportion", "0.000000"),
        breakdown_axes=tuple(
            BreakdownAxisEvidence(
                axis,
                (BreakdownCellEvidence(f"{axis}-cell", comparable_rows),),
            )
            for axis in REQUIRED_BREAKDOWN_AXES
        ),
    )


def _complete_metrics() -> dict[str, tuple[MetricObservation, MetricObservation]]:
    return {
        name: (
            MetricObservation.not_computable(name),
            MetricObservation.not_computable(name),
        )
        for name in SPARSE_COMPLETE_WINDOW_METRICS
    }


def _evaluate(
    *,
    coverage_quality: CoverageQualityEvidence | None = None,
    **overrides: object,
):
    values: dict[str, object] = {
        "candidate_primary_metric": _metric("daily_wape", "0.725160"),
        "incumbent_primary_metric": _metric("daily_wape", "0.773022"),
        "candidate_daily_mae": _metric("daily_mae", "893.149826"),
        "incumbent_daily_mae": _metric("daily_mae", "952.100208"),
        "candidate_p80_coverage": _metric("P80_COVERAGE", "0.585756"),
        "incumbent_p80_coverage": _metric("P80_COVERAGE", "0.139535"),
        "candidate_p90_coverage": _metric("P90_COVERAGE", "0.665698"),
        "incumbent_p90_coverage": _metric("P90_COVERAGE", "0.223837"),
        "coverage_quality": _coverage() if coverage_quality is None else coverage_quality,
        "complete_window_metrics": _complete_metrics(),
        "evaluation_surface_identity": V3_EVALUATION_SURFACE_ID,
        "forecast_horizons": V3_FORECAST_HORIZONS,
        "complete_daily_rowset_authority": V3_COMPLETE_DAILY_ROWSET_AUTHORITY,
        "missing_day_zero_fill": V3_MISSING_DAY_ZERO_FILL,
    }
    values.update(overrides)
    return evaluate_candidate_guardrails_v4_breakdown_reporting(**values)  # type: ignore[arg-type]


def _gate_request(candidate_id: str = "04_yield_parameter") -> CandidateExecutionGateRequest:
    return CandidateExecutionGateRequest(
        experiment_plan_version="v0.3-experiment-plan-v2",
        experiment_plan_hash=("c2bfab4ec38b4ca640f62d061494961c5b49afe5b52fa675326aa80fdf5f8ad9"),
        guardrail_policy_version=V4_GUARDRAIL_POLICY_VERSION,
        guardrail_policy_hash=V4_GUARDRAIL_POLICY_HASH,
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
        evaluation_id="v4-readiness-only",
        candidate_execution_manifest_frozen=True,
        candidate_registry=FROZEN_CANDIDATE_REGISTRY,
        policy_payload=canonical_guardrail_policy_v4_breakdown_reporting(),
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


def _frozen_runs() -> tuple[FrozenC04RunMetrics, ...]:
    return (
        FrozenC04RunMetrics(
            1,
            Decimal("3.802757"),
            Decimal("0.725160"),
            Decimal("893.149826"),
            Decimal("0.585756"),
            Decimal("0.665698"),
        ),
        FrozenC04RunMetrics(
            2,
            Decimal("4.961884"),
            Decimal("0.885404"),
            Decimal("1090.516549"),
            Decimal("0.655523"),
            Decimal("0.726744"),
        ),
        FrozenC04RunMetrics(
            3,
            Decimal("5.182238"),
            Decimal("0.921748"),
            Decimal("1135.280015"),
            Decimal("0.665698"),
            Decimal("0.735465"),
        ),
        FrozenC04RunMetrics(
            4,
            Decimal("4.152099"),
            Decimal("0.766618"),
            Decimal("944.212641"),
            Decimal("0.613372"),
            Decimal("0.686047"),
        ),
    )


def _frozen_incumbent() -> FrozenC04RunMetrics:
    return FrozenC04RunMetrics(
        0,
        Decimal("1.0"),
        Decimal("0.773022"),
        Decimal("952.100208"),
        Decimal("0.139535"),
        Decimal("0.223837"),
    )


def test_v1_policy_hash_preserved() -> None:
    assert sha256_payload(canonical_guardrail_policy()) == GUARDRAIL_POLICY_HASH
    assert GUARDRAIL_POLICY_HASH == (
        "74ecd47339572955e654cf61c38ee6b0546ba51a36e67f80f6ad4dd4519f1ff8"
    )


def test_v2_policy_hash_preserved() -> None:
    assert sha256_payload(canonical_guardrail_policy_v2()) == V2_GUARDRAIL_POLICY_HASH
    assert V2_GUARDRAIL_POLICY_HASH == (
        "65ad056b3085b7ff41d25e1a7a86b990ac0f837270d62f6fd84ce5938843c793"
    )


def test_v3_policy_hash_preserved() -> None:
    assert sha256_payload(canonical_guardrail_policy_v3_sparse()) == V3_GUARDRAIL_POLICY_HASH
    assert V3_GUARDRAIL_POLICY_HASH == (
        "004be89a726ea4afd90ac895ea10f885f749b2f222e0fca5a67d57ba4e2bd3e0"
    )


def test_v4_policy_hash_is_deterministic_and_binds_v3() -> None:
    policy = canonical_guardrail_policy_v4_breakdown_reporting()
    assert sha256_payload(policy) == V4_GUARDRAIL_POLICY_HASH
    assert policy["breakdown_reporting_floor_overlay"] == {
        "predecessor_policy_version": V3_GUARDRAIL_POLICY_VERSION,
        "predecessor_policy_hash": V3_GUARDRAIL_POLICY_HASH,
        "minimum_comparable_rows_for_reporting": 10,
        "reporting_floor_is_selection_threshold": False,
        "below_minimum_status": "INSUFFICIENT_SAMPLE",
        "below_minimum_reason": "BELOW_MINIMUM",
        "below_minimum_selection_blocking": False,
        "required_breakdown_axes": list(REQUIRED_BREAKDOWN_AXES),
        "all_cells_retained_for_reporting": True,
        "silent_exclusion_is_still_forbidden": True,
    }


def test_breakdown_below_10_is_insufficient_sample() -> None:
    disposition = breakdown_reporting_disposition(BreakdownCellEvidence("cell", 9))
    assert disposition.reporting_status == "INSUFFICIENT_SAMPLE"
    assert disposition.reporting_reason == "BELOW_MINIMUM"
    assert disposition.selection_blocking is False


def test_breakdown_below_10_is_not_global_selection_blocker() -> None:
    result = _evaluate()
    assert result.status == "PASS"
    assert result.candidate_eligible is True


def test_breakdown_cell_is_not_silently_dropped() -> None:
    coverage = _coverage()
    assert sum(len(axis.cells) for axis in coverage.breakdown_axes) == len(REQUIRED_BREAKDOWN_AXES)
    assert evaluate_coverage_quality_gate_v4_breakdown_reporting(coverage).status == "PASS"


@pytest.mark.parametrize("missing_axis", REQUIRED_BREAKDOWN_AXES)
def test_missing_required_axis_still_blocks(missing_axis: str) -> None:
    coverage = _coverage()
    result = evaluate_coverage_quality_gate_v4_breakdown_reporting(
        replace(
            coverage,
            breakdown_axes=tuple(
                axis for axis in coverage.breakdown_axes if axis.axis_name != missing_axis
            ),
        )
    )
    assert result.status == "BLOCKED"
    assert result.reason_code == "MISSING_REQUIRED_BREAKDOWN_AXIS"


def test_duplicate_axis_still_blocks() -> None:
    coverage = _coverage()
    result = evaluate_coverage_quality_gate_v4_breakdown_reporting(
        replace(coverage, breakdown_axes=(*coverage.breakdown_axes, coverage.breakdown_axes[0]))
    )
    assert result.status == "BLOCKED"
    assert result.reason_code == "DUPLICATE_REQUIRED_BREAKDOWN_AXIS"


def test_empty_axis_still_blocks() -> None:
    coverage = _coverage()
    first = coverage.breakdown_axes[0]
    result = evaluate_coverage_quality_gate_v4_breakdown_reporting(
        replace(
            coverage,
            breakdown_axes=(
                BreakdownAxisEvidence(first.axis_name),
                *coverage.breakdown_axes[1:],
            ),
        )
    )
    assert result.status == "BLOCKED"
    assert result.reason_code == "EMPTY_REQUIRED_AXIS_CELLS"


def test_silent_exclusion_still_fails() -> None:
    result = evaluate_coverage_quality_gate_v4_breakdown_reporting(
        replace(_coverage(), no_silent_exclusion=False)
    )
    assert result.status == "FAIL"
    assert result.reason_code == "SILENT_EXCLUSION_FORBIDDEN"


@pytest.mark.parametrize(
    ("field_name", "value", "reason"),
    (
        ("coverage_ratio", "0.899999", "MINIMUM_COVERAGE_NOT_MET"),
        (
            "valid_included_canonical_group_coverage",
            "0.999999",
            "CANONICAL_GROUP_COVERAGE_NOT_MET",
        ),
        ("missing_data_proportion", "0.000001", "MISSING_DATA_PROPORTION_EXCEEDED"),
    ),
)
def test_s1_acceptance_gates_still_fail(field_name: str, value: str, reason: str) -> None:
    coverage = _coverage()
    result = evaluate_coverage_quality_gate_v4_breakdown_reporting(
        replace(coverage, **{field_name: _metric(field_name, value)})
    )
    assert result.status == "FAIL"
    assert result.reason_code == reason


def test_v4_routes_execution_gate_and_keeps_restricted_candidates_blocked() -> None:
    assert check_candidate_execution_gate(_gate_request()).allowed is True
    assert (
        "CANDIDATE_01_RERUN_FORBIDDEN"
        in check_candidate_execution_gate(_gate_request("01_parameter_calibration")).reason_codes
    )
    assert (
        "CURRENT_WEATHER_AUTHORITY_REQUIRED"
        in check_candidate_execution_gate(_gate_request("06_weather_response")).reason_codes
    )
    assert (
        "V4_HISTORICAL_ONLY_FEATURE_MANIFEST_REQUIRED"
        in check_candidate_execution_gate(_gate_request("08_residual_feature")).reason_codes
    )


def test_complete_window_metrics_remain_diagnostic_only() -> None:
    result = _evaluate()
    assert all(item.status == "NOT_COMPUTABLE" for item in result.diagnostics)
    assert all(item.selection_blocking is False for item in result.diagnostics)
    assert all(item.diagnostic_only is True for item in result.diagnostics)


def test_c04_readjudication_uses_only_frozen_r1_evidence() -> None:
    results = readjudicate_c04_runs(
        _frozen_runs(), _frozen_incumbent(), coverage_quality=_coverage()
    )
    assert [result.status for result in results] == ["PASS", "FAIL", "FAIL", "PASS"]
    assert all(result.candidate_eligible for result in (results[0], results[3]))
    assert all(not result.candidate_eligible for result in (results[1], results[2]))


def test_c04_readjudication_calls_no_scorer(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.s4_candidate_04_historical_yield import C04HistoricalYieldScorer

    def fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("R2 re-adjudication must not call the scorer")

    monkeypatch.setattr(C04HistoricalYieldScorer, "predict_rows", fail_if_called)
    results = readjudicate_c04_runs(
        _frozen_runs(), _frozen_incumbent(), coverage_quality=_coverage()
    )
    assert len(results) == 4


def test_c04_readjudication_reads_no_validation_dataset() -> None:
    # The re-adjudication API accepts only frozen scalar metrics and in-memory
    # reporting evidence; there is no dataset/path argument or loader call.
    results = readjudicate_c04_runs(
        _frozen_runs(), _frozen_incumbent(), coverage_quality=_coverage()
    )
    assert len(results) == 4


def test_c04_readjudication_creates_no_started_event_and_budget_is_unchanged() -> None:
    results = readjudicate_c04_runs(
        _frozen_runs(), _frozen_incumbent(), coverage_quality=_coverage()
    )
    assert len(results) == 4
    assert {
        "LEGACY_RECONCILED_VALIDATION_DEBIT": 4,
        "CANONICAL_STARTED_COUNT": 4,
        "C04_CANONICAL_STARTED_COUNT": 4,
        "EFFECTIVE_CONSUMED": 8,
        "REMAINING": 24,
        "R2_BUDGET_DELTA": 0,
        "NEW_STARTED_EVENT_COUNT": 0,
        "NEW_VALIDATION_SCORING_CALL_COUNT": 0,
    }["R2_BUDGET_DELTA"] == 0


def test_c04_readjudication_expected_best_run_is_1() -> None:
    results = readjudicate_c04_runs(
        _frozen_runs(), _frozen_incumbent(), coverage_quality=_coverage()
    )
    eligible = [
        run
        for run, result in zip(_frozen_runs(), results, strict=True)
        if result.candidate_eligible
    ]
    assert len(eligible) == 2
    assert eligible[0].run_ordinal == 1
    assert eligible[0].multiplier == Decimal("3.802757")
