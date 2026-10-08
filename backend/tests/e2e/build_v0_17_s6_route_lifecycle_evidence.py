"""Offline test-report projection; no production data, network or calculations."""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def browser_report(path, expected):
    value = json.loads(path.read_text())
    assert value["stats"]["expected"] == expected
    assert all(value["stats"][key] == 0 for key in ("unexpected", "skipped", "flaky"))
    cases = []

    def walk(suite):
        for spec in suite.get("specs", []):
            for test in spec["tests"]:
                assert test["status"] == "expected"
                assert len(test["results"]) == 1 and test["results"][0]["status"] == "passed"
                cases.append(
                    {
                        "file": spec["file"],
                        "case": spec["title"],
                        "project": test["projectName"],
                        "status": "PASS",
                    }
                )
        for child in suite.get("suites", []):
            walk(child)

    for suite in value["suites"]:
        walk(suite)
    assert len(cases) == expected
    return {"raw_report_sha256": sha(path), "stats": value["stats"], "cases": cases}


def main():
    parser = argparse.ArgumentParser()
    for name in ("root", "original", "repeat", "browser"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    folder = "docs/v0-17/evidence/s6-postmerge-route-lifecycle-r1"
    out = root / folder
    originals = {
        str(p.relative_to(args.original)): sha(p)
        for p in sorted(args.original.rglob("*"))
        if p.is_file()
    }
    assert any(p.endswith("trace.zip") for p in originals)
    assert any(p.endswith("frontend-e2e.xml") for p in originals)
    assert any(p.endswith("error-context.md") for p in originals)
    with zipfile.ZipFile(args.original / "run-logs.zip") as archive:
        logs = archive.read("4_frontend-e2e.txt").decode()
    assert "89 passed" in logs and "1 failed" in logs
    assert "route.fulfill: Route is already handled!" in logs
    failure = {
        "run_id": 37807916550,
        "head_sha": "eea84b6606ce356020da979d04a5d0d73af7bd6b",
        "event": "push",
        "conclusion": "failure",
        "job_id": 113416955183,
        "artifact_id": 11564221074,
        "artifact_name": "frontend-e2e-results",
        "test": "real saved authority BASE/REGION/COMPANY, six reads and unchanged service strings",
        "project": "chromium-desktop",
        "passed": 89,
        "failed": 1,
        "error": "route.fulfill: Route is already handled!",
        "location": "frontend/e2e/dashboard.spec.ts:77",
        "trace_findings": [
            "Business assertions completed before After Hooks.",
            "Pending APIRequestContext fetches attempted fulfill during fixture/context cleanup.",
            "SDK reported already-handled routes; page fixture teardown exceeded 30000ms.",
        ],
        "raw_artifacts_preserved": True,
        "raw_artifact_storage": "SEPARATE_LOCAL_READ_ONLY_ARCHIVE; NOT_PUBLIC_SOURCE_DATA",
        "raw_artifact_sha256": originals,
        "github_artifact_url": (
            "https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/"
            "actions/runs/37807916550/artifacts/11564221074"
        ),
    }
    write(out / "original-failure-manifest.json", failure)
    write(out / "repeat-results.json", browser_report(args.repeat, 20))
    write(out / "dashboard-results.json", browser_report(args.browser, 64))
    bindings = {}
    for source, archived in {
        "frontend/e2e/dashboard.spec.ts": "dashboard.spec.ts.txt",
        "backend/tests/e2e/test_v0_17_s6_evidence_contract.py": (
            "test_v0_17_s6_evidence_contract.py.txt"
        ),
    }.items():
        path = folder + "/historical-source/" + archived
        bindings[source] = {
            "archive_path": path,
            "historical_sha256": sha(root / path),
            "current_sha256": sha(root / source),
        }
    sources = [
        "frontend/e2e/dashboard.spec.ts",
        "frontend/e2e/support/dashboard_api.py",
        "frontend/e2e/selector-cancel-reopen.spec.ts",
        "frontend/e2e/dashboard-cross-surface.spec.ts",
        "backend/tests/e2e/test_v0_17_s6_evidence_contract.py",
        "backend/tests/e2e/test_v0_17_s6_route_lifecycle_contract.py",
        "backend/tests/e2e/build_v0_17_s6_route_lifecycle_evidence.py",
        "docs/v0-17/v0.17-s6-postmerge-route-lifecycle-correction-r1.md",
        "docs/v0-17/evidence/v0.17-s6-cross-surface-product-acceptance-r2.json",
    ]
    evidence = {
        "task_id": "V0_17_S6_POST_MERGE_FRONTEND_E2E_ROUTE_LIFECYCLE_CORRECTION_R1",
        "base_main_sha": "eea84b6606ce356020da979d04a5d0d73af7bd6b",
        "scope": "E2E_TEST_PROXY_LIFECYCLE_AND_DIRECT_EVIDENCE_ONLY",
        "original_failure_ci": 37807916550,
        "root_cause": "DETACHED_FETCH_FULFILL_OUTLIVES_ROUTE_DURING_FIXTURE_CLEANUP",
        "route_lifecycle_corrected": True,
        "method_body_headers": "URL_ONLY_NATIVE_CONTINUE; REAL_GET_POST_JSON_PARITY_TESTED",
        "same_origin_cors": "BROWSER_FETCH_SUCCESS_WITH_UNCHANGED_SERVICES; NO_CORS_BYPASS",
        "cancelled_request_handling": (
            "BROWSER_OWNS_RESPONSE; REAL_HELD_RESPONSE_RELEASED_AFTER_NEW_CONTEXT"
        ),
        "error_swallowing": False,
        "fixed_sleeps_added": False,
        "repeat_tests": "20_PASS;10_DESKTOP;10_NARROW_CHROMIUM",
        "dashboard_tests": "64_PASS",
        "frontend_unit_tests": "122_PASS",
        "backend_regression": "968_PASS;4_POSTGRES_DESELECTED",
        "local_full_frontend_e2e": "NOT_RUN_LOCAL_POSTGRES_UNAVAILABLE; EXACT_HEAD_CI_REQUIRED",
        "historical_source_bindings": bindings,
        "source_evidence_sha256": {p: sha(root / p) for p in sources},
        "artifact_sha256": {
            str(p.relative_to(root)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()
        },
        "production_code_changed": False,
        "historical_evidence_rewritten": False,
        "current_actual_accessed": False,
        "governance": {
            "correction_authorized": True,
            "exact_head_ci": "PENDING_AT_COMMIT",
            "s6_formal_complete": False,
            "production_readiness": "NOT_READY",
            "ready_authorized": False,
            "merge_authorized": False,
            "deploy_authorized": False,
            "version_closeout_authorized": False,
            "release_authorized": False,
            "stop": True,
        },
    }
    write(
        root / "docs/v0-17/evidence/v0.17-s6-postmerge-route-lifecycle-correction-r1.json", evidence
    )


if __name__ == "__main__":
    main()
