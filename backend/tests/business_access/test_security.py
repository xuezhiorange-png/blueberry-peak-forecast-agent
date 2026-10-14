"""SYNTHETIC=true: real PostgreSQL, production ASGI, signed contexts and release gates."""

import re
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, event, select, text, update

from backend.app.business_access import tokens
from backend.app.business_access.response import DiscoveryResponse
from backend.app.forecast_intelligence.application import execute_hierarchical_run
from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.local_auth.models import AuthAccount, AuthResourceGrant, AuthSession
from backend.app.local_auth.sessions import now
from backend.app.models.operational_peak import (
    OperationalPeakForecastDaily,
    OperationalPeakForecastRun,
)
from backend.tests.business_access.test_discovery import PREFIX, app_for, grant
from backend.tests.forecast_intelligence.conftest import seed_sources
from backend.tests.forecast_intelligence.test_reconciliation import request as hierarchy_request
from backend.tests.forecast_intelligence.test_v0_17_s1_service_read_api import (
    hierarchy_query,
    query,
)
from backend.tests.local_auth.conftest import login

pytestmark = pytest.mark.postgres


async def corrupt_synthetic_record(db, statement):
    """Deliberate corruption ONLY inside a newly generated disposable test DB.

    The real immutable triggers remain enabled for all normal paths. Failure
    injection is necessary to exercise saved-record disappearance/hash drift.
    """
    database = await db.scalar(text("SELECT current_database()"))
    assert database.startswith("blueberry_test_auth_")
    tables = ("operational_peak_forecast_daily", "operational_peak_forecast_run")
    for table in tables:
        await db.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER USER"))
    try:
        await db.execute(statement)
    finally:
        for table in tables:
            await db.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER USER"))


async def seed(auth, factory, account, authority, count=2):
    ids = await seed_sources(factory, authority)
    grants = []
    for index in range(count):
        grants.append(
            await grant(
                factory, account, query(ids[index], entity_id=("A1", "A2", "B1", "B2")[index])
            )
        )
    app = app_for(auth)
    return ids, grants, app


async def selected(client):
    result = await client.get(PREFIX + "saved-runs")
    assert result.status_code == 200, result.text
    data = result.json()["data"]
    item = data["items"][0]
    return {
        "forecast_identity": item["forecast_identity"],
        "expected_source_result_hash": item["expected_source_result_hash"],
        "grant_revision": data["grant_revision"],
        "catalog_snapshot": data["catalog_snapshot"],
    }


async def submit(client, payload, **headers):
    csrf = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
    return await client.post(
        PREFIX + "selection",
        json=payload,
        headers={"Origin": "https://synthetic.test", "X-CSRF-Token": csrf, **headers},
    )


