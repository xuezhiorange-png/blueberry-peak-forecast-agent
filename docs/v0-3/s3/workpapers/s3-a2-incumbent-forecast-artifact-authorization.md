# V0.3-S3-A2 incumbent forecast artifact implementation authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTHORIZATION
ARTIFACT_VERSION=s3-a2-incumbent-forecast-artifact-authorization-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_GRANT_ONLY
SLICE=V0.3-S3
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
USER_WAIVED_THIRD_PARTY_REVIEW=true
COORDINATOR_REVIEW_COUNTS=true
COORDINATOR_AGENT=https://cursor.com/agents/bc-01a02307-c032-7da6-8a02-00d9b3518794
DOCS_ONLY_AGENT=https://cursor.com/agents/bc-01a02a06-2694-7db3-bffe-cbcc33b2c1a2
BASE_REF=origin/main
BASE_MAIN_SHA=59132bf048879e79389df8a5e0188b802b619197
BASE_MAIN_TREE_SHA=9a1bdb04e630d2ddac49a3234eca6a3af55f9114
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-authorization.json
EVIDENCE_JSON_SHA256=1928d044d85c9dbff3c71d14551409c9c61404ed84174f20979fbc31ba6fae00
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_FORECAST_ARTIFACT=true
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_BIND_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_ADAPTER=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

The user authorized issuance of the S3-A2 incumbent forecast artifact
implementation grant after forecast artifact contract freeze #317. This document
records what a **later** deterministic `IncumbentForecastArtifactPort` live adapter
may do when the user again says 「可以实施」. This PR does not implement an adapter,
write versioned forecast artifacts, produce catalogs, bind catalogs, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, authorize backtests, or claim
S3-B semantics verified.

Analogous to #304 materialization authorization, #309 registry implementation
authorization, #312 catalog binding implementation authorization, and #315 catalog
artifact production authorization: grant only; no backend code in this PR.

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
ALLOWLIST_EXPANSION_AUTHORIZED=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Upstream bindings (reference only)

~~~text
PR317_MERGE=59132bf048879e79389df8a5e0188b802b619197
FORECAST_ARTIFACT_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md
FORECAST_ARTIFACT_CONTRACT_FREEZE_GIT_BLOB_SHA=483eb5fe1354b0000e06228f41d99587fa06fa70
FORECAST_ARTIFACT_CONTRACT_FREEZE_SHA256=9db8eb69dcf8d71e28a62a3a20d1d072aae4d64cc40d9e72eaf8034005ed0196
FORECAST_ARTIFACT_CONTRACT_EVIDENCE_JSON_SHA256=8e19a623c6739abeb047768ef642281b86ac7f2d73ea35fcff83ae3165f40376
CATALOG_ARTIFACT_CONTRACT_FREEZE_GIT_BLOB_SHA=93b30bbaa72267c3fcb032c4c3d8c9462f54a968
CATALOG_ARTIFACT_CONTRACT_FREEZE_SHA256=c32c4275422e2ef39d90449b71d2bfc54d3a094824286a59d6063187fa50563d
CATALOG_ARTIFACT_CONTRACT_EVIDENCE_JSON_SHA256=501dcf1034e615f60ca9b76b79cbbe8f9d352c3ea85abf4380d763842ddd4ca6
AUTH315_EVIDENCE_JSON_SHA256=427dbc4534c9537dbe168e0283644952d82606a481ad0142227dcf7693c9fc09
PRODUCTION_R1_EVIDENCE_JSON_SHA256=a776e557c06e7c31787b9824dedc69735f0143b9a221334a72452ea443cb9dbc
BINDING_CONTRACT_FREEZE_GIT_BLOB_SHA=2a2e0d282e49c1200dea1ecc9ad7e1053adf157c
BINDING_CONTRACT_FREEZE_SHA256=ea49044b7c3481070534d98b57de212d67c29ff4b3b9fae01160b669794e5156
A2_REGISTRY_CONTRACT_FREEZE_GIT_BLOB_SHA=189b9b480cc5d1699dd1c0475cbf09802cf741f0
A2_REGISTRY_CONTRACT_SHA256=d7c681c0179b834c01f9fa760361ac13fed1040d3a8900a58dab24654488b762
CATALOG_ARTIFACT_PY_BLOB=772068c9e68ca8bf0e5bacf280a9f2dad59d9734
BINDING_PY_BLOB=0a335f682a923bcd73908b58cd70cd49c9ab0117
REGISTRY_PY_BLOB=b5ad9e87dadf9947348d6576cdcb544a58a20b95
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
FORBIDDEN_SAMPLE_H7_FIXTURE_AS_FORECAST_ARTIFACT=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_AUTHORIZED=true
DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_ARTIFACT_SERVICE_IMPLEMENTED=true
~~~

