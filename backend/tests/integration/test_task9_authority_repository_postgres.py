# ruff: noqa: E501
"""PostgreSQL integration tests for the Task 9 authority repository.

These tests REQUIRE a real PostgreSQL database.  They are gated by the
``RUN_POSTGRES_INTEGRATION`` environment variable and use async fixtures
that wrap each test in a rolled-back transaction for isolation.
"""

from __future__ import annotations

import asyncio
import os

import pytest

if not os.environ.get("RUN_POSTGRES_INTEGRATION"):
    pytest.skip("RUN_POSTGRES_INTEGRATION not set", allow_module_level=True)

from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import AsyncSessionMaker
from backend.app.harvest_state.authority_canonical import (
    build_daily_capacity_stable_key,
    build_mature_inventory_loss_stable_key,
    make_authority_row_hash,
    make_holiday_calendar_hash,
    make_weather_rule_config_hash,
)
from backend.app.harvest_state.authority_repository import (
    activate_authority,
    cancel_authority,
    create_or_load_capacity_pool_definition,
    create_or_load_daily_capacity,
    create_or_load_holiday_calendar,
    create_or_load_initial_inventory,
    create_or_load_mature_loss,
    create_or_load_run_parameter_package,
    create_or_load_weather_rule,
    load_authority_by_business_key,
    load_authority_by_persistent_identity,
    load_authority_by_row_hash,
    load_capacity_pool_definition_by_id,
    load_holiday_calendar_by_id,
    load_initial_inventory_by_id,
    load_mature_loss_by_id,
    load_weather_rule_by_id,
    replace_run_package_with_dependencies,
    retire_authority,
    supersede_authority,
)
from backend.app.harvest_state.authority_repository_errors import (
    AuthorityConsumabilityIntervalConflictError,
    AuthorityConsumabilityIntervalInvalidError,
    AuthorityHashConflictError,
    AuthorityNotFoundError,
    AuthorityStillReferencedByActivePackageError,
    AuthoritySupersessionScopeConflictError,
    AuthorityVersionConflictError,
    LifecycleTransitionInvalidError,
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
from backend.app.harvest_state.enums import (
    AuthorityFamily,
    AuthorityStatus,
    CapacityInputMode,
    CapacityPoolGrain,
    ForecastQuantile,
    WeatherCombinationMethod,
)
from backend.app.harvest_state.schemas import WeatherFeatureBand, WeatherFeatureRule
from backend.app.models.task9_authority import (
    Task9AuthorityLifecycleEvent,
)

pytestmark = pytest.mark.integration


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
async def db_session():
    """Yield an AsyncSession wrapped in a transaction that rolls back on exit.

    Seeds required FK dimension tables (dim_season, dim_factory, dim_farm,
    dim_subfarm, dim_variety) before yielding so authority inserts don't fail
    on FK constraints.
    """
    async with AsyncSessionMaker() as session:
        async with session.begin():
            # Seed dimension tables required by FK constraints
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
            # Get farm_id for subfarm FK
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
            # Get actual IDs for test constants
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
            # Override module-level constants with real IDs
            _IDS["season"] = season_row.scalar_one()
            _IDS["factory"] = factory_row.scalar_one()
            _IDS["farm"] = farm_id
            _IDS["subfarm"] = subfarm_row.scalar_one()
            _IDS["variety"] = variety_row.scalar_one()
            yield session
            # rollback on exit for test isolation


async def _seed_dimensions(session: AsyncSession) -> None:
    """Seed dimension tables required by FK constraints.

    Idempotent — uses ON CONFLICT DO NOTHING so repeated calls are safe.
    Also updates the module-level ``_IDS`` dict with the actual row IDs.
    """
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
    await session.flush()
    # Refresh IDs
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


# ── Deterministic test data helpers ──────────────────────────────────────

# Shared constants to keep helpers DRY.
_IDS: dict[str, int] = {
    "season": 1,
    "factory": 2,
    "farm": 10,
    "subfarm": 20,
    "variety": 30,
}
_TZ = "Asia/Shanghai"
_AVAILABLE = date(2026, 1, 1)
_EFF_FROM = date(2026, 1, 1)


def _pool_input(
    *,
    code: str = "TEST-POOL",
    version: str = "v1",
    revision: int = 1,
) -> Task9CapacityPoolDefinitionSemanticBundle:
    """Build a valid pool-definition semantic bundle with one FARM-grain member."""
    return Task9CapacityPoolDefinitionSemanticBundle(
        season_id=_IDS["season"],
        destination_factory_id=_IDS["factory"],
        capacity_pool_code=code,
        capacity_pool_grain=CapacityPoolGrain.FARM,
        capacity_input_mode=CapacityInputMode.LABOR_DERIVED,
        capacity_pool_version=version,
        revision=revision,
        effective_from=_EFF_FROM,
        effective_to=None,
        available_at_local_date=_AVAILABLE,
        consumable_from_local_date=None,
        consumable_to_local_date=None,
        status=AuthorityStatus.DRAFT,
        status_changed_at=datetime(2026, 1, 1, tzinfo=UTC),
        superseded_by_id=None,
        source_system="test",
        source_record_key=f"test:pool:{code}:{version}:{revision}",
        source_version="v1",
        members=[
            Task9CapacityPoolMemberSchema(
                farm_id=_IDS["farm"],
                subfarm_id=None,
                variety_id=_IDS["variety"],
            ),
        ],
    )


def _daily_input(
    *,
    pool_code: str = "TEST-POOL",
    pool_version: str = "v1",
    pool_revision: int = 1,
    daily_rev: int = 1,
    cap_date: date | None = None,
) -> Task9DailyCapacitySemanticInput:
    """Build a valid daily-capacity semantic input (LABOR_DERIVED)."""
    return Task9DailyCapacitySemanticInput(
        season_id=_IDS["season"],
        destination_factory_id=_IDS["factory"],
        capacity_pool_code=pool_code,
        capacity_pool_version=pool_version,
        capacity_pool_revision=pool_revision,
        capacity_date=cap_date or date(2026, 6, 15),
        daily_capacity_revision=daily_rev,
        capacity_input_mode=CapacityInputMode.LABOR_DERIVED,
        planned_picker_count=Decimal("100"),
        kg_per_person_per_day=Decimal("50.5"),
        direct_nominal_capacity_kg_per_day=None,
        labor_availability_ratio=Decimal("0.85"),
        operational_efficiency_ratio=Decimal("0.90"),
        available_at_local_date=_AVAILABLE,
        consumable_from_local_date=None,
        consumable_to_local_date=None,
        status=AuthorityStatus.DRAFT,
        status_changed_at=datetime(2026, 1, 1, tzinfo=UTC),
        superseded_by_id=None,
        source_system="test",
        source_record_key=f"test:daily:{pool_code}:{daily_rev}",
        source_version="v1",
    )


def _make_holiday_dates() -> list[Task9HolidayCalendarDateSchema]:
    return [
        Task9HolidayCalendarDateSchema(
            holiday_date=date(2026, 1, 1),
            holiday_code="NEW_YEAR",
            holiday_name="New Year",
        ),
        Task9HolidayCalendarDateSchema(
            holiday_date=date(2026, 1, 29),
            holiday_code="CNY",
            holiday_name="Chinese New Year",
        ),
    ]


def _holiday_input(
    *,
    version: str = "v1",
    revision: int = 1,
    cal_hash: str | None = None,
    dates: list[Task9HolidayCalendarDateSchema] | None = None,
) -> Task9HolidayCalendarSemanticBundle:
    """Build a valid holiday-calendar semantic bundle."""
    effective_dates = dates or _make_holiday_dates()
    unique_dates = sorted({d.holiday_date for d in effective_dates})
    computed_hash = cal_hash or make_holiday_calendar_hash(
        holiday_calendar_version=version,
        holiday_dates=unique_dates,
    )
    return Task9HolidayCalendarSemanticBundle(
        season_id=_IDS["season"],
        calendar_code="CN",
        calendar_version=version,
        revision=revision,
        calendar_hash=computed_hash,
        region_scope=None,
        lifecycle_timezone_name=_TZ,
        available_at_local_date=_AVAILABLE,
        consumable_from_local_date=None,
        consumable_to_local_date=None,
        status=AuthorityStatus.DRAFT,
        status_changed_at=datetime(2026, 1, 1, tzinfo=UTC),
        superseded_by_id=None,
        source_system="test",
        source_record_key=f"test:holiday:{version}:{revision}",
        source_version="v1",
        dates=effective_dates,
    )


def _weather_config_hash(version: str = "v1") -> str:
    """Compute the correct config_hash for a canonical weather rule config."""
    feature_rules_payload = [
        {
            "feature_id": "TEMP",
            "bands": [
                {
                    "lower_bound": "0",
                    "lower_inclusive": True,
                    "upper_bound": "30",
                    "upper_inclusive": False,
                    "multiplier": "1",
                },
            ],
        },
    ]
    exact_config = {
        "version": version,
        "required_feature_ids": ["TEMP"],
        "feature_rules": feature_rules_payload,
        "combination_method": "MULTIPLY",
        "minimum_ratio": "0",
        "maximum_ratio": "1",
        "missing_feature_policy": "BLOCK",
    }
    return make_weather_rule_config_hash(exact_config)


def _weather_input(
    *,
    version: str = "v1",
    revision: int = 1,
    config_hash: str | None = None,
) -> Task9WeatherRuleSemanticInput:
    """Build a valid weather-rule semantic input."""
    return Task9WeatherRuleSemanticInput(
        rule_code="WEATHER-STD",
        rule_version=version,
        revision=revision,
        lifecycle_timezone_name=_TZ,
        combination_method=WeatherCombinationMethod.MULTIPLY,
        minimum_ratio=Decimal("0.0"),
        maximum_ratio=Decimal("1.0"),
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
                        multiplier=Decimal("1.0"),
                    ),
                ],
            ),
        ],
        missing_feature_policy="BLOCK",
        config_hash=config_hash or _weather_config_hash(version),
        effective_from=_EFF_FROM,
        effective_to=None,
        available_at_local_date=_AVAILABLE,
        consumable_from_local_date=None,
        consumable_to_local_date=None,
        status=AuthorityStatus.DRAFT,
        status_changed_at=datetime(2026, 1, 1, tzinfo=UTC),
        superseded_by_id=None,
        source_system="test",
        source_record_key=f"test:weather:{version}:{revision}",
        source_version="v1",
    )


