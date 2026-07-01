from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.harvest_state.canonical import (
    make_holiday_calendar_hash,
    make_weather_rule_config_hash,
)
from backend.app.harvest_state.enums import CapacityInputMode, ForecastQuantile


def _sha(seed: str) -> str:
    return seed * 64


def _capacity_pool_definition_payload() -> dict[str, object]:
    return {
        "season_id": 1,
        "destination_factory_id": 2,
        "capacity_pool_code": "POOL-A",
        "capacity_pool_grain": "FARM",
        "capacity_input_mode": "LABOR_DERIVED",
        "capacity_pool_version": "v1",
        "revision": 1,
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
        "available_at_local_date": date(2026, 1, 1),
        "consumable_from_local_date": None,
        "consumable_to_local_date": None,
        "status": "draft",
        "status_changed_at": datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        "source_system": "task9_historical_authority",
        "source_record_key": "capacity-pool:1:2:POOL-A:v1:1",
        "source_version": "v1",
        "row_hash": "a" * 64,
    }


def _pool_member_payload() -> dict[str, object]:
    return {
        "farm_id": 10,
        "subfarm_id": None,
        "variety_id": 20,
    }


def _daily_capacity_payload() -> dict[str, object]:
    return {
        "capacity_pool_definition_id": 11,
        "season_id": 1,
        "destination_factory_id": 2,
        "capacity_pool_code": "POOL-A",
        "capacity_pool_version": "v1",
        "capacity_pool_revision": 1,
        "capacity_date": date(2026, 2, 1),
        "daily_capacity_revision": 1,
        "capacity_input_mode": "LABOR_DERIVED",
        "planned_picker_count": "10",
        "kg_per_person_per_day": "20",
        "direct_nominal_capacity_kg_per_day": None,
        "labor_availability_ratio": "0.8",
        "operational_efficiency_ratio": "0.9",
        "available_at_local_date": date(2026, 1, 31),
        "consumable_from_local_date": date(2026, 1, 31),
        "consumable_to_local_date": None,
        "status": "active",
        "status_changed_at": datetime(2026, 1, 31, 8, 0, tzinfo=UTC),
        "superseded_by_id": None,
        "source_system": "task9_historical_authority",
        "source_record_key": "daily-capacity:1:2:POOL-A:v1:1:2026-02-01:1",
        "source_version": "v1",
        "row_hash": "c" * 64,
    }


def _run_parameter_package_payload() -> dict[str, object]:
    return {
        "season_id": 1,
        "destination_factory_id": 2,
        "farm_scope_key": "farm-scope:10",
        "farm_timezone": "Asia/Shanghai",
        "destination_factory_timezone": "Asia/Shanghai",
        "harvest_bucket_anchor_local_time": time(9, 0),
        "harvest_to_arrival_lag_days": 1,
        "holiday_calendar_version_id": 31,
        "weather_rule_config_version_id": 41,
        "package_version": "pkg-v1",
        "revision": 1,
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
        "available_at_local_date": date(2026, 1, 1),
        "consumable_from_local_date": date(2026, 1, 1),
        "consumable_to_local_date": None,
        "status": "active",
        "status_changed_at": datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        "superseded_by_id": None,
        "source_system": "task9_historical_authority",
        "source_record_key": "run-package:1:2:farm-scope:10:pkg-v1:1",
        "source_version": "pkg-v1",
        "row_hash": "d" * 64,
    }


def _holiday_calendar_payload() -> dict[str, object]:
    _dates = [
        {"holiday_date": date(2026, 2, 10), "holiday_code": "CNY", "holiday_name": "A"},
        {"holiday_date": date(2026, 2, 10), "holiday_code": "LOCAL", "holiday_name": "B"},
    ]
    _cal_hash = make_holiday_calendar_hash(
        holiday_calendar_version="calendar-v1", holiday_dates=[date(2026, 2, 10)]
    )
    return {
        "season_id": 1,
        "calendar_code": "CN-SH",
        "calendar_version": "calendar-v1",
        "revision": 1,
        "calendar_hash": _cal_hash,
        "region_scope": "CN-SH",
        "lifecycle_timezone_name": "Asia/Shanghai",
        "available_at_local_date": date(2026, 1, 1),
        "consumable_from_local_date": date(2026, 1, 1),
        "consumable_to_local_date": None,
        "status": "active",
        "status_changed_at": datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        "superseded_by_id": None,
        "source_system": "task9_historical_authority",
        "source_record_key": "holiday-calendar:1:CN-SH:Asia/Shanghai:calendar-v1:1",
        "source_version": "calendar-v1",
        "row_hash": "f" * 64,
        "dates": _dates,
    }


