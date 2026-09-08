"""Execution boundary for the durable S4 validation-budget authority.

The candidate execution path must obtain its budget and retry history from the
verified PostgreSQL ledger.  The historical JSONL journal and reconciliation
document remain audit material only; they are deliberately not dependencies of
this adapter.

This module is a control-plane adapter.  It does not score a dataset or call a
model.  A caller supplies a callback for that future work, and the adapter
releases it only after the PostgreSQL STARTED event has committed and been
read back successfully.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.s4_experiment import (
    CandidateExecutionGateRequest,
    CandidateExecutionGateResult,
    check_candidate_execution_gate,
)
from backend.app.s4_validation_budget import (
    S4ValidationBudgetRepository,
    StartedEventCommand,
    TerminalEventCommand,
    ValidationBudgetError,
    ValidationBudgetState,
)
from backend.app.s4_validation_budget.schemas import EVENT_STARTED, MAX_VALIDATION_EVALUATIONS

CANDIDATE_01_ID = "01_parameter_calibration"
CANDIDATE_01_RERUN_FORBIDDEN = "CANDIDATE_01_RERUN_FORBIDDEN"
CANDIDATE_EXECUTION_NOT_AUTHORIZED = "CANDIDATE_EXECUTION_NOT_AUTHORIZED"
POSTGRES_AUTHORITY_UNAVAILABLE = "POSTGRES_AUTHORITY_UNAVAILABLE"
STARTED_READBACK_MISMATCH = "VALIDATION_STARTED_READBACK_MISMATCH"
TERMINAL_APPEND_FAILED = "VALIDATION_TERMINAL_APPEND_FAILED"

ExecutionStatus = Literal["COMPLETED", "FAILED", "BLOCKED"]
type ScorerCallback = Callable[[], object | Awaitable[object]]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class DurableCandidatePreflight:
    """Verified state and gate context prepared for one candidate invocation."""

    status: Literal["ALLOWED", "BLOCKED"]
    blocker: str | None
    reason_code: str | None
    state: ValidationBudgetState | None
    gate_request: CandidateExecutionGateRequest | None
    gate_result: CandidateExecutionGateResult | None
    candidate_actual_run_count: int
    global_actual_evaluation_count: int
    prior_evaluation_ids: tuple[str, ...]

    @property
    def allowed(self) -> bool:
        return self.status == "ALLOWED"


@dataclass(frozen=True, slots=True)
class DurableCandidateExecutionResult:
    """Sanitized outcome of the durable execution boundary."""

    status: ExecutionStatus
    blocker: str | None
    reason_code: str | None
    preflight: DurableCandidatePreflight
    started_persisted: bool
    terminal_persisted: bool
    scorer_called: bool
    started_event_id: str | None
    state_after_start: ValidationBudgetState | None
    state_after_terminal: ValidationBudgetState | None


def _blocked_preflight(
    *,
    blocker: str,
    state: ValidationBudgetState | None = None,
    gate_request: CandidateExecutionGateRequest | None = None,
    gate_result: CandidateExecutionGateResult | None = None,
    candidate_actual_run_count: int = 0,
    global_actual_evaluation_count: int = 0,
    prior_evaluation_ids: tuple[str, ...] = (),
) -> DurableCandidatePreflight:
    return DurableCandidatePreflight(
        status="BLOCKED",
        blocker=blocker,
        reason_code=blocker,
        state=state,
        gate_request=gate_request,
        gate_result=gate_result,
        candidate_actual_run_count=candidate_actual_run_count,
        global_actual_evaluation_count=global_actual_evaluation_count,
        prior_evaluation_ids=prior_evaluation_ids,
    )


class S4CandidateExecutionAuthority:
    """Bind S4-B gate decisions to the PostgreSQL budget/event repository."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        repository: S4ValidationBudgetRepository | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repository = repository or S4ValidationBudgetRepository(session)
        self._clock = clock

    async def _verified_state(self) -> ValidationBudgetState:
        return await self._repository.load_verified_state()

    @staticmethod
    def _bind_request(
        request: CandidateExecutionGateRequest,
        state: ValidationBudgetState,
    ) -> tuple[CandidateExecutionGateRequest, int, tuple[str, ...]]:
        started_events = tuple(event for event in state.events if event.event_type == EVENT_STARTED)
        prior_ids = tuple(event.evaluation_id for event in started_events)
        candidate_count = sum(
            event.candidate_id == request.candidate_id for event in started_events
        )
        bound = replace(
            request,
            candidate_actual_run_count=candidate_count,
            candidate_run_ordinal=candidate_count + 1,
            # This is the effective count, including the frozen legacy debit.
            global_actual_evaluation_count=state.effective_consumed,
            prior_evaluation_ids=prior_ids,
        )
        return bound, candidate_count, prior_ids

    async def preflight(self, request: CandidateExecutionGateRequest) -> DurableCandidatePreflight:
        """Load verified DB state and run the shared S4-B gate.

        No JSONL or repository evidence fallback is attempted.  C01 is a
        permanently blocked historical lane until a separate owner decision
        explicitly changes that policy.
        """

        try:
            state = await self._verified_state()
        except ValidationBudgetError as exc:
            return _blocked_preflight(blocker=exc.reason_code)
        except Exception:
            return _blocked_preflight(blocker=POSTGRES_AUTHORITY_UNAVAILABLE)

        bound_request, candidate_count, prior_ids = self._bind_request(request, state)
        if state.effective_consumed >= MAX_VALIDATION_EVALUATIONS:
            return _blocked_preflight(
                blocker="GLOBAL_VALIDATION_BUDGET_EXHAUSTED",
                state=state,
                gate_request=bound_request,
                candidate_actual_run_count=candidate_count,
                global_actual_evaluation_count=state.effective_consumed,
                prior_evaluation_ids=prior_ids,
            )
        if request.candidate_id == CANDIDATE_01_ID:
            return _blocked_preflight(
                blocker=CANDIDATE_01_RERUN_FORBIDDEN,
                state=state,
                gate_request=bound_request,
                candidate_actual_run_count=candidate_count,
                global_actual_evaluation_count=state.effective_consumed,
                prior_evaluation_ids=prior_ids,
            )

        gate_result = check_candidate_execution_gate(bound_request)
        if not gate_result.allowed:
            reason = (
                gate_result.reason_codes[0]
                if gate_result.reason_codes
                else "EXECUTION_GATE_BLOCKED"
            )
            return _blocked_preflight(
                blocker=reason,
                state=state,
                gate_request=bound_request,
                gate_result=gate_result,
                candidate_actual_run_count=candidate_count,
                global_actual_evaluation_count=state.effective_consumed,
                prior_evaluation_ids=prior_ids,
            )
        return DurableCandidatePreflight(
            status="ALLOWED",
            blocker=None,
            reason_code=None,
            state=state,
            gate_request=bound_request,
            gate_result=gate_result,
            candidate_actual_run_count=candidate_count,
            global_actual_evaluation_count=state.effective_consumed,
            prior_evaluation_ids=prior_ids,
        )

    @staticmethod
    def _started_command(
        *,
        preflight: DurableCandidatePreflight,
        started_at: datetime,
        trigger_source: str,
    ) -> StartedEventCommand:
        state = preflight.state
        request = preflight.gate_request
        if state is None or request is None:
            raise ValueError("durable preflight state is missing")
        return StartedEventCommand(
            evaluation_id=request.evaluation_id or "",
            experiment_plan_version=request.experiment_plan_version,
            candidate_id=request.candidate_id,
            candidate_run_ordinal=request.candidate_run_ordinal,
            # Legacy debit affects the gate count, not the canonical event ordinal.
            global_evaluation_ordinal=state.accepted_last_global_evaluation_ordinal + 1,
            invocation_type=request.invocation_type,
            trigger_source=trigger_source,
            started_at=started_at,
            dataset_hash=request.train_dataset_identity,
            validation_split_hash=request.validation_dataset_identity,
            code_commit_sha=request.code_commit_sha or "",
            parameter_manifest_hash=request.parameter_manifest_hash or "",
            random_seed=request.random_seed,
            retry_of_evaluation_id=request.retry_of_evaluation_id,
            expected_authority_version=state.authority_version,
            expected_event_count=state.accepted_event_count,
            expected_started_count=state.accepted_started_count,
            expected_head_event_hash=state.accepted_head_event_hash,
            expected_last_global_evaluation_ordinal=state.accepted_last_global_evaluation_ordinal,
        )

    async def execute(
        self,
        request: CandidateExecutionGateRequest,
        *,
        scorer: ScorerCallback,
        execution_authorized: bool,
        trigger_source: str,
        started_at: datetime | None = None,
    ) -> DurableCandidateExecutionResult:
        """Run the durable control-plane sequence around a supplied callback.

        ``execution_authorized`` is explicit so this adapter cannot silently
        turn registration or a preflight PASS into permission to run a model.
        The current task passes synthetic callbacks only.
        """

        preflight = await self.preflight(request)
        return await self.execute_preflight(
            preflight,
            scorer=scorer,
            execution_authorized=execution_authorized,
            trigger_source=trigger_source,
            started_at=started_at,
        )

    async def execute_preflight(
        self,
        preflight: DurableCandidatePreflight,
        *,
        scorer: ScorerCallback,
        execution_authorized: bool,
        trigger_source: str,
        started_at: datetime | None = None,
    ) -> DurableCandidateExecutionResult:
        """Execute a previously prepared context using its CAS expectations.

        This explicit seam lets callers surface a stale preflight as a durable
        CAS conflict instead of silently rebuilding it and retrying the same
        evaluation identity.
        """

        if not preflight.allowed:
            return DurableCandidateExecutionResult(
                status="BLOCKED",
                blocker=preflight.blocker,
                reason_code=preflight.reason_code,
                preflight=preflight,
                started_persisted=False,
                terminal_persisted=False,
                scorer_called=False,
                started_event_id=None,
                state_after_start=None,
                state_after_terminal=None,
            )
        if not execution_authorized:
            blocked = _blocked_preflight(
                blocker=CANDIDATE_EXECUTION_NOT_AUTHORIZED,
                state=preflight.state,
                gate_request=preflight.gate_request,
                gate_result=preflight.gate_result,
                candidate_actual_run_count=preflight.candidate_actual_run_count,
                global_actual_evaluation_count=preflight.global_actual_evaluation_count,
                prior_evaluation_ids=preflight.prior_evaluation_ids,
            )
            return DurableCandidateExecutionResult(
                status="BLOCKED",
                blocker=blocked.blocker,
                reason_code=blocked.reason_code,
                preflight=blocked,
                started_persisted=False,
                terminal_persisted=False,
                scorer_called=False,
                started_event_id=None,
                state_after_start=None,
                state_after_terminal=None,
            )

        command = self._started_command(
            preflight=preflight,
            started_at=started_at or self._clock(),
            trigger_source=trigger_source,
        )
        try:
            started = await self._repository.append_started(command)
        except ValidationBudgetError as exc:
            return DurableCandidateExecutionResult(
                status="BLOCKED",
                blocker=exc.reason_code,
                reason_code=exc.reason_code,
                preflight=preflight,
                started_persisted=False,
                terminal_persisted=False,
                scorer_called=False,
                started_event_id=None,
                state_after_start=None,
                state_after_terminal=None,
            )
        except Exception:
            return DurableCandidateExecutionResult(
                status="BLOCKED",
                blocker=POSTGRES_AUTHORITY_UNAVAILABLE,
                reason_code=POSTGRES_AUTHORITY_UNAVAILABLE,
                preflight=preflight,
                started_persisted=False,
                terminal_persisted=False,
                scorer_called=False,
                started_event_id=None,
                state_after_start=None,
                state_after_terminal=None,
            )

        try:
            state_after_start = await self._verified_state()
            committed_ids = tuple(
                event.evaluation_id
                for event in state_after_start.events
                if event.event_type == EVENT_STARTED
            )
            if (
                committed_ids.count(started.evaluation_id) != 1
                or state_after_start.accepted_started_count
                != preflight.state.accepted_started_count + 1  # type: ignore[union-attr]
            ):
                return DurableCandidateExecutionResult(
                    status="BLOCKED",
                    blocker=STARTED_READBACK_MISMATCH,
                    reason_code=STARTED_READBACK_MISMATCH,
                    preflight=preflight,
                    started_persisted=True,
                    terminal_persisted=False,
                    scorer_called=False,
                    started_event_id=started.evaluation_id,
                    state_after_start=state_after_start,
                    state_after_terminal=None,
                )
        except ValidationBudgetError as exc:
            return DurableCandidateExecutionResult(
                status="BLOCKED",
                blocker=exc.reason_code,
                reason_code=exc.reason_code,
                preflight=preflight,
                started_persisted=True,
                terminal_persisted=False,
                scorer_called=False,
                started_event_id=started.evaluation_id,
                state_after_start=None,
                state_after_terminal=None,
            )
        except Exception:
            return DurableCandidateExecutionResult(
                status="BLOCKED",
                blocker=POSTGRES_AUTHORITY_UNAVAILABLE,
                reason_code=POSTGRES_AUTHORITY_UNAVAILABLE,
                preflight=preflight,
                started_persisted=True,
                terminal_persisted=False,
                scorer_called=False,
                started_event_id=started.evaluation_id,
                state_after_start=None,
                state_after_terminal=None,
            )

        try:
            callback_result = scorer()
            if inspect.isawaitable(callback_result):
                callback_result = await callback_result
            metric_result_status = (
                callback_result
                if isinstance(callback_result, str) and callback_result
                else "COMPUTED"
            )
            execution_status: ExecutionStatus = "COMPLETED"
        except Exception:
            metric_result_status = "SCORER_FAILED"
            execution_status = "FAILED"

        try:
            await self._repository.append_terminal(
                TerminalEventCommand(
                    evaluation_id=started.evaluation_id,
                    candidate_id=command.candidate_id,
                    finished_at=self._clock(),
                    execution_status=execution_status,
                    metric_result_status=metric_result_status,
                )
            )
            state_after_terminal = await self._verified_state()
        except ValidationBudgetError as exc:
            return DurableCandidateExecutionResult(
                status="BLOCKED",
                blocker=exc.reason_code,
                reason_code=exc.reason_code,
                preflight=preflight,
                started_persisted=True,
                terminal_persisted=False,
                scorer_called=True,
                started_event_id=started.evaluation_id,
                state_after_start=state_after_start,
                state_after_terminal=None,
            )
        except Exception:
            return DurableCandidateExecutionResult(
                status="BLOCKED",
                blocker=TERMINAL_APPEND_FAILED,
                reason_code=TERMINAL_APPEND_FAILED,
                preflight=preflight,
                started_persisted=True,
                terminal_persisted=False,
                scorer_called=True,
                started_event_id=started.evaluation_id,
                state_after_start=state_after_start,
                state_after_terminal=None,
            )

        return DurableCandidateExecutionResult(
            status=execution_status,
            blocker=None,
            reason_code=None,
            preflight=preflight,
            started_persisted=True,
            terminal_persisted=True,
            scorer_called=True,
            started_event_id=started.evaluation_id,
            state_after_start=state_after_start,
            state_after_terminal=state_after_terminal,
        )


__all__ = [
    "CANDIDATE_01_ID",
    "CANDIDATE_01_RERUN_FORBIDDEN",
    "CANDIDATE_EXECUTION_NOT_AUTHORIZED",
    "DurableCandidateExecutionResult",
    "DurableCandidatePreflight",
    "POSTGRES_AUTHORITY_UNAVAILABLE",
    "S4CandidateExecutionAuthority",
    "STARTED_READBACK_MISMATCH",
    "TERMINAL_APPEND_FAILED",
]
