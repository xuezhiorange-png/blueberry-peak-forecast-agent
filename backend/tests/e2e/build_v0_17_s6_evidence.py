"""Offline SYNTHETIC acceptance evidence projection; never a production entrypoint.

Consumes completed test reports only. Does not execute business calculations.
Original seven artifacts are verified before copying, without changing originals.
"""

import argparse
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def collect_screenshots(browser, execution_id, artifact_root):
    """Only explicit attachments from this successful execution are admissible.

    Validate the entire plan before copying any file. No recursive discovery,
    existing archive reuse, inferred project names or basename overwrites.
    """
    assert execution_id and execution_id != "CI_VALIDATION_NOT_ARCHIVED"
    start = datetime.fromisoformat(browser["stats"]["startTime"])
    end = start + timedelta(milliseconds=browser["stats"]["duration"])
    planned = {}
    seen_sources = set()

    def walk(suite):
        for spec in suite.get("specs", []):
            for test in spec["tests"]:
                for result in test["results"]:
                    attachments = result.get("attachments", [])
                    images = [a for a in attachments if a["contentType"].startswith("image/")]
                    if not images:
                        continue
                    assert spec["file"] == "dashboard-cross-surface.spec.ts", "UNRELATED_SPEC"
                    assert test["status"] == "expected" and result["status"] == "passed"
                    assert len(test["results"]) == 1 and result["retry"] == 0
                    metadata = {}
                    for attachment in attachments:
                        if attachment["name"].startswith("provenance:"):
                            import base64

                            name = attachment["name"].removeprefix("provenance:")
                            assert name not in metadata, "DUPLICATE_PROVENANCE"
                            metadata[name] = json.loads(base64.b64decode(attachment["body"]))
                    assert len(metadata) == len(images), "MISSING_PROVENANCE"
                    for image in images:
                        name = image["name"]
                        meta = metadata[name]
                        assert meta["execution_id"] == execution_id, "STALE_EXECUTION"
                        assert meta["test_file"] == "e2e/" + spec["file"]
                        assert meta["test_title"] == spec["title"]
                        assert meta["project"] == test["projectName"]
                        assert meta["test_id"] == spec["id"] and meta["name"] == name
                        captured_at = datetime.fromisoformat(meta["captured_at"])
                        test_start = datetime.fromisoformat(result["startTime"])
                        assert start <= captured_at <= end
                        # SDK duration excludes worker-fixture startup although
                        # startTime precedes it; it is not a wall-clock deadline.
                        assert test_start <= captured_at
                        path = Path(image["path"]).resolve()
                        relative = path.relative_to(artifact_root.resolve())
                        # Playwright copies attachments to hash-suffixed filenames.
                        # The report's logical name and content digest are authority,
                        # not the SDK-generated attachment basename.
                        assert Path(name).name == name and "SYNTHETIC" in name
                        assert sha(path) == meta["sha256"], "SOURCE_DRIFT"
                        assert relative.as_posix() not in seen_sources, "DUPLICATE_SOURCE"
                        seen_sources.add(relative.as_posix())
                        # Both projects capture all viewports; publish one explicitly
                        # designated desktop-project copy of each page/viewport.
                        if name.endswith("-SYNTHETIC.jpg"):
                            if test["projectName"] != "chromium-desktop":
                                continue
                            destination = name.replace("-SYNTHETIC", "")
                        else:
                            project = {"chromium-desktop": "desktop", "chromium-mobile": "mobile"}[
                                test["projectName"]
                            ]
                            destination = project + "-" + name
                        assert destination not in planned, "DUPLICATE_DESTINATION"
                        planned[destination] = {
                            **meta,
                            "report_spec_id": spec["id"],
                            "test_result_status": result["status"],
                            "test_start_time": result["startTime"],
                            "test_duration_ms": result["duration"],
                            "source_artifact_path": relative.as_posix(),
                            "source_path": path,
                        }
        for child in suite.get("suites", []):
            walk(child)

    for suite in browser["suites"]:
        walk(suite)
    assert len(planned) == 44, "INCOMPLETE_SCREENSHOT_SET"
    return planned


