# S4-A experiment-plan freeze workpaper

## Decision boundary

This workpaper records the S4-A governance freeze on main
`896b195d6ba31c94f34967fb84f5388199b7885b`, which contains the accepted PR
#581 S3 closeout. It freezes the experiment protocol before any candidate is
executed. It does not train, retrain, score, tune, access TEST, change model
behavior, change parameters, or consume validation budget.

The authoritative machine-readable record is:

`docs/v0-3/s4/evidence/s4-a-experiment-plan-and-candidate-registry-freeze-r1.json`

The complete plan object in that record is canonicalized independently of JSON
whitespace or member order. Its SHA-256 is recorded in both documents after
the canonical plan object is finalized.

```text
TASK_ID=V0_3_S4_A_EXPERIMENT_PLAN_AND_CANDIDATE_REGISTRY_FREEZE_R1
BASE_MAIN_SHA=896b195d6ba31c94f34967fb84f5388199b7885b
PR581_MERGE_IN_BASE=true
CURRENT_V0_3_S3_COMPLETE=true
V0_3_S4_AUTHORIZED=true
S3_C_HISTORICAL_PIT_STATUS=NOT_COMPUTABLE
S3_HISTORICAL_EVALUATION_TERMINAL=true
PROSPECTIVE_FORECAST_AUTHORITY_CAPTURE_VERIFIED=true
FUTURE_LEGAL_PIT_REPLAY_SUPPORTED=true
TEST_REMAINS_SEALED=true
```

## Frozen plan identity

```text
EXPERIMENT_PLAN_VERSION=v0.3-experiment-plan-v1
OLD_EXPERIMENT_PLAN_HASH=275796f3e96c5807b7ed3c0e8720eaaf964942d538289905b5d91340ef4e01b9
OLD_EXPERIMENT_PLAN_HASH_INVALIDATED_BY_CORRECTION=true
EXPERIMENT_PLAN_HASH=9e223a02a1b38c028c230a45eb1fa8323f3c2247bb85e7b439f3351e51042500
NEW_EXPERIMENT_PLAN_HASH=9e223a02a1b38c028c230a45eb1fa8323f3c2247bb85e7b439f3351e51042500
HASH_REPLAY=PASS
CORRECTED_PLAN_FIELD_MUTATION_CHANGES_HASH=true
CANONICAL_HASH_ALGORITHM=SHA-256
CANONICAL_HASH_ENCODING=UTF-8
CANONICAL_JSON_SORT_KEYS=true
CANONICAL_JSON_COMPACT_SEPARATORS=true
CANONICAL_JSON_ENSURE_ASCII=false
SAME_PLAN_CANONICAL_HASH_STABLE=true
PLAN_HASH_CHANGES=true
```

The hash preimage is the complete `canonical_experiment_plan` object, not a
partial candidate list. It includes the registry and order, hypotheses,
optimization sequence, fair-comparison invariants, budget and per-candidate
counts, ledger and retry rules, reconciliation consequences, metric and
selection contract, unresolved prerequisites, pending execution sentinels,
TEST boundary, and execution prohibitions. The hash field itself is outside
the preimage.

## Candidate registry

The registry is closed at eight candidates, in the following exact order:

| order | candidate ID | candidate family | parent | planned runs |
| ---: | --- | --- | --- | ---: |
| 01 | `01_parameter_calibration` | `PARAMETER_CALIBRATION` | `V0_2_CURRENT_MODEL` | 4 |
| 02 | `02_quantile_calibration` | `QUANTILE_CALIBRATION` | `V0_2_CURRENT_MODEL` | 4 |
| 03 | `03_phenology_offset` | `PARAMETER_CALIBRATION` | `V0_2_CURRENT_MODEL` | 4 |
| 04 | `04_yield_parameter` | `PARAMETER_CALIBRATION` | `V0_2_CURRENT_MODEL` | 4 |
| 05 | `05_marketable_rate` | `PARAMETER_CALIBRATION` | `V0_2_CURRENT_MODEL` | 4 |
| 06 | `06_weather_response` | `STRUCTURAL_MODEL_CANDIDATE` | `V0_2_CURRENT_MODEL` | 4 |
| 07 | `07_harvest_efficiency` | `PARAMETER_CALIBRATION` | `V0_2_CURRENT_MODEL` | 4 |
| 08 | `08_residual_feature` | `STRUCTURAL_MODEL_CANDIDATE` | `V0_2_CURRENT_MODEL` | 4 |

