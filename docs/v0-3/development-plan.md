# Blueberry Peak Forecast Agent V0.3 Development Plan

## 1. Document identity and version boundary

This document freezes the V0.3 overall development plan. It is a planning and
governance artifact only. It does not implement V0.3-S1, import real business
data, train or change a model, modify production code, create a migration, or
authorize any implementation step.

```text
VERSION=0.3.0
VERSION_NAME=BUSINESS_FORECAST_PILOT
VERSION_NAME_CN=真实业务预测验证与模型优化版
V0_3_TOTAL_SLICES=6
V0_3_RELEASE_CLASS=BUSINESS_PILOT

PRIMARY_GOAL=使用真实历史数据验证、诊断并优化现有产量预测能力，形成可持续运行、评价和迭代的业务预测闭环

MULTI_FACTORY_ROUTING_IN_SCOPE=false
FACTORY_CAPACITY_OPTIMIZATION_IN_SCOPE=false
AUTOMATIC_PRODUCTION_DISPATCH_IN_SCOPE=false
```

V0.3 is a business pilot and model-validation phase. It is not a claim that
the current model has already passed real-business accuracy validation. The
pilot must produce auditable evidence before any release or expansion claim is
made.

V0.3 does not target cross-factory routing, factory scheduling, transportation
optimization, or automatic production commands. Those subjects are explicitly
out of this version boundary even when they appear as broader product context
elsewhere in the repository.

## 2. Existing capability baseline

### 2.1 V0.1 completed baseline

V0.1 established the deterministic forecast calculation and persistence chain,
including:

- complete-season daily effective-marketable-fruit forecasting;
- P50, P80, and P90 forecast ranges;
- natural maturity quantity;
- harvesting capacity;
- mature inventory;
- mature loss;
- single-day peak;
- strict consecutive-seven-natural-day cumulative peak;
- seasonal cumulative quantity;
- persistence and query;
- deterministic replay;
- PostgreSQL complete-season end-to-end coverage.

The V0.1 baseline is a technical capability baseline. It is not evidence of
real-business accuracy, business representativeness, or formal business
acceptance.

### 2.2 V0.2 completed baseline

V0.2 added the engineering trial loop, including:

- actual-harvest data import;
- CSV and XLSX import;
- validation and atomic commit;
- point-in-time actual labels;
- historical backtesting with future-data leakage protection;
- forecast-quality metrics;
- comparison with one naive baseline;
- browser Forecast page;
- forecast-versus-actual Quality page;
- CSV export;
- PostgreSQL and browser end-to-end acceptance.

```text
V0_2_RELEASE_CLASS=ENGINEERING_TRIAL
REAL_BUSINESS_ACCURACY_VALIDATED=false
REAL_BUSINESS_REPRESENTATIVENESS_VALIDATED=false
FORMAL_BUSINESS_ACCEPTANCE_COMPLETE=false
```

V0.2 proves that the engineering trial product loop can run with a versioned,
deterministic trial input generator and engineering acceptance data. It does
not prove real production forecasting accuracy, business representativeness,
formal data ownership, production-system integration, or commercial
deployment acceptance.

## 3. V0.3 business forecast loop

The V0.3 primary chain is frozen as follows:

```text
真实历史数据
→ 数据质量检查
→ 数据版本冻结
→ 历史时点输入还原
→ 当前模型历史回测
→ 误差指标计算
→ 误差来源诊断
→ 参数校准和有限模型优化
→ 候选模型公平比较
→ 锁定候选模型
→ 独立测试
→ 批准试点模型版本
→ 建立试点运行能力
→ 真实产季业务试点
→ 业务试点验收
```

The completed V0.3 evidence package must be able to prove all of the
following:

1. The data source, physical meaning, unit, time basis, and statistical grain
   are explicit.
2. Historical data has an immutable or otherwise governed version identity and
   a reconstructable time-visibility boundary.
3. Historical backtests use only information available at the forecast cutoff.
4. The current model and a naive baseline are compared on identical labels,
   exclusions, cutoffs, horizons, and evaluation ranges.
5. Every model or parameter change has quantitative evidence and a recorded
   reason.
6. The test set remains sealed while parameters and candidates are selected.
7. The selected candidate passes an independent test or holdout evaluation.
8. A real-season business pilot is completed within a defined operational
   scope.
9. Business use, non-use, interpretation, and acceptance results are recorded.
10. Historical forecasts, source data versions, parameters, features, and
    model artifacts are traceable and reproducible.

## 4. Formal slice boundary

V0.3 has exactly six formal slices. No seventh slice may be introduced under
this plan, and cross-factory routing must not be added to any slice.

```text
V0_3_S1=REAL_BUSINESS_DATA_CONTRACT_AND_SOURCE_COHORT_FREEZE
V0_3_S2=REAL_HISTORICAL_DATA_INGESTION_GOVERNANCE_AND_MATERIALIZED_DATASET_FREEZE
V0_3_S3=CURRENT_MODEL_POINT_IN_TIME_BACKTEST_AND_ERROR_DIAGNOSIS
V0_3_S4=PARAMETER_CALIBRATION_MODEL_OPTIMIZATION_AND_SELECTION
V0_3_S5=BUSINESS_FORECAST_OPERATIONS_EXPLANATION_AND_CONTINUOUS_EVALUATION
V0_3_S6=REAL_SEASON_BUSINESS_PILOT_AND_RELEASE_ACCEPTANCE
```

### 4.1 V0.3-S1 — Real business data contract and source cohort freeze

```text
SLICE=V0.3-S1
ENGLISH_ID=REAL_BUSINESS_DATA_CONTRACT_AND_SOURCE_COHORT_FREEZE
MODEL_CHANGE_ALLOWED=false
PRODUCTION_MODEL_TRAINING_ALLOWED=false
FORMAL_DATA_IMPORT_AUTHORIZED=false
```

#### Objective

S1 freezes the contract and the source-cohort identity before production data is
used for model diagnosis. It does not modify the production model, train a
model, or import a formal acceptance dataset. S1 does not claim that the final
cleaned row-level dataset has already been frozen.

#### Contract decisions

- Freeze the target-decision rule and defer the final physical target decision
  until the Q2C acceptance described below.
- Freeze the physical meaning, unit, and time basis of every target and input.
- Freeze the source system, source dataset, source version, owner role, and
  revision policy.
- Freeze the historical visibility rule used to reconstruct what was known at
  a forecast cutoff.
- Freeze inclusion, exclusion, missing-day, correction, and cancellation
  rules.
- Freeze the source file/table cohort and the split-construction policy. The
  final materialized row-level split identities are accepted only after S2
  cleaning and lineage reconciliation.
- Freeze the evaluation metrics and the minimum coverage required for an
  interpretable result.
- Freeze data-quality gates, data custody and access boundaries, and the
  source-cohort manifest, source-level version identity, and hash rules.

#### Primary target and distinct quantities

```text
PRIMARY_TARGET_STATUS=UNRESOLVED_PENDING_V0_3_S1_Q2C_ACCEPTANCE

CURRENT_OBSERVED_LABEL=actual_harvest_quantity_kg
CURRENT_OBSERVED_LABEL_PHYSICAL_BOUNDARY=FARM_PICK
CURRENT_OBSERVED_LABEL_MEASUREMENT=OBSERVED_WEIGHT
CURRENT_OBSERVED_LABEL_UNIT=KG

CURRENT_CORE_FORECAST_OUTPUT=effective_marketable_quantity_kg

PHYSICAL_EQUIVALENCE_ASSUMED=false
SILENT_TARGET_SUBSTITUTION_ALLOWED=false
```

The implementation and reports must distinguish these quantities rather than
silently treating them as interchangeable:

```text
actual_harvest_quantity_kg
effective_marketable_quantity_kg
factory_received_quantity_kg
```

The current Actual Harvest label and the Core Forecast effective marketable
quantity are not automatically equivalent. V0.3 must not directly evaluate
`effective_marketable_quantity_kg` with `actual_harvest_quantity_kg` until the
physical boundary is accepted. Field sorting, processing-factory sorting,
rejection, transport loss, storage loss, and every other transformation must be
explicitly documented rather than silently inferred.

S1 must select and independently accept exactly one target path:

```text
TARGET_DECISION=OBSERVED_FARM_PICK_QUANTITY
```

or:

```text
TARGET_DECISION=VERSIONED_Q2C_TRANSFORMATION
```

The observed FARM_PICK path must explain how the existing forecast output is
aligned to the same physical boundary. A Q2C transformation path must freeze
the input and output quantities, field and factory sorting, rejection,
transport and storage loss, marketable-rate policy, date basis, grain, source,
version, availability time, manifest, hash, owner role, and scope. Until one
path is accepted:

```text
PHYSICALLY_ALIGNED_BACKTEST_ALLOWED=false
MODEL_QUALITY_CLAIM_ALLOWED=false
```

#### Evaluation grain and split policy

The canonical evaluation grain is:

```text
CANONICAL_EVALUATION_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
PLOT_SUPPORTED=false
```

`SUBFARM` and `PLOT` are not interchangeable alternatives. Plot-level support
is outside the default V0.3 contract. A future plot contract requires separate
identity, aggregation, label, and compatibility rules and separate
authorization.

The required dataset split policy is:

