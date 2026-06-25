from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.tests.harvest_state.conftest import make_request, sha256_hex


def test_normal_flow_golden_preserves_mass_and_non_negative_inventory() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import run_harvest_state_model

    result = run_harvest_state_model(Task9ARequest.model_validate(make_request()))

    assert result.status == "completed"
    assert all(row.closing_mature_inventory_kg >= 0 for row in result.daily_pool_state_rows)
    assert all(row.mass_balance_passed for row in result.daily_pool_state_rows)


def test_consecutive_rain_golden_reduces_harvest_capacity() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    for feature in payload["daily_weather_features"]:
        if feature["feature_id"] == "consecutive_rainy_days":
            feature["value"] = Decimal("4")
    result = run_harvest_state_model(Task9ARequest.model_validate(payload))

    day = next(
        row
        for row in result.daily_pool_state_rows
        if row.state_date == date(2026, 3, 1) and row.forecast_quantile == "P50"
    )
    assert day.weather_harvest_efficiency_ratio < Decimal("1")


def test_spring_festival_golden_reduces_capacity_not_supply() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["holiday_dates"] = [date(2026, 3, 2)]
    payload["holiday_calendar_hash"] = sha256_hex(
        {
            "holiday_calendar_version": payload["holiday_calendar_version"],
            "holiday_dates": ["2026-03-02"],
        }
    )
    for capacity in payload["daily_capacity_inputs"]:
        if capacity["capacity_date"] == date(2026, 3, 2):
            capacity["labor_availability_ratio"] = Decimal("0")
    result = run_harvest_state_model(Task9ARequest.model_validate(payload))

    holiday_row = next(
        row
        for row in result.daily_pool_state_rows
        if row.state_date == date(2026, 3, 2) and row.forecast_quantile == "P50"
    )
    assert holiday_row.natural_maturity_supply_kg > 0
    assert holiday_row.harvested_quantity_kg == 0


def test_labor_shortage_golden_creates_and_then_digests_backlog() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    for capacity in payload["daily_capacity_inputs"]:
        if capacity["capacity_date"] == date(2026, 3, 1):
            capacity["planned_picker_count"] = Decimal("1")
            capacity["kg_per_person_per_day"] = Decimal("5")
        else:
            capacity["planned_picker_count"] = Decimal("20")
            capacity["kg_per_person_per_day"] = Decimal("20")
    result = run_harvest_state_model(Task9ARequest.model_validate(payload))

    day1 = next(
        row
        for row in result.daily_pool_state_rows
        if row.state_date == date(2026, 3, 1) and row.forecast_quantile == "P50"
    )
    day3 = next(
        row
        for row in result.daily_pool_state_rows
        if row.state_date == date(2026, 3, 3) and row.forecast_quantile == "P50"
    )
    assert day1.unharvested_backlog_kg > 0
    assert day3.unharvested_backlog_kg <= day1.unharvested_backlog_kg
