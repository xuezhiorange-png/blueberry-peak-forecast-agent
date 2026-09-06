# V0.3-S3 Farm-total Baseline Validation Scoring Authorization (R1)

> Scope: docs-only scoring contract freeze + authorization issuance — no Python, no scoring execution
> Task: `V0_3_S3_FARM_TOTAL_BASELINE_VALIDATION_SCORING_CONTRACT_AND_AUTHORIZATION_R1`
> Task class: `DOCS_ONLY_SCORING_CONTRACT_AND_AUTHORIZATION`
> Parent live execution: PR #568 merge `80298b85c4250f1e0c8a6660c2eeb8f670d4f1eb`

## Machine-readable header

```text
ARTIFACT_ID=V0_3_S3_FARM_TOTAL_BASELINE_VALIDATION_SCORING_AUTHORIZATION
ARTIFACT_VERSION=R1

TASK_ID=V0_3_S3_FARM_TOTAL_BASELINE_VALIDATION_SCORING_CONTRACT_AND_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_SCORING_CONTRACT_AND_AUTHORIZATION

BASE_MAIN_SHA=80298b85c4250f1e0c8a6660c2eeb8f670d4f1eb

PARENT_LIVE_EXECUTION_PR=568
PARENT_LIVE_EXECUTION_MERGE_SHA=80298b85c4250f1e0c8a6660c2eeb8f670d4f1eb
PARENT_BASELINE_EVALUATION_PACKAGE_SHA256=f1098fd3ff2559bda9ff311788496bdbbcb6000c335743f2028ffe558e291c37

USER_GATE=可以

V0_3_S3_FARM_TOTAL_BASELINE_VALIDATION_SCORING_CONTRACT_AUTHORIZED=true
V0_3_S3_FARM_TOTAL_BASELINE_VALIDATION_SCORING_AUTHORIZED=true

FARM_TOTAL_BASELINE_METRIC_EXECUTION_AUTHORIZED=true
FUTURE_SCORING_IMPLEMENTATION_AUTHORIZED=true
FUTURE_LIVE_SCORING_RUNNER_IMPLEMENTATION_AUTHORIZED=true
OFFICIAL_VALIDATION_ACTUAL_USE_FOR_SCORING_AUTHORIZED=true
LIVE_SCORING_REPLAY_AUTHORIZED=true
LIVE_SCORING_EVIDENCE_AUTHORIZED=true

SCORING_EXECUTION_REQUIRES_SEPARATE_USER_GATE=可以执行评分

LIVE_SCORING_PERFORMED=false
VALIDATION_BASELINE_SCORED=false

VALIDATION_ACTUAL_FINITE_DECIMAL_REQUIRED=true
VALIDATION_ACTUAL_NONNEGATIVE_PRECONDITION_REQUIRED=true
NEGATIVE_VALIDATION_ACTUAL_BLOCKER=NEGATIVE_VALIDATION_ACTUAL
NEGATIVE_VALIDATION_ACTUAL_ACTION=STRUCTURAL_FAIL_CLOSED
NEGATIVE_VALIDATION_ACTUAL_IS_NOT_ZERO=true
UPSTREAM_NONNEGATIVE_GUARANTEE_CLAIMED=false

FARM_TOTAL_BASELINE_MAE_AUTHORIZED=true
FARM_TOTAL_BASELINE_WAPE_AUTHORIZED=true
FARM_TOTAL_BASELINE_SMAPE_AUTHORIZED=true
FARM_TOTAL_BASELINE_MAPE_AUTHORIZED=false
FARM_TOTAL_BASELINE_BIAS_AUTHORIZED=false
FARM_TOTAL_BASELINE_COVERAGE_AUTHORIZED=false

BASELINE_VS_INCUMBENT_COMPARISON_AUTHORIZED=false
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false

TEST_EVALUATION_ACCESS=false
TEST_REMAINS_SEALED=true

MODEL_CHANGE=false
PARAMETER_CHANGE=false
MIGRATION_CHANGE=false
SCHEMA_CHANGE=false
V0_3_S4_AUTHORIZED=false

READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The user gate `可以` authorizes issuance of this **scoring contract and grant**
only. Actual VALIDATION scoring execution requires a separate explicit user gate
`可以执行评分`.

```text
VALIDATION_SCORING_AUTHORIZED=true
≠
VALIDATION_BASELINE_SCORED=true

FARM_TOTAL_BASELINE_METRIC_EXECUTION_AUTHORIZED=true
≠
S3_METRIC_EXECUTION_AUTHORIZED=true

