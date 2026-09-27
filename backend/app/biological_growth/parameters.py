"""Explicit scenario parameters; there is intentionally no production default set."""

from __future__ import annotations

import math

from .schemas import Parameter, ParameterAuthority, ParameterSet

_DYNAMIC_LITERATURE_PRIORS: dict[str, tuple[float, str]] = {
    "dynamic_model_e0": (4153.5, "kelvin_energy_parameter"),
    "dynamic_model_e1": (12888.8, "kelvin_energy_parameter"),
    "dynamic_model_a0": (139500.0, "model_rate_constant"),
    "dynamic_model_a1": (2.567e18, "model_rate_constant"),
    "dynamic_model_slope": (1.6, "dimensionless"),
    "dynamic_model_tf_kelvin": (277.0, "kelvin"),
}


def reference_parameter_set(
    overrides: dict[str, float] | None = None,
    *,
    chill_model: str = "UNBOUND",
) -> ParameterSet:
    """Create a synthetic reference set whose values are never production parameters.

    Values are transparent model assumptions chosen for executable golden scenarios,
    not calibrated Yunnan constants and not claims of cultivar-specific truth.
    """
    values: dict[str, tuple[float, str]] = {
        "chill_requirement": (260.0, "model_units_for_selected_chill_model"),
        "forcing_base_temperature_c": (5.0, "degC"),
        "forcing_upper_temperature_c": (28.0, "degC"),
        "bud_swell_forcing_dd": (70.0, "degC_day"),
        "bud_break_forcing_dd": (125.0, "degC_day"),
        "bloom_start_forcing_dd": (180.0, "degC_day"),
        "bloom_duration_dd": (45.0, "degC_day"),
        "fruit_set_lag_dd": (15.0, "degC_day"),
        "flower_bud_response_strength": (0.65, "fraction"),
        "day_neutral_genotype": (0.0, "boolean_as_float"),
        "flower_bud_photoperiod_reference_h": (13.0, "hours"),
        "flower_bud_photoperiod_span_h": (7.0, "hours"),
        "flower_bud_temperature_reference_c": (30.0, "degC"),
        "flower_bud_temperature_span_c": (18.0, "degC"),
        "flower_bud_photoperiod_weight": (0.40, "fraction"),
        "flower_bud_thermal_weight": (0.25, "fraction"),
        "flower_bud_vigor_weight": (0.20, "fraction"),
        "flower_bud_reserve_weight": (0.15, "fraction"),
        "flower_bud_previous_load_penalty": (0.25, "fraction"),
        "flower_bud_induction_threshold": (2.0, "signal_days"),
        "flower_bud_increment_per_signal": (0.05, "buds_per_plant_per_signal_day"),
        "acclimation_photoperiod_threshold_h": (11.5, "hours"),
        "acclimation_temperature_threshold_c": (20.0, "degC"),
        "acclimation_start_signal_days": (10.0, "signal_days"),
        "acclimation_dormancy_signal_days": (20.0, "signal_days"),
        "dormancy_treatment_chill_requirement_reduction_fraction": (
            0.50,
            "fraction_scenario_only",
        ),
        "pruning_bud_loss_fraction": (0.35, "fraction_of_intensity"),
        "pruning_cane_loss_fraction": (0.35, "fraction_of_intensity"),
        "pruning_shoot_loss_fraction": (0.25, "fraction_of_intensity"),
        "stage_sink_fruit_set": (0.35, "relative_sink_weight"),
        "stage_sink_stage_i": (0.75, "relative_sink_weight"),
        "stage_sink_stage_ii": (0.55, "relative_sink_weight"),
        "stage_sink_stage_iii": (1.0, "relative_sink_weight"),
        "stage_sink_color_break": (0.65, "relative_sink_weight"),
        "stage_sink_ripe": (0.20, "relative_sink_weight"),
        "fruit_growth_source_memory_weight": (0.70, "fraction"),
        "fruit_growth_daily_source_weight": (0.30, "fraction"),
        "source_response_reference_index": (0.50, "normalized_index"),
        "fruit_set_source_base_weight": (0.70, "fraction"),
        "fruit_set_source_response_weight": (0.30, "fraction"),
        "seed_maturity_shift_scale_dd": (100.0, "degC_day_per_seed_index"),
        "reserve_fruit_demand_cost": (0.0005, "index_per_fruit_unit_day"),
        "reserve_other_demand_cost": (0.01, "index_per_demand_unit_day"),
        "daily_vigor_maintenance_cost": (0.002, "index_per_day"),
        "carryover_vigor_crop_load_penalty": (0.15, "fraction"),
        "carryover_reserve_crop_load_penalty": (0.20, "fraction"),
        "carryover_bud_crop_load_penalty": (0.25, "fraction"),
        "crop_load_saturation_fruit_per_shoot": (8.0, "fruit_per_shoot_scenario_index_scale"),
        "reserve_mobilization_fraction": (0.12, "fraction_per_day"),
        "postharvest_reserve_gain": (0.004, "index_per_day"),
        "reserve_maintenance_cost": (0.001, "index_per_day"),
        "shoot_growth_cost": (0.002, "index_per_day"),
        "pruning_regrowth_gain": (0.06, "shoots_per_plant"),
        "pruning_leaf_loss_fraction": (0.45, "fraction_of_intensity"),
        "pruning_wood_loss_fraction": (0.62, "fraction_of_intensity"),
        "pollination_baseline_index": (0.65, "fraction"),
        "pollinator_event_increment": (0.18, "fraction"),
        "temperature_stress_low_c": (3.0, "degC"),
        "temperature_stress_high_c": (34.0, "degC"),
        "fruit_set_maximum": (0.82, "fraction"),
        "source_light_half_saturation": (0.45, "normalized_index"),
        "fruit_sink_strength": (0.02, "index_per_stage_weighted_fruit_unit"),
        "vegetative_sink_strength": (0.05, "index_per_vigor_unit"),
        "root_growth_sink_strength": (0.06, "index_per_vigor_unit"),
        "storage_sink_strength": (0.08, "index"),
        "source_sink_floor": (0.10, "fraction"),
        "source_sink_ceiling": (1.0, "fraction"),
        "potential_berry_weight_g": (1.8, "g_per_berry"),
        "berry_weight_source_response": (0.35, "fraction"),
        "seed_index_weight_response": (0.04, "fraction"),
        "marketable_fraction": (0.88, "fraction"),
        "development_base_temperature_c": (4.0, "degC"),
        "ripe_median_thermal_age_dd": (430.0, "degC_day"),
        "ripe_distribution_width_dd": (55.0, "degC_day"),
        "double_sigmoid_stage1_midpoint_dd": (110.0, "degC_day"),
        "double_sigmoid_stage2_midpoint_dd": (300.0, "degC_day"),
        "double_sigmoid_width_dd": (35.0, "degC_day"),
        "microclimate_closure_delta_c": (1.5, "degC_scenario_only"),
        "microclimate_heating_delta_c": (3.0, "degC_scenario_only"),
        "microclimate_shade_fraction": (0.70, "fraction_scenario_only"),
        "radiation_reference_index": (0.50, "normalized_index_scenario_only"),
        "evergreen_flower_bud_rate": (0.004, "buds_per_plant_per_day"),
        "reserve_carryover_fraction": (0.72, "fraction"),
        "vigor_carryover_fraction": (0.70, "fraction"),
        "reserve_bud_contribution": (0.20, "index_per_reserve_index"),
        "cane_productivity_juvenile_weight": (0.75, "relative_index"),
        "cane_productivity_mature_weight": (1.0, "relative_index"),
        "cane_productivity_old_weight": (0.60, "relative_index"),
        "cane_mature_age_years": (2.0, "years"),
        "cane_old_age_years": (5.0, "years"),
    }
    values.update(_DYNAMIC_LITERATURE_PRIORS)
    if overrides:
        for name, value in overrides.items():
            if name not in values:
                raise KeyError(f"Unknown reference parameter {name}")
            values[name] = (value, values[name][1])
    parameters = tuple(
        Parameter(
            parameter_id=f"S3-{authority.value}-{name.upper()}",
            name=name,
            value=value,
            unit=unit,
            authority=authority,
            source_id=("M003;M004" if authority is ParameterAuthority.LITERATURE_PRIOR else None),
            cultivar_scope=(
                "GENERIC_DYNAMIC_MODEL_ORIGIN_NOT_BLUEBERRY_VALIDATED"
                if authority is ParameterAuthority.LITERATURE_PRIOR
                else "REFERENCE_SCENARIO_ONLY"
            ),
            system_scope=(
                "GENERIC_DORMANCY_MODEL_NOT_PRODUCTION_DEFAULT"
                if authority is ParameterAuthority.LITERATURE_PRIOR
                else "REFERENCE_SCENARIO_ONLY"
            ),
            lifecycle=(
                "LITERATURE_PRIOR_NOT_PRODUCTION_PARAMETER"
                if authority is ParameterAuthority.LITERATURE_PRIOR
                else "UNVALIDATED_THEORETICAL_SCENARIO"
            ),
            production_eligible=False,
        )
        for name, (value, unit) in sorted(values.items())
        for authority in [
            ParameterAuthority.LITERATURE_PRIOR
            if name in _DYNAMIC_LITERATURE_PRIORS
            else ParameterAuthority.MODEL_ASSUMPTION
        ]
    )
    return ParameterSet(
        parameter_set_id=f"S3-REFERENCE-{chill_model}-R1",
        parameters=parameters,
        scenario_only=True,
    )


