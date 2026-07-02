"""Unit/contract tests for node orchestration service (Task 11 Phase 1).

Tests the eight-stage DAG orchestration for rolling backtest nodes.
All tests are pure unit tests — no PostgreSQL, no integration mark.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
    ExecutionMode,
    UpstreamSelectionMode,
)
from backend.app.rolling_backtest.node_orchestration import (
    NodeAlreadyFinalizedError,
    PinnedSourceNotFoundError,
    PinnedSourceNotVisibleError,
    Task8ParentAuthorityMismatchError,
    Task9Task8AuthorityMismatchError,
    Task10PredictionNotCompletedError,
    Task10Task9BindingMismatchError,
    UnsupportedExecutionModeError,
    UnsupportedSelectionModeError,
    orchestrate_node,
)
from backend.app.rolling_backtest.orchestration import (
    AvailabilityAuditOutcome,
    NodeOrchestrationOutcome,
    OrchestrationStage,
)
from backend.app.rolling_backtest.persistence import _STAGE_ORDINAL
from backend.app.rolling_backtest.schemas import (
    PersistentUpstreamReference,
    ResolvedUpstreamSemanticIdentity,
    RollingBacktestConfig,
    RollingNodeDefinition,
    UpstreamSemanticIdentityPayload,
)

# Module path for patching
_MOD = "backend.app.rolling_backtest.node_orchestration"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_semantic_payload(
    *,
    semantic_payload_hash: str = "e" * 64,
    input_signature: str = "f" * 64,
    result_hash: str = "a" * 64,
    canonical_payload_hash: str = "b" * 64,
    business_version: str = "v1",
) -> UpstreamSemanticIdentityPayload:
    return UpstreamSemanticIdentityPayload(
        schema_version="task11-upstream-v1",
        display_label="test",
        semantic_payload_hash=semantic_payload_hash,
        input_signature=input_signature,
        result_hash=result_hash,
        canonical_payload_hash=canonical_payload_hash,
        business_version=business_version,
    )


def _make_identity(
    *,
    source_type: AvailabilitySourceType = AvailabilitySourceType.TASK8_FORECAST_RUN,
    source_role: str = "task8_forecast_run",
    semantic_payload_hash: str = "e" * 64,
    input_signature: str = "f" * 64,
    result_hash: str = "a" * 64,
    canonical_payload_hash: str = "b" * 64,
    business_version: str = "v1",
) -> ResolvedUpstreamSemanticIdentity:
    return ResolvedUpstreamSemanticIdentity(
        source_type=source_type,
        source_role=source_role,
        semantic=_make_semantic_payload(
            semantic_payload_hash=semantic_payload_hash,
            input_signature=input_signature,
            result_hash=result_hash,
            canonical_payload_hash=canonical_payload_hash,
            business_version=business_version,
        ),
        persistent_reference=PersistentUpstreamReference(
            reference_type="database_run_id", reference_value=42
        ),
    )


def _make_node_def(
    *,
    selection_mode: UpstreamSelectionMode = UpstreamSelectionMode.PINNED,
    identities: tuple[ResolvedUpstreamSemanticIdentity, ...] | None = None,
) -> RollingNodeDefinition:
    """Build a minimal valid RollingNodeDefinition."""
    if identities is None:
        identities = (
            _make_identity(
                source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
                source_role="task8_forecast_run",
            ),
        )
    return RollingNodeDefinition.model_validate(
        {
            "season_id": 2026,
            "node_key": "march_15",
            "as_of_local_date": "2026-03-15",
            "forecast_cutoff_at": "2026-03-15T04:00:00Z",
            "forecast_start_local_date": "2026-03-16",
            "forecast_end_local_date": "2026-03-31",
            "scope": {
                "destination_factory_ids": {"mode": "include_ids", "ids": [202, 101]},
                "farm_ids": {"mode": "all", "ids": []},
                "subfarm_ids": {"mode": "all", "ids": []},
                "variety_ids": {"mode": "all", "ids": []},
            },
            "upstream_selection_mode": selection_mode.value,
            "forecast_horizon_policy_version": "task11-horizon-v1",
            "timezone": "Asia/Shanghai",
            "task10_model_policy": {
                "policy": "historically_available_model",
                "training_run_semantic_identity": "a" * 64,
                "artifact_semantic_identities": ["b" * 64, "c" * 64],
                "authority_visibility_identity": "d" * 64,
            },
            "resolved_upstream_semantic_identities": [
                {
                    "source_type": ident.source_type.value,
                    "source_role": ident.source_role,
                    "semantic": ident.semantic.model_dump(mode="python"),
                    "persistent_reference": (
                        ident.persistent_reference.model_dump(mode="python")
                        if ident.persistent_reference
                        else None
                    ),
                }
                for ident in identities
            ],
        }
    )


def _make_config(
    *,
    execution_mode: ExecutionMode = ExecutionMode.HISTORICAL_OBSERVED,
    nodes: tuple[RollingNodeDefinition, ...] | None = None,
) -> RollingBacktestConfig:
    if nodes is None:
        nodes = (_make_node_def(),)
    return RollingBacktestConfig.model_validate(
        {
            "rolling_schema_version": "task11-rolling-v1",
            "canonical_serialization_version": "task11-canonical-v1",
            "availability_registry_version": "task11-availability-v1",
            "node_calendar_version": "task11-calendar-v1",
            "forecast_horizon_policy_version": "task11-horizon-v1",
            "upstream_selection_policy_version": "task11-selection-v1",
            "metric_policy_version": "task11-metrics-v1",
            "execution_mode": execution_mode.value,
            "calendar_phase_policy_version": "task11-calendar-phase-v1",
            "cutoff_policy_version": "task11-cutoff-v1",
            "cutoff_timezone": "Asia/Shanghai",
            "cutoff_local_time": "12:00:00",
            "nodes": [node.model_dump(mode="python") for node in nodes],
        }
    )


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_session():
    """Mock AsyncSession for database calls."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def mock_run():
    """Build a mock RollingBacktestRun with valid canonical_payload."""
    run = MagicMock()
    run.id = 1
    run.run_signature = "a" * 64
    config = _make_config()
    run.canonical_payload = config.model_dump(mode="python")
    return run


