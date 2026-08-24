# V0.3-S3-A2 Evaluation Instance Catalog Artifact Contract

## Contract identity and phase boundary

~~~text
CONTRACT_ID=V0_3_S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_CONTRACT
CONTRACT_VERSION=v0-3-s3-a2-evaluation-instance-catalog-artifact-contract-v1
TASK_ID=V03_S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=EVALUATION_INSTANCE_CATALOG_ARTIFACT_PRODUCTION_AND_ACCEPTANCE
USER_GATE=可以下一步
CONTRACT_ONLY=true
BASE_MAIN_SHA=4f51874730594421a4945e23bcbf57db685bd323
BASE_MAIN_TREE_SHA=2a23f2f5b64b01f468f552187a48a72e2fc3f19c
BASE_REF=origin/main
PARENT_BINDING_CONTRACT_ID=V0_3_S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_CONTRACT
PARENT_BINDING_CONTRACT_PATH=docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md
PARENT_BINDING_CONTRACT_FREEZE_GIT_BLOB_SHA=2a2e0d282e49c1200dea1ecc9ad7e1053adf157c
PARENT_BINDING_CONTRACT_FREEZE_SHA256=ea49044b7c3481070534d98b57de212d67c29ff4b3b9fae01160b669794e5156
PARENT_A2_CONTRACT_ID=V0_3_S3_A2_EVALUATION_INSTANCE_REGISTRY_CONTRACT
PARENT_A2_CONTRACT_PATH=docs/v0-3/s3/s3-evaluation-instance-registry-contract.md
PARENT_A2_CONTRACT_FREEZE_GIT_BLOB_SHA=189b9b480cc5d1699dd1c0475cbf09802cf741f0
PARENT_A2_CONTRACT_FREEZE_SHA256=d7c681c0179b834c01f9fa760361ac13fed1040d3a8900a58dab24654488b762
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
REVIEWER_ROLE=COORDINATOR
COORDINATOR_AGENT=https://cursor.com/agents/bc-01a02307-c032-7da6-8a02-00d9b3518794
DOCS_ONLY_AGENT=https://cursor.com/agents/bc-01a02a06-2694-7db3-bffe-cbcc33b2c1a2
NO_STEP_IMPLIES_THE_NEXT=true
~~~

~~~text
S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_CONTRACT_AUTHORIZED=true
S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_CONTRACT_AUTHORIZED=true
S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_IMPLEMENTATION_AUTHORIZED=true
S3_A2_EVALUATION_INSTANCE_REGISTRY_CONTRACT_AUTHORIZED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_BINDING_SERVICE_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
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

This document freezes **how** a future versioned evaluation instance master
catalog artifact may be produced and accepted for binding. It defines artifact
grain, authoritative source layering, content/manifest hash requirements,
repository audit classification, and the boundary between contract authorization
and live `EVALUATION_INSTANCE_REGISTRY_AVAILABLE` closeout.

This is a governance contract only. It does **not** produce a catalog artifact,
enumerate cells, bind a catalog, implement catalog production, flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, run completeness verification, flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, execute backtests, or claim
S3-B semantics verified.

PR #311 froze catalog **binding** rules. PR #313 delivered the in-memory binding
validator. Repository audit at `4f518747` still finds no bindable, versioned
incumbent evaluation instance master catalog. This contract defines what a future
artifact must look like before binding is even meaningful; it does not create one.

~~~text
CONTRACT_MERGE_DOES_NOT_PRODUCE_CATALOG=true
CONTRACT_MERGE_DOES_NOT_BIND_CATALOG=true
AVAILABLE_CLOSEOUT_REQUIRED_FOR_LIVE_FLIP=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
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
CANONICAL_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
Q2C_TARGET=OBSERVED_FARM_PICK_QUANTITY
S3_EVALUATION_PARTITIONS=TRAIN,VALIDATION
TEST_PARTITION_DATES=2026-03-10..2026-04-16
TIMEZONE=Asia/Shanghai
~~~

### 1.2 Input authorities (distinct; do not conflate)

~~~text
V0_3_S3_ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
V0_3_S3_VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
V0_2_S3_INPUT_AUTHORITY_HISTORICAL=S2_IMMUTABLE_BACKTEST_BINDING
DO_NOT_CONFLATE_V0_2_S2_IMMUTABLE_BACKTEST_BINDING_WITH_V0_3_S2_DATASET=true
SOURCE_002_ROW_LEVEL_READ=false
FORBIDDEN_PIT_TABLE_AS_SOURCE_002_PRIMARY=true
FORBIDDEN_OLD_WINNER_TABLE_AS_SOURCE_002_PRIMARY=true
FORBIDDEN_RAW_SOURCE_002_PRIMARY=true
~~~

