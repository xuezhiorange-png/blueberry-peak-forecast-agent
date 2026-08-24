# V0.3-S3-A2 evaluation instance catalog artifact production authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_PRODUCTION_AUTHORIZATION
ARTIFACT_VERSION=s3-a2-catalog-artifact-authorization-v1
TASK_ID=V03_S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_PRODUCTION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_PRODUCTION_GRANT_ONLY
SLICE=V0.3-S3
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
USER_WAIVED_THIRD_PARTY_REVIEW=true
COORDINATOR_REVIEW_COUNTS=true
COORDINATOR_AGENT=https://cursor.com/agents/bc-01a02307-c032-7da6-8a02-00d9b3518794
DOCS_ONLY_AGENT=https://cursor.com/agents/bc-01a02a06-2694-7db3-bffe-cbcc33b2c1a2
BASE_REF=origin/main
BASE_MAIN_SHA=805c9f80cc541db6439eda1d6322c8a6f47b4614
BASE_MAIN_TREE_SHA=5a7ddeae352105fc9df044edb24c08829f2618bb
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-catalog-artifact-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-catalog-artifact-authorization.json
EVIDENCE_JSON_SHA256=427dbc4534c9537dbe168e0283644952d82606a481ad0142227dcf7693c9fc09
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_BIND_CATALOG=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

The user authorized issuance of the S3-A2 evaluation instance catalog artifact
production grant after catalog artifact contract freeze #314. This document
records what a **later** deterministic catalog production service may do when the
user again says 「可以实施」. This PR does not produce a catalog, enumerate cells,
bind a catalog, flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`, flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, authorize backtests, or claim
S3-B semantics verified.

Analogous to #304 materialization authorization, #309 registry implementation
authorization, and #312 catalog binding implementation authorization: grant only;
no backend code in this PR.

~~~text
S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_PRODUCTION_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
ALLOWLIST_EXPANSION_AUTHORIZED=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Upstream bindings (reference only)

~~~text
PR314_MERGE=805c9f80cc541db6439eda1d6322c8a6f47b4614
CATALOG_ARTIFACT_CONTRACT_PATH=docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md
CATALOG_ARTIFACT_CONTRACT_GIT_BLOB_SHA=93b30bbaa72267c3fcb032c4c3d8c9462f54a968
CATALOG_ARTIFACT_CONTRACT_SHA256=c32c4275422e2ef39d90449b71d2bfc54d3a094824286a59d6063187fa50563d
CATALOG_ARTIFACT_EVIDENCE_JSON_SHA256=501dcf1034e615f60ca9b76b79cbbe8f9d352c3ea85abf4380d763842ddd4ca6
CATALOG_BINDING_CONTRACT_FREEZE_GIT_BLOB_SHA=2a2e0d282e49c1200dea1ecc9ad7e1053adf157c
CATALOG_BINDING_CONTRACT_FREEZE_SHA256=ea49044b7c3481070534d98b57de212d67c29ff4b3b9fae01160b669794e5156
BINDING_IMPL_EVIDENCE_JSON_SHA256=d86ad33cba6299a1b58a28598d82a90b20b53fb73700e037919698e89ef24ae5
A2_REGISTRY_CONTRACT_FREEZE_GIT_BLOB_SHA=189b9b480cc5d1699dd1c0475cbf09802cf741f0
A2_REGISTRY_CONTRACT_SHA256=d7c681c0179b834c01f9fa760361ac13fed1040d3a8900a58dab24654488b762
AMENDMENT_PATH=docs/v0-3/s3/s3-daily-rowset-amendment.md
AMENDMENT_GIT_BLOB_SHA=ef3bc17468602a10632271c85d24db36b69984df
P0_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
P0_GIT_BLOB_SHA=7d75622d695da9961e0a3949762e028c43013546
P0_EVIDENCE_JSON_SHA256=580f09e306e4e32db0e72d65158d455bd9fea57b4279497909ff0d54cb91259c
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
FORBIDDEN_SAMPLE_H7_FIXTURE_AS_CATALOG=true
S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_CONTRACT_AUTHORIZED=true
DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_BINDING_SERVICE_IMPLEMENTED=true
~~~

Evidence JSON self-hashes above are binding references, not whole-file
`sha256sum` values. Archived workpaper/evidence bodies from #303–#314 are
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
EVALUATION_INSTANCE_CELL_GRAIN=SEASON,FARM,SUBFARM,VARIETY,MODEL,FORECAST_CUTOFF,FORECAST_QUANTILE
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
V0_3_S3_ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
V0_3_S3_VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
SOURCE_002_ROW_LEVEL_READ=false
REGISTRY_SOURCE_STATUS=NOT_MATERIALIZED_OR_NOT_BOUND
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
UNIQUE_ALEMBIC_HEAD=a7c3e9f1b2d4
~~~

## 3. What this authorization grants

A later deterministic catalog production service may, under a separate user
「可以实施」 gate, deliver an in-memory production service (PEP 420 namespace; no
production `__init__.py`; no Alembic; `IN_MEMORY_SERVICE_ONLY`) that:

~~~text
EVALUATION_INSTANCE_CELL_GRAIN=SEASON,FARM,SUBFARM,VARIETY,MODEL,FORECAST_CUTOFF,FORECAST_QUANTILE
REGISTRY_PARTITION_SCOPE=TRAIN,VALIDATION
PERSISTENCE=IN_MEMORY_SERVICE_ONLY
DETERMINISTIC_AND_REPRODUCIBLE=true
DEFAULT_CONSTRUCTION=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
~~~

The service must:

1. Read `FORECAST_CUTOFF`, `MODEL`, and `FORECAST_QUANTILE` only from versioned
   incumbent forecast artifacts (`V0_3_S3_FORECASTS_AUTHORITY`). If no such
   artifact exists in the repository, fail closed — do not invent cutoffs.
2. Align `SEASON`, `FARM`, `SUBFARM`, and `VARIETY` to accepted S2
   `source-002/e5-live-v1` TRAIN/VALIDATION identities. S2 harvest grain is not
   the catalog; `harvest_business_date` is not `forecast_cutoff`.
3. Label partitions `TRAIN` or `VALIDATION` only. Exclude any cell/window
   intersecting TEST dates `2026-03-10..2026-04-16`.
4. Apply A2 exclusions (普鲜/普青/普冻/废果, 巴松, non 1–4 month). If the
   post-exclusion set is empty, do not claim bindable.
5. Attach catalog-artifact content/manifest hash (not H=7 fixture hash `8e74d6be…`,
   not rowset window hash, not empty-catalog hash).
6. Hand output to `EvaluationInstanceCatalogBindingService` for structural
   validation per binding contract #311.

Tests may inject fixture catalog artifacts. Fixtures must not be written as live
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE=true`, `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=true`,
or `NO_BINDABLE_CATALOG_IN_REPOSITORY=false`.

