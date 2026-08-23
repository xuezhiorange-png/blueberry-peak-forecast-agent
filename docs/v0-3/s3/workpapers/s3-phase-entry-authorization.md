# V0.3-S3 phase-entry authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_PHASE_ENTRY_AUTHORIZATION
ARTIFACT_VERSION=s3-phase-entry-authorization-v1
TASK_ID=V03_S3_P0_PHASE_ENTRY_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_S3_PHASE_ENTRY
AUTHORIZATION_SCOPE=S3_P0_CONTRACT_FREEZE_ONLY
SLICE=V0.3-S3
ENGLISH_ID=CURRENT_MODEL_POINT_IN_TIME_BACKTEST_AND_ERROR_DIAGNOSIS
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
USER_WAIVED_THIRD_PARTY_REVIEW=true
COORDINATOR_REVIEW_COUNTS=true
COORDINATOR_AGENT=https://cursor.com/agents/bc-01a02307-c032-7da6-8a02-00d9b3518794
DOCS_ONLY_AGENT=https://cursor.com/agents/bc-01a02a06-2694-7db3-bffe-cbcc33b2c1a2
AUDITED_REPOSITORY_SHA=9a68698c0ff5454708d0bd52596788d9dfb6cc8f
AUDITED_REPOSITORY_TREE_SHA=85fbc852dd730a408226652b2fb2b790849a9256
AUDITED_REF=origin/main
CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-phase-entry-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-phase-entry-authorization.json
EVIDENCE_JSON_SHA256=580f09e306e4e32db0e72d65158d455bd9fea57b4279497909ff0d54cb91259c
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This document records the V0.3-S3 slice phase entry after user authorization
「可以实施」 and after S2 acceptance (#296) and registry closeout (#297) are on
`main`. This PR freezes the S3 P0 contract and sets
`V0_3_S3_IMPLEMENTATION_AUTHORIZED=true`. It does not execute backtests, read
TEST, change the model, or complete S3.

~~~text
V0_3_S3_PHASE_ENTRY_AUTHORIZED=true
S3_CONTRACT_FREEZE_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
S3_BACKTEST_EXECUTION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
V0_3_S4_AUTHORIZED=false
CONTRACT_MERGE_DOES_NOT_AUTHORIZE_BACKTEST=true
~~~

## 1. Prerequisites on main (bound; not recomputed)

### 1.1 S2 accepted and registry PASS

~~~text
S2_ACCEPTANCE_PR=296
S2_REGISTRY_CLOSEOUT_PR=297
CURRENT_V0_3_S2_COMPLETE=true
CURRENT_V0_3_S2_ACCEPTANCE_STATUS=ACCEPTED
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_ROW_COUNT=16224
VALIDATION_ROW_COUNT=8006
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
TEST_IS_SEALED_PLACEHOLDER=true
~~~

### 1.2 S1 bindings (accepted)

~~~text
Q2C_ACCEPTED=true
V0_3_METRIC_CONTRACT_VERSION=v0.3-metric-contract-v1
EXTERNAL_HOLDOUT_OWNER_DECISION=REVIEWED_NOT_FEASIBLE
EXTERNAL_HOLDOUT_NOT_APPLICABLE=true
~~~

## 2. What this PR does

1. Creates `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` (P0 contract
   freeze).
2. Sets `V0_3_S3_IMPLEMENTATION_AUTHORIZED=false` → `true` in
   `docs/v0-3/development-plan.md` §12 only.

The boolean change means controlled S3 subtasks may be planned under separate
authorization. It is **not** S3 completion and **not** backtest execution
authorization.

## 3. What this PR does not do

~~~text
CURRENT_V0_3_S3_COMPLETE=false
SLICE_S3_COMPLETE_REGISTRY_ROW_UNCHANGED=true
NEXT_TASK_UNCHANGED=V0_3_S1
S2_CONTRACT_UNCHANGED=true
S2_ACCEPTANCE_ARCHIVE_UNCHANGED=true
S2_REGISTRY_CLOSEOUT_UNCHANGED=true
V0_2_METRIC_CONTRACT_UNCHANGED=true
NO_PRODUCTION_CODE=true
NO_TEST_CODE=true
NO_BACKTEST_RUN=true
NO_TEST_READ=true
NO_MODEL_CHANGE=true
~~~

## 4. V0.2 vs V0.3 input authority distinction

The frozen V0.2 metric contract names `S3_INPUT_AUTHORITY=S2_IMMUTABLE_BACKTEST_BINDING`
for historical V0.2 backtest pairing. V0.3-S3 actuals authority is the accepted
V0.3-S2 materialized dataset `source-002/e5-live-v1` TRAIN and VALIDATION
partitions. These must not be conflated in implementation or documentation.

~~~text
V0_2_S3_INPUT_AUTHORITY=S2_IMMUTABLE_BACKTEST_BINDING
V0_3_S3_ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
V0_3_S3_VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
CONFLATION_FORBIDDEN=true
~~~

## 5. P0 contract key boundaries

- S3 diagnosis uses TRAIN + VALIDATION only; TEST remains sealed.
- `MISSING_DAY_POLICY=UNKNOWN_NOT_ZERO`; no zero-fill for missing days.
- Complete daily rowset is `NOT_AVAILABLE_FROM_CURRENT_S2_BINDING`; peak and
  cumulative metrics are `NOT_COMPUTABLE` until S3-A amendment (not authorized).
- Quantile semantics are `NOT_VERIFIED`; coverage is `NOT_COMPUTABLE`.
- Product 3-day vs plan 7-day sustained peak conflict is `UNRESOLVED`; P0 does
  not resolve it.
- Future acceptance gates (`POINT_IN_TIME_REPLAY`, `LEAKAGE_AUDIT`,
  `CURRENT_MODEL_BASELINE`, `ERROR_DIAGNOSIS`, `SLICE_S3_COMPLETE`) are all
  `false`.

## 6. Subtask roadmap (not authorized)

~~~text
S3_P0=this contract (authorized contract-only)
S3_A=daily rowset amendment contract (not authorized)
S3_B=quantile semantics verification (not authorized)
S3_C=TRAIN/VAL PIT backtest execution (not authorized)
S3_D=error attribution matrix (not authorized)
next_subtask_not_implied=true
~~~

## 7. Development-plan mutation accounting

~~~text
DEVELOPMENT_PLAN_MUTATION_COUNT=1
DEVELOPMENT_PLAN_MUTATED_FIELD=V0_3_S3_IMPLEMENTATION_AUTHORIZED
DEVELOPMENT_PLAN_MUTATION_BEFORE=false
DEVELOPMENT_PLAN_MUTATION_AFTER=true
OTHER_DEVELOPMENT_PLAN_FIELDS_UNCHANGED=true
~~~

Explicitly unchanged:

~~~text
CURRENT_V0_3_S3_COMPLETE=false
SLICE_S3_COMPLETE=BLOCKED
NEXT_TASK=V0_3_S1
V0_3_S3_AUTHORIZED=false
~~~

## 8. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
CONTRACT_MERGE_IS_NOT_BACKTEST_EXECUTION=true
AWAITING_COORDINATOR_REVIEW=true
~~~
