# V0.3-S3-A2 Incumbent forecast replay source implementation authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTATION_AUTHORIZATION
ARTIFACT_VERSION=s3-a2-incumbent-forecast-replay-source-authorization-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTATION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTATION_GRANT_ONLY
SLICE=V0.3-S3
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=195303f1a17473d58b0ea4cc773f3ee33f141f40
BASE_MAIN_TREE_SHA=5ac13ce05126f73ddd2a7f189e48d6311dc900e2
PARENT_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-source-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-replay-source-authorization.json
EVIDENCE_JSON_SHA256=601e06ac1d679d7fb165a481cc01c27dd01fdd68e5a0d9699098c214ba88c890
NO_STEP_IMPLIES_THE_NEXT=true
GRANT_ONLY=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_REPLAY_SOURCE=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
AUTHORIZATION_MERGE_DOES_NOT_WIRE_PRODUCER_OR_ADAPTER=true
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_BIND_CATALOG=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

The user authorized issuance of the S3-A2 **incumbent forecast replay source**
implementation grant after replay source contract freeze #330. This document
records what a **later** deterministic replay source R1 may do when the user
again says 「可以实施」. This PR does not implement a replay source, wire producer or
adapter defaults, write live forecast artifacts, produce catalogs, bind catalogs,
flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, authorize backtests, or claim
S3-B semantics verified.

