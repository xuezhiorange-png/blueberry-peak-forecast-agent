from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from backend.app.biological_growth.canonical import canonical_json_bytes, sha256_hex
from backend.app.biological_growth.dormancy import ChillAccumulator
from backend.app.biological_growth.engine import simulate as run_simulation
from backend.app.biological_growth.fruit_development import (
    berry_weight_potential_g,
    double_sigmoid_growth_fraction,
    fruit_growth_fraction,
    maturity_cumulative_fraction,
    seed_adjusted_ripe_median,
)
from backend.app.biological_growth.management import effective_radiation_index
from backend.app.biological_growth.parameters import reference_parameter_set
from backend.app.biological_growth.schemas import (
    ChillModel,
    EnvironmentHour,
    EventType,
    FruitGrowthCurve,
    ManagementEvent,
    SimulationInput,
    SimulationOutput,
)
from backend.app.biological_growth.structure import initial_structural_state
from backend.tests.biological_growth.scenario_factory import GOLDEN_DIR, build_scenario


def simulate(
    request: SimulationInput,
    *,
    chill_model: ChillModel = ChillModel.CHILL_HOURS,
    fruit_growth_curve: FruitGrowthCurve = FruitGrowthCurve.DOUBLE_LOGISTIC,
) -> SimulationOutput:
    """Golden tests must choose a chill candidate; production API has no default."""
    return run_simulation(request, chill_model=chill_model, fruit_growth_curve=fruit_growth_curve)


@pytest.mark.unit
@pytest.mark.parametrize(
    "scenario",
    [
        "deciduous-natural",
        "deciduous-forcing",
        "evergreen",
        "pruning-light",
        "pruning-heavy",
        "flower-thinning-none",
        "flower-thinning-moderate",
        "crop-load-low",
        "crop-load-high",
        "pollination-low",
        "pollination-high",
    ],
)
def test_golden_scenarios_replay_deterministically_and_conserve_state(scenario: str) -> None:
    first = simulate(build_scenario(scenario))
    second = simulate(build_scenario(scenario))
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert first.fruit_growth_curve is FruitGrowthCurve.DOUBLE_LOGISTIC
    assert first.model_version == "THEORETICAL_BLUEBERRY_GROWTH_MODEL_V1"
    assert first.simulation_input_sha256 == sha256_hex(build_scenario(scenario))
    assert first.parameter_set_id == build_scenario(scenario).parameter_set.parameter_set_id
    assert len(first.parameter_set_sha256) == 64
    assert len(first.daily_states) == 330
    assert all(point.new_mature_kg >= 0.0 for point in first.daily_states)
    assert all(0.0 <= point.source_sink_sufficiency <= 1.0 for point in first.daily_states)
    assert all(
        0.0 <= cohort.cumulative_ripe_fraction <= 1.0 for cohort in first.fruit_development_cohorts
    )
    assert all(
        cohort.fruit_number_per_plant <= cohort.effective_pollinated_flowers_per_plant + 1e-12
        for cohort in first.fruit_set_cohorts
    )
    bloom_by_id = {cohort.cohort_id: cohort for cohort in first.bloom_cohorts}
    assert all(
        cohort.effective_pollinated_flowers_per_plant
        <= bloom_by_id[cohort.origin_bloom_cohort_id].flower_quantity_per_plant + 1e-12
        for cohort in first.fruit_set_cohorts
    )
    assert sum(value for _, value in first.daily_newly_mature_quantity_kg) == pytest.approx(
        sum(cohort.ripe_mass_kg for cohort in first.fruit_development_cohorts)
    )
    assert sum(
        value for _, value in first.daily_newly_mature_quantity_kg_per_plant
    ) == pytest.approx(
        sum(cohort.ripe_mass_kg_per_plant for cohort in first.fruit_development_cohorts)
    )
    assert sum(value for _, value in first.daily_newly_mature_quantity_kg) == pytest.approx(
        sum(value for _, value in first.daily_newly_mature_quantity_kg_per_plant)
        * first.productive_area_mu
        * first.plant_density_per_mu
    )
    assert set(first.trace) == {
        "WHY_BUD_BREAK_OCCURRED",
        "WHY_BLOOM_OCCURRED",
        "WHY_FRUIT_SET_CHANGED",
        "WHY_MATURITY_ADVANCED_OR_DELAYED",
        "WHY_YIELD_CHANGED",
        "WHICH_MANAGEMENT_EVENT_AFFECTED_WHICH_STATE",
    }
    bloom_ids = {cohort.cohort_id for cohort in first.bloom_cohorts}
    fruit_set_ids = {cohort.cohort_id for cohort in first.fruit_set_cohorts}
    assert all(cohort.origin_bloom_cohort_id in bloom_ids for cohort in first.fruit_set_cohorts)
    assert all(
        cohort.origin_bloom_cohort_id in bloom_ids
        and cohort.origin_fruit_set_cohort_id in fruit_set_ids
        for cohort in first.fruit_development_cohorts
    )


