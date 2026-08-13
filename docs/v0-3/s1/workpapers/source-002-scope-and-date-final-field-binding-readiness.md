# Source 002 scope/date final-field binding readiness

## Purpose

```text
TASK=SOURCE_002_SCOPE_AND_DATE_FINAL_FIELD_BINDING_READINESS
BASE_MAIN_SHA=4e09382c1b6e6905694ead22510e251606e4714a
TARGET_GATE_ID=S1-SOURCE-AUTHORITY
```

This docs-only task evaluates the seven remaining Source002 scope/date fields using already governed repository evidence. It does not issue the final Source Owner Attestation, accept Source Authority, or change a canonical S1 gate.

## Seven fields

```text
coverage_scope.farms
coverage_scope.subfarms
coverage_scope.varieties
coverage_scope.business_date_start
coverage_scope.business_date_end
coverage_summary.first_harvest_business_date
coverage_summary.last_harvest_business_date
```

The schema requires `farms`, `subfarms`, and `varieties` to contain concrete string arrays. Counts and SHA-256 digests cannot substitute for those array values.

## Four date fields are ready

Already governed derivation evidence fixes the canonical Source002 S1 boundaries:

```text
coverage_scope.business_date_start=2025-08-05
coverage_scope.business_date_end=2026-04-16
coverage_summary.first_harvest_business_date=2025-08-05
coverage_summary.last_harvest_business_date=2026-04-16
```

The last observed date is not treated as a completeness watermark.

## Three identity-array fields remain blocked

Existing governed evidence proves:

```text
FARM_COUNT=84
FARMS_ARRAY_SHA256=2daf09d38efb41bada5a1b493974c569e64b63abdd322e5ab4dacc206edb0381
SUBFARM_COUNT=192
SUBFARMS_ARRAY_SHA256=921a56006d1a75f683c62c8a930e913fc39cabf2dcffec88b16549ed95945e13
VARIETY_COUNT=20
VARIETIES_ARRAY_SHA256=fe6274775796193318fa3ad504ba8cc4e2196b8c58dd8f795cec80cc22c26209
```

The full arrays are not stored in Git. Therefore the three array fields are not ready for final binding even though their deterministic derivation and digests were previously validated.

Earlier governed evidence records an external derived-value package:

```text
PACKAGE_ID=source-002-attestation-derived-values-v1
PACKAGE_SHA256=5b362513ae4ffb9279ba978c64c566f75bc2cda12d10fb0f4bab1a5c445f3fe9
PACKAGE_COMMITTED_TO_GIT=false
FULL_IDENTITY_ARRAYS_IN_PACKAGE_ONLY=true
RAW_ROWS_IN_PACKAGE=false
```

This task does not access that package. A later separately authorized gate may use it as the preferred source of the concrete arrays after identity verification.

## Readiness result

```text
SCOPE_DATE_REQUIRED_FIELD_COUNT=7
READY_FOR_FINAL_FIELD_BINDING_COUNT=4
BLOCKED_FINAL_FIELD_BINDING_COUNT=3
ALL_7_FIELDS_READY=false
DATE_BINDING_READINESS_COMPLETE=true
IDENTITY_ARRAY_BINDING_READINESS_COMPLETE=false
FINAL_ATTESTATION_SCHEMA_READY=false
FINAL_ATTESTATION_ISSUANCE_READY=false
SOURCE_OWNER_ATTESTATION_ISSUED=false
SOURCE_AUTHORITY_ACCEPTED=false
CURRENT_CANONICAL_GATE_PASS_COUNT=0
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=17
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
```

The remaining three blockers require controlled availability of the already-derived concrete identity arrays; they do not require the Source Owner to repeat previously confirmed business facts.

## Stop boundary

After this readiness PR passes its own CI/review/Ready/Merge sequence, the next business gate is:

```text
NEXT_BUSINESS_GATE=SOURCE_002_SCOPE_IDENTITY_ARRAY_CONTROLLED_VALUE_INTAKE_AND_FINAL_BINDING_READINESS
NEXT_BUSINESS_GATE_AUTHORIZED=false
```

Final attestation issuance, Source Authority acceptance, canonical gate mutation, Remaining06, and V0.3 S2 remain unauthorized.

```text
EXACT_HEAD_INDEPENDENT_REVIEW_REQUIRED=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```
