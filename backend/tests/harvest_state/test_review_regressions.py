from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum

import pytest

from backend.tests.harvest_state.conftest import (
    make_capacity_input,
    make_initial_cohort,
    make_loss_input,
    make_pool,
    make_request,
    make_stable_cohort_key,
    make_task8_source_ref,
    make_task8_supply,
    make_task8_verification_snapshot,
    sha256_hex,
)


class _RawAuditEnum(Enum):
    P50 = "P50"


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
        item["source_ref"]["maturity_forecast_as_of_date"] = target_date
        item["verification_snapshot"]["prediction_date"] = target_date
        item["verification_snapshot"]["maturity_forecast_prediction_start_date"] = target_date
        item["verification_snapshot"]["maturity_forecast_prediction_end_date"] = target_date
        item["verification_snapshot"]["maturity_forecast_as_of_date"] = target_date
    for item in payload["mature_inventory_loss_inputs"]:
        item["state_date"] = target_date


def _synchronize_task8_verification_snapshot(
    payload: dict[str, object],
    *,
    prediction_date: date,
    farm_id: int = 1,
    subfarm_id: int | None = 11,
    variety_id: int,
    p50_kg: Decimal,
    p80_kg: Decimal,
    p90_kg: Decimal,
) -> None:
    for item in payload["task8_daily_predictions"]:
        if (
            item["prediction_date"] == prediction_date
            and item["farm_id"] == farm_id
            and item["subfarm_id"] == subfarm_id
            and item["variety_id"] == variety_id
        ):
            item["verification_snapshot"]["p50_kg"] = p50_kg
            item["verification_snapshot"]["p80_kg"] = p80_kg
            item["verification_snapshot"]["p90_kg"] = p90_kg


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


def test_verification_snapshot_is_preserved_in_input_snapshot() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    result = run_harvest_state_model(make_request())

    assert result.status == "completed"
    first = result.input_snapshot["task8_daily_predictions"][0]
    assert first["verification_snapshot"]["maturity_model_version"] == "task8-v1"
    assert len(first["verification_snapshot_hash"]) == 64


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
        item.arrival_local_date < date(2026, 3, 1) for item in result.future_arrival_schedule
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
    _synchronize_task8_verification_snapshot(
        payload,
        prediction_date=date(2026, 3, 2),
        variety_id=102,
        p50_kg=Decimal("0"),
        p80_kg=Decimal("24"),
        p90_kg=Decimal("28"),
    )
    for item in payload["task8_daily_predictions"]:
        if (
            item["prediction_date"] == date(2026, 3, 2)
            and item["variety_id"] == 102
            and item["source_ref"]["forecast_quantile"] == "P50"
        ):
            item["source_ref"]["source_quantity_kg"] = Decimal("0")
            item["verification_snapshot"]["p50_kg"] = Decimal("0")

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
    payload["task8_daily_predictions"][0]["verification_snapshot"][
        "maturity_forecast_run_status"
    ] = "failed"

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
    for prediction_date in (date(2026, 3, 1), date(2026, 3, 2)):
        _synchronize_task8_verification_snapshot(
            payload,
            prediction_date=prediction_date,
            variety_id=101,
            p50_kg=Decimal("0.0004"),
            p80_kg=Decimal("0"),
            p90_kg=Decimal("0"),
        )
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
    assert result.mass_balance_result["internal_passed"] is True
    day2 = next(
        row
        for row in result.daily_member_state_rows
        if row.state_date == date(2026, 3, 2)
        and row.variety_id == 101
        and row.forecast_quantile == "P50"
    )
    assert day2.available_mature_quantity_kg == Decimal("0.001")
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
    assert "INVALID_ARRIVAL_LAG" in result.blockers


def test_native_float_payload_returns_blocked_output() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["daily_capacity_inputs"][0]["kg_per_person_per_day"] = 20.5

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"
    assert any("NATIVE_FLOAT_INPUT" in item for item in result.blockers)


