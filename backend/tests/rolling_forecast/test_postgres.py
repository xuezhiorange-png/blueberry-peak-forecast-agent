"""Real PostgreSQL, real I7 snapshots, real ASGI auth and frozen Ridge inference."""

import asyncio
import json
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError

from backend.app.api.rolling_forecast import ReleasedResponse
from backend.app.local_auth.models import AuthAccount
from backend.app.main import create_app
from backend.app.rolling_forecast import observations
from backend.app.rolling_forecast.models import RollingRun
from backend.tests.local_auth.conftest import login
from backend.tests.rolling_forecast.seed import issue_body, seed

pytestmark = [pytest.mark.postgres, pytest.mark.integration]


async def post(client, body):
    csrf = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
    return await client.post(
        "/api/v1/rolling-forecast-runs",
        json=body,
        headers={"Origin": "https://synthetic.test", "X-CSRF-Token": csrf},
    )


@pytest.mark.asyncio
async def test_real_issue_reload_compare_immutable_and_idempotent(
    pg_auth, tmp_path, record_property
):
    auth, factory, _, account, _ = pg_auth
    _, path = await seed(factory, account.principal_id, tmp_path)
    auth.settings.rolling_forecast_catalog_path = str(path)
    app = create_app(auth.settings)
    app.state.local_auth = auth
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        assert (await login(client)).status_code == 200
        a = await post(client, issue_body())
        assert a.status_code == 200, a.text
        saved = a.json()["data"]
        assert saved["status"] == "COMPUTED" and saved["issued_at"] is None
        assert saved["result"]["feature_snapshot"]["values"]["past_7d_harvest_kg"] == "224.000000"
        assert (await post(client, issue_body())).json()["data"] == saved
        b = await post(client, {**issue_body(1), "rerun_of_run_id": saved["run_id"]})
        assert b.status_code == 200, b.text
        newer = b.json()["data"]
        assert newer["run_id"] != saved["run_id"]
        assert newer["rerun_of_run_id"] == saved["run_id"]
        detail = await client.get(f"/api/v1/rolling-forecast-runs/{saved['run_id']}")
        assert detail.json()["data"] == saved
        daily = await client.get(f"/api/v1/rolling-forecast-runs/{saved['run_id']}/daily")
        assert daily.json()["data"]["result"] == saved["result"]
        history = await client.get("/api/v1/rolling-forecast-runs", params={"limit": 1})
        assert len(history.json()["data"]["items"]) == 1
        comparison = await client.get(
            "/api/v1/rolling-forecast-runs/compare",
            params={"left_run_id": saved["run_id"], "right_run_id": newer["run_id"]},
        )
        assert comparison.status_code == 200, comparison.text
        models = comparison.json()["data"]["models"]
        assert len(models["M1"]["common_target_daily_delta_kg"]) == 14
        assert models["M1"]["windows"]["H7"]["meaning"].startswith("DIFFERENT_ORIGIN")
        assert (await client.get("/api/v1/trial")).status_code == 403
        token = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
        review = await client.post(
            f"/api/v1/rolling-forecast-runs/{saved['run_id']}/review",
            json={"label_snapshot_reference": "SYNTHETIC-SNAPSHOT-2"},
            headers={"Origin": "https://synthetic.test", "X-CSRF-Token": token},
        )
        assert review.status_code == 200, review.text
        assessment = review.json()["data"]
        assert len(assessment["actual_daily"]) == 15
        assert assessment["actual_daily"][0]["business_date"] == "2026-11-06"
        assert assessment["actual_daily"][-1]["business_date"] == "2026-11-20"
        for window, n in (("H7_PREFIX", 7), ("H15_LOCAL", 15)):
            metrics = assessment["groups"][window]["metrics"]
            assert len(metrics) == 10
            assert metrics["SEASON_TOTAL_WAPE"]["common_count"] == 0
            expected = sum(Decimal(r["quantity_kg"]) for r in assessment["actual_daily"][:n])
            assert Decimal(metrics["DAILY_WAPE"]["baseline"]["denominator"]) == expected
            for name in ("M0", "M1"):
                bias = assessment["groups"][window]["BIAS"][name]
                signed = sum(
                    (
                        Decimal(p["kg"]) - Decimal(a["quantity_kg"])
                        for p, a in zip(
                            saved["result"]["models"][name]["daily_forecast_kg"][:n],
                            assessment["actual_daily"][:n],
                            strict=True,
                        )
                    ),
                    Decimal(0),
                )
                assert Decimal(bias["numerator_kg"]) == signed
                # The reported mean keeps Decimal precision, not binary float.
                from decimal import localcontext

                with localcontext() as ctx:
                    ctx.prec = 50
                    assert Decimal(bias["value_kg"]) == signed / n
            assert sum(assessment["groups"][window]["base_outcomes"]["counts"].values()) == 1
        sample = {
            "data_class": "SYNTHETIC_TEST_FIXTURE",
            "current_season_actuals_read": False,
            "run_1": saved,
            "run_2": newer,
            "comparison": comparison.json()["data"],
            "independent_review": assessment,
        }
        artifact = tmp_path / "SYNTHETIC-business-example.json"
        artifact.write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n")
        artifact.chmod(0o600)
        record_property("SYNTHETIC_BUSINESS_EXAMPLE", str(artifact))
    for table in ("rolling_forecast_run", "rolling_forecast_daily"):
        for verb in ("DELETE FROM", "UPDATE"):
            async with factory() as db:
                with pytest.raises(DBAPIError, match="immutable"):
                    await db.execute(
                        text(f"{verb} {table}" + (" SET id=id" if verb == "UPDATE" else ""))
                    )
                await db.rollback()
    async with factory() as db:
        assert len((await db.scalars(select(RollingRun))).all()) == 2


