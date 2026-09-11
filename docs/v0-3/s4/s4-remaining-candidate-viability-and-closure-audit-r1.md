# V0.3 S4 remaining-candidate viability and closure audit R1

```text
TASK_ID=V0_3_S4_REMAINING_CANDIDATE_VIABILITY_AND_CLOSURE_AUDIT_R1
TASK_CLASS=READ_ONLY_CANDIDATE_AUTHORITY_AND_SELECTION_FEASIBILITY_AUDIT
BASE_MAIN_SHA=b0257192bb27097f30f279dcc735d6cc9da812bd
PR601_MERGE_IN_BASE=true
AUDIT_CANDIDATES=02_quantile_calibration,05_marketable_rate,07_harvest_efficiency
VALIDATION_EXECUTION_AUTHORIZED=false
VALIDATION_SCORING_AUTHORIZED=false
TEST_AUTHORIZED=false
```

## Conclusion

This audit is a code-path and authority audit only. It does not construct a
candidate scorer, load the SOURCE-002 rows, read VALIDATION outcomes, access
TEST, call the durable execution authority, or write the validation ledger.

The frozen V2 plan still registers candidates 02, 05, and 07 as
`REGISTERED_AND_GUARDRAIL_ELIGIBLE`. That registry fact is not the same as
current V4 runnability. The current code proves none of the three has a lawful
SOURCE-002-only candidate scoring path that also reaches prediction math.

```text
C02_PLAN_ELIGIBLE=true
C02_CURRENTLY_RUNNABLE_UNDER_V4=false
C02_STRUCTURALLY_SELECTABLE_UNDER_V4=false
C02_BLOCKER=C02_QUANTILE_ONLY_CANDIDATE_CANNOT_STRICTLY_IMPROVE_V4_PRIMARY_POINT_METRIC

C05_PLAN_ELIGIBLE=true
C05_CURRENTLY_RUNNABLE_UNDER_V4=false
C05_STRUCTURALLY_SELECTABLE_UNDER_V4=false
C05_BLOCKER=C05_CANONICAL_MARKETABLE_RATE_AUTHORITY_UNAVAILABLE_IN_SOURCE002_HISTORICAL_LANE

C07_PLAN_ELIGIBLE=true
C07_CURRENTLY_RUNNABLE_UNDER_V4=false
C07_STRUCTURALLY_SELECTABLE_UNDER_V4=false
C07_BLOCKER=C07_CANONICAL_HARVEST_EFFICIENCY_AUTHORITY_UNAVAILABLE_IN_SOURCE002_HISTORICAL_LANE

NEXT_EXECUTABLE_CANDIDATE=NONE
CURRENT_FROZEN_PLAN_HAS_NO_REMAINING_EXECUTABLE_CANDIDATE=true
S4_NEXT_DECISION_REQUIRED=COORDINATOR_CHOICE_BETWEEN_INCUMBENT_CLOSURE_OR_NEW_EXPERIMENT_PLAN_AUTHORIZATION
```

## Frozen authority and boundaries

The audit binds the corrected V2 historical-only plan and the V4 execution
overlay without changing either policy:

```text
EXPERIMENT_PLAN_VERSION=v0.3-experiment-plan-v2
EXPERIMENT_PLAN_HASH=c2bfab4ec38b4ca640f62d061494961c5b49afe5b52fa675326aa80fdf5f8ad9
GUARDRAIL_POLICY_VERSION=v0.3-s4-guardrail-policy-v4-breakdown-reporting-floor
GUARDRAIL_POLICY_HASH=f2b5c808d5a72170f055f891422f4253834a977cd5c74b450c8e4546653f46d2
SOURCE_002_MATERIALIZED_DATASET_IDENTITY=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_ROWS=16224
TRAIN_CONTENT_SHA256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
VALIDATION_ROWS=8006
VALIDATION_CONTENT_SHA256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
FORECAST_HORIZONS=7,14,21
WEATHER_REQUIRED=false
PRODUCTION_PLAN_REQUIRED=false
TASK8_TASK9_REQUIRED=false
PROSPECTIVE_CAPTURE_REQUIRED=false
WALL_CLOCK_WAIT_REQUIRED=false
TEST_REMAINS_SEALED=true
```

