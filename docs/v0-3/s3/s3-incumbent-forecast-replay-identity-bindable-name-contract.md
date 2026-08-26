# V0.3-S3-A2 Incumbent Forecast Replay-Identity Bindable Name Contract

## Contract identity and phase boundary

~~~text
CONTRACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT
CONTRACT_VERSION=v0-3-s3-a2-incumbent-forecast-replay-identity-bindable-name-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME
USER_GATE=可以下一步
CONTRACT_ONLY=true
BASE_MAIN_SHA=67f436fe47003c015e868b0a04fe2b9409490bf5
BASE_MAIN_TREE_SHA=f00e50503b272f1201ad8cc139144f8e7aa48c4e
BASE_REF=origin/main
PARENT_PERSISTENCE_SCHEMA_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-replay-identity-persistence-schema-contract.md
PARENT_PERSISTENCE_SCHEMA_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=a7cf5abfed864fb95ab2f870c422a0f7caaf97fd
SCHEMA_CONTRACT_EVIDENCE_JSON_SHA256=b0c2553f3a561bf8c46b39f015a604f31f9c6a9c5d682a060ad5eff0dfbfb806
SCHEMA_GRANT_EVIDENCE_JSON_SHA256=f58fa58c9f3e815c2a987903d1ec4f2ef6818008cba966c57b1b9ccfafdf6e01
SCHEMA_R1_EVIDENCE_JSON_SHA256=921df3fd317213eeaf44fe594e72650ac7dea84d8499ca915c5f627fe60e3599
PARENT_SQL_TABLE_AUTHORITY_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-sql-table-authority-contract.md
PARENT_SQL_TABLE_AUTHORITY_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=97c15064445d0ff4776884234994f0a10f6537d5
CURRENT_SQL_TABLE_AUTHORITY_CONTRACT_GIT_BLOB_SHA=e492f77475ee363c1eca7aa526c78f623874d317
SQL_TABLE_AUTHORITY_CONTRACT_EVIDENCE_JSON_SHA256=99e4bb4853b6020404a86221c470936fce27f26bb6373fbe81167ffaeac6e260
SQL_TABLE_AUTHORITY_R1_EVIDENCE_JSON_SHA256=aad30ef4b0f6b16cbdab8aab4571f231e46758b138ab636d7b20208c55a39218
PARENT_POSTGRES_OBTAIN_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-postgres-obtain-contract.md
PARENT_POSTGRES_OBTAIN_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c02ae702995c38f33ca73c3af26e8fdb33cc8e04
CURRENT_POSTGRES_OBTAIN_CONTRACT_GIT_BLOB_SHA=25b99e3fd4a55501b2df17204d9f24735f3d1168
V0_2_POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
REVIEWER_ROLE=COORDINATOR
NO_STEP_IMPLIES_THE_NEXT=true
~~~

