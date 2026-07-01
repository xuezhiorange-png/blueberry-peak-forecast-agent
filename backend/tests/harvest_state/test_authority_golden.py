from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest
from pydantic import ValidationError

from backend.app.harvest_state.authority_canonical import (
    build_capacity_pool_definition_payload,
    build_capacity_pool_definition_stable_key,
    build_capacity_pool_member_payload,
    build_daily_capacity_payload,
    build_daily_capacity_stable_key,
    build_holiday_calendar_payload,
    build_holiday_calendar_stable_key,
    build_initial_inventory_cohort_payload,
    build_initial_inventory_snapshot_payload,
    build_initial_inventory_stable_key,
    build_lifecycle_event_payload,
    build_mature_inventory_loss_payload,
    build_mature_inventory_loss_stable_key,
    build_run_parameter_package_payload,
    build_run_parameter_package_stable_key,
    build_weather_rule_config_payload,
    build_weather_rule_stable_key,
    canonical_payload_json,
    make_authority_row_hash,
    make_lifecycle_event_hash,
)
from backend.app.harvest_state.authority_schemas import (
    Task9CapacityPoolDefinitionSemanticBundle,
    Task9CapacityPoolMemberSchema,
    Task9DailyCapacitySemanticInput,
    Task9HolidayCalendarBundleSchema,
    Task9HolidayCalendarDateSchema,
    Task9HolidayCalendarSemanticBundle,
    Task9HolidayCalendarSemanticInput,
    Task9InitialInventoryCohortSchema,
    Task9InitialInventorySemanticBundle,
    Task9InitialInventorySemanticInput,
    Task9LifecycleEventSemanticInput,
    Task9MatureLossSemanticInput,
    Task9RunParameterPackageBundleSchema,
    Task9RunParameterPackageSchema,
    Task9RunParameterPackageSemanticInput,
    Task9WeatherRuleConfigVersionSchema,
    Task9WeatherRuleSemanticInput,
)
from backend.app.harvest_state.canonical import (
    make_holiday_calendar_hash,
    make_weather_rule_config_hash,
)
from backend.app.harvest_state.schemas import WeatherFeatureBand, WeatherFeatureRule

_EXPECTED_POOL_JSON = (
    '{"available_at_local_date":"2026-01-01","capacity_input_mode":"LABOR_DERIVED",'
    '"capacity_pool_code":"POOL-A","capacity_pool_grain":"FARM","capacity_pool_version":"v1",'
    '"destination_factory_id":2,"effective_from":"2026-01-01","effective_to":null,'
    '"members":[{"farm_id":10,"parent_pool_identity":{"available_at_local_date":"2026-01-01",'
    '"capacity_input_mode":"LABOR_DERIVED","capacity_pool_code":"POOL-A",'
    '"capacity_pool_grain":"FARM","capacity_pool_version":"v1","destination_factory_id":2,'
    '"effective_from":"2026-01-01","effective_to":null,"revision":1,"season_id":1,'
    '"source_record_key":"capacity-pool:1:2:POOL-A:v1:1","source_system":"task9_historical_authority",'
    '"source_version":"v1"},"subfarm_id":null,"variety_id":20}],"revision":1,"season_id":1,'
    '"source_record_key":"capacity-pool:1:2:POOL-A:v1:1","source_system":"task9_historical_authority",'
    '"source_version":"v1"}'
)
_EXPECTED_POOL_HASH = "88084f705cc74476345e47522d0aa3a338ca8a652887928283d7bc96566e3c25"
_EXPECTED_POOL_STABLE = "capacity-pool:1:2:POOL-A"

_EXPECTED_MEMBER_JSON = (
    '{"farm_id":10,"parent_pool_identity":{"available_at_local_date":"2026-01-01",'
    '"capacity_input_mode":"LABOR_DERIVED","capacity_pool_code":"POOL-A","capacity_pool_grain":"FARM",'
    '"capacity_pool_version":"v1","destination_factory_id":2,"effective_from":"2026-01-01",'
    '"effective_to":null,"revision":1,"season_id":1,"source_record_key":"capacity-pool:1:2:POOL-A:v1:1",'
    '"source_system":"task9_historical_authority","source_version":"v1"},"subfarm_id":null,'
    '"variety_id":20}'
)
_EXPECTED_MEMBER_HASH = "4888e6a2596b28be7ebb3f9de9a2d566ae73aae951b5777aa9a0810d62c778da"

_EXPECTED_DAILY_JSON = (
    '{"available_at_local_date":"2026-01-31","capacity_date":"2026-02-01",'
    '"capacity_input_mode":"LABOR_DERIVED","capacity_pool_code":"POOL-A",'
    '"capacity_pool_revision":1,"capacity_pool_version":"v1","daily_capacity_revision":1,'
    '"destination_factory_id":2,"direct_nominal_capacity_kg_per_day":null,'
    '"kg_per_person_per_day":"20","labor_availability_ratio":"0.8",'
    '"operational_efficiency_ratio":"0.9","planned_picker_count":"10","season_id":1,'
    '"source_record_key":"daily-capacity:1:2:POOL-A:v1:1:2026-02-01:1",'
    '"source_system":"task9_historical_authority","source_version":"v1"}'
)
_EXPECTED_DAILY_HASH = "d0a85487603f81b3705de4cb78fac54aa4bb9b01f0d83503add50b889eb8ddcc"
_EXPECTED_DAILY_STABLE = "daily-capacity:1:2:POOL-A:v1:1:2026-02-01"

