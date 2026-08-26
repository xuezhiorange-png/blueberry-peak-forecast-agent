# V0.3-S3-A2 S2 Identity Alignment Harvest Source Contract

## Contract identity and phase boundary

~~~text
CONTRACT_ID=V0_3_S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT
CONTRACT_VERSION=v0-3-s3-a2-s2-identity-alignment-harvest-source-contract-v1
TASK_ID=V03_S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE
USER_GATE=可以下一步
CONTRACT_ONLY=true
BASE_MAIN_SHA=3f411cdcc1c56642ca6c9abc2b4476ace83d8c39
BASE_MAIN_TREE_SHA=6cec0ee6157f3fa994e1ce924f03372fac47f669
BASE_REF=origin/main
PARENT_WIRING_CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-producer-adapter-wiring-contract.md
PARENT_PRODUCER_CONTRACT_PATH=docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md
PARENT_ALIGNMENT_CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-contract.md
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
REVIEWER_ROLE=COORDINATOR
NO_STEP_IMPLIES_THE_NEXT=true
~~~

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=true
S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=true
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT_AUTHORIZED=true
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED=false
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_AUTHORIZED=true
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

This document freezes **S2 identity alignment harvest source** governance authority:
when and how a future harvest source may supply `MaterializableRow` tuples to
`AcceptedS2IdentityAlignmentEvidenceProducer` without reading raw SOURCE_002,
without inventing harvest rows, and without flipping live repository closeout flags.

This is a **harvest source** governance contract only. It is **not** an
implementation authorization grant, **not** an R1 implementation package, **not**
producer→adapter re-wiring, **not** forecast replay obtain, **not** live BINDABLE
catalog closeout, **not** SOURCE_002 row-level primary read, **not** TEST unseal,
and **not** evidence that versioned alignment facts exist in the repository today.

Contract merge does **not** implement harvest obtain, does **not** change default
`harvest_rows=()` / `produce()`=`None` / `evidence`=`None`, does **not** invent
harvest rows or SQL, and does **not** write live alignment artifacts into the
repository.

Parent contracts **not reopened** by this contract:

- `docs/v0-3/s3/s3-s2-identity-alignment-producer-adapter-wiring-contract.md` §§1–9
  and R1 pointer (producer→adapter default wiring landed by #347; default
  `harvest_rows=()` unchanged)
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §§1–9 and
  R1 pointer (`produce()` signature, projection grain, fail-closed producer rules)
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §§1–9 (historical §6 audit at
  6a9fde9 not rewritten)

~~~text
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_HARVEST_SOURCE=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_HARVEST_ROWS_FROM_EMPTY=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_PRODUCE_FROM_NONE=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_ALIGNMENT_ARTIFACT=true
CONTRACT_MERGE_DOES_NOT_PRODUCE_CATALOG=true
CONTRACT_MERGE_DOES_NOT_BIND_CATALOG=true
CONTRACT_MERGE_DOES_NOT_CHANGE_CATALOG_SOURCE_KIND_PROVENANCE=true
CONTRACT_MERGE_DOES_NOT_REWIRE_PRODUCER_ADAPTER_WIRING=true
DEFAULT_CATALOG_FIRST_BLOCKER_REMAINS_NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT=true
HARVEST_SOURCE_DOES_NOT_CONSTITUTE_LIVE_S2_ADAPTER_IN_REPOSITORY=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_BY_THIS_CONTRACT=true
~~~

## 1. Inherited authority (not reopened)

### 1.1 Parent producer→adapter wiring contract and landed R1 (#347) (reference only)

