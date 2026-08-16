# V0.3-S1 Source 002 IDFL Top-Level Correction Rule Binding

## 1. Scope and authorization

This docs-only artifact binds only the Source 002 IDFL top-level
`correction_rule` required by the Business Source Attestation schema. It is
issued for independent review and resolves only
`TOP_LEVEL_CORRECTION_RULE_NOT_BOUND`.

```text
ARTIFACT_ID=V0_3_S1_SOURCE_002_IDFL_TOP_LEVEL_CORRECTION_RULE_BINDING
ARTIFACT_VERSION=source-002-idfl-correction-rule-binding-v1
ARTIFACT_STATUS=ISSUED_FOR_INDEPENDENT_REVIEW
TASK=SOURCE_002_IDFL_TOP_LEVEL_CORRECTION_RULE_BINDING
TASK_CLASS=DOCS_ONLY_GOVERNED_TOP_LEVEL_CORRECTION_RULE_BINDING
BASE_MAIN_SHA=50eea0857d9ab6565a016e6c4af2d33194e405bb

SOURCE_SYSTEM=扫码称重系统
SOURCE_DATASET=田间商品果每日采摘净重汇总
SOURCE_VERSION=scan-weight-export:v0_3_s1:002
SOURCE_SNAPSHOT_REFERENCE=snapshot:v0_3_s1:002
LABEL_MODE=IMMUTABLE_DAILY_FINAL_LABEL
LABEL_MODE_VERSION=IDFL_V1
```

No Source 002 workbook, raw rows, production database, test data, or holdout
data was read. No metrics, backtest, or model training was executed.

## 2. Authority basis

The source-class fact authority is
`docs/v0-3/s1/workpapers/actual-harvest-immutable-daily-label-compatibility-decision.md`,
Git blob `48aa581cd37d116bd4405018242a9d6e94e22f36`. It records the governed
representation as `IMMUTABLE_DAILY_BUSINESS_AGGREGATE`, with
`POST_CONFIRMATION_MODIFICATION_RULE=NO_MODIFICATION`,
`POST_CONFIRMATION_MODIFICATION=false`, and no synthetic lifecycle authority.
The source-class facts say correction is not applicable to the current IDFL
representation; they do not claim that an external source system can never
support late entry or another lifecycle capability.

Business-owner decision D-007 is read from
`docs/v0-3/s1/evidence/source-authority-and-scope-business-owner-decision-record.json`,
Git blob `0edbd06acb2bae07b227a23b2e558d032e6efcfe`, with governed decision
record SHA-256
`d5f8e46b7d634def4c5e3ba968e0310925c7b710701850f75728edb589184e69`.
Its approved values prohibit post-confirmation IDFL row revision, require a
new identity and SHA-256 for source-object replacement, prohibit silent source
object/value replacement, and require downstream propagation for withdrawal or
replacement. Unfinished affected gates remain blocked. A formal final Source
Owner Attestation is not issued by D-007.

The Source002-specific CGR-006 evidence is read from
`docs/v0-3/s1/evidence/source-002-cohort-grain-inclusion-revision-decision-record.json`,
Git blob `00642bd1deb8f0b66ca6b278c734a5e18617248d`, with decision-record
SHA-256
`1d737e1a6e2ce3cfaebf1d3449af86a51572d58333cdc1cdfe397a570084f955`.
It reaffirms the IDFL label mode, no label-side revision winner, no
post-confirmation row-level revision or void, new source identity/SHA-256 for
replacement, and downstream invalidation propagation. It is supporting
Source002 policy authority, not Source Authority or Source Cohort acceptance.

## 3. Formal correction rule and schema validation

The exact literal bound by this artifact is:

