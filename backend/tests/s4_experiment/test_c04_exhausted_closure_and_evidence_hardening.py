"""R4 closure and future selection-evidence persistence tests."""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload
from backend.app.s4_c04_validation_eligibility_rejudication import (
    R1_EXPECTED_RUN_ORDINALS,
    load_c04_r1_evidence,
    readjudicate_c04_r1_evidence,
)
from backend.app.s4_experiment import (
    MAX_RUNS_PER_CANDIDATE,
    REQUIRED_BREAKDOWN_AXES,
    BreakdownAxisEvidence,
    BreakdownCellEvidence,
    CoverageQualityEvidence,
    MetricObservation,
    SelectionEvidenceProvenanceError,
    build_coverage_quality_evidence_payload,
    parse_coverage_quality_evidence_payload,
    validate_s4_selection_evidence_payload,
)


def _coverage_quality() -> CoverageQualityEvidence:
    return CoverageQualityEvidence(
        coverage_ratio=MetricObservation.computed("coverage_ratio", Decimal("1.000000")),
        valid_included_canonical_group_coverage=MetricObservation.computed(
            "valid_included_canonical_group_coverage", Decimal("1.000000")
        ),
        missing_data_proportion=MetricObservation.computed(
            "missing_data_proportion", Decimal("0.000000")
        ),
        breakdown_axes=tuple(
            BreakdownAxisEvidence(
                axis_name=axis,
                cells=(
                    BreakdownCellEvidence(
                        f"{axis}:small", 9, reason_code="RAW_SMALL_SAMPLE_REASON"
                    ),
                    BreakdownCellEvidence(f"{axis}:large", 12, reason_code="RAW_COMPUTED_REASON"),
                ),
            )
            for axis in REQUIRED_BREAKDOWN_AXES
        ),
        no_silent_exclusion=True,
    )


def test_c04_run_budget_is_exhausted_at_four() -> None:
    parsed = load_c04_r1_evidence()
    assert MAX_RUNS_PER_CANDIDATE == 4
    assert R1_EXPECTED_RUN_ORDINALS == (1, 2, 3, 4)
    assert tuple(run.run_ordinal for run in parsed.candidates) == R1_EXPECTED_RUN_ORDINALS


def test_c04_r3_blocker_is_final_for_current_evidence() -> None:
    result = readjudicate_c04_r1_evidence()
    assert result.validation_outcome == "BLOCKED_EVIDENCE_INSUFFICIENT"
    assert result.run_eligibilities == ("NOT_PROVEN",) * 4
    assert result.best_validation_run is None


def test_c04_observed_best_is_not_selection_winner() -> None:
    r2_path = Path(__file__).resolve().parents[3] / (
        "docs/v0-3/s4/evidence/s4-c04-validation-eligibility-policy-correction-r2.json"
    )
    r2 = json.loads(r2_path.read_text(encoding="utf-8"))
    assert r2["C04_BEST_RUN_ORDINAL"] == 1
    assert r2["C04_BEST_MULTIPLIER"] == "3.802757"
    assert readjudicate_c04_r1_evidence().best_validation_run is None


def test_evidence_serializer_persists_all_required_axes() -> None:
    payload = build_coverage_quality_evidence_payload(_coverage_quality())
    assert tuple(payload["breakdown_axes"]) == REQUIRED_BREAKDOWN_AXES
    assert len(payload["breakdown_axes"]) == 6


def test_evidence_serializer_persists_all_cells() -> None:
    payload = build_coverage_quality_evidence_payload(_coverage_quality())
    axes = payload["breakdown_axes"]
    assert all(len(axis_payload["cells"]) == 2 for axis_payload in axes.values())


def test_evidence_serializer_persists_comparable_rows() -> None:
    payload = build_coverage_quality_evidence_payload(_coverage_quality())
    rows = {
        cell["comparable_rows"]
        for axis_payload in payload["breakdown_axes"].values()
        for cell in axis_payload["cells"]
    }
    assert rows == {9, 12}


def test_evidence_serializer_persists_metric_status() -> None:
    payload = build_coverage_quality_evidence_payload(_coverage_quality())
    assert {
        cell["metric_status"]
        for axis_payload in payload["breakdown_axes"].values()
        for cell in axis_payload["cells"]
    } == {"COMPUTED"}


