# V0.3-S3-A2 Incumbent forecast V0.2 live postgres read contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-incumbent-forecast-v0-2-live-postgres-read-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=5ff9c2f8d52e3c8878b9b23c3c6a51a782c8cbcf
BASE_MAIN_TREE_SHA=c3196781bcfffa86e5e6b9169924c471bf84bee2
CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-live-postgres-read-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-live-postgres-read-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-live-postgres-read-contract.json
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_PR_IS_NOT_R1=true
THIS_PR_IS_NOT_A_GRANT=true
THIS_DRAFT_IS_NOT_READY=true
~~~

This workpaper records the S3-A2 **incumbent forecast V0.2 live postgres read** contract
freeze after bindable-name R1 (#359). Bindable-name R1 encoded frozen name
`s3_incumbent_forecast_replay_identity`; `bindable_table_names()` returns that 1-tuple;
`NO_BINDABLE_V0_2=false`. `IncumbentForecastReplaySource._empty_v0_2_postgres_obtain`
still returns `()` after consulting non-empty bindable names. This contract freezes
live-read authority for that encoded name only. It does **not** implement live-read, issue
grants, execute R1, populate rows, or flip `NO_VERSIONED` / `LIVE_POSTGRES_READ_IMPLEMENTED`.

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=false
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
FROZEN_LIVE_READ_BINDABLE_TABLE_NAME=s3_incumbent_forecast_replay_identity
OBJECT_ROW_COUNT_AT_REVIEW=0
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Why this contract (unique gap after bindable-name R1)

1. Bindable-name R1 encoded frozen name; `bindable_table_names()` non-empty;
   `NO_BINDABLE_V0_2=false`.
2. `_empty_v0_2_postgres_obtain` consults bindable names, then still returns `()`.
3. That second empty return is the unique remaining code gap; not live postgres read.
4. Empty Alembic table still 0 rows; later live-read of empty table still yields `()`.
5. Catalog first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.
6. Parent obtain §3.1: coordinator-reviewed frozen name now exists in repository contracts.
7. Does not implement read, populate rows, flip `NO_VERSIONED`, or close S3.

## 2. Upstream bindings (reference only)

~~~text
PARENT_BINDABLE_NAME_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=402942dd80a14299db263227e60d4a590b786f76
BINDABLE_NAME_R1_EVIDENCE_JSON_SHA256=121d677c6645f87162a0108649f73aec1e825f1901148170d55179f9aa17543d
PARENT_POSTGRES_OBTAIN_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c02ae702995c38f33ca73c3af26e8fdb33cc8e04
V0_2_POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_PY_BLOB=ac840d2e46836427baaec3e46b0d111eda4adf74
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=9ffb7bdf9beb1d897b8a1752f06de9250011cf15
ALEMBIC_REVISION=e8b2c4d6f1a3
UNIQUE_ALEMBIC_HEAD=e8b2c4d6f1a3
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
~~~

## 3. Frozen live-read authority summary

| field | frozen value |
|---|---|
| live-read bindable table | `s3_incumbent_forecast_replay_identity` |
| object kind | `TABLE` |
| exists in Alembic | `true` |
| row count at review | `0` |
| grain | `DISTINCT(forecast_cutoff_at,model_id,forecast_quantile)` |
| projection columns | `forecast_cutoff_at`, `model_id`, `forecast_quantile` |
| obtain default | fail-closed `()` until live-read R1 |

## 4. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_CONTRACT_AUTHORIZED=false → true
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTATION_AUTHORIZED=false (companion)
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false (companion)
~~~

## 5. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=3009c0ed24d35dadcb717d31e62767662ed36a6f7b238d36e2360854ab51b58d
~~~

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
