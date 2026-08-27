# V0.3-S3-D error attribution execution authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_D_ATTRIBUTION_EXECUTION_AUTHORIZATION
ARTIFACT_VERSION=s3-d-error-attribution-execution-authorization-v1
TASK_ID=V03_S3_D_ATTRIBUTION_EXECUTION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_D_ATTRIBUTION_EXECUTION_GRANT_ONLY
PARALLEL_LANE=S3-D
SLICE=V0.3-S3
ENGLISH_ID=ERROR_ATTRIBUTION_MATRIX_EXECUTION
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=55508ec6cac1479b2d3979c6ca62927add8ce780
BASE_MAIN_TREE_SHA=af7fdc3ecc70bc842d1790cbda9bc10ef4f6edc1
PARENT_LIVE_AUTHORITY_PR=394
PARENT_LIVE_AUTHORITY_MERGE=55508ec6cac1479b2d3979c6ca62927add8ce780
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=01dd243a242cce9aca50ffb19d98cfa4f8dd1e0a1da7b7b0bb926600d220f1ed
LIVE_AUTHORITY_WORKPAPER=docs/v0-3/s3/workpapers/s3-d-error-attribution-contract-live-authority.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-d-error-attribution-execution-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-d-error-attribution-execution-authorization.json
GRANT_ONLY=true
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
THIS_PR_IS_NOT_R1=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
GRANT_MERGE_DOES_NOT_EXECUTE_CHECKLIST=true
GRANT_MERGE_DOES_NOT_EXECUTE_ATTRIBUTION=true
GRANT_MERGE_DOES_NOT_IMPLEMENT_RUNNER=true
GRANT_MERGE_DOES_NOT_TOUCH_PYTHON=true
GRANT_MERGE_DOES_NOT_FLIP_ERROR_DIAGNOSIS=true
GRANT_MERGE_DOES_NOT_FLIP_S3_D_AUTHORIZED=true
GRANT_MERGE_DOES_NOT_AUTHORIZE_S4=true
GRANT_MERGE_DOES_NOT_FLIP_STATUS_AWAY_FROM_NOT_PERFORMED=true
FORBIDDEN_REWRITE_C0_SECTION_5_PENDING_SNAPSHOT=true
FORBIDDEN_REWRITE_S3_D_FREEZE_FENCE_EXECUTION_FLAG=true
FORBIDDEN_REWRITE_HISTORICAL_POINTERS=true
FORBIDDEN_TREAT_THIS_EVIDENCE_AS_ATTRIBUTION_MATRIX_PACKAGE=true
FORBIDDEN_TREAT_THIS_EVIDENCE_AS_BACKTEST_PACKAGE=true
EXECUTION_CLAIM_R1_IS_DOCS_ONLY=true
~~~

