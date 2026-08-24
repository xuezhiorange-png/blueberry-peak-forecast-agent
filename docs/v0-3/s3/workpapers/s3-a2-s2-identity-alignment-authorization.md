# V0.3-S3-A2 S2 identity alignment implementation authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZATION
ARTIFACT_VERSION=s3-a2-s2-identity-alignment-authorization-v1
TASK_ID=V03_S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_GRANT_ONLY
SLICE=V0.3-S3
USER_GATE=可以继续
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=f950f1f7a4ce046f7e10993812d1e6bc9e3238cd
BASE_MAIN_TREE_SHA=0ae09806742dc2d86fa8b45210f49e00ca8910f7
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-authorization.json
EVIDENCE_JSON_SHA256=efb3d9d668f283f00afcb1bc661b6ab6dca10fb48877c00676fefa25e9a32807
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_ALIGNMENT_ADAPTER=true
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_FORECAST_ARTIFACT=true
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_BIND_CATALOG=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

The user authorized issuance of the S3-A2 S2 identity alignment implementation
grant after alignment contract freeze #320. This document records what a **later**
deterministic `S2IdentityAlignmentPort` live adapter may do when the user again
says 「可以实施」. This PR does not implement an adapter, write forecast artifacts,
produce catalogs, bind catalogs, flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`,
flip `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, authorize backtests, or
claim S3-B semantics verified.

Analogous to prior S3-A2 implementation authorization grants: grant only; no
backend code in this PR.

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=false
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Upstream bindings (reference only)

~~~text
PR320_MERGE=f950f1f7a4ce046f7e10993812d1e6bc9e3238cd
ALIGNMENT_CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-contract.md
ALIGNMENT_CONTRACT_GIT_BLOB_SHA=1f72e3449dc13e873fc31d4bfd601c49ac36a4a1
ALIGNMENT_CONTRACT_EVIDENCE_JSON_SHA256=e69478f732675f04e3c981d99676b6f28e6bf7ddee43a7af7174f0a75802212a
CATALOG_ARTIFACT_PY_BLOB=d4212b8c8888b866eb613660d4f645da8e257081
BINDING_PY_BLOB=0a335f682a923bcd73908b58cd70cd49c9ab0117
REGISTRY_PY_BLOB=b5ad9e87dadf9947348d6576cdcb544a58a20b95
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
FORBIDDEN_SAMPLE_H7_FIXTURE_AS_ALIGNMENT_IDENTITY=true
S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
~~~

Evidence JSON self-hashes above are binding references, not whole-file
`sha256sum` values. Archived workpaper/evidence bodies are referenced only; not
rewritten by this authorization grant.

## 2. Inherited S2 and alignment authority (not reopened)

~~~text
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
S2_CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_PARTITION_DATES=2025-08-05..2026-01-30
VALIDATION_PARTITION_DATES=2026-01-31..2026-03-09
TEST_PARTITION_DATES=2026-03-10..2026-04-16
ALIGNMENT_GRAIN=SEASON,FARM,SUBFARM,VARIETY,PARTITION
ALIGNMENT_PROJECTION_VERSION=v0-3-s3-a2-s2-identity-alignment-projection-v1
ALIGNMENT_DEDUP_KEY=season,farm,subfarm,variety,partition
ALIGNMENT_SORT_KEY=partition,season,farm,subfarm,variety
S2_IDENTITY_ALIGNMENT_SOURCE_KIND=SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT
FORBIDDEN_TEST_SOURCE_IDENTITY_IN_ALIGNMENT=true
ALIGNMENT_DOES_NOT_EVALUATE_FORECAST_WINDOWS=true
TEST_WINDOW_FILTER_AUTHORITY=INCUMBENT_FORECAST_ARTIFACT_ADAPTER_AND_DAILY_ROWSET_MATERIALIZER
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 3. What this authorization grants

