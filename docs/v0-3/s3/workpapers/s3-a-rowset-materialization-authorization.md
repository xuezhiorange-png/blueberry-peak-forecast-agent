# V0.3-S3-A rowset materialization authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A_ROWSET_MATERIALIZATION_AUTHORIZATION
ARTIFACT_VERSION=s3-a-rowset-materialization-authorization-v1
TASK_ID=V03_S3_A_ROWSET_MATERIALIZATION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_A_ROWSET_MATERIALIZATION_GRANT_ONLY
SLICE=V0.3-S3
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
USER_WAIVED_THIRD_PARTY_REVIEW=true
COORDINATOR_REVIEW_COUNTS=true
COORDINATOR_AGENT=https://cursor.com/agents/bc-01a02307-c032-7da6-8a02-00d9b3518794
DOCS_ONLY_AGENT=https://cursor.com/agents/bc-01a02a06-2694-7db3-bffe-cbcc33b2c1a2
BASE_REF=origin/main
BASE_MAIN_SHA=7bb66d8c3010ef2341baf3dd25003325067afe50
BASE_MAIN_TREE_SHA=fbacb7f3dfc663f702c79dd3796f921b94672f73
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a-rowset-materialization-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a-rowset-materialization-authorization.json
EVIDENCE_JSON_SHA256=df66d59383d3bdf76e7db6fdc32b21b2f41237ef3072f8a1ac76205ddc4d6239
NO_STEP_IMPLIES_THE_NEXT=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

The user authorized issuance of the S3-A daily rowset materialization grant
after closeout #303. This document records what a **later** implementation may
do when the user again says 「可以实施」. This PR does not implement
materialization, compute identity hashes, authorize completeness verification,
or run backtests.

Analogous to S2 #284: authorization records permitted future work; this PR
writes no backend code.

~~~text
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED=false
ALLOWLIST_EXPANSION_AUTHORIZED=false
AUTHORIZATION_MERGE_DOES_NOT_EXECUTE_MATERIALIZATION=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Closeout and contract bindings (reference only)

~~~text
S3_A_AMENDMENT_CLOSEOUT_PR=303
S3_A_AMENDMENT_CLOSEOUT_MERGE=7bb66d8c3010ef2341baf3dd25003325067afe50
CLOSEOUT_EVIDENCE_JSON_SHA256=7ce9c1bf1c2eee9a3cd0d6176d6a31466e308bd991ab206cf0285967c68523ef
AMENDMENT_PATH=docs/v0-3/s3/s3-daily-rowset-amendment.md
AMENDMENT_GIT_BLOB_SHA=9c4e03b21e1f1622a27a9e1f015a1577d96a1f8d
AMENDMENT_FILE_SHA256=9a56d0277eb138bc5ce70f8c72249040c45081830e6800134c775b45c641f83c
P0_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
P0_GIT_BLOB_SHA=09823e526401a0c736f20f6af77796f14ae10a8c
P0_FILE_SHA256=b9c9862ca165cf4cf3a7fd89f62da87db61f6b92eab3dc4a033b1170cafd7007
P0_EVIDENCE_JSON_SHA256=580f09e306e4e32db0e72d65158d455bd9fea57b4279497909ff0d54cb91259c
S3_A_EVIDENCE_JSON_SHA256=b50948c9529dd7f87b844e61e48fbb3b89d6eae31211f43d6fc5189360553e0a
S3_A1_EVIDENCE_JSON_SHA256=7d5e915bf1eb8b0d7a4f7f271e7f4d492023391a6860e7debc6e403c8898dc89
CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE=true
~~~

Evidence JSON self-hashes above are binding references, not whole-file
`sha256sum` values.

## 2. Inherited S2 and input authority (not reopened)

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
BYTE_COUNT=28668416
DECLARED_SOURCE_ROW_COUNT=233171
V0_3_S3_ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
V0_3_S3_VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
DO_NOT_CONFLATE_V0_2_S2_IMMUTABLE_BACKTEST_BINDING_WITH_V0_3_S2_DATASET=true
~~~

