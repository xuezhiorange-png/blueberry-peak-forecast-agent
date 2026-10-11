"""Public current-runtime evidence and immutable historical sources are separate."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/v0-18/s1/local-auth-runtime-r1.json"


def test_runtime_evidence_canonical_sources_and_security_boundaries():
    raw = EVIDENCE.read_bytes()
    value = json.loads(raw)
    assert raw == (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    assert value["base_main_sha"] == "320f2046e3105b1b55da9cb037892571110b584a"
    for field in ("source_evidence_sha256", "frozen_history_sha256"):
        for relative, digest in value[field].items():
            path = Path(relative)
            assert not path.is_absolute() and ".." not in path.parts
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    assert set(value["security_acceptance"]) == {f"A{i:02}" for i in range(1, 21)}
    assert value["security_acceptance"]["A19"]["result"] == "BLOCKED"
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
