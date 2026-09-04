"""Contract tests for S3-B quantile coverage execution R1 evidence."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = REPO_ROOT / "docs/v0-3/s3/evidence/s3-b-quantile-coverage-execution-r1.json"
WORKPAPER = REPO_ROOT / "docs/v0-3/s3/workpapers/s3-b-quantile-coverage-execution-r1.md"
MODULE = REPO_ROOT / "backend/app/forecast_quality/quantile_coverage.py"


def test_coverage_execution_r1_evidence_contract() -> None:
    payload = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert payload["artifact_id"] == "V0_3_S3_B_QUANTILE_COVERAGE_EXECUTION_R1"
    assert payload["s3_b_coverage_execution_authorized"] is True
    assert payload["s3_b_coverage_implementation"] == "COMPLETE"
    assert payload["s3_b_coverage_execution"] == "NOT_COMPUTABLE_OR_BLOCKED"
    assert payload["test_remains_sealed"] is True
    assert payload["s1_coverage_ratio_not_used"] is True
    assert MODULE.is_file()
    assert WORKPAPER.is_file()
