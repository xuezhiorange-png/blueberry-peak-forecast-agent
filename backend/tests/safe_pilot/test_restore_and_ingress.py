"""SYNTHETIC S5: real pg_dump/pg_restore, TLS network, auth and canonical read."""

import hashlib
import json
import ssl
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.area_yield.data import digest as authority_digest
from backend.app.forecast_intelligence.hierarchy import COMPANY_ID, build_hierarchy
from backend.app.forecast_intelligence.persistence import HierarchicalRunRepository, source_mapping
from backend.app.forecast_intelligence.read_schemas import ForecastReadQuery
from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.forecast_intelligence.reconciliation import reconcile
from backend.app.forecast_intelligence.schemas import CreateHierarchicalRun
from backend.app.forecast_quality.operational_peak_persistence import (
    OperationalPeakRunRepository,
    execution_hash,
)
from backend.app.local_auth.models import AuthAccount, AuthResourceGrant
from backend.app.local_auth.passwords import hash_password
from backend.app.local_auth.service import AuthService
from backend.app.local_auth.sessions import COOKIE, now
from backend.app.main import create_app
from backend.tests.business_access.test_discovery import grant
from backend.tests.safe_pilot.operations import (
    approve_synthetic_recovery_password,
    assert_redacted,
    backup,
    guard_business_writes,
    isolated_environment,
    quarantine,
    restored_database,
    row_digest,
    snapshot,
    tls_server,
)
from frontend.e2e.support.dashboard_api import saved_fixture

pytestmark = pytest.mark.postgres
PASSWORD = "SYNTHETIC-password-123"


async def seed(factory, user):
    result = saved_fixture("SYNTHETIC_S5_BASE")
    authority = hashlib.sha256(b"SYNTHETIC_S5_AUTHORITY").hexdigest()
    request = {
        "base_id": result.base_id,
        "target_season": result.target_season,
        "origin_date": result.origin_date.isoformat(),
    }
    async with factory() as db, db.begin():
        saved = await OperationalPeakRunRepository(db).save(
            request,
            result,
            execution_hash(request, authority, result.policy_version),
            authority,
            None,
        )
        second_result = saved_fixture("SYNTHETIC_S5_OTHER_BASE")
        second_request = {**request, "base_id": second_result.base_id}
        second = await OperationalPeakRunRepository(db).save(
            second_request,
            second_result,
            execution_hash(second_request, authority, second_result.policy_version),
            authority,
            None,
        )
        registry = {
            "bases": [
                {"base_id": b, "canonical_base_name": b, "region_scope": "SYNTHETIC_S5_REGION"}
                for b in (result.base_id, second_result.base_id)
            ]
        }
        hierarchy = build_hierarchy(registry, authority, authority_digest(registry))
        sources = [source_mapping(s) for s in (saved, second)]
        for level, entity in (("REGION", "SYNTHETIC_S5_REGION"), ("COMPANY", COMPANY_ID)):
            aggregate_request = CreateHierarchicalRun(
                target_entity_type=level,
                target_entity_id=entity,
                source_run_ids=[saved.run.run_id, second.run.run_id],
            )
            await HierarchicalRunRepository(db).save(
                hierarchy,
                aggregate_request,
                reconcile(hierarchy, aggregate_request, sources),
                sources,
            )
        user_row = await db.get(AuthAccount, user.account_id)
        user_row.managed_organization_ids = ["SYNTHETIC_ORG"]
        administrator = AuthAccount(
            username_normalized="synthetic-admin",
            password_hash=hash_password(PASSWORD),
            role="ADMIN",
            status="ACTIVE",
            must_change_password=False,
            managed_organization_ids=["SYNTHETIC_ORG"],
            created_at=now(),
            updated_at=now(),
        )
        db.add(administrator)
        selected = ForecastReadQuery(
            source_kind="OPERATIONAL_PEAK",
            forecast_family="OPERATIONAL_PEAK_FORECAST_RUN_V1",
            run_id=saved.run.run_id,
            hierarchy_level="BASE",
            entity_id=result.base_id,
            target_season=result.target_season,
            origin_date=result.origin_date,
            baseline_id=result.baseline_id,
            policy_version=result.policy_version,
            expected_source_result_hash=saved.run.result_hash,
        )
    binding = await grant(factory, user, selected)
    guard_business_writes(factory)
    return selected, binding


