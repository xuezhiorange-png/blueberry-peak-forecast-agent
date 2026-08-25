# V0.3-S3-A2 Incumbent forecast fail-closed wiring R1

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_R1
ARTIFACT_VERSION=s3-a2-incumbent-forecast-fail-closed-wiring-r1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_R1
TASK_CLASS=IMPLEMENTATION
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTATION_ONLY
SLICE=V0.3-S3
USER_GATE=可以实施
BASE_REF=origin/main
BASE_MAIN_SHA=ddb76d3b13c5663203b1fb73057d4a5eb86568bb
BASE_MAIN_TREE_SHA=6c772f7595251580e89a8f6342cc6584b4c7de27
AUTH_PR=340
AUTH_EVIDENCE_JSON_SHA256=84c4491daefa59f74d875f7b311612efbead4143688b5582c499981fe82210e0
FAIL_CLOSED_WIRING_CONTRACT_EVIDENCE_JSON_SHA256=2ea44667836957fa736828cbd4ae123c5d2144a43918939ab4d494f4cbcaf1ff
LIVE_ENVELOPE_R1_EVIDENCE_JSON_SHA256=164b2396091dc5b2daf790f09c92e9ebf628c6e577a37acdc6e4dc0c88b3e601
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-fail-closed-wiring-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-fail-closed-wiring-r1.json
EVIDENCE_JSON_SHA256=a0f3185fda6c243a7013cb01c724d64cf3d74aff19d17370916483cabda94736
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
~~~

This workpaper records R1 fail-closed obtain→produce→adapter default-chain wiring.
It does **not** implement V0.2 postgres obtain, wire alignment producer→adapter,
write live forecast artifacts into the repository, or flip AVAILABLE/VERIFIED closeout
flags.

~~~text
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

## 1. Implementation scope

### 1.1 Delivered

- `backend/app/s3_daily_rowset/incumbent_forecast_artifact_content.py` —
  optional `replay_source` with lazy default_factory; explicit `replay_rows` win over
  `obtain()`; no top-level replay source import
- `backend/app/s3_daily_rowset/forecast_artifact.py` — optional `producer` with lazy
  default_factory; injected `artifact` wins; otherwise `producer.produce()`
- Default catalog path uses wired `IncumbentForecastArtifactAdapter()` via existing
  `_default_forecast_artifact_port()`
- Tests: `backend/tests/s3_daily_rowset/test_incumbent_forecast_fail_closed_wiring.py`

### 1.2 Not delivered

- V0.2 postgres obtain / SOURCE_002 row-level reads
- alignment producer→adapter wiring
- `EVALUATION_INSTANCE_REGISTRY_AVAILABLE=true`
- Live BINDABLE success enumeration
- Alembic persistence or backtest execution

## 2. Fail-closed default chain (parent contract §3.1)

~~~text
DEFAULT_OBTAIN=()
DEFAULT_PRODUCE=None
DEFAULT_ADAPTER_HAS_NO_VERSIONED_ARTIFACT=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
DEFAULT_DECLARED_CATALOG_SOURCE_KIND=BOUND_FIXTURE
EXPLICIT_REPLAY_ROWS_WIN_OVER_OBTAIN=true
INJECTED_ADAPTER_ARTIFACT_WINS=true
HARVEST_DATE_AS_CUTOFF_PRODUCE_NONE=true
FORBIDDEN_TOP_LEVEL_IMPORT_REPLAY_SOURCE_IN_CONTENT_PRODUCER=true
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
DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED=true
THIS_DRAFT_IS_NOT_READY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
