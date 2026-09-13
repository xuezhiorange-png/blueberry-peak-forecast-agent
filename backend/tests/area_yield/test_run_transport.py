import io
import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.cli import run_cli
from backend.app.db.session import get_db_session
from backend.app.main import create_app
from backend.app.models.area_forecast import AreaForecastDailyRow, AreaForecastRun
from backend.tests.area_yield.test_run_persistence import authority, bounded  # noqa: F401

pytestmark = pytest.mark.usefixtures("authority")


@pytest.fixture
async def factory(tmp_path, monkeypatch):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/runs.db", connect_args={"autocommit": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(AreaForecastRun.__table__.create)
        await conn.run_sync(AreaForecastDailyRow.__table__.create)
    monkeypatch.setenv("TRIAL_ACTOR_IDENTITY", "area-run-fixture")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_SOURCE_SYSTEMS", "trial-api")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_CHANNELS", "api")
    monkeypatch.setenv("TRIAL_ACTOR_PERMISSIONS", "may_create_forecast,may_read_forecast")
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_http_create_history_daily_no_reforecast(factory, monkeypatch):
    app = create_app()

    async def sessions():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_db_session] = sessions
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://local") as c:
        first = await c.post("/api/v1/area-forecast-runs", json=bounded().model_dump(mode="json"))
        assert first.status_code == 200, first.text
        body = first.json()
        rid = body["run"]["run_id"]
        repeat = await c.post("/api/v1/area-forecast-runs", json=bounded().model_dump(mode="json"))
        assert repeat.json()["reused_existing_run"]
        assert repeat.json()["run"]["run_id"] == rid
        monkeypatch.delenv("AREA_YIELD_AUTHORITY_PATH")
        get = await c.get(f"/api/v1/area-forecast-runs/{rid}")
        daily = await c.get(f"/api/v1/area-forecast-runs/{rid}/daily")
        history = await c.get("/api/v1/area-forecast-runs?canonical_farm=known&limit=1")
        assert get.json() == body
        assert daily.json() == body["result"]["daily_forecast"]
        assert len(daily.json()) == 207
        assert history.json()["items"][0]["run_id"] == rid
        assert "daily_forecast" not in history.text
        assert (await c.get("/api/v1/area-forecast-runs?limit=101")).status_code == 422
        assert (await c.get("/api/v1/area-forecast-runs?cursor=garbage")).status_code == 422
        assert (await c.get("/api/v1/area-forecast-runs/999999")).status_code == 404


async def test_cli_create_get_list_daily(factory, monkeypatch):
    def call(args, body=""):
        out, err = io.StringIO(), io.StringIO()
        rc = run_cli(
            ["area-forecast-run", *args],
            session_factory=factory,
            stdin=io.StringIO(body),
            stdout=out,
            stderr=err,
        )
        assert rc == 0, err.getvalue()
        return json.loads(out.getvalue())

    first = call(["create", "--input", "-"], bounded().model_dump_json())
    rid = str(first["run"]["run_id"])
    monkeypatch.delenv("AREA_YIELD_AUTHORITY_PATH")
    assert call(["get", "--run-id", rid]) == first
    assert len(call(["daily", "--run-id", rid])["daily_forecast"]) == 207
    assert len(call(["list", "--farm", "known"])["items"]) == 1


@pytest.mark.parametrize(
    "fault,code,status",
    [
        ("unknown", "AREA_FORECAST_UNSUPPORTED_FARM_HISTORY", 422),
        ("prior", "AREA_FORECAST_UNSUPPORTED_FARM_HISTORY", 422),
        ("authority", "AREA_FORECAST_AUTHORITY_UNAVAILABLE", 503),
    ],
)
async def test_http_errors(factory, monkeypatch, fault, code, status):
    app = create_app()

    async def sessions():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_db_session] = sessions
    body = bounded().model_dump(mode="json")
    if fault == "unknown":
        body["farm"] = "unknown"
    elif fault == "prior":
        body["target_season"] = "2027-2028"
        body["season_start"], body["season_end"] = None, None
    else:
        monkeypatch.delenv("AREA_YIELD_AUTHORITY_PATH")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://local") as c:
        response = await c.post("/api/v1/area-forecast-runs", json=body)
    assert response.status_code == status and response.json()["code"] == code


async def test_stateless_http_cli_mcp_do_not_persist(factory):
    from mcp import Client
    from sqlalchemy import func, select

    from backend.app.mcp.area_forecast import TOOL_NAME, server

    app = create_app()

    async def sessions():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_db_session] = sessions
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://local") as c:
        http = await c.post("/api/v1/trial/forecasts", json=bounded().model_dump(mode="json"))
        assert http.status_code == 200
    async with Client(server) as c:
        mcp = await c.call_tool(
            TOOL_NAME, bounded().model_dump(mode="json", exclude={"forecast_method"})
        )
        assert mcp.structured_content == http.json()
    out = io.StringIO()
    assert (
        run_cli(
            ["area-forecast", "--input", "-"],
            session_factory=factory,
            stdin=io.StringIO(bounded().model_dump_json()),
            stdout=out,
        )
        == 0
    )
    assert json.loads(out.getvalue()) == http.json()
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(AreaForecastRun)) == 0
