# V0.3-S3-B Quantile semantics remediation implementation R1

## Artifact identity

```text
ARTIFACT_ID=V0_3_S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_R1
ARTIFACT_VERSION=s3-b-quantile-semantics-remediation-implementation-r1-v1
TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_R1
TASK_CLASS=AUTHORIZED_PRODUCTION_IMPLEMENTATION_R1_CORRECTION_2
USER_GATE=可以实施
INTERPRETED_GATE=V03_S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_R1_CORRECTION_2
BASE_MAIN_SHA=c74cd2c541fe48b78b5a84de87ef10c16eee976e
PARENT_GRANT_PR=536
PARENT_GRANT_MERGE=c74cd2c541fe48b78b5a84de87ef10c16eee976e
EVIDENCE_JSON_SHA256=82eaf19425c7f0c3e8d5824dff5bcf850a496f61a1bd5b760da74efc7ed22f0c
UNAUTHORIZED_PRODUCTION_FILES_CHANGED=NONE
CANONICAL_PY_DIFF_FROM_BASE=false
CANONICAL_PY_BASE_BLOB=1550da6e887d48a54ef355af1b976bad4f2c54b8
CANONICAL_PY_FINAL_BLOB=1550da6e887d48a54ef355af1b976bad4f2c54b8
IMPLEMENTATION_REVIEW_READY=false
NEXT_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_R1_REVIEW
```

Correction 2 restores `canonical.py` to grant base; `final_target_prediction_row_content_payload`
lives in authorized `persistence.py`. Row content hashes exclude DB run IDs; persisted
authority still requires real `model_run_id` / `prediction_run_id` after reload.

Dual-lane implementation: `LEGACY_RESIDUAL_CORRECTION` preserved; new
`FINAL_TARGET_QUANTILE` lane trains direct q=0.50/0.80/0.90 on
`actual_harvest_quantity_kg`, snapshot-only manifest (`manifest_row_count=0`),
canonical JSON snapshot-only prediction persistence (`expected_prediction_row_count=0`),
explicit model identity `final-target-quantile-v1`, and core-forecast binding
via `FinalTargetPredictionAuthority` + `apply_final_target_quantile_to_marketable_curve_rows`.

Semantics remain `VERIFICATION_FAILED`; S3-B coverage unauthorized.
