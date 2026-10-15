"""Real loopback TLS SDK and HTTP use one canonical synthetic PostgreSQL DB."""

import json
import ssl

import httpx
import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr
from starlette.responses import JSONResponse

from backend.app.db import session as database_session
from backend.app.forecast_intelligence.read_schemas import QualityReadQuery
from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.mcp.forecast_intelligence_http import MCP_PATH, create_service_account_app
from backend.app.mcp.forecast_intelligence_tools import TOOLS, tools
from backend.tests.mcp.test_v0_17_s3_productization import (
    HEADER,
    KEY,
    account,
    comparison_payload,
    grant_for,
    request_payload,
)
from backend.tests.mcp.test_v0_18_s3_policy import document, policy
from backend.tests.mcp.test_v0_18_s3_postgres import quality_grant
from backend.tests.safe_pilot.operations import assert_redacted, tls_server
from backend.tests.safe_pilot.test_restore_and_ingress import application, seed, sign_in

pytestmark = pytest.mark.postgres


async def test_operational_factory_all_eight_real_tls_payload_parity_rotation_rollback(
    pg_auth,
    tmp_path,
    monkeypatch,
    caplog,
):
    auth, factory, _, user, _ = pg_auth
    selected, _ = await seed(factory, user)
    await quality_grant(factory, user)
    async with factory() as db:
        source = await ForecastIntelligenceReadService(db).curve(selected)
    provider = policy(tmp_path)
    monkeypatch.setenv("FORECAST_INTELLIGENCE_MCP_POLICY_FILE", str(provider.path))
    # Trusted test composition supplies the disposable PG factory; actual routes,
    # authentication, policy, SDK and canonical services are not mocked.
    monkeypatch.setattr(database_session, "AsyncSessionMaker", factory)
    http_dir, mcp_dir = tmp_path / "http", tmp_path / "mcp"
    http_dir.mkdir()
    mcp_dir.mkdir()
    http_app = application(auth)
    machine_app = create_service_account_app()
    async with (
        tls_server(http_app, http_dir) as (origin, cert, _),
        tls_server(machine_app, mcp_dir) as (machine_origin, machine_cert, _),
    ):
        auth.settings.local_auth_origin = origin
        host = machine_origin.removeprefix("https://")
        machine_account = account(run_grants=(grant_for(source),))
        provider.publish(document(2, accounts=(machine_account,), allowed_hosts=(host,)))
        http_context = ssl.create_default_context(cafile=str(cert))
        machine_context = ssl.create_default_context(cafile=str(machine_cert))
        async with (
            httpx.AsyncClient(base_url=origin, verify=http_context) as http,
            httpx2.AsyncClient(verify=machine_context, headers={HEADER: KEY}) as machine,
        ):
            cookie = await sign_in(http)
            async with streamable_http_client(
                machine_origin + MCP_PATH, http_client=machine
            ) as streams:
                async with ClientSession(streams[0], streams[1]) as sdk:
                    await sdk.initialize()
                    listing = (await sdk.list_tools()).tools
                    assert [t.model_dump() for t in listing] == [t.model_dump() for t in tools()]
                    assert len(listing) == 8
                    for name, tool in TOOLS.items():
                        if tool.method in {"simulate", "compare"}:
                            payload = request_payload(source)
                            if tool.method == "compare":
                                payload = comparison_payload(payload)
                            path = (
                                "compare-capacity-scenarios"
                                if tool.method == "compare"
                                else "simulate-capacity"
                            )
                            csrf = (await http.get("/api/v1/auth/csrf")).json()["data"][
                                "csrf_token"
                            ]
                            response = await http.post(
                                "/api/v1/decision-support/" + path,
                                json=payload,
                                headers={"Origin": origin, "X-CSRF-Token": csrf},
                            )
                        else:
                            payload = (
                                QualityReadQuery().model_dump(mode="json")
                                if tool.method == "quality"
                                else selected.model_dump(mode="json")
                            )
                            response = await http.get(
                                "/api/v1/forecast-intelligence/" + tool.method,
                                params={k: v for k, v in payload.items() if v is not None},
                            )
                        assert response.status_code == 200
                        actual = await sdk.call_tool(name, payload)
                        assert not actual.is_error
                        assert actual.structured_content == response.json()
                        assert json.loads(actual.content[0].text) == response.json()
                    # Rotation is published to the same live operational factory.
                    rotated = machine_account.model_copy(
                        update={"secret": SecretStr("SYNTHETIC_S5_ROTATED_KEY")}
                    )
                    provider.publish(document(3, accounts=(rotated,), allowed_hosts=(host,)))
                    denied = await machine.post(machine_origin + MCP_PATH, json={})
                    assert denied.status_code == 401
            async with httpx2.AsyncClient(
                verify=machine_context, headers={HEADER: "SYNTHETIC_S5_ROTATED_KEY"}
            ) as renewed:
                async with streamable_http_client(
                    machine_origin + MCP_PATH, http_client=renewed
                ) as streams:
                    async with ClientSession(streams[0], streams[1]) as sdk:
                        await sdk.initialize()
                        curve = await sdk.call_tool(
                            "get_forecast_curve", selected.model_dump(mode="json")
                        )
                        assert curve.structured_content == source.model_dump(mode="json")
                        provider.publish(
                            document(
                                4,
                                accounts=(rotated.model_copy(update={"run_grants": ()}),),
                                allowed_hosts=(host,),
                            )
                        )
                        revoked = await sdk.call_tool(
                            "get_forecast_curve", selected.model_dump(mode="json")
                        )
                        assert (
                            revoked.is_error and revoked.structured_content["code"] == "FORBIDDEN"
                        )
            # Missing policy must fail closed; correct private policy restores access,
            # not the revoked old key. No cached static config fallback exists.
            original_bytes = provider.path.read_bytes()
            provider.path.write_bytes(b"SYNTHETIC_INVALID_POLICY")
            assert (await machine.post(machine_origin + MCP_PATH, json={})).status_code == 503
            provider.path.write_bytes(original_bytes)
            assert (await machine.post(machine_origin + MCP_PATH, json={})).status_code == 401
            assert_redacted(caplog.text, [KEY, "SYNTHETIC_S5_ROTATED_KEY", cookie])


