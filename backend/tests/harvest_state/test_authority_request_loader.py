from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest

from backend.app.harvest_state.authority_request_errors import Task9AuthorityRequestAssemblyError
from backend.app.harvest_state.authority_request_loader import (
    assemble_task9_request_from_resolved_authorities,
)
from backend.app.harvest_state.authority_request_types import Task9AuthorityRequestAssembly
from backend.app.harvest_state.authority_resolution_types import (
    AuthorityResolutionMode,
    ResolvedCapacityPoolAuthority,
    ResolvedDailyCapacityAuthority,
    ResolvedHolidayCalendarAuthority,
    ResolvedInitialInventoryAuthority,
    ResolvedMatureLossAuthority,
    ResolvedRunParameterPackageAuthority,
    ResolvedWeatherRuleAuthority,
)
from backend.app.harvest_state.authority_schemas import (
    Task9CapacityPoolDefinitionSemanticBundle,
    Task9CapacityPoolMemberSchema,
    Task9DailyCapacitySemanticInput,
    Task9HolidayCalendarDateSchema,
    Task9HolidayCalendarSemanticBundle,
    Task9InitialInventoryCohortSchema,
    Task9InitialInventorySemanticBundle,
    Task9MatureLossSemanticInput,
    Task9RunParameterPackageSemanticInput,
    Task9WeatherRuleSemanticInput,
)
from backend.app.harvest_state.canonical import (
    make_holiday_calendar_hash,
    make_membership_hash,
    make_stable_cohort_key,
    make_weather_rule_config_hash,
)
from backend.app.harvest_state.enums import (
    AuthorityFamily,
    AuthorityStatus,
    CapacityInputMode,
    CapacityPoolGrain,
    ForecastQuantile,
    ParameterCode,
    WeatherCombinationMethod,
)
from backend.app.harvest_state.schemas import (
    DailyWeatherFeatureInput,
    InitialInventorySourceRef,
    ParameterSourceRef,
    Task8DailyPredictionInput,
    Task8PredictionSourceRef,
    Task8PredictionVerificationSnapshot,
    WeatherFeatureBand,
    WeatherFeatureRule,
)

AS_OF = date(2026, 6, 1)
FORECAST_DATE = date(2026, 6, 15)
ROW = "a" * 64


def _authority_source_record_key(
    family: AuthorityFamily,
    stable_key: str,
    business_version: str,
    revision: int,
) -> str:
    return f"{family.value}:{stable_key}:{business_version}:{revision}"


def _pool(
    *, authority_id: int = 1, mode: CapacityInputMode = CapacityInputMode.LABOR_DERIVED
) -> ResolvedCapacityPoolAuthority:
    bundle = Task9CapacityPoolDefinitionSemanticBundle(
        season_id=1,
        destination_factory_id=2,
        capacity_pool_code="POOL-A",
        capacity_pool_grain=CapacityPoolGrain.FARM,
        capacity_input_mode=mode,
        capacity_pool_version="pool-v1",
        revision=1,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        available_at_local_date=date(2026, 1, 1),
        status=AuthorityStatus.ACTIVE,
        status_changed_at=datetime(2026, 1, 1, tzinfo=UTC),
        consumable_from_local_date=date(2026, 1, 1),
        consumable_to_local_date=None,
        superseded_by_id=None,
        source_system="task9_authority",
        source_record_key="capacity-pool:1:2:POOL-A:pool-v1:1",
        source_version="pool-v1",
        members=[Task9CapacityPoolMemberSchema(farm_id=10, subfarm_id=None, variety_id=20)],
    )
    return ResolvedCapacityPoolAuthority(
        mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
        authority_id=authority_id,
        authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_stable_key="capacity-pool:1:2:POOL-A",
        business_version="pool-v1",
        revision=1,
        row_hash="1" * 64,
        status=AuthorityStatus.ACTIVE,
        available_at_local_date=bundle.available_at_local_date,
        consumable_from_local_date=bundle.consumable_from_local_date,
        consumable_to_local_date=bundle.consumable_to_local_date,
        semantic_bundle=bundle,
        child_row_hashes=("2" * 64,),
    )


def _daily(
    pool: ResolvedCapacityPoolAuthority,
    *,
    mode: CapacityInputMode = CapacityInputMode.LABOR_DERIVED,
    authority_id: int = 11,
) -> ResolvedDailyCapacityAuthority:
    daily = Task9DailyCapacitySemanticInput(
        season_id=1,
        destination_factory_id=2,
        capacity_pool_code="POOL-A",
        capacity_pool_version="pool-v1",
        capacity_pool_revision=1,
        capacity_date=FORECAST_DATE,
        daily_capacity_revision=1,
        capacity_input_mode=mode,
        planned_picker_count=Decimal("10") if mode is CapacityInputMode.LABOR_DERIVED else None,
        kg_per_person_per_day=Decimal("20") if mode is CapacityInputMode.LABOR_DERIVED else None,
        direct_nominal_capacity_kg_per_day=Decimal("200")
        if mode is CapacityInputMode.DIRECT_CAPACITY
        else None,
        labor_availability_ratio=Decimal("0.8"),
        operational_efficiency_ratio=Decimal("0.9"),
        available_at_local_date=date(2026, 1, 1),
        status=AuthorityStatus.ACTIVE,
        status_changed_at=datetime(2026, 1, 1, tzinfo=UTC),
        consumable_from_local_date=date(2026, 1, 1),
        consumable_to_local_date=None,
        superseded_by_id=None,
        source_system="task9_authority",
        source_record_key="daily-capacity:1:2:POOL-A:pool-v1:1:2026-06-15:1",
        source_version="daily-v1",
    )
    return ResolvedDailyCapacityAuthority(
        mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
        authority_id=authority_id,
        authority_family=AuthorityFamily.DAILY_CAPACITY,
        authority_stable_key="daily-capacity:1:2:POOL-A:pool-v1:1:2026-06-15",
        business_version="pool-v1",
        revision=1,
        row_hash="3" * 64,
        status=AuthorityStatus.ACTIVE,
        available_at_local_date=daily.available_at_local_date,
        consumable_from_local_date=daily.consumable_from_local_date,
        consumable_to_local_date=daily.consumable_to_local_date,
        semantic_input=daily,
        parent_pool=pool,
    )


def _holiday() -> ResolvedHolidayCalendarAuthority:
    dates = [
        Task9HolidayCalendarDateSchema(
            holiday_date=date(2026, 1, 1), holiday_code="NY", holiday_name="New Year"
        )
    ]
    bundle = Task9HolidayCalendarSemanticBundle(
        season_id=1,
        calendar_code="CN",
        calendar_version="cal-v1",
        revision=1,
        calendar_hash=make_holiday_calendar_hash(
            holiday_calendar_version="cal-v1", holiday_dates=[date(2026, 1, 1)]
        ),
        region_scope=None,
        lifecycle_timezone_name="Asia/Shanghai",
        available_at_local_date=date(2026, 1, 1),
        status=AuthorityStatus.ACTIVE,
        status_changed_at=datetime(2026, 1, 1, tzinfo=UTC),
        consumable_from_local_date=date(2026, 1, 1),
        consumable_to_local_date=None,
        superseded_by_id=None,
        source_system="task9_authority",
        source_record_key="holiday-calendar:1:CN:Asia/Shanghai:cal-v1:1",
        source_version="cal-v1",
        dates=dates,
    )
    return ResolvedHolidayCalendarAuthority(
        mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
        authority_id=21,
        authority_family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_stable_key="holiday-calendar:1:CN:Asia/Shanghai",
        business_version="cal-v1",
        revision=1,
        row_hash="4" * 64,
        status=AuthorityStatus.ACTIVE,
        available_at_local_date=bundle.available_at_local_date,
        consumable_from_local_date=bundle.consumable_from_local_date,
        consumable_to_local_date=bundle.consumable_to_local_date,
        semantic_bundle=bundle,
    )


