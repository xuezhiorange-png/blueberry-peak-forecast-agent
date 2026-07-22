from __future__ import annotations

from typing import cast

from backend.app.rolling_backtest.canonical import canonical_json_value, sha256_payload
from backend.app.rolling_backtest.config import rolling_backtest_config_payload
from backend.app.rolling_backtest.schemas import (
    ResolvedUpstreamSemanticIdentity,
    RollingBacktestConfig,
    RollingNodeDefinition,
    S2HistoricalBacktestRequest,
    S2HistoricalBindingRow,
    _s2_node_identity_hash_from_values,
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


def s2_request_payload(request: S2HistoricalBacktestRequest) -> dict[str, object]:
    """Return the canonical S2 request identity projection.

    Business-key lists are normalized by the request schema.  No database
    lookup id, insertion timestamp, or runtime ordering is accepted here.
    """

    return cast(
        dict[str, object],
        canonical_json_value(
            {
                "s2_contract_version": request.s2_contract_version,
                "season_business_keys": request.season_business_keys,
                "farm_business_keys": request.farm_business_keys,
                "subfarm_business_keys": request.subfarm_business_keys,
                "variety_business_keys": request.variety_business_keys,
                "master_identity_resolver_version": request.master_identity_resolver_version,
                "mapping_policy_version": request.mapping_policy_version,
                "resolved_identity_snapshot_hash": request.resolved_identity_snapshot_hash,
                "authority_selection_policy_version": request.authority_selection_policy_version,
                "single_node_identity_hash": request.single_node_identity_hash,
                "forecast_cutoff_at": request.forecast_cutoff_at,
                "label_observation_cutoff_at": request.label_observation_cutoff_at,
                "label_visibility_mode": request.label_visibility_mode,
                "requested_horizons_days": request.requested_horizons_days,
            }
        ),
    )


def s2_request_hash(request: S2HistoricalBacktestRequest) -> str:
    return sha256_payload(s2_request_payload(request))


def s2_node_identity_payload(request: S2HistoricalBacktestRequest) -> dict[str, object]:
    return cast(
        dict[str, object],
        canonical_json_value(
            {
                "s2_contract_version": request.s2_contract_version,
                "season_business_keys": request.season_business_keys,
                "farm_business_keys": request.farm_business_keys,
                "subfarm_business_keys": request.subfarm_business_keys,
                "variety_business_keys": request.variety_business_keys,
                "master_identity_resolver_version": request.master_identity_resolver_version,
                "mapping_policy_version": request.mapping_policy_version,
                "resolved_identity_snapshot_hash": request.resolved_identity_snapshot_hash,
                "authority_selection_policy_version": request.authority_selection_policy_version,
                "forecast_cutoff_at": request.forecast_cutoff_at,
                "label_observation_cutoff_at": request.label_observation_cutoff_at,
                "label_visibility_mode": request.label_visibility_mode,
                "requested_horizons_days": request.requested_horizons_days,
            }
        ),
    )


def s2_node_identity_hash(request: S2HistoricalBacktestRequest) -> str:
    derived = _s2_node_identity_hash_from_values(request.model_dump(mode="python"))
    if request.single_node_identity_hash != derived:
        raise ValueError("request node identity does not match canonical node identity")
    return derived


def s2_binding_key_payload(
    request: S2HistoricalBacktestRequest,
    row: S2HistoricalBindingRow,
) -> dict[str, object]:
    return cast(
        dict[str, object],
        canonical_json_value(
            {
                "request_hash": s2_request_hash(request),
                "single_node_identity_hash": s2_node_identity_hash(request),
                "season_business_keys": request.season_business_keys,
                "farm_business_keys": request.farm_business_keys,
                "subfarm_business_keys": request.subfarm_business_keys,
                "variety_business_keys": request.variety_business_keys,
                "horizon_days": row.horizon_days,
                "target_date": row.target_date,
                "business_grain_hash": (
                    row.actual_label.business_grain_hash if row.actual_label is not None else None
                ),
            }
        ),
    )


def s2_binding_key_hash(
    request: S2HistoricalBacktestRequest,
    row: S2HistoricalBindingRow,
) -> str:
    return sha256_payload(s2_binding_key_payload(request, row))


def s2_binding_row_payload(row: S2HistoricalBindingRow) -> dict[str, object]:
    return cast(
        dict[str, object],
        canonical_json_value(row.model_dump(mode="python", exclude={"row_hash"})),
    )


def s2_binding_row_hash(row: S2HistoricalBindingRow) -> str:
    return sha256_payload(s2_binding_row_payload(row))


def s2_instance_payload(
    request: S2HistoricalBacktestRequest,
    rows: tuple[S2HistoricalBindingRow, ...],
) -> dict[str, object]:
    return cast(
        dict[str, object],
        canonical_json_value(
            {
                "request": s2_request_payload(request),
                "binding_rows": tuple(
                    {
                        "row_hash": row.row_hash,
                        "horizon_days": row.horizon_days,
                        "target_date": row.target_date,
                    }
                    for row in sorted(rows, key=lambda item: (item.horizon_days, item.target_date))
                ),
            }
        ),
    )


def s2_instance_hash(
    request: S2HistoricalBacktestRequest,
    rows: tuple[S2HistoricalBindingRow, ...],
) -> str:
    return sha256_payload(s2_instance_payload(request, rows))
