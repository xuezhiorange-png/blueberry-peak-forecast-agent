# V0.3-S3 Daily Rowset Amendment Contract

## Amendment identity and phase boundary

~~~text
AMENDMENT_ID=V0_3_S3_DAILY_ROWSET_AMENDMENT
AMENDMENT_VERSION=v0-3-s3-daily-rowset-amendment-v1
TASK_ID=V03_S3_A_DAILY_ROWSET_AMENDMENT_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A_DAILY_ROWSET_AMENDMENT_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=CURRENT_MODEL_POINT_IN_TIME_BACKTEST_AND_ERROR_DIAGNOSIS
USER_GATE=可以下一步
CONTRACT_ONLY=true
BASE_MAIN_SHA=0a6f412aad63e1f66a5e14e5960ca88deb9b2dcd
BASE_MAIN_TREE_SHA=281d6ecae3daca2acc52e3a7be6522acf12df8ae
BASE_REF=origin/main
PARENT_CONTRACT_ID=V0_3_S3_BACKTEST_AND_DIAGNOSIS_CONTRACT
PARENT_CONTRACT_VERSION=v0-3-s3-backtest-and-diagnosis-contract-v1
PARENT_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
PARENT_CONTRACT_GIT_BLOB_SHA=500896b8150c232e4476e98253b5a7439850001d
PARENT_CONTRACT_SHA256=090acecf54409b86aadaee61cee00a1dd4880450f3f22d183474e00910130bc1
P0_PR=298
P0_MERGE=0a6f412aad63e1f66a5e14e5960ca88deb9b2dcd
REVIEWER_ROLE=COORDINATOR
USER_WAIVED_THIRD_PARTY_REVIEW=true
COORDINATOR_REVIEW_COUNTS=true
NO_STEP_IMPLIES_THE_NEXT=true
~~~

~~~text
S3_A_DAILY_ROWSET_AMENDMENT_CONTRACT_AUTHORIZED=true
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=false
S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
S3_BACKTEST_EXECUTION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false
S3_B_AUTHORIZED=false
S3_C_AUTHORIZED=false
S3_D_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
SOURCE_002_ROW_LEVEL_READ=false
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
ALLOWLIST_EXPANSION_AUTHORIZED=false
V0_3_S4_AUTHORIZED=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
LLM_MUST_NOT_INVENT_TONNES=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

The `S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=false` line in the identity block
above is the S3-A contract freeze-time snapshot. Live materialization
authorization is maintained in `docs/v0-3/development-plan.md` §4.4 and the
S3-A rowset materialization authorization package when issued.

The `S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED=false` line in the identity
block above is the S3-A contract freeze-time snapshot. Live completeness
verification authorization is maintained in `docs/v0-3/development-plan.md` §4.4
and the S3-A completeness verification authorization package when issued.

This document freezes the V0.3-S3-A daily rowset amendment contract. It defines
how sparse SOURCE_002 harvest grains and incumbent-model forecasts must be
expanded into a complete, auditable calendar daily row set for peak and
cumulative metrics. It is a governance amendment, not materialization,
completeness verification, backtest execution, or metric computation.

Merging this amendment does **not** materialize a daily rowset table, does
**not** authorize backtest execution, and does **not** make peak metrics
computable until a separately authorized materialization and completeness
verification pass.

## 1. Inherited authority (not reopened)

### 1.1 Parent S3 P0 contract

~~~text
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
P0_CONTRACT_VERSION=v0-3-s3-backtest-and-diagnosis-contract-v1
P0_EVIDENCE_JSON_SHA256=580f09e306e4e32db0e72d65158d455bd9fea57b4279497909ff0d54cb91259c
V0_3_S3_PHASE_ENTRY_AUTHORIZED=true
~~~

### 1.2 S2 materialized dataset (accepted)

~~~text
S2_CONTRACT_PATH=docs/v0-3/s2/s2-materialized-dataset-contract.md
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
S2_CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_ROW_COUNT=16224
VALIDATION_ROW_COUNT=8006
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
CANONICAL_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
FROZEN_SOURCE_ARTIFACT_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
~~~

### 1.3 V0.3-S3 input authorities (distinct; do not conflate)

~~~text
V0_3_S3_ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
V0_3_S3_VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
V0_2_S3_INPUT_AUTHORITY_HISTORICAL=S2_IMMUTABLE_BACKTEST_BINDING
DO_NOT_CONFLATE_V0_2_S2_IMMUTABLE_BACKTEST_BINDING_WITH_V0_3_S2_DATASET=true
~~~

The V0.2 metric contract names `S3_INPUT_AUTHORITY=S2_IMMUTABLE_BACKTEST_BINDING`
for the V0.2 engineering trial pairing. That artifact exposes sparse
`forecast_horizon_days ∈ {7,14,21}` target-date rows. It is **not** the V0.3-S2
materialized dataset `source-002/e5-live-v1`. S3-A must not treat sparse
7/14/21 binding rows as proof that a complete calendar daily curve already
exists.

