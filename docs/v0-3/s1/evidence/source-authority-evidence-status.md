# Source Authority and Owner Evidence Status

## Current evidence state

    EVIDENCE_RECORD_ID=V0_3_S1_SOURCE_AUTHORITY_EVIDENCE
    EVIDENCE_RECORD_STATUS=BLOCKED
    CURRENT_SOURCE_AUTHORITY_BINDING_STATUS=BLOCKED
    SOURCE_AUTHORITY_STATUS=NOT_ISSUED
    SOURCE_OWNER_ROLE=农场数据负责人
    SOURCE_SYSTEM=扫码称重系统
    SOURCE_DATASET=田间商品果每日采摘净重汇总
    SOURCE_VERSION=scan-weight-export:v0_3_s1:002
    SCHEMA_VERSION=observed-source-schema-v1
    SCHEMA_HASH=919e63c4d3b4d00b304a045f63bfb050d4eb9abec3b0a318186b7ca2e7276867
    SOURCE_SNAPSHOT_REFERENCE=snapshot:v0_3_s1:002
    SOURCE_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
    SOURCE_BYTE_COUNT=28668416
    SOURCE_ROW_COUNT=233171
    ATTESTATION_VERSION=NOT_PROVIDED
    ATTESTATION_EFFECTIVE_AT=NOT_PROVIDED
    EFFECTIVE_TIME=NOT_PROVIDED
    ATTESTATION_STATUS=NOT_ISSUED
    ATTESTATION_HASH=NOT_ISSUED
    COVERAGE_SCOPE=NOT_PROVIDED
    REVISION_POLICY=NOT_PROVIDED
    WITHDRAWAL_AND_VOID_POLICY=NOT_PROVIDED
    KNOWN_EXCLUSIONS=NOT_PROVIDED
    INDEPENDENT_REVIEW_STATUS=NOT_STARTED

Source 002 governed evidence supplies source identity, schema identity,
snapshot reference, source hash, and owner-role facts. Those values are now
reconciled into the fact layer. The formal attestation, effective scope,
policy identities, and attestation hash remain unissued; this record does not
create an attestation object.

```text
SOURCE_IDENTITY_EVIDENCED=true
FORMAL_SOURCE_ATTESTATION_ISSUED=false
SOURCE_AUTHORITY_ACCEPTED=false
STATUS_RECONCILIATION_APPLIED=true
FACT_LAYER_RECONCILED_FROM=docs/v0-3/s1/evidence/source-002-governed-snapshot-evidence.md;docs/v0-3/s1/evidence/source-002-completeness-and-custody-business-evidence.md
```

## Required evidence still missing

- Formal source-owner authority status and attestation binding.
- Source applicability effective time, coverage scope, revision policy, and
  withdrawal/void policy identities.
- A canonical attestation hash over the supplied attestation object.
- Independent review of the complete evidence package.

Private URLs, plaintext storage locators, credentials, personal identity, and
source rows are not permitted in this repository.

## Authority

    AUTHORITY_CONTRACT=docs/v0-3/s1/source-authority-and-cohort-manifest.md
    SOURCE_OWNER_ACCEPTANCE_STATUS=BLOCKED
    ATTESTATION_ACCEPTANCE_STATUS=BLOCKED
