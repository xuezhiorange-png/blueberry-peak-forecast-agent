"""D03 direct administration against isolated PostgreSQL; no real accounts."""

import json
from datetime import timedelta

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import select

from backend.app.forecast_intelligence.read_schemas import QualityReadQuery
from backend.app.forecast_intelligence.read_service import PUBLIC_EVIDENCE_HASHES
from backend.app.local_auth.authorization import authorize, binding_digest
from backend.app.local_auth.models import AuthAccount, AuthAuditEvent, AuthResourceGrant
from backend.app.local_auth.sessions import AuthError, now
from backend.tests.forecast_intelligence.test_v0_17_s1_service_read_api import query
from backend.tests.local_auth.test_admin_runtime import admin
from backend.tests.local_auth.test_authorization_release import request

pytestmark = pytest.mark.postgres


async def simple(pg_auth):
    auth, _, client, _, _ = pg_auth
    _, headers = await admin(pg_auth)
    binding = {
        "identity": query().model_dump(mode="json", exclude={"expected_source_result_hash"}),
        "expected_source_result_hash": "a" * 64,
        "source_authority_version": "SYNTHETIC_R1",
    }
    catalog = {
        "organization_ids": ["SYNTHETIC_ORG"],
        "resources": [
            {
                "organization_id": "SYNTHETIC_ORG",
                "resource_kind": "FORECAST",
                "capability": "may_read_forecast",
                "binding": binding,
            }
        ],
    }
    auth.settings.local_auth_publisher_boundaries_json = SecretStr("")
    auth.settings.local_auth_simple_admin_catalog_json = SecretStr(json.dumps(catalog))
    created = await client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "username": "synthetic-direct",
            "initial_password": "SYNTHETIC-temporary-password",
            "role": "BUSINESS_USER",
            "reason": "SYNTHETIC create",
        },
    )
    assert created.status_code == 201, created.text
    return headers, created.json()["data"], binding, catalog


async def test_direct_create_reset_disable_and_audit_without_account_registration(pg_auth):
    _, factory, client, _, _ = pg_auth
    headers, child, _, _ = await simple(pg_auth)
    listed = (await client.get("/api/v1/admin/users")).json()["data"]["items"]
    assert child["account_id"] in {v["account_id"] for v in listed}
    reset = await client.post(
        f"/api/v1/admin/users/{child['account_id']}/reset-password",
        headers=headers,
        json={
            "new_temporary_password": "SYNTHETIC-reset-password",
            "expected_auth_revision": 1,
            "reason": "SYNTHETIC reset",
        },
    )
    assert reset.status_code == 200
    disabled = await client.patch(
        f"/api/v1/admin/users/{child['account_id']}/status",
        headers=headers,
        json={"status": "DISABLED", "expected_auth_revision": 2, "reason": "SYNTHETIC disable"},
    )
    assert disabled.status_code == 200
    async with factory() as db:
        account = await db.get(AuthAccount, child["account_id"])
        assert account.status == "DISABLED" and account.auth_revision == 3
        assert account.managed_organization_ids == ["SYNTHETIC_ORG"]
        events = (
            await db.scalars(
                select(AuthAuditEvent).where(
                    AuthAuditEvent.target_account_id == child["account_id"]
                )
            )
        ).all()
        assert {v.reason_code for v in events} == {
            "SYNTHETIC create",
            "SYNTHETIC reset",
            "SYNTHETIC disable",
        }
        assert all(v.actor_principal_id and v.occurred_at for v in events)