## 3. What this authorization grants

A later deterministic implementation may, under a separate user 「可以实施」
gate:

1. Read accepted S2 materialized **TRAIN** and **VALIDATION** grains only —
   not the raw SOURCE_002 object, not xls/Sheets, not S1 derived JSON as
   primary input, not PIT/old-winner tables as SOURCE_002 primary path.
2. Expand each evaluation instance cell per frozen S3-A/A1 rules into a calendar
   daily row set with explicit per-day `OBSERVED | UNKNOWN | EXCLUDED` status.
3. Source actual kg as `Decimal` from `OBSERVED` S2 grains only; missing days
   are `UNKNOWN` (null/absent), never numeric zero; numeric imputation forbidden.
4. Replay incumbent V0.2 forecasts at each `forecast_cutoff` with cutoff-visible
   information only; `FORECAST_UNAVAILABLE` rejects the window and is not zero.
5. Compute and persist daily-rowset identity fields via deterministic service
   logic; LLM must not invent hashes, row counts, or tonnage.
6. Bind `Q2C_TARGET=OBSERVED_FARM_PICK_QUANTITY` and
   `S3_EVALUATION_PARTITIONS=TRAIN,VALIDATION`.

~~~text
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=true
SOURCE_002_ROW_LEVEL_READ=false
SOURCE_002_MUTATION_AUTHORIZED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
IDENTITY_SENTINELS_REMAIN_NOT_MATERIALIZED_UNTIL_IMPLEMENTATION=true
~~~

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
FACTORY_BUILDING_AREA_AS_PEAK_FEATURE_FORBIDDEN=true
~~~

## 5. What remains forbidden / not authorized

~~~text
S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_S3_DAILY_ROWSET_CONTRACT_STATUS=NOT_AVAILABLE_FROM_CURRENT_S2_BINDING
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
S3_BACKTEST_EXECUTION_AUTHORIZED=false
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
V0_3_S4_AUTHORIZED=false
ALLOWLIST_EXPANSION_AUTHORIZED=false
P0_SUSTAINED_PEAK_WINDOW_CONFLICT=UNRESOLVED
SUSTAINED_PEAK_PASS_FORBIDDEN_UNTIL_OWNER_DECISION=true
NEW_ALEMBIC_HEAD_FORBIDDEN=true
UNIQUE_ALEMBIC_HEAD=a7c3e9f1b2d4
PARALLEL_ALEMBIC_HEADS_ALLOWED=false
PEP420_FORBIDDEN_PRODUCTION_INITS=true
~~~

Peak / cumulative / complete-horizon metrics remain `NOT_COMPUTABLE` with
`reason_code=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` until
materialization is executed and completeness verification separately passes.

Forbidden during future implementation unless separately authorized:

- TEST partition rows as evaluation input
- completeness verification PASS claims
- backtest execution or coverage metrics
- model or parameter changes
- peak redefined as max over observed sparse days only
- choosing 3-day vs 7-day sustained peak winner
- allowlist expansion or new production paths not already authorized
- rereading raw SOURCE_002 bytes

## 6. Fail-closed implementation requirements

Future implementation must fail closed when:

- S2 grain identity does not match accepted `source-002/e5-live-v1` bindings
- window anchor rules from A1 are violated
- any calendar day in a generated window is silently missing
- `UNKNOWN` or day-level `EXCLUDED` appears inside a generated window
- forecast replay uses post-cutoff information
- identity hash fields would be invented rather than computed

## 7. Registry flip manifest

~~~text
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` live status blocks and §13 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer

Unchanged: `CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE=true` (from #303);
all completeness, semantics, backtest, TEST, and S3-complete flags remain
blocked as listed in §5.

## 8. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AUTHORIZATION_MERGE_IS_NOT_IMPLEMENTATION=true
AWAITING_COORDINATOR_REVIEW=true
~~~
