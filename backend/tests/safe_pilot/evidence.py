"""Archive actual S5 artifacts without overwrite, then print canonical evidence.

Usage: python -m backend.tests.safe_pilot.evidence RAW_RUN AUDIT_AND_CHECK_DIR
Never publishes a dump, account password, Cookie, TLS key or MCP policy.
"""

import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = "89641834ab7a0bd902a23f9243325da5c163d518"
# Only the offline publisher changed after the runtime run; its exact then-current
# bytes were preserved in this local source checkpoint before the correction.
PUBLISHER_CHECKPOINT = "23f2384517fc24badaa130a20d137b81260e7f7d"
ARCHIVE = ROOT / "docs/v0-18/evidence/s5-safe-pilot-r1"
EVIDENCE = ROOT / "docs/v0-18/evidence/s5-isolated-synthetic-safe-pilot-r1.json"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def junit(raw):
    tree = ET.fromstring(raw)
    cases = tree.findall(".//testcase")
    assert cases and not tree.findall(".//failure") and not tree.findall(".//error")
    assert not tree.findall(".//skipped")
    return {
        "passed": len(cases),
        "failed": 0,
        "skipped": 0,
        "cases": [c.attrib.get("classname", "") + "::" + c.attrib["name"] for c in cases],
    }


def sources():
    files = []
    for relative in ("backend/tests/safe_pilot", "docs/v0-18/s5"):
        files.extend(
            p for p in (ROOT / relative).rglob("*") if p.is_file() and "__pycache__" not in p.parts
        )
    files.append(ROOT / "backend/tests/forecast_intelligence/test_v0_18_s5_safe_pilot_contract.py")
    return {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sorted(files)}


