"""Task 11 0013 persistence: migration round-trip, tamper, concurrency, integrity reload.

Requires PostgreSQL with RUN_POSTGRES_INTEGRATION=1 and APP_ENV=test.
"""

from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, text

from backend.app.db.session import AsyncSessionMaker
from backend.app.models.rolling_backtest import (
    RollingBacktestAttempt,
    RollingBacktestNode,
    RollingBacktestRun,
)
from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
    ExecutionMode,
)
from backend.app.rolling_backtest.errors import (
    RollingBacktestAttemptConflictError,
    RollingBacktestAuthorityBindingError,
    RollingBacktestCanonicalParityError,
    RollingBacktestStageIntegrityError,
)
from backend.app.rolling_backtest.persistence import (
    DagPersistenceCommand,
    ResolvedInputPersistenceCommand,
    RollingBacktestPersistenceCommand,
    RollingNodePersistenceCommand,
    create_execution_attempt,
    create_or_load_logical_run,
    finalize_attempt_status,
    finalize_attempt_with_snapshot,
    load_logical_run_with_integrity,
    persist_orchestration_snapshot,
    persist_stage_event,
    validate_orchestration_snapshot_consistency,
    validate_stage_continuity,
)
from backend.app.rolling_backtest.schemas import (
    ResolvedUpstreamSemanticIdentity,
    RollingBacktestConfig,
    RollingNodeDefinition,
    UpstreamSemanticIdentityPayload,
)

_config_counter = 0


pytestmark = pytest.mark.integration


def _next_suffix() -> str:
    global _config_counter
    _config_counter += 1
    return f"_{_config_counter}"


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("RUN_POSTGRES_INTEGRATION=1 required")
    if os.getenv("APP_ENV") != "test":
        pytest.skip("APP_ENV=test required")


def _make_node(
    season_id: int = 2025,
    as_of_local_date: str = "2025-03-15",
) -> RollingNodeDefinition:
    from backend.app.rolling_backtest.enums import (
        DefaultNodeKey,
        Task10ModelPolicy,
        UpstreamSelectionMode,
    )

    as_of = date.fromisoformat(as_of_local_date)
    node_key = {
        (2, 28): DefaultNodeKey.FEBRUARY_END,
        (2, 29): DefaultNodeKey.FEBRUARY_END,
        (3, 15): DefaultNodeKey.MARCH_15,
        (3, 31): DefaultNodeKey.MARCH_31,
        (4, 7): DefaultNodeKey.APRIL_07,
    }.get((as_of.month, as_of.day))
    assert node_key is not None, f"unsupported test as_of_local_date {as_of_local_date}"

    return RollingNodeDefinition.model_validate(
        {
            "season_id": season_id,
            "node_key": node_key.value,
            "as_of_local_date": as_of.isoformat(),
            "forecast_cutoff_at": datetime(
                as_of.year,
                as_of.month,
                as_of.day,
                9,
                30,
                tzinfo=ZoneInfo("Asia/Shanghai"),
            ).isoformat(),
            "forecast_start_local_date": (as_of + timedelta(days=1)).isoformat(),
            "forecast_end_local_date": date(season_id, 5, 31).isoformat(),
            "scope": {
                "destination_factory_ids": {"mode": "include_ids", "ids": [1]},
                "farm_ids": {"mode": "all", "ids": []},
                "subfarm_ids": {"mode": "all", "ids": []},
                "variety_ids": {"mode": "all", "ids": []},
            },
            "upstream_selection_mode": UpstreamSelectionMode.HISTORICAL_RESOLUTION.value,
            "forecast_horizon_policy_version": "v1",
            "task10_model_policy": {
                "policy": Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL.value,
                "training_run_semantic_identity": "a" * 64,
                "artifact_semantic_identities": ["b" * 64, "c" * 64],
                "authority_visibility_identity": "d" * 64,
            },
            "timezone": "Asia/Shanghai",
            "resolved_upstream_semantic_identities": [
                {
                    "source_type": "task3_analytics_build",
                    "source_role": "task3_analytics",
                    "role_qualifier": None,
                    "semantic": {
                        "schema_version": "v1",
                        "display_label": "display:task3_analytics",
                        "semantic_payload_hash": "f" * 64,
                        "input_signature": "a" * 64,
                        "config_hash": "b" * 64,
                        "result_hash": "c" * 64,
                        "canonical_payload_hash": "d" * 64,
                        "artifact_payload_hash": None,
                        "policy_version": "v1",
                        "business_version": "v1",
                    },
                    "persistent_reference": None,
                }
            ],
        }
    )