@pytest.fixture
def mock_node():
    """Build a mock RollingBacktestNode with valid canonical_payload."""
    node = MagicMock()
    node.id = 10
    node.rolling_run_id = 1
    node.status = "pending"
    node.node_signature = "b" * 64
    node.upstream_selection_mode = UpstreamSelectionMode.PINNED
    node_def = _make_node_def()
    node.canonical_payload = node_def.model_dump(mode="python")
    return node


@pytest.fixture
def mock_attempt():
    """Build a mock RollingBacktestAttempt."""
    attempt = MagicMock()
    attempt.id = 100
    attempt.rolling_run_id = 1
    attempt.rolling_node_id = 10
    attempt.attempt_number = 1
    attempt.status = "running"
    attempt.current_stage = "resolve_historical_inputs"
    attempt.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    attempt.finished_at = None
    return attempt


def _run_result_for(obj):
    """Build a mock result that returns obj from scalar_one_or_none()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    return result


def _empty_audit_result():
    """Build a mock result that returns empty list from scalars().all()."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    return result


def _build_session_side_effect(run, node, completed_attempt=None):
    """Build a side_effect for session.execute that routes by model type."""

    def _execute(stmt, *args, **kwargs):
        stmt_str = str(stmt)
        if "RollingBacktestRun" in stmt_str or "rolling_backtest_run" in stmt_str:
            return _run_result_for(run)
        elif "RollingBacktestNode" in stmt_str or "rolling_backtest_node" in stmt_str:
            return _run_result_for(node)
        elif "RollingBacktestAttempt" in stmt_str or "rolling_backtest_attempt" in stmt_str:
            if completed_attempt is not None:
                return _run_result_for(completed_attempt)
            return _empty_audit_result()
        else:
            return _empty_audit_result()

    return _execute


async def _mock_stage_validate_visibility_happy(session, ctx, config, node):
    """Mock stage 2 for happy path: all resolved inputs are visible."""
    for role, outcome in ctx.resolved_inputs.items():
        ctx.availability_audits[role] = AvailabilityAuditOutcome(
            source_role=role,
            source_type=outcome.source_type.value,
            allowed=True,
            blocker_code=None,
            authoritative_available_at=datetime(2026, 3, 14, 4, 0, tzinfo=UTC).isoformat(),
            forecast_cutoff_at=node.forecast_cutoff_at.isoformat(),
            audit_hash="a" * 64,
            parent_authority=None,
        )
    return ctx


# ── Common mock patches for orchestrate_node ─────────────────────────────────


def _make_attempt_mock(attempt_fixture):
    """Build a clean MagicMock for an attempt from fixture data."""
    m = MagicMock()
    m.id = attempt_fixture.id
    m.attempt_number = attempt_fixture.attempt_number
    m.started_at = attempt_fixture.started_at
    m.finished_at = attempt_fixture.finished_at
    return m


