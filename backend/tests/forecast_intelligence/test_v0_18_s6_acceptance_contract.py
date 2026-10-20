"""Offline provenance/governance contract; runtime acceptance is separate."""

import hashlib
import json
from pathlib import Path

import pytest

from backend.tests.historical_source import historical_bytes

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/v0-18/evidence/s6-business-and-security-acceptance-r1.json"
pytestmark = [pytest.mark.unit, pytest.mark.contract]
S6_DELIVERY = "2b890d8e68a47ca506e7cf6b04bd187472138b2d"
EVOLVING_S6_SOURCES = {
    "frontend/e2e/dashboard-business-flow.spec.ts",
    "frontend/e2e/dashboard-s6-acceptance.spec.ts",
    "backend/tests/forecast_intelligence/test_v0_18_s6_acceptance_contract.py",
    "backend/tests/safe_pilot/evidence.py",
}


def checked_source(path, expected, group, commit=S6_DELIVERY):
    raw = (
        historical_bytes(path, commit, root=ROOT)
        if group == "source_evidence_sha256" and path in EVOLVING_S6_SOURCES
        else (ROOT / path).read_bytes()
    )
    assert hashlib.sha256(raw).hexdigest() == expected, path
    return raw


def test_s6_canonical_sources_history_and_artifacts():
    raw = EVIDENCE.read_bytes()
    value = json.loads(raw)
    assert raw == (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    for group in ("source_evidence_sha256", "frozen_history_sha256", "artifacts"):
        for path, entry in value[group].items():
            relative = Path(path)
            assert not relative.is_absolute() and ".." not in relative.parts
            expected = entry["sha256"] if isinstance(entry, dict) else entry
            checked_source(path, expected, group)
    assert value["base_main_sha"] == "fc0b88cf222567e4821a9d11589331f6a7963e04"
    assert value["SYNTHETIC"] is True
    assert value["local_backend"]["new_s6_case_count"] >= 14


@pytest.mark.parametrize("path", sorted(EVOLVING_S6_SOURCES))
def test_fixed_s6_sources_reject_wrong_commit_and_changed_hash(path):
    expected = json.loads(EVIDENCE.read_bytes())["source_evidence_sha256"][path]
    checked_source(path, expected, "source_evidence_sha256")
    with pytest.raises(AssertionError, match="Required historical commit unavailable"):
        checked_source(path, expected, "source_evidence_sha256", commit="0" * 40)
    with pytest.raises(AssertionError):
        checked_source(path, "0" * 64, "source_evidence_sha256")


def test_s6_no_false_authority_or_governance_upgrade():
    value = json.loads(EVIDENCE.read_bytes())
    assert len(value["parity_matrix"]) == 54
    assert len(value["zero_read_proofs"]) == 8
    for proof in value["zero_read_proofs"]:
        for field in (
            "BUSINESS_READ_COUNT",
            "QUALITY_FILE_READ_COUNT",
            "SIMULATION_EXECUTION_COUNT",
        ):
            assert proof[field] == 0
    assert len(value["tls_release_proofs"]) == 2
    for proof in value["tls_release_proofs"]:
        assert proof["canonical_read_reached"] and proof["revocation_committed_before_release"]
        assert proof["sensitive_bytes_returned"] is False
    screenshots = value["browser"]["screenshots"]
    assert len(screenshots) >= 60
    assert len({s["path"] for s in screenshots}) == len(screenshots)
    sources = [value["artifacts"][s["path"]]["source_path"] for s in screenshots]
    identities = [value["artifacts"][s["path"]]["provenance"] for s in screenshots]
    assert len(set(sources)) == len(sources) and len(set(identities)) == len(identities)
    assert all("dashboard-s6-acceptance.spec.ts" in s["spec"] for s in screenshots)
    assert value["known_limits"]["real_ios_safari"] == "NOT_VALIDATED"
    assert value["governance"]["s6_authorized"] is True
    assert value["governance"]["production_readiness"] == "NOT_READY"
    assert all(
        v is False
        for k, v in value["governance"].items()
        if k not in {"s6_authorized", "production_readiness"}
    )


def test_s6_complete_scoped_matrix_and_fresh_screenshot_sources():
    value = json.loads(EVIDENCE.read_bytes())
    assert {
        row["forecast_identity"]["hierarchy_level"]
        for row in value["parity_matrix"]
        if row["forecast_identity"]
    } == {"BASE", "REGION", "COMPANY"}
    assert len({row["tool"] for row in value["parity_matrix"]}) == 8
    assert {row["planning_level"] for row in value["parity_matrix"] if row["planning_level"]} == {
        "POINT",
        "UPPER_PLANNING_BOUND_80",
        "UPPER_PLANNING_BOUND_90",
    }
    required = {"1440x900", "1280x800", "1024x768", "834x1112", "390x844", "360x800"}
    screenshots = value["browser"]["screenshots"]
    for page in ("overview", "curve", "attribution", "capacity", "quality"):
        for viewport in required:
            matched = [
                s for s in screenshots if s["attachment"] == f"S6-{page}-{viewport}-SYNTHETIC"
            ]
            assert {s["project"] for s in matched} == {"chromium-desktop", "chromium-mobile"}
    assert len(value["stage_chain_fresh_verification"]) == 7
    assert value["stage_chain_fresh_verification"][1]["ci"]["conclusion"] == "failure"
    assert value["stage_chain_fresh_verification"][-1]["ci"]["attempt"] == 2
    assert value["stage_chain_fresh_verification"][-1]["ci"]["conclusion"] == "success"
    assert all(row["status"] == "PASS" for row in value["browser"]["cases"])
