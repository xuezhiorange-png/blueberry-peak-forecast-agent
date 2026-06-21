from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.app.baseline.config import (
    BaselineConfig,
    BaselineRules,
    EvaluationRules,
    RidgeRules,
)
from backend.app.baseline.ridge import (
    RIDGE_FEATURES,
    evaluate_ridge_factory_holdout,
    evaluate_ridge_loso,
)
from backend.app.baseline.schemas import BaselineSample


def _config(*, minimum_training_rows: int = 2) -> BaselineConfig:
    return BaselineConfig(
        rules=BaselineRules(
            version="task4-baseline-v1",
            target="stable_median_3d_peak_kg",
            ridge=RidgeRules(alpha=1.0, fit_intercept=True, features=RIDGE_FEATURES),
            evaluation=EvaluationRules(
                primary_scheme="leave_one_season_out",
                minimum_training_rows=minimum_training_rows,
                mape_zero_policy="exclude",
                unit="kg",
            ),
            random_seed=20260621,
        ),
        config_hash="cfg",
        snapshot={"version": "task4-baseline-v1"},
    )


def _sample(
    *,
    season_id: int,
    season_code: str,
    season_start_date: date,
    factory_id: int,
    total_weight: str,
    peak: str,
    variety_hhi: str = "0.10",
    farm_hhi: str = "0.20",
    subfarm_hhi: str = "0.30",
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
        peak_concentration=Decimal("0.10"),
        variety_hhi=Decimal(variety_hhi),
        farm_hhi=Decimal(farm_hhi),
        subfarm_hhi=Decimal(subfarm_hhi),
        single_day_peak_kg=Decimal(peak),
    )


def test_ridge_feature_list_is_exact_and_excludes_peak_concentration() -> None:
    assert RIDGE_FEATURES == (
        "total_weight_kg",
        "variety_hhi",
        "farm_hhi",
        "subfarm_hhi",
    )
    assert "peak_concentration" not in RIDGE_FEATURES


def test_ridge_loso_training_excludes_target_season_and_scaler_fits_train_only() -> None:
    config = _config()
    samples = [
        _sample(
            season_id=1,
            season_code="2024-2025",
            season_start_date=date(2025, 1, 1),
            factory_id=1,
            total_weight="10",
            peak="10",
        ),
        _sample(
            season_id=1,
            season_code="2024-2025",
            season_start_date=date(2025, 1, 1),
            factory_id=2,
            total_weight="20",
            peak="20",
        ),
        _sample(
            season_id=2,
            season_code="2025-2026",
            season_start_date=date(2026, 1, 1),
            factory_id=1,
            total_weight="30",
            peak="30",
        ),
        _sample(
            season_id=2,
            season_code="2025-2026",
            season_start_date=date(2026, 1, 1),
            factory_id=2,
            total_weight="40",
            peak="40",
        ),
        _sample(
            season_id=3,
            season_code="2026-2027",
            season_start_date=date(2027, 1, 1),
            factory_id=1,
            total_weight="50",
            peak="50",
        ),
    ]
    results = evaluate_ridge_loso(samples, config)
    target = next(row for row in results if row.target_season_code == "2026-2027")
    assert target.status == "evaluated"
    assert "2026-2027" not in target.training_season_codes
    assert target.model_metadata["scaler_mean"][0] == 25.0


def test_ridge_factory_holdout_training_excludes_target_factory() -> None:
    config = _config()
    samples = [
        _sample(
            season_id=1,
            season_code="2024-2025",
            season_start_date=date(2025, 1, 1),
            factory_id=1,
            total_weight="10",
            peak="10",
        ),
        _sample(
            season_id=2,
            season_code="2025-2026",
            season_start_date=date(2026, 1, 1),
            factory_id=1,
            total_weight="20",
            peak="20",
        ),
        _sample(
            season_id=1,
            season_code="2024-2025",
            season_start_date=date(2025, 1, 1),
            factory_id=2,
            total_weight="30",
            peak="30",
        ),
        _sample(
            season_id=2,
            season_code="2025-2026",
            season_start_date=date(2026, 1, 1),
            factory_id=2,
            total_weight="40",
            peak="40",
        ),
        _sample(
            season_id=3,
            season_code="2026-2027",
            season_start_date=date(2027, 1, 1),
            factory_id=2,
            total_weight="50",
            peak="50",
        ),
    ]
    results = evaluate_ridge_factory_holdout(samples, config)
    target = next(row for row in results if row.factory_id == 1)
    assert target.status == "evaluated"
    assert "2024-2025" in target.training_season_codes


def test_ridge_excludes_when_training_rows_are_insufficient() -> None:
    config = _config(minimum_training_rows=4)
    samples = [
        _sample(
            season_id=1,
            season_code="2024-2025",
            season_start_date=date(2025, 1, 1),
            factory_id=1,
            total_weight="10",
            peak="10",
        ),
        _sample(
            season_id=2,
            season_code="2025-2026",
            season_start_date=date(2026, 1, 1),
            factory_id=1,
            total_weight="20",
            peak="20",
        ),
        _sample(
            season_id=3,
            season_code="2026-2027",
            season_start_date=date(2027, 1, 1),
            factory_id=1,
            total_weight="30",
            peak="30",
        ),
    ]
    results = evaluate_ridge_loso(samples, config)
    assert all(row.status == "excluded" for row in results)
    assert all(row.exclusion_reason == "insufficient_training_rows" for row in results)


def test_ridge_results_are_reproducible_for_same_input() -> None:
    config = _config()
    samples = [
        _sample(
            season_id=1,
            season_code="2024-2025",
            season_start_date=date(2025, 1, 1),
            factory_id=1,
            total_weight="10",
            peak="10",
        ),
        _sample(
            season_id=1,
            season_code="2024-2025",
            season_start_date=date(2025, 1, 1),
            factory_id=2,
            total_weight="20",
            peak="20",
        ),
        _sample(
            season_id=2,
            season_code="2025-2026",
            season_start_date=date(2026, 1, 1),
            factory_id=1,
            total_weight="30",
            peak="30",
        ),
        _sample(
            season_id=2,
            season_code="2025-2026",
            season_start_date=date(2026, 1, 1),
            factory_id=2,
            total_weight="40",
            peak="40",
        ),
        _sample(
            season_id=3,
            season_code="2026-2027",
            season_start_date=date(2027, 1, 1),
            factory_id=1,
            total_weight="50",
            peak="50",
        ),
    ]
    first = evaluate_ridge_loso(samples, config)
    second = evaluate_ridge_loso(samples, config)
    assert [row.predicted_stable_peak_kg for row in first] == [
        row.predicted_stable_peak_kg for row in second
    ]
