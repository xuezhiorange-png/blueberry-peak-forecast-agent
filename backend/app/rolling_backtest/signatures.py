from __future__ import annotations

from typing import cast

from backend.app.rolling_backtest.canonical import canonical_json_value, sha256_payload
from backend.app.rolling_backtest.config import rolling_backtest_config_payload
from backend.app.rolling_backtest.schemas import RollingBacktestConfig, RollingNodeDefinition


def node_signature_payload(node: RollingNodeDefinition) -> dict[str, object]:
    return cast(
        dict[str, object],
        canonical_json_value(
            {
                "season_id": node.season_id,
                "node_key": node.node_key,
                "as_of_local_date": node.as_of_local_date,
                "forecast_cutoff_at": node.forecast_cutoff_at,
                "forecast_start_local_date": node.forecast_start_local_date,
                "forecast_end_local_date": node.forecast_end_local_date,
                "destination_factory_ids": node.destination_factory_ids,
                "execution_mode": node.execution_mode,
                "upstream_selection_mode": node.upstream_selection_mode,
                "forecast_horizon_policy_version": node.forecast_horizon_policy_version,
                "timezone": node.timezone,
                "resolved_upstream_semantic_identities": (
                    node.resolved_upstream_semantic_identities
                ),
            }
        ),
    )


def node_signature_hash(node: RollingNodeDefinition) -> str:
    return sha256_payload(canonical_json_value(node_signature_payload(node)))


def run_signature_payload(config: RollingBacktestConfig) -> dict[str, object]:
    payload = rolling_backtest_config_payload(config)
    return cast(
        dict[str, object],
        canonical_json_value(
            {
                "rolling_schema_version": payload["rolling_schema_version"],
                "canonical_serialization_version": payload["canonical_serialization_version"],
                "availability_registry_version": payload["availability_registry_version"],
                "node_calendar_version": payload["node_calendar_version"],
                "forecast_horizon_policy_version": payload["forecast_horizon_policy_version"],
                "upstream_selection_policy_version": payload["upstream_selection_policy_version"],
                "metric_policy_version": payload["metric_policy_version"],
                "task10_model_policy": payload["task10_model_policy"],
                "calendar_phase_policy_version": payload["calendar_phase_policy_version"],
                "nodes": payload["nodes"],
            }
        ),
    )


def run_signature_hash(config: RollingBacktestConfig) -> str:
    return sha256_payload(canonical_json_value(run_signature_payload(config)))