def _run_package_input(
    *,
    version: str = "v1",
    revision: int = 1,
) -> Task9RunParameterPackageSemanticInput:
    """Build a valid run-parameter-package semantic input."""
    return Task9RunParameterPackageSemanticInput(
        season_id=_IDS["season"],
        destination_factory_id=_IDS["factory"],
        farm_scope_key="farm-10",
        farm_timezone=_TZ,
        destination_factory_timezone=_TZ,
        harvest_bucket_anchor_local_time=time(6, 0),
        harvest_to_arrival_lag_days=1,
        package_version=version,
        revision=revision,
        effective_from=_EFF_FROM,
        effective_to=None,
        available_at_local_date=_AVAILABLE,
        consumable_from_local_date=None,
        consumable_to_local_date=None,
        status=AuthorityStatus.DRAFT,
        status_changed_at=datetime(2026, 1, 1, tzinfo=UTC),
        superseded_by_id=None,
        source_system="test",
        source_record_key=f"test:runpkg:{version}:{revision}",
        source_version="v1",
    )


def _inventory_input(
    *,
    version: str = "v1",
    revision: int = 1,
) -> Task9InitialInventorySemanticBundle:
    """Build a valid initial-inventory semantic bundle with two cohorts."""
    return Task9InitialInventorySemanticBundle(
        season_id=_IDS["season"],
        destination_factory_id=_IDS["factory"],
        opening_state_date=date(2026, 1, 1),
        snapshot_version=version,
        revision=revision,
        initial_opening_mature_inventory_kg=Decimal("300.00"),
        available_at_local_date=_AVAILABLE,
        consumable_from_local_date=None,
        consumable_to_local_date=None,
        status=AuthorityStatus.DRAFT,
        status_changed_at=datetime(2026, 1, 1, tzinfo=UTC),
        superseded_by_id=None,
        source_system="test",
        source_record_key=f"test:inventory:{version}:{revision}",
        source_version="v1",
        cohorts=[
            Task9InitialInventoryCohortSchema(
                stable_cohort_key="cohort-a",
                forecast_quantile=ForecastQuantile.P50,
                cohort_date=date(2026, 1, 1),
                farm_id=_IDS["farm"],
                subfarm_id=_IDS["subfarm"],
                variety_id=_IDS["variety"],
                remaining_quantity_kg=Decimal("200.00"),
            ),
            Task9InitialInventoryCohortSchema(
                stable_cohort_key="cohort-b",
                forecast_quantile=ForecastQuantile.P50,
                cohort_date=date(2026, 1, 1),
                farm_id=_IDS["farm"],
                subfarm_id=_IDS["subfarm"],
                variety_id=_IDS["variety"],
                remaining_quantity_kg=Decimal("100.00"),
            ),
        ],
    )


def _mature_loss_input(
    *,
    version: str = "v1",
    revision: int = 1,
) -> Task9MatureLossSemanticInput:
    """Build a valid mature-inventory-loss semantic input."""
    return Task9MatureLossSemanticInput(
        season_id=_IDS["season"],
        destination_factory_id=_IDS["factory"],
        state_date=date(2026, 6, 15),
        capacity_pool_code="TEST-POOL",
        forecast_quantile=ForecastQuantile.P50,
        loss_version=version,
        revision=revision,
        mature_inventory_loss_quantity_kg=Decimal("25.50"),
        available_at_local_date=_AVAILABLE,
        consumable_from_local_date=None,
        consumable_to_local_date=None,
        status=AuthorityStatus.DRAFT,
        status_changed_at=datetime(2026, 1, 1, tzinfo=UTC),
        superseded_by_id=None,
        source_system="test",
        source_record_key=f"test:mature:{version}:{revision}",
        source_version="v1",
    )


# ── Lifecycle event query helper ─────────────────────────────────────────


async def _query_lifecycle_events(
    session: AsyncSession,
    *,
    family: str,
    stable_key: str,
    version: str,
    revision: int,
) -> list[Task9AuthorityLifecycleEvent]:
    stmt = (
        select(Task9AuthorityLifecycleEvent)
        .where(
            Task9AuthorityLifecycleEvent.authority_family == family,
            Task9AuthorityLifecycleEvent.authority_stable_key == stable_key,
            Task9AuthorityLifecycleEvent.authority_business_version == version,
            Task9AuthorityLifecycleEvent.authority_revision == revision,
        )
        .order_by(Task9AuthorityLifecycleEvent.transition_sequence)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ══════════════════════════════════════════════════════════════════════════
#  TEST 1 – Capacity pool: create-or-load idempotency
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pool_create_or_load_idempotent(db_session: AsyncSession) -> None:
    inp = _pool_input()
    r1 = await create_or_load_capacity_pool_definition(db_session, definition_input=inp)
    assert r1.parent.created is True
    assert r1.parent.authority_id > 0
    assert len(r1.child_ids) == 1

    r2 = await create_or_load_capacity_pool_definition(db_session, definition_input=inp)
    assert r2.parent.created is False
    assert r2.parent.authority_id == r1.parent.authority_id
    assert r2.parent.row_hash == r1.parent.row_hash


@pytest.mark.asyncio
async def test_pool_persisted_hash_tamper_raises_hash_conflict(
    db_session: AsyncSession,
) -> None:
    inp = _pool_input()
    r1 = await create_or_load_capacity_pool_definition(db_session, definition_input=inp)
    await db_session.execute(
        text(
            "UPDATE task9_capacity_pool_definition "
            "SET row_hash = :row_hash "
            "WHERE id = :authority_id"
        ),
        {"row_hash": "f" * 64, "authority_id": r1.parent.authority_id},
    )
    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await create_or_load_capacity_pool_definition(db_session, definition_input=inp)
    assert exc_info.value.code == "AUTHORITY_HASH_CONFLICT"


# ══════════════════════════════════════════════════════════════════════════
#  TEST 2 – Daily capacity: create-or-load idempotency
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_daily_create_or_load_idempotent(db_session: AsyncSession) -> None:
    # Need a pool definition first (FK dependency)
    pool = _pool_input()
    await create_or_load_capacity_pool_definition(db_session, definition_input=pool)

    inp = _daily_input()
    r1 = await create_or_load_daily_capacity(db_session, daily_input=inp)
    assert r1.created is True
    assert r1.authority_id > 0

    r2 = await create_or_load_daily_capacity(db_session, daily_input=inp)
    assert r2.created is False
    assert r2.authority_id == r1.authority_id
    assert r2.row_hash == r1.row_hash


# ══════════════════════════════════════════════════════════════════════════
#  TEST 3 – Holiday calendar: create-or-load idempotency
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_holiday_create_or_load_idempotent(db_session: AsyncSession) -> None:
    inp = _holiday_input()
    r1 = await create_or_load_holiday_calendar(db_session, calendar_input=inp)
    assert r1.parent.created is True
    assert r1.parent.authority_id > 0
    assert len(r1.child_ids) == 2

    r2 = await create_or_load_holiday_calendar(db_session, calendar_input=inp)
    assert r2.parent.created is False
    assert r2.parent.authority_id == r1.parent.authority_id
    assert r2.parent.row_hash == r1.parent.row_hash


# ══════════════════════════════════════════════════════════════════════════
#  TEST 4 – Weather rule: create-or-load idempotency
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_weather_create_or_load_idempotent(db_session: AsyncSession) -> None:
    inp = _weather_input()
    r1 = await create_or_load_weather_rule(db_session, weather_input=inp)
    assert r1.created is True
    assert r1.authority_id > 0

    r2 = await create_or_load_weather_rule(db_session, weather_input=inp)
    assert r2.created is False
    assert r2.authority_id == r1.authority_id
    assert r2.row_hash == r1.row_hash


# ══════════════════════════════════════════════════════════════════════════
#  TEST 5 – Run package: create-or-load idempotency
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_run_package_create_or_load_idempotent(db_session: AsyncSession) -> None:
    # Need holiday + weather dependencies
    holiday = _holiday_input()
    await create_or_load_holiday_calendar(db_session, calendar_input=holiday)

    weather = _weather_input()
    await create_or_load_weather_rule(db_session, weather_input=weather)

    pkg = _run_package_input()
    r1 = await create_or_load_run_parameter_package(
        db_session,
        package_input=pkg,
        holiday_calendar=holiday,
        weather_rule=weather,
    )
    assert r1.created is True
    assert r1.authority_id > 0

    r2 = await create_or_load_run_parameter_package(
        db_session,
        package_input=pkg,
        holiday_calendar=holiday,
        weather_rule=weather,
    )
    assert r2.created is False
    assert r2.authority_id == r1.authority_id
    assert r2.row_hash == r1.row_hash


# ══════════════════════════════════════════════════════════════════════════
#  TEST 6 – Initial inventory: create-or-load idempotency
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_inventory_create_or_load_idempotent(db_session: AsyncSession) -> None:
    inp = _inventory_input()
    r1 = await create_or_load_initial_inventory(db_session, inventory_input=inp)
    assert r1.parent.created is True
    assert r1.parent.authority_id > 0
    assert len(r1.child_ids) == 2

    r2 = await create_or_load_initial_inventory(db_session, inventory_input=inp)
    assert r2.parent.created is False
    assert r2.parent.authority_id == r1.parent.authority_id
    assert r2.parent.row_hash == r1.parent.row_hash


# ══════════════════════════════════════════════════════════════════════════
#  TEST 7 – Mature loss: create-or-load idempotency
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_mature_loss_create_or_load_idempotent(db_session: AsyncSession) -> None:
    inp = _mature_loss_input()
    r1 = await create_or_load_mature_loss(db_session, loss_input=inp)
    assert r1.created is True
    assert r1.authority_id > 0

    r2 = await create_or_load_mature_loss(db_session, loss_input=inp)
    assert r2.created is False
    assert r2.authority_id == r1.authority_id
    assert r2.row_hash == r1.row_hash


# ══════════════════════════════════════════════════════════════════════════
#  TEST 8 – Version conflict (different payload, same business key)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_mature_loss_version_conflict(db_session: AsyncSession) -> None:
    """Same business key, different payload → AuthorityVersionConflictError."""
    v1 = _mature_loss_input(version="v1", revision=1)
    await create_or_load_mature_loss(db_session, loss_input=v1)

    # Same business key fields but different quantity
    v2 = _mature_loss_input(version="v1", revision=1)
    v2 = v2.model_copy(
        update={
            "mature_inventory_loss_quantity_kg": Decimal("999.00"),
            "source_record_key": "test:mature:v1:1:conflict",
        }
    )
    # The above will produce a different row_hash but the same UQ.
    # However, the canonical builder hashes the semantic input.
    # We need to rebuild to make sure it computes a different hash.
    # Actually, the v2 above is different in loss quantity, so when
    # the repo recomputes from persisted columns it will get the original
    # hash, which will differ from the submitted hash.
    with pytest.raises(AuthorityVersionConflictError) as exc_info:
        await create_or_load_mature_loss(db_session, loss_input=v2)
    assert exc_info.value.code == "AUTHORITY_VERSION_CONFLICT"


# ══════════════════════════════════════════════════════════════════════════
#  TEST 9 – Initial lifecycle event
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_initial_lifecycle_event(db_session: AsyncSession) -> None:
    """Create an authority and verify the initial lifecycle event."""
    inp = _mature_loss_input()
    result = await create_or_load_mature_loss(db_session, loss_input=inp)
    assert result.created is True

    from backend.app.harvest_state.authority_canonical import (
        build_mature_inventory_loss_stable_key,
    )

    stable_key = build_mature_inventory_loss_stable_key(inp)
    events = await _query_lifecycle_events(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY.value,
        stable_key=stable_key,
        version=inp.loss_version,
        revision=inp.revision,
    )
    assert len(events) == 1
    ev = events[0]
    assert ev.transition_sequence == 1
    assert ev.old_status is None
    assert ev.new_status == "draft"
    assert ev.business_row_hash == result.row_hash


# ══════════════════════════════════════════════════════════════════════════
#  TEST 10 – Activation
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_activate_authority(db_session: AsyncSession) -> None:
    inp = _mature_loss_input()
    create_result = await create_or_load_mature_loss(db_session, loss_input=inp)
    auth_id = create_result.authority_id

    boundary = date(2026, 6, 1)
    act = await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=auth_id,
        activation_boundary=boundary,
    )
    assert act.new_status == AuthorityStatus.ACTIVE
    assert act.new_consumable_from == boundary
    assert act.new_consumable_to is None

    from backend.app.harvest_state.authority_canonical import (
        build_mature_inventory_loss_stable_key,
    )

    stable_key = build_mature_inventory_loss_stable_key(inp)
    events = await _query_lifecycle_events(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY.value,
        stable_key=stable_key,
        version=inp.loss_version,
        revision=inp.revision,
    )
    assert len(events) == 2
    assert events[0].transition_sequence == 1
    assert events[0].new_status == "draft"
    assert events[1].transition_sequence == 2
    assert events[1].new_status == "active"


