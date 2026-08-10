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
    LOCAL_DAY_BOUNDARY=LOCAL_CALENDAR_DAY_00_00_ASIA_SHANGHAI
    HARVEST_BUSINESS_DATE_RULE=扫码称重记录时间转换为 Asia/Shanghai 后直接取自然日日期
    ATTESTATION_VERSION=NOT_PROVIDED
    ATTESTATION_EFFECTIVE_AT=NOT_PROVIDED
    EFFECTIVE_TIME=NOT_PROVIDED
    ATTESTATION_STATUS=NOT_ISSUED
    ATTESTATION_HASH=NOT_ISSUED
    COVERAGE_SCOPE=GOVERNED_PACKAGE_REFERENCE_ONLY
    REVISION_POLICY=NOT_PROVIDED
    WITHDRAWAL_AND_VOID_POLICY=PACKAGE_A_CUSTODY_POLICY_REFERENCE
    KNOWN_EXCLUSIONS=NO_KNOWN_BUSINESS_EXCLUSIONS_AT_S1_SOURCE_SCOPE
    MAPPING_SCOPE_MANIFEST_REFERENCE=source-002-mapping-and-scope-identity-v1
    MAPPING_SCOPE_PACKAGE_SHA256=6f07bc878935060f57a2ef24318d6d3b17e27c7f096885f813ac80bed6ac9d10
    INCLUSION_EXCLUSION_MANIFEST_REFERENCE=source-002-inclusion-exclusion-boundary-v1
    CUSTODY_RECORD_REFERENCE=source-002-custody-record-v1
    V0_3_RECORDED_LABEL_PROFILE=RECORDED_BUSINESS_LABEL
    V0_3_RECORDED_LABEL_OPTIONAL_PROVENANCE_FIELDS=transport_before_weighing,storage_before_weighing,postharvest_loss_rule,tare_policy,scale_precision,scale_calibration_authority
    V0_3_RECORDED_LABEL_OPTIONAL_PROVENANCE_HARD_BLOCKER=false
    INDEPENDENT_REVIEW_STATUS=PENDING

Source 002 governed evidence and the Package A artifacts now bind source
identity, schema identity, snapshot reference, source hash, local-day boundary,
known-exclusion boundary, reviewed scope-package hashes, and custody-record
reference. The formal attestation, effective applicability object, completeness
authority, and attestation hash remain unissued; this record does not create an
attestation object.

```text
SOURCE_IDENTITY_EVIDENCED=true
PACKAGE_A_FORMALIZATION_APPLIED=true
FORMAL_SOURCE_ATTESTATION_ISSUED=false
SOURCE_AUTHORITY_ACCEPTED=false
STATUS_RECONCILIATION_APPLIED=true
FACT_LAYER_RECONCILED_FROM=docs/v0-3/s1/evidence/source-002-governed-snapshot-evidence.md;docs/v0-3/s1/evidence/source-002-completeness-and-custody-business-evidence.md
```

The V0.3 recorded-label profile treats the six pre-weigh process and
weighing-device fields as optional provenance/metrology evidence rather than
hard label-eligibility prerequisites. This does not issue the source
attestation or change the blocked source-authority status. The reviewed scope
identity and custody artifacts are supporting evidence only; they do not issue
source authority acceptance.

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