def _weather() -> ResolvedWeatherRuleAuthority:
    config_payload = {
        "version": "weather-v1",
        "required_feature_ids": ["TEMP"],
        "feature_rules": [
            {
                "feature_id": "TEMP",
                "bands": [
                    {
                        "lower_bound": "0",
                        "lower_inclusive": True,
                        "upper_bound": "30",
                        "upper_inclusive": False,
                        "multiplier": "1",
                    }
                ],
            }
        ],
        "combination_method": "MULTIPLY",
        "minimum_ratio": "0",
        "maximum_ratio": "1",
        "missing_feature_policy": "BLOCK",
    }
    weather = Task9WeatherRuleSemanticInput(
        rule_code="WEATHER-STD",
        rule_version="weather-v1",
        revision=1,
        lifecycle_timezone_name="Asia/Shanghai",
        combination_method=WeatherCombinationMethod.MULTIPLY,
        minimum_ratio=Decimal("0"),
        maximum_ratio=Decimal("1"),
        required_feature_ids=["TEMP"],
        feature_rules=[
            WeatherFeatureRule(
                feature_id="TEMP",
                bands=[
                    WeatherFeatureBand(
                        lower_bound=Decimal("0"),
                        lower_inclusive=True,
                        upper_bound=Decimal("30"),
                        upper_inclusive=False,
                        multiplier=Decimal("1"),
                    )
                ],
            )
        ],
        missing_feature_policy="BLOCK",
        config_hash=make_weather_rule_config_hash(config_payload),
        effective_from=date(2026, 1, 1),
        effective_to=None,
        available_at_local_date=date(2026, 1, 1),
        status=AuthorityStatus.ACTIVE,
        status_changed_at=datetime(2026, 1, 1, tzinfo=UTC),
        consumable_from_local_date=date(2026, 1, 1),
        consumable_to_local_date=None,
        superseded_by_id=None,
        source_system="task9_authority",
        source_record_key="weather-rule:WEATHER-STD:Asia/Shanghai:weather-v1:1",
        source_version="weather-v1",
    )
    return ResolvedWeatherRuleAuthority(
        mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
        authority_id=31,
        authority_family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_stable_key="weather-rule:WEATHER-STD:Asia/Shanghai",
        business_version="weather-v1",
        revision=1,
        row_hash="5" * 64,
        status=AuthorityStatus.ACTIVE,
        available_at_local_date=weather.available_at_local_date,
        consumable_from_local_date=weather.consumable_from_local_date,
        consumable_to_local_date=weather.consumable_to_local_date,
        semantic_input=weather,
    )


def _run_package(
    holiday: ResolvedHolidayCalendarAuthority, weather: ResolvedWeatherRuleAuthority
) -> ResolvedRunParameterPackageAuthority:
    pkg = Task9RunParameterPackageSemanticInput(
        season_id=1,
        destination_factory_id=2,
        farm_scope_key="farm-10",
        farm_timezone="Asia/Shanghai",
        destination_factory_timezone="Asia/Shanghai",
        harvest_bucket_anchor_local_time=time(6, 0),
        harvest_to_arrival_lag_days=1,
        package_version="pkg-v1",
        revision=1,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        available_at_local_date=date(2026, 1, 1),
        status=AuthorityStatus.ACTIVE,
        status_changed_at=datetime(2026, 1, 1, tzinfo=UTC),
        consumable_from_local_date=date(2026, 1, 1),
        consumable_to_local_date=None,
        superseded_by_id=None,
        source_system="task9_authority",
        source_record_key="run-package:1:2:farm-10:pkg-v1:1",
        source_version="pkg-v1",
    )
    return ResolvedRunParameterPackageAuthority(
        mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
        authority_id=41,
        authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        authority_stable_key="run-package:1:2:farm-10",
        business_version="pkg-v1",
        revision=1,
        row_hash="6" * 64,
        status=AuthorityStatus.ACTIVE,
        available_at_local_date=pkg.available_at_local_date,
        consumable_from_local_date=pkg.consumable_from_local_date,
        consumable_to_local_date=pkg.consumable_to_local_date,
        semantic_input=pkg,
        holiday_calendar=holiday,
        weather_rule=weather,
    )


def _membership_hash() -> str:
    return make_membership_hash("FARM", [{"farm_id": 10, "subfarm_id": None, "variety_id": 20}])


