"""Offline current-state evidence; not independent review or risk acceptance."""

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from backend.tests.forecast_intelligence.build_v0_18_version_closeout import git_blobs

ROOT = Path(__file__).resolve().parents[3]
BASE = "816d8299f007eab7da140fc5c7547d941c026f8f"
SNAPSHOT_COMMIT = "772503823320c48c6920fc66c5164d8a30844fd9"
CURRENT_MAIN = "8f6cae4004c663b9ccaf2061869cc7cb6e80adc4"
V0_18_RELEASE_HEAD = "b6ac2e658edbace357c575bb42ee46b03bb863b9"
OLD = "93e9660f6ef2c494178be825c66d11898c6fff97"
EVIDENCE = "docs/v0-18/evidence/v0.18.0-final-closeout-status.json"
SNAPSHOT = "docs/v0-18/evidence/v0.18.0-final-closeout-github-snapshot.json"
pytestmark = [pytest.mark.unit, pytest.mark.contract]


def load(path):
    return json.loads((ROOT / path).read_bytes())


def canonical(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


def blob(commit, path):
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)


def v018_source_evidence_bytes(path: str) -> bytes:
    """Retain original V0.18 test-source pins without constraining later PR source."""
    if path == "backend/tests/forecast_intelligence/test_v0_18_final_closeout_status.py":
        return blob(SNAPSHOT_COMMIT, path)
    if path.startswith(("backend/", "frontend/")):
        return blob(V0_18_RELEASE_HEAD, path)
    return (ROOT / path).read_bytes()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(value):
    assert value["task_id"] == "V0_18_FINAL_CLOSEOUT_DECISION"
    assert value["reviewed_main_sha"] == BASE
    assert value["engineering_technical_result"] == "PASS_TESTED_SCOPE"
    assert value["formal_closeout_result"] == "BLOCKED"
    assert value["engineering_release_eligibility"] == "TECHNICAL_CANDIDATE_NOT_APPROVED"
    assert value["production_readiness"] == "NOT_READY"
    assert value["backend_lead_2"] == "PREAUTH_RACE_NOT_TESTED_PENDING"
    assert value["historical_gate_statuses"] == {
        **dict.fromkeys([f"G{i:02}" for i in range(1, 8)], "BLOCKED"),
        **dict.fromkeys([f"G{i:02}" for i in range(8, 14)], "PASS_HISTORICAL_TESTED_SCOPE"),
        **dict.fromkeys([f"G{i:02}" for i in range(14, 17)], "PENDING"),
    }
    assert len(value["historical_approval_gaps"]["formal"]) == 29
    assert len(value["historical_approval_gaps"]["planning"]) == 12
    assert len(value["production_risk_register"]) == 15
    assert all(
        r["status"] == "OPEN_NOT_VALIDATED" and r["production_blocking"]
        for r in value["production_risk_register"]
    )
    assert set(value["controls"]) == set("ABCDEFG")
    for control in value["controls"].values():
        assert control["reviewed_source_sha"] == BASE
        assert control["independent_acceptance_status"] == "PENDING"
        assert control["evidence_references"] and control["checks_performed"]
        assert control["limitations"] and control["findings"]
    assert all(v is False for k, v in value["governance"].items() if k != "stop")
    assert value["governance"]["stop"] is True
    assert value["final_head_ci"] == "EXTERNAL_EXACT_HEAD_RECEIPT_REQUIRED_AFTER_COMMIT"


def test_current_state_and_canonical_sources():
    value = load(EVIDENCE)
    validate(value)
    for path in (EVIDENCE, SNAPSHOT):
        assert (ROOT / path).read_bytes() == canonical(load(path))
    for path, expected in value["source_evidence_sha256"].items():
        assert sha(v018_source_evidence_bytes(path)) == expected, path
    for path, expected in value["historical_snapshot_sha256"].items():
        assert sha((ROOT / path).read_bytes()) == sha(blob(OLD, path)) == expected, path
    for path, expected in value["historical_audit_code_sha256"].items():
        assert sha(blob(OLD, path)) == expected, path
    for path, expected in value["current_main_source_sha256"].items():
        # Frozen 816d8299 audit: later approved source changes do not rewrite history.
        assert sha(blob(BASE, path)) == expected, path
    for path, expected in value["artifact_sha256"].items():
        assert sha((ROOT / path).read_bytes()) == expected, path