async def test_sql_pagination_filters_and_duplicate_grants(pg_auth, synthetic_authority):
    auth, factory, _, account, _ = pg_auth
    ids, _, app = await seed(auth, factory, account, synthetic_authority)
    await grant(factory, account, query(ids[0]))  # Duplicate grant must not duplicate a saved run.
    statements = []

    def observe(conn, cursor, statement, parameters, context, many):
        if "authorized_saved_runs" in statement:
            statements.append((statement, parameters))

    event.listen(factory.kw["bind"].sync_engine, "before_cursor_execute", observe)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://synthetic.test"
        ) as client:
            await login(client)
            first = (await client.get(PREFIX + "saved-runs", params={"page_size": 1})).json()[
                "data"
            ]
            assert first["items"][0]["forecast_identity"]["run_id"] == ids[1]
            cursor = first["next_cursor"]
            assert cursor and len(cursor.encode()) <= 2048
            second = await client.get(
                PREFIX + "saved-runs", params={"page_size": 1, "cursor": cursor}
            )
            assert second.status_code == 200, second.text
            assert [i["forecast_identity"]["run_id"] for i in second.json()["data"]["items"]] == [
                ids[0]
            ]
            assert second.json()["data"]["next_cursor"] is None
            empty = await client.get(PREFIX + "saved-runs", params={"entity_id": "B1"})
            assert empty.status_code == 200 and empty.json()["data"]["items"] == []
            for filters in (
                {"target_season": "2024-2025"},
                {"hierarchy_level": "REGION"},
                {"forecast_family": "OTHER"},
                {"origin_from": "2026-01-02"},
                {"origin_to": "2025-12-31"},
            ):
                response = await client.get(PREFIX + "saved-runs", params=filters)
                assert response.status_code == 200 and response.json()["data"]["items"] == []
            mismatch = await client.get(
                PREFIX + "saved-runs", params={"page_size": 1, "cursor": cursor, "entity_id": "A1"}
            )
            assert mismatch.status_code == 422
        assert statements
        for statement, parameters in statements:
            normalized = " ".join(statement.split())
            assert " WHERE " in normalized and " IN (" in normalized and "COUNT(" not in normalized
            # The only physical IDs requested are the two authorized IDs, never B1/B2.
            placeholders = re.search(r"operational_peak_forecast_run.id IN \(([^)]+)\)", normalized)
            assert placeholders is not None
            positions = [int(v) for v in re.findall(r"\$(\d+)", placeholders.group(1))]
            assert {parameters[p - 1] for p in positions} == set(ids[:2])
        paged = [sql for sql, _ in statements if " LIMIT " in sql]
        assert paged and all("ORDER BY" in sql for sql in paged)
        assert any("authorized_saved_runs.run_id <" in sql for sql in paged)
    finally:
        event.remove(factory.kw["bind"].sync_engine, "before_cursor_execute", observe)


@pytest.mark.parametrize("kind", ["BASE", "REGION", "COMPANY"])
async def test_independent_hierarchy_grants(pg_auth, synthetic_authority, kind):
    auth, factory, _, account, _ = pg_auth
    ids = await seed_sources(factory, synthetic_authority)
    async with factory() as db, db.begin():
        region = await execute_hierarchical_run(db, hierarchy_request(ids[:2], "REGION", "A"))
        company = await execute_hierarchical_run(db, hierarchy_request(ids))
    queries = {
        "BASE": query(ids[0]),
        "REGION": hierarchy_query(region),
        "COMPANY": hierarchy_query(company),
    }
    await grant(factory, account, queries[kind])
    async with AsyncClient(
        transport=ASGITransport(app=app_for(auth)), base_url="https://synthetic.test"
    ) as client:
        await login(client)
        response = await client.get(PREFIX + "scope")
        assert response.status_code == 200, response.text
        assert [e["hierarchy_level"] for e in response.json()["data"]["entities"]] == [kind]
        for level in queries:
            response = await client.get(PREFIX + "saved-runs", params={"hierarchy_level": level})
            assert response.status_code == 200
            assert len(response.json()["data"]["items"]) == int(level == kind)
        payload = await selected(client)
        verified = await submit(client, payload)
        assert verified.status_code == 200, verified.text
        async with factory() as db:
            canonical = await ForecastIntelligenceReadService(db).curve(queries[kind])
        assert verified.json()["data"]["projection_hash"] == canonical.projection_hash