The exact hypotheses are frozen as follows:

```text
01_parameter_calibration:
  parameter_calibration_reduces_primary_metric_without_guardrail_regression
02_quantile_calibration:
  quantile_calibration_improves_p80_p90_coverage_without_point_metric_regression
03_phenology_offset:
  versioned_phenology_offset_reduces_timing_error
04_yield_parameter:
  versioned_yield_parameter_calibration_reduces_quantity_error
05_marketable_rate:
  versioned_marketable_rate_calibration_reduces_marketable_quantity_error
06_weather_response:
  authorized_weather_response_features_reduce_residual_error
07_harvest_efficiency:
  versioned_harvest_efficiency_calibration_reduces_peak_error
08_residual_feature:
  authorized_residual_features_reduce_unexplained_residual
```

For every candidate:

```text
authorized_change=NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION
random_seed_policy=FIXED_AND_RECORDED_PER_RUN
selection_eligibility=REGISTERED_AND_GUARDRAIL_ELIGIBLE
feature_manifest=PENDING_EXECUTION
parameter_manifest=PENDING_EXECUTION
training_dataset_hash=PENDING_EXECUTION
validation_dataset_hash=PENDING_EXECUTION
code_commit_sha=PENDING_EXECUTION
dependency_lock_hash=PENDING_EXECUTION
model_artifact_hash=PENDING_EXECUTION
experiment_result=PENDING_EXECUTION
```

`PENDING_EXECUTION` is a deliberate sentinel and is not evidence that a
candidate was run.

## Optimization and comparison protocol

The optimization order is:

1. data/business parameter calibration (`01`, `03`, `04`, `05`, `07`);
2. P80/P90 calibration (`02`);
3. finite structural/model changes only if calibration is insufficient (`06`,
   `08`).

Structural registration is not execution authorization. Candidate comparison
must keep these invariants constant:

```text
SAME_TRAIN_DATASET=true
SAME_VALIDATION_DATASET=true
SAME_TEST_DATASET=true
SAME_LABELS=true
SAME_EXCLUSION_POLICY=true
SAME_CUTOFF_POLICY=true
SAME_FORECAST_HORIZONS=true
SAME_METRICS=true
```

## Budget and ledger

```text
MAX_VALIDATION_EVALUATIONS=32
MAX_RUNS_PER_CANDIDATE=4
PLANNED_TOTAL_RUN_COUNT=32
ACTUAL_VALIDATION_EVALUATION_COUNT=0
CURRENT_EXPERIMENT_BUDGET_EVALUATION_STATUS=NOT_EVALUATED
```

Every candidate has planned `4`, actual `0`, and remaining `4`. There are no
ledger rows. Zero evaluations do not produce a budget PASS.

The unit is:

```text
VALIDATION_EVALUATION_UNIT=ONE_ACTUAL_MODEL_OR_PARAMETER_EVALUATION_INVOCATION
```

The ledger counts every started invocation, including normal, failed,
aborted, cancelled, timed-out, automatic retry, manual retry,
operator-triggered rerun, and duplicate invocation. Every retry receives a
new `evaluation_id` and references `retry_of_evaluation_id`. No existing row
may be overwritten. The required row fields are:

```text
evaluation_id
experiment_plan_version
candidate_id
candidate_run_ordinal
global_evaluation_ordinal
invocation_type
trigger_source
started_at
finished_at
execution_status
metric_result_status
dataset_hash
validation_split_hash
code_commit_sha
parameter_manifest_hash
random_seed
retry_of_evaluation_id
counted_toward_budget
budget_count_reason
```

Mechanical reconciliation is:

```text
actual_run_count=COUNT(validation_ledger_rows WHERE candidate_id=<candidate>)
remaining_run_budget=planned_run_count-actual_run_count
actual_validation_evaluation_count=COUNT(all counted validation ledger rows)
```

The required limits are `actual_run_count <= planned_run_count`,
`actual_run_count <= MAX_RUNS_PER_CANDIDATE`, and
`actual_validation_evaluation_count <= MAX_VALIDATION_EVALUATIONS`. On
exceedance, budget status is `FAIL`, no candidate is issued, TEST remains
unauthorized, pilot approval is false, and the incumbent is retained. No
post-hoc deletion, rewrite, or reclassification can restore PASS.

## Metric, guardrail, and selection contract

```text
V0_3_METRIC_CONTRACT_VERSION=v0.3-metric-contract-v1
METRIC_CONTRACT_AUTHORITY=docs/forecast-quality/s3-quality-metrics-contract.md
PRIMARY_SELECTION_METRIC=daily_wape
METRIC_CONTRACT_STATUS=PASS
S1_METRIC_CONTRACT_STATUS=PASS
S1_METRIC_CONTRACT_BLOCK_REASON=NONE
METRIC_CONTRACT_RECONCILIATION_CLASS=CANONICALLY_ACCEPTED
S1_METRIC_CONTRACT_AUTHORITY_EVIDENCE_PATH=docs/v0-3/s1/evidence/canonical-acceptance-gate-current-main-reconciliation.json
S1_MINIMUM_COVERAGE_STATUS=PASS
MINIMUM_COVERAGE_THRESHOLD_VALUE=0.900000
S1_DATA_QUALITY_THRESHOLD_STATUS=PASS
S1_ACCEPTED_THRESHOLD_POLICIES=true
S4_METRIC_EXECUTION_PERFORMED=false
S4_METRIC_RESULT_ISSUED=false
S3_HISTORICAL_METRIC_STATUS=NOT_COMPUTABLE_DUE_TO_HISTORICAL_PIT_AUTHORITY_UNAVAILABLE
```

Guardrails are the existing metric identities:

```text
daily_mae
cumulative_absolute_error_kg
single_day_peak_quantity_absolute_error_kg_q
sustained_7day_quantity_absolute_error_kg_q
P80_COVERAGE
P90_COVERAGE
```

The six required breakdown axes are
`forecast_horizon_days`, `farm_business_key`, `subfarm_business_key`,
`variety_business_key`, `season_business_key`, and `model_identity`.
`MIN_COMPARABLE_ROWS_FOR_REPORTING=10`, `S2_COVERAGE_RATIO_REPORTED=true`,
and `NO_SILENT_EXCLUSION=true` remain required.

```text
SELECTION_RULE=MINIMIZE_PRIMARY_SELECTION_METRIC_SUBJECT_TO_GUARDRAILS_AND_COVERAGE
TIE_BREAK_RULE=LEXICOGRAPHIC_CANDIDATE_ID_AFTER_METRIC_ROUNDING_AND_GUARDRAIL_PASS
MULTIPLE_COMPARISON_POLICY=ADJUSTED_MULTI_CANDIDATE_COMPARISON
MULTIPLE_COMPARISON_ADJUSTMENT=HOLM_BONFERRONI_OVER_PREDECLARED_PRIMARY_METRIC_COMPARISONS
```

This plan changes no formulas. Current authority reconciliation binds to the
accepted S3-B R2 verified-claim evidence and the accepted S1 current-main
metric/threshold reconciliation:

```text
CURRENT_P50_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE
CURRENT_P80_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE
CURRENT_P90_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE
CURRENT_P50_SEMANTICS_VERIFIED=true
CURRENT_P80_SEMANTICS_VERIFIED=true
CURRENT_P90_SEMANTICS_VERIFIED=true
ALL_QUANTILE_SEMANTICS_VERIFIED=true
S3_B_VERIFIED_CLAIM_R2_EVIDENCE_PATH=docs/v0-3/s3/evidence/s3-b-quantile-semantics-verified-claim-r2.json
S3_B_VERIFIED_CLAIM_R2_EVIDENCE_FILE_SHA256=bebc33d6e48be4786267b61bbb8ff605c4f4d6b9cd0204d869da2fba7678f74b
S1_METRIC_CONTRACT_STATUS=PASS
S1_METRIC_CONTRACT_BLOCK_REASON=NONE
METRIC_CONTRACT_RECONCILIATION_CLASS=CANONICALLY_ACCEPTED
S1_METRIC_CONTRACT_AUTHORITY_EVIDENCE_FILE_SHA256=396ab86aa8a768c37171fda7d34bb745afdc0918c31addf774a0577c544e581f
S1_ACCEPTED_THRESHOLD_POLICIES=true
MINIMUM_COVERAGE_THRESHOLD_VALUE=0.900000
S1_MINIMUM_COVERAGE_STATUS=PASS
S1_DATA_QUALITY_THRESHOLD_STATUS=PASS
CANDIDATE_GUARDRAIL_THRESHOLDS=NOT_FROZEN_IN_S4_A
S4_CANDIDATE_GUARDRAIL_THRESHOLDS_FROZEN=false
STALE_S3_ROWSET_SNAPSHOT_USED_AS_CURRENT_S4_BLOCKER=false
CURRENT_S4_ROWSET_PREREQUISITE=NOT_ESTABLISHED_AS_S4_PREREQUISITE_BY_POST_S3_CLOSEOUT_AUTHORITY
UNRESOLVED_METRIC_OR_THRESHOLD_PREREQUISITES=CANDIDATE_GUARDRAIL_THRESHOLDS=NOT_FROZEN_IN_S4_A
```

Historical failed S3-B R1 artifacts and the historical rowset snapshot remain
unchanged. The rowset snapshot is not a current S4 blocker because no
post-S3-closeout authority establishes it as an S4-A prerequisite. The plan
accepts metric definitions and threshold policies from current S1 authority,
but does not execute metrics or issue results; candidate-specific guardrail
thresholds remain unfrozen.

## TEST and selection boundary

```text
TEST_ACCESS_CURRENTLY_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
SELECTED_CANDIDATE_ID=NOT_ISSUED
SELECTED_CANDIDATE_COUNT=0
MODEL_APPROVED_FOR_PILOT=false
```

TEST cannot be inspected, loaded, scored, used for threshold derivation, or
used for candidate selection under this freeze.

## Current state and prohibited actions

```text
S4_IMPLEMENTATION_STARTED=true
S4_A_EXPERIMENT_PLAN_FROZEN=true
CURRENT_EXPERIMENT_PLAN_FROZEN=true
S4_A_CANDIDATE_REGISTRY_FROZEN=true
CURRENT_CANDIDATE_REGISTRY_FROZEN=true
S4_CANDIDATE_EXPERIMENT_EXECUTED=false
S4_MODEL_CHANGE_AUTHORIZED=false
S4_PARAMETER_CHANGE_AUTHORIZED=false
S4_ALLOWLIST_EXPANSION_AUTHORIZED=false
DO_NOT_TRAIN_MODEL=true
DO_NOT_RETRAIN_RESIDUAL_MODEL=true
DO_NOT_CHANGE_METRIC_FORMULAS=true
DO_NOT_INVENT_THRESHOLDS=true
DO_NOT_CONSUME_VALIDATION_BUDGET=true
DO_NOT_REOPEN_S3=true
DO_NOT_RELEASE_V0_3=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S4_A_EXPERIMENT_PLAN_FREEZE_REVIEW
```
