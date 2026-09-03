# V0.3-S3-B Quantile semantics remediation implementation R1 (amended)

## Artifact identity

```text
ARTIFACT_ID=V0_3_S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_R1
ARTIFACT_VERSION=s3-b-quantile-semantics-remediation-implementation-r1-v1
TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_REMEDIATION_AMENDED_IMPLEMENTATION_R1
TASK_CLASS=AUTHORIZED_AMENDED_IMPLEMENTATION_R1
USER_GATE=可以实施
INTERPRETED_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_AMENDED_IMPLEMENTATION_R1
BASE_MAIN_SHA=4f515bd3261bdb3e07ac95650a09508ea56b8b64
PARENT_GRANT_AMENDMENT_PR=539
PARENT_GRANT_AMENDMENT_MERGE=4f515bd3261bdb3e07ac95650a09508ea56b8b64
PARENT_GRANT_AMENDMENT_EVIDENCE_JSON_SHA256=d54b56b91fe1897b5dc92bd59b60f1684fa595e76ecc8e0a7ccbcfd9d68a7a04
PARENT_CONTRACT_AMENDMENT_PR=538
PRE_REBASE_HEAD=43dbe2a3aec80086cba0c3d96b33795c906619de
POST_REBASE_HEAD=0933158e53daf1f847ab8a1112f7f14ae229a55d
MIGRATION_REVISION=f3a9b2c8d1e4
MIGRATION_DOWN_REVISION=e8b2c4d6f1a3
FAKE_TASK9_SENTINEL_REMOVED=true
FINAL_TARGET_PREDICTION_MODE=final_target_quantile
EVIDENCE_JSON_SHA256=0a14996c592e80bf3e482a7f070e8ead4f1b55b81b0a407acaeea7aad7ab1554
UNAUTHORIZED_PRODUCTION_FILES_CHANGED=NONE
IMPLEMENTATION_REVIEW_READY=false
NEXT_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_AMENDED_IMPLEMENTATION_R1_REVIEW
```

Amended implementation R1 on PR #537 after Grant Amendment #539 merge resolves the
`FINAL_TARGET_PREDICTION_PERSISTENCE_SCHEMA_CONTRACT_MISMATCH` blocker from Contract
Amendment #538.

Migration `f3a9b2c8d1e4` adds `prediction_target_kind`, nullable Task9 columns for the
final-target lane only, `final_target_quantile` mode, `distinct_grain_count`, and a
PostgreSQL lane-consistency CHECK. Final-target prediction runs persist with lawful
`task9_run_id=NULL`, `task9_result_hash=NULL`, and `mode=final_target_quantile` — no
fake Task9 sentinels (`task9_run_id=0`, all-zero hash).

Final-target training stores `distinct_factory_count=0` and `distinct_grain_count` as
the distinct `(farm_id, subfarm_id, variety_id)` TRAIN grain count. Legacy lane
preserves non-null Task9 authority and `distinct_grain_count=0`.

Direct q=0.50/0.80/0.90 on `actual_harvest_quantity_kg` remains unchanged. Canonical
JSON snapshot-only prediction persistence and authority-bound core forecast binding
remain in place. Semantics remain `VERIFICATION_FAILED`; S3-B coverage unauthorized.
