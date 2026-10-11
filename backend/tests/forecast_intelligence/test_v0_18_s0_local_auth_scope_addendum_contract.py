"""Offline, public-only contract for the pending local-auth S0 addendum."""

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DOC = "docs/v0-18/s0/simplified-local-auth-scope-addendum-r1.md"
JSON = "docs/v0-18/evidence/s0-simplified-local-auth-scope-addendum-r1.json"
TEST = "backend/tests/forecast_intelligence/test_v0_18_s0_local_auth_scope_addendum_contract.py"
FROZEN = {
    "docs/v0-18/evidence/forecast-quality-roadmap-r1.json": (
        "0944268563ecfd8e343e9d22afcc17c9c3938d04a334a747427a10fb696d4007"
    ),
    "docs/v0-18/evidence/s1-identity-and-grant-preflight-r1.json": (
        "f4505dec93e3bdc5d5a8e41deabbbe8b6bd4a66b3134b10f2c0efdd37a4e026c"
    ),
    "docs/v0-18/evidence/s1-simplified-local-auth-plan-r1.json": (
        "ec376c24146f98899c8e8c252f5cc34d88b2929607c0fd1bda21f3e0f601b4c4"
    ),
    "docs/v0-18/evidence/v0.18-roadmap-reassessment-r1.json": (
        "a841afb40bb0f3e2eb1205350a7f60aa1a893483977c4b0e036f470c498f7203"
    ),
    "docs/v0-18/evidence/v0.18.0-scope-freeze-r1.json": (
        "c81e2cad07bf07ae7ae3f9590df03a60f17ba8d01c20822ca7aa981516c45545"
    ),
    "docs/v0-18/forecast-quality-improvement-roadmap-r1.md": (
        "fe2d0df16caf8441274851805c3610540bcd49882044c423011a78f2c7b609f1"
    ),
    "docs/v0-18/v0.18-roadmap-reassessment-r1.md": (
        "932234ecbb8bff12c9ad4fddf2126e6ccfdf9fb093dd1a3f0bc706c9f2d6f4e8"
    ),
    "docs/v0-18/v0.18.0-architecture-and-stage-plan.md": (
        "228cce31135e3e9feee0ab67b16dbcc8680b16d9e8a4ba9b169cd6fc9643740d"
    ),
    "docs/v0-18/v0.18.0-business-usability-scope-freeze.md": (
        "d621c76041c16fb2bfd03f99946777edfc66a34d05cc2ffb321dcc0ca28dbf78"
    ),
    "docs/v0-18/s1/identity-provider-bff-adaptation-review-r1.md": (
        "dcb515ab1c957b89a3dbd8cc4bd782105c5ff0ac856fe78ae6761fff7c95b58b"
    ),
    "docs/v0-18/s1/resource-grant-authority-review-r1.md": (
        "0268b84441856b4a3cd83dcad3d8789f4469d12e74b3f2cf54608d035091e57a"
    ),
    "docs/v0-18/s1/s1-implementation-readiness-decision-matrix-r1.md": (
        "4f37bdef1327b6aa71e7ca82dbcbd05337d153e7f1964e011b00c92566072b81"
    ),
    "docs/v0-18/s1/simplified-local-auth-plan-r1.md": (
        "e0980c2c3895be1b4c47fd5040cbe050b49af6bae01016dd40aa77d680e8331a"
    ),
    "backend/tests/forecast_intelligence/test_v0_18_roadmap_reassessment.py": (
        "1c11f0d8359a34fb2071b7eddcb65db61021e63eeedfcb91d67d67ae1724ab8e"
    ),
    "backend/tests/forecast_intelligence/test_v0_18_s1_preflight_contract.py": (
        "9fb4c206d1ed34ded35bc90bb73dbe74d75307a795c5e2cce55fbe6a0224b3af"
    ),
    "backend/tests/forecast_intelligence/test_v0_18_s1_simplified_local_auth_contract.py": (
        "460857ca809ecce32ac3ba720f406be57fd5346e2d157ca8ce315e4c42da0093"
    ),
    "backend/tests/forecast_intelligence/test_v0_18_scope_freeze.py": (
        "63881d7b7ef6968b24c2747a708c22bf1fa79b485840131a336c9b8d7e3727f1"
    ),
}
DEPENDENCIES = {
    "S0": ["V0_17_0_FORMAL_RELEASE"],
    "S1": [
        "S0_FORMAL_COMPLETE",
        "ADDENDUM_FORMAL_COMPLETE",
        "OWNER_LOCAL_ACCOUNT_AND_POLICY_PUBLISHER_DECISION",
    ],
    "S2": ["S1_FORMAL_COMPLETE"],
    "S3": [
        "S1_FORMAL_COMPLETE",
        "S2_FORMAL_COMPLETE",
        "SERVICE_ACCOUNT_EXACT_GRANT_SAFETY_ACCEPTANCE",
    ],
    "S4": ["S1_FORMAL_COMPLETE", "S2_FORMAL_COMPLETE", "S3_FORMAL_COMPLETE"],
    "S5": [
        "S1_FORMAL_COMPLETE",
        "S2_FORMAL_COMPLETE",
        "S3_FORMAL_COMPLETE",
        "S4_FORMAL_COMPLETE",
        "OWNER_OPERATION_PLAN_REVIEW",
    ],
    "S6": [
        "S1_FORMAL_COMPLETE",
        "S2_FORMAL_COMPLETE",
        "S3_FORMAL_COMPLETE",
        "S4_FORMAL_COMPLETE",
        "S5_FORMAL_COMPLETE",
    ],
}