async def test_direct_exact_catalog_assignment_cas_and_revoke(pg_auth):
    auth, factory, client, _, _ = pg_auth
    headers, child, binding, _ = await simple(pg_auth)
    payload = {
        "subject_principal_id": child["principal_id"],
        "organization_id": "SYNTHETIC_ORG",
        "resource_kind": "FORECAST",
        "capability": "may_read_forecast",
        "binding": binding,
        "valid_from": (now() - timedelta(seconds=5)).isoformat(),
        "valid_until": (now() + timedelta(hours=1)).isoformat(),
        "expected_grant_revision": 1,
        "reason": "SYNTHETIC assign",
    }
    for invalid in (
        {**payload, "organization_id": "INVENTED"},
        {**payload, "binding": {**binding, "expected_source_result_hash": "b" * 64}},
        {**payload, "binding": {**binding, "identity": {**binding["identity"], "run_id": 999999}}},
    ):
        assert (
            await client.post("/api/v1/admin/resource-grants", headers=headers, json=invalid)
        ).status_code == 403
    published = await client.post("/api/v1/admin/resource-grants", headers=headers, json=payload)
    assert published.status_code == 201, published.text
    grant_id = published.json()["data"]["grant_id"]
    principal = await auth.authenticate(request(client))
    with pytest.raises(AuthError):
        await authorize(auth, principal, query())  # ADMIN has no implicit data access.
    assert (
        await client.post("/api/v1/admin/resource-grants", headers=headers, json=payload)
    ).status_code == 409
    async with AsyncClient(transport=client._transport, base_url="https://synthetic.test") as user:
        csrf = (await user.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
        assert (
            await user.post(
                "/api/v1/auth/login",
                json={"username": "synthetic-direct", "password": "SYNTHETIC-temporary-password"},
                headers={"Origin": "https://synthetic.test", "X-CSRF-Token": csrf},
            )
        ).status_code == 200
        csrf = (await user.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
        assert (
            await user.post(
                "/api/v1/auth/change-password",
                json={
                    "current_password": "SYNTHETIC-temporary-password",
                    "new_password": "SYNTHETIC-final-password",
                },
                headers={"Origin": "https://synthetic.test", "X-CSRF-Token": csrf},
            )
        ).status_code == 200
        principal = await auth.authenticate(request(user))
        snapshot, selected = await authorize(auth, principal, query())
        assert snapshot["grant_id"] == grant_id and selected.expected_source_result_hash == "a" * 64
        for selection in (
            query(run_id=999999),
            query(hierarchy_level="COMPANY"),
            QualityReadQuery(),
        ):
            with pytest.raises(AuthError):
                await authorize(auth, principal, selection)
        assert (await user.get("/api/v1/admin/users")).status_code == 403
        revoked = await client.post(
            f"/api/v1/admin/resource-grants/{grant_id}/revoke",
            headers=headers,
            json={"expected_grant_revision": 2, "reason": "SYNTHETIC revoke"},
        )
        assert revoked.status_code == 200
        assert (await user.get("/api/v1/auth/me")).status_code == 401
        with pytest.raises(AuthError):
            await authorize(auth, principal, query())
    async with factory() as db:
        grant = await db.get(AuthResourceGrant, grant_id)
        assert (
            grant.revoked_at is not None and grant.approval_reference == "ADMIN_DIRECT_ASSIGNMENT"
        )
        assert grant.forecast_binding == binding and grant.quality_binding is None
        account = await db.get(AuthAccount, child["account_id"])
        assert account.grant_revision == 3


async def test_simple_admin_unregistered_subject_org_and_elevation_denied(pg_auth):
    auth, _, client, account, _ = pg_auth
    headers, _, _, catalog = await simple(pg_auth)
    assert (
        await client.post(
            "/api/v1/admin/users",
            headers=headers,
            json={
                "username": "synthetic-admin",
                "initial_password": "SYNTHETIC-temporary-password",
                "role": "ADMIN",
                "reason": "SYNTHETIC",
            },
        )
    ).status_code == 403
    assert (
        await client.patch(
            "/api/v1/admin/users/00000000-0000-0000-0000-000000000001/status",
            headers=headers,
            json={"status": "DISABLED", "expected_auth_revision": 1, "reason": "SYNTHETIC"},
        )
    ).status_code == 403
    assert (
        await client.patch(
            f"/api/v1/admin/users/{account.account_id}/status",
            headers=headers,
            json={"status": "DISABLED", "expected_auth_revision": 1, "reason": "SYNTHETIC"},
        )
    ).json()["code"] == "LAST_ADMIN_PROTECTED"
    catalog["organization_ids"] = ["INVENTED"]
    catalog["resources"] = []
    auth.settings.local_auth_simple_admin_catalog_json = SecretStr(json.dumps(catalog))
    assert (await client.get("/api/v1/admin/users")).status_code == 503


async def test_direct_quality_is_separately_registered_and_cross_org_subject_hidden(pg_auth):
    auth, factory, client, _, _ = pg_auth
    headers, child, _, catalog = await simple(pg_auth)
    async with factory() as db, db.begin():
        from backend.app.local_auth.passwords import hash_password

        other = AuthAccount(
            username_normalized="synthetic-other-org",
            password_hash=hash_password("SYNTHETIC-password-123"),
            role="BUSINESS_USER",
            status="ACTIVE",
            managed_organization_ids=["OTHER"],
            created_at=now(),
            updated_at=now(),
        )
        db.add(other)
        await db.flush()
    assert (
        await client.patch(
            f"/api/v1/admin/users/{other.account_id}/status",
            headers=headers,
            json={"status": "DISABLED", "expected_auth_revision": 1, "reason": "SYNTHETIC"},
        )
    ).status_code == 403
    listed = (await client.get("/api/v1/admin/users")).json()["data"]["items"]
    assert other.account_id not in {v["account_id"] for v in listed}
    binding = {
        "query": QualityReadQuery().model_dump(mode="json"),
        "source_split": "EXPOSED_OOT",
        "target_season": "2025-2026",
        "scope": "BASE_COHORT_AGGREGATE",
        "evidence_policy_version": "SYNTHETIC_R1",
        "evidence_hashes": PUBLIC_EVIDENCE_HASHES,
        "evidence_set_digest": binding_digest(PUBLIC_EVIDENCE_HASHES),
    }
    payload = {
        "subject_principal_id": child["principal_id"],
        "organization_id": "SYNTHETIC_ORG",
        "resource_kind": "QUALITY",
        "capability": "may_read_quality",
        "binding": binding,
        "valid_from": (now() - timedelta(seconds=5)).isoformat(),
        "valid_until": (now() + timedelta(hours=1)).isoformat(),
        "expected_grant_revision": 1,
        "reason": "SYNTHETIC quality",
    }
    assert (
        await client.post("/api/v1/admin/resource-grants", headers=headers, json=payload)
    ).status_code == 403
    catalog["resources"].append(
        {key: payload[key] for key in ("organization_id", "resource_kind", "capability", "binding")}
    )
    auth.settings.local_auth_simple_admin_catalog_json = SecretStr(json.dumps(catalog))
    assert (
        await client.post("/api/v1/admin/resource-grants", headers=headers, json=payload)
    ).status_code == 201
    changed = {**payload, "subject_principal_id": other.principal_id, "expected_grant_revision": 1}
    assert (
        await client.post("/api/v1/admin/resource-grants", headers=headers, json=changed)
    ).status_code == 403


@pytest.mark.parametrize(
    "raw", ["{}", "null", "not-json", '{"organization_ids":["*"],"resources":[]}']
)
async def test_invalid_direct_catalog_never_falls_back_to_legacy_approval(pg_auth, raw):
    auth, _, client, _, _ = pg_auth
    await admin(pg_auth)
    auth.settings.local_auth_simple_admin_catalog_json = SecretStr(raw)
    assert (await client.get("/api/v1/admin/users")).status_code == 503
