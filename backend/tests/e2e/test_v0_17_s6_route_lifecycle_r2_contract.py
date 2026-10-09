"""Offline immutable evidence and fail-closed all-active-route safety contract."""

import hashlib
import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.contract]
ROOT = Path(__file__).resolve().parents[3]
RECEIPT = ROOT / "docs/v0-17/evidence/v0.17-s6-postmerge-route-lifecycle-correction-r2.json"
R1 = RECEIPT.with_name("v0.17-s6-postmerge-route-lifecycle-correction-r1.json")
S6 = RECEIPT.with_name("v0.17-s6-cross-surface-product-acceptance-r2.json")
EXPECTED_REBOUND = {
    "frontend/e2e/dashboard-cross-surface.spec.ts",
    "frontend/e2e/selector-cancel-reopen.spec.ts",
    "backend/tests/e2e/test_v0_17_s6_evidence_contract.py",
    "backend/tests/e2e/test_v0_17_s6_route_lifecycle_contract.py",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_historical_evidence_and_source_chain_are_unchanged():
    receipt = json.loads(RECEIPT.read_text())
    first = json.loads(R1.read_text())
    original = json.loads(S6.read_text())
    assert receipt["base_main_sha"] == "d4ce572c0905c23423e72df393682178a8e9db41"
    assert set(receipt["historical_source_bindings"]) == EXPECTED_REBOUND
    assert receipt["frozen_evidence_sha256"][str(R1.relative_to(ROOT))] == sha(R1)
    assert receipt["frozen_evidence_sha256"][str(S6.relative_to(ROOT))] == sha(S6)
    for path, binding in receipt["historical_source_bindings"].items():
        assert sha(ROOT / binding["archive_path"]) == binding["historical_sha256"]
        assert sha(ROOT / path) == binding["current_sha256"]
        assert receipt["artifact_sha256"][binding["archive_path"]] == binding["historical_sha256"]
        if path in first["source_evidence_sha256"]:
            assert first["source_evidence_sha256"][path] == binding["historical_sha256"]
        if path in original["source_evidence_sha256"] and path not in first["historical_source_bindings"]:
            assert original["source_evidence_sha256"][path] == binding["historical_sha256"]
        if path in first["historical_source_bindings"]:
            prior = first["historical_source_bindings"][path]
            assert prior["current_sha256"] == binding["historical_sha256"]
            assert prior["historical_sha256"] == original["source_evidence_sha256"][path]


@pytest.mark.parametrize("group", ["source_evidence_sha256", "artifact_sha256"])
def test_new_source_and_artifact_hashes(group):
    for relative, digest in json.loads(RECEIPT.read_text())[group].items():
        assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
        assert sha(ROOT / relative) == digest


def test_every_active_proxy_is_single_owner_and_post_sdk_assertions_remain():
    for relative in (
        "frontend/e2e/dashboard.spec.ts",
        "frontend/e2e/dashboard-cross-surface.spec.ts",
        "frontend/e2e/selector-cancel-reopen.spec.ts",
    ):
        source = (ROOT / relative).read_text()
        assert "route.fetch(" not in source
        assert "await route.continue({" in source
        assert "ignoreErrors" not in source
        assert "waitForTimeout" not in source
    cross = (ROOT / "frontend/e2e/dashboard-cross-surface.spec.ts").read_text()
    assert cross.count("await assertPostHttpMcpParity(") == 3
    assert '"compare_capacity_scenarios"' in cross
    assert '"simulate_capacity"' in cross
    assert "await route.fallback();" in cross
    assert cross.count("await gate.started;") == 2
    assert cross.count("await gate.finished;") == 2
    selector = (ROOT / "frontend/e2e/selector-cancel-reopen.spec.ts").read_text()
    assert "await gate.started;" in selector and "await gate.finished;" in selector
    gate = (ROOT / "frontend/e2e/support/held-canonical-response.ts").read_text()
    assert "const upstream = await fetch(authorityUrl + path);" in gate
    assert "response.end(body);" in gate and "await held;" in gate


def test_both_red_main_ci_artifacts_preserved_without_success_overclaim():
    receipt = json.loads(RECEIPT.read_text())
    failures = receipt["original_failures"]
    assert {f["run_id"] for f in failures} == {37807916550, 37861642942}
    assert {f["passed"] for f in failures} == {89, 93}
    assert all(f["failed"] == 1 and f["conclusion"] == "failure" for f in failures)
    assert all(f["error"] == "route.fulfill: Route is already handled!" for f in failures)
    assert not receipt["production_code_changed"]
    assert not receipt["history_rewritten"]
    assert not receipt["error_swallowing"]
    assert not receipt["current_actual_accessed"]
    assert receipt["governance"]["production_readiness"] == "NOT_READY"
    for key in (
        "ready_authorized",
        "merge_authorized",
        "version_closeout_authorized",
        "deploy_authorized",
        "release_authorized",
        "s6_formal_complete",
    ):
        assert receipt["governance"][key] is False


def test_canonical_safe_public_evidence():
    receipt = json.loads(RECEIPT.read_text())
    for relative in (str(RECEIPT.relative_to(ROOT)), *receipt["artifact_sha256"]):
        raw = (ROOT / relative).read_text()
        if relative.endswith(".json"):
            assert (
                raw
                == json.dumps(json.loads(raw), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            )
        assert "/Users/" not in raw and "/private/tmp/" not in raw
        assert "Authorization: Bearer" not in raw
