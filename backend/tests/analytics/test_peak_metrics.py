from datetime import date
from decimal import Decimal

from backend.app.analytics.config import AnalyticsRules
from backend.app.analytics.peak_metrics import (
    DailySeriesPoint,
    build_analysis_calendar,
    build_dense_daily_series,
    calculate_hhi,
    compute_factory_peak_metrics,
)


def _rules(*, months: tuple[int, ...] = (1,), window: int = 3) -> AnalyticsRules:
    return AnalyticsRules(
        version="task3-v1",
        analysis_months=months,
        rolling_window_days=window,
        stable_peak_method="median",
        mean_peak_method="mean",
        peak_concentration_definition="stable_median_3d_peak_over_total",
        spring_festival_codes=("spring_festival",),
        unknown_farm_key="__UNKNOWN_FARM__",
        unknown_subfarm_key="__UNKNOWN_SUBFARM__",
        stream_batch_size=5000,
    )


def test_build_analysis_calendar_filters_by_months() -> None:
    dates = build_analysis_calendar(
        start_date=date(2026, 1, 30),
        end_date=date(2026, 2, 2),
        analysis_months=(1,),
    )

    assert dates == [date(2026, 1, 30), date(2026, 1, 31)]


def test_build_dense_daily_series_fills_missing_dates_and_keeps_holiday_labels() -> None:
    calendar = [
        date(2026, 1, 1),
        date(2026, 1, 2),
        date(2026, 1, 3),
        date(2026, 1, 4),
    ]
    dense = build_dense_daily_series(
        calendar_dates=calendar,
        weight_by_date={
            date(2026, 1, 2): Decimal("10"),
            date(2026, 1, 4): Decimal("20"),
        },
        holiday_codes_by_date={date(2026, 1, 3): ("spring_festival",)},
        spring_festival_codes=("spring_festival",),
    )

    assert [point.weight_kg for point in dense] == [
        Decimal("0"),
        Decimal("10"),
        Decimal("0"),
        Decimal("20"),
    ]
    assert len(dense) == 4
    assert dense[2].holiday_codes == ("spring_festival",)
    assert dense[2].is_spring_festival is True


def test_peak_metrics_compute_single_day_stable_and_mean_peaks() -> None:
    dense = [
        DailySeriesPoint(date=date(2026, 1, 1), weight_kg=Decimal("0")),
        DailySeriesPoint(date=date(2026, 1, 2), weight_kg=Decimal("10")),
        DailySeriesPoint(date=date(2026, 1, 3), weight_kg=Decimal("30")),
        DailySeriesPoint(date=date(2026, 1, 4), weight_kg=Decimal("20")),
        DailySeriesPoint(date=date(2026, 1, 5), weight_kg=Decimal("0")),
    ]

    metrics = compute_factory_peak_metrics(
        dense_series=dense,
        rules=_rules(),
        total_weight_kg=Decimal("60"),
        variety_weights={"Dx": Decimal("60")},
        farm_weights={"FarmA": Decimal("60")},
        subfarm_weights={"SubfarmA": Decimal("60")},
    )

    assert metrics.single_day_peak_kg == Decimal("30.000000")
    assert metrics.single_day_peak_date == date(2026, 1, 3)
    assert metrics.stable_median_3d_peak_kg == Decimal("20.000000")
    assert metrics.stable_median_3d_peak_date == date(2026, 1, 3)
    assert metrics.mean_3d_peak_kg == Decimal("20.000000")
    assert metrics.mean_3d_peak_date == date(2026, 1, 3)
    assert metrics.calendar_day_count == 5
    assert metrics.observed_day_count == 3


def test_peak_metrics_choose_earliest_date_for_tied_peaks() -> None:
    dense = [
        DailySeriesPoint(date=date(2026, 1, 1), weight_kg=Decimal("10")),
        DailySeriesPoint(date=date(2026, 1, 2), weight_kg=Decimal("10")),
        DailySeriesPoint(date=date(2026, 1, 3), weight_kg=Decimal("10")),
        DailySeriesPoint(date=date(2026, 1, 4), weight_kg=Decimal("10")),
        DailySeriesPoint(date=date(2026, 1, 5), weight_kg=Decimal("10")),
    ]

    metrics = compute_factory_peak_metrics(
        dense_series=dense,
        rules=_rules(),
        total_weight_kg=Decimal("90"),
        variety_weights={"Dx": Decimal("90")},
        farm_weights={"FarmA": Decimal("90")},
        subfarm_weights={"SubfarmA": Decimal("90")},
    )

    assert metrics.single_day_peak_date == date(2026, 1, 1)
    assert metrics.stable_median_3d_peak_date == date(2026, 1, 2)
    assert metrics.mean_3d_peak_date == date(2026, 1, 2)


