# V0.3-S3-D Error Attribution Contract

## Contract identity and phase boundary

~~~text
CONTRACT_ID=V0_3_S3_D_ERROR_ATTRIBUTION_CONTRACT
CONTRACT_VERSION=v0-3-s3-d-error-attribution-contract-v1
TASK_ID=V03_S3_D_ERROR_ATTRIBUTION_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_D_ERROR_ATTRIBUTION_CONTRACT_ONLY
SLICE=V0.3-S3
PARALLEL_LANE=S3-D
ENGLISH_ID=ERROR_ATTRIBUTION_MATRIX_EXECUTION
USER_GATE=可以下一步
CONTRACT_ONLY=true
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_R1=true
THIS_DRAFT_IS_NOT_READY=true
DEVELOPMENT_PLAN_UNCHANGED=true
BASE_REF=origin/main
BASE_MAIN_SHA=2b0ea55872542501fff246c9d87c6fda7ae8802f
BASE_MAIN_TREE_SHA=6b50a3f1b6fbc38dd106153c0e63e2d2630b1271
PARENT_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
PARENT_P0_PR=298
PARENT_P0_MERGE=0a6f412aad63e1f66a5e14e5960ca88deb9b2dcd
P0_SECTION_9_ERROR_ATTRIBUTION_BINDING=authoritative_semantics
CURRENT_P0_CONTRACT_GIT_BLOB_SHA=9185de110ded647e07a501fa5dbf43874f844381
P0_EVIDENCE_JSON_SHA256=580f09e306e4e32db0e72d65158d455bd9fea57b4279497909ff0d54cb91259c
CURRENT_S3_C0_CONTRACT_GIT_BLOB_SHA=3d86de10946af7d319c663a8a681977799f2466d
PARENT_S3_C0_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=3850b7cc85fa87d2cf7aa1b4fb23c3d756d6295b
CURRENT_S3_A_AMENDMENT_GIT_BLOB_SHA=66a50422d24166af8e9ed4c6d4feb7ea86dd4238
CURRENT_DEVELOPMENT_PLAN_GIT_BLOB_SHA_AT_BASE=b9e282caa3c83f71ec64322d6b8298ec70a944bb
CURRENT_S3_B_CONTRACT_GIT_BLOB_SHA=43c07b3ca032e39b339281acdba4e9ad8219307b
PARENT_S3_C_EXECUTION_GRANT_PR=391
PARENT_S3_C_EXECUTION_GRANT_MERGE=2b0ea55872542501fff246c9d87c6fda7ae8802f
GRANT_EVIDENCE_JSON_SHA256=607bebc01bd136f0c38abaa23c2dff9ac393a2cf7d0c10537977a6dfd005c5c0
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
ALIGNMENT_SECTION_6_SHA256=2eaf3719b1cb2e7097c6ded457098a0563b46c0965eabf38d60327b1a6b2a7a8
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
NO_STEP_IMPLIES_THE_NEXT=true
~~~

~~~text
S3_D_ERROR_ATTRIBUTION_CONTRACT_AUTHORIZED=true
S3_D_ATTRIBUTION_EXECUTION_AUTHORIZED=false
S3_D_AUTHORIZED=false
ERROR_DIAGNOSIS=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
TEST_REMAINS_SEALED=true
SOURCE_002_ROW_LEVEL_READ=false
LLM_MUST_NOT_INVENT_TONNES=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This document freezes the V0.3-S3-D error attribution **execution contract**.
It defines how a future authorized attribution runner must structure error
dimensions, candidate causes, multi-label contribution semantics, and honest
`NOT_COMPUTABLE` handling over TRAIN/VALIDATION diagnostics. It is a governance
contract, not an attribution run, matrix package, backtest run, or S4
authorization.

Merging this contract does **not** authorize attribution execution, live
§4.4 insertion, TEST evaluation, production or test code, or model change.
`S3_D_ATTRIBUTION_EXECUTION_AUTHORIZED` remains `false` after merge.
`ERROR_DIAGNOSIS` remains `false` after merge.

`S3_D_ERROR_ATTRIBUTION_CONTRACT_AUTHORIZED=true` (file fence) ≠ live §4.4
authority ≠ `S3_D_ATTRIBUTION_EXECUTION_AUTHORIZED` ≠ attribution executed ≠
`ERROR_DIAGNOSIS=true` ≠ contribution rates computed ≠ S4 authorized ≠ C0
backtest run ≠ completeness verified ≠ C0 §5 rewritten ≠ `NO_VERSIONED` flipped.
This evidence JSON is not an attribution matrix package, backtest package, or
versioned forecast artifact. Catalog first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.

