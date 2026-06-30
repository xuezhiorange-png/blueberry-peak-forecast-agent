from __future__ import annotations

import asyncio
import os
from datetime import date
from typing import cast

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import AsyncSessionMaker
from backend.app.harvest_state.authority_canonical import make_authority_row_hash
from backend.app.harvest_state.authority_repository import (
    AuthorityFamily,
    create_or_load_capacity_pool_definition,
    create_or_load_daily_capacity_authority,
    create_or_load_holiday_calendar_version,
    create_or_load_initial_inventory_snapshot,
    create_or_load_mature_inventory_loss_authority,
    create_or_load_run_parameter_package,
    create_or_load_weather_rule_config_version,
    load_authority_by_id,
    load_authority_by_persistent_identity,
    load_authority_by_row_hash,
    load_capacity_pool_definition_by_business_key,
    load_capacity_pool_definition_by_id,
    load_daily_capacity_authority_by_business_key,
    load_daily_capacity_authority_by_id,
    load_holiday_calendar_version_by_business_key,
    load_holiday_calendar_version_by_id,
    load_initial_inventory_snapshot_by_business_key,
    load_initial_inventory_snapshot_by_id,
    load_mature_inventory_loss_authority_by_business_key,
    load_mature_inventory_loss_authority_by_id,
    load_run_parameter_package_by_business_key,
    load_run_parameter_package_by_id,
    load_weather_rule_config_version_by_business_key,
    load_weather_rule_config_version_by_id,
    replace_authority,
    replace_run_package_with_dependencies,
    retire_authority,
)
from backend.app.harvest_state.authority_repository_errors import (
    AuthorityDependencyConflictError,
    AuthorityHashConflictError,
    AuthorityVersionConflictError,
)
from backend.app.harvest_state.authority_schemas import (
    Task9CapacityPoolDefinitionSemanticBundle,
    Task9DailyCapacitySemanticInput,
    Task9HolidayCalendarSemanticBundle,
    Task9InitialInventorySemanticBundle,
    Task9MatureLossSemanticInput,
    Task9RunParameterPackageBundleSchema,
    Task9RunParameterPackageSemanticInput,
    Task9WeatherRuleSemanticInput,
)
from backend.app.models import (
    Task9AuthorityLifecycleEvent,
    Task9CapacityPoolDefinition,
    Task9CapacityPoolMember,
    Task9HolidayCalendarVersion,
    Task9RunParameterPackage,
    Task9WeatherRuleConfigVersion,
)
from backend.tests.harvest_state.test_authority_schemas import (
    _capacity_pool_definition_payload,
    _daily_capacity_payload,
    _holiday_calendar_payload,
    _initial_inventory_payload,
    _mature_loss_payload,
    _run_parameter_package_payload,
    _weather_rule_payload,
)
from backend.tests.integration.test_task9_authority_migration_postgres import _seed_dimensions


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("RUN_POSTGRES_INTEGRATION=1 required")
    if os.getenv("APP_ENV") != "test":
        pytest.skip("APP_ENV=test required")


def _pool_bundle(dimensions: dict[str, int]) -> Task9CapacityPoolDefinitionSemanticBundle:
    payload = _capacity_pool_definition_payload()
    payload["season_id"] = dimensions["season_id"]
    payload["destination_factory_id"] = dimensions["factory_id"]
    payload["members"] = [
        {
            "farm_id": dimensions["farm_id"],
            "subfarm_id": None,
            "variety_id": dimensions["variety_id"],
        }
    ]
    return Task9CapacityPoolDefinitionSemanticBundle.model_validate(payload)


def _daily_input(dimensions: dict[str, int]) -> Task9DailyCapacitySemanticInput:
    payload = _daily_capacity_payload()
    payload["season_id"] = dimensions["season_id"]
    payload["destination_factory_id"] = dimensions["factory_id"]
    payload["capacity_pool_code"] = "POOL-A"
    payload["capacity_pool_version"] = "v1"
    payload["capacity_pool_revision"] = 1
    payload["source_record_key"] = "daily-capacity:1:2:POOL-A:v1:1:2026-02-01:1"
    return Task9DailyCapacitySemanticInput.model_validate(payload)


