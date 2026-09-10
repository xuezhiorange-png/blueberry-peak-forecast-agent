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

The C04 derivation function accepts only the TRAIN tuple. It partitions the
ordered TRAIN dates into four expanding chronological folds. For each fold it
fits the same historical base model on earlier TRAIN dates, predicts later
TRAIN target rows at exactly 7, 14, and 21 days after the fit cutoff, and
computes `actual_harvest_quantity_kg / base_prediction` for each comparable
row. The fold value is the median of those ratios. No VALIDATION outcome, TEST
byte, weather, production-plan input, Task8, or Task9 output enters the
derivation.

Observed fold values:

```text
FOLD_1=416.621234
FOLD_2=24.896716
FOLD_3=11.302801
FOLD_4=3.911976
```

They are four unique positive finite Decimal values and replay deterministically
from the same TRAIN identity. The parameter is explicitly:

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
corrected manifest is bound to implementation commit
`b2def154e9851d90353b24ce8dddd16467e19539`:

```text
C04_PARAMETER_MANIFEST_HASH=9cf648dfae3aab5f291503ad8ddf3979c2ad452f082c0ec2c7ff10f3a9f04c17
RUN_1_PARAMETER_MANIFEST_HASH=1af87375617e3336f289827f730c696011bbc95788c6b03bbf46e0decf7320f9
RUN_2_PARAMETER_MANIFEST_HASH=9d1b76216ac1633d9d1ce17710935fa7ce20c7e5f35263ce0db5a4c5165a595a
RUN_3_PARAMETER_MANIFEST_HASH=85d381af339f897a36a30c18685c943fc22666113655fc3abe3338664da2364e
RUN_4_PARAMETER_MANIFEST_HASH=9bc83a2d4a2d3ea35c3856e9603de3bb667a79a686369c86f06944cd49f112c3
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

## R2 correction record

The R1 time-scaled-fit derivation is retained as superseded provenance, not as
the current parameter authority. R2 uses earlier-TRAIN fitting and later-TRAIN
base-model predictions at the frozen 7/14/21 horizons, followed by the median
actual-to-base-prediction ratio. The scorer path, V2 gate, and execution
boundary are unchanged.

```text
TASK_ID=V0_3_S4_C04_PARAMETER_DERIVATION_CORRECTION_R2
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
