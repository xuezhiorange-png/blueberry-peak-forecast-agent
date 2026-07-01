# ruff: noqa: E501
from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from types import MappingProxyType

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

if not os.environ.get("RUN_POSTGRES_INTEGRATION"):
    pytest.skip("RUN_POSTGRES_INTEGRATION not set", allow_module_level=True)

from backend.app.db.session import AsyncSessionMaker
from backend.app.harvest_state.authority_canonical import make_lifecycle_event_hash
from backend.app.harvest_state.authority_repository import (
    activate_authority,
    create_or_load_capacity_pool_definition,
    create_or_load_daily_capacity,
    create_or_load_holiday_calendar,
    create_or_load_initial_inventory,
    create_or_load_mature_loss,
    create_or_load_run_parameter_package,
    create_or_load_weather_rule,
)
from backend.app.harvest_state.authority_request_errors import Task9AuthorityRequestAssemblyError
from backend.app.harvest_state.authority_request_loader import (
    assemble_task9_request_from_resolved_authorities,
)
from backend.app.harvest_state.authority_request_types import Task9AuthorityAssemblyContext
from backend.app.harvest_state.authority_resolution import (
    AuthorityExactReference,
    AuthorityResolutionMode,
    CapacityPoolResolutionRequest,
    DailyCapacityResolutionRequest,
    HolidayCalendarResolutionRequest,
    InitialInventoryResolutionRequest,
    MatureLossResolutionRequest,
    RunParameterPackageResolutionRequest,
    resolve_capacity_pool_definition,
    resolve_daily_capacity,
    resolve_holiday_calendar,
    resolve_initial_inventory,
    resolve_mature_inventory_loss,
    resolve_run_parameter_package,
)
from backend.app.harvest_state.authority_schemas import (
    Task9DailyCapacitySemanticInput,
    Task9InitialInventorySemanticBundle,
    Task9LifecycleEventSemanticInput,
    Task9MatureLossSemanticInput,
)
from backend.app.harvest_state.enums import (
    AuthorityFamily,
    AuthorityStatus,
    CapacityInputMode,
    ForecastQuantile,
    ParameterCode,
)
from backend.app.harvest_state.schemas import (
    DailyWeatherFeatureInput,
    ParameterSourceRef,
    Task8DailyPredictionInput,
    Task8PredictionSourceRef,
    Task8PredictionVerificationSnapshot,
)
from backend.app.models.harvest_state import (
    HarvestStateCohortTransitionRowModel,
    HarvestStateDailyMemberRowModel,
    HarvestStateDailyPoolRowModel,
    HarvestStateFutureArrivalRowModel,
    HarvestStateRun,
)
from backend.app.models.task9_authority import (
    Task9AuthorityLifecycleEvent,
    Task9DailyCapacityAuthority,
)
from backend.tests.integration.test_task9_authority_repository_postgres import (
    _IDS,
    _daily_input,
    _holiday_input,
    _pool_input,
    _run_package_input,
    _weather_input,
)

pytestmark = pytest.mark.integration

AS_OF = date(2026, 6, 1)
FORECAST_DATE = date(2026, 6, 15)
TZ = "Asia/Shanghai"


