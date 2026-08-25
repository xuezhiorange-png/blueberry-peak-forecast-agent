# V0.3-S3-A2 Incumbent forecast fail-closed wiring contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-incumbent-forecast-fail-closed-wiring-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_FAIL_CLOSED_WIRING
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=0bb5877c7c65b75361fe134765a8912788b947b3
BASE_MAIN_TREE_SHA=78a5473169e8dd1e75762bb252aa08b40bd3d295
CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-fail-closed-wiring-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-fail-closed-wiring-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-fail-closed-wiring-contract.json
EVIDENCE_JSON_SHA256=2ea44667836957fa736828cbd4ae123c5d2144a43918939ab4d494f4cbcaf1ff
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This workpaper records the S3-A2 **incumbent forecast fail-closed wiring**
contract freeze after live envelope R1 (#338). Envelope assignment is landed on
`IncumbentForecastArtifactContentProducer`; obtain→produce→adapter default wiring
is not. This contract freezes deterministic default-chain wiring behavior only.
It does **not** implement wiring, authorize V0.2 obtain, or flip `NO_VERSIONED` /
`AVAILABLE` / `VERIFIED`.

~~~text
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Why this contract (unique gap after #338)

1. Replay source default `obtain()`=`()`.
2. Content producer can assign envelope per parent §3; default `replay_rows=()` →
   `produce()`=`None`; default `declared_catalog_source_kind=BOUND_FIXTURE`.
3. Adapter default `artifact=None`; catalog `_default_forecast_artifact_port()` does
   not call `produce()`/`obtain()`.
4. Default catalog first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.
5. Circular import: replay source imports content projection; producer must not
   top-level import replay source.
6. Without wiring, future V0.2 obtain cannot reach default catalog path.

## 2. Upstream bindings (reference only)

~~~text
PARENT_PR=338
LIVE_ENVELOPE_R1_EVIDENCE_JSON_SHA256=164b2396091dc5b2daf790f09c92e9ebf628c6e577a37acdc6e4dc0c88b3e601
LIVE_ENVELOPE_AUTH_EVIDENCE_JSON_SHA256=86d6937c11783d1c95aa6da5de281b749c1272092b452383f2bc27b1c33544b5
LIVE_ENVELOPE_CONTRACT_EVIDENCE_JSON_SHA256=9b67eabc5ae01f5e834dda4d8321208198a4bef3ad3e1d5f6a3bdf2fe5ed27d4
LIVE_ENVELOPE_CONTRACT_GIT_BLOB_SHA=6121c5d5f02c2fa45b9c16b0c417ebb3d06e27fe
CONTENT_PRODUCER_PY_BLOB=12fdac5db326cd2105a12b24f18fcb37a7e75d63
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=070f54311f08a5c7758602fbe105e511fefd8eca
FORECAST_ARTIFACT_PY_BLOB=f928c6c9fa94e91e33c37edd8e9ab57c6e138480
CATALOG_ARTIFACT_PY_BLOB=968e841527b696d17364ddae11693fadb49462b8
TEST_INCUMBENT_FORECAST_LIVE_ENVELOPE_PY_BLOB=cf34f76c734388129b7dbf8d4f585bde584fceac
~~~

## 3. Repository audit (read-only at 0bb5877)

~~~text
ReplaySource default obtain()=()
ContentProducer default replay_rows=() → produce()=None
ContentProducer default declared_catalog_source_kind=BOUND_FIXTURE
ForecastAdapter default artifact=None
catalog _default_forecast_artifact_port → IncumbentForecastArtifactAdapter() bare
catalog default produce() first blocker=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
replay_source imports project_incumbent_forecast_artifact_entries from content producer
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 4. Default-chain wiring freeze (core)

| explicit `adapter.artifact` | explicit `producer.replay_rows` | `obtain()` | `harvest_as_cutoff` | default-path outcome |
|---|---|---|---|---|
| not `None` | any | any | false | injection wins; envelope per frozen envelope §3 |
| `None` | non-empty | any | false | if wired: producer result enters adapter; if unwired: `NO_VERSIONED` |
| `None` | empty | `()` | false | `produce()`=`None`; catalog=`NO_VERSIONED`; live kind prohibited |
| `None` | empty | non-empty | false | envelope only when future obtain implemented and wired; not authorized here |
| any | any | any | true | no envelope; harvest date not forecast cutoff |

### 4.1 Wiring priority

~~~text
INJECTION_WINS_OVER_EMPTY_OBTAIN=true
ADAPTER_USES_PRODUCER_PRODUCE_WHEN_WIRED=true
PRODUCER_REPLAY_ROWS_WIN_OVER_OBTAIN=true
EMPTY_OBTAIN_OR_HARVEST_CUTOFF_PRODUCE_NONE=true
DEFAULT_DECLARED_KIND_REMAINS_BOUND_FIXTURE=true
~~~

### 4.2 Circular-import constraint

~~~text
REPLAY_SOURCE_IMPORTS_CONTENT_PROJECTION=true
PRODUCER_MUST_NOT_TOP_LEVEL_IMPORT_REPLAY_SOURCE=true
CIRCULAR_IMPORT_AVOIDANCE_REQUIRED=true
~~~

## 5. What remains forbidden / not authorized

~~~text
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_WIRING=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED=false
FORBIDDEN_WIRE_ALIGNMENT_PRODUCER_IN_THIS_CONTRACT=true
FORBIDDEN_LIVE_BINDABLE_SUCCESS_ENUM=true
FORBIDDEN_FLIP_NO_VERSIONED=true
FORBIDDEN_V0_2_POSTGRES_OBTAIN=true
TEST_REMAINS_SEALED=true
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_BY_THIS_CONTRACT=true
FUTURE_TEST_PATH=backend/tests/s3_daily_rowset/test_incumbent_forecast_fail_closed_wiring.py
~~~

## 6. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_CONTRACT_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4
- twelve sibling contract pointer sections listed in contract §9

## 7. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_WIRING=true
AWAITING_COORDINATOR_REVIEW=true
~~~
