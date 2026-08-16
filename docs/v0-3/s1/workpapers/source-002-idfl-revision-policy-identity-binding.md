# Source002 IDFL revision-policy identity binding

## 1. Scope and authorization

TASK=SOURCE_002_IDFL_REVISION_POLICY_IDENTITY_BINDING

TASK_CLASS=DOCS_ONLY_GOVERNED_OPAQUE_IDENTITY_BINDING

BASE_MAIN_SHA=b59a9d76603ea4bd1a97df6f80e01c8f03652ba4

This package addresses exactly one hard blocker:
`REVISION_POLICY_IDENTITY_NOT_BOUND_AS_SCHEMA_VALID_OPAQUE_REFERENCE`.
It does not bind late-entry, actual-label visibility, correction, void, final
confirmation, completeness, or final-attestation authority.

REVISION_POLICY_IDENTITY_BINDING_AUTHORIZED=true
LATE_ENTRY_RULE_BINDING_AUTHORIZED=false
ACTUAL_LABEL_VISIBILITY_BINDING_AUTHORIZED=false
CORRECTION_RULE_BINDING_AUTHORIZED=false
VOID_RULE_BINDING_AUTHORIZED=false
FINAL_CONFIRMATION_RULE_BINDING_AUTHORIZED=false
SOURCE_COMPLETENESS_ISSUANCE_AUTHORIZED=false
FINAL_SOURCE_OWNER_ATTESTATION_AUTHORIZED=false
SOURCE_AUTHORITY_ACCEPTANCE_AUTHORIZED=false
SOURCE_COHORT_ACCEPTANCE_AUTHORIZED=false
CANONICAL_GATE_MUTATION_AUTHORIZED=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true

## 2. Revalidated authority inputs

### Accepted IDFL mode

The accepted mode authority is the current-main file
`docs/v0-3/s1/workpapers/immutable-daily-final-label-contract-acceptance-decision.md`.
Its current Git blob is `fe2b09fe9ecf1e0737c34040687097aefd90ffc5`.

DECISION_ID=V0_3_S1_IDFL_V1_ATOMIC_CROSS_CONTRACT_ACCEPTANCE
DECISION=ACCEPT
LABEL_MODE=IMMUTABLE_DAILY_FINAL_LABEL
LABEL_MODE_VERSION=IDFL_V1
MODE_AUTHORITY_PR_NUMBER=180
MODE_AUTHORITY_PR_HEAD_SHA=5added25cbc9be4d35a4517ebff8c34c2144e1a3
MODE_AUTHORITY_PR_MERGE_SHA=6fc689f57fc7f5da7a0c5726472245fd66bc2c9c

The superseded amendment candidate is not used as authority.

### Source002 CGR-006 policy

The source-specific authority is
`docs/v0-3/s1/evidence/source-002-cohort-grain-inclusion-revision-decision-record.json`.
Its current Git blob is `00642bd1deb8f0b66ca6b278c734a5e18617248d`, and its
governed decision-record SHA-256 is
`1d737e1a6e2ce3cfaebf1d3449af86a51572d58333cdc1cdfe397a570084f955`.

SOURCE_SPECIFIC_POLICY_DISPOSITION_ID=CGR-006
SOURCE_SPECIFIC_POLICY_PR_NUMBER=199
SOURCE_SPECIFIC_POLICY_PR_HEAD_SHA=32fe6ce50cdd090df8eaeb0d92008e5748f168c5
SOURCE_SPECIFIC_POLICY_PR_MERGE_SHA=582c5518f120f5dc5719cf13899c3c65d94596b3
SOURCE_SPECIFIC_POLICY_INDEPENDENT_REVIEW_RESULT=PASS

The revalidated CGR-006 semantics remain:

SOURCE_LABEL_MODE=IMMUTABLE_DAILY_FINAL_LABEL / IDFL_V1
LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED=false
REVISION_WINNER_REQUIRED=false
IDFL_WINNER_MANIFEST_REQUIRED=false
IDFL_REVISION_GRAPH_REQUIRED=false
REVISION_POLICY_VERSION=source-002-idfl-revision-policy-v1
WINNER_AND_LINEAGE_RULE=NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE
LATEST_ROW_FALLBACK_ALLOWED=false
LARGEST_REVISION_FALLBACK_ALLOWED=false
DATABASE_ROW_ORDER_AUTHORITY=false
POST_CONFIRMATION_ROW_LEVEL_REVISION_ALLOWED=false
POST_CONFIRMATION_ROW_LEVEL_VOID_ALLOWED=false
SOURCE_REPLACEMENT_REQUIRES_NEW_IDENTITY=true
SOURCE_REPLACEMENT_REQUIRES_NEW_SHA256=true
DOWNSTREAM_INVALIDATION_PROPAGATION_REQUIRED=true
SOURCE_OBJECT_BOUND_ROW_LINEAGE_REQUIRED=true
SOURCE_OBJECT_BOUND_ROW_LINEAGE_IS_SOURCE_SYSTEM_IDENTITY=false
FORECAST_INPUT_REPLAY_REVISION_REQUIREMENTS_PRESERVED=true

No Source002 workbook, raw row, or production database was read for this
binding.

## 3. Issued opaque identity

The independently issued identity is:

REVISION_POLICY_VERSION=source-002-idfl-revision-policy-v1
REVISION_POLICY_IDENTITY=source-002-idfl-revision-policy-identity-v1
WINNER_AND_LINEAGE_RULE=NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE

The identity is deliberately distinct from the version. It identifies the
Source002 actual-harvest IDFL_V1 label-side revision disposition bound to the
accepted IDFL mode and reviewed CGR-006 authority. It is not a row identity,
revision ID, revision graph, historical PIT authority, finalized-at authority,
visibility authority, late-entry authority, completeness authority, Source
Authority acceptance, or Source Cohort acceptance.

