# V0.3-S1 Source 002 IDFL Top-Level Void Rule Binding

## 1. Scope and authorization

This docs-only artifact binds only the Source 002 IDFL top-level `void_rule`
required by the Business Source Attestation schema. It is issued for
independent review and resolves only `TOP_LEVEL_VOID_RULE_NOT_BOUND`.

```text
ARTIFACT_ID=V0_3_S1_SOURCE_002_IDFL_TOP_LEVEL_VOID_RULE_BINDING
ARTIFACT_VERSION=source-002-idfl-top-level-void-rule-binding-v1
ARTIFACT_STATUS=ISSUED_FOR_INDEPENDENT_REVIEW
TASK=SOURCE_002_IDFL_TOP_LEVEL_VOID_RULE_BINDING
TASK_CLASS=DOCS_ONLY_GOVERNED_TOP_LEVEL_VOID_RULE_BINDING
BASE_MAIN_SHA=b0609096236e207056bcb4bf5f1cf0c9f57eeaec

SOURCE_SYSTEM=扫码称重系统
SOURCE_DATASET=田间商品果每日采摘净重汇总
SOURCE_VERSION=scan-weight-export:v0_3_s1:002
SOURCE_SNAPSHOT_REFERENCE=snapshot:v0_3_s1:002
LABEL_MODE=IMMUTABLE_DAILY_FINAL_LABEL
LABEL_MODE_VERSION=IDFL_V1
```

No Source 002 workbook, raw rows, production database, test data, or holdout
data was read. No metrics, backtest, or model training was executed. No
canonical acceptance record was changed.

## 2. Source-class and Source Owner authority

The source-class fact authority is
`docs/v0-3/s1/workpapers/actual-harvest-immutable-daily-label-compatibility-decision.md`,
Git blob `48aa581cd37d116bd4405018242a9d6e94e22f36`. It records
`SOURCE_MODEL=IMMUTABLE_DAILY_BUSINESS_AGGREGATE`,
`POST_CONFIRMATION_MODIFICATION_RULE=NO_MODIFICATION`,
`POST_CONFIRMATION_MODIFICATION=false`,
`VOID_OR_CANCELLATION_SCENARIO=NOT_APPLICABLE`,
`VOID_WORKFLOW_NOT_APPLICABLE=true`,
`SOURCE_FACT_ABSENCE_PRESERVED=true`, and
`NO_SYNTHETIC_LIFECYCLE_AUTHORITY=true`.

Those facts describe the current governed Source002 representation. They do
not assert that an external scan-weigh system lacks a technical void or
withdrawal capability.

The Source Owner confirmation is read from
`docs/v0-3/s1/evidence/source-002-final-attestation-readiness-refresh.json`,
Git blob `3838b8d30c089c5c0087ea4b5e812cc9f42fe9cd`. It was merged through PR
211, head `de097f849b30c6a2c654132912173d84caba1597`, merge
`4e09382c1b6e6905694ead22510e251606e4714a`:

```text
CONFIRMATION_TEXT=数据是准确的，没有撤回和作废
RECORDED_DATA_ACCURACY=CONFIRMED_BY_SOURCE_OWNER
WITHDRAWAL_EXISTS=false
VOID_EXISTS=false
WITHDRAWAL_STATUS_RULE=NO_WITHDRAWAL
VOID_STATUS_RULE=NO_VOID
CONFIRMATION_SCOPE=SOURCE002_RECORDED_DATA_ACCURACY_AND_WITHDRAWAL_VOID_BUSINESS_STATE_ONLY
DOES_NOT_ISSUE_BROADER_COMPLETENESS_WATERMARK=true
DOES_NOT_CONFIRM_EVERY_FINAL_ATTESTATION_FIELD=true
```

`NO_VOID` and `NO_WITHDRAWAL` are current governed Source002 business-state
facts only. They do not become external-system capability-absence claims.

## 3. D-007, CGR-006, and accepted IDFL authority

