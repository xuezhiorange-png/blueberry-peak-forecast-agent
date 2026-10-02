"""Frozen M0 mathematical kernels extracted verbatim from archived research runners.

No candidate search or private source locators. The algorithm/configuration,
rounding and boundary derivative are unchanged; reconciliation parity tests
compare the extraction with the original frozen runners locally.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any, cast

from backend.app.area_yield.v0_10_mechanism_informed_model import (
    normalize_nonnegative,
    task8_shared_shape,
)

SELECTED_VARIANT = "B2_LOCAL_EMPIRICAL_TAIL_DERIVATIVE"
DECIMAL_QUANTUM = Decimal("0.000001")


def _normalize(values: Sequence[float]) -> tuple[float, ...]:
    normalized = normalize_nonnegative(tuple(float(value) for value in values))
    rounded = [float(f"{value:.6f}") for value in normalized]
    if not rounded:
        raise ValueError("EMPTY_CURVE")
    # Correct quantization residual on the largest cell. Correcting the final
    # cell can make a legitimate near-zero tail negative when rounded earlier
    # cells sum slightly above one.
    correction_index = max(range(len(rounded)), key=rounded.__getitem__)
    rounded[correction_index] += 1.0 - sum(rounded)
    if rounded[correction_index] < 0:
        raise ValueError("NORMALIZATION_ROUNDING_NEGATIVE_TAIL")
    if abs(sum(rounded) - 1.0) > 1e-12:
        raise ValueError("NORMALIZATION_MASS_NOT_CONSERVED")
    return tuple(rounded)


def apply_local_empirical_tail_derivative(
    fitted: Sequence[float], empirical: Sequence[float]
) -> tuple[tuple[float, ...], dict[str, Any]]:
    """Locally correct an artificial rising spline tail without adding a fitted parameter."""
    if len(fitted) != len(empirical) or len(fitted) < 4:
        raise ValueError("TAIL_CORRECTION_SUPPORT_INVALID")
    base = tuple(float(value) for value in fitted)
    pooled = tuple(float(value) for value in empirical)
    base_peak = max(range(len(base)), key=base.__getitem__)
    empirical_peak = max(range(len(pooled)), key=pooled.__getitem__)
    base_slope = base[-1] - base[-2]
    if empirical_peak == len(pooled) - 1:
        return _normalize(base), {
            "applied": False,
            "reason": "EMPIRICAL_PEAK_AT_RIGHT_BOUNDARY",
            "empirical_tail_slope": pooled[-1] - pooled[-2],
            "pre_correction_slope": base_slope,
        }
    if base_peak != len(base) - 1 or base_slope <= 0:
        return _normalize(base), {
            "applied": False,
            "reason": "NO_ARTIFICIAL_RISING_BOUNDARY_PEAK",
            "empirical_tail_slope": pooled[-1] - pooled[-2],
            "pre_correction_slope": base_slope,
        }
    # OLS slope over the final three empirical support days, using only this fold's train rows.
    tail = pooled[-3:]
    x_mean = 1.0
    y_mean = statistics.fmean(tail)
    empirical_slope = sum((x - x_mean) * (y - y_mean) for x, y in enumerate(tail)) / 2.0
    if base_slope <= empirical_slope:
        return _normalize(base), {
            "applied": False,
            "reason": "FITTED_TAIL_NOT_STEEPER_THAN_EMPIRICAL_TAIL",
            "empirical_tail_slope": empirical_slope,
            "pre_correction_slope": base_slope,
        }
    # Raising the penultimate value by (base - empirical) makes
    # (last - penultimate) equal the empirical terminal slope.
    delta = base_slope - empirical_slope
    corrected = list(base)
    # Compact cubic h(t)=t^2(t-1), t={0,.5,1}; endpoints stay fixed and
    # the final discrete derivative becomes the fold-local empirical slope.
    midpoint_correction = delta
    corrected[-2] += midpoint_correction
    result = _normalize(corrected)
    return result, {
        "applied": True,
        "reason": "MATCHED_TRAINING_EMPIRICAL_LAST_THREE_DAY_SLOPE",
        "empirical_tail_slope": empirical_slope,
        "pre_correction_slope": base_slope,
        "post_correction_slope": result[-1] - result[-2],
        "midpoint_correction": midpoint_correction,
        "baseline_peak_index": base_peak,
        "empirical_peak_index": empirical_peak,
    }


def _fit_shared_shape(
    samples: Sequence[Mapping[str, Any]], *, support_days: int = 290
) -> tuple[tuple[float, ...], dict[str, Any]]:
    positive = [row for row in samples if float(row["total"]) > 0]
    if not positive:
        raise ValueError("NO_POSITIVE_CURVES_FOR_SHARED_SHAPE")
    season_starts = {
        "2023-2024": date(2023, 7, 1),
        "2024-2025": date(2024, 7, 1),
        "2025-2026": date(2025, 7, 1),
    }
    training_curves: list[list[dict[str, Any]]] = []
    for sample in positive:
        season = str(sample["season"])
        training_curves.append(
            [
                {
                    "season": season,
                    "date": day.isoformat(),
                    "new_quantity_kg": quantity,
                }
                for day, quantity in zip(sample["dates"], sample["quantities"], strict=True)
            ]
        )
    baseline = normalize_nonnegative(
        task8_shared_shape(
            training_curves,
            season_starts=season_starts,
            support_days=tuple(range(support_days)),
        )
    )
    sums = [0.0] * support_days
    counts = [0] * support_days
    for sample in positive:
        total = float(sample["total"])
        axis_start = season_starts[str(sample["season"])]
        for day, quantity in zip(sample["dates"], sample["quantities"], strict=True):
            position = (cast(date, day) - axis_start).days
            if position < 0 or position >= support_days:
                raise ValueError("TRAINING_CURVE_OUTSIDE_CANONICAL_SUPPORT")
            sums[position] += float(quantity) / total
            counts[position] += 1
    empirical = _normalize(
        tuple(
            sums[index] / counts[index] if counts[index] else 0.0 for index in range(support_days)
        )
    )
    if SELECTED_VARIANT != "B2_LOCAL_EMPIRICAL_TAIL_DERIVATIVE":
        raise ValueError("FROZEN_SPLINE_VARIANT_CHANGED")
    corrected, detail = apply_local_empirical_tail_derivative(baseline, empirical)
    return tuple(float(value) for value in corrected), {
        "variant": SELECTED_VARIANT,
        "support_days": support_days,
        "training_base_season_count": len(positive),
        "task8_baseline_curve": list(baseline),
        "pooled_empirical_curve": list(empirical),
        "boundary_correction": detail,
    }


def _daily_quantities(total: float, shares: Sequence[float]) -> tuple[float, ...]:
    values = [Decimal(str(total)) * Decimal(str(share)) for share in shares]
    rounded = [value.quantize(DECIMAL_QUANTUM) for value in values]
    if rounded:
        rounded[-1] += Decimal(str(total)).quantize(DECIMAL_QUANTUM) - sum(rounded, Decimal(0))
    return tuple(float(value) for value in rounded)
