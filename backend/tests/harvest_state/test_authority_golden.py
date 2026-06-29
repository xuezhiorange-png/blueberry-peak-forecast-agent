"""Golden-vector regression tests for Task 9 authority semantic hashing.

Covers P0-1 (semantic inputs), P0-2 (mandatory run-package deps),
P0-3 (SUBFARM grain), P1-1 (no plain UniqueConstraint), P1-2 (golden vectors).
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest
from pydantic import ValidationError

from backend.app.harvest_state.authority_canonical import (
    build_capacity_pool_definition_payload,
    build_daily_capacity_payload,
    build_holiday_calendar_payload,
    build_initial_inventory_snapshot_payload,
    build_lifecycle_event_payload,
    build_mature_inventory_loss_payload,
    build_run_parameter_package_payload,
    build_weather_rule_config_payload,
    canonical_payload_json,
    make_authority_row_hash,
    make_lifecycle_event_hash,
)
from backend.app.harvest_state.authority_schemas import (
    Task9CapacityPoolDefinitionSemanticBundle,
    Task9CapacityPoolMemberSchema,
    Task9DailyCapacityAuthoritySchema,
    Task9DailyCapacitySemanticInput,
    Task9HolidayCalendarDateSchema,
    Task9HolidayCalendarSemanticBundle,
    Task9HolidayCalendarSemanticInput,
    Task9InitialInventoryCohortSchema,
    Task9InitialInventorySemanticBundle,
    Task9InitialInventorySemanticInput,
    Task9LifecycleEventSemanticInput,
    Task9MatureLossSemanticInput,
    Task9RunParameterPackageBundleSchema,
    Task9RunParameterPackageSemanticInput,
    Task9WeatherRuleSemanticInput,
)
from backend.app.harvest_state.canonical import (
    make_holiday_calendar_hash,
    sha256_hex,
)
from backend.app.harvest_state.schemas import WeatherFeatureBand, WeatherFeatureRule

# ── canonical JSON golden vectors ──────────────────────────────────────
# All values below are hardcoded from actual builder output.
# Changing any business field, source field, or canonical ordering will break these.


_EXPECTED_DAILY_JSON = (
    '{"available_at_local_date":"2026-01-31","capacity_date":"2026-02-01",'
    '"capacity_input_mode":"LABOR_DERIVED","capacity_pool_code":"POOL-A",'
    '"capacity_pool_revision":1,"capacity_pool_version":"v1",'
    '"daily_capacity_revision":1,"destination_factory_id":2,'
    '"direct_nominal_capacity_kg_per_day":null,'
    '"kg_per_person_per_day":"20","labor_availability_ratio":"0.8",'
    '"operational_efficiency_ratio":"0.9",'
    '"planned_picker_count":"10",'
    '"season_id":1,'
    '"source_record_key":"daily-capacity:1:2:POOL-A:v1:1:2026-02-01:1",'
    '"source_system":"task9_historical_authority","source_version":"v1"}'
)
_EXPECTED_DAILY_HASH = "d0a85487603f81b3705de4cb78fac54aa4bb9b01f0d83503add50b889eb8ddcc"
_EXPECTED_DAILY_STABLE = "daily-capacity:1:2:POOL-A:v1:1:2026-02-01"

_EXPECTED_POOL_JSON = (
    '{"available_at_local_date":"2026-01-01",'
    '"capacity_input_mode":"LABOR_DERIVED","capacity_pool_code":"POOL-A",'
    '"capacity_pool_grain":"FARM","capacity_pool_version":"v1",'
    '"destination_factory_id":2,"effective_from":"2026-01-01",'
    '"effective_to":null,"members":[{"farm_id":10,'
    '"parent_pool_identity":{"available_at_local_date":"2026-01-01",'
    '"capacity_input_mode":"LABOR_DERIVED","capacity_pool_code":"POOL-A",'
    '"capacity_pool_grain":"FARM","capacity_pool_version":"v1",'
    '"destination_factory_id":2,"effective_from":"2026-01-01",'
    '"effective_to":null,"revision":1,"season_id":1,'
    '"source_record_key":"capacity-pool:1:2:POOL-A:v1:1",'
    '"source_system":"task9_historical_authority","source_version":"v1"},'
    '"subfarm_id":null,"variety_id":20}],"revision":1,"season_id":1,'
    '"source_record_key":"capacity-pool:1:2:POOL-A:v1:1",'
    '"source_system":"task9_historical_authority","source_version":"v1"}'
)
_EXPECTED_POOL_HASH = "88084f705cc74476345e47522d0aa3a338ca8a652887928283d7bc96566e3c25"
_EXPECTED_POOL_STABLE = "capacity-pool:1:2:POOL-A"

_EXPECTED_MEMBER_HASH = "4888e6a2596b28be7ebb3f9de9a2d566ae73aae951b5777aa9a0810d62c778da"

_EXPECTED_RUN_PKG_HASH = "edcaf1234f8fbe5a539b346fbf981affbb5c626c5f40900a7585701958fdbf00"
_EXPECTED_RUN_PKG_STABLE = "run-package:1:2:farm-scope:10"

_EXPECTED_HOLIDAY_HASH = "3a4430ae2ac5ac28859b5909ed6bca1ac3ada7c47bb141de53dc487781ddbc61"
_EXPECTED_HOLIDAY_STABLE = "holiday-calendar:1:CN-SH:Asia/Shanghai"

_EXPECTED_WEATHER_HASH = "bc10adef4f9c5da8b613df6752c13a8cb97de42b36e29a7ba08a6e5e693d2d9f"
_EXPECTED_WEATHER_STABLE = "weather-rule:wx-rule:Asia/Shanghai"
_EXPECTED_CONFIG_HASH = "4854a46ee613e0562b1b294453cc5009a8db37adeb75cd36cf08aa04d29381ee"

_EXPECTED_INV_HASH = "d6047707864469f1ce2cad139ea85d8bf0a92677b4c541304f25fee29eac82c0"
_EXPECTED_INV_STABLE = "initial-inventory:1:2:2026-02-01"

_EXPECTED_COHORT_HASH = "e6101bd08447786dd04e0887c8698b1e043f2ba57727b81614e2ccdbaaebeec3"

_EXPECTED_LOSS_HASH = "6bf2fdaef145ae6ed959577388c060e34ce50f49fc849305141c39035974ab3f"
_EXPECTED_LOSS_STABLE = "mature-loss:1:2:POOL-A:2026-02-01:P50"

_EXPECTED_EVENT_HASH = "0d0f1a4cffd8183eafd1f5f7811399f9aaae68875188bab3e342c358144c0ffa"


_EXPECTED_EVENT_JSON = (
    '{"authority_business_version":"v1","authority_family":"daily_capacity",'
    '"authority_revision":1,'
    '"authority_stable_key":"daily-capacity:1:2:POOL-A:v1:1:2026-02-01",'
    '"business_row_hash":"8888888888888888888888888888888888888888888888888888888888888888",'
    '"event_schema_version":"task9-authority-lifecycle-event-v1",'
    '"new_consumable_from_local_date":null,"new_consumable_to_local_date":null,'
    '"new_status":"draft","old_consumable_from_local_date":null,'
    '"old_consumable_to_local_date":null,"old_status":null,'
    '"source_record_key":"lifecycle:daily-capacity:1",'
    '"source_system":"task9_historical_authority",'
    '"superseded_by_authority_business_version":null,'
    '"superseded_by_authority_revision":null,'
    '"superseded_by_authority_stable_key":null,'
    '"transition_sequence":1,"transitioned_at":"2026-01-01T09:00:00+00:00"}'
)


# ── helpers ────────────────────────────────────────────────────────────


def _daily_semantic() -> Task9DailyCapacitySemanticInput:
    return Task9DailyCapacitySemanticInput(
        season_id=1, destination_factory_id=2,
        capacity_pool_code="POOL-A", capacity_pool_version="v1",
        capacity_pool_revision=1, capacity_date=date(2026, 2, 1),
        daily_capacity_revision=1, capacity_input_mode="LABOR_DERIVED",
        planned_picker_count="10", kg_per_person_per_day="20",
        direct_nominal_capacity_kg_per_day=None,
        labor_availability_ratio="0.8", operational_efficiency_ratio="0.9",
        available_at_local_date=date(2026, 1, 31),
        consumable_from_local_date=date(2026, 1, 31), consumable_to_local_date=None,
        status="active", status_changed_at=datetime(2026, 1, 31, 8, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="daily-capacity:1:2:POOL-A:v1:1:2026-02-01:1",
        source_version="v1",
    )


def _pool_bundle_semantic() -> Task9CapacityPoolDefinitionSemanticBundle:
    return Task9CapacityPoolDefinitionSemanticBundle(
        season_id=1, destination_factory_id=2,
        capacity_pool_code="POOL-A", capacity_pool_grain="FARM",
        capacity_input_mode="LABOR_DERIVED", capacity_pool_version="v1",
        revision=1, effective_from=date(2026, 1, 1), effective_to=None,
        available_at_local_date=date(2026, 1, 1),
        consumable_from_local_date=None, consumable_to_local_date=None,
        status="draft", status_changed_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="capacity-pool:1:2:POOL-A:v1:1",
        source_version="v1",
        members=[Task9CapacityPoolMemberSchema(farm_id=10, subfarm_id=None, variety_id=20)],
    )


def _holiday_semantic() -> Task9HolidayCalendarSemanticInput:
    cal_hash = make_holiday_calendar_hash(
        holiday_calendar_version="calendar-v1", holiday_dates=[date(2026, 2, 10)]
    )
    return Task9HolidayCalendarSemanticInput(
        season_id=1, calendar_code="CN-SH", calendar_version="calendar-v1",
        revision=1, calendar_hash=cal_hash, region_scope="CN-SH",
        lifecycle_timezone_name="Asia/Shanghai",
        available_at_local_date=date(2026, 1, 1),
        consumable_from_local_date=date(2026, 1, 1), consumable_to_local_date=None,
        status="active", status_changed_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="holiday-calendar:1:CN-SH:Asia/Shanghai:calendar-v1:1",
        source_version="calendar-v1",
    )


def _weather_semantic() -> Task9WeatherRuleSemanticInput:
    return Task9WeatherRuleSemanticInput(
        rule_code="wx-rule", rule_version="wx-v1", revision=1,
        lifecycle_timezone_name="Asia/Shanghai",
        combination_method="MULTIPLY", minimum_ratio="0.7", maximum_ratio="1",
        required_feature_ids=["rain", "temp"],
        feature_rules=[
            WeatherFeatureRule(feature_id="rain", bands=[
                WeatherFeatureBand(lower_bound="0", lower_inclusive=True,
                                   upper_bound="10", upper_inclusive=True, multiplier="1")]),
            WeatherFeatureRule(feature_id="temp", bands=[
                WeatherFeatureBand(lower_bound="0", lower_inclusive=True,
                                   upper_bound="30", upper_inclusive=True, multiplier="0.9")]),
        ],
        missing_feature_policy="BLOCK",
        config_hash=_EXPECTED_CONFIG_HASH,
        available_at_local_date=date(2026, 1, 1),
        effective_from=date(2026, 1, 1), effective_to=None,
        consumable_from_local_date=date(2026, 1, 1), consumable_to_local_date=None,
        status="active", status_changed_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="weather-rule:wx-rule:Asia/Shanghai:wx-v1:1",
        source_version="wx-v1",
    )


def _run_pkg_semantic() -> Task9RunParameterPackageSemanticInput:
    return Task9RunParameterPackageSemanticInput(
        season_id=1, destination_factory_id=2, farm_scope_key="farm-scope:10",
        farm_timezone="Asia/Shanghai", destination_factory_timezone="Asia/Shanghai",
        harvest_bucket_anchor_local_time=time(9, 0), harvest_to_arrival_lag_days=1,
        package_version="pkg-v1", revision=1,
        effective_from=date(2026, 1, 1), effective_to=None,
        available_at_local_date=date(2026, 1, 1),
        consumable_from_local_date=date(2026, 1, 1), consumable_to_local_date=None,
        status="active", status_changed_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="run-package:1:2:farm-scope:10:pkg-v1:1",
        source_version="pkg-v1",
    )


def _loss_semantic() -> Task9MatureLossSemanticInput:
    return Task9MatureLossSemanticInput(
        season_id=1, destination_factory_id=2, state_date=date(2026, 2, 1),
        capacity_pool_code="POOL-A", forecast_quantile="P50", loss_version="loss-v1",
        revision=1, mature_inventory_loss_quantity_kg="5",
        available_at_local_date=date(2026, 1, 31),
        consumable_from_local_date=date(2026, 1, 31), consumable_to_local_date=None,
        status="active", status_changed_at=datetime(2026, 1, 31, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="mature-loss:1:2:POOL-A:2026-02-01:P50:loss-v1:1",
        source_version="loss-v1",
    )


def _inv_bundle_semantic() -> Task9InitialInventorySemanticBundle:
    return Task9InitialInventorySemanticBundle(
        season_id=1, destination_factory_id=2, opening_state_date=date(2026, 2, 1),
        snapshot_version="snap-v1", revision=1,
        initial_opening_mature_inventory_kg="30",
        available_at_local_date=date(2026, 1, 31),
        consumable_from_local_date=date(2026, 1, 31), consumable_to_local_date=None,
        status="active", status_changed_at=datetime(2026, 1, 31, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="initial-inventory:1:2:2026-02-01:snap-v1:1",
        source_version="snap-v1",
        cohorts=[
            Task9InitialInventoryCohortSchema(
                stable_cohort_key="c1", forecast_quantile="P50",
                cohort_date=date(2026, 1, 29), farm_id=10, subfarm_id=None,
                variety_id=20, remaining_quantity_kg="10"),
            Task9InitialInventoryCohortSchema(
                stable_cohort_key="c2", forecast_quantile="P80",
                cohort_date=date(2026, 1, 30), farm_id=10, subfarm_id=None,
                variety_id=20, remaining_quantity_kg="10"),
            Task9InitialInventoryCohortSchema(
                stable_cohort_key="c3", forecast_quantile="P90",
                cohort_date=date(2026, 1, 31), farm_id=10, subfarm_id=None,
                variety_id=20, remaining_quantity_kg="10"),
        ],
    )


def _lifecycle_semantic() -> Task9LifecycleEventSemanticInput:
    return Task9LifecycleEventSemanticInput(
        authority_family="daily_capacity",
        authority_stable_key="daily-capacity:1:2:POOL-A:v1:1:2026-02-01",
        authority_business_version="v1", authority_revision=1,
        business_row_hash="8" * 64, transition_sequence=1,
        old_status=None, new_status="draft",
        old_consumable_from_local_date=None, old_consumable_to_local_date=None,
        new_consumable_from_local_date=None, new_consumable_to_local_date=None,
        superseded_by_authority_stable_key=None,
        superseded_by_authority_business_version=None,
        superseded_by_authority_revision=None,
        transitioned_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        source_system="task9_historical_authority",
        source_record_key="lifecycle:daily-capacity:1",
    )


# ── P0-1: semantic inputs without row_hash ────────────────────────────


def test_daily_semantic_input_without_row_hash() -> None:
    """P0-1: construct semantic input without row_hash -> pass."""
    daily = _daily_semantic()
    assert daily.capacity_pool_code == "POOL-A"


def test_daily_semantic_hash_returns_fixed_digest() -> None:
    """P0-1: make_authority_row_hash on semantic input -> fixed digest."""
    daily = _daily_semantic()
    payload = build_daily_capacity_payload(daily)
    assert canonical_payload_json(payload) == _EXPECTED_DAILY_JSON
    assert make_authority_row_hash(daily) == _EXPECTED_DAILY_HASH


def test_lifecycle_semantic_input_without_event_hash() -> None:
    """P0-1: construct lifecycle semantic input without lifecycle_event_hash -> pass."""
    evt = _lifecycle_semantic()
    assert evt.authority_family.value == "daily_capacity"


def test_lifecycle_semantic_hash_returns_fixed_digest() -> None:
    """P0-1: make_lifecycle_event_hash on semantic input -> fixed digest."""
    evt = _lifecycle_semantic()
    assert make_lifecycle_event_hash(evt) == _EXPECTED_EVENT_HASH


# ── P1-2: Golden vectors with hardcoded JSON and SHA-256 ──────────────


def test_capacity_pool_definition_golden_vector() -> None:
    bundle = _pool_bundle_semantic()
    payload = build_capacity_pool_definition_payload(bundle.definition, bundle.members)
    assert canonical_payload_json(payload) == _EXPECTED_POOL_JSON
    assert make_authority_row_hash(bundle) == _EXPECTED_POOL_HASH


def test_capacity_pool_member_golden_vector() -> None:
    bundle = _pool_bundle_semantic()
    member = bundle.members[0]
    parent_def = bundle.definition
    # P0-1: unified entry via make_authority_row_hash with parent_definition
    assert make_authority_row_hash(member, parent_definition=parent_def) == _EXPECTED_MEMBER_HASH


def test_run_parameter_package_golden_vector() -> None:
    bundle = Task9RunParameterPackageBundleSchema(
        package=_run_pkg_semantic(),
        holiday_calendar=_holiday_semantic(),
        weather_rule=_weather_semantic(),
    )
    assert make_authority_row_hash(bundle) == _EXPECTED_RUN_PKG_HASH


def test_holiday_calendar_golden_vector() -> None:
    bundle = Task9HolidayCalendarSemanticBundle(
        **_holiday_semantic().model_dump(),
        dates=[
            Task9HolidayCalendarDateSchema(
                holiday_date=date(2026, 2, 10), holiday_code="CNY", holiday_name="A"),
            Task9HolidayCalendarDateSchema(
                holiday_date=date(2026, 2, 10), holiday_code="LOCAL", holiday_name="B"),
        ],
    )
    header = Task9HolidayCalendarSemanticInput.model_validate(
        bundle.model_dump(exclude={"dates"})
    )
    payload = build_holiday_calendar_payload(header, bundle.dates)
    assert sha256_hex(payload) == _EXPECTED_HOLIDAY_HASH


def test_weather_rule_golden_vector() -> None:
    weather = _weather_semantic()
    payload = build_weather_rule_config_payload(weather)
    assert sha256_hex(payload) == _EXPECTED_WEATHER_HASH


def test_initial_inventory_golden_vector() -> None:
    bundle = _inv_bundle_semantic()
    snap_input = Task9InitialInventorySemanticInput.model_validate(
        bundle.model_dump(exclude={"cohorts"})
    )
    payload = build_initial_inventory_snapshot_payload(snap_input, bundle.cohorts)
    assert sha256_hex(payload) == _EXPECTED_INV_HASH


def test_cohort_golden_vector() -> None:
    bundle = _inv_bundle_semantic()
    snap_input = Task9InitialInventorySemanticInput.model_validate(
        bundle.model_dump(exclude={"cohorts"})
    )
    cohort = bundle.cohorts[0]
    # P0-1: unified entry via make_authority_row_hash with parent_snapshot
    assert make_authority_row_hash(cohort, parent_snapshot=snap_input) == _EXPECTED_COHORT_HASH


def test_mature_loss_golden_vector() -> None:
    loss = _loss_semantic()
    payload = build_mature_inventory_loss_payload(loss)
    assert sha256_hex(payload) == _EXPECTED_LOSS_HASH


def test_lifecycle_event_golden_vector() -> None:
    evt = _lifecycle_semantic()
    payload = build_lifecycle_event_payload(evt)
    assert canonical_payload_json(payload) == _EXPECTED_EVENT_JSON
    assert make_lifecycle_event_hash(evt) == _EXPECTED_EVENT_HASH


# ── P0-2: run-package mandatory dependencies ──────────────────────────


def test_run_package_hash_without_holiday_rejected() -> None:
    pkg = _run_pkg_semantic()
    weather = _weather_semantic()
    with pytest.raises(TypeError, match="requires both"):
        make_authority_row_hash(pkg, weather_rule=weather)


def test_run_package_hash_without_weather_rejected() -> None:
    pkg = _run_pkg_semantic()
    holiday = _holiday_semantic()
    with pytest.raises(TypeError, match="requires both"):
        make_authority_row_hash(pkg, holiday_header=holiday)


def test_run_package_hash_with_both_passes() -> None:
    pkg = _run_pkg_semantic()
    holiday = _holiday_semantic()
    weather = _weather_semantic()
    h = make_authority_row_hash(pkg, holiday_header=holiday, weather_rule=weather)
    assert h == _EXPECTED_RUN_PKG_HASH


def test_run_package_surrogate_id_change_same_hash() -> None:
    """No surrogate FK IDs exist in semantic input."""
    pkg = _run_pkg_semantic()
    dump = pkg.model_dump()
    assert "holiday_calendar_version_id" not in dump
    assert "weather_rule_config_version_id" not in dump


def test_run_package_holiday_identity_change_changes_hash() -> None:
    holiday2 = Task9HolidayCalendarSemanticInput(
        season_id=1, calendar_code="CN-SH", calendar_version="calendar-v2",
        revision=2, calendar_hash="a" * 64, region_scope="CN-SH",
        lifecycle_timezone_name="Asia/Shanghai",
        available_at_local_date=date(2026, 1, 1),
        consumable_from_local_date=date(2026, 1, 1), consumable_to_local_date=None,
        status="active", status_changed_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="holiday-calendar:1:CN-SH:Asia/Shanghai:calendar-v2:2",
        source_version="calendar-v2",
    )
    pkg = _run_pkg_semantic()
    weather = _weather_semantic()
    h1 = make_authority_row_hash(pkg, holiday_header=_holiday_semantic(), weather_rule=weather)
    h2 = make_authority_row_hash(pkg, holiday_header=holiday2, weather_rule=weather)
    assert h1 != h2


def test_run_package_weather_identity_change_changes_hash() -> None:
    """P1-2: two truly different weather semantic identities -> different run-package hash."""
    pkg = _run_pkg_semantic()
    holiday = _holiday_semantic()
    weather_v1 = _weather_semantic()  # wx-v1, revision 1
    weather_v2 = Task9WeatherRuleSemanticInput(
        rule_code="wx-rule", rule_version="wx-v2", revision=2,
        lifecycle_timezone_name="Asia/Shanghai",
        combination_method="MULTIPLY", minimum_ratio="0.7", maximum_ratio="1",
        required_feature_ids=["rain", "temp"],
        feature_rules=[
            WeatherFeatureRule(feature_id="rain", bands=[
                WeatherFeatureBand(lower_bound="0", lower_inclusive=True,
                                   upper_bound="10", upper_inclusive=True, multiplier="1")]),
            WeatherFeatureRule(feature_id="temp", bands=[
                WeatherFeatureBand(lower_bound="0", lower_inclusive=True,
                                   upper_bound="30", upper_inclusive=True, multiplier="0.9")]),
        ],
        missing_feature_policy="BLOCK",
        config_hash="1cd2cf84e812d603f18af7800b9b68479a69528f2e285efe759ac7eb68f98d12",
        available_at_local_date=date(2026, 1, 1),
        effective_from=date(2026, 1, 1), effective_to=None,
        consumable_from_local_date=date(2026, 1, 1), consumable_to_local_date=None,
        status="active", status_changed_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="weather-rule:wx-rule:Asia/Shanghai:wx-v2:2",
        source_version="wx-v2",
    )
    h1 = make_authority_row_hash(pkg, holiday_header=holiday, weather_rule=weather_v1)
    h2 = make_authority_row_hash(pkg, holiday_header=holiday, weather_rule=weather_v2)
    assert h1 != h2

    # P1-2: same semantic weather + different database surrogate ID -> same hash
    weather_v1_copy = Task9WeatherRuleSemanticInput(
        rule_code="wx-rule", rule_version="wx-v1", revision=1,
        lifecycle_timezone_name="Asia/Shanghai",
        combination_method="MULTIPLY", minimum_ratio="0.7", maximum_ratio="1",
        required_feature_ids=["rain", "temp"],
        feature_rules=[
            WeatherFeatureRule(feature_id="rain", bands=[
                WeatherFeatureBand(lower_bound="0", lower_inclusive=True,
                                   upper_bound="10", upper_inclusive=True, multiplier="1")]),
            WeatherFeatureRule(feature_id="temp", bands=[
                WeatherFeatureBand(lower_bound="0", lower_inclusive=True,
                                   upper_bound="30", upper_inclusive=True, multiplier="0.9")]),
        ],
        missing_feature_policy="BLOCK",
        config_hash=_EXPECTED_CONFIG_HASH,
        available_at_local_date=date(2026, 1, 1),
        effective_from=date(2026, 1, 1), effective_to=None,
        consumable_from_local_date=date(2026, 1, 1), consumable_to_local_date=None,
        status="active", status_changed_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="weather-rule:wx-rule:Asia/Shanghai:wx-v1:1",  # same key
        source_version="wx-v1",
    )
    h3 = make_authority_row_hash(pkg, holiday_header=holiday, weather_rule=weather_v1_copy)
    assert h1 == h3


def test_run_package_timezone_mismatch_rejected() -> None:
    """P0-2: valid IANA timezone but mismatched -> RUN_PARAMETER_DEPENDENCY_TIMEZONE_CONFLICT."""
    pkg = Task9RunParameterPackageSemanticInput(
        season_id=1, destination_factory_id=2, farm_scope_key="farm-scope:10",
        farm_timezone="Asia/Shanghai", destination_factory_timezone="US/Eastern",
        harvest_bucket_anchor_local_time=time(9, 0), harvest_to_arrival_lag_days=1,
        package_version="pkg-v1", revision=1,
        effective_from=date(2026, 1, 1), effective_to=None,
        available_at_local_date=date(2026, 1, 1),
        consumable_from_local_date=date(2026, 1, 1), consumable_to_local_date=None,
        status="active", status_changed_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="run-package:1:2:farm-scope:10:pkg-v1:1",
        source_version="pkg-v1",
    )
    holiday = _holiday_semantic()  # Asia/Shanghai
    weather = _weather_semantic()  # Asia/Shanghai
    with pytest.raises(ValidationError, match="RUN_PARAMETER_DEPENDENCY_TIMEZONE_CONFLICT"):
        Task9RunParameterPackageBundleSchema(
            package=pkg, holiday_calendar=holiday, weather_rule=weather
        )


def test_direct_builder_timezone_mismatch_rejected() -> None:
    """P0-2: direct builder with timezone mismatch -> ValueError."""
    pkg = Task9RunParameterPackageSemanticInput(
        season_id=1, destination_factory_id=2, farm_scope_key="farm-scope:10",
        farm_timezone="Asia/Shanghai", destination_factory_timezone="US/Eastern",
        harvest_bucket_anchor_local_time=time(9, 0), harvest_to_arrival_lag_days=1,
        package_version="pkg-v1", revision=1,
        effective_from=date(2026, 1, 1), effective_to=None,
        available_at_local_date=date(2026, 1, 1),
        consumable_from_local_date=date(2026, 1, 1), consumable_to_local_date=None,
        status="active", status_changed_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="run-package:1:2:farm-scope:10:pkg-v1:1",
        source_version="pkg-v1",
    )
    holiday = _holiday_semantic()  # Asia/Shanghai
    weather = _weather_semantic()  # Asia/Shanghai
    with pytest.raises(ValueError, match="RUN_PARAMETER_DEPENDENCY_TIMEZONE_CONFLICT"):
        build_run_parameter_package_payload(pkg, holiday, weather)


def test_direct_hash_timezone_mismatch_rejected() -> None:
    """P0-2: direct hash with timezone mismatch -> ValueError."""
    pkg = Task9RunParameterPackageSemanticInput(
        season_id=1, destination_factory_id=2, farm_scope_key="farm-scope:10",
        farm_timezone="Asia/Shanghai", destination_factory_timezone="US/Eastern",
        harvest_bucket_anchor_local_time=time(9, 0), harvest_to_arrival_lag_days=1,
        package_version="pkg-v1", revision=1,
        effective_from=date(2026, 1, 1), effective_to=None,
        available_at_local_date=date(2026, 1, 1),
        consumable_from_local_date=date(2026, 1, 1), consumable_to_local_date=None,
        status="active", status_changed_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="run-package:1:2:farm-scope:10:pkg-v1:1",
        source_version="pkg-v1",
    )
    holiday = _holiday_semantic()  # Asia/Shanghai
    weather = _weather_semantic()  # Asia/Shanghai
    with pytest.raises(ValueError, match="RUN_PARAMETER_DEPENDENCY_TIMEZONE_CONFLICT"):
        make_authority_row_hash(pkg, holiday_header=holiday, weather_rule=weather)


def test_package_season_mismatch_rejected() -> None:
    """P0-3: package season 2026 + holiday season 2025 -> scope conflict."""
    holiday_2025 = Task9HolidayCalendarSemanticInput(
        season_id=2025, calendar_code="CN-SH", calendar_version="calendar-v1",
        revision=1, calendar_hash="a" * 64, region_scope="CN-SH",
        lifecycle_timezone_name="Asia/Shanghai",
        available_at_local_date=date(2026, 1, 1),
        consumable_from_local_date=date(2026, 1, 1), consumable_to_local_date=None,
        status="active", status_changed_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="holiday-calendar:2025:CN-SH:Asia/Shanghai:calendar-v1:1",
        source_version="calendar-v1",
    )
    pkg = _run_pkg_semantic()  # season_id=2026
    weather = _weather_semantic()
    with pytest.raises(ValueError, match="RUN_PARAMETER_DEPENDENCY_SCOPE_CONFLICT"):
        build_run_parameter_package_payload(pkg, holiday_2025, weather)


def test_holiday_calendar_hash_mismatch_rejected() -> None:
    """P0-3: holiday with different calendar_version -> different run-package hash."""
    # Create holiday with different calendar_version (which IS in semantic identity)
    holiday_v2 = Task9HolidayCalendarSemanticInput(
        season_id=1, calendar_code="CN-SH", calendar_version="calendar-v2",
        revision=2, calendar_hash="f" * 64,
        region_scope="CN-SH",
        lifecycle_timezone_name="Asia/Shanghai",
        available_at_local_date=date(2026, 1, 1),
        consumable_from_local_date=date(2026, 1, 1), consumable_to_local_date=None,
        status="active", status_changed_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="holiday-calendar:1:CN-SH:Asia/Shanghai:calendar-v2:2",
        source_version="calendar-v2",
    )
    pkg = _run_pkg_semantic()
    weather = _weather_semantic()
    h_good = make_authority_row_hash(
        pkg, holiday_header=_holiday_semantic(), weather_rule=weather
    )
    h_bad = make_authority_row_hash(
        pkg, holiday_header=holiday_v2, weather_rule=weather
    )
    assert h_good != h_bad


# ── P0-3: SUBFARM grain ──────────────────────────────────────────────


def test_subfarm_none_and_real_subfarm_rejected() -> None:
    with pytest.raises(ValidationError, match="SUBFARM.*exactly one subfarm"):
        Task9CapacityPoolDefinitionSemanticBundle(
            season_id=1, destination_factory_id=2,
            capacity_pool_code="POOL-A", capacity_pool_grain="SUBFARM",
            capacity_input_mode="LABOR_DERIVED", capacity_pool_version="v1",
            revision=1, effective_from=date(2026, 1, 1), effective_to=None,
            available_at_local_date=date(2026, 1, 1),
            consumable_from_local_date=None, consumable_to_local_date=None,
            status="draft", status_changed_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            superseded_by_id=None,
            source_system="task9_historical_authority",
            source_record_key="capacity-pool:1:2:POOL-A:v1:1",
            source_version="v1",
            members=[
                Task9CapacityPoolMemberSchema(farm_id=10, subfarm_id=None, variety_id=20),
                Task9CapacityPoolMemberSchema(farm_id=10, subfarm_id=5, variety_id=30),
            ],
        )


# ── P0-1: hash excludes metadata ──────────────────────────────────────


def test_hash_excludes_status_and_lifecycle() -> None:
    """Changing status/lifecycle must not change business hash."""
    daily = _daily_semantic()
    h1 = make_authority_row_hash(daily)
    # Create same daily but with different status (via persisted schema)
    daily_changed = Task9DailyCapacityAuthoritySchema.model_validate({
        "capacity_pool_definition_id": 11,
        "season_id": 1, "destination_factory_id": 2,
        "capacity_pool_code": "POOL-A", "capacity_pool_version": "v1",
        "capacity_pool_revision": 1, "capacity_date": date(2026, 2, 1),
        "daily_capacity_revision": 1, "capacity_input_mode": "LABOR_DERIVED",
        "planned_picker_count": "10", "kg_per_person_per_day": "20",
        "direct_nominal_capacity_kg_per_day": None,
        "labor_availability_ratio": "0.8", "operational_efficiency_ratio": "0.9",
        "available_at_local_date": date(2026, 1, 31),
        "consumable_from_local_date": date(2026, 1, 31),
        "consumable_to_local_date": date(2026, 3, 1),
        "status": "superseded", "status_changed_at": datetime(2026, 2, 1, 0, 0, tzinfo=UTC),
        "superseded_by_id": 99,
        "source_system": "task9_historical_authority",
        "source_record_key": "daily-capacity:1:2:POOL-A:v1:1:2026-02-01:1",
        "source_version": "v1", "row_hash": "a" * 64,
    })
    h2 = make_authority_row_hash(daily_changed)
    assert h1 == h2


def test_hash_changes_when_business_value_changes() -> None:
    daily1 = _daily_semantic()
    daily2 = Task9DailyCapacitySemanticInput(
        season_id=1, destination_factory_id=2,
        capacity_pool_code="POOL-A", capacity_pool_version="v1",
        capacity_pool_revision=1, capacity_date=date(2026, 2, 1),
        daily_capacity_revision=1, capacity_input_mode="LABOR_DERIVED",
        planned_picker_count="999", kg_per_person_per_day="20",
        direct_nominal_capacity_kg_per_day=None,
        labor_availability_ratio="0.8", operational_efficiency_ratio="0.9",
        available_at_local_date=date(2026, 1, 31),
        consumable_from_local_date=date(2026, 1, 31), consumable_to_local_date=None,
        status="active", status_changed_at=datetime(2026, 1, 31, 8, 0, tzinfo=UTC),
        superseded_by_id=None,
        source_system="task9_historical_authority",
        source_record_key="daily-capacity:1:2:POOL-A:v1:1:2026-02-01:1",
        source_version="v1",
    )
    assert make_authority_row_hash(daily1) != make_authority_row_hash(daily2)


# ── Stable key golden assertions ──────────────────────────────────────


def test_all_stable_keys_golden() -> None:
    from backend.app.harvest_state.authority_canonical import (
        build_capacity_pool_definition_stable_key,
        build_daily_capacity_stable_key,
        build_holiday_calendar_stable_key,
        build_initial_inventory_stable_key,
        build_mature_inventory_loss_stable_key,
        build_run_parameter_package_stable_key,
        build_weather_rule_stable_key,
    )
    assert build_daily_capacity_stable_key(_daily_semantic()) == _EXPECTED_DAILY_STABLE
    assert build_capacity_pool_definition_stable_key(
        _pool_bundle_semantic().definition
    ) == _EXPECTED_POOL_STABLE
    assert build_run_parameter_package_stable_key(_run_pkg_semantic()) == _EXPECTED_RUN_PKG_STABLE
    assert build_holiday_calendar_stable_key(_holiday_semantic()) == _EXPECTED_HOLIDAY_STABLE
    assert build_weather_rule_stable_key(_weather_semantic()) == _EXPECTED_WEATHER_STABLE
    assert build_initial_inventory_stable_key(
        _inv_bundle_semantic()
    ) == _EXPECTED_INV_STABLE
    assert build_mature_inventory_loss_stable_key(_loss_semantic()) == _EXPECTED_LOSS_STABLE