_EXPECTED_HOLIDAY_JSON = (
    '{"available_at_local_date":"2026-01-01","calendar_code":"CN-SH",'
    '"calendar_hash":"a44d69419c4187f3850cb937055119cf217d38902c4e8fbafaf2144297e87849",'
    '"calendar_version":"calendar-v1","dates":[{"holiday_code":"CNY","holiday_date":"2026-02-10",'
    '"holiday_name":"A"},{"holiday_code":"LOCAL","holiday_date":"2026-02-10","holiday_name":"B"}],'
    '"lifecycle_timezone_name":"Asia/Shanghai","region_scope":"CN-SH","revision":1,"season_id":1,'
    '"source_record_key":"holiday-calendar:1:CN-SH:Asia/Shanghai:calendar-v1:1",'
    '"source_system":"task9_historical_authority","source_version":"calendar-v1"}'
)
_EXPECTED_HOLIDAY_HASH = "3a4430ae2ac5ac28859b5909ed6bca1ac3ada7c47bb141de53dc487781ddbc61"
_EXPECTED_HOLIDAY_STABLE = "holiday-calendar:1:CN-SH:Asia/Shanghai"

_EXPECTED_WEATHER_JSON = (
    '{"available_at_local_date":"2026-01-01","config":{"combination_method":"MULTIPLY",'
    '"feature_rules":[{"bands":[{"lower_bound":"0","lower_inclusive":true,"multiplier":"1",'
    '"upper_bound":"10","upper_inclusive":true}],"feature_id":"rain"},'
    '{"bands":[{"lower_bound":"0","lower_inclusive":true,"multiplier":"0.9",'
    '"upper_bound":"30","upper_inclusive":true}],"feature_id":"temp"}],"maximum_ratio":"1",'
    '"minimum_ratio":"0.7","missing_feature_policy":"BLOCK","required_feature_ids":["rain","temp"],'
    '"version":"wx-v1"},"config_hash":"4854a46ee613e0562b1b294453cc5009a8db37adeb75cd36cf08aa04d29381ee",'
    '"effective_from":"2026-01-01","effective_to":null,"lifecycle_timezone_name":"Asia/Shanghai",'
    '"revision":1,"rule_code":"wx-rule","rule_version":"wx-v1",'
    '"source_record_key":"weather-rule:wx-rule:Asia/Shanghai:wx-v1:1",'
    '"source_system":"task9_historical_authority","source_version":"wx-v1"}'
)
_EXPECTED_WEATHER_HASH = "bc10adef4f9c5da8b613df6752c13a8cb97de42b36e29a7ba08a6e5e693d2d9f"
_EXPECTED_WEATHER_STABLE = "weather-rule:wx-rule:Asia/Shanghai"
_EXPECTED_CONFIG_HASH = "4854a46ee613e0562b1b294453cc5009a8db37adeb75cd36cf08aa04d29381ee"

_EXPECTED_RUN_PACKAGE_JSON = (
    '{"available_at_local_date":"2026-01-01","destination_factory_id":2,'
    '"destination_factory_timezone":"Asia/Shanghai","effective_from":"2026-01-01",'
    '"effective_to":null,"farm_scope_key":"farm-scope:10","farm_timezone":"Asia/Shanghai",'
    '"harvest_bucket_anchor_local_time":"09:00:00","harvest_to_arrival_lag_days":1,'
    '"holiday_calendar":{"authority_stable_key":"holiday-calendar:1:CN-SH:Asia/Shanghai",'
    '"business_row_hash":"3a4430ae2ac5ac28859b5909ed6bca1ac3ada7c47bb141de53dc487781ddbc61",'
    '"business_version":"calendar-v1","calendar_hash":"a44d69419c4187f3850cb937055119cf217d38902c4e8fbafaf2144297e87849",'
    '"lifecycle_timezone_name":"Asia/Shanghai","revision":1},"package_version":"pkg-v1",'
    '"revision":1,"season_id":1,"source_record_key":"run-package:1:2:farm-scope:10:pkg-v1:1",'
    '"source_system":"task9_historical_authority","source_version":"pkg-v1",'
    '"weather_rule":{"authority_stable_key":"weather-rule:wx-rule:Asia/Shanghai",'
    '"business_row_hash":"bc10adef4f9c5da8b613df6752c13a8cb97de42b36e29a7ba08a6e5e693d2d9f",'
    '"business_version":"wx-v1","config_hash":"4854a46ee613e0562b1b294453cc5009a8db37adeb75cd36cf08aa04d29381ee",'
    '"lifecycle_timezone_name":"Asia/Shanghai","revision":1}}'
)
_EXPECTED_RUN_PACKAGE_HASH = "e1ec986e71a098fce5f523167ba57ef4ea86397514629fdb965382dc1628942c"
_EXPECTED_RUN_PACKAGE_STABLE = "run-package:1:2:farm-scope:10"