def _orchestration_patches(
    *,
    mock_run,
    mock_node,
    mock_attempt,
    stage_validate_visibility=None,
):
    """Return a dict of {short_attr_name: mock_value} for patch.multiple."""
    if stage_validate_visibility is None:
        stage_validate_visibility = _mock_stage_validate_visibility_happy

    attempt_inst = _make_attempt_mock(mock_attempt)

    return {
        "create_execution_attempt": AsyncMock(return_value=attempt_inst),
        "persist_stage_event": AsyncMock(),
        "persist_orchestration_snapshot": AsyncMock(),
        "load_logical_run_with_integrity": AsyncMock(return_value=mock_run),
        "finalize_attempt_status": AsyncMock(return_value=attempt_inst),
        "finalize_attempt_with_snapshot": AsyncMock(return_value=(attempt_inst, MagicMock())),
        "update_run_status_from_attempts": AsyncMock(),
        "_stage_validate_visibility": stage_validate_visibility,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════════════


# ── 1. Happy path ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_historical_observed_pinned_success(mock_session, mock_run, mock_node, mock_attempt):
    """Full eight-stage happy path for historical_observed + pinned."""
    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))
    patches = _orchestration_patches(
        mock_run=mock_run, mock_node=mock_node, mock_attempt=mock_attempt
    )

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(
            mock_session,
            rolling_run_id=mock_run.id,
            rolling_node_id=mock_node.id,
        )

    assert isinstance(outcome, NodeOrchestrationOutcome)
    assert outcome.status == "completed"
    assert outcome.stage == OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT.value
    assert outcome.blocker_code is None
    assert outcome.rolling_run_signature == mock_run.run_signature


# ── 2. Retrospective replay unsupported ──────────────────────────────────────


@pytest.mark.asyncio
async def test_retrospective_replay_unsupported(mock_session):
    """Retrospective replay mode returns blocker."""
    retro_config = _make_config(execution_mode=ExecutionMode.RETROSPECTIVE_REPLAY)

    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = retro_config.model_dump(mode="python")

    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "pending"
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.PINNED
    mock_node.canonical_payload = retro_config.nodes[0].model_dump(mode="python")

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    with pytest.raises(UnsupportedExecutionModeError) as exc_info:
        await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)
    assert exc_info.value.code == "UNSUPPORTED_EXECUTION_MODE"


# ── 3. Historical resolution unsupported ─────────────────────────────────────


@pytest.mark.asyncio
async def test_historical_resolution_unsupported(mock_session):
    """Historical resolution mode returns blocker.

    Note: the ExecutionMode enum currently only has HISTORICAL_OBSERVED and
    RETROSPECTIVE_REPLAY. We test with a config whose execution_mode is
    RETROSPECTIVE_REPLAY to exercise the 'unsupported mode' path, which is
    the same code path a future HISTORICAL_RESOLUTION mode would hit.
    """
    retro_config = _make_config(execution_mode=ExecutionMode.RETROSPECTIVE_REPLAY)

    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = retro_config.model_dump(mode="python")

    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "pending"
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.PINNED
    mock_node.canonical_payload = retro_config.nodes[0].model_dump(mode="python")

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    with pytest.raises(UnsupportedExecutionModeError) as exc_info:
        await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)
    assert exc_info.value.code == "UNSUPPORTED_EXECUTION_MODE"


# ── 4. Node already finalized ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_node_already_finalized(mock_session):
    """Completed node cannot be re-executed."""
    config = _make_config()
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = config.model_dump(mode="python")

    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "completed"
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.PINNED
    mock_node.canonical_payload = config.nodes[0].model_dump(mode="python")

    completed_attempt = MagicMock()
    completed_attempt.id = 100
    completed_attempt.status = "completed"
    mock_session.execute = AsyncMock(
        side_effect=_build_session_side_effect(
            mock_run, mock_node, completed_attempt=completed_attempt
        )
    )

    with pytest.raises(NodeAlreadyFinalizedError) as exc_info:
        await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)
    assert exc_info.value.code == "NODE_ALREADY_FINALIZED"


# ── 5. Pinned source not found ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pinned_source_not_found(mock_session):
    """Missing availability audit blocks orchestration."""
    config = _make_config()
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = config.model_dump(mode="python")

    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "pending"
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.PINNED
    mock_node.canonical_payload = config.nodes[0].model_dump(mode="python")

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    async def _stage2_not_found(session, ctx, config, node):
        raise PinnedSourceNotFoundError(
            "no availability audit for pinned source role=task8_forecast_run"
        )

    mock_attempt = MagicMock()
    mock_attempt.id = 100
    mock_attempt.attempt_number = 1
    mock_attempt.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    mock_attempt.finished_at = None

    patches = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=mock_attempt,
        stage_validate_visibility=_stage2_not_found,
    )

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)

    assert outcome.status == "blocked"
    assert outcome.blocker_code == "PINNED_SOURCE_NOT_FOUND"


