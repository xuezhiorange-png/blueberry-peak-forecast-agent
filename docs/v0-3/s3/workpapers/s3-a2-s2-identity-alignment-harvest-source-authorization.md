# V0.3-S3-A2 S2 identity alignment harvest source implementation authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTATION_AUTHORIZATION
ARTIFACT_VERSION=s3-a2-s2-identity-alignment-harvest-source-authorization-v1
TASK_ID=V03_S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTATION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTATION_GRANT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=eeb607a6e0c911a802103dd600eb9954f1cb5c7e
BASE_MAIN_TREE_SHA=a2a5ea2911d4f8ad32e260ad28a926f9e7085035
PARENT_CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-harvest-source-contract.md
PARENT_CONTRACT_GIT_BLOB_SHA=2372c05e1e37d3c552dab0259a24bd8e9c461c91
PARENT_CONTRACT_EVIDENCE_JSON_SHA256=92da3bc9ffab3cb90c825292e8c53f79b1ce5d6abc2ff0ccbedda8b31ba6cb3a
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-harvest-source-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-harvest-source-authorization.json
GRANT_ONLY=true
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
THIS_PR_IS_NOT_R1=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_HARVEST_SOURCE=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_HARVEST_ROWS_FROM_EMPTY=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_PRODUCE_FROM_NONE=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_ALIGNMENT_ARTIFACT=true
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_BIND_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_CATALOG_SOURCE_KIND_PROVENANCE=true
AUTHORIZATION_MERGE_DOES_NOT_REWIRE_PRODUCER_ADAPTER_WIRING=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

