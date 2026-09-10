# Workpaper — C04 historical-only yield scorer readiness R1

```text
TASK_ID=V0_3_S4_C04_HISTORICAL_YIELD_SCORER_READINESS_R1
TASK_CLASS=MODEL_IMPLEMENTATION_AND_MANIFEST_FREEZE
BASE_MAIN_SHA=754386d1ae90a322dd2334793936143bab97eb0a
```

## Authority and data boundary

The corrected V2 plan is the current execution identity:

```text
EXPERIMENT_PLAN_VERSION=v0.3-experiment-plan-v2
EXPERIMENT_PLAN_HASH=c2bfab4ec38b4ca640f62d061494961c5b49afe5b52fa675326aa80fdf5f8ad9
GUARDRAIL_POLICY_VERSION=v0.3-s4-guardrail-policy-v2
GUARDRAIL_POLICY_HASH=65ad056b3085b7ff41d25e1a7a86b990ac0f837270d62f6fd84ce5938843c793
SOURCE_002_TRAIN_ROWS=16224
SOURCE_002_TRAIN_SHA256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
SOURCE_002_VALIDATION_ROWS=8006
SOURCE_002_VALIDATION_SHA256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
FORECAST_HORIZONS=7,14,21
TEST_REMAINS_SEALED=true
```

The C04 derivation function accepts only the TRAIN tuple. It derives one
latest legal pseudo-cutoff dynamically as the maximum TRAIN date minus the
maximum frozen horizon: `2026-01-30 - 21 days = 2026-01-09`. One base model is
fit on rows through that cutoff. It first predicts the three target dates
`2026-01-16`, `2026-01-23`, and `2026-01-30` using only group identity and
date; only then are TRAIN target actuals read. For each horizon, the ratio is
aggregated per `SEASON × FARM × SUBFARM × VARIETY` group before taking the
median. MALL uses only groups with all 7/14/21 horizons and sums actuals and
predictions within the same group. No VALIDATION outcome, TEST byte, weather,
production-plan input, Task8, or Task9 output enters the derivation.

Observed fold values:

```text
CALIBRATION_CUTOFF=2026-01-09
M7=3.802757
M14=4.961884
M21=5.182238
MALL=4.152099
C04_PARAMETER_VALUES=3.802757,4.961884,5.182238,4.152099
```

They are four unique positive finite Decimal values and replay deterministically
from the same TRAIN identity and model state. The parameter is explicitly:

```text
C04_PARAMETER_SEMANTIC=TRAIN_DERIVED_POINT_FORECAST_YIELD_AMPLITUDE_MULTIPLIER
C04_PARAMETER_UNIT=RATIO
C04_PARAMETER_PATH=yield_amplitude_multiplier
BASELINE_MULTIPLIER=1.0
```

## Prediction-path proof

The scorer is separate from the historical C01 local replay. It uses
`fit_shared_curve` for the TRAIN-derived curve and applies the candidate value
at the quantity-amplitude boundary:

```text
base_prediction_total = TRAIN-derived group total or deterministic variety fallback
base_p50 = base_prediction_total * curve_share
candidate_prediction_total = base_prediction_total * multiplier
candidate_p50 = candidate_prediction_total * curve_share
```

The candidate predictor returns no target actual value. With multiplier `1.0`,
the candidate P50 equals base P50 after the repository's Decimal quantization.
With a distinct positive multiplier, the canonical prediction payload changes;
the contract tests observed three changed synthetic target predictions and
different prediction identities. This proves both that the parameter reaches
prediction math and that changing it can change the prediction.

## Manifest and allowlist

The manifest stores a Decimal-normalized full incumbent configuration snapshot,
one candidate snapshot per run, the authorized delta, candidate-config hash,
run-level parameter-manifest hash, code commit binding, and all V2/source
identities. The only allowed candidate-level path is:

```text
ALLOWED_PARAMETER_PATHS=yield_amplitude_multiplier
UNAUTHORIZED_PARAMETER_DIFF_COUNT_PER_RUN=0
```

Mutating a curve, pooling, offset, or forecast field, or changing two fields,
is rejected. The current incumbent file remains untouched and is bound by:

```text
INCUMBENT_CONFIG_FILE_SHA256=fc023976a228c36556ed5f7ababe722a3dd8a558ed11e0473eb415b52dd69ace
INCUMBENT_CONFIG_HASH=3571477d5822f57cd2c424620915560e22481f48983b397a1f1b8934e1a7612c
```

