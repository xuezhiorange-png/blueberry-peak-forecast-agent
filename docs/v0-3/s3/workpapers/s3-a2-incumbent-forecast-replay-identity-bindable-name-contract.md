# V0.3-S3-A2 Incumbent forecast replay-identity bindable name contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-incumbent-forecast-replay-identity-bindable-name-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=67f436fe47003c015e868b0a04fe2b9409490bf5
BASE_MAIN_TREE_SHA=f00e50503b272f1201ad8cc139144f8e7aa48c4e
CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-replay-identity-bindable-name-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-identity-bindable-name-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-replay-identity-bindable-name-contract.json
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_PR_IS_NOT_R1=true
THIS_PR_IS_NOT_A_GRANT=true
THIS_DRAFT_IS_NOT_READY=true
~~~

This workpaper records the S3-A2 **incumbent forecast replay-identity bindable name**
contract freeze after schema R1 (#356). Schema R1 created empty Alembic table
`s3_incumbent_forecast_replay_identity` with 0 upgrade rows. This contract reviews whether
that existing empty table may serve as the sole coordinator-reviewed bindable
replay-identity table name for future live-read paths. It does **not** implement
bindable-name encoding, issue grants, execute R1, implement live postgres read, populate
rows, or flip `NO_VERSIONED` / `NO_BINDABLE_V0_2` / `LIVE_POSTGRES_READ`.

~~~text
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME=s3_incumbent_forecast_replay_identity
FROZEN_BINDABLE_OBJECT_EXISTS_IN_ALEMBIC=true
OBJECT_ROW_COUNT_AT_REVIEW=0
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Why this contract (unique gap after schema R1)

1. Schema R1 (#356) created empty table `s3_incumbent_forecast_replay_identity`; upgrade
   row count is 0.
2. Parent persistence-schema contract §3.1 and §3.5: existence ≠ bindable; separate
   bindable review required.
3. 106-row audit still `MATCH_TABLE_COUNT=0`; new table must not join `MATCH_TABLE_NAMES`.
4. Without reviewed bindable name, later live-read could invent SQL or bind kg tables.
5. This contract reviews only the now-existing empty table as future bindable name.
6. Does not implement live-read, populate rows, flip `NO_VERSIONED`, or change `obtain()`.
7. Empty harvest source remains separate blocker; does not address S2 alignment.

## 2. Upstream bindings (reference only)

~~~text
PARENT_PERSISTENCE_SCHEMA_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-replay-identity-persistence-schema-contract.md
PARENT_PERSISTENCE_SCHEMA_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=a7cf5abfed864fb95ab2f870c422a0f7caaf97fd
SCHEMA_CONTRACT_EVIDENCE_JSON_SHA256=b0c2553f3a561bf8c46b39f015a604f31f9c6a9c5d682a060ad5eff0dfbfb806
SCHEMA_GRANT_EVIDENCE_JSON_SHA256=f58fa58c9f3e815c2a987903d1ec4f2ef6818008cba966c57b1b9ccfafdf6e01
SCHEMA_R1_EVIDENCE_JSON_SHA256=921df3fd317213eeaf44fe594e72650ac7dea84d8499ca915c5f627fe60e3599
PARENT_SQL_TABLE_AUTHORITY_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=97c15064445d0ff4776884234994f0a10f6537d5
SQL_TABLE_AUTHORITY_R1_EVIDENCE_JSON_SHA256=aad30ef4b0f6b16cbdab8aab4571f231e46758b138ab636d7b20208c55a39218
PARENT_POSTGRES_OBTAIN_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c02ae702995c38f33ca73c3af26e8fdb33cc8e04
ALEMBIC_REVISION=e8b2c4d6f1a3
UNIQUE_ALEMBIC_HEAD=e8b2c4d6f1a3
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
~~~

## 3. Frozen bindable name summary

| field | frozen value |
|---|---|
| bindable table name | `s3_incumbent_forecast_replay_identity` |
| object kind | `TABLE` |
| exists in Alembic | `true` |
| one of audited 106 | `false` |
| added to `MATCH_TABLE_NAMES` | `false` |
| row count at review | `0` |
| grain | `DISTINCT(forecast_cutoff_at,model_id,forecast_quantile)` |
| required columns | `forecast_cutoff_at`, `model_id`, `forecast_quantile` |
| kg columns | forbidden |

## 4. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT_AUTHORIZED=false → true
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTATION_AUTHORIZED=false (companion)
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED=false (companion)
~~~

## 5. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_BINDABLE_NAME_ENCODING=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_BINDABLE_V0_2=true
CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true
AWAITING_COORDINATOR_REVIEW=true
~~~
