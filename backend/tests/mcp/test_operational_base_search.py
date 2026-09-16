"""Read-only operational-base discovery and exact-name routing contracts."""

from __future__ import annotations

from mcp import Client
from pydantic import ValidationError

from backend.app.forecast_quality.operational_peak_authority import (
    OperationalPeakAuthorityError,
    OperationalPeakAuthoritySnapshot,
)
from backend.app.mcp import operational_base_search
from backend.app.mcp.area_forecast import server


def _snapshot() -> OperationalPeakAuthoritySnapshot:
    return OperationalPeakAuthoritySnapshot(
        authority_version="OPERATIONAL_PEAK_AUTHORITY_V1",
        policy_version="OPERATIONAL_PEAK_POLICY_V1",
        baseline_id="AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1",
        authority_hash="a" * 64,
        registry={
            "bases": [
                {
                    "base_id": "base-zeta",
                    "canonical_base_name": "保山杨柳基地",
                    "productive_area_mu": "394.000000",
                    "area_basis": "BUSINESS_CONFIRMED",
                    "active": True,
                },
                {
                    "base_id": "base-alpha",
                    "canonical_base_name": "保山杨柳东基地",
                    "productive_area_mu": "100.000000",
                    "area_basis": "BUSINESS_REPORTED",
                    "active": True,
                },
                {
                    "base_id": "base-beta",
                    "canonical_base_name": "建水南庄基地",
                    "productive_area_mu": "152.350000",
                    "area_basis": "MEASURED",
                    "active": True,
                },
                {
                    "base_id": "base-inactive",
                    "canonical_base_name": "保山杨柳旧基地",
                    "productive_area_mu": "1.000000",
                    "area_basis": "BUSINESS_CONFIRMED",
                    "active": False,
                },
            ]
        },
        reference_profile={},
        reference_profile_fold="B",
        weather_used=False,
    )


async def _call(query: str | None = None, limit: int = 20):
    async with Client(server) as client:
        return await client.call_tool(
            operational_base_search.SEARCH,
            {"query": query, "limit": limit},
        )


async def test_search_discovery_schema_and_annotations(monkeypatch):
    monkeypatch.setattr(operational_base_search, "load_operational_peak_authority", _snapshot)
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
    tool = next(tool for tool in tools if tool.name == operational_base_search.SEARCH)
    assert tool.annotations.read_only_hint is True
    assert tool.annotations.destructive_hint is False
    assert tool.annotations.idempotent_hint is True
    assert tool.annotations.open_world_hint is False
    query_schema = tool.input_schema["properties"]["query"]
    assert any(option.get("maxLength") == 200 for option in query_schema["anyOf"])
    assert tool.input_schema["properties"]["limit"]["minimum"] == 1
    assert tool.input_schema["properties"]["limit"]["maximum"] == 100
    assert "base_id" not in tool.input_schema["properties"]


async def test_exact_id_name_substrings_and_no_match(monkeypatch):
    monkeypatch.setattr(operational_base_search, "load_operational_peak_authority", _snapshot)

    exact_id = await _call("  ＢＡＳＥ－ＺＥＴＡ ")
    assert [item["base_id"] for item in exact_id.structured_content["items"]] == ["base-zeta"]
    assert exact_id.structured_content["items"][0]["match_type"] == "EXACT_BASE_ID"

    exact_name = await _call("保山杨柳基地")
    assert [item["canonical_base_name"] for item in exact_name.structured_content["items"]] == [
        "保山杨柳基地"
    ]
    assert exact_name.structured_content["items"][0]["match_type"] == "EXACT_CANONICAL_NAME"

    name_substring = await _call("杨柳")
    assert name_substring.structured_content["match_count"] == 2
    assert [item["base_id"] for item in name_substring.structured_content["items"]] == [
        "base-alpha",
        "base-zeta",
    ]
    assert all(
        item["match_type"] == "CANONICAL_NAME_SUBSTRING"
        for item in name_substring.structured_content["items"]
    )

    id_substring = await _call("base-")
    assert id_substring.structured_content["match_count"] == 3
    assert all(
        item["match_type"] == "BASE_ID_SUBSTRING"
        for item in id_substring.structured_content["items"]
    )

    no_match = await _call("不存在")
    assert no_match.structured_content["match_count"] == 0
    assert no_match.structured_content["items"] == []


async def test_empty_query_limit_order_inactive_and_determinism(monkeypatch):
    monkeypatch.setattr(operational_base_search, "load_operational_peak_authority", _snapshot)
    first = await _call("", 2)
    second = await _call("   ", 2)
    assert first.structured_content["items"] == second.structured_content["items"]
    assert first.structured_content["match_count"] == second.structured_content["match_count"]
    assert first.structured_content["authority_hash"] == second.structured_content["authority_hash"]
    assert first.structured_content["match_count"] == 3
    assert len(first.structured_content["items"]) == 2
    assert [item["canonical_base_name"] for item in first.structured_content["items"]] == [
        "保山杨柳东基地",
        "保山杨柳基地",
    ]
    assert all(item["active"] is True for item in first.structured_content["items"])
    assert "保山杨柳旧基地" not in str(first.structured_content)


async def test_search_validation_and_authority_failure_are_machine_readable(monkeypatch):
    monkeypatch.setattr(operational_base_search, "load_operational_peak_authority", _snapshot)
    async with Client(server) as client:
        for arguments in (
            {"query": "x" * 201},
            {"limit": 0},
            {"limit": 101},
            {"query": 1},
            {"unexpected": "value"},
        ):
            result = await client.call_tool(operational_base_search.SEARCH, arguments)
            assert result.is_error
            assert result.structured_content["code"] == "AREA_FORECAST_REQUEST_INVALID"

    def unavailable():
        raise OperationalPeakAuthorityError("AUTHORITY_FILE_HASH_MISMATCH")

    monkeypatch.setattr(operational_base_search, "load_operational_peak_authority", unavailable)
    failed = await _call()
    assert failed.is_error
    assert failed.structured_content == {
        "status": "error",
        "code": "AUTHORITY_FILE_HASH_MISMATCH",
        "reason": "AUTHORITY_FILE_HASH_MISMATCH",
    }


def test_direct_search_validation_remains_strict(monkeypatch):
    monkeypatch.setattr(operational_base_search, "load_operational_peak_authority", _snapshot)
    try:
        operational_base_search.SearchOperationalBases.model_validate({"limit": 1.2})
    except ValidationError:
        pass
    else:
        raise AssertionError("limit must reject native float input")
