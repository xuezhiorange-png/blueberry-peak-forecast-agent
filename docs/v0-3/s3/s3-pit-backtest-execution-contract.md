# V0.3-S3-C0 Point-in-Time Backtest Execution Contract

## Contract identity and phase boundary

~~~text
CONTRACT_ID=V0_3_S3_C0_PIT_BACKTEST_EXECUTION_CONTRACT
CONTRACT_VERSION=v0-3-s3-c0-pit-backtest-execution-contract-v1
TASK_ID=V03_S3_C0_PIT_BACKTEST_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_C0_PIT_BACKTEST_CONTRACT_ONLY
SLICE=V0.3-S3
PARALLEL_LANE=S3-C0
ENGLISH_ID=CURRENT_MODEL_POINT_IN_TIME_BACKTEST_AND_ERROR_DIAGNOSIS
USER_GATE=可以下一步 并行开发
CONTRACT_ONLY=true
BASE_MAIN_SHA=fd793de12bfe2df646925d9e7adc1d59c046ecdf
BASE_MAIN_TREE_SHA=61d8550f1311e3c0949f5bf08814fc69ddf0fde5
BASE_REF=origin/main
PARENT_CONTRACT_ID=V0_3_S3_BACKTEST_AND_DIAGNOSIS_CONTRACT
PARENT_CONTRACT_VERSION=v0-3-s3-backtest-and-diagnosis-contract-v1
PARENT_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
PARENT_CONTRACT_GIT_BLOB_SHA=45f900f4dfa1ef5da8ea898a39bdded4c8c11f08
PARENT_CONTRACT_SHA256=490f48cde5fd7543f2d7608b0dff388c9a7f99f44d77ed4337f55331e950d7a8
P0_PR=298
P0_MERGE=0a6f412aad63e1f66a5e14e5960ca88deb9b2dcd
S3_A_AMENDMENT_ID=V0_3_S3_DAILY_ROWSET_AMENDMENT
S3_A_AMENDMENT_VERSION=v0-3-s3-daily-rowset-amendment-v1
S3_A_AMENDMENT_PATH=docs/v0-3/s3/s3-daily-rowset-amendment.md
S3_A_AMENDMENT_GIT_BLOB_SHA=1baf930287598f5df78ac28d49c159b4231c0fc6
S3_A_AMENDMENT_SHA256=f2b2473bd7ebe52349010403cbcc45a8a18f3ae7ad3512c97d8b2a30b205a7be
S3_A_PR=299
S3_A_MERGE=fd793de12bfe2df646925d9e7adc1d59c046ecdf
REVIEWER_ROLE=COORDINATOR
USER_WAIVED_THIRD_PARTY_REVIEW=true
COORDINATOR_REVIEW_COUNTS=true
NO_STEP_IMPLIES_THE_NEXT=true
~~~

~~~text
S3_C0_PIT_BACKTEST_CONTRACT_AUTHORIZED=true
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=false
S3_D_AUTHORIZED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
SOURCE_002_ROW_LEVEL_READ=false
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
ALLOWLIST_EXPANSION_AUTHORIZED=false
V0_3_S4_AUTHORIZED=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
DO_NOT_CONFLATE_V0_2_S2_IMMUTABLE_BACKTEST_BINDING_WITH_V0_3_S2_DATASET=true
LLM_MUST_NOT_INVENT_TONNES=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This document freezes the V0.3-S3-C0 point-in-time (PIT) backtest **execution
contract** for TRAIN and VALIDATION partitions only. It defines how a future
authorized runner must reconstruct forecast inputs, pair actuals, record
exclusions and failures, and emit versioned diagnostics. It is a governance
contract, not a backtest run, metric execution, runner implementation, or
acceptance result.

Merging this contract does **not** authorize backtest execution, metric
computation, TEST evaluation, production or test code, or allowlist PASS.
`S3_C_BACKTEST_EXECUTION_AUTHORIZED` remains `false` after merge.

## 1. Inherited authority (not reopened)

### 1.1 Parent S3 P0 contract

~~~text
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
P0_CONTRACT_VERSION=v0-3-s3-backtest-and-diagnosis-contract-v1
P0_EVIDENCE_JSON_SHA256=580f09e306e4e32db0e72d65158d455bd9fea57b4279497909ff0d54cb91259c
V0_3_S3_PHASE_ENTRY_AUTHORIZED=true
~~~

### 1.2 S3-A daily rowset amendment (accepted on main)