The manifest and run hashes are deterministic under canonical JSON rules. The
R3 corrected manifest is bound to implementation commit
`57932bb6f2b6ba17ad0ad4a2ef5fdd73425e6df1`:

```text
C04_PARAMETER_MANIFEST_HASH=555a8b53253c3bfce917b41ddac771f7df82e6add0f005fcd2c2b33e624be22f
RUN_1_PARAMETER_MANIFEST_HASH=4ec3b36876b6394ef72596e1d52fd941023ca350aa8f5d51831f16b5ae770310
RUN_2_PARAMETER_MANIFEST_HASH=a222b793cf91f2a212e9cb2b905d8e737e8152a192a9e403951de05c73d86bbf
RUN_3_PARAMETER_MANIFEST_HASH=633be3689dca6af97e2b52ff44cf2bef6f3d81f085ae7136aeca205791afc7d3
RUN_4_PARAMETER_MANIFEST_HASH=cb6d816a18ffd732fb2dee7df7fb3b1aa4c7fd312be489dffbd049b595c2569d
```

## Guardrail and budget disposition

The V2 authority has 688 sparse target rows at offsets 7/14/21. Point metrics
can be computed by a future authorized scorer, but the current data does not
prove the continuous daily rowset required by cumulative, peak, and sustained
guardrails. The existing policy is not weakened:

```text
C04_FUTURE_EXECUTION_PRIMARY_METRIC_COMPUTABLE=true
C04_FUTURE_EXECUTION_FULL_GUARDRAIL_COMPUTABLE=false
C04_FUTURE_EXECUTION_GUARDRAIL_BLOCKER=COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE
MISSING_DAY_ZERO_FILL=false
```

This task only establishes a lawful scorer path. It does not issue a metric
result, select a run, or authorize execution. The durable budget remains:

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
```

The V2 compatibility audit now reports:

```text
C04_HISTORICAL_ONLY_SCORING_PATH_EXISTS=true
C04_PARAMETER_REACHES_PREDICTION_MATH=true
C04_PARAMETER_CHANGE_CAN_CHANGE_PREDICTION=true
NEXT_EXECUTABLE_CANDIDATE=04_yield_parameter
```

“Executable” here means the first candidate with a real historical-only scorer
path for a separately authorized future run. No C04 execution occurred in this
workpaper's task.

## R2 correction record (superseded by R3)

The R1 time-scaled-fit derivation is retained as superseded provenance, not as
the current parameter authority. R2 uses earlier-TRAIN fitting and later-TRAIN
base-model predictions at the frozen 7/14/21 horizons, followed by the median
actual-to-base-prediction ratio. The scorer path, V2 gate, and execution
boundary are unchanged.

```text
TASK_ID=V0_3_S4_C04_PARAMETER_DERIVATION_CORRECTION_R2
SUPERSEDED=true
FIX=C04_PARAMETER_DERIVATION
OLD_ALGORITHM=FIT_TOTAL_DIVIDED_BY_FIT_DAYS_TIMES_HOLDOUT_DAYS
NEW_ALGORITHM=EARLIER_TRAIN_FIT_SAME_BASE_MODEL_PREDICTS_LATER_TRAIN_7_14_21_ACTUAL_OVER_BASE_PREDICTION_MEDIAN
C04_PARAMETER_DERIVATION_POLICY=TRAIN_ONLY_CHRONOLOGICAL_INNER_FOLDS_BASE_MODEL_HORIZON_RATIO_MEDIAN_V2
C04_PARAMETER_VALUES=416.621234,24.896716,11.302801,3.911976
C04_PARAMETER_MANIFEST_HASH=9cf648dfae3aab5f291503ad8ddf3979c2ad452f082c0ec2c7ff10f3a9f04c17
VALIDATION_USED_FOR_PARAMETER_DERIVATION=false
TEST_USED=false
VALIDATION_EXECUTION=false
BUDGET_DELTA=0
```

## R3 final parameter-freeze correction

R3 replaces the R2 row-level, multi-stage-cutoff derivation. All four values
now use the same latest legal TRAIN pseudo-cutoff and the same model state.
Base predictions are materialized before target actuals are read, and each
ratio is formed at canonical group grain. The fourth value requires a complete
7/14/21 horizon set for the same group.

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