Evidence JSON self-hashes above are binding references, not whole-file
`sha256sum` values. Archived workpaper/evidence bodies from #303–#317 are
referenced only; not rewritten by this authorization grant.

## 2. Inherited S2 and input authority (not reopened)

~~~text
S2_CONTRACT_PATH=docs/v0-3/s2/s2-materialized-dataset-contract.md
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
S2_CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_ROW_COUNT=16224
VALIDATION_ROW_COUNT=8006
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
TEST_PARTITION_DATES=2026-03-10..2026-04-16
S3_EVALUATION_PARTITIONS=TRAIN,VALIDATION
TIMEZONE=Asia/Shanghai
FORECAST_ARTIFACT_FIELDS=FORECAST_CUTOFF,MODEL,FORECAST_QUANTILE
FORECAST_ARTIFACT_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
V0_3_S3_ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
V0_3_S3_VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
SOURCE_002_ROW_LEVEL_READ=false
REGISTRY_SOURCE_STATUS=NOT_MATERIALIZED_OR_NOT_BOUND
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
UNIQUE_ALEMBIC_HEAD=a7c3e9f1b2d4
~~~

## 3. What this authorization grants

A later deterministic `IncumbentForecastArtifactPort` live adapter may, under a
separate user 「可以实施」 gate, deliver an in-memory service (PEP 420 namespace; no
production `__init__.py`; no Alembic; `IN_MEMORY_SERVICE_ONLY`) that:

~~~text
FORECAST_ARTIFACT_FIELDS=FORECAST_CUTOFF,MODEL,FORECAST_QUANTILE
FORECAST_ARTIFACT_REQUIRES_PIT_REPLAY_AT_HISTORICAL_CUTOFF=true
FORECAST_ARTIFACT_REQUIRES_IDFL_LABEL_SIDE_VISIBILITY=true
FORECAST_ARTIFACT_REQUIRES_CONTENT_OR_MANIFEST_HASH=true
PERSISTENCE=IN_MEMORY_SERVICE_ONLY
DETERMINISTIC_AND_REPRODUCIBLE=true
DEFAULT_CONSTRUCTION=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
~~~

The adapter must comply with forecast artifact contract
`docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §§1–8.

Existing port interface (reference only; not modified by this PR) in
`backend/app/s3_daily_rowset/catalog_artifact.py` (`blob=772068c9…`):

- `IncumbentForecastArtifactPort`: `has_versioned_artifact` /
  `catalog_source_kind` / `entries` / `uses_harvest_date_as_forecast_cutoff`
- Default `MissingIncumbentForecastArtifactPort` → `produce()` yields
  `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`

The future adapter must:

1. Read `FORECAST_CUTOFF`, `MODEL`, and `FORECAST_QUANTILE` (and necessary model
   identity metadata) only from versioned incumbent forecast artifacts.
2. Fail closed when no versioned artifact exists: `has_versioned_artifact()=false`,
   `entries()=()`, no invented cutoff lists or cell counts.
3. Not scan the repository for substitute objects.
4. Not treat the following as forecast artifacts:
   `IncumbentDailyCurveProvider` / `FakeIncumbentDailyCurveProvider`,
   `SparseHorizonBindingForecastProvider`, V0.2 `S3BindingRow`, S2 harvest grain /
   `harvest_business_date` enumeration, H=7 fixture `8e74d6be…`,
   `MissingIncumbentForecastArtifactPort` default,
   `FakeIncumbentForecastArtifactPort` (test fixture only),
   `EvaluationInstanceCatalogArtifact` output.
5. Hand accepted rows to existing `EvaluationInstanceCatalogArtifactProductionService`;
   this grant does not authorize rewriting `binding.py` or `registry.py`.
6. Not flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`,
   `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, or
   `NO_BINDABLE_CATALOG_IN_REPOSITORY`.
7. Not write live versioned forecast artifacts or bindable catalogs into the
   repository.
8. Exclude any forecast cutoff or evaluation window intersecting TEST dates
   `2026-03-10..2026-04-16`.
9. Not treat `COMPLETE_SEASON` as dataset PASS.

Forecast-artifact content/manifest hash must not be catalog identity hash, rowset
window hash, H=7 fixture hash `8e74d6be…`, or empty sentinel.

Tests may inject fixture forecast artifacts. Fixtures must not be written as live
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE=true`,
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=true`,
`NO_BINDABLE_CATALOG_IN_REPOSITORY=false`, or
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=false`.