def test_serializer_persists_cell_reason_code() -> None:
    payload = build_coverage_quality_evidence_payload(_coverage_quality())
    assert {
        cell["reason_code"]
        for axis_payload in payload["breakdown_axes"].values()
        for cell in axis_payload["cells"]
    } == {"RAW_SMALL_SAMPLE_REASON", "RAW_COMPUTED_REASON"}


def test_parser_requires_cell_reason_code() -> None:
    payload = build_coverage_quality_evidence_payload(_coverage_quality())
    del payload["breakdown_axes"][REQUIRED_BREAKDOWN_AXES[0]]["cells"][0]["reason_code"]
    with pytest.raises(SelectionEvidenceProvenanceError, match="reason_code"):
        parse_coverage_quality_evidence_payload(payload)


def test_evidence_serializer_persists_no_silent_exclusion() -> None:
    payload = build_coverage_quality_evidence_payload(_coverage_quality())
    assert payload["no_silent_exclusion"] is True
    assert payload["summary_is_cell_evidence"] is False


def test_evidence_round_trip_preserves_cell_identity() -> None:
    original = _coverage_quality()
    payload = build_coverage_quality_evidence_payload(original)
    decoded = json.loads(canonical_json_dumps(payload))
    restored = parse_coverage_quality_evidence_payload(decoded)

    assert tuple(axis.axis_name for axis in restored.breakdown_axes) == REQUIRED_BREAKDOWN_AXES
    assert [cell.cell_id for axis in restored.breakdown_axes for cell in axis.cells] == [
        cell.cell_id for axis in original.breakdown_axes for cell in axis.cells
    ]
    assert [cell.comparable_rows for axis in restored.breakdown_axes for cell in axis.cells] == [
        cell.comparable_rows for axis in original.breakdown_axes for cell in axis.cells
    ]
    assert [cell.metric_status for axis in restored.breakdown_axes for cell in axis.cells] == [
        cell.metric_status for axis in original.breakdown_axes for cell in axis.cells
    ]
    assert [cell.reason_code for axis in restored.breakdown_axes for cell in axis.cells] == [
        cell.reason_code for axis in original.breakdown_axes for cell in axis.cells
    ]
    assert restored.no_silent_exclusion is True


def test_round_trip_preserves_cell_reason_code() -> None:
    original = _coverage_quality()
    restored = parse_coverage_quality_evidence_payload(
        json.loads(canonical_json_dumps(build_coverage_quality_evidence_payload(original)))
    )
    assert [cell.reason_code for axis in restored.breakdown_axes for cell in axis.cells] == [
        cell.reason_code for axis in original.breakdown_axes for cell in axis.cells
    ]


def test_metric_status_and_reason_code_are_independent() -> None:
    payload = build_coverage_quality_evidence_payload(_coverage_quality())
    cell = payload["breakdown_axes"][REQUIRED_BREAKDOWN_AXES[0]]["cells"][0]
    assert cell["metric_status"] == "COMPUTED"
    assert cell["reason_code"] == "RAW_SMALL_SAMPLE_REASON"


def test_reporting_reason_does_not_replace_metric_reason_code() -> None:
    payload = build_coverage_quality_evidence_payload(_coverage_quality())
    cell = payload["breakdown_axes"][REQUIRED_BREAKDOWN_AXES[0]]["cells"][0]
    assert cell["reporting_reason"] == "BELOW_MINIMUM"
    assert cell["reason_code"] == "RAW_SMALL_SAMPLE_REASON"
    assert cell["reporting_reason"] != cell["reason_code"]


def test_evidence_round_trip_hash_is_deterministic() -> None:
    payload = build_coverage_quality_evidence_payload(_coverage_quality())
    replay = json.loads(canonical_json_dumps(payload))
    assert sha256_payload(payload) == sha256_payload(replay)
    assert (
        build_coverage_quality_evidence_payload(parse_coverage_quality_evidence_payload(replay))
        == payload
    )


def test_compact_breakdown_summary_is_not_selection_evidence() -> None:
    compact_metrics = {
        "coverage_ratio": "1.000000",
        "valid_included_canonical_group_coverage": "1.000000",
        "missing_data_proportion": "0.000000",
        "breakdown_metrics": {
            axis: {
                "cell_count": 1,
                "below_minimum_cell_count": 0,
                "non_computed_cell_count": 0,
            }
            for axis in REQUIRED_BREAKDOWN_AXES
        },
    }
    with pytest.raises(SelectionEvidenceProvenanceError, match="PROVENANCE_INCOMPLETE"):
        validate_s4_selection_evidence_payload({"INCUMBENT_METRICS": compact_metrics, "RUNS": []})


