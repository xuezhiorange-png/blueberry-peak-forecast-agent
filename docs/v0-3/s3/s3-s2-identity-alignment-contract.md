# V0.3-S3-A2 S2 Identity Alignment Contract

## Contract identity and phase boundary

~~~text
CONTRACT_ID=V0_3_S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT
CONTRACT_VERSION=v0-3-s3-a2-s2-identity-alignment-contract-v1
TASK_ID=V03_S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=S2_IDENTITY_ALIGNMENT_PORT_LIVE_ADAPTER_PRODUCTION_AND_ACCEPTANCE
USER_GATE=可以下一步
CONTRACT_ONLY=true
BASE_MAIN_SHA=6a9fde9e71ebef2bb3337305618948303784e504
BASE_MAIN_TREE_SHA=5d131027e9a3c7367efda97f5cacf6ef30bbd92d
BASE_REF=origin/main
PARENT_CATALOG_ARTIFACT_CONTRACT_ID=V0_3_S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_CONTRACT
PARENT_CATALOG_ARTIFACT_CONTRACT_PATH=docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
REVIEWER_ROLE=COORDINATOR
NO_STEP_IMPLIES_THE_NEXT=true
~~~

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=false
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_ARTIFACT_SERVICE_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
REGISTRY_SOURCE_STATUS=NOT_MATERIALIZED_OR_NOT_BOUND
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=NOT_PERFORMED
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
CURRENT_V0_3_S3_COMPLETE=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
SOURCE_002_ROW_LEVEL_READ=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This document freezes **how** a future `S2IdentityAlignmentPort` live adapter may
deterministically project accepted S2 TRAIN/VALIDATION identities for catalog
artifact production. It defines alignment grain, authoritative S2 binding,
exclusion policy, source-kind semantics, fail-closed rules, and the boundary
between contract authorization and live adapter implementation.

