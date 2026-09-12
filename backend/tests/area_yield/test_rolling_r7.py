"""Rolling authorization is past-data refitting, not target-season tuning."""

from datetime import date

import pytest

from backend.app.area_yield import confirmed_shape_r3a as shape
from backend.app.area_yield import total_yield_r4 as total
from backend.app.area_yield.evidence_expansion_r6 import prior_prediction
from backend.app.area_yield.shape_r3 import season_calendar


def curve(season="2024-2025"):
    return [
        {"farm": "farm", "date": str(d), "quantity": str(i % 30 + 1)}
        for i, d in enumerate(season_calendar(season))
    ]


def sample(season="2024-2025"):
    return {
        "farm": "farm",
        "season": season,
        "total_kg": "1000",
        "area_mu": "10",
        "completeness": "STRICT_ELIGIBLE",
    }


def test_rolling_shape_frozen_hyperparameters_and_past_only():
    m = shape.fit_rolling_r7({"farm": curve()})
    assert m["alpha"] == 10
    assert len(m["coefficients"]) == 4
    assert m["training_season"] == "2024-2025"
    assert sum(shape.predict(m, "2025-2026")) == pytest.approx(1)
    with pytest.raises(ValueError):
        shape.fit_rolling_r7({"farm": curve("2025-2026")})


def test_rolling_total_uses_previous_season_only():
    model = total.fit_rolling_r7([sample()])
    assert model["global_yield"] == "100.000000"
    assert (
        total.predict_total(model, "10", "farm", "prior")["predicted_season_total_kg"]
        == "1000.000000"
    )
    with pytest.raises(ValueError):
        total.fit_rolling_r7([sample("2025-2026")])


def test_old_authorizations_remain_frozen():
    with pytest.raises(ValueError):
        shape.fit({"farm": curve()}, "2024-2025", "ridge")
    with pytest.raises(ValueError):
        total.fit([sample()])


def test_rolling_prior_uses_2425_and_preserves_unknown():
    history = curve()
    history[10]["quantity"] = ""
    shares, value = prior_prediction(history, "2024-2025", "2025-2026", "10")
    assert history[10]["quantity"] == ""
    assert len(shares) == len(season_calendar("2025-2026"))
    assert sum(shares) == pytest.approx(1)
    assert value is not None


def test_prediction_cannot_target_training_season():
    model = shape.fit_rolling_r7({"farm": curve()})
    with pytest.raises(ValueError):
        shape.predict(model, "2024-2025")
    assert season_calendar("2025-2026")[0] == date(2025, 7, 1)
