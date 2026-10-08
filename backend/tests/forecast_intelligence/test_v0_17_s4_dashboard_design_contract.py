"""Offline S4 design/fixture audit: no browser, API, actuals or forecast execution."""

import ast
import copy
import hashlib
import json
import re
from decimal import ROUND_HALF_EVEN, Decimal, Inexact, Rounded, localcontext
from pathlib import Path

import pytest

from backend.app.forecast_intelligence.business_loss import row_loss, synthetic_contracts

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
    correction = evidence["r2_correction"]
    assert correction["previous_head_sha"] == "09453c1a1e00a47b97dde9769c6b1f8fd73fd131"
    assert correction["independent_review_id"] == 5453163827
    assert (
        correction["offline_parity_test_sha256"]
        == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    )


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


def static_fixture() -> tuple[dict, str]:
    """Read literals only: do not execute JavaScript, forecasts or private data."""
    script = (DESIGN / "prototype/prototype.js").read_text()
    literal = script.split("const fixture = Object.freeze(", 1)[1].split("\n});", 1)[0]
    literal = re.sub(r"\b([A-Za-z][A-Za-z0-9]*):", r"'\1':", literal)
    return ast.literal_eval(literal + "\n}"), script


def audit_fixture(fixture: dict, script: str) -> None:
    """Independent test-only quantity audit; the browser still renders literals."""
    with localcontext() as ctx:
        ctx.prec = 50
        ctx.rounding = ROUND_HALF_EVEN
        ctx.traps[Inexact] = True
        point = [Decimal(x) for x in fixture["point"]]
        assert point == list(
            map(
                Decimal,
                (
                    "80",
                    "100",
                    "120",
                    "160",
                    "200",
                    "180",
                    "140",
                    "100",
                    "80",
                    "120",
                    "160",
                    "140",
                    "100",
                    "80",
                    "60",
                ),
            )
        )
        assert len(fixture["dates"]) == len(point) == 15
        assert fixture["dates"] == [f"01-{day:02d}" for day in range(2, 17)]
        assert sum(point[:7]) == Decimal(fixture["total7"]) == 980
        assert sum(point) == Decimal(fixture["total15"]) == 1820
        assert max(point) == Decimal(fixture["peak"]) == 200
        assert fixture["dates"][point.index(max(point))] == fixture["peakDate"] == "01-06"
        assert fixture["capacity"] == ["140"] * 15
        cost = next(c for c in synthetic_contracts() if c.contract_id == "SYNTHETIC_UNDER_4X_R1")
        assert cost.c_under_per_kg == 4 and cost.c_over_per_kg == 1
        assert cost.contract_hash == (
            "8d6f2567a18bd298f1a261a059a88b2772d77bcc6f03e313dc3853c9cd2f0f3f"
        )
        assert cost.loss_unit == "SYNTHETIC_LOSS_UNIT" and cost.synthetic
        assert not cost.canonical_company_cost
        for literal in (
            "scenario==='B'?'140':'120'",
            "scenario==='C'?'10':''",
            "scenario==='C'?'12':''",
            "scenario==='C'?'20':'0'",
        ):
            assert literal in script
        rows = {r["name"][0]: r for r in fixture["comparison"]}
        assert set(rows) == {"A", "B", "C"}
        operational = {}
        for name, capacity in (
            ("A", Decimal(120)),
            ("B", Decimal(140)),
            ("C", Decimal(10) * Decimal(12) + Decimal(20)),
        ):
            opening = Decimal(0)
            closing_rows, processed_rows, under_rows, over_rows, losses = [], [], [], [], []
            for demand in point:
                workload = opening + demand
                processed = min(workload, capacity)
                closing = workload - processed
                assert opening + demand == processed + closing
                assert 0 <= processed <= capacity and closing >= 0
                # S5 is reused only on explicit synthetic quantities in this offline test.
                loss = row_loss(demand, capacity, cost)
                under = max(demand - capacity, Decimal(0))
                over = max(capacity - demand, Decimal(0))
                assert loss["underforecast_kg"] == under
                assert loss["overforecast_kg"] == over
                assert loss["total_business_loss"] == 4 * under + over
                closing_rows.append(closing)
                processed_rows.append(processed)
                under_rows.append(under)
                over_rows.append(over)
                losses.append(loss["total_business_loss"])
                opening = closing
            row = rows[name]
            assert Decimal(row["max"]) == max(closing_rows)
            assert Decimal(row["ending"]) == closing_rows[-1]
            assert Decimal(row["shortfall"]) == sum(under_rows)
            assert Decimal(row["loss"]) == sum(losses)
            assert sum(point) == sum(processed_rows) + closing_rows[-1]
            operational[name] = (closing_rows, processed_rows, under_rows, over_rows, losses)
        assert operational["B"] == operational["C"]
        closing, processed, under, over, losses = operational["B"]
        assert closing == list(map(Decimal, fixture["backlog"]))
        assert under == list(
            map(
                Decimal,
                (
                    "0",
                    "0",
                    "0",
                    "20",
                    "60",
                    "40",
                    "0",
                    "0",
                    "0",
                    "0",
                    "20",
                    "0",
                    "0",
                    "0",
                    "0",
                ),
            )
        )
        assert sum(x > 0 for x in under) == 4
        assert sum(under) == 140 and sum(over) == 420 and sum(losses) == 980
        assert sum(operational["A"][2]) == 260
        assert sum(operational["A"][3]) == 240
        assert sum(operational["A"][4]) == 1280
        # A zero daily deficit may coexist with a nonzero carried queue.
        assert under[6] == 0 and closing[6] == 120
        summary = script.split("function capacityResults(){", 1)[1].split("function quality(){", 1)[
            0
        ]
        kpi_literal = summary.split("${[", 1)[1].split(".map(", 1)[0]
        kpis = ast.literal_eval("[" + kpi_literal)
        assert kpis == [
            ["日处理量不足", "4", "天"],
            ["累计日不足量", "140", "kg"],
            ["最大积压", "120", "kg"],
            ["期末积压", "0", "kg"],
        ]
        ratio = re.search(r"派生展示约 ([\d.]+)% · exact authority (\d+) / (\d+) kg", summary)
        assert ratio is not None
        assert Decimal(ratio[2]) == sum(processed) == 1820
        assert Decimal(ratio[3]) == Decimal(140) * 15 == 2100
        # Utilization's sole exception is derived Decimal50 HALF_EVEN division.
        with localcontext() as ratio_ctx:
            ratio_ctx.traps[Inexact] = False
            ratio_ctx.clear_flags()
            derived = Decimal(ratio[2]) / Decimal(ratio[3])
            assert ratio_ctx.flags[Inexact] and ratio_ctx.flags[Rounded]
            assert derived == Decimal("0.86666666666666666666666666666666666666666666666667")
            display = (derived * 100).quantize(Decimal("0.01"))
        assert Decimal(ratio[1]) == display == Decimal("86.67")
        assert "<dd>980 SYNTHETIC_LOSS_UNIT · 不是货币</dd>" in summary
        assert "rounding_applied=true" in summary
        ordered = sorted(
            rows,
            key=lambda name: (
                Decimal(rows[name]["loss"]),
                Decimal(rows[name]["max"]),
                Decimal(rows[name]["shortfall"]),
                Decimal(rows[name]["ending"]),
                name,
            ),
        )
        assert ordered == ["B", "C", "A"]
        assert [r["name"][0] for r in fixture["comparison"]] == ordered
        assert [rows[name]["rank"] for name in ordered] == ["1", "2", "3"]
        # B/C tie on all operational keys; lexical scenario ID is only the final tie-break.
        assert all(
            rows["B"][key] == rows["C"][key] for key in ("loss", "max", "shortfall", "ending")
        )


