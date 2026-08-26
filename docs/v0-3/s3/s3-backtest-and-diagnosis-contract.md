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

Live `S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-contract.md`.
Incumbent forecast artifact contract freeze defines how a future versioned forecast
input artifact may be identified and accepted; it does not implement an adapter,
write forecast artifacts, produce catalogs, bind catalogs, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots remain
historical.

Live `S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-authorization.md`.
Incumbent forecast artifact implementation grant does not implement an adapter,
write versioned forecast artifacts, produce catalogs, bind catalogs, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, or authorize backtest execution.
P0 §4.2 freeze snapshots remain historical.

Live `DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-adapter-r1.md`.
Incumbent forecast artifact adapter R1 delivers the in-memory live adapter only; it does not
write versioned forecast artifacts into the repository, implement S2 identity alignment, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots remain
historical.

Live `S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-contract.md`.
S2 identity alignment contract freeze defines how a future `S2IdentityAlignmentPort` live
adapter may project accepted S2 TRAIN/VALIDATION identities; it does not implement an
adapter, write forecast artifacts, produce catalogs, bind catalogs, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots remain
historical.

Live `S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-authorization.md`.
S2 identity alignment implementation grant does not implement an adapter, write
forecast artifacts, produce catalogs, bind catalogs, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, or authorize backtest execution.
P0 §4.2 freeze snapshots remain historical.

Live `S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED` semantics are amended
by `docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-authorization-amendment-r1.md`
and `docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-authorization-amendment-r1.json`
(`EVIDENCE_JSON_SHA256=c4d26633413dcde42b989684c1eb372443f5598c210d6a920dc51e50bc4093a4`)
only within the test-only structural `BOUND_FIXTURE` scope. `BOUND_FIXTURE` is not
live alignment authority; live alignment may use only
`SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT`. The original authorization
workpaper and evidence JSON are not rewritten. This amendment does not implement
an adapter, flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, or authorize backtest execution.
P0 §4.2 freeze snapshots remain historical.

Live `DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-adapter-r1.md`.
S2 identity alignment adapter R1 delivers the in-memory live adapter only; it does not
write live S2 alignment facts into the repository, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots remain
historical.

Live `S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-accepted-s2-identity-alignment-evidence-contract.md`
(`EVIDENCE_JSON_SHA256=2bdb9a578592dadd8cf9d15a8071d46f9983e7bb973159d0c3b6ec21b5725add`).
Accepted S2 identity alignment evidence producer contract defines how a future
deterministic producer may construct `VersionedAcceptedS2IdentityAlignmentEvidence`
for injection into `S2IdentityAlignmentAdapter`; it does not implement a producer,
write live S2 identity facts into the repository, produce catalogs, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots remain
historical.

Live `S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IMPLEMENTATION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-accepted-s2-identity-alignment-evidence-authorization.md`
(`EVIDENCE_JSON_SHA256=7a9fb4be04a165cb83cda2c09585b54624401cc9c004c5e48c49496913dce52e`).
Accepted S2 identity alignment evidence producer implementation grant records what a
later deterministic producer may do; it does not implement a producer, write live S2
identity facts into the repository, produce catalogs, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots remain
historical.


Live `DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-accepted-s2-identity-alignment-evidence-producer-r1.md`
(`EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3`).
Accepted S2 identity alignment evidence producer R1 delivers the in-memory harvest-grain
projector only; it does not write live S2 alignment facts into the repository, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots remain
historical.

Live `S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-content-contract.md`
(`EVIDENCE_JSON_SHA256=6294f2028509f2b1021741ac7aea3f20efdcbe07669b87a1782d18c0a5ca9eae`).
Incumbent forecast artifact content producer contract defines how a future deterministic
producer may construct `VersionedIncumbentForecastArtifact` for injection into
`IncumbentForecastArtifactAdapter`; it does not implement a producer, write live forecast
artifacts into the repository, produce catalogs, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots remain
historical.

Live `S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_IMPLEMENTATION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-content-authorization.md`
(`EVIDENCE_JSON_SHA256=29a486d5fa04542404c6629509ee65ebdf3931c30cf758db643faf93cfd35a38`).
Incumbent forecast artifact content producer implementation grant records what a
later deterministic content producer may do; it does not implement a producer,
write live forecast artifacts into the repository, produce catalogs, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots remain
historical.