~~~text
S3_A_AMENDMENT_PATH=docs/v0-3/s3/s3-daily-rowset-amendment.md
S3_A_AMENDMENT_VERSION=v0-3-s3-daily-rowset-amendment-v1
S3_A_EVIDENCE_JSON_SHA256=b50948c9529dd7f87b844e61e48fbb3b89d6eae31211f43d6fc5189360553e0a
CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_S3_DAILY_ROWSET_CONTRACT_STATUS=NOT_AVAILABLE_FROM_CURRENT_S2_BINDING
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
~~~

S3-C0 inherits S3-A missing-day, calendar-expansion, and metric-computability
semantics. It does not reopen S3-A materialization or completeness
verification.

### 1.3 S2 materialized dataset (accepted)

~~~text
S2_CONTRACT_PATH=docs/v0-3/s2/s2-materialized-dataset-contract.md
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_ROW_COUNT=16224
VALIDATION_ROW_COUNT=8006
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
CANONICAL_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
SOURCE_002_VISIBILITY_PRIMARY_PATH=IDFL_LABEL_SIDE
PIT_SQL_COUNT_EXPECTED=0
OLD_WINNER_SQL_COUNT_EXPECTED=0
~~~

### 1.4 V0.3-S3 input authorities (distinct; do not conflate)

~~~text
V0_3_S3_ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
V0_3_S3_VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
V0_2_S3_INPUT_AUTHORITY_HISTORICAL=S2_IMMUTABLE_BACKTEST_BINDING
DO_NOT_CONFLATE_V0_2_S2_IMMUTABLE_BACKTEST_BINDING_WITH_V0_3_S2_DATASET=true
~~~

The V0.2 metric contract names `S3_INPUT_AUTHORITY=S2_IMMUTABLE_BACKTEST_BINDING`
for the V0.2 engineering trial pairing. That artifact is **not** the V0.3-S2
materialized dataset `source-002/e5-live-v1`. S3-C0 must not conflate these
authorities.

### 1.5 Metric formula authority (reference only; do not mutate)

~~~text
V0_2_METRIC_CONTRACT_PATH=docs/forecast-quality/s3-quality-metrics-contract.md
METRIC_CONTRACT_AUTHORITY_BASE_SHA=b873dd63fc0d5b6375f94674abbd24a94d915f3c
S1_METRIC_CONTRACT_PATH=docs/v0-3/s1/metric-coverage-and-quality-contract.md
V0_3_METRIC_CONTRACT_VERSION=v0.3-metric-contract-v1
DO_NOT_MUTATE_V0_2_METRIC_CONTRACT=true
~~~

## 2. Execution scope

### 2.1 Permitted evaluation partitions

S3-C0 defines execution rules for **TRAIN + VALIDATION only**.

~~~text
S3_EVALUATION_PARTITIONS=TRAIN,VALIDATION
S3_TRAIN_ROW_COUNT=16224
S3_VALIDATION_ROW_COUNT=8006
RANDOM_ADJACENT_DATE_SPLIT_FORBIDDEN=true
TIME_ORDERED_SPLIT_INHERITED_FROM_S1=true
~~~

Random splitting of adjacent dates as the primary validation method is
forbidden.

### 2.2 TEST partition (sealed)

~~~text
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
TEST_IS_SEALED_PLACEHOLDER=true
TEST_ROW_COUNT_ZERO_IS_NOT_EVALUATION_FAILURE=true
FORBIDDEN_TEST_PLACEHOLDER_AS_EVALUATION_ROWS=true
~~~

`TEST.row_count=0` and `TEST.byte_count=240` are identity bindings only. They
are not evaluation rows and must not be reported as backtest failure.

### 2.3 External holdout

~~~text
EXTERNAL_HOLDOUT_NOT_APPLICABLE=true
EXTERNAL_HOLDOUT_OWNER_DECISION=REVIEWED_NOT_FEASIBLE
EXTERNAL_HOLDOUT_BYTES_EXIST=false
DO_NOT_CLAIM_HOLDOUT_BYTES_EXIST=true
~~~

## 3. Point-in-time forecast input reconstruction

Inherited from development-plan §4.4 and P0 §8.

### 3.1 Cutoff visibility rule

For each historical `FORECAST_CUTOFF_AT`, every forecast input row must satisfy:

~~~text
FORECAST_INPUT_ELIGIBILITY_RULE=SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT
FORECASTS_MUST_USE_HISTORICAL_CUTOFF_VISIBILITY=true
FORECAST_CUTOFF_AUTHORITY=EXACT_FORECAST_CUTOFF_AT
FORECAST_TARGET_RELATION=FORECAST_CUTOFF_AT_STRICTLY_BEFORE_FORECAST_TARGET_DATE_OR_WINDOW_END
~~~

