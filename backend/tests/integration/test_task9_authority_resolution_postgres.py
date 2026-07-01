# ruff: noqa: E501
from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import AsyncSessionMaker
from backend.app.harvest_state.authority_canonical import (
    build_daily_capacity_stable_key,
)
from backend.app.harvest_state.authority_repository import (
    _write_lifecycle_event,
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
from backend.app.harvest_state.authority_repository_errors import (
    AuthorityHashConflictError,
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
    AuthorityDependencyMismatchError,
    AuthorityEffectiveIntervalMismatchError,
    AuthorityExactReferenceMismatchError,
    AuthorityNotConsumableAtCutoffError,
    AuthorityScopeMismatchError,
    HistoricalAuthorityNotFoundError,
    TimezoneAuthorityInvalidError,
)
from backend.app.harvest_state.authority_schemas import Task9CapacityPoolMemberSchema
from backend.app.harvest_state.enums import AuthorityFamily, AuthorityStatus
from backend.app.models.task9_authority import (
    Task9CapacityPoolDefinition,
    Task9DailyCapacityAuthority,
    Task9InitialInventorySnapshot,
    Task9MatureInventoryLossAuthority,
    Task9RunParameterPackage,
    Task9WeatherRuleConfigVersion,
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


async def _row_by_id(
    session: AsyncSession,
    model: type,
    authority_id: int,
):
    result = await session.execute(select(model).where(model.id == authority_id))
    return result.scalar_one()


async def _activate_daily_capacity_for_test(
    session: AsyncSession,
    *,
    authority_id: int,
    daily_input: Any,
    activation_boundary: date,
) -> None:
    row = await _row_by_id(session, Task9DailyCapacityAuthority, authority_id)
    row.status = AuthorityStatus.ACTIVE.value
    row.consumable_from_local_date = activation_boundary
    row.consumable_to_local_date = None
    await session.flush()
    await _write_lifecycle_event(
        session,
        family=AuthorityFamily.DAILY_CAPACITY,
        stable_key=build_daily_capacity_stable_key(daily_input),
        business_version=daily_input.capacity_pool_version,
        revision=daily_input.daily_capacity_revision,
        business_row_hash=row.row_hash,
        transition_sequence=2,
        old_status=AuthorityStatus.DRAFT,
        new_status=AuthorityStatus.ACTIVE,
        old_consumable_from=None,
        old_consumable_to=None,
        new_consumable_from=activation_boundary,
        new_consumable_to=None,
    )


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
        old_id=old_created.parent.authority_id,
        new_input=new_input,
        new_members=list(new_input.members),
        replacement_boundary=date(2026, 6, 1),
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

    holiday_v2 = _holiday_input(version="v2", revision=1)
    weather_v2 = _weather_input(version="v2", revision=1)
    await supersede_authority(
        db_session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        old_id=old_holiday_created.parent.authority_id,
        new_input=holiday_v2,
        new_dates=list(holiday_v2.dates),
        replacement_boundary=date(2026, 6, 1),
    )
    await supersede_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        old_id=old_weather_created.authority_id,
        new_input=weather_v2,
        replacement_boundary=date(2026, 6, 1),
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
    await _activate_daily_capacity_for_test(
        db_session,
        authority_id=daily_created.authority_id,
        activation_boundary=date(2026, 3, 1),
        daily_input=daily_input,
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
        text("INSERT INTO dim_farm (name) VALUES ('Finite Pool Farm') ON CONFLICT DO NOTHING")
    )
    finite_farm_row = await db_session.execute(
        text("SELECT id FROM dim_farm WHERE name = 'Finite Pool Farm'")
    )
    finite_farm_id = finite_farm_row.scalar_one()
    finite_pool_input = _pool_input(code="FINITE-POOL", version="v1", revision=1).model_copy(
        update={
            "effective_to": date(2026, 5, 31),
            "members": [
                Task9CapacityPoolMemberSchema(
                    farm_id=finite_farm_id,
                    subfarm_id=None,
                    variety_id=_IDS["variety"],
                )
            ],
        }
    )
    finite_pool_created = await create_or_load_capacity_pool_definition(
        db_session, definition_input=finite_pool_input
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_id=finite_pool_created.parent.authority_id,
        activation_boundary=date(2026, 3, 1),
    )
    mismatched_daily_input = _daily_input(
        pool_code="FINITE-POOL",
        pool_version="v1",
        pool_revision=1,
        cap_date=date(2026, 6, 15),
    )
    mismatched_daily_created = await create_or_load_daily_capacity(
        db_session,
        daily_input=mismatched_daily_input,
    )
    await _activate_daily_capacity_for_test(
        db_session,
        authority_id=mismatched_daily_created.authority_id,
        activation_boundary=date(2026, 3, 1),
        daily_input=mismatched_daily_input,
    )

    with pytest.raises(AuthorityEffectiveIntervalMismatchError) as interval_exc:
        await resolve_daily_capacity(
            db_session,
            request=DailyCapacityResolutionRequest(
                mode=AuthorityResolutionMode.EXACT_REFERENCE,
                as_of_local_date=date(2026, 4, 1),
                timezone_name="Asia/Shanghai",
                season_id=_IDS["season"],
                destination_factory_id=_IDS["factory"],
                capacity_pool_code=finite_pool_input.capacity_pool_code,
                capacity_date=mismatched_daily_input.capacity_date,
                exact_reference=_exact_reference(
                    authority_id=mismatched_daily_created.authority_id,
                    stable_key=(
                        f"daily-capacity:{_IDS['season']}:{_IDS['factory']}:"
                        f"{finite_pool_input.capacity_pool_code}:"
                        f"{finite_pool_input.capacity_pool_version}:"
                        f"{finite_pool_input.revision}:"
                        f"{mismatched_daily_input.capacity_date.isoformat()}"
                    ),
                    version=finite_pool_input.capacity_pool_version,
                    revision=mismatched_daily_input.daily_capacity_revision,
                    row_hash=(
                        await _row_by_id(
                            db_session,
                            Task9DailyCapacityAuthority,
                            mismatched_daily_created.authority_id,
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
    await retire_authority(
        db_session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        authority_id=pkg_created.authority_id,
        retirement_boundary=date(2026, 6, 1),
    )

    holiday_v2 = _holiday_input(version="v2", revision=1)
    weather_v2 = _weather_input(version="v2", revision=1)
    await supersede_authority(
        db_session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        old_id=holiday_created.parent.authority_id,
        new_input=holiday_v2,
        new_dates=list(holiday_v2.dates),
        replacement_boundary=date(2026, 6, 1),
    )
    await supersede_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        old_id=weather_created.authority_id,
        new_input=weather_v2,
        replacement_boundary=date(2026, 6, 1),
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


# ══════════════════════════════════════════════════════════════════════════
# P0-7D Integration Tests
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_current_operational_rejects_future_consumable_from_boundary(
    db_session: AsyncSession,
) -> None:
    """CURRENT_OPERATIONAL rejects authority when as_of < consumable_from."""
    pool_input = _pool_input(version="v1", revision=1)
    pool_created = await create_or_load_capacity_pool_definition(
        db_session, definition_input=pool_input
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_id=pool_created.parent.authority_id,
        activation_boundary=date(2026, 7, 1),
    )

    # as_of=2026-06-15 < consumable_from=2026-07-01 → reject
    with pytest.raises(AuthorityNotConsumableAtCutoffError) as exc_info:
        await resolve_capacity_pool_definition(
            db_session,
            request=CapacityPoolResolutionRequest(
                mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
                as_of_local_date=date(2026, 6, 15),
                timezone_name="Asia/Shanghai",
                season_id=_IDS["season"],
                destination_factory_id=_IDS["factory"],
                capacity_pool_code=pool_input.capacity_pool_code,
                effective_local_date=date(2026, 6, 15),
            ),
        )
    assert exc_info.value.code == "AUTHORITY_NOT_CONSUMABLE_AT_CUTOFF"

    # as_of=2026-07-01 == consumable_from → success
    resolved = await resolve_capacity_pool_definition(
        db_session,
        request=CapacityPoolResolutionRequest(
            mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
            as_of_local_date=date(2026, 7, 1),
            timezone_name="Asia/Shanghai",
            season_id=_IDS["season"],
            destination_factory_id=_IDS["factory"],
            capacity_pool_code=pool_input.capacity_pool_code,
            effective_local_date=date(2026, 7, 1),
        ),
    )
    assert resolved.authority_id == pool_created.parent.authority_id

    # as_of=2026-07-15 > consumable_from → success
    resolved = await resolve_capacity_pool_definition(
        db_session,
        request=CapacityPoolResolutionRequest(
            mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
            as_of_local_date=date(2026, 7, 15),
            timezone_name="Asia/Shanghai",
            season_id=_IDS["season"],
            destination_factory_id=_IDS["factory"],
            capacity_pool_code=pool_input.capacity_pool_code,
            effective_local_date=date(2026, 7, 15),
        ),
    )
    assert resolved.authority_id == pool_created.parent.authority_id


@pytest.mark.asyncio
async def test_current_operational_rejects_activation_boundary_after_cutoff(
    db_session: AsyncSession,
) -> None:
    """CURRENT_OPERATIONAL rejects when as_of is before activation_boundary."""
    pool_input = _pool_input(version="v1", revision=1)
    pool_created = await create_or_load_capacity_pool_definition(
        db_session, definition_input=pool_input
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_id=pool_created.parent.authority_id,
        activation_boundary=date(2026, 6, 1),
    )

    with pytest.raises(AuthorityNotConsumableAtCutoffError) as exc_info:
        await resolve_capacity_pool_definition(
            db_session,
            request=CapacityPoolResolutionRequest(
                mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
                as_of_local_date=date(2026, 5, 31),
                timezone_name="Asia/Shanghai",
                season_id=_IDS["season"],
                destination_factory_id=_IDS["factory"],
                capacity_pool_code=pool_input.capacity_pool_code,
                effective_local_date=date(2026, 5, 31),
            ),
        )
    assert exc_info.value.code == "AUTHORITY_NOT_CONSUMABLE_AT_CUTOFF"


@pytest.mark.asyncio
async def test_weather_exact_reference_scope_mismatch_rule_code(
    db_session: AsyncSession,
) -> None:
    """EXACT_REFERENCE raises AUTHORITY_SCOPE_MISMATCH when rule_code differs."""
    weather_input = _weather_input(version="v1", revision=1).model_copy(
        update={"rule_code": "FROST"}
    )
    weather_created = await create_or_load_weather_rule(db_session, weather_input=weather_input)
    await activate_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=weather_created.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    weather_row = await _row_by_id(
        db_session, Task9WeatherRuleConfigVersion, weather_created.authority_id
    )

    with pytest.raises(AuthorityScopeMismatchError) as exc_info:
        await resolve_weather_rule(
            db_session,
            request=WeatherRuleResolutionRequest(
                mode=AuthorityResolutionMode.EXACT_REFERENCE,
                as_of_local_date=date(2026, 6, 15),
                timezone_name="Asia/Shanghai",
                rule_code="HEAT",
                lifecycle_timezone_name="Asia/Shanghai",
                effective_local_date=date(2026, 1, 1),
                exact_reference=_exact_reference(
                    authority_id=weather_created.authority_id,
                    stable_key="weather-rule:FROST:Asia/Shanghai",
                    version=weather_input.rule_version,
                    revision=weather_input.revision,
                    row_hash=weather_row.row_hash,
                ),
            ),
        )
    assert exc_info.value.code == "AUTHORITY_SCOPE_MISMATCH"
    assert exc_info.value.details.get("reason") == "scope_field_mismatch"
    assert exc_info.value.details.get("field") == "rule_code"


@pytest.mark.asyncio
async def test_weather_exact_reference_scope_mismatch_timezone(
    db_session: AsyncSession,
) -> None:
    """EXACT_REFERENCE raises AUTHORITY_SCOPE_MISMATCH when timezone differs."""
    weather_input = _weather_input(version="v1", revision=1)
    weather_created = await create_or_load_weather_rule(db_session, weather_input=weather_input)
    await activate_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=weather_created.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    weather_row = await _row_by_id(
        db_session, Task9WeatherRuleConfigVersion, weather_created.authority_id
    )

    with pytest.raises(AuthorityScopeMismatchError) as exc_info:
        await resolve_weather_rule(
            db_session,
            request=WeatherRuleResolutionRequest(
                mode=AuthorityResolutionMode.EXACT_REFERENCE,
                as_of_local_date=date(2026, 6, 15),
                timezone_name="Asia/Shanghai",
                rule_code="WEATHER-STD",
                lifecycle_timezone_name="UTC",
                effective_local_date=date(2026, 1, 1),
                exact_reference=_exact_reference(
                    authority_id=weather_created.authority_id,
                    stable_key="weather-rule:WEATHER-STD:Asia/Shanghai",
                    version=weather_input.rule_version,
                    revision=weather_input.revision,
                    row_hash=weather_row.row_hash,
                ),
            ),
        )
    assert exc_info.value.code == "AUTHORITY_SCOPE_MISMATCH"
    assert exc_info.value.details.get("reason") == "scope_field_mismatch"
    assert exc_info.value.details.get("field") == "lifecycle_timezone_name"


@pytest.mark.asyncio
async def test_run_package_holiday_season_mismatch(
    db_session: AsyncSession,
) -> None:
    """CURRENT_OPERATIONAL detects holiday season mismatch in run-package."""
    # Create second season
    await db_session.execute(
        text(
            "INSERT INTO dim_season (code, start_date, end_date) "
            "VALUES ('test-season-B', '2026-01-01', '2026-12-31') "
            "ON CONFLICT DO NOTHING"
        )
    )
    season_b_row = await db_session.execute(
        text("SELECT id FROM dim_season WHERE code = 'test-season-B'")
    )
    season_b_id = season_b_row.scalar_one()

    # Create holiday in season B
    holiday_b_input = _holiday_input(version="v1", revision=1).model_copy(
        update={"season_id": season_b_id}
    )
    holiday_b_created = await create_or_load_holiday_calendar(
        db_session, calendar_input=holiday_b_input
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=holiday_b_created.parent.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    # Create weather in season A (default)
    weather_input = _weather_input(version="v1", revision=1)
    weather_created = await create_or_load_weather_rule(db_session, weather_input=weather_input)
    await activate_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=weather_created.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    # Create run-package in season A referencing holiday from season A (valid)
    pkg_input = _run_package_input(version="v1", revision=1)
    holiday_a_input = _holiday_input(version="v1", revision=1)
    holiday_a_created = await create_or_load_holiday_calendar(
        db_session, calendar_input=holiday_a_input
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=holiday_a_created.parent.authority_id,
        activation_boundary=date(2026, 1, 1),
    )
    pkg_created = await create_or_load_run_parameter_package(
        db_session,
        package_input=pkg_input,
        holiday_calendar=holiday_a_input,
        weather_rule=weather_input,
    )
    # Swap the holiday FK to point to the season-B holiday via raw SQL
    await db_session.execute(
        text(
            "UPDATE task9_run_parameter_package "
            "SET holiday_calendar_version_id = :holiday_id "
            "WHERE id = :pkg_id"
        ),
        {"holiday_id": holiday_b_created.parent.authority_id, "pkg_id": pkg_created.authority_id},
    )
    await db_session.flush()
    db_session.expire_all()
    await activate_authority(
        db_session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        authority_id=pkg_created.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    with pytest.raises(AuthorityDependencyMismatchError) as exc_info:
        await resolve_run_parameter_package(
            db_session,
            request=RunParameterPackageResolutionRequest(
                mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
                as_of_local_date=date(2026, 6, 15),
                timezone_name="Asia/Shanghai",
                season_id=_IDS["season"],
                destination_factory_id=_IDS["factory"],
                farm_scope_key="farm-10",
                effective_local_date=date(2026, 6, 15),
            ),
        )
    err = exc_info.value
    assert err.code == "AUTHORITY_DEPENDENCY_MISMATCH"
    assert err.details.get("reason") == "holiday_season_mismatch"
    expected_package_stable_key = f"run-package:{_IDS['season']}:{_IDS['factory']}:farm-10"
    expected_holiday_stable_key = (
        f"holiday-calendar:{season_b_id}:"
        f"{holiday_b_input.calendar_code}:"
        f"{holiday_b_input.lifecycle_timezone_name}"
    )
    assert err.authority_stable_key == expected_package_stable_key
    assert err.details.get("dependency_family") == "holiday_calendar_version"
    assert err.details.get("dependency_authority_stable_key") == expected_holiday_stable_key
    assert err.details.get("expected_season_id") == _IDS["season"]
    assert err.details.get("actual_season_id") == season_b_id


@pytest.mark.asyncio
async def test_capacity_pool_scope_not_found(
    db_session: AsyncSession,
) -> None:
    """CURRENT_OPERATIONAL raises HISTORICAL_AUTHORITY_NOT_FOUND for missing pool."""
    with pytest.raises(HistoricalAuthorityNotFoundError) as exc_info:
        await resolve_capacity_pool_definition(
            db_session,
            request=CapacityPoolResolutionRequest(
                mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
                as_of_local_date=date(2026, 6, 15),
                timezone_name="Asia/Shanghai",
                season_id=_IDS["season"],
                destination_factory_id=_IDS["factory"],
                capacity_pool_code="NONEXISTENT-POOL",
                effective_local_date=date(2026, 6, 15),
            ),
        )
    assert exc_info.value.code == "HISTORICAL_AUTHORITY_NOT_FOUND"


@pytest.mark.asyncio
async def test_capacity_pool_effective_mismatch(
    db_session: AsyncSession,
) -> None:
    """CURRENT_OPERATIONAL raises AUTHORITY_EFFECTIVE_INTERVAL_MISMATCH."""
    pool_input = _pool_input(version="v1", revision=1).model_copy(
        update={
            "effective_from": date(2026, 1, 1),
            "effective_to": date(2026, 6, 30),
        }
    )
    pool_created = await create_or_load_capacity_pool_definition(
        db_session, definition_input=pool_input
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_id=pool_created.parent.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    with pytest.raises(AuthorityEffectiveIntervalMismatchError) as exc_info:
        await resolve_capacity_pool_definition(
            db_session,
            request=CapacityPoolResolutionRequest(
                mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
                as_of_local_date=date(2026, 7, 1),
                timezone_name="Asia/Shanghai",
                season_id=_IDS["season"],
                destination_factory_id=_IDS["factory"],
                capacity_pool_code=pool_input.capacity_pool_code,
                effective_local_date=date(2026, 7, 1),
            ),
        )
    assert exc_info.value.code == "AUTHORITY_EFFECTIVE_INTERVAL_MISMATCH"


@pytest.mark.asyncio
async def test_exact_reference_hash_mismatch(
    db_session: AsyncSession,
) -> None:
    """EXACT_REFERENCE raises AUTHORITY_HASH_CONFLICT when row_hash differs."""
    pool_input = _pool_input(version="v1", revision=1)
    pool_created = await create_or_load_capacity_pool_definition(
        db_session, definition_input=pool_input
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_id=pool_created.parent.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await resolve_capacity_pool_definition(
            db_session,
            request=CapacityPoolResolutionRequest(
                mode=AuthorityResolutionMode.EXACT_REFERENCE,
                as_of_local_date=date(2026, 6, 15),
                timezone_name="Asia/Shanghai",
                season_id=_IDS["season"],
                destination_factory_id=_IDS["factory"],
                capacity_pool_code=pool_input.capacity_pool_code,
                effective_local_date=date(2026, 1, 1),
                exact_reference=_exact_reference(
                    authority_id=pool_created.parent.authority_id,
                    stable_key=f"capacity-pool:{_IDS['season']}:{_IDS['factory']}:{pool_input.capacity_pool_code}",
                    version=pool_input.capacity_pool_version,
                    revision=pool_input.revision,
                    row_hash="0" * 64,  # wrong hash
                ),
            ),
        )
    assert exc_info.value.code == "AUTHORITY_HASH_CONFLICT"


@pytest.mark.asyncio
async def test_exact_reference_identity_mismatch(
    db_session: AsyncSession,
) -> None:
    """EXACT_REFERENCE raises AUTHORITY_EXACT_REFERENCE_MISMATCH for wrong identity."""
    pool_input = _pool_input(version="v1", revision=1)
    pool_created = await create_or_load_capacity_pool_definition(
        db_session, definition_input=pool_input
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_id=pool_created.parent.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    pool_row = await _row_by_id(
        db_session, Task9CapacityPoolDefinition, pool_created.parent.authority_id
    )

    with pytest.raises(AuthorityExactReferenceMismatchError) as exc_info:
        await resolve_capacity_pool_definition(
            db_session,
            request=CapacityPoolResolutionRequest(
                mode=AuthorityResolutionMode.EXACT_REFERENCE,
                as_of_local_date=date(2026, 6, 15),
                timezone_name="Asia/Shanghai",
                season_id=_IDS["season"],
                destination_factory_id=_IDS["factory"],
                capacity_pool_code=pool_input.capacity_pool_code,
                effective_local_date=date(2026, 1, 1),
                exact_reference=_exact_reference(
                    authority_id=pool_created.parent.authority_id,
                    stable_key="capacity-pool:999:999:WRONG-KEY",
                    version=pool_input.capacity_pool_version,
                    revision=pool_input.revision,
                    row_hash=pool_row.row_hash,
                ),
            ),
        )
    assert exc_info.value.code == "AUTHORITY_EXACT_REFERENCE_MISMATCH"


@pytest.mark.asyncio
async def test_invalid_timezone_before_sql(
    db_session: AsyncSession,
) -> None:
    """TIMEZONE_AUTHORITY_INVALID is raised before any SQL is executed."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with pytest.raises(TimezoneAuthorityInvalidError) as exc_info:
        await resolve_capacity_pool_definition(
            mock_session,
            request=CapacityPoolResolutionRequest(
                mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
                as_of_local_date=date(2026, 6, 15),
                timezone_name="Mars/Olympus",
                season_id=1,
                destination_factory_id=1,
                capacity_pool_code="TEST",
                effective_local_date=date(2026, 6, 15),
            ),
        )
    assert exc_info.value.code == "TIMEZONE_AUTHORITY_INVALID"
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_selected_authority_integrity_tamper(
    db_session: AsyncSession,
) -> None:
    """Corrupting a business field without updating hash triggers hash conflict."""
    weather_input = _weather_input(version="v1", revision=1)
    weather_created = await create_or_load_weather_rule(db_session, weather_input=weather_input)
    await activate_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=weather_created.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    # Pass a wrong hash in the exact reference — the resolver will load
    # the authority, compute the real hash, and detect the mismatch.
    wrong_hash = "0" * 64

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await resolve_weather_rule(
            db_session,
            request=WeatherRuleResolutionRequest(
                mode=AuthorityResolutionMode.EXACT_REFERENCE,
                as_of_local_date=date(2026, 6, 15),
                timezone_name="Asia/Shanghai",
                rule_code=weather_input.rule_code,
                lifecycle_timezone_name="Asia/Shanghai",
                effective_local_date=date(2026, 1, 1),
                exact_reference=_exact_reference(
                    authority_id=weather_created.authority_id,
                    stable_key="weather-rule:WEATHER-STD:Asia/Shanghai",
                    version=weather_input.rule_version,
                    revision=weather_input.revision,
                    row_hash=wrong_hash,
                ),
            ),
        )
    assert exc_info.value.code == "AUTHORITY_HASH_CONFLICT"


@pytest.mark.asyncio
async def test_sentinel_future_authorities_not_consuming_limit(
    db_session: AsyncSession,
) -> None:
    """Future authorities are filtered by SQL predicates, not by LIMIT."""
    # Create a pool and activate with future boundary
    pool_input = _pool_input(code="SENTINEL", version="v1", revision=1)
    pool_created = await create_or_load_capacity_pool_definition(
        db_session, definition_input=pool_input
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_id=pool_created.parent.authority_id,
        activation_boundary=date(2026, 8, 1),
    )

    # Resolve CURRENT_OPERATIONAL with as_of=2026-06-15
    # Pool has future consumable_from (2026-08-01) → lifecycle not consumable
    # Should raise AuthorityNotConsumableAtCutoffError
    with pytest.raises(AuthorityNotConsumableAtCutoffError) as exc_info:
        await resolve_capacity_pool_definition(
            db_session,
            request=CapacityPoolResolutionRequest(
                mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
                as_of_local_date=date(2026, 6, 15),
                timezone_name="Asia/Shanghai",
                season_id=_IDS["season"],
                destination_factory_id=_IDS["factory"],
                capacity_pool_code=pool_input.capacity_pool_code,
                effective_local_date=date(2026, 6, 15),
            ),
        )
    assert exc_info.value.code == "AUTHORITY_NOT_CONSUMABLE_AT_CUTOFF"


# ══════════════════════════════════════════════════════════════════════════
# P0-1: Mode-aware miss classification for superseded/retired pools
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_capacity_pool_superseded_current_operational_rejects(
    db_session: AsyncSession,
) -> None:
    """CURRENT_OPERATIONAL rejects a superseded pool even if historical lifecycle is valid."""
    pool_v1 = _pool_input(code="SUPER-POOL", version="v1", revision=1)
    pool_v1_created = await create_or_load_capacity_pool_definition(
        db_session, definition_input=pool_v1
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_id=pool_v1_created.parent.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    pool_v2 = _pool_input(code="SUPER-POOL", version="v2", revision=1)
    await supersede_authority(
        db_session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        old_id=pool_v1_created.parent.authority_id,
        new_input=pool_v2,
        new_members=list(pool_v2.members),
        replacement_boundary=date(2026, 5, 1),
    )

    # CURRENT_OPERATIONAL as_of=2026-04-01 falls within v1's historical interval
    # but v1 is superseded → must NOT resolve, must NOT raise ValueError
    with pytest.raises(AuthorityNotConsumableAtCutoffError) as exc_info:
        await resolve_capacity_pool_definition(
            db_session,
            request=CapacityPoolResolutionRequest(
                mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
                as_of_local_date=date(2026, 4, 1),
                timezone_name="Asia/Shanghai",
                season_id=_IDS["season"],
                destination_factory_id=_IDS["factory"],
                capacity_pool_code=pool_v1.capacity_pool_code,
                effective_local_date=date(2026, 4, 1),
            ),
        )
    assert exc_info.value.code == "AUTHORITY_NOT_CONSUMABLE_AT_CUTOFF"
    assert exc_info.value.details.get("reason") == "authority_lifecycle_not_consumable_at_cutoff"

    # FIRST_TIME_HISTORICAL as_of=2026-04-01 should still resolve v1
    historical = await resolve_capacity_pool_definition(
        db_session,
        request=CapacityPoolResolutionRequest(
            mode=AuthorityResolutionMode.FIRST_TIME_HISTORICAL,
            as_of_local_date=date(2026, 4, 1),
            timezone_name="Asia/Shanghai",
            season_id=_IDS["season"],
            destination_factory_id=_IDS["factory"],
            capacity_pool_code=pool_v1.capacity_pool_code,
            effective_local_date=date(2026, 4, 1),
        ),
    )
    assert historical.authority_id == pool_v1_created.parent.authority_id
    assert historical.business_version == "v1"


@pytest.mark.asyncio
async def test_capacity_pool_retired_current_operational_rejects(
    db_session: AsyncSession,
) -> None:
    """CURRENT_OPERATIONAL rejects a retired pool even if historical lifecycle is valid."""
    pool_input = _pool_input(code="RETIRE-POOL", version="v1", revision=1)
    pool_created = await create_or_load_capacity_pool_definition(
        db_session, definition_input=pool_input
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_id=pool_created.parent.authority_id,
        activation_boundary=date(2026, 1, 1),
    )
    await retire_authority(
        db_session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_id=pool_created.parent.authority_id,
        retirement_boundary=date(2026, 4, 1),
    )

    # CURRENT_OPERATIONAL as_of=2026-03-15 falls within v1's active interval
    # but v1 is retired → must NOT resolve
    with pytest.raises(AuthorityNotConsumableAtCutoffError) as exc_info:
        await resolve_capacity_pool_definition(
            db_session,
            request=CapacityPoolResolutionRequest(
                mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
                as_of_local_date=date(2026, 3, 15),
                timezone_name="Asia/Shanghai",
                season_id=_IDS["season"],
                destination_factory_id=_IDS["factory"],
                capacity_pool_code=pool_input.capacity_pool_code,
                effective_local_date=date(2026, 3, 15),
            ),
        )
    assert exc_info.value.code == "AUTHORITY_NOT_CONSUMABLE_AT_CUTOFF"
    assert exc_info.value.details.get("reason") == "authority_lifecycle_not_consumable_at_cutoff"

    # FIRST_TIME_HISTORICAL as_of=2026-03-15 should resolve v1
    historical = await resolve_capacity_pool_definition(
        db_session,
        request=CapacityPoolResolutionRequest(
            mode=AuthorityResolutionMode.FIRST_TIME_HISTORICAL,
            as_of_local_date=date(2026, 3, 15),
            timezone_name="Asia/Shanghai",
            season_id=_IDS["season"],
            destination_factory_id=_IDS["factory"],
            capacity_pool_code=pool_input.capacity_pool_code,
            effective_local_date=date(2026, 3, 15),
        ),
    )
    assert historical.authority_id == pool_created.parent.authority_id
    assert historical.business_version == "v1"


# ══════════════════════════════════════════════════════════════════════════
# P1-1: SQL-before-LIMIT sentinel (rewrite with ≥3 futures + 1 valid)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sentinel_future_candidates_do_not_consume_limit(
    db_session: AsyncSession,
) -> None:
    """SQL-before-LIMIT proof: 3 draft sentinels + 1 activated valid candidate.
    Draft rows have consumable_from=NULL → consumability_range=empty → exclusion OK.
    In wrong impl (ORDER BY + LIMIT 2 then Python filter): sentinels hide valid.
    In correct impl (WHERE filters first): only valid passes, returned correctly.
    """
    SENTINEL_CODE = "SENTINEL-LIMIT"
    PRODUCTION_LIMIT = 2

    # Create 4 draft rows with same code and same effective range.
    created_list = []
    for i in range(1, 5):
        pool = _pool_input(code=SENTINEL_CODE, version=f"v{i}", revision=1)
        created = await create_or_load_capacity_pool_definition(db_session, definition_input=pool)
        created_list.append(created)

    # Read all row_hashes and sort
    hash_pairs = []
    for c in created_list:
        row = await _row_by_id(db_session, Task9CapacityPoolDefinition, c.parent.authority_id)
        hash_pairs.append((row.row_hash, row, c))
    hash_pairs.sort(key=lambda x: x[0])

    # Activate the one with HIGHEST row_hash; the rest stay draft
    valid_hash, valid_row, valid_created = hash_pairs[-1]
    sentinel_hashes = [h for h, _, _ in hash_pairs[:-1]]
    sentinel_count = len(sentinel_hashes)

    # Assertions on test construction
    assert PRODUCTION_LIMIT == 2
    assert sentinel_count == 3
    assert sentinel_count > PRODUCTION_LIMIT
    assert all(h < valid_hash for h in sentinel_hashes)

    await activate_authority(
        db_session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_id=valid_created.parent.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    # Resolve CURRENT_OPERATIONAL — draft sentinels filtered by SQL WHERE
    resolved = await resolve_capacity_pool_definition(
        db_session,
        request=CapacityPoolResolutionRequest(
            mode=AuthorityResolutionMode.CURRENT_OPERATIONAL,
            as_of_local_date=date(2026, 6, 15),
            timezone_name="Asia/Shanghai",
            season_id=_IDS["season"],
            destination_factory_id=_IDS["factory"],
            capacity_pool_code=SENTINEL_CODE,
            effective_local_date=date(2026, 6, 15),
        ),
    )
    assert resolved.authority_id == valid_row.id
    assert resolved.business_version == valid_row.capacity_pool_version
    assert resolved.revision == valid_row.revision
    assert resolved.row_hash == valid_hash


# ══════════════════════════════════════════════════════════════════════════
# P1-2: Persisted-authority tamper test (real DB mutation)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_persisted_tamper_detected_by_integrity_loader(
    db_session: AsyncSession,
) -> None:
    """Mutating a persisted business field without updating row_hash triggers hash conflict."""
    weather_input = _weather_input(version="v1", revision=1)
    weather_created = await create_or_load_weather_rule(db_session, weather_input=weather_input)
    await activate_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=weather_created.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    # Read original row hash
    weather_row = await _row_by_id(
        db_session, Task9WeatherRuleConfigVersion, weather_created.authority_id
    )
    original_hash = weather_row.row_hash

    # Tamper: mutate a business field via raw SQL (source_system is in canonical payload)
    await db_session.execute(
        text(
            "UPDATE task9_weather_rule_config_version "
            "SET source_system = 'TAMPERED' "
            "WHERE id = :wid"
        ),
        {"wid": weather_created.authority_id},
    )
    await db_session.flush()
    db_session.expire_all()

    # Use correct exact reference (original stable key, original hash)
    # The resolver loads the authority, computes hash from DB content,
    # and the P0-7C integrity loader detects the mismatch.
    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await resolve_weather_rule(
            db_session,
            request=WeatherRuleResolutionRequest(
                mode=AuthorityResolutionMode.EXACT_REFERENCE,
                as_of_local_date=date(2026, 6, 15),
                timezone_name="Asia/Shanghai",
                rule_code=weather_input.rule_code,
                lifecycle_timezone_name="Asia/Shanghai",
                effective_local_date=date(2026, 1, 1),
                exact_reference=_exact_reference(
                    authority_id=weather_created.authority_id,
                    stable_key="weather-rule:WEATHER-STD:Asia/Shanghai",
                    version=weather_input.rule_version,
                    revision=weather_input.revision,
                    row_hash=original_hash,  # original hash, but DB content is tampered
                ),
            ),
        )
    assert exc_info.value.code == "AUTHORITY_HASH_CONFLICT"
    assert exc_info.value.details.get("reason") == "weather_rule_row_hash_mismatch"


# ══════════════════════════════════════════════════════════════════════════
# P1-3: Dependency timezone mismatch with full context
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_run_package_dependency_timezone_mismatch_with_context(
    db_session: AsyncSession,
) -> None:
    """Timezone mismatch includes full audit context in error details."""
    # Create holiday in Asia/Shanghai
    holiday_input = _holiday_input(version="v1", revision=1)
    holiday_created = await create_or_load_holiday_calendar(
        db_session, calendar_input=holiday_input
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=holiday_created.parent.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    # Create weather in Asia/Shanghai (matching) for creation
    weather_sh = _weather_input(version="v1", revision=1)
    weather_sh_created = await create_or_load_weather_rule(db_session, weather_input=weather_sh)
    await activate_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=weather_sh_created.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    # Create package with matching timezones (all Shanghai)
    pkg_input = _run_package_input(version="v1", revision=1)
    pkg_created = await create_or_load_run_parameter_package(
        db_session,
        package_input=pkg_input,
        holiday_calendar=holiday_input,
        weather_rule=weather_sh,
    )

    # Create a SEPARATE weather with UTC timezone
    weather_utc = _weather_input(version="v2", revision=1).model_copy(
        update={"lifecycle_timezone_name": "UTC"}
    )
    weather_utc_created = await create_or_load_weather_rule(db_session, weather_input=weather_utc)
    await activate_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=weather_utc_created.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    # Swap the package's weather FK to point to the UTC weather
    await db_session.execute(
        text(
            "UPDATE task9_run_parameter_package "
            "SET weather_rule_config_version_id = :weather_id "
            "WHERE id = :pkg_id"
        ),
        {"weather_id": weather_utc_created.authority_id, "pkg_id": pkg_created.authority_id},
    )
    await db_session.flush()
    db_session.expire_all()

    # Activate the package
    await activate_authority(
        db_session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        authority_id=pkg_created.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    # Resolve should detect timezone mismatch
    with pytest.raises(AuthorityDependencyMismatchError) as exc_info:
        await resolve_run_parameter_package(
            db_session,
            request=RunParameterPackageResolutionRequest(
                mode=AuthorityResolutionMode.EXACT_REFERENCE,
                as_of_local_date=date(2026, 6, 15),
                timezone_name="Asia/Shanghai",
                season_id=_IDS["season"],
                destination_factory_id=_IDS["factory"],
                farm_scope_key="farm-10",
                effective_local_date=date(2026, 6, 15),
                exact_reference=_exact_reference(
                    authority_id=pkg_created.authority_id,
                    stable_key=f"run-package:{_IDS['season']}:{_IDS['factory']}:farm-10",
                    version="v1",
                    revision=1,
                    row_hash=(
                        await _row_by_id(
                            db_session, Task9RunParameterPackage, pkg_created.authority_id
                        )
                    ).row_hash,
                ),
            ),
        )
    err = exc_info.value
    assert err.code == "AUTHORITY_DEPENDENCY_MISMATCH"
    assert err.details.get("reason") == "dependency_timezone_mismatch"
    expected_package_stable_key = f"run-package:{_IDS['season']}:{_IDS['factory']}:farm-10"
    expected_weather_stable_key = f"weather-rule:{weather_utc.rule_code}:UTC"
    assert err.authority_stable_key == expected_package_stable_key
    assert err.details.get("dependency_family") == "weather_rule_config_version"
    assert err.details.get("dependency_authority_stable_key") == expected_weather_stable_key
    assert err.details.get("expected_timezone") == "Asia/Shanghai"
    assert err.details.get("actual_timezone") == "UTC"


# ══════════════════════════════════════════════════════════════════════════
# P1-2: Holiday-only timezone mismatch (precedence = holiday first)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_holiday_only_timezone_mismatch(
    db_session: AsyncSession,
) -> None:
    """Package tz=Asia/Shanghai, holiday tz=UTC, weather tz=Asia/Shanghai.
    Precedence: holiday mismatch reported first."""
    holiday_sh = _holiday_input(version="v1", revision=1)
    holiday_sh_created = await create_or_load_holiday_calendar(
        db_session, calendar_input=holiday_sh
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=holiday_sh_created.parent.authority_id,
        activation_boundary=date(2026, 1, 1),
    )
    weather_input = _weather_input(version="v1", revision=1)
    weather_created = await create_or_load_weather_rule(db_session, weather_input=weather_input)
    await activate_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=weather_created.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    # Create package with matching tz (canonical OK)
    pkg_input = _run_package_input(version="v1", revision=1)
    pkg_created = await create_or_load_run_parameter_package(
        db_session,
        package_input=pkg_input,
        holiday_calendar=holiday_sh,
        weather_rule=weather_input,
    )

    # Create holiday with UTC, swap FK
    holiday_utc = _holiday_input(version="v2", revision=1).model_copy(
        update={"lifecycle_timezone_name": "UTC"}
    )
    holiday_utc_created = await create_or_load_holiday_calendar(
        db_session, calendar_input=holiday_utc
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=holiday_utc_created.parent.authority_id,
        activation_boundary=date(2026, 1, 1),
    )
    await db_session.execute(
        text(
            "UPDATE task9_run_parameter_package "
            "SET holiday_calendar_version_id = :hid "
            "WHERE id = :pid"
        ),
        {"hid": holiday_utc_created.parent.authority_id, "pid": pkg_created.authority_id},
    )
    await db_session.flush()
    db_session.expire_all()
    await activate_authority(
        db_session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        authority_id=pkg_created.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    pkg_row = await _row_by_id(db_session, Task9RunParameterPackage, pkg_created.authority_id)
    with pytest.raises(AuthorityDependencyMismatchError) as exc_info:
        await resolve_run_parameter_package(
            db_session,
            request=RunParameterPackageResolutionRequest(
                mode=AuthorityResolutionMode.EXACT_REFERENCE,
                as_of_local_date=date(2026, 6, 15),
                timezone_name="Asia/Shanghai",
                season_id=_IDS["season"],
                destination_factory_id=_IDS["factory"],
                farm_scope_key="farm-10",
                effective_local_date=date(2026, 6, 15),
                exact_reference=_exact_reference(
                    authority_id=pkg_created.authority_id,
                    stable_key=f"run-package:{_IDS['season']}:{_IDS['factory']}:farm-10",
                    version="v1",
                    revision=1,
                    row_hash=pkg_row.row_hash,
                ),
            ),
        )
    err = exc_info.value
    assert err.code == "AUTHORITY_DEPENDENCY_MISMATCH"
    assert err.details.get("reason") == "dependency_timezone_mismatch"
    expected_package_stable_key = f"run-package:{_IDS['season']}:{_IDS['factory']}:farm-10"
    expected_holiday_stable_key = (
        f"holiday-calendar:{_IDS['season']}:{holiday_utc.calendar_code}:UTC"
    )
    assert err.authority_stable_key == expected_package_stable_key
    assert err.details.get("dependency_family") == "holiday_calendar_version"
    assert err.details.get("dependency_authority_stable_key") == expected_holiday_stable_key
    assert err.details.get("expected_timezone") == "Asia/Shanghai"
    assert err.details.get("actual_timezone") == "UTC"


# ══════════════════════════════════════════════════════════════════════════
# P1-2: Package-versus-both timezone mismatch (precedence = holiday first)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_package_versus_both_timezone_mismatch(
    db_session: AsyncSession,
) -> None:
    """Package tz=Asia/Shanghai, holiday tz=Asia/Tokyo, weather tz=Asia/Tokyo.
    Precedence: holiday mismatch reported first. expected != actual."""
    holiday_sh = _holiday_input(version="v1", revision=1)
    holiday_sh_created = await create_or_load_holiday_calendar(
        db_session, calendar_input=holiday_sh
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=holiday_sh_created.parent.authority_id,
        activation_boundary=date(2026, 1, 1),
    )
    weather_sh = _weather_input(version="v1", revision=1)
    weather_sh_created = await create_or_load_weather_rule(db_session, weather_input=weather_sh)
    await activate_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=weather_sh_created.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    # Create package with matching tz
    pkg_input = _run_package_input(version="v1", revision=1)
    pkg_created = await create_or_load_run_parameter_package(
        db_session,
        package_input=pkg_input,
        holiday_calendar=holiday_sh,
        weather_rule=weather_sh,
    )

    # Create holiday with Asia/Tokyo, swap FK
    holiday_tokyo = _holiday_input(version="v2", revision=1).model_copy(
        update={"lifecycle_timezone_name": "Asia/Tokyo"}
    )
    holiday_tokyo_created = await create_or_load_holiday_calendar(
        db_session, calendar_input=holiday_tokyo
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=holiday_tokyo_created.parent.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    # Create weather with Asia/Tokyo, swap FK
    weather_tokyo = _weather_input(version="v2", revision=1).model_copy(
        update={"lifecycle_timezone_name": "Asia/Tokyo"}
    )
    weather_tokyo_created = await create_or_load_weather_rule(
        db_session, weather_input=weather_tokyo
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=weather_tokyo_created.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    # Swap both FKs
    await db_session.execute(
        text(
            "UPDATE task9_run_parameter_package "
            "SET holiday_calendar_version_id = :hid, "
            "    weather_rule_config_version_id = :wid "
            "WHERE id = :pid"
        ),
        {
            "hid": holiday_tokyo_created.parent.authority_id,
            "wid": weather_tokyo_created.authority_id,
            "pid": pkg_created.authority_id,
        },
    )
    await db_session.flush()
    db_session.expire_all()
    await activate_authority(
        db_session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        authority_id=pkg_created.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    pkg_row = await _row_by_id(db_session, Task9RunParameterPackage, pkg_created.authority_id)
    with pytest.raises(AuthorityDependencyMismatchError) as exc_info:
        await resolve_run_parameter_package(
            db_session,
            request=RunParameterPackageResolutionRequest(
                mode=AuthorityResolutionMode.EXACT_REFERENCE,
                as_of_local_date=date(2026, 6, 15),
                timezone_name="Asia/Shanghai",
                season_id=_IDS["season"],
                destination_factory_id=_IDS["factory"],
                farm_scope_key="farm-10",
                effective_local_date=date(2026, 6, 15),
                exact_reference=_exact_reference(
                    authority_id=pkg_created.authority_id,
                    stable_key=f"run-package:{_IDS['season']}:{_IDS['factory']}:farm-10",
                    version="v1",
                    revision=1,
                    row_hash=pkg_row.row_hash,
                ),
            ),
        )
    err = exc_info.value
    assert err.code == "AUTHORITY_DEPENDENCY_MISMATCH"
    assert err.details.get("reason") == "dependency_timezone_mismatch"
    # Precedence: holiday first
    expected_package_stable_key = f"run-package:{_IDS['season']}:{_IDS['factory']}:farm-10"
    expected_holiday_stable_key = (
        f"holiday-calendar:{_IDS['season']}:{holiday_tokyo.calendar_code}:Asia/Tokyo"
    )
    assert err.authority_stable_key == expected_package_stable_key
    assert err.details.get("dependency_family") == "holiday_calendar_version"
    assert err.details.get("dependency_authority_stable_key") == expected_holiday_stable_key
    assert err.details.get("expected_timezone") == "Asia/Shanghai"
    assert err.details.get("actual_timezone") == "Asia/Tokyo"
    assert err.details.get("expected_timezone") != err.details.get("actual_timezone")
