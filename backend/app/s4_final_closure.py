"""Canonical terminal closure for the current V0.3 S4 experiment plan.

This module is a pure control-plane projection.  It consumes the existing
remaining-candidate closure and immutable plan/policy identities; it does not
run a candidate, read validation data, access TEST, or write the budget ledger.
The incumbent is retained only because no admissible replacement was selected
under the frozen plan.  Retention is deliberately not represented as a
validation win or a selected-candidate record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from backend.app.s4_experiment import (
    EXPERIMENT_PLAN_V2_HASH,
    EXPERIMENT_PLAN_V2_VERSION,
    INCUMBENT_MODEL_ID,
    V4_GUARDRAIL_POLICY_HASH,
    V4_GUARDRAIL_POLICY_VERSION,
)
from backend.app.s4_remaining_candidate_viability import (
    DURABLE_BUDGET_READBACK_AVAILABLE,
    LAST_ACCEPTED_CANONICAL_STARTED_COUNT,
    LAST_ACCEPTED_DURABLE_BUDGET_EVIDENCE_PATH,
    LAST_ACCEPTED_DURABLE_BUDGET_EVIDENCE_SHA256,
    LAST_ACCEPTED_EFFECTIVE_CONSUMED,
    LAST_ACCEPTED_REMAINING,
    FrozenS4Closure,
    build_frozen_s4_closure,
)

TASK_ID: Final[str] = "V0_3_S4_INCUMBENT_RETENTION_FINAL_CLOSURE_R1"
SELECTED_CANDIDATE_NOT_ISSUED: Final[str] = "NOT_ISSUED"
NO_EXECUTABLE_CANDIDATE: Final[str] = "NONE"
S4_FINAL_STATUS: Final[str] = "CLOSED_NO_ADMISSIBLE_REPLACEMENT_SELECTED"
INCUMBENT_RETENTION_REASON: Final[str] = "NO_ADMISSIBLE_REPLACEMENT_SELECTED_UNDER_FROZEN_PLAN"
BUDGET_STATE_CLASS: Final[str] = "LAST_ACCEPTED_DURABLE_BUDGET_SNAPSHOT"
NEW_EXPERIMENT_PLAN_NOT_ISSUED: Final[str] = "NOT_ISSUED"


class S4FinalClosureError(RuntimeError):
    """Base error for a closure that cannot be issued safely."""


class S4FinalClosureBlocked(S4FinalClosureError):
    """Raised when the canonical candidate closure is not terminal."""


class S4SelectionStateConflict(S4FinalClosureError):
    """Raised when a selected candidate is supplied to a no-selection closure."""


@dataclass(frozen=True, slots=True)
class CandidateDisposition:
    """One candidate disposition copied from the canonical closure object."""

    candidate_id: str
    currently_runnable_under_v4: bool
    reason_code: str

    def payload(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "currently_runnable_under_v4": self.currently_runnable_under_v4,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class S4FinalClosure:
    """Immutable, no-selection terminal state for the current V0.3 S4 plan."""

    s4_final_status: str
    incumbent_retention_reason: str
    experiment_plan_version: str
    experiment_plan_hash: str
    experiment_plan_execution_status: str
    experiment_plan_reopen_authorized: bool
    guardrail_policy_version: str
    guardrail_policy_hash: str
    selected_candidate_id: str
    selected_candidate_count: int
    incumbent_model_id: str
    incumbent_retained: bool
    incumbent_is_s4_selected_candidate: bool
    incumbent_declared_validation_winner: bool
    candidate_dispositions: tuple[CandidateDisposition, ...]
    next_executable_candidate: str
    current_frozen_plan_has_no_remaining_executable_candidate: bool
    multiple_comparison_final_selection_performed: bool
    holm_adjustment_performed: bool
    multiple_comparison_reason: str
    test_evaluation_authorized: bool
    test_rows_selected: bool
    test_labels_loaded: bool
    test_bytes_read: bool
    test_scoring_performed: bool
    test_remains_sealed: bool
    s4_model_change_authorized: bool
    s4_parameter_change_authorized: bool
    production_model_change_performed: bool
    production_parameter_change_performed: bool
    model_approved_for_pilot: bool
    pilot_deployment_authorized: bool
    new_experiment_plan_authorized: bool
    new_experiment_plan_version: str
    new_guardrail_policy_authorized: bool
    budget_state_class: str
    durable_budget_readback_available: bool
    last_accepted_canonical_started_count: int
    effective_consumed: int
    remaining_validation_budget_unused: int
    budget_carry_forward_authorized: bool
    budget_delta: int
    new_validation_execution: bool
    new_validation_scoring: bool
    new_started_event_count: int
    new_terminal_event_count: int
    budget_provenance_path: str
    budget_provenance_sha256: str

    def payload(self) -> dict[str, object]:
        """Return the deterministic machine-readable closure projection."""

        return {
            "task_id": TASK_ID,
            "s4_final_status": self.s4_final_status,
            "incumbent_retention_reason": self.incumbent_retention_reason,
            "experiment_plan": {
                "version": self.experiment_plan_version,
                "hash": self.experiment_plan_hash,
                "execution_status": self.experiment_plan_execution_status,
                "reopen_authorized": self.experiment_plan_reopen_authorized,
            },
            "guardrail_policy": {
                "version": self.guardrail_policy_version,
                "hash": self.guardrail_policy_hash,
            },
            "selected_candidate_id": self.selected_candidate_id,
            "selected_candidate_count": self.selected_candidate_count,
            "incumbent": {
                "model_id": self.incumbent_model_id,
                "retained": self.incumbent_retained,
                "is_s4_selected_candidate": self.incumbent_is_s4_selected_candidate,
                "declared_validation_winner": self.incumbent_declared_validation_winner,
            },
            "candidate_dispositions": [
                disposition.payload() for disposition in self.candidate_dispositions
            ],
            "next_executable_candidate": self.next_executable_candidate,
            "current_frozen_plan_has_no_remaining_executable_candidate": (
                self.current_frozen_plan_has_no_remaining_executable_candidate
            ),
            "multiple_comparison": {
                "final_selection_performed": self.multiple_comparison_final_selection_performed,
                "holm_adjustment_performed": self.holm_adjustment_performed,
                "reason": self.multiple_comparison_reason,
            },
            "test_boundary": {
                "evaluation_authorized": self.test_evaluation_authorized,
                "rows_selected": self.test_rows_selected,
                "labels_loaded": self.test_labels_loaded,
                "bytes_read": self.test_bytes_read,
                "scoring_performed": self.test_scoring_performed,
                "remains_sealed": self.test_remains_sealed,
            },
            "model_and_pilot_boundary": {
                "s4_model_change_authorized": self.s4_model_change_authorized,
                "s4_parameter_change_authorized": self.s4_parameter_change_authorized,
                "production_model_change_performed": self.production_model_change_performed,
                "production_parameter_change_performed": (
                    self.production_parameter_change_performed
                ),
                "model_approved_for_pilot": self.model_approved_for_pilot,
                "pilot_deployment_authorized": self.pilot_deployment_authorized,
            },
            "new_plan_boundary": {
                "experiment_plan_authorized": self.new_experiment_plan_authorized,
                "experiment_plan_version": self.new_experiment_plan_version,
                "guardrail_policy_authorized": self.new_guardrail_policy_authorized,
            },
            "budget": {
                "state_class": self.budget_state_class,
                "durable_budget_readback_available": self.durable_budget_readback_available,
                "last_accepted_canonical_started_count": (
                    self.last_accepted_canonical_started_count
                ),
                "effective_consumed": self.effective_consumed,
                "remaining_validation_budget_unused": self.remaining_validation_budget_unused,
                "budget_carry_forward_authorized": self.budget_carry_forward_authorized,
                "budget_delta": self.budget_delta,
                "new_started_event_count": self.new_started_event_count,
                "new_terminal_event_count": self.new_terminal_event_count,
                "provenance": {
                    "evidence_path": self.budget_provenance_path,
                    "evidence_sha256": self.budget_provenance_sha256,
                },
            },
            "execution_boundary": {
                "new_validation_execution": self.new_validation_execution,
                "new_validation_scoring": self.new_validation_scoring,
            },
        }


def _candidate_dispositions(closure: FrozenS4Closure) -> tuple[CandidateDisposition, ...]:
    return tuple(
        CandidateDisposition(
            candidate_id=candidate_id,
            currently_runnable_under_v4=runnable,
            reason_code=reason_code,
        )
        for candidate_id, runnable, reason_code in closure.candidate_runnability
    )


def build_s4_final_closure(
    *, selected_candidate_id: str = SELECTED_CANDIDATE_NOT_ISSUED
) -> S4FinalClosure:
    """Build the terminal closure from #602's canonical closure object.

    ``selected_candidate_id`` is an explicit injection point for conflict
    tests or a future authoritative selection record.  The current closure
    accepts only ``NOT_ISSUED``; a real selection must be handled by a separate
    governance task rather than being folded into incumbent retention.
    """

    canonical_closure = build_frozen_s4_closure()
    if (
        canonical_closure.next_executable_candidate != NO_EXECUTABLE_CANDIDATE
        or not canonical_closure.current_frozen_plan_has_no_remaining_executable_candidate
        or any(runnable for _, runnable, _ in canonical_closure.candidate_runnability)
    ):
        raise S4FinalClosureBlocked(
            "S4_FINAL_STATUS=NOT_CLOSED: canonical closure still has a runnable candidate"
        )
    if selected_candidate_id != SELECTED_CANDIDATE_NOT_ISSUED:
        raise S4SelectionStateConflict(
            f"S4_SELECTION_STATE_CONFLICT:selected_candidate_id={selected_candidate_id}"
        )

    return S4FinalClosure(
        s4_final_status=S4_FINAL_STATUS,
        incumbent_retention_reason=INCUMBENT_RETENTION_REASON,
        experiment_plan_version=EXPERIMENT_PLAN_V2_VERSION,
        experiment_plan_hash=EXPERIMENT_PLAN_V2_HASH,
        experiment_plan_execution_status="CLOSED",
        experiment_plan_reopen_authorized=False,
        guardrail_policy_version=V4_GUARDRAIL_POLICY_VERSION,
        guardrail_policy_hash=V4_GUARDRAIL_POLICY_HASH,
        selected_candidate_id=SELECTED_CANDIDATE_NOT_ISSUED,
        selected_candidate_count=0,
        incumbent_model_id=INCUMBENT_MODEL_ID,
        incumbent_retained=True,
        incumbent_is_s4_selected_candidate=False,
        incumbent_declared_validation_winner=False,
        candidate_dispositions=_candidate_dispositions(canonical_closure),
        next_executable_candidate=canonical_closure.next_executable_candidate,
        current_frozen_plan_has_no_remaining_executable_candidate=(
            canonical_closure.current_frozen_plan_has_no_remaining_executable_candidate
        ),
        multiple_comparison_final_selection_performed=False,
        holm_adjustment_performed=False,
        multiple_comparison_reason="NO_CANDIDATE_SELECTION_ISSUED",
        test_evaluation_authorized=False,
        test_rows_selected=False,
        test_labels_loaded=False,
        test_bytes_read=False,
        test_scoring_performed=False,
        test_remains_sealed=True,
        s4_model_change_authorized=False,
        s4_parameter_change_authorized=False,
        production_model_change_performed=False,
        production_parameter_change_performed=False,
        model_approved_for_pilot=False,
        pilot_deployment_authorized=False,
        new_experiment_plan_authorized=False,
        new_experiment_plan_version=NEW_EXPERIMENT_PLAN_NOT_ISSUED,
        new_guardrail_policy_authorized=False,
        budget_state_class=BUDGET_STATE_CLASS,
        durable_budget_readback_available=DURABLE_BUDGET_READBACK_AVAILABLE,
        last_accepted_canonical_started_count=LAST_ACCEPTED_CANONICAL_STARTED_COUNT,
        effective_consumed=LAST_ACCEPTED_EFFECTIVE_CONSUMED,
        remaining_validation_budget_unused=LAST_ACCEPTED_REMAINING,
        budget_carry_forward_authorized=False,
        budget_delta=0,
        new_validation_execution=False,
        new_validation_scoring=False,
        new_started_event_count=0,
        new_terminal_event_count=0,
        budget_provenance_path=LAST_ACCEPTED_DURABLE_BUDGET_EVIDENCE_PATH,
        budget_provenance_sha256=LAST_ACCEPTED_DURABLE_BUDGET_EVIDENCE_SHA256,
    )


def build_s4_final_closure_payload() -> dict[str, object]:
    """Return the canonical payload used by the checked-in closure evidence."""

    return build_s4_final_closure().payload()


def build_machine_derived_s4_final_closure_payload() -> dict[str, object]:
    """Explicit name for the exact evidence projection used in tests."""

    return build_s4_final_closure_payload()


__all__ = [
    "BUDGET_STATE_CLASS",
    "CandidateDisposition",
    "EXPERIMENT_PLAN_V2_HASH",
    "EXPERIMENT_PLAN_V2_VERSION",
    "INCUMBENT_MODEL_ID",
    "INCUMBENT_RETENTION_REASON",
    "NO_EXECUTABLE_CANDIDATE",
    "NEW_EXPERIMENT_PLAN_NOT_ISSUED",
    "S4FinalClosure",
    "S4FinalClosureBlocked",
    "S4FinalClosureError",
    "S4SelectionStateConflict",
    "S4_FINAL_STATUS",
    "SELECTED_CANDIDATE_NOT_ISSUED",
    "TASK_ID",
    "V4_GUARDRAIL_POLICY_HASH",
    "V4_GUARDRAIL_POLICY_VERSION",
    "build_machine_derived_s4_final_closure_payload",
    "build_s4_final_closure",
    "build_s4_final_closure_payload",
]
