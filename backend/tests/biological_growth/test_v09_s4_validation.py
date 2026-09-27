from __future__ import annotations

from dataclasses import replace

import pytest

from backend.app.biological_growth.dormancy import ChillAccumulator
from backend.app.biological_growth.engine import (
    _validate_request,
    simulate,
    simulate_with_daily_chunks,
)
from backend.app.biological_growth.fruit_development import (
    double_gompertz_growth_fraction,
    maturity_cumulative_fraction,
)
from backend.app.biological_growth.parameters import reference_parameter_set, validate_parameter_set
from backend.app.biological_growth.schemas import ChillModel, EventType, ManagementEvent
from backend.tests.biological_growth.s4_validation import (
    build_abstraction_quarantine_rows,
    build_abstraction_review_rows,
    build_dimensional_rows,
    build_equation_rows,
    build_update_order,
    run_synthetic_validation,
    verify_authority_pins,
)
from backend.tests.biological_growth.scenario_factory import build_scenario


def test_reference_parameter_units_match_additive_state_domains() -> None:
    parameters = {item.name: item for item in reference_parameter_set().parameters}

    assert parameters["flower_bud_increment_per_signal"].unit == ("buds_per_plant_per_signal_day")
    assert parameters["evergreen_flower_bud_rate"].unit == "buds_per_plant_per_day"
    assert parameters["pruning_regrowth_gain"].unit == "shoots_per_plant"


def test_parameter_domains_fail_closed_for_invalid_fraction_and_order() -> None:
    invalid_fraction = reference_parameter_set({"fruit_set_maximum": 1.01})
    with pytest.raises(ValueError, match="fraction parameter"):
        validate_parameter_set(invalid_fraction)

    invalid_order = reference_parameter_set(
        {"forcing_base_temperature_c": 28.0, "forcing_upper_temperature_c": 28.0}
    )
    with pytest.raises(ValueError, match="upper temperature"):
        validate_parameter_set(invalid_order)


def test_maturity_distribution_rejects_nonpositive_width() -> None:
    with pytest.raises(ValueError, match="width must be positive"):
        maturity_cumulative_fraction(100.0, median_dd=200.0, width_dd=0.0)


def test_s0_s1_s3_authority_pins_and_declared_s3_fixes_verify() -> None:
    pins = verify_authority_pins()
    assert pins["s0_verified"] is True
    assert pins["s1_verified"] is True
    assert pins["s3_unexplained_pin_mismatches"] == 0
    assert {item["path"] for item in pins["s3_declared_s4_unit_corrections"]} == {
        "backend/app/biological_growth/engine.py",
        "backend/app/biological_growth/dormancy.py",
        "backend/app/biological_growth/parameters.py",
        "backend/app/biological_growth/fruit_development.py",
    }


def test_all_s3_equations_are_resolvable_and_dimensionally_audited() -> None:
    trace = build_equation_rows()
    dimensions = build_dimensional_rows()
    assert len(trace) == 30
    assert all(item["status"] == "PASS" for item in trace)
    assert all(item["implementation_matches_contract"] == "true" for item in trace)
    assert len(dimensions) == 30
    assert all(item["status"] == "PASS" for item in dimensions)
    assert sum(item["unit_correction_applied_in_s4_code"] == "true" for item in dimensions) == 3
    unsupported = next(item for item in trace if item["equation_id"] == "EQA030")
    assert unsupported["unsupported_branch_present"] == "true"
    assert "IRRIGATION_STRESS" in unsupported["unsupported_branch_notes"]
    assert "NUTRITION_INTERVENTION" in unsupported["unsupported_branch_notes"]


def test_unimplemented_management_events_are_explicitly_traced_as_no_effect() -> None:
    request = build_scenario("deciduous-natural")
    first_hour = request.environment[0].timestamp
    events = tuple(
        ManagementEvent(
            event_id=event_type.value,
            event_type=event_type,
            event_datetime=first_hour,
            intensity=0.5,
            intensity_unit="fraction_0_1",
            observed_or_planned="OBSERVED",
            source_reference="SYNTHETIC_TEST_ONLY",
            target="PLANT",
        )
        for event_type in (EventType.IRRIGATION_STRESS, EventType.NUTRITION_INTERVENTION)
    )
    output = simulate(
        replace(request, management_events=events),
        chill_model=ChillModel.CHILL_HOURS,
    )
    no_effect_lines = output.trace["WHICH_MANAGEMENT_EVENT_AFFECTED_WHICH_STATE"]
    assert all(
        f"{event.event_id}:{event.event_type.value}->NO_PHYSIOLOGICAL_EFFECT_BOUND_IN_S3"
        in no_effect_lines
        for event in events
    )


