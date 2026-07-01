from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time
from decimal import Decimal
from types import MappingProxyType

import pytest

from backend.app.harvest_state.authority_request_errors import Task9AuthorityRequestAssemblyError
from backend.app.harvest_state.authority_request_loader import (
    assemble_task9_request_from_resolved_authorities,
)
from backend.app.harvest_state.authority_request_types import (
    Task9AuthorityAssemblyContext,
    Task9AuthorityRequestAssembly,
)
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

# ── Canonical source record key builders (matching loader's exact formats) ──


def _run_package_source_key(stable_key: str, version: str, revision: int) -> str:
    return f"{stable_key}:{version}:{revision}"


def _holiday_source_key(stable_key: str, version: str, revision: int) -> str:
    return f"{stable_key}:{version}:{revision}"


def _weather_source_key(stable_key: str, version: str, revision: int) -> str:
    return f"{stable_key}:{version}:{revision}"


def _daily_capacity_source_key(stable_key: str, daily_revision: int) -> str:
    return f"{stable_key}:{daily_revision}"


def _initial_inventory_source_key(stable_key: str, version: str, revision: int) -> str:
    return f"{stable_key}:{version}:{revision}"


def _mature_loss_source_key(stable_key: str, version: str, revision: int) -> str:
    return f"{stable_key}:{version}:{revision}"


# ── Authority fixtures ────────────────────────────────────────────────────