~~~text
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
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
FROZEN_FUTURE_OBJECT_EXISTS_IN_ALEMBIC=true
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This document freezes coordinator-reviewed **bindable name** authority for the now-existing
empty Alembic table `s3_incumbent_forecast_replay_identity`. Schema R1 (#356) created the
table with 0 upgrade rows. This contract reviews whether that existing empty table may serve
as the sole coordinator-reviewed bindable replay-identity table name for **future** live-read
paths. It is **not** live postgres read, **not** row population, **not** a bindable-name
implementation grant, **not** a `NO_BINDABLE_V0_2` flip, **not** versioned artifact creation,
**not** catalog closeout, and **not** evidence that S3 is complete.

Contract merge does **not** implement live postgres read, does **not** populate rows, does
**not** change default `obtain()` from `()`, does **not** flip
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY`, does **not** flip
`NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY`, does **not** add names to `MATCH_TABLE_NAMES`,
does **not** reclassify any of the 106 audited tables, and does **not** reopen the parent
106-row Alembic audit.

Honest boundary: table existence ≠ bindable implementation. Even after a later bindable-name
R1 records this frozen name in deterministic code and flips `NO_BINDABLE_V0_2` to `false`,
default `obtain()` remains `()` until separate live-read contract + authorization + R1.
Reading the empty table still yields `()`. Empty bindable candidate ≠ versioned incumbent
forecast artifact. This contract does not close S3.

~~~text
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
CONTRACT_MERGE_DOES_NOT_POPULATE_ROWS=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_BINDABLE_V0_2=true
CONTRACT_MERGE_DOES_NOT_FLIP_LIVE_POSTGRES_READ=true
CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true
CONTRACT_MERGE_DOES_NOT_REOPEN_106_ROW_AUDIT=true
CONTRACT_MERGE_DOES_NOT_RECLASSIFY_EXISTING_106=true
CONTRACT_MERGE_DOES_NOT_ADD_TO_MATCH_TABLE_NAMES=true
FORBIDDEN_WRITE_SELECT_FROM_JOIN_WHERE_IN_CONTRACT=true
FORBIDDEN_WRITE_DSN_OR_CONNECTION_STRINGS=true
FORBIDDEN_NEW_ALEMBIC=true
FORBIDDEN_PRODUCTION_INIT_PY=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_BY_THIS_CONTRACT=true
~~~

## 1. Inherited authority (not reopened)

### 1.1 Parent persistence-schema contract

~~~text
PARENT_PERSISTENCE_SCHEMA_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-replay-identity-persistence-schema-contract.md
PARENT_PERSISTENCE_SCHEMA_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=a7cf5abfed864fb95ab2f870c422a0f7caaf97fd
SCHEMA_CONTRACT_EVIDENCE_JSON_SHA256=b0c2553f3a561bf8c46b39f015a604f31f9c6a9c5d682a060ad5eff0dfbfb806
SCHEMA_GRANT_EVIDENCE_JSON_SHA256=f58fa58c9f3e815c2a987903d1ec4f2ef6818008cba966c57b1b9ccfafdf6e01
SCHEMA_R1_EVIDENCE_JSON_SHA256=921df3fd317213eeaf44fe594e72650ac7dea84d8499ca915c5f627fe60e3599
ALEMBIC_REVISION=e8b2c4d6f1a3
ALEMBIC_DOWN_REVISION=a7c3e9f1b2d4
ALEMBIC_MIGRATION_PATH=backend/alembic/versions/e8b2c4d6f1a3_s3_incumbent_forecast_replay_identity.py
ALEMBIC_MIGRATION_BLOB=1e0864ebef1d947d4c9466d71efaa759d44c7ad7
UPGRADE_ROW_COUNT=0
~~~

Parent persistence-schema contract §§1–9 remain authoritative. Parent §3.1 states the frozen
name must not be treated as a bindable V0.2 SQL table name until separate bindable review
after the table truly exists. Parent §3.5 states `NO_BINDABLE_V0_2` remains true until that
separate review. This contract is that bindable review; it does not reopen parent §§1–9.

### 1.2 Parent SQL table-name authority contract

~~~text
PARENT_SQL_TABLE_AUTHORITY_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-sql-table-authority-contract.md
PARENT_SQL_TABLE_AUTHORITY_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=97c15064445d0ff4776884234994f0a10f6537d5
SQL_TABLE_AUTHORITY_CONTRACT_EVIDENCE_JSON_SHA256=99e4bb4853b6020404a86221c470936fce27f26bb6373fbe81167ffaeac6e260
SQL_TABLE_AUTHORITY_R1_EVIDENCE_JSON_SHA256=aad30ef4b0f6b16cbdab8aab4571f231e46758b138ab636d7b20208c55a39218
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
MATCH_TABLE_NAMES=()
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
~~~

The 106-row Alembic audit (snapshot at `2cfc2c0`) remains authoritative. `MATCH_TABLE_COUNT`
remains `0`. This contract does not add `s3_incumbent_forecast_replay_identity` to
`MATCH_TABLE_NAMES` and does not reclassify any audited table.

### 1.3 Parent postgres obtain contract

~~~text
PARENT_POSTGRES_OBTAIN_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-postgres-obtain-contract.md
PARENT_POSTGRES_OBTAIN_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c02ae702995c38f33ca73c3af26e8fdb33cc8e04
V0_2_POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
~~~

Parent postgres obtain contract §3.1: future implementation may bind only to
coordinator-reviewed frozen names already present in repository contracts; if none,
`obtain=()`. This contract introduces the reviewed bindable name freeze; it does not
implement obtain or live postgres read.

### 1.4 Inherited S2 binding

~~~text
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_PARTITION_DATES=2025-08-05..2026-01-30
TRAIN_ROW_COUNT=16224
VALIDATION_PARTITION_DATES=2026-01-31..2026-03-09
VALIDATION_ROW_COUNT=8006
TEST_PARTITION_DATES=2026-03-10..2026-04-16
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
DEFAULT_MONTH_SCOPE=1-4
FORBIDDEN_VARIETIES=普鲜,普青,普冻,废果
FORBIDDEN_FACTORY_BASON=true
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
CONTENT_IDENTITY_VERSION=v0-3-s3-a2-incumbent-forecast-artifact-content-identity-v1
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 2. Why this contract is the unique remaining gap

1. Schema R1 (#356) created empty table `s3_incumbent_forecast_replay_identity`; upgrade
   row count is 0.
2. Parent persistence-schema contract §3.1 and §3.5: table existence ≠ bindable; separate
   bindable review is required before any live-read path may reference the name.
3. The 106-row audit still has `MATCH_TABLE_COUNT=0`; the new table must not be added to
   `MATCH_TABLE_NAMES`; the 106 audit must not be reopened or reclassified.
4. Without a coordinator-reviewed bindable name, later live-read could invent SQL or
   mistakenly bind kg-bearing audited tables.
5. This contract reviews only whether the now-existing empty table may serve as the sole
   coordinator-reviewed bindable replay-identity table name for future live-read paths.
6. This contract does not implement live postgres read, does not populate rows, does not
   flip `NO_VERSIONED`, and does not change default `obtain=()`.
7. Empty harvest source remains the second blocker after forecast non-empty; this contract
   does not address S2 identity alignment.

Do not treat table existence as bindable implementation fact. Do not jump to live-read
contract in this merge.

## 3. Frozen bindable name review

### 3.1 Coordinator-reviewed bindable name

~~~text
FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME=s3_incumbent_forecast_replay_identity
FROZEN_BINDABLE_OBJECT_KIND=TABLE
FROZEN_BINDABLE_OBJECT_EXISTS_IN_ALEMBIC=true
FROZEN_BINDABLE_OBJECT_IS_NOT_ONE_OF_THE_106=true
FROZEN_BINDABLE_OBJECT_IS_NOT_ADDED_TO_MATCH_TABLE_NAMES=true
THIS_IS_NOT_RECLASSIFYING_THE_106=true
COORDINATOR_REVIEWED_BINDABLE_NAME_AFTER_TABLE_EXISTS=true
OBJECT_ROW_COUNT_AT_REVIEW=0
GRAIN=DISTINCT(forecast_cutoff_at,model_id,forecast_quantile)
REQUIRED_COLUMNS=forecast_cutoff_at,model_id,forecast_quantile
OPTIONAL_SURROGATE_PK_DOES_NOT_ENTER_GRAIN=true
NO_KG_COLUMNS=true
UNIQUE_ALEMBIC_HEAD=e8b2c4d6f1a3
~~~

This is a **name review** freeze: the existing empty table is the sole coordinator-reviewed
bindable replay-identity table name permitted for future live-read binding. It is not
live-read, not row population, and not a versioned incumbent forecast artifact.

### 3.2 Honest boundaries at contract merge

~~~text
BINDABLE_NAME_REVIEW_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
BINDABLE_NAME_REVIEW_DOES_NOT_POPULATE_ROWS=true
BINDABLE_NAME_REVIEW_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
EMPTY_BINDABLE_CANDIDATE_IS_NOT_VERSIONED_ARTIFACT=true
LATER_LIVE_READ_OF_EMPTY_TABLE_STILL_YIELDS_EMPTY_OBTAIN=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY_REMAINS_TRUE_AT_CONTRACT_MERGE=true
~~~

Even if a later bindable-name R1 records this name in deterministic code and flips
`NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY` to `false`, default `obtain()` remains `()`
until separate live-read contract + authorization + R1. Reading the empty table still
yields `()`. `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY` remains `true`.

### 3.3 What a later bindable-name R1 may do (not authorized here)

A later bindable-name implementation R1 (separate 「可以实施」 grant required) may:

1. Record this frozen name as the coordinator-reviewed bindable replay-identity table in
   deterministic code (limited edit to `incumbent_forecast_v0_2_sql_table_authority.py` or
   a new module).
2. Flip `DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED` to
   `true` and, as the same semantic act, flip
   `NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY` to `false`.

A later bindable-name R1 must **not**:

- Add the name to `MATCH_TABLE_NAMES` (106 audit set remains `()`).
- Implement live postgres read or write SELECT/FROM/JOIN/WHERE.
- Populate rows or change default `obtain()` from `()`.
- Flip `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED`.
- Flip `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY`.

This contract does not issue an implementation grant and does not authorize that R1.

## 4. Explicit non-scope (not authorized by this contract)

~~~text
CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_BINDABLE_NAME_ENCODING=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
CONTRACT_MERGE_DOES_NOT_POPULATE_ROWS=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_BINDABLE_V0_2=true
CONTRACT_MERGE_DOES_NOT_FLIP_LIVE_POSTGRES_READ=true
CONTRACT_MERGE_DOES_NOT_FLIP_AVAILABLE_OR_VERIFIED=true
CONTRACT_MERGE_DOES_NOT_UNSEAL_TEST=true
CONTRACT_MERGE_DOES_NOT_SOURCE_002_ROW_LEVEL_READ=true
CONTRACT_MERGE_DOES_NOT_ADDRESS_S2_ALIGNMENT=true
CONTRACT_MERGE_DOES_NOT_CLOSE_S3=true
FORBIDDEN_INVENT_SQL_OR_TABLE_NAMES=true
FORBIDDEN_INVENT_CONNECTION_STRINGS=true
FORBIDDEN_INVENT_CUTOFF_LISTS=true
FORBIDDEN_INVENT_TONNES_OR_KG=true
FORBIDDEN_RECLASSIFY_HARVEST_STATE_REPLAY_SOURCE_VISIBILITY_AUDIT=true
FORBIDDEN_BIND_CORE_FORECAST_DAILY_ROW=true
FORBIDDEN_BIND_ROLLING_BACKTEST_BINDING_ROW=true
FORBIDDEN_CHANGE_MATCH_TABLE_COUNT_FROM_106_AUDIT=true
FORBIDDEN_H7_FIXTURE_AS_LIVE_EVIDENCE_OR_CONTENT_IDENTITY=true
FORBIDDEN_REWRITE_ALIGNMENT_CONTRACT_SECTION_6_AUDIT=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
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
ALEMBIC_E8B2C4D6F1A3_BLOB=1e0864ebef1d947d4c9466d71efaa759d44c7ad7
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
TEST_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_PY_BLOB=fb46fa04bc5dea2145dc22927b162fb07d96b251
BOUND_FIXTURE_TEST_INJECTION_PATH_MUST_REMAIN=true
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
~~~

## 6. Forbidden inputs and substitutions

~~~text
FORBIDDEN_INVENT_SECOND_TABLE_NAME=true
FORBIDDEN_REPOSITORY_SCAN_FOR_SUBSTITUTES=true
FORBIDDEN_RAW_SOURCE_002_PRIMARY_READ=true
FORBIDDEN_H7_FIXTURE_AS_LIVE_EVIDENCE_OR_CONTENT_IDENTITY=true
FORBIDDEN_USE_HARVEST_BUSINESS_DATE_AS_FORECAST_CUTOFF=true
FORBIDDEN_REWRITE_ALIGNMENT_CONTRACT_SECTION_6=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
~~~

## 7. TEST seal and exclusion policy

~~~text
TEST_PARTITION_DATES=2026-03-10..2026-04-16
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
TEST_REMAINS_SEALED=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 8. LLM and deterministic service boundary

LLM agents organize explanation and invoke tools. Bindable table names, SQL, DSN,
connection strings, cutoff lists, identity hashes, row content, and tonnes must come
from deterministic service logic and coordinator-reviewed artifacts only. LLM must not
invent tonnes, SQL, table names beyond this freeze, DSNs, connection strings, cutoff
lists, identity hashes, or row payloads.

## 9. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT_AUTHORIZED=false → true
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTATION_AUTHORIZED=false (companion introduced; not flipped)
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED=false (companion introduced; not flipped)
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block and pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-identity-persistence-schema-contract.md` §12 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-sql-table-authority-contract.md` §15 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-harvest-source-contract.md` §18 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-producer-adapter-wiring-contract.md` §21 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-postgres-obtain-contract.md` §24 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-fail-closed-wiring-contract.md` §27 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-envelope-contract.md` §30 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md` §33 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md` §36 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` §39 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §48 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §64 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §47 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §52 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §53 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §56 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §41 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

Unchanged live flags retained:

~~~text
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
MATCH_TABLE_COUNT=0
AUDIT_TABLE_COUNT=106
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
FROZEN_FUTURE_OBJECT_EXISTS_IN_ALEMBIC=true
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
~~~
