"""Offline integrity of this fix's real executions, not a runtime-test substitute."""

import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from backend.tests.historical_source import historical_bytes

ROOT = Path(__file__).resolve().parents[3]
BASE = "816d8299f007eab7da140fc5c7547d941c026f8f"
PREAUTH_DELIVERY = "f151f0e6aca3577c5ee959a220c16e9756179649"
EVOLVED_ROUND_SOURCES = {
    "backend/app/main.py",
}
# These two authorized test adaptations do not rewrite their delivery evidence.
ADAPTED_TEST_SOURCES = {
    "backend/tests/business_access/test_contract.py",
    "backend/tests/mcp/test_v0_18_s3_contract.py",
    "backend/tests/local_auth/test_preauth_fix_evidence_contract.py",
    "backend/tests/revoke_read_race/test_evidence_contract.py",
}
FOLDER = "docs/v0-18/evidence/preauth-concurrent-login-fix-r1/"
pytestmark = [pytest.mark.unit, pytest.mark.contract]


def load(relative):
    return json.loads((ROOT / relative).read_bytes())


def checked(relative, expected, *, commit=None):
    path = ROOT / relative
    assert path.resolve().is_relative_to(ROOT)
    raw = historical_bytes(relative, commit) if commit is not None else path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected
    return raw


def test_canonical_evidence_sources_and_unchanged_history():
    value = load(FOLDER + "evidence.json")
    assert (ROOT / (FOLDER + "evidence.json")).read_bytes() == (
        json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    ).encode()
    for field in ("source_evidence_sha256", "artifact_sha256"):
        for relative, expected in value[field].items():
            checked(
                relative,
                expected,
                commit=(
                    PREAUTH_DELIVERY
                    if field == "source_evidence_sha256" and relative in ADAPTED_TEST_SOURCES
                    else None
                ),
            )
    assert value["production_files"] == ["backend/app/local_auth/service.py"]
    # Audit the original delivery interval, never a future HEAD or worktree.
    changed = (
        subprocess.check_output(
            ["git", "diff", "--name-only", BASE, PREAUTH_DELIVERY, "--", "backend/app"], cwd=ROOT
        )
        .decode()
        .splitlines()
    )
    assert changed == value["production_files"]
    assert not subprocess.check_output(
        [
            "git",
            "diff",
            BASE,
            PREAUTH_DELIVERY,
            "--",
            ".github",
            "backend/alembic",
            "frontend/src",
            "frontend/e2e",
            "pyproject.toml",
            "uv.lock",
        ],
        cwd=ROOT,
    ).strip()
    old_docs = subprocess.check_output(
        ["git", "diff", "--name-status", "--diff-filter=MDR", BASE, PREAUTH_DELIVERY, "--", "docs"],
        cwd=ROOT,
    )
    assert not old_docs.strip()
    assert value["final_head_ci"] == "POST_COMMIT_EXTERNAL_EXACT_HEAD_RECEIPT_REQUIRED"
    assert all(v is False for k, v in value["governance"].items() if k != "stop")
    assert value["governance"]["stop"] is True


def test_red_capsule_and_original_probe_are_unchanged():
    value = load(FOLDER + "evidence.json")
    original = load(FOLDER + "original-red/original-evidence.json")
    assert original["result"] == "RED_CONFIRMED"
    assert original["observations"]["successful_login_count"] == 2
    for old_path, relative in value["original_red_archive_mapping"].items():
        checked(relative, original["artifact_sha256"][old_path])
    checked(
        "backend/tests/preauth_repro_r1/test_concurrent_login.py",
        "35d4c982c39c8737d8f43b949f2228a7c0cc9ddb08cffdd350aedbffaf9bafdb",
    )
    data = load("docs/v0-18/evidence/s3-mcp-service-account-safety-r1.json")
    path = "backend/app/local_auth/service.py"
    raw = historical_bytes(path, data["base_main_sha"])
    assert hashlib.sha256(raw).hexdigest() == data["unchanged_business_sources_sha256"][path]