def generate(index):
    previous = json.loads(
        (ROOT / "docs/v0-18/evidence/s4-dashboard-authorized-business-flow-r1.json").read_text()
    )
    frozen = previous["frozen_history_sha256"]
    assert len(frozen) == 260
    for p, expected in frozen.items():
        assert sha((ROOT / p).read_bytes()) == expected
    # S4 and the subsequent S1-S3 implementation snapshots are also immutable.
    bindings = {}
    for p in (
        subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", "-z", BASE, "docs/v0-18"], cwd=ROOT
        )
        .decode()
        .rstrip("\0")
        .split("\0")
    ):
        old = subprocess.check_output(["git", "show", f"{BASE}:{p}"], cwd=ROOT)
        assert (ROOT / p).read_bytes() == old
        bindings[p] = sha(old)
    for relative, row in index.items():
        assert sha((ROOT / relative).read_bytes()) == row["sha256"]
    backend = junit((ARCHIVE / "backend.xml").read_bytes())
    assert any("full_backup_restore_reapproval" in c for c in backend["cases"])
    assert any("all_eight_real_tls_payload_parity" in c for c in backend["cases"])
    assert any("revocation_committed_before_release" in c for c in backend["cases"])
    assert any("revoke_during_canonical_read" in c for c in backend["cases"])
    manifest = json.loads((ARCHIVE / "owned-resources.json").read_text())
    for path, expected in manifest["source_sha256"].items():
        if path == "backend/tests/safe_pilot/evidence.py":
            historical = subprocess.check_output(
                ["git", "show", f"{PUBLISHER_CHECKPOINT}:{path}"], cwd=ROOT
            )
            assert sha(historical) == expected, path
        else:
            assert sha((ROOT / path).read_bytes()) == expected, path
    assert (
        manifest["backend_exit"]
        == manifest["browser_exit"]
        == manifest["shutdown_exit"]
        == manifest["exit"]
        == 0
    )
    audit = json.loads((ARCHIVE / "npm-audit.json").read_text())
    return {
        "task_id": "V0_18_S5_ISOLATED_SYNTHETIC_SAFE_PILOT_READINESS_R1",
        "version": "0.18.0",
        "base_main_sha": BASE,
        "synthetic": True,
        "authorization": {
            "owner_s5_implementation_authorized": True,
            "real_pilot_deploy_authorized": False,
        },
        "source_evidence_sha256": sources(),
        "offline_publisher_correction": {
            "runtime_source_checkpoint": PUBLISHER_CHECKPOINT,
            "only_post_run_source_change": "backend/tests/safe_pilot/evidence.py",
            "reason": "NUL-separated Git filenames preserve Chinese screenshot paths",
            "current_publisher_validation": "OFFLINE_CONTRACT_PLUS_PENDING_EXACT_HEAD_CI",
            "runtime_modules_replaced_with_old_git_bytes": False,
        },
        "frozen_history_sha256": frozen,
        "v0_18_historical_evidence_sha256": bindings,
        "artifacts": index,
        "local_backend": backend,
        "acceptance": {
            key: "PASS_TESTED_ISOLATED_SCOPE"
            for key in (
                "https_configuration",
                "secret_configuration_fail_closed",
                "local_auth_and_csrf",
                "exact_resource_grants",
                "mcp_service_account_rotation",
                "pre_response_revocation",
                "legacy_controlled_ingress_denial",
                "unauthorized_business_reads_zero",
                "unauthorized_simulation_zero",
                "log_secret_redaction",
                "synthetic_backup",
                "synthetic_restore_hash_parity",
                "rollback_fail_closed",
            )
        },
        "backup": {
            "mechanism": "pg_dump_custom_and_pg_restore_into_new_uuid_database",
            "original_database_unchanged_during_backup": True,
            "post_restore_revoke_all_sessions_and_grants_before_listener": True,
            "old_passwords_invalidated_before_listener": True,
            "current_catalog_admin_explicit_reapproval_required": True,
            "mcp_policy_credentials_not_restored_from_backup": True,
            "private_archive_not_committed": True,
            "runtime_hashes_recorded_in": "backend.xml testcase properties",
        },
        "browser": {
            "suite": "dashboard-business-flow.spec.ts",
            "actual_https_postgres": True,
            "expected_case_count": 26,
            "result": "PASS",
            "projects": ["chromium-desktop", "chromium-mobile"],
            "viewports": [
                [1440, 900],
                [1280, 800],
                [1024, 768],
                [834, 1112],
                [390, 844],
                [360, 800],
            ],
            "screenshots": sum(p.endswith(".png") for p in index),
        },
        "dependency_audit": {
            "result": "COMPLETED_WITH_OPEN_ADVISORIES",
            "npm_metadata": audit["metadata"],
            "production_reachable_high_risk": "NOT_IDENTIFIED_IN_CURRENT_STATIC_SPA_SCOPE",
            "review": "docs/v0-18/s5/frontend-dependency-security-review-r1.md",
            "dependencies_changed": False,
        },
        "limitations": {
            "cross_host_revocation": "NOT_VALIDATED",
            "production_network_isolation": "NOT_VALIDATED",
            "mcp_topology": "SAME_HOST_POSIX_LOCAL_FILESYSTEM",
            "nfs": "NOT_VALIDATED",
            "windows": "NOT_VALIDATED",
            "real_ios_safari": "NOT_VALIDATED",
            "soft_keyboard": "NOT_VALIDATED",
            "screen_reader": "NOT_VALIDATED",
            "production_readiness": "NOT_READY",
            "rpo_rto_retention_capacity_owners": "PENDING_OWNER_DECISION",
            "real_accounts_or_grants_created": False,
            "current_actual_access": False,
            "new_forecast_or_model_experiment": False,
            "production_database_changed": False,
            "rollback_binary_downgrade_tested": False,
        },
        "prior_local_failures": [
            "First request lacked JSON Content-Type: middleware rejected 415 before ingress; "
            "corrected the test request, not production",
            "END_USER CSRF cannot login as admin; test now logs out then obtains PREAUTH, "
            "not a production bypass",
            "Plain HTTP negative client initially inherited a proxy; trust_env=False now "
            "forces the actual loopback TLS socket instead of an environment proxy response",
            "New credential-quarantine regression initially missed the SQL select import; "
            "test-only import corrected and full isolated acceptance rerun",
        ],
        "ci": {
            "result": "PENDING_AT_COMMIT_EXACT_HEAD_RECEIPT_REQUIRED",
            "old_green_ci_reused": False,
        },
        "governance": {
            key: False
            for key in (
                "s5_formal_complete",
                "ready_authorized",
                "merge_authorized",
                "deploy_authorized",
                "tag_authorized",
                "release_authorized",
                "s6_authorized",
            )
        },
    }