Rows with `SOURCE_AVAILABLE_AT > FORECAST_CUTOFF_AT` are ineligible and must
not enter the forecast input set. If a required input cannot be reconstructed
under this rule, the backtest instance is `BLOCKED` or the affected metric cell
is `NOT_COMPUTABLE`; it must not be silently omitted or zero-filled.

### 3.2 Forbidden historical input construction

The following are explicitly forbidden when reconstructing forecast inputs at a
historical cutoff:

~~~text
FORBIDDEN_FINAL_SEASON_FACTS_AT_HISTORICAL_CUTOFF=true
FORBIDDEN_FUTURE_REVISIONS_AT_HISTORICAL_CUTOFF=true
FORBIDDEN_LATER_LABELS_FOR_HISTORICAL_INPUT=true
FORBIDDEN_POST_SEASON_YIELD_IN_PRE_SEASON_INPUT=true
FORBIDDEN_RETROSPECTIVE_PHENOLOGY_IN_EARLIER_FORECAST=true
FORBIDDEN_POST_EVENT_WEATHER_REPLACING_CUTOFF_FORECAST=true
FORBIDDEN_POST_SEASON_MARKETABLE_RATE_IN_PRE_SEASON_INPUT=true
FORBIDDEN_TEST_LABELS_IN_TRAIN_OR_VALIDATION_EXECUTION=true
FORBIDDEN_UNGOVERNED_MASTER_DATA=true
~~~

### 3.3 Forecast authority

~~~text
EVALUATED_MODEL=V0_2_CURRENT_INCUMBENT
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
~~~

Forecasts must come from the incumbent V0.2 model replayed at each historical
cutoff with only cutoff-visible inputs. S3-C0 does not authorize model or
parameter changes.

## 4. Actual pairing and visibility

### 4.1 IDFL label-side authority

Actual pairing for SOURCE_002 uses **IDFL label-side** visibility, not PIT or
old-winner tables.

~~~text
V0_3_S3_VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
ACTUAL_PAIRING_VISIBILITY_PATH=IDFL_LABEL_SIDE
FORBIDDEN_PIT_TABLE_AS_SOURCE_002_PRIMARY=true
FORBIDDEN_OLD_WINNER_TABLE_AS_SOURCE_002_PRIMARY=true
PIT_SQL_COUNT_EXPECTED=0
OLD_WINNER_SQL_COUNT_EXPECTED=0
~~~

`PIT_SQL=0` and `OLD_WINNER_SQL=0` on SOURCE_002 are expected boundary
oracles. Using `s2_pit_visibility_decision` or `s2_revision_winner_decision` as
the primary SOURCE_002 actual-pairing path is forbidden.

### 4.2 Separate visibility domains

Forecast-input visibility and label-observation visibility are separate
boundaries and must not be substituted for one another.

~~~text
FORECAST_INPUT_VISIBILITY_DOMAIN=FORECAST_INPUT
ACTUAL_LABEL_VISIBILITY_DOMAIN=LABEL_OBSERVATION
FORECAST_INPUT_VISIBILITY_POLICY_REUSED_FOR_ACTUAL_LABEL=false
~~~

### 4.3 Pairing grain

~~~text
GROUPING_GRAIN=SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_TARGET_DATE_X_FORECAST_CUTOFF_X_MODEL_IDENTITY_X_FORECAST_QUANTILE
REPORTING_GRAIN=SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_HARVEST_BUSINESS_DATE
Q2C_TARGET=OBSERVED_FARM_PICK_QUANTITY
ACTUAL_UNIT=kg
DECIMAL_ARITHMETIC_REQUIRED=true
FLOAT_ACCUMULATION_FORBIDDEN=true
~~~

Pairing failure yields `NOT_COMPUTABLE`. It must not be reported as zero error or
zero kg.

~~~text
PAIRING_FAILURE_STATUS=NOT_COMPUTABLE
PAIRING_FAILURE_IS_NOT_ZERO=true
PAIRING_FAILURE_MUST_BE_RECORDED=true
~~~

## 5. Evaluation window anchor (S3-A1 pending)

The evaluation-window calendar anchor is owned by S3-A1. Until S3-A1 is merged
and accepted, S3-C0 binds only a **pending reference**:

~~~text
S3_A1_EVALUATION_WINDOW_ANCHOR_STATUS=PENDING_NOT_MERGED
S3_A1_PENDING_WINDOW_ANCHOR=cutoff+1 … cutoff+H
S3_C0_MUST_NOT_INVENT_ALTERNATE_WINDOW_ANCHOR=true
S3_C0_MUST_NOT_FIX_H_WITHOUT_S3_A1=true
~~~

Rules:

- The inclusive calendar evaluation window is anchored from the day after
  `FORECAST_CUTOFF_AT` through `FORECAST_CUTOFF_AT + H` calendar days, where
  `H` is the horizon parameter frozen by S3-A1.