Live `DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-content-producer-r1.md`
(`EVIDENCE_JSON_SHA256=d159c010b4f527972e7554789e85808ae48e11941499c6f597f124fd471ff228`).
Incumbent forecast artifact content producer R1 delivers the in-memory replay-row
projector only; it does not write live forecast artifacts into the repository, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots remain
historical.

Live `S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-source-contract.md`
(`EVIDENCE_JSON_SHA256=59e452eedc6b8db82063d11ccaf7af177447074c7ad68565b31a6d86d5d4b457`).
Incumbent forecast replay source contract defines how a future deterministic replay
source may obtain injectable rows for the landed
`IncumbentForecastArtifactContentProducer`; it does not implement a replay source,
wire producer/adapter defaults, write live forecast artifacts into the repository,
produce catalogs, flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots remain
historical.

Live `S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTATION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-source-authorization.md`
(`EVIDENCE_JSON_SHA256=601e06ac1d679d7fb165a481cc01c27dd01fdd68e5a0d9699098c214ba88c890`).
Incumbent forecast replay source implementation grant records what a later
deterministic replay source R1 may do; it does not implement a replay source, wire
producer/adapter defaults, write live forecast artifacts into the repository,
produce catalogs, flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots remain
historical.


Live `DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-source-r1.md`
(`EVIDENCE_JSON_SHA256=59a198c38c0c1e8e17a718bb5623943c4035b4b9b582e2216b922d526b508929`).
Incumbent forecast replay source R1 delivers the in-memory replay-row obtain service
only; it does not write live forecast artifacts into the repository, wire producer or
adapter defaults, flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`. P0 §4.2 freeze snapshots remain
historical.

Live `S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-live-source-kind-contract.md`
(`EVIDENCE_JSON_SHA256=2d0cce5d0c0f89c136014a2abbd01d67ef0004786c63050115d55a2dc0519ee1`).
Incumbent forecast live source kind contract freezes when live forecast
`catalog_source_kind` may be claimed (`V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF`
only), which kinds must never impersonate it, and why live kind is necessary but not
sufficient for bindable catalog; it does not implement code, modify `registry.py`,
write live forecast artifacts, or flip `NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.
`DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED` remains `false`.

Live `S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTATION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-live-source-kind-authorization.md`
(`EVIDENCE_JSON_SHA256=759644330a0063560f11e53a74a92b03dbb6221ab6c58f523a74462dc145fa9e`).
Incumbent forecast live source kind implementation grant records what a later
deterministic R1 may do when the user again says 「可以实施」: land
`CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF` and add tests;
it does not implement code, wire producer/adapter defaults, write live forecast
artifacts, or flip `NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.
`DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED` remains `false`.

Live `DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-live-source-kind-r1.md`
(`EVIDENCE_JSON_SHA256=3a7a1f4f74074630c4eedb658ca361db579e16b1f7e4630f51b04266fa963a7a`).
Incumbent forecast live source kind R1 lands
`CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF` in `registry.py` only;
it does not wire producer/adapter defaults, write live forecast artifacts into the
repository, or flip `NO_VERSIONED` / `AVAILABLE` / `VERIFIED`. Historical grant and
contract pointer snapshots may remain `false`.

Live `S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-live-envelope-contract.md`
(`EVIDENCE_JSON_SHA256=9b67eabc5ae01f5e834dda4d8321208198a4bef3ad3e1d5f6a3bdf2fe5ed27d4`).
Incumbent forecast live envelope contract freezes deterministic
`catalog_source_kind` envelope assignment on produced forecast artifacts; it does not
implement assignment logic, wire obtain→produce→adapter, write live forecast
artifacts, or flip `NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.
`DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED` remains `false`.

Live `S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTATION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-live-envelope-authorization.md`
(`EVIDENCE_JSON_SHA256=86d6937c11783d1c95aa6da5de281b749c1272092b452383f2bc27b1c33544b5`).
Incumbent forecast live envelope implementation grant records what a later
deterministic R1 may do when the user again says 「可以实施」: implement parent
contract §3 envelope assignment on `IncumbentForecastArtifactContentProducer` via
optional `declared_catalog_source_kind`; it does not implement assignment logic,
wire obtain→produce→adapter, write live forecast artifacts, or flip
`NO_VERSIONED` / `AVAILABLE` / `VERIFIED`. `DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED`
remains `false` until a separate implementation R1.

