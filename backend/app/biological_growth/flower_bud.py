"""Genotype-scoped flower-bud potential response, explicitly scenario-parameterized."""

from __future__ import annotations

from .schemas import Cultivar


def flower_bud_induction_signal(
    cultivar: Cultivar,
    *,
    photoperiod_hours: float | None,
    temperature_c: float,
    vegetative_vigor: float,
    reserve_index: float,
    previous_crop_load: float,
    response_strength: float,
    day_neutral_genotype: bool,
    photoperiod_reference_h: float,
    photoperiod_span_h: float,
    temperature_reference_c: float,
    temperature_span_c: float,
    photoperiod_weight: float,
    thermal_weight: float,
    vigor_weight: float,
    reserve_weight: float,
    previous_load_penalty: float,
) -> float:
    """A bounded abstract signal, not a fitted cultivar law or universal SD threshold."""
    short_day = (
        0.0
        if photoperiod_hours is None
        else min(max((photoperiod_reference_h - photoperiod_hours) / photoperiod_span_h, 0.0), 1.0)
    )
    photo_signal = 1.0 if day_neutral_genotype else short_day
    thermal_signal = min(
        max((temperature_reference_c - temperature_c) / temperature_span_c, 0.0), 1.0
    )
    vigor_signal = min(max(vegetative_vigor, 0.0), 1.0)
    reserve_signal = min(max(reserve_index, 0.0), 1.0)
    prior_load_penalty = min(max(previous_crop_load, 0.0), 1.0)
    cultivar_gate = 1.0 if cultivar.flowering_pathway else 0.0
    raw = (
        cultivar_gate
        * (
            photoperiod_weight * photo_signal
            + thermal_weight * thermal_signal
            + vigor_weight * vigor_signal
            + reserve_weight * reserve_signal
        )
        * (1.0 - previous_load_penalty * prior_load_penalty)
    )
    return min(max(raw * response_strength, 0.0), 1.0)