async def sign_in(client, username="synthetic-user", *, password=PASSWORD, expected=200):
    csrf = await client.get("/api/v1/auth/csrf")
    assert csrf.status_code == 200
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={
            "Origin": str(client.base_url).rstrip("/"),
            "X-CSRF-Token": csrf.json()["data"]["csrf_token"],
        },
    )
    assert response.status_code == expected, response.text
    return client.cookies.get(COOKIE)


def application(auth):
    app = create_app(auth.settings)
    app.state.local_auth = auth
    return app


async def test_full_backup_restore_reapproval_and_fail_closed_rollback(
    pg_auth, tmp_path, record_property
):
    auth, factory, _, user, database = pg_auth
    selected, binding = await seed(factory, user)
    auth.settings.business_access_signing_key = SecretStr("SYNTHETIC_S5_SIGNING_" * 4)
    auth.settings.local_auth_simple_admin_catalog_json = SecretStr(
        json.dumps(
            {
                "organization_ids": ["SYNTHETIC_ORG"],
                "resources": [
                    {
                        "organization_id": "SYNTHETIC_ORG",
                        "resource_kind": "FORECAST",
                        "capability": "may_read_forecast",
                        "binding": binding.forecast_binding,
                    }
                ],
            }
        )
    )
    app = application(auth)
    async with factory() as db:
        original = (await ForecastIntelligenceReadService(db).curve(selected)).model_dump(
            mode="json"
        )
    async with tls_server(app, tmp_path) as (origin, certificate, _):
        auth.settings.local_auth_origin = origin
        context = ssl.create_default_context(cafile=str(certificate))
        async with httpx.AsyncClient(base_url=origin, verify=context) as http:
            old_cookie = await sign_in(http)
            listing = (await http.get("/api/v1/business-access/saved-runs")).json()["data"]
            csrf = (await http.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
            item = listing["items"][0]
            handoff = await http.post(
                "/api/v1/business-access/selection",
                json={
                    "forecast_identity": item["forecast_identity"],
                    "expected_source_result_hash": item["expected_source_result_hash"],
                    "grant_revision": listing["grant_revision"],
                    "catalog_snapshot": listing["catalog_snapshot"],
                },
                headers={"Origin": origin, "X-CSRF-Token": csrf},
            )
            assert handoff.status_code == 200
            old_handoff = handoff.json()["data"]["handoff_token"]
            before = await snapshot(factory)
            assert all(value["count"] > 0 for value in before.values())
            directory = tmp_path / "SYNTHETIC-backup"
            directory.mkdir(mode=0o700)
            archive, archive_hash = await backup(database, directory)
            assert await snapshot(factory) == before
            with pytest.raises(ValueError, match="BACKUP_HASH_MISMATCH"):
                async with restored_database(database, archive, "0" * 64):
                    pytest.fail("INVALID_BACKUP_WAS_RESTORED")
            # Revoke AFTER backup: restoration must not resurrect that earlier grant.
            async with factory() as db, db.begin():
                row = await db.get(AuthResourceGrant, binding.grant_id)
                row.revoked_at = now()
                account = await db.get(AuthAccount, user.account_id)
                account.grant_revision += 1
                await auth.revoke_all(db, account, "SYNTHETIC_POST_BACKUP_REVOCATION")
            async with restored_database(database, archive, archive_hash) as restored:
                env = isolated_environment(restored)
                from sqlalchemy import URL

                engine = create_async_engine(
                    URL.create(
                        "postgresql+asyncpg",
                        username=env["PGUSER"],
                        password=env["PGPASSWORD"],
                        host=env["PGHOST"],
                        port=int(env["PGPORT"]),
                        database=restored,
                    )
                )
                restored_factory = async_sessionmaker(engine, expire_on_commit=False)
                guard_business_writes(restored_factory)
                try:
                    assert await snapshot(restored_factory) == before
                    async with restored_factory() as db:
                        assert (
                            await ForecastIntelligenceReadService(db).curve(selected)
                        ).model_dump(mode="json") == original
                    # No listener exists for the restored DB until all authority is quarantined.
                    await quarantine(restored_factory)
                    restored_auth = AuthService(restored_factory, auth.settings.model_copy())
                    restored_app = application(restored_auth)
                    tls_dir = tmp_path / "restored-TLS"
                    tls_dir.mkdir()
                    async with tls_server(restored_app, tls_dir) as (
                        restored_origin,
                        restored_cert,
                        _,
                    ):
                        restored_auth.settings.local_auth_origin = restored_origin
                        async with httpx.AsyncClient(
                            base_url=restored_origin,
                            verify=ssl.create_default_context(cafile=str(restored_cert)),
                        ) as restored_http:
                            restored_http.cookies.set(
                                COOKIE, old_cookie, domain="127.0.0.1", path="/"
                            )
                            assert (await restored_http.get("/api/v1/auth/me")).status_code == 401
                            await sign_in(restored_http, expected=401)
                            await approve_synthetic_recovery_password(
                                restored_factory,
                                user.account_id,
                                "SYNTHETIC-restored-user-password",
                            )
                            await sign_in(
                                restored_http, password="SYNTHETIC-restored-user-password"
                            )
                            denied = await restored_http.get(
                                "/api/v1/forecast-intelligence/curve",
                                params=selected.model_dump(mode="json"),
                            )
                            assert denied.status_code == 403 and denied.json()["data"] is None
                            assert (
                                await restored_http.get("/api/v1/business-access/saved-runs")
                            ).status_code == 403
                            csrf = (await restored_http.get("/api/v1/auth/csrf")).json()["data"][
                                "csrf_token"
                            ]
                            stale = await restored_http.post(
                                "/api/v1/business-access/selection",
                                json={
                                    "forecast_identity": item["forecast_identity"],
                                    "expected_source_result_hash": item[
                                        "expected_source_result_hash"
                                    ],
                                    "grant_revision": listing["grant_revision"],
                                    "catalog_snapshot": listing["catalog_snapshot"],
                                    "handoff_token": old_handoff,
                                },
                                headers={"Origin": restored_origin, "X-CSRF-Token": csrf},
                            )
                            assert stale.status_code in {403, 409}
                        async with httpx.AsyncClient(
                            base_url=restored_origin,
                            verify=ssl.create_default_context(cafile=str(restored_cert)),
                        ) as admin_http:
                            await sign_in(admin_http, "synthetic-admin", expected=401)
                            async with restored_factory() as db:
                                administrator = await db.scalar(
                                    select(AuthAccount).where(
                                        AuthAccount.username_normalized == "synthetic-admin"
                                    )
                                )
                            await approve_synthetic_recovery_password(
                                restored_factory,
                                administrator.account_id,
                                "SYNTHETIC-restored-admin-password",
                            )
                            await sign_in(
                                admin_http,
                                "synthetic-admin",
                                password="SYNTHETIC-restored-admin-password",
                            )
                            assert (
                                await admin_http.get(
                                    "/api/v1/forecast-intelligence/curve",
                                    params=selected.model_dump(mode="json"),
                                )
                            ).status_code == 403
                            csrf = (await admin_http.get("/api/v1/auth/csrf")).json()["data"][
                                "csrf_token"
                            ]
                            async with restored_factory() as db:
                                subject = await db.get(AuthAccount, user.account_id)
                            approved = await admin_http.post(
                                "/api/v1/admin/resource-grants",
                                json={
                                    "subject_principal_id": user.principal_id,
                                    "organization_id": "SYNTHETIC_ORG",
                                    "resource_kind": "FORECAST",
                                    "capability": "may_read_forecast",
                                    "binding": binding.forecast_binding,
                                    "valid_from": (now() - timedelta(seconds=2)).isoformat(),
                                    "valid_until": (now() + timedelta(hours=1)).isoformat(),
                                    "expected_grant_revision": subject.grant_revision,
                                    "reason": "SYNTHETIC restore explicit reapproval",
                                },
                                headers={"Origin": restored_origin, "X-CSRF-Token": csrf},
                            )
                            assert approved.status_code == 201, approved.text
                        async with httpx.AsyncClient(
                            base_url=restored_origin,
                            verify=ssl.create_default_context(cafile=str(restored_cert)),
                        ) as renewed:
                            await sign_in(renewed, password="SYNTHETIC-restored-user-password")
                            curve = await renewed.get(
                                "/api/v1/forecast-intelligence/curve",
                                params=selected.model_dump(mode="json"),
                            )
                            assert curve.status_code == 200 and curve.json() == original
                            quality = await renewed.get("/api/v1/forecast-intelligence/quality")
                            assert quality.status_code == 403  # still independent
                            assert (
                                await renewed.get("/api/v1/trial/forecast-runs")
                            ).status_code == 403
                    record_property("backup_sha256", archive_hash)
                    record_property("canonical_source_hash", original["source_result_hash"])
                    record_property("restored_table_snapshot", json.dumps(before, sort_keys=True))
                finally:
                    await engine.dispose()


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/trial/forecast-input-authority"),
        ("POST", "/api/v1/trial/forecasts"),
        ("POST", "/api/v1/blueberry/v1/mcp"),
        ("GET", "/api/v1/blueberry/v1/mcp/sse"),
        ("GET", "/sse"),
        ("GET", "/api/v1/operational-peak-forecast-runs"),
        ("POST", "/api/v1/actual-harvest/imports"),
        ("GET", "/api/v1/hierarchical-forecast-runs"),
        ("GET", "/docs"),
        ("GET", "/openapi.json"),
        ("POST", "/unlisted/SYNTHETIC"),
    ],
)
async def test_real_network_legacy_denial_before_database(pg_auth, tmp_path, method, path):
    auth, factory, _, _, _ = pg_auth
    statements = []

    def observe(*args):
        statements.append(args[2])

    event.listen(factory.kw["bind"].sync_engine, "before_cursor_execute", observe)
    try:
        async with tls_server(application(auth), tmp_path) as (origin, cert, _):
            auth.settings.local_auth_origin = origin
            async with httpx.AsyncClient(
                base_url=origin, verify=ssl.create_default_context(cafile=str(cert))
            ) as http:
                denied = await http.request(
                    method,
                    path,
                    headers={"X-Actor": "ADMIN", "Content-Type": "application/json"},
                    content=b"{}" if method == "POST" else None,
                )
                assert denied.status_code == 403 and denied.json()["data"] is None
                assert denied.headers["cache-control"] == "no-store"
                assert statements == []
    finally:
        event.remove(factory.kw["bind"].sync_engine, "before_cursor_execute", observe)


