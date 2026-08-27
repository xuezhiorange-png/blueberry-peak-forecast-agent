# V0.3-S3-C0 PIT backtest execution authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_C_BACKTEST_EXECUTION_AUTHORIZATION
ARTIFACT_VERSION=s3-c0-pit-backtest-execution-authorization-v1
TASK_ID=V03_S3_C_BACKTEST_EXECUTION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_C_BACKTEST_EXECUTION_GRANT_ONLY
PARALLEL_LANE=S3-C0
SLICE=V0.3-S3
ENGLISH_ID=CURRENT_MODEL_POINT_IN_TIME_BACKTEST_AND_ERROR_DIAGNOSIS
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=7e8cb6d9fb4ba60bc82b69fd04f33eec52f56727
BASE_MAIN_TREE_SHA=58e64edf4030ac11d05246972ebeccbfd79ef64b
PARENT_LIVE_AUTHORITY_PR=390
PARENT_LIVE_AUTHORITY_MERGE=7e8cb6d9fb4ba60bc82b69fd04f33eec52f56727
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=5e1221c64f469e1763413a2be8783c2d0a9654cc408851e84e3cfe4834ff4566
LIVE_AUTHORITY_WORKPAPER=docs/v0-3/s3/workpapers/s3-c0-pit-backtest-contract-live-authority.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-c0-pit-backtest-execution-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-c0-pit-backtest-execution-authorization.json
GRANT_ONLY=true
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
THIS_PR_IS_NOT_R1=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
GRANT_MERGE_DOES_NOT_EXECUTE_CHECKLIST=true
GRANT_MERGE_DOES_NOT_EXECUTE_BACKTEST=true
GRANT_MERGE_DOES_NOT_IMPLEMENT_RUNNER=true
GRANT_MERGE_DOES_NOT_TOUCH_PYTHON=true
GRANT_MERGE_DOES_NOT_FLIP_METRIC_EXECUTION=true
GRANT_MERGE_DOES_NOT_AUTHORIZE_S3_D=true
GRANT_MERGE_DOES_NOT_FLIP_STATUS_AWAY_FROM_NOT_PERFORMED=true
FORBIDDEN_REWRITE_C0_SECTION_5_PENDING_SNAPSHOT=true
FORBIDDEN_REWRITE_C0_FREEZE_FENCE_EXECUTION_FLAG=true
FORBIDDEN_REWRITE_HISTORICAL_POINTERS=true
FORBIDDEN_TREAT_THIS_EVIDENCE_AS_BACKTEST_PACKAGE=true
EXECUTION_CLAIM_R1_IS_DOCS_ONLY=true
~~~