### 1.4 Metric formula authority (reference only; do not mutate)

~~~text
V0_2_METRIC_CONTRACT_PATH=docs/forecast-quality/s3-quality-metrics-contract.md
METRIC_CONTRACT_AUTHORITY_BASE_SHA=b873dd63fc0d5b6375f94674abbd24a94d915f3c
S1_METRIC_CONTRACT_PATH=docs/v0-3/s1/metric-coverage-and-quality-contract.md
V0_3_METRIC_CONTRACT_VERSION=v0.3-metric-contract-v1
DO_NOT_MUTATE_V0_2_METRIC_CONTRACT=true
~~~

## 2. Terminology (not interchangeable)

Copied from V0.2 metric contract §2 without formula mutation:

~~~text
forecast_horizon_days
  = the lead time between forecast_cutoff_at and the target_date of a single
    binding row. Currently frozen at 7, 14, or 21.

evaluation_window_days
  = the length of the continuous target-date window required for a cumulative,
    single-day peak, or sustained peak metric. Currently frozen as 7, 14, or 21
    days depending on the requested horizon.

forecast_target_date
  = the calendar business date a single binding row is comparing against.

SPARSE_HORIZON_ROWS_ARE_NOT_COMPLETE_DAILY_CURVE=true
REQUESTED_HORIZONS_7_14_21_ARE_NOT_CONTINUOUS_CALENDAR_DAYS=true
~~~

`forecast_horizon_days` and `evaluation_window_days` are distinct concepts.
A 7-day forecast horizon is not the same as a complete 7-calendar-day daily
curve between cutoff and target.

## 3. Amendment scope and current status

### 3.1 What S3-A defines

S3-A defines the **operational contract** for expanding each evaluation
instance cell into a complete calendar daily row set:

~~~text
EVALUATION_INSTANCE_CELL_GRAIN=SEASON,FARM,SUBFARM,VARIETY,MODEL,FORECAST_CUTOFF,FORECAST_QUANTILE
~~~

For each cell and requested `evaluation_window_days`, the amendment specifies:

- calendar expansion rules
- per-day row status semantics
- actual kg sourcing from accepted S2 grains
- forecast replay requirements at historical cutoff
- window rejection rules for missing or unknown days
- completeness predicates for future verification

### 3.2 What S3-A does not do

~~~text
CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_S3_DAILY_ROWSET_CONTRACT_STATUS=NOT_AVAILABLE_FROM_CURRENT_S2_BINDING
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=true
S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED=true
AMENDMENT_MERGE_DOES_NOT_MATERIALIZE_ROWSET=true
AMENDMENT_MERGE_DOES_NOT_AUTHORIZE_BACKTEST=true
AMENDMENT_MERGE_DOES_NOT_MAKE_PEAK_METRICS_COMPUTABLE=true
MATERIALIZATION_GRANT_DOES_NOT_EXECUTE_MATERIALIZATION=true
~~~

