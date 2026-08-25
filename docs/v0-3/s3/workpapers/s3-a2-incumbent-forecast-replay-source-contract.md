# V0.3-S3-A2 Incumbent forecast replay source contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-incumbent-forecast-replay-source-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_ONLY
SLICE=V0.3-S3
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=499047101d71aedea4dcc39f8ec6413d5b72b93a
BASE_MAIN_TREE_SHA=a862d06e729a3a95f9cc55eeb08b8eb6178c7d86
CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-source-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-replay-source-contract.json
EVIDENCE_JSON_SHA256=59e452eedc6b8db82063d11ccaf7af177447074c7ad68565b31a6d86d5d4b457
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This workpaper records the S3-A2 **incumbent forecast replay source** contract
freeze after content producer R1 (#329). The landed
`IncumbentForecastArtifactContentProducer` projects caller-injected `replay_rows`
into `VersionedIncumbentForecastArtifact`; default `replay_rows=()` →
`produce()`=`None`. Parent content producer contract §§1–9 freeze how injected
rows become forecast artifact content; this contract defines how a future
deterministic replay source may obtain those rows from
`V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF` authority. It does **not**
implement a replay source, wire producer/adapter defaults, write live forecast
artifacts, produce catalogs, or flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE` /
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`.

~~~text
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Why this contract (unique gap)

Catalog `produce()` first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`
because:

1. Content producer only projects caller-injected `replay_rows`.
2. Forecast adapter default `artifact=None`.
3. Repository still has no live versioned incumbent forecast artifact.

This contract freezes replay-source authority only; it does not re-open content
producer contract §§1–9.

## 2. Upstream bindings (reference only)

~~~text
PR329_MERGE=499047101d71aedea4dcc39f8ec6413d5b72b93a
CONTENT_CONTRACT_EVIDENCE_JSON_SHA256=6294f2028509f2b1021741ac7aea3f20efdcbe07669b87a1782d18c0a5ca9eae
CONTENT_AUTH_EVIDENCE_JSON_SHA256=29a486d5fa04542404c6629509ee65ebdf3931c30cf758db643faf93cfd35a38
CONTENT_PRODUCER_R1_EVIDENCE_JSON_SHA256=d159c010b4f527972e7554789e85808ae48e11941499c6f597f124fd471ff228
FORECAST_CONTRACT_EVIDENCE_JSON_SHA256=8e19a623c6739abeb047768ef642281b86ac7f2d73ea35fcff83ae3165f40376
FORECAST_ADAPTER_R1_EVIDENCE_JSON_SHA256=31bb6d24cf4c398eeea86c18d2dece16b9e0ab6f704e9ab229eac5a363d296a0
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=18c1b1c8d66f2e8ae4476f24692f5ebeb85a9a95
FORECAST_ARTIFACT_PY_BLOB=f928c6c9fa94e91e33c37edd8e9ab57c6e138480
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
~~~

## 3. Repository audit (read-only at 4990471)

~~~text
ContentProducer default replay_rows=() → produce()=None
ContentProducer envelope catalog_source_kind=BOUND_FIXTURE (fixture-only)
ForecastAdapter default artifact=None → has_versioned_artifact=false
catalog produce() without injected artifact → NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 4. Replay source contract scope summary

### 4.1 Output grain

~~~text
IncumbentForecastArtifactEntry=model_id,forecast_cutoff_at,forecast_quantile
REPLAY_SOURCE_GRAIN=DISTINCT(forecast_cutoff_at,model_id,forecast_quantile)
INJECTION_TARGET=IncumbentForecastArtifactContentProducer.replay_rows
~~~

### 4.2 Authority layering

~~~text
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
FORECAST_ARTIFACT_REQUIRES_PIT_REPLAY_AT_HISTORICAL_CUTOFF=true
FORECAST_REPLAY_IS_NOT_MODEL_RETRAINING=true
CONTENT_IDENTITY_VERSION=v0-3-s3-a2-incumbent-forecast-artifact-content-identity-v1
~~~

## 5. What remains forbidden / not authorized

~~~text
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_REPLAY_SOURCE=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
CONTRACT_MERGE_DOES_NOT_WIRE_PRODUCER_OR_ADAPTER=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
TEST_REMAINS_SEALED=true
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_BY_THIS_CONTRACT=true
~~~

## 6. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` §12 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §21 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §37 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §20 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §25 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §26 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §29 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §14 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

## 7. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_REPLAY_SOURCE=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
AWAITING_COORDINATOR_REVIEW=true
~~~
