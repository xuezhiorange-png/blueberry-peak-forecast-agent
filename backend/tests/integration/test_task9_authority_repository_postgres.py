# ruff: noqa: E501
"""PostgreSQL integration tests for the Task 9 authority repository.

These tests REQUIRE a real PostgreSQL database.  They are gated by the
``RUN_POSTGRES_INTEGRATION`` environment variable and use async fixtures
that wrap each test in a rolled-back transaction for isolation.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

if not os.environ.get("RUN_POSTGRES_INTEGRATION"):
    pytest.skip("RUN_POSTGRES_INTEGRATION not set", allow_module_level=True)

from backend.app.db.session import AsyncSessionMaker
from backend.app.harvest_state.authority_canonical import (
    build_mature_inventory_loss_stable_key,
    make_authority_row_hash,
    make_holiday_calendar_hash,
    make_lifecycle_event_hash,
    make_weather_rule_config_hash,
)
from backend.app.harvest_state.authority_repository import (
    _advisory_lock_key,
    activate_authority,
    cancel_authority,
    create_or_load_capacity_pool_definition,
    create_or_load_daily_capacity,
    create_or_load_holiday_calendar,
    create_or_load_initial_inventory,
    create_or_load_mature_loss,
    create_or_load_run_parameter_package,
    create_or_load_weather_rule,
    load_capacity_pool_definition_by_id,
    load_holiday_calendar_by_id,
    load_initial_inventory_by_id,
    load_mature_loss_by_id,
    load_weather_rule_by_id,
    retire_authority,
    supersede_authority,
)
from backend.app.harvest_state.authority_repository_errors import (
    AuthorityConsumabilityIntervalConflictError,
    AuthorityHashConflictError,
    AuthorityStillReferencedByActivePackageError,
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
    Task9LifecycleEventSemanticInput,
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
from backend.app.models.task9_authority import Task9AuthorityLifecycleEvent

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
    from backend.app.models.task9_authority import Task9HolidayCalendarVersion

    corrupt_stmt = select(Task9HolidayCalendarVersion).where(
        Task9HolidayCalendarVersion.id == result.parent.authority_id,
    )
    corrupt_result = await session_execute(db_session, corrupt_stmt)
    row = corrupt_result.scalar_one()
    original_hash = row.calendar_hash
    row.calendar_hash = "a" * 64  # definitely wrong
    await db_session.flush()

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_holiday_calendar_by_id(
            db_session,
            authority_id=result.parent.authority_id,
        )
    assert exc_info.value.code == "AUTHORITY_HASH_CONFLICT"
    assert exc_info.value.details["reason"] == "persisted_bundle_validation_failed"
    assert exc_info.value.details["component"] == "holiday_calendar_bundle"

    # Restore for rollback safety (not strictly needed since fixture rolls back)
    row.calendar_hash = original_hash
    await db_session.flush()


# ══════════════════════════════════════════════════════════════════════════
#  TEST 23 – Weather config hash mismatch on load
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_weather_config_hash_mismatch_on_load(db_session: AsyncSession) -> None:
    """Corrupt config_hash in DB, verify load raises."""
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

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_weather_rule_by_id(db_session, authority_id=result.authority_id)
    assert exc_info.value.code == "AUTHORITY_HASH_CONFLICT"
    assert exc_info.value.details["reason"] == "persisted_bundle_validation_failed"
    assert exc_info.value.details["component"] == "weather_rule"

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


async def _seed_dimensions_committed() -> None:
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


async def _rewrite_lifecycle_event(
    session: AsyncSession,
    *,
    event_id: int,
    family: AuthorityFamily,
    **updates: object,
) -> None:
    event_stmt = select(Task9AuthorityLifecycleEvent).where(
        Task9AuthorityLifecycleEvent.id == event_id
    )
    event = (await session.execute(event_stmt)).scalar_one()
    payload = {
        "authority_family": family,
        "authority_stable_key": event.authority_stable_key,
        "authority_business_version": event.authority_business_version,
        "authority_revision": event.authority_revision,
        "business_row_hash": event.business_row_hash,
        "transition_sequence": event.transition_sequence,
        "old_status": event.old_status,
        "new_status": event.new_status,
        "old_consumable_from_local_date": event.old_consumable_from_local_date,
        "old_consumable_to_local_date": event.old_consumable_to_local_date,
        "new_consumable_from_local_date": event.new_consumable_from_local_date,
        "new_consumable_to_local_date": event.new_consumable_to_local_date,
        "superseded_by_authority_stable_key": event.superseded_by_authority_stable_key,
        "superseded_by_authority_business_version": event.superseded_by_authority_business_version,
        "superseded_by_authority_revision": event.superseded_by_authority_revision,
        "transitioned_at": event.transitioned_at,
        "source_system": event.source_system,
        "source_record_key": event.source_record_key,
    }
    payload.update(updates)
    # Remove lifecycle_event_hash before constructing semantic input
    # (Task9LifecycleEventSemanticInput has extra="forbid")
    semantic_payload = {k: v for k, v in payload.items() if k != "lifecycle_event_hash"}
    semantic = Task9LifecycleEventSemanticInput(**semantic_payload)
    payload["lifecycle_event_hash"] = make_lifecycle_event_hash(semantic)
    await session.execute(
        text(
            """
            UPDATE task9_authority_lifecycle_event
            SET old_status = :old_status,
                new_status = :new_status,
                old_consumable_from_local_date = :old_consumable_from_local_date,
                old_consumable_to_local_date = :old_consumable_to_local_date,
                new_consumable_from_local_date = :new_consumable_from_local_date,
                new_consumable_to_local_date = :new_consumable_to_local_date,
                superseded_by_authority_stable_key = :superseded_by_authority_stable_key,
                superseded_by_authority_business_version = :superseded_by_authority_business_version,
                superseded_by_authority_revision = :superseded_by_authority_revision,
                lifecycle_event_hash = :lifecycle_event_hash
            WHERE id = :event_id
            """
        ),
        {
            "event_id": event_id,
            "old_status": payload["old_status"],
            "new_status": payload["new_status"],
            "old_consumable_from_local_date": payload["old_consumable_from_local_date"],
            "old_consumable_to_local_date": payload["old_consumable_to_local_date"],
            "new_consumable_from_local_date": payload["new_consumable_from_local_date"],
            "new_consumable_to_local_date": payload["new_consumable_to_local_date"],
            "superseded_by_authority_stable_key": payload["superseded_by_authority_stable_key"],
            "superseded_by_authority_business_version": payload[
                "superseded_by_authority_business_version"
            ],
            "superseded_by_authority_revision": payload["superseded_by_authority_revision"],
            "lifecycle_event_hash": payload["lifecycle_event_hash"],
        },
    )


@pytest.mark.asyncio
async def test_load_mature_loss_rejects_final_consumable_to_projection_mismatch(
    db_session: AsyncSession,
) -> None:
    inp = _mature_loss_input()
    created = await create_or_load_mature_loss(db_session, loss_input=inp)
    await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=created.authority_id,
        activation_boundary=date(2026, 6, 1),
    )
    await retire_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=created.authority_id,
        retirement_boundary=date(2026, 12, 31),
    )
    stable_key = build_mature_inventory_loss_stable_key(inp)
    events = await _query_lifecycle_events(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY.value,
        stable_key=stable_key,
        version=inp.loss_version,
        revision=inp.revision,
    )
    await _rewrite_lifecycle_event(
        db_session,
        event_id=events[-1].id,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        new_consumable_to_local_date=date(2026, 12, 30),
    )
    db_session.expire_all()
    with pytest.raises(AuthorityConsumabilityIntervalConflictError) as exc_info:
        await load_mature_loss_by_id(db_session, authority_id=created.authority_id)
    assert exc_info.value.code == "AUTHORITY_CONSUMABILITY_INTERVAL_CONFLICT"
    assert exc_info.value.details["reason"] == "final_consumable_to_projection_mismatch"


@pytest.mark.asyncio
async def test_load_mature_loss_rejects_illegal_transition_even_with_valid_hash(
    db_session: AsyncSession,
) -> None:
    inp = _mature_loss_input()
    created = await create_or_load_mature_loss(db_session, loss_input=inp)
    await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=created.authority_id,
        activation_boundary=date(2026, 6, 1),
    )
    await db_session.execute(
        text(
            """
            UPDATE task9_mature_inventory_loss_authority
            SET status = 'cancelled',
                consumable_from_local_date = NULL,
                consumable_to_local_date = NULL
            WHERE id = :authority_id
            """
        ),
        {"authority_id": created.authority_id},
    )
    stable_key = build_mature_inventory_loss_stable_key(inp)
    events = await _query_lifecycle_events(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY.value,
        stable_key=stable_key,
        version=inp.loss_version,
        revision=inp.revision,
    )
    await _rewrite_lifecycle_event(
        db_session,
        event_id=events[-1].id,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        new_status=AuthorityStatus.CANCELLED,
        new_consumable_from_local_date=None,
        new_consumable_to_local_date=None,
    )
    with pytest.raises(LifecycleTransitionInvalidError) as exc_info:
        await load_mature_loss_by_id(db_session, authority_id=created.authority_id)
    assert exc_info.value.code == "LIFECYCLE_TRANSITION_INVALID"
    assert exc_info.value.details["reason"] == "final_status_projection_mismatch"


@pytest.mark.asyncio
async def test_load_holiday_tampered_child_validation_becomes_typed_hash_conflict(
    db_session: AsyncSession,
) -> None:
    inp = _holiday_input()
    created = await create_or_load_holiday_calendar(db_session, calendar_input=inp)
    await db_session.execute(
        text(
            """
            UPDATE task9_holiday_calendar_date
            SET holiday_code = ''
            WHERE holiday_calendar_version_id = :authority_id
              AND holiday_code = 'CNY'
            """
        ),
        {"authority_id": created.parent.authority_id},
    )
    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_holiday_calendar_by_id(db_session, authority_id=created.parent.authority_id)
    assert exc_info.value.code == "AUTHORITY_HASH_CONFLICT"
    assert exc_info.value.details["reason"] == "persisted_bundle_validation_failed"
    assert exc_info.value.details["component"] == "holiday_calendar_date"


@pytest.mark.asyncio
async def test_load_pool_rejects_parent_projection_tamper(db_session: AsyncSession) -> None:
    """Tamper member status → repository detects parent projection mismatch."""
    inp = _pool_input()
    created = await create_or_load_capacity_pool_definition(db_session, definition_input=inp)
    # Tamper: change member consumable_from_key (no FK, no CHECK constraint)
    # to a value different from the parent's projection.
    await db_session.execute(
        text(
            """
            UPDATE task9_capacity_pool_member
            SET consumable_from_key = '1900-01-01'
            WHERE capacity_pool_definition_id = :authority_id
            """
        ),
        {"authority_id": created.parent.authority_id},
    )
    await db_session.flush()
    db_session.expire_all()
    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_capacity_pool_definition_by_id(
            db_session, authority_id=created.parent.authority_id
        )
    assert exc_info.value.code == "AUTHORITY_HASH_CONFLICT"
    assert exc_info.value.details["reason"] == "capacity_pool_member_parent_projection_mismatch"
    assert exc_info.value.details["field"] == "consumable_from_key"


@pytest.mark.asyncio
async def test_concurrent_pool_create_same_payload_blocks_then_reuses_row() -> None:
    await _seed_dimensions_committed()
    pool = _pool_input(code=f"POOL-{uuid4().hex[:8]}")
    stable_key = (
        f"capacity-pool:{pool.season_id}:{pool.destination_factory_id}:{pool.capacity_pool_code}"
    )
    lock_key = _advisory_lock_key(
        AuthorityFamily.CAPACITY_POOL_DEFINITION,
        stable_key,
        pool.capacity_pool_version,
        pool.revision,
    )
    session2_started = asyncio.Event()
    async with AsyncSessionMaker() as session1:
        tx1 = await session1.begin()
        try:
            await session1.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
            result1 = await create_or_load_capacity_pool_definition(session1, definition_input=pool)

            async def _runner() -> object:
                async with AsyncSessionMaker() as session2:
                    async with session2.begin():
                        session2_started.set()
                        return await create_or_load_capacity_pool_definition(
                            session2,
                            definition_input=pool,
                        )

            task = asyncio.create_task(_runner())
            await session2_started.wait()
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=0.2)
            await tx1.commit()
            result2 = await asyncio.wait_for(task, timeout=15)
        finally:
            if tx1.is_active:
                await tx1.rollback()

    assert result1.parent.created is True
    assert result2.parent.created is False
    assert result1.parent.authority_id == result2.parent.authority_id
    assert result1.parent.row_hash == result2.parent.row_hash

    async with AsyncSessionMaker() as verify_session:
        row_count = (
            await verify_session.execute(
                text(
                    """
                    SELECT count(*)
                    FROM task9_capacity_pool_definition
                    WHERE season_id = :season_id
                      AND destination_factory_id = :factory_id
                      AND capacity_pool_code = :capacity_pool_code
                      AND capacity_pool_version = :capacity_pool_version
                      AND revision = :revision
                    """
                ),
                {
                    "season_id": pool.season_id,
                    "factory_id": pool.destination_factory_id,
                    "capacity_pool_code": pool.capacity_pool_code,
                    "capacity_pool_version": pool.capacity_pool_version,
                    "revision": pool.revision,
                },
            )
        ).scalar_one()
        event_count = (
            await verify_session.execute(
                text(
                    """
                    SELECT count(*)
                    FROM task9_authority_lifecycle_event
                    WHERE authority_family = :family
                      AND authority_stable_key = :stable_key
                      AND authority_business_version = :version
                      AND authority_revision = :revision
                    """
                ),
                {
                    "family": AuthorityFamily.CAPACITY_POOL_DEFINITION.value,
                    "stable_key": stable_key,
                    "version": pool.capacity_pool_version,
                    "revision": pool.revision,
                },
            )
        ).scalar_one()
    assert row_count == 1
    assert event_count == 1


@pytest.mark.asyncio
async def test_concurrent_pool_create_conflicting_payload_returns_typed_conflict() -> None:
    await _seed_dimensions_committed()
    pool_a = _pool_input(code=f"POOL-{uuid4().hex[:8]}")
    pool_b = pool_a.model_copy(
        update={
            "source_record_key": f"{pool_a.source_record_key}:other",
            "members": [
                Task9CapacityPoolMemberSchema(
                    farm_id=_IDS["farm"],
                    subfarm_id=_IDS["subfarm"],
                    variety_id=_IDS["variety"],
                )
            ],
        }
    )
    stable_key = f"capacity-pool:{pool_a.season_id}:{pool_a.destination_factory_id}:{pool_a.capacity_pool_code}"
    lock_key = _advisory_lock_key(
        AuthorityFamily.CAPACITY_POOL_DEFINITION,
        stable_key,
        pool_a.capacity_pool_version,
        pool_a.revision,
    )
    session2_started = asyncio.Event()
    async with AsyncSessionMaker() as session1:
        tx1 = await session1.begin()
        try:
            await session1.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
            result1 = await create_or_load_capacity_pool_definition(
                session1, definition_input=pool_a
            )

            async def _runner_conflict() -> object:
                async with AsyncSessionMaker() as session2:
                    async with session2.begin():
                        session2_started.set()
                        return await create_or_load_capacity_pool_definition(
                            session2,
                            definition_input=pool_b,
                        )

            task = asyncio.create_task(_runner_conflict())
            await session2_started.wait()
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=0.2)
            await tx1.commit()
            with pytest.raises(AuthorityVersionConflictError) as exc_info:
                await asyncio.wait_for(task, timeout=15)
        finally:
            if tx1.is_active:
                await tx1.rollback()

    assert result1.parent.created is True
    assert exc_info.value.code == "AUTHORITY_VERSION_CONFLICT"
    async with AsyncSessionMaker() as verify_session:
        row_count = (
            await verify_session.execute(
                text(
                    """
                    SELECT count(*)
                    FROM task9_capacity_pool_definition
                    WHERE season_id = :season_id
                      AND destination_factory_id = :factory_id
                      AND capacity_pool_code = :capacity_pool_code
                      AND capacity_pool_version = :capacity_pool_version
                      AND revision = :revision
                    """
                ),
                {
                    "season_id": pool_a.season_id,
                    "factory_id": pool_a.destination_factory_id,
                    "capacity_pool_code": pool_a.capacity_pool_code,
                    "capacity_pool_version": pool_a.capacity_pool_version,
                    "revision": pool_a.revision,
                },
            )
        ).scalar_one()
        event_count = (
            await verify_session.execute(
                text(
                    """
                    SELECT count(*)
                    FROM task9_authority_lifecycle_event
                    WHERE authority_family = :family
                      AND authority_stable_key = :stable_key
                      AND authority_business_version = :version
                      AND authority_revision = :revision
                    """
                ),
                {
                    "family": AuthorityFamily.CAPACITY_POOL_DEFINITION.value,
                    "stable_key": stable_key,
                    "version": pool_a.capacity_pool_version,
                    "revision": pool_a.revision,
                },
            )
        ).scalar_one()
    assert row_count == 1
    assert event_count == 1
