from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from backend.app.rolling_backtest.canonical import canonical_json_dumps
from backend.app.rolling_backtest.config import rolling_backtest_config_payload
from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
    ExecutionMode,
    Task10ModelPolicy,
    UpstreamSelectionMode,
)
from backend.app.rolling_backtest.errors import RollingBacktestCommandMismatchError
from backend.app.rolling_backtest.persistence import (
    AvailabilityAuditPersistenceCommand,
    DagPersistenceCommand,
    ResolvedInputPersistenceCommand,
    RollingBacktestPersistenceCommand,
    RollingNodePersistenceCommand,
    _config_from_canonical_payload,
    _resolved_input_canonical_payload,
    validate_persistence_command,
)
from backend.app.rolling_backtest.schemas import (
    PersistentUpstreamReference,
    ResolvedUpstreamSemanticIdentity,
    RollingBacktestConfig,
    RollingNodeDefinition,
    Task8ForecastRunAvailabilitySnapshot,
    UpstreamSemanticIdentityPayload,
)
from backend.app.rolling_backtest.signatures import node_signature_payload


def _make_identity(
    *,
    source_role: str,
    ref: PersistentUpstreamReference | None,
) -> ResolvedUpstreamSemanticIdentity:
    return ResolvedUpstreamSemanticIdentity(
        source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
        source_role=source_role,
        semantic=UpstreamSemanticIdentityPayload(
            schema_version="task11-upstream-v1",
            display_label=source_role,
            semantic_payload_hash="e" * 64,
            input_signature="f" * 64,
            result_hash="a" * 64,
            canonical_payload_hash="b" * 64,
            business_version="v1",
            policy_version="p1",
        ),
        persistent_reference=ref,
    )


def _make_node(
    *,
    identities: tuple[ResolvedUpstreamSemanticIdentity, ...],
) -> RollingNodeDefinition:
    return RollingNodeDefinition.model_validate(
        {
            "season_id": 2026,
            "node_key": "march_15",
            "as_of_local_date": "2026-03-15",
            "forecast_cutoff_at": "2026-03-15T04:00:00Z",
            "forecast_start_local_date": "2026-03-16",
            "forecast_end_local_date": "2026-03-31",
            "scope": {
                "destination_factory_ids": {"mode": "include_ids", "ids": [101]},
                "farm_ids": {"mode": "all", "ids": []},
                "subfarm_ids": {"mode": "all", "ids": []},
                "variety_ids": {"mode": "all", "ids": []},
            },
            "upstream_selection_mode": UpstreamSelectionMode.PINNED.value,
            "forecast_horizon_policy_version": "task11-horizon-v1",
            "timezone": "Asia/Shanghai",
            "task10_model_policy": {
                "policy": Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL.value,
                "training_run_semantic_identity": "1" * 64,
                "artifact_semantic_identities": ["2" * 64],
                "authority_visibility_identity": "3" * 64,
            },
            "resolved_upstream_semantic_identities": [
                identity.model_dump(mode="python") for identity in identities
            ],
        }
    )


def _make_config(*, nodes: tuple[RollingNodeDefinition, ...]) -> RollingBacktestConfig:
    return RollingBacktestConfig.model_validate(
        {
            "rolling_schema_version": "task11-rolling-v1",
            "canonical_serialization_version": "task11-canonical-v1",
            "availability_registry_version": "task11-availability-v1",
            "node_calendar_version": "task11-calendar-v1",
            "forecast_horizon_policy_version": "task11-horizon-v1",
            "upstream_selection_policy_version": "task11-selection-v1",
            "metric_policy_version": "task11-metrics-v1",
            "execution_mode": ExecutionMode.HISTORICAL_OBSERVED.value,
            "calendar_phase_policy_version": "task11-calendar-phase-v1",
            "cutoff_policy_version": "task11-cutoff-v1",
            "cutoff_timezone": "Asia/Shanghai",
            "cutoff_local_time": "12:00:00",
            "nodes": [node.model_dump(mode="python") for node in nodes],
        }
    )


