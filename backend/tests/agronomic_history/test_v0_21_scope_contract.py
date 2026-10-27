"""V0_21 S0 public planning contract; no features, model execution or data reads.

Historical reuse identities are Git blobs at BASE, never current source hashes.
"""

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.contract]
ROOT = Path(__file__).resolve().parents[3]
BASE = "c26ad54bc380c3f87a2e2250c91c0bf9ece12e8c"
SCOPE = ROOT / "docs/v0-21/evidence/v0.21-s0-scope.json"


def contract():
    return json.loads(SCOPE.read_bytes())


def assert_boundaries(data):
    assert data["version"] == "0.21.0"
    assert data["implementation_stage"] == "S0"
    assert data["input_data_class"] == "SYNTHETIC_TEST_FIXTURE"
    assert set(data["permissions"]) == {
        "s0_commit_push_draft_pr",
        "s1_implementation",
        "s2_implementation",
        "s3_implementation",
        "s4_implementation",
        "real_agronomic_data_read",
        "real_label_read",
        "model_training",
        "model_refitting",
        "model_promotion",
        "production_forecast_change",
        "prospective_accuracy_validated",
        "deployment",
        "ready",
        "merge",
        "tag",
        "release",
    }
    assert data["permissions"]["s0_commit_push_draft_pr"] is True
    assert all(v is False for k, v in data["permissions"].items() if k != "s0_commit_push_draft_pr")
    assert data["cycle_contract"]["missing_identity_policy"] == "UNMAPPED_NOT_MERGED"
    assert data["cycle_contract"]["cycle_start_policy"] == "EXPLICIT_PER_SEASON_NOT_FIXED_DATE"
    assert data["cycle_contract"]["ambiguous_primary_event"] == "NOT_COMPUTABLE"
    assert data["temporal_contract"]["known_at_required_for_as_of"] is True
    assert data["temporal_contract"]["date_only_is_strict_pit"] is False
    assert data["temporal_contract"]["future_observed_event_as_feature"] is False
    assert data["structure_contract"]["yield_or_peak_effect_coefficients"] is False
    assert data["evaluation_contract"]["season_peak_equals_origin_h15"] is False
    assert data["evaluation_contract"]["s1_metric_formula_changes"] is False
    assert data["evaluation_contract"]["rolling15_role"] == "V0_21_ADDITIVE_PROTOCOL_NOT_S1"
    remaining = data["evaluation_contract"]["remaining_season"]
    assert remaining["scope_id"] == "DECLARED_REMAINING_SEASON_PEAK"
    assert remaining["start_rule"] == "EXPLICIT_START_GTE_LOCAL_ORIGIN_PLUS_1"
    assert remaining["end_rule"] == "PREDECLARED_SEASON_CALENDAR_END"
    assert remaining["missing_dates"] == "NOT_COMPUTABLE_NO_IMPUTATION_OR_SCOPE_SHRINK"
    assert remaining["h15_relabel_allowed"] is False
    assert data["evaluation_contract"]["single_candidate_window_is_timing_skill"] is False
    assert data["completion"]["s1_s4_implemented"] is False
    assert data["completion"]["v021_formal_complete"] is False


def test_version_identity_and_authorization_boundaries():
    data = contract()
    assert_boundaries(data)
    assert data["task_id"] == "V0_21_S0_VERSION_SCOPE_AND_IMPLEMENTATION_PLAN_R2"
    assert data["revision"]["review_id"] == 5663203952
    assert data["revision"]["reviewed_head"] == "4c117bdea6b70d8806e87e48690219db8fac34a5"
    assert data["version_name"] == "AGRONOMIC_CYCLE_AND_FORECAST_RESEARCH_READINESS"
    assert data["base_main_sha"] == BASE
    assert data["preflight"]["existing_v021_conflicts"] == []
    assert data["preflight"]["main_push_ci"]["head_sha"] == BASE
    assert data["preflight"]["main_push_ci"]["conclusion"] == "SUCCESS"
    assert (
        SCOPE.read_bytes()
        == (
            json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
        ).encode()
    )
    assert data["goal_priority"] == {"season_peak": "EQUAL", "origin_h7_h15": "EQUAL"}


