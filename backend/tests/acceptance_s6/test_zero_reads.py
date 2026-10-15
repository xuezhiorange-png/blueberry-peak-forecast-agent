"""Observe real work, not just denials, at real HTTPS HTTP and MCP entrances."""

import json
import ssl
from contextlib import contextmanager

import httpx
import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import event

from backend.app.db import session as database_session
from backend.app.forecast_intelligence import read_service, what_if
from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.local_auth.models import AuthAccount
from backend.app.mcp.forecast_intelligence_http import MCP_PATH, create_service_account_app
from backend.tests.acceptance_s6.test_tls_authority import write
from backend.tests.mcp.test_v0_17_s3_productization import (
    HEADER,
    KEY,
    account,
    grant_for,
    request_payload,
)
from backend.tests.mcp.test_v0_18_s3_policy import document, policy
from backend.tests.mcp.test_v0_18_s3_postgres import quality_grant
from backend.tests.safe_pilot.operations import tls_server
from backend.tests.safe_pilot.test_restore_and_ingress import application, seed, sign_in

pytestmark = pytest.mark.postgres


@contextmanager
def observe_sensitive_work(factory, monkeypatch):
    counts = {
        "BUSINESS_READ_COUNT": 0,
        "QUALITY_FILE_READ_COUNT": 0,
        "SIMULATION_EXECUTION_COUNT": 0,
        "AUTHORIZATION_METADATA_READ_COUNT": 0,
    }

    def sql_observer(conn, cursor, statement, parameters, context, many):
        del conn, cursor, parameters, context, many
        sql = statement.lower().lstrip()
        if sql.startswith("select"):
            if "operational_peak_forecast" in sql or "hierarchical_forecast" in sql:
                counts["BUSINESS_READ_COUNT"] += 1
            elif "auth_" in sql:
                counts["AUTHORIZATION_METADATA_READ_COUNT"] += 1

    original_evidence, original_simulate = read_service.public_evidence, what_if.simulate

    def evidence():
        # Every fixed evidence-file read occurs inside this exact synchronous
        # boundary. Denial must not enter it; successful reads still call it.
        counts["QUALITY_FILE_READ_COUNT"] += 1
        return original_evidence()

    def simulate(*args, **kwargs):
        counts["SIMULATION_EXECUTION_COUNT"] += 1
        return original_simulate(*args, **kwargs)

    event.listen(factory.kw["bind"].sync_engine, "before_cursor_execute", sql_observer)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(read_service, "public_evidence", evidence)
            patch.setattr(what_if, "simulate", simulate)
            yield counts
    finally:
        event.remove(factory.kw["bind"].sync_engine, "before_cursor_execute", sql_observer)


def assert_zero(counts):
    assert {k: v for k, v in counts.items() if k != "AUTHORIZATION_METADATA_READ_COUNT"} == {
        "BUSINESS_READ_COUNT": 0,
        "QUALITY_FILE_READ_COUNT": 0,
        "SIMULATION_EXECUTION_COUNT": 0,
    }


async def test_s6_observers_detect_actual_allowed_work(pg_auth, tmp_path, monkeypatch):
    """Positive controls prevent broken observers from producing false zero proof."""
    auth, factory, _, user, _ = pg_auth
    selected, _ = await seed(factory, user)
    await quality_grant(factory, user)
    async with factory() as db:
        source = await ForecastIntelligenceReadService(db).curve(selected)
    async with tls_server(application(auth), tmp_path) as (origin, cert, _):
        auth.settings.local_auth_origin = origin
        async with httpx.AsyncClient(
            base_url=origin, verify=ssl.create_default_context(cafile=str(cert))
        ) as http:
            await sign_in(http)
            with observe_sensitive_work(factory, monkeypatch) as counts:
                assert (
                    await http.get(
                        "/api/v1/forecast-intelligence/curve",
                        params=selected.model_dump(mode="json"),
                    )
                ).status_code == 200
                assert (await http.get("/api/v1/forecast-intelligence/quality")).status_code == 200
                assert (
                    await write(
                        http,
                        origin,
                        "/api/v1/decision-support/simulate-capacity",
                        request_payload(source),
                    )
                ).status_code == 200
                assert all(value > 0 for value in counts.values())


