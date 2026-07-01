from __future__ import annotations

from typing import cast

from backend.app.rolling_backtest.canonical import canonical_json_value, sha256_payload
from backend.app.rolling_backtest.config import rolling_backtest_config_payload
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
        "semantic": item.semantic.model_dump(mode="python", exclude={"display_label"}),
    }


def node_signature_payload(
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> dict[str, object]:
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
                "scope": node.scope,
                "execution_mode": config.execution_mode,
                "upstream_selection_mode": node.upstream_selection_mode,
                "forecast_horizon_policy_version": node.forecast_horizon_policy_version,
                "task10_model_policy": node.task10_model_policy,
                "cutoff_policy_version": config.cutoff_policy_version,
                "timezone": node.timezone,
                "resolved_upstream_semantic_identities": tuple(
                    _semantic_identity_payload(item)
                    for item in node.resolved_upstream_semantic_identities
                ),
            }
        ),
    )


def node_signature_hash(
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> str:
    return sha256_payload(canonical_json_value(node_signature_payload(config, node)))


def run_signature_payload(config: RollingBacktestConfig) -> dict[str, object]:
    return cast(
        dict[str, object],
        canonical_json_value(rolling_backtest_config_payload(config)),
    )


def run_signature_hash(config: RollingBacktestConfig) -> str:
    return sha256_payload(canonical_json_value(run_signature_payload(config)))