def test_all_stages_are_planned_and_follow_separate_postmerge_gates():
    data = contract()
    assert [s["id"] for s in data["stages"]] == ["S0", "S1", "S2", "S3", "S4"]
    required = {
        "business_goal",
        "functions",
        "code_scope",
        "inputs",
        "outputs",
        "synthetic_scenarios",
        "acceptance",
        "prohibited",
    }
    for i, stage in enumerate(data["stages"]):
        assert all(stage.get(k) for k in required)
        assert stage["status"] == ("SCOPE_DRAFT" if i == 0 else "PLANNED_NOT_AUTHORIZED")
        if i:
            assert stage["previous_stage"] == f"S{i - 1}"
            assert stage["start_gate"] == [
                "PREVIOUS_STAGE_MERGED",
                "MAIN_CI_SUCCESS",
                "OWNER_STAGE_AUTHORIZATION",
                "FRESH_MAIN_BRANCH",
            ]
    assert data["workflow"]["s0_new_paths"] == [
        "docs/v0-21/v0.21.0-version-plan.md",
        "docs/v0-21/stage-implementation-plan.md",
        "docs/v0-21/evidence/v0.21-s0-scope.json",
        "backend/tests/agronomic_history/test_v0_21_scope_contract.py",
    ]
    assert data["workflow"]["stop_after"] == "S0_DRAFT_PR_AND_EXACT_HEAD_CI"


def test_reuse_snapshot_uses_fixed_git_objects_and_original_bytes():
    data = contract()
    assert len({r["id"] for r in data["reuse_inventory"]}) == len(data["reuse_inventory"])
    for item in data["reuse_inventory"]:
        path = Path(item["path"])
        assert not path.is_absolute() and ".." not in path.parts
        assert item["commit"] == BASE
        raw = subprocess.check_output(["git", "show", f"{BASE}:{path.as_posix()}"], cwd=ROOT)
        assert hashlib.sha256(raw).hexdigest() == item["sha256"], str(path)
        assert item["reuse"] and item["minimal_gap"]