A later deterministic `S2IdentityAlignmentPort` live adapter may, under a separate
user 「可以实施」 gate, deliver an in-memory service (PEP 420 namespace; no production
`__init__.py`; no Alembic; `IN_MEMORY_SERVICE_ONLY`) that:

### 3.1 Allowed file changes (future implementation only)

~~~text
NEW_BACKEND_APP_S3_DAILY_ROWSET_S2_IDENTITY_ALIGNMENT_PY=true
NEW_BACKEND_TESTS_S3_DAILY_ROWSET_TEST_S2_IDENTITY_ALIGNMENT_PY=true
REGISTRY_PY_MAY_ADD_SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT_ONLY=true
CATALOG_ARTIFACT_PY_MAY_ADD_LAZY_DEFAULT_FACTORY_WIRING_ONLY=true
~~~

Future implementation may add:

- `backend/app/s3_daily_rowset/s2_identity_alignment.py`
- `backend/tests/s3_daily_rowset/test_s2_identity_alignment.py`

Limited modifications:

- `backend/app/s3_daily_rowset/registry.py` — add only
  `SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT` (not `UNBOUND`, not
  `BOUND_FIXTURE`, not forbidden substitution)
- `backend/app/s3_daily_rowset/catalog_artifact.py` — lazy `default_factory`
  wiring to fail-closed adapter only; reject non-empty rows with
  `UNBOUND`/fixture/forbidden source kinds; do not change existing port method
  signatures

### 3.2 Adapter semantics (future implementation only)

Default without injected versioned accepted S2 evidence:

~~~text
alignment_source_kind=UNBOUND
aligned_identities=()
produce()=NO_S2_IDENTITY_ALIGNMENT
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
~~~

The future adapter must:

1. Accept only caller-explicit injected versioned accepted S2 evidence.
2. Not scan the repository or read raw SOURCE_002 directly.
3. Not log sensitive full-row business data.
4. Validate `dataset_id`, `dataset_version`, and
   `materialized_dataset_identity_sha256`.
5. Validate `harvest_business_date` partition membership against TRAIN/VALIDATION.
6. Use months 1–4 only; exclude 普鲜/普青/普冻/废果 and 巴松/巴松加工厂.
7. Reject TEST source identities; do not evaluate forecast windows (that remains
   with forecast adapter / rowset materializer).
8. Output only `season`, `farm`, `subfarm`, `variety`, `partition`.
9. Apply contract projection version, dedup key, sort key deterministically.
10. Fail closed on blank fields, empty evidence, post-exclusion emptiness, H=7
    fixture, or handwritten farm/date/cell lists.
11. Never treat `harvest_business_date` as `forecast_cutoff`.

The only implementation-status flip permitted by a future implementation PR is:

~~~text
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=false → true
~~~

### 3.3 Forbidden in future implementation

~~~text
IMPLEMENTATION_PR_MAY_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_PR_MAY_NOT_FLIP_COMPLETENESS_VERIFIED=true
IMPLEMENTATION_PR_MAY_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
IMPLEMENTATION_PR_MAY_NOT_PRODUCE_BINDABLE_CATALOG=true
FORBIDDEN_INVENT_FARM_LISTS=true
FORBIDDEN_INVENT_CELL_ROWS=true
FORBIDDEN_INVENT_ALIGNMENT_HASHES=true
~~~

## 4. What remains forbidden / not authorized

~~~text
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=NOT_PERFORMED
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
TEST_REMAINS_SEALED=true
CURRENT_V0_3_S3_COMPLETE=false
V0_3_S4_AUTHORIZED=false
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
ALLOWLIST_EXPANSION_AUTHORIZED=false
SOURCE_002_ROW_LEVEL_READ=false
EMIT_NO_COMPLETE_NDAY_WINDOW_FORBIDDEN=true
~~~

## 5. Registry flip manifest

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §11 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §28 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §12 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §16 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §17 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §20 pointer

Unchanged live flags retained:

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
~~~

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_ALIGNMENT_ADAPTER=true
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_CATALOG=true
AWAITING_COORDINATOR_REVIEW=true
~~~
