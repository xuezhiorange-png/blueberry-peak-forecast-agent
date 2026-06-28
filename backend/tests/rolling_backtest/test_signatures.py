from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
    ExecutionMode,
    UpstreamSelectionMode,
)
from backend.app.rolling_backtest.schemas import (
    ResolvedUpstreamSemanticIdentity,
    RollingBacktestConfig,
    RollingNodeDefinition,
)
from backend.app.rolling_backtest.signatures import (
    node_signature_hash,
    node_signature_payload,
    run_signature_hash,
    run_signature_payload,
)


def _golden_path(name: str) -> Path:
    return Path(__file__).parent / "golden" / name


def _node(
    *,
    node_key: str = "march_15",
    as_of_local_date: date = date(2026, 3, 15),
    forecast_start_local_date: date = date(2026, 3, 16),
    forecast_end_local_date: date = date(2026, 3, 31),
    forecast_cutoff_at: datetime = datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
    execution_mode: ExecutionMode = ExecutionMode.HISTORICAL_OBSERVED,
    identities: tuple[ResolvedUpstreamSemanticIdentity, ...] = (),
) -> RollingNodeDefinition:
    return RollingNodeDefinition(
        season_id=2026,
        node_key=node_key,
        as_of_local_date=as_of_local_date,
        forecast_cutoff_at=forecast_cutoff_at,
        forecast_start_local_date=forecast_start_local_date,
        forecast_end_local_date=forecast_end_local_date,
        destination_factory_ids=(202, 101),
        execution_mode=execution_mode,
        upstream_selection_mode=UpstreamSelectionMode.HISTORICAL_RESOLUTION,
        forecast_horizon_policy_version="task11-horizon-v1",
        timezone="Asia/Shanghai",
        resolved_upstream_semantic_identities=identities,
    )


def _config(nodes: tuple[RollingNodeDefinition, ...]) -> RollingBacktestConfig:
    return RollingBacktestConfig(
        rolling_schema_version="task11-rolling-v1",
        canonical_serialization_version="task11-canonical-v1",
        availability_registry_version="task11-availability-v1",
        node_calendar_version="task11-calendar-v1",
        forecast_horizon_policy_version="task11-horizon-v1",
        upstream_selection_policy_version="task11-selection-v1",
        metric_policy_version="task11-metrics-v1",
        task10_model_policy="historically_available_model",
        calendar_phase_policy_version="task11-calendar-phase-v1",
        cutoff_timezone="Asia/Shanghai",
        cutoff_local_time="12:00:00",
        nodes=nodes,
    )


def test_signature_payloads_match_golden() -> None:
    payload = json.loads(_golden_path("signature_payloads.json").read_text(encoding="utf-8"))
    node = _node(
        identities=(
            ResolvedUpstreamSemanticIdentity(
                source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                semantic_identity="task9:run:77",
                payload_hash="1" * 64,
            ),
            ResolvedUpstreamSemanticIdentity(
                source_type=AvailabilitySourceType.TASK10_MODEL_ARTIFACT,
                semantic_identity="task10:artifact:P50",
                payload_hash="2" * 64,
            ),
        )
    )
    config = _config((node,))

    assert node_signature_payload(node) == payload["historical_node_payload"]
    assert run_signature_payload(config) == payload["historical_run_payload"]
    assert node_signature_hash(node) == payload["historical_node_hash"]
    assert run_signature_hash(config) == payload["historical_run_hash"]


def test_run_signature_is_deterministic_for_reordered_nodes() -> None:
    left = _config(
        (
            _node(),
            _node(
                node_key="march_31",
                as_of_local_date=date(2026, 3, 31),
                forecast_start_local_date=date(2026, 4, 1),
                forecast_end_local_date=date(2026, 4, 7),
                forecast_cutoff_at=datetime(2026, 3, 31, 12, 0, tzinfo=UTC),
                execution_mode=ExecutionMode.HISTORICAL_OBSERVED,
                identities=(
                    ResolvedUpstreamSemanticIdentity(
                        source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                        semantic_identity="task9:run:99",
                        payload_hash="9" * 64,
                    ),
                ),
            ),
        )
    )
    right = _config(tuple(reversed(left.nodes)))
    assert run_signature_hash(left) == run_signature_hash(right)


def test_historical_and_replay_signatures_differ() -> None:
    historical = _node(execution_mode=ExecutionMode.HISTORICAL_OBSERVED)
    replay = _node(execution_mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert node_signature_hash(historical) != node_signature_hash(replay)


def test_reordered_semantically_unordered_inputs_produce_same_hash() -> None:
    left = _node(
        identities=(
            ResolvedUpstreamSemanticIdentity(
                source_type=AvailabilitySourceType.TASK10_MODEL_ARTIFACT,
                semantic_identity="artifact:p80",
                payload_hash="b" * 64,
            ),
            ResolvedUpstreamSemanticIdentity(
                source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                semantic_identity="run:9",
                payload_hash="a" * 64,
            ),
        )
    )
    right = _node(identities=tuple(reversed(left.resolved_upstream_semantic_identities)))
    assert node_signature_hash(left) == node_signature_hash(right)


def test_runtime_fields_do_not_affect_semantic_signature() -> None:
    node = _node()
    payload = node_signature_payload(node)
    payload["status"] = "completed"
    payload["replay_executed_at"] = "2026-06-28T12:00:00Z"
    assert node_signature_hash(node) == node_signature_hash(node)