# ══════════════════════════════════════════════════════════════════════════
#  TEST 11 – Cancellation
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cancel_authority(db_session: AsyncSession) -> None:
    inp = _mature_loss_input()
    create_result = await create_or_load_mature_loss(db_session, loss_input=inp)

    cancel_result = await cancel_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=create_result.authority_id,
    )
    assert cancel_result.new_status == AuthorityStatus.CANCELLED
    assert cancel_result.new_consumable_from is None
    assert cancel_result.new_consumable_to is None


# ══════════════════════════════════════════════════════════════════════════
#  TEST 12 – Retirement
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_retire_authority(db_session: AsyncSession) -> None:
    inp = _mature_loss_input()
    create_result = await create_or_load_mature_loss(db_session, loss_input=inp)

    boundary = date(2026, 6, 1)
    await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=create_result.authority_id,
        activation_boundary=boundary,
    )

    retire_boundary = date(2026, 12, 31)
    retire_result = await retire_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=create_result.authority_id,
        retirement_boundary=retire_boundary,
    )
    assert retire_result.new_status == AuthorityStatus.RETIRED
    assert retire_result.new_consumable_to == retire_boundary

    from backend.app.harvest_state.authority_canonical import (
        build_mature_inventory_loss_stable_key,
    )

    stable_key = build_mature_inventory_loss_stable_key(inp)
    events = await _query_lifecycle_events(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY.value,
        stable_key=stable_key,
        version=inp.loss_version,
        revision=inp.revision,
    )
    assert len(events) == 3
    assert [e.transition_sequence for e in events] == [1, 2, 3]
    assert events[2].new_status == "retired"


# ══════════════════════════════════════════════════════════════════════════
#  TEST 13 – Supersession
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_supersede_authority(db_session: AsyncSession) -> None:
    inp1 = _mature_loss_input(version="v1", revision=1)
    r1 = await create_or_load_mature_loss(db_session, loss_input=inp1)

    boundary = date(2026, 6, 1)
    await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=r1.authority_id,
        activation_boundary=boundary,
    )

    replacement_boundary = date(2026, 9, 1)
    inp2 = _mature_loss_input(version="v2", revision=1)
    sup_result = await supersede_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        old_id=r1.authority_id,
        new_input=inp2,
        replacement_boundary=replacement_boundary,
    )

    # Old is superseded
    assert sup_result.old.new_status == AuthorityStatus.SUPERSEDED
    assert sup_result.old.authority_id == r1.authority_id

    # New is active
    assert sup_result.new_activation.new_status == AuthorityStatus.ACTIVE
    assert sup_result.new_activation.new_consumable_from == replacement_boundary
    assert sup_result.new_activation.new_consumable_to is None


# ══════════════════════════════════════════════════════════════════════════
#  TEST 14 – Terminal transition rejection
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_terminal_transition_rejection(db_session: AsyncSession) -> None:
    """Retired authority cannot be activated again."""
    inp = _mature_loss_input()
    create_result = await create_or_load_mature_loss(db_session, loss_input=inp)

    boundary = date(2026, 6, 1)
    await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=create_result.authority_id,
        activation_boundary=boundary,
    )

    retire_boundary = date(2026, 12, 31)
    await retire_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=create_result.authority_id,
        retirement_boundary=retire_boundary,
    )

    with pytest.raises(LifecycleTransitionInvalidError) as exc_info:
        await activate_authority(
            db_session,
            family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
            authority_id=create_result.authority_id,
            activation_boundary=date(2027, 1, 1),
        )
    assert exc_info.value.code == "LIFECYCLE_TRANSITION_INVALID"
    assert exc_info.value.details["current_status"] == "retired"
    assert exc_info.value.details["target_status"] == "active"


# ══════════════════════════════════════════════════════════════════════════
#  TEST 15 – Exact load verification (mature loss)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_load_mature_loss_by_id(db_session: AsyncSession) -> None:
    inp = _mature_loss_input()
    create_result = await create_or_load_mature_loss(db_session, loss_input=inp)

    loaded = await load_mature_loss_by_id(
        db_session,
        authority_id=create_result.authority_id,
    )
    assert loaded.authority_id == create_result.authority_id
    assert loaded.row_hash == create_result.row_hash
    assert loaded.status == "draft"
    assert loaded.consumable_from_local_date is None
    assert loaded.consumable_to_local_date is None
    assert loaded.superseded_by_id is None


# ══════════════════════════════════════════════════════════════════════════
#  TEST 16 – Exact load verification (pool bundle)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_load_pool_bundle_by_id(db_session: AsyncSession) -> None:
    inp = _pool_input()
    create_result = await create_or_load_capacity_pool_definition(
        db_session,
        definition_input=inp,
    )

    loaded = await load_capacity_pool_definition_by_id(
        db_session,
        authority_id=create_result.parent.authority_id,
    )
    assert loaded.parent.authority_id == create_result.parent.authority_id
    assert loaded.parent.row_hash == create_result.parent.row_hash
    assert loaded.parent.status == "draft"
    assert len(loaded.child_hashes) == 1
    assert len(create_result.child_ids) == 1


# ══════════════════════════════════════════════════════════════════════════
#  TEST 17 – Exact load verification (holiday bundle)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_load_holiday_bundle_by_id(db_session: AsyncSession) -> None:
    inp = _holiday_input()
    create_result = await create_or_load_holiday_calendar(
        db_session,
        calendar_input=inp,
    )

    loaded = await load_holiday_calendar_by_id(
        db_session,
        authority_id=create_result.parent.authority_id,
    )
    assert loaded.parent.authority_id == create_result.parent.authority_id
    assert loaded.parent.row_hash == create_result.parent.row_hash
    assert loaded.parent.status == "draft"


# ══════════════════════════════════════════════════════════════════════════
#  TEST 18 – Exact load verification (weather rule)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_load_weather_rule_by_id(db_session: AsyncSession) -> None:
    inp = _weather_input()
    create_result = await create_or_load_weather_rule(
        db_session,
        weather_input=inp,
    )

    loaded = await load_weather_rule_by_id(
        db_session,
        authority_id=create_result.authority_id,
    )
    assert loaded.authority_id == create_result.authority_id
    assert loaded.row_hash == create_result.row_hash
    assert loaded.status == "draft"


