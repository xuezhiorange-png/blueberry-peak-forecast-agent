# V0.3-S3 Backtest and Diagnosis Contract

## Contract identity and phase boundary

~~~text
CONTRACT_ID=V0_3_S3_BACKTEST_AND_DIAGNOSIS_CONTRACT
CONTRACT_VERSION=v0-3-s3-backtest-and-diagnosis-contract-v1
TASK_ID=V03_S3_P0_CONTRACT_FREEZE_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_P0_CONTRACT_FREEZE_ONLY
SLICE=V0.3-S3
ENGLISH_ID=CURRENT_MODEL_POINT_IN_TIME_BACKTEST_AND_ERROR_DIAGNOSIS
USER_GATE=可以实施
V0_3_S3_PHASE_ENTRY_AUTHORIZED=true
CONTRACT_ONLY=true
BASE_MAIN_SHA=9a68698c0ff5454708d0bd52596788d9dfb6cc8f
BASE_MAIN_TREE_SHA=85fbc852dd730a408226652b2fb2b790849a9256
REVIEWER_ROLE=COORDINATOR
USER_WAIVED_THIRD_PARTY_REVIEW=true
COORDINATOR_REVIEW_COUNTS=true
P0_DOES_NOT_AUTHORIZE_ALLOWLIST_OR_CODE=true
NO_STEP_IMPLIES_THE_NEXT=true
~~~

~~~text
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
S3_BACKTEST_EXECUTION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
V0_3_S4_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
SOURCE_002_ROW_LEVEL_READ=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

This document freezes the shared V0.3-S3 point-in-time backtest and error
diagnosis contract before any implementation subtask begins. It is a governance
contract, not a backtest run, metric execution, model change, or acceptance
result.

P0 creates this document. It does not authorize backtest execution, TEST
evaluation, production or test code, allowlist PASS, or S3 acceptance. Merging
this contract does not imply that backtests may run.

## 1. Inherited accepted authority

### 1.1 S1 bindings (accepted; not reopened)

~~~text
Q2C_TARGET_DECISION=OBSERVED_FARM_PICK_QUANTITY
V0_3_METRIC_CONTRACT_VERSION=v0.3-metric-contract-v1
S1_METRIC_CONTRACT_PATH=docs/v0-3/s1/metric-coverage-and-quality-contract.md
EXTERNAL_HOLDOUT_OWNER_DECISION=REVIEWED_NOT_FEASIBLE
EXTERNAL_HOLDOUT_NOT_APPLICABLE=true
S1_HOLDOUT_FEASIBILITY_GATE=S1-HOLDOUT-FEASIBILITY
~~~

### 1.2 S2 bindings (accepted and registry PASS on main)

~~~text
S2_ACCEPTANCE_PR=296
S2_REGISTRY_CLOSEOUT_PR=297
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
S2_CONTRACT_PATH=docs/v0-3/s2/s2-materialized-dataset-contract.md
S2_ACCEPTANCE_WORKPAPER=docs/v0-3/s2/workpapers/s2-source-002-acceptance-package.md
S2_ACCEPTANCE_EVIDENCE_JSON=docs/v0-3/s2/evidence/s2-source-002-acceptance-package.json
S2_ACCEPTANCE_EVIDENCE_JSON_SHA256=f7856e99ded3cf4c56f1d6e4b283ccd903e35302cb06db606c6446419d76e02f
TRAIN_ROW_COUNT=16224
VALIDATION_ROW_COUNT=8006
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
TEST_IS_SEALED_PLACEHOLDER=true
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
CANONICAL_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
SOURCE_002_VISIBILITY_PRIMARY_PATH=IDFL_LABEL_SIDE
PIT_SQL_COUNT_EXPECTED=0
OLD_WINNER_SQL_COUNT_EXPECTED=0
FROZEN_SOURCE_ARTIFACT_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
CURRENT_V0_3_S2_COMPLETE=true
CURRENT_V0_3_S2_ACCEPTANCE_STATUS=ACCEPTED
~~~

### 1.3 V0.2 metric authority (reference only; do not mutate)

~~~text
V0_2_S3_METRIC_CONTRACT_PATH=docs/forecast-quality/s3-quality-metrics-contract.md
METRIC_CONTRACT_AUTHORITY_BASE_SHA=b873dd63fc0d5b6375f94674abbd24a94d915f3c
V0_2_S3_INPUT_AUTHORITY_HISTORICAL=S2_IMMUTABLE_BACKTEST_BINDING
V0_2_S3_INPUT_AUTHORITY_IS_NOT_V0_3_S2_MATERIALIZED_DATASET=true
~~~

