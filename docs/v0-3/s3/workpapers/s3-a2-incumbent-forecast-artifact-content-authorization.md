# V0.3-S3-A2 Incumbent forecast artifact content producer implementation authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_IMPLEMENTATION_AUTHORIZATION
ARTIFACT_VERSION=s3-a2-incumbent-forecast-artifact-content-authorization-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_IMPLEMENTATION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_IMPLEMENTATION_GRANT_ONLY
SLICE=V0.3-S3
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=00c0b83d36451ac1abad7b9fbc8463935c9558b1
BASE_MAIN_TREE_SHA=d5a70246bdc6fa7b7532c76ba5e0e112f6b3281e
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-content-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-content-authorization.json
EVIDENCE_JSON_SHA256=29a486d5fa04542404c6629509ee65ebdf3931c30cf758db643faf93cfd35a38
NO_STEP_IMPLIES_THE_NEXT=true
GRANT_ONLY=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_CONTENT_PRODUCER=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_BIND_CATALOG=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

The user authorized issuance of the S3-A2 **incumbent forecast artifact content
producer** implementation grant after content producer contract freeze #327. This
document records what a **later** deterministic content producer may do when the
user again says 「可以实施」. This PR does not implement a producer, write live
forecast artifacts, produce catalogs, bind catalogs, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, authorize backtests, or claim
S3-B semantics verified.

