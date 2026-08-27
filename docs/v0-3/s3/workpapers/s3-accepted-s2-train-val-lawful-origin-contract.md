# V0.3-S3-A2 Accepted S2 TRAIN/VALIDATION lawful-origin contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-accepted-s2-train-val-lawful-origin-contract-v1
TASK_ID=V03_S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_CONTRACT_ONLY
SLICE=V0.3-S3
PARALLEL_LANE=S3-A2-ACCEPTED-S2-ORIGIN
ENGLISH_ID=ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN
USER_GATE=授权
NEW_FAMILY_AUTHORIZATION=true
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=d3688ccbb3e213e8344f3c5a766dc9fed4a638a2
BASE_MAIN_TREE_SHA=1cac50843af7f3cab78164a517ce674261830c92
CONTRACT_PATH=docs/v0-3/s3/s3-accepted-s2-train-val-lawful-origin-contract.md
CONTRACT_VERSION=v0-3-s3-a2-accepted-s2-train-val-lawful-origin-contract-v1
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-lawful-origin-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-accepted-s2-train-val-lawful-origin-contract.json
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_R1=true
THIS_PR_IS_NOT_LIVE_AUTHORITY=true
THIS_DRAFT_IS_NOT_READY=true
DEVELOPMENT_PLAN_UNCHANGED=true
LIVE_SECTION_4_4_INSERT_NOT_IN_THIS_PR=true
~~~

