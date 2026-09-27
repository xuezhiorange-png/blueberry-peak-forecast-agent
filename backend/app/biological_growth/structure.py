"""Plant structure and management-event state changes."""

from __future__ import annotations

from dataclasses import dataclass

from .schemas import EventType, ManagementEvent, PlantStructure


@dataclass
class StructuralState:
    productive_canes: float
    age_weighted_productivity_index: float
    productive_shoots: float
    fruiting_wood_index: float
    leaf_area_index: float
    vegetative_shoot_potential: float


def initial_structural_state(
    structure: PlantStructure,
    *,
    juvenile_productivity_weight: float,
    mature_productivity_weight: float,
    old_productivity_weight: float,
    mature_age_years: int,
    old_age_years: int,
) -> StructuralState:
    productive = sum(cane.cane_count * cane.productive_fraction for cane in structure.canes)
    weighted_productive = sum(
        cane.cane_count
        * cane.productive_fraction
        * _cane_age_weight(
            cane.age_years,
            juvenile_weight=juvenile_productivity_weight,
            mature_weight=mature_productivity_weight,
            old_weight=old_productivity_weight,
            mature_age_years=mature_age_years,
            old_age_years=old_age_years,
        )
        for cane in structure.canes
    )
    return StructuralState(
        productive_canes=productive,
        age_weighted_productivity_index=(weighted_productive / productive if productive else 0.0),
        productive_shoots=structure.productive_shoots_per_plant,
        fruiting_wood_index=structure.fruiting_wood_index,
        leaf_area_index=structure.leaf_area_index,
        vegetative_shoot_potential=max(structure.productive_shoots_per_plant, 0.0),
    )


def _cane_age_weight(
    age_years: int,
    *,
    juvenile_weight: float,
    mature_weight: float,
    old_weight: float,
    mature_age_years: int,
    old_age_years: int,
) -> float:
    if old_age_years <= mature_age_years:
        raise ValueError("old cane age must be greater than mature cane age")
    if age_years >= old_age_years:
        return old_weight
    if age_years >= mature_age_years:
        return mature_weight
    return juvenile_weight


def apply_structural_event(
    state: StructuralState,
    event: ManagementEvent,
    *,
    wood_loss_fraction: float,
    leaf_loss_fraction: float,
    regrowth_gain: float,
    cane_loss_fraction: float,
    shoot_loss_fraction: float,
) -> tuple[str, ...]:
    intensity = min(max(event.intensity or 0.0, 0.0), 1.0)
    if event.event_type in {
        EventType.POSTHARVEST_PRUNING,
        EventType.SUMMER_PRUNING,
        EventType.DORMANT_PRUNING,
        EventType.WINTER_PRUNING,
        EventType.PRUNING,
        EventType.CANE_RENEWAL,
        EventType.FRUITING_WOOD_THINNING,
    }:
        state.fruiting_wood_index = max(
            0.0, state.fruiting_wood_index * (1.0 - wood_loss_fraction * intensity)
        )
        state.productive_canes = max(
            0.0,
            state.productive_canes * (1.0 - cane_loss_fraction * wood_loss_fraction * intensity),
        )
        state.productive_shoots = max(
            0.0,
            state.productive_shoots * (1.0 - shoot_loss_fraction * wood_loss_fraction * intensity),
        )
        state.leaf_area_index = max(
            0.0, state.leaf_area_index * (1.0 - leaf_loss_fraction * intensity)
        )
        state.vegetative_shoot_potential += regrowth_gain * intensity
        return (
            f"{event.event_id}:fruiting_wood_and_cane_structure_reduced",
            f"{event.event_id}:leaf_source_potential_changed",
            f"{event.event_id}:future_vegetative_shoot_potential_increased_as_explicit_abstraction",
        )
    return ()


def age_cane_cohorts(structure: PlantStructure) -> tuple[tuple[int, float, float], ...]:
    """Advance cane cohort ages by one season; age class 1 is retained as renewal."""
    aged: list[tuple[int, float, float]] = [(1, 0.0, 1.0)]
    for cane in structure.canes:
        aged.append((cane.age_years + 1, cane.cane_count, cane.productive_fraction))
    return tuple(aged)