Materialization is authorized by a separate grant package; this amendment
contract does not execute materialization. Completeness verification is
authorized by a separate grant package; this amendment contract does not execute
verification or flip `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. Until
materialization output is verified and accepted in a future closeout, peak and
cumulative metrics remain `NOT_COMPUTABLE` with
`reason_code=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING`. S3-A must
not substitute a different reason code implying a complete row set already
exists.

## 4. Missing-day policy

~~~text
MISSING_DAY_POLICY=UNKNOWN_NOT_ZERO
MISSING_DAY_ZERO_FILL=false
MISSING_ACTUAL_TREATED_AS_ZERO=false
NUMERIC_IMPUTATION_ALLOWED=false
~~~

Rules:

- A calendar day with no accepted S2 harvest grain is `UNKNOWN`, not `0` kg.
- `UNKNOWN` actual kg is `null` / absent; it must not be written as numeric zero.
- If any calendar day in a requested evaluation window is `UNKNOWN` or lacks an
  explicit daily row, the window is **REJECTED** and the metric cell is
  `NOT_COMPUTABLE`.
- `NOT_COMPUTABLE` is not zero error and not zero kg.

~~~text
WINDOW_REJECTION_ON_ANY_UNKNOWN_OR_MISSING_DAY=true
NOT_COMPUTABLE_IS_NOT_ZERO=true
~~~

## 5. Calendar expansion operational definition

For each evaluation instance cell
`(season, farm, subfarm, variety, model, forecast_cutoff, quantile)` and each
requested `evaluation_window_days` window within the TRAIN or VALIDATION
partition:

### 5.1 Window selection

All calendar-date arithmetic in this section uses `TIMEZONE=Asia/Shanghai`.
`HARVEST_BUSINESS_DATE` must not be used as `forecast_cutoff`.

#### 5.1.1 Horizon windows (`H ∈ {7,14,21}`)

For horizon-based evaluation where `evaluation_window_days = H`:

~~~text
TIMEZONE=Asia/Shanghai
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
cutoff_business_date = calendar date of forecast_cutoff_at in Asia/Shanghai
evaluation_window_start_date = cutoff_business_date + 1 day
evaluation_window_end_date   = cutoff_business_date + H days
WINDOW_INTERVAL=CLOSED_INCLUSIVE
WINDOW_CALENDAR_DAY_COUNT=H
CUTOFF_DAY_EXCLUDED_FROM_WINDOW=true
~~~

The evaluation window is a closed inclusive calendar-date range containing
exactly `H` calendar days. It starts the day after `cutoff_business_date` and
ends on `cutoff_business_date + H days`. The cutoff calendar day itself is not
included in the window.

Incumbent horizon consistency check:

~~~text
IF forecast_target_date EXISTS FOR horizon H:
  REQUIRED forecast_target_date = cutoff_business_date + H days
  ON_MISMATCH:
    metric_status=NOT_COMPUTABLE
    reason_code=TARGET_DATE_CUTOFF_HORIZON_MISMATCH
WINDOW_OR_HORIZON_REALIGNMENT_FORBIDDEN=true
~~~

If the incumbent model's `forecast_target_date` for horizon `H` exists and does
not equal `cutoff_business_date + H days`, the evaluation instance is
`NOT_COMPUTABLE` with `reason_code=TARGET_DATE_CUTOFF_HORIZON_MISMATCH`.
Adjusting the window boundaries or changing `H` to force alignment is forbidden.

#### 5.1.2 Complete-season window (`COMPLETE_SEASON`)

For complete-season cumulative and peak metrics over the default in-season scope:

~~~text
COMPLETE_SEASON_DEFAULT_MONTH_SCOPE=1-4
COMPLETE_SEASON_WINDOW_START=January 1 of SEASON year in Asia/Shanghai
COMPLETE_SEASON_WINDOW_END=April 30 of SEASON year in Asia/Shanghai
COMPLETE_SEASON_WINDOW_INTERVAL=CLOSED_INCLUSIVE
SEASON_YEAR_SOURCE=accepted S2 grain SEASON field
SEASON_YEAR_DERIVATION_FAILURE=NOT_COMPUTABLE
INVENTED_SEASON_YEAR_FORBIDDEN=true
FACTORY_BUILDING_AREA_AS_PEAK_FEATURE_FORBIDDEN=true
~~~

The `SEASON` year must be derived from the accepted S2 canonical grain `SEASON`
field. If the season year cannot be derived, the evaluation instance is
`NOT_COMPUTABLE`; inventing a season year is forbidden.

Factory building area must not be used as a peak-prediction feature.

#### 5.1.3 General window constraints

- Default season scope uses months 1–4 only, inherited from S2 exclusion policy.
- Sustained-peak sliding `n`-day windows are a second-stage operation inside an
  already-anchored evaluation window. They do not redefine the anchor window in
  §5.1.1 or §5.1.2.
- `PRODUCT_SUSTAINED_PEAK_WINDOW_DAYS=3` vs `PLAN_SUSTAINED_PEAK_WINDOW_DAYS=7`
  remains `UNRESOLVED`; this section does not choose `n`.

### 5.2 Per-calendar-day row requirement

Every calendar day in the window must have exactly one explicit daily row. Silent
omission of a calendar day is forbidden.

~~~text
SILENT_MISSING_CALENDAR_DAY_FORBIDDEN=true
EACH_CALENDAR_DAY_REQUIRES_EXPLICIT_ROW=true
~~~

### 5.3 Per-day status semantics

Each daily row carries `daily_row_status ∈ {OBSERVED, UNKNOWN, EXCLUDED}`.

| Status | Actual kg | Forecast kg | Metric use |
|---|---|---|---|
| `OBSERVED` | Decimal kg from accepted S2 grain | From incumbent replay at cutoff | eligible when forecast available |
| `UNKNOWN` | null / absent (not 0) | From replay if available; else unavailable | window REJECT if actual UNKNOWN |
| `EXCLUDED` | excluded by inherited S2 policy | not used in metrics | see cell-level vs day-level rules below |

#### 5.3.1 Cell-level EXCLUDED (no window generated)

Cell-level exclusion applies before window generation. If the evaluation
instance cell matches any inherited S2 exclusion, the entire cell is not
evaluated and **no evaluation window is generated**:

~~~text
CELL_LEVEL_EXCLUDED_NO_WINDOW_GENERATED=true
CELL_EXCLUDED_VARIETIES=普鲜,普青,普冻,废果
CELL_EXCLUDED_FACTORY_BASON=true
CELL_EXCLUDED_NON_1_4_MONTH_SCOPE=true
EXCLUSION_POLICY_REOPEN_FORBIDDEN=true
~~~

Cell-level exclusions include forbidden varieties, 巴松 factory, and evaluation
cells outside the default 1–4 month scope.

#### 5.3.2 Day-level EXCLUDED inside a generated window

If a generated evaluation window contains any calendar day with
`daily_row_status=EXCLUDED`, that day is treated the same as `UNKNOWN` for
window acceptance:

~~~text
DAY_LEVEL_EXCLUDED_IN_WINDOW=REJECT_WINDOW
EXCLUDED_DAY_IN_WINDOW_EQUALS_UNKNOWN_FOR_REJECTION=true
WINDOW_REJECTION_ON_ANY_EXCLUDED_DAY=true
EXCLUDED_HOLE_PUNCHING_FOR_PEAK_FORBIDDEN=true
PEAK_OVER_OBSERVED_DAYS_ONLY=false
DO_NOT_REDEFINE_PEAK_AS_MAX_OF_SPARSE_OBSERVED=true
~~~

Rules:

- A day-level `EXCLUDED` row inside an already-generated window causes the
  **entire window** to be **REJECTED** and the metric cell to be
  `NOT_COMPUTABLE`.
- Using `EXCLUDED` days to punch holes in the window and then taking the
  maximum over the remaining observed days is forbidden.
- `PEAK_OVER_OBSERVED_DAYS_ONLY=false` remains binding.

While `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false`, window rejection
for incomplete rowsets must still publish
`reason_code=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING`. S3-A1 must
not substitute `NO_COMPLETE_NDAY_WINDOW` before completeness verification.

~~~text
DEFAULT_MONTH_SCOPE=1-4
EXCLUSION_POLICY_REOPEN_FORBIDDEN=true
~~~

### 5.4 Actual side (OBSERVED)

- `OBSERVED` kg may come only from accepted S2 TRAIN/VALIDATION grains at
  `CANONICAL_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE`.
- Units are `kg`, stored and aggregated as `Decimal`; float accumulation is
  forbidden.
- No reread of xls, Google Sheets, S1 derived JSON, PIT tables, or old-winner
  tables as SOURCE_002 primary input.

### 5.5 Forecast side (incumbent replay)

- Forecasts must come from `V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF`.
- For each calendar day in the window, the incumbent model must be replayed with
  only information visible at `forecast_cutoff`.
- If a calendar day has no legal forecast under cutoff visibility, that day is
  `FORECAST_UNAVAILABLE`; the window is **REJECTED** and the metric is
  `NOT_COMPUTABLE`.
- `FORECAST_UNAVAILABLE` is not numeric zero.

~~~text
FORECAST_UNAVAILABLE_IS_NOT_ZERO=true
FINAL_SEASON_FACTS_AT_CUTOFF_FORBIDDEN=true
~~~

### 5.6 Peak definition guardrails

Peak metrics must use the complete calendar daily row set inside the evaluation
window. Redefining peak as the maximum over observed sparse days only is
forbidden.

~~~text
PEAK_OVER_OBSERVED_DAYS_ONLY=false
DO_NOT_REDEFINE_PEAK_AS_MAX_OF_SPARSE_OBSERVED=true
SINGLE_DAY_PEAK_REQUIRES_COMPLETE_DAILY_ROWSET=true
SUSTAINED_PEAK_REQUIRES_COMPLETE_DAILY_ROWSET=true
~~~

## 6. Pairing and reporting grains

Aligned with development-plan §4.4 and V0.2 metric contract §11:

~~~text
GROUPING_GRAIN=SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_TARGET_DATE_X_FORECAST_CUTOFF_X_MODEL_IDENTITY_X_FORECAST_QUANTILE
REPORTING_GRAIN=SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_HARVEST_BUSINESS_DATE
Q2C_TARGET=OBSERVED_FARM_PICK_QUANTITY
ACTUAL_UNIT=kg
DECIMAL_ARITHMETIC_REQUIRED=true
FLOAT_ACCUMULATION_FORBIDDEN=true
~~~

Evaluation partitions:

~~~text
S3_EVALUATION_PARTITIONS=TRAIN,VALIDATION
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
EXTERNAL_HOLDOUT_NOT_APPLICABLE=true
RANDOM_ADJACENT_DATE_SPLIT_FORBIDDEN=true
~~~

## 7. Metric computability under this amendment

S3-A defines computability rules only. It does not compute metrics.

### 7.1 Daily point metrics (not blocked by complete daily rowset)

Per V0.2 metric contract §6:

~~~text
DAILY_POINT_METRICS=daily_mae,daily_wape,daily_smape
DAILY_POINT_METRICS_BLOCKED_BY_COMPLETE_DAILY_ROWSET=false
DAILY_POINT_METRICS_REQUIRE_VALID_PAIRING=true
PAIRING_FAILURE_STATUS=NOT_COMPUTABLE
PAIRING_FAILURE_IS_NOT_ZERO=true
~~~

Daily point metrics run only on legal `OBSERVED` actual ∩ legal forecast pairs.
Pairing failure is `NOT_COMPUTABLE`, not zero error.

### 7.2 Peak, cumulative, and complete-horizon metrics

Until `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=true`:

~~~text
SINGLE_DAY_PEAK_STATUS=NOT_COMPUTABLE
SEASON_CUMULATIVE_STATUS=NOT_COMPUTABLE
COMPLETE_HORIZON_STATUS=NOT_COMPUTABLE
SUSTAINED_PEAK_STATUS=NOT_COMPUTABLE
BLOCKER_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
NOT_COMPUTABLE_IS_NOT_ZERO=true
~~~

S3-A must not claim these metrics are computable in this PR.

### 7.3 Quantile coverage (S3-B gate)

~~~text
P80_COVERAGE_COMPUTABLE=false
P90_COVERAGE_COMPUTABLE=false
QUANTILE_SEMANTICS_GATE=S3-B
S3_A_DOES_NOT_CLAIM_COVERAGE_COMPUTABLE=true
COVERAGE_BLOCKED_BY_QUANTILE_SEMANTICS_NOT_VERIFIED=true
~~~

### 7.4 Sustained peak window conflict (UNRESOLVED)

~~~text
PRODUCT_SUSTAINED_PEAK_WINDOW_DAYS=3
PLAN_SUSTAINED_PEAK_WINDOW_DAYS=7
V0_2_METRIC_ID=SUSTAINED_7DAY_PEAK
P0_SUSTAINED_PEAK_WINDOW_CONFLICT=UNRESOLVED
S3_A_DOES_NOT_RESOLVE_3_VS_7=true
SUSTAINED_PEAK_PASS_FORBIDDEN_UNTIL_OWNER_DECISION=true
~~~

S3-A may define completeness predicates for both 3-day and 7-day sustained
windows, but must not choose a product winner. Until owner decision:

~~~text
SUSTAINED_3DAY_COMPLETENESS_PREDICATE_DEFINED=true
SUSTAINED_7DAY_COMPLETENESS_PREDICATE_DEFINED=true
SUSTAINED_PEAK_METRIC_PASS_FORBIDDEN=true
~~~

### 7.5 Sustained peak reason-code ordering (V0.2 mutual exclusivity)

Per V0.2 metric contract and development-plan §4.4:

~~~text
SUSTAINED_PEAK_STAGE_ORDER=ROWSET_AVAILABILITY_THEN_WINDOW_AVAILABILITY
SUSTAINED_PEAK_STAGE_2_ALLOWED_ONLY_AFTER_STAGE_1_PASS=true
SUSTAINED_PEAK_STAGE_REASONS_MUTUALLY_EXCLUSIVE=true
WHEN_COMPLETE_DAILY_ROWSET_UNAVAILABLE:
  SUSTAINED_PEAK_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
WHEN_COMPLETE_DAILY_ROWSET_AVAILABLE_BUT_NO_COMPLETE_NDAY_WINDOW:
  SUSTAINED_PEAK_REASON_CODE=NO_COMPLETE_NDAY_WINDOW
MISSING_ROWSET_NEVER_RELABELED_AS_MISSING_WINDOW=true
~~~

While `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false`, only the rowset
blocker reason may be published. S3-A must not emit `NO_COMPLETE_7DAY_WINDOW`
or `NO_COMPLETE_3DAY_WINDOW` before rowset completeness is verified.

## 8. Daily rowset identity schema (sentinels only)

Per V0.2 metric contract §2 identity fields. S3-A binds schema and explicit
sentinels only. No materialized hash may be invented in this task.

~~~text
S3_DAILY_ROW_SET_AUTHORITY=V0_3_S3_DAILY_ROWSET_AMENDMENT
S3_DAILY_ROW_SET_IDENTITY=NOT_MATERIALIZED
S3_DAILY_ROW_SET_HASH=NOT_MATERIALIZED
S3_DAILY_ROW_SET_START_DATE=NOT_MATERIALIZED
S3_DAILY_ROW_SET_END_DATE=NOT_MATERIALIZED
S3_DAILY_ROW_SET_EXPECTED_DAY_COUNT=NOT_MATERIALIZED
S3_DAILY_ROW_SET_ACTUAL_DAY_COUNT=NOT_MATERIALIZED
S3_DAILY_ROW_SET_COMPLETENESS_STATUS=BLOCKED_PENDING_MATERIALIZATION_AND_VERIFICATION
DO_NOT_INVENT_MATERIALIZED_HASH=true
~~~

### 8.1 Completeness predicate (defined, not verified)

Future completeness verification must prove, for each evaluation instance cell
and requested window:

~~~text
COMPLETENESS_PREDICATE_1=FULL_CALENDAR_DAY_COVERAGE_IN_WINDOW
COMPLETENESS_PREDICATE_2=NO_SILENT_MISSING_DAYS
COMPLETENESS_PREDICATE_3=NO_ZERO_FILL_FOR_UNKNOWN
COMPLETENESS_PREDICATE_4=OBSERVED_KG_TRACEABLE_TO_SOURCE_002_GRAIN
COMPLETENESS_PREDICATE_5=FORECAST_DAILY_CURVE_VISIBLE_AT_CUTOFF
COMPLETENESS_VERIFICATION_STATUS=NOT_PERFORMED
~~~

This PR does not claim any predicate has passed.

## 9. Forbidden inputs (inherited from P0)

~~~text
FORBIDDEN_REREAD_XLS=true
FORBIDDEN_REREAD_GOOGLE_SHEETS=true
FORBIDDEN_S1_DERIVED_JSON_AS_PRIMARY_INPUT=true
FORBIDDEN_FACTORY_BASON=true
FORBIDDEN_VARIETIES=普鲜,普青,普冻,废果
FORBIDDEN_PIT_TABLE_AS_SOURCE_002_PRIMARY=true
FORBIDDEN_OLD_WINNER_TABLE_AS_SOURCE_002_PRIMARY=true
FORBIDDEN_TEST_PLACEHOLDER_AS_EVALUATION_ROWS=true
FORBIDDEN_FINAL_SEASON_FACTS_AT_HISTORICAL_CUTOFF=true
FORBIDDEN_UNGOVERNED_MASTER_DATA=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 10. Subtask boundaries

~~~text
S3_A_DAILY_ROWSET_AMENDMENT_CONTRACT_AUTHORIZED=true
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=true
S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED=true
S3_B_AUTHORIZED=false
S3_C_AUTHORIZED=false
S3_D_AUTHORIZED=false
next_subtask_not_implied=true
NO_STEP_IMPLIES_THE_NEXT=true
~~~

| Subtask | Status after S3-A merge |
|---|---|
| S3-A contract | frozen (this document) |
| S3-A materialization | authorized (grant only; not executed) |
| S3-A completeness verification | authorized (grant only; not executed) |
| S3-B quantile semantics | not authorized |
| S3-C backtest execution | not authorized |
| S3-D error attribution | not authorized |

## 11. LLM and deterministic service boundary

~~~text
LLM_MUST_NOT_INVENT_TONNES=true
ALL_TONNAGE_FROM_DETERMINISTIC_SERVICE=true
DETERMINISTIC_DAILY_ROWSET_SERVICE_IMPLEMENTED=true
DETERMINISTIC_COMPLETENESS_VERIFICATION_SERVICE_IMPLEMENTED=true
METRIC_EXECUTION_IMPLEMENTED=false
~~~

LLM agents must not invent kg values, row counts, completeness results, or
materialized hashes. Those must come from separately authorized deterministic
services after materialization is authorized.

## 12. Amendment closeout pointer

~~~text
S3_A_AMENDMENT_CLOSEOUT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a-amendment-closeout.md
S3_A_AMENDMENT_CLOSEOUT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a-amendment-closeout.json
EVIDENCE_JSON_SHA256=7ce9c1bf1c2eee9a3cd0d6176d6a31466e308bd991ab206cf0285967c68523ef
CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=true
CLOSEOUT_MERGE_DOES_NOT_AUTHORIZE_MATERIALIZATION=true
~~~

## 13. Rowset materialization authorization pointer

~~~text
S3_A_ROWSET_MATERIALIZATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a-rowset-materialization-authorization.md
S3_A_ROWSET_MATERIALIZATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a-rowset-materialization-authorization.json
EVIDENCE_JSON_SHA256=df66d59383d3bdf76e7db6fdc32b21b2f41237ef3072f8a1ac76205ddc4d6239
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=true
S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
MATERIALIZATION_AUTH_MERGE_DOES_NOT_EXECUTE_MATERIALIZATION=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

Live `S3_A_ROWSET_MATERIALIZATION_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and this authorization package. Identity
sentinels remain `NOT_MATERIALIZED` until a separately gated implementation
run computes them.

