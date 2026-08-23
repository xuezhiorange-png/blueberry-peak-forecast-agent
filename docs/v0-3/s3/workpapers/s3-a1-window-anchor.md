# V0.3-S3-A1 evaluation-window anchor and in-window EXCLUDED

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A1_WINDOW_ANCHOR_AND_EXCLUDED
ARTIFACT_VERSION=s3-a1-window-anchor-v1
TASK_ID=V03_S3_A1_WINDOW_ANCHOR_AND_EXCLUDED_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A1_WINDOW_ANCHOR_AND_EXCLUDED_ONLY
PARALLEL_LANE=S3-A1
SLICE=V0.3-S3
USER_GATE=可以下一步 并行开发
REVIEWER_ROLE=COORDINATOR
COORDINATOR_AGENT=https://cursor.com/agents/bc-01a02307-c032-7da6-8a02-00d9b3518794
AUDITED_REPOSITORY_SHA=fd793de12bfe2df646925d9e7adc1d59c046ecdf
AUDITED_REPOSITORY_TREE_SHA=61d8550f1311e3c0949f5bf08814fc69ddf0fde5
AUDITED_REF=origin/main
S3_A_PR=299
S3_A_MERGE=fd793de12bfe2df646925d9e7adc1d59c046ecdf
S3_A_AMENDMENT_PATH=docs/v0-3/s3/s3-daily-rowset-amendment.md
S3_A_AMENDMENT_GIT_BLOB_SHA=1baf930287598f5df78ac28d49c159b4231c0fc6
S3_A_AMENDMENT_SHA256=f2b2473bd7ebe52349010403cbcc45a8a18f3ae7ad3512c97d8b2a30b205a7be
S3_A_EVIDENCE_JSON_SHA256=b50948c9529dd7f87b844e61e48fbb3b89d6eae31211f43d6fc5189360553e0a
TIMEZONE=Asia/Shanghai
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a1-window-anchor.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a1-window-anchor.json
EVIDENCE_JSON_SHA256=7d5e915bf1eb8b0d7a4f7f271e7f4d492023391a6860e7debc6e403c8898dc89
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This workpaper records the S3-A1 contract patch that freezes evaluation-window
anchor rules and in-window `EXCLUDED` semantics in
`docs/v0-3/s3/s3-daily-rowset-amendment.md` §5.1 and §5.3. It is a contract
patch only. It does not materialize a daily rowset, verify completeness, or
execute backtests.

~~~text
S3_A1_WINDOW_ANCHOR_CONTRACT_AUTHORIZED=true
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=false
S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED=false
S3_B_AUTHORIZED=false
S3_C_AUTHORIZED=false
S3_BACKTEST_EXECUTION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
SOURCE_002_ROW_LEVEL_READ=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

## 1. Parent S3-A binding

~~~text
S3_A_PR=299
S3_A_MERGE=fd793de12bfe2df646925d9e7adc1d59c046ecdf
S3_A_AMENDMENT_PATH=docs/v0-3/s3/s3-daily-rowset-amendment.md
S3_A_AMENDMENT_SHA256=f2b2473bd7ebe52349010403cbcc45a8a18f3ae7ad3512c97d8b2a30b205a7be
~~~

S3-A left §5.1 and §5.3 underspecified. S3-A1 supplies coordinator-ratified
anchor and exclusion rules only.

## 2. Coordinator rulings applied

### 2.1 Horizon windows (`H ∈ {7,14,21}`)

~~~text
TIMEZONE=Asia/Shanghai
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
cutoff_business_date = forecast_cutoff_at in Asia/Shanghai calendar date
evaluation_window_start_date = cutoff_business_date + 1 day
evaluation_window_end_date   = cutoff_business_date + H days
WINDOW_CALENDAR_DAY_COUNT=H
CUTOFF_DAY_EXCLUDED_FROM_WINDOW=true
TARGET_DATE_MISMATCH_REASON_CODE=TARGET_DATE_CUTOFF_HORIZON_MISMATCH
WINDOW_OR_HORIZON_REALIGNMENT_FORBIDDEN=true
~~~

### 2.2 Complete-season window

~~~text
COMPLETE_SEASON_WINDOW=January 1 .. April 30 of SEASON year (Asia/Shanghai, inclusive)
SEASON_YEAR_FROM_ACCEPTED_S2_GRAIN_ONLY=true
SEASON_YEAR_DERIVATION_FAILURE=NOT_COMPUTABLE
FACTORY_BUILDING_AREA_AS_PEAK_FEATURE_FORBIDDEN=true
~~~

### 2.3 In-window EXCLUDED

~~~text
CELL_LEVEL_EXCLUDED_NO_WINDOW_GENERATED=true
DAY_LEVEL_EXCLUDED_IN_WINDOW=REJECT_WINDOW
EXCLUDED_HOLE_PUNCHING_FOR_PEAK_FORBIDDEN=true
PEAK_OVER_OBSERVED_DAYS_ONLY=false
~~~

### 2.4 Sustained peak 3 vs 7

~~~text
PRODUCT_SUSTAINED_PEAK_WINDOW_DAYS=3
PLAN_SUSTAINED_PEAK_WINDOW_DAYS=7
CONFLICT_STATUS=UNRESOLVED
SLIDING_NDAY_IS_SECOND_STAGE_INSIDE_ANCHORED_WINDOW=true
NO_COMPLETE_NDAY_WINDOW_FORBIDDEN_WHILE_COMPLETENESS_UNVERIFIED=true
~~~

## 3. Amendment patch scope

Only these sections of `s3-daily-rowset-amendment.md` are mutated:

- §5.1 Window selection — horizon anchor and complete-season anchor
- §5.3 Per-day status semantics — cell-level vs day-level EXCLUDED

Unchanged by S3-A1:

~~~text
CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
IDENTITY_SENTINELS_REMAIN_NOT_MATERIALIZED=true
S3_B_AUTHORIZED=false
S3_C_AUTHORIZED=false
DEVELOPMENT_PLAN_UNCHANGED=true
P0_CONTRACT_UNCHANGED=true
V0_2_METRIC_CONTRACT_UNCHANGED=true
S2_CONTRACT_UNCHANGED=true
~~~

## 4. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
A1_MERGE_IS_NOT_MATERIALIZATION=true
A1_MERGE_IS_NOT_BACKTEST=true
AWAITING_COORDINATOR_REVIEW=true
~~~