def evidence() -> dict[str, Any]:
    data = json.loads((ROOT / JSON).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_canonical_bytes_and_independent_source_pins() -> None:
    data = evidence()
    canonical = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    assert (ROOT / JSON).read_bytes() == canonical.encode("utf-8")
    assert data["historical_source_sha256"] == FROZEN
    sources = data["source_evidence_sha256"]
    assert data["source_evidence_count"] == len(sources) == len(FROZEN) + 2
    assert set(sources) == set(FROZEN) | {DOC, TEST}
    assert all(sources[path] == digest for path, digest in FROZEN.items())
    for relative, digest in sources.items():
        path = Path(relative)
        assert not path.is_absolute() and ".." not in path.parts
        assert len(digest) == 64
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest


def test_baseline_and_owner_confirmed_history_not_runtime_completion() -> None:
    data = evidence()
    assert data["version"] == "0.18.0"
    assert data["version_name"] == "BUSINESS_USABILITY_AND_SAFE_PILOT_FOUNDATION"
    assert data["base_main_sha"] == "6fb43c92c874de45c773f27c50d44cbe51835bc8"
    assert data["latest_formal_release"] == "v0.17.0"
    live = data["live_preflight"]
    assert live["parallel_addendum_pr_found"] is False
    assert [stage["pr"] for stage in live["stages"]] == [710, 711, 712, 714]
    for stage in live["stages"]:
        assert stage["pr_state"] == "MERGED"
        assert stage["ci_event"] == "push"
        assert stage["ci_head_sha"] == stage["merge_sha"]
        assert stage["ci_status"] == "completed"
        assert stage["ci_conclusion"] == "success"
    assert live["stages"][-1]["merge_sha"] == data["base_main_sha"]
    assert live["pr714_main_ci_jobs"] == {"success": 4, "skipped": 8, "failed": 0}
    assert live["pr714_merge_parents"][1] == live["pr714_head_sha"]
    assert live["pr714_formal_completion_basis"] == (
        "OWNER_CONFIRMED_AND_LIVE_MERGE_PUSH_CI_VERIFIED"
    )


def test_local_identity_roles_and_sessions_are_server_owned() -> None:
    identity = evidence()["identity_contract"]
    assert identity["authentication"] == "LOCAL_USERNAME_PASSWORD"
    assert identity["provisioning"] == "ADMIN_ONLY"
    assert identity["roles"] == ["ADMIN", "BUSINESS_USER"]
    assert identity["principal_types"] == ["END_USER", "SERVICE_ACCOUNT"]
    assert identity["principal_id"] == "SERVER_GENERATED_IMMUTABLE_NON_REUSABLE"
    for key in (
        "public_signup",
        "shared_default_account",
        "username_is_permission_key",
        "client_actor_trusted",
        "admin_implies_forecast_access",
        "admin_implies_quality_access",
    ):
        assert identity[key] is False
    for key in ("session_server_side", "session_revocable", "https_required", "csrf_required"):
        assert identity[key] is True
    assert identity["cookie_requirements"] == ["Secure", "HttpOnly", "SameSite"]
    assert identity["password_storage"] == "SALTED_ADAPTIVE_HASH_NOT_PLAINTEXT_OR_REVERSIBLE"
    assert identity["password_library_and_parameters"] == "PENDING_S1_SEPARATE_APPROVAL"
    assert identity["session_ttl_and_schema"] == "PENDING_S1_SEPARATE_APPROVAL"
    assert identity["login_failure_limits_required"] is True
    assert identity["session_events_requiring_invalidation"] == [
        "LOGOUT",
        "ACCOUNT_DISABLE",
        "PASSWORD_RESET",
        "MATERIAL_GRANT_REVOCATION",
    ]


def test_scope_never_silently_expands_exact_record_authority() -> None:
    grant = evidence()["resource_contract"]
    assert grant["levels"] == ["BASE", "REGION", "COMPANY"]
    for key in (
        "default_deny",
        "explicit_grants",
        "quality_grant_independent",
        "entity_scope_is_additional_constraint",
        "rerun_requires_independent_binding",
        "source_version_drift_requires_reapproval",
        "grant_publisher_server_owned",
    ):
        assert grant[key] is True
    for key in (
        "cross_level_inheritance",
        "admin_bypass",
        "entity_scope_implies_all_runs",
        "future_run_auto_enrollment_allowed",
        "source_hash_is_authorization",
        "current_registry_rewrites_historical_scope",
    ):
        assert grant[key] is False
    assert grant["historical_runs"] == "EXPLICIT_APPROVED_EXACT_RUN_ALLOWLIST"
    assert grant["future_run_enrollment_policy"] == "PENDING_OWNER_DECISION"
    assert grant["required_exact_run_fields"] == [
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
    assert {
        "forecast_family",
        "target_season",
        "source_authority_version",
        "grant_revision",
        "organization_scope",
        "approval_reference",
    }.issubset(grant["scope_constraints"])


def test_authorization_before_read_and_after_in_flight_revocation() -> None:
    data = evidence()
    grant = data["resource_contract"]
    assert grant["order"] == [
        "AUTHENTICATE",
        "CAPABILITY_AND_ORGANIZATION_AND_EXACT_GRANT",
        "CANONICAL_READ_AND_IDENTITY_HASH_VERIFICATION",
        "EXISTING_SERVICE",
        "PRE_RESPONSE_PRINCIPAL_AND_GRANT_REVISION_RECHECK",
    ]
    for key in (
        "pre_response_grant_revision_recheck",
        "pre_response_principal_active_recheck",
        "in_flight_revocation_suppresses_sensitive_response",
        "no_unauthorized_existence_disclosure",
    ):
        assert grant[key] is True
    for key in (
        "unauthorized_business_reads_expected",
        "unauthorized_quality_reads_expected",
        "unauthorized_simulations_expected",
    ):
        assert grant[key] == 0
    assert grant["revocation_invalidates"] == [
        "CACHE",
        "CURSOR",
        "HANDOFF",
        "SELECTED_CONTEXT",
        "RELEVANT_SESSION",
    ]
    assert data["governance"]["pre_response_recheck_implemented"] is False


def test_mcp_replacement_gate_does_not_claim_user_delegation_pass() -> None:
    data = evidence()
    mcp = data["mcp_contract"]
    old = json.loads(
        (ROOT / "docs/v0-18/evidence/s1-simplified-local-auth-plan-r1.json").read_text()
    )
    assert mcp["tool_count"] == 8
    assert mcp["tool_names"] == old["runtime_and_scope_status"]["mcp_tool_names"]
    assert mcp["identity_mode"] == "SERVICE_ACCOUNT_ONLY"
    assert mcp["run_grants"] == "EXACT_RUN_GRANTS"
    assert mcp["quality_grants"] == "INDEPENDENT_QUALITY_GRANTS"
    assert mcp["business_payload_math_hash_unchanged"] is True
    assert mcp["replacement_gate"] == "SERVICE_ACCOUNT_EXACT_GRANT_SAFETY_ACCEPTANCE"
    assert mcp["replacement_gate_status"] == "PENDING_NOT_EXECUTED"
    assert mcp["original_delegation_gate_passed"] is False
    assert mcp["end_user_isolation_validated"] is False
    assert mcp["service_account_is_end_user"] is False
    assert mcp["end_user_delegation"] == "NOT_IMPLEMENTED_UNVERIFIED_EXCLUDED_FIRST_RELEASE"
    assert {
        "DENIAL_BEFORE_READ_AND_SIMULATION",
        "INDEPENDENT_QUALITY_GRANTS",
        "CANONICAL_HASH_PRE_RESPONSE_REVISION",
        "NO_LEGACY_BYPASS",
        "EIGHT_TOOLS_HTTP_PAYLOAD_HASH_PARITY",
    }.issubset(mcp["replacement_acceptance"])


def test_stage_dependencies_and_explicit_technical_revisions() -> None:
    data = evidence()
    original = json.loads((ROOT / "docs/v0-18/evidence/v0.18.0-scope-freeze-r1.json").read_text())
    assert data["stage_order"] == original["stage_order"]
    for stage, deps in DEPENDENCIES.items():
        current = data["stages"][stage]
        assert current["name"] == original["stages"][stage]["name"]
        assert current["depends_on"] == deps
        assert current["implementation_authorized"] is False
        if stage not in {"S1", "S3"}:
            assert deps == original["stages"][stage]["depends_on"]
    original_s1 = original["stages"]["S1"]["depends_on"]
    original_s3 = original["stages"]["S3"]["depends_on"]
    assert original_s1 == [
        "S0_FORMAL_COMPLETE",
        "OWNER_TRUSTED_ISSUER_AND_POLICY_PUBLISHER_DECISION",
    ]
    assert original_s3 == [
        "S1_FORMAL_COMPLETE",
        "S2_FORMAL_COMPLETE",
        "CLIENT_DELEGATION_PROTOCOL_COMPATIBILITY",
    ]
    revisions = {item["old"]: item["new"] for item in data["compatibility_revisions"]}
    assert revisions["OWNER_TRUSTED_ISSUER_AND_POLICY_PUBLISHER_DECISION"] == (
        "OWNER_LOCAL_ACCOUNT_AND_POLICY_PUBLISHER_DECISION"
    )
    assert revisions["CLIENT_DELEGATION_PROTOCOL_COMPATIBILITY"] == (
        "SERVICE_ACCOUNT_EXACT_GRANT_SAFETY_ACCEPTANCE"
    )
    assert revisions["USER_CLIENT_RUN_SCOPE_INTERSECTION"] == (
        "SERVICE_PRINCIPAL_CLIENT_BOUNDARY_EXACT_RUN_AND_QUALITY_GRANTS"
    )
    assert all(
        item["status"] == "PENDING_ADDENDUM_FORMAL_APPROVAL"
        for item in data["compatibility_revisions"]
    )


def test_addendum_is_not_formally_effective_or_runtime_permission() -> None:
    data = evidence()
    state = data["governance"]
    for key in (
        "owner_auth_direction_confirmed",
        "s0_original_formal_complete",
        "s1_preflight_formal_complete",
        "s0_addendum_draft_authorized",
        "s0_addendum_formal_approval_pending",
        "stop_after_draft_exact_head_ci",
    ):
        assert state[key] is True
    for key in (
        "addendum_effective",
        "s1_runtime_authorized",
        "s1_to_s6_implementation_authorized",
        "local_auth_implemented",
        "production_code_changed",
        "database_migration_created",
        "current_season_actual_accessed",
        "model_experiment_executed",
        "peak_business_started",
        "ready_authorized",
        "merge_authorized",
        "deploy_authorized",
        "tag_authorized",
        "release_authorized",
        "version_closeout_authorized",
    ):
        assert state[key] is False
    assert state["formal_effect_requires"] == [
        "INDEPENDENT_EXACT_HEAD_REVIEW",
        "OWNER_READY_MERGE_AUTHORIZATION",
        "ADDENDUM_MERGE",
        "SUCCESSFUL_POST_MERGE_MAIN_CI",
    ]
    assert state["production_readiness"] == "NOT_READY"
    preserved = data["preserved_contracts"]
    assert preserved["historical_sources_immutable"] is True
    assert preserved["original_allowed_paths_and_non_goals"] is True
    assert preserved["original_owner_gates"] is True
    assert preserved["legacy_routes_require_adaptation_or_network_isolation_before_pilot"] is True
    assert preserved["legacy_isolation_verified"] is False
    assert preserved["quality_roadmap_separate"] is True
    for key in (
        "point_is_proven_p50",
        "planning_bounds_proven_quantiles",
        "attribution_is_causal",
        "current_season_actual_available",
        "real_roi_validated",
    ):
        assert preserved[key] is False


def test_document_explains_scope_replacements_and_unimplemented_controls() -> None:
    document = (ROOT / DOC).read_text(encoding="utf-8")
    for text in (
        "逐项兼容与替代矩阵",
        "OWNER_TRUSTED_ISSUER_AND_POLICY_PUBLISHER_DECISION",
        "CLIENT_DELEGATION_PROTOCOL_COMPATIBILITY",
        "USER_CLIENT_RUN_SCOPE_INTERSECTION",
        "PRE_RESPONSE_GRANT_REVISION_RECHECK=true",
        "尚未实现",
        "FUTURE_RUN_AUTO_ENROLLMENT_ALLOWED=false",
        "PENDING_OWNER_DECISION",
        "OWNER_OPERATION_PLAN_REVIEW",
        "S0_ADDENDUM_FORMAL_APPROVAL_PENDING=true",
        "END_USER",
        "SERVICE_ACCOUNT",
        "ADMIN",
        "BUSINESS_USER",
    ):
        assert text in document