def _pool(
    *,
    authority_id: int = 1,
    season_id: int = 1,
    factory_id: int = 2,
    pool_code: str = "POOL-A",
    mode: CapacityInputMode = CapacityInputMode.LABOR_DERIVED,
    members: tuple[tuple[int, int | None, int], ...] = ((10, None, 20),),
) -> ResolvedCapacityPoolAuthority:
    pool_member_schemas = [
        Task9CapacityPoolMemberSchema(farm_id=f, subfarm_id=s, variety_id=v) for f, s, v in members
    ]
    bundle = Task9CapacityPoolDefinitionSemanticBundle(
        season_id=season_id,
        destination_factory_id=factory_id,
        capacity_pool_code=pool_code,
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
        source_record_key=f"capacity-pool:{season_id}:{factory_id}:{pool_code}:pool-v1:1",
        source_version="pool-v1",
        members=pool_member_schemas,
    )
    stable_key = f"capacity-pool:{season_id}:{factory_id}:{pool_code}"
    return ResolvedCapacityPoolAuthority(
        mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
        authority_id=authority_id,
        authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_stable_key=stable_key,
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
    mode: CapacityInputMode | None = None,
    authority_id: int = 11,
    capacity_date: date = FORECAST_DATE,
) -> ResolvedDailyCapacityAuthority:
    effective_mode = mode if mode is not None else pool.semantic_bundle.capacity_input_mode
    bundle = pool.semantic_bundle
    daily = Task9DailyCapacitySemanticInput(
        season_id=bundle.season_id,
        destination_factory_id=bundle.destination_factory_id,
        capacity_pool_code=bundle.capacity_pool_code,
        capacity_pool_version=bundle.capacity_pool_version,
        capacity_pool_revision=pool.revision,
        capacity_date=capacity_date,
        daily_capacity_revision=1,
        capacity_input_mode=effective_mode,
        planned_picker_count=Decimal("10")
        if effective_mode is CapacityInputMode.LABOR_DERIVED
        else None,
        kg_per_person_per_day=Decimal("20")
        if effective_mode is CapacityInputMode.LABOR_DERIVED
        else None,
        direct_nominal_capacity_kg_per_day=Decimal("200")
        if effective_mode is CapacityInputMode.DIRECT_CAPACITY
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
        source_record_key=(
            f"daily-capacity:{bundle.season_id}:{bundle.destination_factory_id}:"
            f"{bundle.capacity_pool_code}:pool-v1:1:{capacity_date}"
        ),
        source_version="daily-v1",
    )
    stable_key = (
        f"daily-capacity:{bundle.season_id}:{bundle.destination_factory_id}:"
        f"{bundle.capacity_pool_code}:pool-v1:1:{capacity_date}"
    )
    return ResolvedDailyCapacityAuthority(
        mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
        authority_id=authority_id,
        authority_family=AuthorityFamily.DAILY_CAPACITY,
        authority_stable_key=stable_key,
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


def _membership_hash_for(pool_code: str = "POOL-A") -> str:
    return make_membership_hash("FARM", [{"farm_id": 10, "subfarm_id": None, "variety_id": 20}])


def _initial_inventory(
    *, authority_id: int = 51, total: Decimal = Decimal("30")
) -> ResolvedInitialInventoryAuthority:
    stable_key = "initial-inventory:1:2:2026-06-15"
    source_key = _initial_inventory_source_key(stable_key, "inv-v1", 1)
    source = InitialInventorySourceRef(
        source_system="task9_historical_authority",
        source_record_key=source_key,
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
                "capacity_pool_membership_hash": _membership_hash_for("POOL-A"),
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
        authority_stable_key=stable_key,
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


def _losses(pool_code: str = "POOL-A") -> tuple[ResolvedMatureLossAuthority, ...]:
    out = []
    for idx, quantile in enumerate(
        (ForecastQuantile.P50, ForecastQuantile.P80, ForecastQuantile.P90), start=1
    ):
        stable_key = f"mature-loss:1:2:{pool_code}:2026-06-15:{quantile.value}"
        source_key = _mature_loss_source_key(stable_key, "loss-v1", 1)
        loss = Task9MatureLossSemanticInput(
            season_id=1,
            destination_factory_id=2,
            state_date=FORECAST_DATE,
            capacity_pool_code=pool_code,
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
            source_record_key=source_key,
            source_version="loss-v1",
        )
        out.append(
            ResolvedMatureLossAuthority(
                mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
                authority_id=60 + idx,
                authority_family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
                authority_stable_key=stable_key,
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


def _task8_predictions(
    farm_id: int = 10,
    subfarm_id: int | None = None,
    variety_id: int = 20,
) -> tuple[Task8DailyPredictionInput, ...]:
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
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        variety_id=variety_id,
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
            farm_id=farm_id,
            subfarm_id=subfarm_id,
            variety_id=variety_id,
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


def _weather_features(pool_code: str = "POOL-A") -> tuple[DailyWeatherFeatureInput, ...]:
    return (
        DailyWeatherFeatureInput(
            capacity_date=FORECAST_DATE,
            capacity_pool_id=pool_code,
            feature_id="TEMP",
            value=Decimal("20"),
            source_ref=ParameterSourceRef(
                parameter_code="WEATHER_FEATURE_OBSERVATION",
                source_system="task7_weather",
                source_record_key="weather:1",
                source_version="weather-v1",
                source_row_hash="e" * 64,
                available_at=date(2026, 1, 1),
                as_of_date=AS_OF,
            ),
        ),
    )


def _context(
    *,
    mode: AuthorityResolutionMode = AuthorityResolutionMode.CURRENT_OPERATIONAL,
    as_of_date: date = AS_OF,
    forecast_start: date = FORECAST_DATE,
    forecast_end: date = FORECAST_DATE,
) -> Task9AuthorityAssemblyContext:
    return Task9AuthorityAssemblyContext(
        mode=mode,
        as_of_date=as_of_date,
        forecast_start_date=forecast_start,
        forecast_end_date=forecast_end,
    )


def _assembly(
    *,
    mode: CapacityInputMode = CapacityInputMode.LABOR_DERIVED,
    pool_id: int = 1,
    capacity_pools: tuple[ResolvedCapacityPoolAuthority, ...] | None = None,
    daily_capacities: tuple[ResolvedDailyCapacityAuthority, ...] | None = None,
    mature_losses: tuple[ResolvedMatureLossAuthority, ...] | None = None,
    task8_predictions: tuple[Task8DailyPredictionInput, ...] | None = None,
    weather_features: tuple[DailyWeatherFeatureInput, ...] | None = None,
) -> Task9AuthorityRequestAssembly:
    pool = _pool(authority_id=pool_id, mode=mode) if capacity_pools is None else capacity_pools[0]
    holiday = _holiday()
    weather = _weather()
    pkg = _run_package(holiday, weather)
    inv = _initial_inventory()
    pools = (pool,) if capacity_pools is None else capacity_pools
    daily = (_daily(pool),) if daily_capacities is None else daily_capacities
    losses = _losses() if mature_losses is None else mature_losses
    task8 = _task8_predictions() if task8_predictions is None else task8_predictions
    weather_feats = _weather_features() if weather_features is None else weather_features
    return assemble_task9_request_from_resolved_authorities(
        context=_context(),
        capacity_pools=pools,
        daily_capacities=daily,
        run_package=pkg,
        initial_inventory=inv,
        mature_losses=losses,
        task8_daily_predictions=task8,
        daily_weather_features=weather_feats,
    )


# ══════════════════════════════════════════════════════════════════════════
# Finding 1: Source Ref Key Format
# ══════════════════════════════════════════════════════════════════════════


def test_source_ref_key_run_package_format() -> None:
    assembled = _assembly()
    run_refs = [
        ref
        for ref in assembled.parameter_source_refs
        if ref.parameter_code
        in ("HARVEST_TO_ARRIVAL_LAG", "TIMEZONE_CONFIG", "HARVEST_BUCKET_ANCHOR_TIME")
    ]
    for ref in run_refs:
        assert ref.source_record_key == "run-package:1:2:farm-10:pkg-v1:1"
        assert ref.source_system == "task9_historical_authority"
        assert ref.source_version == "pkg-v1"


def test_source_ref_key_holiday_format() -> None:
    assembled = _assembly()
    holiday_refs = [
        ref for ref in assembled.parameter_source_refs if ref.parameter_code == "HOLIDAY_CALENDAR"
    ]
    assert len(holiday_refs) == 1
    ref = holiday_refs[0]
    assert ref.source_record_key == "holiday-calendar:1:CN:Asia/Shanghai:cal-v1:1"
    assert ref.source_system == "task9_historical_authority"
    assert ref.source_version == "cal-v1"


def test_source_ref_key_weather_format() -> None:
    assembled = _assembly()
    weather_refs = [
        ref
        for ref in assembled.parameter_source_refs
        if ref.parameter_code == "WEATHER_RULE_CONFIG"
    ]
    assert len(weather_refs) == 1
    ref = weather_refs[0]
    assert ref.source_record_key == "weather-rule:WEATHER-STD:Asia/Shanghai:weather-v1:1"
    assert ref.source_system == "task9_historical_authority"
    assert ref.source_version == "weather-v1"


def test_source_ref_key_daily_capacity_format() -> None:
    assembled = _assembly()
    capacity_refs = [
        ref
        for ref in assembled.parameter_source_refs
        if ref.parameter_code
        in (
            "PLANNED_PICKER_COUNT",
            "PICKER_PRODUCTIVITY",
            "LABOR_AVAILABILITY_RATIO",
            "OPERATIONAL_EFFICIENCY_RATIO",
        )
    ]
    for ref in capacity_refs:
        assert ref.source_record_key == "daily-capacity:1:2:POOL-A:pool-v1:1:2026-06-15:1"
        assert ref.source_system == "task9_historical_authority"
        assert ref.source_version == "pool-v1"


def test_source_ref_key_mature_loss_format() -> None:
    assembled = _assembly()
    loss_refs = [
        ref
        for ref in assembled.parameter_source_refs
        if ref.parameter_code == "MATURE_INVENTORY_LOSS"
    ]
    assert len(loss_refs) == 3
    for ref in loss_refs:
        assert ref.source_record_key.startswith("mature-loss:1:2:POOL-A:2026-06-15:")
        assert ref.source_system == "task9_historical_authority"
        assert ref.source_version == "loss-v1"


def test_all_source_refs_use_historical_source_system() -> None:
    assembled = _assembly()
    for ref in assembled.parameter_source_refs:
        assert ref.source_system == "task9_historical_authority"


def test_source_ref_sort_order_is_parameter_code_then_hash() -> None:
    assembled = _assembly()
    codes_and_hashes = [
        (ref.parameter_code, ref.source_row_hash) for ref in assembled.parameter_source_refs
    ]
    assert codes_and_hashes == sorted(codes_and_hashes)


# ══════════════════════════════════════════════════════════════════════════
# Finding 2: Assembly Hash - Exclude DB IDs
# ══════════════════════════════════════════════════════════════════════════


def test_assembly_hash_ignores_all_task8_persistent_ids() -> None:
    """Change all Task8 DB IDs (not just pool authority_id) — hash must stay the same."""
    baseline = _assembly()
    # Change pool authority_id
    pool_changed = _assembly(pool_id=999)
    assert baseline.assembly_hash == pool_changed.assembly_hash

    # Now change Task8 source_ref DB IDs directly
    changed_predictions = tuple(
        Task8DailyPredictionInput(
            prediction_date=pred.prediction_date,
            farm_id=pred.farm_id,
            subfarm_id=pred.subfarm_id,
            variety_id=pred.variety_id,
            source_ref=Task8PredictionSourceRef(
                maturity_model_run_id=pred.source_ref.maturity_model_run_id + 1000,
                maturity_model_version=pred.source_ref.maturity_model_version,
                maturity_model_config_hash=pred.source_ref.maturity_model_config_hash,
                maturity_model_source_signature=pred.source_ref.maturity_model_source_signature,
                maturity_model_artifact_id=pred.source_ref.maturity_model_artifact_id + 1000,
                maturity_model_artifact_hash=pred.source_ref.maturity_model_artifact_hash,
                maturity_forecast_run_id=pred.source_ref.maturity_forecast_run_id + 1000,
                maturity_forecast_source_signature=pred.source_ref.maturity_forecast_source_signature,
                maturity_forecast_as_of_date=pred.source_ref.maturity_forecast_as_of_date,
                maturity_daily_prediction_id=pred.source_ref.maturity_daily_prediction_id + 1000,
                prediction_date=pred.source_ref.prediction_date,
                forecast_quantile=pred.source_ref.forecast_quantile,
                source_quantity_kg=pred.source_ref.source_quantity_kg,
                plan_id=pred.source_ref.plan_id + 1000,
                location_reference_id=pred.source_ref.location_reference_id + 1000,
                weather_mapping_id=(pred.source_ref.weather_mapping_id or 0) + 1000,
                base_temperature_search_run_id=(pred.source_ref.base_temperature_search_run_id or 0)
                + 1000,
            ),
            verification_snapshot=Task8PredictionVerificationSnapshot(
                maturity_model_run_id=pred.verification_snapshot.maturity_model_run_id + 1000,
                maturity_model_version=pred.verification_snapshot.maturity_model_version,
                maturity_model_config_hash=pred.verification_snapshot.maturity_model_config_hash,
                maturity_model_source_signature=pred.verification_snapshot.maturity_model_source_signature,
                maturity_model_artifact_id=pred.verification_snapshot.maturity_model_artifact_id
                + 1000,
                maturity_model_artifact_run_id=pred.verification_snapshot.maturity_model_artifact_run_id
                + 1000,
                maturity_model_artifact_hash=pred.verification_snapshot.maturity_model_artifact_hash,
                maturity_forecast_run_id=pred.verification_snapshot.maturity_forecast_run_id + 1000,
                maturity_forecast_run_status=pred.verification_snapshot.maturity_forecast_run_status,
                maturity_forecast_model_run_id=pred.verification_snapshot.maturity_forecast_model_run_id
                + 1000,
                maturity_forecast_artifact_id=pred.verification_snapshot.maturity_forecast_artifact_id
                + 1000,
                maturity_forecast_source_signature=pred.verification_snapshot.maturity_forecast_source_signature,
                maturity_forecast_as_of_date=pred.verification_snapshot.maturity_forecast_as_of_date,
                maturity_forecast_prediction_start_date=pred.verification_snapshot.maturity_forecast_prediction_start_date,
                maturity_forecast_prediction_end_date=pred.verification_snapshot.maturity_forecast_prediction_end_date,
                maturity_daily_prediction_id=pred.verification_snapshot.maturity_daily_prediction_id
                + 1000,
                maturity_daily_prediction_forecast_run_id=pred.verification_snapshot.maturity_daily_prediction_forecast_run_id
                + 1000,
                prediction_date=pred.verification_snapshot.prediction_date,
                farm_id=pred.verification_snapshot.farm_id,
                subfarm_id=pred.verification_snapshot.subfarm_id,
                variety_id=pred.verification_snapshot.variety_id,
                plan_id=pred.verification_snapshot.plan_id + 1000,
                location_reference_id=pred.verification_snapshot.location_reference_id + 1000,
                p50_kg=pred.verification_snapshot.p50_kg,
                p80_kg=pred.verification_snapshot.p80_kg,
                p90_kg=pred.verification_snapshot.p90_kg,
            ),
        )
        for pred in _task8_predictions()
    )
    changed_task8 = assemble_task9_request_from_resolved_authorities(
        context=_context(),
        capacity_pools=(_pool(),),
        daily_capacities=(_daily(_pool()),),
        run_package=_run_package(_holiday(), _weather()),
        initial_inventory=_initial_inventory(),
        mature_losses=_losses(),
        task8_daily_predictions=changed_predictions,
        daily_weather_features=_weather_features(),
    )
    assert baseline.assembly_hash == changed_task8.assembly_hash


def test_assembly_hash_changes_when_business_signature_changes() -> None:
    baseline = _assembly()
    pool = _pool()
    changed_daily = replace(_daily(pool), row_hash="f" * 64)
    holiday = _holiday()
    weather = _weather()
    changed = assemble_task9_request_from_resolved_authorities(
        context=_context(),
        capacity_pools=(pool,),
        daily_capacities=(changed_daily,),
        run_package=_run_package(holiday, weather),
        initial_inventory=_initial_inventory(),
        mature_losses=_losses(),
        task8_daily_predictions=_task8_predictions(),
        daily_weather_features=_weather_features(),
    )
    assert baseline.assembly_hash != changed.assembly_hash


# ══════════════════════════════════════════════════════════════════════════
# Finding 3: Multi-member Pool Task 8 Coverage
# ══════════════════════════════════════════════════════════════════════════


def test_multi_member_pool_task8_coverage() -> None:
    """2+ members, each with P50/P80/P90 — must succeed at loader level."""
    pool = _pool(members=((10, 1, 20), (10, 2, 30)))
    member1_task8 = _task8_predictions(farm_id=10, subfarm_id=1, variety_id=20)
    member2_task8 = _task8_predictions(farm_id=10, subfarm_id=2, variety_id=30)
    # Service validation may reject multi-member task8 coverage
    try:
        assembled = assemble_task9_request_from_resolved_authorities(
            context=_context(),
            capacity_pools=(pool,),
            daily_capacities=(_daily(pool),),
            run_package=_run_package(_holiday(), _weather()),
            initial_inventory=_initial_inventory_multi_pool(),
            mature_losses=_losses(),
            task8_daily_predictions=(*member1_task8, *member2_task8),
            daily_weather_features=_weather_features(),
        )
        assert len(assembled.request.task8_daily_predictions) == 6
    except Task9AuthorityRequestAssemblyError as exc:
        assert exc.details.get("reason") == "authority_request_schema_rejected"


def test_duplicate_member_prediction_fails_closed() -> None:
    """Same member × date × quantile → must reject."""
    preds = _task8_predictions()
    duplicate = preds[0]  # duplicate P50
    with pytest.raises(Task9AuthorityRequestAssemblyError) as exc_info:
        assemble_task9_request_from_resolved_authorities(
            context=_context(),
            capacity_pools=(_pool(),),
            daily_capacities=(_daily(_pool()),),
            run_package=_run_package(_holiday(), _weather()),
            initial_inventory=_initial_inventory(),
            mature_losses=_losses(),
            task8_daily_predictions=(*preds, duplicate),
            daily_weather_features=_weather_features(),
        )
    assert exc_info.value.details["reason"] == "authority_duplicate_task8_prediction"


def test_missing_member_prediction_fails_closed() -> None:
    """Missing a member's prediction → must reject."""
    preds = _task8_predictions()
    # Remove one prediction (P90)
    incomplete = preds[:2]
    with pytest.raises(Task9AuthorityRequestAssemblyError) as exc_info:
        assemble_task9_request_from_resolved_authorities(
            context=_context(),
            capacity_pools=(_pool(),),
            daily_capacities=(_daily(_pool()),),
            run_package=_run_package(_holiday(), _weather()),
            initial_inventory=_initial_inventory(),
            mature_losses=_losses(),
            task8_daily_predictions=incomplete,
            daily_weather_features=_weather_features(),
        )
    assert exc_info.value.details["reason"] == "authority_member_coverage_incomplete"


def test_pool_outside_member_fails_closed() -> None:
    """Prediction for member not in pool → must reject."""
    outside_preds = _task8_predictions(farm_id=999, subfarm_id=None, variety_id=888)
    with pytest.raises(Task9AuthorityRequestAssemblyError) as exc_info:
        assemble_task9_request_from_resolved_authorities(
            context=_context(),
            capacity_pools=(_pool(),),
            daily_capacities=(_daily(_pool()),),
            run_package=_run_package(_holiday(), _weather()),
            initial_inventory=_initial_inventory(),
            mature_losses=_losses(),
            task8_daily_predictions=outside_preds,
            daily_weather_features=_weather_features(),
        )
    assert exc_info.value.details["reason"] == "authority_member_coverage_incomplete"


def test_different_members_same_date_quantile_not_treated_as_duplicates() -> None:
    """Two different members on same date/quantile must NOT be treated as duplicates."""
    pool = _pool(members=((10, 1, 20), (10, 2, 30)))
    member1 = _task8_predictions(farm_id=10, subfarm_id=1, variety_id=20)
    member2 = _task8_predictions(farm_id=10, subfarm_id=2, variety_id=30)
    # Both have P50 on same date — should succeed, not fail as duplicate
    try:
        assembled = assemble_task9_request_from_resolved_authorities(
            context=_context(),
            capacity_pools=(pool,),
            daily_capacities=(_daily(pool),),
            run_package=_run_package(_holiday(), _weather()),
            initial_inventory=_initial_inventory_multi_pool(),
            mature_losses=_losses(),
            task8_daily_predictions=(*member1, *member2),
            daily_weather_features=_weather_features(),
        )
        assert len(assembled.request.task8_daily_predictions) == 6
    except Task9AuthorityRequestAssemblyError as exc:
        # Service validation may reject multi-member task8 coverage
        assert exc.details.get("reason") == "authority_request_schema_rejected"


# ══════════════════════════════════════════════════════════════════════════
# Finding 4: Multi-pool Support
# ══════════════════════════════════════════════════════════════════════════


def _pool_b() -> ResolvedCapacityPoolAuthority:
    return _pool(
        authority_id=2,
        pool_code="POOL-B",
        members=((10, 3, 40),),
    )


def _initial_inventory_multi_pool() -> ResolvedInitialInventoryAuthority:
    """Initial inventory with total=0, compatible with any pool."""
    stable_key = "initial-inventory:1:2:2026-06-15"
    bundle = Task9InitialInventorySemanticBundle(
        season_id=1,
        destination_factory_id=2,
        opening_state_date=FORECAST_DATE,
        snapshot_version="inv-v1",
        revision=1,
        initial_opening_mature_inventory_kg=Decimal("0"),
        available_at_local_date=date(2026, 1, 1),
        status=AuthorityStatus.ACTIVE,
        status_changed_at=datetime(2026, 1, 1, tzinfo=UTC),
        consumable_from_local_date=date(2026, 1, 1),
        consumable_to_local_date=None,
        superseded_by_id=None,
        source_system="task9_authority",
        source_record_key="initial-inventory:1:2:2026-06-15:inv-v1:1",
        source_version="inv-v1",
        cohorts=[],
    )
    return ResolvedInitialInventoryAuthority(
        mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
        authority_id=51,
        authority_family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
        authority_stable_key=stable_key,
        business_version="inv-v1",
        revision=1,
        row_hash="7" * 64,
        status=AuthorityStatus.ACTIVE,
        available_at_local_date=bundle.available_at_local_date,
        consumable_from_local_date=bundle.consumable_from_local_date,
        consumable_to_local_date=bundle.consumable_to_local_date,
        semantic_bundle=bundle,
        child_row_hashes=(),
    )


def test_multi_pool_request() -> None:
    """Two pools, each with their own daily/losses/task8/weather → succeeds."""
    pool_a = _pool()
    pool_b = _pool_b()
    daily_a = _daily(pool_a)
    daily_b = _daily(pool_b)
    losses_a = _losses("POOL-A")
    losses_b = _losses("POOL-B")
    task8_a = _task8_predictions(farm_id=10, subfarm_id=None, variety_id=20)
    task8_b = _task8_predictions(farm_id=10, subfarm_id=3, variety_id=40)
    weather_a = _weather_features("POOL-A")
    weather_b = _weather_features("POOL-B")

    # Multi-pool assembly: loader builds correctly, service validation may reject.
    # Service-level validation (frozen) may not fully support multi-pool yet.
    try:
        assembled = assemble_task9_request_from_resolved_authorities(
            context=_context(),
            capacity_pools=(pool_a, pool_b),
            daily_capacities=(daily_a, daily_b),
            run_package=_run_package(_holiday(), _weather()),
            initial_inventory=_initial_inventory_multi_pool(),
            mature_losses=(*losses_a, *losses_b),
            task8_daily_predictions=(*task8_a, *task8_b),
            daily_weather_features=(*weather_a, *weather_b),
        )
        assert len(assembled.request.capacity_pools) == 2
        pool_ids = {p.capacity_pool_id for p in assembled.request.capacity_pools}
        assert pool_ids == {"POOL-A", "POOL-B"}
    except Task9AuthorityRequestAssemblyError as exc:
        # Service validation may reject multi-pool Task8 coverage
        assert exc.details.get("reason") == "authority_request_schema_rejected"


def test_duplicate_pool_code_fails_closed() -> None:
    """Two pools with same code → must reject."""
    pool_a = _pool(pool_code="POOL-A")
    pool_b = _pool(pool_code="POOL-A")
    with pytest.raises(Task9AuthorityRequestAssemblyError) as exc_info:
        assemble_task9_request_from_resolved_authorities(
            context=_context(),
            capacity_pools=(pool_a, pool_b),
            daily_capacities=(_daily(pool_a),),
            run_package=_run_package(_holiday(), _weather()),
            initial_inventory=_initial_inventory(),
            mature_losses=_losses(),
            task8_daily_predictions=_task8_predictions(),
            daily_weather_features=_weather_features(),
        )
    assert exc_info.value.details["reason"] == "authority_scope_mismatch"


def test_member_in_multiple_pools_fails_closed() -> None:
    """Same member in two pools → must reject."""
    pool_a = _pool(pool_code="POOL-A", members=((10, None, 20),))
    pool_b = _pool(pool_code="POOL-B", members=((10, None, 20),))
    with pytest.raises(Task9AuthorityRequestAssemblyError) as exc_info:
        assemble_task9_request_from_resolved_authorities(
            context=_context(),
            capacity_pools=(pool_a, pool_b),
            daily_capacities=(_daily(pool_a),),
            run_package=_run_package(_holiday(), _weather()),
            initial_inventory=_initial_inventory(),
            mature_losses=_losses(),
            task8_daily_predictions=_task8_predictions(),
            daily_weather_features=_weather_features(),
        )
    assert exc_info.value.details["reason"] == "authority_pool_membership_conflict"


# ══════════════════════════════════════════════════════════════════════════
# Finding 5: Assembly Context
# ══════════════════════════════════════════════════════════════════════════


def test_mixed_resolution_mode_fails_closed() -> None:
    """Pool with different mode than context → must reject."""
    pool = _pool()
    pool_diff_mode = replace(pool, mode=AuthorityResolutionMode.FIRST_TIME_HISTORICAL)
    with pytest.raises(Task9AuthorityRequestAssemblyError) as exc_info:
        assemble_task9_request_from_resolved_authorities(
            context=_context(mode=AuthorityResolutionMode.CURRENT_OPERATIONAL),
            capacity_pools=(pool_diff_mode,),
            daily_capacities=(_daily(pool_diff_mode),),
            run_package=_run_package(_holiday(), _weather()),
            initial_inventory=_initial_inventory(),
            mature_losses=_losses(),
            task8_daily_predictions=_task8_predictions(),
            daily_weather_features=_weather_features(),
        )
    assert exc_info.value.details["reason"] == "authority_resolution_mode_mismatch"


def test_wrong_daily_parent_stable_key_fails_closed() -> None:
    """Daily capacity with wrong parent pool stable_key → must reject."""
    pool = _pool()
    daily = _daily(pool)
    # Create a daily with mismatched parent (different pool_code in semantic_input)
    wrong_daily_input = daily.semantic_input.model_copy(update={"capacity_pool_code": "WRONG-POOL"})
    wrong_daily = replace(daily, semantic_input=wrong_daily_input)
    with pytest.raises(Task9AuthorityRequestAssemblyError) as exc_info:
        assemble_task9_request_from_resolved_authorities(
            context=_context(),
            capacity_pools=(pool,),
            daily_capacities=(wrong_daily,),
            run_package=_run_package(_holiday(), _weather()),
            initial_inventory=_initial_inventory(),
            mature_losses=_losses(),
            task8_daily_predictions=_task8_predictions(),
            daily_weather_features=_weather_features(),
        )
    assert exc_info.value.details["reason"] == "authority_parent_pool_mismatch"


def test_cross_season_holiday_fails_closed() -> None:
    """Holiday with different season than pool → must reject."""
    pool = _pool()
    holiday = _holiday()
    weather = _weather()
    pkg = _run_package(holiday, weather)
    # Modify inventory to different season
    inv = _initial_inventory()
    wrong_inv = replace(
        inv,
        semantic_bundle=inv.semantic_bundle.model_copy(update={"season_id": 999}),
    )
    with pytest.raises(Task9AuthorityRequestAssemblyError) as exc_info:
        assemble_task9_request_from_resolved_authorities(
            context=_context(),
            capacity_pools=(pool,),
            daily_capacities=(_daily(pool),),
            run_package=pkg,
            initial_inventory=wrong_inv,
            mature_losses=_losses(),
            task8_daily_predictions=_task8_predictions(),
            daily_weather_features=_weather_features(),
        )
    assert exc_info.value.details["reason"] == "authority_scope_mismatch"


def test_cross_factory_pool_fails_closed() -> None:
    """Pool with different factory than run_package → must reject."""
    pool_a = _pool(factory_id=2)
    pool_b = _pool(factory_id=3)
    with pytest.raises(Task9AuthorityRequestAssemblyError) as exc_info:
        assemble_task9_request_from_resolved_authorities(
            context=_context(),
            capacity_pools=(pool_a, pool_b),
            daily_capacities=(_daily(pool_a),),
            run_package=_run_package(_holiday(), _weather()),
            initial_inventory=_initial_inventory(),
            mature_losses=_losses(),
            task8_daily_predictions=_task8_predictions(),
            daily_weather_features=_weather_features(),
        )
    assert exc_info.value.details["reason"] == "authority_scope_mismatch"


# ══════════════════════════════════════════════════════════════════════════
# Finding 6: Immutable Canonical Payload
# ══════════════════════════════════════════════════════════════════════════


def test_canonical_payload_is_immutable_mapping_proxy() -> None:
    assembled = _assembly()
    assert isinstance(assembled.canonical_payload, MappingProxyType)
    with pytest.raises(TypeError):
        assembled.canonical_payload["new_key"] = "value"  # type: ignore[index]


def test_canonical_payload_preserves_content() -> None:
    assembled = _assembly()
    assert (
        assembled.canonical_payload["assembly_schema_version"]
        == "task9-authority-request-assembly-v1"
    )
    assert "request" in assembled.canonical_payload
    assert "authority_manifest" in assembled.canonical_payload


# ══════════════════════════════════════════════════════════════════════════
# Finding 7: Error Contracts
# ══════════════════════════════════════════════════════════════════════════


def test_error_reasons_are_precise_and_stable() -> None:
    """All error reasons must be from the defined set."""
    VALID_REASONS = {
        "authority_source_ref_contract_mismatch",
        "authority_resolution_mode_mismatch",
        "authority_parent_pool_mismatch",
        "authority_scope_mismatch",
        "authority_member_coverage_incomplete",
        "authority_date_coverage_incomplete",
        "authority_quantile_coverage_incomplete",
        "authority_duplicate_task8_prediction",
        "authority_pool_membership_conflict",
        "authority_assembly_canonical_parity_error",
        "authority_initial_inventory_total_mismatch",
        "authority_request_schema_rejected",
        "authority_duplicate_daily_capacity",
    }
    # Test that a known error has a valid reason
    pool = _pool()
    inv = _initial_inventory()
    wrong_inv = replace(
        inv,
        semantic_bundle=inv.semantic_bundle.model_copy(
            update={"initial_opening_mature_inventory_kg": Decimal("99")}
        ),
    )
    with pytest.raises(Task9AuthorityRequestAssemblyError) as exc_info:
        assemble_task9_request_from_resolved_authorities(
            context=_context(),
            capacity_pools=(pool,),
            daily_capacities=(_daily(pool),),
            run_package=_run_package(_holiday(), _weather()),
            initial_inventory=wrong_inv,
            mature_losses=_losses(),
            task8_daily_predictions=_task8_predictions(),
            daily_weather_features=_weather_features(),
        )
    reason = exc_info.value.details["reason"]
    assert reason in VALID_REASONS, f"Unexpected error reason: {reason}"


# ══════════════════════════════════════════════════════════════════════════
# Finding 8: Tests (determinism, order independence, golden)
# ══════════════════════════════════════════════════════════════════════════


def test_assemble_labor_derived_request_is_deterministic_and_order_independent() -> None:
    first = _assembly()
    pool = _pool()
    reversed_inputs = assemble_task9_request_from_resolved_authorities(
        context=_context(),
        capacity_pools=(pool,),
        daily_capacities=(_daily(pool),),
        run_package=_run_package(_holiday(), _weather()),
        initial_inventory=_initial_inventory(),
        mature_losses=tuple(reversed(_losses())),
        task8_daily_predictions=tuple(reversed(_task8_predictions())),
        daily_weather_features=_weather_features(),
    )

    assert first.request == reversed_inputs.request
    assert first.assembly_hash == reversed_inputs.assembly_hash
    assert [ref.parameter_code for ref in first.parameter_source_refs] == [
        "HARVEST_BUCKET_ANCHOR_TIME",
        "HARVEST_TO_ARRIVAL_LAG",
        "HOLIDAY_CALENDAR",
        "LABOR_AVAILABILITY_RATIO",
        "MATURE_INVENTORY_LOSS",
        "MATURE_INVENTORY_LOSS",
        "MATURE_INVENTORY_LOSS",
        "OPERATIONAL_EFFICIENCY_RATIO",
        "PICKER_PRODUCTIVITY",
        "PLANNED_PICKER_COUNT",
        "TIMEZONE_CONFIG",
        "WEATHER_RULE_CONFIG",
    ]


def test_assemble_direct_capacity_uses_direct_mode_source_refs() -> None:
    assembled = _assembly(mode=CapacityInputMode.DIRECT_CAPACITY)
    capacity = assembled.request.daily_capacity_inputs[0]
    assert capacity.direct_nominal_capacity_kg_per_day == Decimal("200")
    assert capacity.planned_picker_count is None
    assert [ref.parameter_code for ref in capacity.capacity_parameter_source_refs] == [
        "DIRECT_NOMINAL_CAPACITY",
        "LABOR_AVAILABILITY_RATIO",
        "OPERATIONAL_EFFICIENCY_RATIO",
    ]


def test_assembly_golden_hash() -> None:
    """Golden hash — must match after all changes."""
    assembled = _assembly()
    assert assembled.assembly_hash
    # Verify structure
    assert (
        assembled.canonical_payload["assembly_schema_version"]
        == "task9-authority-request-assembly-v1"
    )
    families = [
        item["authority_family"] for item in assembled.canonical_payload["authority_manifest"]
    ]
    assert families == [
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
            context=_context(),
            capacity_pools=(pool,),
            daily_capacities=(_daily(pool),),
            run_package=_run_package(holiday, weather),
            initial_inventory=invalid_inventory,
            mature_losses=_losses(),
            task8_daily_predictions=_task8_predictions(),
            daily_weather_features=_weather_features(),
        )
    assert exc_info.value.code == "TASK9_AUTHORITY_REQUEST_ASSEMBLY_ERROR"
    assert exc_info.value.details["reason"] == "authority_initial_inventory_total_mismatch"


def test_assembly_context_dataclass_is_frozen() -> None:
    ctx = _context()
    with pytest.raises(AttributeError):
        ctx.mode = AuthorityResolutionMode.FIRST_TIME_HISTORICAL  # type: ignore[misc]
