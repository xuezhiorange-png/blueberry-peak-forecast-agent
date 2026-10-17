"""SYNTHETIC: real PostgreSQL, real HTTP, event barriers and actual work counters."""

import asyncio
import json
from collections import Counter
from datetime import timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select, text

from backend.app.forecast_intelligence import what_if
from backend.app.forecast_intelligence.read_schemas import QualityReadQuery
from backend.app.forecast_intelligence.read_service import (
    EVIDENCE_ROOT,
    PUBLIC_EVIDENCE_HASHES,
    ForecastIntelligenceReadService,
)
from backend.app.forecast_quality.operational_peak_persistence import OperationalPeakRunRepository
from backend.app.local_auth.authorization import GuardedResponse, binding_digest
from backend.app.local_auth.models import AuthAccount, AuthResourceGrant
from backend.app.local_auth.sessions import now
from backend.tests.business_access.test_discovery import app_for
from backend.tests.business_access.test_security import selected as selected_payload
from backend.tests.forecast_intelligence.test_v0_17_s2_decision_service import (
    comparison_payload,
    request_payload,
)
from backend.tests.local_auth.conftest import login
from backend.tests.safe_pilot.test_restore_and_ingress import seed

pytestmark = pytest.mark.postgres
REVOCATIONS = ("disable", "grant", "session", "revision", "auth_revision")
OPERATIONS = ("curve", "quality", "simulate", "compare", "scope", "saved-runs", "selection")


class WorkProbe:
    def __init__(self, engine, monkeypatch):
        self.engine = engine
        self.phase = "positive_control"
        self.events = []
        self.counts = Counter()
        original_file = Path.read_bytes
        original_simulate, original_compare = what_if.simulate, what_if.compare_and_rank

        def read_bytes(path):
            if path.is_relative_to(EVIDENCE_ROOT):
                self.observe("quality_file", name=str(path.relative_to(EVIDENCE_ROOT)))
            return original_file(path)

        def simulate(scenario):
            self.observe("simulation")
            return original_simulate(scenario)

        def compare(scenarios):
            self.observe("comparison")
            return original_compare(scenarios)

        monkeypatch.setattr(Path, "read_bytes", read_bytes)
        monkeypatch.setattr(what_if, "simulate", simulate)
        monkeypatch.setattr(what_if, "compare_and_rank", compare)
        event.listen(engine.sync_engine, "after_cursor_execute", self.sql)

    def observe(self, kind, **details):
        self.counts[(self.phase, kind)] += 1
        self.events.append({"event": kind, "phase": self.phase, **details})

    def sql(self, connection, cursor, statement, parameters, context, many):
        del cursor, parameters, context, many
        lower = statement.lower().lstrip()
        if lower.startswith("select") and (
            "operational_peak_forecast" in lower or "hierarchical_forecast" in lower
        ):
            pid, transaction, isolation = connection.exec_driver_sql(
                "SELECT pg_backend_pid(), txid_current(), current_setting('transaction_isolation')"
            ).one()
            self.observe("business_sql", pid=pid, transaction=transaction, isolation=isolation)

    def close(self):
        event.remove(self.engine.sync_engine, "after_cursor_execute", self.sql)


async def fixture(auth, factory, user):
    query, forecast_grant = await seed(factory, user)
    async with factory() as db:
        curve = await ForecastIntelligenceReadService(db).curve(query)
    quality = QualityReadQuery()
    async with factory() as db, db.begin():
        grant = AuthResourceGrant(
            principal_id=user.principal_id,
            resource_kind="QUALITY",
            capability="may_read_quality",
            organization_id="SYNTHETIC_ORG",
            approved_by_principal=user.principal_id,
            approval_reference="SYNTHETIC_TEST_ONLY",
            reason="SYNTHETIC revocation regression",
            grant_revision=1,
            quality_binding={
                "query": quality.model_dump(mode="json"),
                "source_split": "EXPOSED_OOT",
                "target_season": "2025-2026",
                "scope": "BASE_COHORT_AGGREGATE",
                "evidence_policy_version": "SYNTHETIC_R1",
                "evidence_hashes": PUBLIC_EVIDENCE_HASHES,
                "evidence_set_digest": binding_digest(PUBLIC_EVIDENCE_HASHES),
            },
            valid_from=now() - timedelta(seconds=5),
            valid_until=now() + timedelta(hours=1),
            created_at=now(),
        )
        db.add(grant)
        await db.flush()
    return query, forecast_grant, grant, curve, app_for(auth)


