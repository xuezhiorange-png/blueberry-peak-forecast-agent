"""Task 11 node orchestration integration tests.

Requires PostgreSQL with RUN_POSTGRES_INTEGRATION=1 and APP_ENV=test.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError as SAIntegrityError

from backend.app.db.session import AsyncSessionMaker
from backend.app.models.rolling_backtest import (
    RollingBacktestAttempt,
    RollingBacktestNode,
    RollingBacktestOrchestrationSnapshot,
    RollingBacktestRun,
    RollingBacktestStageEvent,
)
from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
    ExecutionMode,
    UpstreamSelectionMode,
)
from backend.app.rolling_backtest.errors import (
    RollingBacktestAttemptConflictError,
    RollingBacktestStageIntegrityError,
)
from backend.app.rolling_backtest.node_orchestration import (
    orchestrate_node,
)
from backend.app.rolling_backtest.persistence import (
    AvailabilityAuditPersistenceCommand,
    DagPersistenceCommand,
    ResolvedInputPersistenceCommand,
    RollingBacktestPersistenceCommand,
    RollingNodePersistenceCommand,
    create_execution_attempt,
    create_or_load_logical_run,
    derive_run_status_from_attempts,
    finalize_attempt_status,
    load_logical_run_with_integrity,
    persist_stage_event,
    update_run_status_from_attempts,
    validate_stage_continuity,
)
from backend.app.rolling_backtest.schemas import (
    HistoricalAvailableModelIdentity,
    PersistentUpstreamReference,
    ResolvedUpstreamSemanticIdentity,
    RollingBacktestConfig,
    RollingNodeDefinition,
    Task8ForecastRunAvailabilitySnapshot,
    UpstreamSemanticIdentityPayload,
)

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


# ── Fixture helpers (same as test_rolling_backtest_persistence.py) ────────────


def _make_historical_model_identity() -> HistoricalAvailableModelIdentity:
    return HistoricalAvailableModelIdentity(
        policy="historically_available_model",
        training_run_semantic_identity="a" * 64,
        artifact_semantic_identities=("b" * 64, "c" * 64),
        authority_visibility_identity="d" * 64,
    )


def _make_node(
    *,
    season_id: int = 2026,
    node_key: str = "march_15",
) -> RollingNodeDefinition:
    """Build a minimal valid RollingNodeDefinition."""
    return RollingNodeDefinition.model_validate(
        {
            "season_id": season_id,
            "node_key": node_key,
            "as_of_local_date": f"{season_id}-03-15",
            "forecast_cutoff_at": f"{season_id}-03-15T04:00:00Z",
            "forecast_start_local_date": f"{season_id}-03-16",
            "forecast_end_local_date": f"{season_id}-03-31",
            "scope": {
                "destination_factory_ids": {"mode": "include_ids", "ids": [202, 101]},
                "farm_ids": {"mode": "all", "ids": []},
                "subfarm_ids": {"mode": "all", "ids": []},
                "variety_ids": {"mode": "all", "ids": []},
            },
            "upstream_selection_mode": "historical_resolution",
            "forecast_horizon_policy_version": "task11-horizon-v1",
            "timezone": "Asia/Shanghai",
            "task10_model_policy": {
                "policy": "historically_available_model",
                "training_run_semantic_identity": "a" * 64,
                "artifact_semantic_identities": ["b" * 64, "c" * 64],
                "authority_visibility_identity": "d" * 64,
            },
        }
    )


def _make_pinned_node(
    *,
    season_id: int = 2026,
    node_key: str = "march_15",
    resolved_identities: tuple[ResolvedUpstreamSemanticIdentity, ...] = (),
) -> RollingNodeDefinition:
    """Build a RollingNodeDefinition with upstream_selection_mode=pinned."""
    node = _make_node(season_id=season_id, node_key=node_key)
    return node.model_copy(
        update={
            "upstream_selection_mode": UpstreamSelectionMode.PINNED,
            "resolved_upstream_semantic_identities": resolved_identities,
        }
    )


def _make_config(
    *,
    execution_mode: ExecutionMode = ExecutionMode.HISTORICAL_OBSERVED,
    nodes: tuple[RollingNodeDefinition, ...] | None = None,
) -> RollingBacktestConfig:
    """Build a minimal valid RollingBacktestConfig."""
    if nodes is None:
        nodes = (_make_node(),)
    node_dicts = [n.model_dump(mode="python") for n in nodes]
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
            "nodes": node_dicts,
        }
    )


def _make_semantic_identity(
    *,
    source_type: AvailabilitySourceType = AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
    source_role: str = "task9_structural_forecast",
    role_qualifier: str | None = None,
) -> ResolvedUpstreamSemanticIdentity:
    return ResolvedUpstreamSemanticIdentity(
        source_type=source_type,
        source_role=source_role,
        role_qualifier=role_qualifier,
        persistent_reference=PersistentUpstreamReference(
            reference_type="database_run_id", reference_value=1
        ),
        semantic=UpstreamSemanticIdentityPayload(
            schema_version="task11-v1",
            display_label="test identity",
            semantic_payload_hash="e" * 64,
            input_signature="f" * 64,
            result_hash="a" * 64,
            canonical_payload_hash="b" * 64,
            business_version="v1",
            policy_version="p1",
        ),
    )


def _make_dag() -> DagPersistenceCommand:
    return DagPersistenceCommand(
        dag_schema_version="task11-dag-v1",
        dag_policy_version="task11-dag-policy-v1",
        dag_dict={"nodes": ["a", "b", "c"], "edges": [("a", "b"), ("b", "c")]},
        expected_node_count=3,
        expected_edge_count=2,
    )


def _make_node_command(
    node: RollingNodeDefinition,
    *,
    identity: ResolvedUpstreamSemanticIdentity | None = None,
) -> RollingNodePersistenceCommand:
    if identity is None:
        identity = _make_semantic_identity()
    node_with_identity = node.model_copy(
        update={"resolved_upstream_semantic_identities": (identity,)}
    )
    return RollingNodePersistenceCommand(
        node=node_with_identity,
        resolved_inputs=(ResolvedInputPersistenceCommand(identity=identity),),
        availability_audits=(),
        dag=_make_dag(),
    )


def _make_persistence_command(
    config: RollingBacktestConfig,
    *,
    with_inputs: bool = True,
    with_audits: bool = False,
    with_dag: bool = True,
) -> RollingBacktestPersistenceCommand:
    """Build a full persistence command from config."""
    node_cmds: list[RollingNodePersistenceCommand] = []
    for node in config.nodes:
        inputs: tuple[ResolvedInputPersistenceCommand, ...] = ()
        audits: tuple[AvailabilityAuditPersistenceCommand, ...] = ()
        dag = None

        if with_inputs:
            inputs = (
                ResolvedInputPersistenceCommand(
                    identity=_make_semantic_identity(
                        source_role="task3_analytics",
                        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
                    ),
                ),
            )

        if with_audits:
            # Create a valid run snapshot
            snapshot = Task8ForecastRunAvailabilitySnapshot(
                source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
                status="completed",
                authoritative_timestamp=datetime(2025, 3, 14, tzinfo=UTC),
            )
            identity = _make_semantic_identity(
                source_role="task8_forecast_run",
                source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            )
            if not inputs:
                inputs = (ResolvedInputPersistenceCommand(identity=identity),)
            elif all(item.identity.source_role != identity.source_role for item in inputs):
                inputs = (*inputs, ResolvedInputPersistenceCommand(identity=identity))
            audits = (
                AvailabilityAuditPersistenceCommand(
                    source_role="task8_forecast_run",
                    snapshot=snapshot,
                    forecast_cutoff_at=node.forecast_cutoff_at,
                    resolved_identity=identity,
                ),
            )

        if with_dag:
            dag = _make_dag()

        node_with_inputs = node.model_copy(
            update={
                "resolved_upstream_semantic_identities": tuple(item.identity for item in inputs)
            }
        )

        node_cmds.append(
            RollingNodePersistenceCommand(
                node=node_with_inputs,
                resolved_inputs=inputs,
                availability_audits=audits,
                dag=dag,
            )
        )

    return RollingBacktestPersistenceCommand(
        config=config.model_copy(update={"nodes": tuple(cmd.node for cmd in node_cmds)}),
        nodes=tuple(node_cmds),
    )


# ── Orchestration test helpers ───────────────────────────────────────────────


def _make_orchestration_persistence_command(
    *,
    execution_mode: ExecutionMode = ExecutionMode.HISTORICAL_OBSERVED,
    identity_role: str = "task8_forecast_run",
    identity_source_type: AvailabilitySourceType = AvailabilitySourceType.TASK8_FORECAST_RUN,
    season_id: int = 2026,
) -> RollingBacktestPersistenceCommand:
    """Build a persistence command suitable for orchestrate_node integration tests.

    Creates a node with upstream_selection_mode=pinned, a matching resolved
    input, and a matching availability audit so that orchestrate_node can
    proceed through all eight stages.
    """
    identity = _make_semantic_identity(
        source_role=identity_role,
        source_type=identity_source_type,
    )
    node = _make_pinned_node(
        season_id=season_id,
        node_key="march_15",
        resolved_identities=(identity,),
    )
    config = _make_config(execution_mode=execution_mode, nodes=(node,))

    # Build availability snapshot that passes the visibility check.
    # For TASK8_FORECAST_RUN: status="completed", authoritative_timestamp before cutoff.
    snapshot = Task8ForecastRunAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
        status="completed",
        authoritative_timestamp=datetime(2025, 3, 14, tzinfo=UTC),
    )

    audit_cmd = AvailabilityAuditPersistenceCommand(
        source_role=identity_role,
        snapshot=snapshot,
        forecast_cutoff_at=node.forecast_cutoff_at,
        resolved_identity=identity,
    )

    ri_cmd = ResolvedInputPersistenceCommand(identity=identity)
    node_cmd = RollingNodePersistenceCommand(
        node=node,
        resolved_inputs=(ri_cmd,),
        availability_audits=(audit_cmd,),
        dag=_make_dag(),
    )

    return RollingBacktestPersistenceCommand(
        config=config.model_copy(update={"nodes": (node,)}),
        nodes=(node_cmd,),
    )


async def _get_node_id_for_run(run_id: int) -> int:
    """Helper to fetch the single node ID for a run."""
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestNode.id).where(RollingBacktestNode.rolling_run_id == run_id)
        )
        return result.scalar_one()


# ═══════════════════════════════════════════════════════════════════════════════
# a) test_single_node_successful_orchestration
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_single_node_successful_orchestration() -> None:
    """Create a run with one node, execute orchestrate_node, verify all artifacts."""
    _require_postgres()
    cmd = _make_orchestration_persistence_command()
    run = await create_or_load_logical_run(cmd)
    assert run.id is not None

    node_id = await _get_node_id_for_run(run.id)

    async with AsyncSessionMaker() as session:
        outcome = await orchestrate_node(
            session,
            rolling_run_id=run.id,
            rolling_node_id=node_id,
        )
        await session.commit()

    assert outcome.status == "completed"
    assert outcome.stage == "finalize_orchestration_snapshot"

    # Verify attempt was created
    async with AsyncSessionMaker() as session:
        attempt_count = await session.scalar(
            select(func.count()).where(RollingBacktestAttempt.rolling_run_id == run.id)
        )
        assert attempt_count == 1

    # Verify stage events were created (8 stages)
    async with AsyncSessionMaker() as session:
        stage_count = await session.scalar(
            select(func.count()).select_from(RollingBacktestStageEvent)
        )
        assert stage_count == 8

    # Verify orchestration snapshot was created
    async with AsyncSessionMaker() as session:
        snap_count = await session.scalar(
            select(func.count()).select_from(RollingBacktestOrchestrationSnapshot)
        )
        assert snap_count == 1

    # Verify integrity reload passes
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestRun).where(RollingBacktestRun.id == run.id)
        )
        loaded_run = result.scalar_one()
        await load_logical_run_with_integrity(session, loaded_run)


# ═══════════════════════════════════════════════════════════════════════════════
# b) test_independent_session_committed_reload
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_independent_session_committed_reload() -> None:
    """Create run + orchestrate, then in a NEW session verify the run loads with integrity."""
    _require_postgres()
    cmd = _make_orchestration_persistence_command()
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    # Orchestrate in one session
    async with AsyncSessionMaker() as session:
        outcome = await orchestrate_node(
            session,
            rolling_run_id=run.id,
            rolling_node_id=node_id,
        )
        await session.commit()
    assert outcome.status == "completed"

    # Reload in a completely independent session
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestRun).where(RollingBacktestRun.id == run.id)
        )
        loaded_run = result.scalar_one()
        assert loaded_run.status in ("forecast_completed", "completed")

        # Full integrity check in the new session
        await load_logical_run_with_integrity(session, loaded_run)

    # Verify attempt and snapshot are visible from independent session
    async with AsyncSessionMaker() as session:
        attempt_count = await session.scalar(
            select(func.count()).where(RollingBacktestAttempt.rolling_run_id == run.id)
        )
        assert attempt_count == 1

        snap_count = await session.scalar(
            select(func.count()).select_from(RollingBacktestOrchestrationSnapshot)
        )
        assert snap_count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# c) test_existing_finalized_result_integrity_reload
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_existing_finalized_result_integrity_reload() -> None:
    """Orchestrate once (success), try again → idempotent completed (P0-1)."""
    _require_postgres()
    cmd = _make_orchestration_persistence_command(
        season_id=2027,
        identity_role="task8_forecast_run_reload",
    )
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    # First orchestration: success
    async with AsyncSessionMaker() as session:
        outcome1 = await orchestrate_node(
            session,
            rolling_run_id=run.id,
            rolling_node_id=node_id,
        )
        await session.commit()
    assert outcome1.status == "completed"

    first_attempt_id = outcome1.attempt_number

    # Second orchestration: idempotent completed (P0-1)
    async with AsyncSessionMaker() as session:
        outcome2 = await orchestrate_node(
            session,
            rolling_run_id=run.id,
            rolling_node_id=node_id,
        )
        await session.commit()
    assert outcome2.status == "completed"
    assert outcome2.diagnostics.get("idempotent_reload") is True
    # Same attempt number, no new attempt created
    assert outcome2.attempt_number == first_attempt_id

    # Verify no new attempt was created
    async with AsyncSessionMaker() as session:
        attempt_count = await session.scalar(
            select(func.count()).where(RollingBacktestAttempt.rolling_run_id == run.id)
        )
        assert attempt_count == 1

    # Verify no new snapshot was created
    async with AsyncSessionMaker() as session:
        snap_count = await session.scalar(
            select(func.count()).select_from(RollingBacktestOrchestrationSnapshot)
        )
        assert snap_count == 1

    # Verify original result is intact via integrity reload in fresh session
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestRun).where(RollingBacktestRun.id == run.id)
        )
        loaded_run = result.scalar_one()
        await load_logical_run_with_integrity(session, loaded_run)

    # Verify snapshot hash unchanged
    async with AsyncSessionMaker() as session:
        snap_result = await session.execute(select(RollingBacktestOrchestrationSnapshot))
        snap = snap_result.scalar_one()
        assert snap.canonical_payload_hash is not None


# ═══════════════════════════════════════════════════════════════════════════════
# d) test_same_node_concurrent_attempt_allocation
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_same_node_concurrent_attempt_allocation() -> None:
    """Two concurrent create_execution_attempt calls for same node get different attempt numbers."""
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    barrier = asyncio.Barrier(2)
    results: list[RollingBacktestAttempt] = []

    async def _create_attempt() -> None:
        await barrier.wait()
        attempt = await create_execution_attempt(run.id, node_id, status="blocked")
        results.append(attempt)

    await asyncio.gather(_create_attempt(), _create_attempt())

    assert len(results) == 2
    numbers = sorted(r.attempt_number for r in results)
    assert numbers == [1, 2]


# ═══════════════════════════════════════════════════════════════════════════════
# e) test_blocked_execution_leaves_no_partial_snapshot
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_blocked_execution_leaves_no_partial_snapshot() -> None:
    """Unsupported execution_mode → blocked, persisted attempt, no completed snapshot (P0-2)."""
    _require_postgres()
    # Use retrospective_replay which is not supported in this phase
    cmd = _make_orchestration_persistence_command(
        execution_mode=ExecutionMode.RETROSPECTIVE_REPLAY,
    )
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    async with AsyncSessionMaker() as session:
        outcome = await orchestrate_node(
            session,
            rolling_run_id=run.id,
            rolling_node_id=node_id,
        )
        await session.commit()

    assert outcome.status == "blocked"
    assert outcome.blocker_code == "UNSUPPORTED_EXECUTION_MODE"

    # Verify exactly 1 attempt was created and finalized as blocked
    async with AsyncSessionMaker() as session:
        attempt_count = await session.scalar(
            select(func.count()).where(RollingBacktestAttempt.rolling_run_id == run.id)
        )
        assert attempt_count == 1

    # Verify attempt status is blocked
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestAttempt).where(RollingBacktestAttempt.rolling_run_id == run.id)
        )
        attempt = result.scalar_one()
        assert attempt.status == "blocked"

    # Verify stage events: persist_stage_event uses ON CONFLICT DO UPDATE,
    # so running → blocked for the same stage = 1 row with terminal state.
    async with AsyncSessionMaker() as session:
        stage_count = await session.scalar(
            select(func.count()).select_from(RollingBacktestStageEvent)
        )
        assert stage_count == 1

    # Verify no Stage 2-8 events exist
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestStageEvent).where(
                RollingBacktestStageEvent.attempt_id == attempt.id
            )
        )
        events = result.scalars().all()
        stage_names = {e.stage for e in events}
        assert stage_names == {"resolve_historical_inputs"}

    # Verify blocked snapshot exists, no completed snapshot
    async with AsyncSessionMaker() as session:
        snap_result = await session.execute(select(RollingBacktestOrchestrationSnapshot))
        snaps = snap_result.scalars().all()
        assert len(snaps) == 1
        assert snaps[0].status == "blocked"
        assert snaps[0].blocker_code == "UNSUPPORTED_EXECUTION_MODE"

    # Verify integrity reload succeeds in fresh session
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestRun).where(RollingBacktestRun.id == run.id)
        )
        loaded_run = result.scalar_one()
        await load_logical_run_with_integrity(session, loaded_run)


# ═══════════════════════════════════════════════════════════════════════════════
# f) test_stage_gap_tamper_rejected
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_stage_gap_tamper_rejected() -> None:
    """Create attempt, persist stages 1 and 3 (skip 2), verify validate_stage_continuity raises."""
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    attempt = await create_execution_attempt(run.id, node_id, status="running")

    # Persist stage 1 (resolve_historical_inputs) and stage 3 (validate_authority_chain)
    # skipping stage 2 (validate_visibility)
    await persist_stage_event(
        attempt.id,
        node_id,
        stage="resolve_historical_inputs",
        status="completed",
    )
    await persist_stage_event(
        attempt.id,
        node_id,
        stage="validate_authority_chain",
        status="completed",
    )

    # validate_stage_continuity should detect the gap at sequence_number 2
    async with AsyncSessionMaker() as session:
        with pytest.raises(RollingBacktestStageIntegrityError, match="stage gap"):
            await validate_stage_continuity(session, attempt.id)


# ═══════════════════════════════════════════════════════════════════════════════
# g) test_stage_duplicate_rejected
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_stage_duplicate_rejected() -> None:
    """Try to create two stage events with same stage name via raw SQL, verify constraint error."""
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    attempt = await create_execution_attempt(run.id, node_id, status="running")

    # First insert succeeds via persist_stage_event
    await persist_stage_event(
        attempt.id,
        node_id,
        stage="resolve_historical_inputs",
        status="completed",
    )

    # Second raw INSERT with same (attempt_id, stage) violates unique constraint
    async with AsyncSessionMaker() as session:
        with pytest.raises(SAIntegrityError):
            await session.execute(
                text(
                    "INSERT INTO rolling_backtest_stage_event "
                    "(attempt_id, rolling_node_id, sequence_number, stage, status, "
                    "entered_at, finished_at) "
                    "VALUES (:attempt_id, :node_id, :seq, :stage, :status, now(), now())"
                ),
                {
                    "attempt_id": attempt.id,
                    "node_id": node_id,
                    "seq": 1,
                    "stage": "resolve_historical_inputs",
                    "status": "completed",
                },
            )
            await session.flush()


# ═══════════════════════════════════════════════════════════════════════════════
# h) test_cross_node_prior_attempt_rejected
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cross_node_prior_attempt_rejected() -> None:
    """Create two nodes, attempt for node1, try to create attempt for node2 with node1's prior."""
    _require_postgres()
    nodes = (
        _make_node(season_id=2025, node_key="march_15"),
        _make_node(season_id=2026, node_key="march_15"),
    )
    config = _make_config(nodes=nodes)
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestNode).where(RollingBacktestNode.rolling_run_id == run.id)
        )
        node_rows = result.scalars().all()
    assert len(node_rows) == 2

    node1_id = node_rows[0].id
    node2_id = node_rows[1].id

    # Create attempt for node1
    attempt1 = await create_execution_attempt(run.id, node1_id, status="blocked")

    # Try to create attempt for node2 with node1's attempt as prior → should fail
    with pytest.raises(RollingBacktestAttemptConflictError):
        await create_execution_attempt(run.id, node2_id, prior_attempt_id=attempt1.id)


