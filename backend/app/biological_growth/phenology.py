"""State labels and progression calculations shared by the simulator engine."""

from __future__ import annotations

DECIDUOUS_STATES = frozenset(
    {
        "POSTHARVEST",
        "VEGETATIVE_REGROWTH",
        "FLOWER_BUD_FORMATION",
        "ACCLIMATION",
        "DORMANT",
        "CHILL_ACCUMULATING",
        "CHILL_SATISFIED",
        "FORCING",
        "BUD_SWELL",
        "BUD_BREAK",
        "BLOOM_10",
        "BLOOM_50",
        "BLOOM_90",
        "FRUIT_SET",
        "GREEN_FRUIT",
        "STAGE_I",
        "STAGE_II",
        "STAGE_III",
        "COLOR_BREAK",
        "RIPE",
    }
)
EVERGREEN_STATES = DECIDUOUS_STATES - {
    "ACCLIMATION",
    "DORMANT",
    "CHILL_ACCUMULATING",
    "CHILL_SATISFIED",
}


def bloom_progress_from_forcing(forcing_dd: float, start_dd: float, duration_dd: float) -> float:
    if duration_dd <= 0.0:
        raise ValueError("Bloom duration must be positive")
    return min(max((forcing_dd - start_dd) / duration_dd, 0.0), 1.0)


def state_from_progress(
    *,
    forcing_dd: float,
    bloom_progress: float,
    bud_swell_dd: float,
    bud_break_dd: float,
    bloom_start_dd: float,
    fruit_set_seen: bool,
    mature_seen: bool,
) -> str:
    if mature_seen:
        return "RIPE"
    if fruit_set_seen:
        return "GREEN_FRUIT"
    if bloom_progress >= 0.9:
        return "BLOOM_90"
    if bloom_progress >= 0.5:
        return "BLOOM_50"
    if bloom_progress >= 0.1:
        return "BLOOM_10"
    if forcing_dd >= bloom_start_dd:
        return "BLOOM_10"
    if forcing_dd >= bud_break_dd:
        return "BUD_BREAK"
    if forcing_dd >= bud_swell_dd:
        return "BUD_SWELL"
    return "FORCING"
