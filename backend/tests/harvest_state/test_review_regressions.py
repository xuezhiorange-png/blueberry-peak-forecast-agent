from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.tests.harvest_state.conftest import (
    make_capacity_input,
    make_initial_cohort,
    make_loss_input,
    make_pool,
    make_request,
    make_stable_cohort_key,
    make_task8_source_ref,
    make_task8_supply,
)


def _retarget_to_single_day(payload: dict[str, object], target_date: date) -> None:
    original_start = date(2026, 3, 1)
    payload["forecast_start_date"] = target_date
    payload["forecast_end_date"] = target_date
    payload["as_of_date"] = target_date
    payload["daily_capacity_inputs"] = [
        item for item in payload["daily_capacity_inputs"] if item["capacity_date"] == original_start
    ]
    payload["daily_weather_features"] = [
        item
        for item in payload["daily_weather_features"]
        if item["capacity_date"] == original_start
    ]
    payload["task8_daily_predictions"] = [
        item
        for item in payload["task8_daily_predictions"]
        if item["prediction_date"] == original_start
    ]
    payload["mature_inventory_loss_inputs"] = [
        item
        for item in payload["mature_inventory_loss_inputs"]
        if item["state_date"] == original_start
    ]
    for item in payload["daily_capacity_inputs"]:
        item["capacity_date"] = target_date
    for item in payload["daily_weather_features"]:
        item["capacity_date"] = target_date
    for item in payload["task8_daily_predictions"]:
        item["prediction_date"] = target_date
        item["source_ref"]["prediction_date"] = target_date
        item["source_ref"]["maturity_forecast_prediction_start_date"] = target_date
        item["source_ref"]["maturity_forecast_prediction_end_date"] = target_date
        item["source_ref"]["maturity_forecast_as_of_date"] = target_date
    for item in payload["mature_inventory_loss_inputs"]:
        item["state_date"] = target_date


def test_arrival_lag_one_moves_arrival_to_destination_date() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["harvest_to_arrival_lag_days"] = 1

    result = run_harvest_state_model(payload)

    assert result.status == "completed"
    day1_pool = next(
        row
        for row in result.daily_pool_state_rows
        if row.state_date == date(2026, 3, 1) and row.forecast_quantile == "P50"
    )
    day2_pool = next(
        row
        for row in result.daily_pool_state_rows
        if row.state_date == date(2026, 3, 2) and row.forecast_quantile == "P50"
    )
    assert day1_pool.arrival_quantity_kg == Decimal("0")
    assert day2_pool.arrival_quantity_kg > Decimal("0")


def test_arrival_outside_window_goes_to_schedule_not_harvest_day() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = {
        **make_request(),
        "forecast_start_date": date(2026, 3, 1),
        "forecast_end_date": date(2026, 3, 1),
    }
    payload["harvest_bucket_anchor_local_time"] = "00:30:00"
    payload["destination_factory_timezone"] = "America/Los_Angeles"
    payload["harvest_to_arrival_lag_days"] = 0

    result = run_harvest_state_model(payload)

    assert result.status == "completed"
    day1_member = next(
        row
        for row in result.daily_member_state_rows
        if row.state_date == date(2026, 3, 1)
        and row.variety_id == 101
        and row.forecast_quantile == "P50"
    )
    assert day1_member.arrival_quantity_kg == Decimal("0")
    assert result.future_arrival_schedule
    assert any(
        item.arrival_local_date < date(2026, 3, 1)
        for item in result.future_arrival_schedule
    )


def test_missing_task8_row_blocks_instead_of_silent_zero() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["task8_daily_predictions"] = [
        item
        for item in payload["task8_daily_predictions"]
        if not (
            item["prediction_date"] == date(2026, 3, 2)
            and item["variety_id"] == 102
            and item["source_ref"]["forecast_quantile"] == "P50"
        )
    ]

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


def test_explicit_zero_task8_row_is_valid_zero() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    for item in payload["task8_daily_predictions"]:
        if (
            item["prediction_date"] == date(2026, 3, 2)
            and item["variety_id"] == 102
            and item["source_ref"]["forecast_quantile"] == "P50"
        ):
            item["source_ref"]["source_quantity_kg"] = Decimal("0")
            item["source_ref"]["p50_kg"] = Decimal("0")

    result = run_harvest_state_model(payload)

    assert result.status == "completed"
    member = next(
        row
        for row in result.daily_member_state_rows
        if row.state_date == date(2026, 3, 2)
        and row.variety_id == 102
        and row.forecast_quantile == "P50"
    )
    assert member.natural_maturity_supply_kg == Decimal("0")


def test_duplicate_task8_row_blocks() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["task8_daily_predictions"].append(payload["task8_daily_predictions"][0])

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


def test_task8_quantile_value_mismatch_blocks() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["task8_daily_predictions"][0]["source_ref"]["source_quantity_kg"] = Decimal("999")

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


