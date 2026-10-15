"""Publish only explicit fresh-run artifacts; duplicate provenance is an error."""

import base64
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from backend.tests.safe_pilot.operations import assert_redacted

ROOT = Path(__file__).resolve().parents[3]
BASE = "fc0b88cf222567e4821a9d11589331f6a7963e04"
ARCHIVE = ROOT / "docs/v0-18/evidence/s6-business-security-r1"
EVIDENCE = ROOT / "docs/v0-18/evidence/s6-business-and-security-acceptance-r1.json"


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def browser_cases(suite):
    for spec in suite.get("specs", []):
        for test in spec["tests"]:
            yield spec, test
    for child in suite.get("suites", []):
        yield from browser_cases(child)


def stage_chain():
    """Query immutable merged PR identities and actual push run results afresh."""
    chain = []
    for stage, number, run_id, expected in (
        ("S1", 717, 38263983686, "success"),
        ("S1_D03", 718, 38326155853, "failure"),
        ("S1_CANARY_CORRECTION", 721, 38425016611, "success"),
        ("S2", 723, 38578960598, "success"),
        ("S3", 724, 38657747572, "success"),
        ("S4", 725, 38673985694, "success"),
        ("S5", 726, 38703671252, "success"),
    ):
        pr = json.loads(
            subprocess.check_output(
                [
                    "gh",
                    "pr",
                    "view",
                    str(number),
                    "--json",
                    "number,state,mergeCommit,headRefOid,baseRefOid,url",
                ],
                cwd=ROOT,
            )
        )
        run = json.loads(
            subprocess.check_output(
                [
                    "gh",
                    "run",
                    "view",
                    str(run_id),
                    "--json",
                    "headSha,event,status,conclusion,attempt,jobs",
                    "--jq",
                    "{headSha,event,status,conclusion,attempt,jobs:[.jobs[]|{name,status,conclusion}]}",
                ],
                cwd=ROOT,
            )
        )
        assert pr["state"] == "MERGED"
        assert run["headSha"] == pr["mergeCommit"]["oid"]
        assert run["event"] == "push" and run["status"] == "completed"
        assert run["conclusion"] == expected
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", pr["mergeCommit"]["oid"], BASE],
            cwd=ROOT,
            check=True,
        )
        chain.append({"stage": stage, "pr": pr, "main_ci_run_id": run_id, "ci": run})
    assert chain[-1]["ci"]["attempt"] == 2
    return chain


