"""R2 role separation and independent conditional-total regression tests."""

import json
from typing import Any

import numpy as np
import pytest

from backend.app.area_yield import conditional_growth as old
from backend.app.area_yield import conditional_growth_r2 as model
from backend.tests.area_yield.test_conditional_growth_r1 import sample


def fixture() -> tuple[list[dict[str, Any]], dict[str, list[float]]]:
    rows = [sample("a", 2023, [1.0] * 14), sample("b", 2023, [4.0] * 14)]
    return rows, {"a|2023-2024": [10.0, 12.0, 14.0, 2.0], "b|2023-2024": [20.0, 22.0, 24.0, 3.0]}


def test_fixed_reference_estimable_in_first_season_and_future_blocked() -> None:
    rows, weather = fixture()
    reference = model.weather_reference(weather, ["2023-2024"])
    assert reference == model.weather_reference(
        {**weather, "a|2024-2025": [999.0] * 4}, ["2023-2024"]
    )
    p, _ = model.prepare(rows, rows, reference, {}, "CGHWV")
    assert p["group_status"]["W"]["varying_dimensions"] > 0
    assert p["group_status"]["H"]["rank"] == 0
    assert p["group_status"]["V"]["rank"] == 0


def test_heldout_base_past_context_not_heldout_target() -> None:
    past = sample("held", 2023, [1.0] * 14)
    target = sample("held", 2024, [1000.0] * 14)
    ctx = old.context([past], {}, {"held|2023-2024": [0.0, 0.5, 0.5, 1.0]})
    first, _ = model.raw_features(target, ctx, {}, "CGHWV")
    second, _ = model.raw_features(
        {**target, "total": 0.0, "quantities": [0.0] * 14}, ctx, {}, "CGHWV"
    )
    assert np.array_equal(first, second, equal_nan=True)
    assert first[0] == pytest.approx(np.log(1.4))


def test_m0_shape_does_not_empty_total_matrix() -> None:
    rows, weather = fixture()
    fitted, audits, _ = model.fit_model(
        rows,
        rows,
        model.weather_reference(weather, ["2023-2024"]),
        {},
        {"version": "M0"},
        {"version": "TY1", "lambda": 0.01},
        [1 / 290] * 290,
        "contract",
    )
    assert fitted["shape_transform"]["active"] == []
    assert fitted["total_transform"]["active"]
    assert len(fitted["total"]["beta"]) > 0
    assert all(a["accepted"] for a in audits)
    request = {
        "base_id": "a",
        "target_season": "2024-2025",
        "target_area_mu": "10",
        "forecast_start_date": "2024-07-01",
        "forecast_end_date": "2024-07-14",
    }
    output = model.forecast(fitted, request)
    assert output == model.forecast(json.loads(json.dumps(fitted)), request)
    assert abs(sum(output["quantities"]) - output["total"]) < 1e-6
    with pytest.raises(ValueError, match="INTEGRITY"):
        model.forecast({**fitted, "pooled_yield": 5}, request)
