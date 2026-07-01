"""Integration test configuration: marker-aware isolation and safety guards.

Provides:
- pytest_collection_modifyitems: enforces one isolation marker per integration test
- isolate_postgres_integration_test: marker-aware autouse fixture
- assert_connected_to_safe_test_database: DB identity verification
- _truncate_master_data: destructive cleanup with full guard

Known limitation: Transaction isolation via AsyncSessionMaker.configure()
does not propagate join_transaction_mode to session.begin() in existing
test patterns. All integration tests currently use TRUNCATE cleanup.
The postgres_transactional_isolation context manager and transactional_session
fixture are available for future tests that can use them.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text

# ── Isolation marker names ───────────────────────────────────────────────────

_ISOLATION_MARKERS = (
    "postgres_transactional",
    "postgres_real_commit",
    "postgres_migration",
    "postgres_concurrency",
)

_SPECIAL_MARKERS = frozenset({
    "postgres_real_commit",
    "postgres_migration",
    "postgres_concurrency",
})

# ── Master data tables for cleanup ───────────────────────────────────────────

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


# ── Collection validation ────────────────────────────────────────────────────


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Enforce marker partition: each integration test gets exactly one isolation marker."""
    for item in items:
        marker_names = {m.name for m in item.iter_markers() if m.name in _ISOLATION_MARKERS}

        is_integration = item.get_closest_marker("integration") is not None

        if not is_integration:
            # Non-integration tests must not have special markers
            invalid = marker_names & _SPECIAL_MARKERS
            if invalid:
                raise pytest.UsageError(
                    f"Non-integration test {item.nodeid} has special marker(s): "
                    f"{', '.join(sorted(invalid))}. "
                    f"Special markers are only for integration tests."
                )
            continue

        # Integration test with no isolation marker → add default
        if not marker_names:
            item.add_marker(pytest.mark.postgres_transactional)
            marker_names = {"postgres_transactional"}

        # Must have exactly one isolation marker
        if len(marker_names) > 1:
            raise pytest.UsageError(
                f"Integration test {item.nodeid} has multiple isolation markers: "
                f"{', '.join(sorted(marker_names))}. "
                f"Each test must have exactly one."
            )


# ── Helper functions ─────────────────────────────────────────────────────────


def _postgres_integration_enabled() -> bool:
    return os.getenv("RUN_POSTGRES_INTEGRATION") == "1"


def _get_marker_name(item: pytest.Item) -> str | None:
    """Return the isolation marker name for a test item, or None."""
    for m in item.iter_markers():
        if m.name in _ISOLATION_MARKERS:
            return m.name
    return None


async def _truncate_master_data() -> None:
    """Destructive cleanup: TRUNCATE all master data tables.

    Calls full identity guard before any destructive operation.
    """
    from backend.tests.postgres_test_support import assert_connected_to_safe_test_database

    await assert_connected_to_safe_test_database()

    from backend.app.db.session import AsyncSessionMaker

    async with AsyncSessionMaker() as session:
        await session.execute(
            text(f"TRUNCATE {', '.join(_MASTER_DATA_TABLES)} RESTART IDENTITY CASCADE")
        )
        await session.commit()


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
async def dispose_engine_after_integration_tests() -> AsyncIterator[None]:
    yield
    if _postgres_integration_enabled():
        from backend.app.db.session import dispose_db_engine

        await dispose_db_engine()


@pytest.fixture(autouse=True)
async def isolate_postgres_integration_test(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    """Autouse fixture for all integration tests.

    All integration tests use TRUNCATE cleanup (known limitation:
    transaction isolation via AsyncSessionMaker.configure() does not
    propagate join_transaction_mode to session.begin() in existing
    test patterns).
    """
    if not _postgres_integration_enabled():
        yield
        return

    # Verify database identity for all integration tests
    from backend.tests.postgres_test_support import assert_connected_to_safe_test_database

    await assert_connected_to_safe_test_database()

    # All tests: truncate before and after
    await _truncate_master_data()
    try:
        yield
    finally:
        await _truncate_master_data()
