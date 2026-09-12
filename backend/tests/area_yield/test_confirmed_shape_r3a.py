from datetime import date, timedelta

import pytest

from backend.app.area_yield.confirmed_shape_r3a import fit, labels, metrics, predict


def fixture():
    days = [date(2023, 10, 1) + timedelta(days=i) for i in range(20)]
    return [
        {
            "date": str(d),
            "farm": "A",
            "quantity": "" if i == 3 else str(i + 1),
            "status": "UNKNOWN_GLOBAL_NO_RECORD" if i == 3 else "OBSERVED",
        }
        for i, d in enumerate(days)
    ]


def test_no_unknown_zero_imputation():
    result = labels(fixture())
    assert result[3] is None
    assert sum(v for v in result if v is not None) == pytest.approx(1)


@pytest.mark.parametrize("kind", ["ridge", "empirical"])
def test_model_hash_and_future_prediction(kind):
    model = fit({"A": fixture()}, "2023-2024", kind)
    prediction = predict(model, "2024-2025")
    assert len(prediction) == 365
    assert sum(prediction) == pytest.approx(1)
    assert min(prediction) >= 0
    model["training_season"] = "other"
    with pytest.raises(ValueError, match="hash"):
        predict(model, "2024-2025")


def test_training_rejects_validation():
    with pytest.raises(ValueError):
        fit({"A": fixture()}, "2024-2025", "ridge")


def test_future_label_cannot_reach_fit():
    rows = fixture()
    rows[0]["date"] = "2025-01-01"
    with pytest.raises(ValueError):
        fit({"A": rows}, "2023-2024", "ridge")


def test_unknown_labels_excluded_not_zeros_and_peak_tie_earliest():
    days = [date(2024, 7, 1) + timedelta(days=i) for i in range(14)]
    actual = [None] + [1 / 13] * 13
    result = metrics(days, actual, [1 / 14] * 14)
    assert result["known_rows"] == 13
    assert result["complete_7day_label_windows"] == 7
    assert result["actual_peak_date"] == "2024-07-02"
    assert result["predicted_peak_date"] == "2024-07-01"
    assert result["unknown_prediction_mass"] > 0


def test_empty_known_curve_rejected():
    with pytest.raises(ValueError):
        labels([{**r, "quantity": ""} for r in fixture()])
