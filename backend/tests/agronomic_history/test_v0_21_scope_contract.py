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
    assert data["evaluation_contract"]["rolling15_role"] == "STRUCTURAL_DIAGNOSTIC_NOT_S1_METRIC"
    assert data["completion"]["s1_s4_implemented"] is False
    assert data["completion"]["v021_formal_complete"] is False


def test_version_identity_and_authorization_boundaries():
    data = contract()
    assert_boundaries(data)
    assert data["task_id"] == "V0_21_S0_VERSION_SCOPE_AND_IMPLEMENTATION_PLAN_R1"
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
        "ORIGIN_H7_PREFIX",
        "ORIGIN_H15_LOCAL",
    ]
    assert data["cycle_contract"]["production_systems"] == [
        "DECIDUOUS_NATURAL",
        "DECIDUOUS_FORCING",
        "EVERGREEN",
    ]


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
    ],
)
def test_unsafe_scope_mutations_are_rejected(section, key, bad_value):
    changed = copy.deepcopy(contract())
    changed[section][key] = bad_value
    with pytest.raises(AssertionError):
        assert_boundaries(changed)
