"""SYNTHETIC=true. Current-policy authentication and cross-process release locks."""

import asyncio
import json
import multiprocessing
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr

from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.mcp.forecast_intelligence_http import (
    MCP_PATH,
    create_forecast_intelligence_app,
    create_service_account_app,
)
from backend.app.mcp.forecast_intelligence_policy import FilePolicy, PolicyDocument
from backend.app.mcp.forecast_intelligence_tools import TOOLS
from backend.tests.mcp.test_v0_17_s3_productization import (
    KEY,
    account,
    call,
    client,
    config,
    dead_session,
    query,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def document(revision=1, **updates):
    return PolicyDocument(
        revision=revision,
        valid_until=datetime.now(UTC) + timedelta(minutes=5),
        config=config(**updates),
    )


def policy(tmp_path):
    directory = tmp_path / "trusted"
    directory.mkdir(mode=0o700)
    provider = FilePolicy(directory / "policy.json")
    provider.publish(document())
    return provider


def publish_in_process(path, ready, done):
    provider = FilePolicy(path)
    ready.set()
    provider.publish(document(2))
    done.set()


def publish_document_in_process(path, replacement, done):
    FilePolicy(path).publish(replacement)
    done.set()


async def test_process_writer_waits_for_sensitive_response_release(tmp_path):
    provider = policy(tmp_path)
    snapshot = await provider.snapshot()
    ctx = multiprocessing.get_context("spawn")
    ready, done = ctx.Event(), ctx.Event()
    process = ctx.Process(target=publish_in_process, args=(provider.path, ready, done))
    async with provider.release(snapshot):
        process.start()
        assert await asyncio.to_thread(ready.wait, 10)
        assert not await asyncio.to_thread(done.wait, 0.2)
    assert await asyncio.to_thread(done.wait, 10)
    await asyncio.to_thread(process.join, 10)
    assert process.exitcode == 0
    assert (await provider.snapshot()).document.revision == 2


async def test_rotation_and_revocation_visible_to_already_created_app(tmp_path, monkeypatch):
    provider = policy(tmp_path)
    monkeypatch.setenv("FORECAST_INTELLIGENCE_MCP_POLICY_FILE", str(provider.path))
    app = create_service_account_app()
    async with client(app) as http:
        assert not (await call(http, "get_forecast_quality", {}))["isError"]
        provider.publish(document(2, accounts=(account(secret=SecretStr("SYNTHETIC_NEW_KEY")),)))
        assert (await http.post(MCP_PATH, json={})).status_code == 401
        http.headers["X-Forecast-Intelligence-Key"] = "SYNTHETIC_NEW_KEY"
        assert not (await call(http, "get_forecast_quality", {}))["isError"]
    assert KEY != "SYNTHETIC_NEW_KEY"


async def test_old_revision_never_released_and_expiry_fails_closed(tmp_path):
    provider = policy(tmp_path)
    snapshot = await provider.snapshot()
    provider.publish(document(2))
    with pytest.raises(ValueError, match="AUTHORIZATION_CHANGED"):
        async with provider.release(snapshot):
            pytest.fail("SENSITIVE_RESPONSE_RELEASED")
    provider.publish(document(3).model_copy(update={"valid_until": datetime.now(UTC)}))
    with pytest.raises(ValueError, match="AUTHORIZATION_UNAVAILABLE"):
        await provider.snapshot()


async def test_last_service_account_can_be_disabled_without_placeholder_identity(tmp_path):
    provider = policy(tmp_path)
    app = create_forecast_intelligence_app(policy=provider, session_factory=dead_session)
    provider.publish(
        document(2).model_copy(update={"disabled_principals": frozenset({"SYNTHETIC_SERVICE"})})
    )
    async with client(app) as http:
        response = await http.post(MCP_PATH, json={})
        assert response.status_code == 401


def test_publisher_rejects_revision_reuse_and_insecure_directory(tmp_path):
    provider = policy(tmp_path)
    with pytest.raises(ValueError):
        provider.publish(document())
    provider.path.parent.chmod(0o755)
    with pytest.raises(ValueError):
        provider.publish(document(2))


@pytest.mark.parametrize(
    "headers,scheme,status",
    [
        ({"X-Forecast-Intelligence-Key": "wrong"}, "https", 401),
        ([("X-Forecast-Intelligence-Key", KEY)] * 2, "https", 401),
        ({"host": "evil.test"}, "https", 403),
        ({"origin": "https://evil.test"}, "https", 403),
        ({}, "http", 403),
    ],
)
async def test_dynamic_transport_keeps_authentication_and_tls_fail_closed(
    tmp_path, headers, scheme, status
):
    provider = policy(tmp_path)
    app = create_forecast_intelligence_app(policy=provider)
    async with client(app) as http:
        response = await http.post(scheme + "://test" + MCP_PATH, json={}, headers=headers)
        assert response.status_code == status
        assert KEY not in response.text
        assert response.headers["cache-control"] == "no-store"


async def test_missing_malformed_symlink_policy_and_environment_fail_closed(tmp_path, monkeypatch):
    provider = policy(tmp_path)
    app = create_forecast_intelligence_app(policy=provider)
    provider.path.write_bytes(b"SYNTHETIC_INVALID_JSON")
    async with client(app) as http:
        assert (await http.post(MCP_PATH, json={})).status_code == 503
    provider.path.unlink()
    provider.path.symlink_to(tmp_path / "does-not-exist")
    async with client(app) as http:
        assert (await http.post(MCP_PATH, json={})).status_code == 503
    monkeypatch.delenv("FORECAST_INTELLIGENCE_MCP_POLICY_FILE", raising=False)
    monkeypatch.setenv("FORECAST_INTELLIGENCE_MCP_CONFIG", config().model_dump_json())
    async with client(create_service_account_app()) as http:
        # Static environment snapshots are not an operational revocation source.
        assert (await http.post(MCP_PATH, json={})).status_code == 503


async def test_timeout_cancellation_and_recovery_with_live_policy(tmp_path, monkeypatch):
    from backend.app.mcp import forecast_intelligence_http as transport

    provider = policy(tmp_path)
    app = create_forecast_intelligence_app(policy=provider)
    entered, exited = asyncio.Event(), asyncio.Event()
    original = ForecastIntelligenceReadService.quality

    async def delayed(self, query):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            exited.set()

    monkeypatch.setattr(ForecastIntelligenceReadService, "quality", delayed)
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "get_forecast_quality", "arguments": {}},
    }
    async with client(app) as http:
        request = asyncio.create_task(http.post(MCP_PATH, json=payload))
        await asyncio.wait_for(entered.wait(), 5)
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        await asyncio.wait_for(exited.wait(), 5)
        monkeypatch.setattr(transport, "EXECUTION_SECONDS", 0.05)
        response = await http.post(MCP_PATH, json=payload)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "EXECUTION_TIMEOUT"
        monkeypatch.setattr(ForecastIntelligenceReadService, "quality", original)
        monkeypatch.setattr(transport, "EXECUTION_SECONDS", 30)
        provider.publish(document(2))
        assert (await http.post(MCP_PATH, json=payload)).json()["result"]["isError"] is False


