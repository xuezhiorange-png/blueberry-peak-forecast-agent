"""Remaining acceptance edges, using real isolated PostgreSQL and HTTP."""

import asyncio
import json
import socket
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.forecast_intelligence.read_schemas import QualityReadQuery
from backend.app.forecast_intelligence.read_service import PUBLIC_EVIDENCE_HASHES
from backend.app.local_auth.authorization import binding_digest
from backend.app.local_auth.models import (
    AuthAccount,
    AuthAuditEvent,
    AuthResourceGrant,
    AuthSession,
)
from backend.app.local_auth.service import AuthService
from backend.app.local_auth.sessions import COOKIE, digest, now
from backend.app.main import create_app
from backend.tests.forecast_intelligence.conftest import seed_sources
from backend.tests.forecast_intelligence.test_v0_17_s1_service_read_api import params, query
from backend.tests.local_auth.conftest import login
from backend.tests.local_auth.test_admin_runtime import admin
from backend.tests.local_auth.test_authorization_release import grant_for

pytestmark = pytest.mark.postgres


async def test_a20_actual_connection_failure_is_safe_and_recovers(pg_auth):
    auth, _, client, _, _ = pg_auth
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    engine = create_async_engine(
        f"postgresql+asyncpg://SYNTHETIC:SYNTHETIC@127.0.0.1:{port}/blueberry_test_unavailable"
    )
    broken = AuthService(async_sessionmaker(engine), auth.settings)
    app = create_app(auth.settings)
    app.state.local_auth = broken
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://synthetic.test"
        ) as c:
            response = await c.get("/api/v1/auth/csrf")
            assert response.status_code == 503
            assert all(
                v not in response.text
                for v in ("SYNTHETIC", "postgresql", "Traceback", "127.0.0.1")
            )
            app.state.local_auth = auth
            assert (await c.get("/api/v1/auth/csrf")).status_code == 200
    finally:
        await engine.dispose()


@pytest.mark.parametrize("field", ["idle_expires_at", "absolute_expires_at"])
async def test_a04_expired_server_session_rejected(pg_auth, field):
    _, factory, client, _, _ = pg_auth
    assert (await login(client)).status_code == 200
    async with factory() as db, db.begin():
        await db.execute(
            update(AuthSession)
            .where(AuthSession.token_digest == digest(client.cookies.get(COOKIE)))
            .values({field: now() - timedelta(seconds=1), "issued_at": now() - timedelta(days=2)})
        )
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_a04_cookie_duplicate_and_forgery(pg_auth):
    _, _, client, _, _ = pg_auth
    assert (await login(client)).status_code == 200
    token = client.cookies.get(COOKIE)
    for header in (f"{COOKIE}={token}; {COOKIE}={token}", f"{COOKIE}={'x' * 43}"):
        assert (await client.get("/api/v1/auth/me", headers={"Cookie": header})).status_code == 401


async def test_a02_unknown_username_matches_bad_password(pg_auth):
    _, _, client, _, _ = pg_auth
    bad = await login(client, "SYNTHETIC-incorrect-password")
    csrf = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
    unknown = await client.post(
        "/api/v1/auth/login",
        json={"username": "synthetic-missing", "password": "SYNTHETIC-password-123"},
        headers={"Origin": "https://synthetic.test", "X-CSRF-Token": csrf},
    )
    assert unknown.status_code == bad.status_code == 401
    assert unknown.json() == bad.json()


async def test_a05_all_management_endpoints_denied_before_target_reads(pg_auth):
    _, factory, client, _, _ = pg_auth
    assert (await login(client)).status_code == 200
    csrf = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
    headers = {"Origin": "https://synthetic.test", "X-CSRF-Token": csrf}
    queries = []

    def observe(conn, cursor, statement, parameters, context, many):
        del conn, cursor, parameters, context, many
        if "auth_resource_grant" in statement or "auth_audit_event" in statement:
            queries.append(statement)

    event.listen(factory.kw["bind"].sync_engine, "before_cursor_execute", observe)
    try:
        for method, path in (
            ("POST", "users"),
            ("GET", "users"),
            ("PATCH", "users/00000000-0000-0000-0000-000000000001/status"),
            ("PATCH", "users/00000000-0000-0000-0000-000000000001/role"),
            ("POST", "users/00000000-0000-0000-0000-000000000001/reset-password"),
            ("POST", "resource-grants"),
            ("GET", "resource-grants"),
            ("POST", "resource-grants/00000000-0000-0000-0000-000000000001/revoke"),
            ("GET", "audit-events"),
        ):
            response = await client.request(
                method,
                "/api/v1/admin/" + path,
                headers=headers,
                **({"json": {}} if method != "GET" else {}),
            )
            assert response.status_code == 403
        assert queries == []
    finally:
        event.remove(factory.kw["bind"].sync_engine, "before_cursor_execute", observe)


async def test_a09_quality_grant_is_independent_and_pinned(pg_auth, monkeypatch, tmp_path):
    auth, factory, _, account, _ = pg_auth
    app = create_app(auth.settings)
    app.state.local_auth = auth
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as c:
        assert (await login(c)).status_code == 200
        assert (await c.get("/api/v1/forecast-intelligence/quality")).status_code == 403
        async with factory() as db, db.begin():
            grant = AuthResourceGrant(
                principal_id=account.principal_id,
                resource_kind="QUALITY",
                capability="may_read_quality",
                organization_id="SYNTHETIC_ORG",
                approved_by_principal=account.principal_id,
                approval_reference="SYNTHETIC",
                reason="isolated acceptance",
                grant_revision=1,
                forecast_binding=None,
                quality_binding={
                    "query": QualityReadQuery().model_dump(mode="json"),
                    "source_split": "EXPOSED_OOT",
                    "target_season": "2025-2026",
                    "scope": "BASE_COHORT_AGGREGATE",
                    "evidence_policy_version": "SYNTHETIC_R1",
                    "evidence_hashes": PUBLIC_EVIDENCE_HASHES,
                    "evidence_set_digest": binding_digest(PUBLIC_EVIDENCE_HASHES),
                },
                valid_from=now() - timedelta(seconds=1),
                valid_until=now() + timedelta(hours=1),
                created_at=now(),
            )
            db.add(grant)
            await db.flush()
        response = await c.get("/api/v1/forecast-intelligence/quality")
        assert response.status_code == 200 and response.json()["status"] in {
            "READY",
            "NOT_AVAILABLE",
        }
        from backend.app.forecast_intelligence import read_service

        monkeypatch.setattr(read_service, "EVIDENCE_ROOT", tmp_path)
        absent = await c.get("/api/v1/forecast-intelligence/quality")
        assert absent.status_code == 200 and absent.json()["status"] == "NOT_AVAILABLE"
        first = next(iter(PUBLIC_EVIDENCE_HASHES))
        (tmp_path / first).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / first).write_bytes(b"SYNTHETIC_DAMAGED_EVIDENCE")
        damaged = await c.get("/api/v1/forecast-intelligence/quality")
        assert damaged.status_code == 409 and damaged.json()["data"] is None
        assert (
            await c.get("/api/v1/forecast-intelligence/curve", params=params(query()))
        ).status_code == 403
        async with factory() as db, db.begin():
            changed = {**grant.quality_binding, "evidence_set_digest": "a" * 64}
            await db.execute(
                update(AuthResourceGrant)
                .where(AuthResourceGrant.grant_id == grant.grant_id)
                .values(quality_binding=changed)
            )
        assert (await c.get("/api/v1/forecast-intelligence/quality")).status_code == 409


async def test_a10_canonical_hash_drift_fails_closed(pg_auth, synthetic_authority):
    auth, factory, _, account, _ = pg_auth
    ids = await seed_sources(factory, synthetic_authority)
    assert ids[0] == query().run_id
    await grant_for(factory, account)  # Deliberately wrong expected source hash.
    app = create_app(auth.settings)
    app.state.local_auth = auth
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as c:
        assert (await login(c)).status_code == 200
        response = await c.get("/api/v1/forecast-intelligence/curve", params=params(query()))
        assert response.status_code == 409 and response.json()["data"] is None
        assert all(s not in response.text for s in ("SELECT", "postgresql", "Traceback"))
        from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService

        async with factory() as db:
            valid = await ForecastIntelligenceReadService(db).curve(query(ids[0]))
        async with factory() as db, db.begin():
            grant = await db.scalar(
                select(AuthResourceGrant).where(
                    AuthResourceGrant.principal_id == account.principal_id
                )
            )
            grant.forecast_binding = {
                **grant.forecast_binding,
                "expected_source_result_hash": valid.source_result_hash,
            }
            # Intentional corruption in the isolated synthetic fixture, never production.
            await db.execute(
                text(
                    "DROP TRIGGER operational_peak_forecast_daily_immutable "
                    "ON operational_peak_forecast_daily"
                )
            )
            await db.execute(
                text(
                    "UPDATE operational_peak_forecast_daily SET predicted_kg=999 WHERE run_id=:run"
                ),
                {"run": ids[0]},
            )
        damaged = await c.get("/api/v1/forecast-intelligence/curve", params=params(query(ids[0])))
        assert damaged.status_code == 409 and damaged.json()["data"] is None


