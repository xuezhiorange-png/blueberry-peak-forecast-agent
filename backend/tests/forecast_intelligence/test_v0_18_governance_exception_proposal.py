"""Offline governance proposal checks; never approve an exception or run business code."""

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from backend.tests.historical_source import historical_bytes

ROOT = Path(__file__).resolve().parents[3]
BASE = "2b890d8e68a47ca506e7cf6b04bd187472138b2d"
CLOSEOUT = "93e9660f6ef2c494178be825c66d11898c6fff97"
R1_HEAD = "63a044b39bb0c7a9a6698b1700628c4ee31a1050"
DOC = "docs/v0-18/v0.18.0-governance-exception-decision-proposal-r1.md"
EVIDENCE = "docs/v0-18/evidence/v0.18.0-governance-exception-proposal-r1.json"
TEST = "backend/tests/forecast_intelligence/test_v0_18_governance_exception_proposal.py"
R1 = "docs/v0-18/evidence/v0.18.0-version-closeout-r1.json"
R2 = "docs/v0-18/evidence/v0.18.0-approval-provenance-r2.json"
FORMAL = {710, 715, 717, 718, 721, 723, 724, 725, 726, 727}
PLANNING = {711, 712, 713, 714, 716}
pytestmark = [pytest.mark.unit, pytest.mark.contract]