```text
CORRECTION_POLICY_VERSION=source-002-idfl-correction-rule-v1
CORRECTION_RULE=NO_POST_CONFIRMATION_ROW_LEVEL_CORRECTION_IN_GOVERNED_IDFL_LABEL_REPRESENTATION; SOURCE_OBJECT_REPLACEMENT_REQUIRES_NEW_IDENTITY_AND_SHA256; SILENT_VALUE_REPLACEMENT_PROHIBITED; DOWNSTREAM_INVALIDATION_PROPAGATION_REQUIRED
CORRECTION_RULE_SCOPE=SOURCE_002_ACTUAL_LABEL_IDFL_V1_ONLY
CORRECTION_RULE_STATUS=BOUND_FOR_INDEPENDENT_REVIEW
```

The current schema
`docs/v0-3/s1/schemas/business-source-attestation.schema.json`, Git blob
`a8e53f6f8c571d481bba54585de175d2060dd93c`, defines
`#/properties/correction_rule` as a string with `minLength=1`. The exact
literal passes the type and non-empty validation:

```text
CORRECTION_RULE_SCHEMA_VALIDATION=PASS
CORRECTION_RULE_NON_EMPTY=true
```

This is a minimal formal binding of already-governed D-007/CGR-006 direction.
It does not create a correction implementation, source-system record ID,
revision graph, revision winner, source timestamp, visibility rule, or
completeness declaration.

## 4. Deterministic binding hash

The JSON artifact contains a stable `binding_payload` with source identity,
IDFL mode, the exact correction literal, D-007/CGR-006 stable authority
identities and hashes, and the governed replacement/propagation semantics. It
excludes timestamp, branch name, PR state, local filesystem path, credentials,
private locator, personal identity, current CI state, and mutable completeness
state.

```text
BINDING_CANONICALIZATION=UTF8_JSON_SORT_KEYS_RECURSIVELY_COMPACT_SEPARATORS_ENSURE_ASCII_FALSE
CORRECTION_RULE_BINDING_SHA256=b2308929eaa9592c2ad306378f8fa05abf8e361aab496d6a0e8d54df5b98f63e
CORRECTION_RULE_BINDING_HASH_REPLAY=PASS
```

## 5. Hard-blocker reconciliation

The current-main state begins with five hard blockers. This package resolves
only the top-level correction-rule binding. The four remaining blockers are
unchanged:

```text
PREVIOUS_HARD_BLOCKER_COUNT=5
RESOLVED_BLOCKER=TOP_LEVEL_CORRECTION_RULE_NOT_BOUND
REMAINING_HARD_BLOCKER_COUNT_AFTER_THIS_BINDING=4
REMAINING_HARD_BLOCKERS=(
TOP_LEVEL_VOID_RULE_NOT_BOUND
TOP_LEVEL_FINAL_CONFIRMATION_RULE_NOT_BOUND
SOURCE_COMPLETENESS_DECLARATION_AND_WATERMARK_NOT_ISSUED
FINAL_SOURCE_OWNER_ATTESTATION_EVENT_AND_INDEPENDENT_ACCEPTANCE_NOT_ISSUED
)
```

This task does not bind `void_rule`, `final_confirmation_rule`, source
completeness, or final attestation.

## 6. Canonical state and stop boundary

No canonical artifact was modified and no gate changed:

```text
CURRENT_CANONICAL_GATE_PASS_COUNT=2
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=15
CANONICAL_GATE_STATUS_CHANGED=false
CANONICAL_ACCEPTANCE_RECORD_CHANGED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false

VOID_RULE_BINDING_AUTHORIZED=false
FINAL_CONFIRMATION_RULE_BINDING_AUTHORIZED=false
SOURCE_COMPLETENESS_ISSUANCE_AUTHORIZED=false
FINAL_SOURCE_OWNER_ATTESTATION_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The next permitted action is
`RUN_SOURCE_002_IDFL_TOP_LEVEL_CORRECTION_RULE_EXACT_HEAD_INDEPENDENT_REVIEW`.
This package stops before independent review, Ready, Merge, void-rule or
final-confirmation binding, completeness issuance, final Source Owner
Attestation, Source Authority/Cohort acceptance, Remaining-06, or V0.3-S2.
