# V0.3-S3-A2 Incumbent forecast artifact content contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-incumbent-forecast-artifact-content-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_ONLY
SLICE=V0.3-S3
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=1c1bd24fbe5e1d46277166fddbee666e86999df1
BASE_MAIN_TREE_SHA=32a58fd49f606d8b23f4228855aefbbd6eb7ca5c
CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-content-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-content-contract.json
EVIDENCE_JSON_SHA256=6294f2028509f2b1021741ac7aea3f20efdcbe07669b87a1782d18c0a5ca9eae
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This workpaper records the S3-A2 **incumbent forecast artifact content producer**
contract freeze after forecast adapter R1 (#319), alignment adapter R1 (#323),
and accepted S2 identity alignment evidence producer R1 (#326). The landed
`IncumbentForecastArtifactAdapter` consumes caller-injected
`VersionedIncumbentForecastArtifact` only; default construction remains
fail-closed. Parent contract `s3-incumbent-forecast-artifact-contract.md` §§1–8
freeze artifact identification and adapter ports; this contract defines how a
future deterministic producer may construct forecast **content** for injection.
It does **not** implement a producer, write live forecast artifacts, produce
catalogs, or flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE` /
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`.

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Upstream bindings (reference only)

~~~text
PR324_MERGE=944fd9c17904a16ce965dbff13dab5045b71e6ee
INCUMBENT_FORECAST_ARTIFACT_CONTRACT_EVIDENCE_JSON_SHA256=8e19a623c6739abeb047768ef642281b86ac7f2d73ea35fcff83ae3165f40376
INCUMBENT_FORECAST_ARTIFACT_ADAPTER_R1_EVIDENCE_JSON_SHA256=31bb6d24cf4c398eeea86c18d2dece16b9e0ab6f704e9ab229eac5a363d296a0
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
FORECAST_ARTIFACT_PY_BLOB=f928c6c9fa94e91e33c37edd8e9ab57c6e138480
CATALOG_ARTIFACT_PY_BLOB=968e841527b696d17364ddae11693fadb49462b8
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
~~~

## 2. Repository audit (read-only at 1c1bd24)

~~~text
IncumbentForecastArtifactAdapter default artifact=None → has_versioned_artifact=false
produce() without injected artifact → NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
catalog_artifact.produce() copies catalog_source_kind from forecast_source_kind
default forecast BOUND_FIXTURE → FIXTURE_ONLY_CATALOG_NOT_BINDABLE may persist
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 3. Content producer contract scope summary

### 3.1 Entry and envelope

~~~text
VersionedIncumbentForecastArtifact
IncumbentForecastArtifactEntry=model_id,forecast_cutoff_at,forecast_quantile
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
USES_HARVEST_DATE_AS_FORECAST_CUTOFF_MUST_BE_FALSE=true
CONTENT_IDENTITY_SHA256_MUST_BE_COMPUTED_FROM_REAL_ROWS_IN_FUTURE_IMPL=true
FORBIDDEN_INVENT_CONTENT_IDENTITY_SHA256=true
~~~

### 3.2 Distinction from parent contract and adapter

~~~text
THIS_IS_CONTENT_PRODUCER_CONTRACT=true
PARENT_FORECAST_CONTRACT_IS_ADAPTER_AND_ACCEPTANCE_CONTRACT=true
PARENT_CONTRACT_SECTIONS_1_8_NOT_REWRITTEN=true
FORECAST_ADAPTER_R1_ALREADY_LANDED=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

## 4. What remains forbidden / not authorized

~~~text
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_CONTENT_PRODUCER=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
TEST_REMAINS_SEALED=true
CURRENT_V0_3_S3_COMPLETE=false
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_BY_THIS_CONTRACT=true
~~~

## 5. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §18 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §34 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §17 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §22 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §23 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §26 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §11 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_CONTENT_PRODUCER=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
AWAITING_COORDINATOR_REVIEW=true
~~~