- S3-C0 must not select a different anchor (for example target-date-only sparse
  rows, harvest-business-date without cutoff offset, or ad hoc season endpoints).
- When S3-A1 merges, future execution must bind the exact anchor definition from
  that contract without reinterpretation.

## 6. Missing-day, exclusion, and coverage recording

### 6.1 Missing-day semantics

~~~text
MISSING_DAY_POLICY=UNKNOWN_NOT_ZERO
MISSING_DAY_ZERO_FILL=false
MISSING_ACTUAL_TREATED_AS_ZERO=false
NUMERIC_IMPUTATION_ALLOWED=false
~~~

A missing harvest day is unknown, not zero. Silent zero-fill is forbidden.

### 6.2 Exclusion and insufficient-coverage recording

Every unavailable, excluded, and insufficient-coverage result must be recorded
explicitly. Silent omission is forbidden.

~~~text
EXCLUSION_MUST_BE_RECORDED=true
INSUFFICIENT_COVERAGE_MUST_BE_RECORDED=true
SILENT_FILL_FORBIDDEN=true
NOT_COMPUTABLE_IS_NOT_ZERO=true
~~~

Inherited exclusions (not reopened):

~~~text
EXCLUDED_VARIETIES=普鲜,普青,普冻,废果
EXCLUDED_FACTORY_BASON=true
DEFAULT_MONTH_SCOPE=1-4
EXCLUSION_POLICY_REOPEN_FORBIDDEN=true
~~~

### 6.3 Baseline parity

The incumbent model and naive baseline must use the **same** exclusion policy and
missing-day policy.

~~~text
INCUMBENT_AND_NAIVE_BASELINE_EXCLUSION_POLICY_IDENTICAL=true
INCUMBENT_AND_NAIVE_BASELINE_MISSING_DAY_POLICY_IDENTICAL=true
BASELINE_COMPARISON_REQUIRES_POLICY_PARITY=true
~~~

## 7. Metric computability under this contract

S3-C0 defines execution-time computability rules only. It does **not** execute
metrics and does not claim metric results.

### 7.1 Daily point metrics

Per P0 §4.3 and S3-A §7.1, daily point metrics are not blocked by the complete
daily rowset amendment. They may be defined on legal `OBSERVED` actual ∩ legal
forecast pairs.

~~~text
DAILY_POINT_METRICS=daily_mae,daily_wape,daily_smape
DAILY_POINT_METRICS_BLOCKED_BY_COMPLETE_DAILY_ROWSET=false
DAILY_POINT_METRICS_REQUIRE_VALID_PAIRING=true
DAILY_POINT_METRICS_REQUIRE_OBSERVED_ACTUAL=true
THIS_PR_DOES_NOT_EXECUTE_DAILY_POINT_METRICS=true
S3_METRIC_EXECUTION_AUTHORIZED=false
~~~

### 7.2 Peak, cumulative, and complete-horizon metrics

Until `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=true`:

~~~text
SINGLE_DAY_PEAK_STATUS=NOT_COMPUTABLE
SUSTAINED_PEAK_STATUS=NOT_COMPUTABLE
SEASON_CUMULATIVE_STATUS=NOT_COMPUTABLE
COMPLETE_HORIZON_STATUS=NOT_COMPUTABLE
NOT_COMPUTABLE_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
NOT_COMPUTABLE_IS_NOT_ZERO=true
~~~

S3-C0 must not emit peak or cumulative numeric results in this contract-only PR.

### 7.3 Quantile coverage (S3-B gate)

Until S3-B sets `CURRENT_P50_SEMANTICS_STATUS`, `CURRENT_P80_SEMANTICS_STATUS`,
and `CURRENT_P90_SEMANTICS_STATUS` to verified states:

~~~text
CURRENT_P50_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P90_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_COVERAGE_COMPUTABLE=false
CURRENT_P90_COVERAGE_COMPUTABLE=false
CURRENT_BASELINE_P80_COMPUTABLE=false
CURRENT_BASELINE_P90_COMPUTABLE=false
QUANTILE_COVERAGE_STATUS=NOT_COMPUTABLE
QUANTILE_COVERAGE_REASON_CODE=QUANTILE_SEMANTICS_NOT_VERIFIED
NOT_VERIFIED_IS_NOT_PASS=true
~~~

### 7.4 Sustained peak window conflict (UNRESOLVED)