VALIDATION_SCORING_AUTHORIZED=true
≠
BASELINE_VS_INCUMBENT_COMPARISON_AUTHORIZED=true

VALIDATION_SCORING_AUTHORIZED=true
≠
TEST_EVALUATION_ACCESS=true
```

## 1. Accepted parent state

Parent live execution evidence:
`docs/v0-3/s3/evidence/s3-farm-total-baseline-live-execution-r1.json`

```text
CURRENT_MAIN_SHA=80298b85c4250f1e0c8a6660c2eeb8f670d4f1eb
LIVE_BASELINE_EXECUTION_PERFORMED=true
VALIDATION_BASELINE_MATERIALIZED=true
LIVE_REPLAY_STATUS=PASS
VALIDATION_BASELINE_SCORED=false
TEST_REMAINS_SEALED=true

SOURCE_002_DATASET_ID=source-002
SOURCE_002_DATASET_VERSION=e5-live-v1
SOURCE_002_MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785

OFFICIAL_TRAIN_CONTENT_SHA256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
OFFICIAL_VALIDATION_CONTENT_SHA256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06

TRAIN_FARM_TOTAL_DATASET_SHA256=08aa2116d700ce00531943fcb00e7ed9b9353ed7821012359838ec027ef7a0e1
VALIDATION_FARM_TOTAL_DATASET_SHA256=351a401fccfeb42758401583ee88a86fb85e9917ca5f3997c62ac3b36f81cac0

ESTIMATOR_STATE_SHA256=daf4a0565d910ef0da70f3de1adcbf6507b60c2c77c784d4c2412a416da755c3
TARGET_IDENTITY_SET_SHA256=9f268fa082e4dc6e1c83ed47fc32a4b6b202f07e38773d9b5a5967c0c9bfe427
BASELINE_POINT_SET_SHA256=5869bbde1c3717c2ee5469976a6cea368c4e5c538063b893c383f244aeaee0a5
TARGET_OUTCOME_SET_SHA256=169033291c46884c587275888b1e6fb83e740b240a74c5a063c4b36291f64d94
PREDICTION_IDENTITY_SHA256=2608b407dc00361cf2cd73e8469ce569591cdb6eacc033e16578d7e1561dbf44
PACKAGE_SHA256=f1098fd3ff2559bda9ff311788496bdbbcb6000c335743f2028ffe558e291c37

TARGET_COUNT=1033
EMITTED_POINT_COUNT=1033
BLOCKED_TARGET_COUNT=0
READY_TARGET_COUNT=1033
```

```text
OWNER_DECISION_SHA256=39722ff8e8a520813975cd7270b6453db388633bffee9c90fb12140440431463
```

## 2. Authorization scope

```text
AUTHORIZATION_SCOPE=V0_3_S3_FARM_TOTAL_BASELINE_VALIDATION_SCORING_ONLY
```

This authorization is local to the Farm-total deterministic baseline VALIDATION
scoring path. It MUST NOT authorize:

- S3-C incumbent PIT backtest execution
- global S3 metric execution
- baseline-vs-incumbent comparison
- TEST evaluation or scoring
- S4
- model changes
- parameter changes
- complete-rowset peak/cumulative metrics
- baseline quantile scoring

## 3. Scoring input authority

Future scoring MUST consume the existing production objects:

- `FarmTotalBaselineEvaluationPackage`
- the exact `FarmTotalValidationDataset` used to build that package

Future public API authorized in principle:

```python
score_farm_total_baseline_validation(
    *,
    evaluation_package: FarmTotalBaselineEvaluationPackage,
    validation_dataset: FarmTotalValidationDataset,
) -> FarmTotalBaselineValidationScorePackage
```

Exact naming may be frozen by the implementation contract, but semantics must be
equivalent.

The scorer MUST NOT:

- rebuild the baseline estimator
- recalculate TRAIN medians independently
- reproject baseline points independently
- load a different validation dataset
- discover actuals from another source
- perform a DB join
- read TEST
- load incumbent forecasts

## 4. Dataset binding

Scoring MUST fail closed unless:

- `validation_dataset.partition_dataset.dataset_sha256`
  equals `evaluation_package.validation_dataset_sha256`
- the validation target identity set exactly corresponds to the package target
  identity set

Required target identity:

```text
(season_business_key, baseline_farm_group_key, harvest_business_date)
```

Forbidden association modes:

- positional zip
- row-order association
- "latest" fallback
- target-date-only association
- source farm-level association
- area-based association

## 5. Scoring grain

```text
SCORING_TARGET_GRAIN=SEASON_X_BASELINE_FARM_GROUP_X_HARVEST_BUSINESS_DATE
SCORING_RESULT_GRAIN=ONE_RESULT_PACKAGE_PER_FARM_TOTAL_VALIDATION_EVALUATION_PACKAGE
```

R1 does NOT authorize:

- per-farm-group score publication
- per-day score publication
- per-target error publication
- per-source-farm score publication

## 6. READY target policy

A target is numeric-score eligible only when the existing evaluation package
marks it READY and there is exactly:

1. one canonical baseline point
2. one canonical VALIDATION actual
3. one exact target-key match

```text
COMPARABLE_TARGET =
  READY
  AND EXACT_BASELINE_POINT_PRESENT
  AND EXACT_VALIDATION_ACTUAL_PRESENT
