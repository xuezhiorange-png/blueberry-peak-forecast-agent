from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.app.planning.plan_config import ProductionPlanConfig, ProductionPlanRules
from backend.app.planning.plan_schemas import ProductionPlanValidationError
from backend.app.planning.plan_service import (
    _decimal_value,
    _derived_total,
    _difference_warning,
    _interval_contains,
    _intervals_overlap,
    _validate_dates,
)


def _config(*, behavior: str = "warn") -> ProductionPlanConfig:
    return ProductionPlanConfig(
        rules=ProductionPlanRules(
            version="task6-v1",
            interval_semantics="half_open",
            explicit_total_tolerance_kg=Decimal("1"),
            explicit_total_mismatch_behavior=behavior,  # type: ignore[arg-type]
        ),
        config_hash="cfg",
        snapshot={},
    )


def test_decimal_value_rejects_invalid_decimal_and_nan() -> None:
    with pytest.raises(ProductionPlanValidationError):
        _decimal_value("not-a-number", field="planted_area_mu")

    with pytest.raises(ProductionPlanValidationError):
        _decimal_value("NaN", field="planted_area_mu")

    with pytest.raises(ProductionPlanValidationError):
        _decimal_value("Infinity", field="planted_area_mu")


def test_derived_total_uses_decimal_math() -> None:
    assert _derived_total(
        planted_area_mu=Decimal("100"),
        expected_yield_kg_per_mu=Decimal("1200.5"),
        marketable_rate=Decimal("0.7"),
    ) == Decimal("84035.00")


def test_difference_warning_warns_or_rejects_based_on_config() -> None:
    difference, warnings = _difference_warning(
        explicit_total=Decimal("90"),
        derived_total=Decimal("100"),
        config=_config(),
    )
    assert difference == Decimal("-10")
    assert warnings == ("expected_total_marketable_kg_diff_exceeds_tolerance",)

    with pytest.raises(ProductionPlanValidationError):
        _difference_warning(
            explicit_total=Decimal("90"),
            derived_total=Decimal("100"),
            config=_config(behavior="reject"),
        )


def test_effective_interval_semantics_are_half_open() -> None:
    assert _interval_contains(
        as_of_date=date(2026, 1, 1),
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 2, 1),
    )
    assert not _interval_contains(
        as_of_date=date(2026, 2, 1),
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 2, 1),
    )


def test_interval_overlap_detects_half_open_boundaries() -> None:
    assert not _intervals_overlap(
        start_a=date(2026, 1, 1),
        end_a=date(2026, 2, 1),
        start_b=date(2026, 2, 1),
        end_b=None,
    )
    assert _intervals_overlap(
        start_a=date(2026, 1, 1),
        end_a=None,
        start_b=date(2026, 1, 15),
        end_b=date(2026, 2, 1),
    )


def test_validate_dates_rejects_invalid_flowering_order_and_effective_range() -> None:
    with pytest.raises(ProductionPlanValidationError):
        _validate_dates(
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 1, 1),
            flowering_start_date=None,
            flowering_peak_date=None,
            flowering_end_date=None,
        )

    with pytest.raises(ProductionPlanValidationError):
        _validate_dates(
            effective_from=date(2026, 1, 1),
            effective_to=None,
            flowering_start_date=date(2026, 2, 10),
            flowering_peak_date=date(2026, 2, 9),
            flowering_end_date=date(2026, 2, 20),
        )


def test_difference_warning_within_tolerance_has_no_warning() -> None:
    difference, warnings = _difference_warning(
        explicit_total=Decimal("100.4"),
        derived_total=Decimal("100"),
        config=_config(),
    )
    assert difference == Decimal("0.4")
    assert warnings == ()
