# ruff: noqa: E501
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.harvest_state.authority_repository import (
    activate_authority,
    create_or_load_capacity_pool_definition,
    create_or_load_daily_capacity,
    create_or_load_holiday_calendar,
    create_or_load_initial_inventory,
    create_or_load_mature_loss,
    create_or_load_run_parameter_package,
    create_or_load_weather_rule,
    retire_authority,
    supersede_authority,
)
from backend.app.harvest_state.authority_resolution import (
    AuthorityExactReference,
    AuthorityResolutionMode,
    CapacityPoolResolutionRequest,
    DailyCapacityResolutionRequest,
    HolidayCalendarResolutionRequest,
    InitialInventoryResolutionRequest,
    MatureLossResolutionRequest,
    RunParameterPackageResolutionRequest,
    WeatherRuleResolutionRequest,
    resolve_capacity_pool_definition,
    resolve_daily_capacity,
    resolve_holiday_calendar,
    resolve_initial_inventory,
    resolve_mature_inventory_loss,
    resolve_run_parameter_package,
    resolve_weather_rule,
)
from backend.app.harvest_state.authority_resolution_errors import (
    AuthorityEffectiveIntervalMismatchError,
    AuthorityNotConsumableAtCutoffError,
)
from backend.app.harvest_state.enums import AuthorityFamily
from backend.app.models.task9_authority import (
    Task9CapacityPoolDefinition,
    Task9DailyCapacityAuthority,
    Task9InitialInventorySnapshot,
    Task9MatureInventoryLossAuthority,
    Task9RunParameterPackage,
)
from backend.tests.integration.test_task9_authority_repository_postgres import (
    _IDS,
    _daily_input,
    _holiday_input,
    _inventory_input,
    _mature_loss_input,
    _pool_input,
    _run_package_input,
    _weather_input,
)

pytestmark = pytest.mark.integration


async def _row_by_id(
    session: AsyncSession,
    model: type,
    authority_id: int,
):
    result = await session.execute(select(model).where(model.id == authority_id))
    return result.scalar_one()


def _exact_reference(
    *,
    authority_id: int,
    stable_key: str,
    version: str,
    revision: int,
    row_hash: str,
) -> AuthorityExactReference:
    return AuthorityExactReference(
        authority_id=authority_id,
        authority_stable_key=stable_key,
        business_version=version,
        revision=revision,
        row_hash=row_hash,
    )


@pytest.mark.asyncio
async def test_resolve_capacity_pool_current_historical_and_exact_reference(
    db_session: AsyncSession,
) -> None:
    old_input = _pool_input(version="v1", revision=1)
    old_created = await create_or_load_capacity_pool_definition(
        db_session, definition_input=old_input
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_id=old_created.parent.authority_id,
        activation_boundary=date(2026, 3, 1),
    )

    new_input = _pool_input(version="v2", revision=1)
    supersession = await supersede_authority(
        db_session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_id=old_created.parent.authority_id,
        new_input=new_input,
        supersession_boundary=date(2026, 6, 1),
    )

    current = await resolve_capacity_pool_definition(
        db_session,
        request=CapacityPoolResolutionRequest(
            mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
            as_of_local_date=date(2026, 6, 1),
            timezone_name="Asia/Shanghai",
            season_id=_IDS["season"],
            destination_factory_id=_IDS["factory"],
            capacity_pool_code=old_input.capacity_pool_code,
            effective_local_date=date(2026, 6, 1),
        ),
    )
    assert current.authority_id == supersession.new.authority_id
    assert current.business_version == "v2"

    historical = await resolve_capacity_pool_definition(
        db_session,
        request=CapacityPoolResolutionRequest(
            mode=AuthorityResolutionMode.FIRST_TIME_HISTORICAL,
            as_of_local_date=date(2026, 5, 31),
            timezone_name="Asia/Shanghai",
            season_id=_IDS["season"],
            destination_factory_id=_IDS["factory"],
            capacity_pool_code=old_input.capacity_pool_code,
            effective_local_date=date(2026, 5, 31),
        ),
    )
    assert historical.authority_id == old_created.parent.authority_id
    assert historical.business_version == "v1"

    old_row = await _row_by_id(
        db_session,
        Task9CapacityPoolDefinition,
        old_created.parent.authority_id,
    )
    exact = await resolve_capacity_pool_definition(
        db_session,
        request=CapacityPoolResolutionRequest(
            mode=AuthorityResolutionMode.EXACT_REFERENCE,
            as_of_local_date=date(2026, 5, 31),
            timezone_name="Asia/Shanghai",
            season_id=_IDS["season"],
            destination_factory_id=_IDS["factory"],
            capacity_pool_code=old_input.capacity_pool_code,
            effective_local_date=date(2026, 5, 31),
            exact_reference=_exact_reference(
                authority_id=old_row.id,
                stable_key=historical.authority_stable_key,
                version=old_row.capacity_pool_version,
                revision=old_row.revision,
                row_hash=old_row.row_hash,
            ),
        ),
    )
    assert exact.authority_id == old_created.parent.authority_id
    assert exact.business_version == "v1"


