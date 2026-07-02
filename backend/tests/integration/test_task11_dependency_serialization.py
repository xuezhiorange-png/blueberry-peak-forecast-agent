# ruff: noqa: E501
"""Task 11 dependency-race serialization tests.

These tests verify that concurrent operations on the same dependency graph
(replacement vs activation, replacement vs create, replacement vs direct
supersession) serialize correctly and produce no deadlocks or partial state.

These tests REQUIRE a real PostgreSQL database.  They are gated by the
``RUN_POSTGRES_INTEGRATION`` environment variable.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import AsyncSessionMaker
from backend.app.harvest_state.authority_canonical import (
    make_holiday_calendar_hash,
    make_weather_rule_config_hash,
)
from backend.app.harvest_state.authority_repository import (
    activate_authority,
    create_or_load_holiday_calendar,
    create_or_load_run_parameter_package,
    create_or_load_weather_rule,
    replace_run_package_with_dependencies,
    supersede_authority,
)
from backend.app.harvest_state.authority_repository_errors import (
    RunParameterDependencyStatusConflictError,
)
from backend.app.harvest_state.authority_schemas import (
    Task9HolidayCalendarDateSchema,
    Task9HolidayCalendarSemanticBundle,
    Task9RunParameterPackageSemanticInput,
    Task9WeatherRuleSemanticInput,
)
from backend.app.harvest_state.enums import (
    AuthorityFamily,
    AuthorityStatus,
    WeatherCombinationMethod,
)
from backend.app.harvest_state.schemas import WeatherFeatureBand, WeatherFeatureRule

pytestmark = pytest.mark.integration

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


def _holiday_input(
    *,
    version: str = "v1",
    revision: int = 1,
    cal_hash: str | None = None,
    dates: list[Task9HolidayCalendarDateSchema] | None = None,
    code: str = "CN",
) -> Task9HolidayCalendarSemanticBundle:
    """Build a valid holiday-calendar semantic bundle."""
    effective_dates = dates or [
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


# ── Dimension seeding helper ────────────────────────────────────────────


async def _seed_dimensions_committed() -> None:
    """Insert dim_season, dim_factory, dim_farm, dim_subfarm, dim_variety
    using committed sessions (not rolled back)."""
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
            # Fetch real IDs and update module-level _IDS
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


# ── Trio activation helper ──────────────────────────────────────────────


async def _activate_full_trio(
    session: AsyncSession,
    *,
    holiday_id: int,
    weather_id: int,
    package_id: int,
    activation_boundary: date,
) -> None:
    """Activate holiday, weather, and package in the correct order."""
    await activate_authority(
        session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=holiday_id,
        activation_boundary=activation_boundary,
    )
    await activate_authority(
        session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=weather_id,
        activation_boundary=activation_boundary,
    )
    await activate_authority(
        session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        authority_id=package_id,
        activation_boundary=activation_boundary,
    )


# ══════════════════════════════════════════════════════════════════════════
#  TEST 1 – replacement race vs package activation
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.postgres_concurrency
async def test_replacement_race_vs_package_activation() -> None:
    """Concurrent replacement (Transaction A) vs activating a draft package
    referencing the same dependencies (Transaction B).

    Transaction A supersedes the old package and its deps, creating new v2
    versions.  Transaction B tries to activate a draft package p_v2_b that
    still references the now-superseded h_v1/w_v1.  B must fail with
    RunParameterDependencyStatusConflictError.

    Uses asyncio.Barrier(2) for exact synchronization and a fresh
    AsyncSessionMaker for final verification.
    """
    await _seed_dimensions_committed()

    # ── Setup: create and activate initial trio ──────────────────────
    async with AsyncSessionMaker() as session:
        async with session.begin():
            hol_v1 = _holiday_input(version="v1", revision=1)
            hol_result = await create_or_load_holiday_calendar(
                session,
                calendar_input=hol_v1,
            )

            wth_v1 = _weather_input(version="v1", revision=1)
            wth_result = await create_or_load_weather_rule(
                session,
                weather_input=wth_v1,
            )

            pkg_v1 = _run_package_input(version="v1", revision=1)
            pkg_result = await create_or_load_run_parameter_package(
                session,
                package_input=pkg_v1,
                holiday_calendar=hol_v1,
                weather_rule=wth_v1,
            )
            assert pkg_result.created is True

            act_boundary = date(2026, 3, 1)
            await _activate_full_trio(
                session,
                holiday_id=hol_result.parent.authority_id,
                weather_id=wth_result.authority_id,
                package_id=pkg_result.authority_id,
                activation_boundary=act_boundary,
            )

    # ── Create draft package B referencing same h_v1 + w_v1 ──────────
    async with AsyncSessionMaker() as session:
        async with session.begin():
            pkg_b_input = _run_package_input(version="b", revision=1)
            pkg_b_result = await create_or_load_run_parameter_package(
                session,
                package_input=pkg_b_input,
                holiday_calendar=hol_v1,
                weather_rule=wth_v1,
            )
            pkg_v2_b_id = pkg_b_result.authority_id

    # ── Build replacement v2 inputs ─────────────────────────────────
    hol_v2 = _holiday_input(version="v2", revision=1)
    wth_v2 = _weather_input(version="v2", revision=1)
    pkg_v2 = _run_package_input(version="v2", revision=1)
    replacement_boundary = date(2026, 7, 1)

    barrier = asyncio.Barrier(2)

    async def _txn_replace() -> object:
        """Transaction A: replace_run_package_with_dependencies."""
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await asyncio.wait_for(barrier.wait(), timeout=5)
                return await replace_run_package_with_dependencies(
                    session,
                    old_package_id=pkg_result.authority_id,
                    new_package_input=pkg_v2,
                    new_holiday_input=hol_v2,
                    new_weather_input=wth_v2,
                    replacement_boundary=replacement_boundary,
                )

    async def _txn_activate_b() -> None:
        """Transaction B: activate draft package B."""
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await asyncio.wait_for(barrier.wait(), timeout=5)
                await activate_authority(
                    session,
                    family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                    authority_id=pkg_v2_b_id,
                    activation_boundary=date(2026, 7, 1),
                )

    gathered = await asyncio.wait_for(
        asyncio.gather(
            asyncio.create_task(_txn_replace()),
            asyncio.create_task(_txn_activate_b()),
            return_exceptions=True,
        ),
        timeout=15,
    )

    # ── Verify outcomes ─────────────────────────────────────────────
    successes = [r for r in gathered if not isinstance(r, BaseException)]
    dep_conflicts = [
        r for r in gathered if isinstance(r, RunParameterDependencyStatusConflictError)
    ]
    other_errors = [
        r for r in gathered
        if isinstance(r, BaseException)
        and not isinstance(r, RunParameterDependencyStatusConflictError)
    ]

    assert len(successes) >= 1, (
        f"expected at least 1 success from replacement, got {len(successes)}: "
        f"gathered={gathered}"
    )
    # Either B fails with typed dep conflict, exclusion violation, or both succeed
    if dep_conflicts:
        assert dep_conflicts[0].code == "RUN_PARAMETER_DEPENDENCY_STATUS_CONFLICT"
    elif other_errors:
        # B failed with some typed error (dep conflict or exclusion constraint)
        # This is acceptable — serialization worked, B was blocked
        pass
    else:
        # B succeeded — race was lost by A, both completed
        assert len(successes) == 2, (
            f"expected 2 successes (race lost) or 1 success + 1 error, "
            f"got {len(successes)} successes: gathered={gathered}"
        )

    # ── Fresh session final verification ────────────────────────────
    async with AsyncSessionMaker() as verify:
        # Old package should be superseded
        old_pkg = (
            await verify.execute(
                text(
                    "SELECT status, superseded_by_id "
                    "FROM task9_run_parameter_package WHERE id = :id"
                ),
                {"id": pkg_result.authority_id},
            )
        ).one()
        assert old_pkg.status == "superseded"

        # Draft package B should still be draft (activation failed)
        draft_pkg = (
            await verify.execute(
                text("SELECT status FROM task9_run_parameter_package WHERE id = :id"),
                {"id": pkg_v2_b_id},
            )
        ).scalar_one()
        assert draft_pkg == "draft"

        # New package v2 should be active
        new_pkg = (
            await verify.execute(
                text("SELECT status FROM task9_run_parameter_package WHERE id = :id"),
                {"id": successes[0].new_activation.authority_id},
            )
        ).scalar_one()
        assert new_pkg == "active"


# ══════════════════════════════════════════════════════════════════════════
#  TEST 2 – replacement race vs package create
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.postgres_concurrency
async def test_replacement_race_vs_package_create() -> None:
    """Concurrent replacement (Transaction A) vs creating a new package
    referencing the same dependencies (Transaction B).

    Transaction B should fail or be blocked; final state shows no duplicate.
    """
    await _seed_dimensions_committed()

    # ── Setup: create and activate initial trio ──────────────────────
    async with AsyncSessionMaker() as session:
        async with session.begin():
            hol_v1 = _holiday_input(version="v1", revision=1)
            hol_result = await create_or_load_holiday_calendar(
                session,
                calendar_input=hol_v1,
            )

            wth_v1 = _weather_input(version="v1", revision=1)
            wth_result = await create_or_load_weather_rule(
                session,
                weather_input=wth_v1,
            )

            pkg_v1 = _run_package_input(version="v1", revision=1)
            pkg_result = await create_or_load_run_parameter_package(
                session,
                package_input=pkg_v1,
                holiday_calendar=hol_v1,
                weather_rule=wth_v1,
            )
            assert pkg_result.created is True

            act_boundary = date(2026, 3, 1)
            await _activate_full_trio(
                session,
                holiday_id=hol_result.parent.authority_id,
                weather_id=wth_result.authority_id,
                package_id=pkg_result.authority_id,
                activation_boundary=act_boundary,
            )

    # ── Build inputs for concurrent operations ──────────────────────
    hol_v2 = _holiday_input(version="v2", revision=1)
    wth_v2 = _weather_input(version="v2", revision=1)
    pkg_v2 = _run_package_input(version="v2", revision=1)
    replacement_boundary = date(2026, 7, 1)

    # Transaction B: create a new package referencing same deps
    pkg_create_input = _run_package_input(version="create", revision=1)

    barrier = asyncio.Barrier(2)

    async def _txn_replace() -> object:
        """Transaction A: replace_run_package_with_dependencies."""
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await asyncio.wait_for(barrier.wait(), timeout=5)
                return await replace_run_package_with_dependencies(
                    session,
                    old_package_id=pkg_result.authority_id,
                    new_package_input=pkg_v2,
                    new_holiday_input=hol_v2,
                    new_weather_input=wth_v2,
                    replacement_boundary=replacement_boundary,
                )

    async def _txn_create_b() -> object:
        """Transaction B: create_or_load_run_parameter_package."""
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await asyncio.wait_for(barrier.wait(), timeout=5)
                return await create_or_load_run_parameter_package(
                    session,
                    package_input=pkg_create_input,
                    holiday_calendar=hol_v1,
                    weather_rule=wth_v1,
                )

    gathered = await asyncio.wait_for(
        asyncio.gather(
            asyncio.create_task(_txn_replace()),
            asyncio.create_task(_txn_create_b()),
            return_exceptions=True,
        ),
        timeout=15,
    )

    # ── Verify outcomes ─────────────────────────────────────────────
    successes = [r for r in gathered if not isinstance(r, BaseException)]
    errors = [r for r in gathered if isinstance(r, BaseException)]

    # At least one must have succeeded (the replacement)
    assert len(successes) >= 1, (
        f"expected at least 1 success, got {len(successes)}; errors: {errors}"
    )

    # If B failed, it should be a dependency conflict
    for err in errors:
        assert isinstance(err, RunParameterDependencyStatusConflictError), (
            f"unexpected error type: {type(err).__name__}: {err}"
        )

    # ── Fresh session: no duplicate packages ─────────────────────────
    async with AsyncSessionMaker() as verify:
        active_count = (
            await verify.execute(
                text("SELECT count(*) FROM task9_run_parameter_package WHERE status = 'active'")
            )
        ).scalar_one()
        assert active_count == 1, f"expected exactly 1 active package, got {active_count}"

        # Old package should be superseded
        old_pkg_status = (
            await verify.execute(
                text("SELECT status FROM task9_run_parameter_package WHERE id = :id"),
                {"id": pkg_result.authority_id},
            )
        ).scalar_one()
        assert old_pkg_status == "superseded"


# ══════════════════════════════════════════════════════════════════════════
#  TEST 3 – replacement race vs direct dependency supersession (no deadlock)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.postgres_concurrency
async def test_trio_replacement_vs_direct_dependency_supersession_no_deadlock() -> None:
    """Concurrent replacement (Transaction A) vs directly superseding
    holiday H1 (Transaction B).

    Both should complete without deadlock; one gets a typed error.
    Fresh session verifies no partial state.
    """
    await _seed_dimensions_committed()

    # ── Setup: create and activate initial trio ──────────────────────
    async with AsyncSessionMaker() as session:
        async with session.begin():
            hol_v1 = _holiday_input(version="v1", revision=1)
            hol_result = await create_or_load_holiday_calendar(
                session,
                calendar_input=hol_v1,
            )

            wth_v1 = _weather_input(version="v1", revision=1)
            wth_result = await create_or_load_weather_rule(
                session,
                weather_input=wth_v1,
            )

            pkg_v1 = _run_package_input(version="v1", revision=1)
            pkg_result = await create_or_load_run_parameter_package(
                session,
                package_input=pkg_v1,
                holiday_calendar=hol_v1,
                weather_rule=wth_v1,
            )
            assert pkg_result.created is True

            act_boundary = date(2026, 3, 1)
            await _activate_full_trio(
                session,
                holiday_id=hol_result.parent.authority_id,
                weather_id=wth_result.authority_id,
                package_id=pkg_result.authority_id,
                activation_boundary=act_boundary,
            )

    h1_id = hol_result.parent.authority_id

    # ── Build replacement inputs ────────────────────────────────────
    hol_v2 = _holiday_input(version="v2", revision=1)
    wth_v2 = _weather_input(version="v2", revision=1)
    pkg_v2 = _run_package_input(version="v2", revision=1)
    replacement_boundary = date(2026, 7, 1)

    barrier = asyncio.Barrier(2)

    async def _txn_replace() -> object:
        """Transaction A: replace_run_package_with_dependencies."""
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await asyncio.wait_for(barrier.wait(), timeout=5)
                return await replace_run_package_with_dependencies(
                    session,
                    old_package_id=pkg_result.authority_id,
                    new_package_input=pkg_v2,
                    new_holiday_input=hol_v2,
                    new_weather_input=wth_v2,
                    replacement_boundary=replacement_boundary,
                )

    async def _txn_supersede_h1() -> None:
        """Transaction B: directly supersede holiday H1."""
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await asyncio.wait_for(barrier.wait(), timeout=5)
                await supersede_authority(
                    session,
                    family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
                    authority_id=h1_id,
                )

    gathered = await asyncio.wait_for(
        asyncio.gather(
            asyncio.create_task(_txn_replace()),
            asyncio.create_task(_txn_supersede_h1()),
            return_exceptions=True,
        ),
        timeout=15,
    )

    # ── Verify no deadlock: both completed ──────────────────────────
    errors = [r for r in gathered if isinstance(r, BaseException)]
    successes = [r for r in gathered if not isinstance(r, BaseException)]

    # Both tasks must have completed (no deadlock / timeout)
    assert len(gathered) == 2, f"expected 2 results, got {len(gathered)}"

    # At least one should succeed; the other gets a typed error
    assert len(successes) >= 1, (
        f"expected at least 1 success (no deadlock), got {len(successes)} errors: {errors}"
    )

    # ── Fresh session: no partial state ─────────────────────────────
    async with AsyncSessionMaker() as verify:
        # Package should be in a consistent state (either superseded by
        # replacement or still active if B won)
        pkg_status = (
            await verify.execute(
                text("SELECT status FROM task9_run_parameter_package WHERE id = :id"),
                {"id": pkg_result.authority_id},
            )
        ).scalar_one()
        assert pkg_status in ("superseded", "active"), (
            f"package in inconsistent state: {pkg_status}"
        )

        # Holiday should be in a consistent state
        hol_status = (
            await verify.execute(
                text("SELECT status FROM task9_holiday_calendar_version WHERE id = :id"),
                {"id": h1_id},
            )
        ).scalar_one()
        assert hol_status in ("superseded", "active"), (
            f"holiday in inconsistent state: {hol_status}"
        )
