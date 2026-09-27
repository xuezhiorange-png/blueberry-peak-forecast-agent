"""Convert cohort maturity-fraction changes to nonnegative biological mass."""

from __future__ import annotations


def newly_mature_mass_kg(
    fruit_count: float,
    berry_weight_g: float,
    ripe_fraction_delta: float,
    marketable_fraction: float,
    plant_count: float,
) -> float:
    values = (fruit_count, berry_weight_g, ripe_fraction_delta, marketable_fraction, plant_count)
    if any(value < 0.0 for value in values):
        raise ValueError("Maturity mass inputs cannot be negative")
    return (
        fruit_count
        * berry_weight_g
        / 1000.0
        * min(ripe_fraction_delta, 1.0)
        * min(marketable_fraction, 1.0)
        * plant_count
    )
