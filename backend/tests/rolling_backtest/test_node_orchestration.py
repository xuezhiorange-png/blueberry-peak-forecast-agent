"""Unit/contract tests for node orchestration service (Task 11 Phase 1).

Tests the eight-stage DAG orchestration for rolling backtest nodes.
All tests are pure unit tests — no PostgreSQL, no integration mark.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
    ExecutionMode,
    UpstreamSelectionMode,
)
from backend.app.rolling_backtest.node_orchestration import (
    HistoricalSourceNotFoundError,
    HistoricalSourceNotVisibleError,
    NodeAlreadyFinalizedError,
    PinnedSourceIdentityMismatchError,
    PinnedSourceNotFoundError,
    PinnedSourceNotVisibleError,
    PinnedSourceScopeMismatchError,
    Task8ParentAuthorityMismatchError,
    Task9Task8AuthorityMismatchError,
    Task10PredictionNotCompletedError,
    Task10Task9BindingMismatchError,
    UnsupportedExecutionModeError,
    UnsupportedSelectionModeError,
    _extract_authoritative_available_at,
    orchestrate_node,
)
from backend.app.rolling_backtest.orchestration import (
    AvailabilityAuditOutcome,
    NodeOrchestrationOutcome,
    OrchestrationStage,
    ResolvedInputOutcome,
    Task9AuthorityOutcome,
    Task10AuthorityOutcome,
)
from backend.app.rolling_backtest.resolution import HistoricalCandidate, ResolutionResult
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


def _scalar_result(obj):
    result = MagicMock()
    result.scalar_one.return_value = obj
    result.scalar_one_or_none.return_value = obj
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


async def _mock_stage_resolve_historical_inputs_happy(session, ctx, config, node):
    """Mock stage 1 for unit tests so later-stage tests stay focused."""
    for identity in node.resolved_upstream_semantic_identities:
        ctx.resolved_inputs[identity.source_role] = ResolvedInputOutcome(
            source_role=identity.source_role,
            source_type=identity.source_type,
            semantic_identity=identity,
            persistent_reference=identity.persistent_reference
            or PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=42,
            ),
            authoritative_available_at=datetime(2026, 3, 14, 4, 0, tzinfo=UTC),
            canonical_identity_hash="1" * 64,
            canonical_payload_hash=identity.semantic.canonical_payload_hash or "2" * 64,
            business_version=identity.semantic.business_version,
        )
    return ctx


async def _noop_stage(session, ctx, config, node):
    """No-op stage helper for unit tests that are not exercising real reuse loaders."""
    return ctx


class _SnapshotWithoutAuthorityTimestamp:
    pass


# ── Common mock patches for orchestrate_node ─────────────────────────────────


def _make_attempt_mock(attempt_fixture):
    """Build a clean MagicMock for an attempt from fixture data."""
    m = MagicMock()
    m.id = attempt_fixture.id
    m.attempt_number = attempt_fixture.attempt_number
    m.prior_attempt_id = getattr(attempt_fixture, "prior_attempt_id", None)
    m.started_at = attempt_fixture.started_at
    m.finished_at = attempt_fixture.finished_at
    return m


def _orchestration_patches(
    *,
    mock_run,
    mock_node,
    mock_attempt,
    stage_resolve_historical_inputs=None,
    stage_validate_visibility=None,
    stage_resolve_task8=None,
    stage_resolve_task9=None,
    stage_resolve_task10=None,
    stage_execute_task10_prediction=None,
):
    """Return a dict of {short_attr_name: mock_value} for patch.multiple."""
    persisted_identities = RollingNodeDefinition.model_validate(
        mock_node.canonical_payload
    ).resolved_upstream_semantic_identities
    if stage_resolve_historical_inputs is None:
        stage_resolve_historical_inputs = _mock_stage_resolve_historical_inputs_happy
    if stage_validate_visibility is None:
        stage_validate_visibility = _mock_stage_validate_visibility_happy
    if stage_resolve_task8 is None:
        stage_resolve_task8 = _noop_stage
    if stage_resolve_task9 is None:
        stage_resolve_task9 = _noop_stage
    if stage_resolve_task10 is None:
        stage_resolve_task10 = _noop_stage
    if stage_execute_task10_prediction is None:
        stage_execute_task10_prediction = _noop_stage

    attempt_inst = _make_attempt_mock(mock_attempt)

    return {
        "create_execution_attempt": AsyncMock(return_value=attempt_inst),
        "persist_stage_event": AsyncMock(),
        "persist_orchestration_snapshot": AsyncMock(),
        "load_node_resolved_identities_with_references": AsyncMock(
            return_value=persisted_identities
        ),
        "load_logical_run_with_integrity": AsyncMock(return_value=mock_run),
        "finalize_attempt_status": AsyncMock(return_value=attempt_inst),
        "finalize_attempt_with_snapshot": AsyncMock(return_value=(attempt_inst, MagicMock())),
        "update_run_status_from_attempts": AsyncMock(),
        "_stage_resolve_historical_inputs": stage_resolve_historical_inputs,
        "_stage_validate_visibility": stage_validate_visibility,
        "_stage_resolve_task8": stage_resolve_task8,
        "_stage_resolve_task9": stage_resolve_task9,
        "_stage_resolve_task10": stage_resolve_task10,
        "_stage_execute_task10_prediction": stage_execute_task10_prediction,
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


@pytest.mark.asyncio
async def test_orchestrate_node_uses_persisted_resolved_references_before_stage1(
    mock_session, mock_run, mock_node, mock_attempt
):
    """Stage 1 must receive identities rehydrated from persisted resolved-input rows."""
    bare_identity = _make_identity().model_copy(update={"persistent_reference": None})
    persisted_identity = _make_identity().model_copy(
        update={
            "persistent_reference": PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=84,
            )
        }
    )
    config = _make_config(nodes=(_make_node_def(identities=(bare_identity,)),))
    mock_run.canonical_payload = config.model_dump(mode="python")
    mock_node.canonical_payload = config.nodes[0].model_dump(mode="python")

    async def _assert_persisted_stage(session, ctx, config, node):
        assert node.resolved_upstream_semantic_identities == (persisted_identity,)
        assert node.resolved_upstream_semantic_identities[0].persistent_reference is not None
        return ctx

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))
    patches = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=mock_attempt,
        stage_resolve_historical_inputs=_assert_persisted_stage,
    )
    patches["load_node_resolved_identities_with_references"] = AsyncMock(
        return_value=(persisted_identity,)
    )

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)

    assert outcome.status == "completed"


# ── 2. Retrospective replay unsupported ──────────────────────────────────────


@pytest.mark.asyncio
async def test_retrospective_replay_unsupported(mock_session):
    """Retrospective replay mode returns blocked outcome (P0-2)."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

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

    mock_attempt = MagicMock()
    mock_attempt.id = 100
    mock_attempt.attempt_number = 1
    mock_attempt.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    mock_attempt.finished_at = None

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    patches = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=mock_attempt,
        stage_resolve_historical_inputs=node_orch._stage_resolve_historical_inputs,
    )

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)
    assert outcome.status == "blocked"
    assert outcome.blocker_code == "UNSUPPORTED_EXECUTION_MODE"


# ── 3. Historical resolution unsupported ─────────────────────────────────────