Live `CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE` authority:
`docs/v0-3/development-plan.md` §4.4. Frozen snapshots in S1, S3-B, and S3-C0
contract files remain historical; they are not overwritten by this closeout.

## 14. Completeness verification authorization pointer

~~~text
S3_A_COMPLETENESS_VERIFICATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a-completeness-verification-authorization.md
S3_A_COMPLETENESS_VERIFICATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a-completeness-verification-authorization.json
EVIDENCE_JSON_SHA256=783bfac0259393f052996de7f8cb43c74512d7062d2725083c9dcade0253ffdc
S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
AUTHORIZATION_MERGE_DOES_NOT_EXECUTE_VERIFICATION=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

Live `S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and this authorization package.
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED` may flip only in a future
coordinator-reviewed verification closeout, not in this authorization grant.
Identity sentinels may remain `NOT_MATERIALIZED` until verification output is
accepted.

## 15. Evaluation instance registry contract pointer

~~~text
S3_A2_EVALUATION_INSTANCE_REGISTRY_CONTRACT_PATH=docs/v0-3/s3/s3-evaluation-instance-registry-contract.md
S3_A2_EVALUATION_INSTANCE_REGISTRY_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-evaluation-instance-registry.md
S3_A2_EVALUATION_INSTANCE_REGISTRY_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-evaluation-instance-registry.json
EVIDENCE_JSON_SHA256=e4b1c86e890de1106c018e130920a0ad4005de631a47c6c34435fcab10148aa4
S3_A2_EVALUATION_INSTANCE_REGISTRY_CONTRACT_AUTHORIZED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=NOT_PERFORMED
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_REGISTRY=true
NO_STEP_IMPLIES_THE_NEXT=true
~~~

Live `S3_A2_EVALUATION_INSTANCE_REGISTRY_CONTRACT_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and this contract package.
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE` may flip only after a separately gated
registry implementation and coordinator-reviewed closeout.
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED` may flip only after dataset-wide
verification closeout, not in this contract freeze.

## 16. Evaluation instance registry implementation authorization pointer

~~~text
S3_A2_REGISTRY_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-registry-implementation-authorization.md
S3_A2_REGISTRY_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-registry-implementation-authorization.json
EVIDENCE_JSON_SHA256=9e8031f4efc06084dd4ee783943b76d47bbd31bd54ed1976853cf2e79e5eda2a
S3_A2_EVALUATION_INSTANCE_REGISTRY_IMPLEMENTATION_AUTHORIZED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
AUTHORIZATION_MERGE_DOES_NOT_EXECUTE_REGISTRY=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

Live `S3_A2_EVALUATION_INSTANCE_REGISTRY_IMPLEMENTATION_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and this authorization package.
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE` may flip only in a future
coordinator-reviewed registry closeout, not in this authorization grant.
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED` may flip only after dataset-wide
verification closeout.

## 17. Evaluation instance registry implementation pointer

~~~text
S3_A2_REGISTRY_IMPLEMENTATION_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-registry-implementation-r1.md
S3_A2_REGISTRY_IMPLEMENTATION_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-registry-implementation-r1.json
EVIDENCE_JSON_SHA256=8fe740675e0dbe0ad3a4a4c85a5786262877d12fd2c8e704899bef8ffda2f43e
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
IMPLEMENTATION_R1_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_R1_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
~~~

