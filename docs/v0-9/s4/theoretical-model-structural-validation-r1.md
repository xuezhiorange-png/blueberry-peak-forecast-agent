# V0.9-S4 — Theoretical Model Structural Validation and Identifiability

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
* Synthetic invariants: **813 checks**;
  golden scenarios: **11**; robustness cases:
  **33**.
* Full-season one-shot/stateful 7-day chunk output parity:
  **True**. This is an in-memory stateful
  generator test; a serialized/process-restart checkpoint format is not claimed.
* Deterministic independent process replay payload SHA-256:
  `02494ff3905a7262b8b0902dd08f3cfb0fcbf17713314b9c74940e93fca7f72c` (both passes byte-identical).

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
| NO_PRUNING | 1.000000 | 78.985455 | 0.256645 | 12.000000 | 16.650787 |
| LIGHT | 0.907000 | 74.966107 | 0.239322 | 12.009000 | 14.368261 |
| MODERATE | 0.752000 | 68.263522 | 0.210449 | 12.024000 | 10.853013 |
| HEAVY | 0.535000 | 58.851146 | 0.170027 | 12.045000 | 6.554230 |

Across no/light/moderate/heavy interventions, fruiting wood, bud potential,
leaf/source structure, and future shoot potential respond through separate
state paths. Seasonal mass is reported as an outcome, not assigned a required
direction.

### Flower thinning is not pruning

| Level | Effective flower load | Fruit number | Final leaf area |
|---|---:|---:|---:|
| NONE | 69.041277 | 22.446756 | 0.680000 |
| LIGHT | 61.444895 | 20.128349 | 0.680000 |
| MODERATE | 51.316386 | 16.997708 | 0.680000 |
| HEAVY | 33.591495 | 11.381842 | 0.680000 |

Thinning changes effective reproductive load and potential fruit number while
leaf area remains unchanged in this counterfactual. The source-per-fruit proxy
increases under heavier thinning. No proportional season-yield rule is imposed.

### Crop load and inter-season linkage

| Level | Fruit load | Sink | Source/sink sufficiency | Reserve | Next-season buds |
|---|---:|---:|---:|---:|---:|
| LOW | 8.541167 | 0.235636 | 0.999469 | 0.654917 | 1.162974 |
| MEDIUM | 19.140610 | 0.305035 | 0.904786 | 0.627815 | 1.131791 |
| HIGH | 34.508873 | 0.405605 | 0.779282 | 0.589547 | 1.086582 |
| OVER_CROPPED | 64.423480 | 0.598252 | 0.674243 | 0.519086 | 0.898907 |

These are synthetic normalized indices, not measured carbon or bud counts.
The two-season test carries reserve/vigor outputs into the second-season
initial state and keeps next-season bud potential as a separate latent index;
it is never cast to buds/plant.

### Chilling, forcing, evergreen, pollination, and fruit cohorts

| Chill case | Final exposure (model units) | Release inferred | Final forcing (degree-day) |
|---|---:|---:|---:|
| INSUFFICIENT | 0.000000 | False | 0.000000 |
| NEAR_THRESHOLD | 244.000000 | False | 0.000000 |
| SUFFICIENT | 425.000000 | True | 3672.750178 |
| EXCESS | 1806.000000 | True | 2742.438603 |

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

* HIGH_LEVERAGE: 13
* MEDIUM_LEVERAGE: 3
* LOW_LEVERAGE: 0
* NEGLIGIBLE_WITHIN_TESTED_RANGE: 8
* INTERACTION_SUSPECTED parameter/output pairs:
  8

These labels describe leverage only; no parameter value, model family, or
threshold is selected. The full parameter/output effects and tested ranges are
in the sensitivity register.

The 114-parameter identifiability register is structural, not a statistical
confidence analysis. Counts: {"CONDITIONALLY_IDENTIFIABLE": 19, "CONFOUNDED": 24, "LITERATURE_PRIOR_ONLY": 22, "OBSERVATION_DEPENDENT": 37, "UNIDENTIFIABLE_IN_V1": 12}.
Composite source/sink, flower-count × set-probability, density × per-plant
productivity, thermal requirement × microclimate response, and berry-weight ×
marketable fraction are explicit confounding groups. Minimum disambiguating
observations are mapped per parameter; the S2 audit remains the source for what
is available now. No 2025–2026 actuals were loaded or scored.

## Abstraction review and quarantine

All 18 explicit S3 abstractions were reviewed. Decisions:
`{"ACCEPT_V1": 3, "RECLASSIFY_RESEARCH_ONLY": 1, "REQUIRE_NEW_AUTHORITY": 1, "RESTRICT_DOMAIN": 13}`. High-risk abstractions are
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
future calibration register has 11 P0, 5
P1, and 4 P2 requirements. P0 collection/authority is a
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
`02494ff3905a7262b8b0902dd08f3cfb0fcbf17713314b9c74940e93fca7f72c`. The machine evidence lists SHA-256 for every S4 output and code
artifact; its own hash is excluded from its internal manifest. Full CI was not
run. No commit, PR, Ready, Merge, deployment, or S4→next-stage action occurred.

## Local validation gates

* Focused tests: `PASS`; S4 and S3 focused suites: ['20 passed in 11.98s', '40 passed, 1 deselected in 8.79s'].
* Ruff check/format: `PASS`.
* Mypy: `PASS` (strict, S4/app scope; imported frozen S3 fixture/test typing diagnostics suppressed).
* Full CI: `NOT_RUN`.