async def revoke(auth, factory, user, grant_id, kind, events):
    async with factory() as db, db.begin():
        account = await db.scalar(
            select(AuthAccount).where(AuthAccount.account_id == user.account_id).with_for_update()
        )
        pid, transaction, isolation = (
            await db.execute(
                text(
                    "SELECT pg_backend_pid(), txid_current(), "
                    "current_setting('transaction_isolation')"
                )
            )
        ).one()
        if kind == "disable":
            account.status = "DISABLED"
            account.auth_revision += 1
            await auth.revoke_all(db, account, "SYNTHETIC_DISABLE")
        elif kind == "grant":
            grant = await db.get(AuthResourceGrant, grant_id)
            grant.revoked_at = now()
            account.grant_revision += 1
            await auth.revoke_all(db, account, "SYNTHETIC_GRANT_REVOKED")
        elif kind == "session":
            # Same subject-lock protocol as actual logout; no account revision bump.
            await auth.revoke_all(db, account, "SYNTHETIC_SESSION_REVOKED")
        elif kind == "auth_revision":
            account.auth_revision += 1
        else:
            # A version mismatch must fail even without explicit session revocation.
            account.grant_revision += 1
        events.append(
            {
                "event": "revocation_locked",
                "pid": pid,
                "transaction": transaction,
                "isolation": isolation,
                "kind": kind,
            }
        )
    events.append({"event": "revocation_commit_completed", "kind": kind})


@pytest.mark.parametrize("revocation", REVOCATIONS)
@pytest.mark.parametrize("operation", OPERATIONS)
async def test_committed_revocation_prevents_all_sensitive_work(
    pg_auth, monkeypatch, record_property, operation, revocation
):
    auth, factory, _, user, _ = pg_auth
    query, forecast_grant, quality_grant, curve, app = await fixture(auth, factory, user)
    ready, resume = asyncio.Event(), asyncio.Event()
    pause = False
    sent = []
    original_authenticate = auth.authenticate

    async def authentication_barrier(request, **kwargs):
        principal = await original_authenticate(request, **kwargs)
        if pause:
            ready.set()
            await resume.wait()
        return principal

    async def measured_app(scope, receive, send):
        async def capture(message):
            if pause:
                sent.append(dict(message))
            await send(message)

        await app(scope, receive, capture)

    monkeypatch.setattr(auth, "authenticate", authentication_barrier)
    probe = WorkProbe(factory.kw["bind"], monkeypatch)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=measured_app), base_url="https://synthetic.test"
        ) as client:
            assert (await login(client)).status_code == 200
            token = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
            headers = {"Origin": "https://synthetic.test", "X-CSRF-Token": token}
            selection = await selected_payload(client) if operation == "selection" else None

            async def call():
                if operation in {"simulate", "compare"}:
                    payload = request_payload(curve)
                    name = (
                        "simulate-capacity"
                        if operation == "simulate"
                        else "compare-capacity-scenarios"
                    )
                    return await client.post(
                        "/api/v1/decision-support/" + name,
                        json=payload if operation == "simulate" else comparison_payload(payload),
                        headers=headers,
                    )
                if operation == "selection":
                    return await client.post(
                        "/api/v1/business-access/selection", json=selection, headers=headers
                    )
                if operation in {"scope", "saved-runs"}:
                    return await client.get("/api/v1/business-access/" + operation)
                return await client.get(
                    "/api/v1/forecast-intelligence/" + operation,
                    params=(QualityReadQuery() if operation == "quality" else query).model_dump(
                        mode="json", exclude_none=True
                    ),
                )

            response = await call()
            assert response.status_code == 200, response.text
            expected = {
                "quality": "quality_file",
                "simulate": "simulation",
                "compare": "comparison",
            }.get(operation, "business_sql")
            assert probe.counts[("positive_control", expected)] > 0
            positive = dict(
                Counter(
                    {k: v for (phase, k), v in probe.counts.items() if phase == "positive_control"}
                )
            )
            probe.phase = "paused_before_admission"
            pause = True
            pending = asyncio.create_task(call())
            try:
                await asyncio.wait_for(ready.wait(), 5)
                probe.events.append({"event": "authenticated_before_revocation"})
                await revoke(
                    auth,
                    factory,
                    user,
                    quality_grant.grant_id if operation == "quality" else forecast_grant.grant_id,
                    revocation,
                    probe.events,
                )
                probe.phase = "after_commit"
                resume.set()
                result = await asyncio.wait_for(pending, 10)
                assert result.status_code in {401, 403}, result.text
                body = b"".join(m.get("body", b"") for m in sent)
                assert body == result.content
                sensitive_sent = json.loads(body)["data"] is not None
                assert not sensitive_sent
                assert query.expected_source_result_hash not in body.decode()
                observed = {
                    kind: probe.counts[("after_commit", kind)]
                    for kind in ("business_sql", "quality_file", "simulation", "comparison")
                }
                report = {
                    "SYNTHETIC": True,
                    "operation": operation,
                    "revocation": revocation,
                    "positive_control_counts": positive,
                    "post_commit_counts": observed,
                    "http_status": result.status_code,
                    "sensitive_response_sent": sensitive_sent,
                    "timeline": probe.events,
                }
                record_property("REVOKE_READ_PROOF", json.dumps(report, sort_keys=True))
                assert all(value == 0 for value in observed.values()), report
            finally:
                resume.set()
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
    finally:
        probe.close()


