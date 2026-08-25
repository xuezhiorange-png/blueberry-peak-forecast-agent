# V0.3-S3-A2 Incumbent forecast live source kind implementation authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTATION_AUTHORIZATION
ARTIFACT_VERSION=s3-a2-incumbent-forecast-live-source-kind-authorization-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTATION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTATION_GRANT_ONLY
SLICE=V0.3-S3
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=c857cce1a80a2771cd93a1664d4f00e88259ba32
BASE_MAIN_TREE_SHA=03430f187f993b23e2931cb70ecbb077cf1d8d94
PARENT_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-live-source-kind-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-live-source-kind-authorization.json
EVIDENCE_JSON_SHA256=759644330a0063560f11e53a74a92b03dbb6221ab6c58f523a74462dc145fa9e
NO_STEP_IMPLIES_THE_NEXT=true
GRANT_ONLY=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_LIVE_SOURCE_KIND=true
AUTHORIZATION_MERGE_DOES_NOT_MODIFY_REGISTRY_PY_ENUM=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
AUTHORIZATION_MERGE_DOES_NOT_WIRE_PRODUCER_OR_ADAPTER=true
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_BIND_CATALOG=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

The user authorized issuance of the S3-A2 **incumbent forecast live source kind**
implementation grant after live source kind contract freeze #333. This document
records what a **later** deterministic live source kind R1 may do when the user
again says 「可以实施」. This PR does not implement code, land `CatalogSourceKind`
enum members, wire producer or adapter defaults, write live forecast artifacts,
produce catalogs, bind catalogs, flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`,
flip `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, authorize backtests, or
claim S3-B semantics verified.

This is **live source kind** implementation authorization only. Parent live source
kind contract §§1–9 remain authoritative and are not reopened. Do not
re-authorize replay source, content producer, or forecast adapter consumer.

~~~text
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_IMPLEMENTATION_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Upstream bindings (reference only)

~~~text
PR333_MERGE=c857cce1a80a2771cd93a1664d4f00e88259ba32
LIVE_SOURCE_KIND_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md
LIVE_SOURCE_KIND_CONTRACT_GIT_BLOB_SHA=a5d98821e53f1a584078ea7f1a461f84fc747302
LIVE_SOURCE_KIND_CONTRACT_EVIDENCE_JSON_SHA256=2d0cce5d0c0f89c136014a2abbd01d67ef0004786c63050115d55a2dc0519ee1
REPLAY_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=59e452eedc6b8db82063d11ccaf7af177447074c7ad68565b31a6d86d5d4b457
REPLAY_SOURCE_R1_EVIDENCE_JSON_SHA256=59a198c38c0c1e8e17a718bb5623943c4035b4b9b582e2216b922d526b508929
CONTENT_PRODUCER_R1_EVIDENCE_JSON_SHA256=d159c010b4f527972e7554789e85808ae48e11941499c6f597f124fd471ff228
FORECAST_ADAPTER_R1_EVIDENCE_JSON_SHA256=31bb6d24cf4c398eeea86c18d2dece16b9e0ab6f704e9ab229eac5a363d296a0
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=070f54311f08a5c7758602fbe105e511fefd8eca
INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=18c1b1c8d66f2e8ae4476f24692f5ebeb85a9a95
FORECAST_ARTIFACT_PY_BLOB=f928c6c9fa94e91e33c37edd8e9ab57c6e138480
CATALOG_ARTIFACT_PY_BLOB=968e841527b696d17364ddae11693fadb49462b8
BINDING_PY_BLOB=0a335f682a923bcd73908b58cd70cd49c9ab0117
REGISTRY_PY_BLOB=d3d4dc77e6340786ddcca128eb02e0c1d898a502
TEST_CATALOG_ARTIFACT_PY_BLOB=af59a9f1d291ab32eff23684aca477f0e4a852cd
TEST_FORECAST_ARTIFACT_PY_BLOB=2ae0036a46f6f0b2898a8fca3589041b9869c196
TEST_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=11e23e247d6f90e8c7528a073b6e90c709f4a5cc
TEST_INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=14a2c27f97fa50a37902558c9819f07cd3d71411
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
CONTENT_IDENTITY_VERSION=v0-3-s3-a2-incumbent-forecast-artifact-content-identity-v1
~~~

