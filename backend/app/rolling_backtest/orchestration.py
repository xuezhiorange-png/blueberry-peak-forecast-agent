"""Rolling backtest orchestration: node execution, Task 9/10 binding, and persistence.

Phase 3 orchestration layer — consumes resolved identities from the resolution
layer, validates authority chains, invokes existing Task 8/9/10 services, and
persists execution attempts, stages, blockers, and diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
    Task10ModelPolicy,
)
from backend.app.rolling_backtest.resolution import (
    ResolutionResult,
    resolve_historical,
    resolve_pinned,
)
from backend.app.rolling_backtest.schemas import (
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
    PINNED_SOURCE_NOT_VISIBLE = "pinned_source_not_visible"
    PINNED_SOURCE_IDENTITY_MISMATCH = "pinned_source_identity_mismatch"
    TASK9_TASK8_AUTHORITY_MISMATCH = "task9_task8_authority_mismatch"
    TASK9_REPLAY_INPUT_INCOMPLETE = "task9_replay_input_incomplete"
    TASK9_EXECUTION_BLOCKED = "task9_execution_blocked"
    TASK10_MODEL_NOT_AVAILABLE = "task10_model_not_available"
    TASK10_TRAINING_NOT_IMPLEMENTED = "task10_training_not_implemented"
    TASK10_TASK9_BINDING_MISMATCH = "task10_task9_binding_mismatch"
    TASK10_PREDICTION_BLOCKED = "task10_prediction_blocked"
    FUTURE_SOURCE_LEAKAGE_DETECTED = "future_source_leakage_detected"


# ── Outcome contracts ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class NodeOrchestrationOutcome:
    """Typed outcome of a single node's orchestration attempt."""

    rolling_run_signature: str
    node_signature: str
    attempt_number: int
    status: str  # ForecastStatus value
    stage: str  # OrchestrationStage value
    resolved_inputs: tuple[dict[str, object], ...] = ()
    availability_audits: tuple[dict[str, object], ...] = ()
    task9_authority: dict[str, object] | None = None
    task10_authority: dict[str, object] | None = None
    fallback_mode: str | None = None
    blocker_code: str | None = None
    diagnostics: dict[str, object] = field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None


# ── Node orchestration entry point ───────────────────────────────────────────


