"""Offline contracts for the V0.18 roadmap reassessment; no network or data access."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.contract]
ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_PATH = "docs/v0-18/evidence/v0.18-roadmap-reassessment-r1.json"
DOC_PATH = "docs/v0-18/v0.18-roadmap-reassessment-r1.md"
BASE_SHA = "a2af2f246d2f4a16a1c6be514f004167d80f5b1e"


def raw(path: str) -> bytes:
    relative = Path(path)
    assert not relative.is_absolute()
    assert ".." not in relative.parts
    assert relative.parts[0] in {"backend", "docs", "frontend"}
    return (ROOT / relative).read_bytes()


def load(path: str) -> dict[str, Any]:
    return json.loads(raw(path))


def canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def test_evidence_is_canonical_and_all_public_sources_match() -> None:
    evidence = load(EVIDENCE_PATH)
    assert raw(EVIDENCE_PATH) == canonical(evidence)
    assert evidence["base_main_sha"] == BASE_SHA

    sources = evidence["source_evidence_sha256"]
    assert evidence["source_evidence_count"] == len(sources) == 58
    for path, expected in sources.items():
        assert len(expected) == 64
        assert hashlib.sha256(raw(path)).hexdigest() == expected, path

    document_hash = evidence["document_sha256"][DOC_PATH]
    assert hashlib.sha256(raw(DOC_PATH)).hexdigest() == document_hash


def test_live_release_and_formal_s0_s1_preflight_are_bound_to_base() -> None:
    evidence = load(EVIDENCE_PATH)
    live = evidence["live_preflight"]
    assert live["main_sha"] == BASE_SHA
    assert live["latest_formal_release"] == "v0.17.0"
    assert live["latest_release_draft"] is False
    assert live["latest_release_prerelease"] is False
    assert live["parallel_v018_roadmap_pr_found"] is False

    s0 = live["s0"]
    assert s0["pr_number"] == 710
    assert s0["formal_complete_confirmed"] is True
    assert s0["pr_base_sha"] == "1b218edc74ff29091c07607ddbcdba0c10577398"
    assert s0["merge_commit_sha"] == "52b5a80f89c59130917b29c9097d63076eab4acb"
    assert s0["merge_parents"] == [s0["pr_base_sha"], s0["pr_head_sha"]]
    assert s0["exact_head_pr_ci_conclusion"] == "success"
    assert s0["exact_head_pr_ci_jobs"] == "12_SUCCESS_0_SKIPPED"
    assert s0["post_merge_main_ci_head_sha"] == s0["merge_commit_sha"]
    assert s0["post_merge_main_ci_conclusion"] == "success"
    assert s0["post_merge_main_ci_jobs"] == "4_SUCCESS_8_WORKFLOW_SKIPPED"

    s1 = live["s1_preflight"]
    assert s1["pr_number"] == 711
    assert s1["formal_preflight_complete_confirmed"] is True
    assert s1["implementation_authorized"] is False
    assert s1["pr_base_sha"] == s0["merge_commit_sha"]
    assert s1["merge_commit_sha"] == BASE_SHA
    assert s1["merge_parents"] == [s1["pr_base_sha"], s1["pr_head_sha"]]
    assert s1["post_merge_main_ci_head_sha"] == BASE_SHA
    assert s1["post_merge_main_ci_conclusion"] == "success"
    assert s1["post_merge_main_ci_jobs"] == "4_SUCCESS_8_WORKFLOW_SKIPPED"
    assert s1["owner_decisions_pending"] == [
        "DECISION-01",
        "DECISION-02",
        "DECISION-03",
        "DECISION-04",
        "DECISION-05",
        "DECISION-06",
    ]


def test_version_scope_is_preserved_and_identity_implementation_remains_paused() -> None:
    evidence = load(EVIDENCE_PATH)
    scope = evidence["current_version_scope"]
    assert scope["version"] == "0.18.0"
    assert scope["version_name"] == "BUSINESS_USABILITY_AND_SAFE_PILOT_FOUNDATION"
    assert scope["preserved"] is True
    assert scope["scope_amendment_recommended"] is False
    assert scope["historical_s0_s6_declared_superseded"] is False
    assert scope["s0_formal_complete"] is True
    assert scope["s1_preflight_formal_complete"] is True
    assert scope["s1_identity_auth_implementation_paused"] is True
    assert scope["s1_implementation_authorized"] is False

    recommendation = evidence["governance_recommendation"]
    assert recommendation["peak_business_capability_governance"] == (
        "SEPARATE_FUTURE_OWNER_APPROVED_VERSION_PROPOSAL"
    )
    assert recommendation["future_version_number"] is None
    assert recommendation["future_version_name"] is None
    assert recommendation["future_version_status"] == "PENDING_OWNER_DECISION"
    assert recommendation["no_stage_in_this_roadmap_is_authorized"] is True


def test_operational_peak_core_forecast_and_m1_authorities_are_not_conflated() -> None:
    evidence = load(EVIDENCE_PATH)
    inventory = evidence["capability_inventory"]
    operational = inventory["operational_peak"]
    core = inventory["core_forecast"]

    assert operational["family"] == "OPERATIONAL_PEAK_FORECAST_RUN_V1"
    assert operational["saved_curve_single_day_peak"] is True
    assert operational["saved_h7_h15_prefixes"] is True
    assert operational["rolling_seven_maximum_contract"] is False
    assert operational["consecutive_high_period_contract"] is False
    assert operational["factory_assignment_contract"] is False
    assert operational["processing_capacity_contract"] is False
    assert operational["run_bound_upper80_authority"] is False
    assert operational["run_bound_upper90_authority"] is False
    assert operational["run_bound_m1_attribution_authority"] is False

    assert core["persisted_domain_and_cli_lane_exists"] is True
    assert core["destination_factory_scoped_run_exists_in_code"] is True
    assert core["single_day_and_sustained_seven_day_metrics_exist"] is True
    assert core["effective_harvest_capacity_is_processing_throughput"] is False
    assert core["destination_factory_to_operational_peak_base_mapping_proven"] is False
    assert core["forecast_intelligence_http_exposed"] is False
    assert core["forecast_intelligence_mcp_exposed"] is False
    assert core["forecast_intelligence_dashboard_exposed"] is False
    assert core["quantile_types_prove_calibration"] is False

    quality = evidence["quality_boundaries"]
    assert quality["m1_model_id"] == "V0_15_S5_M1_RIDGE"
    assert quality["operational_peak_model_family"] == operational["family"]
    assert quality["m1_peak_metrics_are_operational_peak_accuracy"] is False
    assert quality["strict_pit"] is False
    assert quality["historical_available_at_proven"] is False
    assert quality["retrospective_authority_used"] is True
    assert quality["prospective_accuracy_validated"] is False
    assert quality["new_accuracy_target"] is None
    assert quality["business_error_threshold"] is None
    assert quality["peak_date_tolerance_days"] is None
    assert quality["frozen_coverage_observation"] == "UNDER_NOMINAL"
    frozen = load("docs/v0-18/evidence/forecast-quality-roadmap-r1.json")["frozen_baseline"]
    assert quality["m1_h7_daily_wape"] == frozen["daily_wape"]["H7"]
    assert quality["m1_h15_daily_wape"] == frozen["daily_wape"]["H15"]
    assert (
        quality["m1_single_day_peak_date_mae_days"]
        == frozen["peak_metrics"]["SINGLE_DAY_PEAK_DATE_MAE_DAYS"]
    )
    assert (
        quality["m1_single_day_peak_quantity_mae_kg"]
        == frozen["peak_metrics"]["SINGLE_DAY_PEAK_QUANTITY_MAE_KG"]
    )
    assert (
        quality["m1_rolling7_peak_start_date_mae_days"]
        == frozen["peak_metrics"]["ROLLING7_PEAK_START_DATE_MAE_DAYS"]
    )
    assert (
        quality["m1_rolling7_peak_quantity_mae_kg"]
        == frozen["peak_metrics"]["ROLLING7_PEAK_QUANTITY_MAE_KG"]
    )


def test_priority_stages_have_authority_dependencies_and_acceptance() -> None:
    evidence = load(EVIDENCE_PATH)
    stages = evidence["roadmap_stages"]
    assert [stage["stage_id"] for stage in stages] == [
        "R0",
        "R1",
        "R2",
        "R3",
        "R4",
        "R5",
        "R6",
    ]
    required = {
        "goal",
        "existing_capability_and_gap",
        "input_authority",
        "deliverables",
        "dependencies",
        "acceptance",
        "authorization_required",
        "expected_modules",
        "non_goals",
    }
    for stage in stages:
        assert required <= stage.keys()
        assert stage["input_authority"]
        assert stage["acceptance"]
        assert stage["authorization_required"]
        assert stage["non_goals"]

    by_id = {stage["stage_id"]: stage for stage in stages}
    assert "R1_FORMAL_COMPLETE" in by_id["R2"]["dependencies"]
    assert "R0" in by_id["R3"]["dependencies"]
    assert "R4_FOR_FACTORY_PRESENTATION" in by_id["R5"]["dependencies"]
    assert "HARVEST_CAPACITY_NOT_RELABELLED_AS_PROCESSING_CAPACITY" in by_id["R4"]["acceptance"]
    assert by_id["R1"]["authorization_required"] == "CURRENTLY_PAUSED_AND_UNAUTHORIZED"

    quality_stages = evidence["quality_research_stages"]
    assert [stage["stage_id"] for stage in quality_stages] == [
        "Q1",
        "Q2",
        "Q3",
        "Q4",
        "Q5",
        "Q6",
    ]
    assert all(stage["authorization_required"] for stage in quality_stages)
    assert all(stage["input_authority"] for stage in quality_stages)


def test_data_classification_and_non_execution_boundaries_remain_fail_closed() -> None:
    evidence = load(EVIDENCE_PATH)
    classification = evidence["classification"]
    assert (
        "OPERATIONAL_PEAK_HISTORICAL_SCORING"
        in classification["requires_separate_historical_research_data_authorization"]
    )
    assert (
        "AUTHORITATIVE_BASE_FACTORY_ASSIGNMENT"
        in classification["must_wait_for_authorized_real_operational_data"]
    )
    assert (
        "TRACEABLE_REPORT_TEMPLATE_FROM_AUTHORIZED_SAVED_RESPONSE"
        in classification["designable_without_new_business_data"]
    )

    for boundary, value in evidence["execution_boundaries"].items():
        assert value is False, boundary

    assert evidence["quality_boundaries"]["current_season_actual_available"] is False
    assert evidence["quality_boundaries"]["historical_research_execution_authorized"] is False
    assert evidence["quality_boundaries"]["prospective_scoring_authorized"] is False
