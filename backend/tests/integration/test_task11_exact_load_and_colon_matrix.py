"""Exact-load API direct coverage tests and daily-capacity colon matrix tests.

14 loaders imported (7 by_business_key + 7 by_row_hash):
  load_capacity_pool_definition_by_business_key
  load_capacity_pool_definition_by_row_hash
  load_daily_capacity_by_business_key
  load_daily_capacity_by_row_hash
  load_holiday_calendar_by_business_key
  load_holiday_calendar_by_row_hash
  load_weather_rule_by_business_key
  load_weather_rule_by_row_hash
  load_run_parameter_package_by_business_key
  load_run_parameter_package_by_row_hash
  load_initial_inventory_by_business_key
  load_initial_inventory_by_row_hash
  load_mature_loss_by_business_key
  load_mature_loss_by_row_hash
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import AsyncSessionMaker
from backend.app.harvest_state.authority_canonical import (
    build_capacity_pool_definition_stable_key,
    build_daily_capacity_stable_key,
    build_holiday_calendar_stable_key,
    build_initial_inventory_stable_key,
    build_mature_inventory_loss_stable_key,
    build_run_parameter_package_stable_key,
    build_weather_rule_stable_key,
    make_holiday_calendar_hash,
    make_weather_rule_config_hash,
)
from backend.app.harvest_state.authority_repository import (
    create_or_load_capacity_pool_definition,
    create_or_load_daily_capacity,
    create_or_load_holiday_calendar,
    create_or_load_initial_inventory,
    create_or_load_mature_loss,
    create_or_load_run_parameter_package,
    create_or_load_weather_rule,
    load_capacity_pool_definition_by_business_key,
    load_capacity_pool_definition_by_row_hash,
    load_daily_capacity_by_business_key,
    load_daily_capacity_by_row_hash,
    load_holiday_calendar_by_business_key,
    load_holiday_calendar_by_row_hash,
    load_initial_inventory_by_business_key,
    load_initial_inventory_by_row_hash,
    load_mature_loss_by_business_key,
    load_mature_loss_by_row_hash,
    load_run_parameter_package_by_business_key,
    load_run_parameter_package_by_row_hash,
    load_weather_rule_by_business_key,
    load_weather_rule_by_row_hash,
)
from backend.app.harvest_state.authority_repository_errors import (
    AuthorityNotFoundError,
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
    AuthorityStatus,
    CapacityInputMode,
    CapacityPoolGrain,
    ForecastQuantile,
    WeatherCombinationMethod,
)
from backend.app.harvest_state.schemas import WeatherFeatureBand, WeatherFeatureRule

pytestmark = pytest.mark.integration


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
async def db_session():
    """Yield an AsyncSession wrapped in a transaction that rolls back on exit.

    Seeds required FK dimension tables before yielding.
    """
    async with AsyncSessionMaker() as session:
        async with session.begin():
            # Seed dimension tables required by FK constraints
            from sqlalchemy import text

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
            _IDS["season"] = season_row.scalar_one()
            _IDS["factory"] = factory_row.scalar_one()
            _IDS["farm"] = farm_id
            _IDS["subfarm"] = subfarm_row.scalar_one()
            _IDS["variety"] = variety_row.scalar_one()
            yield session


# ── Deterministic test data helpers ──────────────────────────────────────

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


# ── Helper: create or find pool + daily capacity for tests ──────────────


async def _ensure_pool_for_daily(
    session: AsyncSession,
    *,
    pool_code: str = "TEST-POOL",
    pool_version: str = "v1",
    pool_revision: int = 1,
) -> int:
    """Create a pool definition needed as FK for daily capacity. Returns authority_id."""
    pool = _pool_input(code=pool_code, version=pool_version, revision=pool_revision)
    result = await create_or_load_capacity_pool_definition(session, definition_input=pool)
    return result.parent.authority_id


# ══════════════════════════════════════════════════════════════════════════
#  SECTION A – by_business_key happy path (7 families)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_exact_load_pool_by_business_key_happy(db_session: AsyncSession) -> None:
    """Create a capacity pool, then load by business_key, verify same authority_id."""
    inp = _pool_input()
    create_result = await create_or_load_capacity_pool_definition(db_session, definition_input=inp)
    expected_id = create_result.parent.authority_id

    stable_key = build_capacity_pool_definition_stable_key(inp)
    loaded = await load_capacity_pool_definition_by_business_key(
        db_session,
        stable_key=stable_key,
        business_version=inp.capacity_pool_version,
        revision=inp.revision,
    )
    assert loaded.parent.authority_id == expected_id


@pytest.mark.asyncio
async def test_exact_load_daily_by_business_key_happy(db_session: AsyncSession) -> None:
    """Create a daily capacity (with pool FK), then load by business_key."""
    await _ensure_pool_for_daily(db_session)
    inp = _daily_input()
    create_result = await create_or_load_daily_capacity(db_session, daily_input=inp)
    expected_id = create_result.authority_id

    stable_key = build_daily_capacity_stable_key(inp)
    loaded = await load_daily_capacity_by_business_key(
        db_session,
        stable_key=stable_key,
        business_version=inp.capacity_pool_version,
        revision=inp.daily_capacity_revision,
    )
    assert loaded.authority_id == expected_id


@pytest.mark.asyncio
async def test_exact_load_holiday_by_business_key_happy(db_session: AsyncSession) -> None:
    """Create a holiday calendar, then load by business_key, verify same authority_id."""
    inp = _holiday_input()
    create_result = await create_or_load_holiday_calendar(db_session, calendar_input=inp)
    expected_id = create_result.parent.authority_id

    stable_key = build_holiday_calendar_stable_key(inp)
    loaded = await load_holiday_calendar_by_business_key(
        db_session,
        stable_key=stable_key,
        business_version=inp.calendar_version,
        revision=inp.revision,
    )
    assert loaded.parent.authority_id == expected_id


@pytest.mark.asyncio
async def test_exact_load_weather_by_business_key_happy(db_session: AsyncSession) -> None:
    """Create a weather rule, then load by business_key, verify same authority_id."""
    inp = _weather_input()
    create_result = await create_or_load_weather_rule(db_session, weather_input=inp)
    expected_id = create_result.authority_id

    stable_key = build_weather_rule_stable_key(inp)
    loaded = await load_weather_rule_by_business_key(
        db_session,
        stable_key=stable_key,
        business_version=inp.rule_version,
        revision=inp.revision,
    )
    assert loaded.authority_id == expected_id


@pytest.mark.asyncio
async def test_exact_load_run_package_by_business_key_happy(db_session: AsyncSession) -> None:
    """Create a run-package, then load by business_key, verify same authority_id."""
    await create_or_load_holiday_calendar(db_session, calendar_input=_holiday_input())
    await create_or_load_weather_rule(db_session, weather_input=_weather_input())
    inp = _run_package_input()
    create_result = await create_or_load_run_parameter_package(
        db_session,
        package_input=inp,
        holiday_calendar=_holiday_input(),
        weather_rule=_weather_input(),
    )
    expected_id = create_result.authority_id

    stable_key = build_run_parameter_package_stable_key(inp)
    loaded = await load_run_parameter_package_by_business_key(
        db_session,
        stable_key=stable_key,
        business_version=inp.package_version,
        revision=inp.revision,
    )
    assert loaded.authority_id == expected_id


@pytest.mark.asyncio
async def test_exact_load_inventory_by_business_key_happy(db_session: AsyncSession) -> None:
    """Create an initial inventory, then load by business_key, verify same authority_id."""
    inp = _inventory_input()
    create_result = await create_or_load_initial_inventory(db_session, inventory_input=inp)
    expected_id = create_result.parent.authority_id

    stable_key = build_initial_inventory_stable_key(inp)
    loaded = await load_initial_inventory_by_business_key(
        db_session,
        stable_key=stable_key,
        business_version=inp.snapshot_version,
        revision=inp.revision,
    )
    assert loaded.parent.authority_id == expected_id


@pytest.mark.asyncio
async def test_exact_load_mature_loss_by_business_key_happy(db_session: AsyncSession) -> None:
    """Create a mature loss, then load by business_key, verify same authority_id."""
    inp = _mature_loss_input()
    create_result = await create_or_load_mature_loss(db_session, loss_input=inp)
    expected_id = create_result.authority_id

    stable_key = build_mature_inventory_loss_stable_key(inp)
    loaded = await load_mature_loss_by_business_key(
        db_session,
        stable_key=stable_key,
        business_version=inp.loss_version,
        revision=inp.revision,
    )
    assert loaded.authority_id == expected_id


# ══════════════════════════════════════════════════════════════════════════
#  SECTION B – by_business_key wrong stable_key (7 families)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_exact_load_pool_by_business_key_wrong_key(db_session: AsyncSession) -> None:
    """Wrong stable_key must raise AuthorityNotFoundError."""
    inp = _pool_input()
    await create_or_load_capacity_pool_definition(db_session, definition_input=inp)

    with pytest.raises(AuthorityNotFoundError):
        await load_capacity_pool_definition_by_business_key(
            db_session,
            stable_key="capacity-pool:999999:999999:WRONG-POOL",
            business_version=inp.capacity_pool_version,
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_exact_load_daily_by_business_key_wrong_key(db_session: AsyncSession) -> None:
    """Wrong stable_key must raise AuthorityNotFoundError."""
    await _ensure_pool_for_daily(db_session)
    inp = _daily_input()
    await create_or_load_daily_capacity(db_session, daily_input=inp)

    with pytest.raises(AuthorityNotFoundError):
        await load_daily_capacity_by_business_key(
            db_session,
            stable_key="daily-capacity:999999:999999:WRONG-POOL:v1:1:2026-06-15",
            business_version=inp.capacity_pool_version,
            revision=inp.daily_capacity_revision,
        )


@pytest.mark.asyncio
async def test_exact_load_holiday_by_business_key_wrong_key(db_session: AsyncSession) -> None:
    """Wrong stable_key must raise AuthorityNotFoundError."""
    inp = _holiday_input()
    await create_or_load_holiday_calendar(db_session, calendar_input=inp)

    with pytest.raises(AuthorityNotFoundError):
        await load_holiday_calendar_by_business_key(
            db_session,
            stable_key="holiday-calendar:999999:WRONG-CAL:Asia/Shanghai",
            business_version=inp.calendar_version,
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_exact_load_weather_by_business_key_wrong_key(db_session: AsyncSession) -> None:
    """Wrong stable_key must raise AuthorityNotFoundError."""
    inp = _weather_input()
    await create_or_load_weather_rule(db_session, weather_input=inp)

    with pytest.raises(AuthorityNotFoundError):
        await load_weather_rule_by_business_key(
            db_session,
            stable_key="weather-rule:WRONG-RULE:Asia/Shanghai",
            business_version=inp.rule_version,
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_exact_load_run_package_by_business_key_wrong_key(db_session: AsyncSession) -> None:
    """Wrong stable_key must raise AuthorityNotFoundError."""
    await create_or_load_holiday_calendar(db_session, calendar_input=_holiday_input())
    await create_or_load_weather_rule(db_session, weather_input=_weather_input())
    inp = _run_package_input()
    await create_or_load_run_parameter_package(
        db_session,
        package_input=inp,
        holiday_calendar=_holiday_input(),
        weather_rule=_weather_input(),
    )

    with pytest.raises(AuthorityNotFoundError):
        await load_run_parameter_package_by_business_key(
            db_session,
            stable_key="run-package:999999:999999:wrong-scope",
            business_version=inp.package_version,
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_exact_load_inventory_by_business_key_wrong_key(db_session: AsyncSession) -> None:
    """Wrong stable_key must raise AuthorityNotFoundError."""
    inp = _inventory_input()
    await create_or_load_initial_inventory(db_session, inventory_input=inp)

    with pytest.raises(AuthorityNotFoundError):
        await load_initial_inventory_by_business_key(
            db_session,
            stable_key="initial-inventory:999999:999999:2099-01-01",
            business_version=inp.snapshot_version,
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_exact_load_mature_loss_by_business_key_wrong_key(db_session: AsyncSession) -> None:
    """Wrong stable_key must raise AuthorityNotFoundError."""
    inp = _mature_loss_input()
    await create_or_load_mature_loss(db_session, loss_input=inp)

    with pytest.raises(AuthorityNotFoundError):
        await load_mature_loss_by_business_key(
            db_session,
            stable_key="mature-loss:999999:999999:WRONG-POOL:2026-06-15:p50",
            business_version=inp.loss_version,
            revision=inp.revision,
        )


# ══════════════════════════════════════════════════════════════════════════
#  SECTION C – by_business_key wrong business_version (7 families)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_exact_load_pool_by_business_key_wrong_version(db_session: AsyncSession) -> None:
    """Correct stable_key but wrong business_version → AuthorityNotFoundError."""
    inp = _pool_input()
    await create_or_load_capacity_pool_definition(db_session, definition_input=inp)

    stable_key = build_capacity_pool_definition_stable_key(inp)
    with pytest.raises(AuthorityNotFoundError):
        await load_capacity_pool_definition_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version="v99",
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_exact_load_daily_by_business_key_wrong_version(db_session: AsyncSession) -> None:
    """Correct stable_key but wrong business_version → AuthorityNotFoundError."""
    await _ensure_pool_for_daily(db_session)
    inp = _daily_input()
    await create_or_load_daily_capacity(db_session, daily_input=inp)

    stable_key = build_daily_capacity_stable_key(inp)
    with pytest.raises(AuthorityNotFoundError):
        await load_daily_capacity_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version="v99",
            revision=inp.daily_capacity_revision,
        )


@pytest.mark.asyncio
async def test_exact_load_holiday_by_business_key_wrong_version(db_session: AsyncSession) -> None:
    """Correct stable_key but wrong business_version → AuthorityNotFoundError."""
    inp = _holiday_input()
    await create_or_load_holiday_calendar(db_session, calendar_input=inp)

    stable_key = build_holiday_calendar_stable_key(inp)
    with pytest.raises(AuthorityNotFoundError):
        await load_holiday_calendar_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version="v99",
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_exact_load_weather_by_business_key_wrong_version(db_session: AsyncSession) -> None:
    """Correct stable_key but wrong business_version → AuthorityNotFoundError."""
    inp = _weather_input()
    await create_or_load_weather_rule(db_session, weather_input=inp)

    stable_key = build_weather_rule_stable_key(inp)
    with pytest.raises(AuthorityNotFoundError):
        await load_weather_rule_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version="v99",
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_exact_load_run_package_by_business_key_wrong_version(
    db_session: AsyncSession,
) -> None:
    """Correct stable_key but wrong business_version → AuthorityNotFoundError."""
    await create_or_load_holiday_calendar(db_session, calendar_input=_holiday_input())
    await create_or_load_weather_rule(db_session, weather_input=_weather_input())
    inp = _run_package_input()
    await create_or_load_run_parameter_package(
        db_session,
        package_input=inp,
        holiday_calendar=_holiday_input(),
        weather_rule=_weather_input(),
    )

    stable_key = build_run_parameter_package_stable_key(inp)
    with pytest.raises(AuthorityNotFoundError):
        await load_run_parameter_package_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version="v99",
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_exact_load_inventory_by_business_key_wrong_version(db_session: AsyncSession) -> None:
    """Correct stable_key but wrong business_version → AuthorityNotFoundError."""
    inp = _inventory_input()
    await create_or_load_initial_inventory(db_session, inventory_input=inp)

    stable_key = build_initial_inventory_stable_key(inp)
    with pytest.raises(AuthorityNotFoundError):
        await load_initial_inventory_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version="v99",
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_exact_load_mature_loss_by_business_key_wrong_version(
    db_session: AsyncSession,
) -> None:
    """Correct stable_key but wrong business_version → AuthorityNotFoundError."""
    inp = _mature_loss_input()
    await create_or_load_mature_loss(db_session, loss_input=inp)

    stable_key = build_mature_inventory_loss_stable_key(inp)
    with pytest.raises(AuthorityNotFoundError):
        await load_mature_loss_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version="v99",
            revision=inp.revision,
        )


# ══════════════════════════════════════════════════════════════════════════
#  SECTION D – by_business_key malformed prefix (7 families)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_exact_load_pool_by_business_key_malformed_prefix(db_session: AsyncSession) -> None:
    """Key with wrong prefix → AuthorityNotFoundError."""
    inp = _pool_input()
    await create_or_load_capacity_pool_definition(db_session, definition_input=inp)

    with pytest.raises(AuthorityNotFoundError):
        await load_capacity_pool_definition_by_business_key(
            db_session,
            stable_key="wrong-prefix:1:2:3",
            business_version=inp.capacity_pool_version,
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_exact_load_daily_by_business_key_malformed_prefix(db_session: AsyncSession) -> None:
    """Key with wrong prefix → AuthorityNotFoundError."""
    await _ensure_pool_for_daily(db_session)
    inp = _daily_input()
    await create_or_load_daily_capacity(db_session, daily_input=inp)

    with pytest.raises(AuthorityNotFoundError):
        await load_daily_capacity_by_business_key(
            db_session,
            stable_key="wrong-prefix:1:2:3:v1:1:2026-06-15",
            business_version=inp.capacity_pool_version,
            revision=inp.daily_capacity_revision,
        )


@pytest.mark.asyncio
async def test_exact_load_holiday_by_business_key_malformed_prefix(
    db_session: AsyncSession,
) -> None:
    """Key with wrong prefix → AuthorityNotFoundError."""
    inp = _holiday_input()
    await create_or_load_holiday_calendar(db_session, calendar_input=inp)

    with pytest.raises(AuthorityNotFoundError):
        await load_holiday_calendar_by_business_key(
            db_session,
            stable_key="wrong-prefix:1:2:3",
            business_version=inp.calendar_version,
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_exact_load_weather_by_business_key_malformed_prefix(
    db_session: AsyncSession,
) -> None:
    """Key with wrong prefix → AuthorityNotFoundError."""
    inp = _weather_input()
    await create_or_load_weather_rule(db_session, weather_input=inp)

    with pytest.raises(AuthorityNotFoundError):
        await load_weather_rule_by_business_key(
            db_session,
            stable_key="wrong-prefix:1:2:3",
            business_version=inp.rule_version,
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_exact_load_run_package_by_business_key_malformed_prefix(
    db_session: AsyncSession,
) -> None:
    """Key with wrong prefix → AuthorityNotFoundError."""
    await create_or_load_holiday_calendar(db_session, calendar_input=_holiday_input())
    await create_or_load_weather_rule(db_session, weather_input=_weather_input())
    inp = _run_package_input()
    await create_or_load_run_parameter_package(
        db_session,
        package_input=inp,
        holiday_calendar=_holiday_input(),
        weather_rule=_weather_input(),
    )

    with pytest.raises(AuthorityNotFoundError):
        await load_run_parameter_package_by_business_key(
            db_session,
            stable_key="wrong-prefix:1:2:3",
            business_version=inp.package_version,
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_exact_load_inventory_by_business_key_malformed_prefix(
    db_session: AsyncSession,
) -> None:
    """Key with wrong prefix → AuthorityNotFoundError."""
    inp = _inventory_input()
    await create_or_load_initial_inventory(db_session, inventory_input=inp)

    with pytest.raises(AuthorityNotFoundError):
        await load_initial_inventory_by_business_key(
            db_session,
            stable_key="wrong-prefix:1:2:3",
            business_version=inp.snapshot_version,
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_exact_load_mature_loss_by_business_key_malformed_prefix(
    db_session: AsyncSession,
) -> None:
    """Key with wrong prefix → AuthorityNotFoundError."""
    inp = _mature_loss_input()
    await create_or_load_mature_loss(db_session, loss_input=inp)

    with pytest.raises(AuthorityNotFoundError):
        await load_mature_loss_by_business_key(
            db_session,
            stable_key="wrong-prefix:1:2:3",
            business_version=inp.loss_version,
            revision=inp.revision,
        )


# ══════════════════════════════════════════════════════════════════════════
#  SECTION E – by_row_hash happy path (7 families)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_exact_load_pool_by_row_hash_happy(db_session: AsyncSession) -> None:
    """Create a capacity pool, then load by row_hash, verify same authority_id."""
    inp = _pool_input()
    create_result = await create_or_load_capacity_pool_definition(db_session, definition_input=inp)
    expected_id = create_result.parent.authority_id
    row_hash = create_result.parent.row_hash

    loaded = await load_capacity_pool_definition_by_row_hash(db_session, row_hash=row_hash)
    assert loaded.parent.authority_id == expected_id


@pytest.mark.asyncio
async def test_exact_load_daily_by_row_hash_happy(db_session: AsyncSession) -> None:
    """Create a daily capacity, then load by row_hash, verify same authority_id."""
    await _ensure_pool_for_daily(db_session)
    inp = _daily_input()
    create_result = await create_or_load_daily_capacity(db_session, daily_input=inp)
    expected_id = create_result.authority_id
    row_hash = create_result.row_hash

    loaded = await load_daily_capacity_by_row_hash(db_session, row_hash=row_hash)
    assert loaded.authority_id == expected_id


@pytest.mark.asyncio
async def test_exact_load_holiday_by_row_hash_happy(db_session: AsyncSession) -> None:
    """Create a holiday calendar, then load by row_hash, verify same authority_id."""
    inp = _holiday_input()
    create_result = await create_or_load_holiday_calendar(db_session, calendar_input=inp)
    expected_id = create_result.parent.authority_id
    row_hash = create_result.parent.row_hash

    loaded = await load_holiday_calendar_by_row_hash(db_session, row_hash=row_hash)
    assert loaded.parent.authority_id == expected_id


@pytest.mark.asyncio
async def test_exact_load_weather_by_row_hash_happy(db_session: AsyncSession) -> None:
    """Create a weather rule, then load by row_hash, verify same authority_id."""
    inp = _weather_input()
    create_result = await create_or_load_weather_rule(db_session, weather_input=inp)
    expected_id = create_result.authority_id
    row_hash = create_result.row_hash

    loaded = await load_weather_rule_by_row_hash(db_session, row_hash=row_hash)
    assert loaded.authority_id == expected_id


@pytest.mark.asyncio
async def test_exact_load_run_package_by_row_hash_happy(db_session: AsyncSession) -> None:
    """Create a run-package, then load by row_hash, verify same authority_id."""
    await create_or_load_holiday_calendar(db_session, calendar_input=_holiday_input())
    await create_or_load_weather_rule(db_session, weather_input=_weather_input())
    inp = _run_package_input()
    create_result = await create_or_load_run_parameter_package(
        db_session,
        package_input=inp,
        holiday_calendar=_holiday_input(),
        weather_rule=_weather_input(),
    )
    expected_id = create_result.authority_id
    row_hash = create_result.row_hash

    loaded = await load_run_parameter_package_by_row_hash(db_session, row_hash=row_hash)
    assert loaded.authority_id == expected_id


@pytest.mark.asyncio
async def test_exact_load_inventory_by_row_hash_happy(db_session: AsyncSession) -> None:
    """Create an initial inventory, then load by row_hash, verify same authority_id."""
    inp = _inventory_input()
    create_result = await create_or_load_initial_inventory(db_session, inventory_input=inp)
    expected_id = create_result.parent.authority_id
    row_hash = create_result.parent.row_hash

    loaded = await load_initial_inventory_by_row_hash(db_session, row_hash=row_hash)
    assert loaded.parent.authority_id == expected_id


@pytest.mark.asyncio
async def test_exact_load_mature_loss_by_row_hash_happy(db_session: AsyncSession) -> None:
    """Create a mature loss, then load by row_hash, verify same authority_id."""
    inp = _mature_loss_input()
    create_result = await create_or_load_mature_loss(db_session, loss_input=inp)
    expected_id = create_result.authority_id
    row_hash = create_result.row_hash

    loaded = await load_mature_loss_by_row_hash(db_session, row_hash=row_hash)
    assert loaded.authority_id == expected_id


# ══════════════════════════════════════════════════════════════════════════
#  SECTION F – by_row_hash zero match / fake hash (7 families)
# ══════════════════════════════════════════════════════════════════════════

_FAKE_HASH = "0" * 64


@pytest.mark.asyncio
async def test_exact_load_pool_by_row_hash_zero_match(db_session: AsyncSession) -> None:
    """Fake row_hash must raise AuthorityNotFoundError."""
    with pytest.raises(AuthorityNotFoundError):
        await load_capacity_pool_definition_by_row_hash(db_session, row_hash=_FAKE_HASH)


@pytest.mark.asyncio
async def test_exact_load_daily_by_row_hash_zero_match(db_session: AsyncSession) -> None:
    """Fake row_hash must raise AuthorityNotFoundError."""
    with pytest.raises(AuthorityNotFoundError):
        await load_daily_capacity_by_row_hash(db_session, row_hash=_FAKE_HASH)


@pytest.mark.asyncio
async def test_exact_load_holiday_by_row_hash_zero_match(db_session: AsyncSession) -> None:
    """Fake row_hash must raise AuthorityNotFoundError."""
    with pytest.raises(AuthorityNotFoundError):
        await load_holiday_calendar_by_row_hash(db_session, row_hash=_FAKE_HASH)


@pytest.mark.asyncio
async def test_exact_load_weather_by_row_hash_zero_match(db_session: AsyncSession) -> None:
    """Fake row_hash must raise AuthorityNotFoundError."""
    with pytest.raises(AuthorityNotFoundError):
        await load_weather_rule_by_row_hash(db_session, row_hash=_FAKE_HASH)


@pytest.mark.asyncio
async def test_exact_load_run_package_by_row_hash_zero_match(db_session: AsyncSession) -> None:
    """Fake row_hash must raise AuthorityNotFoundError."""
    with pytest.raises(AuthorityNotFoundError):
        await load_run_parameter_package_by_row_hash(db_session, row_hash=_FAKE_HASH)


@pytest.mark.asyncio
async def test_exact_load_inventory_by_row_hash_zero_match(db_session: AsyncSession) -> None:
    """Fake row_hash must raise AuthorityNotFoundError."""
    with pytest.raises(AuthorityNotFoundError):
        await load_initial_inventory_by_row_hash(db_session, row_hash=_FAKE_HASH)


@pytest.mark.asyncio
async def test_exact_load_mature_loss_by_row_hash_zero_match(db_session: AsyncSession) -> None:
    """Fake row_hash must raise AuthorityNotFoundError."""
    with pytest.raises(AuthorityNotFoundError):
        await load_mature_loss_by_row_hash(db_session, row_hash=_FAKE_HASH)


# ══════════════════════════════════════════════════════════════════════════
#  SECTION G – Daily-capacity colon-matrix tests
#  Test pool codes and pool versions that contain colons, verifying the
#  parser handles them unambiguously via the business_version suffix.
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_daily_colon_matrix_code_pool_a_version_v1(db_session: AsyncSession) -> None:
    """code='POOL:A', pool_version='v1' → build key, load, verify same authority_id."""
    pool_code = "POOL:A"
    pool_version = "v1"

    await _ensure_pool_for_daily(db_session, pool_code=pool_code, pool_version=pool_version)
    inp = _daily_input(pool_code=pool_code, pool_version=pool_version)
    create_result = await create_or_load_daily_capacity(db_session, daily_input=inp)
    expected_id = create_result.authority_id

    stable_key = build_daily_capacity_stable_key(inp)
    loaded = await load_daily_capacity_by_business_key(
        db_session,
        stable_key=stable_key,
        business_version=inp.capacity_pool_version,
        revision=inp.daily_capacity_revision,
    )
    assert loaded.authority_id == expected_id


@pytest.mark.asyncio
async def test_daily_colon_matrix_code_pool_version_v_colon_1(db_session: AsyncSession) -> None:
    """code='POOL', pool_version='v:1' → build key, load, verify same authority_id."""
    pool_code = "POOL"
    pool_version = "v:1"

    await _ensure_pool_for_daily(db_session, pool_code=pool_code, pool_version=pool_version)
    inp = _daily_input(pool_code=pool_code, pool_version=pool_version)
    create_result = await create_or_load_daily_capacity(db_session, daily_input=inp)
    expected_id = create_result.authority_id

    stable_key = build_daily_capacity_stable_key(inp)
    loaded = await load_daily_capacity_by_business_key(
        db_session,
        stable_key=stable_key,
        business_version=inp.capacity_pool_version,
        revision=inp.daily_capacity_revision,
    )
    assert loaded.authority_id == expected_id


@pytest.mark.asyncio
async def test_daily_colon_matrix_code_pool_a_version_v_colon_1(db_session: AsyncSession) -> None:
    """code='POOL:A', pool_version='v:1' → both contain colons, verify load."""
    pool_code = "POOL:A"
    pool_version = "v:1"

    await _ensure_pool_for_daily(db_session, pool_code=pool_code, pool_version=pool_version)
    inp = _daily_input(pool_code=pool_code, pool_version=pool_version)
    create_result = await create_or_load_daily_capacity(db_session, daily_input=inp)
    expected_id = create_result.authority_id

    stable_key = build_daily_capacity_stable_key(inp)
    loaded = await load_daily_capacity_by_business_key(
        db_session,
        stable_key=stable_key,
        business_version=inp.capacity_pool_version,
        revision=inp.daily_capacity_revision,
    )
    assert loaded.authority_id == expected_id


@pytest.mark.asyncio
async def test_daily_colon_matrix_code_abc_version_vxy(db_session: AsyncSession) -> None:
    """code='A:B:C', pool_version='v:x:y' → multiple colons in both, verify load."""
    pool_code = "A:B:C"
    pool_version = "v:x:y"

    await _ensure_pool_for_daily(db_session, pool_code=pool_code, pool_version=pool_version)
    inp = _daily_input(pool_code=pool_code, pool_version=pool_version)
    create_result = await create_or_load_daily_capacity(db_session, daily_input=inp)
    expected_id = create_result.authority_id

    stable_key = build_daily_capacity_stable_key(inp)
    loaded = await load_daily_capacity_by_business_key(
        db_session,
        stable_key=stable_key,
        business_version=inp.capacity_pool_version,
        revision=inp.daily_capacity_revision,
    )
    assert loaded.authority_id == expected_id


@pytest.mark.asyncio
async def test_daily_colon_matrix_wrong_business_version_raises(db_session: AsyncSession) -> None:
    """Colon-rich key with wrong business_version → AuthorityNotFoundError."""
    pool_code = "A:B:C"
    pool_version = "v:x:y"

    await _ensure_pool_for_daily(db_session, pool_code=pool_code, pool_version=pool_version)
    inp = _daily_input(pool_code=pool_code, pool_version=pool_version)
    await create_or_load_daily_capacity(db_session, daily_input=inp)

    stable_key = build_daily_capacity_stable_key(inp)
    with pytest.raises(AuthorityNotFoundError):
        await load_daily_capacity_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version="wrong-version",
            revision=inp.daily_capacity_revision,
        )


# ══════════════════════════════════════════════════════════════════════════
#  SECTION H – Canonical alias rejection test
#  The by_business_key loader must reject non-canonical variants of a key
#  (e.g. lowercased or underscored) even though they refer to the same
#  logical entity.
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_exact_load_pool_alias_rejection_lowercased(db_session: AsyncSession) -> None:
    """A pool with code 'POOL-A' must NOT be found via 'pool-a' (lowercase alias)."""
    inp = _pool_input(code="POOL-A")
    create_result = await create_or_load_capacity_pool_definition(db_session, definition_input=inp)

    # Canonical key: capacity-pool:{season}:{factory}:POOL-A
    stable_key_canonical = build_capacity_pool_definition_stable_key(inp)
    # Lowercase alias
    stable_key_alias = stable_key_canonical.replace("POOL-A", "pool-a")

    # Canonical key works
    loaded = await load_capacity_pool_definition_by_business_key(
        db_session,
        stable_key=stable_key_canonical,
        business_version=inp.capacity_pool_version,
        revision=inp.revision,
    )
    assert loaded.parent.authority_id == create_result.parent.authority_id

    # Alias must be rejected
    with pytest.raises(AuthorityNotFoundError):
        await load_capacity_pool_definition_by_business_key(
            db_session,
            stable_key=stable_key_alias,
            business_version=inp.capacity_pool_version,
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_exact_load_pool_alias_rejection_underscored(db_session: AsyncSession) -> None:
    """A pool with code 'POOL-A' must NOT be found via 'POOL_A' (underscore alias)."""
    inp = _pool_input(code="POOL-A")
    create_result = await create_or_load_capacity_pool_definition(db_session, definition_input=inp)

    stable_key_canonical = build_capacity_pool_definition_stable_key(inp)
    # Underscore alias
    stable_key_alias = stable_key_canonical.replace("POOL-A", "POOL_A")

    # Canonical key works
    loaded = await load_capacity_pool_definition_by_business_key(
        db_session,
        stable_key=stable_key_canonical,
        business_version=inp.capacity_pool_version,
        revision=inp.revision,
    )
    assert loaded.parent.authority_id == create_result.parent.authority_id

    # Alias must be rejected
    with pytest.raises(AuthorityNotFoundError):
        await load_capacity_pool_definition_by_business_key(
            db_session,
            stable_key=stable_key_alias,
            business_version=inp.capacity_pool_version,
            revision=inp.revision,
        )
