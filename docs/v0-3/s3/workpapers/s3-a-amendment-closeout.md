# V0.3-S3-A daily rowset amendment closeout

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A_AMENDMENT_CLOSEOUT
ARTIFACT_VERSION=s3-a-amendment-closeout-v1
TASK_ID=V03_S3_A_AMENDMENT_CLOSEOUT_R1
TASK_CLASS=DOCS_ONLY_AMENDMENT_CLOSEOUT
AUTHORIZATION_SCOPE=S3_A_DAILY_ROWSET_AMENDMENT_CLOSEOUT_ONLY
SLICE=V0.3-S3
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
USER_WAIVED_THIRD_PARTY_REVIEW=true
COORDINATOR_REVIEW_COUNTS=true
COORDINATOR_AGENT=https://cursor.com/agents/bc-01a02307-c032-7da6-8a02-00d9b3518794
DOCS_ONLY_AGENT=https://cursor.com/agents/bc-01a02a06-2694-7db3-bffe-cbcc33b2c1a2
BASE_REF=origin/main
BASE_MAIN_SHA=fb97a843f7026ece9bb227ee9981beca53c566f5
BASE_MAIN_TREE_SHA=647ba46fa863f3346544a2c48230a8b97b72160d
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a-amendment-closeout.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a-amendment-closeout.json
EVIDENCE_JSON_SHA256=7ce9c1bf1c2eee9a3cd0d6176d6a31466e308bd991ab206cf0285967c68523ef
NO_STEP_IMPLIES_THE_NEXT=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This closeout aligns live registry state for the S3-A daily rowset amendment
contract after merged S3-A (#299) and S3-A1 (#300). It flips
`CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE` from `false` to `true`. It does
not materialize a daily rowset, verify completeness, authorize backtest
execution, unseal TEST, or resolve the 3-day vs 7-day sustained peak conflict.

~~~text
CLOSEOUT_MERGE_DOES_NOT_AUTHORIZE_MATERIALIZATION=true
CLOSEOUT_MERGE_DOES_NOT_AUTHORIZE_COMPLETENESS_VERIFICATION=true
CLOSEOUT_MERGE_DOES_NOT_AUTHORIZE_BACKTEST=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Pre-closeout contract bindings (main at `fb97a84`)

### 1.1 P0 contract (closeout baseline)

~~~text
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
P0_CONTRACT_GIT_BLOB_SHA=45f900f4dfa1ef5da8ea898a39bdded4c8c11f08
P0_CONTRACT_FILE_SHA256=490f48cde5fd7543f2d7608b0dff388c9a7f99f44d77ed4337f55331e950d7a8
P0_EVIDENCE_JSON_SHA256=580f09e306e4e32db0e72d65158d455bd9fea57b4279497909ff0d54cb91259c
P0_PR=298
P0_MERGE=0a6f412aad63e1f66a5e14e5960ca88deb9b2dcd
~~~

### 1.2 S3-A amendment (A1 baseline)

~~~text
S3_A_AMENDMENT_PATH=docs/v0-3/s3/s3-daily-rowset-amendment.md
S3_A_AMENDMENT_GIT_BLOB_SHA=e1109c30b90464e575700ac3a332b3c46c1bcd40
S3_A_AMENDMENT_FILE_SHA256=73fc80cd66d5606e99c8f085962397f582a37cab7fb645567a3e55e5a2a3e721
S3_A_EVIDENCE_JSON_SHA256=b50948c9529dd7f87b844e61e48fbb3b89d6eae31211f43d6fc5189360553e0a
S3_A_PR=299
S3_A_MERGE=fd793de12bfe2df646925d9e7adc1d59c046ecdf
~~~

Note: `b50948c9…` is the JSON self-hash of `s3-a-daily-rowset-amendment.json`,
not the whole-file `sha256sum`.

### 1.3 S3-A1 window anchor

~~~text
S3_A1_PR=300
S3_A1_MERGE=ef3702dd168b2c4e9adff133a2807ec1819dfaa7
S3_A1_EVIDENCE_JSON_SHA256=7d5e915bf1eb8b0d7a4f7f271e7f4d492023391a6860e7debc6e403c8898dc89
~~~

### 1.4 Downstream contracts (reference only; not mutated)

~~~text
S3_B_PR=301
S3_B_MERGE=f9e7b221722d74789112142aebb77a5c69687ea3
S3_B_EVIDENCE_JSON_SHA256=52dfe07eb6a17004704a1545c136a51c4646fbc7b7f7bca80b13f87a71e2d3e7
S3_C0_PR=302
S3_C0_MERGE=fb97a843f7026ece9bb227ee9981beca53c566f5
S3_C0_EVIDENCE_JSON_SHA256=12c40e013c60de9f9dbcfd7b5e7788281d9c7d6adcde641d6d436b3e65b5d7e1
~~~

Frozen snapshots in S1, S3-B, and S3-C0 contract files that still record
`CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE=false` are historical freeze
snapshots. Live authority is `docs/v0-3/development-plan.md` §4.4.

### 1.5 Inherited S2 / input authority (not reopened)

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
SOURCE_OBJECT_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
V0_3_S3_ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
V0_3_S3_VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
V0_2_S3_INPUT_AUTHORITY_HISTORICAL=S2_IMMUTABLE_BACKTEST_BINDING
DO_NOT_CONFLATE_V0_2_BINDING_WITH_V0_3_S2_DATASET=true
~~~

## 2. Closeout scoring (independent; not automatic from A1 merge)

| # | Criterion | Evidence | Result |
|---|---|---|---|
| 1 | S3-A (#299) froze calendar expansion, `UNKNOWN_NOT_ZERO`, no zero-fill, actual kg from SOURCE_002 TRAIN/VAL grains only, incumbent replay at cutoff, identity schema+sentinels, completeness predicates defined but not verified | `s3-daily-rowset-amendment.md` §4–§8; evidence `b50948c9…` | **PASS** |
| 2 | S3-A1 (#300) closed operational residuals: §5.1 window anchors, §5.3 cell vs day-level EXCLUDED | `s3-daily-rowset-amendment.md` §5.1–§5.3; evidence `7d5e915b…` | **PASS** |
| 3 | 3 vs 7 sustained peak is metric-window conflict, not rowset-expansion residual; remains `UNRESOLVED`; not used as reason to keep amendment incomplete | P0 §6; amendment §7.4; closeout keeps `P0_SUSTAINED_PEAK_WINDOW_CONFLICT=UNRESOLVED` | **PASS** |
| 4 | Materialization, completeness verification, semantics verification, and backtest execution are not amendment-contract completion conditions | All merged contracts keep materialization/backtest flags `false` | **PASS** |

All four criteria pass. Closeout may flip `CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE=true`.

## 3. Registry flip manifest

### 3.1 Flipped to `true` (this closeout only)

~~~text
CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE=false → true
~~~

Locations updated:

- `docs/v0-3/development-plan.md` §4.4
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §3.2 and §12 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §4.2 live block

### 3.2 Explicitly remain `false` / unchanged

~~~text
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_S3_DAILY_ROWSET_CONTRACT_STATUS=NOT_AVAILABLE_FROM_CURRENT_S2_BINDING
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=false
S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
S3_BACKTEST_EXECUTION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
CURRENT_P50_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P90_SEMANTICS_STATUS=NOT_VERIFIED
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
CURRENT_V0_3_S3_COMPLETE=false
CURRENT_V0_3_S1_COMPLETE=false
NEXT_TASK=V0_3_S1
V0_3_S4_AUTHORIZED=false
ALLOWLIST_EXPANSION_AUTHORIZED=false
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
SOURCE_002_ROW_LEVEL_READ=false
SUSTAINED_PEAK_PASS_FORBIDDEN_UNTIL_OWNER_DECISION=true
P0_SUSTAINED_PEAK_WINDOW_CONFLICT=UNRESOLVED
IDENTITY_SENTINELS_REMAIN_NOT_MATERIALIZED=true
~~~

Peak / cumulative / complete-horizon metrics remain `NOT_COMPUTABLE` with
`reason_code=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING`.

## 4. Frozen A1 window rules (not reopened)

~~~text
HORIZONS_DAYS=7,14,21
TIMEZONE=Asia/Shanghai
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
evaluation_window_start_date=cutoff_business_date + 1 day
evaluation_window_end_date=cutoff_business_date + H days
TARGET_DATE_MISMATCH=TARGET_DATE_CUTOFF_HORIZON_MISMATCH
WINDOW_OR_HORIZON_REALIGNMENT_FORBIDDEN=true
COMPLETE_SEASON=January 1 .. April 30 of SEASON year (from accepted S2 grain)
CELL_LEVEL_EXCLUDED_NO_WINDOW=true
DAY_LEVEL_EXCLUDED_IN_WINDOW=REJECT_WINDOW
PEAK_OVER_OBSERVED_DAYS_ONLY=false
~~~

## 5. Boundaries

This closeout does **not**:

- authorize daily rowset materialization or invent identity hashes
- perform completeness verification
- claim S3-B quantile semantics verified or coverage computable
- authorize S3-C backtest execution
- unseal TEST or authorize S4
- resolve 3-day vs 7-day sustained peak
- modify S2, V0.2 metric, S1, S3-B, or S3-C0 contract files
- modify backend / tests / alembic / allowlist

~~~text
THIS_DRAFT_IS_NOT_READY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
