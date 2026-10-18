"""Append-only closeout status; scoped fix review is not whole-version approval."""

import copy
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from backend.tests.historical_source import historical_bytes

ROOT = Path(__file__).resolve().parents[3]
BASE = "8f6cae4004c663b9ccaf2061869cc7cb6e80adc4"
PREVIOUS = "772503823320c48c6920fc66c5164d8a30844fd9"
OLD_MAIN = "816d8299f007eab7da140fc5c7547d941c026f8f"
FIX_HEAD = "f151f0e6aca3577c5ee959a220c16e9756179649"
PREFIX = "docs/v0-18/evidence/"
EVIDENCE = PREFIX + "v0.18.0-final-closeout-preauth-update.json"
SNAPSHOT = PREFIX + "v0.18.0-final-closeout-preauth-github-snapshot.json"
OLD_EVIDENCE = PREFIX + "v0.18.0-final-closeout-status.json"
pytestmark = [pytest.mark.unit, pytest.mark.contract]


def load(path):
    return json.loads((ROOT / path).read_bytes())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def validate(value):
    assert value["task_id"] == "V0_18_FINAL_CLOSEOUT_DECISION"
    assert value["reviewed_main_sha"] == BASE
    assert value["previous_pr_head_sha"] == PREVIOUS
    assert value["preauth_status"] == "FIXED_TESTED_SCOPE"
    assert value["backend_lead_2"] == "FIXED_TESTED_SCOPE"
    assert value["engineering_technical_result"] == "PASS_TESTED_SCOPE"
    assert value["formal_closeout_result"] == "BLOCKED"
    assert value["engineering_release_eligibility"] == "TECHNICAL_CANDIDATE_NOT_APPROVED"
    assert value["production_readiness"] == "NOT_READY"
    previous = load(OLD_EVIDENCE)
    assert value["semantic_boundaries"] == previous["semantic_boundaries"]
    for field in (
        "historical_gate_statuses",
        "historical_approval_gaps",
        "production_risk_register",
    ):
        assert value[field] == previous[field]
    assert len(value["historical_approval_gaps"]["formal"]) == 29
    assert len(value["historical_approval_gaps"]["planning"]) == 12
    assert len(value["production_risk_register"]) == 15
    assert all(r["status"] == "OPEN_NOT_VALIDATED" for r in value["production_risk_register"])
    assert set(value["controls"]) == set("ABCDEFG")
    for row in value["controls"].values():
        assert row["reviewed_source_sha"] == BASE
        assert row["independent_acceptance_status"] == "PENDING"
        assert row["checks_performed"] and row["limitations"] and row["evidence_references"]
        prior = row["prior_independent_evidence_finding"]
        assert prior["review_id"] == 5561062016 and prior["reviewed_head_sha"] == PREVIOUS
        assert prior["not_formal_control_activation"]
        assert prior["new_current_head_acceptance_inferred"] is False
    assert not any(v for k, v in value["governance"].items() if k != "stop")
    assert value["governance"]["stop"]
    assert value["final_head_ci"] == "EXTERNAL_EXACT_HEAD_RECEIPT_REQUIRED_AFTER_COMMIT"


def test_canonical_append_sources_and_preserved_snapshots():
    value = load(EVIDENCE)
    validate(value)
    for path in (EVIDENCE, SNAPSHOT):
        assert (ROOT / path).read_bytes() == canonical(load(path))
    for field in ("source_evidence_sha256", "artifact_sha256"):
        for path, expected in value[field].items():
            assert sha((ROOT / path).read_bytes()) == expected, path
    for path, expected in value["preserved_snapshot_sha256"].items():
        assert sha((ROOT / path).read_bytes()) == sha(historical_bytes(path, PREVIOUS)) == expected
    for path, expected in value["current_main_source_sha256"].items():
        assert sha((ROOT / path).read_bytes()) == sha(historical_bytes(path, BASE)) == expected
    previous = load(OLD_EVIDENCE)
    assert previous["reviewed_main_sha"] == OLD_MAIN
    assert previous["backend_lead_2"] == "PREAUTH_RACE_NOT_TESTED_PENDING"
    original_test = "backend/tests/forecast_intelligence/test_v0_18_final_closeout_status.py"
    assert (
        sha(historical_bytes(original_test, PREVIOUS))
        == previous["source_evidence_sha256"][original_test]
    )


