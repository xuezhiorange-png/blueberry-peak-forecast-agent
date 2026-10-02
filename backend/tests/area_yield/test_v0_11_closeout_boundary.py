"""Closeout tests: synthetic engineering, never prospective model validation."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.area_yield import m0_baseline
from backend.tests.area_yield.test_m0_baseline_delivery_r1 import fitted
from scripts.replay_v0_11_closeout import verify_boundary

ROOT = Path(__file__).resolve().parents[3]
BOUNDARY = ROOT / "docs/v0-11/evidence/v0.11.0-research-engineering-closeout.json"


def test_identity_and_legacy_fixture_preserved() -> None:
    model = fitted()
    assert model["model_id"] == "M0-ALL-HISTORY-REFERENCE-R1"
    assert model["model_family"] == "M0_CORRECTED_TASK8_SHARED_SPLINE"
    assert model["model_role"] == "REFERENCE_BASELINE"
    assert model["approval_status"] == "RESEARCH_ONLY"
    legacy = m0_baseline.load_model(ROOT / "backend/tests/fixtures/m0-synthetic-test-only.json")
    assert legacy["schema"] == m0_baseline.LEGACY_SCHEMA
    assert legacy["model_id"] == m0_baseline.MODEL_FAMILY


@pytest.mark.parametrize(
    "field",
    [
        "VERSION_COMPLETE",
        "PROSPECTIVE_ACCURACY_VALIDATED",
        "PRODUCTION_USE_APPROVED",
        "CONDITIONAL_MODELS_PROMOTED",
        "V0_11_REOPEN_FOR_FUTURE_REQUEST",
    ],
)
def test_false_gate_cannot_be_promoted(field: str) -> None:
    payload = json.loads(BOUNDARY.read_text())
    payload[field] = True
    with pytest.raises(ValueError, match="CLOSEOUT"):
        verify_boundary(payload)


def test_closed_is_not_complete() -> None:
    payload = json.loads(BOUNDARY.read_text())
    verify_boundary(payload)
    assert payload["V0_11_LIFECYCLE_CLOSED"] and not payload["VERSION_COMPLETE"]


def test_public_replay_fresh_process() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.replay_v0_11_closeout"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["status"] == "PASS"
    assert report["level"] == "ENGINEERING_CLOSEOUT_REPLAY"
    assert report["real_forecast_count"] == 0
    assert report["private_row_level_data_required"] is False


def test_identity_role_cannot_be_promoted() -> None:
    model = fitted()
    model["model_role"] = "PRODUCTION_APPROVED"
    with pytest.raises(ValueError):
        m0_baseline.validate_model(m0_baseline.seal_model(model))
