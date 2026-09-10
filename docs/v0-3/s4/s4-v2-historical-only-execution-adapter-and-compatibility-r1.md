# V0.3 S4 V2 historical-only execution adapter and compatibility R1

> Review correction R2 preserves the frozen V2 candidate eligibility semantics, separates plan eligibility from current runnability, completes the audit to 8/8 candidates, and relabels budget numbers as freeze-point evidence rather than durable authority.

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

## C04 historical-only scorer readiness correction

The C04 readiness implementation adds a real SOURCE-002-only prediction path
without changing the V1 authority or running a candidate.  Candidate 04 is a
TRAIN-derived point-forecast amplitude multiplier, not a planning yield input:

```text
TASK_ID=V0_3_S4_C04_HISTORICAL_YIELD_SCORER_READINESS_R1
C04_PARAMETER_SEMANTIC=TRAIN_DERIVED_POINT_FORECAST_YIELD_AMPLITUDE_MULTIPLIER
C04_PARAMETER_UNIT=RATIO
C04_PARAMETER_PATH=yield_amplitude_multiplier
C04_PARAMETER_DERIVATION_POLICY=TRAIN_ONLY_CHRONOLOGICAL_INNER_FOLDS_BASE_MODEL_HORIZON_RATIO_MEDIAN_V2
C04_PARAMETER_VALUES=416.621234,24.896716,11.302801,3.911976
C04_PARAMETER_VALUE_COUNT=4
C04_PARAMETER_VALUES_UNIQUE_POSITIVE_FINITE=true
VALIDATION_USED_FOR_PARAMETER_DERIVATION=false
TEST_USED=false
```

The four values are the median actual-to-base-model-prediction ratio from four
chronological inner folds of TRAIN. Each earlier TRAIN fit predicts later TRAIN
rows at the exact 7/14/21 horizons; VALIDATION is not an input to derivation
and TEST is not read.
The candidate prediction is explicitly:

```text
candidate_prediction_total = base_prediction_total * yield_amplitude_multiplier
candidate_daily_p50 = candidate_prediction_total * curve_share
```

The scorer uses the existing `fit_shared_curve` modeling primitive and never
calls `run_local_replay`.  A baseline multiplier of `1.0` replays the base
amplitude exactly, while a different positive multiplier changes the canonical
prediction identity.  Full configuration snapshots, run-level hashes, and the
V2 plan/guardrail identities are bound in the C04 manifest.

```text
C04_HISTORICAL_ONLY_SCORING_PATH_EXISTS=true
C04_PARAMETER_REACHES_PREDICTION_MATH=true
C04_PARAMETER_CHANGE_CAN_CHANGE_PREDICTION=true
C04_SCORER_PATH=backend.app.s4_candidate_04_historical_yield.C04HistoricalYieldScorer.predict_rows
C04_V2_MANIFEST_BINDING=true
C04_PARAMETER_ALLOWLIST=yield_amplitude_multiplier
USES_SOURCE_002_TRAIN=true
USES_SOURCE_002_VALIDATION_TARGET_IDENTITIES=true
USES_WEATHER=false
USES_PRODUCTION_PLAN=false
USES_TASK8=false
USES_TASK9=false
```

The existing V2 compatibility audit now reports C04 as the only currently
runnable historical-only scorer.  This is execution readiness, not execution
authorization or selection:

```text
CURRENTLY_RUNNABLE_UNDER_V2_IDS=04_yield_parameter
NEXT_EXECUTABLE_CANDIDATE=04_yield_parameter
C04_FUTURE_EXECUTION_PRIMARY_METRIC_COMPUTABLE=true
C04_FUTURE_EXECUTION_FULL_GUARDRAIL_COMPUTABLE=false
C04_FUTURE_EXECUTION_GUARDRAIL_BLOCKER=COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE
```

The sparse 7/14/21 target surface still does not establish a complete daily
rowset.  The inherited cumulative, single-day peak, and sustained seven-day
guardrails therefore remain unavailable and are not weakened or zero-filled.
No STARTED event, VALIDATION metric result, candidate execution, budget debit,
or TEST access was introduced.

