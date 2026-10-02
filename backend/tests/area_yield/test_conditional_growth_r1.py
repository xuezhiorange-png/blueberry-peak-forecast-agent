"""Mathematical and isolation tests for the single conditional curve family."""

import json
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from backend.app.area_yield import conditional_growth as cg


def sample(base: str, year: int, values: list[float]) -> dict[str, Any]:
    return {
        "base_id": base,
        "season": f"{year}-{year + 1}",
        "area": 10.0,
        "dates": [(date(year, 7, 1) + timedelta(days=i)).isoformat() for i in range(len(values))],
        "quantities": values,
        "total": sum(values),
    }


def test_basis_identifiability_and_canonical_axis() -> None:
    for n in (4, 6):
        b = cg.basis(np.arange(290), n)
        assert b.shape == (290, n - 1)
        assert np.linalg.matrix_rank(b) == n - 1
        assert np.array_equal(b, cg.basis(np.arange(290), n))
    assert cg.positions(["2025-07-22", "2025-07-23"], "2025-2026").tolist() == [21, 22]


def test_shape_gradient_and_certificate_and_condition_response() -> None:
    b = cg.basis(np.arange(290), 6)
    x = np.array([[-1.0], [1.0]])
    p = [cg.softmax(b @ np.array([3, 2, 0, -2, -3])), cg.softmax(b @ np.array([-3, -2, 0, 2, 3]))]
    objective = cg.shape_objective([b, b], x, p, 0.001)
    theta = np.linspace(-0.1, 0.1, 10)
    value, grad = objective(theta)
    numerical = np.array(
        [
            (
                objective(theta + np.eye(10)[j] * 1e-5)[0]
                - objective(theta - np.eye(10)[j] * 1e-5)[0]
            )
            / 2e-5
            for j in range(10)
        ]
    )
    assert np.allclose(grad, numerical, atol=1e-8)
    fit = cg.solve(objective, 10, 0.001)
    assert fit["accepted"] and fit["gap_bound"] <= cg.GAP_TOL
    assert fit["objective"] < value
    a = cg.shape_predict(fit["theta"], b, x[0])
    z = cg.shape_predict(fit["theta"], b, x[1])
    assert np.argmax(a) != np.argmax(z)
    assert np.abs(a - z).sum() > 0.1
    assert np.isfinite(cg.softmax(np.array([10000.0, -10000.0, 0.0]))).all()


def test_total_zero_beta_parity_and_gradient() -> None:
    x = np.array([[-1.0], [0.0], [1.0]])
    area = np.array([10.0, 20.0, 30.0])
    q = np.array([200.0, 100.0, 600.0])
    objective = cg.total_objective(x, area, q, 0.01)
    beta = np.array([0.2])
    num = (objective(beta + 1e-5)[0] - objective(beta - 1e-5)[0]) / 2e-5
    assert objective(beta)[1][0] == pytest.approx(num, abs=1e-8)
    alpha = cg.total_intercept(np.zeros(1), x, area, q)
    assert np.exp(alpha) == pytest.approx(q.sum() / area.sum(), abs=1e-12)
    with pytest.raises(ValueError):
        cg.total_objective(x, area, np.zeros(3), 0.1)


def test_features_do_not_use_self_or_future_records() -> None:
    train = [sample("b", 2023, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])]
    weather = {"b|2023-2024": [20.0, 21.0, 22.0, 2.0], "b|2024-2025": [999.0] * 4}
    mix = {"b|2023-2024": [0.5, 0.2, 0.1, 0.8], "b|2024-2025": [1.0] * 4}
    context = cg.context(train, weather, mix)
    own, _ = cg.raw_features(train[0], context, "CGHWV")
    assert np.isnan(own[0]) and np.isnan(own[5]) and np.isnan(own[10])
    future = sample("b", 2024, [999.0] * 7)
    first, lineage = cg.raw_features(future, context, "CGHWV")
    changed = {**future, "quantities": [0.0] * 7, "total": 0.0}
    second, _ = cg.raw_features(changed, context, "CGHWV")
    assert np.array_equal(first, second, equal_nan=True)
    assert first[0] == pytest.approx(np.log(2.8))
    assert all(r["source_seasons"] in ("", "2023-2024") for r in lineage)