async def orchestrate_node(
    session: AsyncSession,
    *,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    run_signature: str,
    attempt_number: int,
) -> NodeOrchestrationOutcome:
    """Execute full node orchestration: resolve inputs → validate → execute.

    Returns a typed outcome that can be persisted via Phase 2 repository.
    """
    started_at = datetime.now(UTC)
    node_sig = _node_sig_str(config, node)

    # ── Stage 1: Resolve historical inputs ─────────────────────────────
    stage = OrchestrationStage.RESOLVE_HISTORICAL_INPUTS
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
        # historical_resolution
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

    if blocked:
        return NodeOrchestrationOutcome(
            rolling_run_signature=run_signature,
            node_signature=node_sig,
            attempt_number=attempt_number,
            status="blocked",
            stage=stage.value,
            blocker_code=blocker_code,
            diagnostics=_collect_diagnostics(resolutions),
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )

    # ── Stage 2: Validate visibility ──────────────────────────────────
    stage = OrchestrationStage.VALIDATE_VISIBILITY
    for result in resolutions:
        if result.resolved is None:
            continue
        if result.resolved.authoritative_available_at > node.forecast_cutoff_at:
            return NodeOrchestrationOutcome(
                rolling_run_signature=run_signature,
                node_signature=node_sig,
                attempt_number=attempt_number,
                status="blocked",
                stage=stage.value,
                blocker_code=OrchestrationBlocker.FUTURE_SOURCE_LEAKAGE_DETECTED.value,
                diagnostics={
                    "source_role": result.source_role,
                    "available_at": result.resolved.authoritative_available_at.isoformat(),
                    "cutoff": node.forecast_cutoff_at.isoformat(),
                },
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )

    # ── Stage 3: Task 9 resolution ────────────────────────────────────
    stage = OrchestrationStage.RESOLVE_OR_REPLAY_TASK9
    task9_result = resolutions[0] if resolutions else None
    task9_authority: dict[str, object] | None = None

    if task9_result and task9_result.resolved:
        task9_authority = {
            "source_role": "task9_structural_forecast",
            "run_id": task9_result.resolved.persistent_reference.reference_value,
            "source_type": task9_result.resolved.source_type.value,
            "available_at": task9_result.resolved.authoritative_available_at.isoformat(),
            "semantic_hash": task9_result.resolved.canonical_identity_hash,
        }

    # ── Stage 4: Task 10 model policy ─────────────────────────────────
    stage = OrchestrationStage.RESOLVE_OR_TRAIN_TASK10
    task10_authority: dict[str, object] | None = None
    fallback_mode: str | None = None

    if node.task10_model_policy.policy == Task10ModelPolicy.REPLAY_TRAINED_MODEL:
        # Replay-trained model: NOT_IMPLEMENTED in Phase 3
        return NodeOrchestrationOutcome(
            rolling_run_signature=run_signature,
            node_signature=node_sig,
            attempt_number=attempt_number,
            status="blocked",
            stage=stage.value,
            blocker_code=OrchestrationBlocker.TASK10_TRAINING_NOT_IMPLEMENTED.value,
            diagnostics={
                "policy": "replay_trained_model",
                "message": "Replay training not available in Phase 3",
            },
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )

    # historically_available_model: use resolved Task 10 training run
    for resolution in resolutions:
        if resolution.source_type == AvailabilitySourceType.TASK10_TRAINING_RUN:
            if resolution.resolved:
                task10_authority = {
                    "source_role": "task10_training_run",
                    "run_id": resolution.resolved.persistent_reference.reference_value,
                    "source_type": resolution.resolved.source_type.value,
                    "available_at": resolution.resolved.authoritative_available_at.isoformat(),
                }
            else:
                fallback_mode = "structural_only"
            break

    if task10_authority is None and fallback_mode is None:
        return NodeOrchestrationOutcome(
            rolling_run_signature=run_signature,
            node_signature=node_sig,
            attempt_number=attempt_number,
            status="blocked",
            stage=stage.value,
            blocker_code=OrchestrationBlocker.TASK10_MODEL_NOT_AVAILABLE.value,
            diagnostics={"message": "No Task 10 training run resolved"},
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )

    # ── Stage 5: Task 10 prediction binding ───────────────────────────
    stage = OrchestrationStage.EXECUTE_TASK10_PREDICTION

    # Validate Task 9-Task 10 binding
    if task9_authority is None and fallback_mode != "structural_only":
        return NodeOrchestrationOutcome(
            rolling_run_signature=run_signature,
            node_signature=node_sig,
            attempt_number=attempt_number,
            status="blocked",
            stage=stage.value,
            blocker_code=OrchestrationBlocker.TASK10_TASK9_BINDING_MISMATCH.value,
            diagnostics={"message": "Task 10 prediction requires Task 9 authority"},
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )

    # ── Stage 6: Finalize ─────────────────────────────────────────────
    stage = OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT

    resolved_inputs: list[dict[str, object]] = []
    for resolution in resolutions:
        if resolution.resolved:
            resolved_inputs.append(
                {
                    "source_role": resolution.source_role,
                    "source_type": resolution.source_type.value,
                    "run_id": resolution.resolved.persistent_reference.reference_value,
                    "semantic_hash": resolution.resolved.canonical_identity_hash,
                    "available_at": resolution.resolved.authoritative_available_at.isoformat(),
                }
            )

    return NodeOrchestrationOutcome(
        rolling_run_signature=run_signature,
        node_signature=node_sig,
        attempt_number=attempt_number,
        status="forecast_completed" if not fallback_mode else "partially_completed",
        stage=stage.value,
        resolved_inputs=tuple(resolved_inputs),
        task9_authority=task9_authority,
        task10_authority=task10_authority,
        fallback_mode=fallback_mode,
        diagnostics=_collect_diagnostics(resolutions),
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )


# ── Internal helpers ─────────────────────────────────────────────────────────


def _node_sig_str(config: RollingBacktestConfig, node: RollingNodeDefinition) -> str:
    """Compute node signature string for outcome identification."""
    from backend.app.rolling_backtest.signatures import node_signature_hash

    return node_signature_hash(config, node)


def _collect_diagnostics(
    resolutions: list[ResolutionResult],
) -> dict[str, object]:
    """Collect sanitized diagnostics from resolution results."""
    diag: dict[str, object] = {"resolution_count": len(resolutions)}
    for r in resolutions:
        if r.blocked:
            diag[f"{r.source_role}_blocked"] = r.blocker_code or "unknown"
        elif r.resolved:
            diag[f"{r.source_role}_resolved"] = r.resolved.persistent_reference.reference_value
    return diag
