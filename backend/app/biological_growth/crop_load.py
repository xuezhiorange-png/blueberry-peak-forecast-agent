"""Flower, fruitlet and fruit loads remain separate state quantities."""

from __future__ import annotations


def thin_quantity(quantity: float, intensity: float) -> float:
    return max(0.0, quantity * (1.0 - min(max(intensity, 0.0), 1.0)))


def crop_load_index(
    fruit_number_per_plant: float,
    productive_shoots_per_plant: float,
    fruit_capacity_per_shoot: float,
) -> float:
    denominator = max(productive_shoots_per_plant * fruit_capacity_per_shoot, 1e-12)
    return min(max(fruit_number_per_plant / denominator, 0.0), 1.0)
