"""Actual stdio processes use normal DB settings and concurrent PostgreSQL writes."""

import asyncio
import importlib
import json
import os
import sys
from uuid import uuid4

import anyio
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from httpx import ASGITransport, AsyncClient
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.core.config import get_settings
from backend.app.db.session import get_db_session
from backend.app.main import create_app
from backend.app.models.area_forecast import AreaForecastDailyRow, AreaForecastRun
from backend.tests.area_yield.test_run_persistence import authority  # noqa: F401
from backend.tests.mcp.test_persisted_tools import ALL_NAMES, NAMES, args

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.usefixtures("authority"),
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_INTEGRATION") != "1", reason="PostgreSQL opt-in"),
]


@pytest.fixture
async def isolated_database():
    assert os.getenv("APP_ENV") == "test"
    settings = get_settings()
    name = "mcp_runs_test_" + uuid4().hex
    admin = create_async_engine(settings.async_database_url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_async_engine(
        settings.model_copy(update={"postgres_db": name}).async_database_url
    )
    try:
        async with engine.begin() as conn:

            def install(sync):
                with Operations.context(MigrationContext.configure(sync)):
                    importlib.import_module(
                        "backend.alembic.versions.0034_area_forecast_runs"
                    ).upgrade()
                    importlib.import_module(
                        "backend.alembic.versions.0035_operational_peak_forecast_runs"
                    ).upgrade()
                    importlib.import_module(
                        "backend.alembic.versions.0036_v06_pit_data_foundation"
                    ).upgrade()

            await conn.run_sync(install)
        env = {**os.environ, "POSTGRES_DB": name}
        yield engine, env
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            # Only this test-generated database; no shared/user database is deleted.
            await conn.execute(text(f'DROP DATABASE "{name}"'))
        await admin.dispose()


async def test_actual_stdio_concurrent_create_and_read_parity(isolated_database, monkeypatch):
    engine, env = isolated_database
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "backend.app.mcp.area_forecast"], env=env
    )
    async with Client(parameters) as c:
        assert [t.name for t in (await c.list_tools()).tools] == ALL_NAMES
        a, b = await asyncio.gather(c.call_tool(NAMES[1], args()), c.call_tool(NAMES[1], args()))
        assert not a.is_error and not b.is_error
        payloads = [a.structured_content, b.structured_content]
        assert sorted(p["reused_existing_run"] for p in payloads) == [False, True]
        assert payloads[0]["run"]["run_id"] == payloads[1]["run"]["run_id"]
        saved = next(p for p in payloads if not p["reused_existing_run"])
        reused = next(p for p in payloads if p["reused_existing_run"])
        rid = saved["run"]["run_id"]
        assert len(saved["result"]["daily_forecast"]) == 207
        assert not (await c.call_tool(NAMES[0], args())).is_error
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(AreaForecastRun)) == 1
        assert await s.scalar(select(func.count()).select_from(AreaForecastDailyRow)) == 207
    # HTTP and CLI create must reuse this exact stdio-created execution.
    monkeypatch.setenv("TRIAL_ACTOR_IDENTITY", "mcp-postgres-fixture")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_SOURCE_SYSTEMS", "trial-api")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_CHANNELS", "api")
    monkeypatch.setenv("TRIAL_ACTOR_PERMISSIONS", "may_create_forecast,may_read_forecast")
    app = create_app()

    async def sessions():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_db_session] = sessions

    async def cli(words, input_bytes=None):
        p = await anyio.run_process(
            [sys.executable, "-m", "backend.app.cli", "area-forecast-run", *words],
            env=env,
            input=input_bytes,
            check=True,
        )
        return json.loads(p.stdout)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://local") as http:
        assert (await http.post("/api/v1/area-forecast-runs", json=args())).json() == reused
        assert await cli(["create", "--input", "-"], json.dumps(args()).encode()) == reused
        env.pop("AREA_YIELD_AUTHORITY_PATH", None)
        env.pop("AREA_YIELD_AUTHORITY_SHA256", None)
        monkeypatch.delenv("AREA_YIELD_AUTHORITY_PATH")
        # A fresh stdio process cannot access authority; all historical operations still work.
        parameters = StdioServerParameters(
            command=sys.executable, args=["-m", "backend.app.mcp.area_forecast"], env=env
        )
        async with Client(parameters) as c:
            get = await c.call_tool(NAMES[2], {"run_id": rid})
            assert not get.is_error and get.structured_content == saved
            assert (await http.get(f"/api/v1/area-forecast-runs/{rid}")).json() == saved
            assert await cli(["get", "--run-id", str(rid)]) == saved
            daily = (await c.call_tool(NAMES[4], {"run_id": rid})).structured_content[
                "daily_forecast"
            ]
            assert daily == saved["result"]["daily_forecast"]
            assert (await http.get(f"/api/v1/area-forecast-runs/{rid}/daily")).json() == daily
            assert (await cli(["daily", "--run-id", str(rid)]))["daily_forecast"] == daily
            history = (await c.call_tool(NAMES[3], {})).structured_content
            assert (await http.get("/api/v1/area-forecast-runs")).json() == history
            assert await cli(["list"]) == history
            assert "daily_forecast" not in json.dumps(history)
