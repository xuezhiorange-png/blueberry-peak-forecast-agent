"""Deterministic, scenario-only blueberry biological growth simulator."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Generator
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import cast

from .canonical import sha256_hex
from .crop_load import crop_load_index
from .dormancy import ChillAccumulator
from .flower_bud import flower_bud_induction_signal
from .forcing import growing_degree_hour
from .fruit_development import (
    advance_thermal_age,
    berry_weight_potential_g,
    fruit_growth_fraction,
    maturity_cumulative_fraction,
    seed_adjusted_ripe_median,
)
from .fruit_set import fruit_set_probability, set_fruit_count
from .interseason import carryover_state
from .management import effective_radiation_index, effective_temperature_c
from .maturity import newly_mature_mass_kg
from .parameters import validate_parameter_set
from .phenology import (
    bloom_progress_from_forcing,
    state_from_progress,
)
from .pollination import pollination_sufficiency
from .postharvest import update_reserve_index
from .schemas import (
    BloomCohortOutput,
    ChillModel,
    EnvironmentHour,
    EventType,
    FruitDevelopmentCohortOutput,
    FruitGrowthCurve,
    FruitSetCohortOutput,
    InterSeasonOutput,
    ManagementEvent,
    PlantStatePoint,
    ProductionSystem,
    SimulationInput,
    SimulationOutput,
)
from .source_sink import source_sink_balance, stage_weighted_fruit_load
from .structure import age_cane_cohorts, apply_structural_event, initial_structural_state


@dataclass
class _FruitCohort:
    cohort_id: str
    origin_date: date
    flower_quantity: float
    effective_pollinated_flowers: float
    thermal_age_dd: float = 0.0
    fruit_set_date: date | None = None
    fruit_number: float = 0.0
    previous_ripe_fraction: float = 0.0
    source_modifier: float = 1.0
    seed_index: float = 0.5
    ripe_mass_kg: float = 0.0
    ripe_mass_kg_per_plant: float = 0.0
    potential_berry_weight_g: float = 0.0
    development_stage: str = "FRUIT_SET"


def simulate(
    request: SimulationInput,
    *,
    chill_model: ChillModel,
    fruit_growth_curve: FruitGrowthCurve = FruitGrowthCurve.DOUBLE_LOGISTIC,
) -> SimulationOutput:
    """Run the complete supplied series in one stateful execution."""
    return _drain_daily_execution(
        _simulate_daily_steps(
            request,
            chill_model=chill_model,
            fruit_growth_curve=fruit_growth_curve,
        ),
        chunk_days=None,
    )


def simulate_with_daily_chunks(
    request: SimulationInput,
    *,
    chill_model: ChillModel,
    chunk_days: int,
    fruit_growth_curve: FruitGrowthCurve = FruitGrowthCurve.DOUBLE_LOGISTIC,
) -> SimulationOutput:
    """Run the same input by consuming daily state transitions in fixed chunks.

    The generator retains the live in-memory model state between chunks. This
    validates continuous execution parity; it does not claim a serialized or
    process-restart checkpoint format.
    """
    if chunk_days <= 0:
        raise ValueError("chunk_days must be positive")
    return _drain_daily_execution(
        _simulate_daily_steps(
            request,
            chill_model=chill_model,
            fruit_growth_curve=fruit_growth_curve,
        ),
        chunk_days=chunk_days,
    )


def _drain_daily_execution(
    execution: Generator[PlantStatePoint, None, SimulationOutput],
    *,
    chunk_days: int | None,
) -> SimulationOutput:
    while True:
        try:
            if chunk_days is None:
                while True:
                    next(execution)
            else:
                for _ in range(chunk_days):
                    next(execution)
        except StopIteration as completed:
            return cast(SimulationOutput, completed.value)


def _simulate_daily_steps(
    request: SimulationInput,
    *,
    chill_model: ChillModel,
    fruit_growth_curve: FruitGrowthCurve,
) -> Generator[PlantStatePoint, None, SimulationOutput]:
    """Run supplied hourly conditions through biological state transitions.

    The chill algorithm is a required explicit choice; no global chill model is
    selected. The double-logistic size trajectory is the default theoretical
    reference, with Gompertz and stagewise alternatives available.
    All numerical parameters must be explicitly supplied in a non-production
    `ParameterSet`. `DYNAMIC_CHILL_PORTIONS` uses a generic published formulation;
    its constants are literature priors, not blueberry-validated production values.
    """
    _validate_request(request)
    validate_parameter_set(request.parameter_set)
    p = request.parameter_set.get
    hours_by_day: dict[date, list[EnvironmentHour]] = defaultdict(list)
    for item in request.environment:
        hours_by_day[item.timestamp.date()].append(item)
    dates = sorted(hours_by_day)
    events_by_day: dict[date, list[ManagementEvent]] = defaultdict(list)
    for event in sorted(
        request.management_events, key=lambda item: (item.event_datetime, item.event_id)
    ):
        events_by_day[event.event_datetime.date()].append(event)

    structure = initial_structural_state(
        request.plant_structure,
        juvenile_productivity_weight=p("cane_productivity_juvenile_weight"),
        mature_productivity_weight=p("cane_productivity_mature_weight"),
        old_productivity_weight=p("cane_productivity_old_weight"),
        mature_age_years=int(p("cane_mature_age_years")),
        old_age_years=int(p("cane_old_age_years")),
    )
    structure.leaf_area_index *= request.initial_state.leaf_retention_ratio
    reserve = request.initial_state.reserve_index
    vigor = request.initial_state.vigor_index
    flower_bud_potential = request.initial_state.flower_bud_potential_per_plant
    flower_load = 0.0
    dormancy_treatment_intensity = 0.0
    dynamic_constants = (
        {
            name: p(name)
            for name in (
                "dynamic_model_e0",
                "dynamic_model_e1",
                "dynamic_model_a0",
                "dynamic_model_a1",
                "dynamic_model_slope",
                "dynamic_model_tf_kelvin",
            )
        }
        if chill_model is ChillModel.DYNAMIC_CHILL_PORTIONS
        else None
    )
    chill = ChillAccumulator(chill_model, dynamic_constants)
    dormancy_released = (
        request.production_system is ProductionSystem.EVERGREEN
        and request.cultivar.evergreen_dormancy_bypass is True
    )
    forcing_total = 0.0
    acclimation_signal = 0.0
    bud_induction_accumulation = 0.0
    bloom_progress = 0.0
    cohorts: list[_FruitCohort] = []
    daily_states: list[PlantStatePoint] = []
    daily_mature: list[tuple[date, float]] = []
    daily_mature_per_plant: list[tuple[date, float]] = []
    trace: dict[str, list[str]] = {
        "WHY_BUD_BREAK_OCCURRED": [],
        "WHY_BLOOM_OCCURRED": [],
        "WHY_FRUIT_SET_CHANGED": [],
        "WHY_MATURITY_ADVANCED_OR_DELAYED": [],
        "WHY_YIELD_CHANGED": [],
        "WHICH_MANAGEMENT_EVENT_AFFECTED_WHICH_STATE": [],
    }
    if dormancy_released:
        trace["WHY_BUD_BREAK_OCCURRED"].append(
            "explicit cultivar-scoped evergreen bypass binding; not a universal zero-chill rule"
        )
    events_all = tuple(request.management_events)
    production_system = request.production_system
    last_stage = "POSTHARVEST"
    fruit_set_seen = False
    mature_seen = False

    for day_index, current_day in enumerate(dates):
        daily_events = tuple(events_by_day.get(current_day, ()))
        for event in daily_events:
            event_effect_bound = False
            if event.event_type in {
                EventType.GREENHOUSE_CLOSE,
                EventType.GREENHOUSE_OPEN,
                EventType.HEATING_START,
                EventType.HEATING_STOP,
                EventType.SHADE_START,
                EventType.SHADE_STOP,
                EventType.SHADE_APPLICATION,
            }:
                trace["WHICH_MANAGEMENT_EVENT_AFFECTED_WHICH_STATE"].append(
                    f"{event.event_id}:{event.event_type.value}->environment_or_phenology_driver_only"
                )
                event_effect_bound = True
            elif event.event_type is EventType.DORMANCY_BREAK_TREATMENT:
                if request.production_system is ProductionSystem.EVERGREEN:
                    trace["WHICH_MANAGEMENT_EVENT_AFFECTED_WHICH_STATE"].append(
                        f"{event.event_id}:NOT_APPLICABLE_TO_EVERGREEN_PATH"
                    )
                else:
                    dormancy_treatment_intensity = max(
                        dormancy_treatment_intensity, event.intensity or 0.0
                    )
                    trace["WHICH_MANAGEMENT_EVENT_AFFECTED_WHICH_STATE"].append(
                        f"{event.event_id}:scenario dormancy-release gate modifier; "
                        "not a production treatment recommendation"
                    )
                event_effect_bound = True
            notes = apply_structural_event(
                structure,
                event,
                wood_loss_fraction=p("pruning_wood_loss_fraction"),
                leaf_loss_fraction=p("pruning_leaf_loss_fraction"),
                regrowth_gain=p("pruning_regrowth_gain"),
                cane_loss_fraction=p("pruning_cane_loss_fraction"),
                shoot_loss_fraction=p("pruning_shoot_loss_fraction"),
            )
            if notes:
                event_effect_bound = True
                bud_retention = 1.0 - min(max(event.intensity or 0.0, 0.0), 1.0) * p(
                    "pruning_bud_loss_fraction"
                )
                flower_bud_potential *= max(0.0, bud_retention)
                for cohort in cohorts:
                    if cohort.fruit_set_date is None:
                        cohort.flower_quantity *= max(0.0, bud_retention)
                trace["WHICH_MANAGEMENT_EVENT_AFFECTED_WHICH_STATE"].extend(notes)
            elif event.event_type in {
                EventType.FLOWER_BUD_THINNING,
                EventType.FLOWER_REMOVAL,
                EventType.FLOWER_THINNING,
            }:
                reduction = min(max(event.intensity or 0.0, 0.0), 1.0)
                flower_bud_potential *= 1.0 - reduction
                flower_load *= 1.0 - reduction
                for cohort in cohorts:
                    if cohort.fruit_set_date is None:
                        cohort.flower_quantity *= 1.0 - reduction
                trace["WHICH_MANAGEMENT_EVENT_AFFECTED_WHICH_STATE"].append(
                    f"{event.event_id}:effective_flower_load_reduced;leaf_source_retained"
                )
                event_effect_bound = True
            elif event.event_type in {EventType.FRUITLET_THINNING, EventType.FRUIT_THINNING}:
                retained = 1.0 - min(max(event.intensity or 0.0, 0.0), 1.0)
                for cohort in cohorts:
                    cohort.fruit_number *= retained
                trace["WHICH_MANAGEMENT_EVENT_AFFECTED_WHICH_STATE"].append(
                    f"{event.event_id}:fruit_sink_reduced"
                )
                event_effect_bound = True
            elif event.event_type is EventType.DEFOLIATION:
                intensity = min(max(event.intensity or 0.0, 0.0), 1.0)
                structure.leaf_area_index *= 1.0 - intensity
                trace["WHICH_MANAGEMENT_EVENT_AFFECTED_WHICH_STATE"].append(
                    f"{event.event_id}:leaf_area_and_source_potential_reduced"
                )
                event_effect_bound = True
            elif event.event_type is EventType.LEAF_RETENTION_MANAGEMENT:
                target_retention = min(max(event.intensity or 0.0, 0.0), 1.0)
                structure.leaf_area_index = max(
                    structure.leaf_area_index,
                    request.plant_structure.leaf_area_index * target_retention,
                )
                trace["WHICH_MANAGEMENT_EVENT_AFFECTED_WHICH_STATE"].append(
                    f"{event.event_id}:leaf_retention_target_applied_to_source_potential"
                )
                event_effect_bound = True
            elif event.event_type in {
                EventType.POLLINATION_WINDOW_START,
                EventType.POLLINATION_WINDOW_END,
                EventType.POLLINATION_START,
                EventType.POLLINATION_END,
                EventType.POLLINATOR_INTRODUCTION,
            }:
                trace["WHICH_MANAGEMENT_EVENT_AFFECTED_WHICH_STATE"].append(
                    f"{event.event_id}:{event.event_type.value}->pollination_opportunity"
                )
                event_effect_bound = True
            if not event_effect_bound:
                trace["WHICH_MANAGEMENT_EVENT_AFFECTED_WHICH_STATE"].append(
                    f"{event.event_id}:{event.event_type.value}->NO_PHYSIOLOGICAL_EFFECT_BOUND_IN_S3"
                )

        observations = hours_by_day[current_day]
        radiation_samples = [
            effective_radiation_index(
                item,
                events_all,
                scenario_mode=request.environment_mode == "THEORETICAL_SCENARIO_MICROCLIMATE",
                shade_fraction=p("microclimate_shade_fraction"),
            )
            for item in observations
            if item.radiation_index is not None
        ]
        radiation = (
            sum(radiation_samples) / len(radiation_samples)
            if radiation_samples
            else p("radiation_reference_index")
        )
        photo_values = [
            item.photoperiod_hours for item in observations if item.photoperiod_hours is not None
        ]
        photoperiod = sum(photo_values) / len(photo_values) if photo_values else None
        effective_temps: list[float] = []
        chill_increment_today = 0.0
        forcing_increment_today = 0.0
        thermal_development_today = 0.0
        chilling_active = (
            production_system is not ProductionSystem.EVERGREEN
            and acclimation_signal >= p("acclimation_start_signal_days")
        )
        for observation in observations:
            effective_temp = effective_temperature_c(
                observation,
                events_all,
                scenario_mode=request.environment_mode == "THEORETICAL_SCENARIO_MICROCLIMATE",
                closure_delta_c=p("microclimate_closure_delta_c"),
                heating_delta_c=p("microclimate_heating_delta_c"),
            )
            effective_temps.append(effective_temp)
            if chilling_active:
                chill_increment_today += chill.add_hour(effective_temp)
            if dormancy_released:
                forcing_increment_today += growing_degree_hour(
                    effective_temp,
                    base_temperature_c=p("forcing_base_temperature_c"),
                    upper_temperature_c=p("forcing_upper_temperature_c"),
                )
            thermal_development_today += advance_thermal_age(
                effective_temp, base_temperature_c=p("development_base_temperature_c")
            )
        thermal_mean = sum(effective_temps) / len(effective_temps)

        if day_index == 0:
            stage = "POSTHARVEST"
        else:
            stage = "VEGETATIVE_REGROWTH"
        signal = flower_bud_induction_signal(
            request.cultivar,
            photoperiod_hours=photoperiod,
            temperature_c=thermal_mean,
            vegetative_vigor=vigor,
            reserve_index=reserve,
            previous_crop_load=request.initial_state.prior_crop_load_index,
            response_strength=p("flower_bud_response_strength"),
            day_neutral_genotype=bool(p("day_neutral_genotype")),
            photoperiod_reference_h=p("flower_bud_photoperiod_reference_h"),
            photoperiod_span_h=p("flower_bud_photoperiod_span_h"),
            temperature_reference_c=p("flower_bud_temperature_reference_c"),
            temperature_span_c=p("flower_bud_temperature_span_c"),
            photoperiod_weight=p("flower_bud_photoperiod_weight"),
            thermal_weight=p("flower_bud_thermal_weight"),
            vigor_weight=p("flower_bud_vigor_weight"),
            reserve_weight=p("flower_bud_reserve_weight"),
            previous_load_penalty=p("flower_bud_previous_load_penalty"),
        )
        bud_induction_accumulation += signal
        if (
            photoperiod is not None
            and photoperiod <= p("acclimation_photoperiod_threshold_h")
            and thermal_mean <= p("acclimation_temperature_threshold_c")
        ):
            acclimation_signal += 1.0
        if bud_induction_accumulation >= p("flower_bud_induction_threshold"):
            stage = "FLOWER_BUD_FORMATION"
            flower_bud_potential += signal * max(vigor, 0.0) * p("flower_bud_increment_per_signal")
        if production_system is ProductionSystem.EVERGREEN:
            stage = "EVERGREEN_CONTINUATION" if forcing_total < p("bud_swell_forcing_dd") else stage
            flower_bud_potential += p("evergreen_flower_bud_rate") * max(vigor, 0.0)
        elif acclimation_signal >= p("acclimation_start_signal_days"):
            required_chill = p("chill_requirement")
            treatment_reduction = (
                p("dormancy_treatment_chill_requirement_reduction_fraction")
                if dormancy_treatment_intensity > 0.0
                else 0.0
            )
            if not 0.0 <= treatment_reduction <= 1.0:
                raise ValueError("Dormancy treatment reduction must be in [0,1]")
            effective_chill_threshold = required_chill * (
                1.0 - dormancy_treatment_intensity * treatment_reduction
            )
            if chill.total < effective_chill_threshold:
                stage = (
                    "DORMANT"
                    if acclimation_signal >= p("acclimation_dormancy_signal_days")
                    else "ACCLIMATION"
                )
            elif not dormancy_released:
                dormancy_released = True
                stage = "CHILL_SATISFIED"
                if chill.total < required_chill and dormancy_treatment_intensity > 0.0:
                    trace["WHY_BUD_BREAK_OCCURRED"].append(
                        f"{current_day.isoformat()}:scenario treatment-adjusted release gate; "
                        f"{chill_model.value}={chill.total:.6f}, "
                        f"effective_threshold={effective_chill_threshold:.6f}"
                    )
                else:
                    trace["WHY_BUD_BREAK_OCCURRED"].append(
                        f"{current_day.isoformat()}:model-inferred release after "
                        f"{chill_model.value} exposure threshold"
                    )
        forcing_total += forcing_increment_today
        if forcing_increment_today > 0 and stage not in {"CHILL_SATISFIED", "CHILL_ACCUMULATING"}:
            stage = "FORCING"
        if stage == "FORCING" and forcing_total >= p("bud_swell_forcing_dd"):
            stage = "BUD_SWELL"
        if forcing_total >= p("bud_break_forcing_dd"):
            if last_stage != "BUD_BREAK":
                trace["WHY_BUD_BREAK_OCCURRED"].append(
                    f"{current_day.isoformat()}:forcing accumulation crossed "
                    "supplied bud-break threshold"
                )
            stage = "BUD_BREAK"

        prior_bloom = bloom_progress
        if dormancy_released and forcing_total >= p("bloom_start_forcing_dd"):
            bloom_progress = bloom_progress_from_forcing(
                forcing_total,
                p("bloom_start_forcing_dd"),
                p("bloom_duration_dd"),
            )
        if bloom_progress > prior_bloom:
            if flower_load == 0.0:
                flower_load = max(
                    0.0,
                    flower_bud_potential
                    * structure.fruiting_wood_index
                    * structure.age_weighted_productivity_index,
                )
            new_flowers = flower_load * (bloom_progress - prior_bloom)
            cohort_id = f"{request.simulation_id}-B-{current_day.isoformat()}"
            cohorts.append(
                _FruitCohort(
                    cohort_id=cohort_id,
                    origin_date=current_day,
                    flower_quantity=new_flowers,
                    effective_pollinated_flowers=0.0,
                )
            )
            trace["WHY_BLOOM_OCCURRED"].append(
                f"{current_day.isoformat()}:{new_flowers:.8f} flowers/plant "
                "from continuous forcing progress"
            )
        total_fruit = sum(cohort.fruit_number for cohort in cohorts)
        temperature_suitability = _temperature_suitability(
            thermal_mean,
            p("temperature_stress_low_c"),
            p("temperature_stress_high_c"),
        )
        balance = source_sink_balance(
            leaf_area_index=structure.leaf_area_index,
            canopy_health=request.initial_state.canopy_health_index,
            radiation_index=radiation,
            temperature_suitability=temperature_suitability,
            reserve_index=reserve,
            fruit_number_per_plant=stage_weighted_fruit_load(
                tuple((cohort.fruit_number, cohort.development_stage) for cohort in cohorts),
                {
                    "FRUIT_SET": p("stage_sink_fruit_set"),
                    "STAGE_I": p("stage_sink_stage_i"),
                    "STAGE_II": p("stage_sink_stage_ii"),
                    "STAGE_III": p("stage_sink_stage_iii"),
                    "COLOR_BREAK": p("stage_sink_color_break"),
                    "RIPE": p("stage_sink_ripe"),
                },
            ),
            vegetative_vigor=vigor,
            fruit_sink_strength=p("fruit_sink_strength"),
            vegetative_sink_strength=p("vegetative_sink_strength"),
            root_growth_sink_strength=p("root_growth_sink_strength"),
            storage_sink_strength=p("storage_sink_strength"),
            reserve_mobilization_fraction=p("reserve_mobilization_fraction"),
            light_half_saturation=p("source_light_half_saturation"),
            sufficiency_floor=p("source_sink_floor"),
            sufficiency_ceiling=p("source_sink_ceiling"),
        )
        pollination = pollination_sufficiency(
            events_all,
            at=observations[-1].timestamp,
            baseline=p("pollination_baseline_index"),
            introduction_increment=p("pollinator_event_increment"),
            temperature_suitability=temperature_suitability,
        )
        fruit_set_today = False
        newly_mature_today = 0.0
        newly_mature_today_per_plant = 0.0
        for cohort in cohorts:
            if cohort.fruit_set_date is None:
                cohort.thermal_age_dd += thermal_development_today
                if cohort.thermal_age_dd >= p("fruit_set_lag_dd") and cohort.flower_quantity > 0:
                    cohort.effective_pollinated_flowers = cohort.flower_quantity * pollination
                    probability = fruit_set_probability(
                        pollination,
                        balance.sufficiency,
                        temperature_suitability,
                        p("fruit_set_maximum"),
                        p("fruit_set_source_base_weight"),
                        p("fruit_set_source_response_weight"),
                    )
                    cohort.fruit_number = set_fruit_count(
                        cohort.effective_pollinated_flowers, probability
                    )
                    cohort.fruit_set_date = current_day
                    cohort.source_modifier = balance.sufficiency
                    cohort.seed_index = pollination
                    fruit_set_today = True
                    trace["WHY_FRUIT_SET_CHANGED"].append(
                        f"{cohort.cohort_id}:flowers={cohort.flower_quantity:.8f};pollination={pollination:.6f};set={cohort.fruit_number:.8f}"
                    )
            else:
                cohort.thermal_age_dd += thermal_development_today
                prior_fraction = cohort.previous_ripe_fraction
                ripe_fraction = maturity_cumulative_fraction(
                    cohort.thermal_age_dd,
                    median_dd=seed_adjusted_ripe_median(
                        p("ripe_median_thermal_age_dd"),
                        seed_index=cohort.seed_index,
                        reference_index=p("source_response_reference_index"),
                        response=p("seed_index_weight_response"),
                        shift_scale_dd=p("seed_maturity_shift_scale_dd"),
                    ),
                    width_dd=p("ripe_distribution_width_dd"),
                )
                delta_fraction = max(0.0, ripe_fraction - prior_fraction)
                growth_fraction = fruit_growth_fraction(
                    cohort.thermal_age_dd,
                    curve=fruit_growth_curve,
                    stage1_midpoint_dd=p("double_sigmoid_stage1_midpoint_dd"),
                    stage2_midpoint_dd=p("double_sigmoid_stage2_midpoint_dd"),
                    width_dd=p("double_sigmoid_width_dd"),
                    final_age_dd=p("ripe_median_thermal_age_dd"),
                )
                source_modifier = max(
                    0.0,
                    min(
                        1.0,
                        p("fruit_growth_source_memory_weight") * cohort.source_modifier
                        + p("fruit_growth_daily_source_weight") * balance.sufficiency,
                    ),
                )
                berry_weight = berry_weight_potential_g(
                    p("potential_berry_weight_g"),
                    growth_fraction=growth_fraction,
                    source_modifier=source_modifier,
                    source_reference_index=p("source_response_reference_index"),
                    source_response=p("berry_weight_source_response"),
                    seed_index=cohort.seed_index,
                    seed_response=p("seed_index_weight_response"),
                )
                cohort.potential_berry_weight_g = berry_weight
                cohort.development_stage = _fruit_stage(cohort.thermal_age_dd, p)
                amount_per_plant = newly_mature_mass_kg(
                    cohort.fruit_number,
                    berry_weight,
                    delta_fraction,
                    p("marketable_fraction"),
                    1.0,
                )
                amount = amount_per_plant * (
                    request.productive_area_mu * request.plant_structure.plant_density_per_mu
                )
                newly_mature_today += amount
                newly_mature_today_per_plant += amount_per_plant
                cohort.ripe_mass_kg += amount
                cohort.ripe_mass_kg_per_plant += amount_per_plant
                cohort.previous_ripe_fraction = ripe_fraction
                cohort.source_modifier = source_modifier
                if delta_fraction > 0:
                    trace["WHY_MATURITY_ADVANCED_OR_DELAYED"].append(
                        f"{cohort.cohort_id}:{current_day.isoformat()};thermal_age_dd={cohort.thermal_age_dd:.6f};delta={delta_fraction:.8f}"
                    )
        if fruit_set_today:
            fruit_set_seen = True
        if newly_mature_today > 0.0:
            mature_seen = True
        stage = (
            state_from_progress(
                forcing_dd=forcing_total,
                bloom_progress=bloom_progress,
                bud_swell_dd=p("bud_swell_forcing_dd"),
                bud_break_dd=p("bud_break_forcing_dd"),
                bloom_start_dd=p("bloom_start_forcing_dd"),
                fruit_set_seen=fruit_set_seen,
                mature_seen=mature_seen,
            )
            if forcing_total >= p("bud_swell_forcing_dd")
            else stage
        )
        reserve = update_reserve_index(
            reserve,
            source_supply=balance.source_supply,
            fruit_demand=total_fruit,
            vegetative_demand=vigor,
            storage_demand=p("storage_sink_strength"),
            gain_rate=p("postharvest_reserve_gain"),
            maintenance_cost=p("reserve_maintenance_cost"),
            fruit_demand_cost=p("reserve_fruit_demand_cost"),
            other_demand_cost=p("reserve_other_demand_cost"),
        )
        vigor = min(
            1.0,
            max(
                0.0,
                vigor
                + p("shoot_growth_cost") * balance.sufficiency
                - p("daily_vigor_maintenance_cost") * (1.0 - balance.sufficiency),
            ),
        )
        daily_mature.append((current_day, newly_mature_today))
        daily_mature_per_plant.append((current_day, newly_mature_today_per_plant))
        daily_states.append(
            PlantStatePoint(
                day=current_day,
                reserve_index=reserve,
                vigor_index=vigor,
                leaf_area_index=structure.leaf_area_index,
                productive_canes=structure.productive_canes,
                productive_shoots_per_plant=structure.productive_shoots,
                fruiting_wood_index=structure.fruiting_wood_index,
                vegetative_shoot_potential=structure.vegetative_shoot_potential,
                flower_bud_potential_per_plant=flower_bud_potential,
                flower_load_per_plant=flower_load,
                fruit_load_per_plant=total_fruit,
                source_supply_index=balance.source_supply,
                sink_demand_index=balance.sink_demand,
                source_sink_sufficiency=balance.sufficiency,
                phenology_stage=stage,
                dormancy_state=(
                    "NOT_APPLICABLE"
                    if production_system is ProductionSystem.EVERGREEN
                    else "RELEASED"
                    if dormancy_released
                    else "CHILL_ACCUMULATING"
                    if acclimation_signal >= p("acclimation_start_signal_days")
                    else "ENDO_DORMANT"
                ),
                chill_accumulation=chill.total,
                forcing_accumulation=forcing_total,
                bloom_progress=bloom_progress,
                new_mature_kg=newly_mature_today,
                new_mature_kg_per_plant=newly_mature_today_per_plant,
            )
        )
        last_stage = stage
        if newly_mature_today > 0:
            trace["WHY_YIELD_CHANGED"].append(
                f"{current_day.isoformat()}:maturity distribution x fruit count "
                "x berry mass x marketable fraction x area-scaled plant count"
            )
        yield daily_states[-1]

    bloom_cohort_outputs = tuple(
        BloomCohortOutput(
            cohort_id=item.cohort_id,
            origin_date=item.origin_date,
            flower_quantity_per_plant=item.flower_quantity,
        )
        for item in cohorts
    )
    fruit_set_cohort_outputs = tuple(
        FruitSetCohortOutput(
            cohort_id=f"{item.cohort_id}-SET",
            origin_bloom_cohort_id=item.cohort_id,
            fruit_set_date=item.fruit_set_date,
            effective_pollinated_flowers_per_plant=item.effective_pollinated_flowers,
            fruit_number_per_plant=item.fruit_number,
        )
        for item in cohorts
        if item.fruit_set_date is not None
    )
    fruit_development_cohort_outputs = tuple(
        FruitDevelopmentCohortOutput(
            cohort_id=f"{item.cohort_id}-FRUIT",
            origin_bloom_cohort_id=item.cohort_id,
            origin_fruit_set_cohort_id=f"{item.cohort_id}-SET",
            fruit_set_date=item.fruit_set_date,
            fruit_quantity_per_plant=item.fruit_number,
            development_stage=item.development_stage,
            seed_effect_index=item.seed_index,
            thermal_age_degree_days=item.thermal_age_dd,
            source_sink_modifier=item.source_modifier,
            cumulative_ripe_fraction=item.previous_ripe_fraction,
            potential_berry_weight_g=item.potential_berry_weight_g,
            ripe_mass_kg=item.ripe_mass_kg,
            ripe_mass_kg_per_plant=item.ripe_mass_kg_per_plant,
        )
        for item in cohorts
        if item.fruit_set_date is not None
    )
    carryover = carryover_state(
        reserve_index=reserve,
        vigor_index=vigor,
        crop_load_index=crop_load_index(
            sum(item.fruit_number for item in cohorts),
            structure.productive_shoots,
            p("crop_load_saturation_fruit_per_shoot"),
        ),
        reserve_carryover_fraction=p("reserve_carryover_fraction"),
        vigor_carryover_fraction=p("vigor_carryover_fraction"),
        vigor_crop_load_penalty=p("carryover_vigor_crop_load_penalty"),
        reserve_crop_load_penalty=p("carryover_reserve_crop_load_penalty"),
        bud_crop_load_penalty=p("carryover_bud_crop_load_penalty"),
        reserve_bud_contribution=p("reserve_bud_contribution"),
    )
    aged_canes = age_cane_cohorts(request.plant_structure)
    interseason = InterSeasonOutput(
        postharvest_vigor_proxy=carryover["postharvest_vigor_proxy"],
        carbohydrate_reserve_proxy=carryover["carbohydrate_reserve_proxy"],
        next_season_flower_bud_potential=carryover["next_season_flower_bud_potential"],
        next_cane_age_structure=aged_canes,
    )
    canonical_request = replace(
        request,
        management_events=tuple(
            sorted(request.management_events, key=lambda item: (item.event_datetime, item.event_id))
        ),
    )
    return SimulationOutput(
        simulation_id=request.simulation_id,
        model_version="THEORETICAL_BLUEBERRY_GROWTH_MODEL_V1",
        simulation_input_sha256=sha256_hex(canonical_request),
        parameter_set_id=request.parameter_set.parameter_set_id,
        parameter_set_sha256=sha256_hex(request.parameter_set),
        cultivar_id=request.cultivar.cultivar_id,
        production_system=request.production_system,
        productive_area_mu=request.productive_area_mu,
        plant_density_per_mu=request.plant_structure.plant_density_per_mu,
        chill_model=chill_model,
        fruit_growth_curve=fruit_growth_curve,
        daily_states=tuple(daily_states),
        bloom_cohorts=bloom_cohort_outputs,
        fruit_set_cohorts=fruit_set_cohort_outputs,
        fruit_development_cohorts=fruit_development_cohort_outputs,
        daily_newly_mature_quantity_kg=tuple(daily_mature),
        daily_newly_mature_quantity_kg_per_plant=tuple(daily_mature_per_plant),
        interseason_state=interseason,
        trace={key: tuple(value) for key, value in trace.items()},
    )


def _validate_request(request: SimulationInput) -> None:
    if (
        not math.isfinite(request.productive_area_mu)
        or not math.isfinite(request.plant_structure.plant_density_per_mu)
        or request.productive_area_mu <= 0
        or request.plant_structure.plant_density_per_mu <= 0
    ):
        raise ValueError("Positive productive area and plant density are required")
    structure = request.plant_structure
    if any(
        not math.isfinite(value) or value < 0.0
        for value in (
            structure.leaf_area_index,
            structure.productive_shoots_per_plant,
            structure.fruiting_wood_index,
        )
    ) or any(
        cane.age_years < 0
        or not math.isfinite(cane.cane_count)
        or cane.cane_count < 0.0
        or not 0.0 <= cane.productive_fraction <= 1.0
        for cane in structure.canes
    ):
        raise ValueError(
            "Plant structure values must be finite and nonnegative with valid fractions"
        )
    if request.environment_mode not in {
        "OBSERVED_OR_SUPPLIED_MICROCLIMATE",
        "THEORETICAL_SCENARIO_MICROCLIMATE",
    }:
        raise ValueError("Unknown microclimate input mode")
    if not request.environment:
        raise ValueError("At least one hourly environment observation is required")
    if not request.cultivar.cultivar_id or not request.cultivar.blueberry_type:
        raise ValueError("Cultivar identity and blueberry type are required")
    if request.production_system is ProductionSystem.EVERGREEN:
        if request.cultivar.evergreen_dormancy_bypass is not True:
            raise ValueError(
                "Evergreen pathway requires explicit cultivar-scoped dormancy behavior; "
                "no universal zero-chill assumption is available"
            )
    elif request.cultivar.evergreen_dormancy_bypass is not None:
        raise ValueError("Evergreen dormancy binding is only valid for EVERGREEN systems")
    if (
        not math.isfinite(request.initial_state.flower_bud_potential_per_plant)
        or request.initial_state.flower_bud_potential_per_plant < 0.0
    ):
        raise ValueError("Initial flower-bud potential must be finite and nonnegative")
    if not 0.0 <= request.initial_state.prior_crop_load_index <= 1.0:
        raise ValueError("Prior crop-load index must be in [0,1]")
    for observation in request.environment:
        numeric_values = (
            observation.air_temperature_c,
            observation.relative_humidity_pct,
            observation.root_zone_temperature_c,
            observation.radiation_index,
            observation.photoperiod_hours,
        )
        if any(value is not None and not math.isfinite(value) for value in numeric_values):
            raise ValueError("Environment observations must be finite")
        if (
            observation.relative_humidity_pct is not None
            and not 0.0 <= observation.relative_humidity_pct <= 100.0
        ):
            raise ValueError("Relative humidity must be in [0,100] percent")
        if (
            observation.radiation_index is not None
            and not 0.0 <= observation.radiation_index <= 1.0
        ):
            raise ValueError("Radiation index must be in [0,1]")
        if (
            observation.photoperiod_hours is not None
            and not 0.0 <= observation.photoperiod_hours <= 24.0
        ):
            raise ValueError("Photoperiod must be in [0,24] hours")
    timestamps = [item.timestamp for item in request.environment]
    if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
        raise ValueError("Hourly environment must be strictly ordered without duplicates")
    for before, after in zip(timestamps, timestamps[1:], strict=False):
        if after - before != timedelta(hours=1):
            raise ValueError("Environment time series must have contiguous hourly observations")
    hours_by_day: dict[date, list[datetime]] = defaultdict(list)
    for timestamp in timestamps:
        hours_by_day[timestamp.date()].append(timestamp)
    if any(
        len(day_timestamps) != 24
        or day_timestamps[0].hour != 0
        or day_timestamps[-1].hour != 23
        or any(item.minute or item.second or item.microsecond for item in day_timestamps)
        for day_timestamps in hours_by_day.values()
    ):
        raise ValueError("Each simulated calendar day requires 24 complete hourly observations")
    values = (
        request.initial_state.reserve_index,
        request.initial_state.vigor_index,
        request.initial_state.canopy_health_index,
        request.initial_state.leaf_retention_ratio,
    )
    if any(not 0.0 <= value <= 1.0 for value in values):
        raise ValueError("Normalized initial plant indices must be in [0,1]")
    if any(
        event.observed_or_planned not in {"OBSERVED", "PLANNED"}
        for event in request.management_events
    ):
        raise ValueError("Management events must be declared observed or planned")
    event_ids = [event.event_id for event in request.management_events]
    if any(not event_id for event_id in event_ids) or len(set(event_ids)) != len(event_ids):
        raise ValueError("Management event IDs must be nonempty and unique")
    intensity_required = {
        EventType.POSTHARVEST_PRUNING,
        EventType.SUMMER_PRUNING,
        EventType.DORMANT_PRUNING,
        EventType.WINTER_PRUNING,
        EventType.PRUNING,
        EventType.CANE_RENEWAL,
        EventType.FRUITING_WOOD_THINNING,
        EventType.FLOWER_BUD_THINNING,
        EventType.FLOWER_REMOVAL,
        EventType.FLOWER_THINNING,
        EventType.FRUITLET_THINNING,
        EventType.FRUIT_THINNING,
        EventType.DEFOLIATION,
        EventType.LEAF_RETENTION_MANAGEMENT,
        EventType.SHADE_START,
        EventType.SHADE_APPLICATION,
        EventType.DORMANCY_BREAK_TREATMENT,
    }
    if any(
        event.event_type in intensity_required and event.intensity is None
        for event in request.management_events
    ):
        raise ValueError("Management interventions requiring intensity must declare it")
    if any(
        event.event_type in intensity_required
        and event.intensity is not None
        and not 0.0 <= event.intensity <= 1.0
        for event in request.management_events
    ):
        raise ValueError("S3 management intensity must be a fraction in [0,1]")
    if any(
        event.intensity is not None and event.intensity_unit != "fraction_0_1"
        for event in request.management_events
    ):
        raise ValueError("S3 management intensity unit must be fraction_0_1")


def _temperature_suitability(temperature: float, low: float, high: float) -> float:
    if low >= high:
        raise ValueError("Temperature stress bounds must be ordered")
    if temperature < low:
        return max(0.0, temperature / low) if low > 0 else 0.0
    if temperature <= high:
        return 1.0
    return max(0.0, 1.0 - (temperature - high) / max(high - low, 1e-12))


def _fruit_stage(thermal_age_dd: float, get: Callable[[str], float]) -> str:
    if thermal_age_dd < get("double_sigmoid_stage1_midpoint_dd"):
        return "STAGE_I"
    if thermal_age_dd < get("double_sigmoid_stage2_midpoint_dd"):
        return "STAGE_II"
    if thermal_age_dd < get("ripe_median_thermal_age_dd"):
        return "STAGE_III"
    return "COLOR_BREAK"
