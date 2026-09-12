"""User-approved business-window change does not alter raw data or learned models."""

from dataclasses import asdict
from datetime import date

import pytest

from backend.app.area_yield.business_boundary_r7b import (
    END,
    START,
    apply_window,
    qualify_window,
    window_rows,
)
from backend.app.area_yield.composite_r5 import compose, evaluate
from backend.app.area_yield.evidence_expansion_r6 import FarmSeasonQualification
from backend.app.area_yield.shape_r3 import season_calendar


def rows():
    return [
        {"farm": "f", "date": str(d), "quantity": "1", "status": "OBSERVED"}
        for d in season_calendar("2025-2026")
    ]


def qualification():
    return asdict(
        FarmSeasonQualification(
            "f",
            "2025-2026",
            "a" * 64,
            "2025-07-22",
            "2026-04-16",
            True,
            (),
            True,
            "RIGHT_CENSORED",
            True,
            "10",
            "BUSINESS_CONFIRMED",
            False,
            False,
            "NOT_COMPUTABLE_OTHER",
            "NOT_COMPUTABLE_OTHER",
            ("BOUNDARY_BUFFER_LT_14",),
        )
    )


def test_tail_excluded_from_labels_and_total():
    source = rows()
    for r in source:
        if r["date"] > str(END):
            r["quantity"] = "9999999"
    kept = window_rows(source)
    assert kept[0]["date"] == str(START) and kept[-1]["date"] == str(END)
    assert sum(int(r["quantity"]) for r in kept) == len(kept)
    assert source[-1]["quantity"] == "9999999"


def test_explicit_boundary_replaces_buffer_not_ledger_rules():
    q = qualify_window(qualification(), rows(), True)
    assert q.shape_evaluable and q.total_evaluable
    assert q.season_completeness_status == "STRICT_ELIGIBLE"
    assert "BOUNDARY_BUFFER_LT_14" not in q.exclusion_reasons
    source = rows()
    source[100]["quantity"] = ""
    q = qualify_window(qualification(), source, True)
    assert not q.shape_evaluable
    assert q.season_completeness_status == "GLOBAL_UNKNOWN_BLOCKED"
    assert source[100]["quantity"] == ""


def test_unknown_outside_active_span_retained_not_zero():
    source = rows()
    for r in source:
        if r["date"] < "2025-09-01":
            r["quantity"] = ""
    q = qualify_window(qualification(), source, True)
    assert q.shape_evaluable
    assert window_rows(source)[0]["quantity"] == ""


def test_area_missing_only_blocks_total():
    q = qualification()
    q.update(area_bound=False, productive_area_mu=None, area_basis=None)
    result = qualify_window(q, rows(), True)
    assert result.shape_evaluable and not result.total_evaluable


def test_historical_windows_cannot_be_changed():
    q = qualification()
    q["season"] = "2024-2025"
    with pytest.raises(ValueError):
        qualify_window(q, rows(), True)


def test_prediction_application_has_no_actual_input():
    raw = [1 / 365] * 365
    result = apply_window(raw)
    assert len(result["shares"]) == (END - START).days + 1
    assert sum(result["shares"]) == pytest.approx(1)
    assert raw == [1 / 365] * 365
    assert result["post_window_class"] == "TAIL_FRUIT_OUT_OF_SCOPE"
    assert result["post_window_mass"] > 0


def test_window_zero_mass_fails_without_fake_prediction():
    raw = [0.0] * 365
    raw[-1] = 1.0
    with pytest.raises(ValueError):
        apply_window(raw)


def test_in_window_peak_and_week_exact_despite_raw_tail_peak():
    raw = [1 / 365] * 365
    raw[-1] += 1
    raw = [v / 2 for v in raw]
    shares = apply_window(raw)["shares"]
    observed = window_rows(rows())
    m = evaluate(observed, "100", shares, str(START), str(END))
    assert m["peak_evaluation_status"] == "EXACT_COMPUTABLE"
    assert m["seven_day_evaluation_status"] == "EXACT_COMPUTABLE"
    assert date.fromisoformat(m["predicted_7day_start"]) <= date(2026, 4, 9)
    assert m["mass_balance_pass"]
    assert abs(float(sum(compose("100", shares))) - 100) < 0.001


@pytest.mark.parametrize("case", ["source", "zero", "train", "coverage"])
def test_other_qualification_failures_still_fail_closed(case):
    q = qualification()
    if case == "source":
        q["source_complete"] = False
    if case == "zero":
        q["ledger_zero_semantics_authorized"] = False
    if case == "coverage":
        q["coverage_end"] = "2026-04-14"
    assert not qualify_window(q, rows(), case != "train").shape_evaluable
