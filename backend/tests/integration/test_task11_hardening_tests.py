"""Hardening tests for Task 9 authority repository:
wrong-revision, ambiguous row-hash, row/lifecycle/child tamper, canonical alias."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy import text
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
    activate_authority,
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
    AuthorityHashConflictError,
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
    AuthorityFamily,
    AuthorityStatus,
    CapacityInputMode,
    CapacityPoolGrain,
    ForecastQuantile,
    WeatherCombinationMethod,
)
from backend.app.harvest_state.schemas import WeatherFeatureBand, WeatherFeatureRule

pytestmark = pytest.mark.integration

# ── Deterministic fake SHA-256 that passes the row_hash CHECK constraint ──
_FAKE_HASH_A = "a" * 64
_FAKE_HASH_B = "b" * 64

_IDS: dict[str, int] = {"season": 1, "factory": 2, "farm": 10, "subfarm": 20, "variety": 30}
_TZ = "Asia/Shanghai"
_AVAILABLE = date(2026, 1, 1)
_EFF_FROM = date(2026, 1, 1)


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
            # rollback on exit for test isolation


# ── Deterministic test data helpers ──────────────────────────────────────


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
    code: str = "CN",
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
        calendar_code=code,
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
        source_record_key=f"test:holiday:{version}:{revision}:{code}",
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
    code: str = "WEATHER-STD",
) -> Task9WeatherRuleSemanticInput:
    """Build a valid weather-rule semantic input."""
    return Task9WeatherRuleSemanticInput(
        rule_code=code,
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
        source_record_key=f"test:weather:{version}:{revision}:{code}",
        source_version="v1",
    )


def _run_package_input(
    *,
    version: str = "v1",
    revision: int = 1,
    farm_scope: str = "farm-10",
) -> Task9RunParameterPackageSemanticInput:
    """Build a valid run-parameter-package semantic input."""
    return Task9RunParameterPackageSemanticInput(
        season_id=_IDS["season"],
        destination_factory_id=_IDS["factory"],
        farm_scope_key=farm_scope,
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
        source_record_key=f"test:runpkg:{version}:{revision}:{farm_scope}",
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


# ══════════════════════════════════════════════════════════════════════════
#  SECTION I – Wrong revision (7 families)
#  Correct stable_key + correct business_version but revision=999
#  must raise AuthorityNotFoundError for every family.
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_wrong_revision_pool(db_session: AsyncSession) -> None:
    inp = _pool_input()
    await create_or_load_capacity_pool_definition(db_session, definition_input=inp)
    stable_key = build_capacity_pool_definition_stable_key(inp)
    with pytest.raises(AuthorityNotFoundError):
        await load_capacity_pool_definition_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.capacity_pool_version,
            revision=999,
        )


@pytest.mark.asyncio
async def test_wrong_revision_daily(db_session: AsyncSession) -> None:
    """daily-capacity: correct pool + date but daily_capacity_revision=999."""
    pool = _pool_input()
    await create_or_load_capacity_pool_definition(db_session, definition_input=pool)
    inp = _daily_input()
    await create_or_load_daily_capacity(db_session, daily_input=inp)
    stable_key = build_daily_capacity_stable_key(inp)
    with pytest.raises(AuthorityNotFoundError):
        await load_daily_capacity_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.capacity_pool_version,
            revision=999,
        )


@pytest.mark.asyncio
async def test_wrong_revision_holiday(db_session: AsyncSession) -> None:
    inp = _holiday_input()
    await create_or_load_holiday_calendar(db_session, calendar_input=inp)
    stable_key = build_holiday_calendar_stable_key(inp)
    with pytest.raises(AuthorityNotFoundError):
        await load_holiday_calendar_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.calendar_version,
            revision=999,
        )


@pytest.mark.asyncio
async def test_wrong_revision_weather(db_session: AsyncSession) -> None:
    inp = _weather_input()
    await create_or_load_weather_rule(db_session, weather_input=inp)
    stable_key = build_weather_rule_stable_key(inp)
    with pytest.raises(AuthorityNotFoundError):
        await load_weather_rule_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.rule_version,
            revision=999,
        )


@pytest.mark.asyncio
async def test_wrong_revision_run_package(db_session: AsyncSession) -> None:
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
            business_version=inp.package_version,
            revision=999,
        )


@pytest.mark.asyncio
async def test_wrong_revision_inventory(db_session: AsyncSession) -> None:
    inp = _inventory_input()
    await create_or_load_initial_inventory(db_session, inventory_input=inp)
    stable_key = build_initial_inventory_stable_key(inp)
    with pytest.raises(AuthorityNotFoundError):
        await load_initial_inventory_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.snapshot_version,
            revision=999,
        )


@pytest.mark.asyncio
async def test_wrong_revision_mature(db_session: AsyncSession) -> None:
    inp = _mature_loss_input()
    await create_or_load_mature_loss(db_session, loss_input=inp)
    stable_key = build_mature_inventory_loss_stable_key(inp)
    with pytest.raises(AuthorityNotFoundError):
        await load_mature_loss_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.loss_version,
            revision=999,
        )


# ══════════════════════════════════════════════════════════════════════════
#  SECTION II – Ambiguous row-hash (7 families)
#  Insert a second parent row with different business identity but the
#  *same* row_hash.  load_*_by_row_hash must raise
#  AuthorityHashConflictError with reason='ambiguous_row_hash_lookup'
#  and match_count=2.
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ambiguous_row_hash_pool(db_session: AsyncSession) -> None:
    inp = _pool_input()
    create_result = await create_or_load_capacity_pool_definition(db_session, definition_input=inp)
    row_hash = create_result.parent.row_hash
    sid, fid = _IDS["season"], _IDS["factory"]

    # Insert second parent with different version/revision, same row_hash
    await db_session.execute(
        text(
            """
            INSERT INTO task9_capacity_pool_definition (
                season_id, destination_factory_id, capacity_pool_code,
                capacity_pool_version, revision, capacity_pool_grain, capacity_input_mode,
                effective_from, available_at_local_date, status, status_changed_at,
                source_system, source_record_key, source_version, row_hash
            ) VALUES (
                :sid, :fid, 'TEST-POOL',
                'v2', 2, 'FARM', 'LABOR_DERIVED',
                '2026-01-01', '2026-01-01', 'draft', now(),
                'test', 'test:pool:v2:2', 'v1', :rh
            )
            """
        ),
        {"sid": sid, "fid": fid, "rh": row_hash},
    )

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_capacity_pool_definition_by_row_hash(db_session, row_hash=row_hash)
    assert exc_info.value.details["reason"] == "ambiguous_row_hash_lookup"
    assert exc_info.value.details["match_count"] == 2


@pytest.mark.asyncio
async def test_ambiguous_row_hash_daily(db_session: AsyncSession) -> None:
    """daily-capacity: two parents with same row_hash but different business identity."""
    pool = _pool_input()
    await create_or_load_capacity_pool_definition(db_session, definition_input=pool)
    inp = _daily_input()
    create_result = await create_or_load_daily_capacity(db_session, daily_input=inp)
    row_hash = create_result.row_hash
    pid = create_result.authority_id

    # Get the pool definition id for the FK
    pool_result = await db_session.execute(
        text(
            "SELECT capacity_pool_definition_id FROM task9_daily_capacity_authority WHERE id = :id"
        ),
        {"id": pid},
    )
    pool_def_id = pool_result.scalar_one()

    # Insert second daily capacity with different revision, same row_hash
    await db_session.execute(
        text(
            """
            INSERT INTO task9_daily_capacity_authority (
                capacity_pool_definition_id, capacity_date, daily_capacity_revision,
                planned_picker_count, kg_per_person_per_day,
                labor_availability_ratio, operational_efficiency_ratio,
                available_at_local_date, status, status_changed_at,
                source_system, source_record_key, source_version, row_hash
            ) VALUES (
                :pid, '2026-06-15', 2,
                100, 50.5,
                0.85, 0.90,
                '2026-01-01', 'draft', now(),
                'test', 'test:daily:v1:2', 'v1', :rh
            )
            """
        ),
        {"pid": pool_def_id, "rh": row_hash},
    )

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_daily_capacity_by_row_hash(db_session, row_hash=row_hash)
    assert exc_info.value.details["reason"] == "ambiguous_row_hash_lookup"
    assert exc_info.value.details["match_count"] == 2


@pytest.mark.asyncio
async def test_ambiguous_row_hash_holiday(db_session: AsyncSession) -> None:
    inp = _holiday_input()
    create_result = await create_or_load_holiday_calendar(db_session, calendar_input=inp)
    row_hash = create_result.parent.row_hash
    sid = _IDS["season"]

    # Insert second holiday version with different version/revision, same row_hash
    await db_session.execute(
        text(
            """
            INSERT INTO task9_holiday_calendar_version (
                season_id, calendar_code, lifecycle_timezone_name,
                calendar_version, revision, calendar_hash,
                available_at_local_date, status, status_changed_at,
                source_system, source_record_key, source_version, row_hash
            ) VALUES (
                :sid, 'CN', 'Asia/Shanghai',
                'v2', 2, :ch,
                '2026-01-01', 'draft', now(),
                'test', 'test:holiday:v2:2', 'v1', :rh
            )
            """
        ),
        {"sid": sid, "ch": inp.calendar_hash, "rh": row_hash},
    )

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_holiday_calendar_by_row_hash(db_session, row_hash=row_hash)
    assert exc_info.value.details["reason"] == "ambiguous_row_hash_lookup"
    assert exc_info.value.details["match_count"] == 2


@pytest.mark.asyncio
async def test_ambiguous_row_hash_weather(db_session: AsyncSession) -> None:
    inp = _weather_input()
    create_result = await create_or_load_weather_rule(db_session, weather_input=inp)
    row_hash = create_result.row_hash

    # Insert second weather config with different version/revision, same row_hash
    await db_session.execute(
        text(
            """
            INSERT INTO task9_weather_rule_config_version (
                rule_code, lifecycle_timezone_name, rule_version, revision,
                combination_method, minimum_ratio, maximum_ratio,
                required_feature_ids, feature_rules_json, missing_feature_policy,
                config_hash, effective_from,
                available_at_local_date, status, status_changed_at,
                source_system, source_record_key, source_version, row_hash
            ) VALUES (
                'WEATHER-V2', 'Asia/Shanghai', 'v2', 2,
                'MULTIPLY', 0.0, 1.0,
                :feat_ids, :feat_rules,
                'BLOCK',
                :ch,
                '2026-01-01',
                '2026-01-01', 'draft', now(),
                'test', 'test:weather:v2:2', 'v1', :rh
            )
            """
        ),
        {
            "ch": inp.config_hash,
            "rh": row_hash,
            "feat_ids": '["TEMP"]',
            "feat_rules": '[{"feature_id":"TEMP","bands":[{"lower_bound":"0","lower_inclusive":true,"upper_bound":"30","upper_inclusive":false,"multiplier":"1"}]}]',
        },
    )

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_weather_rule_by_row_hash(db_session, row_hash=row_hash)
    assert exc_info.value.details["reason"] == "ambiguous_row_hash_lookup"
    assert exc_info.value.details["match_count"] == 2


@pytest.mark.asyncio
async def test_ambiguous_row_hash_run_package(db_session: AsyncSession) -> None:
    hol_result = await create_or_load_holiday_calendar(db_session, calendar_input=_holiday_input())
    wth_result = await create_or_load_weather_rule(db_session, weather_input=_weather_input())
    inp = _run_package_input()
    create_result = await create_or_load_run_parameter_package(
        db_session,
        package_input=inp,
        holiday_calendar=_holiday_input(),
        weather_rule=_weather_input(),
    )
    row_hash = create_result.row_hash
    sid, fid = _IDS["season"], _IDS["factory"]

    # Insert second package with different version/revision, same row_hash
    await db_session.execute(
        text(
            """
            INSERT INTO task9_run_parameter_package (
                season_id, destination_factory_id, farm_scope_key,
                package_version, revision,
                farm_timezone, destination_factory_timezone,
                harvest_bucket_anchor_local_time, harvest_to_arrival_lag_days,
                holiday_calendar_version_id, weather_rule_config_version_id,
                effective_from, available_at_local_date, status, status_changed_at,
                source_system, source_record_key, source_version, row_hash
            ) VALUES (
                :sid, :fid, 'farm-10',
                'v2', 2,
                'Asia/Shanghai', 'Asia/Shanghai',
                '06:00:00', 1,
                :hol_id, :wth_id,
                '2026-01-01', '2026-01-01', 'draft', now(),
                'test', 'test:runpkg:v2:2', 'v1', :rh
            )
            """
        ),
        {
            "sid": sid,
            "fid": fid,
            "rh": row_hash,
            "hol_id": hol_result.parent.authority_id,
            "wth_id": wth_result.authority_id,
        },
    )

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_run_parameter_package_by_row_hash(db_session, row_hash=row_hash)
    assert exc_info.value.details["reason"] == "ambiguous_row_hash_lookup"
    assert exc_info.value.details["match_count"] == 2


@pytest.mark.asyncio
async def test_ambiguous_row_hash_inventory(db_session: AsyncSession) -> None:
    """initial-inventory: two parents with same row_hash but different business identity."""
    inp = _inventory_input()
    create_result = await create_or_load_initial_inventory(db_session, inventory_input=inp)
    row_hash = create_result.parent.row_hash
    sid, fid = _IDS["season"], _IDS["factory"]

    # Insert second inventory snapshot with different version/revision, same row_hash
    await db_session.execute(
        text(
            """
            INSERT INTO task9_initial_inventory_snapshot (
                season_id, destination_factory_id, opening_state_date,
                snapshot_version, revision,
                initial_opening_mature_inventory_kg,
                available_at_local_date, status, status_changed_at,
                source_system, source_record_key, source_version, row_hash
            ) VALUES (
                :sid, :fid, '2026-01-01',
                'v2', 2,
                300.00,
                '2026-01-01', 'draft', now(),
                'test', 'test:inventory:v2:2', 'v1', :rh
            )
            """
        ),
        {"sid": sid, "fid": fid, "rh": row_hash},
    )

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_initial_inventory_by_row_hash(db_session, row_hash=row_hash)
    assert exc_info.value.details["reason"] == "ambiguous_row_hash_lookup"
    assert exc_info.value.details["match_count"] == 2


@pytest.mark.asyncio
async def test_ambiguous_row_hash_mature(db_session: AsyncSession) -> None:
    """mature-loss: two parents with same row_hash but different business identity."""
    inp = _mature_loss_input()
    create_result = await create_or_load_mature_loss(db_session, loss_input=inp)
    row_hash = create_result.row_hash
    sid, fid = _IDS["season"], _IDS["factory"]

    # Insert second mature loss with different version/revision, same row_hash
    await db_session.execute(
        text(
            """
            INSERT INTO task9_mature_inventory_loss_authority (
                season_id, destination_factory_id, state_date,
                capacity_pool_code, forecast_quantile,
                loss_version, revision,
                mature_inventory_loss_quantity_kg,
                available_at_local_date, status, status_changed_at,
                source_system, source_record_key, source_version, row_hash
            ) VALUES (
                :sid, :fid, '2026-06-15',
                'TEST-POOL', 'P50',
                'v2', 2,
                25.50,
                '2026-01-01', 'draft', now(),
                'test', 'test:mature:v2:2', 'v1', :rh
            )
            """
        ),
        {"sid": sid, "fid": fid, "rh": row_hash},
    )

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_mature_loss_by_row_hash(db_session, row_hash=row_hash)
    assert exc_info.value.details["reason"] == "ambiguous_row_hash_lookup"
    assert exc_info.value.details["match_count"] == 2


# ══════════════════════════════════════════════════════════════════════════
#  SECTION III – Row tamper delegation (7 families)
#  After create, use raw SQL to mutate a hash-covered business field
#  (source_record_key) WITHOUT updating row_hash.  The by-ID loader
#  must detect the mismatch and raise AuthorityHashConflictError.
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_row_tamper_pool(db_session: AsyncSession) -> None:
    """Tamper source_record_key on capacity_pool → hash mismatch."""
    inp = _pool_input()
    create_result = await create_or_load_capacity_pool_definition(db_session, definition_input=inp)
    authority_id = create_result.parent.authority_id
    stable_key = build_capacity_pool_definition_stable_key(inp)

    await db_session.execute(
        text(
            "UPDATE task9_capacity_pool_definition"
            " SET source_record_key = 'TAMPERED' WHERE id = :id"
        ),
        {"id": authority_id},
    )
    db_session.expire_all()

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_capacity_pool_definition_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.capacity_pool_version,
            revision=inp.revision,
        )
    assert exc_info.value.details.get("reason") == "capacity_pool_definition_row_hash_mismatch"


@pytest.mark.asyncio
async def test_row_tamper_daily(db_session: AsyncSession) -> None:
    """Tamper source_record_key on daily_capacity_authority → hash mismatch."""
    pool = _pool_input()
    await create_or_load_capacity_pool_definition(db_session, definition_input=pool)
    inp = _daily_input()
    create_result = await create_or_load_daily_capacity(db_session, daily_input=inp)
    authority_id = create_result.authority_id
    stable_key = build_daily_capacity_stable_key(inp)

    await db_session.execute(
        text(
            "UPDATE task9_daily_capacity_authority"
            " SET source_record_key = 'TAMPERED' WHERE id = :id"
        ),
        {"id": authority_id},
    )
    db_session.expire_all()

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_daily_capacity_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.capacity_pool_version,
            revision=inp.daily_capacity_revision,
        )
    assert exc_info.value.details.get("reason") == "daily_capacity_row_hash_mismatch"


@pytest.mark.asyncio
async def test_row_tamper_holiday(db_session: AsyncSession) -> None:
    """Tamper source_record_key on holiday_calendar_version → hash mismatch."""
    inp = _holiday_input()
    create_result = await create_or_load_holiday_calendar(db_session, calendar_input=inp)
    authority_id = create_result.parent.authority_id
    stable_key = build_holiday_calendar_stable_key(inp)

    await db_session.execute(
        text(
            "UPDATE task9_holiday_calendar_version"
            " SET source_record_key = 'TAMPERED' WHERE id = :id"
        ),
        {"id": authority_id},
    )
    db_session.expire_all()

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_holiday_calendar_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.calendar_version,
            revision=inp.revision,
        )
    assert exc_info.value.details.get("reason") == "holiday_calendar_row_hash_mismatch"


@pytest.mark.asyncio
async def test_row_tamper_weather(db_session: AsyncSession) -> None:
    """Tamper source_record_key on weather_rule_config_version → hash mismatch."""
    inp = _weather_input()
    create_result = await create_or_load_weather_rule(db_session, weather_input=inp)
    authority_id = create_result.authority_id
    stable_key = build_weather_rule_stable_key(inp)

    await db_session.execute(
        text(
            "UPDATE task9_weather_rule_config_version"
            " SET source_record_key = 'TAMPERED' WHERE id = :id"
        ),
        {"id": authority_id},
    )
    db_session.expire_all()

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_weather_rule_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.rule_version,
            revision=inp.revision,
        )
    assert exc_info.value.details.get("reason") == "weather_rule_row_hash_mismatch"


@pytest.mark.asyncio
async def test_row_tamper_run_package(db_session: AsyncSession) -> None:
    """Tamper source_record_key on run_parameter_package → hash mismatch."""
    await create_or_load_holiday_calendar(db_session, calendar_input=_holiday_input())
    await create_or_load_weather_rule(db_session, weather_input=_weather_input())
    inp = _run_package_input()
    create_result = await create_or_load_run_parameter_package(
        db_session,
        package_input=inp,
        holiday_calendar=_holiday_input(),
        weather_rule=_weather_input(),
    )
    authority_id = create_result.authority_id
    stable_key = build_run_parameter_package_stable_key(inp)

    await db_session.execute(
        text(
            "UPDATE task9_run_parameter_package SET source_record_key = 'TAMPERED' WHERE id = :id"
        ),
        {"id": authority_id},
    )
    db_session.expire_all()

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_run_parameter_package_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.package_version,
            revision=inp.revision,
        )
    assert exc_info.value.details.get("reason") == "run_parameter_package_row_hash_mismatch"


@pytest.mark.asyncio
async def test_row_tamper_inventory(db_session: AsyncSession) -> None:
    """Tamper source_record_key on initial_inventory_snapshot → hash mismatch."""
    inp = _inventory_input()
    create_result = await create_or_load_initial_inventory(db_session, inventory_input=inp)
    authority_id = create_result.parent.authority_id
    stable_key = build_initial_inventory_stable_key(inp)

    await db_session.execute(
        text(
            "UPDATE task9_initial_inventory_snapshot"
            " SET source_record_key = 'TAMPERED' WHERE id = :id"
        ),
        {"id": authority_id},
    )
    db_session.expire_all()

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_initial_inventory_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.snapshot_version,
            revision=inp.revision,
        )
    assert exc_info.value.details.get("reason") == "initial_inventory_row_hash_mismatch"


@pytest.mark.asyncio
async def test_row_tamper_mature(db_session: AsyncSession) -> None:
    """Tamper source_record_key on mature_inventory_loss_authority → hash mismatch."""
    inp = _mature_loss_input()
    create_result = await create_or_load_mature_loss(db_session, loss_input=inp)
    authority_id = create_result.authority_id
    stable_key = build_mature_inventory_loss_stable_key(inp)

    await db_session.execute(
        text(
            "UPDATE task9_mature_inventory_loss_authority"
            " SET source_record_key = 'TAMPERED' WHERE id = :id"
        ),
        {"id": authority_id},
    )
    db_session.expire_all()

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_mature_loss_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.loss_version,
            revision=inp.revision,
        )
    assert exc_info.value.details.get("reason") == "mature_inventory_loss_row_hash_mismatch"


# ══════════════════════════════════════════════════════════════════════════
#  SECTION IV – Lifecycle tamper delegation (7 families)
#  Create + activate, then use raw SQL to mutate a lifecycle-event
#  hash-covered field (old_status) WITHOUT recomputing
#  lifecycle_event_hash.  The by-ID loader must detect the mismatch.
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_lifecycle_tamper_pool(db_session: AsyncSession) -> None:
    """Activate pool, tamper lifecycle event old_status → hash mismatch."""
    inp = _pool_input()
    create_result = await create_or_load_capacity_pool_definition(db_session, definition_input=inp)
    authority_id = create_result.parent.authority_id
    stable_key = build_capacity_pool_definition_stable_key(inp)

    activate_result = await activate_authority(
        db_session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_id=authority_id,
        activation_boundary=date(2026, 1, 1),
    )
    event_id = activate_result.lifecycle_event_id

    # Tamper old_status on the activation event (seq=2: draft→active)
    await db_session.execute(
        text("UPDATE task9_authority_lifecycle_event SET old_status = 'active' WHERE id = :id"),
        {"id": event_id},
    )
    db_session.expire_all()

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_capacity_pool_definition_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.capacity_pool_version,
            revision=inp.revision,
        )
    assert exc_info.value.details.get("reason") == "lifecycle_event_hash_mismatch"


@pytest.mark.asyncio
async def test_lifecycle_tamper_daily(db_session: AsyncSession) -> None:
    """Tamper the initial lifecycle event old_status → hash mismatch on reload.

    Note: activate_authority is not used here because the daily-capacity
    stable-key ORM builder requires joined pool-definition columns.
    Instead, we tamper the initial lifecycle event created during
    create_or_load.
    """
    pool = _pool_input()
    await create_or_load_capacity_pool_definition(db_session, definition_input=pool)
    inp = _daily_input()
    create_result = await create_or_load_daily_capacity(db_session, daily_input=inp)
    authority_id = create_result.authority_id
    stable_key = build_daily_capacity_stable_key(inp)

    # Find the initial lifecycle event for this daily capacity
    evt_result = await db_session.execute(
        text(
            "SELECT id FROM task9_authority_lifecycle_event "
            "WHERE authority_family = :family "
            "AND authority_stable_key = :skey "
            "AND authority_business_version = :ver "
            "AND authority_revision = :rev "
            "ORDER BY transition_sequence LIMIT 1"
        ),
        {
            "family": AuthorityFamily.DAILY_CAPACITY.value,
            "skey": stable_key,
            "ver": inp.capacity_pool_version,
            "rev": inp.daily_capacity_revision,
        },
    )
    event_id = evt_result.scalar_one()

    # Tamper old_status on the initial event (seq=1: initial creation)
    await db_session.execute(
        text(
            "UPDATE task9_authority_lifecycle_event "
            "SET old_status = 'active' WHERE id = :id"
        ),
        {"id": event_id},
    )
    db_session.expire_all()

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_daily_capacity_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.capacity_pool_version,
            revision=inp.daily_capacity_revision,
        )
    assert exc_info.value.details.get("reason") == "lifecycle_event_hash_mismatch"


@pytest.mark.asyncio
async def test_lifecycle_tamper_holiday(db_session: AsyncSession) -> None:
    """Activate holiday calendar, tamper lifecycle event old_status."""
    inp = _holiday_input()
    create_result = await create_or_load_holiday_calendar(db_session, calendar_input=inp)
    authority_id = create_result.parent.authority_id
    stable_key = build_holiday_calendar_stable_key(inp)

    activate_result = await activate_authority(
        db_session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=authority_id,
        activation_boundary=date(2026, 1, 1),
    )
    event_id = activate_result.lifecycle_event_id

    await db_session.execute(
        text("UPDATE task9_authority_lifecycle_event SET old_status = 'active' WHERE id = :id"),
        {"id": event_id},
    )
    db_session.expire_all()

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_holiday_calendar_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.calendar_version,
            revision=inp.revision,
        )
    assert exc_info.value.details.get("reason") == "lifecycle_event_hash_mismatch"


@pytest.mark.asyncio
async def test_lifecycle_tamper_weather(db_session: AsyncSession) -> None:
    """Activate weather rule, tamper lifecycle event old_status."""
    inp = _weather_input()
    create_result = await create_or_load_weather_rule(db_session, weather_input=inp)
    authority_id = create_result.authority_id
    stable_key = build_weather_rule_stable_key(inp)

    activate_result = await activate_authority(
        db_session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=authority_id,
        activation_boundary=date(2026, 1, 1),
    )
    event_id = activate_result.lifecycle_event_id

    await db_session.execute(
        text("UPDATE task9_authority_lifecycle_event SET old_status = 'active' WHERE id = :id"),
        {"id": event_id},
    )
    db_session.expire_all()

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_weather_rule_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.rule_version,
            revision=inp.revision,
        )
    assert exc_info.value.details.get("reason") == "lifecycle_event_hash_mismatch"


@pytest.mark.asyncio
async def test_lifecycle_tamper_run_package(db_session: AsyncSession) -> None:
    """Activate run package, tamper lifecycle event old_status."""
    await create_or_load_holiday_calendar(db_session, calendar_input=_holiday_input())
    await create_or_load_weather_rule(db_session, weather_input=_weather_input())
    inp = _run_package_input()
    create_result = await create_or_load_run_parameter_package(
        db_session,
        package_input=inp,
        holiday_calendar=_holiday_input(),
        weather_rule=_weather_input(),
    )
    authority_id = create_result.authority_id
    stable_key = build_run_parameter_package_stable_key(inp)

    activate_result = await activate_authority(
        db_session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        authority_id=authority_id,
        activation_boundary=date(2026, 1, 1),
    )
    event_id = activate_result.lifecycle_event_id

    await db_session.execute(
        text("UPDATE task9_authority_lifecycle_event SET old_status = 'active' WHERE id = :id"),
        {"id": event_id},
    )
    db_session.expire_all()

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_run_parameter_package_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.package_version,
            revision=inp.revision,
        )
    assert exc_info.value.details.get("reason") == "lifecycle_event_hash_mismatch"


@pytest.mark.asyncio
async def test_lifecycle_tamper_inventory(db_session: AsyncSession) -> None:
    """Activate initial inventory, tamper lifecycle event old_status."""
    inp = _inventory_input()
    create_result = await create_or_load_initial_inventory(db_session, inventory_input=inp)
    authority_id = create_result.parent.authority_id
    stable_key = build_initial_inventory_stable_key(inp)

    activate_result = await activate_authority(
        db_session,
        family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
        authority_id=authority_id,
        activation_boundary=date(2026, 1, 1),
    )
    event_id = activate_result.lifecycle_event_id

    await db_session.execute(
        text("UPDATE task9_authority_lifecycle_event SET old_status = 'active' WHERE id = :id"),
        {"id": event_id},
    )
    db_session.expire_all()

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_initial_inventory_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.snapshot_version,
            revision=inp.revision,
        )
    assert exc_info.value.details.get("reason") == "lifecycle_event_hash_mismatch"


@pytest.mark.asyncio
async def test_lifecycle_tamper_mature(db_session: AsyncSession) -> None:
    """Activate mature loss, tamper lifecycle event old_status."""
    inp = _mature_loss_input()
    create_result = await create_or_load_mature_loss(db_session, loss_input=inp)
    authority_id = create_result.authority_id
    stable_key = build_mature_inventory_loss_stable_key(inp)

    activate_result = await activate_authority(
        db_session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_id=authority_id,
        activation_boundary=date(2026, 1, 1),
    )
    event_id = activate_result.lifecycle_event_id

    await db_session.execute(
        text("UPDATE task9_authority_lifecycle_event SET old_status = 'active' WHERE id = :id"),
        {"id": event_id},
    )
    db_session.expire_all()

    with pytest.raises(AuthorityHashConflictError) as exc_info:
        await load_mature_loss_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.loss_version,
            revision=inp.revision,
        )
    assert exc_info.value.details.get("reason") == "lifecycle_event_hash_mismatch"


# ══════════════════════════════════════════════════════════════════════════
#  SECTION V – Bundle child tamper (3 families)
#  For capacity_pool, holiday, initial_inventory: create the bundle,
#  then use raw SQL to mutate a child row's hash-covered field WITHOUT
#  updating the parent or child hash.  The loader must detect the
#  mismatch.
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_child_tamper_pool_member(db_session: AsyncSession) -> None:
    """capacity_pool_member: tamper variety_id → parent hash mismatch on reload.

    Creates a second variety row, updates one member to reference it,
    and verifies the parent hash mismatches on reload.
    """
    inp = _pool_input()
    create_result = await create_or_load_capacity_pool_definition(db_session, definition_input=inp)
    pool_id = create_result.parent.authority_id
    stable_key = build_capacity_pool_definition_stable_key(inp)

    # Create a second variety to use as tamper target (avoids FK violation)
    await db_session.execute(
        text(
            "INSERT INTO dim_variety (code, name) "
            "VALUES ('test-var-tamper', 'Tamper Variety') "
            "ON CONFLICT DO NOTHING"
        ),
    )
    new_var_row = await db_session.execute(
        text("SELECT id FROM dim_variety WHERE code = 'test-var-tamper'"),
    )
    new_var_id = new_var_row.scalar_one()

    # Tamper the member row by changing variety_id (hash-covered, now valid FK)
    await db_session.execute(
        text(
            "UPDATE task9_capacity_pool_member "
            "SET variety_id = :new_var "
            "WHERE capacity_pool_definition_id = :pool_id"
        ),
        {"new_var": new_var_id, "pool_id": pool_id},
    )
    db_session.expire_all()

    with pytest.raises(AuthorityHashConflictError):
        await load_capacity_pool_definition_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.capacity_pool_version,
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_child_tamper_holiday_date(db_session: AsyncSession) -> None:
    """holiday_date: tamper holiday_code → parent hash mismatch on reload."""
    inp = _holiday_input()
    create_result = await create_or_load_holiday_calendar(db_session, calendar_input=inp)
    hol_id = create_result.parent.authority_id
    stable_key = build_holiday_calendar_stable_key(inp)

    # Tamper the date row
    await db_session.execute(
        text(
            "UPDATE task9_holiday_calendar_date "
            "SET holiday_code = 'TAMPERED' "
            "WHERE holiday_calendar_version_id = :hol_id"
        ),
        {"hol_id": hol_id},
    )
    db_session.expire_all()

    with pytest.raises(AuthorityHashConflictError):
        await load_holiday_calendar_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.calendar_version,
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_child_tamper_inventory_cohort(db_session: AsyncSession) -> None:
    """initial_inventory_cohort: tamper stable_cohort_key → parent hash mismatch on reload."""
    inp = _inventory_input()
    create_result = await create_or_load_initial_inventory(db_session, inventory_input=inp)
    inv_id = create_result.parent.authority_id
    stable_key = build_initial_inventory_stable_key(inp)

    # Tamper ONE cohort row (must not update both to avoid unique constraint)
    await db_session.execute(
        text(
            "UPDATE task9_initial_inventory_cohort "
            "SET stable_cohort_key = 'TAMPERED' "
            "WHERE id = ("
            "  SELECT id FROM task9_initial_inventory_cohort "
            "  WHERE initial_inventory_snapshot_id = :inv_id "
            "  LIMIT 1"
            ")"
        ),
        {"inv_id": inv_id},
    )
    db_session.expire_all()

    with pytest.raises(AuthorityHashConflictError):
        await load_initial_inventory_by_business_key(
            db_session,
            stable_key=stable_key,
            business_version=inp.snapshot_version,
            revision=inp.revision,
        )


# ══════════════════════════════════════════════════════════════════════════
#  SECTION VI – Canonical alias rejection (replaces existing Section H)
#  Non-canonical key variants must be rejected by the by_business_key
#  loader even when a valid authority exists.
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_canonical_alias_leading_zero_season(db_session: AsyncSession) -> None:
    """capacity-pool:01:2:POOL-A → rebuilt as capacity-pool:1:2:POOL-A → rejected."""
    inp = _pool_input(code="POOL-A")
    create_result = await create_or_load_capacity_pool_definition(db_session, definition_input=inp)

    canonical_key = build_capacity_pool_definition_stable_key(inp)
    # Canonical works
    loaded = await load_capacity_pool_definition_by_business_key(
        db_session,
        stable_key=canonical_key,
        business_version=inp.capacity_pool_version,
        revision=inp.revision,
    )
    assert loaded.parent.authority_id == create_result.parent.authority_id

    # Leading zero on season_id → int("01") == 1, rebuild drops the zero
    alias_key = f"capacity-pool:0{inp.season_id}:{inp.destination_factory_id}:POOL-A"
    with pytest.raises(AuthorityNotFoundError):
        await load_capacity_pool_definition_by_business_key(
            db_session,
            stable_key=alias_key,
            business_version=inp.capacity_pool_version,
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_canonical_alias_leading_plus_run_package(db_session: AsyncSession) -> None:
    """run-package:+1:2:farm-10 → int("+1")==1, rebuild mismatch → rejected."""
    await create_or_load_holiday_calendar(db_session, calendar_input=_holiday_input())
    await create_or_load_weather_rule(db_session, weather_input=_weather_input())
    inp = _run_package_input()
    create_result = await create_or_load_run_parameter_package(
        db_session,
        package_input=inp,
        holiday_calendar=_holiday_input(),
        weather_rule=_weather_input(),
    )

    canonical_key = build_run_parameter_package_stable_key(inp)
    loaded = await load_run_parameter_package_by_business_key(
        db_session,
        stable_key=canonical_key,
        business_version=inp.package_version,
        revision=inp.revision,
    )
    assert loaded.authority_id == create_result.authority_id

    # Leading plus on season_id
    alias_key = f"run-package:+{inp.season_id}:{inp.destination_factory_id}:farm-10"
    with pytest.raises(AuthorityNotFoundError):
        await load_run_parameter_package_by_business_key(
            db_session,
            stable_key=alias_key,
            business_version=inp.package_version,
            revision=inp.revision,
        )


@pytest.mark.asyncio
async def test_canonical_alias_empty_components(db_session: AsyncSession) -> None:
    """Keys with empty components must raise AuthorityNotFoundError.

    - capacity-pool:1:2:        (empty pool code)
    - run-package:1:2:          (empty scope key)
    - holiday-calendar:1::Asia/Shanghai  (empty calendar code)
    - weather-rule::Asia/Shanghai         (empty rule code)
    """
    # capacity-pool:1:2: → empty pool code
    with pytest.raises(AuthorityNotFoundError):
        await load_capacity_pool_definition_by_business_key(
            db_session,
            stable_key="capacity-pool:1:2:",
            business_version="v1",
            revision=1,
        )

    # run-package:1:2: → empty scope key
    with pytest.raises(AuthorityNotFoundError):
        await load_run_parameter_package_by_business_key(
            db_session,
            stable_key="run-package:1:2:",
            business_version="v1",
            revision=1,
        )

    # holiday-calendar:1::Asia/Shanghai → empty calendar code
    with pytest.raises(AuthorityNotFoundError):
        await load_holiday_calendar_by_business_key(
            db_session,
            stable_key="holiday-calendar:1::Asia/Shanghai",
            business_version="v1",
            revision=1,
        )

    # weather-rule::Asia/Shanghai → empty rule code
    with pytest.raises(AuthorityNotFoundError):
        await load_weather_rule_by_business_key(
            db_session,
            stable_key="weather-rule::Asia/Shanghai",
            business_version="v1",
            revision=1,
        )


@pytest.mark.asyncio
async def test_canonical_alias_extra_segment_initial_inventory(db_session: AsyncSession) -> None:
    """initial-inventory:1:2:garbage:2026-01-01 → extra segment → AuthorityNotFoundError."""
    inp = _inventory_input()
    await create_or_load_initial_inventory(db_session, inventory_input=inp)

    # Canonical key works
    canonical_key = build_initial_inventory_stable_key(inp)
    loaded = await load_initial_inventory_by_business_key(
        db_session,
        stable_key=canonical_key,
        business_version=inp.snapshot_version,
        revision=inp.revision,
    )
    assert loaded.parent.authority_id > 0

    # Extra segment between factory_id and date → non-canonical → rejected
    alias_key = "initial-inventory:1:2:garbage:2026-01-01"
    with pytest.raises(AuthorityNotFoundError):
        await load_initial_inventory_by_business_key(
            db_session,
            stable_key=alias_key,
            business_version=inp.snapshot_version,
            revision=inp.revision,
        )
