# V0.3-S3-A2 Accepted S2 TRAIN/VALIDATION kg row-level-read R1

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_R1
ARTIFACT_VERSION=s3-accepted-s2-train-val-kg-row-level-read-r1-v1
TASK_ID=V03_S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_R1
TASK_CLASS=IMPLEMENTATION
AUTHORIZATION_SCOPE=S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTATION_ONLY
PARALLEL_LANE=S3-A2-ACCEPTED-S2-KG-READ
SLICE=V0.3-S3
ENGLISH_ID=ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=db577208424e972f53bdfb4fb7215781b87a1f49
BASE_MAIN_TREE_SHA=605e93ec2ea06dfdd71a22f191a6c89e54dc7b61
PARENT_GRANT_PR=408
PARENT_GRANT_MERGE=db577208424e972f53bdfb4fb7215781b87a1f49
GRANT_WORKPAPER=docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-kg-row-level-read-authorization.md
GRANT_WORKPAPER_GIT_BLOB_SHA=1a3c3365936354eab59fa41121c2891b8bdefeb2
GRANT_EVIDENCE_JSON_SHA256=09b60adda82b4d83315eb091b81b68c5f927fc040fe5ab20b9405db9cdfebaeb
PARENT_LIVE_AUTHORITY_PR=407
PARENT_LIVE_AUTHORITY_MERGE=a60b79a9606c9625478eb1777fa60135e849d339
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=cef159639a25737cb28f6e80069709fd3bc10d5e6c86fcb8888cf1bdfdc42140
PARENT_CONTRACT_PR=406
PARENT_CONTRACT_MERGE=6ff9768820f931e6203f3847932c82f46f7f4f27
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-kg-row-level-read-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-accepted-s2-train-val-kg-row-level-read-r1.json
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
IMPLEMENTATION_R1=true
EXECUTION_CLAIM_R1_IS_DOCS_ONLY=true
CHECKLIST_EXECUTED=true
THIS_FAMILY_DOCS_ONLY_STAGES_MUST_NOT_FLIP_SOURCE_002_ROW_LEVEL_READ=true
NAMING_ORIGIN_IS_NOT_KG_ROW_LEVEL_READ=true
FORBIDDEN_RESOLVE_3_VS_7=true
FORBIDDEN_AUTHORIZE_S3_B_COVERAGE=true
FORBIDDEN_AUTHORIZE_S4=true
FORBIDDEN_REWRITE_POPULATED_ORIGIN_FREEZE=true
FORBIDDEN_WRITE_SELECT_FROM_JOIN_WHERE_IN_CONTRACT=true
FORBIDDEN_WRITE_DSN_OR_CONNECTION_STRINGS=true
FORBIDDEN_TOUCH_PYTHON=true
~~~