def _holiday_bundle(dimensions: dict[str, int]) -> Task9HolidayCalendarSemanticBundle:
    payload = _holiday_calendar_payload()
    payload["season_id"] = dimensions["season_id"]
    return Task9HolidayCalendarSemanticBundle.model_validate(payload)


def _weather_input() -> Task9WeatherRuleSemanticInput:
    return Task9WeatherRuleSemanticInput.model_validate(_weather_rule_payload())


def _package_bundle(dimensions: dict[str, int]) -> Task9RunParameterPackageBundleSchema:
    package_payload = _run_parameter_package_payload()
    package_payload["season_id"] = dimensions["season_id"]
    package_payload["destination_factory_id"] = dimensions["factory_id"]
    package = Task9RunParameterPackageSemanticInput.model_validate(package_payload)
    return Task9RunParameterPackageBundleSchema(
        package=package,
        holiday_calendar=_holiday_bundle(dimensions),
        weather_rule=_weather_input(),
    )


def _inventory_bundle(dimensions: dict[str, int]) -> Task9InitialInventorySemanticBundle:
    payload = _initial_inventory_payload()
    payload["season_id"] = dimensions["season_id"]
    payload["destination_factory_id"] = dimensions["factory_id"]
    for cohort in payload["cohorts"]:
        cohort["farm_id"] = dimensions["farm_id"]
        cohort["subfarm_id"] = None
        cohort["variety_id"] = dimensions["variety_id"]
    return Task9InitialInventorySemanticBundle.model_validate(payload)


def _mature_loss_input(dimensions: dict[str, int]) -> Task9MatureLossSemanticInput:
    payload = _mature_loss_payload()
    payload["season_id"] = dimensions["season_id"]
    payload["destination_factory_id"] = dimensions["factory_id"]
    return Task9MatureLossSemanticInput.model_validate(payload)


async def _create_full_authority_set(
    session: AsyncSession, dimensions: dict[str, int]
) -> dict[str, int]:
    pool = await create_or_load_capacity_pool_definition(session, bundle=_pool_bundle(dimensions))
    daily = await create_or_load_daily_capacity_authority(
        session, authority=_daily_input(dimensions)
    )
    holiday = await create_or_load_holiday_calendar_version(
        session, bundle=_holiday_bundle(dimensions)
    )
    weather = await create_or_load_weather_rule_config_version(session, authority=_weather_input())
    package = await create_or_load_run_parameter_package(
        session, bundle=_package_bundle(dimensions)
    )
    inventory = await create_or_load_initial_inventory_snapshot(
        session, bundle=_inventory_bundle(dimensions)
    )
    mature_loss = await create_or_load_mature_inventory_loss_authority(
        session, authority=_mature_loss_input(dimensions)
    )
    await session.commit()
    return {
        "pool_id": pool.authority.id,
        "daily_id": daily.authority.id,
        "holiday_id": holiday.authority.id,
        "weather_id": weather.authority.id,
        "package_id": package.authority.id,
        "inventory_id": inventory.authority.id,
        "mature_loss_id": mature_loss.authority.id,
    }


async def _count_rows(session: AsyncSession, model: type[object]) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


@pytest.mark.asyncio
async def test_capacity_pool_create_or_load_is_idempotent_and_detects_conflicts() -> None:
    _require_postgres()
    dims = await _seed_dimensions()
    async with AsyncSessionMaker() as session:
        created = await create_or_load_capacity_pool_definition(session, bundle=_pool_bundle(dims))
        await session.commit()
    async with AsyncSessionMaker() as session:
        loaded = await create_or_load_capacity_pool_definition(session, bundle=_pool_bundle(dims))
        assert loaded.created is False
        assert loaded.authority.id == created.authority.id
        assert (
            await session.scalar(select(func.count()).select_from(Task9AuthorityLifecycleEvent))
            == 2
        )
    changed_payload = _capacity_pool_definition_payload()
    changed_payload["season_id"] = dims["season_id"]
    changed_payload["destination_factory_id"] = dims["factory_id"]
    changed_payload["members"] = [
        {"farm_id": dims["farm_id"], "subfarm_id": None, "variety_id": dims["variety_id"]},
        {
            "farm_id": dims["farm_id"],
            "subfarm_id": dims["subfarm_id"],
            "variety_id": dims["variety_id"],
        },
    ]
    changed_bundle = Task9CapacityPoolDefinitionSemanticBundle.model_validate(changed_payload)
    async with AsyncSessionMaker() as session:
        with pytest.raises(AuthorityVersionConflictError) as excinfo:
            await create_or_load_capacity_pool_definition(session, bundle=changed_bundle)
        assert excinfo.value.code == "AUTHORITY_VERSION_CONFLICT"
    async with AsyncSessionMaker() as session:
        await session.execute(
            text("UPDATE task9_capacity_pool_definition SET row_hash = :row_hash WHERE id = :id"),
            {"row_hash": "f" * 64, "id": created.authority.id},
        )
        await session.commit()
    async with AsyncSessionMaker() as session:
        with pytest.raises(AuthorityHashConflictError) as excinfo:
            await load_capacity_pool_definition_by_business_key(
                session,
                season_id=dims["season_id"],
                destination_factory_id=dims["factory_id"],
                capacity_pool_code="POOL-A",
                capacity_pool_version="v1",
                revision=1,
            )
        assert excinfo.value.code == "AUTHORITY_HASH_CONFLICT"


