"""SYNTHETIC=true. Real MCP SDK HTTP and S1 HTTP over the same PostgreSQL authority."""

# Fixture imports register isolated PostgreSQL, never a production database.
# ruff: noqa: F811

import asyncio
import json
import multiprocessing
import socket
import ssl
import subprocess
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx2
import pytest
import uvicorn
from httpx import ASGITransport, AsyncClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr
from sqlalchemy import event, text

from backend.app.forecast_intelligence.application import execute_hierarchical_run
from backend.app.forecast_intelligence.hierarchy import COMPANY_ID
from backend.app.forecast_intelligence.read_schemas import QualityReadQuery
from backend.app.forecast_intelligence.read_service import (
    PUBLIC_EVIDENCE_HASHES,
    ForecastIntelligenceReadService,
)
from backend.app.local_auth.authorization import binding_digest
from backend.app.local_auth.models import AuthResourceGrant
from backend.app.local_auth.sessions import now
from backend.app.mcp.forecast_intelligence_http import MCP_PATH, create_forecast_intelligence_app
from backend.app.mcp.forecast_intelligence_tools import TOOLS, tools
from backend.tests.business_access.test_discovery import app_for, grant
from backend.tests.forecast_intelligence.conftest import seed_sources
from backend.tests.forecast_intelligence.test_reconciliation import request as hierarchy_request
from backend.tests.local_auth.conftest import login, pg_auth, synthetic_authority  # noqa: F401
from backend.tests.mcp.test_v0_17_s3_productization import (
    HEADER,
    KEY,
    account,
    comparison_payload,
    grant_for,
    hierarchy_query,
    query,
    request_payload,
)
from backend.tests.mcp.test_v0_18_s3_policy import document, policy, publish_document_in_process

pytestmark = pytest.mark.postgres


