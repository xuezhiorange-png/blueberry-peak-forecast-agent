"""Predeclared synthetic conformal contracts; no real labels or training."""

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from random import Random
from zoneinfo import ZoneInfo

import pytest

from backend.app.area_yield.v015_research_cohort import canonical
from backend.app.forecast_intelligence.uncertainty import (
    MODEL_ID,
    CalibrationTargetRow,
    calibrate,
    evaluate,
    interval,
    order_statistic,
)


def rows(days=25, bases=2, leads=(1, 2, 7, 15)):
    result = []
    for day in range(days):
        origin = datetime(2025, 9, 1, 17, tzinfo=ZoneInfo("Asia/Shanghai")) + timedelta(days=day)
        for base in range(bases):
            for lead in leads:
                result.append(
                    CalibrationTargetRow(
                        row_key=f"synthetic-{day}-{base}#D{lead:02}",
                        base_id=f"synthetic-{base}",
                        season="2025-2026",
                        forecast_origin=origin,
                        lead_day=lead,
                        target_date=origin.date() + timedelta(days=lead),
                        point_prediction_kg=Decimal("10"),
                        actual_kg=Decimal(day + base),
                    )
                )
    return result


@pytest.mark.parametrize("n", [0, 1, 2, 3])
def test_insufficient_quantile(n):
    assert order_statistic([Decimal(i) for i in range(n)], 80) is None
    assert order_statistic([Decimal(i) for i in range(n)], 90) is None


def test_exact_quantiles_and_intervals():
    assert order_statistic(list(map(Decimal, range(1, 5))), 80) == 4
    assert order_statistic(list(map(Decimal, range(1, 5))), 90) is None
    scores = list(map(Decimal, range(1, 10)))
    assert order_statistic(scores, 80) == 8
    assert order_statistic(scores, 90) == 9
    assert interval(Decimal(10), Decimal(3), Decimal(4)) == {
        "lower_kg": "7",
        "upper_kg": "13",
        "upper_planning_bound_kg": "14",
    }
    assert interval(Decimal(2), Decimal(5), Decimal(7))["lower_kg"] == "0"
    assert order_statistic([Decimal(1)] * 8 + [Decimal(1000000)], 90) == 1000000


def test_order_invariance_and_nested_intervals():
    source = rows()
    expected = calibrate(source)
    Random(15016).shuffle(source)
    assert canonical(calibrate(source)) == canonical(expected)
    for r in expected:
        if r["interval_90_status"] == "COMPUTABLE":
            assert Decimal(r["prediction_interval_90"]["lower_kg"]) <= Decimal(
                r["prediction_interval_80"]["lower_kg"]
            )
            assert Decimal(r["prediction_interval_90"]["upper_kg"]) >= Decimal(
                r["prediction_interval_80"]["upper_kg"]
            )
            assert (
                Decimal(r["upper_planning_bound_90"]) >= Decimal(r["upper_planning_bound_80"]) >= 10
            )


@pytest.mark.parametrize("mutation", ["future", "target_today", "same_origin", "cross_lead"])
def test_leakage_mutation(mutation):
    source = rows()
    focus = source[12 * 8]
    before = next(r for r in calibrate(source) if r["row_key"] == focus.row_key)

    def forbidden(r):
        if mutation == "future":
            return r.forecast_origin > focus.forecast_origin
        if mutation == "target_today":
            return (
                r.forecast_origin < focus.forecast_origin
                and r.target_date >= focus.forecast_origin.date()
            )
        if mutation == "same_origin":
            return r.forecast_origin == focus.forecast_origin and r.base_id != focus.base_id
        return r.lead_day != focus.lead_day

    changed = [replace(r, actual_kg=Decimal(999999)) if forbidden(r) else r for r in source]
    after = next(r for r in calibrate(changed) if r["row_key"] == focus.row_key)
    assert canonical(before) == canonical(after)


def test_past_positive_sensitivity_and_zero_retained():
    source = rows(days=12, bases=1, leads=(1,))
    source = [replace(r, actual_kg=Decimal(0)) for r in source]
    baseline = calibrate(source)
    assert baseline[-1]["calibration_n"] == 10
    assert baseline[-1]["abs_score_q90_kg"] == "10"
    changed = calibrate(
        [replace(r, actual_kg=Decimal(1000)) if i < 9 else r for i, r in enumerate(source)]
    )
    assert changed[-1]["abs_score_q90_kg"] == "990"
    assert baseline[0]["prediction_interval_80"] is None
    assert baseline[0]["interval_80_covered"] is None


@pytest.mark.parametrize("bad", [1.5, Decimal("NaN"), Decimal("Infinity"), Decimal(-1)])
@pytest.mark.parametrize("field", ["actual_kg", "point_prediction_kg"])
def test_numeric_fail_closed(bad, field):
    with pytest.raises(ValueError, match="SOURCE_NUMERIC_INVALID"):
        calibrate([replace(rows(1)[0], **{field: bad})])


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("split", "VALIDATION", "SOURCE_SPLIT_INVALID"),
        ("season", "2026-2027", "FAIL_CURRENT_SEASON_ACTUAL_PRESENT"),
        ("point_model_id", "M0", "POINT_MODEL_IDENTITY_MISMATCH"),
        ("forecast_origin", datetime(2025, 9, 1), "SOURCE_ORIGIN_SEMANTICS_DRIFT"),
    ],
)
def test_source_identity_fail_closed(field, value, code):
    with pytest.raises(ValueError, match=code):
        calibrate([replace(rows(1)[0], **{field: value})])


def test_duplicate_and_horizon_accounting():
    with pytest.raises(ValueError, match="ROWSET_ACCOUNTING_FAILED"):
        calibrate([rows(1)[0]] * 2)
    result = calibrate(rows())
    metrics, leads, breadth, private = evaluate(result)
    assert metrics["H7"]["PI80"]["candidate_row_count"] == 25 * 2 * 3
    assert metrics["H15"]["PI80"]["candidate_row_count"] == len(result)
    assert len(leads) == 15
    assert "base_id" not in canonical(breadth).decode()
    assert private and MODEL_ID == "V0_15_S5_M1_RIDGE"
    for name, value in metrics["H15"].items():
        assert (
            value["candidate_row_count"]
            == value["computable_row_count"] + value["not_computable_row_count"]
        )
        assert value["covered_row_count"] <= value["computable_row_count"]
        if name.startswith("PI"):
            assert Decimal(value["min_interval_width_kg"]) >= 0


def test_coverage_inclusive_and_zero_denominator():
    result = calibrate(rows(days=1))
    m, _, _, _ = evaluate(result)
    assert m["H15"]["PI90"]["empirical_coverage"] is None
    assert m["H15"]["PI90"]["not_computable_row_count"] == len(result)


def test_inclusive_interval_endpoints_and_upper_bound():
    source = [replace(r, actual_kg=Decimal(13)) for r in rows(days=13, bases=1, leads=(1,))]
    source[-2] = replace(source[-2], actual_kg=Decimal(7))
    result = calibrate(source)
    assert result[-2]["prediction_interval_90"] == {"lower_kg": "7", "upper_kg": "13"}
    assert result[-2]["interval_90_covered"] is True
    assert result[-1]["interval_90_covered"] is True
    assert result[-1]["upper_90_covered"] is True
    with pytest.raises(ValueError, match="SOURCE_NUMERIC_INVALID"):
        interval(1.5, Decimal(1), Decimal(1))
