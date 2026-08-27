# V0.3-S3-A2 Accepted S2 TRAIN/VALIDATION lawful-origin implementation authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTATION_AUTHORIZATION
ARTIFACT_VERSION=s3-accepted-s2-train-val-lawful-origin-authorization-v1
TASK_ID=V03_S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTATION_GRANT_ONLY
PARALLEL_LANE=S3-A2-ACCEPTED-S2-ORIGIN
SLICE=V0.3-S3
ENGLISH_ID=ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=8c47106dfabb687499df46aa1184d87d04ff38cf
BASE_MAIN_TREE_SHA=6864dc3a133489c6abc2fcdc31b6712d04b56dcb
PARENT_CONTRACT_PR=402
PARENT_CONTRACT_MERGE=bc74487fae621b6229caf0b39441f1196d96aa13
PARENT_LIVE_AUTHORITY_PR=403
PARENT_LIVE_AUTHORITY_MERGE=8c47106dfabb687499df46aa1184d87d04ff38cf
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=785a17d515abe9af1d09e865bf04de4e885223ec4f8a3a03547bfaf9be128d3c
LIVE_AUTHORITY_WORKPAPER=docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-lawful-origin-contract-live-authority.md
LIVE_AUTHORITY_WORKPAPER_GIT_BLOB_SHA=97cdf70849c0f71d10d6983dcb4110d003f649c0
LIVE_AUTHORITY_EVIDENCE_GIT_BLOB_SHA=c420aba659d00ca53ac35fd76a071ef86cc5cbb5
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-lawful-origin-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-accepted-s2-train-val-lawful-origin-authorization.json
GRANT_ONLY=true
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
THIS_PR_IS_NOT_R1=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
GRANT_MERGE_DOES_NOT_FLIP_IMPLEMENTED=true
GRANT_MERGE_DOES_NOT_TOUCH_PYTHON=true
LATER_R1_IS_DOCS_ONLY=true
EXECUTION_CLAIM_R1_IS_DOCS_ONLY=true
FORBIDDEN_REWRITE_POPULATED_ORIGIN_FREEZE=true
FORBIDDEN_RESOLVE_3_VS_7=true
FORBIDDEN_AUTHORIZE_S3_B_COVERAGE=true
FORBIDDEN_AUTHORIZE_S4=true
~~~