@pytest.mark.asyncio
async def test_resolve_holiday_and_weather_historical_superseded_rows(
    db_session: AsyncSession,
) -> None:
    old_holiday = _holiday_input(version="v1", revision=1)
    old_holiday_created = await create_or_load_holiday_calendar(
        db_session, calendar_input=old_holiday
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=old_holiday_created.parent.authority_id,
        activation_boundary=date(2026, 3, 1),
    )
    old_weather = _weather_input(version="v1", revision=1)
    old_weather_created = await create_or_load_weather_rule(db_session, weather_input=old_weather)
    await activate_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=old_weather_created.authority_id,
        activation_boundary=date(2026, 3, 1),
    )

    await supersede_authority(
        db_session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=old_holiday_created.parent.authority_id,
        new_input=_holiday_input(version="v2", revision=1),
        supersession_boundary=date(2026, 6, 1),
    )
    await supersede_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=old_weather_created.authority_id,
        new_input=_weather_input(version="v2", revision=1),
        supersession_boundary=date(2026, 6, 1),
    )

    holiday = await resolve_holiday_calendar(
        db_session,
        request=HolidayCalendarResolutionRequest(
            mode=AuthorityResolutionMode.FIRST_TIME_HISTORICAL,
            as_of_local_date=date(2026, 5, 31),
            timezone_name="Asia/Shanghai",
            season_id=_IDS["season"],
            calendar_code="CN",
            lifecycle_timezone_name="Asia/Shanghai",
        ),
    )
    weather = await resolve_weather_rule(
        db_session,
        request=WeatherRuleResolutionRequest(
            mode=AuthorityResolutionMode.FIRST_TIME_HISTORICAL,
            as_of_local_date=date(2026, 5, 31),
            timezone_name="Asia/Shanghai",
            rule_code="WEATHER-STD",
            lifecycle_timezone_name="Asia/Shanghai",
            effective_local_date=date(2026, 5, 31),
        ),
    )
    assert holiday.business_version == "v1"
    assert weather.business_version == "v1"


