# V0.3-S3-A2 Evaluation Instance Registry Contract

## Contract identity and phase boundary

~~~text
CONTRACT_ID=V0_3_S3_A2_EVALUATION_INSTANCE_REGISTRY_CONTRACT
CONTRACT_VERSION=v0-3-s3-a2-evaluation-instance-registry-contract-v1
TASK_ID=V03_S3_A2_EVALUATION_INSTANCE_REGISTRY_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_EVALUATION_INSTANCE_REGISTRY_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=EVALUATION_INSTANCE_REGISTRY_FOR_DATASET_COMPLETENESS
USER_GATE=可以下一步
CONTRACT_ONLY=true
BASE_MAIN_SHA=f05f6ed71b82188bea4dbbf7b892e5c99dc380af
BASE_MAIN_TREE_SHA=c237833a2a6429ad15577ad473fd8f9bff7cf28d
BASE_REF=origin/main
PARENT_AMENDMENT_ID=V0_3_S3_DAILY_ROWSET_AMENDMENT
PARENT_AMENDMENT_VERSION=v0-3-s3-daily-rowset-amendment-v1
PARENT_AMENDMENT_PATH=docs/v0-3/s3/s3-daily-rowset-amendment.md
PARENT_AMENDMENT_GIT_BLOB_SHA=39357fc946ce9f67647ff138411c259dc7c27b42
PARENT_AMENDMENT_SHA256=c5bd7da04214b35a05b3f180a72344ad7f2e2279f7b3224e33eb4568d93c61ff
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
P0_GIT_BLOB_SHA=2f3cbbb1bdefa708fe8dab35d0e5c8b440f8f16f
P0_SHA256=4ee057f3c1b1d0eecda6e12ae7a1d495cbc45d69ef9806f01e1810fb0db30c41
P0_EVIDENCE_JSON_SHA256=580f09e306e4e32db0e72d65158d455bd9fea57b4279497909ff0d54cb91259c
REVIEWER_ROLE=COORDINATOR
COORDINATOR_AGENT=https://cursor.com/agents/bc-01a02307-c032-7da6-8a02-00d9b3518794
DOCS_ONLY_AGENT=https://cursor.com/agents/bc-01a02a06-2694-7db3-bffe-cbcc33b2c1a2
NO_STEP_IMPLIES_THE_NEXT=true
~~~

~~~text
S3_A2_EVALUATION_INSTANCE_REGISTRY_CONTRACT_AUTHORIZED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=false
S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED=true
DETERMINISTIC_COMPLETENESS_VERIFICATION_SERVICE_IMPLEMENTED=true
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

This document freezes the **evaluation instance registry** contract for V0.3-S3-A.
It defines catalog grain, in-scope inclusion rules, source authority, fail-closed
behavior when no versioned registry is bound, and the necessary and sufficient
conditions for dataset-level `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=true`.

This is a governance contract only. It does **not** implement a registry, materialize
cell rows, run completeness predicates, flip `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`,
execute backtests, or claim S3-B semantics verified.

Amendment §8.1 requires future completeness verification to prove predicates **for
each evaluation instance cell and requested window**. Without a versioned cell
catalog, dataset-level verification cannot be performed and completeness closeout
cannot flip `VERIFIED` to `true`.

PR #307 delivered window-level `CompletenessVerifier` with
`evaluation_instance_registry_available=false` and
`SINGLE_H7_FIXTURE_SUCCESS_DOES_NOT_EQUAL_DATASET_COMPLETE=true`. This contract
defines what a future registry implementation must bind before dataset-wide PASS
is even meaningful.

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
~~~

### 1.2 S3-A amendment cell grain and window anchors (frozen; not redefined)

