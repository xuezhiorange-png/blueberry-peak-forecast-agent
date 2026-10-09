"""Offline public closeout contracts; never collect live data or replay experiments."""

import ast
import hashlib
import json
import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.contract]
ROOT = Path(__file__).resolve().parents[3]
DOC = "docs/v0-17/v0.17.0-closeout.md"
RECEIPT = "docs/v0-17/evidence/v0.17.0-version-closeout-r1.json"
MANIFEST = "docs/v0-17/evidence/v0.17.0-version-closeout-manifest-r1.json"
BASE = "df6520404334bd518d3f65e3da470315bab194f9"
RELEASE_BASE = "2eb88a198fa2247ce813f8dac7bf7b41b8fdee32"
HEADS = (
    "6b80bcd416618dc70332d96c6e09afb7761d41bf",
    "02244bac750d1eedc10302e242e5f61ff30cc185",
    "cc045039e836baa19cd992ffb58e43cc13685a29",
    "ec3814c8391e4d0f66c4c56c3fca0a6748a8783a",
    "cb58a5661d0a3d159a3bdb1d10e383c4c877901f",
    "f635f728760c42718a78c3c537ebdc906d0f0adc",
    "2e5f639ab7d50de616ba6add80d1f4efce2c2359",
    "da398dd63a64c130bc723310419cafe9a8a41c64",
    "a7d5b3691ad2e13444c4f72d52b9dfa282092f18",
    "385906085a91b25c98913fd49a3dff14c1f3e6cc",
)
MERGES = (
    "1cabff0887b1525f15409b7bdc88ed2396a147d8",
    "ac4e862aea8b87d072835bbc1b2ae98e60adcb3e",
    "0512a2c4f21bc5faaac7936776ed2de8eecb5669",
    "4c9a29542cef2e0dc10812826d2b7e9333956c0a",
    "493d8a28daf4f35d4c6e6a3a933b09393c1080c5",
    "a7585286d5f654265025a7f79f5622f6d8474d35",
    "2022dc00b2aa685a2d7331aba5a47142f655a723",
    "eea84b6606ce356020da979d04a5d0d73af7bd6b",
    "d4ce572c0905c23423e72df393682178a8e9db41",
    BASE,
)
PR_RUNS = (
    37660361201,
    37710846272,
    37719264076,
    37727860163,
    37745161616,
    37761928112,
    37777753841,
    37800798505,
    37857931884,
    37874965290,
)
MAIN_RUNS = (
    37705147340,
    37714290836,
    37723603089,
    37732882094,
    37750293163,
    37767679478,
    37783261851,
    37807916550,
    37861642942,
    37881564725,
)
TOOLS = {
    "get_forecast_overview",
    "get_forecast_curve",
    "get_hierarchical_forecast",
    "get_forecast_uncertainty",
    "get_forecast_attribution",
    "get_forecast_quality",
    "simulate_capacity",
    "compare_capacity_scenarios",
}


def raw(relative):
    path = Path(relative)
    assert not path.is_absolute() and ".." not in path.parts
    assert path.parts[0] in {"docs", "backend", "frontend", "scripts"}
    return (ROOT / path).read_bytes()


def load(relative):
    return json.loads(raw(relative))


