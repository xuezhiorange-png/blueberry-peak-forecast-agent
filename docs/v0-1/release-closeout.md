# Blueberry Peak Forecast Agent V0.1 Release Closeout

## 1. Final verdict

```text
VERSION=0.1.0
V0_1_SCOPE=S1,S2,S3,S4,S5
V0_1_SCOPE_COMPLETE=true
V0_1_RELEASE_TARGET_COMPLETE=true
V0_1_RELEASE_BOUNDARY_SHA=235bde1407bdd0b86f2b31ad75ba1c3b8dc5ba61
V0_1_RELEASE_BRANCH=release/v0.1.0
V0_1_NEW_FEATURE_WORK_ALLOWED=false
```

V0.1 is the completed Core Forecast release. It is not the entire project backlog and it is not extended by Issues #99 or #102 remaining open.

## 2. Frozen release target

The release target is the deterministic full-season Core Forecast chain:

```text
complete-season fixture
→ Task 8 natural-maturity authority
→ Task 9 harvest and mature-inventory authority
→ complete daily effective-marketable curve
→ single-day peak
→ strict rolling seven-day cumulative peak
→ season cumulative quantity
→ persistence, query, integrity reload, and explicit rerun
→ unified CLI
→ PostgreSQL full-season E2E acceptance
```

The target contains exactly five slices. No additional slice is required to call V0.1 complete.

## 3. Accepted slices

| Slice | Scope | PR | Merge SHA | Status |
|---|---|---:|---|---|
| S1 | Physical-quantity contract and complete-season oracle | #108 | `4527d21322208426b70b8d75623b09e0182fbee6` | merged and accepted |
| S2 | Complete daily effective-marketable curve | #109 | `79e5fa37cf54ed039115d6007ba00238281e5953` | merged and accepted |
| S3 | Canonical peak and season metrics | #110 | `7cae51d0da5c3a6e31d33062b5649d548c83ff6c` | merged and accepted |
| S4 | Persistence, query, integrity reload, and explicit rerun | #111 | `07d539a525ba39507c1e4baa0cd69469e8f9a402` | merged and accepted |
| S5 | Unified CLI and full-season PostgreSQL E2E | #112 | `235bde1407bdd0b86f2b31ad75ba1c3b8dc5ba61` | merged and accepted |

The S5 merge SHA is the release boundary because it is the first mainline commit containing all five accepted slices.

## 4. Version identity

The repository already carries the correct application version:

```text
pyproject.toml: version = "0.1.0"
backend/app/core/version.py: APP_VERSION = "0.1.0"
```

No version-code change is required for the V0.1 closeout.

## 5. Canonical acceptance evidence

```text
FIXTURE_ID=v0_1_complete_season_case_01
CALENDAR_DATE_COUNT=90
SCOPE_COUNT=4
QUANTILE_COUNT=3
SERIES_COUNT=12
DAILY_ROW_COUNT=1080
TRANSITION_COUNT=1068

SOURCE_CURVE_HASH=de81bfa3a23efcef0398758e5105199eede9222adb0aff4acda67f3fe9697687
METRICS_HASH=cfba5f2af9236e907527ef72d2d8e0a34b99f2cad29aaac502e6159c1d6d586a
RESULT_HASH=802504d0798f6ce1f46978806a4b986eefe2ff733616b60af7143ff3e641535a
```

The accepted S5 exact-head CI run is `29502932462`, completed successfully on `721eea8abbdcdc8d0b9a4d17935cdf2bd05c66a6` before merge.

The accepted evidence proves:

- strict complete-season fixture validation;
- deterministic P50/P80/P90 daily curves;
- exact Decimal arithmetic and deterministic hashes;
- single-day and seven-calendar-day peak semantics;
- immutable completed-run persistence;
- same-request idempotent reuse;
- explicit changed-input rerun lineage;
- blocked execution with zero writes;
- persisted reload parity;
- PostgreSQL full-season end-to-end execution.

## 6. Scope exclusions

The following are not V0.1 release dependencies:

```text
ISSUE99_IN_V0_1=false
ISSUE102_IN_V0_1=false
Q2A_I1_TO_I8_IN_V0_1=false
Q2B_IN_V0_1=false
Q3_IN_V0_1=false
TASK013_SLICE_C_IN_V0_1=false
MODEL_CHANGE_IN_V0_1=false
```

Specifically excluded:

- user-supplied actual-harvest import and its API/spreadsheet lifecycle;
- atomic source commit beyond the V0.1 Core Forecast pipeline;
- revision winner selection and cutoff-bound aggregation;
- active or evaluation label snapshots;
- historical accuracy scoring and point-in-time backtest runner;
- deterministic operational recommendation expansion;
- model improvement;
- multi-factory routing and allocation optimization;
- frontend, dashboard, and report implementation.

Open issues remain project backlog only. They do not reopen or enlarge V0.1.

## 7. Post-V0.1 work classification

Work merged or designed after the frozen V0.1 target is classified as post-V0.1 and remains unassigned until a separate version decision is made.

```text
POST_V0_1_WORK_VERSION=UNASSIGNED
POST_V0_1_WORK_MAY_CONTINUE_WITHOUT_VERSION_DECISION=false
Q2A_I6_IMPLEMENTATION_AUTHORIZED=false
Q2A_I7_IMPLEMENTATION_AUTHORIZED=false
Q2A_I8_IMPLEMENTATION_AUTHORIZED=false
Q2B_AUTHORIZED=false
Q3_AUTHORIZED=false
```

The earlier Q2A-I6 contract-reset and implementation directions are superseded by this release-scope correction. No Q2A-I6 branch, worktree, migration, implementation commit, push, or PR is authorized by the V0.1 closeout.

## 8. Release-reference rule

The immutable V0.1 release reference must point to:

```text
235bde1407bdd0b86f2b31ad75ba1c3b8dc5ba61
```

It must not point to the later current `main`, because later commits contain post-V0.1 work.

The repository branch `release/v0.1.0` is fixed at this boundary. A future `v0.1.0` Git tag or GitHub Release must use the same commit.

## 9. Governance correction

```text
V0_1_SCOPE_FROZEN=true
V0_1_SCOPE_DRIFT_REJECTED=true
PROJECT_BACKLOG_DOES_NOT_EXTEND_RELEASE_SCOPE=true
OPEN_ISSUE_DOES_NOT_REOPEN_RELEASE=true
ALL_POST_S5_WORK_REQUIRES_NEW_VERSION_ASSIGNMENT=true
NO_STEP_IMPLIES_THE_NEXT=true
```

The correct next decision is a version-planning decision, not automatic continuation of Q2A or TASK-013 work.