def _initial_inventory(
    *, authority_id: int = 51, total: Decimal = Decimal("30")
) -> ResolvedInitialInventoryAuthority:
    source = InitialInventorySourceRef(
        source_system="task9_authority",
        source_record_key=_authority_source_record_key(
            AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
            "initial-inventory:1:2:2026-06-15",
            "inv-v1",
            1,
        ),
        source_version="inv-v1",
        source_row_hash="7" * 64,
        available_at=date(2026, 1, 1),
        as_of_date=AS_OF,
    )
    cohorts = []
    for quantile, qty in [
        (ForecastQuantile.P50, Decimal("10")),
        (ForecastQuantile.P80, Decimal("10")),
        (ForecastQuantile.P90, Decimal("10")),
    ]:
        key = make_stable_cohort_key(
            {
                "schema_version": "task9a-cohort-key-v1",
                "source_ref_type": "INITIAL_INVENTORY_SNAPSHOT",
                "source_system": source.source_system,
                "source_record_key": source.source_record_key,
                "source_version": source.source_version,
                "source_row_hash": source.source_row_hash,
                "cohort_date": FORECAST_DATE,
                "forecast_quantile": quantile,
                "farm_id": 10,
                "subfarm_id": None,
                "variety_id": 20,
                "capacity_pool_id": "POOL-A",
                "capacity_pool_membership_hash": _membership_hash(),
                "destination_factory_id": 2,
            }
        )
        cohorts.append(
            Task9InitialInventoryCohortSchema(
                stable_cohort_key=key,
                forecast_quantile=quantile,
                cohort_date=FORECAST_DATE,
                farm_id=10,
                subfarm_id=None,
                variety_id=20,
                remaining_quantity_kg=qty,
            )
        )
    bundle = Task9InitialInventorySemanticBundle(
        season_id=1,
        destination_factory_id=2,
        opening_state_date=FORECAST_DATE,
        snapshot_version="inv-v1",
        revision=1,
        initial_opening_mature_inventory_kg=total,
        available_at_local_date=date(2026, 1, 1),
        status=AuthorityStatus.ACTIVE,
        status_changed_at=datetime(2026, 1, 1, tzinfo=UTC),
        consumable_from_local_date=date(2026, 1, 1),
        consumable_to_local_date=None,
        superseded_by_id=None,
        source_system="task9_authority",
        source_record_key="initial-inventory:1:2:2026-06-15:inv-v1:1",
        source_version="inv-v1",
        cohorts=cohorts,
    )
    return ResolvedInitialInventoryAuthority(
        mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
        authority_id=authority_id,
        authority_family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
        authority_stable_key="initial-inventory:1:2:2026-06-15",
        business_version="inv-v1",
        revision=1,
        row_hash="7" * 64,
        status=AuthorityStatus.ACTIVE,
        available_at_local_date=bundle.available_at_local_date,
        consumable_from_local_date=bundle.consumable_from_local_date,
        consumable_to_local_date=bundle.consumable_to_local_date,
        semantic_bundle=bundle,
        child_row_hashes=("8" * 64, "9" * 64, "b" * 64),
    )


def _losses() -> tuple[ResolvedMatureLossAuthority, ...]:
    out = []
    for idx, quantile in enumerate(
        (ForecastQuantile.P50, ForecastQuantile.P80, ForecastQuantile.P90), start=1
    ):
        loss = Task9MatureLossSemanticInput(
            season_id=1,
            destination_factory_id=2,
            state_date=FORECAST_DATE,
            capacity_pool_code="POOL-A",
            forecast_quantile=quantile,
            loss_version="loss-v1",
            revision=1,
            mature_inventory_loss_quantity_kg=Decimal("1"),
            available_at_local_date=date(2026, 1, 1),
            status=AuthorityStatus.ACTIVE,
            status_changed_at=datetime(2026, 1, 1, tzinfo=UTC),
            consumable_from_local_date=date(2026, 1, 1),
            consumable_to_local_date=None,
            superseded_by_id=None,
            source_system="task9_authority",
            source_record_key=f"mature-loss:1:2:POOL-A:2026-06-15:{quantile.value}:loss-v1:1",
            source_version="loss-v1",
        )
        out.append(
            ResolvedMatureLossAuthority(
                mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
                authority_id=60 + idx,
                authority_family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
                authority_stable_key=f"mature-loss:1:2:POOL-A:2026-06-15:{quantile.value}",
                business_version="loss-v1",
                revision=1,
                row_hash=f"{idx}" * 64,
                status=AuthorityStatus.ACTIVE,
                available_at_local_date=loss.available_at_local_date,
                consumable_from_local_date=loss.consumable_from_local_date,
                consumable_to_local_date=loss.consumable_to_local_date,
                semantic_input=loss,
            )
        )
    return tuple(out)


