# V0.3 S4 C04 historical yield scorer readiness R1

This package binds Candidate 04 to the corrected V2 historical-only execution
authority. It implements a deterministic, SOURCE-002-only prediction path and
freezes its TRAIN-derived parameter manifest. It does not execute a candidate,
score VALIDATION, create a durable `EVALUATION_STARTED`, consume budget, or read
TEST.

## Frozen authority

```text
TASK_ID=V0_3_S4_C04_HISTORICAL_YIELD_SCORER_READINESS_R1
BASE_MAIN_SHA=754386d1ae90a322dd2334793936143bab97eb0a
CANDIDATE_ID=04_yield_parameter
CANDIDATE_FAMILY=PARAMETER_CALIBRATION
PARENT_MODEL_ID=V0_2_CURRENT_MODEL
EXPERIMENT_PLAN_VERSION=v0.3-experiment-plan-v2
EXPERIMENT_PLAN_HASH=c2bfab4ec38b4ca640f62d061494961c5b49afe5b52fa675326aa80fdf5f8ad9
GUARDRAIL_POLICY_VERSION=v0.3-s4-guardrail-policy-v2
GUARDRAIL_POLICY_HASH=65ad056b3085b7ff41d25e1a7a86b990ac0f837270d62f6fd84ce5938843c793
V0_3_FORECAST_INPUT_BASIS=HISTORICAL_DATA_ONLY
FORECAST_HORIZONS=7,14,21
TEST_REMAINS_SEALED=true
```

The V1 plan and guardrail identities remain immutable and replayable. C04 is
bound to the V2 gate and to the existing frozen C04 registry entry; no registry
or experiment-plan object was changed.

## Parameter semantics and derivation

The C04 parameter is a quantity-amplitude multiplier, not a planning
`expected_yield_kg_per_mu`, marketable-rate input, weather feature, or maturity
phase adjustment:

```text
C04_PARAMETER_SEMANTIC=TRAIN_DERIVED_POINT_FORECAST_YIELD_AMPLITUDE_MULTIPLIER
C04_PARAMETER_UNIT=RATIO
C04_PARAMETER_PATH=yield_amplitude_multiplier
BASELINE_MULTIPLIER=1.0
```

Exactly four values are derived from SOURCE-002 TRAIN. Four chronological inner
folds fit the same historical base model on earlier TRAIN dates, then predict
the later TRAIN target dates at exactly +7, +14, and +21 days. Each fold
computes the robust median of `actual_harvest_quantity_kg / base_prediction`
over those comparable target rows. The resulting fold medians are fixed in
ordinal order:

```text
RUN_1=416.621234
RUN_2=24.896716
RUN_3=11.302801
RUN_4=3.911976
PARAMETER_VALUE_COUNT=4
VALUES_UNIQUE=true
VALUES_POSITIVE=true
VALUES_FINITE=true
DERIVATION_DETERMINISTIC=true
VALIDATION_USED_FOR_PARAMETER_DERIVATION=false
TEST_USED=false
ADAPTIVE_SEARCH_ALLOWED=false
POST_VALIDATION_PARAMETER_SUBSTITUTION_ALLOWED=false
```

The incumbent configuration is read from `configs/maturity_curve.yaml` and
stored as a Decimal-normalized full snapshot. Every candidate snapshot differs
from it only by the additional C04 amplitude path. The allowlist rejects curve,
pooling, offset, forecast, or any other parameter change. The incumbent file
and config hashes are:

```text
INCUMBENT_CONFIG_FILE_SHA256=fc023976a228c36556ed5f7ababe722a3dd8a558ed11e0473eb415b52dd69ace
INCUMBENT_CONFIG_HASH=3571477d5822f57cd2c424620915560e22481f48983b397a1f1b8934e1a7612c
```

## Historical scorer path

`C04HistoricalYieldScorer` obtains fitting rows through
`v2_training_rows(authority)`, which returns only the verified SOURCE-002 TRAIN
tuple. It accepts the V2 authority's held-out 7/14/21 target identities for a
future score surface, but it does not use target actual quantities in model
fitting. There is no TEST reader and no weather, production-plan, Task8, or
Task9 dependency.

The scorer reuses the repository `fit_shared_curve` primitive and preserves the
historical base math:

```text
base_p50 = base_prediction_total * curve_share
candidate_prediction_total = base_prediction_total * multiplier
candidate_p50 = candidate_prediction_total * curve_share
```

With `multiplier=1.0`, candidate P50 is an exact replay of the base amplitude.
A different positive multiplier changes the P50 payload and its canonical
prediction identity. The scorer is intentionally not `run_local_replay`; the
V2 audit now points to:

```text
C04_SCORER_PATH=backend.app.s4_candidate_04_historical_yield.C04HistoricalYieldScorer.predict_rows
C04_HISTORICAL_ONLY_SCORING_PATH_EXISTS=true
C04_PARAMETER_REACHES_PREDICTION_MATH=true
C04_PARAMETER_CHANGE_CAN_CHANGE_PREDICTION=true
```

The C04 gate-request builder binds the V2 plan, V2 guardrail policy, frozen
registry, manifest/run hash, SOURCE-002 pairing identities, exact horizons,
and the current runtime count of four as a readiness input. It is a pure
request builder; it does not call `S4CandidateExecutionAuthority.execute`.

## Metric boundary

The primary point metric `daily_wape` is marked computable after a separately
authorized historical-only scoring run. The sparse 7/14/21 target surface does
not prove a complete daily rowset, so the inherited full-window metrics remain
unavailable:

```text
C04_FUTURE_EXECUTION_PRIMARY_METRIC_COMPUTABLE=true
C04_FUTURE_EXECUTION_FULL_GUARDRAIL_COMPUTABLE=false
C04_FUTURE_EXECUTION_GUARDRAIL_BLOCKER=COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE
cumulative_absolute_error_kg=NOT_COMPUTABLE
single_day_peak_quantity_absolute_error_kg_q=NOT_COMPUTABLE
sustained_7day_quantity_absolute_error_kg_q=NOT_COMPUTABLE
MISSING_DAY_ZERO_FILL=false
```

No guardrail threshold or metric formula was weakened.

## Safety and current decision

```text
C04_PARAMETER_MANIFEST_VERSION=v0.3-s4-c04-yield-parameter-manifest-v1
C04_PARAMETER_MANIFEST_HASH=9cf648dfae3aab5f291503ad8ddf3979c2ad452f082c0ec2c7ff10f3a9f04c17
C04_PARAMETER_MANIFEST_CODE_COMMIT=b2def154e9851d90353b24ce8dddd16467e19539
C04_PARAMETER_MANIFEST_FROZEN=true
C04_CURRENT_V0_3_EXECUTION_ELIGIBLE=true
C04_CURRENTLY_RUNNABLE_UNDER_V2=true
NEXT_EXECUTABLE_CANDIDATE=04_yield_parameter
```

This is a scorer-readiness result only. It does not select C04, authorize it,
or imply a future run. The durable PostgreSQL budget remains unchanged:

```text
LEGACY_RECONCILED_VALIDATION_DEBIT=4
CANONICAL_STARTED_COUNT=0
EFFECTIVE_CONSUMED=4
REMAINING=28
BUDGET_DELTA=0
EVALUATION_STARTED_CREATED=false
CANDIDATE_EXECUTION_PERFORMED=false
VALIDATION_SCORING_PERFORMED=false
TEST_ACCESS_REQUESTED=false
TEST_BYTES_READ=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S4_C04_HISTORICAL_SCORER_READINESS_REVIEW
```

## Verification coverage

The C04 contract tests cover TRAIN-only derivation, exact four-value and
chronological-fold invariants, native-float rejection, canonical manifest and
run-hash replay, full-snapshot allowlisting, no-weather/no-plan/no-Task8/Task9
inputs, exact horizons, base replay, prediction identity change, V2 gate
binding, no STARTED event, unchanged budget, and the sealed TEST boundary.
The existing V2 S4 adapter suite was updated only to reflect the now-proven
C04 path; C01 remains forbidden and C06/C08 remain V2-ineligible.

## R2 parameter-derivation correction

The original R1 derivation used `fit_total / fit_days * holdout_days` as the
baseline. That time-scaled total folds seasonal ramp-up into the amplitude and
is superseded. The current R2 derivation fits an earlier TRAIN base model,
predicts later TRAIN rows at the frozen 7/14/21-day horizons, and takes the
median of each comparable row's actual-to-base-prediction ratio. It remains
TRAIN-only and deterministic; VALIDATION and TEST are not read.

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
C04_SCORER_PATH=KEEP
V2_GATE=KEEP
VALIDATION_EXECUTION=false
LEGACY_RECONCILED_VALIDATION_DEBIT=4
EFFECTIVE_CONSUMED=4
REMAINING=28
BUDGET_DELTA=0
TEST_REMAINS_SEALED=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The prior values and manifest remain available in the repository history and
are explicitly superseded by this correction. The corrected four run values
are not an execution authorization and no STARTED event or validation score
was created.
