from __future__ import annotations

from decimal import Decimal


def weighted_quantile(
    values: list[Decimal],
    weights: list[Decimal],
    quantile: Decimal,
) -> Decimal:
    if len(values) != len(weights) or not values:
        raise ValueError("values and weights must be non-empty and aligned")
    if quantile < Decimal("0") or quantile > Decimal("1"):
        raise ValueError("quantile must be between 0 and 1")

    pairs = sorted(zip(values, weights, strict=True), key=lambda item: item[0])
    total_weight = Decimal("0")
    for _, weight in pairs:
        if weight <= 0:
            raise ValueError("weights must be positive")
        total_weight += weight
    threshold = total_weight * quantile
    cumulative = Decimal("0")
    for value, weight in pairs:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return pairs[-1][0]


def widen_interval(
    lower: Decimal,
    upper: Decimal,
    *,
    factor: Decimal,
    floor: Decimal,
    ceiling: Decimal | None,
) -> tuple[Decimal, Decimal]:
    center = (lower + upper) / Decimal("2")
    half_width = ((upper - lower) / Decimal("2")) * factor
    widened_lower = center - half_width
    widened_upper = center + half_width
    return clipped_interval(widened_lower, widened_upper, floor=floor, ceiling=ceiling)


def clipped_interval(
    lower: Decimal,
    upper: Decimal,
    *,
    floor: Decimal,
    ceiling: Decimal | None,
) -> tuple[Decimal, Decimal]:
    clipped_lower = max(lower, floor)
    clipped_upper = upper if ceiling is None else min(upper, ceiling)
    return clipped_lower, clipped_upper
