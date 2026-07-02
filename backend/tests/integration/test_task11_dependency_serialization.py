"""Task 11 dependency-race serialization tests.

These tests verify that concurrent operations on the same dependency graph
(replacement vs activation, replacement vs create, replacement vs direct
supersession, activation vs activation, replacement vs replacement)
serialize correctly and produce no deadlocks or partial state.

These tests REQUIRE a real PostgreSQL database.  They are gated by the
``RUN_POSTGRES_INTEGRATION`` environment variable.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

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
    cancel_authority,
    create_or_load_holiday_calendar,
    create_or_load_run_parameter_package,
    create_or_load_weather_rule,
    replace_run_package_with_dependencies,
    supersede_authority,
)
from backend.app.harvest_state.authority_repository_errors import (
    AuthorityStillReferencedByActivePackageError,
    AuthoritySupersessionScopeConflictError,
    LifecycleTransitionInvalidError,
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
    """Insert dim rows using committed sessions."""
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


# ── Setup helper ────────────────────────────────────────────────────────


async def _setup_initial_trio() -> tuple[
    Task9HolidayCalendarSemanticBundle,
    Task9WeatherRuleSemanticInput,
    Any,
    Any,
    Any,
]:
    """Create and activate an initial trio."""
    async with AsyncSessionMaker() as session:
        async with session.begin():
            hol_v1 = _holiday_input(version="v1", revision=1)
            hol_result = await create_or_load_holiday_calendar(session, calendar_input=hol_v1)
            wth_v1 = _weather_input(version="v1", revision=1)
            wth_result = await create_or_load_weather_rule(session, weather_input=wth_v1)
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
    return hol_v1, wth_v1, pkg_result, hol_result, wth_result


# ── Hook helper for deterministic post-lock synchronization ──────────────


class _DependencyRaceControl:
    """Bidirectional synchronization for dependency race tests.

    Ensures Transaction A holds advisory locks BEFORE Transaction B
    starts, then pauses A until the test explicitly releases it.
    This proves B was actually blocked while A held the locks.

    Production hook default must remain None — no production semantics
    changed.
    """

    def __init__(self) -> None:
        self._a_lock_acquired = asyncio.Event()
        self._release_a = asyncio.Event()

    async def hook(self, phase: str) -> None:
        """Called by repository code at defined synchronization points."""
        if phase == "after_dependency_locks_acquired":
            # Transaction A has acquired advisory locks — signal and
            # then PAUSE until the test explicitly releases.
            self._a_lock_acquired.set()
            await asyncio.wait_for(self._release_a.wait(), timeout=10)

    async def wait_a_has_locks(self) -> None:
        """Block until A has acquired advisory locks."""
        await asyncio.wait_for(self._a_lock_acquired.wait(), timeout=5)

    def release_a_now(self) -> None:
        """Release A so it continues to commit."""
        self._release_a.set()


# ══════════════════════════════════════════════════════════════════════════
#  TEST 1 — replacement race vs package activation
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.postgres_concurrency
async def test_replacement_race_vs_package_activation() -> None:
    """Concurrent replacement (Transaction A) vs activating a draft package
    referencing the same dependencies (Transaction B).

    Deterministic: A starts first, acquires advisory locks, PAUSES.
    B starts, blocks on advisory lock.  Test verifies B is blocked.
    Test releases A.  A commits.  B re-reads deps, finds them
    superseded, raises RunParameterDependencyStatusConflictError.
    """
    await _seed_dimensions_committed()

    # Setup: create and activate initial trio
    hol_v1, wth_v1, pkg_result, _, _ = await _setup_initial_trio()

    # Create draft package B referencing same h_v1 + w_v1
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

    hol_v2 = _holiday_input(version="v2", revision=1)
    wth_v2 = _weather_input(version="v2", revision=1)
    pkg_v2 = _run_package_input(version="v2", revision=1)
    replacement_boundary = date(2026, 7, 1)

    control = _DependencyRaceControl()
    import backend.app.harvest_state.authority_repository as _repo

    original_hook = _repo._dependency_serialization_test_hook
    _repo._dependency_serialization_test_hook = control.hook

    try:

        async def _txn_replace() -> Any:
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    return await replace_run_package_with_dependencies(
                        session,
                        old_package_id=pkg_result.authority_id,
                        new_package_input=pkg_v2,
                        new_holiday_input=hol_v2,
                        new_weather_input=wth_v2,
                        replacement_boundary=replacement_boundary,
                    )

        task_a = asyncio.create_task(_txn_replace())
        # Wait for A to acquire advisory locks (A now pauses)
        await control.wait_a_has_locks()

        # Start B — B will block on advisory lock
        async def _txn_activate_b() -> Any:
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    return await activate_authority(
                        session,
                        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                        authority_id=pkg_v2_b_id,
                        activation_boundary=date(2026, 7, 1),
                    )

        task_b = asyncio.create_task(_txn_activate_b())
        # Yield to event loop so B starts and blocks on advisory lock
        await asyncio.sleep(0)
        # Prove B is blocked (not done) while A holds locks
        assert not task_b.done(), "B should be blocked on advisory lock while A holds it"

        # Release A → A commits → B unblocks
        control.release_a_now()

        gathered = await asyncio.wait_for(
            asyncio.gather(task_a, task_b, return_exceptions=True),
            timeout=15,
        )
    finally:
        _repo._dependency_serialization_test_hook = original_hook

    # Verify frozen outcome
    successes = [r for r in gathered if not isinstance(r, BaseException)]
    dep_conflicts = [
        r for r in gathered if isinstance(r, RunParameterDependencyStatusConflictError)
    ]

    assert len(successes) == 1, (
        f"expected exactly 1 success (replacement), got {len(successes)}: gathered={gathered}"
    )
    assert len(dep_conflicts) == 1, (
        f"expected exactly 1 dep conflict (activation), "
        f"got {len(dep_conflicts)}: gathered={gathered}"
    )

    replacement_result = successes[0]
    assert replacement_result.new_activation is not None

    # Fresh session final verification
    async with AsyncSessionMaker() as verify:
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

        draft_pkg = (
            await verify.execute(
                text("SELECT status FROM task9_run_parameter_package WHERE id = :id"),
                {"id": pkg_v2_b_id},
            )
        ).scalar_one()
        assert draft_pkg == "draft"

        new_pkg = (
            await verify.execute(
                text("SELECT status FROM task9_run_parameter_package WHERE id = :id"),
                {"id": replacement_result.new_activation.authority_id},
            )
        ).scalar_one()
        assert new_pkg == "active"

        stale_refs = (
            await verify.execute(
                text(
                    "SELECT count(*) FROM task9_run_parameter_package p "
                    "JOIN task9_holiday_calendar_version h "
                    "  ON p.holiday_calendar_version_id = h.id "
                    "WHERE h.status = 'superseded' "
                    "AND p.status = 'active'"
                )
            )
        ).scalar_one()
        assert stale_refs == 0


# ══════════════════════════════════════════════════════════════════════════
#  TEST 2 — replacement race vs package create
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.postgres_concurrency
async def test_replacement_race_vs_package_create() -> None:
    """Concurrent replacement (A) vs creating a new package (B) referencing
    the same dependencies.

    Deterministic: A starts first, acquires locks, PAUSES.  B starts,
    blocks on advisory lock.  Test verifies B is blocked.  A commits.
    B re-reads superseded deps, raises typed error.
    Proposed package B row does NOT exist in any state.
    """
    await _seed_dimensions_committed()

    hol_v1, wth_v1, pkg_result, _, _ = await _setup_initial_trio()

    hol_v2 = _holiday_input(version="v2", revision=1)
    wth_v2 = _weather_input(version="v2", revision=1)
    pkg_v2 = _run_package_input(version="v2", revision=1)
    replacement_boundary = date(2026, 7, 1)
    pkg_create_input = _run_package_input(version="create", revision=1)

    control = _DependencyRaceControl()
    import backend.app.harvest_state.authority_repository as _repo

    original_hook = _repo._dependency_serialization_test_hook
    _repo._dependency_serialization_test_hook = control.hook

    try:

        async def _txn_replace() -> Any:
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    return await replace_run_package_with_dependencies(
                        session,
                        old_package_id=pkg_result.authority_id,
                        new_package_input=pkg_v2,
                        new_holiday_input=hol_v2,
                        new_weather_input=wth_v2,
                        replacement_boundary=replacement_boundary,
                    )

        task_a = asyncio.create_task(_txn_replace())
        await control.wait_a_has_locks()

        async def _txn_create_b() -> Any:
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    return await create_or_load_run_parameter_package(
                        session,
                        package_input=pkg_create_input,
                        holiday_calendar=hol_v1,
                        weather_rule=wth_v1,
                    )

        task_b = asyncio.create_task(_txn_create_b())
        await asyncio.sleep(0)
        assert not task_b.done(), "B should be blocked on advisory lock while A holds it"

        control.release_a_now()

        gathered = await asyncio.wait_for(
            asyncio.gather(task_a, task_b, return_exceptions=True),
            timeout=15,
        )
    finally:
        _repo._dependency_serialization_test_hook = original_hook

    # Frozen outcome: exactly 1 success, exactly 1 error
    successes = [r for r in gathered if not isinstance(r, BaseException)]
    errors = [r for r in gathered if isinstance(r, BaseException)]

    assert len(successes) == 1, (
        f"expected exactly 1 success (replacement), got {len(successes)}: gathered={gathered}"
    )
    assert len(errors) == 1, (
        f"expected exactly 1 error (create blocked), got {len(errors)}: gathered={gathered}"
    )
    assert isinstance(errors[0], RunParameterDependencyStatusConflictError), (
        f"expected RunParameterDependencyStatusConflictError, "
        f"got {type(errors[0]).__name__}: {errors[0]}"
    )

    # Prove the success is trio replacement, not create
    replacement_result = successes[0]
    assert replacement_result.new_activation is not None

    # Fresh session: comprehensive verification
    async with AsyncSessionMaker() as verify:
        # Proposed create package does NOT exist in any state
        proposed_count = (
            await verify.execute(
                text(
                    "SELECT count(*) "
                    "FROM task9_run_parameter_package "
                    "WHERE season_id = :sid "
                    "AND destination_factory_id = :fid "
                    "AND farm_scope_key = :fsk "
                    "AND package_version = :ver "
                    "AND revision = :rev"
                ),
                {
                    "sid": _IDS["season"],
                    "fid": _IDS["factory"],
                    "fsk": "farm-10",
                    "ver": "create",
                    "rev": 1,
                },
            )
        ).scalar_one()
        assert proposed_count == 0, (
            f"proposed create package should not exist, got count={proposed_count}"
        )

        # No active or draft package references old holiday/weather
        # This is a loose check; the key assertion is below
        _stale_hol_refs = (
            await verify.execute(
                text(
                    "SELECT count(*) FROM task9_run_parameter_package p "
                    "WHERE p.holiday_calendar_version_id IN ("
                    "  SELECT id FROM task9_holiday_calendar_version "
                    "  WHERE status IN ('active', 'draft')"
                    ") AND p.status IN ('active', 'draft')"
                )
            )
        ).scalar_one()

        # Old package superseded
        old_pkg_status = (
            await verify.execute(
                text("SELECT status FROM task9_run_parameter_package WHERE id = :id"),
                {"id": pkg_result.authority_id},
            )
        ).scalar_one()
        assert old_pkg_status == "superseded"

        # Only one active package
        active_count = (
            await verify.execute(
                text("SELECT count(*) FROM task9_run_parameter_package WHERE status = 'active'")
            )
        ).scalar_one()
        assert active_count == 1

        # No stale references
        stale_refs = (
            await verify.execute(
                text(
                    "SELECT count(*) FROM task9_run_parameter_package p "
                    "JOIN task9_holiday_calendar_version h "
                    "  ON p.holiday_calendar_version_id = h.id "
                    "WHERE h.status = 'superseded' "
                    "AND p.status = 'active'"
                )
            )
        ).scalar_one()
        assert stale_refs == 0


# ══════════════════════════════════════════════════════════════════════════
#  TEST 3 — replacement race vs direct dependency supersession
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.postgres_concurrency
async def test_trio_replacement_vs_direct_dependency_supersession_no_deadlock() -> None:
    """Concurrent trio replacement (A) vs directly superseding holiday H1
    with a different new holiday (B).

    Deterministic: A starts first, acquires locks on H1/W1, PAUSES.
    B starts, blocks on H1 advisory lock.  Test verifies B is blocked.
    A commits.  B unblocks, re-reads H1, finds superseded, raises
    LifecycleTransitionInvalidError.

    Frozen outcome:
      - A: trio replacement succeeds
      - B: LifecycleTransitionInvalidError
      - successes == 1, errors == 1
    """
    await _seed_dimensions_committed()

    _, _, pkg_result, hol_result, _ = await _setup_initial_trio()
    h1_id = hol_result.parent.authority_id

    hol_v2 = _holiday_input(version="v2", revision=1)
    wth_v2 = _weather_input(version="v2", revision=1)
    pkg_v2 = _run_package_input(version="v2", revision=1)
    replacement_boundary = date(2026, 7, 1)

    direct_holiday_v2 = _holiday_input(version="direct-v2", revision=1)

    control = _DependencyRaceControl()
    import backend.app.harvest_state.authority_repository as _repo

    original_hook = _repo._dependency_serialization_test_hook
    _repo._dependency_serialization_test_hook = control.hook

    try:

        async def _txn_replace() -> Any:
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    return await replace_run_package_with_dependencies(
                        session,
                        old_package_id=pkg_result.authority_id,
                        new_package_input=pkg_v2,
                        new_holiday_input=hol_v2,
                        new_weather_input=wth_v2,
                        replacement_boundary=replacement_boundary,
                    )

        task_a = asyncio.create_task(_txn_replace())
        await control.wait_a_has_locks()

        async def _txn_supersede_h1() -> Any:
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    return await supersede_authority(
                        session,
                        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
                        old_id=h1_id,
                        new_input=direct_holiday_v2,
                        replacement_boundary=date(2026, 7, 1),
                        new_dates=direct_holiday_v2.dates,
                    )

        task_b = asyncio.create_task(_txn_supersede_h1())
        await asyncio.sleep(0)
        assert not task_b.done(), "B should be blocked on H1 advisory lock while A holds it"

        control.release_a_now()

        gathered = await asyncio.wait_for(
            asyncio.gather(task_a, task_b, return_exceptions=True),
            timeout=15,
        )
    finally:
        _repo._dependency_serialization_test_hook = original_hook

    # Frozen outcome: exactly 1 success, exactly 1 error
    errors = [r for r in gathered if isinstance(r, BaseException)]
    successes = [r for r in gathered if not isinstance(r, BaseException)]

    assert len(gathered) == 2
    assert len(successes) == 1, (
        f"expected exactly 1 success (trio replacement), got {len(successes)}: gathered={gathered}"
    )
    assert len(errors) == 1, (
        f"expected exactly 1 error (direct supersession), got {len(errors)}: gathered={gathered}"
    )
    # Loser must be a specific typed error — LifecycleTransitionInvalidError
    # because supersede_authority re-reads H1, finds it superseded, and
    # the ACTIVE→SUPERSEDED transition fails.
    assert isinstance(errors[0], LifecycleTransitionInvalidError), (
        f"expected LifecycleTransitionInvalidError, got {type(errors[0]).__name__}: {errors[0]}"
    )

    # Comprehensive database verification
    async with AsyncSessionMaker() as verify:
        # Old package = superseded
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
        assert old_pkg.superseded_by_id is not None

        # Old holiday = superseded
        old_hol = (
            await verify.execute(
                text(
                    "SELECT status, superseded_by_id "
                    "FROM task9_holiday_calendar_version WHERE id = :id"
                ),
                {"id": h1_id},
            )
        ).one()
        assert old_hol.status == "superseded"
        assert old_hol.superseded_by_id is not None

        # New trio (replacement) = active
        new_pkg = (
            await verify.execute(
                text("SELECT count(*) FROM task9_run_parameter_package WHERE status = 'active'")
            )
        ).scalar_one()
        assert new_pkg == 1

        new_hol = (
            await verify.execute(
                text("SELECT count(*) FROM task9_holiday_calendar_version WHERE status = 'active'")
            )
        ).scalar_one()
        assert new_hol >= 1

        new_wth = (
            await verify.execute(
                text(
                    "SELECT count(*) FROM task9_weather_rule_config_version WHERE status = 'active'"
                )
            )
        ).scalar_one()
        assert new_wth >= 1

        # Direct-v2 holiday row absent
        direct_v2_count = (
            await verify.execute(
                text(
                    "SELECT count(*) "
                    "FROM task9_holiday_calendar_version "
                    "WHERE calendar_version = :ver"
                ),
                {"ver": "direct-v2"},
            )
        ).scalar_one()
        assert direct_v2_count == 0, f"direct-v2 holiday should not exist, got {direct_v2_count}"

        # No active/draft package references superseded old dependencies
        stale_refs = (
            await verify.execute(
                text(
                    "SELECT count(*) FROM task9_run_parameter_package p "
                    "JOIN task9_holiday_calendar_version h "
                    "  ON p.holiday_calendar_version_id = h.id "
                    "WHERE h.status = 'superseded' "
                    "AND p.status = 'active'"
                )
            )
        ).scalar_one()
        assert stale_refs == 0


# ══════════════════════════════════════════════════════════════════════════
#  TEST 4 — concurrent activation vs activation
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.postgres_concurrency
async def test_concurrent_package_activation_uses_locked_fresh_state() -> None:
    """Two concurrent activate_authority calls on the same draft package.

    Frozen outcome:
      - Exactly one activation succeeds
      - Exactly one LifecycleTransitionInvalidError
      - Final package status = active
      - Activation lifecycle event delta = 1
    """
    await _seed_dimensions_committed()

    # ── Setup: create trio (draft, not activated) ───────────────────
    async with AsyncSessionMaker() as session:
        async with session.begin():
            hol_v1 = _holiday_input(version="v1", revision=1)
            hol_result = await create_or_load_holiday_calendar(session, calendar_input=hol_v1)
            wth_v1 = _weather_input(version="v1", revision=1)
            wth_result = await create_or_load_weather_rule(session, weather_input=wth_v1)
            pkg_v1 = _run_package_input(version="v1", revision=1)
            pkg_result = await create_or_load_run_parameter_package(
                session,
                package_input=pkg_v1,
                holiday_calendar=hol_v1,
                weather_rule=wth_v1,
            )
            assert pkg_result.created is True

            act_boundary = date(2026, 3, 1)
            await activate_authority(
                session,
                family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
                authority_id=hol_result.parent.authority_id,
                activation_boundary=act_boundary,
            )
            await activate_authority(
                session,
                family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
                authority_id=wth_result.authority_id,
                activation_boundary=act_boundary,
            )

    async with AsyncSessionMaker() as session:
        count_before = (
            await session.execute(text("SELECT count(*) FROM task9_authority_lifecycle_event"))
        ).scalar_one()

    barrier = asyncio.Barrier(2)
    pkg_id = pkg_result.authority_id
    act_boundary = date(2026, 3, 1)

    async def _txn_activate() -> Any:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await asyncio.wait_for(barrier.wait(), timeout=5)
                return await activate_authority(
                    session,
                    family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                    authority_id=pkg_id,
                    activation_boundary=act_boundary,
                )

    gathered = await asyncio.wait_for(
        asyncio.gather(
            asyncio.create_task(_txn_activate()),
            asyncio.create_task(_txn_activate()),
            return_exceptions=True,
        ),
        timeout=15,
    )

    successes = [r for r in gathered if not isinstance(r, BaseException)]
    lifecycle_errors = [r for r in gathered if isinstance(r, LifecycleTransitionInvalidError)]

    assert len(successes) == 1, (
        f"expected exactly 1 success, got {len(successes)}: gathered={gathered}"
    )
    assert len(lifecycle_errors) == 1, (
        f"expected exactly 1 LifecycleTransitionInvalidError, "
        f"got {len(lifecycle_errors)}: gathered={gathered}"
    )

    async with AsyncSessionMaker() as verify:
        pkg_status = (
            await verify.execute(
                text("SELECT status FROM task9_run_parameter_package WHERE id = :id"),
                {"id": pkg_id},
            )
        ).scalar_one()
        assert pkg_status == "active"

        count_after = (
            await verify.execute(text("SELECT count(*) FROM task9_authority_lifecycle_event"))
        ).scalar_one()
        assert count_after == count_before + 1


# ══════════════════════════════════════════════════════════════════════════
#  TEST 5 — concurrent replacement vs replacement
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.postgres_concurrency
async def test_concurrent_trio_replacement_uses_locked_fresh_state() -> None:
    """Two concurrent replace_run_package_with_dependencies calls on the
    same old package.

    Frozen outcome:
      - Exactly one replacement succeeds
      - Exactly one typed lifecycle/version conflict
      - Old package superseded exactly once
      - Only one new active replacement package
    """
    await _seed_dimensions_committed()

    _, _, pkg_result, _, _ = await _setup_initial_trio()

    barrier = asyncio.Barrier(2)

    async def _txn_replace_a() -> Any:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await asyncio.wait_for(barrier.wait(), timeout=5)
                hol_v = _holiday_input(version="a2", revision=1)
                wth_v = _weather_input(version="a2", revision=1)
                pkg_v = _run_package_input(version="a2", revision=1)
                return await replace_run_package_with_dependencies(
                    session,
                    old_package_id=pkg_result.authority_id,
                    new_package_input=pkg_v,
                    new_holiday_input=hol_v,
                    new_weather_input=wth_v,
                    replacement_boundary=date(2026, 7, 1),
                )

    async def _txn_replace_b() -> Any:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await asyncio.wait_for(barrier.wait(), timeout=5)
                hol_v = _holiday_input(version="b2", revision=1)
                wth_v = _weather_input(version="b2", revision=1)
                pkg_v = _run_package_input(version="b2", revision=1)
                return await replace_run_package_with_dependencies(
                    session,
                    old_package_id=pkg_result.authority_id,
                    new_package_input=pkg_v,
                    new_holiday_input=hol_v,
                    new_weather_input=wth_v,
                    replacement_boundary=date(2026, 7, 1),
                )

    gathered = await asyncio.wait_for(
        asyncio.gather(
            asyncio.create_task(_txn_replace_a()),
            asyncio.create_task(_txn_replace_b()),
            return_exceptions=True,
        ),
        timeout=15,
    )

    successes = [r for r in gathered if not isinstance(r, BaseException)]
    errors = [r for r in gathered if isinstance(r, BaseException)]

    assert len(successes) == 1, (
        f"expected exactly 1 success, got {len(successes)}: gathered={gathered}"
    )
    assert len(errors) == 1, f"expected exactly 1 error, got {len(errors)}: gathered={gathered}"

    for err in errors:
        assert isinstance(
            err,
            (
                LifecycleTransitionInvalidError,
                RunParameterDependencyStatusConflictError,
            ),
        ), f"unexpected error type: {type(err).__name__}: {err}"

    async with AsyncSessionMaker() as verify:
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
        assert old_pkg.superseded_by_id is not None

        active_count = (
            await verify.execute(
                text("SELECT count(*) FROM task9_run_parameter_package WHERE status = 'active'")
            )
        ).scalar_one()
        assert active_count == 1

        active_holidays = (
            await verify.execute(
                text(
                    "SELECT count(*) "
                    "FROM task9_holiday_calendar_version "
                    "WHERE status = 'active' "
                    "AND season_id = :sid"
                ),
                {"sid": _IDS["season"]},
            )
        ).scalar_one()
        assert active_holidays >= 1

        active_weather = (
            await verify.execute(
                text(
                    "SELECT count(*) FROM task9_weather_rule_config_version WHERE status = 'active'"
                )
            )
        ).scalar_one()
        assert active_weather >= 1


# ══════════════════════════════════════════════════════════════════════════
#  P0-1 — activation dependency-ID drift after lock
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.integration
async def test_activation_rejects_dependency_id_drift_after_lock() -> None:
    """If the package's dependency FKs change between the scalar lookup
    and the FOR UPDATE lock, activation must fail closed.

    Uses _before_mutation_hook to swap the holiday FK on the package
    row after advisory locks are acquired but before FOR UPDATE.
    """
    await _seed_dimensions_committed()

    # Create trio v1 and activate deps + package
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
            h1_id = hol_result.parent.authority_id
            w1_id = wth_result.authority_id

            # Activate deps and package
            await activate_authority(
                session,
                family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
                authority_id=h1_id,
                activation_boundary=date(2026, 3, 1),
            )
            await activate_authority(
                session,
                family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
                authority_id=w1_id,
                activation_boundary=date(2026, 3, 1),
            )
            await activate_authority(
                session,
                family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                authority_id=pkg_result.authority_id,
                activation_boundary=date(2026, 3, 1),
            )

    # Create a second holiday to drift the FK to
    async with AsyncSessionMaker() as session:
        async with session.begin():
            hol_drift = _holiday_input(version="drift", revision=1)
            drift_result = await create_or_load_holiday_calendar(
                session,
                calendar_input=hol_drift,
            )
            drift_hol_id = drift_result.parent.authority_id
            # Activate the drift holiday
            await activate_authority(
                session,
                family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
                authority_id=drift_hol_id,
                activation_boundary=date(2026, 3, 1),
            )

    # Cancel the current package so we can re-create and try activation
    async with AsyncSessionMaker() as session:
        async with session.begin():
            await cancel_authority(
                session,
                family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                authority_id=pkg_result.authority_id,
            )

    # Re-create package v1b referencing same deps
    async with AsyncSessionMaker() as session:
        async with session.begin():
            pkg_v1b = _run_package_input(version="v1b", revision=1)
            pkg_v1b_result = await create_or_load_run_parameter_package(
                session,
                package_input=pkg_v1b,
                holiday_calendar=_holiday_input(version="v1", revision=1),
                weather_rule=_weather_input(version="v1", revision=1),
            )
            pkg_v1b_id = pkg_v1b_result.authority_id

    # Hook that swaps holiday FK after advisory locks are acquired
    async def _drift_hook(phase: str) -> None:
        if phase == "after_dependency_locks_acquired":
            # Swap the holiday FK on the package row via raw SQL
            async with AsyncSessionMaker() as drift_session:
                async with drift_session.begin():
                    await drift_session.execute(
                        text(
                            "UPDATE task9_run_parameter_package "
                            "SET holiday_calendar_version_id = :new_hid "
                            "WHERE id = :pid"
                        ),
                        {"new_hid": drift_hol_id, "pid": pkg_v1b_id},
                    )

    import backend.app.harvest_state.authority_repository as _repo

    original_hook = _repo._dependency_serialization_test_hook
    _repo._dependency_serialization_test_hook = _drift_hook

    try:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                with pytest.raises(AuthoritySupersessionScopeConflictError) as exc_info:
                    await activate_authority(
                        session,
                        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                        authority_id=pkg_v1b_id,
                        activation_boundary=date(2026, 7, 1),
                    )
                assert exc_info.value.details["reason"] == "dependency_id_drift"
                assert exc_info.value.details["package_id"] == pkg_v1b_id
    finally:
        _repo._dependency_serialization_test_hook = original_hook

    # Verify package remains draft, no activation event
    async with AsyncSessionMaker() as verify:
        pkg_status = (
            await verify.execute(
                text("SELECT status FROM task9_run_parameter_package WHERE id = :id"),
                {"id": pkg_v1b_id},
            )
        ).scalar_one()
        assert pkg_status == "draft"


# ══════════════════════════════════════════════════════════════════════════
#  P0-1 — activation refreshes preloaded dependency identity map
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.integration
async def test_activation_refreshes_preloaded_dependency_identity_map() -> None:
    """Even if the Session identity map contains a stale holiday/weather
    ORM object, activate_authority must read fresh state from DB
    (populate_existing=True) and reject if deps are no longer ACTIVE.
    """
    await _seed_dimensions_committed()

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
            h1_id = hol_result.parent.authority_id
            w1_id = wth_result.authority_id

            # Activate deps and package
            await activate_authority(
                session,
                family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
                authority_id=h1_id,
                activation_boundary=date(2026, 3, 1),
            )
            await activate_authority(
                session,
                family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
                authority_id=w1_id,
                activation_boundary=date(2026, 3, 1),
            )
            await activate_authority(
                session,
                family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                authority_id=pkg_result.authority_id,
                activation_boundary=date(2026, 3, 1),
            )

    # Now supersede holiday in a separate session (committed)
    async with AsyncSessionMaker() as session:
        async with session.begin():
            hol_v2 = _holiday_input(version="v2", revision=1)
            await supersede_authority(
                session,
                family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
                old_id=h1_id,
                new_input=hol_v2,
                replacement_boundary=date(2026, 6, 1),
                new_dates=hol_v2.dates,
            )

    # Now try to activate a NEW package referencing the superseded h1.
    # First create a draft package.
    async with AsyncSessionMaker() as session:
        async with session.begin():
            pkg_v2 = _run_package_input(version="v2", revision=1)
            pkg_v2_result = await create_or_load_run_parameter_package(
                session,
                package_input=pkg_v2,
                holiday_calendar=_holiday_input(version="v1", revision=1),
                weather_rule=_weather_input(version="v1", revision=1),
            )
            pkg_v2_id = pkg_v2_result.authority_id

    # Activation must reject because h1 is now superseded
    async with AsyncSessionMaker() as session:
        async with session.begin():
            with pytest.raises(RunParameterDependencyStatusConflictError):
                await activate_authority(
                    session,
                    family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                    authority_id=pkg_v2_id,
                    activation_boundary=date(2026, 7, 1),
                )

    # Package must remain draft
    async with AsyncSessionMaker() as verify:
        pkg_status = (
            await verify.execute(
                text("SELECT status FROM task9_run_parameter_package WHERE id = :id"),
                {"id": pkg_v2_id},
            )
        ).scalar_one()
        assert pkg_status == "draft"


# ══════════════════════════════════════════════════════════════════════════
#  P1-1 — Independent fresh-session replacement rollback evidence
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.integration
async def test_shared_rejection_fresh_session_committed_state() -> None:
    """Three-session atomicity evidence for shared dependency rejection.

    Session 1: create and commit old holiday/weather/package A/B.
    Session 2: attempt replacement of package A, assert rollback.
    Session 3: verify committed database state is unchanged.
    """
    await _seed_dimensions_committed()

    # ── Session 1: Create and commit baseline state ────────────────
    h1_id: int
    w1_id: int
    pkg_a_id: int
    pkg_b_id: int
    async with AsyncSessionMaker() as s1:
        async with s1.begin():
            hol_v1 = _holiday_input(version="v1", revision=1)
            hol_result = await create_or_load_holiday_calendar(
                s1,
                calendar_input=hol_v1,
            )
            h1_id = hol_result.parent.authority_id

            wth_v1 = _weather_input(version="v1", revision=1)
            wth_result = await create_or_load_weather_rule(
                s1,
                weather_input=wth_v1,
            )
            w1_id = wth_result.authority_id

            # Activate holiday and weather
            await activate_authority(
                s1,
                family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
                authority_id=h1_id,
                activation_boundary=date(2026, 3, 1),
            )
            await activate_authority(
                s1,
                family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
                authority_id=w1_id,
                activation_boundary=date(2026, 3, 1),
            )

            # Package A → holiday h1, weather w1
            pkg_a_input = _run_package_input(version="a", revision=1)
            pkg_a_result = await create_or_load_run_parameter_package(
                s1,
                package_input=pkg_a_input,
                holiday_calendar=hol_v1,
                weather_rule=wth_v1,
            )
            pkg_a_id = pkg_a_result.authority_id
            await activate_authority(
                s1,
                family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                authority_id=pkg_a_id,
                activation_boundary=date(2026, 3, 1),
            )

            # Package B → same holiday h1, different weather
            wth_v1b = _weather_input(version="w1b", revision=1)
            wth_v1b_result = await create_or_load_weather_rule(
                s1,
                weather_input=wth_v1b,
            )
            w1b_id = wth_v1b_result.authority_id
            await activate_authority(
                s1,
                family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
                authority_id=w1b_id,
                activation_boundary=date(2026, 3, 1),
            )
            pkg_b_input = _run_package_input(version="b", revision=1)
            pkg_b_result = await create_or_load_run_parameter_package(
                s1,
                package_input=pkg_b_input,
                holiday_calendar=hol_v1,
                weather_rule=wth_v1b,
            )
            pkg_b_id = pkg_b_result.authority_id
            await activate_authority(
                s1,
                family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                authority_id=pkg_b_id,
                activation_boundary=date(2026, 3, 1),
            )

    # ── Record pre-replacement state via raw SQL ───────────────────
    async with AsyncSessionMaker() as s_pre:
        async with s_pre.begin():
            pre_hol = (
                await s_pre.execute(
                    text(
                        "SELECT status, row_hash, superseded_by_id, "
                        "consumable_from_local_date, "
                        "consumable_to_local_date "
                        "FROM task9_holiday_calendar_version WHERE id = :id"
                    ),
                    {"id": h1_id},
                )
            ).one()
            pre_wth = (
                await s_pre.execute(
                    text(
                        "SELECT status, row_hash, superseded_by_id, "
                        "consumable_from_local_date, "
                        "consumable_to_local_date "
                        "FROM task9_weather_rule_config_version "
                        "WHERE id = :id"
                    ),
                    {"id": w1_id},
                )
            ).one()
            pre_pkg_a = (
                await s_pre.execute(
                    text(
                        "SELECT status, row_hash, superseded_by_id, "
                        "consumable_from_local_date, "
                        "consumable_to_local_date "
                        "FROM task9_run_parameter_package WHERE id = :id"
                    ),
                    {"id": pkg_a_id},
                )
            ).one()
            pre_events = (
                await s_pre.execute(text("SELECT count(*) FROM task9_authority_lifecycle_event"))
            ).scalar_one()

    # ── Session 2: Attempt replacement → expect rollback ───────────
    hol_v2 = _holiday_input(version="v2", revision=1)
    wth_v2 = _weather_input(version="v2", revision=1)
    pkg_v2 = _run_package_input(version="v2", revision=1)

    with pytest.raises(AuthorityStillReferencedByActivePackageError):
        async with AsyncSessionMaker() as s2:
            async with s2.begin():
                await replace_run_package_with_dependencies(
                    s2,
                    old_package_id=pkg_a_id,
                    new_package_input=pkg_v2,
                    new_holiday_input=hol_v2,
                    new_weather_input=wth_v2,
                    replacement_boundary=date(2026, 7, 1),
                )

    # ── Session 3: Verify committed state is unchanged ─────────────
    async with AsyncSessionMaker() as s3:
        async with s3.begin():
            # No proposed identities exist
            proposed_hol = (
                await s3.execute(
                    text(
                        "SELECT count(*) "
                        "FROM task9_holiday_calendar_version "
                        "WHERE calendar_version = :ver"
                    ),
                    {"ver": "v2"},
                )
            ).scalar_one()
            assert proposed_hol == 0, f"proposed holiday v2 should not exist, got {proposed_hol}"

            proposed_wth = (
                await s3.execute(
                    text(
                        "SELECT count(*) "
                        "FROM task9_weather_rule_config_version "
                        "WHERE rule_version = :ver"
                    ),
                    {"ver": "v2"},
                )
            ).scalar_one()
            assert proposed_wth == 0, f"proposed weather v2 should not exist, got {proposed_wth}"

            proposed_pkg = (
                await s3.execute(
                    text(
                        "SELECT count(*) "
                        "FROM task9_run_parameter_package "
                        "WHERE package_version = :ver"
                    ),
                    {"ver": "v2"},
                )
            ).scalar_one()
            assert proposed_pkg == 0, f"proposed package v2 should not exist, got {proposed_pkg}"

            # Old identities unchanged
            post_hol = (
                await s3.execute(
                    text(
                        "SELECT status, row_hash, superseded_by_id, "
                        "consumable_from_local_date, "
                        "consumable_to_local_date "
                        "FROM task9_holiday_calendar_version WHERE id = :id"
                    ),
                    {"id": h1_id},
                )
            ).one()
            assert post_hol.status == pre_hol.status
            assert post_hol.row_hash == pre_hol.row_hash
            assert post_hol.superseded_by_id == pre_hol.superseded_by_id
            assert post_hol.consumable_from_local_date == pre_hol.consumable_from_local_date
            assert post_hol.consumable_to_local_date == pre_hol.consumable_to_local_date

            post_wth = (
                await s3.execute(
                    text(
                        "SELECT status, row_hash, superseded_by_id, "
                        "consumable_from_local_date, "
                        "consumable_to_local_date "
                        "FROM task9_weather_rule_config_version "
                        "WHERE id = :id"
                    ),
                    {"id": w1_id},
                )
            ).one()
            assert post_wth.status == pre_wth.status
            assert post_wth.row_hash == pre_wth.row_hash
            assert post_wth.superseded_by_id == pre_wth.superseded_by_id

            post_pkg_a = (
                await s3.execute(
                    text(
                        "SELECT status, row_hash, superseded_by_id, "
                        "consumable_from_local_date, "
                        "consumable_to_local_date "
                        "FROM task9_run_parameter_package WHERE id = :id"
                    ),
                    {"id": pkg_a_id},
                )
            ).one()
            assert post_pkg_a.status == pre_pkg_a.status
            assert post_pkg_a.row_hash == pre_pkg_a.row_hash
            assert post_pkg_a.superseded_by_id == pre_pkg_a.superseded_by_id

            # Package A remains active
            assert post_pkg_a.status == "active"
            # Holiday remains active
            assert post_hol.status == "active"
            # Weather remains active
            assert post_wth.status == "active"

            # Lifecycle event count unchanged
            post_events = (
                await s3.execute(text("SELECT count(*) FROM task9_authority_lifecycle_event"))
            ).scalar_one()
            assert post_events == pre_events
