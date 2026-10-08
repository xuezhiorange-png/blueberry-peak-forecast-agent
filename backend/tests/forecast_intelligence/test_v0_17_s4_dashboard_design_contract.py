"""Offline S4 design contracts: no browser, API, actuals or engine execution."""

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DESIGN = ROOT / "docs/v0-17/design/s4"
EVIDENCE = ROOT / "docs/v0-17/evidence/v0.17-s4-dashboard-design-freeze-r1.json"
PAGES = ["OVERVIEW", "FORECAST", "ATTRIBUTION", "CAPACITY_SIMULATOR", "QUALITY"]
STATES = [
    "LOADING",
    "READY",
    "EMPTY",
    "PARTIAL",
    "NOT_AVAILABLE",
    "ERROR",
    "AUTHORITY_MISMATCH",
    "NO_CURRENT_ACTUAL",
]


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def test_navigation_and_kpis() -> None:
    contract = load(DESIGN / "dashboard-contract-r1.json")
    assert contract["pages"] == PAGES
    assert contract["hierarchy"] == ["COMPANY", "REGION", "BASE"]
    assert contract["kpis"] == [
        "FORECAST_7D_TOTAL",
        "FORECAST_15D_TOTAL",
        "PEAK_DATE",
        "PEAK_DAILY_QUANTITY",
    ]
    assert contract["business_run_selector_backend_ready"] is False
    assert len(contract["components"]) == 29


@pytest.mark.parametrize("page", PAGES)
def test_eight_states(page: str) -> None:
    matrix = load(DESIGN / "dashboard-contract-r1.json")["state_matrix"][page]
    assert list(matrix) == sorted(STATES)
    assert all(item["copy"] and item["recovery"] and item["data_rule"] for item in matrix.values())


def test_component_contracts() -> None:
    for component in load(DESIGN / "dashboard-contract-r1.json")["components"].values():
        for field in (
            "inputs",
            "authority",
            "missing",
            "interaction",
            "desktop",
            "mobile",
            "copy",
            "states",
            "accessibility",
            "acceptance",
        ):
            assert component[field], field


def test_canonical_design_json_bytes() -> None:
    for path in (
        EVIDENCE,
        DESIGN / "dashboard-contract-r1.json",
        DESIGN / "design-tokens-r1.json",
        DESIGN / "visual-qa-report-r1.json",
    ):
        canonical = json.dumps(load(path), ensure_ascii=False, sort_keys=True, indent=2)
        assert path.read_bytes() == (canonical + "\n").encode()


def test_transport_and_semantics_remain_unavailable() -> None:
    contract = load(DESIGN / "dashboard-contract-r1.json")
    for field in (
        "upper_bounds_available",
        "attribution_available",
        "contribution_api_available",
    ):
        assert contract[field] is False
    assert contract["no_client_business_math"] is True
    assert contract["planning_levels"] == [
        "POINT",
        "UPPER_PLANNING_BOUND_80",
        "UPPER_PLANNING_BOUND_90",
    ]


def test_tokens_and_breakpoints() -> None:
    tokens = load(DESIGN / "design-tokens-r1.json")
    assert set(tokens) == {
        "color",
        "typography",
        "spacing",
        "radius",
        "border",
        "shadow",
        "elevation",
        "breakpoint",
        "grid",
        "motion",
        "focus",
        "data_series",
        "state",
    }
    assert tokens["typography"]["body_px"] == 15
    assert tokens["focus"]["minimum_touch_target_px"] == 44


def test_prototype_is_offline_and_not_business_math() -> None:
    script = (DESIGN / "prototype/prototype.js").read_text()
    html = (DESIGN / "prototype/index.html").read_text()
    assert html.count('data-page="') == 5
    assert "SYNTHETIC DESIGN FIXTURE — NOT PRODUCTION DATA" in html
    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        "WebSocket",
        "localStorage",
        ".reduce(",
        "eval(",
        "new Function",
        "innerHTML = location",
    ):
        assert forbidden not in script
    for phrase in (
        "请选择已保存预测",
        "当前产季暂无可用于正式评分的实际采收数据",
        "NOT_AVAILABLE",
        "SYNTHETIC_LOSS_UNIT",
    ):
        assert phrase in html + script


def test_source_and_artifact_hashes() -> None:
    evidence = load(EVIDENCE)
    for group in ("source_evidence_sha256", "design_artifact_sha256"):
        assert evidence[group]
        for relative, expected in evidence[group].items():
            assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected, relative
    assert evidence["source_evidence_count"] == len(evidence["source_evidence_sha256"])


def test_visual_evidence() -> None:
    report = load(DESIGN / "visual-qa-report-r1.json")
    assert report["browser_engine"] == "Chromium"
    assert report["real_ios_safari_verified"] is False
    assert report["viewports"] == [
        [1440, 900],
        [1280, 800],
        [1024, 768],
        [834, 1112],
        [390, 844],
        [360, 800],
    ]
    assert len(report["screenshots"]) >= 38
    assert report["overflow_failures"] == []
    for shot in report["screenshots"]:
        path = DESIGN / shot["path"]
        assert path.read_bytes()[:3] == b"\xff\xd8\xff"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == shot["sha256"]
    for check in (
        "keyboard",
        "dialog_focus_return",
        "scenario_stale",
        "date_link",
        "font_enlargement",
        "reduced_motion",
        "orientation",
    ):
        assert report["checks"][check] == "PASS"


def test_governance_and_limitations() -> None:
    evidence = load(EVIDENCE)
    for field in (
        "owner_visual_approval",
        "s4_formal_complete",
        "s5_authorized",
        "ready_authorized",
        "merge_authorized",
        "deploy_authorized",
        "tag_authorized",
        "release_authorized",
        "production_frontend_changed",
        "current_actual_scoring",
        "client_business_math",
        "fake_attribution",
        "upper_fallback",
        "real_roi_claim",
    ):
        assert evidence[field] is False
    assert evidence["s4_implementation_authorized"] is True
    assert evidence["preflight_consumed"] is True
    assert evidence["candidate_status"] == "PASS"


def test_document_handoff_and_privacy() -> None:
    handoff = (DESIGN / "s5-implementation-handoff-r1.md").read_text()
    for keyword in ("Saved-run", "贡献", "Trial", "S5", "Owner", "取消", "Decimal", "八状态"):
        assert keyword in handoff
    for path in DESIGN.rglob("*"):
        if path.suffix in {".json", ".html", ".js", ".css", ".md"}:
            content = path.read_text()
            for forbidden in ("postgresql://", "Bearer ey", "/Users/charles/", "sk-proj-"):
                assert forbidden not in content, path