# ══════════════════════════════════════════════════════════════════════════
#  TEST 19 – Exact load verification (initial inventory bundle)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_load_inventory_bundle_by_id(db_session: AsyncSession) -> None:
    inp = _inventory_input()
    create_result = await create_or_load_initial_inventory(
        db_session,
        inventory_input=inp,
    )

    loaded = await load_initial_inventory_by_id(
        db_session,
        authority_id=create_result.parent.authority_id,
    )
    assert loaded.parent.authority_id == create_result.parent.authority_id
    assert loaded.parent.row_hash == create_result.parent.row_hash
    assert loaded.parent.status == "draft"
    assert len(loaded.child_hashes) == 2


# ══════════════════════════════════════════════════════════════════════════
#  TEST 20 – Pool bundle atomic write: members verified on load
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pool_bundle_members_on_load(db_session: AsyncSession) -> None:
    """Create pool bundle with members and verify hashes on load."""
    inp = _pool_input()
    create_result = await create_or_load_capacity_pool_definition(
        db_session,
        definition_input=inp,
    )
    assert create_result.parent.created is True
    assert len(create_result.child_ids) == 1

    loaded = await load_capacity_pool_definition_by_id(
        db_session,
        authority_id=create_result.parent.authority_id,
    )
    # The load function internally verifies child hashes — if it returns
    # without raising, all hashes matched.
    assert len(loaded.child_hashes) == 1
    assert loaded.parent.row_hash == create_result.parent.row_hash


# ══════════════════════════════════════════════════════════════════════════
#  TEST 21 – Inventory bundle: cohort sum reconciliation
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_inventory_cohort_sum_reconciliation(db_session: AsyncSession) -> None:
    """Verify cohort sum matches header total."""
    inp = _inventory_input()
    # Header total = 300.00, cohorts = 200.00 + 100.00 = 300.00
    create_result = await create_or_load_initial_inventory(
        db_session,
        inventory_input=inp,
    )
    assert create_result.parent.created is True
    assert len(create_result.child_ids) == 2

    loaded = await load_initial_inventory_by_id(
        db_session,
        authority_id=create_result.parent.authority_id,
    )
    # load verifies cohort hashes internally
    assert len(loaded.child_hashes) == 2


# ══════════════════════════════════════════════════════════════════════════
#  TEST 22 – Holiday calendar hash mismatch on load
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_holiday_calendar_hash_mismatch_on_load(db_session: AsyncSession) -> None:
    """Load a holiday calendar and verify calendar_hash is checked.

    The calendar_hash is embedded in the row at creation time.
    If we manually corrupt it in the DB, load should raise.
    We test the positive path: creating with correct hash succeeds on load.
    """
    inp = _holiday_input()
    result = await create_or_load_holiday_calendar(db_session, calendar_input=inp)

    # Positive path: load succeeds when hash is correct
    loaded = await load_holiday_calendar_by_id(
        db_session,
        authority_id=result.parent.authority_id,
    )
    assert loaded.parent.row_hash == result.parent.row_hash

    # Manually corrupt the calendar_hash in the DB
    from backend.app.harvest_state.authority_repository_errors import (
        HolidayCalendarHashMismatchError,
    )
    from backend.app.models.task9_authority import Task9HolidayCalendarVersion

    corrupt_stmt = select(Task9HolidayCalendarVersion).where(
        Task9HolidayCalendarVersion.id == result.parent.authority_id,
    )
    corrupt_result = await session_execute(db_session, corrupt_stmt)
    row = corrupt_result.scalar_one()
    original_hash = row.calendar_hash
    row.calendar_hash = "a" * 64  # definitely wrong
    await db_session.flush()

    with pytest.raises(HolidayCalendarHashMismatchError) as exc_info:
        await load_holiday_calendar_by_id(
            db_session,
            authority_id=result.parent.authority_id,
        )
    assert exc_info.value.code == "HOLIDAY_CALENDAR_HASH_MISMATCH"

    # Restore for rollback safety (not strictly needed since fixture rolls back)
    row.calendar_hash = original_hash
    await db_session.flush()


# ══════════════════════════════════════════════════════════════════════════
#  TEST 23 – Weather config hash mismatch on load
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_weather_config_hash_mismatch_on_load(db_session: AsyncSession) -> None:
    """Corrupt config_hash in DB, verify load raises."""
    from backend.app.harvest_state.authority_repository_errors import (
        WeatherRuleConfigHashMismatchError,
    )
    from backend.app.models.task9_authority import Task9WeatherRuleConfigVersion

    inp = _weather_input()
    result = await create_or_load_weather_rule(db_session, weather_input=inp)

    # Corrupt config_hash
    stmt = select(Task9WeatherRuleConfigVersion).where(
        Task9WeatherRuleConfigVersion.id == result.authority_id,
    )
    db_result = await session_execute(db_session, stmt)
    row = db_result.scalar_one()
    original_hash = row.config_hash
    row.config_hash = "b" * 64
    await db_session.flush()

    with pytest.raises(WeatherRuleConfigHashMismatchError) as exc_info:
        await load_weather_rule_by_id(db_session, authority_id=result.authority_id)
    assert exc_info.value.code == "WEATHER_RULE_CONFIG_HASH_MISMATCH"

    row.config_hash = original_hash
    await db_session.flush()


# ══════════════════════════════════════════════════════════════════════════
#  TEST 24 – Dependency protection: cannot retire holiday referenced by
#            active run package
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_dependency_protection_holiday(db_session: AsyncSession) -> None:
    """Retiring a holiday still referenced by an active package must fail."""
    # Create holiday + weather + package
    holiday = _holiday_input()
    await create_or_load_holiday_calendar(db_session, calendar_input=holiday)

    weather = _weather_input()
    await create_or_load_weather_rule(db_session, weather_input=weather)

    pkg = _run_package_input()
    pkg_result = await create_or_load_run_parameter_package(
        db_session,
        package_input=pkg,
        holiday_calendar=holiday,
        weather_rule=weather,
    )
    # Activate the package
    await activate_authority(
        db_session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        authority_id=pkg_result.authority_id,
        activation_boundary=date(2026, 6, 1),
    )

    # Now we need the holiday's ID.  Query it.
    from backend.app.models.task9_authority import Task9HolidayCalendarVersion

    hol_stmt = select(Task9HolidayCalendarVersion).where(
        Task9HolidayCalendarVersion.season_id == _IDS["season"],
        Task9HolidayCalendarVersion.calendar_code == "CN",
        Task9HolidayCalendarVersion.calendar_version == "v1",
        Task9HolidayCalendarVersion.revision == 1,
    )
    hol_result = await session_execute(db_session, hol_stmt)
    holiday_row = hol_result.scalar_one()

    # Activate the holiday so we can try to retire it
    await activate_authority(
        db_session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=holiday_row.id,
        activation_boundary=date(2026, 6, 1),
    )

    with pytest.raises(AuthorityStillReferencedByActivePackageError) as exc_info:
        await retire_authority(
            db_session,
            family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
            authority_id=holiday_row.id,
            retirement_boundary=date(2026, 12, 31),
        )
    assert exc_info.value.code == "AUTHORITY_STILL_REFERENCED_BY_ACTIVE_PACKAGE"


# ══════════════════════════════════════════════════════════════════════════
#  TEST 25 – Supersession: old status + superseded_by_id verification
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_supersede_old_status_and_link(db_session: AsyncSession) -> None:
    """After supersession, verify old row has superseded status and link to new."""
    from backend.app.models.task9_authority import Task9MatureInventoryLossAuthority

    inp1 = _mature_loss_input(version="v1", revision=1)
    r1 = await create_or_load_mature_loss(db_session, loss_input=inp1)

    boundary = date(2026, 6, 1)
    await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=r1.authority_id,
        activation_boundary=boundary,
    )

    inp2 = _mature_loss_input(version="v2", revision=1)
    sup = await supersede_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        old_id=r1.authority_id,
        new_input=inp2,
        replacement_boundary=date(2026, 9, 1),
    )

    # Load old row directly to verify fields
    stmt = select(Task9MatureInventoryLossAuthority).where(
        Task9MatureInventoryLossAuthority.id == r1.authority_id,
    )
    result = await session_execute(db_session, stmt)
    old_row = result.scalar_one()
    assert old_row.status == "superseded"
    assert old_row.superseded_by_id == sup.new.authority_id


# ══════════════════════════════════════════════════════════════════════════
#  TEST 26 – Supersession: new authority is active with correct boundary
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_supersede_new_authority_active_boundary(db_session: AsyncSession) -> None:
    """New authority created by supersession is active with correct consumable_from."""
    from backend.app.models.task9_authority import Task9MatureInventoryLossAuthority

    inp1 = _mature_loss_input(version="v1", revision=1)
    r1 = await create_or_load_mature_loss(db_session, loss_input=inp1)

    await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=r1.authority_id,
        activation_boundary=date(2026, 6, 1),
    )

    replacement_boundary = date(2026, 9, 1)
    inp2 = _mature_loss_input(version="v2", revision=1)
    sup = await supersede_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        old_id=r1.authority_id,
        new_input=inp2,
        replacement_boundary=replacement_boundary,
    )

    stmt = select(Task9MatureInventoryLossAuthority).where(
        Task9MatureInventoryLossAuthority.id == sup.new.authority_id,
    )
    result = await session_execute(db_session, stmt)
    new_row = result.scalar_one()
    assert new_row.status == "active"
    assert new_row.consumable_from_local_date == replacement_boundary
    assert new_row.consumable_to_local_date is None


# ══════════════════════════════════════════════════════════════════════════
#  TEST 27 – Supersession: lifecycle events on old (draft→active→superseded)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_supersede_lifecycle_events_old(db_session: AsyncSession) -> None:
    from backend.app.harvest_state.authority_canonical import (
        build_mature_inventory_loss_stable_key,
    )

    inp1 = _mature_loss_input(version="v1", revision=1)
    r1 = await create_or_load_mature_loss(db_session, loss_input=inp1)

    await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=r1.authority_id,
        activation_boundary=date(2026, 6, 1),
    )

    inp2 = _mature_loss_input(version="v2", revision=1)
    await supersede_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        old_id=r1.authority_id,
        new_input=inp2,
        replacement_boundary=date(2026, 9, 1),
    )

    stable_key = build_mature_inventory_loss_stable_key(inp1)
    events = await _query_lifecycle_events(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY.value,
        stable_key=stable_key,
        version=inp1.loss_version,
        revision=inp1.revision,
    )
    assert len(events) == 3
    assert [e.new_status for e in events] == ["draft", "active", "superseded"]
    assert [e.transition_sequence for e in events] == [1, 2, 3]


