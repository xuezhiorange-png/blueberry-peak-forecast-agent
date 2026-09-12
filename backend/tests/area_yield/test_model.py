from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.app.area_yield.data import AreaAuthority, Receipt, materialize
from backend.app.area_yield.evaluation import compare
from backend.app.area_yield.model import fit_model, predict


def rows():
    return [
        {
            "date": (date(2024, 10, 1) + timedelta(days=i)).isoformat(),
            "area_mu": "10.000000",
            "actual_kg": str(i + 1),
            "scope_id": "scope",
            "season_id": "2024-2025",
            "observation_status": "OBSERVED",
        }
        for i in range(40)
    ]


@pytest.mark.parametrize("kind", ["baseline", "ridge"])
def test_area_scaling_and_serializable_model(kind):
    import json

    model = fit_model(rows(), kind, date(2024, 11, 9), "scope")
    loaded = json.loads(json.dumps(model))
    dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(7)]
    small = predict(loaded, dates, Decimal("10"), "scope")
    large = predict(loaded, dates, Decimal("20"), "scope")
    assert all(abs(b - a * 2) <= Decimal("0.000001") for a, b in zip(small, large, strict=True))
    assert all(x.is_finite() and x >= 0 for x in small)


@pytest.mark.parametrize("area", ["0", "-1", "NaN", "Infinity"])
def test_invalid_area_rejected(area):
    model = fit_model(rows(), "baseline", date(2024, 11, 9), "scope")
    with pytest.raises(ValueError):
        predict(model, [date(2025, 1, 1)], Decimal(area), "scope")


def test_future_training_rows_and_wrong_scope_rejected():
    with pytest.raises(ValueError, match="cutoff"):
        fit_model(rows(), "ridge", date(2024, 10, 2), "scope")
    with pytest.raises(ValueError, match="scope"):
        fit_model(rows(), "ridge", date(2024, 11, 9), "wrong")


def test_area_scope_period_and_missing_zero_policy():
    start = date(2024, 10, 1)
    area = AreaAuthority(
        "scope",
        "2024-2025",
        start,
        start + timedelta(days=2),
        Decimal("10"),
        "AUTHORIZED_CALIBRATION",
        "owner",
        False,
    )
    receipt = Receipt("r1", "scope", "2024-2025", start, Decimal("20"), "DETAIL")
    result = materialize([receipt], area)
    assert result[0]["actual_kg"] == "20.000000"
    assert result[1]["actual_kg"] == ""
    assert result[1]["observation_status"] == "UNKNOWN_MISSING"
    from dataclasses import replace

    zero = materialize([receipt], replace(area, complete_ledger=True))
    assert zero[1]["actual_kg"] == "0.000000"
    assert zero[1]["observation_status"] == "AUTHORIZED_LEDGER_ZERO"
    with pytest.raises(ValueError):
        materialize([replace(receipt, scope_id="wrong")], area)
    with pytest.raises(ValueError):
        materialize([replace(receipt, day=start - timedelta(days=1))], area)
    with pytest.raises(ValueError):
        materialize([replace(receipt, season_id="wrong")], area)


def test_aggregation_no_duplicate_or_parent_detail_double_count():
    day = date(2024, 10, 1)
    area = AreaAuthority("scope", "season", day, day, Decimal("10"), "MEASURED", "source", True)
    row = Receipt("r1", "scope", "season", day, Decimal("10"), "DETAIL")
    assert materialize([row, row], area)[0]["actual_kg"] == "10.000000"
    from dataclasses import replace

    with pytest.raises(ValueError):
        materialize([row, replace(row, quantity=Decimal("11"))], area)
    with pytest.raises(ValueError):
        materialize([row, replace(row, source_id="sum", grain="AGGREGATE")], area)


def test_complete_seven_day_metrics_and_missing_labels():
    r = rows()[:8]
    metric = compare(r, [Decimal(x["actual_kg"]) for x in r])
    assert metric["daily_wape"] == "0.000000"
    assert metric["rolling_7day_peak_absolute_error_kg"] == "0.000000"
    r[3]["actual_kg"] = ""
    metric = compare(r, [Decimal("1")] * 8)
    assert metric["window_metrics_status"] == "NOT_COMPUTABLE_MISSING_LABELS"
    assert metric["window_total_absolute_error_kg"] is None


def test_zero_wape_denominator_is_not_zero_score():
    r = rows()[:8]
    for row in r:
        row["actual_kg"] = "0"
    assert compare(r, [Decimal("1")] * 8)["daily_wape"] is None


def test_prediction_requires_no_actuals_and_future_features():
    model = fit_model(rows(), "ridge", date(2024, 11, 9), "scope")
    assert model["feature_names"] == ["sin1", "cos1", "sin2", "cos2"]
    expected = predict(model, [date(2025, 2, 1)], Decimal("10"), "scope")
    changed = rows()
    changed[-1]["actual_kg"] = "999999"
    assert predict(model, [date(2025, 2, 1)], Decimal("10"), "scope") == expected


def test_fit_and_hash_are_deterministic_and_scaler_is_train_only():
    first = fit_model(rows(), "ridge", date(2024, 11, 9), "scope")
    second = fit_model(rows(), "ridge", date(2024, 11, 9), "scope")
    assert first == second
    from backend.app.area_yield.model import features
    import numpy as np

    expected = np.mean([features(date.fromisoformat(r["date"])) for r in rows()], axis=0)
    assert first["scaler_mean"] == expected.tolist()


def test_subwindow_not_renormalized_to_full_season_total():
    model = fit_model(rows(), "ridge", date(2024, 11, 9), "scope")
    dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(30)]
    full = predict(model, dates, Decimal("10"), "scope")
    assert predict(model, dates[:7], Decimal("10"), "scope") == full[:7]


def test_seven_day_peak_is_cumulative_and_earliest_tie():
    from backend.app.area_yield.evaluation import summaries

    dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(8)]
    result = summaries(dates, [Decimal("2")] * 8)
    assert result["rolling_7day_peak"]["cumulative_quantity_kg"] == "14.000000"
    assert result["rolling_7day_peak"]["start_date"] == "2025-01-01"
    assert result["single_day_peak"]["date"] == "2025-01-01"
