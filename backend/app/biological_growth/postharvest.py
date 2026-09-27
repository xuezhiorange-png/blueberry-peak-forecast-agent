"""Latent reserve/vigor bookkeeping for the postharvest-to-next-season bridge."""

from __future__ import annotations


def update_reserve_index(
    current: float,
    *,
    source_supply: float,
    fruit_demand: float,
    vegetative_demand: float,
    storage_demand: float,
    gain_rate: float,
    maintenance_cost: float,
    fruit_demand_cost: float,
    other_demand_cost: float,
) -> float:
    change = (
        gain_rate * source_supply
        - maintenance_cost
        - fruit_demand_cost * fruit_demand
        - other_demand_cost * vegetative_demand
        - other_demand_cost * storage_demand
    )
    return min(max(current + change, 0.0), 1.0)