### 1.3 Upstream contract and implementation references (not rewritten)

~~~text
CATALOG_BINDING_CONTRACT_FREEZE_GIT_BLOB_SHA=2a2e0d282e49c1200dea1ecc9ad7e1053adf157c
CATALOG_BINDING_CONTRACT_FREEZE_SHA256=ea49044b7c3481070534d98b57de212d67c29ff4b3b9fae01160b669794e5156
BINDING_CONTRACT_EVIDENCE_JSON_SHA256=1122134e91610eb88c5521fce3ffe76d4e7e9a05ff02b8c719cf8459daac2a4b
AUTH312_EVIDENCE_JSON_SHA256=22b8e4bd0c8d530008afd42b3f9213f4c47b4870b5709576ea7993725cf9f379
BINDING_IMPL_EVIDENCE_JSON_SHA256=d86ad33cba6299a1b58a28598d82a90b20b53fb73700e037919698e89ef24ae5
A2_REGISTRY_CONTRACT_FREEZE_GIT_BLOB_SHA=189b9b480cc5d1699dd1c0475cbf09802cf741f0
A2_REGISTRY_CONTRACT_SHA256=d7c681c0179b834c01f9fa760361ac13fed1040d3a8900a58dab24654488b762
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
FORBIDDEN_SAMPLE_H7_FIXTURE_AS_CATALOG=true
UNIQUE_ALEMBIC_HEAD=a7c3e9f1b2d4
PARALLEL_ALEMBIC_HEADS_ALLOWED=false
~~~

Evidence JSON self-hashes above are binding references, not whole-file
`sha256sum` values. Archived workpaper/evidence bodies from #303–#313 are
referenced only; not rewritten by this contract task.

## 2. Catalog artifact definition

### 2.1 What the artifact is

A bindable evaluation instance catalog artifact is a **versioned, non-empty**
master directory at amendment evaluation-instance cell grain:

~~~text
EVALUATION_INSTANCE_CELL_GRAIN=SEASON,FARM,SUBFARM,VARIETY,MODEL,FORECAST_CUTOFF,FORECAST_QUANTILE
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
CATALOG_ARTIFACT_IS_NOT_S2_HARVEST_GRAIN_TABLE=true
CATALOG_ARTIFACT_IS_NOT_V0_2_S3_BINDING_ROW_SET=true
CATALOG_ARTIFACT_IS_NOT_H7_FIXTURE=true
CATALOG_ARTIFACT_IS_NOT_UNBOUND_OR_EMPTY=true
CATALOG_ARTIFACT_IS_NOT_TEST_ONLY_FIXTURE=true
~~~

Each artifact row identifies one in-scope evaluation instance **cell** with a
partition label (`TRAIN` or `VALIDATION`). The artifact is the authoritative
input to `EvaluationInstanceCatalogBindingService`; it is not the binding
validator itself and not a materialized daily rowset window.

### 2.2 What the artifact is not

~~~text
FORBIDDEN_S2_HARVEST_GRAIN_CATALOG_AS_EVALUATION_INSTANCE_REGISTRY=true
FORBIDDEN_V0_2_S3_BINDING_ROWS_AS_V0_3_COMPLETE_REGISTRY=true
FORBIDDEN_FARM_PICK_DAY_ENUMERATION_AS_FORECAST_CUTOFF=true
FORBIDDEN_SAMPLE_H7_FIXTURE_AS_CATALOG=true
FORBIDDEN_EMPTY_CATALOG_AS_BINDABLE=true
FORBIDDEN_UNBOUND_REGISTRY_STATE_AS_CATALOG=true
~~~

## 3. Authoritative source layering

Production of a future catalog artifact must respect distinct authorities. Mixing
layers is forbidden.

### 3.1 Forecast and model fields

~~~text
FORECAST_CUTOFF_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
MODEL_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
FORECAST_QUANTILE_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
FORBIDDEN_INVENT_CUTOFFS=true
FORBIDDEN_HANDWRITTEN_CUTOFF_LISTS=true
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
~~~

`FORECAST_CUTOFF`, `MODEL`, and `FORECAST_QUANTILE` must come from versioned
incumbent forecast artifacts replayed at historical cutoff with IDFL label-side
visibility. Hand-written cutoff lists are forbidden. `harvest_business_date` from
S2 grain must not substitute for `forecast_cutoff`.

### 3.2 Location and variety fields

~~~text
SEASON_FARM_SUBFARM_VARIETY_ALIGNMENT=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
S2_HARVEST_GRAIN_IS_NOT_CATALOG_ARTIFACT=true
~~~

