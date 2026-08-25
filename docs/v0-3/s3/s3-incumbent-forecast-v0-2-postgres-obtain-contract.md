# V0.3-S3-A2 Incumbent Forecast V0.2 Postgres Obtain Contract

## Contract identity and phase boundary

~~~text
CONTRACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT
CONTRACT_VERSION=v0-3-s3-a2-incumbent-forecast-v0-2-postgres-obtain-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN
USER_GATE=可以下一步
CONTRACT_ONLY=true
BASE_MAIN_SHA=40f779d6464b368b6429a9430e8a777695380e1b
BASE_MAIN_TREE_SHA=98d84b0338f5177c3a5a535c7ac2b12558be0596
BASE_REF=origin/main
PARENT_WIRING_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-fail-closed-wiring-contract.md
PARENT_REPLAY_SOURCE_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md
PARENT_LIVE_ENVELOPE_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-live-envelope-contract.md
PARENT_CONTENT_PRODUCER_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
REVIEWER_ROLE=COORDINATOR
NO_STEP_IMPLIES_THE_NEXT=true
~~~

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED=false
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
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

This document freezes **V0.2 postgres obtain** governance authority: when
`IncumbentForecastReplaySource.obtain()` may read incumbent forecast replay rows
from the named V0.2 in-service model historical-cutoff point-in-time authority,
and how empty-default obtain must remain fail-closed until that path is separately
implemented.

This is a **V0.2 postgres obtain** governance contract only. It is **not** an
implementation authorization grant, **not** an R1 implementation package, **not**
alignment producer→adapter wiring, **not** live BINDABLE catalog closeout, **not**
SOURCE_002 row-level primary read, **not** TEST unseal, and **not** evidence that
versioned forecast artifacts exist in the repository today.

Contract merge does **not** change current default `obtain()`=`()`, does **not**
implement postgres reading, does **not** invent SQL or table names, and does **not**
write live forecast artifacts into the repository.

Parent contracts **not reopened** by this contract:

- `docs/v0-3/s3/s3-incumbent-forecast-fail-closed-wiring-contract.md` §§1–9 and R1
  pointer (obtain→produce→adapter default chain landed by #341; empty obtain
  remains fail-closed)
- `docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md` §§1–9 and R1
  (`obtain()` signature, grain, harvest-is-not-cutoff; explicit non-empty
  `replay_rows` still use projection)
- `docs/v0-3/s3/s3-incumbent-forecast-live-envelope-contract.md` §§1–9 and §11
  (envelope assignment table unchanged)
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` §§1–9 (content
  identity recipe unchanged)

~~~text
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_V0_2_POSTGRES_OBTAIN=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
CONTRACT_MERGE_DOES_NOT_PRODUCE_CATALOG=true
CONTRACT_MERGE_DOES_NOT_BIND_CATALOG=true
CONTRACT_MERGE_DOES_NOT_WIRE_ALIGNMENT=true
EMPTY_OBTAIN_MUST_NOT_CLAIM_LIVE_KIND=true
DEFAULT_CATALOG_FIRST_BLOCKER_REMAINS_NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_BY_THIS_CONTRACT=true
~~~

## 1. Inherited authority (not reopened)

### 1.1 Parent fail-closed wiring contract and landed R1 (#341) (reference only)

~~~text
FAIL_CLOSED_WIRING_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-fail-closed-wiring-contract.md
FAIL_CLOSED_WIRING_CONTRACT_EVIDENCE_JSON_SHA256=2ea44667836957fa736828cbd4ae123c5d2144a43918939ab4d494f4cbcaf1ff
FAIL_CLOSED_WIRING_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=84c4491daefa59f74d875f7b311612efbead4143688b5582c499981fe82210e0
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
FORECAST_ARTIFACT_PY_BLOB=73e65fbe6774ef555f825efc74c9c8eb5f003575
INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=0cc05fff3deff00d279070aa246f241ff3754e89
TEST_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_PY_BLOB=97b072ca484ce50be6796b88c28b8999d9bde353
~~~

Fail-closed wiring contract §§1–9 and R1 pointer remain authoritative. R1 (#341)
wired obtain→produce→adapter defaults. Default construction still yields empty
obtain and catalog first blocker `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. Wiring
contract and R1 explicitly did not implement V0.2 postgres obtain.

