"""Real PostgreSQL round trip and immutable constraints; isolated test profile only."""

import importlib
import os
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.app.area_yield.run_application import execute_area_forecast_run
from backend.app.area_yield.run_persistence import AreaForecastRunRepository
from backend.app.core.config import get_settings
from backend.app.models.area_forecast import AreaForecastDailyRow, AreaForecastRun
from backend.tests.area_yield.test_run_persistence import authority, bounded  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.usefixtures("authority"),
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_INTEGRATION") != "1", reason="PostgreSQL opt-in"),
]


@pytest.fixture
async def pg_engine():
    assert os.getenv("APP_ENV") == "test"
    engine = create_async_engine(get_settings().async_database_url)
    # Isolated schema, never truncate or mutate other task data.
    schema = "area_run_test_" + uuid4().hex
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    await engine.dispose()
    engine = create_async_engine(
        get_settings().async_database_url, connect_args={"server_settings": {"search_path": schema}}
    )
    async with engine.begin() as conn:

        def install(c):
            with Operations.context(MigrationContext.configure(c)):
                importlib.import_module(
                    "backend.alembic.versions.0034_area_forecast_runs"
                ).upgrade()

        await conn.run_sync(install)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


async def test_postgres_fresh_session_idempotency_immutability(pg_engine):
    async with AsyncSession(pg_engine, expire_on_commit=False) as s:
        async with s.begin():
            first = await execute_area_forecast_run(s, bounded())
    async with AsyncSession(pg_engine) as s:
        async with s.begin():
            loaded = await AreaForecastRunRepository(s).get(first.run.run_id)
            assert loaded.result == first.result and len(loaded.result.daily_forecast) == 207
            again = await execute_area_forecast_run(s, bounded())
            assert again.reused_existing_run and again.run.run_id == first.run.run_id
        for table in ("area_forecast_run", "area_forecast_daily_row"):
            with pytest.raises(DBAPIError):
                async with s.begin():
                    await s.execute(text(f"UPDATE {table} SET id=id"))
        with pytest.raises(IntegrityError):
            async with s.begin():
                row = await s.scalar(select(AreaForecastDailyRow).limit(1))
                s.add(
                    AreaForecastDailyRow(
                        run_id=row.run_id,
                        row_index=row.row_index,
                        date=row.date,
                        predicted_kg=row.predicted_kg,
                        share=row.share,
                        share_text=row.share_text,
                    )
                )
                await s.flush()


@pytest.mark.migration
async def test_postgres_migration_down_upgrade(pg_engine):
    module = importlib.import_module("backend.alembic.versions.0034_area_forecast_runs")
    async with pg_engine.begin() as conn:

        def cycle(c):
            with Operations.context(MigrationContext.configure(c)):
                module.downgrade()
                assert c.execute(text("SELECT to_regclass('area_forecast_run')")).scalar() is None
                module.upgrade()
                assert c.execute(text("SELECT to_regclass('area_forecast_daily_row')")).scalar()

        await conn.run_sync(cycle)


async def test_postgres_caller_rollback(pg_engine):
    async with AsyncSession(pg_engine) as s:
        await execute_area_forecast_run(s, bounded())
        await s.rollback()
    async with AsyncSession(pg_engine) as s:
        assert await s.scalar(select(AreaForecastRun.id)) is None


async def test_populated_downgrade_fails_closed(pg_engine):
    async with AsyncSession(pg_engine) as s, s.begin():
        saved = await execute_area_forecast_run(s, bounded())
    async with pg_engine.begin() as conn:

        def guarded(c):
            with Operations.context(MigrationContext.configure(c)):
                with pytest.raises(RuntimeError, match="AREA_RUN_DATA_PREVENTS_DOWNGRADE"):
                    importlib.import_module(
                        "backend.alembic.versions.0034_area_forecast_runs"
                    ).downgrade()

        await conn.run_sync(guarded)
    async with AsyncSession(pg_engine) as s:
        assert (await AreaForecastRunRepository(s).get(saved.run.run_id)).result == saved.result


async def test_postgres_concurrent_idempotency(pg_engine):
    import asyncio

    async def create():
        async with AsyncSession(pg_engine) as s, s.begin():
            return await execute_area_forecast_run(s, bounded())

    a, b = await asyncio.gather(create(), create())
    assert a.run.run_id == b.run.run_id
    assert sorted([a.reused_existing_run, b.reused_existing_run]) == [False, True]


async def test_postgres_rerun_scope_before_reuse(pg_engine):
    from backend.app.area_yield.run_persistence import AreaForecastPersistenceConflictError

    async with AsyncSession(pg_engine) as s, s.begin():
        a = await execute_area_forecast_run(s, bounded())
        b = await execute_area_forecast_run(s, bounded(farm="other"))
    async with AsyncSession(pg_engine) as s, s.begin():
        with pytest.raises(AreaForecastPersistenceConflictError) as err:
            await execute_area_forecast_run(s, bounded(), rerun_of_run_id=b.run.run_id)
        assert err.value.code == "AREA_FORECAST_RERUN_SCOPE_MISMATCH"
        child = await execute_area_forecast_run(
            s, bounded(productive_area_mu="500"), rerun_of_run_id=a.run.run_id
        )
    async with AsyncSession(pg_engine) as s:
        loaded = await AreaForecastRunRepository(s).get(child.run.run_id)
        assert loaded.run.rerun_of_run_id == a.run.run_id
        assert loaded.result == child.result
