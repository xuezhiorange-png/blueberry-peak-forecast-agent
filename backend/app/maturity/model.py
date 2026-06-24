from __future__ import annotations

from decimal import Decimal

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import SplineTransformer


def _to_decimal(value: float) -> Decimal:
    return Decimal(f"{value:.6f}")


def fit_shared_curve(
    *,
    relative_days: tuple[int, ...],
    shares: tuple[Decimal, ...],
    sample_weights: tuple[Decimal, ...],
    support_days: tuple[int, ...],
    spline_degree: int,
    spline_knot_count: int,
    ridge_alpha: Decimal,
) -> tuple[Decimal, ...]:
    if not relative_days:
        raise ValueError("relative_days must not be empty")
    x = np.asarray(relative_days, dtype=float).reshape(-1, 1)
    y = np.asarray([float(value) for value in shares], dtype=float)
    weights = np.asarray([float(value) for value in sample_weights], dtype=float)
    knots = min(spline_knot_count, len(relative_days))
    spline = SplineTransformer(
        n_knots=max(knots, spline_degree + 1),
        degree=spline_degree,
        include_bias=False,
        extrapolation="constant",
    )
    x_basis = spline.fit_transform(x)
    model = Ridge(alpha=float(ridge_alpha), fit_intercept=True, random_state=0)
    model.fit(x_basis, y, sample_weight=weights)
    support_basis = spline.transform(np.asarray(support_days, dtype=float).reshape(-1, 1))
    predicted = model.predict(support_basis)
    predicted = np.clip(predicted, 0.0, None)
    if float(predicted.sum()) <= 0:
        raise ValueError("curve prediction collapsed to zero mass")
    normalized = predicted / predicted.sum()
    decimals = [_to_decimal(value) for value in normalized.tolist()]
    difference = Decimal("1.000000") - sum(decimals, Decimal("0"))
    decimals[-1] += difference
    return tuple(decimals)


def blend_curves(
    *,
    parent: tuple[Decimal, ...],
    local: tuple[Decimal, ...],
    shrinkage: Decimal,
) -> tuple[Decimal, ...]:
    if len(parent) != len(local):
        raise ValueError("parent and local curves must have the same support length")
    mixed = [
        (Decimal("1") - shrinkage) * parent_value + shrinkage * local_value
        for parent_value, local_value in zip(parent, local, strict=True)
    ]
    total = sum(mixed, Decimal("0"))
    if total <= 0:
        raise ValueError("blended curve mass must be positive")
    normalized = [
        (value / total).quantize(Decimal("0.000001"))
        for value in mixed
    ]
    difference = Decimal("1.000000") - sum(normalized, Decimal("0"))
    if normalized:
        normalized[-1] += difference
    return tuple(normalized)


def reconcile_p50_mass(
    *,
    expected_total_kg: Decimal,
    density: tuple[Decimal, ...],
) -> tuple[Decimal, ...]:
    daily = [(expected_total_kg * item).quantize(Decimal("0.000001")) for item in density]
    difference = expected_total_kg.quantize(Decimal("0.000001")) - sum(daily, Decimal("0"))
    if daily:
        daily[-1] += difference
    return tuple(daily)
