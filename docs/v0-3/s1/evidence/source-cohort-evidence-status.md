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

The reconciled counts are preparation metadata, never an accepted S2 row
count. This status record does not issue a final rowset identity or a cohort
manifest. S2 remains unauthorized.

## Required cohort metadata still missing

- Governed cohort identity bound to a source attestation.
- Applicable seasons, farms, subfarms, varieties, and business-date range.
- Versioned mapping, visibility, inclusion, revision, and split policy
  identities.
- A versioned cohort manifest hash bound to the available source-object
  identity and aggregate scope evidence.
- Independent review of the resulting aggregate-only manifest.

## Authority

    AUTHORITY_CONTRACT=docs/v0-3/s1/source-authority-and-cohort-manifest.md
    MANIFEST_SCHEMA=docs/v0-3/s1/schemas/source-cohort-manifest.schema.json