~~~text
PRODUCT_SUSTAINED_PEAK_WINDOW_DAYS=3
PLAN_SUSTAINED_PEAK_WINDOW_DAYS=7
V0_2_METRIC_ID=SUSTAINED_7DAY_PEAK
P0_SUSTAINED_PEAK_WINDOW_CONFLICT=UNRESOLVED
S3_C0_DOES_NOT_RESOLVE_3_VS_7=true
SUSTAINED_PEAK_PASS_FORBIDDEN_UNTIL_OWNER_DECISION=true
~~~

## 8. Leakage audit checklist (future execution)

The following checklist is frozen for future authorized execution. This PR does
not perform the audit.

| Audit item | Rule | Failure action |
|---|---|---|
| Post-cutoff weather observations | Must not enter forecast input at cutoff | `BLOCKED` or `NOT_COMPUTABLE` |
| Retrospective phenology | Must not backdate into earlier forecast | `BLOCKED` or `NOT_COMPUTABLE` |
| Post-season yield per mu (亩产) | Must not enter pre-season forecast input | `BLOCKED` or `NOT_COMPUTABLE` |
| Final marketable rate (终商品果率) | Must not enter pre-season forecast input | `BLOCKED` or `NOT_COMPUTABLE` |
| TEST partition labels | Must not enter TRAIN/VALIDATION execution | forbidden input |
| Ungoverned master data | Must not enter any execution path | forbidden input |
| `SOURCE_AVAILABLE_AT > FORECAST_CUTOFF_AT` | Row ineligible for forecast input | exclude; record |
| PIT / old-winner as SOURCE_002 primary | Forbidden pairing path | forbidden input |
| Final-season facts at historical cutoff | Forbidden input construction | `BLOCKED` or `NOT_COMPUTABLE` |
| Later labels for historical input | Forbidden input construction | `BLOCKED` or `NOT_COMPUTABLE` |

~~~text
LEAKAGE_AUDIT_PERFORMED_IN_THIS_PR=false
POINT_IN_TIME_REPLAY=false
LEAKAGE_AUDIT=false
~~~

## 9. Required outputs (future execution contract)

When separately authorized, a PIT backtest runner must emit:

1. Reproducible point-in-time backtest diagnostics on TRAIN/VALIDATION
2. Versioned metric results with explicit `NOT_COMPUTABLE` / `NOT_VERIFIED`
   states and formal reason codes
3. Recorded exclusions, pairing failures, and insufficient-coverage instances
4. Input snapshot metadata: data version, model version, training cutoff,
   prediction generation time, and confidence intervals per AGENTS.md rule 7
5. Traceability to accepted S2 row identities and forecast cutoff

S3-C0 does **not** implement the deterministic metric service or runner.

~~~text
DETERMINISTIC_METRIC_SERVICE_IMPLEMENTED=false
BACKTEST_RUNNER_IMPLEMENTED=false
LLM_MUST_NOT_INVENT_TONNES=true
ALL_TONNAGE_INTERVALS_FROM_DETERMINISTIC_SERVICE=true
~~~

## 10. Forbidden inputs and actions

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
FORBIDDEN_SOURCE_002_ROW_LEVEL_READ_IN_THIS_TASK=true
FORBIDDEN_TEST_READ_IN_THIS_TASK=true
FORBIDDEN_SQL_DUMP=true
FORBIDDEN_BACKTEST_RUN_IN_THIS_TASK=true
FORBIDDEN_RUNNER_IMPLEMENTATION_IN_THIS_TASK=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 11. Subtask boundaries

~~~text
S3_C0_PIT_BACKTEST_CONTRACT_AUTHORIZED=true
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=false
S3_B_AUTHORIZED=false
S3_D_AUTHORIZED=false
next_subtask_not_implied=true
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_MERGE_DOES_NOT_AUTHORIZE_BACKTEST=true
~~~

| Subtask | Status after S3-C0 merge |
|---|---|
| S3-C0 execution contract | frozen (this document) |
| S3-C backtest execution | not authorized |
| S3 metric execution | not authorized |
| S3-A materialization | not authorized |
| S3-B quantile semantics | not authorized |
| S3-D error attribution | not authorized |

## 12. LLM and deterministic service boundary

~~~text
LLM_MUST_NOT_INVENT_TONNES=true
ALL_TONNAGE_INTERVALS_FROM_DETERMINISTIC_SERVICE=true
DETERMINISTIC_METRIC_SERVICE_IMPLEMENTED_IN_C0=false
METRIC_EXECUTION_IMPLEMENTED_IN_C0=false
~~~

LLM agents organize explanations and invoke tools only. All tonnage, intervals,
contribution rates, and pass/fail thresholds must come from deterministic
services after separate authorization. S3-C0 does not implement those services.

## 13. S3-B quantile semantics contract live-authority pointer