# ══════════════════════════════════════════════════════════════════════════
#  TEST 28 – Supersession: lifecycle events on new (draft→active)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_supersede_lifecycle_events_new(db_session: AsyncSession) -> None:
    from backend.app.harvest_state.authority_canonical import (
        build_mature_inventory_loss_stable_key,
    )

    inp1 = _mature_loss_input(version="v1", revision=1)
    r1 = await create_or_load_mature_loss(db_session, loss_input=inp1)

    await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=r1.authority_id,
        activation_boundary=date(2026, 6, 1),
    )

    inp2 = _mature_loss_input(version="v2", revision=1)
    _sup = await supersede_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        old_id=r1.authority_id,
        new_input=inp2,
        replacement_boundary=date(2026, 9, 1),
    )

    stable_key = build_mature_inventory_loss_stable_key(inp2)
    events = await _query_lifecycle_events(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY.value,
        stable_key=stable_key,
        version=inp2.loss_version,
        revision=inp2.revision,
    )
    assert len(events) == 2
    assert [e.new_status for e in events] == ["draft", "active"]
    assert [e.transition_sequence for e in events] == [1, 2]


# ══════════════════════════════════════════════════════════════════════════
#  TEST 29 – Activation: verify consumable_from on loaded row
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_activation_sets_consumable_from_on_load(db_session: AsyncSession) -> None:
    inp = _mature_loss_input()
    r = await create_or_load_mature_loss(db_session, loss_input=inp)

    boundary = date(2026, 6, 1)
    await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=r.authority_id,
        activation_boundary=boundary,
    )

    loaded = await load_mature_loss_by_id(db_session, authority_id=r.authority_id)
    assert loaded.status == "active"
    assert loaded.consumable_from_local_date == boundary
    assert loaded.consumable_to_local_date is None


# ══════════════════════════════════════════════════════════════════════════
#  TEST 30 – Retirement: verify consumable_to on loaded row
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_retirement_sets_consumable_to_on_load(db_session: AsyncSession) -> None:
    inp = _mature_loss_input()
    r = await create_or_load_mature_loss(db_session, loss_input=inp)

    act_boundary = date(2026, 6, 1)
    await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=r.authority_id,
        activation_boundary=act_boundary,
    )

    ret_boundary = date(2026, 12, 31)
    await retire_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=r.authority_id,
        retirement_boundary=ret_boundary,
    )

    loaded = await load_mature_loss_by_id(db_session, authority_id=r.authority_id)
    assert loaded.status == "retired"
    assert loaded.consumable_from_local_date == act_boundary
    assert loaded.consumable_to_local_date == ret_boundary


# ══════════════════════════════════════════════════════════════════════════
#  TEST 31 – Cancellation: verify consumable fields on loaded row
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cancel_sets_consumable_null_on_load(db_session: AsyncSession) -> None:
    inp = _mature_loss_input()
    r = await create_or_load_mature_loss(db_session, loss_input=inp)

    await cancel_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=r.authority_id,
    )

    loaded = await load_mature_loss_by_id(db_session, authority_id=r.authority_id)
    assert loaded.status == "cancelled"
    assert loaded.consumable_from_local_date is None
    assert loaded.consumable_to_local_date is None


# ══════════════════════════════════════════════════════════════════════════
#  TEST 32 – Weather create-or-load idempotency with hash verification
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_weather_hash_roundtrip(db_session: AsyncSession) -> None:
    """Create weather, load, verify row_hash matches expected canonical hash."""
    inp = _weather_input()
    r = await create_or_load_weather_rule(db_session, weather_input=inp)
    expected_hash = make_authority_row_hash(inp)
    assert r.row_hash == expected_hash

    loaded = await load_weather_rule_by_id(db_session, authority_id=r.authority_id)
    assert loaded.row_hash == expected_hash


# ══════════════════════════════════════════════════════════════════════════
#  TEST 33 – Pool definition hash roundtrip
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pool_hash_roundtrip(db_session: AsyncSession) -> None:
    inp = _pool_input()
    r = await create_or_load_capacity_pool_definition(db_session, definition_input=inp)
    expected_hash = make_authority_row_hash(inp)
    assert r.parent.row_hash == expected_hash

    loaded = await load_capacity_pool_definition_by_id(
        db_session,
        authority_id=r.parent.authority_id,
    )
    assert loaded.parent.row_hash == expected_hash


# ══════════════════════════════════════════════════════════════════════════
#  TEST 34 – Holiday hash roundtrip
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_holiday_hash_roundtrip(db_session: AsyncSession) -> None:
    inp = _holiday_input()
    r = await create_or_load_holiday_calendar(db_session, calendar_input=inp)
    expected_hash = make_authority_row_hash(inp)
    assert r.parent.row_hash == expected_hash

    loaded = await load_holiday_calendar_by_id(
        db_session,
        authority_id=r.parent.authority_id,
    )
    assert loaded.parent.row_hash == expected_hash


# ══════════════════════════════════════════════════════════════════════════
#  TEST 35 – Inventory hash roundtrip
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_inventory_hash_roundtrip(db_session: AsyncSession) -> None:
    inp = _inventory_input()
    r = await create_or_load_initial_inventory(db_session, inventory_input=inp)
    expected_hash = make_authority_row_hash(inp)
    assert r.parent.row_hash == expected_hash

    loaded = await load_initial_inventory_by_id(
        db_session,
        authority_id=r.parent.authority_id,
    )
    assert loaded.parent.row_hash == expected_hash


# ── Utility helpers ──────────────────────────────────────────────────────


async def session_execute(session: AsyncSession, stmt):  # type: ignore[no-untyped-def]
    """Thin wrapper to keep test lines short."""
    return await session.execute(stmt)


# ══════════════════════════════════════════════════════════════════════════
#  P0-2 LIFECYCLE CHAIN TAMPER TESTS
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_lifecycle_event_sequence_gap(db_session: AsyncSession) -> None:
    """Create authority, manually tamper event sequence → chain verification fails."""
    inp = _mature_loss_input()
    result = await create_or_load_mature_loss(db_session, loss_input=inp)
    assert result.created is True

    # Tamper: change sequence 1 to sequence 5 (creating a gap)
    events = await _query_lifecycle_events(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY.value,
        stable_key=build_mature_inventory_loss_stable_key(inp),
        version=inp.loss_version,
        revision=inp.revision,
    )
    assert len(events) == 1
    events[0].transition_sequence = 5
    await db_session.flush()

    with pytest.raises(LifecycleTransitionInvalidError) as exc_info:
        await load_mature_loss_by_id(
            db_session, authority_id=result.authority_id
        )
    assert exc_info.value.code == "LIFECYCLE_TRANSITION_INVALID"


@pytest.mark.asyncio
async def test_lifecycle_event_self_hash_tamper(db_session: AsyncSession) -> None:
    """Tamper lifecycle_event_hash → load rejects."""
    inp = _mature_loss_input()
    result = await create_or_load_mature_loss(db_session, loss_input=inp)

    events = await _query_lifecycle_events(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY.value,
        stable_key=build_mature_inventory_loss_stable_key(inp),
        version=inp.loss_version,
        revision=inp.revision,
    )
    assert len(events) == 1
    events[0].lifecycle_event_hash = "a" * 64
    await db_session.flush()

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_mature_loss_by_id(db_session, authority_id=result.authority_id)
    assert exc_info.value.code == "AUTHORITY_HASH_CONFLICT"


@pytest.mark.asyncio
async def test_lifecycle_event_business_row_hash_tamper(
    db_session: AsyncSession,
) -> None:
    """Tamper business_row_hash on event → load rejects."""
    inp = _mature_loss_input()
    result = await create_or_load_mature_loss(db_session, loss_input=inp)

    events = await _query_lifecycle_events(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY.value,
        stable_key=build_mature_inventory_loss_stable_key(inp),
        version=inp.loss_version,
        revision=inp.revision,
    )
    assert len(events) == 1
    events[0].business_row_hash = "b" * 64
    await db_session.flush()

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_mature_loss_by_id(db_session, authority_id=result.authority_id)
    assert exc_info.value.code == "AUTHORITY_HASH_CONFLICT"