@pytest.mark.asyncio
async def test_exact_load_locators_cover_all_seven_families() -> None:
    _require_postgres()
    dims = await _seed_dimensions()
    async with AsyncSessionMaker() as session:
        ids = await _create_full_authority_set(session, dims)
    async with AsyncSessionMaker() as session:
        by_id_rows = [
            await load_capacity_pool_definition_by_id(session, authority_id=ids["pool_id"]),
            await load_daily_capacity_authority_by_id(session, authority_id=ids["daily_id"]),
            await load_holiday_calendar_version_by_id(session, authority_id=ids["holiday_id"]),
            await load_weather_rule_config_version_by_id(session, authority_id=ids["weather_id"]),
            await load_run_parameter_package_by_id(session, authority_id=ids["package_id"]),
            await load_initial_inventory_snapshot_by_id(session, authority_id=ids["inventory_id"]),
            await load_mature_inventory_loss_authority_by_id(
                session, authority_id=ids["mature_loss_id"]
            ),
        ]
        pool = await load_capacity_pool_definition_by_business_key(
            session,
            season_id=dims["season_id"],
            destination_factory_id=dims["factory_id"],
            capacity_pool_code="POOL-A",
            capacity_pool_version="v1",
            revision=1,
        )
        daily = await load_daily_capacity_authority_by_business_key(
            session,
            season_id=dims["season_id"],
            destination_factory_id=dims["factory_id"],
            capacity_pool_code="POOL-A",
            capacity_pool_version="v1",
            capacity_pool_revision=1,
            capacity_date=date(2026, 2, 1),
            daily_capacity_revision=1,
        )
        holiday = await load_holiday_calendar_version_by_business_key(
            session,
            season_id=dims["season_id"],
            calendar_code="CN-SH",
            lifecycle_timezone_name="Asia/Shanghai",
            calendar_version="calendar-v1",
            revision=1,
        )
        weather = await load_weather_rule_config_version_by_business_key(
            session,
            rule_code="wx-rule",
            lifecycle_timezone_name="Asia/Shanghai",
            rule_version="wx-v1",
            revision=1,
        )
        package = await load_run_parameter_package_by_business_key(
            session,
            season_id=dims["season_id"],
            destination_factory_id=dims["factory_id"],
            farm_scope_key="farm-scope:10",
            package_version="pkg-v1",
            revision=1,
        )
        inventory = await load_initial_inventory_snapshot_by_business_key(
            session,
            season_id=dims["season_id"],
            destination_factory_id=dims["factory_id"],
            opening_state_date=date(2026, 2, 1),
            snapshot_version="snap-v1",
            revision=1,
        )
        mature_loss = await load_mature_inventory_loss_authority_by_business_key(
            session,
            season_id=dims["season_id"],
            destination_factory_id=dims["factory_id"],
            state_date=date(2026, 2, 1),
            capacity_pool_code="POOL-A",
            forecast_quantile="P50",
            loss_version="loss-v1",
            revision=1,
        )
        rows = [pool, daily, holiday, weather, package, inventory, mature_loss]
        assert {row.id for row in rows} == set(ids.values())
        assert {row.id for row in by_id_rows} == set(ids.values())
        by_identity_rows = [
            await load_authority_by_persistent_identity(
                session,
                family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
                stable_key="capacity-pool:1:2:POOL-A",
                business_version="v1",
                revision=1,
            ),
            await load_authority_by_persistent_identity(
                session,
                family=AuthorityFamily.DAILY_CAPACITY,
                stable_key="daily-capacity:1:2:POOL-A:v1:1:2026-02-01",
                business_version="v1",
                revision=1,
            ),
            await load_authority_by_persistent_identity(
                session,
                family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
                stable_key="holiday-calendar:1:CN-SH:Asia/Shanghai",
                business_version="calendar-v1",
                revision=1,
            ),
            await load_authority_by_persistent_identity(
                session,
                family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
                stable_key="weather-rule:wx-rule:Asia/Shanghai",
                business_version="wx-v1",
                revision=1,
            ),
            await load_authority_by_persistent_identity(
                session,
                family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                stable_key="run-package:1:2:farm-scope:10",
                business_version="pkg-v1",
                revision=1,
            ),
            await load_authority_by_persistent_identity(
                session,
                family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
                stable_key="initial-inventory:1:2:2026-02-01",
                business_version="snap-v1",
                revision=1,
            ),
            await load_authority_by_persistent_identity(
                session,
                family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
                stable_key="mature-loss:1:2:POOL-A:2026-02-01:P50",
                business_version="loss-v1",
                revision=1,
            ),
        ]
        assert {row.id for row in by_identity_rows} == set(ids.values())
        by_hash_rows = [
            await load_authority_by_row_hash(
                session, family=AuthorityFamily.CAPACITY_POOL_DEFINITION, row_hash=pool.row_hash
            ),
            await load_authority_by_row_hash(
                session, family=AuthorityFamily.DAILY_CAPACITY, row_hash=daily.row_hash
            ),
            await load_authority_by_row_hash(
                session,
                family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
                row_hash=holiday.row_hash,
            ),
            await load_authority_by_row_hash(
                session,
                family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
                row_hash=weather.row_hash,
            ),
            await load_authority_by_row_hash(
                session, family=AuthorityFamily.RUN_PARAMETER_PACKAGE, row_hash=package.row_hash
            ),
            await load_authority_by_row_hash(
                session,
                family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
                row_hash=inventory.row_hash,
            ),
            await load_authority_by_row_hash(
                session,
                family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
                row_hash=mature_loss.row_hash,
            ),
        ]
        assert {row.id for row in by_hash_rows} == set(ids.values())
        generic_by_id = await load_authority_by_id(
            session,
            family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            authority_id=ids["package_id"],
        )
        assert generic_by_id.id == ids["package_id"]


