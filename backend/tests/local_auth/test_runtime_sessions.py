"""Runtime assertions against real PostgreSQL and actual authentication routes."""

import asyncio
from datetime import timedelta

import pytest
from argon2 import PasswordHasher
from sqlalchemy import select, update

from backend.app.local_auth.models import AuthAccount, AuthSession
from backend.app.local_auth.passwords import HASHER, hash_password, verify_password
from backend.app.local_auth.sessions import COOKIE
from backend.tests.local_auth.conftest import login

pytestmark = pytest.mark.postgres


async def test_a18_successful_login_rehashes_without_replacing_principal(pg_auth):
    _, factory, client, account, _ = pg_auth
    old = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(
        "SYNTHETIC-password-123"
    )
    async with factory() as db, db.begin():
        await db.execute(
            update(AuthAccount)
            .where(AuthAccount.account_id == account.account_id)
            .values(password_hash=old)
        )
    response = await login(client)
    assert response.status_code == 200
    assert response.json()["data"]["principal_id"] == account.principal_id
    async with factory() as db:
        changed = await db.get(AuthAccount, account.account_id)
        assert changed.password_hash != old and not HASHER.check_needs_rehash(changed.password_hash)


def test_argon2id_parameters_and_random_salts():
    first, second = hash_password("SYNTHETIC-password-123"), hash_password("SYNTHETIC-password-123")
    assert first != second and first.startswith("$argon2id$")
    assert HASHER.memory_cost >= 19456 and HASHER.time_cost >= 2 and HASHER.parallelism == 1
    assert verify_password(first, "SYNTHETIC-password-123")
    assert not verify_password(first, "SYNTHETIC-password-wrong")


@pytest.mark.asyncio
async def test_a01_login_cookie_digest_and_me(pg_auth):
    _, factory, client, account, _ = pg_auth
    response = await login(client)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert all(v in cookie for v in (COOKIE, "HttpOnly", "Secure", "SameSite=lax", "Path=/"))
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["data"]["principal_id"] == account.principal_id
    async with factory() as db:
        sessions = (await db.scalars(select(AuthSession))).all()
        assert len(sessions) == 2
        assert all(v.token_digest != client.cookies.get(COOKIE) for v in sessions)
        authenticated = next(v for v in sessions if v.kind == "END_USER")
        assert authenticated.absolute_expires_at - authenticated.issued_at == timedelta(hours=24)


@pytest.mark.asyncio
async def test_a02_wrong_password_and_disabled_have_same_safe_error(pg_auth):
    _, factory, client, account, _ = pg_auth
    wrong = await login(client, "SYNTHETIC-password-wrong")
    assert wrong.status_code == 401
    async with factory() as db, db.begin():
        await db.execute(
            update(AuthAccount)
            .where(AuthAccount.account_id == account.account_id)
            .values(status="DISABLED")
        )
    disabled = await login(client)
    assert disabled.status_code == 401 and disabled.json() == wrong.json()


@pytest.mark.asyncio
async def test_a03_revision_change_revokes_existing_session(pg_auth):
    _, factory, client, account, _ = pg_auth
    assert (await login(client)).status_code == 200
    async with factory() as db, db.begin():
        await db.execute(
            update(AuthAccount)
            .where(AuthAccount.account_id == account.account_id)
            .values(auth_revision=2)
        )
    assert (await client.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_a04_logout_invalidates_cookie(pg_auth):
    _, _, client, _, _ = pg_auth
    assert (await login(client)).status_code == 200
    token = client.cookies.get(COOKIE)
    csrf = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
    response = await client.post(
        "/api/v1/auth/logout",
        json={},
        headers={"Origin": "https://synthetic.test", "X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert (
        await client.get("/api/v1/auth/me", headers={"Cookie": f"{COOKIE}={token}"})
    ).status_code == 401


@pytest.mark.asyncio
async def test_a05_business_user_cannot_manage_accounts(pg_auth):
    _, _, client, _, _ = pg_auth
    assert (await login(client)).status_code == 200
    assert (await client.get("/api/v1/admin/users")).status_code == 403


@pytest.mark.asyncio
async def test_a15_csrf_origin_and_preauth_refresh(pg_auth):
    _, _, client, _, _ = pg_auth
    first = await client.get("/api/v1/auth/csrf")
    second = await client.get("/api/v1/auth/csrf")
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["csrf_token"] != second.json()["data"]["csrf_token"]
    payload = {"username": "synthetic-user", "password": "SYNTHETIC-password-123"}
    assert (
        await client.post(
            "/api/v1/auth/login", json=payload, headers={"Origin": "https://synthetic.test"}
        )
    ).status_code == 403
    assert (
        await client.post(
            "/api/v1/auth/login",
            json=payload,
            headers={
                "Origin": "https://evil.test",
                "X-CSRF-Token": second.json()["data"]["csrf_token"],
            },
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_a16_cross_worker_login_limit(pg_auth):
    auth, factory, client, _, _ = pg_auth
    from starlette.requests import Request

    from backend.app.local_auth.schemas import Login
    from backend.app.local_auth.service import AuthService
    from backend.app.local_auth.sessions import AuthError

    workers = [auth, AuthService(factory, auth.settings)]
    requests = []
    for _ in range(7):
        async with factory() as db, db.begin():
            raw, csrf = await auth.issue(db, None)
        requests.append(
            Request(
                {
                    "type": "http",
                    "method": "POST",
                    "scheme": "https",
                    "path": "/api/v1/auth/login",
                    "query_string": b"",
                    "server": ("synthetic.test", 443),
                    "client": ("127.0.0.1", 1),
                    "headers": [
                        (b"host", b"synthetic.test"),
                        (b"origin", b"https://synthetic.test"),
                        (b"content-type", b"application/json"),
                        (b"cookie", f"{COOKIE}={raw}".encode()),
                        (b"x-csrf-token", csrf.encode()),
                    ],
                }
            )
        )

    async def attempt(index):
        try:
            await workers[index % 2].login(
                requests[index],
                Login(username="synthetic-user", password="SYNTHETIC-password-wrong"),
            )
        except AuthError as exc:
            return exc.status
        raise AssertionError("Invalid password accepted")

    results = await asyncio.gather(*(attempt(i) for i in range(7)))
    assert results.count(401) == 5 and results.count(429) == 2
