"""E4 adapter acceptance uses hand-specified synthetic artifacts, never training."""

import json
import os
import sys
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast

import anyio
import pytest
from httpx import ASGITransport, AsyncClient
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from backend.app.area_yield import area_size_r1
from backend.app.area_yield import prospective_validation as e1
from backend.app.area_yield import research_mcp_application as app
from backend.app.area_yield import research_records as legacy
from backend.app.area_yield.data import digest
from backend.app.area_yield.v0_12_e1_fixtures import make_fixture
from backend.app.core.config import get_settings
from backend.app.main import create_app
from backend.app.mcp import v0_12_research as tools
from backend.app.mcp.area_forecast import server
from backend.tests.mcp.test_streamable_http_postgres import running_backend


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    case = make_fixture(tmp_path / "SYNTHETIC")
    monkeypatch.setenv("V0_12_RESEARCH_MCP_ENABLED", "true")
    monkeypatch.setenv("V0_12_RESEARCH_RUNTIME_REGISTRY_PATH", str(case["registry"]))
    monkeypatch.setenv("V0_12_RESEARCH_TEST_STORE_PATH", str(case["store"]))
    get_settings.cache_clear()
    monkeypatch.setattr(area_size_r1, "fit", lambda *a, **k: pytest.fail("TRAINING"))
    yield case
    get_settings.cache_clear()


def business(**changes: Any) -> dict[str, Any]:
    return {
        "request_id": "E4_SYNTHETIC_REQUEST",
        "target_area_mu": "736.000000",
        "target_season": "2028-2029",
        "base_or_farm_context": "TEST_ONLY_UNSEEN_BASE",
        **changes,
    }


def reseal(path: Path, mutate: Callable[[dict[str, Any]], Any]) -> None:
    record = legacy.read(path)
    mutate(record)
    record["record_hash"] = digest({k: v for k, v in record.items() if k != "record_hash"})
    path.write_text(json.dumps(record))