Business Owner decision D-007 is read from
`docs/v0-3/s1/evidence/source-authority-and-scope-business-owner-decision-record.json`,
Git blob `0edbd06acb2bae07b227a23b2e558d032e6efcfe`, with decision-record
SHA-256
`d5f8e46b7d634def4c5e3ba968e0310925c7b710701850f75728edb589184e69`.
It governs no post-confirmation IDFL row void, new identity and SHA-256 for
source-object replacement, no silent replacement, downstream propagation, and
blocking affected unfinished gates. Its withdrawal and void policy versions
are `source-002-withdrawal-policy-v1` and
`source-002-void-propagation-policy-v1`.

Source002 CGR-006 is read from
`docs/v0-3/s1/evidence/source-002-cohort-grain-inclusion-revision-decision-record.json`,
Git blob `00642bd1deb8f0b66ca6b278c734a5e18617248d`, with decision-record
SHA-256
`1d737e1a6e2ce3cfaebf1d3449af86a51572d58333cdc1cdfe397a570084f955`.
It confirms no post-confirmation row-level void, replacement identity/SHA
requirements, downstream invalidation propagation, and source-object-bound
lineage.

The accepted IDFL mode authority is
`docs/v0-3/s1/workpapers/immutable-daily-final-label-contract-acceptance-decision.md`,
Git blob `fe2b09fe9ecf1e0737c34040687097aefd90ffc5`:

```text
MODE_AUTHORITY_DECISION_ID=V0_3_S1_IDFL_V1_ATOMIC_CROSS_CONTRACT_ACCEPTANCE
MODE_AUTHORITY_DECISION=ACCEPT
MODE_AUTHORITY_PR_HEAD_SHA=5added25cbc9be4d35a4517ebff8c34c2144e1a3
MODE_AUTHORITY_PR_MERGE_SHA=6fc689f57fc7f5da7a0c5726472245fd66bc2c9c
```

## 4. Formal void rule and schema validation

The exact literal bound by this artifact is:

```text
VOID_POLICY_VERSION=source-002-idfl-void-rule-v1
VOID_RULE_SCOPE=SOURCE_002_ACTUAL_LABEL_IDFL_V1_ONLY
VOID_RULE=NO_POST_CONFIRMATION_ROW_LEVEL_VOID_IN_GOVERNED_IDFL_LABEL_REPRESENTATION; CURRENT_GOVERNED_SOURCE_OBJECT_VOID_STATUS=NO_VOID; SOURCE_OBJECT_WITHDRAWAL_OR_REPLACEMENT_REQUIRES_DOWNSTREAM_INVALIDATION_PROPAGATION; AFFECTED_UNFINISHED_GATES_BECOME_BLOCKED
VOID_RULE_STATUS=BOUND_FOR_INDEPENDENT_REVIEW
VOID_RULE_SCHEMA_VALIDATION=PASS
VOID_RULE_NON_EMPTY=true
```

The current schema
`docs/v0-3/s1/schemas/business-source-attestation.schema.json`, Git blob
`a8e53f6f8c571d481bba54585de175d2060dd93c`, defines
`#/properties/void_rule` as a string with `minLength=1`. The literal passes
that type and non-empty validation.

```text
POST_CONFIRMATION_ROW_LEVEL_VOID_ALLOWED=false
CURRENT_GOVERNED_SOURCE_OBJECT_WITHDRAWAL_STATUS=NO_WITHDRAWAL
CURRENT_GOVERNED_SOURCE_OBJECT_VOID_STATUS=NO_VOID
CURRENT_GOVERNED_SOURCE_OBJECT_WITHDRAWAL_EXISTS=false
CURRENT_GOVERNED_SOURCE_OBJECT_VOID_EXISTS=false
SOURCE_OBJECT_WITHDRAWAL_OR_REPLACEMENT_REQUIRES_DOWNSTREAM_INVALIDATION_PROPAGATION=true
AFFECTED_UNFINISHED_GATES_BECOME_BLOCKED=true
EXTERNAL_SOURCE_SYSTEM_VOID_CAPABILITY_CLAIMED=false
EXTERNAL_SOURCE_SYSTEM_WITHDRAWAL_CAPABILITY_CLAIMED=false
```