~~~text
S3_B_QUANTILE_SEMANTICS_CONTRACT_LIVE_AUTHORITY_WORKPAPER=docs/v0-3/s3/workpapers/s3-b-quantile-semantics-contract-live-authority.md
S3_B_QUANTILE_SEMANTICS_CONTRACT_LIVE_AUTHORITY_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-b-quantile-semantics-contract-live-authority.json
EVIDENCE_JSON_SHA256=7d47de8c84dcd52d6feea8aff3ecdcd3ecf6d4e9f7879c32f076dafae559a9c9
PARENT_S3_B_PR=301
PARENT_S3_B_MERGE=f9e7b221722d74789112142aebb77a5c69687ea3
PARENT_S3_B_CONTRACT_PATH=docs/v0-3/s3/s3-quantile-semantics-contract.md
PARENT_S3_B_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=8456c9b4412a68680033995605c82356d0a322e0
CURRENT_S3_B_CONTRACT_GIT_BLOB_SHA=8456c9b4412a68680033995605c82356d0a322e0
S3_B_CONTRACT_EVIDENCE_JSON_SHA256=52dfe07eb6a17004704a1545c136a51c4646fbc7b7f7bca80b13f87a71e2d3e7
S3_B_CONTRACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-b-quantile-semantics.md
PARENT_P0_CONTRACT_GIT_BLOB_SHA_AT_S3_B_FREEZE=45f900f4dfa1ef5da8ea898a39bdded4c8c11f08
CURRENT_P0_CONTRACT_GIT_BLOB_SHA=cdf636b645345a41223ec2854c87d7ed2308cb63
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
P0_EVIDENCE_JSON_SHA256=580f09e306e4e32db0e72d65158d455bd9fea57b4279497909ff0d54cb91259c
PARENT_S3_A_AMENDMENT_GIT_BLOB_SHA_AT_S3_B_FREEZE=1baf930287598f5df78ac28d49c159b4231c0fc6
CURRENT_S3_A_AMENDMENT_GIT_BLOB_SHA=2119ed47ac2e53e0eeac5f505b976c0b972665a9
S3_A_AMENDMENT_PATH=docs/v0-3/s3/s3-daily-rowset-amendment.md
S3_A_AMENDMENT_EVIDENCE_JSON_SHA256=b50948c9529dd7f87b844e61e48fbb3b89d6eae31211f43d6fc5189360553e0a
PARENT_S3_C0_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=3850b7cc85fa87d2cf7aa1b4fb23c3d756d6295b
CURRENT_S3_C0_CONTRACT_GIT_BLOB_SHA=21c3b2d31a4fa40039d054c1cc82fffcb1f978b0
S3_C0_CONTRACT_PATH=docs/v0-3/s3/s3-pit-backtest-execution-contract.md
S3_C0_EVIDENCE_JSON_SHA256=12c40e013c60de9f9dbcfd7b5e7788281d9c7d6adcde641d6d436b3e65b5d7e1
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
ALIGNMENT_SECTION_6_SHA256=2eaf3719b1cb2e7097c6ded457098a0563b46c0965eabf38d60327b1a6b2a7a8
POPULATED_ORIGIN_R1_EVIDENCE_JSON_SHA256=f431cbceb91d830adfc332311dfbf052e74599080c22cd2736b1bc2f7e4c5ea4
CURRENT_POPULATED_ORIGIN_CONTRACT_GIT_BLOB_SHA=29dd5d3183a9f9bd4c096d1e8724fd6582a47caa
PARENT_POPULATED_ORIGIN_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=b9d3daad7eb8aa172b2ad241d7b78223d362c82b
TASK_CLASS=CONTRACT_DEFINITION_ONLY
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_R1=true
PARALLEL_LANE=S3-B
S3_B_QUANTILE_SEMANTICS_CONTRACT_AUTHORIZED=true
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
CURRENT_P50_SEMANTICS_VERIFIED=false
CURRENT_P80_SEMANTICS_VERIFIED=false
CURRENT_P90_SEMANTICS_VERIFIED=false
CURRENT_P50_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P90_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_COVERAGE_COMPUTABLE=false
CURRENT_P90_COVERAGE_COMPUTABLE=false
CURRENT_QUANTILE_REASON_CODE=QUANTILE_SEMANTICS_NOT_VERIFIED
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
PENDING_COORDINATOR_EXECUTION_NOT_VERIFIED_CLAIM=true
S3_B_CONTRACT_LIVE_AUTHORITY_IS_NOT_CHECKLIST_EXECUTION=true
S3_B_CONTRACT_LIVE_AUTHORITY_IS_NOT_VERIFIED_CLAIM=true
CONTRACT_LIVE_AUTHORITY_MERGE_DOES_NOT_EXECUTE_CHECKLIST=true
CONTRACT_LIVE_AUTHORITY_MERGE_DOES_NOT_FLIP_VERIFIED_CLAIM=true
CONTRACT_LIVE_AUTHORITY_MERGE_DOES_NOT_FLIP_COVERAGE_COMPUTABLE=true
CONTRACT_LIVE_AUTHORITY_MERGE_DOES_NOT_TOUCH_PYTHON=true
FORBIDDEN_TREAT_THIS_EVIDENCE_AS_SEMANTICS_VERIFIED_CLAIM=true
FORBIDDEN_TREAT_S3_B_CONTRACT_FREEZE_AS_VERIFIED_UPPER_QUANTILE=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
~~~