```

Do not silently drop a READY target.

If a READY target lacks its point or its matching actual:

```text
STRUCTURAL_FAIL_CLOSED=true
```

Do not convert it into an ordinary blocked target.

## 7. Blocked target policy

Existing package outcomes remain authoritative.

Known non-ready classes include:

- `INSUFFICIENT_TRAIN_SUPPORT`
- `UNSEEN_GROUP`

These targets:

- MUST remain in `TARGET_COUNT`
- MUST remain in diagnostic counters
- MUST NOT enter numeric metric arithmetic
- MUST NOT be treated as zero baseline
- MUST NOT be treated as zero actual
- MUST NOT be silently omitted from evidence counters

Closure rule:

```text
TARGET_COUNT = COMPARABLE_TARGET_COUNT + BLOCKED_TARGET_COUNT
```

For a valid score package:

```text
COMPARABLE_TARGET_COUNT = READY_TARGET_COUNT
```

Any mismatch is fail closed.

Current parent state:

```text
TARGET_COUNT=1033
READY_TARGET_COUNT=1033
BLOCKED_TARGET_COUNT=0
```

The implementation contract must support future non-zero blocker counts.

## 8. Missing actual policy

```text
MISSING_DAY_POLICY=UNKNOWN_NOT_ZERO
MISSING_ACTUAL_TREATED_AS_ZERO=false
NUMERIC_IMPUTATION_ALLOWED=false
ZERO_FILL_AUTHORIZED=false
```

For an existing READY target, a missing actual is structural invalidity for this
scoring package, not a zero.

### Validation actual domain and scorer-local precondition

The S2/Farm-total production path does not itself establish a nonnegative
guarantee for `MaterializableRow.actual_harvest_quantity_kg`. This R1 contract
therefore freezes the validation at the scorer boundary:

```text
VALIDATION_ACTUAL_FINITE_DECIMAL_REQUIRED=true
VALIDATION_ACTUAL_NONNEGATIVE_PRECONDITION_REQUIRED=true
NEGATIVE_VALIDATION_ACTUAL_BLOCKER=NEGATIVE_VALIDATION_ACTUAL
NEGATIVE_VALIDATION_ACTUAL_ACTION=STRUCTURAL_FAIL_CLOSED
NEGATIVE_VALIDATION_ACTUAL_IS_NOT_ZERO=true
UPSTREAM_NONNEGATIVE_GUARANTEE_CLAIMED=false
```

Before any MAE/WAPE/sMAPE arithmetic, every comparable VALIDATION actual must:

1. be a finite `Decimal`
2. satisfy `actual_i >= 0`

If any comparable target has `actual_i < 0`, the complete score package must
fail closed with blocker `NEGATIVE_VALIDATION_ACTUAL`. Do not abs-transform the
negative actual, zero-fill it, silently omit it, convert it to `BLOCKED`, or
continue scoring the remaining targets.

## 9. Allowed metric family — exactly three

| Metric | Authorized |
| --- | --- |
| `FARM_TOTAL_BASELINE_MAE` | true |
| `FARM_TOTAL_BASELINE_WAPE` | true |
| `FARM_TOTAL_BASELINE_SMAPE` | true |
| `FARM_TOTAL_BASELINE_MAPE` | false |
| `FARM_TOTAL_BASELINE_BIAS` | false |
| `FARM_TOTAL_BASELINE_RELATIVE_BIAS` | false |
| `FARM_TOTAL_BASELINE_COVERAGE` | false |
| `FARM_TOTAL_BASELINE_PEAK_METRIC` | false |
| `FARM_TOTAL_BASELINE_CUMULATIVE_METRIC` | false |
| `FARM_TOTAL_BASELINE_QUANTILE_METRIC` | false |
| baseline-vs-incumbent comparison | false |

## 10. Metric formulas

All numeric arithmetic:

- `Decimal` only
- native float accumulation forbidden
- `DECIMAL_QUANTUM=0.000001`
- `ROUNDING=ROUND_HALF_EVEN`

R1 scoring first requires every comparable VALIDATION actual to pass the
scorer-local finite-Decimal and nonnegative precondition. Only after that
precondition passes may MAE/WAPE/sMAPE arithmetic begin.

For each comparable target `i`:

```text
prediction_i = baseline point kg
actual_i = exact VALIDATION actual harvest kg
error_i = prediction_i - actual_i
absolute_error_i = abs(error_i)
N = comparable target count
```

### MAE

```text
MAE = sum(absolute_error_i) / N
```

`MAE` is `NOT_COMPUTABLE` when `N = 0`.

### WAPE

```text
WAPE = sum(absolute_error_i) / sum(actual_i)
```

R1 scoring first requires every comparable VALIDATION actual to pass the
scorer-local finite-Decimal and nonnegative precondition. After that
precondition passes, WAPE uses the governed actual kg values directly.

`WAPE` is `NOT_COMPUTABLE` when `sum(actual_i) = 0`. Do not substitute another
denominator.

### sMAPE term

```text
if prediction_i == 0 and actual_i == 0:
  smape_term_i = 0