def test_pr_parent_chain_actual_jobs_and_scoped_reviews():
    snapshot = load(SNAPSHOT)
    prs = {p["number"]: p for p in snapshot["pull_requests"]}
    numbers = [710, 711, 712, 713, 714, 715, 716, 717, 718, 721, 723, 724, 725, 726, 727]
    numbers += [729, 730, 731, 732]
    previous = "1b218edc74ff29091c07607ddbcdba0c10577398"
    for number in numbers:
        row = prs[number]
        parents = (
            subprocess.check_output(
                ["git", "rev-list", "--parents", "-n", "1", row["merge_sha"]], cwd=ROOT
            )
            .decode()
            .split()[1:]
        )
        assert row["merged"] and row["state"] == "closed"
        assert parents == row["parents"] == [previous, row["head_sha"]]
        pr_runs = [r for r in row["ci_attempts"] if r["event"] == "pull_request"]
        assert pr_runs and all(r["head_sha"] == row["head_sha"] for r in pr_runs)
        latest = max(pr_runs, key=lambda r: (r["id"], r["run_attempt"]))
        assert latest["conclusion"] == "success" and latest["status"] == "completed"
        assert len(latest["jobs"]) == 12
        assert all(j["conclusion"] == "success" for j in latest["jobs"])
        pushes = [r for r in row["ci_attempts"] if r["event"] == "push"]
        assert pushes and all(r["head_sha"] == row["merge_sha"] for r in pushes)
        latest = max(pushes, key=lambda r: (r["id"], r["run_attempt"]))
        assert latest["conclusion"] == {718: "failure", 731: "cancelled"}.get(number, "success")
        assert len(latest["jobs"]) == 12
        previous = row["merge_sha"]
    assert previous == BASE == snapshot["reviewed_main_sha"]
    for number, review_id in {
        729: 5545395837,
        730: 5556168873,
        731: 5556766696,
        732: 5557159134,
    }.items():
        review = next(r for r in prs[number]["reviews"] if r["id"] == review_id)
        assert review["commit_id"] == prs[number]["head_sha"]
        assert review["state"] == "COMMENTED" and "REVIEW_RESULT=PASS" in review["body"]
    assert [
        (r["run_attempt"], r["conclusion"])
        for r in prs[726]["ci_attempts"]
        if r["id"] == 38703671252
    ] == [(1, "cancelled"), (2, "success")]
    assert snapshot["release"]["tag_name"] == "v0.17.0"
    assert not snapshot["release"]["draft"] and not snapshot["release"]["prerelease"]


def test_original_gaps_risks_and_semantics_are_not_replaced():
    value = load(EVIDENCE)
    proposal = load("docs/v0-18/evidence/v0.18.0-governance-exception-proposal-r1.json")
    r1 = load("docs/v0-18/evidence/v0.18.0-version-closeout-r1.json")
    r2 = load("docs/v0-18/evidence/v0.18.0-approval-provenance-r2.json")
    assert value["historical_approval_gaps"] == proposal["historical_approval_gaps"]
    assert value["production_risk_register"] == proposal["production_risk_register"]
    assert value["semantic_boundaries"] == r1["semantic_boundaries"]
    assert [g["status"] for g in r2["version_complete_gates"][:7]] == ["BLOCKED"] * 7
    assert value["backend_lead_2"] == "PREAUTH_RACE_NOT_TESTED_PENDING"
    assert value["observed_fixed_race_counts"] == {
        "business_sql": 0,
        "quality_file": 0,
        "simulation": 0,
        "comparison": 0,
    }
    frozen = r1["frozen_model_and_math_sha256"]
    current = git_blobs(ROOT, dict.fromkeys(frozen, BASE))
    assert all(sha(current[path]) == expected for path, expected in frozen.items())


@pytest.mark.parametrize(
    "path",
    [
        "backend/tests/forecast_intelligence/build_v0_18_approval_provenance_r2.py",
        "backend/tests/forecast_intelligence/test_v0_18_approval_provenance_r2.py",
        "backend/tests/forecast_intelligence/test_v0_18_final_closeout_status.py",
    ],
)
def test_v018_historical_source_pins_use_immutable_git_bytes(path):
    expected = load(EVIDENCE)["source_evidence_sha256"][path]
    assert sha(v018_source_evidence_bytes(path)) == expected


@pytest.mark.parametrize(
    "path",
    [
        "backend/app/api/business_access.py",
        "frontend/src/dashboard/app/Dashboard.tsx",
    ],
)
def test_v018_current_main_snapshot_never_depends_on_later_worktree(path):
    expected = load(EVIDENCE)["current_main_source_sha256"][path]
    assert sha(blob(BASE, path)) == expected


def v018_delivery_changed_paths() -> list[str]:
    """Inspect the immutable V0.18 delivery range, not a later PR's working tree."""
    return (
        subprocess.check_output(
            ["git", "diff", "--name-only", CURRENT_MAIN, V0_18_RELEASE_HEAD], cwd=ROOT
        )
        .decode()
        .splitlines()
    )


def assert_v018_delivery_scope(changed: list[str], allowed: set[str]) -> None:
    """Preserve both the historical allowlist and the production-path prohibition."""
    assert set(changed) <= allowed
    assert not any(path.startswith(("backend/app/", "frontend/", ".github/")) for path in changed)


