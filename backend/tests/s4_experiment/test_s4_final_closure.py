"""Contract tests for the terminal no-selection S4 closure."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from backend.app import s4_final_closure as closure_module
from backend.app.s4_experiment import (
    EXPERIMENT_PLAN_V2_HASH,
    EXPERIMENT_PLAN_V2_VERSION,
    INCUMBENT_MODEL_ID,
    V4_GUARDRAIL_POLICY_HASH,
    V4_GUARDRAIL_POLICY_VERSION,
)
from backend.app.s4_remaining_candidate_viability import (
    FrozenS4Closure,
    build_frozen_s4_closure,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_PATH = REPO_ROOT / "docs/v0-3/s4/evidence/s4-incumbent-retention-final-closure-r1.json"


def test_s4_final_closure_consumes_pr602_canonical_closure() -> None:
    closure = closure_module.build_s4_final_closure()
    canonical = build_frozen_s4_closure()
    assert [item.payload() for item in closure.candidate_dispositions] == [
        {
            "candidate_id": candidate_id,
            "currently_runnable_under_v4": runnable,
            "reason_code": reason_code,
        }
        for candidate_id, runnable, reason_code in canonical.candidate_runnability
    ]
    assert closure.next_executable_candidate == canonical.next_executable_candidate == "NONE"
    assert (
        closure.current_frozen_plan_has_no_remaining_executable_candidate
        is canonical.current_frozen_plan_has_no_remaining_executable_candidate
        is True
    )


def test_all_eight_candidates_are_currently_not_runnable() -> None:
    closure = closure_module.build_s4_final_closure()
    assert len(closure.candidate_dispositions) == 8
    assert all(not item.currently_runnable_under_v4 for item in closure.candidate_dispositions)


def test_next_executable_candidate_is_none() -> None:
    closure = closure_module.build_s4_final_closure()
    assert closure.next_executable_candidate == "NONE"
    assert closure.current_frozen_plan_has_no_remaining_executable_candidate is True


def test_selected_candidate_is_not_issued() -> None:
    closure = closure_module.build_s4_final_closure()
    assert closure.selected_candidate_id == "NOT_ISSUED"
    assert closure.selected_candidate_count == 0


def test_selected_candidate_conflict_fails_closed() -> None:
    with pytest.raises(closure_module.S4SelectionStateConflict):
        closure_module.build_s4_final_closure(selected_candidate_id="04_yield_parameter")


def test_nonterminal_canonical_closure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    nonterminal = FrozenS4Closure(
        candidate_runnability=(("04_yield_parameter", True, "NONE"),),
        next_executable_candidate="04_yield_parameter",
        current_frozen_plan_has_no_remaining_executable_candidate=False,
        s4_next_decision_required="NONE",
    )
    monkeypatch.setattr(closure_module, "build_frozen_s4_closure", lambda: nonterminal)
    with pytest.raises(closure_module.S4FinalClosureBlocked):
        closure_module.build_s4_final_closure()


def test_incumbent_is_retained() -> None:
    closure = closure_module.build_s4_final_closure()
    assert closure.incumbent_model_id == INCUMBENT_MODEL_ID == "V0_2_CURRENT_MODEL"
    assert closure.incumbent_retained is True
    assert closure.incumbent_retention_reason == (
        "NO_ADMISSIBLE_REPLACEMENT_SELECTED_UNDER_FROZEN_PLAN"
    )


def test_incumbent_is_not_s4_selected_candidate() -> None:
    closure = closure_module.build_s4_final_closure()
    assert closure.incumbent_is_s4_selected_candidate is False
    assert closure.incumbent_declared_validation_winner is False


def test_no_holm_adjustment_is_run_without_selection() -> None:
    closure = closure_module.build_s4_final_closure()
    assert closure.multiple_comparison_final_selection_performed is False
    assert closure.holm_adjustment_performed is False
    assert closure.multiple_comparison_reason == "NO_CANDIDATE_SELECTION_ISSUED"


def test_no_candidate_ranking_is_issued() -> None:
    payload = closure_module.build_s4_final_closure_payload()
    comparison = payload["multiple_comparison"]
    assert isinstance(comparison, dict)
    assert comparison["final_selection_performed"] is False
    assert comparison["holm_adjustment_performed"] is False


def test_test_evaluation_remains_unauthorized() -> None:
    closure = closure_module.build_s4_final_closure()
    assert closure.test_evaluation_authorized is False
    assert closure.test_scoring_performed is False


def test_test_remains_sealed() -> None:
    closure = closure_module.build_s4_final_closure()
    assert closure.test_rows_selected is False
    assert closure.test_labels_loaded is False
    assert closure.test_bytes_read is False
    assert closure.test_remains_sealed is True


def test_model_change_is_not_authorized() -> None:
    closure = closure_module.build_s4_final_closure()
    assert closure.s4_model_change_authorized is False
    assert closure.s4_parameter_change_authorized is False
    assert closure.production_model_change_performed is False
    assert closure.production_parameter_change_performed is False
    assert closure.model_approved_for_pilot is False


def test_parameter_change_is_not_authorized() -> None:
    closure = closure_module.build_s4_final_closure()
    assert closure.s4_parameter_change_authorized is False
    assert closure.production_parameter_change_performed is False


def test_pilot_is_not_authorized() -> None:
    assert closure_module.build_s4_final_closure().pilot_deployment_authorized is False


def test_no_new_experiment_plan_is_issued() -> None:
    closure = closure_module.build_s4_final_closure()
    assert closure.experiment_plan_version == EXPERIMENT_PLAN_V2_VERSION
    assert closure.experiment_plan_hash == EXPERIMENT_PLAN_V2_HASH
    assert closure.experiment_plan_execution_status == "CLOSED"
    assert closure.experiment_plan_reopen_authorized is False
    assert closure.new_experiment_plan_authorized is False
    assert closure.new_experiment_plan_version == "NOT_ISSUED"
    assert closure.new_guardrail_policy_authorized is False


def test_frozen_plan_and_policy_identities_are_preserved() -> None:
    closure = closure_module.build_s4_final_closure()
    assert closure.guardrail_policy_version == V4_GUARDRAIL_POLICY_VERSION
    assert closure.guardrail_policy_hash == V4_GUARDRAIL_POLICY_HASH


def test_budget_snapshot_provenance_is_explicit() -> None:
    closure = closure_module.build_s4_final_closure()
    assert closure.budget_state_class == "LAST_ACCEPTED_DURABLE_BUDGET_SNAPSHOT"
    assert closure.durable_budget_readback_available is False
    assert closure.last_accepted_canonical_started_count == 4
    assert closure.effective_consumed == 8
    assert closure.remaining_validation_budget_unused == 24
    assert closure.budget_carry_forward_authorized is False
    assert closure.budget_delta == 0
    assert closure.budget_provenance_path.endswith("s4-c04-controlled-real-validation-r1.json")
    assert len(closure.budget_provenance_sha256) == 64


def test_remaining_budget_is_unused_not_auto_carried_forward() -> None:
    closure = closure_module.build_s4_final_closure()
    assert closure.remaining_validation_budget_unused == 24
    assert closure.budget_carry_forward_authorized is False


def test_closure_creates_no_started_event() -> None:
    closure = closure_module.build_s4_final_closure()
    assert closure.new_started_event_count == 0
    assert closure.new_terminal_event_count == 0


def test_closure_performs_no_validation_scoring() -> None:
    closure = closure_module.build_s4_final_closure()
    assert closure.new_validation_execution is False
    assert closure.new_validation_scoring is False


def test_closure_reads_no_test_data() -> None:
    source = inspect.getsource(closure_module)
    assert "S4ValidationBudgetRepository" not in source
    assert "load_frozen_engineering_dataset" not in source
    assert "predict_rows" not in source
    assert "execute(" not in source
    assert "session.commit" not in source


def test_checked_in_closure_evidence_matches_canonical_payload() -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert evidence["MACHINE_DERIVED_CLOSURE_PAYLOAD"] == (
        closure_module.build_machine_derived_s4_final_closure_payload()
    )
