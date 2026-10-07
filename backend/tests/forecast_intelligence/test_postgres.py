"""Real PostgreSQL in a fresh test-owned schema; never touches source/business data."""

import asyncio
import os
import uuid

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.core.config import get_settings
from backend.app.forecast_intelligence.application import execute_hierarchical_run
from backend.app.forecast_intelligence.persistence import HierarchicalRunRepository
from backend.app.models.hierarchical_forecast import HierarchicalForecastRun
from backend.tests.db.migration import assert_safe_isolated_db_name
from backend.tests.db.profile import assert_safe_postgres_test_identity
from backend.tests.forecast_intelligence.conftest import MIGRATION, create_tables, seed_sources
from backend.tests.forecast_intelligence.test_reconciliation import request

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION") != "1", reason="LOCAL_POSTGRES_NOT_AVAILABLE"
    ),
]


@pytest.fixture
async def pg_factory():
    settings = get_settings()
    assert settings.app_env == "test"
    assert settings.postgres_host in {"localhost", "127.0.0.1", "::1"}
    assert_safe_isolated_db_name(settings.postgres_db)
    if settings.postgres_port == 5432:
        # Existing concurrency CI uses container-local 5432, but only with a
        # validated per-run isolated database. Never permit this on a workstation.
        assert os.getenv("GITHUB_ACTIONS") == "true"
    else:
        assert_safe_postgres_test_identity()
    schema = "s1_hierarchy_test_" + uuid.uuid4().hex
    engine = create_async_engine(
        settings.async_database_url, connect_args={"server_settings": {"search_path": schema}}
    )
    async with engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        async with engine.begin() as connection:
            await connection.run_sync(create_tables)

            def empty_roundtrip(sync):
                with Operations.context(MigrationContext.configure(sync)):
                    MIGRATION.downgrade()
                    MIGRATION.upgrade()

            await connection.run_sync(empty_roundtrip)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        # Only this freshly generated synthetic test namespace is removed.
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


async def test_pg_complete_incomplete_constraints_immutability_and_downgrade(
    pg_factory, synthetic_authority
):
    ids = await seed_sources(pg_factory, synthetic_authority)
    async with pg_factory() as session, session.begin():
        complete = await execute_hierarchical_run(session, request(ids))
        incomplete = await execute_hierarchical_run(session, request(ids[:-1]))
        assert complete.result["company_path_parity"] is True
        assert incomplete.result["daily_forecast"] == []
    async with pg_factory() as session:
        assert (
            await HierarchicalRunRepository(session).get(complete.run.run_id)
        ).result == complete.result
        assert (
            await HierarchicalRunRepository(session).get(incomplete.run.run_id)
        ).result == incomplete.result
    for table in (
        "hierarchical_forecast_run",
        "hierarchical_forecast_daily",
        "hierarchical_forecast_source",
        "operational_peak_forecast_run",
        "operational_peak_forecast_daily",
    ):
        for sql in (f"UPDATE {table} SET id=id", f"DELETE FROM {table}"):
            async with pg_factory() as session:
                with pytest.raises(DBAPIError, match="immutable"):
                    await session.execute(text(sql))
                await session.rollback()
    async with pg_factory() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO hierarchical_forecast_daily "
                    "(run_id,row_index,forecast_date,predicted_kg) "
                    "VALUES (:id,0,'2026-01-02',-1)"
                ),
                {"id": incomplete.run.run_id},
            )
        await session.rollback()
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO hierarchical_forecast_source "
                    "(hierarchical_run_id,source_operational_peak_run_id,base_id,"
                    "source_execution_hash,source_result_hash) SELECT hierarchical_run_id,"
                    "source_operational_peak_run_id,base_id,source_execution_hash,"
                    "source_result_hash FROM hierarchical_forecast_source LIMIT 1"
                )
            )
        await session.rollback()
    async with pg_factory.kw["bind"].begin() as connection:

        def populated_downgrade(sync):
            with Operations.context(MigrationContext.configure(sync)):
                MIGRATION.downgrade()

        with pytest.raises(RuntimeError, match="HIERARCHICAL_FORECAST_DATA_PREVENTS_DOWNGRADE"):
            await connection.run_sync(populated_downgrade)


@pytest.mark.postgres_concurrency
async def test_pg_same_execution_concurrent_create(pg_factory, synthetic_authority, monkeypatch):
    ids = await seed_sources(pg_factory, synthetic_authority)
    barrier = asyncio.Barrier(2)
    original_save = HierarchicalRunRepository.save

    async def simultaneous_save(self, *args):
        await barrier.wait()
        return await original_save(self, *args)

    monkeypatch.setattr(HierarchicalRunRepository, "save", simultaneous_save)

    async def create():
        async with pg_factory() as session, session.begin():
            return await execute_hierarchical_run(session, request(ids))

    first, second = await asyncio.wait_for(asyncio.gather(create(), create()), timeout=30)
    assert first.run.run_id == second.run.run_id
    assert first.result == second.result
    assert first.reused_existing_run != second.reused_existing_run
    async with pg_factory() as session:
        assert await session.scalar(select(func.count()).select_from(HierarchicalForecastRun)) == 1
