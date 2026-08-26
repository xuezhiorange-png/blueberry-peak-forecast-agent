# V0.3-S3-A2 Incumbent forecast V0.2 live postgres read R1

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_R1
ARTIFACT_VERSION=s3-a2-incumbent-forecast-v0-2-live-postgres-read-r1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_R1
TASK_CLASS=IMPLEMENTATION
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTATION_ONLY
SLICE=V0.3-S3
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=74ebf85c016605f4723dbae9596259dd4a32338d
BASE_MAIN_TREE_SHA=5bd0e9cf3de79e591eea7844e56912ad560e590f
PARENT_GRANT_PR=361
PARENT_CONTRACT_PR=360
AUTH_EVIDENCE_JSON_SHA256=ba791a1c2292d36b075cc6bc717d788df9d1efd063193ed5d2290783f4bfbeec
LIVE_POSTGRES_READ_CONTRACT_EVIDENCE_JSON_SHA256=3009c0ed24d35dadcb717d31e62767662ed36a6f7b238d36e2360854ab51b58d
BINDABLE_NAME_R1_EVIDENCE_JSON_SHA256=121d677c6645f87162a0108649f73aec1e825f1901148170d55179f9aa17543d
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-live-postgres-read-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-live-postgres-read-r1.json
EVIDENCE_JSON_SHA256=8b56f82fe1dd9871dfb7f02ef3b9f768f265020f7f62b4078fb9b7feb1187763
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
~~~

This workpaper records R1 implementation of the live postgres read path bound only to frozen
table `s3_incumbent_forecast_replay_identity`. Live-read R1 ≠ row population ≠ versioned forecast
artifact ≠ catalog closeout. Empty Alembic table still has **0 rows**. Default obtain() without
injected session remains `()`. Live-read of the empty table still yields `()`. This R1 does **not**
close S3. Jumping to row population or claiming a versioned artifact in repository is forbidden.

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
MATCH_TABLE_COUNT=0
AUDIT_TABLE_COUNT=106
OBJECT_ROW_COUNT_AT_REVIEW=0
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
LATER_LIVE_READ_OF_EMPTY_TABLE_STILL_YIELDS_EMPTY=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

## 1. Implementation scope

### 1.1 Delivered

- `incumbent_forecast_v0_2_live_postgres_read.py` helper with injected session provider
- `_empty_v0_2_postgres_obtain` wired to live read of frozen bindable table only
- Tests: `test_incumbent_forecast_v0_2_live_postgres_read.py`
- Oracle updates: `test_incumbent_forecast_v0_2_postgres_obtain.py`

### 1.2 Not delivered

- row population / INSERT / UPDATE / DELETE
- versioned forecast artifact in repository
- live DSN / connection string invention
- adding frozen name to `MATCH_TABLE_NAMES`
- new Alembic revision
- S3 closeout or `NO_VERSIONED` flip

## 2. Honest boundary

~~~text
LIVE_READ_R1_IS_NOT_ROW_POPULATION=true
LIVE_READ_R1_IS_NOT_VERSIONED_ARTIFACT=true
EMPTY_TABLE_STILL_ZERO_ROWS=true
DEFAULT_OBTAIN_WITHOUT_SESSION_REMAINS_EMPTY=true
LATER_LIVE_READ_OF_EMPTY_TABLE_STILL_YIELDS_EMPTY=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
LIVE_READ_R1_FLIPS_ONLY_LIVE_POSTGRES_READ_IMPLEMENTED=true
~~~

## 3. Status

~~~text
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=true
THIS_DRAFT_IS_NOT_READY=true
AWAITING_COORDINATOR_REVIEW=true
~~~

## 4. CI isolation note (out of slice; not a quality fix)

At commit `f0739a0f2514aca68292a105b766bea1bebe19bf`, GitHub Actions run
[32945730546](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/32945730546)
(`conclusion=failure`) had a single failing job: `postgres-concurrency` (job `98105914506`).

Failed node:

`backend/tests/forecast_quality/test_idempotency.py::test_round_c_v2_natural_manifest_vs_child_race_is_serialized`

Exception: `TimeoutError` (~17s) on `asyncpg INSERT INTO model_baseline_comparison (...)`, cancelled
while locking tuple in `quality_evaluation_run` via PL/pgSQL
`quality_evaluation_child_insert_guard()`.

Isolation facts recorded here (not used as a quality-fix excuse):

- The `postgres-concurrency` pytest shard collects only
  `backend/tests/test_concurrency_isolation_helpers.py`,
  `backend/tests/test_concurrency_isolation_helpers_live.py`,
  `backend/tests/rolling_backtest/test_historical_backtest_concurrency.py`, and
  `backend/tests/forecast_quality/test_idempotency.py` under marker `-m postgres_concurrency`.
  It does **not** collect `backend/tests/s3_daily_rowset/**`.
- This PR (27 files, +1696 / −3) does not modify `forecast_quality/**`, `rolling_backtest/**`,
  Alembic, or `quality_evaluation_*` / `model_baseline_comparison` triggers.
- Live-read tests use `sqlite:///:memory:` with autouse
  `clear_v0_2_live_postgres_session_provider()` teardown; no DSN, no `get_settings`, no
  `create_engine` in production paths for default obtain.
- The failing node builds its own temporary database; it shares no session with S3 empty-table
  live-read.

This slice does **not** fix that Round C v2 natural-lock race flake. A rerun may pass without
changing live-read semantics. If the same nodeid fails again, stop and report — do not expand scope
into `forecast_quality`.
