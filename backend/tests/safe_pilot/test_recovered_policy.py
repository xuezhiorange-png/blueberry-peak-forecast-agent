"""Configuration recovery must reauthenticate the NEW key, not revive an old one."""

import ssl

import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr

from backend.app.db import session as database_session
from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.mcp.forecast_intelligence_http import MCP_PATH, create_service_account_app
from backend.tests.mcp.test_v0_17_s3_productization import HEADER, KEY, account, grant_for
from backend.tests.mcp.test_v0_18_s3_policy import document, policy
from backend.tests.safe_pilot.operations import tls_server
from backend.tests.safe_pilot.test_restore_and_ingress import seed

pytestmark = pytest.mark.postgres


async def test_repaired_policy_reauthenticates_new_credential_only(pg_auth, tmp_path, monkeypatch):
    _, factory, _, user, _ = pg_auth
    selected, _ = await seed(factory, user)
    async with factory() as db:
        original = await ForecastIntelligenceReadService(db).curve(selected)
    provider = policy(tmp_path)
    monkeypatch.setenv("FORECAST_INTELLIGENCE_MCP_POLICY_FILE", str(provider.path))
    monkeypatch.setattr(database_session, "AsyncSessionMaker", factory)
    tls = tmp_path / "TLS"
    tls.mkdir()
    async with tls_server(create_service_account_app(), tls) as (origin, cert, _):
        provider.publish(
            document(
                2,
                allowed_hosts=(origin.removeprefix("https://"),),
                accounts=(
                    account(
                        secret=SecretStr("SYNTHETIC_REPAIRED_KEY"),
                        run_grants=(grant_for(original),),
                    ),
                ),
            )
        )
        valid = provider.path.read_bytes()
        provider.path.write_bytes(b"SYNTHETIC_BROKEN_POLICY")
        async with httpx2.AsyncClient(
            verify=ssl.create_default_context(cafile=str(cert)),
            headers={HEADER: "SYNTHETIC_REPAIRED_KEY"},
            trust_env=False,
        ) as http:
            assert (await http.post(origin + MCP_PATH, json={})).status_code == 503
            provider.path.write_bytes(valid)
            assert (
                await http.post(origin + MCP_PATH, json={}, headers={HEADER: KEY})
            ).status_code == 401
            async with streamable_http_client(origin + MCP_PATH, http_client=http) as streams:
                async with ClientSession(streams[0], streams[1]) as sdk:
                    await sdk.initialize()
                    assert len((await sdk.list_tools()).tools) == 8
                    curve = await sdk.call_tool(
                        "get_forecast_curve", selected.model_dump(mode="json")
                    )
                    assert not curve.is_error
                    assert curve.structured_content == original.model_dump(mode="json")
