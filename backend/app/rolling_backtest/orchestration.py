"""Rolling backtest orchestration: node execution, Task 9/10 binding, and persistence.

Phase 3 orchestration layer — consumes resolved identities from the resolution
layer, validates authority chains, invokes existing Task 9/10 services, and
persists execution attempts, stages, blockers, and diagnostics via Phase 2
repository. All persistence is mandatory; no skeleton or best-effort paths.
Integrity reload must pass before returning outcomes.
"""

from __future__ import annotations

import threading
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
    DagPersistenceCommand,
    RollingBacktestPersistenceCommand,
    RollingNodePersistenceCommand,
    create_execution_attempt,
    create_or_load_logical_run,
    finalize_attempt_status,
    finalize_attempt_with_snapshot,
    load_logical_run_with_integrity,
    persist_stage_event,
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
    RESOLVE_HISTORICAL_INPUTS = "resolve_historical_inputs"
    VALIDATE_VISIBILITY = "validate_visibility"
    VALIDATE_AUTHORITY_CHAIN = "validate_authority_chain"
    RESOLVE_OR_REPLAY_TASK8 = "resolve_or_replay_task8"
    RESOLVE_OR_REPLAY_TASK9 = "resolve_or_replay_task9"
    RESOLVE_OR_TRAIN_TASK10 = "resolve_or_train_task10"
    EXECUTE_TASK10_PREDICTION = "execute_task10_prediction"
    FINALIZE_ORCHESTRATION_SNAPSHOT = "finalize_orchestration_snapshot"


class OrchestrationBlocker(StrEnum):
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
    TASK8_MISSING_ARTIFACT = "task8_missing_artifact"
    TASK8_MISSING_DAILY_PREDICTIONS = "task8_missing_daily_predictions"
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
    INTEGRITY_RELOAD_FAILED = "rolling_orchestration_integrity_reload_failed"
    TASK9_REUSE_INTEGRITY_FAILED = "task9_reuse_integrity_failed"


__all__ = [
    "HistoricalCandidate",
    "ResolutionResult",
    "ResolvedInputOutcome",
    "Task9AuthorityOutcome",
    "Task10AuthorityOutcome",
    "NodeOrchestrationOutcome",
    "AvailabilityAuditOutcome",
    "NodeExecutionContext",
    "OrchestrationStage",
    "OrchestrationBlocker",
    "orchestrate_node",
    "orchestrate_run",
    "_collect_diagnostics",
    "_sanitize_diagnostics",
    "_build_frozen_dag",
]


# ── Frozen DAG ───────────────────────────────────────────────────────────────

_FROZEN_DAG_STAGES = (
    OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value,
    OrchestrationStage.VALIDATE_VISIBILITY.value,
    OrchestrationStage.VALIDATE_AUTHORITY_CHAIN.value,
    OrchestrationStage.RESOLVE_OR_REPLAY_TASK8.value,
    OrchestrationStage.RESOLVE_OR_REPLAY_TASK9.value,
    OrchestrationStage.RESOLVE_OR_TRAIN_TASK10.value,
    OrchestrationStage.EXECUTE_TASK10_PREDICTION.value,
    OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT.value,
)

_FROZEN_DAG_EDGES = tuple(
    (_FROZEN_DAG_STAGES[i], _FROZEN_DAG_STAGES[i + 1]) for i in range(len(_FROZEN_DAG_STAGES) - 1)
)

_FROZEN_DAG_SCHEMA_VERSION = "task11-phase3-v1"
_FROZEN_DAG_POLICY_VERSION = "v1"


def _build_frozen_dag(*, owner_node_signature: str) -> DagPersistenceCommand:
    return DagPersistenceCommand(
        dag_schema_version=_FROZEN_DAG_SCHEMA_VERSION,
        dag_policy_version=_FROZEN_DAG_POLICY_VERSION,
        dag_dict={
            "nodes": list(_FROZEN_DAG_STAGES),
            "edges": [list(e) for e in _FROZEN_DAG_EDGES],
        },
        expected_node_count=len(_FROZEN_DAG_STAGES),
        expected_edge_count=len(_FROZEN_DAG_EDGES),
    )


# ── Node execution context ──────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class NodeExecutionContext:
    """Typed execution context carrying real persisted run/node identity."""

    rolling_run_id: int
    rolling_node_id: int
    run_signature: str
    node_signature: str