```text
LEGACY_RECONCILED_VALIDATION_DEBIT=4
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
FINAL_STOP_GATE=COORDINATOR_V0_3_S4_C04_HISTORICAL_SCORER_READINESS_REVIEW
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

The frozen V2 plan uses `current_v0_3_execution_eligible` to mean that a candidate is within the historical-only V0.3 lane and may proceed to a future, separately authorized V2 manifest. It does **not** mean that a runnable scorer already exists. R2 therefore keeps that frozen eligibility unchanged and separately records `currently_runnable_under_v2`.

A candidate is currently runnable only when the frozen eligibility is true and the repository has a V2-bound historical-only scoring path whose parameter or feature reaches prediction math and can change predictions. The audit covers all eight frozen registry entries.

| candidate | frozen historical-only eligible | V2 scoring path | currently runnable | reason |
| --- | --- | --- | --- | --- |
| `01_parameter_calibration` | true | false | false | `CANDIDATE_01_RERUN_FORBIDDEN` |
| `02_quantile_calibration` | true | false | false | `NO_V2_BOUND_PREDICTION_QUANTILE_PATH` |
| `03_phenology_offset` | true | false | false | `C03_NO_SOURCE_002_ONLY_SCORING_PATH` |
| `04_yield_parameter` | true | true | true | `C04_HISTORICAL_ONLY_SCORER_READY` |
| `05_marketable_rate` | true | false | false | `NO_BOUND_CANDIDATE_05_SCORING_PATH` |
| `06_weather_response` | false | false | false | `C06_WEATHER_OUTSIDE_V2_HISTORICAL_POLICY` |
| `07_harvest_efficiency` | true | false | false | `NO_BOUND_CANDIDATE_07_SCORING_PATH` |
| `08_residual_feature` | false | false | false | `V2_HISTORICAL_ONLY_FEATURE_MANIFEST_REQUIRED` |

Candidate 01 remains frozen as V2 historical-only eligible in the canonical plan but cannot be rerun. Candidate 02 has only a metric calculator, not a V2-bound prediction/quantile calibration path. Candidate 03's parameter reaches legacy maturity prediction math, but that legacy path consumes planning/weather/Task8/Task9 authority and is not a SOURCE-002-only V2 scorer. Candidates 04, 05, and 07 have historical-only-compatible hypotheses but no bound candidate-specific scorer. Candidates 06 and 08 remain ineligible under the frozen V2 overlay and are still included in the 8/8 compatibility audit.

```text
CANDIDATE_COMPATIBILITY_AUDIT_COMPLETE=true
AUDITED_CANDIDATE_COUNT=8
FROZEN_CURRENT_V0_3_EXECUTION_ELIGIBLE_IDS=01,02,03,04,05,07
CURRENTLY_RUNNABLE_UNDER_V2_IDS=04_yield_parameter
NEXT_EXECUTABLE_CANDIDATE=04_yield_parameter
C03_HISTORICAL_ONLY_SCORING_PATH_EXISTS=false
C03_CURRENT_V0_3_EXECUTION_ELIGIBLE=true
C03_CURRENTLY_RUNNABLE_UNDER_V2=false
```

## Execution, budget, and TEST safety

This implementation provides pure readiness and data-authority constructors.
It does not call the durable execution authority, create a STARTED event, run
the local scorer, score VALIDATION, or read TEST:

```text
DURABLE_VALIDATION_BUDGET_AUTHORITY=POSTGRESQL
BUDGET_STATE_CLASS=FREEZE_POINT_EVIDENCE_SNAPSHOT_NOT_DURABLE_READBACK
LEGACY_RECONCILED_VALIDATION_DEBIT=4
FREEZE_SNAPSHOT_CANONICAL_STARTED_COUNT=0
FREEZE_SNAPSHOT_EFFECTIVE_CONSUMED=4
FREEZE_SNAPSHOT_REMAINING=28
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

## R2 C04 parameter-derivation correction

The original C04 time-scaled fit-total derivation is superseded. The current
manifest values are derived by fitting an earlier TRAIN base model, predicting
later TRAIN rows at the exact 7/14/21 horizons, and taking the median
actual-to-base-prediction ratio. This correction changes only parameter
derivation; the C04 scorer path, V2 gate, and no-execution boundary remain
unchanged.

```text
TASK_ID=V0_3_S4_C04_PARAMETER_DERIVATION_CORRECTION_R2
OLD_ALGORITHM=FIT_TOTAL_DIVIDED_BY_FIT_DAYS_TIMES_HOLDOUT_DAYS
NEW_ALGORITHM=EARLIER_TRAIN_FIT_SAME_BASE_MODEL_PREDICTS_LATER_TRAIN_7_14_21_ACTUAL_OVER_BASE_PREDICTION_MEDIAN
C04_PARAMETER_DERIVATION_POLICY=TRAIN_ONLY_CHRONOLOGICAL_INNER_FOLDS_BASE_MODEL_HORIZON_RATIO_MEDIAN_V2
C04_PARAMETER_VALUES=416.621234,24.896716,11.302801,3.911976
C04_PARAMETER_MANIFEST_HASH=9cf648dfae3aab5f291503ad8ddf3979c2ad452f082c0ec2c7ff10f3a9f04c17
C04_PARAMETER_MANIFEST_CODE_COMMIT=b2def154e9851d90353b24ce8dddd16467e19539
VALIDATION_USED_FOR_PARAMETER_DERIVATION=false
TEST_USED=false
VALIDATION_EXECUTION=false
BUDGET_DELTA=0
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