The V4 primary remains `daily_wape` with the strict relation
`candidate < incumbent`; the point guardrail remains `daily_mae` with
`candidate <= incumbent`. A candidate cannot become selectable by changing
the denominator, suppressing a breakdown cell, inventing a proxy parameter, or
reinterpreting a SOURCE-002 field.

## Code-level candidate audit

### C02 — quantile calibration

The registered paths are `intervals.p80_quantile` and
`intervals.p90_quantile`. The current implementation at
`backend/app/forecast_quality/quantile_coverage.py:192-266` computes empirical
coverage from already paired forecast and actual rows. It is a metric path,
not a V2-bound prediction path. The current V2 audit records that path at
`backend/app/s4_v2_historical_only_execution.py:224-240` and proves that the
candidate parameters do not reach prediction math.

Therefore changing the two registered interval values cannot change P50 or
the primary `daily_wape` prediction surface. Under the frozen strict primary
rule, a quantile-only candidate is structurally unselectable even though the
quantile coverage metrics themselves are legitimate metrics. A future C02
would require an explicitly authorized prediction/quantile adapter and a
policy decision; this audit does not create either.

### C05 — marketable rate

The current production-shaped core forecast path is
`backend.app.core_forecast.application.execute_core_forecast_run` and
`backend.app.core_forecast.service.compose_complete_daily_marketable_curve`.
The latter reads persisted Task8 and Task9 authorities before composing the
curve (`service.py:533-590`) and applies persisted sorting and post-harvest
retention policy to the harvested quantity (`service.py:395-525`). The
planning model and documentation define a separate planning formula using
`marketable_rate` (`backend/app/models/planning.py:236-250` and
`docs/11_production_plan_and_phenology.md:71-93`).

There is no bound C05 candidate scorer that takes an unambiguous SOURCE-002
historical marketable-rate authority and applies it to the V2 prediction math.
Treating actual harvest as marketable quantity, defaulting the rate, or
substituting a C04 amplitude multiplier would create a new semantic rather
than prove C05. The audit consequently fails closed with
`C05_CANONICAL_MARKETABLE_RATE_AUTHORITY_UNAVAILABLE_IN_SOURCE002_HISTORICAL_LANE`.

### C07 — harvest efficiency

The current harvest-state implementation is
`backend.app.harvest_state.service.run_harvest_state_model`. Its effective
capacity calculation multiplies nominal capacity by labor availability,
weather efficiency, and operational efficiency (`service.py:780-885`). The
weather ratio is computed by
`backend.app.harvest_state.weather.compute_weather_efficiency_ratio`
(`weather.py:49-68`), and the authority schemas/models persist the efficiency
fields (`authority_schemas.py:163-204`, `models/task9_authority.py:230-234`).

No V2-bound C07 candidate scorer or SOURCE-002-only historical definition of
the required efficiency authority is present. The audit does not invent an
actual-yield, peak-error, labor, or weather proxy. It fails closed with
`C07_CANONICAL_HARVEST_EFFICIENCY_AUTHORITY_UNAVAILABLE_IN_SOURCE002_HISTORICAL_LANE`.

## Compatibility matrix

| candidate | plan eligible | SOURCE-002-only input path | real candidate scorer | parameter reaches prediction math | changes prediction | V4 runnable | disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `02_quantile_calibration` | true | not bound | metric-only coverage function | false | false | false | quantile-only candidate cannot strictly improve V4 point primary |
| `05_marketable_rate` | true | not proven | none | false | false | false | marketable-rate authority unavailable in SOURCE-002 lane |
| `07_harvest_efficiency` | true | not proven | none | false | false | false | harvest-efficiency authority unavailable in SOURCE-002 lane |

Compatibility requires both historical-only input compatibility and a real
candidate parameter/feature effect on the scoring path. A manifest or registry
row alone is insufficient.