Live `EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED` authority:
`docs/v0-3/development-plan.md` §4.4 and this implementation package.
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE` may flip only in a future
coordinator-reviewed registry closeout, not in R1 implementation.

## 18. Evaluation instance catalog binding contract pointer

~~~text
S3_A2_CATALOG_BINDING_CONTRACT_PATH=docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md
S3_A2_CATALOG_BINDING_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-catalog-binding-contract.md
S3_A2_CATALOG_BINDING_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-catalog-binding-contract.json
EVIDENCE_JSON_SHA256=1122134e91610eb88c5521fce3ffe76d4e7e9a05ff02b8c719cf8459daac2a4b
S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_CONTRACT_AUTHORIZED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CONTRACT_MERGE_DOES_NOT_BIND_CATALOG=true
BINDING_IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

Live `S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_CONTRACT_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and this catalog binding contract package.
This contract defines how a future catalog may be bound; it does not bind one or
flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`.

## 19. Evaluation instance catalog binding implementation authorization pointer

~~~text
S3_A2_CATALOG_BINDING_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-catalog-binding-authorization.md
S3_A2_CATALOG_BINDING_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-catalog-binding-authorization.json
EVIDENCE_JSON_SHA256=22b8e4bd0c8d530008afd42b3f9213f4c47b4870b5709576ea7993725cf9f379
S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_IMPLEMENTATION_AUTHORIZED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
AUTHORIZATION_MERGE_DOES_NOT_BIND_CATALOG=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

Live `S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_IMPLEMENTATION_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and this authorization package.
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE` may flip only in a future
coordinator-reviewed registry closeout, not in this authorization grant.
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED` may flip only after dataset-wide
verification closeout.