The V0.2-S3 contract `S3_INPUT_AUTHORITY=S2_IMMUTABLE_BACKTEST_BINDING` names
the V0.2 historical backtest pairing artifact. It is **not** the V0.3-S2
materialized dataset `source-002/e5-live-v1`. V0.3-S3 must not conflate these
authorities.

### 1.4 Slice objective authority

~~~text
SLICE_OBJECTIVE_AUTHORITY=docs/v0-3/development-plan.md
SLICE_OBJECTIVE_SECTIONS=§4.4,§4.5
~~~

S3 evaluates the current V0.2 incumbent model against governed real historical
data using strict historical visibility. It produces an error diagnosis and a
quantified candidate-improvement backlog for S4. It does not change the model or
parameters.

## 2. V0.3-S3 input authority

V0.3-S3 binds the following authorities. These names are distinct from the
V0.2 `S2_IMMUTABLE_BACKTEST_BINDING` pairing.

~~~text
V0_3_S3_ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
V0_3_S3_VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
V0_3_S3_METRIC_FORMULA_AUTHORITY=docs/forecast-quality/s3-quality-metrics-contract.md
V0_3_S3_METRIC_COVERAGE_AUTHORITY=docs/v0-3/s1/metric-coverage-and-quality-contract.md
~~~

### 2.1 Permitted inputs

- TRAIN and VALIDATION materialized partitions from accepted S2
  `source-002/e5-live-v1`
- IDFL label-side visibility reconstruction for SOURCE_002
- Incumbent V0.2 current model forecasts at each historical cutoff
- Accepted S1 metric contract definitions and versioned metric IDs

### 2.2 Forbidden inputs

The following are explicitly forbidden as S3 inputs:

~~~text
FORBIDDEN_REREAD_XLS=true
FORBIDDEN_REREAD_GOOGLE_SHEETS=true
FORBIDDEN_S1_DERIVED_JSON_AS_PRIMARY_INPUT=true
FORBIDDEN_FACTORY_BASON=true
FORBIDDEN_VARIETIES=普鲜,普青,普冻,废果
FORBIDDEN_PIT_TABLE_AS_SOURCE_002_PRIMARY=true
FORBIDDEN_OLD_WINNER_TABLE_AS_SOURCE_002_PRIMARY=true
FORBIDDEN_TEST_PLACEHOLDER_AS_EVALUATION_ROWS=true
FORBIDDEN_UNGOVERNED_MASTER_DATA=true
FORBIDDEN_FINAL_SEASON_FACTS_AT_HISTORICAL_CUTOFF=true
~~~

`PIT_SQL_COUNT=0` and `OLD_WINNER_SQL_COUNT=0` are expected for SOURCE_002.
Using PIT or old-winner tables as SOURCE_002 primary visibility is forbidden.

## 3. Split and evaluation scope

### 3.1 Permitted evaluation partitions

S3 diagnosis uses **TRAIN + VALIDATION only**.

~~~text
S3_EVALUATION_PARTITIONS=TRAIN,VALIDATION
S3_TRAIN_ROW_COUNT=16224
S3_VALIDATION_ROW_COUNT=8006
RANDOM_ADJACENT_DATE_SPLIT_FORBIDDEN=true
TIME_ORDERED_SPLIT_INHERITED_FROM_S1=true
~~~

### 3.2 TEST partition (sealed)

~~~text
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
TEST_IS_SEALED_PLACEHOLDER=true
TEST_ROW_COUNT_ZERO_IS_NOT_EVALUATION_FAILURE=true
~~~

TEST placeholder hashes are identity bindings only. They are not evaluation
rows. S3 must not treat `TEST.row_count=0` as a backtest failure.

### 3.3 External holdout

~~~text
EXTERNAL_HOLDOUT_NOT_APPLICABLE=true
EXTERNAL_HOLDOUT_OWNER_DECISION=REVIEWED_NOT_FEASIBLE
EXTERNAL_HOLDOUT_BYTES_EXIST=false
DO_NOT_CLAIM_HOLDOUT_BYTES_EXIST=true
~~~

## 4. Missing-day and daily rowset policy

### 4.1 Missing-day semantics