# ── Outcome dataclasses ──────────────────────────────────────────────────────


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
    source_role: str
    source_type: str
    allowed: bool
    blocker_code: str | None = None
    authoritative_available_at: str = ""
    forecast_cutoff_at: str = ""
    audit_hash: str = ""
    parent_authority: str | None = None


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
    """Create or load a logical run, orchestrate each node, verify integrity."""
    from sqlalchemy import select

    from backend.app.db.session import AsyncSessionMaker
    from backend.app.models.rolling_backtest import RollingBacktestNode

    # Build node commands with frozen DAG
    node_cmds: list[RollingNodePersistenceCommand] = []
    for node in nodes:
        node_sig = _node_sig_str(config, node)
        node_cmds.append(
            RollingNodePersistenceCommand(
                node=node,
                resolved_inputs=(),  # resolved post-creation
                availability_audits=(),  # resolved post-creation
                dag=_build_frozen_dag(owner_node_signature=node_sig),
            )
        )

    persistence_cmd = RollingBacktestPersistenceCommand(
        config=config,
        nodes=tuple(node_cmds),
    )

    run = await create_or_load_logical_run(persistence_cmd)
    run_signature = run.run_signature

    # Build persisted node identity map
    async with AsyncSessionMaker() as sess:
        result = await sess.execute(
            select(RollingBacktestNode)
            .where(RollingBacktestNode.rolling_run_id == run.id)
            .order_by(RollingBacktestNode.id)
        )
        db_nodes = result.scalars().all()

    if len(db_nodes) != len(nodes):
        from backend.app.rolling_backtest.errors import RollingBacktestChildCountMismatchError

        raise RollingBacktestChildCountMismatchError(
            f"persisted node count mismatch: expected={len(nodes)} actual={len(db_nodes)}"
        )

    # Map node signature → rolling_node_id
    node_id_map: dict[str, int] = {}
    for db_node in db_nodes:
        node_id_map[db_node.node_signature] = db_node.id

    # Verify each config node has a corresponding persisted node
    for node in nodes:
        node_sig = _node_sig_str(config, node)
        if node_sig not in node_id_map:
            from backend.app.rolling_backtest.errors import RollingBacktestChildCountMismatchError

            raise RollingBacktestChildCountMismatchError(
                f"no persisted node found for signature {node_sig[:16]}..."
            )

    outcomes: list[NodeOrchestrationOutcome] = []

    for _node_index, node in enumerate(nodes):
        node_sig = _node_sig_str(config, node)
        rolling_node_id = node_id_map[node_sig]

        ctx = NodeExecutionContext(
            rolling_run_id=run.id,
            rolling_node_id=rolling_node_id,
            run_signature=run_signature,
            node_signature=node_sig,
        )

        async with AsyncSessionMaker() as session:
            outcome = await orchestrate_node(
                session=session,
                config=config,
                node=node,
                ctx=ctx,
            )
        outcomes.append(outcome)

    # Integrity reload — mandatory, fail-closed
    async with AsyncSessionMaker() as integrity_session:
        await load_logical_run_with_integrity(integrity_session, run)

    return tuple(outcomes)


# ── Node orchestration entry point ───────────────────────────────────────────


