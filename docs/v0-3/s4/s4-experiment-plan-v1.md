# V0.3 S4-A experiment plan and candidate registry

This document is the current S4-A experiment-plan freeze. It is a governance
artifact, not an experiment execution record. The machine-readable companion
at `docs/v0-3/s4/evidence/s4-a-experiment-plan-and-candidate-registry-freeze-r1.json`
contains the complete canonical plan object and its deterministic SHA-256.

## Freeze state

```text
TASK_ID=V0_3_S4_A_EXPERIMENT_PLAN_AND_CANDIDATE_REGISTRY_FREEZE_R1
BASE_MAIN_SHA=896b195d6ba31c94f34967fb84f5388199b7885b
PR581_MERGE_IN_BASE=true
EXPERIMENT_PLAN_VERSION=v0.3-experiment-plan-v1
EXPERIMENT_PLAN_HASH=275796f3e96c5807b7ed3c0e8720eaaf964942d538289905b5d91340ef4e01b9
SAME_PLAN_CANONICAL_HASH_STABLE=true
PLAN_HASH_CHANGES=true
S4_IMPLEMENTATION_STARTED=true
S4_A_EXPERIMENT_PLAN_FROZEN=true
CURRENT_EXPERIMENT_PLAN_FROZEN=true
S4_A_CANDIDATE_REGISTRY_FROZEN=true
CURRENT_CANDIDATE_REGISTRY_FROZEN=true
S4_CANDIDATE_EXPERIMENT_EXECUTED=false
```

S4 implementation has started only in the sense that this governance plan is
being frozen. No candidate has run, no model has been trained or retrained,
and no model behavior or parameter has changed.

The plan hash is computed over the `canonical_experiment_plan` object in the
companion JSON, excluding the top-level hash field itself, using UTF-8 JSON
with sorted keys, compact separators, and `ensure_ascii=false`, followed by
SHA-256. The canonical object includes the complete registry, ordering,
budget, ledger, metric/selection, TEST, pending-execution, and boundary
semantics. A semantically unchanged object has a stable hash; any plan-field
mutation changes the preimage and therefore the hash.

## Candidate registry

Exactly eight candidates are frozen, in this order. No candidate may be added,
removed, renamed, reordered, or substituted after this freeze without a new
experiment-plan version and separate authorization.

| order | candidate ID | family | hypothesis | planned runs |
| ---: | --- | --- | --- | ---: |
| 01 | `01_parameter_calibration` | `PARAMETER_CALIBRATION` | parameter calibration reduces primary metric without guardrail regression | 4 |
| 02 | `02_quantile_calibration` | `QUANTILE_CALIBRATION` | quantile calibration improves P80/P90 coverage without point metric regression | 4 |
| 03 | `03_phenology_offset` | `PARAMETER_CALIBRATION` | versioned phenology offset reduces timing error | 4 |
| 04 | `04_yield_parameter` | `PARAMETER_CALIBRATION` | versioned yield parameter calibration reduces quantity error | 4 |
| 05 | `05_marketable_rate` | `PARAMETER_CALIBRATION` | versioned marketable rate calibration reduces marketable quantity error | 4 |
| 06 | `06_weather_response` | `STRUCTURAL_MODEL_CANDIDATE` | authorized weather response features reduce residual error | 4 |
| 07 | `07_harvest_efficiency` | `PARAMETER_CALIBRATION` | versioned harvest efficiency calibration reduces peak error | 4 |
| 08 | `08_residual_feature` | `STRUCTURAL_MODEL_CANDIDATE` | authorized residual features reduce unexplained residual | 4 |

Every row has:

```text
parent_model_id=V0_2_CURRENT_MODEL
authorized_change=NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION
random_seed_policy=FIXED_AND_RECORDED_PER_RUN
selection_eligibility=REGISTERED_AND_GUARDRAIL_ELIGIBLE
```

The exact candidate hypotheses and all registry fields are canonicalized in
the companion JSON. Until a separately authorized run exists, every candidate
retains these execution sentinels; they are not completion evidence:

```text
feature_manifest=PENDING_EXECUTION
parameter_manifest=PENDING_EXECUTION
training_dataset_hash=PENDING_EXECUTION
validation_dataset_hash=PENDING_EXECUTION
code_commit_sha=PENDING_EXECUTION
dependency_lock_hash=PENDING_EXECUTION
model_artifact_hash=PENDING_EXECUTION
experiment_result=PENDING_EXECUTION
```

