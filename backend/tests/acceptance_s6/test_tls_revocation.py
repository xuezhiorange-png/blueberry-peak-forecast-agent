"""Barrier-controlled revocation after actual canonical read, before real TLS send."""

import asyncio
import json
import ssl

import httpx
import pytest
from sqlalchemy import select

from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.local_auth.models import AuthAccount, AuthResourceGrant
from backend.app.local_auth.sessions import now
from backend.tests.safe_pilot.operations import tls_server
from backend.tests.safe_pilot.test_restore_and_ingress import application, seed, sign_in

pytestmark = pytest.mark.postgres


@pytest.mark.parametrize("revocation", ["account", "grant"])
async def test_s6_tls_revocation_precedes_response_release(
    pg_auth, tmp_path, monkeypatch, record_property, revocation
):
    auth, factory, _, user, _ = pg_auth
    selected, binding = await seed(factory, user)
    entered, resume = asyncio.Event(), asyncio.Event()
    original = ForecastIntelligenceReadService.curve
    captured = []

    async def measured_read(self, query):
        result = await original(self, query)
        captured.append(result.source_result_hash)
        entered.set()
        await resume.wait()
        return result

    monkeypatch.setattr(ForecastIntelligenceReadService, "curve", measured_read)
    async with tls_server(application(auth), tmp_path) as (origin, cert, _):
        auth.settings.local_auth_origin = origin
        async with httpx.AsyncClient(
            base_url=origin, verify=ssl.create_default_context(cafile=str(cert))
        ) as http:
            await sign_in(http)
            pending = asyncio.create_task(
                http.get(
                    "/api/v1/forecast-intelligence/curve", params=selected.model_dump(mode="json")
                )
            )
            try:
                await asyncio.wait_for(entered.wait(), 10)
                async with factory() as db, db.begin():
                    account = await db.scalar(
                        select(AuthAccount)
                        .where(AuthAccount.account_id == user.account_id)
                        .with_for_update()
                    )
                    if revocation == "account":
                        account.status = "DISABLED"
                        account.auth_revision += 1
                    else:
                        grant = await db.get(AuthResourceGrant, binding.grant_id)
                        grant.revoked_at = now()
                        account.grant_revision += 1
                    await auth.revoke_all(db, account, "SYNTHETIC_S6_IN_FLIGHT_REVOCATION")
                resume.set()
                response = await asyncio.wait_for(pending, 10)
                assert response.status_code in {401, 403}
                assert response.json()["data"] is None
                assert captured and all(digest not in response.text for digest in captured)
                assert "daily_rows" not in response.text
                record_property(
                    "S6_TLS_RELEASE_PROOF",
                    json.dumps(
                        {
                            "canonical_read_reached": True,
                            "revocation_committed_before_release": True,
                            "http_status": response.status_code,
                            "sensitive_bytes_returned": False,
                        },
                        sort_keys=True,
                    ),
                )
            finally:
                resume.set()
                if not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
