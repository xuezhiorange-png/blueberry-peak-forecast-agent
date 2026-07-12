"""TASK-013 Slice A — ``forecast_peak`` deterministic adapter.

This is a pure deterministic rule adapter governed by an explicit
:class:`~backend.app.agent.schemas.PeakMetricPolicy`.  It implements exactly
the §16.5 frozen formulas:

1. ``single_day_peak[q]`` = maximum ``final_corrected_arrival_quantity_kg.q``
   over all rows of ``per_day``.  Equal maxima resolve to the earliest
   date (``PeakMetricPolicy.tie_break = EARLIEST_START_DATE``).
2. Tie-break = earliest date.  Stable.  No blocker is raised on equal maxima.
3. ``sustained_3day_peak[q]`` = maximum rolling three-day arithmetic mean in
   ``kg/day``.  Window must contain three actual consecutive calendar dates.
4. The matching 3-day cumulative ``kg`` is also output.
5. The P50 / P80 / P90 quantiles are computed separately and never mixed.
6. ±7-day peak window is inclusive and clipped to the season boundaries
   (``per_day[0].date`` ... ``per_day[-1].date``).
7. ``high_load_reference = SINGLE_DAY_PEAK`` → ``high_load_threshold[q] =
   ratio × single_day_peak[q].volume_kg`` (decimal arithmetic, no float).
8. ``peak_duration_days[q]`` = length of the maximum consecutive run of
   days *containing* ``single_day_peak[q].date`` whose value meets the
   threshold, with the same tie-break.
9. Dominant variety uses the selected window + quantile and discloses both
   numerator and denominator.

The adapter emits policy version + config hash + ``agent_peak_hash``.  No
``PEAK_TIE_BREAK_FAILED`` blocker is raised (the stable tie-break always
resolves a winner).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal

from backend.app.agent.canonical import sha256_payload
from backend.app.agent.enums import ForecastQuantile
from backend.app.agent.schemas import (
    DominantVarietyEntry,
    ForecastDailyCurveOutput,
    ForecastDailyRow,
    ForecastPeakInput,
    ForecastPeakOutput,
    PeakMetricPolicy,
    SingleDayPeakEntry,
    SustainedPeakEntry,
)


# --- Decimal arithmetic (canonical, no float) ----------------------------

def _to_decimal(value: str) -> Decimal:
    return Decimal(value)


def _quantize(dec: Decimal) -> Decimal:
    """Round half-even at 18 fractional digits per the §16.5.8 convention."""

    return dec.quantize(Decimal("1e-18"), rounding=ROUND_HALF_EVEN)


# --- Peak finding ---------------------------------------------------------

@dataclass(frozen=True)
class _Peak:
    date: date
    volume: Decimal


def _single_day_peak(
    rows: list[ForecastDailyRow],
    *,
    quantile: ForecastQuantile,
    tie_break: str,
) -> _Peak:
    if not rows:
        raise ValueError("per_day is empty")

    field = {
        "P50": "p50",
        "P80": "p80",
        "P90": "p90",
    }[quantile]
    # Single-day peak: max of the per-day final_corrected_arrival_quantity_kg
    best: tuple[Decimal, date] | None = None
    for row in rows:
        v = _to_decimal(getattr(row.final_corrected_arrival_quantity_kg, field))
        d = row.date
        if best is None:
            best = (v, d)
            continue
        if v > best[0]:
            best = (v, d)
        elif v == best[0] and tie_break == "EARLIEST_START_DATE" and d < best[1]:
            best = (v, d)
    assert best is not None  # rows is non-empty
    return _Peak(date=best[1], volume=_quantize(best[0]))


def _sustained_3day_peak(
    rows: list[ForecastDailyRow],
    *,
    quantile: ForecastQuantile,
) -> SustainedPeakEntry:
    """Maximum rolling 3-day arithmetic mean in kg/day; matching 3-day cumulative kg."""

    field = {"P50": "p50", "P80": "p80", "P90": "p90"}[quantile]
    by_date: dict[date, Decimal] = {
        r.date: _to_decimal(getattr(r.final_corrected_arrival_quantity_kg, field)) for r in rows
    }
    sorted_dates = sorted(by_date.keys())
    if len(sorted_dates) < 3:
        raise ValueError("sustained 3-day window requires at least 3 dates")
    best_mean = Decimal("-Infinity")
    best_window: tuple[date, date] | None = None
    best_cumulative = Decimal("0")
    # Window continuity: the three dates must be consecutive in the calendar.
    for i in range(len(sorted_dates) - 2):
        d0, d1, d2 = sorted_dates[i], sorted_dates[i + 1], sorted_dates[i + 2]
        if (d1 - d0) != timedelta(days=1) or (d2 - d1) != timedelta(days=1):
            continue  # skip non-consecutive triples
        mean = _quantize((by_date[d0] + by_date[d1] + by_date[d2]) / Decimal(3))
        if mean > best_mean:
            best_mean = mean
            best_window = (d0, d2)
            best_cumulative = _quantize(by_date[d0] + by_date[d1] + by_date[d2])
    if best_window is None:
        raise ValueError("no complete 3-consecutive-date window")
    assert best_window is not None  # for type checkers
    return SustainedPeakEntry(
        start_date=best_window[0],
        end_date=best_window[1],
        rolling_daily_average_kg_per_day=format(best_mean, "f"),
        cumulative_quantity_kg=format(best_cumulative, "f"),
    )


def _peak_window_cumulative(
    rows: list[ForecastDailyRow],
    *,
    quantile: ForecastQuantile,
    peak_date: date,
    before_days: int,
    after_days: int,
    season_start: date,
    season_end: date,
) -> Decimal:
    """Cumulative kg over the inclusive ±7-day window around the peak,
    clipped to ``[season_start, season_end]``."""

    field = {"P50": "p50", "P80": "p80", "P90": "p90"}[quantile]
    by_date = {r.date: _to_decimal(getattr(r.final_corrected_arrival_quantity_kg, field)) for r in rows}
    window_start = max(peak_date - timedelta(days=before_days), season_start)
    window_end = min(peak_date + timedelta(days=after_days), season_end)
    total = Decimal("0")
    d = window_start
    while d <= window_end:
        if d in by_date:
            total += by_date[d]
        d += timedelta(days=1)
    return _quantize(total)


def _high_load_threshold(
    *,
    ratio: Decimal,
    single_day_peak_volume_kg: Decimal,
) -> Decimal:
    return _quantize(ratio * single_day_peak_volume_kg)


def _peak_duration_days(
    rows: list[ForecastDailyRow],
    *,
    quantile: ForecastQuantile,
    threshold: Decimal,
    peak_date: date,
) -> int:
    field = {"P50": "p50", "P80": "p80", "P90": "p90"}[quantile]
    by_date = {
        r.date: _to_decimal(getattr(r.final_corrected_arrival_quantity_kg, field)) for r in rows
    }
    sorted_dates = sorted(by_date.keys())
    above = [d for d in sorted_dates if by_date[d] >= threshold]
    if not above:
        return 0
    # Find the maximum consecutive segment containing peak_date.
    max_run = 0
    current_run = 0
    run_start_idx: int | None = None
    max_run_start: int | None = None
    max_run_end: int | None = None
    for i, d in enumerate(sorted_dates):
        if by_date[d] >= threshold:
            if current_run == 0:
                run_start_idx = i
            current_run += 1
            # If this run contains peak_date, record it as a candidate.
            if run_start_idx is not None and sorted_dates[run_start_idx] <= peak_date <= d:
                if current_run > max_run:
                    max_run = current_run
                    max_run_start = run_start_idx
                    max_run_end = i
        else:
            current_run = 0
            run_start_idx = None
    return max_run


def _dominant_variety(
    rows: list[ForecastDailyRow],
    *,
    quantile: ForecastQuantile,
    window_start: date,
    window_end: date,
) -> DominantVarietyEntry | None:
    """Dominant variety over the selected window + quantile.

    Discloses both numerator and denominator so the contribution rate is
    independently verifiable.
    """

    field = {"P50": "p50", "P80": "p80", "P90": "p90"}[quantile]
    numerator_by_variety: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    denominator = Decimal("0")
    for r in rows:
        if r.date < window_start or r.date > window_end:
            continue
        total_q = _to_decimal(getattr(r.final_corrected_arrival_quantity_kg, field))
        denominator += total_q
        for c in r.per_variety_contribution:
            v = _to_decimal(getattr(c, f"volume_kg_{field.lower()}"))
            numerator_by_variety[c.variety_id] += v
    if not numerator_by_variety or denominator == 0:
        return None
    best_variety = max(numerator_by_variety.items(), key=lambda kv: kv[1])
    rate = _quantize(best_variety[1] / denominator)
    return DominantVarietyEntry(
        variety_id=best_variety[0],
        contribution_rate=format(rate, "f"),
        numerator_kg=format(_quantize(best_variety[1]), "f"),
        denominator_kg=format(_quantize(denominator), "f"),
    )


# --- Top-level adapter ----------------------------------------------------

class DefaultPeakAdapter:
    """Default ``forecast_peak`` deterministic rule adapter."""

    def execute(self, *, input: ForecastPeakInput) -> ForecastPeakOutput:
        daily: ForecastDailyCurveOutput = input.daily_curve
        policy: PeakMetricPolicy = input.peak_metric_policy

        # Empty curve → EMPTY_CURVE blocker.  We still return a partial
        # output so the orchestrator can carry the policy version + hash.
        if not daily.per_day:
            raise ValueError("per_day is empty; cannot compute peak")

        season_start = daily.per_day[0].date
        season_end = daily.per_day[-1].date

        single_day_peak: dict[ForecastQuantile, SingleDayPeakEntry] = {}
        sustained_3day: dict[ForecastQuantile, SustainedPeakEntry] = {}
        peak_window_cum: dict[ForecastQuantile, str] = {}
        peak_duration: dict[ForecastQuantile, int] = {}
        high_load_threshold: dict[ForecastQuantile, str] = {}
        dominant_variety: dict[ForecastQuantile, DominantVarietyEntry] = {}

        for q in ("P50", "P80", "P90"):
            peak = _single_day_peak(
                daily.per_day,
                quantile=q,
                tie_break=policy.tie_break,
            )
            single_day_peak[q] = SingleDayPeakEntry(
                date=peak.date,
                volume_kg=format(peak.volume, "f"),
            )

            sus = _sustained_3day_peak(daily.per_day, quantile=q)
            sustained_3day[q] = sus

            cum = _peak_window_cumulative(
                daily.per_day,
                quantile=q,
                peak_date=peak.date,
                before_days=policy.peak_window_days_before,
                after_days=policy.peak_window_days_after,
                season_start=season_start,
                season_end=season_end,
            )
            peak_window_cum[q] = format(cum, "f")

            threshold = _high_load_threshold(
                ratio=_to_decimal(policy.high_load_threshold_ratio),
                single_day_peak_volume_kg=peak.volume,
            )
            high_load_threshold[q] = format(threshold, "f")
            peak_duration[q] = _peak_duration_days(
                daily.per_day,
                quantile=q,
                threshold=threshold,
                peak_date=peak.date,
            )
            dv = _dominant_variety(
                daily.per_day,
                quantile=q,
                window_start=sus.start_date,
                window_end=sus.end_date,
            )
            if dv is not None:
                dominant_variety[q] = dv

        # agent_peak_hash over a stable payload that includes policy version
        # + per-quantile peak entries.
        peak_hash_payload = {
            "policy_version": policy.policy_version,
            "policy_config_hash": policy.policy_config_hash,
            "single_day_peak": {q: {"date": str(v.date), "volume_kg": v.volume_kg} for q, v in single_day_peak.items()},
            "sustained_3day_peak": {
                q: {
                    "start_date": str(v.start_date),
                    "end_date": str(v.end_date),
                    "rolling_daily_average_kg_per_day": v.rolling_daily_average_kg_per_day,
                    "cumulative_quantity_kg": v.cumulative_quantity_kg,
                }
                for q, v in sustained_3day.items()
            },
            "peak_duration_days": dict(peak_duration),
            "high_load_threshold": high_load_threshold,
        }
        agent_peak_hash = sha256_payload(peak_hash_payload)

        return ForecastPeakOutput(
            peak_metric_policy_version=policy.policy_version,
            peak_metric_policy_config_hash=policy.policy_config_hash,
            agent_peak_hash=agent_peak_hash,
            single_day_peak=single_day_peak,
            sustained_window_days=policy.sustained_window_days,
            sustained_3day_peak=sustained_3day,
            peak_window_days_before=policy.peak_window_days_before,
            peak_window_days_after=policy.peak_window_days_after,
            peak_window_cumulative_quantity_kg=peak_window_cum,
            peak_duration_days=peak_duration,
            high_load_threshold=high_load_threshold,
            dominant_variety=dominant_variety,
            peak_formation_explanation_ref=None,
        )


__all__ = ["DefaultPeakAdapter"]