## Optimization order

The frozen search order is:

1. Data/business parameter calibration: candidates `01`, `03`, `04`, `05`,
   and `07`.
2. P80/P90 calibration: candidate `02`.
3. Finite structural/model changes only if calibration is insufficient:
   candidates `06` and `08`.

`06_weather_response` and `08_residual_feature` are structural candidates.
Registration does not authorize execution. No candidate execution is
authorized by this S4-A plan.

## Fair-comparison invariants

Every future candidate comparison must keep the following identical:

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

The TEST split remains sealed and cannot be used for tuning, threshold
derivation, or candidate selection.

## Validation budget

```text
MAX_VALIDATION_EVALUATIONS=32
MAX_RUNS_PER_CANDIDATE=4
PLANNED_TOTAL_RUN_COUNT=32
ACTUAL_VALIDATION_EVALUATION_COUNT=0
CURRENT_EXPERIMENT_BUDGET_EVALUATION_STATUS=NOT_EVALUATED
```

The current per-candidate reconciliation is deliberately unexecuted:

| candidate ID | planned | actual | remaining |
| --- | ---: | ---: | ---: |
| `01_parameter_calibration` | 4 | 0 | 4 |
| `02_quantile_calibration` | 4 | 0 | 4 |
| `03_phenology_offset` | 4 | 0 | 4 |
| `04_yield_parameter` | 4 | 0 | 4 |
| `05_marketable_rate` | 4 | 0 | 4 |
| `06_weather_response` | 4 | 0 | 4 |
| `07_harvest_efficiency` | 4 | 0 | 4 |
| `08_residual_feature` | 4 | 0 | 4 |

No budget PASS is inferred from zero evaluations. The allowed future budget
states are `NOT_EVALUATED`, `PASS`, `FAIL`, and `BLOCKED`.

## Validation ledger contract

```text
VALIDATION_EVALUATION_UNIT=ONE_ACTUAL_MODEL_OR_PARAMETER_EVALUATION_INVOCATION
VALIDATION_EVALUATION_ID_REUSE_ALLOWED=false
VALIDATION_LEDGER_COUNTS_ALL_STARTED_EVALUATIONS=true
VALIDATION_LEDGER_RECONCILIATION_REQUIRED=true
VALIDATION_BUDGET_FAIL_CLOSED=true
CURRENT_LEDGER_ROW_COUNT=0
```

The counted invocation types are:

```text
NORMAL_RUN
FAILED_RUN
ABORTED_RUN
CANCELLED_RUN
TIMEOUT_RUN
AUTOMATIC_RETRY
MANUAL_RETRY
OPERATOR_TRIGGERED_RERUN
DUPLICATE_INVOCATION
```

Each started invocation creates a new `evaluation_id`, including failed,
aborted, cancelled, timed-out, and retried invocations. A retry creates a new
row and references `retry_of_evaluation_id`; no existing row may be
overwritten. Only a preflight that starts no model or parameter evaluation may
be excluded, and the exclusion must have explicit evidence and a reason.

Every ledger row must contain:

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

Mechanical reconciliation is defined as:

```text
actual_run_count = COUNT(validation_ledger_rows WHERE candidate_id=<candidate>)
remaining_run_budget = planned_run_count - actual_run_count
actual_validation_evaluation_count = COUNT(all counted validation ledger rows)
```

The reconciled counts must satisfy:

```text
actual_run_count <= planned_run_count
actual_run_count <= MAX_RUNS_PER_CANDIDATE
actual_validation_evaluation_count <= MAX_VALIDATION_EVALUATIONS
```

If any limit is exceeded, the budget status is `FAIL`, no candidate is issued,
TEST access remains unauthorized, pilot approval is false, and the incumbent
is retained. Ledger row deletion, budget rewriting, and post-hoc
reclassification cannot restore PASS.

## Metric and selection contract

The plan binds to:

```text
V0_3_METRIC_CONTRACT_VERSION=v0.3-metric-contract-v1
METRIC_CONTRACT_AUTHORITY=docs/forecast-quality/s3-quality-metrics-contract.md
PRIMARY_SELECTION_METRIC=daily_wape
METRIC_CONTRACT_STATUS=FROZEN_DEFINITION_BOUND_EXECUTION_NOT_PERFORMED
```