_EXPECTED_INVENTORY_JSON = (
    '{"available_at_local_date":"2026-01-31","cohorts":[{"cohort_date":"2026-01-29",'
    '"farm_id":10,"forecast_quantile":"P50","parent_snapshot_identity":{"available_at_local_date":"2026-01-31",'
    '"destination_factory_id":2,"initial_opening_mature_inventory_kg":"30","opening_state_date":"2026-02-01",'
    '"revision":1,"season_id":1,"snapshot_version":"snap-v1",'
    '"source_record_key":"initial-inventory:1:2:2026-02-01:snap-v1:1",'
    '"source_system":"task9_historical_authority","source_version":"snap-v1"},'
    '"remaining_quantity_kg":"10","stable_cohort_key":"c1","subfarm_id":null,"variety_id":20},'
    '{"cohort_date":"2026-01-30","farm_id":10,"forecast_quantile":"P80","parent_snapshot_identity":'
    '{"available_at_local_date":"2026-01-31","destination_factory_id":2,'
    '"initial_opening_mature_inventory_kg":"30","opening_state_date":"2026-02-01","revision":1,'
    '"season_id":1,"snapshot_version":"snap-v1",'
    '"source_record_key":"initial-inventory:1:2:2026-02-01:snap-v1:1",'
    '"source_system":"task9_historical_authority","source_version":"snap-v1"},'
    '"remaining_quantity_kg":"10","stable_cohort_key":"c2","subfarm_id":null,"variety_id":20},'
    '{"cohort_date":"2026-01-31","farm_id":10,"forecast_quantile":"P90","parent_snapshot_identity":'
    '{"available_at_local_date":"2026-01-31","destination_factory_id":2,'
    '"initial_opening_mature_inventory_kg":"30","opening_state_date":"2026-02-01","revision":1,'
    '"season_id":1,"snapshot_version":"snap-v1",'
    '"source_record_key":"initial-inventory:1:2:2026-02-01:snap-v1:1",'
    '"source_system":"task9_historical_authority","source_version":"snap-v1"},'
    '"remaining_quantity_kg":"10","stable_cohort_key":"c3","subfarm_id":null,"variety_id":20}],'
    '"destination_factory_id":2,"initial_opening_mature_inventory_kg":"30","opening_state_date":"2026-02-01",'
    '"revision":1,"season_id":1,"snapshot_version":"snap-v1",'
    '"source_record_key":"initial-inventory:1:2:2026-02-01:snap-v1:1",'
    '"source_system":"task9_historical_authority","source_version":"snap-v1"}'
)
_EXPECTED_INVENTORY_HASH = "d6047707864469f1ce2cad139ea85d8bf0a92677b4c541304f25fee29eac82c0"
_EXPECTED_INVENTORY_STABLE = "initial-inventory:1:2:2026-02-01"

_EXPECTED_COHORT_JSON = (
    '{"cohort_date":"2026-01-29","farm_id":10,"forecast_quantile":"P50",'
    '"parent_snapshot_identity":{"available_at_local_date":"2026-01-31","destination_factory_id":2,'
    '"initial_opening_mature_inventory_kg":"30","opening_state_date":"2026-02-01","revision":1,'
    '"season_id":1,"snapshot_version":"snap-v1",'
    '"source_record_key":"initial-inventory:1:2:2026-02-01:snap-v1:1",'
    '"source_system":"task9_historical_authority","source_version":"snap-v1"},'
    '"remaining_quantity_kg":"10","stable_cohort_key":"c1","subfarm_id":null,"variety_id":20}'
)
_EXPECTED_COHORT_HASH = "e6101bd08447786dd04e0887c8698b1e043f2ba57727b81614e2ccdbaaebeec3"

_EXPECTED_LOSS_JSON = (
    '{"available_at_local_date":"2026-01-31","capacity_pool_code":"POOL-A",'
    '"destination_factory_id":2,"forecast_quantile":"P50","loss_version":"loss-v1",'
    '"mature_inventory_loss_quantity_kg":"5","revision":1,"season_id":1,'
    '"source_record_key":"mature-loss:1:2:POOL-A:2026-02-01:P50:loss-v1:1",'
    '"source_system":"task9_historical_authority","source_version":"loss-v1","state_date":"2026-02-01"}'
)
_EXPECTED_LOSS_HASH = "6bf2fdaef145ae6ed959577388c060e34ce50f49fc849305141c39035974ab3f"
_EXPECTED_LOSS_STABLE = "mature-loss:1:2:POOL-A:2026-02-01:P50"

_EXPECTED_EVENT_JSON = (
    '{"authority_business_version":"v1","authority_family":"daily_capacity",'
    '"authority_revision":1,"authority_stable_key":"daily-capacity:1:2:POOL-A:v1:1:2026-02-01",'
    '"business_row_hash":"8888888888888888888888888888888888888888888888888888888888888888",'
    '"event_schema_version":"task9-authority-lifecycle-event-v1","new_consumable_from_local_date":null,'
    '"new_consumable_to_local_date":null,"new_status":"draft","old_consumable_from_local_date":null,'
    '"old_consumable_to_local_date":null,"old_status":null,"source_record_key":"lifecycle:daily-capacity:1",'
    '"source_system":"task9_historical_authority","superseded_by_authority_business_version":null,'
    '"superseded_by_authority_revision":null,"superseded_by_authority_stable_key":null,'
    '"transition_sequence":1,"transitioned_at":"2026-01-01T09:00:00+00:00"}'
)
_EXPECTED_EVENT_HASH = "0d0f1a4cffd8183eafd1f5f7811399f9aaae68875188bab3e342c358144c0ffa"


