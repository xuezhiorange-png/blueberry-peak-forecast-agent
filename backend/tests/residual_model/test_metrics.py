from __future__ import annotations

from decimal import Decimal


def test_residual_mae() -> None:
    from backend.app.residual_model.metrics import residual_mae

    value = residual_mae(
        [Decimal("10"), Decimal("20")],
        [Decimal("12"), Decimal("14")],
    )
    assert value == Decimal("4")


def test_wmape_zero_denominator() -> None:
    from backend.app.residual_model.metrics import wmape

    assert wmape([Decimal("0")], [Decimal("1")]) is None


def test_pinball_loss() -> None:
    from backend.app.residual_model.metrics import pinball_loss

    value = pinball_loss(
        [Decimal("10"), Decimal("20")],
        [Decimal("8"), Decimal("22")],
        quantile=Decimal("0.5"),
    )
    assert value == Decimal("1")


def test_empirical_coverage() -> None:
    from backend.app.residual_model.metrics import empirical_coverage

    value = empirical_coverage(
        actuals=[Decimal("10"), Decimal("30")],
        lower=[Decimal("5"), Decimal("25")],
        upper=[Decimal("15"), Decimal("29")],
    )
    assert value == Decimal("0.5")


def test_quantile_crossing_count() -> None:
    from backend.app.residual_model.metrics import quantile_crossing_count

    count = quantile_crossing_count(
        p50=[Decimal("1"), Decimal("5")],
        p80=[Decimal("2"), Decimal("4")],
        p90=[Decimal("3"), Decimal("6")],
    )
    assert count == 1
