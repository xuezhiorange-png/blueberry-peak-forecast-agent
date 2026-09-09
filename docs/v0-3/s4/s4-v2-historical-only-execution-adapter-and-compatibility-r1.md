# V0.3 S4 V2 historical-only execution adapter and compatibility R1

This document records the V2 execution-readiness adapter. It binds the
current execution policy to the accepted SOURCE-002 historical TRAIN and
VALIDATION partitions, and audits the registered candidate code paths. It does
not start a candidate, score VALIDATION, access TEST, or mutate the validation
budget.

## Frozen execution identities

The V1 authority remains replayable and is not overwritten:

```text
EXPERIMENT_PLAN_V1=v0.3-experiment-plan-v1
EXPERIMENT_PLAN_V1_HASH=9e223a02a1b38c028c230a45eb1fa8323f3c2247bb85e7b439f3351e51042500
GUARDRAIL_POLICY_V1_HASH=74ecd47339572955e654cf61c38ee6b0546ba51a36e67f80f6ad4dd4519f1ff8
```

The current execution policy is a separate V2 object:

```text
EXPERIMENT_PLAN_V2=v0.3-experiment-plan-v2
EXPERIMENT_PLAN_V2_HASH=c2bfab4ec38b4ca640f62d061494961c5b49afe5b52fa675326aa80fdf5f8ad9
GUARDRAIL_POLICY_V2_VERSION=v0.3-s4-guardrail-policy-v2
GUARDRAIL_POLICY_V2_HASH=65ad056b3085b7ff41d25e1a7a86b990ac0f837270d62f6fd84ce5938843c793
```

The V2 overlay is historical-only and fail-closed:

```text
HISTORICAL_DATA_ONLY=true
WEATHER_REQUIRED=false
PRODUCTION_PLAN_REQUIRED=false
TASK8_TASK9_REQUIRED=false
PROSPECTIVE_CAPTURE_REQUIRED=false
WALL_CLOCK_WAIT_REQUIRED=false
FORECAST_HORIZONS=7,14,21
TEST_REMAINS_SEALED=true
CANDIDATE_01_RERUN_FORBIDDEN=true
CANDIDATE_06_EXECUTION_ELIGIBLE=false
CANDIDATE_08_EXECUTION_ELIGIBLE=false
```

The inherited metric and comparison formulas are copied into the V2 policy
preimage without changing their V1 meaning. The new hash covers the V2 plan
binding and execution overlay; it is not a V1 hash relabeled as V2.

## SOURCE-002 historical authority

The adapter verifies the official partition content hashes and row counts
before constructing the authority object:

```text
SOURCE=SOURCE_002
MATERIALIZED_DATASET_IDENTITY=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_ROWS=16224
TRAIN_CONTENT_SHA256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
VALIDATION_ROWS=8006
VALIDATION_CONTENT_SHA256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
TEST_ROW_COUNT=0
TEST_REMAINS_SEALED=true
```

The historical cutoff is derived from the governed data, not supplied as a
literal policy date:

```text
CUTOFF_RULE=max(TRAIN.harvest_business_date)
TRAIN_END_DERIVED=2026-01-30
VALIDATION_START=2026-01-31
```

Evaluation targets are the held-out VALIDATION rows whose date offset from the
derived cutoff is exactly 7, 14, or 21 days. The current fixture has 688 such
target rows and all three requested offsets are observed. These target values
are evaluation labels only; `v2_training_rows()` returns the exact TRAIN tuple
and never returns VALIDATION rows for fitting.

The adapter emits these row-free identity values:

```text
TRAIN_DATASET_IDENTITY=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
VALIDATION_DATASET_IDENTITY=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
ACTUAL_LABEL_SET_IDENTITY=0e16328e531fc1509324c51d1b019f188b182ccce59a3d50f35f4516cd49ba5a
CUTOFF_POLICY_IDENTITY=58a2cffb8e42b80206c06b57e9040fe6aefeea6e5edaf259af961487ac3287c1
FORECAST_HORIZON_SET_IDENTITY=6c4f20463009ddfe68aa198e47e3331a2608cb5bf50825c9a0128b5f1d603c4c
BUSINESS_GRAIN_SET_IDENTITY=fb3533257a48ef547a75a3f62f40949947e4109bbc37487758a963f7f96dbc09
COMMON_COMPARABLE_SET_IDENTITY=4ea0db5f4e61189aa2390ee5a6b51d9cc7ca2dea70d327da10f86b8c6c662807
```

