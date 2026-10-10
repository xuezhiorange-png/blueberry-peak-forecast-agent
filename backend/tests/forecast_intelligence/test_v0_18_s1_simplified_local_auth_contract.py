"""Offline contract tests for the additive V0.18 local-auth plan."""

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs/v0-18/s1/simplified-local-auth-plan-r1.md"
EVIDENCE = ROOT / "docs/v0-18/evidence/s1-simplified-local-auth-plan-r1.json"
HISTORICAL_PREFLIGHT = ROOT / "docs/v0-18/evidence/s1-identity-and-grant-preflight-r1.json"

FROZEN_SOURCE_HASHES = {
    "docs/v0-18/v0.18.0-business-usability-scope-freeze.md": (
        "d621c76041c16fb2bfd03f99946777edfc66a34d05cc2ffb321dcc0ca28dbf78"
    ),
    "docs/v0-18/v0.18.0-architecture-and-stage-plan.md": (
        "228cce31135e3e9feee0ab67b16dbcc8680b16d9e8a4ba9b169cd6fc9643740d"
    ),
    "docs/v0-18/evidence/v0.18.0-scope-freeze-r1.json": (
        "c81e2cad07bf07ae7ae3f9590df03a60f17ba8d01c20822ca7aa981516c45545"
    ),
    "docs/v0-18/s1/s1-implementation-readiness-decision-matrix-r1.md": (
        "4f37bdef1327b6aa71e7ca82dbcbd05337d153e7f1964e011b00c92566072b81"
    ),
    "docs/v0-18/s1/identity-provider-bff-adaptation-review-r1.md": (
        "dcb515ab1c957b89a3dbd8cc4bd782105c5ff0ac856fe78ae6761fff7c95b58b"
    ),
    "docs/v0-18/s1/resource-grant-authority-review-r1.md": (
        "0268b84441856b4a3cd83dcad3d8789f4469d12e74b3f2cf54608d035091e57a"
    ),
    "docs/v0-18/evidence/s1-identity-and-grant-preflight-r1.json": (
        "f4505dec93e3bdc5d5a8e41deabbbe8b6bd4a66b3134b10f2c0efdd37a4e026c"
    ),
}


