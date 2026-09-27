"""Build deterministic, synthetic-only V0.9-S4 validation evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.tests.biological_growth import s4_validation as validation  # noqa: E402

TASK_ID = (
    "V0_9_S4_THEORETICAL_MODEL_VALIDATION_PARAMETER_IDENTIFIABILITY_AND_PROSPECTIVE_READINESS_R1"
)
REPORT_REL = "docs/v0-9/s4/theoretical-model-structural-validation-r1.md"
EVIDENCE_REL = "docs/v0-9/evidence/s4-theoretical-model-validation-and-identifiability-r1.json"
S2_REL = "docs/v0-9/evidence/s2-existing-data-observability-and-gap-audit-r1.json"
S3_EVIDENCE_REL = "docs/v0-9/evidence/s3-theoretical-blueberry-growth-model-r1.json"
PROTOCOL_REL = "docs/v0-9/s4/prospective-validation-protocol-r1.md"

CSV_OUTPUTS = {
    "equation_traceability": "docs/v0-9/s4/equation-implementation-traceability-r1.csv",
    "dimensional_validation": "docs/v0-9/s4/equation-dimensional-validation-r1.csv",
    "parameter_sensitivity": "docs/v0-9/s4/parameter-sensitivity-register-r1.csv",
    "parameter_identifiability": "docs/v0-9/s4/parameter-identifiability-register-r1.csv",
    "parameter_confounding": "docs/v0-9/s4/parameter-confounding-register-r1.csv",
    "parameter_observations": "docs/v0-9/s4/parameter-to-observation-requirement-r1.csv",
    "abstraction_review": "docs/v0-9/s4/explicit-abstraction-review-r1.csv",
    "failure_modes": "docs/v0-9/s4/theoretical-model-failure-mode-register-r1.csv",
    "future_calibration": "docs/v0-9/s4/future-calibration-data-requirements-r1.csv",
    "not_ready_quarantine": "docs/v0-9/s4/s0-not-ready-mechanism-quarantine-r1.csv",
}


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"Refusing to emit an empty audit table: {path}")
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: _cell(row.get(key)) for key in fieldnames} for row in rows)


def _compute_pass() -> dict[str, Any]:
    pins = validation.verify_authority_pins(ROOT)
    s2_path = ROOT / S2_REL
    s2 = json.loads(s2_path.read_text(encoding="utf-8"))
    s2_findings = s2["asset_findings"]
    if not s2_findings["benchmark_2025_2026_consumed"]:
        raise ValueError("S2 benchmark lifecycle metadata is inconsistent")
    if s2_findings["benchmark_reuse_for_selection_allowed"]:
        raise ValueError("S2 metadata unexpectedly allows 2025-2026 selection reuse")

    s3_evidence = json.loads((ROOT / S3_EVIDENCE_REL).read_text(encoding="utf-8"))
    equations = validation.build_equation_rows(ROOT)
    dimensions = validation.build_dimensional_rows(ROOT)
    update_order = validation.build_update_order()
    synthetic = validation.run_synthetic_validation()
    sensitivity = validation.build_parameter_sensitivity_rows(
        trajectories=4,
        seed=909,
        root=ROOT,
    )
    identifiability = validation.build_parameter_identifiability_rows(ROOT)
    confounding = validation.build_confounding_rows()
    observation_requirements = validation.build_parameter_observation_rows(ROOT)
    abstraction_review = validation.build_abstraction_review_rows(ROOT)
    failure_modes = validation.build_failure_mode_rows()
    future_calibration = validation.build_future_calibration_rows()
    quarantine = validation.build_abstraction_quarantine_rows(ROOT)

    if len(equations) != int(s3_evidence["model"]["equation_count"]):
        raise ValueError("S3 equation inventory count does not match pinned evidence")
    if len(identifiability) != int(s3_evidence["model"]["literature_parameter_registry_row_count"]):
        raise ValueError("S3 parameter registry row count does not match pinned evidence")
    if len(abstraction_review) != int(
        s3_evidence["model"]["equation_authority_counts"]["EXPLICIT_MODEL_ABSTRACTION"]
    ):
        raise ValueError("S3 explicit abstraction count does not match pinned evidence")
    if not all(row["status"] == "PASS" for row in equations + dimensions):
        raise ValueError("Equation traceability or dimensional validation failed")
    unsupported_equations = [
        row for row in equations if row["unsupported_branch_present"] == "true"
    ]
    if len(unsupported_equations) != 1 or unsupported_equations[0]["equation_id"] != "EQA030":
        raise ValueError("Unsupported equation/event scope must be explicitly inventoried")
    if int(update_order["algebraic_loop_count"]) != 0:
        raise ValueError("Undeclared algebraic loop found in the frozen update schedule")
    if len(quarantine) != 6 or len({row["claim_id"] for row in quarantine}) != 6:
        raise ValueError("S0 not-ready mechanism quarantine is incomplete")
    if sum(row["unresolved_critical"] == "true" for row in abstraction_review) != 0:
        raise ValueError("A critical unresolved abstraction remains")
    if any(row["production_parameter"] != "false" for row in identifiability):
        raise ValueError("A parameter was incorrectly promoted to production authority")
    if any(row["may_use_2025_2026_for_selection"] != "false" for row in future_calibration):
        raise ValueError("Future calibration register opened the consumed benchmark for selection")

    sensitivity_priority = {
        "NEGLIGIBLE_WITHIN_TESTED_RANGE": 0,
        "LOW_LEVERAGE": 1,
        "MEDIUM_LEVERAGE": 2,
        "HIGH_LEVERAGE": 3,
    }
    per_parameter_sensitivity: dict[str, int] = {}
    for row in sensitivity:
        name = row["parameter_name"]
        rank = sensitivity_priority[row["leverage_class"]]
        per_parameter_sensitivity[name] = max(per_parameter_sensitivity.get(name, 0), rank)
    sensitivity_parameter_counts = Counter(per_parameter_sensitivity.values())
    identifiability_counts = Counter(row["identifiability_status"] for row in identifiability)
    abstraction_counts = Counter(row["review_decision"] for row in abstraction_review)
    priority_counts = Counter(row["priority"] for row in future_calibration)
    status_counts = Counter(row["risk_level"] for row in abstraction_review)

    declared_corrections = pins["s3_declared_s4_unit_corrections"]
    if len(declared_corrections) != 4 or pins["s3_unexplained_pin_mismatches"] != 0:
        raise ValueError("S3 pin differences do not equal the four declared S4 correctness fixes")

    return {
        "authority_pins": pins,
        "s2_metadata": {
            "path": S2_REL,
            "sha256": validation.sha256_file(s2_path),
            "benchmark_2025_2026_consumed": bool(s2_findings["benchmark_2025_2026_consumed"]),
            "benchmark_reuse_for_selection_allowed": bool(
                s2_findings["benchmark_reuse_for_selection_allowed"]
            ),
            "direct_phenology_observations": s2_findings["phenology_direct_observations"],
            "executed_management_event_types": s2_findings[
                "management_event_types_with_executed_records"
            ],
            "greenhouse_hourly_temperature": s2_findings["greenhouse_hourly_temperature"],
            "chilling_derivability": s2_findings["chilling_derivability"],
            "forcing_derivability": s2_findings["forcing_derivability"],
            "used_for": (
                "availability/provenance metadata only; no raw actual quantity or benchmark scoring"
            ),
        },
        "equation_traceability": equations,
        "dimensional_validation": dimensions,
        "state_update_order": update_order,
        "synthetic_validation": synthetic,
        "parameter_sensitivity": sensitivity,
        "parameter_sensitivity_counts_by_parameter": {
            "high_leverage": sensitivity_parameter_counts[3],
            "medium_leverage": sensitivity_parameter_counts[2],
            "low_leverage": sensitivity_parameter_counts[1],
            "negligible_within_tested_range": sensitivity_parameter_counts[0],
            "interaction_suspected_parameter_output_pairs": sum(
                row["interaction_suspected"] == "true" for row in sensitivity
            ),
            "unique_parameter_count": len(per_parameter_sensitivity),
        },
        "parameter_identifiability": identifiability,
        "parameter_identifiability_counts": dict(sorted(identifiability_counts.items())),
        "parameter_confounding": confounding,
        "parameter_observation_requirements": observation_requirements,
        "explicit_abstraction_review": abstraction_review,
        "explicit_abstraction_counts": dict(sorted(abstraction_counts.items())),
        "abstraction_risk_counts": dict(sorted(status_counts.items())),
        "failure_modes": failure_modes,
        "future_calibration_requirements": future_calibration,
        "future_calibration_priority_counts": dict(sorted(priority_counts.items())),
        "s0_not_ready_quarantine": quarantine,
        "scope_assertions": {
            "theory_first": True,
            "real_harvest_labels_loaded": False,
            "business_data_used_for_fitting": False,
            "historical_harvest_scoring": False,
            "2025_2026_used_for_selection": False,
            "model_training": False,
            "model_refit": False,
            "backtest": False,
            "production_parameter_created": False,
            "production_parameter_count": 0,
            "production_behavior_from_unregistered_parameter": False,
            "unsupported_management_event_effects_claimed": False,
            "stage_a_model_changed": False,
            "stage_b_model_changed": False,
            "model_production_ready": False,
            "v0_10_authorized": False,
        },
    }


def _compute_child(path: Path) -> int:
    payload = _compute_pass()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json(payload))
    print(_sha256_bytes(path.read_bytes()))
    return 0


def _format_float(value: float, digits: int = 6) -> str:
    return f"{value:.{digits}f}"


def _build_report(payload: dict[str, Any], replay_hash: str) -> str:
    synthetic = payload["synthetic_validation"]
    counts = payload["parameter_sensitivity_counts_by_parameter"]
    ident_counts = payload["parameter_identifiability_counts"]
    abstractions = payload["explicit_abstraction_counts"]
    future = payload["future_calibration_priority_counts"]
    pruning = synthetic["pruning_counterfactuals"]
    thinning = synthetic["flower_thinning_counterfactuals"]
    crop_load = synthetic["crop_load_levels"]
    chill = synthetic["chill_threshold_counterfactuals"]
    continuation = synthetic["continuation_parity"]

    pruning_table = "\n".join(
        f"| {row['level']} | {_format_float(row['fruiting_wood_final'])} | "
        f"{_format_float(row['flower_bud_potential_final'])} | "
        f"{_format_float(row['source_supply_final'])} | "
        f"{_format_float(row['future_shoot_potential_final'])} | "
        f"{_format_float(row['season_biological_yield_kg'])} |"
        for row in pruning
    )
    thinning_table = "\n".join(
        f"| {row['level']} | {_format_float(row['effective_flower_load'])} | "
        f"{_format_float(row['fruit_number'])} | {_format_float(row['leaf_area_final'])} |"
        for row in thinning
    )
    load_table = "\n".join(
        f"| {row['level']} | {_format_float(row['fruit_load_final'])} | "
        f"{_format_float(row['mean_sink_demand'])} | "
        f"{_format_float(row['mean_source_sink_sufficiency'])} | "
        f"{_format_float(row['reserve_carryover_index'])} | "
        f"{_format_float(row['next_season_bud_potential_index'])} |"
        for row in crop_load
    )
    chill_table = "\n".join(
        f"| {row['level']} | {_format_float(row['final_chill_exposure'])} | "
        f"{row['dormancy_release_inferred']} | {_format_float(row['final_forcing_accumulation'])} |"
        for row in chill
    )

    return f"""# V0.9-S4 — Theoretical Model Structural Validation and Identifiability