def test_transform_training_only_and_constants() -> None:
    values = np.array([[1.0, np.nan, 0.0], [3.0, np.nan, 0.0]])
    t = cg.fit_transform(values)
    assert t["active"] == [0]
    assert cg.transform(values, t).shape == (2, 1)
    assert cg.transform(np.array([[100.0, 999.0, 1.0]]), t)[0, 0] == 98.0


def test_quantities_mass_and_rolling_peak() -> None:
    q = cg.quantities(123.456789, cg.softmax(np.arange(14) / 20))
    assert abs(sum(q) - 123.456789) < 1e-9
    s = cg.curve_stats(q)
    assert s["peak7_value"] == pytest.approx(max(sum(q[i : i + 7]) for i in range(8)))
    assert cg.curve_stats([1.0] * 14)["peak_index"] == 0
    assert cg.curve_stats([1.0] * 14)["peak7_index"] == 0


def test_solver_success_is_not_numerical_acceptance(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(*args: Any, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(x=np.zeros(1), success=True, nit=0, message="early exit")

    monkeypatch.setattr(cg, "minimize", fake)

    def objective(a: np.ndarray) -> tuple[float, np.ndarray]:
        return float((a[0] - 2) ** 2), np.array([2 * (a[0] - 2)])

    result = cg.solve(objective, 1, 0.1)
    assert not result["accepted"]
    assert len(result["attempts"]) == 2
    assert all(r["solver_success"] for r in result["attempts"])


def test_artifact_id_invariance_window_normalization_and_positive_total() -> None:
    training = [sample("base_" + "a" * 24, 2023, [1.0] * 14)]
    model, audits, _ = cg.fit_model(
        training,
        {},
        {},
        {"version": "CG0", "basis": 4, "lambda": 0.1},
        {"version": "TY1", "lambda": 0.1},
        [1 / 290] * 290,
        "test",
    )
    r = {
        "base_id": "base_" + "b" * 24,
        "target_season": "2024-2025",
        "target_area_mu": "10",
        "forecast_start_date": "2024-07-22",
        "forecast_end_date": "2024-08-10",
    }
    first = cg.forecast(model, r)
    second = cg.forecast(model, {**r, "base_id": "base_" + "c" * 24})
    assert first["quantities"] == second["quantities"]
    assert sum(first["shares"]) == pytest.approx(1, abs=1e-12)
    assert first["total"] > 0 and first["total"] == pytest.approx(14.0)
    assert all(a["accepted"] for a in audits)
    changed = {**model, "pooled_yield": 999.0}
    with pytest.raises(ValueError, match="INTEGRITY"):
        cg.forecast(changed, r)
    for area in ("0", "-1", "nan", "inf"):
        with pytest.raises(ValueError):
            cg.forecast(model, {**r, "target_area_mu": area})
    with pytest.raises(ValueError):
        cg.forecast(model, {**r, "forecast_start_date": "2023-07-01"})
    loaded = json.loads(json.dumps(model))
    assert cg.forecast(loaded, r) == first
    double = cg.forecast(loaded, {**r, "target_area_mu": "20"})
    assert double["total"] == pytest.approx(2 * first["total"])
    assert np.allclose(double["shares"], first["shares"], atol=1e-14)


def test_legal_zero_total_does_not_create_shape_labels() -> None:
    train = [sample("a", 2023, [0.0] * 14), sample("b", 2023, [1.0] * 14)]
    model, audits, _ = cg.fit_model(
        train,
        {},
        {},
        {"version": "CG0", "basis": 4, "lambda": 0.1},
        {"version": "TY0"},
        [1 / 290] * 290,
        "test",
    )
    assert model["pooled_yield"] == pytest.approx(14 / 20)
    assert all(a["accepted"] for a in audits)
