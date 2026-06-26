from __future__ import annotations

from decimal import Decimal


def residual_mae(actuals: list[Decimal], predictions: list[Decimal]) -> Decimal | None:
    if not actuals:
        return None
    total = sum(
        (abs(actual - predicted) for actual, predicted in zip(actuals, predictions, strict=True)),
        Decimal("0"),
    )
    return total / Decimal(len(actuals))


def wmape(actuals: list[Decimal], predictions: list[Decimal]) -> Decimal | None:
    if not actuals:
        return None
    denominator = sum((abs(actual) for actual in actuals), Decimal("0"))
    if denominator == 0:
        return None
    numerator = sum(
        (abs(actual - predicted) for actual, predicted in zip(actuals, predictions, strict=True)),
        Decimal("0"),
    )
    return numerator / denominator


def pinball_loss(
    actuals: list[Decimal],
    predictions: list[Decimal],
    *,
    quantile: Decimal,
) -> Decimal | None:
    if not actuals:
        return None
    total = Decimal("0")
    for actual, predicted in zip(actuals, predictions, strict=True):
        error = actual - predicted
        total += max(quantile * error, (quantile - Decimal("1")) * error)
    return total / Decimal(len(actuals))


def empirical_coverage(
    *,
    actuals: list[Decimal],
    lower: list[Decimal],
    upper: list[Decimal],
) -> Decimal | None:
    if not actuals:
        return None
    covered = sum(
        1
        for actual, lower_value, upper_value in zip(actuals, lower, upper, strict=True)
        if lower_value <= actual <= upper_value
    )
    return Decimal(covered) / Decimal(len(actuals))


def quantile_crossing_count(
    *,
    p50: list[Decimal],
    p80: list[Decimal],
    p90: list[Decimal],
) -> int:
    return sum(
        1
        for value50, value80, value90 in zip(p50, p80, p90, strict=True)
        if not (value50 <= value80 <= value90)
    )