```text
REQUIRED_DATASET_SPLITS=TRAIN,VALIDATION,TEST
EXTERNAL_HOLDOUT_POLICY=CONDITIONAL_ON_S1_FEASIBILITY_GATE
```

Splits must use complete time intervals or complete seasons. Randomly splitting
adjacent daily rows is prohibited as the primary evaluation method.

S1 must assess complete-season count, farm and variety coverage, time span,
data completeness, point-in-time reconstructability, and canonical-grain
coverage before deciding whether an external holdout is feasible. If an
independent TEST cannot be constructed, independent model-release evaluation
and pilot approval are not allowed.

#### S1 acceptance evidence

S1 is accepted only when the target decision rule, contract, source-owner
responsibility, visibility rule, exclusion policy, split policy, metric
definitions, minimum coverage, data-custody boundary, and source-cohort hash
rules are independently reviewed. S1 acceptance does not authorize S2 data
ingestion or model work.

```text
S1_FINAL_CLEAN_ROWSET_FROZEN=false
S1_MATERIALIZED_DATASET_HASH_AVAILABLE=false
```

### 4.2 V0.3-S2 — Real historical data ingestion, governance, and materialized dataset freeze

```text
SLICE=V0.3-S2
ENGLISH_ID=REAL_HISTORICAL_DATA_INGESTION_GOVERNANCE_AND_MATERIALIZED_DATASET_FREEZE
MODEL_CHANGE_ALLOWED=false
```

#### Objective

S2 connects the approved real historical sources to the governed ingestion and
quality pipeline while preserving raw facts and their lineage. S2 materializes
the final datasets only after cleaning, correction, exclusion, and visibility
decisions. S2 does not change the forecast model.

#### Minimum data range

The governed source scope must address, where available and approved:

- actual harvest quantity;
- effective marketable quantity or marketable-fruit rate;
- farm, subfarm, plot, and variety identities;
- planted and productive area;
- tree age or planting date;
- expected and actual yield per mu;
- phenology dates;
- weather observations and their publication or availability time;
- picker count and harvesting efficiency;
- mature inventory and loss;
- data-entry time, revision time, cancellation time, and final-confirmation
  state.

#### Governance invariants

```text
RAW_SOURCE_IMMUTABLE=true
CLEANED_DATA_VERSIONED=true
MANUAL_CORRECTION_AUDITED=true
SILENT_VALUE_REPLACEMENT=false
SOURCE_ROW_LINEAGE_REQUIRED=true
POINT_IN_TIME_VISIBILITY_REQUIRED=true
```

Raw source rows must not be overwritten. Cleaning and correction must produce
versioned records with an auditable reason, actor role, timestamp, and source
lineage. Missing data must not be silently converted to zero. A revision is
usable in a historical forecast only when its visibility timestamp satisfies
the historical cutoff rule.

#### S2 responsibilities and acceptance evidence

S2 requires an immutable raw-source reference, a cleaned-data manifest, a
quality report, a correction ledger, a time-visibility report, reproducible
TRAIN/VALIDATION/TEST dataset builds, and a conditional EXTERNAL_HOLDOUT build
when S1 found it feasible. It must also record final row count, byte count,
content hashes, and the exclusion/correction lineage for every materialized
dataset.

S2 must complete final split re-acceptance after materialization. S2 acceptance
does not authorize S3 backtesting until those artifacts are reviewed and the
following independent gate is accepted:

```text
MATERIALIZED_DATASET_FREEZE_COMPLETE=true
FINAL_SPLIT_MANIFEST_ACCEPTED=true
FINAL_DATASET_HASHES_ACCEPTED=true
S3_BACKTEST_MAY_BE_AUTHORIZED=true
```

The final S2 gate is not an implementation authorization for S3.

### 4.3 Historical time-visibility and winner contract

V0.3 adopts the existing Q2A/I7 and Q2C visibility semantics. It must not
compress all source timing into one generic `available_at` field.

```text
FORECAST_CUTOFF_AT
LABEL_OBSERVATION_CUTOFF_AT
SNAPSHOT_EXECUTED_AT
SOURCE_RECORDED_AT
SOURCE_AVAILABLE_AT
SOURCE_REVISED_AT
SOURCE_FINALIZED_AT
SOURCE_CANCELLED_AT
```

Forecast inputs may be used only when:

```text
SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT
```

Actual labels must follow the existing I7/Q2C committed-state, finalized-state,
cancellation, revision-winner, terminal-lineage, deterministic tie-break, and
no-latest-row-fallback rules. Forecast-input visibility and label-observation
visibility are separate boundaries and must not be substituted for one another.

S1 must define source-specific rules for actual harvest labels, area, yield
plans, phenology, weather observations, historical weather forecasts, picker
count, harvesting efficiency, marketable rate, manual corrections, and canceled
or voided records. In particular:

- a post-season final yield may not enter a pre-season forecast input;
- a retrospectively entered phenology value may not enter an earlier forecast;
- complete post-event weather observations may not replace the weather
  forecast visible at the historical cutoff;
- post-season marketable-rate aggregates may not enter pre-season inputs;
- final test labels may use final values, but test inputs may not use future
  final values.

Any source whose historical visibility cannot be reconstructed must be marked:

```text
SOURCE_POINT_IN_TIME_ELIGIBLE=false
```

That source must be excluded from the historical input or make the relevant
backtest instance `BLOCKED`.

### 4.4 V0.3-S3 — Current model point-in-time backtest and error diagnosis

```text
SLICE=V0.3-S3
ENGLISH_ID=CURRENT_MODEL_POINT_IN_TIME_BACKTEST_AND_ERROR_DIAGNOSIS
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
```

#### Objective

S3 evaluates the current V0.2 model against the governed real historical data
using strict historical visibility. It produces an error diagnosis and a
quantified candidate-improvement backlog; it does not change the model or
parameters. S3 must remain blocked until the Q2C target path and S2 materialized
dataset gate are accepted.

#### Backtest rules

- Reconstruct each forecast input from data visible at its historical cutoff.
- Keep the production exclusion and missing-data policies identical across the
  current model and naive baseline.
- Use the final S2-accepted TRAIN, VALIDATION, and TEST identities. Use an
  EXTERNAL_HOLDOUT only when S1 declared it feasible and S2 materialized it.
- Do not use final-season facts, future revisions, or later labels to construct
  a historical input.
- Record every unavailable, excluded, and insufficient-coverage result rather
  than silently filling it.

#### Required horizons and metrics

```text
7_DAY_HORIZON
14_DAY_HORIZON
21_DAY_HORIZON
COMPLETE_SEASON
```

At minimum, report the versioned metric contract described below. Generic
metric names are not accepted as result identifiers:

- `daily_mae`;
- `daily_wape`;
- `daily_smape`;
- `cumulative_signed_error_kg`;
- `cumulative_absolute_error_kg`;
- `cumulative_signed_relative_error`;
- `cumulative_absolute_relative_error`;
- `single_day_peak_date_signed_error_days_q`;
- `single_day_peak_date_absolute_error_days_q`;
- `single_day_peak_quantity_signed_error_kg_q`;
- `single_day_peak_quantity_absolute_error_kg_q`;
- `sustained_7day_start_date_signed_error_days_q`;
- `sustained_7day_start_date_absolute_error_days_q`;
- `sustained_7day_quantity_signed_error_kg_q`;
- `sustained_7day_quantity_absolute_error_kg_q`;
- `P80_COVERAGE` and `P90_COVERAGE`;
- `P80_UPPER_QUANTILE_SPREAD` and `P90_UPPER_QUANTILE_SPREAD`;
- the explicitly versioned naive-baseline comparison fields.

#### Error attribution matrix

Error attribution has two layers and is not a strict causal decomposition.
Multiple candidate causes are allowed, and unexplained residuals must remain
visible.

```text
QUANTITY_LEVEL_ERROR
MATURITY_TIMING_ERROR
SINGLE_DAY_PEAK_ERROR
SEVEN_DAY_PEAK_ERROR
SEASON_CUMULATIVE_QUANTITY_ERROR
QUANTILE_CALIBRATION_ERROR
```

```text
PHENOLOGY_INPUT
WEATHER_RESPONSE
HARVEST_CAPACITY
MARKETABLE_RATE
MATURE_INVENTORY
MASTER_DATA
DATA_QUALITY
UNKNOWN_RESIDUAL

MULTI_LABEL_ATTRIBUTION=true
```

Each attribution records `attribution_id`, `error_instance_id`,
`error_dimension`, `candidate_cause`, `attribution_method`,
`evidence_reference`, `counterfactual_run_id`, `estimated_contribution_status`,
`estimated_contribution`, `not_computable_reason`, `confidence_class`,
`reviewer`, and `reviewed_at`. Permitted methods are
`RULE_BASED_DIAGNOSIS`, `SOURCE_CORRECTION_COMPARISON`,
`COUNTERFACTUAL_RERUN`, `ABLATION_EXPERIMENT`, and
`MANUAL_EXPERT_REVIEW`. Manual review is auditable but cannot alone authorize a
model change.

The contribution fields are fail-closed:

```text
estimated_contribution_status=COMPUTED|NOT_COMPUTABLE
```