@pytest.mark.asyncio
async def test_historical_resolution_unsupported(mock_session):
    """Historical resolution selects via resolve_historical and completes."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

    node_def = _make_node_def(selection_mode=UpstreamSelectionMode.HISTORICAL_RESOLUTION)
    config = _make_config(nodes=(node_def,))
    persisted_identity = node_def.resolved_upstream_semantic_identities[0]

    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = config.model_dump(mode="python")

    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "pending"
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.HISTORICAL_RESOLUTION
    mock_node.canonical_payload = node_def.model_dump(mode="python")

    mock_attempt = MagicMock()
    mock_attempt.id = 100
    mock_attempt.attempt_number = 1
    mock_attempt.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    mock_attempt.finished_at = None

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    resolved_candidate = HistoricalCandidate(
        source_role=persisted_identity.source_role,
        source_type=persisted_identity.source_type,
        persistent_reference=PersistentUpstreamReference(
            reference_type="database_run_id",
            reference_value=84,
        ),
        semantic_identity=persisted_identity.model_copy(
            update={
                "persistent_reference": PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=84,
                )
            }
        ),
        authoritative_available_at=datetime(2026, 3, 14, 4, 0, tzinfo=UTC),
        business_version=persisted_identity.semantic.business_version,
        canonical_payload_hash="c" * 64,
    )

    patches = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=mock_attempt,
        stage_resolve_historical_inputs=node_orch._stage_resolve_historical_inputs,
    )

    with (
        patch.multiple(_MOD, **patches),
        patch(
            f"{_MOD}.resolve_historical",
            AsyncMock(
                return_value=ResolutionResult(
                    source_role=persisted_identity.source_role,
                    source_type=persisted_identity.source_type,
                    candidates=(resolved_candidate,),
                    resolved=resolved_candidate,
                )
            ),
        ),
        patch(
            f"{_MOD}._build_availability_snapshot_for_resolved_input",
            AsyncMock(
                return_value=MagicMock(
                    source_type=persisted_identity.source_type,
                    status="completed",
                    authoritative_timestamp=datetime(2026, 3, 14, 4, 0, tzinfo=UTC),
                )
            ),
        ),
        patch(f"{_MOD}._has_historical_candidates_outside_cutoff", AsyncMock(return_value=False)),
    ):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)
    assert outcome.status == "completed"
    assert outcome.blocker_code is None


@pytest.mark.asyncio
async def test_historical_resolution_no_candidate_blocks(mock_session):
    """Historical resolution with no valid candidate must block fail-closed."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

    node_def = _make_node_def(selection_mode=UpstreamSelectionMode.HISTORICAL_RESOLUTION)
    config = _make_config(nodes=(node_def,))
    persisted_identity = node_def.resolved_upstream_semantic_identities[0]

    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = config.model_dump(mode="python")

    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "pending"
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.HISTORICAL_RESOLUTION
    mock_node.canonical_payload = node_def.model_dump(mode="python")

    mock_attempt = MagicMock()
    mock_attempt.id = 100
    mock_attempt.attempt_number = 1
    mock_attempt.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    mock_attempt.finished_at = None

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    patches = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=mock_attempt,
        stage_resolve_historical_inputs=node_orch._stage_resolve_historical_inputs,
    )

    with (
        patch.multiple(_MOD, **patches),
        patch(
            f"{_MOD}.resolve_historical",
            AsyncMock(
                return_value=ResolutionResult(
                    source_role=persisted_identity.source_role,
                    source_type=persisted_identity.source_type,
                    candidates=(),
                    blocked=True,
                    blocker_code="historical_source_not_found",
                )
            ),
        ),
        patch(f"{_MOD}._has_historical_candidates_outside_cutoff", AsyncMock(return_value=False)),
    ):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)
    assert outcome.status == "blocked"
    assert outcome.blocker_code == HistoricalSourceNotFoundError.code


@pytest.mark.asyncio
async def test_historical_resolution_not_visible_blocks(mock_session):
    """Historical resolution with only cutoff-invisible candidates must block."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

    node_def = _make_node_def(selection_mode=UpstreamSelectionMode.HISTORICAL_RESOLUTION)
    config = _make_config(nodes=(node_def,))
    persisted_identity = node_def.resolved_upstream_semantic_identities[0]

    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = config.model_dump(mode="python")

    mock_node = MagicMock()
    mock_node.id = 10
    mock_node.rolling_run_id = 1
    mock_node.status = "pending"
    mock_node.node_signature = "b" * 64
    mock_node.upstream_selection_mode = UpstreamSelectionMode.HISTORICAL_RESOLUTION
    mock_node.canonical_payload = node_def.model_dump(mode="python")

    mock_attempt = MagicMock()
    mock_attempt.id = 100
    mock_attempt.attempt_number = 1
    mock_attempt.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    mock_attempt.finished_at = None

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    patches = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=mock_attempt,
        stage_resolve_historical_inputs=node_orch._stage_resolve_historical_inputs,
    )

    with (
        patch.multiple(_MOD, **patches),
        patch(
            f"{_MOD}.resolve_historical",
            AsyncMock(
                return_value=ResolutionResult(
                    source_role=persisted_identity.source_role,
                    source_type=persisted_identity.source_type,
                    candidates=(),
                    blocked=True,
                    blocker_code="historical_source_not_visible",
                )
            ),
        ),
    ):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)
    assert outcome.status == "blocked"
    assert outcome.blocker_code == HistoricalSourceNotVisibleError.code


# ── 4. Node already finalized ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_node_already_finalized(mock_session):
    """Completed node returns idempotent completed outcome (P0-1)."""
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
    completed_attempt.attempt_number = 1
    completed_attempt.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    completed_attempt.finished_at = datetime(2026, 3, 15, 5, 0, tzinfo=UTC)

    mock_session.execute = AsyncMock(
        side_effect=_build_session_side_effect(
            mock_run, mock_node, completed_attempt=completed_attempt
        )
    )

    patches = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=completed_attempt,
    )
    patches["load_logical_run_with_integrity"] = AsyncMock(return_value=mock_run)

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)
    assert outcome.status == "completed"
    assert outcome.diagnostics.get("idempotent_reload") is True
    assert outcome.attempt_number == 1


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


def test_extract_authoritative_available_at_rejects_missing_timestamp() -> None:
    """Availability extraction must fail closed without a persisted timestamp."""
    with pytest.raises(PinnedSourceIdentityMismatchError):
        _extract_authoritative_available_at(_SnapshotWithoutAuthorityTimestamp())


# ── 7. Task 8 parent authority mismatch ──────────────────────────────────────


@pytest.mark.asyncio
async def test_task8_parent_authority_mismatch(mock_session):
    """Task 8 artifact without model run blocks orchestration."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

    artifact_identity = _make_identity(
        source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
        source_role="task8_model_artifact",
    ).model_copy(
        update={
            "persistent_reference": PersistentUpstreamReference(
                reference_type="database_artifact_id",
                reference_value=42,
            )
        }
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
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=mock_attempt,
        stage_resolve_task8=node_orch._stage_resolve_task8,
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


@pytest.mark.asyncio
async def test_stage2_blocker_uses_actual_terminal_stage(
    mock_session, mock_run, mock_node, mock_attempt
):
    """Blocked stage uses the actual failing stage, not the last completed stage."""
    config = _make_config()
    mock_run.canonical_payload = config.model_dump(mode="python")
    mock_node.canonical_payload = config.nodes[0].model_dump(mode="python")
    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    async def _stage2_blocked(session, ctx, config, node):
        raise PinnedSourceNotVisibleError("blocked at stage 2")

    finalize_mock = AsyncMock(return_value=(mock_attempt, MagicMock()))
    update_run_mock = AsyncMock()
    patches = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=mock_attempt,
        stage_validate_visibility=_stage2_blocked,
    )
    patches["finalize_attempt_with_snapshot"] = finalize_mock
    patches["update_run_status_from_attempts"] = update_run_mock

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)

    assert outcome.status == "blocked"
    assert outcome.blocker_code == "PINNED_SOURCE_NOT_VISIBLE"
    assert outcome.stage == OrchestrationStage.VALIDATE_VISIBILITY.value
    assert (
        outcome.diagnostics["last_completed_stage"]
        == OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value
    )
    assert outcome.diagnostics["terminal_stage"] == OrchestrationStage.VALIDATE_VISIBILITY.value

    assert (
        finalize_mock.await_args.kwargs["current_stage"]
        == OrchestrationStage.VALIDATE_VISIBILITY.value
    )
    assert (
        finalize_mock.await_args.kwargs["terminal_stage"]
        == OrchestrationStage.VALIDATE_VISIBILITY.value
    )
    assert (
        finalize_mock.await_args.kwargs["sanitized_diagnostics"]["last_completed_stage"]
        == OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value
    )
    assert (
        finalize_mock.await_args.kwargs["sanitized_diagnostics"]["terminal_stage"]
        == OrchestrationStage.VALIDATE_VISIBILITY.value
    )

    stage_calls = patches["persist_stage_event"].call_args_list
    assert stage_calls[1].kwargs["stage"] == OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value
    assert stage_calls[1].kwargs["status"] == "completed"
    assert stage_calls[3].kwargs["stage"] == OrchestrationStage.VALIDATE_VISIBILITY.value
    assert stage_calls[3].kwargs["status"] == "blocked"