@pytest.mark.parametrize("name", ["round1", "round2"])
def test_two_real_postgres_rounds_meet_the_original_invariant(name):
    run = load(FOLDER + "evidence.json")["repeat_runs"][name]
    proof = load(run["concurrent_proof"])
    for relative, expected in proof["source_sha256"].items():
        checked(
            relative,
            expected,
            commit=PREAUTH_DELIVERY if relative in EVOLVED_ROUND_SOURCES else None,
        )
    assert proof["classification"] == "GREEN_NOT_REPRODUCED"
    assert proof["deterministic_barrier"]
    assert proof["request_b_status"] == proof["me_b_status"] == 200
    assert proof["request_a_status"] == proof["me_a_status"] == 401
    assert proof["successful_login_count"] == proof["new_auth_session_count"] == 1
    assert proof["login_success_audit_count"] == proof["independently_valid_cookie_count"] == 1
    assert proof["database"]["preauth"]["revoked"]
    assert proof["database"]["preauth"]["revoke_reason"] == "LOGIN_ROTATION"
    assert proof["b_transaction_before_a_resume"] == "committed"
    assert proof["a_transaction_final_status"] == "aborted"
    assert proof["transactions"]["A"]["pid"] != proof["transactions"]["B"]["pid"]
    assert proof["transactions"]["A"]["transaction"] != proof["transactions"]["B"]["transaction"]
    events = [x["event"] for x in proof["timeline"]]
    assert events.index("B_COMMIT_INDEPENDENTLY_CONFIRMED_BEFORE_A_RESUME") < events.index(
        "A_RESUMED_WITH_ORIGINAL_OBJECT"
    )
    owned = load(run["owned_manifest"])
    assert owned["exit"] == 0 and owned["cleanup"]["state"] == "STOPPED"
    assert owned["cleanup"]["listener_closed"] and owned["cleanup"]["postmaster_absent"]
    junit = ET.parse(ROOT / run["junit"])
    assert not junit.findall(".//failure") and not junit.findall(".//error")
    assert not junit.findall(".//skipped")
    assert len(junit.findall(".//testcase")) >= 13


def test_revoke_read_zero_work_and_complete_browser_results():
    value = load(FOLDER + "evidence.json")
    junit = ET.parse(ROOT / value["related_regression"]["junit"])
    assert not junit.findall(".//failure") and not junit.findall(".//error")
    proofs = [
        json.loads(p.attrib["value"])
        for p in junit.findall(".//property")
        if p.attrib.get("name") == "REVOKE_READ_PROOF"
    ]
    assert len(proofs) == 35
    for proof in proofs:
        assert not proof["sensitive_response_sent"]
        assert sum(proof["positive_control_counts"].values()) > 0
        assert all(v == 0 for v in proof["post_commit_counts"].values())
    stats = load(value["frontend_e2e"]["report"])["stats"]
    assert stats["expected"] == 144
    assert stats["unexpected"] == stats["skipped"] == stats["flaky"] == 0
    assert load(value["frontend_e2e"]["owned_manifest"])["cleanup"]["state"] == "STOPPED"


def test_missing_git_object_or_wrong_expected_hash_fails():
    proof = load(load(FOLDER + "evidence.json")["repeat_runs"]["round1"]["concurrent_proof"])
    for relative in EVOLVED_ROUND_SOURCES:
        expected = proof["source_sha256"][relative]
        checked(relative, expected, commit=PREAUTH_DELIVERY)
        with pytest.raises(AssertionError):
            checked(relative, "0" * 64, commit=PREAUTH_DELIVERY)
        with pytest.raises(AssertionError):
            checked(relative, expected, commit="0" * 40)
    with pytest.raises(AssertionError):
        historical_bytes("backend/app/local_auth/service.py", "0" * 40)
    with pytest.raises(AssertionError):
        historical_bytes("backend/app/local_auth/SYNTHETIC_NONEXISTENT.py", BASE)
    with pytest.raises(AssertionError):
        checked("backend/app/local_auth/service.py", "0" * 64)
    for relative in ADAPTED_TEST_SOURCES:
        expected = load(FOLDER + "evidence.json")["source_evidence_sha256"][relative]
        assert checked(relative, expected, commit=PREAUTH_DELIVERY) == historical_bytes(
            relative, PREAUTH_DELIVERY
        )
        with pytest.raises(AssertionError):
            checked(relative, "0" * 64, commit=PREAUTH_DELIVERY)
        with pytest.raises(AssertionError):
            checked(relative, expected, commit="0" * 40)