def test_task8_forecast_not_completed_blocks() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["task8_daily_predictions"][0]["source_ref"]["forecast_run_status"] = "failed"

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


def test_caller_initial_stable_key_mismatch_blocks() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["initial_inventory_cohorts"][0]["stable_cohort_key"] = "bad-key"

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


def test_duplicate_stable_cohort_key_blocks() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    duplicate_key = payload["initial_inventory_cohorts"][0]["stable_cohort_key"]
    payload["initial_inventory_cohorts"][1]["stable_cohort_key"] = duplicate_key

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


def test_sub_milligram_quantity_is_not_lost_before_output_quantization() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["forecast_end_date"] = date(2026, 3, 2)
    payload["task8_daily_predictions"] = [
        make_task8_supply(
            prediction_date=date(2026, 3, 1),
            quantile="P50",
            quantity=Decimal("0.0004"),
            variety_id=101,
        ),
        make_task8_supply(
            prediction_date=date(2026, 3, 2),
            quantile="P50",
            quantity=Decimal("0.0004"),
            variety_id=101,
        ),
        make_task8_supply(
            prediction_date=date(2026, 3, 1),
            quantile="P80",
            quantity=Decimal("0"),
            variety_id=101,
        ),
        make_task8_supply(
            prediction_date=date(2026, 3, 2),
            quantile="P80",
            quantity=Decimal("0"),
            variety_id=101,
        ),
        make_task8_supply(
            prediction_date=date(2026, 3, 1),
            quantile="P90",
            quantity=Decimal("0"),
            variety_id=101,
        ),
        make_task8_supply(
            prediction_date=date(2026, 3, 2),
            quantile="P90",
            quantity=Decimal("0"),
            variety_id=101,
        ),
    ]
    payload["capacity_pools"] = [
        make_pool(
            grain="SUBFARM_VARIETY",
            members=[{"farm_id": 1, "subfarm_id": 11, "variety_id": 101}],
        )
    ]
    payload["initial_inventory_cohorts"] = []
    payload["initial_opening_mature_inventory_kg"] = Decimal("0")
    payload["daily_capacity_inputs"] = [
        make_capacity_input(
            capacity_date=date(2026, 3, 1),
            pool_id="pool-a",
            planned_picker_count=Decimal("0"),
            productivity=Decimal("0"),
        ),
        make_capacity_input(
            capacity_date=date(2026, 3, 2),
            pool_id="pool-a",
            planned_picker_count=Decimal("0"),
            productivity=Decimal("0"),
        ),
    ]
    payload["mature_inventory_loss_inputs"] = [
        make_loss_input(
            state_date=date(2026, 3, 1),
            pool_id="pool-a",
            quantile="P50",
            quantity=Decimal("0"),
        ),
        make_loss_input(
            state_date=date(2026, 3, 2),
            pool_id="pool-a",
            quantile="P50",
            quantity=Decimal("0"),
        ),
        make_loss_input(
            state_date=date(2026, 3, 1),
            pool_id="pool-a",
            quantile="P80",
            quantity=Decimal("0"),
        ),
        make_loss_input(
            state_date=date(2026, 3, 2),
            pool_id="pool-a",
            quantile="P80",
            quantity=Decimal("0"),
        ),
        make_loss_input(
            state_date=date(2026, 3, 1),
            pool_id="pool-a",
            quantile="P90",
            quantity=Decimal("0"),
        ),
        make_loss_input(
            state_date=date(2026, 3, 2),
            pool_id="pool-a",
            quantile="P90",
            quantity=Decimal("0"),
        ),
    ]

    result = run_harvest_state_model(payload)

    assert result.status == "completed"
    day2 = next(
        row
        for row in result.daily_member_state_rows
        if row.state_date == date(2026, 3, 2)
        and row.variety_id == 101
        and row.forecast_quantile == "P50"
    )
    assert day2.closing_mature_inventory_kg == Decimal("0.001")


def test_duplicate_weather_input_blocks() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["daily_weather_features"].append(payload["daily_weather_features"][0])

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


def test_dst_nonexistent_local_time_returns_blocked_output() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    _retarget_to_single_day(payload, date(2026, 3, 8))
    payload["farm_timezone"] = "America/Los_Angeles"
    payload["harvest_bucket_anchor_local_time"] = "02:30:00"

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"
    assert any("DST_NONEXISTENT_LOCAL_TIME" in item for item in result.blockers)


def test_dst_ambiguous_local_time_returns_blocked_output() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    _retarget_to_single_day(payload, date(2026, 11, 1))
    payload["farm_timezone"] = "America/Los_Angeles"
    payload["harvest_bucket_anchor_local_time"] = "01:30:00"

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"
    assert any("DST_AMBIGUOUS_LOCAL_TIME" in item for item in result.blockers)


def test_raw_payload_validation_returns_blocked_output() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["harvest_to_arrival_lag_days"] = -1

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"
    assert result.daily_pool_state_rows == []


