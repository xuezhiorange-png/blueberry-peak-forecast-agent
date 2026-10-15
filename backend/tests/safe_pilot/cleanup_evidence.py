"""Publish explicit cancellation-correction artifacts; never private PG contents.

Usage: python -m backend.tests.safe_pilot.cleanup_evidence NEW_SUCCESSFUL_RUN
Output is exclusively new R1 correction evidence; existing S5 archives untouched.
"""

import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from backend.tests.historical_source import historical_bytes
from backend.tests.safe_pilot.evidence import EVIDENCE as OLD_EVIDENCE
from backend.tests.safe_pilot.evidence import R1_CHECKPOINT, ROOT
from backend.tests.safe_pilot.operations import assert_redacted

TASK = "V0_18_S5_SIGTERM_OWNED_POSTGRES_CLEANUP_CORRECTION_R1"
ARCHIVE = ROOT / "docs/v0-18/evidence/s5-sigterm-cleanup-correction-r1"
EVIDENCE = ROOT / "docs/v0-18/evidence/s5-sigterm-cleanup-correction-r1.json"
SOURCES = (
    "backend/tests/safe_pilot/run.py",
    "backend/tests/safe_pilot/test_runner_cleanup.py",
    "backend/tests/safe_pilot/cleanup_evidence.py",
    "backend/tests/safe_pilot/evidence.py",
    "backend/tests/forecast_intelligence/test_v0_18_s5_safe_pilot_contract.py",
    "backend/tests/forecast_intelligence/test_v0_18_s5_cleanup_correction_contract.py",
    "docs/v0-18/s5/sigterm-owned-postgres-cleanup-correction-r1.md",
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def publish(run):
    assert not EVIDENCE.exists() and not ARCHIVE.exists(), "REFUSE_EVIDENCE_OVERWRITE"
    old = json.loads(OLD_EVIDENCE.read_bytes())
    assert OLD_EVIDENCE.read_bytes() == historical_bytes(
        str(OLD_EVIDENCE.relative_to(ROOT)), R1_CHECKPOINT
    )
    for group in ("frozen_history_sha256", "v0_18_historical_evidence_sha256"):
        for path, expected in old[group].items():
            assert sha((ROOT / path).read_bytes()) == expected
    for path, entry in old["artifacts"].items():
        assert sha((ROOT / path).read_bytes()) == entry["sha256"]
    manifest = json.loads((run / "owned-resources.json").read_bytes())
    assert manifest["exit"] == manifest["shutdown_exit"] == 0
    assert manifest["backend_exit"] == manifest["browser_exit"] == 0
    assert "26 passed" in (run / "browser.log").read_text()
    assert sha((run / "execution.log").read_bytes()) == manifest["execution_sha256"]
    assert manifest["cleanup"]["state"] == "STOPPED"
    for path, expected in manifest["source_sha256"].items():
        assert sha((ROOT / path).read_bytes()) == expected, path
    tree = ET.fromstring((run / "backend.xml").read_bytes())
    assert not any(tree.findall(".//" + tag) for tag in ("failure", "error", "skipped"))
    cases = [
        case
        for case in tree.findall(".//testcase")
        if "test_runner_cleanup" in case.attrib.get("classname", "")
    ]
    assert len(cases) == 8
    password = (run / "private-password").read_text().strip()
    ARCHIVE.mkdir()
    artifacts = {}

    def copy(source, destination):
        raw = source.read_bytes()
        assert_redacted(raw.decode(), [password])
        published = raw.replace(str(ROOT).encode(), b"<S5_WORKTREE>")
        published = published.replace(b"/Users/charles", b"<OPERATOR_HOME>")
        target = ARCHIVE / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(published)
        artifacts[str(target.relative_to(ROOT))] = {
            "sha256": sha(published),
            "raw_sha256": sha(raw),
            "source_path": str(source),
            "redaction": "OPERATOR_HOME_AND_WORKTREE_ONLY",
        }

    for name in (
        "owned-resources.json",
        "backend.xml",
        "execution.log",
        "postgres.log",
        "browser.log",
    ):
        copy(run / name, "full-run/" + name)
    matrix = []
    for case in cases:
        properties = {
            p.attrib["name"]: p.attrib["value"] for p in case.findall("./properties/property")
        }
        name = case.attrib["name"]
        row = {"case": name, "result": "PASS", "resources": []}
        if "owned_resource_evidence" in properties:
            resources = Path(properties["owned_resource_evidence"])
            assert resources.name.startswith("SYNTHETIC-s5-cancel-")
            for directory in sorted(resources.iterdir()):
                owned = directory / "SYNTHETIC-owned"
                report = json.loads((owned / "owned-resources.json").read_bytes())
                teardown = json.loads((directory / "fixture-cleanup.json").read_bytes())
                assert teardown["postgres_status_after_fixture_cleanup"] == 3
                assert teardown["postmaster_absent_after_fixture_cleanup"] is True
                baseline = "baseline_reproduces" in name
                executed = json.loads((directory / "executed-source.json").read_bytes())
                if baseline:
                    assert report["exit"] != 0 and "shutdown_exit" not in report
                    assert teardown["postmaster_existed_before_fixture_cleanup"] is True
                    assert executed["kind"] == "FIXED_GIT_BASELINE_REPRO_ONLY"
                    assert executed["commit"] == R1_CHECKPOINT
                    assert (
                        executed["sha256"]
                        == old["source_evidence_sha256"]["backend/tests/safe_pilot/run.py"]
                    )
                else:
                    assert teardown["runner_process_exit"] == report["exit"]
                    assert executed["kind"] == "CURRENT_RUNTIME_SOURCE"
                    assert executed["sha256"] == sha(
                        (ROOT / "backend/tests/safe_pilot/run.py").read_bytes()
                    )
                    assert report["shutdown_exit"] == 0
                    assert report["cleanup"]["state"] == "STOPPED"
                    assert teardown["postmaster_existed_before_fixture_cleanup"] is False
                    assert report["cleanup"]["postmaster_absent"]
                    assert report["cleanup"]["listener_closed"]
                prefix = name + "/" + directory.name + "/"
                private_password = (owned / "private-password").read_text().strip()
                for item in ("owned-resources.json", "execution.log", "postgres.log"):
                    assert_redacted((owned / item).read_text(), [private_password])
                    copy(owned / item, prefix + item)
                copy(directory / "runner.log", prefix + "runner.log")
                copy(directory / "fixture-cleanup.json", prefix + "fixture-cleanup.json")
                copy(directory / "executed-source.json", prefix + "executed-source.json")
                row["resources"].append(
                    {
                        "archive": prefix,
                        "baseline_leak_observed": baseline,
                        "post_fixture_postgres_status": 3,
                        "manifest_exit": report["exit"],
                        "observed_process_exit": teardown["runner_process_exit"],
                        "executed_source": executed,
                    }
                )
        matrix.append(row)
    value = {
        "task_id": TASK,
        "synthetic": True,
        "pr_number": 726,
        "previous_pr_head": R1_CHECKPOINT,
        "base_main_sha": subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=ROOT)
        .decode()
        .strip(),
        "source_evidence_sha256": {p: sha((ROOT / p).read_bytes()) for p in SOURCES},
        "previous_evidence_sha256": sha(OLD_EVIDENCE.read_bytes()),
        "historical_original_source_sha256": old["source_evidence_sha256"][
            "backend/tests/safe_pilot/run.py"
        ],
        "historical_source_checkpoint": R1_CHECKPOINT,
        "historical_expected_hashes_changed": False,
        "frozen_history_count": len(old["frozen_history_sha256"]),
        "previous_s5_artifact_count": len(old["artifacts"]),
        "case_matrix": matrix,
        "local_backend_passed": len(tree.findall(".//testcase")),
        "browser_passed": 26,
        "artifacts": artifacts,
        "cleanup_contract": {
            "started_boolean_not_authoritative": True,
            "exclusive_directory_device_inode": True,
            "postmaster_pid_file_and_process_data_directory": True,
            "pid_reuse_rejected": True,
            "business_process_group_cancelled": True,
            "startup_settled_before_directory_scoped_stop": True,
            "repeated_sigterm_sigint_do_not_interrupt_cleanup": True,
            "independent_cluster_untouched": True,
            "process_pid_file_and_listener_verified_after_stop": True,
            "private_evidence_preserved": True,
            "global_or_port_based_process_killing": False,
        },
        "limitations": {
            "sigkill_power_loss_cleanup_guaranteed": False,
            "platform": "LOCAL_MACOS_POSIX_PLUS_PENDING_LINUX_EXACT_HEAD_CI",
            "production_readiness": "NOT_READY",
            "production_code_changed": False,
            "real_accounts_or_production_database_accessed": False,
        },
        "ci": {
            "status": "PENDING_AT_COMMIT_REQUIRE_NEW_EXACT_HEAD_RECEIPT",
            "old_green_reused": False,
        },
        "governance": {
            key: False
            for key in (
                "s5_formal_complete",
                "ready_authorized",
                "merge_authorized",
                "deploy_authorized",
                "release_authorized",
                "s6_authorized",
            )
        },
    }
    with EVIDENCE.open("xb") as output:
        output.write(canonical(value))


if __name__ == "__main__":
    publish(Path(sys.argv[1]).resolve())