@pytest.mark.parametrize("cancel", [False, True])
async def test_admitted_read_precedes_commit_and_cancellation_releases_lock(
    pg_auth, monkeypatch, record_property, cancel
):
    auth, factory, _, user, _ = pg_auth
    query, _, _, _, app = await fixture(auth, factory, user)
    admitted, resume, at_gate, allow_gate = (asyncio.Event() for _ in range(4))
    waiter_ready, committed = asyncio.Event(), asyncio.Event()
    original_get, original_send = OperationalPeakRunRepository.get, GuardedResponse.__call__
    pause = False
    reader_pid = waiter_pid = None
    timeline = []

    async def held_read(repository, run_id):
        nonlocal reader_pid
        if pause:
            reader_pid, tx = (
                await repository.session.execute(text("SELECT pg_backend_pid(), txid_current()"))
            ).one()
            timeline.append({"event": "reader_admitted", "pid": reader_pid, "transaction": tx})
            admitted.set()
            await resume.wait()
        return await original_get(repository, run_id)

    async def held_gate(response, scope, receive, send):
        if pause:
            at_gate.set()
            await allow_gate.wait()
        await original_send(response, scope, receive, send)

    monkeypatch.setattr(OperationalPeakRunRepository, "get", held_read)
    monkeypatch.setattr(GuardedResponse, "__call__", held_gate)
    probe = WorkProbe(factory.kw["bind"], monkeypatch)

    async def revoker():
        nonlocal waiter_pid
        async with factory() as db, db.begin():
            waiter_pid, tx = (
                await db.execute(text("SELECT pg_backend_pid(), txid_current()"))
            ).one()
            timeline.append(
                {"event": "writer_attempting_lock", "pid": waiter_pid, "transaction": tx}
            )
            waiter_ready.set()
            account = await db.scalar(
                select(AuthAccount)
                .where(AuthAccount.account_id == user.account_id)
                .with_for_update()
            )
            account.status = "DISABLED"
            account.auth_revision += 1
            await auth.revoke_all(db, account, "SYNTHETIC_ORDERED_DISABLE")
        timeline.append({"event": "disable_commit_completed"})
        probe.phase = "after_commit"
        committed.set()

    async def blocked_by_reader():
        async with factory() as db:
            while True:
                blockers = await db.scalar(
                    text("SELECT pg_blocking_pids(:pid)"), {"pid": waiter_pid}
                )
                if reader_pid in blockers:
                    timeline.append({"event": "actual_postgres_lock_wait", "blockers": blockers})
                    return

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://synthetic.test"
        ) as client:
            assert (await login(client)).status_code == 200
            positive = await client.get(
                "/api/v1/forecast-intelligence/curve", params=query.model_dump(mode="json")
            )
            assert positive.status_code == 200
            assert probe.counts[("positive_control", "business_sql")] == 2
            pause, probe.phase = True, "before_commit"
            pending = asyncio.create_task(
                client.get(
                    "/api/v1/forecast-intelligence/curve", params=query.model_dump(mode="json")
                )
            )
            writer = None
            try:
                await asyncio.wait_for(admitted.wait(), 5)
                writer = asyncio.create_task(revoker())
                await asyncio.wait_for(waiter_ready.wait(), 5)
                assert waiter_pid != reader_pid
                await asyncio.wait_for(blocked_by_reader(), 5)
                assert not committed.is_set()
                if cancel:
                    pending.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await pending
                else:
                    resume.set()
                    await asyncio.wait_for(at_gate.wait(), 5)
                await asyncio.wait_for(committed.wait(), 5)
                if not cancel:
                    allow_gate.set()
                    response = await asyncio.wait_for(pending, 5)
                    assert response.status_code == 401
                    assert response.json()["data"] is None
                    assert query.expected_source_result_hash not in response.text
                assert probe.counts[("before_commit", "business_sql")] == (0 if cancel else 2)
                assert probe.counts[("after_commit", "business_sql")] == 0
                record_property(
                    "READ_LOCK_PROOF",
                    json.dumps(
                        {
                            "cancelled": cancel,
                            "timeline": timeline,
                            "work": probe.events,
                            "before_commit_reads": probe.counts[("before_commit", "business_sql")],
                            "after_commit_reads": probe.counts[("after_commit", "business_sql")],
                        },
                        sort_keys=True,
                    ),
                )
            finally:
                resume.set()
                allow_gate.set()
                for task in (pending, writer):
                    if task is not None and not task.done():
                        task.cancel()
                await asyncio.gather(
                    *(t for t in (pending, writer) if t is not None), return_exceptions=True
                )
    finally:
        probe.close()