Evidence JSON self-hashes above are binding references, not whole-file
`sha256sum` values. Archived workpaper/evidence bodies are referenced only; not
rewritten by this authorization grant.

## 2. Inherited S2 and live source kind contract authority (not reopened)

~~~text
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_PARTITION_DATES=2025-08-05..2026-01-30
VALIDATION_PARTITION_DATES=2026-01-31..2026-03-09
TEST_PARTITION_DATES=2026-03-10..2026-04-16
TRAIN_ROW_COUNT=16224
VALIDATION_ROW_COUNT=8006
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
LIVE_FORECAST_SOURCE_KIND=V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 3. What this authorization grants

A later deterministic live source kind R1 may, under a separate user
「可以实施」 gate, land the `CatalogSourceKind` enum member named by parent contract
`LIVE_FORECAST_SOURCE_KIND=V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF` and add
tests proving enum membership and impersonation prohibitions. Default construction
must remain fail-closed; catalog default first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.

### 3.1 Allowed file changes (future implementation only)

~~~text
MODIFY_REGISTRY_PY_CATALOG_SOURCE_KIND_ENUM_ONLY=true
NEW_BACKEND_TESTS_S3_DAILY_ROWSET_TEST_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_PY=true
FORBIDDEN_MODIFY_INCUMBENT_FORECAST_ARTIFACT_ADAPTER_PORT_SIGNATURE=true
FORBIDDEN_MODIFY_CONTENT_PRODUCER_PROJECTION_OR_HASH_RECIPE=true
FORBIDDEN_MODIFY_CONTENT_PRODUCER_BOUND_FIXTURE_ENVELOPE_DEFAULT=true
FORBIDDEN_MODIFY_CATALOG_SOURCE_KIND_PROVENANCE=true
FORBIDDEN_MODIFY_CATALOG_ARTIFACT_PY=true
FORBIDDEN_MODIFY_FORECAST_ARTIFACT_PY=true
FORBIDDEN_MODIFY_BINDING_PY=true
FORBIDDEN_MODIFY_INCUMBENT_FORECAST_REPLAY_SOURCE_PY=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
FORBIDDEN_TOUCH_TEST_FORECAST_ARTIFACT_PY=true
FORBIDDEN_TOUCH_TEST_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY=true
FORBIDDEN_TOUCH_TEST_INCUMBENT_FORECAST_REPLAY_SOURCE_PY=true
PREFER_NO_CHANGE_TO_CONTENT_PRODUCER_FORECAST_ADAPTER_CATALOG_BINDING_REPLAY_SOURCE_BLOBS=true
~~~

Future implementation may:

1. Add `V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF` to `CatalogSourceKind` in
   `registry.py` (string value same as member name).
2. Add `backend/tests/s3_daily_rowset/test_incumbent_forecast_live_source_kind.py`
   (or equivalent new test file).

The new enum member must **not** be added to `FORBIDDEN_CATALOG_SOURCE_KINDS` and
must **not** be added to `ALLOWED_ALIGNMENT_SOURCE_KINDS` (it is a forecast kind,
not an alignment kind).

Limited optional change to `incumbent_forecast_artifact_content.py` only when
explicit live envelope marking is required by tests; default must remain
`BOUND_FIXTURE` or `produce()`=`None`. Test fixture envelopes must not use live
kind.

### 3.2 Live source kind semantics (future implementation only)

The future R1 must preserve parent contract §§3–6:

1. **Only** `V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF` may be live forecast
   `catalog_source_kind`.
