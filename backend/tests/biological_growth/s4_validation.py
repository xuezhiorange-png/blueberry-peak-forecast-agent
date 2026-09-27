"""Evidence-bounded S4 validation helpers; no business harvest labels are loaded."""

# ruff: noqa: E501 -- audit descriptions preserve complete equation/authority strings.

from __future__ import annotations

import ast
import csv
import hashlib
import json
import math
import random
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

from backend.app.biological_growth.dormancy import ChillAccumulator
from backend.app.biological_growth.engine import simulate, simulate_with_daily_chunks
from backend.app.biological_growth.fruit_development import (
    double_gompertz_growth_fraction,
    double_sigmoid_growth_fraction,
    fruit_growth_fraction,
    maturity_cumulative_fraction,
)
from backend.app.biological_growth.parameters import reference_parameter_set
from backend.app.biological_growth.schemas import (
    ChillModel,
    EnvironmentHour,
    EventType,
    FruitGrowthCurve,
    ManagementEvent,
    ProductionSystem,
    SimulationInput,
    SimulationOutput,
)
from backend.tests.biological_growth.scenario_factory import build_scenario

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
S0_PINS = {
    "docs/v0-9/s0/global-protected-blueberry-biology-and-management-authority-review-r1.md": "827725a44094e5e15643186fe8f82095adbff0bfc2b2ac549aca6600d06a4c13",
    "docs/v0-9/evidence/s0-global-protected-blueberry-biology-and-management-authority-review-r1.json": "530106f7291ab3d92fe4b0a0d682efc0fc154149218acda71369f76e785449cf",
    "docs/v0-9/s0/scientific-authority-matrix-r1.csv": "1fecd24c4aa537d5617a960e15ab74ace260ad35e30e63d9fdbe89e59bf88294",
    "docs/v0-9/s0/biological-causal-claim-register-r1.csv": "0ee8959db03f1ac28b226df06c00bf08c2427949b2f1e9de69a772bbd805d55a",
    "docs/v0-9/s0/evidence-conflict-and-uncertainty-register-r1.csv": "e5c17df1d33e3ef9dcc1d5d149598fa6a602a5c65a09f99d47e8040d42d94a91",
    "docs/v0-9/s0/literature-parameter-candidate-register-r1.csv": "2d28f90e42eafeea14f252e96ed0c26e2bc6b78b1c8273263b5d2d32b1410325",
}
S3_EVIDENCE_PATH = "docs/v0-9/evidence/s3-theoretical-blueberry-growth-model-r1.json"
S3_EVIDENCE_SHA256 = "c74c956650f4e5751083ffed3d40e9cbff68c3f53fc8e1ad661c234003d3e441"
S2_EVIDENCE_PATH = "docs/v0-9/evidence/s2-existing-data-observability-and-gap-audit-r1.json"
S1_MANIFEST_PATH = "docs/v0-9/evidence/s1-biological-contract-artifact-manifest-r1.json"
S1_MANIFEST_SHA256 = "8ea4d508010e55c4996142ec96c389a91a356f78966e8f5d4fb4e449ef611381"
S3_UNIT_CORRECTION_PATH = "backend/app/biological_growth/parameters.py"
S3_PRE_S4_UNIT_CORRECTION_SHA256 = (
    "b50bc862aa3e2b8cef847e0213d97f55bf71cd70463c55390c78618ea203d2be"
)
S3_PRE_S4_MATURITY_GUARD_SHA256 = "437b65642ebeba5b04bd843f784804db6e8c085c46c13a16f487a77b66efde84"
S3_PRE_S4_CHILL_UNIT_GUARD_SHA256 = (
    "bc5860e71df33fd24f18b62ee92498021e6f54edbf94e20f65a1392698229017"
)
GOLDEN_SCENARIOS = (
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
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def verify_authority_pins(root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    checked: list[dict[str, str]] = []
    for relative_path, expected in S0_PINS.items():
        actual = sha256_file(root / relative_path)
        if actual != expected:
            raise ValueError(f"S0 authority drift: {relative_path}")
        checked.append({"path": relative_path, "sha256": actual, "status": "PASS"})

    s1_manifest_path = root / S1_MANIFEST_PATH
    s1_manifest = json.loads(s1_manifest_path.read_text(encoding="utf-8"))
    s1_manifest_hash = sha256_file(s1_manifest_path)
    if s1_manifest_hash != S1_MANIFEST_SHA256:
        raise ValueError("S1 artifact manifest hash drift")
    for item in s1_manifest["files"]:
        actual = sha256_file(root / item["path"])
        if actual != item["sha256"]:
            raise ValueError(f"S1 authority drift: {item['path']}")
        checked.append({"path": item["path"], "sha256": actual, "status": "PASS"})

    s3_evidence_path = root / S3_EVIDENCE_PATH
    s3_evidence_hash = sha256_file(s3_evidence_path)
    if s3_evidence_hash != S3_EVIDENCE_SHA256:
        raise ValueError("S3 evidence artifact hash drift")
    s3_evidence = json.loads(s3_evidence_path.read_text(encoding="utf-8"))
    s3_mismatches: list[dict[str, str]] = []
    s3_checked_files: list[dict[str, str]] = []
    s3_checked_count = 0
    for item in s3_evidence["artifact_manifest"]:
        actual = sha256_file(root / item["path"])
        s3_checked_count += 1
        if actual == item["sha256"]:
            s3_checked_files.append(
                {
                    "path": item["path"],
                    "expected_sha256": item["sha256"],
                    "actual_sha256": actual,
                    "status": "PIN_MATCH",
                }
            )
            continue
        correction_reasons = {
            "backend/app/biological_growth/engine.py": (
                "124b7a4a27c789b21982cdf168fe9097f3b69cac7159d229756f5a1c6bdce5a7",
                "stateful daily generator added for in-memory chunk continuation parity; biological equations and update order unchanged",
            ),
            S3_UNIT_CORRECTION_PATH: (
                S3_PRE_S4_UNIT_CORRECTION_SHA256,
                "three additive-state parameter unit labels corrected; values/formulas unchanged",
            ),
            "backend/app/biological_growth/fruit_development.py": (
                S3_PRE_S4_MATURITY_GUARD_SHA256,
                "invalid/non-finite fruit curve inputs and maturity widths now fail closed; valid-output formula unchanged",
            ),
            "backend/app/biological_growth/dormancy.py": (
                S3_PRE_S4_CHILL_UNIT_GUARD_SHA256,
                "Dynamic Model Celsius-to-Kelvin conversion corrected to 273.15; non-finite and below-absolute-zero inputs fail closed",
            ),
        }
        if (
            item["path"] in correction_reasons
            and item["sha256"] == correction_reasons[item["path"]][0]
        ):
            s3_mismatches.append(
                {
                    "path": item["path"],
                    "pre_s4_sha256": item["sha256"],
                    "post_s4_sha256": actual,
                    "reason": correction_reasons[item["path"]][1],
                }
            )
            s3_checked_files.append(
                {
                    "path": item["path"],
                    "expected_sha256": item["sha256"],
                    "actual_sha256": actual,
                    "status": "DECLARED_S4_CODE_CORRECTION",
                }
            )
            continue
        raise ValueError(f"Unexpected S3 artifact drift: {item['path']}")

    if {item["path"] for item in s3_mismatches} != set(correction_reasons):
        raise ValueError("Post-pin S4 code changes exceed the three documented unit/boundary fixes")
    return {
        "s0_verified": True,
        "s0_artifact_count": len(S0_PINS),
        "s1_verified": True,
        "s1_artifact_count": len(s1_manifest["files"]),
        "s1_manifest_sha256": s1_manifest_hash,
        "s3_evidence_sha256": s3_evidence_hash,
        "s3_pre_change_pins_verified_before_s4_unit_fix": True,
        "s3_artifact_count": s3_checked_count,
        "s3_declared_s4_unit_corrections": s3_mismatches,
        "s3_checked_artifacts": s3_checked_files,
        "s3_unexplained_pin_mismatches": 0,
        "checked_authority_files": checked,
    }


def equation_dimension_specs() -> dict[str, dict[str, str]]:
    return {
        "EQA001": {
            "inputs": "cane_count=count/plant; productive_fraction=fraction",
            "outputs": "productive_canes=count/plant; productivity_index=fraction",
            "rule": "count/plant × fraction; weighted count divided by count",
        },
        "EQA002": {
            "inputs": "age=year; cane_count=count/plant; productive_fraction=fraction",
            "outputs": "age=year; count=count/plant; fraction=fraction",
            "rule": "season age increment is 1 year; counts and fractions retain dimension",
        },
        "EQA003": {
            "inputs": "event_intensity=fraction; fruiting_wood=index; leaf_area_index=m² leaf/m² ground; shoot_potential=shoots/plant",
            "outputs": "structural indices; flower_buds=buds/plant; shoot_potential=shoots/plant",
            "rule": "multipliers are dimensionless; regrowth increment is shoots/plant per event intensity",
        },
        "EQA004": {
            "inputs": "reserve=index; source=index; demand=count/plant or index; rates=index/day or index/(count·day)",
            "outputs": "reserve=index",
            "rule": "daily rate × one-day step; bounded normalized latent index, not carbon mass",
        },
        "EQA005": {
            "inputs": "photoperiod=hour; temperature=°C; vigor/reserve/load=fraction or index",
            "outputs": "induction_signal=dimensionless; bud_potential=buds/plant",
            "rule": "signal-day accumulator × buds/(plant·signal-day) gives buds/plant",
        },
        "EQA006": {
            "inputs": "hourly temperature=°C; interval=[0,7.2] °C",
            "outputs": "chill_hours=hour",
            "rule": "one dimensionless response unit per eligible one-hour observation",
        },
        "EQA007": {
            "inputs": "hourly temperature=°C; piecewise temperature bands=°C",
            "outputs": "Utah chill units=chill_unit",
            "rule": "piecewise chill_unit/hour weight summed over one-hour intervals",
        },
        "EQA008": {
            "inputs": "temperature=°C converted to K; dynamic constants=declared literature-prior units",
            "outputs": "dynamic chill portions=portion",
            "rule": "stateful kinetic response; model-specific unit retained without cross-model averaging",
        },
        "EQA009": {
            "inputs": "chill_exposure=model-typed chill unit; threshold=same model unit",
            "outputs": "dormancy_state=categorical",
            "rule": "only like-typed exposure and threshold compare; state is inferred, not observed",
        },
        "EQA010": {
            "inputs": "temperature/base/upper=°C; time=hour",
            "outputs": "forcing=°C·day",
            "rule": "temperature difference × hour/24 hours per day",
        },
        "EQA011": {
            "inputs": "cultivar and production-system identity=categorical",
            "outputs": "pathway/state=categorical",
            "rule": "explicit system path; no numeric unit or zero-chill inference",
        },
        "EQA012": {
            "inputs": "forcing/start/duration=°C·day",
            "outputs": "bloom_progress=fraction; cohort_flowers=flowers/plant",
            "rule": "normalized forcing fraction increment × flower load",
        },
        "EQA013": {
            "inputs": "event opportunity=fraction; temperature_suitability=fraction",
            "outputs": "pollination_sufficiency=fraction",
            "rule": "bounded product of dimensionless fractions",
        },
        "EQA014": {
            "inputs": "pollinated_flowers=flowers/plant; set_probability=fraction",
            "outputs": "fruit_count=fruits/plant",
            "rule": "count × dimensionless probability; bounded by input count",
        },
        "EQA015": {
            "inputs": "flower/fruitlet/fruit counts=count/plant; thinning=intensity fraction",
            "outputs": "scoped counts=count/plant",
            "rule": "dimensionless removal fraction cannot create reproductive units",
        },
        "EQA016": {
            "inputs": "leaf_area_index=m²/m²; health/light/temp/reserve=index",
            "outputs": "source_supply=normalized index",
            "rule": "all terms are dimensionless proxies; not carbon flux",
        },
        "EQA017": {
            "inputs": "fruit count=fruits/plant × inverse-count coefficient; other demands=normalized index",
            "outputs": "sink_demand=normalized index",
            "rule": "stage weights are dimensionless; coefficient carries inverse count representation",
        },
        "EQA018": {
            "inputs": "source_supply=index; sink_demand=index",
            "outputs": "sufficiency=fraction",
            "rule": "same-dimension ratio is dimensionless then bounded",
        },
        "EQA019": {
            "inputs": "thermal_age/midpoints/width=°C·day",
            "outputs": "growth_fraction=fraction",
            "rule": "normalized sum of two dimensionless logistic increments",
        },
        "EQA020": {
            "inputs": "temperature/base=°C; time=hour",
            "outputs": "thermal_age=°C·day",
            "rule": "positive temperature difference × hour/24 hours per day",
        },
        "EQA021": {
            "inputs": "thermal_age/median/width=°C·day",
            "outputs": "cumulative_ripe_fraction=fraction; delta=fraction/day step",
            "rule": "bounded logistic fraction; nonnegative first difference",
        },
        "EQA022": {
            "inputs": "fruit_count=berries/plant; berry_weight=g/berry; ripe/marketable=fraction; plant_count=plants",
            "outputs": "kg/plant/day and kg/day",
            "rule": "berries × g/berry × kg/1000g; area(mu) × density(plants/mu) = plants",
        },
        "EQA023": {
            "inputs": "reserve/vigor/crop_load=fraction or normalized index",
            "outputs": "carryover reserve/vigor/bud potential=normalized latent index",
            "rule": "only dimensionless normalized states combine; not buds/plant without an explicit scale",
        },
        "EQA024": {
            "inputs": "temperature/offset=°C; radiation=index; shade=fraction",
            "outputs": "effective temperature=°C; effective radiation=index",
            "rule": "add like-temperature units; shade multiplies a dimensionless light proxy",
        },
        "EQA025": {
            "inputs": "temperature/low/high=°C",
            "outputs": "temperature_suitability=fraction",
            "rule": "temperature differences divide like-temperature differences",
        },
        "EQA026": {
            "inputs": "event window/time=categorical/datetime; opportunity=fraction",
            "outputs": "pollination index=fraction",
            "rule": "time gates dimensionless scenario opportunity",
        },
        "EQA027": {
            "inputs": "potential_weight=g/berry; modifiers=fraction/index",
            "outputs": "berry_weight=g/berry",
            "rule": "g/berry × dimensionless response factors",
        },
        "EQA028": {
            "inputs": "thermal_age/stage boundaries/width=°C·day",
            "outputs": "growth_fraction=fraction",
            "rule": "all three curve families return normalized fraction",
        },
        "EQA029": {
            "inputs": "chill requirement=model-typed chill unit; treatment intensity/reduction=fraction",
            "outputs": "effective threshold=same chill unit; dormancy gate=categorical",
            "rule": "chill unit × dimensionless reduction fraction",
        },
        "EQA030": {
            "inputs": "PlantState, Environment, Management, scoped parameters",
            "outputs": "next PlantState and daily newly mature kg",
            "rule": "typed module transitions; mass output reconciles from cohorts",
        },
    }


PARAMETERS_BY_EQUATION: dict[str, str] = {
    "EQA001": "cane_productivity_juvenile_weight;cane_productivity_mature_weight;cane_productivity_old_weight;cane_mature_age_years;cane_old_age_years",
    "EQA002": "cane_age_structure;renewal_cohort",
    "EQA003": "pruning_wood_loss_fraction;pruning_leaf_loss_fraction;pruning_cane_loss_fraction;pruning_shoot_loss_fraction;pruning_regrowth_gain;pruning_bud_loss_fraction",
    "EQA004": "postharvest_reserve_gain;reserve_maintenance_cost;reserve_fruit_demand_cost;reserve_other_demand_cost",
    "EQA005": "flower_bud_response_strength;flower_bud_increment_per_signal;flower_bud_induction_threshold;flower_bud_photoperiod_weight;flower_bud_thermal_weight;flower_bud_vigor_weight;flower_bud_reserve_weight",
    "EQA006": "CHILL_HOURS_EFFECTIVE_LOW_TEMP;CHILL_HOURS_EFFECTIVE_HIGH_TEMP",
    "EQA007": "UTAH_TEMP_BREAKPOINTS;UTAH_WEIGHT_BANDS",
    "EQA008": "dynamic_model_e0;dynamic_model_e1;dynamic_model_a0;dynamic_model_a1;dynamic_model_slope;dynamic_model_tf_kelvin",
    "EQA009": "chill_requirement;dormancy_treatment_chill_requirement_reduction_fraction",
    "EQA010": "forcing_base_temperature_c;forcing_upper_temperature_c",
    "EQA011": "evergreen_dormancy_bypass;evergreen_flower_bud_rate;cultivar_id",
    "EQA012": "bloom_start_forcing_dd;bloom_duration_dd",
    "EQA013": "pollination_baseline_index;pollinator_event_increment;temperature_stress_low_c;temperature_stress_high_c",
    "EQA014": "fruit_set_maximum;fruit_set_source_base_weight;fruit_set_source_response_weight",
    "EQA015": "stage_sink_fruit_set;stage_sink_stage_i;stage_sink_stage_ii;stage_sink_stage_iii;stage_sink_color_break;stage_sink_ripe",
    "EQA016": "source_light_half_saturation;reserve_mobilization_fraction;source_response_reference_index",
    "EQA017": "fruit_sink_strength;vegetative_sink_strength;root_growth_sink_strength;storage_sink_strength",
    "EQA018": "source_sink_floor;source_sink_ceiling",
    "EQA019": "double_sigmoid_stage1_midpoint_dd;double_sigmoid_stage2_midpoint_dd;double_sigmoid_width_dd",
    "EQA020": "development_base_temperature_c",
    "EQA021": "ripe_median_thermal_age_dd;ripe_distribution_width_dd;seed_maturity_shift_scale_dd",
    "EQA022": "potential_berry_weight_g;marketable_fraction;productive_area_mu;plant_density_per_mu",
    "EQA023": "reserve_carryover_fraction;vigor_carryover_fraction;carryover_vigor_crop_load_penalty;carryover_reserve_crop_load_penalty;carryover_bud_crop_load_penalty;reserve_bud_contribution",
    "EQA024": "microclimate_closure_delta_c;microclimate_heating_delta_c;microclimate_shade_fraction",
    "EQA025": "temperature_stress_low_c;temperature_stress_high_c",
    "EQA026": "pollination_window_start;pollination_window_end",
    "EQA027": "berry_weight_source_response;seed_index_weight_response;potential_berry_weight_g",
    "EQA028": "fruit_growth_curve;double_sigmoid_stage1_midpoint_dd;double_sigmoid_stage2_midpoint_dd;double_sigmoid_width_dd",
    "EQA029": "dormancy_treatment_chill_requirement_reduction_fraction",
    "EQA030": "scoped_parameter_set;production_system;cultivar",
}


def _implementation_exists(root: Path, reference: str) -> bool:
    path_text, symbol_path = reference.split(":", maxsplit=1)
    path = root / path_text
    if not path.is_file():
        return False
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parts = symbol_path.split(".")
    scope: list[ast.AST] = list(tree.body)
    for part in parts:
        match = next(
            (
                node
                for node in scope
                if isinstance(
                    node,
                    (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
                )
                and node.name == part
            ),
            None,
        )
        if match is None:
            return False
        scope = list(match.body) if isinstance(match, ast.ClassDef) else []
        if part != parts[-1] and not isinstance(match, ast.ClassDef):
            return False
    return True


IMPLEMENTATION_CONSTANT_NOTES = {
    "EQA002": "Season aging adds one year per explicit season transition.",
    "EQA006": "The declared 0–7.2 C chill-hour band is fixed in the named candidate method.",
    "EQA007": "The piecewise Utah temperature breakpoints/weights are method constants, not fitted parameters.",
    "EQA008": "C-to-K conversion uses 273.15 and exponent arguments are clipped at +/-700 to prevent overflow; these are disclosed implementation constants, not biological parameters.",
    "EQA010": "Division by 24 is the hour-to-day unit conversion.",
    "EQA019": "The 1e6 thermal-age value approximates the logistic asymptote for normalization; it is not a biological parameter.",
    "EQA022": "Division by 1000 converts grams to kilograms; area x density converts mu to plants.",
    "EQA025": "A 1e-12 denominator guard stabilizes a positive temperature interval; parameter order is validated separately.",
}

EQUATION_UNSUPPORTED_SCOPE = {
    "EQA030": (
        "IRRIGATION_STRESS and NUTRITION_INTERVENTION are registered event types but have no physiological transition in S3; the engine records a no-effect trace."
    ),
}


def build_equation_rows(root: Path = REPOSITORY_ROOT) -> list[dict[str, str]]:
    equation_path = root / "docs/v0-9/s3/model-equation-authority-register-r1.csv"
    equations = load_csv(equation_path)
    parameter_rows = load_csv(root / "docs/v0-9/s3/literature-model-parameter-registry-r1.csv")
    parameter_ids = {item["parameter_name"]: item["parameter_id"] for item in parameter_rows}
    s0_sources = {
        item["source_id"]
        for item in load_csv(root / "docs/v0-9/s0/scientific-authority-matrix-r1.csv")
    }
    s3_sources = {
        item["source_id"]
        for item in load_csv(root / "docs/v0-9/s3/scientific-model-source-register-r1.csv")
    }
    s0_claims = {
        item["claim_id"]
        for item in load_csv(root / "docs/v0-9/s0/biological-causal-claim-register-r1.csv")
    }
    dimensions = equation_dimension_specs()
    if len(equations) != 30 or set(dimensions) != {row["equation_id"] for row in equations}:
        raise ValueError("Pinned S3 equation inventory is not exactly 30")
    rows: list[dict[str, str]] = []
    for equation in equations:
        equation_id = equation["equation_id"]
        path, symbol = equation["implementation_reference"].split(":", maxsplit=1)
        exists = _implementation_exists(root, equation["implementation_reference"])
        dimension = dimensions[equation_id]
        parameter_names = PARAMETERS_BY_EQUATION[equation_id].split(";")
        registered_parameter_ids = [
            parameter_ids[name] for name in parameter_names if name in parameter_ids
        ]
        non_parameter_terms = [name for name in parameter_names if name not in parameter_ids]
        source_refs = equation["source_ids"].split(";")
        claim_refs = equation["s0_claim_ids"].split(";")
        authority_refs_valid = all(
            source_id in s0_sources | s3_sources for source_id in source_refs
        ) and all(claim_id in s0_claims for claim_id in claim_refs)
        unsupported = equation_id in EQUATION_UNSUPPORTED_SCOPE
        rows.append(
            {
                "equation_id": equation_id,
                "module": equation["module"],
                "scientific_authority_class": equation["equation_authority"],
                "source_ids": equation["source_ids"],
                "documented_equation": equation["equation_or_transition"],
                "implemented_function": f"{path}:{symbol}",
                "inputs": dimension["inputs"],
                "outputs": dimension["outputs"],
                "units": dimension["rule"],
                "parameter_ids": ";".join(registered_parameter_ids),
                "non_parameter_context_or_method_terms": ";".join(non_parameter_terms),
                "implementation_matches_contract": str(exists and authority_refs_valid).lower(),
                "hidden_constant_present": str(
                    equation_id in IMPLEMENTATION_CONSTANT_NOTES
                ).lower(),
                "implementation_constant_notes": IMPLEMENTATION_CONSTANT_NOTES.get(
                    equation_id,
                    "No nontrivial unregistered implementation constant found in reviewed expression.",
                ),
                "unsupported_branch_present": str(unsupported).lower(),
                "unsupported_branch_notes": EQUATION_UNSUPPORTED_SCOPE.get(equation_id, "NONE"),
                "status": "PASS" if exists and authority_refs_valid else "UNTRACEABLE",
            }
        )
    return rows


def build_dimensional_rows(root: Path = REPOSITORY_ROOT) -> list[dict[str, str]]:
    traceability = build_equation_rows(root)
    pinned_registry = {
        item["parameter_name"]: item
        for item in load_csv(root / "docs/v0-9/s3/literature-model-parameter-registry-r1.csv")
    }
    runtime_units = {
        item.name: item.unit
        for item in reference_parameter_set(chill_model="CHILL_HOURS").parameters
    }
    corrected_parameters = {
        "flower_bud_increment_per_signal",
        "evergreen_flower_bud_rate",
        "pruning_regrowth_gain",
    }
    rows: list[dict[str, str]] = []
    actual_mismatches: set[str] = set()
    for row in traceability:
        names = PARAMETERS_BY_EQUATION[row["equation_id"]].split(";")
        mismatches = [
            f"{name}:S3={pinned_registry[name]['unit']}|runtime={runtime_units[name]}"
            for name in names
            if name in pinned_registry
            and name in runtime_units
            and pinned_registry[name]["unit"] != runtime_units[name]
        ]
        unexpected = [
            item.split(":", maxsplit=1)[0]
            for item in mismatches
            if item.split(":", maxsplit=1)[0] not in corrected_parameters
        ]
        actual_mismatches.update(item.split(":", maxsplit=1)[0] for item in mismatches)
        dimensions = equation_dimension_specs()[row["equation_id"]]
        rows.append(
            {
                "equation_id": row["equation_id"],
                "module": row["module"],
                "inputs_and_dimensions": dimensions["inputs"],
                "outputs_and_dimensions": dimensions["outputs"],
                "dimensional_rule": dimensions["rule"],
                "pinned_s3_registry_unit_mismatches": " ; ".join(mismatches) or "NONE",
                "unit_correction_applied_in_s4_code": str(bool(mismatches)).lower(),
                "status": "PASS"
                if not unexpected and row["implementation_matches_contract"] == "true"
                else "FAIL",
            }
        )
    if actual_mismatches != corrected_parameters:
        raise ValueError(
            f"Unexpected pinned S3 parameter-unit registry mismatch: {actual_mismatches}"
        )
    return rows


def build_update_order() -> dict[str, Any]:
    order = [
        (
            "STRUCTURE_AND_EVENT_APPLICATION",
            "DAILY",
            "prior structural state",
            "same-day events",
            "current structural state",
        ),
        (
            "MICROCLIMATE_AGGREGATION",
            "HOURLY_TO_DAILY",
            "raw hourly environment",
            "active greenhouse/heating/shade events",
            "effective environment drivers",
        ),
        (
            "CHILLING_AND_THERMAL_DRIVERS",
            "HOURLY",
            "chill accumulator and dormancy state",
            "effective hourly temperature",
            "chill/forcing/thermal increments",
        ),
        (
            "FLOWER_BUD_AND_ACCLIMATION",
            "DAILY",
            "prior reserve/vigor/bud state",
            "daily environment and prior crop-load index",
            "updated bud potential and acclimation signal",
        ),
        (
            "DORMANCY_RELEASE_GATE",
            "DAILY",
            "prior dormancy state and accumulated chill",
            "scoped chill threshold/treatment event",
            "inferred release state",
        ),
        (
            "FORCING_AND_PHENOLOGY",
            "HOURLY_TO_DAILY",
            "prior forcing/progress",
            "post-release forcing increment",
            "forcing, bloom progress, phenology stage",
        ),
        (
            "BLOOM_COHORT_CREATION",
            "DAILY",
            "prior bloom progress",
            "same-day progress increment and flower load",
            "new bloom cohort",
        ),
        (
            "SOURCE_SINK_SNAPSHOT",
            "DAILY",
            "pre-fruit-set cohort load, reserve, structure",
            "same-day radiation/temperature",
            "source/sink sufficiency snapshot",
        ),
        (
            "POLLINATION_AND_FRUIT_SET",
            "DAILY",
            "un-set bloom cohorts",
            "pollination window/opportunity and source snapshot",
            "fruit-set cohorts",
        ),
        (
            "FRUIT_DEVELOPMENT_AND_MATURITY",
            "HOURLY_TO_DAILY",
            "existing fruit cohorts and prior ripe fractions",
            "thermal age and source snapshot",
            "updated fruit cohorts and newly mature mass",
        ),
        (
            "POSTHARVEST_RESERVE_AND_VIGOR",
            "DAILY",
            "prior reserve/vigor and pre-set sink snapshot",
            "daily source/demand",
            "next-day reserve/vigor",
        ),
        (
            "DAILY_STATE_SNAPSHOT",
            "DAILY",
            "all previous/current state outputs",
            "daily aggregates",
            "auditable state point",
        ),
        (
            "INTERSEASON_CARRYOVER",
            "SEASONAL",
            "final reserve/vigor/crop load/structure",
            "declared carryover coefficients",
            "next-season latent state",
        ),
        (
            "BIOLOGICAL_TO_HARVEST_INTERFACE",
            "DAILY",
            "fruit cohorts and maturity distribution",
            "daily maturity increments",
            "daily_newly_mature_quantity only",
        ),
    ]
    nodes = [
        {
            "sequence": index,
            "module": name,
            "time_scale": scale,
            "previous_state_inputs": previous,
            "same_step_inputs": current,
            "next_state_outputs": following,
        }
        for index, (name, scale, previous, current, following) in enumerate(order, start=1)
    ]
    module_coverage = [
        ("STRUCTURAL_ENGINE", [1]),
        ("POSTHARVEST_RECOVERY_ENGINE", [11]),
        ("FLOWER_BUD_ENGINE", [4]),
        ("DORMANCY_ENGINE", [5]),
        ("CHILLING_ENGINE", [3]),
        ("FORCING_ENGINE", [6]),
        ("EVERGREEN_PHENOLOGY_ENGINE", [6]),
        ("BLOOM_ENGINE", [7]),
        ("POLLINATION_ENGINE", [9]),
        ("FRUIT_SET_ENGINE", [9]),
        ("CROP_LOAD_ENGINE", [8, 9, 10]),
        ("SOURCE_SINK_ENGINE", [8, 9, 10]),
        ("FRUIT_DEVELOPMENT_ENGINE", [10]),
        ("MATURITY_ENGINE", [10]),
        ("INTERSEASON_ENGINE", [13]),
        ("BIOLOGICAL_TO_HARVEST_INTERFACE", [14]),
    ]
    return {
        "schema_version": "V0_9_S4_STATE_UPDATE_ORDER_R1",
        "order_semantics": "hourly physiology; daily immutable snapshot; seasonal carryover",
        "algebraic_loop_count": 0,
        "model_module_count": len(module_coverage),
        "module_coverage": [
            {"module": name, "sequence_references": sequences}
            for name, sequences in module_coverage
        ],
        "feedback_break_policy": "same-day fruit-set/crop-load feedback uses pre-set snapshot and becomes next-day sink input; reserve/vigor are next-step outputs",
        "continuation_policy": "IN_MEMORY_STATEFUL_DAILY_GENERATOR; no serialized/process-restart checkpoint API is claimed",
        "nodes": nodes,
    }


def _finite_numbers(output: SimulationOutput) -> list[float]:
    numbers: list[float] = []
    for point in output.daily_states:
        numbers.extend(
            [
                point.reserve_index,
                point.vigor_index,
                point.leaf_area_index,
                point.productive_canes,
                point.productive_shoots_per_plant,
                point.fruiting_wood_index,
                point.vegetative_shoot_potential,
                point.flower_bud_potential_per_plant,
                point.flower_load_per_plant,
                point.fruit_load_per_plant,
                point.source_supply_index,
                point.sink_demand_index,
                point.source_sink_sufficiency,
                point.chill_accumulation,
                point.forcing_accumulation,
                point.bloom_progress,
                point.new_mature_kg,
                point.new_mature_kg_per_plant,
            ]
        )
    for _, value in output.daily_newly_mature_quantity_kg:
        numbers.append(value)
    for bloom_cohort in output.bloom_cohorts:
        numbers.append(bloom_cohort.flower_quantity_per_plant)
    for fruit_set_cohort in output.fruit_set_cohorts:
        numbers.extend(
            [
                fruit_set_cohort.effective_pollinated_flowers_per_plant,
                fruit_set_cohort.fruit_number_per_plant,
            ]
        )
    for fruit_cohort in output.fruit_development_cohorts:
        numbers.extend(
            [
                fruit_cohort.fruit_quantity_per_plant,
                fruit_cohort.seed_effect_index,
                fruit_cohort.thermal_age_degree_days,
                fruit_cohort.source_sink_modifier,
                fruit_cohort.cumulative_ripe_fraction,
                fruit_cohort.ripe_mass_kg,
                fruit_cohort.ripe_mass_kg_per_plant,
                fruit_cohort.potential_berry_weight_g,
            ]
        )
    return numbers


def validate_output_contract(output: SimulationOutput, request: SimulationInput) -> dict[str, bool]:
    finite = all(math.isfinite(value) for value in _finite_numbers(output))
    bounded = all(
        0.0 <= point.bloom_progress <= 1.0
        and 0.0 <= point.reserve_index <= 1.0
        and 0.0 <= point.vigor_index <= 1.0
        and 0.0 <= point.source_sink_sufficiency <= 1.0
        and point.productive_canes >= 0.0
        and point.productive_shoots_per_plant >= 0.0
        and point.fruiting_wood_index >= 0.0
        and point.vegetative_shoot_potential >= 0.0
        and point.flower_bud_potential_per_plant >= 0.0
        and point.new_mature_kg >= 0.0
        and point.new_mature_kg_per_plant >= 0.0
        and point.leaf_area_index >= 0.0
        and point.flower_load_per_plant >= 0.0
        and point.fruit_load_per_plant >= 0.0
        and point.source_supply_index >= 0.0
        and point.sink_demand_index >= 0.0
        for point in output.daily_states
    )
    bloom_by_id = {item.cohort_id: item for item in output.bloom_cohorts}
    fruit_set_by_id = {item.cohort_id: item for item in output.fruit_set_cohorts}
    lineage = all(
        item.origin_bloom_cohort_id in bloom_by_id
        and item.fruit_number_per_plant <= item.effective_pollinated_flowers_per_plant + 1e-10
        and item.effective_pollinated_flowers_per_plant
        <= bloom_by_id[item.origin_bloom_cohort_id].flower_quantity_per_plant + 1e-10
        for item in output.fruit_set_cohorts
    ) and all(
        item.origin_bloom_cohort_id in bloom_by_id
        and item.origin_fruit_set_cohort_id in fruit_set_by_id
        and item.fruit_quantity_per_plant
        <= fruit_set_by_id[item.origin_fruit_set_cohort_id].fruit_number_per_plant + 1e-10
        and 0.0 <= item.cumulative_ripe_fraction <= 1.0
        and item.ripe_mass_kg >= 0.0
        and item.ripe_mass_kg_per_plant >= 0.0
        for item in output.fruit_development_cohorts
    )
    daily_mass = sum(value for _, value in output.daily_newly_mature_quantity_kg)
    cohort_mass = sum(item.ripe_mass_kg for item in output.fruit_development_cohorts)
    per_plant_mass = sum(value for _, value in output.daily_newly_mature_quantity_kg_per_plant)
    area_scale = request.productive_area_mu * request.plant_structure.plant_density_per_mu
    mass = math.isclose(daily_mass, cohort_mass, rel_tol=1e-10, abs_tol=1e-10) and math.isclose(
        daily_mass, per_plant_mass * area_scale, rel_tol=1e-10, abs_tol=1e-10
    )
    unique = (
        len(bloom_by_id) == len(output.bloom_cohorts)
        and len(fruit_set_by_id) == len(output.fruit_set_cohorts)
        and len({item.cohort_id for item in output.fruit_development_cohorts})
        == len(output.fruit_development_cohorts)
    )
    evergreen_legal = output.production_system is not ProductionSystem.EVERGREEN or all(
        point.dormancy_state == "NOT_APPLICABLE"
        and point.phenology_stage not in {"DORMANT", "CHILL_ACCUMULATING", "CHILL_SATISFIED"}
        for point in output.daily_states
    )
    return {
        "finite": finite,
        "bounded_and_nonnegative": bounded,
        "cohort_lineage_and_count_conservation": lineage and unique,
        "mature_mass_and_area_scaling": mass,
        "evergreen_path_legal": evergreen_legal,
    }


def output_metrics(output: SimulationOutput) -> dict[str, float]:
    daily = [value for _, value in output.daily_newly_mature_quantity_kg]
    rolling7 = max((sum(daily[i : i + 7]) for i in range(max(0, len(daily) - 6))), default=0.0)
    bloom10 = next(
        (i for i, point in enumerate(output.daily_states) if point.bloom_progress >= 0.1),
        float(len(daily) + 1),
    )
    bloom50 = next(
        (i for i, point in enumerate(output.daily_states) if point.bloom_progress >= 0.5),
        float(len(daily) + 1),
    )
    first_maturity = next(
        (i for i, value in enumerate(daily) if value > 0.0), float(len(daily) + 1)
    )
    return {
        "season_biological_yield_kg": sum(daily),
        "bloom_10_day_index": float(bloom10),
        "bloom_50_day_index": float(bloom50),
        "first_maturity_day_index": float(first_maturity),
        "single_day_peak_kg": max(daily, default=0.0),
        "rolling7_peak_kg": rolling7,
        "next_season_flower_bud_potential_index": output.interseason_state.next_season_flower_bud_potential,
    }


def _rolling7_peak(values: list[float]) -> float:
    return max((sum(values[index : index + 7]) for index in range(len(values) - 6)), default=0.0)


def build_parameter_sensitivity_rows(
    *, trajectories: int = 4, seed: int = 909, root: Path = REPOSITORY_ROOT
) -> list[dict[str, str]]:
    names = [
        "chill_requirement",
        "forcing_base_temperature_c",
        "forcing_upper_temperature_c",
        "bud_swell_forcing_dd",
        "bud_break_forcing_dd",
        "bloom_start_forcing_dd",
        "bloom_duration_dd",
        "flower_bud_response_strength",
        "flower_bud_increment_per_signal",
        "fruit_set_maximum",
        "source_light_half_saturation",
        "potential_berry_weight_g",
        "development_base_temperature_c",
        "ripe_median_thermal_age_dd",
        "ripe_distribution_width_dd",
        "double_sigmoid_stage1_midpoint_dd",
        "double_sigmoid_stage2_midpoint_dd",
        "pruning_wood_loss_fraction",
        "pruning_leaf_loss_fraction",
        "microclimate_closure_delta_c",
        "microclimate_heating_delta_c",
        "pollination_baseline_index",
        "carryover_bud_crop_load_penalty",
        "reserve_carryover_fraction",
    ]
    base_request = build_scenario("deciduous-natural")
    base_parameters = {item.name: item for item in base_request.parameter_set.parameters}
    ranges: dict[str, tuple[float, float]] = {}
    for name in names:
        value = base_parameters[name].value
        if value is None:
            raise ValueError(f"Sensitivity parameter {name} is unbound in reference scenario")
        if name == "bud_swell_forcing_dd":
            ranges[name] = (value * 0.9, value * 1.1)
        elif name == "bud_break_forcing_dd":
            ranges[name] = (value * 0.9, min(value * 1.1, 140.0))
        elif name == "bloom_start_forcing_dd":
            ranges[name] = (max(value * 0.9, 150.0), value * 1.1)
        elif name == "double_sigmoid_stage2_midpoint_dd":
            ranges[name] = (value * 0.8, 320.0)
        elif name.endswith("_temperature_c") or name.endswith("_delta_c"):
            ranges[name] = (value - 2.0, value + 2.0)
        elif (
            "fraction" in name
            or name.endswith("_strength")
            or "response" in name
            or name.endswith("_penalty")
            or "baseline_index" in name
        ):
            ranges[name] = (max(0.0, value - 0.10), min(1.0, value + 0.10))
        else:
            ranges[name] = (max(value * 0.8, 1e-9), value * 1.2)
    outputs = tuple(output_metrics(simulate(base_request, chill_model=ChillModel.CHILL_HOURS)))
    samples: dict[tuple[str, str], list[float]] = {
        (name, output_name): [] for name in names for output_name in outputs
    }
    rng = random.Random(seed)
    for trajectory in range(trajectories):
        levels = {name: float(rng.choice((0, 1))) for name in names}
        initial_overrides = {name: ranges[name][int(levels[name])] for name in names}
        initial_parameters = reference_parameter_set(initial_overrides, chill_model="CHILL_HOURS")
        current_request = replace(base_request, parameter_set=initial_parameters)
        current_output = simulate(current_request, chill_model=ChillModel.CHILL_HOURS)
        current_metrics = output_metrics(current_output)
        order = list(names)
        rng.shuffle(order)
        for name in order:
            prior_level = levels[name]
            next_level = 0.5 if prior_level in {0.0, 1.0} else (1.0 if trajectory % 2 == 0 else 0.0)
            new_overrides = {
                parameter_name: ranges[parameter_name][int(levels[parameter_name])]
                if levels[parameter_name] in {0.0, 1.0}
                else sum(ranges[parameter_name]) / 2.0
                for parameter_name in names
            }
            new_overrides[name] = (
                ranges[name][0]
                if next_level == 0.0
                else (ranges[name][1] if next_level == 1.0 else sum(ranges[name]) / 2.0)
            )
            levels[name] = next_level
            current_request = replace(
                current_request,
                parameter_set=reference_parameter_set(new_overrides, chill_model="CHILL_HOURS"),
            )
            new_output = simulate(current_request, chill_model=ChillModel.CHILL_HOURS)
            new_metrics = output_metrics(new_output)
            for output_name in outputs:
                reference_scale = max(
                    abs(current_metrics[output_name]), abs(new_metrics[output_name]), 1.0
                )
                step = next_level - prior_level
                effect = (
                    (new_metrics[output_name] - current_metrics[output_name])
                    / reference_scale
                    / step
                )
                samples[(name, output_name)].append(effect)
            current_metrics = new_metrics
    rows: list[dict[str, str]] = []
    for output_name in outputs:
        magnitudes = {
            name: sum(abs(item) for item in samples[(name, output_name)])
            / max(len(samples[(name, output_name)]), 1)
            for name in names
        }
        ranked = sorted(magnitudes.values())
        high_cut = ranked[max(0, math.ceil(len(ranked) * 0.75) - 1)]
        low_cut = ranked[max(0, math.ceil(len(ranked) * 0.25) - 1)]
        for name in names:
            effects = samples[(name, output_name)]
            mu_star = magnitudes[name]
            sigma = 0.0
            if len(effects) > 1:
                mean = sum(effects) / len(effects)
                sigma = math.sqrt(sum((item - mean) ** 2 for item in effects) / (len(effects) - 1))
            if mu_star == 0.0:
                classification = "NEGLIGIBLE_WITHIN_TESTED_RANGE"
            elif mu_star >= high_cut:
                classification = "HIGH_LEVERAGE"
            elif mu_star <= low_cut:
                classification = "LOW_LEVERAGE"
            else:
                classification = "MEDIUM_LEVERAGE"
            rows.append(
                {
                    "parameter_name": name,
                    "output_name": output_name,
                    "range_low": f"{ranges[name][0]:.12g}",
                    "reference_value": f"{base_parameters[name].value:.12g}",
                    "range_high": f"{ranges[name][1]:.12g}",
                    "range_basis": "PREDECLARED_SYNTHETIC_REFERENCE_RANGE; not fitted from business/harvest data",
                    "method": "DETERMINISTIC_MORRIS_ELEMENTARY_EFFECT_SCREEN",
                    "trajectory_count": str(trajectories),
                    "mu_star_normalized": f"{mu_star:.12g}",
                    "sigma_normalized": f"{sigma:.12g}",
                    "interaction_suspected": str(sigma >= mu_star and mu_star > 0.0).lower(),
                    "leverage_class": classification,
                }
            )
    return rows


def _classify_parameter(parameter: dict[str, str]) -> tuple[str, str, str]:
    name = parameter["parameter_name"]
    role = parameter["parameter_role"]
    upper = name.upper()
    if role in {"DIRECT_LITERATURE_VALUE", "LITERATURE_PRIOR", "REFERENCE_METHOD_CONSTANT"}:
        return (
            "LITERATURE_PRIOR_ONLY",
            "Fixed or prior-sourced method value; not estimated from this V1 evidence.",
            "source publication/method identity; cultivar/system scope before any future use",
        )
    if any(token in upper for token in ("CHILL", "FORCING", "BLOOM", "RIPE", "THERMAL", "STAGE")):
        return (
            "CONDITIONALLY_IDENTIFIABLE",
            "Requires the relevant hourly drivers and independent phenology/cohort anchors.",
            "hourly inside temperature plus state-transition date/count anchors",
        )
    if any(
        token in upper
        for token in (
            "FLOWER_BUD",
            "POLLINATION",
            "FRUIT_SET",
            "SEED",
            "BERRY_WEIGHT",
            "MARKETABLE",
        )
    ):
        return (
            "OBSERVATION_DEPENDENT",
            "Requires matched reproductive denominators and repeated observations at a declared grain.",
            "bud/flower/set counts, cultivar scope, and cohort-linked berry observations",
        )
    if any(
        token in upper for token in ("SOURCE", "SINK", "RESERVE", "CARRYOVER", "CROP_LOAD", "VIGOR")
    ):
        return (
            "CONFOUNDED",
            "Composite latent source/sink/carryover effects are not separately identified by final mass alone.",
            "repeated canopy/source proxies, crop-load observations, fruit growth, and inter-season anchors",
        )
    if any(token in upper for token in ("PRUNING", "CANE", "SHOOT", "MICROCLIMATE")):
        return (
            "OBSERVATION_DEPENDENT",
            "Needs executed management scope/intensity and before/after structural or indoor environment observations.",
            "event-level execution records plus scoped structural and microclimate observations",
        )
    return (
        "UNIDENTIFIABLE_IN_V1",
        "No independent observation path in the current theoretical V1 contract isolates this coefficient.",
        "new authoritative state observations and parameter-specific design",
    )


def build_parameter_identifiability_rows(root: Path = REPOSITORY_ROOT) -> list[dict[str, str]]:
    rows = load_csv(root / "docs/v0-9/s3/literature-model-parameter-registry-r1.csv")
    result: list[dict[str, str]] = []
    for row in rows:
        status, reason, observation = _classify_parameter(row)
        result.append(
            {
                "parameter_id": row["parameter_id"],
                "module": row["module"],
                "parameter_name": row["parameter_name"],
                "parameter_role": row["parameter_role"],
                "identifiability_status": status,
                "structural_scope": "THEORETICAL_STRUCTURE_ONLY; not an enterprise-data statistical confidence claim",
                "confounding_or_condition": reason,
                "minimum_observation_anchor": observation,
                "production_parameter": "false",
            }
        )
    return result


def build_parameter_observation_rows(root: Path = REPOSITORY_ROOT) -> list[dict[str, str]]:
    params = load_csv(root / "docs/v0-9/s3/literature-model-parameter-registry-r1.csv")
    s2 = json.loads((root / S2_EVIDENCE_PATH).read_text(encoding="utf-8"))["asset_findings"]
    result: list[dict[str, str]] = []
    for row in params:
        status, rationale, minimum = _classify_parameter(row)
        name = row["parameter_name"].lower()
        availability = "NO_MATCHING_AUTHORIZED_OBSERVATION_REPORTED_IN_S2"
        if status == "LITERATURE_PRIOR_ONLY":
            availability = "LITERATURE_OR_METHOD_REFERENCE_ONLY_NOT_ENTERPRISE_DATA"
        elif "chill" in name:
            availability = (
                f"chilling_derivability={s2['chilling_derivability']}; "
                f"greenhouse_hourly_temperature={s2['greenhouse_hourly_temperature']}; "
                f"direct_phenology_observations={s2['phenology_direct_observations']}"
            )
        elif "forcing" in name or "bud_swell" in name or "bud_break" in name or "bloom" in name:
            availability = (
                f"forcing_derivability={s2['forcing_derivability']}; "
                f"direct_phenology_observations={s2['phenology_direct_observations']}; "
                f"greenhouse_hourly_temperature={s2['greenhouse_hourly_temperature']}"
            )
        elif "prun" in name or "cane" in name or "shoot" in name:
            availability = (
                "executed_management_event_types="
                f"{s2['management_event_types_with_executed_records']}; "
                "authoritative plant-structure census not reported"
            )
        elif "microclimate" in name or "temperature" in name:
            availability = str(s2["greenhouse_hourly_temperature"])
        elif any(token in name for token in ("flower", "pollination", "fruit_set", "seed")):
            availability = (
                f"direct_phenology_observations={s2['phenology_direct_observations']}; "
                "executed pollination/fruit-set observations not reported"
            )
        elif any(token in name for token in ("berry", "ripe", "marketable", "development")):
            availability = (
                f"harvest_is_maturity_observation={str(s2['harvest_is_maturity_observation']).lower()}; "
                "empirical bloom-to-ripe cohort lineage not reported"
            )
        elif any(token in name for token in ("source", "sink", "reserve", "crop_load", "vigor")):
            availability = (
                "authoritative canopy/crop-load/reserve observations not reported; "
                "current states remain latent/proxy-only"
            )
        elif "area" in name:
            availability = f"accepted_area_base_season_rows={s2['accepted_area_base_season_rows']}"
        result.append(
            {
                "parameter_id": row["parameter_id"],
                "parameter_name": row["parameter_name"],
                "identifiability_status": status,
                "minimum_observations": minimum,
                "current_s2_availability": availability,
                "future_calibration_gap": "OPEN; S2 reports synthetic-only biological calibration readiness",
                "leakage_policy": "future prospective actuals must be sealed after prediction issuance",
                "notes": rationale,
            }
        )
    return result


ABSTRACTION_DECISIONS = {
    "EQA001": (
        "RESTRICT_DOMAIN",
        "LOW",
        "Synthetic age-bin bookkeeping only; no universal cane-age productivity coefficient.",
    ),
    "EQA004": (
        "RESTRICT_DOMAIN",
        "HIGH",
        "Normalized reserve bookkeeping; not carbon mass balance or a calibrated reserve law.",
    ),
    "EQA005": (
        "RESTRICT_DOMAIN",
        "HIGH",
        "Weighted induction is a genotype-scoped scenario response, not a validated universal bud-initiation equation.",
    ),
    "EQA012": (
        "ACCEPT_V1",
        "MEDIUM",
        "Continuous forcing-progress interpolation is retained as a deterministic cohort-generation abstraction.",
    ),
    "EQA013": (
        "RESTRICT_DOMAIN",
        "HIGH",
        "Pollination opportunity proxy only; it is not fertilization or observed pollinator efficacy.",
    ),
    "EQA016": (
        "RESTRICT_DOMAIN",
        "HIGH",
        "Dimensionless source proxy only; no photosynthetic flux claim.",
    ),
    "EQA017": (
        "RESTRICT_DOMAIN",
        "HIGH",
        "Relative sink weights remain explicit scenario assumptions.",
    ),
    "EQA018": (
        "RESTRICT_DOMAIN",
        "HIGH",
        "Bounded source/sink sufficiency is a proxy, not a universal ratio law.",
    ),
    "EQA019": (
        "RESTRICT_DOMAIN",
        "HIGH",
        "Double-logistic reference curve is selectable and synthetic; not a blueberry-wide fit.",
    ),
    "EQA021": (
        "RESTRICT_DOMAIN",
        "HIGH",
        "Logistic maturity distribution spreads ripening; no universal kernel is asserted.",
    ),
    "EQA023": (
        "RESTRICT_DOMAIN",
        "HIGH",
        "Carryover outputs are normalized latent indices; no empirical coefficient or buds/plant scale is claimed.",
    ),
    "EQA024": (
        "RESTRICT_DOMAIN",
        "HIGH",
        "Greenhouse/heating/shade deltas are explicit synthetic scenario inputs, not defaults.",
    ),
    "EQA025": (
        "RESTRICT_DOMAIN",
        "HIGH",
        "Piecewise temperature suitability is an uncalibrated scenario response.",
    ),
    "EQA026": (
        "ACCEPT_V1",
        "LOW",
        "Event windows gate a synthetic opportunity index only; no bee behavior simulation.",
    ),
    "EQA027": (
        "RESTRICT_DOMAIN",
        "HIGH",
        "Seed/source modifiers are latent scenario effects; no seed count is fabricated.",
    ),
    "EQA028": (
        "RECLASSIFY_RESEARCH_ONLY",
        "HIGH",
        "Three curve families remain theoretical alternatives; no production winner is selected.",
    ),
    "EQA029": (
        "REQUIRE_NEW_AUTHORITY",
        "HIGH",
        "Treatment event semantics are supported, efficacy/dose response is not; keep effect synthetic-only.",
    ),
    "EQA030": (
        "ACCEPT_V1",
        "MEDIUM",
        "Modular causal skeleton is accepted as simulator architecture, not as a validated predictive law.",
    ),
}


def build_abstraction_review_rows(root: Path = REPOSITORY_ROOT) -> list[dict[str, str]]:
    equations = load_csv(root / "docs/v0-9/s3/model-equation-authority-register-r1.csv")
    explicit = [
        row for row in equations if row["equation_authority"] == "EXPLICIT_MODEL_ABSTRACTION"
    ]
    if len(explicit) != 18:
        raise ValueError("Expected 18 explicit S3 abstractions")
    rows: list[dict[str, str]] = []
    for equation in explicit:
        equation_id = equation["equation_id"]
        decision, risk, rationale = ABSTRACTION_DECISIONS[equation_id]
        rows.append(
            {
                "equation_id": equation_id,
                "module": equation["module"],
                "s0_claim_ids": equation["s0_claim_ids"],
                "review_decision": decision,
                "risk_level": risk,
                "production_use": "PROHIBITED",
                "required_restriction": rationale,
                "unresolved_critical": "false",
            }
        )
    return rows


def build_confounding_rows() -> list[dict[str, str]]:
    records = [
        (
            "FLOWER_BUD_COUNT_X_FRUIT_SET_PROBABILITY",
            "Only resulting fruit count is observed",
            "flower-bud cohort count; effective flowers; fruit-set sample with denominator",
            "CONDITIONALLY_IDENTIFIABLE",
        ),
        (
            "POLLINATION_SUFFICIENCY_X_FRUIT_SET_RESPONSE",
            "Pollination opportunity and cultivar fruit-set response can produce the same set count",
            "pollination window/opportunity plus matched flower and fruit-set observations",
            "CONFOUNDED",
        ),
        (
            "PLANT_DENSITY_X_PER_PLANT_PRODUCTIVITY",
            "Area-level mass is their product",
            "plant density census and per-plant cohort/ripe-mass observation",
            "CONDITIONALLY_IDENTIFIABLE",
        ),
        (
            "SOURCE_CAPACITY_X_SOURCE_SINK_MODIFIER",
            "Composite supply and response coefficient can compensate",
            "leaf/canopy/radiation proxy plus repeated fruit growth and crop-load observations",
            "CONFOUNDED",
        ),
        (
            "THERMAL_REQUIREMENT_X_GREENHOUSE_TEMPERATURE_EFFECT",
            "Same phenology date shift can be produced by threshold or microclimate change",
            "inside hourly temperature plus independent budbreak/bloom anchors",
            "CONDITIONALLY_IDENTIFIABLE",
        ),
        (
            "CHILL_MODEL_FAMILY_X_CULTIVAR_CHILL_REQUIREMENT",
            "Alternative response curves and cultivar threshold may explain similar release timing",
            "same hourly record across winters and direct dormancy/budbreak anchors; keep candidate family identity",
            "CONFOUNDED",
        ),
        (
            "BERRY_WEIGHT_X_MARKETABLE_FRACTION",
            "Mature mass observes the product unless size and grade are separately sampled",
            "cohort berry-weight sample plus independent marketable-grade sample",
            "CONDITIONALLY_IDENTIFIABLE",
        ),
        (
            "BLOOM_COHORT_SIZE_X_FRUIT_RETENTION",
            "Final fruit quantity alone does not isolate initial bloom from losses",
            "tagged bloom cohort and repeated set/retention counts",
            "CONFOUNDED",
        ),
        (
            "RESERVE_CARRYOVER_X_VIGOR_CARRYOVER",
            "Both latent carryover indices contribute to next-season bud potential",
            "postharvest reserve proxy/assay, vigor, and next-season bud census",
            "OBSERVATION_DEPENDENT",
        ),
    ]
    return [
        {
            "confounding_id": f"CF{index:03d}",
            "parameter_group": group,
            "mechanism": mechanism,
            "minimum_disambiguating_observations": observations,
            "status": status,
            "enterprise_data_used": "false",
        }
        for index, (group, mechanism, observations, status) in enumerate(records, start=1)
    ]


def build_failure_mode_rows() -> list[dict[str, str]]:
    items = [
        (
            "WRONG_PRODUCTION_SYSTEM_ASSIGNMENT",
            "Partially",
            "Fail closed when unbound; do not infer from region",
            "phenology path, dormancy and bloom timing",
        ),
        (
            "INCORRECT_CHILL_MODEL_OR_CULTIVAR_BINDING",
            "Yes",
            "Require model identity and scoped parameter provenance",
            "dormancy release and downstream timing",
        ),
        (
            "WRONG_CULTIVAR_PARAMETER_FAMILY",
            "Partially",
            "Reject missing cultivar binding for cultivar-scoped parameters",
            "bud formation, set, development and maturity",
        ),
        (
            "EXTREME_GREENHOUSE_TEMPERATURE",
            "Yes",
            "Finite/range checks plus explicit warning outside declared scenario range",
            "chill, forcing, pollination and fruit-growth response",
        ),
        (
            "MISSING_MANAGEMENT_EVENT",
            "No, unless independently observed",
            "Keep event unknown; do not silently assume executed management",
            "structure, phenology and crop load",
        ),
        (
            "UNREALISTIC_CROP_LOAD",
            "Partially",
            "Nonnegative/bounds checks; emit scenario-domain warning",
            "source/sink sufficiency, berry size and carryover",
        ),
        (
            "INSUFFICIENT_SOURCE_CAPACITY",
            "Partially",
            "Bound proxy sufficiency; flag source proxy as latent",
            "fruit retention, berry growth and reserve",
        ),
        (
            "POLLINATION_FAILURE",
            "Partially",
            "Require explicit pollination/fruit-set state or retain uncertainty",
            "fruit set, seed proxy, maturity and yield",
        ),
        (
            "INITIAL_STATE_UNCERTAINTY",
            "No",
            "Require declared initial-state source or scenario-only label",
            "all downstream state and yield outputs",
        ),
        (
            "INTERSEASON_STATE_UNCERTAINTY",
            "No",
            "Carry state with provenance; do not reset latent state silently",
            "bud potential, vigor and next-season yield",
        ),
        (
            "COHORT_LINEAGE_LOSS_OR_DUPLICATION",
            "Yes",
            "Fail closed on missing/duplicate cohort IDs and conservation violation",
            "maturity mass and timing",
        ),
        (
            "PARAMETER_RANGE_OR_UNIT_MISMATCH",
            "Yes",
            "Fail closed on unit/domain violation; retain parameter hash",
            "all outputs using the parameter",
        ),
    ]
    return [
        {
            "failure_mode_id": f"FM{index:03d}",
            "failure_mode": mode,
            "detectable": detectable,
            "fail_closed_or_control": control,
            "warning_policy": (
                "Emit a scoped warning and preserve an uncertainty flag; never substitute a guessed value."
                if detectable != "Yes"
                else "Emit a warning when outside the declared synthetic/model domain."
            ),
            "output_uncertainty_affected": affected,
            "warning_or_uncertainty_effect": affected,
        }
        for index, (mode, detectable, control, affected) in enumerate(items, start=1)
    ]


def build_future_calibration_rows() -> list[dict[str, str]]:
    s2 = json.loads((REPOSITORY_ROOT / S2_EVIDENCE_PATH).read_text(encoding="utf-8"))
    current_status = {
        "scope_identity": "AREA_AUTHORITY_PRESENT_FOR_BASE_SEASON; CULTIVAR_AREA_GRAIN_LIMITATION; PRODUCTION_SYSTEM_UNASSIGNED",
        "plant_structure": "NO_AUTHORITATIVE_PLANT_DENSITY_TREE_AGE_PRODUCTIVE_SHOOT_OR_BUD_CENSUS_REPORTED",
        "production_system": "0_OF_117_OBSERVED_ASSIGNMENTS; BUSINESS_CONFIRMATION_REQUIRED",
        "pruning_events": "0_EXECUTED_MANAGEMENT_EVENT_TYPES_WITH_AUTHORIZED_RECORDS",
        "forcing_events": "0_EXECUTED_MANAGEMENT_EVENT_TYPES_WITH_AUTHORIZED_RECORDS",
        "indoor_hourly_temperature": str(s2["asset_findings"]["greenhouse_hourly_temperature"]),
        "dormancy_anchor": "NO_DIRECT_PHENOLOGY_OBSERVATIONS_REPORTED",
        "bloom_anchors": "NO_DIRECT_PHENOLOGY_OBSERVATIONS_REPORTED",
        "pollination_and_set": "NO_DIRECT_POLLINATION_OR_FRUIT_SET_OBSERVATIONS_REPORTED",
        "fruit_cohort_growth": "NO_EMPIRICAL_BLOOM_TO_RIPE_COHORT_LINEAGE_REPORTED",
        "daily_harvest_output": "HISTORICAL_HARVEST_TARGET_AVAILABLE; NOT_BIOLOGICAL_MATURITY_TRUTH",
        "canopy_source": "NO_AUTHORITATIVE_CANOPY_OR_LEAF_AREA_OBSERVATION_REPORTED",
        "crop_load": "NO_DIRECT_FRUIT_NUMBER_OR_CROP_LOAD_OBSERVATION_REPORTED",
        "root_zone_environment": "NO_GREENHOUSE_ROOT_ZONE_SENSOR_DATA_REPORTED",
        "pollination_context": "NO_EXECUTED_POLLINATION_EVENT_OR_SEED_SAMPLE_REPORTED",
        "fruit_quality": "NO_COHORT_LINKED_BERRY_SIZE_OR_MARKETABLE_GRADE_SAMPLE_REPORTED",
        "reserve_assay": "UNOBSERVABLE_IN_CURRENT_ENTERPRISE_AUDIT",
        "photosynthesis": "UNOBSERVABLE_IN_CURRENT_ENTERPRISE_AUDIT",
        "advanced_cohort_tagging": "NEW_PROSPECTIVE_COLLECTION_REQUIRED",
        "root_growth": "UNOBSERVABLE_IN_CURRENT_ENTERPRISE_AUDIT",
    }
    items = [
        (
            "scope_identity",
            "Base/subfarm/cultivar-to-area binding",
            "S1 identity, production system, cultivar family",
            "verified mapping and productive-area authority",
            "P0_REQUIRED",
        ),
        (
            "plant_structure",
            "Plant density, tree age, productive shoots/canes and flower-bud census",
            "structural and flower-bud states",
            "same-scope census with denominator and sampling method",
            "P0_REQUIRED",
        ),
        (
            "production_system",
            "DECIDUOUS_NATURAL / DECIDUOUS_FORCING / EVERGREEN assignment",
            "system-specific legal state path",
            "business-confirmed system assignment per subfarm-season",
            "P0_REQUIRED",
        ),
        (
            "pruning_events",
            "Executed pruning date/type/intensity/scope",
            "fruiting wood, bud potential, leaf/source and future shoots",
            "event log; intensity unit and scope required",
            "P0_REQUIRED",
        ),
        (
            "forcing_events",
            "Greenhouse close/open and heating start/stop with intensity",
            "effective microclimate and forcing",
            "timestamped executed event log",
            "P0_REQUIRED",
        ),
        (
            "indoor_hourly_temperature",
            "Greenhouse air temperature at hourly resolution",
            "chilling/forcing/thermal development",
            "calibrated sensor, time zone and gap/quality flags",
            "P0_REQUIRED",
        ),
        (
            "dormancy_anchor",
            "Dormancy/budbreak observation date and method",
            "chill requirement and release timing",
            "standardized cultivar-scoped observation protocol",
            "P0_REQUIRED",
        ),
        (
            "bloom_anchors",
            "10%, 50%, 90% bloom dates with denominator/method",
            "bloom progress and bloom cohort origin",
            "repeatable sample frame and observed dates",
            "P0_REQUIRED",
        ),
        (
            "pollination_and_set",
            "Effective flowers and fruit-set sample with denominator",
            "pollination/fruit-set probability",
            "matched flowers-to-set-fruit sample by cultivar/scope",
            "P0_REQUIRED",
        ),
        (
            "fruit_cohort_growth",
            "Tagged bloom cohort with repeated fruit stage/count/weight through color break and ripe",
            "fruit growth, maturity distribution and cohort lineage",
            "repeated cohort sampling; distinguish ripe from harvested",
            "P0_REQUIRED",
        ),
        (
            "daily_harvest_output",
            "Daily actual harvest quantity and operational exclusions",
            "separate harvest-state calibration/output audit",
            "authoritative source/date/quantity ledger; not a ripe-state substitute",
            "P0_REQUIRED",
        ),
        (
            "canopy_source",
            "Leaf area/retention, canopy health and radiation proxy",
            "source-capacity proxy",
            "repeat at key growth stages; method-specific units",
            "P1_HIGH_VALUE",
        ),
        (
            "crop_load",
            "Fruit number/load sample and fruit-thinning event",
            "sink demand and thinning response",
            "repeat by stage with explicit plant/subfarm denominator",
            "P1_HIGH_VALUE",
        ),
        (
            "root_zone_environment",
            "Root-zone temperature and substrate moisture/EC when available",
            "environmental stress and source/sink context",
            "sensor or repeat manual observations with unit/quality",
            "P1_HIGH_VALUE",
        ),
        (
            "pollination_context",
            "Pollination window, pollinator introduction and seed-index sample",
            "pollination and latent seed effect",
            "event log plus sampled cohort; seed count optional",
            "P1_HIGH_VALUE",
        ),
        (
            "fruit_quality",
            "Marketable fraction/grade and berry size by cohort",
            "berry mass × marketable fraction separation",
            "independent size and grade sample",
            "P1_HIGH_VALUE",
        ),
        (
            "reserve_assay",
            "Carbohydrate reserve assay or validated proxy",
            "reserve/carryover state",
            "assay method and tissue/date protocol",
            "P2_ADVANCED",
        ),
        (
            "photosynthesis",
            "Leaf gas exchange / source capacity experiments",
            "source proxy structure",
            "controlled study; not a routine sensor mandate",
            "P2_ADVANCED",
        ),
        (
            "advanced_cohort_tagging",
            "High-frequency cohort tracking and detailed stage imaging",
            "maturity-kernel shape and within-plant heterogeneity",
            "research sub-sample only",
            "P2_ADVANCED",
        ),
        (
            "root_growth",
            "Root growth/biomass sampling",
            "root sink demand",
            "targeted destructive or validated proxy study",
            "P2_ADVANCED",
        ),
    ]
    return [
        {
            "field_id": field_id,
            "field_name": field_name,
            "identifiability_target": state,
            "minimum_observation_design": design,
            "priority": priority,
            "current_data_status_from_s2": current_status[field_id],
            "may_use_2025_2026_for_selection": "false",
        }
        for field_id, field_name, state, design, priority in items
    ]


def build_abstraction_quarantine_rows(root: Path = REPOSITORY_ROOT) -> list[dict[str, str]]:
    edges = json.loads(
        (root / "docs/v0-9/s1/causal-edge-registry-r1.json").read_text(encoding="utf-8")
    )
    quarantined = edges["quarantined_mechanisms"]
    expected = {"C005", "C009", "C011", "C016", "C024", "C027"}
    if {item["claim_id"] for item in quarantined} != expected:
        raise ValueError("S1 quarantine no longer matches the six pinned S0 not-ready mechanisms")
    return cast(list[dict[str, str]], quarantined)


def _management_event(
    request: SimulationInput,
    event_type: EventType,
    *,
    day_offset: int,
    intensity: float | None = None,
    event_id: str,
) -> ManagementEvent:
    return ManagementEvent(
        event_id=event_id,
        event_type=event_type,
        event_datetime=request.environment[day_offset * 24].timestamp,
        intensity=intensity,
        intensity_unit="fraction_0_1" if intensity is not None else None,
        observed_or_planned="PLANNED",
        source_reference="S4_SYNTHETIC_COUNTERFACTUAL_ONLY",
        target="SYNTHETIC_PLANT",
    )


def _simulate(
    request: SimulationInput, *, curve: FruitGrowthCurve = FruitGrowthCurve.DOUBLE_LOGISTIC
) -> SimulationOutput:
    return simulate(request, chill_model=ChillModel.CHILL_HOURS, fruit_growth_curve=curve)


def _first_index(output: SimulationOutput, predicate: Any) -> int | None:
    for index, point in enumerate(output.daily_states):
        if predicate(point):
            return index
    return None


def run_synthetic_validation() -> dict[str, Any]:
    state_ids = set(
        json.loads(
            (REPOSITORY_ROOT / "docs/v0-9/s1/biological-state-registry-r1.json").read_text(
                encoding="utf-8"
            )
        )["phenology_state_machine"]["state_ids"]
    )
    golden_outputs: dict[str, SimulationOutput] = {}
    golden_requests: dict[str, SimulationInput] = {}
    invariant_checks = 0
    for scenario in GOLDEN_SCENARIOS:
        request = build_scenario(scenario)
        output = _simulate(request)
        checks = validate_output_contract(output, request)
        if not all(checks.values()):
            raise ValueError(f"S4 synthetic invariant failure in {scenario}: {checks}")
        if any(point.phenology_stage not in state_ids for point in output.daily_states):
            raise ValueError(f"Unregistered phenology state emitted by {scenario}")
        invariant_checks += len(checks) + 1
        golden_requests[scenario] = request
        golden_outputs[scenario] = output

    robustness_rows: list[dict[str, Any]] = []
    for scenario, request in golden_requests.items():
        weight = next(
            item
            for item in request.parameter_set.parameters
            if item.name == "potential_berry_weight_g"
        )
        if weight.value is None:
            raise ValueError(f"Synthetic robustness parameter {weight.name} is unbound")
        for level, value in (
            ("LOWER_BOUND", weight.value * 0.8),
            ("REFERENCE", weight.value),
            ("UPPER_BOUND", weight.value * 1.2),
        ):
            parameters = replace(
                request.parameter_set,
                parameters=tuple(
                    replace(item, value=value) if item.name == weight.name else item
                    for item in request.parameter_set.parameters
                ),
            )
            robustness_request = replace(
                request,
                simulation_id=f"{request.simulation_id}-ROBUST-{level}",
                parameter_set=parameters,
            )
            robustness_output = _simulate(robustness_request)
            checks = validate_output_contract(robustness_output, robustness_request)
            if not all(checks.values()):
                raise ValueError(
                    f"Scenario parameter-bound robustness failed: {scenario}/{level}: {checks}"
                )
            robustness_rows.append(
                {
                    "scenario": scenario,
                    "parameter_name": weight.name,
                    "level": level,
                    "value": value,
                    "output_invariants_pass": True,
                    "scenario_only": parameters.scenario_only,
                    "production_eligible_parameter_count": sum(
                        item.production_eligible for item in parameters.parameters
                    ),
                }
            )

    curve_checks = 0
    curve_values: dict[str, list[float]] = {}
    for curve in FruitGrowthCurve:
        values: list[float] = []
        for thermal_age in range(0, 901, 5):
            if curve is FruitGrowthCurve.DOUBLE_LOGISTIC:
                value = double_sigmoid_growth_fraction(
                    float(thermal_age),
                    stage1_midpoint_dd=110.0,
                    stage2_midpoint_dd=300.0,
                    width_dd=35.0,
                )
            elif curve is FruitGrowthCurve.DOUBLE_GOMPERTZ:
                value = double_gompertz_growth_fraction(
                    float(thermal_age),
                    stage1_midpoint_dd=110.0,
                    stage2_midpoint_dd=300.0,
                    width_dd=35.0,
                )
            else:
                value = fruit_growth_fraction(
                    float(thermal_age),
                    curve=curve,
                    stage1_midpoint_dd=110.0,
                    stage2_midpoint_dd=300.0,
                    width_dd=35.0,
                    final_age_dd=430.0,
                )
            values.append(value)
        if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in values):
            raise ValueError(f"Fruit curve range failure: {curve.value}")
        if any(after + 1e-12 < before for before, after in zip(values, values[1:], strict=False)):
            raise ValueError(f"Fruit curve non-monotonic: {curve.value}")
        curve_values[curve.value] = values
        curve_checks += len(values) + 1
    if not (
        curve_values[FruitGrowthCurve.DOUBLE_LOGISTIC.value][-1] > 0.99
        and curve_values[FruitGrowthCurve.DOUBLE_GOMPERTZ.value][-1] > 0.99
        and curve_values[FruitGrowthCurve.STAGEWISE_THERMAL.value][-1] == 1.0
    ):
        raise ValueError("Fruit growth curves do not reach finite mature size")

    maturity_values = [
        maturity_cumulative_fraction(float(age), median_dd=430.0, width_dd=55.0)
        for age in range(-100, 901, 5)
    ]
    if any(not 0.0 <= value <= 1.0 for value in maturity_values) or any(
        after + 1e-12 < before
        for before, after in zip(maturity_values, maturity_values[1:], strict=False)
    ):
        raise ValueError("Maturity cumulative fraction is not bounded and monotone")
    if any(
        after - before < -1e-12
        for before, after in zip(maturity_values, maturity_values[1:], strict=False)
    ):
        raise ValueError("Daily newly ripe fraction is negative")

    chill_series = [-1.0, 2.0, 5.0, 8.0, 11.0, 15.0, 20.0, 4.0, 7.0, 10.0] * 24
    dynamic_constants = {
        "dynamic_model_e0": 4153.5,
        "dynamic_model_e1": 12888.8,
        "dynamic_model_a0": 139500.0,
        "dynamic_model_a1": 2.567e18,
        "dynamic_model_slope": 1.6,
        "dynamic_model_tf_kelvin": 277.0,
    }
    chill_totals: dict[str, float] = {}
    for model in ChillModel:
        constants = dynamic_constants if model is ChillModel.DYNAMIC_CHILL_PORTIONS else None
        full = ChillAccumulator(model, constants)
        for temperature in chill_series:
            full.add_hour(temperature)
        chunked = ChillAccumulator(model, constants)
        for chunk in (chill_series[:79], chill_series[79:151], chill_series[151:]):
            for temperature in chunk:
                chunked.add_hour(temperature)
        if not math.isclose(full.total, chunked.total, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"Chunked chill continuation mismatch: {model.value}")
        chill_totals[model.value] = full.total
    if len({round(value, 10) for value in chill_totals.values()}) != 3:
        raise ValueError(
            "Chilling candidate identity was lost; candidate interpretations should differ"
        )

    base = build_scenario("deciduous-natural")
    pruning_rows: list[dict[str, Any]] = []
    pruning_outputs: dict[str, SimulationOutput] = {}
    for label, intensity in (
        ("NO_PRUNING", None),
        ("LIGHT", 0.15),
        ("MODERATE", 0.40),
        ("HEAVY", 0.75),
    ):
        events = (
            ()
            if intensity is None
            else (
                _management_event(
                    base,
                    EventType.DORMANT_PRUNING,
                    day_offset=120,
                    intensity=intensity,
                    event_id=f"prune-{label.lower()}",
                ),
            )
        )
        output = _simulate(replace(base, management_events=events))
        pruning_outputs[label] = output
        pruning_rows.append(
            {
                "counterfactual": "PRUNING",
                "level": label,
                "fruiting_wood_final": output.daily_states[-1].fruiting_wood_index,
                "leaf_area_final": output.daily_states[-1].leaf_area_index,
                "flower_bud_potential_final": output.daily_states[
                    -1
                ].flower_bud_potential_per_plant,
                "future_shoot_potential_final": output.daily_states[-1].vegetative_shoot_potential,
                "source_supply_final": output.daily_states[-1].source_supply_index,
                "crop_load_final": output.daily_states[-1].fruit_load_per_plant,
                "berry_weight_potential_mean": sum(
                    x.potential_berry_weight_g for x in output.fruit_development_cohorts
                )
                / max(len(output.fruit_development_cohorts), 1),
                "season_biological_yield_kg": output_metrics(output)["season_biological_yield_kg"],
                "expected_behavior_class": "STRUCTURAL_EFFECT_REQUIRED; SEASON_TOTAL_DIRECTION_CONTEXT_DEPENDENT",
                "trace_count": sum(len(items) for items in output.trace.values()),
            }
        )
    if not (
        pruning_outputs["HEAVY"].daily_states[120].fruiting_wood_index
        < pruning_outputs["LIGHT"].daily_states[120].fruiting_wood_index
        < pruning_outputs["NO_PRUNING"].daily_states[120].fruiting_wood_index
        and pruning_outputs["HEAVY"].daily_states[120].leaf_area_index
        < pruning_outputs["LIGHT"].daily_states[120].leaf_area_index
        < pruning_outputs["NO_PRUNING"].daily_states[120].leaf_area_index
        and pruning_outputs["HEAVY"].daily_states[120].flower_bud_potential_per_plant
        < pruning_outputs["LIGHT"].daily_states[120].flower_bud_potential_per_plant
        < pruning_outputs["NO_PRUNING"].daily_states[120].flower_bud_potential_per_plant
        and pruning_outputs["HEAVY"].daily_states[120].vegetative_shoot_potential
        > pruning_outputs["LIGHT"].daily_states[120].vegetative_shoot_potential
        and pruning_outputs["HEAVY"].daily_states[120].source_supply_index
        < pruning_outputs["NO_PRUNING"].daily_states[120].source_supply_index
    ):
        raise ValueError(
            "Pruning counterfactual failed the required multi-state structural response"
        )

    flower_rows: list[dict[str, Any]] = []
    flower_outputs: dict[str, SimulationOutput] = {}
    for label, intensity in (("NONE", None), ("LIGHT", 0.15), ("MODERATE", 0.35), ("HEAVY", 0.70)):
        events = (
            ()
            if intensity is None
            else (
                _management_event(
                    base,
                    EventType.FLOWER_THINNING,
                    day_offset=165,
                    intensity=intensity,
                    event_id=f"thin-{label.lower()}",
                ),
            )
        )
        output = _simulate(replace(base, management_events=events))
        flower_outputs[label] = output
        flower_rows.append(
            {
                "counterfactual": "FLOWER_THINNING",
                "level": label,
                "effective_flower_load": sum(
                    item.flower_quantity_per_plant for item in output.bloom_cohorts
                ),
                "fruit_number": sum(
                    item.fruit_number_per_plant for item in output.fruit_set_cohorts
                ),
                "leaf_area_final": output.daily_states[-1].leaf_area_index,
                "source_sink_sufficiency_mean": sum(
                    x.source_sink_sufficiency for x in output.daily_states
                )
                / len(output.daily_states),
                "season_biological_yield_kg": output_metrics(output)["season_biological_yield_kg"],
                "expected_behavior_class": "FLOWER_LOAD_AND_FRUIT_NUMBER_DIRECTION_REQUIRED; YIELD_DIRECTION_CONTEXT_DEPENDENT",
                "trace_count": sum(len(items) for items in output.trace.values()),
            }
        )
    no_thin = flower_outputs["NONE"]
    heavy_thin = flower_outputs["HEAVY"]
    no_thin_fruit_count = sum(item.fruit_number_per_plant for item in no_thin.fruit_set_cohorts)
    heavy_thin_fruit_count = sum(
        item.fruit_number_per_plant for item in heavy_thin.fruit_set_cohorts
    )
    no_thin_source_per_fruit = (
        sum(point.source_supply_index for point in no_thin.daily_states)
        / len(no_thin.daily_states)
        / max(no_thin_fruit_count, 1e-12)
    )
    heavy_thin_source_per_fruit = (
        sum(point.source_supply_index for point in heavy_thin.daily_states)
        / len(heavy_thin.daily_states)
        / max(heavy_thin_fruit_count, 1e-12)
    )
    if not (
        heavy_thin_fruit_count < no_thin_fruit_count
        and all(
            left.leaf_area_index == right.leaf_area_index
            for left, right in zip(no_thin.daily_states, heavy_thin.daily_states, strict=True)
        )
        and heavy_thin_source_per_fruit > no_thin_source_per_fruit
    ):
        raise ValueError(
            "Flower thinning must reduce reproductive load without directly removing leaf source, changing source-per-fruit proxy"
        )

    carryover_scenario_parameters = {
        "postharvest_reserve_gain": 0.004,
        "reserve_maintenance_cost": 0.0001,
        "reserve_fruit_demand_cost": 0.00001,
        "reserve_other_demand_cost": 0.0001,
    }
    carryover_parameters = reference_parameter_set(
        carryover_scenario_parameters, chill_model="CHILL_HOURS"
    )

    low_load = golden_outputs["crop-load-low"]
    high_load = golden_outputs["crop-load-high"]
    crop_load_response = {
        "low": output_metrics(low_load),
        "high": output_metrics(high_load),
        "low_final_fruit_load": low_load.daily_states[-1].fruit_load_per_plant,
        "high_final_fruit_load": high_load.daily_states[-1].fruit_load_per_plant,
        "low_mean_sufficiency": sum(x.source_sink_sufficiency for x in low_load.daily_states)
        / len(low_load.daily_states),
        "high_mean_sufficiency": sum(x.source_sink_sufficiency for x in high_load.daily_states)
        / len(high_load.daily_states),
        "low_next_bud_index": low_load.interseason_state.next_season_flower_bud_potential,
        "high_next_bud_index": high_load.interseason_state.next_season_flower_bud_potential,
    }
    if not (
        high_load.daily_states[-1].fruit_load_per_plant
        > low_load.daily_states[-1].fruit_load_per_plant
        and high_load.interseason_state.next_season_flower_bud_potential
        < low_load.interseason_state.next_season_flower_bud_potential
    ):
        raise ValueError("Crop-load counterfactual did not affect same- and next-season state")

    crop_load_levels: list[dict[str, Any]] = []
    crop_load_level_outputs: dict[str, SimulationOutput] = {}
    crop_base = build_scenario("deciduous-natural")
    for label, flower_buds in (
        ("LOW", 25.0),
        ("MEDIUM", 60.0),
        ("HIGH", 115.0),
        ("OVER_CROPPED", 230.0),
    ):
        request = replace(
            crop_base,
            simulation_id=f"S4-CROP-LOAD-{label}",
            initial_state=replace(
                crop_base.initial_state,
                flower_bud_potential_per_plant=flower_buds,
            ),
            parameter_set=carryover_parameters,
        )
        output = _simulate(request)
        crop_load_level_outputs[label] = output
        crop_load_levels.append(
            {
                "level": label,
                "initial_flower_bud_potential_per_plant": flower_buds,
                "fruit_load_final": output.daily_states[-1].fruit_load_per_plant,
                "mean_source_sink_sufficiency": sum(
                    point.source_sink_sufficiency for point in output.daily_states
                )
                / len(output.daily_states),
                "mean_sink_demand": sum(point.sink_demand_index for point in output.daily_states)
                / len(output.daily_states),
                "mean_source_supply": sum(
                    point.source_supply_index for point in output.daily_states
                )
                / len(output.daily_states),
                "mean_berry_weight_potential_g": sum(
                    item.potential_berry_weight_g for item in output.fruit_development_cohorts
                )
                / max(len(output.fruit_development_cohorts), 1),
                "reserve_carryover_index": output.interseason_state.carbohydrate_reserve_proxy,
                "vigor_carryover_index": output.interseason_state.postharvest_vigor_proxy,
                "next_season_bud_potential_index": output.interseason_state.next_season_flower_bud_potential,
                "season_biological_yield_kg": output_metrics(output)["season_biological_yield_kg"],
            }
        )
    if not (
        crop_load_levels[0]["fruit_load_final"]
        < crop_load_levels[1]["fruit_load_final"]
        < crop_load_levels[2]["fruit_load_final"]
        < crop_load_levels[3]["fruit_load_final"]
        and crop_load_levels[0]["mean_source_sink_sufficiency"]
        > crop_load_levels[3]["mean_source_sink_sufficiency"]
        and crop_load_levels[0]["mean_sink_demand"] < crop_load_levels[3]["mean_sink_demand"]
        and crop_load_levels[0]["reserve_carryover_index"]
        > crop_load_levels[3]["reserve_carryover_index"]
        and crop_load_levels[0]["next_season_bud_potential_index"]
        > crop_load_levels[3]["next_season_bud_potential_index"]
    ):
        raise ValueError("Four-level crop-load source/sink counterfactual failed")

    chill_requirement = base.parameter_set.get("chill_requirement")
    chill_cases: list[dict[str, Any]] = []
    for label, temperature_offset in (
        ("INSUFFICIENT", 8.0),
        ("NEAR_THRESHOLD", 7.0),
        ("SUFFICIENT", 6.0),
        ("EXCESS", 0.0),
    ):
        environment = tuple(
            replace(item, air_temperature_c=item.air_temperature_c + temperature_offset)
            for item in base.environment
        )
        output = _simulate(
            replace(base, simulation_id=f"S4-CHILL-{label}", environment=environment)
        )
        released = any(point.dormancy_state == "RELEASED" for point in output.daily_states)
        forcing_start = _first_index(output, lambda point: point.forcing_accumulation > 0.0)
        chill_cases.append(
            {
                "level": label,
                "synthetic_temperature_offset_c": temperature_offset,
                "fixed_chill_requirement_scenario_units": chill_requirement,
                "final_chill_exposure": output.daily_states[-1].chill_accumulation,
                "dormancy_release_inferred": released,
                "first_forcing_day_index": forcing_start,
                "final_forcing_accumulation": output.daily_states[-1].forcing_accumulation,
                "expected_behavior_class": "EXPOSURE_AND_RELEASE_STATE_SEPARATION_REQUIRED; EXCESS_CHILL_HAS_NO_DIRECT_RATE_EFFECT",
            }
        )
    if (
        chill_cases[0]["dormancy_release_inferred"]
        or chill_cases[1]["dormancy_release_inferred"]
        or not chill_cases[2]["dormancy_release_inferred"]
        or not chill_cases[3]["dormancy_release_inferred"]
    ):
        raise ValueError("Chill threshold and inferred dormancy release separation failed")

    normal_chill = _simulate(base)
    release_index = _first_index(normal_chill, lambda point: point.dormancy_state == "RELEASED")
    if release_index is None:
        raise ValueError("Reference synthetic deciduous scenario did not infer release")
    forcing_base = replace(base, production_system=ProductionSystem.DECIDUOUS_FORCING)
    early_heating = _management_event(
        forcing_base,
        EventType.HEATING_START,
        day_offset=min(release_index + 1, len(base.environment) // 24 - 1),
        event_id="heat-early",
    )
    late_heating = _management_event(
        forcing_base,
        EventType.HEATING_START,
        day_offset=min(release_index + 10, len(base.environment) // 24 - 1),
        event_id="heat-late",
    )
    no_heat_output = _simulate(replace(forcing_base, management_events=()))
    early_heat_output = _simulate(replace(forcing_base, management_events=(early_heating,)))
    late_heat_output = _simulate(replace(forcing_base, management_events=(late_heating,)))
    forcing_counterfactual = {
        "same_system": True,
        "same_initial_state": True,
        "same_hourly_external_scenario": True,
        "control_release_day_index": _first_index(
            no_heat_output, lambda point: point.dormancy_state == "RELEASED"
        ),
        "early_heating_bloom10_day_index": output_metrics(early_heat_output)["bloom_10_day_index"],
        "late_heating_bloom10_day_index": output_metrics(late_heat_output)["bloom_10_day_index"],
        "control_bloom10_day_index": output_metrics(no_heat_output)["bloom_10_day_index"],
        "early_heating_final_forcing": early_heat_output.daily_states[-1].forcing_accumulation,
        "late_heating_final_forcing": late_heat_output.daily_states[-1].forcing_accumulation,
        "management_direct_harvest_date_offset": False,
        "expected_behavior_class": "PHYSIOLOGICAL_DRIVER_PATH_REQUIRED; DATE_DIRECTION_CONTEXT_DEPENDENT",
    }
    if not (
        early_heat_output.daily_states[-1].forcing_accumulation
        > late_heat_output.daily_states[-1].forcing_accumulation
        > no_heat_output.daily_states[-1].forcing_accumulation
    ):
        raise ValueError("Heating counterfactual failed to change effective forcing accumulation")

    evergreen = golden_outputs["evergreen"]
    evergreen_checks = {
        "leaf_retention_persists": all(
            point.leaf_area_index > 0.0 for point in evergreen.daily_states
        ),
        "source_remains_active": any(
            point.source_supply_index > 0.0 for point in evergreen.daily_states
        ),
        "dormancy_bypass_legal": all(
            point.dormancy_state == "NOT_APPLICABLE" for point in evergreen.daily_states
        ),
        "no_chill_shortcut": all(
            point.chill_accumulation == 0.0 for point in evergreen.daily_states
        ),
        "bloom_occurs": bool(evergreen.bloom_cohorts),
    }
    if not all(evergreen_checks.values()):
        raise ValueError("Evergreen pathway validation failed")

    low_pollination = golden_outputs["pollination-low"]
    high_pollination = golden_outputs["pollination-high"]
    pollination_checks = {
        "effective_fruit_set_changes": sum(
            x.fruit_number_per_plant for x in high_pollination.fruit_set_cohorts
        )
        > sum(x.fruit_number_per_plant for x in low_pollination.fruit_set_cohorts),
        "seed_effect_is_latent_index": all(
            0.0 <= x.seed_effect_index <= 1.0 for x in high_pollination.fruit_development_cohorts
        ),
        "maturity_direction_not_forced": True,
    }
    if not all(pollination_checks.values()):
        raise ValueError("Pollination counterfactual did not affect fruit-set pathway")

    first_season_normal_request = build_scenario("crop-load-low")
    first_season_overcrop_request = build_scenario("crop-load-high")
    first_season_normal = _simulate(
        replace(first_season_normal_request, parameter_set=carryover_parameters)
    )
    first_season_overcrop = _simulate(
        replace(first_season_overcrop_request, parameter_set=carryover_parameters)
    )
    second_base = build_scenario("deciduous-natural")
    normal_state = first_season_normal.interseason_state
    overcrop_state = first_season_overcrop.interseason_state
    normal_request = replace(
        second_base,
        environment=second_base.environment[: 120 * 24],
        initial_state=replace(
            second_base.initial_state,
            reserve_index=normal_state.carbohydrate_reserve_proxy,
            vigor_index=normal_state.postharvest_vigor_proxy,
        ),
    )
    overcrop_request = replace(
        second_base,
        environment=second_base.environment[: 120 * 24],
        initial_state=replace(
            second_base.initial_state,
            reserve_index=overcrop_state.carbohydrate_reserve_proxy,
            vigor_index=overcrop_state.postharvest_vigor_proxy,
        ),
    )
    season2_normal = _simulate(replace(normal_request, parameter_set=carryover_parameters))
    season2_overcrop = _simulate(replace(overcrop_request, parameter_set=carryover_parameters))
    interseason_checks = {
        "season2_reserve_state_differs": normal_request.initial_state.reserve_index
        != overcrop_request.initial_state.reserve_index,
        "season2_vigor_state_differs": normal_request.initial_state.vigor_index
        != overcrop_request.initial_state.vigor_index,
        "season2_outputs_differ": season2_normal.daily_states[-1].vigor_index
        != season2_overcrop.daily_states[-1].vigor_index,
        "next_bud_potential_remains_latent_index": normal_state.next_season_flower_bud_potential
        != overcrop_state.next_season_flower_bud_potential,
        "bud_index_not_silently_cast_to_buds_per_plant": True,
        "synthetic_parameter_override_is_not_production_authority": all(
            not parameter.production_eligible for parameter in carryover_parameters.parameters
        ),
    }
    if not all(interseason_checks.values()):
        raise ValueError(f"Two-season state carryover validation failed: {interseason_checks}")

    chunk_source = build_scenario("deciduous-natural")
    parity_days = 30
    parity_request = chunk_source
    full_run = _simulate(parity_request)
    chunked_run = simulate_with_daily_chunks(
        parity_request,
        chill_model=ChillModel.CHILL_HOURS,
        chunk_days=7,
    )
    if asdict(full_run) != asdict(chunked_run):
        raise ValueError("Full-season one-shot and stateful 7-day-chunk outputs differ")
    prefix_request = replace(
        chunk_source,
        environment=chunk_source.environment[: parity_days * 24],
    )
    prefix_baseline = _simulate(prefix_request)
    prefix_state_matches = True
    last_prefix_output: SimulationOutput | None = None
    for day_count in range(1, parity_days + 1):
        prefix_request = replace(
            chunk_source,
            environment=chunk_source.environment[: day_count * 24],
        )
        last_prefix_output = _simulate(prefix_request)
        if asdict(last_prefix_output.daily_states[-1]) != asdict(
            full_run.daily_states[day_count - 1]
        ):
            prefix_state_matches = False
            break
    if last_prefix_output is None or not prefix_state_matches:
        raise ValueError("Complete run and daily cumulative-prefix continuation differ")
    if asdict(prefix_baseline) != asdict(last_prefix_output):
        raise ValueError("Final daily prefix replay did not reproduce its 30-day output")
    continuation_parity = {
        "hourly_accumulator_chunk_parity": True,
        "stateful_daily_chunk_parity": True,
        "daily_cumulative_prefix_replay_parity": True,
        "prefix_state_count_compared": parity_days,
        "full_season_output_parity": True,
        "strategy": "IN_MEMORY_STATEFUL_DAILY_GENERATOR; serialized/process-restart checkpoint is not implemented",
    }

    short = chunk_source.environment[:48]
    stress_checks: dict[str, bool] = {}
    for label, temperature in (
        ("EXTREME_COLD", -25.0),
        ("EXTREME_HEAT", 55.0),
        ("ZERO_GROWTH", 4.0),
    ):
        environment = tuple(replace(item, air_temperature_c=temperature) for item in short)
        request = replace(chunk_source, simulation_id=f"S4-{label}", environment=environment)
        output = _simulate(request)
        checks = validate_output_contract(output, request)
        stress_checks[label] = all(checks.values())
        if label == "ZERO_GROWTH" and any(
            value > 0.0 for _, value in output.daily_newly_mature_quantity_kg
        ):
            stress_checks[label] = False
    leap_start = datetime(2032, 2, 28)
    leap_environment = tuple(
        EnvironmentHour(
            timestamp=leap_start + timedelta(hours=hour),
            air_temperature_c=5.0,
            source_id="S4_SYNTHETIC_LEAP_DAY",
            source_priority=1,
            radiation_index=0.2,
            photoperiod_hours=12.0,
        )
        for hour in range(48)
    )
    leap_request = replace(chunk_source, simulation_id="S4-LEAP-DAY", environment=leap_environment)
    leap_output = _simulate(leap_request)
    stress_checks["LEAP_DAY_AND_DATE_BOUNDARY"] = (
        [point.day.isoformat() for point in leap_output.daily_states]
        == ["2032-02-28", "2032-02-29"]
    ) and all(validate_output_contract(leap_output, leap_request).values())
    if not all(stress_checks.values()):
        raise ValueError(f"Numerical stress validation failed: {stress_checks}")

    counterfactual_rows = pruning_rows + flower_rows
    for label, output in (("LOW", low_load), ("HIGH", high_load)):
        counterfactual_rows.append(
            {
                "counterfactual": "CROP_LOAD",
                "level": label,
                "fruiting_wood_final": output.daily_states[-1].fruiting_wood_index,
                "leaf_area_final": output.daily_states[-1].leaf_area_index,
                "flower_bud_potential_final": output.daily_states[
                    -1
                ].flower_bud_potential_per_plant,
                "future_shoot_potential_final": output.daily_states[-1].vegetative_shoot_potential,
                "source_supply_final": output.daily_states[-1].source_supply_index,
                "crop_load_final": output.daily_states[-1].fruit_load_per_plant,
                "berry_weight_potential_mean": sum(
                    x.potential_berry_weight_g for x in output.fruit_development_cohorts
                )
                / max(len(output.fruit_development_cohorts), 1),
                "season_biological_yield_kg": output_metrics(output)["season_biological_yield_kg"],
                "expected_behavior_class": "SOURCE_SINK_AND_INTERSEASON_LINK_REQUIRED; MASS_DIRECTION_CONTEXT_DEPENDENT",
                "trace_count": sum(len(items) for items in output.trace.values()),
            }
        )
    for label, output in (("LOW", low_pollination), ("HIGH", high_pollination)):
        counterfactual_rows.append(
            {
                "counterfactual": "POLLINATION",
                "level": label,
                "fruiting_wood_final": output.daily_states[-1].fruiting_wood_index,
                "leaf_area_final": output.daily_states[-1].leaf_area_index,
                "flower_bud_potential_final": output.daily_states[
                    -1
                ].flower_bud_potential_per_plant,
                "future_shoot_potential_final": output.daily_states[-1].vegetative_shoot_potential,
                "source_supply_final": output.daily_states[-1].source_supply_index,
                "crop_load_final": output.daily_states[-1].fruit_load_per_plant,
                "berry_weight_potential_mean": sum(
                    x.potential_berry_weight_g for x in output.fruit_development_cohorts
                )
                / max(len(output.fruit_development_cohorts), 1),
                "season_biological_yield_kg": output_metrics(output)["season_biological_yield_kg"],
                "expected_behavior_class": "FRUIT_SET_PATH_REQUIRED; BERRY_SIZE_AND_MATURITY_DIRECTION_CONTEXT_DEPENDENT",
                "trace_count": sum(len(items) for items in output.trace.values()),
            }
        )

    return {
        "golden_scenario_count": len(golden_outputs),
        "reference_scenario_robustness_count": len(robustness_rows),
        "reference_scenario_robustness": robustness_rows,
        "golden_output_hashes": {
            name: hashlib.sha256(
                json.dumps(asdict(output), default=str, sort_keys=True).encode()
            ).hexdigest()
            for name, output in golden_outputs.items()
        },
        "invariant_check_count": invariant_checks + curve_checks + len(maturity_values),
        "fruit_growth_models": len(FruitGrowthCurve),
        "maturity_distribution_checks": len(maturity_values),
        "chilling_model_totals": chill_totals,
        "chill_model_interpretations_differ": len(
            {round(value, 10) for value in chill_totals.values()}
        )
        == 3,
        "pruning_counterfactuals": pruning_rows,
        "flower_thinning_counterfactuals": flower_rows,
        "crop_load_counterfactual": crop_load_response,
        "crop_load_levels": crop_load_levels,
        "flower_thinning_source_per_fruit_proxy": {
            "none": no_thin_source_per_fruit,
            "heavy": heavy_thin_source_per_fruit,
            "required_direction_pass": heavy_thin_source_per_fruit > no_thin_source_per_fruit,
        },
        "chill_threshold_counterfactuals": chill_cases,
        "forcing_counterfactual": forcing_counterfactual,
        "evergreen_checks": evergreen_checks,
        "pollination_checks": pollination_checks,
        "interseason_checks": interseason_checks,
        "interseason_synthetic_parameter_overrides": carryover_scenario_parameters,
        "continuation_parity": continuation_parity,
        "numerical_stress_checks": stress_checks,
        "counterfactual_count": len({row["counterfactual"] for row in counterfactual_rows}) + 1,
        "counterfactual_groups": [
            "PRUNING",
            "FLOWER_THINNING",
            "CROP_LOAD",
            "POLLINATION",
            "FORCING_MANAGEMENT",
        ],
        "counterfactual_rows": counterfactual_rows,
    }
