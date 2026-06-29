# ruff: noqa: E501
"""PostgreSQL migration and constraint coverage for task9 historical authority."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app.db.session import AsyncSessionMaker
from backend.app.models import (
    Factory,
    Farm,
    Season,
    Subfarm,
    Task9AuthorityLifecycleEvent,
    Task9CapacityPoolDefinition,
    Task9CapacityPoolMember,
    Task9DailyCapacityAuthority,
    Task9HolidayCalendarDate,
    Task9HolidayCalendarVersion,
    Task9InitialInventoryCohort,
    Task9InitialInventorySnapshot,
    Task9MatureInventoryLossAuthority,
    Task9RunParameterPackage,
    Task9WeatherRuleConfigVersion,
    Variety,
)

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("RUN_POSTGRES_INTEGRATION=1 required")
    if os.getenv("APP_ENV") != "test":
        pytest.skip("APP_ENV=test required")


async def _scalar(sql: str, params: dict[str, Any] | None = None) -> Any:
    async with AsyncSessionMaker() as session:
        result = await session.execute(text(sql), params or {})
        return result.scalar_one()


async def _expect_integrity_error(sql: str, params: dict[str, Any] | None = None) -> IntegrityError:
    async with AsyncSessionMaker() as session:
        with pytest.raises(IntegrityError) as excinfo:
            await session.execute(text(sql), params or {})
            await session.flush()
        await session.rollback()
        await session.execute(text("SELECT 1"))
        return excinfo.value


def _normalize_contype(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return value.decode("ascii")
    return value


def _constraint_name(exc: IntegrityError) -> str | None:
    for candidate in (
        getattr(exc, "orig", None),
        getattr(getattr(exc, "orig", None), "orig", None),
        getattr(getattr(exc, "orig", None), "__cause__", None),
    ):
        if candidate is None:
            continue
        name = getattr(candidate, "constraint_name", None)
        if name:
            return name
    return None


async def _seed_dimensions() -> dict[str, int]:
    async with AsyncSessionMaker() as session:
        season = Season(code="S2025", start_date=date(2025, 1, 1), end_date=date(2025, 5, 31))
        factory = Factory(code="F001", name="Factory 001")
        farm = Farm(name="Farm 001")
        variety = Variety(code="V001", name="Variety 001")
        session.add_all([season, factory, farm, variety])
        await session.flush()
        subfarm = Subfarm(farm_id=farm.id, name="Subfarm 001")
        session.add(subfarm)
        await session.flush()
        await session.commit()
        return {
            "season_id": season.id,
            "factory_id": factory.id,
            "farm_id": farm.id,
            "subfarm_id": subfarm.id,
            "variety_id": variety.id,
        }


def _sha(char: str) -> str:
    return char * 64


def _ts() -> datetime:
    return datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


def _date(d: int) -> date:
    return date(2025, 1, d)


async def _insert_capacity_pool_definition(
    *,
    season_id: int,
    factory_id: int,
    code: str = "POOL-A",
    version: str = "v1",
    revision: int = 1,
    status: str = "active",
    effective_from: date | None = None,
    effective_to: date | None = None,
    available_at: date | None = None,
    consumable_from: date | None = None,
    consumable_to: date | None = None,
    superseded_by_id: int | None = None,
    row_hash: str | None = None,
) -> int:
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            text(
                """
                INSERT INTO task9_capacity_pool_definition (
                    season_id,
                    destination_factory_id,
                    capacity_pool_code,
                    capacity_pool_version,
                    revision,
                    capacity_pool_grain,
                    capacity_input_mode,
                    effective_from,
                    effective_to,
                    available_at_local_date,
                    consumable_from_local_date,
                    consumable_to_local_date,
                    status,
                    status_changed_at,
                    source_system,
                    source_record_key,
                    source_version,
                    row_hash,
                    superseded_by_id
                )
                VALUES (
                    :season_id,
                    :factory_id,
                    :code,
                    :version,
                    :revision,
                    'FARM',
                    'LABOR_DERIVED',
                    :effective_from,
                    :effective_to,
                    :available_at,
                    :consumable_from,
                    :consumable_to,
                    :status,
                    :status_changed_at,
                    'task9_historical_authority',
                    :source_record_key,
                    'src-v1',
                    :row_hash,
                    :superseded_by_id
                )
                RETURNING id
                """
            ),
            {
                "season_id": season_id,
                "factory_id": factory_id,
                "code": code,
                "version": version,
                "revision": revision,
                "effective_from": effective_from or _date(1),
                "effective_to": effective_to,
                "available_at": available_at or _date(1),
                "consumable_from": consumable_from,
                "consumable_to": consumable_to,
                "status": status,
                "status_changed_at": _ts(),
                "source_record_key": (
                    f"capacity-pool:{season_id}:{factory_id}:{code}:{version}:{revision}"
                ),
                "row_hash": row_hash or _sha("a"),
                "superseded_by_id": superseded_by_id,
            },
        )
        inserted_id = int(result.scalar_one())
        await session.commit()
        return inserted_id


async def _insert_pool_member(
    *,
    pool_id: int,
    season_id: int,
    factory_id: int,
    farm_id: int,
    subfarm_id: int | None,
    variety_id: int,
    effective_from: date | None = None,
    effective_to: date | None = None,
    status: str = "active",
    consumable_from_key: date | None = None,
    consumable_to_key: date | None = None,
    row_hash: str | None = None,
) -> int:
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            text(
                """
                INSERT INTO task9_capacity_pool_member (
                    capacity_pool_definition_id,
                    season_id,
                    destination_factory_id,
                    farm_id,
                    subfarm_id,
                    variety_id,
                    effective_from,
                    effective_to,
                    status,
                    consumable_from_key,
                    consumable_to_key,
                    row_hash
                )
                VALUES (
                    :pool_id,
                    :season_id,
                    :factory_id,
                    :farm_id,
                    :subfarm_id,
                    :variety_id,
                    :effective_from,
                    :effective_to,
                    :status,
                    :consumable_from_key,
                    :consumable_to_key,
                    :row_hash
                )
                RETURNING id
                """
            ),
            {
                "pool_id": pool_id,
                "season_id": season_id,
                "factory_id": factory_id,
                "farm_id": farm_id,
                "subfarm_id": subfarm_id,
                "variety_id": variety_id,
                "effective_from": effective_from or _date(1),
                "effective_to": effective_to,
                "status": status,
                "consumable_from_key": consumable_from_key or _date(2),
                "consumable_to_key": consumable_to_key or _date(20),
                "row_hash": row_hash or _sha("b"),
            },
        )
        inserted_id = int(result.scalar_one())
        await session.commit()
        return inserted_id


async def _insert_daily_capacity(
    *,
    pool_id: int,
    capacity_date: date | None = None,
    revision: int = 1,
    status: str = "active",
    available_at: date | None = None,
    consumable_from: date | None = None,
    consumable_to: date | None = None,
    superseded_by_id: int | None = None,
    row_hash: str | None = None,
) -> int:
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            text(
                """
                INSERT INTO task9_daily_capacity_authority (
                    capacity_pool_definition_id,
                    capacity_date,
                    daily_capacity_revision,
                    planned_picker_count,
                    kg_per_person_per_day,
                    direct_nominal_capacity_kg_per_day,
                    labor_availability_ratio,
                    operational_efficiency_ratio,
                    available_at_local_date,
                    consumable_from_local_date,
                    consumable_to_local_date,
                    status,
                    status_changed_at,
                    superseded_by_id,
                    source_system,
                    source_record_key,
                    source_version,
                    row_hash
                )
                VALUES (
                    :pool_id,
                    :capacity_date,
                    :revision,
                    10.000,
                    100.000,
                    NULL,
                    0.800000,
                    0.900000,
                    :available_at,
                    :consumable_from,
                    :consumable_to,
                    :status,
                    :status_changed_at,
                    :superseded_by_id,
                    'task9_historical_authority',
                    :source_record_key,
                    'src-v1',
                    :row_hash
                )
                RETURNING id
                """
            ),
            {
                "pool_id": pool_id,
                "capacity_date": capacity_date or _date(3),
                "revision": revision,
                "available_at": available_at or _date(1),
                "consumable_from": consumable_from,
                "consumable_to": consumable_to,
                "status": status,
                "status_changed_at": _ts(),
                "superseded_by_id": superseded_by_id,
                "source_record_key": f"daily-capacity:{pool_id}:{capacity_date or _date(3)}:{revision}",
                "row_hash": row_hash or _sha("c"),
            },
        )
        inserted_id = int(result.scalar_one())
        await session.commit()
        return inserted_id


async def _insert_holiday_header(
    *, season_id: int, status: str = "active", revision: int = 1
) -> int:
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            text(
                """
                INSERT INTO task9_holiday_calendar_version (
                    season_id,
                    calendar_code,
                    lifecycle_timezone_name,
                    calendar_version,
                    revision,
                    region_scope,
                    calendar_hash,
                    available_at_local_date,
                    consumable_from_local_date,
                    consumable_to_local_date,
                    status,
                    status_changed_at,
                    superseded_by_id,
                    source_system,
                    source_record_key,
                    source_version,
                    row_hash
                )
                VALUES (
                    :season_id,
                    'CAL-1',
                    'Asia/Shanghai',
                    'v1',
                    :revision,
                    'region-a',
                    :calendar_hash,
                    :available_at,
                    :consumable_from,
                    :consumable_to,
                    :status,
                    :status_changed_at,
                    NULL,
                    'task9_historical_authority',
                    :source_record_key,
                    'src-v1',
                    :row_hash
                )
                RETURNING id
                """
            ),
            {
                "season_id": season_id,
                "revision": revision,
                "calendar_hash": _sha("d"),
                "available_at": _date(1),
                "consumable_from": _date(2) if status == "active" else None,
                "consumable_to": None,
                "status": status,
                "status_changed_at": _ts(),
                "source_record_key": f"holiday-calendar:{season_id}:CAL-1:Asia/Shanghai:v1:{revision}",
                "row_hash": _sha("e"),
            },
        )
        inserted_id = int(result.scalar_one())
        await session.commit()
        return inserted_id


async def _insert_holiday_date(
    holiday_header_id: int, *, holiday_date: date, code: str = "CNY"
) -> int:
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            text(
                """
                INSERT INTO task9_holiday_calendar_date (
                    holiday_calendar_version_id,
                    holiday_date,
                    holiday_code,
                    holiday_name
                )
                VALUES (:holiday_header_id, :holiday_date, :code, 'Holiday Name')
                RETURNING id
                """
            ),
            {
                "holiday_header_id": holiday_header_id,
                "holiday_date": holiday_date,
                "code": code,
            },
        )
        inserted_id = int(result.scalar_one())
        await session.commit()
        return inserted_id


async def _insert_weather_rule(*, status: str = "active", revision: int = 1) -> int:
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            text(
                """
                INSERT INTO task9_weather_rule_config_version (
                    rule_code,
                    lifecycle_timezone_name,
                    rule_version,
                    revision,
                    combination_method,
                    minimum_ratio,
                    maximum_ratio,
                    required_feature_ids,
                    feature_rules_json,
                    missing_feature_policy,
                    config_hash,
                    available_at_local_date,
                    consumable_from_local_date,
                    consumable_to_local_date,
                    effective_from,
                    effective_to,
                    status,
                    status_changed_at,
                    superseded_by_id,
                    source_system,
                    source_record_key,
                    source_version,
                    row_hash
                )
                VALUES (
                    'WR-1',
                    'Asia/Shanghai',
                    'v1',
                    :revision,
                    'MULTIPLY',
                    0.500000,
                    1.000000,
                    CAST(:required_feature_ids AS jsonb),
                    CAST(:feature_rules_json AS jsonb),
                    'BLOCK',
                    :config_hash,
                    :available_at,
                    :consumable_from,
                    :consumable_to,
                    :effective_from,
                    :effective_to,
                    :status,
                    :status_changed_at,
                    NULL,
                    'task9_historical_authority',
                    :source_record_key,
                    'src-v1',
                    :row_hash
                )
                RETURNING id
                """
            ),
            {
                "revision": revision,
                "required_feature_ids": json.dumps(["tmean"]),
                "feature_rules_json": json.dumps(
                    [{"feature_id": "tmean", "bands": [{"min": 0, "max": 10, "ratio": "0.8"}]}]
                ),
                "config_hash": _sha("f"),
                "available_at": _date(1),
                "consumable_from": _date(2) if status == "active" else None,
                "consumable_to": None,
                "effective_from": _date(1),
                "effective_to": None,
                "status": status,
                "status_changed_at": _ts(),
                "source_record_key": f"weather-rule:WR-1:Asia/Shanghai:v1:{revision}",
                "row_hash": _sha("1"),
            },
        )
        inserted_id = int(result.scalar_one())
        await session.commit()
        return inserted_id


async def _insert_run_package(
    *,
    season_id: int,
    factory_id: int,
    holiday_id: int,
    weather_id: int,
    status: str = "active",
    revision: int = 1,
) -> int:
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            text(
                """
                INSERT INTO task9_run_parameter_package (
                    season_id,
                    destination_factory_id,
                    farm_scope_key,
                    package_version,
                    revision,
                    farm_timezone,
                    destination_factory_timezone,
                    harvest_bucket_anchor_local_time,
                    harvest_to_arrival_lag_days,
                    holiday_calendar_version_id,
                    weather_rule_config_version_id,
                    available_at_local_date,
                    consumable_from_local_date,
                    consumable_to_local_date,
                    effective_from,
                    effective_to,
                    status,
                    status_changed_at,
                    superseded_by_id,
                    source_system,
                    source_record_key,
                    source_version,
                    row_hash
                )
                VALUES (
                    :season_id,
                    :factory_id,
                    'farm-scope:a',
                    'v1',
                    :revision,
                    'Asia/Shanghai',
                    'Asia/Shanghai',
                    '09:00',
                    1,
                    :holiday_id,
                    :weather_id,
                    :available_at,
                    :consumable_from,
                    :consumable_to,
                    :effective_from,
                    :effective_to,
                    :status,
                    :status_changed_at,
                    NULL,
                    'task9_historical_authority',
                    :source_record_key,
                    'src-v1',
                    :row_hash
                )
                RETURNING id
                """
            ),
            {
                "season_id": season_id,
                "factory_id": factory_id,
                "revision": revision,
                "holiday_id": holiday_id,
                "weather_id": weather_id,
                "available_at": _date(1),
                "consumable_from": _date(2) if status == "active" else None,
                "consumable_to": None,
                "effective_from": _date(1),
                "effective_to": None,
                "status": status,
                "status_changed_at": _ts(),
                "source_record_key": f"run-package:{season_id}:{factory_id}:farm-scope:a:v1:{revision}",
                "row_hash": _sha("2"),
            },
        )
        inserted_id = int(result.scalar_one())
        await session.commit()
        return inserted_id


async def _insert_inventory_snapshot(
    *, season_id: int, factory_id: int, status: str = "active"
) -> int:
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            text(
                """
                INSERT INTO task9_initial_inventory_snapshot (
                    season_id,
                    destination_factory_id,
                    opening_state_date,
                    snapshot_version,
                    revision,
                    initial_opening_mature_inventory_kg,
                    available_at_local_date,
                    consumable_from_local_date,
                    consumable_to_local_date,
                    status,
                    status_changed_at,
                    superseded_by_id,
                    source_system,
                    source_record_key,
                    source_version,
                    row_hash
                )
                VALUES (
                    :season_id,
                    :factory_id,
                    :opening_state_date,
                    'v1',
                    1,
                    30.000000,
                    :available_at,
                    :consumable_from,
                    :consumable_to,
                    :status,
                    :status_changed_at,
                    NULL,
                    'task9_historical_authority',
                    :source_record_key,
                    'src-v1',
                    :row_hash
                )
                RETURNING id
                """
            ),
            {
                "season_id": season_id,
                "factory_id": factory_id,
                "opening_state_date": _date(3),
                "available_at": _date(1),
                "consumable_from": _date(2) if status == "active" else None,
                "consumable_to": None,
                "status": status,
                "status_changed_at": _ts(),
                "source_record_key": f"initial-inventory:{season_id}:{factory_id}:{_date(3)}",
                "row_hash": _sha("3"),
            },
        )
        inserted_id = int(result.scalar_one())
        await session.commit()
        return inserted_id


async def _insert_inventory_cohort(
    *,
    snapshot_id: int,
    farm_id: int,
    subfarm_id: int | None,
    variety_id: int,
    stable_cohort_key: str = "cohort-1",
) -> int:
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            text(
                """
                INSERT INTO task9_initial_inventory_cohort (
                    initial_inventory_snapshot_id,
                    stable_cohort_key,
                    forecast_quantile,
                    cohort_date,
                    farm_id,
                    subfarm_id,
                    variety_id,
                    remaining_quantity_kg,
                    row_hash
                )
                VALUES (
                    :snapshot_id,
                    :stable_cohort_key,
                    'P50',
                    :cohort_date,
                    :farm_id,
                    :subfarm_id,
                    :variety_id,
                    30.000000,
                    :row_hash
                )
                RETURNING id
                """
            ),
            {
                "snapshot_id": snapshot_id,
                "stable_cohort_key": stable_cohort_key,
                "cohort_date": _date(3),
                "farm_id": farm_id,
                "subfarm_id": subfarm_id,
                "variety_id": variety_id,
                "row_hash": _sha("4"),
            },
        )
        inserted_id = int(result.scalar_one())
        await session.commit()
        return inserted_id


async def _insert_mature_loss(*, season_id: int, factory_id: int, status: str = "active") -> int:
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            text(
                """
                INSERT INTO task9_mature_inventory_loss_authority (
                    season_id,
                    destination_factory_id,
                    state_date,
                    capacity_pool_code,
                    forecast_quantile,
                    loss_version,
                    revision,
                    mature_inventory_loss_quantity_kg,
                    available_at_local_date,
                    consumable_from_local_date,
                    consumable_to_local_date,
                    status,
                    status_changed_at,
                    superseded_by_id,
                    source_system,
                    source_record_key,
                    source_version,
                    row_hash
                )
                VALUES (
                    :season_id,
                    :factory_id,
                    :state_date,
                    'POOL-A',
                    'P50',
                    'v1',
                    1,
                    2.500000,
                    :available_at,
                    :consumable_from,
                    :consumable_to,
                    :status,
                    :status_changed_at,
                    NULL,
                    'task9_historical_authority',
                    :source_record_key,
                    'src-v1',
                    :row_hash
                )
                RETURNING id
                """
            ),
            {
                "season_id": season_id,
                "factory_id": factory_id,
                "state_date": _date(4),
                "available_at": _date(1),
                "consumable_from": _date(2) if status == "active" else None,
                "consumable_to": None,
                "status": status,
                "status_changed_at": _ts(),
                "source_record_key": f"mature-loss:{season_id}:{factory_id}:POOL-A:{_date(4)}:P50",
                "row_hash": _sha("5"),
            },
        )
        inserted_id = int(result.scalar_one())
        await session.commit()
        return inserted_id


async def _insert_lifecycle_event() -> int:
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            text(
                """
                INSERT INTO task9_authority_lifecycle_event (
                    authority_family,
                    authority_stable_key,
                    authority_business_version,
                    authority_revision,
                    business_row_hash,
                    transition_sequence,
                    old_status,
                    new_status,
                    old_consumable_from_local_date,
                    old_consumable_to_local_date,
                    new_consumable_from_local_date,
                    new_consumable_to_local_date,
                    superseded_by_authority_stable_key,
                    superseded_by_authority_business_version,
                    superseded_by_authority_revision,
                    transitioned_at,
                    source_system,
                    source_record_key,
                    lifecycle_event_hash
                )
                VALUES (
                    'capacity_pool_definition',
                    'capacity-pool:1:1:POOL-A',
                    'v1',
                    1,
                    :business_row_hash,
                    1,
                    NULL,
                    'draft',
                    NULL,
                    NULL,
                    NULL,
                    NULL,
                    NULL,
                    NULL,
                    NULL,
                    :transitioned_at,
                    'task9_historical_authority',
                    'lifecycle-event:capacity-pool:1',
                    :lifecycle_event_hash
                )
                RETURNING id
                """
            ),
            {
                "business_row_hash": _sha("6"),
                "transitioned_at": _ts(),
                "lifecycle_event_hash": _sha("7"),
            },
        )
        inserted_id = int(result.scalar_one())
        await session.commit()
        return inserted_id


async def _insert_valid_bundle() -> dict[str, int]:
    ids = await _seed_dimensions()
    holiday_id = await _insert_holiday_header(season_id=ids["season_id"])
    await _insert_holiday_date(holiday_id, holiday_date=_date(10))
    weather_id = await _insert_weather_rule()
    run_package_id = await _insert_run_package(
        season_id=ids["season_id"],
        factory_id=ids["factory_id"],
        holiday_id=holiday_id,
        weather_id=weather_id,
    )
    pool_id = await _insert_capacity_pool_definition(
        season_id=ids["season_id"],
        factory_id=ids["factory_id"],
        status="retired",
        consumable_from=_date(2),
        consumable_to=_date(20),
    )
    await _insert_pool_member(
        pool_id=pool_id,
        season_id=ids["season_id"],
        factory_id=ids["factory_id"],
        farm_id=ids["farm_id"],
        subfarm_id=ids["subfarm_id"],
        variety_id=ids["variety_id"],
        status="retired",
        consumable_from_key=_date(2),
        consumable_to_key=_date(20),
    )
    daily_id = await _insert_daily_capacity(
        pool_id=pool_id,
        status="active",
        consumable_from=_date(2),
    )
    snapshot_id = await _insert_inventory_snapshot(
        season_id=ids["season_id"],
        factory_id=ids["factory_id"],
    )
    await _insert_inventory_cohort(
        snapshot_id=snapshot_id,
        farm_id=ids["farm_id"],
        subfarm_id=ids["subfarm_id"],
        variety_id=ids["variety_id"],
    )
    loss_id = await _insert_mature_loss(
        season_id=ids["season_id"],
        factory_id=ids["factory_id"],
    )
    event_id = await _insert_lifecycle_event()
    return {
        **ids,
        "holiday_id": holiday_id,
        "weather_id": weather_id,
        "run_package_id": run_package_id,
        "pool_id": pool_id,
        "daily_id": daily_id,
        "snapshot_id": snapshot_id,
        "loss_id": loss_id,
        "event_id": event_id,
    }


@pytest.mark.asyncio
async def test_task9_authority_tables_exist_with_expected_columns() -> None:
    _require_postgres()
    expected_tables = {
        Task9CapacityPoolDefinition.__tablename__,
        Task9CapacityPoolMember.__tablename__,
        Task9DailyCapacityAuthority.__tablename__,
        Task9RunParameterPackage.__tablename__,
        Task9HolidayCalendarVersion.__tablename__,
        Task9HolidayCalendarDate.__tablename__,
        Task9WeatherRuleConfigVersion.__tablename__,
        Task9InitialInventorySnapshot.__tablename__,
        Task9InitialInventoryCohort.__tablename__,
        Task9MatureInventoryLossAuthority.__tablename__,
        Task9AuthorityLifecycleEvent.__tablename__,
    }
    actual_tables = set(
        await _scalar(
            """
            SELECT array_agg(table_name ORDER BY table_name)
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = ANY(:tables)
            """,
            {"tables": list(expected_tables)},
        )
    )
    assert actual_tables == expected_tables


@pytest.mark.asyncio
async def test_task9_authority_extension_generated_columns_and_indexes_exist() -> None:
    _require_postgres()
    extension = await _scalar("SELECT extname FROM pg_extension WHERE extname = 'btree_gist'")
    assert extension == "btree_gist"

    async with AsyncSessionMaker() as session:
        generated = await session.execute(
            text(
                """
                SELECT table_name, column_name, generation_expression
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND is_generated = 'ALWAYS'
                  AND table_name IN (
                    'task9_capacity_pool_definition',
                    'task9_capacity_pool_member',
                    'task9_daily_capacity_authority',
                    'task9_run_parameter_package',
                    'task9_holiday_calendar_version',
                    'task9_weather_rule_config_version',
                    'task9_initial_inventory_snapshot',
                    'task9_mature_inventory_loss_authority'
                  )
                ORDER BY table_name, column_name
                """
            )
        )
        generated_rows = {
            (row.table_name, row.column_name): row.generation_expression for row in generated
        }
    assert ("task9_capacity_pool_definition", "effective_range") in generated_rows
    assert ("task9_capacity_pool_member", "normalized_subfarm_id") in generated_rows
    assert ("task9_daily_capacity_authority", "consumability_range") in generated_rows
    assert ("task9_run_parameter_package", "effective_range") in generated_rows
    assert ("task9_weather_rule_config_version", "consumability_range") in generated_rows
    assert ("task9_initial_inventory_snapshot", "consumability_range") in generated_rows

    index_defs = await _scalar(
        """
        SELECT array_agg(indexdef ORDER BY indexname)
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'task9_capacity_pool_member'
        """
    )
    assert any("NULLS NOT DISTINCT" in definition for definition in index_defs)


@pytest.mark.asyncio
async def test_task9_authority_constraint_catalog_contains_expected_postgres_objects() -> None:
    _require_postgres()
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            text(
                """
                SELECT conname, contype, pg_get_constraintdef(oid) AS constraint_def
                FROM pg_constraint
                WHERE conname IN (
                    'ex_task9_capacity_pool_definition_combined_overlap',
                    'ex_task9_capacity_pool_member_combined_overlap',
                    'ex_task9_run_parameter_package_combined_overlap',
                    'ex_task9_daily_capacity_consumability_overlap',
                    'ex_task9_holiday_calendar_consumability_overlap',
                    'ex_task9_weather_rule_combined_overlap',
                    'ex_task9_initial_inventory_consumability_overlap',
                    'ex_task9_mature_loss_consumability_overlap',
                    'uq_task9_authority_lifecycle_event_identity_sequence',
                    'uq_task9_authority_lifecycle_event_identity_hash'
                )
                ORDER BY conname
                """
            )
        )
        rows = {
            row["conname"]: (
                _normalize_contype(row["contype"]),
                row["constraint_def"],
            )
            for row in result.mappings()
        }
    assert rows["ex_task9_capacity_pool_definition_combined_overlap"][0] == "x"
    assert "season_id WITH =" in rows["ex_task9_capacity_pool_definition_combined_overlap"][1]
    assert (
        "destination_factory_id WITH ="
        in rows["ex_task9_capacity_pool_definition_combined_overlap"][1]
    )
    assert (
        "capacity_pool_code WITH =" in rows["ex_task9_capacity_pool_definition_combined_overlap"][1]
    )
    assert (
        "effective_range WITH &&" in rows["ex_task9_capacity_pool_definition_combined_overlap"][1]
    )
    assert (
        "consumability_range WITH &&"
        in rows["ex_task9_capacity_pool_definition_combined_overlap"][1]
    )
    assert rows["ex_task9_capacity_pool_member_combined_overlap"][0] == "x"
    assert "farm_id WITH =" in rows["ex_task9_capacity_pool_member_combined_overlap"][1]
    assert (
        "normalized_subfarm_id WITH =" in rows["ex_task9_capacity_pool_member_combined_overlap"][1]
    )
    assert "variety_id WITH =" in rows["ex_task9_capacity_pool_member_combined_overlap"][1]
    assert "effective_range WITH &&" in rows["ex_task9_capacity_pool_member_combined_overlap"][1]
    assert (
        "consumability_range WITH &&" in rows["ex_task9_capacity_pool_member_combined_overlap"][1]
    )
    assert rows["ex_task9_run_parameter_package_combined_overlap"][0] == "x"
    assert "season_id WITH =" in rows["ex_task9_run_parameter_package_combined_overlap"][1]
    assert (
        "destination_factory_id WITH ="
        in rows["ex_task9_run_parameter_package_combined_overlap"][1]
    )
    assert "farm_scope_key WITH =" in rows["ex_task9_run_parameter_package_combined_overlap"][1]
    assert "effective_range WITH &&" in rows["ex_task9_run_parameter_package_combined_overlap"][1]
    assert (
        "consumability_range WITH &&" in rows["ex_task9_run_parameter_package_combined_overlap"][1]
    )
    assert rows["ex_task9_daily_capacity_consumability_overlap"][0] == "x"
    assert (
        "capacity_pool_definition_id WITH ="
        in rows["ex_task9_daily_capacity_consumability_overlap"][1]
    )
    assert "capacity_date WITH =" in rows["ex_task9_daily_capacity_consumability_overlap"][1]
    assert "consumability_range WITH &&" in rows["ex_task9_daily_capacity_consumability_overlap"][1]
    assert rows["ex_task9_holiday_calendar_consumability_overlap"][0] == "x"
    assert "season_id WITH =" in rows["ex_task9_holiday_calendar_consumability_overlap"][1]
    assert "calendar_code WITH =" in rows["ex_task9_holiday_calendar_consumability_overlap"][1]
    assert (
        "lifecycle_timezone_name WITH ="
        in rows["ex_task9_holiday_calendar_consumability_overlap"][1]
    )
    assert (
        "consumability_range WITH &&" in rows["ex_task9_holiday_calendar_consumability_overlap"][1]
    )
    assert rows["ex_task9_weather_rule_combined_overlap"][0] == "x"
    assert "rule_code WITH =" in rows["ex_task9_weather_rule_combined_overlap"][1]
    assert "lifecycle_timezone_name WITH =" in rows["ex_task9_weather_rule_combined_overlap"][1]
    assert "effective_range WITH &&" in rows["ex_task9_weather_rule_combined_overlap"][1]
    assert "consumability_range WITH &&" in rows["ex_task9_weather_rule_combined_overlap"][1]
    assert rows["ex_task9_initial_inventory_consumability_overlap"][0] == "x"
    assert "season_id WITH =" in rows["ex_task9_initial_inventory_consumability_overlap"][1]
    assert (
        "destination_factory_id WITH ="
        in rows["ex_task9_initial_inventory_consumability_overlap"][1]
    )
    assert (
        "opening_state_date WITH =" in rows["ex_task9_initial_inventory_consumability_overlap"][1]
    )
    assert (
        "consumability_range WITH &&" in rows["ex_task9_initial_inventory_consumability_overlap"][1]
    )
    assert rows["ex_task9_mature_loss_consumability_overlap"][0] == "x"
    assert "season_id WITH =" in rows["ex_task9_mature_loss_consumability_overlap"][1]
    assert "destination_factory_id WITH =" in rows["ex_task9_mature_loss_consumability_overlap"][1]
    assert "capacity_pool_code WITH =" in rows["ex_task9_mature_loss_consumability_overlap"][1]
    assert "state_date WITH =" in rows["ex_task9_mature_loss_consumability_overlap"][1]
    assert "forecast_quantile WITH =" in rows["ex_task9_mature_loss_consumability_overlap"][1]
    assert "consumability_range WITH &&" in rows["ex_task9_mature_loss_consumability_overlap"][1]
    assert rows["uq_task9_authority_lifecycle_event_identity_sequence"][0] == "u"
    assert rows["uq_task9_authority_lifecycle_event_identity_hash"][0] == "u"


@pytest.mark.asyncio
async def test_task9_authority_valid_insert_bundle_succeeds() -> None:
    _require_postgres()
    inserted = await _insert_valid_bundle()
    assert inserted["run_package_id"] > 0
    assert inserted["daily_id"] > 0
    assert inserted["snapshot_id"] > 0
    assert inserted["loss_id"] > 0
    assert inserted["event_id"] > 0


@pytest.mark.asyncio
async def test_duplicate_nullable_member_key_is_rejected() -> None:
    _require_postgres()
    ids = await _seed_dimensions()
    pool_id = await _insert_capacity_pool_definition(
        season_id=ids["season_id"],
        factory_id=ids["factory_id"],
        status="retired",
        consumable_from=_date(2),
        consumable_to=_date(20),
    )
    await _insert_pool_member(
        pool_id=pool_id,
        season_id=ids["season_id"],
        factory_id=ids["factory_id"],
        farm_id=ids["farm_id"],
        subfarm_id=None,
        variety_id=ids["variety_id"],
        status="retired",
        consumable_from_key=_date(2),
        consumable_to_key=_date(20),
    )
    exc = await _expect_integrity_error(
        """
        INSERT INTO task9_capacity_pool_member (
            capacity_pool_definition_id,
            season_id,
            destination_factory_id,
            farm_id,
            subfarm_id,
            variety_id,
            effective_from,
            effective_to,
            status,
            consumable_from_key,
            consumable_to_key,
            row_hash
        )
        VALUES (
            :pool_id, :season_id, :factory_id, :farm_id, NULL, :variety_id,
            :effective_from, :effective_to, :status, :consumable_from_key, :consumable_to_key, :row_hash
        )
        """,
        {
            "pool_id": pool_id,
            "season_id": ids["season_id"],
            "factory_id": ids["factory_id"],
            "farm_id": ids["farm_id"],
            "variety_id": ids["variety_id"],
            "effective_from": _date(1),
            "effective_to": None,
            "status": "retired",
            "consumable_from_key": _date(2),
            "consumable_to_key": _date(20),
            "row_hash": _sha("8"),
        },
    )
    assert _constraint_name(exc) == "uq_task9_capacity_pool_member_business_key"


@pytest.mark.asyncio
async def test_invalid_status_invalid_sha_revision_ratio_and_negative_quantity_are_rejected() -> (
    None
):
    _require_postgres()
    ids = await _seed_dimensions()

    await _expect_integrity_error(
        """
        INSERT INTO task9_holiday_calendar_version (
            season_id, calendar_code, lifecycle_timezone_name, calendar_version, revision,
            region_scope, calendar_hash, available_at_local_date, consumable_from_local_date,
            consumable_to_local_date, status, status_changed_at, superseded_by_id,
            source_system, source_record_key, source_version, row_hash
        )
        VALUES (
            :season_id, 'CAL-1', 'Asia/Shanghai', 'v1', 1, NULL, :calendar_hash, :available_at,
            NULL, NULL, 'invalid', :status_changed_at, NULL,
            'task9_historical_authority', 'bad-status', 'src-v1', :row_hash
        )
        """,
        {
            "season_id": ids["season_id"],
            "calendar_hash": _sha("9"),
            "available_at": _date(1),
            "status_changed_at": _ts(),
            "row_hash": _sha("a"),
        },
    )

    await _expect_integrity_error(
        """
        INSERT INTO task9_mature_inventory_loss_authority (
            season_id, destination_factory_id, state_date, capacity_pool_code, forecast_quantile,
            loss_version, revision, mature_inventory_loss_quantity_kg, available_at_local_date,
            consumable_from_local_date, consumable_to_local_date, status, status_changed_at,
            superseded_by_id, source_system, source_record_key, source_version, row_hash
        )
        VALUES (
            :season_id, :factory_id, :state_date, 'POOL-A', 'P50', 'v1', 0, 1.000000, :available_at,
            NULL, NULL, 'draft', :status_changed_at, NULL,
            'task9_historical_authority', 'bad-revision', 'src-v1', :row_hash
        )
        """,
        {
            "season_id": ids["season_id"],
            "factory_id": ids["factory_id"],
            "state_date": _date(4),
            "available_at": _date(1),
            "status_changed_at": _ts(),
            "row_hash": _sha("b"),
        },
    )

    await _expect_integrity_error(
        """
        INSERT INTO task9_weather_rule_config_version (
            rule_code, lifecycle_timezone_name, rule_version, revision, combination_method,
            minimum_ratio, maximum_ratio, required_feature_ids, feature_rules_json,
            missing_feature_policy, config_hash, available_at_local_date, consumable_from_local_date,
            consumable_to_local_date, effective_from, effective_to, status, status_changed_at,
            superseded_by_id, source_system, source_record_key, source_version, row_hash
        )
        VALUES (
            'WR-1', 'Asia/Shanghai', 'v1', 1, 'MULTIPLY',
            1.100000, 1.000000, '[]'::jsonb, '[]'::jsonb, 'BLOCK',
            :config_hash, :available_at, NULL, NULL, :effective_from, NULL,
            'draft', :status_changed_at, NULL, 'task9_historical_authority', 'bad-ratio', 'src-v1', :row_hash
        )
        """,
        {
            "config_hash": _sha("c"),
            "available_at": _date(1),
            "effective_from": _date(1),
            "status_changed_at": _ts(),
            "row_hash": _sha("d"),
        },
    )

    await _expect_integrity_error(
        """
        INSERT INTO task9_initial_inventory_snapshot (
            season_id, destination_factory_id, opening_state_date, snapshot_version, revision,
            initial_opening_mature_inventory_kg, available_at_local_date, consumable_from_local_date,
            consumable_to_local_date, status, status_changed_at, superseded_by_id,
            source_system, source_record_key, source_version, row_hash
        )
        VALUES (
            :season_id, :factory_id, :opening_state_date, 'v1', 1,
            -1.000000, :available_at, NULL, NULL, 'draft', :status_changed_at, NULL,
            'task9_historical_authority', 'negative-qty', 'src-v1', :row_hash
        )
        """,
        {
            "season_id": ids["season_id"],
            "factory_id": ids["factory_id"],
            "opening_state_date": _date(3),
            "available_at": _date(1),
            "status_changed_at": _ts(),
            "row_hash": _sha("e"),
        },
    )

    await _expect_integrity_error(
        """
        INSERT INTO task9_capacity_pool_definition (
            season_id, destination_factory_id, capacity_pool_code, capacity_pool_version, revision,
            capacity_pool_grain, capacity_input_mode, effective_from, effective_to, available_at_local_date,
            consumable_from_local_date, consumable_to_local_date, status, status_changed_at,
            source_system, source_record_key, source_version, row_hash, superseded_by_id
        )
        VALUES (
            :season_id, :factory_id, 'POOL-A', 'v1', 1, 'FARM', 'LABOR_DERIVED',
            :effective_from, NULL, :available_at, NULL, NULL, 'draft', :status_changed_at,
            'task9_historical_authority', 'bad-sha', 'src-v1', 'not-a-sha', NULL
        )
        """,
        {
            "season_id": ids["season_id"],
            "factory_id": ids["factory_id"],
            "effective_from": _date(1),
            "available_at": _date(1),
            "status_changed_at": _ts(),
        },
    )


@pytest.mark.asyncio
async def test_invalid_effective_range_consumability_projection_and_daily_mode_are_rejected() -> (
    None
):
    _require_postgres()
    ids = await _seed_dimensions()

    await _expect_integrity_error(
        """
        INSERT INTO task9_capacity_pool_definition (
            season_id, destination_factory_id, capacity_pool_code, capacity_pool_version, revision,
            capacity_pool_grain, capacity_input_mode, effective_from, effective_to, available_at_local_date,
            consumable_from_local_date, consumable_to_local_date, status, status_changed_at,
            source_system, source_record_key, source_version, row_hash, superseded_by_id
        )
        VALUES (
            :season_id, :factory_id, 'POOL-A', 'v1', 1, 'FARM', 'LABOR_DERIVED',
            :effective_from, :effective_to, :available_at, :consumable_from, NULL,
            'active', :status_changed_at, 'task9_historical_authority', 'bad-effective', 'src-v1', :row_hash, NULL
        )
        """,
        {
            "season_id": ids["season_id"],
            "factory_id": ids["factory_id"],
            "effective_from": _date(5),
            "effective_to": _date(4),
            "available_at": _date(1),
            "consumable_from": _date(2),
            "status_changed_at": _ts(),
            "row_hash": _sha("f"),
        },
    )

    pool_id = await _insert_capacity_pool_definition(
        season_id=ids["season_id"],
        factory_id=ids["factory_id"],
        status="active",
        consumable_from=_date(2),
    )
    exc = await _expect_integrity_error(
        """
        INSERT INTO task9_daily_capacity_authority (
            capacity_pool_definition_id, capacity_date, daily_capacity_revision, planned_picker_count,
            kg_per_person_per_day, direct_nominal_capacity_kg_per_day, labor_availability_ratio,
            operational_efficiency_ratio, available_at_local_date, consumable_from_local_date,
            consumable_to_local_date, status, status_changed_at, superseded_by_id,
            source_system, source_record_key, source_version, row_hash
        )
        VALUES (
            :pool_id, :capacity_date, 1, 10.000, 100.000, NULL, 0.800000, 0.900000,
            :available_at, NULL, NULL, 'active', :status_changed_at, NULL,
            'task9_historical_authority', 'bad-projection', 'src-v1', :row_hash
        )
        """,
        {
            "pool_id": pool_id,
            "capacity_date": _date(3),
            "available_at": _date(1),
            "status_changed_at": _ts(),
            "row_hash": _sha("1"),
        },
    )
    assert _constraint_name(exc) == "ck_task9_daily_capacity_authority_lifecycle_projection"

    await _expect_integrity_error(
        """
        INSERT INTO task9_daily_capacity_authority (
            capacity_pool_definition_id, capacity_date, daily_capacity_revision, planned_picker_count,
            kg_per_person_per_day, direct_nominal_capacity_kg_per_day, labor_availability_ratio,
            operational_efficiency_ratio, available_at_local_date, consumable_from_local_date,
            consumable_to_local_date, status, status_changed_at, superseded_by_id,
            source_system, source_record_key, source_version, row_hash
        )
        VALUES (
            :pool_id, :capacity_date, 1, 10.000, 100.000, 200.000, 0.800000, 0.900000,
            :available_at, :consumable_from, NULL, 'active', :status_changed_at, NULL,
            'task9_historical_authority', 'bad-mode', 'src-v1', :row_hash
        )
        """,
        {
            "pool_id": pool_id,
            "capacity_date": _date(3),
            "available_at": _date(1),
            "consumable_from": _date(2),
            "status_changed_at": _ts(),
            "row_hash": _sha("2"),
        },
    )

    for value, field, expected_constraint, record_key in (
        (
            -1,
            "planned_picker_count",
            "ck_task9_daily_capacity_picker_count_non_negative",
            "bad-picker-count",
        ),
        (
            -1,
            "kg_per_person_per_day",
            "ck_task9_daily_capacity_productivity_non_negative",
            "bad-productivity",
        ),
        (
            -1,
            "direct_nominal_capacity_kg_per_day",
            "ck_task9_daily_capacity_direct_capacity_non_negative",
            "bad-direct-capacity",
        ),
    ):
        sql = """
        INSERT INTO task9_daily_capacity_authority (
            capacity_pool_definition_id, capacity_date, daily_capacity_revision, planned_picker_count,
            kg_per_person_per_day, direct_nominal_capacity_kg_per_day, labor_availability_ratio,
            operational_efficiency_ratio, available_at_local_date, consumable_from_local_date,
            consumable_to_local_date, status, status_changed_at, superseded_by_id,
            source_system, source_record_key, source_version, row_hash
        )
        VALUES (
            :pool_id, :capacity_date, :revision, :planned_picker_count, :kg_per_person_per_day,
            :direct_nominal_capacity_kg_per_day, 0.800000, 0.900000, :available_at,
            :consumable_from, NULL, 'active', :status_changed_at, NULL,
            'task9_historical_authority', :source_record_key, 'src-v1', :row_hash
        )
        """
        params = {
            "pool_id": pool_id,
            "capacity_date": _date(4),
            "revision": 2 if field != "direct_nominal_capacity_kg_per_day" else 3,
            "planned_picker_count": None,
            "kg_per_person_per_day": None,
            "direct_nominal_capacity_kg_per_day": None,
            "available_at": _date(1),
            "consumable_from": _date(2),
            "status_changed_at": _ts(),
            "source_record_key": record_key,
            "row_hash": _sha(record_key[0]),
        }
        if field == "direct_nominal_capacity_kg_per_day":
            params["direct_nominal_capacity_kg_per_day"] = value
        else:
            params["planned_picker_count"] = 10 if field != "planned_picker_count" else value
            params["kg_per_person_per_day"] = 100 if field != "kg_per_person_per_day" else value
        exc = await _expect_integrity_error(sql, params)
        assert _constraint_name(exc) == expected_constraint


@pytest.mark.asyncio
async def test_invalid_superseded_and_lifecycle_event_replacement_identity_are_rejected() -> None:
    _require_postgres()
    ids = await _seed_dimensions()

    await _expect_integrity_error(
        """
        INSERT INTO task9_capacity_pool_definition (
            season_id, destination_factory_id, capacity_pool_code, capacity_pool_version, revision,
            capacity_pool_grain, capacity_input_mode, effective_from, effective_to, available_at_local_date,
            consumable_from_local_date, consumable_to_local_date, status, status_changed_at,
            source_system, source_record_key, source_version, row_hash, superseded_by_id
        )
        VALUES (
            :season_id, :factory_id, 'POOL-A', 'v1', 1, 'FARM', 'LABOR_DERIVED',
            :effective_from, NULL, :available_at, :consumable_from, NULL,
            'superseded', :status_changed_at, 'task9_historical_authority', 'bad-superseded', 'src-v1', :row_hash, NULL
        )
        """,
        {
            "season_id": ids["season_id"],
            "factory_id": ids["factory_id"],
            "effective_from": _date(1),
            "available_at": _date(1),
            "consumable_from": _date(2),
            "status_changed_at": _ts(),
            "row_hash": _sha("3"),
        },
    )

    await _expect_integrity_error(
        """
        INSERT INTO task9_authority_lifecycle_event (
            authority_family, authority_stable_key, authority_business_version, authority_revision,
            business_row_hash, transition_sequence, old_status, new_status,
            old_consumable_from_local_date, old_consumable_to_local_date,
            new_consumable_from_local_date, new_consumable_to_local_date,
            superseded_by_authority_stable_key, superseded_by_authority_business_version,
            superseded_by_authority_revision, transitioned_at, source_system, source_record_key,
            lifecycle_event_hash
        )
        VALUES (
            'capacity_pool_definition', 'capacity-pool:1:1:POOL-A', 'v1', 1,
            :business_row_hash, 1, NULL, 'retired',
            NULL, NULL, NULL, NULL,
            'capacity-pool:1:1:POOL-B', 'v1', 2, :transitioned_at,
            'task9_historical_authority', 'bad-lifecycle', :lifecycle_event_hash
        )
        """,
        {
            "business_row_hash": _sha("4"),
            "transitioned_at": _ts(),
            "lifecycle_event_hash": _sha("5"),
        },
    )


@pytest.mark.asyncio
async def test_duplicate_holiday_date_and_duplicate_cohort_key_are_rejected() -> None:
    _require_postgres()
    ids = await _insert_valid_bundle()

    await _expect_integrity_error(
        """
        INSERT INTO task9_holiday_calendar_date (
            holiday_calendar_version_id, holiday_date, holiday_code, holiday_name
        )
        VALUES (:holiday_id, :holiday_date, 'CNY', 'Holiday Name')
        """,
        {"holiday_id": ids["holiday_id"], "holiday_date": _date(10)},
    )

    await _expect_integrity_error(
        """
        INSERT INTO task9_initial_inventory_cohort (
            initial_inventory_snapshot_id, stable_cohort_key, forecast_quantile, cohort_date,
            farm_id, subfarm_id, variety_id, remaining_quantity_kg, row_hash
        )
        VALUES (
            :snapshot_id, 'cohort-1', 'P80', :cohort_date, :farm_id, :subfarm_id, :variety_id,
            1.000000, :row_hash
        )
        """,
        {
            "snapshot_id": ids["snapshot_id"],
            "cohort_date": _date(3),
            "farm_id": ids["farm_id"],
            "subfarm_id": ids["subfarm_id"],
            "variety_id": ids["variety_id"],
            "row_hash": _sha("6"),
        },
    )


@pytest.mark.asyncio
async def test_duplicate_lifecycle_transition_sequence_is_rejected() -> None:
    _require_postgres()
    await _insert_lifecycle_event()
    await _expect_integrity_error(
        """
        INSERT INTO task9_authority_lifecycle_event (
            authority_family, authority_stable_key, authority_business_version, authority_revision,
            business_row_hash, transition_sequence, old_status, new_status,
            old_consumable_from_local_date, old_consumable_to_local_date,
            new_consumable_from_local_date, new_consumable_to_local_date,
            superseded_by_authority_stable_key, superseded_by_authority_business_version,
            superseded_by_authority_revision, transitioned_at, source_system, source_record_key,
            lifecycle_event_hash
        )
        VALUES (
            'capacity_pool_definition', 'capacity-pool:1:1:POOL-A', 'v1', 1,
            :business_row_hash, 1, 'draft', 'active',
            NULL, NULL, :new_from, NULL,
            NULL, NULL, NULL, :transitioned_at,
            'task9_historical_authority', 'dup-seq', :lifecycle_event_hash
        )
        """,
        {
            "business_row_hash": _sha("7"),
            "new_from": _date(2),
            "transitioned_at": _ts(),
            "lifecycle_event_hash": _sha("8"),
        },
    )


@pytest.mark.asyncio
async def test_overlapping_effective_and_consumability_intervals_are_rejected_but_adjacent_allowed() -> (
    None
):
    _require_postgres()
    ids = await _seed_dimensions()

    await _insert_capacity_pool_definition(
        season_id=ids["season_id"],
        factory_id=ids["factory_id"],
        code="POOL-A",
        version="v1",
        revision=1,
        status="retired",
        effective_from=_date(1),
        effective_to=_date(10),
        available_at=_date(1),
        consumable_from=_date(2),
        consumable_to=_date(11),
        row_hash=_sha("9"),
    )

    await _expect_integrity_error(
        """
        INSERT INTO task9_capacity_pool_definition (
            season_id, destination_factory_id, capacity_pool_code, capacity_pool_version, revision,
            capacity_pool_grain, capacity_input_mode, effective_from, effective_to, available_at_local_date,
            consumable_from_local_date, consumable_to_local_date, status, status_changed_at,
            source_system, source_record_key, source_version, row_hash, superseded_by_id
        )
        VALUES (
            :season_id, :factory_id, 'POOL-A', 'v2', 1, 'FARM', 'LABOR_DERIVED',
            :effective_from, :effective_to, :available_at, :consumable_from, :consumable_to,
            'retired', :status_changed_at, 'task9_historical_authority', 'overlap', 'src-v1', :row_hash, NULL
        )
        """,
        {
            "season_id": ids["season_id"],
            "factory_id": ids["factory_id"],
            "effective_from": _date(5),
            "effective_to": _date(12),
            "available_at": _date(1),
            "consumable_from": _date(6),
            "consumable_to": _date(13),
            "status_changed_at": _ts(),
            "row_hash": _sha("a"),
        },
    )

    adjacent_id = await _insert_capacity_pool_definition(
        season_id=ids["season_id"],
        factory_id=ids["factory_id"],
        code="POOL-A",
        version="v3",
        revision=1,
        status="retired",
        effective_from=_date(11),
        effective_to=_date(20),
        available_at=_date(1),
        consumable_from=_date(11),
        consumable_to=_date(20),
        row_hash=_sha("b"),
    )
    assert adjacent_id > 0


@pytest.mark.asyncio
async def test_open_ended_consumability_blocks_future_overlap() -> None:
    _require_postgres()
    ids = await _seed_dimensions()
    pool_id = await _insert_capacity_pool_definition(
        season_id=ids["season_id"],
        factory_id=ids["factory_id"],
        status="active",
        consumable_from=_date(2),
        row_hash=_sha("c"),
    )
    await _insert_daily_capacity(
        pool_id=pool_id,
        status="active",
        consumable_from=_date(2),
        consumable_to=None,
        row_hash=_sha("d"),
    )
    await _expect_integrity_error(
        """
        INSERT INTO task9_daily_capacity_authority (
            capacity_pool_definition_id, capacity_date, daily_capacity_revision, planned_picker_count,
            kg_per_person_per_day, direct_nominal_capacity_kg_per_day, labor_availability_ratio,
            operational_efficiency_ratio, available_at_local_date, consumable_from_local_date,
            consumable_to_local_date, status, status_changed_at, superseded_by_id,
            source_system, source_record_key, source_version, row_hash
        )
        VALUES (
            :pool_id, :capacity_date, 2, 10.000, 100.000, NULL, 0.800000, 0.900000,
            :available_at, :consumable_from, :consumable_to, 'retired', :status_changed_at, NULL,
            'task9_historical_authority', 'open-overlap', 'src-v1', :row_hash
        )
        """,
        {
            "pool_id": pool_id,
            "capacity_date": _date(3),
            "available_at": _date(1),
            "consumable_from": _date(5),
            "consumable_to": _date(7),
            "status_changed_at": _ts(),
            "row_hash": _sha("e"),
        },
    )


@pytest.mark.asyncio
async def test_orm_and_migration_parity_for_ordinary_columns() -> None:
    _require_postgres()
    expected = {
        Task9CapacityPoolDefinition.__tablename__: Task9CapacityPoolDefinition.__table__,
        Task9CapacityPoolMember.__tablename__: Task9CapacityPoolMember.__table__,
        Task9DailyCapacityAuthority.__tablename__: Task9DailyCapacityAuthority.__table__,
        Task9RunParameterPackage.__tablename__: Task9RunParameterPackage.__table__,
        Task9HolidayCalendarVersion.__tablename__: Task9HolidayCalendarVersion.__table__,
        Task9HolidayCalendarDate.__tablename__: Task9HolidayCalendarDate.__table__,
        Task9WeatherRuleConfigVersion.__tablename__: Task9WeatherRuleConfigVersion.__table__,
        Task9InitialInventorySnapshot.__tablename__: Task9InitialInventorySnapshot.__table__,
        Task9InitialInventoryCohort.__tablename__: Task9InitialInventoryCohort.__table__,
        Task9MatureInventoryLossAuthority.__tablename__: Task9MatureInventoryLossAuthority.__table__,
        Task9AuthorityLifecycleEvent.__tablename__: Task9AuthorityLifecycleEvent.__table__,
    }
    migration_only_columns = {
        "task9_capacity_pool_definition": {
            "effective_to_exclusive",
            "effective_range",
            "consumable_from_key",
            "consumable_to_key",
            "consumability_range",
        },
        "task9_capacity_pool_member": {
            "normalized_subfarm_id",
            "effective_to_exclusive",
            "effective_range",
            "consumability_range",
        },
        "task9_daily_capacity_authority": {"consumability_range"},
        "task9_holiday_calendar_version": {"consumability_range"},
        "task9_weather_rule_config_version": {
            "consumability_range",
            "effective_to_exclusive",
            "effective_range",
        },
        "task9_run_parameter_package": {
            "consumability_range",
            "effective_to_exclusive",
            "effective_range",
        },
        "task9_initial_inventory_snapshot": {"consumability_range"},
        "task9_mature_inventory_loss_authority": {"consumability_range"},
    }

    async with AsyncSessionMaker() as session:
        result = await session.execute(
            text(
                """
                SELECT
                    table_name,
                    column_name,
                    data_type,
                    udt_name,
                    is_nullable,
                    numeric_precision,
                    numeric_scale,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name LIKE 'task9_%'
                ORDER BY table_name, ordinal_position
                """
            )
        )
        db_rows = {}
        for row in result:
            db_rows.setdefault(row.table_name, {})[row.column_name] = row

        fk_rows = await session.execute(
            text(
                """
                SELECT
                    tc.table_name,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name,
                    rc.update_rule,
                    rc.delete_rule
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                JOIN information_schema.referential_constraints AS rc
                  ON tc.constraint_name = rc.constraint_name
                 AND tc.table_schema = rc.constraint_schema
                JOIN information_schema.constraint_column_usage AS ccu
                  ON rc.unique_constraint_name = ccu.constraint_name
                 AND rc.unique_constraint_schema = ccu.constraint_schema
                WHERE tc.table_schema = 'public'
                  AND tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_name LIKE 'task9_%'
                ORDER BY tc.table_name, kcu.column_name
                """
            )
        )
        db_fks = {
            (row.table_name, row.column_name): (
                row.foreign_table_name,
                row.foreign_column_name,
                row.update_rule,
                row.delete_rule,
            )
            for row in fk_rows
        }

        generated = await session.execute(
            text(
                """
                SELECT table_name, column_name, generation_expression
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND is_generated = 'ALWAYS'
                  AND table_name LIKE 'task9_%'
                """
            )
        )
        generated_rows = {
            (row.table_name, row.column_name): row.generation_expression for row in generated
        }

    for table_name, table in expected.items():
        for column in table.columns:
            assert column.name in db_rows[table_name]
            db_column = db_rows[table_name][column.name]
            assert column.nullable == (db_column.is_nullable == "YES")
            if str(column.type).startswith("NUMERIC("):
                assert db_column.data_type == "numeric"
                precision, scale = (
                    str(column.type).removeprefix("NUMERIC(").removesuffix(")").split(", ")
                )
                assert db_column.numeric_precision == int(precision)
                assert db_column.numeric_scale == int(scale)
            elif str(column.type) == "DATETIME":
                assert db_column.data_type == "timestamp with time zone"
            elif str(column.type) == "DATE":
                assert db_column.data_type == "date"
            elif str(column.type) == "TIME":
                assert db_column.data_type == "time without time zone"
            elif str(column.type) == "JSONB":
                assert db_column.data_type == "jsonb"
                assert db_column.udt_name == "jsonb"
            elif str(column.type) in {"TEXT", "BIGINT", "INTEGER"}:
                expected_type = {
                    "TEXT": "text",
                    "BIGINT": "bigint",
                    "INTEGER": "integer",
                }[str(column.type)]
                assert db_column.data_type == expected_type
            if column.server_default is not None and column.name == "created_at":
                assert db_column.column_default is not None
                assert "now()" in db_column.column_default
            for foreign_key in column.foreign_keys:
                target_table, target_column = foreign_key.target_fullname.split(".")
                assert db_fks[(table_name, column.name)] == (
                    target_table,
                    target_column,
                    foreign_key.onupdate or "NO ACTION",
                    foreign_key.ondelete or "NO ACTION",
                )
        extra_columns = set(db_rows[table_name]) - {column.name for column in table.columns}
        assert extra_columns == migration_only_columns.get(table_name, set())

    assert (
        "COALESCE(subfarm_id, 0)"
        in generated_rows[("task9_capacity_pool_member", "normalized_subfarm_id")]
    )
    assert (
        "'infinity'::date"
        in generated_rows[("task9_capacity_pool_definition", "effective_to_exclusive")]
        or "infinity"
        in generated_rows[("task9_capacity_pool_definition", "effective_to_exclusive")]
    )
    assert (
        "effective_to + 1"
        in generated_rows[("task9_capacity_pool_definition", "effective_to_exclusive")]
    )
    assert "[)" in generated_rows[("task9_capacity_pool_definition", "effective_range")]
    assert "[)" in generated_rows[("task9_daily_capacity_authority", "consumability_range")]
    assert ("task9_capacity_pool_member", "consumable_from_key") not in generated_rows
    assert ("task9_capacity_pool_member", "consumable_to_key") not in generated_rows