# ── 6. Pinned source not visible ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pinned_source_not_visible(mock_session):
    """Blocked audit blocks orchestration."""
    config = _make_config()
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = config.model_dump(mode="python")

    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "pending"
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.PINNED
    mock_node.canonical_payload = config.nodes[0].model_dump(mode="python")

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    async def _stage2_not_visible(session, ctx, config, node):
        raise PinnedSourceNotVisibleError(
            "pinned source role=task8_forecast_run blocked by STATUS_NOT_ALLOWED"
        )

    mock_attempt = MagicMock()
    mock_attempt.id = 100
    mock_attempt.attempt_number = 1
    mock_attempt.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    mock_attempt.finished_at = None

    patches = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=mock_attempt,
        stage_validate_visibility=_stage2_not_visible,
    )

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)

    assert outcome.status == "blocked"
    assert outcome.blocker_code == "PINNED_SOURCE_NOT_VISIBLE"


# ── 7. Task 8 parent authority mismatch ──────────────────────────────────────


@pytest.mark.asyncio
async def test_task8_parent_authority_mismatch(mock_session):
    """Task 8 artifact without model run blocks orchestration."""
    artifact_identity = _make_identity(
        source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
        source_role="task8_model_artifact",
    )
    node_def = _make_node_def(identities=(artifact_identity,))
    config = _make_config(nodes=(node_def,))

    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = config.model_dump(mode="python")

    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "pending"
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.PINNED
    mock_node.canonical_payload = config.nodes[0].model_dump(mode="python")

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    mock_attempt = MagicMock()
    mock_attempt.id = 100
    mock_attempt.attempt_number = 1
    mock_attempt.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    mock_attempt.finished_at = None

    patches = _orchestration_patches(
        mock_run=mock_run, mock_node=mock_node, mock_attempt=mock_attempt
    )

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)

    assert outcome.status == "blocked"
    assert outcome.blocker_code == "TASK8_PARENT_AUTHORITY_MISMATCH"


# ── 8. Task 9 task 8 mismatch ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_task9_task8_mismatch(mock_session):
    """Task 9 frozen identity mismatch blocks orchestration."""
    config = _make_config()
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = config.model_dump(mode="python")

    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "pending"
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.PINNED
    mock_node.canonical_payload = config.nodes[0].model_dump(mode="python")

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    async def _stage5_task9_mismatch(session, ctx, config, node):
        raise Task9Task8AuthorityMismatchError(
            "Task 9 frozen Task 8 identity does not match resolved Task 8"
        )

    mock_attempt = MagicMock()
    mock_attempt.id = 100
    mock_attempt.attempt_number = 1
    mock_attempt.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    mock_attempt.finished_at = None

    patches = _orchestration_patches(
        mock_run=mock_run, mock_node=mock_node, mock_attempt=mock_attempt
    )
    patches["_stage_resolve_task9"] = _stage5_task9_mismatch

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)

    assert outcome.status == "blocked"
    assert outcome.blocker_code == "TASK9_TASK8_AUTHORITY_MISMATCH"


# ── 9. Task 10 task 9 mismatch ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_task10_task9_mismatch(mock_session):
    """Task 10 binding mismatch blocks orchestration."""
    config = _make_config()
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = config.model_dump(mode="python")

    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "pending"
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.PINNED
    mock_node.canonical_payload = config.nodes[0].model_dump(mode="python")

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    async def _stage6_task10_mismatch(session, ctx, config, node):
        raise Task10Task9BindingMismatchError("Task 10 binding does not match Task 9 identity")

    mock_attempt = MagicMock()
    mock_attempt.id = 100
    mock_attempt.attempt_number = 1
    mock_attempt.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    mock_attempt.finished_at = None

    patches = _orchestration_patches(
        mock_run=mock_run, mock_node=mock_node, mock_attempt=mock_attempt
    )
    patches["_stage_resolve_task10"] = _stage6_task10_mismatch

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)

    assert outcome.status == "blocked"
    assert outcome.blocker_code == "TASK10_TASK9_BINDING_MISMATCH"


# ── 10. Task 10 prediction not completed ─────────────────────────────────────