## Frozen plan closure

The complete current V4 overlay is also reconciled so that this audit does not
mistake an omitted candidate for a next step:

| candidate | plan eligibility | current V4 runnability | current reason |
| --- | --- | --- | --- |
| `01_parameter_calibration` | true | false | `CANDIDATE_01_RERUN_FORBIDDEN` |
| `02_quantile_calibration` | true | false | C02 quantile-only structural blocker |
| `03_phenology_offset` | true | false | canonical shift model not separable from forward-looking authority |
| `04_yield_parameter` | true | false | `C04_EXHAUSTED_EVIDENCE_INSUFFICIENT` |
| `05_marketable_rate` | true | false | C05 SOURCE-002 authority unavailable |
| `06_weather_response` | false | false | `C06_WEATHER_OUTSIDE_V2_HISTORICAL_POLICY` |
| `07_harvest_efficiency` | true | false | C07 SOURCE-002 authority unavailable |
| `08_residual_feature` | false | false | `V2_HISTORICAL_ONLY_FEATURE_MANIFEST_REQUIRED` |

The C01 rerun prohibition, C03 canonical-shift blocker, and C04 exhausted
evidence closure remain prior facts. They are not reopened by this audit.

Because no candidate is currently runnable under the frozen V4 overlay, the
audit issues no candidate, no incumbent selection, no TEST authorization, and
no new experiment plan. The only coordinator decision left at this boundary
is whether to close the current frozen S4 lane around the incumbent or
separately authorize a new experiment-plan change.

## Execution and budget proof

The audit implementation is pure and read-only. It contains no dataset loader,
scorer callback, TEST reader, database repository, or ledger write. The
freeze-point budget facts remain:

```text
LEGACY_RECONCILED_VALIDATION_DEBIT=4
CANONICAL_STARTED_COUNT=4
EFFECTIVE_CONSUMED=8
REMAINING=24
BUDGET_DELTA=0
EVALUATION_STARTED_CREATED=false
EVALUATION_TERMINAL_CREATED=false
VALIDATION_SCORING_PERFORMED=false
CANDIDATE_EXECUTION_PERFORMED=false
VALIDATION_DATA_REREAD=false
TEST_ACCESS_REQUESTED=false
TEST_BYTES_READ=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
```

The farm-total baseline remains a historical TRAIN-only median comparison
reference. It is not promoted to the selected model and it does not acquire
invented P80/P90 outputs.

## Audit implementation

`backend/app/s4_remaining_candidate_viability.py` provides the immutable
read-only audit rows and the eight-candidate closure payload. Its tests verify
that registry plan eligibility is independent from current runnability, the
C02 strict-primary disposition is preserved, C05/C07 missing authority fails
closed, and the audit cannot create an evaluation event or access TEST.

This artifact is an audit result, not authorization to implement or execute
C02, C05, or C07.

```text
RESULT=AUDITED_AND_PUSHED
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S4_REMAINING_CANDIDATE_VIABILITY_REVIEW
```

## R2 authority-binding correction

This append-only correction supersedes the R1 presentation of the remaining
candidate audit without changing the frozen V2 plan, V4 policy, or any prior
execution evidence.

```text
TASK_ID=V0_3_S4_REMAINING_CANDIDATE_AUTHORITY_BINDING_CORRECTION_R2
RESULT=CORRECTED_AND_PUSHED
EXPERIMENT_PLAN_VERSION=v0.3-experiment-plan-v2
EXPERIMENT_PLAN_HASH=c2bfab4ec38b4ca640f62d061494961c5b49afe5b52fa675326aa80fdf5f8ad9
GUARDRAIL_POLICY_VERSION=v0.3-s4-guardrail-policy-v4-breakdown-reporting-floor
GUARDRAIL_POLICY_HASH=f2b5c808d5a72170f055f891422f4253834a977cd5c74b450c8e4546653f46d2
V2_CURRENT_EXECUTION_ELIGIBLE=01,02,03,04,05,07
V2_CURRENT_EXECUTION_INELIGIBLE=06,08
FROZEN_REGISTRY_SELECTION_ELIGIBILITY=REGISTERED_AND_GUARDRAIL_ELIGIBLE_FOR_ALL_EIGHT
CURRENT_V4_RUNNABILITY=NONE
NEXT_EXECUTABLE_CANDIDATE=NONE
```

