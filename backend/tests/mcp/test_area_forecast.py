"""MCP protocol clients exercise the same product boundary; fixture data only."""

import hashlib
import json
import os
import sys

import anyio
import pytest
from httpx import ASGITransport, AsyncClient
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from backend.app.area_yield.product import AreaDrivenForecastResult
from backend.app.area_yield.product_authority import forecast_area_product
from backend.app.main import create_app
from backend.app.mcp.area_forecast import TOOL_NAME, input_schema, server
from backend.tests.area_yield.test_product_p1 import bundle, request


@pytest.fixture
def configured(tmp_path, monkeypatch):
    raw = json.dumps(bundle()).encode()
    path = tmp_path / "private-authority.json"
    path.write_bytes(raw)
    monkeypatch.setenv("AREA_YIELD_AUTHORITY_PATH", str(path))
    monkeypatch.setenv("AREA_YIELD_AUTHORITY_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setenv("TRIAL_ACTOR_IDENTITY", "local-mcp-fixture")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_SOURCE_SYSTEMS", "trial-api")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_CHANNELS", "api")
    monkeypatch.setenv("TRIAL_ACTOR_PERMISSIONS", "may_create_forecast")
    return path


def arguments():
    return request().model_dump(mode="json", exclude={"forecast_method"})


async def test_discovery_without_authority(monkeypatch):
    monkeypatch.delenv("AREA_YIELD_AUTHORITY_PATH", raising=False)
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
    assert len(tools) == 5 and tools[0].name == TOOL_NAME
    assert tools[0].description
    assert tools[0].input_schema == input_schema()
    assert set(tools[0].input_schema["required"]) == {"farm", "productive_area_mu", "target_season"}
    assert set(tools[0].input_schema["properties"]) == set(arguments())
    assert tools[0].input_schema["properties"]["productive_area_mu"]["type"] == "string"
    assert tools[0].output_schema == AreaDrivenForecastResult.model_json_schema()
    schemas = {"input": input_schema(), "output": AreaDrivenForecastResult.model_json_schema()}
    assert (
        hashlib.sha256(
            json.dumps(schemas, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        == "5d0054933e148a95bf33c5d4f3a4029f3ea00267dee62c445b666b5d776b3d93"
    )


@pytest.mark.parametrize("failure", ["unknown", "prior", "authority"])
async def test_typed_error_transport_parity(configured, monkeypatch, failure):
    args = arguments()
    if failure == "unknown":
        args["farm"] = "unknown"
    elif failure == "prior":
        args["target_season"] = "2027-2028"
    else:
        monkeypatch.delenv("AREA_YIELD_AUTHORITY_SHA256")
    async with Client(server) as client:
        mcp = await client.call_tool(TOOL_NAME, args)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://local") as c:
        http = await c.post(
            "/api/v1/trial/forecasts",
            json={
                "forecast_method": "AREA_DRIVEN_B1",
                **args,
            },
        )
    cli = await anyio.run_process(
        [sys.executable, "-m", "backend.app.cli", "area-forecast", "--input", "-"],
        input=json.dumps(args).encode(),
        check=False,
    )
    assert http.status_code == (503 if failure == "authority" else 422)
    assert cli.returncode == (3 if failure == "authority" else 2)
    assert mcp.is_error
    assert mcp.structured_content["code"] == http.json()["code"]
    assert mcp.structured_content["reason"] == http.json()["details"]["reason"]
    assert mcp.structured_content["code"] in cli.stderr.decode()
    assert mcp.structured_content["reason"] in cli.stderr.decode()


async def test_four_way_payload_hash_parity_and_determinism(configured):
    expected = forecast_area_product(request()).model_dump(mode="json")
    async with Client(server) as client:
        for _ in range(2):
            result = await client.call_tool(TOOL_NAME, arguments())
            assert not result.is_error
            assert result.structured_content == expected
            assert json.loads(result.content[0].text) == expected
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://local") as c:
        response = await c.post("/api/v1/trial/forecasts", json=request().model_dump(mode="json"))
    assert response.status_code == 200 and response.json() == expected
    cli = await anyio.run_process(
        [sys.executable, "-m", "backend.app.cli", "area-forecast", "--input", "-"],
        input=request().model_dump_json().encode(),
        check=True,
    )
    assert json.loads(cli.stdout) == expected


async def test_actual_stdio_client_discovery_and_call(configured):
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "backend.app.mcp.area_forecast"], env=dict(os.environ)
    )
    async with Client(params) as client:
        assert (await client.list_tools()).tools[0].name == TOOL_NAME
        result = await client.call_tool(TOOL_NAME, arguments())
    assert result.structured_content == forecast_area_product(request()).model_dump(mode="json")


