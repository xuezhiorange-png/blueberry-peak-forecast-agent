# V0.3-S3-A1 Window-anchor verified-claim R1

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A1_WINDOW_ANCHOR_CLAIM_R1
ARTIFACT_VERSION=s3-a1-window-anchor-claim-r1-v1
TASK_ID=V03_S3_A1_WINDOW_ANCHOR_CLAIM_R1
TASK_CLASS=IMPLEMENTATION
AUTHORIZATION_SCOPE=S3_A1_WINDOW_ANCHOR_CLAIM_IMPLEMENTATION_ONLY
PARALLEL_LANE=S3-A1
SLICE=V0.3-S3
ENGLISH_ID=WINDOW_ANCHOR_VERIFIED_CLAIM
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=a0aa8946f356e207d18bff3b18ab95a81a24147b
BASE_MAIN_TREE_SHA=c01ee160420bbab86d0b14936c6ba21644fb9dae
PARENT_GRANT_PR=388
PARENT_GRANT_MERGE=a0aa8946f356e207d18bff3b18ab95a81a24147b
GRANT_EVIDENCE_JSON_SHA256=60d613327cde434e16ec425c00d41f52ab843581e47b0cc952a4fa029458492f
GRANT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a1-window-anchor-claim-authorization.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a1-window-anchor-claim-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a1-window-anchor-claim-r1.json
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
IMPLEMENTATION_R1=true
VERIFIED_CLAIM_R1_IS_DOCS_ONLY=true
CHECKLIST_EXECUTED=true
~~~

