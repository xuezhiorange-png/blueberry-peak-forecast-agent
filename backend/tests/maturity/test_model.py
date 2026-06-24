from __future__ import annotations

from decimal import Decimal

from backend.app.maturity.model import (
    blend_curves,
    fit_shared_curve,
    reconcile_p50_mass,
)


def test_fit_shared_curve_is_non_negative_and_normalized() -> None:
    support_days = tuple(range(-2, 5))
    curve = fit_shared_curve(
        relative_days=(-2, -1, 0, 1, 2),
        shares=(
            Decimal("0.05"),
            Decimal("0.15"),
            Decimal("0.40"),
            Decimal("0.25"),
            Decimal("0.15"),
        ),
        sample_weights=(
            Decimal("1"),
            Decimal("1"),
            Decimal("2"),
            Decimal("1"),
            Decimal("1"),
        ),
        support_days=support_days,
        spline_degree=3,
        spline_knot_count=4,
        ridge_alpha=Decimal("0.1"),
    )

    assert len(curve) == len(support_days)
    assert all(value >= 0 for value in curve)
    assert sum(curve, Decimal("0")).quantize(Decimal("0.000001")) == Decimal("1.000000")


def test_reconcile_p50_mass_preserves_total() -> None:
    density = (
        Decimal("0.1"),
        Decimal("0.2"),
        Decimal("0.3"),
        Decimal("0.4"),
    )

    daily = reconcile_p50_mass(
        expected_total_kg=Decimal("1000"),
        density=density,
    )

    assert daily == (
        Decimal("100.000000"),
        Decimal("200.000000"),
        Decimal("300.000000"),
        Decimal("400.000000"),
    )
    assert sum(daily, Decimal("0")) == Decimal("1000.000000")


def test_blend_curves_uses_parent_for_zero_shrinkage() -> None:
    parent = (Decimal("0.2"), Decimal("0.3"), Decimal("0.5"))
    local = (Decimal("0.4"), Decimal("0.3"), Decimal("0.3"))

    assert blend_curves(parent=parent, local=local, shrinkage=Decimal("0")) == parent
    assert blend_curves(parent=parent, local=local, shrinkage=Decimal("1")) == local
