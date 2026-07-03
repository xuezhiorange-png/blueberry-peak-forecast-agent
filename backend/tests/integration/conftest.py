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
        await session.execute(text(f"TRUNCATE {', '.join(to_truncate)} RESTART IDENTITY CASCADE"))
        await session.commit()


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
