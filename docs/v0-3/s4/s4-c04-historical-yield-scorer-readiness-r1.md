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

Exactly four values are derived from SOURCE-002 TRAIN at one latest legal
pseudo-cutoff. The cutoff is derived dynamically as
`max(TRAIN.harvest_business_date) - max(FORECAST_HORIZONS)`, which is
`2026-01-09` for the frozen TRAIN ending on `2026-01-30`. One base model is fit
on TRAIN rows through that cutoff. It first predicts the three target dates
`2026-01-16`, `2026-01-23`, and `2026-01-30` from group identity and date only;
only after those base-prediction identities are fixed are TRAIN target actuals
read for calibration. Each multiplier is the median of one ratio per canonical
`SEASON × FARM × SUBFARM × VARIETY` group. The four values are M7, M14, M21,
and MALL, where MALL requires the same group to have all three horizons:

```text
CALIBRATION_CUTOFF=2026-01-09
RUN_1_M7=3.802757
RUN_2_M14=4.961884
RUN_3_M21=5.182238
RUN_4_MALL=4.152099
C04_PARAMETER_VALUES=3.802757,4.961884,5.182238,4.152099
PARAMETER_VALUE_COUNT=4
VALUES_UNIQUE=true
VALUES_POSITIVE=true
VALUES_FINITE=true
DERIVATION_DETERMINISTIC=true
VALIDATION_USED_FOR_PARAMETER_DERIVATION=false
TEST_USED=false
SAME_CALIBRATION_CUTOFF_FOR_ALL_VALUES=true
GROUP_LEVEL_RATIO_USED=true
ROW_LEVEL_RATIO_MEDIAN_USED=false
TARGET_ACTUAL_USED_FOR_MODEL_FITTING=false
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
C04_PARAMETER_MANIFEST_HASH=555a8b53253c3bfce917b41ddac771f7df82e6add0f005fcd2c2b33e624be22f
C04_PARAMETER_MANIFEST_CODE_COMMIT=57932bb6f2b6ba17ad0ad4a2ef5fdd73425e6df1
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

The C04 contract tests cover TRAIN-only derivation, latest-legal-cutoff and
same-cutoff group-level ratio invariants, exact four-value uniqueness, native-
float rejection, canonical manifest and
run-hash replay, full-snapshot allowlisting, no-weather/no-plan/no-Task8/Task9
inputs, exact horizons, base replay, prediction identity change, V2 gate
binding, no STARTED event, unchanged budget, and the sealed TEST boundary.
The existing V2 S4 adapter suite was updated only to reflect the now-proven
C04 path; C01 remains forbidden and C06/C08 remain V2-ineligible.

## R2 parameter-derivation correction (superseded by R3)

The original R1 derivation used `fit_total / fit_days * holdout_days` as the
baseline. R2 then moved to earlier-TRAIN fitting and later-TRAIN base-model
predictions, but still used multiple stage cutoffs and row-level ratios. R2 is
retained as audit provenance only and is superseded by the single-cutoff,
group-level R3 derivation below.

```text
TASK_ID=V0_3_S4_C04_PARAMETER_DERIVATION_CORRECTION_R2
SUPERSEDED=true
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

The prior values and manifest remain available as superseded audit history.

## R3 final parameter-freeze correction

R3 fixes the remaining calibration-granularity error. It uses the latest legal
TRAIN pseudo-cutoff, one base model state, and one ratio per canonical group.
The base predictions are completed from target identity fields before target
actuals are read. M7, M14, and M21 are per-horizon group ratios; MALL is the
same-group ratio over the summed 7/14/21 actuals and predictions, excluding any
group missing a horizon. No row-level median, partial-group aggregation, or
manual uniqueness perturbation is allowed.

```text
TASK_ID=V0_3_S4_C04_PARAMETER_FREEZE_FINAL_CORRECTION_R3
TARGET_PR=598
SUPERSEDES_R2=true
OLD_R2_VALUES_SUPERSEDED=true
OLD_R2_VALUES_NOT_FROZEN=true
C04_PARAMETER_DERIVATION_POLICY=TRAIN_ONLY_LATEST_LEGAL_PSEUDO_CUTOFF_GROUP_HORIZON_AMPLITUDE_CALIBRATION_V3
TRAIN_END=2026-01-30
C04_CALIBRATION_CUTOFF=2026-01-09
CALIBRATION_TARGET_DATES=2026-01-16,2026-01-23,2026-01-30
C04_M7=3.802757
C04_M14=4.961884
C04_M21=5.182238
C04_MALL=4.152099
C04_PARAMETER_VALUES=3.802757,4.961884,5.182238,4.152099
C04_PARAMETER_VALUE_COUNT=4
SAME_CALIBRATION_CUTOFF_FOR_ALL_VALUES=true
SAME_MODEL_STATE_FOR_ALL_VALUES=true
GROUP_LEVEL_RATIO_USED=true
ROW_LEVEL_RATIO_MEDIAN_USED=false
TARGET_ACTUAL_USED_FOR_MODEL_FITTING=false
VALIDATION_USED_FOR_PARAMETER_DERIVATION=false
TEST_USED=false
C04_PARAMETER_MANIFEST_HASH=555a8b53253c3bfce917b41ddac771f7df82e6add0f005fcd2c2b33e624be22f
C04_PARAMETER_MANIFEST_CODE_COMMIT=57932bb6f2b6ba17ad0ad4a2ef5fdd73425e6df1
VALIDATION_EXECUTION=false
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
FINAL_STOP_GATE=COORDINATOR_PR598_C04_PARAMETER_FREEZE_FINAL_REVIEW
```

R3 changes only parameter derivation. The scorer path, V2 gate, SOURCE-002
authority, budget persistence, and TEST boundary remain unchanged.
