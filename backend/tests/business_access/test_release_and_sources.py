"""Real response locking, concurrent principals, canonical corruption and source separation."""

import asyncio
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from backend.app.business_access.response import DiscoveryResponse
from backend.app.business_access.service import DiscoveryService
from backend.app.forecast_intelligence.application import execute_hierarchical_run
from backend.app.forecast_intelligence.read_schemas import QualityReadQuery
from backend.app.forecast_intelligence.read_service import PUBLIC_EVIDENCE_HASHES
from backend.app.local_auth.authorization import binding_digest
from backend.app.local_auth.models import AuthAccount, AuthResourceGrant
from backend.app.local_auth.sessions import now
from backend.app.models.operational_peak import OperationalPeakForecastDaily
from backend.tests.business_access.test_discovery import PREFIX, app_for, grant
from backend.tests.business_access.test_security import (
    corrupt_synthetic_record,
    seed,
    selected,
    submit,
)
from backend.tests.forecast_intelligence.test_reconciliation import request as hierarchy_request
from backend.tests.forecast_intelligence.test_v0_17_s1_service_read_api import (
    hierarchy_query,
)
from backend.tests.local_auth.conftest import login
from backend.tests.local_auth.test_authorization_release import request

pytestmark = pytest.mark.postgres


async def test_shared_release_lock_and_cancellation(pg_auth, synthetic_authority):
    auth, factory, client, account, _ = pg_auth
    _, _, _ = await seed(auth, factory, account, synthetic_authority, count=1)
    await login(client)
    incoming = request(client)
    principal = await auth.authenticate(incoming)
    service = DiscoveryService(auth)
    async with factory() as db:
        data, catalog = await service.scope(db, principal)
    response = DiscoveryResponse(data, service, incoming, principal, catalog)
    sending = asyncio.Event()
    never = asyncio.Event()

    async def send(message):
        if message["type"] == "http.response.start":
            sending.set()
            await never.wait()

    async def receive():
        return {"type": "http.disconnect"}

    task = asyncio.create_task(response(incoming.scope, receive, send))
    await asyncio.wait_for(sending.wait(), 5)
    try:
        # NOWAIT is a deterministic PostgreSQL assertion: the real send gate
        # still holds the subject lock, not a timer-based approximation.
        from sqlalchemy.exc import DBAPIError

        async with factory() as db, db.begin():
            with pytest.raises(DBAPIError, match="could not obtain lock"):
                await db.scalar(
                    select(AuthAccount)
                    .where(AuthAccount.account_id == account.account_id)
                    .with_for_update(nowait=True)
                )
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    async with factory() as db, db.begin():
        subject = await asyncio.wait_for(
            db.scalar(
                select(AuthAccount)
                .where(AuthAccount.account_id == account.account_id)
                .with_for_update(nowait=True)
            ),
            5,
        )
        assert subject.principal_id == principal.principal_id


@pytest.mark.parametrize("during_release", [False, True])
async def test_canonical_daily_corruption_rejected(
    pg_auth, synthetic_authority, monkeypatch, during_release
):
    auth, factory, _, account, _ = pg_auth
    ids, _, app = await seed(auth, factory, account, synthetic_authority, count=1)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        await login(client)
        payload = await selected(client)

        async def corrupt():
            async with factory() as db, db.begin():
                await corrupt_synthetic_record(
                    db,
                    update(OperationalPeakForecastDaily)
                    .where(
                        OperationalPeakForecastDaily.run_id == ids[0],
                        OperationalPeakForecastDaily.row_index == 0,
                    )
                    .values(predicted_kg="999999.000000"),
                )

        if during_release:
            original = DiscoveryResponse.__call__

            async def interleave(response, scope, receive, send):
                await corrupt()
                await original(response, scope, receive, send)

            monkeypatch.setattr(DiscoveryResponse, "__call__", interleave)
        else:
            await corrupt()
        result = await submit(client, payload)
        assert result.status_code == 409, result.text
        assert result.json()["data"] is None and "handoff_token" not in result.text


async def test_sources_not_collapsed_and_partial_hierarchy(pg_auth, synthetic_authority):
    auth, factory, _, account, _ = pg_auth
    ids, _, app = await seed(auth, factory, account, synthetic_authority, count=1)
    async with factory() as db, db.begin():
        region = await execute_hierarchical_run(db, hierarchy_request(ids[:2], "REGION", "A"))
        partial = await execute_hierarchical_run(db, hierarchy_request(ids[:3]))
    await grant(factory, account, hierarchy_query(region))
    await grant(factory, account, hierarchy_query(partial))
    assert ids[0] == region.run.run_id  # Same numeric ID, distinct authoritative sources.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        await login(client)
        result = await client.get(PREFIX + "saved-runs")
        assert result.status_code == 200, result.text
        items = result.json()["data"]["items"]
        assert len(items) == 3
        assert {i["forecast_identity"]["source_kind"] for i in items} == {
            "OPERATIONAL_PEAK",
            "HIERARCHICAL",
        }
        assert items[0]["forecast_identity"]["source_kind"] == "HIERARCHICAL"
        assert items[0]["forecast_identity"]["run_id"] == partial.run.run_id
        assert items[0]["completeness_status"] == "INCOMPLETE_CHILD_COVERAGE"
        payload = await selected(client)
        assert (await submit(client, payload)).status_code == 200


async def test_quality_grant_does_not_discover_forecasts(pg_auth):
    auth, factory, _, account, _ = pg_auth
    async with factory() as db, db.begin():
        db.add(
            AuthResourceGrant(
                principal_id=account.principal_id,
                resource_kind="QUALITY",
                capability="may_read_quality",
                organization_id="SYNTHETIC_ORG",
                approved_by_principal=account.principal_id,
                approval_reference="SYNTHETIC",
                reason="SYNTHETIC independent Quality",
                grant_revision=1,
                forecast_binding=None,
                quality_binding={
                    "query": QualityReadQuery().model_dump(mode="json"),
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
        )
    async with AsyncClient(
        transport=ASGITransport(app=app_for(auth)), base_url="https://synthetic.test"
    ) as client:
        await login(client)
        scope = await client.get(PREFIX + "scope")
        assert scope.status_code == 200, scope.text
        assert scope.json()["data"]["entities"] == []
        assert scope.json()["data"]["capabilities"] == ["may_read_quality"]
        assert (await client.get(PREFIX + "saved-runs")).status_code == 403


async def test_ungranted_existing_and_nonexistent_no_business_reads(pg_auth, synthetic_authority):
    from sqlalchemy import event

    auth, factory, _, account, _ = pg_auth
    ids, _, app = await seed(auth, factory, account, synthetic_authority, count=1)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        await login(client)
        payload = await selected(client)
        statements = []

        def observe(conn, cursor, statement, parameters, context, many):
            if "operational_peak" in statement or "hierarchical_forecast" in statement:
                statements.append(statement)

        event.listen(factory.kw["bind"].sync_engine, "before_cursor_execute", observe)
        try:
            for run in (ids[1], 999999):
                payload["forecast_identity"].update(run_id=run, entity_id="A2")
                result = await submit(client, payload)
                assert result.status_code == 403 and result.json()["data"] is None
            assert statements == []
        finally:
            event.remove(factory.kw["bind"].sync_engine, "before_cursor_execute", observe)