def test_invalid_farm_timezone_returns_blocked_output() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["farm_timezone"] = "Bad/Timezone"

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"
    assert "INVALID_TIMEZONE" in result.blockers
    assert result.daily_pool_state_rows == []
    assert result.daily_member_state_rows == []
    assert result.cohort_transition_rows == []
    assert result.future_arrival_schedule == []


def test_invalid_destination_timezone_returns_blocked_output() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["destination_factory_timezone"] = "Bad/Timezone"

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"
    assert "INVALID_TIMEZONE" in result.blockers


@pytest.mark.parametrize(
    ("field_name", "timezone_value"),
    [
        ("farm_timezone", "Bad/Timezone"),
        ("destination_factory_timezone", "Bad/Timezone"),
        ("farm_timezone", ""),
        ("destination_factory_timezone", ""),
        ("farm_timezone", "/etc/passwd"),
        ("destination_factory_timezone", "/etc/passwd"),
        ("farm_timezone", "../UTC"),
        ("destination_factory_timezone", "../UTC"),
        ("farm_timezone", "UTC\0x"),
        ("destination_factory_timezone", "UTC\0x"),
    ],
)
def test_invalid_timezone_key_returns_blocked_output(
    field_name: str,
    timezone_value: str,
) -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload[field_name] = timezone_value

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"
    assert "INVALID_TIMEZONE" in result.blockers
    assert result.daily_pool_state_rows == []
    assert result.daily_member_state_rows == []
    assert result.cohort_transition_rows == []
    assert result.future_arrival_schedule == []


@pytest.mark.parametrize("timezone_value", ["", "/etc/passwd", "../UTC", "UTC\0x"])
def test_invalid_timezone_value_error_does_not_escape(timezone_value: str) -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["farm_timezone"] = timezone_value

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"
    assert "INVALID_TIMEZONE" in result.blockers


def test_invalid_timezone_result_hash_is_deterministic() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload_a = make_request()
    payload_b = make_request()
    payload_a["farm_timezone"] = "Bad/Timezone"
    payload_b["farm_timezone"] = "Bad/Timezone"

    result_a = run_harvest_state_model(payload_a)
    result_b = run_harvest_state_model(payload_b)

    assert result_a.status == "blocked"
    assert result_b.status == "blocked"
    assert result_a.result_hash == result_b.result_hash


@pytest.mark.parametrize("timezone_value", ["", "/etc/passwd", "../UTC", "UTC\0x"])
def test_invalid_timezone_variants_have_deterministic_hash(timezone_value: str) -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload_a = make_request()
    payload_b = make_request()
    payload_a["destination_factory_timezone"] = timezone_value
    payload_b["destination_factory_timezone"] = timezone_value

    result_a = run_harvest_state_model(payload_a)
    result_b = run_harvest_state_model(payload_b)

    assert result_a.status == "blocked"
    assert result_b.status == "blocked"
    assert result_a.result_hash == result_b.result_hash


def test_task8_future_as_of_date_blocks() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["task8_daily_predictions"][0]["verification_snapshot"][
        "maturity_forecast_as_of_date"
    ] = date(2026, 3, 1)

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


def test_task8_signature_mismatch_blocks() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["task8_daily_predictions"][0]["verification_snapshot"][
        "maturity_model_source_signature"
    ] = "other-model-sig"

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


def test_task8_model_version_mismatch_blocks() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    for item in payload["task8_daily_predictions"]:
        item["source_ref"]["maturity_model_version"] = "task8-v2"
        item["verification_snapshot"]["maturity_model_version"] = "task8-v2"
        break

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


def test_task8_model_config_hash_mismatch_blocks() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    for item in payload["task8_daily_predictions"]:
        item["source_ref"]["maturity_model_config_hash"] = "cfg-v2"
        item["verification_snapshot"]["maturity_model_config_hash"] = "cfg-v2"
        break

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


def test_task8_model_source_signature_mismatch_blocks() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    for item in payload["task8_daily_predictions"]:
        item["source_ref"]["maturity_model_source_signature"] = "model-sig-v2"
        item["verification_snapshot"]["maturity_model_source_signature"] = "model-sig-v2"
        break

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