def _task8_predictions() -> tuple[Task8DailyPredictionInput, ...]:
    verification = Task8PredictionVerificationSnapshot(
        maturity_model_run_id=1,
        maturity_model_version="maturity-v1",
        maturity_model_config_hash="c" * 64,
        maturity_model_source_signature="model-source",
        maturity_model_artifact_id=2,
        maturity_model_artifact_run_id=1,
        maturity_model_artifact_hash="d" * 64,
        maturity_forecast_run_id=3,
        maturity_forecast_run_status="completed",
        maturity_forecast_model_run_id=1,
        maturity_forecast_artifact_id=2,
        maturity_forecast_source_signature="forecast-source",
        maturity_forecast_as_of_date=AS_OF,
        maturity_forecast_prediction_start_date=FORECAST_DATE,
        maturity_forecast_prediction_end_date=FORECAST_DATE,
        maturity_daily_prediction_id=4,
        maturity_daily_prediction_forecast_run_id=3,
        prediction_date=FORECAST_DATE,
        farm_id=10,
        subfarm_id=None,
        variety_id=20,
        plan_id=5,
        location_reference_id=6,
        p50_kg=Decimal("10"),
        p80_kg=Decimal("20"),
        p90_kg=Decimal("30"),
    )
    quantities = {
        ForecastQuantile.P50: Decimal("10"),
        ForecastQuantile.P80: Decimal("20"),
        ForecastQuantile.P90: Decimal("30"),
    }
    return tuple(
        Task8DailyPredictionInput(
            prediction_date=FORECAST_DATE,
            farm_id=10,
            subfarm_id=None,
            variety_id=20,
            source_ref=Task8PredictionSourceRef(
                maturity_model_run_id=1,
                maturity_model_version="maturity-v1",
                maturity_model_config_hash="c" * 64,
                maturity_model_source_signature="model-source",
                maturity_model_artifact_id=2,
                maturity_model_artifact_hash="d" * 64,
                maturity_forecast_run_id=3,
                maturity_forecast_source_signature="forecast-source",
                maturity_forecast_as_of_date=AS_OF,
                maturity_daily_prediction_id=4,
                prediction_date=FORECAST_DATE,
                forecast_quantile=q,
                source_quantity_kg=qty,
                plan_id=5,
                location_reference_id=6,
                weather_mapping_id=7,
                base_temperature_search_run_id=8,
            ),
            verification_snapshot=verification,
        )
        for q, qty in quantities.items()
    )


def _weather_features() -> tuple[DailyWeatherFeatureInput, ...]:
    return (
        DailyWeatherFeatureInput(
            capacity_date=FORECAST_DATE,
            capacity_pool_id="POOL-A",
            feature_id="TEMP",
            value=Decimal("20"),
            source_ref=ParameterSourceRef(
                parameter_code=ParameterCode.WEATHER_FEATURE_OBSERVATION,
                source_system="task7_weather",
                source_record_key="weather:1",
                source_version="weather-v1",
                source_row_hash="e" * 64,
                available_at=date(2026, 1, 1),
                as_of_date=AS_OF,
            ),
        ),
    )


def _assembly(
    *, mode: CapacityInputMode = CapacityInputMode.LABOR_DERIVED, pool_id: int = 1
) -> Task9AuthorityRequestAssembly:
    pool = _pool(authority_id=pool_id, mode=mode)
    holiday = _holiday()
    weather = _weather()
    return assemble_task9_request_from_resolved_authorities(
        as_of_date=AS_OF,
        forecast_start_date=FORECAST_DATE,
        forecast_end_date=FORECAST_DATE,
        capacity_pool=pool,
        daily_capacities=(_daily(pool, mode=mode),),
        run_package=_run_package(holiday, weather),
        initial_inventory=_initial_inventory(),
        mature_losses=_losses(),
        task8_daily_predictions=_task8_predictions(),
        daily_weather_features=_weather_features(),
    )


def test_assemble_labor_derived_request_is_deterministic_and_order_independent() -> None:
    first = _assembly()
    pool = _pool()
    holiday = _holiday()
    weather = _weather()
    reversed_inputs = assemble_task9_request_from_resolved_authorities(
        as_of_date=AS_OF,
        forecast_start_date=FORECAST_DATE,
        forecast_end_date=FORECAST_DATE,
        capacity_pool=pool,
        daily_capacities=(_daily(pool),),
        run_package=_run_package(holiday, weather),
        initial_inventory=_initial_inventory(),
        mature_losses=tuple(reversed(_losses())),
        task8_daily_predictions=tuple(reversed(_task8_predictions())),
        daily_weather_features=_weather_features(),
    )

    assert first.request == reversed_inputs.request
    assert first.assembly_hash == reversed_inputs.assembly_hash
    assert [ref.parameter_code for ref in first.parameter_source_refs] == [
        ParameterCode.HOLIDAY_CALENDAR,
        ParameterCode.WEATHER_RULE_CONFIG,
        ParameterCode.HARVEST_TO_ARRIVAL_LAG,
        ParameterCode.TIMEZONE_CONFIG,
        ParameterCode.HARVEST_BUCKET_ANCHOR_TIME,
        ParameterCode.PLANNED_PICKER_COUNT,
        ParameterCode.PICKER_PRODUCTIVITY,
        ParameterCode.LABOR_AVAILABILITY_RATIO,
        ParameterCode.OPERATIONAL_EFFICIENCY_RATIO,
        ParameterCode.MATURE_INVENTORY_LOSS,
        ParameterCode.MATURE_INVENTORY_LOSS,
        ParameterCode.MATURE_INVENTORY_LOSS,
    ]


