# V0.3-S3-A2 evaluation instance catalog binding R1

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_R1
ARTIFACT_VERSION=s3-a2-catalog-binding-implementation-r1
TASK_ID=V03_S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_IMPLEMENTATION_R1
TASK_CLASS=IMPLEMENTATION
AUTHORIZATION_SCOPE=S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_IMPLEMENTATION_ONLY
SLICE=V0.3-S3
USER_GATE=可以实施
COORDINATOR_AGENT=https://cursor.com/agents/bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=9e907032e03a0b8305ce9738b250c919e66b00c8
BASE_MAIN_TREE_SHA=89b31a47f0001a3b95e3f250494a2cd3c177ed88
AUTH_PR=312
AUTH_EVIDENCE_JSON_SHA256=22b8e4bd0c8d530008afd42b3f9213f4c47b4870b5709576ea7993725cf9f379
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-catalog-binding-implementation-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-catalog-binding-implementation-r1.json
EVIDENCE_JSON_SHA256=d86ad33cba6299a1b58a28598d82a90b20b53fb73700e037919698e89ef24ae5
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This workpaper records the R1 deterministic in-memory catalog binding validator.
It structurally checks injected catalog candidates against binding contract §3
requirements using `EvaluationInstanceRegistryService.list_in_scope_cells()`.
It does **not** bind a live repository catalog, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`.

~~~text
S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_BINDING_SERVICE_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
PERSISTENCE=IN_MEMORY_SERVICE_ONLY
DEFAULT_CONSTRUCTION=UNBOUND
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

## 1. Implementation scope

### 1.1 Delivered

- `backend/app/s3_daily_rowset/binding.py` — `EvaluationInstanceCatalogBindingService`
- Reuses `registry.py` ports, forbidden source kinds, and in-scope enumeration
- Tests: `backend/tests/s3_daily_rowset/test_catalog_binding.py`

### 1.2 Not delivered

- Live catalog binding or `EVALUATION_INSTANCE_REGISTRY_AVAILABLE=true`
- Dataset completeness VERIFIED closeout
- Alembic persistence, HTTP endpoints, SOURCE_002 row-level reads
- Backtest or metric execution

## 2. Fail-closed binding semantics

Default construction has no candidate catalog:

~~~text
REGISTRY_SOURCE_STATUS=NOT_MATERIALIZED_OR_NOT_BOUND
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
evaluation_instance_registry_available=false
current_s3_daily_rowset_completeness_verified=false
~~~

Fixture catalogs may achieve `in_memory_structural_acceptance=true` in tests only.
Classification remains `FIXTURE_ONLY_CATALOG_NOT_BINDABLE`. Live AVAILABLE and
VERIFIED remain false.

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
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
~~~

## 5. Status

~~~text
DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_BINDING_SERVICE_IMPLEMENTED=true
THIS_DRAFT_IS_NOT_READY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