@pytest.mark.parametrize(
    "changes,code,reason",
    [
        (
            {"farm": "unknown"},
            "AREA_FORECAST_UNSUPPORTED_FARM_HISTORY",
            "UNSUPPORTED_CANONICAL_FARM",
        ),
        (
            {"target_season": "2027-2028"},
            "AREA_FORECAST_UNSUPPORTED_FARM_HISTORY",
            "PRIOR_SEASON_HISTORY_MISSING",
        ),
        (
            {"productive_area_mu": 393.4},
            "AREA_FORECAST_REQUEST_INVALID",
            "INVALID_REQUEST_DOCUMENT",
        ),
        (
            {"productive_area_mu": "NaN"},
            "AREA_FORECAST_REQUEST_INVALID",
            "INVALID_REQUEST_DOCUMENT",
        ),
        (
            {"target_season": "2026-2028"},
            "AREA_FORECAST_REQUEST_INVALID",
            "INVALID_REQUEST_DOCUMENT",
        ),
        (
            {"season_start": "2026-10-01"},
            "AREA_FORECAST_REQUEST_INVALID",
            "BOTH_WINDOW_BOUNDS_REQUIRED",
        ),
        (
            {"as_of": "2026-07-01"},
            "AREA_FORECAST_REQUEST_INVALID",
            "AS_OF_MUST_PRECEDE_TARGET_SEASON",
        ),
        (
            {"authority_path": "/private/secret"},
            "AREA_FORECAST_REQUEST_INVALID",
            "INVALID_REQUEST_DOCUMENT",
        ),
    ],
)
async def test_errors_fail_closed(configured, changes, code, reason):
    async with Client(server) as client:
        r = await client.call_tool(TOOL_NAME, {**arguments(), **changes})
    assert r.is_error
    assert r.structured_content == {"status": "error", "code": code, "reason": reason}
    assert "/private/secret" not in r.model_dump_json()


@pytest.mark.parametrize("fault", ["missing", "unreadable", "outer_hash", "payload_hash"])
async def test_authority_errors_redacted(configured, monkeypatch, fault):
    if fault == "missing":
        monkeypatch.delenv("AREA_YIELD_AUTHORITY_PATH")
    elif fault == "unreadable":
        monkeypatch.setenv("AREA_YIELD_AUTHORITY_PATH", "/private/secret/not-present")
    elif fault == "outer_hash":
        monkeypatch.setenv("AREA_YIELD_AUTHORITY_SHA256", "0" * 64)
    else:
        raw = json.dumps({**bundle(), "hash": "0" * 64}).encode()
        configured.write_bytes(raw)
        monkeypatch.setenv("AREA_YIELD_AUTHORITY_SHA256", hashlib.sha256(raw).hexdigest())
    async with Client(server) as client:
        r = await client.call_tool(TOOL_NAME, arguments())
    assert r.is_error and r.structured_content["code"] == "AREA_FORECAST_AUTHORITY_UNAVAILABLE"
    assert (
        str(configured) not in r.model_dump_json() and "/private/secret" not in r.model_dump_json()
    )
