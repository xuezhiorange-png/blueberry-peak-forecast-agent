# V0.3-S3-A2 incumbent forecast artifact adapter R1

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_ARTIFACT_ADAPTER_R1
ARTIFACT_VERSION=s3-a2-incumbent-forecast-artifact-adapter-r1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_ARTIFACT_ADAPTER_R1
TASK_CLASS=IMPLEMENTATION
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_ARTIFACT_ADAPTER_IMPLEMENTATION_ONLY
SLICE=V0.3-S3
USER_GATE=可以实施
COORDINATOR_AGENT=https://cursor.com/agents/bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=cdcc41aedfc05242e74d2d41f1b8abd997138306
BASE_MAIN_TREE_SHA=0fb803f3b781a0c4803e0f4da0bd476f1c610560
AUTH_PR=318
AUTH_EVIDENCE_JSON_SHA256=1928d044d85c9dbff3c71d14551409c9c61404ed84174f20979fbc31ba6fae00
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-adapter-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-adapter-r1.json
EVIDENCE_JSON_SHA256=31bb6d24cf4c398eeea86c18d2dece16b9e0ab6f704e9ab229eac5a363d296a0
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This workpaper records the R1 deterministic in-memory incumbent forecast artifact
live adapter. It implements `IncumbentForecastArtifactPort` for injected
`VersionedIncumbentForecastArtifact` rows and hands accepted forecast-side fields
to existing `EvaluationInstanceCatalogArtifactProductionService.produce()`. It
does **not** write versioned forecast artifacts into the repository, implement S2
identity alignment, flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`.

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
PERSISTENCE=IN_MEMORY_SERVICE_ONLY
DEFAULT_CONSTRUCTION=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

## 1. Implementation scope

### 1.1 Delivered

- `backend/app/s3_daily_rowset/forecast_artifact.py` —
  `IncumbentForecastArtifactAdapter`, `VersionedIncumbentForecastArtifact`
- Default `EvaluationInstanceCatalogArtifactProductionService` forecast port uses
  the live adapter (still fail-closed without injected artifact)
- Reuses `catalog_artifact.py` port interface and production service unchanged
  apart from default factory
- Tests: `backend/tests/s3_daily_rowset/test_forecast_artifact.py`

### 1.2 Not delivered

- Versioned forecast artifacts written into repository
- S2 identity alignment live adapter
- `EVALUATION_INSTANCE_REGISTRY_AVAILABLE=true`
- Dataset completeness VERIFIED closeout
- Alembic persistence, HTTP endpoints, SOURCE_002 row-level reads
- Backtest or metric execution

## 2. Fail-closed adapter semantics

Default construction has no injected versioned forecast artifact:

~~~text
has_versioned_artifact=false
entries=()
catalog_source_kind=NOT_MATERIALIZED_OR_NOT_BOUND
produce()=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
~~~

Injected test fixtures may set `has_versioned_artifact=true`, but default
`EmptyS2IdentityAlignmentPort` keeps catalog `produce()` at
`NO_S2_IDENTITY_ALIGNMENT`. Live AVAILABLE and VERIFIED remain false.

Forbidden forecast artifact identities include H=7 fixture hash `8e74d6be…`, empty
sentinels, harvest-date-as-cutoff claims, and TEST-intersecting cutoffs/windows.

## 3. Bound S2 authority (reference only)

~~~text
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
S2_CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TEST_PARTITION_DATES=2026-03-10..2026-04-16
TIMEZONE=Asia/Shanghai
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
FORBIDDEN_SAMPLE_H7_FIXTURE_AS_FORECAST_ARTIFACT=true
~~~

## 4. Global state preserved

~~~text
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
REGISTRY_SOURCE_STATUS=NOT_MATERIALIZED_OR_NOT_BOUND
TEST_REMAINS_SEALED=true
~~~

## 5. Status

~~~text
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
THIS_DRAFT_IS_NOT_READY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
