"""SYNTHETIC real ASGI/SQLAlchemy/PostgreSQL. No authentication result mocks."""

import asyncio
import contextvars
import hashlib
import json
import time
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select, text

from backend.app.local_auth.models import AuthAuditEvent, AuthSession
from backend.app.local_auth.sessions import COOKIE, digest
from backend.tests.safe_pilot.test_restore_and_ingress import application

pytestmark = [pytest.mark.postgres, pytest.mark.concurrency]
LABEL = contextvars.ContextVar("synthetic_request_label", default="observer")
ORIGIN = "https://synthetic.test"
PAYLOAD = {"username": "synthetic-user", "password": "SYNTHETIC-password-123"}
ROOT = Path(__file__).resolve().parents[3]


def save(path, value, record_property):
    value["SYNTHETIC"] = True
    value["transport"] = "PRODUCTION_CREATE_APP_HTTPX_ASGI_TRANSPORT_NOT_NETWORK_TLS"
    value["source_sha256"] = {
        p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
        for p in (
            "backend/app/main.py",
            "backend/app/api/local_auth.py",
            "backend/app/local_auth/service.py",
            "backend/app/local_auth/sessions.py",
            "backend/app/local_auth/models.py",
            "backend/tests/local_auth/conftest.py",
            "backend/tests/safe_pilot/run.py",
            "backend/tests/preauth_repro_r1/test_concurrent_login.py",
        )
    }
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    record_property("PREAUTH_REPRO", json.dumps(value, sort_keys=True))


async def identity(db):
    pid, xid, isolation, version = (
        await db.execute(
            text(
                "SELECT pg_backend_pid(), txid_current(), "
                "current_setting('transaction_isolation'), current_setting('server_version')"
            )
        )
    ).one()
    return {"pid": pid, "transaction": str(xid), "isolation": isolation, "postgresql": version}


async def inspect(factory, account_id, preauth_id):
    async with factory() as db:
        row = await db.get(AuthSession, preauth_id)
        sessions = (
            await db.scalars(select(AuthSession).where(AuthSession.account_id == account_id))
        ).all()
        audits = (
            await db.scalars(
                select(AuthAuditEvent).where(
                    AuthAuditEvent.target_account_id == account_id,
                    AuthAuditEvent.action == "LOGIN_SUCCESS",
                )
            )
        ).all()
        return {
            "preauth": {
                "session_id": row.session_id,
                "kind": row.kind,
                "revoked": row.revoked_at is not None,
                "revoke_reason": row.revoke_reason,
            },
            "sessions": [
                {"session_id": s.session_id, "kind": s.kind, "revoked": s.revoked_at is not None}
                for s in sessions
            ],
            "login_success_audit_ids": [a.event_id for a in audits],
        }


async def handshake(client, factory):
    reply = await client.get("/api/v1/auth/csrf")
    assert reply.status_code == 200
    raw = client.cookies.get(COOKIE)
    assert raw
    async with factory() as db:
        row = await db.scalar(select(AuthSession).where(AuthSession.token_digest == digest(raw)))
        assert row.kind == "PREAUTH" and row.revoked_at is None
        preauth_id = row.session_id
    return raw, preauth_id, {"Origin": ORIGIN, "X-CSRF-Token": reply.json()["data"]["csrf_token"]}


async def post(client, raw, headers):
    # Explicit original Cookie; the client's newly rotated cookie is NOT replayed.
    return await client.post(
        "/api/v1/auth/login", json=PAYLOAD, headers=headers | {"Cookie": f"{COOKIE}={raw}"}
    )


async def test_01_real_login_and_consumed_preauth_sequential_replay(
    pg_auth, tmp_path, record_property
):
    auth, factory, _, user, _ = pg_auth
    app = application(auth)
    async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client:
        raw, preauth_id, headers = await handshake(client, factory)
        assert (
            await post(client, raw, headers | {"X-CSRF-Token": "SYNTHETIC_INVALID_TOKEN"})
        ).status_code == 403
        assert (
            await post(client, raw, headers | {"Origin": "https://invalid.synthetic.test"})
        ).status_code == 403
        first = await post(client, raw, headers)
        assert first.status_code == 200
        assert (await client.get("/api/v1/auth/me")).status_code == 200
        second = await post(client, raw, headers)
        old_me = await client.get("/api/v1/auth/me", headers={"Cookie": f"{COOKIE}={raw}"})
        state = await inspect(factory, user.account_id, preauth_id)
        result = {
            "case": "POSITIVE_AND_SEQUENTIAL_NEGATIVE_CONTROLS",
            "first_status": first.status_code,
            "sequential_replay_status": second.status_code,
            "old_preauth_me_status": old_me.status_code,
            "database": state,
        }
        save(tmp_path / "controls.json", result, record_property)
        assert second.status_code == old_me.status_code == 401
        assert len(state["sessions"]) == len(state["login_success_audit_ids"]) == 1
        assert state["preauth"]["revoked"] and state["preauth"]["revoke_reason"] == "LOGIN_ROTATION"