```text
estimated_contribution_status=COMPUTED
→ estimated_contribution has a value
→ not_computable_reason is empty

estimated_contribution_status=NOT_COMPUTABLE
→ estimated_contribution is empty
→ not_computable_reason is non-empty
```

The value zero is never used to mean that a contribution could not be
computed. Multiple labels may describe one error instance and may overlap:

```text
MULTI_LABEL_CONTRIBUTIONS_MUTUALLY_EXCLUSIVE=false
MULTI_LABEL_CONTRIBUTIONS_MAY_OVERLAP=true
MULTI_LABEL_CONTRIBUTIONS_SUM_TO_100_PERCENT_REQUIRED=false
MULTI_LABEL_CONTRIBUTIONS_CAUSAL_DECOMPOSITION=false
```

Each contribution is a local estimate under its recorded method. Contributions
are not summed or normalized to 100 percent, a `NOT_COMPUTABLE` contribution
does not remove the diagnostic label, and manual review cannot fabricate a
numeric contribution.

#### S3 acceptance evidence

S3 is accepted only when the point-in-time replay, leakage audit, current-model
metrics, naive-baseline metrics, coverage report, and error-attribution matrix
are reproducible from their manifests. The output is a ranked, evidence-based
candidate list for S4, not an authorization to change the model.

### 4.5 V0.3 metric contract and threshold boundary

```text
V0_3_METRIC_CONTRACT_VERSION=v0.3-metric-contract-v1
V0_3_METRIC_CONTRACT_STATUS=PENDING_S1_ACCEPTANCE
METRIC_CONTRACT_AUTHORITY=docs/forecast-quality/s3-quality-metrics-contract.md
METRIC_CONTRACT_AUTHORITY_BASE_SHA=b873dd63fc0d5b6375f94674abbd24a94d915f3c
METRIC_INPUT_MASK_POLICY_VERSION=v0.2-s3-metric-input-mask-v1
```

V0.3 continues to reference the formal V0.2 metric semantics. A changed
formula, mask, aggregation rule, or zero policy requires a separately versioned
contract; a metric name alone is not a definition. The contract must freeze the
following machine-readable fields before any TEST access:

```text
canonical_metric_id
formula_authority
eligible_mask
missing_day_policy
zero_denominator_policy
small_denominator_policy
double_zero_policy
decimal_precision
rounding_phase
aggregation_order
weighting_policy
minimum_sample_count
minimum_coverage_ratio
grouping_grain
date_error_sign_policy
peak_tie_break_policy
seven_day_window_date_basis
horizon_aggregation_policy
not_computable_policy
```

The current authority binds `daily_mae`, `daily_wape`, and `daily_smape` to
the P50 metric mask, uses exact Decimal arithmetic, applies final-boundary
`ROUND_HALF_EVEN`, reports WAPE denominator-zero as `NOT_COMPUTABLE`, treats
the sMAPE double-zero row as zero, and does not add an epsilon to an exact
denominator. It also binds the calculation grain, deduplication, farm-after-
subfarm aggregation order, unweighted arithmetic means, minimum comparable
rows, and the continuous-calendar-day seven-day window. V0.3 must preserve
those semantics unless a new contract version is independently accepted.

```text
MINIMUM_SAMPLE_COUNT=10
MINIMUM_COVERAGE_RATIO=UNRESOLVED_PENDING_V0_3_S1_METRIC_CONTRACT
MINIMUM_COVERAGE_RATIO_STATUS=UNRESOLVED_PENDING_V0_3_S1_METRIC_CONTRACT
GROUPING_GRAIN=SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_TARGET_DATE_X_FORECAST_CUTOFF_X_MODEL_IDENTITY_X_FORECAST_QUANTILE
REPORTING_GRAIN=SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_HARVEST_BUSINESS_DATE
WEIGHTING_POLICY=UNWEIGHTED_ARITHMETIC_MEAN_AND_WAPE_ACTUAL_DENOMINATOR
SMALL_DENOMINATOR_POLICY=NO_EPSILON_EXACT_AUTHORITY_DENOMINATOR
MISSING_DAY_POLICY=REJECT_INCOMPLETE_WINDOW_AND_UNKNOWN_NOT_ZERO
DATE_ERROR_SIGN_POLICY=SIGNED_AND_ABSOLUTE_FIELDS_BOTH_REQUIRED
PEAK_TIE_BREAK_POLICY=EARLIEST_DATE_AND_EARLIEST_START_DATE
SEVEN_DAY_WINDOW_DATE_BASIS=CONTINUOUS_CALENDAR_DAYS_REJECT_INCOMPLETE_WINDOW
HORIZON_AGGREGATION_POLICY=REQUESTED_HORIZON_AND_EVALUATION_WINDOW_MUST_NOT_BE_CONFUSED
GENERIC_CUMULATIVE_ERROR_TERM_ALLOWED=false
GENERIC_SEASONAL_CUMULATIVE_ERROR_TERM_ALLOWED=false
GENERIC_PEAK_DATE_ERROR_TERM_ALLOWED=false
GENERIC_CUMULATIVE_ERROR_OCCURRENCES=0
GENERIC_SEASONAL_CUMULATIVE_ERROR_OCCURRENCES=0
```

The V0.3 metric gate uses `PASS`, `FAIL`, and `NOT_COMPUTABLE`: `PASS` means
the metric contract and required evidence are satisfied, `FAIL` means a
required contract or result check failed, and `NOT_COMPUTABLE` means the
authoritative denominator, complete window, or physical-alignment prerequisite
is unavailable. Metric-cell statuses remain those of the S3 authority,
including `COMPUTED`, `COMPARED`, `NOT_COMPUTABLE`, `NOT_VERIFIED`, and
`INSUFFICIENT_SAMPLE`.

Unless a future contract adds lower quantiles, `interval width` must not be
used as an ambiguous two-sided interval term. The current upper-quantile
semantics are:

```text
P80_UPPER_QUANTILE_SPREAD=P80-P50
P90_UPPER_QUANTILE_SPREAD=P90-P50
P80_COVERAGE=actual_target <= forecast_P80
P90_COVERAGE=actual_target <= forecast_P90
```

Coverage is meaningful only after Q2C physical alignment. S1 freezes the metric
definitions, threshold owner, threshold-setting process, and minimum coverage.
S3 derives baseline evidence only from TRAIN and VALIDATION. Before TEST is
opened, the following must be true:

```text
MODEL_ACCEPTANCE_THRESHOLD_FREEZE_COMPLETE=true
METRIC_CONTRACT_FROZEN_BEFORE_TEST=true
THRESHOLDS_FROZEN_BEFORE_TEST=true
METRIC_SEMANTICS_CHANGE_AFTER_TEST_ACCESS=false
```

Thresholds may use business requirements, TRAIN results, and VALIDATION results,
but may not be adjusted after TEST inspection. Any formula, mask, weight,
threshold, or aggregation change after TEST access requires a new metric
contract version, invalidates the old TEST conclusion, requires a new
independent authorization, and may not reuse the old TEST pass result.

### 4.6 V0.3-S4 — Parameter calibration, model optimization, and candidate selection

```text
SLICE=V0.3-S4
ENGLISH_ID=PARAMETER_CALIBRATION_MODEL_OPTIMIZATION_AND_SELECTION
```

S4 may be authorized only after S3 has been accepted. Before S3 acceptance,
no parameter or model change is in scope.

#### Optimization order

1. Calibrate data and business parameters.
2. Calibrate P80/P90 interval behavior.
3. Apply only finite model changes supported by the S3 diagnosis.

Priority candidates include:

- area;
- yield per mu;
- marketable-fruit rate;
- phenology offset;
- variety parameters;
- weather response;
- harvest efficiency;
- maturity loss;
- initial mature inventory.

Only when parameter calibration is insufficient may the candidate set consider:

- maturity-curve structure;
- variety-stratified models;
- regional-stratified models;
- weather features;
- residual features;
- residual-model retraining.

#### Fair comparison invariants

Every candidate comparison must hold the following constant:

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

The test set is sealed. It must not be repeatedly used to tune parameters or
choose candidates. If the test set is opened for a final decision, the event,
reason, and consequence must be recorded and a new independent holdout must be
defined before claiming an unbiased result.

#### Validation experiment budget and candidate-selection protocol

Before any candidate experiment is executed, S4 must freeze one experiment
plan. The values below are a finite planning boundary, not an authorization to
run experiments:

```text
EXPERIMENT_PLAN_FROZEN=true
EXPERIMENT_PLAN_VERSION=v0.3-experiment-plan-v1
EXPERIMENT_PLAN_HASH=PENDING_EXECUTION
CANDIDATE_COUNT=8
CANDIDATE_IDS=01_parameter_calibration,02_quantile_calibration,03_phenology_offset,04_yield_parameter,05_marketable_rate,06_weather_response,07_harvest_efficiency,08_residual_feature
MAX_VALIDATION_EVALUATIONS=32
MAX_RUNS_PER_CANDIDATE=4
PRIMARY_SELECTION_METRIC=daily_wape
PRIMARY_SELECTION_METRIC_STATUS=PENDING_S1_METRIC_CONTRACT_ACCEPTANCE
REGRESSION_GUARDRAILS=daily_mae,cumulative_absolute_error_kg,single_day_peak_quantity_absolute_error_kg_q,sustained_7day_quantity_absolute_error_kg_q,P80_COVERAGE,P90_COVERAGE
GROUP_COVERAGE_REQUIREMENTS=ALL_SIX_REQUIRED_BREAKDOWN_AXES;MIN_COMPARABLE_ROWS_FOR_REPORTING=10;S2_COVERAGE_RATIO_REPORTED;NO_SILENT_EXCLUSION
SELECTION_RULE=MINIMIZE_PRIMARY_SELECTION_METRIC_SUBJECT_TO_GUARDRAILS_AND_COVERAGE
TIE_BREAK_RULE=LEXICOGRAPHIC_CANDIDATE_ID_AFTER_METRIC_ROUNDING_AND_GUARDRAIL_PASS
MULTIPLE_COMPARISON_POLICY=ADJUSTED_MULTI_CANDIDATE_COMPARISON
MULTIPLE_COMPARISON_ADJUSTMENT=HOLM_BONFERRONI_OVER_PREDECLARED_PRIMARY_METRIC_COMPARISONS
```

The candidate registry is closed before the first run. Every candidate must
have all of the following fields; `PENDING_EXECUTION` means that the future
subtask has not yet produced the artifact and is not evidence of completion:

```text
candidate_id=01_parameter_calibration
candidate_family=PARAMETER_CALIBRATION
parent_model_id=V0_2_CURRENT_MODEL
hypothesis=parameter_calibration_reduces_primary_metric_without_guardrail_regression
authorized_change=NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION
feature_manifest=PENDING_EXECUTION
parameter_manifest=PENDING_EXECUTION
training_dataset_hash=PENDING_EXECUTION
validation_dataset_hash=PENDING_EXECUTION
code_commit_sha=PENDING_EXECUTION
dependency_lock_hash=PENDING_EXECUTION
random_seed_policy=FIXED_AND_RECORDED_PER_RUN
planned_run_count=4
selection_eligibility=REGISTERED_AND_GUARDRAIL_ELIGIBLE

candidate_id=02_quantile_calibration
candidate_family=QUANTILE_CALIBRATION
parent_model_id=V0_2_CURRENT_MODEL
hypothesis=quantile_calibration_improves_p80_p90_coverage_without_point_metric_regression
authorized_change=NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION
feature_manifest=PENDING_EXECUTION
parameter_manifest=PENDING_EXECUTION
training_dataset_hash=PENDING_EXECUTION
validation_dataset_hash=PENDING_EXECUTION
code_commit_sha=PENDING_EXECUTION
dependency_lock_hash=PENDING_EXECUTION
random_seed_policy=FIXED_AND_RECORDED_PER_RUN
planned_run_count=4
selection_eligibility=REGISTERED_AND_GUARDRAIL_ELIGIBLE

candidate_id=03_phenology_offset
candidate_family=PARAMETER_CALIBRATION
parent_model_id=V0_2_CURRENT_MODEL
hypothesis=versioned_phenology_offset_reduces_timing_error
authorized_change=NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION
feature_manifest=PENDING_EXECUTION
parameter_manifest=PENDING_EXECUTION
training_dataset_hash=PENDING_EXECUTION
validation_dataset_hash=PENDING_EXECUTION
code_commit_sha=PENDING_EXECUTION
dependency_lock_hash=PENDING_EXECUTION
random_seed_policy=FIXED_AND_RECORDED_PER_RUN
planned_run_count=4
selection_eligibility=REGISTERED_AND_GUARDRAIL_ELIGIBLE

candidate_id=04_yield_parameter
candidate_family=PARAMETER_CALIBRATION
parent_model_id=V0_2_CURRENT_MODEL
hypothesis=versioned_yield_parameter_calibration_reduces_quantity_error
authorized_change=NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION
feature_manifest=PENDING_EXECUTION
parameter_manifest=PENDING_EXECUTION
training_dataset_hash=PENDING_EXECUTION
validation_dataset_hash=PENDING_EXECUTION
code_commit_sha=PENDING_EXECUTION
dependency_lock_hash=PENDING_EXECUTION
random_seed_policy=FIXED_AND_RECORDED_PER_RUN
planned_run_count=4
selection_eligibility=REGISTERED_AND_GUARDRAIL_ELIGIBLE

candidate_id=05_marketable_rate
candidate_family=PARAMETER_CALIBRATION
parent_model_id=V0_2_CURRENT_MODEL
hypothesis=versioned_marketable_rate_calibration_reduces_marketable_quantity_error
authorized_change=NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION
feature_manifest=PENDING_EXECUTION
parameter_manifest=PENDING_EXECUTION
training_dataset_hash=PENDING_EXECUTION
validation_dataset_hash=PENDING_EXECUTION
code_commit_sha=PENDING_EXECUTION
dependency_lock_hash=PENDING_EXECUTION
random_seed_policy=FIXED_AND_RECORDED_PER_RUN
planned_run_count=4
selection_eligibility=REGISTERED_AND_GUARDRAIL_ELIGIBLE

candidate_id=06_weather_response
candidate_family=STRUCTURAL_MODEL_CANDIDATE
parent_model_id=V0_2_CURRENT_MODEL
hypothesis=authorized_weather_response_features_reduce_residual_error
authorized_change=NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION
feature_manifest=PENDING_EXECUTION
parameter_manifest=PENDING_EXECUTION
training_dataset_hash=PENDING_EXECUTION
validation_dataset_hash=PENDING_EXECUTION
code_commit_sha=PENDING_EXECUTION
dependency_lock_hash=PENDING_EXECUTION
random_seed_policy=FIXED_AND_RECORDED_PER_RUN
planned_run_count=4
selection_eligibility=REGISTERED_AND_GUARDRAIL_ELIGIBLE

candidate_id=07_harvest_efficiency
candidate_family=PARAMETER_CALIBRATION
parent_model_id=V0_2_CURRENT_MODEL
hypothesis=versioned_harvest_efficiency_calibration_reduces_peak_error
authorized_change=NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION
feature_manifest=PENDING_EXECUTION
parameter_manifest=PENDING_EXECUTION
training_dataset_hash=PENDING_EXECUTION
validation_dataset_hash=PENDING_EXECUTION
code_commit_sha=PENDING_EXECUTION
dependency_lock_hash=PENDING_EXECUTION
random_seed_policy=FIXED_AND_RECORDED_PER_RUN
planned_run_count=4
selection_eligibility=REGISTERED_AND_GUARDRAIL_ELIGIBLE

candidate_id=08_residual_feature
candidate_family=STRUCTURAL_MODEL_CANDIDATE
parent_model_id=V0_2_CURRENT_MODEL
hypothesis=authorized_residual_features_reduce_unexplained_residual
authorized_change=NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION
feature_manifest=PENDING_EXECUTION
parameter_manifest=PENDING_EXECUTION
training_dataset_hash=PENDING_EXECUTION
validation_dataset_hash=PENDING_EXECUTION
code_commit_sha=PENDING_EXECUTION
dependency_lock_hash=PENDING_EXECUTION
random_seed_policy=FIXED_AND_RECORDED_PER_RUN
planned_run_count=4
selection_eligibility=REGISTERED_AND_GUARDRAIL_ELIGIBLE

ALL_VALIDATION_TRIALS_RECORDED=true
FAILED_TRIALS_REMOVED_FROM_LEDGER=false
EXPERIMENT_BUDGET_NOT_EXCEEDED=true
VALIDATION_SELECTION_STATUS=NO_ACCEPTABLE_CANDIDATE_IF_BUDGET_EXHAUSTED
```

The registry includes successful, failed, aborted, rejected, and non-selected
runs. Validation candidates are finite, repeated runs are capped, manual
screening is recorded, and the search space cannot be expanded after the
budget is exhausted. A budget-exhausted search with no eligible candidate must
retain the incumbent:

```text
WHEN_VALIDATION_BUDGET_EXHAUSTED_WITHOUT_ELIGIBLE_CANDIDATE:
VALIDATION_SELECTION_STATUS=NO_ACCEPTABLE_CANDIDATE
TEST_ACCESS_CURRENTLY_AUTHORIZED=false
INCUMBENT_MODEL_RETAINED=true
```

Any further experiment requires new independent validation data or a new
pre-approved experiment round, a new plan version, a new complete candidate
list, and separate implementation authorization. The prior ledger remains
immutable.

#### TEST prerequisite contract

The following is a prerequisite contract and is not current authorization:

```text
WHEN_SEPARATELY_AUTHORIZED:
TEST_ACCESS_PREREQUISITES_FROZEN=true
EXPERIMENT_PLAN_FROZEN=true
EXPERIMENT_BUDGET_NOT_EXCEEDED=true
ALL_VALIDATION_TRIALS_RECORDED=true
CANDIDATE_REGISTRY_FROZEN=true
SELECTED_CANDIDATE_ID=PENDING_SELECTION
SELECTED_CANDIDATE_COUNT=1
INCUMBENT_MODEL_ID=V0_2_CURRENT_MODEL
METRIC_CONTRACT_VERSION=v0.3-metric-contract-v1
ACCEPTANCE_THRESHOLD_MANIFEST_HASH=PENDING_EXECUTION
SELECTION_DECISION_ARTIFACT_HASH=PENDING_EXECUTION
TEST_ACCESS_CURRENTLY_AUTHORIZED=true
```

In the current planning document no TEST authorization has been issued:

```text
TEST_ACCESS_PREREQUISITES_FROZEN=false
TEST_ACCESS_CURRENTLY_AUTHORIZED=false
TEST_ACCESS_MAY_BE_SEPARATELY_AUTHORIZED=true
PLANNING_DOCUMENT_DOES_NOT_AUTHORIZE_TEST_ACCESS=true
TEST_ACCESS_AUTHORIZATION_ID=NOT_ISSUED
AUTHORIZED_PR_NUMBER=NOT_ISSUED
AUTHORIZED_HEAD_SHA=NOT_ISSUED
AUTHORIZED_DATASET_HASH=NOT_ISSUED
AUTHORIZED_TEST_SPLIT_HASH=NOT_ISSUED
AUTHORIZED_SELECTED_CANDIDATE_ID=NOT_ISSUED
AUTHORIZED_INCUMBENT_MODEL_ID=NOT_ISSUED
AUTHORIZED_METRIC_CONTRACT_VERSION=NOT_ISSUED
AUTHORIZED_THRESHOLD_MANIFEST_HASH=NOT_ISSUED
AUTHORIZED_BY=NOT_ISSUED
AUTHORIZED_AT=NOT_ISSUED
```

S3 uses TRAIN and VALIDATION for diagnosis and candidate direction. S4 may
request separate TEST authorization only after the candidate and thresholds
are locked. Only the locked candidate and locked incumbent may enter the final
TEST comparison. If the candidate fails:

```text
SELECTED_CANDIDATE_STATUS=REJECTED
MODEL_APPROVED_FOR_PILOT=false
INCUMBENT_MODEL_RETAINED=true
```

The same TEST cannot be used for another tuning cycle. A subsequent attempt
requires unused test data, a new dataset version, a new candidate registration,
separate authorization, and a new review cycle.

If S1 proves an external holdout feasible, it is used once for final evaluation
only and never for feature selection, parameter selection, or threshold tuning.
Until that feasibility decision is accepted:

```text
EXTERNAL_HOLDOUT_GATE_STATUS=BLOCKED
EXTERNAL_HOLDOUT_GATE_BLOCK_REASON=FEASIBILITY_NOT_YET_ACCEPTED
CROSS_FARM_GENERALIZATION_CLAIM_ALLOWED=false
```

Only a reviewed S1 feasibility artifact may set the conditional gate to
`NOT_APPLICABLE`:

```text
ALLOWED_NOT_APPLICABLE_GATE=MODEL_EXTERNAL_HOLDOUT_FEASIBILITY
S1_HOLDOUT_FEASIBILITY_DECISION=NOT_FEASIBLE
S1_HOLDOUT_FEASIBILITY_ARTIFACT_HASH=PENDING_EXECUTION
S1_HOLDOUT_DECISION_REVIEWED=false
```

#### Candidate artifact requirements

Each candidate must have:

- dataset hash;
- feature manifest;
- parameter manifest;
- model artifact hash;
- source commit SHA;
- random seed;
- experiment result;
- release manifest;
- rollback plan.

S4 acceptance requires a fair comparison, an independent test result, a
selection rationale, and a reproducible pilot-approval and rollback manifest.

### 4.7 V0.3-S5 — Business forecast operations, explanation, and continuous evaluation

```text
SLICE=V0.3-S5
ENGLISH_ID=BUSINESS_FORECAST_OPERATIONS_EXPLANATION_AND_CONTINUOUS_EVALUATION
```

#### Objective

S5 operates the selected pilot-approved model in the pilot workflow and keeps the
forecast-to-actual loop auditable. It addresses explanation and operations,
not cross-factory routing or automatic production control.

#### Required capabilities

The pilot surface must support:

- comparison of the current forecast with the previous forecast;
- comparison of the current model with the previous pilot-approved model;
- comparison before and after calibration;
- P50/P80/P90 comparison;
- forecast-versus-actual comparison;
- current-model-versus-naive-baseline comparison;
- data-gap and data-quality risk notices;
- model and parameter version display;
- historical forecast query;
- result export;
- business adoption record;
- reason record for manual adjustment.

The service must preserve the immutability of historical forecasts. A new
forecast is an additional versioned result, not an overwrite of the previous
result.

#### Explanation rule

Structured explanations must be derived from actual input differences,
version differences, and result differences. The system must not invent a
weather, maturity, capacity, or data-quality cause that is not present in the
recorded evidence.

#### S5 acceptance evidence

S5 requires operational run records, version comparison evidence, persisted
explanation evidence, data-quality notices, forecast history, export evidence,
and a traceable record of business adoption or non-adoption. S5 completion means
only that pilot operations are ready:

```text
PILOT_OPERATIONS_READY=true
```

It does not mean that the real-season pilot succeeded or that business
acceptance occurred.

### 4.8 V0.3-S6 — Real-season business pilot and release acceptance

```text
SLICE=V0.3-S6
ENGLISH_ID=REAL_SEASON_BUSINESS_PILOT_AND_RELEASE_ACCEPTANCE
```

#### Objective

S6 runs the pilot-approved model through a real season and records technical,
model, and business acceptance. S6 is the final pilot and acceptance slice,
not an authorization to expand into unrelated operational automation.

#### Minimum pilot scope

```text
FARMS>=2
VARIETIES>=2
FIXED_FORECAST_CADENCE=true
ACTUAL_RESULT_FEEDBACK_COMPLETE=true
```

The actual pilot scope, source-owner authorization, measurement boundary,
security handling, and business acceptance roles must be documented before
real business data is imported. This plan does not itself grant that
authorization.

The lifecycle states are:

```text
CANDIDATE_SELECTED
CANDIDATE_TEST_PASSED
MODEL_APPROVED_FOR_PILOT
PILOT_OPERATIONS_READY
PILOT_RUNNING
V0_3_BUSINESS_PILOT_ACCEPTED
V0_3_BUSINESS_PILOT_FAILED
PRODUCTION_RELEASE_APPROVED
```

S4 may produce `MODEL_APPROVED_FOR_PILOT=true` at most. S5 owns pilot-operation
readiness. S6 is the sole owner of `V0_3_BUSINESS_PILOT_ACCEPTED` and
`V0_3_BUSINESS_PILOT_FAILED`. Business adoption records are not business
acceptance records. If the pilot fails or is not accepted:

```text
V0_3_COMPLETE=false
PRODUCTION_RELEASE_APPROVED=false
PILOT_MODEL_ROLLBACK_REQUIRED=true
```

V0.3 does not authorize production release:

```text
PRODUCTION_RELEASE_APPROVED=false
PRODUCTION_RELEASE_IN_V0_3_SCOPE=false
```

#### Technical acceptance

Technical acceptance must cover:

- data import;
- forecast execution;
- historical result query;
- data and model traceability;
- deterministic replay;
- PostgreSQL E2E;
- browser E2E;
- full-suite CI;
- a unique Alembic head.

#### Model acceptance

Model acceptance must report:

- daily error;
- seven-day error;
- fourteen-day error;
- twenty-one-day error;
- `single_day_peak_date_signed_error_days_q` and
  `single_day_peak_date_absolute_error_days_q`;
- `sustained_7day_start_date_signed_error_days_q` and
  `sustained_7day_start_date_absolute_error_days_q`;
- `cumulative_signed_error_kg`, `cumulative_absolute_error_kg`,
  `cumulative_signed_relative_error`, and
  `cumulative_absolute_relative_error`;
- P80 coverage;
- P90 coverage;
- improvement or regression against the current model;
- improvement or regression against the naive baseline.

#### Business acceptance

Business acceptance must record:

- whether high peaks were identified early enough;
- whether the forecast informed workforce preparation;
- whether it informed packaging preparation;
- whether it informed precooling and processing preparation;
- whether business users understood the forecast;
- whether false positives and false negatives were acceptable;
- whether the forecast was adopted;
- why it was not adopted when it was not used;
- whether the evidence supports a larger pilot.

## 5. Explicit non-scope

The following are outside V0.3. They are not optional enhancements and must
not be smuggled into a formal slice through an implementation backlog:

```text
MULTI_FACTORY_ROUTING
CROSS_FACTORY_ALLOCATION
FACTORY_CAPACITY_OPTIMIZATION
AUTOMATIC_PEAK_SHAVING
VEHICLE_ROUTING
TRANSPORT_SCHEDULING
PRECOOLING_CHAMBER_SCHEDULING
PROCESSING_LINE_SCHEDULING
REAL_TIME_ERP_INTEGRATION
REAL_TIME_IOT_INTEGRATION
AUTOMATIC_PRODUCTION_COMMANDS
COMPLEX_RBAC
APPROVAL_WORKFLOW_PLATFORM
MULTI_AGENT_EXPANSION
LLM_CHAT
COLD_STORAGE_DESIGN_OPTIMIZATION
```

In particular:

```text
MULTI_FACTORY_ROUTING_IN_SCOPE=false
FACTORY_CAPACITY_OPTIMIZATION_IN_SCOPE=false
AUTOMATIC_PRODUCTION_DISPATCH_IN_SCOPE=false
```

V0.3 may record an operational context or a manually supplied capacity
constraint when that is necessary to evaluate the forecast, but it does not
automatically route loads, allocate work across factories, schedule equipment,
or issue production commands.