~~~text
PARENT_WIRING_CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-producer-adapter-wiring-contract.md
PARENT_WIRING_CONTRACT_GIT_BLOB_SHA=71d723a00f722efe04f238276ce4e4cddb193f13
WIRING_CONTRACT_EVIDENCE_JSON_SHA256=89e4a35e68d70d942df0c795953573828618d62ac3caddc78dba5609608ec36a
WIRING_GRANT_EVIDENCE_JSON_SHA256=7a4a758259f3e5a54ef01ac623f822fc3bafb2a04c0031d040e8fb2332506f6f
WIRING_R1_EVIDENCE_JSON_SHA256=1349db0e8ef64f99250ae965b99fbba52d817f682201286852dccaa3df20c579
WIRING_R1_EVIDENCE_GIT_BLOB_SHA=ffcbff7dedf4da263e30e885fb07881f779d711f
CATALOG_ARTIFACT_PY_BLOB=8196cb7dca33df8708f78789bd2eb9e8243b8354
~~~

Wiring contract §§1–9 and R1 pointer remain authoritative. R1 (#347) wires
`AcceptedS2IdentityAlignmentEvidenceProducer.produce()` into
`S2IdentityAlignmentAdapter.evidence`. Default `harvest_rows=()` still yields
`produce()`=`None` → `evidence=None` → `aligned_identities=()` → `UNBOUND`.
Wiring contract catalog default `harvest_rows=default()` is not reopened.

### 1.2 Parent accepted evidence producer contract and landed R1 (reference only)

~~~text
PARENT_PRODUCER_CONTRACT_PATH=docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md
PARENT_PRODUCER_CONTRACT_GIT_BLOB_SHA=65c5ea7916ef15d777ff2053015f99e56ea4268a
EVIDENCE_PRODUCER_CONTRACT_EVIDENCE_JSON_SHA256=2bdb9a578592dadd8cf9d15a8071d46f9983e7bb973159d0c3b6ec21b5725add
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY_BLOB=14e5614c9069b7b50d12bf3caa36305245c2cc39
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IDENTITY_VERSION=v0-3-s3-a2-accepted-s2-identity-alignment-evidence-identity-v1
HARVEST_ROWS_TYPE=tuple[MaterializableRow,...]
PRODUCER_EVIDENCE_FIELDS=season,farm,subfarm,variety,harvest_business_date
CANONICAL_GRAIN=SEASON×FARM×SUBFARM×VARIETY×HARVEST_BUSINESS_DATE
~~~

Evidence producer contract §§1–9 and R1 pointer remain authoritative. Producer
accepts `harvest_rows: tuple[MaterializableRow, ...]` only; projected evidence
fields remain `season`, `farm`, `subfarm`, `variety`, `harvest_business_date`.

### 1.3 Parent alignment and forecast chain (reference only)

~~~text
PARENT_ALIGNMENT_CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-contract.md
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
S2_IDENTITY_ALIGNMENT_PY_BLOB=b899e52dbd8752b30395441389ad93fc98d9dbf7
ALIGNMENT_PROJECTION_VERSION=v0-3-s3-a2-s2-identity-alignment-projection-v1
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
DEFAULT_DECLARED_CATALOG_SOURCE_KIND=BOUND_FIXTURE
CATALOG_SOURCE_KIND_COPIED_FROM_FORECAST_NOT_ALIGNMENT=true
~~~

Alignment contract §6 audit at 6a9fde9 naming `EmptyS2IdentityAlignmentPort` as
production default is a historical snapshot and is **not** rewritten. Catalog
`catalog_source_kind` is copied from forecast, not from alignment or harvest source.

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

After producer→adapter wiring R1 (#347):

1. Wiring R1 landed `AcceptedS2IdentityAlignmentEvidenceProducer.produce()` into
   `S2IdentityAlignmentAdapter.evidence`.
2. Default remains `harvest_rows=()` → `produce()`=`None` → `evidence=None` →
   `aligned_identities=()` → `UNBOUND`.
3. The producer has only constructor parameter `harvest_rows`; there is no harvest
   source seam analogous to `IncumbentForecastReplaySource.obtain()`.
4. Catalog default wiring still passes `harvest_rows=default()`; it does not read
   SOURCE_002.
5. Without a frozen harvest source contract, a later R1 could invent harvest rows,
   farm/cell/date lists, or treat unverified daily rowset / SOURCE_002 row-level read
   as live harvest authority.
6. This contract freezes fail-closed harvest source authority only; it does not
   implement obtain, invent rows, or flip `NO_LIVE_S2`.

## 3. Harvest source freeze

### 3.1 What harvest source is (and is not)

~~~text
HARVEST_SOURCE_IS_NOT_PRODUCER=true
HARVEST_SOURCE_IS_NOT_ADAPTER=true
HARVEST_SOURCE_IS_NOT_CATALOG=true
HARVEST_SOURCE_IS_NOT_FORECAST_REPLAY=true
HARVEST_SOURCE_IS_NOT_EVALUATION_INSTANCE_CATALOG=true
HARVEST_SOURCE_OUTPUT_TYPE=tuple[MaterializableRow,...]
HARVEST_SOURCE_CARRIES_NO_KG_OR_TONNES=true
HARVEST_SOURCE_CARRIES_NO_DAILY_CURVE=true
HARVEST_SOURCE_CARRIES_NO_MODEL_ID=true
HARVEST_SOURCE_CARRIES_NO_FORECAST_CUTOFF=true
HARVEST_SOURCE_CARRIES_NO_FORECAST_QUANTILE=true
HARVEST_SOURCE_CARRIES_NO_FACTORY_BUILDING_AREA=true
DEFAULT_OBTAIN_SIGNATURE=obtain(self)->tuple[MaterializableRow,...]
FORBIDDEN_MODIFY_PRODUCER_PRODUCE_PORT_SIGNATURE=true
FORBIDDEN_MODIFY_ADAPTER_EVIDENCE_FIELD_SIGNATURE=true
FORBIDDEN_ADD_PARAMETERS_TO_PRODUCE=true
FORBIDDEN_ADD_PARAMETERS_TO_OBTAIN=true
~~~

Harvest source is an upstream seam supplying `MaterializableRow` tuples to the
already-landed producer. It is analogous in role to incumbent forecast replay
source for forecast content, but must not be conflated with forecast replay,
postgres obtain, adapter, or catalog.

### 3.2 Obtain priority table (core freeze)

| priority | condition | outcome |
|---|---|---|
| 1 | explicit non-empty `harvest_rows` on producer | injection wins; harvest source must not override test injection including `BOUND_FIXTURE` path |
| 2 | default construction | future R1 may wire optional internal `harvest_source`; `produce()` / `obtain()` must not gain parameters |
| 3 | default `harvest_rows=()` or `harvest_source.obtain()`=`()` | `produce()`=`None` → `evidence=None` |
| 4 | forbidden default reads | no raw SOURCE_002 primary read, repo scan, hand-written farm/cell/date lists, H7 live evidence, or unverified daily rowset as live harvest |
| 5 | TEST intersection | any harvest row intersecting TEST window `2026-03-10..2026-04-16` excluded; post-exclusion empty → `()` |
| 6 | default catalog after any future obtain | first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT` |
| 7 | forecast non-empty and alignment empty | `NO_S2_IDENTITY_ALIGNMENT` |
| 8 | `catalog_source_kind` | copied from forecast, not from alignment or harvest source |
| 9 | empty harvest / alignment result | no live S2 adapter-in-repository claim; no versioned alignment facts claim |

### 3.3 Future R1 limited edit surface (named only)

~~~text
FUTURE_MAY_CREATE_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_PY=true
FUTURE_PATH=backend/app/s3_daily_rowset/s2_identity_alignment_harvest_source.py
FUTURE_MAY_LIMITED_EDIT_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY_HARVEST_SOURCE_ONLY=true
OPTIONAL_HARVEST_SOURCE_FIELD_LAZY_DEFAULT_FACTORY_ALLOWED=true
CIRCULAR_IMPORT_AVOIDANCE_REQUIRED=true
EXPLICIT_HARVEST_ROWS_WIN_OVER_HARVEST_SOURCE=true
DEFAULT_HARVEST_SOURCE_OBTAIN_EMPTY=true
FUTURE_TEST_PATH=backend/tests/s3_daily_rowset/test_s2_identity_alignment_harvest_source.py
FORBIDDEN_MODIFY_CATALOG_ARTIFACT_PY_WIRING=true
FORBIDDEN_MODIFY_S2_IDENTITY_ALIGNMENT_PY=true
FORBIDDEN_MODIFY_BINDING_PY=true
FORBIDDEN_MODIFY_REGISTRY_PY=true
FORBIDDEN_MODIFY_FORECAST_REPLAY_CONTENT_POSTGRES_OBTAIN_FROZEN_BLOBS=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
PERSISTENCE=IN_MEMORY_SERVICE_ONLY
~~~

Future R1 may add optional `harvest_source` inside the producer (lazy
`default_factory`, circular-import safe) similar to content producer's
`replay_source`. Future R1 must **not** modify `catalog_artifact.py` wiring,
`s2_identity_alignment.py`, `binding.py`, `registry.py`, forecast chain frozen
blobs, or `test_catalog_artifact.py`.

### 3.4 Completeness and SOURCE_002 prohibition

~~~text
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=NOT_PERFORMED
FORBIDDEN_UNVERIFIED_DAILY_ROWSET_AS_LIVE_HARVEST_AUTHORITY=true
SOURCE_002_ROW_LEVEL_READ=false
FORBIDDEN_RAW_SOURCE_002_PRIMARY_READ=true
FORBIDDEN_REPOSITORY_SCAN_FOR_SUBSTITUTES=true
DEFAULT_MONTH_SCOPE=1-4
FORBIDDEN_VARIETIES=普鲜,普青,普冻,废果
FORBIDDEN_FACTORY_BASON=true
~~~

## 4. Explicit non-scope (not authorized by this contract)

~~~text
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_HARVEST_OBTAIN=true
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
CONTRACT_MERGE_DOES_NOT_REWIRE_FORECAST_OBTAIN_PRODUCE_ADAPTER=true
CONTRACT_MERGE_DOES_NOT_REWRITE_ALIGNMENT_CONTRACT_SECTION_6_AUDIT=true
FORBIDDEN_NEW_ALEMBIC=true
FORBIDDEN_PRODUCTION_INIT_PY=true
~~~

## 5. Frozen Python blob audit (byte-identical at contract merge)

~~~text
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
FORBIDDEN_H7_FIXTURE_AS_LIVE_EVIDENCE_OR_CONTENT_IDENTITY=true
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

Any harvest row whose `harvest_business_date` or projection intersects the TEST
window must be excluded; post-exclusion empty → `obtain()`=`()`.

## 8. LLM and deterministic service boundary

LLM agents organize explanation and invoke tools. Harvest row lists, identity
hashes, distinct row counts, SQL, table names, farms, cells, dates, and tonnes
must come from deterministic service logic and coordinator-reviewed artifacts only.
LLM must not invent tonnes, farms, cells, dates, cutoff lists, identity hashes,
SQL, table names, or distinct row counts.

## 9. Registry flip manifest

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_AUTHORIZED=false → true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED=false (companion introduced; not flipped)
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live block and pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-producer-adapter-wiring-contract.md` §12 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-postgres-obtain-contract.md` §15 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-fail-closed-wiring-contract.md` §18 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-envelope-contract.md` §21 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md` §24 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md` §27 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` §30 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §39 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §55 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §38 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §43 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §44 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §47 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §32 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

Unchanged live flags retained:

~~~text
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
~~~

## 10. S2 identity alignment harvest source implementation authorization pointer

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
## 11. S2 identity alignment harvest source R1 pointer

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
