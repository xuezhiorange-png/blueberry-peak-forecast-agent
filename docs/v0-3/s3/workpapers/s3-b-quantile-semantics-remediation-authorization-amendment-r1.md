# S3-B quantile semantics remediation implementation grant amendment R1

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_GRANT_AMENDMENT
ARTIFACT_VERSION=s3-b-quantile-semantics-remediation-authorization-amendment-r1-v1
TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_REMEDIATION_GRANT_AMENDMENT_R1
TASK_CLASS=IMPLEMENTATION_GRANT_AMENDMENT_AUTHORIZATION_ISSUANCE_ONLY
AUTHORIZATION_SCOPE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_GRANT_AMENDMENT_ONLY
PARALLEL_LANE=S3-B
SLICE=V0.3-S3
USER_GATE=授权
INTERPRETED_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_GRANT_AMENDMENT_AUTHORING_ONLY
GRANT_AMENDMENT_AUTHORING_AUTHORIZED=true
BASE_MAIN_SHA=e3ba3b4fdd1f4c625f342fd55b96826728a1afc9
BASE_MAIN_TREE_SHA=801c2ff83c29bdb7df95bec3b2e65bd20612ea1b
PARENT_CONTRACT_PR=535
PARENT_CONTRACT_MERGE=46f1e2b9ffccf9998ab73ca92e450f049cab00d9
PARENT_CONTRACT_EVIDENCE_JSON_SHA256=1553f0def25480671416ecd0f5756cdc3c66378e95a4ce0cf7acc0081c57dbad
PARENT_GRANT_PR=536
PARENT_GRANT_MERGE=c74cd2c541fe48b78b5a84de87ef10c16eee976e
PARENT_GRANT_EVIDENCE_JSON_SHA256=78137b0a227853ad1449787efaee0ef3d2776e97a54f1faeec0dad0720fd3498
PARENT_CONTRACT_AMENDMENT_PR=538
PARENT_CONTRACT_AMENDMENT_HEAD=eff8848baf5f3da37328b59fad9c4edaca418836
PARENT_CONTRACT_AMENDMENT_MERGE=e3ba3b4fdd1f4c625f342fd55b96826728a1afc9
PARENT_CONTRACT_AMENDMENT_EVIDENCE_JSON_SHA256=61ffb33d466aa8b3b4221793976481b8bac5448956b3a143c8cbde3bad7d2642
BLOCKED_IMPLEMENTATION_PR=537
BLOCKED_IMPLEMENTATION_HEAD=43dbe2a3aec80086cba0c3d96b33795c906619de
PR_537_BLOCKER=FINAL_TARGET_PREDICTION_PERSISTENCE_SCHEMA_CONTRACT_MISMATCH
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-b-quantile-semantics-remediation-authorization-amendment-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-b-quantile-semantics-remediation-authorization-amendment-r1.json
EVIDENCE_JSON_SHA256=d54b56b91fe1897b5dc92bd59b60f1684fa595e76ecc8e0a7ccbcfd9d68a7a04
GRANT_AMENDMENT_ONLY=true
THIS_PR_IS_NOT_IMPLEMENTATION_R1=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
STOP_AFTER_GRANT_AMENDMENT_AUTHORING=true
NEXT_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_GRANT_AMENDMENT_REVIEW
~~~

Contract Amendment #538 merged to main. This Grant Amendment extends Parent Grant
#536 with migration/schema persistence authority from #538. Parent Grant workpaper
and evidence JSON remain historical and unchanged. Draft implementation PR #537
remains open, draft, and blocked by schema/contract mismatch (CI success does
not override). This PR does not implement migrations, production code, training,
TEST, or coverage.

## 1. Superseded Parent Grant field

Parent Grant #536 remains binding except:

~~~text
OLD_MIGRATION_REQUIRED=false
NEW_MIGRATION_REQUIRED=true
~~~

## 2. Inherited Contract Amendment facts (#538)

~~~text
MIGRATION_REQUIRED=true
PREDICTION_TARGET_KIND_COLUMN_REQUIRED=true
PREDICTION_TARGET_KIND_VALUES=LEGACY_RESIDUAL_CORRECTION,FINAL_TARGET_QUANTILE
TASK9_RUN_ID_NULLABLE=true
TASK9_RESULT_HASH_NULLABLE=true
FINAL_TARGET_TASK9_RUN_ID=null
FINAL_TARGET_TASK9_RESULT_HASH=null
FAKE_TASK9_AUTHORITY_FOR_FINAL_TARGET=false
TASK9_RUN_ID_ZERO_SENTINEL_FORBIDDEN=true
TASK9_RESULT_HASH_ALL_ZERO_SENTINEL_FORBIDDEN=true
FINAL_TARGET_PREDICTION_MODE=final_target_quantile
FINAL_TARGET_QUANTILE_USES_RESIDUAL_CORRECTED_MODE=false
DISTINCT_GRAIN_COUNT_COLUMN_REQUIRED=true
DB_LANE_CONSISTENCY_CONSTRAINT_REQUIRED=true
FINAL_TARGET_PREDICTION_PERSISTENCE_POLICY=CANONICAL_JSON_SNAPSHOT_ONLY
ROW_CONTENT_HASH_EXCLUDES_DB_RUN_IDS=true
REAL_MODEL_RUN_ID_REQUIRED_AFTER_PERSISTENCE=true
REAL_PREDICTION_RUN_ID_REQUIRED_AFTER_PERSISTENCE=true
FINAL_TARGET_DISTINCT_FACTORY_COUNT=0
FINAL_TARGET_DISTINCT_GRAIN_COUNT=count_distinct_farm_subfarm_variety_in_train_rows
FINAL_TARGET_GRAIN_COUNT_STORED_AS_FACTORY_COUNT=false
LEGACY_EXISTING_ROW_BACKFILL_TARGET_KIND=LEGACY_RESIDUAL_CORRECTION
EXISTING_LEGACY_ROWS_PRESERVED=true
~~~

