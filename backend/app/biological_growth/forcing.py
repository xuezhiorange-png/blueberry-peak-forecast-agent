"""Hourly forcing response; threshold parameters are supplied, never defaulted."""

from __future__ import annotations


def growing_degree_hour(
    temperature_c: float,
    *,
    base_temperature_c: float,
    upper_temperature_c: float,
) -> float:
    if upper_temperature_c <= base_temperature_c:
        raise ValueError("upper temperature must exceed base temperature")
    effective = min(max(temperature_c, base_temperature_c), upper_temperature_c)
    return max(0.0, effective - base_temperature_c) / 24.0


def thermal_development_hour(temperature_c: float, *, base_temperature_c: float) -> float:
    return max(0.0, temperature_c - base_temperature_c) / 24.0