@pytest.mark.asyncio
async def test_resolve_daily_capacity_rejects_parent_not_consumable_and_effective_mismatch(
    db_session: AsyncSession,
) -> None:
    pool_input = _pool_input(version="v1", revision=1)
    pool_created = await create_or_load_capacity_pool_definition(
        db_session, definition_input=pool_input
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_id=pool_created.parent.authority_id,
        activation_boundary=date(2026, 3, 1),
    )
    daily_input = _daily_input(pool_version="v1", pool_revision=1)
    daily_created = await create_or_load_daily_capacity(db_session, daily_input=daily_input)
    await activate_authority(
        db_session,
        family=AuthorityFamily.DAILY_CAPACITY,
        authority_id=daily_created.authority_id,
        activation_boundary=date(2026, 3, 1),
    )

    await retire_authority(
        db_session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_id=pool_created.parent.authority_id,
        retirement_boundary=date(2026, 5, 1),
    )

    with pytest.raises(AuthorityNotConsumableAtCutoffError) as exc_info:
        await resolve_daily_capacity(
            db_session,
            request=DailyCapacityResolutionRequest(
                mode=AuthorityResolutionMode.FIRST_TIME_HISTORICAL,
                as_of_local_date=date(2026, 5, 15),
                timezone_name="Asia/Shanghai",
                season_id=_IDS["season"],
                destination_factory_id=_IDS["factory"],
                capacity_pool_code=pool_input.capacity_pool_code,
                capacity_date=daily_input.capacity_date,
            ),
        )
    assert exc_info.value.code == "AUTHORITY_NOT_CONSUMABLE_AT_CUTOFF"

    await db_session.execute(
        text(
            """
            UPDATE task9_capacity_pool_definition
            SET effective_to = DATE '2026-05-31'
            WHERE id = :authority_id
            """
        ),
        {"authority_id": pool_created.parent.authority_id},
    )
    await db_session.flush()

    with pytest.raises(AuthorityEffectiveIntervalMismatchError) as interval_exc:
        await resolve_daily_capacity(
            db_session,
            request=DailyCapacityResolutionRequest(
                mode=AuthorityResolutionMode.EXACT_REFERENCE,
                as_of_local_date=date(2026, 4, 1),
                timezone_name="Asia/Shanghai",
                season_id=_IDS["season"],
                destination_factory_id=_IDS["factory"],
                capacity_pool_code=pool_input.capacity_pool_code,
                capacity_date=daily_input.capacity_date,
                exact_reference=_exact_reference(
                    authority_id=daily_created.authority_id,
                    stable_key=(
                        f"daily-capacity:{_IDS['season']}:{_IDS['factory']}:"
                        f"{pool_input.capacity_pool_code}:{pool_input.capacity_pool_version}:"
                        f"{pool_input.revision}:{daily_input.capacity_date.isoformat()}"
                    ),
                    version=pool_input.capacity_pool_version,
                    revision=daily_input.daily_capacity_revision,
                    row_hash=(
                        await _row_by_id(
                            db_session, Task9DailyCapacityAuthority, daily_created.authority_id
                        )
                    ).row_hash,
                ),
            ),
        )
    assert interval_exc.value.code == "AUTHORITY_EFFECTIVE_INTERVAL_MISMATCH"


@pytest.mark.asyncio
async def test_resolve_run_package_uses_exact_fk_dependencies(
    db_session: AsyncSession,
) -> None:
    holiday_v1 = _holiday_input(version="v1", revision=1)
    holiday_created = await create_or_load_holiday_calendar(db_session, calendar_input=holiday_v1)
    await activate_authority(
        db_session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=holiday_created.parent.authority_id,
        activation_boundary=date(2026, 3, 1),
    )
    weather_v1 = _weather_input(version="v1", revision=1)
    weather_created = await create_or_load_weather_rule(db_session, weather_input=weather_v1)
    await activate_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=weather_created.authority_id,
        activation_boundary=date(2026, 3, 1),
    )
    pkg_v1 = _run_package_input(version="v1", revision=1)
    pkg_created = await create_or_load_run_parameter_package(
        db_session,
        package_input=pkg_v1,
        holiday_calendar=holiday_v1,
        weather_rule=weather_v1,
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        authority_id=pkg_created.authority_id,
        activation_boundary=date(2026, 3, 1),
    )

    await supersede_authority(
        db_session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=holiday_created.parent.authority_id,
        new_input=_holiday_input(version="v2", revision=1),
        supersession_boundary=date(2026, 6, 1),
    )
    await supersede_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=weather_created.authority_id,
        new_input=_weather_input(version="v2", revision=1),
        supersession_boundary=date(2026, 6, 1),
    )

    resolved = await resolve_run_parameter_package(
        db_session,
        request=RunParameterPackageResolutionRequest(
            mode=AuthorityResolutionMode.EXACT_REFERENCE,
            as_of_local_date=date(2026, 5, 31),
            timezone_name="Asia/Shanghai",
            season_id=_IDS["season"],
            destination_factory_id=_IDS["factory"],
            farm_scope_key="farm-10",
            effective_local_date=date(2026, 5, 31),
            exact_reference=_exact_reference(
                authority_id=pkg_created.authority_id,
                stable_key=f"run-package:{_IDS['season']}:{_IDS['factory']}:farm-10",
                version="v1",
                revision=1,
                row_hash=(
                    await _row_by_id(db_session, Task9RunParameterPackage, pkg_created.authority_id)
                ).row_hash,
            ),
        ),
    )
    assert resolved.business_version == "v1"
    assert resolved.holiday_calendar.business_version == "v1"
    assert resolved.weather_rule.business_version == "v1"