@pytest.mark.parametrize(
    "fault", ["tamper", "expiry", "foreign_session", "foreign_user", "directory", "record_hash"]
)
async def test_cursor_fail_closed(pg_auth, synthetic_authority, monkeypatch, fault):
    auth, factory, _, account, _ = pg_auth
    ids, _, app = await seed(auth, factory, account, synthetic_authority)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        await login(client)
        cursor = (await client.get(PREFIX + "saved-runs", params={"page_size": 1})).json()["data"][
            "next_cursor"
        ]
        expected = 422
        if fault == "tamper":
            cursor = ("A" if cursor[0] != "A" else "B") + cursor[1:]
        elif fault == "expiry":
            future = now() + timedelta(seconds=901)
            monkeypatch.setattr(tokens, "now", lambda: future)
        elif fault == "foreign_session":
            client.cookies.clear()
            await login(client)
            expected = 403
        elif fault == "foreign_user":
            async with factory() as db, db.begin():
                old = await db.get(AuthAccount, account.account_id)
                old.username_normalized = "synthetic-original"
                other = AuthAccount(
                    username_normalized="synthetic-user",
                    password_hash=old.password_hash,
                    role="BUSINESS_USER",
                    status="ACTIVE",
                    must_change_password=False,
                    created_at=now(),
                    updated_at=now(),
                )
                db.add(other)
            client.cookies.clear()
            await login(client)
            expected = 403
        elif fault == "directory":
            auth.settings.local_auth_organization_ids_json = '["SYNTHETIC_ORG", "SYNTHETIC_OTHER"]'
            expected = 409
        else:
            async with factory() as db, db.begin():
                await corrupt_synthetic_record(
                    db,
                    update(OperationalPeakForecastRun)
                    .where(OperationalPeakForecastRun.id == ids[0])
                    .values(result_hash="f" * 64),
                )
            expected = 409
        response = await client.get(
            PREFIX + "saved-runs", params={"page_size": 1, "cursor": cursor}
        )
        assert response.status_code == expected, response.text
        assert response.json()["data"] is None and response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "fault",
    [
        "ungranted",
        "hash",
        "missing",
        "identity",
        "handoff_purpose",
        "handoff_expired",
        "handoff_session",
        "revoked",
    ],
)
async def test_selection_and_handoff_revalidated(pg_auth, synthetic_authority, monkeypatch, fault):
    auth, factory, _, account, _ = pg_auth
    ids, grants, app = await seed(auth, factory, account, synthetic_authority)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        await login(client)
        payload = await selected(client)
        response = await submit(client, payload)
        assert response.status_code == 200, response.text
        payload["handoff_token"] = response.json()["data"]["handoff_token"]
        consumed = await submit(client, payload)
        assert consumed.status_code == 200, consumed.text
        expected = 403
        if fault == "ungranted":
            payload["forecast_identity"].update(run_id=ids[2], entity_id="B1")
        elif fault == "hash":
            payload["expected_source_result_hash"] = "f" * 64
        elif fault == "missing":
            async with factory() as db, db.begin():
                await corrupt_synthetic_record(
                    db,
                    delete(OperationalPeakForecastDaily).where(
                        OperationalPeakForecastDaily.run_id == ids[1]
                    ),
                )
                await corrupt_synthetic_record(
                    db,
                    delete(OperationalPeakForecastRun).where(
                        OperationalPeakForecastRun.id == ids[1]
                    ),
                )
            expected = 404
        elif fault == "identity":
            async with factory() as db, db.begin():
                await corrupt_synthetic_record(
                    db,
                    update(OperationalPeakForecastRun)
                    .where(OperationalPeakForecastRun.id == ids[1])
                    .values(base_id="SYNTHETIC_CHANGED"),
                )
            expected = 409
        elif fault == "handoff_purpose":
            payload["handoff_token"] = (
                await client.get(PREFIX + "saved-runs", params={"page_size": 1})
            ).json()["data"]["next_cursor"]
            expected = 422
        elif fault == "handoff_expired":
            future = now() + timedelta(seconds=301)
            monkeypatch.setattr(tokens, "now", lambda: future)
            expected = 422
        elif fault == "handoff_session":
            client.cookies.clear()
            await login(client)
        else:
            async with factory() as db, db.begin():
                await db.execute(
                    update(AuthResourceGrant)
                    .where(AuthResourceGrant.grant_id == grants[1].grant_id)
                    .values(revoked_at=now())
                )
        rejected = await submit(client, payload)
        assert rejected.status_code == expected, rejected.text
        assert rejected.json()["data"] is None