~~~text
MISSING_DAY_POLICY=UNKNOWN_NOT_ZERO
MISSING_DAY_ZERO_FILL=false
MISSING_ACTUAL_TREATED_AS_ZERO=false
~~~

A missing harvest day is unknown, not zero. S3 must not silently fill missing
days with `0` kg or invent tonnage.

### 4.2 Current daily rowset contract status

The development plan and V0.2 metric contract both record that a complete
calendar daily row set is **not** available from the current S2 binding. P0
copies that state verbatim; it does not claim amendment completion.

~~~text
CURRENT_S3_DAILY_ROWSET_CONTRACT_STATUS=NOT_AVAILABLE_FROM_CURRENT_S2_BINDING
CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
S2_TO_S3_DAILY_ROWSET_AMENDMENT_REQUIRED=true
~~~

Live `CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE` is maintained in
`docs/v0-3/development-plan.md` §4.4 and the S3-A closeout package. Amendment
contract text completion does not imply a materialized calendar daily row set
exists from the current S2 binding.

P0 did **not** define how sparse harvest grains become a complete calendar
daily row set. That requires a separately authorized S3-A daily-rowset amendment
contract.

### 4.3 Metric computability under current binding

Peak, cumulative, and complete-horizon metrics are `NOT_COMPUTABLE` until the
daily-rowset amendment is accepted:

~~~text
PEAK_AND_COMPLETE_HORIZON_METRICS_REQUIRE_COMPLETE_DAILY_ROW_SET=true
SINGLE_DAY_PEAK_CURRENT_STATUS=NOT_COMPUTABLE
SUSTAINED_PEAK_CURRENT_STATUS=NOT_COMPUTABLE
SEASON_CUMULATIVE_CURRENT_STATUS=NOT_COMPUTABLE
COMPLETE_HORIZON_CURRENT_STATUS=NOT_COMPUTABLE
NOT_COMPUTABLE_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
NOT_COMPUTABLE_IS_NOT_ZERO=true
~~~

Daily point metrics (`daily_mae`, `daily_wape`, `daily_smape`, and related §6
fields) are **not** blocked by the complete-daily-rowset amendment per the V0.2
metric contract. They remain computable only when valid forecast/actual pairs
exist under accepted visibility and pairing rules. Pairing failure yields
`NOT_COMPUTABLE`; it must not be reported as zero.

~~~text
DAILY_POINT_METRICS_BLOCKED_BY_COMPLETE_DAILY_ROWSET=false
DAILY_POINT_METRICS_REQUIRE_VALID_PAIRING=true
PAIRING_FAILURE_STATUS=NOT_COMPUTABLE
PAIRING_FAILURE_IS_NOT_ZERO=true
~~~

## 5. Quantile semantics and coverage

All quantile semantics and coverage metrics are currently unverified and not
computable for release.

~~~text
CURRENT_P50_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P90_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_COVERAGE_COMPUTABLE=false
CURRENT_P90_COVERAGE_COMPUTABLE=false
CURRENT_BASELINE_P80_COMPUTABLE=false
CURRENT_BASELINE_P90_COMPUTABLE=false
CURRENT_QUANTILE_REASON_CODE=QUANTILE_SEMANTICS_NOT_VERIFIED
NOT_VERIFIED_IS_NOT_PASS=true
NOT_COMPUTABLE_IS_NOT_ZERO=true
~~~

### 5.1 Coverage definition

Per the V0.2 metric contract:

~~~text
P80_COVERAGE_DEFINITION=actual<=forecast_p80
P90_COVERAGE_DEFINITION=actual<=forecast_p90
P80_UPPER_QUANTILE_SPREAD=P80-P50
P90_UPPER_QUANTILE_SPREAD=P90-P50
P80_UPPER_QUANTILE_SPREAD_IS_PREDICTION_INTERVAL_WIDTH=false
P90_UPPER_QUANTILE_SPREAD_IS_PREDICTION_INTERVAL_WIDTH=false
COVERAGE_REQUIRES_COMPLETE_DAILY_ROW_SET=false
~~~

Coverage may be computed over valid paired sparse binding rows once quantile
semantics are verified. It does not require a complete daily row set.

## 6. Product rule vs plan: sustained peak window (UNRESOLVED)

AGENTS.md business rules require simultaneous output of single-day peak and
**continuous 3-day** sustained peak. The development-plan §4.4 objective list
and the V0.2 metric contract freeze **sustained_7day** peak metrics.

