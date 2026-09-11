from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.app.planning.empirical_maturity import build_empirical_curve


def test_empirical_calendar_and_denominator() -> None:
    curve = build_empirical_curve(
        {date(2024, 10, 15): Decimal("10"), date(2025, 5, 9): Decimal("20")},
        source_hash="a" * 64,
        area_mu=Decimal("736"),
        as_of=date(2026, 9, 11),
    )
    assert len(curve["days"]) == 207
    assert curve["zero_filled_day_count"] == 205
    assert sum(Decimal(row["share"]) for row in curve["days"]) == 1
    assert curve["forecast_start"] == "2026-10-15"
    assert curve["forecast_end"] == "2027-05-09"
    assert curve["maturity_authority_type"] == "HISTORICAL_CALIBRATION"
    assert "maturity_width_days" not in curve
    assert "model_run_id" not in curve


def test_authorized_yield_calculation() -> None:
    curve = build_empirical_curve(
        {date(2024, 10, 15): Decimal("968113.233000")},
        source_hash="a" * 64,
        area_mu=Decimal("736.000000"),
        as_of=date(2026, 9, 11),
    )
    assert curve["yield_kg_per_mu"] == "1315.371240"
    assert curve["expected_total_before_task9_rounding"] == "968113.232640"
    assert sum(Decimal(row["supply_kg"]) for row in curve["days"]) == Decimal("968113.233")


def test_empirical_hash_deterministic_and_input_sensitive() -> None:
    days = {date(2025, 1, 1) + timedelta(days=i): Decimal(i + 1) for i in range(10)}

    def run(daily: dict) -> dict:
        return build_empirical_curve(
            daily, source_hash="a" * 64, area_mu=Decimal("736"), as_of=date(2026, 9, 11)
        )

    assert run(days) == run(dict(reversed(list(days.items()))))
    changed = dict(days)
    changed[date(2025, 1, 1)] = Decimal("2")
    assert run(days)["curve_hash"] != run(changed)["curve_hash"]


def test_negative_empirical_fact_rejected() -> None:
    with pytest.raises(ValueError):
        build_empirical_curve(
            {date(2025, 1, 1): Decimal("-1")},
            source_hash="a" * 64,
            area_mu=Decimal("736"),
            as_of=date(2026, 9, 11),
        )


def test_complete_ledger_181_observed_plus_26_zero_days():
    start = date(2024, 10, 15)
    indices = [0, *range(27, 207)]
    daily = {start + timedelta(days=i): Decimal(i + 1) for i in indices}
    curve = build_empirical_curve(
        daily, source_hash="a" * 64, area_mu=Decimal("736"), as_of=date(2026, 9, 11)
    )
    assert curve["observed_day_count"] == 181
    assert curve["zero_filled_day_count"] == 26
    assert len(curve["days"]) == 207
    assert all(
        Decimal(r["historical_kg"]) == 0 and Decimal(r["share"]) == 0
        for r in curve["days"]
        if not r["observed"]
    )
    assert curve["arrival_equals_harvest"] is True


def test_empirical_source_must_precede_as_of():
    with pytest.raises(ValueError, match="precede"):
        build_empirical_curve(
            {date(2026, 9, 11): Decimal(1)},
            source_hash="a" * 64,
            area_mu=Decimal(736),
            as_of=date(2026, 9, 11),
        )
