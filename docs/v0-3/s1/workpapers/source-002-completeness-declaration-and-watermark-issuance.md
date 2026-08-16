# Source002 completeness declaration and watermark issuance

## Artifact identity

```text
ARTIFACT_ID=V0_3_S1_SOURCE_002_COMPLETENESS_DECLARATION_AND_WATERMARK_ISSUANCE
ARTIFACT_VERSION=source-002-completeness-declaration-and-watermark-issuance-v1
ARTIFACT_STATUS=ISSUED_FOR_INDEPENDENT_REVIEW
TASK=SOURCE_002_COMPLETENESS_DECLARATION_AND_WATERMARK_ISSUANCE
TASK_CLASS=DOCS_ONLY_GOVERNED_COMPLETENESS_DECLARATION_AND_WATERMARK_ISSUANCE
BASE_MAIN_SHA=1e9e6b2484888d3ff06d9f7270d72c5f055856d4
SOURCE_COMPLETENESS_POLICY_VERSION=source-002-completeness-policy-v1
COMPLETENESS_DECLARATION_VERSION=source-002-completeness-declaration-v1
```

This package issues a governed completeness declaration for the fixed
Source002 object for independent review. It does not accept Source Authority,
issue the final Source Owner Attestation, mutate a canonical gate, or authorize
any downstream phase.

## Source identity and authority

```text
SOURCE_SYSTEM=扫码称重系统
SOURCE_DATASET=田间商品果每日采摘净重汇总
SOURCE_VERSION=scan-weight-export:v0_3_s1:002
SOURCE_SNAPSHOT_REFERENCE=snapshot:v0_3_s1:002
SOURCE_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
SOURCE_BYTE_COUNT=28668416
SOURCE_ROW_COUNT=233171
SCHEMA_VERSION=observed-source-schema-v1
SCHEMA_SHA256=919e63c4d3b4d00b304a045f63bfb050d4eb9abec3b0a318186b7ca2e7276867
```

The fixed identity is reused from the current-main aggregate governance
evidence at
`docs/v0-3/s1/evidence/source-002-governed-snapshot-evidence.md`, Git blob
`140f649ddc17a443e08316818acc0d00b79c371b`. This task did not reopen or scan
the Source002 workbook or row-level data.

The business-owner authority record is
`docs/v0-3/s1/evidence/source-authority-and-scope-business-owner-decision-record.json`,
Git blob `0edbd06acb2bae07b227a23b2e558d032e6efcfe`:

```text
D005_DECISION_ID=D-005
COMPLETENESS_DECLARATION_OWNER_ROLE=农场数据负责人
D005_PRIOR_COMPLETENESS_DECLARATION_ISSUED=false
D005_PRIOR_SOURCE_COMPLETENESS_AUTHORITY_ACCEPTED=false
D007_DECISION_ID=D-007
SOURCE_OBJECT_REPLACEMENT_REQUIRES_NEW_IDENTITY=true
SOURCE_OBJECT_REPLACEMENT_REQUIRES_NEW_SHA256=true
SILENT_SOURCE_OBJECT_REPLACEMENT=false
SILENT_VALUE_REPLACEMENT=false
WITHDRAWAL_OR_REPLACEMENT_REQUIRES_DOWNSTREAM_PROPAGATION=true
AFFECTED_UNFINISHED_GATES_BECOME_BLOCKED=true
WITHDRAWAL_POLICY_VERSION=source-002-withdrawal-policy-v1
VOID_PROPAGATION_POLICY_VERSION=source-002-void-propagation-policy-v1
FORMAL_FINAL_SOURCE_ATTESTATION_ISSUED=false
```

D-005 establishes the completeness declaration role. D-007 establishes the
replacement identity/SHA and downstream invalidation boundary. Neither
authority is changed by this package.

## Completeness policy and explicit declaration

```text
COMPLETENESS_SCOPE=FIXED_SOURCE_002_OBJECT
COMPLETENESS_DECLARATION_OWNER_ROLE=农场数据负责人
SOURCE_COMPLETE_THROUGH_BUSINESS_DATE=2026-04-16
COMPLETENESS_DECLARATION_EVENT=产季结束核对完成后，由农场数据负责人确认固定 Source002 对象截至声明日期的数据完整性
POST_DECLARATION_OMISSION_HANDLING=WITHDRAW_OR_REPLACE_SOURCE_OBJECT
REPLACEMENT_REQUIRES_NEW_IDENTITY=true
REPLACEMENT_REQUIRES_NEW_SHA256=true
SILENT_REPLACEMENT_ALLOWED=false
DOWNSTREAM_INVALIDATION_REQUIRED=true
AFFECTED_UNFINISHED_GATES_BECOME_BLOCKED=true
WATERMARK_PROVENANCE=EXPLICIT_BUSINESS_COMPLETENESS_CONFIRMATION
MAX_OBSERVED_DATE_USED_AS_INFERENCE=false
```

`2026-04-16` is issued here from the explicit business completeness
confirmation. It is not promoted because it happens to be the observed maximum
date.

## Scope and July disposition

```text
RAW_OBSERVED_START=2025-07-22
RAW_OBSERVED_END=2026-04-16
CANONICAL_COVERAGE_START=2025-08-05
CANONICAL_COVERAGE_END=2026-04-16
JULY_UNMAPPED_DATE=2025-07-22
JULY_UNMAPPED_ROW_COUNT=2
RAW_ROWS_RETAINED=true
CANONICAL_S1_COHORT_INCLUDED=false
AUTOMATIC_SEASON_ASSIGNMENT=false
COMPLETENESS != CANONICAL_COHORT_INCLUSION
```

