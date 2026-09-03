# V0.3-S3-B Quantile semantics remediation implementation authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_AUTHORIZATION
ARTIFACT_VERSION=s3-b-quantile-semantics-remediation-authorization-v1
TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_GRANT_R1
TASK_CLASS=IMPLEMENTATION_AUTHORIZATION_ISSUANCE_ONLY
AUTHORIZATION_SCOPE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_GRANT_ONLY
PARALLEL_LANE=S3-B
SLICE=V0.3-S3
ENGLISH_ID=QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION
USER_GATE=授权
INTERPRETED_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_GRANT_AUTHORING_ONLY
GRANT_AUTHORING_AUTHORIZED=true
BASE_REF=origin/main
BASE_MAIN_SHA=46f1e2b9ffccf9998ab73ca92e450f049cab00d9
BASE_MAIN_TREE_SHA=088b4aae37cba7ac8d365b32f5f770666517d86b
PARENT_CONTRACT_PR=535
PARENT_CONTRACT_HEAD=36a06c2408c0645d61532e3651decadb99070a75
PARENT_CONTRACT_MERGE=46f1e2b9ffccf9998ab73ca92e450f049cab00d9
PARENT_CONTRACT_EVIDENCE_JSON_SHA256=1553f0def25480671416ecd0f5756cdc3c66378e95a4ce0cf7acc0081c57dbad
PARENT_CONTRACT_DOC_BLOB=e15679aab10b1112c88779faec0cd5ac30773771
PARENT_CONTRACT_WORKPAPER_BLOB=ddbf38af7c8f353f14f9169e2d65fb7b1c8a28c0
PARENT_CONTRACT_EVIDENCE_BLOB=b145ebb1c6972257310210d47387b2e8aa7f74a6
PARENT_CONTRACT_PATH=docs/v0-3/s3/s3-quantile-semantics-remediation-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-b-quantile-semantics-remediation-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-b-quantile-semantics-remediation-authorization.json
GRANT_ONLY=true
THIS_PR_IS_NOT_IMPLEMENTATION_R1=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
STOP_AFTER_GRANT_AUTHORING=true
NEXT_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_GRANT_REVIEW
~~~

The user authorized issuance of the S3-B **quantile semantics remediation
implementation** grant after parent remediation Contract #535 merged to main.
This document records what a **later** implementation R1 may change when the user
again says exactly or equivalently 「可以实施」. This PR does not implement the
model, does not train, does not read TEST, does not execute S3-B coverage, does
not flip `CURRENT_P*_SEMANTICS_STATUS`, and does not mutate production Python.

Parent remediation Contract decisions are **not reopened**:

~~~text
CANONICAL_OPTION=FINAL_TARGET_DIRECT_QUANTILE_MODEL
FINAL_TARGET_Y=model_harvested_marketable_quantity_kg
FINAL_TARGET_ACTUAL_LABEL=actual_harvest_quantity_kg
FINAL_TARGET_ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
FINAL_TARGET_MANIFEST_PERSISTENCE_POLICY=TRAINING_RUN_MANIFEST_SNAPSHOT_JSON
LEGACY_RESIDUAL_MANIFEST_ROW_POLICY=LEGACY_RECEIPT_RESIDUAL_LANE_ONLY
FINAL_TARGET_ROWS_WRITE_LEGACY_RESIDUAL_MODEL_MANIFEST_ROW=false
MIGRATION_REQUIRED=false
QUANTILE_CROSSING_POLICY=DETERMINISTIC_REARRANGEMENT_WITH_FINAL_OUTPUT_VERIFICATION
FALLBACK_QUANTILE_SEMANTICS_POLICY=FAIL_CLOSED_NO_VERIFIED_QUANTILE_OUTPUT
~~~

## 1. Implementation scope granted (not executed)

~~~text
S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_SCOPE_GRANTED=true
MODEL_CHANGE_SCOPE_GRANTED=true
FINAL_TARGET_QUANTILE_MODEL_CHANGE_SCOPE_GRANTED=true
TRAINING_PIPELINE_CHANGE_SCOPE_GRANTED=true
FINAL_TARGET_MANIFEST_CODE_PATH_CHANGE_SCOPE_GRANTED=true
CORE_FORECAST_PUBLICATION_WIRING_SCOPE_GRANTED=true
IMPLEMENTATION_R1_USER_GATE_SATISFIED=false
IMPLEMENTATION_EXECUTION_AUTHORIZED_NOW=false
TRAINING_EXECUTION_AUTHORIZED_NOW=false
~~~

Implementation may begin only after:

1. this Grant independently reviews PASS;
2. this Grant merges to main;
3. user later says 「可以实施」.

## 2. Authorized future production change allowlist

Later R1 may mutate **only** these production files unless Contract/Grant
amendment expands scope:

~~~text
AUTHORIZED_FUTURE_PRODUCTION_CHANGE_ALLOWLIST=
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
~~~