### 1.2 Parent replay source contract and landed R1 (reference only)

~~~text
REPLAY_SOURCE_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md
REPLAY_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=59e452eedc6b8db82063d11ccaf7af177447074c7ad68565b31a6d86d5d4b457
REPLAY_SOURCE_R1_EVIDENCE_JSON_SHA256=59a198c38c0c1e8e17a718bb5623943c4035b4b9b582e2216b922d526b508929
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=070f54311f08a5c7758602fbe105e511fefd8eca
TEST_INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=14a2c27f97fa50a37902558c9819f07cd3d71411
~~~

Current landed `obtain()` behavior:

- `uses_harvest_date_as_forecast_cutoff=true` → `()`
- empty `replay_rows` → `()`
- non-empty `replay_rows` → `project_incumbent_forecast_artifact_entries(...)`

Replay source contract §§1–9 and R1 remain authoritative. This contract does not
modify `obtain()` signature or replay-row projection semantics.

### 1.3 Parent live envelope and content producer (reference only)

~~~text
LIVE_ENVELOPE_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-live-envelope-contract.md
LIVE_ENVELOPE_CONTRACT_EVIDENCE_JSON_SHA256=9b67eabc5ae01f5e834dda4d8321208198a4bef3ad3e1d5f6a3bdf2fe5ed27d4
LIVE_ENVELOPE_R1_EVIDENCE_JSON_SHA256=164b2396091dc5b2daf790f09c92e9ebf628c6e577a37acdc6e4dc0c88b3e601
CONTENT_PRODUCER_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md
CONTENT_CONTRACT_EVIDENCE_JSON_SHA256=6294f2028509f2b1021741ac7aea3f20efdcbe07669b87a1782d18c0a5ca9eae
CONTENT_IDENTITY_VERSION=v0-3-s3-a2-incumbent-forecast-artifact-content-identity-v1
ALIGNMENT_PROJECTION_VERSION=v0-3-s3-a2-s2-identity-alignment-projection-v1
DEFAULT_DECLARED_CATALOG_SOURCE_KIND=BOUND_FIXTURE
TEST_INCUMBENT_FORECAST_LIVE_ENVELOPE_PY_BLOB=cf34f76c734388129b7dbf8d4f585bde584fceac
TEST_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_PY_BLOB=10ac671d603b842ece5cb3ae449b1580715ed2b0
~~~

Live envelope contract §§1–9 and §11 remain authoritative. Envelope assignment
table and content identity recipe are not modified. Default
`declared_catalog_source_kind` remains `BOUND_FIXTURE`; this contract must not
change it to `V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF` by default.

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
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
UNIQUE_ALEMBIC_HEAD=a7c3e9f1b2d4
PEP_420_NAMESPACE=true
PRODUCTION_INIT_PY_FORBIDDEN=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 2. Why this contract is the unique remaining gap

