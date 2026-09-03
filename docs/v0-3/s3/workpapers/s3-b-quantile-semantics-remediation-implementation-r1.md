# V0.3-S3-B Quantile semantics remediation implementation R1

## Artifact identity

```text
ARTIFACT_ID=V0_3_S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_R1
ARTIFACT_VERSION=s3-b-quantile-semantics-remediation-implementation-r1-v1
TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_R1
TASK_CLASS=AUTHORIZED_PRODUCTION_IMPLEMENTATION_R1
USER_GATE=可以实施
INTERPRETED_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_R1
BASE_MAIN_SHA=c74cd2c541fe48b78b5a84de87ef10c16eee976e
PARENT_GRANT_PR=536
PARENT_GRANT_MERGE=c74cd2c541fe48b78b5a84de87ef10c16eee976e
EVIDENCE_JSON_SHA256=d6f3bbe6e54e6f7f43fef4502c03c9bf9716c813b93cf37542a1d53b213a9300
```

Dual-lane implementation: `LEGACY_RESIDUAL_CORRECTION` preserved; new
`FINAL_TARGET_QUANTILE` lane trains direct q=0.50/0.80/0.90 on
`actual_harvest_quantity_kg`, snapshot-only manifest (`manifest_row_count=0`),
canonical JSON snapshot-only prediction persistence (`expected_prediction_row_count=0`),
explicit model identity `final-target-quantile-v1`, and core-forecast binding
via `apply_final_target_quantile_to_marketable_curve_rows`.

Semantics remain `VERIFICATION_FAILED`; S3-B coverage unauthorized.
