"""Production ingress, real canonical PostgreSQL reads and frozen engine parity."""

from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

from backend.app.forecast_intelligence.application import execute_hierarchical_run
from backend.app.forecast_intelligence.decision_service import DecisionSupportService
from backend.app.forecast_intelligence.hierarchy import COMPANY_ID
from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.local_auth.models import AuthResourceGrant
from backend.app.local_auth.sessions import now
from backend.app.main import create_app
from backend.tests.forecast_intelligence.conftest import seed_sources
from backend.tests.forecast_intelligence.test_reconciliation import request as hierarchy_request
from backend.tests.forecast_intelligence.test_v0_17_s1_service_read_api import (
    hierarchy_query,
    params,
    query,
)
from backend.tests.forecast_intelligence.test_v0_17_s2_decision_service import (
    comparison_payload,
    request_payload,
)
from backend.tests.local_auth.conftest import login

pytestmark = pytest.mark.postgres


@pytest.mark.asyncio
async def test_a13_controlled_legacy_ingress_no_fallback(pg_auth):
    auth, _, _, _, _ = pg_auth
    app = create_app(auth.settings)
    app.state.local_auth = auth
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        for path in (
            "/api/v1/trial/forecast",
            "/api/v1/blueberry/v1/mcp",
            "/api/v1/blueberry/v1/mcp/sse",
            "/api/v1/actual-harvest/imports",
            "/api/v1/operational-peak-runs",
        ):
            denied = await client.get(path, headers={"X-Actor": "admin", "X-Role": "ADMIN"})
            assert denied.status_code == 403 and denied.json()["data"] is None
        assert (
            await client.get("/api/v1/forecast-intelligence/curve", params=params(query()))
        ).status_code == 401


@pytest.mark.asyncio
async def test_a07_unauthorized_forecast_reads_zero(pg_auth):
    auth, factory, _, _, _ = pg_auth
    statements = []

    def observe(conn, cursor, statement, parameters, context, executemany):
        del conn, cursor, parameters, context, executemany
        if "operational_peak" in statement.lower() or "hierarchical_forecast" in statement.lower():
            statements.append(statement)

    app = create_app(auth.settings)
    app.state.local_auth = auth
    event.listen(factory.kw["bind"].sync_engine, "before_cursor_execute", observe)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://synthetic.test"
        ) as client:
            assert (await login(client)).status_code == 200
            for run in (1, 999999):
                denied = await client.get(
                    "/api/v1/forecast-intelligence/curve", params=params(query(run))
                )
                assert denied.status_code == 403
            assert statements == []
    finally:
        event.remove(factory.kw["bind"].sync_engine, "before_cursor_execute", observe)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["BASE", "REGION", "COMPANY"])
async def test_a14_real_controlled_http_frozen_service_parity(pg_auth, synthetic_authority, kind):
    auth, factory, _, account, _ = pg_auth
    # Only fixture setup executes the existing frozen synthetic seed generator;
    # all HTTP acceptance reads below use persisted canonical results.
    ids = await seed_sources(factory, synthetic_authority)
    selected = query(ids[0])
    if kind != "BASE":
        async with factory() as db, db.begin():
            saved = await execute_hierarchical_run(
                db,
                hierarchy_request(
                    ids[:2] if kind == "REGION" else ids,
                    kind,
                    "A" if kind == "REGION" else COMPANY_ID,
                ),
            )
        selected = hierarchy_query(saved)
    async with factory() as db:
        reader = ForecastIntelligenceReadService(db)
        source = await reader.curve(selected)
        expected = {
            operation: (await getattr(reader, operation)(selected)).model_dump(mode="json")
            for operation in ("overview", "curve", "hierarchy", "uncertainty", "attribution")
        }
        decision = DecisionSupportService(reader)
        payload = request_payload(source)
        expected_simulation = (await decision.simulate(payload)).model_dump(mode="json")
        expected_comparison = (await decision.compare(comparison_payload(payload))).model_dump(
            mode="json"
        )
    async with factory() as db, db.begin():
        db.add(
            AuthResourceGrant(
                principal_id=account.principal_id,
                resource_kind="FORECAST",
                capability="may_read_forecast",
                organization_id="SYNTHETIC_ORG",
                approved_by_principal=account.principal_id,
                approval_reference="SYNTHETIC_TEST_ONLY",
                reason="isolated parity",
                grant_revision=1,
                forecast_binding={
                    "identity": selected.model_dump(
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
        )
    app = create_app(auth.settings)
    app.state.local_auth = auth
    business_dml = []

    def no_business_write(conn, cursor, statement, parameters, context, many):
        del conn, cursor, parameters, context, many
        if (
            statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
            and "auth_" not in statement
        ):
            business_dml.append(statement)
            raise AssertionError("NO_BUSINESS_DML")

    event.listen(factory.kw["bind"].sync_engine, "before_cursor_execute", no_business_write)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        assert (await login(client)).status_code == 200
        for operation, canonical in expected.items():
            received = await client.get(
                "/api/v1/forecast-intelligence/" + operation, params=params(selected)
            )
            assert received.status_code == 200, received.text
            assert received.json() == canonical
        token = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
        headers = {"Origin": "https://synthetic.test", "X-CSRF-Token": token}
        for name, body, canonical in (
            ("simulate-capacity", payload, expected_simulation),
            ("compare-capacity-scenarios", comparison_payload(payload), expected_comparison),
        ):
            received = await client.post(
                "/api/v1/decision-support/" + name, json=body, headers=headers
            )
            assert received.status_code == 200, received.text
            assert received.json() == canonical
    event.remove(factory.kw["bind"].sync_engine, "before_cursor_execute", no_business_write)
    assert business_dml == []