def _make_config(
    nodes: tuple[RollingNodeDefinition, ...] | None = None,
    *,
    suffix: str | None = None,
) -> RollingBacktestConfig:
    from backend.app.rolling_backtest.schemas import RollingBacktestConfig

    if suffix is None:
        suffix = _next_suffix()
    sv = f"v1{suffix}"
    if nodes is None:
        nodes = (_make_node(),)
    return RollingBacktestConfig(
        execution_mode=ExecutionMode.HISTORICAL_OBSERVED,
        rolling_schema_version=f"task11-rolling-{sv}",
        canonical_serialization_version=sv,
        availability_registry_version=sv,
        node_calendar_version=sv,
        forecast_horizon_policy_version=sv,
        upstream_selection_policy_version=sv,
        metric_policy_version=sv,
        calendar_phase_policy_version=sv,
        cutoff_policy_version=sv,
        cutoff_timezone="Asia/Shanghai",
        cutoff_local_time="09:30",
        nodes=nodes,
    )


def _make_semantic_identity(
    source_role: str = "task3_analytics",
    source_type: AvailabilitySourceType = AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
) -> ResolvedUpstreamSemanticIdentity:
    return ResolvedUpstreamSemanticIdentity(
        source_type=source_type,
        source_role=source_role,
        role_qualifier=None,
        persistent_reference=None,
        semantic=UpstreamSemanticIdentityPayload(
            schema_version="v1",
            display_label=f"display:{source_role}",
            semantic_payload_hash="f" * 64,
            input_signature="a" * 64,
            config_hash="b" * 64,
            result_hash="c" * 64,
            canonical_payload_hash="d" * 64,
            artifact_payload_hash=None,
            policy_version="v1",
            business_version="v1",
        ),
    )


def _make_dag() -> DagPersistenceCommand:
    return DagPersistenceCommand(
        dag_schema_version="v1",
        dag_policy_version="v1",
        dag_dict={"nodes": ["n1"], "edges": []},
        expected_node_count=1,
        expected_edge_count=0,
    )


def _make_persistence_command(
    config: RollingBacktestConfig,
) -> RollingBacktestPersistenceCommand:
    node_cmds: list[RollingNodePersistenceCommand] = []
    for node in config.nodes:
        inputs: tuple[ResolvedInputPersistenceCommand, ...] = (
            ResolvedInputPersistenceCommand(
                identity=_make_semantic_identity(
                    source_role="task3_analytics",
                    source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
                ),
            ),
        )
        node_cmds.append(
            RollingNodePersistenceCommand(
                node=node,
                resolved_inputs=inputs,
                availability_audits=(),
                dag=_make_dag(),
            )
        )
    return RollingBacktestPersistenceCommand(
        config=config,
        nodes=tuple(node_cmds),
    )


async def _first_node_id(run_id: int) -> int:
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestNode).where(RollingBacktestNode.rolling_run_id == run_id).limit(1)
        )
        node = result.scalar_one_or_none()
        assert node is not None, f"no node found for run {run_id}"
        return node.id


# ═══════════════════════════════════════════════════════════════════════════════
# Migration round-trip
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_0013_migration_tables_exist() -> None:
    """Verify 0013 tables exist after migration."""
    _require_postgres()
    async with AsyncSessionMaker() as session:
        for table in ("rolling_backtest_stage_event", "rolling_backtest_orchestration_snapshot"):
            result = await session.execute(
                text(f"SELECT 1 FROM information_schema.tables WHERE table_name = '{table}'")
            )
            assert result.scalar() == 1, f"table {table} missing"


@pytest.mark.asyncio
async def test_0013_attempt_has_node_id_column() -> None:
    """Verify rolling_backtest_attempt has rolling_node_id column."""
    _require_postgres()
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'rolling_backtest_attempt' "
                "AND column_name = 'rolling_node_id'"
            )
        )
        assert result.scalar() == "NO", "rolling_node_id must be NOT NULL"


