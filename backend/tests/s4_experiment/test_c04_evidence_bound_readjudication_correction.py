"""R3 provenance-bound C04 readjudication tests."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.s4_c04_validation_eligibility_rejudication import (
    R1_BREAKDOWN_EVIDENCE_INSUFFICIENT_REASON,
    R1_EVIDENCE_RELATIVE_PATH,
    R1_EVIDENCE_SHA256,
    R1EvidenceHashMismatch,
    load_c04_r1_evidence,
    readjudicate_c04_r1_evidence,
)

R1_EVIDENCE = Path(__file__).resolve().parents[3] / R1_EVIDENCE_RELATIVE_PATH


def test_readjudication_loads_r1_evidence_not_hardcoded_metrics() -> None:
    payload = json.loads(R1_EVIDENCE.read_text(encoding="utf-8"))
    parsed = load_c04_r1_evidence()

    assert parsed.sha256 == R1_EVIDENCE_SHA256
    assert parsed.candidates[0].daily_wape == Decimal(payload["RUNS"][0]["candidate_daily_wape"])
    assert parsed.candidates[0].daily_mae == Decimal(payload["RUNS"][0]["candidate_daily_mae"])
    assert parsed.incumbent.daily_wape == Decimal(payload["INCUMBENT_METRICS"]["daily_wape"])
    assert parsed.incumbent.daily_mae == Decimal(payload["INCUMBENT_METRICS"]["daily_mae"])


def test_readjudication_rejects_r1_evidence_hash_mismatch(tmp_path: Path) -> None:
    tampered = tmp_path / R1_EVIDENCE.name
    tampered.write_bytes(R1_EVIDENCE.read_bytes() + b"\n")

    with pytest.raises(R1EvidenceHashMismatch):
        load_c04_r1_evidence(tampered)


def test_readjudication_requires_real_breakdown_cell_evidence() -> None:
    parsed = load_c04_r1_evidence()

    assert parsed.real_breakdown_cell_evidence_available is False
    assert any(
        path.endswith(".breakdown_metrics.forecast_horizon_days.cells")
        for path in parsed.missing_breakdown_evidence
    )
    assert any(path.endswith(".no_silent_exclusion") for path in parsed.missing_breakdown_evidence)


def test_synthetic_coverage_cannot_issue_c04_winner() -> None:
    result = readjudicate_c04_r1_evidence()

    assert result.real_breakdown_cell_evidence_available is False
    assert result.run_eligibilities == ("NOT_PROVEN",) * 4
    assert result.best_validation_run is None
    assert result.validation_outcome == "BLOCKED_EVIDENCE_INSUFFICIENT"
    assert result.blocker == R1_BREAKDOWN_EVIDENCE_INSUFFICIENT_REASON
    assert result.v4_results == ()


def test_missing_cell_level_evidence_blocks() -> None:
    result = readjudicate_c04_r1_evidence()

    assert result.validation_outcome == "BLOCKED_EVIDENCE_INSUFFICIENT"
    assert result.run_eligibilities == ("NOT_PROVEN",) * 4


def test_no_validation_loader_called(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app import s4_v2_historical_only_execution

    def fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("R3 must not load SOURCE-002 or VALIDATION")

    monkeypatch.setattr(
        s4_v2_historical_only_execution,
        "load_frozen_engineering_dataset",
        fail_if_called,
    )
    result = readjudicate_c04_r1_evidence()

    assert result.validation_outcome == "BLOCKED_EVIDENCE_INSUFFICIENT"


def test_no_scorer_called(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.s4_candidate_04_historical_yield import C04HistoricalYieldScorer

    def fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("R3 must not invoke the C04 scorer")

    monkeypatch.setattr(C04HistoricalYieldScorer, "predict_rows", fail_if_called)
    result = readjudicate_c04_r1_evidence()

    assert result.validation_outcome == "BLOCKED_EVIDENCE_INSUFFICIENT"


def test_no_durable_execution_called(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.s4_candidate_execution_authority import S4CandidateExecutionAuthority

    async def fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("R3 must not call durable execution")

    monkeypatch.setattr(S4CandidateExecutionAuthority, "execute", fail_if_called)
    result = readjudicate_c04_r1_evidence()

    assert result.validation_outcome == "BLOCKED_EVIDENCE_INSUFFICIENT"


def test_c04_readjudication_budget_remains_8_24() -> None:
    result = readjudicate_c04_r1_evidence()

    assert result.validation_outcome == "BLOCKED_EVIDENCE_INSUFFICIENT"
    assert {
        "CANONICAL_STARTED_COUNT": 4,
        "C04_CANONICAL_STARTED_COUNT": 4,
        "EFFECTIVE_CONSUMED": 8,
        "REMAINING": 24,
        "R3_BUDGET_DELTA": 0,
        "NEW_VALIDATION_SCORING_CALL_COUNT": 0,
        "NEW_STARTED_EVENT_COUNT": 0,
    }["R3_BUDGET_DELTA"] == 0
