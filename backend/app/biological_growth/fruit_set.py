"""Bounded fruit-set abstraction preserving flower-to-fruit count conservation."""

from __future__ import annotations


def fruit_set_probability(
    pollination_index: float,
    source_sink_sufficiency: float,
    temperature_suitability: float,
    maximum_probability: float,
    source_base_weight: float,
    source_response_weight: float,
) -> float:
    value = (
        maximum_probability
        * pollination_index
        * (source_base_weight + source_response_weight * source_sink_sufficiency)
    )
    return min(max(value * temperature_suitability, 0.0), 1.0)


def set_fruit_count(effective_pollinated_flowers: float, probability: float) -> float:
    return min(max(effective_pollinated_flowers * probability, 0.0), effective_pollinated_flowers)