@pytest.mark.asyncio
async def test_task10_prediction_not_completed(mock_session):
    """Missing prediction blocks orchestration."""
    config = _make_config()
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = config.model_dump(mode="python")

    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "pending"
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.PINNED
    mock_node.canonical_payload = config.nodes[0].model_dump(mode="python")

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    async def _stage7_no_prediction(session, ctx, config, node):
        raise Task10PredictionNotCompletedError(
            "Task 10 prediction run is not completed or completed_at missing"
        )

    mock_attempt = MagicMock()
    mock_attempt.id = 100
    mock_attempt.attempt_number = 1
    mock_attempt.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    mock_attempt.finished_at = None

    patches = _orchestration_patches(
        mock_run=mock_run, mock_node=mock_node, mock_attempt=mock_attempt
    )
    patches["_stage_execute_task10_prediction"] = _stage7_no_prediction

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)

    assert outcome.status == "blocked"
    assert outcome.blocker_code == "TASK10_PREDICTION_NOT_COMPLETED"


# ── 11. Sanitized diagnostics ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sanitized_diagnostics(mock_session):
    """Error diagnostics are sanitized — no connection info leaked."""
    config = _make_config()
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = config.model_dump(mode="python")

    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "pending"
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.PINNED
    mock_node.canonical_payload = config.nodes[0].model_dump(mode="python")

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    async def _stage2_sanitized(session, ctx, config, node):
        raise PinnedSourceNotVisibleError(
            "pinned source blocked by STATUS_NOT_ALLOWED; "
            "connection_url=postgresql://user:secret@host/db"
        )

    mock_attempt = MagicMock()
    mock_attempt.id = 100
    mock_attempt.attempt_number = 1
    mock_attempt.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    mock_attempt.finished_at = None

    finalize_mock = AsyncMock(return_value=(mock_attempt, MagicMock()))

    patches = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=mock_attempt,
        stage_validate_visibility=_stage2_sanitized,
    )
    patches["finalize_attempt_with_snapshot"] = finalize_mock

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)

    assert outcome.status == "blocked"
    assert outcome.blocker_code == "PINNED_SOURCE_NOT_VISIBLE"

    # Verify finalize_attempt_with_snapshot was called with sanitized diagnostics
    assert finalize_mock.called
    call_kwargs = finalize_mock.call_args.kwargs
    sanitized = call_kwargs.get("sanitized_diagnostics", {})
    sanitized_str = json.dumps(sanitized, default=str)
    assert "secret" not in sanitized_str.lower()
    assert "postgresql" not in sanitized_str.lower()
    assert "connection" not in sanitized_str.lower()


# ── 12. Full eight-stage completed chain ─────────────────────────────────────


@pytest.mark.asyncio
async def test_full_eight_stage_completed_chain(mock_session, mock_run, mock_node, mock_attempt):
    """Verify all 8 stage events are created for a completed node."""
    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))
    patches = _orchestration_patches(
        mock_run=mock_run, mock_node=mock_node, mock_attempt=mock_attempt
    )

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(
            mock_session,
            rolling_run_id=mock_run.id,
            rolling_node_id=mock_node.id,
        )

    assert outcome.status == "completed"

    # Each stage emits two events (running + completed) → 8 stages × 2 = 16
    persist_stage_call = patches["persist_stage_event"]
    assert persist_stage_call.call_count == 16

    # Verify all 8 stage names appear in the calls
    called_stages = set()
    for call in persist_stage_call.call_args_list:
        stage_value = call.kwargs.get("stage")
        called_stages.add(stage_value)

    expected_stages = {stage.value for stage in OrchestrationStage}
    assert called_stages == expected_stages


# ── 13. Blocked stage has no later events ────────────────────────────────────


@pytest.mark.asyncio
async def test_blocked_stage_has_no_later_events(mock_session):
    """Blocked at stage 2 → no events for stages 3-8."""
    config = _make_config()
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = config.model_dump(mode="python")

    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "pending"
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.PINNED
    mock_node.canonical_payload = config.nodes[0].model_dump(mode="python")

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    async def _stage2_blocked(session, ctx, config, node):
        raise PinnedSourceNotVisibleError("blocked at stage 2")

    mock_attempt = MagicMock()
    mock_attempt.id = 100
    mock_attempt.attempt_number = 1
    mock_attempt.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    mock_attempt.finished_at = None

    patches = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=mock_attempt,
        stage_validate_visibility=_stage2_blocked,
    )

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)

    assert outcome.status == "blocked"

    persist_stage_call = patches["persist_stage_event"]

    # Collect all stages that had events
    called_stages = set()
    for call in persist_stage_call.call_args_list:
        stage_value = call.kwargs.get("stage")
        called_stages.add(stage_value)

    # Only stage 1 (resolve_historical_inputs) and stage 2 (validate_visibility)
    # should have events. Stages 3-8 should NOT.
    later_stages = [
        "validate_authority_chain",
        "resolve_or_replay_task8",
        "resolve_or_replay_task9",
        "resolve_or_train_task10",
        "execute_task10_prediction",
        "finalize_orchestration_snapshot",
    ]
    for blocked_stage in later_stages:
        assert blocked_stage not in called_stages, (
            f"Stage {blocked_stage} should not have events after block at stage 2"
        )


