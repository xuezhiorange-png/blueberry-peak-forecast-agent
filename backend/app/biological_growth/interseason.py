"""Normalized latent state transfer between production seasons."""

from __future__ import annotations


def carryover_state(
    *,
    reserve_index: float,
    vigor_index: float,
    crop_load_index: float,
    reserve_carryover_fraction: float,
    vigor_carryover_fraction: float,
    vigor_crop_load_penalty: float,
    reserve_crop_load_penalty: float,
    bud_crop_load_penalty: float,
    reserve_bud_contribution: float,
) -> dict[str, float]:
    reserve = min(max(reserve_index, 0.0), 1.0)
    vigor = min(max(vigor_index, 0.0), 1.0)
    load = min(max(crop_load_index, 0.0), 1.0)
    return {
        "postharvest_vigor_proxy": max(
            0.0, vigor * vigor_carryover_fraction * (1.0 - vigor_crop_load_penalty * load)
        ),
        "carbohydrate_reserve_proxy": max(
            0.0, reserve * reserve_carryover_fraction * (1.0 - reserve_crop_load_penalty * load)
        ),
        "next_season_flower_bud_potential": max(
            0.0,
            vigor * (1.0 - bud_crop_load_penalty * load) + reserve * reserve_bud_contribution,
        ),
    }
