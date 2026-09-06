# V0.3-S3 Farm-total Baseline Live Execution Authorization (R1)

> Scope: docs-only live-execution contract freeze + authorization issuance — no Python, no execution, no scoring
> Task: `V0_3_S3_FARM_TOTAL_BASELINE_LIVE_EXECUTION_CONTRACT_AND_AUTHORIZATION_R1`
> Task class: `DOCS_ONLY_LIVE_EXECUTION_CONTRACT_AND_AUTHORIZATION`
> Parent evaluation package: PR #566 merge `80b05d5c033f19d0ded3dc7c983a08f00f50d662`

## Machine-readable header

```text
ARTIFACT_ID=V0_3_S3_FARM_TOTAL_BASELINE_LIVE_EXECUTION_AUTHORIZATION
ARTIFACT_VERSION=R1

TASK_ID=V0_3_S3_FARM_TOTAL_BASELINE_LIVE_EXECUTION_CONTRACT_AND_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_LIVE_EXECUTION_CONTRACT_AND_AUTHORIZATION

BASE_MAIN_SHA=80b05d5c033f19d0ded3dc7c983a08f00f50d662

PARENT_EVALUATION_PACKAGE_PR=566
PARENT_EVALUATION_PACKAGE_MERGE_SHA=80b05d5c033f19d0ded3dc7c983a08f00f50d662

USER_GATE=可以

V0_3_S3_FARM_TOTAL_BASELINE_LIVE_EXECUTION_CONTRACT_AUTHORIZED=true
V0_3_S3_FARM_TOTAL_BASELINE_LIVE_EXECUTION_AUTHORIZED=true

FUTURE_LIVE_RUNNER_IMPLEMENTATION_AUTHORIZED=true

OFFICIAL_TRAIN_EXECUTION_AUTHORIZED=true
OFFICIAL_VALIDATION_TARGET_PROJECTION_AUTHORIZED=true

LIVE_EXECUTION_PERFORMED=false
LIVE_TRAIN_EXECUTION_PERFORMED=false
LIVE_VALIDATION_EXECUTION_PERFORMED=false
VALIDATION_BASELINE_MATERIALIZED=false
VALIDATION_BASELINE_SCORED=false

EXECUTION_REQUIRES_SEPARATE_USER_GATE_可以执行=true

S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false

TEST_EVALUATION_ACCESS=false
TEST_REMAINS_SEALED=true

MODEL_CHANGE=false
PARAMETER_CHANGE=false
MIGRATION_CHANGE=false
SCHEMA_CHANGE=false
V0_3_S4_AUTHORIZED=false

READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The user gate `可以` authorizes issuance of this **live-execution contract and grant**
only. Actual official data execution requires a separate explicit user gate
`可以执行`.

```text
LIVE_EXECUTION_AUTHORIZED=true
≠
LIVE_EXECUTION_PERFORMED=true

LIVE_EXECUTION_AUTHORIZED=true
≠
VALIDATION_SCORING_AUTHORIZED=true

LIVE_EXECUTION_AUTHORIZED=true
≠
S3_METRIC_EXECUTION_AUTHORIZED=true