2. `BOUND_FIXTURE`, `UNBOUND`, and `FORBIDDEN_CATALOG_SOURCE_KINDS` members must
   not impersonate live forecast authority.
3. `SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT` remains alignment kind only;
   `catalog_artifact.produce()` copies `catalog_source_kind` from forecast, not
   alignment.
4. Default fail-closed: `obtain()`=`()`; producer `produce()`=`None`; adapter
   `artifact=None`; catalog default `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.
   Empty results must not carry live kind.
5. Test-injected `BOUND_FIXTURE` paths must remain →
   `FIXTURE_ONLY_CATALOG_NOT_BINDABLE`. Frozen test blobs must stay byte-identical.
6. Live kind is necessary but not sufficient for bindable catalog; no live
   `BINDABLE` success enumeration.
7. Must not wire producer/adapter `default_factory` so repository default gains
   versioned forecast artifact.
8. Must not invent cutoff lists, SQL, table names, hashes, tonnes, farm/cell
   lists, or distinct entry counts.
9. Must not read SOURCE_002 at row level as primary input; must not repository-scan
   for substitutes; must not treat `harvest_business_date` as `forecast_cutoff`.
10. Must not add Alembic; `UNIQUE_ALEMBIC_HEAD=a7c3e9f1b2d4`.
11. Forbid H7 fixture
    `8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18` as live
    evidence or content identity.
12. TEST partition exclusion: `2026-03-10..2026-04-16`; default months 1–4;
    exclude 普鲜/普青/普冻/废果 and 巴松/巴松加工厂.

The only implementation-status flip permitted by a future implementation PR is:

~~~text
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED=false → true
~~~

That flip must be recorded in `docs/v0-3/development-plan.md` §4.4 live block, not
only in an R1 pointer snapshot.

### 3.3 Forbidden in future implementation

~~~text
IMPLEMENTATION_PR_MAY_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_PR_MAY_NOT_FLIP_COMPLETENESS_VERIFIED=true
IMPLEMENTATION_PR_MAY_NOT_WRITE_LIVE_FORECAST_ARTIFACT_TO_REPOSITORY=true
IMPLEMENTATION_PR_MAY_NOT_PRODUCE_BINDABLE_CATALOG=true
IMPLEMENTATION_PR_MAY_NOT_FLIP_NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
IMPLEMENTATION_PR_MAY_NOT_FLIP_NO_BINDABLE_CATALOG_IN_REPOSITORY=true
IMPLEMENTATION_PR_MAY_NOT_USE_ALIGNMENT_KIND_AS_FORECAST_KIND=true
IMPLEMENTATION_PR_MAY_NOT_USE_BOUND_FIXTURE_AS_LIVE_FORECAST_KIND=true
IMPLEMENTATION_PR_MAY_NOT_MODIFY_FROZEN_TEST_BLOBS=true
FORBIDDEN_INVENT_CUTOFF_LISTS=true
FORBIDDEN_INVENT_CONTENT_IDENTITY_SHA256=true
FORBIDDEN_INVENT_CATALOG_IDENTITY=true
FORBIDDEN_NEW_ALEMBIC=true
UNIQUE_ALEMBIC_HEAD=a7c3e9f1b2d4
FORBIDDEN_V0_2_POSTGRES_CONCURRENCY_CANARY_FLAKY_TESTS=true
PEP_420_NAMESPACE=true
PRODUCTION_INIT_PY_FORBIDDEN=true
~~~

## 4. What remains forbidden / not authorized

~~~text
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
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
~~~

## 5. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTATION_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4
- `docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md` §10 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md` §13 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` §16 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §25 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §41 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §24 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §29 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §30 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §33 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §18 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

Unchanged live flags retained:

~~~text
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED=false
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
~~~

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_LIVE_SOURCE_KIND=true
AUTHORIZATION_MERGE_DOES_NOT_MODIFY_REGISTRY_PY_ENUM=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
AWAITING_COORDINATOR_REVIEW=true
~~~