# ── 14. Retry creates new attempt ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_creates_new_attempt(mock_session):
    """Second attempt after blocked has prior_attempt_id set."""
    config = _make_config()
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = config.model_dump(mode="python")

    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "blocked"  # Previously blocked, allows retry
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.PINNED
    mock_node.canonical_payload = config.nodes[0].model_dump(mode="python")

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    second_attempt = MagicMock()
    second_attempt.id = 101
    second_attempt.attempt_number = 2
    second_attempt.started_at = datetime(2026, 3, 15, 5, 0, tzinfo=UTC)
    second_attempt.finished_at = None

    create_fn = AsyncMock(return_value=second_attempt)

    patches = _orchestration_patches(
        mock_run=mock_run, mock_node=mock_node, mock_attempt=second_attempt
    )
    patches["create_execution_attempt"] = create_fn

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)

    assert outcome.status == "completed"
    assert outcome.attempt_number == 2

    # Verify create_execution_attempt was called with correct args
    create_fn.assert_called_once()
    call_args = create_fn.call_args
    # rolling_run_id and rolling_node_id are positional args
    assert call_args.args[0] == 1  # rolling_run_id
    assert call_args.args[1] == 10  # rolling_node_id
    assert call_args.kwargs["status"] == "running"


# ── 15. Cross-node prior attempt rejected ────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_node_prior_attempt_rejected(mock_session):
    """prior_attempt_id from wrong node causes failed status."""
    from backend.app.rolling_backtest.errors import RollingBacktestAttemptConflictError

    config = _make_config()
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = config.model_dump(mode="python")

    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "blocked"
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.PINNED
    mock_node.canonical_payload = config.nodes[0].model_dump(mode="python")

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    async def _create_attempt_conflict(*args, **kwargs):
        raise RollingBacktestAttemptConflictError("attempt 101 prior link crosses node boundary")

    mock_attempt = MagicMock()
    mock_attempt.id = 100
    mock_attempt.attempt_number = 1
    mock_attempt.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    mock_attempt.finished_at = None

    patches = _orchestration_patches(
        mock_run=mock_run, mock_node=mock_node, mock_attempt=mock_attempt
    )
    patches["create_execution_attempt"] = _create_attempt_conflict

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)
    assert outcome.status == "blocked"
    assert "crosses node boundary" in str(outcome.diagnostics.get("error", ""))


# ── 16. Successful node cannot be overwritten ────────────────────────────────


@pytest.mark.asyncio
async def test_successful_node_cannot_be_overwritten(mock_session):
    """Cannot re-run a completed node — verifies NodeAlreadyFinalizedError."""
    config = _make_config()
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = config.model_dump(mode="python")

    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "completed"
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.PINNED
    mock_node.canonical_payload = config.nodes[0].model_dump(mode="python")

    completed_attempt = MagicMock()
    completed_attempt.id = 200
    completed_attempt.status = "completed"
    mock_session.execute = AsyncMock(
        side_effect=_build_session_side_effect(
            mock_run, mock_node, completed_attempt=completed_attempt
        )
    )

    with pytest.raises(NodeAlreadyFinalizedError) as exc_info:
        await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)
    assert exc_info.value.code == "NODE_ALREADY_FINALIZED"


# ── 17. Mixed node status aggregation ────────────────────────────────────────