else:
  smape_term_i = 2 * abs(prediction_i - actual_i) / (abs(prediction_i) + abs(actual_i))
```

### sMAPE

```text
SMAPE = sum(smape_term_i) / N
```

`sMAPE` is `NOT_COMPUTABLE` when `N = 0`.

## 11. Metric status

Each authorized metric must have explicit:

- `metric_name`
- `metric_value`
- `metric_status`
- `reason_code`
- `numerator`
- `denominator`

Do not publish an absent metric as numeric zero.

Required status family:

- `COMPUTED`
- `NOT_COMPUTABLE`

Required reasons at minimum:

- `NONE`
- `NO_COMPARABLE_TARGETS`
- `WAPE_DENOMINATOR_ZERO`

No PASS/FAIL superiority semantics. No business acceptance threshold.

## 12. Future scoring package

Freeze a future immutable package equivalent to:

- `FarmTotalBaselineValidationMetricCell`
- `FarmTotalBaselineValidationScoreDiagnostics`
- `FarmTotalBaselineValidationScorePackage`

Required score diagnostics:

- `target_count`
- `comparable_target_count`
- `blocked_target_count`
- `ready_target_count`
- `insufficient_train_support_target_count`
- `unseen_group_target_count`
- `negative_validation_actual_count`

Successful score package:

```text
NEGATIVE_VALIDATION_ACTUAL_COUNT=0
```

If `NEGATIVE_VALIDATION_ACTUAL_COUNT > 0`, the complete score package must fail
closed and no successful score package may be emitted.

Metric cells exactly: `MAE`, `WAPE`, `SMAPE`.

No MAPE. No bias. No coverage. No comparison delta.

## 13. Deterministic hash layers

Freeze at least four score identities:

| Hash | Semantics |
| --- | --- |
| `SCORING_TARGET_ACTUAL_SET_SHA256` | canonical ordered set of target identity + exact validation actual value |
| `SCORING_INPUT_SHA256` | score schema version, evaluation `PACKAGE_SHA256`, validation dataset SHA256, target/baseline/outcome identities, target-actual set hash, counters, metric policy/version |
| `METRIC_RESULT_SET_SHA256` | exact three ordered metric cells including name, value/null, status, reason, numerator/null, denominator/null |
| `SCORE_PACKAGE_SHA256` | all upstream scoring identities, score diagnostics, metric result set hash |

`SCORING_TARGET_ACTUAL_SET_SHA256` may be computed from real actual values in
memory. Repository evidence may persist the hash only, not the underlying values.

## 14. Canonicalization

Reuse:

- `backend.app.forecast_quality.canonical.canonical_json_bytes`
- existing Decimal emission/quantization helpers where semantically valid

No native float. No JSON serializer invented solely for this scorer. Ordering
must be deterministic and independent of input row order.

## 15. Publication boundary

Future scoring may compute in memory:

- real baseline point values
- real VALIDATION actual values
- real target-level errors
- real MAE numerator
- real WAPE numerator/denominator
- real sMAPE terms
- real metric values

Repository evidence MAY persist only aggregate metric values and authorized
aggregate numerators/denominators plus counts and hashes.

It MUST NOT persist:

- per-target baseline point
- per-target VALIDATION actual
- per-target error
- per-target absolute error
- full scoring pair list
- raw TRAIN rows
- raw VALIDATION rows
- TEST bytes

## 16. TEST custody

```text
TEST_EVALUATION_ACCESS=false
TEST_LABEL_ACCESS=false
TEST_TARGET_CONSTRUCTION=false
TEST_SCORING=false
TEST_PAYLOAD_RETURNED=false
TEST_REMAINS_SEALED=true
```

Existing SOURCE-002 sealed custody verification may continue. That custody
verification is not TEST evaluation.

## 17. No incumbent comparison

```text
BASELINE_VS_INCUMBENT_COMPARISON_AUTHORIZED=false
ROUND_C_COMPARISON_EXECUTION_AUTHORIZED=false
```

Do NOT authorize:

- incumbent forecast loading
- incumbent scoring
- common comparable model/baseline set
- `comparison.py` execution
- daily MAE/WAPE/sMAPE deltas
- improvement percentages
- model-better/baseline-better verdict
- superiority PASS/FAIL

## 18. S3-C and global metric boundary

```text
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false
```

`FARM_TOTAL_BASELINE_METRIC_EXECUTION_AUTHORIZED=true` does NOT imply
`S3_METRIC_EXECUTION_AUTHORIZED=true`.

## 19. Complete-rowset metrics still forbidden

Do not authorize:

- single-day peak metric
- sustained peak metric
- season cumulative metric
- complete-horizon metric

## 20. Quantile boundary

```text
BASELINE_P80_STATUS=NOT_COMPUTABLE
BASELINE_P90_STATUS=NOT_COMPUTABLE
BASELINE_OUTPUT_DISTRIBUTION_AUTHORIZED=false
BASELINE_QUANTILE_SCORING_AUTHORIZED=false
```

No interval coverage. No P80/P90 scoring. No pinball loss.

## 21. Future implementation — one large PR

After this authorization merges AND the user later provides `可以执行评分`, the
next task is authorized to combine:

```text
SCORING_IMPLEMENTATION
+ SYNTHETIC_TESTS
+ LIVE_SCORING
+ LIVE_REPLAY
+ EXECUTION_EVIDENCE
```

in ONE PR. Do not split those into micro-PRs.

## 22. Future authorized paths — exactly five

| Path | Role |
| --- | --- |
| `backend/app/forecast_quality/farm_total_baseline_validation_scoring.py` | scorer module |
| `backend/tests/forecast_quality/test_farm_total_baseline_validation_scoring.py` | synthetic tests |
| `scripts/run_v03_farm_total_baseline_validation_scoring.py` | live scoring runner |
| `docs/v0-3/s3/workpapers/s3-farm-total-baseline-validation-scoring-r1.md` | execution workpaper |
| `docs/v0-3/s3/evidence/s3-farm-total-baseline-validation-scoring-r1.json` | execution evidence |

```text
FUTURE_CHANGED_FILE_COUNT=5
FUTURE_EXISTING_FILE_MUTATION_AUTHORIZED=false
```

Do not authorize modification of:

- `farm_total_baseline_estimator.py`
- `farm_total_baseline_evaluation_package.py`
- `farm_total_data_plane.py`
- `calculator_daily.py`
- `comparison.py`
- `persistence.py`
- `schemas.py`
- `enums.py`
- migrations

## 23. Future live scoring input reconstruction

Future live runner must reconstruct the exact same accepted baseline package
through the existing governed chain:

```text
official SOURCE-002 TRAIN/VALIDATION obtain
→ reviewed authority bundle
→ materialize_farm_total_baseline_data_plane(verify_official_hashes=True)
→ build_farm_total_baseline_evaluation_package(...)
```

Require resulting:

```text
PACKAGE_SHA256=f1098fd3ff2559bda9ff311788496bdbbcb6000c335743f2028ffe558e291c37
```

for the R1 official replay target.

If parent package identity changes: fail closed. Do not score a different package
under the R1 evidence identity.

## 24. Future live replay

```text
LIVE_SCORING_REPLAY_REQUIRED=true
LIVE_SCORING_REPLAY_COUNT=2
LIVE_SCORING_REPLAY_IDENTITY_MATCH_REQUIRED=true
```

Both runs must use the same:

- runner commit
- SOURCE-002 identity
- authority packages
- baseline evaluation package identity
- validation dataset identity

Require equality at minimum:

- `PACKAGE_SHA256`
- `SCORING_TARGET_ACTUAL_SET_SHA256`
- `SCORING_INPUT_SHA256`
- `METRIC_RESULT_SET_SHA256`
- `SCORE_PACKAGE_SHA256`
- `TARGET_COUNT`
- `COMPARABLE_TARGET_COUNT`
- `BLOCKED_TARGET_COUNT`
- `READY_TARGET_COUNT`
- `INSUFFICIENT_TRAIN_SUPPORT_TARGET_COUNT`
- `UNSEEN_GROUP_TARGET_COUNT`
- `NEGATIVE_VALIDATION_ACTUAL_COUNT`
- MAE metric value/status/reason
- WAPE metric value/status/reason
- SMAPE metric value/status/reason

Any mismatch:

```text
LIVE_SCORING_STATUS=BLOCKED
LIVE_SCORING_REPLAY_STATUS=FAIL
```

No PASS evidence.

## 25. Future test requirements

MINIMUM_TEST_THEMES=35

Minimum test themes (35):

1. exact package/validation dataset hash binding
2. row-order invariance
3. exact target-key pairing
4. duplicate validation target fail closed
5. missing READY actual fail closed
6. negative_validation_actual_fail_closed
7. missing READY baseline point fail closed
8. blocked targets excluded from arithmetic but retained in counters
9. target count closure
10. comparable count equals READY count
11. MAE hand-computed example
12. WAPE hand-computed example
13. sMAPE hand-computed example
14. sMAPE zero/zero term equals zero
15. zero comparable targets => metrics NOT_COMPUTABLE
16. WAPE zero denominator => WAPE NOT_COMPUTABLE
17. Decimal-only arithmetic
18. native float rejected/not used
19. deterministic target-actual-set hash
20. deterministic scoring-input hash
21. deterministic metric-result-set hash
22. deterministic score-package hash
23. validation actual perturbation changes scoring hashes/results
24. baseline point perturbation changes scoring hashes/results
25. TRAIN-only unrelated mutation cannot directly alter validation target actual set identity
26. no per-target values serialized into repository evidence payload
27. no TEST access
28. no incumbent import/use
29. no comparison result fields
30. no MAPE
31. no bias
32. no coverage
33. no P80/P90
34. no peak/cumulative metrics
35. fail-closed behavior deterministic

Required negative-actual behavior: one negative comparable VALIDATION actual must
cause structural fail closed, emit no successful metric package, and must not be
abs-transformed, silently omitted, or zero-filled.

## 26. Future execution evidence fields

Future live evidence must include at minimum:

`EXECUTION_MAIN_SHA`, `SCORING_RUNNER_COMMIT_SHA`, SOURCE-002 identities,
authority hashes, baseline evaluation package hashes, scoring hash layers,
target/comparable/blocked counters, MAE/WAPE/SMAPE value/status/reason,
`NEGATIVE_VALIDATION_ACTUAL_COUNT`, `LIVE_SCORING_REPLAY_COUNT`,
`LIVE_SCORING_REPLAY_STATUS`, `TEST_REMAINS_SEALED`,
`VALIDATION_BASELINE_SCORED=true`.

Successful official scoring requires:

```text
NEGATIVE_VALIDATION_ACTUAL_COUNT=0
```

If `NEGATIVE_VALIDATION_ACTUAL_COUNT > 0`, no successful score package or PASS
execution evidence may be emitted.

No per-target values.

## 27. Prohibitions — this PR

```text
SCORING_IMPLEMENTATION_IN_THIS_PR=false
SCORING_EXECUTION_IN_THIS_PR=false
OFFICIAL_VALIDATION_ACTUAL_READ_IN_THIS_PR=false
LIVE_DB_CONNECTION_IN_THIS_PR=false
METRIC_VALUE_COMPUTATION_IN_THIS_PR=false
TEST_ACCESS_IN_THIS_PR=false
INCUMBENT_FORECAST_ACCESS_IN_THIS_PR=false
COMPARISON_EXECUTION_IN_THIS_PR=false
S3_C_EXECUTION_IN_THIS_PR=false
S4_AUTHORIZATION_IN_THIS_PR=false
```
