"""R4 historical harvest aggregation and explicitly authorized baseline policies.

This is a partial calibration payload, not a new parameter library or Task8
model. It never invents an anchor or maps spline density to undefined scalar
width/skewness parameters. Persistence uses the existing planning services only
after the missing model adapter is resolved.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from backend.app.planning.hashing import input_hash

POLICY_VERSION = "v0.3-banna-arrival-equals-harvest-baseline-r4"
PRECISION = Decimal("0.000001")


@dataclass(frozen=True)
class HarvestFact:
    source_row_identity: str
    harvest_date: date
    arrival_quantity_kg: Decimal


@dataclass(frozen=True)
class HistoricalArea:
    farm_name: str
    variety_code: str
    start_date: date
    end_date: date
    area_mu: Decimal
    source_identity: str


def build_harvest_baseline(
    facts: tuple[HarvestFact, ...],
    *,
    source_sha256: str,
    farm_name: str,
    variety_code: str,
    factory_name: str,
    source_visible_on: date,
    as_of_date: date,
    historical_area: HistoricalArea | None = None,
) -> dict[str, Any]:
    """Aggregate already scope-selected, hash-verified facts without zero fill.

    Caller must resolve farm/variety/factory and verify the exact source bytes.
    A current acceptance area is deliberately not a default historical area.
    """
    if len(source_sha256) != 64 or any(c not in "0123456789abcdef" for c in source_sha256):
        raise ValueError("source SHA256 required")
    if not facts or not all((farm_name, variety_code, factory_name)):
        raise ValueError("nonempty authorized scope and facts required")
    if source_visible_on > as_of_date:
        raise ValueError("future source visibility")
    seen: set[str] = set()
    daily: dict[date, Decimal] = {}
    for row in sorted(facts, key=lambda item: item.source_row_identity):
        if not row.source_row_identity or row.source_row_identity in seen:
            raise ValueError("missing or duplicate source row identity")
        seen.add(row.source_row_identity)
        value = row.arrival_quantity_kg
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise ValueError("invalid harvest quantity")
        if row.harvest_date > as_of_date:
            raise ValueError("future harvest fact")
        daily[row.harvest_date] = daily.get(row.harvest_date, Decimal("0")) + value
    total = sum(daily.values(), Decimal("0"))
    if total <= 0:
        raise ValueError("positive historical harvest total required")
    dates = sorted(daily)
    parameters: dict[str, Any] = {
        "marketable_rate": {
            "value": "1.000000",
            "unit": "ratio",
            "authority_type": "BASELINE_POLICY",
            "policy_reason": (
                "Historical arrival is harvested usable quantity; do not double-discount it."
            ),
        },
        "harvest_realization_rate": {
            "value": "1.000000",
            "unit": "ratio",
            "authority_type": "BASELINE_POLICY",
            "policy_reason": (
                "No additional realization discount; "
                "Task9 capacity and inventory constraints remain."
            ),
        },
    }
    area_payload = None
    if historical_area is not None:
        area = historical_area
        if (
            area.farm_name != farm_name
            or area.variety_code != variety_code
            or area.start_date > dates[0]
            or area.end_date < dates[-1]
            or not area.source_identity
            or not isinstance(area.area_mu, Decimal)
            or not area.area_mu.is_finite()
            or area.area_mu <= 0
        ):
            raise ValueError("historical area scope/window/source invalid")
        area_payload = {
            "area_mu": str(area.area_mu.quantize(PRECISION)),
            "source_identity": area.source_identity,
            "start_date": area.start_date.isoformat(),
            "end_date": area.end_date.isoformat(),
        }
        parameters["yield_kg_per_mu"] = {
            "value": str((total / area.area_mu).quantize(PRECISION)),
            "unit": "kg_per_mu",
            "authority_type": "DERIVED_FROM_HISTORY",
            "formula": "sum(historical_arrival_quantity_kg) / historical_planted_area_mu",
        }
    peak = max(dates, key=lambda day: daily[day])
    payload: dict[str, Any] = {
        "policy_version": POLICY_VERSION,
        "arrival_equals_harvest": True,
        "source_sha256": source_sha256,
        "source_visible_on": source_visible_on.isoformat(),
        "as_of_date": as_of_date.isoformat(),
        "farm_name": farm_name,
        "variety_code": variety_code,
        "factory_name": factory_name,
        "source_row_count": len(facts),
        "source_row_identity_hash": input_hash({"rows": sorted(seen)}, as_of_date=as_of_date),
        "window_start": dates[0].isoformat(),
        "window_end": dates[-1].isoformat(),
        "observed_day_count": len(dates),
        "missing_calendar_day_count": (dates[-1] - dates[0]).days + 1 - len(dates),
        "missing_day_zero_fill": False,
        "historical_total_harvest_kg": str(total.quantize(PRECISION)),
        "first_positive_harvest_date": next(day for day in dates if daily[day] > 0).isoformat(),
        "raw_peak_date": peak.isoformat(),
        "raw_peak_quantity_kg": str(daily[peak].quantize(PRECISION)),
        "raw_peak_is_smoothed_maturity_peak": False,
        "daily_harvest": [
            {"date": day.isoformat(), "kg": str(daily[day].quantize(PRECISION))} for day in dates
        ],
        "historical_area_binding_available": historical_area is not None,
        "historical_area": area_payload,
        "parameters": parameters,
        "parameter_library_ready": False,
    }
    payload["calibration_hash"] = input_hash(payload, as_of_date=as_of_date)
    return payload