async def test_default_disabled_preserves_ten_tools(
    runtime: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("V0_12_RESEARCH_MCP_ENABLED", "false")
    get_settings.cache_clear()
    async with Client(server) as client:
        assert len((await client.list_tools()).tools) == 10
        failed = await client.call_tool(tools.READINESS, {})
    assert failed.is_error
    assert failed.structured_content["code"] == "V0_12_RESEARCH_INTERFACE_DISABLED"


async def test_enabled_four_tools_full_flow(runtime: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    async with Client(server) as client:
        listed = (await client.list_tools()).tools
        assert len(listed) == 14
        assert {t.name for t in listed[-4:]} == set(tools.CONTRACTS)
        for tool in listed[-4:]:
            encoded = json.dumps(tool.input_schema)
            assert "anyOf" not in encoded and "oneOf" not in encoded
            assert tool.input_schema["additionalProperties"] is False
            assert tool.annotations is not None
            assert tool.annotations.idempotent_hint == (tool.name != tools.CREATE)
        ready = (await client.call_tool(tools.READINESS, {})).structured_content
        assert ready["real_prospective_enabled"] is False
        created = (await client.call_tool(tools.CREATE, business())).structured_content
        assert "daily_curve" not in json.dumps(created)
        identity = {"forecast_id": created["forecast_id"]}
        monkeypatch.setattr(area_size_r1, "predict", lambda *a, **k: pytest.fail("REPREDICT"))
        loaded = (await client.call_tool(tools.GET, identity)).structured_content
        verified = (await client.call_tool(tools.VERIFY, identity)).structured_content
        assert len(loaded["candidate"]["daily_curve"]) == 289
        assert verified["seal_verified"] is True
        assert verified["seal_hash"] == created["seal_hash"]
        duplicate = await client.call_tool(tools.CREATE, business())
        assert duplicate.structured_content["code"] == "V0_12_RESEARCH_DUPLICATE_REQUEST"
    output = json.dumps([ready, created, loaded, verified])
    for secret in (str(runtime["store"]), "artifact_path", "training_bases", "parameters"):
        assert secret not in output


@pytest.mark.parametrize(
    "field",
    [
        "request_mode",
        "authorization_status",
        "production_mode",
        "prospective_mode",
        "model_id",
        "candidate_model_id",
        "candidate_artifact_hash",
        "candidate_config_hash",
        "comparator_id",
        "runtime_registry_path",
        "authorization_path",
        "request_source_path",
        "store_path",
        "penalty",
        "alpha",
        "beta",
        "yield",
        "shape",
        "requested_at",
    ],
)
async def test_override_unknown_field_rejected(runtime: Any, field: str) -> None:
    async with Client(server) as client:
        result = await client.call_tool(tools.CREATE, business(**{field: "REAL_PROSPECTIVE"}))
    assert result.is_error
    assert result.structured_content["reason"] == "INVALID_REQUEST_DOCUMENT"


@pytest.mark.parametrize(
    "changes",
    [
        {"target_area_mu": "0"},
        {"target_area_mu": "-1"},
        {"target_area_mu": 736},
        {"target_area_mu": "NaN"},
        {"target_area_mu": "0.0000009"},
        {"target_season": "2028-2030"},
        {"target_season": "2025-2026"},
        {"base_or_farm_context": "../private"},
        {"request_id": "../secret"},
    ],
)
async def test_invalid_business_request(runtime: Any, changes: dict[str, Any]) -> None:
    async with Client(server) as client:
        result = await client.call_tool(tools.CREATE, business(**changes))
    assert result.is_error
    assert not list(runtime["store"].glob("predictions/*/record.json"))


@pytest.mark.parametrize(
    "fault",
    [
        "registry_missing",
        "registry_corrupt",
        "content_false",
        "inactive",
        "wrong_role",
        "candidate_missing",
        "candidate_changed",
        "comparator_missing",
        "comparator_changed",
        "store_unavailable",
        "public_declaration",
        "self_hash_invalid",
    ],
)
async def test_runtime_failures_closed(
    runtime: Any, fault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = runtime["registry"]
    data = legacy.read(registry)
    if fault == "registry_missing":
        registry.unlink()
    elif fault == "registry_corrupt":
        registry.write_text("broken")
    elif fault in {"content_false", "inactive", "wrong_role"}:
        key, value = {
            "content_false": ("content_verified", False),
            "inactive": ("active_for_research", False),
            "wrong_role": ("model_role", "PRODUCTION"),
        }[fault]
        reseal(registry, lambda r: r["entries"][0].update({key: value}))
    elif fault == "public_declaration":
        monkeypatch.setenv(
            "V0_12_RESEARCH_RUNTIME_REGISTRY_PATH",
            "configs/v0_12_e1_reported_artifact_registry.json",
        )
        get_settings.cache_clear()
    elif fault == "store_unavailable":
        runtime["store"].write_text("not directory")
    else:
        entry = data["entries"][
            0 if fault.startswith("candidate") or fault == "self_hash_invalid" else 1
        ]
        path = Path(entry["artifact_path"])
        if fault.endswith("missing"):
            await anyio.to_thread.run_sync(path.unlink)
        else:
            model = legacy.read(path)
            model["parameters"]["alpha"] = 999
            await anyio.to_thread.run_sync(path.write_text, json.dumps(model))
            if fault == "self_hash_invalid":
                reseal(
                    registry,
                    lambda r: r["entries"][0].update(
                        {
                            "artifact_file_hash": legacy.file_hash(path),
                            "config_hash": digest(e1.config_snapshot(model)),
                        }
                    ),
                )
    async with Client(server) as client:
        result = await client.call_tool(tools.READINESS, {})
        refused_create = await client.call_tool(tools.CREATE, business())
    assert result.is_error
    assert result.structured_content["code"] == "V0_12_RESEARCH_RUNTIME_NOT_READY"
    assert refused_create.is_error
    assert refused_create.structured_content["code"] == "V0_12_RESEARCH_RUNTIME_NOT_READY"


@pytest.mark.parametrize("name", [tools.GET, tools.VERIFY])
async def test_tampered_record_rejected(runtime: Any, name: str) -> None:
    created = app.create_test_forecast(business())
    path = runtime["store"] / "predictions" / created["forecast_id"] / "record.json"
    changed = legacy.read(path)
    changed["prediction"]["candidate"]["predicted_season_total_kg"] = "1"
    path.write_text(json.dumps(changed))
    async with Client(server) as client:
        result = await client.call_tool(name, {"forecast_id": created["forecast_id"]})
    assert result.is_error
    assert result.structured_content["code"] == "V0_12_RESEARCH_INTEGRITY_FAILURE"


def test_extrapolation_duplicate_concurrency_and_real_rejection(runtime: Any) -> None:
    created = app.create_test_forecast(business(target_area_mu="3000"))
    assert created["area_applicability"]["area_position"] == "EXTRAPOLATION"
    assert created["prospective_accuracy_validated"] is False
    with pytest.raises(ValueError, match="INVALID_REQUEST_DOCUMENT"):
        app.create_test_forecast(business(request_mode="REAL_PROSPECTIVE"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(app.create_test_forecast, business(request_id="CONCURRENT"))
            for _ in range(2)
        ]
    outcomes = []
    for future in futures:
        try:
            outcomes.append(future.result()["forecast_id"])
        except ValueError as exc:
            assert str(exc) == "DUPLICATE_REQUEST_ISSUANCE"
    assert len(outcomes) == 1


@pytest.mark.parametrize("exception", [ValueError, OSError, RuntimeError])
async def test_exception_text_never_leaks(
    runtime: Any, monkeypatch: pytest.MonkeyPatch, exception: type[Exception]
) -> None:
    def broken(*args: Any) -> Any:
        raise exception("/Users/secret/path postgres://user:token alpha=4 stack trace")

    monkeypatch.setattr(app, "create_test_forecast", broken)
    async with Client(server) as client:
        result = await client.call_tool(tools.CREATE, business())
    assert result.is_error
    assert all(
        text not in json.dumps(result.structured_content)
        for text in ("/Users/", "postgres://", "token", "alpha", "stack trace")
    )


async def test_actual_stdio_process(runtime: Any) -> None:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "backend.app.mcp.area_forecast"], env=dict(os.environ)
    )
    async with Client(params) as client:
        assert len((await client.list_tools()).tools) == 14
        assert (await client.call_tool(tools.READINESS, {})).structured_content["E3_COMPLETE"]
        created = (
            await client.call_tool(tools.CREATE, business(request_id="STDIO"))
        ).structured_content
        for name in (tools.GET, tools.VERIFY):
            assert not (
                await client.call_tool(name, {"forecast_id": created["forecast_id"]})
            ).is_error


@pytest.mark.parametrize("path", ["/api/v1/blueberry/v1/mcp/sse", "/api/v1/blueberry/v1/mcp"])
async def test_http_protocol_and_connector(
    runtime: Any, path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BLUEBERRY_MCP_CONNECTOR_SHARED_SECRET", "E4-test-secret")
    get_settings.cache_clear()
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://local"
    ) as client:
        for key in (None, "wrong"):
            response = await client.post(
                path, json={}, headers={} if key is None else {"X-Blueberry-Connector-Key": key}
            )
            assert response.status_code == 401
        client.headers["X-Blueberry-Connector-Key"] = "E4-test-secret"

        async def rpc(method: str, params: dict[str, Any]) -> dict[str, Any]:
            response = await client.post(
                path, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            )
            assert response.status_code == 200
            return cast(dict[str, Any], response.json()["result"])

        await rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "E4-test", "version": "1"},
            },
        )
        assert len((await rpc("tools/list", {}))["tools"]) == 14

        async def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            result = await rpc("tools/call", {"name": name, "arguments": arguments})
            assert result["isError"] is False
            return cast(dict[str, Any], result["structuredContent"])

        await call(tools.READINESS, {})
        created = await call(tools.CREATE, business(request_id="HTTP"))
        for name in (tools.GET, tools.VERIFY):
            await call(name, {"forecast_id": created["forecast_id"]})


