"""Print canonical public S4 evidence; copy/verify artifacts without overwrites first.

Usage: python -m backend.tests.forecast_intelligence.generate_v0_18_s4_evidence
    <isolated-artifact-directory>
This reader has no network, database or model access and never writes files.
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from backend.tests.historical_source import AUTHORIZED_HISTORY_PATHS, historical_bytes

ROOT = Path(__file__).resolve().parents[3]
BASE = "08b185b4621bf517846c986841bb5579b6c37b35"
HISTORY = "320f2046e3105b1b55da9cb037892571110b584a"
ARCHIVE = "docs/v0-18/evidence/s4-business-flow-r1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(artifacts):
    changed = subprocess.check_output(
        ["git", "diff", BASE, "--name-only"], cwd=ROOT, text=True
    ).splitlines()
    files = {p for p in changed if p.endswith((".py", ".ts", ".tsx", ".css", ".md"))}
    for directory in ("frontend/src/dashboard", "docs/v0-18/s4"):
        files.update(str(p.relative_to(ROOT)) for p in (ROOT / directory).rglob("*") if p.is_file())
    files.update(
        {
            "frontend/src/test/businessFixtures.ts",
            "frontend/src/test/businessFlow.test.tsx",
            "frontend/e2e/dashboard-business-flow.spec.ts",
            "frontend/e2e/support/business_pg.py",
            "frontend/e2e/support/business_compat.py",
            "backend/tests/forecast_intelligence/test_v0_18_s4_business_flow_contract.py",
            "backend/tests/forecast_intelligence/generate_v0_18_s4_evidence.py",
        }
    )
    sources = {p: sha(ROOT / p) for p in sorted(files)}
    original = json.loads((ROOT / "docs/v0-18/s1/local-auth-runtime-r1.json").read_text())
    frozen = original["frozen_history_sha256"]
    assert len(frozen) == 260
    for p, expected in frozen.items():
        assert sha(ROOT / p) == expected
    screenshots, states = {}, {}
    labels = {
        "总览": "OVERVIEW",
        "预测": "FORECAST",
        "影响因素": "ATTRIBUTION",
        "产能模拟": "CAPACITY_SIMULATOR",
        "预测质量": "QUALITY",
    }
    for path in sorted((ROOT / ARCHIVE / "screenshots").rglob("*.png")):
        project = "chromium-mobile" if "chromium-mobile" in path.parent.name else "chromium-desktop"
        match = re.fullmatch(r"(.+)-(\d+)x(\d+)-SYNTHETIC.png", path.name)
        if match:
            page, width, height = match.groups()
            assert page in labels
            source_root = "full-browser-results"
            entry = {
                "page": labels[page],
                "viewport": [int(width), int(height)],
                "test_case": f"HTTPS five pages no overflow {width}x{height}",
            }
            target = screenshots
        else:
            source_root = "full-browser-results"
            entry = {
                "state": path.name.removesuffix("-SYNTHETIC.png"),
                "viewport": [390, 844] if project.endswith("mobile") else [1440, 900],
                "test_case": (
                    "login error, authorized selector and keyboard large-text visual evidence"
                ),
            }
            target = states
        source = artifacts / source_root / path.parent.name / path.name
        assert source.is_file() and source.read_bytes() == path.read_bytes()
        entry.update(
            source_path=f"{source_root}/{path.parent.name}/{path.name}",
            spec="dashboard-business-flow.spec.ts",
            project=project,
            synthetic=True,
            sha256=sha(path),
            browser="Chromium 151.0.7922.34",
        )
        target[str(path.relative_to(ROOT))] = entry
    assert len(screenshots) == 60 and len(states) == 6
    assert len({e["source_path"] for e in [*screenshots.values(), *states.values()]}) == 66
    sources.update({str(p.relative_to(ROOT)): sha(p) for p in (ROOT / ARCHIVE).glob("*.log")})
    bindings = {
        p: {"commit": HISTORY, "sha256": hashlib.sha256(historical_bytes(p, HISTORY)).hexdigest()}
        for p in sorted(AUTHORIZED_HISTORY_PATHS)
        if p.startswith("frontend/")
    }
    for p, commit in (
        (
            "frontend/src/test/dashboardGovernance.test.ts",
            "e9812e82067dceae444ff0707ceeb2f560c1018e",
        ),
        ("backend/tests/historical_source.py", BASE),
        ("backend/tests/local_auth/test_runtime_evidence_contract.py", BASE),
        ("backend/tests/mcp/test_v0_18_s3_contract.py", BASE),
    ):
        bindings[p] = {
            "commit": commit,
            "sha256": hashlib.sha256(historical_bytes(p, commit)).hexdigest(),
        }
    return {
        "task_id": "V0_18_S4_DASHBOARD_AUTHORIZED_BUSINESS_FLOW_R1",
        "base_main_sha": BASE,
        "owner_s4_implementation_authorized": True,
        "source_evidence_sha256": sources,
        "source_evidence_count": len(sources),
        "frozen_history_sha256": frozen,
        "historical_source_bindings": bindings,
        "screenshots": screenshots,
        "state_screenshots": states,
        "production_readiness": "NOT_READY",
        "runtime": {
            "top_level_pages": [
                "OVERVIEW",
                "FORECAST",
                "ATTRIBUTION",
                "CAPACITY_SIMULATOR",
                "QUALITY",
            ],
            "real_session": True,
            "csrf_all_posts": True,
            "server_authorized_discovery": True,
            "atomic_canonical_selection": True,
            "handoff_memory_only": True,
            "abort_and_generation_guards": True,
            "physical_sensitive_context_clear": True,
            "admin_no_implicit_data": True,
            "automatic_latest": False,
            "client_business_math": False,
            "idle_session_poll_seconds": 60,
            "push_revocation": False,
            "handoff_max_seconds": 300,
            "unbound_upper_attribution_contribution": "NOT_AVAILABLE",
        },
        "acceptance": {
            "frontend_unit_passed": 130,
            "backend_focused_passed": 1381,
            "backend_focused_existing_conditional_skips": 4,
            "historical_contract_passed": 103,
            "browser_full_suite_passed": 118,
            "browser_full_suite_source_head": "1fd15da560c022038f80b964a6552d6a683d613a",
            "browser_additional_visual_cases_passed": 2,
            "https_postgres_cases_included": 26,
            "viewport_page_combinations": 30,
            "screenshot_count": 66,
            "real_ios_safari_validated": False,
            "soft_keyboard_validated": False,
            "screen_reader_validated": False,
            "certificate_scope": "SELF_SIGNED_LOOPBACK_TEST_BROWSER_ONLY",
            "ruff": "PASS",
            "format": "PASS",
            "mypy_scope": "backend/app: 581 source files",
            "mypy": "PASS",
            "frontend_build": "PASS",
        },
        "ci": {"result": "PENDING_AT_COMMIT_EXACT_HEAD_RECEIPT_REQUIRED"},
        "post_submission_correction": {
            "previous_head": "1fd15da560c022038f80b964a6552d6a683d613a",
            "superseded_ci_run": 38666863373,
            "root_cause": "ACTIVE_LOGIN_CONTROLLER_NOT_ABORTED_ON_DASHBOARD_UNMOUNT",
            "reproduction": "FAIL_EXPECTED_ABORTED_TRUE_ACTUAL_FALSE",
            "secondary_test_failure": "UNRELEASED_FAILING_UNIT_PROMISE_QUEUE_CASCADE",
            "runtime_unit_passed": 130,
            "https_postgres_retest_passed": 26,
            "final_ci_required_browser_cases": 120,
        },
        "governance": {
            k: False
            for k in (
                "s4_formal_complete",
                "s5_started",
                "production_deployed",
                "production_database_changed",
                "real_accounts_or_grants_created",
                "current_actual_accessed",
                "model_or_business_math_changed",
                "production_backend_changed",
                "mcp_runtime_changed",
                "ready_authorized",
                "merge_authorized",
                "deploy_authorized",
                "tag_authorized",
                "release_authorized",
            )
        },
    }


if __name__ == "__main__":
    print(json.dumps(generate(Path(sys.argv[1])), ensure_ascii=False, sort_keys=True, indent=2))
