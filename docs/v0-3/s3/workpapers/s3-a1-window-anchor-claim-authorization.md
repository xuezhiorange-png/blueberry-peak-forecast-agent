# V0.3-S3-A1 Window-anchor verified-claim authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A1_WINDOW_ANCHOR_CLAIM_AUTHORIZATION
ARTIFACT_VERSION=s3-a1-window-anchor-claim-authorization-v1
TASK_ID=V03_S3_A1_WINDOW_ANCHOR_CLAIM_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_A1_WINDOW_ANCHOR_CLAIM_GRANT_ONLY
PARALLEL_LANE=S3-A1
SLICE=V0.3-S3
ENGLISH_ID=WINDOW_ANCHOR_VERIFIED_CLAIM
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=7a6479a8cb930e2aa55090783dbf5455a784632b
BASE_MAIN_TREE_SHA=374941acb2b5c00f0316b8dae92f307375b67d66
PARENT_LIVE_AUTHORITY_PR=387
PARENT_LIVE_AUTHORITY_MERGE=7a6479a8cb930e2aa55090783dbf5455a784632b
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=f1d403146dfdd442800d5dfe4520a10717b991cafb1ed4b610af431268deac96
LIVE_AUTHORITY_WORKPAPER=docs/v0-3/s3/workpapers/s3-a1-window-anchor-contract-live-authority.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a1-window-anchor-claim-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a1-window-anchor-claim-authorization.json
GRANT_ONLY=true
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
THIS_PR_IS_NOT_R1=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
GRANT_MERGE_DOES_NOT_EXECUTE_CHECKLIST=true
GRANT_MERGE_DOES_NOT_FLIP_CLAIM_STATUS_AWAY_FROM_NOT_VERIFIED=true
GRANT_MERGE_DOES_NOT_AUTHORIZE_C0_EXECUTION=true
GRANT_MERGE_DOES_NOT_TOUCH_PYTHON=true
FORBIDDEN_TREAT_THIS_EVIDENCE_AS_VERIFIED_CLAIM_PACKAGE=true
FORBIDDEN_TREAT_THIS_EVIDENCE_AS_BACKTEST_PACKAGE=true
FORBIDDEN_REWRITE_C0_SECTION_5_PENDING_SNAPSHOT=true
FORBIDDEN_REWRITE_HISTORICAL_LIVE_AUTHORITY_POINTERS=true
~~~