def publish(run):
    assert not EVIDENCE.exists() and not ARCHIVE.exists(), "REFUSE_EVIDENCE_OVERWRITE"
    manifest = json.loads((run / "owned-resources.json").read_bytes())
    assert manifest["exit"] == manifest["backend_exit"] == manifest["browser_exit"] == 0
    assert manifest["cleanup"]["state"] == "STOPPED"
    assert manifest["cleanup"]["listener_closed"] and manifest["cleanup"]["postmaster_absent"]
    assert manifest["shutdown_exit"] == 0 and manifest["execution_secret_scan"] == "PASS"
    assert manifest["execution_sha256"] == sha((run / "execution.log").read_bytes())
    executed = json.loads((run / "s6-executed-sources.json").read_bytes())["source_sha256"]
    for path, expected in (manifest["source_sha256"] | executed).items():
        assert sha((ROOT / path).read_bytes()) == expected, "EXECUTED_SOURCE_DRIFT: " + path
    junit = ET.fromstring((run / "backend.xml").read_bytes())
    assert not any(junit.findall(".//" + name) for name in ("failure", "error", "skipped"))
    cases = junit.findall(".//testcase")
    browser = json.loads((run / "browser-results.json").read_bytes())
    assert (
        browser["stats"]["unexpected"]
        == browser["stats"]["flaky"]
        == browser["stats"]["skipped"]
        == 0
    )
    assert not browser.get("errors")
    stages = stage_chain()
    ARCHIVE.mkdir()
    artifacts, provenance = {}, set()
    secrets = [(run / "private-password").read_text().strip()]

    def copy(raw, destination, *, source, identity=None):
        target = ARCHIVE / destination
        assert not target.exists(), "DUPLICATE_ARCHIVE_DESTINATION"
        if identity is not None:
            assert identity not in provenance, "DUPLICATE_SCREENSHOT_PROVENANCE"
            provenance.add(identity)
        if target.suffix != ".png":
            assert_redacted(raw.decode(), secrets)
            published = raw.replace(str(ROOT).encode(), b"<S6_WORKTREE>")
            published = published.replace(b"/Users/charles", b"<OPERATOR_HOME>")
        else:
            published = raw
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(published)
        relative = str(target.relative_to(ROOT))
        artifacts[relative] = {
            "sha256": sha(published),
            "raw_sha256": sha(raw),
            "source_path": str(source),
            "provenance": identity,
        }
        return relative

    for name in (
        "owned-resources.json",
        "s6-executed-sources.json",
        "s6-toolchain.json",
        "backend.xml",
        "execution.log",
        "postgres.log",
        "browser.log",
        "browser-results.json",
    ):
        copy((run / name).read_bytes(), "run/" + name, source=run / name)
    screenshots, browser_matrix = [], []
    for suite in browser["suites"]:
        for spec, test in browser_cases(suite):
            assert test["status"] == "expected" and len(test["results"]) == 1
            result = test["results"][0]
            assert result["status"] == "passed"
            browser_matrix.append(
                {
                    "spec": spec["file"],
                    "case": spec["title"],
                    "project": test["projectName"],
                    "status": "PASS",
                }
            )
            if Path(spec["file"]).name != "dashboard-s6-acceptance.spec.ts":
                continue
            for index, attachment in enumerate(result.get("attachments", [])):
                identity = json.dumps(
                    [spec["file"], spec["title"], test["projectName"], index, attachment["name"]]
                )
                key = sha(identity.encode())[:24]
                if attachment["contentType"] == "image/png":
                    path = Path(attachment["path"])
                    assert path.is_relative_to(run / "browser"), "SCREENSHOT_OUTSIDE_CURRENT_RUN"
                    name = copy(
                        path.read_bytes(),
                        "screenshots/" + key + ".png",
                        source=path,
                        identity=identity,
                    )
                    screenshots.append(
                        {
                            "path": name,
                            "spec": spec["file"],
                            "case": spec["title"],
                            "project": test["projectName"],
                            "attachment": attachment["name"],
                            "sha256": artifacts[name]["sha256"],
                        }
                    )
                elif attachment["contentType"] == "application/json":
                    raw = (
                        Path(attachment["path"]).read_bytes()
                        if "path" in attachment
                        else base64.b64decode(attachment["body"])
                    )
                    copy(raw, "browser-observations/" + key + ".json", source=identity)
    assert len(screenshots) >= 60
    parity, zero, release = [], [], []
    for case in cases:
        for prop in case.findall("./properties/property"):
            if prop.attrib["name"] == "S6_PARITY_MATRIX":
                parity.extend(json.loads(prop.attrib["value"]))
            elif prop.attrib["name"] == "S6_ZERO_READ_PROOF":
                zero.append({"case": case.attrib["name"], **json.loads(prop.attrib["value"])})
            elif prop.attrib["name"] == "S6_TLS_RELEASE_PROOF":
                release.append({"case": case.attrib["name"], **json.loads(prop.attrib["value"])})
    assert len(parity) == 54 and len(zero) == 8 and len(release) == 2
    tracked = subprocess.check_output(
        [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
            "-z",
            BASE,
            "docs/v0-15",
            "docs/v0-16",
            "docs/v0-17",
            "docs/v0-18",
        ],
        cwd=ROOT,
    ).split(b"\0")
    frozen = {}
    for entry in filter(None, tracked):
        path = entry.decode()
        original = subprocess.check_output(["git", "show", BASE + ":" + path], cwd=ROOT)
        assert (ROOT / path).read_bytes() == original, "FROZEN_HISTORY_CHANGED: " + path
        frozen[path] = sha(original)
    sources = sorted(
        set(executed)
        | set(manifest["source_sha256"])
        | {
            "backend/tests/acceptance_s6/evidence.py",
            "backend/tests/forecast_intelligence/test_v0_18_s6_acceptance_contract.py",
            "docs/v0-18/s6/business-and-security-acceptance-r1.md",
        }
    )
    evidence = {
        "task_id": "V0_18_S6_BUSINESS_AND_SECURITY_ACCEPTANCE_R1",
        "base_main_sha": BASE,
        "SYNTHETIC": True,
        "stage_chain_fresh_verification": stages,
        "local_backend": {
            "status": "PASS",
            "case_count": len(cases),
            "new_s6_case_count": sum(
                "acceptance_s6" in c.attrib.get("classname", "") for c in cases
            ),
        },
        "browser": {
            "status": "PASS",
            "case_count": len(browser_matrix),
            "cases": browser_matrix,
            "screenshots": screenshots,
            "engine": "Desktop Chromium; narrow project is not iOS",
        },
        "parity_matrix": parity,
        "zero_read_proofs": zero,
        "tls_release_proofs": release,
        "execution_command": [
            "python",
            "-m",
            "backend.tests.acceptance_s6.run",
            "--output",
            str(run),
            "--browser",
        ],
        "ui_state_matrix": {
            "READY": "PASS_REAL_CANONICAL_VALUES",
            "EMPTY": "PASS_REAL_NO_SELECTION",
            "LOADING": "PASS_REAL_CANONICAL_RESPONSE_BARRIER",
            "PARTIAL": "PASS_REAL_TWO_DAY_SAVED_WINDOW",
            "NOT_AVAILABLE": "PASS_UNBOUND_ATTRIBUTION_UPPER_CONTRIBUTION",
            "NO_CURRENT_ACTUAL": "PASS_HISTORICAL_QUALITY_INDEPENDENT_MODULE",
            "ERROR": "PASS_REAL_POSTGRES_CONNECTION_FAULT_AND_RETRY",
            "AUTHORITY_MISMATCH": "PASS_REAL_CATALOG_DRIFT_409_CLEARS_CONTEXT",
            "all_states_on_every_page": "NOT_VALIDATED_NOT_ALL_ARE_LEGALLY_REACHABLE",
        },
        "source_evidence_sha256": {p: sha((ROOT / p).read_bytes()) for p in sources},
        "frozen_history_sha256": frozen,
        "artifacts": artifacts,
        "known_limits": {
            "real_ios_safari": "NOT_VALIDATED",
            "screen_reader": "NOT_VALIDATED",
            "soft_keyboard": "NOT_VALIDATED",
            "cross_host_nfs_windows_revocation": "NOT_VALIDATED",
            "rolling_seven_day_maximum_four_surface_metric": (
                "NOT_VALIDATED_SOURCE_CAPABILITY_UNAVAILABLE"
            ),
            "production_credentials_network_certificates": "NOT_VALIDATED",
            "jwt_issuer_audience": "NOT_APPLICABLE_LOCAL_OPAQUE_SESSION_AND_SERVICE_ACCOUNT",
            "open_frontend_dependency_advisories": "S5_OPEN_ADVISORIES_PRESERVED",
        },
        "governance": {
            "s6_authorized": True,
            "s6_formal_complete": False,
            "production_readiness": "NOT_READY",
            "ready_authorized": False,
            "merge_authorized": False,
            "deploy_authorized": False,
            "tag_authorized": False,
            "release_authorized": False,
            "version_closeout_authorized": False,
        },
        "exact_head_ci": {
            "status": "PENDING_POST_COMMIT_RECEIPT",
            "self_referential_head_not_fabricated": True,
        },
    }
    EVIDENCE.write_bytes(canonical(evidence))