@asynccontextmanager
async def sdk_client(app, key=KEY):
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), headers={HEADER: key}
    ) as http:
        async with streamable_http_client("https://test" + MCP_PATH, http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as sdk:
                await sdk.initialize()
                yield sdk


async def quality_grant(factory, principal):
    async with factory() as db, db.begin():
        db.add(
            AuthResourceGrant(
                principal_id=principal.principal_id,
                resource_kind="QUALITY",
                capability="may_read_quality",
                organization_id="SYNTHETIC_ORG",
                approved_by_principal=principal.principal_id,
                approval_reference="SYNTHETIC",
                reason="SYNTHETIC parity",
                grant_revision=1,
                forecast_binding=None,
                quality_binding={
                    "query": QualityReadQuery().model_dump(mode="json"),
                    "evidence_policy_version": "SYNTHETIC_R1",
                    "source_split": "EXPOSED_OOT",
                    "target_season": "2025-2026",
                    "scope": "BASE_COHORT_AGGREGATE",
                    "evidence_hashes": PUBLIC_EVIDENCE_HASHES,
                    "evidence_set_digest": binding_digest(PUBLIC_EVIDENCE_HASHES),
                },
                valid_from=now() - timedelta(seconds=5),
                valid_until=now() + timedelta(hours=1),
                created_at=now(),
            )
        )


@pytest.mark.parametrize("level", ["BASE", "REGION", "COMPANY"])
async def test_all_eight_sdk_tools_match_authenticated_http(
    pg_auth, synthetic_authority, tmp_path, level
):
    auth, factory, _, user, _ = pg_auth
    ids = await seed_sources(factory, synthetic_authority)
    selected = query(ids[0])
    if level != "BASE":
        async with factory() as db, db.begin():
            saved = await execute_hierarchical_run(
                db,
                hierarchy_request(
                    ids[:2] if level == "REGION" else ids,
                    kind=level,
                    entity="A" if level == "REGION" else COMPANY_ID,
                ),
            )
            selected = hierarchy_query(saved)
    await grant(factory, user, selected)
    await quality_grant(factory, user)
    async with factory() as db:
        source = await ForecastIntelligenceReadService(db).curve(selected)
    provider = policy(tmp_path)
    provider.publish(document(2, accounts=(account(run_grants=(grant_for(source),)),)))
    app = create_forecast_intelligence_app(policy=provider, session_factory=factory)
    async with (
        sdk_client(app) as sdk,
        AsyncClient(
            transport=ASGITransport(app=app_for(auth)), base_url="https://synthetic.test"
        ) as http,
    ):
        assert (await login(http)).status_code == 200
        listing = (await sdk.list_tools()).tools
        assert [t.name for t in listing] == list(TOOLS)
        assert [t.model_dump() for t in listing] == [t.model_dump() for t in tools()]
        for name, tool in list(TOOLS.items())[:6]:
            params = (
                QualityReadQuery().model_dump(mode="json")
                if tool.method == "quality"
                else selected.model_dump(mode="json")
            )
            actual = await sdk.call_tool(name, params)
            response = await http.get(
                "/api/v1/forecast-intelligence/" + tool.method,
                params={k: v for k, v in params.items() if v is not None},
            )
            assert response.status_code == 200, response.text
            assert not actual.is_error
            assert actual.structured_content == response.json()
            assert json.loads(actual.content[0].text) == response.json()
            if tool.method in ("uncertainty", "attribution"):
                assert response.json()["status"] == "NOT_AVAILABLE"
        csrf = (await http.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
        for mode in ("DIRECT", "WORKFORCE_DERIVED"):
            for planning in ("POINT", "UPPER_PLANNING_BOUND_80", "UPPER_PLANNING_BOUND_90"):
                for comparison in (False, True):
                    payload = request_payload(source, mode=mode)
                    payload["planning_level"] = planning
                    if comparison:
                        payload = comparison_payload(payload)
                    name = "compare_capacity_scenarios" if comparison else "simulate_capacity"
                    path = "compare-capacity-scenarios" if comparison else "simulate-capacity"
                    actual = await sdk.call_tool(name, payload)
                    response = await http.post(
                        "/api/v1/decision-support/" + path,
                        json=payload,
                        headers={"Origin": "https://synthetic.test", "X-CSRF-Token": csrf},
                    )
                    assert response.status_code == 200, response.text
                    assert not actual.is_error
                    assert actual.structured_content == response.json()
                    assert json.loads(actual.content[0].text) == response.json()


async def test_revoked_grant_denied_before_postgres_and_simulation(
    pg_auth, synthetic_authority, tmp_path
):
    _, factory, _, _, _ = pg_auth
    ids = await seed_sources(factory, synthetic_authority)
    async with factory() as db:
        source = await ForecastIntelligenceReadService(db).curve(query(ids[0]))
    provider = policy(tmp_path)
    provider.publish(document(2, accounts=(account(run_grants=(grant_for(source),)),)))
    app = create_forecast_intelligence_app(policy=provider, session_factory=factory)
    statements = []

    def observe(conn, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(factory.kw["bind"].sync_engine, "before_cursor_execute", observe)
    try:
        async with sdk_client(app) as sdk:
            provider.publish(document(3, accounts=(account(run_grants=()),)))
            for name, payload in (
                ("get_forecast_curve", query(ids[0]).model_dump(mode="json")),
                ("simulate_capacity", request_payload(source)),
                ("compare_capacity_scenarios", comparison_payload(request_payload(source))),
            ):
                result = await sdk.call_tool(name, payload)
                assert result.is_error and result.structured_content["code"] == "FORBIDDEN"
            assert statements == []
    finally:
        event.remove(factory.kw["bind"].sync_engine, "before_cursor_execute", observe)


@pytest.mark.parametrize("change", ["revoke", "rotate", "disable", "expire"])
async def test_revoke_during_canonical_read_sends_no_sensitive_result(
    pg_auth, synthetic_authority, tmp_path, monkeypatch, change
):
    _, factory, _, _, _ = pg_auth
    ids = await seed_sources(factory, synthetic_authority)
    async with factory() as db:
        source = await ForecastIntelligenceReadService(db).curve(query(ids[0]))
    provider = policy(tmp_path)
    provider.publish(document(2, accounts=(account(run_grants=(grant_for(source),)),)))
    entered, resume = asyncio.Event(), asyncio.Event()
    original = ForecastIntelligenceReadService.curve

    async def delayed(self, selection):
        result = await original(self, selection)
        entered.set()
        await resume.wait()
        return result

    monkeypatch.setattr(ForecastIntelligenceReadService, "curve", delayed)
    app = create_forecast_intelligence_app(policy=provider, session_factory=factory)
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "get_forecast_curve",
                "arguments": query(ids[0]).model_dump(mode="json"),
            },
        }
    ).encode()
    sent = []
    consumed = False

    async def receive():
        nonlocal consumed
        if not consumed:
            consumed = True
            return {"type": "http.request", "body": body}
        await asyncio.Event().wait()

    async def send(message):
        sent.append(message)

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
                    (HEADER.lower().encode(), KEY.encode()),
                ],
            },
            receive,
            send,
        )
    )
    await asyncio.wait_for(entered.wait(), 10)
    replacement = document(3, accounts=(account(run_grants=()),))
    if change == "rotate":
        replacement = document(
            3,
            accounts=(
                account(run_grants=(grant_for(source),), secret=SecretStr("SYNTHETIC_ROTATED_KEY")),
            ),
        )
    elif change == "disable":
        replacement = document(3).model_copy(
            update={"disabled_principals": frozenset({"SYNTHETIC_SERVICE"})}
        )
    elif change == "expire":
        replacement = replacement.model_copy(update={"valid_until": now()})
    context = multiprocessing.get_context("spawn")
    done = context.Event()
    publisher = context.Process(
        target=publish_document_in_process, args=(provider.path, replacement, done)
    )
    publisher.start()
    assert await asyncio.to_thread(done.wait, 10)
    await asyncio.to_thread(publisher.join, 10)
    assert publisher.exitcode == 0
    resume.set()
    await asyncio.wait_for(task, 10)
    assert sent[0]["status"] == 503
    assert source.source_result_hash.encode() not in b"".join(m.get("body", b"") for m in sent)
    assert b"daily_rows" not in b"".join(m.get("body", b"") for m in sent)


