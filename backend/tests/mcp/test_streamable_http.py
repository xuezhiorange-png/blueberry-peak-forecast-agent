"""JSON-only inbound transport; tool contracts stay owned by the existing server."""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from mcp import Client
from mcp.types import Tool
from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError

from backend.app.core.config import AppSettings
from backend.app.main import create_app
from backend.app.mcp import persisted_runs
from backend.app.mcp.area_forecast import server
from backend.tests.area_yield.test_run_persistence import authority  # noqa: F401
from backend.tests.mcp.test_persisted_tools import NAMES, args

PATHS = ["/api/v1/blueberry/v1/mcp/sse", "/api/v1/blueberry/v1/mcp"]
INITIALIZE = {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "doubao-acceptance", "version": "0.1"},
}


async def rpc(client, method, params, path=PATHS[0], **kwargs):
    response = await client.post(
        path, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, **kwargs
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert "mcp-session-id" not in response.headers
    return response.json()["result"]


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("accept", [None, "*/*", "application/json"])
async def test_initialize_list_json_without_session_or_sse(path, accept):
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://local") as c:
        c.headers.pop("accept", None)
        if accept:
            c.headers["accept"] = accept
        initialized = await rpc(c, "initialize", INITIALIZE, path)
        assert initialized["serverInfo"]["name"] == "blueberry-area-forecast"
        listed = await rpc(c, "tools/list", {}, path)
        async with Client(server) as stdio_equivalent:
            expected = (await stdio_equivalent.list_tools()).tools
        assert [Tool.model_validate(t) for t in listed["tools"]] == expected
        assert [t["name"] for t in listed["tools"]] == NAMES
        assert (await c.get(path)).status_code == 405


@pytest.mark.parametrize("path", PATHS)
async def test_shared_secret_all_posts(path):
    settings = AppSettings(blueberry_mcp_connector_shared_secret=SecretStr("test-secret"))
    async with AsyncClient(
        transport=ASGITransport(app=create_app(settings)), base_url="http://local"
    ) as c:
        for method in ("initialize", "tools/list", "tools/call"):
            for headers in ({}, {"X-Blueberry-Connector-Key": "wrong"}):
                response = await c.post(path, json={"method": method}, headers=headers)
                assert response.status_code == 401
                assert "test-secret" not in response.text and "wrong" not in response.text
        await rpc(
            c, "initialize", INITIALIZE, path, headers={"X-Blueberry-Connector-Key": "test-secret"}
        )
        await rpc(c, "tools/list", {}, path, headers={"X-Blueberry-Connector-Key": "test-secret"})


@pytest.mark.parametrize("name", NAMES[1:])
async def test_db_errors_remain_redacted(name, monkeypatch):
    def broken():
        raise SQLAlchemyError("postgresql://private:secret@host/db SELECT /private/path")

    monkeypatch.setattr(persisted_runs, "AsyncSessionMaker", broken)
    body = args() if name == NAMES[1] else ({} if name == NAMES[3] else {"run_id": 1})
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://local") as c:
        result = await rpc(c, "tools/call", {"name": name, "arguments": body})
    assert result["isError"]
    assert result["structuredContent"]["code"] == "AREA_FORECAST_WRITE_FAILURE"
    assert all(s not in json.dumps(result) for s in ("postgresql", "SELECT", "/private", "secret"))


@pytest.mark.usefixtures("authority")
@pytest.mark.parametrize(
    "body", [args(farm="unknown"), args(productive_area_mu=393.4), args(target_season="2027-2028")]
)
async def test_product_error_parity(body):
    async with Client(server) as c:
        expected = await c.call_tool(NAMES[0], body)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://local") as c:
        result = await rpc(c, "tools/call", {"name": NAMES[0], "arguments": body})
    assert result["isError"] and result["structuredContent"] == expected.structured_content


async def test_secret_environment_configuration(monkeypatch):
    monkeypatch.setenv("BLUEBERRY_MCP_CONNECTOR_SHARED_SECRET", "environment-secret")
    settings = AppSettings(_env_file=None)
    assert "environment-secret" not in repr(settings)
    async with AsyncClient(
        transport=ASGITransport(app=create_app(settings)), base_url="http://local"
    ) as c:
        assert (await c.post(PATHS[0], json={})).status_code == 401
        await rpc(
            c, "initialize", INITIALIZE, headers={"X-Blueberry-Connector-Key": "environment-secret"}
        )
