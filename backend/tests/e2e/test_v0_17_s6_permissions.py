"""SYNTHETIC=true. R2 exact grants on the same canonical SQLite authority."""
# ruff: noqa: F811

import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import event

from backend.app.actual_harvest_import.api_auth import get_actual_harvest_actor
from backend.app.db.session import get_db_session
from backend.app.forecast_intelligence.read_access import QualityGrant
from backend.app.mcp.forecast_intelligence_auth import MCPServiceConfig
from backend.app.mcp.forecast_intelligence_http import MCP_PATH, create_forecast_intelligence_app
from backend.tests.e2e.test_v0_17_s6_cross_surface_parity import environment, scenario  # noqa: F401
from frontend.e2e.support import s6_api as harness

pytestmark = [pytest.mark.unit, pytest.mark.contract]


@pytest.mark.parametrize("scope", [0, 1, 2, 3])
async def test_sdk_explicit_grant_never_implies_other_scopes(environment, scope):
    app, _ = environment
    principal = app.state.account.model_copy(
        update={"run_grants": (app.state.account.run_grants[scope],)}
    )
    counts = {"sessions": 0}

    @asynccontextmanager
    async def counted():
        counts["sessions"] += 1
        async with app.state.sessions() as session:
            yield session

    app.state.mcp = create_forecast_intelligence_app(
        MCPServiceConfig(accounts=(principal,), allowed_hosts=("s6.test",), allowed_origins=()),
        session_factory=counted,
    )
    async with harness.sdk_client(app) as sdk:
        for index, identity in enumerate(harness.seed.STATE["identities"]):
            before = counts["sessions"]
            result = await harness.sdk_call(sdk, "get_forecast_curve", identity)
            assert result.is_error == (index != scope)
            if index != scope:
                assert result.structured_content["code"] == "FORBIDDEN"
                assert counts["sessions"] == before
            else:
                assert result.structured_content == harness.seed.STATE["canonical_curves"][index]
        query = {**harness.seed.STATE["identities"][scope], "expected_source_result_hash": "0" * 64}
        before = counts["sessions"]
        result = await harness.sdk_call(sdk, "get_forecast_curve", query)
        assert result.is_error and result.structured_content["code"] == "FORBIDDEN"
        assert counts["sessions"] == before


async def test_sdk_concurrent_principals_and_quality_grants(environment, monkeypatch):
    app, _ = environment
    first = app.state.account.model_copy(update={"run_grants": app.state.account.run_grants[:1]})
    second = first.model_copy(
        update={
            "principal_id": "SYNTHETIC_SECOND",
            "secret": SecretStr("SYNTHETIC_SECOND_KEY"),
            "run_grants": (),
            "quality_grants": (QualityGrant(mode="HISTORICAL_VALIDATION"),),
        }
    )
    app.state.mcp = create_forecast_intelligence_app(
        MCPServiceConfig(accounts=(first, second), allowed_hosts=("s6.test",), allowed_origins=()),
        session_factory=app.state.sessions,
    )

    async def invoke(index):
        async with harness.sdk_client(
            app, harness.TEST_KEY if index % 2 == 0 else "SYNTHETIC_SECOND_KEY"
        ) as sdk:
            result = await harness.sdk_call(
                sdk, "get_forecast_curve", harness.seed.STATE["identities"][0]
            )
            assert result.is_error == bool(index % 2)
            if index % 2:
                assert result.structured_content["code"] == "FORBIDDEN"

    await asyncio.gather(*(invoke(i) for i in range(8)))

    def no_files():
        pytest.fail("UNAUTHORIZED_QUALITY_FILE_READ")

    monkeypatch.setattr("backend.app.forecast_intelligence.read_service.public_evidence", no_files)
    async with harness.sdk_client(app, "SYNTHETIC_SECOND_KEY") as sdk:
        value = await harness.sdk_call(
            sdk, "get_forecast_quality", {"mode": "CURRENT_PRODUCTION_ACCURACY"}
        )
        assert value.is_error and value.structured_content["code"] == "FORBIDDEN"


