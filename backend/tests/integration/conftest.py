import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text

from backend.app.db.session import AsyncSessionMaker, dispose_db_engine

_MASTER_DATA_TABLES = (
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
        await session.execute(
            text(f"TRUNCATE {', '.join(_MASTER_DATA_TABLES)} RESTART IDENTITY CASCADE")
        )
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