def validate_parameter_set(parameter_set: ParameterSet) -> None:
    names = [parameter.name for parameter in parameter_set.parameters]
    if len(names) != len(set(names)):
        raise ValueError("Parameter names must be unique")
    if any(parameter.production_eligible for parameter in parameter_set.parameters):
        raise ValueError("S3 reference parameters cannot be production eligible")
    if not parameter_set.scenario_only:
        raise ValueError("S3 requires an explicitly scenario-only ParameterSet")
    if any(
        parameter.value is not None and not math.isfinite(parameter.value)
        for parameter in parameter_set.parameters
    ):
        raise ValueError("S3 parameters must be finite")
    if any(
        parameter.authority is ParameterAuthority.LITERATURE_PRIOR
        and (not parameter.source_id or "NOT_PRODUCTION" not in parameter.lifecycle)
        for parameter in parameter_set.parameters
    ):
        raise ValueError("Literature priors must retain source and non-production lifecycle")

    for parameter in parameter_set.parameters:
        value = parameter.value
        if value is None:
            continue
        unit = parameter.unit.lower()
        if (
            unit in {"fraction", "fraction_scenario_only", "boolean_as_float"}
            or unit.startswith("fraction_of_")
            or unit == "normalized_index"
        ) and not 0.0 <= value <= 1.0:
            raise ValueError(f"fraction parameter {parameter.name} must be in [0,1]")
        if not unit.startswith("degc") and not unit.startswith("k_minus_degc") and value < 0.0:
            raise ValueError(f"non-temperature parameter {parameter.name} cannot be negative")

    values_by_name = {parameter.name: parameter.value for parameter in parameter_set.parameters}
    forcing_base = values_by_name.get("forcing_base_temperature_c")
    forcing_upper = values_by_name.get("forcing_upper_temperature_c")
    if forcing_base is not None and forcing_upper is not None and forcing_upper <= forcing_base:
        raise ValueError("forcing upper temperature must exceed forcing base temperature")
    stress_low = values_by_name.get("temperature_stress_low_c")
    stress_high = values_by_name.get("temperature_stress_high_c")
    if stress_low is not None and stress_high is not None and stress_high <= stress_low:
        raise ValueError("temperature stress high bound must exceed low bound")
    source_floor = values_by_name.get("source_sink_floor")
    source_ceiling = values_by_name.get("source_sink_ceiling")
    if source_floor is not None and source_ceiling is not None and source_ceiling < source_floor:
        raise ValueError("source-sink ceiling must be greater than or equal to floor")
    stage1 = values_by_name.get("double_sigmoid_stage1_midpoint_dd")
    stage2 = values_by_name.get("double_sigmoid_stage2_midpoint_dd")
    ripe_median = values_by_name.get("ripe_median_thermal_age_dd")
    if stage1 is not None and stage2 is not None and ripe_median is not None:
        if not 0.0 < stage1 < stage2 < ripe_median:
            raise ValueError("fruit development thermal stages must be strictly ordered")
    mature_age = values_by_name.get("cane_mature_age_years")
    old_age = values_by_name.get("cane_old_age_years")
    if mature_age is not None and old_age is not None and old_age <= mature_age:
        raise ValueError("old cane age must exceed mature cane age")
