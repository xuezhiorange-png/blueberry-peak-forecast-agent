# V0.3-S3-B Quantile Semantics Remediation Contract Amendment

## Amendment identity and phase boundary

~~~text
AMENDMENT_ID=V0_3_S3_B_QUANTILE_SEMANTICS_REMEDIATION_CONTRACT_AMENDMENT
AMENDMENT_VERSION=v0-3-s3-b-quantile-semantics-remediation-contract-amendment-v1
TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_REMEDIATION_CONTRACT_AMENDMENT_R1
TASK_CLASS=CONTRACT_AMENDMENT_ONLY
AUTHORIZATION_SCOPE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_CONTRACT_AMENDMENT_ONLY
PARALLEL_LANE=S3-B
SLICE=V0.3-S3
USER_GATE=授权
INTERPRETED_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_CONTRACT_AMENDMENT_AUTHORING_ONLY
CONTRACT_AMENDMENT_AUTHORING_AUTHORIZED=true
CONTRACT_AMENDMENT_ONLY=true
BASE_MAIN_SHA=c74cd2c541fe48b78b5a84de87ef10c16eee976e
BASE_MAIN_TREE_SHA=a42f9bde5d365cc4512ceeadc50c99aa3cd5dc8b
PARENT_CONTRACT_PR=535
PARENT_CONTRACT_MERGE=46f1e2b9ffccf9998ab73ca92e450f049cab00d9
PARENT_CONTRACT_EVIDENCE_JSON_SHA256=1553f0def25480671416ecd0f5756cdc3c66378e95a4ce0cf7acc0081c57dbad
PARENT_GRANT_PR=536
PARENT_GRANT_MERGE=c74cd2c541fe48b78b5a84de87ef10c16eee976e
PARENT_GRANT_EVIDENCE_JSON_SHA256=78137b0a227853ad1449787efaee0ef3d2776e97a54f1faeec0dad0720fd3498
BLOCKED_IMPLEMENTATION_PR=537
BLOCKED_IMPLEMENTATION_HEAD=43dbe2a3aec80086cba0c3d96b33795c906619de
NO_STEP_IMPLIES_THE_NEXT=true
THIS_AMENDMENT_IS_NOT_A_GRANT=true
THIS_AMENDMENT_IS_NOT_IMPLEMENTATION=true
GRANT_AMENDMENT_AUTHORIZED=false
IMPLEMENTATION_AUTHORIZED=false
MIGRATION_IMPLEMENTATION_AUTHORIZED=false
PRODUCTION_CODE_MUTATION_AUTHORIZED=false
TEST_CODE_MUTATION_AUTHORIZED=false
MIGRATION_MUTATION_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
STOP_AFTER_CONTRACT_AMENDMENT_AUTHORING=true
NEXT_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_CONTRACT_AMENDMENT_REVIEW
~~~