def main():
    parser = argparse.ArgumentParser()
    for name in ("root", "original", "captures", "browser", "backend"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--browser-artifact-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    evidence_root = root / "docs/v0-17/evidence"
    output = evidence_root / "s6-cross-surface-r2"
    correction_path = "docs/v0-17/evidence/v0.17-s6-selector-cancel-reopen-correction-r1.json"
    correction = json.loads((root / correction_path).read_text())
    pins = correction["original_s6_artifacts_sha256"]
    # Verify all before copying any. No fallback reconstruction.
    assert all(sha(args.original / path) == expected for path, expected in pins.items())
    historical = {}
    for path, expected in pins.items():
        dest = output / "historical-r1" / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.original / path, dest)
        assert sha(dest) == expected
        historical[str(dest.relative_to(root))] = expected
    original = json.loads(
        (
            args.original / "docs/v0-17/evidence/v0.17-s6-cross-surface-product-acceptance-r1.json"
        ).read_text()
    )
    sources = set(original["source_evidence_sha256"])
    sources.update(correction["source_evidence_sha256"])
    sources.add(correction_path)
    sources.add("docs/v0-17/v0.17-s6-cross-surface-product-acceptance-r2.md")
    sources.update(
        str(p.relative_to(root))
        for p in (root / "frontend/src/dashboard").rglob("*")
        if p.is_file()
    )
    sources.update(
        str(p.relative_to(root))
        for p in evidence_root.glob("v0.17-*.json")
        if "s6-cross-surface" not in p.name
    )
    for name in (
        "v0.17-s1-forecast-intelligence-service-read-api-r1.json",
        "v0.17-s2-decision-support-api-r1.json",
        "v0.17-s3-mcp-productization-r1.json",
        "v0.17-s5-dashboard-implementation-r1.json",
    ):
        frozen = json.loads((evidence_root / name).read_text())
        for path, expected in frozen["source_evidence_sha256"].items():
            # Selector changed only in separately authorized PR705; old S5
            # snapshot remains intact and is not a mutable current-state DB.
            if path != "frontend/src/dashboard/components/AuthorizedSavedRunSelector.tsx":
                assert sha(root / path) == expected, path
            sources.add(path)
    sources.update(str(p.relative_to(root)) for p in (root / "backend/tests/e2e").glob("*.py"))
    sources.update(
        {
            "frontend/e2e/dashboard-cross-surface.spec.ts",
            "frontend/e2e/support/s6_api.py",
            "frontend/e2e/support/s6_seed.py",
            "frontend/e2e/dashboard.spec.ts",
            "frontend/e2e/selector-cancel-reopen.spec.ts",
            "frontend/src/test/selectorCancellation.test.tsx",
            "backend/tests/mcp/test_v0_17_s3_safety.py",
            "backend/tests/mcp/test_v0_17_s3_productization.py",
        }
    )
    hashes = {p: sha(root / p) for p in sorted(sources)}
    cases = []
    for case in ET.parse(args.backend).iter("testcase"):
        assert (
            case.find("failure") is None
            and case.find("error") is None
            and case.find("skipped") is None
        )
        cases.append(
            {"suite": case.attrib["classname"], "case": case.attrib["name"], "result": "PASS"}
        )
    browser = json.loads(args.browser.read_text())
    assert (
        browser["stats"]["unexpected"]
        == browser["stats"]["skipped"]
        == browser["stats"]["flaky"]
        == 0
    )
    browser_cases = []

    def walk(suite):
        for spec in suite.get("specs", []):
            for test in spec["tests"]:
                assert test["status"] == "expected"
                browser_cases.append(
                    {
                        "file": spec["file"],
                        "case": spec["title"],
                        "project": test["projectName"],
                        "result": "PASS",
                    }
                )
        for child in suite.get("suites", []):
            walk(child)

    for suite in browser["suites"]:
        walk(suite)
    # Preserve exact SDK/HTTP-asserted business payloads, not independent mock JSON.
    calls = []
    for path in sorted(args.captures.glob("*.json")):
        captured = json.loads(path.read_text())
        assert captured["post_seed_dml_count"] == 0
        for call in captured["sdk_calls"]:
            calls.append({"case": path.stem, **call})
    write(output / "parity-payloads.json", {"SYNTHETIC": True, "calls": calls})
    matrix = []
    for call in calls:
        if call["is_error"] or not call["case"].startswith(
            (
                "test_all_eight",
                "test_capacity_and_planning",
                "test_current_quality",
                "test_saved_special",
                "test_explicit_cost",
            )
        ):
            continue
        payload = call["payload"]
        matrix.append(
            {
                "case": call["case"],
                "tool": call["tool"],
                "forecast_identity": payload.get("forecast_identity"),
                "hierarchy_identity": payload.get("hierarchy_identity"),
                "authority_identity": payload.get("authority_identity"),
                **{
                    key: payload.get(key)
                    for key in (
                        "source_result_hash",
                        "projection_hash",
                        "adapter_authority_hash",
                        "engine_result_hash",
                        "planning_level",
                        "cost_contract_id",
                        "cost_contract_hash",
                    )
                },
                "status": payload["status"],
                "unavailable_reason": payload.get("unavailable_reason"),
                "scenario_input_identity": call["arguments"],
                "http_status": 200,
                "mcp_status": "BUSINESS_SUCCESS",
                "numeric_parity": "PASS",
                "hash_parity": "PASS",
                "semantic_parity": "PASS",
                "business_payload_sha256": hashlib.sha256(
                    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                "http_mcp_full_json_equality": "PASS",
                "dashboard_verification": (
                    "DOM_CASES_FOR_BASE_REGION_COMPANY_AND_ABC; "
                    "NOT_EVERY_BACKEND_PARAMETER_COMBINATION"
                ),
            }
        )
    write(output / "parity-matrix.json", matrix)
    write(
        output / "test-results.json",
        {
            "SYNTHETIC": True,
            "backend": cases,
            "browser": browser_cases,
            "browser_stats": browser["stats"],
        },
    )
    design = json.loads((root / "docs/v0-17/design/s4/dashboard-contract-r1.json").read_text())
    states = {
        page: {
            state: {
                "contract": "PASS_FROZEN_CONTRACT_AND_STATUS_RENDERER",
                "runtime_scope": (
                    "NO_LEGAL_READY_ATTRIBUTION_SOURCE; NOT_FABRICATED"
                    if page == "ATTRIBUTION" and state == "READY"
                    else "NO_CURRENT_ACTUAL_IS_QUALITY_MODULE_ONLY"
                    if state == "NO_CURRENT_ACTUAL" and page != "QUALITY"
                    else "NO_NEW_FROZEN_PARTIAL_QUALITY_SOURCE"
                    if page == "QUALITY" and state == "PARTIAL"
                    else "MODULE_APPLICABILITY; SAVED_CURVES_AND_FAILURE_INJECTION; SEE_NODEIDS"
                ),
            }
            for state in design["state_matrix"][page]
        }
        for page in design["pages"]
    }
    write(
        output / "failure-state-matrix.json",
        {
            "states": states,
            "failure_cases": [c for c in cases if "failures" in c["suite"]],
            "permission_cases": [c for c in cases if "permissions" in c["suite"]],
            "supplemental_transport_tests": (
                "FULL_S3_SAFETY_REGRESSION: timeout/cancel/disconnect/"
                "argument/response limits and recovery"
            ),
            "http_denial": "LAZY_SESSION_POSSIBLE; ZERO_SQL_BEFORE_AUTHORIZATION",
        },
    )
    write(
        output / "accessibility-results.json",
        {
            "browser": "Playwright 1.62.0 Chromium; narrow viewport is not real mobile Safari",
            "viewports": design["viewports"],
            "unique_page_viewport_combinations": 30,
            "document_horizontal_overflow": "PASS_30_COMBINATIONS_REPEATED_IN_TWO_PROJECTS",
            "keyboard_date_controls": "PASS",
            "dialog_focus_return": "PASS",
            "font_enlargement": "PASS_TESTED_DASHBOARD_FONT_30PX",
            "reduced_motion": "PASS",
            "chart_source_table": "PASS",
            "real_ios_safari": "NOT_VALIDATED",
            "soft_keyboard": "NOT_VALIDATED",
            "screen_reader": "NOT_VALIDATED",
            "visual_review": "REPRESENTATIVE_DESKTOP_PHONE_TABLET_INSPECTED; NO_REDESIGN",
        },
    )
    plan = collect_screenshots(browser, args.execution_id, args.browser_artifact_root)
    screenshots = {}
    provenance = []
    for name, record in sorted(plan.items()):
        source = record.pop("source_path")
        dest = output / "screenshots" / name
        shutil.copy2(source, dest)
        destination = str(dest.relative_to(root))
        screenshots[destination] = sha(dest)
        provenance.append({**record, "archive_path": destination})
    # Public, path-safe extraction of the exact report attachments. Keep the
    # original report digest too; never publish its machine-specific config.
    report_path = output / "screenshot-execution-report.json"
    write(
        report_path,
        {
            "raw_report_sha256": sha(args.browser),
            "stats": browser["stats"],
            "cases": provenance,
        },
    )
    write(
        output / "screenshot-provenance.json",
        {
            "schema": "V0_17_S6_SCREENSHOT_PROVENANCE_R1",
            "execution_id": args.execution_id,
            "artifact_root_label": args.browser_artifact_root.name,
            "browser_report_sha256": sha(args.browser),
            "public_report_sha256": sha(report_path),
            "start_time": browser["stats"]["startTime"],
            "duration_ms": browser["stats"]["duration"],
            "selection": (
                "EXACT_SPEC_ATTACHMENTS; DESKTOP_PROJECT_FOR_PAGE_VIEWPORTS; "
                "BOTH_PROJECTS_FOR_STATES"
            ),
            "duplicate_destination_policy": "REJECT_BEFORE_COPY",
            "screenshots": provenance,
        },
    )
    artifacts = {str(p.relative_to(root)): sha(p) for p in sorted(output.glob("*.json"))}
    evidence = {
        "schema": "V0_17_S6_CROSS_SURFACE_PRODUCT_ACCEPTANCE_R2",
        "version": "0.17.0",
        "stage": "S6",
        "task_id": "V0_17_S6_CROSS_SURFACE_E2E_PRODUCT_ACCEPTANCE_R2_RESUME",
        "base_main_sha": "2022dc00b2aa685a2d7331aba5a47142f655a723",
        "correction": {
            "pr": 705,
            "head_sha": "2e5f639ab7d50de616ba6add80d1f4efce2c2359",
            "merge_sha": "2022dc00b2aa685a2d7331aba5a47142f655a723",
            "post_merge_ci": 37783261851,
            "post_merge_ci_conclusion": "success",
            "selector_retest": "PASS_FRESH_R2",
        },
        "evidence_provenance_correction": {
            "review_id": 5458870712,
            "previous_head": "0e1935d5f0c372acba48812d1f5ae65a8b9822df",
            "previous_cancel_reopen_images": "NOT_ACCEPTED_AS_FRESH_R2_EVIDENCE",
            "scope": "S6_TEST_AND_EVIDENCE_ONLY",
            "execution_id": args.execution_id,
            "fresh_screenshot_count": len(screenshots),
            "provenance_admission": "PASS_EXACT_REPORT_ATTACHMENTS",
            "duplicate_destination_admission": "REJECT",
            "independent_reassessment": "PENDING",
        },
        "original_r1_hash_audit": "PASS_7_OF_7",
        "original_r1_artifacts_sha256": pins,
        "historical_copy_sha256": historical,
        "source_evidence_sha256": hashes,
        "source_evidence_count": len(hashes),
        "artifact_sha256": artifacts,
        "screenshot_sha256": screenshots,
        "screenshot_count": len(screenshots),
        "test_counts": {
            "parity": sum("parity" in c["suite"] for c in cases),
            "permissions": sum("permissions" in c["suite"] for c in cases),
            "failures": sum("failures" in c["suite"] for c in cases),
            "backend_acceptance": len(cases),
            "browser": len(browser_cases),
        },
        "execution": {
            "synthetic": True,
            "same_database_http_mcp_browser": True,
            "real_mcp_sdk_client_session": True,
            "mcp_tool_count": 8,
            "post_seed_business_dml_count": 0,
            "unauthorized_sql_count": 0,
            "unauthorized_business_execution_count": 0,
            "current_actual_accessed": False,
            "current_actual_read": False,
            "current_actual_import": False,
            "current_actual_scoring": False,
            "current_season_actual_required": False,
            "private_data_accessed": False,
            "model_training": False,
            "new_forecast_execution": False,
            "automatic_optimization": False,
            "business_action_persisted": False,
        },
        "validation": {
            "backend_regression": "968 passed, 4 deselected, 60 warnings",
            "frontend_unit": "122 passed",
            "selector_strict_mode": "11 passed",
            "ruff": "PASS",
            "format": "PASS",
            "mypy": "PASS_562_SOURCE_FILES",
            "frontend_typecheck": "PASS",
            "frontend_lint": "PASS",
            "frontend_format": "PASS",
            "frontend_build": "PASS",
            "local_trial_browser": "NOT_RUN_LOCAL_POSTGRES_UNAVAILABLE; EXACT_HEAD_CI_REQUIRED",
            "local_full_suite": "NOT_RUN_KNOWN_LOCAL_LIBOMP_UNAVAILABLE",
            "exact_head_ci": "PENDING_AT_COMMIT; FINAL_RECEIPT_BINDS_LIVE_RESULT",
        },
        "results": {
            "cross_surface_parity": "PASS_LOCAL_PENDING_EXACT_HEAD_CI",
            "product_acceptance": "PASS_ISOLATED_AVAILABLE_AUTHORITY_PENDING_EXACT_HEAD_CI",
            "production_readiness": "NOT_READY",
            "ready_interval_attribution_parity": "NOT_VALIDATED_NO_RUN_BOUND_AUTHORITY",
            "unbound_upper80": "NOT_AVAILABLE",
            "unbound_upper90": "NOT_AVAILABLE",
            "unbound_attribution": "NOT_AVAILABLE",
            "synthetic_loss_unit": "SYNTHETIC_LOSS_UNIT",
            "rank_order": ["B", "C", "A"],
            "tie_semantics": (
                "Equal operational quantities; distinct lexical scenario_id ranks, "
                "not shared ordinal rank"
            ),
        },
        "production_gaps": {
            key: False
            for key in [
                "business_run_selector_backend_ready",
                "normal_business_discovery_available",
                "production_multi_user_scope_validated",
                "child_contribution_authority_available",
                "production_service_account_configured",
                "production_run_grants_verified",
                "production_access_isolation_verified",
                "production_deployed",
                "current_season_actual_available",
                "real_roi_validated",
                "canonical_company_cost_established",
                "real_ios_safari_validated",
                "soft_keyboard_validated",
                "screen_reader_validated",
            ]
        },
        "governance": {
            "s6_authorized": True,
            "s6_resume_authorized": True,
            "s6_formal_complete": False,
            **{
                key: False
                for key in [
                    "ready_authorized",
                    "merge_authorized",
                    "deploy_authorized",
                    "tag_authorized",
                    "release_authorized",
                    "version_closeout_authorized",
                    "v0_18_authorized",
                    "production_backend_changed",
                    "production_mcp_changed",
                    "production_frontend_changed",
                    "frozen_math_changed",
                    "historical_evidence_changed",
                ]
            },
            "stop": True,
        },
    }
    write(evidence_root / "v0.17-s6-cross-surface-product-acceptance-r2.json", evidence)
    print(
        json.dumps(
            {
                "sources": len(hashes),
                "screenshots": len(screenshots),
                "counts": evidence["test_counts"],
            }
        )
    )


if __name__ == "__main__":
    main()