Live `DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-live-envelope-r1.md`
(`EVIDENCE_JSON_SHA256=164b2396091dc5b2daf790f09c92e9ebf628c6e577a37acdc6e4dc0c88b3e601`).
Incumbent forecast live envelope R1 implements parent contract §3 envelope
assignment on `IncumbentForecastArtifactContentProducer` via optional
`declared_catalog_source_kind`; it does not wire obtain→produce→adapter defaults,
write live forecast artifacts into the repository, or flip `NO_VERSIONED` /
`AVAILABLE` / `VERIFIED`. Historical grant and contract pointer snapshots may
remain `false`.

Live `S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_CONTRACT_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-fail-closed-wiring-contract.md`
(`EVIDENCE_JSON_SHA256=2ea44667836957fa736828cbd4ae123c5d2144a43918939ab4d494f4cbcaf1ff`).
Incumbent forecast fail-closed wiring contract freezes deterministic obtain→produce→adapter
default-chain behavior; it does not implement wiring, authorize V0.2 obtain, or flip
`NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.
`DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED` remains `false`.

Live `S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTATION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-fail-closed-wiring-authorization.md`
(`EVIDENCE_JSON_SHA256=84c4491daefa59f74d875f7b311612efbead4143688b5582c499981fe82210e0`).
Incumbent forecast fail-closed wiring implementation grant records what a later
deterministic wiring R1 may do when the user again says 「可以实施」: implement parent
contract §3 obtain→produce→adapter default-chain wiring; it does not implement wiring,
authorize V0.2 obtain, or flip `NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.
`DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED` remains `false`
until a separate implementation R1.


Live `DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-fail-closed-wiring-r1.md`
(`EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e`).
Incumbent forecast fail-closed wiring R1 wires obtain→produce→adapter defaults while
empty obtain remains fail-closed; it does not implement V0.2 postgres obtain, wire
alignment producer→adapter, or flip `NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.
Historical grant and contract pointer snapshots may remain `false`.


Live `S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-postgres-obtain-contract.md`
(`EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49`).
Incumbent forecast V0.2 postgres obtain contract freezes empty-default obtain authority
from named V0.2 point-in-time replay; it does not implement postgres reading, invent SQL
or table names, or flip `NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED` remains `false`.


Live `S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTATION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-postgres-obtain-authorization.md`
(`EVIDENCE_JSON_SHA256=6b3655921acd896f0570e0c01fbcb5a85478018c8c968bb84c26a02567253bdd`).
Incumbent forecast V0.2 postgres obtain implementation grant records what a later
deterministic obtain R1 may do when the user again says 「可以实施」: implement parent
contract §3.2 empty-default obtain from named V0.2 point-in-time replay; it does not
implement postgres reading, invent SQL or table names, or flip `NO_VERSIONED` /
`AVAILABLE` / `VERIFIED`.
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED` remains `false`
until a separate implementation R1.


Live `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-postgres-obtain-r1.md`
(`EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10`).
Incumbent forecast V0.2 postgres obtain R1 lands the empty-default fail-closed
postgres obtain path; repository contracts contain no frozen SQL or table names so
default `obtain()` remains `()`. It does not flip `NO_VERSIONED` / `AVAILABLE` /
`VERIFIED` or wire alignment producer→adapter. Historical grant and contract
pointer snapshots may remain `false`.


Live `S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-producer-adapter-wiring-contract.md`
(`EVIDENCE_JSON_SHA256=89e4a35e68d70d942df0c795953573828618d62ac3caddc78dba5609608ec36a`).
S2 identity alignment producer→adapter wiring contract freezes fail-closed default wiring
authority from producer `produce()` into adapter `evidence`; it does not implement wiring,
invent harvest rows or SQL, or flip `NO_LIVE_S2` / `NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.
`DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED` remains `false`.


Live `S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-producer-adapter-wiring-authorization.md`
(`EVIDENCE_JSON_SHA256=7a4a758259f3e5a54ef01ac623f822fc3bafb2a04c0031d040e8fb2332506f6f`).
S2 identity alignment producer→adapter wiring implementation grant records what a later
deterministic wiring R1 may do when the user again says 「可以实施」: implement parent
contract §3.2 default producer→adapter wiring in `catalog_artifact.py`; it does not
implement wiring, invent harvest rows or SQL, or flip `NO_LIVE_S2` / `NO_VERSIONED` /
`AVAILABLE` / `VERIFIED`.
`DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED` remains `false`
until a separate implementation R1.


Live `DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-producer-adapter-wiring-r1.md`
(`EVIDENCE_JSON_SHA256=1349db0e8ef64f99250ae965b99fbba52d817f682201286852dccaa3df20c579`).
S2 identity alignment producer→adapter wiring R1 wires default
`AcceptedS2IdentityAlignmentEvidenceProducer.produce()` into
`S2IdentityAlignmentAdapter.evidence`; default `harvest_rows=()` still yields
`evidence=None`. It does not flip `NO_LIVE_S2` / `NO_VERSIONED` / `AVAILABLE` /
`VERIFIED` or read SOURCE_002 row-level harvest. Historical grant and contract
pointer snapshots may remain `false`.


Live `S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-harvest-source-contract.md`
(`EVIDENCE_JSON_SHA256=92da3bc9ffab3cb90c825292e8c53f79b1ce5d6abc2ff0ccbedda8b31ba6cb3a`).
S2 identity alignment harvest source contract freezes fail-closed upstream harvest
authority for `MaterializableRow` tuples; it does not implement obtain, invent harvest
rows or SQL, or flip `NO_LIVE_S2` / `NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.
`DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED` remains `false`.