The binding does not claim an external-system capability absence. It does not
issue completeness, promote a coverage end watermark, create lifecycle facts,
or accept Source Authority or Source Cohort.

## 5. Deterministic binding hash

The JSON artifact contains a stable `binding_payload` covering Source002
identity, IDFL mode, the exact void literal, Source Owner current-state
confirmation and provenance, D-007, CGR-006, and mode-authority identities and
hashes. It excludes timestamp, branch name, PR state, CI state, local paths,
credentials, private locators, personal identity, and mutable completeness
watermark state.

```text
BINDING_CANONICALIZATION=UTF8_JSON_SORT_KEYS_RECURSIVELY_COMPACT_SEPARATORS_ENSURE_ASCII_FALSE
VOID_RULE_BINDING_SHA256=f6ee0538e3a8ac906687cb428266a180a61e54cc6f33a338849a5f27a01286f2
VOID_RULE_BINDING_HASH_REPLAY=PASS
AUTHORIZED_PAYLOAD_REQUIRED_FIELDS_PRESENT=true
```

## 6. Hard-blocker reconciliation

The current main after PR #233 merge begins with four hard blockers. This
artifact resolves only the top-level void-rule binding. The three listed below
are the outcome after this binding enters main; they are not the pre-merge
current-main count:

```text
PREVIOUS_HARD_BLOCKER_COUNT=4
RESOLVED_BLOCKER=TOP_LEVEL_VOID_RULE_NOT_BOUND
REMAINING_HARD_BLOCKER_COUNT_AFTER_THIS_BINDING=3
REMAINING_HARD_BLOCKERS=(
TOP_LEVEL_FINAL_CONFIRMATION_RULE_NOT_BOUND
SOURCE_COMPLETENESS_DECLARATION_AND_WATERMARK_NOT_ISSUED
FINAL_SOURCE_OWNER_ATTESTATION_EVENT_AND_INDEPENDENT_ACCEPTANCE_NOT_ISSUED
)
OTHER_BLOCKERS_PARTIALLY_RESOLVED=false
```

This task does not bind `final_confirmation_rule`, issue completeness, or
issue a final Source Owner Attestation.

## 7. Canonical state and stop boundary

No canonical artifact was modified and no gate changed:

```text
CURRENT_CANONICAL_GATE_PASS_COUNT=2
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=15
CANONICAL_GATE_STATUS_CHANGED=false
CANONICAL_ACCEPTANCE_RECORD_CHANGED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
FINAL_ATTESTATION_SCHEMA_READY=false
FINAL_ATTESTATION_ISSUANCE_READY=false
FINAL_ATTESTATION_ISSUED=false
SOURCE_COMPLETENESS_ISSUED=false
SOURCE_COMPLETE_THROUGH_BUSINESS_DATE=NOT_ISSUED

VOID_RULE_BINDING_AUTHORIZED=true
FINAL_CONFIRMATION_RULE_BINDING_AUTHORIZED=false
SOURCE_COMPLETENESS_ISSUANCE_AUTHORIZED=false
FINAL_SOURCE_OWNER_ATTESTATION_AUTHORIZED=false
SOURCE_AUTHORITY_ACCEPTANCE_AUTHORIZED=false
SOURCE_COHORT_ACCEPTANCE_AUTHORIZED=false
CANONICAL_GATE_MUTATION_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The next permitted action is
`RUN_SOURCE_002_IDFL_TOP_LEVEL_VOID_RULE_EXACT_HEAD_INDEPENDENT_REVIEW`.
This package stops before independent review, Ready, Merge,
`final_confirmation_rule` binding, completeness issuance, final attestation,
Source Authority/Cohort acceptance, Remaining-06, or V0.3-S2.