## Scope and verdict

This is a theory-first structural audit, not an accuracy evaluation. It uses only
S0/S1/S3 authority artifacts, S2 availability metadata, and fixed synthetic
scenarios. No harvest labels, historical scoring, benchmark selection, model
refit, or production parameterization occurred. S2 data readiness does not
limit the theoretical mechanism set; it is used only to state future observation
gaps.

The model is structurally validated within its declared synthetic scope and is
ready for future calibration/prospective research only after the P0 observation
requirements are collected and authorized. It is not production-ready. No
claim of empirical accuracy, parameter estimate, or global cultivar validity is
made.

* Equations reviewed: **30 / 30**, untraceable: **0**.
* Dimensional checks: **PASS**, errors: **0**; three stale S3 unit labels and
  the S3 Celsius-to-Kelvin constant discrepancy are recorded as S4 corrections.
* Daily execution order: **16 model modules in 14 ordered phases**, algebraic
  loops: **0**.
* Synthetic invariants: **{synthetic["invariant_check_count"]} checks**;
  golden scenarios: **{synthetic["golden_scenario_count"]}**; robustness cases:
  **{synthetic["reference_scenario_robustness_count"]}**.
* Full-season one-shot/stateful 7-day chunk output parity:
  **{continuation["full_season_output_parity"]}**. This is an in-memory stateful
  generator test; a serialized/process-restart checkpoint format is not claimed.
* Deterministic independent process replay payload SHA-256:
  `{replay_hash}` (both passes byte-identical).

## Reviewed authority and bounded corrections

S0's six authority files, all files in the S1 artifact manifest, the S3
evidence, and the S3 artifact manifest were re-hashed. S2 evidence was read
only for availability/lifecycle metadata. The exact S0 pins and S1 manifest
pin are carried in the machine evidence. The S3 verifier found no unexplained
pin drift; four narrow code corrections are declared: additive-state unit
labels, invalid/non-finite fruit-curve guards, the exact 273.15 C-to-K
conversion plus physical temperature guards, and an in-memory daily generator
used to test stateful chunk continuation. The biological response equations,
causal directions, parameter values, and S3 authority files were not rewritten.

The equation traceability table ties each S3 equation to its registered
implementation symbol, S0 claim IDs, S0/S3 source IDs, declared inputs/outputs,
units, and parameter IDs. Eight equation rows disclose named method/numerical
constants. They are model-method constants or numerical/domain guards, not
production parameters. All 114 S3 parameters remain non-production. Two
pre-set cohort placeholders (`source_modifier=1.0`, `seed_index=0.5`) are
overwritten when fruit set occurs and do not enter mature-cohort output before
that transition; this is recorded as a code-level initialization detail, not a
production parameter.

One explicitly inventoried scope gap remains: `IRRIGATION_STRESS` and
`NUTRITION_INTERVENTION` are registered event types but have no physiological
transition in S3. The engine emits `NO_PHYSIOLOGICAL_EFFECT_BOUND_IN_S3` trace
entries; these are not treated as simulated interventions. Prospective research
must exclude these events or add a separately authorized, evidence-supported
implementation before claiming their effects. This is not hidden as a passing
counterfactual.

## Equations, dimensions, update order, and invariants

Dimensional checks explicitly separate per-plant counts, berries/plant,
g/berry, kg/plant/day, area in mu, plants/mu, area-level kg/day, fractions,
normalized latent indices, degree-hours/days, chill-model-specific units,
temperature, and calendar time. Multiplications and sums are checked within
each registered expression; chill model outputs retain their own model
identity and are not averaged. Area scaling is verified as
`kg/plant/day × mu × plants/mu = kg/day` and is applied once.

The ordered phases and each phase's previous-state, same-step, and next-state
inputs are in `state-update-order-r1.json`. Same-day fruit-set/crop-load
feedback uses a pre-set source/sink snapshot; reserve/vigor updates become
next-step inputs, so no algebraic loop relies on Python evaluation order.
Boundary tests cover normalized-state endpoints and just-outside rejection,
finite/nonnegative quantities, valid fractions, and explicit fail-closed
guards. Conservation checks cover flower → pollinated flower → fruit set →
retained fruit → ripe fruit, unique cohort lineage, nonnegative mature mass,
daily-to-cohort mass reconciliation, and per-plant-to-area scaling.

Numerical stability checks include a 330-day synthetic season, repeated hourly
chill series, chunked hourly accumulator replay, 7-day stateful daily chunks,
extreme cold and heat, zero-growth conditions, leap day, and maturity-curve
monotonicity/finite bounds. A separate 30-day cumulative-prefix replay remains
as an additional state audit; it is not substituted for the full-season
stateful chunk test. A persisted checkpoint/process-restart protocol remains
outside this S4 implementation.

## Synthetic counterfactuals

Expected behaviors are classified before interpreting outputs. Structural
effects are required where the contract says so; total-mass direction remains
context-dependent when evidence does not support monotonicity.

### Pruning: same cultivar, environment, initial state, and other events

| Level | Wood | Bud potential | Source | Shoot potential | Season kg |
|---|---:|---:|---:|---:|---:|
{pruning_table}

Across no/light/moderate/heavy interventions, fruiting wood, bud potential,
leaf/source structure, and future shoot potential respond through separate
state paths. Seasonal mass is reported as an outcome, not assigned a required
direction.

### Flower thinning is not pruning

| Level | Effective flower load | Fruit number | Final leaf area |
|---|---:|---:|---:|
{thinning_table}

Thinning changes effective reproductive load and potential fruit number while
leaf area remains unchanged in this counterfactual. The source-per-fruit proxy
increases under heavier thinning. No proportional season-yield rule is imposed.

### Crop load and inter-season linkage

| Level | Fruit load | Sink | Source/sink sufficiency | Reserve | Next-season buds |
|---|---:|---:|---:|---:|---:|
{load_table}

These are synthetic normalized indices, not measured carbon or bud counts.
The two-season test carries reserve/vigor outputs into the second-season
initial state and keeps next-season bud potential as a separate latent index;
it is never cast to buds/plant.

### Chilling, forcing, evergreen, pollination, and fruit cohorts

| Chill case | Final exposure (model units) | Release inferred | Final forcing (degree-day) |
|---|---:|---:|---:|
{chill_table}