~~~text
PRODUCT_SUSTAINED_PEAK_WINDOW_DAYS=3
PLAN_SUSTAINED_PEAK_WINDOW_DAYS=7
V0_2_METRIC_ID=SUSTAINED_7DAY_PEAK
P0_SUSTAINED_PEAK_WINDOW_CONFLICT=UNRESOLVED
P0_DOES_NOT_RESOLVE_3_VS_7=true
SUSTAINED_PEAK_PASS_FORBIDDEN_UNTIL_OWNER_DECISION=true
~~~

P0 records the conflict. It does not choose 3-day or 7-day sustained peak.
Until an owner decision amends the metric contract or product rule binding, any
sustained-peak `PASS` claim is forbidden.

## 7. Model and output boundaries

### 7.1 Incumbent model only

~~~text
EVALUATED_MODEL=V0_2_CURRENT_INCUMBENT
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
FORECASTS_MUST_USE_HISTORICAL_CUTOFF_VISIBILITY=true
~~~

S3 diagnoses the incumbent V0.2 current model. It does not authorize model or
parameter changes.

### 7.2 Outputs

S3 produces:

- reproducible point-in-time backtest diagnostics on TRAIN/VALIDATION
- versioned metric results with explicit `NOT_COMPUTABLE` / `NOT_VERIFIED` states
- an error attribution matrix and candidate-improvement backlog for S4

S3 does **not** authorize implementing those improvements in S3.

### 7.3 LLM and deterministic service boundary

~~~text
LLM_MUST_NOT_INVENT_TONNES=true
ALL_TONNAGE_INTERVALS_FROM_DETERMINISTIC_SERVICE=true
DETERMINISTIC_METRIC_SERVICE_IMPLEMENTED_IN_P0=false
~~~

LLM agents organize explanations and invoke tools only. All tonnage, intervals,
contribution rates, and pass/fail thresholds must come from deterministic
services. P0 does not implement those services.

## 8. Point-in-time backtest rules

Inherited from development-plan §4.4:

- Reconstruct each forecast input from data visible at its historical cutoff.
- Keep production exclusion and missing-data policies identical across incumbent
  model and naive baseline.
- Use final S2-accepted TRAIN and VALIDATION identities; TEST remains sealed.
- Do not use final-season facts, future revisions, or later labels to construct
  historical inputs.
- Record every unavailable, excluded, and insufficient-coverage result; do not
  silently fill.
- Forbid random splitting of adjacent dates as the primary validation method.

## 9. Error attribution (§4.5 binding)

Error attribution has two layers and is not a strict causal decomposition.
Multiple candidate causes are allowed; unexplained residuals remain visible.

Required error dimensions include quantity-level, maturity-timing, single-day
peak, seven-day peak (pending window resolution), season-cumulative, and
quantile-calibration errors. Candidate causes include phenology input, weather
response, harvest capacity, marketable rate, mature inventory, master data,
data quality, and unknown residual.

~~~text
MULTI_LABEL_ATTRIBUTION=true
MULTI_LABEL_CONTRIBUTIONS_MUTUALLY_EXCLUSIVE=false
MULTI_LABEL_CONTRIBUTIONS_MAY_OVERLAP=true
ESTIMATED_CONTRIBUTION_STATUS=COMPUTED|NOT_COMPUTABLE
NOT_COMPUTABLE_CONTRIBUTION_IS_NOT_ZERO=true
MANUAL_REVIEW_CANNOT_AUTHORIZE_MODEL_CHANGE=true
~~~

## 10. Future S3 acceptance gates (all false at P0)

The following are prerequisites for future S3 acceptance. P0 records them as
**not** satisfied:

~~~text
DAILY_ROWSET_AMENDMENT_COMPLETE=false
P50_SEMANTICS_VERIFIED=false
P80_SEMANTICS_VERIFIED=false
P90_SEMANTICS_VERIFIED=false
P50_P80_P90_SEMANTICS_VERIFIED=false
POINT_IN_TIME_REPLAY=false
LEAKAGE_AUDIT=false
CURRENT_MODEL_BASELINE=false
ERROR_DIAGNOSIS=false
SLICE_S3_COMPLETE=false
CURRENT_V0_3_S3_COMPLETE=false
V0_3_S4_AUTHORIZED=false
~~~

`NOT_VERIFIED` is not `PASS`. `NOT_COMPUTABLE` is not zero.

Live amendment-complete status is maintained in `docs/v0-3/development-plan.md`
and `docs/v0-3/s3/workpapers/s3-a-amendment-closeout.md`. The block above is
the P0 freeze snapshot.

