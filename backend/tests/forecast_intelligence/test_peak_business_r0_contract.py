"""Offline contract checks for the Peak Business R0 design package.

The arithmetic helpers below are deliberately test-local synthetic examples;
they are not imported by production code and do not calculate business results.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_PATH = (
    ROOT / "docs/roadmap/peak-business/evidence/r0-metric-and-authority-contract-r1.json"
)


def load_evidence() -> dict[str, object]:
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def synthetic_daily_peak(values: list[Decimal]) -> tuple[int, Decimal]:
    """Return earliest 1-based index at the maximum for a SYNTHETIC curve."""
    maximum = max(values)
    return values.index(maximum) + 1, maximum


def synthetic_rolling7(dates: list[date], values: list[Decimal]) -> tuple[date, Decimal, int]:
    """Evaluate complete consecutive 7-calendar-day windows only."""
    assert len(dates) == len(values)
    assert all(
        current - previous == timedelta(days=1)
        for previous, current in zip(dates, dates[1:], strict=False)
    )
    if len(values) < 7:
        raise ValueError("NOT_COMPUTABLE_NO_COMPLETE_7DAY_WINDOW")
    windows = [sum(values[start : start + 7], Decimal(0)) for start in range(len(values) - 6)]
    best_value = max(windows)
    best_index = windows.index(best_value)
    return dates[best_index], best_value, len(windows)


def test_evidence_is_canonical_and_all_source_bytes_are_bound() -> None:
    raw = EVIDENCE_PATH.read_text(encoding="utf-8")
    evidence = load_evidence()
    canonical = json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    assert raw == canonical

    sources = evidence["source_evidence_sha256"]
    documents = evidence["document_sha256"]
    assert isinstance(sources, dict)
    assert isinstance(documents, dict)
    assert evidence["source_evidence_count"] == len(sources)
    for relative_path, expected_hash in {**sources, **documents}.items():
        path = ROOT / relative_path
        assert path.is_file(), relative_path
        assert sha256(path) == expected_hash, relative_path


def test_live_baseline_release_and_governance_snapshot_are_explicit() -> None:
    evidence = load_evidence()
    assert evidence["base_main_sha"] == "b7ae7b4d35f182d5505ff3ea3750c5de403b2b81"
    assert evidence["latest_formal_release"] == "v0.17.0"
    assert evidence["workflow_identifier"] == "PEAK_BUSINESS"
    assert evidence["formal_version_number"] is None
    assert evidence["formal_version_name"] is None

    live = evidence["live_preflight"]
    assert live["main_sha"] == evidence["base_main_sha"]
    assert live["latest_release"] == "v0.17.0"
    assert live["v018_s0_pr"] == 710
    assert live["v018_s0_formal_complete"] is True
    assert live["v018_s0_exact_head_ci"]["run_id"] == "38014489131"
    assert live["v018_s0_exact_head_ci"]["conclusion"] == "success"
    assert live["v018_s0_post_merge_ci_run_id"] == "38017386758"
    assert live["v018_s0_post_merge_ci"]["success_jobs"] == 4
    assert live["v018_s0_post_merge_ci"]["skipped_jobs"] == 8
    assert live["v018_s1_preflight_pr"] == 711
    assert live["v018_s1_preflight_formal_complete"] is True
    assert live["v018_s1_preflight_review_complete"] is True
    assert live["v018_s1_preflight_independent_review_result"] == "PASS"
    assert live["v018_s1_preflight_independent_review_state"] == "COMMENTED"
    assert live["v018_s1_implementation_formal_complete"] is False
    assert live["v018_s1_preflight_review_state"] == "COMMENTED"
    assert live["v018_s1_identity_implementation"] == "PAUSED_AND_UNAUTHORIZED"
    assert live["v018_s1_preflight_exact_head_ci"]["conclusion"] == "success"
    assert live["v018_s1_preflight_post_merge_ci"]["conclusion"] == "success"
    assert live["roadmap_reassessment_pr"] == 712
    assert live["roadmap_reassessment_merge_sha"] == evidence["base_main_sha"]
    assert live["roadmap_reassessment_pr_ci"]["success_jobs"] == 12
    assert live["roadmap_reassessment_post_merge_ci_run_id"] == "38034832975"
    assert live["roadmap_reassessment_post_merge_ci"]["success_jobs"] == 4
    assert live["roadmap_reassessment_post_merge_ci"]["skipped_jobs"] == 8

    governance = evidence["governance"]
    assert governance["v018_name_and_scope_preserved"] is True
    assert governance["v018_scope_amended"] is False
    assert governance["v018_s0_to_s6_superseded"] is False
    assert governance["identity_auth_implementation_paused"] is True
    assert governance["all_future_stages_authorized"] is False
    assert governance["ready_authorized"] is False
    assert governance["merge_authorized"] is False


def test_forecast_families_and_capacity_authorities_are_not_conflated() -> None:
    evidence = load_evidence()
    inventory = evidence["capability_inventory"]
    operational = inventory["operational_peak"]
    core = inventory["core_forecast"]
    actuals = inventory["historical_actual_peak_analytics"]
    v016 = inventory["v016_decision_support"]

    assert operational["forecast_family"] == "OPERATIONAL_PEAK_FORECAST_RUN_V1"
    assert operational["baseline_id"] == "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1"
    assert operational["policy_version"] == "OPERATIONAL_PEAK_POLICY_V1"
    assert operational["saved_h7_prefix"] is True
    assert operational["rolling7_peak_projection"] is False
    assert operational["factory_assignment_authority"] is False
    assert operational["factory_processing_capacity_authority"] is False
    assert operational["normal_business_run_discovery"] is False

    assert core["separate_forecast_family"] is True
    assert core["rolling7_metric_exists_for_its_own_curve"] is True
    assert core["effective_harvest_capacity_is_factory_processing_throughput"] is False
    assert core["results_reusable_for_operational_peak"] is False
    assert core["p50_p80_p90_schema_proves_calibration"] is False

    assert actuals["actual_fact_analysis_only"] is True
    assert actuals["forecast_metric_authority"] is False
    assert actuals["forecast_missing_days_may_be_zero_filled"] is False
    assert actuals["raw_actual_rows_accessed_in_this_task"] is False

    assert v016["explicit_capacity_scenarios_exist"] is True
    assert v016["canonical_factory_capacity_authority"] is False
    assert v016["real_company_cost_established"] is False
    assert v016["optimizer_or_automatic_action"] is False


def test_metric_contract_separates_prefix_peak_and_complete_rolling_windows() -> None:
    evidence = load_evidence()
    contract = evidence["metric_contract"]
    assert contract["h7_prefix"]["definition"] == "D1_THROUGH_D7_SUM"
    assert contract["h7_prefix"]["same_as_rolling7_max"] is False
    assert contract["rolling7_peak"]["full_15_day_candidate_window_count"] == 9
    assert contract["rolling7_peak"]["tie_break"] == "EARLIEST_START_DATE"
    assert contract["rolling7_peak"]["missing_day_fill"] == "FORBIDDEN"
    assert contract["daily_peak"]["tie_break"] == "EARLIEST_DATE"
    assert contract["daily_peak"]["sum_of_child_peaks_allowed"] is False
    assert contract["completeness"]["missing_to_zero"] is False
    assert contract["completeness"]["cross_run_or_cross_family_composition"] is False
    assert contract["completeness"]["identity_or_source_hash_mismatch"] == "AUTHORITY_MISMATCH"

    values = [Decimal(value) for value in [10, 10, 10, 10, 10, 10, 10, 100, 100, 0, 0, 0, 0, 0, 0]]
    dates = [date(2026, 1, 1) + timedelta(days=index) for index in range(len(values))]
    h7_prefix = sum(values[:7], Decimal(0))
    start, rolling7, candidate_count = synthetic_rolling7(dates, values)
    assert h7_prefix == Decimal(70)
    assert rolling7 == Decimal(250)
    assert start == dates[2]
    assert candidate_count == 9

    peak_index, peak_value = synthetic_daily_peak([Decimal(5), Decimal(9), Decimal(9)])
    assert (peak_index, peak_value) == (2, Decimal(9))
    zero_peak_index, zero_peak_value = synthetic_daily_peak([Decimal(0), Decimal(0)])
    assert (zero_peak_index, zero_peak_value) == (1, Decimal(0))
    assert contract["daily_peak"]["zero_curve_event_status"] == "NO_POSITIVE_DEMAND"


def test_incomplete_windows_hierarchy_and_pending_thresholds_fail_closed() -> None:
    evidence = load_evidence()
    contract = evidence["metric_contract"]
    assert contract["rolling7_peak"]["incomplete_declared_range"] == "PARTIAL_NOT_GLOBAL"
    with pytest.raises(ValueError, match="NOT_COMPUTABLE_NO_COMPLETE_7DAY_WINDOW"):
        synthetic_rolling7(
            [date(2026, 1, 1) + timedelta(days=index) for index in range(6)],
            [Decimal(1)] * 6,
        )
    with pytest.raises(AssertionError):
        synthetic_rolling7(
            [date(2026, 1, 1), date(2026, 1, 3)]
            + [date(2026, 1, 4) + timedelta(days=index) for index in range(5)],
            [Decimal(1)] * 7,
        )

    a = [Decimal(10), Decimal(0)]
    b = [Decimal(0), Decimal(10)]
    aggregate = [left + right for left, right in zip(a, b, strict=True)]
    assert synthetic_daily_peak(aggregate)[1] == Decimal(10)
    assert sum(synthetic_daily_peak(series)[1] for series in (a, b)) == Decimal(20)

    assert contract["consecutive_high_period"]["status"] == "NOT_AVAILABLE_THRESHOLD_UNAPPROVED"
    assert contract["concentration"]["zero_denominator"] == "NOT_COMPUTABLE_ZERO_DENOMINATOR"
    assert evidence["synthetic_contract_examples"]["incomplete_calendar_is_not_filled"] is True


def test_factory_and_report_authority_are_explicitly_bounded() -> None:
    evidence = load_evidence()
    factory = evidence["factory_authority"]
    assert factory["base_to_factory_assignment"] == "NOT_AVAILABLE"
    assert factory["factory_processing_capacity"] == "NOT_AVAILABLE"
    assert factory["allocation_authority"] == "NOT_AVAILABLE"
    assert factory["effective_harvest_capacity_is_processing_capacity"] is False
    assert factory["user_entered_s2_capacity_is_verified_factory_capacity"] is False
    multi_factory = factory["multi_factory_assignment"]
    assert multi_factory["allowed_only_with_explicit_effective_dated_assignments"] is True
    assert multi_factory["allocation_modes"] == ["SHARE", "EXPLICIT_QUANTITY"]
    assert multi_factory["share_conservation_required"] is True
    assert multi_factory["implicit_residual_distribution_allowed"] is False

    example = load_evidence()["synthetic_contract_examples"]
    assert example["multi_factory_without_authorized_mapping_status"] == "NOT_AVAILABLE"
    assert example["incomplete_child_coverage_status"] == "INCOMPLETE_CHILD_COVERAGE"
    share_example = example["multi_factory_with_explicit_share_example"]
    assert share_example["synthetic"] is True
    assert share_example["implies_real_assignment"] is False
    assert sum((Decimal(value) for value in share_example["shares"]), Decimal(0)) == Decimal("1.0")
    assert example["source_hash_or_run_identity_mismatch_status"] == "AUTHORITY_MISMATCH"

    report = evidence["report_provenance"]
    assert report["server_projection_is_authority"] is True
    assert report["client_business_math_allowed"] is False
    assert report["report_generated_at_is_forecast_issuance_time"] is False
    assert report["unavailable_sections_may_be_filled_by_report"] is False


def test_owner_decisions_and_future_stages_remain_unapproved() -> None:
    evidence = load_evidence()
    decisions = evidence["owner_decisions"]
    assert [decision["id"] for decision in decisions] == [
        f"DECISION-{index:02d}" for index in range(1, 9)
    ]
    assert all(decision["status"] == "PENDING_OWNER_DECISION" for decision in decisions)

    proposal = evidence["future_stage_proposal"]
    assert proposal["formal_version_approved"] is False
    assert proposal["stage_ids"] == [f"PB-S{index}" for index in range(7)]
    assert all(stage["implementation_authorized"] is False for stage in proposal["stages"].values())
    assert proposal["previous_stage_pass_authorizes_next"] is False


def test_historical_quality_is_m1_retrospective_not_operational_peak_accuracy() -> None:
    quality = load_evidence()["quality_research_boundary"]
    assert quality["model_id"] == "V0_15_S5_M1_RIDGE"
    assert quality["split"] == "EXPOSED_OOT"
    assert quality["season"] == "2025-2026"
    assert Decimal(quality["daily_wape_h7"]).quantize(Decimal("0.0000000001")) == Decimal(
        "0.4249224043"
    )
    assert Decimal(quality["daily_wape_h15"]).quantize(Decimal("0.0000000001")) == Decimal(
        "0.4506174628"
    )
    assert quality["interval_coverage_h7_h15_under_nominal"] is True
    coverage = quality["interval_coverage_observations"]
    assert coverage["H7"]["candidate_rows"] == 61_425
    assert coverage["H7"]["computable_rows"] == 60_060
    assert coverage["H7"]["not_computable_rows"] == 1_365
    assert coverage["H15"]["candidate_rows"] == 131_625
    assert coverage["H15"]["computable_rows"] == 126_360
    assert coverage["H15"]["not_computable_rows"] == 5_265
    for horizon in coverage.values():
        for metric in ("PI80", "PI90", "UPPER80", "UPPER90"):
            observation = horizon[metric]
            assert Decimal(observation["empirical_coverage"]) < Decimal(
                observation["nominal_coverage"]
            )
    assert quality["strict_pit"] is False
    assert quality["historical_actual_available_at_proven"] is False
    assert quality["retrospective_authority_used"] is True
    assert quality["prospective_accuracy_validated"] is False
    assert quality["operational_peak_accuracy_proven_by_m1"] is False
    assert quality["new_training_refit_tuning_scoring_or_calibration"] is False
    assert quality["historical_row_or_actual_data_access"] is False


def test_execution_boundary_prohibits_production_and_model_work() -> None:
    boundaries = load_evidence()["execution_boundaries"]
    assert all(value is False for value in boundaries.values())