async def test_loopback_tcp_http_and_stdio_parity(runtime: Any) -> None:
    # Reuse the existing local FastAPI launcher; no new transport or public tunnel.
    async with running_backend(dict(os.environ)) as http:

        async def rpc(method: str, params: dict[str, Any], path: str) -> dict[str, Any]:
            response = await http.post(
                path, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            )
            assert response.status_code == 200
            return cast(dict[str, Any], response.json()["result"])

        paths = ["/api/v1/blueberry/v1/mcp/sse", "/api/v1/blueberry/v1/mcp"]
        async with Client(
            StdioServerParameters(
                command=sys.executable,
                args=["-m", "backend.app.mcp.area_forecast"],
                env=dict(os.environ),
            )
        ) as stdio:
            expected = (await stdio.list_tools()).tools
            for i, path in enumerate(paths):
                await rpc(
                    "initialize",
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "E4-loopback", "version": "1"},
                    },
                    path,
                )
                listed = await rpc("tools/list", {}, path)
                assert [t["name"] for t in listed["tools"]] == [t.name for t in expected]
                issued = await rpc(
                    "tools/call",
                    {"name": tools.CREATE, "arguments": business(request_id=f"TCP_{i}")},
                    path,
                )
                assert not issued["isError"]
                identity = {"forecast_id": issued["structuredContent"]["forecast_id"]}
                for name in (tools.READINESS, tools.GET, tools.VERIFY):
                    arguments = {} if name == tools.READINESS else identity
                    actual = await rpc("tools/call", {"name": name, "arguments": arguments}, path)
                    result = await stdio.call_tool(name, arguments)
                    assert not actual["isError"] and not result.is_error
                    assert actual["structuredContent"] == result.structured_content