`SEASON`, `FARM`, `SUBFARM`, and `VARIETY` must align to accepted S2
`source-002/e5-live-v1` TRAIN/VALIDATION identities. S2 harvest grain tables
supply alignment evidence only; they are not the evaluation instance catalog
artifact.

### 3.3 Partition and TEST seal

~~~text
S3_EVALUATION_PARTITIONS=TRAIN,VALIDATION
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
TEST_PARTITION_DATES=2026-03-10..2026-04-16
FORBIDDEN_TEST_CELL_IN_ARTIFACT=true
~~~

Partition labels are `TRAIN` or `VALIDATION` only. Any cell or evaluation
window intersecting TEST partition dates must not enter the artifact.

### 3.4 A2 exclusion rules (inherited)

~~~text
CELL_LEVEL_EXCLUDED_NO_WINDOW=true
FORBIDDEN_VARIETIES=普鲜,普青,普冻,废果
FORBIDDEN_FACTORY_BASON=true
DEFAULT_SEASON_MONTH_SCOPE=1-4
NON_IN_SEASON_MONTHS_EXCLUDED=true
COMPLETE_SEASON_IS_NOT_DATASET_COMPLETENESS_PASS=true
~~~

After A2 cell-level exclusions, the in-scope artifact set must be non-empty
before a future binder may structurally accept it. **This contract does not
claim the in-scope set is non-empty today and does not publish cell counts.**

## 4. Artifact identity and hash requirements

### 4.1 Content/manifest hash

~~~text
CATALOG_ARTIFACT_REQUIRES_CONTENT_OR_MANIFEST_HASH=true
CATALOG_ARTIFACT_HASH_IS_NOT_ROWSET_WINDOW_HASH=true
CATALOG_ARTIFACT_HASH_IS_NOT_H7_FIXTURE_HASH=true
CATALOG_ARTIFACT_HASH_IS_NOT_EMPTY_CATALOG_HASH=true
FORBIDDEN_INVENT_CATALOG_HASHES=true
~~~

A future accepted artifact must carry its own versioned content hash or manifest
hash (catalog-artifact identity, not daily-rowset window hash, not H=7 fixture
hash `8e74d6be…`, not an empty-catalog sentinel). **This PR does not invent
that hash.**

### 4.2 Lineage and dataset binding

Future artifacts must declare binding to:

~~~text
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
~~~

## 5. Repository audit classification (read-only at 4f518747)

Audit at base `4f51874730594421a4945e23bcbf57db685bd323` classifies existing
repository objects. This section records classification only; it does not create
new catalog objects or hashes.

~~~text
UnboundEvaluationInstanceCatalog → NOT_BINDABLE
InMemoryEvaluationInstanceCatalog → NOT_BINDABLE (unless future versioned artifact injected under separate gate)
S3BindingRow → FORBIDDEN_SUBSTITUTION
S2_harvest_grain → FORBIDDEN_SUBSTITUTION
H7_success_fixture_hash_8e74d6be → FORBIDDEN_SUBSTITUTION
binding.py_validator → NOT_CATALOG_ARTIFACT
REGISTRY_PY_BLOB=b5ad9e87dadf9947348d6576cdcb544a58a20b95
BINDING_PY_BLOB=0a335f682a923bcd73908b58cd70cd49c9ab0117
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
REGISTRY_SOURCE_STATUS=NOT_MATERIALIZED_OR_NOT_BOUND
~~~

~~~text
FORBIDDEN_INVENT_CELL_ROWS=true
FORBIDDEN_INVENT_CUTOFFS=true
FORBIDDEN_HANDWRITTEN_FARM_LISTS=true
FORBIDDEN_HANDWRITTEN_CELL_COUNTS=true
~~~

## 6. Future production acceptance (defined, not authorized)

This contract defines what a **later** catalog production implementation may
target when the user separately says 「可以实施」. This contract merge does **not**
authorize that implementation.

A future production pass must:

1. Emit a versioned catalog artifact at amendment cell grain.
2. Populate fields only from authoritative layers in §3.
3. Attach catalog-artifact content/manifest hash and S2 dataset lineage.
4. Exclude TEST-intersecting and A2-excluded cells.
5. Produce a non-empty in-scope set after exclusions.
6. Hand the artifact to `EvaluationInstanceCatalogBindingService` for structural
   validation per binding contract #311.