## 20. Evaluation instance catalog binding implementation pointer

~~~text
S3_A2_CATALOG_BINDING_IMPLEMENTATION_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-catalog-binding-implementation-r1.md
S3_A2_CATALOG_BINDING_IMPLEMENTATION_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-catalog-binding-implementation-r1.json
EVIDENCE_JSON_SHA256=d86ad33cba6299a1b58a28598d82a90b20b53fb73700e037919698e89ef24ae5
DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_BINDING_SERVICE_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
IMPLEMENTATION_R1_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_R1_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
~~~

Live `DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_BINDING_SERVICE_IMPLEMENTED` authority:
`docs/v0-3/development-plan.md` §4.4 and this implementation package.
R1 delivers the in-memory structural validator only; it does not bind a live
catalog or flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`.

## 21. Evaluation instance catalog artifact contract pointer

~~~text
S3_A2_CATALOG_ARTIFACT_CONTRACT_PATH=docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md
S3_A2_CATALOG_ARTIFACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-catalog-artifact-contract.md
S3_A2_CATALOG_ARTIFACT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-catalog-artifact-contract.json
EVIDENCE_JSON_SHA256=501dcf1034e615f60ca9b76b79cbbe8f9d352c3ea85abf4380d763842ddd4ca6
S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_CONTRACT_AUTHORIZED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CONTRACT_MERGE_DOES_NOT_PRODUCE_CATALOG=true
CONTRACT_MERGE_DOES_NOT_BIND_CATALOG=true
NO_STEP_IMPLIES_THE_NEXT=true
~~~

Live `S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_CONTRACT_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and this catalog artifact contract package.
This contract defines how a future catalog artifact may be produced; it does not
produce one or flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`.

## 22. Evaluation instance catalog artifact production authorization pointer

~~~text
S3_A2_CATALOG_ARTIFACT_PRODUCTION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-catalog-artifact-authorization.md
S3_A2_CATALOG_ARTIFACT_PRODUCTION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-catalog-artifact-authorization.json
EVIDENCE_JSON_SHA256=427dbc4534c9537dbe168e0283644952d82606a481ad0142227dcf7693c9fc09
S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_PRODUCTION_AUTHORIZED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_BIND_CATALOG=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED` may flip only after dataset-wide
verification closeout.