LIVE_EXECUTION_AUTHORIZED=true
≠
TEST_EVALUATION_ACCESS=true
```

## 1. Upstream authority (reference only)

| Role | Path |
| --- | --- |
| Parent evaluation package module | `backend/app/forecast_quality/farm_total_baseline_evaluation_package.py` |
| Parent evaluation package authorization | `docs/v0-3/s3/workpapers/s3-farm-total-baseline-evaluation-package-implementation-authorization.md` |
| Parent estimator module | `backend/app/forecast_quality/farm_total_baseline_estimator.py` |
| Farm-total data plane | `backend/app/forecast_quality/farm_total_data_plane.py` |
| Owner decision binding | `docs/v0-3/s3/s3-farm-total-baseline-estimator-owner-decision-binding.md` |

```text
PARENT_EVALUATION_PACKAGE_PR=566
PARENT_EVALUATION_PACKAGE_MERGE_SHA=80b05d5c033f19d0ded3dc7c983a08f00f50d662
PARENT_AUTHORIZATION_PR=565
PARENT_ESTIMATOR_PR=564
OWNER_DECISION_SHA256=39722ff8e8a520813975cd7270b6453db388633bffee9c90fb12140440431463
```

This authorization does not modify upstream implementation or binding artifacts.

## 2. Authorization scope

```text
AUTHORIZATION_SCOPE=V0_3_S3_FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_LIVE_EXECUTION_ONLY
```

This authorization is local to the Farm-total deterministic baseline evaluation
package live execution path.

It MUST NOT authorize:

- S3-C incumbent PIT backtest execution
- S3 metric execution
- VALIDATION scoring
- baseline-vs-incumbent comparison
- TEST evaluation
- S4
- model changes
- parameter changes

## 3. What this PR grants

This PR grants contract freeze and future live-execution authorization only.

```text
V0_3_S3_FARM_TOTAL_BASELINE_LIVE_EXECUTION_CONTRACT_AUTHORIZED=true
V0_3_S3_FARM_TOTAL_BASELINE_LIVE_EXECUTION_AUTHORIZED=true
FUTURE_LIVE_RUNNER_IMPLEMENTATION_AUTHORIZED=true

