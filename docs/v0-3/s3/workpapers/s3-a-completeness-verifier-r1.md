# V0.3-S3-A completeness verifier R1

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A_COMPLETENESS_VERIFIER_R1
ARTIFACT_VERSION=s3-a-completeness-verifier-r1
TASK_ID=V03_S3_A_COMPLETENESS_VERIFIER_R1
TASK_CLASS=IMPLEMENTATION
AUTHORIZATION_SCOPE=S3_A_COMPLETENESS_VERIFICATION_IMPLEMENTATION_ONLY
SLICE=V0.3-S3
USER_GATE=可以实施
COORDINATOR_AGENT=https://cursor.com/agents/bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=a4d94f345ea8f4ae9296013a16c1e4277dec6c5f
BASE_MAIN_TREE_SHA=6a0c8daf8334b49e453cc6b72f8f0c529253b2ac
FEATURE_HEAD_SHA=16ebbfb9c8e8f0e8c8e8f0e8c8e8f0e8c8e8f0e8
AUTH_PR=306
AUTH_EVIDENCE_JSON_SHA256=783bfac0259393f052996de7f8cb43c74512d7062d2725083c9dcade0253ffdc
MATERIALIZER_PR=305
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a-completeness-verifier-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a-completeness-verifier-r1.json
EVIDENCE_JSON_SHA256=45a6a2aeb33ce102f47ebe2b09a6d191fb7009355471d927252bb45b7459251d
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This workpaper records the R1 deterministic completeness verifier service. It
evaluates amendment §8.1 five predicates on **single** materialized windows
produced by `DailyRowsetMaterializerService`. It does **not** flip dataset-level
completeness, execute backtests, or claim evaluation-instance registry coverage.

~~~text
S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED=true
DETERMINISTIC_COMPLETENESS_VERIFICATION_SERVICE_IMPLEMENTED=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_BACKTEST_EXECUTION_AUTHORIZED=false
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
PERSISTENCE=IN_MEMORY_SERVICE_ONLY
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

## 1. Implementation scope

### 1.1 Delivered

- `backend/app/s3_daily_rowset/completeness.py` — `CompletenessVerifier`
- Predicate IDs bound to amendment §8.1:
  1. `FULL_CALENDAR_DAY_COVERAGE_IN_WINDOW`
  2. `NO_SILENT_MISSING_DAYS`
  3. `NO_ZERO_FILL_FOR_UNKNOWN`
  4. `OBSERVED_KG_TRACEABLE_TO_SOURCE_002_GRAIN`
  5. `FORECAST_DAILY_CURVE_VISIBLE_AT_CUTOFF`
- Tests: `backend/tests/s3_daily_rowset/test_completeness.py`

### 1.2 Not delivered

- Evaluation-instance master registry / dataset-wide completeness PASS
- `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=true` (forbidden in R1)
- `NO_COMPLETE_NDAY_WINDOW` emission
- Backtest or metric execution
- Alembic persistence

## 2. Predicate semantics

Verifier input is a `DailyRowsetResult` from the materializer (in-memory R1).
All five predicates require `MaterializationOutcome.SUCCESS` to PASS.

Single-window all-pass (e.g. H=7 fixture hash `8e74d6be…`) does **not** imply
dataset completeness. Output always sets:

~~~text
dataset_completeness_verified=false
current_s3_daily_rowset_completeness_verified=false
evaluation_instance_registry_available=false
~~~

`COMPLETE_SEASON` windows intersecting TEST partition dates
(`2026-03-10` .. `2026-04-16`) remain materializer-rejected; verifier predicates
FAIL. This is TEST seal enforcement, not completeness PASS.

## 3. Bound S2 authority (reference only)

~~~text
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
S2_CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
~~~

## 4. Global state preserved

~~~text
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
P0_SUSTAINED_PEAK_WINDOW_CONFLICT=UNRESOLVED
~~~

## 5. Status

~~~text
DETERMINISTIC_COMPLETENESS_VERIFICATION_SERVICE_IMPLEMENTED=true
THIS_DRAFT_IS_NOT_READY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
