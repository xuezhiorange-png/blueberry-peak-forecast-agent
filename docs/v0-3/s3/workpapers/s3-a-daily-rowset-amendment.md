# V0.3-S3-A daily rowset amendment contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A_DAILY_ROWSET_AMENDMENT
ARTIFACT_VERSION=s3-a-daily-rowset-amendment-v1
TASK_ID=V03_S3_A_DAILY_ROWSET_AMENDMENT_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A_DAILY_ROWSET_AMENDMENT_CONTRACT_ONLY
SLICE=V0.3-S3
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
USER_WAIVED_THIRD_PARTY_REVIEW=true
COORDINATOR_REVIEW_COUNTS=true
COORDINATOR_AGENT=https://cursor.com/agents/bc-01a02307-c032-7da6-8a02-00d9b3518794
DOCS_ONLY_AGENT=https://cursor.com/agents/bc-01a02a06-2694-7db3-bffe-cbcc33b2c1a2
AUDITED_REPOSITORY_SHA=0a6f412aad63e1f66a5e14e5960ca88deb9b2dcd
AUDITED_REPOSITORY_TREE_SHA=281d6ecae3daca2acc52e3a7be6522acf12df8ae
AUDITED_REF=origin/main
AMENDMENT_PATH=docs/v0-3/s3/s3-daily-rowset-amendment.md
AMENDMENT_VERSION=v0-3-s3-daily-rowset-amendment-v1
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a-daily-rowset-amendment.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a-daily-rowset-amendment.json
EVIDENCE_JSON_SHA256=b50948c9529dd7f87b844e61e48fbb3b89d6eae31211f43d6fc5189360553e0a
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This workpaper records the S3-A daily rowset amendment contract freeze after
user authorization 「可以下一步」 and after S3 P0 contract merge (PR #298). This
PR defines how sparse SOURCE_002 grains expand into a complete calendar daily
row set. It does not materialize rows, verify completeness, execute backtests,
or change the model.

~~~text
S3_A_DAILY_ROWSET_AMENDMENT_CONTRACT_AUTHORIZED=true
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=false
S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED=false
S3_BACKTEST_EXECUTION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

## 1. Parent P0 binding

~~~text
P0_PR=298
P0_MERGE=0a6f412aad63e1f66a5e14e5960ca88deb9b2dcd
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
P0_CONTRACT_VERSION=v0-3-s3-backtest-and-diagnosis-contract-v1
P0_CONTRACT_GIT_BLOB_SHA=500896b8150c232e4476e98253b5a7439850001d
P0_CONTRACT_SHA256=090acecf54409b86aadaee61cee00a1dd4880450f3f22d183474e00910130bc1
P0_EVIDENCE_JSON_SHA256=580f09e306e4e32db0e72d65158d455bd9fea57b4279497909ff0d54cb91259c
~~~

P0 left `CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE=false` and delegated the
operational definition to S3-A. This task supplies that definition only.

## 2. Bound S2 facts (not recomputed)

~~~text
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_ROW_COUNT=16224
VALIDATION_ROW_COUNT=8006
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
CANONICAL_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
V0_3_S3_ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
V0_3_S3_VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
~~~

## 3. Authority distinction

~~~text
V0_2_S3_INPUT_AUTHORITY=S2_IMMUTABLE_BACKTEST_BINDING
V0_3_S3_ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
CONFLATION_FORBIDDEN=true
SPARSE_7_14_21_HORIZON_ROWS_ARE_NOT_COMPLETE_DAILY_CURVE=true
~~~

## 4. S3-A contract core semantics

### 4.1 Terminology

- `forecast_horizon_days` ≠ `evaluation_window_days`
- 7/14/21 horizon rows are sparse target dates, not continuous daily curves

### 4.2 Missing-day

~~~text
MISSING_DAY_POLICY=UNKNOWN_NOT_ZERO
MISSING_DAY_ZERO_FILL=false
NUMERIC_IMPUTATION_ALLOWED=false
WINDOW_REJECTION_ON_UNKNOWN_OR_MISSING_DAY=true
~~~

### 4.3 Calendar expansion

For each evaluation instance cell and requested window:

- every calendar day has an explicit row with status
  `OBSERVED | UNKNOWN | EXCLUDED`
- silent missing days forbidden
- `OBSERVED` kg from accepted S2 Decimal grains only
- `UNKNOWN` kg is null/absent, never 0
- forecast replay at cutoff; `FORECAST_UNAVAILABLE` rejects window
- `PEAK_OVER_OBSERVED_DAYS_ONLY=false`

### 4.4 Metric computability (definition only)

~~~text
DAILY_POINT_METRICS_NOT_BLOCKED_BY_COMPLETE_DAILY_ROWSET=true
PEAK_CUMULATIVE_COMPLETE_HORIZON_BLOCKED_UNTIL_COMPLETENESS_VERIFIED=true
COVERAGE_BLOCKED_BY_S3_B=true
SUSTAINED_3_VS_7_UNRESOLVED=true
SUSTAINED_PEAK_PASS_FORBIDDEN_UNTIL_OWNER_DECISION=true
BLOCKER_REASON_WHILE_UNVERIFIED=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
~~~

### 4.5 Identity sentinels

~~~text
S3_DAILY_ROW_SET_IDENTITY=NOT_MATERIALIZED
S3_DAILY_ROW_SET_HASH=NOT_MATERIALIZED
S3_DAILY_ROW_SET_COMPLETENESS_STATUS=BLOCKED_PENDING_MATERIALIZATION_AND_VERIFICATION
DO_NOT_INVENT_MATERIALIZED_HASH=true
~~~

## 5. Current status flags (unchanged by this PR)

~~~text
CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
DEVELOPMENT_PLAN_CURRENT_FIELDS_UNCHANGED=true
~~~

Coordinator closeout will flip `CURRENT_*` fields after separate acceptance.
This PR does not edit `development-plan.md`.

## 6. Optional P0 pointer patch

If applied, P0 receives only:

~~~text
S3_A_AUTHORIZED=true
S3_A_AMENDMENT_PATH=docs/v0-3/s3/s3-daily-rowset-amendment.md
S3_A_AMENDMENT_VERSION=v0-3-s3-daily-rowset-amendment-v1
~~~

P0 identity block, `CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE`, and
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED` remain unchanged.

## 7. Not authorized

~~~text
S3_B_AUTHORIZED=false
S3_C_AUTHORIZED=false
S3_D_AUTHORIZED=false
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=false
S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED=false
next_subtask_not_implied=true
~~~

## 8. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AMENDMENT_MERGE_IS_NOT_MATERIALIZATION=true
AMENDMENT_MERGE_IS_NOT_BACKTEST=true
AWAITING_COORDINATOR_REVIEW=true
~~~
