from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.planning.quantiles import (
    clipped_interval,
    weighted_quantile,
    widen_interval,
)


def test_weighted_quantile_returns_expected_p10_p50_p90() -> None:
    values = [Decimal("10"), Decimal("20"), Decimal("30")]
    weights = [Decimal("1"), Decimal("2"), Decimal("1")]

    assert weighted_quantile(values, weights, Decimal("0.10")) == Decimal("10")
    assert weighted_quantile(values, weights, Decimal("0.50")) == Decimal("20")
    assert weighted_quantile(values, weights, Decimal("0.90")) == Decimal("30")


def test_widen_interval_expands_around_center_deterministically() -> None:
    lower, upper = widen_interval(
        Decimal("10"),
        Decimal("30"),
        factor=Decimal("1.50"),
        floor=Decimal("0"),
        ceiling=None,
    )

    assert lower == Decimal("5.0")
    assert upper == Decimal("35.0")


@pytest.mark.parametrize(
    ("lower", "upper", "floor", "ceiling", "expected"),
    [
        (Decimal("-0.2"), Decimal("1.2"), Decimal("0"), Decimal("1"), (Decimal("0"), Decimal("1"))),
        (Decimal("-5"), Decimal("12"), Decimal("0"), None, (Decimal("0"), Decimal("12"))),
    ],
)
def test_clipped_interval_applies_rate_and_non_negative_bounds(
    lower: Decimal,
    upper: Decimal,
    floor: Decimal,
    ceiling: Decimal | None,
    expected: tuple[Decimal, Decimal],
) -> None:
    assert clipped_interval(lower, upper, floor=floor, ceiling=ceiling) == expected


def test_weighted_quantile_rejects_non_positive_weights() -> None:
    with pytest.raises(ValueError):
        weighted_quantile([Decimal("1")], [Decimal("0")], Decimal("0.50"))