~~~text
EVALUATION_INSTANCE_CELL_GRAIN=SEASON,FARM,SUBFARM,VARIETY,MODEL,FORECAST_CUTOFF,FORECAST_QUANTILE
TIMEZONE=Asia/Shanghai
HORIZONS_DAYS=7,14,21
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
cutoff_business_date = calendar date of forecast_cutoff_at in Asia/Shanghai
evaluation_window_start_date = cutoff_business_date + 1 day
evaluation_window_end_date   = cutoff_business_date + H days
WINDOW_OR_HORIZON_REALIGNMENT_FORBIDDEN=true
CELL_LEVEL_EXCLUDED_NO_WINDOW=true
~~~

Window anchor rules are frozen from S3-A1. This contract must not re-anchor
windows, change `H`, or substitute harvest-date enumeration for `forecast_cutoff`.

### 1.3 Input authorities (distinct; do not conflate)

~~~text
V0_3_S3_ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
V0_3_S3_VISIBILITY_AUTHORITY=SOURCE_002_IDFL_LABEL_SIDE
V0_2_S3_INPUT_AUTHORITY_HISTORICAL=S2_IMMUTABLE_BACKTEST_BINDING
DO_NOT_CONFLATE_V0_2_S2_IMMUTABLE_BACKTEST_BINDING_WITH_V0_3_S2_DATASET=true
SOURCE_002_ROW_LEVEL_READ=false
FORBIDDEN_PIT_TABLE_AS_SOURCE_002_PRIMARY=true
FORBIDDEN_OLD_WINNER_TABLE_AS_SOURCE_002_PRIMARY=true
~~~

Actual kg must flow only through accepted S2 materialized grain and the existing
`DailyRowsetMaterializerService`. Forecast replay authority remains incumbent
model at historical cutoff with IDFL label-side visibility.

### 1.4 Upstream implementation references (not rewritten)

~~~text
PR307_MERGE=f05f6ed71b82188bea4dbbf7b892e5c99dc380af
VERIFIER_EVIDENCE_JSON_SHA256=78912e668dfd72ae08b94c86851a3dd812479527c6881659f0c5d630c4134358
AUTH306_EVIDENCE_JSON_SHA256=783bfac0259393f052996de7f8cb43c74512d7062d2725083c9dcade0253ffdc
MATERIALIZER_EVIDENCE_JSON_SHA256=4eefdfbaee5be91c594d5f0203270ce52a42ec71538659c5484d436a3eb7e65c
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
FORBIDDEN_SAMPLE_H7_FIXTURE_AS_CATALOG=true
~~~

The H=7 fixture hash is a single-window predicate-pass example only. It is not
registry evidence and must not be cited as dataset completeness or catalog coverage.

## 2. Registry purpose and verification unit

### 2.1 Catalog grain

The evaluation instance registry is a versioned master catalog at amendment cell
grain:

~~~text
REGISTRY_ROW_GRAIN=SEASON,FARM,SUBFARM,VARIETY,MODEL,FORECAST_CUTOFF,FORECAST_QUANTILE
REGISTRY_PARTITION_SCOPE=TRAIN,VALIDATION
~~~

Each registry row identifies one in-scope evaluation instance **cell**. It does
not substitute S2 harvest-grain row enumeration, farm pick-day lists, or sparse
V0.2 `S3BindingRow` rows as a complete V0.3 catalog.

### 2.2 Verification unit

Dataset completeness verification operates on the Cartesian product:

~~~text
VERIFICATION_UNIT=IN_SCOPE_CELL × H
H ∈ {7,14,21}
~~~

For each verification unit, the materializer produces a daily rowset window and
`CompletenessVerifier` evaluates amendment §8.1 five predicates. A dataset-level
PASS requires every in-scope verification unit to PASS; sampling or representative
subset PASS is forbidden.