This Amendment amends **only** the persistence and migration assumptions of the
merged S3-B Quantile Semantics Remediation Contract (#535). It does **not**
reopen the parent Contract body file
`docs/v0-3/s3/s3-quantile-semantics-remediation-contract.md`.

It does **not** implement code, migrations, tests, or PR #537 corrections.

## 1. Blocked implementation discovery (not a CI failure)

~~~text
PR_537_IMPLEMENTATION_REVIEW_STATUS=CHANGES_REQUIRED
PR_537_BLOCKER=FINAL_TARGET_PREDICTION_PERSISTENCE_SCHEMA_CONTRACT_MISMATCH
BLOCKED_IMPLEMENTATION_CI_CONCLUSION=success
IMPLEMENTATION_BLOCKED_BY_CONTRACT_NOT_CI=true
~~~

Draft implementation PR #537 (`43dbe2a`) passes CI but is blocked by schema /
contract semantics mismatch:

~~~text
FAKE_LEGACY_TASK9_AUTHORITY_DETECTED=true
LEGACY_MODE_OVERLOAD_DETECTED=true
FINAL_TARGET_PREDICTION_PERSISTENCE_BLOCKED=true
OBSERVED_FINAL_TARGET_PREDICTION_TASK9_RUN_ID=0
OBSERVED_FINAL_TARGET_PREDICTION_TASK9_RESULT_HASH=0000000000000000000000000000000000000000000000000000000000000000
OBSERVED_FINAL_TARGET_PREDICTION_MODE=residual_corrected
~~~

Final-target prediction must not bind fake Task9 authority or overload legacy
`residual_corrected` mode merely to satisfy non-null relational constraints.

## 2. Inherited architecture (not reopened)

~~~text
CANONICAL_OPTION=FINAL_TARGET_DIRECT_QUANTILE_MODEL
FINAL_TARGET_Y=model_harvested_marketable_quantity_kg
FINAL_TARGET_ACTUAL_LABEL=actual_harvest_quantity_kg
FINAL_TARGET_ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
QUANTILE_LEVELS=0.50,0.80,0.90
QUANTILE_CROSSING_POLICY=DETERMINISTIC_REARRANGEMENT_WITH_FINAL_OUTPUT_VERIFICATION
FALLBACK_QUANTILE_SEMANTICS_POLICY=FAIL_CLOSED_NO_VERIFIED_QUANTILE_OUTPUT
FINAL_TARGET_MANIFEST_PERSISTENCE_POLICY=TRAINING_RUN_MANIFEST_SNAPSHOT_JSON
FINAL_TARGET_PREDICTION_PERSISTENCE_POLICY=CANONICAL_JSON_SNAPSHOT_ONLY
~~~

## 3. Superseded parent Contract fields (Amendment authority only)

The parent Contract #535 remains historical and unchanged. This Amendment is
the newer authority **only** for:

| Field | Parent Contract | Amended |
| --- | --- | --- |
| `MIGRATION_REQUIRED` | `false` | `true` |
| `MIGRATION_DECISION_PROVEN` | `true` (no migration) | `true` (migration required) |
| `BACKEND_APP_MODELS_RESIDUAL_MODEL_CHANGE_REQUIRED` | `false` | `true` |
| `BACKEND_APP_RESIDUAL_MODEL_ENUMS_CHANGE_REQUIRED` | (absent) | `true` |
| `ALEMBIC_MIGRATION_CHANGE_REQUIRED` | (absent) | `true` |

~~~text
OLD_MIGRATION_REQUIRED=false
NEW_MIGRATION_REQUIRED=true
OLD_MIGRATION_DECISION_PROVEN=true
NEW_MIGRATION_DECISION_PROVEN=true
OLD_BACKEND_APP_MODELS_RESIDUAL_MODEL_CHANGE_REQUIRED=false
NEW_BACKEND_APP_MODELS_RESIDUAL_MODEL_CHANGE_REQUIRED=true
BACKEND_APP_RESIDUAL_MODEL_ENUMS_CHANGE_REQUIRED=true
ALEMBIC_MIGRATION_CHANGE_REQUIRED=true
~~~

## 4. Canonical migration architecture

Use the existing `residual_model_prediction_run` parent table. Do **not** create
a parallel fake legacy row or placeholder Task9 authority.

~~~text
PREDICTION_RUN_SHARED_PARENT_TABLE=true
PREDICTION_TARGET_KIND_COLUMN_REQUIRED=true
PREDICTION_TARGET_KIND_COLUMN=prediction_target_kind
PREDICTION_TARGET_KIND_VALUES=LEGACY_RESIDUAL_CORRECTION,FINAL_TARGET_QUANTILE
LEGACY_EXISTING_ROW_BACKFILL_TARGET_KIND=LEGACY_RESIDUAL_CORRECTION
~~~

Existing prediction rows MUST be migrated/backfilled as
`prediction_target_kind=LEGACY_RESIDUAL_CORRECTION`.

New final-target prediction runs MUST persist as
`prediction_target_kind=FINAL_TARGET_QUANTILE`.

## 5. Task9 authority nullability

Legacy receipt-residual lane requires Task9 authority. Final-target lane does not.

~~~text
TASK9_RUN_ID_NULLABLE=true
TASK9_RESULT_HASH_NULLABLE=true
LEGACY_RESIDUAL_CORRECTION_TASK9_RUN_ID=NOT_NULL
LEGACY_RESIDUAL_CORRECTION_TASK9_RESULT_HASH=NOT_NULL
FINAL_TARGET_TASK9_RUN_ID=NULL
FINAL_TARGET_TASK9_RESULT_HASH=NULL
FINAL_TARGET_TASK9_RUN_ID_SENTINEL_FORBIDDEN=0
FINAL_TARGET_TASK9_RESULT_HASH_SENTINEL_FORBIDDEN=0000000000000000000000000000000000000000000000000000000000000000
FAKE_TASK9_AUTHORITY_FOR_FINAL_TARGET=false
~~~

No final-target prediction may bind a nonexistent or irrelevant `harvest_state_run`
merely to satisfy a legacy foreign key.

Future ORM changes:

- `ResidualModelPredictionRun.task9_run_id` → `nullable=true`
- `ResidualModelPredictionRun.task9_result_hash` → `nullable=true`

## 6. Prediction mode

~~~text
FINAL_TARGET_PREDICTION_MODE=final_target_quantile
FINAL_TARGET_QUANTILE_USES_RESIDUAL_CORRECTED_MODE=false
~~~

Future enum must include:

~~~text
ResidualPredictionMode.FINAL_TARGET_QUANTILE=final_target_quantile
~~~

Completed final-target prediction:

~~~text
prediction_target_kind=FINAL_TARGET_QUANTILE
execution_status=completed
mode=final_target_quantile
~~~

Blocked/failed final-target execution may use `mode=blocked` when
`prediction_target_kind=FINAL_TARGET_QUANTILE`.

Legacy modes remain: `residual_corrected`, `structural_only`, `blocked` for
`LEGACY_RESIDUAL_CORRECTION` only.

## 7. Database lane-consistency constraint

Future migration MUST encode relational lane semantics (not Python-only):

**LEGACY lane** (`prediction_target_kind=LEGACY_RESIDUAL_CORRECTION`):

- `task9_run_id IS NOT NULL`
- `task9_result_hash IS NOT NULL`
- `mode IN (residual_corrected, structural_only, blocked)`

**FINAL-TARGET lane** (`prediction_target_kind=FINAL_TARGET_QUANTILE`):

- `task9_run_id IS NULL`
- `task9_result_hash IS NULL`
- `training_run_id IS NOT NULL`
- `expected_prediction_row_count = 0`
- completed: `execution_status=completed` AND `mode=final_target_quantile`
- blocked/failed: `execution_status IN (blocked, failed)` AND `mode=blocked`

~~~text
DB_LANE_CONSISTENCY_CONSTRAINT_REQUIRED=true
~~~

## 8. Task9 hash constraint

~~~text
LEGACY_TASK9_HASH_VALIDATION_PRESERVED=true
FINAL_TARGET_NULL_TASK9_HASH_ALLOWED=true
INVALID_NON_NULL_TASK9_HASH_ALLOWED=false
~~~

Non-null `task9_result_hash` must remain canonical lowercase SHA-256. NULL is
legal **only** for `FINAL_TARGET_QUANTILE`.

## 9. Final-target prediction row persistence (preserved)

~~~text
FINAL_TARGET_PREDICTION_PERSISTENCE_POLICY=CANONICAL_JSON_SNAPSHOT_ONLY
FINAL_TARGET_EXPECTED_PREDICTION_ROW_COUNT=0
FINAL_TARGET_LEGACY_PREDICTION_CHILD_ROWS=0
ROW_CONTENT_HASH_EXCLUDES_DB_RUN_IDS=true
MODEL_RUN_ID_NOT_IN_CONTENT_HASH=true
PREDICTION_RUN_ID_NOT_IN_CONTENT_HASH=true
REAL_MODEL_RUN_ID_REQUIRED_AFTER_PERSISTENCE=true
REAL_PREDICTION_RUN_ID_REQUIRED_AFTER_PERSISTENCE=true
~~~

`canonical_output.final_target_rows` holds logical rows; reload must
independently validate content hashes and run authority.

## 10. Training count semantics — fix legacy overload

~~~text
DISTINCT_GRAIN_COUNT_COLUMN_REQUIRED=true
FINAL_TARGET_GRAIN_COUNT_STORED_AS_FACTORY_COUNT=false
~~~

Future training-run schema adds `ResidualModelTrainingRun.distinct_grain_count`.

**LEGACY_RESIDUAL_CORRECTION:**

- `distinct_factory_count` = actual legacy factory count
- `distinct_grain_count = 0`

**FINAL_TARGET_QUANTILE:**

- `distinct_factory_count = 0`
- `distinct_grain_count` = count distinct `(farm_id, subfarm_id, variety_id)` within included TRAIN rows

Existing legacy training rows backfill: `distinct_grain_count=0`. Historical
`distinct_factory_count` values are not destroyed or reinterpreted.

## 11. Migration backward compatibility

~~~text
EXISTING_LEGACY_PREDICTION_ROWS_PRESERVED=true
EXISTING_LEGACY_TRAINING_ROWS_PRESERVED=true
EXISTING_TASK9_FOREIGN_KEYS_PRESERVED=true
EXISTING_RESIDUAL_CHILD_ROWS_PRESERVED=true
LEGACY_QUERY_BEHAVIOR_PRESERVED=true
~~~

Backfill existing prediction rows:
`prediction_target_kind=LEGACY_RESIDUAL_CORRECTION`.

Backfill existing training rows: `distinct_grain_count=0`.

No existing legacy row may be rewritten as `FINAL_TARGET_QUANTILE`.

## 12. Downgrade policy

~~~text
DESTRUCTIVE_FINAL_TARGET_DOWNGRADE_FORBIDDEN=true
~~~

Before downgrade removes `prediction_target_kind`, `final_target_quantile` mode,
`distinct_grain_count`, or Task9-null final-target semantics, it MUST detect
any `prediction_target_kind=FINAL_TARGET_QUANTILE` rows. If present:
`DOWNGRADE_BLOCKED=true`. Do not silently coerce final-target rows into
`residual_corrected` with `task9_run_id=0` or fake Task9 hashes.

## 13. Alembic authority (recorded at authoring; migration not in this PR)

At Contract Amendment authoring on base `c74cd2c`:

~~~text
ALEMBIC_HEAD_COUNT=1
ALEMBIC_HEADS=e8b2c4d6f1a3
~~~

Recorded via `uv run alembic -c backend/alembic.ini heads` from repository root.
No `revision`, `down_revision`, or migration filename is invented here.

Future Grant Amendment must freeze the exact new migration path/revision from
then-current main before migration implementation begins.

~~~text
NEW_MIGRATION_REQUIRED=true
MIGRATION_FILE_PATH=FROZEN_BY_FUTURE_GRANT_AMENDMENT_AFTER_ALEMBIC_HEADS_VERIFICATION
~~~

## 14. Updated future production change surface

Preserves parent Grant #536 implementation surface. Adds migration-required paths
for a **future** Grant Amendment (not this PR):

| Path | CHANGE_REQUIRED | Reason |
| --- | --- | --- |
| `backend/app/models/residual_model.py` | true | ORM nullability, `prediction_target_kind`, mode/lane checks, `distinct_grain_count` |
| `backend/app/residual_model/enums.py` | true | truthful `final_target_quantile` prediction mode |
| `backend/app/residual_model/schemas.py` | true | optional Task9 authority for final-target lane; explicit target-kind persistence |
| `backend/app/residual_model/persistence.py` | true | NULL Task9 authority and `final_target_quantile` mode (not legacy sentinels) |
| `backend/app/residual_model/service.py` | true | remove Task9 sentinel constants and `residual_corrected` from final-target finalization |
| `backend/app/residual_model/application.py` | true | E2E persisted final-target validates amended relational authority |
| `backend/app/residual_model/replay_training_authority.py` | true | replay payloads must not require fake Task9 for final-target lane |
| `backend/app/residual_model/config.py` | false | no additional migration semantics beyond existing target-kind discriminator |
| `backend/app/core_forecast/service.py` | false | authority-bound final-target curve binding remains sufficient |
| Alembic new migration | true | schema changes per this Amendment |

Parent Grant allowlist paths (`dataset.py`, `model.py`, `projection.py`,
`training_manifest.py`, etc.) remain the implementation surface after amended
Grant authorization; this Amendment does not shrink that surface.

## 15. PR #537 status (frozen)

~~~text
PR_537_OPEN=true
PR_537_DRAFT=true
PR_537_MERGED=false
PR_537_DO_NOT_MODIFY_IN_THIS_AMENDMENT=true
PR_537_DO_NOT_READY=true
PR_537_DO_NOT_MERGE=true
~~~

After this Amendment and a future Grant Amendment land, #537 may be corrected /
rebased under separately authorized amended implementation scope.

## 16. Non-retroactive authority

~~~text
OLD_IMPLEMENTATION_GATE_DOES_NOT_AUTHORIZE_NEW_MIGRATION_SCOPE=true
NEW_IMPLEMENTATION_GATE_REQUIRED_AFTER_GRANT_AMENDMENT=true
NEW_GRANT_AMENDMENT_REQUIRED=true
NO_RETROACTIVE_SCOPE_EXPANSION=true
~~~

The earlier user gate 「可以实施」 was issued before this migration/schema scope
existed. After Contract Amendment Review PASS → Ready/Merge → Grant Amendment
authorization → Grant Amendment Review PASS → Grant Amendment Ready/Merge, a
**new** user implementation gate 「可以实施」 is required.

## 17. Governance (unchanged)

~~~text
CURRENT_P50_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P80_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P90_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P50_SEMANTICS_VERIFIED=false
CURRENT_P80_SEMANTICS_VERIFIED=false
CURRENT_P90_SEMANTICS_VERIFIED=false
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
TEST_EVALUATION_AUTHORIZED=false
SOURCE_002_RAW_READ_AUTHORIZED=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_V0_3_S3_COMPLETE=false
V0_3_S4_AUTHORIZED=false
~~~