# ═══════════════════════════════════════════════════════════════════════════════
# Attempt lifecycle with node_id
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_attempt_created_with_node_id() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)
    node_id = await _first_node_id(run.id)

    a1 = await create_execution_attempt(run.id, node_id, status="running")
    assert a1.rolling_node_id == node_id
    assert a1.attempt_number == 1

    # Finalize a1 before creating retry
    await finalize_attempt_status(a1.id, status="failed", current_stage="test_fail")
    a2 = await create_execution_attempt(run.id, node_id, status="failed")
    assert a2.rolling_node_id == node_id
    assert a2.attempt_number == 2

    # Finalize a2 and create a3
    await finalize_attempt_status(a2.id, status="failed", current_stage="test_fail")
    a3 = await create_execution_attempt(run.id, node_id, status="running")
    assert a3.rolling_node_id == node_id
    assert a3.attempt_number == 3


@pytest.mark.asyncio
async def test_attempt_unique_per_node() -> None:
    _require_postgres()
    nodes = (_make_node(season_id=2025), _make_node(season_id=2026, as_of_local_date="2026-03-15"))
    config = _make_config(nodes=nodes)
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestNode)
            .where(RollingBacktestNode.rolling_run_id == run.id)
            .order_by(RollingBacktestNode.id)
        )
        db_nodes = result.scalars().all()
    assert len(db_nodes) == 2

    nid1, nid2 = db_nodes[0].id, db_nodes[1].id

    a1 = await create_execution_attempt(run.id, nid1, status="running")
    a2 = await create_execution_attempt(run.id, nid2, status="running")
    assert a1.attempt_number == 1
    assert a2.attempt_number == 1  # Different nodes => independent counters


@pytest.mark.asyncio
async def test_integrity_reload_allows_attempt_one_per_node() -> None:
    _require_postgres()
    nodes = (_make_node(season_id=2025), _make_node(season_id=2026, as_of_local_date="2026-03-15"))
    config = _make_config(nodes=nodes)
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestNode)
            .where(RollingBacktestNode.rolling_run_id == run.id)
            .order_by(RollingBacktestNode.id)
        )
        db_nodes = result.scalars().all()
    nid1, nid2 = db_nodes[0].id, db_nodes[1].id

    await create_execution_attempt(run.id, nid1, status="running")
    await create_execution_attempt(run.id, nid2, status="running")

    async with AsyncSessionMaker() as session:
        stored_run = await session.get(RollingBacktestRun, run.id)
        assert stored_run is not None
        reloaded = await load_logical_run_with_integrity(session, stored_run)
        assert reloaded.id == run.id


@pytest.mark.asyncio
async def test_integrity_reload_allows_retry_on_one_node_only() -> None:
    _require_postgres()
    nodes = (_make_node(season_id=2025), _make_node(season_id=2026, as_of_local_date="2026-03-15"))
    config = _make_config(nodes=nodes)
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestNode)
            .where(RollingBacktestNode.rolling_run_id == run.id)
            .order_by(RollingBacktestNode.id)
        )
        db_nodes = result.scalars().all()
    nid1, nid2 = db_nodes[0].id, db_nodes[1].id

    first = await create_execution_attempt(run.id, nid1, status="running")
    await finalize_attempt_status(
        first.id,
        status="failed",
        current_stage="resolve_historical_inputs",
    )
    retry = await create_execution_attempt(run.id, nid1, status="running")
    other = await create_execution_attempt(run.id, nid2, status="running")
    assert retry.attempt_number == 2
    assert other.attempt_number == 1

    async with AsyncSessionMaker() as session:
        stored_run = await session.get(RollingBacktestRun, run.id)
        assert stored_run is not None
        reloaded = await load_logical_run_with_integrity(session, stored_run)
        assert reloaded.id == run.id


@pytest.mark.asyncio
async def test_attempt_cross_node_prior_blocked() -> None:
    _require_postgres()
    nodes = (_make_node(season_id=2025), _make_node(season_id=2026, as_of_local_date="2026-03-15"))
    config = _make_config(nodes=nodes)
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestNode)
            .where(RollingBacktestNode.rolling_run_id == run.id)
            .order_by(RollingBacktestNode.id)
        )
        db_nodes = result.scalars().all()
    nid1, nid2 = db_nodes[0].id, db_nodes[1].id

    a1 = await create_execution_attempt(run.id, nid1, status="failed")
    # Attempt to create on nid2 with prior_attempt_id pointing to nid1's attempt
    with pytest.raises(RollingBacktestAttemptConflictError):
        await create_execution_attempt(run.id, nid2, status="running", prior_attempt_id=a1.id)


