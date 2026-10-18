"""Real synthetic PostgreSQL/production ASGI; fault hooks never fake success."""

import asyncio
import hashlib
from datetime import timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select

from backend.app.local_auth import service as service_module
from backend.app.local_auth.models import AuthAuditEvent, AuthSession
from backend.app.local_auth.service import AuthService
from backend.app.local_auth.sessions import COOKIE, digest, now
from backend.tests.preauth_repro_r1.test_concurrent_login import (
    ORIGIN,
    PAYLOAD,
    handshake,
    inspect,
    post,
    save,
)
from backend.tests.safe_pilot.test_restore_and_ingress import application

pytestmark = [pytest.mark.postgres, pytest.mark.concurrency]


def test_original_red_probe_bytes_unchanged():
    raw = Path(__file__).with_name("test_concurrent_login.py").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "35d4c982c39c8737d8f43b949f2228a7c0cc9ddb08cffdd350aedbffaf9bafdb"
    )


async def test_distinct_preauth_can_both_login_with_real_session_row_locks(
    pg_auth, tmp_path, record_property
):
    auth, factory, _, user, _ = pg_auth
    app = application(auth)
    locks = []
    engine = factory.kw["bind"]

    def observe(conn, cursor, statement, parameters, context, many):
        del cursor, parameters, context, many
        lower = statement.lower()
        if "from auth_session" in lower and "for update" in lower:
            assert "auth_session.session_id =" in lower and "auth_session.token_digest =" in lower
            locks.append({"pid": conn.connection.driver_connection.get_server_pid()})

    event.listen(engine.sync_engine, "after_cursor_execute", observe)
    try:
        async with (
            AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as a,
            AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as b,
        ):
            raw_a, id_a, headers_a = await handshake(a, factory)
            raw_b, id_b, headers_b = await handshake(b, factory)
            assert id_a != id_b and raw_a != raw_b
            responses = await asyncio.wait_for(
                asyncio.gather(post(a, raw_a, headers_a), post(b, raw_b, headers_b)), 10
            )
            assert [r.status_code for r in responses] == [200, 200]
            assert (await a.get("/api/v1/auth/me")).status_code == 200
            assert (await b.get("/api/v1/auth/me")).status_code == 200
            state_a, state_b = (
                await inspect(factory, user.account_id, id_a),
                await inspect(factory, user.account_id, id_b),
            )
            assert state_a["preauth"]["revoked"] and state_b["preauth"]["revoked"]
            assert len(state_a["sessions"]) == len(state_a["login_success_audit_ids"]) == 2
            assert len(locks) == 2
            save(
                tmp_path / "distinct.json",
                {
                    "case": "DISTINCT_PREAUTH_LEGAL",
                    "statuses": [r.status_code for r in responses],
                    "session_for_update_observations": locks,
                    "database": state_a,
                },
                record_property,
            )
    finally:
        event.remove(engine.sync_engine, "after_cursor_execute", observe)


@pytest.mark.parametrize("change", ["idle_expiry", "absolute_expiry", "revoked", "csrf", "digest"])
async def test_locked_final_preauth_validation_rejects_inflight_changes(
    pg_auth, monkeypatch, change, tmp_path, record_property
):
    auth, factory, _, user, _ = pg_auth
    app = application(auth)
    loaded, resume = asyncio.Event(), asyncio.Event()
    original = auth.load
    paused = False

    async def barrier(db, request, **kwargs):
        nonlocal paused
        result = await original(db, request, **kwargs)
        if kwargs.get("preauth") and request.method == "POST" and not paused:
            paused = True
            loaded.set()
            await asyncio.wait_for(resume.wait(), 10)
        return result

    monkeypatch.setattr(auth, "load", barrier)
    async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client:
        raw, preauth_id, headers = await handshake(client, factory)
        pending = asyncio.create_task(post(client, raw, headers))
        try:
            await asyncio.wait_for(loaded.wait(), 10)
            if change == "csrf":
                refresh = await client.get(
                    "/api/v1/auth/csrf", headers={"Cookie": f"{COOKIE}={raw}"}
                )
                assert refresh.status_code == 200
                assert refresh.json()["data"]["csrf_token"] != headers["X-CSRF-Token"]
            else:
                async with factory() as db, db.begin():
                    row = await db.scalar(
                        select(AuthSession)
                        .where(AuthSession.session_id == preauth_id)
                        .with_for_update()
                    )
                    if change == "idle_expiry":
                        row.idle_expires_at = now() - timedelta(seconds=1)
                    elif change == "absolute_expiry":
                        row.issued_at = now() - timedelta(hours=1)
                        row.absolute_expires_at = now() - timedelta(seconds=1)
                    elif change == "revoked":
                        row.revoked_at, row.revoke_reason = now(), "SYNTHETIC_REVOKE"
                    else:
                        row.token_digest = digest("SYNTHETIC_REPLACED_TOKEN_NOT_A_CREDENTIAL")
            resume.set()
            response = await asyncio.wait_for(pending, 10)
            expected = 403 if change == "csrf" else 401
            assert response.status_code == expected
            assert response.json()["data"] is None
            assert COOKIE not in client.cookies or client.cookies.get(COOKIE) == raw
            state = await inspect(factory, user.account_id, preauth_id)
            assert not state["sessions"] and not state["login_success_audit_ids"]
            save(
                tmp_path / "inflight-change.json",
                {
                    "case": "INFLIGHT_PREAUTH_CHANGE",
                    "change": change,
                    "status": response.status_code,
                    "database": state,
                },
                record_property,
            )
        finally:
            resume.set()
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)


