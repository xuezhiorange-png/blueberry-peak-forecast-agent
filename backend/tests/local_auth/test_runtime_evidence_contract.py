"""Public current-runtime evidence and immutable historical sources are separate."""

import hashlib
import json
from pathlib import Path

from backend.tests.historical_source import historical_bytes

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/v0-18/s1/local-auth-runtime-r1.json"
MERGED_S1 = "e9812e82067dceae444ff0707ceeb2f560c1018e"
REVISED_RUNTIME_SOURCES = {
    "backend/tests/forecast_intelligence/test_v0_18_s1_preflight_contract.py",
    "backend/tests/e2e/test_v0_17_s6_evidence_contract.py",
    "backend/tests/forecast_intelligence/test_v0_18_roadmap_reassessment.py",
    "backend/app/models/__init__.py",
    ".github/workflows/ci.yml",
    "backend/app/local_auth/authorization.py",
    "frontend/src/test/dashboardGovernance.test.ts",
    "backend/tests/historical_source.py",
    "backend/app/main.py",
    "backend/app/local_auth/repository.py",
    "backend/app/core/config.py",
    "backend/app/local_auth/schemas.py",
    "backend/app/local_auth/service.py",
    "backend/app/api/local_auth_admin.py",
    "backend/tests/local_auth/test_runtime_evidence_contract.py",
}


def test_runtime_evidence_canonical_sources_and_security_boundaries():
    raw = EVIDENCE.read_bytes()
    value = json.loads(raw)
    assert raw == (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    assert value["base_main_sha"] == "320f2046e3105b1b55da9cb037892571110b584a"
    for field in ("source_evidence_sha256", "frozen_history_sha256"):
        for relative, digest in value[field].items():
            path = Path(relative)
            assert not path.is_absolute() and ".." not in path.parts
            source = (
                historical_bytes(relative, MERGED_S1)
                if field == "source_evidence_sha256" and relative in REVISED_RUNTIME_SOURCES
                else (ROOT / path).read_bytes()
            )
            assert hashlib.sha256(source).hexdigest() == digest
    assert set(value["security_acceptance"]) == {f"A{i:02}" for i in range(1, 21)}
    assert value["security_acceptance"]["A19"]["result"] == "PASS_TESTED_SCOPE"
    previous = value["r4_correction"]["previous_r3_snapshot"]
    original = historical_bytes("docs/v0-18/s1/local-auth-runtime-r1.json", previous["head_sha"])
    assert hashlib.sha256(original).hexdigest() == previous["evidence_sha256"]
    assert json.loads(original)["security_acceptance"]["A19"]["result"] == "BLOCKED"
    assert previous["a19_status"] == "BLOCKED"
    assert value["security_acceptance_counts"] == {"blocked": 0, "fail": 0, "pass_tested_scope": 20}
    assert value["r4_correction"]["previous_exact_head_ci"]["conclusion"] == "failure"
    assert value["dependency_review"]["unrelated_dependency_upgrades_authorized"] is False
    assert value["production_readiness"] == "NOT_READY"
    assert value["real_admin_and_org_authority"] == "PENDING"
    assert all(
        value["governance"][key] is False
        for key in (
            "s1_formal_complete",
            "ready_authorized",
            "merge_authorized",
            "deploy_authorized",
            "tag_authorized",
            "release_authorized",
            "s2_s6_authorized",
        )
    )
    assert value["legacy_entry"]["production_factory_bypass_option"] is False
    assert value["legacy_entry"]["test_entry_imported_by_production"] is False
    assert value["historical_hash_adaptation"]["expected_hashes_changed"] is False
