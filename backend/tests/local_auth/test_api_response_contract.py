"""Real synthetic PostgreSQL HTTP responses match immutable PR #716 fields."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr

from backend.app.local_auth.sessions import now
from backend.tests.forecast_intelligence.test_v0_17_s1_service_read_api import query
from backend.tests.local_auth.test_admin_runtime import admin

pytestmark = pytest.mark.postgres
CONTRACT = json.loads(
    (
        Path(__file__).resolve().parents[3]
        / "docs/v0-18/evidence/s1-local-auth-implementation-contract-r1.json"
    ).read_text()
)["api"]["endpoints"]


def fields(response, endpoint, status=200):
    assert response.status_code == status, response.text
    assert set(response.json()["data"]) == set(CONTRACT[endpoint]["response_fields"])
    assert all(
        secret not in response.text
        for secret in (
            "password_hash",
            "token_digest",
            "csrf_token_digest",
            "SYNTHETIC-temporary-password",
        )
    )
    return response.json()["data"]


async def test_r4_all_admin_response_fields_and_scoped_pagination(pg_auth):
    auth, _, client, account, _ = pg_auth
    boundary, headers = await admin(pg_auth)
    created = await client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "username": "synthetic-contract",
            "initial_password": "SYNTHETIC-temporary-password",
            "role": "BUSINESS_USER",
            "reason": "SYNTHETIC R4",
        },
    )
    child = fields(created, "create_user", 201)
    boundary["manageable_account_ids"].append(child["account_id"])
    boundary["create_roles"].append("ADMIN")
    auth.settings.local_auth_publisher_boundaries_json = SecretStr(json.dumps([boundary]))
    listed = fields(await client.get("/api/v1/admin/users?page_size=1"), "list_users")
    assert len(listed["items"]) == 1 and listed["next_account_id"] is not None
    second = fields(
        await client.get(
            "/api/v1/admin/users",
            params={"page_size": 1, "after_account_id": listed["next_account_id"]},
        ),
        "list_users",
    )
    assert second["next_account_id"] is None
    assert {v["account_id"] for v in listed["items"] + second["items"]} == {
        account.account_id,
        child["account_id"],
    }
    path = "/api/v1/admin/users/" + child["account_id"]
    role = fields(
        await client.patch(
            path + "/role",
            headers=headers,
            json={"role": "ADMIN", "expected_auth_revision": 1, "reason": "SYNTHETIC"},
        ),
        "user_role",
    )
    assert role["auth_revision"] == 2
    status = fields(
        await client.patch(
            path + "/status",
            headers=headers,
            json={"status": "DISABLED", "expected_auth_revision": 2, "reason": "SYNTHETIC"},
        ),
        "user_status",
    )
    assert status["auth_revision"] == 3
    reset = fields(
        await client.post(
            path + "/reset-password",
            headers=headers,
            json={
                "new_temporary_password": "SYNTHETIC-reset-password",
                "expected_auth_revision": 3,
                "reason": "SYNTHETIC",
            },
        ),
        "reset_password",
    )
    assert reset == {"reset": True, "must_change_password": True}
    payload = {
        "subject_principal_id": child["principal_id"],
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
        "reason": "SYNTHETIC R4",
    }
    boundary["approved_grants"] = [payload]
    auth.settings.local_auth_publisher_boundaries_json = SecretStr(json.dumps([boundary]))
    grant = fields(
        await client.post("/api/v1/admin/resource-grants", headers=headers, json=payload),
        "create_grant",
        201,
    )
    assert grant["binding_summary"] == {
        "binding": payload["binding"],
        "resource_kind": "FORECAST",
        "capability": "may_read_forecast",
        "organization_id": "SYNTHETIC_ORG",
    }
    grants = fields(await client.get("/api/v1/admin/resource-grants"), "list_grants")
    assert [g["grant_id"] for g in grants["items"]] == [grant["grant_id"]]
    revoked = fields(
        await client.post(
            "/api/v1/admin/resource-grants/" + grant["grant_id"] + "/revoke",
            headers=headers,
            json={"expected_grant_revision": 2, "reason": "SYNTHETIC"},
        ),
        "revoke_grant",
    )
    assert revoked["revoked"] and revoked["new_grant_revision"] == 3
    params = {
        "organization_id": "SYNTHETIC_ORG",
        "from": (now() - timedelta(hours=1)).isoformat(),
        "to": (now() + timedelta(minutes=1)).isoformat(),
    }
    events = fields(await client.get("/api/v1/admin/audit-events", params=params), "audit_events")
    assert {e["action"] for e in events["items"]} >= {"GRANT_CREATED", "GRANT_REVOKED"}
    assert (
        await client.get(
            "/api/v1/admin/audit-events", params={**params, "organization_id": "SYNTHETIC_OTHER"}
        )
    ).status_code == 403
    assert (await client.get("/api/v1/admin/users?page_size=101")).status_code == 422


async def test_r4_auth_response_fields_match_frozen_contract(pg_auth):
    _, _, client, _, _ = pg_auth
    csrf = fields(await client.get("/api/v1/auth/csrf"), "csrf")
    headers = {"Origin": "https://synthetic.test", "X-CSRF-Token": csrf["csrf_token"]}
    fields(
        await client.post(
            "/api/v1/auth/login",
            headers=headers,
            json={"username": "synthetic-user", "password": "SYNTHETIC-password-123"},
        ),
        "login",
    )
    fields(await client.get("/api/v1/auth/me"), "me")
    csrf = fields(await client.get("/api/v1/auth/csrf"), "csrf")
    headers["X-CSRF-Token"] = csrf["csrf_token"]
    assert fields(
        await client.post(
            "/api/v1/auth/change-password",
            headers=headers,
            json={
                "current_password": "SYNTHETIC-password-123",
                "new_password": "SYNTHETIC-new-password",
            },
        ),
        "change_password",
    )["password_changed"]
    csrf = fields(await client.get("/api/v1/auth/csrf"), "csrf")
    headers["X-CSRF-Token"] = csrf["csrf_token"]
    assert fields(await client.post("/api/v1/auth/logout", headers=headers, json={}), "logout")[
        "logged_out"
    ]