def test_task8_artifact_id_mismatch_blocks() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    for item in payload["task8_daily_predictions"]:
        item["source_ref"]["maturity_model_artifact_id"] = 999
        item["verification_snapshot"]["maturity_model_artifact_id"] = 999
        item["verification_snapshot"]["maturity_forecast_artifact_id"] = 999
        break

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


def test_task8_artifact_hash_mismatch_blocks() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["task8_daily_predictions"][0]["verification_snapshot"][
        "maturity_model_artifact_hash"
    ] = "other-artifact-hash"

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


def test_mixed_task8_forecast_runs_block() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["task8_daily_predictions"][0]["source_ref"]["maturity_forecast_run_id"] = 999
    payload["task8_daily_predictions"][0]["source_ref"]["maturity_forecast_source_signature"] = (
        "forecast-sig-999"
    )
    payload["task8_daily_predictions"][0]["verification_snapshot"]["maturity_forecast_run_id"] = 999
    payload["task8_daily_predictions"][0]["verification_snapshot"][
        "maturity_forecast_source_signature"
    ] = "forecast-sig-999"
    payload["task8_daily_predictions"][0]["verification_snapshot"][
        "maturity_daily_prediction_forecast_run_id"
    ] = 999

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


def test_same_prediction_id_different_variety_blocks() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    shared_id = payload["task8_daily_predictions"][0]["source_ref"]["maturity_daily_prediction_id"]
    payload["task8_daily_predictions"][1]["source_ref"]["maturity_daily_prediction_id"] = shared_id
    payload["task8_daily_predictions"][1]["verification_snapshot"][
        "maturity_daily_prediction_id"
    ] = shared_id

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


def test_same_prediction_id_different_snapshot_blocks() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    shared_id = payload["task8_daily_predictions"][0]["source_ref"]["maturity_daily_prediction_id"]
    payload["task8_daily_predictions"][3]["source_ref"]["maturity_daily_prediction_id"] = shared_id
    payload["task8_daily_predictions"][3]["verification_snapshot"][
        "maturity_daily_prediction_id"
    ] = shared_id
    payload["task8_daily_predictions"][3]["verification_snapshot"]["p50_kg"] = Decimal("999")

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


def test_three_quantiles_share_identical_verification_identity() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    result = run_harvest_state_model(make_request())

    assert result.status == "completed"


def test_continuity_failure_after_day_one_blocks() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["forecast_end_date"] = date(2026, 3, 2)
    payload["daily_capacity_inputs"] = payload["daily_capacity_inputs"][:2]
    payload["daily_weather_features"] = payload["daily_weather_features"][:6]
    payload["mature_inventory_loss_inputs"] = payload["mature_inventory_loss_inputs"][:6]
    payload["task8_daily_predictions"] = [
        item
        for item in payload["task8_daily_predictions"]
        if item["prediction_date"] <= date(2026, 3, 2)
    ]
    payload["initial_inventory_cohorts"][0]["remaining_quantity_kg"] = Decimal("5.500")
    payload["initial_opening_mature_inventory_kg"] = Decimal("30.500")
    payload["daily_capacity_inputs"][0]["planned_picker_count"] = Decimal("0")
    payload["daily_capacity_inputs"][0]["kg_per_person_per_day"] = Decimal("0")
    payload["daily_capacity_inputs"][1]["planned_picker_count"] = Decimal("0")
    payload["daily_capacity_inputs"][1]["kg_per_person_per_day"] = Decimal("0")

    result_ok = run_harvest_state_model(payload)
    assert result_ok.status == "completed"
    original_key = result_ok.cohort_transition_rows[0].stable_cohort_key

    payload_bad = make_request()
    payload_bad["forecast_end_date"] = date(2026, 3, 2)
    payload_bad["daily_capacity_inputs"] = payload_bad["daily_capacity_inputs"][:2]
    payload_bad["daily_weather_features"] = payload_bad["daily_weather_features"][:6]
    payload_bad["mature_inventory_loss_inputs"] = payload_bad["mature_inventory_loss_inputs"][:6]
    payload_bad["task8_daily_predictions"] = [
        item
        for item in payload_bad["task8_daily_predictions"]
        if item["prediction_date"] <= date(2026, 3, 2)
    ]
    payload_bad["initial_inventory_cohorts"][0]["remaining_quantity_kg"] = Decimal("5.500")
    payload_bad["initial_opening_mature_inventory_kg"] = Decimal("30.500")
    payload_bad["daily_capacity_inputs"][0]["planned_picker_count"] = Decimal("0")
    payload_bad["daily_capacity_inputs"][0]["kg_per_person_per_day"] = Decimal("0")
    payload_bad["daily_capacity_inputs"][1]["planned_picker_count"] = Decimal("0")
    payload_bad["daily_capacity_inputs"][1]["kg_per_person_per_day"] = Decimal("0")
    payload_bad["initial_inventory_cohorts"][0]["stable_cohort_key"] = sha256_hex(
        {"different": original_key}
    )

    result = run_harvest_state_model(payload_bad)

    assert result.status == "blocked"


