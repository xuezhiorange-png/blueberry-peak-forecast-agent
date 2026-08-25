# V0.3-S3-A2 Accepted S2 identity alignment evidence implementation authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IMPLEMENTATION_AUTHORIZATION
ARTIFACT_VERSION=s3-a2-accepted-s2-identity-alignment-evidence-authorization-v1
TASK_ID=V03_S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IMPLEMENTATION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IMPLEMENTATION_GRANT_ONLY
SLICE=V0.3-S3
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=944fd9c17904a16ce965dbff13dab5045b71e6ee
BASE_MAIN_TREE_SHA=d19ed5468877cf0aa352d03ec9b842ac9b23f213
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-accepted-s2-identity-alignment-evidence-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-accepted-s2-identity-alignment-evidence-authorization.json
EVIDENCE_JSON_SHA256=7a9fb4be04a165cb83cda2c09585b54624401cc9c004c5e48c49496913dce52e
NO_STEP_IMPLIES_THE_NEXT=true
GRANT_ONLY=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_EVIDENCE_PRODUCER=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_S2_ALIGNMENT_FACTS=true
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_FORECAST_ARTIFACT=true
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_BIND_CATALOG=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

The user authorized issuance of the S3-A2 **accepted S2 identity alignment evidence
producer** implementation grant after producer contract freeze #324. This document
records what a **later** deterministic evidence producer may do when the user again
says 「可以实施」. This PR does not implement a producer, write live S2 identity facts,
produce catalogs, bind catalogs, flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`,
flip `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, authorize backtests, or claim
S3-B semantics verified.