def _daily_semantic(
    *,
    planned_picker_count: str = "10",
    minimum_capacity_pool_revision: int = 1,
    daily_capacity_revision: int = 1,
) -> Task9DailyCapacitySemanticInput:
    return Task9DailyCapacitySemanticInput(
        season_id=1,
        destination_factory_id=2,
        capacity_pool_code="POOL-A",
        capacity_pool_version="v1",
        capacity_pool_revision=minimum_capacity_pool_revision,
        capacity_date=date(2026, 2, 1),
        daily_capacity_revision=daily_capacity_revision,
        capacity_input_mode="LABOR_DERIVED",
        planned_picker_count=planned_picker_count,
        kg_per_person_per_day="20",
        direct_nominal_capacity_kg_per_day=None,
        labor_availability_ratio="0.8",
        operational_efficiency_ratio="0.9",
        available_at_local_date=date(2026, 1, 31),
        consumable_from_local_date=date(2026, 1, 31),
        consumable_to_local_date=None,
        status="active",
        status_changed_at=datetime(2026, 1, 31, 8, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="daily-capacity:1:2:POOL-A:v1:1:2026-02-01:1",
        source_version="v1",
    )


def _pool_bundle_semantic() -> Task9CapacityPoolDefinitionSemanticBundle:
    return Task9CapacityPoolDefinitionSemanticBundle(
        season_id=1,
        destination_factory_id=2,
        capacity_pool_code="POOL-A",
        capacity_pool_grain="FARM",
        capacity_input_mode="LABOR_DERIVED",
        capacity_pool_version="v1",
        revision=1,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        available_at_local_date=date(2026, 1, 1),
        consumable_from_local_date=None,
        consumable_to_local_date=None,
        status="draft",
        status_changed_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="capacity-pool:1:2:POOL-A:v1:1",
        source_version="v1",
        members=[Task9CapacityPoolMemberSchema(farm_id=10, subfarm_id=None, variety_id=20)],
    )


def _holiday_dates(
    *,
    include_extra_date: bool = False,
    duplicate_code: bool = False,
) -> list[Task9HolidayCalendarDateSchema]:
    dates = [
        Task9HolidayCalendarDateSchema(
            holiday_date=date(2026, 2, 10),
            holiday_code="CNY",
            holiday_name="A",
        ),
        Task9HolidayCalendarDateSchema(
            holiday_date=date(2026, 2, 10),
            holiday_code="CNY" if duplicate_code else "LOCAL",
            holiday_name="B",
        ),
    ]
    if include_extra_date:
        dates.append(
            Task9HolidayCalendarDateSchema(
                holiday_date=date(2026, 2, 11),
                holiday_code="EXTRA",
                holiday_name="C",
            )
        )
    return dates


def _holiday_header_semantic(
    *,
    version: str = "calendar-v1",
    revision: int = 1,
    calendar_hash: str | None = None,
    season_id: int = 1,
) -> Task9HolidayCalendarSemanticInput:
    if calendar_hash is None:
        calendar_hash = make_holiday_calendar_hash(
            holiday_calendar_version=version,
            holiday_dates=[date(2026, 2, 10)],
        )
    return Task9HolidayCalendarSemanticInput(
        season_id=season_id,
        calendar_code="CN-SH",
        calendar_version=version,
        revision=revision,
        calendar_hash=calendar_hash,
        region_scope="CN-SH",
        lifecycle_timezone_name="Asia/Shanghai",
        available_at_local_date=date(2026, 1, 1),
        consumable_from_local_date=date(2026, 1, 1),
        consumable_to_local_date=None,
        status="active",
        status_changed_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key=f"holiday-calendar:{season_id}:CN-SH:Asia/Shanghai:{version}:{revision}",
        source_version=version,
    )


def _holiday_bundle_semantic(
    *,
    include_extra_date: bool = False,
    duplicate_code: bool = False,
    version: str = "calendar-v1",
    revision: int = 1,
    season_id: int = 1,
) -> Task9HolidayCalendarSemanticBundle:
    dates = _holiday_dates(
        include_extra_date=include_extra_date,
        duplicate_code=duplicate_code,
    )
    return Task9HolidayCalendarSemanticBundle(
        **_holiday_header_semantic(
            version=version,
            revision=revision,
            season_id=season_id,
            calendar_hash=make_holiday_calendar_hash(
                holiday_calendar_version=version,
                holiday_dates=sorted({item.holiday_date for item in dates}),
            ),
        ).model_dump(),
        dates=dates,
    )


def _holiday_bundle_persisted(
    *,
    row_hash: str | None = None,
    include_extra_date: bool = False,
) -> Task9HolidayCalendarBundleSchema:
    bundle = _holiday_bundle_semantic(include_extra_date=include_extra_date)
    resolved_row_hash = row_hash if row_hash is not None else make_authority_row_hash(bundle)
    return Task9HolidayCalendarBundleSchema.model_validate(
        {**bundle.model_dump(), "row_hash": resolved_row_hash}
    )


def _weather_feature_rules(
    *,
    temp_multiplier: str = "0.9",
) -> list[WeatherFeatureRule]:
    return [
        WeatherFeatureRule(
            feature_id="rain",
            bands=[
                WeatherFeatureBand(
                    lower_bound="0",
                    lower_inclusive=True,
                    upper_bound="10",
                    upper_inclusive=True,
                    multiplier="1",
                )
            ],
        ),
        WeatherFeatureRule(
            feature_id="temp",
            bands=[
                WeatherFeatureBand(
                    lower_bound="0",
                    lower_inclusive=True,
                    upper_bound="30",
                    upper_inclusive=True,
                    multiplier=temp_multiplier,
                )
            ],
        ),
    ]


def _weather_config_hash(
    *,
    minimum_ratio: str = "0.7",
    maximum_ratio: str = "1",
    temp_multiplier: str = "0.9",
) -> str:
    return make_weather_rule_config_hash(
        {
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
                            "multiplier": temp_multiplier,
                        }
                    ],
                },
            ],
            "combination_method": "MULTIPLY",
            "minimum_ratio": minimum_ratio,
            "maximum_ratio": maximum_ratio,
            "missing_feature_policy": "BLOCK",
        }
    )


