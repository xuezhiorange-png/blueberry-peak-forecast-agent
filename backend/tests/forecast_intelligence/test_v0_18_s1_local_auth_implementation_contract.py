"""Offline specification checks only: no runtime authentication or data access."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from backend.tests.historical_source import source_bytes

ROOT = Path(__file__).resolve().parents[3]
DOC = "docs/v0-18/s1/local-auth-implementation-contract-r1.md"
EVIDENCE = "docs/v0-18/evidence/s1-local-auth-implementation-contract-r1.json"
ADDENDUM = "docs/v0-18/evidence/s0-simplified-local-auth-scope-addendum-r1.json"
ADDENDUM_SHA = "eaf767b26e02e3495e9ac57bc61ee44c02229c25d82c79c5c49665ec3e796055"
BASE = "5b07acee24a56ffb9c7b7f6b697c6763e96e06b8"


def evidence() -> dict[str, Any]:
    value = json.loads((ROOT / EVIDENCE).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_canonical_json_and_independently_pinned_history() -> None:
    data = evidence()
    assert (ROOT / EVIDENCE).read_bytes() == (
        json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    assert hashlib.sha256((ROOT / ADDENDUM).read_bytes()).hexdigest() == ADDENDUM_SHA
    old = json.loads((ROOT / ADDENDUM).read_text(encoding="utf-8"))
    pins = {**old["source_evidence_sha256"], ADDENDUM: ADDENDUM_SHA}
    assert data["historical_source_sha256"] == pins
    for path, digest in data["source_evidence_sha256"].items():
        assert hashlib.sha256(source_bytes(path, root=ROOT)).hexdigest() == digest, path
    assert data["source_evidence_count"] == len(data["source_evidence_sha256"])
    assert data["source_evidence_sha256"].items() >= pins.items()
    assert DOC in data["source_evidence_sha256"]
    assert EVIDENCE not in data["source_evidence_sha256"]


def test_version_live_baseline_and_new_governance_event() -> None:
    data = evidence()
    assert data["base_main_sha"] == BASE
    assert data["task_id"] == "V0_18_S1_LOCAL_AUTH_IMPLEMENTATION_CONTRACT_R1"
    assert data["version"] == "0.18.0"
    assert data["version_name"] == "BUSINESS_USABILITY_AND_SAFE_PILOT_FOUNDATION"
    assert data["latest_formal_release"] == "v0.17.0"
    assert data["live_preflight"]["pr715"]["merge_sha"] == BASE
    assert data["live_preflight"]["pr715"]["post_merge_ci"] == 38114257884
    assert data["live_preflight"]["pr715"]["ci_conclusion"] == "success"
    assert data["governance"]["owner_contract_authorized"] is True
    assert data["governance"]["s0_addendum_formal_complete_basis"] == (
        "OWNER_CONFIRMED_WITH_LIVE_MERGE_AND_PUSH_CI"
    )
    for key, value in data["governance"].items():
        if key.endswith("_authorized") and key != "owner_contract_authorized":
            assert value is False, key
    assert data["governance"]["runtime_implemented"] is False
    assert data["governance"]["production_readiness"] == "NOT_READY"
    assert data["allowed_changed_files"] == [
        DOC,
        EVIDENCE,
        "backend/tests/forecast_intelligence/test_v0_18_s1_local_auth_implementation_contract.py",
    ]


def test_four_additive_tables_and_real_migration_head() -> None:
    database = evidence()["database"]
    assert database["reuse"] == "EXISTING_POSTGRESQL_SQLALCHEMY_BASE_ASYNCSESSION"
    assert database["observed_alembic_heads"] == ["0040_hierarchical_forecast"]
    assert database["future_revision_id"] is None
    assert database["migration_created"] is False
    assert set(database["tables"]) == {
        "auth_account",
        "auth_session",
        "auth_resource_grant",
        "auth_audit_event",
    }
    account = database["tables"]["auth_account"]
    assert {
        "account_id",
        "principal_id",
        "username_normalized",
        "password_hash",
        "auth_revision",
        "grant_revision",
        "role",
        "status",
    } <= set(account)
    assert database["principal_immutable_non_reusable"] is True
    assert database["username_is_authorization_key"] is False
    assert database["trial_owner_is_local_principal"] is False
    assert database["audit_append_only"] is True
    assert database["management_audit_atomic"] is True


def test_local_identity_roles_password_and_pending_parameters() -> None:
    auth = evidence()["authentication"]
    assert auth["mode"] == "LOCAL_USERNAME_PASSWORD"
    assert auth["roles"] == ["ADMIN", "BUSINESS_USER"]
    assert auth["principal_types"] == ["END_USER", "SERVICE_ACCOUNT"]
    assert auth["public_registration"] is False
    assert auth["shared_default_account"] is False
    assert auth["admin_implicit_forecast_access"] is False
    assert auth["admin_implicit_quality_access"] is False
    assert auth["password_algorithm"] == "ARGON2ID"
    assert auth["candidate_dependency"] == "argon2-cffi"
    assert (
        auth["candidate_dependency_review_status"] == "PENDING_IMPLEMENTATION_DEPENDENCY_APPROVAL"
    )
    params = auth["candidate_parameters"]
    assert params["approval_status"] == "PENDING_OWNER_APPROVAL"
    assert (params["memory_kib_min"], params["time_cost_min"], params["parallelism"]) == (
        19456,
        2,
        1,
    )
    assert (params["idle_seconds"], params["absolute_seconds"]) == (28800, 86400)
    assert (params["failure_window_seconds"], params["failure_count"]) == (900, 5)
    assert auth["login_throttling_cross_worker_atomic"] is True
    assert auth["bootstrap_public_endpoint"] is False
    assert auth["reset_forces_password_change"] is True


def test_session_csrf_revocation_and_response_release_contract() -> None:
    session = evidence()["session"]
    assert session["mode"] == "OPAQUE_SERVER_SIDE_SESSION"
    assert session["token_random_bytes_min"] == 32
    assert session["database_stores_raw_token"] is False
    assert session["cookie"] == {
        "name": "__Host-blueberry-session",
        "secure": True,
        "http_only": True,
        "same_site": "Lax",
        "path": "/",
        "domain": None,
    }
    assert session["csrf"] == "SYNCHRONIZER_TOKEN_AND_EXACT_ORIGIN_JSON"
    assert session["preauth_grants_business_access"] is False
    assert session["password_change_required_blocks_business"] is True
    assert set(session["invalidation_events"]) == {
        "LOGOUT",
        "ACCOUNT_DISABLE",
        "PASSWORD_RESET",
        "ROLE_CHANGE",
        "MATERIAL_GRANT_REVOCATION",
    }
    grant = evidence()["authorization"]
    assert grant["pre_response_grant_revision_recheck"] is True
    assert grant["pre_response_principal_active_recheck"] is True
    assert grant["fresh_revision_read"] == "READ_COMMITTED_NOT_STALE_ORM_SNAPSHOT"
    assert grant["sensitive_response_streaming"] is False
    assert grant["revocation_before_release_sensitive_bytes_expected"] == 0
    assert grant["already_sent_bytes_retractable"] is False
    assert grant["recheck_runtime_implemented"] is False


def test_exact_resource_scope_quality_and_denial_before_read() -> None:
    resource = evidence()["authorization"]
    assert resource["order"] == [
        "AUTHENTICATE",
        "CHECK_CAPABILITY",
        "CHECK_EXACT_RESOURCE_GRANT",
        "CANONICAL_READ",
        "VERIFY_IDENTITY_HASH",
        "PRE_RESPONSE_PRINCIPAL_GRANT_RECHECK",
    ]
    assert resource["levels"] == ["BASE", "REGION", "COMPANY"]
    assert resource["exact_run_fields"] == [
        "source_kind",
        "forecast_family",
        "run_id",
        "hierarchy_level",
        "entity_id",
        "target_season",
        "origin_date",
        "baseline_id",
        "policy_version",
        "expected_source_result_hash",
    ]
    assert resource["quality_independent"] is True
    assert resource["quality_evidence_binding_required"] is True
    for key in (
        "cross_level_inheritance",
        "future_run_auto_enrollment",
        "admin_bypass",
        "client_actor_trusted",
        "hash_is_authorization",
        "s1_saved_run_discovery",
        "global_latest",
    ):
        assert resource[key] is False, key
    assert resource["denial_before_sensitive_read"] is True
    assert resource["unauthorized_forecast_reads_expected"] == 0
    assert resource["unauthorized_quality_reads_expected"] == 0
    assert resource["unauthorized_simulations_expected"] == 0
    assert resource["unauthorized_existing_missing_same_error"] == "403_FORBIDDEN"
    assert resource["organization_steward_approval_required"] is True
    assert resource["admin_grant_publication_boundary_required"] is True


@pytest.mark.parametrize(
    "operation",
    [
        "csrf",
        "login",
        "logout",
        "me",
        "change_password",
        "create_user",
        "user_status",
        "user_role",
        "reset_password",
        "list_users",
        "create_grant",
        "revoke_grant",
        "list_grants",
        "audit_events",
    ],
)
def test_minimal_api_schema_auth_and_no_secret_response(operation: str) -> None:
    api = evidence()["api"]
    endpoint = api["endpoints"][operation]
    assert endpoint["path"].startswith("/api/v1/")
    assert endpoint["method"] in {"GET", "POST", "PATCH"}
    assert endpoint["request_extra_fields"] == "FORBID"
    assert endpoint["implemented"] is False
    assert endpoint["response_sensitive_fields"] == []
    if endpoint["method"] in {"POST", "PATCH"}:
        assert endpoint["csrf_required"] is True
    if operation in {
        "create_user",
        "user_status",
        "user_role",
        "reset_password",
        "list_users",
        "create_grant",
        "revoke_grant",
        "list_grants",
        "audit_events",
    }:
        assert endpoint["permission"] == "ADMIN_AND_APPROVED_MANAGEMENT_BOUNDARY"
    assert api["error_statuses"] == [401, 403, 404, 409, 413, 415, 422, 429, 503]
    assert api["admin_auth_body_limit_bytes"] == 16384
    assert api["errors_redact_inputs_sql_paths_credentials"] is True


def test_legacy_transport_compatibility_and_implementation_allowlist() -> None:
    data = evidence()
    compat = data["compatibility"]
    assert compat["trial_actor_fallback"] is False
    assert compat["legacy_protected_ingress_policy"] == "EXPLICIT_ALLOWLIST_DEFAULT_DENY"
    assert compat["legacy_isolation_verified"] is False
    assert compat["mcp_mode"] == "SERVICE_ACCOUNT_ONLY"
    assert compat["mcp_tool_count"] == 8
    assert compat["mcp_end_user_delegation"] is False
    assert compat["mcp_runtime_changed"] is False
    assert compat["business_payload_hash_math_unchanged"] is True
    assert compat["dashboard_runtime_changed"] is False
    assert compat["dashboard_csrf_client_stage"] == "S4"
    assert compat["s1_existing_dashboard_post_compatibility_claimed"] is False
    files = data["future_s1_allowed_paths"]
    assert "backend/app/api/forecast_intelligence_read.py" in files
    assert "backend/app/api/forecast_intelligence_decision.py" in files
    assert not any("/mcp/" in path or path.startswith("frontend/") for path in files)
    assert not any(
        path.endswith("read_service.py") or path.endswith("decision_service.py") for path in files
    )


def test_preserved_stage_dependencies_and_no_circular_s3_gate() -> None:
    data = evidence()
    old = json.loads((ROOT / ADDENDUM).read_text(encoding="utf-8"))
    assert data["stage_order"] == old["stage_order"]
    assert data["stage_dependencies"] == {
        name: stage["depends_on"] for name, stage in old["stages"].items()
    }
    safety = "SERVICE_ACCOUNT_EXACT_GRANT_SAFETY_ACCEPTANCE"
    assert safety not in data["stage_dependencies"]["S3"]
    assert safety in data["s3_completion_acceptance"]
    assert data["s3_safety_acceptance_status"] == "PENDING_NOT_EXECUTED"


def test_security_matrix_is_planned_not_executed_and_owner_decisions_explicit() -> None:
    data = evidence()
    assert [case["id"] for case in data["security_acceptance_matrix"]] == [
        f"A{i:02d}" for i in range(1, 21)
    ]
    assert all(case["status"] == "PLANNED_NOT_RUN" for case in data["security_acceptance_matrix"])
    assert len(data["owner_decisions"]) == 4
    assert all(
        decision["status"] == "PENDING_OWNER_APPROVAL" for decision in data["owner_decisions"]
    )
    assert data["governance"]["runtime_authorization_requires"] == [
        "CONTRACT_INDEPENDENT_REVIEW",
        "OWNER_CONTRACT_READY_MERGE",
        "CONTRACT_MERGE_AND_MAIN_CI_SUCCESS",
        "OWNER_PARAMETER_AND_RESPONSIBILITY_APPROVAL",
        "S1_SEPARATE_CODE_SCHEMA_DEPENDENCY_AUTHORIZATION",
    ]
    doc = (ROOT / DOC).read_text(encoding="utf-8")
    for phrase in ("PLANNED_NOT_RUN", "不再拆分设计前置任务"):
        assert phrase in doc
    for phrase in (
        "同一403",
        "PRE_RESPONSE_GRANT_REVISION_RECHECK=true",
        "账号禁用留存",
        "已在撤销前通过 gate 并发出的字节无法追回",
        "初始/重置密码",
        "S1_IMPLEMENTATION_AUTHORIZED=false",
        "NOT_READY",
        "S2才提供发现",
    ):
        assert phrase in doc
