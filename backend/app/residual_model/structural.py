from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from backend.app.harvest_state.schemas import Task9ACompletedOutput


def aggregate_structural_arrivals(
    output: Task9ACompletedOutput,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[int, date], dict[str, Decimal]] = defaultdict(
        lambda: {"P50": Decimal("0"), "P80": Decimal("0"), "P90": Decimal("0")}
    )

    for member_row in output.daily_member_state_rows:
        bucket = buckets[(member_row.destination_factory_id, member_row.state_date)]
        bucket[member_row.forecast_quantile.value] += member_row.arrival_quantity_kg

    for future_row in output.future_arrival_schedule:
        bucket = buckets[(future_row.destination_factory_id, future_row.arrival_local_date)]
        bucket[future_row.forecast_quantile.value] += future_row.quantity_kg

    structural_rows: list[dict[str, Any]] = []
    for (destination_factory_id, arrival_local_date), quantiles in sorted(
        buckets.items(),
        key=lambda item: (item[0][0], item[0][1]),
    ):
        structural_rows.append(
            {
                "destination_factory_id": destination_factory_id,
                "arrival_local_date": arrival_local_date,
                "forecast_horizon_days": (arrival_local_date - output.forecast_start_date).days + 1,
                "structural_p50_kg": quantiles["P50"],
                "structural_p80_kg": quantiles["P80"],
                "structural_p90_kg": quantiles["P90"],
            }
        )
    return structural_rows