async def test_stop_revoke_restart_verify_then_manual_resume(pg_auth, tmp_path):
    """Executable isolated rollback order; same verified compatible binary, not a downgrade."""
    auth, factory, _, user, _ = pg_auth
    selected, _ = await seed(factory, user)

    class Admission:
        def __init__(self, app):
            self.app, self.enabled = app, False

        async def __call__(self, scope, receive, send):
            if not self.enabled:
                await JSONResponse(
                    {"SYNTHETIC": True, "status": "ACCESS_STOPPED"}, status_code=503
                )(scope, receive, send)
            else:
                await self.app(scope, receive, send)

    entry = Admission(application(auth))
    async with tls_server(entry, tmp_path) as (origin, cert, _):
        auth.settings.local_auth_origin = origin
        async with httpx.AsyncClient(
            base_url=origin, verify=ssl.create_default_context(cafile=str(cert))
        ) as client:
            assert (await client.get("/health/live")).status_code == 503
            entry.enabled = True  # explicit synthetic operator confirmation
            old_cookie = await sign_in(client)
            result = await client.get(
                "/api/v1/forecast-intelligence/curve", params=selected.model_dump(mode="json")
            )
            assert result.status_code == 200
            entry.enabled = False
            assert (await client.get("/api/v1/auth/me")).status_code == 503
            from backend.tests.safe_pilot.operations import quarantine

            await quarantine(factory)
            entry.app = application(auth)  # replace with the same frozen compatible version
            assert (await client.get("/health/live")).status_code == 503
            async with factory() as db:
                assert (await ForecastIntelligenceReadService(db).curve(selected)).model_dump(
                    mode="json"
                ) == result.json()
            entry.enabled = True  # manual confirmation, NOT automatic health-triggered reopening
            assert (await client.get("/api/v1/auth/me")).status_code == 401
            client.cookies.clear()
            await sign_in(client, expected=401)
            from backend.tests.safe_pilot.operations import approve_synthetic_recovery_password

            await approve_synthetic_recovery_password(
                factory, user.account_id, "SYNTHETIC-rollback-reapproved-password"
            )
            await sign_in(client, password="SYNTHETIC-rollback-reapproved-password")
            assert (
                await client.get(
                    "/api/v1/forecast-intelligence/curve", params=selected.model_dump(mode="json")
                )
            ).status_code == 403
            assert (await client.get("/api/v1/trial/forecast-runs")).status_code == 403
            assert old_cookie != client.cookies.get("__Host-blueberry-session")
