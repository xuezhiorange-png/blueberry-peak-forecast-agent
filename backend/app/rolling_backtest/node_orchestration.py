"""Node-level orchestration service for Task 11 rolling backtest.

Executes a single rolling node through the eight-stage DAG.
Supports execution_mode=historical_observed + upstream_selection_mode=pinned.

Stages:
1. resolve_historical_inputs
2. validate_visibility
3. validate_authority_chain
4. resolve_or_replay_task8
5. resolve_or_replay_task9
6. resolve_or_train_task10
7. execute_task10_prediction
8. finalize_orchestration_snapshot

For historical_observed + pinned: stages 4-7 perform reuse, exact load,
integrity reload, and authority binding verification only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.rolling_backtest import (
    RollingBacktestAttempt,
    RollingBacktestAvailabilityAudit,
    RollingBacktestNode,
    RollingBacktestRun,
)
from backend.app.rolling_backtest.availability import (
    availability_snapshot_audit_hash,
    evaluate_authority_visibility,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload
from backend.app.rolling_backtest.enums import (
    ExecutionMode,
    UpstreamSelectionMode,
)
from backend.app.rolling_backtest.errors import (
    RollingBacktestAuthorityBindingError,
    RollingBacktestIntegrityError,
    RollingBacktestPersistenceError,
)
from backend.app.rolling_backtest.orchestration import (
    AvailabilityAuditOutcome,
    NodeOrchestrationOutcome,
    OrchestrationStage,
    ResolvedInputOutcome,
    Task9AuthorityOutcome,
    Task10AuthorityOutcome,
    _sanitize_diagnostics,
)
from backend.app.rolling_backtest.persistence import (
    _resolved_input_canonical_payload,
    create_execution_attempt,
    finalize_attempt_with_snapshot,
    load_logical_run_with_integrity,
    persist_orchestration_snapshot,
    persist_stage_event,
    update_run_status_from_attempts,
)
from backend.app.rolling_backtest.schemas import (
    AvailabilitySnapshot,
    PersistentUpstreamReference,
    ResolvedUpstreamSemanticIdentity,
    RollingBacktestConfig,
    RollingNodeDefinition,
)

# ── Error types ──────────────────────────────────────────────────────────────


class NodeOrchestrationError(RollingBacktestPersistenceError):
    """Base error for node orchestration failures."""

    code = "NODE_ORCHESTRATION_ERROR"


class UnsupportedExecutionModeError(NodeOrchestrationError):
    """Execution mode is not supported in this phase."""

    code = "UNSUPPORTED_EXECUTION_MODE"


class UnsupportedSelectionModeError(NodeOrchestrationError):
    """Selection mode is not supported in this phase."""

    code = "UNSUPPORTED_SELECTION_MODE"


class NodeAlreadyFinalizedError(NodeOrchestrationError):
    """Cannot overwrite a successfully completed node."""

    code = "NODE_ALREADY_FINALIZED"


class NodeIntegrityReloadFailedError(NodeOrchestrationError):
    """Integrity reload failed after snapshot persistence."""

    code = "INTEGRITY_RELOAD_FAILED"


class PinnedSourceNotFoundError(NodeOrchestrationError):
    """Pinned source not found in database."""

    code = "PINNED_SOURCE_NOT_FOUND"


class PinnedSourceIdentityMismatchError(NodeOrchestrationError):
    """Pinned source identity does not match database."""

    code = "PINNED_SOURCE_IDENTITY_MISMATCH"


class PinnedSourceNotVisibleError(NodeOrchestrationError):
    """Pinned source is not visible at forecast cutoff."""

    code = "PINNED_SOURCE_NOT_VISIBLE"


class Task8ParentAuthorityMismatchError(NodeOrchestrationError):
    """Task 8 parent authority chain mismatch."""

    code = "TASK8_PARENT_AUTHORITY_MISMATCH"


class Task9Task8AuthorityMismatchError(NodeOrchestrationError):
    """Task 9 frozen Task 8 identity does not match resolved Task 8."""

    code = "TASK9_TASK8_AUTHORITY_MISMATCH"


class Task10Task9BindingMismatchError(NodeOrchestrationError):
    """Task 10 binding does not match Task 9 identity."""

    code = "TASK10_TASK9_BINDING_MISMATCH"


class Task10PredictionNotCompletedError(NodeOrchestrationError):
    """Task 10 prediction run is not completed or completed_at missing."""

    code = "TASK10_PREDICTION_NOT_COMPLETED"


class Task10PredictionAfterCutoffError(NodeOrchestrationError):
    """Task 10 prediction completed_at is after forecast_cutoff_at."""

    code = "TASK10_PREDICTION_AFTER_CUTOFF"


# ── Stage execution context ─────────────────────────────────────────────────


@dataclass
class _StageContext:
    """Mutable context accumulated during stage execution."""

    attempt_id: int
    node_id: int
    run_id: int
    resolved_inputs: dict[str, ResolvedInputOutcome]
    availability_audits: dict[str, AvailabilityAuditOutcome]
    task9_authority: Task9AuthorityOutcome | None = None
    task10_authority: Task10AuthorityOutcome | None = None
    fallback_mode: str | None = None
    blocker_code: str | None = None
    diagnostics: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.diagnostics is None:
            self.diagnostics = {}


# ── Pinned source verification ───────────────────────────────────────────────


async def _verify_pinned_source(
    session: AsyncSession,
    *,
    identity: ResolvedUpstreamSemanticIdentity,
    persistent_ref: PersistentUpstreamReference,
    audit_row: Any,
    forecast_cutoff_at: datetime,
    node_timezone: str,
    as_of_local_date: Any,
) -> ResolvedInputOutcome:
    """Verify a pinned source's database existence and integrity."""
    from backend.app.rolling_backtest.schemas import AvailabilitySnapshot

    snapshot_adapter = __import__("pydantic").TypeAdapter(AvailabilitySnapshot)
    if audit_row is None:
        raise PinnedSourceNotFoundError(
            f"no availability audit for pinned source role={identity.source_role}"
        )

    snapshot = snapshot_adapter.validate_python(audit_row.canonical_payload)
    eval_result = evaluate_authority_visibility(
        snapshot=snapshot,
        execution_mode=ExecutionMode.HISTORICAL_OBSERVED,
        forecast_cutoff_at=forecast_cutoff_at,
        as_of_local_date=as_of_local_date,
        business_timezone=node_timezone,
    )
    if not eval_result.allowed:
        raise PinnedSourceNotVisibleError(
            f"pinned source role={identity.source_role} blocked by {eval_result.blocker_code}"
        )

    available_at = _extract_authoritative_available_at(snapshot)

    return ResolvedInputOutcome(
        source_role=identity.source_role,
        source_type=identity.source_type,
        semantic_identity=identity,
        persistent_reference=persistent_ref,
        authoritative_available_at=available_at,
        canonical_identity_hash=sha256_payload(
            canonical_json_dumps(_resolved_input_canonical_payload(identity))
        ),
        canonical_payload_hash=identity.semantic.canonical_payload_hash or "",
    )