This is a governance contract only. It does **not** implement an alignment adapter,
write live forecast artifacts, produce evaluation instance catalogs, bind catalogs,
flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, run completeness verification,
flip `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, execute backtests, or claim
S3-B semantics verified.

`EvaluationInstanceCatalogArtifactProductionService` currently defaults to
`EmptyS2IdentityAlignmentPort` (`alignment_source_kind()` → `UNBOUND`,
`aligned_identities()` → `()`, `produce()` → `NO_S2_IDENTITY_ALIGNMENT`). Incumbent
forecast artifact adapter R1 does not implement S2 identity alignment. This
contract fills that gap without implementing it.

~~~text
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_ALIGNMENT_ADAPTER=true
CONTRACT_MERGE_DOES_NOT_PRODUCE_FORECAST_ARTIFACT=true
CONTRACT_MERGE_DOES_NOT_PRODUCE_CATALOG=true
CONTRACT_MERGE_DOES_NOT_BIND_CATALOG=true
AVAILABLE_CLOSEOUT_REQUIRED_FOR_LIVE_FLIP=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_BY_THIS_CONTRACT=true
~~~

## 1. Inherited authority (not reopened)

### 1.1 S2 materialized dataset (accepted)

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
TRAIN_PARTITION_DATES=2025-08-05..2026-01-30
VALIDATION_PARTITION_DATES=2026-01-31..2026-03-09
TEST_PARTITION_DATES=2026-03-10..2026-04-16
S3_EVALUATION_PARTITIONS=TRAIN,VALIDATION
TIMEZONE=Asia/Shanghai
CANONICAL_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
Q2C_TARGET=OBSERVED_FARM_PICK_QUANTITY
~~~

### 1.2 Input authorities (distinct; do not conflate)

~~~text
V0_3_S3_ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
V0_3_S3_VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
SOURCE_002_ROW_LEVEL_READ=false
FORBIDDEN_RAW_SOURCE_002_PRIMARY=true
FORBIDDEN_PIT_TABLE_AS_SOURCE_002_PRIMARY=true
FORBIDDEN_OLD_WINNER_TABLE_AS_SOURCE_002_PRIMARY=true
~~~

### 1.3 Upstream contract and implementation references (not rewritten)

~~~text
CATALOG_ARTIFACT_CONTRACT_FREEZE_GIT_BLOB_SHA=93b30bbaa72267c3fcb032c4c3d8c9462f54a968
CATALOG_ARTIFACT_CONTRACT_FREEZE_SHA256=c32c4275422e2ef39d90449b71d2bfc54d3a094824286a59d6063187fa50563d
CATALOG_ARTIFACT_CONTRACT_EVIDENCE_JSON_SHA256=501dcf1034e615f60ca9b76b79cbbe8f9d352c3ea85abf4380d763842ddd4ca6
FORECAST_ARTIFACT_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md
FORECAST_ARTIFACT_ADAPTER_R1_EVIDENCE_JSON_SHA256=31bb6d24cf4c398eeea86c18d2dece16b9e0ab6f704e9ab229eac5a363d296a0
CATALOG_ARTIFACT_PY_BLOB=772068c9e68ca8bf0e5bacf280a9f2dad59d9734
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
FORBIDDEN_SAMPLE_H7_FIXTURE_AS_CATALOG=true
FORBIDDEN_SAMPLE_H7_FIXTURE_AS_ALIGNMENT_IDENTITY=true
UNIQUE_ALEMBIC_HEAD=a7c3e9f1b2d4
PARALLEL_ALEMBIC_HEADS_ALLOWED=false
~~~

Evidence JSON self-hashes above are binding references, not whole-file
`sha256sum` values. Archived workpaper/evidence bodies are referenced only; not
rewritten by this contract task.

## 2. Alignment definition

### 2.1 What alignment is

S2 identity alignment is the deterministic projection of accepted S2 TRAIN and
VALIDATION identities into catalog-production input rows:

~~~text
ALIGNMENT_GRAIN=SEASON × FARM × SUBFARM × VARIETY × PARTITION
ALIGNMENT_PARTITIONS=TRAIN,VALIDATION
S2_ALIGNED_IDENTITY_FIELDS=season,farm,subfarm,variety,partition
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
ALIGNMENT_DOES_NOT_CARRY_MODEL=true
ALIGNMENT_DOES_NOT_CARRY_FORECAST_CUTOFF=true
ALIGNMENT_DOES_NOT_CARRY_FORECAST_QUANTILE=true
ALIGNMENT_DOES_NOT_CARRY_TONNES=true
ALIGNMENT_DOES_NOT_CARRY_DAILY_KG_CURVE=true
~~~

Each `S2AlignedIdentity` row supplies only `season`, `farm`, `subfarm`, `variety`,
and `partition` (`TRAIN` | `VALIDATION`). Forecast-side fields remain the
responsibility of `IncumbentForecastArtifactPort`.

### 2.2 What alignment is not

~~~text
ALIGNMENT_IS_NOT_S2_HARVEST_GRAIN_ENUMERATION=true
ALIGNMENT_IS_NOT_EVALUATION_INSTANCE_CATALOG=true
ALIGNMENT_IS_NOT_FORECAST_ARTIFACT=true
ALIGNMENT_IS_NOT_INCUMBENT_DAILY_CURVE=true
ALIGNMENT_IS_NOT_V0_2_S3_BINDING_ROW_SET=true
ALIGNMENT_IS_NOT_H7_FIXTURE=true
ALIGNMENT_IS_NOT_EMPTY_PORT_DEFAULT=true
ALIGNMENT_IS_NOT_BOUND_FIXTURE=true
~~~

Specifically excluded:

- S2 harvest grain / `harvest_business_date` enumeration alone
- `EvaluationInstanceCatalogArtifact` output
- `IncumbentForecastArtifactPort` forecast rows
- `IncumbentDailyCurveProvider` daily kg curves
- V0.2 `S3BindingRow` sparse horizon rows
- H=7 fixture hash `8e74d6be…`
- `EmptyS2IdentityAlignmentPort` default (not accepted alignment evidence)
- `BOUND_FIXTURE` or other test-only fixture source kinds as live authority

## 3. Projection, exclusion, and sorting rules

### 3.1 Accepted S2 projection scope

~~~text
ALIGNMENT_SOURCE_DATASET_ID=source-002
ALIGNMENT_SOURCE_DATASET_VERSION=e5-live-v1
ALIGNMENT_SOURCE_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
DEFAULT_MONTH_SCOPE=1-4
ALIGNMENT_PROJECT_FROM_ACCEPTED_S2_TRAIN_VALIDATION_ONLY=true
ALIGNMENT_DEDUPLICATE=true
ALIGNMENT_STABLE_SORT=true
FORBIDDEN_HANDWRITTEN_FARM_LISTS=true
FORBIDDEN_HANDWRITTEN_CELL_LISTS=true
FORBIDDEN_HANDWRITTEN_DATE_LISTS=true
FORBIDDEN_REPOSITORY_SCAN_FOR_SUBSTITUTES=true
~~~

Future alignment must:

1. Start from accepted S2 `source-002/e5-live-v1` TRAIN/VALIDATION materialized
   identities only.
2. Default to months 1–4 accepted grain before projection.
3. Deduplicate on `SEASON × FARM × SUBFARM × VARIETY × PARTITION`.
4. Return rows in stable deterministic sort order.
5. Never treat `harvest_business_date` as `forecast_cutoff`.

### 3.2 Mandatory exclusions

~~~text
FORBIDDEN_VARIETIES=普鲜,普青,普冻,废果
FORBIDDEN_FACTORY_BASON=true
FORBIDDEN_FACTORY_BASON_PROCESSING_PLANT_BUILDING_AREA_AS_FEATURE=true
FORBIDDEN_NON_1_4_MONTH_SCOPE=true
FORBIDDEN_TEST_PARTITION=true
~~~

Processing-plant building area must not enter alignment or downstream prediction
features.

## 4. TEST seal and partition authority

~~~text
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
TRAIN_PARTITION_DATES=2025-08-05..2026-01-30
VALIDATION_PARTITION_DATES=2026-01-31..2026-03-09
TEST_PARTITION_DATES=2026-03-10..2026-04-16
FORBIDDEN_TEST_IDENTITY_OR_WINDOW_IN_ALIGNMENT=true
COMPLETE_SEASON_IS_NOT_DATASET_COMPLETENESS_PASS=true
COMPLETE_SEASON_INTERSECTING_TEST_IS_NOT_DATASET_PASS=true
~~~

Any alignment identity or evaluation window intersecting TEST partition dates must
not enter a future accepted alignment result.

## 5. Source kind and alignment evidence requirements

### 5.1 Future live source kind (semantic freeze only)

~~~text
S2_IDENTITY_ALIGNMENT_SOURCE_KIND=SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT
BOUND_FIXTURE_MUST_NOT_BE_LIVE_SOURCE_KIND=true
UNBOUND_MUST_NOT_BE_LIVE_SOURCE_KIND=true
THIS_PR_DOES_NOT_MODIFY_PYTHON_ENUM=true
~~~

This contract freezes the semantic source kind for a future live adapter. It does
not modify `CatalogSourceKind` or other Python enums in this PR.

### 5.2 Evidence consumption rules

~~~text
ALIGNMENT_REQUIRES_VERSIONED_ACCEPTED_S2_EVIDENCE=true
ALIGNMENT_EVIDENCE_MUST_BE_CALLER_PROVIDED_OR_DETERMINISTIC_SERVICE_RETURNED=true
FORBIDDEN_DIRECT_RAW_SOURCE_002_READ=true
FORBIDDEN_LOG_SENSITIVE_FULL_ROW_DATA=true
FORBIDDEN_INVENT_ALIGNMENT_HASHES=true
~~~

A future live adapter may consume only versioned, caller-explicit, or
deterministic-service-returned accepted S2 alignment evidence. It must not scan
the repository for substitute files or read raw SOURCE_002 directly.

## 6. Repository audit classification (read-only at 6a9fde9)

Audit at base `6a9fde9e71ebef2bb3337305618948303784e504` classifies existing
repository objects. This section records classification only.

| Object | Classification |
|---|---|
| `EmptyS2IdentityAlignmentPort` (production default) | `NO_S2_IDENTITY_ALIGNMENT` |
| `S2AlignedIdentity` schema | `ALIGNMENT_ROW_SHAPE_ONLY` |
| S2 harvest grain enumeration alone | `FORBIDDEN_SUBSTITUTION` |
| `IncumbentDailyCurveProvider` / daily kg curves | `NOT_ALIGNMENT_ARTIFACT` |
| `SparseHorizonBindingForecastProvider` / `S3BindingRow` | `FORBIDDEN_SUBSTITUTION` |
| H=7 fixture `8e74d6be…` | `FORBIDDEN_SUBSTITUTION` |
| `EvaluationInstanceCatalogArtifact` output | `NOT_ALIGNMENT_ARTIFACT` |
| `catalog_artifact.py` production service | `CONSUMER_NOT_ALIGNMENT_ARTIFACT` |

~~~text
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
FORBIDDEN_INVENT_CELL_ROWS=true
~~~

Authorizing this contract does **not** mean a live S2 identity alignment adapter
exists in the repository.

## 7. Future adapter acceptance (defined, not authorized)

This contract defines what a **later** `S2IdentityAlignmentPort` live adapter may
target when the user separately says 「可以实施」 and a separate docs-only
implementation authorization grant is issued. This contract merge does **not**
authorize that implementation.

A future live adapter must:

1. Expose accepted `S2AlignedIdentity` rows via `S2IdentityAlignmentPort`.
2. Return `alignment_source_kind()` consistent with
   `SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT` when evidence is accepted.
3. Fail closed on dataset identity mismatch, missing versioned alignment evidence,
   `UNBOUND`/fixture/forbidden source kinds, blank identity fields, non
   TRAIN/VALIDATION partitions, TEST intersection, post-exclusion emptiness, or
   forbidden substitutions.
4. Hand accepted identities to existing `EvaluationInstanceCatalogArtifactProductionService`.
5. Not flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`,
   `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, or
   `NO_BINDABLE_CATALOG_IN_REPOSITORY`.

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED=false
IMPLEMENTATION_PR_MAY_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_PR_MAY_NOT_FLIP_COMPLETENESS_VERIFIED=true
MISSING_PORT_REPLACEMENT_REQUIRES_SEPARATE_AUTH_GRANT_AND_USER_GATE=true
~~~

## 8. What remains forbidden / not authorized

~~~text
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=NOT_PERFORMED
CURRENT_S3_DAILY_ROWSET_CONTRACT_STATUS=NOT_AVAILABLE_FROM_CURRENT_S2_BINDING
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
S3_BACKTEST_EXECUTION_AUTHORIZED=false
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false
V0_3_S4_AUTHORIZED=false
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
ALLOWLIST_EXPANSION_AUTHORIZED=false
P0_SUSTAINED_PEAK_WINDOW_CONFLICT=UNRESOLVED
SUSTAINED_PEAK_PASS_FORBIDDEN_UNTIL_OWNER_DECISION=true
EMIT_NO_COMPLETE_NDAY_WINDOW_FORBIDDEN=true
~~~

While `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false`, metric blockers
must remain `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING`.

Out of scope for this contract: writing live forecast artifacts, catalog
production closeout, catalog binding closeout, AVAILABLE closeout, VERIFIED
closeout, S3-B verified claim, S3-C backtest, TEST unseal, SOURCE_002 row-level
read, V0.2 postgres concurrency canary flake remediation.

## 9. Subtask boundaries

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=false
next_subtask_not_implied=true
NO_STEP_IMPLIES_THE_NEXT=true
~~~

| Subtask | Status after S2 identity alignment contract merge |
|---|---|
| S3-A2 S2 identity alignment contract | frozen (this document) |
| S3-A2 incumbent forecast artifact adapter R1 | merged (does not implement alignment) |
| S3-A2 catalog artifact production R1 | merged |
| S2 identity alignment live adapter | not authorized |
| Catalog binding (live) | not performed |
| Registry AVAILABLE closeout | not performed |

## 10. LLM and deterministic service boundary

~~~text
LLM_MUST_NOT_INVENT_FARM_LISTS=true
LLM_MUST_NOT_INVENT_CELL_ROWS=true
LLM_MUST_NOT_INVENT_ALIGNMENT_HASHES=true
LLM_MUST_NOT_INVENT_CUTOFF_LISTS=true
ALL_ALIGNMENT_CONTENT_FROM_VERSIONED_ACCEPTED_S2_EVIDENCE=true
~~~

LLM agents organize explanation and invoke tools. Alignment identities, hashes,
cell counts, farm lists, and availability flags must come from versioned accepted
S2 evidence and coordinator-reviewed artifacts only.