@pytest.mark.asyncio
async def test_mixed_node_status_aggregation(mock_session):
    """Multiple nodes with different statuses — each handled independently."""
    config = _make_config()
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = config.model_dump(mode="python")

    # Node A: completed → blocked
    mock_node_a = MagicMock()
    mock_node_a.id = 10
    mock_node_a.rolling_run_id = 1
    mock_node_a.status = "completed"
    mock_node_a.node_signature = "b" * 64
    mock_node_a.upstream_selection_mode = UpstreamSelectionMode.PINNED
    mock_node_a.canonical_payload = config.nodes[0].model_dump(mode="python")

    completed_attempt_a = MagicMock()
    completed_attempt_a.id = 300
    completed_attempt_a.status = "completed"
    mock_session.execute = AsyncMock(
        side_effect=_build_session_side_effect(
            mock_run, mock_node_a, completed_attempt=completed_attempt_a
        )
    )

    with pytest.raises(NodeAlreadyFinalizedError) as exc_info:
        await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)
    assert exc_info.value.code == "NODE_ALREADY_FINALIZED"

    # Node B: pending → success
    mock_node_b = MagicMock()
    mock_node_b.id = 20
    mock_node_b.rolling_run_id = 1
    mock_node_b.status = "pending"
    mock_node_b.node_signature = "c" * 64
    mock_node_b.upstream_selection_mode = UpstreamSelectionMode.PINNED
    mock_node_b.canonical_payload = config.nodes[0].model_dump(mode="python")

    mock_attempt_b = MagicMock()
    mock_attempt_b.id = 200
    mock_attempt_b.attempt_number = 1
    mock_attempt_b.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    mock_attempt_b.finished_at = None

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node_b))

    patches = _orchestration_patches(
        mock_run=mock_run, mock_node=mock_node_b, mock_attempt=mock_attempt_b
    )

    with patch.multiple(_MOD, **patches):
        outcome_b = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=20)

    assert outcome_b.status == "completed"


# ── 18. Deterministic final snapshot hash ────────────────────────────────────


@pytest.mark.asyncio
async def test_deterministic_final_snapshot_hash(mock_session, mock_run, mock_node, mock_attempt):
    """Same inputs → same hash in the orchestration snapshot."""
    captured_snapshots = []

    async def _capture_snapshot(*args, **kwargs):
        canonical_payload = kwargs.get("canonical_payload")
        if canonical_payload is None and len(args) > 3:
            canonical_payload = args[3]
        captured_snapshots.append(canonical_payload)
        return MagicMock()

    # Run 1
    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))
    patches1 = _orchestration_patches(
        mock_run=mock_run, mock_node=mock_node, mock_attempt=mock_attempt
    )
    patches1["persist_orchestration_snapshot"] = _capture_snapshot

    with patch.multiple(_MOD, **patches1):
        await orchestrate_node(
            mock_session,
            rolling_run_id=mock_run.id,
            rolling_node_id=mock_node.id,
        )

    # Run 2
    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))
    patches2 = _orchestration_patches(
        mock_run=mock_run, mock_node=mock_node, mock_attempt=mock_attempt
    )
    patches2["persist_orchestration_snapshot"] = _capture_snapshot

    with patch.multiple(_MOD, **patches2):
        await orchestrate_node(
            mock_session,
            rolling_run_id=mock_run.id,
            rolling_node_id=mock_node.id,
        )

    assert len(captured_snapshots) == 2
    assert captured_snapshots[0] is not None
    assert captured_snapshots[1] is not None

    # Compute deterministic hash
    hash1 = hashlib.sha256(
        json.dumps(captured_snapshots[0], sort_keys=True, default=str).encode()
    ).hexdigest()
    hash2 = hashlib.sha256(
        json.dumps(captured_snapshots[1], sort_keys=True, default=str).encode()
    ).hexdigest()
    assert hash1 == hash2, "Same inputs must produce identical snapshot hashes"


# ── 19. Unsupported mode returns typed error ─────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_mode_returns_typed_error(mock_session):
    """Returns UnsupportedExecutionModeError, not NotImplementedError."""
    retro_config = _make_config(execution_mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = retro_config.model_dump(mode="python")

    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "pending"
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.PINNED
    mock_node.canonical_payload = retro_config.nodes[0].model_dump(mode="python")

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    with pytest.raises(UnsupportedExecutionModeError) as exc_info:
        await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)
    assert exc_info.value.code == "UNSUPPORTED_EXECUTION_MODE"
    # Verify it's a typed error, not NotImplementedError
    assert not isinstance(exc_info.value, NotImplementedError)


# ══════════════════════════════════════════════════════════════════════════════
# Additional contract tests
# ══════════════════════════════════════════════════════════════════════════════


# ── Run not found ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_not_found(mock_session):
    """Missing run raises integrity error."""
    mock_session.execute = AsyncMock(return_value=_run_result_for(None))

    from backend.app.rolling_backtest.errors import RollingBacktestIntegrityError

    with pytest.raises(RollingBacktestIntegrityError):
        await orchestrate_node(mock_session, rolling_run_id=999, rolling_node_id=10)