After fail-closed wiring R1 (#341):

1. obtain→produce→adapter default chain is wired; empty default construction still
   yields `obtain()`=`()` and catalog `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.
2. `IncumbentForecastReplaySource.obtain()` still returns `()` when
   `replay_rows` is empty and `uses_harvest_date_as_forecast_cutoff=false`.
3. Wiring contract, implementation authorization, and R1 all state that V0.2
   postgres obtain is **not** implemented.
4. Without a frozen obtain authority contract, a future R1 could invent SQL, table
   names, cutoff lists, or repository-scan substitutes.
5. This contract freezes the only permitted future empty-default obtain path:
   named V0.2 in-service model historical-cutoff point-in-time replay authority
   returning grain `DISTINCT(forecast_cutoff_at, model_id, forecast_quantile)`,
   fail-closed on ambiguity, exclusion, or emptiness.

This contract does not authorize alignment producer→adapter wiring, live BINDABLE
success enumeration, AVAILABLE/VERIFIED closeout, TEST unseal, SOURCE_002 row-level
read, or repository scan substitution.

## 3. V0.2 postgres obtain freeze

### 3.1 Named authority (reference only; no SQL or table names in this contract)

~~~text
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
FORECAST_ARTIFACT_REQUIRES_PIT_REPLAY_AT_HISTORICAL_CUTOFF=true
FORECAST_REPLAY_IS_NOT_MODEL_RETRAINING=true
REPLAY_SOURCE_OUTPUT_TYPE=IncumbentForecastArtifactEntry
REPLAY_SOURCE_OUTPUT_FIELDS=model_id,forecast_cutoff_at,forecast_quantile
REPLAY_SOURCE_GRAIN=DISTINCT(forecast_cutoff_at,model_id,forecast_quantile)
REPLAY_SOURCE_CARRIES_NO_KG_OR_TONNES=true
REPLAY_SOURCE_CARRIES_NO_DAILY_CURVE=true
REPLAY_SOURCE_CARRIES_NO_HARVEST_BUSINESS_DATE=true
REPLAY_SOURCE_CARRIES_NO_CATALOG_CELL=true
REPLAY_SOURCE_CARRIES_NO_ALIGNMENT_IDENTITY=true
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
USES_HARVEST_DATE_AS_FORECAST_CUTOFF_MUST_BE_FALSE=true
OBTAIN_SIGNATURE=obtain(self)->tuple[IncumbentForecastArtifactEntry,...]
FORBIDDEN_MODIFY_REPLAY_SOURCE_PORT_SIGNATURE=true
FORBIDDEN_ADD_PARAMETERS_TO_OBTAIN=true
~~~

Future implementation may bind only to coordinator-reviewed frozen V0.2/S3
authority object names already present in repository contracts. If no such frozen
name exists, obtain must fail-closed to `()`. This contract does not invent new
authority names, SQL, table names, connection strings, DSNs, or database names.

### 3.2 Empty-default obtain priority (core freeze)

When and only when `uses_harvest_date_as_forecast_cutoff=false` and explicit
`replay_rows` is empty, a future R1 **may** attempt V0.2 postgres obtain. This
contract does not implement that path.

| priority | condition | obtain outcome |
|---|---|---|
| 1 | `uses_harvest_date_as_forecast_cutoff=true` | `()`; postgres read forbidden |
| 2 | explicit non-empty `replay_rows` | existing projection path; postgres read forbidden; must not override injection |
| 3 | explicit empty `replay_rows` and `harvest_as_cutoff=false` | future R1 may attempt V0.2 postgres obtain; **not implemented by this contract** |
| 4 | postgres missing / unreadable / ambiguous / unauthorized / projection missing / post-exclusion empty | `()` |
| 5 | empty result | must not claim live kind; must not claim versioned artifact in repository |
| 6 | non-empty result | must pass landed wiring chain and frozen envelope assignment table; live envelope necessary but not sufficient for BINDABLE catalog |
| 7 | default catalog with empty obtain | first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT` |

### 3.3 Relationship to wiring and envelope (reference only)

~~~text
LANDED_WIRING_CHAIN_OBTAIN_TO_PRODUCE_TO_ADAPTER=true
DEFAULT_OBTAIN_REMAINS_EMPTY_UNTIL_SEPARATE_R1=true
ENVELOPE_ASSIGNMENT_TABLE_UNCHANGED=true
CONTENT_IDENTITY_RECIPE_UNCHANGED=true
LIVE_ENVELOPE_KIND_NECESSARY_BUT_NOT_SUFFICIENT_FOR_BINDABLE_CATALOG=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
FORBIDDEN_MODIFY_WIRING_R1=true
~~~

Non-empty obtain results still flow through the landed wiring chain and parent
envelope assignment rules. This contract does not reopen wiring R1 or envelope §3.

### 3.4 Forbidden invention and substitution

~~~text
FORBIDDEN_INVENT_SQL_OR_TABLE_NAMES=true
FORBIDDEN_INVENT_CONNECTION_STRINGS=true
FORBIDDEN_INVENT_DSN_OR_DATABASE_NAMES=true
FORBIDDEN_INVENT_CUTOFF_LISTS=true
FORBIDDEN_INVENT_CONTENT_IDENTITY_SHA256=true
FORBIDDEN_INVENT_CATALOG_IDENTITY=true
FORBIDDEN_INVENT_DISTINCT_ENTRY_COUNTS=true
FORBIDDEN_REPOSITORY_SCAN_FOR_SUBSTITUTES=true
FORBIDDEN_RAW_SOURCE_002_PRIMARY_READ=true
SOURCE_002_ROW_LEVEL_READ=false
POSTGRES_OBTAIN_IS_NOT_SOURCE_002_HARVEST_ROW_READ=true
POSTGRES_OBTAIN_IS_NOT_S2_HARVEST_GRAIN_ENUMERATION=true
FORBIDDEN_H7_FIXTURE_AS_LIVE_EVIDENCE_OR_CONTENT_IDENTITY=true
~~~

### 3.5 Fixture and frozen test paths (preserved)

~~~text
BOUND_FIXTURE_TEST_INJECTION_PATH_MUST_REMAIN=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
TEST_CATALOG_ARTIFACT_PY_BLOB=af59a9f1d291ab32eff23684aca477f0e4a852cd
FORBIDDEN_TOUCH_TEST_FORECAST_ARTIFACT_PY=true
TEST_FORECAST_ARTIFACT_PY_BLOB=2ae0036a46f6f0b2898a8fca3589041b9869c196
FORBIDDEN_TOUCH_TEST_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY=true
TEST_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=11e23e247d6f90e8c7528a073b6e90c709f4a5cc
FORBIDDEN_TOUCH_TEST_INCUMBENT_FORECAST_REPLAY_SOURCE_PY=true
FORBIDDEN_TOUCH_TEST_INCUMBENT_FORECAST_LIVE_ENVELOPE_PY=true
FORBIDDEN_TOUCH_TEST_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_PY=true
FORBIDDEN_TOUCH_TEST_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_PY=true
~~~

## 4. Explicit non-scope (not authorized by this contract)

This contract merge does **not** authorize:

- implementing V0.2 postgres obtain in Python
- changing default `obtain()` from `()` on empty `replay_rows`
- writing versioned incumbent forecast artifacts into the repository
- flipping `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY`
- bindable catalog production or `EVALUATION_INSTANCE_REGISTRY_AVAILABLE` closeout
- `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED` closeout
- alignment producer→adapter wiring
- live BINDABLE success enumeration
- TEST evaluation or TEST unseal
- SOURCE_002 row-level primary read
- modifying envelope assignment table or content identity recipe
- modifying wiring R1 landed behavior
- new Alembic migrations

~~~text
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
FORBIDDEN_LIVE_BINDABLE_SUCCESS_ENUM=true
FORBIDDEN_FLIP_NO_VERSIONED=true
FORBIDDEN_FLIP_NO_BINDABLE=true
FORBIDDEN_FLIP_AVAILABLE_OR_VERIFIED=true
FORBIDDEN_NEW_ALEMBIC=true
FORBIDDEN_PRODUCTION_INIT_PY=true
FORBIDDEN_MODIFY_ENVELOPE_ASSIGNMENT_TABLE=true
FORBIDDEN_MODIFY_CONTENT_IDENTITY_RECIPE=true
FORBIDDEN_V0_2_POSTGRES_CONCURRENCY_CANARY_FLAKY_TESTS=true
FUTURE_MAY_LIMITED_EDIT_INCUMBENT_FORECAST_REPLAY_SOURCE_PY_EMPTY_DEFAULT_OBTAIN_PATH_ONLY=true
FUTURE_TEST_PATH=backend/tests/s3_daily_rowset/test_incumbent_forecast_v0_2_postgres_obtain.py
PERSISTENCE=IN_MEMORY_SERVICE_ONLY
~~~

Future implementation paths above are named only; this contract does not create
implementation authorization or mutate production/test code.

## 5. Frozen Python blob audit (byte-identical at contract merge)

~~~text
FORECAST_ARTIFACT_PY_BLOB=73e65fbe6774ef555f825efc74c9c8eb5f003575
INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=0cc05fff3deff00d279070aa246f241ff3754e89
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=070f54311f08a5c7758602fbe105e511fefd8eca
CATALOG_ARTIFACT_PY_BLOB=968e841527b696d17364ddae11693fadb49462b8
S2_IDENTITY_ALIGNMENT_PY_BLOB=b899e52dbd8752b30395441389ad93fc98d9dbf7
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY_BLOB=14e5614c9069b7b50d12bf3caa36305245c2cc39
BINDING_PY_BLOB=0a335f682a923bcd73908b58cd70cd49c9ab0117
REGISTRY_PY_BLOB=ca16d518ab18136059cd08bcf4b247774d750bb5
TEST_CATALOG_ARTIFACT_PY_BLOB=af59a9f1d291ab32eff23684aca477f0e4a852cd
TEST_FORECAST_ARTIFACT_PY_BLOB=2ae0036a46f6f0b2898a8fca3589041b9869c196
TEST_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=11e23e247d6f90e8c7528a073b6e90c709f4a5cc
TEST_INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=14a2c27f97fa50a37902558c9819f07cd3d71411
TEST_INCUMBENT_FORECAST_LIVE_ENVELOPE_PY_BLOB=cf34f76c734388129b7dbf8d4f585bde584fceac
TEST_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_PY_BLOB=10ac671d603b842ece5cb3ae449b1580715ed2b0
TEST_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_PY_BLOB=97b072ca484ce50be6796b88c28b8999d9bde353
FROZEN_PYTHON_BLOBS_NOT_MUTATED_BY_THIS_CONTRACT=true
~~~

## 6. Forbidden inputs and substitutions

~~~text
FORBIDDEN_USE_HARVEST_BUSINESS_DATE_AS_FORECAST_CUTOFF=true
FORBIDDEN_MODIFY_REPLAY_SOURCE_OBTAIN_SEMANTICS=true
FORBIDDEN_MODIFY_REGISTRY_PY=true
FORBIDDEN_MODIFY_BINDING_PY=true
FORBIDDEN_MODIFY_S2_IDENTITY_ALIGNMENT_PY=true
FORBIDDEN_MODIFY_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY=true
FORBIDDEN_WIRE_ALIGNMENT_PRODUCER_IN_THIS_CONTRACT=true
FORBIDDEN_ADD_CATALOG_SOURCE_KIND_TO_INCUMBENT_FORECAST_ARTIFACT_ENTRY=true
FORBIDDEN_SUBSTITUTION_INCUMBENT_DAILY_CURVE_PROVIDER=true
FORBIDDEN_SUBSTITUTION_SPARSE_HORIZON_BINDING_FORECAST_PROVIDER=true
FORBIDDEN_SUBSTITUTION_S3_BINDING_ROW=true
FORBIDDEN_SUBSTITUTION_S2_HARVEST_GRAIN=true
FORBIDDEN_SUBSTITUTION_H7_FIXTURE=true
~~~

## 7. TEST seal and exclusion policy

~~~text
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
TEST_PARTITION_DATES=2026-03-10..2026-04-16
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
FORBIDDEN_TEST_CUTOFF_OR_HORIZON_INTERSECTION=true
DEFAULT_MONTH_SCOPE=1-4
FORBIDDEN_VARIETIES=普鲜,普青,普冻,废果
FORBIDDEN_FACTORY_BASON=true
~~~

Any `forecast_cutoff_at` or 7/14/21-day evaluation horizon window intersecting TEST
partition dates must be excluded before obtain may return rows. Post-exclusion
emptiness must yield `()`.

## 8. LLM and deterministic service boundary

LLM agents organize explanation and invoke tools. Obtain outcomes, cutoff lists,
identity hashes, distinct entry counts, SQL, table names, and tonnes must come
from deterministic service logic and coordinator-reviewed artifacts only. LLM must
not invent tonnes, farms, cells, cutoff lists, identity hashes, SQL, table names,
or distinct entry counts.

## 9. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live block and pointer
- `docs/v0-3/s3/s3-incumbent-forecast-fail-closed-wiring-contract.md` §12 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-envelope-contract.md` §15 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md` §18 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md` §21 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` §24 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §33 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §49 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §32 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §37 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §38 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §41 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §26 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

Unchanged live flags retained:

~~~text
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
~~~

## 10. Incumbent forecast V0.2 postgres obtain implementation authorization pointer

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-postgres-obtain-authorization.md
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-postgres-obtain-authorization.json
EVIDENCE_JSON_SHA256=6b3655921acd896f0570e0c01fbcb5a85478018c8c968bb84c26a02567253bdd
PARENT_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
FAIL_CLOSED_WIRING_CONTRACT_EVIDENCE_JSON_SHA256=2ea44667836957fa736828cbd4ae123c5d2144a43918939ab4d494f4cbcaf1ff
LIVE_ENVELOPE_R1_EVIDENCE_JSON_SHA256=164b2396091dc5b2daf790f09c92e9ebf628c6e577a37acdc6e4dc0c88b3e601
REPLAY_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=59e452eedc6b8db82063d11ccaf7af177447074c7ad68565b31a6d86d5d4b457
REPLAY_SOURCE_R1_EVIDENCE_JSON_SHA256=59a198c38c0c1e8e17a718bb5623943c4035b4b9b582e2216b922d526b508929
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_V0_2_POSTGRES_OBTAIN=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
~~~

Live `S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTATION_AUTHORIZED` authority
follows `docs/v0-3/development-plan.md` §4.4 live state block; this pointer does
not rewrite V0.2 postgres obtain contract freeze rules in §§1–9.

## 11. Incumbent forecast V0.2 postgres obtain R1 pointer

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-postgres-obtain-r1.md
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-postgres-obtain-r1.json
EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
V0_2_POSTGRES_OBTAIN_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=6b3655921acd896f0570e0c01fbcb5a85478018c8c968bb84c26a02567253bdd
V0_2_POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_AUTHORIZED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
IMPLEMENTATION_MERGE_DOES_NOT_WIRE_ALIGNMENT=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
~~~

Live `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED` authority
follows `docs/v0-3/development-plan.md` §4.4 live state block; this pointer does
not rewrite V0.2 postgres obtain contract freeze rules in §§1–9. R1 lands empty-default fail-closed postgres obtain;
no frozen SQL or table names exist in repository contracts so default `obtain()`
remains `()`.

## 12. S2 identity alignment producer→adapter wiring contract pointer

~~~text
CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-producer-adapter-wiring-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-producer-adapter-wiring-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-producer-adapter-wiring-contract.json
EVIDENCE_JSON_SHA256=89e4a35e68d70d942df0c795953573828618d62ac3caddc78dba5609608ec36a
PARENT_ALIGNMENT_CONTRACT_GIT_BLOB_SHA=7568a608b891d4b98b9aaf7f6857a28eb90bb123
PARENT_EVIDENCE_PRODUCER_CONTRACT_GIT_BLOB_SHA=22f49d7a78bad1a9332040e9f890daa22ef4b1e3
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_AUTHORIZED=true
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
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_WIRING=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_PRODUCE_FROM_NONE=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
~~~

Live `S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_AUTHORIZED` authority
follows `docs/v0-3/development-plan.md` §4.4 live state block; this pointer does
not rewrite V0.2 postgres obtain contract freeze rules in §§1–9.

## 13. S2 identity alignment producer→adapter wiring implementation authorization pointer

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
not rewrite V0.2 postgres obtain contract freeze rules in §§1–9.

## 14. S2 identity alignment producer→adapter wiring R1 pointer

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
not rewrite V0.2 postgres obtain contract freeze rules in §§1–9. R1 wires default producer→adapter construction;
default `harvest_rows=()` still yields `evidence=None`; `NO_LIVE_S2` remains `true`.