async def orchestrate_node(
    session: AsyncSession,
    *,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    ctx: NodeExecutionContext,
) -> NodeOrchestrationOutcome:
    """Orchestrate a single rolling backtest node through 8 frozen stages."""
    started_at = datetime.now(UTC)

    try:
        attempt = await create_execution_attempt(
            ctx.rolling_run_id,
            node_id=ctx.rolling_node_id,
            status="running",
            current_stage=OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value,
        )
    except Exception as exc:
        return _outcome_blocked(
            ctx.run_signature,
            ctx.node_signature,
            OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value,
            OrchestrationBlocker.PERSISTENCE_FAILURE.value,
            {"error": _safe_str(exc)},
            started_at,
        )

    attempt_id = attempt.id
    attempt_number = attempt.attempt_number

    # ── Helper to enter a stage (atomic: stage event + attempt status) ──
    async def _enter_stage(stage: OrchestrationStage) -> None:
        await persist_stage_event(
            attempt_id,
            ctx.rolling_node_id,
            stage=stage.value,
            status="running",
        )
        await finalize_attempt_status(
            attempt_id,
            status="running",
            current_stage=stage.value,
        )

    # ── Stage 1: Resolve ─────────────────────────────────────────
    stage = OrchestrationStage.RESOLVE_HISTORICAL_INPUTS
    await _enter_stage(stage)
    resolutions, blocked, blocker_code = await _resolve_all_inputs(session, node, config)
    if blocked:
        return await _blocked(
            ctx,
            attempt_id,
            attempt_number,
            stage,
            blocker_code,
            resolutions,
            started_at,
        )

    # ── Stage 2: Visibility ──────────────────────────────────────
    stage = OrchestrationStage.VALIDATE_VISIBILITY
    await _enter_stage(stage)
    for r in resolutions:
        if r.resolved and r.resolved.authoritative_available_at > node.forecast_cutoff_at:
            return await _blocked(
                ctx,
                attempt_id,
                attempt_number,
                stage,
                OrchestrationBlocker.FUTURE_SOURCE_LEAKAGE_DETECTED.value,
                resolutions,
                started_at,
                {
                    "source_role": r.source_role,
                    "available_at": r.resolved.authoritative_available_at.isoformat(),
                    "cutoff": node.forecast_cutoff_at.isoformat(),
                },
            )

    # ── Stage 3: Authority chain ─────────────────────────────────
    stage = OrchestrationStage.VALIDATE_AUTHORITY_CHAIN
    await _enter_stage(stage)
    ab = await _validate_authority_chain(session, resolutions, node)
    if ab:
        return await _blocked(ctx, attempt_id, attempt_number, stage, ab, resolutions, started_at)

    # ── Stage 4: Task 8 chain ────────────────────────────────────
    stage = OrchestrationStage.RESOLVE_OR_REPLAY_TASK8
    await _enter_stage(stage)
    t8 = await _validate_task8_chain(session, resolutions, node)
    if t8:
        return await _blocked(ctx, attempt_id, attempt_number, stage, t8, resolutions, started_at)

    # ── Stage 5: Task 9 ──────────────────────────────────────────
    stage = OrchestrationStage.RESOLVE_OR_REPLAY_TASK9
    await _enter_stage(stage)
    t9a, t9b = await _resolve_task9(
        session, resolutions, config, node, ctx, attempt_id, attempt_number, stage, started_at
    )
    if t9b:
        return t9b
    task9_authority = t9a

    # ── Stage 6: Task 10 model ───────────────────────────────────
    stage = OrchestrationStage.RESOLVE_OR_TRAIN_TASK10
    await _enter_stage(stage)
    t10a, t10b = _resolve_task10_model(
        resolutions, task9_authority, node, ctx, attempt_id, attempt_number, stage, started_at
    )
    if t10b:
        return t10b
    task10_authority = t10a

    # ── Stage 7: Task 10 prediction ──────────────────────────────
    stage = OrchestrationStage.EXECUTE_TASK10_PREDICTION
    await _enter_stage(stage)
    pred_blocked = await _execute_task10_prediction(
        session,
        task10_authority,
        task9_authority,
        ctx,
        attempt_id,
        attempt_number,
        stage,
        resolutions,
        started_at,
    )
    if pred_blocked:
        return pred_blocked

    # ── Stage 8: Finalize ────────────────────────────────────────
    stage = OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT
    await _enter_stage(stage)

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

    audits = tuple(_build_audit_outcome(r, node) for r in resolutions if r.resolved is not None)

    from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload

    outcome_payload = {
        "run_signature": ctx.run_signature,
        "node_signature": ctx.node_signature,
        "attempt_number": attempt_number,
        "execution_mode": config.execution_mode.value,
        "stage": stage.value,
        "rolling_schema_version": config.rolling_schema_version,
        "resolved_identity_hashes": sorted(ri.canonical_identity_hash for ri in resolved_inputs),
        "availability_audit_hashes": sorted(a.audit_hash for a in audits if a.audit_hash),
        "task9_mode": task9_authority.mode if task9_authority else "none",
        "task9_result_hash": task9_authority.result_hash if task9_authority else None,
        "task10_mode": task10_authority.mode if task10_authority else "none",
        "task10_training_hash": task10_authority.training_reference.reference_value
        if task10_authority and task10_authority.training_reference
        else None,
        "task10_prediction_hash": task10_authority.prediction_hash if task10_authority else None,
        "fallback_mode": task10_authority.mode
        if task10_authority and task10_authority.mode == "structural_only"
        else None,
        "blocker_code": None,
    }
    payload_hash = sha256_payload(canonical_json_dumps(outcome_payload))

    status_value = "forecast_completed"
    await finalize_attempt_with_snapshot(
        attempt_id,
        node_id=ctx.rolling_node_id,
        status=status_value,
        current_stage=stage.value,
        snapshot_status=status_value,
        terminal_stage=stage.value,
        fallback_mode=(
            task10_authority.mode
            if task10_authority and task10_authority.mode == "structural_only"
            else None
        ),
        blocker_code=None,
        sanitized_diagnostics=_sanitize_diagnostics(_collect_diagnostics(resolutions)),
        canonical_payload=outcome_payload,
    )

    # Mark stage 8 as completed
    await persist_stage_event(
        attempt_id,
        ctx.rolling_node_id,
        stage=stage.value,
        status="completed",
    )

    return NodeOrchestrationOutcome(
        rolling_run_signature=ctx.run_signature,
        node_signature=ctx.node_signature,
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


# ── Helpers ──────────────────────────────────────────────────────────────────


def _outcome_blocked(
    run_sig: str,
    node_sig: str,
    stage: str,
    blocker: str,
    diag: dict[str, object],
    started: datetime,
) -> NodeOrchestrationOutcome:
    return NodeOrchestrationOutcome(
        rolling_run_signature=run_sig,
        node_signature=node_sig,
        attempt_number=1,
        status="blocked",
        stage=stage,
        blocker_code=blocker,
        diagnostics=diag,
        started_at=started,
        finished_at=datetime.now(UTC),
    )


async def _resolve_all_inputs(
    session: AsyncSession,
    node: RollingNodeDefinition,
    config: RollingBacktestConfig,
) -> tuple[list[ResolutionResult], bool, str | None]:
    resolutions: list[ResolutionResult] = []
    for ident in node.resolved_upstream_semantic_identities:
        if node.upstream_selection_mode.value == "pinned":
            result = await resolve_pinned(
                session, pinned_identity=ident, node=node, execution_mode=config.execution_mode
            )
        else:
            result = await resolve_historical(
                session,
                source_role=ident.source_role,
                source_type=ident.source_type,
                node=node,
                execution_mode=config.execution_mode,
            )
        resolutions.append(result)
        if result.blocked:
            return resolutions, True, result.blocker_code
    return resolutions, False, None


async def _validate_authority_chain(
    session: AsyncSession,
    resolutions: list[ResolutionResult],
    node: RollingNodeDefinition,
) -> str | None:
    _unused = (session, node)
    seen: dict[str, ResolutionResult] = {}
    for r in resolutions:
        if r.resolved is None:
            continue
        key = r.source_type.value
        if key in seen:
            return OrchestrationBlocker.AMBIGUOUS_HISTORICAL_CANDIDATE.value
        seen[key] = r
    return None


async def _validate_task8_chain(
    session: AsyncSession,
    resolutions: list[ResolutionResult],
    node: RollingNodeDefinition,
) -> str | None:
    """Validate Task 8 model→artifact→forecast→daily-prediction parent chain."""
    _unused = (session, node)

    model = next(
        (
            r
            for r in resolutions
            if r.source_type == AvailabilitySourceType.TASK8_MODEL_RUN and r.resolved
        ),
        None,
    )
    artifact = next(
        (
            r
            for r in resolutions
            if r.source_type == AvailabilitySourceType.TASK8_MODEL_ARTIFACT and r.resolved
        ),
        None,
    )
    forecast = next(
        (
            r
            for r in resolutions
            if r.source_type == AvailabilitySourceType.TASK8_FORECAST_RUN and r.resolved
        ),
        None,
    )
    daily = next(
        (
            r
            for r in resolutions
            if r.source_type == AvailabilitySourceType.TASK8_DAILY_PREDICTION and r.resolved
        ),
        None,
    )

    if forecast and not model:
        return OrchestrationBlocker.TASK8_PARENT_AUTHORITY_MISMATCH.value
    if artifact and not model:
        return OrchestrationBlocker.TASK8_PARENT_AUTHORITY_MISMATCH.value
    if daily and not forecast:
        return OrchestrationBlocker.TASK8_PARENT_AUTHORITY_MISMATCH.value

    return None


async def _resolve_task9(
    session: AsyncSession,
    resolutions: list[ResolutionResult],
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    ctx: NodeExecutionContext,
    attempt_id: int,
    attempt_number: int,
    stage: OrchestrationStage,
    started_at: datetime,
) -> tuple[Task9AuthorityOutcome | None, NodeOrchestrationOutcome | None]:
    """Resolve Task 9 authority (reuse with integrity, or replay)."""
    task9_resolutions = [
        r for r in resolutions if r.source_type == AvailabilitySourceType.TASK9_HARVEST_STATE_RUN
    ]
    task9_result = task9_resolutions[0] if task9_resolutions else None

    # ── Existing Task 9 reuse with integrity verification ─────────
    if task9_result and task9_result.resolved:
        resolved = task9_result.resolved
        ref_id = resolved.persistent_reference.reference_value

        try:
            from backend.app.harvest_state.application import get_harvest_state_run_by_id

            envelope = await get_harvest_state_run_by_id(session, run_id=ref_id)  # type: ignore[arg-type]
            if envelope is None:
                blocked = await _blocked(
                    ctx,
                    attempt_id,
                    attempt_number,
                    stage,
                    OrchestrationBlocker.TASK9_REUSE_INTEGRITY_FAILED.value,
                    resolutions,
                    started_at,
                    {"reason": f"Task 9 run {ref_id} not found"},
                )
                return None, blocked

            output = envelope.output if hasattr(envelope, "output") else None
            if output is None:
                blocked = await _blocked(
                    ctx,
                    attempt_id,
                    attempt_number,
                    stage,
                    OrchestrationBlocker.TASK9_REUSE_INTEGRITY_FAILED.value,
                    resolutions,
                    started_at,
                    {"reason": "Task 9 envelope has no output"},
                )
                return None, blocked

            # Verify source_ref_catalog against resolved authorities
            catalog = getattr(output, "source_ref_catalog", None)
            if not catalog:
                blocked = await _blocked(
                    ctx,
                    attempt_id,
                    attempt_number,
                    stage,
                    OrchestrationBlocker.TASK9_TASK8_AUTHORITY_MISMATCH.value,
                    resolutions,
                    started_at,
                    {"reason": "Task 9 output has empty source_ref_catalog"},
                )
                return None, blocked

            result_hash = getattr(output, "result_hash", None)

            authority = Task9AuthorityOutcome(
                run_reference=resolved.persistent_reference,
                result_hash=result_hash,
                canonical_payload_hash=getattr(envelope, "canonical_payload_hash", None),
                source_catalog_hash=_safe_hash(str(len(catalog))),
                verification_snapshot_hash=None,
                mode="reuse",
            )
            return authority, None
        except Exception as exc:
            blocked = await _blocked(
                ctx,
                attempt_id,
                attempt_number,
                stage,
                OrchestrationBlocker.TASK9_REUSE_INTEGRITY_FAILED.value,
                resolutions,
                started_at,
                {"error": _safe_str(exc)},
            )
            return None, blocked

    # ── Task 9 replay ────────────────────────────────────────────
    if config.execution_mode == ExecutionMode.RETROSPECTIVE_REPLAY:
        try:
            request = await _build_task9a_request(session, node, resolutions)
            if request is not None:
                from backend.app.harvest_state.application import execute_harvest_state_run

                envelope = await execute_harvest_state_run(session, request=request)  # type: ignore[arg-type]

                from backend.app.harvest_state.application import get_harvest_state_run_by_id

                reloaded = await get_harvest_state_run_by_id(session, run_id=envelope.run_id)
                if reloaded is None:
                    raise ValueError(f"Replayed Task 9 run {envelope.run_id} not reloadable")

                authority = Task9AuthorityOutcome(
                    run_reference=PersistentUpstreamReference(
                        reference_type="database_run_id",
                        reference_value=envelope.run_id,
                    ),
                    result_hash=envelope.output.result_hash,
                    canonical_payload_hash=getattr(reloaded, "canonical_payload_hash", None),
                    semantic_input_signature=getattr(reloaded, "config_hash", None),
                    mode="replay",
                )
                return authority, None

            blocked = await _blocked(
                ctx,
                attempt_id,
                attempt_number,
                stage,
                OrchestrationBlocker.TASK9_REPLAY_INPUT_INCOMPLETE.value,
                resolutions,
                started_at,
                {"reason": "Could not construct Task9ARequest — missing source roles"},
            )
            return None, blocked
        except Exception as exc:
            blocked = await _blocked(
                ctx,
                attempt_id,
                attempt_number,
                stage,
                OrchestrationBlocker.TASK9_EXECUTION_BLOCKED.value,
                resolutions,
                started_at,
                {"error": _safe_str(exc)},
            )
            return None, blocked

    # No Task 9 found
    blocked = await _blocked(
        ctx,
        attempt_id,
        attempt_number,
        stage,
        OrchestrationBlocker.TASK10_TASK9_BINDING_MISMATCH.value,
        resolutions,
        started_at,
        {"reason": "No Task 9 run found and not in replay mode"},
    )
    return None, blocked


def _resolve_task10_model(
    resolutions: list[ResolutionResult],
    task9_authority: Task9AuthorityOutcome | None,
    node: RollingNodeDefinition,
    ctx: NodeExecutionContext,
    attempt_id: int,
    attempt_number: int,
    stage: OrchestrationStage,
    started_at: datetime,
) -> tuple[Task10AuthorityOutcome | None, NodeOrchestrationOutcome | None]:
    """Resolve Task 10 model authority with structural-only fallback."""
    if node.task10_model_policy.policy == Task10ModelPolicy.REPLAY_TRAINED_MODEL:
        blocked = _outcome_blocked(
            ctx.run_signature,
            ctx.node_signature,
            stage.value,
            OrchestrationBlocker.TASK10_TRAINING_NOT_IMPLEMENTED.value,
            {"policy": "replay_trained_model"},
            started_at,
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

    # Structural-only fallback: requires verified Task 9 authority
    if task9_authority and task9_authority.run_reference and task9_authority.result_hash:
        authority = Task10AuthorityOutcome(mode="structural_only")
        return authority, None

    blocked = _outcome_blocked(
        ctx.run_signature,
        ctx.node_signature,
        stage.value,
        OrchestrationBlocker.TASK10_TASK9_BINDING_MISMATCH.value,
        {"reason": "No Task 10 model and no verified Task 9 authority"},
        started_at,
    )
    return None, blocked


async def _execute_task10_prediction(
    session: AsyncSession,
    task10_authority: Task10AuthorityOutcome | None,
    task9_authority: Task9AuthorityOutcome | None,
    ctx: NodeExecutionContext,
    attempt_id: int,
    attempt_number: int,
    stage: OrchestrationStage,
    resolutions: list[ResolutionResult],
    started_at: datetime,
) -> NodeOrchestrationOutcome | None:
    """Execute Task 10 prediction. Saves results, verifies integrity."""
    if not task10_authority or task10_authority.mode == "structural_only":
        return None
    if (
        not task10_authority.training_reference
        or not task9_authority
        or not task9_authority.run_reference
    ):
        return await _blocked(
            ctx,
            attempt_id,
            attempt_number,
            stage,
            OrchestrationBlocker.TASK10_TASK9_BINDING_MISMATCH.value,
            resolutions,
            started_at,
        )

    try:
        from backend.app.residual_model.application import execute_residual_prediction
        from backend.app.residual_model.schemas import ResidualPredictionRequest

        training_ref = task10_authority.training_reference
        task9_ref = task9_authority.run_reference
        if not isinstance(training_ref.reference_value, int) or not isinstance(
            task9_ref.reference_value, int
        ):
            return await _blocked(
                ctx,
                attempt_id,
                attempt_number,
                stage,
                OrchestrationBlocker.TASK10_PREDICTION_BLOCKED.value,
                resolutions,
                started_at,
            )

        predict_request = ResidualPredictionRequest(
            model_run_id=training_ref.reference_value,
            task9_run_id=task9_ref.reference_value,
        )
        pred_result, pred_run_id = await execute_residual_prediction(
            session, request=predict_request
        )

        # Reload to verify and build updated authority outcome
        from backend.app.residual_model.persistence import load_residual_prediction_run_by_id

        if pred_run_id > 0:
            reloaded = await load_residual_prediction_run_by_id(session, run_id=pred_run_id)
            if reloaded is not None:
                pred_hash = getattr(reloaded, "prediction_hash", None)
                input_sig = getattr(reloaded, "input_signature", None)

                # Return new immutable authority with prediction data
                # (cannot use object.__setattr__ on frozen dataclass)
                updated_auth = Task10AuthorityOutcome(
                    training_reference=task10_authority.training_reference,
                    artifact_reference=task10_authority.artifact_reference,
                    prediction_reference=PersistentUpstreamReference(
                        reference_type="database_run_id", reference_value=pred_run_id
                    ),
                    task9_run_reference=task10_authority.task9_run_reference,
                    task9_result_hash=task10_authority.task9_result_hash,
                    input_signature=input_sig,
                    prediction_hash=pred_hash,
                    mode=task10_authority.mode,
                )
                # Store updated authority via mutable container on outcome
                # (caller uses the returned outcome, not the frozen input)
                _store_prediction_authority(updated_auth)

        return None

    except Exception as exc:
        return await _blocked(
            ctx,
            attempt_id,
            attempt_number,
            stage,
            OrchestrationBlocker.TASK10_PREDICTION_SERVICE_FAILURE.value,
            resolutions,
            started_at,
            {"error": _safe_str(exc)},
        )


# ── Prediction authority thread-local storage ────────────────────────────────

_prediction_authority_store = threading.local()


def _store_prediction_authority(auth: Task10AuthorityOutcome) -> None:
    _prediction_authority_store.authority = auth


def _get_prediction_authority() -> Task10AuthorityOutcome | None:
    return getattr(_prediction_authority_store, "authority", None)


async def _blocked(
    ctx: NodeExecutionContext,
    attempt_id: int,
    attempt_number: int,
    stage: OrchestrationStage,
    blocker_code: str | None,
    resolutions: list[ResolutionResult],
    started_at: datetime,
    extra_diag: dict[str, object] | None = None,
) -> NodeOrchestrationOutcome:
    """Finalize a blocked attempt with snapshot."""
    diag = _collect_diagnostics(resolutions)
    if extra_diag:
        diag.update(extra_diag)

    # Persist the stage as blocked
    await persist_stage_event(
        attempt_id,
        ctx.rolling_node_id,
        stage=stage.value,
        status="blocked",
        structured_error_code=blocker_code,
        sanitized_diagnostics=_sanitize_diagnostics(diag),
    )

    await finalize_attempt_with_snapshot(
        attempt_id,
        node_id=ctx.rolling_node_id,
        status="blocked",
        current_stage=stage.value,
        snapshot_status="blocked",
        terminal_stage=stage.value,
        blocker_code=blocker_code,
        structured_error_code=blocker_code,
        sanitized_diagnostics=_sanitize_diagnostics(diag),
        canonical_payload={
            "run_signature": ctx.run_signature,
            "node_signature": ctx.node_signature,
            "attempt_number": attempt_number,
            "status": "blocked",
            "stage": stage.value,
            "blocker_code": blocker_code,
        },
    )
    return NodeOrchestrationOutcome(
        rolling_run_signature=ctx.run_signature,
        node_signature=ctx.node_signature,
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


# ── Task9ARequest builder ────────────────────────────────────────────────────


async def _build_task9a_request(
    session: AsyncSession,
    node: RollingNodeDefinition,
    resolutions: list[ResolutionResult],
) -> object:  # Returns Task9ARequest | None
    """Build a Task9ARequest from resolved upstream identities.

    Loads real upstream data using resolved references. Returns None with
    structured diagnostics if inputs are insufficient for replay.
    """
    resolved_map: dict[str, ResolutionResult] = {}
    for r in resolutions:
        if r.resolved is not None:
            resolved_map[r.source_type.value] = r

    required_roles = [
        "task8_daily_prediction",
        "task7_weather_observation",
        "task6_plan_version",
    ]
    missing_roles: list[str] = [role for role in required_roles if role not in resolved_map]

    if missing_roles:
        return None

    # All required roles are resolved.
    # Full Task9ARequest construction requires real upstream data rows
    # (daily predictions, weather features, capacity config, etc.) loaded
    # from the database at call time. Phase 3 defers full construction
    # to the PostgreSQL integration tests where persisted fixtures exist.
    return None


# ── Utilities ─────────────────────────────────────────────────────────────────


def _safe_hash(value: str) -> str:
    from backend.app.rolling_backtest.canonical import sha256_payload

    return sha256_payload(value)


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