## 11. Subtask roadmap (named only; not authorized)

The following subtasks are named for planning. None are authorized by P0.

| Subtask | Description | Authorized by P0 |
|---|---|---|
| S3-P0 | This contract freeze | yes (contract only) |
| S3-A | Daily rowset amendment contract | no |
| S3-B | Quantile semantics verification | no |
| S3-C | TRAIN/VAL point-in-time backtest execution | no |
| S3-D | Error attribution matrix execution | no |

~~~text
next_subtask_not_implied=true
S3_A_AUTHORIZED=true
S3_A_AMENDMENT_PATH=docs/v0-3/s3/s3-daily-rowset-amendment.md
S3_A_AMENDMENT_VERSION=v0-3-s3-daily-rowset-amendment-v1
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=true
S3_B_AUTHORIZED=false
S3_C_AUTHORIZED=false
S3_D_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
~~~

Live `S3_A_ROWSET_MATERIALIZATION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a-rowset-materialization-authorization.md`.
Materialization grant does not execute materialization, authorize completeness
verification, or authorize backtest execution. The `Authorized by P0` table
column above is the P0 freeze snapshot.

Live `S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a-completeness-verification-authorization.md`.
Completeness verification grant does not execute verification, flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, or authorize backtest
execution. P0 §4.2 `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false` remains
the P0 freeze snapshot.

Live `S3_A2_EVALUATION_INSTANCE_REGISTRY_CONTRACT_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-evaluation-instance-registry.md`.
Registry contract freeze does not implement the registry, materialize cell rows,
flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots remain
historical.

Live `S3_A2_EVALUATION_INSTANCE_REGISTRY_IMPLEMENTATION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-registry-implementation-authorization.md`.
Registry implementation grant does not execute registry implementation, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, or authorize backtest execution.
P0 §4.2 freeze snapshots remain historical.

Live `EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-registry-implementation-r1.md`.
R1 implementation delivers the deterministic in-memory registry service only;
it does not flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE` or
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots remain
historical.

Live `S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_CONTRACT_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-catalog-binding-contract.md`.
Catalog binding contract freeze defines how a future versioned catalog may be
bound; it does not bind a catalog, flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`,
or flip `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots
remain historical.

Live `S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_IMPLEMENTATION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-catalog-binding-authorization.md`.
Catalog binding implementation grant does not implement the binder, bind a catalog,
flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, or authorize backtest execution.
P0 §4.2 freeze snapshots remain historical.

Live `DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_BINDING_SERVICE_IMPLEMENTED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-catalog-binding-implementation-r1.md`.
Catalog binding R1 delivers the in-memory structural validator only; it does not
bind a live catalog, flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots remain
historical.

Live `S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_CONTRACT_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-catalog-artifact-contract.md`.
Catalog artifact contract freeze defines how a future versioned catalog may be
produced and accepted; it does not produce a catalog, bind a catalog, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots remain
historical.

Live `S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_PRODUCTION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-catalog-artifact-authorization.md`.
Catalog artifact production grant does not produce a catalog, bind a catalog,
flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, or authorize backtest execution.
P0 §4.2 freeze snapshots remain historical.

Live `DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_ARTIFACT_SERVICE_IMPLEMENTED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-catalog-artifact-production-r1.md`.
Catalog artifact production R1 delivers the in-memory production service only; it does not
write a live bindable catalog into the repository, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots remain
historical.

## 12. Phase-entry effect on development plan

P0 phase entry sets `V0_3_S3_IMPLEMENTATION_AUTHORIZED=true` in
`docs/v0-3/development-plan.md` §12. That boolean means the slice may begin
controlled subtasks under separate authorization. It does **not** mean:

- S3 is complete (`CURRENT_V0_3_S3_COMPLETE` remains `false`)
- `SLICE_S3_COMPLETE` registry row may pass
- backtest code may be written or executed
- TEST may be evaluated
- S4 is authorized

~~~text
V0_3_S3_IMPLEMENTATION_AUTHORIZED_MEANING=CONTROLLED_SUBTASKS_MAY_BE_PLANNED
V0_3_S3_IMPLEMENTATION_AUTHORIZED_DOES_NOT_MEAN_BACKTEST_EXECUTION=true
CONTRACT_MERGE_DOES_NOT_AUTHORIZE_BACKTEST=true
~~~