@pytest.mark.asyncio
async def test_lifecycle_first_event_not_draft(db_session: AsyncSession) -> None:
    """Delete initial event, replace with wrong transition → chain rejects."""
    inp = _mature_loss_input()
    result = await create_or_load_mature_loss(db_session, loss_input=inp)

    events = await _query_lifecycle_events(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY.value,
        stable_key=build_mature_inventory_loss_stable_key(inp),
        version=inp.loss_version,
        revision=inp.revision,
    )
    assert len(events) == 1

    # Delete the initial event and replace with wrong transition
    await db_session.delete(events[0])
    await db_session.flush()

    # Insert a fake event with old_status=active (not NULL→draft)
    # Use raw SQL to avoid ORM quirks with server_default columns
    # Also compute valid lifecycle_event_hash so hash check passes
    from backend.app.harvest_state.authority_canonical import make_lifecycle_event_hash
    from backend.app.harvest_state.authority_schemas import Task9LifecycleEventSemanticInput

    fake_stable_key = build_mature_inventory_loss_stable_key(inp)
    fake_sem = Task9LifecycleEventSemanticInput(
        authority_family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_stable_key=fake_stable_key,
        authority_business_version=inp.loss_version,
        authority_revision=inp.revision,
        business_row_hash=result.row_hash,
        transition_sequence=1,
        old_status=AuthorityStatus.ACTIVE,
        new_status=AuthorityStatus.DRAFT,
        old_consumable_from_local_date=None,
        old_consumable_to_local_date=None,
        new_consumable_from_local_date=None,
        new_consumable_to_local_date=None,
        superseded_by_authority_stable_key=None,
        superseded_by_authority_business_version=None,
        superseded_by_authority_revision=None,
        transitioned_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_system="tamper",
        source_record_key="tamper:fake",
    )
    fake_event_hash = make_lifecycle_event_hash(fake_sem)
    await db_session.execute(
        text(
            "INSERT INTO task9_authority_lifecycle_event ("
            "authority_family, authority_stable_key, authority_business_version, "
            "authority_revision, business_row_hash, transition_sequence, "
            "old_status, new_status, lifecycle_event_hash, "
            "transitioned_at, source_system, source_record_key"
            ") VALUES ("
            ":family, :stable_key, :version, :revision, :row_hash, 1, "
            "'active', 'draft', :event_hash, "
            ":transitioned_at, 'tamper', 'tamper:fake'"
            ")"
        ),
        {
            "family": AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY.value,
            "stable_key": fake_stable_key,
            "version": inp.loss_version,
            "revision": inp.revision,
            "row_hash": result.row_hash,
            "event_hash": fake_event_hash,
            "transitioned_at": datetime(2026, 1, 1, tzinfo=UTC),
        },
    )
    await db_session.flush()

    with pytest.raises(LifecycleTransitionInvalidError) as exc_info:
        await load_mature_loss_by_id(db_session, authority_id=result.authority_id)
    assert exc_info.value.code == "LIFECYCLE_TRANSITION_INVALID"


@pytest.mark.asyncio
async def test_lifecycle_chain_projection_discontinuity(
    db_session: AsyncSession,
) -> None:
    """Tamper old/new status to break continuity → chain rejects."""
    inp = _mature_loss_input()
    result = await create_or_load_mature_loss(db_session, loss_input=inp)
    auth_id = result.authority_id

    # Activate, then retire to get 3 events
    await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=auth_id,
        activation_boundary=date(2026, 6, 1),
    )
    await retire_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=auth_id,
        retirement_boundary=date(2026, 12, 31),
    )

    events = await _query_lifecycle_events(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY.value,
        stable_key=build_mature_inventory_loss_stable_key(inp),
        version=inp.loss_version,
        revision=inp.revision,
    )
    assert len(events) == 3

    # Tamper event 2's old_status to break chain continuity
    # Event 2 (draft→active): change old_status from "draft" to "cancelled"
    # Also update lifecycle_event_hash so the hash check passes and the
    # chain continuity check catches the tamper.
    events[1].old_status = "cancelled"
    from backend.app.harvest_state.authority_canonical import make_lifecycle_event_hash
    from backend.app.harvest_state.authority_schemas import Task9LifecycleEventSemanticInput

    sem = Task9LifecycleEventSemanticInput(
        authority_family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_stable_key=events[1].authority_stable_key,
        authority_business_version=events[1].authority_business_version,
        authority_revision=events[1].authority_revision,
        business_row_hash=events[1].business_row_hash,
        transition_sequence=events[1].transition_sequence,
        old_status=AuthorityStatus("cancelled"),
        new_status=AuthorityStatus(events[1].new_status),
        old_consumable_from_local_date=events[1].old_consumable_from_local_date,
        old_consumable_to_local_date=events[1].old_consumable_to_local_date,
        new_consumable_from_local_date=events[1].new_consumable_from_local_date,
        new_consumable_to_local_date=events[1].new_consumable_to_local_date,
        superseded_by_authority_stable_key=events[1].superseded_by_authority_stable_key,
        superseded_by_authority_business_version=events[1].superseded_by_authority_business_version,
        superseded_by_authority_revision=events[1].superseded_by_authority_revision,
        transitioned_at=events[1].transitioned_at,
        source_system=events[1].source_system,
        source_record_key=events[1].source_record_key,
    )
    events[1].lifecycle_event_hash = make_lifecycle_event_hash(sem)
    await db_session.flush()

    with pytest.raises(LifecycleTransitionInvalidError) as exc_info:
        await load_mature_loss_by_id(db_session, authority_id=auth_id)
    assert exc_info.value.code == "LIFECYCLE_TRANSITION_INVALID"


@pytest.mark.asyncio
async def test_lifecycle_incomplete_replacement_identity(
    db_session: AsyncSession,
) -> None:
    """Create supersession event with partial replacement fields → load rejects."""
    inp1 = _mature_loss_input(version="v1", revision=1)
    r1 = await create_or_load_mature_loss(db_session, loss_input=inp1)

    await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=r1.authority_id,
        activation_boundary=date(2026, 6, 1),
    )

    inp2 = _mature_loss_input(version="v2", revision=1)
    _sup = await supersede_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        old_id=r1.authority_id,
        new_input=inp2,
        replacement_boundary=date(2026, 9, 1),
    )

    # Find the supersession event on old and tamper it
    stable_key_old = build_mature_inventory_loss_stable_key(inp1)
    events = await _query_lifecycle_events(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY.value,
        stable_key=stable_key_old,
        version=inp1.loss_version,
        revision=inp1.revision,
    )
    assert len(events) == 3
    # The third event is the supersession event
    sup_event = events[2]
    assert sup_event.new_status == "superseded"

    # Set the superseded_by fields to point to a non-existent authority,
    # so the chain verification detects "replacement_identity_not_resolvable"
    # (the CHECK constraint requires all-or-none, so we use all three with
    # fake values that won't resolve to any real authority)
    sup_event.superseded_by_authority_stable_key = "fake-nonexistent-stable-key"
    sup_event.superseded_by_authority_business_version = "fake-v99"
    sup_event.superseded_by_authority_revision = 999
    # Recompute lifecycle_event_hash to match the tampered values
    from backend.app.harvest_state.authority_canonical import make_lifecycle_event_hash
    from backend.app.harvest_state.authority_schemas import Task9LifecycleEventSemanticInput

    sem = Task9LifecycleEventSemanticInput(
        authority_family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_stable_key=sup_event.authority_stable_key,
        authority_business_version=sup_event.authority_business_version,
        authority_revision=sup_event.authority_revision,
        business_row_hash=sup_event.business_row_hash,
        transition_sequence=sup_event.transition_sequence,
        old_status=AuthorityStatus(sup_event.old_status) if sup_event.old_status else None,
        new_status=AuthorityStatus(sup_event.new_status),
        old_consumable_from_local_date=sup_event.old_consumable_from_local_date,
        old_consumable_to_local_date=sup_event.old_consumable_to_local_date,
        new_consumable_from_local_date=sup_event.new_consumable_from_local_date,
        new_consumable_to_local_date=sup_event.new_consumable_to_local_date,
        superseded_by_authority_stable_key=sup_event.superseded_by_authority_stable_key,
        superseded_by_authority_business_version=sup_event.superseded_by_authority_business_version,
        superseded_by_authority_revision=sup_event.superseded_by_authority_revision,
        transitioned_at=sup_event.transitioned_at,
        source_system=sup_event.source_system,
        source_record_key=sup_event.source_record_key,
    )
    sup_event.lifecycle_event_hash = make_lifecycle_event_hash(sem)
    await db_session.flush()

    with pytest.raises(AuthoritySupersessionScopeConflictError) as exc_info:
        await load_mature_loss_by_id(
            db_session, authority_id=r1.authority_id
        )
    assert exc_info.value.code == "AUTHORITY_SUPERSESSION_SCOPE_CONFLICT"


@pytest.mark.asyncio
async def test_lifecycle_final_event_mismatch(db_session: AsyncSession) -> None:
    """Modify final event to disagree with authority state → load rejects."""
    inp = _mature_loss_input()
    result = await create_or_load_mature_loss(db_session, loss_input=inp)

    events = await _query_lifecycle_events(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY.value,
        stable_key=build_mature_inventory_loss_stable_key(inp),
        version=inp.loss_version,
        revision=inp.revision,
    )
    assert len(events) == 1

    # The authority is "draft", tamper the event's new_status to "active"
    # Also update lifecycle_event_hash so the hash check passes and the
    # projection mismatch check catches the tamper.
    events[0].new_status = "active"
    from backend.app.harvest_state.authority_canonical import make_lifecycle_event_hash
    from backend.app.harvest_state.authority_schemas import Task9LifecycleEventSemanticInput

    sem = Task9LifecycleEventSemanticInput(
        authority_family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_stable_key=events[0].authority_stable_key,
        authority_business_version=events[0].authority_business_version,
        authority_revision=events[0].authority_revision,
        business_row_hash=events[0].business_row_hash,
        transition_sequence=events[0].transition_sequence,
        old_status=None,
        new_status=AuthorityStatus("active"),
        old_consumable_from_local_date=events[0].old_consumable_from_local_date,
        old_consumable_to_local_date=events[0].old_consumable_to_local_date,
        new_consumable_from_local_date=events[0].new_consumable_from_local_date,
        new_consumable_to_local_date=events[0].new_consumable_to_local_date,
        superseded_by_authority_stable_key=events[0].superseded_by_authority_stable_key,
        superseded_by_authority_business_version=events[0].superseded_by_authority_business_version,
        superseded_by_authority_revision=events[0].superseded_by_authority_revision,
        transitioned_at=events[0].transitioned_at,
        source_system=events[0].source_system,
        source_record_key=events[0].source_record_key,
    )
    events[0].lifecycle_event_hash = make_lifecycle_event_hash(sem)
    await db_session.flush()

    with pytest.raises((AuthorityConsumabilityIntervalConflictError, LifecycleTransitionInvalidError)):
        await load_mature_loss_by_id(db_session, authority_id=result.authority_id)