async def test_two_dynamic_service_accounts_never_mix_principals(
    pg_auth, synthetic_authority, tmp_path
):
    _, factory, _, _, _ = pg_auth
    ids = await seed_sources(factory, synthetic_authority)
    async with factory() as db:
        first = await ForecastIntelligenceReadService(db).curve(query(ids[0]))
        second = await ForecastIntelligenceReadService(db).curve(query(ids[1], entity_id="A2"))
    other = account(
        principal_id="SYNTHETIC_OTHER",
        secret=SecretStr("SYNTHETIC_OTHER_KEY"),
        run_grants=(grant_for(second, principal_id="SYNTHETIC_OTHER"),),
        quality_grants=(),
    )
    provider = policy(tmp_path)
    provider.publish(document(2, accounts=(account(run_grants=(grant_for(first),)), other)))
    app = create_forecast_intelligence_app(policy=provider, session_factory=factory)

    async def invoke(index):
        selected = index % 2
        async with sdk_client(app, KEY if selected == 0 else "SYNTHETIC_OTHER_KEY") as sdk:
            own = await sdk.call_tool(
                "get_forecast_curve",
                query(ids[selected], entity_id="A1" if selected == 0 else "A2").model_dump(
                    mode="json"
                ),
            )
            denied = await sdk.call_tool(
                "get_forecast_curve",
                query(ids[1 - selected], entity_id="A2" if selected == 0 else "A1").model_dump(
                    mode="json"
                ),
            )
            assert (
                own.structured_content["forecast_identity"]["entity_id"]
                == (first if selected == 0 else second).forecast_identity.entity_id
            )
            assert not own.is_error and denied.is_error
            assert denied.structured_content["code"] == "FORBIDDEN"
            if selected:
                quality = await sdk.call_tool("get_forecast_quality", {})
                assert quality.is_error and quality.structured_content["code"] == "FORBIDDEN"

    await asyncio.gather(*(invoke(i) for i in range(6)))


