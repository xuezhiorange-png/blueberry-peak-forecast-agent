from __future__ import annotations

from backend.app.rolling_backtest.canonical import canonical_json_value, sha256_payload
from backend.app.rolling_backtest.schemas import (
    ResolvedUpstreamSemanticIdentity,
    RollingBacktestConfig,
    RollingNodeDefinition,
)


def _semantic_identity_payload(
    item: ResolvedUpstreamSemanticIdentity,
) -> dict[str, object]:
    return {
        "source_type": item.source_type,
        "source_role": item.source_role,
        "role_qualifier": item.role_qualifier,
        "semantic": item.semantic,
    }


def _node_semantic_payload(node: RollingNodeDefinition) -> dict[str, object]:
    return {
        "season_id": node.season_id,
        "node_key": node.node_key,
        "as_of_local_date": node.as_of_local_date,
        "forecast_cutoff_at": node.forecast_cutoff_at,
        "forecast_start_local_date": node.forecast_start_local_date,
        "forecast_end_local_date": node.forecast_end_local_date,
        "scope": node.scope,
        "upstream_selection_mode": node.upstream_selection_mode,
        "forecast_horizon_policy_version": node.forecast_horizon_policy_version,
        "timezone": node.timezone,
        "resolved_upstream_semantic_identities": tuple(
            _semantic_identity_payload(item) for item in node.resolved_upstream_semantic_identities
        ),
    }


def rolling_backtest_config_payload(config: RollingBacktestConfig) -> dict[str, object]:
    return {
        "rolling_schema_version": config.rolling_schema_version,
        "canonical_serialization_version": config.canonical_serialization_version,
        "availability_registry_version": config.availability_registry_version,
        "node_calendar_version": config.node_calendar_version,
        "forecast_horizon_policy_version": config.forecast_horizon_policy_version,
        "upstream_selection_policy_version": config.upstream_selection_policy_version,
        "metric_policy_version": config.metric_policy_version,
        "execution_mode": config.execution_mode,
        "task10_model_policy": config.task10_model_policy,
        "calendar_phase_policy_version": config.calendar_phase_policy_version,
        "cutoff_policy_version": config.cutoff_policy_version,
        "cutoff_timezone": config.cutoff_timezone,
        "cutoff_local_time": config.cutoff_local_time,
        "nodes": tuple(_node_semantic_payload(node) for node in config.nodes),
    }


def rolling_backtest_config_hash(config: RollingBacktestConfig) -> str:
    return sha256_payload(canonical_json_value(rolling_backtest_config_payload(config)))
