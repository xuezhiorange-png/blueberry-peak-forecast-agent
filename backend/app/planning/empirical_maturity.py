"""Acceptance empirical harvest proxy; not a spline or physiological model."""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from backend.app.harvest_state.canonical import is_sha256_hex, quantize_quantity, sha256_hex

POLICY_VERSION = "v0.3-banna-empirical-harvest-baseline-r5"


def build_empirical_curve(
    daily: dict[date, Decimal],
    *,
    source_hash: str,
    area_mu: Decimal,
    as_of: date,
) -> dict[str, Any]:
    if not daily or not is_sha256_hex(source_hash):
        raise ValueError("verified nonempty ledger required")
    if not isinstance(area_mu, Decimal) or not area_mu.is_finite() or area_mu <= 0:
        raise ValueError("invalid calibration area")
    if any(not isinstance(v, Decimal) or not v.is_finite() or v < 0 for v in daily.values()):
        raise ValueError("invalid harvest fact")
    start, end = min(daily), max(daily)
    if end >= as_of:
        raise ValueError("historical source must precede acceptance as-of")
    dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    values = [daily.get(day, Decimal("0")) for day in dates]
    total = sum(values, Decimal("0"))
    if total <= 0:
        raise ValueError("positive historical total required")
    yield_value = (total / area_mu).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    expected = (area_mu * yield_value).quantize(Decimal("0.000001"))
    # Reconcile at Task9's existing kg precision. Never put residue on zero days.
    largest = values.index(max(values))
    shares = [(value / total).quantize(Decimal("1e-18")) for value in values]
    shares[largest] += Decimal("1") - sum(shares)
    supply = [quantize_quantity(expected * share) for share in shares]
    supply[largest] += quantize_quantity(expected) - sum(supply)
    forecast_start = date(as_of.year, start.month, start.day)
    if forecast_start <= as_of:
        forecast_start = date(as_of.year + 1, start.month, start.day)
    payload: dict[str, Any] = {
        "policy_version": POLICY_VERSION,
        "maturity_authority_type": "HISTORICAL_CALIBRATION",
        "truth_class": "FORECAST_CALIBRATION_PROXY",
        "arrival_equals_harvest": True,
        "source_hash": source_hash,
        "as_of": as_of.isoformat(),
        "calendar_start": start.isoformat(),
        "calendar_end": end.isoformat(),
        "observed_day_count": len(daily),
        "zero_filled_day_count": len(dates) - len(daily),
        "zero_fill_authority": "COORDINATOR_COMPLETE_RECEIPT_LEDGER_R5",
        "forecast_date_policy": "NEXT_FUTURE_HISTORICAL_START_MONTH_DAY_RELATIVE_INDEX_V1",
        "forecast_start": forecast_start.isoformat(),
        "forecast_end": (forecast_start + timedelta(days=len(dates) - 1)).isoformat(),
        "calibration_area_mu": format(area_mu, ".6f"),
        "yield_kg_per_mu": format(yield_value, ".6f"),
        "yield_authority_type": "ACCEPTANCE_BASELINE_CALIBRATION",
        "historical_total_kg": format(total, ".6f"),
        "expected_total_before_task9_rounding": format(expected, ".6f"),
        "capacity_kg_per_day": format(max(values), ".6f"),
        "capacity_authority_type": "DERIVED_FROM_HISTORICAL_HARVEST",
        "marketable_rate": "1.000000",
        "harvest_realization_rate": "1.000000",
        "neutral_corrections_authority_type": "BASELINE_POLICY",
        "uncertainty_status": "NOT_CALIBRATED_IDENTICAL_POINT_SCENARIOS",
        "days": [
            {
                "relative_day_index": i,
                "historical_date": day.isoformat(),
                "date": (forecast_start + timedelta(days=i)).isoformat(),
                "historical_kg": format(values[i], ".6f"),
                "observed": day in daily,
                "share": format(shares[i], ".18f"),
                "supply_kg": format(supply[i], ".3f"),
            }
            for i, day in enumerate(dates)
        ],
    }
    payload["curve_hash"] = sha256_hex(payload)
    return payload