The user authorized issuance of the S3-A2 **accepted S2 TRAIN/VALIDATION lawful-origin**
implementation grant after live contract authority merged on main (#403). This document
records what a **later** docs-only execution R1 may do when the user again says
「可以实施」. This PR does not execute dataset-identity-layer origin binding, does not
flip `DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTED`, does not read
SOURCE_002 row-level data, does not land identity-set members, and does not authorize
production or test code mutation.

This is **lawful-origin implementation** authorization only. Parent freeze (#402), live
contract authority (#403), populated-origin closed family, C0 §5 pending snapshot, P0,
S3-B family, and A2 identity-set family remain authoritative and are not reopened.

~~~text
S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_CONTRACT_AUTHORIZED=true
S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTED=false
SOURCE_002_ROW_LEVEL_READ=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
TEST_REMAINS_SEALED=true
COMPLETENESS_VERIFICATION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

`S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTATION_AUTHORIZED=true` ≠
`DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTED` ≠ `SOURCE_002_ROW_LEVEL_READ`
≠ members landed ≠ `NO_REVIEWED` flipped ≠ versioned forecast artifact produced ≠
`NO_VERSIONED` flipped ≠ catalog bindable ≠ completeness verified ≠ backtest/attribution/metrics
computed ≠ S3-B coverage ≠ S4 ≠ TEST unsealed ≠ populated-origin
`FAIL_CLOSED_NO_LAWFUL_POPULATED_ORIGIN_TODAY` rewritten ≠ C0 §5 `PENDING_NOT_MERGED`
rewritten. `#402` / `#403` contract-file fence
`S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTATION_AUTHORIZED=false` remains
historical freeze snapshot; live authority is `docs/v0-3/development-plan.md` §4.4.
`DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTED=false` ≠ origin binding
recorded. This evidence JSON is **not** a versioned forecast artifact, completeness
verified package, backtest package, metric results package, or attribution matrix.
Catalog first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.

## 1. Unique remaining gap (this grant does not fill it)

~~~text
S3_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_FREEZE_WORKPAPER_GIT_BLOB_SHA=ced95fc7ec856c79ebde9ecd55e3c7258eb14a35
S3_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_FREEZE_EVIDENCE_JSON_SHA256=c5d811b784425d03cbbf33cf6ee048557a88e7e8efcb9a2cde721e6463f3cfdc
UNIQUE_REMAINING_GAP=_dataset_identity_layer_origin_binding_not_yet_recorded
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTED=false
~~~

Lawful-origin freeze (#402) and live contract authority (#403) are on main. Dataset-identity-layer
origin binding defined in the frozen contract has not been recorded. This grant authorizes a
**later** docs-only execution R1 to re-bind blobs and execute the procedure — it does not
perform that execution today.

## 2. Upstream bindings

~~~text
PARENT_CONTRACT_PR=402
PARENT_CONTRACT_MERGE=bc74487fae621b6229caf0b39441f1196d96aa13
PARENT_LIVE_AUTHORITY_PR=403
PARENT_LIVE_AUTHORITY_MERGE=8c47106dfabb687499df46aa1184d87d04ff38cf
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=785a17d515abe9af1d09e865bf04de4e885223ec4f8a3a03547bfaf9be128d3c
S3_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=a062c42fe19f773c2393b6ed4d336d5fd91f1483
CURRENT_S3_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_CONTRACT_GIT_BLOB_SHA=fc518656c9bb6c8b786ae759038656718592cd46
S3_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_FREEZE_EVIDENCE_JSON_SHA256=c5d811b784425d03cbbf33cf6ee048557a88e7e8efcb9a2cde721e6463f3cfdc
CURRENT_S3_C0_CONTRACT_GIT_BLOB_SHA=e59f8a2d255df392116c65d535ae22ae3854ae98
CURRENT_S3_D_CONTRACT_GIT_BLOB_SHA=0819f429dcaf390a97a51a674ca96405eb8ebab7
CURRENT_S3_A_AMENDMENT_GIT_BLOB_SHA=257048fc0b69c55d34e59b70f1dea8be68cf0386
CURRENT_P0_CONTRACT_GIT_BLOB_SHA=841ad76810c76fc66f8dad05fe5dc7166378853e
CURRENT_DEVELOPMENT_PLAN_GIT_BLOB_SHA_AT_BASE=c696e529f47afdce09dc51404a5edcbc05bd56ae
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
~~~

Historical #402–#403 pointer snapshots retain their own `CURRENT_*` at insert time and
must not be refreshed by this grant.

## 3. Frozen subsequent R1 procedure (execution not authorized in this grant)

The following checklist is frozen for a future separately authorized docs-only execution R1
pass. This grant does not execute it.

### 3.1 Procedure steps

1. Re-bind each referenced git blob SHA on then-current `origin/main`.
2. Confirm lawful-origin freeze workpaper blob is still `ced95fc7ec856c79ebde9ecd55e3c7258eb14a35`
   and freeze evidence content SHA256 is still
   `c5d811b784425d03cbbf33cf6ee048557a88e7e8efcb9a2cde721e6463f3cfdc`; live-authority
   evidence SHA256 is still `785a17d515abe9af1d09e865bf04de4e885223ec4f8a3a03547bfaf9be128d3c`.
3. Confirm lawful-origin contract file top fence still contains
   `S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTATION_AUTHORIZED=false` (historical
   freeze snapshot; R1 must not rewrite fence).
4. Confirm lawful-origin contract top identity block `BASE_MAIN_SHA` is still
   `d3688ccbb3e213e8344f3c5a766dc9fed4a638a2` and §12/§13 historical `CURRENT_*` snapshots
   are not refreshed.
5. Confirm live §4.4 has `S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_CONTRACT_AUTHORIZED=true`
   and `S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTATION_AUTHORIZED=true`.
6. Confirm contract §3 official hashes still match S2 acceptance package (reference only,
   do not recompute); TEST remains sealed.
7. Confirm populated-origin freeze `FAIL_CLOSED_NO_LAWFUL_POPULATED_ORIGIN_TODAY` is not
   rewritten; C0 §5 `PENDING_NOT_MERGED` is not rewritten.
8. Must not read kilograms, enumerate members, invent hashes/tonnes/farm/date/cutoff lists,
   unseal TEST, flip `NO_VERSIONED` / `NO_REVIEWED` / completeness verified, change C0/S3-D/metric
   STATUS, authorize S3-B coverage or S4, touch Python, mutate V0.2 formulas, flip §4.5, adjudicate
   3 vs 7, or treat H7 fixture `8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18`
   as live evidence.
9. Legal R1 unique flip: `DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTED`
   `false` → `true`, semantics = dataset-identity-layer binding of accepted TRAIN+VALIDATION
   official hashes as this family's lawful origin. `IMPLEMENTED=true` ≠ kg read ≠ members
   landed ≠ forecast artifact exists.

### 3.2 Honest boundary

Lawful-origin freeze (#402) ≠ live-authority (#403) ≠ this grant ≠ execution R1 ≠ kg read.
`GRANT_MERGE_DOES_NOT_FLIP_IMPLEMENTED=true`.
`FORBIDDEN_REWRITE_POPULATED_ORIGIN_FREEZE=true`.
`FORBIDDEN_REWRITE_C0_SECTION_5_PENDING_SNAPSHOT=true`.

## 4. Six-file manifest

| # | path |
|---|------|
| 1 | `docs/v0-3/development-plan.md` |
| 2 | `docs/v0-3/s3/s3-daily-rowset-amendment.md` |
| 3 | `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` |
| 4 | `docs/v0-3/s3/s3-accepted-s2-train-val-lawful-origin-contract.md` |
| 5 | `docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-lawful-origin-authorization.md` |
| 6 | `docs/v0-3/s3/evidence/s3-accepted-s2-train-val-lawful-origin-authorization.json` |

## 5. Unique flip

~~~text
S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTATION_AUTHORIZED=false → true
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTED=false (companion unchanged)
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block and authorization pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §108 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` Live paragraph immediately before ## 12
- `docs/v0-3/s3/s3-accepted-s2-train-val-lawful-origin-contract.md` §13 pointer

## 6. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=c6a1e4e973600cb8ef3c8ad50aaa6453b877b6a65e48ae8cbcf840917537630f
~~~

## 7. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
GRANT_MERGE_DOES_NOT_FLIP_IMPLEMENTED=true
AWAITING_COORDINATOR_REVIEW=true
~~~
