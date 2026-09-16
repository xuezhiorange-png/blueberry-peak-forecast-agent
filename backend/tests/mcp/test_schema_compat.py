"""Regression coverage for the Doubao-compatible MCP input-schema projection."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

import pytest
from mcp import Client

from backend.app.mcp.area_forecast import server
from backend.app.mcp.schema_compat import (
    MCPInputSchemaProjectionError,
    project_mcp_input_schema,
)

ALL_TOOL_NAMES = {
    "forecast_blueberry_by_area",
    "create_blueberry_area_forecast_run",
    "get_blueberry_area_forecast_run",
    "list_blueberry_area_forecast_runs",
    "get_blueberry_area_forecast_daily",
    "create_blueberry_operational_peak_forecast_run",
    "get_blueberry_operational_peak_forecast_run",
    "list_blueberry_operational_peak_forecast_runs",
    "get_blueberry_operational_peak_forecast_daily",
}
POSITIVE_ID_TOOL_NAMES = {
    "create_blueberry_area_forecast_run",
    "get_blueberry_area_forecast_run",
    "get_blueberry_area_forecast_daily",
    "create_blueberry_operational_peak_forecast_run",
    "get_blueberry_operational_peak_forecast_run",
    "get_blueberry_operational_peak_forecast_daily",
}


def _contains_key(node: object, key: str) -> bool:
    if isinstance(node, dict):
        return key in node or any(_contains_key(value, key) for value in node.values())
    if isinstance(node, list):
        return any(_contains_key(value, key) for value in node)
    return False


def _has_positive_integer_constraint(node: object) -> bool:
    if isinstance(node, dict):
        if node.get("type") == "integer" and node.get("minimum") == 1:
            return True
        return any(_has_positive_integer_constraint(value) for value in node.values())
    if isinstance(node, list):
        return any(_has_positive_integer_constraint(value) for value in node)
    return False


def _property_has_positive_integer_constraint(schema: dict[str, Any], name: str) -> bool:
    property_schema = schema.get("properties", {}).get(name, {})
    return _has_positive_integer_constraint(property_schema)


def test_projection_is_recursive_and_does_not_mutate_input() -> None:
    schema = {
        "type": "object",
        "description": "preserved",
        "properties": {
            "run_id": {
                "anyOf": [
                    {"type": "integer", "exclusiveMinimum": 0},
                    {"type": "null"},
                ]
            }
        },
    }
    original = copy.deepcopy(schema)

    projected = project_mcp_input_schema(schema)

    assert schema == original
    assert projected["description"] == "preserved"
    assert projected["properties"]["run_id"]["anyOf"][0] == {
        "type": "integer",
        "minimum": 1,
    }
    assert projected["properties"]["run_id"]["anyOf"][1] == {"type": "null"}


def test_projection_fails_closed_on_conflicting_minimum() -> None:
    with pytest.raises(MCPInputSchemaProjectionError):
        project_mcp_input_schema({"type": "integer", "exclusiveMinimum": 0, "minimum": 0})


@pytest.mark.asyncio
async def test_all_nine_tools_expose_projected_input_schemas() -> None:
    async with Client(server) as client:
        tools = (await client.list_tools()).tools

    assert len(tools) == 9
    assert {tool.name for tool in tools} == ALL_TOOL_NAMES
    assert all(not _contains_key(tool.input_schema, "exclusiveMinimum") for tool in tools)

    by_name = {tool.name: tool.input_schema for tool in tools}
    assert all(
        _property_has_positive_integer_constraint(by_name[name], property_name)
        for name, property_name in {
            "create_blueberry_area_forecast_run": "rerun_of_run_id",
            "get_blueberry_area_forecast_run": "run_id",
            "get_blueberry_area_forecast_daily": "run_id",
            "create_blueberry_operational_peak_forecast_run": "rerun_of_run_id",
            "get_blueberry_operational_peak_forecast_run": "run_id",
            "get_blueberry_operational_peak_forecast_daily": "run_id",
        }.items()
    )

    affected = {
        name
        for name, schema in by_name.items()
        if name in POSITIVE_ID_TOOL_NAMES
        and (
            _property_has_positive_integer_constraint(schema, "run_id")
            or _property_has_positive_integer_constraint(schema, "rerun_of_run_id")
        )
    }
    assert affected == POSITIVE_ID_TOOL_NAMES


@pytest.mark.asyncio
async def test_all_tool_input_schema_hash_is_frozen() -> None:
    async with Client(server) as client:
        tools = (await client.list_tools()).tools

    payload = [{"name": tool.name, "input_schema": tool.input_schema} for tool in tools]
    schema_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert schema_hash == "a634d7fd4cc3c88ced801bdef4e5d41123c55d841b212998f94d26313294d36e"


@pytest.mark.asyncio
async def test_runtime_positive_integer_validation_remains_strict() -> None:
    async with Client(server) as client:
        for value in (0, -1, 1.2, "1"):
            result = await client.call_tool("get_blueberry_area_forecast_run", {"run_id": value})
            assert result.is_error
            assert result.structured_content["code"] == "AREA_FORECAST_REQUEST_INVALID"

        result = await client.call_tool(
            "create_blueberry_area_forecast_run",
            {
                "farm": "known",
                "productive_area_mu": "100",
                "target_season": "2026-2027",
                "rerun_of_run_id": 0,
            },
        )
        assert result.is_error
        assert result.structured_content["code"] == "AREA_FORECAST_REQUEST_INVALID"