def _weather_semantic(
    *,
    minimum_ratio: str = "0.7",
    maximum_ratio: str = "1",
    temp_multiplier: str = "0.9",
) -> Task9WeatherRuleSemanticInput:
    return Task9WeatherRuleSemanticInput(
        rule_code="wx-rule",
        rule_version="wx-v1",
        revision=1,
        lifecycle_timezone_name="Asia/Shanghai",
        combination_method="MULTIPLY",
        minimum_ratio=minimum_ratio,
        maximum_ratio=maximum_ratio,
        required_feature_ids=["rain", "temp"],
        feature_rules=_weather_feature_rules(temp_multiplier=temp_multiplier),
        missing_feature_policy="BLOCK",
        config_hash=_weather_config_hash(
            minimum_ratio=minimum_ratio,
            maximum_ratio=maximum_ratio,
            temp_multiplier=temp_multiplier,
        ),
        available_at_local_date=date(2026, 1, 1),
        effective_from=date(2026, 1, 1),
        effective_to=None,
        consumable_from_local_date=date(2026, 1, 1),
        consumable_to_local_date=None,
        status="active",
        status_changed_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="weather-rule:wx-rule:Asia/Shanghai:wx-v1:1",
        source_version="wx-v1",
    )


def _weather_persisted(
    *,
    row_hash: str | None = None,
    minimum_ratio: str = "0.7",
    temp_multiplier: str = "0.9",
) -> Task9WeatherRuleConfigVersionSchema:
    semantic = _weather_semantic(
        minimum_ratio=minimum_ratio,
        temp_multiplier=temp_multiplier,
    )
    resolved_row_hash = row_hash if row_hash is not None else make_authority_row_hash(semantic)
    return Task9WeatherRuleConfigVersionSchema.model_validate(
        {**semantic.model_dump(), "row_hash": resolved_row_hash}
    )


def _run_package_semantic() -> Task9RunParameterPackageSemanticInput:
    return Task9RunParameterPackageSemanticInput(
        season_id=1,
        destination_factory_id=2,
        farm_scope_key="farm-scope:10",
        farm_timezone="Asia/Shanghai",
        destination_factory_timezone="Asia/Shanghai",
        harvest_bucket_anchor_local_time=time(9, 0),
        harvest_to_arrival_lag_days=1,
        package_version="pkg-v1",
        revision=1,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        available_at_local_date=date(2026, 1, 1),
        consumable_from_local_date=date(2026, 1, 1),
        consumable_to_local_date=None,
        status="active",
        status_changed_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="run-package:1:2:farm-scope:10:pkg-v1:1",
        source_version="pkg-v1",
    )


def _run_package_persisted(
    *,
    holiday_calendar_version_id: int,
    weather_rule_config_version_id: int,
) -> Task9RunParameterPackageSchema:
    return Task9RunParameterPackageSchema.model_validate(
        {
            **_run_package_semantic().model_dump(),
            "holiday_calendar_version_id": holiday_calendar_version_id,
            "weather_rule_config_version_id": weather_rule_config_version_id,
            "row_hash": "d" * 64,
        }
    )


def _run_package_bundle(
    *,
    package: Task9RunParameterPackageSemanticInput | Task9RunParameterPackageSchema | None = None,
    holiday_calendar: (
        Task9HolidayCalendarSemanticBundle | Task9HolidayCalendarBundleSchema | None
    ) = None,
    weather_rule: Task9WeatherRuleSemanticInput | Task9WeatherRuleConfigVersionSchema | None = None,
) -> Task9RunParameterPackageBundleSchema:
    return Task9RunParameterPackageBundleSchema(
        package=_run_package_semantic() if package is None else package,
        holiday_calendar=(
            _holiday_bundle_semantic() if holiday_calendar is None else holiday_calendar
        ),
        weather_rule=_weather_semantic() if weather_rule is None else weather_rule,
    )


