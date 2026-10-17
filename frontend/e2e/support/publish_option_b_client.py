"""Publish current-run client evidence, never overwrite an earlier archive."""

import argparse
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = "ebe50fbe250097a882407604a8482ca9cfdf6d9a"
DEST = ROOT / "docs/v0-18/evidence/option-b-client-fix-r1"


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def snapshot(run):
    assert not (run / "browser.log").exists(), "SNAPSHOT_MUST_PRECEDE_BROWSER"
    paths = sorted((ROOT / "frontend/src/dashboard").rglob("*"))
    paths += [
        ROOT / p
        for p in (
            "frontend/e2e/dashboard-business-flow.spec.ts",
            "frontend/e2e/dashboard-s6-acceptance.spec.ts",
            "frontend/e2e/option-b-client-binding.spec.ts",
            "frontend/e2e/support/option_b_binding_pg.py",
        )
    ]
    value = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "phase": "BEFORE_BROWSER_BUILD",
        "source_sha256": {
            str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in paths if p.is_file()
        },
    }
    with (run / "client-source-before-browser.json").open("xb") as output:
        output.write(canonical(value))


def publish(run):
    owned = json.loads((run / "owned-resources.json").read_bytes())
    assert owned["exit"] == owned["backend_exit"] == owned["browser_exit"] == 0
    assert owned["cleanup"]["state"] == "STOPPED" and owned["shutdown_exit"] == 0
    assert owned["cleanup"]["listener_closed"] and owned["cleanup"]["postmaster_absent"]
    before = json.loads((run / "client-source-before-browser.json").read_bytes())
    for path, expected in before["source_sha256"].items():
        assert sha((ROOT / path).read_bytes()) == expected, "SOURCE_DRIFT: " + path
    private_password = (run / "private-password").read_bytes().strip()
    archive = DEST / "green"
    archive.mkdir()
    artifacts = {}
    for name in (
        "owned-resources.json",
        "client-source-before-browser.json",
        "s6-executed-sources.json",
        "s6-toolchain.json",
        "backend.xml",
        "browser-results.json",
        "execution.log",
        "browser.log",
        "postgres.log",
    ):
        raw = (run / name).read_bytes()
        assert private_password not in raw, "PRIVATE_CREDENTIAL_IN_PUBLIC_OUTPUT"
        public = raw.replace(str(ROOT).encode(), b"<CLIENT_WORKTREE>")
        with (archive / name).open("xb") as output:
            output.write(public)
        artifacts[str((archive / name).relative_to(ROOT))] = {
            "sha256": sha(public),
            "raw_sha256": sha(raw),
            "source": str(run / name),
        }
    unit_source = Path("/tmp/option-b-client-full-unit-final2.json")
    unit_raw = unit_source.read_bytes()
    unit = json.loads(unit_raw)
    assert unit["numFailedTests"] == 0 and unit["numPassedTests"] == unit["numTotalTests"]
    unit_public = unit_raw.replace(str(ROOT).encode(), b"<CLIENT_WORKTREE>")
    (archive / "frontend-unit.json").write_bytes(unit_public)
    artifacts[str((archive / "frontend-unit.json").relative_to(ROOT))] = {
        "sha256": sha(unit_public),
        "raw_sha256": sha(unit_raw),
        "source": str(unit_source),
    }
    junit = ET.fromstring((run / "backend.xml").read_bytes())
    tests = list(junit.iter("testcase"))
    assert all(t.find("failure") is None and t.find("error") is None for t in tests)
    browser = json.loads((run / "browser-results.json").read_bytes())
    assert browser["stats"]["unexpected"] == browser["stats"]["flaky"] == 0
    source_paths = (
        subprocess.check_output(["git", "ls-tree", "-r", "--name-only", BASE], cwd=ROOT)
        .decode()
        .splitlines()
    )
    frozen = {
        p: sha((ROOT / p).read_bytes())
        for p in source_paths
        if p.startswith(("docs/v0-16/", "docs/v0-17/", "docs/v0-18/"))
    }
    for path, expected in frozen.items():
        assert sha(subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=ROOT)) == expected
    server_sources = (
        "backend/app/forecast_intelligence/what_if.py",
        "backend/app/forecast_intelligence/decision_schemas.py",
        "backend/app/forecast_intelligence/decision_service.py",
        "backend/app/forecast_intelligence/business_loss.py",
        "backend/app/area_yield/v015_research_cohort.py",
    )
    source_hashes = {p: sha((ROOT / p).read_bytes()) for p in server_sources}
    for p, expected in source_hashes.items():
        assert sha(subprocess.check_output(["git", "show", f"{BASE}:{p}"], cwd=ROOT)) == expected
    red = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in (DEST / "red").iterdir()}
    assert (
        red[str((DEST / "red/original-probes.json").relative_to(ROOT))]
        == "0a95616445def5634cfb68d12e4b7f70fad92127ec51dad64f15836c28e0820b"
    )
    evidence = {
        "task_id": "V0_18_OPTION_B_CLIENT_AUTHORITY_SCENARIO_BINDING_FIX_R1",
        "base_main_sha": BASE,
        "result": "LOCAL_GREEN_PENDING_EXACT_HEAD_CI_AND_INDEPENDENT_REVIEW",
        "original_red_sha256": red,
        "runtime_source_sha256": before["source_sha256"],
        "frozen_server_contract_sha256": source_hashes,
        "frozen_history_sha256": frozen,
        "artifacts": artifacts,
        "local_tests": {
            "frontend_unit_passed": unit["numPassedTests"],
            "backend_cases": len(tests),
            "browser": browser["stats"],
        },
        "owned_cleanup": owned["cleanup"],
        "binding_method": (
            "VERIFY_EXISTING_FROZEN_INPUT_COMMITMENT_AND_RAW_INPUT_STRINGS_NO_BUSINESS_RECALCULATION"
        ),
        "scenario_version_echo_added": False,
        "backend_contract_changed": False,
        "business_math_changed": False,
        "backend_reproduction_is_separate": True,
        "backend_reproduction_pass_claim": False,
        "governance": {
            "a_g_independent_acceptance": "PENDING",
            "h_owner_risk_acceptance": False,
            "governance_exception_approved": False,
            "version_closeout_formal_complete": False,
            "production_readiness": "NOT_READY",
            "ready_authorized": False,
            "merge_authorized": False,
            "tag_authorized": False,
            "release_authorized": False,
            "deploy_authorized": False,
            "stop": True,
        },
        "exact_head_ci": "PENDING_POST_COMMIT_SEPARATE_RECEIPT",
    }
    with (DEST / "evidence.json").open("xb") as output:
        output.write(canonical(evidence))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--snapshot-only", action="store_true")
    args = parser.parse_args()
    snapshot(args.run) if args.snapshot_only else publish(args.run)
