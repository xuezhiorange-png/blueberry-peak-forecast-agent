# V0.3-S3-A2 Incumbent Forecast Replay-Identity Persistence Schema Contract

## Contract identity and phase boundary

~~~text
CONTRACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT
CONTRACT_VERSION=v0-3-s3-a2-incumbent-forecast-replay-identity-persistence-schema-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA
USER_GATE=可以下一步
CONTRACT_ONLY=true
BASE_MAIN_SHA=694e41b1097afb7e608c07eedbf08323103a952a
BASE_MAIN_TREE_SHA=57f4383178e9b762922b4bd486614fda39d8ba2a
BASE_REF=origin/main
PARENT_SQL_TABLE_AUTHORITY_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-sql-table-authority-contract.md
PARENT_SQL_TABLE_AUTHORITY_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=97c15064445d0ff4776884234994f0a10f6537d5
SQL_TABLE_AUTHORITY_CONTRACT_EVIDENCE_JSON_SHA256=99e4bb4853b6020404a86221c470936fce27f26bb6373fbe81167ffaeac6e260
SQL_TABLE_AUTHORITY_GRANT_EVIDENCE_JSON_SHA256=8262b9350f59db13ecf67e87734ca6dc9caf58f8c4689c64a331a36b551f1cfd
SQL_TABLE_AUTHORITY_R1_EVIDENCE_JSON_SHA256=aad30ef4b0f6b16cbdab8aab4571f231e46758b138ab636d7b20208c55a39218
PARENT_POSTGRES_OBTAIN_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-postgres-obtain-contract.md
PARENT_POSTGRES_OBTAIN_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c02ae702995c38f33ca73c3af26e8fdb33cc8e04
CURRENT_ORIGIN_MAIN_POSTGRES_OBTAIN_CONTRACT_GIT_BLOB_SHA=b919bc7a9fe3e4ed7f1345ba12f0b11da53ecb9c
V0_2_POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
REVIEWER_ROLE=COORDINATOR
NO_STEP_IMPLIES_THE_NEXT=true
~~~

~~~text
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
MATCH_TABLE_NAMES=()
MATCH_TABLE_COUNT=0
AUDIT_TABLE_COUNT=106
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
FROZEN_FUTURE_OBJECT_NAME=s3_incumbent_forecast_replay_identity
FROZEN_FUTURE_OBJECT_EXISTS_IN_ALEMBIC=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This document freezes a **future Alembic persistence object** for incumbent forecast
replay identity: coordinator-reviewed table name `s3_incumbent_forecast_replay_identity`
with grain columns matching landed `IncumbentForecastArtifactEntry` semantics. The
object does **not** exist in Alembic today and is **not** one of the audited 106 tables.

This is a **persistence-schema governance contract** only. It is **not** an
implementation authorization grant, **not** Alembic / CREATE TABLE R1, **not** live
postgres read, **not** a bindable-name flip, **not** versioned artifact creation,
**not** catalog closeout, **not** SOURCE_002 row-level read, **not** TEST unseal, and
**not** evidence that S3 is complete.

Contract merge does **not** add Alembic revisions, does **not** implement live postgres
read, does **not** invent SQL or connection strings, does **not** reclassify any of
the 106 existing tables as `MATCH`, does **not** add names to `MATCH_TABLE_NAMES`, and
does **not** flip `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY`.

Honest boundary: even if a later schema R1 creates an empty table from this freeze,
default obtain remains `()` until separate coordinator-reviewed contracts authorize
bindable-name review after real table existence, live postgres read, and non-invented
identity population paths. Default catalog first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.

