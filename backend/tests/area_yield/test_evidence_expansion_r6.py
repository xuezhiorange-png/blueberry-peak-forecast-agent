from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.app.area_yield.data import digest
from backend.app.area_yield.evidence_expansion_r6 import (
    build_qualifications,
    prior_prediction,
    validate_daily,
)
from backend.app.area_yield.total_yield_r4 import Area


def facts():
    start = date(2023, 7, 1)
    return [
        {
            "canonical_farm_id": f,
            "date": str(start + timedelta(days=i)),
            "daily_harvest_kg": "10" if f == "farm" and 15 <= i <= 25 else "0",
        }
        for i in range(50)
        for f in ("farm", "other")
    ]


def area(basis="BUSINESS_CONFIRMED"):
    return Area("farm", "10", basis, "explicit confirmation", "a" * 64, "FARM", True)


def qualify(rows=None, areas=None, complete=True):
    return build_qualifications(
        facts() if rows is None else rows,
        "2023-2024",
        "b" * 64,
        date(2023, 7, 1),
        date(2023, 8, 19),
        complete,
        True,
        {"farm"},
        areas or {},
    )


def test_exact_identity_and_no_fuzzy_match():
    q, _, _ = qualify()
    assert not next(r for r in q if r.canonical_farm == "other").shape_evaluable
    assert next(r for r in q if r.canonical_farm == "farm").shape_evaluable


def test_global_unknown_remains_unknown_and_blocks_active_span():
    rows = [r for r in facts() if r["date"] != "2023-07-21"]
    q, curves, _ = qualify(rows)
    f = next(r for r in q if r.canonical_farm == "farm")
    assert f.season_completeness_status == "GLOBAL_UNKNOWN_BLOCKED"
    assert f.active_span_global_unknown_days == ("2023-07-21",)
    assert next(r for r in curves["farm"] if r["date"] == "2023-07-21")["quantity"] == ""


def test_active_source_absence_is_ledger_zero_not_unknown():
    rows = [
        r for r in facts() if not (r["canonical_farm_id"] == "farm" and r["date"] == "2023-07-21")
    ]
    q, curves, _ = qualify(rows)
    assert next(r for r in q if r.canonical_farm == "farm").shape_evaluable
    cell = next(r for r in curves["farm"] if r["date"] == "2023-07-21")
    assert cell["quantity"] == "0"
    assert cell["status"] == "SOURCE_ACTIVE_LEDGER_ZERO"


@pytest.mark.parametrize(
    "basis", ["PREVIOUS_SEASON_PROXY", "INFERRED_FROM_YIELD", "CROSS_FARM_COPY", "GUESS"]
)
def test_area_authority_rejects_unapproved_basis(basis):
    with pytest.raises(ValueError):
        qualify(areas={"farm": area(basis)})


def test_area_missing_does_not_block_shape_and_same_area_across_seasons():
    q, _, _ = qualify()
    f = next(r for r in q if r.canonical_farm == "farm")
    assert f.shape_evaluable and not f.total_evaluable and not f.area_bound
    q, _, _ = qualify(areas={"farm": area()})
    assert next(r for r in q if r.canonical_farm == "farm").total_evaluable


def test_qualification_deterministic_under_reorder():
    a, _, _ = qualify()
    b, _, _ = qualify(list(reversed(facts())))
    assert a == b


@pytest.mark.parametrize("value", ["", "-1", "NaN", "Infinity"])
def test_new_daily_source_invalid_values_fail_closed(value):
    rows = facts()
    rows[0]["daily_harvest_kg"] = value
    with pytest.raises(ValueError):
        validate_daily(rows)


def test_duplicate_daily_grain_rejected():
    with pytest.raises(ValueError):
        validate_daily(facts() + [facts()[0]])


def test_incomplete_source_never_zero_fills_or_scores():
    q, _, _ = qualify(complete=False)
    assert all(not r.total_evaluable and not r.shape_evaluable for r in q)


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity"])
def test_invalid_area_never_inferred(value):
    invalid = Area("farm", value, "MEASURED", "source", "a" * 64, "FARM", True)
    with pytest.raises(ValueError):
        qualify(areas={"farm": invalid})


def test_unconfirmed_absence_remains_unknown():
    rows = [
        r for r in facts() if not (r["canonical_farm_id"] == "farm" and r["date"] == "2023-07-21")
    ]
    _, curves, _ = qualify(rows, complete=False)
    assert next(r for r in curves["farm"] if r["date"] == "2023-07-21")["quantity"] == ""


def test_prior_prediction_has_no_fit_and_preserves_unknown(monkeypatch):
    from backend.app.area_yield import confirmed_shape_r3a, total_yield_r4

    def forbidden(*args, **kwargs):
        pytest.fail("fit invoked")

    monkeypatch.setattr(confirmed_shape_r3a, "fit", forbidden)
    monkeypatch.setattr(total_yield_r4, "fit", forbidden)
    _, curves, _ = qualify()
    before = digest(curves)
    shares, value = prior_prediction(curves["farm"], "2023-2024", "2024-2025", "10")
    assert digest(curves) == before
    assert abs(sum(shares) - 1) < 1e-12
    assert all(v >= 0 for v in shares)
    assert Decimal(value) == 11
    with pytest.raises(ValueError):
        prior_prediction(curves["farm"], "2023-2024", "2023-2024", "10")
