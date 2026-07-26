from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

from .canonical import canonical_json_bytes
from .enums import MetricStatus, ReasonCode
from .schemas import BreakdownSpec, S3BindingRow

MIN_COMPARABLE_ROWS_FOR_REPORTING = 10


def _identity(spec: BreakdownSpec) -> dict[str, Any]:
    return {
        "season_business_key": spec.season_business_key,
        "farm_business_key": spec.farm_business_key,
        "subfarm_business_key": spec.subfarm_business_key,
        "variety_business_key": spec.variety_business_key,
        "model_identity": spec.model_identity,
        "forecast_horizon_days": spec.forecast_horizon_days,
    }


def calculate_breakdown_cells(
    rows: Iterable[S3BindingRow], breakdown_spec: BreakdownSpec
) -> list[dict[str, Any]]:
    comparable_rows = [
        row
        for row in rows
        if row.s2_status == "COMPARABLE"
        and row.forecast_value_kg is not None
        and row.actual_value_kg is not None
    ]
    identity = _identity(breakdown_spec)
    enough = len(comparable_rows) >= MIN_COMPARABLE_ROWS_FOR_REPORTING
    return [
        {
            "cell_identity": identity,
            "cell_identity_hash": hashlib.sha256(canonical_json_bytes(identity)).hexdigest(),
            "metric_status": MetricStatus.COMPUTED if enough else MetricStatus.INSUFFICIENT_SAMPLE,
            "reason_code": ReasonCode.NONE if enough else ReasonCode.BELOW_MINIMUM,
            "comparable_row_count": len(comparable_rows),
        }
    ]