# ═══════════════════════════════════════════════════════════════════════════════
# Stage event persistence
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_persist_stage_event_entering() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)
    node_id = await _first_node_id(run.id)
    attempt = await create_execution_attempt(run.id, node_id, status="running")

    event = await persist_stage_event(
        attempt.id, node_id, stage="resolve_historical_inputs", status="running"
    )
    assert event.sequence_number == 1
    assert event.status == "running"
    assert event.finished_at is None


@pytest.mark.asyncio
async def test_persist_stage_event_completing() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)
    node_id = await _first_node_id(run.id)
    attempt = await create_execution_attempt(run.id, node_id, status="running")

    # Enter
    event = await persist_stage_event(
        attempt.id, node_id, stage="resolve_historical_inputs", status="running"
    )
    # Complete
    updated = await persist_stage_event(
        attempt.id, node_id, stage="resolve_historical_inputs", status="completed"
    )
    assert updated.id == event.id
    assert updated.status == "completed"
    assert updated.finished_at is not None


@pytest.mark.asyncio
async def test_persist_stage_event_duplicate_stage_blocked() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)
    node_id = await _first_node_id(run.id)
    attempt = await create_execution_attempt(run.id, node_id, status="running")

    event1 = await persist_stage_event(
        attempt.id, node_id, stage="resolve_historical_inputs", status="running"
    )
    # Entering same stage again should update, not insert new
    event2 = await persist_stage_event(
        attempt.id, node_id, stage="resolve_historical_inputs", status="completed"
    )
    assert event2.id == event1.id  # Same row updated


@pytest.mark.asyncio
async def test_persist_stage_event_with_blocker() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)
    node_id = await _first_node_id(run.id)
    attempt = await create_execution_attempt(run.id, node_id, status="running")

    event = await persist_stage_event(
        attempt.id,
        node_id,
        stage="validate_visibility",
        status="blocked",
        structured_error_code="VISIBILITY_BLOCKED",
    )
    assert event.status == "blocked"
    assert event.structured_error_code == "VISIBILITY_BLOCKED"
    assert event.finished_at is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Stage continuity validation
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_validate_stage_continuity_happy_path() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)
    node_id = await _first_node_id(run.id)
    attempt = await create_execution_attempt(run.id, node_id, status="running")

    for stage in ("resolve_historical_inputs", "validate_visibility", "validate_authority_chain"):
        await persist_stage_event(attempt.id, node_id, stage=stage, status="completed")

    async with AsyncSessionMaker() as session:
        await validate_stage_continuity(
            session, attempt.id, terminal_stage="validate_authority_chain"
        )


@pytest.mark.asyncio
async def test_validate_stage_continuity_gap() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)
    node_id = await _first_node_id(run.id)
    attempt = await create_execution_attempt(run.id, node_id, status="running")

    await persist_stage_event(
        attempt.id, node_id, stage="resolve_historical_inputs", status="completed"
    )
    # Skip stage 2 (validate_visibility), insert stage 3
    await persist_stage_event(
        attempt.id, node_id, stage="validate_authority_chain", status="completed"
    )

    async with AsyncSessionMaker() as session:
        with pytest.raises(RollingBacktestStageIntegrityError):
            await validate_stage_continuity(
                session, attempt.id, terminal_stage="validate_authority_chain"
            )


@pytest.mark.asyncio
async def test_validate_stage_continuity_still_running() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)
    node_id = await _first_node_id(run.id)
    attempt = await create_execution_attempt(run.id, node_id, status="running")

    await persist_stage_event(
        attempt.id, node_id, stage="resolve_historical_inputs", status="completed"
    )
    await persist_stage_event(attempt.id, node_id, stage="validate_visibility", status="running")

    async with AsyncSessionMaker() as session:
        with pytest.raises(RollingBacktestStageIntegrityError):
            await validate_stage_continuity(
                session, attempt.id, terminal_stage="validate_authority_chain"
            )