~~~text
COMPLETENESS_PREDICATE_1=FULL_CALENDAR_DAY_COVERAGE_IN_WINDOW
COMPLETENESS_PREDICATE_2=NO_SILENT_MISSING_DAYS
COMPLETENESS_PREDICATE_3=NO_ZERO_FILL_FOR_UNKNOWN
COMPLETENESS_PREDICATE_4=OBSERVED_KG_TRACEABLE_TO_SOURCE_002_GRAIN
COMPLETENESS_PREDICATE_5=FORECAST_DAILY_CURVE_VISIBLE_AT_CUTOFF
~~~

## 3. Inclusion and exclusion rules

### 3.1 Partition scope

~~~text
S3_EVALUATION_PARTITIONS=TRAIN,VALIDATION
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
TEST_PARTITION_DATES=2026-03-10..2026-04-16
~~~

Only TRAIN and VALIDATION cells may appear in the in-scope registry. TEST remains
sealed. Any evaluation window intersecting TEST partition dates is REJECTED.

### 3.2 Cell-level exclusion (out of catalog)

Cells excluded at S3-A cell grain do not enter the in-scope registry and have no
evaluation window:

~~~text
CELL_LEVEL_EXCLUDED_NO_WINDOW=true
FORBIDDEN_VARIETIES=普鲜,普青,普冻,废果
FORBIDDEN_FACTORY_BASON=true
DEFAULT_SEASON_MONTH_SCOPE=1-4
NON_IN_SEASON_MONTHS_EXCLUDED=true
~~~

### 3.3 COMPLETE_SEASON and TEST intersection

`COMPLETE_SEASON` windows (January 1 – April 30 of season year, Asia/Shanghai)
intersect the sealed TEST partition (`2026-03-10..2026-04-16`). Such windows
remain materializer `REJECT` / `TEST_PARTITION_NOT_ALLOWED`. The registry must not
treat `COMPLETE_SEASON` coverage as a dataset completeness PASS.

~~~text
COMPLETE_SEASON_TEST_INTERSECTION_REMAINS_REJECT=true
COMPLETE_SEASON_IS_NOT_DATASET_COMPLETENESS_PASS=true
~~~

### 3.4 Forbidden catalog substitutions

~~~text
FORBIDDEN_FARM_PICK_DAY_ENUMERATION_AS_FORECAST_CUTOFF=true
FORBIDDEN_S2_HARVEST_GRAIN_CATALOG_AS_EVALUATION_INSTANCE_REGISTRY=true
FORBIDDEN_V0_2_S3_BINDING_ROWS_AS_V0_3_COMPLETE_REGISTRY=true
FORBIDDEN_INVENT_CUTOFFS=true
FORBIDDEN_INVENT_CELL_ROWS=true
~~~

V0.2 `S3BindingRow` field names may be used only as grain reference. Claiming that
sparse 7/14/21 binding rows already constitute the V0.3 complete evaluation
instance catalog is forbidden.

## 4. Registry source authority and fail-closed state

### 4.1 Current repository state

As of this contract freeze, the repository has **no** bindable, versioned
incumbent evaluation instance master catalog:

~~~text
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
REGISTRY_SOURCE_STATUS=NOT_MATERIALIZED_OR_NOT_BOUND
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=false
~~~

### 4.2 Fail-closed prohibitions

While `EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false`:

~~~text
FORBIDDEN_INVENT_CUTOFFS=true
FORBIDDEN_INVENT_CELL_ROWS=true
FORBIDDEN_SAMPLE_H7_FIXTURE_AS_CATALOG=true
FORBIDDEN_HANDWRITTEN_FARM_LISTS=true
FORBIDDEN_HANDWRITTEN_CUTOFF_LISTS=true
FORBIDDEN_HANDWRITTEN_CELL_COUNTS=true
DO_NOT_INVENT_REGISTRY_HASH=true
~~~

No agent may hand-write farm lists, cutoff lists, cell counts, or registry
identity hashes to impersonate a catalog. Empty or unbound catalog is not VERIFIED.

### 4.3 Future registry binding requirements

A future registry implementation must expose, at minimum:

- versioned registry identity (content hash or manifest hash)
- authoritative source lineage (incumbent model replay + accepted S2 partition binding)
- explicit in-scope cell enumeration at amendment grain
- partition label per cell (`TRAIN` or `VALIDATION`)
- binding to `DATASET_ID=source-002` and `DATASET_VERSION=e5-live-v1`

Until such a binding exists and is accepted in a coordinator-reviewed closeout,
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE` remains `false`.

## 5. Dataset-level VERIFIED necessary and sufficient conditions

This contract defines when `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=true`
may be claimed. **This PR does not claim any condition is satisfied.**

### 5.1 Necessary conditions (all required)

~~~text
REQUIREMENT_1=EVALUATION_INSTANCE_REGISTRY_AVAILABLE=true
REQUIREMENT_2=EVERY_IN_SCOPE_VERIFICATION_UNIT_PASSES_ALL_FIVE_PREDICATES
REQUIREMENT_3=NO_SAMPLING_OR_REPRESENTATIVE_H7_SUBSET_PASS
REQUIREMENT_4=NON_EMPTY_BOUND_REGISTRY_REQUIRED
REQUIREMENT_5=NO_SILENT_DENOMINATOR_DROP_EXCEPT_CELL_LEVEL_EXCLUDED
~~~

Concretely:

1. `EVALUATION_INSTANCE_REGISTRY_AVAILABLE=true` after future implementation and
   closeout acceptance.
2. For **each** in-scope cell × each `H ∈ {7,14,21}`, `CompletenessVerifier` reports
   all five predicates PASS on the materialized window.
3. Single-window H=7 fixture success does **not** substitute for full catalog coverage.
4. Empty catalog or unbound registry ≠ VERIFIED.
5. Any unit with `UNKNOWN`, day-level `EXCLUDED`, `FORECAST_UNAVAILABLE`,
   `TEST` intersection, or `TARGET_DATE_CUTOFF_HORIZON_MISMATCH` is FAIL for that
   unit. Such units may be omitted from the denominator only when the cell is
   contractually out-of-scope via cell-level EXCLUDED rules in §3.2.

### 5.2 What this contract does not authorize

~~~text
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=NOT_PERFORMED
CURRENT_S3_DAILY_ROWSET_CONTRACT_STATUS=NOT_AVAILABLE_FROM_CURRENT_S2_BINDING
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
IMPLEMENTATION_PR_MAY_NOT_FLIP_COMPLETENESS_VERIFIED=true
COMPLETENESS_VERIFIED_CLOSEOUT_REQUIRED_FOR_LIVE_FLIP=true
~~~

While `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false`, metric blockers must
remain `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING`. Emitting
`NO_COMPLETE_NDAY_WINDOW` before completeness verification closeout is forbidden.

### 5.3 Peak and cumulative computability

~~~text
PEAK_METRICS_COMPUTABLE=false
CUMULATIVE_METRICS_COMPUTABLE=false
COMPLETE_HORIZON_METRICS_COMPUTABLE=false
PEAK_OVER_OBSERVED_DAYS_ONLY=false
P0_SUSTAINED_PEAK_WINDOW_CONFLICT=UNRESOLVED
SUSTAINED_PEAK_PASS_FORBIDDEN_UNTIL_OWNER_DECISION=true
~~~

## 6. Subtask boundaries

~~~text
S3_A_DAILY_ROWSET_AMENDMENT_CONTRACT_AUTHORIZED=true
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=true
S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED=true
S3_A2_EVALUATION_INSTANCE_REGISTRY_CONTRACT_AUTHORIZED=true
DETERMINISTIC_DAILY_ROWSET_SERVICE_IMPLEMENTED=true
DETERMINISTIC_COMPLETENESS_VERIFICATION_SERVICE_IMPLEMENTED=true
S3_B_AUTHORIZED=false
S3_C_AUTHORIZED=false
S3_D_AUTHORIZED=false
S3_BACKTEST_EXECUTION_AUTHORIZED=false
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false
next_subtask_not_implied=true
NO_STEP_IMPLIES_THE_NEXT=true
~~~

| Subtask | Status after S3-A2 contract merge |
|---|---|
| S3-A2 evaluation instance registry contract | frozen (this document) |
| Registry implementation | not implemented |
| Dataset completeness VERIFIED | not performed |
| S3-B quantile semantics | not authorized |
| S3-C backtest execution | not authorized |

## 7. LLM and deterministic service boundary

~~~text
LLM_MUST_NOT_INVENT_TONNES=true
ALL_TONNAGE_FROM_DETERMINISTIC_SERVICE=true
LLM_MUST_NOT_INVENT_REGISTRY_ROWS=true
LLM_MUST_NOT_INVENT_PREDICATE_OUTCOMES=true
~~~

LLM agents organize explanation and invoke tools. Registry contents, cell counts,
predicate outcomes, and completeness flags must come from deterministic services
and coordinator-reviewed evidence only.

## 8. Implementation authorization pointer

~~~text
S3_A2_REGISTRY_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-registry-implementation-authorization.md
S3_A2_REGISTRY_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-registry-implementation-authorization.json
EVIDENCE_JSON_SHA256=9e8031f4efc06084dd4ee783943b76d47bbd31bd54ed1976853cf2e79e5eda2a
S3_A2_EVALUATION_INSTANCE_REGISTRY_IMPLEMENTATION_AUTHORIZED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
AUTHORIZATION_MERGE_DOES_NOT_EXECUTE_REGISTRY=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

Live `S3_A2_EVALUATION_INSTANCE_REGISTRY_IMPLEMENTATION_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and the authorization package above.
This pointer does not rewrite contract freeze rules in §§1–7.