## 4. Schema validation

`revision_policy.revision_policy_identity` is defined by
`business-source-attestation.schema.json` as `#/$defs/opaqueReference` with
pattern:

`^(?![A-Za-z]:)(?![A-Za-z][A-Za-z0-9+.-]*://)[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$`

The new identity passed the actual pattern check:

OPAQUE_REFERENCE_SCHEMA_VALIDATION=PASS
OPAQUE_REFERENCE_IS_URI=false
OPAQUE_REFERENCE_IS_STORAGE_PATH=false
OPAQUE_REFERENCE_IS_PRIVATE_LOCATOR=false
IDENTITY_EQUALS_VERSION=false
REVISION_POLICY_IDENTITY_SCHEMA_VALID=true
REVISION_POLICY_IDENTITY_DISTINCT_FROM_VERSION=true

No file path, GitHub URL, private URL, storage path, database ID, Git blob
alone, prose candidate, or revision-winner hash is used as the identity.

## 5. Deterministic binding hash

The binding payload contains only stable governance fields:

```json
{"label_mode":"IMMUTABLE_DAILY_FINAL_LABEL","label_mode_version":"IDFL_V1","mode_authority_decision_id":"V0_3_S1_IDFL_V1_ATOMIC_CROSS_CONTRACT_ACCEPTANCE","mode_authority_pr_head_sha":"5added25cbc9be4d35a4517ebff8c34c2144e1a3","mode_authority_pr_merge_sha":"6fc689f57fc7f5da7a0c5726472245fd66bc2c9c","revision_policy_identity":"source-002-idfl-revision-policy-identity-v1","revision_policy_version":"source-002-idfl-revision-policy-v1","source_dataset":"田间商品果每日采摘净重汇总","source_snapshot_reference":"snapshot:v0_3_s1:002","source_specific_policy_decision_record_sha256":"1d737e1a6e2ce3cfaebf1d3449af86a51572d58333cdc1cdfe397a570084f955","source_specific_policy_disposition_id":"CGR-006","source_specific_policy_pr_head_sha":"32fe6ce50cdd090df8eaeb0d92008e5748f168c5","source_specific_policy_pr_merge_sha":"582c5518f120f5dc5719cf13899c3c65d94596b3","source_system":"扫码称重系统","source_version":"scan-weight-export:v0_3_s1:002","winner_and_lineage_rule":"NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE"}
```

Canonicalization is
`UTF8_JSON_SORT_KEYS_RECURSIVELY_COMPACT_SEPARATORS_ENSURE_ASCII_FALSE`.

REVISION_POLICY_IDENTITY_BINDING_SHA256=bed73c6515073fe36b0e6ceee376644078a1ad988125b40ac48af274135d6b86
REVISION_POLICY_IDENTITY_BINDING_HASH_REPLAY=PASS

The payload excludes timestamps, branch/current PR state, local paths, private
locators, credentials, and personal identity.

## 6. Semantics and implementation boundary

BUSINESS_SEMANTICS_CHANGED=false
IDFL_MODE_SEMANTICS_CHANGED=false
REVISION_POLICY_SEMANTICS_CHANGED=false
REVISION_WINNER_IMPLEMENTED=false
REVISION_GRAPH_CREATED=false
SOURCE_SYSTEM_RECORD_ID_CREATED=false
SOURCE_LIFECYCLE_FACT_SYNTHESIZED=false

This identity binding does not create a winner algorithm, revision graph, or
source-system record. It does not relax the preserved forecast-input replay
requirements or assert any completeness/visibility/lifecycle fact.

## 7. Hard-blocker reconciliation

PREVIOUS_HARD_BLOCKER_COUNT=8
RESOLVED_BLOCKER=REVISION_POLICY_IDENTITY_NOT_BOUND_AS_SCHEMA_VALID_OPAQUE_REFERENCE
REMAINING_HARD_BLOCKER_COUNT_AFTER_THIS_BINDING=7

The remaining seven blockers are unchanged:

1. `SOURCE_002_IDFL_LATE_ENTRY_RULE_NOT_BOUND`
2. `SOURCE_002_IDFL_ACTUAL_LABEL_VISIBILITY_BOUNDARY_NOT_BOUND`
3. `TOP_LEVEL_CORRECTION_RULE_NOT_BOUND`
4. `TOP_LEVEL_VOID_RULE_NOT_BOUND`
5. `TOP_LEVEL_FINAL_CONFIRMATION_RULE_NOT_BOUND`
6. `SOURCE_COMPLETENESS_DECLARATION_AND_WATERMARK_NOT_ISSUED`
7. `FINAL_SOURCE_OWNER_ATTESTATION_EVENT_AND_INDEPENDENT_ACCEPTANCE_NOT_ISSUED`

No remaining blocker is partially resolved by this artifact.

## 8. Canonical state and stop boundary

CURRENT_CANONICAL_GATE_PASS_COUNT=2
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=15
CANONICAL_GATE_STATUS_CHANGED=false
CANONICAL_ACCEPTANCE_RECORD_CHANGED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
FINAL_ATTESTATION_SCHEMA_READY=false
FINAL_ATTESTATION_ISSUANCE_READY=false
FINAL_ATTESTATION_ISSUED=false

The artifact is issued for independent review only. The next permitted action
is:

NEXT_RECOMMENDED_ACTION=RUN_SOURCE_002_IDFL_REVISION_POLICY_IDENTITY_BINDING_EXACT_HEAD_INDEPENDENT_REVIEW

No independent review, Ready, Merge, remaining blocker binding, Source
Authority/Cohort acceptance, Remaining-06, or S2 action is performed by this
task.