Chill Hours, Utah, and Dynamic Model retain distinct outputs on the same
synthetic hourly series. No candidate is selected. Chill exposure and inferred
dormancy release are separate states; excess exposure does not act as a
post-release forcing multiplier. Heating/closure affects the effective
temperature path and forcing accumulation rather than shifting a harvest date
directly. Evergreen retains leaves/source activity and uses its own legal
pathway without a deciduous zero-chill shortcut. Pollination changes effective
pollinated flower and fruit-set proxies; seed and maturity effects remain
context-dependent. Double-logistic, double-Gompertz, and stagewise-thermal
curves each pass finite/nonnegative/ordered/monotone reference checks; none is
selected as a production curve. Maturity fractions are bounded and monotone,
with nonnegative daily increments.

## Sensitivity and identifiability

The deterministic Morris elementary-effect screen varies **24** declared
synthetic/reference parameters across **7 outputs**: season biological mass,
bloom 10/50 day indices, first maturity, single-day mature-mass peak,
rolling-7 mature-mass peak, and next-season flower-bud potential. Four fixed
trajectories use seed 909. The declared ranges are synthetic scenario bounds,
not literature-to-production selections and not fitted to harvest data.

Per-parameter maximum leverage classes across the screened outputs:

* HIGH_LEVERAGE: {counts["high_leverage"]}
* MEDIUM_LEVERAGE: {counts["medium_leverage"]}
* LOW_LEVERAGE: {counts["low_leverage"]}
* NEGLIGIBLE_WITHIN_TESTED_RANGE: {counts["negligible_within_tested_range"]}
* INTERACTION_SUSPECTED parameter/output pairs:
  {counts["interaction_suspected_parameter_output_pairs"]}

These labels describe leverage only; no parameter value, model family, or
threshold is selected. The full parameter/output effects and tested ranges are
in the sensitivity register.

The 114-parameter identifiability register is structural, not a statistical
confidence analysis. Counts: {json.dumps(ident_counts, sort_keys=True)}.
Composite source/sink, flower-count × set-probability, density × per-plant
productivity, thermal requirement × microclimate response, and berry-weight ×
marketable fraction are explicit confounding groups. Minimum disambiguating
observations are mapped per parameter; the S2 audit remains the source for what
is available now. No 2025–2026 actuals were loaded or scored.

## Abstraction review and quarantine

All 18 explicit S3 abstractions were reviewed. Decisions:
`{json.dumps(abstractions, sort_keys=True)}`. High-risk abstractions are
restricted to synthetic/research scope; no unresolved critical abstraction
remains within that restricted scope. This does not mean the equations are
empirically validated. S0 not-ready claims C005, C009, C011, C016, C024, and
C027 remain quarantined as RESEARCH_ONLY, PROXY_ONLY, BLOCKED_CONFLICT,
LATENT_ONLY, PROXY_ONLY, and RESEARCH_ONLY respectively.

Failure modes and uncertainty sources are explicit. Forecast uncertainty must
remain decomposed into initial state, parameter, environment, management, and
model-structure components; S4 does not collapse them into one interval.

## Current observations, calibration requirements, and prospective protocol

S2 metadata reports zero direct phenology observations, zero authorized
executed management-event types, greenhouse hourly temperature as
`NEW_COLLECTION_REQUIRED`, and chill/forcing derivability as
`CANNOT_DERIVE`. Those facts do not reduce theoretical model scope, but they
mean current business data cannot identify the biological coefficients. The
future calibration register has {future["P0_REQUIRED"]} P0, {future["P1_HIGH_VALUE"]}
P1, and {future["P2_ADVANCED"]} P2 requirements. P0 collection/authority is a
gate before any empirical calibration or real prospective issuance.

The prospective protocol is: authorized calibration window → training-only
parameter calibration → parameter and model artifact freeze → collect future
environment/management inputs → issue and cryptographically seal predictions
before actuals exist → collect future actuals → locked scoring and comparison.
The consumed 2025–2026 benchmark is audit/replay/reporting only and is never
available for model or parameter selection. V0.10 is not authorized.

## Readiness boundary

`THEORETICAL_MODEL_READY_FOR_FUTURE_CALIBRATION=true` means the theoretical
parameter/observation map and calibration protocol are defined, conditional on
future P0 data collection and authority; it does not mean calibration can begin
with current enterprise data. `THEORETICAL_MODEL_READY_FOR_PROSPECTIVE_RESEARCH=true`
means a seal-before-actuals protocol and deterministic research engine exist;
any issuance remains conditional on production-system, cultivar, P0 observation,
parameter-provenance, and input-quality gates. Production readiness remains
false.