def _inventory_bundle_semantic() -> Task9InitialInventorySemanticBundle:
    return Task9InitialInventorySemanticBundle(
        season_id=1,
        destination_factory_id=2,
        opening_state_date=date(2026, 2, 1),
        snapshot_version="snap-v1",
        revision=1,
        initial_opening_mature_inventory_kg="30",
        available_at_local_date=date(2026, 1, 31),
        consumable_from_local_date=date(2026, 1, 31),
        consumable_to_local_date=None,
        status="active",
        status_changed_at=datetime(2026, 1, 31, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="initial-inventory:1:2:2026-02-01:snap-v1:1",
        source_version="snap-v1",
        cohorts=[
            Task9InitialInventoryCohortSchema(
                stable_cohort_key="c1",
                forecast_quantile="P50",
                cohort_date=date(2026, 1, 29),
                farm_id=10,
                subfarm_id=None,
                variety_id=20,
                remaining_quantity_kg="10",
            ),
            Task9InitialInventoryCohortSchema(
                stable_cohort_key="c2",
                forecast_quantile="P80",
                cohort_date=date(2026, 1, 30),
                farm_id=10,
                subfarm_id=None,
                variety_id=20,
                remaining_quantity_kg="10",
            ),
            Task9InitialInventoryCohortSchema(
                stable_cohort_key="c3",
                forecast_quantile="P90",
                cohort_date=date(2026, 1, 31),
                farm_id=10,
                subfarm_id=None,
                variety_id=20,
                remaining_quantity_kg="10",
            ),
        ],
    )


def _inventory_header(
    bundle: Task9InitialInventorySemanticBundle,
) -> Task9InitialInventorySemanticInput:
    return Task9InitialInventorySemanticInput.model_validate(bundle.model_dump(exclude={"cohorts"}))


def _mature_loss_semantic() -> Task9MatureLossSemanticInput:
    return Task9MatureLossSemanticInput(
        season_id=1,
        destination_factory_id=2,
        state_date=date(2026, 2, 1),
        capacity_pool_code="POOL-A",
        forecast_quantile="P50",
        loss_version="loss-v1",
        revision=1,
        mature_inventory_loss_quantity_kg="5",
        available_at_local_date=date(2026, 1, 31),
        consumable_from_local_date=date(2026, 1, 31),
        consumable_to_local_date=None,
        status="active",
        status_changed_at=datetime(2026, 1, 31, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="mature-loss:1:2:POOL-A:2026-02-01:P50:loss-v1:1",
        source_version="loss-v1",
    )


def _lifecycle_event_semantic() -> Task9LifecycleEventSemanticInput:
    return Task9LifecycleEventSemanticInput(
        authority_family="daily_capacity",
        authority_stable_key=_EXPECTED_DAILY_STABLE,
        authority_business_version="v1",
        authority_revision=1,
        business_row_hash="8" * 64,
        transition_sequence=1,
        old_status=None,
        new_status="draft",
        old_consumable_from_local_date=None,
        old_consumable_to_local_date=None,
        new_consumable_from_local_date=None,
        new_consumable_to_local_date=None,
        superseded_by_authority_stable_key=None,
        superseded_by_authority_business_version=None,
        superseded_by_authority_revision=None,
        transitioned_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        source_system="task9_historical_authority",
        source_record_key="lifecycle:daily-capacity:1",
    )


def test_capacity_pool_definition_golden_vector() -> None:
    bundle = _pool_bundle_semantic()
    payload = build_capacity_pool_definition_payload(bundle.definition, bundle.members)
    assert canonical_payload_json(payload) == _EXPECTED_POOL_JSON
    assert make_authority_row_hash(bundle) == _EXPECTED_POOL_HASH
    assert build_capacity_pool_definition_stable_key(bundle.definition) == _EXPECTED_POOL_STABLE


def test_capacity_pool_member_golden_vector() -> None:
    bundle = _pool_bundle_semantic()
    payload = build_capacity_pool_member_payload(bundle.members[0], bundle.definition)
    assert canonical_payload_json(payload) == _EXPECTED_MEMBER_JSON
    assert (
        make_authority_row_hash(
            bundle.members[0],
            parent_definition=bundle.definition,
        )
        == _EXPECTED_MEMBER_HASH
    )


def test_daily_capacity_golden_vector() -> None:
    daily = _daily_semantic()
    payload = build_daily_capacity_payload(daily)
    assert canonical_payload_json(payload) == _EXPECTED_DAILY_JSON
    assert make_authority_row_hash(daily) == _EXPECTED_DAILY_HASH
    assert build_daily_capacity_stable_key(daily) == _EXPECTED_DAILY_STABLE


def test_holiday_calendar_golden_vector() -> None:
    holiday = _holiday_bundle_semantic()
    payload = build_holiday_calendar_payload(holiday, holiday.dates)
    assert canonical_payload_json(payload) == _EXPECTED_HOLIDAY_JSON
    assert make_authority_row_hash(holiday) == _EXPECTED_HOLIDAY_HASH
    assert build_holiday_calendar_stable_key(holiday) == _EXPECTED_HOLIDAY_STABLE


def test_weather_rule_golden_vector() -> None:
    weather = _weather_semantic()
    payload = build_weather_rule_config_payload(weather)
    assert canonical_payload_json(payload) == _EXPECTED_WEATHER_JSON
    assert make_authority_row_hash(weather) == _EXPECTED_WEATHER_HASH
    assert build_weather_rule_stable_key(weather) == _EXPECTED_WEATHER_STABLE


def test_run_parameter_package_golden_vector() -> None:
    bundle = _run_package_bundle()
    payload = build_run_parameter_package_payload(
        bundle.package,
        bundle.holiday_calendar,
        bundle.weather_rule,
    )
    assert canonical_payload_json(payload) == _EXPECTED_RUN_PACKAGE_JSON
    assert make_authority_row_hash(bundle) == _EXPECTED_RUN_PACKAGE_HASH
    assert build_run_parameter_package_stable_key(bundle.package) == _EXPECTED_RUN_PACKAGE_STABLE


def test_initial_inventory_golden_vector() -> None:
    bundle = _inventory_bundle_semantic()
    header = _inventory_header(bundle)
    payload = build_initial_inventory_snapshot_payload(header, bundle.cohorts)
    assert canonical_payload_json(payload) == _EXPECTED_INVENTORY_JSON
    assert make_authority_row_hash(bundle) == _EXPECTED_INVENTORY_HASH
    assert build_initial_inventory_stable_key(header) == _EXPECTED_INVENTORY_STABLE


def test_initial_inventory_cohort_golden_vector() -> None:
    bundle = _inventory_bundle_semantic()
    header = _inventory_header(bundle)
    payload = build_initial_inventory_cohort_payload(bundle.cohorts[0], header)
    assert canonical_payload_json(payload) == _EXPECTED_COHORT_JSON
    assert (
        make_authority_row_hash(
            bundle.cohorts[0],
            parent_snapshot=header,
        )
        == _EXPECTED_COHORT_HASH
    )


def test_mature_inventory_loss_golden_vector() -> None:
    loss = _mature_loss_semantic()
    payload = build_mature_inventory_loss_payload(loss)
    assert canonical_payload_json(payload) == _EXPECTED_LOSS_JSON
    assert make_authority_row_hash(loss) == _EXPECTED_LOSS_HASH
    assert build_mature_inventory_loss_stable_key(loss) == _EXPECTED_LOSS_STABLE


def test_lifecycle_event_golden_vector() -> None:
    event = _lifecycle_event_semantic()
    payload = build_lifecycle_event_payload(event)
    assert canonical_payload_json(payload) == _EXPECTED_EVENT_JSON
    assert make_lifecycle_event_hash(event) == _EXPECTED_EVENT_HASH


def test_holiday_bundle_duplicate_date_code_rejected() -> None:
    with pytest.raises(ValidationError, match="holiday \\(date, code\\) must be unique"):
        _holiday_bundle_semantic(duplicate_code=True)


def test_holiday_bundle_calendar_hash_mismatch_rejected() -> None:
    with pytest.raises(ValidationError, match="HOLIDAY_CALENDAR_HASH_MISMATCH"):
        Task9HolidayCalendarSemanticBundle(
            **_holiday_header_semantic(calendar_hash="a" * 64).model_dump(),
            dates=_holiday_dates(),
        )


def test_run_package_direct_builder_with_unverified_holiday_header_rejected() -> None:
    with pytest.raises(TypeError, match="bundle with dates"):
        build_run_parameter_package_payload(
            _run_package_semantic(),
            _holiday_header_semantic(),
            _weather_semantic(),
        )


def test_run_package_direct_hash_with_unverified_holiday_header_rejected() -> None:
    with pytest.raises(TypeError, match="bundle with dates"):
        make_authority_row_hash(
            _run_package_semantic(),
            holiday_calendar=_holiday_header_semantic(),
            weather_rule=_weather_semantic(),
        )


def test_run_package_bundle_with_verified_holiday_and_weather_passes() -> None:
    assert make_authority_row_hash(_run_package_bundle()) == _EXPECTED_RUN_PACKAGE_HASH


def test_run_package_entry_points_produce_identical_payload_and_hash() -> None:
    semantic_bundle = _run_package_bundle()
    direct_payload = build_run_parameter_package_payload(
        _run_package_semantic(),
        _holiday_bundle_semantic(),
        _weather_semantic(),
    )
    direct_hash = make_authority_row_hash(
        _run_package_semantic(),
        holiday_calendar=_holiday_bundle_semantic(),
        weather_rule=_weather_semantic(),
    )
    persisted_payload = build_run_parameter_package_payload(
        _run_package_persisted(
            holiday_calendar_version_id=10,
            weather_rule_config_version_id=20,
        ),
        _holiday_bundle_persisted(),
        _weather_persisted(),
    )
    persisted_hash = make_authority_row_hash(
        _run_package_persisted(
            holiday_calendar_version_id=10,
            weather_rule_config_version_id=20,
        ),
        holiday_calendar=_holiday_bundle_persisted(),
        weather_rule=_weather_persisted(),
    )
    semantic_payload = build_run_parameter_package_payload(
        semantic_bundle.package,
        semantic_bundle.holiday_calendar,
        semantic_bundle.weather_rule,
    )
    assert canonical_payload_json(semantic_payload) == _EXPECTED_RUN_PACKAGE_JSON
    assert canonical_payload_json(direct_payload) == canonical_payload_json(semantic_payload)
    assert canonical_payload_json(persisted_payload) == canonical_payload_json(semantic_payload)
    assert direct_hash == _EXPECTED_RUN_PACKAGE_HASH
    assert persisted_hash == _EXPECTED_RUN_PACKAGE_HASH


def test_run_package_calendar_hash_change_changes_hash() -> None:
    holiday_a = _holiday_bundle_semantic()
    holiday_b = _holiday_bundle_semantic(include_extra_date=True)
    assert holiday_a.calendar_hash != holiday_b.calendar_hash
    assert make_authority_row_hash(
        _run_package_semantic(),
        holiday_calendar=holiday_a,
        weather_rule=_weather_semantic(),
    ) != make_authority_row_hash(
        _run_package_semantic(),
        holiday_calendar=holiday_b,
        weather_rule=_weather_semantic(),
    )


def test_run_package_holiday_dates_change_changes_hash() -> None:
    hash_a = make_authority_row_hash(
        _run_package_semantic(),
        holiday_calendar=_holiday_bundle_semantic(),
        weather_rule=_weather_semantic(),
    )
    hash_b = make_authority_row_hash(
        _run_package_semantic(),
        holiday_calendar=_holiday_bundle_semantic(include_extra_date=True),
        weather_rule=_weather_semantic(),
    )
    assert hash_a != hash_b


def test_run_package_config_hash_change_changes_hash() -> None:
    weather_a = _weather_semantic()
    weather_b = _weather_semantic(minimum_ratio="0.8")
    assert weather_a.config_hash != weather_b.config_hash
    assert make_authority_row_hash(
        _run_package_semantic(),
        holiday_calendar=_holiday_bundle_semantic(),
        weather_rule=weather_a,
    ) != make_authority_row_hash(
        _run_package_semantic(),
        holiday_calendar=_holiday_bundle_semantic(),
        weather_rule=weather_b,
    )


def test_run_package_weather_config_change_changes_hash() -> None:
    weather_a = _weather_semantic()
    weather_b = _weather_semantic(temp_multiplier="0.8")
    assert weather_a.config_hash != weather_b.config_hash
    assert make_authority_row_hash(
        _run_package_semantic(),
        holiday_calendar=_holiday_bundle_semantic(),
        weather_rule=weather_a,
    ) != make_authority_row_hash(
        _run_package_semantic(),
        holiday_calendar=_holiday_bundle_semantic(),
        weather_rule=weather_b,
    )


def test_run_package_same_dependency_identity_is_deterministic() -> None:
    hash_a = make_authority_row_hash(
        _run_package_semantic(),
        holiday_calendar=_holiday_bundle_semantic(),
        weather_rule=_weather_semantic(),
    )
    hash_b = make_authority_row_hash(
        _run_package_semantic(),
        holiday_calendar=_holiday_bundle_semantic(),
        weather_rule=_weather_semantic(),
    )
    assert hash_a == hash_b


def test_persisted_holiday_row_hash_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match="HOLIDAY_CALENDAR_ROW_HASH_MISMATCH"):
        make_authority_row_hash(
            _run_package_semantic(),
            holiday_calendar=_holiday_bundle_persisted(row_hash="f" * 64),
            weather_rule=_weather_semantic(),
        )


def test_persisted_weather_row_hash_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match="WEATHER_RULE_ROW_HASH_MISMATCH"):
        make_authority_row_hash(
            _run_package_semantic(),
            holiday_calendar=_holiday_bundle_semantic(),
            weather_rule=_weather_persisted(row_hash="2" * 64),
        )


