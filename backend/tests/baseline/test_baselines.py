from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.app.baseline.baselines import (
    evaluate_previous_season_peak,
    evaluate_volume_previous_concentration,
    previous_season_by_start_date,
)
from backend.app.baseline.schemas import BaselineSample


def _sample(
    *,
    season_id: int,
    season_code: str,
    season_start_date: date,
    factory_id: int,
    peak: str,
    total_weight: str = "1000",
    concentration: str = "0.1000000000",
) -> BaselineSample:
    return BaselineSample(
        season_id=season_id,
        season_code=season_code,
        season_start_date=season_start_date,
        factory_id=factory_id,
        factory_name=f"Factory {factory_id}",
        build_run_id=season_id * 10 + factory_id,
        total_weight_kg=Decimal(total_weight),
        stable_median_3d_peak_kg=Decimal(peak),
        peak_concentration=Decimal(concentration),
        variety_hhi=Decimal("0.5"),
        farm_hhi=Decimal("0.5"),
        subfarm_hhi=Decimal("0.5"),
        single_day_peak_kg=Decimal(peak),
    )


def test_previous_season_is_sorted_by_start_date_not_code() -> None:
    samples = [
        _sample(
            season_id=2,
            season_code="2025-2026",
            season_start_date=date(2026, 1, 1),
            factory_id=1,
            peak="200",
        ),
        _sample(
            season_id=1,
            season_code="2024-2025",
            season_start_date=date(2025, 1, 1),
            factory_id=1,
            peak="100",
        ),
        _sample(
            season_id=3,
            season_code="2030-2031",
            season_start_date=date(2027, 1, 1),
            factory_id=1,
            peak="300",
        ),
    ]
    mapping = previous_season_by_start_date(samples)
    assert mapping["2024-2025"] is None
    assert mapping["2025-2026"] == "2024-2025"
    assert mapping["2030-2031"] == "2025-2026"


def test_previous_season_baseline_does_not_skip_missing_adjacent_factory_metric() -> None:
    samples = [
        _sample(
            season_id=1,
            season_code="2024-2025",
            season_start_date=date(2025, 1, 1),
            factory_id=1,
            peak="100",
        ),
        _sample(
            season_id=2,
            season_code="2025-2026",
            season_start_date=date(2026, 1, 1),
            factory_id=2,
            peak="120",
        ),
        _sample(
            season_id=3,
            season_code="2026-2027",
            season_start_date=date(2027, 1, 1),
            factory_id=1,
            peak="130",
        ),
    ]
    result = evaluate_previous_season_peak(samples)
    target = next(row for row in result if row.target_season_code == "2026-2027")
    assert target.status == "excluded"
    assert target.exclusion_reason == "missing_previous_season_factory_metric"


def test_previous_season_peak_formula_uses_immediate_prior_peak() -> None:
    samples = [
        _sample(
            season_id=1,
            season_code="2024-2025",
            season_start_date=date(2025, 1, 1),
            factory_id=1,
            peak="100",
        ),
        _sample(
            season_id=2,
            season_code="2025-2026",
            season_start_date=date(2026, 1, 1),
            factory_id=1,
            peak="150",
        ),
    ]
    result = evaluate_previous_season_peak(samples)
    target = next(row for row in result if row.target_season_code == "2025-2026")
    assert target.predicted_stable_peak_kg == Decimal("100.000000")


def test_volume_previous_concentration_formula_uses_oracle_total_weight() -> None:
    samples = [
        _sample(
            season_id=1,
            season_code="2024-2025",
            season_start_date=date(2025, 1, 1),
            factory_id=1,
            peak="100",
            concentration="0.2000000000",
        ),
        _sample(
            season_id=2,
            season_code="2025-2026",
            season_start_date=date(2026, 1, 1),
            factory_id=1,
            peak="150",
            total_weight="800",
        ),
    ]
    result = evaluate_volume_previous_concentration(samples)
    target = next(row for row in result if row.target_season_code == "2025-2026")
    assert target.predicted_stable_peak_kg == Decimal("160.000000")
