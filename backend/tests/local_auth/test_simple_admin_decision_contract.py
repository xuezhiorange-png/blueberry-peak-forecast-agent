"""D03 additive decision, current sources, and immutable merged S1 evidence."""

import hashlib
import json
from pathlib import Path

from backend.tests.historical_source import historical_bytes

ROOT = Path(__file__).resolve().parents[3]
MERGED_D03 = "c35524174865785164fe4529f35067037ccddc2a"
S2_REVISED_SOURCES = {
    "backend/app/local_auth/service.py",
    "backend/app/core/config.py",
    "backend/tests/local_auth/test_runtime_evidence_contract.py",
    "backend/tests/local_auth/test_simple_admin_decision_contract.py",
}


def test_simple_admin_decision_preserves_history_and_runtime_boundaries():
    raw = (ROOT / "docs/v0-18/s1/simple-admin-d03-closure-r1.json").read_bytes()
    value = json.loads(raw)
    assert raw == (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    assert value["task_id"] == "V0_18_S1_SIMPLE_ADMIN_CLOSURE_R1"
    assert value["base_main_sha"] == "e9812e82067dceae444ff0707ceeb2f560c1018e"
    assert value["owner_simple_admin_scheme_approved"] is True
    assert value["per_account_preregistration_required"] is False
    assert value["per_assignment_external_approval_required"] is False
    assert value["catalog_source"] == "TRUSTED_SERVER_CONFIGURATION_ONLY"
    assert value["admin_has_implicit_business_access"] is False
    assert value["future_run_auto_grants"] is False
    assert value["quality_grant_independent"] is True
    assert value["security_acceptance_counts"] == {"pass_tested_scope": 20, "fail": 0, "blocked": 0}
    assert all(v is False for v in value["prohibited_actions"].values())
    for relative, expected in value["source_evidence_sha256"].items():
        path = Path(relative)
        assert not path.is_absolute() and ".." not in path.parts
        source = (
            historical_bytes(relative, MERGED_D03)
            if relative in S2_REVISED_SOURCES
            else (ROOT / path).read_bytes()
        )
        assert hashlib.sha256(source).hexdigest() == expected
    old_path = "docs/v0-18/s1/local-auth-runtime-r1.json"
    assert (ROOT / old_path).read_bytes() == historical_bytes(old_path, value["base_main_sha"])
    original = json.loads((ROOT / old_path).read_bytes())
    assert len(original["frozen_history_sha256"]) == 260
    for relative, expected in original["frozen_history_sha256"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected
