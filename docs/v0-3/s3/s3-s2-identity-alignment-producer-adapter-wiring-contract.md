# V0.3-S3-A2 S2 Identity Alignment Producer→Adapter Wiring Contract

## Contract identity and phase boundary

~~~text
CONTRACT_ID=V0_3_S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT
CONTRACT_VERSION=v0-3-s3-a2-s2-identity-alignment-producer-adapter-wiring-contract-v1
TASK_ID=V03_S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING
USER_GATE=可以下一步
CONTRACT_ONLY=true
BASE_MAIN_SHA=79fa9bf3ec7ab4c532e55f58aefcfb0f09ef4191
BASE_MAIN_TREE_SHA=15760ff16d1120aa120849ec866758105902779f
BASE_REF=origin/main
PARENT_ALIGNMENT_CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-contract.md
PARENT_EVIDENCE_PRODUCER_CONTRACT_PATH=docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md
PARENT_CATALOG_ARTIFACT_CONTRACT_PATH=docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
REVIEWER_ROLE=COORDINATOR
NO_STEP_IMPLIES_THE_NEXT=true
~~~

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=true
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT_AUTHORIZED=true
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=false
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=NOT_PERFORMED
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
CURRENT_V0_3_S3_COMPLETE=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
FORBIDDEN_INVENT_SQL_OR_TABLE_NAMES=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This document freezes **S2 identity alignment producer→adapter wiring** governance
authority: how default construction must fail-closed wire
`AcceptedS2IdentityAlignmentEvidenceProducer.produce()` into
`S2IdentityAlignmentAdapter.evidence` without reading raw SOURCE_002, without
writing live alignment facts into the repository, and without changing catalog
`catalog_source_kind` provenance.

This is a **producer→adapter wiring** governance contract only. It is **not** an
implementation authorization grant, **not** an R1 implementation package, **not**
V0.2 postgres obtain, **not** forecast obtain→produce→adapter re-wiring, **not**
live BINDABLE catalog closeout, **not** SOURCE_002 row-level primary read, **not**
TEST unseal, and **not** evidence that versioned alignment facts exist in the
repository today.

Contract merge does **not** implement wiring, does **not** change default
`produce()`=`None` / `evidence`=`None` behavior, does **not** invent harvest rows,
SQL, or table names, and does **not** write live alignment artifacts into the
repository.

Parent contracts **not reopened** by this contract:

- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §§1–9 and adapter R1 pointer
  (projection, exclusion, sorting; historical §6 audit snapshot at 6a9fde9 not
  rewritten)
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §§1–9 and
  producer R1 pointer (`produce()` signature, fail-closed producer rules)
- `docs/v0-3/s3/s3-incumbent-forecast-fail-closed-wiring-contract.md` §§1–9 and R1
  (obtain→produce→adapter forecast chain; explicitly excluded alignment wiring)
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-postgres-obtain-contract.md` §§1–9 and
  R1 pointer (postgres obtain; explicitly excluded alignment wiring)

~~~text
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_WIRING=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_PRODUCE_FROM_NONE=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_ALIGNMENT_ARTIFACT=true
CONTRACT_MERGE_DOES_NOT_PRODUCE_CATALOG=true
CONTRACT_MERGE_DOES_NOT_BIND_CATALOG=true
CONTRACT_MERGE_DOES_NOT_CHANGE_CATALOG_SOURCE_KIND_PROVENANCE=true
DEFAULT_CATALOG_FIRST_BLOCKER_REMAINS_NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT=true
WIRING_DOES_NOT_CONSTITUTE_LIVE_S2_ADAPTER_IN_REPOSITORY=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_BY_THIS_CONTRACT=true
~~~

## 1. Inherited authority (not reopened)

### 1.1 Parent S2 identity alignment contract and landed adapter R1 (reference only)

~~~text
PARENT_ALIGNMENT_CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-contract.md
PARENT_ALIGNMENT_CONTRACT_GIT_BLOB_SHA=7568a608b891d4b98b9aaf7f6857a28eb90bb123
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
S2_IDENTITY_ALIGNMENT_PY_BLOB=b899e52dbd8752b30395441389ad93fc98d9dbf7
ALIGNMENT_PROJECTION_VERSION=v0-3-s3-a2-s2-identity-alignment-projection-v1
~~~

Alignment contract §§1–9 and adapter R1 pointer remain authoritative. Historical
§6 repository audit at 6a9fde9 naming `EmptyS2IdentityAlignmentPort` as production
default is a snapshot and is **not** rewritten. At contract merge audit
(`79fa9bf`), `catalog_artifact.py` `_default_s2_identity_alignment_port()` returns
`S2IdentityAlignmentAdapter()` with default `evidence=None`; `EmptyS2IdentityAlignmentPort`
class still exists but is not the catalog default factory.

### 1.2 Parent accepted evidence producer contract and landed R1 (reference only)

~~~text
PARENT_EVIDENCE_PRODUCER_CONTRACT_PATH=docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md
PARENT_EVIDENCE_PRODUCER_CONTRACT_GIT_BLOB_SHA=22f49d7a78bad1a9332040e9f890daa22ef4b1e3
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
EVIDENCE_PRODUCER_AUTH_EVIDENCE_JSON_SHA256=7a9fb4be04a165cb83cda2c09585b54624401cc9c004c5e48c49496913dce52e
EVIDENCE_PRODUCER_CONTRACT_EVIDENCE_JSON_SHA256=2bdb9a578592dadd8cf9d15a8071d46f9983e7bb973159d0c3b6ec21b5725add
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY_BLOB=14e5614c9069b7b50d12bf3caa36305245c2cc39
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IDENTITY_VERSION=v0-3-s3-a2-accepted-s2-identity-alignment-evidence-identity-v1
~~~

Evidence producer contract §§1–9 and R1 pointer remain authoritative. Default
`harvest_rows=()` → `produce()`=`None`.

### 1.3 Parent catalog artifact and forecast chain (reference only)

~~~text
PARENT_CATALOG_ARTIFACT_CONTRACT_GIT_BLOB_SHA=9caa94290d17ac594c0619fe4f442b7050d3615e
CATALOG_ARTIFACT_PY_BLOB=968e841527b696d17364ddae11693fadb49462b8
FORECAST_ARTIFACT_PY_BLOB=73e65fbe6774ef555f825efc74c9c8eb5f003575
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
DEFAULT_DECLARED_CATALOG_SOURCE_KIND=BOUND_FIXTURE
~~~

`EvaluationInstanceCatalogArtifactProductionService.produce()` checks forecast first:
default catalog first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.
If forecast is non-empty and alignment is empty, second blocker is
`NO_S2_IDENTITY_ALIGNMENT`. `catalog_source_kind` is copied from forecast, not
from alignment. `BOUND_FIXTURE` is not live alignment authority.

### 1.4 S2 binding seal (reference only)

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
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
FORBIDDEN_H7_FIXTURE_AS_LIVE_EVIDENCE_OR_CONTENT_IDENTITY=true
UNIQUE_ALEMBIC_HEAD=a7c3e9f1b2d4
PEP_420_NAMESPACE=true
PRODUCTION_INIT_PY_FORBIDDEN=true
~~~

## 2. Why this contract is the unique remaining gap

After postgres obtain R1 (#344):

1. `S2IdentityAlignmentAdapter` is landed (`s2_identity_alignment.py` blob
   `b899e52dbd8752b30395441389ad93fc98d9dbf7`); default `evidence=None` →
   `aligned_identities=()` → `alignment_source_kind=UNBOUND`.
2. `AcceptedS2IdentityAlignmentEvidenceProducer` is landed
   (`accepted_s2_identity_alignment_evidence.py` blob
   `14e5614c9069b7b50d12bf3caa36305245c2cc39`); default `harvest_rows=()` →
   `produce()`=`None`.
3. `catalog_artifact.py` `_default_s2_identity_alignment_port()` returns
   `S2IdentityAlignmentAdapter()` but does **not** call the producer and does
   **not** inject evidence.
4. `EvaluationInstanceCatalogArtifactProductionService.produce()` checks forecast
   first: default catalog first blocker remains
   `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`; if forecast is non-empty and
   alignment is empty, second blocker is `NO_S2_IDENTITY_ALIGNMENT`.
5. `produce()` copies `catalog_source_kind` from forecast, not from alignment.
   Default declared kind remains `BOUND_FIXTURE` → `FIXTURE_ONLY_CATALOG_NOT_BINDABLE`.
   `BOUND_FIXTURE` is not live alignment authority.
6. Alignment contract §6 audit table still records `EmptyS2IdentityAlignmentPort` as
   production default at 6a9fde9; that historical snapshot is **not** rewritten.
   At `79fa9bf` audit, default is `Adapter(evidence=None)`; `EmptyS2IdentityAlignmentPort`
   exists but is not the catalog default factory.
7. Fail-closed wiring and postgres obtain contracts explicitly excluded alignment
   producer→adapter wiring. Postgres obtain R1 (#344) explicitly did not wire
   alignment.
8. This contract freezes authoritative fail-closed rules for how default construction
   must wire `producer.produce()` into `adapter.evidence`; it does not implement
   wiring, invent harvest rows, read SOURCE_002, or write live facts into the
   repository.

## 3. Producer→adapter wiring freeze

### 3.1 Named wiring path (future R1 only; not implemented by this contract)

~~~text
AcceptedS2IdentityAlignmentEvidenceProducer(
  dataset_identity=<service.dataset_identity>,
  harvest_rows=default()
).produce()
→ S2IdentityAlignmentAdapter(evidence=produced_or_None)
~~~

### 3.2 Wiring priority table (core freeze)

| priority | condition | outcome |
|---|---|---|
| 1 | caller supplies explicit `alignment_port` | explicit port wins; must not swallow test injection including `BOUND_FIXTURE` test path |
| 2 | default construction | may use lazy `default_factory` / `__post_init__` to connect producer to adapter; `produce()` / `obtain()` must not gain parameters |
| 3 | default `harvest_rows=()` or `produce()` is `None` | `adapter.evidence=None` → `aligned_identities=()` |
| 4 | default path | must not read raw SOURCE_002, scan repository substitutes, hand-write farm/cell/date lists, or use H7 fixture as live evidence |
| 5 | after wiring, default catalog | first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT` (postgres obtain default still `()`) |
| 6 | forecast non-empty and alignment empty | `NO_S2_IDENTITY_ALIGNMENT` |
| 7 | `catalog_source_kind` | still copied from forecast, not from alignment; no `FIXTURE_ONLY` / `BINDABLE` success enum change in this slice |
| 8 | wiring landed | does not constitute live S2 adapter-in-repository; `NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY` remains `true` |
| 9 | empty alignment result | must not claim versioned alignment facts exist in repository |

### 3.3 Port signatures and circular-import constraint

~~~text
PRODUCER_SIGNATURE=produce(self)->AcceptedS2IdentityAlignmentEvidence|None
ADAPTER_EVIDENCE_FIELD=evidence: AcceptedS2IdentityAlignmentEvidence|None
FORBIDDEN_MODIFY_PRODUCER_PORT_SIGNATURE=true
FORBIDDEN_MODIFY_ADAPTER_PORT_SIGNATURE=true
FORBIDDEN_ADD_PARAMETERS_TO_PRODUCE=true
FORBIDDEN_ADD_PARAMETERS_TO_OBTAIN=true
CIRCULAR_IMPORT_AVOIDANCE_REQUIRED=true
~~~

### 3.4 Future R1 limited edit surface (named only)

~~~text
FUTURE_MAY_LIMITED_EDIT_CATALOG_ARTIFACT_PY_DEFAULT_ALIGNMENT_PORT_ONLY=true
FUTURE_TEST_PATH=backend/tests/s3_daily_rowset/test_s2_identity_alignment_producer_adapter_wiring.py
PERSISTENCE=IN_MEMORY_SERVICE_ONLY
~~~

Future R1 may modify only `catalog_artifact.py` `_default_s2_identity_alignment_port()`
wiring. Future R1 must **not** modify `s2_identity_alignment.py`,
`accepted_s2_identity_alignment_evidence.py`, `binding.py`, `registry.py`,
`test_catalog_artifact.py`, forecast/replay/content frozen blobs, Alembic,
production `__init__.py`, or perform SOURCE_002 row-level read.

## 4. Explicit non-scope (not authorized by this contract)

This contract merge does **not** authorize:

~~~text
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_WIRING=true
CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true
CONTRACT_MERGE_DOES_NOT_EXECUTE_R1=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_LIVE_S2=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_BINDABLE=true
CONTRACT_MERGE_DOES_NOT_FLIP_AVAILABLE_OR_VERIFIED=true
CONTRACT_MERGE_DOES_NOT_CHANGE_CATALOG_SOURCE_KIND_PROVENANCE=true
CONTRACT_MERGE_DOES_NOT_LIVE_BINDABLE_SUCCESS_ENUM=true
CONTRACT_MERGE_DOES_NOT_UNSEAL_TEST=true
CONTRACT_MERGE_DOES_NOT_SOURCE_002_ROW_LEVEL_READ=true
CONTRACT_MERGE_DOES_NOT_REWRITE_ALIGNMENT_CONTRACT_SECTION_6_AUDIT=true
CONTRACT_MERGE_DOES_NOT_REWIRE_FORECAST_OBTAIN_PRODUCE_ADAPTER=true
FORBIDDEN_NEW_ALEMBIC=true
FORBIDDEN_PRODUCTION_INIT_PY=true
~~~

## 5. Frozen Python blob audit (byte-identical at contract merge)

~~~text
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
TEST_FORECAST_ARTIFACT_PY_BLOB=2ae0036a46f6f0b2898a8fca3589041b9869c196
TEST_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=11e23e247d6f90e8c7528a073b6e90c709f4a5cc
TEST_INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=14a2c27f97fa50a37902558c9819f07cd3d71411
TEST_INCUMBENT_FORECAST_LIVE_ENVELOPE_PY_BLOB=cf34f76c734388129b7dbf8d4f585bde584fceac
TEST_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_PY_BLOB=10ac671d603b842ece5cb3ae449b1580715ed2b0
TEST_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_PY_BLOB=97b072ca484ce50be6796b88c28b8999d9bde353
TEST_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_PY_BLOB=8db60cba335dd87ac72f7b86469168e15b7efe97
BOUND_FIXTURE_TEST_INJECTION_PATH_MUST_REMAIN=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
FROZEN_PYTHON_BLOBS_NOT_MUTATED_BY_THIS_CONTRACT=true
~~~

## 6. Forbidden inputs and substitutions

~~~text
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
SOURCE_002_ROW_LEVEL_READ=false
FORBIDDEN_H7_FIXTURE_AS_LIVE_EVIDENCE_OR_CONTENT_IDENTITY=true
DEFAULT_MONTH_SCOPE=1-4
FORBIDDEN_VARIETIES=普鲜,普青,普冻,废果
FORBIDDEN_FACTORY_BASON=true
~~~

## 7. TEST seal and exclusion policy

~~~text
TEST_REMAINS_SEALED=true
TEST_PARTITION_DATES=2026-03-10..2026-04-16
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
FORBIDDEN_TEST_CUTOFF_OR_HORIZON_INTERSECTION=true
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
~~~

Any alignment evidence or projection intersecting the TEST window must be excluded;
post-exclusion empty → `produce()`=`None` → `adapter.evidence=None`.

## 8. LLM and deterministic service boundary

LLM agents organize explanation and invoke tools. Alignment outcomes, harvest row
lists, identity hashes, distinct row counts, SQL, table names, and tonnes must come
from deterministic service logic and coordinator-reviewed artifacts only. LLM must
not invent tonnes, farms, cells, dates, cutoff lists, identity hashes, SQL, table
names, or distinct row counts.

## 9. Registry flip manifest

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_AUTHORIZED=false → true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=false (companion introduced; not flipped)
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live block and pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-postgres-obtain-contract.md` §12 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-fail-closed-wiring-contract.md` §15 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-envelope-contract.md` §18 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md` §21 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md` §24 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` §27 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §36 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §52 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §35 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §40 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §41 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §44 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §29 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

Unchanged live flags retained:

~~~text
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=true
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
~~~

## 10. S2 identity alignment producer→adapter wiring implementation authorization pointer

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-producer-adapter-wiring-authorization.md
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-producer-adapter-wiring-authorization.json
EVIDENCE_JSON_SHA256=7a4a758259f3e5a54ef01ac623f822fc3bafb2a04c0031d040e8fb2332506f6f
PARENT_CONTRACT_EVIDENCE_JSON_SHA256=89e4a35e68d70d942df0c795953573828618d62ac3caddc78dba5609608ec36a
PARENT_CONTRACT_GIT_BLOB_SHA=4ffe45d030e00029b5053165eec8646be591420a
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=true
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_WIRING=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_PRODUCE_FROM_NONE=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_ALIGNMENT_ARTIFACT=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
~~~

Live `S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_AUTHORIZED` authority
follows `docs/v0-3/development-plan.md` §4.4 live state block; this pointer does
not rewrite producer→adapter wiring contract freeze rules in §§1–9.

## 11. S2 identity alignment producer→adapter wiring R1 pointer

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-producer-adapter-wiring-r1.md
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-producer-adapter-wiring-r1.json
EVIDENCE_JSON_SHA256=1349db0e8ef64f99250ae965b99fbba52d817f682201286852dccaa3df20c579
WIRING_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=7a4a758259f3e5a54ef01ac623f822fc3bafb2a04c0031d040e8fb2332506f6f
WIRING_CONTRACT_EVIDENCE_JSON_SHA256=89e4a35e68d70d942df0c795953573828618d62ac3caddc78dba5609608ec36a
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=true
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_AUTHORIZED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_NO_LIVE_S2=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
IMPLEMENTATION_MERGE_DOES_NOT_SOURCE_002_ROW_LEVEL_READ=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
~~~

Live `DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED` authority
follows `docs/v0-3/development-plan.md` §4.4 live state block; this pointer does
not rewrite producer→adapter wiring contract freeze rules in §§1–9. R1 wires default producer→adapter construction;
default `harvest_rows=()` still yields `evidence=None`; `NO_LIVE_S2` remains `true`.

## 12. S2 identity alignment harvest source contract pointer

~~~text
CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-harvest-source-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-harvest-source-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-harvest-source-contract.json
EVIDENCE_JSON_SHA256=92da3bc9ffab3cb90c825292e8c53f79b1ce5d6abc2ff0ccbedda8b31ba6cb3a
PARENT_WIRING_CONTRACT_GIT_BLOB_SHA=71d723a00f722efe04f238276ce4e4cddb193f13
WIRING_CONTRACT_EVIDENCE_JSON_SHA256=89e4a35e68d70d942df0c795953573828618d62ac3caddc78dba5609608ec36a
WIRING_R1_EVIDENCE_JSON_SHA256=1349db0e8ef64f99250ae965b99fbba52d817f682201286852dccaa3df20c579
PARENT_PRODUCER_CONTRACT_GIT_BLOB_SHA=65c5ea7916ef15d777ff2053015f99e56ea4268a
EVIDENCE_PRODUCER_CONTRACT_EVIDENCE_JSON_SHA256=2bdb9a578592dadd8cf9d15a8071d46f9983e7bb973159d0c3b6ec21b5725add
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=true
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_HARVEST_SOURCE=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_HARVEST_ROWS_FROM_EMPTY=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
~~~

Live `S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_AUTHORIZED` authority
follows `docs/v0-3/development-plan.md` §4.4 live state block; this pointer does
not rewrite producer→adapter wiring contract freeze rules in §§1–9.

## 13. S2 identity alignment harvest source implementation authorization pointer

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-harvest-source-authorization.md
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-harvest-source-authorization.json
EVIDENCE_JSON_SHA256=bad95719d0f2af0481093251707643ec6aa69fc299770d27e7a52e3703d24c64
PARENT_HARVEST_CONTRACT_GIT_BLOB_SHA=2372c05e1e37d3c552dab0259a24bd8e9c461c91
PARENT_HARVEST_CONTRACT_EVIDENCE_JSON_SHA256=92da3bc9ffab3cb90c825292e8c53f79b1ce5d6abc2ff0ccbedda8b31ba6cb3a
PARENT_WIRING_CONTRACT_GIT_BLOB_SHA=71d723a00f722efe04f238276ce4e4cddb193f13
WIRING_CONTRACT_EVIDENCE_JSON_SHA256=89e4a35e68d70d942df0c795953573828618d62ac3caddc78dba5609608ec36a
WIRING_GRANT_EVIDENCE_JSON_SHA256=7a4a758259f3e5a54ef01ac623f822fc3bafb2a04c0031d040e8fb2332506f6f
WIRING_R1_EVIDENCE_JSON_SHA256=1349db0e8ef64f99250ae965b99fbba52d817f682201286852dccaa3df20c579
PARENT_PRODUCER_CONTRACT_GIT_BLOB_SHA=65c5ea7916ef15d777ff2053015f99e56ea4268a
EVIDENCE_PRODUCER_CONTRACT_EVIDENCE_JSON_SHA256=2bdb9a578592dadd8cf9d15a8071d46f9983e7bb973159d0c3b6ec21b5725add
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTATION_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=true
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_HARVEST_SOURCE=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_HARVEST_ROWS_FROM_EMPTY=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_PRODUCE_FROM_NONE=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_ALIGNMENT_ARTIFACT=true
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_BIND_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_CATALOG_SOURCE_KIND_PROVENANCE=true
AUTHORIZATION_MERGE_DOES_NOT_REWIRE_PRODUCER_ADAPTER_WIRING=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
~~~

Live `S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTATION_AUTHORIZED` authority
follows `docs/v0-3/development-plan.md` §4.4 live state block; this pointer does
not rewrite harvest source contract freeze rules in §§1–9. This grant records what a
later deterministic harvest source R1 may do when the user again says 「可以实施」;
it does not implement obtain, invent harvest rows or SQL, or flip `NO_LIVE_S2` /
`NO_VERSIONED` / `AVAILABLE` / `VERIFIED`. `DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED` remains `false` until a separate implementation R1.
## 14. S2 identity alignment harvest source R1 pointer

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-harvest-source-r1.md
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-harvest-source-r1.json
EVIDENCE_JSON_SHA256=bef3cedecf7498064f9929e7c40b863ed8ad028d0cf0e9f30e7b547bc7af408e
HARVEST_SOURCE_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=bad95719d0f2af0481093251707643ec6aa69fc299770d27e7a52e3703d24c64
HARVEST_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=92da3bc9ffab3cb90c825292e8c53f79b1ce5d6abc2ff0ccbedda8b31ba6cb3a
WIRING_R1_EVIDENCE_JSON_SHA256=1349db0e8ef64f99250ae965b99fbba52d817f682201286852dccaa3df20c579
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED=true
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTATION_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_AUTHORIZED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_NO_LIVE_S2=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
IMPLEMENTATION_MERGE_DOES_NOT_SOURCE_002_ROW_LEVEL_READ=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
~~~~~~~~~

Live `DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED` authority
follows `docs/v0-3/development-plan.md` §4.4 live state block; this pointer does
not rewrite harvest source contract freeze rules in §§1–9. R1 adds in-memory
`S2IdentityAlignmentHarvestSource.obtain()` and producer `harvest_source` fallback;
default `harvest_rows=()` and default `obtain()=()` still yield `produce()=None`.
`NO_LIVE_S2` remains `true`. Historical grant/contract pointer snapshots may remain `false`.