The user authorized issuance of the S3-A1 **window-anchor verified-claim** grant after live contract
authority merged on main (#387). This document records what a **later** docs-only claim R1 may do
when the user again says 「可以实施」. This PR does not execute the frozen claim-verification procedure,
does not write `VERIFIED_FREEZE_STILL_BOUND` or `VERIFICATION_FAILED` to live status, does not execute
a window, does not authorize C0 execution, and does not authorize production or test code mutation.

This is **window-anchor verified-claim** authorization only. Parent A1 freeze (#300), live contract
authority (#387), amendment §5.1/§5.3, C0 §5 pending snapshot, P0, S3-B family, and A2 identity-set
family remain authoritative and are not reopened.

~~~text
S3_A1_WINDOW_ANCHOR_CONTRACT_AUTHORIZED=true
S3_A1_WINDOW_ANCHOR_CLAIM_AUTHORIZED=true
CURRENT_S3_A1_WINDOW_ANCHOR_CLAIM_STATUS=NOT_VERIFIED
S3_BACKTEST_EXECUTION_AUTHORIZED=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

`S3_A1_WINDOW_ANCHOR_CLAIM_AUTHORIZED=true` ≠ checklist executed ≠
`CURRENT_S3_A1_WINDOW_ANCHOR_CLAIM_STATUS=VERIFIED_FREEZE_STILL_BOUND` ≠ window executed ≠
evaluation window materialized ≠ `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED` ≠
`S3_C0_PIT_BACKTEST_CONTRACT_AUTHORIZED` live ≠ `S3_C_BACKTEST_EXECUTION_AUTHORIZED` ≠ backtest run ≠
C0 §5 freeze rewritten ≠ `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT` flipped. This evidence JSON is
**not** a verified-claim package or backtest package. Catalog first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. A2 identity-set family remains fail-closed.

## 1. Unique remaining gap (this grant does not fill it)

~~~text
PARENT_S3_A1_WORKPAPER_GIT_BLOB_SHA_AT_FREEZE=3db9c30ccae9ac20805cb3021caa989ebbc7f5e2
A1_EVIDENCE_JSON_SHA256=7d5e915bf1eb8b0d7a4f7f271e7f4d492023391a6860e7debc6e403c8898dc89
UNIQUE_REMAINING_GAP=_frozen_claim_verification_procedure_not_yet_executed
CURRENT_S3_A1_WINDOW_ANCHOR_CLAIM_STATUS=NOT_VERIFIED
~~~

A1 freeze (#300) and live contract authority (#387) are on main. The frozen claim-verification
procedure defined in this grant has not been executed. This grant authorizes a **later** docs-only R1
to re-bind blobs and execute the procedure — it does not perform that execution today.

## 2. Upstream bindings

~~~text
PARENT_LIVE_AUTHORITY_PR=387
PARENT_LIVE_AUTHORITY_MERGE=7a6479a8cb930e2aa55090783dbf5455a784632b
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=f1d403146dfdd442800d5dfe4520a10717b991cafb1ed4b610af431268deac96
PARENT_S3_A1_PR=300
PARENT_S3_A1_MERGE=ef3702dd168b2c4e9adff133a2807ec1819dfaa7
PARENT_S3_A1_FREEZE_COMMIT=7900e54b95c93797f665a3fc3dd2451f7c3d2f7a
PARENT_S3_A1_WORKPAPER_GIT_BLOB_SHA_AT_FREEZE=3db9c30ccae9ac20805cb3021caa989ebbc7f5e2
CURRENT_A1_WORKPAPER_GIT_BLOB_SHA=3db9c30ccae9ac20805cb3021caa989ebbc7f5e2
A1_EVIDENCE_JSON_SHA256=7d5e915bf1eb8b0d7a4f7f271e7f4d492023391a6860e7debc6e403c8898dc89
PARENT_S3_A_PR=299
PARENT_S3_A_MERGE=fd793de12bfe2df646925d9e7adc1d59c046ecdf
CURRENT_S3_A_AMENDMENT_GIT_BLOB_SHA=994c8e3e55ddec951972f2dac97764bd18122d6b
CURRENT_P0_CONTRACT_GIT_BLOB_SHA=a5a7cb1214c9e32c6c39b079e31cc6ec2c4f11ea
PARENT_S3_C0_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=3850b7cc85fa87d2cf7aa1b4fb23c3d756d6295b
CURRENT_S3_C0_CONTRACT_GIT_BLOB_SHA=dd81edd71568a3be6557160bebe947c790fcda6f
CURRENT_S3_B_CONTRACT_GIT_BLOB_SHA=43c07b3ca032e39b339281acdba4e9ad8219307b
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
ALIGNMENT_SECTION_6_SHA256=2eaf3719b1cb2e7097c6ded457098a0563b46c0965eabf38d60327b1a6b2a7a8
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
~~~

Historical #387 live-authority pointer snapshots retain their own `CURRENT_*` at insert time and must
not be refreshed by this grant.

## 3. Frozen claim-verification procedure (execution not authorized)

The following checklist is frozen for a future separately authorized claim R1 pass. This grant does
not execute it.

### 3.1 Procedure steps

1. Re-bind each referenced git blob SHA on then-current `origin/main`.
2. Confirm A1 freeze workpaper blob is still `3db9c30ccae9ac20805cb3021caa989ebbc7f5e2` and A1
   freeze evidence content SHA256 is still
   `7d5e915bf1eb8b0d7a4f7f271e7f4d492023391a6860e7debc6e403c8898dc89`.
3. Confirm amendment §5.1 still contains: `TIMEZONE=Asia/Shanghai`,
   `HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true`,
   `evaluation_window_start_date = cutoff_business_date + 1 day`,
   `evaluation_window_end_date = cutoff_business_date + H days`,
   `WINDOW_CALENDAR_DAY_COUNT=H`, `CUTOFF_DAY_EXCLUDED_FROM_WINDOW=true`,
   `WINDOW_OR_HORIZON_REALIGNMENT_FORBIDDEN=true`, `H ∈ {7,14,21}`.
4. Confirm amendment §5.3 still has cell-level EXCLUDED (no window generated) and day-level
   EXCLUDED = `REJECT_WINDOW`; EXCLUDED hole-punching for peak forbidden.
5. Confirm C0 §5 heading is still "Evaluation window anchor (S3-A1 pending)" and freeze lines still
   include `S3_A1_EVALUATION_WINDOW_ANCHOR_STATUS=PENDING_NOT_MERGED` and
   `S3_C0_MUST_NOT_INVENT_ALTERNATE_WINDOW_ANCHOR=true`. R1 must **not** rewrite those freeze lines.
6. Confirm live §4.4 has `S3_A1_WINDOW_ANCHOR_CONTRACT_AUTHORIZED=true` and
   `S3_A1_WINDOW_ANCHOR_CLAIM_AUTHORIZED=true`.
7. Confirm C0 has not added an alternate live window definition contradicting the A1 freeze
   (cutoff+1 … cutoff+H).
8. Write `CURRENT_S3_A1_WINDOW_ANCHOR_CLAIM_STATUS` in live registry and evidence JSON with legal
   values only: `VERIFIED_FREEZE_STILL_BOUND`, `VERIFICATION_FAILED`, `NOT_VERIFIED`. If amendment
   §5.1/§5.3 drifted from freeze: `VERIFICATION_FAILED`. Must not change model/parameters, must not
   execute a window, must not flip completeness / `NO_VERSIONED` / C0 execution / S3-B statuses.

### 3.2 Honest boundary

A1 freeze (#300) ≠ live-authority (#387) ≠ this grant ≠ claim R1 ≠ C0 live-authority ≠ C0 execution.
`GRANT_MERGE_DOES_NOT_EXECUTE_CHECKLIST=true`.
`GRANT_MERGE_DOES_NOT_FLIP_CLAIM_STATUS_AWAY_FROM_NOT_VERIFIED=true`.
`FORBIDDEN_REWRITE_C0_SECTION_5_PENDING_SNAPSHOT=true`.

## 4. Unique flip

~~~text
S3_A1_WINDOW_ANCHOR_CLAIM_AUTHORIZED=absent → true
CURRENT_S3_A1_WINDOW_ANCHOR_CLAIM_STATUS=NOT_VERIFIED (companion insert; not a success flip)
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block and grant pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §95 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live paragraph
- `docs/v0-3/s3/s3-pit-backtest-execution-contract.md` §17 pointer

## 5. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=60d613327cde434e16ec425c00d41f52ab843581e47b0cc952a4fa029458492f
~~~

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
GRANT_MERGE_DOES_NOT_EXECUTE_CHECKLIST=true
AWAITING_COORDINATOR_REVIEW=true
~~~