def canonical(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


@pytest.mark.parametrize("path", [RECEIPT, MANIFEST])
def test_canonical_bytes(path):
    value = load(path)
    assert raw(path) == canonical(value)
    assert canonical(dict(reversed(list(value.items())))) == raw(path)


def test_manifest_and_source_byte_binding():
    evidence, manifest = load(RECEIPT), load(MANIFEST)
    assert manifest["schema"] == "V0_17_VERSION_CLOSEOUT_MANIFEST_R1"
    assert set(manifest["members"]) == {DOC, RECEIPT}
    for path, expected in manifest["members"].items():
        assert hashlib.sha256(raw(path)).hexdigest() == expected
    sources = evidence["source_evidence_sha256"]
    assert evidence["source_evidence_count"] == manifest["source_evidence_count"] == len(sources)
    for path, expected in sources.items():
        assert re.fullmatch(r"[0-9a-f]{64}", expected)
        assert hashlib.sha256(raw(path)).hexdigest() == expected, path
    assert hashlib.sha256(canonical(sources)).hexdigest() == evidence["source_map_sha256"]


@pytest.mark.parametrize("index", range(10))
def test_exact_live_captured_stage_chain(index):
    stage = load(RECEIPT)["stage_chain"][index]
    previous = MERGES[index - 1] if index else RELEASE_BASE
    assert stage["pr_number"] == 699 + index
    assert stage["pr_state"] == "MERGED" and stage["merged"] is True
    assert stage["head_sha"] == HEADS[index]
    assert stage["base_sha"] == previous
    assert stage["merge_commit_sha"] == MERGES[index]
    assert stage["merge_parents"] == [previous, HEADS[index]]
    assert stage["git_merge_parents"] == stage["merge_parents"]
    assert stage["merged_by"] == "xuezhiorange-png"
    assert stage["implementation_authorization_verified"] is True
    assert stage["authorization_evidence"]["value"] is True
    authority = load(stage["authorization_evidence"]["path"])
    for key in stage["authorization_evidence"]["keys"]:
        authority = authority[key]
    assert authority is True
    reviews = stage["independent_reviews"]
    valid = [r for r in reviews if r["commit_id"] == HEADS[index] and r["result"] == "PASS"]
    assert valid and stage["independent_review_exact_head_match"] is True
    for review in valid:
        assert review["state"] == "COMMENTED"
        assert "independent" in review["summary"].lower()
        assert "PASS" in review["summary"]
        assert review["body_sha256"] and review["submitted_at"] <= stage["merged_at"]
    for key, event, head, run, expected in (
        ("pr_ci", "pull_request", HEADS[index], PR_RUNS[index], "success"),
        (
            "main_ci",
            "push",
            MERGES[index],
            MAIN_RUNS[index],
            "failure" if index in {7, 8} else "success",
        ),
    ):
        ci = stage[key]
        assert (ci["run_id"], ci["event"], ci["head_sha"]) == (run, event, head)
        assert ci["status"] == "completed" and ci["conclusion"] == expected
        assert ci["attempt"] >= 1 and len(ci["jobs"]) == 12
        assert len({j["id"] for j in ci["jobs"]}) == 12
        assert all(j["status"] == "completed" for j in ci["jobs"])
        counts = ci["job_counts"]
        for conclusion in ("success", "skipped", "failure", "cancelled"):
            assert counts[conclusion] == sum(j["conclusion"] == conclusion for j in ci["jobs"])
        assert counts["cancelled"] == 0
        assert counts["success"] == (12 if event == "pull_request" else 3 if index in {7, 8} else 4)
        assert counts["skipped"] == (0 if event == "pull_request" else 8)
        assert counts["failure"] == (1 if event == "push" and index in {7, 8} else 0)


def test_red_main_runs_remain_failures_and_final_closure_is_separate():
    evidence = load(RECEIPT)
    assert evidence["base_main_sha"] == BASE
    red = evidence["s6_correction_chain"]
    assert [r["failed_run_id"] for r in red] == [37807916550, 37861642942]
    assert [r["corrected_by_pr"] for r in red] == [707, 708]
    assert all(r["historical_conclusion"] == "failure" for r in red)
    assert all(r["error"] == "route.fulfill: Route is already handled!" for r in red)
    comment = evidence["s6_formal_confirmation"]
    assert comment["id"] == 6074984775 and comment["author"] == "xuezhiorange-png"
    assert comment["confirmed_main_sha"] == BASE
    assert comment["confirmed_main_ci"] == 37881564725
    assert comment["s6_formal_complete"] is True
    assert evidence["stage_chain"][7]["historical_main_gate_passed"] is False
    assert evidence["stage_chain"][8]["historical_main_gate_passed"] is False
    assert evidence["stage_chain"][9]["historical_main_gate_passed"] is True
    assert evidence["final_main_log_summaries"]["frontend-e2e"]["passed"] == 94
    assert evidence["final_main_log_summaries"]["full-suite-canary"]["passed"] == 9824


def test_frozen_isolation_and_historical_snapshots():
    evidence = load(RECEIPT)
    for audit in evidence["frozen_git_audit"].values():
        assert audit["changed_files"] == []
        assert audit["release_baseline"] == "v0.16.0"
    assert evidence["historical_evidence_unchanged"]
    for path, binding in evidence["historical_evidence_sha256"].items():
        assert hashlib.sha256(raw(path)).hexdigest() == binding["sha256"]
        assert binding["verified_against_committed_head"] in HEADS
    for path, key in (
        (
            "docs/v0-17/evidence/v0.17-s6-cross-surface-product-acceptance-r2.json",
            "s6_formal_complete",
        ),
        (
            "docs/v0-17/evidence/v0.17-s6-postmerge-route-lifecycle-correction-r1.json",
            "s6_formal_complete",
        ),
        (
            "docs/v0-17/evidence/v0.17-s6-postmerge-route-lifecycle-correction-r2.json",
            "s6_formal_complete",
        ),
    ):
        assert load(path)["governance"][key] is False


def test_product_capabilities_bind_real_source_and_accurate_coverage():
    evidence = load(RECEIPT)
    scope = load("docs/v0-17/evidence/v0.17.0-version-plan-and-product-scope-freeze-r1.json")
    product = evidence["capability_summary"]
    assert evidence["version"] == "0.17.0"
    assert evidence["version_name"] == "FORECAST_INTELLIGENCE_PRODUCTIZATION_AND_DASHBOARD"
    assert evidence["release_class"] == "PRODUCTIZATION_AND_ENGINEERING_VERSION"
    assert product["top_level_pages"] == scope["TOP_LEVEL_PAGES"]
    assert (
        product["mcp_tool_mapping"]
        == load("docs/v0-17/evidence/v0.17-s3-mcp-productization-r1.json")["eight_tool_mapping"]
    )
    assert set(product["mcp_tool_mapping"]) == TOOLS and len(TOOLS) == 8
    tree = ast.parse(raw("backend/app/mcp/forecast_intelligence_tools.py"))
    assignment = next(
        n
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "TOOLS" for t in n.targets)
    )
    assert {k.value for k in assignment.value.keys} == TOOLS
    dashboard = raw("frontend/src/dashboard/app/Dashboard.tsx").decode()
    assert re.findall(r'<Route path="([^"*]+)"', dashboard) == [
        "overview",
        "forecast",
        "attribution",
        "capacity",
        "quality",
    ]
    assert product["one_service_layer"] is True
    assert product["read_capability_count"] == 6
    assert product["decision_http_capability_count"] == 3
    s6 = load("docs/v0-17/evidence/v0.17-s6-cross-surface-product-acceptance-r2.json")
    assert product["s6_test_counts"] == s6["test_counts"]
    assert product["s6_acceptance_scope"] == "ISOLATED_SYNTHETIC_AVAILABLE_AUTHORITY"
    assert product["dashboard_parity_scope"] == "DOM_CASES_NOT_EVERY_BACKEND_PARAMETER_COMBINATION"
    matrix = load("docs/v0-17/evidence/s6-cross-surface-r2/parity-matrix.json")
    assert matrix and all(r["http_mcp_full_json_equality"] == "PASS" for r in matrix)
    assert {r["tool"] for r in matrix} == TOOLS
    assert product["conditional_ranking"] == ["B", "C", "A"]
    assert product["equal_quantity_ties_use_lexical_ids_not_shared_ordinal"] is True


