# V0.3-S3-B pairing policy dual issuance R1

## Artifact identity

```text
ARTIFACT_ID=V0_3_S3_B_PAIRING_POLICY_DUAL_ISSUANCE_R1
ARTIFACT_VERSION=s3-b-pairing-policy-dual-issuance-r1-v1
TASK_ID=V0_3_S3_B_PAIRING_POLICY_DUAL_ISSUANCE_R1
TASK_CLASS=CONTROLLED_PRODUCTION_ISSUANCE_MUTATION
AUTHORIZATION_SCOPE=S3_B_PAIRING_POLICY_AND_EXACT_ACTUAL_PAIRING_POLICY_DUAL_ISSUANCE_ONLY
USER_GATE=下一步
USER_AUTHORIZATION=下一步
INTERPRETED_GATE=S3_B_PAIRING_POLICY_DUAL_ISSUANCE_R1
BASE_MAIN_SHA=29443560137cf11daeefa36cfe1bc90b21281717
REQUIRED_BASE_MAIN_SHA=29443560137cf11daeefa36cfe1bc90b21281717
MAIN_MATCHES_REQUIRED_BASE=true
MAIN_CONTAINS_PR546=true
PARENT_PR=546
PARENT_MERGE_COMMIT=29443560137cf11daeefa36cfe1bc90b21281717
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
FINAL_STOP_GATE=COORDINATOR_PAIRING_POLICY_DUAL_ISSUANCE_RE_REVIEW
```

## Preflight

Fetched `origin/main` at `2944356`. Matches required base SHA. PR #546 merge
(policy issuance infrastructure) is contained on main.

## Issuance summary

Dual issuance populates production with exactly two trusted issued pairing
policy records and the corresponding production allowlists. No packages,
authorities, schema versions, or coverage execution are enabled.

| Policy | Version | Grant ID |
| --- | --- | --- |
| General TRAIN/VAL binding pairing | `v0-3-s3-b-train-val-binding-pairing-policy-v1` | `V0_3_S3_B_GENERAL_PAIRING_POLICY_ISSUANCE_GRANT_R1` |
| Exact-actual pairing | `v0-3-s3-b-exact-actual-pairing-policy-v1` | `V0_3_S3_B_EXACT_ACTUAL_PAIRING_POLICY_ISSUANCE_GRANT_R1` |

### General policy record

```text
POLICY_KIND=TRAIN_VAL_BINDING_PAIRING
SEMANTIC_RULE_OR_AUTHORITY=V0_3_S3_B_PAIRING_POLICY_AUTHORITY_CONTRACT
SEMANTIC_AUTHORITY_VERSION=v0-3-s3-b-pairing-policy-authority-contract-v1
PERMITTED_PARTITIONS=TRAIN,VALIDATION
POLICY_RECORD_IDENTITY=1757bebc6342fda123847a60638c0e0c575eed8aa3575d24616180073f0c07eb
CANONICAL_HASH=2dccdc7ad60ffdafa0d4b8cef2212cf46351f3959b2666ddd8d7c3d0dac2d9dc
```

### Exact-actual policy record

```text
POLICY_KIND=EXACT_ACTUAL_PAIRING
SEMANTIC_RULE_OR_AUTHORITY=EXACT_ACTUAL_PAIRED
SEMANTIC_AUTHORITY_VERSION=null
PERMITTED_PARTITIONS=TRAIN,VALIDATION
POLICY_RECORD_IDENTITY=4ee0cbccf291a7fb7a3706e52373e3c5e586339b4c44ae5318ad3635286ea5a2
CANONICAL_HASH=a4adb0a1dffbb796cdf39014747a31e731c4b392e11f3d673a6b611c623a4429
```

## Production mutations

| Control | Before | After |
| --- | --- | --- |
| `PRODUCTION_TRUSTED_ISSUED_PAIRING_POLICY_REGISTRY.count()` | 0 | 2 |
| `_ISSUED_PAIRING_POLICY_VERSIONS` | `frozenset()` | `{v0-3-s3-b-train-val-binding-pairing-policy-v1}` |
| `ISSUED_EXACT_ACTUAL_PAIRING_POLICY_VERSIONS` | `frozenset()` | `{v0-3-s3-b-exact-actual-pairing-policy-v1}` |
| `EXACT_ACTUAL_PAIRING_POLICY_VERSION_STATUS` | `NOT_ISSUED` | `ISSUED` |

## Remaining blocked controls

```text
PRODUCTION_PUBLISHED_PAIRING_PACKAGE_COUNT=0
PRODUCTION_ISSUED_AUTHORITY_RECORD_COUNT=0
ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSION_COUNT=0
S3_B_COVERAGE_EXECUTION=NOT_COMPUTABLE_OR_BLOCKED
TEST_REMAINS_SEALED=true
```

## Dual-gate invariant

Coverage authority verification requires both:

1. Registry-backed `verify_issued_pairing_policy()` pass for the canonical version.
2. Production allowlist membership (`_ISSUED_PAIRING_POLICY_VERSIONS` or
   `ISSUED_EXACT_ACTUAL_PAIRING_POLICY_VERSIONS`).

Neither gate alone is sufficient.

## Historical artifacts

Contract and evidence artifacts from R1 authority contract and issuance infra
remain unchanged. They record `NOT_ISSUED` at the time of their creation.

## Changed files

- `backend/app/forecast_quality/train_val_pairing_policy_registry.py`
- `backend/app/forecast_quality/train_val_trusted_registry.py`
- `backend/app/forecast_quality/train_val_pairing.py`
- `backend/tests/forecast_quality/test_s3_b_pairing_policy_dual_issuance_r1.py`
- `backend/tests/forecast_quality/test_s3_b_pairing_policy_issuance_infra_r1.py`
- `backend/tests/forecast_quality/test_s3_b_pairing_package_authority_infra_r1.py`
- `docs/v0-3/s3/workpapers/s3-b-pairing-policy-dual-issuance-r1.md`
- `docs/v0-3/s3/evidence/s3-b-pairing-policy-dual-issuance-r1.json`