This is **replay source** authorization only. `IncumbentForecastArtifactContentProducer`
(R1, #329) is already landed on main. Do not re-authorize the content producer or
forecast adapter consumer.

~~~text
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_IMPLEMENTATION_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Upstream bindings (reference only)

~~~text
PR330_MERGE=195303f1a17473d58b0ea4cc773f3ee33f141f40
REPLAY_SOURCE_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md
REPLAY_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=59e452eedc6b8db82063d11ccaf7af177447074c7ad68565b31a6d86d5d4b457
CONTENT_CONTRACT_EVIDENCE_JSON_SHA256=6294f2028509f2b1021741ac7aea3f20efdcbe07669b87a1782d18c0a5ca9eae
CONTENT_AUTH_EVIDENCE_JSON_SHA256=29a486d5fa04542404c6629509ee65ebdf3931c30cf758db643faf93cfd35a38
CONTENT_PRODUCER_R1_EVIDENCE_JSON_SHA256=d159c010b4f527972e7554789e85808ae48e11941499c6f597f124fd471ff228
FORECAST_ADAPTER_R1_EVIDENCE_JSON_SHA256=31bb6d24cf4c398eeea86c18d2dece16b9e0ab6f704e9ab229eac5a363d296a0
INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=18c1b1c8d66f2e8ae4476f24692f5ebeb85a9a95
FORECAST_ARTIFACT_PY_BLOB=f928c6c9fa94e91e33c37edd8e9ab57c6e138480
CATALOG_ARTIFACT_PY_BLOB=968e841527b696d17364ddae11693fadb49462b8
REGISTRY_PY_BLOB=d3d4dc77e6340786ddcca128eb02e0c1d898a502
TEST_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=11e23e247d6f90e8c7528a073b6e90c709f4a5cc
TEST_CATALOG_ARTIFACT_PY_BLOB=af59a9f1d291ab32eff23684aca477f0e4a852cd
TEST_FORECAST_ARTIFACT_PY_BLOB=2ae0036a46f6f0b2898a8fca3589041b9869c196
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
CONTENT_IDENTITY_VERSION=v0-3-s3-a2-incumbent-forecast-artifact-content-identity-v1
~~~

Evidence JSON self-hashes above are binding references, not whole-file
`sha256sum` values. Archived workpaper/evidence bodies are referenced only; not
rewritten by this authorization grant.

## 2. Inherited S2 and replay source contract authority (not reopened)

~~~text
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_PARTITION_DATES=2025-08-05..2026-01-30
VALIDATION_PARTITION_DATES=2026-01-31..2026-03-09
TEST_PARTITION_DATES=2026-03-10..2026-04-16
TRAIN_ROW_COUNT=16224
VALIDATION_ROW_COUNT=8006
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
FORECAST_ARTIFACT_REQUIRES_PIT_REPLAY_AT_HISTORICAL_CUTOFF=true
FORECAST_REPLAY_IS_NOT_MODEL_RETRAINING=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 3. What this authorization grants

A later deterministic incumbent forecast replay source may, under a separate user
「可以实施」 gate, deliver an in-memory service (PEP 420 namespace; no production
`__init__.py`; no Alembic; `IN_MEMORY_SERVICE_ONLY`) that obtains injectable replay
rows for the landed `IncumbentForecastArtifactContentProducer` as `replay_rows`.

### 3.1 Allowed file changes (future implementation only)

~~~text
NEW_BACKEND_APP_S3_DAILY_ROWSET_INCUMBENT_FORECAST_REPLAY_SOURCE_PY=true
NEW_BACKEND_TESTS_S3_DAILY_ROWSET_TEST_INCUMBENT_FORECAST_REPLAY_SOURCE_PY=true
CONTENT_PRODUCER_PY_MAY_ADD_REPLAY_SOURCE_PORT_AND_LAZY_DEFAULT_FACTORY_ONLY=true
FORBIDDEN_MODIFY_INCUMBENT_FORECAST_ARTIFACT_ADAPTER_PORT_SIGNATURE=true
FORBIDDEN_MODIFY_CATALOG_SOURCE_KIND_PROVENANCE=true
FORBIDDEN_MODIFY_CATALOG_ARTIFACT_PY=true
FORBIDDEN_MODIFY_FORECAST_ARTIFACT_PY=true
FORBIDDEN_MODIFY_REGISTRY_PY=true
FORBIDDEN_MODIFY_CONTENT_PRODUCER_PROJECTION_OR_HASH_RECIPE=true
FORBIDDEN_MODIFY_CONTENT_PRODUCER_BOUND_FIXTURE_ENVELOPE_DEFAULT=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
FORBIDDEN_TOUCH_TEST_FORECAST_ARTIFACT_PY=true
FORBIDDEN_TOUCH_TEST_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY=true
~~~

Future implementation may add:

- `backend/app/s3_daily_rowset/incumbent_forecast_replay_source.py`
- `backend/tests/s3_daily_rowset/test_incumbent_forecast_replay_source.py`

Limited optional wiring in `incumbent_forecast_artifact_content.py` only:

- replay source port / lazy `default_factory` only
- default empty `replay_rows` or `source.obtain()` empty tuple → `produce()`=`None`
- **must not** change content producer projection, hash recipe, or `BOUND_FIXTURE`
  envelope default
- **must not** change `IncumbentForecastArtifactAdapter` port signatures
- **must not** change `catalog_artifact.py`, `forecast_artifact.py`, or
  `registry.py` in this grant scope
- **must not** modify `produce()` copying `catalog_source_kind` from
  `forecast_source_kind`

### 3.2 Replay source semantics (future implementation only)

Output row type: `IncumbentForecastArtifactEntry` with fields
`model_id`, `forecast_cutoff_at`, `forecast_quantile` only.

Grain: `DISTINCT(forecast_cutoff_at, model_id, forecast_quantile)`.

The future replay source must:

1. Bind forecast authority `V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF`
   with visibility `SOURCE_002_IDFL_LABEL_SIDE` and PIT replay at historical
   cutoff; `FORECAST_REPLAY_IS_NOT_MODEL_RETRAINING=true`.
2. Obtain rows from the named incumbent replay authority; forbid handwritten
   cutoff, farm, or cell lists; forbid inventing V0.2 table names or SQL.
3. Set `harvest_business_date` is **not** `forecast_cutoff`; if harvest date is
   treated as cutoff → empty tuple.
4. Output must not carry kg/tonnes, daily curves, catalog cells, or alignment
   identities.
5. Fail closed on missing projection → empty tuple; do not invent rows or
   distinct entry counts.
6. Post-exclusion emptiness must not be labeled with live forecast source kind.
7. Exclude TEST partition: cutoff or horizon windows 7/14/21 intersecting
   `2026-03-10..2026-04-16` must be excluded (same prohibition as
   `_entry_intersects_test_partition`).
8. Default months 1–4; exclude 普鲜/普青/普冻/废果 and 巴松/巴松加工厂.
9. Not read raw SOURCE_002 as primary input; not use S2 harvest grain as forecast
   cutoff primary source.
10. Not log sensitive full-row business data.
11. Not invent `content_identity_sha256` (remains computed by landed content
    producer using `v0-3-s3-a2-incumbent-forecast-artifact-content-identity-v1`).
12. Forbid H7 fixture
    `8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18` as live
    evidence or content identity.
13. Tests may inject synthetic rows; test hashes must not be claimed as live
    SOURCE_002 or repository content identity.

#### 3.2.1 Authorization clarification for `REPLAY_SOURCE_DOES_NOT_READ_REPOSITORY_FOR_ROWS`

Parent replay source contract §2.2 sets
`REPLAY_SOURCE_DOES_NOT_READ_REPOSITORY_FOR_ROWS=true`. This grant clarifies for
future R1:

- **Forbidden:** git/repository scan for substitute rows; treating SOURCE_002
  harvest grain as forecast cutoff primary source; handwritten lists.
- **Permitted:** obtaining `DISTINCT(forecast_cutoff_at, model_id,
  forecast_quantile)` rows from the named authority
  `V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF` with IDFL label-side PIT
  replay at historical cutoff.
- **Default:** no live V0.2 binding at construction → empty tuple → producer
  `produce()`=`None` → `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY`
  remains true.

#### 3.2.2 Forbidden substitutions

~~~text
FORBIDDEN_SUBSTITUTION_INCUMBENT_DAILY_CURVE_PROVIDER=true
FORBIDDEN_SUBSTITUTION_SPARSE_HORIZON_BINDING_FORECAST_PROVIDER=true
FORBIDDEN_SUBSTITUTION_S3_BINDING_ROW=true
FORBIDDEN_SUBSTITUTION_S2_HARVEST_GRAIN=true
FORBIDDEN_SUBSTITUTION_H7_FIXTURE=true
FORBIDDEN_SUBSTITUTION_REPOSITORY_SCAN=true
BOUND_FIXTURE_IS_NOT_LIVE_FORECAST_AUTHORITY=true
~~~

`CatalogSourceKind` enum changes remain forbidden in this grant and in future
R1. `LIVE_FORECAST_SOURCE_KIND_CANDIDATE=V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF`
is named only.

The only implementation-status flip permitted by a future implementation PR is:

~~~text
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=false → true
~~~

### 3.3 Forbidden in future implementation

~~~text
IMPLEMENTATION_PR_MAY_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_PR_MAY_NOT_FLIP_COMPLETENESS_VERIFIED=true
IMPLEMENTATION_PR_MAY_NOT_WRITE_LIVE_FORECAST_ARTIFACT_TO_REPOSITORY=true
IMPLEMENTATION_PR_MAY_NOT_PRODUCE_BINDABLE_CATALOG=true
IMPLEMENTATION_PR_MAY_NOT_FLIP_NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
IMPLEMENTATION_PR_MAY_NOT_MODIFY_CATALOG_SOURCE_KIND_ENUM=true
FORBIDDEN_INVENT_CUTOFF_LISTS=true
FORBIDDEN_INVENT_FARM_LISTS=true
FORBIDDEN_INVENT_CELL_ROWS=true
FORBIDDEN_INVENT_CONTENT_IDENTITY_SHA256=true
FORBIDDEN_INVENT_DISTINCT_ENTRY_COUNTS=true
FORBIDDEN_NEW_ALEMBIC=true
UNIQUE_ALEMBIC_HEAD=a7c3e9f1b2d4
FORBIDDEN_V0_2_POSTGRES_CONCURRENCY_CANARY_FLAKY_TESTS=true
~~~

## 4. What remains forbidden / not authorized

~~~text
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=NOT_PERFORMED
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
TEST_REMAINS_SEALED=true
CURRENT_V0_3_S3_COMPLETE=false
V0_3_S4_AUTHORIZED=false
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
ALLOWLIST_EXPANSION_AUTHORIZED=false
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 5. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTATION_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4
- `docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md` §10 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` §13 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §22 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §38 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §21 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §26 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §27 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §30 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §15 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

Unchanged live flags retained:

~~~text
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=false
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
~~~

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_REPLAY_SOURCE=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
AWAITING_COORDINATOR_REVIEW=true
~~~
