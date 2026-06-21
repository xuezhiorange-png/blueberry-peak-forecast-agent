from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from backend.app.analytics.config import AnalyticsRules

_KG_QUANT = Decimal("0.000001")
_RATIO_QUANT = Decimal("0.0000000001")


def _quantize_kg(value: Decimal) -> Decimal:
    return value.quantize(_KG_QUANT, rounding=ROUND_HALF_UP)


def _quantize_ratio(value: Decimal) -> Decimal:
    return value.quantize(_RATIO_QUANT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class DailySeriesPoint:
    date: date
    weight_kg: Decimal
    holiday_codes: tuple[str, ...] = ()
    is_spring_festival: bool = False


@dataclass(frozen=True)
class FactoryPeakMetrics:
    analysis_start_date: date
    analysis_end_date: date
    calendar_day_count: int
    observed_day_count: int
    total_weight_kg: Decimal
    single_day_peak_kg: Decimal
    single_day_peak_date: date
    stable_median_3d_peak_kg: Decimal
    stable_median_3d_peak_date: date | None
    mean_3d_peak_kg: Decimal
    mean_3d_peak_date: date | None
    peak_concentration: Decimal
    variety_hhi: Decimal
    farm_hhi: Decimal
    subfarm_hhi: Decimal
    unknown_farm_weight_share: Decimal
    unknown_subfarm_weight_share: Decimal
    spring_festival_day_count: int


def build_analysis_calendar(
    *,
    start_date: date,
    end_date: date,
    analysis_months: Iterable[int],
) -> list[date]:
    allowed_months = set(analysis_months)
    current = start_date
    dates: list[date] = []
    while current <= end_date:
        if current.month in allowed_months:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def build_dense_daily_series(
    *,
    calendar_dates: list[date],
    weight_by_date: dict[date, Decimal],
    holiday_codes_by_date: dict[date, tuple[str, ...]],
    spring_festival_codes: tuple[str, ...],
) -> list[DailySeriesPoint]:
    spring_codes = set(spring_festival_codes)
    series: list[DailySeriesPoint] = []
    for current_date in calendar_dates:
        holiday_codes = tuple(sorted(set(holiday_codes_by_date.get(current_date, ()))))
        series.append(
            DailySeriesPoint(
                date=current_date,
                weight_kg=_quantize_kg(weight_by_date.get(current_date, Decimal("0"))),
                holiday_codes=holiday_codes,
                is_spring_festival=bool(spring_codes.intersection(holiday_codes)),
            )
        )
    return series


def calculate_hhi(weights_by_key: dict[str, Decimal]) -> Decimal:
    total_weight = sum(weights_by_key.values(), Decimal("0"))
    if total_weight <= 0:
        return _quantize_ratio(Decimal("0"))
    hhi = sum(
        (
            (weight / total_weight) * (weight / total_weight)
            for weight in weights_by_key.values()
            if weight > 0
        ),
        Decimal("0"),
    )
    return _quantize_ratio(hhi)


def _earliest_peak(window_values: list[tuple[date, Decimal]]) -> tuple[Decimal, date | None]:
    if not window_values:
        return _quantize_kg(Decimal("0")), None
    peak_value, peak_date = window_values[0][1], window_values[0][0]
    for current_date, current_value in window_values[1:]:
        if current_value > peak_value:
            peak_value = current_value
            peak_date = current_date
    return _quantize_kg(peak_value), peak_date


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def compute_factory_peak_metrics(
    *,
    dense_series: list[DailySeriesPoint],
    rules: AnalyticsRules,
    total_weight_kg: Decimal,
    variety_weights: dict[str, Decimal],
    farm_weights: dict[str, Decimal],
    subfarm_weights: dict[str, Decimal],
) -> FactoryPeakMetrics:
    if not dense_series:
        raise ValueError("dense_series must not be empty")
    if total_weight_kg <= 0:
        raise ValueError("total_weight_kg must be positive")

    total_weight = _quantize_kg(total_weight_kg)
    observed_day_count = sum(1 for point in dense_series if point.weight_kg > 0)
    single_day_peak_kg, single_day_peak_date = _earliest_peak(
        [(point.date, point.weight_kg) for point in dense_series]
    )

    window_radius = rules.rolling_window_radius
    stable_candidates: list[tuple[date, Decimal]] = []
    mean_candidates: list[tuple[date, Decimal]] = []
    for index in range(window_radius, len(dense_series) - window_radius):
        window = dense_series[index - window_radius : index + window_radius + 1]
        values = [point.weight_kg for point in window]
        center_date = dense_series[index].date
        stable_candidates.append((center_date, _quantize_kg(_median(values))))
        mean_candidates.append(
            (
                center_date,
                _quantize_kg(sum(values, Decimal("0")) / Decimal(len(values))),
            )
        )

    stable_peak_kg, stable_peak_date = _earliest_peak(stable_candidates)
    mean_peak_kg, mean_peak_date = _earliest_peak(mean_candidates)
    peak_concentration = _quantize_ratio(stable_peak_kg / total_weight)

    unknown_farm_weight = farm_weights.get(rules.unknown_farm_key, Decimal("0"))
    unknown_subfarm_weight = subfarm_weights.get(rules.unknown_subfarm_key, Decimal("0"))

    return FactoryPeakMetrics(
        analysis_start_date=dense_series[0].date,
        analysis_end_date=dense_series[-1].date,
        calendar_day_count=len(dense_series),
        observed_day_count=observed_day_count,
        total_weight_kg=total_weight,
        single_day_peak_kg=single_day_peak_kg,
        single_day_peak_date=single_day_peak_date or dense_series[0].date,
        stable_median_3d_peak_kg=stable_peak_kg,
        stable_median_3d_peak_date=stable_peak_date,
        mean_3d_peak_kg=mean_peak_kg,
        mean_3d_peak_date=mean_peak_date,
        peak_concentration=peak_concentration,
        variety_hhi=calculate_hhi(variety_weights),
        farm_hhi=calculate_hhi(farm_weights),
        subfarm_hhi=calculate_hhi(subfarm_weights),
        unknown_farm_weight_share=_quantize_ratio(unknown_farm_weight / total_weight),
        unknown_subfarm_weight_share=_quantize_ratio(unknown_subfarm_weight / total_weight),
        spring_festival_day_count=sum(1 for point in dense_series if point.is_spring_festival),
    )