## 9. Registry implementation pointer

~~~text
S3_A2_REGISTRY_IMPLEMENTATION_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-registry-implementation-r1.md
S3_A2_REGISTRY_IMPLEMENTATION_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-registry-implementation-r1.json
EVIDENCE_JSON_SHA256=8fe740675e0dbe0ad3a4a4c85a5786262877d12fd2c8e704899bef8ffda2f43e
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
IMPLEMENTATION_R1_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_R1_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
~~~

Live `EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED` authority:
`docs/v0-3/development-plan.md` §4.4 and this implementation package.
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE` may flip only in a future
coordinator-reviewed registry closeout, not in R1 implementation.

## 10. Catalog binding contract pointer

~~~text
S3_A2_CATALOG_BINDING_CONTRACT_PATH=docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md
S3_A2_CATALOG_BINDING_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-catalog-binding-contract.md
S3_A2_CATALOG_BINDING_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-catalog-binding-contract.json
EVIDENCE_JSON_SHA256=1122134e91610eb88c5521fce3ffe76d4e7e9a05ff02b8c719cf8459daac2a4b
S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_CONTRACT_AUTHORIZED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CONTRACT_MERGE_DOES_NOT_BIND_CATALOG=true
BINDING_IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

Live `S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_CONTRACT_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and this catalog binding contract package.
This pointer does not rewrite A2 contract freeze rules in §§1–7.
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE` may flip only in a future
coordinator-reviewed closeout, not in this contract merge.

## 11. Catalog binding implementation authorization pointer

~~~text
S3_A2_CATALOG_BINDING_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-catalog-binding-authorization.md
S3_A2_CATALOG_BINDING_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-catalog-binding-authorization.json
EVIDENCE_JSON_SHA256=22b8e4bd0c8d530008afd42b3f9213f4c47b4870b5709576ea7993725cf9f379
S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_IMPLEMENTATION_AUTHORIZED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
AUTHORIZATION_MERGE_DOES_NOT_BIND_CATALOG=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

Live `S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_IMPLEMENTATION_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and the authorization package above.
This pointer does not rewrite A2 contract freeze rules in §§1–7.