~~~text
CONTRACT_MERGE_DOES_NOT_ADD_ALEMBIC=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
CONTRACT_MERGE_DOES_NOT_INVENT_SQL_OR_TABLE_NAMES=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_LIVE_S2=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_BINDABLE_V0_2_SQL_TABLE_NAME=true
CONTRACT_MERGE_DOES_NOT_FLIP_AVAILABLE_OR_VERIFIED=true
CONTRACT_MERGE_DOES_NOT_UNSEAL_TEST=true
CONTRACT_MERGE_DOES_NOT_SOURCE_002_ROW_LEVEL_READ=true
CONTRACT_MERGE_DOES_NOT_REOPEN_106_ROW_AUDIT=true
CONTRACT_MERGE_DOES_NOT_RECLASSIFY_EXISTING_106=true
FORBIDDEN_WRITE_SELECT_FROM_JOIN_WHERE_IN_CONTRACT=true
FORBIDDEN_WRITE_DSN_OR_CONNECTION_STRINGS=true
FORBIDDEN_NEW_ALEMBIC=true
FORBIDDEN_PRODUCTION_INIT_PY=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_BY_THIS_CONTRACT=true
~~~

## 1. Inherited authority (not reopened)

### 1.1 Parent SQL table-name authority contract

~~~text
PARENT_SQL_TABLE_AUTHORITY_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-sql-table-authority-contract.md
PARENT_SQL_TABLE_AUTHORITY_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=97c15064445d0ff4776884234994f0a10f6537d5
SQL_TABLE_AUTHORITY_CONTRACT_EVIDENCE_JSON_SHA256=99e4bb4853b6020404a86221c470936fce27f26bb6373fbe81167ffaeac6e260
SQL_TABLE_AUTHORITY_R1_EVIDENCE_JSON_SHA256=aad30ef4b0f6b16cbdab8aab4571f231e46758b138ab636d7b20208c55a39218
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
MATCH_TABLE_NAMES=()
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
~~~

Parent contract §§1–9 and the frozen 106-row `MATCH`/`NOT_MATCH` audit remain
authoritative. This contract cites that audit only; it does not copy the 106-row
register and does not reopen or reclassify it. `FORBIDDEN_INVENT_SQL_OR_TABLE_NAMES`
from parent contract #351 forbids inventing `MATCH` names for the existing 106 tables;
this contract instead freezes one **future** object name not present in Alembic today.

### 1.2 Parent postgres obtain contract §3.1

~~~text
PARENT_POSTGRES_OBTAIN_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-postgres-obtain-contract.md
PARENT_POSTGRES_OBTAIN_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c02ae702995c38f33ca73c3af26e8fdb33cc8e04
V0_2_POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
~~~

Parent contract §§1–9 remain authoritative. Parent §3.1 requires future implementation
to bind only coordinator-reviewed frozen names already present in repository contracts;
if no bindable name exists, obtain must fail-closed to `()`. This persistence-schema
contract is the coordinator-reviewed freeze for a **future** name; because the object
does not exist in Alembic yet, it is **not** a repository bindable name today and does
not change `NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY`.

### 1.3 Frozen replay-source grain

~~~text
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
REPLAY_SOURCE_GRAIN=DISTINCT(forecast_cutoff_at,model_id,forecast_quantile)
REPLAY_SOURCE_OUTPUT_FIELDS=model_id,forecast_cutoff_at,forecast_quantile
REPLAY_SOURCE_CARRIES_NO_KG_OR_TONNES=true
REPLAY_SOURCE_CARRIES_NO_DAILY_CURVE=true
REPLAY_SOURCE_CARRIES_NO_HARVEST_BUSINESS_DATE=true
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
USES_HARVEST_DATE_AS_FORECAST_CUTOFF_MUST_BE_FALSE=true
CONTENT_IDENTITY_VERSION=v0-3-s3-a2-incumbent-forecast-artifact-content-identity-v1
ALIGNMENT_PROJECTION_VERSION=v0-3-s3-a2-s2-identity-alignment-projection-v1
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IDENTITY_VERSION=v0-3-s3-a2-accepted-s2-identity-alignment-evidence-identity-v1
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
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
SOURCE_002_ROW_LEVEL_READ=false
DEFAULT_MONTH_SCOPE=1-4
FORBIDDEN_VARIETIES=普鲜,普青,普冻,废果
FORBIDDEN_FACTORY_BASON=true
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
~~~

Alignment contract §6 audit (`EmptyS2IdentityAlignmentPort` production default snapshot)
remains byte-identical and is not reopened. H7 fixture hash is forbidden as live
evidence or content identity.

## 2. Why this contract is the unique remaining gap

