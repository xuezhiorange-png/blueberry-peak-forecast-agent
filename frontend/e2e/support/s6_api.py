"""SYNTHETIC=true S6 harness. One SQLite authority for HTTP, SDK and browser.

Never imported by production. Credentials stay in this server process. The
SDK audit endpoint returns business payloads only, not transport configuration.
"""

import json
from contextlib import asynccontextmanager

import httpx2
from fastapi import FastAPI
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr

from backend.app.api.forecast_intelligence_decision import router as decision_router
from backend.app.api.forecast_intelligence_read import router as read_router
from backend.app.db.session import get_db_session
from backend.app.forecast_intelligence.read_access import QualityGrant, RunGrant, ServiceAccount
from backend.app.forecast_intelligence.read_schemas import ForecastIdentity
from backend.app.mcp.forecast_intelligence_auth import MCPServiceConfig
from backend.app.mcp.forecast_intelligence_http import MCP_PATH, create_forecast_intelligence_app
from frontend.e2e.support import s6_seed as seed

SYNTHETIC = True
TEST_KEY = "SYNTHETIC_S6_SERVER_ONLY_CREDENTIAL"


@asynccontextmanager
async def lifespan(app):
    async with seed.lifespan(app):

        @asynccontextmanager
        async def sessions():
            async for session in app.dependency_overrides[get_db_session]():
                yield session

        grants = tuple(
            RunGrant(
                principal_id="SYNTHETIC_S6",
                forecast_identity=ForecastIdentity.model_validate(
                    {k: v for k, v in q.items() if k != "expected_source_result_hash"}
                ),
                source_result_hash=q["expected_source_result_hash"],
            )
            for q in seed.STATE["identities"]
        )
        account = ServiceAccount(
            principal_id="SYNTHETIC_S6",
            secret=SecretStr(TEST_KEY),
            permissions=frozenset({"may_read_forecast", "may_read_quality"}),
            run_grants=grants,
            quality_grants=tuple(
                QualityGrant(mode=mode)
                for mode in ("HISTORICAL_VALIDATION", "CURRENT_PRODUCTION_ACCURACY")
            ),
        )
        app.state.sessions = sessions
        app.state.account = account
        app.state.mcp = create_forecast_intelligence_app(
            MCPServiceConfig(accounts=(account,), allowed_hosts=("s6.test",), allowed_origins=()),
            session_factory=sessions,
        )
        yield


@asynccontextmanager
async def sdk_client(app, key=TEST_KEY):
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app.state.mcp),
        headers={"X-Forecast-Intelligence-Key": key},
    ) as http:
        async with streamable_http_client(
            "https://s6.test" + MCP_PATH, http_client=http
        ) as streams:
            async with ClientSession(streams[0], streams[1]) as sdk:
                await sdk.initialize()
                yield sdk


async def sdk_call(sdk, name, arguments):
    result = await sdk.call_tool(name, arguments)
    assert json.loads(result.content[0].text) == result.structured_content
    return result


app = FastAPI(lifespan=lifespan)
app.include_router(read_router, prefix="/api/v1/forecast-intelligence")
app.include_router(decision_router, prefix="/api/v1/decision-support")


@app.get("/__dashboard_test__/authority")
async def authority():
    return {"SYNTHETIC": True, **seed.STATE}


@app.post("/__s6_test__/sdk")
async def sdk_audit(payload: dict):
    # Test-side browser driver invokes this endpoint; production Dashboard never
    # calls it and never sees an MCP credential or service-account grant.
    async with sdk_client(app) as sdk:
        result = await sdk_call(sdk, payload["name"], payload["arguments"])
        return {"SYNTHETIC": True, "isError": result.is_error, "payload": result.structured_content}
