"""Offline contract checks for the V0.18 S1 identity/grant preflight."""

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/v0-18/evidence/s1-identity-and-grant-preflight-r1.json"
DESIGN_DOCS = (
    "docs/v0-18/s1/identity-provider-bff-adaptation-review-r1.md",
    "docs/v0-18/s1/resource-grant-authority-review-r1.md",
    "docs/v0-18/s1/s1-implementation-readiness-decision-matrix-r1.md",
)
REQUIRED_SOURCES = {
    "backend/app/actual_harvest_import/api_auth.py",
    "backend/app/api/forecast_intelligence_decision.py",
    "backend/app/api/forecast_intelligence_read.py",
    "backend/app/forecast_intelligence/decision_service.py",
    "backend/app/forecast_intelligence/read_access.py",
    "backend/app/forecast_intelligence/read_service.py",
    "backend/app/mcp/forecast_intelligence_auth.py",
    "backend/app/mcp/forecast_intelligence_http.py",
    "backend/app/mcp/forecast_intelligence_tools.py",
    "backend/app/trial.py",
    "backend/tests/forecast_intelligence/test_v0_17_s1_service_read_api.py",
    "backend/tests/forecast_intelligence/test_v0_17_s2_decision_api.py",
    "backend/tests/mcp/test_v0_17_s3_productization.py",
    "docs/v0-17/v0.17-s1-forecast-intelligence-service-read-api-r1.md",
    "docs/v0-17/v0.17-s2-decision-support-api-r1.md",
    "docs/v0-17/v0.17-s3-mcp-productization-r1.md",
    "docs/v0-18/evidence/v0.18.0-scope-freeze-r1.json",
    "docs/v0-18/v0.18.0-architecture-and-stage-plan.md",
    "docs/v0-18/v0.18.0-business-usability-scope-freeze.md",
    "frontend/src/dashboard/api/client.ts",
    "frontend/src/dashboard/context/ForecastContext.tsx",
}