The user authorized issuance of the S3-D **error attribution execution** grant after live contract
authority merged on main (#394). This document records what a **later** docs-only execution R1
may do when the user again says 「可以实施」. This PR does not execute the frozen attribution
execution checklist, does not write `CONTRACT_STILL_BOUND_BLOCKED` or `EXECUTION_FAILED` to live
status, does not implement a runner, does not execute attribution, and does not authorize production or
test code mutation.

This is **error attribution execution** authorization only. Parent S3-D freeze (#392), live contract
authority (#394), C0 family (closed through execution R1 #393), A1 family, C0 §5 pending snapshot,
P0, S3-B family, and A2 identity-set family remain authoritative and are not reopened.

~~~text
S3_D_ERROR_ATTRIBUTION_CONTRACT_AUTHORIZED=true
S3_D_ATTRIBUTION_EXECUTION_AUTHORIZED=true
CURRENT_S3_D_ATTRIBUTION_EXECUTION_STATUS=NOT_PERFORMED
S3_C0_PIT_BACKTEST_CONTRACT_AUTHORIZED=true
S3_C_BACKTEST_EXECUTION_AUTHORIZED=true
CURRENT_S3_C_BACKTEST_EXECUTION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

`S3_D_ATTRIBUTION_EXECUTION_AUTHORIZED=true` ≠ runner implemented ≠ attribution executed ≠
`ERROR_DIAGNOSIS=true` ≠ contribution rates computed ≠ `S3_D_AUTHORIZED` ≠ S4 authorized ≠
C0 backtest run ≠ `CURRENT_S3_C_BACKTEST_EXECUTION_STATUS` flipped ≠ C0 §5 freeze rewritten ≠
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT` flipped ≠ S3-B `VERIFICATION_FAILED` repaired.
`#392` / `#394` contract-file fence `S3_D_ATTRIBUTION_EXECUTION_AUTHORIZED=false` remains historical
freeze snapshot; live authority is `docs/v0-3/development-plan.md` §4.4.
`CURRENT_S3_D_ATTRIBUTION_EXECUTION_STATUS=NOT_PERFORMED` ≠ checklist executed. This evidence JSON
is **not** an attribution matrix package, backtest package, or versioned forecast artifact. Catalog
first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. A2 identity-set family remains
fail-closed.

## 1. Unique remaining gap (this grant does not fill it)

~~~text
S3_D_FREEZE_WORKPAPER_GIT_BLOB_SHA=e4d872c2efb398ec24a4c2c625232902c8ffec9d
S3_D_FREEZE_EVIDENCE_JSON_SHA256=1b9524cc80d1dfc5a5f6ef2fe174007c929f42ef6a7b313aa0f09d95eaad692a
UNIQUE_REMAINING_GAP=_frozen_attribution_execution_checklist_not_yet_executed
CURRENT_S3_D_ATTRIBUTION_EXECUTION_STATUS=NOT_PERFORMED
~~~

S3-D freeze (#392) and live contract authority (#394) are on main. The frozen attribution execution
checklist defined in this grant has not been executed. This grant authorizes a **later**
docs-only execution R1 to re-bind blobs and execute the procedure — it does not perform that
execution today.

## 2. Upstream bindings

~~~text
PARENT_LIVE_AUTHORITY_PR=394
PARENT_LIVE_AUTHORITY_MERGE=55508ec6cac1479b2d3979c6ca62927add8ce780
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=01dd243a242cce9aca50ffb19d98cfa4f8dd1e0a1da7b7b0bb926600d220f1ed
LIVE_AUTHORITY_WORKPAPER_GIT_BLOB_SHA=2a4533738aefede713fffa4f7920620aea252430
LIVE_AUTHORITY_EVIDENCE_GIT_BLOB_SHA=8eab6bc684c23e909f1dd65f86e09584e11411f9
PARENT_S3_D_PR=392
PARENT_S3_D_MERGE=16775371f8a639e52cbb5216487e5eacd3feaa6b
S3_D_CONTRACT_PATH=docs/v0-3/s3/s3-error-attribution-contract.md
S3_D_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=2723772fe11e623f22acb3b3bd1c17259c7ef0aa
CURRENT_S3_D_CONTRACT_GIT_BLOB_SHA=a8a5196b30413e64879112b594e4dfff6c00623e
S3_D_FREEZE_WORKPAPER=docs/v0-3/s3/workpapers/s3-d-error-attribution-contract.md
S3_D_FREEZE_WORKPAPER_GIT_BLOB_SHA=e4d872c2efb398ec24a4c2c625232902c8ffec9d
S3_D_FREEZE_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-d-error-attribution-contract.json
S3_D_FREEZE_EVIDENCE_GIT_BLOB_SHA=a0767eb4dae982f0fbfc937b492c7d15ae0274e9
S3_D_FREEZE_EVIDENCE_JSON_SHA256=1b9524cc80d1dfc5a5f6ef2fe174007c929f42ef6a7b313aa0f09d95eaad692a
PARENT_C0_R1_PR=393
PARENT_C0_R1_MERGE=6a6e8860f9cbddd570b3dcb51b1f4f2f89d599a0
C0_R1_EVIDENCE_JSON_SHA256=632211d4c0afd3a4002dcf2bb2793fc7992663b5b0df51ef32b08e99ac70d7e2
C0_R1_WORKPAPER_GIT_BLOB_SHA=f18fa01abb73927c92e909a759803a314cc3f10c
PARENT_S3_C0_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=3850b7cc85fa87d2cf7aa1b4fb23c3d756d6295b
CURRENT_S3_C0_CONTRACT_GIT_BLOB_SHA=e59f8a2d255df392116c65d535ae22ae3854ae98
S3_C0_CONTRACT_PATH=docs/v0-3/s3/s3-pit-backtest-execution-contract.md
PARENT_S3_A1_WORKPAPER_GIT_BLOB_SHA_AT_FREEZE=3db9c30ccae9ac20805cb3021caa989ebbc7f5e2
CURRENT_A1_WORKPAPER_GIT_BLOB_SHA=3db9c30ccae9ac20805cb3021caa989ebbc7f5e2
A1_R1_EVIDENCE_JSON_SHA256=5321c28fee94e61635b9ef22ade6e20e8ccc754cf1a314e5dc57b5a78b710522
CURRENT_S3_A_AMENDMENT_GIT_BLOB_SHA=43368eb07b12d6496f5502a6b5d70263cf09ab60
CURRENT_P0_CONTRACT_GIT_BLOB_SHA=8a956ef9d47168223c1842f46d1977fb333d68fc
CURRENT_S3_B_CONTRACT_GIT_BLOB_SHA=43c07b3ca032e39b339281acdba4e9ad8219307b
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
ALIGNMENT_SECTION_6_SHA256=2eaf3719b1cb2e7097c6ded457098a0563b46c0965eabf38d60327b1a6b2a7a8
CURRENT_DEVELOPMENT_PLAN_GIT_BLOB_SHA_AT_BASE=044ed71800b695c4fd8ee7ed09a0efbddaba455f
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
~~~

Historical #387–#394 pointer snapshots retain their own `CURRENT_*` at insert time and
must not be refreshed by this grant.

## 3. Frozen attribution execution procedure (execution not authorized)

The following checklist is frozen for a future separately authorized execution R1 pass. This
grant does not execute it.

### 3.1 Procedure steps

1. Re-bind each referenced git blob SHA on then-current `origin/main`.
2. Confirm S3-D freeze workpaper blob is still `e4d872c2efb398ec24a4c2c625232902c8ffec9d` and S3-D
   freeze evidence content SHA256 is still
   `1b9524cc80d1dfc5a5f6ef2fe174007c929f42ef6a7b313aa0f09d95eaad692a`.
3. Confirm S3-D contract file top fence still contains
   `S3_D_ATTRIBUTION_EXECUTION_AUTHORIZED=false` (historical freeze snapshot; R1 must not rewrite
   fence).
4. Confirm S3-D contract top identity block `BASE_MAIN_SHA` is still
   `2b0ea55872542501fff246c9d87c6fda7ae8802f` and §12 live-authority pointer historical
   `CURRENT_*` snapshots are not refreshed.
5. Confirm live §4.4 has `S3_D_ERROR_ATTRIBUTION_CONTRACT_AUTHORIZED=true` and
   `S3_D_ATTRIBUTION_EXECUTION_AUTHORIZED=true`.
6. Confirm C0 §5 heading is still "Evaluation window anchor (S3-A1 pending)" and freeze lines
   still include `S3_A1_EVALUATION_WINDOW_ANCHOR_STATUS=PENDING_NOT_MERGED` and
   `S3_C0_MUST_NOT_INVENT_ALTERNATE_WINDOW_ANCHOR=true`. R1 must **not** rewrite those freeze
   lines.
7. Confirm blockers remain: `CURRENT_S3_C_BACKTEST_EXECUTION_STATUS=CONTRACT_STILL_BOUND_BLOCKED`;
   no legal backtest package; `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false`;
   `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true`; `SOURCE_002_ROW_LEVEL_READ=false`;
   `TEST_REMAINS_SEALED=true`; S3-B `CURRENT_P*_SEMANTICS_STATUS=VERIFICATION_FAILED`;
   `QUANTILE_CALIBRATION_DIMENSION_COMPUTABLE=false`; `S3_B_COVERAGE_EXECUTION_AUTHORIZED=false`.
8. Must not implement attribution runner, execute attribution, invent tonnes/contribution rates/
   farms/dates/SQL table names, read SOURCE_002 row-level, unseal TEST, or change model/parameters;
   must not flip `NO_VERSIONED` / completeness / `ERROR_DIAGNOSIS` / `S3_D_AUTHORIZED`; must not
   adjudicate P0 3-day vs 7-day window.
9. Write `CURRENT_S3_D_ATTRIBUTION_EXECUTION_STATUS` in live registry and evidence JSON with legal
   values only: `CONTRACT_STILL_BOUND_BLOCKED`, `EXECUTION_FAILED`, `NOT_PERFORMED`. Forbidden:
   `EXECUTED`, `SUCCESS`, `PASS`, `VERIFIED_TRUE`, `ERROR_DIAGNOSIS=true`.

### 3.2 Honest boundary

S3-D freeze (#392) ≠ live-authority (#394) ≠ this grant ≠ execution R1 ≠ runner implementation.
`GRANT_MERGE_DOES_NOT_EXECUTE_CHECKLIST=true`.
`GRANT_MERGE_DOES_NOT_FLIP_STATUS_AWAY_FROM_NOT_PERFORMED=true`.
`FORBIDDEN_REWRITE_C0_SECTION_5_PENDING_SNAPSHOT=true`.
`FORBIDDEN_REWRITE_S3_D_FREEZE_FENCE_EXECUTION_FLAG=true`.

## 4. Unique flip

~~~text
S3_D_ATTRIBUTION_EXECUTION_AUTHORIZED=absent → true
CURRENT_S3_D_ATTRIBUTION_EXECUTION_STATUS=NOT_PERFORMED (companion insert; not a success flip)
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block and grant pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §101 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live paragraph
- `docs/v0-3/s3/s3-error-attribution-contract.md` §13 pointer

## 5. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=5076168044f30e20ffa7d74c07b3808d88d3036c350029d05068dbc6da7a7590
~~~

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
GRANT_MERGE_DOES_NOT_EXECUTE_CHECKLIST=true
AWAITING_COORDINATOR_REVIEW=true
~~~
