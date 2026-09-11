"""Read-only closure audit tests for the remaining V0.3 S4 candidates."""

from __future__ import annotations

from backend.app.s4_remaining_candidate_viability import (
    AUDIT_CANDIDATE_IDS,
    C02_ID,
    C02_PATH_BLOCKER,
    C02_STRUCTURAL_BLOCKER,
    C05_BLOCKER,
    C05_ID,
    C07_BLOCKER,
    C07_ID,
    CANONICAL_STARTED_COUNT,
    EFFECTIVE_CONSUMED,
    LEGACY_RECONCILED_VALIDATION_DEBIT,
    REMAINING_VALIDATION_BUDGET,
    RemainingCandidateViability,
    build_frozen_s4_closure,
    build_remaining_candidate_audit_payload,
    build_remaining_candidate_viability_audit,
)


def _audit_by_id() -> dict[str, RemainingCandidateViability]:
    return {row.candidate_id: row for row in build_remaining_candidate_viability_audit()}


def test_c02_quantile_parameters_do_not_mutate_p50() -> None:
    row = _audit_by_id()[C02_ID]
    assert row.parameter_or_feature_path == (
        "intervals.p80_quantile",
        "intervals.p90_quantile",
    )
    assert row.parameter_reaches_prediction_math is False
    assert row.parameter_change_can_change_prediction is False
    assert "P50" in row.canonical_control_fields


def test_c02_v4_primary_requires_strict_wape_improvement() -> None:
    payload = build_remaining_candidate_audit_payload()
    selection_policy = payload["selection_policy"]
    assert isinstance(selection_policy, dict)
    assert selection_policy["primary_metric"] == "daily_wape"
    assert selection_policy["primary_required_relation"] == (
        "CANDIDATE_STRICTLY_LESS_THAN_INCUMBENT"
    )


def test_c02_quantile_only_candidate_is_not_selectable_under_strict_point_primary() -> None:
    row = _audit_by_id()[C02_ID]
    assert row.structurally_selectable_under_v4 is False
    assert row.reason_code == C02_STRUCTURAL_BLOCKER
    assert row.secondary_reason_codes == (C02_PATH_BLOCKER,)


def test_c05_canonical_marketable_rate_path_is_audited() -> None:
    row = _audit_by_id()[C05_ID]
    assert row.parameter_or_feature_path == ("marketable_rate",)
    assert "backend.app.core_forecast.service.compose_complete_daily_marketable_curve" in (
        row.actual_execution_function
    )
    assert row.uses_task8 is True
    assert row.uses_task9 is True
    assert row.uses_production_plan is True
    assert row.reason_code == C05_BLOCKER


def test_c05_source002_field_availability_is_explicit() -> None:
    row = _audit_by_id()[C05_ID]
    assert row.source_002_only_candidate_path_exists is False
    assert row.uses_source_002_train is False
    assert row.uses_source_002_validation is False
    assert row.historical_only_input_compatible is False


def test_c05_missing_authority_fails_closed() -> None:
    row = _audit_by_id()[C05_ID]
    assert row.historical_only_execution_compatible is False
    assert row.currently_runnable_under_v4 is False
    assert row.structurally_selectable_under_v4 is False


def test_c07_canonical_harvest_efficiency_path_is_audited() -> None:
    row = _audit_by_id()[C07_ID]
    assert row.parameter_or_feature_path == ("harvest_efficiency",)
    assert row.actual_execution_function == (
        "backend.app.harvest_state.service.run_harvest_state_model",
    )
    assert row.canonical_control_fields == (
        "labor_availability_ratio",
        "weather_harvest_efficiency_ratio",
        "operational_efficiency_ratio",
    )
    assert row.uses_weather is True
    assert row.uses_task9 is True
    assert row.reason_code == C07_BLOCKER


def test_c07_source002_field_availability_is_explicit() -> None:
    row = _audit_by_id()[C07_ID]
    assert row.source_002_only_candidate_path_exists is False
    assert row.uses_source_002_train is False
    assert row.uses_source_002_validation is False
    assert row.historical_only_input_compatible is False


def test_c07_missing_authority_fails_closed() -> None:
    row = _audit_by_id()[C07_ID]
    assert row.historical_only_execution_compatible is False
    assert row.currently_runnable_under_v4 is False
    assert row.structurally_selectable_under_v4 is False


def test_no_proxy_candidate_semantics_are_created() -> None:
    rows = build_remaining_candidate_viability_audit()
    assert all(row.source_002_only_candidate_path_exists is False for row in rows)
    assert all("proxy" not in " ".join(row.required_future_authority).lower() for row in rows)
    payload = build_remaining_candidate_audit_payload()
    selection_policy = payload["selection_policy"]
    assert isinstance(selection_policy, dict)
    assert selection_policy["no_proxy_parameter_invention"] is True
    assert selection_policy["no_source002_field_reinterpretation"] is True


def test_frozen_plan_eligibility_is_preserved() -> None:
    payload = build_remaining_candidate_audit_payload()
    eligibility = payload["frozen_plan_eligibility"]
    assert eligibility == {
        "01_parameter_calibration": True,
        "02_quantile_calibration": True,
        "03_phenology_offset": True,
        "04_yield_parameter": True,
        "05_marketable_rate": True,
        "06_weather_response": True,
        "07_harvest_efficiency": True,
        "08_residual_feature": True,
    }


def test_current_runnability_is_separate_from_plan_eligibility() -> None:
    rows = build_remaining_candidate_viability_audit()
    assert tuple(row.candidate_id for row in rows) == AUDIT_CANDIDATE_IDS
    assert all(row.plan_eligible is True for row in rows)
    assert all(row.currently_runnable_under_v4 is False for row in rows)
    assert all(row.plan_eligible != row.currently_runnable_under_v4 for row in rows)


def test_audit_creates_no_started_event() -> None:
    payload = build_remaining_candidate_audit_payload()
    boundary = payload["execution_boundary"]
    assert isinstance(boundary, dict)
    assert boundary["evaluation_started_created"] is False
    assert boundary["evaluation_terminal_created"] is False


def test_audit_performs_no_validation_scoring() -> None:
    payload = build_remaining_candidate_audit_payload()
    boundary = payload["execution_boundary"]
    assert isinstance(boundary, dict)
    assert boundary["validation_execution_authorized"] is False
    assert boundary["validation_scoring_performed"] is False
    assert boundary["candidate_execution_performed"] is False


def test_budget_remains_8_24() -> None:
    payload = build_remaining_candidate_audit_payload()
    budget = payload["budget"]
    assert isinstance(budget, dict)
    assert LEGACY_RECONCILED_VALIDATION_DEBIT == 4
    assert CANONICAL_STARTED_COUNT == 4
    assert EFFECTIVE_CONSUMED == 8
    assert REMAINING_VALIDATION_BUDGET == 24
    assert budget["budget_delta"] == 0


def test_test_remains_sealed() -> None:
    payload = build_remaining_candidate_audit_payload()
    assert payload["test_remains_sealed"] is True
    boundary = payload["execution_boundary"]
    assert isinstance(boundary, dict)
    assert boundary["test_access_requested"] is False
    assert boundary["test_bytes_read"] is False


def test_no_remaining_candidate_is_the_current_closure() -> None:
    closure = build_frozen_s4_closure()
    assert closure.next_executable_candidate == "NONE"
    assert closure.current_frozen_plan_has_no_remaining_executable_candidate is True
    assert closure.s4_next_decision_required == (
        "COORDINATOR_CHOICE_BETWEEN_INCUMBENT_CLOSURE_OR_NEW_EXPERIMENT_PLAN_AUTHORIZATION"
    )