This workpaper records the S3-A2 **accepted S2 TRAIN/VALIDATION lawful-origin** contract
freeze after user authorization `USER_GATE=授权` for a **new family**. Historical
source-002 data is already accepted in S2 (#296); this PR names that accepted dataset
as the lawful origin identity at the dataset-identity layer for later deterministic
binding. This is **not** `可以实施`, not a grant, not R1, not live §4.4 authority, not
kg row-level read, not identity-set member landing, not versioned forecast artifact
production, and not populated-origin freeze rewrite.

~~~text
S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_CONTRACT_AUTHORIZED=true
S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
TEST_EVALUATION_AUTHORIZED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
V0_3_S4_AUTHORIZED=false
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
CONTRACT_FILE_FENCE_IS_NOT_LIVE_REGISTRY_AUTHORITY=true
~~~

`S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_CONTRACT_AUTHORIZED=true` (file fence) ≠
live §4.4 authority ≠ implementation authorized ≠ implemented ≠
`SOURCE_002_ROW_LEVEL_READ` ≠ members landed ≠ `NO_REVIEWED` flipped ≠ versioned
forecast artifact exists ≠ `NO_VERSIONED` flipped ≠ catalog bindable ≠ completeness
`VERIFIED=true` ≠ backtest/attribution/metrics computed ≠ S3-B coverage ≠ S4 ≠ TEST
unsealed. Catalog first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.

## 1. Three-file manifest (exactly)

| # | path |
|---|------|
| 1 | `docs/v0-3/s3/s3-accepted-s2-train-val-lawful-origin-contract.md` |
| 2 | `docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-lawful-origin-contract.md` |
| 3 | `docs/v0-3/s3/evidence/s3-accepted-s2-train-val-lawful-origin-contract.json` |

No fourth file. No Python, Alembic, tests, or edits to development-plan, amendment,
P0, C0, S3-D, metric, S3-B, or any A2 identity-set / populated-origin contract.

## 2. Parent bindings (not reopened)

### 2.1 P0 contract (#298)

~~~text
PARENT_P0_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
PARENT_P0_PR=298
PARENT_P0_MERGE=0a6f412aad63e1f66a5e14e5960ca88deb9b2dcd
CURRENT_P0_CONTRACT_GIT_BLOB_SHA=1f3f1ee3be2494d56fc53f233a1cf6937638781d
P0_EVIDENCE_JSON_SHA256=580f09e306e4e32db0e72d65158d455bd9fea57b4279497909ff0d54cb91259c
FORBIDDEN_ADD_P0_SECTION_11_SIXTH_ROW=true
~~~

### 2.2 S2 accepted dataset (#296)

~~~text
S2_CONTRACT_PATH=docs/v0-3/s2/s2-materialized-dataset-contract.md
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
S2_ACCEPTANCE_PR=296
S2_ACCEPTANCE_MERGE=9aa4de9367d065dcb642ae233325640d24da69d6
S2_ACCEPTANCE_EVIDENCE_JSON_SHA256=f7856e99ded3cf4c56f1d6e4b283ccd903e35302cb06db606c6446419d76e02f
OFFICIAL_HASH_PACKAGE_EVIDENCE_JSON_SHA256=63bc6e23ce4ffec8de268e7b11d99fab007a168007b24c6498489ef6d0cc9b52
SLICE_S2_COMPLETE=PASS
~~~

### 2.3 Populated-origin closed family (#381–#383)

~~~text
PARENT_POPULATED_ORIGIN_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-identity-set-candidate-source-populated-origin-contract.md
CURRENT_POPULATED_ORIGIN_CONTRACT_GIT_BLOB_SHA=29dd5d3183a9f9bd4c096d1e8724fd6582a47caa
POPULATED_ORIGIN_CONTRACT_PR=381
POPULATED_ORIGIN_R1_PR=383
POPULATED_ORIGIN_R1_EVIDENCE_JSON_SHA256=f431cbceb91d830adfc332311dfbf052e74599080c22cd2736b1bc2f7e4c5ea4
DOES_NOT_REWRITE_POPULATED_ORIGIN_FREEZE=true
FAIL_CLOSED_NO_LAWFUL_POPULATED_ORIGIN_TODAY_REMAINS_HISTORICAL=true
~~~

### 2.4 Artifact contract (HOW, not ORIGIN)

~~~text
PARENT_ARTIFACT_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md
CURRENT_ARTIFACT_CONTRACT_GIT_BLOB_SHA=09590293c66f3e29c50df2c26aed793c90ab8df6
ARTIFACT_CONTRACT_DEFINES_HOW_NOT_THIS_FAMILY_ORIGIN=true
~~~

### 2.5 Completeness dataset-claim R1 (#401)

~~~text
PARENT_COMPLETENESS_DATASET_CLAIM_R1_PR=401
PARENT_COMPLETENESS_DATASET_CLAIM_R1_MERGE=d3688ccbb3e213e8344f3c5a766dc9fed4a638a2
COMPLETENESS_DATASET_CLAIM_R1_EVIDENCE_JSON_SHA256=c22e897c1dad6340cd00cbaced43964252505f01815ea0754257c336e627682e
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
~~~

Binding failure ≠ source-002 does not exist.

### 2.6 Sibling contracts (frozen, not edited)

~~~text
CURRENT_S3_C0_CONTRACT_GIT_BLOB_SHA=e59f8a2d255df392116c65d535ae22ae3854ae98
CURRENT_S3_D_CONTRACT_GIT_BLOB_SHA=0819f429dcaf390a97a51a674ca96405eb8ebab7
CURRENT_S3_METRIC_CONTRACT_GIT_BLOB_SHA=04ce7bac640f272bb3035bf5af755944f20bb5ce
CURRENT_S3_B_CONTRACT_GIT_BLOB_SHA=43c07b3ca032e39b339281acdba4e9ad8219307b
CURRENT_S3_A_AMENDMENT_GIT_BLOB_SHA=1c1850cf92734f16a38cfc5d1a78c2be7e4150c9
CURRENT_DEVELOPMENT_PLAN_GIT_BLOB_SHA_AT_BASE=3996a275973ecf5b91c419c5a5a06adbeb32346e
C0_R1_EVIDENCE_JSON_SHA256=632211d4c0afd3a4002dcf2bb2793fc7992663b5b0df51ef32b08e99ac70d7e2
S3_D_R1_EVIDENCE_JSON_SHA256=7bc94666a5087cace5c6f6ff6c735b62fa552cb747d76f7d4b5d6e7dc6712119
METRIC_R1_EVIDENCE_JSON_SHA256=a03fc4848028880dcd80b5f0fae51b5dde21426af4d74da64e6b62bfa0d7af30
~~~

## 3. Named lawful origin (dataset identity layer)

Official hashes copied from S2 acceptance / official hash package (not recomputed):

~~~text
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
S3_EVALUATION_PARTITIONS=TRAIN,VALIDATION
TRAIN.row_count=16224
TRAIN.content_sha256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
VALIDATION.row_count=8006
VALIDATION.content_sha256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
TEST.row_count=0
TEST_REMAINS_SEALED=true
~~~

Naming rules: dataset identity ≠ member enumeration ≠ kg row-level read ≠ versioned
forecast artifact. Contract does not enumerate farm/date/cutoff member literals.

## 4. Unique flip (file fence only)

Only `S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_CONTRACT_AUTHORIZED` flips
`false` → `true` in the new contract file (and workpaper/evidence restatement).
Companions introduced as `false`:
`S3_A2_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTATION_AUTHORIZED`,
`DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTED`.

Not flipped in this PR: `SOURCE_002_ROW_LEVEL_READ`, `NO_VERSIONED`,
`NO_REVIEWED`, `COMPLETENESS_VERIFIED`, C0/S3-D/metric STATUS, TEST seal,
S3-B coverage, S4, live §4.4 insert.

## 5. Forbidden (summary)

- Invent members, farm/date/cutoff lists, hashes, or tonnes
- `SOURCE_002_ROW_LEVEL_READ` or TEST unseal
- Live §4.4 insert; development-plan rewrite; C0 §5 rewrite; P0 §11 sixth row
- Append pointers onto A2 identity-set contracts; rewrite populated-origin freeze
- Authorize S3-B coverage or S4; touch Python / Alembic / tests
- Treat H7 fixture `8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18`
  as live evidence or this origin
- Treat populated-origin R1 evidence as this family's origin attestation

## 6. Honest boundary

Lawful-origin contract freeze ≠ grant ≠ R1 ≠ implementation ≠ live §4.4 authority
≠ kg row-level read ≠ members landed ≠ versioned forecast artifact produced ≠
`NO_VERSIONED` flipped ≠ `NO_REVIEWED` flipped ≠ catalog bindable ≠ completeness
verified ≠ backtest/attribution/metrics computed. This family is not populated-origin's
fourth slice; it does not append pointers to 30 A2 identity-set contracts.
`POPULATED_ORIGIN_R1_EVIDENCE_JSON_SHA256` is not this family's attestation.

## 7. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=c5d811b784425d03cbbf33cf6ee048557a88e7e8efcb9a2cde721e6463f3cfdc
~~~
