import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text

from backend.app.db.session import AsyncSessionMaker, dispose_db_engine

_MASTER_DATA_TABLES = (
    "task9_authority_lifecycle_event",
    "task9_mature_inventory_loss_authority",
    "task9_initial_inventory_cohort",
    "task9_initial_inventory_snapshot",
    "task9_run_parameter_package",
    "task9_weather_rule_config_version",
    "task9_holiday_calendar_date",
    "task9_holiday_calendar_version",
    "task9_daily_capacity_authority",
    "task9_capacity_pool_member",
    "task9_capacity_pool_definition",
    "rolling_backtest_orchestration_snapshot",
    "rolling_backtest_stage_event",
    "rolling_backtest_dag_snapshot",
    "rolling_backtest_availability_audit",
    "rolling_backtest_resolved_input",
    "rolling_backtest_attempt",
    "rolling_backtest_node",
    "rolling_backtest_run",
    "residual_model_execution_attempt",
    "residual_model_prediction_row",
    "residual_model_prediction_run",
    "residual_model_artifact",
    "residual_model_manifest_row",
    "residual_model_training_run",
    "harvest_state_replay_source_visibility_audit",
    "harvest_state_future_arrival_row",
    "harvest_state_cohort_transition_row",
    "harvest_state_daily_member_row",
    "harvest_state_daily_pool_row",
    "harvest_state_run",
    "maturity_daily_prediction",
    "maturity_forecast_run",
    "maturity_model_artifact",
    "maturity_model_run",
    "weather_feature_run",
    "base_temperature_search_run",
    "location_weather_mapping",
    "weather_import_run",
    "weather_daily_observation",
    "weather_source_location",
    "production_plan_import_run",
    "farm_season_variety_plan",
    "parameter_inference_result",
    "parameter_inference_run",
    "minimal_forecast_task",
    "parameter_observation",
    "parameter_library_version",
    "location_reference",
    "climate_zone_import_run",
    "dim_agro_climate_zone",
    "baseline_backtest_result",
    "baseline_backtest_run",
    "factory_season_peak_metric",
    "fact_receipt_daily",
    "analytics_build_run",
    "fact_receipt_raw",
    "ingest_file",
    "dim_holiday",
    "dim_subfarm",
    "dim_grade",
    "dim_variety",
    "dim_farm",
    "dim_factory",
    "dim_season",
)


def _postgres_integration_enabled() -> bool:
    return os.getenv("RUN_POSTGRES_INTEGRATION") == "1"


def _ensure_test_database() -> None:
    if os.getenv("APP_ENV") != "test":
        raise RuntimeError("PostgreSQL integration cleanup requires APP_ENV=test")


