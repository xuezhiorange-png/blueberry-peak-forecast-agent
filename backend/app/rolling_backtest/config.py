from __future__ import annotations

from backend.app.rolling_backtest.canonical import canonical_json_value, sha256_payload
from backend.app.rolling_backtest.schemas import RollingBacktestConfig


def rolling_backtest_config_payload(config: RollingBacktestConfig) -> dict[str, object]:
    return {
        "rolling_schema_version": config.rolling_schema_version,
        "canonical_serialization_version": config.canonical_serialization_version,
        "availability_registry_version": config.availability_registry_version,
        "node_calendar_version": config.node_calendar_version,
        "forecast_horizon_policy_version": config.forecast_horizon_policy_version,
        "upstream_selection_policy_version": config.upstream_selection_policy_version,
        "metric_policy_version": config.metric_policy_version,
        "task10_model_policy": config.task10_model_policy,
        "calendar_phase_policy_version": config.calendar_phase_policy_version,
        "cutoff_timezone": config.cutoff_timezone,
        "cutoff_local_time": config.cutoff_local_time,
        "nodes": config.nodes,
    }


def rolling_backtest_config_hash(config: RollingBacktestConfig) -> str:
    return sha256_payload(canonical_json_value(rolling_backtest_config_payload(config)))
