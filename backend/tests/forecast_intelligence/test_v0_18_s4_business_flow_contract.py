"""S4 public evidence integrity; actual browser/auth acceptance is separate."""

import hashlib
import json
from pathlib import Path

from backend.tests.historical_source import historical_bytes

ROOT = Path(__file__).resolve().parents[3]
BASE = "08b185b4621bf517846c986841bb5579b6c37b35"
S4_DELIVERY = "89641834ab7a0bd902a23f9243325da5c163d518"
APPROVED_EVOLVING_SOURCES = {
    "backend/tests/mcp/test_v0_18_s3_contract.py",
    "backend/tests/local_auth/test_runtime_evidence_contract.py",
    "frontend/src/dashboard/api/client.ts",
    "frontend/src/dashboard/api/security.ts",
    "frontend/src/dashboard/components/AuthorizedSavedRunSelector.tsx",
    "backend/tests/forecast_intelligence/test_v0_18_s4_business_flow_contract.py",
}
FILE = ROOT / "docs/v0-18/evidence/s4-dashboard-authorized-business-flow-r1.json"


def test_canonical_sources_and_immutable_history():
    raw = FILE.read_bytes()
    data = json.loads(raw)
    assert raw == (json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
    assert data["task_id"] == "V0_18_S4_DASHBOARD_AUTHORIZED_BUSINESS_FLOW_R1"
    assert data["base_main_sha"] == BASE
    assert len(data["frozen_history_sha256"]) == 260
    for field in ("source_evidence_sha256", "frozen_history_sha256"):
        for relative, expected in data[field].items():
            path = Path(relative)
            assert not path.is_absolute() and ".." not in path.parts
            source = (
                historical_bytes(relative, S4_DELIVERY, root=ROOT)
                if field == "source_evidence_sha256" and relative in APPROVED_EVOLVING_SOURCES
                else (ROOT / path).read_bytes()
            )
            assert hashlib.sha256(source).hexdigest() == expected
            if field == "frozen_history_sha256":
                assert (ROOT / path).read_bytes() == historical_bytes(relative, BASE)
    for relative, binding in data["historical_source_bindings"].items():
        assert (
            hashlib.sha256(historical_bytes(relative, binding["commit"])).hexdigest()
            == binding["sha256"]
        )


def test_runtime_boundaries_and_pending_governance():
    data = json.loads(FILE.read_bytes())
    assert data["runtime"]["top_level_pages"] == [
        "OVERVIEW",
        "FORECAST",
        "ATTRIBUTION",
        "CAPACITY_SIMULATOR",
        "QUALITY",
    ]
    for key in (
        "real_session",
        "csrf_all_posts",
        "server_authorized_discovery",
        "atomic_canonical_selection",
        "handoff_memory_only",
        "abort_and_generation_guards",
        "physical_sensitive_context_clear",
        "admin_no_implicit_data",
    ):
        assert data["runtime"][key] is True
    assert data["runtime"]["automatic_latest"] is False
    assert data["runtime"]["client_business_math"] is False
    assert data["runtime"]["idle_session_poll_seconds"] == 60
    assert data["runtime"]["push_revocation"] is False
    assert data["production_readiness"] == "NOT_READY"
    assert all(value is False for value in data["governance"].values())
    assert data["ci"]["result"] == "PENDING_AT_COMMIT_EXACT_HEAD_RECEIPT_REQUIRED"


def test_screenshots_have_unique_test_case_project_viewport_provenance():
    data = json.loads(FILE.read_bytes())
    sources = set()
    coverage = set()
    for relative, entry in data["screenshots"].items():
        assert entry["source_path"] not in sources
        sources.add(entry["source_path"])
        assert entry["spec"] == "dashboard-business-flow.spec.ts"
        assert entry["project"] in {"chromium-desktop", "chromium-mobile"}
        assert entry["synthetic"] is True
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == entry["sha256"]
        coverage.add((entry["page"], tuple(entry["viewport"])))
    assert len(coverage) == 30
    assert data["acceptance"]["real_ios_safari_validated"] is False
    assert data["acceptance"]["soft_keyboard_validated"] is False
    assert data["acceptance"]["screen_reader_validated"] is False