@pytest.mark.asyncio
async def test_stage6_blocker_uses_actual_terminal_stage(
    mock_session, mock_run, mock_node, mock_attempt
):
    """Later-stage blockers keep previous completion separate from actual terminal stage."""
    config = _make_config()
    mock_run.canonical_payload = config.model_dump(mode="python")
    mock_node.canonical_payload = config.nodes[0].model_dump(mode="python")
    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    async def _stage6_blocked(session, ctx, config, node):
        raise Task10Task9BindingMismatchError("task10/task9 mismatch")

    finalize_mock = AsyncMock(return_value=(mock_attempt, MagicMock()))
    update_run_mock = AsyncMock()
    patches = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=mock_attempt,
        stage_resolve_task10=_stage6_blocked,
    )
    patches["finalize_attempt_with_snapshot"] = finalize_mock
    patches["update_run_status_from_attempts"] = update_run_mock

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)

    assert outcome.status == "blocked"
    assert outcome.blocker_code == "TASK10_TASK9_BINDING_MISMATCH"
    assert outcome.stage == OrchestrationStage.RESOLVE_OR_TRAIN_TASK10.value
    assert (
        outcome.diagnostics["last_completed_stage"]
        == OrchestrationStage.RESOLVE_OR_REPLAY_TASK9.value
    )
    assert outcome.diagnostics["terminal_stage"] == OrchestrationStage.RESOLVE_OR_TRAIN_TASK10.value
    assert (
        finalize_mock.await_args.kwargs["current_stage"]
        == OrchestrationStage.RESOLVE_OR_TRAIN_TASK10.value
    )
    assert (
        finalize_mock.await_args.kwargs["sanitized_diagnostics"]["last_completed_stage"]
        == OrchestrationStage.RESOLVE_OR_REPLAY_TASK9.value
    )


@pytest.mark.asyncio
async def test_unexpected_stage_exception_uses_actual_terminal_stage(
    mock_session, mock_run, mock_node, mock_attempt
):
    """Unexpected stage exceptions keep the real terminal stage and generic blocker outcome."""
    config = _make_config()
    mock_run.canonical_payload = config.model_dump(mode="python")
    mock_node.canonical_payload = config.nodes[0].model_dump(mode="python")
    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    async def _stage5_boom(session, ctx, config, node):
        raise RuntimeError("boom")

    finalize_mock = AsyncMock(return_value=(mock_attempt, MagicMock()))
    update_run_mock = AsyncMock()
    patches = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=mock_attempt,
        stage_resolve_task9=_stage5_boom,
    )
    patches["finalize_attempt_with_snapshot"] = finalize_mock
    patches["update_run_status_from_attempts"] = update_run_mock

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)

    assert outcome.status == "failed"
    assert outcome.blocker_code == "PERSISTENCE_FAILURE"
    assert outcome.stage == OrchestrationStage.RESOLVE_OR_REPLAY_TASK9.value
    assert (
        outcome.diagnostics["last_completed_stage"]
        == OrchestrationStage.RESOLVE_OR_REPLAY_TASK8.value
    )
    assert outcome.diagnostics["terminal_stage"] == OrchestrationStage.RESOLVE_OR_REPLAY_TASK9.value
    assert (
        finalize_mock.await_args.kwargs["current_stage"]
        == OrchestrationStage.RESOLVE_OR_REPLAY_TASK9.value
    )
    assert finalize_mock.await_args.kwargs["structured_error_code"] == "PERSISTENCE_FAILURE"
    blocked_stage_call = patches["persist_stage_event"].call_args_list[-1]
    assert blocked_stage_call.kwargs["stage"] == OrchestrationStage.RESOLVE_OR_REPLAY_TASK9.value
    assert blocked_stage_call.kwargs["status"] == "blocked"
    assert blocked_stage_call.kwargs["structured_error_code"] == "STAGE_FAILED"


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
    """Re-running a completed node returns idempotent completed outcome (P0-1)."""
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
    completed_attempt.attempt_number = 1
    completed_attempt.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    completed_attempt.finished_at = datetime(2026, 3, 15, 5, 0, tzinfo=UTC)

    mock_session.execute = AsyncMock(
        side_effect=_build_session_side_effect(
            mock_run, mock_node, completed_attempt=completed_attempt
        )
    )

    patches = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=completed_attempt,
    )
    patches["load_logical_run_with_integrity"] = AsyncMock(return_value=mock_run)

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)
    assert outcome.status == "completed"
    assert outcome.diagnostics.get("idempotent_reload") is True


# ── 17. Mixed node status aggregation ────────────────────────────────────────


@pytest.mark.asyncio
async def test_mixed_node_status_aggregation(mock_session):
    """Multiple nodes with different statuses — each handled independently (P0-1)."""
    config = _make_config()
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.run_signature = "a" * 64
    mock_run.canonical_payload = config.model_dump(mode="python")

    # Node A: completed → returns completed with idempotent_reload
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
    completed_attempt_a.attempt_number = 1
    completed_attempt_a.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    completed_attempt_a.finished_at = datetime(2026, 3, 15, 5, 0, tzinfo=UTC)
    mock_session.execute = AsyncMock(
        side_effect=_build_session_side_effect(
            mock_run, mock_node_a, completed_attempt=completed_attempt_a
        )
    )

    patches_a = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node_a,
        mock_attempt=completed_attempt_a,
    )
    patches_a["load_logical_run_with_integrity"] = AsyncMock(return_value=mock_run)

    with patch.multiple(_MOD, **patches_a):
        outcome_a = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)
    assert outcome_a.status == "completed"
    assert outcome_a.diagnostics.get("idempotent_reload") is True

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
    """Returns blocked outcome with UNSUPPORTED_EXECUTION_MODE blocker (P0-2)."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

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

    mock_attempt = MagicMock()
    mock_attempt.id = 100
    mock_attempt.attempt_number = 1
    mock_attempt.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    mock_attempt.finished_at = None

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    patches = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=mock_attempt,
        stage_resolve_historical_inputs=node_orch._stage_resolve_historical_inputs,
    )

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)
    assert outcome.status == "blocked"
    assert outcome.blocker_code == "UNSUPPORTED_EXECUTION_MODE"


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


@pytest.mark.asyncio
async def test_run_stage_passes_caller_session_to_stage_event_persistence(mock_session):
    """Stage persistence must use the caller session so one node orchestration stays atomic."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

    captured_sessions: list[object | None] = []

    async def _capture_stage_event(*args, **kwargs):
        captured_sessions.append(kwargs.get("session"))
        return MagicMock()

    async def _noop_stage(session, ctx, config, node):
        return ctx

    ctx = node_orch._StageContext(
        attempt_id=100,
        node_id=10,
        run_id=1,
        resolved_inputs={},
        availability_audits={},
    )

    with patch(f"{_MOD}.persist_stage_event", new=AsyncMock(side_effect=_capture_stage_event)):
        await node_orch._run_stage(
            mock_session,
            ctx,
            OrchestrationStage.RESOLVE_HISTORICAL_INPUTS,
            _make_config(),
            _make_node_def(),
            _noop_stage,
        )

    assert captured_sessions == [mock_session, mock_session]


@pytest.mark.asyncio
async def test_exact_pinned_candidate_loads_task8_model_run_via_official_loader():
    """Pinned exact-load must use the official Task 8 loader and frozen authority time."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

    identity = _make_identity(
        source_type=AvailabilitySourceType.TASK8_MODEL_RUN,
        source_role="task8_model_run",
        semantic_payload_hash="c" * 64,
        canonical_payload_hash="c" * 64,
        business_version="task8-v1",
    ).model_copy(
        update={
            "persistent_reference": PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=84,
            )
        }
    )

    session = AsyncMock()
    row = MagicMock()
    row.id = 84
    row.finished_at = datetime(2026, 3, 14, 4, 0, tzinfo=UTC)
    row.config_hash = "c" * 64
    row.model_version = "task8-v1"
    session.get = AsyncMock(return_value=row)

    with patch(
        f"{_MOD}.load_maturity_model_result",
        new=AsyncMock(return_value=MagicMock(status="completed")),
    ) as load_model:
        candidate = await node_orch._load_exact_pinned_candidate(
            session,
            _make_node_def(identities=(identity,)),
            identity,
        )

    load_model.assert_awaited_once_with(session, run_id=84)
    assert candidate.persistent_reference == PersistentUpstreamReference(
        reference_type="database_run_id",
        reference_value=84,
    )
    assert candidate.authoritative_available_at == row.finished_at
    assert candidate.canonical_payload_hash == "c" * 64


@pytest.mark.asyncio
async def test_task9_reuse_uses_official_loader_and_freezes_hashes():
    """Task 9 reuse must go through the official envelope loader and carry frozen hashes."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

    task9_identity = _make_identity(
        source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
        source_role="task9_structural_forecast",
        input_signature="1" * 64,
        result_hash="2" * 64,
        canonical_payload_hash="3" * 64,
    )
    task8_identity = _make_identity(
        source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
        source_role="task8_forecast_run",
        input_signature="4" * 64,
        result_hash="5" * 64,
        canonical_payload_hash="6" * 64,
    )
    ctx = node_orch._StageContext(
        attempt_id=100,
        node_id=10,
        run_id=1,
        resolved_inputs={
            "task9_structural_forecast": node_orch.ResolvedInputOutcome(
                source_role=task9_identity.source_role,
                source_type=task9_identity.source_type,
                semantic_identity=task9_identity,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=42,
                ),
                authoritative_available_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
                canonical_identity_hash="7" * 64,
                canonical_payload_hash="8" * 64,
            ),
            "task8_forecast_run": node_orch.ResolvedInputOutcome(
                source_role=task8_identity.source_role,
                source_type=task8_identity.source_type,
                semantic_identity=task8_identity,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=84,
                ),
                authoritative_available_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
                canonical_identity_hash="9" * 64,
                canonical_payload_hash="a" * 64,
            ),
        },
        availability_audits={},
    )
    envelope = MagicMock()
    envelope.status = "completed"
    envelope.result_hash = "2" * 64
    envelope.config_hash = "b" * 64
    envelope.output = MagicMock()
    envelope.output.input_snapshot = {"task8_daily_predictions": []}
    envelope.output.source_catalog_hash = "c" * 64
    envelope.output.verification_snapshot_hash = "d" * 64
    session = AsyncMock()
    session.get = AsyncMock(
        side_effect=[
            MagicMock(id=84, plan_id=501),
            MagicMock(id=501, season_id=2026),
        ]
    )

    with patch(
        f"{_MOD}.get_harvest_state_run_by_id",
        new=AsyncMock(return_value=envelope),
        create=True,
    ) as get_run:
        await node_orch._resolve_task9_reuse(
            ctx,
            _make_config(nodes=(_make_node_def(identities=(task8_identity, task9_identity)),)),
            _make_node_def(identities=(task8_identity, task9_identity)),
            session=session,
            resolved_inputs=ctx.resolved_inputs,
        )

    get_run.assert_awaited_once()
    assert ctx.task9_authority is not None
    assert ctx.task9_authority.source_catalog_hash == "c" * 64
    assert ctx.task9_authority.verification_snapshot_hash == "d" * 64


