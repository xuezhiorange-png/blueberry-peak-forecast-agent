"""Typed command and readback schemas for the S4 validation budget."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

MAX_VALIDATION_EVALUATIONS = 32
MAX_RUNS_PER_CANDIDATE = 4
LEGACY_RECONCILED_VALIDATION_DEBIT = 4
AUTHORITY_KEY = "V0_3_S4_VALIDATION_BUDGET"
EVENT_STARTED = "EVALUATION_STARTED"
EVENT_TERMINAL = "EVALUATION_TERMINAL"
STARTED_INVOCATION = "STARTED_INVOCATION"

STARTED_BODY_FIELDS: tuple[str, ...] = (
    "evaluation_id",
    "experiment_plan_version",
    "candidate_id",
    "candidate_run_ordinal",
    "global_evaluation_ordinal",
    "invocation_type",
    "trigger_source",
    "started_at",
    "finished_at",
    "execution_status",
    "metric_result_status",
    "dataset_hash",
    "validation_split_hash",
    "code_commit_sha",
    "parameter_manifest_hash",
    "random_seed",
    "retry_of_evaluation_id",
    "counted_toward_budget",
    "budget_count_reason",
)
TERMINAL_BODY_FIELDS: tuple[str, ...] = (
    "evaluation_id",
    "candidate_id",
    "finished_at",
    "execution_status",
    "metric_result_status",
    "counted_toward_budget",
)


@dataclass(frozen=True, slots=True)
class StartedEventCommand:
    """All fields needed to durably append one STARTED invocation."""

    evaluation_id: str
    experiment_plan_version: str
    candidate_id: str
    candidate_run_ordinal: int
    global_evaluation_ordinal: int
    invocation_type: str
    trigger_source: str
    started_at: datetime
    dataset_hash: str
    validation_split_hash: str
    code_commit_sha: str
    parameter_manifest_hash: str
    random_seed: int | None
    finished_at: datetime | None = None
    execution_status: str | None = None
    metric_result_status: str | None = None
    retry_of_evaluation_id: str | None = None
    counted_toward_budget: bool = True
    budget_count_reason: str = STARTED_INVOCATION
    expected_authority_version: int | None = None
    expected_event_count: int | None = None
    expected_started_count: int | None = None
    expected_head_event_hash: str | None = None
    expected_last_global_evaluation_ordinal: int | None = None

    _body_fields: ClassVar[tuple[str, ...]] = STARTED_BODY_FIELDS

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> StartedEventCommand:
        """Build a command from the frozen ledger field mapping."""

        data = dict(value)
        return cls(
            evaluation_id=data["evaluation_id"],
            experiment_plan_version=data["experiment_plan_version"],
            candidate_id=data["candidate_id"],
            candidate_run_ordinal=data["candidate_run_ordinal"],
            global_evaluation_ordinal=data["global_evaluation_ordinal"],
            invocation_type=data["invocation_type"],
            trigger_source=data["trigger_source"],
            started_at=data["started_at"],
            dataset_hash=data["dataset_hash"],
            validation_split_hash=data["validation_split_hash"],
            code_commit_sha=data["code_commit_sha"],
            parameter_manifest_hash=data["parameter_manifest_hash"],
            random_seed=data["random_seed"],
            finished_at=data.get("finished_at"),
            execution_status=data.get("execution_status"),
            metric_result_status=data.get("metric_result_status"),
            retry_of_evaluation_id=data.get("retry_of_evaluation_id"),
            counted_toward_budget=data.get("counted_toward_budget", True),
            budget_count_reason=data.get("budget_count_reason", STARTED_INVOCATION),
        )

    def body(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "experiment_plan_version": self.experiment_plan_version,
            "candidate_id": self.candidate_id,
            "candidate_run_ordinal": self.candidate_run_ordinal,
            "global_evaluation_ordinal": self.global_evaluation_ordinal,
            "invocation_type": self.invocation_type,
            "trigger_source": self.trigger_source,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "execution_status": self.execution_status,
            "metric_result_status": self.metric_result_status,
            "dataset_hash": self.dataset_hash,
            "validation_split_hash": self.validation_split_hash,
            "code_commit_sha": self.code_commit_sha,
            "parameter_manifest_hash": self.parameter_manifest_hash,
            "random_seed": self.random_seed,
            "retry_of_evaluation_id": self.retry_of_evaluation_id,
            "counted_toward_budget": self.counted_toward_budget,
            "budget_count_reason": self.budget_count_reason,
        }


@dataclass(frozen=True, slots=True)
class TerminalEventCommand:
    """All fields needed to append the immutable terminal extension."""

    evaluation_id: str
    candidate_id: str
    finished_at: datetime
    execution_status: str
    metric_result_status: str

    _body_fields: ClassVar[tuple[str, ...]] = TERMINAL_BODY_FIELDS

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> TerminalEventCommand:
        data = dict(value)
        return cls(
            evaluation_id=data["evaluation_id"],
            candidate_id=data["candidate_id"],
            finished_at=data["finished_at"],
            execution_status=data["execution_status"],
            metric_result_status=data["metric_result_status"],
        )

    def body(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "candidate_id": self.candidate_id,
            "finished_at": self.finished_at,
            "execution_status": self.execution_status,
            "metric_result_status": self.metric_result_status,
            "counted_toward_budget": False,
        }


@dataclass(frozen=True, slots=True)
class StoredValidationEvent:
    authority_key: str
    event_sequence: int
    event_type: str
    evaluation_id: str
    candidate_id: str
    event_payload: dict[str, Any]
    previous_event_hash: str
    event_hash: str
    created_at: datetime
    candidate_run_ordinal: int | None = None
    global_evaluation_ordinal: int | None = None
    invocation_type: str | None = None
    counted_toward_budget: bool | None = None
    budget_count_reason: str | None = None
    finished_at: datetime | None = None
    execution_status: str | None = None
    metric_result_status: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationBudgetState:
    authority_key: str
    authority_version: int
    accepted_event_count: int
    accepted_started_count: int
    accepted_head_event_hash: str
    accepted_last_global_evaluation_ordinal: int
    legacy_reconciled_validation_debit: int
    effective_consumed: int
    remaining: int
    events: tuple[StoredValidationEvent, ...] = ()


VerifiedValidationBudgetState = ValidationBudgetState


__all__ = [
    "AUTHORITY_KEY",
    "EVENT_STARTED",
    "EVENT_TERMINAL",
    "LEGACY_RECONCILED_VALIDATION_DEBIT",
    "MAX_RUNS_PER_CANDIDATE",
    "MAX_VALIDATION_EVALUATIONS",
    "STARTED_BODY_FIELDS",
    "STARTED_INVOCATION",
    "TERMINAL_BODY_FIELDS",
    "StartedEventCommand",
    "StoredValidationEvent",
    "TerminalEventCommand",
    "ValidationBudgetState",
    "VerifiedValidationBudgetState",
]