Default construction when no versioned incumbent forecast artifact exists:

~~~text
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
REGISTRY_SOURCE_STATUS=NOT_MATERIALIZED_OR_NOT_BOUND
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
FORBIDDEN_INVENT_CUTOFFS=true
FORBIDDEN_INVENT_CELL_ROWS=true
FORBIDDEN_INVENT_FORECAST_ARTIFACT_HASHES=true
~~~

## 4. Fail-closed conditions (must not be reported as PASS)

Future implementation must fail closed when:

- hand-written cutoff lists, cell counts, or forecast artifact hashes are used
- daily kg curves, sparse horizon binding rows, S2 harvest grain, or H=7 fixture
  substitute for versioned forecast artifact rows
- repository scan discovers substitute files treated as artifacts
- `COMPLETE_SEASON` is treated as dataset PASS despite TEST partition intersection
- LLM invents cutoff lists, cell counts, forecast artifact hashes, or predicate outcomes

~~~text
IMPLEMENTATION_PR_MAY_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_PR_MAY_NOT_FLIP_COMPLETENESS_VERIFIED=true
REGISTRY_AVAILABLE_CLOSEOUT_REQUIRED_FOR_LIVE_FLIP=true
COMPLETENESS_VERIFIED_CLOSEOUT_REQUIRED_FOR_LIVE_FLIP=true
EMIT_NO_COMPLETE_NDAY_WINDOW_FORBIDDEN=true
COMPLETE_SEASON_IS_NOT_DATASET_COMPLETENESS_PASS=true
~~~

## 5. What remains forbidden / not authorized

~~~text
S2_IDENTITY_ALIGNMENT_PORT_LIVE_ADAPTER_NOT_THIS_GRANT=true
MATERIALIZE_VERSIONED_FORECAST_ARTIFACT_IN_REPOSITORY_NOT_AUTHORIZED=true
REPOSITORY_SCAN_FOR_ARTIFACT_SUBSTITUTES_NOT_AUTHORIZED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=NOT_PERFORMED
CURRENT_S3_DAILY_ROWSET_CONTRACT_STATUS=NOT_AVAILABLE_FROM_CURRENT_S2_BINDING
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
S3_BACKTEST_EXECUTION_AUTHORIZED=false
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
CURRENT_V0_3_S3_COMPLETE=false
V0_3_S4_AUTHORIZED=false
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
ALLOWLIST_EXPANSION_AUTHORIZED=false
P0_SUSTAINED_PEAK_WINDOW_CONFLICT=UNRESOLVED
SUSTAINED_PEAK_PASS_FORBIDDEN_UNTIL_OWNER_DECISION=true
~~~

While `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false`, metric blockers
must remain `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING`. Emitting
`NO_COMPLETE_NDAY_WINDOW` before completeness verification closeout is forbidden.

Read-only repository audit conclusion remains: no versioned incumbent forecast
artifact and no bindable catalog in repository.

## 6. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §25 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §9 implementation authorization pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §13 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §14 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §17 pointer

Unchanged live flags retained:

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_AUTHORIZED=true
DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_ARTIFACT_SERVICE_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
~~~

## 7. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_FORECAST_ARTIFACT=true
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_BIND_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_ADAPTER=true
AWAITING_COORDINATOR_REVIEW=true
~~~
