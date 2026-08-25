# V0.3-S3-A2 Incumbent Forecast Artifact Content Contract

## Contract identity and phase boundary

~~~text
CONTRACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT
CONTRACT_VERSION=v0-3-s3-a2-incumbent-forecast-artifact-content-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER
USER_GATE=可以下一步
CONTRACT_ONLY=true
BASE_MAIN_SHA=1c1bd24fbe5e1d46277166fddbee666e86999df1
BASE_MAIN_TREE_SHA=32a58fd49f606d8b23f4228855aefbbd6eb7ca5c
BASE_REF=origin/main
PARENT_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTRACT
PARENT_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
REVIEWER_ROLE=COORDINATOR
NO_STEP_IMPLIES_THE_NEXT=true
~~~

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=false
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=NOT_PERFORMED
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
CURRENT_V0_3_S3_COMPLETE=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This document freezes **how** a future deterministic **content producer** may
construct `VersionedIncumbentForecastArtifact` for caller injection into the
landed `IncumbentForecastArtifactAdapter` consumer. It defines producer scope,
authoritative forecast replay inputs, entry row shape, fail-closed rules, and
boundaries with adjacent slices.

This is a **content producer** governance contract only. It is **not** the
incumbent forecast artifact adapter consumer contract
(`docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §§1–8), **not** an
implementation authorization, and **not** evidence that versioned forecast
artifacts exist in the repository today.

~~~text
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_CONTENT_PRODUCER=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
CONTRACT_MERGE_DOES_NOT_PRODUCE_CATALOG=true
CONTRACT_MERGE_DOES_NOT_BIND_CATALOG=true
AVAILABLE_CLOSEOUT_REQUIRED_FOR_LIVE_FLIP=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_BY_THIS_CONTRACT=true
~~~

## 1. Inherited authority (not reopened)

### 1.1 Parent forecast artifact contract and adapter (reference only)

~~~text
INCUMBENT_FORECAST_ARTIFACT_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md
INCUMBENT_FORECAST_ARTIFACT_CONTRACT_EVIDENCE_JSON_SHA256=8e19a623c6739abeb047768ef642281b86ac7f2d73ea35fcff83ae3165f40376
INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=1928d044d85c9dbff3c71d14551409c9c61404ed84174f20979fbc31ba6fae00
INCUMBENT_FORECAST_ARTIFACT_ADAPTER_R1_EVIDENCE_JSON_SHA256=31bb6d24cf4c398eeea86c18d2dece16b9e0ab6f704e9ab229eac5a363d296a0
FORECAST_ARTIFACT_PY_BLOB=f928c6c9fa94e91e33c37edd8e9ab57c6e138480
TEST_FORECAST_ARTIFACT_PY_BLOB=2ae0036a46f6f0b2898a8fca3589041b9869c196
~~~

Parent contract §§1–8 remain authoritative and are not rewritten by this
content producer contract. `IncumbentForecastArtifactAdapter` (R1, #319) is
already landed; this contract does not re-authorize or re-implement the adapter.

### 1.2 S2 binding and adjacent producers (reference only)

~~~text
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
S2_CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_ROW_COUNT=16224
VALIDATION_ROW_COUNT=8006
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
TRAIN_PARTITION_DATES=2025-08-05..2026-01-30
VALIDATION_PARTITION_DATES=2026-01-31..2026-03-09
TEST_PARTITION_DATES=2026-03-10..2026-04-16
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY_BLOB=14e5614c9069b7b50d12bf3caa36305245c2cc39
S2_IDENTITY_ALIGNMENT_PY_BLOB=b899e52dbd8752b30395441389ad93fc98d9dbf7
~~~

Alignment evidence producer R1 is landed; default construction still yields no
live S2 identity facts in the repository. This content producer contract does not
conflate forecast content with S2 identity alignment evidence.

### 1.3 Repository audit references (read-only at 1c1bd24)

~~~text
CATALOG_ARTIFACT_PY_BLOB=968e841527b696d17364ddae11693fadb49462b8
REGISTRY_PY_BLOB=d3d4dc77e6340786ddcca128eb02e0c1d898a502
TEST_CATALOG_ARTIFACT_PY_BLOB=af59a9f1d291ab32eff23684aca477f0e4a852cd
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
UNIQUE_ALEMBIC_HEAD=a7c3e9f1b2d4
PARALLEL_ALEMBIC_HEADS_ALLOWED=false
SOURCE_002_ROW_LEVEL_READ=false
~~~

Evidence JSON self-hashes above are binding references, not whole-file
`sha256sum` values.

## 2. What the content producer is

### 2.1 Producer definition

A future deterministic **incumbent forecast artifact content producer** projects
versioned incumbent forecast replay rows into `VersionedIncumbentForecastArtifact`
for caller injection into `IncumbentForecastArtifactAdapter`.

~~~text
PRODUCER_OUTPUT_TYPE=VersionedIncumbentForecastArtifact
ENTRY_ROW_TYPE=IncumbentForecastArtifactEntry
ENTRY_ROW_FIELDS=model_id,forecast_cutoff_at,forecast_quantile
OPTIONAL_ENVELOPE_FIELDS=model_identity_metadata,content_identity_sha256
PRODUCER_IS_NOT_FORECAST_ADAPTER=true
PRODUCER_IS_NOT_CATALOG_ARTIFACT=true
PRODUCER_IS_NOT_S2_HARVEST_GRAIN_ENUMERATION=true
PRODUCER_IS_NOT_ALIGNMENT_EVIDENCE=true
PRODUCER_CARRIES_NO_KG_OR_TONNES=true
PRODUCER_CARRIES_NO_DAILY_CURVE=true
~~~

Each `IncumbentForecastArtifactEntry` carries only:

- `model_id`
- `forecast_cutoff_at`
- `forecast_quantile`

The versioned envelope may additionally bind `model_identity_metadata` and
`content_identity_sha256`. The producer must **not** carry kg/tonnes, daily kg
curves, S2 harvest grain fields, `harvest_business_date` as cutoff, catalog
cells, or alignment identities.

### 2.2 Consumer handoff (adapter R1; not redefined here)

`IncumbentForecastArtifactAdapter` (landed in `forecast_artifact.py`) consumes
caller-injected `VersionedIncumbentForecastArtifact` only. Default construction
has `artifact=None` → `has_versioned_artifact=false` →
`EvaluationInstanceCatalogArtifactProductionService.produce()` →
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.

~~~text
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
USES_HARVEST_DATE_AS_FORECAST_CUTOFF_MUST_BE_FALSE=true
HARVEST_DATE_AS_CUTOFF_FORBIDDEN_ADAPTER_ENTRIES_EMPTY=true
ADAPTER_DOES_NOT_READ_REPOSITORY_FOR_ARTIFACT=true
ADAPTER_DOES_NOT_READ_RAW_SOURCE_002=true
~~~

If `uses_harvest_date_as_forecast_cutoff` is true, the adapter must return
`entries()=()` and `produce()` → `HARVEST_DATE_AS_CUTOFF_FORBIDDEN`.

### 2.3 Catalog artifact coupling (unchanged)

`catalog_artifact.py` `produce()` copies `catalog_source_kind` from
`forecast_source_kind`, not from alignment source kind. This contract does not
change that provenance. Default forecast injection may remain `BOUND_FIXTURE`;
even with future live forecast content injected, catalog production may still
yield `FIXTURE_ONLY_CATALOG_NOT_BINDABLE` when forecast source kind is
fixture-bound.

~~~text
CATALOG_SOURCE_KIND_COPIED_FROM_FORECAST_SOURCE_KIND=true
THIS_CONTRACT_DOES_NOT_CHANGE_CATALOG_SOURCE_KIND_PROVENANCE=true
BOUND_FIXTURE_IS_NOT_LIVE_FORECAST_AUTHORITY=true
TEST_ONLY_EXPLICIT_INJECTION_BOUND_FIXTURE_PATH_PRESERVED=true
~~~

## 3. Allowed authoritative inputs (semantic freeze; not implemented by this contract)

### 3.1 Forecast and visibility authority

~~~text
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
FORECAST_ARTIFACT_REQUIRES_PIT_REPLAY_AT_HISTORICAL_CUTOFF=true
FORBIDDEN_HANDWRITTEN_CUTOFF_LISTS=true
FORBIDDEN_HARVEST_DATE_ENUMERATION_AS_CUTOFF=true
FORBIDDEN_RAW_SOURCE_002_PRIMARY_READ=true
FORBIDDEN_REPOSITORY_SCAN_FOR_SUBSTITUTES=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

Future implementation may project `DISTINCT(forecast_cutoff_at, model_id,
forecast_quantile)` from versioned incumbent historical cutoff replay at
point-in-time with IDFL label-side visibility. This is not harvest-day
enumeration and not S2 harvest grain projection.

### 3.2 Content identity hash (defined, not invented)

~~~text
CONTENT_IDENTITY_SHA256_MUST_BE_DETERMINISTIC_OVER_REAL_PRODUCED_ROWS=true
FORBIDDEN_PLACEHOLDER_CONTENT_IDENTITY_SHA256=true
FORBIDDEN_EMPTY_STRING_CONTENT_IDENTITY_SHA256=true
FORBIDDEN_ZERO_SENTINEL_CONTENT_IDENTITY_SHA256=true
FORBIDDEN_H7_FIXTURE_AS_CONTENT_IDENTITY_SHA256=true
FORBIDDEN_INVENT_CONTENT_IDENTITY_SHA256=true
FORBIDDEN_INVENT_DISTINCT_ENTRY_COUNTS=true
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
~~~

A future producer implementation must compute `content_identity_sha256` from the
actual produced entries using a separately versioned deterministic recipe. This
contract merge does **not** publish that hash value, cutoff lists, or distinct
entry counts.

### 3.3 Future live forecast source kind (named only; enum unchanged)

~~~text
LIVE_FORECAST_SOURCE_KIND_CANDIDATE=V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
THIS_CONTRACT_DOES_NOT_MODIFY_REGISTRY_PY_ENUM=true
BOUND_FIXTURE_MUST_NOT_BE_LIVE_FORECAST_SOURCE_KIND=true
UNBOUND_MUST_NOT_BE_LIVE_FORECAST_SOURCE_KIND=true
FORBIDDEN_CATALOG_SOURCE_KINDS_REMAINS_UNCHANGED_BY_THIS_CONTRACT=true
~~~

This contract may name a future live forecast source kind candidate only. It
does **not** modify `registry.py` or `CatalogSourceKind`; enum changes remain for
a later implementation authorization and code lane.

## 4. Forbidden inputs and substitutions

~~~text
FORBIDDEN_SUBSTITUTION_INCUMBENT_DAILY_CURVE_PROVIDER=true
FORBIDDEN_SUBSTITUTION_SPARSE_HORIZON_BINDING_FORECAST_PROVIDER=true
FORBIDDEN_SUBSTITUTION_S3_BINDING_ROW=true
FORBIDDEN_SUBSTITUTION_S2_HARVEST_GRAIN=true
FORBIDDEN_SUBSTITUTION_H7_FIXTURE=true
FORBIDDEN_SUBSTITUTION_REPOSITORY_SCAN=true
FORBIDDEN_HANDWRITTEN_FARM_LISTS=true
FORBIDDEN_HANDWRITTEN_CELL_LISTS=true
FORBIDDEN_HANDWRITTEN_DATE_LISTS=true
FORBIDDEN_MODIFY_FORECAST_ADAPTER_PORT_SIGNATURE=true
FORBIDDEN_TOUCH_FROZEN_TEST_CATALOG_ARTIFACT_PY=true
FORBIDDEN_NEW_ALEMBIC=true
FORBIDDEN_V0_2_POSTGRES_CONCURRENCY_CANARY_FLAKY_TESTS=true
~~~

## 5. TEST seal and exclusion policy

~~~text
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
TEST_PARTITION_DATES=2026-03-10..2026-04-16
FORBIDDEN_TEST_CUTOFF_OR_HORIZON_INTERSECTION=true
TEST_WINDOW_FILTER_AUTHORITY=INCUMBENT_FORECAST_ARTIFACT_ADAPTER_AND_DAILY_ROWSET_MATERIALIZER
DEFAULT_MONTH_SCOPE=1-4
FORBIDDEN_VARIETIES=普鲜,普青,普冻,废果
FORBIDDEN_FACTORY_BASON=true
~~~

Any `forecast_cutoff_at` or evaluation horizon window (7/14/21-day) intersecting
TEST partition dates `2026-03-10..2026-04-16` must be excluded. The adapter
already implements `_entry_intersects_test_partition`; the content producer must
apply the same prohibition at production time.

## 6. Fail-closed producer rules

1. **No injected replay rows** → caller leaves adapter at default
   `artifact=None` → `produce()` remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.
2. **Missing projection** → do not invent cutoff/model/quantile lists; future
   implementation should yield empty artifact / `None`.
3. **Post-exclusion emptiness** → must not be labeled with a live forecast
   source kind; must not claim versioned forecast artifacts exist in the
   repository.
4. **Repository has no versioned incumbent forecast artifacts today** → contract
   authorization does not mean live forecast content is already materialized in
   the repository.

~~~text
FAIL_CLOSED_ON_EMPTY_POST_EXCLUSION_ARTIFACT=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY_TODAY=true
CONTRACT_AUTHORIZATION_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
~~~

`BOUND_FIXTURE` is not live forecast authority. Test-only explicit injection of
`BOUND_FIXTURE` forecast paths must remain →
`FIXTURE_ONLY_CATALOG_NOT_BINDABLE`. Live `catalog_source_kind` must not be
`BOUND_FIXTURE`, `UNBOUND`, or any `FORBIDDEN_CATALOG_SOURCE_KINDS` member when
claiming live forecast authority.

## 7. Explicit non-scope (not authorized by this contract)

This contract merge does **not** authorize:

- implementing the content producer service
- writing versioned incumbent forecast artifacts into the repository
- flipping `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY`
- bindable catalog production
- `EVALUATION_INSTANCE_REGISTRY_AVAILABLE` closeout
- `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED` closeout
- live S2 identity alignment facts
- S3-B semantics verified claims
- S3-C backtest execution
- TEST evaluation or TEST unseal
- modifying `IncumbentForecastArtifactAdapter` port signatures
- modifying `catalog_artifact.produce()` catalog_source_kind provenance

Future code paths named for contract narration only (not created by this PR):

~~~text
FUTURE_BACKEND_APP_PATH=backend/app/s3_daily_rowset/incumbent_forecast_artifact_content.py
FUTURE_TEST_PATH=backend/tests/s3_daily_rowset/test_incumbent_forecast_artifact_content.py
PERSISTENCE=IN_MEMORY_SERVICE_ONLY
PEP_420_NAMESPACE=true
PRODUCTION_INIT_PY_FORBIDDEN=true
ALEMBIC_FORBIDDEN=true
~~~

~~~text
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
~~~

## 8. LLM and deterministic service boundary

LLM agents organize explanation and invoke tools. Forecast entries, content
hashes, cutoff lists, farm lists, and availability flags must come from
versioned incumbent replay and coordinator-reviewed artifacts only. LLM must not
invent tonnes, farms, cells, cutoff lists, identity hashes, or distinct entry
counts.

## 9. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live block and pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §18 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §34 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §17 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §22 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §23 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §26 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §11 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

Unchanged live flags retained:

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=false
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
~~~