## 6. Completion gate

The final completion marker is frozen as:

```text
BLUEBERRY_FORECAST_AGENT_V0_3_BUSINESS_FORECAST_PILOT_COMPLETE
```

The marker may be used only when every condition below is true. Listing a
condition here does not assert that it has been satisfied.

In this gate, `REAL_DATASET_FROZEN=true` means the final S2 materialized
dataset has passed split and hash re-acceptance; it does not mean that S1 froze
the final cleaned row set.

```text
V0_3_S1_COMPLETE=true
V0_3_S2_COMPLETE=true
V0_3_S3_COMPLETE=true
V0_3_S4_COMPLETE=true
V0_3_S5_COMPLETE=true
V0_3_S6_COMPLETE=true

REAL_DATA_CONTRACT_ACCEPTED=true
REAL_DATASET_FROZEN=true
MATERIALIZED_DATASET_FREEZE_COMPLETE=true
FINAL_SPLIT_MANIFEST_ACCEPTED=true
FINAL_DATASET_HASHES_ACCEPTED=true
DATA_QUALITY_GATE_PASSED=true
POINT_IN_TIME_BACKTEST_PASSED=true
CURRENT_MODEL_BASELINE_COMPLETE=true
ERROR_DIAGNOSIS_COMPLETE=true
SELECTED_MODEL_HOLDOUT_TEST_PASSED=true
PILOT_MODEL_RELEASE_MANIFEST_COMPLETE=true
MODEL_APPROVED_FOR_PILOT=true
BUSINESS_PILOT_COMPLETED=true
BUSINESS_ACCEPTANCE_RECORDED=true
POSTGRESQL_E2E_PASSED=true
BROWSER_E2E_PASSED=true
FULL_SUITE_CI_PASSED=true
UNIQUE_ALEMBIC_HEAD=true
```

No release, production-deployment, or broader-scope claim may use the marker
while any condition is false, unverified, or only inferred from a merged code
change.

## 7. V0.3 completion evidence matrix

Every final gate must be represented by an evidence row containing:

```text
gate_id
gate_class
owner_role
authoritative_artifact
artifact_hash_or_run_id
metric_contract_version
acceptance_threshold
status
reviewer
reviewed_at
notes
```

Allowed statuses are only:

```text
PASS
FAIL
BLOCKED
NOT_APPLICABLE
```

The following is the V0.3 Completion Gate Registry. Each row is independent;
the current planning document deliberately records every row as `BLOCKED` with
`NOT_YET_EXECUTED`. No future hash, run ID, reviewer name, or review timestamp
is invented here.