The accepted loader opens only `train.content.gz` and `validation.content.gz`.
There is no TEST path in the V2 authority constructor.

## Metric availability and guardrail disposition

The adapter exposes computability rather than pretending that a missing window
is complete:

```text
DAILY_WAPE=COMPUTABLE_AFTER_HISTORICAL_ONLY_SCORING_PATH
DAILY_MAE=COMPUTABLE_AFTER_HISTORICAL_ONLY_SCORING_PATH
P80_COVERAGE=COMPUTABLE_AFTER_HISTORICAL_ONLY_SCORING_PATH
P90_COVERAGE=COMPUTABLE_AFTER_HISTORICAL_ONLY_SCORING_PATH
CUMULATIVE_ABSOLUTE_ERROR_KG_Q=COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE
SINGLE_DAY_PEAK_QUANTITY_ABSOLUTE_ERROR_KG_Q=COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE
SUSTAINED_7DAY_QUANTITY_ABSOLUTE_ERROR_KG_Q=COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE
S4_B_GUARDRAIL_DISPOSITION=BLOCKED_UNDER_INHERITED_POLICY_WHEN_REQUIRED_COMPLETE_WINDOW_METRICS_UNAVAILABLE
```

The 688 sparse target rows are not represented as a complete daily curve, and
missing days are never zero-filled. No scoring is run by this adapter.

## Code-level candidate compatibility audit

Compatibility requires both historical-only input compatibility and a real
V2-bound path whose parameter reaches prediction math and can change the
prediction. A manifest or a parameter name alone is not enough.

| candidate | actual path | data/input finding | reaches prediction math | parameter can change prediction | V2 historical path | current eligible | reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `01_parameter_calibration` | `backend.app.s4_local_engineering.run_local_replay` | SOURCE-002 TRAIN/VALIDATION plus curve config | true | true | false | false | `CANDIDATE_01_RERUN_FORBIDDEN` |
| `02_quantile_calibration` | `backend.app.forecast_quality.quantile_coverage.compute_upper_quantile_coverage` | S3-bound forecast/actual metric rows, not a V2 prediction path | false | false | false | false | `NO_V2_BOUND_PREDICTION_QUANTILE_PATH` |
| `03_phenology_offset` | legacy maturity service plus no V2 local scorer | production plan, weather, and Task8/Task9 runtime authority | true in legacy path | true in legacy path | false | false | `C03_NO_SOURCE_002_ONLY_SCORING_PATH` |
| `04_yield_parameter` | no bound candidate scorer | no actual V2 execution function | false | false | false | false | `NO_BOUND_CANDIDATE_04_SCORING_PATH` |
| `05_marketable_rate` | no bound candidate scorer | no actual V2 execution function | false | false | false | false | `NO_BOUND_CANDIDATE_05_SCORING_PATH` |
| `07_harvest_efficiency` | no bound candidate scorer | no actual V2 execution function | false | false | false | false | `NO_BOUND_CANDIDATE_07_SCORING_PATH` |

Candidate 01 remains permanently blocked from rerun despite its old local
scorer using the historical partitions. Candidate 02 currently has only a
metric calculator; it does not produce the candidate-specific historical
predictions required for lawful quantile calibration. Candidate 03's
`offset.maximum_abs_shift_days` reaches the legacy maturity prediction math,
but that path consumes planning/weather/Task8/Task9 authority and is not a
SOURCE-002-only V2 scorer. It is therefore explicitly fail-closed rather than
wired to the old forward-looking service.

Candidates 06 and 08 remain blocked by the V2 eligibility overlay: 06 requires
weather-response authority and 08 lacks a V2-bound historical-only feature
manifest. Neither is included in the six-candidate V2-eligible audit table.