def _weather_rule_payload() -> dict[str, object]:
    _exact_config = {
        "version": "wx-v1",
        "required_feature_ids": ["rain", "temp"],
        "feature_rules": [
            {
                "feature_id": "rain",
                "bands": [
                    {
                        "lower_bound": "0",
                        "lower_inclusive": True,
                        "upper_bound": "10",
                        "upper_inclusive": True,
                        "multiplier": "1",
                    }
                ],
            },
            {
                "feature_id": "temp",
                "bands": [
                    {
                        "lower_bound": "0",
                        "lower_inclusive": True,
                        "upper_bound": "30",
                        "upper_inclusive": True,
                        "multiplier": "0.9",
                    }
                ],
            },
        ],
        "combination_method": "MULTIPLY",
        "minimum_ratio": "0.7",
        "maximum_ratio": "1",
        "missing_feature_policy": "BLOCK",
    }
    _cfg_hash = make_weather_rule_config_hash(_exact_config)
    return {
        "rule_code": "wx-rule",
        "rule_version": "wx-v1",
        "revision": 1,
        "lifecycle_timezone_name": "Asia/Shanghai",
        "combination_method": "MULTIPLY",
        "minimum_ratio": "0.7",
        "maximum_ratio": "1",
        "required_feature_ids": ["rain", "temp"],
        "feature_rules": [
            {
                "feature_id": "rain",
                "bands": [
                    {
                        "lower_bound": "0",
                        "lower_inclusive": True,
                        "upper_bound": "10",
                        "upper_inclusive": True,
                        "multiplier": "1",
                    }
                ],
            },
            {
                "feature_id": "temp",
                "bands": [
                    {
                        "lower_bound": "0",
                        "lower_inclusive": True,
                        "upper_bound": "30",
                        "upper_inclusive": True,
                        "multiplier": "0.9",
                    }
                ],
            },
        ],
        "missing_feature_policy": "BLOCK",
        "config_hash": _cfg_hash,
        "available_at_local_date": date(2026, 1, 1),
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
        "consumable_from_local_date": date(2026, 1, 1),
        "consumable_to_local_date": None,
        "status": "active",
        "status_changed_at": datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        "superseded_by_id": None,
        "source_system": "task9_historical_authority",
        "source_record_key": "weather-rule:wx-rule:Asia/Shanghai:wx-v1:1",
        "source_version": "wx-v1",
        "row_hash": "2" * 64,
    }


def _initial_inventory_payload(total: str = "30") -> dict[str, object]:
    return {
        "season_id": 1,
        "destination_factory_id": 2,
        "opening_state_date": date(2026, 2, 1),
        "snapshot_version": "snap-v1",
        "revision": 1,
        "initial_opening_mature_inventory_kg": total,
        "available_at_local_date": date(2026, 1, 31),
        "consumable_from_local_date": date(2026, 1, 31),
        "consumable_to_local_date": None,
        "status": "active",
        "status_changed_at": datetime(2026, 1, 31, 9, 0, tzinfo=UTC),
        "superseded_by_id": None,
        "source_system": "task9_historical_authority",
        "source_record_key": "initial-inventory:1:2:2026-02-01:snap-v1:1",
        "source_version": "snap-v1",
        "row_hash": "3" * 64,
        "cohorts": [
            {
                "stable_cohort_key": "c1",
                "forecast_quantile": "P50",
                "cohort_date": date(2026, 1, 29),
                "farm_id": 10,
                "subfarm_id": None,
                "variety_id": 20,
                "remaining_quantity_kg": "10",
            },
            {
                "stable_cohort_key": "c2",
                "forecast_quantile": "P80",
                "cohort_date": date(2026, 1, 30),
                "farm_id": 10,
                "subfarm_id": None,
                "variety_id": 20,
                "remaining_quantity_kg": "10",
            },
            {
                "stable_cohort_key": "c3",
                "forecast_quantile": "P90",
                "cohort_date": date(2026, 1, 31),
                "farm_id": 10,
                "subfarm_id": None,
                "variety_id": 20,
                "remaining_quantity_kg": "10",
            },
        ],
    }


def _mature_loss_payload() -> dict[str, object]:
    return {
        "season_id": 1,
        "destination_factory_id": 2,
        "state_date": date(2026, 2, 1),
        "capacity_pool_code": "POOL-A",
        "forecast_quantile": "P50",
        "loss_version": "loss-v1",
        "revision": 1,
        "mature_inventory_loss_quantity_kg": "5",
        "available_at_local_date": date(2026, 1, 31),
        "consumable_from_local_date": date(2026, 1, 31),
        "consumable_to_local_date": None,
        "status": "active",
        "status_changed_at": datetime(2026, 1, 31, 9, 0, tzinfo=UTC),
        "superseded_by_id": None,
        "source_system": "task9_historical_authority",
        "source_record_key": "mature-loss:1:2:POOL-A:2026-02-01:P50:loss-v1:1",
        "source_version": "loss-v1",
        "row_hash": "7" * 64,
    }