def _read_evidence() -> dict[str, Any]:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def test_evidence_is_canonical_and_all_source_hashes_match() -> None:
    evidence = _read_evidence()
    canonical = json.dumps(evidence, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    assert EVIDENCE.read_text(encoding="utf-8") == canonical

    sources = evidence["source_evidence_sha256"]
    assert evidence["source_evidence_count"] == len(sources) == 30
    assert set(FROZEN_SOURCE_HASHES.items()).issubset(sources.items())
    assert (
        sources["docs/v0-18/s1/simplified-local-auth-plan-r1.md"]
        == hashlib.sha256(PLAN.read_bytes()).hexdigest()
    )

    for relative_path, expected_hash in sources.items():
        path = Path(relative_path)
        assert not path.is_absolute()
        assert ".." not in path.parts
        assert len(expected_hash) == 64
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected_hash


def test_fresh_baseline_and_completed_preflight_are_not_rewritten() -> None:
    evidence = _read_evidence()
    live = evidence["live_preflight"]
    assert evidence["base_main_sha"] == "f333a2f713f409abfa967d9dfea5b025638f03a2"
    assert live["main_sha"] == evidence["base_main_sha"]
    assert evidence["current_baseline_status"]["latest_formal_release"] == "v0.17.0"
    assert live["v018_draft_pr_found"] is False

    assert live["s0"]["pr_number"] == 710
    assert live["s0"]["pr_state"] == "MERGED"
    assert live["s0"]["formal_complete_verified"] is True
    assert live["s0"]["post_merge_ci_conclusion"] == "success"
    assert live["s1_preflight"]["pr_number"] == 711
    assert live["s1_preflight"]["pr_state"] == "MERGED"
    assert live["s1_preflight"]["formal_complete_verified"] is True
    assert live["s1_preflight"]["production_implementation_authorized"] is False

    old_preflight = json.loads(HISTORICAL_PREFLIGHT.read_text(encoding="utf-8"))
    old_identity_review = old_preflight["identity_provider_review"]
    assert old_identity_review["company_provider_status"] == "UNVERIFIED"
    assert old_identity_review["selection_status"] == "PENDING_OWNER_DECISION"
    assert evidence["historical_contracts"]["historical_oidc_recommendation_rewritten"] is False


def test_local_account_and_session_contract_is_server_owned_and_fail_closed() -> None:
    evidence = _read_evidence()
    identity = evidence["identity_and_session_contract"]
    assert identity["human_roles"] == ["ADMIN", "BUSINESS_USER"]
    assert identity["public_signup"] is False
    assert identity["account_self_registration"] is False
    assert identity["shared_default_account"] is False
    assert identity["internal_principal_mapping"] == (
        "SERVER_GENERATED_IMMUTABLE_NON_RECYCLING_OPAQUE_PRINCIPAL_ID"
    )
    assert identity["principal_key_is_username"] is False
    assert identity["service_account_is_human_account"] is False
    assert identity["admin_role_implies_forecast_access"] is False
    assert identity["admin_role_implies_quality_access"] is False
    assert identity["session_server_side"] is True
    assert identity["session_revocation_events"] == [
        "logout",
        "account disable",
        "password reset",
        "material grant revocation",
    ]
    assert "HttpOnly" in identity["browser_cookie_candidate"]
    assert "Secure" in identity["browser_cookie_candidate"]
    assert "SameSite=Lax" in identity["browser_cookie_candidate"]
    assert "synchronizer token" in identity["csrf_controls"]
    assert "Origin validation for state-changing requests" in identity["csrf_controls"]
    assert identity["password_storage"].startswith("salted adaptive password hash only")
    assert "19 MiB" in identity["password_storage_parameter_floor"]


def test_resource_grants_are_explicit_non_inheriting_and_checked_before_reads() -> None:
    evidence = _read_evidence()
    grants = evidence["resource_grant_contract"]
    assert grants["scope_levels"] == ["BASE", "REGION", "COMPANY"]
    assert grants["base_region_company_independent_no_inheritance"] is True
    assert grants["historical_quality_independent_grant"] is True
    assert grants["grant_publisher_server_side_only"] is True
    assert grants["client_fields_can_create_or_expand_grant"] is False
    assert grants["source_hash_alone_authorizes"] is False
    assert grants["scope_wildcard_default"] is False
    assert grants["required_saved_forecast_identity_fields"] == [
        "source_kind",
        "forecast_family",
        "run_id",
        "hierarchy_level",
        "entity_id",
        "target_season",
        "origin_date",
        "baseline_id",
        "policy_version",
        "source_result_hash",
    ]
    assert grants["unauthorized_business_read_count_expected"] == 0
    assert grants["unauthorized_quality_read_count_expected"] == 0
    assert grants["unauthorized_simulation_count_expected"] == 0
    assert grants["authorization_order"] == [
        "authenticate account and resolve active principal",
        "check capability and explicit scope grant",
        "verify complete canonical saved-run identity and source hash",
        "read/project business data or execute permitted simulation",
    ]


def test_stage_order_and_mcp_compatibility_remain_bounded() -> None:
    evidence = _read_evidence()
    stages = evidence["proposed_stage_plan"]
    assert [item["stage"] for item in stages] == ["S0", "S1", "S2", "S3", "S4", "S5", "S6"]
    assert all(item["implementation_authorized"] is False for item in stages)
    runtime = evidence["runtime_and_scope_status"]
    assert runtime["mcp_identity_mode_first_release"] == (
        "SERVICE_ACCOUNT_WITH_EXACT_RUN_AND_QUALITY_GRANTS"
    )
    assert runtime["mcp_end_user_delegation_implemented"] is False
    assert runtime["mcp_tool_count"] == 8
    assert runtime["mcp_tool_names"] == [
        "get_forecast_overview",
        "get_forecast_curve",
        "get_hierarchical_forecast",
        "get_forecast_uncertainty",
        "get_forecast_attribution",
        "get_forecast_quality",
        "simulate_capacity",
        "compare_capacity_scenarios",
    ]
    assert evidence["historical_contracts"]["legacy_route_isolation_verified"] is False
    assert (
        evidence["historical_contracts"][
            "legacy_routes_must_be_adapted_or_network_restricted_before_pilot"
        ]
        is True
    )
    assert runtime["production_readiness"] == "NOT_READY"


def test_governance_forbids_runtime_scope_and_release_actions() -> None:
    evidence = _read_evidence()
    governance = evidence["governance"]
    assert evidence["decision_record"]["owner_auth_direction"] == "SIMPLIFIED_LOCAL_AUTH"
    assert evidence["decision_record"]["scope_amendment_required"] is True
    assert evidence["decision_record"]["scope_amendment_status"] == "PENDING_OWNER_APPROVAL"
    assert governance["s0_original_scope_preserved"] is True
    assert governance["historical_evidence_modified"] is False
    assert governance["s1_production_implementation_authorized"] is False
    assert governance["production_code_authorized"] is False
    assert governance["production_code_changed"] is False
    assert governance["database_migration_created"] is False
    assert governance["model_or_forecast_changed"] is False
    assert governance["ready_authorized"] is False
    assert governance["merge_authorized"] is False
    assert governance["deploy_authorized"] is False
    assert governance["tag_authorized"] is False
    assert governance["release_authorized"] is False


def test_plan_marks_amendment_and_owner_decisions_without_claiming_approval() -> None:
    document = PLAN.read_text(encoding="utf-8")
    assert "SCOPE_AMENDMENT_REQUIRED=true" in document
    assert "PENDING_OWNER_DECISION" in document
    assert "S1 production implementation authorized | `false`" in document
    assert "No runtime behavior is changed here." in document
    assert "## Owner decisions still pending" in document
    assert "## Security references" in document