@pytest.mark.parametrize("damage", ["hash", "delete"])
async def test_canonical_hash_drift_or_deleted_record_cannot_return_data(
    pg_auth, synthetic_authority, tmp_path, damage
):
    _, factory, _, _, _ = pg_auth
    ids = await seed_sources(factory, synthetic_authority)
    selected = query(ids[0])
    async with factory() as db:
        source = await ForecastIntelligenceReadService(db).curve(selected)
    provider = policy(tmp_path)
    provider.publish(document(2, accounts=(account(run_grants=(grant_for(source),)),)))
    # Intentional corruption ONLY in the fixture-owned, disposable PostgreSQL DB.
    async with factory() as db, db.begin():
        await db.execute(
            text(
                "DROP TRIGGER operational_peak_forecast_run_immutable "
                "ON operational_peak_forecast_run"
            )
        )
        if damage == "hash":
            await db.execute(
                text("UPDATE operational_peak_forecast_run SET result_hash=:hash WHERE id=:id"),
                {"hash": "b" * 64, "id": ids[0]},
            )
        else:
            await db.execute(
                text(
                    "DROP TRIGGER operational_peak_forecast_daily_immutable "
                    "ON operational_peak_forecast_daily"
                )
            )
            await db.execute(
                text("DELETE FROM operational_peak_forecast_daily WHERE run_id=:id"), {"id": ids[0]}
            )
            await db.execute(
                text("DELETE FROM operational_peak_forecast_run WHERE id=:id"), {"id": ids[0]}
            )
    app = create_forecast_intelligence_app(policy=provider, session_factory=factory)
    async with sdk_client(app) as sdk:
        result = await sdk.call_tool("get_forecast_curve", selected.model_dump(mode="json"))
        assert result.is_error
        assert result.structured_content["data"] is None
        assert result.structured_content["code"] == (
            "SAVED_RUN_INTEGRITY_FAILED" if damage == "hash" else "SAVED_RUN_NOT_FOUND"
        )


async def test_real_tls_loopback_sdk_reads_canonical_postgres(
    pg_auth, synthetic_authority, tmp_path
):
    _, factory, _, _, _ = pg_auth
    ids = await seed_sources(factory, synthetic_authority)
    selected = query(ids[0])
    async with factory() as db:
        source = await ForecastIntelligenceReadService(db).curve(selected)
    key, cert = tmp_path / "synthetic.key", tmp_path / "synthetic.crt"
    generated = await asyncio.to_thread(
        subprocess.run,
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=SYNTHETIC_TEST_ONLY",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        capture_output=True,
        check=False,
    )
    assert generated.returncode == 0
    key.chmod(0o600)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    provider = policy(tmp_path)
    provider.publish(
        document(
            2,
            accounts=(account(run_grants=(grant_for(source),)),),
            allowed_hosts=(f"127.0.0.1:{port}",),
        )
    )
    app = create_forecast_intelligence_app(policy=provider, session_factory=factory)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            ssl_keyfile=str(key),
            ssl_certfile=str(cert),
            lifespan="off",
            log_level="warning",
            timeout_graceful_shutdown=1,
        )
    )
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                    pytest.fail("TLS_TEST_SERVER_NOT_STARTED")
                await asyncio.sleep(0)
        context = ssl.create_default_context(cafile=str(cert))
        async with httpx2.AsyncClient(verify=context, headers={HEADER: KEY}) as http:
            async with streamable_http_client(
                f"https://127.0.0.1:{port}" + MCP_PATH, http_client=http
            ) as streams:
                async with ClientSession(streams[0], streams[1]) as sdk:
                    await sdk.initialize()
                    assert len((await sdk.list_tools()).tools) == 8
                    value = await sdk.call_tool(
                        "get_forecast_curve", selected.model_dump(mode="json")
                    )
                    assert not value.is_error
                    assert value.structured_content == source.model_dump(mode="json")
                    assert json.loads(value.content[0].text) == value.structured_content
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        listener.close()
    assert task.done() and listener.fileno() == -1
