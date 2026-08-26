# V0.3-S3-A2 Incumbent forecast replay-identity persistence schema contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-incumbent-forecast-replay-identity-persistence-schema-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=694e41b1097afb7e608c07eedbf08323103a952a
BASE_MAIN_TREE_SHA=57f4383178e9b762922b4bd486614fda39d8ba2a
CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-replay-identity-persistence-schema-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-identity-persistence-schema-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-replay-identity-persistence-schema-contract.json
EVIDENCE_JSON_SHA256=b0c2553f3a561bf8c46b39f015a604f31f9c6a9c5d682a060ad5eff0dfbfb806
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_DRAFT_IS_NOT_READY=true
~~~

This workpaper records the S3-A2 **incumbent forecast replay-identity persistence schema**
contract freeze after SQL table-name authority R1 (#353). Default obtain remains `()`.
This contract freezes a future Alembic table name and replay-grain column semantics only.
It does **not** add Alembic, implement schema, issue grants, execute R1, or flip
`NO_VERSIONED` / `NO_LIVE_S2` / `AVAILABLE` / `VERIFIED`.

~~~text
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED=false
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
FROZEN_FUTURE_OBJECT_NAME=s3_incumbent_forecast_replay_identity
FROZEN_FUTURE_OBJECT_EXISTS_IN_ALEMBIC=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Why this contract (unique gap after #353)

1. SQL table-name authority R1 encoded `MATCH_TABLE_COUNT=0`; default obtain still `()`.
2. All 106 existing tables remain `NOT_MATCH`; kg tables must not bind.
3. Without a coordinator-reviewed future persistence object, later live-read could invent SQL.
4. This contract freezes only `s3_incumbent_forecast_replay_identity` and grain columns.
5. Empty harvest source remains a separate blocker; this contract does not address S2.
6. This contract does not flip `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY`.

## 2. Upstream bindings (reference only)

~~~text
PARENT_SQL_TABLE_AUTHORITY_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-sql-table-authority-contract.md
PARENT_SQL_TABLE_AUTHORITY_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=97c15064445d0ff4776884234994f0a10f6537d5
SQL_TABLE_AUTHORITY_CONTRACT_EVIDENCE_JSON_SHA256=99e4bb4853b6020404a86221c470936fce27f26bb6373fbe81167ffaeac6e260
SQL_TABLE_AUTHORITY_R1_EVIDENCE_JSON_SHA256=aad30ef4b0f6b16cbdab8aab4571f231e46758b138ab636d7b20208c55a39218
PARENT_POSTGRES_OBTAIN_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c02ae702995c38f33ca73c3af26e8fdb33cc8e04
V0_2_POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
REPLAY_SOURCE_GRAIN=DISTINCT(forecast_cutoff_at,model_id,forecast_quantile)
UNIQUE_ALEMBIC_HEAD=a7c3e9f1b2d4
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
~~~

## 3. Future object summary

| field | frozen value |
|---|---|
| object name | `s3_incumbent_forecast_replay_identity` |
| object kind | `TABLE` |
| exists in Alembic at freeze | `false` |
| one of audited 106 | `false` |
| added to `MATCH_TABLE_NAMES` | `false` |
| required columns | `forecast_cutoff_at`, `model_id`, `forecast_quantile` |
| grain uniqueness | unique on triple |
| optional surrogate PK | allowed; must not replace grain uniqueness |
| forbidden payloads | kg/tonnes/weight/quantity/forecast_value/daily curve/harvest date/alignment/catalog cell |

## 4. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_AUTHORIZED=false → true
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED=false (companion)
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTATION_AUTHORIZED=false (companion)
~~~

## 5. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
CONTRACT_MERGE_DOES_NOT_ADD_ALEMBIC=true
CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true
AWAITING_COORDINATOR_REVIEW=true
~~~
