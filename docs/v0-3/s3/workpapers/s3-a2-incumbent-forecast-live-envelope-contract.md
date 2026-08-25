# V0.3-S3-A2 Incumbent forecast live envelope contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-incumbent-forecast-live-envelope-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_LIVE_ENVELOPE
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=e93474cf787b8ff2cd1eb96c5a202879585f8304
BASE_MAIN_TREE_SHA=7eba0765f28c2cc30e743897f96130983b9eb80b
CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-live-envelope-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-live-envelope-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-live-envelope-contract.json
EVIDENCE_JSON_SHA256=bec6560beac306018c909e49ccd0c44d1bd6cf1a22e5331b63834f1fdadef3f0
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This workpaper records the S3-A2 **incumbent forecast live envelope** contract
freeze after live source kind R1 (#335). Enum member
`CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF` is landed; content
producer still assigns `BOUND_FIXTURE` on every non-empty projection. This contract
freezes deterministic envelope `catalog_source_kind` assignment only. It does
**not** implement assignment logic, wire obtain→produce→adapter, write live
artifacts, or flip `NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.

~~~text
S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Why this contract (unique gap)

After #335:

1. Live enum landed (`registry.py` blob `ca16d518…`).
2. Replay source default `obtain()`=`()`.
3. Content producer non-empty `replay_rows` → envelope still `BOUND_FIXTURE`.
4. Adapter default `artifact=None` → `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.
5. Row tuples cannot infer live vs fixture alone.

Parent live source kind contract §6 named eligibility only; this contract
freezes assignment authority.

## 2. Upstream bindings (reference only)

~~~text
PR335_MERGE=e93474cf787b8ff2cd1eb96c5a202879585f8304
LIVE_SOURCE_KIND_CONTRACT_EVIDENCE_JSON_SHA256=2d0cce5d0c0f89c136014a2abbd01d67ef0004786c63050115d55a2dc0519ee1
LIVE_SOURCE_KIND_R1_EVIDENCE_JSON_SHA256=3a7a1f4f74074630c4eedb658ca361db579e16b1f7e4630f51b04266fa963a7a
LIVE_SOURCE_KIND_AUTH_EVIDENCE_JSON_SHA256=759644330a0063560f11e53a74a92b03dbb6221ab6c58f523a74462dc145fa9e
REPLAY_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=59e452eedc6b8db82063d11ccaf7af177447074c7ad68565b31a6d86d5d4b457
REPLAY_SOURCE_R1_EVIDENCE_JSON_SHA256=59a198c38c0c1e8e17a718bb5623943c4035b4b9b582e2216b922d526b508929
CONTENT_CONTRACT_EVIDENCE_JSON_SHA256=6294f2028509f2b1021741ac7aea3f20efdcbe07669b87a1782d18c0a5ca9eae
CONTENT_PRODUCER_R1_EVIDENCE_JSON_SHA256=d159c010b4f527972e7554789e85808ae48e11941499c6f597f124fd471ff228
REGISTRY_PY_BLOB=ca16d518ab18136059cd08bcf4b247774d750bb5
INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=18c1b1c8d66f2e8ae4476f24692f5ebeb85a9a95
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=070f54311f08a5c7758602fbe105e511fefd8eca
FORECAST_ARTIFACT_PY_BLOB=f928c6c9fa94e91e33c37edd8e9ab57c6e138480
CATALOG_ARTIFACT_PY_BLOB=968e841527b696d17364ddae11693fadb49462b8
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
~~~

## 3. Repository audit (read-only at e93474c)

~~~text
Registry: V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF landed; not forbidden; not alignment
ReplaySource default obtain()=()
ContentProducer default replay_rows=() → produce()=None
ContentProducer non-empty replay_rows → catalog_source_kind=BOUND_FIXTURE (hardcoded)
ForecastAdapter default artifact=None → NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
catalog produce() copies catalog_source_kind from forecast not alignment
BOUND_FIXTURE → FIXTURE_ONLY_CATALOG_NOT_BINDABLE
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 4. Envelope assignment scope summary

### 4.1 Assignment outcomes

~~~text
LIVE_ENVELOPE_KIND=CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
FIXTURE_ENVELOPE_KIND=CatalogSourceKind.BOUND_FIXTURE
FORBIDDEN_INFER_LIVE_KIND_FROM_ROW_TUPLE_ALONE=true
~~~

### 4.2 Live envelope eligibility (all required)

~~~text
NAMED_V0_2_REPLAY_AUTHORITY_REQUIRED=true
NON_EMPTY_POST_EXCLUSION_REPLAY_ROWS_REQUIRED=true
CONTENT_IDENTITY_COMPUTED_BY_LANDED_RECIPE_REQUIRED=true
EXPLICIT_LIVE_ASSIGNMENT_REQUIRED=true
~~~

### 4.3 Bindable catalog prerequisite

~~~text
LIVE_ENVELOPE_KIND_NECESSARY_BUT_NOT_SUFFICIENT_FOR_BINDABLE_CATALOG=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
~~~

## 5. What remains forbidden / not authorized

~~~text
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_ENVELOPE_ASSIGNMENT=true
CONTRACT_MERGE_DOES_NOT_WIRE_PRODUCER_OR_ADAPTER=true
CONTRACT_MERGE_DOES_NOT_MODIFY_REGISTRY_PY_ENUM=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED=false
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
TEST_REMAINS_SEALED=true
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_BY_THIS_CONTRACT=true
~~~

## 6. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4
- `docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md` §12 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md` §15 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` §18 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §27 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §43 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §26 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §31 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §32 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §35 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §20 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

## 7. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_ENVELOPE_ASSIGNMENT=true
CONTRACT_MERGE_DOES_NOT_WIRE_PRODUCER_OR_ADAPTER=true
AWAITING_COORDINATOR_REVIEW=true
~~~
