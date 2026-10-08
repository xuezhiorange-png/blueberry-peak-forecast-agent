"""SYNTHETIC=true. Real SDK registry/HTTP calls, isolated saved-run database."""

# Fixture imports intentionally register isolated fixtures in this test module.
# ruff: noqa: F811

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient
from jsonschema import validate
from mcp import Client
from pydantic import SecretStr, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from backend.app.forecast_intelligence.application import execute_hierarchical_run
from backend.app.forecast_intelligence.decision_service import DecisionSupportService
from backend.app.forecast_intelligence.hierarchy import COMPANY_ID
from backend.app.forecast_intelligence.read_access import QualityGrant, RunGrant
from backend.app.forecast_intelligence.read_schemas import QualityReadQuery
from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.mcp.forecast_intelligence_auth import MCPServiceConfig
from backend.app.mcp.forecast_intelligence_http import (
    MCP_BODY_LIMIT,
    MCP_PATH,
    create_forecast_intelligence_app,
)
from backend.app.mcp.forecast_intelligence_server import create_server
from backend.app.mcp.forecast_intelligence_tools import TOOLS, tools
from backend.tests.forecast_intelligence.conftest import (  # noqa: F401
    hierarchy_factory,
    source_ids,
    synthetic_authority,
)
from backend.tests.forecast_intelligence.test_reconciliation import request as hierarchy_request
from backend.tests.forecast_intelligence.test_v0_17_s1_service_read_api import (
    configured_app,
    hierarchy_query,
    query,
)
from backend.tests.forecast_intelligence.test_v0_17_s2_decision_service import (
    comparison_payload,
    request_payload,
)
from backend.tests.forecast_intelligence.test_v0_17_s3_read_access import account

pytestmark = [pytest.mark.unit, pytest.mark.contract]
KEY = "SYNTHETIC_TEST_CREDENTIAL_ONLY"
HEADER = "X-Forecast-Intelligence-Key"
INITIALIZE = {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "SYNTHETIC_ACCEPTANCE", "version": "1"},
}


def config(principal=None, **updates):
    return MCPServiceConfig(
        **(
            dict(
                accounts=(principal or account(),),
                allowed_hosts=("test",),
                allowed_origins=("https://trusted.test",),
                require_https=True,
            )
            | updates
        )
    )


def grant_for(source, **updates):
    grant = RunGrant(
        principal_id="SYNTHETIC_SERVICE",
        forecast_identity=source.forecast_identity,
        source_result_hash=source.source_result_hash,
    )
    return grant.model_copy(update=updates)


def client(app, **kwargs):
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://test",
        headers={HEADER: KEY},
        **kwargs,
    )


async def rpc(c, method, params):
    r = await c.post(MCP_PATH, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")
    assert "mcp-session-id" not in r.headers
    return r.json()


async def call(c, name, arguments):
    value = (await rpc(c, "tools/call", {"name": name, "arguments": arguments}))["result"]
    assert json.loads(value["content"][0]["text"]) == value["structuredContent"]
    schema = next(t.output_schema for t in tools() if t.name == name)
    validate(value["structuredContent"], schema)
    return value


def dead_session():
    pytest.fail("NO_SESSION_ALLOWED")


async def test_sdk_discovery_exact_eight_and_isolated_transport():
    async with Client(create_server(account(), dead_session)) as sdk:
        listing = (await sdk.list_tools()).tools
    assert [t.name for t in listing] == list(TOOLS)
    assert len(listing) == 8
    for tool in listing:
        assert tool.annotations.read_only_hint
        assert tool.annotations.idempotent_hint
        assert not tool.annotations.destructive_hint
        assert "actor" not in tool.input_schema["properties"]
    app = create_forecast_intelligence_app(config(), session_factory=dead_session)
    async with client(app) as c:
        init = (await rpc(c, "initialize", INITIALIZE))["result"]
        assert init["serverInfo"]["name"] == "blueberry-forecast-intelligence-v017"
        listed = (await rpc(c, "tools/list", {}))["result"]
        assert listed["tools"] == [
            t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in listing
        ]
        for path in ("/api/v1/blueberry/v1/mcp", "/api/v1/blueberry/v1/mcp/sse"):
            assert (await c.post(path, json={})).status_code == 404
        for method in ("GET", "PUT", "PATCH", "DELETE"):
            assert (await c.request(method, MCP_PATH)).status_code == 405


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {HEADER: "wrong"},
        {"X-Blueberry-Connector-Key": KEY},
        [(HEADER, KEY), (HEADER, KEY)],
    ],
)
async def test_authentication_before_sdk_or_session(headers):
    app = create_forecast_intelligence_app(config(), session_factory=dead_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c:
        for method in ("initialize", "tools/list", "tools/call"):
            response = await c.post(MCP_PATH, json={"method": method}, headers=headers)
            assert response.status_code == 401
            assert KEY not in response.text and "wrong" not in response.text


async def test_missing_config_fails_closed(monkeypatch):
    monkeypatch.delenv("FORECAST_INTELLIGENCE_MCP_CONFIG", raising=False)
    app = create_forecast_intelligence_app(session_factory=dead_session)
    async with client(app) as c:
        r = await c.post(MCP_PATH, json={})
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "AUTHORIZATION_UNAVAILABLE"


@pytest.mark.parametrize(
    "updates",
    [
        {"allowed_hosts": ("*",)},
        {"allowed_origins": ("*",)},
        {"accounts": ()},
        {"accounts": (account(), account())},
    ],
)
def test_invalid_server_configuration(updates):
    with pytest.raises(ValidationError):
        config(**updates)


@pytest.mark.parametrize(
    "headers",
    [
        {"host": "evil.test"},
        {"origin": "https://evil.test"},
        [("host", "test"), ("host", "test")],
        [("origin", "https://trusted.test"), ("origin", "https://trusted.test")],
    ],
)
async def test_host_origin_never_substitute_authentication(headers):
    app = create_forecast_intelligence_app(config(), session_factory=dead_session)
    async with client(app) as c:
        assert (await c.post(MCP_PATH, json={}, headers=headers)).status_code == 403
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={HEADER: KEY}
    ) as c:
        assert (await c.post(MCP_PATH, json={})).status_code == 403