@pytest.fixture
async def db_session() -> AsyncSession:
    async with AsyncSessionMaker() as session:
        async with session.begin():
            await session.execute(
                text(
                    "INSERT INTO dim_season (code, start_date, end_date) "
                    "VALUES ('test-season', '2026-01-01', '2026-12-31') "
                    "ON CONFLICT DO NOTHING"
                )
            )
            await session.execute(
                text(
                    "INSERT INTO dim_factory (code, name) "
                    "VALUES ('test-factory', 'Test Factory') "
                    "ON CONFLICT DO NOTHING"
                )
            )
            await session.execute(
                text("INSERT INTO dim_farm (name) VALUES ('Test Farm') ON CONFLICT DO NOTHING")
            )
            farm_row = await session.execute(
                text("SELECT id FROM dim_farm WHERE name = 'Test Farm'")
            )
            farm_id = farm_row.scalar_one()
            await session.execute(
                text(
                    "INSERT INTO dim_subfarm (farm_id, name) "
                    "VALUES (:farm_id, 'Test Subfarm') "
                    "ON CONFLICT DO NOTHING"
                ),
                {"farm_id": farm_id},
            )
            await session.execute(
                text(
                    "INSERT INTO dim_variety (code, name) "
                    "VALUES ('test-var', 'Test Variety') "
                    "ON CONFLICT DO NOTHING"
                )
            )
            season_row = await session.execute(
                text("SELECT id FROM dim_season WHERE code = 'test-season'")
            )
            factory_row = await session.execute(
                text("SELECT id FROM dim_factory WHERE code = 'test-factory'")
            )
            subfarm_row = await session.execute(
                text(
                    "SELECT id FROM dim_subfarm WHERE farm_id = :farm_id AND name = 'Test Subfarm'"
                ),
                {"farm_id": farm_id},
            )
            variety_row = await session.execute(
                text("SELECT id FROM dim_variety WHERE code = 'test-var'")
            )
            _IDS["season"] = season_row.scalar_one()
            _IDS["factory"] = factory_row.scalar_one()
            _IDS["farm"] = farm_id
            _IDS["subfarm"] = subfarm_row.scalar_one()
            _IDS["variety"] = variety_row.scalar_one()
            yield session


def _assembly_context(
    *,
    mode: AuthorityResolutionMode = AuthorityResolutionMode.CURRENT_OPERATIONAL,
) -> Task9AuthorityAssemblyContext:
    return Task9AuthorityAssemblyContext(
        mode=mode,
        as_of_date=AS_OF,
        forecast_start_date=FORECAST_DATE,
        forecast_end_date=FORECAST_DATE,
    )


def _inventory_stable_key() -> str:
    return f"initial-inventory:{_IDS['season']}:{_IDS['factory']}:{FORECAST_DATE}"


def _inventory_input_for_request() -> Task9InitialInventorySemanticBundle:
    return Task9InitialInventorySemanticBundle(
        season_id=_IDS["season"],
        destination_factory_id=_IDS["factory"],
        opening_state_date=FORECAST_DATE,
        snapshot_version="v1",
        revision=1,
        initial_opening_mature_inventory_kg=Decimal("0"),
        available_at_local_date=date(2026, 1, 1),
        consumable_from_local_date=None,
        consumable_to_local_date=None,
        status=AuthorityStatus.DRAFT,
        status_changed_at=_pool_input().status_changed_at,
        superseded_by_id=None,
        source_system="test",
        source_record_key="test:inventory:request:v1:1",
        source_version="v1",
        cohorts=[],
    )


def _mature_loss_input_for_quantile(quantile: ForecastQuantile) -> Task9MatureLossSemanticInput:
    base = _mature_loss_base()
    return Task9MatureLossSemanticInput(
        **{
            **base.model_dump(),
            "forecast_quantile": quantile,
            "source_record_key": f"test:mature:{quantile.value}:v1:1",
        }
    )


def _mature_loss_base() -> Task9MatureLossSemanticInput:
    return Task9MatureLossSemanticInput(
        season_id=_IDS["season"],
        destination_factory_id=_IDS["factory"],
        state_date=FORECAST_DATE,
        capacity_pool_code="TEST-POOL",
        forecast_quantile=ForecastQuantile.P50,
        loss_version="v1",
        revision=1,
        mature_inventory_loss_quantity_kg=Decimal("1"),
        available_at_local_date=date(2026, 1, 1),
        consumable_from_local_date=None,
        consumable_to_local_date=None,
        status=AuthorityStatus.DRAFT,
        status_changed_at=_pool_input().status_changed_at,
        superseded_by_id=None,
        source_system="test",
        source_record_key="test:mature:P50:v1:1",
        source_version="v1",
    )