@pytest.mark.asyncio
async def test_load_exact_task8_daily_prediction_requires_database_row_id():
    import backend.app.rolling_backtest.node_orchestration as node_orch

    identity = _make_identity(
        source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
        source_role="task8_daily_prediction:2026-03-01",
    )
    with pytest.raises(PinnedSourceIdentityMismatchError):
        await node_orch._load_exact_pinned_candidate(
            AsyncMock(),
            _make_node_def(identities=(identity,)),
            identity,
        )


@pytest.mark.asyncio
async def test_load_exact_task8_model_artifact_requires_database_artifact_id():
    import backend.app.rolling_backtest.node_orchestration as node_orch

    identity = _make_identity(
        source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
        source_role="task8_model_artifact",
    )
    with pytest.raises(PinnedSourceIdentityMismatchError):
        await node_orch._load_exact_pinned_candidate(
            AsyncMock(),
            _make_node_def(identities=(identity,)),
            identity,
        )


@pytest.mark.asyncio
async def test_load_exact_task3_candidate_rejects_db_season_scope_mismatch():
    import backend.app.rolling_backtest.node_orchestration as node_orch

    identity = _make_identity(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        source_role="task3_analytics_build",
        business_version="agg-v1",
    )
    session = AsyncMock()
    session.get = AsyncMock(
        return_value=MagicMock(
            id=42,
            season_id=2026,
            aggregation_version="agg-v1",
            config_hash="a" * 64,
            finished_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
        )
    )
    mismatched_node = _make_node_def(identities=(identity,)).model_copy(
        update={
            "season_id": 2027,
            "as_of_local_date": date(2027, 3, 15),
            "forecast_cutoff_at": datetime(2027, 3, 15, 4, 0, tzinfo=UTC),
            "forecast_start_local_date": date(2027, 3, 16),
            "forecast_end_local_date": date(2027, 3, 31),
        }
    )

    with pytest.raises(PinnedSourceScopeMismatchError):
        await node_orch._load_exact_pinned_candidate(
            session,
            mismatched_node,
            identity,
        )


@pytest.mark.asyncio
async def test_verify_task8_daily_exact_set_rejects_db_date_to_id_mismatch():
    import backend.app.rolling_backtest.node_orchestration as node_orch

    pinned_daily_a = _make_identity(
        source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
        source_role="task8_daily_prediction:2026-03-01",
        semantic_payload_hash="5" * 64,
        input_signature="4" * 64,
        canonical_payload_hash="5" * 64,
    ).model_copy(
        update={
            "persistent_reference": PersistentUpstreamReference(
                reference_type="database_row_id",
                reference_value=901,
            )
        }
    )
    pinned_daily_b = _make_identity(
        source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
        source_role="task8_daily_prediction:2026-03-02",
        semantic_payload_hash="6" * 64,
        input_signature="4" * 64,
        canonical_payload_hash="6" * 64,
    ).model_copy(
        update={
            "persistent_reference": PersistentUpstreamReference(
                reference_type="database_row_id",
                reference_value=902,
            )
        }
    )
    pinned_outcomes = (
        node_orch.ResolvedInputOutcome(
            source_role=pinned_daily_a.source_role,
            source_type=pinned_daily_a.source_type,
            semantic_identity=pinned_daily_a,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_row_id",
                reference_value=901,
            ),
            authoritative_available_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
            canonical_identity_hash="1" * 64,
            canonical_payload_hash="5" * 64,
        ),
        node_orch.ResolvedInputOutcome(
            source_role=pinned_daily_b.source_role,
            source_type=pinned_daily_b.source_type,
            semantic_identity=pinned_daily_b,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_row_id",
                reference_value=902,
            ),
            authoritative_available_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
            canonical_identity_hash="2" * 64,
            canonical_payload_hash="6" * 64,
        ),
    )
    verification_rows = [
        {
            "verification_snapshot": {
                "prediction_date": date(2026, 3, 1),
                "forecast_quantile": "P50",
                "maturity_daily_prediction_id": 901,
                "maturity_daily_prediction_forecast_run_id": 84,
            }
        },
        {
            "verification_snapshot": {
                "prediction_date": date(2026, 3, 1),
                "forecast_quantile": "P80",
                "maturity_daily_prediction_id": 901,
                "maturity_daily_prediction_forecast_run_id": 84,
            }
        },
        {
            "verification_snapshot": {
                "prediction_date": date(2026, 3, 1),
                "forecast_quantile": "P90",
                "maturity_daily_prediction_id": 901,
                "maturity_daily_prediction_forecast_run_id": 84,
            }
        },
        {
            "verification_snapshot": {
                "prediction_date": date(2026, 3, 2),
                "forecast_quantile": "P50",
                "maturity_daily_prediction_id": 902,
                "maturity_daily_prediction_forecast_run_id": 84,
            }
        },
        {
            "verification_snapshot": {
                "prediction_date": date(2026, 3, 2),
                "forecast_quantile": "P80",
                "maturity_daily_prediction_id": 902,
                "maturity_daily_prediction_forecast_run_id": 84,
            }
        },
        {
            "verification_snapshot": {
                "prediction_date": date(2026, 3, 2),
                "forecast_quantile": "P90",
                "maturity_daily_prediction_id": 902,
                "maturity_daily_prediction_forecast_run_id": 84,
            }
        },
    ]
    db_row_a = MagicMock(id=901, forecast_run_id=84, prediction_date=date(2026, 3, 1))
    db_row_b = MagicMock(id=999, forecast_run_id=84, prediction_date=date(2026, 3, 2))
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [db_row_a, db_row_b]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)

    with pytest.raises(Task9Task8AuthorityMismatchError):
        await node_orch._verify_task8_daily_exact_set(
            session,
            forecast_run_id=84,
            pinned_daily_inputs=pinned_outcomes,
            task9_snapshot_rows=verification_rows,
            source_ref_payload_by_hash={},
        )


@pytest.mark.asyncio
async def test_load_exact_task8_forecast_rejects_plan_season_scope_mismatch():
    import backend.app.rolling_backtest.node_orchestration as node_orch

    identity = _make_identity(
        source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
        source_role="task8_forecast_run",
        input_signature="4" * 64,
    )
    forecast_row = MagicMock(
        id=84,
        plan_id=501,
        finished_at=datetime(2026, 2, 28, 13, 0, tzinfo=UTC),
        source_signature="4" * 64,
    )
    plan_row = MagicMock(id=501, season_id=2026)
    session = AsyncMock()
    session.get = AsyncMock(side_effect=[forecast_row, plan_row])

    with patch(
        f"{_MOD}.load_maturity_forecast_result",
        new=AsyncMock(return_value=MagicMock(status="completed")),
        create=True,
    ):
        with pytest.raises(PinnedSourceScopeMismatchError):
            await node_orch._load_exact_pinned_candidate(
                session,
                _make_node_def().model_copy(
                    update={
                        "season_id": 2027,
                        "as_of_local_date": date(2027, 3, 15),
                        "forecast_cutoff_at": datetime(2027, 3, 15, 4, 0, tzinfo=UTC),
                        "forecast_start_local_date": date(2027, 3, 16),
                        "forecast_end_local_date": date(2027, 3, 31),
                    }
                ),
                identity,
            )