## 23. Evaluation instance catalog artifact production R1 pointer

~~~text
S3_A2_CATALOG_ARTIFACT_PRODUCTION_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-catalog-artifact-production-r1.md
S3_A2_CATALOG_ARTIFACT_PRODUCTION_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-catalog-artifact-production-r1.json
EVIDENCE_JSON_SHA256=a776e557c06e7c31787b9824dedc69735f0143b9a221334a72452ea443cb9dbc
DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_ARTIFACT_SERVICE_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
IMPLEMENTATION_MERGE_DOES_NOT_PRODUCE_LIVE_BINDABLE_CATALOG=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
~~~

Live `DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_ARTIFACT_SERVICE_IMPLEMENTED` is
maintained in `docs/v0-3/development-plan.md` §4.4 and this R1 package.
This pointer does not rewrite amendment freeze rules in §§1–21.

## 24. Incumbent forecast artifact contract pointer

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md
S3_A2_INCUMBENT_FORECAST_ARTIFACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-contract.md
S3_A2_INCUMBENT_FORECAST_ARTIFACT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-contract.json
EVIDENCE_JSON_SHA256=8e19a623c6739abeb047768ef642281b86ac7f2d73ea35fcff83ae3165f40376
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_AUTHORIZED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CONTRACT_MERGE_DOES_NOT_PRODUCE_FORECAST_ARTIFACT=true
CONTRACT_MERGE_DOES_NOT_PRODUCE_CATALOG=true
CONTRACT_MERGE_DOES_NOT_BIND_CATALOG=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
NO_STEP_IMPLIES_THE_NEXT=true
~~~

Live `S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and this incumbent forecast artifact contract package.
This contract defines how a future versioned forecast input artifact may be identified
and accepted; it does not implement an adapter, write forecast artifacts, produce
catalogs, or flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`.

## 25. Incumbent forecast artifact implementation authorization pointer

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-authorization.md
S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-authorization.json
EVIDENCE_JSON_SHA256=1928d044d85c9dbff3c71d14551409c9c61404ed84174f20979fbc31ba6fae00
S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTHORIZED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_FORECAST_ARTIFACT=true
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_BIND_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_ADAPTER=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
NO_STEP_IMPLIES_THE_NEXT=true
~~~

Live `S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and this implementation authorization package.
This grant records what a later deterministic adapter may do; it does not implement
an adapter, write forecast artifacts, produce catalogs, or flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`.

## 26. S2 identity alignment contract pointer

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-contract.md
S3_A2_S2_IDENTITY_ALIGNMENT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-contract.md
S3_A2_S2_IDENTITY_ALIGNMENT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-contract.json
EVIDENCE_JSON_SHA256=077d43f436113fce0228f06f2756a54f0f88cc1dad8378793f468fbe64f5634c
S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=false
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_ALIGNMENT_ADAPTER=true
CONTRACT_MERGE_DOES_NOT_PRODUCE_CATALOG=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
NO_STEP_IMPLIES_THE_NEXT=true
~~~

Live `S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and this S2 identity alignment contract package.
This contract defines how a future alignment adapter may project accepted S2 identities;
it does not implement an adapter, produce catalogs, or flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`.

## 26. Incumbent forecast artifact adapter R1 pointer

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_ADAPTER_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-adapter-r1.md
S3_A2_INCUMBENT_FORECAST_ARTIFACT_ADAPTER_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-adapter-r1.json
EVIDENCE_JSON_SHA256=31bb6d24cf4c398eeea86c18d2dece16b9e0ab6f704e9ab229eac5a363d296a0
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTHORIZED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
IMPLEMENTATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
~~~

Live `DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and this R1 package.
This pointer does not rewrite amendment freeze rules in §§1–21.