@pytest.mark.asyncio
async def test_unauthorized_reads_zero_and_account_revocation(pg_auth, tmp_path):
    auth, factory, _, account, _ = pg_auth
    _, path = await seed(factory, account.principal_id, tmp_path)
    auth.settings.rolling_forecast_catalog_path = str(path)
    app = create_app(auth.settings)
    app.state.local_auth = auth
    reads = []

    def observe(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and any(
            t in statement
            for t in (
                "actual_harvest_label_snapshot_winner",
                "rolling_forecast_run",
                "rolling_forecast_daily",
            )
        ):
            reads.append(statement)

    engine = factory.kw["bind"]
    event.listen(engine.sync_engine, "before_cursor_execute", observe)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://synthetic.test"
        ) as client:
            assert (await client.get("/api/v1/rolling-forecast-runs")).status_code == 401
            assert (await login(client)).status_code == 200
            invalid = {**issue_body(), "base_id": "KNOWN_BUT_UNAUTHORIZED_BASE"}
            assert (await post(client, invalid)).status_code == 403
            assert not reads
            # Positive control: this same SQL observer sees a legitimate read.
            assert (await post(client, issue_body())).status_code == 200
            assert reads
            reads.clear()
            token = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
            async with factory() as db, db.begin():
                subject = await db.get(AuthAccount, account.account_id, with_for_update=True)
                subject.status = "DISABLED"
                subject.auth_revision += 1
                await auth.revoke_all(db, subject, "SYNTHETIC_S7_DISABLE")
            denied = await client.post(
                "/api/v1/rolling-forecast-runs",
                json=issue_body(),
                headers={"Origin": "https://synthetic.test", "X-CSRF-Token": token},
            )
            assert denied.status_code == 401
            assert not reads
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", observe)


@pytest.mark.parametrize("changed", ["base_id", "season", "organization_id"])
@pytest.mark.asyncio
async def test_reused_context_never_reauthorizes_previous_resource(pg_auth, tmp_path, changed):
    auth, factory, _, account, _ = pg_auth
    _, path = await seed(factory, account.principal_id, tmp_path)
    auth.settings.rolling_forecast_catalog_path = str(path)
    app = create_app(auth.settings)
    app.state.local_auth = auth
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        assert (await login(client)).status_code == 200
        first = await post(client, issue_body())
        assert first.status_code == 200
        old = first.json()["data"]
        value = json.loads(path.read_bytes())
        context = value["contexts"][0]
        if changed == "base_id":
            context["area"]["base_id"] = "SYNTHETIC_OTHER_BASE"
        elif changed == "season":
            context["area"]["season"] = context["calendar"]["season"] = "2027-2028"
        else:
            old_org = context["organization_id"]
            context["organization_id"] = "SYNTHETIC_OTHER_ORG"
            auth.settings.local_auth_organization_ids_json = json.dumps(
                [old_org, context["organization_id"]]
            )
        path.write_text(json.dumps(value))
        for suffix in ("", "/daily"):
            denied = await client.get(f"/api/v1/rolling-forecast-runs/{old['run_id']}{suffix}")
            assert denied.status_code == 404, (changed, denied.text)
        history = await client.get("/api/v1/rolling-forecast-runs")
        assert history.status_code == 200
        assert history.json()["data"]["items"] == []
        comparison = await client.get(
            "/api/v1/rolling-forecast-runs/compare",
            params={"left_run_id": old["run_id"], "right_run_id": old["run_id"]},
        )
        assert comparison.status_code == 404
        body = issue_body()
        body.update(
            base_id=context["area"]["base_id"],
            target_season=context["area"]["season"],
            rerun_of_run_id=old["run_id"],
        )
        reads = []

        def observe(conn, cursor, statement, parameters, context, executemany):
            if "actual_harvest_label_snapshot_winner" in statement:
                reads.append(statement)

        engine = factory.kw["bind"]
        event.listen(engine.sync_engine, "before_cursor_execute", observe)
        try:
            assert (await post(client, body)).status_code == 404
            assert reads == []
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", observe)


