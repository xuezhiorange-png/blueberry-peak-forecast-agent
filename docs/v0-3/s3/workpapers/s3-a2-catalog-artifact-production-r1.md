# V0.3-S3-A2 evaluation instance catalog artifact production R1

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_PRODUCTION_R1
ARTIFACT_VERSION=s3-a2-catalog-artifact-production-r1
TASK_ID=V03_S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_PRODUCTION_R1
TASK_CLASS=IMPLEMENTATION
AUTHORIZATION_SCOPE=S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_PRODUCTION_IMPLEMENTATION_ONLY
SLICE=V0.3-S3
USER_GATE=可以实施
COORDINATOR_AGENT=https://cursor.com/agents/bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=206c0626d60261b1111cac8c1c74189e3cc279f6
BASE_MAIN_TREE_SHA=3745d3d9556643565f392fd02d04b0a0c46b9a35
AUTH_PR=315
AUTH_EVIDENCE_JSON_SHA256=427dbc4534c9537dbe168e0283644952d82606a481ad0142227dcf7693c9fc09
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-catalog-artifact-production-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-catalog-artifact-production-r1.json
EVIDENCE_JSON_SHA256=a776e557c06e7c31787b9824dedc69735f0143b9a221334a72452ea443cb9dbc
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This workpaper records the R1 deterministic in-memory catalog artifact production
service. It produces evaluation instance catalog artifacts only from injected
ports (`IncumbentForecastArtifactPort`, `S2IdentityAlignmentPort`) and hands
output to `EvaluationInstanceCatalogBindingService.validate()`. It does **not**
write a live versioned catalog into the repository, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`.

~~~text
S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_PRODUCTION_AUTHORIZED=true
DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_ARTIFACT_SERVICE_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
PERSISTENCE=IN_MEMORY_SERVICE_ONLY
DEFAULT_CONSTRUCTION=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

## 1. Implementation scope

### 1.1 Delivered

- `backend/app/s3_daily_rowset/catalog_artifact.py` —
  `EvaluationInstanceCatalogArtifactProductionService`
- Ports: `IncumbentForecastArtifactPort`, `S2IdentityAlignmentPort`
- Deterministic catalog content/manifest SHA256 via `compute_catalog_identity_sha256()`
- Reuses `registry.py`, `binding.py`, `exclusion.py` (via binder/registry)
- Tests: `backend/tests/s3_daily_rowset/test_catalog_artifact.py`

### 1.2 Not delivered

- Live bindable catalog in repository
- `EVALUATION_INSTANCE_REGISTRY_AVAILABLE=true`
- Dataset completeness VERIFIED closeout
- Alembic persistence, HTTP endpoints, SOURCE_002 row-level reads
- Backtest or metric execution

## 2. Fail-closed production semantics

Default construction has no versioned incumbent forecast artifact:

~~~text
reason_code=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
catalog=UnboundEvaluationInstanceCatalog
catalog_identity_sha256=None
REGISTRY_SOURCE_STATUS=NOT_MATERIALIZED_OR_NOT_BOUND
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
evaluation_instance_registry_available=false
current_s3_daily_rowset_completeness_verified=false
~~~

Without S2 identity alignment, production fails closed even when a forecast
artifact port is injected. Forbidden catalog sources, harvest-date-as-cutoff
claims, and dataset identity mismatches all fail closed without inventing cells,
cutoffs, or hashes.

Test-injected fixture catalogs may achieve `in_memory_structural_acceptance=true`
through the binder. Classification remains `FIXTURE_ONLY_CATALOG_NOT_BINDABLE`.
Live AVAILABLE and VERIFIED remain false.

## 3. Bound S2 authority (reference only)

~~~text
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
S2_CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
FORBIDDEN_SAMPLE_H7_FIXTURE_AS_CATALOG=true
~~~

## 4. Global state preserved

~~~text
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
REGISTRY_SOURCE_STATUS=NOT_MATERIALIZED_OR_NOT_BOUND
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
~~~

## 5. Status

~~~text
DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_ARTIFACT_SERVICE_IMPLEMENTED=true
THIS_DRAFT_IS_NOT_READY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