Default construction when no versioned incumbent forecast artifact exists:

~~~text
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
REGISTRY_SOURCE_STATUS=NOT_MATERIALIZED_OR_NOT_BOUND
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
FORBIDDEN_INVENT_CUTOFFS=true
FORBIDDEN_INVENT_CELL_ROWS=true
FORBIDDEN_INVENT_CATALOG_HASHES=true
~~~

## 4. Fail-closed conditions (must not be reported as PASS)

Future implementation must fail closed when:

- hand-written farm lists, cutoff lists, cell counts, or catalog hashes are used
- S2 harvest grain, farm pick-day enumeration, or V0.2 `S3BindingRow` sparse rows
  substitute for the V0.3 complete evaluation instance catalog
- H=7 fixture hash `8e74d6be…` is cited as catalog or dataset completeness evidence
- `COMPLETE_SEASON` is treated as dataset PASS despite TEST partition intersection
- raw SOURCE_002, xls, Sheets, S1 JSON, PIT, or old-winner tables are used as
  SOURCE_002 primary input
- LLM invents registry rows, cell counts, catalog hashes, or predicate outcomes

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

Read-only repository audit conclusion remains: no bindable catalog in repository.

## 6. Registry flip manifest

~~~text
S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_PRODUCTION_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §22 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §10 implementation authorization pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §11 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §14 pointer

Unchanged live flags retained:

~~~text
S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_CONTRACT_AUTHORIZED=true
DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_BINDING_SERVICE_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
~~~

## 7. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_BIND_CATALOG=true
AWAITING_COORDINATOR_REVIEW=true
~~~