def test_documents_match_frozen_scope_and_address_seven_business_questions():
    data = contract()
    for path, expected in data["document_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    plan = (ROOT / "docs/v0-21/v0.21.0-version-plan.md").read_text()
    for question in range(1, 8):
        assert f"### Q{question}." in plan
    stages = (ROOT / "docs/v0-21/stage-implementation-plan.md").read_text()
    for i in range(5):
        assert f"## S{i}" in stages
    assert len(data["evaluation_contract"]["s1_metric_ids"]) == 10
    assert len(set(data["evaluation_contract"]["s1_metric_ids"])) == 10
    assert data["evaluation_contract"]["window_families"] == [
        "FULL_SEASON_PEAK",
        "DECLARED_REMAINING_SEASON_PEAK",
        "ORIGIN_H7_PREFIX",
        "ORIGIN_H15_LOCAL",
    ]
    assert data["cycle_contract"]["production_systems"] == [
        "DECIDUOUS_NATURAL",
        "DECIDUOUS_FORCING",
        "EVERGREEN",
    ]


def test_additive_protocol_freezes_units_denominators_and_failure_scopes():
    data = contract()["evaluation_contract"]
    additional = {m["id"]: m for m in data["v021_additive_metrics"]}
    assert set(additional) == {
        "V0_21_ROLLING_15DAY_PEAK_START_MAE",
        "V0_21_ROLLING_15DAY_PEAK_QUANTITY_MAE",
        "V0_21_ORIGIN_WINDOW_TOTAL_MAE",
        "V0_21_ORIGIN_WINDOW_TOTAL_WAPE",
    }
    assert not set(additional) & set(data["s1_metric_ids"])
    for metric in additional.values():
        assert metric["implementation_status"] == "PLANNED_S3_NOT_IMPLEMENTED"
        assert metric["numerator"] and metric["denominator"] and metric["not_computable"]
    date_metric = additional["V0_21_ROLLING_15DAY_PEAK_START_MAE"]
    assert date_metric["unit"] == "calendar_days"
    assert date_metric["denominator"] == "N_COMMON_COMPLETE_POSITIVE_ACTUAL_WINDOWS"
    quantity_metric = additional["V0_21_ROLLING_15DAY_PEAK_QUANTITY_MAE"]
    assert quantity_metric["denominator"] == "N_COMMON_COMPLETE_WINDOWS_INCLUDING_ZERO_ACTUAL"
    total = additional["V0_21_ORIGIN_WINDOW_TOTAL_WAPE"]
    assert total["numerator"] == "SUM_ABS_WINDOW_PREDICTED_TOTAL_MINUS_ACTUAL_TOTAL"
    assert total["denominator"] == "SUM_ACTUAL_WINDOW_TOTAL_ON_COMMON_COHORT"
    assert total["scopes"] == ["ORIGIN_H7_PREFIX", "ORIGIN_H15_LOCAL"]
    assert (
        data["same_date_pairing"] == "EXACT_BASE_MEMBER_SEASON_SCOPE_TARGET_DATE_AND_PHYSICAL_BASIS"
    )
    assert data["common_cohort_per_metric"] is True
    assert data["failures_retained_in_C0"] is True
    assert data["full_season_wape_allowed_for_remaining"] is False
    assert data["peak_selection"] == "INDEPENDENT_PREDICTION_AND_LABEL_MAXIMA_ON_SAME_SUPPORT"


def test_r1_scope_remains_a_verifiable_historical_snapshot():
    data = contract()
    raw = subprocess.check_output(
        [
            "git",
            "show",
            f"{data['revision']['reviewed_head']}:docs/v0-21/evidence/v0.21-s0-scope.json",
        ],
        cwd=ROOT,
    )
    assert hashlib.sha256(raw).hexdigest() == data["revision"]["previous_scope_sha256"]
    assert json.loads(raw)["schema_version"] == "V0_21_S0_SCOPE_R1"


@pytest.mark.parametrize(
    "section,key,bad_value",
    [
        ("permissions", "s1_implementation", True),
        ("permissions", "real_agronomic_data_read", True),
        ("permissions", "model_training", True),
        ("permissions", "production_forecast_change", True),
        ("permissions", "merge", True),
        ("cycle_contract", "missing_identity_policy", "MERGE_UNKNOWN_PLOTS"),
        ("cycle_contract", "cycle_start_policy", "JULY_01_EVERY_SEASON"),
        ("temporal_contract", "known_at_required_for_as_of", False),
        ("temporal_contract", "date_only_is_strict_pit", True),
        ("temporal_contract", "future_observed_event_as_feature", True),
        ("structure_contract", "yield_or_peak_effect_coefficients", True),
        ("evaluation_contract", "season_peak_equals_origin_h15", True),
        ("evaluation_contract", "s1_metric_formula_changes", True),
        ("evaluation_contract", "rolling15_role", "REDEFINED_S1_METRIC"),
        ("evaluation_contract", "single_candidate_window_is_timing_skill", True),
    ],
)
def test_unsafe_scope_mutations_are_rejected(section, key, bad_value):
    changed = copy.deepcopy(contract())
    changed[section][key] = bad_value
    with pytest.raises(AssertionError):
        assert_boundaries(changed)


@pytest.mark.parametrize(
    "key,bad_value",
    [
        ("start_rule", "ORIGIN_DAY_ALLOWED"),
        ("end_rule", "ORIGIN_PLUS_15_AUTO_END"),
        ("missing_dates", "DROP_MISSING_TARGETS"),
        ("h15_relabel_allowed", True),
    ],
)
def test_remaining_season_scope_cannot_be_renamed_or_silently_shortened(key, bad_value):
    changed = copy.deepcopy(contract())
    changed["evaluation_contract"]["remaining_season"][key] = bad_value
    with pytest.raises(AssertionError):
        assert_boundaries(changed)