Live `S3_B_QUANTILE_SEMANTICS_CONTRACT_AUTHORIZED` is maintained in `docs/v0-3/development-plan.md` §4.4 live state block and `docs/v0-3/s3/workpapers/s3-b-quantile-semantics-contract-live-authority.md` (`EVIDENCE_JSON_SHA256=7d47de8c84dcd52d6feea8aff3ecdcd3ecf6d4e9f7879c32f076dafae559a9c9`). S3-B quantile semantics verification procedure contract is on main (#301). This live-authority insert records that the frozen procedure contract is authorized in the development-plan live registry. `S3_B_QUANTILE_SEMANTICS_CONTRACT_AUTHORIZED=true` ≠ `CURRENT_P*_SEMANTICS_VERIFIED` ≠ `S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED` ≠ checklist executed ≠ P50/P80/P90 are `VERIFIED_TRUE_UPPER_QUANTILE` ≠ coverage computable ≠ model change allowed. #301 preliminary conclusions (e.g. P80/P90 as P50+margin) remain `PENDING_COORDINATOR_EXECUTION`, not verified claim results. This evidence JSON is not a semantics-verified claim package. Catalog first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. A2 identity-set family remains fail-closed; this insert is not origin / members / artifact authority. Historical pointer snapshots may remain without `S3_B_QUANTILE_SEMANTICS_CONTRACT_AUTHORIZED`.

## 14. S3-B quantile semantics verified-claim authorization pointer

~~~text
S3_B_QUANTILE_SEMANTICS_VERIFIED_CLAIM_AUTHORIZATION_WORKPAPER=docs/v0-3/s3/workpapers/s3-b-quantile-semantics-verified-claim-authorization.md
S3_B_QUANTILE_SEMANTICS_VERIFIED_CLAIM_AUTHORIZATION_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-b-quantile-semantics-verified-claim-authorization.json
EVIDENCE_JSON_SHA256=0697b9bac264f71f2465f057f1bf3f7df35ed33b5c69f94ca8a44e2ec3ec7413
PARENT_LIVE_AUTHORITY_PR=384
PARENT_LIVE_AUTHORITY_MERGE=d92e9d11d3930a5f7a93d61402bb363327ffebec
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=7d47de8c84dcd52d6feea8aff3ecdcd3ecf6d4e9f7879c32f076dafae559a9c9
LIVE_AUTHORITY_WORKPAPER=docs/v0-3/s3/workpapers/s3-b-quantile-semantics-contract-live-authority.md
PARENT_S3_B_PR=301
PARENT_S3_B_MERGE=f9e7b221722d74789112142aebb77a5c69687ea3
PARENT_S3_B_CONTRACT_PATH=docs/v0-3/s3/s3-quantile-semantics-contract.md
PARENT_S3_B_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=8456c9b4412a68680033995605c82356d0a322e0
S3_B_CONTRACT_CONTENT_SHA256_AT_FREEZE=28dfb92b96caf6cef9124c80abcd23feb3a569a01131cad94a56089cf30fa6f1
CURRENT_S3_B_CONTRACT_GIT_BLOB_SHA=2eed2f1366080059e3f250e52f9dd1c64dfa6f2c
S3_B_CONTRACT_EVIDENCE_JSON_SHA256=52dfe07eb6a17004704a1545c136a51c4646fbc7b7f7bca80b13f87a71e2d3e7
S3_B_CONTRACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-b-quantile-semantics.md
PARENT_P0_CONTRACT_GIT_BLOB_SHA_AT_S3_B_FREEZE=45f900f4dfa1ef5da8ea898a39bdded4c8c11f08
CURRENT_P0_CONTRACT_GIT_BLOB_SHA=247ad7c41dec35c7e299f73eb66c610aec5fbcf6
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
P0_EVIDENCE_JSON_SHA256=580f09e306e4e32db0e72d65158d455bd9fea57b4279497909ff0d54cb91259c
PARENT_S3_A_AMENDMENT_GIT_BLOB_SHA_AT_S3_B_FREEZE=1baf930287598f5df78ac28d49c159b4231c0fc6
CURRENT_S3_A_AMENDMENT_GIT_BLOB_SHA=63bcee78e659663e568bafcc7fd70edabdb79105
S3_A_AMENDMENT_PATH=docs/v0-3/s3/s3-daily-rowset-amendment.md
S3_A_AMENDMENT_EVIDENCE_JSON_SHA256=b50948c9529dd7f87b844e61e48fbb3b89d6eae31211f43d6fc5189360553e0a
PARENT_S3_C0_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=3850b7cc85fa87d2cf7aa1b4fb23c3d756d6295b
CURRENT_S3_C0_CONTRACT_GIT_BLOB_SHA=8728188f5468e8ec5c9adc958b547cf840e307ee
S3_C0_CONTRACT_PATH=docs/v0-3/s3/s3-pit-backtest-execution-contract.md
S3_C0_EVIDENCE_JSON_SHA256=12c40e013c60de9f9dbcfd7b5e7788281d9c7d6adcde641d6d436b3e65b5d7e1
CURRENT_POPULATED_ORIGIN_CONTRACT_GIT_BLOB_SHA=29dd5d3183a9f9bd4c096d1e8724fd6582a47caa
PARENT_POPULATED_ORIGIN_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=b9d3daad7eb8aa172b2ad241d7b78223d362c82b
POPULATED_ORIGIN_R1_EVIDENCE_JSON_SHA256=f431cbceb91d830adfc332311dfbf052e74599080c22cd2736b1bc2f7e4c5ea4
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
ALIGNMENT_SECTION_6_SHA256=2eaf3719b1cb2e7097c6ded457098a0563b46c0965eabf38d60327b1a6b2a7a8
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
GRANT_ONLY=true
THIS_PR_IS_NOT_R1=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
PARALLEL_LANE=S3-B
S3_B_QUANTILE_SEMANTICS_CONTRACT_AUTHORIZED=true
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=true
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
CURRENT_P50_SEMANTICS_VERIFIED=false
CURRENT_P80_SEMANTICS_VERIFIED=false
CURRENT_P90_SEMANTICS_VERIFIED=false
CURRENT_P50_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P90_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_COVERAGE_COMPUTABLE=false
CURRENT_P90_COVERAGE_COMPUTABLE=false
CURRENT_QUANTILE_REASON_CODE=QUANTILE_SEMANTICS_NOT_VERIFIED
S3_BACKTEST_EXECUTION_AUTHORIZED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
PENDING_COORDINATOR_EXECUTION_NOT_VERIFIED_CLAIM=true
GRANT_MERGE_DOES_NOT_EXECUTE_CHECKLIST=true
GRANT_MERGE_DOES_NOT_FLIP_CURRENT_P_SEMANTICS_STATUS=true
GRANT_MERGE_DOES_NOT_FLIP_COVERAGE_EXECUTION=true
GRANT_MERGE_DOES_NOT_TOUCH_PYTHON=true
FORBIDDEN_TREAT_THIS_EVIDENCE_AS_SEMANTICS_VERIFIED_CLAIM=true
FORBIDDEN_TREAT_S3_B_CONTRACT_FREEZE_AS_VERIFIED_UPPER_QUANTILE=true
FORBIDDEN_TREAT_301_PRELIMINARY_AS_R1_RESULT=true
FORBIDDEN_CHANGE_MODEL_TO_FORCE_PASS=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
~~~

Live `S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED` is maintained in `docs/v0-3/development-plan.md` §4.4 live state block and `docs/v0-3/s3/workpapers/s3-b-quantile-semantics-verified-claim-authorization.md` (`EVIDENCE_JSON_SHA256=0697b9bac264f71f2465f057f1bf3f7df35ed33b5c69f94ca8a44e2ec3ec7413`). S3-B quantile semantics procedure contract is on main (#301); live contract authority is on main (#384). This grant authorizes a **later** docs-only verified-claim R1 to execute the frozen §7 checklist when the user again says 「可以实施」. `S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=true` ≠ checklist executed ≠ `CURRENT_P*_SEMANTICS_VERIFIED` ≠ P50/P80/P90 are `VERIFIED_TRUE_UPPER_QUANTILE` ≠ coverage computable ≠ model change allowed. This evidence JSON is not a semantics-verified claim package. #301 preliminary conclusions remain `PENDING_COORDINATOR_EXECUTION`, not verification results. Catalog first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. A2 identity-set family remains fail-closed; this grant is not origin / members / artifact authority. Historical pointer snapshots may remain `S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false`.
