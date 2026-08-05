# Source Cohort Identity Evidence Status

## Current evidence state

    EVIDENCE_RECORD_ID=V0_3_S1_SOURCE_COHORT_EVIDENCE
    EVIDENCE_RECORD_STATUS=BLOCKED
    CURRENT_SOURCE_COHORT_FREEZE_STATUS=BLOCKED
    SOURCE_COHORT_MANIFEST_STATUS=NOT_ISSUED
    SOURCE_COHORT_ID=NOT_ISSUED
    MANIFEST_VERSION=NOT_PROVIDED
    MANIFEST_HASH=NOT_ISSUED
    SOURCE_OBJECT_IDENTITY_HASHES=NOT_ISSUED
    DECLARED_SOURCE_ROW_COUNT=NOT_PROVIDED
    DECLARED_SOURCE_BYTE_COUNT=NOT_PROVIDED
    INDEPENDENT_REVIEW_STATUS=NOT_STARTED

No source authority identity is available from which to issue a cohort
manifest. No source, cleaned, materialized, split, snapshot, or label rowset
is included or referenced by this record.

## S1/S2 boundary

    S1_FREEZES_SOURCE_COHORT_IDENTITY=true
    S1_FREEZES_FINAL_CLEAN_ROWSET=false
    S2_OWNS_FINAL_MATERIALIZED_ROWSET=true
    SOURCE_ROW_COUNT_IS_DECLARED_SOURCE_METADATA=true
    SOURCE_ROW_COUNT_IS_NOT_S2_ACCEPTED_ROW_COUNT=true
    SOURCE_ROW_COUNT_DOES_NOT_FREEZE_FINAL_ROWSET=true

The missing declared counts are represented as NOT_PROVIDED, never as zero.
This status record does not issue source object hashes or a final rowset
identity. S2 remains unauthorized.

## Required cohort metadata still missing

- Governed cohort identity bound to a source attestation.
- Applicable seasons, farms, subfarms, varieties, and business-date range.
- Versioned mapping, visibility, inclusion, revision, and split policy
  identities.
- Immutable source-object identity hashes and a versioned manifest hash.
- Independent review of the resulting aggregate-only manifest.

## Authority

    AUTHORITY_CONTRACT=docs/v0-3/s1/source-authority-and-cohort-manifest.md
    MANIFEST_SCHEMA=docs/v0-3/s1/schemas/source-cohort-manifest.schema.json
