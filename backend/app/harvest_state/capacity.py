from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from backend.app.harvest_state.canonical import quantize_quantity


@dataclass(slots=True)
class FIFOAllocation:
    stable_cohort_key: str
    harvested_quantity_kg: Decimal


@dataclass(slots=True)
class FIFOLossAllocation:
    stable_cohort_key: str
    loss_quantity_kg: Decimal


def harvest_arrival_datetimes(
    *,
    harvest_local_date: date,
    harvest_bucket_anchor_local_time: str,
    farm_timezone: str,
    destination_factory_timezone: str,
    harvest_to_arrival_lag_days: int,
) -> dict[str, str | date]:
    farm_zone = ZoneInfo(farm_timezone)
    destination_zone = ZoneInfo(destination_factory_timezone)
    anchor_time = datetime.strptime(harvest_bucket_anchor_local_time, "%H:%M:%S").time()
    harvest_anchor_at = datetime.combine(harvest_local_date, anchor_time, farm_zone)
    arrival_at = harvest_anchor_at + timedelta(days=harvest_to_arrival_lag_days)
    arrival_local = arrival_at.astimezone(destination_zone)
    return {
        "harvest_anchor_at": harvest_anchor_at.isoformat(),
        "arrival_at": arrival_local.isoformat(),
        "arrival_local_date": arrival_local.date(),
    }


def allocate_fifo_loss(
    cohorts: list[dict[str, object]],
    loss_quantity_kg: Decimal,
) -> list[FIFOLossAllocation]:
    remaining = loss_quantity_kg
    allocations: list[FIFOLossAllocation] = []
    for cohort in cohorts:
        if remaining <= 0:
            break
        available = cohort["remaining_quantity_kg"]
        if not isinstance(available, Decimal):
            raise TypeError("remaining_quantity_kg must be Decimal")
        consumed = min(available, remaining)
        cohort["remaining_quantity_kg"] = quantize_quantity(available - consumed)
        remaining -= consumed
        allocations.append(
            FIFOLossAllocation(
                stable_cohort_key=str(cohort["stable_cohort_key"]),
                loss_quantity_kg=quantize_quantity(consumed),
            )
        )
    return allocations


def allocate_fifo_harvest(
    cohorts: list[dict[str, object]],
    capacity_kg: Decimal,
) -> list[FIFOAllocation]:
    remaining = capacity_kg
    allocations: list[FIFOAllocation] = []
    for cohort in cohorts:
        if remaining <= 0:
            break
        available = cohort["remaining_quantity_kg"]
        if not isinstance(available, Decimal):
            raise TypeError("remaining_quantity_kg must be Decimal")
        harvested = min(available, remaining)
        cohort["remaining_quantity_kg"] = quantize_quantity(available - harvested)
        remaining -= harvested
        allocations.append(
            FIFOAllocation(
                stable_cohort_key=str(cohort["stable_cohort_key"]),
                harvested_quantity_kg=quantize_quantity(harvested),
            )
        )
    return allocations
