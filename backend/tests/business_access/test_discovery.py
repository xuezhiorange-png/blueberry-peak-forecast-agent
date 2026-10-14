"""Real HTTP and canonical PostgreSQL saved-run discovery acceptance."""

from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import event

from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.local_auth.models import AuthResourceGrant
from backend.app.local_auth.sessions import now
from backend.app.main import create_app
from backend.tests.forecast_intelligence.conftest import seed_sources
from backend.tests.forecast_intelligence.test_v0_17_s1_service_read_api import query
from backend.tests.local_auth.conftest import login

pytestmark = pytest.mark.postgres
PREFIX = "/api/v1/business-access/"


async def grant(factory, account, selection):
    async with factory() as db:
        source = await ForecastIntelligenceReadService(db).curve(selection)
    async with factory() as db, db.begin():
        row = AuthResourceGrant(
            principal_id=account.principal_id,
            resource_kind="FORECAST",
            capability="may_read_forecast",
            organization_id="SYNTHETIC_ORG",
            approved_by_principal=account.principal_id,
            approval_reference="SYNTHETIC",
            reason="SYNTHETIC discovery acceptance",
            grant_revision=1,
            forecast_binding={
                "identity": selection.model_dump(
                    mode="json", exclude={"expected_source_result_hash"}
                ),
                "expected_source_result_hash": source.source_result_hash,
                "source_authority_version": "SYNTHETIC_R1",
            },
            quality_binding=None,
            valid_from=now() - timedelta(seconds=5),
            valid_until=now() + timedelta(hours=1),
            created_at=now(),
        )
        db.add(row)
        await db.flush()
    return row


def app_for(auth):
    auth.settings.business_access_signing_key = SecretStr(
        "SYNTHETIC_SIGNING_KEY_NOT_PRODUCTION_" * 2
    )
    app = create_app(auth.settings)
    app.state.local_auth = auth
    return app


async def test_authorized_listing_and_selection_without_business_dml(pg_auth, synthetic_authority):
    auth, factory, _, account, _ = pg_auth
    ids = await seed_sources(factory, synthetic_authority)
    selected = query(ids[0])
    await grant(factory, account, selected)
    statements = []

    def observe(conn, cursor, statement, parameters, context, many):
        del conn, cursor, parameters, context, many
        statements.append(statement)

    event.listen(factory.kw["bind"].sync_engine, "before_cursor_execute", observe)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app_for(auth)), base_url="https://synthetic.test"
        ) as client:
            assert (await login(client)).status_code == 200
            scope = await client.get(PREFIX + "scope")
            assert scope.status_code == 200, scope.text
            assert scope.headers["cache-control"] == "no-store"
            assert [v["entity_id"] for v in scope.json()["data"]["entities"]] == [
                selected.entity_id
            ]
            listing = await client.get(PREFIX + "saved-runs")
            assert listing.status_code == 200, listing.text
            data = listing.json()["data"]
            assert len(data["items"]) == 1 and data["next_cursor"] is None
            item = data["items"][0]
            assert item["forecast_identity"] == selected.model_dump(
                mode="json", exclude={"expected_source_result_hash"}
            )
            assert "daily_rows" not in listing.text and "forecast_7d_total" not in listing.text
            csrf = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
            payload = {
                "forecast_identity": item["forecast_identity"],
                "expected_source_result_hash": item["expected_source_result_hash"],
                "grant_revision": data["grant_revision"],
                "catalog_snapshot": data["catalog_snapshot"],
            }
            response = await client.post(
                PREFIX + "selection",
                json=payload,
                headers={"Origin": "https://synthetic.test", "X-CSRF-Token": csrf},
            )
            assert response.status_code == 200, response.text
            result = response.json()["data"]
            assert (
                result["forecast_identity"] == item["forecast_identity"]
                and result["expires_in"] == 300
            )
            assert result["expected_source_result_hash"] == item["expected_source_result_hash"]
            assert result["handoff_token"] and "daily_rows" not in response.text
        business = [
            s.lower()
            for s in statements
            if "operational_peak_forecast" in s.lower() or "hierarchical_forecast" in s.lower()
        ]
        assert not any(s.lstrip().startswith(("insert", "update", "delete")) for s in business)
        assert any(" limit " in s and "order by" in s and "where" in s for s in business)
    finally:
        event.remove(factory.kw["bind"].sync_engine, "before_cursor_execute", observe)


@pytest.mark.parametrize("role", ["BUSINESS_USER", "ADMIN"])
async def test_no_grant_denied_before_forecast_read(pg_auth, role):
    auth, factory, _, account, _ = pg_auth
    async with factory() as db, db.begin():
        row = await db.get(type(account), account.account_id)
        row.role = role
    statements = []

    def observe(conn, cursor, statement, parameters, context, many):
        del conn, cursor, parameters, context, many
        if "operational_peak" in statement or "hierarchical_forecast" in statement:
            statements.append(statement)

    event.listen(factory.kw["bind"].sync_engine, "before_cursor_execute", observe)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app_for(auth)), base_url="https://synthetic.test"
        ) as client:
            assert (await login(client)).status_code == 200
            for path in ("scope", "saved-runs"):
                response = await client.get(PREFIX + path)
                assert response.status_code == 403 and response.json()["data"] is None
            assert statements == []
    finally:
        event.remove(factory.kw["bind"].sync_engine, "before_cursor_execute", observe)
