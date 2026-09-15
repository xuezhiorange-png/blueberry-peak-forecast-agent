"""MCP transport tests for the four persisted S6 operational peak tools."""

from __future__ import annotations

from mcp import Client

from backend.app.mcp import operational_peak_runs
from backend.app.mcp.area_forecast import server


def _body() -> dict[str, str]:
    return {
        "base_id": "base-yangliu",
        "target_season": "2026-2027",
        "origin_date": "2027-03-31",
    }


async def test_operational_tools_discovery_and_roundtrip(s6_factory, s6_authority, monkeypatch):
    monkeypatch.setattr(operational_peak_runs, "AsyncSessionMaker", s6_factory)
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
        names = [tool.name for tool in tools]
        assert names == [
            "forecast_blueberry_by_area",
            "create_blueberry_area_forecast_run",
            "get_blueberry_area_forecast_run",
            "list_blueberry_area_forecast_runs",
            "get_blueberry_area_forecast_daily",
            "create_blueberry_operational_peak_forecast_run",
            "get_blueberry_operational_peak_forecast_run",
            "list_blueberry_operational_peak_forecast_runs",
            "get_blueberry_operational_peak_forecast_daily",
        ]
        new_tools = tools[5:]
        assert new_tools[0].annotations.read_only_hint is False
        assert all(tool.annotations.destructive_hint is False for tool in new_tools)
        assert all(tool.annotations.idempotent_hint is True for tool in new_tools)

        first = await client.call_tool("create_blueberry_operational_peak_forecast_run", _body())
        assert not first.is_error
        first_body = first.structured_content
        run_id = first_body["run"]["run_id"]
        assert first_body["result"]["forecast_7d"]["total_kg"] == "2758.000000"
        repeat = await client.call_tool("create_blueberry_operational_peak_forecast_run", _body())
        assert repeat.structured_content["reused_existing_run"] is True
        assert repeat.structured_content["run"]["run_id"] == run_id
        got = await client.call_tool(
            "get_blueberry_operational_peak_forecast_run", {"run_id": run_id}
        )
        daily = await client.call_tool(
            "get_blueberry_operational_peak_forecast_daily", {"run_id": run_id}
        )
        history = await client.call_tool("list_blueberry_operational_peak_forecast_runs", {})
        assert got.structured_content == first_body
        assert len(daily.structured_content["daily_forecast"]) == 15
        assert history.structured_content["items"][0]["run_id"] == run_id

        monkeypatch.delenv("OPERATIONAL_PEAK_AUTHORITY_PATH")
        assert not (
            await client.call_tool(
                "get_blueberry_operational_peak_forecast_run", {"run_id": run_id}
            )
        ).is_error
        assert not (
            await client.call_tool(
                "get_blueberry_operational_peak_forecast_daily", {"run_id": run_id}
            )
        ).is_error


async def test_operational_create_authority_error_is_machine_readable(
    s6_factory, s6_authority, monkeypatch
):
    monkeypatch.setattr(operational_peak_runs, "AsyncSessionMaker", s6_factory)
    monkeypatch.delenv("OPERATIONAL_PEAK_AUTHORITY_PATH")
    async with Client(server) as client:
        result = await client.call_tool("create_blueberry_operational_peak_forecast_run", _body())
    assert result.is_error
    assert result.structured_content["code"] == "AUTHORITY_NOT_CONFIGURED"
