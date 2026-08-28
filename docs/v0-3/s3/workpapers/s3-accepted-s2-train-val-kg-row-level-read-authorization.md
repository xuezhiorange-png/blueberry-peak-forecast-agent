# V0.3-S3-A2 Accepted S2 TRAIN/VALIDATION kg row-level-read implementation authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZATION
ARTIFACT_VERSION=s3-accepted-s2-train-val-kg-row-level-read-authorization-v1
TASK_ID=V03_S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTATION_GRANT_ONLY
PARALLEL_LANE=S3-A2-ACCEPTED-S2-KG-READ
SLICE=V0.3-S3
ENGLISH_ID=ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=a60b79a9606c9625478eb1777fa60135e849d339
BASE_MAIN_TREE_SHA=58448f6dbf0ea695b4b728683359320239267c74
PARENT_CONTRACT_PR=406
PARENT_CONTRACT_MERGE=6ff9768820f931e6203f3847932c82f46f7f4f27
PARENT_LIVE_AUTHORITY_PR=407
PARENT_LIVE_AUTHORITY_MERGE=a60b79a9606c9625478eb1777fa60135e849d339
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=cef159639a25737cb28f6e80069709fd3bc10d5e6c86fcb8888cf1bdfdc42140
LIVE_AUTHORITY_WORKPAPER=docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-kg-row-level-read-contract-live-authority.md
LIVE_AUTHORITY_WORKPAPER_GIT_BLOB_SHA=b70f1a46a13ca8b18e8fe76f1d01b526f14ac42a
LIVE_AUTHORITY_EVIDENCE_GIT_BLOB_SHA=982ac1521020a26be8414b71e489df241f9235b4
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-kg-row-level-read-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-accepted-s2-train-val-kg-row-level-read-authorization.json
GRANT_ONLY=true
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
THIS_PR_IS_NOT_R1=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
GRANT_MERGE_DOES_NOT_FLIP_IMPLEMENTED=true
GRANT_MERGE_DOES_NOT_EXECUTE_KG_ROW_LEVEL_READ=true
GRANT_MERGE_DOES_NOT_TOUCH_PYTHON=true
LATER_R1_IS_DOCS_ONLY=true
EXECUTION_CLAIM_R1_IS_DOCS_ONLY=true
THIS_FAMILY_DOCS_ONLY_STAGES_MUST_NOT_FLIP_SOURCE_002_ROW_LEVEL_READ=true
FORBIDDEN_REWRITE_POPULATED_ORIGIN_FREEZE=true
FORBIDDEN_RESOLVE_3_VS_7=true
FORBIDDEN_AUTHORIZE_S3_B_COVERAGE=true
FORBIDDEN_AUTHORIZE_S4=true
~~~