Guardrail metric identities are:

```text
daily_mae
cumulative_absolute_error_kg
single_day_peak_quantity_absolute_error_kg_q
sustained_7day_quantity_absolute_error_kg_q
P80_COVERAGE
P90_COVERAGE
```

Group coverage requires all six existing S3 breakdown axes, a reporting floor
of 10 comparable rows, the S2 coverage ratio, and no silent exclusion:

```text
REQUIRED_BREAKDOWN_AXES=forecast_horizon_days,farm_business_key,subfarm_business_key,variety_business_key,season_business_key,model_identity
REQUIRED_BREAKDOWN_AXIS_COUNT=6
MIN_COMPARABLE_ROWS_FOR_REPORTING=10
S2_COVERAGE_RATIO_REPORTED=true
NO_SILENT_EXCLUSION=true
```

The selection contract is:

```text
SELECTION_RULE=MINIMIZE_PRIMARY_SELECTION_METRIC_SUBJECT_TO_GUARDRAILS_AND_COVERAGE
TIE_BREAK_RULE=LEXICOGRAPHIC_CANDIDATE_ID_AFTER_METRIC_ROUNDING_AND_GUARDRAIL_PASS
MULTIPLE_COMPARISON_POLICY=ADJUSTED_MULTI_CANDIDATE_COMPARISON
MULTIPLE_COMPARISON_ADJUSTMENT=HOLM_BONFERRONI_OVER_PREDECLARED_PRIMARY_METRIC_COMPARISONS
```

Metric formulas are not changed by this plan. Current unresolved prerequisites
are recorded rather than converted into a false PASS:

```text
P50_SEMANTICS=NOT_VERIFIED
P80_SEMANTICS=NOT_VERIFIED
P90_SEMANTICS=NOT_VERIFIED
S3_COMPLETE_DAILY_ROW_SET_STATUS=NOT_AVAILABLE_FROM_CURRENT_S2_BINDING
CANDIDATE_GUARDRAIL_THRESHOLDS=NOT_FROZEN_IN_S4_A
```

The S4-A plan freezes metric identities and selection mechanics; it does not
invent candidate-specific guardrail thresholds or issue metric results.

## TEST and selection boundary

```text
TEST_ACCESS_CURRENTLY_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
SELECTED_CANDIDATE_ID=NOT_ISSUED
SELECTED_CANDIDATE_COUNT=0
MODEL_APPROVED_FOR_PILOT=false
```

It is forbidden to inspect, load, score, or use TEST to derive thresholds or
select a candidate. A candidate selection, TEST authorization, and pilot
approval require later, separate governance decisions.

## Current S4-A state and hard boundaries

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
ACTUAL_VALIDATION_EVALUATION_COUNT=0
CURRENT_EXPERIMENT_BUDGET_EVALUATION_STATUS=NOT_EVALUATED
```

This freeze does not execute candidates, change model behavior, change
parameters, train or retrain models, consume validation budget, access TEST,
change metric formulas, invent thresholds, reopen S3, or release V0.3.

```text
DO_NOT_RUN_CANDIDATE_01=true
DO_NOT_RUN_CANDIDATE_02=true
DO_NOT_RUN_CANDIDATE_03=true
DO_NOT_RUN_CANDIDATE_04=true
DO_NOT_RUN_CANDIDATE_05=true
DO_NOT_RUN_CANDIDATE_06=true
DO_NOT_RUN_CANDIDATE_07=true
DO_NOT_RUN_CANDIDATE_08=true
DO_NOT_CHANGE_MODEL=true
DO_NOT_CHANGE_PARAMETERS=true
DO_NOT_TRAIN_MODEL=true
DO_NOT_RETRAIN_RESIDUAL_MODEL=true
DO_NOT_ACCESS_TEST=true
DO_NOT_UNSEAL_TEST=true
DO_NOT_CHANGE_METRIC_FORMULAS=true
DO_NOT_INVENT_THRESHOLDS=true
DO_NOT_EXPAND_CANDIDATE_REGISTRY=true
DO_NOT_CONSUME_VALIDATION_BUDGET=true
DO_NOT_REOPEN_S3=true
DO_NOT_RELEASE_V0_3=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S4_A_EXPERIMENT_PLAN_FREEZE_REVIEW
```
