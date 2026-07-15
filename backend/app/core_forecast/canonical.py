from __future__ import annotations

import hashlib

from backend.app.core_forecast.schemas import (
    QUANTILE_RANK,
    CompleteDailyMarketableCurveRow,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps

DAILY_CURVE_SCHEMA_VERSION = "v0.1-complete-daily-marketable-curve-v1"
METRICS_SCHEMA_VERSION = "v0.1-core-forecast-metrics-v1"


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