| gate_id | gate_class | required_or_conditional | owner_role | authoritative_artifact | artifact_identity_source | acceptance_threshold_source | allowed_not_applicable_condition | initial_status | initial_block_reason | reviewer_role |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `SLICE_S1_COMPLETE` | technical | required | `v0_3_plan_owner` | S1 acceptance package | governed manifest | S1 acceptance criteria | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `SLICE_S2_COMPLETE` | technical | required | `data_governance_owner` | S2 acceptance package | materialized dataset manifest | S2 acceptance criteria | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `SLICE_S3_COMPLETE` | model | required | `model_validation_owner` | S3 backtest package | backtest manifest | S3 acceptance criteria | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `SLICE_S4_COMPLETE` | model | required | `model_selection_owner` | S4 selection package | experiment manifest | S4 acceptance criteria | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `SLICE_S5_COMPLETE` | technical | required | `pilot_operations_owner` | S5 operations package | pilot operations manifest | S5 acceptance criteria | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `SLICE_S6_COMPLETE` | business | required | `business_pilot_owner` | S6 pilot acceptance package | pilot acceptance manifest | S6 acceptance criteria | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `TECH_UNIQUE_ALEMBIC_HEAD` | technical | required | `engineering_release_owner` | migration head output | exact revision and run ID | one expected head | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `TECH_POSTGRESQL_E2E` | technical | required | `engineering_test_owner` | PostgreSQL E2E report | exact-head CI run ID | required PostgreSQL jobs pass | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `TECH_BROWSER_E2E` | technical | required | `frontend_test_owner` | browser E2E report | exact-head CI run ID | desktop and mobile jobs pass | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `TECH_REQUIRED_CI_JOBS` | technical | required | `engineering_release_owner` | CI job registry | exact-head CI run ID | all required jobs pass | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `TECH_DETERMINISTIC_REPLAY` | technical | required | `engineering_test_owner` | replay evidence package | replay manifest hash | same input produces same identity | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `TECH_LINEAGE_INTEGRITY` | technical | required | `data_governance_owner` | lineage and correction ledger | lineage manifest hash | every accepted row has lineage | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `TECH_RELEASE_MANIFEST_INTEGRITY` | technical | required | `engineering_release_owner` | pilot release manifest | manifest hash | code, data, model, and parameter identities bind | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_Q2C_PHYSICAL_ALIGNMENT` | model | required | `data_governance_owner` | Q2C decision package | attestation and decision hash | one closed Q2C outcome | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_MATERIALIZED_DATASET_ACCEPTED` | model | required | `data_governance_owner` | S2 materialized dataset package | dataset manifest hash | final rowset and lineage accepted | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_MATERIALIZED_DATASET_FREEZE_COMPLETE` | model | required | `data_governance_owner` | S2 freeze record | materialized dataset hash | freeze and immutability accepted | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_FINAL_SPLIT_MANIFEST_ACCEPTED` | model | required | `model_validation_owner` | final split manifest | split manifest hash | TRAIN/VALIDATION/TEST accepted | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_FINAL_DATASET_HASHES_ACCEPTED` | model | required | `data_governance_owner` | final dataset hash package | dataset hash set | all materialized hashes accepted | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_DATA_QUALITY_GATE` | model | required | `data_quality_owner` | quality and exclusion report | quality report hash | quality thresholds and exclusions accepted | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_POINT_IN_TIME_REPLAY` | model | required | `model_validation_owner` | historical replay package | replay manifest hash | input and label cutoffs bind | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_FUTURE_LEAKAGE_AUDIT` | model | required | `model_validation_owner` | leakage audit package | audit run ID and hash | no future input or label leakage | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_CURRENT_BASELINE_COMPLETE` | model | required | `model_validation_owner` | current-model baseline package | baseline manifest hash | all required horizons and groups reported | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_ERROR_DIAGNOSIS_COMPLETE` | model | required | `model_validation_owner` | attribution matrix package | attribution manifest hash | methods and evidence are complete | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_EXPERIMENT_PLAN_FROZEN` | model | required | `model_selection_owner` | experiment plan and candidate registry | plan hash | finite budget and candidates frozen | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_VALIDATION_BUDGET_COMPLIANT` | model | required | `model_selection_owner` | validation ledger | ledger hash | budget not exceeded and all trials recorded | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_CANDIDATE_REGISTRY_FROZEN` | model | required | `model_selection_owner` | candidate registry | registry hash | complete finite registry accepted | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_TEST_ACCESS_SEPARATELY_AUTHORIZED` | model | required | `model_selection_owner` | independent TEST authorization record | authorization ID and dataset hashes | authorized head, split, candidate, and metric version match | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_LOCKED_TEST_COMPLETE` | model | required | `model_validation_owner` | locked TEST result | test run ID and result hash | only locked candidate and incumbent evaluated | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_PRIMARY_METRIC_ACCEPTED` | model | required | `model_validation_owner` | metric result package | metric manifest hash | primary metric and status pass | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_REGRESSION_GUARDRAILS_ACCEPTED` | model | required | `model_validation_owner` | regression guardrail package | guardrail manifest hash | every guardrail passes or is explicitly not computable | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_QUANTILE_CALIBRATION_ACCEPTED` | model | required | `model_validation_owner` | quantile calibration package | calibration manifest hash | P80/P90 semantics and coverage accepted | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_PILOT_ARTIFACT_MANIFEST_COMPLETE` | model | required | `model_selection_owner` | pilot model release manifest | model manifest hash | code, data, parameter, artifact, and rollback identities bind | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_APPROVED_FOR_PILOT` | model | required | `model_selection_owner` | pilot approval record | approval record ID and manifest hash | locked TEST and rollback evidence pass | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `MODEL_EXTERNAL_HOLDOUT_FEASIBILITY` | model | conditional | `model_validation_owner` | S1 holdout feasibility decision | feasibility artifact hash | feasibility decision reviewed | only after reviewed `NOT_FEASIBLE` decision | `BLOCKED` | `FEASIBILITY_NOT_YET_ACCEPTED` | `PENDING_INDEPENDENT_REVIEW` |
| `BUSINESS_DATA_OWNER_ACCEPTANCE` | business | required | `business_data_owner_role` | governed source acceptance | attestation hash | formal source-owner acceptance | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `BUSINESS_TARGET_CONTRACT_ACCEPTANCE` | business | required | `business_owner_role` | target semantic acceptance | Q2C decision hash | physical target boundary accepted | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `BUSINESS_PILOT_SCOPE_ACCEPTANCE` | business | required | `business_pilot_owner` | pilot scope record | scope manifest hash | farms, varieties, cadence, and purpose accepted | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `BUSINESS_PILOT_OPERATIONS_READY` | business | required | `pilot_operations_owner` | operations readiness package | readiness manifest hash | run, compare, explain, and feedback paths ready | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `BUSINESS_REAL_SEASON_EXECUTION_COMPLETE` | business | required | `business_pilot_owner` | real-season pilot ledger | pilot run manifest hash | actual feedback and cadence complete | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `BUSINESS_ADOPTION_AND_NON_ADOPTION_LEDGER_COMPLETE` | business | required | `business_pilot_owner` | adoption ledger | ledger hash | adoption and non-adoption reasons recorded | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `BUSINESS_FALSE_POSITIVE_FALSE_NEGATIVE_REVIEW_COMPLETE` | business | required | `business_pilot_owner` | business error review | review record ID and hash | false-positive and false-negative review accepted | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |
| `BUSINESS_PILOT_ACCEPTANCE_DECISION` | business | required | `business_acceptance_owner` | pilot accept/fail decision | decision record ID and hash | explicit accept or fail decision recorded | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` |

Each row also carries the following runtime fields, which remain pending in
this planning document:

```text
artifact_hash_or_run_id=PENDING_EXECUTION
reviewer=PENDING_INDEPENDENT_REVIEW
reviewed_at=PENDING_INDEPENDENT_REVIEW
notes=PENDING_EXECUTION
```

`NOT_APPLICABLE` is permitted only for
`MODEL_EXTERNAL_HOLDOUT_FEASIBILITY`, and only after the reviewed S1 artifact
proves `S1_HOLDOUT_FEASIBILITY_DECISION=NOT_FEASIBLE`. All required gates must
be `PASS`; no required gate may use `NOT_APPLICABLE` to bypass evidence.
`FULL_SUITE_CI_PASSED` proves only a technical gate. Browser E2E does not prove
model accuracy, PostgreSQL E2E does not prove real-data representativeness, and
a skipped `full-suite-canary` is never converted to `PASS`.

The existing completion booleans map one-to-one to gate IDs as follows:

```text
V0_3_S1_COMPLETE=SLICE_S1_COMPLETE
V0_3_S2_COMPLETE=SLICE_S2_COMPLETE
V0_3_S3_COMPLETE=SLICE_S3_COMPLETE
V0_3_S4_COMPLETE=SLICE_S4_COMPLETE
V0_3_S5_COMPLETE=SLICE_S5_COMPLETE
V0_3_S6_COMPLETE=SLICE_S6_COMPLETE
REAL_DATA_CONTRACT_ACCEPTED=MODEL_Q2C_PHYSICAL_ALIGNMENT
REAL_DATASET_FROZEN=MODEL_MATERIALIZED_DATASET_ACCEPTED
MATERIALIZED_DATASET_FREEZE_COMPLETE=MODEL_MATERIALIZED_DATASET_FREEZE_COMPLETE
FINAL_SPLIT_MANIFEST_ACCEPTED=MODEL_FINAL_SPLIT_MANIFEST_ACCEPTED
FINAL_DATASET_HASHES_ACCEPTED=MODEL_FINAL_DATASET_HASHES_ACCEPTED
DATA_QUALITY_GATE_PASSED=MODEL_DATA_QUALITY_GATE
POINT_IN_TIME_BACKTEST_PASSED=MODEL_POINT_IN_TIME_REPLAY
CURRENT_MODEL_BASELINE_COMPLETE=MODEL_CURRENT_BASELINE_COMPLETE
ERROR_DIAGNOSIS_COMPLETE=MODEL_ERROR_DIAGNOSIS_COMPLETE
SELECTED_MODEL_HOLDOUT_TEST_PASSED=MODEL_LOCKED_TEST_COMPLETE
PILOT_MODEL_RELEASE_MANIFEST_COMPLETE=MODEL_PILOT_ARTIFACT_MANIFEST_COMPLETE
MODEL_APPROVED_FOR_PILOT=MODEL_APPROVED_FOR_PILOT
BUSINESS_PILOT_COMPLETED=BUSINESS_REAL_SEASON_EXECUTION_COMPLETE
BUSINESS_ACCEPTANCE_RECORDED=BUSINESS_PILOT_ACCEPTANCE_DECISION
POSTGRESQL_E2E_PASSED=TECH_POSTGRESQL_E2E
BROWSER_E2E_PASSED=TECH_BROWSER_E2E
FULL_SUITE_CI_PASSED=TECH_REQUIRED_CI_JOBS
UNIQUE_ALEMBIC_HEAD=TECH_UNIQUE_ALEMBIC_HEAD
```

```text
ALL_COMPLETION_BOOLEANS_MAPPED_TO_GATE_IDS=true
UNMAPPED_COMPLETION_BOOLEAN_COUNT=0
ALL_REQUIRED_TECHNICAL_GATES=PASS
ALL_REQUIRED_MODEL_GATES=PASS
ALL_REQUIRED_BUSINESS_GATES=PASS
ALL_CONDITIONAL_GATES=PASS_OR_PREAUTHORIZED_NOT_APPLICABLE
```

The last four values are completion conditions, not current assertions. The
completion marker may be used only after the registry contains accepted rows
for every required gate and an allowed conditional gate disposition.

## 8. Authorization sequence and dependency gates

The slice dependency order is explicit:

```text
S1_ACCEPTED → S2_MAY_BE_AUTHORIZED
S2_ACCEPTED → S3_MAY_BE_AUTHORIZED
S3_ACCEPTED → S4_MAY_BE_AUTHORIZED
S4_ACCEPTED → S5_MAY_BE_AUTHORIZED
S5_ACCEPTED → S6_MAY_BE_AUTHORIZED
```

The arrows describe a prerequisite for a later authorization; they do not
authorize the later implementation automatically. Every slice requires a
separate scope, evidence, and authorization decision.

```text
NO_STEP_IMPLIES_THE_NEXT=true
OPEN_BACKLOG_DOES_NOT_EXTEND_VERSION_SCOPE=true
PLANNING_DOES_NOT_AUTHORIZE_IMPLEMENTATION=true
```

An open backlog item cannot expand V0.3 beyond the six formal slices. A product
or governance request that is outside this document requires an explicit
version replan before it can be considered.

## 9. Data, privacy, and reproducibility boundaries

Real business data may be used in V0.3 only after a separate authorization has
confirmed the source owner, purpose, approved dataset identity, physical
measurement boundary, historical visibility, access controls, and retention
rules. No real data is added by this planning document.

Every accepted dataset or model result must be reproducible from a stable
manifest. The manifest must identify source version, time boundary, inclusion
and exclusion rules, feature set, parameters, code commit, model artifact, and
random seed where applicable. Sensitive raw rows, credentials, personal data,
and private source URLs must not be committed to the repository.

```text
COMMIT_REAL_BUSINESS_DATA_TO_GIT=false
COMMIT_DERIVED_REAL_BUSINESS_ROW_DATA_TO_GIT=false
COMMIT_PRIVATE_SOURCE_URL_TO_GIT=false
COMMIT_CREDENTIALS_TO_GIT=false
```

The repository may contain contracts, schema, manifest structure, hashes, row
and byte counts, non-sensitive summaries, synthetic fixtures, and explicitly
approved de-identified examples only. Real raw data and cleaned real row-level
data must remain in controlled external storage. S1 must freeze the storage
type, access owner, least-privilege boundary, retention, withdrawal and void
rules, downstream propagation, purpose, usage authorization, and the binding
between the manifest and the external object.

The trial and pilot evidence must distinguish:

- engineering-flow correctness;
- statistical/model evidence;
- real-business data acceptance;
- business adoption and formal acceptance.

Passing one category does not imply passing another category.

## 10. Controlled subtask decomposition

The six formal slices remain fixed, while controlled subtasks and multiple
reviewable PRs are allowed inside a slice:

```text
V0_3_TOTAL_SLICES=6
FORMAL_SLICE_COUNT_FIXED=true
SUBTASK_DECOMPOSITION_ALLOWED=true
SUBTASK_SCOPE_EXPANSION_ALLOWED=false
ONE_FORMAL_SLICE_MAY_USE_MULTIPLE_CONTROLLED_PRS=true
```

Every subtask has an explicit planning record with:

```text
subtask_id
parent_slice
objective
scope
dependencies
authorized_path_prefixes
proposed_new_paths
acceptance_evidence
explicit_non_scope
authorization_state
next_subtask_not_implied
```

The following are controlled subtasks, not additional formal slices. Because
this overall plan does not authorize implementation and cannot safely freeze
implementation paths before the independent subtask authorization, every
record uses `NONE_UNTIL_SUBTASK_AUTHORIZATION` rather than an invented path.

```text
subtask_id=S2-A
parent_slice=V0.3-S2
objective=SOURCE_AUTHORITY_AND_GOVERNED_LANDING
scope=approved source authority binding; external object manifest; immutable raw-source identity; governed landing interface or process
dependencies=S1_ACCEPTED
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=source authority record; object manifest; raw-source identity and lineage review
explicit_non_scope=data cleaning; final split; model backtest; model change
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S2-B
parent_slice=V0.3-S2
objective=IDENTITY_MAPPING_AND_DETERMINISTIC_CLEANING
scope=farm/subfarm/variety/season identity mapping; unit normalization; deterministic cleaning; correction and exclusion ledger
dependencies=S2-A_ACCEPTED
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=identity mapping manifest; cleaning rules; correction/exclusion ledger; deterministic replay
explicit_non_scope=final dataset split; final metrics; model modification; TEST access
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S2-C
parent_slice=V0.3-S2
objective=QUALITY_AND_HISTORICAL_VISIBILITY_MATERIALIZATION
scope=data quality report; point-in-time eligibility; source-specific winner selection; historical visibility materialization
dependencies=S2-B_ACCEPTED
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=quality report; visibility report; winner/lineage evidence; leakage preflight
explicit_non_scope=model backtest; TEST access; model training; production release
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S2-D
parent_slice=V0.3-S2
objective=MATERIALIZED_DATASET_BUILD_AND_FINAL_SPLIT_RE_ACCEPTANCE
scope=TRAIN/VALIDATION/TEST materialization; conditional external holdout; final manifests; final hashes; split re-acceptance
dependencies=S2-C_ACCEPTED
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=materialized dataset manifests; split manifest; hash set; final row/exclusion lineage
explicit_non_scope=S3 execution; model modification; TEST access; pilot operations
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S4-A
parent_slice=V0.3-S4
objective=EXPERIMENT_REGISTRY_BUDGET_AND_REPRODUCIBILITY
scope=experiment plan; finite candidate registry; validation budget; run ledger; reproducibility identities
dependencies=S3_ACCEPTED
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=experiment plan hash; candidate registry; complete validation ledger; reproducibility manifest
explicit_non_scope=unregistered candidate execution; TEST access; pilot approval; production release
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S4-B
parent_slice=V0.3-S4
objective=PARAMETER_AND_QUANTILE_CALIBRATION
scope=versioned parameter calibration; P80/P90 calibration; validation-only evaluation under the frozen experiment budget
dependencies=S4-A_ACCEPTED
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=parameter manifest; quantile calibration report; validation ledger entries; guardrail report
explicit_non_scope=model structure change; TEST access; pilot approval; production release
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S4-C
parent_slice=V0.3-S4
objective=EVIDENCE_AUTHORIZED_STRUCTURAL_MODEL_CANDIDATES
scope=only S3-supported structural candidates; feature/parameter manifests; candidate artifacts; reproducible validation comparison
dependencies=S4-B_EVIDENCE_REVIEWED_AND_S3_AUTHORIZATION_LIST_ACCEPTED
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=candidate registry entry; S3 evidence reference; artifact hash; validation result and ledger entry
explicit_non_scope=unsupported model candidate; hidden trial; TEST access; production release
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S4-D
parent_slice=V0.3-S4
objective=LOCKED_CANDIDATE_TEST_AND_PILOT_MODEL_APPROVAL
scope=locked candidate/incumbent comparison; separate TEST authorization; one-time TEST result; pilot-model approval and rollback manifest
dependencies=EXPERIMENT_BUDGET_COMPLETE_AND_CANDIDATE_LOCKED_AND_SEPARATE_TEST_AUTHORIZATION
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=TEST authorization record; locked test result; selection decision; pilot approval and rollback manifest
explicit_non_scope=TEST-after tuning; new hidden candidate; production release; S5 operations
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S5-A
parent_slice=V0.3-S5
objective=BACKEND_PILOT_OPERATIONS
scope=pilot model execution; versioned forecast operations; persisted comparison and run evidence; export and feedback hooks
dependencies=MODEL_APPROVED_FOR_PILOT
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=operations readiness package; run records; comparison/readback/export evidence
explicit_non_scope=model training; model selection; business acceptance; production release
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S5-B
parent_slice=V0.3-S5
objective=FRONTEND_COMPARISON_WARNINGS_AND_STRUCTURED_EXPLANATION
scope=forecast comparison; data-quality warnings; evidence-derived explanations; model/parameter version display
dependencies=S5-A_ACCEPTED
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=browser evidence; persisted explanation evidence; warning and comparison acceptance report
explicit_non_scope=client-side forecast calculation; LLM unsupported explanation; business acceptance; production release
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S5-C
parent_slice=V0.3-S5
objective=CONTINUOUS_EVALUATION_AND_ADOPTION_RECORDS
scope=forecast-to-actual feedback; continuous metric updates; adoption/non-adoption ledger; manual adjustment reasons
dependencies=S5-A_ACCEPTED_AND_S5-B_ACCEPTED
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=continuous evaluation package; adoption ledger; non-adoption reasons; adjustment audit
explicit_non_scope=production release; S6 pilot acceptance decision; cross-factory routing
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true
```

All eleven subtasks require independent authorization, a scoped PR, and
acceptance evidence. A subtask acceptance does not authorize the next subtask,
and decomposition cannot add a seventh slice or expand the non-scope:

```text
SUBTASK_RECORD_COUNT=11
SUBTASK_ACCEPTANCE_DOES_NOT_AUTHORIZE_NEXT=true
SUBTASK_DECOMPOSITION_DOES_NOT_EXPAND_SCOPE=true
```

## 11. Authority precedence and known documentation conflicts

The following authority order applies:

1. `docs/forecast-quality/q2c-physical-target-equivalence-contract.md`
   (`Q2C`) governs physical target equivalence and target disposition.
2. `docs/forecast-quality/q2a-i7-label-snapshot-and-revision-winner-contract.md`
   (`Q2A/I7`) governs label visibility, winner selection, lineage, and
   canonical grain.
3. `docs/forecast-quality/s3-quality-metrics-contract.md` (`S3`) governs the
   existing metric formulas, masks, zero policies, Decimal semantics, and peak
   tie-breaking.
4. `docs/v0-1/core-forecast-contract.md` (`Core Forecast`) governs the forecast
   quantities, date basis, and strict consecutive-seven-day peak.
5. `backend/app/core_forecast/schemas.py`,
   `backend/app/actual_harvest_import/schemas.py`, and
   `backend/app/rolling_backtest/orchestration.py` are the sampled production
   implementation references for those contracts.
6. The current Actual Harvest contract cannot be silently substituted for
   effective marketable quantity.
7. The older three-day wording in `AGENTS.md` is a documentation conflict for a
   separate governance task; this PR does not modify `AGENTS.md`.
8. README transport, processing-capacity, and cross-factory language is product
   context, not V0.3 authorization.
9. `destination_factory_id` is not a cross-factory routing authority.
10. Older “not implemented” status text in Q2A/I7 does not override current code
   and accepted V0.2 engineering evidence; stale documentation requires a
   separate governance task.

These conflicts must not be resolved by changing an unrelated file in this PR.

The metric authority is pinned independently of this plan:

```text
METRIC_CONTRACT_AUTHORITY=docs/forecast-quality/s3-quality-metrics-contract.md
METRIC_CONTRACT_AUTHORITY_BASE_SHA=b873dd63fc0d5b6375f94674abbd24a94d915f3c
METRIC_INPUT_MASK_POLICY_VERSION=v0.2-s3-metric-input-mask-v1
V0_3_METRIC_CONTRACT_VERSION=v0.3-metric-contract-v1
```

## 11.1. R2 content-correction closure

The following statuses describe the planning-document corrections only. They
are not implementation, acceptance, TEST access, or release approvals:

```text
V0_3_METRIC_CONTRACT_NOT_UNIQUE=ADDRESSED
HOLDOUT_AND_MODEL_SELECTION_PROTOCOL_UNCLOSED=ADDRESSED
ERROR_ATTRIBUTION_METHOD_UNDEFINED=ADDRESSED
COMPLETION_GATE_EVIDENCE_NOT_CLOSED=ADDRESSED
SLICE_INTERNAL_DECOMPOSITION_UNDEFINED=ADDRESSED
HIDDEN_TEST_ACCESS_AUTHORIZATION=ADDRESSED
```

## 12. Current authorization status

This document freezes the plan only. No V0.3 implementation is authorized by
this commit or by its Draft PR.

```text
V0_3_PLAN_FROZEN=true