@pytest.mark.asyncio
async def test_validate_stage_continuity_beyond_terminal() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)
    node_id = await _first_node_id(run.id)
    attempt = await create_execution_attempt(run.id, node_id, status="running")

    await persist_stage_event(
        attempt.id, node_id, stage="resolve_historical_inputs", status="completed"
    )
    await persist_stage_event(attempt.id, node_id, stage="validate_visibility", status="completed")
    await persist_stage_event(
        attempt.id, node_id, stage="validate_authority_chain", status="completed"
    )
    # Extra stage beyond terminal
    await persist_stage_event(
        attempt.id, node_id, stage="resolve_or_replay_task8", status="completed"
    )

    async with AsyncSessionMaker() as session:
        with pytest.raises(RollingBacktestStageIntegrityError):
            await validate_stage_continuity(
                session, attempt.id, terminal_stage="validate_authority_chain"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Cross-table rolling_node_id tamper
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_stage_event_node_id_tamper_detected() -> None:
    _require_postgres()
    nodes = (_make_node(season_id=2025), _make_node(season_id=2026, as_of_local_date="2026-03-15"))
    config = _make_config(nodes=nodes)
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestNode)
            .where(RollingBacktestNode.rolling_run_id == run.id)
            .order_by(RollingBacktestNode.id)
        )
        db_nodes = result.scalars().all()
    nid1, nid2 = db_nodes[0].id, db_nodes[1].id

    attempt = await create_execution_attempt(run.id, nid1, status="running")
    await persist_stage_event(
        attempt.id, nid1, stage="resolve_historical_inputs", status="completed"
    )

    # Tamper: change rolling_node_id to wrong node
    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                f"UPDATE rolling_backtest_stage_event "
                f"SET rolling_node_id = {nid2} WHERE attempt_id = {attempt.id}"
            )
        )
        await session.commit()

    async with AsyncSessionMaker() as session:
        with pytest.raises(RollingBacktestAuthorityBindingError):
            await validate_stage_continuity(session, attempt.id)


# ═══════════════════════════════════════════════════════════════════════════════
# Orchestration snapshot persistence
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_persist_orchestration_snapshot() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)
    node_id = await _first_node_id(run.id)
    attempt = await create_execution_attempt(run.id, node_id, status="running")

    await persist_stage_event(
        attempt.id, node_id, stage="resolve_historical_inputs", status="completed"
    )
    await persist_stage_event(attempt.id, node_id, stage="validate_visibility", status="completed")

    snapshot = await persist_orchestration_snapshot(
        attempt.id,
        node_id,
        status="completed",
        terminal_stage="validate_visibility",
    )
    assert snapshot.terminal_stage == "validate_visibility"
    assert snapshot.canonical_payload_hash is not None
    assert len(snapshot.canonical_payload_hash) == 64


@pytest.mark.asyncio
async def test_snapshot_terminal_stage_drift_blocked() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)
    node_id = await _first_node_id(run.id)
    attempt = await create_execution_attempt(run.id, node_id, status="running")

    await persist_stage_event(
        attempt.id, node_id, stage="resolve_historical_inputs", status="completed"
    )

    with pytest.raises(RollingBacktestStageIntegrityError):
        await persist_orchestration_snapshot(
            attempt.id,
            node_id,
            status="completed",
            terminal_stage="validate_authority_chain",
            # Mismatch: last event is resolve_historical_inputs
        )


@pytest.mark.asyncio
async def test_snapshot_duplicate_attempt_blocked() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)
    node_id = await _first_node_id(run.id)
    attempt = await create_execution_attempt(run.id, node_id, status="running")

    await persist_stage_event(
        attempt.id, node_id, stage="resolve_historical_inputs", status="completed"
    )
    await persist_orchestration_snapshot(
        attempt.id, node_id, status="completed", terminal_stage="resolve_historical_inputs"
    )

    with pytest.raises(RollingBacktestAttemptConflictError):
        await persist_orchestration_snapshot(
            attempt.id, node_id, status="completed", terminal_stage="resolve_historical_inputs"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Cross-table orchestration_snapshot consistency
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_snapshot_node_id_cross_check_pass() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)
    node_id = await _first_node_id(run.id)
    attempt = await create_execution_attempt(run.id, node_id, status="running")

    await persist_stage_event(
        attempt.id, node_id, stage="resolve_historical_inputs", status="completed"
    )
    await persist_orchestration_snapshot(
        attempt.id, node_id, status="completed", terminal_stage="resolve_historical_inputs"
    )

    async with AsyncSessionMaker() as session:
        await validate_orchestration_snapshot_consistency(session, attempt.id)