@pytest.mark.asyncio
async def test_load_exact_task10_model_artifact_requires_database_artifact_id():
    import backend.app.rolling_backtest.node_orchestration as node_orch

    identity = _make_identity(
        source_type=AvailabilitySourceType.TASK10_MODEL_ARTIFACT,
        source_role="task10_model_artifact",
    )
    with pytest.raises(PinnedSourceIdentityMismatchError):
        await node_orch._load_exact_pinned_candidate(
            AsyncMock(),
            _make_node_def(identities=(identity,)),
            identity,
        )


@pytest.mark.asyncio
async def test_task9_reuse_rejects_quantile_rows_with_different_daily_ids():
    import backend.app.rolling_backtest.node_orchestration as node_orch

    task9_identity = _make_identity(
        source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
        source_role="task9_structural_forecast",
        input_signature="1" * 64,
        result_hash="2" * 64,
        canonical_payload_hash="3" * 64,
    )
    task8_forecast_identity = _make_identity(
        source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
        source_role="task8_forecast_run",
        input_signature="4" * 64,
    )
    task8_daily_identity = _make_identity(
        source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
        source_role="task8_daily_prediction:2026-03-01",
        semantic_payload_hash="5" * 64,
        input_signature="4" * 64,
        canonical_payload_hash="5" * 64,
    ).model_copy(
        update={
            "persistent_reference": PersistentUpstreamReference(
                reference_type="database_row_id",
                reference_value=901,
            )
        }
    )
    ctx = node_orch._StageContext(
        attempt_id=100,
        node_id=10,
        run_id=1,
        resolved_inputs={
            "task9_structural_forecast": node_orch.ResolvedInputOutcome(
                source_role=task9_identity.source_role,
                source_type=task9_identity.source_type,
                semantic_identity=task9_identity,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=42,
                ),
                authoritative_available_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
                canonical_identity_hash="7" * 64,
                canonical_payload_hash="8" * 64,
            ),
            "task8_forecast_run": node_orch.ResolvedInputOutcome(
                source_role=task8_forecast_identity.source_role,
                source_type=task8_forecast_identity.source_type,
                semantic_identity=task8_forecast_identity,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=84,
                ),
                authoritative_available_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
                canonical_identity_hash="9" * 64,
                canonical_payload_hash="a" * 64,
            ),
            task8_daily_identity.source_role: node_orch.ResolvedInputOutcome(
                source_role=task8_daily_identity.source_role,
                source_type=task8_daily_identity.source_type,
                semantic_identity=task8_daily_identity,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_row_id",
                    reference_value=901,
                ),
                authoritative_available_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
                canonical_identity_hash="b" * 64,
                canonical_payload_hash="5" * 64,
            ),
        },
        availability_audits={},
    )
    envelope = MagicMock()
    envelope.status = "completed"
    envelope.result_hash = "2" * 64
    envelope.config_hash = "b" * 64
    envelope.output = MagicMock()
    envelope.output.input_snapshot = {
        "task8_daily_predictions": [
            {
                "source_ref": {
                    "forecast_quantile": "P50",
                    "source_quantity_kg": "20",
                },
                "verification_snapshot": {
                    "prediction_date": date(2026, 3, 1),
                    "maturity_forecast_as_of_date": date(2026, 2, 28),
                    "maturity_forecast_prediction_start_date": date(2026, 3, 1),
                    "maturity_forecast_prediction_end_date": date(2026, 3, 3),
                    "maturity_daily_prediction_id": 901,
                    "maturity_daily_prediction_forecast_run_id": 84,
                    "maturity_forecast_run_id": 84,
                    "maturity_forecast_run_status": "completed",
                    "maturity_forecast_model_run_id": 101,
                    "maturity_forecast_artifact_id": 201,
                    "maturity_forecast_source_signature": "4" * 64,
                    "plan_id": 501,
                    "location_reference_id": 601,
                    "farm_id": 1,
                    "subfarm_id": 11,
                    "variety_id": 101,
                    "p50_kg": "20",
                },
            },
            {
                "source_ref": {
                    "forecast_quantile": "P80",
                    "source_quantity_kg": "24",
                },
                "verification_snapshot": {
                    "prediction_date": date(2026, 3, 1),
                    "maturity_forecast_as_of_date": date(2026, 2, 28),
                    "maturity_forecast_prediction_start_date": date(2026, 3, 1),
                    "maturity_forecast_prediction_end_date": date(2026, 3, 3),
                    "maturity_daily_prediction_id": 902,
                    "maturity_daily_prediction_forecast_run_id": 84,
                    "maturity_forecast_run_id": 84,
                    "maturity_forecast_run_status": "completed",
                    "maturity_forecast_model_run_id": 101,
                    "maturity_forecast_artifact_id": 201,
                    "maturity_forecast_source_signature": "4" * 64,
                    "plan_id": 501,
                    "location_reference_id": 601,
                    "farm_id": 1,
                    "subfarm_id": 11,
                    "variety_id": 101,
                    "p80_kg": "24",
                },
            },
            {
                "source_ref": {
                    "forecast_quantile": "P90",
                    "source_quantity_kg": "28",
                },
                "verification_snapshot": {
                    "prediction_date": date(2026, 3, 1),
                    "maturity_forecast_as_of_date": date(2026, 2, 28),
                    "maturity_forecast_prediction_start_date": date(2026, 3, 1),
                    "maturity_forecast_prediction_end_date": date(2026, 3, 3),
                    "maturity_daily_prediction_id": 901,
                    "maturity_daily_prediction_forecast_run_id": 84,
                    "maturity_forecast_run_id": 84,
                    "maturity_forecast_run_status": "completed",
                    "maturity_forecast_model_run_id": 101,
                    "maturity_forecast_artifact_id": 201,
                    "maturity_forecast_source_signature": "4" * 64,
                    "plan_id": 501,
                    "location_reference_id": 601,
                    "farm_id": 1,
                    "subfarm_id": 11,
                    "variety_id": 101,
                    "p90_kg": "28",
                },
            },
        ]
    }
    envelope.output.source_catalog_hash = "c" * 64
    envelope.output.verification_snapshot_hash = "d" * 64
    session = AsyncMock()
    session.get = AsyncMock(
        side_effect=[
            MagicMock(
                id=84,
                plan_id=501,
                status="completed",
                model_run_id=101,
                artifact_id=201,
                source_signature="4" * 64,
                as_of_date=date(2026, 2, 28),
                prediction_start_date=date(2026, 3, 1),
                prediction_end_date=date(2026, 3, 3),
                location_reference_id=601,
                weather_mapping_id=801,
                base_temperature_search_run_id=901,
            ),
            MagicMock(
                id=501,
                season_id=2026,
                farm_id=1,
                subfarm_id=11,
                variety_id=101,
            ),
        ]
    )

    with patch(
        f"{_MOD}.get_harvest_state_run_by_id",
        new=AsyncMock(return_value=envelope),
        create=True,
    ):
        with pytest.raises(Task9Task8AuthorityMismatchError):
            await node_orch._resolve_task9_reuse(
                ctx,
                _make_config(
                    nodes=(
                        _make_node_def(
                            identities=(
                                task8_forecast_identity,
                                task8_daily_identity,
                                task9_identity,
                            )
                        ),
                    )
                ),
                _make_node_def(
                    identities=(
                        task8_forecast_identity,
                        task8_daily_identity,
                        task9_identity,
                    )
                ),
                session=session,
                resolved_inputs=ctx.resolved_inputs,
            )


