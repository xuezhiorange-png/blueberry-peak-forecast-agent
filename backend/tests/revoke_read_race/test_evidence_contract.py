"""Archived observations are evidence, not a replacement for current PG tests."""

import ast
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from backend.tests.historical_source import historical_bytes

ROOT = Path(__file__).resolve().parents[3]
ARCHIVE = ROOT / "docs/v0-18/evidence/backend-revoke-read-race-fix-r1"
MERGED_REVOKE_FIX = "8c6f8cdb579b97669e7cc27edea3e75ea32090e6"
PREAUTH_REVISED_TEST_SOURCES = {
    "backend/tests/business_access/test_contract.py",
    "backend/tests/mcp/test_v0_18_s3_contract.py",
    "backend/tests/revoke_read_race/test_evidence_contract.py",
}


def test_canonical_evidence_and_source_bytes():
    raw = (ARCHIVE / "evidence.json").read_bytes()
    value = json.loads(raw)
    assert raw == (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    assert value["base_main_sha"] == "4d61e3d64a4ecde2ccf90961bb5afa47ae6f19ec"
    for field in ("source_evidence_sha256", "artifact_sha256"):
        for relative, expected in value[field].items():
            path = Path(relative)
            assert not path.is_absolute() and ".." not in path.parts
            source = (
                historical_bytes(relative, MERGED_REVOKE_FIX)
                if field == "source_evidence_sha256" and relative in PREAUTH_REVISED_TEST_SOURCES
                else (ROOT / path).read_bytes()
            )
            assert hashlib.sha256(source).hexdigest() == expected
    assert value["backend_lead_2"] == "PENDING"
    assert value["production_readiness"] == "NOT_READY"
    assert value["independent_review"] == "PENDING"
    assert not any(value["governance"].values())


def test_original_red_and_unweakened_probe_are_preserved():
    original = (ARCHIVE / "original-red/executed-test-source.txt").read_bytes()
    assert hashlib.sha256(original).hexdigest() == (
        "056238c364557bd20ad8ac5fdbc8038e6921c321da903d7d1f1ddd35f1a7a4d7"
    )
    current = (ROOT / "backend/tests/revoke_read_race/test_original_repro.py").read_bytes()

    def probe(raw):
        return next(
            node
            for node in ast.parse(raw).body
            if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("test_lead_1_")
        )

    assert ast.dump(probe(original)) == ast.dump(probe(current))
    red = ET.parse(ARCHIVE / "original-red/red-junit.xml")
    assert len(red.findall(".//failure")) == 1
    observation = json.loads(
        next(
            p for p in red.findall(".//property") if p.attrib["name"] == "OPTION_B_PG_LEAD_1"
        ).attrib["value"]
    )
    assert observation["business_reads_after_disable_commit"] == 2
    assert observation["response_status"] == 401
    assert observation["sensitive_response_sent"] is False


def test_actual_green_properties_have_positive_controls_and_zero_post_commit_work():
    green = ET.parse(ARCHIVE / "matrix-green/backend.xml")
    assert not green.findall(".//failure") and not green.findall(".//error")
    assert not green.findall(".//skipped")
    assert len(green.findall(".//testcase")) == 49
    observed = [
        json.loads(p.attrib["value"])
        for p in green.findall(".//property")
        if p.attrib["name"] == "REVOKE_READ_PROOF"
    ]
    assert len(observed) == 35
    assert {v["revocation"] for v in observed} == {
        "disable",
        "grant",
        "session",
        "revision",
        "auth_revision",
    }
    for row in observed:
        assert row["positive_control_counts"]
        assert all(v > 0 for v in row["positive_control_counts"].values())
        assert row["post_commit_counts"] == {
            "business_sql": 0,
            "quality_file": 0,
            "simulation": 0,
            "comparison": 0,
        }
        assert row["sensitive_response_sent"] is False
    receipt = json.loads((ARCHIVE / "evidence.json").read_bytes())
    assert receipt["observed_post_disable_counts"] == {
        kind: sum(
            row["post_commit_counts"][kind] for row in observed if row["revocation"] == "disable"
        )
        for kind in ("business_sql", "quality_file", "simulation", "comparison")
    }
    for folder in (
        "original-red",
        "repeated-red",
        "matrix-green",
        "matrix-repeat",
        "related",
        "full-e2e",
    ):
        file = "owned-cleanup.json" if folder == "original-red" else "owned-resources.json"
        data = json.loads((ARCHIVE / folder / file).read_bytes())
        cleanup = data.get("cleanup", data)
        assert cleanup["state"] == "STOPPED"
        assert cleanup["listener_closed"] and cleanup["postmaster_absent"]
        assert cleanup["directory_identity_verified"]
    server = json.loads((ARCHIVE / "full-e2e/legacy-server-cleanup.json").read_bytes())
    assert server["owned_process_stopped"] and server["exit"] is not None
