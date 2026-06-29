"""Task 11 rolling backtest persistence integration tests.

Requires PostgreSQL with RUN_POSTGRES_INTEGRATION=1 and APP_ENV=test.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import AsyncSessionMaker
from backend.app.models.rolling_backtest import (
    RollingBacktestAttempt,
    RollingBacktestAvailabilityAudit,
    RollingBacktestDagSnapshot,
    RollingBacktestNode,
    RollingBacktestResolvedInput,
    RollingBacktestRun,
)
from backend.app.rolling_backtest import persistence as persistence_module
from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
    ExecutionMode,
    Task10ModelPolicy,
)
from backend.app.rolling_backtest.errors import (
    RollingBacktestAttemptConflictError,
    RollingBacktestAuthorityBindingError,
    RollingBacktestCanonicalParityError,
    RollingBacktestChildCountMismatchError,
    RollingBacktestDagIntegrityError,
    RollingBacktestIdentityConflictError,
    RollingBacktestIntegrityError,
    RollingBacktestPersistenceError,
)
from backend.app.rolling_backtest.persistence import (
    AvailabilityAuditPersistenceCommand,
    DagPersistenceCommand,
    ResolvedInputPersistenceCommand,
    RollingBacktestPersistenceCommand,
    RollingNodePersistenceCommand,
    create_execution_attempt,
    create_or_load_logical_run,
    finalize_attempt_status,
    finalize_attempt_with_snapshot,
    persist_stage_event,
)
from backend.app.rolling_backtest.schemas import (
    HistoricalAvailableModelIdentity,
    ResolvedUpstreamSemanticIdentity,
    RollingBacktestConfig,
    RollingNodeDefinition,
    Task8ForecastRunAvailabilitySnapshot,
    UpstreamSemanticIdentityPayload,
)
from backend.app.rolling_backtest.signatures import (
    run_signature_hash,
)

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


# ── Fixture helpers ──────────────────────────────────────────────────────────


def _make_historical_model_identity() -> HistoricalAvailableModelIdentity:
    return HistoricalAvailableModelIdentity(
        policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
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


# ═══════════════════════════════════════════════════════════════════════════════
# Happy path
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_logical_run_single_node() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)
    assert run.id is not None
    assert run.run_signature == run_signature_hash(config)
    assert run.expected_node_count == 1
    assert run.status == "pending"


@pytest.mark.asyncio
async def test_create_logical_run_multi_node() -> None:
    _require_postgres()
    nodes = (
        _make_node(season_id=2025),
        _make_node(season_id=2026),
    )
    config = _make_config(nodes=nodes)
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)
    assert run.expected_node_count == 2

    async with AsyncSessionMaker() as session:
        count = await session.scalar(
            select(func.count()).where(RollingBacktestNode.rolling_run_id == run.id)
        )
        assert count == 2


@pytest.mark.asyncio
async def test_create_with_resolved_inputs_and_audits_and_dag() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=True, with_audits=True, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        node_result = await session.execute(
            select(RollingBacktestNode).where(RollingBacktestNode.rolling_run_id == run.id)
        )
        node = node_result.scalar_one()

        input_count = await session.scalar(
            select(func.count()).where(RollingBacktestResolvedInput.rolling_node_id == node.id)
        )
        assert input_count == 2

        audit_count = await session.scalar(
            select(func.count()).where(RollingBacktestAvailabilityAudit.rolling_node_id == node.id)
        )
        assert audit_count == 1

        dag_result = await session.execute(
            select(RollingBacktestDagSnapshot).where(
                RollingBacktestDagSnapshot.rolling_node_id == node.id
            )
        )
        dag = dag_result.scalar_one()
        assert dag.expected_node_count == 3
        assert dag.expected_edge_count == 2


# ═══════════════════════════════════════════════════════════════════════════════
# Idempotency
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_same_config_twice_is_idempotent() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run1 = await create_or_load_logical_run(cmd)
    run2 = await create_or_load_logical_run(cmd)
    assert run1.id == run2.id
    assert run1.run_signature == run2.run_signature

    async with AsyncSessionMaker() as session:
        total_runs = await session.scalar(select(func.count()).select_from(RollingBacktestRun))
        assert total_runs == 1
        total_nodes = await session.scalar(select(func.count()).select_from(RollingBacktestNode))
        assert total_nodes == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Signature conflict (via SQL tamper)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_same_signature_tampered_canonical_payload_is_rejected() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    await create_or_load_logical_run(cmd)

    # Tamper canonical_payload
    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                "UPDATE rolling_backtest_run SET canonical_payload = '{\"tampered\": true}'::jsonb "
            ),
        )
        await session.commit()

    with pytest.raises(RollingBacktestCanonicalParityError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_same_signature_tampered_canonical_hash_is_rejected() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    await create_or_load_logical_run(cmd)

    # Tamper canonical_payload_hash
    async with AsyncSessionMaker() as session:
        await session.execute(
            text("UPDATE rolling_backtest_run SET canonical_payload_hash = :h"),
            {"h": "0" * 64},
        )
        await session.commit()

    with pytest.raises(RollingBacktestIdentityConflictError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_same_signature_tampered_config_hash_is_rejected() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    await create_or_load_logical_run(cmd)

    # Tamper config_hash
    async with AsyncSessionMaker() as session:
        await session.execute(
            text("UPDATE rolling_backtest_run SET config_hash = :h"),
            {"h": "0" * 64},
        )
        await session.commit()

    with pytest.raises(RollingBacktestIdentityConflictError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_same_signature_tampered_run_execution_mode_is_rejected() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        await session.execute(
            text("UPDATE rolling_backtest_run SET execution_mode = 'retrospective_replay'")
        )
        await session.commit()

    with pytest.raises(RollingBacktestCanonicalParityError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_same_signature_tampered_cutoff_timezone_is_rejected() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        await session.execute(text("UPDATE rolling_backtest_run SET cutoff_timezone = 'UTC'"))
        await session.commit()

    with pytest.raises(RollingBacktestCanonicalParityError):
        await create_or_load_logical_run(cmd)


# ═══════════════════════════════════════════════════════════════════════════════
# Atomic rollback
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_mid_transaction_child_failure_rolls_back_all_tables() -> None:
    _require_postgres()
    nodes = (_make_node(season_id=2025), _make_node(season_id=2026))
    config = _make_config(nodes=nodes)
    command = _make_persistence_command(config, with_inputs=True, with_audits=True, with_dag=True)
    failure_hook_entered = False

    async def inject_duplicate_resolved_input(
        phase: str,
        session: AsyncSession,
        node: RollingBacktestNode,
    ) -> None:
        nonlocal failure_hook_entered
        if phase != "after_first_node_children_flush":
            return
        failure_hook_entered = True

        run_count_in_tx = await session.scalar(select(func.count()).select_from(RollingBacktestRun))
        node_count_in_tx = await session.scalar(
            select(func.count()).select_from(RollingBacktestNode)
        )
        assert run_count_in_tx is not None and run_count_in_tx >= 1
        assert node_count_in_tx is not None and node_count_in_tx >= 1

        await session.execute(
            text(
                "INSERT INTO rolling_backtest_resolved_input ("
                "rolling_node_id, source_role, source_type, role_qualifier, "
                "semantic_input_signature, result_hash, canonical_payload_hash, "
                "schema_version, policy_version, persistent_reference_type, "
                "persistent_reference_value, canonical_payload, audit_hash"
                ") VALUES ("
                ":rolling_node_id, :source_role, :source_type, NULL, "
                ":semantic_input_signature, :result_hash, :canonical_payload_hash, "
                ":schema_version, :policy_version, NULL, NULL, "
                "CAST(:canonical_payload AS jsonb), :audit_hash"
                ")"
            ),
            {
                "rolling_node_id": node.id,
                "source_role": "task3_analytics",
                "source_type": "task3_analytics_build",
                "semantic_input_signature": "1" * 64,
                "result_hash": "2" * 64,
                "canonical_payload_hash": "3" * 64,
                "schema_version": "task11-upstream-v1",
                "policy_version": "p1",
                "canonical_payload": (
                    '{"source_role":"task3_analytics",'
                    '"source_type":"task3_analytics_build",'
                    '"role_qualifier":null,'
                    '"semantic":{'
                    '"schema_version":"task11-upstream-v1",'
                    '"semantic_payload_hash":"' + ("4" * 64) + '",'
                    '"input_signature":"' + ("1" * 64) + '",'
                    '"result_hash":"' + ("2" * 64) + '",'
                    '"canonical_payload_hash":"' + ("3" * 64) + '",'
                    '"business_version":"v1",'
                    '"policy_version":"p1"'
                    "}}"
                ),
                "audit_hash": "5" * 64,
            },
        )
        await session.flush()

    persistence_module._PERSISTENCE_WRITE_TEST_HOOK = inject_duplicate_resolved_input
    try:
        with pytest.raises(RollingBacktestPersistenceError) as exc:
            await create_or_load_logical_run(command)
    finally:
        persistence_module._PERSISTENCE_WRITE_TEST_HOOK = None

    assert failure_hook_entered is True
    assert exc.value.code == "ROLLING_BACKTEST_PERSISTENCE_ERROR"

    async with AsyncSessionMaker() as session:
        run_count = await session.scalar(select(func.count()).select_from(RollingBacktestRun))
        node_count = await session.scalar(select(func.count()).select_from(RollingBacktestNode))
        input_count = await session.scalar(
            select(func.count()).select_from(RollingBacktestResolvedInput)
        )
        audit_count = await session.scalar(
            select(func.count()).select_from(RollingBacktestAvailabilityAudit)
        )
        dag_count = await session.scalar(
            select(func.count()).select_from(RollingBacktestDagSnapshot)
        )
        attempt_count = await session.scalar(
            select(func.count()).select_from(RollingBacktestAttempt)
        )
        assert run_count == 0
        assert node_count == 0
        assert input_count == 0
        assert audit_count == 0
        assert dag_count == 0
        assert attempt_count == 0


# ═══════════════════════════════════════════════════════════════════════════════


async def _first_node_id(run_id: int) -> int:
    """Load the first node_id for a run (for tests)."""
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestNode).where(RollingBacktestNode.rolling_run_id == run_id).limit(1)
        )
        node = result.scalar_one_or_none()
        assert node is not None, f"no node found for run {run_id}"
        return node.id


async def _mark_attempt_failed(
    attempt_id: int,
    node_id: int,
    *,
    stage: str = "resolve_historical_inputs",
) -> None:
    await persist_stage_event(
        attempt_id,
        node_id,
        stage=stage,
        status="failed",
        structured_error_code="TEST_FAILURE",
    )
    await finalize_attempt_with_snapshot(
        attempt_id,
        node_id=node_id,
        status="failed",
        current_stage=stage,
        snapshot_status="failed",
        terminal_stage=stage,
        structured_error_code="TEST_FAILURE",
        canonical_payload={"test": "failed-attempt"},
    )


async def _mark_attempt_running(
    attempt_id: int,
    node_id: int,
    *,
    stage: str = "resolve_historical_inputs",
) -> None:
    await persist_stage_event(
        attempt_id,
        node_id,
        stage=stage,
        status="running",
    )
    await finalize_attempt_status(
        attempt_id,
        status="running",
        current_stage=stage,
    )


# Attempt lifecycle
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_attempt_auto_increment_and_chain() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    a1 = await create_execution_attempt(run.id, await _first_node_id(run.id), status="running")
    assert a1.attempt_number == 1
    assert a1.prior_attempt_id is None

    await finalize_attempt_status(
        a1.id,
        status="failed",
        current_stage="config_validation",
        structured_error_code="TEST_FAILURE",
    )

    a2 = await create_execution_attempt(
        run.id,
        await _first_node_id(run.id),
        status="running",
        prior_attempt_id=a1.id,
    )
    assert a2.attempt_number == 2
    assert a2.prior_attempt_id == a1.id

    await finalize_attempt_status(
        a2.id,
        status="blocked",
        current_stage="waiting_for_retry",
        structured_error_code="TEST_BLOCKED",
    )

    a3 = await create_execution_attempt(run.id, await _first_node_id(run.id), status="running")
    assert a3.attempt_number == 3
    assert a3.prior_attempt_id == a2.id


@pytest.mark.asyncio
async def test_cannot_modify_completed_attempt() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)
    a1 = await create_execution_attempt(run.id, await _first_node_id(run.id), status="running")
    await finalize_attempt_status(a1.id, status="completed", current_stage="done")

    with pytest.raises(RollingBacktestAttemptConflictError):
        await finalize_attempt_status(a1.id, status="failed", current_stage="retry")


@pytest.mark.asyncio
async def test_prior_attempt_must_belong_to_same_run() -> None:
    _require_postgres()
    config1 = _make_config()
    cmd1 = _make_persistence_command(config1, with_inputs=False, with_dag=True)
    run1 = await create_or_load_logical_run(cmd1)

    config2 = _make_config(nodes=(_make_node(season_id=2025),))
    cmd2 = _make_persistence_command(config2, with_inputs=False, with_dag=True)
    run2 = await create_or_load_logical_run(cmd2)

    a1 = await create_execution_attempt(run1.id, await _first_node_id(run1.id), status="failed")
    await finalize_attempt_status(a1.id, status="failed", current_stage="init")

    # Attempt to link prior from run2 to run1's attempt
    with pytest.raises(RollingBacktestAttemptConflictError):
        await create_execution_attempt(
            run2.id,
            await _first_node_id(run2.id),
            status="running",
            prior_attempt_id=a1.id,
        )


@pytest.mark.asyncio
async def test_retry_after_running_attempt_is_rejected() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)
    _ = await create_execution_attempt(run.id, await _first_node_id(run.id), status="running")

    with pytest.raises(RollingBacktestAttemptConflictError) as exc:
        await create_execution_attempt(run.id, await _first_node_id(run.id), status="running")

    assert exc.value.code == "ROLLING_BACKTEST_ATTEMPT_CONFLICT"


@pytest.mark.asyncio
async def test_retry_after_completed_attempt_is_rejected() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)
    attempt = await create_execution_attempt(run.id, await _first_node_id(run.id), status="running")
    await finalize_attempt_status(attempt.id, status="completed", current_stage="done")

    with pytest.raises(RollingBacktestAttemptConflictError) as exc:
        await create_execution_attempt(run.id, await _first_node_id(run.id), status="running")

    assert exc.value.code == "ROLLING_BACKTEST_ATTEMPT_CONFLICT"


# ═══════════════════════════════════════════════════════════════════════════════
# Tamper detection matrix
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tamper_delete_node_triggers_child_count_error() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    # Delete a node
    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                "DELETE FROM rolling_backtest_dag_snapshot WHERE rolling_node_id IN ("
                "  SELECT id FROM rolling_backtest_node WHERE rolling_run_id = :rid"
                ")"
            ),
            {"rid": run.id},
        )
        await session.execute(
            text("DELETE FROM rolling_backtest_node WHERE rolling_run_id = :rid"),
            {"rid": run.id},
        )
        await session.commit()

    with pytest.raises(RollingBacktestChildCountMismatchError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_tamper_insert_extra_node_triggers_child_count_error() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    # Insert an extra node
    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                "INSERT INTO rolling_backtest_node "
                "(rolling_run_id, season_id, node_key, node_signature, "
                "as_of_local_date, forecast_cutoff_at, forecast_start_local_date, "
                "forecast_end_local_date, execution_mode, upstream_selection_mode, "
                "scope, forecast_horizon_policy_version, task10_model_policy, "
                "cutoff_policy_version, timezone, canonical_payload, canonical_payload_hash, "
                "expected_resolved_input_count, expected_availability_audit_count) "
                "VALUES (:rid, 9999, 'extra', :sig, '2025-01-01', "
                "'2025-01-01T00:00:00Z', '2025-01-02', '2025-01-31', "
                "'historical_observed', 'historical_resolution', "
                "'{}'::jsonb, 'task11-horizon-v1', '{}'::jsonb, "
                "'task11-cutoff-v1', 'Asia/Shanghai', '{}'::jsonb, :hash, 0, 0)"
            ),
            {"rid": run.id, "sig": "a" * 64, "hash": "0" * 64},
        )
        await session.commit()

    with pytest.raises(RollingBacktestChildCountMismatchError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_tamper_node_canonical_payload_triggers_parity_error() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                "UPDATE rolling_backtest_node "
                "SET canonical_payload = '{\"tampered\": true}'::jsonb "
                "WHERE rolling_run_id = :rid"
            ),
            {"rid": run.id},
        )
        await session.commit()

    with pytest.raises(RollingBacktestCanonicalParityError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_tamper_node_canonical_hash_triggers_parity_error() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                "UPDATE rolling_backtest_node "
                "SET canonical_payload_hash = :h "
                "WHERE rolling_run_id = :rid"
            ),
            {"h": "0" * 64, "rid": run.id},
        )
        await session.commit()

    with pytest.raises(RollingBacktestCanonicalParityError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_tamper_node_normalized_date_triggers_parity_error() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                "UPDATE rolling_backtest_node "
                "SET forecast_end_local_date = DATE '2026-04-01' "
                "WHERE rolling_run_id = :rid"
            ),
            {"rid": run.id},
        )
        await session.commit()

    with pytest.raises(RollingBacktestCanonicalParityError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_tamper_node_timezone_triggers_parity_error() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        await session.execute(
            text("UPDATE rolling_backtest_node SET timezone = 'UTC' WHERE rolling_run_id = :rid"),
            {"rid": run.id},
        )
        await session.commit()

    with pytest.raises(RollingBacktestCanonicalParityError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_tamper_delete_resolved_input_triggers_child_count_error() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=True, with_audits=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        node_result = await session.execute(
            select(RollingBacktestNode).where(RollingBacktestNode.rolling_run_id == run.id)
        )
        node = node_result.scalar_one()
        await session.execute(
            text("DELETE FROM rolling_backtest_resolved_input WHERE rolling_node_id = :nid"),
            {"nid": node.id},
        )
        await session.commit()

    with pytest.raises(RollingBacktestChildCountMismatchError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_tamper_resolved_input_semantic_hash_triggers_parity_error() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=True, with_audits=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                "UPDATE rolling_backtest_resolved_input "
                "SET audit_hash = :h "
                "WHERE rolling_node_id IN ("
                "  SELECT id FROM rolling_backtest_node WHERE rolling_run_id = :rid"
                ")"
            ),
            {"h": "0" * 64, "rid": run.id},
        )
        await session.commit()

    with pytest.raises(RollingBacktestCanonicalParityError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_tamper_persistent_db_id_in_semantic_payload_is_detected() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=True, with_audits=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    # Inject database_id into canonical_payload
    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                "UPDATE rolling_backtest_resolved_input "
                "SET canonical_payload = "
                "canonical_payload || '{\"persistent_reference\": 123}'::jsonb "
                "WHERE rolling_node_id IN ("
                "  SELECT id FROM rolling_backtest_node WHERE rolling_run_id = :rid"
                ")"
            ),
            {"rid": run.id},
        )
        await session.commit()

    with pytest.raises(RollingBacktestIntegrityError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_tamper_availability_audit_payload_triggers_parity_error() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_audits=True, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                "UPDATE rolling_backtest_availability_audit "
                "SET canonical_payload = '{\"tampered\": true}'::jsonb "
                "WHERE rolling_node_id IN ("
                "  SELECT id FROM rolling_backtest_node WHERE rolling_run_id = :rid"
                ")"
            ),
            {"rid": run.id},
        )
        await session.commit()

    with pytest.raises(RollingBacktestCanonicalParityError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_tamper_availability_audit_hash_triggers_parity_error() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_audits=True, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                "UPDATE rolling_backtest_availability_audit "
                "SET audit_hash = :h "
                "WHERE rolling_node_id IN ("
                "  SELECT id FROM rolling_backtest_node WHERE rolling_run_id = :rid"
                ")"
            ),
            {"h": "0" * 64, "rid": run.id},
        )
        await session.commit()

    with pytest.raises(RollingBacktestCanonicalParityError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_tamper_availability_audit_source_role_triggers_binding_error() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_audits=True, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                "UPDATE rolling_backtest_availability_audit "
                "SET source_role = 'wrong_role' "
                "WHERE rolling_node_id IN ("
                "  SELECT id FROM rolling_backtest_node WHERE rolling_run_id = :rid"
                ")"
            ),
            {"rid": run.id},
        )
        await session.commit()

    with pytest.raises(RollingBacktestAuthorityBindingError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_tamper_availability_audit_source_type_triggers_binding_error() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_audits=True, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                "UPDATE rolling_backtest_availability_audit "
                "SET source_type = 'task3_analytics_build' "
                "WHERE rolling_node_id IN ("
                "  SELECT id FROM rolling_backtest_node WHERE rolling_run_id = :rid"
                ")"
            ),
            {"rid": run.id},
        )
        await session.commit()

    with pytest.raises(RollingBacktestAuthorityBindingError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_deleted_dag_fails_closed() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_audits=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                "DELETE FROM rolling_backtest_dag_snapshot WHERE rolling_node_id IN ("
                "  SELECT id FROM rolling_backtest_node WHERE rolling_run_id = :rid"
                ")"
            ),
            {"rid": run.id},
        )
        await session.commit()

    with pytest.raises(RollingBacktestDagIntegrityError) as exc:
        await create_or_load_logical_run(cmd)

    assert exc.value.code == "ROLLING_BACKTEST_DAG_INTEGRITY_ERROR"


@pytest.mark.asyncio
async def test_tamper_dag_payload_triggers_parity_error() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_audits=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        node_signature = await session.scalar(
            select(RollingBacktestNode.node_signature).where(
                RollingBacktestNode.rolling_run_id == run.id
            )
        )
        assert node_signature is not None
        await session.execute(
            text(
                "UPDATE rolling_backtest_dag_snapshot "
                "SET canonical_payload = "
                "jsonb_build_object("
                "'owner_node_signature', CAST(:node_signature AS text), "
                "'dag_schema_version', 'task11-dag-v1', "
                "'dag_policy_version', 'task11-dag-policy-v1', "
                "'nodes', jsonb_build_array('a', 'b', 'd'), "
                "'edges', jsonb_build_array("
                "  jsonb_build_array('a', 'b'), "
                "  jsonb_build_array('b', 'd')"
                ")"
                ") "
                "WHERE rolling_node_id IN ("
                "  SELECT id FROM rolling_backtest_node WHERE rolling_run_id = :rid"
                ")"
            ),
            {"rid": run.id, "node_signature": node_signature},
        )
        await session.commit()

    with pytest.raises(RollingBacktestCanonicalParityError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_dag_owner_mismatch_fails_closed() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_audits=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        bad_owner = "b" * 64
        await session.execute(
            text(
                "UPDATE rolling_backtest_dag_snapshot "
                "SET canonical_payload = "
                "jsonb_set("
                "canonical_payload, "
                "'{owner_node_signature}', "
                "to_jsonb(CAST(:bad_owner AS text))"
                ") "
                "WHERE rolling_node_id IN ("
                "  SELECT id FROM rolling_backtest_node WHERE rolling_run_id = :rid"
                ")"
            ),
            {"rid": run.id, "bad_owner": bad_owner},
        )
        await session.commit()

    with pytest.raises(RollingBacktestDagIntegrityError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_dag_missing_endpoint_fails_closed() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_audits=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        node_signature = await session.scalar(
            select(RollingBacktestNode.node_signature).where(
                RollingBacktestNode.rolling_run_id == run.id
            )
        )
        assert node_signature is not None
        await session.execute(
            text(
                "UPDATE rolling_backtest_dag_snapshot "
                "SET canonical_payload = "
                "jsonb_build_object("
                "'owner_node_signature', CAST(:node_signature AS text), "
                "'dag_schema_version', 'task11-dag-v1', "
                "'dag_policy_version', 'task11-dag-policy-v1', "
                "'nodes', jsonb_build_array('a'), "
                "'edges', jsonb_build_array(jsonb_build_array('a', 'missing'))"
                ") "
                "WHERE rolling_node_id IN ("
                "  SELECT id FROM rolling_backtest_node WHERE rolling_run_id = :rid"
                ")"
            ),
            {"rid": run.id, "node_signature": node_signature},
        )
        await session.commit()

    with pytest.raises(RollingBacktestDagIntegrityError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_tamper_dag_expected_count_triggers_mismatch() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_audits=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                "UPDATE rolling_backtest_dag_snapshot "
                "SET expected_node_count = 999 "
                "WHERE rolling_node_id IN ("
                "  SELECT id FROM rolling_backtest_node WHERE rolling_run_id = :rid"
                ")"
            ),
            {"rid": run.id},
        )
        await session.commit()

    with pytest.raises(RollingBacktestChildCountMismatchError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_tamper_attempt_skip_number_is_detected() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    node_id = await _first_node_id(run.id)
    a1 = await create_execution_attempt(run.id, node_id, status="failed")
    await _mark_attempt_failed(a1.id, node_id)
    a2 = await create_execution_attempt(
        run.id, node_id, status="failed", prior_attempt_id=a1.id
    )
    await _mark_attempt_failed(a2.id, node_id)

    # Tamper: change attempt 2's number to 3
    async with AsyncSessionMaker() as session:
        await session.execute(
            text("UPDATE rolling_backtest_attempt SET attempt_number = 3 WHERE id = :aid"),
            {"aid": a2.id},
        )
        await session.commit()

    with pytest.raises(RollingBacktestAttemptConflictError):
        await create_or_load_logical_run(cmd)


@pytest.mark.asyncio
async def test_tamper_attempt_prior_points_to_other_run_is_detected() -> None:
    _require_postgres()
    config1 = _make_config()
    cmd1 = _make_persistence_command(config1, with_inputs=False, with_dag=True)
    run1 = await create_or_load_logical_run(cmd1)

    config2 = _make_config(nodes=(_make_node(season_id=2025),))
    cmd2 = _make_persistence_command(config2, with_inputs=False, with_dag=True)
    run2 = await create_or_load_logical_run(cmd2)

    node1 = await _first_node_id(run1.id)
    node2 = await _first_node_id(run2.id)
    a1 = await create_execution_attempt(run1.id, node1, status="failed")
    a2 = await create_execution_attempt(run2.id, node2, status="failed")
    await _mark_attempt_failed(a1.id, node1)
    await _mark_attempt_failed(a2.id, node2)

    # Tamper: make a1's prior point to a2 (different run)
    async with AsyncSessionMaker() as session:
        await session.execute(
            text("UPDATE rolling_backtest_attempt SET prior_attempt_id = :pid WHERE id = :aid"),
            {"pid": a2.id, "aid": a1.id},
        )
        await session.commit()

    with pytest.raises(RollingBacktestAttemptConflictError):
        await create_or_load_logical_run(cmd1)


@pytest.mark.asyncio
async def test_tamper_attempt_two_prior_null_is_detected() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    node_id = await _first_node_id(run.id)
    first = await create_execution_attempt(run.id, node_id, status="failed")
    await _mark_attempt_failed(first.id, node_id)
    second = await create_execution_attempt(run.id, node_id, status="running")
    await _mark_attempt_running(second.id, node_id)
    assert second.prior_attempt_id == first.id

    async with AsyncSessionMaker() as session:
        await session.execute(
            text("UPDATE rolling_backtest_attempt SET prior_attempt_id = NULL WHERE id = :aid"),
            {"aid": second.id},
        )
        await session.commit()

    with pytest.raises(RollingBacktestAttemptConflictError):
        await create_or_load_logical_run(cmd)


# ═══════════════════════════════════════════════════════════════════════════════
# Concurrency
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_concurrent_same_run_signature_only_creates_one() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)

    entered = 0
    released = asyncio.Event()
    both_waiting = asyncio.Event()

    async def barrier(phase: str) -> None:
        nonlocal entered
        if phase != "after_lookup":
            return
        entered += 1
        if entered == 2:
            both_waiting.set()
        await both_waiting.wait()
        await released.wait()

    persistence_module._CREATE_OR_LOAD_SYNC_HOOK = barrier
    try:
        left_task = asyncio.create_task(create_or_load_logical_run(cmd))
        right_task = asyncio.create_task(create_or_load_logical_run(cmd))
        await asyncio.wait_for(both_waiting.wait(), timeout=5)
        released.set()
        run1, run2 = await asyncio.gather(left_task, right_task)
    finally:
        persistence_module._CREATE_OR_LOAD_SYNC_HOOK = None

    assert run1.id == run2.id

    async with AsyncSessionMaker() as session:
        run_count = await session.scalar(select(func.count()).select_from(RollingBacktestRun))
        node_count = await session.scalar(select(func.count()).select_from(RollingBacktestNode))
        input_count = await session.scalar(
            select(func.count()).select_from(RollingBacktestResolvedInput)
        )
        audit_count = await session.scalar(
            select(func.count()).select_from(RollingBacktestAvailabilityAudit)
        )
        dag_count = await session.scalar(
            select(func.count()).select_from(RollingBacktestDagSnapshot)
        )
        assert run_count == 1
        assert node_count == 1
        assert input_count == 0
        assert audit_count == 0
        assert dag_count == 1


@pytest.mark.asyncio
async def test_concurrent_attempt_allocation_serializes_numbering() -> None:
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)
    first = await create_execution_attempt(run.id, await _first_node_id(run.id), status="failed")

    entered = 0
    release = asyncio.Event()
    first_has_lock = asyncio.Event()

    async def lock_hook(phase: str) -> None:
        nonlocal entered
        if phase != "after_node_lock":
            return
        entered += 1
        if entered == 1:
            first_has_lock.set()
            await release.wait()

    persistence_module._ATTEMPT_ALLOCATION_SYNC_HOOK = lock_hook
    try:
        left = asyncio.create_task(
            create_execution_attempt(run.id, await _first_node_id(run.id), status="running")
        )
        await asyncio.wait_for(first_has_lock.wait(), timeout=5)
        right = asyncio.create_task(
            create_execution_attempt(run.id, await _first_node_id(run.id), status="running")
        )
        release.set()
        second, third = await asyncio.gather(left, right, return_exceptions=True)
    finally:
        persistence_module._ATTEMPT_ALLOCATION_SYNC_HOOK = None

    assert first.attempt_number == 1
    success_results = [item for item in (second, third) if isinstance(item, RollingBacktestAttempt)]
    conflict_results = [
        item for item in (second, third) if isinstance(item, RollingBacktestAttemptConflictError)
    ]
    assert len(success_results) == 1
    assert len(conflict_results) == 1
    assert success_results[0].attempt_number == 2
    assert success_results[0].prior_attempt_id == first.id
    assert conflict_results[0].code == "ROLLING_BACKTEST_ATTEMPT_CONFLICT"