async def test_02_one_preauth_must_not_issue_two_valid_sessions(
    pg_auth, monkeypatch, tmp_path, record_property
):
    auth, factory, _, user, _ = pg_auth
    app = application(auth)
    loaded_a, resume_a = asyncio.Event(), asyncio.Event()
    timeline, transactions = [], {}
    engine = factory.kw["bind"]
    original_load, original_issue = auth.load, auth.issue

    def observe(kind, **details):
        timeline.append(
            {
                "sequence": len(timeline),
                "monotonic_ns": time.monotonic_ns(),
                "request": LABEL.get(),
                "event": kind,
                **details,
            }
        )

    def before(conn, cursor, statement, parameters, context, many):
        del conn, cursor, statement, parameters, many
        context.preauth_probe_start = time.monotonic_ns()

    def after(conn, cursor, statement, parameters, context, many):
        del cursor, parameters, many
        lower = statement.lower()
        kind = None
        if "pg_advisory_xact_lock" in lower:
            kind = "ADVISORY_LOCK_GRANTED"
        elif "auth_account" in lower and "for update" in lower:
            kind = "ACCOUNT_ROW_LOCK_GRANTED"
        elif lower.startswith("insert into auth_session"):
            kind = "SESSION_INSERT_EXECUTED"
        elif lower.startswith("update auth_session"):
            kind = "SESSION_UPDATE_EXECUTED"
        elif lower.startswith("insert into auth_audit_event"):
            kind = "AUDIT_INSERT_EXECUTED"
        if kind:
            observe(
                kind,
                pid=conn.connection.driver_connection.get_server_pid(),
                duration_ns=time.monotonic_ns() - context.preauth_probe_start,
            )

    async def load_barrier(db, request, **kwargs):
        value = await original_load(db, request, **kwargs)
        label = LABEL.get()
        if kwargs.get("preauth") and label in {"A", "B"}:
            assert kwargs.get("csrf") is True
            meta = await identity(db)
            transactions[label] = meta
            observe(
                "PREAUTH_VALIDATED",
                session_id=value[0].session_id,
                cached_revoked=value[0].revoked_at is not None,
                **meta,
            )
            if label == "A":
                loaded_a.set()
                await asyncio.wait_for(resume_a.wait(), 30)
                # Observe the original ORM object only; do not refresh/repair it.
                observe(
                    "A_RESUMED_WITH_ORIGINAL_OBJECT", cached_revoked=value[0].revoked_at is not None
                )
        return value

    async def issue_observer(db, account):
        if account is not None and LABEL.get() in {"A", "B"}:
            meta = await identity(db)
            assert meta == transactions[LABEL.get()]
            locks = (
                (
                    await db.execute(
                        text(
                            "SELECT locktype, mode, granted FROM pg_locks "
                            "WHERE pid=pg_backend_pid() ORDER BY locktype, mode"
                        )
                    )
                )
                .mappings()
                .all()
            )
            observe("BEFORE_REAL_SESSION_ISSUE", **meta, locks=[dict(x) for x in locks])
        return await original_issue(db, account)

    monkeypatch.setattr(auth, "load", load_barrier)
    monkeypatch.setattr(auth, "issue", issue_observer)
    event.listen(engine.sync_engine, "before_cursor_execute", before)
    event.listen(engine.sync_engine, "after_cursor_execute", after)
    pending = None
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client_a,
        AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client_b,
    ):
        try:
            raw, preauth_id, headers = await handshake(client_a, factory)

            async def call(label, client):
                token = LABEL.set(label)
                try:
                    reply = await post(client, raw, headers)
                    observe(
                        "HTTP_RESPONSE_COMPLETE_COMMIT_CONTEXT_EXITED", status=reply.status_code
                    )
                    return reply
                finally:
                    LABEL.reset(token)

            pending = asyncio.create_task(call("A", client_a))
            await asyncio.wait_for(loaded_a.wait(), 10)
            observe("A_BARRIER_REACHED_BEFORE_ANY_LOGIN_LOCK")
            reply_b = await asyncio.wait_for(call("B", client_b), 10)
            state_after_b = await inspect(factory, user.account_id, preauth_id)
            async with factory() as observer:
                commit_b = await observer.scalar(
                    text("SELECT pg_xact_status(CAST(:xid AS xid8))"),
                    {"xid": int(transactions["B"]["transaction"])},
                )
                activity = (
                    (
                        await observer.execute(
                            text(
                                "SELECT pid, state, wait_event_type, wait_event, "
                                "pg_blocking_pids(pid) AS blocking_pids FROM pg_stat_activity "
                                "WHERE pid IN (:a,:b) ORDER BY pid"
                            ),
                            {"a": transactions["A"]["pid"], "b": transactions["B"]["pid"]},
                        )
                    )
                    .mappings()
                    .all()
                )
            assert commit_b == "committed" and reply_b.status_code == 200
            assert state_after_b["preauth"]["revoked"] and len(state_after_b["sessions"]) == 1
            observe(
                "B_COMMIT_INDEPENDENTLY_CONFIRMED_BEFORE_A_RESUME",
                pg_xact_status=commit_b,
                database=state_after_b,
                activity=[dict(x) for x in activity],
            )
            resume_a.set()
            reply_a = await asyncio.wait_for(pending, 10)
            state = await inspect(factory, user.account_id, preauth_id)
            me_a, me_b = (
                await client_a.get("/api/v1/auth/me"),
                await client_b.get("/api/v1/auth/me"),
            )
            cookies = [client_a.cookies.get(COOKIE), client_b.cookies.get(COOKIE)]
            mapped = []
            async with factory() as db:
                commit_a = await db.scalar(
                    text("SELECT pg_xact_status(CAST(:xid AS xid8))"),
                    {"xid": int(transactions["A"]["transaction"])},
                )
                for raw_cookie in cookies:
                    row = (
                        await db.scalar(
                            select(AuthSession).where(
                                AuthSession.token_digest == digest(raw_cookie)
                            )
                        )
                        if raw_cookie
                        else None
                    )
                    mapped.append(row.session_id if row else None)
            old_me = await client_b.get("/api/v1/auth/me", headers={"Cookie": f"{COOKIE}={raw}"})
            state_final = await inspect(factory, user.account_id, preauth_id)
            assert transactions["A"]["pid"] != transactions["B"]["pid"]
            assert transactions["A"]["transaction"] != transactions["B"]["transaction"]
            assert state_final["preauth"]["revoked"] and old_me.status_code == 401
            assert all(t["isolation"] == "read committed" for t in transactions.values())
            valid_count = sum(reply.status_code == 200 for reply in (me_a, me_b))
            classification = "INCONCLUSIVE"
            if (
                reply_a.status_code == reply_b.status_code == 200
                and valid_count == len(set(mapped)) == len(state["sessions"]) == 2
                and len(state["login_success_audit_ids"]) == 2
                and commit_a == commit_b == "committed"
            ):
                classification = "RED_CONFIRMED"
            elif (
                reply_a.status_code in {401, 403}
                and reply_b.status_code == 200
                and valid_count == len(state["sessions"]) == 1
                and len(state["login_success_audit_ids"]) == 1
            ):
                classification = "GREEN_NOT_REPRODUCED"
            result = {
                "case": "A_LOAD_B_COMMIT_A_RESUME",
                "classification": classification,
                "deterministic_barrier": True,
                "shared_preauth_session_id": preauth_id,
                "request_a_status": reply_a.status_code,
                "request_b_status": reply_b.status_code,
                "me_a_status": me_a.status_code,
                "me_b_status": me_b.status_code,
                "successful_login_count": sum(r.status_code == 200 for r in (reply_a, reply_b)),
                "new_auth_session_count": len(state["sessions"]),
                "independently_valid_cookie_count": valid_count,
                "cookie_session_ids": mapped,
                "login_success_audit_count": len(state["login_success_audit_ids"]),
                "a_transaction_final_status": commit_a,
                "b_transaction_before_a_resume": commit_b,
                "database": state_final,
                "transactions": transactions,
                "timeline": timeline,
                "old_preauth_me_status": old_me.status_code,
            }
            save(tmp_path / "concurrent.json", result, record_property)
            assert classification != "INCONCLUSIVE", "Target outcome was not established"
            # Actual security invariant; leave RED as a real failing test.
            assert result["successful_login_count"] <= 1, (
                "PREAUTH consumed twice by committed production login transactions"
            )
            assert (
                valid_count <= 1
                and len(state["sessions"]) <= 1
                and len(state["login_success_audit_ids"]) <= 1
            )
        finally:
            resume_a.set()
            if pending is not None and not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
            event.remove(engine.sync_engine, "before_cursor_execute", before)
            event.remove(engine.sync_engine, "after_cursor_execute", after)