OFFICIAL_TRAIN_BYTE_READ_AUTHORIZED=true
OFFICIAL_VALIDATION_BYTE_READ_AUTHORIZED=true
LOAD_AUTHORITY_BUNDLE_FROM_PATHS_AUTHORIZED=true
MATERIALIZE_FARM_TOTAL_BASELINE_DATA_PLANE_ON_OFFICIAL_DATA_AUTHORIZED=true
REAL_TRAIN_GROUP_MEDIAN_COMPUTATION_AUTHORIZED=true
REAL_BASELINE_PREDICTION_MATERIALIZATION_IN_MEMORY_AUTHORIZED=true
LIVE_EVALUATION_PACKAGE_CONSTRUCTION_AUTHORIZED=true
LIVE_REPLAY_EXECUTION_AUTHORIZED=true
LIVE_EXECUTION_EVIDENCE_AUTHORIZED=true
```

Preserved false gates:

```text
LIVE_BASELINE_EXECUTION_PERFORMED=false
LIVE_TRAIN_EXECUTION_PERFORMED=false
LIVE_VALIDATION_EXECUTION_PERFORMED=false
VALIDATION_BASELINE_MATERIALIZED=false
VALIDATION_BASELINE_SCORED=false
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false
TEST_EVALUATION_ACCESS=false
MODEL_CHANGE=false
PARAMETER_CHANGE=false
V0_3_S4_AUTHORIZED=false
```

## 4. Future live execution PR paths

After separate user gate `可以执行`, authorize one future PR to create **exactly**:

| Kind | Path |
| --- | --- |
| Live runner | `scripts/run_v03_farm_total_baseline_evaluation_package.py` |
| Synthetic runner tests | `backend/tests/forecast_quality/test_farm_total_baseline_live_execution_runner.py` |
| Live execution workpaper | `docs/v0-3/s3/workpapers/s3-farm-total-baseline-live-execution-r1.md` |
| Machine-readable execution evidence | `docs/v0-3/s3/evidence/s3-farm-total-baseline-live-execution-r1.json` |

```text
FUTURE_CHANGED_FILE_COUNT=4
FUTURE_EXISTING_FILE_MUTATION_AUTHORIZED=false
```

The future task should combine runner implementation, runner tests, live execution,
replay, and evidence in the **same PR**. Do not split unless a genuine execution
blocker is found.

## 5. Governed SOURCE-002 live input

The future runner MUST reuse:

```text
backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_obtain.obtain_accepted_s2_train_val_content_bytes_from_bound_live_session
```

or the exact existing governed production seam behind it.

Do not write a new raw SQL reader. Do not create a new DB engine. Do not invent a
connection string. Do not query S2 partition tables independently.

Required successful obtain state:

```text
obtained=true
reason_code=OBTAINED
train_content_bytes present
validation_content_bytes present
test_remains_sealed=true
```

The future runner must fail closed otherwise.

## 6. TEST custody clarification

The existing governed SOURCE-002 live obtain seam performs custody verification of
the sealed TEST placeholder internally. It may verify TEST row count, sealed TEST
byte count, and sealed TEST content hash solely to prove TEST remains sealed.

It MUST NOT:

- return TEST content bytes
- construct TEST target keys
- parse TEST labels for evaluation
- build a TEST Farm-total dataset
- construct a TEST baseline package
- score TEST
- publish TEST row contents

```text
TEST_EVALUATION_ACCESS=false
TEST_LABEL_ACCESS=false
TEST_TARGET_CONSTRUCTION=false
TEST_PACKAGE_CONSTRUCTION=false
TEST_SCORING=false
TEST_PAYLOAD_RETURNED=false
SEALED_TEST_CUSTODY_VERIFICATION_VIA_EXISTING_READER_AUTHORIZED=true
TEST_REMAINS_SEALED=true
```

This custody check is not TEST evaluation authorization.

## 7. Authority bundle

Future runner may use:

```text
load_authority_bundle_from_paths(…)
```

with an explicitly supplied `--authority-dir` containing:

- `farm_total_group_mapping_package.json`
- `farm_total_area_authority_package.json`

The live task MUST use existing, already-reviewed authority packages.

```text
AUTHORITY_PACKAGE_REGENERATION_AUTHORIZED=false
```

Do NOT run `scripts/generate_v03_farm_total_authority_packages.py` merely because
expected files are missing.

If reviewed package files are unavailable:

```text
STOP_AND_REPORT_LIVE_AUTHORITY_PACKAGE_FILES_UNAVAILABLE
```

Do not substitute synthetic packages. Do not regenerate from guessed paths.

## 8. Official Farm-total data plane

Future runner must call:

```text
materialize_farm_total_baseline_data_plane(
    train_content_bytes=…,
    validation_content_bytes=…,
    authority_bundle=…,
    verify_official_hashes=True,
)
```

Required success conditions:

```text
blocker == FarmTotalDatasetBlocker.NONE
result is not None
validation_used_as_training_input == false
area_double_count_count == 0
source_farm_double_map_count == 0
source_actual_double_count == 0
```

The data-plane layer remains authoritative for official hash validation, Farm-total
projection, mapping binding, area authority binding, and TRAIN/VALIDATION separation.
Do not duplicate those validations in the live runner.

## 9. Live baseline package execution

After successful Farm-total data-plane result, future runner must call exactly:

```text
build_farm_total_baseline_evaluation_package(
    train_dataset=result.train_dataset,
    validation_dataset=result.validation_dataset,
)
```

Do not reimplement target construction, TRAIN median, support policy, projection, hash
calculation, or diagnostics. The existing production package is authoritative.

## 10. Authorized real computation

Future execution is authorized to compute in memory:

- real TRAIN group support counts
- real TRAIN group medians
- real VALIDATION target identities
- real baseline point predictions
- real per-target READY / INSUFFICIENT_TRAIN_SUPPORT / UNSEEN_GROUP outcomes
- real deterministic hash identities

```text
REAL_BASELINE_PREDICTIONS_COMPUTABLE_IN_MEMORY=true
REAL_BASELINE_POINT_VALUES_REPOSITORY_PERSISTENCE_AUTHORIZED=false
VALIDATION_ACTUAL_VALUES_REPOSITORY_PERSISTENCE_AUTHORIZED=false
RAW_TRAIN_ROWS_REPOSITORY_PERSISTENCE_AUTHORIZED=false
RAW_VALIDATION_ROWS_REPOSITORY_PERSISTENCE_AUTHORIZED=false
```

## 11. Execution evidence output policy

Future evidence artifacts may persist identities, counts, statuses, and hashes.

They MUST NOT persist:

- full TRAIN rows
- full VALIDATION rows
- VALIDATION actual quantities per target
- baseline prediction values per target
- raw SOURCE-002 bytes
- TEST bytes

Required evidence fields include:

```text
EXECUTION_MAIN_SHA
RUNNER_COMMIT_SHA
SOURCE_002_DATASET_ID
SOURCE_002_DATASET_VERSION
SOURCE_002_MATERIALIZED_DATASET_IDENTITY_SHA256
OFFICIAL_TRAIN_CONTENT_SHA256
OFFICIAL_VALIDATION_CONTENT_SHA256
TRAIN_SOURCE_ROW_COUNT
VALIDATION_SOURCE_ROW_COUNT
TEST_REMAINS_SEALED
FARM_GROUP_MAPPING_SET_SHA256
FARM_AREA_AUTHORITY_SET_SHA256
TRAIN_FARM_TOTAL_ROW_COUNT
VALIDATION_FARM_TOTAL_ROW_COUNT
TRAIN_FARM_GROUP_COUNT
VALIDATION_FARM_GROUP_COUNT
TRAIN_FARM_TOTAL_DATASET_SHA256
VALIDATION_FARM_TOTAL_DATASET_SHA256
AREA_DOUBLE_COUNT_COUNT
SOURCE_FARM_DOUBLE_MAP_COUNT
SOURCE_ACTUAL_DOUBLE_COUNT
VALIDATION_USED_AS_TRAINING_INPUT
PACKAGE_SCHEMA_VERSION
TARGET_COUNT
EMITTED_POINT_COUNT
BLOCKED_TARGET_COUNT
READY_TARGET_COUNT
INSUFFICIENT_TRAIN_SUPPORT_TARGET_COUNT
UNSEEN_GROUP_TARGET_COUNT
ESTIMATOR_STATE_SHA256
TARGET_IDENTITY_SET_SHA256
BASELINE_POINT_SET_SHA256
TARGET_OUTCOME_SET_SHA256
PREDICTION_IDENTITY_SHA256
PACKAGE_SHA256
```

Do not include real kg values in repository execution evidence.

## 12. Six hash layers

The future live run must record the existing six package identities emitted by
`FarmTotalBaselineEvaluationPackage`:

```text
estimator_state_sha256
target_identity_set_sha256
baseline_point_set_sha256
target_outcome_set_sha256
prediction_identity_sha256
package_sha256
```

No hash algorithm change. No new canonicalization. No independent ad-hoc serializer.

## 13. Live replay

The future controlled execution MUST run the live runner twice against the same main /
runner commit, accepted SOURCE-002 dataset identity, and reviewed authority package
files.

Require equality across run 1 and run 2 for:

```text
TRAIN_FARM_TOTAL_DATASET_SHA256
VALIDATION_FARM_TOTAL_DATASET_SHA256
ESTIMATOR_STATE_SHA256
TARGET_IDENTITY_SET_SHA256
BASELINE_POINT_SET_SHA256
TARGET_OUTCOME_SET_SHA256
PREDICTION_IDENTITY_SHA256
PACKAGE_SHA256
TARGET_COUNT
EMITTED_POINT_COUNT
BLOCKED_TARGET_COUNT
READY_TARGET_COUNT
INSUFFICIENT_TRAIN_SUPPORT_TARGET_COUNT
UNSEEN_GROUP_TARGET_COUNT
```

```text
LIVE_REPLAY_REQUIRED=true
LIVE_REPLAY_COUNT=2
LIVE_REPLAY_IDENTITY_MATCH_REQUIRED=true
```

If any required value differs:

```text
EXECUTION_STATUS=BLOCKED
REPLAY_STATUS=FAIL
```

Do not publish a PASS execution artifact.

## 14. Future runner output

The future runner should emit one machine-readable JSON object to stdout.

No business-value tables. No full target list. No actual rows. No full baseline
points. The JSON must contain only authorized execution evidence fields plus
`execution_status`, `blocker`, and `reason_code` when execution fails closed.

The runner should exit non-zero on fail-closed execution.

## 15. Future runner testing

The future test file must use synthetic/in-memory data only.

Minimum test themes (20):

1. successful runner orchestration on synthetic authority/data
2. SOURCE-002 obtain failure fails closed
3. missing authority package path fails closed
4. invalid authority bundle fails closed
5. Farm-total data-plane blocker fails closed
6. `validation_used_as_training_input=true` is rejected
7. nonzero `area_double_count_count` rejected
8. nonzero `source_farm_double_map_count` rejected
9. nonzero `source_actual_double_count` rejected
10. package builder called only after data-plane success
11. runner output includes all six hash fields
12. runner output excludes target-level actuals
13. runner output excludes target-level baseline values
14. runner output excludes TEST payload
15. deterministic stdout payload under same synthetic inputs
16. execution evidence contains package diagnostics counts
17. no scoring fields
18. no metric result fields
19. no P80/P90 baseline values
20. fail-closed exit behavior is deterministic

No live DB connection in pytest.

## 16. Validation scoring hard boundary

```text
VALIDATION_SCORING_AUTHORIZED=false
VALIDATION_BASELINE_SCORED=false
S3_METRIC_EXECUTION_AUTHORIZED=false
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
```

The future live runner MUST NOT calculate MAE, WAPE, SMAPE, MAPE, bias, coverage,
baseline-vs-incumbent difference, improvement percentage, or pass/fail superiority.

The live execution package is prediction materialization only.

## 17. Quantile boundary

```text
BASELINE_OUTPUT_DISTRIBUTION_AUTHORIZED=false
BASELINE_P80_STATUS=NOT_COMPUTABLE
BASELINE_P90_STATUS=NOT_COMPUTABLE
BASELINE_P80_P90_REASON=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
```

No P80. No P90. No baseline uncertainty distribution.

## 18. Model / S4 boundary

```text
MODEL_CHANGE=false
PARAMETER_CHANGE=false
V0_3_S4_AUTHORIZED=false
```

The future live runner must not import or mutate incumbent model behavior.

## 19. Persistence boundary

Runtime `FarmTotalBaselineEvaluationPackage` remains:

```text
PERSISTENCE=IN_MEMORY_ONLY
```

The only repository persistence authorized by the future task is summarized workpaper
and evidence JSON. No DB table, ORM, migration, JSON dump of full package points, or
object storage.

## 20. Future execution workpaper state

After successful future execution, required state:

```text
LIVE_BASELINE_EXECUTION_PERFORMED=true
LIVE_TRAIN_EXECUTION_PERFORMED=true
LIVE_VALIDATION_TARGET_PROJECTION_PERFORMED=true
VALIDATION_BASELINE_MATERIALIZED=true
LIVE_REPLAY_STATUS=PASS
VALIDATION_BASELINE_SCORED=false
S3_METRIC_EXECUTION=false
TEST_EVALUATION_ACCESS=false
MODEL_CHANGE=false
PARAMETER_CHANGE=false
V0_3_S4_AUTHORIZED=false
```

## 21. This PR boundary

```text
THIS_PR_DOCS_ONLY=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
```

This docs-only authorization PR changes exactly two new artifacts under
`docs/v0-3/s3/workpapers/` and `docs/v0-3/s3/evidence/`.

Evidence:
`docs/v0-3/s3/evidence/s3-farm-total-baseline-live-execution-authorization.json`