def archive(run, checks):
    raw_manifest = json.loads((run / "owned-resources.json").read_text())
    assert raw_manifest["exit"] == 0
    assert (
        raw_manifest["backend_exit"]
        == raw_manifest["browser_exit"]
        == raw_manifest["shutdown_exit"]
        == 0
    )
    assert "26 passed" in (run / "browser.log").read_text()
    # Explicit sources only; identical destination names from other suites are
    # never recursively merged. 'xb' rejects any accidental second publication.
    pairs = [
        (run / p, p)
        for p in ("backend.xml", "execution.log", "browser.log", "owned-resources.json")
    ]
    pairs += [
        (checks / p, p)
        for p in (
            "npm-audit.json",
            "npm-audit-production.json",
            "npm-paths.txt",
            "npm-production-tree.json",
            "unit.log",
            "frontend-build.log",
            "frontend-lint.log",
            "frontend-format.log",
            "typecheck.log",
            "ruff.log",
            "format.log",
            "mypy.log",
            "s5-first.log",
            "s5-final.log",
            "config-debug.log",
            "config-retest.log",
            "s5-credential-final.log",
        )
    ]
    pairs += [
        (p, "browser/" + str(p.relative_to(run / "browser")))
        for p in sorted((run / "browser").rglob("*.png"))
    ]
    index = {}
    for source, destination in pairs:
        raw = source.read_bytes()
        public = raw
        if source.suffix != ".png":
            text = raw.decode()
            for private, label in (
                (str(ROOT), "<S5_WORKTREE>"),
                (str(run), "<S5_RUN>"),
                (str(checks), "<S5_CHECKS>"),
                ("/Users/charles", "<OPERATOR_HOME>"),
            ):
                text = text.replace(private, label)
            text = re.sub(r"/private/var/folders/[^\s'\")]+", "<PRIVATE_TEST_TMP>", text)
            # Failure tracebacks can quote test source containing literal fixture
            # passwords. Preserve raw hashes privately, never publish those values
            # as log text even though the synthetic fixtures are public test code.
            for credential in (
                "SYNTHETIC-password-123",
                "SYNTHETIC-restored-user-password",
                "SYNTHETIC-restored-admin-password",
                "SYNTHETIC-rollback-reapproved-password",
                "SYNTHETIC_REPAIRED_KEY",
                "SYNTHETIC_S5_ROTATED_KEY",
            ):
                text = text.replace(credential, "<REDACTED_TEST_CREDENTIAL>")
            public = text.encode()
        from backend.tests.safe_pilot.operations import assert_redacted

        assert_redacted(
            public.decode(errors="ignore"), [(run / "private-password").read_text().strip()]
        )
        target = ARCHIVE / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(public)
        index[str(target.relative_to(ROOT))] = {
            "sha256": sha(public),
            "raw_source_sha256": sha(raw),
            "source_run": "S5_FINAL_ISOLATED_RUN"
            if source.is_relative_to(run)
            else "S5_LOCAL_CHECKS_AND_PRIOR_FAILURES",
            "source_path": str(
                source.relative_to(run)
                if source.is_relative_to(run)
                else source.relative_to(checks)
            ),
            "transform": "NONE"
            if public == raw
            else "operator_temp_and_test_credential_redaction_only",
        }
    with (ARCHIVE / "artifact-index.json").open("x") as output:
        json.dump(index, output, ensure_ascii=False, sort_keys=True, indent=2)
        output.write("\n")
    return index


if __name__ == "__main__":
    if len(sys.argv) == 3:
        bindings = archive(Path(sys.argv[1]), Path(sys.argv[2]))
    else:
        bindings = json.loads((ARCHIVE / "artifact-index.json").read_text())
    print(json.dumps(generate(bindings), ensure_ascii=False, sort_keys=True, indent=2))
