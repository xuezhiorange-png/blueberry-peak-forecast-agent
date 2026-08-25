# V0.3-S3-A2 Incumbent forecast V0.2 postgres obtain contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-incumbent-forecast-v0-2-postgres-obtain-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=40f779d6464b368b6429a9430e8a777695380e1b
BASE_MAIN_TREE_SHA=98d84b0338f5177c3a5a535c7ac2b12558be0596
CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-postgres-obtain-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-postgres-obtain-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-postgres-obtain-contract.json
EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This workpaper records the S3-A2 **incumbent forecast V0.2 postgres obtain**
contract freeze after fail-closed wiring R1 (#341). obtain→produce→adapter default
chain is landed; default `obtain()` on empty `replay_rows` remains `()`. This
contract freezes the only permitted future empty-default obtain authority path.
It does **not** implement postgres reading, invent SQL/table names, or flip
`NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
FORBIDDEN_INVENT_SQL_OR_TABLE_NAMES=true
~~~

## 1. Why this contract (unique gap after #341)

1. Wiring R1 landed obtain→produce→adapter defaults.
2. `obtain()` still returns `()` for empty `replay_rows` when `harvest_as_cutoff=false`.
3. Default catalog first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.
4. Wiring contract/authorization/R1 explicitly excluded V0.2 postgres obtain.
5. This contract freezes named authority and fail-closed priority without inventing SQL.

## 2. Upstream bindings (reference only)

~~~text
PARENT_PR=341
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
FAIL_CLOSED_WIRING_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=84c4491daefa59f74d875f7b311612efbead4143688b5582c499981fe82210e0
FAIL_CLOSED_WIRING_CONTRACT_EVIDENCE_JSON_SHA256=2ea44667836957fa736828cbd4ae123c5d2144a43918939ab4d494f4cbcaf1ff
LIVE_ENVELOPE_R1_EVIDENCE_JSON_SHA256=164b2396091dc5b2daf790f09c92e9ebf628c6e577a37acdc6e4dc0c88b3e601
LIVE_ENVELOPE_CONTRACT_EVIDENCE_JSON_SHA256=9b67eabc5ae01f5e834dda4d8321208198a4bef3ad3e1d5f6a3bdf2fe5ed27d4
REPLAY_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=59e452eedc6b8db82063d11ccaf7af177447074c7ad68565b31a6d86d5d4b457
REPLAY_SOURCE_R1_EVIDENCE_JSON_SHA256=59a198c38c0c1e8e17a718bb5623943c4035b4b9b582e2216b922d526b508929
CONTENT_IDENTITY_VERSION=v0-3-s3-a2-incumbent-forecast-artifact-content-identity-v1
FORECAST_ARTIFACT_PY_BLOB=73e65fbe6774ef555f825efc74c9c8eb5f003575
INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=0cc05fff3deff00d279070aa246f241ff3754e89
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=070f54311f08a5c7758602fbe105e511fefd8eca
~~~

## 3. Repository audit (read-only at 40f779d)

~~~text
Wiring R1: obtain→produce→adapter defaults landed
ReplaySource obtain(): harvest_as_cutoff → (); empty replay_rows → (); non-empty → project
Default obtain() still ()
Default catalog produce() first blocker=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 4. Empty-default obtain priority (core)

| priority | condition | outcome |
|---|---|---|
| 1 | `harvest_as_cutoff=true` | `()`; no postgres |
| 2 | explicit non-empty `replay_rows` | projection; no postgres |
| 3 | explicit empty `replay_rows`, `harvest_as_cutoff=false` | future R1 may attempt V0.2 postgres obtain; not implemented here |
| 4 | missing/unreadable/ambiguous/unauthorized/excluded-empty | `()` |
| 5 | empty result | no live kind; no versioned artifact claim |
| 6 | non-empty result | landed wiring + frozen envelope table |
| 7 | empty obtain default | catalog `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT` |

### 4.1 Named authority (no SQL in this contract)

~~~text
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
REPLAY_SOURCE_GRAIN=DISTINCT(forecast_cutoff_at,model_id,forecast_quantile)
FORBIDDEN_INVENT_SQL_OR_TABLE_NAMES=true
FORBIDDEN_REPOSITORY_SCAN_FOR_SUBSTITUTES=true
~~~

## 5. What remains forbidden / not authorized

~~~text
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_V0_2_POSTGRES_OBTAIN=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED=false
FORBIDDEN_WIRE_ALIGNMENT_PRODUCER_IN_THIS_CONTRACT=true
FORBIDDEN_LIVE_BINDABLE_SUCCESS_ENUM=true
FORBIDDEN_FLIP_NO_VERSIONED=true
TEST_REMAINS_SEALED=true
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_BY_THIS_CONTRACT=true
FUTURE_TEST_PATH=backend/tests/s3_daily_rowset/test_incumbent_forecast_v0_2_postgres_obtain.py
~~~

## 6. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4
- thirteen sibling contract pointer sections listed in contract §9

## 7. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_V0_2_POSTGRES_OBTAIN=true
AWAITING_COORDINATOR_REVIEW=true
~~~