@pytest.mark.asyncio
async def test_task10_reuse_uses_official_loaders_and_feature_binding():
    """Task 10 reuse must exact-load training/artifact/prediction and freeze feature authority."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

    task3_identity = _make_identity(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        source_role="task3_analytics_build",
        business_version="agg-v1",
    )
    task9_identity = _make_identity(
        source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
        source_role="task9_structural_forecast",
        result_hash="2" * 64,
        canonical_payload_hash="3" * 64,
    )
    training_identity = _make_identity(
        source_type=AvailabilitySourceType.TASK10_TRAINING_RUN,
        source_role="task10_training_run",
    )
    artifact_identity = _make_identity(
        source_type=AvailabilitySourceType.TASK10_MODEL_ARTIFACT,
        source_role="task10_model_artifact",
    )
    prediction_identity = _make_identity(
        source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
        source_role="task10_prediction_run",
        input_signature="6" * 64,
        result_hash="7" * 64,
    )
    ctx = node_orch._StageContext(
        attempt_id=100,
        node_id=10,
        run_id=1,
        resolved_inputs={
            "task3_analytics_build": node_orch.ResolvedInputOutcome(
                source_role=task3_identity.source_role,
                source_type=task3_identity.source_type,
                semantic_identity=task3_identity.model_copy(
                    update={
                        "persistent_reference": PersistentUpstreamReference(
                            reference_type="database_run_id",
                            reference_value=34,
                        ),
                        "semantic": task3_identity.semantic.model_copy(
                            update={"config_hash": "c" * 64}
                        ),
                    }
                ),
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=34,
                ),
                authoritative_available_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
                canonical_identity_hash="1" * 64,
                canonical_payload_hash="2" * 64,
                business_version="agg-v1",
            ),
            "task9_structural_forecast": node_orch.ResolvedInputOutcome(
                source_role=task9_identity.source_role,
                source_type=task9_identity.source_type,
                semantic_identity=task9_identity,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=11,
                ),
                authoritative_available_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
                canonical_identity_hash="3" * 64,
                canonical_payload_hash="4" * 64,
            ),
            "task10_training_run": node_orch.ResolvedInputOutcome(
                source_role=training_identity.source_role,
                source_type=training_identity.source_type,
                semantic_identity=training_identity.model_copy(
                    update={
                        "persistent_reference": PersistentUpstreamReference(
                            reference_type="database_run_id",
                            reference_value=31,
                        )
                    }
                ),
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=31,
                ),
                authoritative_available_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
                canonical_identity_hash="5" * 64,
                canonical_payload_hash="6" * 64,
            ),
            "task10_model_artifact": node_orch.ResolvedInputOutcome(
                source_role=artifact_identity.source_role,
                source_type=artifact_identity.source_type,
                semantic_identity=artifact_identity.model_copy(
                    update={
                        "persistent_reference": PersistentUpstreamReference(
                            reference_type="database_artifact_id",
                            reference_value=32,
                        )
                    }
                ),
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_artifact_id",
                    reference_value=32,
                ),
                authoritative_available_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
                canonical_identity_hash="7" * 64,
                canonical_payload_hash="8" * 64,
            ),
            "task10_prediction_run": node_orch.ResolvedInputOutcome(
                source_role=prediction_identity.source_role,
                source_type=prediction_identity.source_type,
                semantic_identity=prediction_identity.model_copy(
                    update={
                        "persistent_reference": PersistentUpstreamReference(
                            reference_type="database_run_id",
                            reference_value=33,
                        )
                    }
                ),
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=33,
                ),
                authoritative_available_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
                canonical_identity_hash="9" * 64,
                canonical_payload_hash="a" * 64,
            ),
        },
        availability_audits={},
        task9_authority=Task9AuthorityOutcome(
            run_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=11,
            ),
            result_hash="2" * 64,
            mode="reuse",
        ),
    )

    session = AsyncMock()
    artifact_row = MagicMock()
    artifact_row.training_run_id = 31
    artifact_row.artifact_sha256 = "b" * 64
    prediction_row = MagicMock()
    prediction_row.completed_at = datetime(2026, 3, 15, 3, 0, tzinfo=UTC)
    prediction_row.training_run_id = 31

    async def _session_get(model, key):
        if model.__name__ == "ResidualModelArtifact":
            return artifact_row
        if model.__name__ == "ResidualModelPredictionRun":
            return prediction_row
        return None

    session.get = AsyncMock(side_effect=_session_get)

    training_result = MagicMock(execution_status="completed")
    trusted_artifact = MagicMock()
    trusted_artifact.metadata.binary_sha256 = "b" * 64
    prediction_result = MagicMock(
        execution_status="completed",
        task9_run_id=11,
        task9_result_hash="2" * 64,
        prediction_input_signature="6" * 64,
        prediction_hash="7" * 64,
        input_snapshot={
            "feature_actual_snapshot": {
                "build_run_id": 34,
                "aggregation_version": "agg-v1",
                "config_hash": "c" * 64,
            }
        },
    )

    with (
        patch(
            f"{_MOD}.load_residual_training_run_by_id",
            new=AsyncMock(return_value=training_result),
        ) as load_training,
        patch(
            f"{_MOD}.load_and_validate_trusted_residual_artifacts",
            new=AsyncMock(return_value=[trusted_artifact]),
        ) as load_artifacts,
        patch(
            f"{_MOD}.load_residual_prediction_run_by_id",
            new=AsyncMock(return_value=prediction_result),
        ) as load_prediction,
    ):
        await node_orch._resolve_task10_reuse(
            session,
            ctx,
            _make_config(),
            _make_node_def(
                identities=(
                    task3_identity,
                    task9_identity,
                    training_identity,
                    artifact_identity,
                    prediction_identity,
                )
            ),
            resolved_inputs=ctx.resolved_inputs,
        )

    load_training.assert_awaited_once()
    load_artifacts.assert_awaited_once()
    load_prediction.assert_awaited_once()
    assert ctx.task10_authority is not None
    assert ctx.task10_authority.feature_reference == PersistentUpstreamReference(
        reference_type="database_run_id",
        reference_value=34,
    )
    assert ctx.task10_authority.task9_run_reference == PersistentUpstreamReference(
        reference_type="database_run_id",
        reference_value=11,
    )


@pytest.mark.asyncio
async def test_task10_prediction_reuse_reloads_prediction_and_feature_binding():
    """Stage 7 must exact-load the prediction run again instead of acting as a no-op."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

    session = AsyncMock()
    prediction_row = MagicMock()
    prediction_row.completed_at = datetime(2026, 3, 15, 3, 0, tzinfo=UTC)
    session.get = AsyncMock(return_value=prediction_row)
    prediction_result = MagicMock(
        execution_status="completed",
        task9_run_id=11,
        task9_result_hash="2" * 64,
        prediction_input_signature="6" * 64,
        prediction_hash="7" * 64,
        input_snapshot={"feature_actual_snapshot": {"build_run_id": 34}},
    )
    ctx = node_orch._StageContext(
        attempt_id=100,
        node_id=10,
        run_id=1,
        resolved_inputs={},
        availability_audits={},
        task9_authority=Task9AuthorityOutcome(
            run_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=11,
            ),
            result_hash="2" * 64,
            mode="reuse",
        ),
        task10_authority=Task10AuthorityOutcome(
            prediction_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=33,
            ),
            feature_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=34,
            ),
            task9_run_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=11,
            ),
            task9_result_hash="2" * 64,
            input_signature="6" * 64,
            prediction_hash="7" * 64,
            mode="reuse",
        ),
    )

    with patch(
        f"{_MOD}.load_residual_prediction_run_by_id",
        new=AsyncMock(return_value=prediction_result),
    ) as load_prediction:
        await node_orch._execute_task10_prediction_reuse(
            session,
            ctx,
            _make_config(),
            _make_node_def(),
        )

    load_prediction.assert_awaited_once_with(session, run_id=33)