## 1. Inherited authority (not reopened)

### 1.1 Parent S3 P0 contract

~~~text
PARENT_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
PARENT_P0_PR=298
PARENT_P0_MERGE=0a6f412aad63e1f66a5e14e5960ca88deb9b2dcd
P0_SECTION_9_ERROR_ATTRIBUTION_BINDING=authoritative_semantics
CURRENT_P0_CONTRACT_GIT_BLOB_SHA=9185de110ded647e07a501fa5dbf43874f844381
P0_EVIDENCE_JSON_SHA256=580f09e306e4e32db0e72d65158d455bd9fea57b4279497909ff0d54cb91259c
P0_SUBTASK_NAME=Error attribution matrix execution
~~~

P0 §11 names S3-D as 「Error attribution matrix execution」. P0 §9 binds the
semantic rules frozen here. This contract does not reopen P0 §10 acceptance
gates or P0 §11 subtask authorization table freeze snapshots.

### 1.2 S3-C0 backtest execution contract and grant

~~~text
S3_C0_CONTRACT_PATH=docs/v0-3/s3/s3-pit-backtest-execution-contract.md
CURRENT_S3_C0_CONTRACT_GIT_BLOB_SHA=3d86de10946af7d319c663a8a681977799f2466d
PARENT_S3_C0_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=3850b7cc85fa87d2cf7aa1b4fb23c3d756d6295b
PARENT_S3_C_EXECUTION_GRANT_PR=391
PARENT_S3_C_EXECUTION_GRANT_MERGE=2b0ea55872542501fff246c9d87c6fda7ae8802f
GRANT_EVIDENCE_JSON_SHA256=607bebc01bd136f0c38abaa23c2dff9ac393a2cf7d0c10537977a6dfd005c5c0
CURRENT_S3_C_BACKTEST_EXECUTION_STATUS=NOT_PERFORMED
~~~

Attribution consumes versioned backtest diagnostics when they exist. This
contract does **not** claim `S3_C_BACKTEST_EXECUTION_AUTHORIZED` has produced a
legal backtest package. `CURRENT_S3_C_BACKTEST_EXECUTION_STATUS=NOT_PERFORMED`
at base.

### 1.3 S3-A amendment and S3-B quantile semantics

~~~text
CURRENT_S3_A_AMENDMENT_GIT_BLOB_SHA=66a50422d24166af8e9ed4c6d4feb7ea86dd4238
CURRENT_S3_B_CONTRACT_GIT_BLOB_SHA=43c07b3ca032e39b339281acdba4e9ad8219307b
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_P50_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P80_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P90_SEMANTICS_STATUS=VERIFICATION_FAILED
~~~

S3-D inherits missing-day and metric-computability semantics from S3-A. It does
not reopen S3-B coverage execution or repair `VERIFICATION_FAILED`.

### 1.4 C0 §5 evaluation window anchor (historical snapshot; do not rewrite)

~~~text
C0_SECTION_5_TITLE=Evaluation window anchor (S3-A1 pending)
S3_A1_EVALUATION_WINDOW_ANCHOR_STATUS=PENDING_NOT_MERGED
S3_C0_MUST_NOT_INVENT_ALTERNATE_WINDOW_ANCHOR=true
FORBIDDEN_REWRITE_C0_SECTION_5=true
~~~

This contract records C0 §5 as a historical freeze snapshot. It does not rewrite
C0 §5 or invent an alternate window anchor.

## 2. Error attribution semantics (P0 §9 binding)

Error attribution has **two layers** and is **not** a strict causal
decomposition. Multiple candidate causes are allowed per error dimension;
contributions may overlap; unexplained residuals must remain visible.

~~~text
TWO_LAYER_ATTRIBUTION=true
STRICT_CAUSAL_DECOMPOSITION=false
MULTI_LABEL_ATTRIBUTION=true
MULTI_LABEL_CONTRIBUTIONS_MUTUALLY_EXCLUSIVE=false
MULTI_LABEL_CONTRIBUTIONS_MAY_OVERLAP=true
ESTIMATED_CONTRIBUTION_STATUS=COMPUTED|NOT_COMPUTABLE
NOT_COMPUTABLE_CONTRIBUTION_IS_NOT_ZERO=true
MANUAL_REVIEW_CANNOT_AUTHORIZE_MODEL_CHANGE=true
UNEXPLAINED_RESIDUAL_MUST_REMAIN_VISIBLE=true
~~~