def _lifecycle_event_payload() -> dict[str, object]:
    return {
        "authority_family": "daily_capacity",
        "authority_stable_key": "daily-capacity:1:2:POOL-A:v1:1:2026-02-01",
        "authority_business_version": "v1",
        "authority_revision": 1,
        "business_row_hash": "8" * 64,
        "transition_sequence": 1,
        "old_status": None,
        "new_status": "draft",
        "old_consumable_from_local_date": None,
        "old_consumable_to_local_date": None,
        "new_consumable_from_local_date": None,
        "new_consumable_to_local_date": None,
        "superseded_by_authority_stable_key": None,
        "superseded_by_authority_business_version": None,
        "superseded_by_authority_revision": None,
        "transitioned_at": datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        "source_system": "task9_historical_authority",
        "source_record_key": "lifecycle:daily-capacity:1",
        "lifecycle_event_hash": "9" * 64,
    }


def test_authority_schema_rejects_native_float_business_values() -> None:
    from backend.app.harvest_state.authority_schemas import Task9DailyCapacityAuthoritySchema

    payload = _daily_capacity_payload()
    payload["kg_per_person_per_day"] = 20.5
    with pytest.raises(ValidationError):
        Task9DailyCapacityAuthoritySchema.model_validate(payload)


def test_authority_schema_validates_timezone_and_capacity_mode() -> None:
    from backend.app.harvest_state.authority_schemas import (
        Task9AuthorityStatus,
        Task9DailyCapacityAuthoritySchema,
        Task9RunParameterPackageSchema,
    )

    daily = Task9DailyCapacityAuthoritySchema.model_validate(_daily_capacity_payload())
    assert daily.capacity_input_mode is CapacityInputMode.LABOR_DERIVED
    pkg = Task9RunParameterPackageSchema.model_validate(_run_parameter_package_payload())
    assert pkg.status is Task9AuthorityStatus.ACTIVE

    invalid = _run_parameter_package_payload()
    invalid["farm_timezone"] = "Mars/Olympus"
    with pytest.raises(ValidationError):
        Task9RunParameterPackageSchema.model_validate(invalid)


def test_authority_schema_validates_lifecycle_and_replacement_identity() -> None:
    from backend.app.harvest_state.authority_schemas import (
        Task9AuthorityLifecycleEventSchema,
        Task9CapacityPoolDefinitionSchema,
    )

    payload = _capacity_pool_definition_payload()
    Task9CapacityPoolDefinitionSchema.model_validate(payload)

    invalid = _capacity_pool_definition_payload()
    invalid["status"] = "active"
    invalid["consumable_from_local_date"] = None
    with pytest.raises(ValidationError):
        Task9CapacityPoolDefinitionSchema.model_validate(invalid)

    event = _lifecycle_event_payload()
    Task9AuthorityLifecycleEventSchema.model_validate(event)

    invalid_event = _lifecycle_event_payload()
    invalid_event["new_status"] = "superseded"
    with pytest.raises(ValidationError):
        Task9AuthorityLifecycleEventSchema.model_validate(invalid_event)


def test_authority_aggregate_schema_validates_holiday_inventory_and_member_contracts() -> None:
    from backend.app.harvest_state.authority_schemas import (
        Task9CapacityPoolDefinitionBundleSchema,
        Task9HolidayCalendarBundleSchema,
        Task9InitialInventoryBundleSchema,
    )

    pool_bundle = Task9CapacityPoolDefinitionBundleSchema.model_validate(
        {
            **_capacity_pool_definition_payload(),
            "members": [_pool_member_payload()],
        }
    )
    assert len(pool_bundle.members) == 1

    holiday_bundle = Task9HolidayCalendarBundleSchema.model_validate(_holiday_calendar_payload())
    assert holiday_bundle.request_holiday_dates == [date(2026, 2, 10)]

    inventory_bundle = Task9InitialInventoryBundleSchema.model_validate(
        _initial_inventory_payload()
    )
    assert inventory_bundle.initial_opening_mature_inventory_kg == Decimal("30")

    invalid_inventory = _initial_inventory_payload(total="31")
    with pytest.raises(ValidationError):
        Task9InitialInventoryBundleSchema.model_validate(invalid_inventory)


def test_authority_schema_weather_and_loss_validation() -> None:
    from backend.app.harvest_state.authority_schemas import (
        Task9MatureInventoryLossAuthoritySchema,
        Task9WeatherRuleConfigVersionSchema,
    )

    weather = Task9WeatherRuleConfigVersionSchema.model_validate(_weather_rule_payload())
    assert weather.required_feature_ids == ["rain", "temp"]

    invalid_weather = _weather_rule_payload()
    invalid_weather["feature_rules"] = invalid_weather["feature_rules"][:1]
    with pytest.raises(ValidationError):
        Task9WeatherRuleConfigVersionSchema.model_validate(invalid_weather)

    loss = Task9MatureInventoryLossAuthoritySchema.model_validate(_mature_loss_payload())
    assert loss.forecast_quantile is ForecastQuantile.P50