def test_run_package_surrogate_ids_do_not_change_hash() -> None:
    package_a = _run_package_persisted(
        holiday_calendar_version_id=10,
        weather_rule_config_version_id=20,
    )
    package_b = _run_package_persisted(
        holiday_calendar_version_id=999,
        weather_rule_config_version_id=888,
    )
    hash_a = make_authority_row_hash(
        package_a,
        holiday_calendar=_holiday_bundle_persisted(),
        weather_rule=_weather_persisted(),
    )
    hash_b = make_authority_row_hash(
        package_b,
        holiday_calendar=_holiday_bundle_persisted(),
        weather_rule=_weather_persisted(),
    )
    assert hash_a == hash_b == _EXPECTED_RUN_PACKAGE_HASH


def test_run_package_same_surrogate_ids_but_holiday_identity_change_changes_hash() -> None:
    package = _run_package_persisted(
        holiday_calendar_version_id=10,
        weather_rule_config_version_id=20,
    )
    hash_a = make_authority_row_hash(
        package,
        holiday_calendar=_holiday_bundle_persisted(),
        weather_rule=_weather_persisted(),
    )
    hash_b = make_authority_row_hash(
        package,
        holiday_calendar=_holiday_bundle_persisted(include_extra_date=True),
        weather_rule=_weather_persisted(),
    )
    assert hash_a != hash_b


