# V0.3-S3-B Quantile semantics remediation implementation R1

## Artifact identity

```text
ARTIFACT_ID=V0_3_S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_R1
ARTIFACT_VERSION=s3-b-quantile-semantics-remediation-implementation-r1-v1
TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_R1
TASK_CLASS=AUTHORIZED_PRODUCTION_IMPLEMENTATION_R1_CORRECTION
USER_GATE=可以实施
INTERPRETED_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_R1_CORRECTION
BASE_MAIN_SHA=c74cd2c541fe48b78b5a84de87ef10c16eee976e
PARENT_GRANT_PR=536
PARENT_GRANT_MERGE=c74cd2c541fe48b78b5a84de87ef10c16eee976e
EVIDENCE_JSON_SHA256=02773b7a99c5b5c7c0f5f2e8ca54849499fca60df9da46a851b8e183dcbafdfa
UNAUTHORIZED_PRODUCTION_FILES_CHANGED=NONE
FINAL_TARGET_MODEL_FAMILY=hist_gradient_boosting_final_target_quantile
LEGACY_MODEL_FAMILY=hist_gradient_boosting_quantile
IMPLEMENTATION_REVIEW_READY=false
NEXT_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_R1_REVIEW
```

Correction R1 restores Grant allowlist compliance (`enums.py` / `manifest.py`
unchanged at base), relocates final-target helpers into authorized modules,
uses distinct final-target model family token, `min_grains` eligibility,
`execute_final_target_prediction`, authority-bound core-forecast binding, and
persisted prediction run identity without DB IDs in row content hashes.

Dual-lane implementation: `LEGACY_RESIDUAL_CORRECTION` preserved; new
`FINAL_TARGET_QUANTILE` lane trains direct q=0.50/0.80/0.90 on
`actual_harvest_quantity_kg`, snapshot-only manifest (`manifest_row_count=0`),
canonical JSON snapshot-only prediction persistence (`expected_prediction_row_count=0`),
explicit model identity `final-target-quantile-v1`, and core-forecast binding
via `FinalTargetPredictionAuthority` + `apply_final_target_quantile_to_marketable_curve_rows`.

Semantics remain `VERIFICATION_FAILED`; S3-B coverage unauthorized.
