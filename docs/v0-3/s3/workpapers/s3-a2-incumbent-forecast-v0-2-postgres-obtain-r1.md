# V0.3-S3-A2 Incumbent forecast V0.2 postgres obtain R1

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_R1
ARTIFACT_VERSION=s3-a2-incumbent-forecast-v0-2-postgres-obtain-r1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_R1
TASK_CLASS=IMPLEMENTATION
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTATION_ONLY
SLICE=V0.3-S3
USER_GATE=可以实施
BASE_REF=origin/main
BASE_MAIN_SHA=595a2221c0ec431528146a3e2c8f41c343bb0106
BASE_MAIN_TREE_SHA=27166201bc9e7497362d53342b0e4396bbc5f427
AUTH_PR=343
AUTH_EVIDENCE_JSON_SHA256=6b3655921acd896f0570e0c01fbcb5a85478018c8c968bb84c26a02567253bdd
V0_2_POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-postgres-obtain-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-postgres-obtain-r1.json
EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
~~~

This workpaper records R1 empty-default V0.2 postgres obtain wiring on
`IncumbentForecastReplaySource.obtain()`. Repository contracts contain no frozen
V0.2/S3 SQL or table names; default construction therefore remains fail-closed
with `obtain()`=`()`. It does **not** flip `NO_VERSIONED`, wire alignment
producer→adapter, or close out BINDABLE catalog.

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

## 1. Implementation scope

### 1.1 Delivered

- `backend/app/s3_daily_rowset/incumbent_forecast_replay_source.py` —
  empty-default obtain priority per parent contract §3.2; optional injectable
  zero-argument `v0_2_postgres_obtain` seam defaulting fail-closed to `()`; no
  SQL/table names/DSN/sqlalchemy imports
- Tests: `backend/tests/s3_daily_rowset/test_incumbent_forecast_v0_2_postgres_obtain.py`

### 1.2 Not delivered

- Frozen V0.2/S3 SQL or table names (none in repository contracts)
- Live postgres reading in default construction
- alignment producer→adapter wiring
- `EVALUATION_INSTANCE_REGISTRY_AVAILABLE=true`
- Live BINDABLE success enumeration
- Alembic persistence or backtest execution

## 2. Obtain priority (parent contract §3.2)

~~~text
HARVEST_AS_CUTOFF_OBTAIN_EMPTY=true
EXPLICIT_REPLAY_ROWS_WIN_OVER_POSTGRES=true
EMPTY_REPLAY_ROWS_ATTEMPT_V0_2_POSTGRES_OBTAIN=true
DEFAULT_V0_2_POSTGRES_OBTAIN_FAIL_CLOSED_TO_EMPTY=true
DEFAULT_OBTAIN=()
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
DEFAULT_DECLARED_CATALOG_SOURCE_KIND=BOUND_FIXTURE
FORBIDDEN_INVENT_SQL_OR_TABLE_NAMES=true
CONTENT_IDENTITY_VERSION=v0-3-s3-a2-incumbent-forecast-artifact-content-identity-v1
~~~

## 3. Global state preserved

~~~text
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
TEST_REMAINS_SEALED=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 4. Status

~~~text
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED=true
THIS_DRAFT_IS_NOT_READY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
