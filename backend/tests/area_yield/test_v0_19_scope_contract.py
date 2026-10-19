"""V0.19 S0 public-file contracts only: no database, labels, fitting or scoring."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.contract]
ROOT = Path(__file__).resolve().parents[3]
BASE = "b6ac2e658edbace357c575bb42ee46b03bb863b9"
EVIDENCE = ROOT / "docs/v0-19/evidence/v0.19.0-scope-freeze-r1.json"
DOCUMENT = "docs/v0-19/v0.19.0-version-plan-and-scope-freeze.md"
DATA = json.loads(EVIDENCE.read_bytes())
NAMES = [
    "VERSION_SCOPE_FREEZE",
    "MODEL_BASELINE_AND_PEAK_ERROR_PROTOCOL",
    "DAILY_CURVE_TEMPORAL_RESOLUTION_CANDIDATE",
    "CONTROLLED_TEMPORAL_MODEL_VALIDATION",
    "AGRONOMIC_FEATURE_VALUE_AND_RESEARCH_CLOSEOUT",
]
METRICS = [
    "SEASON_TOTAL_WAPE",
    "DAILY_WAPE",
    "DAILY_MAE",
    "SINGLE_DAY_PEAK_DATE_MAE",
    "SINGLE_DAY_PEAK_QUANTITY_MAE",
    "ROLLING_7DAY_PEAK_START_MAE",
    "ROLLING_7DAY_PEAK_QUANTITY_MAE",
    "BASE_BREADTH",
    "SAMPLE_COVERAGE",
    "NOT_COMPUTABLE_COUNT",
]


def source_bytes(path):
    relative = Path(path)
    assert not relative.is_absolute() and ".." not in relative.parts
    assert relative.parts[0] in {"docs", "backend"}
    if path == "backend/app/forecast_quality/operational_peak.py":
        # Pin the delivered historical algorithm, not every future working-tree version.
        return subprocess.run(
            ["git", "show", f"{BASE}:{path}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
    return (ROOT / relative).read_bytes()


def test_version_identity_release_and_canonical_json():
    assert DATA["task_id"] == "V0_19_VERSION_SCOPE_AND_TASK_FREEZE_R1"
    assert DATA["version"] == "0.19.0"
    assert DATA["version_name"] == "HARVEST_CURVE_AND_PEAK_TIMING_ALGORITHM_RESEARCH"
    assert DATA["version_name_cn"] == "蓝莓采收曲线与高峰时间预测算法研究版"
    assert DATA["release_class"] == "ALGORITHM_RESEARCH"
    assert DATA["base_main_sha"] == DATA["source_commit"] == BASE
    assert (
        EVIDENCE.read_bytes()
        == (
            json.dumps(DATA, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
        ).encode()
    )
    live = DATA["live_preflight"]
    assert live["latest_formal_release"] == "v0.18.0"
    assert live["release_id"] == 416386990
    assert live["release_draft"] is live["release_prerelease"] is False
    assert live["parallel_v019_open_pr_count"] == 0
    assert live["v019_implementation_approval_found"] is False
    assert live["initial_worktree_clean"] is live["main_matches_expected"] is True
    assert DATA["allowed_new_paths"] == [
        DOCUMENT,
        "docs/v0-19/evidence/v0.19.0-scope-freeze-r1.json",
        "backend/tests/area_yield/test_v0_19_scope_contract.py",
    ]


@pytest.mark.parametrize("path,expected", DATA["source_evidence_sha256"].items())
def test_public_original_source_bytes_unchanged(path, expected):
    assert len(expected) == 64
    assert hashlib.sha256(source_bytes(path)).hexdigest() == expected, path


def test_document_binding_and_independent_historical_anchors():
    assert DATA["source_evidence_count"] == len(DATA["source_evidence_sha256"]) == 11
    assert (
        hashlib.sha256((ROOT / DOCUMENT).read_bytes()).hexdigest()
        == DATA["document_sha256"][DOCUMENT]
    )
    assert (
        DATA["source_evidence_sha256"][
            "docs/v0-8/s9/scale-shape-error-decomposition-and-model-diagnosis-r1.md"
        ]
        == "60d45f0d3d0f2158255234b703c3510e4b54b2658646ac8ffbc3f8b3c40140ef"
    )
    assert (
        DATA["source_evidence_sha256"]["backend/app/forecast_quality/operational_peak.py"]
        == "3bebc3d193052b87968b95bdfc55ae1ca3ab2bb784d6c520743489e1586fb762"
    )


def test_inherited_findings_not_rebranded_or_ranked():
    facts = DATA["historical_findings"]
    assert facts["v08"] == "SCALE_AND_SHAPE_ERRORS_NON_ADDITIVE"
    assert facts["v13_weather_quantity"] == "SUPPORTED_IN_FROZEN_HISTORICAL_SCOPE"
    assert facts["v13_simple_gdd"] == "NO_STABLE_GAIN_PROVEN"
    assert facts["v13_weather_gdd_timing"] == "NOT_SUPPORTED"
    assert facts["v15_base10"] == "NO_CLEAR_LEADER"
    assert facts["v15_harvest_state_quantity"] == "SUPPORTED_SHORT_TERM_HISTORICAL_SCOPE"
    assert facts["v15_harvest_state_rolling7_start"] == (
        "NO_STABLE_IMPROVEMENT_OOT_REGRESSION_PRESERVED"
    )
    assert facts["operational_peak"] == "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1"
    for key in [
        "h7_prefix_is_rolling7_max",
        "cross_family_or_sample_ranking_allowed",
        "old_research_is_new_discovery",
        "production_accuracy_proven",
    ]:
        assert facts[key] is False
    assert DATA["model_families"] == [
        "AREA_FORECAST_PRODUCT",
        "OPERATIONAL_PEAK",
        "V0_15_BASE10_RIDGE",
        "V0_15_HARVEST_STATE_RIDGE",
        "CORE_FORECAST",
    ]
    assert len(DATA["objectives"]) == 5


@pytest.mark.parametrize("index,name", list(enumerate(NAMES)))
def test_stage_order_dependencies_deliverables_and_separate_owner_gate(index, name):
    assert DATA["stage_order"] == ["S0", "S1", "S2", "S3", "S4"]
    stage = DATA["stages"][f"S{index}"]
    assert stage["name"] == name
    assert stage["task_id"] == f"V0_19_S{index}_{name}"
    assert stage["depends_on"] == (
        [f"S{index - 1}_FORMAL_COMPLETE"] if index else ["OWNER_S0_AUTHORIZATION"]
    )
    assert stage["implementation_authorized"] is stage["formal_complete"] is False
    assert stage["docs_contract_only_authorized"] is (index == 0)
    assert stage["deliverables"]
    if index:
        assert stage["entry_gate"].startswith("SEPARATE_OWNER_IMPLEMENTATION")
    assert stage["completion_gate"] == "INDEPENDENT_REVIEW_OWNER_READY_MERGE_AND_POSTMERGE_CI"


def test_peak_metrics_scope_completeness_and_units_are_not_interchangeable():
    assert DATA["metrics"] == METRICS
    rules = DATA["metric_boundaries"]
    assert rules["h7"] == "D1_THROUGH_D7_PREFIX"
    assert rules["rolling7"] == "MAX_SUM_OF_COMPLETE_SEVEN_CONSECUTIVE_CALENDAR_DAYS"
    assert rules["tie_break"] == "EARLIEST_DATE"
    assert rules["missing_dates"] == "NOT_COMPUTABLE_NOT_ZERO"
    assert rules["windows_separate"] == ["FULL_SEASON", "H15_LOCAL_WINDOW"]
    assert rules["physical_basis_separate"] == ["ACTUAL_HARVEST", "FACTORY_ARRIVAL_PROXY"]
    assert rules["quantity_timing_evaluated_separately"] is True
    assert rules["business_accuracy_threshold"] is None


def test_candidate_is_one_isolated_preregistered_non_promoted_method():
    rules = DATA["candidate_constraints"]
    assert rules["max_new_daily_curve_candidates"] == 1
    for key in [
        "method_parameter_rules_frozen_before_results",
        "isolated_research_path",
        "operational_peak_baseline_preserved",
        "nonnegative",
        "numerically_stable",
        "mass_conserving",
        "continuous_dates",
        "deterministic",
    ]:
        assert rules[key] is True
    for key in [
        "method_selected_in_s0",
        "hidden_parameters",
        "future_target_actuals_allowed",
        "fixed_artificial_peak_shift_allowed",
        "accuracy_improvement_claim_in_s2",
    ]:
        assert rules[key] is False


def test_validation_requires_independent_data_experiment_permission_and_common_rows():
    assert DATA["stages"]["S3"]["entry_gate"] == (
        "SEPARATE_OWNER_IMPLEMENTATION_AND_DATA_AND_EXPERIMENT_AUTHORIZATION"
    )
    rules = DATA["controlled_validation"]
    for key in [
        "same_source",
        "same_target",
        "same_training_evaluation_range",
        "same_samples_and_physical_basis",
        "parameters_from_allowed_training_validation_only",
        "prediction_label_isolation",
        "seal_predictions_before_label_scoring",
        "preserve_failures_regressions_not_computable",
    ]:
        assert rules[key] is True
    for key in [
        "strict_pit",
        "exposed_2025_2026_is_blind_oot",
        "current_2026_2027_access_authorized",
    ]:
        assert rules[key] is False
    assert rules["insufficient_data_or_time_evidence"] == "BLOCKED"


def test_agronomic_reuse_hypotheses_not_new_event_system_or_proven_gain():
    rules = DATA["agronomic"]
    assert rules["priority"] == [
        "FLOWERING_START_FULL_END",
        "CULTIVAR_PLOT_AREA_LINK",
        "FORCING_ACTION_AND_TIME",
        "PRUNING_TYPE_TIME_INTENSITY",
        "EXISTING_HARVEST_STATE",
        "WEATHER_AND_PHENOLOGY_TIME",
    ]
    assert rules["reuse"] == ["V0_9_MANAGEMENT_EVENT", "PHENOLOGY_OBSERVATION", "PIT"]
    assert rules["allowed_conclusions"] == [
        "SUPPORTED_FOR_FURTHER_RESEARCH",
        "NOT_SUPPORTED",
        "INCONCLUSIVE",
        "BLOCKED",
    ]
    for key in [
        "new_event_system",
        "automatic_production_db_integration",
        "assumed_statistical_gain",
        "full_production_biophysical_model_training",
        "supported_implies_production_approval",
    ]:
        assert rules[key] is False


def test_completion_requires_executed_research_not_positive_results_or_production_claim():
    complete = DATA["research_completion"]
    assert complete["required"] == [
        "S0_S4_AUTHORIZED_COMPLETE",
        "CLEAR_RESEARCH_CONTRACT",
        "AT_LEAST_ONE_RUNNABLE_DAILY_CANDIDATE",
        "LAWFUL_REPRODUCIBLE_S3_COMPARISON",
        "SEPARATE_QUANTITY_AND_PEAK_METRICS",
        "RETAIN_REGRESSION_AND_NO_GAIN",
        "UNCHANGED_ORIGINAL_MODEL_AND_HISTORY",
        "DISCLOSE_PIT_AND_PROVENANCE_LIMITS",
        "CLEAR_CONCLUSION_AND_NEXT_DIRECTION",
        "FINAL_VERSION_REVIEW",
    ]
    assert (
        complete["s3_data_blocked_implies_incomplete"] is complete["no_stable_gain_allowed"] is True
    )
    for key in [
        "version_research_complete",
        "unexecuted_experiment_counts_as_complete",
        "production_accuracy_validated",
        "production_deployment_authorized",
    ]:
        assert complete[key] is False


def test_no_execution_or_implicit_downstream_authorization():
    assert DATA["production_ready"] is False
    governance = DATA["governance"]
    assert governance["owner_authorized"] is governance["stop_after_draft_exact_head_ci"] is True
    assert governance["s0_formal_complete"] is False
    assert {k for k, v in governance.items() if v is True} == {
        "owner_authorized",
        "stop_after_draft_exact_head_ci",
    }
    assert all(v is False for v in DATA["execution"].values())
    text = (ROOT / DOCUMENT).read_text()
    for token in [
        "STRICT_PIT=false",
        "PROSPECTIVE_ACCURACY_VALIDATED=false",
        "NO_STABLE_GAIN",
        "NOT_AVAILABLE",
        "七日分箱",
        "质量守恒",
        "不重新评分",
        "2026–2027",
        "单独 Owner 实施授权",
        "S0_FORMAL_COMPLETE=false",
    ]:
        assert token in text
