# V0.3-S3-A2 Incumbent forecast artifact content producer R1

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_R1
ARTIFACT_VERSION=s3-a2-incumbent-forecast-artifact-content-producer-r1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_R1
TASK_CLASS=IMPLEMENTATION
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTATION_ONLY
SLICE=V0.3-S3
USER_GATE=可以实施
BASE_REF=origin/main
BASE_MAIN_SHA=6681bdbc5fdfed2c5c896005b059a4c8de040eb7
BASE_MAIN_TREE_SHA=5254a915253cf00408229db6a97f532c315d4d73
AUTH_PR=328
AUTH_EVIDENCE_JSON_SHA256=29a486d5fa04542404c6629509ee65ebdf3931c30cf758db643faf93cfd35a38
CONTENT_CONTRACT_EVIDENCE_JSON_SHA256=6294f2028509f2b1021741ac7aea3f20efdcbe07669b87a1782d18c0a5ca9eae
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-content-producer-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-content-producer-r1.json
EVIDENCE_JSON_SHA256=d159c010b4f527972e7554789e85808ae48e11941499c6f597f124fd471ff228
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This workpaper records the R1 deterministic in-memory incumbent forecast artifact
content producer. It projects caller-injected forecast replay rows into
`VersionedIncumbentForecastArtifact` for injection into
`IncumbentForecastArtifactAdapter`. It does **not** write live forecast artifacts
into the repository, flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`.

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
PERSISTENCE=IN_MEMORY_SERVICE_ONLY
DEFAULT_CONSTRUCTION=NO_REPLAY_ROWS
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

## 1. Implementation scope

### 1.1 Delivered

- `backend/app/s3_daily_rowset/incumbent_forecast_artifact_content.py` —
  `IncumbentForecastArtifactContentProducer`, `compute_content_identity_sha256`
- Reuses `VersionedIncumbentForecastArtifact` / `IncumbentForecastArtifactEntry`
  from existing forecast adapter modules
- Tests: `backend/tests/s3_daily_rowset/test_incumbent_forecast_artifact_content.py`

### 1.2 Not delivered

- Live forecast artifact facts written into repository
- `catalog_artifact.py` default producer port wiring (optional R1 deferral)
- `CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF`
- `EVALUATION_INSTANCE_REGISTRY_AVAILABLE=true`
- Dataset completeness VERIFIED closeout
- Alembic persistence, HTTP endpoints, SOURCE_002 row-level reads
- Backtest or metric execution

## 2. Fail-closed producer semantics

Default construction has no injected replay rows:

~~~text
produce()=None
adapter default artifact=None → NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
produce() with forecast only=NO_S2_IDENTITY_ALIGNMENT
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
~~~

Test-only synthetic replay injection remains caller-controlled; test hashes are
not claimed as live SOURCE_002 / repository content identity.

## 3. Bound S2 authority (reference only)

~~~text
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
CONTENT_IDENTITY_VERSION=v0-3-s3-a2-incumbent-forecast-artifact-content-identity-v1
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
~~~

## 4. Global state preserved

~~~text
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
REGISTRY_SOURCE_STATUS=NOT_MATERIALIZED_OR_NOT_BOUND
TEST_REMAINS_SEALED=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 5. Status

~~~text
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=true
THIS_DRAFT_IS_NOT_READY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