def test_golden_manifest_has_all_required_synthetic_counterfactuals() -> None:
    manifest = json.loads((GOLDEN_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["production_parameter"] is False
    assert len(manifest["scenarios"]) == 11
    assert all((GOLDEN_DIR / f"{name}.json").is_file() for name in manifest["scenarios"])


def test_evergreen_uses_independent_non_chill_path() -> None:
    result = simulate(build_scenario("evergreen"))
    assert all(point.chill_accumulation == 0.0 for point in result.daily_states)
    assert all(point.dormancy_state == "NOT_APPLICABLE" for point in result.daily_states)
    assert any(point.bloom_progress > 0.0 for point in result.daily_states)
    assert all(
        point.phenology_stage not in {"DORMANT", "CHILL_ACCUMULATING", "CHILL_SATISFIED"}
        for point in result.daily_states
    )
    assert any(
        "explicit cultivar-scoped evergreen bypass" in item
        for item in result.trace["WHY_BUD_BREAK_OCCURRED"]
    )


def test_evergreen_requires_explicit_cultivar_scoped_dormancy_binding() -> None:
    request = build_scenario("evergreen")
    unresolved = replace(
        request, cultivar=replace(request.cultivar, evergreen_dormancy_bypass=None)
    )
    with pytest.raises(ValueError, match="no universal zero-chill assumption"):
        simulate(unresolved)


def test_initial_flower_bud_potential_must_be_finite() -> None:
    request = build_scenario("deciduous-natural")
    invalid = replace(
        request,
        initial_state=replace(request.initial_state, flower_bud_potential_per_plant=float("nan")),
    )
    with pytest.raises(ValueError, match="finite and nonnegative"):
        simulate(invalid)


def test_management_intensity_requires_declared_fraction_unit() -> None:
    request = build_scenario("pruning-light")
    invalid_event = replace(request.management_events[0], intensity_unit="percent")
    invalid = replace(request, management_events=(invalid_event,))
    with pytest.raises(ValueError, match="fraction_0_1"):
        simulate(invalid)


def test_insufficient_chill_does_not_enter_standard_deciduous_forcing_path() -> None:
    request = build_scenario("deciduous-natural", chill_requirement=10000.0)
    result = simulate(request)
    assert not any(point.bloom_progress > 0.0 for point in result.daily_states)
    assert max(point.forcing_accumulation for point in result.daily_states) == 0.0
    assert not any(point.dormancy_state == "RELEASED" for point in result.daily_states)


def test_dormancy_treatment_uses_only_an_explicit_scenario_gate_modifier() -> None:
    request = build_scenario("deciduous-natural", chill_requirement=10_000.0)
    parameters = reference_parameter_set(
        {
            "chill_requirement": 10_000.0,
            "dormancy_treatment_chill_requirement_reduction_fraction": 0.90,
        }
    )
    treatment = ManagementEvent(
        event_id="synthetic-dormancy-treatment",
        event_type=EventType.DORMANCY_BREAK_TREATMENT,
        event_datetime=request.environment[0].timestamp,
        intensity=1.0,
        intensity_unit="fraction_0_1",
        observed_or_planned="PLANNED",
        source_reference="SYNTHETIC_COUNTERFACTUAL;C014_EVENT_AUTHORITY",
        target="SYNTHETIC_BUDS",
    )
    treated = simulate(
        replace(
            request,
            parameter_set=parameters,
            management_events=(treatment,),
        )
    )
    assert any(point.dormancy_state == "RELEASED" for point in treated.daily_states)
    assert any(point.forcing_accumulation > 0.0 for point in treated.daily_states)
    assert any(
        "scenario treatment-adjusted release gate" in item
        for item in treated.trace["WHY_BUD_BREAK_OCCURRED"]
    )
    assert (
        "not a production treatment recommendation"
        in treated.trace["WHICH_MANAGEMENT_EVENT_AFFECTED_WHICH_STATE"][0]
    )


def test_heating_changes_microclimate_driven_timing_not_a_calendar_offset() -> None:
    natural_request = build_scenario("deciduous-natural")
    natural = simulate(natural_request)
    forced_request = build_scenario("deciduous-forcing")
    forced = simulate(replace(forced_request, production_system=natural_request.production_system))
    natural_bloom = next(point.day for point in natural.daily_states if point.bloom_progress > 0.0)
    forced_bloom = next(point.day for point in forced.daily_states if point.bloom_progress > 0.0)
    assert forced_bloom < natural_bloom
    assert forced.trace["WHICH_MANAGEMENT_EVENT_AFFECTED_WHICH_STATE"]
    assert forced.trace["WHY_BLOOM_OCCURRED"]


def test_pruning_and_flower_thinning_change_different_state_paths() -> None:
    light = simulate(build_scenario("pruning-light"))
    heavy = simulate(build_scenario("pruning-heavy"))
    assert heavy.daily_states[-1].leaf_area_index < light.daily_states[-1].leaf_area_index
    assert heavy.daily_states[-1].productive_canes < light.daily_states[-1].productive_canes
    assert any(
        "future_vegetative_shoot_potential" in item
        for item in heavy.trace["WHICH_MANAGEMENT_EVENT_AFFECTED_WHICH_STATE"]
    )

    unthinned = simulate(build_scenario("flower-thinning-none"))
    thinned = simulate(build_scenario("flower-thinning-moderate"))
    assert sum(c.fruit_number_per_plant for c in thinned.fruit_set_cohorts) < sum(
        c.fruit_number_per_plant for c in unthinned.fruit_set_cohorts
    )
    assert thinned.daily_states[-1].leaf_area_index == unthinned.daily_states[-1].leaf_area_index
    assert sum(c.potential_berry_weight_g for c in thinned.fruit_development_cohorts) / len(
        thinned.fruit_development_cohorts
    ) > sum(c.potential_berry_weight_g for c in unthinned.fruit_development_cohorts) / len(
        unthinned.fruit_development_cohorts
    )


def test_crop_load_competes_for_source_and_pollination_changes_set() -> None:
    low_load = simulate(build_scenario("crop-load-low"))
    high_load = simulate(build_scenario("crop-load-high"))
    assert (
        high_load.daily_states[-1].fruit_load_per_plant
        > low_load.daily_states[-1].fruit_load_per_plant
    )
    assert min(p.source_sink_sufficiency for p in high_load.daily_states) < min(
        p.source_sink_sufficiency for p in low_load.daily_states
    )
    assert (
        high_load.interseason_state.next_season_flower_bud_potential
        < low_load.interseason_state.next_season_flower_bud_potential
    )
    low_pollination = simulate(build_scenario("pollination-low"))
    high_pollination = simulate(build_scenario("pollination-high"))
    assert sum(c.fruit_number_per_plant for c in high_pollination.fruit_set_cohorts) > sum(
        c.fruit_number_per_plant for c in low_pollination.fruit_set_cohorts
    )
    assert sum(c.seed_effect_index for c in high_pollination.fruit_development_cohorts) > sum(
        c.seed_effect_index for c in low_pollination.fruit_development_cohorts
    )
    low_seed_weight = berry_weight_potential_g(
        1.8,
        growth_fraction=0.8,
        source_modifier=0.7,
        source_reference_index=0.5,
        source_response=0.35,
        seed_index=0.2,
        seed_response=0.04,
    )
    high_seed_weight = berry_weight_potential_g(
        1.8,
        growth_fraction=0.8,
        source_modifier=0.7,
        source_reference_index=0.5,
        source_response=0.35,
        seed_index=0.9,
        seed_response=0.04,
    )
    assert high_seed_weight > low_seed_weight
    assert seed_adjusted_ripe_median(
        430.0, seed_index=0.9, reference_index=0.5, response=0.04, shift_scale_dd=100.0
    ) < seed_adjusted_ripe_median(
        430.0, seed_index=0.2, reference_index=0.5, response=0.04, shift_scale_dd=100.0
    )


def test_all_chill_accumulators_are_repeatable_and_separate_from_release_state() -> None:
    temperatures = [-2.0, 1.0, 5.0, 8.0, 16.0, 20.0] * 240
    results: dict[ChillModel, tuple[float, float]] = {}
    parameters = reference_parameter_set()
    dynamic_constants = {
        name: parameters.get(name)
        for name in (
            "dynamic_model_e0",
            "dynamic_model_e1",
            "dynamic_model_a0",
            "dynamic_model_a1",
            "dynamic_model_slope",
            "dynamic_model_tf_kelvin",
        )
    }
    for model in ChillModel:
        constants = dynamic_constants if model is ChillModel.DYNAMIC_CHILL_PORTIONS else None
        accumulator = ChillAccumulator(model, constants)
        for temperature in temperatures:
            accumulator.add_hour(temperature)
        again = ChillAccumulator(model, constants)
        for temperature in temperatures:
            again.add_hour(temperature)
        results[model] = (accumulator.total, again.total)
        assert accumulator.total == again.total
    assert len({round(value[0], 8) for value in results.values()}) == 3


def test_simulation_outputs_remain_nonnegative_and_phenology_indices_are_bounded() -> None:
    result = simulate(build_scenario("deciduous-forcing"))
    for point in result.daily_states:
        assert point.reserve_index >= 0.0
        assert point.vigor_index >= 0.0
        assert point.leaf_area_index >= 0.0
        assert point.productive_canes >= 0.0
        assert point.productive_shoots_per_plant >= 0.0
        assert point.fruiting_wood_index >= 0.0
        assert point.vegetative_shoot_potential >= 0.0
        assert point.flower_bud_potential_per_plant >= 0.0
        assert point.flower_load_per_plant >= 0.0
        assert point.fruit_load_per_plant >= 0.0
        assert point.source_supply_index >= 0.0
        assert point.sink_demand_index >= 0.0
        assert 0.0 <= point.bloom_progress <= 1.0
        assert 0.0 <= point.source_sink_sufficiency <= 1.0
        assert point.new_mature_kg >= 0.0
    assert all(cohort.ripe_mass_kg >= 0.0 for cohort in result.fruit_development_cohorts)


def test_management_event_order_is_deterministic_and_unbound_actions_are_explicit() -> None:
    request = build_scenario("deciduous-forcing")
    forward = simulate(request)
    reversed_events = simulate(
        replace(request, management_events=tuple(reversed(request.management_events)))
    )
    assert canonical_json_bytes(forward) == canonical_json_bytes(reversed_events)

    nutrition_event = ManagementEvent(
        event_id="nutrition-unbound",
        event_type=EventType.NUTRITION_INTERVENTION,
        event_datetime=request.environment[0].timestamp,
        intensity=None,
        intensity_unit=None,
        observed_or_planned="PLANNED",
        source_reference="SYNTHETIC_TEST",
        target="SYNTHETIC",
    )
    result = simulate(
        replace(request, management_events=request.management_events + (nutrition_event,))
    )
    assert any(
        "NO_PHYSIOLOGICAL_EFFECT_BOUND_IN_S3" in trace
        for trace in result.trace["WHICH_MANAGEMENT_EVENT_AFFECTED_WHICH_STATE"]
    )


def test_double_sigmoid_and_maturity_distribution_are_monotone_bounded() -> None:
    ages = list(range(0, 801, 10))
    growth = [
        double_sigmoid_growth_fraction(
            float(age), stage1_midpoint_dd=110.0, stage2_midpoint_dd=300.0, width_dd=35.0
        )
        for age in ages
    ]
    maturity = [
        maturity_cumulative_fraction(float(age), median_dd=430.0, width_dd=55.0) for age in ages
    ]
    assert all(0.0 <= value <= 1.0 for value in growth + maturity)
    assert growth == sorted(growth)
    assert maturity == sorted(maturity)


@pytest.mark.parametrize("curve", list(FruitGrowthCurve))
def test_selectable_fruit_growth_curves_are_monotone_and_bounded(
    curve: FruitGrowthCurve,
) -> None:
    values = [
        fruit_growth_fraction(
            float(age),
            curve=curve,
            stage1_midpoint_dd=110.0,
            stage2_midpoint_dd=300.0,
            width_dd=35.0,
            final_age_dd=430.0,
        )
        for age in range(-10, 801, 10)
    ]
    assert all(0.0 <= value <= 1.0 for value in values)
    assert values == sorted(values)
    assert fruit_growth_fraction(
        800.0,
        curve=curve,
        stage1_midpoint_dd=110.0,
        stage2_midpoint_dd=300.0,
        width_dd=35.0,
        final_age_dd=430.0,
    ) == pytest.approx(1.0)


def test_stagewise_growth_rejects_invalid_boundaries() -> None:
    with pytest.raises(ValueError, match="strictly ordered"):
        fruit_growth_fraction(
            100.0,
            curve=FruitGrowthCurve.STAGEWISE_THERMAL,
            stage1_midpoint_dd=300.0,
            stage2_midpoint_dd=110.0,
            width_dd=35.0,
            final_age_dd=430.0,
        )


def test_simulator_rejects_partial_calendar_day_environment() -> None:
    request = build_scenario("deciduous-natural")
    with pytest.raises(ValueError, match="24 complete hourly observations"):
        simulate(replace(request, environment=request.environment[1:]))


def test_simulation_records_selected_theoretical_curve_and_chill_model() -> None:
    request = build_scenario("deciduous-natural")
    output = simulate(
        request,
        chill_model=ChillModel.UTAH_CHILL_UNITS,
        fruit_growth_curve=FruitGrowthCurve.DOUBLE_GOMPERTZ,
    )
    assert output.chill_model is ChillModel.UTAH_CHILL_UNITS
    assert output.fruit_growth_curve is FruitGrowthCurve.DOUBLE_GOMPERTZ
    assert output.parameter_set_id == request.parameter_set.parameter_set_id
    assert output.parameter_set_sha256 == sha256_hex(request.parameter_set)


def test_simulator_requires_explicit_chill_model_selection() -> None:
    request = build_scenario("deciduous-natural")
    with pytest.raises(TypeError, match="chill_model"):
        run_simulation(request)  # type: ignore[call-arg]


def test_area_scales_population_output_without_changing_per_plant_state() -> None:
    request = build_scenario("deciduous-natural")
    doubled = replace(request, productive_area_mu=2.0)
    first = simulate(request)
    second = simulate(doubled)
    assert (
        first.daily_states[-1].fruit_load_per_plant == second.daily_states[-1].fruit_load_per_plant
    )
    assert sum(x[1] for x in second.daily_newly_mature_quantity_kg) == pytest.approx(
        2.0 * sum(x[1] for x in first.daily_newly_mature_quantity_kg)
    )
    assert second.daily_newly_mature_quantity_kg_per_plant == (
        first.daily_newly_mature_quantity_kg_per_plant
    )
    assert sum(x[1] for x in first.daily_newly_mature_quantity_kg_per_plant) > 0.0


def test_nonfinite_or_production_parameter_sets_fail_closed() -> None:
    request = build_scenario("deciduous-natural")
    parameters = request.parameter_set
    invalid = replace(
        parameters,
        parameters=tuple(
            replace(item, value=float("nan")) if item.name == "chill_requirement" else item
            for item in parameters.parameters
        ),
    )
    with pytest.raises(ValueError, match="must be finite"):
        simulate(replace(request, parameter_set=invalid))

    production_prior = replace(
        parameters,
        parameters=tuple(
            replace(item, production_eligible=True)
            if item.authority.value == "LITERATURE_PRIOR"
            else item
            for item in parameters.parameters
        ),
    )
    with pytest.raises(ValueError, match="cannot be production eligible"):
        simulate(replace(request, parameter_set=production_prior))


def test_parameter_set_cannot_be_promoted_to_production_by_default() -> None:
    parameters = reference_parameter_set()
    assert parameters.scenario_only
    assert all(not item.production_eligible for item in parameters.parameters)


def test_equation_authority_and_parameter_registries_are_complete_and_scoped() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    equation_path = repo_root / "docs/v0-9/s3/model-equation-authority-register-r1.csv"
    parameter_path = repo_root / "docs/v0-9/s3/literature-model-parameter-registry-r1.csv"
    source_path = repo_root / "docs/v0-9/s3/scientific-model-source-register-r1.csv"
    claim_path = repo_root / "docs/v0-9/s0/biological-causal-claim-register-r1.csv"
    authority_path = repo_root / "docs/v0-9/s0/scientific-authority-matrix-r1.csv"

    def rows(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    equations = rows(equation_path)
    parameters = rows(parameter_path)
    source_records = rows(source_path)
    source_ids = {row["source_id"] for row in source_records}
    source_ids.update(row["source_id"] for row in rows(authority_path))
    claim_ids = {row["claim_id"] for row in rows(claim_path)}
    allowed_authorities = {
        "DIRECT_LITERATURE_EQUATION",
        "LITERATURE_DERIVED_STRUCTURE",
        "STANDARD_AGRONOMIC_MODEL",
        "EXPLICIT_MODEL_ABSTRACTION",
    }

    assert len({row["equation_id"] for row in equations}) == 30
    assert {row["equation_authority"] for row in equations} <= allowed_authorities
    for equation in equations:
        assert equation["production_approved"] == "false"
        assert equation["implementation_reference"]
        assert set(equation["source_ids"].split(";")) <= source_ids
        assert set(equation["s0_claim_ids"].split(";")) <= claim_ids

    parameter_names = {row["parameter_name"] for row in parameters}
    assert {item.name for item in reference_parameter_set().parameters} <= parameter_names
    assert len(parameter_names) == len(parameters)
    assert all(row["production_parameter"] == "false" for row in parameters)
    assert len(source_records) == 20
    assert all(row["authority_tier"] in {"A", "A2", "B", "C", "D", "X"} for row in source_records)
    assert all(row["peer_review_status"].startswith("Peer-reviewed") for row in source_records)
    assert all(row["calibration_status"] == "NOT_CALIBRATED" for row in parameters)
    priors = [row for row in parameters if row["parameter_role"] == "LITERATURE_PRIOR"]
    assert len(priors) == 7
    assert all(row["source_id"] == "M003;M004" for row in priors)
    literature_values = [
        row for row in parameters if row["parameter_role"] == "DIRECT_LITERATURE_VALUE"
    ]
    assert len(literature_values) == 13
    assert all(set(row["source_id"].split(";")) <= source_ids for row in literature_values)
    method_constants = [
        row for row in parameters if row["parameter_role"] == "REFERENCE_METHOD_CONSTANT"
    ]
    assert len(method_constants) == 2


def test_s0_not_ready_mechanisms_remain_quarantined() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    claims_path = repo_root / "docs/v0-9/s0/biological-causal-claim-register-r1.csv"
    with claims_path.open(encoding="utf-8", newline="") as stream:
        claims = list(csv.DictReader(stream))
    not_ready_ids = {"C005", "C009", "C011", "C016", "C024", "C027"}
    claim_ids = {row["claim_id"] for row in claims}
    assert not_ready_ids <= claim_ids
    assert len(not_ready_ids) == 6


def test_documented_reference_scenarios_are_synthetic_and_complete() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    manifest = json.loads(
        (repo_root / "docs/v0-9/s3/reference-scenario-manifest-r1.json").read_text(encoding="utf-8")
    )
    test_manifest = json.loads((GOLDEN_DIR / "manifest.json").read_text(encoding="utf-8"))
    names = [scenario["scenario_id"] for scenario in manifest["scenarios"]]
    assert names == test_manifest["scenarios"]
    assert manifest["production_parameter"] is False
    assert manifest["business_data_used"] is False
    assert manifest["historical_harvest_used_for_fitting"] is False
    assert manifest["benchmark_2025_2026_read"] is False
    assert manifest["s0_not_ready_claims_quarantined_from_production_parameterization"] == [
        "C005",
        "C009",
        "C011",
        "C016",
        "C024",
        "C027",
    ]
    assert manifest["unauthorized_mechanism_promotion_count"] == 0
    assert all(
        (repo_root / scenario["golden_fixture"]).is_file() for scenario in manifest["scenarios"]
    )


def test_s3_evidence_artifact_manifest_hashes_match_files() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    evidence_path = repo_root / "docs/v0-9/evidence/s3-theoretical-blueberry-growth-model-r1.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert (
        evidence["task_id"]
        == "V0_9_S3_THEORETICAL_BLUEBERRY_GROWTH_MODEL_AND_DETERMINISTIC_SIMULATOR_R1"
    )
    assert evidence["result"] == "PASS_V0_9_S3_THEORETICAL_GROWTH_MODEL_IMPLEMENTED"
    artifact_paths = {item["path"] for item in evidence["artifact_manifest"]}
    assert str(evidence_path.relative_to(repo_root)) not in artifact_paths
    assert "backend/app/biological_growth/engine.py" in artifact_paths
    assert "backend/tests/biological_growth/test_v09_s3_theoretical_simulator.py" in artifact_paths
    for item in evidence["artifact_manifest"]:
        actual = hashlib.sha256((repo_root / item["path"]).read_bytes()).hexdigest()
        assert actual == item["sha256"], item["path"]


def test_shade_changes_synthetic_radiation_but_not_supplied_microclimate() -> None:
    timestamp = datetime(2030, 6, 1)
    observation = EnvironmentHour(
        timestamp=timestamp,
        air_temperature_c=20.0,
        source_id="SYNTHETIC",
        source_priority=1,
        radiation_index=0.8,
    )
    event = ManagementEvent(
        event_id="shade",
        event_type=EventType.SHADE_START,
        event_datetime=timestamp,
        intensity=0.5,
        intensity_unit="fraction_0_1",
        observed_or_planned="PLANNED",
        source_reference="GOLDEN_FIXTURE",
        target="SYNTHETIC",
    )
    assert effective_radiation_index(
        observation, (event,), scenario_mode=True, shade_fraction=0.7
    ) == pytest.approx(0.52)
    assert (
        effective_radiation_index(observation, (event,), scenario_mode=False, shade_fraction=0.7)
        == 0.8
    )


def test_cane_age_response_is_explicitly_parameterized() -> None:
    request = build_scenario("deciduous-natural")
    weights = {
        "juvenile_productivity_weight": 0.5,
        "mature_productivity_weight": 1.0,
        "old_productivity_weight": 0.4,
        "mature_age_years": 2,
        "old_age_years": 5,
    }
    mature_state = initial_structural_state(request.plant_structure, **weights)
    old_structure = replace(
        request.plant_structure,
        canes=tuple(replace(cane, age_years=6) for cane in request.plant_structure.canes),
    )
    old_state = initial_structural_state(old_structure, **weights)
    assert mature_state.age_weighted_productivity_index > old_state.age_weighted_productivity_index
