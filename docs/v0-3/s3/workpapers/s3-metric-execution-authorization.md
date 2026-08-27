# V0.3-S3 Metric execution authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_METRIC_EXECUTION_AUTHORIZATION
ARTIFACT_VERSION=s3-metric-execution-authorization-v1
TASK_ID=V03_S3_METRIC_EXECUTION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_METRIC_EXECUTION_GRANT_ONLY
PARALLEL_LANE=S3-METRIC
SLICE=V0.3-S3
ENGLISH_ID=S3_METRIC_EXECUTION
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=1a751e6a59c60b9c41c578f61773bdf236b63ca3
BASE_MAIN_TREE_SHA=d0c4a6eac2ee411695710e1a683e07789da8f786
PARENT_LIVE_AUTHORITY_PR=398
PARENT_LIVE_AUTHORITY_MERGE=1a751e6a59c60b9c41c578f61773bdf236b63ca3
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=d599906aef3560893ee56367d480bac4979b4de39c62ed4688604a7cc6eca5b0
LIVE_AUTHORITY_WORKPAPER=docs/v0-3/s3/workpapers/s3-metric-execution-contract-live-authority.md
LIVE_AUTHORITY_WORKPAPER_GIT_BLOB_SHA=9aa92c3fed0e57395f8c7e27e2b4ff084320df7e
LIVE_AUTHORITY_EVIDENCE_GIT_BLOB_SHA=4755d67468cf1bb88b5d6afef403a0dba49e7f4b
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-metric-execution-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-metric-execution-authorization.json
GRANT_ONLY=true
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
THIS_PR_IS_NOT_R1=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
GRANT_MERGE_DOES_NOT_EXECUTE_CHECKLIST=true
GRANT_MERGE_DOES_NOT_EXECUTE_METRICS=true
GRANT_MERGE_DOES_NOT_IMPLEMENT_RUNNER=true
GRANT_MERGE_DOES_NOT_TOUCH_PYTHON=true
GRANT_MERGE_DOES_NOT_ACCEPT_S1=true
GRANT_MERGE_DOES_NOT_MUTATE_V0_2_FORMULAS=true
GRANT_MERGE_DOES_NOT_AUTHORIZE_S4=true
GRANT_MERGE_DOES_NOT_FLIP_STATUS_AWAY_FROM_NOT_PERFORMED=true
FORBIDDEN_REWRITE_C0_SECTION_5_PENDING_SNAPSHOT=true
FORBIDDEN_REWRITE_METRIC_FREEZE_FENCE=true
FORBIDDEN_REWRITE_HISTORICAL_POINTERS=true
FORBIDDEN_EDIT_C0_CONTRACT=true
FORBIDDEN_TREAT_THIS_EVIDENCE_AS_METRIC_RESULTS_PACKAGE=true
FORBIDDEN_TREAT_THIS_EVIDENCE_AS_BACKTEST_PACKAGE=true
FORBIDDEN_TREAT_THIS_EVIDENCE_AS_ATTRIBUTION_MATRIX_PACKAGE=true
EXECUTION_CLAIM_R1_IS_DOCS_ONLY=true
~~~

