"""Replay Task 10 binding contract (§11 — Decision 9).

Frozen at
``docs/task-11-phase3-retrospective-replay-amendment.md`` §11.

This module is the **bucket #6 binding hardening**. It enforces that
Task 10 inputs (training / artifact / prediction) under
``ExecutionMode.RETROSPECTIVE_REPLAY`` may only bind to the
replay-produced Task 9 row + its result_hash, and must not silently
fall back to current-data / latest-row / wall-clock-derived outputs.

§11 contract summary (verbatim, see doc for full text):

1. ``task9_run_id`` MUST equal the replay-produced
   ``HarvestStateRun.id`` (the row whose ``is_replay = TRUE``). The
   Phase 2 resolver path that picks the latest historical row is
   disabled; only the row produced by the current replay's
   ``execute_harvest_state_run`` + subsequent replay-metadata writer
   (bucket #4) is binding-eligible.
2. ``task9_result_hash`` MUST be loaded from
   ``load_harvest_state_output_by_id(session, run_id=…)``, not from
   any earlier historical row.
3. ``Task10ModelPolicy.REPLAY_TRAINED_MODEL`` only allows replay
   strategies already covered by Issue #29. Issue #29 §3 currently
   only authorizes ``HISTORICALLY_AVAILABLE_MODEL`` for replay;
   ``REPLAY_TRAINED_MODEL`` requests are therefore rejected with
   ``TASK10_REPLAY_BINDING_INVALID``.
4. Cross-run substitution is rejected: the only allowed
   ``task9_run_id`` is the one produced by the current replay.
5. The binding event is recorded as an
   ``AvailabilityBlockerCode``-typed entry on the rolling
   ``rolling_backtest_stage_event`` table.

Hard constraints (per bucket #6 authorization):

- No new migration, schema, or ORM changes.
- No Task 9 service behavior changes (no call to
  ``run_harvest_state_model`` or any lower-level Task 9 internals).
- No Task 10 residual-model semantics beyond the binding contract.
- No current-data / latest-row / wall-clock fallback introduced.
- No availability / resolution authority semantics changes (the §11
  rules apply exclusively to ``ExecutionMode.RETROSPECTIVE_REPLAY``;
  the historical path is unchanged).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.harvest_state.persistence import (
    load_harvest_state_output_by_id,
)
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.residual_model.persistence import (
    ResidualModelPersistenceError,
    load_residual_prediction_run_by_id,
)

from .enums import AvailabilitySourceType, ExecutionMode, Task10ModelPolicy
from .node_orchestration import Task10ReplayBindingInvalidError
from .orchestration import OrchestrationBlocker
from .replay_pipeline import ReplayPipelineOutcome

if TYPE_CHECKING:
    from .orchestration import ResolvedInputOutcome


# ── Frozen blocker code ───────────────────────────────────────────────────────
# §7 blocker taxonomy (Decision 5) frozen in bucket #2; the literal is
# carried from ``OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID`` to
# avoid drift between the enum and the typed-error ``code``.
_TASK10_REPLAY_BINDING_INVALID_BLOCKER: Final[str] = (
    OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID.value
)


# ── Identity projection ──────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ReplayTask9BindingContext:
    """Compact projection of the replay-produced Task 9 identity for binding.

    Built from a :class:`ReplayPipelineOutcome` plus the replay-stamped
    ``HarvestStateRun`` row (``is_replay = TRUE``) loaded by the metadata
    writer. This is the **only** set of bindings Task 10 may consume
    under ``ExecutionMode.RETROSPECTIVE_REPLAY`` (§11 §1 + §2).

    Attributes:
        task9_run_id: The replay-produced ``HarvestStateRun.id``.
        task9_result_hash: The replay-produced
            ``HarvestStateRun.result_hash`` (loaded from
            ``load_harvest_state_output_by_id`` per §11 §2, NOT
            propagated from any earlier historical row).
        is_replay_provenance: Always ``True`` for this projection. The
            loaded row's ``is_replay`` column MUST be ``TRUE``; a
            ``False`` or ``None`` value causes binding failure
            with code :attr:`TASK10_REPLAY_BINDING_INVALID`.
        replay_code_version: The ``code_version`` carried by the
            replay runtime identity.
        replay_executed_at: The ``replay_executed_at`` stamped by
            bucket #4; used for audit diagnostics only.
    """

    task9_run_id: int
    task9_result_hash: str
    is_replay_provenance: bool
    replay_code_version: str
    replay_executed_at: datetime


# ── Public exception / helper ────────────────────────────────────────────────


def is_replay_execution_mode(execution_mode: ExecutionMode | str) -> bool:
    """Return ``True`` iff ``execution_mode == ExecutionMode.RETROSPECTIVE_REPLAY``.

    Accepts both the enum and the raw string value to keep callers
    tolerant of cfg-driven config payloads.
    """
    if isinstance(execution_mode, ExecutionMode):
        return execution_mode is ExecutionMode.RETROSPECTIVE_REPLAY
    return str(execution_mode) == ExecutionMode.RETROSPECTIVE_REPLAY.value


async def build_replay_task9_binding_context(
    session: AsyncSession,
    *,
    replay_outcome: ReplayPipelineOutcome,
) -> ReplayTask9BindingContext:
    """Construct a :class:`ReplayTask9BindingContext` from a replay outcome.

    Validates that:

    - the ``HarvestStateRun`` row referenced by
      ``replay_outcome.task9_run_id`` exists and has
      ``is_replay = TRUE`` (§11 §1 — replay-produced row);
    - ``load_harvest_state_output_by_id(session, run_id=...)``
      returns a completed payload with the matching
      ``result_hash`` (§11 §2 — result_hash loaded from a
      dedicated integrity loader, not from any earlier historical
      row).

    Raises:
        Task10ReplayBindingInvalidError: If the row is missing, the
            row's ``is_replay`` is not ``True``, or the integrity
            loader cannot produce a matching ``result_hash``. The
            catch block at lines ~2383-2428 of ``node_orchestration.py``
            converts this into a blocked outcome with the §7 frozen
            ``task10_replay_binding_invalid`` blocker code.
    """
    # Mirror the bucket #4 metadata-writer pattern (replay_metadata.py
    # lines 297-306): load via select + scalar_one_or_none(). A direct
    # ``session.get(HarvestStateRun, run_id)`` is equivalent but the
    # select keeps the call site style-consistent with the rest of the
    # replay module.
    result = await session.execute(
        select(HarvestStateRun).where(HarvestStateRun.id == replay_outcome.task9_run_id)
    )
    run_row = result.scalar_one_or_none()
    if run_row is None:
        raise Task10ReplayBindingInvalidError(
            "replay-produced HarvestStateRun "
            f"id={replay_outcome.task9_run_id} not found; "
            "cross-run substitution is not allowed (§11 §1)",
        )

    is_replay_value = bool(getattr(run_row, "is_replay", False))
    if not is_replay_value:
        raise Task10ReplayBindingInvalidError(
            f"Task 9 run id={replay_outcome.task9_run_id} has "
            f"is_replay={is_replay_value}; expected is_replay=TRUE "
            "for replay-mode binding (§11 §1)",
        )

    # §11 §2: result_hash is loaded from the dedicated integrity loader,
    # not from any earlier historical row.
    output = await load_harvest_state_output_by_id(
        session, run_id=replay_outcome.task9_run_id
    )
    if output is None or getattr(output, "result_hash", None) is None:
        raise Task10ReplayBindingInvalidError(
            "replay-produced HarvestStateRun id="
            f"{replay_outcome.task9_run_id} did not yield a "
            "valid result_hash via "
            "load_harvest_state_output_by_id (§11 §2)",
        )

    return ReplayTask9BindingContext(
        task9_run_id=replay_outcome.task9_run_id,
        task9_result_hash=output.result_hash,
        is_replay_provenance=True,
        replay_code_version=replay_outcome.code_version,
        replay_executed_at=replay_outcome.replay_executed_at,
    )


# ── Binding validator ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ReplayTask10BindingOutcome:
    """Outcome of a successful replay-binding evaluation.

    Fields populated only after
    :func:`evaluate_replay_task10_binding` returns without raising.
    On any failure the function raises
    :class:`Task10ReplayBindingInvalidError` instead.

    Attributes:
        prediction_run_id: The pinned Task 10 prediction
            ``database_run_id`` accepted as the binding target.
        task9_run_id: Echoed from the binding context for audit.
        task9_result_hash: Echoed from the binding context for audit.
        is_replay_provenance: Always ``True`` — confirmation that the
            binding-target prediction row references the replay-produced
            Task 9 row, NOT an earlier historical row.
        model_policy: The ``Task10ModelPolicy`` that authorized this
            binding (always
            :attr:`Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL` per
            Issue #29 §3 + §11 §3).
    """

    prediction_run_id: int
    task9_run_id: int
    task9_result_hash: str
    is_replay_provenance: bool
    model_policy: Task10ModelPolicy


def validate_replay_task10_model_policy(
    *,
    requested_policy: Task10ModelPolicy | str | None,
) -> Task10ModelPolicy:
    """Enforce Issue #29 §3 + §11 §3: reject ``REPLAY_TRAINED_MODEL`` for replay.

    Returns the validated policy. Raises
    :class:`Task10ReplayBindingInvalidError` for any policy other than
    :attr:`Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL` (including
    ``None`` and unrecognized values).
    """
    if requested_policy is None:
        raise Task10ReplayBindingInvalidError(
            "Task 10 model policy must be "
            "HISTORICALLY_AVAILABLE_MODEL for replay; "
            "REPLAY_TRAINED_MODEL would require a strategy "
            "authorized by Issue #29, which currently covers "
            "none. See §11 §3 + Issue #29 §3.",
        )
    if isinstance(requested_policy, Task10ModelPolicy):
        policy_value = requested_policy
    else:
        try:
            policy_value = Task10ModelPolicy(requested_policy)
        except ValueError as exc:
            raise Task10ReplayBindingInvalidError(
                f"unknown Task 10 model policy: {requested_policy!r}",
            ) from exc

    if policy_value is not Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL:
        raise Task10ReplayBindingInvalidError(
            f"Task 10 model policy {policy_value.value} is not "
            "authorized for replay (Issue #29 §3 only covers "
            "HISTORICALLY_AVAILABLE_MODEL); refusing to invent "
            "a replay-trained strategy (§11 §3 stop condition).",
        )
    return policy_value


def _select_task10_prediction_input(
    resolved_inputs: dict[str, ResolvedInputOutcome],
) -> ResolvedInputOutcome | None:
    """Return the Task 10 prediction resolved input, if present.

    Iterates the resolved_inputs mapping (mirrors the Phase 2 selection
    in ``_resolve_task10_reuse``) and returns the first input whose
    ``source_type`` is :attr:`TASK10_PREDICTION_RUN`. Returns
    ``None`` when no such input exists (legitimately — the resolved
    Inputs may carry only training / artifact / analytics_build for
    some replay configurations).
    """
    for outcome in resolved_inputs.values():
        if outcome.source_type is AvailabilitySourceType.TASK10_PREDICTION_RUN:
            return outcome
    return None


def _prediction_database_run_id(
    prediction_input: ResolvedInputOutcome,
) -> int:
    """Extract the integer ``database_run_id`` from a Task 10 prediction input.

    Mirrors the Phase 2 ``_require_database_ref(..., allowed_types=("database_run_id",))``
    helper but stays pure (no DB access). For replay binding, only
    database_run_id references are accepted (no artifact_id, no
    semantic_hash-only refs).
    """
    reference = prediction_input.persistent_reference
    if reference.reference_type != "database_run_id":
        raise Task10ReplayBindingInvalidError(
            "Task 10 prediction must be a database_run_id "
            f"reference for replay binding; got "
            f"{reference.reference_type!r}",
        )
    if not isinstance(reference.reference_value, int):
        raise Task10ReplayBindingInvalidError(
            "Task 10 prediction database_run_id must be an int; "
            f"got {type(reference.reference_value).__name__}",
        )
    return reference.reference_value


async def evaluate_replay_task10_binding(
    session: AsyncSession,
    *,
    binding_context: ReplayTask9BindingContext,
    prediction_input: ResolvedInputOutcome | None,
    requested_policy: Task10ModelPolicy | str | None,
) -> ReplayTask10BindingOutcome | None:
    """Validate the §11 replay Task 10 binding against the replay context.

    §11 rules (verbatim sequence):

    1. If a Task 10 prediction is present in the resolved inputs,
       load the pinned prediction row and require:
       - ``prediction.task9_run_id == binding_context.task9_run_id``
         (cross-run substitution ⇒
         :class:`Task10ReplayBindingInvalidError`).
       - ``prediction.task9_result_hash == binding_context.task9_result_hash``
         (cross-run / hash-mismatch substitution ⇒ same error).
       - ``prediction.mode != "historical_observed"`` (Decision 8 —
         replay output cannot pose as
         :attr:`ExecutionMode.HISTORICAL_OBSERVED`; fall-through if
         a current-data / wall-clock shadowed row is presented ⇒ same
         error).
    2. If no prediction is bound (no Task 10 prediction output at all),
       the binding is trivially satisfied for replay; reject only on
       policy-mismatch — i.e., a ``REPLAY_TRAINED_MODEL`` policy
       request without an authorizing Issue #29 strategy ⇒
       :class:`Task10ReplayBindingInvalidError`.

    Returns a :class:`ReplayTask10BindingOutcome` if the binding holds;
    otherwise raises :class:`Task10ReplayBindingInvalidError`.

    The function does NOT call ``run_harvest_state_model`` or any
    Task 9 lower-level internals (§11 §1 / Decision 3 — bucket #6 may
    not change Task 9 service behavior). It only loads the integrity
    views via ``load_residual_prediction_run_by_id``.

    Args:
        session: Async SQLAlchemy session. Used **only** to call
            ``load_residual_prediction_run_by_id`` — no inserts, no
            updates, no new transactions.
        binding_context: The :class:`ReplayTask9BindingContext`
            produced by :func:`build_replay_task9_binding_context`
            for this replay's Task 9 row.
        prediction_input: The ``task10_prediction_run`` resolved
            input, or ``None`` if the replay run does not bind a
            Task 10 prediction (the replay pipeline is free to
            emit Task 9 output without a downstream Task 10
            prediction; the binding validator accommodates both).
        requested_policy: The Task 10 model policy requested by the
            caller. See :func:`validate_replay_task10_model_policy`.

    Returns:
        ``None`` if no Task 10 prediction input was supplied AND the
        requested policy is allowed — the replay binding is trivially
        satisfied. Otherwise a :class:`ReplayTask10BindingOutcome`
        carrying the validated binding identity.

    Raises:
        Task10ReplayBindingInvalidError: On any §11 rule violation.
            The catch block converts this into a blocked outcome with
            the §7 frozen ``task10_replay_binding_invalid`` blocker
            code.
    """
    policy_value = validate_replay_task10_model_policy(
        requested_policy=requested_policy,
    )

    if prediction_input is None:
        # No prediction binding to validate. Cross-run substitution is
        # structurally impossible because there is no other run to
        # substitute. The policy gate above already rejected
        # REPLAY_TRAINED_MODEL (Issue #29 §3 + §11 §3).
        return None

    prediction_run_id = _prediction_database_run_id(prediction_input)

    # §11 §1: load via the dedicated integrity loader
    # (load_residual_prediction_run_by_id) — same loader used by Phase 2.
    try:
        prediction_result = await load_residual_prediction_run_by_id(
            session, run_id=prediction_run_id
        )
    except ResidualModelPersistenceError as exc:
        raise Task10ReplayBindingInvalidError(
            f"Task 10 prediction run {prediction_run_id} failed "
            f"integrity loader: {exc}",
        ) from exc

    if prediction_result is None:
        raise Task10ReplayBindingInvalidError(
            f"Task 10 prediction run {prediction_run_id} not "
            "found via the dedicated integrity loader; refusing "
            "to substitute an earlier or current-data row (§11 §4).",
        )

    # §11 §1: cross-run substitution rejected.
    if prediction_result.task9_run_id != binding_context.task9_run_id:
        raise Task10ReplayBindingInvalidError(
            f"Task 10 prediction run {prediction_run_id} binds to "
            f"Task 9 run {prediction_result.task9_run_id}, expected "
            f"{binding_context.task9_run_id} (replay-produced); "
            "cross-run substitution rejected (§11 §1 + §4).",
        )

    # §11 §2: hash equivalence — bind only to the replay-produced
    # result_hash loaded from load_harvest_state_output_by_id.
    if prediction_result.task9_result_hash != binding_context.task9_result_hash:
        raise Task10ReplayBindingInvalidError(
            f"Task 10 prediction run {prediction_run_id} carries "
            f"task9_result_hash={prediction_result.task9_result_hash!r}, "
            f"expected {binding_context.task9_result_hash!r} "
            "(replay-produced via load_harvest_state_output_by_id); "
            "cross-run / hash-mismatch substitution rejected "
            "(§11 §2 + §4).",
        )

    # §11 §1 / Decision 8: replay-produced row is_replay=TRUE. We
    # already enforced this above in build_replay_task9_binding_context.
    # No additional check here — the load_residual_prediction_run_by_id
    # path loads the prediction, not the upstream Task 9 row, and
    # the prediction's own ``mode`` column carries
    # ``ResidualPredictionMode`` values (residual_corrected /
    # structural_only / blocked) which are orthogonal to execution
    # mode.

    return ReplayTask10BindingOutcome(
        prediction_run_id=prediction_run_id,
        task9_run_id=binding_context.task9_run_id,
        task9_result_hash=binding_context.task9_result_hash,
        is_replay_provenance=binding_context.is_replay_provenance,
        model_policy=policy_value,
    )


async def evaluate_replay_task10_binding_for_resolved_inputs(
    session: AsyncSession,
    *,
    binding_context: ReplayTask9BindingContext,
    resolved_inputs: dict[str, ResolvedInputOutcome],
    requested_policy: Task10ModelPolicy | str | None,
) -> ReplayTask10BindingOutcome | None:
    """Convenience wrapper for the replay pipeline.

    Picks the ``TASK10_PREDICTION_RUN`` resolved input (if any) and
    delegates to :func:`evaluate_replay_task10_binding`. Bucket #6
    does NOT call this directly from the replay pipeline — the
    pipeline is in bucket #5 and remains unchanged. The wrapper is
    provided so future dispatch callers (bucket #6+ scope) can wire
    it without modifying bucket #5's surface.

    Args:
        session: Async SQLAlchemy session.
        binding_context: The :class:`ReplayTask9BindingContext`
            produced for this replay.
        resolved_inputs: The resolved inputs dict (same shape as
            :class:`_StageContext.resolved_inputs`).
        requested_policy: The Task 10 model policy requested.

    Returns:
        Same as :func:`evaluate_replay_task10_binding`.

    Raises:
        Task10ReplayBindingInvalidError: Per
            :func:`evaluate_replay_task10_binding`.
    """
    prediction_input = _select_task10_prediction_input(resolved_inputs)
    return await evaluate_replay_task10_binding(
        session,
        binding_context=binding_context,
        prediction_input=prediction_input,
        requested_policy=requested_policy,
    )