1. SQL table-name authority R1 (#353) encoded `MATCH_TABLE_COUNT=0` in memory; default
   `obtain()` still returns `()`.
2. All 106 existing Alembic tables remain `NOT_MATCH`; `core_forecast_daily_row` and
   `rolling_backtest_binding_row` must not bind.
3. Without a coordinator-reviewed future persistence object, later live-read work could
   invent SQL or mis-bind kg-bearing tables.
4. This contract freezes only the future object name and replay-grain column semantics.
5. Empty harvest source remains a separate second blocker when forecast is non-empty;
   this contract does not address S2 alignment.
6. This contract does **not** flip `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY`.

## 3. Future persistence object freeze

### 3.1 Object identity

~~~text
FROZEN_FUTURE_OBJECT_NAME=s3_incumbent_forecast_replay_identity
FROZEN_FUTURE_OBJECT_KIND=TABLE
FROZEN_FUTURE_OBJECT_EXISTS_IN_ALEMBIC=false
FROZEN_FUTURE_OBJECT_IS_NOT_ONE_OF_THE_106=true
FROZEN_FUTURE_OBJECT_IS_NOT_ADDED_TO_MATCH_TABLE_NAMES=true
COORDINATOR_REVIEWED_FUTURE_OBJECT_NAME_FREEZE=true
THIS_IS_NOT_RECLASSIFYING_THE_106=true
OBJECT_KIND_MUST_BE_TABLE_NOT_VIEW=true
~~~

The frozen name is coordinator-reviewed for future Alembic creation only. It is not
present in `backend/alembic/versions/*.py` at `694e41b`. It must not be treated as a
bindable V0.2 SQL table name until a separate contract reviews bindability after the
table truly exists.

### 3.2 Grain columns and uniqueness

~~~text
REPLAY_SOURCE_GRAIN=DISTINCT(forecast_cutoff_at,model_id,forecast_quantile)
REPLAY_SOURCE_OUTPUT_FIELDS=model_id,forecast_cutoff_at,forecast_quantile
REQUIRED_COLUMNS=forecast_cutoff_at,model_id,forecast_quantile
REQUIRED_COLUMNS_NOT_NULL=true
UNIQUE_ON_GRAIN_TRIPLE=true
OPTIONAL_SURROGATE_PRIMARY_KEY_ALLOWED=true
SURROGATE_PK_MUST_NOT_REPLACE_GRAIN_UNIQUENESS=true
~~~

Column semantics (matching landed `IncumbentForecastArtifactEntry`; no executable DDL):

| column | semantics |
|---|---|
| `forecast_cutoff_at` | timezone-aware timestamp; naive timestamps forbidden (consistent with Python replay source) |
| `model_id` | non-empty text |
| `forecast_quantile` | non-empty text |
| optional surrogate primary key | integer or UUID permitted; must not replace grain triple uniqueness; must not enter replay grain |

### 3.3 Forbidden columns

The future object must not carry kg, tonnes, weight, quantity, forecast values, daily
curves, harvest business dates, catalog cells, alignment identity, or
`physical_alignment_status` columns. `harvest_business_date` must not substitute for
`forecast_cutoff_at`.

~~~text
FORBIDDEN_COLUMN_FAMILIES=kg,tonnes,weight,quantity,forecast_value,daily_curve,harvest_business_date,catalog_cell,alignment_identity,physical_alignment_status
USES_HARVEST_DATE_AS_FORECAST_CUTOFF_MUST_BE_FALSE=true
~~~

### 3.4 Future Alembic linearity

~~~text
UNIQUE_ALEMBIC_HEAD_AT_FREEZE=a7c3e9f1b2d4
FUTURE_SCHEMA_R1_MUST_BE_LINEAR_CHILD_OF_UNIQUE_HEAD=true
FORBIDDEN_PARALLEL_ALEMBIC_HEAD=true
FORBIDDEN_NEW_ALEMBIC_IN_THIS_CONTRACT=true
FUTURE_SCHEMA_R1_MAY_CREATE_ONLY_THIS_EMPTY_TABLE=true
DEFAULT_ROW_COUNT_AT_CREATION=0
~~~

A later schema implementation R1 (not authorized here) may add exactly one linear
child revision from the then-unique Alembic head, creating only this frozen empty table.
If head advances before that R1, the child revision must attach to the then-unique head.

### 3.5 What even a later empty-table R1 would not flip

~~~text
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
EMPTY_TABLE_IS_NOT_LIVE_POSTGRES_READ=true
EMPTY_TABLE_DOES_NOT_REOPEN_106_AUDIT=true
EMPTY_TABLE_DOES_NOT_ADD_TO_MATCH_TABLE_NAMES=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY_REMAINS_TRUE_UNTIL_SEPARATE_BINDABLE_REVIEW=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
FORBIDDEN_INVENT_CUTOFF_MODEL_QUANTILE_ROWS=true
~~~

## 4. Explicit non-scope (not authorized by this contract)

~~~text
CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_SCHEMA=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
CONTRACT_MERGE_DOES_NOT_POPULATE_ROWS=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
CONTRACT_MERGE_DOES_NOT_PRODUCE_CATALOG=true
CONTRACT_MERGE_DOES_NOT_BIND_CATALOG=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_LIVE_S2=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_BINDABLE_V0_2_SQL_TABLE_NAME=true
CONTRACT_MERGE_DOES_NOT_FLIP_AVAILABLE_OR_VERIFIED=true
CONTRACT_MERGE_DOES_NOT_UNSEAL_TEST=true
CONTRACT_MERGE_DOES_NOT_SOURCE_002_ROW_LEVEL_READ=true
FORBIDDEN_WRITE_CREATE_TABLE_IN_CONTRACT=true
FORBIDDEN_WRITE_ALTER_TABLE_IN_CONTRACT=true
FORBIDDEN_WRITE_SELECT_FROM_JOIN_WHERE_IN_CONTRACT=true
FORBIDDEN_WRITE_DSN_OR_CONNECTION_STRINGS=true
FORBIDDEN_INVENT_REVISION_ID=true
FORBIDDEN_INVENT_EXTRA_TABLE_NAMES=true
FORBIDDEN_INVENT_EXTRA_COLUMNS_BEYOND_OPTIONAL_SURROGATE_PK=true
FORBIDDEN_INVENT_INDEXES_BEYOND_GRAIN_UNIQUENESS=true
~~~

## 5. Frozen Python blob audit (byte-identical at contract merge)

~~~text
CATALOG_ARTIFACT_PY_BLOB=8196cb7dca33df8708f78789bd2eb9e8243b8354
S2_IDENTITY_ALIGNMENT_PY_BLOB=b899e52dbd8752b30395441389ad93fc98d9dbf7
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY_BLOB=b0dc923ae4a4c06e3f6ccafd38e175d8ac16d3f7
S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_PY_BLOB=ae3381d2c0b0744a49519370e67005c479120665
FORECAST_ARTIFACT_PY_BLOB=73e65fbe6774ef555f825efc74c9c8eb5f003575
INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=0cc05fff3deff00d279070aa246f241ff3754e89
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=9ffb7bdf9beb1d897b8a1752f06de9250011cf15
INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_PY_BLOB=96dfcdd079382f8009adba2c315e75691f3ea22d
BINDING_PY_BLOB=0a335f682a923bcd73908b58cd70cd49c9ab0117
REGISTRY_PY_BLOB=ca16d518ab18136059cd08bcf4b247774d750bb5
TEST_CATALOG_ARTIFACT_PY_BLOB=af59a9f1d291ab32eff23684aca477f0e4a852cd
TEST_S2_IDENTITY_ALIGNMENT_PY_BLOB=9c653823ebca79fdb12d61325fdb4b18e17d0cef
TEST_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY_BLOB=c81c3ebfe565095f17cfa8794d115ea9fab0ca73
TEST_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_PY_BLOB=9fdd22ccadd6990fa2522c8b23a287dc4e87f173
TEST_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_PY_BLOB=929b9fc8a89c1a0b31154cd89b2bd6d4c7cb4a4a
TEST_FORECAST_ARTIFACT_PY_BLOB=2ae0036a46f6f0b2898a8fca3589041b9869c196
TEST_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=11e23e247d6f90e8c7528a073b6e90c709f4a5cc
TEST_INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=14a2c27f97fa50a37902558c9819f07cd3d71411
TEST_INCUMBENT_FORECAST_LIVE_ENVELOPE_PY_BLOB=cf34f76c734388129b7dbf8d4f585bde584fceac
TEST_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_PY_BLOB=10ac671d603b842ece5cb3ae449b1580715ed2b0
TEST_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_PY_BLOB=97b072ca484ce50be6796b88c28b8999d9bde353
TEST_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_PY_BLOB=8db60cba335dd87ac72f7b86469168e15b7efe97
TEST_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_PY_BLOB=8b71c85fb07ffded95c9d27c37145cfbc5d4488f
BOUND_FIXTURE_TEST_INJECTION_PATH_MUST_REMAIN=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
FORBIDDEN_TOUCH_ANY_PYTHON=true
~~~

## 6. Forbidden inputs and substitutions

~~~text
FORBIDDEN_INVENT_SQL_OR_TABLE_NAMES=true
FORBIDDEN_INVENT_CONNECTION_STRINGS=true
FORBIDDEN_INVENT_DSN_OR_DATABASE_NAMES=true
FORBIDDEN_INVENT_CUTOFF_LISTS=true
FORBIDDEN_INVENT_CONTENT_IDENTITY_SHA256=true
FORBIDDEN_INVENT_DISTINCT_ENTRY_COUNTS=true
FORBIDDEN_INVENT_TONNES_OR_KG=true
FORBIDDEN_REPOSITORY_SCAN_FOR_SUBSTITUTES=true
FORBIDDEN_RAW_SOURCE_002_PRIMARY_READ=true
FORBIDDEN_H7_FIXTURE_AS_LIVE_EVIDENCE_OR_CONTENT_IDENTITY=true
FORBIDDEN_RECLASSIFY_HARVEST_STATE_REPLAY_SOURCE_VISIBILITY_AUDIT=true
FORBIDDEN_BIND_KG_TABLES_AS_REPLAY_AUTHORITY=true
FORBIDDEN_BIND_ROLLING_BACKTEST_BINDING_ROW=true
FORBIDDEN_BIND_CORE_FORECAST_DAILY_ROW=true
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

## 8. LLM and deterministic service boundary

LLM agents organize explanation and invoke tools. Persistence schema names, SQL, DSN,
connection strings, cutoff lists, identity hashes, row content, and tonnes must come
from deterministic service logic and coordinator-reviewed artifacts only. LLM must not
invent tonnes, SQL, table names beyond this freeze, DSNs, connection strings, cutoff
lists, identity hashes, or row payloads.

## 9. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_AUTHORIZED=false → true
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED=false (companion introduced; not flipped)
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTATION_AUTHORIZED=false (companion introduced; not flipped)
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block and pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-sql-table-authority-contract.md` §12 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-harvest-source-contract.md` §15 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-producer-adapter-wiring-contract.md` §18 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-postgres-obtain-contract.md` §21 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-fail-closed-wiring-contract.md` §24 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-envelope-contract.md` §27 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md` §30 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md` §33 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` §36 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §45 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §61 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §44 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §49 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §50 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §53 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §38 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

Unchanged live flags retained:

~~~text
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
MATCH_TABLE_COUNT=0
AUDIT_TABLE_COUNT=106
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
~~~

## 10. Incumbent forecast replay-identity persistence schema implementation authorization pointer

~~~text
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-identity-persistence-schema-authorization.md
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-replay-identity-persistence-schema-authorization.json
EVIDENCE_JSON_SHA256=f58fa58c9f3e815c2a987903d1ec4f2ef6818008cba966c57b1b9ccfafdf6e01
PARENT_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=cb7dbac6c1f2c0e1a9c23a69f1ad6a684da40e75
PARENT_CONTRACT_EVIDENCE_JSON_SHA256=b0c2553f3a561bf8c46b39f015a604f31f9c6a9c5d682a060ad5eff0dfbfb806
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
FROZEN_FUTURE_OBJECT_NAME=s3_incumbent_forecast_replay_identity
FROZEN_FUTURE_OBJECT_EXISTS_IN_ALEMBIC=false
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_SCHEMA=true
AUTHORIZATION_MERGE_DOES_NOT_ADD_ALEMBIC=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_NO_BINDABLE_V0_2_SQL_TABLE_NAME=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_LIVE_POSTGRES_READ=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
~~~

Live `S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTATION_AUTHORIZED`
authority follows `docs/v0-3/development-plan.md` §4.4 live state block; this pointer does
not rewrite persistence-schema contract freeze rules in §§1–9 or reopen the parent 106-row
Alembic audit. This grant records what a later deterministic schema R1 may do when the user
again says 「可以实施」: create the frozen empty table `s3_incumbent_forecast_replay_identity`
via one linear Alembic revision. It does not add Alembic, write SQL, populate rows, or flip
`NO_VERSIONED` / `NO_BINDABLE_V0_2` / `LIVE_POSTGRES_READ`. Authorization merge does not
close S3. `DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED`
and `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED` remain `false`.
A later schema R1 flips only `SCHEMA_IMPLEMENTED`, not `LIVE_POSTGRES_READ`. Historical
pointer snapshots may remain `false`.

## 11. Incumbent forecast replay-identity persistence schema R1 pointer

~~~text
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-identity-persistence-schema-r1.md
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-replay-identity-persistence-schema-r1.json
EVIDENCE_JSON_SHA256=921df3fd317213eeaf44fe594e72650ac7dea84d8499ca915c5f627fe60e3599
SCHEMA_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=f58fa58c9f3e815c2a987903d1ec4f2ef6818008cba966c57b1b9ccfafdf6e01
SCHEMA_CONTRACT_EVIDENCE_JSON_SHA256=b0c2553f3a561bf8c46b39f015a604f31f9c6a9c5d682a060ad5eff0dfbfb806
SQL_TABLE_AUTHORITY_R1_EVIDENCE_JSON_SHA256=aad30ef4b0f6b16cbdab8aab4571f231e46758b138ab636d7b20208c55a39218
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
FROZEN_FUTURE_OBJECT_NAME=s3_incumbent_forecast_replay_identity
FROZEN_FUTURE_OBJECT_EXISTS_IN_ALEMBIC=true
ALEMBIC_REVISION=e8b2c4d6f1a3
ALEMBIC_DOWN_REVISION=a7c3e9f1b2d4
ALEMBIC_MIGRATION_PATH=backend/alembic/versions/e8b2c4d6f1a3_s3_incumbent_forecast_replay_identity.py
ALEMBIC_MIGRATION_BLOB=1e0864ebef1d947d4c9466d71efaa759d44c7ad7
UPGRADE_ROW_COUNT=0
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
MATCH_TABLE_NAMES=()
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
EMPTY_TABLE_IS_NOT_LIVE_POSTGRES_READ=true
EMPTY_TABLE_DOES_NOT_ADD_TO_MATCH_TABLE_NAMES=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_LIVE_POSTGRES_READ=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_NO_BINDABLE_V0_2=true
IMPLEMENTATION_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
IMPLEMENTATION_MERGE_DOES_NOT_POPULATE_UPGRADE_ROWS=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
SCHEMA_R1_FLIPS_ONLY_SCHEMA_IMPLEMENTED=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
~~~

Live `DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED` authority
follows `docs/v0-3/development-plan.md` §4.4 live state block; this pointer does not rewrite
persistence-schema contract freeze rules in §§1–9 or reopen the parent 106-row Alembic audit.
R1 creates the frozen empty Alembic table `s3_incumbent_forecast_replay_identity` with 0 upgrade
rows. Empty table ≠ versioned incumbent forecast artifact. Empty table ≠ bindable V0.2 SQL table
name. Empty table ≠ live postgres read. Default `obtain()` remains `()`. This R1 flips only
`SCHEMA_IMPLEMENTED`, not `LIVE_POSTGRES_READ`. Historical grant/contract pointer snapshots may
remain `false` for `FROZEN_FUTURE_OBJECT_EXISTS_IN_ALEMBIC`.