async def _truncate_master_data() -> None:
    _ensure_test_database()
    async with AsyncSessionMaker() as session:
        # Filter to tables that actually exist in the database
        result = await session.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        existing = {row[0] for row in result.fetchall()}
        to_truncate = [t for t in _MASTER_DATA_TABLES if t in existing]
        if not to_truncate:
            return
        # Best-effort: terminate any leftover backend connections that are
        # stuck in `idle in transaction` (or its aborted variant). These
        # are the canonical symptom of a fixture helper that opened a
        # session via `async with AsyncSessionMaker()`, executed SELECTs,
        # and exited the `async with` block without first committing or
        # rolling back the autobegun transaction. The leftover
        # transaction keeps row-level locks (including any
        # `SELECT ... FOR UPDATE` taken via `with_for_update()` inside
        # `_run_stage` / `create_execution_attempt`) alive even after the
        # session's ORM is closed, and the next test's autouse
        # `TRUNCATE ... RESTART IDENTITY CASCADE` would wait for those
        # locks until `lock_timeout` fires (or hang indefinitely when no
        # timeout is set).
        #
        # Terminating the leaked backend forces PG to roll back its open
        # transaction and release every lock it held, so the TRUNCATE
        # that follows can proceed immediately. The
        # `pid <> pg_backend_pid()` filter keeps the truncate session
        # itself alive; the `datname = current_database()` filter keeps
        # this destructive operation scoped to the test database. The
        # `try/except` wrapper allows the operation to silently succeed
        # on databases without the `pg_stat_activity` permissions
        # (e.g. locked-down managed PG instances) — the lock_timeout
        # belt below still provides the safety net.
        try:
            await session.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE state IN ("
                    "    'idle in transaction', "
                    "    'idle in transaction (aborted)'"
                    ") "
                    "AND datname = current_database() "
                    "AND pid <> pg_backend_pid()"
                )
            )
        except Exception:
            pass
        # Use a short statement-level timeout so the truncate fails
        # fast if any prior transaction still holds an ACCESS EXCLUSIVE
        # lock on the master data tables (e.g. from a leaked
        # connection that could not be terminated above). Without this,
        # a leaked lock would hang pytest indefinitely.
        try:
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
        except Exception:
            pass
        try:
            await session.execute(
                text(f"TRUNCATE {', '.join(to_truncate)} RESTART IDENTITY CASCADE")
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest.fixture(scope="session", autouse=True)
async def dispose_engine_after_integration_tests() -> AsyncIterator[None]:
    yield
    if _postgres_integration_enabled():
        await dispose_db_engine()


@pytest.fixture(autouse=True)
async def isolate_master_data_tables() -> AsyncIterator[None]:
    if not _postgres_integration_enabled():
        yield
        return

    await _truncate_master_data()
    try:
        yield
    finally:
        await _truncate_master_data()


# ---------------------------------------------------------------------------
# Slice 2 — opt-in transactional isolation fixture
# ---------------------------------------------------------------------------
#
# This fixture is **opt-in**: a test must declare it as a parameter to
# use it. The autouse `isolate_master_data_tables` TRUNCATE fixture
# above continues to run for every integration test, including tests
# that opt into `transactional_pg_session`. The TRUNCATE behavior is
# unchanged in this slice; removing it is Slice 5 territory.
#
# The fixture is gated on:
#   - `_postgres_integration_enabled()` — RUN_POSTGRES_INTEGRATION=1
#   - the Slice 1 dev-DB safeguard — assert_safe_postgres_test_identity
# When either gate fails, the fixture yields a no-op context that
# lets the test body run without acquiring a real connection. This
# matches the pre-Slice-2 behavior for the same gate conditions and
# keeps the rest of the integration suite green on hosts that do not
# run PG.


@pytest.fixture
async def transactional_pg_session() -> AsyncIterator[object]:
    """Opt-in transaction + savepoint + rollback session for PG tests.

    Yields a SQLAlchemy :class:`AsyncSession` that is bound to a
    single outer transaction on a dedicated connection. The fixture
    rolls the outer transaction back at teardown so every write is
    reverted, including writes that passed through
    ``session.commit()``.

    When PG is not enabled (``RUN_POSTGRES_INTEGRATION!=1``) the
    fixture emits a pytest skip. When the Slice 1 dev-DB safeguard
    rejects the test identity, the fixture ALSO emits a pytest skip
    rather than a fixture setup error. The safeguard remains
    fail-closed: it is still invoked and still raises; the fixture
    converts that raise into a pytest skip so the test body never
    runs in an unsafe profile and never opens a connection. Tests
    that need a real connection should be marked with
    ``@pytest.mark.skipif(not _postgres_integration_enabled(), ...)``
    (or the equivalent pattern used elsewhere in this directory).
    """
    from backend.tests.integration._txn_isolation import (
        transactional_async_session,
    )
    from backend.tests.postgres_test_support import (
        assert_safe_postgres_test_identity,
    )

    if not _postgres_integration_enabled():
        pytest.skip("transactional_pg_session requires RUN_POSTGRES_INTEGRATION=1")
        return  # unreachable, but keeps type checkers happy

    # Slice 1 dev-DB safeguard: must run BEFORE the engine connects,
    # so an unsafe DATABASE_URL / port / APP_ENV fails fast without
    # touching the wire. The safeguard itself remains fail-closed and
    # raises ValueError on unsafe inputs; the fixture converts that
    # raise into a pytest skip so the test body does not run in an
    # unsafe profile and the engine is never asked to connect. This
    # is the CI dev-DB design: ``postgres-domain-1`` (and related
    # shards) intentionally inject a dev ``POSTGRES_DB`` so that any
    # test taking the new fixture under that shard is correctly
    # skipped rather than counted as a job failure.
    try:
        assert_safe_postgres_test_identity(env=None)
    except ValueError as exc:
        pytest.skip(
            "transactional_pg_session skipped: "
            "Slice 1 dev-DB safeguard rejected current profile "
            f"({exc})"
        )
        return  # unreachable, but keeps type checkers happy

    # Import the module-level AsyncEngine directly to avoid the
    # ``async_sessionmaker().get_bind()`` typing ambiguity (the latter
    # returns ``Engine | Connection`` from SQLAlchemy's sync base
    # class, not the ``AsyncEngine`` we need here).
    from backend.app.db.session import engine as _pg_engine

    async with transactional_async_session(_pg_engine) as session:
        yield session