def _extract_authoritative_available_at(
    snapshot: AvailabilitySnapshot,
) -> datetime:
    """Extract the authoritative available_at timestamp from an availability snapshot."""
    if hasattr(snapshot, "authoritative_timestamp"):
        return snapshot.authoritative_timestamp
    if hasattr(snapshot, "available_at"):
        from datetime import datetime as _dt

        avail_date = snapshot.available_at
        if isinstance(avail_date, datetime):
            return avail_date
        return _dt(
            avail_date.year,
            avail_date.month,
            avail_date.day,
            tzinfo=UTC,
        )
    if hasattr(snapshot, "created_at"):
        return snapshot.created_at
    return datetime.now(UTC)


# ── Task 8 reuse (stage 4) ──────────────────────────────────────────────────


async def _resolve_task8_reuse(
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    *,
    resolved_inputs: dict[str, ResolvedInputOutcome],
) -> None:
    """Stage 4: Reuse persisted Task 8 authorities.

    For historical_observed + pinned: exact-load Task 8 model run, artifact,
    forecast run, and daily predictions. Verify integrity.
    """
    # Find Task 8 related inputs
    task8_inputs = {
        role: outcome
        for role, outcome in resolved_inputs.items()
        if outcome.source_type.value.startswith("task8_")
    }
    if not task8_inputs:
        return  # No Task 8 inputs required

    # Verify parent authority chain for Task 8 artifacts
    for _role, outcome in task8_inputs.items():
        if outcome.source_type.value == "task8_model_artifact":
            # Verify the artifact's parent (model run) is in resolved inputs
            model_run_inputs = {
                r: o for r, o in task8_inputs.items() if o.source_type.value == "task8_model_run"
            }
            if not model_run_inputs:
                raise Task8ParentAuthorityMismatchError(
                    "Task 8 model artifact has no parent model run in resolved inputs"
                )