def _direct_daily_input() -> Task9DailyCapacitySemanticInput:
    base = _daily_input()
    return Task9DailyCapacitySemanticInput(
        **{
            **base.model_dump(),
            "capacity_input_mode": CapacityInputMode.DIRECT_CAPACITY,
            "planned_picker_count": None,
            "kg_per_person_per_day": None,
            "direct_nominal_capacity_kg_per_day": Decimal("200"),
            "source_record_key": "test:daily:direct:1",
        }
    )


def _exact_reference(resolved: object) -> AuthorityExactReference:
    return AuthorityExactReference(
        authority_id=resolved.authority_id,
        authority_stable_key=resolved.authority_stable_key,
        business_version=resolved.business_version,
        revision=resolved.revision,
        row_hash=resolved.row_hash,
    )


def _created_reference(
    created: object,
    *,
    stable_key: str,
    business_version: str = "v1",
    revision: int = 1,
) -> AuthorityExactReference:
    return AuthorityExactReference(
        authority_id=created.authority_id,
        authority_stable_key=stable_key,
        business_version=business_version,
        revision=revision,
        row_hash=created.row_hash,
    )


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
        farm_id=_IDS["farm"],
        subfarm_id=None,
        variety_id=_IDS["variety"],
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
            farm_id=_IDS["farm"],
            subfarm_id=None,
            variety_id=_IDS["variety"],
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
                forecast_quantile=quantile,
                source_quantity_kg=quantity,
                plan_id=5,
                location_reference_id=6,
                weather_mapping_id=7,
                base_temperature_search_run_id=8,
            ),
            verification_snapshot=verification,
        )
        for quantile, quantity in quantities.items()
    )


