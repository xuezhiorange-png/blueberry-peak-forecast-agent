"""Read-only closure audit tests for the remaining V0.3 S4 candidates."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from backend.app.s4_experiment import (
    EXPERIMENT_PLAN_V2_HASH,
    EXPERIMENT_PLAN_V2_VERSION,
    V2_CANDIDATE_06_EXECUTION_ELIGIBLE,
    V2_CANDIDATE_08_EXECUTION_ELIGIBLE,
    V4_GUARDRAIL_POLICY_HASH,
    V4_GUARDRAIL_POLICY_VERSION,
)
from backend.app.s4_remaining_candidate_viability import (
    C02_ID,
    C02_PATH_BLOCKER,
    C02_STRUCTURAL_BLOCKER,
    C04_EXHAUSTED_EVIDENCE,
    C05_BLOCKER,
    C05_ID,
    C07_BLOCKER,
    C07_ID,
    DURABLE_BUDGET_READBACK_AVAILABLE,
    LAST_ACCEPTED_CANONICAL_STARTED_COUNT,
    LAST_ACCEPTED_DURABLE_BUDGET_EVIDENCE_PATH,
    LAST_ACCEPTED_DURABLE_BUDGET_EVIDENCE_SHA256,
    LAST_ACCEPTED_EFFECTIVE_CONSUMED,
    LAST_ACCEPTED_REMAINING,
    LEGACY_RECONCILED_VALIDATION_DEBIT,
    RemainingCandidateViability,
    build_frozen_s4_closure,
    build_machine_derived_audit_payload,
    build_remaining_candidate_audit_payload,
    build_remaining_candidate_viability_audit,
    c02_quantile_effect_proof,
)
from backend.app.s4_v2_historical_only_execution import (
    V2_C05_CANONICAL_EXECUTION_FUNCTIONS,
    V2_C05_CANONICAL_PARAMETER_PATH,
    V2_C05_CANONICAL_SOURCE_DOMAIN,
    V2_C07_CANONICAL_EXECUTION_FUNCTIONS,
    V2_C07_CANONICAL_PARAMETER_PATH,
    V2_C07_CANONICAL_SOURCE_DOMAIN,
    V2_CANDIDATE_AUDIT_ORDER,
    build_v2_candidate_compatibility_audit,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_PATH = (
    REPO_ROOT / "docs/v0-3/s4/evidence/s4-remaining-candidate-viability-and-closure-audit-r1.json"
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


def test_c02_quantile_effect_proof_is_machine_derived() -> None:
    proof = c02_quantile_effect_proof()
    assert proof["p50_unchanged"] is True
    assert proof["p80_changed"] is True
    assert proof["p90_changed"] is True
    assert proof["equal_wape_is_not_improved"] is True


def test_c02_p80_p90_changes_do_not_change_p50() -> None:
    proof = c02_quantile_effect_proof()
    assert proof["p80_changed"] is True
    assert proof["p90_changed"] is True
    assert proof["p50_unchanged"] is True


def test_c02_v4_primary_requires_strict_wape_improvement() -> None:
    payload = build_remaining_candidate_audit_payload()
    selection_policy = payload["selection_policy"]
    assert isinstance(selection_policy, dict)
    assert selection_policy["primary_metric"] == "daily_wape"
    assert selection_policy["primary_required_relation"] == (
        "CANDIDATE_STRICTLY_LESS_THAN_INCUMBENT"
    )
    assert selection_policy["c02_implementation_blocker"] == C02_PATH_BLOCKER
    assert selection_policy["c02_structural_selection_blocker"] == C02_STRUCTURAL_BLOCKER
    assert selection_policy["c02_requires_policy_amendment"] is True


def test_c02_equal_wape_is_not_improved_under_v4() -> None:
    proof = c02_quantile_effect_proof()
    assert proof["equal_daily_wape_status"] == "FAIL"
    assert proof["equal_daily_wape_reason_code"] == "NOT_IMPROVED"


def test_c02_requires_policy_amendment() -> None:
    row = _audit_by_id()[C02_ID]
    assert row.requires_policy_amendment is True


def test_c02_quantile_only_candidate_is_not_selectable_under_strict_point_primary() -> None:
    row = _audit_by_id()[C02_ID]
    assert row.structurally_selectable_under_v4 is False
    assert row.reason_code == C02_STRUCTURAL_BLOCKER
    assert row.secondary_reason_codes == (C02_PATH_BLOCKER,)
    assert row.implementation_blocker == C02_PATH_BLOCKER
    assert row.structural_selection_blocker == C02_STRUCTURAL_BLOCKER
    assert row.requires_policy_amendment is True


def test_c05_canonical_marketable_rate_path_is_audited() -> None:
    row = _audit_by_id()[C05_ID]
    assert row.parameter_or_feature_path == ("marketable_rate",)
    assert row.canonical_parameter_path == V2_C05_CANONICAL_PARAMETER_PATH
    assert row.canonical_execution_functions == V2_C05_CANONICAL_EXECUTION_FUNCTIONS
    assert row.canonical_source_domain == V2_C05_CANONICAL_SOURCE_DOMAIN
    assert "backend.app.core_forecast.service.compose_complete_daily_marketable_curve" not in (
        row.actual_execution_function
    )
    assert "backend.app.planning.plan_service._derived_total" in row.actual_execution_function
    assert row.uses_task8 is False
    assert row.uses_task9 is False
    assert row.uses_production_plan is True
    assert row.parameter_reaches_prediction_math is True
    assert row.parameter_change_can_change_prediction is True
    assert row.explicit_total_override_exists is True
    assert row.reason_code == C05_BLOCKER


def test_c05_core_curve_does_not_reapply_marketable_rate() -> None:
    row = _audit_by_id()[C05_ID]
    assert (
        "backend.app.core_forecast.service.compose_complete_daily_marketable_curve"
        not in row.actual_execution_function
    )
    payload = build_remaining_candidate_audit_payload()
    path_audit = payload["c05_canonical_path_audit"]
    assert isinstance(path_audit, dict)
    assert path_audit["core_curve_does_not_reapply_marketable_rate"] is True


def test_c05_market_rate_role_is_bound_to_real_upstream_path() -> None:
    assert "backend.app.planning.plan_service._derived_total" in (
        V2_C05_CANONICAL_EXECUTION_FUNCTIONS
    )
    assert "backend.app.maturity.service._resolve_training_sample" in (
        V2_C05_CANONICAL_EXECUTION_FUNCTIONS
    )
    assert "backend.app.models.production_plan.FarmSeasonVarietyPlan.marketable_rate" in (
        V2_C05_CANONICAL_PARAMETER_PATH
    )


def test_c05_retention_rates_are_not_market_rate() -> None:
    row = _audit_by_id()[C05_ID]
    assert row.parameter_or_feature_path == ("marketable_rate",)
    assert "sorting_retention_rate" not in V2_C05_CANONICAL_PARAMETER_PATH
    assert "postharvest_retention_rate" not in V2_C05_CANONICAL_PARAMETER_PATH


def test_c05_source002_field_availability_is_explicit() -> None:
    row = _audit_by_id()[C05_ID]
    assert row.source_002_only_candidate_path_exists is False
    assert row.uses_source_002_train is False
    assert row.uses_source_002_validation is False
    assert row.historical_only_input_compatible is False
    assert row.historical_only_execution_compatible is False


def test_c05_missing_authority_fails_closed() -> None:
    row = _audit_by_id()[C05_ID]
    assert row.currently_runnable_under_v4 is False
    assert row.structurally_selectable_under_v4 is False


def test_c07_canonical_harvest_efficiency_path_is_audited() -> None:
    row = _audit_by_id()[C07_ID]
    assert row.parameter_or_feature_path == ("harvest_efficiency",)
    assert row.canonical_parameter_path == V2_C07_CANONICAL_PARAMETER_PATH
    assert row.canonical_execution_functions == V2_C07_CANONICAL_EXECUTION_FUNCTIONS
    assert row.canonical_source_domain == V2_C07_CANONICAL_SOURCE_DOMAIN
    assert row.actual_execution_function == V2_C07_CANONICAL_EXECUTION_FUNCTIONS
    assert row.canonical_parameter_path[-1] == "resolved_effective_capacity_kg_per_day"
    assert row.uses_weather is True
    assert row.uses_task9 is True
    assert row.parameter_reaches_prediction_math is True
    assert row.parameter_change_can_change_prediction is True
    assert row.reason_code == C07_BLOCKER


def test_c07_effective_capacity_inputs_are_bound_to_real_harvest_state_path() -> None:
    row = _audit_by_id()[C07_ID]
    assert row.canonical_parameter_path == V2_C07_CANONICAL_PARAMETER_PATH
    assert row.canonical_execution_functions == V2_C07_CANONICAL_EXECUTION_FUNCTIONS
    assert row.canonical_source_domain == V2_C07_CANONICAL_SOURCE_DOMAIN
    assert "resolved_effective_capacity_kg_per_day" in row.canonical_parameter_path
    assert "WEATHER_FEATURE_AUTHORITY" in row.canonical_source_domain
    assert "TASK9_DAILY_CAPACITY_AUTHORITY" in row.canonical_source_domain


def test_c07_source002_field_availability_is_explicit() -> None:
    row = _audit_by_id()[C07_ID]
    assert row.source_002_only_candidate_path_exists is False
    assert row.uses_source_002_train is False
    assert row.uses_source_002_validation is False
    assert row.historical_only_input_compatible is False
    assert row.historical_only_execution_compatible is False


def test_c07_missing_authority_fails_closed() -> None:
    row = _audit_by_id()[C07_ID]
    assert row.currently_runnable_under_v4 is False
    assert row.structurally_selectable_under_v4 is False


def test_audit_imports_canonical_experiment_plan_identity() -> None:
    payload = build_remaining_candidate_audit_payload()
    assert payload["experiment_plan_version"] == EXPERIMENT_PLAN_V2_VERSION
    assert payload["experiment_plan_hash"] == EXPERIMENT_PLAN_V2_HASH


def test_audit_imports_canonical_v4_policy_identity() -> None:
    payload = build_remaining_candidate_audit_payload()
    assert payload["guardrail_policy_version"] == V4_GUARDRAIL_POLICY_VERSION
    assert payload["guardrail_policy_hash"] == V4_GUARDRAIL_POLICY_HASH


def test_historical_execution_eligibility_matches_v2_authority() -> None:
    expected = {
        row.candidate_id: row.current_v0_3_execution_eligible
        for row in build_v2_candidate_compatibility_audit()
    }
    payload = build_remaining_candidate_audit_payload()
    assert payload["v2_current_execution_eligibility"] == expected
    assert payload["frozen_plan_eligibility"] == expected


def test_candidate_06_historical_execution_eligible_false() -> None:
    rows = {row.candidate_id: row for row in build_v2_candidate_compatibility_audit()}
    assert V2_CANDIDATE_06_EXECUTION_ELIGIBLE is False
    assert rows["06_weather_response"].current_v0_3_execution_eligible is False


def test_candidate_08_historical_execution_eligible_false() -> None:
    rows = {row.candidate_id: row for row in build_v2_candidate_compatibility_audit()}
    assert V2_CANDIDATE_08_EXECUTION_ELIGIBLE is False
    assert rows["08_residual_feature"].current_v0_3_execution_eligible is False


def test_registry_selection_eligibility_is_separate_from_execution_eligibility() -> None:
    payload = build_remaining_candidate_audit_payload()
    registry = payload["frozen_registry_selection_eligibility"]
    current = payload["v2_current_execution_eligibility"]
    assert isinstance(registry, dict)
    assert isinstance(current, dict)
    assert set(registry) == set(V2_CANDIDATE_AUDIT_ORDER)
    assert all(
        entry["selection_eligibility"] == "REGISTERED_AND_GUARDRAIL_ELIGIBLE"
        for entry in registry.values()
    )
    assert current["06_weather_response"] is False
    assert current["08_residual_feature"] is False


def test_current_runnability_is_derived_from_authority_facts() -> None:
    closure = build_frozen_s4_closure()
    actual = {
        row["candidate_id"]: (row["currently_runnable_under_v4"], row["reason_code"])
        for row in closure.payload()["candidate_runnability"]
    }
    assert actual["01_parameter_calibration"] == (
        False,
        "CANDIDATE_01_RERUN_FORBIDDEN",
    )
    assert actual[C02_ID] == (False, C02_STRUCTURAL_BLOCKER)
    assert actual["04_yield_parameter"] == (False, C04_EXHAUSTED_EVIDENCE)
    assert actual[C05_ID] == (False, C05_BLOCKER)
    assert actual[C07_ID] == (False, C07_BLOCKER)
    assert all(runnable is False for runnable, _ in actual.values())


def test_current_runnability_is_derived_not_static_copy() -> None:
    closure = build_frozen_s4_closure()
    payload = build_remaining_candidate_audit_payload()
    closure_payload = payload["frozen_s4_closure"]
    assert closure_payload == closure.payload()
    assert closure.next_executable_candidate == "NONE"
    assert all(not runnable for _, runnable, _ in closure.candidate_runnability)


def test_checked_in_evidence_matches_canonical_audit_payload() -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert evidence["MACHINE_DERIVED_AUDIT_PAYLOAD"] == build_machine_derived_audit_payload()


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


def test_budget_claim_has_explicit_snapshot_provenance() -> None:
    payload = build_remaining_candidate_audit_payload()
    budget = payload["budget"]
    assert isinstance(budget, dict)
    assert DURABLE_BUDGET_READBACK_AVAILABLE is False
    assert budget["state_class"] == "LAST_ACCEPTED_DURABLE_BUDGET_SNAPSHOT"
    assert budget["values_are_current_database_readback"] is False
    assert budget["canonical_started_count"] == LAST_ACCEPTED_CANONICAL_STARTED_COUNT
    assert budget["effective_consumed"] == LAST_ACCEPTED_EFFECTIVE_CONSUMED
    assert budget["remaining"] == LAST_ACCEPTED_REMAINING
    assert budget["legacy_reconciled_validation_debit"] == 4
    assert budget["provenance"] == {
        "evidence_path": LAST_ACCEPTED_DURABLE_BUDGET_EVIDENCE_PATH,
        "evidence_sha256": LAST_ACCEPTED_DURABLE_BUDGET_EVIDENCE_SHA256,
    }
    assert LEGACY_RECONCILED_VALIDATION_DEBIT == 4


def test_no_ledger_write_or_validation_read_path_exists() -> None:
    from backend.app import s4_remaining_candidate_viability as module

    source = inspect.getsource(module)
    assert "S4ValidationBudgetRepository" not in source
    assert "load_frozen_engineering_dataset" not in source
    assert "predict_rows" not in source
    assert "execute(" not in source


def test_no_ledger_write() -> None:
    from backend.app import s4_remaining_candidate_viability as module

    source = inspect.getsource(module)
    assert "S4ValidationBudgetRepository" not in source
    assert "session.commit" not in source
    assert "INSERT INTO" not in source


def test_no_validation_read() -> None:
    from backend.app import s4_remaining_candidate_viability as module

    source = inspect.getsource(module)
    assert "load_frozen_engineering_dataset" not in source
    assert "predict_rows" not in source
    assert "validation actual" not in source.lower()


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