A future runner must emit, per error dimension and evaluation instance:

1. **Layer 1 — error magnitude**: signed or unsigned error against the
   incumbent forecast diagnostic for that dimension, with explicit
   `COMPUTED` / `NOT_COMPUTABLE` status.
2. **Layer 2 — candidate cause attribution**: estimated contribution shares or
   intervals per candidate cause, each with `COMPUTED` / `NOT_COMPUTABLE`
   status. Overlapping multi-label contributions are permitted.

`NOT_COMPUTABLE` contribution is **not** zero. `NOT_COMPUTABLE` is not `PASS`.
Manual review may annotate but cannot authorize model or parameter change.

## 3. Required error dimensions (frozen enumeration)

| Dimension ID | Description | Notes at contract freeze |
|---|---|---|
| `quantity_level` | Aggregate quantity error vs actuals | Requires legal paired diagnostics |
| `maturity_timing` | Timing of maturity curve vs actual harvest timing | Not a causal claim |
| `single_day_peak` | Single-day peak error | Requires peak metric computability |
| `seven_day_peak` | Sustained peak error (7-day window per P0 §9) | P0 §6 3 vs 7 `UNRESOLVED`; this contract does **not** choose |
| `season_cumulative` | Season-cumulative error | Requires complete-horizon rowset semantics |
| `quantile_calibration` | P50/P80/P90 calibration error | Blocked while quantile semantics `VERIFICATION_FAILED` |

~~~text
REQUIRED_ERROR_DIMENSIONS=quantity_level,maturity_timing,single_day_peak,seven_day_peak,season_cumulative,quantile_calibration
PRODUCT_SUSTAINED_PEAK_WINDOW_DAYS=3
PLAN_SUSTAINED_PEAK_WINDOW_DAYS=7
P0_SUSTAINED_PEAK_WINDOW_CONFLICT=UNRESOLVED
P0_DOES_NOT_RESOLVE_3_VS_7=true
S3_D_DOES_NOT_RESOLVE_3_VS_7=true
SUSTAINED_PEAK_PASS_FORBIDDEN_UNTIL_OWNER_DECISION=true
QUANTILE_CALIBRATION_DIMENSION_COMPUTABLE=false
~~~

Until P0 §6 sustained-peak conflict is owner-resolved, a future runner must
record both single-day peak and the P0-named seven-day peak dimension without
claiming sustained-peak `PASS` or choosing 3-day vs 7-day product binding.

## 4. Candidate causes (frozen enumeration)

| Cause ID | Description |
|---|---|
| `phenology_input` | Phenology / maturity curve input assumptions |
| `weather_response` | Weather response in forecast pathway |
| `harvest_capacity` | Harvest capacity constraints |
| `marketable_rate` | Marketable / commodity rate assumptions |
| `mature_inventory` | Mature inventory carry assumptions |
| `master_data` | Farm, variety, or master-data binding errors |
| `data_quality` | Source visibility, pairing, or completeness defects |
| `unknown_residual` | Unexplained residual (must remain visible) |

~~~text
REQUIRED_CANDIDATE_CAUSES=phenology_input,weather_response,harvest_capacity,marketable_rate,mature_inventory,master_data,data_quality,unknown_residual
UNKNOWN_RESIDUAL_REQUIRED=true
~~~

## 5. Inputs and prerequisites (definition only)

A future authorized attribution runner may consume only:

- versioned PIT backtest diagnostic artifacts produced under S3-C0 contract
  rules, when they exist and are legally bound;
- S3-A daily rowset amendment semantics for missing-day and computability;
- verified quantile semantics when `CURRENT_P*_SEMANTICS_STATUS` permits
  calibration attribution;
- deterministic metric service outputs with explicit status fields.

~~~text
INPUT_REQUIRES_LEGAL_BACKTEST_PACKAGE=true
INPUT_REQUIRES_EXPLICIT_STATUS_FIELDS=true
FORBIDDEN_INVENT_TONNES=true
FORBIDDEN_INVENT_CONTRIBUTION_RATES=true
FORBIDDEN_WRITE_NOT_COMPUTABLE_AS_ZERO=true
FORBIDDEN_SOURCE_002_ROW_LEVEL_READ=true
FORBIDDEN_TEST_READ=true
FORBIDDEN_TEST_EVALUATION=true
~~~

## 6. Honest blockers at contract freeze

