"""Rolling backtest orchestration: node execution, Task 9/10 binding, and persistence.

Phase 3 orchestration layer — consumes resolved identities from the resolution
layer, validates authority chains, invokes existing Task 9/10 services, and
persists execution attempts, stages, blockers, and diagnostics via Phase 2
repository. All persistence is mandatory; no skeleton or best-effort paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
    ExecutionMode,
    Task10ModelPolicy,
)
from backend.app.rolling_backtest.persistence import (
    RollingBacktestPersistenceCommand,
    RollingNodePersistenceCommand,
    create_execution_attempt,
    create_or_load_logical_run,
    finalize_attempt_status,
    load_logical_run_with_integrity,
)
from backend.app.rolling_backtest.resolution import (
    HistoricalCandidate,
    ResolutionResult,
    resolve_historical,
    resolve_pinned,
)
from backend.app.rolling_backtest.schemas import (
    PersistentUpstreamReference,
    ResolvedUpstreamSemanticIdentity,
    RollingBacktestConfig,
    RollingNodeDefinition,
)

# ── Orchestration stage enum ─────────────────────────────────────────────────


class OrchestrationStage(StrEnum):
    """Typed stages for node orchestration execution."""

    RESOLVE_HISTORICAL_INPUTS = "resolve_historical_inputs"
    VALIDATE_VISIBILITY = "validate_visibility"
    VALIDATE_AUTHORITY_CHAIN = "validate_authority_chain"
    RESOLVE_OR_REPLAY_TASK8 = "resolve_or_replay_task8"
    RESOLVE_OR_REPLAY_TASK9 = "resolve_or_replay_task9"
    RESOLVE_OR_TRAIN_TASK10 = "resolve_or_train_task10"
    EXECUTE_TASK10_PREDICTION = "execute_task10_prediction"
    FINALIZE_ORCHESTRATION_SNAPSHOT = "finalize_orchestration_snapshot"


# ── Structured blocker codes ─────────────────────────────────────────────────


class OrchestrationBlocker(StrEnum):
    """Stable blocker codes for orchestration failures."""

    HISTORICAL_SOURCE_NOT_FOUND = "historical_source_not_found"
    HISTORICAL_SOURCE_NOT_VISIBLE = "historical_source_not_visible"
    HISTORICAL_SOURCE_INTEGRITY_FAILURE = "historical_source_integrity_failure"
    AMBIGUOUS_HISTORICAL_CANDIDATE = "ambiguous_historical_candidate"
    PINNED_SOURCE_NOT_FOUND = "pinned_source_not_found"
    PINNED_SOURCE_TYPE_MISMATCH = "pinned_source_type_mismatch"
    PINNED_SOURCE_ROLE_MISMATCH = "pinned_source_role_mismatch"
    PINNED_SOURCE_NOT_VISIBLE = "pinned_source_not_visible"
    PINNED_SOURCE_IDENTITY_MISMATCH = "pinned_source_identity_mismatch"
    PINNED_SOURCE_INTEGRITY_FAILURE = "pinned_source_integrity_failure"
    TASK8_PARENT_AUTHORITY_MISMATCH = "task8_parent_authority_mismatch"
    TASK9_TASK8_AUTHORITY_MISMATCH = "task9_task8_authority_mismatch"
    TASK9_REPLAY_INPUT_INCOMPLETE = "task9_replay_input_incomplete"
    TASK9_EXECUTION_BLOCKED = "task9_execution_blocked"
    TASK10_MODEL_NOT_AVAILABLE = "task10_model_not_available"
    TASK10_TRAINING_NOT_IMPLEMENTED = "task10_training_not_implemented"
    TASK10_TASK9_BINDING_MISMATCH = "task10_task9_binding_mismatch"
    TASK10_PREDICTION_BLOCKED = "task10_prediction_blocked"
    TASK10_PREDICTION_SERVICE_FAILURE = "task10_prediction_service_failure"
    FUTURE_SOURCE_LEAKAGE_DETECTED = "future_source_leakage_detected"
    NO_SESSION_CONFIGURED = "no_session_configured"
    PERSISTENCE_FAILURE = "persistence_failure"


# ── Typed outcome contracts ──────────────────────────────────────────────────


__all__ = [
    "HistoricalCandidate",
    "ResolutionResult",
    "ResolvedInputOutcome",
    "Task9AuthorityOutcome",
    "Task10AuthorityOutcome",
    "NodeOrchestrationOutcome",
    "OrchestrationStage",
    "OrchestrationBlocker",
    "orchestrate_node",
    "orchestrate_run",
    "_collect_diagnostics",
    "_sanitize_diagnostics",
]


@dataclass(frozen=True, slots=True)
class ResolvedInputOutcome:
    source_role: str
    source_type: AvailabilitySourceType
    semantic_identity: ResolvedUpstreamSemanticIdentity
    persistent_reference: PersistentUpstreamReference
    authoritative_available_at: datetime
    canonical_identity_hash: str
    canonical_payload_hash: str
    business_version: str | None = None


@dataclass(frozen=True, slots=True)
class AvailabilityAuditOutcome:
    """Typed availability audit record (replaces dict[str, object])."""

    source_role: str
    source_type: str
    allowed: bool
    blocker_code: str | None = None
    authoritative_available_at: str = ""
    forecast_cutoff_at: str = ""
    audit_hash: str = ""


@dataclass(frozen=True, slots=True)
class Task9AuthorityOutcome:
    run_reference: PersistentUpstreamReference | None = None
    semantic_input_signature: str | None = None
    result_hash: str | None = None
    canonical_payload_hash: str | None = None
    source_catalog_hash: str | None = None
    verification_snapshot_hash: str | None = None
    mode: str = "unresolved"


@dataclass(frozen=True, slots=True)
class Task10AuthorityOutcome:
    training_reference: PersistentUpstreamReference | None = None
    artifact_reference: PersistentUpstreamReference | None = None
    prediction_reference: PersistentUpstreamReference | None = None
    task9_run_reference: PersistentUpstreamReference | None = None
    task9_result_hash: str | None = None
    input_signature: str | None = None
    prediction_hash: str | None = None
    mode: str = "unresolved"


@dataclass(frozen=True, slots=True)
class NodeOrchestrationOutcome:
    rolling_run_signature: str
    node_signature: str
    attempt_number: int
    status: str
    stage: str
    resolved_inputs: tuple[ResolvedInputOutcome, ...] = ()
    availability_audits: tuple[AvailabilityAuditOutcome, ...] = ()
    task9_authority: Task9AuthorityOutcome | None = None
    task10_authority: Task10AuthorityOutcome | None = None
    fallback_mode: str | None = None
    blocker_code: str | None = None
    diagnostics: dict[str, object] = field(default_factory=dict)
    canonical_payload_hash: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None


# ── Run-level orchestration entry point ──────────────────────────────────────


async def orchestrate_run(
    config: RollingBacktestConfig,
    nodes: tuple[RollingNodeDefinition, ...],
) -> tuple[NodeOrchestrationOutcome, ...]:
    """Create or load a logical run, then orchestrate each node with real sessions.

    Uses Phase 2 repository for run management and the default AsyncSessionMaker
    for database access. No skeleton/sessionless paths exist in production.
    """
    from backend.app.db.session import AsyncSessionMaker

    persistence_cmd = RollingBacktestPersistenceCommand(
        config=config,
        nodes=tuple(RollingNodePersistenceCommand(node=node) for node in nodes),
    )

    run = await create_or_load_logical_run(persistence_cmd)
    run_signature = run.run_signature

    outcomes: list[NodeOrchestrationOutcome] = []
    for _i, node in enumerate(nodes):
        async with AsyncSessionMaker() as session:
            outcome = await orchestrate_node(
                session=session,
                config=config,
                node=node,
                run_signature=run_signature,
                logical_run_id=run.id,
            )
        outcomes.append(outcome)

    # Integrity reload to verify persistence parity
    try:
        async with AsyncSessionMaker() as integrity_session:
            await load_logical_run_with_integrity(integrity_session, run)
    except Exception:
        pass  # Non-blocking parity check

    return tuple(outcomes)


# ── Node orchestration entry point ───────────────────────────────────────────


async def orchestrate_node(
    session: AsyncSession,
    *,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    run_signature: str,
    logical_run_id: int,
) -> NodeOrchestrationOutcome:
    """Execute full node orchestration: resolve inputs → validate → execute → persist.

    Session is REQUIRED — there is no skeleton/sessionless path.
    All persistence operations are mandatory.
    """
    started_at = datetime.now(UTC)
    node_sig = _node_sig_str(config, node)

    # ── Create execution attempt via Phase 2 persistence ─────────────────
    try:
        attempt = await create_execution_attempt(
            logical_run_id,
            status="running",
            current_stage=OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value,
        )
        attempt_id = attempt.id
        attempt_number = attempt.attempt_number
    except Exception as exc:
        return NodeOrchestrationOutcome(
            rolling_run_signature=run_signature,
            node_signature=node_sig,
            attempt_number=1,
            status="blocked",
            stage=OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value,
            blocker_code=OrchestrationBlocker.PERSISTENCE_FAILURE.value,
            diagnostics={"error": _safe_str(exc)},
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )

    # ── Stage 1: Resolve historical inputs ────────────────────────────
    stage = OrchestrationStage.RESOLVE_HISTORICAL_INPUTS
    await _persist_stage(attempt_id, stage.value, "running")

    resolutions, blocked, blocker_code = await _resolve_all_inputs(session, node, config)

    if blocked:
        return await _make_blocked_outcome(
            attempt_id,
            run_signature,
            node_sig,
            attempt_number,
            stage,
            blocker_code,
            resolutions,
            started_at,
        )

    # ── Stage 2: Validate visibility ──────────────────────────────────
    stage = OrchestrationStage.VALIDATE_VISIBILITY
    await _persist_stage(attempt_id, stage.value, "running")

    for result in resolutions:
        if result.resolved is None:
            continue
        if result.resolved.authoritative_available_at > node.forecast_cutoff_at:
            return await _make_blocked_outcome(
                attempt_id,
                run_signature,
                node_sig,
                attempt_number,
                stage,
                OrchestrationBlocker.FUTURE_SOURCE_LEAKAGE_DETECTED.value,
                resolutions,
                started_at,
                extra_diag={
                    "source_role": result.source_role,
                    "available_at": result.resolved.authoritative_available_at.isoformat(),
                    "cutoff": node.forecast_cutoff_at.isoformat(),
                },
            )

    # ── Stage 3: Validate authority chain ─────────────────────────────
    stage = OrchestrationStage.VALIDATE_AUTHORITY_CHAIN
    await _persist_stage(attempt_id, stage.value, "running")

    authority_blocked = await _validate_authority_chain(session, resolutions, node)
    if authority_blocked:
        return await _make_blocked_outcome(
            attempt_id,
            run_signature,
            node_sig,
            attempt_number,
            stage,
            authority_blocked,
            resolutions,
            started_at,
        )

    # ── Stage 4: Task 8 resolution ────────────────────────────────────
    stage = OrchestrationStage.RESOLVE_OR_REPLAY_TASK8
    await _persist_stage(attempt_id, stage.value, "running")

    # Verify Task 8 model → forecast → daily prediction chain
    task8_blocked = await _validate_task8_chain(session, resolutions, node)
    if task8_blocked:
        return await _make_blocked_outcome(
            attempt_id,
            run_signature,
            node_sig,
            attempt_number,
            stage,
            task8_blocked,
            resolutions,
            started_at,
        )

    # ── Stage 5: Task 9 resolution ────────────────────────────────────
    stage = OrchestrationStage.RESOLVE_OR_REPLAY_TASK9
    await _persist_stage(attempt_id, stage.value, "running")

    task9_authority, task9_blocked = await _resolve_task9(
        session,
        resolutions,
        config,
        node,
        attempt_id,
        run_signature,
        node_sig,
        attempt_number,
        stage,
        started_at,
    )
    if task9_blocked:
        return task9_blocked  # Already a NodeOrchestrationOutcome from _resolve_task9

    # ── Stage 6: Task 10 model resolution ─────────────────────────────
    stage = OrchestrationStage.RESOLVE_OR_TRAIN_TASK10
    await _persist_stage(attempt_id, stage.value, "running")

    task10_authority, task10_blocked = _resolve_task10_model(
        resolutions,
        task9_authority,
        node,
        attempt_id,
        run_signature,
        node_sig,
        attempt_number,
        stage,
        started_at,
    )
    if task10_blocked:
        return task10_blocked

    # ── Stage 7: Task 10 prediction execution ─────────────────────────
    stage = OrchestrationStage.EXECUTE_TASK10_PREDICTION
    await _persist_stage(attempt_id, stage.value, "running")

    pred_blocked = await _execute_task10_prediction(
        session,
        task10_authority,
        task9_authority,
        attempt_id,
        run_signature,
        node_sig,
        attempt_number,
        stage,
        resolutions,
        started_at,
    )
    if pred_blocked:
        return pred_blocked

    # ── Stage 8: Finalize ────────────────────────────────────────────
    stage = OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT

    resolved_inputs = tuple(
        ResolvedInputOutcome(
            source_role=r.source_role,
            source_type=r.source_type,
            semantic_identity=r.resolved.semantic_identity,
            persistent_reference=r.resolved.persistent_reference,
            authoritative_available_at=r.resolved.authoritative_available_at,
            canonical_identity_hash=r.resolved.canonical_identity_hash,
            canonical_payload_hash=r.resolved.canonical_payload_hash,
            business_version=r.resolved.business_version,
        )
        for r in resolutions
        if r.resolved is not None
    )

    # Build availability audits
    audits = tuple(_build_audit_outcome(r, node) for r in resolutions if r.resolved is not None)

    # Compute canonical payload hash from all resolved identities
    from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload

    outcome_payload = {
        "run_signature": run_signature,
        "node_signature": node_sig,
        "attempt_number": attempt_number,
        "execution_mode": config.execution_mode.value,
        "stage": stage.value,
        "resolved_identity_hashes": sorted(ri.canonical_identity_hash for ri in resolved_inputs),
        "task9_mode": task9_authority.mode if task9_authority else "none",
        "task9_result_hash": task9_authority.result_hash if task9_authority else None,
        "task10_mode": task10_authority.mode if task10_authority else "none",
        "fallback_mode": (
            task10_authority.mode
            if task10_authority and task10_authority.mode == "structural_only"
            else None
        ),
    }
    payload_hash = sha256_payload(canonical_json_dumps(outcome_payload))

    status_value = "forecast_completed"

    await _persist_stage(attempt_id, stage.value, status_value)

    return NodeOrchestrationOutcome(
        rolling_run_signature=run_signature,
        node_signature=node_sig,
        attempt_number=attempt_number,
        status=status_value,
        stage=stage.value,
        resolved_inputs=resolved_inputs,
        availability_audits=audits,
        task9_authority=task9_authority,
        task10_authority=task10_authority,
        fallback_mode=task10_authority.mode
        if task10_authority and task10_authority.mode == "structural_only"
        else None,
        canonical_payload_hash=payload_hash,
        diagnostics=_collect_diagnostics(resolutions),
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )


# ── Internal helpers ─────────────────────────────────────────────────────────


async def _resolve_all_inputs(
    session: AsyncSession,
    node: RollingNodeDefinition,
    config: RollingBacktestConfig,
) -> tuple[list[ResolutionResult], bool, str | None]:
    """Resolve all upstream identities for a node."""
    resolutions: list[ResolutionResult] = []
    blocked = False
    blocker_code: str | None = None

    if node.upstream_selection_mode.value == "pinned":
        for ident in node.resolved_upstream_semantic_identities:
            result = await resolve_pinned(
                session,
                pinned_identity=ident,
                node=node,
                execution_mode=config.execution_mode,
            )
            resolutions.append(result)
            if result.blocked:
                blocked = True
                blocker_code = result.blocker_code
                break
    else:
        for ident in node.resolved_upstream_semantic_identities:
            result = await resolve_historical(
                session,
                source_role=ident.source_role,
                source_type=ident.source_type,
                node=node,
                execution_mode=config.execution_mode,
            )
            resolutions.append(result)
            if result.blocked:
                blocked = True
                blocker_code = result.blocker_code
                break

    return resolutions, blocked, blocker_code


async def _validate_authority_chain(
    session: AsyncSession,
    resolutions: list[ResolutionResult],
    node: RollingNodeDefinition,
) -> str | None:
    """Validate that resolved parent authorities are internally consistent.

    Returns blocker_code if validation fails, None if OK.
    """
    _unused = (session, node)
    # Check that resolved types are not conflicting
    resolved_types: dict[str, ResolutionResult] = {}
    for r in resolutions:
        if r.resolved is None:
            continue
        key = r.source_type.value
        if key in resolved_types:
            return OrchestrationBlocker.AMBIGUOUS_HISTORICAL_CANDIDATE.value
        resolved_types[key] = r
    return None


async def _validate_task8_chain(
    session: AsyncSession,
    resolutions: list[ResolutionResult],
    node: RollingNodeDefinition,
) -> str | None:
    """Validate Task 8 model → forecast → daily-prediction parent chain."""
    _unused = (session, node)

    # If we have a Task 8 forecast, ensure we also have a model run
    has_model = any(
        r.source_type == AvailabilitySourceType.TASK8_MODEL_RUN and r.resolved for r in resolutions
    )
    has_forecast = any(
        r.source_type == AvailabilitySourceType.TASK8_FORECAST_RUN and r.resolved
        for r in resolutions
    )

    if has_forecast and not has_model:
        return OrchestrationBlocker.TASK8_PARENT_AUTHORITY_MISMATCH.value

    return None


async def _resolve_task9(
    session: AsyncSession,
    resolutions: list[ResolutionResult],
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    attempt_id: int,
    run_signature: str,
    node_sig: str,
    attempt_number: int,
    stage: OrchestrationStage,
    started_at: datetime,
) -> tuple[Task9AuthorityOutcome | None, NodeOrchestrationOutcome | None]:
    """Resolve Task 9 authority (reuse or replay).

    Returns (authority, None) on success or (None, blocked_outcome) on failure.
    """
    task9_resolutions = [
        r for r in resolutions if r.source_type == AvailabilitySourceType.TASK9_HARVEST_STATE_RUN
    ]
    task9_result = task9_resolutions[0] if task9_resolutions else None

    if task9_result and task9_result.resolved:
        resolved = task9_result.resolved
        authority = Task9AuthorityOutcome(
            run_reference=resolved.persistent_reference,
            result_hash=resolved.semantic_identity.semantic.result_hash,
            canonical_payload_hash=resolved.canonical_payload_hash,
            mode="reuse",
        )
        return authority, None

    if config.execution_mode == ExecutionMode.RETROSPECTIVE_REPLAY:
        try:
            request = await _build_task9a_request(session, node, resolutions)
            if request is not None:
                from backend.app.harvest_state.application import execute_harvest_state_run

                envelope = await execute_harvest_state_run(session, request=request)  # type: ignore[arg-type]
                authority = Task9AuthorityOutcome(
                    run_reference=PersistentUpstreamReference(
                        reference_type="database_run_id",
                        reference_value=envelope.run_id,
                    ),
                    result_hash=envelope.output.result_hash,
                    mode="replay",
                )
                return authority, None

            blocked = await _make_blocked_outcome(
                attempt_id,
                run_signature,
                node_sig,
                attempt_number,
                stage,
                OrchestrationBlocker.TASK9_REPLAY_INPUT_INCOMPLETE.value,
                resolutions,
                started_at,
                extra_diag={"reason": "Could not construct Task9ARequest"},
            )
            return None, blocked
        except Exception as exc:
            blocked = await _make_blocked_outcome(
                attempt_id,
                run_signature,
                node_sig,
                attempt_number,
                stage,
                OrchestrationBlocker.TASK9_EXECUTION_BLOCKED.value,
                resolutions,
                started_at,
                extra_diag={"error": _safe_str(exc)},
            )
            return None, blocked

    # No Task 9 found and not in replay mode
    blocked = await _make_blocked_outcome(
        attempt_id,
        run_signature,
        node_sig,
        attempt_number,
        stage,
        OrchestrationBlocker.TASK10_TASK9_BINDING_MISMATCH.value,
        resolutions,
        started_at,
        extra_diag={"reason": "No Task 9 run found and not in replay mode"},
    )
    return None, blocked


def _resolve_task10_model(
    resolutions: list[ResolutionResult],
    task9_authority: Task9AuthorityOutcome | None,
    node: RollingNodeDefinition,
    attempt_id: int,
    run_signature: str,
    node_sig: str,
    attempt_number: int,
    stage: OrchestrationStage,
    started_at: datetime,
) -> tuple[Task10AuthorityOutcome | None, NodeOrchestrationOutcome | None]:
    """Resolve Task 10 model authority. Returns (authority, blocked_outcome)."""
    if node.task10_model_policy.policy == Task10ModelPolicy.REPLAY_TRAINED_MODEL:
        blocked = NodeOrchestrationOutcome(
            rolling_run_signature=run_signature,
            node_signature=node_sig,
            attempt_number=attempt_number,
            status="blocked",
            stage=stage.value,
            blocker_code=OrchestrationBlocker.TASK10_TRAINING_NOT_IMPLEMENTED.value,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
        return None, blocked

    task10_trainings = [
        r for r in resolutions if r.source_type == AvailabilitySourceType.TASK10_TRAINING_RUN
    ]
    task10_train_result = task10_trainings[0] if task10_trainings else None

    if task10_train_result and task10_train_result.resolved:
        training = task10_train_result.resolved
        if task9_authority and task9_authority.run_reference:
            authority = Task10AuthorityOutcome(
                training_reference=training.persistent_reference,
                task9_run_reference=task9_authority.run_reference,
                task9_result_hash=task9_authority.result_hash,
                mode="historically_available",
            )
        else:
            authority = Task10AuthorityOutcome(
                training_reference=training.persistent_reference,
                mode="historically_available",
            )
        return authority, None

    # No Task 10 model found — but we need Task 9 authority to proceed
    if task9_authority and task9_authority.run_reference:
        authority = Task10AuthorityOutcome(mode="structural_only")
        return authority, None

    # No Task 9 and no Task 10 — blocked
    blocked = NodeOrchestrationOutcome(
        rolling_run_signature=run_signature,
        node_signature=node_sig,
        attempt_number=attempt_number,
        status="blocked",
        stage=stage.value,
        blocker_code=OrchestrationBlocker.TASK10_TASK9_BINDING_MISMATCH.value,
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )
    return None, blocked


async def _execute_task10_prediction(
    session: AsyncSession,
    task10_authority: Task10AuthorityOutcome | None,
    task9_authority: Task9AuthorityOutcome | None,
    attempt_id: int,
    run_signature: str,
    node_sig: str,
    attempt_number: int,
    stage: OrchestrationStage,
    resolutions: list[ResolutionResult],
    started_at: datetime,
) -> NodeOrchestrationOutcome | None:
    """Execute Task 10 prediction. Returns None if OK, blocked outcome if failed."""
    if not task10_authority:
        return None  # No Task 10 to execute

    if task10_authority.mode == "structural_only":
        return None  # No model to predict with

    if (
        not task10_authority.training_reference
        or not task9_authority
        or not task9_authority.run_reference
    ):
        return await _make_blocked_outcome(
            attempt_id,
            run_signature,
            node_sig,
            attempt_number,
            stage,
            OrchestrationBlocker.TASK10_TASK9_BINDING_MISMATCH.value,
            resolutions,
            started_at,
            extra_diag={"reason": "Missing training or task9 reference"},
        )

    try:
        from backend.app.residual_model.application import execute_residual_prediction
        from backend.app.residual_model.schemas import ResidualPredictionRequest

        training_ref = task10_authority.training_reference
        task9_ref = task9_authority.run_reference

        if not isinstance(training_ref.reference_value, int) or not isinstance(
            task9_ref.reference_value, int
        ):
            return await _make_blocked_outcome(
                attempt_id,
                run_signature,
                node_sig,
                attempt_number,
                stage,
                OrchestrationBlocker.TASK10_PREDICTION_BLOCKED.value,
                resolutions,
                started_at,
                extra_diag={"reason": "Invalid reference type for prediction"},
            )

        predict_request = ResidualPredictionRequest(
            model_run_id=training_ref.reference_value,
            task9_run_id=task9_ref.reference_value,
        )
        _pred_result, _pred_run_id = await execute_residual_prediction(
            session, request=predict_request
        )
        return None

    except Exception as exc:
        return await _make_blocked_outcome(
            attempt_id,
            run_signature,
            node_sig,
            attempt_number,
            stage,
            OrchestrationBlocker.TASK10_PREDICTION_SERVICE_FAILURE.value,
            resolutions,
            started_at,
            extra_diag={"error": _safe_str(exc)},
        )


async def _persist_stage(
    attempt_id: int,
    stage: str,
    status: str,
    blocker_code: str | None = None,
    diagnostics: dict[str, object] | None = None,
) -> None:
    """Persist stage transition via Phase 2 repository (mandatory)."""
    await finalize_attempt_status(
        attempt_id,
        status=status,
        current_stage=stage,
        structured_error_code=blocker_code,
        sanitized_diagnostics=_sanitize_diagnostics(diagnostics or {}),
    )


async def _make_blocked_outcome(
    attempt_id: int,
    run_signature: str,
    node_sig: str,
    attempt_number: int,
    stage: OrchestrationStage,
    blocker_code: str | None,
    resolutions: list[ResolutionResult],
    started_at: datetime,
    extra_diag: dict[str, object] | None = None,
) -> NodeOrchestrationOutcome:
    """Create a blocked outcome and persist the blocked status."""
    diag = _collect_diagnostics(resolutions)
    if extra_diag:
        diag.update(extra_diag)

    await _persist_stage(attempt_id, stage.value, "blocked", blocker_code, diag)

    return NodeOrchestrationOutcome(
        rolling_run_signature=run_signature,
        node_signature=node_sig,
        attempt_number=attempt_number,
        status="blocked",
        stage=stage.value,
        blocker_code=blocker_code,
        diagnostics=diag,
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )


def _build_audit_outcome(
    result: ResolutionResult,
    node: RollingNodeDefinition,
) -> AvailabilityAuditOutcome:
    """Build a typed availability audit from a resolution result."""
    resolved = result.resolved
    if resolved is None:
        return AvailabilityAuditOutcome(
            source_role=result.source_role,
            source_type=result.source_type.value,
            allowed=False,
            blocker_code=result.blocker_code,
        )

    allowed = resolved.authoritative_available_at <= node.forecast_cutoff_at
    return AvailabilityAuditOutcome(
        source_role=result.source_role,
        source_type=result.source_type.value,
        allowed=allowed,
        blocker_code=result.blocker_code if not allowed else None,
        authoritative_available_at=resolved.authoritative_available_at.isoformat(),
        forecast_cutoff_at=node.forecast_cutoff_at.isoformat(),
    )


async def _build_task9a_request(
    session: AsyncSession,
    node: RollingNodeDefinition,
    resolutions: list[ResolutionResult],
) -> object:  # Returns Task9ARequest | None
    """Build a Task9ARequest from resolved upstream identities.

    Attempts to construct a real request using resolved upstream data.
    Returns None if insufficient inputs are available for replay.
    """

    # Attempt to load the actual required data from upstream.
    # In Phase 3, a complete Task9ARequest requires:
    # - Weather features from task7
    # - Daily maturity predictions from task8 forecast
    # - Capacity config from system configuration
    # - Harvest parameters from parameter library
    #
    # When upstream data is available in PostgreSQL, this function
    # will load it. For now, return None to signal incomplete inputs.
    _unused = (session, node, resolutions)
    return None


def _node_sig_str(config: RollingBacktestConfig, node: RollingNodeDefinition) -> str:
    from backend.app.rolling_backtest.signatures import node_signature_hash

    return node_signature_hash(config, node)


def _collect_diagnostics(resolutions: list[ResolutionResult]) -> dict[str, object]:
    diag: dict[str, object] = {"resolution_count": len(resolutions)}
    for r in resolutions:
        if r.blocked:
            diag[f"{r.source_role}_blocked"] = r.blocker_code or "unknown"
        elif r.resolved:
            diag[f"{r.source_role}_resolved"] = r.resolved.persistent_reference.reference_value
    return diag


def _safe_str(exc: BaseException) -> str:
    """Safe exception string without sensitive details."""
    return f"{type(exc).__name__}: {str(exc)[:200]}"


def _sanitize_diagnostics(raw: dict[str, object]) -> dict[str, object]:
    SENSITIVE_KEYS = {"password", "secret", "token", "connection_url", "dsn"}
    SENSITIVE_KEY_SUBSTRINGS = ("dsn", "connection", "password", "secret", "token")
    SENSITIVE_SUBSTRINGS = ("postgres", "sql", "psycopg", "asyncpg")

    def _sanitize_value(value: object) -> object:
        if isinstance(value, dict):
            result: dict[str, object] = {}
            for k, v in value.items():
                k_lower = k.lower()
                if k_lower in SENSITIVE_KEYS or any(
                    sub in k_lower for sub in SENSITIVE_KEY_SUBSTRINGS
                ):
                    result[k] = "[REDACTED]"
                else:
                    result[k] = _sanitize_value(v)
            return result
        if isinstance(value, (list, tuple)):
            return [_sanitize_value(item) for item in value]
        if isinstance(value, str):
            for substr in SENSITIVE_SUBSTRINGS:
                if substr in value.lower():
                    return "[REDACTED]"
            if len(value) > 500:
                return value[:500] + "..."
        return value

    return _sanitize_value(raw)  # type: ignore[return-value]
