"""Legacy share_text and new canonical output coexist without migration/rewrite."""

import os

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.area_yield import product
from backend.app.area_yield.run_application import execute_area_forecast_run
from backend.app.area_yield.run_persistence import AreaForecastRunRepository
from backend.app.models.area_forecast import AreaForecastDailyRow
from backend.tests.area_yield.test_run_persistence import authority, bounded  # noqa: F401
from backend.tests.mcp.test_persisted_stdio_postgres import isolated_database as isolated_database

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.usefixtures("authority"),
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_INTEGRATION") != "1", reason="PostgreSQL opt-in"),
]


async def test_old_and_new_immutable_rows_roundtrip(isolated_database, monkeypatch):
    engine, _ = isolated_database
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        with monkeypatch.context() as legacy:
            legacy.setattr(product, "canonical_share_text", str)
            old = await execute_area_forecast_run(session, bounded())
        new = await execute_area_forecast_run(session, bounded(productive_area_mu="500"))
        again = await execute_area_forecast_run(session, bounded(productive_area_mu="500"))
        assert again.run.run_id == new.run.run_id and again.reused_existing_run
    monkeypatch.delenv("AREA_YIELD_AUTHORITY_PATH")
    async with factory() as session:
        repo = AreaForecastRunRepository(session)
        assert (await repo.get(old.run.run_id)) == old
        assert (await repo.get(new.run.run_id)) == new
        assert len((await repo.history()).items) == 2
        rows = (
            await session.scalars(
                select(AreaForecastDailyRow).order_by(
                    AreaForecastDailyRow.run_id, AreaForecastDailyRow.row_index
                )
            )
        ).all()
        old_text = [r.share_text for r in rows if r.run_id == old.run.run_id]
        new_text = [r.share_text for r in rows if r.run_id == new.run.run_id]
        assert old_text == [r.share for r in old.result.daily_forecast]
        assert new_text == [r.share for r in new.result.daily_forecast]
        assert len(old_text) == len(new_text) == 207
        assert any(len(s.split(".")[-1]) > 15 for s in old_text)
        assert all(len(s.split(".")[-1]) == 15 for s in new_text)