Live `S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTATION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-harvest-source-authorization.md`
(`EVIDENCE_JSON_SHA256=bad95719d0f2af0481093251707643ec6aa69fc299770d27e7a52e3703d24c64`).
S2 identity alignment harvest source implementation authorization records what a later
deterministic harvest source R1 may do when the user again says 「可以实施」; it does not
implement obtain, invent harvest rows or SQL, or flip `NO_LIVE_S2` / `NO_VERSIONED` /
`AVAILABLE` / `VERIFIED`. `DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED` remains `false` until a separate implementation R1.


Live `DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-harvest-source-r1.md`
(`EVIDENCE_JSON_SHA256=bef3cedecf7498064f9929e7c40b863ed8ad028d0cf0e9f30e7b547bc7af408e`). S2 identity alignment harvest source R1 adds
in-memory obtain seam and producer fallback; default `harvest_rows=()` and default
`obtain()=()` still yield `produce()=None`. It does not flip `NO_LIVE_S2` / `NO_VERSIONED` /
`AVAILABLE` / `VERIFIED` or read SOURCE_002 row-level harvest. Historical grant and contract
pointer snapshots may remain `false`.


Live `S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_CONTRACT_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-sql-table-authority-contract.md`
(`EVIDENCE_JSON_SHA256=99e4bb4853b6020404a86221c470936fce27f26bb6373fbe81167ffaeac6e260`).
Incumbent forecast V0.2/S3 SQL table-name authority contract freezes a read-only
Alembic audit at `2cfc2c0`: zero `MATCH` table names for replay grain
`DISTINCT(forecast_cutoff_at, model_id, forecast_quantile)`; default obtain remains
fail-closed `()`. It does not implement live postgres read, invent SQL or table names,
or flip `NO_VERSIONED` / `NO_LIVE_S2` / `AVAILABLE` / `VERIFIED`.
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED` remains `false`.


Live `S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_IMPLEMENTATION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-sql-table-authority-authorization.md`
(`EVIDENCE_JSON_SHA256=8262b9350f59db13ecf67e87734ca6dc9caf58f8c4689c64a331a36b551f1cfd`).
Incumbent forecast V0.2/S3 SQL table-name authority implementation authorization records what a
later deterministic R1 may do when the user again says 「可以实施」: encode the frozen empty
bindable-name set as in-memory authority while default obtain remains `()`. It does not implement
live postgres read, invent SQL or table names, or flip `NO_VERSIONED` / `NO_LIVE_S2` / `AVAILABLE` /
`VERIFIED`. `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_IMPLEMENTED` and
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED` remain `false` until separate implementation R1.


Live `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_IMPLEMENTED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-sql-table-authority-r1.md`
(`EVIDENCE_JSON_SHA256=aad30ef4b0f6b16cbdab8aab4571f231e46758b138ab636d7b20208c55a39218`). SQL table-name authority R1 encodes the frozen
empty bindable-name set in memory; default `obtain()` remains `()` without postgres I/O. It does
not flip live postgres read or flip `NO_VERSIONED` / `NO_LIVE_S2` / `AVAILABLE` / `VERIFIED`.
Historical grant and contract pointer snapshots may remain `false`.