@pytest.mark.parametrize("operation", ["scope", "saved-runs", "selection"])
@pytest.mark.parametrize(
    "revocation", ["account", "session", "grant", "grant_expiry", "source_hash"]
)
async def test_actual_asgi_release_rechecks(
    pg_auth, synthetic_authority, monkeypatch, operation, revocation
):
    auth, factory, _, account, _ = pg_auth
    ids, grants, app = await seed(auth, factory, account, synthetic_authority, count=1)
    original = DiscoveryResponse.__call__
    reached = []

    async def interleave(response, scope, receive, send):
        reached.append(True)
        async with factory() as db, db.begin():
            await db.scalar(
                select(AuthAccount)
                .where(AuthAccount.account_id == account.account_id)
                .with_for_update()
            )
            if revocation == "account":
                await db.execute(
                    update(AuthAccount)
                    .where(AuthAccount.account_id == account.account_id)
                    .values(status="DISABLED", auth_revision=2)
                )
            elif revocation == "session":
                await db.execute(
                    update(AuthSession)
                    .where(AuthSession.account_id == account.account_id)
                    .values(revoked_at=now())
                )
            elif revocation == "grant":
                await db.execute(
                    update(AuthResourceGrant)
                    .where(AuthResourceGrant.grant_id == grants[0].grant_id)
                    .values(revoked_at=now())
                )
            elif revocation == "grant_expiry":
                await db.execute(
                    update(AuthResourceGrant)
                    .where(AuthResourceGrant.grant_id == grants[0].grant_id)
                    .values(valid_until=now() - timedelta(seconds=1))
                )
            else:
                await corrupt_synthetic_record(
                    db,
                    update(OperationalPeakForecastRun)
                    .where(OperationalPeakForecastRun.id == ids[0])
                    .values(result_hash="f" * 64),
                )
        await original(response, scope, receive, send)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        await login(client)
        payload = await selected(client)
        monkeypatch.setattr(DiscoveryResponse, "__call__", interleave)
        result = (
            await submit(client, payload)
            if operation == "selection"
            else await client.get(PREFIX + operation)
        )
        assert reached == [True]
        assert result.status_code in {401, 403, 409}, result.text
        assert result.json()["data"] is None
        assert "handoff_token" not in result.text and "entity_name" not in result.text


@pytest.mark.parametrize(
    "parameters",
    [
        {"page_size": 0},
        {"page_size": 101},
        {"cursor": "x" * 2049},
        {"origin_from": "bad"},
        {"origin_from": "2026-02-01", "origin_to": "2026-01-01"},
        {"principal_id": "spoof"},
    ],
)
async def test_invalid_filters(pg_auth, parameters):
    auth, _, _, _, _ = pg_auth
    async with AsyncClient(
        transport=ASGITransport(app=app_for(auth)), base_url="https://synthetic.test"
    ) as client:
        await login(client)
        result = await client.get(PREFIX + "saved-runs", params=parameters)
        assert result.status_code == 422 and result.json()["data"] is None


async def test_auth_csrf_signing_and_legacy_boundaries(pg_auth, synthetic_authority):
    auth, factory, _, account, _ = pg_auth
    _, _, app = await seed(auth, factory, account, synthetic_authority)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        assert (await client.get(PREFIX + "scope")).status_code == 401
        await login(client)
        payload = await selected(client)
        assert (
            await client.post(
                PREFIX + "selection", json=payload, headers={"Origin": "https://synthetic.test"}
            )
        ).status_code == 403
        assert (await submit(client, payload, Origin="https://evil.test")).status_code == 403
        assert (
            await client.get(PREFIX + "scope", headers={"X-Principal-ID": account.principal_id})
        ).status_code == 403
        for path in ("/api/v1/trial/forecast-runs", "/api/v1/blueberry/v1/mcp", PREFIX + "latest"):
            assert (await client.get(path)).status_code == 403
        auth.settings.business_access_signing_key = SecretStr("")
        response = await client.get(PREFIX + "saved-runs")
        assert response.status_code == 503 and response.json()["data"] is None