The user authorized issuance of the S3-A2 **S2 identity alignment harvest source**
implementation grant after the harvest source contract freeze on main (#348). This
document records what a **later** deterministic harvest source R1 may do when the
user again says 「可以实施」. This PR does not implement harvest obtain, modify Python,
invent harvest rows or SQL, write live alignment artifacts, flip `NO_LIVE_S2` /
`NO_VERSIONED` / `AVAILABLE` / `VERIFIED`, or authorize BINDABLE catalog closeout.

This is **harvest source** implementation authorization only. Parent harvest source
contract §§1–9 remain authoritative and are not reopened. Do not rewrite alignment
contract §6 (`6a9fde9` audit snapshot; `EmptyS2IdentityAlignmentPort` remains the
historical production default).

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTATION_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=true
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT_AUTHORIZED=true
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED=false
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=NOT_PERFORMED
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Upstream bindings (reference only)

~~~text
PARENT_PR=348
PARENT_HARVEST_CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-harvest-source-contract.md
PARENT_HARVEST_CONTRACT_GIT_BLOB_SHA=2372c05e1e37d3c552dab0259a24bd8e9c461c91
PARENT_HARVEST_CONTRACT_EVIDENCE_JSON_SHA256=92da3bc9ffab3cb90c825292e8c53f79b1ce5d6abc2ff0ccbedda8b31ba6cb3a
PARENT_WIRING_CONTRACT_GIT_BLOB_SHA=71d723a00f722efe04f238276ce4e4cddb193f13
WIRING_CONTRACT_EVIDENCE_JSON_SHA256=89e4a35e68d70d942df0c795953573828618d62ac3caddc78dba5609608ec36a
WIRING_GRANT_EVIDENCE_JSON_SHA256=7a4a758259f3e5a54ef01ac623f822fc3bafb2a04c0031d040e8fb2332506f6f
WIRING_R1_EVIDENCE_JSON_SHA256=1349db0e8ef64f99250ae965b99fbba52d817f682201286852dccaa3df20c579
WIRING_R1_EVIDENCE_GIT_BLOB_SHA=ffcbff7dedf4da263e30e885fb07881f779d711f
PARENT_PRODUCER_CONTRACT_GIT_BLOB_SHA=65c5ea7916ef15d777ff2053015f99e56ea4268a
EVIDENCE_PRODUCER_CONTRACT_EVIDENCE_JSON_SHA256=2bdb9a578592dadd8cf9d15a8071d46f9983e7bb973159d0c3b6ec21b5725add
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
CATALOG_ARTIFACT_PY_BLOB=8196cb7dca33df8708f78789bd2eb9e8243b8354
S2_IDENTITY_ALIGNMENT_PY_BLOB=b899e52dbd8752b30395441389ad93fc98d9dbf7
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY_BLOB=14e5614c9069b7b50d12bf3caa36305245c2cc39
FORECAST_ARTIFACT_PY_BLOB=73e65fbe6774ef555f825efc74c9c8eb5f003575
INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=0cc05fff3deff00d279070aa246f241ff3754e89
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=f11e5c3bb34fb070c89e1b01fb62d81d2eb06218
BINDING_PY_BLOB=0a335f682a923bcd73908b58cd70cd49c9ab0117
REGISTRY_PY_BLOB=ca16d518ab18136059cd08bcf4b247774d750bb5
TEST_CATALOG_ARTIFACT_PY_BLOB=af59a9f1d291ab32eff23684aca477f0e4a852cd
TEST_S2_IDENTITY_ALIGNMENT_PY_BLOB=9c653823ebca79fdb12d61325fdb4b18e17d0cef
TEST_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY_BLOB=c81c3ebfe565095f17cfa8794d115ea9fab0ca73
TEST_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_PY_BLOB=9fdd22ccadd6990fa2522c8b23a287dc4e87f173
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
ALIGNMENT_PROJECTION_VERSION=v0-3-s3-a2-s2-identity-alignment-projection-v1
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IDENTITY_VERSION=v0-3-s3-a2-accepted-s2-identity-alignment-evidence-identity-v1
~~~

Evidence JSON self-hashes above are binding references, not whole-file
`sha256sum` values. Archived workpaper/evidence bodies are referenced only; not
rewritten by this authorization grant.

## 2. Inherited S2 and parent harvest source contract authority (not reopened)

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
DEFAULT_MONTH_SCOPE=1-4
FORBIDDEN_VARIETIES=普鲜,普青,普冻,废果
FORBIDDEN_FACTORY_BASON=true
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
CANONICAL_GRAIN=SEASON×FARM×SUBFARM×VARIETY×HARVEST_BUSINESS_DATE
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
SECOND_BLOCKER_FORECAST_NON_EMPTY_ALIGNMENT_EMPTY=NO_S2_IDENTITY_ALIGNMENT
SOURCE_002_ROW_LEVEL_READ=false
UNIQUE_ALEMBIC_HEAD=a7c3e9f1b2d4
PEP_420_NAMESPACE=true
PRODUCTION_INIT_PY_FORBIDDEN=true
~~~

## 3. What this authorization grants

A later deterministic harvest source R1 may, under a separate user 「可以实施」 gate,
deliver an in-memory harvest source service (PEP 420 namespace; no production
`__init__.py`; no Alembic; `IN_MEMORY_SERVICE_ONLY`) analogous to incumbent forecast
`IncumbentForecastReplaySource` for the landed `AcceptedS2IdentityAlignmentEvidenceProducer`.

### 3.1 Allowed file changes (future implementation only)

~~~text
NEW_BACKEND_APP_S3_DAILY_ROWSET_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_PY=true
NEW_BACKEND_TESTS_S3_DAILY_ROWSET_TEST_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_PY=true
FUTURE_PATH=backend/app/s3_daily_rowset/s2_identity_alignment_harvest_source.py
FUTURE_TEST_PATH=backend/tests/s3_daily_rowset/test_s2_identity_alignment_harvest_source.py
FUTURE_MAY_LIMITED_EDIT_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY_HARVEST_SOURCE_ONLY=true
OPTIONAL_HARVEST_SOURCE_FIELD_LAZY_DEFAULT_FACTORY_ALLOWED=true
CIRCULAR_IMPORT_AVOIDANCE_REQUIRED=true
EXPLICIT_HARVEST_ROWS_WIN_OVER_HARVEST_SOURCE=true
DEFAULT_HARVEST_SOURCE_OBTAIN_EMPTY=true
DEFAULT_OBTAIN_SIGNATURE=obtain(self)->tuple[MaterializableRow,...]
HARVEST_SOURCE_OUTPUT_TYPE=tuple[MaterializableRow,...]
PRODUCER_EVIDENCE_FIELDS=season,farm,subfarm,variety,harvest_business_date
FORBIDDEN_MODIFY_CATALOG_ARTIFACT_PY_WIRING=true
FORBIDDEN_MODIFY_S2_IDENTITY_ALIGNMENT_PY=true
FORBIDDEN_MODIFY_BINDING_PY=true
FORBIDDEN_MODIFY_REGISTRY_PY=true
FORBIDDEN_MODIFY_FORECAST_REPLAY_CONTENT_POSTGRES_OBTAIN_FROZEN_BLOBS=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
FORBIDDEN_TOUCH_TEST_S2_IDENTITY_ALIGNMENT_PY=true
FORBIDDEN_TOUCH_TEST_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY=true
FORBIDDEN_TOUCH_TEST_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_PY=true
BOUND_FIXTURE_TEST_INJECTION_PATH_MUST_REMAIN=true
~~~

Future implementation may add:

- `backend/app/s3_daily_rowset/s2_identity_alignment_harvest_source.py`
- `backend/tests/s3_daily_rowset/test_s2_identity_alignment_harvest_source.py`

Limited optional wiring in `accepted_s2_identity_alignment_evidence.py` only:

- optional `harvest_source` field with lazy `default_factory` (avoid circular import)
- explicit non-empty `harvest_rows` must win over harvest source
- default `harvest_rows=()` or `harvest_source.obtain()`=`()` → `produce()`=`None`
- **must not** change `produce()` port signature
- **must not** change `S2IdentityAlignmentAdapter.evidence` field signature
- **must not** change `catalog_artifact.py` default wiring (`harvest_rows=default()`)
- **must not** change `catalog_source_kind` provenance (copied from forecast only)

#### 3.1.1 Harvest source semantics (future implementation only)

Output row type: `tuple[MaterializableRow, ...]` — the type already accepted by
`AcceptedS2IdentityAlignmentEvidenceProducer`. Producer-projected evidence fields
remain: `season`, `farm`, `subfarm`, `variety`, `harvest_business_date`.

The future harvest source must:

1. Carry no kg/tonnes, daily curves, `model_id`, `forecast_cutoff`, quantiles, or
   factory building area.
2. Default `obtain()`=`()`; empty result must not claim live S2 adapter-in-repository
   or versioned alignment facts.
3. Forbid raw SOURCE_002 primary read, repository scan, handwritten farm/cell/date
   lists, H7 live evidence, and unverified daily rowset as live harvest authority.
4. Exclude TEST partition intersection `2026-03-10..2026-04-16`; post-exclusion
   empty → `()`.
5. Default catalog first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.
6. `catalog_source_kind` copied from forecast, not alignment or harvest source.
7. `HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true`.
8. Forbid H7 fixture
   `8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18` as live
   evidence or content identity.
9. Tests may inject synthetic rows via explicit `harvest_rows`; `BOUND_FIXTURE` path
   must remain.

### 3.2 Obtain priority table (parent contract §3.2; unchanged semantics)

| priority | condition | outcome |
|---|---|---|
| 1 | explicit non-empty `harvest_rows` | injection wins including `BOUND_FIXTURE` test path |
| 2 | default construction | future optional internal `harvest_source`; no new port parameters |
| 3 | default `harvest_rows=()` or `harvest_source.obtain()`=`()` | `produce()`=`None` → `evidence=None` |
| 4 | forbidden default reads | no SOURCE_002 / repo scan / hand-written lists / H7 live / unverified rowset |
| 5 | TEST intersection `2026-03-10..2026-04-16` | exclude; post-exclusion empty → `()` |
| 6 | default catalog after any future obtain | first blocker `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT` |
| 7 | forecast non-empty and alignment empty | `NO_S2_IDENTITY_ALIGNMENT` |
| 8 | `catalog_source_kind` | copied from forecast, not alignment or harvest source |
| 9 | empty harvest / alignment result | no live S2 adapter claim; no versioned alignment facts claim |

### 3.3 Forbidden in future implementation

~~~text
FORBIDDEN_ADD_PARAMETERS_TO_PRODUCE=true
FORBIDDEN_ADD_PARAMETERS_TO_OBTAIN=true
FORBIDDEN_MODIFY_PRODUCER_PRODUCE_PORT_SIGNATURE=true
FORBIDDEN_MODIFY_ADAPTER_EVIDENCE_FIELD_SIGNATURE=true
FORBIDDEN_MODIFY_CATALOG_ARTIFACT_PY=true
FORBIDDEN_MODIFY_S2_IDENTITY_ALIGNMENT_PY=true
FORBIDDEN_MODIFY_BINDING_PY=true
FORBIDDEN_MODIFY_REGISTRY_PY=true
FORBIDDEN_MODIFY_FORECAST_ARTIFACT_PY=true
FORBIDDEN_MODIFY_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY=true
FORBIDDEN_MODIFY_INCUMBENT_FORECAST_REPLAY_SOURCE_PY=true
FORBIDDEN_MODIFY_FORECAST_REPLAY_CONTENT_POSTGRES_OBTAIN_FROZEN_BLOBS=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
FORBIDDEN_TOUCH_TEST_S2_IDENTITY_ALIGNMENT_PY=true
FORBIDDEN_TOUCH_TEST_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY=true
FORBIDDEN_TOUCH_TEST_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_PY=true
FORBIDDEN_INVENT_SQL_OR_TABLE_NAMES=true
FORBIDDEN_INVENT_CONNECTION_STRINGS=true
FORBIDDEN_INVENT_DSN_OR_DATABASE_NAMES=true
FORBIDDEN_INVENT_HARVEST_ROW_LISTS=true
FORBIDDEN_INVENT_FARM_OR_CELL_LISTS=true
FORBIDDEN_INVENT_DATE_LISTS=true
FORBIDDEN_INVENT_CUTOFF_LISTS=true
FORBIDDEN_INVENT_IDENTITY_HASHES=true
FORBIDDEN_INVENT_DISTINCT_ROW_COUNTS=true
FORBIDDEN_INVENT_TONNES_OR_KG=true
FORBIDDEN_REPOSITORY_SCAN_FOR_SUBSTITUTES=true
FORBIDDEN_RAW_SOURCE_002_PRIMARY_READ=true
FORBIDDEN_UNVERIFIED_DAILY_ROWSET_AS_LIVE_HARVEST_AUTHORITY=true
FORBIDDEN_H7_FIXTURE_AS_LIVE_EVIDENCE_OR_CONTENT_IDENTITY=true
FORBIDDEN_LIVE_BINDABLE_SUCCESS_ENUM=true
FORBIDDEN_FLIP_NO_LIVE_S2=true
FORBIDDEN_FLIP_NO_VERSIONED=true
FORBIDDEN_FLIP_NO_BINDABLE=true
FORBIDDEN_FLIP_AVAILABLE_OR_VERIFIED=true
FORBIDDEN_UNSEAL_TEST=true
FORBIDDEN_NEW_ALEMBIC=true
FORBIDDEN_PRODUCTION_INIT_PY=true
FORBIDDEN_REWRITE_ALIGNMENT_CONTRACT_SECTION_6_AUDIT=true
HARVEST_SOURCE_DOES_NOT_CONSTITUTE_LIVE_S2_ADAPTER_IN_REPOSITORY=true
IMPLEMENTATION_PR_MAY_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_PR_MAY_NOT_FLIP_COMPLETENESS_VERIFIED=true
IMPLEMENTATION_PR_MAY_NOT_WRITE_LIVE_ALIGNMENT_ARTIFACT_TO_REPOSITORY=true
IMPLEMENTATION_PR_MAY_NOT_PRODUCE_BINDABLE_CATALOG=true
~~~

The only implementation-status flip permitted by a future implementation PR is:

~~~text
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED=false → true
~~~

That flip must be recorded in `docs/v0-3/development-plan.md` §4.4 live block, not
only in an R1 pointer snapshot.

## 4. What remains forbidden / not authorized

~~~text
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=NOT_PERFORMED
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
TEST_REMAINS_SEALED=true
CURRENT_V0_3_S3_COMPLETE=false
V0_3_S4_AUTHORIZED=false
SOURCE_002_ROW_LEVEL_READ=false
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_HARVEST_ROWS_FROM_EMPTY=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_PRODUCE_FROM_NONE=true
~~~

## 5. Registry flip manifest

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTATION_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block
- `docs/v0-3/s3/s3-s2-identity-alignment-harvest-source-contract.md` §10 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-producer-adapter-wiring-contract.md` §13 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-postgres-obtain-contract.md` §16 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-fail-closed-wiring-contract.md` §19 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-envelope-contract.md` §22 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md` §25 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md` §28 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` §31 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §40 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §56 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §39 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §44 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §45 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §48 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §33 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

Unchanged live flags retained:

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=true
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
~~~

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_HARVEST_SOURCE=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_HARVEST_ROWS_FROM_EMPTY=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_PRODUCE_FROM_NONE=true
AWAITING_COORDINATOR_REVIEW=true
~~~