## 3. Alembic authority (recorded at authoring)

~~~text
ALEMBIC_HEAD_COUNT=1
ALEMBIC_HEADS=e8b2c4d6f1a3
AUTHORIZED_NEW_MIGRATION_COUNT=1
AUTHORIZED_NEW_MIGRATION_PATH=backend/alembic/versions/f3a9b2c8d1e4_s3_b_final_target_quantile_prediction_lane.py
AUTHORIZED_MIGRATION_DOWN_REVISION=e8b2c4d6f1a3
AUTHORIZED_MIGRATION_REVISION=f3a9b2c8d1e4
OTHER_MIGRATION_FILES_AUTHORIZED=false
DO_NOT_CREATE_MIGRATION_FILE_IN_THIS_GRANT=true
~~~

## 4. Effective future production change allowlist

Parent Grant #536 allowlist **plus** Contract Amendment additions:

~~~text
EFFECTIVE_FUTURE_PRODUCTION_CHANGE_ALLOWLIST=
backend/app/residual_model/dataset.py
backend/app/residual_model/model.py
backend/app/residual_model/service.py
backend/app/residual_model/projection.py
backend/app/residual_model/config.py
backend/app/residual_model/training_manifest.py
backend/app/residual_model/schemas.py
backend/app/residual_model/persistence.py
backend/app/residual_model/replay_training_authority.py
backend/app/residual_model/application.py
backend/app/core_forecast/service.py
backend/app/models/residual_model.py
backend/app/residual_model/enums.py
backend/alembic/versions/f3a9b2c8d1e4_s3_b_final_target_quantile_prediction_lane.py
~~~

Amendment necessity (does not revoke Parent Grant paths):

~~~text
backend/app/models/residual_model.py CHANGE_REQUIRED=true
backend/app/residual_model/enums.py CHANGE_REQUIRED=true
backend/app/residual_model/service.py CHANGE_REQUIRED=true
backend/app/residual_model/schemas.py CHANGE_REQUIRED=true
backend/app/residual_model/persistence.py CHANGE_REQUIRED=true
backend/app/residual_model/replay_training_authority.py CHANGE_REQUIRED=true
backend/app/residual_model/application.py CHANGE_REQUIRED=true
alembic_new_migration CHANGE_REQUIRED=true
backend/app/residual_model/config.py AMENDMENT_ADDITIONAL_CHANGE_REQUIRED=false
backend/app/core_forecast/service.py AMENDMENT_ADDITIONAL_CHANGE_REQUIRED=false
~~~

## 5. Forbidden future production change list

All production paths outside the effective allowlist remain forbidden, including:

~~~text
FORBIDDEN_FUTURE_PRODUCTION_CHANGE_LIST=
backend/app/api/rolling_backtest_replay_trained.py
backend/app/api/residual_model.py
backend/app/harvest_state/service.py
backend/app/maturity/model.py
backend/app/maturity/service.py
backend/app/maturity/calibration.py
backend/alembic/**
alembic/**
sql/**
~~~

Only `AUTHORIZED_NEW_MIGRATION_PATH` is exempt from `backend/alembic/**` prohibition.

## 6. DB lane consistency (future migration only)

Legacy lane: `LEGACY_RESIDUAL_CORRECTION`, non-null Task9, modes
`residual_corrected|structural_only|blocked`.

Final-target lane: `FINAL_TARGET_QUANTILE`, null Task9,
`mode=final_target_quantile` when completed. Forbidden:
`FINAL_TARGET_QUANTILE` + `residual_corrected`.

## 7. Model semantics (not reopened)

~~~text
CANONICAL_OPTION=FINAL_TARGET_DIRECT_QUANTILE_MODEL
FINAL_TARGET_Y=model_harvested_marketable_quantity_kg
FINAL_TARGET_ACTUAL_LABEL=actual_harvest_quantity_kg
QUANTILE_CROSSING_POLICY=DETERMINISTIC_REARRANGEMENT_WITH_FINAL_OUTPUT_VERIFICATION
FALLBACK_QUANTILE_SEMANTICS_POLICY=FAIL_CLOSED_NO_VERIFIED_QUANTILE_OUTPUT
IMPLEMENTATION_SUCCESS_IS_NOT_SEMANTICS_VERIFICATION=true
~~~

## 8. Gates and governance

~~~text
OLD_IMPLEMENTATION_GATE_DOES_NOT_AUTHORIZE_AMENDED_SCOPE=true
NEW_IMPLEMENTATION_GATE_REQUIRED_AFTER_GRANT_AMENDMENT_MERGE=true
IMPLEMENTATION_AUTHORIZED=false
MIGRATION_IMPLEMENTATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
TEST_EVALUATION_AUTHORIZED=false
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
CURRENT_P50_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P80_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P90_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_V0_3_S3_COMPLETE=false
V0_3_S4_AUTHORIZED=false
~~~

EVIDENCE_JSON_SHA256=d54b56b91fe1897b5dc92bd59b60f1684fa595e76ecc8e0a7ccbcfd9d68a7a04
