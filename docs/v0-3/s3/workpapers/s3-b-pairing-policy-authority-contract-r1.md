# V0.3-S3-B pairing policy authority contract R1

## Artifact identity

```text
ARTIFACT_ID=V0_3_S3_B_PAIRING_POLICY_AUTHORITY_CONTRACT_R1
ARTIFACT_VERSION=s3-b-pairing-policy-authority-contract-r1-v1
TASK_ID=V0_3_S3_B_PAIRING_POLICY_AUTHORITY_CONTRACT_R1
TASK_CLASS=READ_ONLY_DISCOVERY_AND_CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_B_PAIRING_POLICY_AND_EXACT_ACTUAL_PAIRING_POLICY_AUTHORITY_CONTRACT_ONLY
USER_GATE=下一步
INTERPRETED_GATE=S3_B_PAIRING_POLICY_AUTHORITY_CONTRACT_R1_DEFINITION
BASE_MAIN_SHA=66ae5601865ff483e73f962431c21e02f2af2a69
BASE_MAIN_TREE_SHA=78512484a467a91e93fa10e2c0fb6fc89d01b8fc
REQUIRED_BASE_MAIN_SHA=66ae5601865ff483e73f962431c21e02f2af2a69
MAIN_MATCHES_REQUIRED_BASE=true
MAIN_CONTAINS_PR544=true
PARENT_PR=544
PARENT_MERGE_COMMIT=66ae5601865ff483e73f962431c21e02f2af2a69
CONTRACT_PATH=docs/v0-3/s3/s3-b-pairing-policy-authority-contract.md
PRODUCTION_CHANGED_FILES=NONE
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
FINAL_STOP_GATE=COORDINATOR_PAIRING_POLICY_AUTHORITY_CONTRACT_RE_REVIEW
```

## Preflight

Fetched `origin/main` at `66ae560`. Matches required base SHA. PR #544 merge
is contained (`7478d38` ancestor of main).

Pairing infrastructure landed on main:

- `backend/app/forecast_quality/train_val_pairing.py`
- `backend/app/forecast_quality/train_val_trusted_registry.py`
- `backend/app/forecast_quality/quantile_coverage.py` (registry-backed gate)

Production issued sets remain empty. No policy versions issued.

## Discovery summary

### Equivalent family

```text
EXISTING_EQUIVALENT_POLICY_AUTHORITY_FAMILY=false
```

Parent pairing package contract (`s3-train-val-binding-pairing-package-contract.md`)
names policy version fields and states `NOT_ISSUED` but does not define unified
policy issuance authority. This contract fills that gap without duplicating the
package envelope or partition authority issuance definitions.

### Current-main policy truth

| Item | Value |
| --- | --- |
| `TRAIN_VAL_PAIRING_POLICY_V1` | `v0-3-s3-b-train-val-binding-pairing-policy-v1` |
| Pairing policy status | NOT_ISSUED |
| `FROZEN_EXACT_ACTUAL_PAIRING_RULE` | `EXACT_ACTUAL_PAIRED` |
| Versioned exact-actual policy ID | NOT_AVAILABLE |
| `ISSUED_PAIRING_POLICY_VERSION_COUNT` | 0 |
| `ISSUED_EXACT_ACTUAL_PAIRING_POLICY_VERSION_COUNT` | 0 |
| `ISSUED_SCHEMA_VERSION_COUNT` | 0 |
| `PRODUCTION_PUBLISHED_PACKAGE_COUNT` | 0 |
| `PRODUCTION_ISSUED_AUTHORITY_RECORD_COUNT` | 0 |

### Proposed exact-actual policy version

```text
PROPOSED_EXACT_ACTUAL_PAIRING_POLICY_VERSION=v0-3-s3-b-exact-actual-pairing-policy-v1
EXACT_ACTUAL_PAIRING_POLICY_VERSION_DEFINED=true
EXACT_ACTUAL_PAIRING_POLICY_VERSION_ISSUED=false
```

`v0-2-exact-actual-paired-v1` not present on main; not reused.

## Semantic authority paths

- `docs/forecast-quality/s3-quality-metrics-contract.md` §11.1–§11.3
- `docs/v0-3/s3/s3-quantile-semantics-remediation-contract.md` §3.2
- `docs/v0-3/s3/s3-quantile-semantics-contract.md` §3
- `backend/app/forecast_quality/quantile_coverage.py` `_is_exact_actual_paired()`

Coverage mask unchanged.

## Issuance authority (frozen)

```text
WHO_ISSUES_PAIRING_POLICY=FUTURE_S3_B_PAIRING_POLICY_ISSUANCE_GRANT
WHO_ISSUES_EXACT_ACTUAL_PAIRING_POLICY=FUTURE_S3_B_EXACT_ACTUAL_PAIRING_POLICY_ISSUANCE_GRANT
POLICY_CONSTANT_EXISTENCE != POLICY_ISSUANCE
CALLER_DEFINED_VERSION_STRING_IS_NOT_AUTHORITY=true
```

## Producer gap

```text
V0_3_PARTITION_SCOPED_S3_BINDING_ROW_PRODUCER_AVAILABLE=false
ROW_LEVEL_PARTITION_MEMBERSHIP_PROVEN=false
REAL_PAIRING_PACKAGE_MATERIALIZATION_ELIGIBLE=false
```

### Materialization prerequisites (pre-materialization only)

```text
REAL_PAIRING_PACKAGE_MATERIALIZATION_PREREQUISITES=
  GENERAL_PAIRING_POLICY_ISSUED
  EXACT_ACTUAL_PAIRING_POLICY_ISSUED
  V0_3_PARTITION_SCOPED_S3_BINDING_ROW_PRODUCER_AVAILABLE
  ROW_LEVEL_PARTITION_MEMBERSHIP_PROVEN
  lawful source-002/e5-live-v1 actuals authority available
  lawful incumbent forecast + cutoff authority available
  TEST_REMAINS_SEALED
```

Post-materialization steps (publication, authority issuance, schema registration)
are **not** materialization prerequisites.

### Full Coverage-chain remaining prerequisites

```text
REMAINING_COVERAGE_EXECUTION_CHAIN=
  policy issuance → partition-scoped producer → row-level membership proof
  → real package materialization → package verification → package publication
  → partition authority issuance → schema registration → Coverage execution authorization
```

```text
MATERIALIZATION_PREREQUISITES != FULL_COVERAGE_CHAIN_PREREQUISITES
```

## Issuance order

Policy semantics → version identity → explicit grant → allowlist update →
partition-scoped producer → package materialization → publication → authority
record → schema registration → Coverage.

Each step independently authorized.

## Out of scope

No production code. No policy issuance. No package publication. No Coverage
execution. TEST remains sealed.