The user authorized issuance of the S3-A2 **accepted S2 TRAIN/VALIDATION kg
row-level-read** implementation grant after live contract authority merged on
main (#407). This document records what a **later** docs-only execution R1 may do
when the user again says 「可以实施」. This PR does not execute kilogram row-level
read, does not flip `DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTED`,
does not flip `SOURCE_002_ROW_LEVEL_READ`, does not land identity-set members, and
does not authorize production or test code mutation.

This is **kg row-level-read implementation** authorization only. Parent freeze
(#406), live contract authority (#407), origin family (#402–#405), populated-origin
closed family, C0 §5 pending snapshot, P0, S3-B family, and A2 identity-set family
remain authoritative and are not reopened.

~~~text
S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_CONTRACT_AUTHORIZED=true
S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTED=false
SOURCE_002_ROW_LEVEL_READ=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
TEST_REMAINS_SEALED=true
COMPLETENESS_VERIFICATION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
DO_NOT_INVENT_HASHES_OR_TONNES=true
THIS_FAMILY_DOCS_ONLY_STAGES_MUST_NOT_FLIP_SOURCE_002_ROW_LEVEL_READ=true
NAMING_ORIGIN_IS_NOT_KG_ROW_LEVEL_READ=true
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTED=true
~~~

`S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZED=true` ≠
`DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTED` ≠
`SOURCE_002_ROW_LEVEL_READ` ≠ kg row-level read performed ≠ members landed ≠
`NO_REVIEWED` flipped ≠ versioned forecast artifact produced ≠ `NO_VERSIONED`
flipped ≠ catalog bindable ≠ completeness verified ≠ backtest/attribution/metrics
computed ≠ S3-B coverage ≠ S4 ≠ TEST unsealed ≠ populated-origin
`FAIL_CLOSED_NO_LAWFUL_POPULATED_ORIGIN_TODAY` rewritten ≠ C0 §5 `PENDING_NOT_MERGED`
rewritten. `#406` / `#407` contract-file fence
`S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZED=false`
remains historical freeze snapshot; live authority is
`docs/v0-3/development-plan.md` §4.4.
`DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTED=false` ≠ kg
read recorded. Later docs-only R1 `IMPLEMENTED=true` still ≠ kg actually read ≠
`SOURCE_002_ROW_LEVEL_READ`. Actual kg read / unique live flip of
`SOURCE_002_ROW_LEVEL_READ` requires a later separate deterministic reader
attestation slice, not this grant and not docs-only R1 alone. This evidence JSON
is **not** a versioned forecast artifact, completeness verified package, backtest
package, metric results package, or attribution matrix. Catalog first blocker
remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.

## 1. Unique remaining gap (this grant does not fill it)

~~~text
S3_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_FREEZE_WORKPAPER_GIT_BLOB_SHA=52cff2ac2db42cd64ed7b9df1691d0dc311e6622
S3_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_FREEZE_EVIDENCE_JSON_SHA256=618b33a0ad903181f646fbd7b740e30fc136dbaa21e0b7d73334ce1141d0795c
UNIQUE_REMAINING_GAP=_frozen_lawful_read_target_binding_checklist_not_yet_recorded
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTED=false
~~~

Kg row-level-read freeze (#406) and live contract authority (#407) are on main.
The frozen lawful read target remains bound, but the docs-only checklist that
records that binding has not been executed. This grant authorizes a **later**
docs-only execution R1 to re-bind blobs and execute the procedure — it does not
perform that execution today, does not read kilograms, and does not flip
`SOURCE_002_ROW_LEVEL_READ`.

## 2. Upstream bindings

~~~text
PARENT_CONTRACT_PR=406
PARENT_CONTRACT_MERGE=6ff9768820f931e6203f3847932c82f46f7f4f27
PARENT_LIVE_AUTHORITY_PR=407
PARENT_LIVE_AUTHORITY_MERGE=a60b79a9606c9625478eb1777fa60135e849d339
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=cef159639a25737cb28f6e80069709fd3bc10d5e6c86fcb8888cf1bdfdc42140
S3_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=bf177c3e532a40a316f6cbe37aeec04001635408
CURRENT_S3_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_CONTRACT_GIT_BLOB_SHA=3eb0ad4d5385713467a838043696cc45ea34ad32
S3_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_FREEZE_EVIDENCE_JSON_SHA256=618b33a0ad903181f646fbd7b740e30fc136dbaa21e0b7d73334ce1141d0795c
ORIGIN_R1_EVIDENCE_JSON_SHA256=c29070e45ac887c882c3488d5e18efc0c1ed7dac9e633e9b0ece1c051c3606d7
CURRENT_S3_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_CONTRACT_GIT_BLOB_SHA=e4a2fc260e2bf135d246018473edfc89ba671787
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTED=true
NAMING_ORIGIN_IS_NOT_KG_ROW_LEVEL_READ=true
CURRENT_S3_C0_CONTRACT_GIT_BLOB_SHA=e59f8a2d255df392116c65d535ae22ae3854ae98
CURRENT_S3_D_CONTRACT_GIT_BLOB_SHA=0819f429dcaf390a97a51a674ca96405eb8ebab7
CURRENT_S3_A_AMENDMENT_GIT_BLOB_SHA=f3163004cd8ea5e9b4f5bc859925da7fdaaee56a
CURRENT_P0_CONTRACT_GIT_BLOB_SHA=6fa6787cea2312554715094fefad180aca8689b0
CURRENT_DEVELOPMENT_PLAN_GIT_BLOB_SHA_AT_BASE=ece882d9b8ebde47c555ccd96e2fc2ffe036d99f
A1_WORKPAPER_GIT_BLOB_SHA=c8c8ed7540ce2ae36bf07127494a508256a813d6
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
~~~

Historical #406–#407 pointer snapshots retain their own `CURRENT_*` at insert
time and must not be refreshed by this grant.

## 3. Frozen subsequent R1 procedure (execution not authorized in this grant)

The following checklist is frozen for a future separately authorized docs-only
execution R1 pass. This grant does not execute it.

### 3.1 Procedure steps

1. Re-bind each referenced git blob SHA on then-current `origin/main`.
2. Confirm kg-read freeze workpaper blob is still `52cff2ac2db42cd64ed7b9df1691d0dc311e6622`
   and freeze evidence content SHA256 is still
   `618b33a0ad903181f646fbd7b740e30fc136dbaa21e0b7d73334ce1141d0795c`; live-authority
   evidence SHA256 is still `cef159639a25737cb28f6e80069709fd3bc10d5e6c86fcb8888cf1bdfdc42140`.
3. Confirm kg-read contract file top fence still contains
   `S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZED=false`
   (historical freeze snapshot; R1 must not rewrite fence).
4. Confirm kg-read contract top identity block `BASE_MAIN_SHA` is still
   `3f0fd2fc2e5f46489d4714026792e5b279531fca` and §13 historical `CURRENT_*`
   snapshots are not refreshed.
5. Confirm live §4.4 has `S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_CONTRACT_AUTHORIZED=true`
   and `S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZED=true`.
6. Confirm contract §3 official hashes still match S2 acceptance package
   (reference only, do not recompute); TEST remains sealed. Official TRAIN
   `16224` / `be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2`;
   VAL `8006` / `4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06`;
   dataset `source-002` / `e5-live-v1` /
   `f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785`. Grain
   `SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE`. Label
   `actual_harvest_quantity_kg`. Months 1–4. Exclude 普鲜/普青/普冻/废果 and 巴松.
   `HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true`. Replay table
   `s3_incumbent_forecast_replay_identity` is not the harvest kg target.
7. Confirm populated-origin freeze `FAIL_CLOSED_NO_LAWFUL_POPULATED_ORIGIN_TODAY`
   is not rewritten; C0 §5 `PENDING_NOT_MERGED` is not rewritten.
8. Must not read kilograms, enumerate members, invent hashes/tonnes/farm/date/cutoff
   lists, unseal TEST, flip `SOURCE_002_ROW_LEVEL_READ` / `NO_VERSIONED` /
   `NO_REVIEWED` / completeness verified, change C0/S3-D/metric STATUS, authorize
   S3-B coverage or S4, touch Python, mutate V0.2 formulas, flip §4.5, adjudicate
   3 vs 7, write `SELECT`/`FROM`/`JOIN`/`WHERE` or DSN strings, or treat H7 fixture
   `8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18` as live
   evidence.
9. Legal R1 unique flip: `DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTED`
   `false` → `true`, semantics = docs-only checklist that the frozen lawful read
   target is still bound. `IMPLEMENTED=true` after that R1 still ≠ kg actually
   read ≠ `SOURCE_002_ROW_LEVEL_READ`. Actual kg read / unique live flip of
   `SOURCE_002_ROW_LEVEL_READ` requires a later separate deterministic reader
   attestation slice, not docs-only grant/R1 alone.

### 3.2 Honest boundary

Kg-read freeze (#406) ≠ live-authority (#407) ≠ this grant ≠ execution R1 ≠ kg
read ≠ `SOURCE_002_ROW_LEVEL_READ`.
`GRANT_MERGE_DOES_NOT_FLIP_IMPLEMENTED=true`.
`GRANT_MERGE_DOES_NOT_EXECUTE_KG_ROW_LEVEL_READ=true`.
`THIS_FAMILY_DOCS_ONLY_STAGES_MUST_NOT_FLIP_SOURCE_002_ROW_LEVEL_READ=true`.
`FORBIDDEN_REWRITE_POPULATED_ORIGIN_FREEZE=true`.
`FORBIDDEN_REWRITE_C0_SECTION_5_PENDING_SNAPSHOT=true`.

## 4. Six-file manifest

| # | path |
|---|------|
| 1 | `docs/v0-3/development-plan.md` |
| 2 | `docs/v0-3/s3/s3-daily-rowset-amendment.md` |
| 3 | `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` |
| 4 | `docs/v0-3/s3/s3-accepted-s2-train-val-kg-row-level-read-contract.md` |
| 5 | `docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-kg-row-level-read-authorization.md` |
| 6 | `docs/v0-3/s3/evidence/s3-accepted-s2-train-val-kg-row-level-read-authorization.json` |

## 5. Unique flip

~~~text
S3_A2_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZED=false → true
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTED=false (companion unchanged)
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block and authorization pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §111 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` Live paragraph immediately before ## 12
- `docs/v0-3/s3/s3-accepted-s2-train-val-kg-row-level-read-contract.md` §14 pointer

## 6. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=09b60adda82b4d83315eb091b81b68c5f927fc040fe5ab20b9405db9cdfebaeb
~~~

## 7. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
GRANT_MERGE_DOES_NOT_FLIP_IMPLEMENTED=true
GRANT_MERGE_DOES_NOT_EXECUTE_KG_ROW_LEVEL_READ=true
AWAITING_COORDINATOR_REVIEW=true
~~~
