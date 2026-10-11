"""Actual HTTP grant publication/revocation requires exact server approval."""

import json
from datetime import timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from backend.app.local_auth.models import AuthAccount, AuthAuditEvent, AuthResourceGrant
from backend.app.local_auth.sessions import now
from backend.tests.forecast_intelligence.test_v0_17_s1_service_read_api import query
from backend.tests.local_auth.test_admin_runtime import admin

pytestmark = pytest.mark.postgres


async def test_a17_approved_grant_exact_cas_revocation_and_audit(pg_auth):
    auth, factory, client, _, _ = pg_auth
    boundary, headers = await admin(pg_auth)
    response = await client.post(
        "/api/v1/admin/users",
        json={
            "username": "synthetic-grantee",
            "initial_password": "SYNTHETIC-temporary-password",
            "role": "BUSINESS_USER",
            "reason": "SYNTHETIC",
        },
        headers=headers,
    )
    assert response.status_code == 201
    subject = response.json()["data"]
    boundary["manageable_account_ids"].append(subject["account_id"])
    payload = {
        "subject_principal_id": subject["principal_id"],
        "organization_id": "SYNTHETIC_ORG",
        "resource_kind": "FORECAST",
        "capability": "may_read_forecast",
        "binding": {
            "identity": query().model_dump(mode="json", exclude={"expected_source_result_hash"}),
            "expected_source_result_hash": "a" * 64,
            "source_authority_version": "SYNTHETIC_R1",
        },
        "valid_from": (now() - timedelta(seconds=5)).isoformat(),
        "valid_until": (now() + timedelta(hours=1)).isoformat(),
        "expected_grant_revision": 1,
        "approval_reference": "SYNTHETIC_OWNER_APPROVAL",
        "reason": "SYNTHETIC acceptance",
    }
    auth.settings.local_auth_publisher_boundaries_json = SecretStr(json.dumps([boundary]))
    assert (
        await client.post("/api/v1/admin/resource-grants", json=payload, headers=headers)
    ).status_code == 403
    boundary["approved_grants"] = [payload]
    auth.settings.local_auth_publisher_boundaries_json = SecretStr(json.dumps([boundary]))
    published = await client.post("/api/v1/admin/resource-grants", json=payload, headers=headers)
    assert published.status_code == 201, published.text
    grant_id = published.json()["data"]["grant_id"]
    assert published.json()["data"]["new_grant_revision"] == 2
    assert (
        await client.post("/api/v1/admin/resource-grants", json=payload, headers=headers)
    ).status_code == 409
    changed = {**payload, "organization_id": "SYNTHETIC_OTHER"}
    assert (
        await client.post("/api/v1/admin/resource-grants", json=changed, headers=headers)
    ).status_code == 403
    revoked = await client.post(
        f"/api/v1/admin/resource-grants/{grant_id}/revoke",
        json={"expected_grant_revision": 2, "reason": "SYNTHETIC revoke"},
        headers=headers,
    )
    assert revoked.status_code == 200 and revoked.json()["data"]["new_grant_revision"] == 3
    repeated = await client.post(
        f"/api/v1/admin/resource-grants/{grant_id}/revoke",
        json={"expected_grant_revision": 3, "reason": "SYNTHETIC retry"},
        headers=headers,
    )
    assert repeated.status_code == 200
    async with factory() as db:
        grant = await db.get(AuthResourceGrant, grant_id)
        assert grant.revoked_at is not None
        account = await db.get(AuthAccount, subject["account_id"])
        assert account.grant_revision == 3
        actions = set((await db.scalars(select(AuthAuditEvent.action))).all())
        assert {"GRANT_CREATED", "GRANT_REVOKED"} <= actions