def _weather_features() -> tuple[DailyWeatherFeatureInput, ...]:
    return (
        DailyWeatherFeatureInput(
            capacity_date=FORECAST_DATE,
            capacity_pool_id="TEST-POOL",
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


async def _activate_daily_capacity_for_request_test(
    session: AsyncSession,
    *,
    daily_input: Task9DailyCapacitySemanticInput,
    authority_id: int,
    row_hash: str,
    activation_boundary: date,
) -> None:
    row = (
        await session.execute(
            select(Task9DailyCapacityAuthority).where(
                Task9DailyCapacityAuthority.id == authority_id
            )
        )
    ).scalar_one()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    stable_key = (
        f"daily-capacity:{daily_input.season_id}:"
        f"{daily_input.destination_factory_id}:"
        f"{daily_input.capacity_pool_code}:"
        f"{daily_input.capacity_pool_version}:"
        f"{daily_input.capacity_pool_revision}:"
        f"{daily_input.capacity_date.isoformat()}"
    )
    row.status = AuthorityStatus.ACTIVE
    row.status_changed_at = now
    row.consumable_from_local_date = activation_boundary
    row.consumable_to_local_date = None
    semantic_event = Task9LifecycleEventSemanticInput(
        authority_family=AuthorityFamily.DAILY_CAPACITY,
        authority_stable_key=stable_key,
        authority_business_version=daily_input.capacity_pool_version,
        authority_revision=daily_input.daily_capacity_revision,
        business_row_hash=row_hash,
        transition_sequence=2,
        old_status=AuthorityStatus.DRAFT,
        new_status=AuthorityStatus.ACTIVE,
        old_consumable_from_local_date=None,
        old_consumable_to_local_date=None,
        new_consumable_from_local_date=activation_boundary,
        new_consumable_to_local_date=None,
        superseded_by_authority_stable_key=None,
        superseded_by_authority_business_version=None,
        superseded_by_authority_revision=None,
        transitioned_at=now,
        source_system="authority_repository",
        source_record_key=(
            f"lifecycle:{AuthorityFamily.DAILY_CAPACITY.value}:"
            f"{stable_key}:{daily_input.daily_capacity_revision}:2"
        ),
    )
    session.add(
        Task9AuthorityLifecycleEvent(
            authority_family=AuthorityFamily.DAILY_CAPACITY.value,
            authority_stable_key=stable_key,
            authority_business_version=daily_input.capacity_pool_version,
            authority_revision=daily_input.daily_capacity_revision,
            business_row_hash=row_hash,
            transition_sequence=2,
            old_status=AuthorityStatus.DRAFT.value,
            new_status=AuthorityStatus.ACTIVE.value,
            old_consumable_from_local_date=None,
            old_consumable_to_local_date=None,
            new_consumable_from_local_date=activation_boundary,
            new_consumable_to_local_date=None,
            superseded_by_authority_stable_key=None,
            superseded_by_authority_business_version=None,
            superseded_by_authority_revision=None,
            transitioned_at=now,
            source_system="authority_repository",
            source_record_key=semantic_event.source_record_key,
            lifecycle_event_hash=make_lifecycle_event_hash(semantic_event),
        )
    )
    await session.flush()


async def _create_activate_authorities(
    session: AsyncSession,
    *,
    capacity_mode: CapacityInputMode,
) -> dict[str, object]:
    pool_input = _pool_input()
    if capacity_mode is CapacityInputMode.DIRECT_CAPACITY:
        pool_input = pool_input.model_copy(
            update={"capacity_input_mode": CapacityInputMode.DIRECT_CAPACITY}
        )
    pool_result = await create_or_load_capacity_pool_definition(
        session, definition_input=pool_input
    )
    await activate_authority(
        session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_id=pool_result.parent.authority_id,
        activation_boundary=date(2026, 1, 1),
    )
    daily_input = (
        _direct_daily_input()
        if capacity_mode is CapacityInputMode.DIRECT_CAPACITY
        else _daily_input()
    )
    daily_result = await create_or_load_daily_capacity(session, daily_input=daily_input)
    await _activate_daily_capacity_for_request_test(
        session,
        authority_id=daily_result.authority_id,
        daily_input=daily_input,
        row_hash=daily_result.row_hash,
        activation_boundary=date(2026, 1, 1),
    )
    holiday_input = _holiday_input()
    holiday_result = await create_or_load_holiday_calendar(session, calendar_input=holiday_input)
    await activate_authority(
        session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=holiday_result.parent.authority_id,
        activation_boundary=date(2026, 1, 1),
    )
    weather_input = _weather_input()
    weather_result = await create_or_load_weather_rule(session, weather_input=weather_input)
    await activate_authority(
        session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=weather_result.authority_id,
        activation_boundary=date(2026, 1, 1),
    )
    package_input = _run_package_input()
    package_result = await create_or_load_run_parameter_package(
        session,
        package_input=package_input,
        holiday_calendar=holiday_input,
        weather_rule=weather_input,
    )
    await activate_authority(
        session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        authority_id=package_result.authority_id,
        activation_boundary=date(2026, 1, 1),
    )
    inventory_input = _inventory_input_for_request()
    inventory_result = await create_or_load_initial_inventory(
        session,
        inventory_input=inventory_input,
    )
    await activate_authority(
        session,
        family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
        authority_id=inventory_result.parent.authority_id,
        activation_boundary=date(2026, 1, 1),
    )
    loss_results = {}
    for quantile in ForecastQuantile:
        loss_input = _mature_loss_input_for_quantile(quantile)
        loss_result = await create_or_load_mature_loss(session, loss_input=loss_input)
        await activate_authority(
            session,
            family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
            authority_id=loss_result.authority_id,
            activation_boundary=date(2026, 1, 1),
        )
        loss_results[quantile] = loss_result
    return {
        "pool": pool_result,
        "daily": daily_result,
        "holiday": holiday_result,
        "weather": weather_result,
        "package": package_result,
        "inventory": inventory_result,
        "losses": loss_results,
    }


async def _resolved_set(
    session: AsyncSession,
    *,
    mode: AuthorityResolutionMode,
    created: dict[str, object],
):
    exact = mode is AuthorityResolutionMode.EXACT_REFERENCE
    pool_stable_key = f"capacity-pool:{_IDS['season']}:{_IDS['factory']}:TEST-POOL"
    daily_stable_key = (
        f"daily-capacity:{_IDS['season']}:{_IDS['factory']}:TEST-POOL:v1:1:{FORECAST_DATE}"
    )
    holiday_stable_key = f"holiday-calendar:{_IDS['season']}:CN:{TZ}"
    run_package_stable_key = f"run-package:{_IDS['season']}:{_IDS['factory']}:farm-10"
    pool = await resolve_capacity_pool_definition(
        session,
        request=CapacityPoolResolutionRequest(
            mode=mode,
            as_of_local_date=AS_OF,
            timezone_name=TZ,
            season_id=_IDS["season"],
            destination_factory_id=_IDS["factory"],
            capacity_pool_code="TEST-POOL",
            effective_local_date=FORECAST_DATE,
            exact_reference=_created_reference(
                created["pool"].parent,
                stable_key=pool_stable_key,
            )
            if exact
            else None,
        ),
    )
    daily = await resolve_daily_capacity(
        session,
        request=DailyCapacityResolutionRequest(
            mode=mode,
            as_of_local_date=AS_OF,
            timezone_name=TZ,
            season_id=_IDS["season"],
            destination_factory_id=_IDS["factory"],
            capacity_pool_code="TEST-POOL",
            capacity_date=FORECAST_DATE,
            exact_reference=_created_reference(
                created["daily"],
                stable_key=daily_stable_key,
            )
            if exact
            else None,
        ),
    )
    holiday = await resolve_holiday_calendar(
        session,
        request=HolidayCalendarResolutionRequest(
            mode=mode,
            as_of_local_date=AS_OF,
            timezone_name=TZ,
            season_id=_IDS["season"],
            calendar_code="CN",
            lifecycle_timezone_name=TZ,
            exact_reference=_created_reference(
                created["holiday"].parent,
                stable_key=holiday_stable_key,
            )
            if exact
            else None,
        ),
    )
    run_package = await resolve_run_parameter_package(
        session,
        request=RunParameterPackageResolutionRequest(
            mode=mode,
            as_of_local_date=AS_OF,
            timezone_name=TZ,
            season_id=_IDS["season"],
            destination_factory_id=_IDS["factory"],
            farm_scope_key="farm-10",
            effective_local_date=FORECAST_DATE,
            exact_reference=_created_reference(
                created["package"],
                stable_key=run_package_stable_key,
            )
            if exact
            else None,
        ),
    )
    assert run_package.holiday_calendar.authority_id == holiday.authority_id
    inventory = await resolve_initial_inventory(
        session,
        request=InitialInventoryResolutionRequest(
            mode=mode,
            as_of_local_date=AS_OF,
            timezone_name=TZ,
            season_id=_IDS["season"],
            destination_factory_id=_IDS["factory"],
            opening_state_date=FORECAST_DATE,
            exact_reference=_created_reference(
                created["inventory"].parent,
                stable_key=_inventory_stable_key(),
            )
            if exact
            else None,
        ),
    )
    losses = []
    for quantile in ForecastQuantile:
        losses.append(
            await resolve_mature_inventory_loss(
                session,
                request=MatureLossResolutionRequest(
                    mode=mode,
                    as_of_local_date=AS_OF,
                    timezone_name=TZ,
                    season_id=_IDS["season"],
                    destination_factory_id=_IDS["factory"],
                    capacity_pool_code="TEST-POOL",
                    state_date=FORECAST_DATE,
                    forecast_quantile=quantile,
                    exact_reference=_created_reference(
                        created["losses"][quantile],
                        stable_key=(
                            f"mature-loss:{_IDS['season']}:{_IDS['factory']}:"
                            f"TEST-POOL:{FORECAST_DATE}:{quantile.value}"
                        ),
                    )
                    if exact
                    else None,
                ),
            )
        )
    return pool, daily, run_package, inventory, tuple(losses)


async def _harvest_state_row_count(session: AsyncSession) -> int:
    total = 0
    for model in (
        HarvestStateRun,
        HarvestStateDailyPoolRowModel,
        HarvestStateDailyMemberRowModel,
        HarvestStateCohortTransitionRowModel,
        HarvestStateFutureArrivalRowModel,
    ):
        total += await session.scalar(select(func.count()).select_from(model))
    return total


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "capacity_mode"),
    [
        (AuthorityResolutionMode.CURRENT_OPERATIONAL, CapacityInputMode.LABOR_DERIVED),
        (AuthorityResolutionMode.FIRST_TIME_HISTORICAL, CapacityInputMode.LABOR_DERIVED),
        (AuthorityResolutionMode.EXACT_REFERENCE, CapacityInputMode.DIRECT_CAPACITY),
    ],
)
async def test_assemble_task9_request_from_resolved_postgres_authorities(
    db_session: AsyncSession,
    mode: AuthorityResolutionMode,
    capacity_mode: CapacityInputMode,
) -> None:
    created = await _create_activate_authorities(db_session, capacity_mode=capacity_mode)
    pool, daily, run_package, inventory, losses = await _resolved_set(
        db_session,
        mode=mode,
        created=created,
    )

    assembled = assemble_task9_request_from_resolved_authorities(
        context=_assembly_context(mode=mode),
        capacity_pools=(pool,),
        daily_capacities=(daily,),
        run_package=run_package,
        initial_inventory=inventory,
        mature_losses=losses,
        task8_daily_predictions=_task8_predictions(),
        daily_weather_features=_weather_features(),
    )

    assert assembled.request.destination_factory_id == _IDS["factory"]
    assert assembled.request.daily_capacity_inputs[0].capacity_input_mode is capacity_mode
    assert {
        loss.forecast_quantile for loss in assembled.request.mature_inventory_loss_inputs
    } == set(ForecastQuantile)
    assert assembled.assembly_hash
    assert isinstance(assembled.canonical_payload, MappingProxyType)
    assert await _harvest_state_row_count(db_session) == 0


