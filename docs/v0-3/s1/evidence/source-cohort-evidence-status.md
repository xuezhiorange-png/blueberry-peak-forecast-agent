# Source Cohort Identity Evidence Status

## Current evidence state

    EVIDENCE_RECORD_ID=V0_3_S1_SOURCE_COHORT_EVIDENCE
    EVIDENCE_RECORD_STATUS=BLOCKED
    CURRENT_SOURCE_COHORT_FREEZE_STATUS=BLOCKED
    SOURCE_COHORT_MANIFEST_STATUS=NOT_ISSUED
    SOURCE_COHORT_ID=NOT_ISSUED
    MANIFEST_VERSION=NOT_PROVIDED
    MANIFEST_HASH=NOT_ISSUED
    SOURCE_OBJECT_IDENTITY_HASHES=SOURCE_002_SHA256_FC83859871C544B584B3999B6796DDD518CDC8BB8DD9754F5B5C9D6AE62DB81A
    SOURCE_OBJECT_IDENTITY_HASHES_STATUS=AVAILABLE_PREPARATION_ONLY
    DECLARED_SOURCE_ROW_COUNT=233171
    DECLARED_SOURCE_BYTE_COUNT=28668416
    LOCAL_DAY_BOUNDARY=LOCAL_CALENDAR_DAY_00_00_ASIA_SHANGHAI
    KNOWN_EXCLUSIONS=NO_KNOWN_BUSINESS_EXCLUSIONS_AT_S1_SOURCE_SCOPE
    GOVERNED_SCOPE_IDENTITY_MANIFEST_STATUS=ISSUED_FOR_INDEPENDENT_REVIEW
    GOVERNED_SCOPE_IDENTITY_MANIFEST_REFERENCE=source-002-mapping-and-scope-identity-v1
    GOVERNED_SCOPE_IDENTITY_PACKAGE_SHA256=6f07bc878935060f57a2ef24318d6d3b17e27c7f096885f813ac80bed6ac9d10
    FARMS_ARRAY_SHA256=2daf09d38efb41bada5a1b493974c569e64b63abdd322e5ab4dacc206edb0381
    SUBFARMS_ARRAY_SHA256=921a56006d1a75f683c62c8a930e913fc39cabf2dcffec88b16549ed95945e13
    VARIETIES_ARRAY_SHA256=fe6274775796193318fa3ad504ba8cc4e2196b8c58dd8f795cec80cc22c26209
    FARM_COUNT=84
    SUBFARM_COUNT=192
    VARIETY_COUNT=20
    INCLUSION_EXCLUSION_MANIFEST_STATUS=ISSUED_FOR_INDEPENDENT_REVIEW
    INCLUSION_EXCLUSION_MANIFEST_REFERENCE=source-002-inclusion-exclusion-boundary-v1
    CUSTODY_RECORD_STATUS=ISSUED_FOR_INDEPENDENT_REVIEW
    CUSTODY_RECORD_REFERENCE=source-002-custody-record-v1
    MAPPED_SEASON_IDENTITIES=[2025~2026]
    MAPPED_CANONICAL_GROUP_COUNT=529
    UNMAPPED_ROW_COUNT=2
    UNMAPPED_DISTINCT_DATE_COUNT=1
    INDEPENDENT_REVIEW_STATUS=NOT_STARTED

Source 002 governed evidence now supplies source-object identity and aggregate
coverage metadata for preparation. It still does not issue a cohort identity,
manifest version, manifest hash, scope arrays, or a final rowset.

```text
SOURCE_COHORT_FACTS_RECONCILED=true
PACKAGE_A_FORMALIZATION_APPLIED=true
FORMAL_SOURCE_COHORT_MANIFEST_CREATED=false
SOURCE_COHORT_ACCEPTED=false
STATUS_RECONCILIATION_APPLIED=true
FACT_LAYER_RECONCILED_FROM=docs/v0-3/s1/evidence/source-002-governed-snapshot-evidence.md
```

## S1/S2 boundary

    S1_FREEZES_SOURCE_COHORT_IDENTITY=true
    S1_FREEZES_FINAL_CLEAN_ROWSET=false
    S2_OWNS_FINAL_MATERIALIZED_ROWSET=true
    SOURCE_ROW_COUNT_IS_DECLARED_SOURCE_METADATA=true
    SOURCE_ROW_COUNT_IS_NOT_S2_ACCEPTED_ROW_COUNT=true
    SOURCE_ROW_COUNT_DOES_NOT_FREEZE_FINAL_ROWSET=true

The reconciled counts and reviewed identity-package hashes are preparation
metadata, never an accepted S2 row count or a source-cohort manifest. The full
84/192/20 arrays remain outside Git, and this status record does not issue a
final rowset identity or a cohort manifest. S2 remains unauthorized.

## Required cohort metadata still missing

- Governed cohort identity bound to a source attestation.
- Concrete scope arrays inside a schema-valid source-cohort manifest; the
  Package A reference intentionally stores counts and hashes only.
- Versioned mapping, visibility, inclusion, revision, and split policy
  identities.
- A versioned cohort manifest hash bound to the available source-object
  identity and aggregate scope evidence.
- Independent review of the resulting aggregate-only manifest.

## Authority

    AUTHORITY_CONTRACT=docs/v0-3/s1/source-authority-and-cohort-manifest.md
    MANIFEST_SCHEMA=docs/v0-3/s1/schemas/source-cohort-manifest.schema.json