def _make_dag() -> DagPersistenceCommand:
    return DagPersistenceCommand(
        dag_schema_version="task11-dag-v1",
        dag_policy_version="task11-dag-policy-v1",
        dag_dict={"nodes": ["a"], "edges": []},
        expected_node_count=1,
        expected_edge_count=0,
    )


def _make_command(
    *,
    identity: ResolvedUpstreamSemanticIdentity,
    command_ref: PersistentUpstreamReference | None,
) -> RollingBacktestPersistenceCommand:
    node = _make_node(identities=(identity,))
    config = _make_config(nodes=(node,))
    validated_node = config.nodes[0]
    validated_identity = validated_node.resolved_upstream_semantic_identities[0]
    audit = AvailabilityAuditPersistenceCommand(
        source_role=validated_identity.source_role,
        snapshot=Task8ForecastRunAvailabilitySnapshot(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            status="completed",
            authoritative_timestamp=datetime(2026, 3, 14, tzinfo=UTC),
        ),
        forecast_cutoff_at=validated_node.forecast_cutoff_at,
        resolved_identity=validated_identity,
    )
    node_cmd = RollingNodePersistenceCommand(
        node=validated_node,
        resolved_inputs=(
            ResolvedInputPersistenceCommand(
                identity=validated_identity,
                persistent_reference=command_ref,
            ),
        ),
        availability_audits=(audit,),
        dag=_make_dag(),
    )
    return RollingBacktestPersistenceCommand(config=config, nodes=(node_cmd,))


@pytest.mark.parametrize(
    ("identity_ref", "command_ref"),
    [
        (
            PersistentUpstreamReference(reference_type="database_run_id", reference_value=41),
            None,
        ),
        (
            None,
            PersistentUpstreamReference(reference_type="database_run_id", reference_value=41),
        ),
        (
            PersistentUpstreamReference(reference_type="database_run_id", reference_value=41),
            PersistentUpstreamReference(reference_type="database_run_id", reference_value=42),
        ),
        (None, None),
    ],
)
def test_validate_persistence_command_rejects_persistent_reference_mismatch(
    identity_ref: PersistentUpstreamReference | None,
    command_ref: PersistentUpstreamReference | None,
) -> None:
    command = _make_command(
        identity=_make_identity(source_role="task8_forecast_run", ref=identity_ref),
        command_ref=command_ref,
    )

    with pytest.raises(RollingBacktestCommandMismatchError) as exc:
        validate_persistence_command(command)

    assert exc.value.code == "ROLLING_BACKTEST_COMMAND_MISMATCH"


def test_validate_persistence_command_accepts_matching_pinned_reference() -> None:
    ref = PersistentUpstreamReference(reference_type="database_run_id", reference_value=41)
    command = _make_command(
        identity=_make_identity(source_role="task8_forecast_run", ref=ref),
        command_ref=ref,
    )

    validate_persistence_command(command)


def test_resolved_input_canonical_payload_excludes_persistent_reference_fields() -> None:
    identity = _make_identity(
        source_role="task8_forecast_run",
        ref=PersistentUpstreamReference(
            reference_type="database_run_id",
            reference_value=41,
        ),
    )
    node = _make_node(identities=(identity,))
    config = _make_config(nodes=(node,))
    payload = _resolved_input_canonical_payload(identity)

    for raw in (
        canonical_json_dumps(rolling_backtest_config_payload(config)),
        canonical_json_dumps(node_signature_payload(config, config.nodes[0])),
        canonical_json_dumps(payload),
    ):
        assert "persistent_reference" not in raw
        assert "database_id" not in raw
        assert "uuid" not in raw
        assert "orm_id" not in raw


def test_multi_identity_round_trip_preserves_canonical_payload() -> None:
    identities = tuple(
        _make_identity(
            source_role=f"role_{index:02d}",
            ref=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=100 + index,
            ),
        )
        for index in (7, 1, 5, 3, 8, 2, 6, 4)
    )
    node = _make_node(identities=identities)
    config = _make_config(nodes=(node,))

    payload = rolling_backtest_config_payload(config)
    reloaded = _config_from_canonical_payload(json.loads(canonical_json_dumps(payload)))

    assert rolling_backtest_config_payload(reloaded) == payload