def test_snapshot_payload_freezes_references_and_hashes():
    """Completed orchestration snapshot must freeze exact authority references and hashes."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

    identity = _make_identity(
        source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
        source_role="task8_forecast_run",
    )
    outcome = node_orch.ResolvedInputOutcome(
        source_role=identity.source_role,
        source_type=identity.source_type,
        semantic_identity=identity,
        persistent_reference=PersistentUpstreamReference(
            reference_type="database_run_id",
            reference_value=42,
        ),
        authoritative_available_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
        canonical_identity_hash="1" * 64,
        canonical_payload_hash="2" * 64,
        business_version="v1",
    )
    ctx = node_orch._StageContext(
        attempt_id=100,
        node_id=10,
        run_id=1,
        resolved_inputs={identity.source_role: outcome},
        availability_audits={},
        attempt_number=2,
        prior_attempt_id=99,
        task9_authority=Task9AuthorityOutcome(
            run_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=11,
            ),
            semantic_input_signature="3" * 64,
            result_hash="4" * 64,
            canonical_payload_hash="5" * 64,
            source_catalog_hash="6" * 64,
            verification_snapshot_hash="7" * 64,
            mode="reuse",
        ),
        task10_authority=Task10AuthorityOutcome(
            training_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=21,
            ),
            artifact_reference=PersistentUpstreamReference(
                reference_type="database_artifact_id",
                reference_value=22,
            ),
            feature_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=24,
            ),
            prediction_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=23,
            ),
            task9_run_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=11,
            ),
            task9_result_hash="8" * 64,
            input_signature="9" * 64,
            prediction_hash="a" * 64,
            mode="reuse",
        ),
    )

    snapshot = node_orch._build_orchestration_snapshot_payload(
        ctx,
        _make_config(),
        _make_node_def(),
        run_signature="b" * 64,
        node_signature="c" * 64,
    )

    assert snapshot["resolved_inputs"]["task8_forecast_run"]["persistent_reference"] == {
        "reference_type": "database_run_id",
        "reference_value": 42,
    }
    assert snapshot["attempt"] == {
        "attempt_id": 100,
        "attempt_number": 2,
        "prior_attempt_id": 99,
    }
    assert snapshot["task8_authorities"]["task8_forecast_run"]["canonical_payload_hash"] == "2" * 64
    assert snapshot["dag"]["dag_schema_version"] == "task11-phase3-v1"
    assert len(snapshot["dag_hash"]) == 64
    assert snapshot["task9_authority"]["source_catalog_hash"] == "6" * 64
    assert snapshot["task9_authority"]["verification_snapshot_hash"] == "7" * 64
    assert snapshot["task10_authority"]["artifact_reference"] == {
        "reference_type": "database_artifact_id",
        "reference_value": 22,
    }
    assert snapshot["task10_authority"]["feature_reference"] == {
        "reference_type": "database_run_id",
        "reference_value": 24,
    }


@pytest.mark.asyncio
async def test_finalize_blocked_uses_caller_session(mock_attempt):
    """Blocked finalization must stay in the caller transaction and update run status."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

    session = AsyncMock()
    ctx = node_orch._StageContext(
        attempt_id=mock_attempt.id,
        node_id=10,
        run_id=1,
        resolved_inputs={},
        availability_audits={},
    )
    ctx.last_completed_stage = OrchestrationStage.VALIDATE_VISIBILITY.value
    ctx.diagnostics["last_completed_stage"] = OrchestrationStage.VALIDATE_VISIBILITY.value
    finalize_mock = AsyncMock(return_value=(mock_attempt, MagicMock()))
    update_run_mock = AsyncMock()

    with (
        patch(f"{_MOD}.finalize_attempt_with_snapshot", new=finalize_mock),
        patch(f"{_MOD}.update_run_status_from_attempts", new=update_run_mock),
    ):
        await node_orch._finalize_blocked(
            session,
            ctx,
            _make_config(),
            _make_node_def(),
            MagicMock(id=1),
            mock_attempt,
            blocker_code="PINNED_SOURCE_NOT_VISIBLE",
            error=PinnedSourceNotVisibleError("blocked"),
        )

    assert finalize_mock.await_args.kwargs["session"] is session
    assert (
        finalize_mock.await_args.kwargs["terminal_stage"]
        == OrchestrationStage.VALIDATE_VISIBILITY.value
    )
    update_run_mock.assert_awaited_once_with(session, 1)


@pytest.mark.asyncio
async def test_completed_path_updates_run_status_before_integrity_reload(
    mock_session,
    mock_run,
    mock_node,
    mock_attempt,
):
    """Successful orchestration must derive run status before the integrity reload."""
    order: list[str] = []

    async def _update_run_status(session, run_id):
        order.append("update_run_status")
        return "forecast_completed"

    async def _integrity_reload(session, run):
        order.append("integrity_reload")
        return run

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))
    patches = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=mock_attempt,
    )
    patches["update_run_status_from_attempts"] = AsyncMock(side_effect=_update_run_status)
    patches["load_logical_run_with_integrity"] = AsyncMock(side_effect=_integrity_reload)

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(
            mock_session,
            rolling_run_id=mock_run.id,
            rolling_node_id=mock_node.id,
        )

    assert outcome.status == "completed"
    assert order == ["update_run_status", "integrity_reload"]
    mock_session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_integrity_reload_failure_rolls_back_without_persisting_blocked_finalize(
    mock_session,
    mock_run,
    mock_node,
    mock_attempt,
):
    """Integrity reload failure must rollback the whole transaction and skip blocked persistence."""
    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))
    finalize_snapshot_mock = AsyncMock(return_value=(mock_attempt, MagicMock()))
    patches = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=mock_attempt,
    )
    patches["load_logical_run_with_integrity"] = AsyncMock(
        side_effect=RuntimeError("reload failed")
    )
    patches["finalize_attempt_with_snapshot"] = finalize_snapshot_mock

    with patch.multiple(_MOD, **patches):
        outcome = await orchestrate_node(
            mock_session,
            rolling_run_id=mock_run.id,
            rolling_node_id=mock_node.id,
        )

    assert outcome.status == "blocked"
    assert outcome.blocker_code == "ROLLING_ORCHESTRATION_INTEGRITY_RELOAD_FAILED"
    mock_session.rollback.assert_awaited_once()
    finalize_snapshot_mock.assert_not_awaited()


# ── Unsupported selection mode ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_historical_resolution_without_valid_candidates_blocks(mock_session):
    """Historical resolution without any visible or future candidate blocks as not found."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

    node_def = _make_node_def(selection_mode=UpstreamSelectionMode.HISTORICAL_RESOLUTION)
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
    mock_node.upstream_selection_mode = UpstreamSelectionMode.HISTORICAL_RESOLUTION
    mock_node.canonical_payload = node_def.model_dump(mode="python")

    mock_attempt = MagicMock()
    mock_attempt.id = 100
    mock_attempt.attempt_number = 1
    mock_attempt.started_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    mock_attempt.finished_at = None

    mock_session.execute = AsyncMock(side_effect=_build_session_side_effect(mock_run, mock_node))

    patches = _orchestration_patches(
        mock_run=mock_run,
        mock_node=mock_node,
        mock_attempt=mock_attempt,
        stage_resolve_historical_inputs=node_orch._stage_resolve_historical_inputs,
    )

    with (
        patch.multiple(_MOD, **patches),
        patch(f"{_MOD}._has_historical_candidates_outside_cutoff", AsyncMock(return_value=False)),
    ):
        outcome = await orchestrate_node(mock_session, rolling_run_id=1, rolling_node_id=10)
    assert outcome.status == "blocked"
    assert outcome.blocker_code == HistoricalSourceNotFoundError.code


# ═══════════════════════════════════════════════════════════════════════════════
# Task 9 source_ref_catalog fallback unit coverage
# ═══════════════════════════════════════════════════════════════════════════════


def _build_catalog_fallback_pinned_outcomes(
    *, source_ref_hash_a: str, source_ref_hash_b: str
) -> tuple:
    """Build a pair of pinned_daily_inputs outcomes for catalog-fallback tests."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

    def _identity(date_str: str, daily_id: int) -> ResolvedUpstreamSemanticIdentity:
        return _make_identity(
            source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
            source_role=f"task8_daily_prediction:{date_str}",
            semantic_payload_hash=str(daily_id).zfill(64)[:64],
            input_signature="4" * 64,
            canonical_payload_hash=str(daily_id).zfill(64)[:64],
        ).model_copy(
            update={
                "persistent_reference": PersistentUpstreamReference(
                    reference_type="database_row_id",
                    reference_value=daily_id,
                )
            }
        )

    identity_a = _identity("2026-03-01", 901)
    identity_b = _identity("2026-03-02", 902)
    return (
        node_orch.ResolvedInputOutcome(
            source_role=identity_a.source_role,
            source_type=identity_a.source_type,
            semantic_identity=identity_a,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_row_id",
                reference_value=901,
            ),
            authoritative_available_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
            canonical_identity_hash="1" * 64,
            canonical_payload_hash="5" * 64,
        ),
        node_orch.ResolvedInputOutcome(
            source_role=identity_b.source_role,
            source_type=identity_b.source_type,
            semantic_identity=identity_b,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_row_id",
                reference_value=902,
            ),
            authoritative_available_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
            canonical_identity_hash="2" * 64,
            canonical_payload_hash="6" * 64,
        ),
    )


def _build_catalog_fallback_verification_rows() -> list[dict]:
    """6 verification rows for 2 dates × 3 quantiles; forecast_quantile intentionally absent.

    Each row carries a unique source_ref_hash so the catalog can resolve
    a different forecast_quantile per row (P50, P80, P90 for each date).
    """
    rows: list[dict] = []
    quantile_to_hash = {"P50": "hash-p50", "P80": "hash-p80", "P90": "hash-p90"}
    for day, daily_id in [
        (date(2026, 3, 1), 901),
        (date(2026, 3, 2), 902),
    ]:
        for _quantile, hash_key in quantile_to_hash.items():
            rows.append(
                {
                    "source_ref_hash": hash_key,
                    # NOTE: no inline forecast_quantile → catalog fallback path
                    "verification_snapshot": {
                        "prediction_date": day,
                        # forecast_quantile is None → forces catalog lookup
                        "maturity_daily_prediction_id": daily_id,
                        "maturity_daily_prediction_forecast_run_id": 84,
                    },
                }
            )
    return rows


def _build_catalog_fallback_db_rows() -> list[MagicMock]:
    return [
        MagicMock(id=901, forecast_run_id=84, prediction_date=date(2026, 3, 1)),
        MagicMock(id=902, forecast_run_id=84, prediction_date=date(2026, 3, 2)),
    ]


