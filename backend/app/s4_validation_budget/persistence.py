"""PostgreSQL-backed S4 validation-budget persistence primitive.

The repository owns one transaction at a time and never writes the legacy
JSONL journal.  The event payload is canonical; typed columns are checked
projections used only for constraints and readback validation.
"""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.s4_validation_budget import (
    S4ValidationBudgetAuthority,
    S4ValidationEvent,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps
from backend.app.s4_validation_budget.canonical import (
    GENESIS_EVENT_HASH,
    canonical_event_body,
    validation_event_hash,
)
from backend.app.s4_validation_budget.errors import ValidationBudgetBlocked
from backend.app.s4_validation_budget.schemas import (
    AUTHORITY_KEY,
    EVENT_STARTED,
    EVENT_TERMINAL,
    LEGACY_RECONCILED_VALIDATION_DEBIT,
    MAX_RUNS_PER_CANDIDATE,
    MAX_VALIDATION_EVALUATIONS,
    STARTED_BODY_FIELDS,
    STARTED_INVOCATION,
    TERMINAL_BODY_FIELDS,
    StartedEventCommand,
    StoredValidationEvent,
    TerminalEventCommand,
    ValidationBudgetState,
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_TERMINAL_STATUSES = frozenset(
    {"COMPLETED", "FAILED", "ABORTED", "CANCELLED", "TIMEOUT", "BLOCKED"}
)

BeforeHeadAdvanceHook = Callable[[AsyncSession], Awaitable[None] | None]


def _blocked(reason_code: str) -> ValidationBudgetBlocked:
    return ValidationBudgetBlocked(reason_code)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _canonical_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    # The existing canonical serializer is the repository authority for the
    # exact timestamp spelling stored in event_payload.
    return str(json.loads(canonical_json_dumps(_aware_utc(value))))


def _same_timestamp(typed: datetime | None, body_value: object) -> bool:
    if typed is None:
        return body_value is None
    return _canonical_datetime(typed) == body_value


def _valid_sha(value: object) -> bool:
    return isinstance(value, str) and _SHA256_PATTERN.fullmatch(value) is not None


def _nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _model_event(row: S4ValidationEvent) -> StoredValidationEvent:
    payload = row.event_payload
    if not isinstance(payload, dict):
        raise _blocked("VALIDATION_EVENT_PROJECTION_MISMATCH")
    created_at = row.created_at or _utc_now()
    return StoredValidationEvent(
        authority_key=row.authority_key,
        event_sequence=int(row.event_sequence),
        event_type=row.event_type,
        evaluation_id=row.evaluation_id,
        candidate_id=row.candidate_id,
        event_payload=dict(payload),
        previous_event_hash=row.previous_event_hash,
        event_hash=row.event_hash,
        created_at=_aware_utc(created_at),
        candidate_run_ordinal=(
            None if row.candidate_run_ordinal is None else int(row.candidate_run_ordinal)
        ),
        global_evaluation_ordinal=(
            None if row.global_evaluation_ordinal is None else int(row.global_evaluation_ordinal)
        ),
        invocation_type=row.invocation_type,
        counted_toward_budget=row.counted_toward_budget,
        budget_count_reason=row.budget_count_reason,
        finished_at=(None if row.finished_at is None else _aware_utc(row.finished_at)),
        execution_status=row.execution_status,
        metric_result_status=row.metric_result_status,
    )


def _authority_values(row: S4ValidationBudgetAuthority) -> tuple[int, int, int, str, int]:
    return (
        int(row.authority_version),
        int(row.accepted_event_count),
        int(row.accepted_started_count),
        row.accepted_head_event_hash,
        int(row.accepted_last_global_evaluation_ordinal),
    )


def _validate_authority_row(row: S4ValidationBudgetAuthority) -> None:
    version, event_count, started_count, head_hash, last_ordinal = _authority_values(row)
    if row.authority_key != AUTHORITY_KEY:
        raise _blocked("VALIDATION_BUDGET_AUTHORITY_INVALID")
    if (
        version < 0
        or event_count < 0
        or started_count < 0
        or started_count > event_count
        or last_ordinal < 0
        or row.legacy_reconciled_validation_debit != LEGACY_RECONCILED_VALIDATION_DEBIT
        or not _valid_sha(head_hash)
        or row.legacy_reconciled_validation_debit + started_count > MAX_VALIDATION_EVALUATIONS
    ):
        raise _blocked("VALIDATION_BUDGET_AUTHORITY_INVALID")


def _projection_matches(row: S4ValidationEvent, payload: Mapping[str, Any]) -> None:
    if row.evaluation_id != payload.get("evaluation_id"):
        raise _blocked("VALIDATION_EVENT_PROJECTION_MISMATCH")
    if row.candidate_id != payload.get("candidate_id"):
        raise _blocked("VALIDATION_EVENT_PROJECTION_MISMATCH")

    if row.event_type == EVENT_STARTED:
        for field in (
            "candidate_run_ordinal",
            "global_evaluation_ordinal",
            "invocation_type",
            "counted_toward_budget",
            "budget_count_reason",
        ):
            if getattr(row, field) != payload.get(field):
                raise _blocked("VALIDATION_EVENT_PROJECTION_MISMATCH")
        if (
            not isinstance(payload.get("candidate_run_ordinal"), int)
            or isinstance(payload.get("candidate_run_ordinal"), bool)
            or not 1 <= payload["candidate_run_ordinal"] <= MAX_RUNS_PER_CANDIDATE
            or not isinstance(payload.get("global_evaluation_ordinal"), int)
            or isinstance(payload.get("global_evaluation_ordinal"), bool)
            or payload["global_evaluation_ordinal"] < 1
            or payload.get("counted_toward_budget") is not True
            or payload.get("budget_count_reason") != STARTED_INVOCATION
        ):
            raise _blocked("VALIDATION_EVENT_PROJECTION_MISMATCH")
        if set(payload) < set(STARTED_BODY_FIELDS):
            raise _blocked("VALIDATION_EVENT_PROJECTION_MISMATCH")
        return

    if row.event_type == EVENT_TERMINAL:
        for field in (
            "finished_at",
            "execution_status",
            "metric_result_status",
            "counted_toward_budget",
        ):
            value = getattr(row, field)
            if field == "finished_at":
                matches = _same_timestamp(value, payload.get(field))
            else:
                matches = value == payload.get(field)
            if not matches:
                raise _blocked("VALIDATION_EVENT_PROJECTION_MISMATCH")
        if set(payload) < set(TERMINAL_BODY_FIELDS):
            raise _blocked("VALIDATION_EVENT_PROJECTION_MISMATCH")
        return

    raise _blocked("VALIDATION_EVENT_PROJECTION_MISMATCH")


def _verify_event_projection_and_hash(
    row: S4ValidationEvent,
    *,
    expected_sequence: int,
    expected_previous_hash: str,
) -> StoredValidationEvent:
    event = _model_event(row)
    if event.event_sequence != expected_sequence:
        raise _blocked("VALIDATION_LEDGER_EVENT_COUNT_MISMATCH")
    if event.previous_event_hash != expected_previous_hash:
        raise _blocked("VALIDATION_EVENT_HASH_CHAIN_MISMATCH")
    try:
        payload = canonical_event_body(event.event_payload)
    except (TypeError, ValueError):
        raise _blocked("VALIDATION_EVENT_HASH_CHAIN_MISMATCH") from None
    _projection_matches(row, payload)
    if (
        validation_event_hash(
            event_type=event.event_type,
            event_payload=payload,
            previous_event_hash=event.previous_event_hash,
        )
        != event.event_hash
    ):
        raise _blocked("VALIDATION_EVENT_HASH_CHAIN_MISMATCH")
    return event


def _verify_events(
    authority: S4ValidationBudgetAuthority,
    rows: Sequence[S4ValidationEvent],
) -> tuple[StoredValidationEvent, ...]:
    expected_count = int(authority.accepted_event_count)
    actual_count = len(rows)
    if actual_count < expected_count:
        raise _blocked("VALIDATION_LEDGER_TAIL_TRUNCATION_DETECTED")
    if actual_count != expected_count:
        raise _blocked("VALIDATION_LEDGER_EVENT_COUNT_MISMATCH")

    events: list[StoredValidationEvent] = []
    previous = GENESIS_EVENT_HASH
    seen_pairs: set[tuple[str, str]] = set()
    seen_hashes: set[str] = set()
    for expected_sequence, row in enumerate(rows, start=1):
        event = _verify_event_projection_and_hash(
            row,
            expected_sequence=expected_sequence,
            expected_previous_hash=previous,
        )
        pair = (event.evaluation_id, event.event_type)
        if pair in seen_pairs or event.event_hash in seen_hashes:
            raise _blocked("VALIDATION_EVENT_HASH_CHAIN_MISMATCH")
        seen_pairs.add(pair)
        seen_hashes.add(event.event_hash)
        events.append(event)
        previous = event.event_hash

    started_by_evaluation: dict[str, StoredValidationEvent] = {}
    terminal_by_evaluation: dict[str, StoredValidationEvent] = {}
    for event in events:
        if event.event_type == EVENT_STARTED:
            if event.evaluation_id in started_by_evaluation:
                raise _blocked("VALIDATION_EVENT_HASH_CHAIN_MISMATCH")
            started_by_evaluation[event.evaluation_id] = event
        elif event.event_type == EVENT_TERMINAL:
            if event.evaluation_id in terminal_by_evaluation:
                raise _blocked("VALIDATION_DUPLICATE_TERMINAL")
            terminal_by_evaluation[event.evaluation_id] = event
        else:
            raise _blocked("VALIDATION_EVENT_PROJECTION_MISMATCH")

    for evaluation_id, terminal in terminal_by_evaluation.items():
        started = started_by_evaluation.get(evaluation_id)
        if started is None:
            raise _blocked("VALIDATION_TERMINAL_WITHOUT_STARTED")
        if terminal.candidate_id != started.candidate_id:
            raise _blocked("VALIDATION_TERMINAL_CANDIDATE_MISMATCH")

    started_count = len(started_by_evaluation)
    if started_count != int(authority.accepted_started_count):
        raise _blocked("VALIDATION_LEDGER_STARTED_COUNT_MISMATCH")
    max_global = max(
        (event.global_evaluation_ordinal or 0 for event in started_by_evaluation.values()),
        default=0,
    )
    if max_global != int(authority.accepted_last_global_evaluation_ordinal):
        raise _blocked("VALIDATION_GLOBAL_ORDINAL_REGRESSION")
    if events and events[-1].event_hash != authority.accepted_head_event_hash:
        raise _blocked("VALIDATION_LEDGER_HEAD_MISMATCH")
    if not events and authority.accepted_head_event_hash != GENESIS_EVENT_HASH:
        raise _blocked("VALIDATION_LEDGER_HEAD_MISMATCH")
    return tuple(events)


def _state_from_verified_rows(
    authority: S4ValidationBudgetAuthority,
    events: tuple[StoredValidationEvent, ...],
) -> ValidationBudgetState:
    _validate_authority_row(authority)
    if int(authority.authority_version) != int(authority.accepted_event_count):
        raise _blocked("VALIDATION_BUDGET_AUTHORITY_INVALID")
    effective = int(authority.legacy_reconciled_validation_debit) + int(
        authority.accepted_started_count
    )
    return ValidationBudgetState(
        authority_key=authority.authority_key,
        authority_version=int(authority.authority_version),
        accepted_event_count=int(authority.accepted_event_count),
        accepted_started_count=int(authority.accepted_started_count),
        accepted_head_event_hash=authority.accepted_head_event_hash,
        accepted_last_global_evaluation_ordinal=int(
            authority.accepted_last_global_evaluation_ordinal
        ),
        legacy_reconciled_validation_debit=int(authority.legacy_reconciled_validation_debit),
        effective_consumed=effective,
        remaining=MAX_VALIDATION_EVALUATIONS - effective,
        events=events,
    )


def _candidate_started_count(events: Sequence[StoredValidationEvent], candidate_id: str) -> int:
    return sum(
        event.event_type == EVENT_STARTED and event.candidate_id == candidate_id for event in events
    )


def _validate_started_command(command: StartedEventCommand) -> None:
    for value in (
        command.evaluation_id,
        command.experiment_plan_version,
        command.candidate_id,
        command.invocation_type,
        command.trigger_source,
        command.dataset_hash,
        command.validation_split_hash,
        command.code_commit_sha,
        command.parameter_manifest_hash,
    ):
        if not _nonempty_text(value):
            raise _blocked("VALIDATION_BUDGET_AUTHORITY_INVALID")
    if (
        not isinstance(command.candidate_run_ordinal, int)
        or isinstance(command.candidate_run_ordinal, bool)
        or not isinstance(command.global_evaluation_ordinal, int)
        or isinstance(command.global_evaluation_ordinal, bool)
        or command.candidate_run_ordinal < 1
        or command.global_evaluation_ordinal < 1
    ):
        raise _blocked("VALIDATION_CANDIDATE_RUN_ORDINAL_INVALID")
    if command.counted_toward_budget is not True:
        raise _blocked("VALIDATION_EVENT_PROJECTION_MISMATCH")
    if command.budget_count_reason != STARTED_INVOCATION:
        raise _blocked("VALIDATION_EVENT_PROJECTION_MISMATCH")
    try:
        canonical_event_body(command.body())
    except (TypeError, ValueError):
        raise _blocked("VALIDATION_EVENT_PROJECTION_MISMATCH") from None


def _validate_terminal_command(command: TerminalEventCommand) -> None:
    if not _nonempty_text(command.evaluation_id) or not _nonempty_text(command.candidate_id):
        raise _blocked("VALIDATION_TERMINAL_WITHOUT_STARTED")
    if command.execution_status not in _TERMINAL_STATUSES:
        raise _blocked("VALIDATION_BUDGET_AUTHORITY_INVALID")
    try:
        canonical_event_body(command.body())
    except (TypeError, ValueError):
        raise _blocked("VALIDATION_EVENT_PROJECTION_MISMATCH") from None


class S4ValidationBudgetRepository:
    """Append-only validation-budget repository with a durable monotonic head."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        clock: Callable[[], datetime] = _utc_now,
        before_head_advance_hook: BeforeHeadAdvanceHook | None = None,
    ) -> None:
        self._session = session
        self._clock = clock
        self._before_head_advance_hook = before_head_advance_hook

    async def _read_verified_in_transaction(self) -> ValidationBudgetState:
        authority = await self._session.scalar(
            select(S4ValidationBudgetAuthority).where(
                S4ValidationBudgetAuthority.authority_key == AUTHORITY_KEY
            )
        )
        if authority is None:
            raise _blocked("VALIDATION_BUDGET_AUTHORITY_MISSING")
        rows = list(
            (
                await self._session.scalars(
                    select(S4ValidationEvent)
                    .where(S4ValidationEvent.authority_key == AUTHORITY_KEY)
                    .order_by(S4ValidationEvent.event_sequence)
                )
            ).all()
        )
        events = _verify_events(authority, rows)
        return _state_from_verified_rows(authority, events)

    async def load_verified_state(self) -> ValidationBudgetState:
        """Verify the accepted head, complete event chain, and projections."""

        if self._session.in_transaction():
            return await self._read_verified_in_transaction()
        async with self._session.begin():
            return await self._read_verified_in_transaction()

    async def _locked_state(self) -> tuple[S4ValidationBudgetAuthority, ValidationBudgetState]:
        authority = await self._session.scalar(
            select(S4ValidationBudgetAuthority)
            .where(S4ValidationBudgetAuthority.authority_key == AUTHORITY_KEY)
            .with_for_update()
        )
        if authority is None:
            raise _blocked("VALIDATION_BUDGET_AUTHORITY_MISSING")
        rows = list(
            (
                await self._session.scalars(
                    select(S4ValidationEvent)
                    .where(S4ValidationEvent.authority_key == AUTHORITY_KEY)
                    .order_by(S4ValidationEvent.event_sequence)
                )
            ).all()
        )
        events = _verify_events(authority, rows)
        return authority, _state_from_verified_rows(authority, events)

    async def _call_head_hook(self) -> None:
        if self._before_head_advance_hook is None:
            return
        result = self._before_head_advance_hook(self._session)
        if inspect.isawaitable(result):
            await result

    async def _advance_head(
        self,
        *,
        state: ValidationBudgetState,
        event: S4ValidationEvent,
        started_delta: int,
        last_global_ordinal: int,
    ) -> None:
        await self._call_head_hook()
        expected = (
            state.authority_version,
            state.accepted_event_count,
            state.accepted_started_count,
            state.accepted_head_event_hash,
            state.accepted_last_global_evaluation_ordinal,
        )
        values = {
            "authority_version": state.authority_version + 1,
            "accepted_event_count": state.accepted_event_count + 1,
            "accepted_started_count": state.accepted_started_count + started_delta,
            "accepted_head_event_hash": event.event_hash,
            "accepted_last_global_evaluation_ordinal": last_global_ordinal,
            "updated_at": _aware_utc(self._clock()),
        }
        result = await self._session.execute(
            update(S4ValidationBudgetAuthority)
            .where(
                S4ValidationBudgetAuthority.authority_key == AUTHORITY_KEY,
                S4ValidationBudgetAuthority.authority_version == expected[0],
                S4ValidationBudgetAuthority.accepted_event_count == expected[1],
                S4ValidationBudgetAuthority.accepted_started_count == expected[2],
                S4ValidationBudgetAuthority.accepted_head_event_hash == expected[3],
                S4ValidationBudgetAuthority.accepted_last_global_evaluation_ordinal == expected[4],
            )
            .values(**values)
        )
        if cast(CursorResult[Any], result).rowcount != 1:
            raise _blocked("VALIDATION_BUDGET_AUTHORITY_CAS_CONFLICT")

    async def append_started(
        self,
        command: StartedEventCommand | Mapping[str, Any],
    ) -> StoredValidationEvent:
        """Atomically append STARTED and advance the accepted authority head."""

        if not isinstance(command, StartedEventCommand):
            command = StartedEventCommand.from_mapping(command)
        _validate_started_command(command)
        try:
            async with self._session.begin():
                authority, state = await self._locked_state()
                if command.expected_authority_version is not None and (
                    command.expected_authority_version != state.authority_version
                    or command.expected_event_count != state.accepted_event_count
                    or command.expected_started_count != state.accepted_started_count
                    or command.expected_head_event_hash != state.accepted_head_event_hash
                    or command.expected_last_global_evaluation_ordinal
                    != state.accepted_last_global_evaluation_ordinal
                ):
                    raise _blocked("VALIDATION_BUDGET_AUTHORITY_CAS_CONFLICT")
                if state.effective_consumed >= MAX_VALIDATION_EVALUATIONS:
                    raise _blocked("VALIDATION_BUDGET_EXHAUSTED")
                candidate_count = _candidate_started_count(state.events, command.candidate_id)
                if candidate_count >= MAX_RUNS_PER_CANDIDATE:
                    raise _blocked("VALIDATION_CANDIDATE_RUN_LIMIT_EXCEEDED")
                expected_candidate_ordinal = candidate_count + 1
                if command.candidate_run_ordinal != expected_candidate_ordinal:
                    if command.candidate_run_ordinal <= candidate_count:
                        raise _blocked("VALIDATION_CANDIDATE_RUN_ORDINAL_DUPLICATE")
                    raise _blocked("VALIDATION_CANDIDATE_RUN_ORDINAL_INVALID")
                expected_global_ordinal = state.accepted_last_global_evaluation_ordinal + 1
                if command.global_evaluation_ordinal != expected_global_ordinal:
                    if command.global_evaluation_ordinal <= (
                        state.accepted_last_global_evaluation_ordinal
                    ):
                        raise _blocked("VALIDATION_BUDGET_AUTHORITY_CAS_CONFLICT")
                    raise _blocked("VALIDATION_GLOBAL_ORDINAL_REGRESSION")
                if any(event.evaluation_id == command.evaluation_id for event in state.events):
                    raise _blocked("VALIDATION_EVALUATION_ID_REUSE")

                payload = canonical_event_body(command.body())
                sequence = state.accepted_event_count + 1
                event_hash = validation_event_hash(
                    event_type=EVENT_STARTED,
                    event_payload=payload,
                    previous_event_hash=state.accepted_head_event_hash,
                )
                event_row = S4ValidationEvent(
                    authority_key=AUTHORITY_KEY,
                    event_sequence=sequence,
                    event_type=EVENT_STARTED,
                    evaluation_id=payload["evaluation_id"],
                    candidate_id=payload["candidate_id"],
                    candidate_run_ordinal=payload["candidate_run_ordinal"],
                    global_evaluation_ordinal=payload["global_evaluation_ordinal"],
                    invocation_type=payload["invocation_type"],
                    counted_toward_budget=payload["counted_toward_budget"],
                    budget_count_reason=payload["budget_count_reason"],
                    event_payload=payload,
                    previous_event_hash=state.accepted_head_event_hash,
                    event_hash=event_hash,
                    created_at=_aware_utc(self._clock()),
                )
                _projection_matches(event_row, payload)
                self._session.add(event_row)
                await self._session.flush()
                await self._advance_head(
                    state=state,
                    event=event_row,
                    started_delta=1,
                    last_global_ordinal=command.global_evaluation_ordinal,
                )
                await self._session.flush()
                return _model_event(event_row)
        except IntegrityError as exc:
            raise _blocked("VALIDATION_CANDIDATE_RUN_ORDINAL_DUPLICATE") from exc

    async def append_terminal(
        self,
        command: TerminalEventCommand | Mapping[str, Any],
    ) -> StoredValidationEvent:
        """Append an immutable terminal event without consuming budget."""

        if not isinstance(command, TerminalEventCommand):
            command = TerminalEventCommand.from_mapping(command)
        _validate_terminal_command(command)
        try:
            async with self._session.begin():
                _, state = await self._locked_state()
                started = next(
                    (
                        event
                        for event in state.events
                        if event.event_type == EVENT_STARTED
                        and event.evaluation_id == command.evaluation_id
                    ),
                    None,
                )
                if started is None:
                    raise _blocked("VALIDATION_TERMINAL_WITHOUT_STARTED")
                if any(
                    event.event_type == EVENT_TERMINAL
                    and event.evaluation_id == command.evaluation_id
                    for event in state.events
                ):
                    raise _blocked("VALIDATION_DUPLICATE_TERMINAL")
                if started.candidate_id != command.candidate_id:
                    raise _blocked("VALIDATION_TERMINAL_CANDIDATE_MISMATCH")

                payload = canonical_event_body(command.body())
                event_hash = validation_event_hash(
                    event_type=EVENT_TERMINAL,
                    event_payload=payload,
                    previous_event_hash=state.accepted_head_event_hash,
                )
                event_row = S4ValidationEvent(
                    authority_key=AUTHORITY_KEY,
                    event_sequence=state.accepted_event_count + 1,
                    event_type=EVENT_TERMINAL,
                    evaluation_id=payload["evaluation_id"],
                    candidate_id=payload["candidate_id"],
                    finished_at=_aware_utc(command.finished_at),
                    execution_status=payload["execution_status"],
                    metric_result_status=payload["metric_result_status"],
                    counted_toward_budget=payload["counted_toward_budget"],
                    event_payload=payload,
                    previous_event_hash=state.accepted_head_event_hash,
                    event_hash=event_hash,
                    created_at=_aware_utc(self._clock()),
                )
                _projection_matches(event_row, payload)
                self._session.add(event_row)
                await self._session.flush()
                await self._advance_head(
                    state=state,
                    event=event_row,
                    started_delta=0,
                    last_global_ordinal=state.accepted_last_global_evaluation_ordinal,
                )
                await self._session.flush()
                return _model_event(event_row)
        except IntegrityError as exc:
            raise _blocked("VALIDATION_DUPLICATE_TERMINAL") from exc


__all__ = ["S4ValidationBudgetRepository"]
