"""Additional real S2 transport/authorization failure and isolation boundaries."""

import asyncio
import socket
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.forecast_quality.operational_peak import (
    OperationalPeakForecastRequest,
    forecast_operational_peak,
)
from backend.app.forecast_quality.operational_peak_persistence import (
    OperationalPeakRunRepository,
    execution_hash,
    request_snapshot,
)
from backend.app.local_auth.models import AuthAccount
from backend.app.local_auth.service import AuthService
from backend.app.local_auth.sessions import now
from backend.tests.business_access.test_discovery import PREFIX, app_for, grant
from backend.tests.business_access.test_security import seed, selected, submit
from backend.tests.forecast_intelligence.test_v0_17_s1_service_read_api import query
from backend.tests.local_auth.conftest import login

pytestmark = pytest.mark.postgres


async def test_concurrent_users_only_see_their_own_records(pg_auth, synthetic_authority):
    auth, factory, _, account, _ = pg_auth
    ids, _, app = await seed(auth, factory, account, synthetic_authority, count=1)
    async with factory() as db, db.begin():
        original = await db.get(AuthAccount, account.account_id)
        second = AuthAccount(
            username_normalized="synthetic-second",
            password_hash=original.password_hash,
            role="BUSINESS_USER",
            status="ACTIVE",
            must_change_password=False,
            created_at=now(),
            updated_at=now(),
        )
        db.add(second)
        await db.flush()
    await grant(factory, second, query(ids[1], entity_id="A2"))
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="https://synthetic.test") as a,
        AsyncClient(transport=ASGITransport(app=app), base_url="https://synthetic.test") as b,
    ):
        await login(a)
        csrf = (await b.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
        logged = await b.post(
            "/api/v1/auth/login",
            json={"username": "synthetic-second", "password": "SYNTHETIC-password-123"},
            headers={"Origin": "https://synthetic.test", "X-CSRF-Token": csrf},
        )
        assert logged.status_code == 200
        results = await asyncio.gather(
            *(client.get(PREFIX + "saved-runs") for client in (a, b) * 5)
        )
        for index, result in enumerate(results):
            assert result.status_code == 200
            assert [
                item["forecast_identity"]["run_id"] for item in result.json()["data"]["items"]
            ] == [ids[index % 2]]
        payload = await selected(a)
        issued = await submit(a, payload)
        payload["handoff_token"] = issued.json()["data"]["handoff_token"]
        assert (await submit(b, payload)).status_code == 403


async def test_authorized_short_window_is_not_padded(pg_auth, synthetic_authority):
    auth, factory, _, account, _ = pg_auth
    request = OperationalPeakForecastRequest("A1", "2025-2026", date(2026, 4, 13))
    value = forecast_operational_peak(
        request, synthetic_authority.registry, synthetic_authority.reference_profile
    )
    snapshot = request_snapshot(request)
    async with factory() as db, db.begin():
        saved = await OperationalPeakRunRepository(db).save(
            snapshot=snapshot,
            result=value,
            execution_id=execution_hash(
                snapshot, synthetic_authority.authority_hash, synthetic_authority.policy_version
            ),
            authority_hash=synthetic_authority.authority_hash,
            rerun_of_run_id=None,
        )
    await grant(factory, account, query(saved.run.run_id, origin_date="2026-04-13"))
    async with AsyncClient(
        transport=ASGITransport(app=app_for(auth)), base_url="https://synthetic.test"
    ) as client:
        await login(client)
        result = await client.get(PREFIX + "saved-runs")
        assert result.status_code == 200, result.text
        assert result.json()["data"]["items"][0]["completeness_status"] == "PARTIAL_DATE_WINDOW"
        assert (await submit(client, await selected(client))).status_code == 200
    # Source immutable row count is validated by Canonical Read, not filled to 15.
    assert len(saved.result["daily_forecast"]) == 2


async def test_revision_change_rejects_issued_context(pg_auth, synthetic_authority):
    auth, factory, _, account, _ = pg_auth
    _, _, app = await seed(auth, factory, account, synthetic_authority)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        await login(client)
        cursor = (await client.get(PREFIX + "saved-runs", params={"page_size": 1})).json()["data"][
            "next_cursor"
        ]
        async with factory() as db, db.begin():
            subject = await db.scalar(
                select(AuthAccount)
                .where(AuthAccount.account_id == account.account_id)
                .with_for_update()
            )
            subject.grant_revision += 1
            await auth.revoke_all(db, subject, "SYNTHETIC_REVOCATION")
        result = await client.get(PREFIX + "saved-runs", params={"page_size": 1, "cursor": cursor})
        assert result.status_code == 401 and result.json()["data"] is None


async def test_database_unavailable_and_transport_limits(pg_auth, synthetic_authority):
    auth, factory, _, account, _ = pg_auth
    _, _, app = await seed(auth, factory, account, synthetic_authority)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        await login(client)
        csrf = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
        result = await client.post(
            PREFIX + "selection",
            content=b"x" * 131073,
            headers={
                "Content-Type": "application/json",
                "Origin": "https://synthetic.test",
                "X-CSRF-Token": csrf,
            },
        )
        assert result.status_code == 413 and result.json()["data"] is None
        for suffix in ("?page_size=1&page_size=2", "?entity_id=" + "x" * 8193):
            assert (await client.get(PREFIX + "saved-runs" + suffix)).status_code == 422
        result = await client.post(
            PREFIX + "selection",
            content=b"{invalid",
            headers={
                "Content-Type": "application/json",
                "Origin": "https://synthetic.test",
                "X-CSRF-Token": csrf,
            },
        )
        assert result.status_code == 422
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        engine = create_async_engine(
            f"postgresql+asyncpg://SYNTHETIC:SYNTHETIC@127.0.0.1:{port}/blueberry_test_s2_unavailable"
        )
        app.state.local_auth = AuthService(async_sessionmaker(engine), auth.settings)
        try:
            result = await client.get(PREFIX + "saved-runs")
            assert result.status_code == 503
            assert all(
                secret not in result.text
                for secret in ("SYNTHETIC", "postgresql", "SQL", "Traceback", "127.0.0.1")
            )
        finally:
            await engine.dispose()
        app.state.local_auth = auth
        assert (await client.get(PREFIX + "saved-runs")).status_code == 200