The July disposition remains a season/cohort mapping decision. The two raw
rows remain retained and outside the canonical S1 cohort. It is not changed
into a completeness exception.

## Missingness boundary

The existing governed missingness result is reused without recalculation:

```text
MISSING_DAY_RULE=EXPLICIT_SOURCE_DATA_LOSS_ONLY
MISSING_DAY_COUNT=0
MISSING_DATA_PROPORTION=0.00000000
SOURCE_LOSS_STATUS=NO_KNOWN_SOURCE_DATA_LOSS_FOR_GOVERNED_SCOPE
```

The prior `MISSING_DAY_COUNT=0` is not itself completeness proof. The authority
for this package's watermark is the new explicit business completeness
confirmation above.

## Declaration state and current-main boundary

```text
COMPLETENESS_DECLARATION_STATUS=ISSUED_FOR_INDEPENDENT_REVIEW
SOURCE_002_COMPLETENESS_AUTHORITY_ISSUED=true
SOURCE_002_COMPLETENESS_AUTHORITY_ACCEPTED=false
SOURCE_COMPLETENESS_WATERMARK_ISSUED=true
CURRENT_MAIN_COMPLETENESS_AUTHORITY_ISSUED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
FINAL_SOURCE_OWNER_ATTESTATION_ISSUED=false
FINAL_ATTESTATION_ISSUED=false
```

The declaration is issued in this Draft PR. `CURRENT_MAIN_COMPLETENESS_AUTHORITY_ISSUED=false`
remains true until this PR is merged; no current-main state is silently
rewritten.

## Watermark is not a lifecycle timestamp

```text
SOURCE_COMPLETENESS_WATERMARK_AS_SOURCE_RECORDED_AT=false
SOURCE_COMPLETENESS_WATERMARK_AS_SOURCE_AVAILABLE_AT=false
SOURCE_COMPLETENESS_WATERMARK_AS_LABEL_VISIBILITY_TIME=false
SOURCE_COMPLETENESS_WATERMARK_AS_FINALIZED_AT=false
WATERMARK_IS_SOURCE_OBJECT_COMPLETENESS_ONLY=true
```

The completeness watermark is not `source_recorded_at`,
`source_available_at`, label visibility time, or `finalized_at`.

## Deterministic evidence payload

The JSON `evidence_payload` binds the fixed source object, schema identity,
explicit declaration, scope boundaries, July disposition, and D-007 replacement
and invalidation rules. The canonicalization is:

```text
UTF8_JSON_SORT_KEYS_RECURSIVELY_COMPACT_SEPARATORS_ENSURE_ASCII_FALSE
```

The final file records the independently replayed hash:

```text
SOURCE_COMPLETENESS_EVIDENCE_HASH=ee30f3ddcc615453ff923b38622d256659c1bcc2609dcd47ddeef1fce0b00d47
SOURCE_COMPLETENESS_EVIDENCE_HASH_REPLAY=PASS
DECLARED_SHA256=ee30f3ddcc615453ff923b38622d256659c1bcc2609dcd47ddeef1fce0b00d47
REPLAYED_SHA256=ee30f3ddcc615453ff923b38622d256659c1bcc2609dcd47ddeef1fce0b00d47
```

## Hard blockers and governance boundary

Before this PR merges, current main has two remaining blockers. The
prospective state after this PR merges has one:

```text
PREVIOUS_HARD_BLOCKER_COUNT=2
RESOLVED_BLOCKER=SOURCE_COMPLETENESS_DECLARATION_AND_WATERMARK_NOT_ISSUED
REMAINING_HARD_BLOCKER_COUNT_AFTER_MERGE=1
REMAINING_HARD_BLOCKERS=(
FINAL_SOURCE_OWNER_ATTESTATION_EVENT_AND_INDEPENDENT_ACCEPTANCE_NOT_ISSUED
)
OTHER_BLOCKERS_PARTIALLY_RESOLVED=false
CURRENT_MAIN_PRE_MERGE_HARD_BLOCKER_COUNT=2

CURRENT_CANONICAL_GATE_PASS_COUNT=2
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=15
CANONICAL_GATE_STATUS_CHANGED=false
CANONICAL_ACCEPTANCE_RECORD_CHANGED=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
```

## Validation results

All scoped checks were executed against the final JSON/Markdown artifacts and
the Git-tracked authority evidence. No Source002 raw workbook or row-level
data was reopened.

```text
JSON_SYNTAX=PASS
JSON_MARKDOWN_PARITY=PASS
SOURCE_IDENTITY_PARITY=PASS
D005_OWNER_ROLE_AUTHORITY_PARITY=PASS
D007_REPLACEMENT_INVALIDATION_AUTHORITY_PARITY=PASS
COMPLETE_THROUGH_DATE_PARITY=PASS
COMPLETENESS_DECLARATION_EVENT_PARITY=PASS
JULY_DISPOSITION_PRESERVED=PASS
WATERMARK_NOT_LIFECYCLE_TIMESTAMP=PASS
DETERMINISTIC_EVIDENCE_HASH_REPLAY=PASS
CHANGED_FILE_SCOPE=PASS
GIT_DIFF_CHECK=PASS
```

The next permitted action is independent review of this exact-head Draft PR:

```text
INDEPENDENT_REVIEW_REQUIRED=true
INDEPENDENT_REVIEW_PERFORMED=false
READY_AUTHORIZED=false
READY_PERFORMED=false
MERGE_AUTHORIZED=false
MERGE_PERFORMED=false
FINAL_SOURCE_OWNER_ATTESTATION_PERFORMED=false
SOURCE_COMPLETENESS_ISSUANCE_AUTHORIZED=true
FINAL_SOURCE_OWNER_ATTESTATION_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```