@pytest.mark.asyncio
async def test_member_projection_cascades_and_trio_replacement_workflow() -> None:
    _require_postgres()
    dims = await _seed_dimensions()
    async with AsyncSessionMaker() as session:
        pool_result = await create_or_load_capacity_pool_definition(
            session, bundle=_pool_bundle(dims)
        )
        holiday_result = await create_or_load_holiday_calendar_version(
            session, bundle=_holiday_bundle(dims)
        )
        await create_or_load_weather_rule_config_version(session, authority=_weather_input())
        package_result = await create_or_load_run_parameter_package(
            session, bundle=_package_bundle(dims)
        )
        await session.commit()
        await session.refresh(pool_result.authority)
        member_before = await session.scalar(
            select(Task9CapacityPoolMember).where(
                Task9CapacityPoolMember.capacity_pool_definition_id == pool_result.authority.id
            )
        )
        assert member_before is not None
        retired_pool = await retire_authority(
            session,
            family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
            authority_id=pool_result.authority.id,
            retirement_boundary=date(2026, 1, 10),
        )
        await session.commit()
        member_after = await session.scalar(
            select(Task9CapacityPoolMember).where(
                Task9CapacityPoolMember.capacity_pool_definition_id == pool_result.authority.id
            )
        )
        assert member_after is not None
        assert retired_pool.status == "retired"
        assert member_after.status == "retired"
        assert member_after.consumable_to_key == date(2026, 1, 10)
        with pytest.raises(AuthorityDependencyConflictError) as excinfo:
            await replace_authority(
                session,
                family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
                old_authority_id=holiday_result.authority.id,
                new_authority_id=holiday_result.authority.id,
                replacement_boundary=date(2026, 1, 15),
            )
        assert excinfo.value.code == "AUTHORITY_DEPENDENCY_CONFLICT"
        new_holiday = _holiday_bundle(dims).model_copy(update={"revision": 2, "status": "draft"})
        new_weather = _weather_input().model_copy(update={"revision": 2, "status": "draft"})
        new_package = cast(
            Task9RunParameterPackageSemanticInput,
            _package_bundle(dims).package.model_copy(update={"revision": 2, "status": "draft"}),
        )
        replacement = await replace_run_package_with_dependencies(
            session,
            old_package_id=package_result.authority.id,
            new_holiday=new_holiday,
            new_weather=new_weather,
            new_package=new_package,
            replacement_boundary=date(2026, 1, 15),
        )
        await session.commit()
        new_package_row = await session.get(Task9RunParameterPackage, replacement.new_package_id)
        old_package_row = await session.get(Task9RunParameterPackage, replacement.old_package_id)
        new_holiday_row = await session.get(Task9HolidayCalendarVersion, replacement.new_holiday_id)
        new_weather_row = await session.get(
            Task9WeatherRuleConfigVersion, replacement.new_weather_id
        )
        assert old_package_row is not None and old_package_row.status == "superseded"
        assert new_package_row is not None and new_package_row.status == "active"
        assert new_holiday_row is not None and new_holiday_row.status == "active"
        assert new_weather_row is not None and new_weather_row.status == "active"
        assert old_package_row.consumable_to_local_date == date(2026, 1, 15)
        assert new_package_row.consumable_from_local_date == date(2026, 1, 15)
        assert new_holiday_row.consumable_from_local_date == date(2026, 1, 15)
        assert new_weather_row.consumable_from_local_date == date(2026, 1, 15)
        assert new_package_row.holiday_calendar_version_id == replacement.new_holiday_id
        assert new_package_row.weather_rule_config_version_id == replacement.new_weather_id