async def test_a12_concurrent_principal_session_isolation(pg_auth):
    auth, factory, client, account, _ = pg_auth
    from backend.app.local_auth.passwords import hash_password

    async with factory() as db, db.begin():
        other = AuthAccount(
            username_normalized="synthetic-other",
            password_hash=hash_password("SYNTHETIC-password-123"),
            role="BUSINESS_USER",
            status="ACTIVE",
            must_change_password=False,
            created_at=now(),
            updated_at=now(),
        )
        db.add(other)
        await db.flush()
    async with AsyncClient(
        transport=client._transport, base_url="https://synthetic.test"
    ) as second:
        assert (await login(client)).status_code == 200
        csrf = (await second.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
        assert (
            await second.post(
                "/api/v1/auth/login",
                json={"username": "synthetic-other", "password": "SYNTHETIC-password-123"},
                headers={"Origin": "https://synthetic.test", "X-CSRF-Token": csrf},
            )
        ).status_code == 200
        responses = await asyncio.gather(*(c.get("/api/v1/auth/me") for c in [client, second] * 5))
        assert [r.json()["data"]["principal_id"] for r in responses] == [
            account.principal_id,
            other.principal_id,
        ] * 5


async def test_a15_duplicate_origin_and_csrf_rejected(pg_auth):
    _, _, client, _, _ = pg_auth
    assert (await login(client)).status_code == 200
    csrf = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
    base = [("Origin", "https://synthetic.test"), ("X-CSRF-Token", csrf)]
    for extra in base:
        assert (
            await client.post("/api/v1/auth/logout", json={}, headers=[*base, extra])
        ).status_code == 403


async def test_a16_password_and_body_limits_before_hash(pg_auth):
    _, _, client, _, _ = pg_auth
    csrf = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
    headers = {"Origin": "https://synthetic.test", "X-CSRF-Token": csrf}
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"username": "synthetic-user", "password": "x" * 129},
            headers=headers,
        )
    ).status_code == 422
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"username": "synthetic-user", "password": "x" * 17000},
            headers=headers,
        )
    ).status_code == 413


async def test_a17_audit_failure_rolls_back_account_creation(pg_auth):
    _, factory, client, _, _ = pg_auth
    _, headers = await admin(pg_auth)
    async with factory() as db, db.begin():
        await db.execute(
            text(
                "CREATE FUNCTION synthetic_reject_audit() RETURNS trigger LANGUAGE plpgsql "
                "AS $$ BEGIN RAISE EXCEPTION 'SYNTHETIC audit fault'; END $$"
            )
        )
        await db.execute(
            text(
                "CREATE TRIGGER synthetic_reject_audit BEFORE INSERT ON auth_audit_event "
                "FOR EACH ROW EXECUTE FUNCTION synthetic_reject_audit()"
            )
        )
    response = await client.post(
        "/api/v1/admin/users",
        json={
            "username": "synthetic-rollback",
            "initial_password": "SYNTHETIC-temporary-password",
            "role": "BUSINESS_USER",
            "reason": "SYNTHETIC",
        },
        headers=headers,
    )
    assert response.status_code == 503 and "audit fault" not in response.text
    async with factory() as db:
        assert (
            await db.scalar(
                select(AuthAccount.account_id).where(
                    AuthAccount.username_normalized == "synthetic-rollback"
                )
            )
            is None
        )


async def test_a19_audit_has_no_credentials(pg_auth):
    _, factory, client, _, _ = pg_auth
    assert (await login(client)).status_code == 200
    async with factory() as db:
        records = (await db.scalars(select(AuthAuditEvent))).all()
        values = json.dumps(
            [
                {
                    column.name: str(getattr(r, column.name))
                    for column in AuthAuditEvent.__table__.columns
                }
                for r in records
            ]
        )
    assert all(
        v not in values
        for v in (
            "SYNTHETIC-password-123",
            client.cookies.get(COOKIE),
            "SYNTHETIC_TEST_ONLY_NOT_PRODUCTION",
        )
    )
