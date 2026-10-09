"""Offline correction evidence and immutable historical source binding."""

import hashlib
import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.contract]
ROOT = Path(__file__).resolve().parents[3]
FILE = ROOT / "docs/v0-17/evidence/v0.17-s6-postmerge-route-lifecycle-correction-r1.json"


def load():
    return json.loads(FILE.read_text())


def load_successor():
    return json.loads(
        FILE.with_name("v0.17-s6-postmerge-route-lifecycle-correction-r2.json").read_text()
    )


@pytest.mark.parametrize("group", ["source_evidence_sha256", "artifact_sha256"])
def test_exact_new_source_and_artifact_hashes(group):
    value = load()
    successor = load_successor()
    for relative, digest in value[group].items():
        assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
        if (
            group == "source_evidence_sha256"
            and relative in successor["historical_source_bindings"]
        ):
            binding = successor["historical_source_bindings"][relative]
            assert binding["historical_sha256"] == digest
            assert (
                hashlib.sha256((ROOT / binding["archive_path"]).read_bytes()).hexdigest()
                == digest
            )
            assert (
                hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
                == binding["current_sha256"]
            )
            continue
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest


def test_history_is_bound_without_rewriting_r2():
    old = json.loads(
        (ROOT / "docs/v0-17/evidence/v0.17-s6-cross-surface-product-acceptance-r2.json").read_text()
    )
    successor = load_successor()
    for source, binding in load()["historical_source_bindings"].items():
        assert binding["historical_sha256"] == old["source_evidence_sha256"][source]
        assert (
            hashlib.sha256((ROOT / binding["archive_path"]).read_bytes()).hexdigest()
            == binding["historical_sha256"]
        )
        if source in successor["historical_source_bindings"]:
            next_binding = successor["historical_source_bindings"][source]
            assert next_binding["historical_sha256"] == binding["current_sha256"]
            assert (
                hashlib.sha256((ROOT / next_binding["archive_path"]).read_bytes()).hexdigest()
                == binding["current_sha256"]
            )
            assert (
                hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
                == next_binding["current_sha256"]
            )
        else:
            assert (
                hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
                == binding["current_sha256"]
            )


def test_failed_ci_raw_artifact_inventory_and_real_repeat_matrix():
    folder = FILE.parent / "s6-postmerge-route-lifecycle-r1"
    failure = json.loads((folder / "original-failure-manifest.json").read_text())
    assert failure["run_id"] == 37807916550
    assert failure["head_sha"] == load()["base_main_sha"]
    assert failure["passed"] == 89 and failure["failed"] == 1
    assert failure["error"] == "route.fulfill: Route is already handled!"
    for suffix in ("run-logs.zip", "frontend-e2e.xml", "trace.zip", "error-context.md"):
        assert any(path.endswith(suffix) for path in failure["raw_artifact_sha256"])
    repeats = json.loads((folder / "repeat-results.json").read_text())
    assert len(repeats["cases"]) == 20
    for project in ("chromium-desktop", "chromium-mobile"):
        assert sum(row["project"] == project for row in repeats["cases"]) == 10
    browser = json.loads((folder / "dashboard-results.json").read_text())
    assert len(browser["cases"]) == 64
    assert all(case["status"] == "PASS" for case in browser["cases"])


def test_native_single_action_and_no_production_governance_overclaim():
    source = (ROOT / "frontend/e2e/dashboard.spec.ts").read_text()
    proxy = source.split("page: async", 1)[1].split("async function select", 1)[0]
    assert "await route.continue({" in proxy
    assert "route.fetch(" not in proxy and "route.fulfill(" not in proxy
    assert "ignoreErrors" not in source and "waitForTimeout" not in source
    value = load()
    assert not value["production_code_changed"] and not value["historical_evidence_rewritten"]
    assert not value["error_swallowing"] and not value["current_actual_accessed"]
    assert value["governance"]["production_readiness"] == "NOT_READY"
    for field in (
        "s6_formal_complete",
        "ready_authorized",
        "merge_authorized",
        "deploy_authorized",
        "version_closeout_authorized",
        "release_authorized",
    ):
        assert value["governance"][field] is False


def test_canonical_public_evidence():
    value = load()
    for path in [
        FILE,
        *(ROOT / relative for relative in value["artifact_sha256"] if relative.endswith(".json")),
    ]:
        raw = path.read_text()
        assert (
            raw == json.dumps(json.loads(raw), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        )
        assert "/Users/" not in raw and "/private/tmp/" not in raw
        assert "DATABASE_URL=" not in raw and "Authorization: Bearer" not in raw