@pytest.mark.parametrize("name", list(TOOLS))
async def test_permission_denial_no_repository_quality_or_simulation(name, monkeypatch):
    principal = account(
        permissions=frozenset(
            {"may_read_forecast" if name == "get_forecast_quality" else "may_read_quality"}
        )
    )

    def forbidden(*args, **kwargs):
        pytest.fail("BUSINESS_READ_EXECUTED")

    monkeypatch.setattr("backend.app.forecast_intelligence.read_service.public_evidence", forbidden)
    monkeypatch.setattr(DecisionSupportService, "simulate", forbidden)
    app = create_forecast_intelligence_app(config(principal), session_factory=dead_session)
    async with client(app) as c:
        value = await call(c, name, {})
        assert value["isError"] and value["structuredContent"]["code"] == "FORBIDDEN"


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
        {"expected_source_result_hash": "b" * 64},
    ],
)
async def test_ungranted_runs_denied_before_read(updates):
    app = create_forecast_intelligence_app(config(), session_factory=dead_session)
    async with client(app) as c:
        value = await call(c, "get_forecast_curve", query(**updates).model_dump(mode="json"))
        assert value["isError"] and value["structuredContent"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("field", ["actor", "source_system", "permissions", "authority_hash"])
async def test_client_identity_cannot_grant_permissions(field):
    app = create_forecast_intelligence_app(config(), session_factory=dead_session)
    async with client(app) as c:
        value = await call(
            c, "get_forecast_curve", query().model_dump(mode="json") | {field: "fake"}
        )
        assert value["isError"] and value["structuredContent"]["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize("name", list(TOOLS)[:5])
@pytest.mark.parametrize("scope", ["BASE", "REGION", "COMPANY"])
async def test_read_service_http_mcp_payload_parity(
    hierarchy_factory,
    source_ids,
    monkeypatch,
    name,
    scope,
):
    async with hierarchy_factory() as session:
        if scope == "BASE":
            selection = query(source_ids[0])
        else:
            saved = await execute_hierarchical_run(
                session,
                hierarchy_request(
                    source_ids[:2] if scope == "REGION" else source_ids,
                    kind=scope,
                    entity="A" if scope == "REGION" else COMPANY_ID,
                ),
            )
            await session.commit()
            selection = hierarchy_query(saved)
        reader = ForecastIntelligenceReadService(session)
        expected = (await getattr(reader, TOOLS[name].method)(selection)).model_dump(mode="json")
        source = await reader.curve(selection)
    principal = account(run_grants=(grant_for(source),))
    app = create_forecast_intelligence_app(config(principal), session_factory=hierarchy_factory)
    http_app = configured_app(hierarchy_factory, monkeypatch)
    async with (
        client(app) as c,
        AsyncClient(transport=ASGITransport(app=http_app), base_url="http://test") as h,
    ):
        value = await call(c, name, selection.model_dump(mode="json"))
        assert not value["isError"]
        assert value["structuredContent"] == expected
        r = await h.get(
            "/api/v1/forecast-intelligence/" + TOOLS[name].method,
            params=selection.model_dump(mode="json", exclude_none=True),
        )
        assert r.status_code == 200, r.text
        assert r.json() == expected


@pytest.mark.parametrize("mode", ["HISTORICAL_VALIDATION", "CURRENT_PRODUCTION_ACCURACY"])
async def test_quality_parity_without_database(mode, hierarchy_factory, monkeypatch):
    q = QualityReadQuery(mode=mode)
    expected = (await ForecastIntelligenceReadService(None).quality(q)).model_dump(mode="json")
    principal = account(quality_grants=(QualityGrant(mode=mode),))
    app = create_forecast_intelligence_app(config(principal), session_factory=dead_session)
    http_app = configured_app(hierarchy_factory, monkeypatch)
    async with (
        client(app) as c,
        AsyncClient(transport=ASGITransport(app=http_app), base_url="http://test") as h,
    ):
        value = await call(c, "get_forecast_quality", q.model_dump(mode="json"))
        assert not value["isError"] and value["structuredContent"] == expected
        assert (
            await h.get(
                "/api/v1/forecast-intelligence/quality",
                params=q.model_dump(mode="json", exclude_none=True),
            )
        ).json() == expected


@pytest.mark.parametrize(
    "planning", ["POINT", "UPPER_PLANNING_BOUND_80", "UPPER_PLANNING_BOUND_90"]
)
@pytest.mark.parametrize("mode", ["DIRECT", "WORKFORCE_DERIVED"])
@pytest.mark.parametrize("comparison", [False, True])
async def test_decision_service_http_mcp_exact_parity(
    hierarchy_factory,
    source_ids,
    monkeypatch,
    planning,
    mode,
    comparison,
):
    async with hierarchy_factory() as session:
        reader = ForecastIntelligenceReadService(session)
        source = await reader.curve(query(source_ids[0]))
        payload = request_payload(source, mode=mode)
        payload["planning_level"] = planning
        if comparison:
            payload = comparison_payload(payload)
        method = "compare" if comparison else "simulate"
        expected = (await getattr(DecisionSupportService(reader), method)(payload)).model_dump(
            mode="json"
        )
    app = create_forecast_intelligence_app(
        config(account(run_grants=(grant_for(source),))),
        session_factory=hierarchy_factory,
    )
    http_app = configured_app(hierarchy_factory, monkeypatch)
    name = "compare_capacity_scenarios" if comparison else "simulate_capacity"
    path = "compare-capacity-scenarios" if comparison else "simulate-capacity"
    async with (
        client(app) as c,
        AsyncClient(transport=ASGITransport(app=http_app), base_url="http://test") as h,
    ):
        value = await call(c, name, payload)
        assert not value["isError"] and value["structuredContent"] == expected
        r = await h.post("/api/v1/decision-support/" + path, json=payload)
        assert r.status_code == 200 and r.json() == expected
        if planning != "POINT":
            assert expected["status"] == "NOT_AVAILABLE" and expected["data"] is None


async def test_protocol_negotiation_and_resource_limit_recovery():
    app = create_forecast_intelligence_app(config(), session_factory=dead_session)
    async with client(app) as c:
        r = await c.post(MCP_PATH, content=b"x" * (MCP_BODY_LIMIT + 1))
        assert r.status_code == 413
        r = await c.post(MCP_PATH, content=b"{", headers={"content-type": "application/json"})
        assert r.status_code == 400
        r = await c.post(MCP_PATH, json={}, headers={"accept": "text/event-stream"})
        assert r.status_code == 406
        error = await rpc(c, "unknown/method", {})
        assert "error" in error
        assert "result" in await rpc(c, "initialize", INITIALIZE)
        assert "result" in await rpc(c, "tools/list", {})


async def test_concurrent_principal_scope_isolation(hierarchy_factory, source_ids):
    async with hierarchy_factory() as session:
        source = await ForecastIntelligenceReadService(session).curve(query(source_ids[0]))
    first = account(run_grants=(grant_for(source),))
    second = account(
        principal_id="SYNTHETIC_OTHER",
        secret=SecretStr("SYNTHETIC_OTHER_CREDENTIAL"),
        run_grants=(),
        quality_grants=(QualityGrant(mode="HISTORICAL_VALIDATION"),),
    )
    app = create_forecast_intelligence_app(
        config(accounts=(first, second)),
        session_factory=hierarchy_factory,
    )

    async def invoke(secret):
        async with client(app) as c:
            c.headers[HEADER] = secret
            return await call(c, "get_forecast_curve", query(source_ids[0]).model_dump(mode="json"))

    results = await asyncio.gather(
        *(invoke(KEY if i % 2 == 0 else "SYNTHETIC_OTHER_CREDENTIAL") for i in range(8))
    )
    for i, value in enumerate(results):
        assert value["isError"] == bool(i % 2)
        if i % 2:
            assert value["structuredContent"]["code"] == "FORBIDDEN"


async def test_grant_hash_drift_and_persistence_failure_are_redacted(hierarchy_factory, source_ids):
    async with hierarchy_factory() as session:
        source = await ForecastIntelligenceReadService(session).curve(query(source_ids[0]))
    principal = account(run_grants=(grant_for(source, source_result_hash="b" * 64),))
    app = create_forecast_intelligence_app(config(principal), session_factory=hierarchy_factory)
    async with client(app) as c:
        value = await call(c, "get_forecast_curve", query(source_ids[0]).model_dump(mode="json"))
        assert value["isError"] and value["structuredContent"]["code"] == "AUTHORITY_MISMATCH"

    def broken():
        raise SQLAlchemyError("SELECT postgresql://secret@host /private/token")

    app = create_forecast_intelligence_app(config(), session_factory=broken)
    async with client(app) as c:
        value = await call(c, "get_forecast_curve", query().model_dump(mode="json"))
        assert value["structuredContent"]["code"] == "PERSISTENCE_UNAVAILABLE"
        assert all(
            s not in json.dumps(value) for s in ("SELECT", "postgresql", "/private", "secret")
        )