The user authorized issuance of the S3-C **PIT backtest execution** grant after live contract
authority merged on main (#390). This document records what a **later** docs-only execution R1
may do when the user again says 「可以实施」. This PR does not execute the frozen execution
checklist, does not write `CONTRACT_STILL_BOUND_BLOCKED` or `EXECUTION_FAILED` to live status,
does not implement a runner, does not execute backtests, and does not authorize production or
test code mutation.

This is **PIT backtest execution** authorization only. Parent C0 freeze (#302), live contract
authority (#390), A1 family, C0 §5 pending snapshot, P0, S3-B family, and A2 identity-set
family remain authoritative and are not reopened.

~~~text
S3_C0_PIT_BACKTEST_CONTRACT_AUTHORIZED=true
S3_C_BACKTEST_EXECUTION_AUTHORIZED=true
CURRENT_S3_C_BACKTEST_EXECUTION_STATUS=NOT_PERFORMED
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

`S3_C_BACKTEST_EXECUTION_AUTHORIZED=true` ≠ runner implemented ≠ backtest run ≠
`S3_METRIC_EXECUTION_AUTHORIZED` ≠ window executed ≠ evaluation window materialized ≠
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED` ≠ C0 §5 freeze rewritten ≠
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT` flipped ≠ S3-B `VERIFICATION_FAILED` repaired ≠
S3-D authorized. `#302` / `#390` contract-file fence `S3_C_BACKTEST_EXECUTION_AUTHORIZED=false`
remains historical freeze snapshot; live authority is `docs/v0-3/development-plan.md` §4.4.
`CURRENT_S3_C_BACKTEST_EXECUTION_STATUS=NOT_PERFORMED` ≠ checklist executed. This evidence JSON
is **not** a backtest package or versioned forecast artifact. Catalog first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. A2 identity-set family remains fail-closed.

## 1. Unique remaining gap (this grant does not fill it)

~~~text
PARENT_S3_C0_WORKPAPER_GIT_BLOB_SHA_AT_FREEZE=3b9909a50a0daf0869b4727f2b089bc0e1686ed3
S3_C0_EVIDENCE_JSON_SHA256=12c40e013c60de9f9dbcfd7b5e7788281d9c7d6adcde641d6d436b3e65b5d7e1
UNIQUE_REMAINING_GAP=_frozen_execution_checklist_not_yet_executed
CURRENT_S3_C_BACKTEST_EXECUTION_STATUS=NOT_PERFORMED
~~~

C0 freeze (#302) and live contract authority (#390) are on main. The frozen execution
checklist defined in this grant has not been executed. This grant authorizes a **later**
docs-only execution R1 to re-bind blobs and execute the procedure — it does not perform that
execution today.

## 2. Upstream bindings

~~~text
PARENT_LIVE_AUTHORITY_PR=390
PARENT_LIVE_AUTHORITY_MERGE=7e8cb6d9fb4ba60bc82b69fd04f33eec52f56727
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=5e1221c64f469e1763413a2be8783c2d0a9654cc408851e84e3cfe4834ff4566
LIVE_AUTHORITY_WORKPAPER_GIT_BLOB_SHA=87820baa7f6261dec2a4ca20b43fb607ca0b4b9e
LIVE_AUTHORITY_EVIDENCE_GIT_BLOB_SHA=e77be08287af25fc83a8ecd2f06f8348db6a5c60
PARENT_S3_C0_PR=302
PARENT_S3_C0_MERGE=fb97a843f7026ece9bb227ee9981beca53c566f5
PARENT_S3_C0_WORKPAPER_GIT_BLOB_SHA_AT_FREEZE=3b9909a50a0daf0869b4727f2b089bc0e1686ed3
CURRENT_C0_WORKPAPER_GIT_BLOB_SHA=3b9909a50a0daf0869b4727f2b089bc0e1686ed3
S3_C0_EVIDENCE_JSON_SHA256=12c40e013c60de9f9dbcfd7b5e7788281d9c7d6adcde641d6d436b3e65b5d7e1
C0_EVIDENCE_GIT_BLOB_SHA=bbded6e2b98b782d36558ce9c3163d82d22f1765
PARENT_S3_C0_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=3850b7cc85fa87d2cf7aa1b4fb23c3d756d6295b
CURRENT_S3_C0_CONTRACT_GIT_BLOB_SHA=a2933f3b28178152741ba44a87f65e01edbd0c20
PARENT_S3_A1_WORKPAPER_GIT_BLOB_SHA_AT_FREEZE=3db9c30ccae9ac20805cb3021caa989ebbc7f5e2
A1_R1_EVIDENCE_JSON_SHA256=5321c28fee94e61635b9ef22ade6e20e8ccc754cf1a314e5dc57b5a78b710522
CURRENT_S3_A_AMENDMENT_GIT_BLOB_SHA=ad2f72a3d74c9070d66016871e11bf256828e2f4
CURRENT_P0_CONTRACT_GIT_BLOB_SHA=e6a88ce81ac84e6f62619a177da53b8d38792e39
CURRENT_S3_B_CONTRACT_GIT_BLOB_SHA=43c07b3ca032e39b339281acdba4e9ad8219307b
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
ALIGNMENT_SECTION_6_SHA256=2eaf3719b1cb2e7097c6ded457098a0563b46c0965eabf38d60327b1a6b2a7a8
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
~~~

Historical #387/#388/#389/#390 pointer snapshots retain their own `CURRENT_*` at insert time and
must not be refreshed by this grant.

## 3. Frozen execution procedure (execution not authorized)

The following checklist is frozen for a future separately authorized execution R1 pass. This
grant does not execute it.

### 3.1 Procedure steps

1. Re-bind each referenced git blob SHA on then-current `origin/main`.
2. Confirm C0 freeze workpaper blob is still `3b9909a50a0daf0869b4727f2b089bc0e1686ed3` and C0
   freeze evidence content SHA256 is still
   `12c40e013c60de9f9dbcfd7b5e7788281d9c7d6adcde641d6d436b3e65b5d7e1`.
3. Confirm C0 contract file top fence still contains
   `S3_C_BACKTEST_EXECUTION_AUTHORIZED=false` (historical freeze snapshot; R1 must not rewrite
   fence).
4. Confirm C0 §5 heading is still "Evaluation window anchor (S3-A1 pending)" and freeze lines
   still include `S3_A1_EVALUATION_WINDOW_ANCHOR_STATUS=PENDING_NOT_MERGED` and
   `S3_C0_MUST_NOT_INVENT_ALTERNATE_WINDOW_ANCHOR=true`. R1 must **not** rewrite those freeze
   lines.
5. Confirm live §4.4 has `S3_C0_PIT_BACKTEST_CONTRACT_AUTHORIZED=true` and
   `S3_C_BACKTEST_EXECUTION_AUTHORIZED=true`.
6. Confirm A1 freeze workpaper blob is still `3db9c30ccae9ac20805cb3021caa989ebbc7f5e2` and live
   `CURRENT_S3_A1_WINDOW_ANCHOR_CLAIM_STATUS=VERIFIED_FREEZE_STILL_BOUND`.
7. Confirm blockers remain: `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false`;
   `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true`; `SOURCE_002_ROW_LEVEL_READ=false`;
   `TEST_REMAINS_SEALED=true`; S3-B `CURRENT_P*_SEMANTICS_STATUS=VERIFICATION_FAILED`;
   `S3_B_COVERAGE_EXECUTION_AUTHORIZED=false`.
8. Must not implement runner, execute backtest, invent tonnes/farms/dates/SQL table names, read
   SOURCE_002 row-level, unseal TEST, or change model/parameters; must not flip `NO_VERSIONED` /
   completeness / coverage.
9. Write `CURRENT_S3_C_BACKTEST_EXECUTION_STATUS` in live registry and evidence JSON with legal
   values only: `CONTRACT_STILL_BOUND_BLOCKED`, `EXECUTION_FAILED`, `NOT_PERFORMED`. Forbidden:
   `EXECUTED`, `SUCCESS`, `PASS`, `VERIFIED_TRUE`.

### 3.2 Honest boundary

C0 freeze (#302) ≠ live-authority (#390) ≠ this grant ≠ execution R1 ≠ runner implementation.
`GRANT_MERGE_DOES_NOT_EXECUTE_CHECKLIST=true`.
`GRANT_MERGE_DOES_NOT_FLIP_STATUS_AWAY_FROM_NOT_PERFORMED=true`.
`FORBIDDEN_REWRITE_C0_SECTION_5_PENDING_SNAPSHOT=true`.
`FORBIDDEN_REWRITE_C0_FREEZE_FENCE_EXECUTION_FLAG=true`.

## 4. Unique flip

~~~text
S3_C_BACKTEST_EXECUTION_AUTHORIZED=absent → true
CURRENT_S3_C_BACKTEST_EXECUTION_STATUS=NOT_PERFORMED (companion insert; not a success flip)
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block and grant pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §98 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live paragraph
- `docs/v0-3/s3/s3-pit-backtest-execution-contract.md` §20 pointer

## 5. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=607bebc01bd136f0c38abaa23c2dff9ac393a2cf7d0c10537977a6dfd005c5c0
~~~

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
GRANT_MERGE_DOES_NOT_EXECUTE_CHECKLIST=true
AWAITING_COORDINATOR_REVIEW=true
~~~