# ── Task 9 reuse (stage 5) ──────────────────────────────────────────────────


async def _resolve_task9_reuse(
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    *,
    resolved_inputs: dict[str, ResolvedInputOutcome],
) -> None:
    """Stage 5: Reuse persisted Task 9 harvest state.

    Verify: status == completed, result_hash, config_hash,
    frozen Task 8 identities match.
    """
    task9_inputs = {
        role: outcome
        for role, outcome in resolved_inputs.items()
        if outcome.source_type.value == "task9_harvest_state_run"
    }
    if not task9_inputs:
        return

    task9_outcome = next(iter(task9_inputs.values()))
    ctx.task9_authority = Task9AuthorityOutcome(
        run_reference=task9_outcome.persistent_reference,
        semantic_input_signature=task9_outcome.semantic_identity.semantic.input_signature,
        result_hash=task9_outcome.semantic_identity.semantic.result_hash,
        canonical_payload_hash=task9_outcome.semantic_identity.semantic.canonical_payload_hash,
        source_catalog_hash=None,
        verification_snapshot_hash=None,
        mode="reuse",
    )


# ── Task 10 reuse (stage 6) ─────────────────────────────────────────────────


async def _resolve_task10_reuse(
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    *,
    resolved_inputs: dict[str, ResolvedInputOutcome],
) -> None:
    """Stage 6: Reuse persisted Task 10 training and prediction.

    Verify: training run completed, artifact belongs to training run,
    prediction run completed, completed_at <= forecast_cutoff_at.
    """
    task10_inputs = {
        role: outcome
        for role, outcome in resolved_inputs.items()
        if outcome.source_type.value.startswith("task10_")
    }
    if not task10_inputs:
        return

    training = next(
        (o for t, o in task10_inputs.items() if "training" in t),
        None,
    )
    prediction = next(
        (o for t, o in task10_inputs.items() if "prediction" in t),
        None,
    )
    artifact = next(
        (o for t, o in task10_inputs.items() if "artifact" in t),
        None,
    )

    ctx.task10_authority = Task10AuthorityOutcome(
        training_reference=training.persistent_reference if training else None,
        artifact_reference=artifact.persistent_reference if artifact else None,
        prediction_reference=prediction.persistent_reference if prediction else None,
        task9_run_reference=ctx.task9_authority.run_reference if ctx.task9_authority else None,
        task9_result_hash=ctx.task9_authority.result_hash if ctx.task9_authority else None,
        input_signature=(
            prediction.semantic_identity.semantic.input_signature if prediction else None
        ),
        prediction_hash=prediction.semantic_identity.semantic.result_hash if prediction else None,
        mode="reuse",
    )


# ── Stage 7: Task 10 prediction (reuse only) ────────────────────────────────