@pytest.mark.asyncio
async def test_run_package_create_rejects_submitted_dependency_payload_mismatch() -> None:
    _require_postgres()
    dims = await _seed_dimensions()
    async with AsyncSessionMaker() as session:
        await create_or_load_holiday_calendar_version(session, bundle=_holiday_bundle(dims))
        await create_or_load_weather_rule_config_version(session, authority=_weather_input())
        await session.commit()

    submitted_holiday_payload = _holiday_bundle(dims).model_dump(mode="json")
    submitted_holiday_payload["dates"][-1]["holiday_name"] = "Tampered Holiday Name"
    mismatched_holiday = Task9HolidayCalendarSemanticBundle.model_validate(
        submitted_holiday_payload
    )
    mismatched_holiday = Task9HolidayCalendarSemanticBundle.model_validate(
        {
            **mismatched_holiday.model_dump(mode="json"),
            "row_hash": make_authority_row_hash(mismatched_holiday),
        }
    )

    async with AsyncSessionMaker() as session:
        with pytest.raises(AuthorityDependencyConflictError) as excinfo:
            await create_or_load_run_parameter_package(
                session,
                bundle=Task9RunParameterPackageBundleSchema(
                    package=_package_bundle(dims).package,
                    holiday_calendar=mismatched_holiday,
                    weather_rule=_weather_input(),
                ),
            )
        assert excinfo.value.code == "AUTHORITY_DEPENDENCY_CONFLICT"
        assert await _count_rows(session, Task9RunParameterPackage) == 0