~~~text
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_BY_THIS_CONTRACT=true
IMPLEMENTATION_PR_MAY_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_PR_MAY_NOT_FLIP_COMPLETENESS_VERIFIED=true
AVAILABLE_CLOSEOUT_REQUIRED_FOR_LIVE_FLIP=true
COMPLETENESS_VERIFIED_CLOSEOUT_REQUIRED_FOR_LIVE_FLIP=true
EMIT_NO_COMPLETE_NDAY_WINDOW_FORBIDDEN=true
~~~

## 7. What remains forbidden / not authorized

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
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
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

This contract does not authorize: catalog production implementation, binding
re-implementation, AVAILABLE closeout, VERIFIED closeout, S3-B verified claim,
S3-C backtest execution, SOURCE_002 row-level read, or TEST unseal.

## 8. Subtask boundaries

~~~text
S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_CONTRACT_AUTHORIZED=true
S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_CONTRACT_AUTHORIZED=true
DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_BINDING_SERVICE_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
next_subtask_not_implied=true
NO_STEP_IMPLIES_THE_NEXT=true
~~~

| Subtask | Status after catalog artifact contract merge |
|---|---|
| S3-A2 catalog artifact contract | frozen (this document) |
| S3-A2 catalog binding contract | frozen (#311) |
| S3-A2 binding R1 validator | merged (#313) |
| Catalog artifact production | not authorized |
| Catalog binding (live) | not performed |
| Registry AVAILABLE closeout | not performed |
| Dataset completeness VERIFIED | not performed |

## 9. LLM and deterministic service boundary

~~~text
LLM_MUST_NOT_INVENT_REGISTRY_ROWS=true
LLM_MUST_NOT_INVENT_CATALOG_HASHES=true
LLM_MUST_NOT_INVENT_CELL_COUNTS=true
LLM_MUST_NOT_INVENT_CUTOFF_LISTS=true
LLM_MUST_NOT_INVENT_FARM_LISTS=true
ALL_CATALOG_CONTENT_FROM_VERSIONED_ARTIFACT=true
~~~

LLM agents organize explanation and invoke tools. Catalog contents, artifact
hashes, cell counts, cutoff lists, and availability flags must come from
versioned artifacts and coordinator-reviewed evidence only.

## 10. Catalog artifact production authorization pointer

~~~text
S3_A2_CATALOG_ARTIFACT_PRODUCTION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-catalog-artifact-authorization.md
S3_A2_CATALOG_ARTIFACT_PRODUCTION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-catalog-artifact-authorization.json
EVIDENCE_JSON_SHA256=427dbc4534c9537dbe168e0283644952d82606a481ad0142227dcf7693c9fc09
S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_PRODUCTION_AUTHORIZED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_BIND_CATALOG=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

Live `S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_PRODUCTION_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and the authorization package above.
This pointer does not rewrite contract freeze rules in §§1–9.

## 11. Catalog artifact production R1 pointer

~~~text
S3_A2_CATALOG_ARTIFACT_PRODUCTION_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-catalog-artifact-production-r1.md
S3_A2_CATALOG_ARTIFACT_PRODUCTION_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-catalog-artifact-production-r1.json
EVIDENCE_JSON_SHA256=a776e557c06e7c31787b9824dedc69735f0143b9a221334a72452ea443cb9dbc
DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_ARTIFACT_SERVICE_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
IMPLEMENTATION_MERGE_DOES_NOT_PRODUCE_LIVE_BINDABLE_CATALOG=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
~~~

Live `DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_ARTIFACT_SERVICE_IMPLEMENTED` is
maintained in `docs/v0-3/development-plan.md` §4.4 and this R1 package.
This pointer does not rewrite contract freeze rules in §§1–9.

## 12. Incumbent forecast artifact contract pointer

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md
S3_A2_INCUMBENT_FORECAST_ARTIFACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-contract.md
S3_A2_INCUMBENT_FORECAST_ARTIFACT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-contract.json
EVIDENCE_JSON_SHA256=8e19a623c6739abeb047768ef642281b86ac7f2d73ea35fcff83ae3165f40376
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_AUTHORIZED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CONTRACT_MERGE_DOES_NOT_PRODUCE_FORECAST_ARTIFACT=true
CONTRACT_MERGE_DOES_NOT_PRODUCE_CATALOG=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

Live `S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and the incumbent forecast artifact contract package above.
This pointer does not rewrite contract freeze rules in §§1–9.

## 13. Incumbent forecast artifact implementation authorization pointer

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-authorization.md
S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-authorization.json
EVIDENCE_JSON_SHA256=1928d044d85c9dbff3c71d14551409c9c61404ed84174f20979fbc31ba6fae00
S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTHORIZED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_FORECAST_ARTIFACT=true
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_ADAPTER=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

Live `S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and the implementation authorization package above.
This pointer does not rewrite contract freeze rules in §§1–9.
