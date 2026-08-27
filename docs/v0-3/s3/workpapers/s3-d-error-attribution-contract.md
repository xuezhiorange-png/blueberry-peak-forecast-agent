# V0.3-S3-D Error attribution contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_D_ERROR_ATTRIBUTION_CONTRACT
ARTIFACT_VERSION=s3-d-error-attribution-contract-v1
TASK_ID=V03_S3_D_ERROR_ATTRIBUTION_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_D_ERROR_ATTRIBUTION_CONTRACT_ONLY
SLICE=V0.3-S3
PARALLEL_LANE=S3-D
ENGLISH_ID=ERROR_ATTRIBUTION_MATRIX_EXECUTION
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=2b0ea55872542501fff246c9d87c6fda7ae8802f
BASE_MAIN_TREE_SHA=6b50a3f1b6fbc38dd106153c0e63e2d2630b1271
CONTRACT_PATH=docs/v0-3/s3/s3-error-attribution-contract.md
CONTRACT_VERSION=v0-3-s3-d-error-attribution-contract-v1
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-d-error-attribution-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-d-error-attribution-contract.json
NO_STEP_IMPLIES_THE_NEXT=true
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_R1=true
THIS_DRAFT_IS_NOT_READY=true
DEVELOPMENT_PLAN_UNCHANGED=true
~~~

This workpaper records the S3-D error attribution **contract freeze** after user
authorization 「可以下一步」. This PR defines how a future authorized attribution
runner must structure error dimensions, candidate causes, multi-label semantics,
and honest `NOT_COMPUTABLE` handling. It does not execute attribution, authorize
`S3_D_ATTRIBUTION_EXECUTION_AUTHORIZED`, insert live §4.4 flags, run backtests,
read TEST, read SOURCE_002 row-level data, or change the model.

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
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

`S3_D_ERROR_ATTRIBUTION_CONTRACT_AUTHORIZED=true` (file fence) ≠ live §4.4
authority ≠ `S3_D_ATTRIBUTION_EXECUTION_AUTHORIZED` ≠ attribution executed ≠
`ERROR_DIAGNOSIS=true` ≠ contribution rates computed ≠ S4 authorized ≠ C0
backtest run ≠ completeness verified ≠ C0 §5 rewritten ≠ `NO_VERSIONED` flipped.
This evidence JSON is not an attribution matrix package, backtest package, or
versioned forecast artifact. Catalog first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.

## 1. Parent bindings (not reopened)

### 1.1 P0 contract (#298)

~~~text
PARENT_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
PARENT_P0_PR=298
PARENT_P0_MERGE=0a6f412aad63e1f66a5e14e5960ca88deb9b2dcd
P0_SECTION_9_ERROR_ATTRIBUTION_BINDING=authoritative_semantics
CURRENT_P0_CONTRACT_GIT_BLOB_SHA=9185de110ded647e07a501fa5dbf43874f844381
P0_EVIDENCE_JSON_SHA256=580f09e306e4e32db0e72d65158d455bd9fea57b4279497909ff0d54cb91259c
~~~

S3-D inherits P0 §9 error attribution semantics. This contract does not reopen
P0 §6 sustained-peak 3 vs 7 conflict resolution.

### 1.2 S3-C0 execution contract (#302) and execution grant (#391)

~~~text
CURRENT_S3_C0_CONTRACT_GIT_BLOB_SHA=3d86de10946af7d319c663a8a681977799f2466d
PARENT_S3_C0_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=3850b7cc85fa87d2cf7aa1b4fb23c3d756d6295b
PARENT_S3_C_EXECUTION_GRANT_PR=391
PARENT_S3_C_EXECUTION_GRANT_MERGE=2b0ea55872542501fff246c9d87c6fda7ae8802f
GRANT_EVIDENCE_JSON_SHA256=607bebc01bd136f0c38abaa23c2dff9ac393a2cf7d0c10537977a6dfd005c5c0
CURRENT_S3_C_BACKTEST_EXECUTION_STATUS=NOT_PERFORMED
~~~

Attribution execution depends on future legal backtest diagnostics. This
contract does not claim C0 backtest has run.

### 1.3 Sibling bindings at base

~~~text
CURRENT_S3_A_AMENDMENT_GIT_BLOB_SHA=66a50422d24166af8e9ed4c6d4feb7ea86dd4238
CURRENT_DEVELOPMENT_PLAN_GIT_BLOB_SHA_AT_BASE=b9e282caa3c83f71ec64322d6b8298ec70a944bb
CURRENT_S3_B_CONTRACT_GIT_BLOB_SHA=43c07b3ca032e39b339281acdba4e9ad8219307b
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
ALIGNMENT_SECTION_6_SHA256=2eaf3719b1cb2e7097c6ded457098a0563b46c0965eabf38d60327b1a6b2a7a8
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
~~~

## 2. Inherited P0 §9 semantics (frozen)

~~~text
MULTI_LABEL_ATTRIBUTION=true
MULTI_LABEL_CONTRIBUTIONS_MUTUALLY_EXCLUSIVE=false
MULTI_LABEL_CONTRIBUTIONS_MAY_OVERLAP=true
ESTIMATED_CONTRIBUTION_STATUS=COMPUTED|NOT_COMPUTABLE
NOT_COMPUTABLE_CONTRIBUTION_IS_NOT_ZERO=true
MANUAL_REVIEW_CANNOT_AUTHORIZE_MODEL_CHANGE=true
TWO_LAYER_ATTRIBUTION=true
STRICT_CAUSAL_DECOMPOSITION=false
UNEXPLAINED_RESIDUAL_MUST_REMAIN_VISIBLE=true
~~~

## 3. Frozen error dimensions and candidate causes

Error dimensions (definition only): quantity-level, maturity-timing, single-day
peak, seven-day peak (P0 §6 3 vs 7 `UNRESOLVED`; this contract does not
choose), season-cumulative, quantile-calibration.

Candidate causes (definition only): phenology input, weather response, harvest
capacity, marketable rate, mature inventory, master data, data quality, unknown
residual.

## 4. Honest blockers at freeze time

~~~text
CURRENT_S3_C_BACKTEST_EXECUTION_STATUS=NOT_PERFORMED
NO_LEGAL_BACKTEST_PACKAGE=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
CURRENT_P50_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P80_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P90_SEMANTICS_STATUS=VERIFICATION_FAILED
QUANTILE_CALIBRATION_DIMENSION_COMPUTABLE=false
C0_SECTION_5_PENDING_NOT_MERGED_REMAINS_HISTORICAL_SNAPSHOT=true
FORBIDDEN_REWRITE_C0_SECTION_5=true
~~~

## 5. Contract-only boundary

~~~text
CONTRACT_MERGE_DOES_NOT_AUTHORIZE_ATTRIBUTION=true
CONTRACT_FILE_FENCE_IS_NOT_LIVE_REGISTRY_AUTHORITY=true
S3_D_ATTRIBUTION_EXECUTION_REQUIRES_SEPARATE_AUTHORIZATION=true
LIVE_SECTION_4_4_INSERT_NOT_IN_THIS_PR=true
DEVELOPMENT_PLAN_UNCHANGED=true
~~~

Same gap type as C0 #302 → #390 live-authority path. This contract freeze does
not fill live §4.4.

## 6. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=1b9524cc80d1dfc5a5f6ef2fe174007c929f42ef6a7b313aa0f09d95eaad692a
~~~

## 7. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
