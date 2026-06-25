from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.tests.harvest_state.conftest import make_request


def test_completed_output_contains_three_state_arrays() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import run_harvest_state_model

    result = run_harvest_state_model(Task9ARequest.model_validate(make_request()))

    assert result.status == "completed"
    assert result.daily_pool_state_rows
    assert result.daily_member_state_rows
    assert result.cohort_transition_rows


def test_pool_rows_equal_member_row_sums() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import run_harvest_state_model

    result = run_harvest_state_model(Task9ARequest.model_validate(make_request()))

    target_pool = next(
        row
        for row in result.daily_pool_state_rows
        if row.state_date == date(2026, 3, 1) and row.forecast_quantile == "P50"
    )
    member_rows = [
        row
        for row in result.daily_member_state_rows
        if row.state_date == target_pool.state_date
        and row.capacity_pool_id == target_pool.capacity_pool_id
        and row.forecast_quantile == target_pool.forecast_quantile
    ]

    assert (
        sum((row.harvested_quantity_kg for row in member_rows), Decimal("0"))
        == target_pool.harvested_quantity_kg
    )
    assert (
        sum((row.arrival_quantity_kg for row in member_rows), Decimal("0"))
        == target_pool.arrival_quantity_kg
    )


def test_member_rows_equal_cohort_transition_sums() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import run_harvest_state_model

    result = run_harvest_state_model(Task9ARequest.model_validate(make_request()))
    target_member = next(
        row
        for row in result.daily_member_state_rows
        if row.state_date == date(2026, 3, 1)
        and row.forecast_quantile == "P50"
        and row.variety_id == 101
    )
    cohort_rows = [
        row
        for row in result.cohort_transition_rows
        if row.state_date == target_member.state_date
        and row.forecast_quantile == target_member.forecast_quantile
        and row.variety_id == target_member.variety_id
    ]
    assert (
        sum((row.harvested_quantity_kg for row in cohort_rows), Decimal("0"))
        == target_member.harvested_quantity_kg
    )
    assert (
        sum((row.closing_quantity_kg for row in cohort_rows), Decimal("0"))
        == target_member.closing_mature_inventory_kg
    )


def test_fifo_backlog_age_is_preserved_across_days() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    for item in payload["daily_capacity_inputs"]:
        item["planned_picker_count"] = Decimal("1")
        item["kg_per_person_per_day"] = Decimal("5")

    result = run_harvest_state_model(Task9ARequest.model_validate(payload))

    day1 = [
        row
        for row in result.cohort_transition_rows
        if row.state_date == date(2026, 3, 1) and row.forecast_quantile == "P50"
    ]
    day2 = [
        row
        for row in result.cohort_transition_rows
        if row.state_date == date(2026, 3, 2) and row.forecast_quantile == "P50"
    ]
    oldest_day1 = min(
        (row for row in day1 if row.closing_quantity_kg > 0),
        key=lambda row: (row.cohort_date, row.variety_id, row.subfarm_id, row.stable_cohort_key),
    )
    matching_day2 = next(
        row for row in day2 if row.stable_cohort_key == oldest_day1.stable_cohort_key
    )
    assert matching_day2.opening_quantity_kg == oldest_day1.closing_quantity_kg


def test_loss_is_applied_before_harvest_and_does_not_create_negative_inventory() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    for item in payload["mature_inventory_loss_inputs"]:
        if item["state_date"] == date(2026, 3, 1) and item["forecast_quantile"] == "P50":
            item["mature_inventory_loss_quantity_kg"] = Decimal("10")
    result = run_harvest_state_model(Task9ARequest.model_validate(payload))
    target = next(
        row
        for row in result.daily_pool_state_rows
        if row.state_date == date(2026, 3, 1) and row.forecast_quantile == "P50"
    )

    assert target.harvestable_mature_quantity_kg == target.available_mature_quantity_kg - Decimal(
        "10"
    )
    assert target.closing_mature_inventory_kg >= 0


def test_future_arrival_schedule_preserved_when_arrival_outside_window() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["harvest_to_arrival_lag_days"] = 5
    result = run_harvest_state_model(Task9ARequest.model_validate(payload))

    assert result.future_arrival_schedule
    assert all(
        entry.arrival_local_date > date(2026, 3, 3) for entry in result.future_arrival_schedule
    )


def test_shanghai_to_tokyo_arrival_date_example() -> None:
    from backend.app.harvest_state.capacity import harvest_arrival_datetimes

    arrival = harvest_arrival_datetimes(
        harvest_local_date=date(2026, 3, 1),
        harvest_bucket_anchor_local_time="18:00:00",
        farm_timezone="Asia/Shanghai",
        destination_factory_timezone="Asia/Tokyo",
        harvest_to_arrival_lag_days=1,
    )

    assert arrival["harvest_anchor_at"] == "2026-03-01T18:00:00+08:00"
    assert arrival["arrival_at"] == "2026-03-02T19:00:00+09:00"
    assert arrival["arrival_local_date"] == date(2026, 3, 2)