async def test_actual_asgi_send_holds_release_lock_and_cancel_frees_it(tmp_path):
    provider = policy(tmp_path)
    app = create_forecast_intelligence_app(policy=provider)
    context = multiprocessing.get_context("spawn")
    ready, done = context.Event(), context.Event()
    publisher = context.Process(target=publish_in_process, args=(provider.path, ready, done))
    sending = asyncio.Event()
    sent = []
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_forecast_quality", "arguments": {}},
        }
    ).encode()
    consumed = False

    async def receive():
        nonlocal consumed
        if not consumed:
            consumed = True
            return {"type": "http.request", "body": body}
        await asyncio.Event().wait()

    async def send(message):
        sent.append(message)
        if message["type"] == "http.response.start":
            sending.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(
        app(
            {
                "type": "http",
                "method": "POST",
                "path": MCP_PATH,
                "scheme": "https",
                "query_string": b"",
                "headers": [
                    (b"host", b"test"),
                    (b"content-type", b"application/json"),
                    (b"accept", b"application/json"),
                    (b"x-forecast-intelligence-key", KEY.encode()),
                ],
            },
            receive,
            send,
        )
    )
    await asyncio.wait_for(sending.wait(), 10)
    publisher.start()
    assert await asyncio.to_thread(ready.wait, 10)
    assert not await asyncio.to_thread(done.wait, 0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await asyncio.to_thread(done.wait, 10)
    await asyncio.to_thread(publisher.join, 10)
    assert publisher.exitcode == 0
    assert all(m["type"] != "http.response.body" for m in sent)


@pytest.mark.parametrize("name", list(TOOLS))
async def test_latest_policy_capability_denial_before_any_business_execution(
    tmp_path, monkeypatch, name
):
    from backend.app.forecast_intelligence.decision_service import DecisionSupportService

    def forbidden(*args, **kwargs):
        pytest.fail("UNAUTHORIZED_BUSINESS_EXECUTION")

    monkeypatch.setattr("backend.app.forecast_intelligence.read_service.public_evidence", forbidden)
    monkeypatch.setattr(DecisionSupportService, "simulate", forbidden)
    monkeypatch.setattr(DecisionSupportService, "compare", forbidden)
    provider = policy(tmp_path)
    permissions = frozenset(
        {"may_read_forecast" if name == "get_forecast_quality" else "may_read_quality"}
    )
    provider.publish(document(2, accounts=(account(permissions=permissions),)))
    app = create_forecast_intelligence_app(policy=provider, session_factory=dead_session)
    async with client(app) as http:
        result = await call(http, name, {})
        assert result["isError"] and result["structuredContent"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize(
    "updates",
    [
        {"run_id": 999},
        {"entity_id": "A2"},
        {"hierarchy_level": "REGION"},
        {"hierarchy_level": "COMPANY"},
        {"target_season": "2026-2027"},
        {"forecast_family": "OTHER"},
        {"baseline_id": "OTHER"},
        {"policy_version": "OTHER"},
        {"expected_source_result_hash": "b" * 64},
    ],
)
async def test_latest_policy_exact_grant_denial_before_canonical_read(tmp_path, updates):
    provider = policy(tmp_path)
    app = create_forecast_intelligence_app(policy=provider, session_factory=dead_session)
    async with client(app) as http:
        result = await call(http, "get_forecast_curve", query(**updates).model_dump(mode="json"))
        assert result["isError"] and result["structuredContent"]["code"] == "FORBIDDEN"


async def test_dedicated_dynamic_app_has_no_legacy_or_business_discovery_routes(tmp_path):
    app = create_forecast_intelligence_app(policy=policy(tmp_path), session_factory=dead_session)
    async with client(app) as http:
        for path in (
            "/api/v1/blueberry/v1/mcp",
            "/api/v1/blueberry/v1/mcp/sse",
            "/trial/forecast",
            "/api/v1/business-access/saved-runs",
        ):
            assert (await http.post(path, json={})).status_code == 404


async def test_disconnect_after_body_cancels_running_sdk_work_and_sends_nothing(
    tmp_path, monkeypatch
):
    provider = policy(tmp_path)
    app = create_forecast_intelligence_app(policy=provider, session_factory=dead_session)
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def delayed(self, query):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(ForecastIntelligenceReadService, "quality", delayed)
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_forecast_quality", "arguments": {}},
        }
    ).encode()
    consumed = False
    sent = []

    async def receive():
        nonlocal consumed
        if not consumed:
            consumed = True
            return {"type": "http.request", "body": body}
        await entered.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    async with asyncio.timeout(10):
        await app(
            {
                "type": "http",
                "method": "POST",
                "path": MCP_PATH,
                "scheme": "https",
                "query_string": b"",
                "headers": [
                    (b"host", b"test"),
                    (b"content-type", b"application/json"),
                    (b"accept", b"application/json"),
                    (b"x-forecast-intelligence-key", KEY.encode()),
                ],
            },
            receive,
            send,
        )
    assert cancelled.is_set() and sent == []
