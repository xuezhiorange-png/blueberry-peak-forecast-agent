# V0.3-S3-A2 Incumbent forecast live source kind contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-incumbent-forecast-live-source-kind-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT_ONLY
SLICE=V0.3-S3
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=b499ad88e6dfba9c01cdefae1341eb0fda8f6ade
BASE_MAIN_TREE_SHA=5b02ffb814c56118d0de4471a07ce7749a694e7c
CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-live-source-kind-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-live-source-kind-contract.json
EVIDENCE_JSON_SHA256=2d0cce5d0c0f89c136014a2abbd01d67ef0004786c63050115d55a2dc0519ee1
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This workpaper records the S3-A2 **incumbent forecast live source kind** contract
freeze after replay source R1 (#332). Replay source contract §§1–9 and content
producer contract §§1–9 already freeze obtain/produce authority and name
`LIVE_FORECAST_SOURCE_KIND_CANDIDATE` only. This contract closes the remaining
gap: when live forecast `catalog_source_kind` may be claimed, which kinds must
never impersonate it, and why live kind is necessary but not sufficient for
bindable catalog. It does **not** implement code, modify `registry.py`, write
live forecast artifacts, or flip `NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.

~~~text
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Why this contract (unique gap)

Catalog `produce()` first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`
because:

1. Replay source R1 landed; default `obtain()`=`()`.
2. Content producer R1 landed; default `replay_rows=()` → `produce()`=`None`;
   envelope `catalog_source_kind=BOUND_FIXTURE`.
3. Forecast adapter default `artifact=None`.
4. `CatalogSourceKind` has no `V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF` member.
5. Parent contracts name candidate only; no live `BINDABLE` success path.

## 2. Upstream bindings (reference only)

~~~text
PR332_MERGE=b499ad88e6dfba9c01cdefae1341eb0fda8f6ade
REPLAY_SOURCE_CONTRACT_GIT_BLOB_SHA=f26a3443d7f6e40fcb533e32dfcdd517a04cf3bf
REPLAY_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=59e452eedc6b8db82063d11ccaf7af177447074c7ad68565b31a6d86d5d4b457
REPLAY_SOURCE_R1_EVIDENCE_JSON_SHA256=59a198c38c0c1e8e17a718bb5623943c4035b4b9b582e2216b922d526b508929
CONTENT_PRODUCER_CONTRACT_GIT_BLOB_SHA=9a1e58958f6cd7e09b34371293f3f8d3b94a7dee
CONTENT_CONTRACT_EVIDENCE_JSON_SHA256=6294f2028509f2b1021741ac7aea3f20efdcbe07669b87a1782d18c0a5ca9eae
CONTENT_PRODUCER_R1_EVIDENCE_JSON_SHA256=d159c010b4f527972e7554789e85808ae48e11941499c6f597f124fd471ff228
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=070f54311f08a5c7758602fbe105e511fefd8eca
INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=18c1b1c8d66f2e8ae4476f24692f5ebeb85a9a95
FORECAST_ARTIFACT_PY_BLOB=f928c6c9fa94e91e33c37edd8e9ab57c6e138480
CATALOG_ARTIFACT_PY_BLOB=968e841527b696d17364ddae11693fadb49462b8
REGISTRY_PY_BLOB=d3d4dc77e6340786ddcca128eb02e0c1d898a502
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
~~~

## 3. Repository audit (read-only at b499ad8)

~~~text
ReplaySource default obtain()=()
ContentProducer default replay_rows=() → produce()=None
ContentProducer envelope catalog_source_kind=BOUND_FIXTURE (fixture-only)
ForecastAdapter default artifact=None → has_versioned_artifact=false
catalog produce() without injected artifact → NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 4. Live source kind contract scope summary

### 4.1 Authoritative live kind

~~~text
LIVE_FORECAST_SOURCE_KIND=V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
ONLY_THIS_KIND_MAY_BE_LIVE_FORECAST_CATALOG_SOURCE_KIND=true
THIS_CONTRACT_DOES_NOT_MODIFY_REGISTRY_PY_ENUM=true
~~~

### 4.2 Non-live and alignment kinds

~~~text
BOUND_FIXTURE_IS_NOT_LIVE_FORECAST_SOURCE_KIND=true
UNBOUND_IS_NOT_LIVE_FORECAST_SOURCE_KIND=true
FORBIDDEN_CATALOG_SOURCE_KINDS_ARE_NOT_LIVE_FORECAST_SOURCE_KINDS=true
SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT_IS_ALIGNMENT_KIND_ONLY=true
CATALOG_PRODUCE_COPIES_CATALOG_SOURCE_KIND_FROM_FORECAST_NOT_ALIGNMENT=true
~~~

### 4.3 Bindable catalog prerequisite

~~~text
LIVE_FORECAST_SOURCE_KIND_NECESSARY_BUT_NOT_SUFFICIENT_FOR_BINDABLE_CATALOG=true
BOUND_FIXTURE_YIELDS_FIXTURE_ONLY_CATALOG_NOT_BINDABLE=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
~~~

## 5. What remains forbidden / not authorized

~~~text
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_SOURCE_KIND=true
CONTRACT_MERGE_DOES_NOT_MODIFY_REGISTRY_PY_ENUM=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
CONTRACT_MERGE_DOES_NOT_WIRE_PRODUCER_OR_ADAPTER=true
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED=false
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
TEST_REMAINS_SEALED=true
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_BY_THIS_CONTRACT=true
~~~

## 6. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4
- `docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md` §12 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` §15 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §24 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §40 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §23 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §28 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §29 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §32 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §17 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

## 7. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_SOURCE_KIND=true
CONTRACT_MERGE_DOES_NOT_MODIFY_REGISTRY_PY_ENUM=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
AWAITING_COORDINATOR_REVIEW=true
~~~