@pytest.fixture(scope="module")
def evidence() -> dict:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def test_machine_evidence_is_canonical_and_all_bound_sources_match(evidence: dict) -> None:
    raw = EVIDENCE.read_bytes()
    canonical = (json.dumps(evidence, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
    assert raw == canonical

    sources = evidence["source_evidence_sha256"]
    assert evidence["source_evidence_count"] == len(sources) == 34
    assert REQUIRED_SOURCES.issubset(sources)
    assert set(DESIGN_DOCS).issubset(sources)
    for relative_path, expected_hash in sources.items():
        path = Path(relative_path)
        assert not path.is_absolute()
        assert ".." not in path.parts
        assert len(expected_hash) == 64
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected_hash


def test_live_baseline_and_s0_formal_receipt_are_frozen(evidence: dict) -> None:
    live = evidence["live_preflight"]
    assert evidence["base_main_sha"] == "52b5a80f89c59130917b29c9097d63076eab4acb"
    assert live["main_sha"] == evidence["base_main_sha"]
    assert live["latest_formal_release"] == "v0.17.0"
    assert live["s0_pr_number"] == 710
    assert live["s0_pr_state"] == "MERGED"
    assert live["s0_pr_base_sha"] == "1b218edc74ff29091c07607ddbcdba0c10577398"
    assert live["s0_pr_head_sha"] == "504ca8eca78bfdeb083de5fe0cb1b3a9da1e55a4"
    assert live["s0_merge_commit_sha"] == evidence["base_main_sha"]
    assert live["s0_formal_complete_confirmed"] is True
    assert live["s0_exact_head_ci_conclusion"] == "success"
    assert live["s0_main_post_merge_ci_conclusion"] == "success"
    assert live["s0_main_post_merge_ci_event"] == "push"
    assert live["s0_main_post_merge_ci_head_sha"] == evidence["base_main_sha"]
    assert live["s0_main_post_merge_ci_jobs"] == "4_SUCCESS_8_WORKFLOW_SKIPPED"
    assert live["open_v018_s1_pr_found"] is False
    assert live["open_v018_s1_remote_branch_found"] is False


def test_identity_provider_candidates_are_not_misrepresented_as_configured(evidence: dict) -> None:
    review = evidence["identity_provider_review"]
    assert review["company_provider_status"] == "UNVERIFIED"
    assert review["company_enterprise_provider_verified"] is False
    assert review["repository_oidc_bff_runtime_found"] is False
    assert review["selection_status"] == "PENDING_OWNER_DECISION"
    assert "TRUSTED_ISSUER_AND_TENANT" in review["unverified_inputs"]
    assert "BFF_HOSTING_AND_SESSION_STORE" in review["unverified_inputs"]

    identity_docs = (ROOT / DESIGN_DOCS[0]).read_text(encoding="utf-8")
    assert "候选 A：企业托管 OIDC + 同源 BFF" in identity_docs
    assert "候选 B：独立部署 OIDC 提供方 + 同源 BFF" in identity_docs
    assert "候选 C：浏览器 SPA 直接 OIDC/OAuth" in identity_docs
    assert "PENDING_OWNER_DECISION" in identity_docs
    assert "UNVERIFIED" in identity_docs


def test_principal_and_grant_contract_is_explicit_and_default_deny(evidence: dict) -> None:
    mapping = evidence["principal_mapping"]
    assert mapping["end_user_key"] == ["validated_issuer", "case_sensitive_subject"]
    assert mapping["internal_principal_id"] == "SERVER_OWNED_IMMUTABLE_IDENTIFIER"
    assert mapping["email_or_display_name_is_identity_key"] is False
    assert mapping["principal_types"] == ["END_USER", "SERVICE_ACCOUNT"]
    assert mapping["service_account_is_end_user"] is False

    grants = evidence["resource_authorization_design"]
    assert grants["default_deny"] is True
    assert grants["wildcard_or_allow_all"] is False
    assert grants["base_region_company_grants_independent"] is True
    assert grants["quality_grant_independent"] is True
    assert grants["resource_grant_binds_complete_forecast_identity_and_source_hash"] is True
    assert grants["client_supplied_actor_or_source_system_authorizes"] is False
    assert grants["hierarchy_registry_used_as_acl"] is False
    assert grants["missing_or_ungranted_resource_existence_disclosed"] is False
    assert grants["unauthorized_business_read_expected"] == 0
    assert grants["unauthorized_quality_evidence_read_expected"] == 0
    assert grants["unauthorized_simulation_expected"] == 0
    assert grants["grant_verification_order"] == [
        "TRUSTED_AUTHENTICATION",
        "PRINCIPAL_STATUS",
        "CAPABILITY",
        "ORGANIZATION_SCOPE_AND_EXACT_RESOURCE_GRANT",
        "CANONICAL_BUSINESS_READ",
        "IDENTITY_AND_SOURCE_HASH_RECHECK",
        "FROZEN_S1_S2_SERVICE",
        "PRE_RESPONSE_GRANT_REVISION_RECHECK",
    ]


def test_http_mcp_dashboard_adaptation_preserves_business_authority(evidence: dict) -> None:
    adaptation = evidence["adaptation_review"]
    http = adaptation["http"]
    assert http["existing_permission_names"] == ["may_read_forecast", "may_read_quality"]
    assert http["end_user_resource_acl_available"] is False
    assert http["business_repository_read_before_permission_tested_zero"] is True
    assert (
        http["route_permission_check_is_inside_handler_after_service_dependency_resolution"] is True
    )
    assert http["s1_s2_business_payload_and_math_change_allowed"] is False

    mcp = adaptation["mcp"]
    assert mcp["tool_count"] == 8
    assert mcp["tool_names_change_allowed"] is False
    assert mcp["existing_run_grant_binds_full_forecast_identity_and_source_hash"] is True
    assert mcp["existing_quality_grant_independent"] is True
    assert mcp["end_user_delegation_available"] is False
    assert mcp["end_user_delegation_client_compatibility"] == "UNVERIFIED"
    assert mcp["service_account_is_end_user"] is False

    dashboard = adaptation["dashboard"]
    assert dashboard["advanced_identity_input_is_authorization"] is False
    assert dashboard["business_run_discovery_available"] is False
    assert dashboard["normal_user_login_available"] is False


def test_six_owner_decisions_are_pending_or_explicitly_recommended(evidence: dict) -> None:
    decisions = evidence["owner_decisions"]
    assert [item["decision_id"] for item in decisions] == [
        "DECISION-01",
        "DECISION-02",
        "DECISION-03",
        "DECISION-04",
        "DECISION-05",
        "DECISION-06",
    ]
    assert all("APPROVED" not in item["status"] for item in decisions)
    assert decisions[0]["status"] == "PENDING_OWNER_DECISION"
    assert decisions[3]["status"] == "BLOCKER_PENDING_OWNER_DECISION"
    assert decisions[5]["status"] == "BLOCKER_UNVERIFIED_CLIENT_COMPATIBILITY"
    matrix = (ROOT / DESIGN_DOCS[2]).read_text(encoding="utf-8")
    for decision_id in (f"DECISION-0{n}" for n in range(1, 7)):
        assert decision_id in matrix


def test_scope_and_governance_do_not_authorize_implementation(evidence: dict) -> None:
    assert evidence["task_id"] == "V0_18_S1_IDENTITY_AND_GRANT_AUTHORITY_PREFLIGHT_R1"
    assert evidence["authorized_scope"] == "DESIGN_AND_ADAPTATION_REVIEW_ONLY"
    assert evidence["owner_authorized"] is True
    assert evidence["s1_implementation_authorized"] is False
    for field in (
        "database_migration_created",
        "identity_provider_connected",
        "production_code_changed",
        "production_database_connected",
        "production_user_created",
        "real_secret_created",
        "sensitive_business_data_read",
    ):
        assert evidence["scope"][field] is False