def test_initial_inventory_aggregate_requires_exact_decimal_equality() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["initial_inventory_cohorts"] = []
    payload["initial_opening_mature_inventory_kg"] = Decimal("0.0004")

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"
    assert any("INITIAL_INVENTORY_SUM_MISMATCH" in item for item in result.blockers)


def test_empty_initial_inventory_with_exact_zero_is_valid() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["initial_inventory_cohorts"] = []
    payload["initial_opening_mature_inventory_kg"] = Decimal("0")

    result = run_harvest_state_model(payload)

    assert result.status == "completed"


def test_sub_milligram_capacity_harvests_before_output_quantization() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["forecast_start_date"] = date(2026, 3, 1)
    payload["forecast_end_date"] = date(2026, 3, 1)
    payload["daily_capacity_inputs"] = [
        make_capacity_input(
            capacity_date=date(2026, 3, 1),
            mode="DIRECT_CAPACITY",
            planned_picker_count=None,
            productivity=None,
            direct_capacity=Decimal("0.0004"),
        )
    ]
    payload["task8_daily_predictions"] = [
        make_task8_supply(
            prediction_date=date(2026, 3, 1),
            quantile="P50",
            quantity=Decimal("0.0010"),
            variety_id=101,
        ),
        make_task8_supply(
            prediction_date=date(2026, 3, 1),
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
    ]
    _synchronize_task8_verification_snapshot(
        payload,
        prediction_date=date(2026, 3, 1),
        variety_id=101,
        p50_kg=Decimal("0.0010"),
        p80_kg=Decimal("0"),
        p90_kg=Decimal("0"),
    )
    payload["capacity_pools"] = [
        make_pool(
            grain="SUBFARM_VARIETY",
            members=[{"farm_id": 1, "subfarm_id": 11, "variety_id": 101}],
        )
    ]
    payload["daily_weather_features"] = payload["daily_weather_features"][:3]
    payload["mature_inventory_loss_inputs"] = [
        make_loss_input(
            state_date=date(2026, 3, 1),
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
            state_date=date(2026, 3, 1),
            pool_id="pool-a",
            quantile="P90",
            quantity=Decimal("0"),
        ),
    ]
    payload["initial_inventory_cohorts"] = []
    payload["initial_opening_mature_inventory_kg"] = Decimal("0")

    result = run_harvest_state_model(payload)

    assert result.status == "completed"
    p50_row = next(row for row in result.cohort_transition_rows if row.forecast_quantile == "P50")
    assert p50_row.harvested_quantity_kg == Decimal("0.000")
    assert p50_row.closing_quantity_kg == Decimal("0.001")


def test_weather_ratio_is_not_quantized_before_capacity_calculation() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["weather_rule_config"]["feature_rules"][0]["bands"][0]["multiplier"] = Decimal(
        "0.1234567"
    )
    payload["weather_rule_config"]["feature_rules"][1]["bands"][0]["multiplier"] = Decimal("1")
    payload["weather_rule_config"]["feature_rules"][2]["bands"][1]["multiplier"] = Decimal("1")
    payload["daily_capacity_inputs"] = [
        make_capacity_input(
            capacity_date=date(2026, 3, 1),
            mode="DIRECT_CAPACITY",
            planned_picker_count=None,
            productivity=None,
            direct_capacity=Decimal("1000000"),
        )
    ]
    payload["forecast_start_date"] = date(2026, 3, 1)
    payload["forecast_end_date"] = date(2026, 3, 1)
    payload["daily_weather_features"] = payload["daily_weather_features"][:3]
    payload["task8_daily_predictions"] = payload["task8_daily_predictions"][:6]
    payload["mature_inventory_loss_inputs"] = payload["mature_inventory_loss_inputs"][:3]

    result = run_harvest_state_model(payload)

    assert result.status == "completed"
    assert (
        result.resolved_parameter_snapshot.daily_pool_parameters[0].weather_harvest_efficiency_ratio
        == Decimal("0.123457")
    )


def test_resolved_parameter_snapshot_quantizes_ratio_only_on_output() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["weather_rule_config"]["feature_rules"][0]["bands"][0]["multiplier"] = Decimal(
        "0.1234567"
    )
    payload["weather_rule_config"]["feature_rules"][1]["bands"][0]["multiplier"] = Decimal("1")
    payload["weather_rule_config"]["feature_rules"][2]["bands"][1]["multiplier"] = Decimal("1")

    result = run_harvest_state_model(payload)

    assert result.status == "completed"
    assert (
        result.resolved_parameter_snapshot.daily_pool_parameters[0].weather_harvest_efficiency_ratio
        == Decimal("0.123457")
    )


def test_verification_snapshot_change_changes_result_hash() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload_a = make_request()
    payload_b = make_request()
    for item in payload_b["task8_daily_predictions"]:
        item["verification_snapshot"]["maturity_forecast_prediction_end_date"] = date(
            2026, 3, 31
        )

    result_a = run_harvest_state_model(payload_a)
    result_b = run_harvest_state_model(payload_b)

    assert result_a.status == "completed"
    assert result_b.status == "completed"
    assert result_a.input_snapshot != result_b.input_snapshot
    assert result_a.result_hash != result_b.result_hash


def test_unselected_quantile_value_change_changes_result_hash() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload_a = make_request()
    payload_b = make_request()
    _synchronize_task8_verification_snapshot(
        payload_b,
        prediction_date=date(2026, 3, 1),
        variety_id=101,
        p50_kg=Decimal("20"),
        p80_kg=Decimal("999"),
        p90_kg=Decimal("28"),
    )
    for item in payload_b["task8_daily_predictions"]:
        if (
            item["prediction_date"] == date(2026, 3, 1)
            and item["variety_id"] == 101
            and item["source_ref"]["forecast_quantile"] == "P80"
        ):
            item["source_ref"]["source_quantity_kg"] = Decimal("999")

    result_a = run_harvest_state_model(payload_a)
    result_b = run_harvest_state_model(payload_b)

    assert result_a.status == "completed"
    assert result_b.status == "completed"
    assert result_a.result_hash != result_b.result_hash


def test_task8_input_order_does_not_change_result_hash() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload_a = make_request()
    payload_b = make_request()
    payload_b["task8_daily_predictions"] = list(reversed(payload_b["task8_daily_predictions"]))

    result_a = run_harvest_state_model(payload_a)
    result_b = run_harvest_state_model(payload_b)

    assert result_a.status == "completed"
    assert result_b.status == "completed"
    assert result_a.result_hash == result_b.result_hash


def test_run_parameter_source_conflict_blocks() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["run_parameter_source_refs"].append(
        {
            **payload["run_parameter_source_refs"][0],
            "source_record_key": "holiday-calendar-v2",
            "source_row_hash": sha256_hex({"source": "holiday-calendar-v2"}),
        }
    )

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


def test_holiday_calendar_hash_mismatch_blocks() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["holiday_calendar_hash"] = sha256_hex({"bad": "hash"})

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"


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
    verification_snapshot = make_task8_verification_snapshot(
        prediction_date=date(2026, 3, 1),
        forecast_quantile="P50",
        source_quantity_kg=Decimal("10"),
        variety_id=101,
    )
    verification_snapshot["p50_kg"] = Decimal("10")
    verification_snapshot["p80_kg"] = Decimal("0")
    verification_snapshot["p90_kg"] = Decimal("0")
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
                "verification_snapshot": verification_snapshot,
            },
            {
                "prediction_date": date(2026, 3, 1),
                "farm_id": 1,
                "subfarm_id": 11,
                "variety_id": 101,
                "source_ref": make_task8_source_ref(
                    prediction_date=date(2026, 3, 1),
                    forecast_quantile="P80",
                    source_quantity_kg=Decimal("0"),
                ),
                "verification_snapshot": {
                    **make_task8_verification_snapshot(
                        prediction_date=date(2026, 3, 1),
                        forecast_quantile="P80",
                        source_quantity_kg=Decimal("0"),
                        variety_id=101,
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
                "source_ref": make_task8_source_ref(
                    prediction_date=date(2026, 3, 1),
                    forecast_quantile="P90",
                    source_quantity_kg=Decimal("0"),
                ),
                "verification_snapshot": {
                    **make_task8_verification_snapshot(
                        prediction_date=date(2026, 3, 1),
                        forecast_quantile="P90",
                        source_quantity_kg=Decimal("0"),
                        variety_id=101,
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
    p50_rows = [row for row in result.cohort_transition_rows if row.forecast_quantile == "P50"]
    assert len(p50_rows) == 2


def test_malformed_members_container_returns_blocked() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["capacity_pools"][0]["members"] = 42

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"
    assert result.daily_pool_state_rows == []


def test_malformed_capacity_pools_array_item_returns_blocked() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["capacity_pools"] = [42]

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"
    assert result.daily_pool_state_rows == []


def test_malformed_source_ref_returns_blocked() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["task8_daily_predictions"][0]["source_ref"] = []

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"
    assert result.daily_pool_state_rows == []


def test_raw_time_value_is_preserved_in_blocked_snapshot() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["harvest_bucket_anchor_local_time"] = time(18, 0)
    payload["capacity_pools"][0]["members"] = 42

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"
    assert result.input_snapshot["harvest_bucket_anchor_local_time"] == "18:00:00"


def test_different_raw_time_values_change_blocked_result_hash() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload_a = make_request()
    payload_b = make_request()
    payload_a["harvest_bucket_anchor_local_time"] = time(18, 0)
    payload_b["harvest_bucket_anchor_local_time"] = time(19, 0)
    payload_a["capacity_pools"][0]["members"] = 42
    payload_b["capacity_pools"][0]["members"] = 42

    result_a = run_harvest_state_model(payload_a)
    result_b = run_harvest_state_model(payload_b)

    assert result_a.status == "blocked"
    assert result_b.status == "blocked"
    assert result_a.input_snapshot["harvest_bucket_anchor_local_time"] == "18:00:00"
    assert result_b.input_snapshot["harvest_bucket_anchor_local_time"] == "19:00:00"
    assert result_a.result_hash != result_b.result_hash


def test_raw_datetime_value_is_preserved() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["audit_datetime"] = datetime(2026, 3, 1, 18, 30, 0)
    payload["capacity_pools"] = [42]

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"
    assert result.input_snapshot["audit_datetime"] == "2026-03-01T18:30:00"


def test_raw_enum_value_is_canonicalized() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["audit_quantile"] = _RawAuditEnum.P50
    payload["task8_daily_predictions"][0]["source_ref"] = []

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"
    assert result.input_snapshot["audit_quantile"] == "P50"


def test_malformed_nested_mapping_returns_blocked() -> None:
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["task8_daily_predictions"] = [{"farm_id": {"bad": 1}}]

    result = run_harvest_state_model(payload)

    assert result.status == "blocked"
    assert result.daily_pool_state_rows == []
