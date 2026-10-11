"""Revocation after real canonical reads but before actual ASGI send."""

from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.local_auth.authorization import GuardedResponse
from backend.app.local_auth.models import AuthAccount, AuthResourceGrant, AuthSession
from backend.app.local_auth.sessions import now
from backend.app.main import create_app
from backend.tests.forecast_intelligence.conftest import seed_sources
from backend.tests.forecast_intelligence.test_v0_17_s1_service_read_api import params, query
from backend.tests.local_auth.conftest import login
from backend.tests.local_auth.test_authorization_release import grant_for

pytestmark = pytest.mark.postgres


@pytest.mark.parametrize("revocation", ["disable", "grant", "expiry", "session"])
async def test_a11_real_canonical_read_revocation_wins_before_asgi_send(
    pg_auth, synthetic_authority, monkeypatch, revocation
):
    auth, factory, _, account, _ = pg_auth
    ids = await seed_sources(factory, synthetic_authority)
    async with factory() as db:
        source = await ForecastIntelligenceReadService(db).curve(query(ids[0]))
    grant = await grant_for(factory, account)
    async with factory() as db, db.begin():
        await db.execute(
            update(AuthResourceGrant)
            .where(AuthResourceGrant.grant_id == grant.grant_id)
            .values(
                forecast_binding={
                    **grant.forecast_binding,
                    "expected_source_result_hash": source.source_result_hash,
                }
            )
        )
    original = GuardedResponse.__call__
    reached = []

    async def interleave(response, scope, receive, send):
        assert (
            response.body == source.model_dump_json().encode()
            or source.source_result_hash.encode() in response.body
        )
        reached.append(True)
        async with factory() as db, db.begin():
            await db.scalar(
                select(AuthAccount)
                .where(AuthAccount.account_id == account.account_id)
                .with_for_update()
            )
            if revocation == "disable":
                await db.execute(
                    update(AuthAccount)
                    .where(AuthAccount.account_id == account.account_id)
                    .values(status="DISABLED", auth_revision=2)
                )
            elif revocation == "grant":
                await db.execute(
                    update(AuthResourceGrant)
                    .where(AuthResourceGrant.grant_id == grant.grant_id)
                    .values(revoked_at=now())
                )
                await db.execute(
                    update(AuthAccount)
                    .where(AuthAccount.account_id == account.account_id)
                    .values(grant_revision=2)
                )
            elif revocation == "expiry":
                await db.execute(
                    update(AuthResourceGrant)
                    .where(AuthResourceGrant.grant_id == grant.grant_id)
                    .values(valid_until=now() - timedelta(microseconds=1))
                )
            else:
                await db.execute(
                    update(AuthSession)
                    .where(AuthSession.account_id == account.account_id)
                    .values(revoked_at=now())
                )
        await original(response, scope, receive, send)

    monkeypatch.setattr(GuardedResponse, "__call__", interleave)
    app = create_app(auth.settings)
    app.state.local_auth = auth
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as c:
        assert (await login(c)).status_code == 200
        response = await c.get("/api/v1/forecast-intelligence/curve", params=params(query(ids[0])))
        assert response.status_code in {401, 403}
        assert response.json()["data"] is None
        assert source.source_result_hash not in response.text
        assert reached == [True]
