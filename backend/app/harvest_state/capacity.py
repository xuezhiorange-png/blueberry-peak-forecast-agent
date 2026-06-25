from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo


@dataclass(slots=True)
class FIFOAllocation:
    stable_cohort_key: str
    harvested_quantity_kg: Decimal


@dataclass(slots=True)
class FIFOLossAllocation:
    stable_cohort_key: str
    loss_quantity_kg: Decimal


def _resolve_local_datetime(
    *,
    local_date: date,
    local_time: time,
    timezone_name: str,
) -> datetime:
    zone = ZoneInfo(timezone_name)
    naive = datetime.combine(local_date, local_time)
    valid_candidates: list[datetime] = []
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=zone, fold=fold)
        roundtrip = candidate.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
        if roundtrip == naive:
            valid_candidates.append(candidate)
    if not valid_candidates:
        raise ValueError("NONEXISTENT_LOCAL_TIME")
    offsets = {candidate.utcoffset() for candidate in valid_candidates}
    if len(offsets) > 1:
        raise ValueError("AMBIGUOUS_LOCAL_TIME")
    return valid_candidates[0]


def resolve_harvest_arrival(
    *,
    harvest_local_date: date,
    harvest_bucket_anchor_local_time: time,
    farm_timezone: str,
    destination_factory_timezone: str,
    harvest_to_arrival_lag_days: int,
) -> dict[str, datetime | date]:
    destination_zone = ZoneInfo(destination_factory_timezone)
    harvest_anchor_at = _resolve_local_datetime(
        local_date=harvest_local_date,
        local_time=harvest_bucket_anchor_local_time,
        timezone_name=farm_timezone,
    )
    arrival_at_utc = harvest_anchor_at.astimezone(UTC) + timedelta(days=harvest_to_arrival_lag_days)
    arrival_local = arrival_at_utc.astimezone(destination_zone)
    return {
        "harvest_anchor_at": harvest_anchor_at,
        "arrival_at": arrival_local,
        "arrival_local_date": arrival_local.date(),
    }


def harvest_arrival_datetimes(
    *,
    harvest_local_date: date,
    harvest_bucket_anchor_local_time: str,
    farm_timezone: str,
    destination_factory_timezone: str,
    harvest_to_arrival_lag_days: int,
) -> dict[str, str | date]:
    anchor_time = datetime.strptime(harvest_bucket_anchor_local_time, "%H:%M:%S").time()
    resolved = resolve_harvest_arrival(
        harvest_local_date=harvest_local_date,
        harvest_bucket_anchor_local_time=anchor_time,
        farm_timezone=farm_timezone,
        destination_factory_timezone=destination_factory_timezone,
        harvest_to_arrival_lag_days=harvest_to_arrival_lag_days,
    )
    return {
        "harvest_anchor_at": resolved["harvest_anchor_at"].isoformat(),
        "arrival_at": resolved["arrival_at"].isoformat(),
        "arrival_local_date": resolved["arrival_local_date"],
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
        cohort["remaining_quantity_kg"] = available - consumed
        remaining -= consumed
        allocations.append(
            FIFOLossAllocation(
                stable_cohort_key=str(cohort["stable_cohort_key"]),
                loss_quantity_kg=consumed,
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
        cohort["remaining_quantity_kg"] = available - harvested
        remaining -= harvested
        allocations.append(
            FIFOAllocation(
                stable_cohort_key=str(cohort["stable_cohort_key"]),
                harvested_quantity_kg=harvested,
            )
        )
    return allocations