## 12. Catalog binding implementation pointer

~~~text
S3_A2_CATALOG_BINDING_IMPLEMENTATION_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-catalog-binding-implementation-r1.md
S3_A2_CATALOG_BINDING_IMPLEMENTATION_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-catalog-binding-implementation-r1.json
EVIDENCE_JSON_SHA256=d86ad33cba6299a1b58a28598d82a90b20b53fb73700e037919698e89ef24ae5
DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_BINDING_SERVICE_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
IMPLEMENTATION_R1_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_R1_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
~~~

Live `DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_BINDING_SERVICE_IMPLEMENTED` authority:
`docs/v0-3/development-plan.md` §4.4 and this implementation package.
R1 delivers the in-memory structural validator only; it does not bind a live
catalog or flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`.

## 13. Catalog artifact contract pointer

~~~text
S3_A2_CATALOG_ARTIFACT_CONTRACT_PATH=docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md
S3_A2_CATALOG_ARTIFACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-catalog-artifact-contract.md
S3_A2_CATALOG_ARTIFACT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-catalog-artifact-contract.json
EVIDENCE_JSON_SHA256=501dcf1034e615f60ca9b76b79cbbe8f9d352c3ea85abf4380d763842ddd4ca6
S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_CONTRACT_AUTHORIZED=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CONTRACT_MERGE_DOES_NOT_PRODUCE_CATALOG=true
CONTRACT_MERGE_DOES_NOT_BIND_CATALOG=true
~~~

Live `S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_CONTRACT_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and this catalog artifact contract package.
This pointer does not rewrite A2 contract freeze rules in §§1–7.

## 14. Catalog artifact production authorization pointer

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
This pointer does not rewrite A2 contract freeze rules in §§1–7.

## 15. Catalog artifact production R1 pointer

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
This pointer does not rewrite A2 contract freeze rules in §§1–7.

## 16. Incumbent forecast artifact contract pointer

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
This pointer does not rewrite A2 contract freeze rules in §§1–7.

## 17. Incumbent forecast artifact implementation authorization pointer

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
This pointer does not rewrite A2 contract freeze rules in §§1–7.

## 18. Incumbent forecast artifact adapter R1 pointer

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_ADAPTER_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-adapter-r1.md
S3_A2_INCUMBENT_FORECAST_ARTIFACT_ADAPTER_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-adapter-r1.json
EVIDENCE_JSON_SHA256=31bb6d24cf4c398eeea86c18d2dece16b9e0ab6f704e9ab229eac5a363d296a0
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTHORIZED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
IMPLEMENTATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
~~~

Live `DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED` is maintained in
`docs/v0-3/development-plan.md` §4.4 and this R1 package.
This pointer does not rewrite A2 contract freeze rules in §§1–7.

## 19. S2 identity alignment contract pointer

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-contract.md
S3_A2_S2_IDENTITY_ALIGNMENT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-contract.md
S3_A2_S2_IDENTITY_ALIGNMENT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-contract.json
EVIDENCE_JSON_SHA256=e69478f732675f04e3c981d99676b6f28e6bf7ddee43a7af7174f0a75802212a
S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=false
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_ALIGNMENT_ADAPTER=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

Live `S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and the S2 identity alignment contract package above.
This pointer does not rewrite A2 contract freeze rules in §§1–7.

## 20. S2 identity alignment implementation authorization pointer

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-authorization.md
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-authorization.json
EVIDENCE_JSON_SHA256=1d1b213e6a31e899ce777440f1f1dce63be66006520e417775cdb330d335221d
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=false
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_ALIGNMENT_ADAPTER=true
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_CATALOG=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

Live `S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED` authority:
`docs/v0-3/development-plan.md` §4.4 and the implementation authorization package above.
This pointer does not rewrite A2 contract freeze rules in §§1–7.
