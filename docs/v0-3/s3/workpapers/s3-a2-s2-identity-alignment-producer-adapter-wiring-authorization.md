# V0.3-S3-A2 S2 identity alignment producer→adapter wiring implementation authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_AUTHORIZATION
ARTIFACT_VERSION=s3-a2-s2-identity-alignment-producer-adapter-wiring-authorization-v1
TASK_ID=V03_S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_GRANT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=7912c4128ba0665943283b7b22ba6fc102b7cf2f
BASE_MAIN_TREE_SHA=7149f233e79267fb5370fd69bdee8cdf6e1302ce
PARENT_CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-producer-adapter-wiring-contract.md
PARENT_CONTRACT_GIT_BLOB_SHA=4ffe45d030e00029b5053165eec8646be591420a
PARENT_CONTRACT_EVIDENCE_JSON_SHA256=89e4a35e68d70d942df0c795953573828618d62ac3caddc78dba5609608ec36a
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-producer-adapter-wiring-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-producer-adapter-wiring-authorization.json
GRANT_ONLY=true
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_WIRING=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_PRODUCE_FROM_NONE=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_ALIGNMENT_ARTIFACT=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

The user authorized issuance of the S3-A2 **S2 identity alignment producer→adapter
wiring** implementation grant after the wiring contract freeze on main (#345). This
document records what a **later** deterministic wiring R1 may do when the user again
says 「可以实施」. This PR does not implement wiring, modify Python, invent harvest rows
or SQL, write live alignment artifacts, flip `NO_LIVE_S2` / `NO_VERSIONED` /
`AVAILABLE` / `VERIFIED`, or authorize BINDABLE catalog closeout.

This is **producer→adapter wiring** implementation authorization only. Parent wiring
contract §§1–9 remain authoritative and are not reopened.

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=true
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT_AUTHORIZED=true
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=false
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Upstream bindings (reference only)

~~~text
PARENT_CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-producer-adapter-wiring-contract.md
PARENT_CONTRACT_GIT_BLOB_SHA=4ffe45d030e00029b5053165eec8646be591420a
PARENT_CONTRACT_EVIDENCE_JSON_SHA256=89e4a35e68d70d942df0c795953573828618d62ac3caddc78dba5609608ec36a
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
EVIDENCE_PRODUCER_AUTH_EVIDENCE_JSON_SHA256=7a9fb4be04a165cb83cda2c09585b54624401cc9c004c5e48c49496913dce52e
EVIDENCE_PRODUCER_CONTRACT_EVIDENCE_JSON_SHA256=2bdb9a578592dadd8cf9d15a8071d46f9983e7bb973159d0c3b6ec21b5725add
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
CATALOG_ARTIFACT_PY_BLOB=968e841527b696d17364ddae11693fadb49462b8
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
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
ALIGNMENT_PROJECTION_VERSION=v0-3-s3-a2-s2-identity-alignment-projection-v1
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IDENTITY_VERSION=v0-3-s3-a2-accepted-s2-identity-alignment-evidence-identity-v1
~~~

Evidence JSON self-hashes above are binding references, not whole-file
`sha256sum` values. Archived workpaper/evidence bodies are referenced only; not
rewritten by this authorization grant.

## 2. Inherited S2 and parent wiring contract authority (not reopened)

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
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
SECOND_BLOCKER_FORECAST_NON_EMPTY_ALIGNMENT_EMPTY=NO_S2_IDENTITY_ALIGNMENT
DEFAULT_DECLARED_CATALOG_SOURCE_KIND=BOUND_FIXTURE
SOURCE_002_ROW_LEVEL_READ=false
UNIQUE_ALEMBIC_HEAD=a7c3e9f1b2d4
PEP_420_NAMESPACE=true
PRODUCTION_INIT_PY_FORBIDDEN=true
~~~

## 3. What this authorization grants

A later deterministic wiring R1 may, under a separate user 「可以实施」 gate,
implement parent contract §3.2 default producer→adapter wiring and add
`backend/tests/s3_daily_rowset/test_s2_identity_alignment_producer_adapter_wiring.py`.
Default construction must remain fail-closed; empty producer output must not claim
live alignment facts; catalog default first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.

### 3.1 Allowed file changes (future implementation only)

#### 3.1.1 `catalog_artifact.py` (default alignment port only)

~~~text
MODIFY_CATALOG_ARTIFACT_PY_DEFAULT_ALIGNMENT_PORT_ONLY=true
DEFAULT_FACTORY_OR_POST_INIT_WIRING_ALLOWED=true
USE_SERVICE_DATASET_IDENTITY=true
FORBIDDEN_MODIFY_S2_IDENTITY_ALIGNMENT_PY=true
FORBIDDEN_MODIFY_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY=true
FORBIDDEN_MODIFY_BINDING_PY=true
FORBIDDEN_MODIFY_REGISTRY_PY=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
~~~

Future implementation may modify only `catalog_artifact.py`
`_default_s2_identity_alignment_port()` / default construction wiring using lazy
`default_factory` or `__post_init__` with `service.dataset_identity`.

#### 3.1.2 Named wiring path (future R1 only)

~~~text
AcceptedS2IdentityAlignmentEvidenceProducer(
  dataset_identity=<service.dataset_identity>,
  harvest_rows=default()
).produce()
→ S2IdentityAlignmentAdapter(evidence=produced_or_None)
ACTUAL_EVIDENCE_TYPE=VersionedAcceptedS2IdentityAlignmentEvidence|None
CONTRACT_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IS_SHORTHAND_ONLY=true
FORBIDDEN_MODIFY_PRODUCER_PORT_SIGNATURE_TO_MATCH_SHORTHAND=true
FORBIDDEN_MODIFY_ADAPTER_PORT_SIGNATURE_TO_MATCH_SHORTHAND=true
FORBIDDEN_ADD_PARAMETERS_TO_PRODUCE=true
FORBIDDEN_ADD_PARAMETERS_TO_OBTAIN=true
~~~

Parent contract §3.3 uses `AcceptedS2IdentityAlignmentEvidence` as shorthand. The
actual runtime evidence type is `VersionedAcceptedS2IdentityAlignmentEvidence | None`.
Future R1 must not modify producer or adapter signatures to match the shorthand.

#### 3.1.3 New test module

~~~text
NEW_BACKEND_TESTS_S3_DAILY_ROWSET_TEST_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_PY=true
FUTURE_TEST_PATH=backend/tests/s3_daily_rowset/test_s2_identity_alignment_producer_adapter_wiring.py
~~~

Tests must cover fail-closed behavior: explicit `alignment_port` injection wins
(including `BOUND_FIXTURE` path); default `harvest_rows=()` → `produce()`=`None` →
`evidence=None`; forbidden default reads fail-closed. Do not use H7 fixture as live
evidence.

### 3.2 Wiring priority table (parent contract §3.2; unchanged semantics)

| priority | condition | outcome |
|---|---|---|
| 1 | explicit `alignment_port` | injection wins including `BOUND_FIXTURE` test path |
| 2 | default construction | lazy producer→adapter wiring allowed; no new port parameters |
| 3 | default `harvest_rows=()` or `produce()` is `None` | `adapter.evidence=None` → `aligned_identities=()` |
| 4 | forbidden default reads | no SOURCE_002 / repo scan / hand-written farm lists / H7 live evidence |
| 5 | default catalog after wiring | first blocker `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT` |
| 6 | forecast non-empty and alignment empty | `NO_S2_IDENTITY_ALIGNMENT` |
| 7 | `catalog_source_kind` | copied from forecast, not alignment |
| 8 | wiring landed | `NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY` remains `true` |
| 9 | empty alignment result | no versioned alignment facts claim |

### 3.3 Forbidden in future implementation

~~~text
FORBIDDEN_MODIFY_S2_IDENTITY_ALIGNMENT_PY=true
FORBIDDEN_MODIFY_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY=true
FORBIDDEN_MODIFY_BINDING_PY=true
FORBIDDEN_MODIFY_REGISTRY_PY=true
FORBIDDEN_MODIFY_FORECAST_ARTIFACT_PY=true
FORBIDDEN_MODIFY_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY=true
FORBIDDEN_MODIFY_INCUMBENT_FORECAST_REPLAY_SOURCE_PY=true
FORBIDDEN_MODIFY_FORECAST_REPLAY_CONTENT_POSTGRES_OBTAIN_FROZEN_BLOBS=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
FORBIDDEN_TOUCH_TEST_S2_IDENTITY_ALIGNMENT_PY=true
FORBIDDEN_TOUCH_TEST_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY=true
FORBIDDEN_INVENT_SQL_OR_TABLE_NAMES=true
FORBIDDEN_INVENT_HARVEST_ROW_LISTS=true
FORBIDDEN_INVENT_FARM_OR_CELL_LISTS=true
FORBIDDEN_REPOSITORY_SCAN_FOR_SUBSTITUTES=true
FORBIDDEN_RAW_SOURCE_002_PRIMARY_READ=true
FORBIDDEN_H7_FIXTURE_AS_LIVE_EVIDENCE_OR_CONTENT_IDENTITY=true
FORBIDDEN_LIVE_BINDABLE_SUCCESS_ENUM=true
FORBIDDEN_FLIP_NO_LIVE_S2=true
FORBIDDEN_FLIP_NO_VERSIONED=true
FORBIDDEN_FLIP_NO_BINDABLE=true
FORBIDDEN_FLIP_AVAILABLE_OR_VERIFIED=true
FORBIDDEN_UNSEAL_TEST=true
FORBIDDEN_NEW_ALEMBIC=true
FORBIDDEN_PRODUCTION_INIT_PY=true
IMPLEMENTATION_PR_MAY_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_PR_MAY_NOT_FLIP_COMPLETENESS_VERIFIED=true
IMPLEMENTATION_PR_MAY_NOT_WRITE_LIVE_ALIGNMENT_ARTIFACT_TO_REPOSITORY=true
IMPLEMENTATION_PR_MAY_NOT_PRODUCE_BINDABLE_CATALOG=true
~~~

The only implementation-status flip permitted by a future implementation PR is:

~~~text
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=false → true
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
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_PRODUCE_FROM_NONE=true
~~~

## 5. Registry flip manifest

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block
- `docs/v0-3/s3/s3-s2-identity-alignment-producer-adapter-wiring-contract.md` §10 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-postgres-obtain-contract.md` §13 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-fail-closed-wiring-contract.md` §16 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-envelope-contract.md` §19 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md` §22 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md` §25 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` §28 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §37 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §53 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §36 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §41 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §42 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §45 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §30 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

Unchanged live flags retained:

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=false
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
~~~

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_WIRING=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_PRODUCE_FROM_NONE=true
AWAITING_COORDINATOR_REVIEW=true
~~~