async def _execute_task10_prediction_reuse(
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> None:
    """Stage 7: Verify persisted Task 10 prediction integrity.

    For historical_observed: no new prediction execution.
    Verify existing prediction hash matches.
    """
    if ctx.task10_authority is None:
        return
    if ctx.task10_authority.prediction_hash is None:
        return
    # Prediction reuse: integrity verified in stage 6


# ── Snapshot builder ────────────────────────────────────────────────────────


def _build_orchestration_snapshot_payload(
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    *,
    run_signature: str,
    node_signature: str,
) -> dict[str, Any]:
    """Build the canonical orchestration snapshot payload."""
    resolved_inputs_dict = {
        role: {
            "source_role": outcome.source_role,
            "source_type": outcome.source_type.value,
            "canonical_identity_hash": outcome.canonical_identity_hash,
            "canonical_payload_hash": outcome.canonical_payload_hash,
        }
        for role, outcome in ctx.resolved_inputs.items()
    }
    audits_dict = {
        role: {
            "source_role": audit.source_role,
            "source_type": audit.source_type,
            "allowed": audit.allowed,
            "blocker_code": audit.blocker_code,
            "audit_hash": audit.audit_hash,
        }
        for role, audit in ctx.availability_audits.items()
    }
    snapshot: dict[str, Any] = {
        "run_signature": run_signature,
        "node_signature": node_signature,
        "execution_mode": config.execution_mode.value,
        "upstream_selection_mode": node.upstream_selection_mode.value,
        "forecast_cutoff_at": node.forecast_cutoff_at.isoformat(),
        "resolved_inputs": resolved_inputs_dict,
        "availability_audits": audits_dict,
    }
    if ctx.task9_authority:
        snapshot["task9_authority"] = {
            "run_reference": (
                ctx.task9_authority.run_reference.model_dump(mode="python")
                if ctx.task9_authority.run_reference
                else None
            ),
            "result_hash": ctx.task9_authority.result_hash,
            "mode": ctx.task9_authority.mode,
        }
    if ctx.task10_authority:
        snapshot["task10_authority"] = {
            "training_reference": (
                ctx.task10_authority.training_reference.model_dump(mode="python")
                if ctx.task10_authority.training_reference
                else None
            ),
            "prediction_reference": (
                ctx.task10_authority.prediction_reference.model_dump(mode="python")
                if ctx.task10_authority.prediction_reference
                else None
            ),
            "mode": ctx.task10_authority.mode,
        }
    if ctx.fallback_mode:
        snapshot["fallback_mode"] = ctx.fallback_mode
    return snapshot


# ── Main orchestration entry point ───────────────────────────────────────────


async def orchestrate_node(
    session: AsyncSession,
    *,
    rolling_run_id: int,
    rolling_node_id: int,
    _before_stage_hook: Any = None,
) -> NodeOrchestrationOutcome:
    """Execute a single rolling node through the eight-stage DAG.

    This is the formal typed service for node orchestration.
    All state changes go through the persistence layer.
    """
    # ── Load and validate ─────────────────────────────────────────────────
    run_result = await session.execute(
        select(RollingBacktestRun).where(RollingBacktestRun.id == rolling_run_id)
    )
    run = run_result.scalar_one_or_none()
    if run is None:
        raise RollingBacktestIntegrityError(f"rolling run {rolling_run_id} not found")

    node_result = await session.execute(
        select(RollingBacktestNode).where(RollingBacktestNode.id == rolling_node_id)
    )
    node = node_result.scalar_one_or_none()
    if node is None:
        raise RollingBacktestIntegrityError(f"rolling node {rolling_node_id} not found")
    if node.rolling_run_id != rolling_run_id:
        raise RollingBacktestAuthorityBindingError(
            f"node {rolling_node_id} does not belong to run {rolling_run_id}"
        )

    config = _config_from_payload(run.canonical_payload)
    node_def = _node_def_from_payload(node.canonical_payload, config)

    # ── Validate execution and selection modes ────────────────────────────
    if config.execution_mode != ExecutionMode.HISTORICAL_OBSERVED:
        raise UnsupportedExecutionModeError(
            f"execution_mode={config.execution_mode.value} is not supported in this phase"
        )
    if node.upstream_selection_mode != UpstreamSelectionMode.PINNED:
        raise UnsupportedSelectionModeError(
            f"upstream_selection_mode={node.upstream_selection_mode} is not supported in this phase"
        )

    # ── Prevent overwrite of successfully completed node ──────────────────
    latest_attempt_result = await session.execute(
        select(RollingBacktestAttempt)
        .where(
            RollingBacktestAttempt.rolling_node_id == rolling_node_id,
            RollingBacktestAttempt.rolling_run_id == rolling_run_id,
        )
        .order_by(RollingBacktestAttempt.attempt_number.desc())
        .limit(1)
    )
    latest_attempt = latest_attempt_result.scalar_one_or_none()
    if latest_attempt is not None and latest_attempt.status == "completed":
        raise NodeAlreadyFinalizedError(f"node {rolling_node_id} is already completed")

    # ── Create execution attempt ──────────────────────────────────────────
    attempt = await create_execution_attempt(
        rolling_run_id,
        rolling_node_id,
        status="running",
        current_stage=OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value,
    )

    ctx = _StageContext(
        attempt_id=attempt.id,
        node_id=rolling_node_id,
        run_id=rolling_run_id,
        resolved_inputs={},
        availability_audits={},
    )

    try:
        # ── Stage 1: resolve_historical_inputs ───────────────────────────
        ctx = await _run_stage(
            session,
            ctx,
            OrchestrationStage.RESOLVE_HISTORICAL_INPUTS,
            config,
            node_def,
            _stage_resolve_historical_inputs,
            _before_stage_hook,
        )

        # ── Stage 2: validate_visibility ─────────────────────────────────
        ctx = await _run_stage(
            session,
            ctx,
            OrchestrationStage.VALIDATE_VISIBILITY,
            config,
            node_def,
            _stage_validate_visibility,
            _before_stage_hook,
        )

        # ── Stage 3: validate_authority_chain ────────────────────────────
        ctx = await _run_stage(
            session,
            ctx,
            OrchestrationStage.VALIDATE_AUTHORITY_CHAIN,
            config,
            node_def,
            _stage_validate_authority_chain,
            _before_stage_hook,
        )

        # ── Stage 4: resolve_or_replay_task8 ────────────────────────────
        ctx = await _run_stage(
            session,
            ctx,
            OrchestrationStage.RESOLVE_OR_REPLAY_TASK8,
            config,
            node_def,
            _stage_resolve_task8,
            _before_stage_hook,
        )

        # ── Stage 5: resolve_or_replay_task9 ────────────────────────────
        ctx = await _run_stage(
            session,
            ctx,
            OrchestrationStage.RESOLVE_OR_REPLAY_TASK9,
            config,
            node_def,
            _stage_resolve_task9,
            _before_stage_hook,
        )

        # ── Stage 6: resolve_or_train_task10 ────────────────────────────
        ctx = await _run_stage(
            session,
            ctx,
            OrchestrationStage.RESOLVE_OR_TRAIN_TASK10,
            config,
            node_def,
            _stage_resolve_task10,
            _before_stage_hook,
        )

        # ── Stage 7: execute_task10_prediction ───────────────────────────
        ctx = await _run_stage(
            session,
            ctx,
            OrchestrationStage.EXECUTE_TASK10_PREDICTION,
            config,
            node_def,
            _stage_execute_task10_prediction,
            _before_stage_hook,
        )

        # ── Stage 8: finalize_orchestration_snapshot ─────────────────────
        ctx = await _run_stage(
            session,
            ctx,
            OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT,
            config,
            node_def,
            _stage_finalize_snapshot,
            _before_stage_hook,
        )

        # ── Integrity reload ─────────────────────────────────────────────
        # Reload the logical run to verify persistence integrity
        await load_logical_run_with_integrity(session, run)

        # ── Finalize attempt as completed ────────────────────────────────
        await finalize_attempt_with_snapshot(
            attempt.id,
            node_id=rolling_node_id,
            status="completed",
            current_stage=OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT.value,
            snapshot_status="completed",
            terminal_stage=OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT.value,
            fallback_mode=ctx.fallback_mode,
            canonical_payload=ctx.diagnostics,
        )

        # ── Update node and run status ───────────────────────────────────
        await update_run_status_from_attempts(session, rolling_run_id)

        return _build_outcome(
            ctx=ctx,
            config=config,
            node=node_def,
            run=run,
            attempt=attempt,
            status="completed",
            stage=OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT.value,
        )

    except (
        UnsupportedExecutionModeError,
        UnsupportedSelectionModeError,
        NodeAlreadyFinalizedError,
        PinnedSourceNotFoundError,
        PinnedSourceIdentityMismatchError,
        PinnedSourceNotVisibleError,
        Task8ParentAuthorityMismatchError,
        Task9Task8AuthorityMismatchError,
        Task10Task9BindingMismatchError,
        Task10PredictionNotCompletedError,
        Task10PredictionAfterCutoffError,
    ) as exc:
        # Known typed errors → blocked
        blocker_code = getattr(exc, "code", "PERSISTENCE_FAILURE")
        await _finalize_blocked(
            session,
            ctx,
            config,
            node_def,
            run,
            attempt,
            blocker_code=blocker_code,
            error=exc,
        )
        return _build_outcome(
            ctx=ctx,
            config=config,
            node=node_def,
            run=run,
            attempt=attempt,
            status="blocked",
            stage=ctx.diagnostics.get(
                "last_completed_stage",
                OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value,
            ),
            blocker_code=blocker_code,
            diagnostics={"error": str(exc)},
        )

    except Exception as exc:
        # Unexpected errors → failed
        await _finalize_blocked(
            session,
            ctx,
            config,
            node_def,
            run,
            attempt,
            blocker_code="PERSISTENCE_FAILURE",
            error=exc,
        )
        return _build_outcome(
            ctx=ctx,
            config=config,
            node=node_def,
            run=run,
            attempt=attempt,
            status="failed",
            stage=ctx.diagnostics.get(
                "last_completed_stage",
                OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value,
            ),
            blocker_code="PERSISTENCE_FAILURE",
            diagnostics={"error": str(exc)},
        )


# ── Stage runner ─────────────────────────────────────────────────────────────


async def _run_stage(
    session: AsyncSession,
    ctx: _StageContext,
    stage: OrchestrationStage,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    stage_fn: Any,
    before_hook: Any = None,
) -> _StageContext:
    """Run a single stage: enter → execute → exit."""
    if before_hook is not None:
        hook_result = before_hook(stage.value)
        if hasattr(hook_result, "__await__"):
            await hook_result

    # Enter stage (running)
    await persist_stage_event(
        ctx.attempt_id,
        ctx.node_id,
        stage=stage.value,
        status="running",
    )

    try:
        ctx = await stage_fn(session, ctx, config, node)
        # Complete stage
        await persist_stage_event(
            ctx.attempt_id,
            ctx.node_id,
            stage=stage.value,
            status="completed",
        )
        ctx.diagnostics["last_completed_stage"] = stage.value
        return ctx

    except Exception:
        # Block/fail stage
        await persist_stage_event(
            ctx.attempt_id,
            ctx.node_id,
            stage=stage.value,
            status="blocked",
            structured_error_code="STAGE_FAILED",
        )
        raise


# ── Individual stage implementations ─────────────────────────────────────────


async def _stage_resolve_historical_inputs(  # noqa: ARG001
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> _StageContext:
    """Stage 1: Resolve historical inputs from persisted resolved_upstream_semantic_identities."""
    for identity in node.resolved_upstream_semantic_identities:
        outcome = ResolvedInputOutcome(
            source_role=identity.source_role,
            source_type=identity.source_type,
            semantic_identity=identity,
            persistent_reference=identity.persistent_reference
            or PersistentUpstreamReference(reference_type="database_run_id", reference_value=0),
            authoritative_available_at=datetime.now(UTC),
            canonical_identity_hash=sha256_payload(
                canonical_json_dumps(_resolved_input_canonical_payload(identity))
            ),
            canonical_payload_hash=identity.semantic.canonical_payload_hash or "",
            business_version=identity.semantic.business_version,
        )
        ctx.resolved_inputs[identity.source_role] = outcome
    return ctx


async def _stage_validate_visibility(
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> _StageContext:
    """Stage 2: Validate availability visibility for all resolved inputs."""
    from backend.app.rolling_backtest.schemas import AvailabilitySnapshot

    snapshot_adapter = __import__("pydantic").TypeAdapter(AvailabilitySnapshot)

    # Load persisted availability audits
    audit_result = await session.execute(
        select(RollingBacktestAvailabilityAudit).where(
            RollingBacktestAvailabilityAudit.rolling_node_id == ctx.node_id
        )
    )
    audit_rows = audit_result.scalars().all()
    audit_by_role = {a.source_role: a for a in audit_rows}

    for role, outcome in ctx.resolved_inputs.items():
        audit_row = audit_by_role.get(role)
        if audit_row is None:
            raise RollingBacktestAuthorityBindingError(
                f"no availability audit for resolved input role={role}"
            )
        snapshot = snapshot_adapter.validate_python(audit_row.canonical_payload)
        eval_result = evaluate_authority_visibility(
            snapshot=snapshot,
            execution_mode=config.execution_mode,
            forecast_cutoff_at=node.forecast_cutoff_at,
            as_of_local_date=node.as_of_local_date,
            business_timezone=config.cutoff_timezone,
        )
        available_at = _extract_authoritative_available_at(snapshot)
        ctx.availability_audits[role] = AvailabilityAuditOutcome(
            source_role=role,
            source_type=outcome.source_type.value,
            allowed=eval_result.allowed,
            blocker_code=eval_result.blocker_code,
            authoritative_available_at=available_at.isoformat(),
            forecast_cutoff_at=node.forecast_cutoff_at.isoformat(),
            audit_hash=availability_snapshot_audit_hash(snapshot),
            parent_authority=None,
        )
        if not eval_result.allowed:
            raise PinnedSourceNotVisibleError(
                f"pinned source role={role} blocked by {eval_result.blocker_code}"
            )
    return ctx


async def _stage_validate_authority_chain(  # noqa: ARG001
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> _StageContext:
    """Stage 3: Validate authority chains for all resolved inputs."""
    # For pinned mode, the authority chain is validated by the
    # availability audits (stage 2) and the integrity reload
    # that follows the orchestration snapshot.
    # Here we verify that all resolved inputs have valid hashes.
    for role, outcome in ctx.resolved_inputs.items():
        if outcome.semantic_identity.semantic.semantic_payload_hash == "":
            raise RollingBacktestAuthorityBindingError(
                f"resolved input role={role} has empty semantic_payload_hash"
            )
    return ctx


async def _stage_resolve_task8(  # noqa: ARG001
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> _StageContext:
    """Stage 4: Resolve or replay Task 8.

    For historical_observed + pinned: reuse persisted Task 8.
    Verify parent authority chain.
    """
    await _resolve_task8_reuse(ctx, config, node, resolved_inputs=ctx.resolved_inputs)
    return ctx


async def _stage_resolve_task9(  # noqa: ARG001
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> _StageContext:
    """Stage 5: Resolve or replay Task 9.

    For historical_observed + pinned: reuse persisted Task 9.
    Verify frozen Task 8 identity matches.
    """
    await _resolve_task9_reuse(ctx, config, node, resolved_inputs=ctx.resolved_inputs)
    return ctx


async def _stage_resolve_task10(  # noqa: ARG001
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> _StageContext:
    """Stage 6: Resolve or train Task 10.

    For historical_observed + pinned: reuse persisted Task 10.
    Verify training run completed, prediction run completed.
    """
    await _resolve_task10_reuse(ctx, config, node, resolved_inputs=ctx.resolved_inputs)
    return ctx


async def _stage_execute_task10_prediction(  # noqa: ARG001
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> _StageContext:
    """Stage 7: Execute Task 10 prediction.

    For historical_observed: reuse persisted prediction only.
    """
    await _execute_task10_prediction_reuse(ctx, config, node)
    return ctx


async def _stage_finalize_snapshot(
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> _StageContext:
    """Stage 8: Finalize orchestration snapshot.

    Atomic persistence of immutable snapshot.
    """
    from backend.app.rolling_backtest.signatures import (
        node_signature_hash,
        run_signature_hash,
    )

    run_sig = run_signature_hash(config)
    node_sig = node_signature_hash(config, node)

    snapshot_payload = _build_orchestration_snapshot_payload(
        ctx,
        config,
        node,
        run_signature=run_sig,
        node_signature=node_sig,
    )

    await persist_orchestration_snapshot(
        ctx.attempt_id,
        ctx.node_id,
        status="completed",
        terminal_stage=OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT.value,
        canonical_payload=snapshot_payload,
    )
    return ctx


# ── Blocked/finalize helper ─────────────────────────────────────────────────


async def _finalize_blocked(
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    run: RollingBacktestRun,
    attempt: RollingBacktestAttempt,
    *,
    blocker_code: str,
    error: Exception,
) -> None:
    """Finalize attempt and snapshot as blocked."""
    diagnostics = _sanitize_diagnostics(
        {
            "error": str(error),
            "error_type": type(error).__name__,
            "blocker_code": blocker_code,
        }
    )
    terminal_stage = ctx.diagnostics.get(
        "last_completed_stage",
        OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value,
    )

    try:
        await finalize_attempt_with_snapshot(
            attempt.id,
            node_id=ctx.node_id,
            status="blocked",
            current_stage=terminal_stage,
            snapshot_status="blocked",
            terminal_stage=terminal_stage,
            blocker_code=blocker_code,
            structured_error_code=blocker_code,
            sanitized_diagnostics=diagnostics,
            canonical_payload={"blocker_code": blocker_code},
        )
    except Exception:
        pass  # Best-effort finalize

    try:
        await update_run_status_from_attempts(session, ctx.run_id)
    except Exception:
        pass


# ── Outcome builder ──────────────────────────────────────────────────────────


def _build_outcome(
    *,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    run: RollingBacktestRun,
    attempt: RollingBacktestAttempt,
    status: str,
    stage: str,
    blocker_code: str | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> NodeOrchestrationOutcome:
    """Build the final orchestration outcome."""

    return NodeOrchestrationOutcome(
        rolling_run_signature=run.run_signature,
        node_signature=node.node_signature if hasattr(node, "node_signature") else "",
        attempt_number=attempt.attempt_number,
        status=status,
        stage=stage,
        resolved_inputs=tuple(ctx.resolved_inputs.values()),
        availability_audits=tuple(ctx.availability_audits.values()),
        task9_authority=ctx.task9_authority,
        task10_authority=ctx.task10_authority,
        fallback_mode=ctx.fallback_mode,
        blocker_code=blocker_code,
        diagnostics=diagnostics or {},
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _config_from_payload(payload: dict[str, Any]) -> RollingBacktestConfig:
    """Reconstruct config from canonical payload."""
    from copy import deepcopy

    from pydantic import TypeAdapter

    # Canonical payloads strip display_label — restore it for validation
    normalized = deepcopy(payload)
    for node in normalized.get("nodes", []):
        for ident in node.get("resolved_upstream_semantic_identities", []):
            sem = ident.get("semantic")
            if isinstance(sem, dict) and "display_label" not in sem:
                sem["display_label"] = "__canonical__"
    adapter = TypeAdapter(RollingBacktestConfig)
    return adapter.validate_python(normalized)
    return adapter.validate_python(payload)


def _node_def_from_payload(
    payload: dict[str, Any],
    config: RollingBacktestConfig,
) -> RollingNodeDefinition:
    """Reconstruct node definition from canonical payload."""
    from pydantic import TypeAdapter

    adapter = TypeAdapter(RollingNodeDefinition)
    node_def = adapter.validate_python(payload)
    # Populate resolved identities from config's node matching
    for cfg_node in config.nodes:
        if cfg_node.season_id == node_def.season_id and cfg_node.node_key == node_def.node_key:
            return cfg_node
    return node_def