def test_assemble_direct_capacity_uses_direct_mode_source_refs() -> None:
    assembled = _assembly(mode=CapacityInputMode.DIRECT_CAPACITY)
    capacity = assembled.request.daily_capacity_inputs[0]
    assert capacity.direct_nominal_capacity_kg_per_day == Decimal("200")
    assert capacity.planned_picker_count is None
    assert [ref.parameter_code for ref in capacity.capacity_parameter_source_refs] == [
        ParameterCode.DIRECT_NOMINAL_CAPACITY,
        ParameterCode.LABOR_AVAILABILITY_RATIO,
        ParameterCode.OPERATIONAL_EFFICIENCY_RATIO,
    ]


def test_assembly_hash_ignores_persistent_database_ids() -> None:
    assert _assembly(pool_id=1).assembly_hash == _assembly(pool_id=999).assembly_hash


def test_assembly_hash_changes_when_business_hash_changes() -> None:
    baseline = _assembly()
    pool = _pool()
    changed_daily = replace(_daily(pool), row_hash="f" * 64)
    holiday = _holiday()
    weather = _weather()
    changed = assemble_task9_request_from_resolved_authorities(
        as_of_date=AS_OF,
        forecast_start_date=FORECAST_DATE,
        forecast_end_date=FORECAST_DATE,
        capacity_pool=pool,
        daily_capacities=(changed_daily,),
        run_package=_run_package(holiday, weather),
        initial_inventory=_initial_inventory(),
        mature_losses=_losses(),
        task8_daily_predictions=_task8_predictions(),
        daily_weather_features=_weather_features(),
    )
    assert baseline.assembly_hash != changed.assembly_hash


def test_assembly_golden_hash_and_payload_shape() -> None:
    assembled = _assembly()

    assert (
        assembled.assembly_hash
        == "f47a542a50ec73164c36f44034e1e2e99a97c3fb7f351b6d99ce84dd8bb5a53c"
    )
    assert (
        assembled.canonical_payload["assembly_schema_version"]
        == "task9-authority-request-assembly-v1"
    )
    assert [
        item["authority_family"] for item in assembled.canonical_payload["authority_manifest"]
    ] == [
        "capacity_pool_definition",
        "daily_capacity",
        "holiday_calendar_version",
        "initial_inventory_snapshot",
        "mature_inventory_loss_authority",
        "mature_inventory_loss_authority",
        "mature_inventory_loss_authority",
        "run_parameter_package",
        "weather_rule_config_version",
    ]


def test_initial_inventory_total_mismatch_fails_closed() -> None:
    pool = _pool()
    holiday = _holiday()
    weather = _weather()
    inventory = _initial_inventory()
    invalid_inventory = replace(
        inventory,
        semantic_bundle=inventory.semantic_bundle.model_copy(
            update={"initial_opening_mature_inventory_kg": Decimal("99")}
        ),
    )
    with pytest.raises(Task9AuthorityRequestAssemblyError) as exc_info:
        assemble_task9_request_from_resolved_authorities(
            as_of_date=AS_OF,
            forecast_start_date=FORECAST_DATE,
            forecast_end_date=FORECAST_DATE,
            capacity_pool=pool,
            daily_capacities=(_daily(pool),),
            run_package=_run_package(holiday, weather),
            initial_inventory=invalid_inventory,
            mature_losses=_losses(),
            task8_daily_predictions=_task8_predictions(),
            daily_weather_features=_weather_features(),
        )
    assert exc_info.value.code == "TASK9_AUTHORITY_REQUEST_ASSEMBLY_ERROR"
    assert exc_info.value.details["reason"] == "authority_initial_inventory_total_mismatch"