@pytest.mark.parametrize("name", [tools.GET, tools.VERIFY])
async def test_non_test_record_rejected(runtime: Any, name: str) -> None:
    created = app.create_test_forecast(business())
    path = runtime["store"] / "predictions" / created["forecast_id"] / "record.json"
    reseal(path, lambda r: r.update(test_only=False, prospective_class="REAL_ELIGIBLE_PROSPECTIVE"))
    async with Client(server) as client:
        result = await client.call_tool(name, {"forecast_id": created["forecast_id"]})
    assert result.is_error


def test_real_mode_low_level_still_disabled(runtime: Any) -> None:
    from datetime import UTC, datetime

    request = {**runtime["request"], "request_mode": "REAL_PROSPECTIVE"}
    with pytest.raises(ValueError, match="REAL_PROSPECTIVE_NOT_AUTHORIZED"):
        e1.validate_request(request, datetime.now(UTC))


async def test_original_namespace_cannot_bypass_e2_authority(runtime: Any) -> None:
    reseal(runtime["registry"], lambda r: [entry.update(synthetic=False) for entry in r["entries"]])
    async with Client(server) as client:
        refused = await client.call_tool(tools.CREATE, business())
    assert refused.is_error
    assert refused.structured_content["code"] == "V0_12_RESEARCH_RUNTIME_NOT_READY"


async def test_synthetic_entry_cannot_impersonate_original_r1(runtime: Any) -> None:
    registry = legacy.read(runtime["registry"])
    entry = registry["entries"][0]
    path = Path(entry["artifact_path"])
    model = legacy.read(path)
    model["model_id"] = "NEXT_AREA_SIZE_20261002_R1_CANDIDATE"
    model["artifact_hash"] = digest({k: v for k, v in model.items() if k != "artifact_hash"})
    await anyio.to_thread.run_sync(path.write_text, json.dumps(model))
    reseal(
        runtime["registry"],
        lambda r: r["entries"][0].update(
            model_id=model["model_id"],
            registry_id=model["model_id"],
            artifact_hash=model["artifact_hash"],
            artifact_file_hash=legacy.file_hash(path),
        ),
    )
    async with Client(server) as client:
        result = await client.call_tool(tools.CREATE, business())
    assert result.is_error
    assert result.structured_content["code"] == "V0_12_RESEARCH_RUNTIME_NOT_READY"


async def test_missing_record_and_invalid_identity(runtime: Any) -> None:
    async with Client(server) as client:
        missing = await client.call_tool(
            tools.GET, {"forecast_id": "00000000-0000-0000-0000-000000000000"}
        )
        invalid = await client.call_tool(tools.GET, {"forecast_id": "../secret"})
    assert missing.structured_content["code"] == "V0_12_RESEARCH_FORECAST_NOT_FOUND"
    assert invalid.structured_content["reason"] == "INVALID_REQUEST_DOCUMENT"


def test_committed_e4_contract_keeps_scientific_gates_closed() -> None:
    evidence = legacy.read(Path("docs/v0-12/evidence/v0.12-e4-research-mcp-interface-r1.json"))
    assert set(evidence["RESEARCH_MCP_TOOL_NAMES"]) == set(tools.CONTRACTS)
    assert evidence["RESEARCH_MCP_TOOL_COUNT"] == 4
    assert evidence["MCP_TOOL_COUNT_DISABLED"] == 10
    assert evidence["MCP_TOOL_COUNT_ENABLED"] == 14
    for field in (
        "REAL_PROSPECTIVE_ENABLED",
        "STABLE_GAIN_ESTABLISHED",
        "NEW_BLIND_VALIDATION",
        "PROSPECTIVE_ACCURACY_VALIDATED",
        "PRODUCTION_USE_APPROVED",
        "V0_12_S2_AUTHORIZED",
        "V0_12_VERSION_COMPLETE",
        "MODEL_OVERRIDE_EXPOSED",
        "ACTUAL_IMPORT_TOOL_EXPOSED",
        "LOCKED_SCORING_TOOL_EXPOSED",
    ):
        assert evidence[field] is False
    assert evidence["REAL_FORECAST_COUNT"] == 0
