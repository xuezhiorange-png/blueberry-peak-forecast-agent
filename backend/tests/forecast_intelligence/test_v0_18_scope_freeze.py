"""Offline design contracts; no service, network, database or experiment execution."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.contract]
ROOT = Path(__file__).resolve().parents[3]
SCOPE = "docs/v0-18/evidence/v0.18.0-scope-freeze-r1.json"
QUALITY = "docs/v0-18/evidence/forecast-quality-roadmap-r1.json"
BASE = "1b218edc74ff29091c07607ddbcdba0c10577398"
IDENTITY = [
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
PAGES = ["OVERVIEW", "FORECAST", "ATTRIBUTION", "CAPACITY_SIMULATOR", "QUALITY"]
TOOLS = [
    "get_forecast_overview",
    "get_forecast_curve",
    "get_hierarchical_forecast",
    "get_forecast_uncertainty",
    "get_forecast_attribution",
    "get_forecast_quality",
    "simulate_capacity",
    "compare_capacity_scenarios",
]


def raw(path):
    relative = Path(path)
    assert not relative.is_absolute() and ".." not in relative.parts
    assert relative.parts[0] in {"docs", "backend"}
    return (ROOT / relative).read_bytes()


def load(path):
    return json.loads(raw(path))


def canonical(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


@pytest.mark.parametrize("path", [SCOPE, QUALITY])
def test_canonical_and_public_source_bindings(path):
    data = load(path)
    assert raw(path) == canonical(data)
    assert canonical(dict(reversed(list(data.items())))) == raw(path)
    sources = data["source_evidence_sha256"]
    assert data["source_evidence_count"] == len(sources)
    assert len(sources) == 23
    for name, expected in sources.items():
        assert hashlib.sha256(raw(name)).hexdigest() == expected, name
    for name, expected in data["document_sha256"].items():
        assert hashlib.sha256(raw(name)).hexdigest() == expected, name
    # Independent immutable anchors, not a receipt self-assertion.
    assert (
        sources["docs/v0-17/evidence/v0.17.0-version-closeout-r1.json"]
        == "8e5185a139ec106edb80393db2047de6398300e1035eeee2b7b85167ba017b14"
    )
    assert (
        sources["docs/v0-15/evidence/harvest-state-incremental-value-r1/exposed-oot-metrics.json"]
        == "02319ad9e14bcc855dafa7937c3ba89f373faf9098be20c5f47b9ae1d5d26ba7"
    )
    assert (
        sources["docs/v0-16/evidence/uncertainty-conformal-calibration-r1/coverage-summary-r1.json"]
        == "1586144b596e315ef627ee1874a1104229337bae96a86fd4e26d066c55dadd17"
    )


def test_version_and_live_preflight_snapshot():
    data = load(SCOPE)
    assert data["task_id"] == "V0_18_S0_BUSINESS_USABILITY_SCOPE_FREEZE_R1"
    assert data["version"] == "0.18.0"
    assert data["version_name"] == "BUSINESS_USABILITY_AND_SAFE_PILOT_FOUNDATION"
    assert data["base_main_sha"] == BASE
    live = data["live_preflight"]
    assert live["latest_formal_release"] == "v0.17.0"
    assert live["release_id"] == 408106332
    assert live["tag_object_sha"] == "3442d9fd8dbecf14eb34e8409d79b063a30af52b"
    assert live["tag_target_sha"] == BASE
    assert live["release_draft"] is live["release_prerelease"] is False
    assert live["parallel_v018_branches"] == live["parallel_v018_prs"] == 0
    assert live["initial_worktree_clean"] is True


def test_stage_dependency_scope_and_separate_authorization():
    data = load(SCOPE)
    assert data["stage_order"] == ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "VERSION_CLOSEOUT"]
    stages = data["stages"]
    assert stages["S1"]["name"] == "TRUSTED_IDENTITY_AND_RESOURCE_AUTHORIZATION"
    assert stages["S2"]["depends_on"] == ["S1_FORMAL_COMPLETE"]
    for i in range(1, 7):
        stage = stages[f"S{i}"]
        assert stage["implementation_authorized"] is False
        assert stage["allowed_paths"] and stage["acceptance"] and stage["excluded"]
        assert stage["owner_gate"] == "SEPARATE_IMPLEMENTATION_THEN_REVIEW_READY_MERGE_MAIN_CI"
    assert stages["S5"]["deployment_authorized"] is False
    assert data["quality_research_is_v018_stage"] is False


def test_trusted_identity_and_auth_before_sensitive_reads():
    auth = load(SCOPE)["authorization_architecture"]
    assert auth["principal_types"] == ["END_USER", "SERVICE_ACCOUNT"]
    assert auth["identity_key"] == ["trusted_issuer", "subject"]
    assert auth["client_actor_trusted"] is auth["service_account_is_end_user"] is False
    assert auth["order"] == [
        "AUTHENTICATE",
        "CAPABILITY",
        "RESOURCE_GRANT",
        "CANONICAL_READ",
        "RECHECK_HASH_AND_GRANT",
        "SERVICE",
    ]
    assert auth["unauthorized_sensitive_read_count"] == 0
    assert auth["unauthorized_existence_disclosure"] is False
    assert auth["aggregate_grant_independent"] is auth["quality_grant_independent"] is True
    assert auth["current_registry_rewrites_saved_hierarchy"] is False
    assert auth["delegation_effective_scope"] == "INTERSECTION_USER_CLIENT_AND_EXACT_RUN_GRANTS"
    assert auth["provider_configured"] is auth["production_acl_validated"] is False
    assert auth["revocation"] == "RECHECK_EACH_REQUEST_INVALIDATE_CURSOR_HANDOFF_AND_CACHE"


def test_discovery_filter_cursor_and_reauthorization():
    discovery = load(SCOPE)["saved_run_discovery_contract"]
    assert discovery["implemented"] is False
    assert discovery["identity_fields"] == IDENTITY
    assert discovery["authorization_filter_before_pagination"] is True
    assert discovery["global_total_exposed"] is discovery["global_latest_allowed"] is False
    assert discovery["sort"] == [
        "origin_date_DESC",
        "source_kind_ASC",
        "forecast_family_ASC",
        "run_id_DESC",
        "entity_id_ASC",
        "source_result_hash_ASC",
    ]
    assert discovery["limits"] == {
        "default_page_size": 20,
        "max_page_size": 100,
        "max_cursor_bytes": 2048,
        "cursor_ttl_seconds": 900,
        "handoff_ttl_seconds": 300,
    }
    assert set(discovery["cursor_binding"]) == {
        "principal",
        "client",
        "grant_revision",
        "catalog_snapshot",
        "filters",
        "sort",
        "last_key",
        "expires_at",
    }
    assert discovery["handoff_is_authorization"] is False
    assert discovery["handoff_validation"] == [
        "SERVER_SIGNATURE",
        "PRINCIPAL_CLIENT_BINDING",
        "EXPIRY",
        "GRANT_REVISION",
        "EXACT_IDENTITY_AND_HASH",
        "REAUTHORIZE",
        "CANONICAL_READ",
    ]
    assert discovery["source_hash_changed"] == "409_RESELECT_NO_FALLBACK"
    assert discovery["rerun_auto_replacement"] is False


@pytest.mark.parametrize("status", ["401", "403", "404", "409", "413", "422", "503"])
def test_error_contract_and_future_negative_acceptance(status):
    data = load(SCOPE)
    assert data["error_contract"][status]
    assert data["acceptance_matrix"]["http_statuses"] == [401, 403, 404, 409, 413, 422, 503]
    assert data["acceptance_matrix"]["execution_status"] == "PLANNED_NOT_RUN"
    assert (
        data["error_contract"]["403"]
        == "SAME_DENIAL_FOR_NONEXISTENT_OR_UNGRANTED_RESOURCE_BEFORE_LOOKUP"
    )
    assert data["error_contract"]["404"] == "ONLY_AFTER_VALID_EXACT_RESOURCE_GRANT"


def test_existing_products_and_unbound_authority_preserved():
    product = load(SCOPE)["product_contract"]
    assert product["pages"] == PAGES and product["mcp_tools"] == TOOLS
    assert product["hierarchy"] == ["COMPANY", "REGION", "BASE"]
    assert product["one_service_layer"] is True
    assert product["client_business_math"] is product["ninth_mcp_tool"] is False
    assert product["mcp_discovery"] == "AUTHORIZED_HTTP_HANDOFF_NO_NEW_TOOL"
    assert product["unavailable"] == {
        key: "NOT_AVAILABLE" for key in ["UPPER80", "UPPER90", "ATTRIBUTION", "CHILD_CONTRIBUTION"]
    }
    assert product["point_fallback"] is product["missing_to_zero"] is False
    assert product["loss_unit"] == "SYNTHETIC_LOSS_UNIT"
    assert product["scenario_ranking"] == "SERVER_CONDITIONAL_ORDER_NOT_OPTIMIZATION"
    assert product["h7"] == "D1_THROUGH_D7_PREFIX"


def test_safe_pilot_is_synthetic_and_requires_separate_deployment():
    pilot = load(SCOPE)["safe_pilot_architecture"]
    assert pilot["dataset"] == "ISOLATED_SYNTHETIC_CANONICAL_SAVED_RUNS"
    assert pilot["production_database_connected"] is pilot["deployed"] is False
    assert pilot["legacy_access"] == "DEFAULT_DENY_SEPARATE_TRUST_DOMAIN_TEST_ALL_OLD_PATHS"
    assert pilot["secrets"] == "SERVER_SECRET_STORE_NO_BUNDLE_NO_LOG_NO_REPOSITORY"
    assert set(pilot["required_drills"]) >= {
        "CREDENTIAL_ROTATION",
        "GRANT_REVOCATION",
        "BACKUP_RESTORE_HASH_PARITY",
        "ROLLBACK_REVOKE_ACCESS",
        "CROSS_PRINCIPAL_DENIAL",
        "AUDIT_REDACTION",
    }
    assert pilot["rpo"] is pilot["rto"] is None
    assert pilot["owner_deployment_gate_required"] is True


@pytest.mark.parametrize("path", [SCOPE, QUALITY])
def test_current_authorizations_and_no_experiments(path):
    data = load(path)
    assert data["governance"]["owner_authorized"] is True
    assert data["governance"]["s0_formal_complete"] is False
    for key in [
        "s1_to_s6_authorized",
        "production_code_authorized",
        "model_training_authorized",
        "current_season_actual_access_authorized",
        "ready_authorized",
        "merge_authorized",
        "deploy_authorized",
        "tag_authorized",
        "release_authorized",
    ]:
        assert data["governance"][key] is False
    assert data["governance"]["stop_after_draft_exact_head_ci"] is True
    for value in data["execution_boundaries"].values():
        assert value is False
    assert data["production_readiness"] == "NOT_READY"


def test_quality_baseline_exact_original_values_and_denominators():
    data = load(QUALITY)
    original = load(
        "docs/v0-15/evidence/harvest-state-incremental-value-r1/exposed-oot-metrics.json"
    )["M1"]
    point = load("docs/v0-16/evidence/forecastops-monitoring-r1/point-quality-summary-r1.json")[
        "horizons"
    ]
    baseline = data["frozen_baseline"]
    assert baseline["model_id"] == "V0_15_S5_M1_RIDGE"
    assert baseline["split"] == "EXPOSED_OOT" and baseline["season"] == "2025-2026"
    for h in ["H7", "H15"]:
        assert baseline["daily_wape"][h] == original[f"{h}_DAILY_WAPE"] == point[h]["daily_wape"]
    assert baseline["daily_wape"]["H7"] == "0.42492240428114891228797259913152412125067904816858"
    assert baseline["daily_wape"]["H15"] == "0.45061746284274714676741860562477726865031957501063"
    assert baseline["origin_count"] == 8775 and baseline["target_row_count"] == 131625
    assert baseline["strict_pit"] is baseline["historical_available_at_proven"] is False
    assert baseline["operational_peak_is_m1"] is False
    coverage = load(
        "docs/v0-16/evidence/uncertainty-conformal-calibration-r1/coverage-summary-r1.json"
    )
    assert baseline["coverage"] == coverage
    for horizon in coverage.values():
        for record in horizon.values():
            assert Decimal(record["empirical_coverage"]) < Decimal(record["nominal_coverage"])
            assert (
                record["candidate_row_count"]
                == record["computable_row_count"] + record["not_computable_row_count"]
            )
    assert baseline["peak_metrics"] == {
        k: original[k]
        for k in [
            "SINGLE_DAY_PEAK_DATE_MAE_DAYS",
            "SINGLE_DAY_PEAK_QUANTITY_MAE_KG",
            "ROLLING7_PEAK_START_DATE_MAE_DAYS",
            "ROLLING7_PEAK_QUANTITY_MAE_KG",
        ]
    }


def test_quality_six_tracks_protocol_leakage_and_owner_thresholds():
    data = load(QUALITY)
    assert list(data["tracks"]) == ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]
    assert all(
        track["execution_authorized"] is False and track["deliverables"] and track["entry_gate"]
        for track in data["tracks"].values()
    )
    assert data["new_accuracy_target"] is data["business_threshold"] is None
    assert data["threshold_authority"] == "FUTURE_OWNER_DECISION_BEFORE_EVALUATION"
    assert data["tracks"]["Q1"]["paired_key"] == [
        "model_family",
        "fit_state",
        "base_scope",
        "origin",
        "lead",
        "target_date",
        "label_authority",
    ]
    assert (
        data["tracks"]["Q2"]["window_policy"]
        == "SAME_COMPLETE_D1_D15_EARLIEST_TIE_ROLLING7_COMPLETE_7_DAYS"
    )
    assert data["tracks"]["Q3"]["coverage_grain"] == "DAILY_TARGET_ROWS_NOT_CUMULATIVE_INTERVAL"
    assert data["tracks"]["Q4"]["required_receipts"] == [
        "FORECAST_ORIGIN",
        "SOURCE_AVAILABLE_AT",
        "INGESTED_AT",
        "AS_ISSUED_AT",
        "MODEL_AND_INPUT_SEAL",
        "ACTUAL_AVAILABLE_AT",
        "SCORING_CUTOFF",
    ]
    assert (
        data["tracks"]["Q5"]["random_adjacent_split_allowed"]
        is data["tracks"]["Q5"]["post_holdout_tuning_allowed"]
        is False
    )
    assert data["tracks"]["Q6"]["actual_access_requires_separate_owner_authorization"] is True
    assert data["tracks"]["Q6"]["promotion_automatic"] is False


def test_documents_cover_design_not_existing_runtime_claims():
    data = load(SCOPE)
    assert len(data["document_sha256"]) == 3
    docs = "\n".join(raw(path).decode() for path in data["document_sha256"])
    for token in [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5",
        "S6",
        "NOT_AVAILABLE",
        "NOT_READY",
        "available_at",
        "EXPOSED_OOT",
        "409",
        "分页",
        "回滚",
        "独立授权",
    ]:
        assert token in docs
    assert load(QUALITY)["source_evidence_sha256"] == data["source_evidence_sha256"]
    old = load("docs/v0-17/evidence/v0.17.0-version-closeout-r1.json")
    assert old["governance"]["v0_17_version_complete"] is False
