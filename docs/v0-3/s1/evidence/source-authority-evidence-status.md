# Source Authority and Owner Evidence Status

## Current evidence state

    EVIDENCE_RECORD_ID=V0_3_S1_SOURCE_AUTHORITY_EVIDENCE
    EVIDENCE_RECORD_STATUS=ACCEPTED
    CURRENT_SOURCE_AUTHORITY_BINDING_STATUS=ACCEPTED
    SOURCE_AUTHORITY_STATUS=ACCEPTED
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
    ATTESTATION_VERSION=source-002-final-source-owner-attestation-v1
    ATTESTATION_EFFECTIVE_AT=2026-08-16T21:42:00+08:00
    EFFECTIVE_TIME=BOUND_IN_FINAL_ATTESTATION
    ATTESTATION_STATUS=ATTESTED
    ATTESTATION_HASH=2c7bd156da2eb3d7c2cb5906e23cb3d380f709b43e39e1c6a6ce38f5587971e1
    COVERAGE_SCOPE=BOUND_IN_FINAL_ATTESTATION
    REVISION_POLICY=source-002-idfl-revision-policy-v1;source-002-idfl-revision-policy-identity-v1
    WITHDRAWAL_AND_VOID_POLICY=source-002-withdrawal-policy-v1;source-002-void-propagation-policy-v1
    KNOWN_EXCLUSIONS=NO_KNOWN_BUSINESS_EXCLUSIONS_AT_S1_SOURCE_SCOPE
    MAPPING_SCOPE_MANIFEST_REFERENCE=source-002-mapping-and-scope-identity-v1
    MAPPING_SCOPE_PACKAGE_SHA256=6f07bc878935060f57a2ef24318d6d3b17e27c7f096885f813ac80bed6ac9d10
    INCLUSION_EXCLUSION_MANIFEST_REFERENCE=source-002-inclusion-exclusion-boundary-v1
    CUSTODY_RECORD_REFERENCE=source-002-custody-record-v1
    V0_3_RECORDED_LABEL_PROFILE=RECORDED_BUSINESS_LABEL
    V0_3_RECORDED_LABEL_OPTIONAL_PROVENANCE_FIELDS=transport_before_weighing,storage_before_weighing,postharvest_loss_rule,tare_policy,scale_precision,scale_calibration_authority
    V0_3_RECORDED_LABEL_OPTIONAL_PROVENANCE_HARD_BLOCKER=false
    INDEPENDENT_REVIEW_STATUS=PASS

Source 002 governed evidence and the Package A artifacts now bind source
identity, schema identity, snapshot reference, source hash, local-day boundary,
known-exclusion boundary, reviewed scope-package hashes, and custody-record
reference. Current main now contains the issued final Source Owner Attestation;
PR #238 exact-head independent acceptance `4946622009` and CI `31955752008`
verified it before merge. This status record mirrors that current acceptance and
does not accept Source Cohort or Q2C.

```text
SOURCE_IDENTITY_EVIDENCED=true
PACKAGE_A_FORMALIZATION_APPLIED=true
FORMAL_SOURCE_ATTESTATION_ISSUED=true
SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
CURRENT_CANONICAL_GATE_PASS_COUNT=3
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=14
STATUS_RECONCILIATION_APPLIED=true
FACT_LAYER_RECONCILED_FROM=docs/v0-3/s1/evidence/source-002-governed-snapshot-evidence.md;docs/v0-3/s1/evidence/source-002-completeness-and-custody-business-evidence.md
```

The V0.3 recorded-label profile treats the six pre-weigh process and
weighing-device fields as optional provenance/metrology evidence rather than
hard label-eligibility prerequisites. The reviewed scope identity and custody
artifacts remain supporting evidence for downstream gates; they do not issue
Source Cohort or Q2C acceptance.

## Required evidence still missing

- No Source Authority artifact remains missing after the PR #238 exact-head
  independent acceptance and merge.
- Source Cohort freeze and accepted cohort manifest remain blocked.
- Q2C and other downstream canonical gates remain blocked.
- Final S1 independent review remains pending; this closeout is gate-local.

Private URLs, plaintext storage locators, credentials, personal identity, and
source rows are not permitted in this repository.

## Authority

    AUTHORITY_CONTRACT=docs/v0-3/s1/source-authority-and-cohort-manifest.md
    SOURCE_OWNER_ACCEPTANCE_STATUS=ACCEPTED
    ATTESTATION_ACCEPTANCE_STATUS=ACCEPTED

## Post-PR238 current-main revalidation

```text
POST_PR238_CURRENT_MAIN_REVALIDATION=PASS
PR238_MERGED=true
PR238_MERGE_COMMIT_SHA=d3828041f15d9bba0b201429250a2041bcf63c2f
SOURCE_AUTHORITY_INDEPENDENT_REVIEW_ID=4946622009
SOURCE_AUTHORITY_INDEPENDENT_REVIEW_RESULT=PASS
SOURCE_AUTHORITY_REVIEWED_HEAD_SHA=9b181f4e160981dca7a28fa584855e70a9555f34
SOURCE_AUTHORITY_EXACT_HEAD_CI_RUN_ID=31955752008
SOURCE_AUTHORITY_EXACT_HEAD_CI_CONCLUSION=success
SOURCE_AUTHORITY_MISSING_AUTHORITATIVE_ARTIFACTS=[]
SOURCE_AUTHORITY_MISSING_DECISIONS_OR_AUTHORITIES=[]
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
S1_ACCEPTED=false
```

This current-main revalidation is limited to `S1-SOURCE-AUTHORITY`; it does not
close the cohort, Q2C, custody, visibility, metric, split, holdout, or final S1
acceptance gates.