The registry identity, family, hypothesis, and planned-run facts now come
directly from `FROZEN_CANDIDATE_REGISTRY`. The current V2 execution overlay
comes from `build_v2_candidate_compatibility_audit`; it is intentionally
separate from the registry's selection-eligibility string. In particular,
`06_weather_response` and `08_residual_feature` are not current V2 execution
eligible even though their immutable registry registrations remain visible.

### C02 corrected disposition

The C02 path is a metric-only empirical upper-quantile coverage function, not a
V2-bound prediction path. A synthetic Decimal-only proof changes P80/P90 while
keeping P50 unchanged. Therefore the V4 `daily_wape` value is equal to the
incumbent and `compare_primary_metric` returns `FAIL` with `NOT_IMPROVED`.

```text
IMPLEMENTATION_BLOCKER=NO_V2_BOUND_PREDICTION_QUANTILE_PATH
STRUCTURAL_SELECTION_BLOCKER=C02_QUANTILE_ONLY_CANDIDATE_CANNOT_STRICTLY_IMPROVE_V4_PRIMARY_POINT_METRIC
C02_REQUIRES_POLICY_AMENDMENT=true
```

No policy amendment is issued by this audit.

### C05 corrected canonical path

The direct `marketable_rate` authority is the planning/maturity upstream path:

```text
planted_area_mu * expected_yield_kg_per_mu * marketable_rate
    -> expected_total_marketable_kg
```

The canonical functions are `_derived_total`, `_prepare_plan_inputs`,
`_resolve_training_sample`, and `forecast_natural_maturity`. The core daily
curve function is not reported as a direct `marketable_rate` execution path;
its separate conversion uses harvested quantity with sorting and post-harvest
retention. An explicit `expected_total_marketable_kg` override exists. Since
SOURCE-002 does not provide the required planted-area/yield/marketable-rate
authority, C05 remains unrunnable under V4 with blocker
`C05_CANONICAL_MARKETABLE_RATE_AUTHORITY_UNAVAILABLE_IN_SOURCE002_HISTORICAL_LANE`.

### C07 corrected canonical path

The canonical harvest-efficiency path resolves effective capacity from labor
availability, weather efficiency, and operational efficiency, producing
`resolved_effective_capacity_kg_per_day`. It is implemented through
`_validated_request`, `compute_weather_efficiency_ratio`, and
`run_harvest_state_model`, with Task9, weather, and holiday authority. Those
inputs are not SOURCE-002 historical-only authority, so C07 remains closed
under V4 with its existing canonical-input blocker.

### Budget provenance and execution boundary

This audit did not perform a PostgreSQL readback. The reported 4/8/24 values
are explicitly the last accepted durable snapshot from
`s4-c04-controlled-real-validation-r1.json`, SHA-256
`78b1489b28fe0056e1c7fd88165f927c04d16bf1083926048ba4c36e3c1498b3`; they are
not presented as a current database read. No ledger write, validation data
read, scorer call, candidate execution, or TEST access occurred.

```text
DURABLE_BUDGET_READBACK_AVAILABLE=false
LAST_ACCEPTED_CANONICAL_STARTED_COUNT=4
LAST_ACCEPTED_EFFECTIVE_CONSUMED=8
LAST_ACCEPTED_REMAINING=24
NEW_VALIDATION_EXECUTION=false
NEW_VALIDATION_SCORING=false
EVALUATION_STARTED_CREATED=false
TEST_REMAINS_SEALED=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S4_REMAINING_CANDIDATE_AUTHORITY_R2_REVIEW
```

The machine-derived projection in the evidence JSON is generated by
`build_machine_derived_audit_payload()` and is covered by the checked-in
golden consistency test.