The user authorized issuance of the S3 **metric execution** grant after live contract
authority merged on main (#398). This document records what a **later** docs-only execution R1
may do when the user again says 「可以实施」. This PR does not execute the frozen metric
execution checklist, does not write `CONTRACT_STILL_BOUND_BLOCKED` or `EXECUTION_FAILED` to live
status, does not implement a runner, does not execute metrics, and does not authorize production or
test code mutation.

This is **metric execution** authorization only. Parent S3 metric freeze (#397), live contract
authority (#398), C0 family (closed through execution R1 #393), S3-D family (closed through
execution R1 #396), A1 family, C0 §5 pending snapshot, P0, S3-B family, and A2 identity-set family
remain authoritative and are not reopened.

~~~text
S3_METRIC_EXECUTION_CONTRACT_AUTHORIZED=true
S3_METRIC_EXECUTION_AUTHORIZED=true
CURRENT_S3_METRIC_EXECUTION_STATUS=NOT_PERFORMED
S3_C0_PIT_BACKTEST_CONTRACT_AUTHORIZED=true
S3_C_BACKTEST_EXECUTION_AUTHORIZED=true
CURRENT_S3_C_BACKTEST_EXECUTION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
S3_D_ERROR_ATTRIBUTION_CONTRACT_AUTHORIZED=true
S3_D_ATTRIBUTION_EXECUTION_AUTHORIZED=true
CURRENT_S3_D_ATTRIBUTION_EXECUTION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LEGAL_BACKTEST_PACKAGE=true
V0_3_METRIC_CONTRACT_STATUS=PENDING_S1_ACCEPTANCE
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

`S3_METRIC_EXECUTION_AUTHORIZED=true` ≠ runner implemented ≠ metrics computed ≠ `EXECUTED` ≠
completeness verified ≠ `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT` flipped ≠ S3-B coverage
authorized ≠ S1 acceptance ≠ formula change ≠ 3 vs 7 resolved ≠ TEST unsealed ≠ S4 authorized ≠
C0 `CURRENT_S3_C_BACKTEST_EXECUTION_STATUS` flipped ≠ S3-D
`CURRENT_S3_D_ATTRIBUTION_EXECUTION_STATUS` flipped. `#397` / `#398` contract-file fence
`S3_METRIC_EXECUTION_AUTHORIZED=false` remains historical freeze snapshot; live authority is
`docs/v0-3/development-plan.md` §4.4. `CURRENT_S3_METRIC_EXECUTION_STATUS=NOT_PERFORMED` ≠
checklist executed. This evidence JSON is **not** a metric results package, backtest package,
attribution matrix, or versioned forecast artifact. Catalog first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.

## 1. Unique remaining gap (this grant does not fill it)

~~~text
S3_METRIC_FREEZE_WORKPAPER_GIT_BLOB_SHA=e81f0456b964e677e58576eaf99d8d5f5dbad426
S3_METRIC_FREEZE_EVIDENCE_JSON_SHA256=6c8f7f2ea43b7aee0a7531035e12370dc67ea05dacd79292b6ead775929be6db
UNIQUE_REMAINING_GAP=_frozen_metric_execution_checklist_not_yet_executed
CURRENT_S3_METRIC_EXECUTION_STATUS=NOT_PERFORMED
~~~

S3 metric freeze (#397) and live contract authority (#398) are on main. The frozen metric execution
checklist defined in this grant has not been executed. This grant authorizes a **later**
docs-only execution R1 to re-bind blobs and execute the procedure — it does not perform that
execution today.

## 2. Upstream bindings

~~~text
PARENT_LIVE_AUTHORITY_PR=398
PARENT_LIVE_AUTHORITY_MERGE=1a751e6a59c60b9c41c578f61773bdf236b63ca3
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=d599906aef3560893ee56367d480bac4979b4de39c62ed4688604a7cc6eca5b0
LIVE_AUTHORITY_WORKPAPER_GIT_BLOB_SHA=9aa92c3fed0e57395f8c7e27e2b4ff084320df7e
LIVE_AUTHORITY_EVIDENCE_GIT_BLOB_SHA=4755d67468cf1bb88b5d6afef403a0dba49e7f4b
PARENT_S3_METRIC_PR=397
PARENT_S3_METRIC_MERGE=29aba4886ba20bd7d38e52e57527754ba8b65081
S3_METRIC_CONTRACT_PATH=docs/v0-3/s3/s3-metric-execution-contract.md
S3_METRIC_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=1197a32779dee76cb5f43ce86f761389501b501b
CURRENT_S3_METRIC_CONTRACT_GIT_BLOB_SHA=223d363f4b9113995747fb8a4e6c816ae1495b1a
S3_METRIC_FREEZE_WORKPAPER=docs/v0-3/s3/workpapers/s3-metric-execution-contract.md
S3_METRIC_FREEZE_WORKPAPER_GIT_BLOB_SHA=e81f0456b964e677e58576eaf99d8d5f5dbad426
S3_METRIC_FREEZE_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-metric-execution-contract.json
S3_METRIC_FREEZE_EVIDENCE_GIT_BLOB_SHA=7d8d13e4e139fd2130c53ec5699e9b3c67dc7452
S3_METRIC_FREEZE_EVIDENCE_JSON_SHA256=6c8f7f2ea43b7aee0a7531035e12370dc67ea05dacd79292b6ead775929be6db
S3_D_R1_EVIDENCE_JSON_SHA256=7bc94666a5087cace5c6f6ff6c735b62fa552cb747d76f7d4b5d6e7dc6712119
C0_R1_EVIDENCE_JSON_SHA256=632211d4c0afd3a4002dcf2bb2793fc7992663b5b0df51ef32b08e99ac70d7e2
CURRENT_S3_C0_CONTRACT_GIT_BLOB_SHA=e59f8a2d255df392116c65d535ae22ae3854ae98
CURRENT_S3_D_CONTRACT_GIT_BLOB_SHA=0819f429dcaf390a97a51a674ca96405eb8ebab7
CURRENT_S3_A_AMENDMENT_GIT_BLOB_SHA=729e6c6ffdb1dac4ca8c03c16ac99675600b18bb
CURRENT_P0_CONTRACT_GIT_BLOB_SHA=26bd92650e701a8ae2c9b3b9c1d5086067b797f9
CURRENT_S3_B_CONTRACT_GIT_BLOB_SHA=43c07b3ca032e39b339281acdba4e9ad8219307b
CURRENT_DEVELOPMENT_PLAN_GIT_BLOB_SHA_AT_BASE=9a98b80a905174b74500ea34336528187b7a1992
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
~~~

Historical #397–#398 pointer snapshots retain their own `CURRENT_*` at insert time and
must not be refreshed by this grant.

## 3. Frozen metric execution procedure (execution not authorized)

The following checklist is frozen for a future separately authorized execution R1 pass. This
grant does not execute it.

### 3.1 Procedure steps

1. Re-bind each referenced git blob SHA on then-current `origin/main`.
2. Confirm S3 metric freeze workpaper blob is still `e81f0456b964e677e58576eaf99d8d5f5dbad426`
   and S3 metric freeze evidence content SHA256 is still
   `6c8f7f2ea43b7aee0a7531035e12370dc67ea05dacd79292b6ead775929be6db`.
3. Confirm S3 metric contract file top fence still contains
   `S3_METRIC_EXECUTION_AUTHORIZED=false` (historical freeze snapshot; R1 must not rewrite
   fence).
4. Confirm S3 metric contract top identity block `BASE_MAIN_SHA` is still
   `e6f1fa41f4b4e6ed1533fb4e50cf74c2a80b6a8f` and §12 live-authority pointer historical
   `CURRENT_*` snapshots are not refreshed.
5. Confirm live §4.4 has `S3_METRIC_EXECUTION_CONTRACT_AUTHORIZED=true` and
   `S3_METRIC_EXECUTION_AUTHORIZED=true`.
6. Confirm C0 §5 heading is still "Evaluation window anchor (S3-A1 pending)" and freeze lines
   still include `S3_A1_EVALUATION_WINDOW_ANCHOR_STATUS=PENDING_NOT_MERGED` and
   `S3_C0_MUST_NOT_INVENT_ALTERNATE_WINDOW_ANCHOR=true`. R1 must **not** rewrite those freeze
   lines.
7. Confirm blockers remain: `CURRENT_S3_C_BACKTEST_EXECUTION_STATUS=CONTRACT_STILL_BOUND_BLOCKED`;
   `CURRENT_S3_D_ATTRIBUTION_EXECUTION_STATUS=CONTRACT_STILL_BOUND_BLOCKED`; no legal backtest
   package; `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false`;
   `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true`; `SOURCE_002_ROW_LEVEL_READ=false`;
   `TEST_REMAINS_SEALED=true`; S3-B `CURRENT_P*_SEMANTICS_STATUS=VERIFICATION_FAILED`;
   `QUANTILE_CALIBRATION_METRICS_COMPUTABLE=false`; `S3_B_COVERAGE_EXECUTION_AUTHORIZED=false`.
8. Must not implement metric runner, execute metrics, invent tonnes/metric values/farms/dates/SQL
   table names, read SOURCE_002 row-level, unseal TEST, mutate V0.2 formulas, accept S1, or change
   model/parameters; must not flip `NO_VERSIONED` / completeness / C0 or S3-D STATUS; must not
   adjudicate P0 3-day vs 7-day window.
9. Write `CURRENT_S3_METRIC_EXECUTION_STATUS` in live registry and evidence JSON with legal
   values only: `CONTRACT_STILL_BOUND_BLOCKED`, `EXECUTION_FAILED`, `NOT_PERFORMED`. Forbidden:
   `EXECUTED`, `SUCCESS`, `PASS`, `VERIFIED_TRUE`.

### 3.2 Honest boundary

S3 metric freeze (#397) ≠ live-authority (#398) ≠ this grant ≠ execution R1 ≠ runner implementation.
`GRANT_MERGE_DOES_NOT_EXECUTE_CHECKLIST=true`.
`GRANT_MERGE_DOES_NOT_FLIP_STATUS_AWAY_FROM_NOT_PERFORMED=true`.
`FORBIDDEN_REWRITE_C0_SECTION_5_PENDING_SNAPSHOT=true`.
`FORBIDDEN_REWRITE_METRIC_FREEZE_FENCE=true`.

## 4. Unique flip

~~~text
S3_METRIC_EXECUTION_AUTHORIZED=absent → true
CURRENT_S3_METRIC_EXECUTION_STATUS=NOT_PERFORMED (companion insert; not a success flip)
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block and grant pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §104 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live paragraph
- `docs/v0-3/s3/s3-metric-execution-contract.md` §13 pointer

## 5. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=86114249be6418924b042f66a09623ef6aa2eb124238068ab6260c29a3c54f94
~~~

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
GRANT_MERGE_DOES_NOT_EXECUTE_CHECKLIST=true
AWAITING_COORDINATOR_REVIEW=true
~~~
