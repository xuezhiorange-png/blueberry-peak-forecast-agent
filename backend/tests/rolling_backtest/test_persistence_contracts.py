from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest

from backend.app.rolling_backtest import persistence as persistence_module
from backend.app.rolling_backtest.enums import AvailabilitySourceType, ExecutionMode
from backend.app.rolling_backtest.errors import (
    RollingBacktestAuthorityBindingError,
    RollingBacktestCommandMismatchError,
)
from backend.app.rolling_backtest.persistence import (
    AvailabilityAuditPersistenceCommand,
    DagPersistenceCommand,
    ResolvedInputPersistenceCommand,
    RollingBacktestPersistenceCommand,
    RollingNodePersistenceCommand,
    validate_persistence_command,
)
from backend.app.rolling_backtest.schemas import (
    ResolvedUpstreamSemanticIdentity,
    RollingBacktestConfig,
    RollingNodeDefinition,
    Task8ForecastRunAvailabilitySnapshot,
    UpstreamSemanticIdentityPayload,
)


def _make_node(
    *,
    season_id: int = 2026,
    node_key: str = "march_15",
) -> RollingNodeDefinition:
    return RollingNodeDefinition.model_validate(
        {
            "season_id": season_id,
            "node_key": node_key,
            "as_of_local_date": f"{season_id}-03-15",
            "forecast_cutoff_at": f"{season_id}-03-15T04:00:00Z",
            "forecast_start_local_date": f"{season_id}-03-16",
            "forecast_end_local_date": f"{season_id}-03-31",
            "scope": {
                "destination_factory_ids": {"mode": "include_ids", "ids": [101, 202]},
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
    if nodes is None:
        nodes = (_make_node(),)
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


def _make_semantic_identity(
    *,
    source_type: AvailabilitySourceType = AvailabilitySourceType.TASK8_FORECAST_RUN,
    source_role: str = "task8_forecast_run",
) -> ResolvedUpstreamSemanticIdentity:
    return ResolvedUpstreamSemanticIdentity(
        source_type=source_type,
        source_role=source_role,
        semantic=UpstreamSemanticIdentityPayload(
            schema_version="task11-upstream-v1",
            display_label="test",
            semantic_payload_hash="e" * 64,
            input_signature="f" * 64,
            result_hash="a" * 64,
            canonical_payload_hash="b" * 64,
            business_version="v1",
            policy_version="p1",
        ),
    )


def _make_snapshot() -> Task8ForecastRunAvailabilitySnapshot:
    return Task8ForecastRunAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
        status="completed",
        authoritative_timestamp=datetime(2025, 3, 14, 4, 0, tzinfo=UTC),
    )


def _make_dag() -> DagPersistenceCommand:
    return DagPersistenceCommand(
        dag_schema_version="task11-dag-v1",
        dag_policy_version="task11-dag-policy-v1",
        dag_dict={"nodes": ["extract", "forecast"], "edges": [["extract", "forecast"]]},
        expected_node_count=2,
        expected_edge_count=1,
    )


def _make_node_command(
    node: RollingNodeDefinition,
    *,
    identity: ResolvedUpstreamSemanticIdentity | None = None,
    audit_role: str = "task8_forecast_run",
) -> RollingNodePersistenceCommand:
    if identity is None:
        identity = _make_semantic_identity(source_role=audit_role)
    node = node.model_copy(update={"resolved_upstream_semantic_identities": (identity,)})
    return RollingNodePersistenceCommand(
        node=node,
        resolved_inputs=(ResolvedInputPersistenceCommand(identity=identity),),
        availability_audits=(
            AvailabilityAuditPersistenceCommand(
                source_role=audit_role,
                snapshot=_make_snapshot(),
                forecast_cutoff_at=node.forecast_cutoff_at,
                resolved_identity=identity,
            ),
        ),
        dag=_make_dag(),
    )


def test_validate_persistence_command_rejects_missing_node() -> None:
    nodes = (_make_node(season_id=2025), _make_node(season_id=2026))
    config = _make_config(nodes=nodes)
    command = RollingBacktestPersistenceCommand(
        config=config,
        nodes=(_make_node_command(nodes[0]),),
    )

    with pytest.raises(RollingBacktestCommandMismatchError) as exc:
        validate_persistence_command(command)

    assert exc.value.code == "ROLLING_BACKTEST_COMMAND_MISMATCH"


def test_persistence_write_test_hook_defaults_to_none() -> None:
    assert persistence_module._PERSISTENCE_WRITE_TEST_HOOK is None


def test_persistence_write_test_hook_not_exposed_in_public_api() -> None:
    parameters = inspect.signature(persistence_module.create_or_load_logical_run).parameters
    assert "_PERSISTENCE_WRITE_TEST_HOOK" not in parameters
    assert "failure_injection" not in parameters


def test_persistence_write_test_hook_not_in_semantic_payload() -> None:
    node = _make_node()
    config = _make_config(nodes=(node,))
    payload = persistence_module._json_value(  # noqa: SLF001
        persistence_module.rolling_backtest_config_payload(config)
    )
    assert "_PERSISTENCE_WRITE_TEST_HOOK" not in str(payload)
    assert "failure_injection" not in str(payload)


def test_validate_persistence_command_rejects_reordered_nodes() -> None:
    nodes = (_make_node(season_id=2025), _make_node(season_id=2026))
    config = _make_config(nodes=nodes)
    command = RollingBacktestPersistenceCommand(
        config=config,
        nodes=(
            _make_node_command(nodes[1]),
            _make_node_command(nodes[0]),
        ),
    )

    with pytest.raises(RollingBacktestCommandMismatchError) as exc:
        validate_persistence_command(command)

    assert exc.value.code == "ROLLING_BACKTEST_COMMAND_MISMATCH"


def test_validate_persistence_command_rejects_audit_role_mismatch() -> None:
    node = _make_node()
    identity = _make_semantic_identity(source_role="task8_forecast_run")
    node = node.model_copy(update={"resolved_upstream_semantic_identities": (identity,)})
    config = _make_config(nodes=(node,))
    command = RollingBacktestPersistenceCommand(
        config=config,
        nodes=(
            RollingNodePersistenceCommand(
                node=node,
                resolved_inputs=(ResolvedInputPersistenceCommand(identity=identity),),
                availability_audits=(
                    AvailabilityAuditPersistenceCommand(
                        source_role="task8_model_artifact",
                        snapshot=_make_snapshot(),
                        forecast_cutoff_at=node.forecast_cutoff_at,
                        resolved_identity=identity,
                    ),
                ),
                dag=_make_dag(),
            ),
        ),
    )

    with pytest.raises(RollingBacktestAuthorityBindingError) as exc:
        validate_persistence_command(command)

    assert exc.value.code == "ROLLING_BACKTEST_AUTHORITY_BINDING_ERROR"


def test_validate_persistence_command_rejects_audit_source_type_mismatch() -> None:
    node = _make_node()
    identity = _make_semantic_identity(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        source_role="task8_forecast_run",
    )
    node = node.model_copy(update={"resolved_upstream_semantic_identities": (identity,)})
    config = _make_config(nodes=(node,))
    command = RollingBacktestPersistenceCommand(
        config=config,
        nodes=(
            RollingNodePersistenceCommand(
                node=node,
                resolved_inputs=(ResolvedInputPersistenceCommand(identity=identity),),
                availability_audits=(
                    AvailabilityAuditPersistenceCommand(
                        source_role="task8_forecast_run",
                        snapshot=_make_snapshot(),
                        forecast_cutoff_at=node.forecast_cutoff_at,
                        resolved_identity=identity,
                    ),
                ),
                dag=_make_dag(),
            ),
        ),
    )

    with pytest.raises(RollingBacktestAuthorityBindingError) as exc:
        validate_persistence_command(command)

    assert exc.value.code == "ROLLING_BACKTEST_AUTHORITY_BINDING_ERROR"


def test_validate_persistence_command_rejects_missing_resolved_identity() -> None:
    node = _make_node()
    identity = _make_semantic_identity()
    node = node.model_copy(update={"resolved_upstream_semantic_identities": (identity,)})
    config = _make_config(nodes=(node,))
    command = RollingBacktestPersistenceCommand(
        config=config,
        nodes=(
            RollingNodePersistenceCommand(
                node=node,
                resolved_inputs=(ResolvedInputPersistenceCommand(identity=identity),),
                availability_audits=(
                    AvailabilityAuditPersistenceCommand(
                        source_role="task8_forecast_run",
                        snapshot=_make_snapshot(),
                        forecast_cutoff_at=node.forecast_cutoff_at,
                        resolved_identity=None,  # type: ignore[arg-type]
                    ),
                ),
                dag=_make_dag(),
            ),
        ),
    )

    with pytest.raises(RollingBacktestAuthorityBindingError) as exc:
        validate_persistence_command(command)

    assert exc.value.code == "ROLLING_BACKTEST_AUTHORITY_BINDING_ERROR"


def test_validate_persistence_command_requires_dag_per_node() -> None:
    node = _make_node()
    identity = _make_semantic_identity()
    node = node.model_copy(update={"resolved_upstream_semantic_identities": (identity,)})
    config = _make_config(nodes=(node,))
    command = RollingBacktestPersistenceCommand(
        config=config,
        nodes=(
            RollingNodePersistenceCommand(
                node=node,
                resolved_inputs=(ResolvedInputPersistenceCommand(identity=identity),),
                availability_audits=(
                    AvailabilityAuditPersistenceCommand(
                        source_role="task8_forecast_run",
                        snapshot=_make_snapshot(),
                        forecast_cutoff_at=node.forecast_cutoff_at,
                        resolved_identity=identity,
                    ),
                ),
                dag=None,  # type: ignore[arg-type]
            ),
        ),
    )

    with pytest.raises(RollingBacktestCommandMismatchError) as exc:
        validate_persistence_command(command)

    assert exc.value.code == "ROLLING_BACKTEST_COMMAND_MISMATCH"