@pytest.mark.asyncio
async def test_snapshot_node_id_tamper_detected() -> None:
    _require_postgres()
    nodes = (_make_node(season_id=2025), _make_node(season_id=2026, as_of_local_date="2026-03-15"))
    config = _make_config(nodes=nodes)
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestNode)
            .where(RollingBacktestNode.rolling_run_id == run.id)
            .order_by(RollingBacktestNode.id)
        )
        db_nodes = result.scalars().all()
    nid1, nid2 = db_nodes[0].id, db_nodes[1].id

    attempt = await create_execution_attempt(run.id, nid1, status="running")
    await persist_stage_event(
        attempt.id, nid1, stage="resolve_historical_inputs", status="completed"
    )
    await persist_orchestration_snapshot(
        attempt.id, nid1, status="completed", terminal_stage="resolve_historical_inputs"
    )

    # Tamper: change snapshot rolling_node_id
    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                f"UPDATE rolling_backtest_orchestration_snapshot "
                f"SET rolling_node_id = {nid2} WHERE attempt_id = {attempt.id}"
            )
        )
        await session.commit()

    async with AsyncSessionMaker() as session:
        with pytest.raises(RollingBacktestAuthorityBindingError):
            await validate_orchestration_snapshot_consistency(session, attempt.id)


@pytest.mark.asyncio
async def test_finalize_attempt_and_snapshot_share_transaction() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)
    node_id = await _first_node_id(run.id)
    attempt = await create_execution_attempt(run.id, node_id, status="running")
    await persist_stage_event(
        attempt.id, node_id, stage="resolve_historical_inputs", status="completed"
    )
    await persist_orchestration_snapshot(
        attempt.id, node_id, status="completed", terminal_stage="resolve_historical_inputs"
    )

    with pytest.raises(RollingBacktestAttemptConflictError):
        await finalize_attempt_with_snapshot(
            attempt.id,
            node_id=node_id,
            status="blocked",
            current_stage="resolve_historical_inputs",
            snapshot_status="blocked",
            terminal_stage="resolve_historical_inputs",
            blocker_code="duplicate_snapshot",
        )

    async with AsyncSessionMaker() as session:
        refreshed = await session.get(RollingBacktestAttempt, attempt.id)
        assert refreshed is not None
        assert refreshed.status == "running"
        assert refreshed.current_stage == "initialized"
        assert refreshed.finished_at is None


@pytest.mark.asyncio
async def test_load_logical_run_with_integrity_detects_stage_gap() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)
    node_id = await _first_node_id(run.id)
    attempt = await create_execution_attempt(run.id, node_id, status="running")
    await persist_stage_event(
        attempt.id, node_id, stage="resolve_historical_inputs", status="completed"
    )
    await persist_stage_event(
        attempt.id, node_id, stage="validate_authority_chain", status="completed"
    )

    async with AsyncSessionMaker() as session:
        stored_run = await session.get(RollingBacktestRun, run.id)
        assert stored_run is not None
        with pytest.raises(RollingBacktestStageIntegrityError):
            await load_logical_run_with_integrity(session, stored_run)


@pytest.mark.asyncio
async def test_load_logical_run_with_integrity_detects_snapshot_stage_drift() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)
    node_id = await _first_node_id(run.id)
    attempt = await create_execution_attempt(run.id, node_id, status="running")
    await persist_stage_event(
        attempt.id, node_id, stage="resolve_historical_inputs", status="completed"
    )
    await persist_orchestration_snapshot(
        attempt.id, node_id, status="completed", terminal_stage="resolve_historical_inputs"
    )

    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                "UPDATE rolling_backtest_attempt "
                "SET current_stage = 'validate_visibility', status = 'completed', "
                "finished_at = now() "
                "WHERE id = :attempt_id"
            ),
            {"attempt_id": attempt.id},
        )
        await session.commit()

    async with AsyncSessionMaker() as session:
        stored_run = await session.get(RollingBacktestRun, run.id)
        assert stored_run is not None
        with pytest.raises(RollingBacktestCanonicalParityError):
            await load_logical_run_with_integrity(session, stored_run)


# ═══════════════════════════════════════════════════════════════════════════════
# Concurrency
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_concurrent_attempt_creation_same_node() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config)
    run = await create_or_load_logical_run(cmd)
    node_id = await _first_node_id(run.id)

    # Create first attempt to ensure node has a "completed" attempt that
    # the concurrent path would try to retry. Actually, we want to test
    # FOR UPDATE serialization. The repo code locks the node row.
    async def _create() -> RollingBacktestAttempt:
        return await create_execution_attempt(run.id, node_id, status="running")

    t1 = asyncio.create_task(_create())
    await asyncio.sleep(0.01)
    t2 = asyncio.create_task(_create())

    results = await asyncio.gather(t1, t2, return_exceptions=True)

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]

    # At least one succeeds (FOR UPDATE serializes, one gets locked out)
    assert len(successes) >= 1
    if failures:
        for f in failures:
            assert isinstance(f, RollingBacktestAttemptConflictError)