This is **content producer** authorization only. The `IncumbentForecastArtifactAdapter`
consumer (R1, #319) is already landed on main. Do not re-authorize the adapter
consumer.

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=false
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
PR327_MERGE=00c0b83d36451ac1abad7b9fbc8463935c9558b1
CONTENT_PRODUCER_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md
CONTENT_PRODUCER_CONTRACT_EVIDENCE_JSON_SHA256=6294f2028509f2b1021741ac7aea3f20efdcbe07669b87a1782d18c0a5ca9eae
INCUMBENT_FORECAST_ARTIFACT_CONTRACT_EVIDENCE_JSON_SHA256=8e19a623c6739abeb047768ef642281b86ac7f2d73ea35fcff83ae3165f40376
INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=1928d044d85c9dbff3c71d14551409c9c61404ed84174f20979fbc31ba6fae00
INCUMBENT_FORECAST_ARTIFACT_ADAPTER_R1_EVIDENCE_JSON_SHA256=31bb6d24cf4c398eeea86c18d2dece16b9e0ab6f704e9ab229eac5a363d296a0
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
FORECAST_ARTIFACT_PY_BLOB=f928c6c9fa94e91e33c37edd8e9ab57c6e138480
CATALOG_ARTIFACT_PY_BLOB=968e841527b696d17364ddae11693fadb49462b8
S2_IDENTITY_ALIGNMENT_PY_BLOB=b899e52dbd8752b30395441389ad93fc98d9dbf7
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY_BLOB=14e5614c9069b7b50d12bf3caa36305245c2cc39
REGISTRY_PY_BLOB=d3d4dc77e6340786ddcca128eb02e0c1d898a502
TEST_CATALOG_ARTIFACT_PY_BLOB=af59a9f1d291ab32eff23684aca477f0e4a852cd
TEST_FORECAST_ARTIFACT_PY_BLOB=2ae0036a46f6f0b2898a8fca3589041b9869c196
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
~~~

Evidence JSON self-hashes above are binding references, not whole-file
`sha256sum` values. Archived workpaper/evidence bodies are referenced only; not
rewritten by this authorization grant.

## 2. Inherited S2 and content contract authority (not reopened)

~~~text
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
S2_CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
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
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 3. What this authorization grants

A later deterministic incumbent forecast artifact content producer may, under a
separate user 「可以实施」 gate, deliver an in-memory service (PEP 420 namespace; no
production `__init__.py`; no Alembic; `IN_MEMORY_SERVICE_ONLY`) that constructs
`VersionedIncumbentForecastArtifact` for caller injection into the landed
`IncumbentForecastArtifactAdapter`.

### 3.1 Allowed file changes (future implementation only)

~~~text
NEW_BACKEND_APP_S3_DAILY_ROWSET_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY=true
NEW_BACKEND_TESTS_S3_DAILY_ROWSET_TEST_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY=true
CATALOG_ARTIFACT_PY_MAY_ADD_PRODUCER_PORT_AND_LAZY_DEFAULT_FACTORY_ONLY=true
FORECAST_ARTIFACT_PY_MAY_ADD_PRODUCER_PORT_AND_LAZY_DEFAULT_FACTORY_ONLY=true
FORBIDDEN_MODIFY_INCUMBENT_FORECAST_ARTIFACT_ADAPTER_PORT_SIGNATURE=true
FORBIDDEN_MODIFY_CATALOG_SOURCE_KIND_PROVENANCE=true
FORBIDDEN_MODIFY_REGISTRY_PY_IN_THIS_GRANT_PR=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
FORBIDDEN_TOUCH_TEST_FORECAST_ARTIFACT_PY=true
~~~

Future implementation may add:

- `backend/app/s3_daily_rowset/incumbent_forecast_artifact_content.py`
- `backend/tests/s3_daily_rowset/test_incumbent_forecast_artifact_content.py`

Limited optional wiring in `catalog_artifact.py` and/or `forecast_artifact.py`:

- producer port / lazy `default_factory` only
- default `artifact=None` → adapter remains `UNBOUND` → `produce()` with forecast
  only remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`
- **must not** change `produce()` copying `catalog_source_kind` from
  `forecast_source_kind`
- **must not** change `IncumbentForecastArtifactAdapter` port signatures
- **must not** modify `FORBIDDEN_CATALOG_SOURCE_KINDS` or
  `ALLOWED_ALIGNMENT_SOURCE_KINDS` in this grant PR
- wiring similar to #326 evidence producer is allowed but not required by this grant

### 3.2 Producer semantics (future implementation only)

Output envelope: `VersionedIncumbentForecastArtifact`

Entry row: `IncumbentForecastArtifactEntry` with fields
`model_id`, `forecast_cutoff_at`, `forecast_quantile` only.

The future producer must:

1. Bind forecast authority `V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF`
   with visibility `SOURCE_002_IDFL_LABEL_SIDE` and PIT replay at historical
   cutoff.
2. Project `DISTINCT(cutoff, model, quantile)` from versioned incumbent historical
   cutoff replay; forbid handwritten cutoff lists, farm lists, or cell lists.
3. Set `uses_harvest_date_as_forecast_cutoff=false`; `harvest_business_date` is
   **not** `forecast_cutoff`.
4. Output must not carry kg/tonnes, daily curves, S2 harvest grain, alignment
   evidence, or catalog cells.
5. Compute `content_identity_sha256` deterministically over real forecast rows;
   forbid empty string, `0`*64, and H7 fixture
   `8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18`.
6. Fail closed on missing projection → empty artifact / `None`; do not invent
   cutoff lists, farm lists, cell rows, or distinct entry counts.
7. Post-exclusion emptiness must not be labeled with live forecast source kind.
8. Exclude TEST partition: cutoff or horizon windows 7/14/21 intersecting
   `2026-03-10..2026-04-16` must be excluded (same prohibition as adapter
   `_entry_intersects_test_partition`).
9. Not read raw SOURCE_002 as primary input; not scan repository for substitutes
   (daily curves, `SparseHorizonBindingForecastProvider`, `S3BindingRow`, S2
   harvest grain, H7 fixture are `FORBIDDEN_SUBSTITUTION`).
10. Not log sensitive full-row business data.
11. Default construction must not claim versioned forecast artifacts exist in the
    repository (`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY` remains
    true).

`CatalogSourceKind` currently has no `V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF`.
This grant PR must not change `registry.py`. A future implementation PR **may**
add that enum value; it must not place it in `FORBIDDEN_CATALOG_SOURCE_KINDS`,
must not change existing forbidden members or `ALLOWED_ALIGNMENT_SOURCE_KINDS`,
and live envelopes must explicitly set that kind — dataclass defaults `BOUND_FIXTURE`
or `UNBOUND` must not be treated as live forecast authority. If adding the enum
would force changes to frozen tests, that implementation PR must defer the enum
to a later grant.

`BOUND_FIXTURE` is not live forecast authority; #322 test-only explicit injection
path must remain → `FIXTURE_ONLY_CATALOG_NOT_BINDABLE`.

The only implementation-status flip permitted by a future implementation PR is:

~~~text
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=false → true
~~~

`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY` remains true unless a
later separate closeout authorizes otherwise.

### 3.3 Forbidden in future implementation

~~~text
IMPLEMENTATION_PR_MAY_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_PR_MAY_NOT_FLIP_COMPLETENESS_VERIFIED=true
IMPLEMENTATION_PR_MAY_NOT_WRITE_LIVE_FORECAST_ARTIFACT_TO_REPOSITORY=true
IMPLEMENTATION_PR_MAY_NOT_PRODUCE_BINDABLE_CATALOG=true
IMPLEMENTATION_PR_MAY_NOT_WRITE_LIVE_S2_ALIGNMENT_FACTS=true
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
EMIT_NO_COMPLETE_NDAY_WINDOW_FORBIDDEN=true
~~~

## 5. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_IMPLEMENTATION_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` §10 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §19 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §35 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §18 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §23 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §24 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §27 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §12 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

Unchanged live flags retained:

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=false
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
~~~

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_CONTENT_PRODUCER=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
AWAITING_COORDINATOR_REVIEW=true
~~~