This workpaper records docs-only execution R1 per grant (#408) and frozen
`docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-kg-row-level-read-authorization.md` §3.1
(blob `1a3c3365936354eab59fa41121c2891b8bdefeb2`). Git blob bindings were
re-traced on `origin/main` at base `db57720`. This R1 records that the frozen
lawful read target is still bound. It does not read kilograms, read SOURCE_002
row-level data, land identity-set members, produce versioned forecast artifacts,
bind catalogs, verify completeness, execute backtest/attribution/metrics,
authorize S3-B coverage or S4, unseal TEST, rewrite populated-origin freeze,
rewrite C0 §5, mutate V0.2 formulas, adjudicate P0 3-day vs 7-day window, write
`SELECT`/`FROM`/`JOIN`/`WHERE` or DSN strings, or flip
`SOURCE_002_ROW_LEVEL_READ`.

~~~text
S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_CONTRACT_AUTHORIZED=true
S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTED=true
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTED=true
SOURCE_002_ROW_LEVEL_READ=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
TEST_REMAINS_SEALED=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
CURRENT_S3_C_BACKTEST_EXECUTION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
CURRENT_S3_D_ATTRIBUTION_EXECUTION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
CURRENT_S3_METRIC_EXECUTION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
CURRENT_S3_A1_WINDOW_ANCHOR_CLAIM_STATUS=VERIFIED_FREEZE_STILL_BOUND
CURRENT_P50_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P80_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P90_SEMANTICS_STATUS=VERIFICATION_FAILED
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
V0_3_METRIC_CONTRACT_STATUS=PENDING_S1_ACCEPTANCE
~~~

`DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTED=true` ≠
`SOURCE_002_ROW_LEVEL_READ` ≠ kg row-level read performed ≠ members landed ≠
`NO_REVIEWED` flipped ≠ versioned forecast artifact produced ≠ `NO_VERSIONED`
flipped ≠ catalog bindable ≠ completeness verified ≠ backtest/attribution/metrics
computed ≠ S3-B coverage ≠ S4 ≠ TEST unsealed ≠ populated-origin
`FAIL_CLOSED_NO_LAWFUL_POPULATED_ORIGIN_TODAY` rewritten ≠ C0 §5 `PENDING_NOT_MERGED`
rewritten. `CHECKLIST_EXECUTED=true` ≠ kg read ≠ member enumeration ≠ forecast
artifact exists. `#406` / `#407` / `#408` contract-file fence
`S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZED=false` and
historical pointer snapshots `DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTED=false`
remain historical freeze snapshots where frozen; live authority is
`docs/v0-3/development-plan.md` §4.4. Actual kg read / unique live flip of
`SOURCE_002_ROW_LEVEL_READ` requires a later separate deterministic reader
attestation slice. This evidence JSON is not a versioned forecast artifact,
completeness verified package, backtest package, metric results package, or
attribution matrix. Catalog first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.

## 1. Frozen §3.1 execution summary

Authority: `docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-kg-row-level-read-authorization.md`
§3.1.

### Step 1 — Git blob re-bind on `origin/main` at `db57720`

~~~text
docs/v0-3/development-plan.md=cf201d3f1a8c1b3a6a7988073f5fe1abd195903a
docs/v0-3/s3/s3-daily-rowset-amendment.md=fbfa51cd381512b39489f41818fd93e13a4e740d
docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md=3a75deef4fc6a92567e0735a73bd0fadabb23e97
docs/v0-3/s3/s3-accepted-s2-train-val-kg-row-level-read-contract.md=1d735e04eadc07360fc550b5f585c5ab6c471174
docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-kg-row-level-read-authorization.md=1a3c3365936354eab59fa41121c2891b8bdefeb2
docs/v0-3/s3/evidence/s3-accepted-s2-train-val-kg-row-level-read-authorization.json=e00e3cf2a131e153fc6dbb797d8bfcce3a85b20b
docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-kg-row-level-read-contract.md=52cff2ac2db42cd64ed7b9df1691d0dc311e6622
docs/v0-3/s3/evidence/s3-accepted-s2-train-val-kg-row-level-read-contract.json=e44d68f1fa5d254c16cded82d4f5a8e84d7e015f
docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-kg-row-level-read-contract-live-authority.md=b70f1a46a13ca8b18e8fe76f1d01b526f14ac42a
docs/v0-3/s3/evidence/s3-accepted-s2-train-val-kg-row-level-read-contract-live-authority.json=982ac1521020a26be8414b71e489df241f9235b4
docs/v0-3/s3/s3-pit-backtest-execution-contract.md=e59f8a2d255df392116c65d535ae22ae3854ae98
docs/v0-3/s3/s3-error-attribution-contract.md=0819f429dcaf390a97a51a674ca96405eb8ebab7
REBIND_COMPLETE=true
C0_AND_S3_D_RECORDED_NOT_EDITED=true
RESULT=PASS
~~~

### Step 2 — Freeze workpaper and authority evidence unchanged

~~~text
S3_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_FREEZE_WORKPAPER_GIT_BLOB_SHA=52cff2ac2db42cd64ed7b9df1691d0dc311e6622
S3_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_FREEZE_EVIDENCE_JSON_SHA256=618b33a0ad903181f646fbd7b740e30fc136dbaa21e0b7d73334ce1141d0795c
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=cef159639a25737cb28f6e80069709fd3bc10d5e6c86fcb8888cf1bdfdc42140
GRANT_EVIDENCE_JSON_SHA256=09b60adda82b4d83315eb091b81b68c5f927fc040fe5ab20b9405db9cdfebaeb
RESULT=PASS
~~~

### Step 3 — Contract file top fence unchanged

~~~text
S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZED=false
IDENTITY_BASE_MAIN_SHA=3f0fd2fc2e5f46489d4714026792e5b279531fca
FENCE_NOT_REWRITTEN=true
RESULT=PASS
~~~

### Step 4 — §13/§14 historical pointers not refreshed

~~~text
CONTRACT_TOP_IDENTITY_BASE_MAIN_SHA=3f0fd2fc2e5f46489d4714026792e5b279531fca
SECTION_13_BASE_MAIN_SHA=6ff9768820f931e6203f3847932c82f46f7f4f27
SECTION_13_CURRENT_P0=3cc74845099496e1ea9ea764c622cdc5b95307b0
SECTION_14_BASE_MAIN_SHA=a60b79a9606c9625478eb1777fa60135e849d339
SECTION_14_CURRENT_P0=6fa6787cea2312554715094fefad180aca8689b0
HISTORICAL_POINTERS_NOT_REFRESHED=true
RESULT=PASS
~~~

### Step 5 — Live §4.4 contract and implementation authorization confirmed

~~~text
S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_CONTRACT_AUTHORIZED=true
S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTED_BEFORE_R1=false
LIVE_FLAGS_CONFIRMED_AT_BASE=true
RESULT=PASS
~~~

### Step 6 — Contract §3 official hashes match S2 acceptance (reference only); TEST sealed

~~~text
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_ROW_COUNT=16224
TRAIN_CONTENT_SHA256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
VALIDATION_ROW_COUNT=8006
VALIDATION_CONTENT_SHA256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
TRAIN_PARTITION=2025-08-05..2026-01-30
VALIDATION_PARTITION=2026-01-31..2026-03-09
TEST_PARTITION=2026-03-10..2026-04-16
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
CANONICAL_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
ACTUAL_LABEL=actual_harvest_quantity_kg
MONTHS=1-4
EXCLUDE_PRODUCT_CLASSES=普鲜、普青、普冻、废果
EXCLUDE_PLANT=巴松
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
REPLAY_TABLE_S3_INCUMBENT_FORECAST_REPLAY_IDENTITY_IS_NOT_HARVEST_KG_TARGET=true
REFERENCE_ONLY_NO_RECOMPUTE=true
TEST_REMAINS_SEALED=true
RESULT=PASS
~~~

### Step 7 — Populated-origin freeze and C0 §5 pending snapshot unchanged

~~~text
POPULATED_ORIGIN_FREEZE=FAIL_CLOSED_NO_LAWFUL_POPULATED_ORIGIN_TODAY
POPULATED_ORIGIN_CONTRACT_NOT_EDITED=true
C0_SECTION_5_TITLE=Evaluation window anchor (S3-A1 pending)
S3_A1_EVALUATION_WINDOW_ANCHOR_STATUS=PENDING_NOT_MERGED
C0_CONTRACT_NOT_EDITED=true
RESULT=PASS
~~~

### Step 8 — Forbidden actions not performed

~~~text
SOURCE_002_ROW_LEVEL_NOT_READ=true
KG_ROW_LEVEL_NOT_READ=true
MEMBERS_NOT_ENUMERATED=true
HASHES_TONNES_FARMS_DATES_NOT_INVENTED=true
TEST_NOT_UNSEALED=true
NO_VERSIONED_NOT_FLIPPED=true
NO_REVIEWED_NOT_FLIPPED=true
COMPLETENESS_NOT_FLIPPED=true
C0_STATUS_NOT_FLIPPED=true
S3_D_STATUS_NOT_FLIPPED=true
METRIC_STATUS_NOT_FLIPPED=true
S3_B_COVERAGE_NOT_AUTHORIZED=true
S4_NOT_AUTHORIZED=true
PYTHON_NOT_TOUCHED=true
V0_2_FORMULAS_NOT_MUTATED=true
SECTION_4_5_NOT_FLIPPED=true
P0_3DAY_VS_7DAY_NOT_ADJUDICATED=true
SELECT_FROM_JOIN_WHERE_NOT_WRITTEN=true
DSN_NOT_WRITTEN=true
H7_FIXTURE_NOT_TREATED_AS_LIVE_EVIDENCE=true
RESULT=PASS
~~~

### Step 9 — Unique flip IMPLEMENTED

~~~text
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTED=false → true
SEMANTICS=docs_only_checklist_that_frozen_lawful_read_target_is_still_bound
IMPLEMENTED_TRUE_DOES_NOT_MEAN_KG_ROW_LEVEL_READ_PERFORMED=true
IMPLEMENTED_TRUE_DOES_NOT_MEAN_SOURCE_002_ROW_LEVEL_READ=true
RESULT=PASS
~~~

## 2. Six-file manifest

| # | path |
|---|------|
| 1 | `docs/v0-3/development-plan.md` |
| 2 | `docs/v0-3/s3/s3-daily-rowset-amendment.md` |
| 3 | `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` |
| 4 | `docs/v0-3/s3/s3-accepted-s2-train-val-kg-row-level-read-contract.md` |
| 5 | `docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-kg-row-level-read-r1.md` |
| 6 | `docs/v0-3/s3/evidence/s3-accepted-s2-train-val-kg-row-level-read-r1.json` |

## 3. Unique flip

~~~text
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block
- `docs/v0-3/development-plan.md` R1 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §112 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` Live paragraph immediately before ## 12
- `docs/v0-3/s3/s3-accepted-s2-train-val-kg-row-level-read-contract.md` §15 pointer

Historical grant pointer (#408) snapshots retain `DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTED=false`.
`IMPLEMENTED=true` ≠ kg actually read ≠ `SOURCE_002_ROW_LEVEL_READ`. Actual kg
read / unique live flip of `SOURCE_002_ROW_LEVEL_READ` requires a later separate
deterministic reader attestation slice.

## 4. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=8dd8fc438b0b9252e68bea9a94f693c6e98e5e037fbecc87340c29a933832298
~~~

## 5. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
IMPLEMENTATION_MERGE_DOES_NOT_READ_SOURCE_002_ROW_LEVEL=true
IMPLEMENTATION_MERGE_DOES_NOT_EXECUTE_KG_ROW_LEVEL_READ=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_SOURCE_002_ROW_LEVEL_READ=true
IMPLEMENTATION_MERGE_DOES_NOT_LAND_MEMBERS=true
IMPLEMENTATION_MERGE_DOES_NOT_PRODUCE_VERSIONED_FORECAST_ARTIFACT=true
AWAITING_COORDINATOR_REVIEW=true
~~~
