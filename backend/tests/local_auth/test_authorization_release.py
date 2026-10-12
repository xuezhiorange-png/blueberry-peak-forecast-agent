"""Real PostgreSQL grant and ASGI release linearization assertions."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select, update
from starlette.requests import Request

from backend.app.forecast_intelligence.read_schemas import QualityReadQuery
from backend.app.local_auth.authorization import GuardedResponse, authorize
from backend.app.local_auth.models import AuthAccount, AuthResourceGrant
from backend.app.local_auth.sessions import COOKIE, AuthError, now
from backend.tests.forecast_intelligence.test_v0_17_s1_service_read_api import query
from backend.tests.local_auth.conftest import login

pytestmark = pytest.mark.postgres


def request(client):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "path": "/api/v1/forecast-intelligence/curve",
            "query_string": b"",
            "server": ("synthetic.test", 443),
            "client": ("127.0.0.1", 1),
            "headers": [
                (b"host", b"synthetic.test"),
                (b"cookie", f"{COOKIE}={client.cookies.get(COOKIE)}".encode()),
            ],
        }
    )


async def grant_for(factory, account):
    selection = query()
    async with factory() as db, db.begin():
        grant = AuthResourceGrant(
            principal_id=account.principal_id,
            resource_kind="FORECAST",
            capability="may_read_forecast",
            organization_id="SYNTHETIC_ORG",
            approved_by_principal=account.principal_id,
            approval_reference="SYNTHETIC_TEST_ONLY",
            reason="isolated acceptance",
            grant_revision=1,
            forecast_binding={
                "identity": selection.model_dump(
                    mode="json", exclude={"expected_source_result_hash"}
                ),
                "expected_source_result_hash": "a" * 64,
                "source_authority_version": "SYNTHETIC_R1",
            },
            quality_binding=None,
            valid_from=now() - timedelta(seconds=5),
            valid_until=now() + timedelta(hours=1),
            created_at=now(),
        )
        db.add(grant)
        await db.flush()
    return grant


@pytest.mark.asyncio
async def test_a06_admin_has_no_implicit_resource_access(pg_auth):
    auth, factory, client, account, _ = pg_auth
    async with factory() as db, db.begin():
        await db.execute(
            update(AuthAccount)
            .where(AuthAccount.account_id == account.account_id)
            .values(role="ADMIN")
        )
    assert (await login(client)).status_code == 200
    principal = await auth.authenticate(request(client))
    for selection in (query(), QualityReadQuery()):
        with pytest.raises(AuthError) as failure:
            await authorize(auth, principal, selection)
        assert failure.value.status == 403


@pytest.mark.asyncio
async def test_a07_a08_a09_exact_identity_and_independent_quality(pg_auth):
    auth, factory, client, account, _ = pg_auth
    await grant_for(factory, account)
    assert (await login(client)).status_code == 200
    principal = await auth.authenticate(request(client))
    snapshot, selection = await authorize(auth, principal, query())
    assert selection.expected_source_result_hash == "a" * 64
    assert snapshot["principal_id"] == account.principal_id
    for changed in (
        query(run_id=2),
        query(entity_id="other"),
        query(hierarchy_level="REGION"),
        query(hierarchy_level="COMPANY"),
        query(target_season="2026-2027"),
        query(forecast_family="other"),
        query(expected_source_result_hash="b" * 64),
        QualityReadQuery(),
    ):
        with pytest.raises(AuthError) as failure:
            await authorize(auth, principal, changed)
        assert failure.value.status == 403
    auth.settings.local_auth_organization_ids_json = '["OTHER_ORGANIZATION"]'
    with pytest.raises(AuthError):
        await authorize(auth, principal, query())


@pytest.mark.asyncio
async def test_a11_revocation_committed_before_release_sends_no_sensitive_bytes(pg_auth):
    auth, factory, client, account, _ = pg_auth
    grant = await grant_for(factory, account)
    assert (await login(client)).status_code == 200
    incoming = request(client)
    principal = await auth.authenticate(incoming)
    snapshot, _ = await authorize(auth, principal, query())
    response = GuardedResponse(
        {"SENSITIVE_SYNTHETIC_RESULT": "must not release"}, auth, incoming, principal, snapshot
    )
    async with factory() as db, db.begin():
        subject = await db.scalar(
            select(AuthAccount)
            .where(AuthAccount.account_id == account.account_id)
            .with_for_update()
        )
        subject.grant_revision += 1
        await db.execute(
            update(AuthResourceGrant)
            .where(AuthResourceGrant.grant_id == grant.grant_id)
            .values(revoked_at=now())
        )
        await auth.revoke_all(db, subject, "SYNTHETIC_REVOCATION")
    messages = []

    async def send(message):
        messages.append(message)

    async def receive():
        return {"type": "http.disconnect"}

    await response(incoming.scope, receive, send)
    assert messages[0]["status"] in {401, 403}
    assert b"SENSITIVE_SYNTHETIC_RESULT" not in b"".join(v.get("body", b"") for v in messages)


@pytest.mark.asyncio
async def test_a12_release_lock_blocks_revocation_and_cancellation_releases_lock(pg_auth):
    auth, factory, client, account, _ = pg_auth
    await grant_for(factory, account)
    assert (await login(client)).status_code == 200
    incoming = request(client)
    principal = await auth.authenticate(incoming)
    snapshot, _ = await authorize(auth, principal, query())
    response = GuardedResponse(
        {"source_result_hash": "a" * 64}, auth, incoming, principal, snapshot
    )
    entered = asyncio.Event()
    blocked = asyncio.Event()

    async def send(message):
        if message["type"] == "http.response.start":
            entered.set()
            await blocked.wait()

    async def receive():
        return {"type": "http.disconnect"}

    sending = asyncio.create_task(response(incoming.scope, receive, send))
    await asyncio.wait_for(entered.wait(), 3)

    async def revoke():
        async with factory() as db, db.begin():
            await db.execute(
                update(AuthAccount)
                .where(AuthAccount.account_id == account.account_id)
                .values(auth_revision=2)
            )

    revoking = asyncio.create_task(revoke())
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(asyncio.shield(revoking), 0.1)
    sending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await sending
    await asyncio.wait_for(revoking, 3)
    assert (await client.get("/api/v1/auth/me")).status_code == 401