def test_review_merge_and_exact_head_actual_ci_are_not_approval_substitutes():
    snapshot = load(SNAPSHOT)
    row = snapshot["preauth_pr"]
    assert row["number"] == 733 and row["merged"] and row["state"] == "closed"
    assert row["head_sha"] == FIX_HEAD and row["merge_sha"] == BASE
    parents = (
        subprocess.check_output(["git", "rev-list", "--parents", "-n", "1", BASE], cwd=ROOT)
        .decode()
        .split()[1:]
    )
    assert parents == row["parents"] == [OLD_MAIN, FIX_HEAD]
    review = snapshot["preauth_review"]
    assert review["id"] == 5561705476 and review["commit_id"] == FIX_HEAD
    assert review["state"] == "COMMENTED"
    assert review["submitted_at"] < row["merged_at"]
    for text in ("REVIEW_RESULT=PASS", "PREAUTH_DUPLICATE_CONSUMPTION_FIX_ONLY", "AI-assisted"):
        assert text in review["body"]
    assert snapshot["review_scope"] == "RECORDED_AI_ASSISTED_PREAUTH_FIX_ONLY_NOT_A_G_ACCEPTANCE"
    prior = snapshot["previous_closeout_review"]
    assert prior["id"] == 5561062016 and prior["commit_id"] == PREVIOUS
    assert prior["state"] == "COMMENTED"
    assert "PASS_AS_FAITHFUL_CLOSEOUT_STATUS_PACKAGE" in prior["body"]
    assert "Do not modify the committed PENDING statuses to PASS" in prior["body"]
    release = snapshot["latest_release"]
    assert release["tag_name"] == "v0.17.0"
    assert release["draft"] is release["prerelease"] is False
    for name, run_id, head, event, success, skipped in (
        ("preauth_pr_ci", 39097619239, FIX_HEAD, "pull_request", 12, 0),
        ("preauth_main_ci", 39105220096, BASE, "push", 4, 8),
        ("previous_closeout_ci", 39045692189, PREVIOUS, "pull_request", 12, 0),
    ):
        run = snapshot[name]
        assert run["id"] == run_id and run["head_sha"] == head and run["event"] == event
        assert run["status"] == "completed" and run["conclusion"] == "success"
        assert run["run_attempt"] == 1 and len(run["jobs"]) == 12
        assert all(j["status"] == "completed" for j in run["jobs"])
        assert sum(j["conclusion"] == "success" for j in run["jobs"]) == success
        assert sum(j["conclusion"] == "skipped" for j in run["jobs"]) == skipped
        assert all(j["conclusion"] in {"success", "skipped"} for j in run["jobs"])


