from __future__ import annotations

import hashlib
from datetime import UTC

from backend.app.core_forecast.schemas import (
    QUANTILE_RANK,
    CompleteDailyMarketableCurveRequest,
    CompleteDailyMarketableCurveRow,
    CoreForecastCodeAuthority,
    MarketableRetentionPolicySnapshot,
    RegisterCoreForecastCodeAuthority,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps

DAILY_CURVE_SCHEMA_VERSION = "v0.1-complete-daily-marketable-curve-v1"
METRICS_SCHEMA_VERSION = "v0.1-core-forecast-metrics-v1"
CORE_FORECAST_RUN_SCHEMA_VERSION = "v0.1-core-forecast-run-v1"
CORE_FORECAST_REQUEST_SCHEMA_VERSION = "v0.1-core-forecast-request-v1"
CORE_FORECAST_AUTHORITY_RUN_SCHEMA_VERSION = "v0.1-core-forecast-run-authority-v2"
CORE_FORECAST_AUTHORITY_REQUEST_SCHEMA_VERSION = "v0.1-core-forecast-request-authority-v2"
CORE_FORECAST_CODE_AUTHORITY_SCHEMA_VERSION = "v0.1-core-forecast-code-authority-v1"
CORE_FORECAST_DATE_BASIS = "HARVEST_BUSINESS_DATE"


def core_forecast_code_authority_payload(
    authority: RegisterCoreForecastCodeAuthority | CoreForecastCodeAuthority,
) -> dict[str, object]:
    return {
        "authority_schema_version": CORE_FORECAST_CODE_AUTHORITY_SCHEMA_VERSION,
        "source_commit_sha": authority.source_commit_sha,
        "build_artifact_hash": authority.build_artifact_hash,
        "config_bundle_hash": authority.config_bundle_hash,
        "available_at": authority.available_at.astimezone(UTC).isoformat(),
    }


def compute_core_forecast_code_authority_hash(
    authority: RegisterCoreForecastCodeAuthority | CoreForecastCodeAuthority,
) -> str:
    return hashlib.sha256(
        canonical_json_dumps(core_forecast_code_authority_payload(authority)).encode("utf-8")
    ).hexdigest()


def compute_daily_curve_hash(
    rows: tuple[CompleteDailyMarketableCurveRow, ...],
) -> str:
    ordered_rows = sorted(
        rows,
        key=lambda row: (
            row.date,
            row.farm_id,
            row.subfarm_id,
            row.variety_id,
            QUANTILE_RANK[row.forecast_quantile],
        ),
    )
    payload = {
        "schema_version": DAILY_CURVE_SCHEMA_VERSION,
        "rows": [row.model_dump(mode="json") for row in ordered_rows],
    }
    return hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()


def _policy_entry_sort_key(entry: dict[str, object]) -> tuple[object, ...]:
    return (
        entry["forecast_season_id"],
        entry["forecast_season_code"],
        entry["farm_id"],
        entry["subfarm_id"],
        entry["variety_id"],
    )


def _sorted_policy_entries(snapshot: MarketableRetentionPolicySnapshot) -> list[dict[str, object]]:
    entries = [entry.model_dump(mode="json") for entry in snapshot.entries]
    return sorted(entries, key=_policy_entry_sort_key)


def compute_retention_policy_snapshot_hash(
    snapshot: MarketableRetentionPolicySnapshot,
) -> str:
    payload = {"entries": _sorted_policy_entries(snapshot)}
    return hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()


def compute_core_forecast_input_hash(
    request: CompleteDailyMarketableCurveRequest,
    retention_policy: MarketableRetentionPolicySnapshot,
    *,
    code_authority: CoreForecastCodeAuthority | None = None,
) -> str:
    policy_hash = compute_retention_policy_snapshot_hash(retention_policy)
    scopes = sorted(
        (
            {
                "farm_id": scope.farm_id,
                "subfarm_id": scope.subfarm_id,
                "variety_id": scope.variety_id,
            }
            for scope in request.scopes
        ),
        key=lambda item: (item["farm_id"], item["subfarm_id"], item["variety_id"]),
    )
    payload = {
        "request_schema_version": (
            CORE_FORECAST_AUTHORITY_REQUEST_SCHEMA_VERSION
            if code_authority is not None
            else CORE_FORECAST_REQUEST_SCHEMA_VERSION
        ),
        "forecast_season_id": request.forecast_season_id,
        "forecast_season_code": request.forecast_season_code,
        "forecast_start_date": request.forecast_start_date.isoformat(),
        "forecast_end_date": request.forecast_end_date.isoformat(),
        "destination_factory_id": request.destination_factory_id,
        "task8_forecast_run_id": request.task8_forecast_run_id,
        "task9_harvest_state_run_id": request.task9_harvest_state_run_id,
        "scopes": scopes,
        "retention_policy_snapshot": {"entries": _sorted_policy_entries(retention_policy)},
        "retention_policy_snapshot_hash": policy_hash,
    }
    if code_authority is not None:
        payload["code_authority"] = {
            "authority_id": code_authority.authority_id,
            "authority_hash": code_authority.authority_hash,
            **core_forecast_code_authority_payload(code_authority),
        }
    return hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()


def compute_core_forecast_request_hash(
    forecast_input_hash: str,
    rerun_of_run_id: int | None,
    *,
    authority_bound: bool = False,
) -> str:
    payload = {
        "request_schema_version": (
            CORE_FORECAST_AUTHORITY_REQUEST_SCHEMA_VERSION
            if authority_bound
            else CORE_FORECAST_REQUEST_SCHEMA_VERSION
        ),
        "forecast_input_hash": forecast_input_hash,
        "rerun_of_run_id": rerun_of_run_id,
    }
    return hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()


def compute_core_forecast_result_hash(
    *,
    request_hash: str,
    forecast_input_hash: str,
    curve_hash: str,
    metrics_hash: str,
    daily_row_count: int,
    metric_row_count: int,
    authority_bound: bool = False,
) -> str:
    payload = {
        "run_schema_version": (
            CORE_FORECAST_AUTHORITY_RUN_SCHEMA_VERSION
            if authority_bound
            else CORE_FORECAST_RUN_SCHEMA_VERSION
        ),
        "request_hash": request_hash,
        "forecast_input_hash": forecast_input_hash,
        "date_basis": CORE_FORECAST_DATE_BASIS,
        "curve_hash": curve_hash,
        "metrics_hash": metrics_hash,
        "daily_row_count": daily_row_count,
        "metric_row_count": metric_row_count,
    }
    return hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()