def test_gates_retain_pending_closeout_and_release_states():
    evidence = load(RECEIPT)
    gates = evidence["version_complete_gates"]
    assert [g["gate_id"] for g in gates] == [f"G{i:02}" for i in range(1, 17)]
    assert [g["status"] for g in gates] == ["PASS"] * 13 + ["PENDING"] * 3
    assert all(g["evidence"] for g in gates)
    assert evidence["gate_counts"] == {"pass": 13, "pending": 3, "fail": 0}
    assert evidence["latest_formal_release"] == "v0.16.0"
    governance = evidence["governance"]
    assert governance["version_closeout_authorized"] is True
    assert governance["version_closeout_independent_review"] == "PENDING"
    assert governance["version_closeout_implementation_complete"] is False
    assert governance["external_exact_head_ci"] == "REQUIRED_SEPARATE_TERMINAL_PR_RECEIPT"
    assert all(governance[f"s{i}_formal_complete_verified"] for i in range(7))
    for key in (
        "version_closeout_formal_complete",
        "v0_17_version_complete",
        "ready_authorized",
        "merge_authorized",
        "tag_authorized",
        "release_authorized",
        "deploy_authorized",
        "v0_18_authorized",
        "v0_18_started",
        "tag_created",
        "release_created",
    ):
        assert governance[key] is False


