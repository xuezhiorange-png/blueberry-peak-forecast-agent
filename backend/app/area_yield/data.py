"""Explicit quantity/area correspondence, receipt deduplication and ledger calendars."""

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

QUANTUM = Decimal("0.000001")


def fixed(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("non-finite quantity")
    return format(value.quantize(QUANTUM, rounding=ROUND_HALF_EVEN), "f")


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def calendar(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("invalid calendar")
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


@dataclass(frozen=True)
class AreaAuthority:
    scope_id: str
    season_id: str
    start: date
    end: date
    area_mu: Decimal
    basis: str
    source: str
    complete_ledger: bool


@dataclass(frozen=True)
class Receipt:
    source_id: str
    scope_id: str
    season_id: str
    day: date
    quantity: Decimal
    grain: str


def materialize(receipts: list[Receipt], authority: AreaAuthority) -> list[dict[str, str]]:
    if not authority.area_mu.is_finite() or authority.area_mu <= 0 or not authority.source:
        raise ValueError("area authority invalid")
    if authority.basis not in {"MEASURED", "AUTHORIZED_CALIBRATION"}:
        raise ValueError("area basis invalid")
    seen: dict[str, Receipt] = {}
    totals: dict[date, Decimal] = defaultdict(Decimal)
    grains: set[str] = set()
    for row in receipts:
        if (row.scope_id, row.season_id) != (authority.scope_id, authority.season_id):
            raise ValueError("quantity/area scope or season mismatch")
        if not authority.start <= row.day <= authority.end:
            raise ValueError("quantity outside area effective period")
        if not row.quantity.is_finite() or row.quantity < 0 or not row.source_id:
            raise ValueError("invalid receipt")
        if row.source_id in seen:
            if seen[row.source_id] != row:
                raise ValueError("conflicting duplicate receipt")
            continue
        seen[row.source_id] = row
        grains.add(row.grain)
        totals[row.day] += row.quantity
    if len(grains) != 1 or not grains <= {"DETAIL", "AGGREGATE"}:
        raise ValueError("aggregate/detail overlap or empty receipts")
    return [
        {
            "scope_id": authority.scope_id,
            "season_id": authority.season_id,
            "date": day.isoformat(),
            "area_mu": fixed(authority.area_mu),
            "area_basis": authority.basis,
            "area_source": authority.source,
            "area_effective_period": f"{authority.start}/{authority.end}",
            "actual_kg": fixed(totals.get(day, Decimal(0)))
            if day in totals or authority.complete_ledger
            else "",
            "observation_status": "OBSERVED"
            if day in totals
            else "AUTHORIZED_LEDGER_ZERO"
            if authority.complete_ledger
            else "UNKNOWN_MISSING",
        }
        for day in calendar(authority.start, authority.end)
    ]