## 3. Explicitly forbidden production mutation

~~~text
FORBIDDEN_FUTURE_PRODUCTION_CHANGE_LIST=
backend/app/models/residual_model.py
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

`MIGRATION_REQUIRED=false` remains binding. If implementation discovers a
forbidden path must change: `STOP`, `IMPLEMENTATION_SCOPE_INSUFFICIENT=true`,
`CONTRACT_OR_GRANT_AMENDMENT_REQUIRED=true`.

## 4. Model / artifact identity (resolved at R1 evidence)

~~~text
PREDICTION_TARGET_KIND=FINAL_TARGET_QUANTILE
NEW_MODEL_SEMANTIC_VERSION_REQUIRED=true
IN_PLACE_INCUMBENT_ARTIFACT_OVERWRITE_FORBIDDEN=true
INCUMBENT_MODEL_HISTORY_PRESERVED=true
LEGACY_RESIDUAL_TARGET_ARTIFACT_ACCEPTED_AS_FINAL_TARGET=false
~~~

Exact `MODEL_FAMILY`, `MODEL_VERSION`, and `ARTIFACT_SCHEMA_VERSION` tokens must
be recorded in later R1 evidence. They must be new and unambiguous; do not
silently reuse incumbent residual-target identity.

## 5. Final-target manifest rules

For `prediction_target_kind=FINAL_TARGET_QUANTILE`:

~~~text
FINAL_TARGET_MANIFEST_SOURCE=ResidualModelTrainingRun.manifest_snapshot
FINAL_TARGET_MANIFEST_ROW_COUNT_FIELD=0
WRITE_RESIDUAL_MODEL_MANIFEST_ROW=false
LOGICAL_MANIFEST_ROWS_REQUIRED=true
LEGACY_CHILD_ROWS_REQUIRED=false
FAKE_DESTINATION_FACTORY_FORBIDDEN=true
FAKE_RECEIPT_QUANTITY_FORBIDDEN=true
FAKE_RESIDUAL_LABEL_FORBIDDEN=true
PLACEHOLDER_LEGACY_RECEIPT_FIELDS_FORBIDDEN=true
~~~

## 6. Data authority and fences

~~~text
TRAIN_AND_VALIDATION_ONLY=true
FINAL_TARGET_ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
TEST_REMAINS_SEALED=true
TEST_EVALUATION_AUTHORIZED=false
SOURCE_002_RAW_READ_AUTHORIZED=false
UNGOVERNED_SOURCE_002_ROW_LEVEL_READ_AUTHORIZED=false
FEATURES_AVAILABLE_AT_FORECAST_CUTOFF=true
NO_POST_CUTOFF_FEATURE_LEAKAGE=true
LABEL_OBSERVATION_AUTHORITY_VALID=true
FORECAST_TARGET_GRAIN_MATCH=true
~~~

## 7. Quantile semantics and crossing (unchanged from Contract)

Direct training on same final Y at q=0.50 / 0.80 / 0.90. Forbidden:
`RESIDUAL_LABEL_AS_FINAL_TARGET`, `STRUCTURAL_P50_PLUS_RESIDUAL_QUANTILE_AS_FINAL_SEMANTICS`,
`SYMMETRIC_MARGIN_AS_FINAL_P80_P90`. Require `P50 <= P80 <= P90` with
`DETERMINISTIC_REARRANGEMENT_WITH_FINAL_OUTPUT_VERIFICATION`;
`MONOTONIC_PROJECTION_CONFERS_QUANTILE_SEMANTICS=false`; raw and final crossing
counts auditable.

## 8. Fallback and post-implementation status

~~~text
FALLBACK_QUANTILE_SEMANTICS_POLICY=FAIL_CLOSED_NO_VERIFIED_QUANTILE_OUTPUT
IMPLEMENTATION_SUCCESS_IS_NOT_SEMANTICS_VERIFICATION=true
CURRENT_P50_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P80_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P90_SEMANTICS_STATUS=VERIFICATION_FAILED
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
~~~

## 9. Companion state (preserved)

~~~text
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_A2_COMPLETENESS_PASS_AUTHORIZED=false
CURRENT_V0_3_S3_COMPLETE=false
V0_3_S4_AUTHORIZED=false
THIS_GRANT_DOES_NOT_COMPLETE_S3=true
~~~

## 10. Grant review readiness

~~~text
GRANT_REVIEW_READY=true
GRANT_MERGE_DOES_NOT_IMPLEMENT_MODEL=true
GRANT_MERGE_DOES_NOT_FLIP_SEMANTICS_STATUS=true
GRANT_MERGE_DOES_NOT_AUTHORIZE_COVERAGE=true
GRANT_MERGE_DOES_NOT_TOUCH_PRODUCTION_PYTHON=true
~~~

EVIDENCE_JSON_SHA256=78137b0a227853ad1449787efaee0ef3d2776e97a54f1faeec0dad0720fd3498
