"""Public evidence binding and fresh-process pure reconciliation determinism."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def test_frozen_inputs_and_governance_evidence():
    root = Path(__file__).resolve().parents[3]
    evidence = json.loads(
        (
            root / "docs/v0-16/evidence/v0.16-s1-hierarchical-forecast-reconciliation-r1.json"
        ).read_text()
    )
    for name, expected in evidence["source_evidence_sha256"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
    assert evidence["SOURCE_FORECAST_FAMILY"] == "OPERATIONAL_PEAK_FORECAST_RUN_V1"
    assert evidence["FARM_HIERARCHY_ADMITTED"] is False
    assert evidence["FACTORY_HIERARCHY_ADMITTED"] is False
    assert evidence["MISSING_CHILD_AS_ZERO"] is False
    assert evidence["alembic_head_count"] == 1
    for name in (
        "CURRENT_SEASON_ACTUAL_READ",
        "MODEL_TRAINING_EXECUTED",
        "S2_STARTED",
        "V0_14_CHANGED",
        "V0_15_CHANGED",
        "READY_AUTHORIZED",
        "MERGE_AUTHORIZED",
        "TAG_AUTHORIZED",
        "RELEASE_AUTHORIZED",
        "PREEXISTING_P1_MODIFIED",
    ):
        assert evidence[name] is False


def test_fresh_process_deterministic_result_bytes():
    root = Path(__file__).resolve().parents[3]
    script = (
        "import json; "
        "import backend.tests.forecast_intelligence.test_reconciliation as t; "
        "from backend.app.forecast_intelligence.reconciliation import reconcile; "
        "print(json.dumps(reconcile(t.hierarchy(),t.request(),t.sources()),"
        "sort_keys=True,separators=(',',':')))"
    )
    first = subprocess.check_output([sys.executable, "-c", script], cwd=root)
    second = subprocess.check_output([sys.executable, "-c", script], cwd=root)
    assert first == second
    assert json.loads(first)["company_path_parity"] is True
