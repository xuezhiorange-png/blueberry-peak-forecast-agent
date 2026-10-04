"""S5 consumes public snapshots only; no research execution or private fixtures."""

import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.run_v0_13_s5_feature_value_closeout import (
    BASE,
    RESULT_FIELDS,
    SLICES,
    CloseoutError,
    build_closeout,
    joint_incremental_decision,
    load_public_inputs,
    map_predictive_gate,
    validate_lineage_record,
    verify_public_pin,
)

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.contract


def public_inputs() -> dict:
    return load_public_inputs(ROOT, verify_git=False)


def lineage() -> list[dict]:
    return [
        dict(
            s,
            lineage_pass="PASS",
            exact_head_jobs_success=12,
            post_merge_jobs_success=4,
            post_merge_jobs_skipped=8,
        )
        for s in SLICES
    ]


def test_s0_exact_four_fields_and_final_mapping() -> None:
    result = build_closeout(public_inputs(), lineage())
    assert set(result["final_results"]) == set(RESULT_FIELDS)
    assert result["final_results"] == {
        "WEATHER_INCREMENTAL_VALUE": "SUPPORTED",
        "GDD_INCREMENTAL_VALUE": "NOT_SUPPORTED",
        "WEATHER_PLUS_GDD_INCREMENTAL_VALUE": "NOT_SUPPORTED",
        "PEAK_TIMING_INCREMENTAL_VALUE": "NOT_SUPPORTED",
    }


@pytest.mark.parametrize(
    "gate,decision",
    [
        ("MEETS_SUPPORTED_CRITERIA", "SUPPORTED"),
        ("MEETS_NOT_SUPPORTED_CRITERIA", "NOT_SUPPORTED"),
        ("INCONCLUSIVE_BY_FROZEN_RULE", "INCONCLUSIVE"),
    ],
)
def test_predictive_gate_mapping(gate: str, decision: str) -> None:
    assert map_predictive_gate(gate) == decision


def test_joint_incremental_requires_both_required_incremental_legs_supported() -> None:
    assert joint_incremental_decision("SUPPORTED", "NOT_SUPPORTED", "INCONCLUSIVE") == (
        "NOT_SUPPORTED",
        False,
    )
    assert joint_incremental_decision("SUPPORTED", "SUPPORTED", "SUPPORTED") == ("SUPPORTED", True)
    assert joint_incremental_decision("SUPPORTED", "SUPPORTED", "INCONCLUSIVE") == (
        "INCONCLUSIVE",
        False,
    )


def test_oracle_cannot_enter_primary_decisions_and_history_remains_separate() -> None:
    inputs = public_inputs()
    original = build_closeout(inputs, lineage())
    assert original["V0_7_WEATHER_INCREMENTAL_VALUE"] == "INCONCLUSIVE"
    assert original["oracle"]["support_classification"] == (
        "NOT_APPLICABLE_RESEARCH_UPPER_BOUND_ONLY"
    )
    assert original["PRODUCTION_USE_APPROVED"] is False
    assert original["V0_14_AUTHORIZED"] is False
    assert original["NEXT_VERSION_IMPLEMENTATION_AUTHORIZED"] is False
    assert original["TAG_AUTHORIZED"] is False
    assert original["RELEASE_AUTHORIZED"] is False
    assert original["V0_13_VERSION_COMPLETE"] is True
    changed = copy.deepcopy(inputs)
    changed["S4"]["control_report"]["oracle_comparisons"]["ORACLE_VS_M1"][
        "both_dates_improve_every_fold"
    ] = True
    assert build_closeout(changed, lineage())["final_results"] == original["final_results"]


def test_prior_evidence_drift_fails_closed() -> None:
    with pytest.raises(CloseoutError, match="PREVIOUS_SLICE_EVIDENCE_DRIFT"):
        verify_public_pin(b"changed", "0" * 64, "same", "same")
    with pytest.raises(CloseoutError, match="PREVIOUS_SLICE_EVIDENCE_DRIFT"):
        verify_public_pin(b"same", hashlib.sha256(b"same").hexdigest(), "old", "new")


def test_public_pins_and_deterministic_closeout() -> None:
    inputs = public_inputs()
    a = build_closeout(inputs, lineage())
    assert a == build_closeout(inputs, lineage())
    assert len(a["public_evidence_pins"]) == 10
    for pin in a["public_evidence_pins"].values():
        assert pin["slice_merge_blob"] == pin["base_blob"]
        assert len(pin["sha256"]) == 64


def test_ci_public_fixture_mode_needs_no_git_history_or_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("CI fixture must not invoke a subprocess")

    monkeypatch.setattr("scripts.run_v0_13_s5_feature_value_closeout.command", forbidden)
    report = build_closeout(public_inputs(), lineage())
    assert report["PRIVATE_DATA_REQUIRED_FOR_CI"] is False


@pytest.mark.parametrize("mutation", ["head", "merge", "draft", "ci_sha", "failure", "empty_jobs"])
def test_lineage_mutations_fail_closed(mutation: str) -> None:
    s = SLICES[0]
    pr = {"state": "MERGED", "headRefOid": s["head"], "mergeCommit": {"oid": s["merge"]}}
    ci = {
        "status": "completed",
        "conclusion": "success",
        "headSha": s["head"],
        "jobs": [{"conclusion": "success"}] * 12,
    }
    post = dict(ci, headSha=s["merge"])
    if mutation == "head":
        pr["headRefOid"] = "wrong"
    elif mutation == "merge":
        pr["mergeCommit"] = {"oid": "wrong"}
    elif mutation == "draft":
        pr["state"] = "OPEN"
    elif mutation == "ci_sha":
        ci["headSha"] = BASE
    elif mutation == "failure":
        ci["jobs"] = [{"conclusion": "failure"}] * 12
    else:
        ci["jobs"] = []
    with pytest.raises(CloseoutError, match="LINEAGE"):
        validate_lineage_record(s, pr, ci, post)


def test_illegal_gate_and_primary_authority_mutations_rejected() -> None:
    with pytest.raises(CloseoutError):
        map_predictive_gate("ORACLE_SUPPORTED")
    inputs = public_inputs()
    inputs["S4"]["ORACLE_DEPLOYABLE"] = True
    with pytest.raises(CloseoutError):
        build_closeout(inputs, lineage())
    inputs = public_inputs()
    inputs["S0"]["result_fields"].append("ORACLE_VALUE")
    with pytest.raises(CloseoutError):
        build_closeout(inputs, lineage())


def test_runner_has_no_model_or_private_reader_imports() -> None:
    runner = ROOT / "scripts/run_v0_13_s5_feature_value_closeout.py"
    tree = ast.parse(runner.read_text())
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert all(not (m or "").startswith("backend") for m in imports)
    assert "xlrd" not in runner.read_text()
    assert "read_excel" not in runner.read_text()


def test_committed_closeout_matches_public_evidence_projection() -> None:
    path = ROOT / "docs/v0-13/evidence/v0.13-s5-feature-value-decision-and-version-closeout-r1.json"
    evidence = json.loads(path.read_text())
    assert evidence == build_closeout(public_inputs(), evidence["git_lineage"])
    assert all(
        evidence[k] is False
        for k in (
            "PRIVATE_HARVEST_ROW_READ",
            "PRIVATE_WEATHER_DATA_READ",
            "MODEL_TRAINING_EXECUTED",
            "BACKTEST_EXECUTED",
            "SCORING_EXECUTED",
            "ORACLE_EXECUTED",
            "NEW_MODEL_ARTIFACT",
            "NEW_PREDICTION_ARTIFACT",
            "V0_12_REOPENED",
            "V0_12_ARTIFACTS_CHANGED",
        )
    )