def test_red_two_green_rounds_and_current_postgres_security_regression():
    value = load(EVIDENCE)
    fix = load(PREFIX + "preauth-concurrent-login-fix-r1/evidence.json")
    original = load(PREFIX + "preauth-concurrent-login-fix-r1/original-red/original-evidence.json")
    assert original["result"] == "RED_CONFIRMED"
    assert original["observations"]["successful_login_count"] == 2
    for run in fix["repeat_runs"].values():
        proof = load(run["concurrent_proof"])
        assert proof["successful_login_count"] == proof["new_auth_session_count"] == 1
        assert proof["login_success_audit_count"] == proof["independently_valid_cookie_count"] == 1
        assert proof["request_a_status"] == 401 and proof["request_b_status"] == 200
        assert proof["me_b_status"] == 200 and proof["b_transaction_before_a_resume"] == "committed"
        assert proof["a_transaction_final_status"] == "aborted"
    runtime = value["current_local_security_regression"]
    junit = ET.parse(ROOT / runtime["junit"])
    assert len(junit.findall(".//testcase")) == runtime["tests"]
    assert not any(junit.findall(".//" + tag) for tag in ("failure", "error", "skipped"))
    proofs = [
        json.loads(p.attrib["value"])
        for p in junit.findall(".//property")
        if p.attrib.get("name") == "REVOKE_READ_PROOF"
    ]
    assert len(proofs) == 35
    assert all(sum(p["positive_control_counts"].values()) > 0 for p in proofs)
    assert all(
        not p["sensitive_response_sent"] and not any(p["post_commit_counts"].values())
        for p in proofs
    )
    current = [
        json.loads(p.attrib["value"])
        for p in junit.findall(".//property")
        if p.attrib.get("name") == "PREAUTH_REPRO"
    ]
    concurrent = next(p for p in current if "successful_login_count" in p)
    assert concurrent["successful_login_count"] == concurrent["new_auth_session_count"] == 1
    assert concurrent["login_success_audit_count"] == 1
    assert concurrent["request_a_status"] == 401 and concurrent["me_b_status"] == 200
    assert concurrent["database"]["preauth"]["revoked"]
    assert concurrent["database"]["preauth"]["revoke_reason"] == "LOGIN_ROTATION"
    for path, expected in concurrent["source_sha256"].items():
        assert sha((ROOT / path).read_bytes()) == expected
    manifest = load(runtime["owned_manifest"])
    assert manifest["exit"] == 0 and manifest["cleanup"]["state"] == "STOPPED"
    assert manifest["cleanup"]["listener_closed"] and manifest["cleanup"]["postmaster_absent"]
    for path in value["ci_junit_artifacts"].values():
        tree = ET.parse(ROOT / path)
        assert not tree.findall(".//failure") and not tree.findall(".//error")
        cases = [
            c for c in tree.findall(".//testcase") if "preauth_repro_r1" in c.get("classname", "")
        ]
        assert len(cases) == 13 and all(c.find("skipped") is None for c in cases)


def test_current_pr_contains_no_extra_production_changes():
    sync = load(EVIDENCE)["main_sync_merge"]
    parents = (
        subprocess.check_output(["git", "rev-list", "--parents", "-n", "1", sync["sha"]], cwd=ROOT)
        .decode()
        .split()[1:]
    )
    assert parents == sync["parents"] == [PREVIOUS, BASE]
    changed = (
        subprocess.check_output(["git", "diff", "--name-only", BASE], cwd=ROOT)
        .decode()
        .splitlines()
    )
    assert not any(
        p.startswith(("backend/app/", "frontend/", "backend/alembic/", ".github/"))
        or p in {"pyproject.toml", "uv.lock"}
        for p in changed
    )
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", PREVIOUS, "HEAD"], cwd=ROOT
        ).returncode
        == 0
    )
    assert (
        subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT).returncode
        == 0
    )


@pytest.mark.parametrize(
    "change", ["preauth", "gate", "risk", "acceptance", "owner", "release", "complete", "ready"]
)
def test_unsupported_completion_or_risk_acceptance_remains_rejected(change):
    value = copy.deepcopy(load(EVIDENCE))
    if change == "preauth":
        value["preauth_status"] = "ALL_AUTHENTICATION_RISKS_ELIMINATED"
    elif change == "gate":
        value["historical_gate_statuses"]["G01"] = "PASS"
    elif change == "risk":
        value["production_risk_register"][0]["status"] = "CLOSED"
    elif change == "acceptance":
        value["controls"]["A"]["independent_acceptance_status"] = "PASS"
    elif change == "owner":
        value["governance"]["owner_historical_risk_acceptance"] = True
    elif change == "complete":
        value["formal_closeout_result"] = "PASS"
    elif change == "ready":
        value["production_readiness"] = "READY"
    else:
        value["engineering_release_eligibility"] = "APPROVED"
    with pytest.raises(AssertionError):
        validate(value)
