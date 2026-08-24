# V0.3-S3-A2 S2 identity alignment adapter R1

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_S2_IDENTITY_ALIGNMENT_ADAPTER_R1
ARTIFACT_VERSION=s3-a2-s2-identity-alignment-adapter-r1
TASK_ID=V03_S3_A2_S2_IDENTITY_ALIGNMENT_ADAPTER_R1
TASK_CLASS=IMPLEMENTATION
AUTHORIZATION_SCOPE=S3_A2_S2_IDENTITY_ALIGNMENT_ADAPTER_IMPLEMENTATION_ONLY
SLICE=V0.3-S3
USER_GATE=可以实施
BASE_REF=origin/main
BASE_MAIN_SHA=8cca6706128924cf7616b761329cc6c1395af0d4
BASE_MAIN_TREE_SHA=7e62b2bc5b8f8733376bc886ca7822c662e34de0
AUTH_PR=321
AUTH_AMENDMENT_PR=322
AUTH_EVIDENCE_JSON_SHA256=1d1b213e6a31e899ce777440f1f1dce63be66006520e417775cdb330d335221d
AUTH_AMENDMENT_EVIDENCE_JSON_SHA256=c4d26633413dcde42b989684c1eb372443f5598c210d6a920dc51e50bc4093a4
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-adapter-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-adapter-r1.json
EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This workpaper records the R1 deterministic in-memory `S2IdentityAlignmentPort`
live adapter. It projects caller-injected accepted S2 TRAIN/VALIDATION evidence
into `S2AlignedIdentity` rows for existing
`EvaluationInstanceCatalogArtifactProductionService.produce()`. It does **not**
write live S2 alignment facts into the repository, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, or flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`.

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
PERSISTENCE=IN_MEMORY_SERVICE_ONLY
DEFAULT_CONSTRUCTION=NO_S2_IDENTITY_ALIGNMENT
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

## 1. Implementation scope

### 1.1 Delivered

- `backend/app/s3_daily_rowset/s2_identity_alignment.py` —
  `S2IdentityAlignmentAdapter`, `VersionedAcceptedS2IdentityAlignmentEvidence`
- `CatalogSourceKind.SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT` enum in
  `registry.py` (not forbidden)
- `catalog_artifact.py` default alignment port + #322 alignment source validation
- Tests: `backend/tests/s3_daily_rowset/test_s2_identity_alignment.py`

### 1.2 Not delivered

- Live S2 alignment facts written into repository
- `EVALUATION_INSTANCE_REGISTRY_AVAILABLE=true`
- Dataset completeness VERIFIED closeout
- Alembic persistence, HTTP endpoints, SOURCE_002 row-level reads
- Backtest or metric execution

## 2. Fail-closed adapter semantics

Default construction has no injected alignment evidence:

~~~text
alignment_source_kind=NOT_MATERIALIZED_OR_NOT_BOUND
aligned_identities=()
produce() without forecast=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
produce() with forecast only=NO_S2_IDENTITY_ALIGNMENT
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
~~~

Test-only `BOUND_FIXTURE` alignment injection remains allowed per #322 amendment.
Live AVAILABLE and VERIFIED remain false.

## 3. Bound S2 authority (reference only)

~~~text
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
S2_CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
ALIGNMENT_PROJECTION_VERSION=v0-3-s3-a2-s2-identity-alignment-projection-v1
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
~~~

## 4. Global state preserved

~~~text
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
REGISTRY_SOURCE_STATUS=NOT_MATERIALIZED_OR_NOT_BOUND
TEST_REMAINS_SEALED=true
~~~

## 5. Status

~~~text
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=true
THIS_DRAFT_IS_NOT_READY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