V0_3_IMPLEMENTATION_AUTHORIZED=false
V0_3_S1_IMPLEMENTATION_AUTHORIZED=false
V0_3_S2_IMPLEMENTATION_AUTHORIZED=false
V0_3_S3_IMPLEMENTATION_AUTHORIZED=false
V0_3_S4_IMPLEMENTATION_AUTHORIZED=false
V0_3_S5_IMPLEMENTATION_AUTHORIZED=false
V0_3_S6_IMPLEMENTATION_AUTHORIZED=false

REAL_DATA_IMPORT_AUTHORIZED=false
MODEL_CHANGE_AUTHORIZED=false
PRODUCTION_CODE_CHANGE_AUTHORIZED=false
MIGRATION_AUTHORIZED=false
FRONTEND_CHANGE_AUTHORIZED=false
MULTI_FACTORY_ROUTING_AUTHORIZED=false
TEST_ACCESS_CURRENTLY_AUTHORIZED=false
PLANNING_DOCUMENT_DOES_NOT_AUTHORIZE_TEST_ACCESS=true
```

The next permitted task is a separately planned and separately authorized:

```text
NEXT_TASK=V0_3_S1
NEXT_TASK_SCOPE=REAL_BUSINESS_DATA_CONTRACT_AND_SOURCE_COHORT_FREEZE
```

That next task must not be started automatically by this plan, this branch, or
the associated Draft PR.
