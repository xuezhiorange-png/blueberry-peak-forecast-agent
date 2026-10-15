"""New cleanup acceptance cannot rewrite or inherit the old S5 runtime PASS."""

import hashlib
import json

import pytest

from backend.tests.historical_source import historical_bytes
from backend.tests.safe_pilot.cleanup_evidence import EVIDENCE, ROOT, TASK, canonical
from backend.tests.safe_pilot.evidence import EVIDENCE as OLD_EVIDENCE
from backend.tests.safe_pilot.evidence import R1_CHECKPOINT, source_bytes

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_cleanup_correction_canonical_current_sources_and_artifacts():
    raw = EVIDENCE.read_bytes()
    value = json.loads(raw)
    assert raw == canonical(value)
    assert value["task_id"] == TASK
    assert value["previous_pr_head"] == R1_CHECKPOINT
    for path, expected in value["source_evidence_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    for path, entry in value["artifacts"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == entry["sha256"]
        if path.endswith("/owned-resources.json"):
            manifest = json.loads((ROOT / path).read_bytes())
            log_path = path.removesuffix("owned-resources.json") + "execution.log"
            assert manifest["execution_sha256"] == value["artifacts"][log_path]["raw_sha256"]
            if "cleanup" in manifest:
                assert manifest["cleanup"]["state"] == "STOPPED"
                assert manifest["cleanup"]["postmaster_absent"]
                assert manifest["cleanup"]["listener_closed"]
    assert len(value["case_matrix"]) == 8
    assert all(case["result"] == "PASS" for case in value["case_matrix"])
    assert value["browser_passed"] == 26
    assert value["local_backend_passed"] >= 230
    assert value["cleanup_contract"]["global_or_port_based_process_killing"] is False
    assert all(
        v
        for k, v in value["cleanup_contract"].items()
        if k != "global_or_port_based_process_killing"
    )
    assert value["limitations"]["production_code_changed"] is False
    assert value["limitations"]["production_readiness"] == "NOT_READY"
    assert not any(value["governance"].values())
    assert value["ci"]["old_green_reused"] is False


def test_original_s5_evidence_and_hash_expectations_remain_historical():
    old_raw = OLD_EVIDENCE.read_bytes()
    assert old_raw == historical_bytes(str(OLD_EVIDENCE.relative_to(ROOT)), R1_CHECKPOINT)
    old = json.loads(old_raw)
    for path, expected in old["source_evidence_sha256"].items():
        assert hashlib.sha256(source_bytes(path, R1_CHECKPOINT)).hexdigest() == expected
    # Current code really changed: historical hash checks are NOT runtime proof.
    runner = "backend/tests/safe_pilot/run.py"
    assert (
        hashlib.sha256((ROOT / runner).read_bytes()).hexdigest()
        != old["source_evidence_sha256"][runner]
    )
    with pytest.raises(AssertionError, match="UNREVIEWED_S5_SOURCE_CHECKPOINT"):
        source_bytes(runner, "0" * 40)