def _build_catalog_fallback_payload_map(quantile_per_hash: dict[str, str]) -> dict[str, dict]:
    """Build source_ref_payload_by_hash with given quantile per hash key."""
    return {
        h: {"forecast_quantile": q, "source_quantity_kg": "20.000000"}
        for h, q in quantile_per_hash.items()
    }


@pytest.mark.asyncio
async def test_catalog_payload_resolves_forecast_quantile_via_source_ref_hash() -> None:
    """Catalog hit: row has source_ref_hash, no inline forecast_quantile, catalog has payload."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

    pinned_outcomes = _build_catalog_fallback_pinned_outcomes(
        source_ref_hash_a="hash-p50", source_ref_hash_b="hash-p80"
    )
    verification_rows = _build_catalog_fallback_verification_rows()
    source_ref_payload_by_hash = _build_catalog_fallback_payload_map(
        {"hash-p50": "P50", "hash-p80": "P80", "hash-p90": "P90"}
    )

    db_rows = _build_catalog_fallback_db_rows()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = db_rows
    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)

    result = await node_orch._verify_task8_daily_exact_set(
        session,
        forecast_run_id=84,
        pinned_daily_inputs=pinned_outcomes,
        task9_snapshot_rows=verification_rows,
        source_ref_payload_by_hash=source_ref_payload_by_hash,
    )

    # All 6 rows were resolved, with forecast_quantile from catalog for each.
    # Note: _Task8DailyExactSet exposes target_dates / task9_date_to_id / db_rows_by_date,
    # but the per-date row internals (task9_rows_by_date) are local to the function.
    # We assert the public surface here; the per-date quantile resolution is verified
    # indirectly through target_dates and task9_daily_ids.
    assert set(result.target_dates) == {date(2026, 3, 1), date(2026, 3, 2)}
    assert result.db_daily_ids == frozenset({901, 902})
    assert result.task9_daily_ids == frozenset({901, 902})
    assert result.db_date_to_id == {date(2026, 3, 1): 901, date(2026, 3, 2): 902}
    assert result.task9_date_to_id == {date(2026, 3, 1): 901, date(2026, 3, 2): 902}


@pytest.mark.asyncio
async def test_missing_source_ref_hash_raises_typed_error() -> None:
    """Catalog miss-path: row has no source_ref_hash AND no inline forecast_quantile."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

    pinned_outcomes = _build_catalog_fallback_pinned_outcomes(
        source_ref_hash_a="hash-p50", source_ref_hash_b="hash-p80"
    )
    rows = _build_catalog_fallback_verification_rows()
    # Strip source_ref_hash on the first row
    rows[0].pop("source_ref_hash", None)

    db_rows = _build_catalog_fallback_db_rows()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = db_rows
    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)

    with pytest.raises(Task9Task8AuthorityMismatchError) as exc_info:
        await node_orch._verify_task8_daily_exact_set(
            session,
            forecast_run_id=84,
            pinned_daily_inputs=pinned_outcomes,
            task9_snapshot_rows=rows,
            source_ref_payload_by_hash=_build_catalog_fallback_payload_map(
                {"hash-p50": "P50", "hash-p80": "P80", "hash-p90": "P90"}
            ),
        )
    assert "source_ref_hash is absent" in str(exc_info.value)


@pytest.mark.asyncio
async def test_missing_catalog_payload_raises_typed_error() -> None:
    """Catalog miss-path: row has source_ref_hash but catalog is empty for that hash."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

    pinned_outcomes = _build_catalog_fallback_pinned_outcomes(
        source_ref_hash_a="hash-p50", source_ref_hash_b="hash-p80"
    )
    rows = _build_catalog_fallback_verification_rows()
    # Only hash-p80 + hash-p90 are in the catalog; hash-p50 is missing
    source_ref_payload_by_hash = _build_catalog_fallback_payload_map(
        {"hash-p80": "P80", "hash-p90": "P90"}
    )

    db_rows = _build_catalog_fallback_db_rows()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = db_rows
    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)

    with pytest.raises(Task9Task8AuthorityMismatchError) as exc_info:
        await node_orch._verify_task8_daily_exact_set(
            session,
            forecast_run_id=84,
            pinned_daily_inputs=pinned_outcomes,
            task9_snapshot_rows=rows,
            source_ref_payload_by_hash=source_ref_payload_by_hash,
        )
    assert "missing from source_ref_catalog" in str(exc_info.value)


@pytest.mark.asyncio
async def test_invalid_catalog_forecast_quantile_raises_typed_error() -> None:
    """Catalog hit but payload.forecast_quantile is not in {P50, P80, P90}."""
    import backend.app.rolling_backtest.node_orchestration as node_orch

    pinned_outcomes = _build_catalog_fallback_pinned_outcomes(
        source_ref_hash_a="hash-p50", source_ref_hash_b="hash-p80"
    )
    rows = _build_catalog_fallback_verification_rows()
    # hash-p50 has invalid forecast_quantile
    source_ref_payload_by_hash = {
        "hash-p50": {"forecast_quantile": "INVALID", "source_quantity_kg": "20.000000"},
        "hash-p80": {"forecast_quantile": "P80", "source_quantity_kg": "24.000000"},
        "hash-p90": {"forecast_quantile": "P90", "source_quantity_kg": "28.000000"},
    }

    db_rows = _build_catalog_fallback_db_rows()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = db_rows
    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)

    with pytest.raises(Task9Task8AuthorityMismatchError) as exc_info:
        await node_orch._verify_task8_daily_exact_set(
            session,
            forecast_run_id=84,
            pinned_daily_inputs=pinned_outcomes,
            task9_snapshot_rows=rows,
            source_ref_payload_by_hash=source_ref_payload_by_hash,
        )
    assert "forecast quantile is invalid" in str(exc_info.value)


@pytest.mark.asyncio
async def test_decimal_string_quantity_bridge_matches_db_decimal() -> None:
    """Source quantity string (post-canonical_json_value round-trip) must match DB Decimal.

    The catalog stores source_quantity_kg as a string after canonical_json_value
    serialization (Decimal -> string for canonical form). The DB row stores
    p{50,80,90}_kg as Decimal. parse_decimal() must bridge the type mismatch.
    """
    from decimal import Decimal

    import backend.app.rolling_backtest.node_orchestration as node_orch

    pinned_outcomes = _build_catalog_fallback_pinned_outcomes(
        source_ref_hash_a="hash-p50", source_ref_hash_b="hash-p80"
    )
    rows = _build_catalog_fallback_verification_rows()
    # catalog: string form (canonical_json_value Decimal->string)
    source_ref_payload_by_hash = {
        "hash-p50": {"forecast_quantile": "P50", "source_quantity_kg": "20"},
        "hash-p80": {"forecast_quantile": "P80", "source_quantity_kg": "24"},
        "hash-p90": {"forecast_quantile": "P90", "source_quantity_kg": "28"},
    }

    # DB rows with Decimal type quantities (mimic Numeric(18, 6) column)
    db_rows = [
        MagicMock(
            id=901,
            forecast_run_id=84,
            prediction_date=date(2026, 3, 1),
            p50_kg=Decimal("20.000000"),
            p80_kg=Decimal("24.000000"),
            p90_kg=Decimal("28.000000"),
        ),
        MagicMock(
            id=902,
            forecast_run_id=84,
            prediction_date=date(2026, 3, 2),
            p50_kg=Decimal("20.000000"),
            p80_kg=Decimal("24.000000"),
            p90_kg=Decimal("28.000000"),
        ),
    ]
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = db_rows
    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)

    # First, verify _verify_task8_daily_exact_set succeeds (catalog hit, all 6 rows resolved)
    result = await node_orch._verify_task8_daily_exact_set(
        session,
        forecast_run_id=84,
        pinned_daily_inputs=pinned_outcomes,
        task9_snapshot_rows=rows,
        source_ref_payload_by_hash=source_ref_payload_by_hash,
    )
    assert len(result.db_rows_by_date) == 2

    # Second, verify the parse_decimal bridge: catalog "20" string == DB Decimal("20.000000")
    from backend.app.harvest_state.canonical import parse_decimal

    for hash_key, expected_db in [
        ("hash-p50", db_rows[0].p50_kg),
        ("hash-p80", db_rows[0].p80_kg),
        ("hash-p90", db_rows[0].p90_kg),
    ]:
        catalog_value = source_ref_payload_by_hash[hash_key]["source_quantity_kg"]
        bridged = parse_decimal(catalog_value)
        assert isinstance(bridged, Decimal)
        assert isinstance(expected_db, Decimal)
        assert bridged == expected_db, (
            f"parse_decimal({catalog_value!r}) = {bridged!r} must equal "
            f"DB Decimal {expected_db!r}"
        )