This is **producer** authorization only. The `S2IdentityAlignmentAdapter` consumer
(R1, #323) is already landed on main. Do not re-authorize the adapter consumer.

~~~text
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IMPLEMENTATION_AUTHORIZED=true
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Upstream bindings (reference only)

~~~text
PR324_MERGE=944fd9c17904a16ce965dbff13dab5045b71e6ee
EVIDENCE_PRODUCER_CONTRACT_PATH=docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md
EVIDENCE_PRODUCER_CONTRACT_EVIDENCE_JSON_SHA256=2bdb9a578592dadd8cf9d15a8071d46f9983e7bb973159d0c3b6ec21b5725add
S2_IDENTITY_ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=1d1b213e6a31e899ce777440f1f1dce63be66006520e417775cdb330d335221d
S2_IDENTITY_ALIGNMENT_AUTH_AMENDMENT_R1_EVIDENCE_JSON_SHA256=c4d26633413dcde42b989684c1eb372443f5598c210d6a920dc51e50bc4093a4
S2_IDENTITY_ALIGNMENT_PY_BLOB=b899e52dbd8752b30395441389ad93fc98d9dbf7
CATALOG_ARTIFACT_PY_BLOB=968e841527b696d17364ddae11693fadb49462b8
FORECAST_ARTIFACT_PY_BLOB=f928c6c9fa94e91e33c37edd8e9ab57c6e138480
REGISTRY_PY_BLOB=d3d4dc77e6340786ddcca128eb02e0c1d898a502
TEST_CATALOG_ARTIFACT_PY_BLOB=af59a9f1d291ab32eff23684aca477f0e4a852cd
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=true
~~~

Evidence JSON self-hashes above are binding references, not whole-file
`sha256sum` values. Archived workpaper/evidence bodies are referenced only; not
rewritten by this authorization grant.

## 2. Inherited S2 and producer contract authority (not reopened)

~~~text
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
S2_CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
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
ALIGNMENT_PROJECTION_VERSION=v0-3-s3-a2-s2-identity-alignment-projection-v1
S2_IDENTITY_ALIGNMENT_SOURCE_KIND=SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 3. What this authorization grants

A later deterministic accepted S2 identity alignment evidence producer may, under a
separate user 「可以实施」 gate, deliver an in-memory service (PEP 420 namespace; no
production `__init__.py`; no Alembic; `IN_MEMORY_SERVICE_ONLY`) that constructs
`VersionedAcceptedS2IdentityAlignmentEvidence` for caller injection into the
landed `S2IdentityAlignmentAdapter`.

### 3.1 Allowed file changes (future implementation only)

~~~text
NEW_BACKEND_APP_S3_DAILY_ROWSET_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY=true
NEW_BACKEND_TESTS_S3_DAILY_ROWSET_TEST_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY=true
CATALOG_ARTIFACT_PY_MAY_ADD_PRODUCER_PORT_AND_LAZY_DEFAULT_FACTORY_ONLY=true
FORBIDDEN_MODIFY_S2_IDENTITY_ALIGNMENT_ADAPTER_PORT_SIGNATURE=true
FORBIDDEN_MODIFY_FORBIDDEN_CATALOG_SOURCE_KINDS=true
FORBIDDEN_MODIFY_ALLOWED_ALIGNMENT_SOURCE_KINDS=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
~~~

Future implementation may add:

- `backend/app/s3_daily_rowset/accepted_s2_identity_alignment_evidence.py`
- `backend/tests/s3_daily_rowset/test_accepted_s2_identity_alignment_evidence.py`

Limited optional wiring in `catalog_artifact.py`:

- producer port / lazy `default_factory` only
- default empty evidence → adapter remains `UNBOUND` → `produce()` with forecast
  only remains `NO_S2_IDENTITY_ALIGNMENT`
- **must not** change `produce()` copying `catalog_source_kind` from
  `forecast_source_kind`
- **must not** change `S2IdentityAlignmentAdapter` port signatures
- **must not** modify `FORBIDDEN_CATALOG_SOURCE_KINDS` or
  `ALLOWED_ALIGNMENT_SOURCE_KINDS` (contract already satisfied; no enum changes
  required by this grant)

### 3.2 Producer semantics (future implementation only)

Output envelope: `VersionedAcceptedS2IdentityAlignmentEvidence`

Evidence row: `AcceptedS2IdentityEvidenceRow` with fields
`season`, `farm`, `subfarm`, `variety`, `harvest_business_date` only.

The future producer must:

1. Bind `dataset_id=source-002`, `dataset_version=e5-live-v1`,
   `materialized_dataset_identity_sha256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785`.
2. Use TRAIN `2025-08-05..2026-01-30` and VALIDATION `2026-01-31..2026-03-09`
   only; default months 1–4; exclude 普鲜/普青/普冻/废果 and 巴松/巴松加工厂.
3. Project identity fields from accepted S2 Lane D materialized harvest grain;
   output must not carry kg/tonnes, `source_row_identity`, `cleaned_row_identity`,
   pit hashes, `model_id`, `forecast_cutoff`, or quantiles.
4. Treat `harvest_business_date` as partition/month input only; it is **not**
   `forecast_cutoff`.
5. Compute `content_identity_sha256` deterministically over real evidence rows;
   forbid empty string, `0`*64, and H7 fixture
   `8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18`.
6. Fail closed on dataset identity mismatch; missing projection → empty evidence /
   `None`; do not invent farm/cell/date lists.
7. Post-exclusion emptiness must not be labeled with live alignment source kind.
8. Reject TEST partition identities; TEST window filtering remains with forecast
   adapter / rowset materializer.
9. Not read raw SOURCE_002 as primary input; not scan repository for substitutes.
10. Not log sensitive full-row business data.
11. Default construction must not claim live S2 identity facts exist in the
    repository (`NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY` remains true).

Live alignment source kind for injected evidence consumed by the adapter remains
`SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT` only. `BOUND_FIXTURE` is not
live alignment authority; #322 test-only explicit injection path must remain →
`FIXTURE_ONLY_CATALOG_NOT_BINDABLE`.

The only implementation-status flip permitted by a future implementation PR is:

~~~text
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=false → true
~~~

### 3.3 Forbidden in future implementation

~~~text
IMPLEMENTATION_PR_MAY_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_PR_MAY_NOT_FLIP_COMPLETENESS_VERIFIED=true
IMPLEMENTATION_PR_MAY_NOT_WRITE_LIVE_S2_ALIGNMENT_FACTS=true
IMPLEMENTATION_PR_MAY_NOT_PRODUCE_BINDABLE_CATALOG=true
IMPLEMENTATION_PR_MAY_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
FORBIDDEN_INVENT_FARM_LISTS=true
FORBIDDEN_INVENT_CELL_ROWS=true
FORBIDDEN_INVENT_CONTENT_IDENTITY_SHA256=true
FORBIDDEN_INVENT_DISTINCT_IDENTITY_COUNTS=true
FORBIDDEN_NEW_ALEMBIC=true
UNIQUE_ALEMBIC_HEAD=a7c3e9f1b2d4
FORBIDDEN_V0_2_POSTGRES_CONCURRENCY_CANARY_FLAKY_TESTS=true
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
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IMPLEMENTATION_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §9 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §32 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §15 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §16 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §20 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §21 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §24 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

Unchanged live flags retained:

~~~text
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=true
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
~~~

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_EVIDENCE_PRODUCER=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_S2_ALIGNMENT_FACTS=true
AWAITING_COORDINATOR_REVIEW=true
~~~