@pytest.mark.asyncio
async def test_assemble_rejects_cross_factory_resolved_authority(
    db_session: AsyncSession,
) -> None:
    created = await _create_activate_authorities(
        db_session,
        capacity_mode=CapacityInputMode.LABOR_DERIVED,
    )
    pool, daily, run_package, inventory, losses = await _resolved_set(
        db_session,
        mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
        created=created,
    )
    wrong_inventory = replace(
        inventory,
        semantic_bundle=inventory.semantic_bundle.model_copy(
            update={"destination_factory_id": _IDS["factory"] + 1000}
        ),
    )

    with pytest.raises(Task9AuthorityRequestAssemblyError) as exc_info:
        assemble_task9_request_from_resolved_authorities(
            context=_assembly_context(),
            capacity_pools=(pool,),
            daily_capacities=(daily,),
            run_package=run_package,
            initial_inventory=wrong_inventory,
            mature_losses=losses,
            task8_daily_predictions=_task8_predictions(),
            daily_weather_features=_weather_features(),
        )

    assert exc_info.value.code == "TASK9_AUTHORITY_REQUEST_ASSEMBLY_ERROR"
    assert exc_info.value.details["reason"] == "authority_scope_mismatch"


@pytest.mark.asyncio
async def test_assemble_rejects_missing_mature_loss_quantile(
    db_session: AsyncSession,
) -> None:
    created = await _create_activate_authorities(
        db_session,
        capacity_mode=CapacityInputMode.LABOR_DERIVED,
    )
    pool, daily, run_package, inventory, losses = await _resolved_set(
        db_session,
        mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
        created=created,
    )

    with pytest.raises(Task9AuthorityRequestAssemblyError) as exc_info:
        assemble_task9_request_from_resolved_authorities(
            context=_assembly_context(),
            capacity_pools=(pool,),
            daily_capacities=(daily,),
            run_package=run_package,
            initial_inventory=inventory,
            mature_losses=losses[:2],
            task8_daily_predictions=_task8_predictions(),
            daily_weather_features=_weather_features(),
        )

    assert exc_info.value.code == "TASK9_AUTHORITY_REQUEST_ASSEMBLY_ERROR"
    assert exc_info.value.details["reason"] == "authority_quantile_coverage_incomplete"