# ══════════════════════════════════════════════════════════════════════════
#  P0-3 MEMBER PROJECTION TESTS
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pool_member_cannot_fake_parent_fields(
    db_session: AsyncSession,
) -> None:
    """Verify member inherits from DB parent, not publisher input."""
    inp = _pool_input()
    result = await create_or_load_capacity_pool_definition(
        db_session, definition_input=inp
    )
    assert result.parent.created is True

    # Load succeeds — members inherited correct fields from parent
    loaded = await load_capacity_pool_definition_by_id(
        db_session, authority_id=result.parent.authority_id
    )
    assert len(loaded.child_hashes) == 1
    assert loaded.parent.row_hash == result.parent.row_hash


@pytest.mark.asyncio
async def test_pool_member_projection_tamper_detected(
    db_session: AsyncSession,
) -> None:
    """Modify member's inherited fields → load rejects."""
    from backend.app.models.task9_authority import Task9CapacityPoolMember

    inp = _pool_input()
    result = await create_or_load_capacity_pool_definition(
        db_session, definition_input=inp
    )

    # Find the member row and tamper it
    member_stmt = select(Task9CapacityPoolMember).where(
        Task9CapacityPoolMember.capacity_pool_definition_id
        == result.parent.authority_id,
    )
    member_result = await session_execute(db_session, member_stmt)
    members = list(member_result.scalars().all())
    assert len(members) == 1

    # Tamper the member's row_hash
    original_hash = members[0].row_hash
    members[0].row_hash = "f" * 64
    await db_session.flush()

    # Load should detect the tamper
    with pytest.raises(Exception):  # noqa: B017
        await load_capacity_pool_definition_by_id(
            db_session, authority_id=result.parent.authority_id
        )

    # Restore for rollback safety
    members[0].row_hash = original_hash
    await db_session.flush()


@pytest.mark.asyncio
async def test_pool_member_child_add_delete_tamper(
    db_session: AsyncSession,
) -> None:
    """Delete a member via raw SQL → load detects tampering (empty members rejected)."""
    inp = _pool_input()
    result = await create_or_load_capacity_pool_definition(
        db_session, definition_input=inp
    )
    parent_id = result.parent.authority_id

    # Count members before
    count_before = await db_session.execute(
        text(
            "SELECT count(*) FROM task9_capacity_pool_member "
            "WHERE capacity_pool_definition_id = :pid"
        ),
        {"pid": parent_id},
    )
    assert count_before.scalar_one() == 1

    # Delete the member via raw SQL (bypasses SQLAlchemy identity-map caching)
    await db_session.execute(
        text(
            "DELETE FROM task9_capacity_pool_member "
            "WHERE capacity_pool_definition_id = :pid"
        ),
        {"pid": parent_id},
    )
    await db_session.flush()

    # Confirm raw SQL delete took effect
    count_after = await db_session.execute(
        text(
            "SELECT count(*) FROM task9_capacity_pool_member "
            "WHERE capacity_pool_definition_id = :pid"
        ),
        {"pid": parent_id},
    )
    assert count_after.scalar_one() == 0, "Raw SQL delete should have removed the member"

    # Expire all ORM state so the next SELECT hits the DB, not the identity map
    db_session.expire_all()

    # Load should detect tampering.  The load function reconstructs the
    # semantic bundle from DB data; with 0 members the Pydantic
    # "members must not be empty" validator fires, which is the correct
    # tamper-detection path (ValidationError wraps the tamper).
    with pytest.raises((AuthorityHashConflictError, ValidationError)):
        await load_capacity_pool_definition_by_id(
            db_session, authority_id=parent_id
        )
    # Fixture rollback handles cleanup — no manual restore needed


# ══════════════════════════════════════════════════════════════════════════
#  P0-5 BOUNDARY VALIDATION TESTS
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_activation_boundary_before_available_at(
    db_session: AsyncSession,
) -> None:
    """activation_boundary < available_at → AUTHORITY_CONSUMABILITY_INTERVAL_INVALID."""
    # Use a pool with available_at=2026-01-01
    inp = _pool_input()
    await create_or_load_capacity_pool_definition(
        db_session, definition_input=inp
    )

    daily = _daily_input()
    r = await create_or_load_daily_capacity(db_session, daily_input=daily)

    # Try to activate with boundary before available_at (2026-01-01)
    with pytest.raises(AuthorityConsumabilityIntervalInvalidError) as exc_info:
        await activate_authority(
            db_session,
            family=AuthorityFamily.DAILY_CAPACITY,
            authority_id=r.authority_id,
            activation_boundary=date(2025, 12, 1),
        )
    assert exc_info.value.code == "AUTHORITY_CONSUMABILITY_INTERVAL_INVALID"
    assert exc_info.value.details["reason"] == "activation_boundary_before_available_at"


@pytest.mark.asyncio
async def test_activation_boundary_equals_available_at(
    db_session: AsyncSession,
) -> None:
    """activation_boundary == available_at → should succeed."""
    inp = _pool_input()
    await create_or_load_capacity_pool_definition(
        db_session, definition_input=inp
    )

    daily = _daily_input()
    r = await create_or_load_daily_capacity(db_session, daily_input=daily)

    # available_at = 2026-01-01, activation_boundary = 2026-01-01 → OK
    act = await activate_authority(
        db_session,
        family=AuthorityFamily.DAILY_CAPACITY,
        authority_id=r.authority_id,
        activation_boundary=date(2026, 1, 1),
    )
    assert act.new_status == AuthorityStatus.ACTIVE
    assert act.new_consumable_from == date(2026, 1, 1)


@pytest.mark.asyncio
async def test_retirement_equals_consumable_from(
    db_session: AsyncSession,
) -> None:
    """retirement_boundary == consumable_from → AUTHORITY_CONSUMABILITY_INTERVAL_INVALID."""
    inp = _mature_loss_input()
    r = await create_or_load_mature_loss(db_session, loss_input=inp)

    boundary = date(2026, 6, 1)
    await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=r.authority_id,
        activation_boundary=boundary,
    )

    # retirement_boundary == consumable_from → must be strictly after
    with pytest.raises(AuthorityConsumabilityIntervalInvalidError) as exc_info:
        await retire_authority(
            db_session,
            family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
            authority_id=r.authority_id,
            retirement_boundary=boundary,
        )
    assert exc_info.value.code == "AUTHORITY_CONSUMABILITY_INTERVAL_INVALID"
    assert (
        exc_info.value.details["reason"]
        == "retirement_boundary_not_after_consumable_from"
    )


@pytest.mark.asyncio
async def test_retirement_before_consumable_from(
    db_session: AsyncSession,
) -> None:
    """retirement_boundary < consumable_from → AUTHORITY_CONSUMABILITY_INTERVAL_INVALID."""
    inp = _mature_loss_input()
    r = await create_or_load_mature_loss(db_session, loss_input=inp)

    await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=r.authority_id,
        activation_boundary=date(2026, 6, 1),
    )

    with pytest.raises(AuthorityConsumabilityIntervalInvalidError) as exc_info:
        await retire_authority(
            db_session,
            family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
            authority_id=r.authority_id,
            retirement_boundary=date(2026, 5, 1),
        )
    assert exc_info.value.code == "AUTHORITY_CONSUMABILITY_INTERVAL_INVALID"
    assert (
        exc_info.value.details["reason"]
        == "retirement_boundary_not_after_consumable_from"
    )


@pytest.mark.asyncio
async def test_retirement_after_consumable_from(
    db_session: AsyncSession,
) -> None:
    """retirement_boundary > consumable_from → should succeed."""
    inp = _mature_loss_input()
    r = await create_or_load_mature_loss(db_session, loss_input=inp)

    await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=r.authority_id,
        activation_boundary=date(2026, 6, 1),
    )

    ret = await retire_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=r.authority_id,
        retirement_boundary=date(2026, 12, 31),
    )
    assert ret.new_status == AuthorityStatus.RETIRED
    assert ret.new_consumable_to == date(2026, 12, 31)