# ── Node not found ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_node_not_found(mock_session):
    """Missing node raises integrity error."""
    mock_run = MagicMock()
    mock_run.id = 1
    config = _make_config()
    mock_run.canonical_payload = config.model_dump(mode="python")

    mock_session.execute = AsyncMock(side_effect=[_run_result_for(mock_run), _run_result_for(None)])

    from backend.app.rolling_backtest.errors import RollingBacktestIntegrityError

    with pytest.raises(RollingBacktestIntegrityError):
        await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=999)


# ── Node wrong run ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_node_wrong_run(mock_session):
    """Node belonging to different run raises authority binding error."""
    mock_run = MagicMock()
    mock_run.id = 1
    config = _make_config()
    mock_run.canonical_payload = config.model_dump(mode="python")

    mock_node_wrong = MagicMock()
    mock_node_wrong.id = 10
    mock_node_wrong.rolling_run_id = 2  # Wrong run!
    mock_node_wrong.status = "pending"
    mock_node_wrong.node_signature = "b" * 64
    mock_node_wrong.upstream_selection_mode = UpstreamSelectionMode.PINNED
    mock_node_wrong.canonical_payload = config.nodes[0].model_dump(mode="python")

    mock_session.execute = AsyncMock(
        side_effect=[_run_result_for(mock_run), _run_result_for(mock_node_wrong)]
    )

    from backend.app.rolling_backtest.errors import RollingBacktestAuthorityBindingError

    with pytest.raises(RollingBacktestAuthorityBindingError):
        await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)


# ── Error types are specific ─────────────────────────────────────────────────


def test_error_types_are_specific():
    """All orchestration error types inherit from NodeOrchestrationError."""
    from backend.app.rolling_backtest.node_orchestration import NodeOrchestrationError

    error_classes = [
        UnsupportedExecutionModeError,
        UnsupportedSelectionModeError,
        NodeAlreadyFinalizedError,
        PinnedSourceNotFoundError,
        PinnedSourceNotVisibleError,
        Task8ParentAuthorityMismatchError,
        Task9Task8AuthorityMismatchError,
        Task10Task9BindingMismatchError,
        Task10PredictionNotCompletedError,
    ]
    for exc_cls in error_classes:
        assert issubclass(exc_cls, NodeOrchestrationError), (
            f"{exc_cls.__name__} should inherit from NodeOrchestrationError"
        )
        instance = exc_cls("test message")
        assert hasattr(instance, "code")
        assert isinstance(instance.code, str)
        assert len(instance.code) > 0


# ── Blocker codes are unique ─────────────────────────────────────────────────


def test_blocker_codes_are_unique():
    """Each error type has a unique blocker code."""
    error_classes = [
        UnsupportedExecutionModeError,
        UnsupportedSelectionModeError,
        NodeAlreadyFinalizedError,
        PinnedSourceNotFoundError,
        PinnedSourceNotVisibleError,
        Task8ParentAuthorityMismatchError,
        Task9Task8AuthorityMismatchError,
        Task10Task9BindingMismatchError,
        Task10PredictionNotCompletedError,
    ]
    codes = [cls.code for cls in error_classes]
    assert len(codes) == len(set(codes)), f"Duplicate blocker codes: {codes}"


# ── Stage ordinal mapping ────────────────────────────────────────────────────


def test_stage_ordinal_mapping_complete():
    """All orchestration stages have ordinals."""
    for stage in OrchestrationStage:
        assert stage.value in _STAGE_ORDINAL, f"Stage {stage.value} missing from _STAGE_ORDINAL"


def test_stage_ordinals_are_sequential():
    """Stage ordinals are 1-8 in order."""
    ordinals = [_STAGE_ORDINAL[stage.value] for stage in OrchestrationStage]
    assert ordinals == list(range(1, len(OrchestrationStage) + 1))


# ── Unsupported selection mode ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_selection_mode(mock_session):
    """Non-pinned selection mode returns UnsupportedSelectionModeError."""
    config = _make_config()
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = config.model_dump(mode="python")

    node_def = _make_node_def(selection_mode=UpstreamSelectionMode.HISTORICAL_RESOLUTION)
    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "pending"
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.HISTORICAL_RESOLUTION
    mock_node.canonical_payload = node_def.model_dump(mode="python")

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    with pytest.raises(UnsupportedSelectionModeError) as exc_info:
        await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)
    assert exc_info.value.code == "UNSUPPORTED_SELECTION_MODE"