@pytest.mark.asyncio
async def test_resolve_initial_inventory_and_mature_loss_exact_reference(
    db_session: AsyncSession,
) -> None:
    inventory_input = _inventory_input(version="v1", revision=1)
    inventory_created = await create_or_load_initial_inventory(
        db_session, inventory_input=inventory_input
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
        authority_id=inventory_created.parent.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    mature_loss_input = _mature_loss_input(version="v1", revision=1)
    mature_loss_created = await create_or_load_mature_loss(db_session, loss_input=mature_loss_input)
    await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=mature_loss_created.authority_id,
        activation_boundary=date(2026, 3, 1),
    )

    resolved_inventory = await resolve_initial_inventory(
        db_session,
        request=InitialInventoryResolutionRequest(
            mode=AuthorityResolutionMode.EXACT_REFERENCE,
            as_of_local_date=date(2026, 1, 1),
            timezone_name="Asia/Shanghai",
            season_id=_IDS["season"],
            destination_factory_id=_IDS["factory"],
            opening_state_date=inventory_input.opening_state_date,
            exact_reference=_exact_reference(
                authority_id=inventory_created.parent.authority_id,
                stable_key=(
                    f"initial-inventory:{_IDS['season']}:{_IDS['factory']}:"
                    f"{inventory_input.opening_state_date.isoformat()}"
                ),
                version="v1",
                revision=1,
                row_hash=(
                    await _row_by_id(
                        db_session,
                        Task9InitialInventorySnapshot,
                        inventory_created.parent.authority_id,
                    )
                ).row_hash,
            ),
        ),
    )
    resolved_mature_loss = await resolve_mature_inventory_loss(
        db_session,
        request=MatureLossResolutionRequest(
            mode=AuthorityResolutionMode.EXACT_REFERENCE,
            as_of_local_date=date(2026, 6, 15),
            timezone_name="Asia/Shanghai",
            season_id=_IDS["season"],
            destination_factory_id=_IDS["factory"],
            capacity_pool_code=mature_loss_input.capacity_pool_code,
            state_date=mature_loss_input.state_date,
            forecast_quantile=mature_loss_input.forecast_quantile,
            exact_reference=_exact_reference(
                authority_id=mature_loss_created.authority_id,
                stable_key=(
                    f"mature-loss:{_IDS['season']}:{_IDS['factory']}:"
                    f"{mature_loss_input.capacity_pool_code}:{mature_loss_input.state_date.isoformat()}:"
                    f"{mature_loss_input.forecast_quantile}"
                ),
                version="v1",
                revision=1,
                row_hash=(
                    await _row_by_id(
                        db_session,
                        Task9MatureInventoryLossAuthority,
                        mature_loss_created.authority_id,
                    )
                ).row_hash,
            ),
        ),
    )

    assert resolved_inventory.business_version == "v1"
    assert resolved_inventory.semantic_bundle.initial_opening_mature_inventory_kg > 0
    assert resolved_mature_loss.business_version == "v1"
    assert resolved_mature_loss.semantic_input.mature_inventory_loss_quantity_kg > 0