@pytest.mark.asyncio
async def test_concurrent_idempotence_cancellation_rollback_and_recovery(
    pg_auth, tmp_path, monkeypatch
):
    auth, factory, _, account, _ = pg_auth
    _, path = await seed(factory, account.principal_id, tmp_path)
    auth.settings.rolling_forecast_catalog_path = str(path)
    app = create_app(auth.settings)
    app.state.local_auth = auth
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        assert (await login(client)).status_code == 200
        token = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
        headers = {"Origin": "https://synthetic.test", "X-CSRF-Token": token}
        a, b = await asyncio.gather(
            *[
                client.post("/api/v1/rolling-forecast-runs", json=issue_body(), headers=headers)
                for _ in range(2)
            ]
        )
        assert a.status_code == b.status_code == 200, (a.text, b.text)
        assert a.json()["data"]["run_id"] == b.json()["data"]["run_id"]
        arrived = asyncio.Event()
        original = observations.load

        async def held(*args, **kwargs):
            arrived.set()
            await asyncio.Event().wait()
            return await original(*args, **kwargs)

        monkeypatch.setattr(observations, "load", held)
        pending = asyncio.create_task(
            client.post("/api/v1/rolling-forecast-runs", json=issue_body(1), headers=headers)
        )
        await asyncio.wait_for(arrived.wait(), 3)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(RollingRun)) == 1
        monkeypatch.setattr(observations, "load", original)
        recovered = await client.post(
            "/api/v1/rolling-forecast-runs", json=issue_body(1), headers=headers
        )
        assert recovered.status_code == 200, recovered.text
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(RollingRun)) == 2


@pytest.mark.asyncio
async def test_partial_history_policy_reload_and_pre_response_revocation(
    pg_auth, tmp_path, monkeypatch
):
    auth, factory, _, account, _ = pg_auth
    _, path = await seed(factory, account.principal_id, tmp_path)
    auth.settings.rolling_forecast_catalog_path = str(path)
    app = create_app(auth.settings)
    app.state.local_auth = auth
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        assert (await login(client)).status_code == 200
        value = json.loads(path.read_text())
        value["contexts"][0]["snapshots"][0]["complete_dates"].pop(0)
        path.write_text(json.dumps(value))
        partial = await post(client, issue_body())
        assert partial.status_code == 200, partial.text
        data = partial.json()["data"]
        assert data["status"] == "PARTIAL"
        assert data["result"]["models"]["M0"]["status"] == "COMPUTED"
        assert data["result"]["models"]["M1"]["status"] == "NOT_COMPUTABLE"
        assert data["result"]["models"]["M1"]["daily_forecast_kg"] == []
        original = ReleasedResponse.__call__

        async def revoked(response, scope, receive, send):
            async with factory() as db, db.begin():
                subject = await db.get(AuthAccount, account.account_id, with_for_update=True)
                subject.grant_revision += 1
                await auth.revoke_all(db, subject, "SYNTHETIC_BEFORE_SEND")
            await original(response, scope, receive, send)

        monkeypatch.setattr(ReleasedResponse, "__call__", revoked)
        denied = await post(client, issue_body(1))
        assert denied.status_code == 401 and denied.json()["data"] is None
        # The second run was computed BEFORE revocation committed, not after;
        # the final fresh-session gate withheld every result byte.
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(RollingRun)) == 2