def test_current_delivery_is_audit_only_not_production_mutation():
    value = load(EVIDENCE)
    historical = set(value["historical_snapshot_sha256"]) | set(
        value["historical_audit_code_sha256"]
    )
    added = {
        EVIDENCE,
        SNAPSHOT,
        "docs/v0-18/v0.18.0-final-closeout-status.md",
        "backend/tests/forecast_intelligence/test_v0_18_final_closeout_status.py",
        "docs/v0-18/v0.18.0-final-closeout-preauth-update.md",
        "docs/v0-18/evidence/v0.18.0-final-closeout-preauth-update.json",
        "docs/v0-18/evidence/v0.18.0-final-closeout-preauth-github-snapshot.json",
        "backend/tests/forecast_intelligence/test_v0_18_final_closeout_preauth_update.py",
        "docs/v0-18/evidence/final-closeout-preauth-current/backend.xml",
        "docs/v0-18/evidence/final-closeout-preauth-current/execution.log",
        "docs/v0-18/evidence/final-closeout-preauth-current/owned-resources.json",
        "docs/v0-18/evidence/final-closeout-preauth-current/main-canary.xml",
        "docs/v0-18/evidence/final-closeout-preauth-current/pr-canary.xml",
    }
    # This is a historical V0.18 audit. Later-version commits are out of scope.
    changed = v018_delivery_changed_paths()
    assert_v018_delivery_scope(changed, historical | added)


def test_v018_delivery_diff_uses_only_frozen_commit_range(monkeypatch):
    calls = []

    def fake_check_output(args, *, cwd):
        calls.append((args, cwd))
        return b"docs/v0-18/v0.18.0-closeout.md"

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    assert v018_delivery_changed_paths() == ["docs/v0-18/v0.18.0-closeout.md"]
    assert calls == [(["git", "diff", "--name-only", CURRENT_MAIN, V0_18_RELEASE_HEAD], ROOT)]


@pytest.mark.parametrize(
    "unauthorized_path",
    [
        "backend/app/_v018_delivery_scope_probe.py",
        "frontend/_v018_delivery_scope_probe.ts",
        ".github/workflows/_v018_delivery_scope_probe.yml",
        "docs/_v018_delivery_scope_probe.md",
    ],
)
def test_v018_historical_delivery_rejects_unauthorized_paths(unauthorized_path):
    value = load(EVIDENCE)
    allowed = (
        set(value["historical_snapshot_sha256"])
        | set(value["historical_audit_code_sha256"])
        | {
            EVIDENCE,
            SNAPSHOT,
            "docs/v0-18/v0.18.0-final-closeout-status.md",
            "backend/tests/forecast_intelligence/test_v0_18_final_closeout_status.py",
            "docs/v0-18/v0.18.0-final-closeout-preauth-update.md",
            "docs/v0-18/evidence/v0.18.0-final-closeout-preauth-update.json",
            "docs/v0-18/evidence/v0.18.0-final-closeout-preauth-github-snapshot.json",
            "backend/tests/forecast_intelligence/test_v0_18_final_closeout_preauth_update.py",
            "docs/v0-18/evidence/final-closeout-preauth-current/backend.xml",
            "docs/v0-18/evidence/final-closeout-preauth-current/execution.log",
            "docs/v0-18/evidence/final-closeout-preauth-current/owned-resources.json",
            "docs/v0-18/evidence/final-closeout-preauth-current/main-canary.xml",
            "docs/v0-18/evidence/final-closeout-preauth-current/pr-canary.xml",
        }
    )
    assert unauthorized_path not in allowed
    with pytest.raises(AssertionError):
        assert_v018_delivery_scope([unauthorized_path], allowed)
    # Verify the production-path guard independently of the historical allowlist.
    if unauthorized_path.startswith(("backend/app/", "frontend/", ".github/")):
        with pytest.raises(AssertionError):
            assert_v018_delivery_scope([unauthorized_path], allowed | {unauthorized_path})


@pytest.mark.parametrize(
    "field,new",
    [
        ("formal_closeout_result", "PASS"),
        ("production_readiness", "READY"),
        ("backend_lead_2", "PASS"),
        ("engineering_release_eligibility", "APPROVED"),
    ],
)
def test_unsupported_acceptance_cannot_pass(field, new):
    value = copy.deepcopy(load(EVIDENCE))
    value[field] = new
    with pytest.raises(AssertionError):
        validate(value)


def test_risk_or_historical_gate_cannot_be_silently_closed():
    for mode in ("gate", "risk", "acceptance", "owner"):
        value = copy.deepcopy(load(EVIDENCE))
        if mode == "gate":
            value["historical_gate_statuses"]["G01"] = "PASS"
        elif mode == "risk":
            value["production_risk_register"][0]["status"] = "CLOSED"
        elif mode == "acceptance":
            value["controls"]["A"]["independent_acceptance_status"] = "PASS"
        else:
            value["governance"]["owner_historical_risk_acceptance"] = True
        with pytest.raises(AssertionError):
            validate(value)