@pytest.mark.parametrize(
    "denial",
    [
        "missing_cookie",
        "wrong_hash",
        "foreign_run",
        "foreign_season",
        "foreign_family",
        "no_quality",
        "admin",
    ],
)
async def test_s6_http_denies_before_sensitive_work(
    pg_auth, tmp_path, monkeypatch, record_property, denial
):
    auth, factory, _, user, _ = pg_auth
    selected, _ = await seed(factory, user)
    async with factory() as db:
        source = await ForecastIntelligenceReadService(db).curve(selected)
    if denial == "admin":
        async with factory() as db, db.begin():
            subject = await db.get(AuthAccount, user.account_id)
            subject.role = "ADMIN"
        # ADMIN itself grants nothing: request a different ungranted identity.
    changes = {
        "wrong_hash": {"expected_source_result_hash": "0" * 64},
        "foreign_run": {"run_id": 999999},
        "foreign_season": {"target_season": "2024-2025"},
        "foreign_family": {"forecast_family": "SYNTHETIC_OTHER_FAMILY"},
        "admin": {"run_id": 999999},
    }
    query = selected.model_dump(mode="json") | changes.get(denial, {})
    payload = request_payload(source)
    payload["forecast_selection"] = {
        k: v for k, v in query.items() if k != "expected_source_result_hash"
    }
    payload["expected_source_result_hash"] = query["expected_source_result_hash"]
    async with tls_server(application(auth), tmp_path) as (origin, cert, _):
        auth.settings.local_auth_origin = origin
        async with httpx.AsyncClient(
            base_url=origin, verify=ssl.create_default_context(cafile=str(cert))
        ) as http:
            if denial != "missing_cookie":
                await sign_in(http)
            with observe_sensitive_work(factory, monkeypatch) as counts:
                if denial == "no_quality":
                    response = await http.get("/api/v1/forecast-intelligence/quality")
                else:
                    response = await http.get("/api/v1/forecast-intelligence/curve", params=query)
                assert response.status_code == (401 if denial == "missing_cookie" else 403)
                assert response.json()["data"] is None
                assert response.headers["cache-control"] == "no-store"
                if denial not in {"missing_cookie", "no_quality"}:
                    simulated = await write(
                        http, origin, "/api/v1/decision-support/simulate-capacity", payload
                    )
                    assert simulated.status_code == 403 and simulated.json()["data"] is None
                assert_zero(counts)
                record_property("S6_ZERO_READ_PROOF", json.dumps(counts, sort_keys=True))


async def test_s6_mcp_no_exact_or_quality_grant_has_zero_sensitive_work(
    pg_auth, tmp_path, monkeypatch, record_property
):
    _, factory, _, user, _ = pg_auth
    selected, _ = await seed(factory, user)
    async with factory() as db:
        source = await ForecastIntelligenceReadService(db).curve(selected)
    provider = policy(tmp_path)
    monkeypatch.setenv("FORECAST_INTELLIGENCE_MCP_POLICY_FILE", str(provider.path))
    monkeypatch.setattr(database_session, "AsyncSessionMaker", factory)
    tls_dir = tmp_path / "tls"
    tls_dir.mkdir()
    async with tls_server(create_service_account_app(), tls_dir) as (origin, cert, _):
        provider.publish(
            document(
                2,
                accounts=(account(run_grants=(grant_for(source),), quality_grants=()),),
                allowed_hosts=(origin.removeprefix("https://"),),
            )
        )
        async with httpx2.AsyncClient(
            verify=ssl.create_default_context(cafile=str(cert)), headers={HEADER: KEY}
        ) as http:
            async with streamable_http_client(origin + MCP_PATH, http_client=http) as streams:
                async with ClientSession(streams[0], streams[1]) as sdk:
                    await sdk.initialize()
                    with observe_sensitive_work(factory, monkeypatch) as counts:
                        foreign = selected.model_dump(mode="json") | {"run_id": 999999}
                        simulation = request_payload(source)
                        simulation["forecast_selection"]["run_id"] = 999999
                        for name, payload in (
                            ("get_forecast_curve", foreign),
                            ("get_forecast_quality", {}),
                            ("simulate_capacity", simulation),
                        ):
                            result = await sdk.call_tool(name, payload)
                            assert result.is_error
                            assert result.structured_content["data"] is None
                        assert_zero(counts)
                        record_property("S6_ZERO_READ_PROOF", json.dumps(counts, sort_keys=True))