This workpaper records docs-only verified-claim R1 per grant (#388) and frozen
`docs/v0-3/s3/workpapers/s3-a1-window-anchor-claim-authorization.md` §3.1.
Code-read traced window-anchor contract bindings on `origin/main` at base
`a0aa8946` with git blob bindings. This R1 does not modify Python, execute a
window, materialize evaluation rows, or flip completeness / C0 execution /
`NO_VERSIONED` / S3-B statuses.

~~~text
S3_A1_WINDOW_ANCHOR_CONTRACT_AUTHORIZED=true
S3_A1_WINDOW_ANCHOR_CLAIM_AUTHORIZED=true
CURRENT_S3_A1_WINDOW_ANCHOR_CLAIM_STATUS=VERIFIED_FREEZE_STILL_BOUND
S3_BACKTEST_EXECUTION_AUTHORIZED=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
~~~

`CHECKLIST_EXECUTED=true` ≠ window executed ≠ evaluation window materialized ≠
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED` ≠ `S3_C0_PIT_BACKTEST_CONTRACT_AUTHORIZED`
live ≠ `S3_C_BACKTEST_EXECUTION_AUTHORIZED` ≠ backtest run ≠ C0 §5 freeze
rewritten ≠ `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT` flipped ≠ S3-B
`VERIFICATION_FAILED` repaired. C0 §5 `PENDING_NOT_MERGED` is an expected
historical freeze snapshot, not `VERIFICATION_FAILED`. This evidence is not a
backtest package or versioned forecast artifact. Catalog first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.

## 1. Frozen §3.1 execution summary

### 1.1 Step 1 — Git blob re-bind on `origin/main` at `a0aa8946`

~~~text
docs/v0-3/development-plan.md=1a804783e71bb642890467a8526a678a79f8319c
docs/v0-3/s3/s3-daily-rowset-amendment.md=5b246de53475ca8d5447df3606ef657ae15cc4c5
docs/v0-3/s3/s3-pit-backtest-execution-contract.md=998c47dcbf1d54b161561309c3edccb34426dd9a
docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md=2ebd82eb90739cf6e25bc0426ec50af1f53c897b
docs/v0-3/s3/workpapers/s3-a1-window-anchor.md=3db9c30ccae9ac20805cb3021caa989ebbc7f5e2
docs/v0-3/s3/evidence/s3-a1-window-anchor.json=6979179b7823061165cbffb852a69e81e8ad727c
docs/v0-3/s3/workpapers/s3-a1-window-anchor-claim-authorization.md=e0fa252ad57f5facc92930f26ec25dd667bcb2d5
docs/v0-3/s3/evidence/s3-a1-window-anchor-claim-authorization.json=1eed6897380aae033d003e7845c639cbe882a6c8
docs/v0-3/s3/workpapers/s3-a1-window-anchor-contract-live-authority.md=9d7854cb1c5e67600856b5eb851f8a17ec5ee008
docs/v0-3/s3/s3-quantile-semantics-contract.md=43c07b3ca032e39b339281acdba4e9ad8219307b
REBIND_COMPLETE=true
~~~

### 1.2 Step 2 — A1 freeze workpaper and evidence unchanged

~~~text
PARENT_S3_A1_WORKPAPER_GIT_BLOB_SHA_AT_FREEZE=3db9c30ccae9ac20805cb3021caa989ebbc7f5e2
CURRENT_A1_WORKPAPER_GIT_BLOB_SHA=3db9c30ccae9ac20805cb3021caa989ebbc7f5e2
A1_EVIDENCE_JSON_SHA256=7d5e915bf1eb8b0d7a4f7f271e7f4d492023391a6860e7debc6e403c8898dc89
A1_EVIDENCE_GIT_BLOB_SHA=6979179b7823061165cbffb852a69e81e8ad727c
FREEZE_WORKPAPER_BYTE_IDENTICAL=true
FREEZE_EVIDENCE_CONTENT_SHA256_UNCHANGED=true
~~~

### 1.3 Step 3 — Amendment §5.1 window anchor rules unchanged

Authority: `docs/v0-3/s3/s3-daily-rowset-amendment.md` §5.1.1 at blob
`5b246de53475ca8d5447df3606ef657ae15cc4c5`.

~~~text
TIMEZONE=Asia/Shanghai
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
evaluation_window_start_date=cutoff_business_date+1 day
evaluation_window_end_date=cutoff_business_date+H days
WINDOW_CALENDAR_DAY_COUNT=H
CUTOFF_DAY_EXCLUDED_FROM_WINDOW=true
WINDOW_OR_HORIZON_REALIGNMENT_FORBIDDEN=true
H_IN_{7,14,21}=true
AMENDMENT_SECTION_5_1_UNCHANGED=true
~~~

### 1.4 Step 4 — Amendment §5.3 EXCLUDED semantics unchanged

Authority: `docs/v0-3/s3/s3-daily-rowset-amendment.md` §5.3 at blob
`5b246de53475ca8d5447df3606ef657ae15cc4c5`.

~~~text
CELL_LEVEL_EXCLUDED_NO_WINDOW_GENERATED=true
DAY_LEVEL_EXCLUDED_IN_WINDOW=REJECT_WINDOW
EXCLUDED_HOLE_PUNCHING_FOR_PEAK_FORBIDDEN=true
AMENDMENT_SECTION_5_3_UNCHANGED=true
~~~

### 1.5 Step 5 — C0 §5 pending snapshot preserved (expected)

Authority: `docs/v0-3/s3/s3-pit-backtest-execution-contract.md` §5 at blob
`998c47dcbf1d54b161561309c3edccb34426dd9a`.

~~~text
SECTION_5_HEADING=Evaluation window anchor (S3-A1 pending)
S3_A1_EVALUATION_WINDOW_ANCHOR_STATUS=PENDING_NOT_MERGED
S3_A1_PENDING_WINDOW_ANCHOR=cutoff+1 … cutoff+H
S3_C0_MUST_NOT_INVENT_ALTERNATE_WINDOW_ANCHOR=true
C0_SECTION_5_FREEZE_LINES_UNREWRITTEN=true
PENDING_NOT_MERGED_IS_EXPECTED_HISTORICAL_SNAPSHOT=true
PENDING_NOT_MERGED_NOT_VERIFICATION_FAILED=true
~~~

Even though A1 live contract+claim are authorized in development-plan, C0 §5
remains the freeze-era pending reference. R1 does not rewrite those lines.

### 1.6 Step 6 — Live §4.4 contract and claim authorized

Authority: `docs/v0-3/development-plan.md` §4.4 at blob
`1a804783e71bb642890467a8526a678a79f8319c`.

~~~text
S3_A1_WINDOW_ANCHOR_CONTRACT_AUTHORIZED=true
S3_A1_WINDOW_ANCHOR_CLAIM_AUTHORIZED=true
LIVE_CONTRACT_AND_CLAIM_AUTHORIZED_CONFIRMED=true
~~~

### 1.7 Step 7 — No contradictory C0 live window definition

C0 §5 rules at lines 296–304 describe the same anchor as amendment §5.1:
inclusive calendar window from the day after `FORECAST_CUTOFF_AT` through
`FORECAST_CUTOFF_AT + H` calendar days. No alternate live anchor contradicting
`cutoff+1 … cutoff+H` was found outside the freeze pending snapshot.

~~~text
C0_LIVE_WINDOW_CONSISTENT_WITH_A1_FREEZE=true
NO_ALTERNATE_LIVE_WINDOW_ANCHOR_DETECTED=true
~~~

### 1.8 Step 8 — Disposition

~~~text
CURRENT_S3_A1_WINDOW_ANCHOR_CLAIM_STATUS=VERIFIED_FREEZE_STILL_BOUND
AMENDMENT_DRIFT_DETECTED=false
C0_CONTRADICTION_DETECTED=false
CHECKLIST_COMPLETE=true
~~~

All eight steps passed. Amendment §5.1/§5.3 remain byte-identical to freeze
bindings. C0 §5 `PENDING_NOT_MERGED` is recorded as expected historical state,
not failure. Disposition is `VERIFIED_FREEZE_STILL_BOUND`, not lingering
`NOT_VERIFIED`.

## 2. Live registry update

Only `CURRENT_S3_A1_WINDOW_ANCHOR_CLAIM_STATUS` updated in
`docs/v0-3/development-plan.md` §4.4 live state block:
`NOT_VERIFIED` → `VERIFIED_FREEZE_STILL_BOUND`. `S3_A1_WINDOW_ANCHOR_CONTRACT_AUTHORIZED`
and `S3_A1_WINDOW_ANCHOR_CLAIM_AUTHORIZED` remain `true`.

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block and R1 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §96 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live paragraph
- `docs/v0-3/s3/s3-pit-backtest-execution-contract.md` §18 pointer

Historical live-authority (#387) and grant (#388) pointer snapshots are not
refreshed.

## 3. Honest boundary

~~~text
CHECKLIST_EXECUTED_TRUE_DOES_NOT_MEAN_WINDOW_EXECUTED=true
VERIFIED_FREEZE_STILL_BOUND_NOT_COMPLETENESS_VERIFIED=true
VERIFIED_FREEZE_STILL_BOUND_NOT_C0_EXECUTION_AUTHORIZED=true
VERIFIED_FREEZE_STILL_BOUND_NOT_BACKTEST=true
C0_PENDING_NOT_MERGED_REMAINS_HISTORICAL_SNAPSHOT=true
FORBIDDEN_REWRITE_C0_SECTION_5_PENDING_SNAPSHOT=true
FORBIDDEN_CHANGE_MODEL_TO_FORCE_PASS=true
FORBIDDEN_TREAT_THIS_EVIDENCE_AS_BACKTEST_PACKAGE=true
FORBIDDEN_TREAT_THIS_EVIDENCE_AS_VERSIONED_FORECAST_ARTIFACT=true
IMPLEMENTATION_MERGE_DOES_NOT_TOUCH_PYTHON=true
IMPLEMENTATION_MERGE_DOES_NOT_MATERIALIZE_EVALUATION_ROWS=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
~~~

## 4. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=5321c28fee94e61635b9ef22ade6e20e8ccc754cf1a314e5dc57b5a78b710522
~~~

## 5. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