def test_static_synthetic_fixture_numerical_parity() -> None:
    audit_fixture(*static_fixture())


@pytest.mark.parametrize(
    "field",
    ["total7", "total15", "peak", "peakDate", "point", "capacity", "backlog", "loss", "rank"],
)
def test_fixture_audit_detects_literal_tampering(field: str) -> None:
    fixture, script = static_fixture()
    changed = copy.deepcopy(fixture)
    if field in {"point", "capacity", "backlog"}:
        changed[field][0] = "999"
    elif field in {"loss", "rank"}:
        changed["comparison"][0][field] = "999"
    else:
        changed[field] = "999"
    with pytest.raises(AssertionError):
        audit_fixture(changed, script)


@pytest.mark.parametrize(
    "old,new",
    [
        ("['日处理量不足','4','天']", "['日处理量不足','5','天']"),
        ("86.67%", "87.62%"),
        ("1820 / 2100", "1840 / 2100"),
        ("<dd>980 SYNTHETIC_LOSS_UNIT", "<dd>960 SYNTHETIC_LOSS_UNIT"),
    ],
)
def test_fixture_audit_detects_rendered_summary_tampering(old: str, new: str) -> None:
    fixture, script = static_fixture()
    assert old in script
    with pytest.raises(AssertionError):
        audit_fixture(fixture, script.replace(old, new))