Live `S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-identity-persistence-schema-contract.md`
(`EVIDENCE_JSON_SHA256=b0c2553f3a561bf8c46b39f015a604f31f9c6a9c5d682a060ad5eff0dfbfb806`). This contract
freezes future object `s3_incumbent_forecast_replay_identity`; the object does not exist in Alembic
today. It does not add Alembic, implement live postgres read, populate rows, or flip `NO_VERSIONED`.
`DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED` and
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED` remain `false`.

Live `S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTATION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-identity-persistence-schema-authorization.md`
(`EVIDENCE_JSON_SHA256=f58fa58c9f3e815c2a987903d1ec4f2ef6818008cba966c57b1b9ccfafdf6e01`). Incumbent forecast replay-identity persistence schema implementation
authorization records what a later deterministic schema R1 may do when the user again says
「可以实施」: create the frozen empty table `s3_incumbent_forecast_replay_identity` via one linear
Alembic revision. This grant does not add Alembic, write SQL, populate rows, or flip `NO_VERSIONED` /
`NO_BINDABLE_V0_2` / `LIVE_POSTGRES_READ`. Authorization merge does not close S3.
`DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED` and
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED` remain `false`. A later schema
R1 flips only `SCHEMA_IMPLEMENTED`, not `LIVE_POSTGRES_READ`.

Live `DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-identity-persistence-schema-r1.md`
(`EVIDENCE_JSON_SHA256=921df3fd317213eeaf44fe594e72650ac7dea84d8499ca915c5f627fe60e3599`). Schema R1 creates the frozen empty Alembic table
`s3_incumbent_forecast_replay_identity` with 0 upgrade rows. Empty table ≠ versioned incumbent forecast artifact.
Empty table ≠ bindable V0.2 SQL table name. Empty table ≠ live postgres read. Default `obtain()` remains `()`.
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED` remains `false`. This R1 flips only
`SCHEMA_IMPLEMENTED`, not `LIVE_POSTGRES_READ`. Historical grant and contract pointer snapshots may remain `false`
for `FROZEN_FUTURE_OBJECT_EXISTS_IN_ALEMBIC`.

Live `S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-identity-bindable-name-contract.md`
(`EVIDENCE_JSON_SHA256=34827903ef67de35958cd0e967b1b008ccde1ed90803bc81a4c1fdc6d1467f14`). Incumbent forecast replay-identity bindable name contract freezes
coordinator-reviewed bindable name `s3_incumbent_forecast_replay_identity` for the now-existing empty
Alembic table (0 rows at review). Table existence ≠ bindable implementation. This contract does not
implement live postgres read, populate rows, flip `NO_BINDABLE_V0_2`, flip `NO_VERSIONED`, or change
default `obtain()`. `DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED` and
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED` remain `false`. A later
bindable-name R1 flips only `BINDABLE_NAME_IMPLEMENTED` (and `NO_BINDABLE_V0_2`), not `LIVE_POSTGRES_READ`.

Live `S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTATION_AUTHORIZED` is maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-identity-bindable-name-authorization.md`
(`EVIDENCE_JSON_SHA256=b745ccdc0a5084368852041337d5409d0c8aad4c93183070a573a35167df604d`). Incumbent forecast replay-identity bindable name implementation authorization
records what a later deterministic bindable-name R1 may do when the user again says 「可以实施」: record
frozen name `s3_incumbent_forecast_replay_identity` in deterministic code. Grant ≠ bindable-name encoding ≠
live postgres read ≠ versioned forecast artifact. Empty table + reviewed name + unused grant still yields
`obtain()=()`. Later live-read of the empty table still yields `()`. This grant does not encode bindable
names, populate rows, flip `NO_BINDABLE_V0_2`, flip `NO_VERSIONED`, or implement live postgres read.
`DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED` and
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED` remain `false`. A later bindable-name
R1 flips only `BINDABLE_NAME_IMPLEMENTED` (and `NO_BINDABLE_V0_2`), not `LIVE_POSTGRES_READ`. Jumping to
live-read now is forbidden.

Live `DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED` and
`NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY` are maintained in
`docs/v0-3/development-plan.md` §4.4 live state block and
`docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-identity-bindable-name-r1.md`
(`EVIDENCE_JSON_SHA256=121d677c6645f87162a0108649f73aec1e825f1901148170d55179f9aa17543d`). Bindable-name R1 encodes frozen name
`s3_incumbent_forecast_replay_identity` in deterministic authority code only. Encoding the name
≠ live postgres read ≠ versioned forecast artifact. Empty table still has 0 rows. Default
`obtain()` remains `()`. This R1 flips only `BINDABLE_NAME_IMPLEMENTED` and `NO_BINDABLE_V0_2`,
not `LIVE_POSTGRES_READ`. Historical grant and contract pointer snapshots may remain
`NO_BINDABLE_V0_2=true`.

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