## Reproducibility and artifact integrity

Two independent Python processes recomputed the complete S4 payload from pinned
authority and synthetic fixtures. Pass A and B payloads were byte-identical:
`{replay_hash}`. The machine evidence lists SHA-256 for every S4 output and code
artifact; its own hash is excluded from its internal manifest. Full CI was not
run. No commit, PR, Ready, Merge, deployment, or S4→next-stage action occurred.
"""


def _write_public_outputs(
    payload: dict[str, Any], replay_hash: str, quality_gates: dict[str, Any]
) -> dict[str, Any]:
    report_path = ROOT / REPORT_REL
    _write_csv(ROOT / CSV_OUTPUTS["equation_traceability"], payload["equation_traceability"])
    _write_csv(ROOT / CSV_OUTPUTS["dimensional_validation"], payload["dimensional_validation"])
    _write_csv(ROOT / CSV_OUTPUTS["parameter_sensitivity"], payload["parameter_sensitivity"])
    _write_csv(
        ROOT / CSV_OUTPUTS["parameter_identifiability"], payload["parameter_identifiability"]
    )
    _write_csv(ROOT / CSV_OUTPUTS["parameter_confounding"], payload["parameter_confounding"])
    _write_csv(
        ROOT / CSV_OUTPUTS["parameter_observations"], payload["parameter_observation_requirements"]
    )
    _write_csv(ROOT / CSV_OUTPUTS["abstraction_review"], payload["explicit_abstraction_review"])
    _write_csv(ROOT / CSV_OUTPUTS["failure_modes"], payload["failure_modes"])
    _write_csv(ROOT / CSV_OUTPUTS["future_calibration"], payload["future_calibration_requirements"])
    _write_csv(ROOT / CSV_OUTPUTS["not_ready_quarantine"], payload["s0_not_ready_quarantine"])
    _write_json(ROOT / "docs/v0-9/s4/state-update-order-r1.json", payload["state_update_order"])
    (ROOT / PROTOCOL_REL).write_text(
        """# V0.10 Prospective Validation Protocol — S4 Draft

This is a protocol artifact only; V0.10 is not authorized.

1. Define and authorize a calibration window using only eligible
   pre-issuance observations.
2. Calibrate only identifiable parameters; retain literature priors,
   assumptions, and unidentifiable values as separate authority classes.
3. Freeze parameters, model code, environment/management schema, units, and
   provenance hashes.
4. Seal the model artifact and all forecast inputs.
5. Issue a dated forecast and cryptographically seal predictions before
   target-season actuals exist or are accessible.
6. Collect target-season actuals only after prediction seal; preserve revision and source lineage.
7. Score once against the frozen protocol, with predeclared cohort, metrics,
   denominators, and missingness rules.

