"""Typed, unit-declared inputs and outputs for the V0.9 theoretical simulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class ProductionSystem(StrEnum):
    DECIDUOUS_NATURAL = "DECIDUOUS_NATURAL"
    DECIDUOUS_FORCING = "DECIDUOUS_FORCING"
    EVERGREEN = "EVERGREEN"


class ChillModel(StrEnum):
    CHILL_HOURS = "CHILL_HOURS"
    UTAH_CHILL_UNITS = "UTAH_CHILL_UNITS"
    DYNAMIC_CHILL_PORTIONS = "DYNAMIC_CHILL_PORTIONS"


class FruitGrowthCurve(StrEnum):
    DOUBLE_LOGISTIC = "DOUBLE_LOGISTIC"
    DOUBLE_GOMPERTZ = "DOUBLE_GOMPERTZ"
    STAGEWISE_THERMAL = "STAGEWISE_THERMAL"


class EventType(StrEnum):
    POSTHARVEST_PRUNING = "POSTHARVEST_PRUNING"
    SUMMER_PRUNING = "SUMMER_PRUNING"
    DORMANT_PRUNING = "DORMANT_PRUNING"
    CANE_RENEWAL = "CANE_RENEWAL"
    FRUITING_WOOD_THINNING = "FRUITING_WOOD_THINNING"
    FLOWER_BUD_THINNING = "FLOWER_BUD_THINNING"
    FLOWER_REMOVAL = "FLOWER_REMOVAL"
    FLOWER_THINNING = "FLOWER_THINNING"
    FRUITLET_THINNING = "FRUITLET_THINNING"
    FRUIT_THINNING = "FRUIT_THINNING"
    GREENHOUSE_CLOSE = "GREENHOUSE_CLOSE"
    GREENHOUSE_OPEN = "GREENHOUSE_OPEN"
    HEATING_START = "HEATING_START"
    HEATING_STOP = "HEATING_STOP"
    DORMANCY_BREAK_TREATMENT = "DORMANCY_BREAK_TREATMENT"
    SHADE_START = "SHADE_START"
    SHADE_STOP = "SHADE_STOP"
    SHADE_APPLICATION = "SHADE_APPLICATION"
    LEAF_RETENTION_MANAGEMENT = "LEAF_RETENTION_MANAGEMENT"
    DEFOLIATION = "DEFOLIATION"
    POLLINATION_WINDOW_START = "POLLINATION_WINDOW_START"
    POLLINATION_WINDOW_END = "POLLINATION_WINDOW_END"
    POLLINATION_START = "POLLINATION_START"
    POLLINATION_END = "POLLINATION_END"
    POLLINATOR_INTRODUCTION = "POLLINATOR_INTRODUCTION"
    IRRIGATION_STRESS = "IRRIGATION_STRESS"
    NUTRITION_INTERVENTION = "NUTRITION_INTERVENTION"
    PRUNING = "PRUNING"
    WINTER_PRUNING = "WINTER_PRUNING"


class ParameterAuthority(StrEnum):
    BUSINESS_CONFIRMED = "BUSINESS_CONFIRMED"
    DIRECT_OBSERVED = "DIRECT_OBSERVED"
    DATA_CALIBRATED = "DATA_CALIBRATED"
    LITERATURE_PRIOR = "LITERATURE_PRIOR"
    MODEL_ASSUMPTION = "MODEL_ASSUMPTION"
    UNBOUND = "UNBOUND"


@dataclass(frozen=True)
class Cultivar:
    cultivar_id: str
    blueberry_type: str
    flowering_pathway: str = "SEASONAL"
    evergreen_dormancy_bypass: bool | None = None


@dataclass(frozen=True)
class CaneCohort:
    age_years: int
    cane_count: float
    productive_fraction: float


@dataclass(frozen=True)
class PlantStructure:
    plant_density_per_mu: float
    canes: tuple[CaneCohort, ...]
    leaf_area_index: float
    productive_shoots_per_plant: float
    fruiting_wood_index: float


@dataclass(frozen=True)
class InitialPlantState:
    reserve_index: float
    vigor_index: float
    canopy_health_index: float
    flower_bud_potential_per_plant: float
    prior_crop_load_index: float
    leaf_retention_ratio: float


@dataclass(frozen=True)
class EnvironmentHour:
    timestamp: datetime
    air_temperature_c: float
    source_id: str
    source_priority: int
    relative_humidity_pct: float | None = None
    root_zone_temperature_c: float | None = None
    radiation_index: float | None = None
    photoperiod_hours: float | None = None


@dataclass(frozen=True)
class ManagementEvent:
    event_id: str
    event_type: EventType
    event_datetime: datetime
    intensity: float | None
    intensity_unit: str | None
    observed_or_planned: str
    source_reference: str
    target: str


@dataclass(frozen=True)
class Parameter:
    parameter_id: str
    name: str
    value: float | None
    unit: str
    authority: ParameterAuthority
    source_id: str | None
    cultivar_scope: str
    system_scope: str
    lifecycle: str
    production_eligible: bool = False


@dataclass(frozen=True)
class ParameterSet:
    parameter_set_id: str
    parameters: tuple[Parameter, ...]
    scenario_only: bool = True

    def get(self, name: str) -> float:
        for parameter in self.parameters:
            if parameter.name == name and parameter.value is not None:
                return parameter.value
        raise KeyError(f"Unbound required parameter: {name}")


@dataclass(frozen=True)
class SimulationInput:
    simulation_id: str
    cultivar: Cultivar
    production_system: ProductionSystem
    plant_structure: PlantStructure
    initial_state: InitialPlantState
    environment: tuple[EnvironmentHour, ...]
    management_events: tuple[ManagementEvent, ...]
    parameter_set: ParameterSet
    productive_area_mu: float
    environment_mode: str = "OBSERVED_OR_SUPPLIED_MICROCLIMATE"


@dataclass(frozen=True)
class PlantStatePoint:
    day: date
    reserve_index: float
    vigor_index: float
    leaf_area_index: float
    productive_canes: float
    productive_shoots_per_plant: float
    fruiting_wood_index: float
    vegetative_shoot_potential: float
    flower_bud_potential_per_plant: float
    flower_load_per_plant: float
    fruit_load_per_plant: float
    source_supply_index: float
    sink_demand_index: float
    source_sink_sufficiency: float
    phenology_stage: str
    dormancy_state: str
    chill_accumulation: float
    forcing_accumulation: float
    bloom_progress: float
    new_mature_kg: float
    new_mature_kg_per_plant: float


@dataclass(frozen=True)
class BloomCohortOutput:
    cohort_id: str
    origin_date: date
    flower_quantity_per_plant: float


@dataclass(frozen=True)
class FruitSetCohortOutput:
    cohort_id: str
    origin_bloom_cohort_id: str
    fruit_set_date: date
    effective_pollinated_flowers_per_plant: float
    fruit_number_per_plant: float


@dataclass(frozen=True)
class FruitDevelopmentCohortOutput:
    cohort_id: str
    origin_bloom_cohort_id: str
    origin_fruit_set_cohort_id: str
    fruit_set_date: date
    fruit_quantity_per_plant: float
    development_stage: str
    seed_effect_index: float
    thermal_age_degree_days: float
    source_sink_modifier: float
    cumulative_ripe_fraction: float
    potential_berry_weight_g: float
    ripe_mass_kg: float
    ripe_mass_kg_per_plant: float


@dataclass(frozen=True)
class InterSeasonOutput:
    postharvest_vigor_proxy: float
    carbohydrate_reserve_proxy: float
    next_season_flower_bud_potential: float
    next_cane_age_structure: tuple[tuple[int, float, float], ...]


@dataclass(frozen=True)
class SimulationOutput:
    simulation_id: str
    model_version: str
    simulation_input_sha256: str
    parameter_set_id: str
    parameter_set_sha256: str
    cultivar_id: str
    production_system: ProductionSystem
    productive_area_mu: float
    plant_density_per_mu: float
    chill_model: ChillModel
    fruit_growth_curve: FruitGrowthCurve
    daily_states: tuple[PlantStatePoint, ...]
    bloom_cohorts: tuple[BloomCohortOutput, ...]
    fruit_set_cohorts: tuple[FruitSetCohortOutput, ...]
    fruit_development_cohorts: tuple[FruitDevelopmentCohortOutput, ...]
    daily_newly_mature_quantity_kg: tuple[tuple[date, float], ...]
    daily_newly_mature_quantity_kg_per_plant: tuple[tuple[date, float], ...]
    interseason_state: InterSeasonOutput
    trace: dict[str, tuple[str, ...]] = field(default_factory=dict)
