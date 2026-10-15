"""S6 extends the existing S4 PG/HTTPS harness, never the production app.

The same disposable database supplies browser HTTP, direct canonical reads and
the independent real TLS MCP SDK. No business response or authorization mock.
"""

import hashlib
import json
import ssl
import tempfile
from contextlib import asynccontextmanager
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Literal

import httpx2
from fastapi import Request
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.db import session as database_session
from backend.app.forecast_intelligence.decision_service import DecisionSupportService
from backend.app.forecast_intelligence.read_schemas import ForecastReadQuery, QualityReadQuery
from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.forecast_quality.operational_peak import canonical_result_hash
from backend.app.forecast_quality.operational_peak_persistence import (
    OperationalPeakRunRepository,
    execution_hash,
)
from backend.app.local_auth.models import AuthAccount, AuthResourceGrant
from backend.app.local_auth.service import AuthService
from backend.app.mcp.forecast_intelligence_http import MCP_PATH, create_service_account_app
from backend.app.mcp.forecast_intelligence_policy import FilePolicy
from backend.tests.mcp.test_v0_17_s3_productization import HEADER, KEY, account, grant_for
from backend.tests.mcp.test_v0_18_s3_policy import document
from backend.tests.safe_pilot.operations import tls_server
from frontend.e2e.support import business_pg

original_lifespan = business_pg.outer.router.lifespan_context
original_fixture = business_pg.saved_fixture
original_grant = business_pg.grant
SHORT_QUERY = None


def saved_fixture(base):
    """Literal short-window seed, before the existing post-seed DML guard.

    No forecast is executed: 80 + 100 = the explicit 180 kg fixture. Missing
    days and full-window summaries remain absent, never zero-filled.
    """
    result = original_fixture(base)
    if base != "SYNTHETIC_SHORT_BASE":
        return result
    short = result.daily_forecast[:2]

    def incomplete(window):
        return replace(
            window,
            status="NOT_COMPUTABLE_FULL_WINDOW",
            total_kg=None,
            peak_date=None,
            peak_kg=None,
            available_days=2,
            reason="BUSINESS_SEASON_WINDOW_EXCEEDED",
        )

    result = replace(
        result,
        daily_forecast=short,
        business_season_end=short[-1].date,
        forecast_7d=incomplete(result.forecast_7d),
        forecast_15d=incomplete(result.forecast_15d),
        remaining_business_window=replace(
            result.remaining_business_window,
            end_date=short[-1].date,
            total_kg=Decimal("180"),
            peak_date=short[1].date,
            peak_kg=Decimal("100"),
            available_days=2,
        ),
    )
    return replace(result, result_hash=canonical_result_hash(result))


async def seed_grant(factory, principal, query):
    """Extend the existing seeding phase, before its DML guard, not live auth."""
    global SHORT_QUERY
    row = await original_grant(factory, principal, query)
    if SHORT_QUERY is None and principal.username_normalized == "synthetic-user":
        value = saved_fixture("SYNTHETIC_SHORT_BASE")
        snapshot = {
            "base_id": value.base_id,
            "target_season": value.target_season,
            "origin_date": value.origin_date.isoformat(),
        }
        authority = hashlib.sha256(b"SYNTHETIC_S6_SHORT_LITERAL").hexdigest()
        async with factory() as db, db.begin():
            saved = await OperationalPeakRunRepository(db).save(
                snapshot,
                value,
                execution_hash(snapshot, authority, value.policy_version),
                authority,
                None,
            )
        SHORT_QUERY = query.model_copy(
            update={
                "run_id": saved.run.run_id,
                "entity_id": value.base_id,
                "expected_source_result_hash": saved.run.result_hash,
            }
        )
        await original_grant(factory, principal, SHORT_QUERY)
    return row


business_pg.grant = seed_grant


@asynccontextmanager
async def lifespan(outer):
    async with original_lifespan(outer):
        import os

        assert SHORT_QUERY is not None
        business_pg.STATE["identities"].append(SHORT_QUERY.model_dump(mode="json"))
        root = Path(tempfile.mkdtemp(prefix="SYNTHETIC-s6-sdk-"))
        provider = FilePolicy(root / "policy.json")
        factory = outer.state.auth.factory
        previous = database_session.AsyncSessionMaker
        old_path = os.environ.get("FORECAST_INTELLIGENCE_MCP_POLICY_FILE")
        os.environ["FORECAST_INTELLIGENCE_MCP_POLICY_FILE"] = str(provider.path)
        database_session.AsyncSessionMaker = factory
        try:
            async with factory() as db:
                sources = [
                    await ForecastIntelligenceReadService(db).curve(ForecastReadQuery(**q))
                    for q in business_pg.STATE["identities"]
                ]
            async with tls_server(create_service_account_app(), root) as (origin, cert, _):
                provider.publish(
                    document(
                        1,
                        accounts=(account(run_grants=tuple(grant_for(s) for s in sources)),),
                        allowed_hosts=(origin.removeprefix("https://"),),
                    )
                )
                outer.state.s6_mcp = (origin, cert)
                yield
        finally:
            database_session.AsyncSessionMaker = previous
            if old_path is None:
                os.environ.pop("FORECAST_INTELLIGENCE_MCP_POLICY_FILE", None)
            else:
                os.environ["FORECAST_INTELLIGENCE_MCP_POLICY_FILE"] = old_path
    # Only after the nested TLS MCP server and the original UUID PG database
    # fixture have BOTH finished cleanup; independent of uvicorn log verbosity.
    print("S6_HARNESS_CLEANUP_COMPLETE", flush=True)


