"""Real transactions and HTTP; wrappers only observe/barrier, never forge results."""

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select, text

from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.local_auth.models import AuthAccount
from backend.tests.local_auth.conftest import login
from backend.tests.safe_pilot.test_restore_and_ingress import application, seed

pytestmark = pytest.mark.postgres


async def test_lead_1_disable_after_authentication_before_grant_and_read(
    pg_auth, monkeypatch, record_property, tmp_path
):
    auth, factory, _, user, _ = pg_auth
    selected, _ = await seed(factory, user)
    app = application(auth)
    authenticated, resume = asyncio.Event(), asyncio.Event()
    pause = False
    counts = {"business_reads": 0}
    observations = []
    original_authenticate, original_curve = auth.authenticate, ForecastIntelligenceReadService.curve

    async def barrier_authenticate(request, **kwargs):
        principal = await original_authenticate(request, **kwargs)
        if pause and request.url.path.endswith("/curve"):
            observations.append({"event": "authenticated_transaction_complete"})
            authenticated.set()
            await resume.wait()
        return principal

    async def observe_curve(self, query):
        pid, transaction, isolation = (
            await self.session.execute(
                text(
                    "SELECT pg_backend_pid(), txid_current(), "
                    "current_setting('transaction_isolation')"
                )
            )
        ).one()
        observations.append(
            {
                "event": "canonical_read_entry",
                "pid": pid,
                "transaction": transaction,
                "isolation": isolation,
            }
        )
        return await original_curve(self, query)

    def sql_observer(conn, cursor, statement, parameters, context, many):
        del conn, cursor, parameters, context, many
        sql = statement.lower().lstrip()
        if sql.startswith("select") and (
            "operational_peak_forecast" in sql or "hierarchical_forecast" in sql
        ):
            counts["business_reads"] += 1

    monkeypatch.setattr(auth, "authenticate", barrier_authenticate)
    monkeypatch.setattr(ForecastIntelligenceReadService, "curve", observe_curve)
    engine = factory.kw["bind"]
    event.listen(engine.sync_engine, "before_cursor_execute", sql_observer)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://synthetic.test"
        ) as client:
            assert (await login(client)).status_code == 200
            positive = await client.get(
                "/api/v1/forecast-intelligence/curve", params=selected.model_dump(mode="json")
            )
            assert positive.status_code == 200
            assert positive.json()["source_result_hash"] == selected.expected_source_result_hash
            assert counts["business_reads"] > 0, "Broken SQL observer cannot prove zero work"
            positive_count = counts["business_reads"]
            counts["business_reads"] = 0
            observations.clear()
            pause = True
            pending = asyncio.create_task(
                client.get(
                    "/api/v1/forecast-intelligence/curve", params=selected.model_dump(mode="json")
                )
            )
            try:
                await asyncio.wait_for(authenticated.wait(), 5)
                # Hold this physical connection until the request completes, so
                # the canonical reader cannot reuse its PostgreSQL backend PID.
                async with engine.connect() as connection:
                    async with factory(bind=connection) as db, db.begin():
                        pid, transaction, isolation = (
                            await db.execute(
                                text(
                                    "SELECT pg_backend_pid(), txid_current(), "
                                    "current_setting('transaction_isolation')"
                                )
                            )
                        ).one()
                        account = await db.scalar(
                            select(AuthAccount)
                            .where(AuthAccount.account_id == user.account_id)
                            .with_for_update()
                        )
                        account.status = "DISABLED"
                        account.auth_revision += 1
                        await auth.revoke_all(db, account, "SYNTHETIC_OPTION_B_DISABLE")
                        observations.append(
                            {
                                "event": "account_exclusive_lock_and_revoke",
                                "pid": pid,
                                "transaction": transaction,
                                "isolation": isolation,
                            }
                        )
                    observations.append({"event": "revocation_commit_completed"})
                    resume.set()
                    response = await asyncio.wait_for(pending, 10)
                assert response.status_code in {401, 403}
                assert response.json()["data"] is None
                assert "daily_rows" not in response.text
                assert selected.expected_source_result_hash not in response.text
                assert (await client.get("/api/v1/auth/me")).status_code == 401
                readers = [o for o in observations if o["event"] == "canonical_read_entry"]
                assert all(r["pid"] != pid and r["transaction"] != transaction for r in readers)
                result = {
                    "SYNTHETIC": True,
                    "lead": "AUTHENTICATE_TO_READ_REVOCATION_WINDOW",
                    "positive_control_business_reads": positive_count,
                    "business_reads_after_disable_commit": counts["business_reads"],
                    "sensitive_response_sent": False,
                    "response_status": response.status_code,
                    "session_invalidated": True,
                    "observations": observations,
                    "expected_business_reads_after_disable_commit": 0,
                }
                record_property("OPTION_B_PG_LEAD_1", json.dumps(result, sort_keys=True))
                (tmp_path / "lead-1-observations.json").write_text(
                    json.dumps(result, sort_keys=True, indent=2) + "\n"
                )
                assert counts["business_reads"] == 0, (
                    "Disabled subject reached real canonical SQL before final send denial"
                )
            finally:
                resume.set()
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", sql_observer)