def test_update_order_covers_all_modules_and_declares_no_algebraic_loop() -> None:
    order = build_update_order()
    assert order["model_module_count"] == 16
    assert len(order["module_coverage"]) == 16
    assert order["algebraic_loop_count"] == 0
    assert all(
        set(node)
        >= {
            "previous_state_inputs",
            "same_step_inputs",
            "next_state_outputs",
        }
        for node in order["nodes"]
    )


def test_explicit_abstractions_reviewed_and_six_not_ready_claims_quarantined() -> None:
    assert len(build_abstraction_review_rows()) == 18
    quarantine = build_abstraction_quarantine_rows()
    assert len(quarantine) == 6
    assert {item["claim_id"] for item in quarantine} == {
        "C005",
        "C009",
        "C011",
        "C016",
        "C024",
        "C027",
    }


def test_synthetic_invariants_and_counterfactual_validation() -> None:
    result = run_synthetic_validation()
    assert result["golden_scenario_count"] == 11
    assert result["reference_scenario_robustness_count"] == 33
    assert result["counterfactual_count"] == 5
    assert result["continuation_parity"]["full_season_output_parity"] is True
    assert result["continuation_parity"]["stateful_daily_chunk_parity"] is True
    assert all(result["numerical_stress_checks"].values())
    assert all(result["interseason_checks"].values())


def test_stateful_daily_chunk_execution_matches_one_shot_output() -> None:
    full_request = build_scenario("deciduous-natural")
    request = replace(full_request, environment=full_request.environment[: 30 * 24])
    one_shot = simulate(request, chill_model=ChillModel.CHILL_HOURS)
    for chunk_days in (1, 7, 30):
        chunked = simulate_with_daily_chunks(
            request,
            chill_model=ChillModel.CHILL_HOURS,
            chunk_days=chunk_days,
        )
        assert chunked == one_shot
    with pytest.raises(ValueError, match="chunk_days must be positive"):
        simulate_with_daily_chunks(request, chill_model=ChillModel.CHILL_HOURS, chunk_days=0)


def test_double_gompertz_rejects_non_finite_parameters() -> None:
    with pytest.raises(ValueError, match="finite"):
        double_gompertz_growth_fraction(
            10.0,
            stage1_midpoint_dd=100.0,
            stage2_midpoint_dd=200.0,
            width_dd=float("nan"),
        )


def test_dynamic_chill_rejects_nonphysical_and_nonfinite_temperature() -> None:
    accumulator = ChillAccumulator(
        model=ChillModel.DYNAMIC_CHILL_PORTIONS,
        dynamic_constants={
            "dynamic_model_e0": 4153.5,
            "dynamic_model_e1": 12888.8,
            "dynamic_model_a0": 139500.0,
            "dynamic_model_a1": 2.567e18,
            "dynamic_model_slope": 1.6,
            "dynamic_model_tf_kelvin": 277.0,
        },
    )
    with pytest.raises(ValueError, match="finite"):
        accumulator.add_hour(float("nan"))
    with pytest.raises(ValueError, match="absolute zero"):
        accumulator.add_hour(-273.15)


@pytest.mark.parametrize(
    "value",
    [0.0, 1.0, 1e-12, 1.0 - 1e-12],
)
def test_normalized_state_bounds_accept_edges_and_just_inside_values(value: float) -> None:
    request = build_scenario("deciduous-natural")
    state = replace(request.initial_state, reserve_index=value)
    _validate_request(replace(request, initial_state=state))


@pytest.mark.parametrize("value", [-1e-12, 1.0 + 1e-12])
def test_normalized_state_bounds_fail_closed_just_outside(value: float) -> None:
    request = build_scenario("deciduous-natural")
    state = replace(request.initial_state, reserve_index=value)
    with pytest.raises(ValueError, match="Normalized initial plant indices"):
        _validate_request(replace(request, initial_state=state))


@pytest.mark.parametrize("temperature", [-25.0, 55.0])
def test_extreme_but_finite_temperature_is_valid_for_synthetic_stress(
    temperature: float,
) -> None:
    request = build_scenario("deciduous-natural")
    environment = tuple(
        replace(hour, air_temperature_c=temperature) for hour in request.environment
    )
    _validate_request(replace(request, environment=environment))
