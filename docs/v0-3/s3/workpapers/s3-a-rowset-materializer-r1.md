# V0.3-S3-A daily rowset materializer R1

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A_ROWSET_MATERIALIZER_R1
ARTIFACT_VERSION=s3-a-rowset-materializer-r1
TASK_ID=V03_S3_A_ROWSET_MATERIALIZER_R1
TASK_CLASS=IMPLEMENTATION
AUTHORIZATION_SCOPE=S3_A_ROWSET_MATERIALIZER_IMPLEMENTATION_ONLY
SLICE=V0.3-S3
USER_GATE=可以实施
COORDINATOR_AGENT=https://cursor.com/agents/bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_MAIN_SHA=a824c204a0ff9d944027000fb14ddb5c0a88218e
BASE_MAIN_TREE_SHA=d9c20c0bb9bdac157d4cc1038003da9dff0a3e6b
FEATURE_HEAD_SHA=pending-after-commit
AUTH_EVIDENCE_PR=304
AUTH_EVIDENCE_JSON_SHA256=df66d59383d3bdf76e7db6fdc32b21b2f41237ef3072f8a1ac76205ddc4d6239
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a-rowset-materializer-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a-rowset-materializer-r1.json
EVIDENCE_JSON_SHA256=4eefdfbaee5be91c594d5f0203270ce52a42ec71538659c5484d436a3eb7e65c
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This workpaper records the R1 deterministic daily rowset materializer service.
It materializes evaluation windows from accepted S2 TRAIN/VALIDATION grains and
an incumbent daily-curve port. It does **not** verify completeness, execute
backtests, or change the incumbent model.

~~~text
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=true
S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED=false
S3_BACKTEST_EXECUTION_AUTHORIZED=false
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_V0_3_S3_COMPLETE=false
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
SOURCE_002_ROW_LEVEL_READ=false
PERSISTENCE=IN_MEMORY_SERVICE_ONLY
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

## 1. Implementation scope

### 1.1 Delivered

- Namespace package `backend/app/s3_daily_rowset/` (PEP 420; no package `__init__.py`)
- Modules: `window.py`, `actuals.py`, `exclusion.py`, `forecast_port.py`, `identity.py`, `schemas.py`, `service.py`
- Tests: `backend/tests/s3_daily_rowset/`
- Deterministic rowset identity hash from canonical serialization
- Incumbent daily-curve port with explicit `FakeIncumbentDailyCurveProvider` test double
- FAIL CLOSED on dataset identity mismatch, TEST partition, UNKNOWN/EXCLUDED days, and `FORECAST_UNAVAILABLE`

### 1.2 Not delivered

- Alembic persistence table (R1 in-memory service only)
- Completeness verification (`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED` remains false)
- Backtest or metric execution
- Full TRAIN/VAL incumbent replay for every cutoff
- Sustained peak PASS (3 vs 7 remains UNRESOLVED)
- Public HTTP endpoints

## 2. Bound S2 authority (read-only)

~~~text
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
CANONICAL_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
~~~

## 3. Window and rejection semantics

- `TIMEZONE=Asia/Shanghai`
- Horizon `H ∈ {7,14,21}`: window = `[cutoff+1, cutoff+H]` calendar days inclusive
- `forecast_target_date` mismatch → `TARGET_DATE_CUTOFF_HORIZON_MISMATCH` (no realignment)
- Cell-level EXCLUDED: forbidden varieties, 巴松, non Jan–Apr scope → no window
- Day-level EXCLUDED or UNKNOWN → entire window REJECTED; kg never coerced to 0
- `FORECAST_UNAVAILABLE` → window REJECTED (not 0)
- `COMPLETE_SEASON` = Jan 1 .. Apr 30 of derived SEASON year
- `COMPLETE_SEASON` windows that include TEST partition dates
  (`2026-03-10` .. `2026-04-16`) → entire materialization `REJECTED` with
  `TEST_PARTITION_NOT_ALLOWED`. This is TEST seal enforcement, not completeness
  verification PASS.

## 4. Global state preserved

~~~text
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_S3_DAILY_ROWSET_CONTRACT_STATUS=NOT_AVAILABLE_FROM_CURRENT_S2_BINDING
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
P0_SUSTAINED_PEAK_WINDOW_CONFLICT=UNRESOLVED
SUSTAINED_PEAK_PASS_FORBIDDEN_UNTIL_OWNER_DECISION=true
~~~

Peak/cumulative metrics remain `NOT_COMPUTABLE` until a separately authorized
completeness verification pass.

## 5. Status

~~~text
DETERMINISTIC_DAILY_ROWSET_SERVICE_IMPLEMENTED=true
THIS_DRAFT_IS_NOT_READY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
