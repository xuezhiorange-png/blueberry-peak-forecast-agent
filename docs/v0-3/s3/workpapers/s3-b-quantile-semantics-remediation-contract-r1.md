# S3-B quantile semantics remediation contract R1 workpaper

## Task envelope

~~~text
TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_REMEDIATION_CONTRACT_R1
CORRECTION_TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_REMEDIATION_CONTRACT_R1_CORRECTION
CORRECTION_PR=535
CORRECTION_SCOPE=DOCS_ONLY
TASK_CLASS=CONTRACT_DEFINITION_ONLY
USER_GATE=授权
INTERPRETED_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_CONTRACT_AUTHORING_ONLY
CONTRACT_AUTHORING_AUTHORIZED=true
GRANT_AUTHORIZED=false
IMPLEMENTATION_AUTHORIZED=false
BASE_MAIN_SHA=323c5e7b886b594e6f1cb76dd7d621d03f00a461
BASE_MAIN_TREE_SHA=9ccface3c206687fb2ba8a838a058c34fdeea04d
PARENT_CLOSEOUT_PR=534
PARENT_CLOSEOUT_MERGE=323c5e7b886b594e6f1cb76dd7d621d03f00a461
PARENT_OBSERVATION_TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_REMEDIATION_OBSERVATION_R0
PARENT_OBSERVATION_REVIEW_STATUS=PASS
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_R1_IMPLEMENTATION=true
PRODUCTION_CODE_MUTATION_AUTHORIZED=false
TEST_CODE_MUTATION_AUTHORIZED=false
MIGRATION_MUTATION_AUTHORIZED=false
STOP_AFTER_CONTRACT_AUTHORING=true
NEXT_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_CONTRACT_REVIEW
~~~

## Purpose

Freeze remediation architecture to replace incumbent unverified P50/P80/P90
semantics with direct final-target quantile modeling. Contract authoring and
correction #535 are docs-only.

## Final target and actual label authority (corrected)

~~~text
FINAL_TARGET_Y=model_harvested_marketable_quantity_kg
FINAL_TARGET_ACTUAL_LABEL=actual_harvest_quantity_kg
FINAL_TARGET_ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
FINAL_TARGET_ACTUALS_AUTHORITY_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
FINAL_TARGET_ACTUALS_AUTHORITY_SECTION=§2 / §2.1 actuals authority
ACTUAL_LABEL_AUTHORITY_SEPARATED=true
~~~

`actual_harvest_quantity_kg` is the **label field** for pairing semantics.
`V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION` is the **dataset actuals
authority** for lawful TRAIN/VALIDATION materialization.

## Manifest persistence decision (corrected)

Repository inspection at base `323c5e7` of
`save_residual_training_run`, `load_residual_training_run_by_id`,
`ResidualModelTrainingRun.manifest_snapshot`, and `ResidualModelManifestRow`:

- Incumbent runs duplicate snapshot JSON into factory-receipt child rows.
- Child rows are **required** today for load/replay (`manifest_row_count` match).
- Child-table schema cannot store farm-harvest final-target rows without fake
  factory/receipt/residual placeholders.

Canonical policy frozen:

~~~text
FINAL_TARGET_MANIFEST_PERSISTENCE_POLICY=TRAINING_RUN_MANIFEST_SNAPSHOT_JSON
LEGACY_RESIDUAL_MANIFEST_ROW_POLICY=LEGACY_RECEIPT_RESIDUAL_LANE_ONLY
FINAL_TARGET_ROWS_WRITE_LEGACY_RESIDUAL_MODEL_MANIFEST_ROW=false
MIGRATION_REQUIRED=false
MIGRATION_DECISION_PROVEN=true
NO_PLACEHOLDER_LEGACY_FIELDS=true
~~~

Future final-target runs: authoritative rows in `manifest_snapshot` JSON only,
`manifest_row_count=0`, no child inserts, load/replay from snapshot when
`prediction_target_kind=FINAL_TARGET_QUANTILE`.

## Reclassified persistence-related surfaces

| Path | CHANGE_REQUIRED | Reason |
| --- | --- | --- |
| `persistence.py` | true | snapshot-only save/load for final-target lane; `manifest_row_count=0` path |
| `models/residual_model.py` | false | `manifest_snapshot` JSON exists; child table stays legacy-only |
| `replay_training_authority.py` | true | label/dataset identity uses final Y, not receipt kg |
| `application.py` | true | replay gate from snapshot rows without child-row requirement |
| `schemas.py` | true | final-target snapshot row schema and `prediction_target_kind` |
| `training_manifest.py` | true | build farm-harvest manifest rows for snapshot JSON |

## Acceptance evidence

~~~text
ACTUAL_LABEL_AUTHORITY_SEPARATED=true
FINAL_TARGET_MANIFEST_PERSISTENCE_POLICY_RESOLVED=true
MIGRATION_DECISION_PROVEN=true
NO_PLACEHOLDER_LEGACY_FIELDS=true
CONTRACT_REVIEW_READY=true
~~~

Evidence digest:

~~~text
EVIDENCE_JSON_SHA256=1553f0def25480671416ecd0f5756cdc3c66378e95a4ce0cf7acc0081c57dbad
~~~

Grant remains required before implementation.