def add_checks(directory):
    """Append current new evidence only; never overwrite prior artifact bytes."""
    value = json.loads(EVIDENCE.read_bytes())
    checks = json.loads((directory / "checks.json").read_bytes())
    assert len(checks) == 9 and all(c["exit"] == 0 for c in checks)
    assert "local_checks" not in value
    for check in checks:
        source = directory / (check["name"] + ".log")
        raw = source.read_bytes()
        assert sha(raw) == check["sha256"]
        published = raw.replace(str(ROOT).encode(), b"<S6_WORKTREE>").replace(
            b"/Users/charles", b"<OPERATOR_HOME>"
        )
        path = ARCHIVE / "checks" / source.name
        path.parent.mkdir(exist_ok=True)
        with path.open("xb") as output:
            output.write(published)
        value["artifacts"][str(path.relative_to(ROOT))] = {
            "sha256": sha(published),
            "raw_sha256": sha(raw),
            "source_path": str(source),
            "provenance": "S6_CURRENT_LOCAL_CHECK",
        }
    value["local_checks"] = checks
    EVIDENCE.write_bytes(canonical(value))


if __name__ == "__main__":
    if sys.argv[1] == "--checks":
        add_checks(Path(sys.argv[2]).absolute())
    else:
        publish(Path(sys.argv[1]).absolute())