async def test_concurrent_wrong_passwords_use_postgres_cross_worker_limits(
    pg_auth, tmp_path, record_property
):
    auth, factory, _, user, _ = pg_auth
    workers = [application(auth), application(AuthService(factory, auth.settings))]
    clients = [
        AsyncClient(transport=ASGITransport(app=workers[i % 2]), base_url=ORIGIN) for i in range(7)
    ]
    try:
        handshakes = [await handshake(c, factory) for c in clients]

        async def wrong(client, context):
            raw, _, headers = context
            return await client.post(
                "/api/v1/auth/login",
                json=PAYLOAD | {"password": "SYNTHETIC-wrong-password-123"},
                headers=headers | {"Cookie": f"{COOKIE}={raw}"},
            )

        replies = await asyncio.wait_for(
            asyncio.gather(*(wrong(c, h) for c, h in zip(clients, handshakes, strict=True))), 10
        )
        statuses = [r.status_code for r in replies]
        assert statuses.count(401) == 5 and statuses.count(429) == 2
        state = await inspect(factory, user.account_id, handshakes[0][1])
        assert not state["sessions"] and not state["login_success_audit_ids"]
        async with factory() as db:
            failures = (
                await db.scalars(
                    select(AuthAuditEvent).where(AuthAuditEvent.action == "LOGIN_FAILURE")
                )
            ).all()
        assert len(failures) == 15  # Five attempts, each audits three existing buckets.
        save(
            tmp_path / "wrong-passwords.json",
            {
                "case": "CROSS_WORKER_WRONG_PASSWORD_LIMIT",
                "statuses": statuses,
                "login_failure_audit_rows": len(failures),
                "database": state,
            },
            record_property,
        )
    finally:
        await asyncio.gather(*(c.aclose() for c in clients))


@pytest.mark.parametrize(
    "fault", ["after_issue_exception", "after_issue_cancel", "audit_exception"]
)
async def test_transaction_rollback_has_no_ghost_session_or_success_audit(
    pg_auth, monkeypatch, fault, tmp_path, record_property
):
    auth, factory, _, user, _ = pg_auth
    app = application(auth)
    issued, hold = asyncio.Event(), asyncio.Event()
    original_issue, original_audit = auth.issue, service_module.audit
    inject = True

    async def issue(db, account):
        result = await original_issue(db, account)
        if account is not None and inject:
            issued.set()
            if fault == "after_issue_cancel":
                await hold.wait()
            elif fault == "after_issue_exception":
                raise OSError("SYNTHETIC_TRANSACTION_FAULT")
        return result

    def audit(db, action, **kwargs):
        original_audit(db, action, **kwargs)
        if action == "LOGIN_SUCCESS" and inject and fault == "audit_exception":
            raise OSError("SYNTHETIC_AUDIT_FAULT")

    monkeypatch.setattr(auth, "issue", issue)
    monkeypatch.setattr(service_module, "audit", audit)
    async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client:
        raw, preauth_id, headers = await handshake(client, factory)
        pending = asyncio.create_task(post(client, raw, headers))
        try:
            if fault == "after_issue_cancel":
                await asyncio.wait_for(issued.wait(), 10)
                pending.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await pending
                status = None
            else:
                response = await asyncio.wait_for(pending, 10)
                status = response.status_code
                assert status == 503  # Expected injected failure, NOT concurrency GREEN.
            assert issued.is_set()
            before_retry = await inspect(factory, user.account_id, preauth_id)
            assert not before_retry["preauth"]["revoked"]
            assert not before_retry["sessions"] and not before_retry["login_success_audit_ids"]
            inject = False
            retry = await post(client, raw, headers)
            assert retry.status_code == 200
            assert (await client.get("/api/v1/auth/me")).status_code == 200
            state = await inspect(factory, user.account_id, preauth_id)
            assert state["preauth"]["revoked"]
            assert len(state["sessions"]) == len(state["login_success_audit_ids"]) == 1
            save(
                tmp_path / "rollback.json",
                {
                    "case": "TRANSACTION_ROLLBACK",
                    "fault": fault,
                    "injected_failure_status": status,
                    "before_retry": before_retry,
                    "after_legal_retry": state,
                },
                record_property,
            )
        finally:
            hold.set()
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