```text
CANDIDATE_COMPATIBILITY_AUDIT_COMPLETE=true
NEXT_EXECUTABLE_CANDIDATE=NONE
C03_HISTORICAL_ONLY_SCORING_PATH_EXISTS=false
C03_CURRENT_V0_3_EXECUTION_ELIGIBLE=false
```

## Execution, budget, and TEST safety

This implementation provides pure readiness and data-authority constructors.
It does not call the durable execution authority, create a STARTED event, run
the local scorer, score VALIDATION, or read TEST:

```text
LEGACY_RECONCILED_VALIDATION_DEBIT=4
CANONICAL_STARTED_COUNT=0
EFFECTIVE_CONSUMED=4
REMAINING=28
BUDGET_DELTA=0
EVALUATION_STARTED_CREATED=false
CANDIDATE_EXECUTION_PERFORMED=false
VALIDATION_SCORING_PERFORMED=false
C01_RERUN_PERFORMED=false
TEST_ACCESS_REQUESTED=false
TEST_PAYLOAD_OBTAINED=false
TEST_EVALUATION_PERFORMED=false
SELECTED_CANDIDATE_ID=NOT_ISSUED
```

The farm-total baseline remains a separate historical TRAIN-only median
reference. It is not redefined as the selected V0.3 model and no baseline P80
or P90 is invented.

## Reuse and non-scope

V1 canonical policy and the existing local metric contract remain untouched.
The adapter reuses the existing SOURCE-002 partition loader, canonical JSON
hashing, `MaterializableRow`, and `LocalEngineeringContractError`. It does not
modify the V1 candidate manifest, the durable budget authority, production
forecast flows, or TEST policy.

No candidate is selected or authorized by this readiness result. A future
candidate execution requires a separately V2-bound manifest and explicit
execution authorization after a real SOURCE-002-only scoring path exists.

```text
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TEST_REMAINS_SEALED=true
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S4_V2_EXECUTION_COMPATIBILITY_REVIEW
```

## R2 correction — durable execution gate binding

The durable authority now dispatches the existing public gate by the request's
explicit experiment-plan/policy identity. V1 requests continue to use the V1
plan and guardrail hash; V2 requests use the V2 plan and the corrected V2
guardrail hash. This keeps V1 replayability intact and prevents a V2 request
from being rejected solely by a V1-only execution adapter.

The V2 canonical guardrail policy contains immutable policy facts only. The
observed runtime values `canonical_started_count=0`, `effective_consumed=4`,
and `remaining=28` remain readiness evidence and are read from the durable
PostgreSQL authority; they are excluded from the V2 policy preimage.

```text
TASK_ID=V0_3_S4_V2_DURABLE_EXECUTION_GATE_BINDING_CORRECTION_R2
TARGET_PR=597
PREVIOUS_HEAD_SHA=8b38e50dee8d88f5943b4d1daa710a1893b59ddb
V1_REPLAYABILITY_PRESERVED=true
V2_EXECUTION_GATE_ROUTED_BY_EXPLICIT_IDENTITY=true
V2_GUARDRAIL_POLICY_HASH=65ad056b3085b7ff41d25e1a7a86b990ac0f837270d62f6fd84ce5938843c793
V2_RUNTIME_COUNTERS_EXCLUDED_FROM_POLICY_HASH=true
V2_PREFLIGHT_READS_DURABLE_BUDGET_STATE=true
V2_PREFLIGHT_CREATES_NO_STARTED_EVENT=true
V2_PREFLIGHT_CALLS_NO_SCORER=true
CURRENT_V2_BOUND_EXECUTION_ADAPTER_IMPLEMENTED=true
NEXT_EXECUTABLE_CANDIDATE=NONE
CANONICAL_STARTED_COUNT=0
EFFECTIVE_CONSUMED=4
REMAINING=28
BUDGET_DELTA=0
CANDIDATE_EXECUTION_PERFORMED=false
VALIDATION_SCORING_PERFORMED=false
TEST_REMAINS_SEALED=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_PR597_V2_DURABLE_EXECUTION_GATE_R2_REVIEW
```