def canonical(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source(path):
    return json.loads(historical_bytes(path, CLOSEOUT, root=ROOT))


def proposal():
    return json.loads((ROOT / EVIDENCE).read_bytes())


def expected_gaps(r2, numbers):
    gaps = []
    for row in r2["approval_audit"]:
        if row["pr_number"] not in numbers:
            continue
        for action in row["missing_records"]:
            candidates = [
                r
                for r in r2["approval_records"]
                if r["pr_number"] == row["pr_number"] and r["action_type"] == action
            ]
            reason = (
                "PR727_ORIGINAL_PRIOR_REVIEW_OR_EXACT_HEAD_CONTEXT_UNAVAILABLE"
                if candidates
                else "NO_VERIFIED_ORIGINAL_RECORD_IN_ACCESSED_SOURCES"
            )
            gaps.append(
                {
                    "gap_id": f"PR{row['pr_number']}:{action}",
                    "pr_number": row["pr_number"],
                    "head_sha": row["head_sha"],
                    "classification": row["classification"],
                    "action_type": action,
                    "original_status": row["actions"][action],
                    "candidate_evidence_ids": [r["evidence_id"] for r in candidates],
                    "missing_reason": reason,
                    "absence_of_approval_proven": False,
                    "resolved_by_this_proposal": False,
                }
            )
    return gaps


def validate(p):
    assert p["task_id"] == "V0_18_GOVERNANCE_EXCEPTION_DECISION_PROPOSAL_R1"
    assert p["exception_id"] == "V0_18_HISTORICAL_APPROVAL_PROVENANCE_EXCEPTION"
    assert p["decision"]["status"] == "PROPOSED"
    assert p["decision"]["recommended_option"] == "OPTION_B"
    assert p["decision"]["owner_selected_option"] is None
    assert p["decision"]["owner_risk_acceptance"] is False
    assert p["future_application_requirements"]["active"] is False
    for field in ("approved_by", "decision_timestamp", "approval_record_locator"):
        assert p["decision"][field] is None
    assert p["scope"]["repository"] == "xuezhiorange-png/blueberry-peak-forecast-agent"
    assert p["scope"]["version"] == "0.18.0"
    assert p["scope"]["purpose"] == "V0_18_ENGINEERING_CLOSEOUT_ONLY"
    assert p["scope"]["one_time"] is True
    assert set(p["scope"]["excluded"]) == {
        "PRODUCTION_DEPLOYMENT",
        "PRODUCTION_SECURITY_ACCEPTANCE",
        "REAL_DATA_IMPORT",
        "FORECAST_ACCURACY_VALIDATION",
        "TAG",
        "RELEASE",
        "V0_19",
        "OTHER_PROJECTS",
    }
    assert p["historical_approval_gaps"]["formal"] == expected_gaps(source(R2), FORMAL)
    assert p["historical_approval_gaps"]["planning"] == expected_gaps(source(R2), PLANNING)
    assert len(p["historical_approval_gaps"]["formal"]) == 29
    assert len(p["historical_approval_gaps"]["planning"]) == 12
    assert p["original_gate_matrix"] == [
        {"id": g["id"], "status": g["status"]} for g in source(R2)["version_complete_gates"]
    ]
    assert p["original_gate_counts"] == {"PASS": 6, "BLOCKED": 7, "PENDING": 3, "FAIL": 0}
    assert p["historical_failures"] == source(R1)["historical_failures"]
    assert p["production_risk_register"] == source(R1)["production_gap_register"]
    assert len(p["production_risk_register"]) == 15
    assert all(
        r["status"] == "OPEN_NOT_VALIDATED" and r["production_blocking"]
        for r in p["production_risk_register"]
    )
    assert {c["id"] for c in p["compensating_controls"]} == set("ABCDEFGH")
    assert all(
        c["accepted"] is False and c["accepted_by"] is None for c in p["compensating_controls"]
    )
    assert all(c["status"] == "PENDING_INDEPENDENT_ACCEPTANCE" for c in p["compensating_controls"])
    assert all(
        c["acceptance_record"] is None and c["acceptance_timestamp"] is None
        for c in p["compensating_controls"]
    )
    assert p["historical_gate_reason_classification"] == {
        f"G{i:02}": "BLOCKED_HISTORICAL_EVIDENCE" for i in range(1, 8)
    }
    assert p["technical_delivery_evidence"]["historical_approval_absence_proven"] is False
    assert p["current_effect"] == {
        "exception_effective": False,
        "historical_approvals_reconstructed": False,
        "historical_gates_changed": False,
        "historical_pass_statistics_changed": False,
        "version_completion_definition_changed": False,
        "closeout_eligible_by_exception": False,
        "production_risks_closed": False,
        "independent_compensating_review_performed": False,
    }
    governance = p["governance"]
    assert governance["proposal_authorized"] is True
    assert governance["production_readiness"] == "NOT_READY"
    for field in (
        "exception_approved",
        "historical_approval_ratified",
        "version_closeout_formal_complete",
        "v0_18_version_complete",
        "ready_authorized",
        "merge_authorized",
        "tag_authorized",
        "release_authorized",
        "deploy_authorized",
        "v0_19_authorized",
        "production_code_changed",
        "database_accessed",
        "forecast_executed",
        "current_actual_accessed",
    ):
        assert governance[field] is False, field
    assert governance["stop"] is True


def test_current_proposal_is_not_approval_or_waiver():
    validate(proposal())


def test_canonical_json_and_new_source_hashes():
    p = proposal()
    assert (ROOT / EVIDENCE).read_bytes() == canonical(p)
    assert set(p["proposal_source_sha256"]) == {DOC, TEST}
    for path, expected in p["proposal_source_sha256"].items():
        assert sha((ROOT / path).read_bytes()) == expected
    assert canonical(p) == canonical(dict(reversed(list(p.items()))))


def test_r1_r2_original_git_bytes_not_rewritten():
    bindings = proposal()["closeout_source_bindings"]
    assert len(bindings) == 11
    for path, binding in bindings.items():
        assert binding["commit_sha"] == CLOSEOUT
        raw = historical_bytes(path, CLOSEOUT, root=ROOT)
        assert sha(raw) == binding["sha256"]
        if binding["generation"] == "R1":
            assert raw == historical_bytes(path, R1_HEAD, root=ROOT)
    assert (
        source(R1)["gate_counts"] == source(R2)["gate_counts"] == proposal()["original_gate_counts"]
    )


def test_29_formal_and_12_planning_gaps_stay_separate_and_complete():
    p = proposal()
    groups = p["historical_approval_gaps"]
    assert {g["pr_number"] for g in groups["formal"]} == FORMAL
    assert {g["pr_number"] for g in groups["planning"]} == PLANNING
    all_gaps = groups["formal"] + groups["planning"]
    assert len({g["gap_id"] for g in all_gaps}) == 41
    assert all(g["original_status"] != "VERIFIED" for g in all_gaps)
    assert all(g["absence_of_approval_proven"] is False for g in all_gaps)
    assert all(g["missing_reason"] for g in all_gaps)


def test_history_failed_and_cancelled_ci_remains_failed_and_cancelled():
    red, cancelled = proposal()["historical_failures"]
    assert (red["pr"], red["run"], red["conclusion"], red["corrected_by_pr"]) == (
        718,
        38326155853,
        "failure",
        721,
    )
    assert (
        cancelled["pr"],
        cancelled["run"],
        cancelled["attempt"],
        cancelled["conclusion"],
        cancelled["successful_attempt"],
    ) == (726, 38703671252, 1, "cancelled", 2)


def test_all_options_and_future_acceptance_require_separate_authority():
    p = proposal()
    assert set(p["owner_options"]) == {"OPTION_A", "OPTION_B", "OPTION_C"}
    for option in p["owner_options"].values():
        assert {
            "scope",
            "required_evidence",
            "residual_risk",
            "closeout_effect",
            "tag_release_effect",
            "production_effect",
        } <= set(option)
        assert option["tag_release_effect"] == "NO_AUTHORIZATION_OR_AUTOMATIC_GATE_PASS"
        assert option["production_effect"] == "NOT_READY_NO_DEPLOYMENT_AUTHORIZATION"
    future = p["future_application_requirements"]
    assert future["active"] is False
    assert future["separate_proposal_review_and_owner_rule_approval"] is True
    assert future["separate_rule_pr_merge_and_main_ci"] is True
    assert future["compensating_controls_a_h_verified"] is True
    assert future["current_timestamp_owner_risk_acceptance_and_exception_record"] is True
    assert future["closeout_g14_g15_separate_review_and_authorization"] is True
    assert future["g16_not_waived_or_approved"] is True
    assert future["requires_closeout_pr_approval_to_approve_its_exception"] is False
    assert future["head_or_scope_drift_requires_new_review"] is True
    assert future["this_proposal_may_modify_pr728"] is False
    ci = p["preflight"]["closeout_ci"]
    assert (ci["id"], ci["head_sha"], ci["event"], ci["status"], ci["conclusion"]) == (
        38859661855,
        CLOSEOUT,
        "pull_request",
        "completed",
        "success",
    )
    jobs = p["preflight"]["closeout_ci_jobs"]
    assert len(jobs) == len({j["id"] for j in jobs}) == 12
    assert all(j["status"] == "completed" and j["conclusion"] == "success" for j in jobs)
    assert p["preflight"]["proposal_ci"] == "PENDING_POST_COMMIT_SEPARATE_EXACT_HEAD_RECEIPT"


@pytest.mark.parametrize(
    "mutation",
    [
        "approve",
        "select_b",
        "accept_risk",
        "backdate",
        "gate_pass",
        "gap_delete",
        "planning_as_formal",
        "failure_erased",
        "risk_close",
        "control_pass",
        "activate",
        "complete",
        "deploy",
    ],
)
def test_forbidden_shortcuts_fail_closed(mutation):
    p = copy.deepcopy(proposal())
    if mutation == "approve":
        p["decision"]["status"] = "APPROVED"
    elif mutation == "select_b":
        p["decision"]["owner_selected_option"] = "OPTION_B"
    elif mutation == "accept_risk":
        p["decision"]["owner_risk_acceptance"] = True
    elif mutation == "backdate":
        p["decision"]["decision_timestamp"] = "2026-01-01T00:00:00Z"
    elif mutation == "gate_pass":
        p["original_gate_matrix"][0]["status"] = "PASS"
    elif mutation == "gap_delete":
        p["historical_approval_gaps"]["formal"].pop()
    elif mutation == "planning_as_formal":
        p["historical_approval_gaps"]["formal"].append(
            p["historical_approval_gaps"]["planning"].pop()
        )
    elif mutation == "failure_erased":
        p["historical_failures"][0]["conclusion"] = "success"
    elif mutation == "risk_close":
        p["production_risk_register"][0]["production_blocking"] = False
    elif mutation == "control_pass":
        p["compensating_controls"][0]["accepted"] = True
    elif mutation == "activate":
        p["current_effect"]["exception_effective"] = True
    elif mutation == "complete":
        p["governance"]["v0_18_version_complete"] = True
    else:
        p["governance"]["deploy_authorized"] = True
    with pytest.raises(AssertionError):
        validate(p)


def test_unavailable_capabilities_and_release_gates_not_waived():
    p = proposal()
    assert p["capability_limits"] == source(R1)["semantic_boundaries"]
    assert p["capability_limits"]["point_is_proven_p50"] is False
    assert p["capability_limits"]["real_roi_validated"] is False
    assert (
        p["compensatory_review_scope"]
        == "CURRENT_ENGINEERING_STATE_NOT_PROOF_OF_HISTORICAL_APPROVAL"
    )
    assert p["decision"]["allowed_statuses"] == [
        "NOT_REQUESTED",
        "PROPOSED",
        "APPROVED",
        "REJECTED",
    ]


def test_main_baseline_bytes_only_three_additions():
    # Bind the introducing commit, so this historical proposal does not freeze
    # every later authorized main change. No refs, databases or files are edited.
    additions = (
        subprocess.check_output(
            ["git", "log", "--diff-filter=A", "--format=%H", "--", DOC], cwd=ROOT
        )
        .decode()
        .splitlines()
    )
    if additions:
        end = additions[-1]
        fields = (
            subprocess.check_output(["git", "diff", "--name-status", BASE, end], cwd=ROOT)
            .decode()
            .splitlines()
        )
        assert set(fields) == {"A\t" + p for p in (DOC, EVIDENCE, TEST)}
    else:
        fields = (
            subprocess.check_output(["git", "status", "--porcelain=v1"], cwd=ROOT)
            .decode()
            .splitlines()
        )
        assert {line[3:] for line in fields} <= {DOC, EVIDENCE, TEST}
