"""Actual ADMIN HTTP management with explicitly synthetic publisher approval."""

import json

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import select, update

from backend.app.local_auth.models import AuthAccount, AuthAuditEvent, AuthResourceGrant
from backend.tests.local_auth.conftest import login

pytestmark = pytest.mark.postgres


async def admin(pg_auth):
    auth, factory, client, account, _ = pg_auth
    async with factory() as db, db.begin():
        await db.execute(
            update(AuthAccount)
            .where(AuthAccount.account_id == account.account_id)
            .values(role="ADMIN")
        )
    boundary = {
        "principal_id": account.principal_id,
        "organization_ids": ["SYNTHETIC_ORG"],
        "manageable_account_ids": [account.account_id],
        "create_roles": ["BUSINESS_USER"],
        "approved_grants": [],
    }
    auth.settings.local_auth_publisher_boundaries_json = SecretStr(json.dumps([boundary]))
    assert (await login(client)).status_code == 200
    csrf = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
    return boundary, {"Origin": "https://synthetic.test", "X-CSRF-Token": csrf}


@pytest.mark.asyncio
async def test_a01_admin_creates_account_without_business_grants(pg_auth):
    _, factory, client, _, _ = pg_auth
    _, headers = await admin(pg_auth)
    result = await client.post(
        "/api/v1/admin/users",
        json={
            "username": "synthetic-child",
            "initial_password": "SYNTHETIC-temporary-password",
            "role": "BUSINESS_USER",
            "reason": "SYNTHETIC acceptance",
        },
        headers=headers,
    )
    assert result.status_code == 201
    child = result.json()["data"]
    assert child["must_change_password"] and child["role"] == "BUSINESS_USER"
    assert "password_hash" not in result.text
    async with factory() as db:
        assert (
            await db.scalar(
                select(AuthResourceGrant.grant_id).where(
                    AuthResourceGrant.principal_id == child["principal_id"]
                )
            )
            is None
        )
        assert (
            await db.scalar(
                select(AuthAuditEvent.event_id).where(AuthAuditEvent.action == "ACCOUNT_CREATED")
            )
            is not None
        )
    await client.post("/api/v1/auth/logout", json={}, headers=headers)
    csrf = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
    signed = await client.post(
        "/api/v1/auth/login",
        json={"username": "synthetic-child", "password": "SYNTHETIC-temporary-password"},
        headers={"Origin": "https://synthetic.test", "X-CSRF-Token": csrf},
    )
    assert (
        signed.status_code == 200 and signed.json()["data"]["principal_id"] == child["principal_id"]
    )


@pytest.mark.asyncio
async def test_a17_last_admin_cas_and_explicit_management_scope(pg_auth):
    _, _, client, account, _ = pg_auth
    _, headers = await admin(pg_auth)
    root = f"/api/v1/admin/users/{account.account_id}/status"
    payload = {"status": "DISABLED", "expected_auth_revision": 1, "reason": "SYNTHETIC acceptance"}
    denied = await client.patch(root, json=payload, headers=headers)
    assert denied.status_code == 409 and denied.json()["code"] == "LAST_ADMIN_PROTECTED"
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    stale = await client.patch(
        root, json={**payload, "expected_auth_revision": 999}, headers=headers
    )
    assert stale.status_code == 409 and stale.json()["code"] == "REVISION_CONFLICT"
    unauthorized = await client.patch(
        "/api/v1/admin/users/00000000-0000-0000-0000-000000000001/status",
        json=payload,
        headers=headers,
    )
    assert unauthorized.status_code == 403


@pytest.mark.asyncio
async def test_a20_missing_publisher_and_invalid_origin_fail_closed(pg_auth):
    auth, _, client, _, _ = pg_auth
    await admin(pg_auth)
    auth.settings.local_auth_publisher_boundaries_json = SecretStr("")
    unavailable = await client.get("/api/v1/admin/users")
    assert unavailable.status_code == 503
    assert all(
        value not in unavailable.text
        for value in ("SELECT", "password_hash", "postgresql", "Traceback")
    )
    auth.settings.local_auth_origin = ""
    assert (await client.get("/api/v1/auth/me")).status_code == 503


@pytest.mark.asyncio
async def test_a03_admin_reset_forced_change_and_old_session_revocation(pg_auth):
    auth, _, client, _, _ = pg_auth
    boundary, headers = await admin(pg_auth)
    created = await client.post(
        "/api/v1/admin/users",
        json={
            "username": "synthetic-child",
            "initial_password": "SYNTHETIC-temporary-password",
            "role": "BUSINESS_USER",
            "reason": "SYNTHETIC acceptance",
        },
        headers=headers,
    )
    assert created.status_code == 201
    child = created.json()["data"]
    boundary["manageable_account_ids"].append(child["account_id"])
    auth.settings.local_auth_publisher_boundaries_json = SecretStr(json.dumps([boundary]))
    async with AsyncClient(transport=client._transport, base_url="https://synthetic.test") as user:

        async def sign_in(password):
            csrf = (await user.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
            return await user.post(
                "/api/v1/auth/login",
                json={"username": "synthetic-child", "password": password},
                headers={"Origin": "https://synthetic.test", "X-CSRF-Token": csrf},
            )

        assert (await sign_in("SYNTHETIC-temporary-password")).status_code == 200
        reset = await client.post(
            f"/api/v1/admin/users/{child['account_id']}/reset-password",
            json={
                "new_temporary_password": "SYNTHETIC-reset-password",
                "expected_auth_revision": 1,
                "reason": "SYNTHETIC acceptance",
            },
            headers=headers,
        )
        assert reset.status_code == 200
        assert (await user.get("/api/v1/auth/me")).status_code == 401
        assert (await sign_in("SYNTHETIC-reset-password")).status_code == 200
        assert (await user.get("/api/v1/auth/me")).json()["data"]["must_change_password"] is True
        csrf = (await user.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
        changed = await user.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "SYNTHETIC-reset-password",
                "new_password": "SYNTHETIC-final-password",
            },
            headers={"Origin": "https://synthetic.test", "X-CSRF-Token": csrf},
        )
        assert changed.status_code == 200
        assert (await user.get("/api/v1/auth/me")).json()["data"]["must_change_password"] is False


@pytest.mark.asyncio
async def test_a18_synthetic_bootstrap_requires_approval_and_is_not_repeatable(pg_auth):
    from backend.app.local_auth.bootstrap import bootstrap
    from backend.app.local_auth.sessions import AuthError

    _, factory, _, _, _ = pg_auth
    with pytest.raises(AuthError):
        await bootstrap(factory, "synthetic-bootstrap", "SYNTHETIC-bootstrap-password")
    first = await bootstrap(
        factory,
        "synthetic-bootstrap",
        "SYNTHETIC-bootstrap-password",
        trusted_operator_approved=True,
    )
    with pytest.raises(AuthError) as failure:
        await bootstrap(
            factory,
            "synthetic-other",
            "SYNTHETIC-bootstrap-password",
            trusted_operator_approved=True,
        )
    assert failure.value.code == "BOOTSTRAP_ALREADY_COMPLETED"
    async with factory() as db:
        account = await db.scalar(select(AuthAccount).where(AuthAccount.principal_id == first))
        assert account.must_change_password and account.role == "ADMIN"