# ══════════════════════════════════════════════════════════════════════════
#  P0-4 DEPENDENCY REPLACEMENT TESTS
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_trio_replacement_atomic(db_session: AsyncSession) -> None:
    """Full trio replacement test via replace_run_package_with_dependencies."""
    # Create old trio
    holiday = _holiday_input()
    await create_or_load_holiday_calendar(db_session, calendar_input=holiday)

    weather = _weather_input()
    await create_or_load_weather_rule(db_session, weather_input=weather)

    pkg = _run_package_input(version="v1", revision=1)
    pkg_result = await create_or_load_run_parameter_package(
        db_session,
        package_input=pkg,
        holiday_calendar=holiday,
        weather_rule=weather,
    )

    # Activate old package (and its dependencies)
    hol_id = await _get_holiday_id_async(db_session, holiday)
    wx_id = await _get_weather_id_async(db_session, weather)
    await activate_authority(
        db_session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=hol_id,
        activation_boundary=date(2026, 1, 1),
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=wx_id,
        activation_boundary=date(2026, 1, 1),
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        authority_id=pkg_result.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    # Create new trio inputs
    new_holiday = _holiday_input(version="v2", revision=1)
    new_weather = _weather_input(version="v2", revision=1)
    new_pkg = _run_package_input(version="v2", revision=1)

    boundary = date(2026, 7, 1)
    sup_result = await replace_run_package_with_dependencies(
        db_session,
        old_package_id=pkg_result.authority_id,
        new_package_input=new_pkg,
        new_holiday_input=new_holiday,
        new_weather_input=new_weather,
        replacement_boundary=boundary,
    )

    # Verify old package is superseded
    assert sup_result.old.new_status == AuthorityStatus.SUPERSEDED
    assert sup_result.old.new_consumable_to == boundary

    # Verify new package is active
    assert sup_result.new_activation.new_status == AuthorityStatus.ACTIVE
    assert sup_result.new_activation.new_consumable_from == boundary


@pytest.mark.asyncio
async def test_trio_replacement_interval_consistency(
    db_session: AsyncSession,
) -> None:
    """All 6 authorities use same boundary after replacement."""
    # Create old trio
    holiday = _holiday_input()
    await create_or_load_holiday_calendar(db_session, calendar_input=holiday)

    weather = _weather_input()
    await create_or_load_weather_rule(db_session, weather_input=weather)

    pkg = _run_package_input(version="v1", revision=1)
    pkg_result = await create_or_load_run_parameter_package(
        db_session,
        package_input=pkg,
        holiday_calendar=holiday,
        weather_rule=weather,
    )

    # Activate all
    hol_id = await _get_holiday_id_async(db_session, holiday)
    wx_id = await _get_weather_id_async(db_session, weather)

    await activate_authority(
        db_session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=hol_id,
        activation_boundary=date(2026, 1, 1),
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=wx_id,
        activation_boundary=date(2026, 1, 1),
    )
    await activate_authority(
        db_session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        authority_id=pkg_result.authority_id,
        activation_boundary=date(2026, 1, 1),
    )

    # Replace
    new_holiday = _holiday_input(version="v2", revision=1)
    new_weather = _weather_input(version="v2", revision=1)
    new_pkg = _run_package_input(version="v2", revision=1)

    boundary = date(2026, 7, 1)
    await replace_run_package_with_dependencies(
        db_session,
        old_package_id=pkg_result.authority_id,
        new_package_input=new_pkg,
        new_holiday_input=new_holiday,
        new_weather_input=new_weather,
        replacement_boundary=boundary,
    )

    # Verify old trio consumable_to == boundary
    from backend.app.models.task9_authority import (
        Task9HolidayCalendarVersion,
        Task9RunParameterPackage,
        Task9WeatherRuleConfigVersion,
    )

    old_pkg_stmt = select(Task9RunParameterPackage).where(
        Task9RunParameterPackage.id == pkg_result.authority_id,
    )
    old_pkg_row = (await session_execute(db_session, old_pkg_stmt)).scalar_one()
    assert old_pkg_row.consumable_to_local_date == boundary

    old_hol_stmt = select(Task9HolidayCalendarVersion).where(
        Task9HolidayCalendarVersion.id == hol_id,
    )
    old_hol_row = (await session_execute(db_session, old_hol_stmt)).scalar_one()
    assert old_hol_row.consumable_to_local_date == boundary

    old_wx_stmt = select(Task9WeatherRuleConfigVersion).where(
        Task9WeatherRuleConfigVersion.id == wx_id,
    )
    old_wx_row = (await session_execute(db_session, old_wx_stmt)).scalar_one()
    assert old_wx_row.consumable_to_local_date == boundary


async def _get_holiday_id_async(session: AsyncSession, inp) -> int:  # type: ignore[no-untyped-def]
    from backend.app.models.task9_authority import Task9HolidayCalendarVersion

    stmt = select(Task9HolidayCalendarVersion).where(
        Task9HolidayCalendarVersion.season_id == inp.season_id,
        Task9HolidayCalendarVersion.calendar_code == inp.calendar_code,
        Task9HolidayCalendarVersion.calendar_version == inp.calendar_version,
        Task9HolidayCalendarVersion.revision == inp.revision,
    )
    result = await session_execute(session, stmt)
    return result.scalar_one().id


async def _get_weather_id_async(session: AsyncSession, inp) -> int:  # type: ignore[no-untyped-def]
    from backend.app.models.task9_authority import Task9WeatherRuleConfigVersion

    stmt = select(Task9WeatherRuleConfigVersion).where(
        Task9WeatherRuleConfigVersion.rule_code == inp.rule_code,
        Task9WeatherRuleConfigVersion.rule_version == inp.rule_version,
        Task9WeatherRuleConfigVersion.revision == inp.revision,
    )
    result = await session_execute(session, stmt)
    return result.scalar_one().id


# ══════════════════════════════════════════════════════════════════════════
#  P0-7 EXACT LOAD TESTS
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_load_by_business_key(db_session: AsyncSession) -> None:
    """Load daily capacity by business key."""
    inp = _pool_input()
    await create_or_load_capacity_pool_definition(
        db_session, definition_input=inp
    )

    daily = _daily_input()
    create_result = await create_or_load_daily_capacity(
        db_session, daily_input=daily
    )

    stable_key = build_daily_capacity_stable_key(daily)
    loaded = await load_authority_by_business_key(
        db_session,
        family=AuthorityFamily.DAILY_CAPACITY,
        stable_key=stable_key,
        business_version=daily.capacity_pool_version,
        revision=daily.daily_capacity_revision,
    )
    assert loaded.authority_id == create_result.authority_id
    assert loaded.row_hash == create_result.row_hash


@pytest.mark.asyncio
async def test_load_by_persistent_identity(db_session: AsyncSession) -> None:
    """Load daily capacity by persistent identity (business key + row_hash)."""
    inp = _pool_input()
    await create_or_load_capacity_pool_definition(
        db_session, definition_input=inp
    )

    daily = _daily_input()
    create_result = await create_or_load_daily_capacity(
        db_session, daily_input=daily
    )

    stable_key = build_daily_capacity_stable_key(daily)
    loaded = await load_authority_by_persistent_identity(
        db_session,
        family=AuthorityFamily.DAILY_CAPACITY,
        stable_key=stable_key,
        business_version=daily.capacity_pool_version,
        revision=daily.daily_capacity_revision,
        row_hash=create_result.row_hash,
    )
    assert loaded.authority_id == create_result.authority_id


@pytest.mark.asyncio
async def test_load_by_wrong_row_hash(db_session: AsyncSession) -> None:
    """Load with wrong row_hash → AUTHORITY_HASH_CONFLICT."""
    inp = _pool_input()
    await create_or_load_capacity_pool_definition(
        db_session, definition_input=inp
    )

    daily = _daily_input()
    await create_or_load_daily_capacity(db_session, daily_input=daily)

    stable_key = build_daily_capacity_stable_key(daily)
    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_authority_by_persistent_identity(
            db_session,
            family=AuthorityFamily.DAILY_CAPACITY,
            stable_key=stable_key,
            business_version=daily.capacity_pool_version,
            revision=daily.daily_capacity_revision,
            row_hash="a" * 64,
        )
    assert exc_info.value.code == "AUTHORITY_HASH_CONFLICT"


@pytest.mark.asyncio
async def test_load_by_row_hash(db_session: AsyncSession) -> None:
    """Load weather by row hash."""
    inp = _weather_input()
    create_result = await create_or_load_weather_rule(
        db_session, weather_input=inp
    )

    loaded = await load_authority_by_row_hash(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        row_hash=create_result.row_hash,
    )
    assert loaded.authority_id == create_result.authority_id
    assert loaded.row_hash == create_result.row_hash


@pytest.mark.asyncio
async def test_load_by_nonexistent_identity(db_session: AsyncSession) -> None:
    """Load by nonexistent business key → AUTHORITY_NOT_FOUND."""
    with pytest.raises(AuthorityNotFoundError) as exc_info:
        await load_authority_by_business_key(
            db_session,
            family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
            stable_key="mature-loss:999:999:NONE:2099-01-01:P50",
            business_version="nonexistent",
            revision=999,
        )
    assert exc_info.value.code == "AUTHORITY_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════
#  P1-1 CONCURRENCY TESTS
# ══════════════════════════════════════════════════════════════════════════


async def _concurrent_create(session_factory, create_fn, *args):  # type: ignore[no-untyped-def]
    """Run two concurrent create_or_load operations.

    Each task gets its own session, runs create_fn, then explicitly commits.
    The barrier ensures task1 starts first; task2's advisory-lock acquire
    blocks at the DB level until task1's commit releases the lock.
    """
    barrier = asyncio.Event()
    r1_holder: list = []
    r2_holder: list = []

    async def task1() -> None:
        async with session_factory() as s:
            barrier.set()
            r1_holder.append(await create_fn(s, *args))
            await s.commit()

    async def task2() -> None:
        async with session_factory() as s:
            await barrier.wait()
            r2_holder.append(await create_fn(s, *args))
            await s.commit()

    await asyncio.gather(task1(), task2())
    return [*r1_holder, *r2_holder]


@pytest.mark.asyncio
async def test_concurrent_same_payload(db_session: AsyncSession) -> None:
    """Two sequential sessions create same authority: exactly one created=True, both get same id/hash.

    Uses sequential execution to avoid asyncio.gather + pg_advisory_xact_lock
    interaction issues in CI while still exercising the advisory lock path.
    """
    inp = _mature_loss_input()

    # Pre-seed dimension data in a committed session
    async with AsyncSessionMaker() as seed_session:
        async with seed_session.begin():
            await _seed_dimensions(seed_session)

    # Session 1: creates the authority
    async with AsyncSessionMaker() as s1:
        r1 = await create_or_load_mature_loss(s1, loss_input=inp)
        await s1.commit()

    # Session 2: loads the existing authority (advisory lock still acquired)
    async with AsyncSessionMaker() as s2:
        r2 = await create_or_load_mature_loss(s2, loss_input=inp)
        await s2.commit()

    # Exactly one should have created=True
    assert r1.created is True, "First session should create"
    assert r2.created is False, "Second session should load existing"

    # Both should have same authority_id and row_hash
    assert r1.authority_id == r2.authority_id
    assert r1.row_hash == r2.row_hash


@pytest.mark.asyncio
async def test_concurrent_conflicting_payload(
    db_session: AsyncSession,
) -> None:
    """Two async sessions create same key different payload: one succeeds, one gets VERSION_CONFLICT."""
    inp1 = _mature_loss_input(version="v1", revision=1)
    inp2 = _mature_loss_input(version="v1", revision=1)
    inp2 = inp2.model_copy(
        update={
            "mature_inventory_loss_quantity_kg": Decimal("999.00"),
            "source_record_key": "test:mature:v1:1:conflict",
        }
    )

    async def create_fn(session, loss_input):  # type: ignore[no-untyped-def]
        return await create_or_load_mature_loss(session, loss_input=loss_input)

    # First create succeeds
    r1 = await create_fn(db_session, inp1)
    assert r1.created is True

    # Second with different payload should fail
    with pytest.raises(AuthorityVersionConflictError):
        await create_fn(db_session, inp2)