@pytest.mark.asyncio
async def test_dependency_aware_trio_replacement_rolls_back_orphan_drafts() -> None:
    _require_postgres()
    dims = await _seed_dimensions()
    async with AsyncSessionMaker() as session:
        await create_or_load_holiday_calendar_version(session, bundle=_holiday_bundle(dims))
        await create_or_load_weather_rule_config_version(session, authority=_weather_input())
        package_result = await create_or_load_run_parameter_package(
            session, bundle=_package_bundle(dims)
        )
        await session.commit()

    async with AsyncSessionMaker() as session:
        new_holiday = Task9HolidayCalendarSemanticBundle.model_validate(
            {**_holiday_bundle(dims).model_dump(mode="json"), "revision": 2, "status": "draft"}
        )
        new_weather = Task9WeatherRuleSemanticInput.model_validate(
            {**_weather_input().model_dump(mode="json"), "revision": 2, "status": "draft"}
        )
        bad_package = Task9RunParameterPackageSemanticInput.model_validate(
            {
                **_package_bundle(dims).package.model_dump(mode="json"),
                "revision": 2,
                "status": "draft",
                "destination_factory_timezone": "UTC",
            }
        )
        with pytest.raises(AuthorityDependencyConflictError) as excinfo:
            await replace_run_package_with_dependencies(
                session,
                old_package_id=package_result.authority.id,
                new_holiday=new_holiday,
                new_weather=new_weather,
                new_package=bad_package,
                replacement_boundary=date(2026, 1, 15),
            )
        assert excinfo.value.code == "AUTHORITY_DEPENDENCY_CONFLICT"
        await session.rollback()

    async with AsyncSessionMaker() as session:
        assert await _count_rows(session, Task9HolidayCalendarVersion) == 1
        assert await _count_rows(session, Task9WeatherRuleConfigVersion) == 1
        assert await _count_rows(session, Task9RunParameterPackage) == 1


@pytest.mark.asyncio
async def test_concurrent_same_payload_returns_single_authority_row() -> None:
    _require_postgres()
    dims = await _seed_dimensions()
    bundle = _pool_bundle(dims)
    start = asyncio.Event()

    async def _worker() -> tuple[bool, int]:
        async with AsyncSessionMaker() as session:
            await start.wait()
            result = await create_or_load_capacity_pool_definition(session, bundle=bundle)
            await session.commit()
            return result.created, result.authority.id

    task_a = asyncio.create_task(_worker())
    task_b = asyncio.create_task(_worker())
    start.set()
    results = await asyncio.gather(task_a, task_b)
    assert {created for created, _authority_id in results} == {True, False}
    assert len({authority_id for _created, authority_id in results}) == 1

    async with AsyncSessionMaker() as session:
        assert await _count_rows(session, Task9CapacityPoolDefinition) == 1
        assert await _count_rows(session, Task9AuthorityLifecycleEvent) == 2


@pytest.mark.asyncio
async def test_concurrent_conflicting_payload_returns_version_conflict() -> None:
    _require_postgres()
    dims = await _seed_dimensions()
    same_bundle = _pool_bundle(dims)
    conflict_payload = _capacity_pool_definition_payload()
    conflict_payload["season_id"] = dims["season_id"]
    conflict_payload["destination_factory_id"] = dims["factory_id"]
    conflict_payload["members"] = [
        {"farm_id": dims["farm_id"], "subfarm_id": None, "variety_id": dims["variety_id"]},
        {
            "farm_id": dims["farm_id"],
            "subfarm_id": dims["subfarm_id"],
            "variety_id": dims["variety_id"],
        },
    ]
    conflict_bundle = Task9CapacityPoolDefinitionSemanticBundle.model_validate(conflict_payload)
    start = asyncio.Event()

    async def _worker(
        bundle: Task9CapacityPoolDefinitionSemanticBundle,
    ) -> tuple[str, bool | str, int | None]:
        async with AsyncSessionMaker() as session:
            await start.wait()
            try:
                result = await create_or_load_capacity_pool_definition(session, bundle=bundle)
            except AuthorityVersionConflictError as exc:
                await session.rollback()
                return ("conflict", exc.code, None)
            await session.commit()
            return ("ok", result.created, result.authority.id)

    task_a = asyncio.create_task(_worker(same_bundle))
    task_b = asyncio.create_task(_worker(conflict_bundle))
    start.set()
    results = await asyncio.gather(task_a, task_b)
    assert sorted(result[0] for result in results) == ["conflict", "ok"]
    ok_result = next(result for result in results if result[0] == "ok")
    conflict_result = next(result for result in results if result[0] == "conflict")
    assert ok_result[1] is True
    assert conflict_result[1] == "AUTHORITY_VERSION_CONFLICT"

    async with AsyncSessionMaker() as session:
        assert await _count_rows(session, Task9CapacityPoolDefinition) == 1
        assert await _count_rows(session, Task9AuthorityLifecycleEvent) == 2