def test_native_float_payload_returns_blocked_output() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["daily_capacity_inputs"][0]["kg_per_person_per_day"] = 20.5

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"
    assert any("NATIVE_FLOAT_INPUT" in item for item in result.blockers)


def test_blocked_result_hash_is_order_invariant() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload_a = make_request()
    payload_b = make_request()
    payload_a["harvest_to_arrival_lag_days"] = -1
    payload_b["harvest_to_arrival_lag_days"] = -1
    payload_b["task8_daily_predictions"] = list(reversed(payload_b["task8_daily_predictions"]))

    result_a = run_harvest_state_model(payload_a)
    result_b = run_harvest_state_model(payload_b)

    assert result_a.status == "blocked"
    assert result_b.status == "blocked"
    assert result_a.result_hash == result_b.result_hash


def test_fixed_golden_payload_single_member_single_day() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    source_ref = make_task8_source_ref(
        prediction_date=date(2026, 3, 1),
        forecast_quantile="P50",
        source_quantity_kg=Decimal("10"),
    )
    source_ref["p50_kg"] = Decimal("10")
    source_ref["p80_kg"] = Decimal("0")
    source_ref["p90_kg"] = Decimal("0")
    payload = {
        **make_request(),
        "forecast_start_date": date(2026, 3, 1),
        "forecast_end_date": date(2026, 3, 1),
        "capacity_pools": [
            make_pool(
                grain="SUBFARM_VARIETY",
                members=[{"farm_id": 1, "subfarm_id": 11, "variety_id": 101}],
            )
        ],
        "task8_daily_predictions": [
            {
                "prediction_date": date(2026, 3, 1),
                "farm_id": 1,
                "subfarm_id": 11,
                "variety_id": 101,
                "source_ref": source_ref,
            },
            {
                "prediction_date": date(2026, 3, 1),
                "farm_id": 1,
                "subfarm_id": 11,
                "variety_id": 101,
                "source_ref": {
                    **make_task8_source_ref(
                        prediction_date=date(2026, 3, 1),
                        forecast_quantile="P80",
                        source_quantity_kg=Decimal("0"),
                    ),
                    "p50_kg": Decimal("10"),
                    "p80_kg": Decimal("0"),
                    "p90_kg": Decimal("0"),
                },
            },
            {
                "prediction_date": date(2026, 3, 1),
                "farm_id": 1,
                "subfarm_id": 11,
                "variety_id": 101,
                "source_ref": {
                    **make_task8_source_ref(
                        prediction_date=date(2026, 3, 1),
                        forecast_quantile="P90",
                        source_quantity_kg=Decimal("0"),
                    ),
                    "p50_kg": Decimal("10"),
                    "p80_kg": Decimal("0"),
                    "p90_kg": Decimal("0"),
                },
            },
        ],
        "initial_inventory_cohorts": [],
        "initial_opening_mature_inventory_kg": Decimal("0"),
        "daily_capacity_inputs": [
            make_capacity_input(
                capacity_date=date(2026, 3, 1),
                mode="DIRECT_CAPACITY",
                planned_picker_count=None,
                productivity=None,
                direct_capacity=Decimal("7"),
            )
        ],
        "mature_inventory_loss_inputs": [
            make_loss_input(
                state_date=date(2026, 3, 1),
                pool_id="pool-a",
                quantile="P50",
                quantity=Decimal("1"),
            ),
            make_loss_input(
                state_date=date(2026, 3, 1),
                pool_id="pool-a",
                quantile="P80",
                quantity=Decimal("0"),
            ),
            make_loss_input(
                state_date=date(2026, 3, 1),
                pool_id="pool-a",
                quantile="P90",
                quantity=Decimal("0"),
            ),
        ],
    }
    payload["initial_inventory_cohorts"] = [
        make_initial_cohort(
            quantile="P50",
            quantity=Decimal("2"),
            variety_id=101,
            capacity_pool_membership_hash=make_stable_cohort_key(
                {
                    "capacity_pool_grain": "SUBFARM_VARIETY",
                    "members": [{"farm_id": 1, "subfarm_id": 11, "variety_id": 101}],
                }
            ),
        )
    ]
    payload["initial_opening_mature_inventory_kg"] = Decimal("2")

    result = run_harvest_state_model(payload)

    assert result.status == "completed"
    pool_row = result.daily_pool_state_rows[0]
    member_row = result.daily_member_state_rows[0]
    assert pool_row.opening_mature_inventory_kg == Decimal("2.000")
    assert pool_row.natural_maturity_supply_kg == Decimal("10.000")
    assert pool_row.mature_inventory_loss_quantity_kg == Decimal("1.000")
    assert pool_row.harvested_quantity_kg == Decimal("7.000")
    assert pool_row.closing_mature_inventory_kg == Decimal("4.000")
    assert member_row.harvested_quantity_kg == Decimal("7.000")
    p50_rows = [
        row for row in result.cohort_transition_rows if row.forecast_quantile == "P50"
    ]
    assert len(p50_rows) == 2