def test_write_time_selection_evidence_gate_blocks_compact_payload(tmp_path: Path) -> None:
    from backend.app.s4_candidate_04_controlled_real_validation import write_evidence

    compact = {
        "INCUMBENT_METRICS": {
            "coverage_ratio": "1.000000",
            "breakdown_metrics": {
                axis: {"cell_count": 1, "below_minimum_cell_count": 0}
                for axis in REQUIRED_BREAKDOWN_AXES
            },
        },
        "RUNS": [],
    }
    output = tmp_path / "selection-evidence.json"
    with pytest.raises(SelectionEvidenceProvenanceError, match="PROVENANCE_INCOMPLETE"):
        write_evidence(output, compact)
    assert not output.exists()


def test_write_time_selection_evidence_accepts_canonical_cells(tmp_path: Path) -> None:
    from backend.app.s4_candidate_04_controlled_real_validation import write_evidence

    coverage_payload = build_coverage_quality_evidence_payload(_coverage_quality())
    evidence = {
        "INCUMBENT_METRICS": {"coverage_quality_evidence": coverage_payload},
        "RUNS": [{"candidate_metrics": {"coverage_quality_evidence": coverage_payload}}],
    }
    output = tmp_path / "selection-evidence.json"
    write_evidence(output, evidence)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert (
        written["INCUMBENT_METRICS"]["coverage_quality_evidence"]["summary_is_cell_evidence"]
        is False
    )


def test_incomplete_selection_evidence_fails_closed() -> None:
    payload = build_coverage_quality_evidence_payload(_coverage_quality())
    payload.pop("no_silent_exclusion")
    with pytest.raises(SelectionEvidenceProvenanceError):
        parse_coverage_quality_evidence_payload(payload)


def test_missing_reason_code_fails_closed() -> None:
    original = _coverage_quality()
    first_axis = original.breakdown_axes[0]
    first_cell = first_axis.cells[0]
    missing_reason = BreakdownCellEvidence(
        first_cell.cell_id,
        first_cell.comparable_rows,
        first_cell.metric_status,
    )
    incomplete = replace(
        original,
        breakdown_axes=(
            replace(first_axis, cells=(missing_reason, *first_axis.cells[1:])),
            *original.breakdown_axes[1:],
        ),
    )
    with pytest.raises(SelectionEvidenceProvenanceError, match="reason_code"):
        build_coverage_quality_evidence_payload(incomplete)


def test_no_validation_dataset_read(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app import s4_v2_historical_only_execution

    monkeypatch.setattr(
        s4_v2_historical_only_execution,
        "load_frozen_engineering_dataset",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("R4 must not load VALIDATION")
        ),
    )
    assert readjudicate_c04_r1_evidence().best_validation_run is None


def test_no_scorer_call(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.s4_candidate_04_historical_yield import C04HistoricalYieldScorer

    monkeypatch.setattr(
        C04HistoricalYieldScorer,
        "predict_rows",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("R4 must not call scorer")),
    )
    assert readjudicate_c04_r1_evidence().best_validation_run is None


def test_no_durable_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.s4_candidate_execution_authority import S4CandidateExecutionAuthority

    async def fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("R4 must not call durable execution")

    monkeypatch.setattr(S4CandidateExecutionAuthority, "execute", fail_if_called)
    result = readjudicate_c04_r1_evidence()
    assert result.v4_results == ()


def test_budget_remains_8_24() -> None:
    r1_path = Path(__file__).resolve().parents[3] / (
        "docs/v0-3/s4/evidence/s4-c04-controlled-real-validation-r1.json"
    )
    r1 = json.loads(r1_path.read_text(encoding="utf-8"))
    assert r1["FINAL_BUDGET_STATE"]["accepted_started_count"] == 4
    assert r1["FINAL_BUDGET_STATE"]["effective_consumed"] == 8
    assert r1["FINAL_BUDGET_STATE"]["remaining"] == 24
    assert readjudicate_c04_r1_evidence().validation_outcome == ("BLOCKED_EVIDENCE_INSUFFICIENT")


def test_test_remains_sealed() -> None:
    result = readjudicate_c04_r1_evidence()
    assert result.best_validation_run is None