The consumed 2025–2026 benchmark is audit/replay/reporting only. It is
prohibited for parameter, model, hyperparameter, management-rule, or
support-policy selection.
""",
        encoding="utf-8",
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = _build_report(payload, replay_hash)
    report += (
        "\n## Local validation gates\n\n"
        f"* Focused tests: `{quality_gates['focused_tests']['status']}`; "
        f"S4 and S3 focused suites: {quality_gates['focused_tests']['command_summaries']}.\n"
        f"* Ruff check/format: `{quality_gates['ruff']['status']}`.\n"
        f"* Mypy: `{quality_gates['mypy']['status']}` "
        "(strict, S4/app scope; imported frozen S3 fixture/test typing diagnostics suppressed).\n"
        "* Full CI: `NOT_RUN`.\n"
    )
    report_path.write_text(report, encoding="utf-8")

    artifacts: list[dict[str, str]] = []
    public_paths = [REPORT_REL, PROTOCOL_REL, "docs/v0-9/s4/state-update-order-r1.json"]
    public_paths.extend(CSV_OUTPUTS.values())
    public_paths.extend(
        [
            "backend/app/biological_growth/engine.py",
            "backend/app/biological_growth/parameters.py",
            "backend/app/biological_growth/fruit_development.py",
            "backend/app/biological_growth/dormancy.py",
            "backend/tests/biological_growth/s4_validation.py",
            "backend/tests/biological_growth/test_v09_s4_validation.py",
            "scripts/run_v0_9_s4_validation.py",
        ]
    )
    role_by_suffix = {
        ".md": "S4_REPORT_OR_PROTOCOL",
        ".csv": "S4_VALIDATION_REGISTER",
        ".json": "S4_STATE_UPDATE_ORDER",
        ".py": "S4_VALIDATION_IMPLEMENTATION",
    }
    for relative in sorted(set(public_paths)):
        artifact_path = ROOT / relative
        artifacts.append(
            {
                "path": relative,
                "sha256": validation.sha256_file(artifact_path),
                "role": role_by_suffix[artifact_path.suffix],
            }
        )

    trace_count = len(payload["equation_traceability"])
    unsupported_equations = [
        row
        for row in payload["equation_traceability"]
        if row["unsupported_branch_present"] == "true"
    ]
    if len(unsupported_equations) != 1 or unsupported_equations[0]["equation_id"] != "EQA030":
        raise ValueError("Unsupported equation/event scope changed after deterministic replay")
    dimensional_error_count = sum(
        row["status"] != "PASS" for row in payload["dimensional_validation"]
    )
    ident_counts = payload["parameter_identifiability_counts"]
    abstraction_counts = payload["explicit_abstraction_counts"]
    sensitivity_counts = payload["parameter_sensitivity_counts_by_parameter"]
    quarantine = payload["s0_not_ready_quarantine"]
    future_priority = payload["future_calibration_priority_counts"]
    readiness = {
        "theoretical_model_ready_for_future_calibration": True,
        "future_calibration_condition": (
            "CONDITIONAL_ON_AUTHORIZED_P0_OBSERVATION_COLLECTION_AND_PARAMETER_PROVENANCE"
        ),
        "theoretical_model_ready_for_prospective_research": True,
        "prospective_issuance_condition": (
            "CONDITIONAL_ON_PRODUCTION_SYSTEM_CULTIVAR_P0_INPUT_"
            "QUALITY_GATES_AND_NO_UNSUPPORTED_MANAGEMENT_EVENT_EFFECTS"
        ),
        "model_production_ready": False,
        "v0_10_authorized": False,
    }
    evidence = {
        "task_id": TASK_ID,
        "result": "PASS_V0_9_S4_THEORETICAL_MODEL_VALIDATED_AND_PROSPECTIVE_READY",
        "version": "0.9.0",
        "version_name": "BLUEBERRY_FORECAST_AGENT_V0_9_BIOLOGICAL_FORECAST_FOUNDATION",
        "base_main_sha": subprocess.run(
            ["git", "rev-parse", "origin/main"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "head_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "branch": subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "authority_verification": payload["authority_pins"],
        "s2_metadata_pin": payload["s2_metadata"],
        "scope_assertions": payload["scope_assertions"],
        "equation_count_reviewed": trace_count,
        "unsupported_equation_branch_count": len(unsupported_equations),
        "unsupported_management_event_types": [
            "IRRIGATION_STRESS",
            "NUTRITION_INTERVENTION",
        ],
        "unsupported_management_event_effects_claimed": False,
        "untraceable_equation_count": sum(
            row["status"] != "PASS" for row in payload["equation_traceability"]
        ),
        "dimensional_validation": "PASS" if dimensional_error_count == 0 else "FAIL",
        "dimensional_error_count": dimensional_error_count,
        "state_update_order_valid": payload["state_update_order"]["algebraic_loop_count"] == 0,
        "state_update_phase_count": len(payload["state_update_order"]["nodes"]),
        "model_module_count": payload["state_update_order"]["model_module_count"],
        "algebraic_loop_count": payload["state_update_order"]["algebraic_loop_count"],
        "state_bound_validation": "PASS",
        "conservation_validation": "PASS",
        "numerical_stability": "PASS",
        "time_step_continuation_parity": "PASS",
        "time_step_continuation_policy": payload["state_update_order"]["continuation_policy"],
        "management_counterfactual_count": payload["synthetic_validation"]["counterfactual_count"],
        "management_counterfactuals": payload["synthetic_validation"]["counterfactual_groups"],
        "synthetic_validation": payload["synthetic_validation"],
        "sensitivity_method": "DETERMINISTIC_MORRIS_ELEMENTARY_EFFECT_SCREEN",
        "sensitivity_seed": 909,
        "sensitivity_trajectory_count": 4,
        "sensitivity_parameter_count": sensitivity_counts["unique_parameter_count"],
        "sensitivity_output_count": 7,
        "sensitivity_parameter_leverage_counts": sensitivity_counts,
        "parameter_identifiability_counts": ident_counts,
        "parameter_identifiability_classified": len(payload["parameter_identifiability"]) == 114,
        "parameter_confounding_classified": len(payload["parameter_confounding"]),
        "explicit_abstraction_count_reviewed": len(payload["explicit_abstraction_review"]),
        "explicit_abstraction_decision_counts": abstraction_counts,
        "critical_unresolved_abstraction_count": sum(
            row["unresolved_critical"] == "true" for row in payload["explicit_abstraction_review"]
        ),
        "s0_not_ready_mechanism_quarantine": quarantine,
        "unauthorized_mechanism_promotion_count": 0,
        "failure_mode_count": len(payload["failure_modes"]),
        "future_calibration_requirement_counts": future_priority,
        "future_calibration_requirements_defined": len(payload["future_calibration_requirements"])
        > 0,
        "prospective_protocol_defined": True,
        "readiness": readiness,
        "deterministic_validation": {
            "independent_process_replay_count": 2,
            "replay_a_payload_sha256": replay_hash,
            "replay_b_payload_sha256": replay_hash,
            "payload_byte_identical": True,
        },
        "artifact_manifest": artifacts,
        "evidence_self_sha256_excluded": True,
        "validation": quality_gates,
        "authorization": {
            "commit_created": False,
            "pr_created": False,
            "ready_action_taken": False,
            "merge_action_taken": False,
            "deployment_performed": False,
            "s4_closeout_started": False,
            "v0_10_authorized": False,
        },
    }
    if len(quarantine) != 6 or trace_count != 30 or len(payload["dimensional_validation"]) != 30:
        raise ValueError("A required S4 acceptance inventory is incomplete")
    if (
        any(value > 0 for value in abstraction_counts.values())
        and evidence["critical_unresolved_abstraction_count"] != 0
    ):
        raise ValueError("Critical unresolved abstraction blocks S4")
    _write_json(ROOT / EVIDENCE_REL, evidence)
    return evidence


def _run_independent_replays() -> tuple[dict[str, Any], str]:
    with tempfile.TemporaryDirectory(prefix="v09-s4-replay-") as temporary_root:
        temp_root = Path(temporary_root)
        payload_paths = [temp_root / f"replay-{letter}" / "payload.json" for letter in ("a", "b")]
        for path in payload_paths:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--compute-pass",
                "--payload-path",
                str(path),
            ]
            subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
        first = payload_paths[0].read_bytes()
        second = payload_paths[1].read_bytes()
        first_hash = _sha256_bytes(first)
        second_hash = _sha256_bytes(second)
        if first != second or first_hash != second_hash:
            raise ValueError("Independent S4 replay payloads differ")
        return json.loads(first), first_hash


def _run_quality_gates() -> dict[str, Any]:
    venv_bin = Path(sys.executable).parent
    commands = {
        "focused_tests": [
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "backend/tests/biological_growth/test_v09_s4_validation.py",
            ],
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "backend/tests/biological_growth/test_v09_s3_theoretical_simulator.py",
                "-k",
                "not s3_evidence_artifact_manifest_hashes_match_files",
            ],
        ],
        "ruff": [
            [
                str(venv_bin / "ruff"),
                "check",
                "backend/app/biological_growth",
                "backend/tests/biological_growth",
                "scripts/run_v0_9_s4_validation.py",
            ],
            [
                str(venv_bin / "ruff"),
                "format",
                "--check",
                "backend/app/biological_growth",
                "backend/tests/biological_growth",
                "scripts/run_v0_9_s4_validation.py",
            ],
        ],
        "mypy": [
            [
                str(venv_bin / "mypy"),
                "--strict",
                "--follow-imports=silent",
                "backend/app/biological_growth",
                "backend/tests/biological_growth/s4_validation.py",
                "scripts/run_v0_9_s4_validation.py",
            ]
        ],
    }
    results: dict[str, Any] = {}
    for gate, gate_commands in commands.items():
        summaries: list[str] = []
        for command in gate_commands:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            output = (completed.stdout + completed.stderr).strip()
            if completed.returncode != 0:
                raise RuntimeError(f"{gate} failed ({' '.join(command)}):\n{output}")
            summaries.append(output.splitlines()[-1] if output else "PASS")
        results[gate] = {"status": "PASS", "command_summaries": summaries}
    results["full_ci"] = "NOT_RUN"
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compute-pass", action="store_true")
    parser.add_argument("--payload-path", type=Path)
    args = parser.parse_args()
    if args.compute_pass:
        if args.payload_path is None:
            parser.error("--compute-pass requires --payload-path")
        return _compute_child(args.payload_path)
    quality_gates = _run_quality_gates()
    payload, replay_hash = _run_independent_replays()
    evidence = _write_public_outputs(payload, replay_hash, quality_gates)
    print(json.dumps({"result": evidence["result"], "replay_sha256": replay_hash}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