business_pg.outer.router.lifespan_context = lifespan


@business_pg.outer.post("/__s6_test__/database/{state}")
async def database_fault(state: Literal["unavailable", "restore"]):
    """Fixed synthetic connection fault; no arbitrary target or fake HTTP result."""
    outer = business_pg.outer
    if state == "unavailable":
        assert not hasattr(outer.state, "s6_failed_engine")
        import socket

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        engine = create_async_engine(
            f"postgresql+asyncpg://SYNTHETIC:SYNTHETIC@127.0.0.1:{port}/blueberry_test_s6_unavailable"
        )
        outer.state.s6_failed_engine = engine
        outer.state.production.state.local_auth = AuthService(
            async_sessionmaker(engine), outer.state.auth.settings
        )
    else:
        outer.state.production.state.local_auth = outer.state.auth
        if hasattr(outer.state, "s6_failed_engine"):
            await outer.state.s6_failed_engine.dispose()
            del outer.state.s6_failed_engine
    return {"SYNTHETIC": True, "state": state}


@business_pg.outer.post("/__s6_test__/catalog-drift")
async def catalog_drift():
    """Mutate only synthetic authorization metadata to test snapshot mismatch."""
    async with business_pg.outer.state.auth.factory() as db, db.begin():
        subject = await db.scalar(
            select(AuthAccount)
            .where(AuthAccount.username_normalized == "synthetic-user")
            .with_for_update()
        )
        grants = (
            await db.scalars(
                select(AuthResourceGrant).where(
                    AuthResourceGrant.principal_id == subject.principal_id,
                    AuthResourceGrant.resource_kind == "FORECAST",
                )
            )
        ).all()
        for grant in grants:
            binding = dict(grant.forecast_binding)
            binding["source_authority_version"] += "_S6_DRIFT"
            grant.forecast_binding = binding
    return {"SYNTHETIC": True, "catalog_changed": True}


async def sdk_call(name, payload):
    origin, cert = business_pg.outer.state.s6_mcp
    async with httpx2.AsyncClient(
        verify=ssl.create_default_context(cafile=str(cert)), headers={HEADER: KEY}
    ) as machine:
        async with streamable_http_client(origin + MCP_PATH, http_client=machine) as streams:
            async with ClientSession(streams[0], streams[1]) as sdk:
                await sdk.initialize()
                result = await sdk.call_tool(name, payload)
                assert not result.is_error
                assert json.loads(result.content[0].text) == result.structured_content
                return result.structured_content


@business_pg.outer.get("/__s6_test__/parity")
async def parity(level: Literal["BASE", "REGION", "COMPANY"] = "BASE"):
    query = ForecastReadQuery(
        **next(q for q in business_pg.STATE["identities"] if q["hierarchy_level"] == level)
    )
    result = {"SYNTHETIC": True}
    async with business_pg.outer.state.auth.factory() as db:
        reader = ForecastIntelligenceReadService(db)
        for method, tool in (
            ("overview", "get_forecast_overview"),
            ("curve", "get_forecast_curve"),
            ("hierarchy", "get_hierarchical_forecast"),
            ("uncertainty", "get_forecast_uncertainty"),
            ("attribution", "get_forecast_attribution"),
            ("quality", "get_forecast_quality"),
        ):
            selected = QualityReadQuery() if method == "quality" else query
            canonical = (await getattr(reader, method)(selected)).model_dump(mode="json")
            assert canonical == await sdk_call(tool, selected.model_dump(mode="json"))
            result[method] = canonical
    return result


@business_pg.outer.post("/__s6_test__/decision-parity/{method}")
async def decision_parity(method: Literal["simulate", "compare"], request: Request):
    payload = await request.json()
    async with business_pg.outer.state.auth.factory() as db:
        canonical = (
            await getattr(DecisionSupportService(ForecastIntelligenceReadService(db)), method)(
                payload
            )
        ).model_dump(mode="json")
    tool = "simulate_capacity" if method == "simulate" else "compare_capacity_scenarios"
    assert canonical == await sdk_call(tool, payload)
    return {"SYNTHETIC": True, "canonical_and_sdk": canonical}


app = business_pg.app
