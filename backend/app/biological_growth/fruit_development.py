"""Cohort thermal age and a normalized double-sigmoid berry-growth trajectory."""

from __future__ import annotations

import math

from .forcing import thermal_development_hour
from .schemas import FruitGrowthCurve


def advance_thermal_age(temperature_c: float, *, base_temperature_c: float) -> float:
    return thermal_development_hour(temperature_c, base_temperature_c=base_temperature_c)


def _logistic(value: float, midpoint: float, width: float) -> float:
    if not all(math.isfinite(item) for item in (value, midpoint, width)) or width <= 0.0:
        raise ValueError("Logistic inputs must be finite and width must be positive")
    z = min(max(-(value - midpoint) / width, -700.0), 700.0)
    return 1.0 / (1.0 + math.exp(z))


def double_sigmoid_growth_fraction(
    thermal_age_dd: float,
    *,
    stage1_midpoint_dd: float,
    stage2_midpoint_dd: float,
    width_dd: float,
) -> float:
    """Two logistic expansion increments normalized to [0,1]."""
    if not 0.0 < stage1_midpoint_dd < stage2_midpoint_dd:
        raise ValueError("Double-logistic midpoints must be positive and strictly ordered")
    first = _logistic(thermal_age_dd, stage1_midpoint_dd, width_dd)
    second = _logistic(thermal_age_dd, stage2_midpoint_dd, width_dd)
    final = _logistic(1e6, stage1_midpoint_dd, width_dd) + _logistic(
        1e6, stage2_midpoint_dd, width_dd
    )
    return min(max((first + second) / final, 0.0), 1.0)


def double_gompertz_growth_fraction(
    thermal_age_dd: float,
    *,
    stage1_midpoint_dd: float,
    stage2_midpoint_dd: float,
    width_dd: float,
) -> float:
    """Alternative smooth two-Gompertz reference curve; parameters remain scenario-only."""
    if not 0.0 < stage1_midpoint_dd < stage2_midpoint_dd:
        raise ValueError("Double-Gompertz midpoints must be positive and strictly ordered")
    first = _gompertz(thermal_age_dd, stage1_midpoint_dd, width_dd)
    second = _gompertz(thermal_age_dd, stage2_midpoint_dd, width_dd)
    return min(max((first + second) / 2.0, 0.0), 1.0)


def stagewise_thermal_growth_fraction(
    thermal_age_dd: float,
    *,
    stage1_end_dd: float,
    stage2_end_dd: float,
    final_age_dd: float,
) -> float:
    """Piecewise thermal reference with continuous joins at the declared stage bounds."""
    if not all(
        math.isfinite(item) for item in (thermal_age_dd, stage1_end_dd, stage2_end_dd, final_age_dd)
    ):
        raise ValueError("Stagewise thermal inputs must be finite")
    if not 0.0 < stage1_end_dd < stage2_end_dd < final_age_dd:
        raise ValueError("Stagewise thermal boundaries must be positive and strictly ordered")
    age = max(0.0, thermal_age_dd)
    if age <= stage1_end_dd:
        return 0.5 * age / stage1_end_dd
    if age <= stage2_end_dd:
        return 0.5
    return min(1.0, 0.5 + 0.5 * (age - stage2_end_dd) / (final_age_dd - stage2_end_dd))


def fruit_growth_fraction(
    thermal_age_dd: float,
    *,
    curve: FruitGrowthCurve,
    stage1_midpoint_dd: float,
    stage2_midpoint_dd: float,
    width_dd: float,
    final_age_dd: float,
) -> float:
    if not all(
        math.isfinite(item)
        for item in (
            thermal_age_dd,
            stage1_midpoint_dd,
            stage2_midpoint_dd,
            width_dd,
            final_age_dd,
        )
    ):
        raise ValueError("Fruit-growth inputs must be finite")
    if not 0.0 < stage1_midpoint_dd < stage2_midpoint_dd < final_age_dd:
        raise ValueError("Fruit-growth thermal boundaries must be positive and strictly ordered")
    if width_dd <= 0.0:
        raise ValueError("Fruit-growth curve width must be positive")
    if curve is FruitGrowthCurve.DOUBLE_LOGISTIC:
        return double_sigmoid_growth_fraction(
            thermal_age_dd,
            stage1_midpoint_dd=stage1_midpoint_dd,
            stage2_midpoint_dd=stage2_midpoint_dd,
            width_dd=width_dd,
        )
    if curve is FruitGrowthCurve.DOUBLE_GOMPERTZ:
        return double_gompertz_growth_fraction(
            thermal_age_dd,
            stage1_midpoint_dd=stage1_midpoint_dd,
            stage2_midpoint_dd=stage2_midpoint_dd,
            width_dd=width_dd,
        )
    return stagewise_thermal_growth_fraction(
        thermal_age_dd,
        stage1_end_dd=stage1_midpoint_dd,
        stage2_end_dd=stage2_midpoint_dd,
        final_age_dd=final_age_dd,
    )


def _gompertz(value: float, midpoint: float, width: float) -> float:
    if not all(math.isfinite(item) for item in (value, midpoint, width)) or width <= 0.0:
        raise ValueError("Gompertz inputs must be finite and width must be positive")
    z = min(max((value - midpoint) / width, -700.0), 700.0)
    return math.exp(-math.exp(-z))


def maturity_cumulative_fraction(
    thermal_age_dd: float, *, median_dd: float, width_dd: float
) -> float:
    if not all(math.isfinite(value) for value in (thermal_age_dd, median_dd, width_dd)):
        raise ValueError("Maturity distribution inputs must be finite")
    if width_dd <= 0.0:
        raise ValueError("Maturity distribution width must be positive")
    return _logistic(thermal_age_dd, median_dd, width_dd)


def seed_adjusted_ripe_median(
    base_median_dd: float,
    *,
    seed_index: float,
    reference_index: float,
    response: float,
    shift_scale_dd: float,
) -> float:
    """Scenario modifier only; seed count is not inferred or fabricated."""
    return base_median_dd + response * (reference_index - seed_index) * shift_scale_dd


def berry_weight_potential_g(
    potential_weight_g: float,
    *,
    growth_fraction: float,
    source_modifier: float,
    source_reference_index: float,
    source_response: float,
    seed_index: float,
    seed_response: float,
) -> float:
    """Bounded-response structure for synthetic source and latent seed effects."""
    weight = potential_weight_g * growth_fraction
    weight *= 1.0 + source_response * (source_modifier - source_reference_index)
    weight *= 1.0 + seed_response * (seed_index - source_reference_index)
    return max(0.0, weight)