async def test_untrusted_host_origin_proxy_and_missing_secrets(pg_auth, tmp_path, caplog):
    auth, factory, _, user, _ = pg_auth
    selected, _ = await seed(factory, user)
    async with tls_server(application(auth), tmp_path) as (origin, cert, _):
        auth.settings.local_auth_origin = origin
        async with httpx.AsyncClient(
            base_url=origin, verify=ssl.create_default_context(cafile=str(cert))
        ) as http:
            transmitted = []

            async def capture(request):
                for name in ("cookie", "x-csrf-token"):
                    if request.headers.get(name):
                        transmitted.append(request.headers[name])

            http.event_hooks["request"].append(capture)
            cookie = await sign_in(http)
            for headers in (
                {"Host": "evil.invalid"},
                {"Origin": "https://evil.invalid"},
                {"X-Actor": "ADMIN"},
                {"X-Principal-Id": user.principal_id},
            ):
                assert (await http.get("/api/v1/auth/me", headers=headers)).status_code == 403
            http.cookies.clear()
            assert (
                await http.get(
                    "/api/v1/forecast-intelligence/curve",
                    params=selected.model_dump(mode="json"),
                    headers={"X-Forwarded-Proto": "https", "X-Forwarded-User": user.principal_id},
                )
            ).status_code == 401
            auth.settings.local_auth_login_bucket_secret = SecretStr("")
            assert (await http.get("/api/v1/auth/csrf")).status_code == 503
            auth.settings.local_auth_login_bucket_secret = SecretStr("SYNTHETIC_RESTORED_SECRET")
            await sign_in(http)
            auth.settings.local_auth_organization_ids_json = "NOT_JSON"
            denied = await http.get(
                "/api/v1/forecast-intelligence/curve", params=selected.model_dump(mode="json")
            )
            assert denied.status_code == 503 and denied.json()["data"] is None
            auth.settings.local_auth_organization_ids_json = '["SYNTHETIC_ORG"]'
            auth.settings.business_access_signing_key = SecretStr("")
            assert (await http.get("/api/v1/business-access/saved-runs")).status_code == 503
            auth.settings.business_access_signing_key = SecretStr("SYNTHETIC_REPAIRED_SIGNING_" * 3)
            assert (await http.get("/api/v1/business-access/saved-runs")).status_code == 200
            csrf = (await http.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
            assert (
                await http.post(
                    "/api/v1/auth/logout", json={}, headers={"Origin": origin, "X-CSRF-Token": csrf}
                )
            ).status_code == 200
            await sign_in(http, "synthetic-admin")
            auth.settings.local_auth_simple_admin_catalog_json = SecretStr("NOT_JSON")
            assert (await http.get("/api/v1/admin/users")).status_code == 503
            with pytest.raises(httpx.HTTPError):
                async with httpx.AsyncClient(trust_env=False) as insecure:
                    await insecure.get(
                        origin.replace("https://", "http://") + "/api/v1/auth/me",
                        headers={"X-Forwarded-Proto": "https"},
                    )
            assert_redacted(
                caplog.text, [PASSWORD, cookie, "SYNTHETIC_RESTORED_SECRET", *transmitted]
            )


@pytest.mark.unit
@pytest.mark.contract
def test_backup_rejects_unsafe_targets_and_log_scanner_cannot_false_pass(monkeypatch):
    for database in (
        "postgres",
        "blueberry_peak",
        "blueberry_test_auth_../../",
        "blueberry_test_s5_not_uuid",
    ):
        with pytest.raises(ValueError):
            isolated_environment(database)
    monkeypatch.setenv("POSTGRES_HOST", "production.invalid")
    with pytest.raises(ValueError):
        isolated_environment("blueberry_test_s5_" + uuid4().hex)
    assert_redacted("safe action=DENY", ["SYNTHETIC_SECRET"])
    with pytest.raises(AssertionError, match="SENSITIVE_LOG_VALUE_FOUND"):
        assert_redacted("leaked=SYNTHETIC_SECRET", ["SYNTHETIC_SECRET"])


@pytest.mark.unit
@pytest.mark.contract
def test_snapshot_preserves_numeric_lexemes_and_duplicate_rows():
    first = '{"quantity":1000000000000.000000000001}'
    second = '{"quantity":1000000000000.000000000002}'
    assert json.loads(first) == json.loads(second)  # illustrates the old float collision
    assert row_digest([first]) != row_digest([second])
    assert row_digest([first, second]) == row_digest([second, first])
    assert row_digest([first, first]) != row_digest([first])
