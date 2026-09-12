import json
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pytest
from sklearn.preprocessing import SplineTransformer

from backend.app.area_yield.spline_r2 import basis, fit, position, predict


def fixture_rows():
    return [
        {
            "scope_id": "scope",
            "season_id": "2024-2025",
            "date": (date(2024, 10, 15) + timedelta(days=i)).isoformat(),
            "area_mu": "736.000000",
            "actual_kg": str(100 + i * i),
            "observation_status": "OBSERVED",
        }
        for i in range(60)
    ]


def test_spline_basis_round_trip_matches_sklearn_and_is_deterministic():
    model = fit(fixture_rows(), date(2024, 12, 13), "scope")
    x = np.array([[position(date.fromisoformat(r["date"]))] for r in fixture_rows()])
    transformer = SplineTransformer(
        n_knots=6, degree=3, include_bias=False, extrapolation="linear", knots="uniform"
    ).fit(x)
    targets = np.array([[x[0, 0] - 0.1], [x[-1, 0] + 0.1], [x[20, 0]]])
    assert np.allclose(
        basis(json.loads(json.dumps(model)), targets[:, 0]),
        transformer.transform(targets),
        rtol=0,
        atol=1e-12,
    )
    assert fit(fixture_rows(), date(2024, 12, 13), "scope") == model


def test_spline_rejects_future_training_label_and_past_prediction():
    with pytest.raises(ValueError, match="cutoff"):
        fit(fixture_rows(), date(2024, 11, 1), "scope")
    model = fit(fixture_rows(), date(2024, 12, 13), "scope")
    with pytest.raises(ValueError, match="cutoff"):
        predict(model, [date(2024, 12, 13)], Decimal("736"), "scope")


@pytest.mark.parametrize("area", ["0", "-1", "NaN", "Infinity"])
def test_spline_area_must_be_positive_finite(area):
    model = fit(fixture_rows(), date(2024, 12, 13), "scope")
    with pytest.raises(ValueError):
        predict(model, [date(2025, 1, 1)], Decimal(area), "scope")


def test_spline_hash_integrity_and_scaling():
    model = fit(fixture_rows(), date(2024, 12, 13), "scope")
    dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(14)]
    values = [predict(model, dates, Decimal(a), "scope") for a in ("368", "736", "1104")]
    for a, b, c in zip(*values, strict=True):
        assert all(v.is_finite() and v >= 0 for v in (a, b, c))
        assert abs(b - a * 2) <= Decimal("0.0000015")
        assert abs(c - b * Decimal("1.5")) <= Decimal("0.00000125")
    model["intercept"] += 1
    with pytest.raises(ValueError, match="integrity"):
        predict(model, dates, Decimal("736"), "scope")