def test_run_package_same_surrogate_ids_but_weather_identity_change_changes_hash() -> None:
    package = _run_package_persisted(
        holiday_calendar_version_id=10,
        weather_rule_config_version_id=20,
    )
    hash_a = make_authority_row_hash(
        package,
        holiday_calendar=_holiday_bundle_persisted(),
        weather_rule=_weather_persisted(),
    )
    hash_b = make_authority_row_hash(
        package,
        holiday_calendar=_holiday_bundle_persisted(),
        weather_rule=_weather_persisted(minimum_ratio="0.8"),
    )
    assert hash_a != hash_b


def test_run_package_scope_mismatch_rejected() -> None:
    with pytest.raises(ValidationError, match="RUN_PARAMETER_DEPENDENCY_SCOPE_CONFLICT"):
        _run_package_bundle(holiday_calendar=_holiday_bundle_semantic(season_id=2025))


def test_run_package_timezone_mismatch_rejected() -> None:
    package = Task9RunParameterPackageSemanticInput.model_validate(
        {
            **_run_package_semantic().model_dump(),
            "destination_factory_timezone": "US/Eastern",
        }
    )
    with pytest.raises(ValidationError, match="RUN_PARAMETER_DEPENDENCY_TIMEZONE_CONFLICT"):
        _run_package_bundle(package=package)


def test_business_row_hash_excludes_status_and_lifecycle_fields() -> None:
    hash_a = make_authority_row_hash(_daily_semantic())
    persisted = Task9DailyCapacitySemanticInput.model_validate(
        {
            **_daily_semantic().model_dump(),
            "status": "active",
            "status_changed_at": datetime(2026, 2, 1, 0, 0, tzinfo=UTC),
            "consumable_from_local_date": date(2026, 2, 1),
        }
    )
    assert hash_a == make_authority_row_hash(persisted)


def test_business_row_hash_changes_when_business_value_changes() -> None:
    assert make_authority_row_hash(_daily_semantic()) != make_authority_row_hash(
        _daily_semantic(planned_picker_count="999")
    )


def test_daily_parent_revision_changes_stable_key_but_child_revision_does_not() -> None:
    base = _daily_semantic()
    parent_changed = _daily_semantic(minimum_capacity_pool_revision=2)
    child_changed = _daily_semantic(daily_capacity_revision=2)
    assert build_daily_capacity_stable_key(base) != build_daily_capacity_stable_key(parent_changed)
    assert build_daily_capacity_stable_key(base) == build_daily_capacity_stable_key(child_changed)
