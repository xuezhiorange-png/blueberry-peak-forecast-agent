# V0.3-S3-A2 evaluation instance registry R1

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_EVALUATION_INSTANCE_REGISTRY_R1
ARTIFACT_VERSION=s3-a2-registry-implementation-r1
TASK_ID=V03_S3_A2_EVALUATION_INSTANCE_REGISTRY_IMPLEMENTATION_R1
TASK_CLASS=IMPLEMENTATION
AUTHORIZATION_SCOPE=S3_A2_EVALUATION_INSTANCE_REGISTRY_IMPLEMENTATION_ONLY
SLICE=V0.3-S3
USER_GATE=可以实施
COORDINATOR_AGENT=https://cursor.com/agents/bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=33a236873851d4b95b4e03c064f8a6185ee1e19f
BASE_MAIN_TREE_SHA=3d1b6e0ca0b3fef0e74a4a23218088b1a9d6f0b2
AUTH_PR=309
AUTH_EVIDENCE_JSON_SHA256=9e8031f4efc06084dd4ee783943b76d47bbd31bd54ed1976853cf2e79e5eda2a
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-registry-implementation-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-registry-implementation-r1.json
EVIDENCE_JSON_SHA256=8fe740675e0dbe0ad3a4a4c85a5786262877d12fd2c8e704899bef8ffda2f43e
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This workpaper records the R1 deterministic evaluation instance registry service.
It exposes catalog port interfaces, in-scope cell enumeration at amendment cell
grain, and verification-unit expansion (`IN_SCOPE_CELL × {7,14,21}`). It does
**not** flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, dataset-level completeness
VERIFIED, execute backtests, or claim S3-B semantics verified.

~~~text
S3_A2_EVALUATION_INSTANCE_REGISTRY_IMPLEMENTATION_AUTHORIZED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
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

- `backend/app/s3_daily_rowset/registry.py` — `EvaluationInstanceRegistryService`
- Catalog port + `UnboundEvaluationInstanceCatalog` (default production binding)
- Test-injectable `InMemoryEvaluationInstanceCatalog` (fixture catalogs only)
- Tests: `backend/tests/s3_daily_rowset/test_registry.py`

### 1.2 Not delivered

- Versioned production catalog binding or `EVALUATION_INSTANCE_REGISTRY_AVAILABLE=true`
- Dataset-wide completeness PASS / `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=true`
- `NO_COMPLETE_NDAY_WINDOW` emission
- Backtest or metric execution
- Alembic persistence or public HTTP endpoints

## 2. Fail-closed registry semantics

Default service construction binds an **unbound** catalog:

~~~text
REGISTRY_SOURCE_STATUS=NOT_MATERIALIZED_OR_NOT_BOUND
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
in_scope_cells=empty
verification_units=empty
~~~

Forbidden catalog sources fail closed, including:

- H=7 fixture hash `8e74d6be…` as catalog identity
- S2 harvest grain, V0.2 `S3BindingRow` sparse rows, handwritten farm/cutoff lists
- TEST partition cells and horizon windows intersecting TEST dates
- Forbidden varieties and 巴松 factory cells

Output always sets:

~~~text
evaluation_instance_registry_available=false
dataset_completeness_verified=false
current_s3_daily_rowset_completeness_verified=false
~~~

`COMPLETE_SEASON` windows intersecting TEST (`2026-03-10` .. `2026-04-16`) remain
rejected; they are not dataset completeness PASS.

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
P0_SUSTAINED_PEAK_WINDOW_CONFLICT=UNRESOLVED
~~~

## 5. Status

~~~text
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
THIS_DRAFT_IS_NOT_READY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
