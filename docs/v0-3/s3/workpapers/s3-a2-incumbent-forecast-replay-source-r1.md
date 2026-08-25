# V0.3-S3-A2 Incumbent forecast replay source R1

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_R1
ARTIFACT_VERSION=s3-a2-incumbent-forecast-replay-source-r1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_R1
TASK_CLASS=IMPLEMENTATION
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTATION_ONLY
SLICE=V0.3-S3
USER_GATE=可以实施
BASE_REF=origin/main
BASE_MAIN_SHA=dd49238fcef8282ab942a11f48a6909380cce78e
BASE_MAIN_TREE_SHA=99da9e516b800fae923821be5069e1b7a8e3ff10
AUTH_PR=331
AUTH_EVIDENCE_JSON_SHA256=601e06ac1d679d7fb165a481cc01c27dd01fdd68e5a0d9699098c214ba88c890
REPLAY_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=59e452eedc6b8db82063d11ccaf7af177447074c7ad68565b31a6d86d5d4b457
CONTENT_PRODUCER_R1_EVIDENCE_JSON_SHA256=d159c010b4f527972e7554789e85808ae48e11941499c6f597f124fd471ff228
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-source-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-replay-source-r1.json
EVIDENCE_JSON_SHA256=59a198c38c0c1e8e17a718bb5623943c4035b4b9b582e2216b922d526b508929
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This workpaper records the R1 deterministic in-memory incumbent forecast replay
source. It obtains caller-injected replay rows for the landed
`IncumbentForecastArtifactContentProducer`. It does **not** write live forecast
artifacts into the repository, wire producer/adapter defaults, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`.

~~~text
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
PERSISTENCE=IN_MEMORY_SERVICE_ONLY
DEFAULT_CONSTRUCTION=NO_LIVE_V0_2_BINDING
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

## 1. Implementation scope

### 1.1 Delivered

- `backend/app/s3_daily_rowset/incumbent_forecast_replay_source.py` —
  `IncumbentForecastReplaySource`
- Reuses `IncumbentForecastArtifactEntry` and
  `project_incumbent_forecast_artifact_entries` projection rules from the landed
  content producer module
- Tests: `backend/tests/s3_daily_rowset/test_incumbent_forecast_replay_source.py`

### 1.2 Not delivered

- Live V0.2 replay binding or repository reads
- Content producer / forecast adapter default wiring
- `content_identity_sha256` computation (remains content producer responsibility)
- `EVALUATION_INSTANCE_REGISTRY_AVAILABLE=true`
- Alembic persistence, HTTP endpoints, SOURCE_002 row-level reads
- Backtest or metric execution

## 2. Fail-closed replay source semantics

Default construction has no injected replay rows:

~~~text
obtain()=()
content producer default replay_rows=() → produce()=None
catalog default produce()=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
~~~

Test-only synthetic replay injection remains caller-controlled.

## 3. Bound S2 authority (reference only)

~~~text
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TEST_PARTITION_DATES=2026-03-10..2026-04-16
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
CONTENT_IDENTITY_VERSION=v0-3-s3-a2-incumbent-forecast-artifact-content-identity-v1
~~~

## 4. Global state preserved

~~~text
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
TEST_REMAINS_SEALED=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 5. Status

~~~text
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=true
THIS_DRAFT_IS_NOT_READY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