def test_production_gaps_privacy_and_no_execution_overclaim():
    evidence = load(RECEIPT)
    assert evidence["scope"] == "PUBLIC_FROZEN_EVIDENCE_ONLY"
    assert evidence["production_readiness"] == "NOT_READY"
    assert evidence["limitations"] and all(v is False for v in evidence["limitations"].values())
    for field in (
        "private_data_read",
        "new_real_training",
        "new_real_scoring",
        "new_actual_access",
        "new_forecast_execution",
        "new_simulation_experiment",
        "production_code_changed",
    ):
        assert evidence[field] is False
    assert evidence["data_authority"] == {
        "strict_pit": False,
        "historical_actual_available_at_proven": False,
        "retrospective_authority_used": True,
        "current_season_actual_dependency": False,
        "current_season_actual_read": False,
        "current_season_actual_import": False,
        "current_season_actual_scoring": False,
    }
    for path in (DOC, RECEIPT, MANIFEST):
        assert not re.search(
            r"/(?:Users|private|tmp|root|home)/|postgres(?:ql)?://|"
            r"gh[pousr]_[A-Za-z0-9]+|Authorization: Bearer",
            raw(path).decode(),
        )
    tree = ast.parse(Path(__file__).read_text())
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    imports.update(a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names)
    assert imports == {"ast", "hashlib", "json", "re", "pathlib", "pytest"}


@pytest.mark.parametrize(
    "stage,expected",
    [
        ("S2", "f35f2700011f440569c9a0140dc9deb482281d60190e8a601b5a503c79013efd"),
        ("S3", "950d7d4885c4a96b43bba5ad6b586ee7a424ae86482618a8be22ed272039a422"),
        ("S4", "6dfe2c1ac684844af636d936b5797d301e80f015c9e3dd880a102127a169ac1c"),
        ("S5", "740c0a48506b524ea822b88ad9c5b3443cf3356969026e02cff4a6e1a3c446b7"),
        ("S6", "c1712c6596a813816eefbcb8d51c7088304549cfcc1899a637dff1b150be6463"),
    ],
)
def test_independent_frozen_policy_identity(stage, expected):
    pin = load(RECEIPT)["frozen_policy_pins"][stage]
    assert pin["POLICY_HASH"] == expected
    payload = load(pin["PATH"])
    assert payload["policy_hash"] == expected
    serialized = (
        json.dumps(payload["policy"], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        + "\n"
    ).encode()
    assert hashlib.sha256(serialized).hexdigest() == expected


def test_required_production_gaps_and_old_blocked_reviews_cannot_disappear():
    evidence = load(RECEIPT)
    required = {
        "production_multi_user_scope_validated",
        "normal_business_discovery_available",
        "business_run_selector_backend_ready",
        "production_access_isolation_verified",
        "production_service_account_configured",
        "production_run_grants_verified",
        "production_deployed",
        "child_contribution_authority_available",
        "upper80_run_bound_authority",
        "upper90_run_bound_authority",
        "attribution_run_bound_authority",
        "current_season_actual_available",
        "prospective_accuracy_validated",
        "canonical_company_cost_established",
        "real_roi_validated",
        "real_ios_safari_validated",
        "screen_reader_validated",
        "soft_keyboard_validated",
    }
    assert required <= evidence["limitations"].keys()
    reviews = {r["id"]: r for s in evidence["stage_chain"] for r in s["independent_reviews"]}
    assert reviews[5453163827]["result"] == reviews[5458870712]["result"] == "BLOCKED"
    assert reviews[5453800712]["result"] == reviews[5459657345]["result"] == "PASS"


def test_public_upstream_map_has_independent_immutable_anchor():
    sources = load(RECEIPT)["source_evidence_sha256"]
    upstream = {
        path: value
        for path, value in sources.items()
        if path
        not in {
            "backend/tests/forecast_intelligence/test_v0_17_version_closeout.py",
            "backend/tests/forecast_intelligence/build_v0_17_version_closeout.py",
        }
    }
    assert hashlib.sha256(canonical(upstream)).hexdigest() == (
        "dc22a7317d01f8d1ff295a4b175531b052d60e98cce6fcb3b54b83d93fb56d77"
    )
