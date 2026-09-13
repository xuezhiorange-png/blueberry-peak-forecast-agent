"""Real TCP HTTP + stdio + CLI share normal configured PostgreSQL execution identity."""

import asyncio
import json
import os
import socket
import sys
from contextlib import asynccontextmanager

import anyio
import pytest
from httpx import AsyncClient, ConnectError
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import Tool
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.area_yield.product_authority import forecast_area_product
from backend.app.models.area_forecast import AreaForecastDailyRow, AreaForecastRun
from backend.tests.area_yield.test_run_persistence import authority, bounded  # noqa: F401
from backend.tests.mcp.test_persisted_stdio_postgres import isolated_database as isolated_database
from backend.tests.mcp.test_persisted_tools import NAMES, args
from backend.tests.mcp.test_streamable_http import INITIALIZE, PATHS, rpc

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.usefixtures("authority"),
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_INTEGRATION") != "1", reason="PostgreSQL opt-in"),
]


@asynccontextmanager
async def running_backend(env, port=0):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", port))
        port = listener.getsockname()[1]
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "uvicorn",
        "backend.app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=30) as client:
            for _ in range(200):
                assert process.returncode is None, "backend exited before ready"
                try:
                    if (await client.get("/health/live")).status_code == 200:
                        break
                except ConnectError:
                    pass
                await asyncio.sleep(0.1)
            else:
                pytest.fail("backend readiness timeout")
            yield client
    finally:
        process.terminate()
        await asyncio.wait_for(process.wait(), 10)


async def test_network_five_tools_and_transport_parity(isolated_database, monkeypatch):
    engine, env = isolated_database
    env.update(
        {
            "TRIAL_ACTOR_IDENTITY": "streamable-http-fixture",
            "TRIAL_ACTOR_ALLOWED_SOURCE_SYSTEMS": "trial-api",
            "TRIAL_ACTOR_ALLOWED_CHANNELS": "api",
            "TRIAL_ACTOR_PERMISSIONS": "may_create_forecast,may_read_forecast",
            "BLUEBERRY_MCP_CONNECTOR_SHARED_SECRET": "network-test-key",
        }
    )

    async def cli(words, body=None):
        result = await anyio.run_process(
            [sys.executable, "-m", "backend.app.cli", *words],
            env=env,
            input=json.dumps(body).encode() if body is not None else None,
        )
        return json.loads(result.stdout)

    async def call(c, name, body):
        result = await rpc(c, "tools/call", {"name": name, "arguments": body})
        assert not result.get("isError"), result
        return result["structuredContent"]

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with (
        running_backend(env) as http,
        Client(
            StdioServerParameters(
                command=sys.executable, args=["-m", "backend.app.mcp.area_forecast"], env=env
            )
        ) as stdio,
    ):
        http.headers["X-Blueberry-Connector-Key"] = "network-test-key"
        http.headers.pop("accept", None)
        await rpc(http, "initialize", INITIALIZE)
        listed = await rpc(http, "tools/list", {})
        assert [Tool.model_validate(t) for t in listed["tools"]] == (await stdio.list_tools()).tools
        predicted = await call(http, NAMES[0], args())
        assert predicted == forecast_area_product(bounded()).model_dump(mode="json")
        assert predicted == (await stdio.call_tool(NAMES[0], args())).structured_content
        assert predicted == await cli(["area-forecast", "--input", "-"], args())
        assert (
            predicted
            == (
                await http.post("/api/v1/trial/forecasts", json=bounded().model_dump(mode="json"))
            ).json()
        )
        async with factory() as s:
            assert await s.scalar(select(func.count()).select_from(AreaForecastRun)) == 0
        a, b = await asyncio.gather(call(http, NAMES[1], args()), call(http, NAMES[1], args()))
        assert sorted([a["reused_existing_run"], b["reused_existing_run"]]) == [False, True]
        saved = a if not a["reused_existing_run"] else b
        reused = b if b["reused_existing_run"] else a
        rid = saved["run"]["run_id"]
        assert reused["run"]["run_id"] == rid
        assert (await http.post("/api/v1/area-forecast-runs", json=args())).json() == reused
        assert await cli(["area-forecast-run", "create", "--input", "-"], args()) == reused
        assert (await stdio.call_tool(NAMES[1], args())).structured_content == reused
        async with factory() as s:
            assert await s.scalar(select(func.count()).select_from(AreaForecastRun)) == 1
            assert await s.scalar(select(func.count()).select_from(AreaForecastDailyRow)) == 207
    env.pop("AREA_YIELD_AUTHORITY_PATH", None)
    env.pop("AREA_YIELD_AUTHORITY_SHA256", None)
    async with (
        running_backend(env) as http,
        Client(
            StdioServerParameters(
                command=sys.executable, args=["-m", "backend.app.mcp.area_forecast"], env=env
            )
        ) as stdio,
    ):
        http.headers["X-Blueberry-Connector-Key"] = "network-test-key"
        for name in NAMES[:2]:
            failed = await rpc(http, "tools/call", {"name": name, "arguments": args()})
            assert failed["isError"]
            assert failed["structuredContent"]["code"] == "AREA_FORECAST_AUTHORITY_UNAVAILABLE"
        assert await call(http, NAMES[2], {"run_id": rid}) == saved
        assert (await stdio.call_tool(NAMES[2], {"run_id": rid})).structured_content == saved
        assert (await http.get(f"/api/v1/area-forecast-runs/{rid}")).json() == saved
        assert await cli(["area-forecast-run", "get", "--run-id", str(rid)]) == saved
        daily = await call(http, NAMES[4], {"run_id": rid})
        assert len(daily["daily_forecast"]) == 207
        assert (await stdio.call_tool(NAMES[4], {"run_id": rid})).structured_content == daily
        assert (await http.get(f"/api/v1/area-forecast-runs/{rid}/daily")).json() == daily[
            "daily_forecast"
        ]
        assert (await cli(["area-forecast-run", "daily", "--run-id", str(rid)]))[
            "daily_forecast"
        ] == daily["daily_forecast"]
        history = await call(http, NAMES[3], {})
        assert (await stdio.call_tool(NAMES[3], {})).structured_content == history
        assert (await http.get("/api/v1/area-forecast-runs")).json() == history
        assert await cli(["area-forecast-run", "list"]) == history
        assert "daily_forecast" not in json.dumps(history)
        assert (await rpc(http, "tools/list", {}, PATHS[1]))["tools"] == listed["tools"]