async def test_read_lock_wait_is_bounded_and_recovers(pg_auth, monkeypatch):
    auth, factory, _, user, _ = pg_auth
    query, _, _, _, app = await fixture(auth, factory, user)
    probe = WorkProbe(factory.kw["bind"], monkeypatch)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://synthetic.test"
        ) as client:
            assert (await login(client)).status_code == 200
            probe.phase = "lock_contention"
            async with factory() as writer, writer.begin():
                await writer.scalar(
                    select(AuthAccount)
                    .where(AuthAccount.account_id == user.account_id)
                    .with_for_update()
                )
                result = await asyncio.wait_for(
                    client.get(
                        "/api/v1/forecast-intelligence/curve", params=query.model_dump(mode="json")
                    ),
                    5,
                )
                assert result.status_code == 503
                assert result.json()["data"] is None
            assert probe.counts[("lock_contention", "business_sql")] == 0
            probe.phase = "recovered"
            result = await client.get(
                "/api/v1/forecast-intelligence/curve", params=query.model_dump(mode="json")
            )
            assert result.status_code == 200
            assert probe.counts[("recovered", "business_sql")] == 2
    finally:
        probe.close()


@pytest.mark.parametrize("operation", ["simulate", "compare"])
@pytest.mark.parametrize("revocation", REVOCATIONS)
async def test_revocation_between_saved_curve_and_engine_execution(
    pg_auth, monkeypatch, record_property, operation, revocation
):
    auth, factory, _, user, _ = pg_auth
    query, grant, _, curve, app = await fixture(auth, factory, user)
    read, resume = asyncio.Event(), asyncio.Event()
    original = ForecastIntelligenceReadService.curve

    async def after_curve(reader, selected):
        value = await original(reader, selected)
        read.set()
        await resume.wait()
        return value

    monkeypatch.setattr(ForecastIntelligenceReadService, "curve", after_curve)
    probe = WorkProbe(factory.kw["bind"], monkeypatch)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://synthetic.test"
        ) as client:
            assert (await login(client)).status_code == 200
            token = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
            payload = request_payload(curve)
            probe.phase = "before_commit"
            pending = asyncio.create_task(
                client.post(
                    "/api/v1/decision-support/"
                    + (
                        "simulate-capacity"
                        if operation == "simulate"
                        else "compare-capacity-scenarios"
                    ),
                    json=payload if operation == "simulate" else comparison_payload(payload),
                    headers={"Origin": "https://synthetic.test", "X-CSRF-Token": token},
                )
            )
            try:
                await asyncio.wait_for(read.wait(), 5)
                assert probe.counts[("before_commit", "business_sql")] == 2
                await revoke(auth, factory, user, grant.grant_id, revocation, probe.events)
                probe.phase = "after_commit"
                resume.set()
                result = await asyncio.wait_for(pending, 10)
                assert result.status_code in {401, 403}, result.text
                assert result.json()["data"] is None
                assert query.expected_source_result_hash not in result.text
                assert not any(
                    probe.counts[("after_commit", k)]
                    for k in ("business_sql", "quality_file", "simulation", "comparison")
                )
                assert not any(
                    probe.counts[("before_commit", k)] for k in ("simulation", "comparison")
                )
                record_property(
                    "ENGINE_ADMISSION_PROOF",
                    json.dumps(
                        {
                            "operation": operation,
                            "revocation": revocation,
                            "before_commit_business_reads": probe.counts[
                                ("before_commit", "business_sql")
                            ],
                            "post_commit_simulation_count": probe.counts[
                                ("after_commit", "simulation")
                            ],
                            "post_commit_comparison_count": probe.counts[
                                ("after_commit", "comparison")
                            ],
                            "timeline": probe.events,
                        },
                        sort_keys=True,
                    ),
                )
            finally:
                resume.set()
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
    finally:
        probe.close()