@pytest.mark.parametrize(
    "case,status",
    [
        ("missing", 401),
        ("wrong", 401),
        ("duplicate", 401),
        ("host", 403),
        ("origin", 403),
        ("http", 403),
        ("oversize", 413),
        ("config", 503),
    ],
)
async def test_transport_denial_without_session(environment, case, status, monkeypatch):
    app, _ = environment

    def no_session():
        pytest.fail("UNAUTHORIZED_REPOSITORY_READ")

    monkeypatch.delenv("FORECAST_INTELLIGENCE_MCP_CONFIG", raising=False)
    config = (
        None
        if case == "config"
        else MCPServiceConfig(
            accounts=(app.state.account,), allowed_hosts=("s6.test",), allowed_origins=()
        )
    )
    mcp = create_forecast_intelligence_app(config, session_factory=no_session)
    headers = [("X-Forecast-Intelligence-Key", harness.TEST_KEY)]
    if case == "missing":
        headers = []
    if case == "wrong":
        headers = [("X-Forecast-Intelligence-Key", "SYNTHETIC_WRONG")]
    if case == "duplicate":
        headers *= 2
    if case == "host":
        headers.append(("host", "untrusted.test"))
    if case == "origin":
        headers.append(("origin", "https://untrusted.test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mcp),
        base_url=("http" if case == "http" else "https") + "://s6.test",
    ) as client:
        result = await client.post(
            MCP_PATH, content=b"x" * 262145 if case == "oversize" else b"{}", headers=headers
        )
        assert result.status_code == status
        assert harness.TEST_KEY not in result.text


@pytest.mark.parametrize("code", [401, 403, 404, 409, 413, 422, 503])
async def test_http_status_matrix_authorization_before_read(environment, code):
    app, http = environment
    identity = dict(harness.seed.STATE["identities"][0])
    original_actor = app.dependency_overrides[get_actual_harvest_actor]
    original_session = app.dependency_overrides[get_db_session]
    count = 0
    sql = []

    def audit(conn, cursor, statement, parameters, context, executemany):
        sql.append(statement)

    async def counted():
        nonlocal count
        count += 1
        async for session in original_session():
            engine = session.bind.sync_engine
            event.listen(engine, "before_cursor_execute", audit)
            try:
                yield session
            finally:
                event.remove(engine, "before_cursor_execute", audit)

    app.dependency_overrides[get_db_session] = counted
    if code in (401, 403, 503):

        async def denied():
            # 401 is trusted upstream rejection, not an invented login/ACL system.
            raise HTTPException(
                code,
                detail={
                    "code": "UNAUTHENTICATED"
                    if code == 401
                    else "FORBIDDEN"
                    if code == 403
                    else "AUTHORIZATION_UNAVAILABLE"
                },
            )

        app.dependency_overrides[get_actual_harvest_actor] = denied
    elif code == 404:
        identity["run_id"] = 999999
    elif code == 409:
        identity["expected_source_result_hash"] = "0" * 64
    elif code == 422:
        identity["run_id"] = "invalid"
    try:
        if code == 413:
            result = await http.post(
                "/api/v1/decision-support/simulate-capacity",
                content=b"x" * 131073,
                headers={"content-type": "application/json"},
            )
        else:
            result = await http.get("/api/v1/forecast-intelligence/curve", params=identity)
        assert result.status_code == code
        assert all(
            s not in result.text
            for s in ("SELECT ", "postgresql://", "Traceback", "/private/", harness.TEST_KEY)
        )
        if code in (401, 403, 503):
            # FastAPI constructs its lazy session dependency before actor;
            # session construction is not a repository/SQL read.
            assert count == 1
            assert sql == []
    finally:
        app.dependency_overrides[get_actual_harvest_actor] = original_actor
        app.dependency_overrides[get_db_session] = original_session
    # Exact same valid identity succeeds after denial/error; never mutate previous authority.
    restored = await http.get(
        "/api/v1/forecast-intelligence/curve", params=harness.seed.STATE["identities"][0]
    )
    assert restored.status_code == 200
    assert restored.json() == harness.seed.STATE["canonical_curves"][0]


@pytest.mark.parametrize("name", ["simulate_capacity", "compare_capacity_scenarios"])
async def test_denied_decisions_execute_no_business(environment, name, monkeypatch):
    app, _ = environment
    payload = scenario(harness.seed.STATE["canonical_curves"][1])
    if name == "compare_capacity_scenarios":
        rows = {k: payload.pop(k) for k in ("scenario_id", "scenario_version", "capacity_rows")}
        payload["scenarios"] = [rows, {**rows, "scenario_id": "C"}]
    principal = app.state.account.model_copy(
        update={"run_grants": app.state.account.run_grants[:1]}
    )

    def forbidden(*args, **kwargs):
        pytest.fail("UNAUTHORIZED_BUSINESS_EXECUTION")

    monkeypatch.setattr(
        "backend.app.forecast_intelligence.decision_service.DecisionSupportService.simulate",
        forbidden,
    )
    monkeypatch.setattr(
        "backend.app.forecast_intelligence.decision_service.DecisionSupportService.compare",
        forbidden,
    )
    app.state.mcp = create_forecast_intelligence_app(
        MCPServiceConfig(accounts=(principal,), allowed_hosts=("s6.test",), allowed_origins=()),
        session_factory=forbidden,
    )
    async with harness.sdk_client(app) as sdk:
        value = await harness.sdk_call(sdk, name, payload)
        assert value.is_error and value.structured_content["code"] == "FORBIDDEN"
