"""Explicit simplified proxy for composite plant source and sink pressure."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSinkResult:
    source_supply: float
    sink_demand: float
    sufficiency: float


def source_sink_balance(
    *,
    leaf_area_index: float,
    canopy_health: float,
    radiation_index: float,
    temperature_suitability: float,
    reserve_index: float,
    fruit_number_per_plant: float,
    vegetative_vigor: float,
    fruit_sink_strength: float,
    vegetative_sink_strength: float,
    root_growth_sink_strength: float,
    storage_sink_strength: float,
    reserve_mobilization_fraction: float,
    light_half_saturation: float,
    sufficiency_floor: float,
    sufficiency_ceiling: float,
) -> SourceSinkResult:
    """Dimensionless scenario-level balance; no carbon-mass interpretation."""
    light = max(0.0, radiation_index) / (max(0.0, radiation_index) + light_half_saturation)
    source = max(0.0, leaf_area_index) * max(0.0, canopy_health) * light
    source *= max(0.0, temperature_suitability)
    source += max(0.0, reserve_index) * reserve_mobilization_fraction
    sink = (
        max(0.0, fruit_number_per_plant) * fruit_sink_strength
        + max(0.0, vegetative_vigor) * vegetative_sink_strength
        + max(0.0, vegetative_vigor) * root_growth_sink_strength
        + storage_sink_strength
    )
    sufficiency = min(sufficiency_ceiling, max(sufficiency_floor, source / max(sink, 1e-12)))
    return SourceSinkResult(source, sink, sufficiency)


def stage_weighted_fruit_load(
    cohorts: tuple[tuple[float, str], ...], stage_weights: dict[str, float]
) -> float:
    """Synthetic stage-weight abstraction; coefficients are not blueberry priors."""
    return sum(max(count, 0.0) * stage_weights.get(stage, 1.0) for count, stage in cohorts)