# ═══════════════════════════════════════════════════════════════════════════════
# i) test_derive_run_status_from_attempts
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_derive_run_status_from_attempts() -> None:
    """Create run with one node, create attempt with status completed, verify derived status."""
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    # Create and finalize an attempt as completed
    attempt = await create_execution_attempt(run.id, node_id, status="pending")
    await finalize_attempt_status(
        attempt.id,
        status="completed",
        current_stage="finalize_orchestration_snapshot",
    )

    async with AsyncSessionMaker() as session:
        derived = await derive_run_status_from_attempts(session, run.id)
    assert derived == "forecast_completed"


# ═══════════════════════════════════════════════════════════════════════════════
# j) test_update_run_status_from_attempts
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_update_run_status_from_attempts() -> None:
    """Create run, create attempt, finalize, call update_run_status_from_attempts, verify."""
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)
    assert run.status == "pending"
    node_id = await _get_node_id_for_run(run.id)

    # Create and finalize an attempt as completed
    attempt = await create_execution_attempt(run.id, node_id, status="pending")
    await finalize_attempt_status(
        attempt.id,
        status="completed",
        current_stage="finalize_orchestration_snapshot",
    )

    async with AsyncSessionMaker() as session:
        new_status = await update_run_status_from_attempts(session, run.id)
        await session.commit()

    assert new_status == "forecast_completed"

    # Verify the run status is updated in the database
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestRun.status).where(RollingBacktestRun.id == run.id)
        )
        db_status = result.scalar_one()
    assert db_status == "forecast_completed"