The following blockers are recorded at base `2b0ea558`. This contract does not
flip them.

~~~text
CURRENT_S3_C_BACKTEST_EXECUTION_STATUS=NOT_PERFORMED
NO_LEGAL_BACKTEST_PACKAGE=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_P50_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P80_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P90_SEMANTICS_STATUS=VERIFICATION_FAILED
QUANTILE_CALIBRATION_DIMENSION_COMPUTABLE=false
ERROR_DIAGNOSIS=false
V0_3_S4_AUTHORIZED=false
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
~~~

## 7. Forbidden inputs and actions

~~~text
FORBIDDEN_INVENT_TONNES=true
FORBIDDEN_INVENT_CONTRIBUTION_RATES=true
FORBIDDEN_WRITE_NOT_COMPUTABLE_AS_ZERO=true
FORBIDDEN_MANUAL_REVIEW_AUTHORIZE_MODEL_CHANGE=true
FORBIDDEN_CLAIM_S4_AUTHORIZED_FROM_ATTRIBUTION=true
FORBIDDEN_UNSEAL_TEST=true
FORBIDDEN_SOURCE_002_ROW_LEVEL_READ=true
FORBIDDEN_ATTRIBUTION_RUN_IN_THIS_TASK=true
FORBIDDEN_LIVE_SECTION_4_4_INSERT_IN_THIS_TASK=true
FORBIDDEN_REWRITE_C0_SECTION_5=true
FORBIDDEN_REWRITE_DEVELOPMENT_PLAN=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 8. Subtask boundaries

~~~text
S3_D_ERROR_ATTRIBUTION_CONTRACT_AUTHORIZED=true
S3_D_ATTRIBUTION_EXECUTION_AUTHORIZED=false
S3_D_AUTHORIZED=false
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false
ERROR_DIAGNOSIS=false
next_subtask_not_implied=true
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_MERGE_DOES_NOT_AUTHORIZE_ATTRIBUTION=true
CONTRACT_FILE_FENCE_IS_NOT_LIVE_REGISTRY_AUTHORITY=true
S3_D_ATTRIBUTION_EXECUTION_REQUIRES_SEPARATE_AUTHORIZATION=true
LIVE_SECTION_4_4_INSERT_NOT_IN_THIS_PR=true
DEVELOPMENT_PLAN_UNCHANGED=true
~~~

| Subtask | Status after S3-D contract merge |
|---|---|
| S3-D error attribution contract | frozen (this document) |
| S3-D attribution execution | not authorized |
| S3-C backtest execution | not performed at base |
| S3 metric execution | not authorized |
| S3-B quantile coverage execution | not authorized |
| S4 improvement implementation | not authorized |

Future `S3_D_ATTRIBUTION_EXECUTION_AUTHORIZED` and live `docs/v0-3/development-plan.md`
§4.4 insertion require a **separate** grant or live-authority PR. This contract
freeze does not perform that step (same gap type as C0 #302 → #390).

## 9. LLM and deterministic service boundary

~~~text
LLM_MUST_NOT_INVENT_TONNES=true
ALL_TONNAGE_AND_CONTRIBUTION_RATES_FROM_DETERMINISTIC_SERVICE=true
DETERMINISTIC_ATTRIBUTION_SERVICE_IMPLEMENTED_IN_S3_D=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

LLM agents organize explanations and invoke tools only. All tonnage, intervals,
contribution rates, and pass/fail thresholds must come from deterministic
services. S3-D contract merge does not implement those services.

## 10. Contract merge effect

~~~text
CONTRACT_MERGE_DOES_NOT_AUTHORIZE_ATTRIBUTION=true
CONTRACT_MERGE_DOES_NOT_EXECUTE_ATTRIBUTION=true
CONTRACT_MERGE_DOES_NOT_AUTHORIZE_BACKTEST=true
CONTRACT_MERGE_DOES_NOT_FLIP_ERROR_DIAGNOSIS=true
CONTRACT_MERGE_DOES_NOT_AUTHORIZE_S4=true
CONTRACT_MERGE_DOES_NOT_TOUCH_PYTHON=true
CONTRACT_FILE_FENCE_IS_NOT_LIVE_REGISTRY_AUTHORITY=true
DEVELOPMENT_PLAN_UNCHANGED=true
~~~

## 11. Evidence cross-reference

~~~text
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-d-error-attribution-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-d-error-attribution-contract.json
~~~

Evidence digest is recorded in the workpaper and evidence JSON. This contract
file does not embed runtime attribution results.