def test_peak_metrics_do_not_use_incomplete_edge_windows() -> None:
    dense = [
        DailySeriesPoint(date=date(2026, 1, 1), weight_kg=Decimal("100")),
        DailySeriesPoint(date=date(2026, 1, 2), weight_kg=Decimal("0")),
        DailySeriesPoint(date=date(2026, 1, 3), weight_kg=Decimal("0")),
    ]

    metrics = compute_factory_peak_metrics(
        dense_series=dense,
        rules=_rules(),
        total_weight_kg=Decimal("100"),
        variety_weights={"Dx": Decimal("100")},
        farm_weights={"FarmA": Decimal("100")},
        subfarm_weights={"SubfarmA": Decimal("100")},
    )

    assert metrics.single_day_peak_date == date(2026, 1, 1)
    assert metrics.stable_median_3d_peak_date == date(2026, 1, 2)
    assert metrics.stable_median_3d_peak_kg == Decimal("0.000000")
    assert metrics.mean_3d_peak_date == date(2026, 1, 2)
    assert metrics.mean_3d_peak_kg == Decimal("33.333333")


def test_peak_metrics_do_not_use_non_consecutive_three_day_windows() -> None:
    dense = [
        DailySeriesPoint(date=date(2026, 1, 31), weight_kg=Decimal("10")),
        DailySeriesPoint(date=date(2026, 3, 1), weight_kg=Decimal("99")),
        DailySeriesPoint(date=date(2026, 3, 2), weight_kg=Decimal("10")),
    ]

    metrics = compute_factory_peak_metrics(
        dense_series=dense,
        rules=_rules(),
        total_weight_kg=Decimal("119"),
        variety_weights={"Dx": Decimal("119")},
        farm_weights={"FarmA": Decimal("119")},
        subfarm_weights={"SubfarmA": Decimal("119")},
    )

    assert metrics.single_day_peak_date == date(2026, 3, 1)
    assert metrics.stable_median_3d_peak_date is None
    assert metrics.stable_median_3d_peak_kg == Decimal("0.000000")
    assert metrics.mean_3d_peak_date is None
    assert metrics.mean_3d_peak_kg == Decimal("0.000000")


def test_peak_metrics_allow_month_boundary_consecutive_windows() -> None:
    dense = [
        DailySeriesPoint(date=date(2026, 1, 31), weight_kg=Decimal("10")),
        DailySeriesPoint(date=date(2026, 2, 1), weight_kg=Decimal("30")),
        DailySeriesPoint(date=date(2026, 2, 2), weight_kg=Decimal("20")),
    ]

    metrics = compute_factory_peak_metrics(
        dense_series=dense,
        rules=_rules(),
        total_weight_kg=Decimal("60"),
        variety_weights={"Dx": Decimal("60")},
        farm_weights={"FarmA": Decimal("60")},
        subfarm_weights={"SubfarmA": Decimal("60")},
    )

    assert metrics.stable_median_3d_peak_date == date(2026, 2, 1)
    assert metrics.stable_median_3d_peak_kg == Decimal("20.000000")
    assert metrics.mean_3d_peak_date == date(2026, 2, 1)
    assert metrics.mean_3d_peak_kg == Decimal("20.000000")


def test_stable_and_mean_peak_dates_can_differ() -> None:
    dense = [
        DailySeriesPoint(date=date(2026, 1, 1), weight_kg=Decimal("100")),
        DailySeriesPoint(date=date(2026, 1, 2), weight_kg=Decimal("1")),
        DailySeriesPoint(date=date(2026, 1, 3), weight_kg=Decimal("100")),
        DailySeriesPoint(date=date(2026, 1, 4), weight_kg=Decimal("60")),
        DailySeriesPoint(date=date(2026, 1, 5), weight_kg=Decimal("60")),
    ]

    metrics = compute_factory_peak_metrics(
        dense_series=dense,
        rules=_rules(),
        total_weight_kg=Decimal("321"),
        variety_weights={"Dx": Decimal("321")},
        farm_weights={"FarmA": Decimal("321")},
        subfarm_weights={"SubfarmA": Decimal("321")},
    )

    assert metrics.stable_median_3d_peak_date == date(2026, 1, 2)
    assert metrics.stable_median_3d_peak_kg == Decimal("100.000000")
    assert metrics.mean_3d_peak_date == date(2026, 1, 4)
    assert metrics.mean_3d_peak_kg == Decimal("73.333333")


def test_hhi_and_unknown_weight_shares_use_decimal_precision() -> None:
    assert calculate_hhi({"only": Decimal("10")}) == Decimal("1.0000000000")
    assert calculate_hhi({"a": Decimal("5"), "b": Decimal("5")}) == Decimal("0.5000000000")
    assert calculate_hhi({"a": Decimal("50"), "b": Decimal("25"), "c": Decimal("25")}) == Decimal(
        "0.3750000000"
    )

    dense = [
        DailySeriesPoint(date=date(2026, 1, 1), weight_kg=Decimal("1")),
        DailySeriesPoint(date=date(2026, 1, 2), weight_kg=Decimal("2")),
        DailySeriesPoint(date=date(2026, 1, 3), weight_kg=Decimal("2")),
    ]
    metrics = compute_factory_peak_metrics(
        dense_series=dense,
        rules=_rules(),
        total_weight_kg=Decimal("5"),
        variety_weights={"Dx": Decimal("5")},
        farm_weights={"__UNKNOWN_FARM__": Decimal("2"), "FarmA": Decimal("3")},
        subfarm_weights={"__UNKNOWN_SUBFARM__": Decimal("1"), "SubfarmA": Decimal("4")},
    )

    assert metrics.unknown_farm_weight_share == Decimal("0.4000000000")
    assert metrics.unknown_subfarm_weight_share == Decimal("0.2000000000")
