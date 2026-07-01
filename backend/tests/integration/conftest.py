"""Integration test configuration: database safety guard and isolation fixtures.

Provides:
- assert_safe_postgres_test_configuration(): typed, testable safety check
- assert_connected_to_safe_test_database(): actual DB identity verification
- Transactional isolation fixture for postgres_transactional tests
- Cleanup fixture for postgres_real_commit / postgres_concurrency tests
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.app.core.config import get_settings

# ── Safety constants ─────────────────────────────────────────────────────────

ALLOWED_TEST_DATABASES = {"blueberry_peak_test"}
FORBIDDEN_DATABASES = {"blueberry_peak", "postgres", "template0", "template1"}

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


# ── Safety guard functions ───────────────────────────────────────────────────


def assert_safe_postgres_test_configuration() -> None:
    """Validate environment variables before any destructive DB operation.

    Raises RuntimeError with a clear message if any condition fails.
    Never includes passwords in error messages.
    """
    app_env = os.getenv("APP_ENV")
    if app_env != "test":
        raise RuntimeError(f"Refusing to run: APP_ENV={app_env!r} (expected 'test')")

    db_name = os.getenv("POSTGRES_DB")
    if not db_name:
        raise RuntimeError("Refusing to run: POSTGRES_DB is not set")

    if db_name in FORBIDDEN_DATABASES:
        raise RuntimeError(f"Refusing to run: POSTGRES_DB={db_name!r} is a protected database name")

    if db_name not in ALLOWED_TEST_DATABASES:
        raise RuntimeError(
            f"Refusing to run: POSTGRES_DB={db_name!r} is not in allowed test databases"
        )


async def assert_connected_to_safe_test_database() -> None:
    """Verify the actual database connection matches expected test configuration.

    Checks:
    1. APP_ENV == "test"
    2. POSTGRES_DB == "blueberry_peak_test"
    3. SELECT current_database() returns "blueberry_peak_test"
    4. All three sources agree

    Raises RuntimeError if any check fails.
    """
    assert_safe_postgres_test_configuration()

    settings = get_settings()
    configured_db = settings.postgres_db

    env_db = os.getenv("POSTGRES_DB", "")

    engine = create_async_engine(settings.async_database_url)
    try:
        async with engine.connect() as conn:
            actual_db = await conn.execute(text("SELECT current_database()"))
            actual_db_name = actual_db.scalar_one()
    finally:
        await engine.dispose()

    if configured_db != env_db:
        raise RuntimeError(
            f"Database mismatch: configured URL has {configured_db!r}, env has {env_db!r}"
        )

    if configured_db != actual_db_name:
        raise RuntimeError(
            f"Database mismatch: configured {configured_db!r}, "
            f"actual connected to {actual_db_name!r}"
        )

    if actual_db_name not in ALLOWED_TEST_DATABASES:
        raise RuntimeError(f"Connected to {actual_db_name!r} which is not an allowed test database")


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _postgres_integration_enabled() -> bool:
    return os.getenv("RUN_POSTGRES_INTEGRATION") == "1"


def _ensure_test_database() -> None:
    if os.getenv("APP_ENV") != "test":
        raise RuntimeError("PostgreSQL integration cleanup requires APP_ENV=test")


async def _truncate_master_data() -> None:
    _ensure_test_database()
    from backend.app.db.session import AsyncSessionMaker

    async with AsyncSessionMaker() as session:
        await session.execute(
            text(f"TRUNCATE {', '.join(_MASTER_DATA_TABLES)} RESTART IDENTITY CASCADE")
        )
        await session.commit()


@pytest.fixture(scope="session", autouse=True)
async def dispose_engine_after_integration_tests() -> AsyncIterator[None]:
    yield
    if _postgres_integration_enabled():
        from backend.app.db.session import dispose_db_engine

        await dispose_db_engine()


@pytest.fixture(autouse=True)
async def verify_test_database_identity() -> None:
    """Fail-closed: verify we are connected to the safe test database."""
    if not _postgres_integration_enabled():
        return
    await assert_connected_to_safe_test_database()


@pytest.fixture(autouse=True)
async def isolate_master_data_tables() -> AsyncIterator[None]:
    """Clean up test data before and after each integration test.

    Used for postgres_real_commit and postgres_concurrency tests where
    transaction rollback isolation is not possible.
    """
    if not _postgres_integration_enabled():
        yield
        return

    await _truncate_master_data()
    try:
        yield
    finally:
        await _truncate_master_data()


@pytest.fixture
async def transactional_session() -> AsyncIterator[AsyncSession]:
    """Provide a session isolated by an outer transaction/savepoint.

    The outer transaction is never committed — it is rolled back on teardown,
    ensuring no test data escapes to the database.

    Application code calling session.commit() will create a savepoint instead,
    so data is visible within the test but not outside.
    """
    from backend.app.db.session import engine

    async with engine.connect() as conn:
        txn = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await txn.rollback()
