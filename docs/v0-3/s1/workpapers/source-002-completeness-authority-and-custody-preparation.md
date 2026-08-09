# V0.3-S1 Source 002 Completeness Authority and Custody Preparation

## Workpaper identity and boundary

```text
WORKPAPER_ID=V0_3_S1_SOURCE_002_COMPLETENESS_AUTHORITY_AND_CUSTODY_PREPARATION
WORKPAPER_STATUS=PREPARED_FOR_BUSINESS_AND_GOVERNANCE_EVIDENCE
BASELINE_MAIN_SHA=91c39de15145df0e293dac5f4495452b4a74ad99

SOURCE_CLASS=ACTUAL_HARVEST_LABEL
SOURCE_SYSTEM=扫码称重系统
SOURCE_DATASET=田间商品果每日采摘净重汇总
SOURCE_VERSION=scan-weight-export:v0_3_s1:002
SOURCE_SNAPSHOT_REFERENCE=snapshot:v0_3_s1:002
SOURCE_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
SOURCE_OWNER_ROLE=农场数据负责人

LABEL_MODE=IMMUTABLE_DAILY_FINAL_LABEL
LABEL_MODE_VERSION=IDFL_V1
IMMUTABLE_DAILY_FINAL_LABEL_ACCEPTED=true
SOURCE_002_IDFL_V1_MODE_COMPATIBILITY=PASS

SOURCE_002_COMPLETENESS_AUTHORITY_ISSUED=false
SOURCE_002_CUSTODY_RECORD_ISSUED=false
SOURCE_002_SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_002_SOURCE_COHORT_ACCEPTED=false
SOURCE_002_SOURCE_SPECIFIC_ACCEPTANCE_ISSUED=false
```

This is a preparation workpaper. It defines the evidence and governance
inputs required for a future reviewed decision; it does not issue a
completeness authority, custody record, source attestation, source authority,
source cohort, Q2C decision, or S1 acceptance.

The workpaper does not reopen or parse Source 002, request source rows, create
a snapshot, import business data, or write to a database.

## Existing facts reused without re-asking

The following facts are reused from already accepted business and aggregate
evidence. They are not re-confirmed by this workpaper and are not upgraded to
formal completeness or custody authority.

```text
SOURCE_SYSTEM=扫码称重系统
SOURCE_DATASET=田间商品果每日采摘净重汇总
SOURCE_OWNER_ROLE=农场数据负责人
SOURCE_EFFECTIVE_SEASON=2024~2025产季起
SPREADSHEET_IS_INDEPENDENT_SOURCE=false
SPREADSHEET_ROLE=扫码系统导出、汇总或整理副本

SOURCE_VERSION=scan-weight-export:v0_3_s1:002
SOURCE_SNAPSHOT_REFERENCE=snapshot:v0_3_s1:002
SOURCE_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
SOURCE_BYTE_COUNT=28668416
OBSERVED_SCHEMA_VERSION=observed-source-schema-v1
SCHEMA_SHA256=919e63c4d3b4d00b304a045f63bfb050d4eb9abec3b0a318186b7ca2e7276867
SOURCE_ROW_COUNT=233171

OBSERVED_FIRST_HARVEST_BUSINESS_DATE=2025-07-22
OBSERVED_LAST_HARVEST_BUSINESS_DATE=2026-04-16

BUSINESS_REPORTED_LATE_ENTRY_SCENARIO=NOT_APPLICABLE
BUSINESS_REPORTED_NO_RECORD_INTERPRETATION=当日无记录表示当日无采摘
BUSINESS_RULE_POST_CONFIRMATION_MODIFICATION_ALLOWED=false
BUSINESS_RULE_POST_CONFIRMATION_DELETION_ALLOWED=false
BUSINESS_RULE_CORRECTION_AFTER_CONFIRMATION_SUPPORTED=false
BUSINESS_RULE_VOID_AFTER_CONFIRMATION_SUPPORTED=false

EXISTING_BUSINESS_FACTS_REUSED=true
BUSINESS_OWNER_ROLE_RECONFIRMATION_REQUIRED=false
EXISTING_SOURCE_OBJECT_IDENTITY_EVIDENCE_REUSED=true
SOURCE_002_RE_READ_THIS_TASK=false
SOURCE_HASH_RECOMPUTED_THIS_TASK=false
SCHEMA_HASH_RECOMPUTED_THIS_TASK=false
ROW_LEVEL_EVIDENCE_RECOMPUTED_THIS_TASK=false
```

`SOURCE_OWNER_ROLE=农场数据负责人` identifies the recorded source-owner role.
It does not by itself identify the role authorized to issue a completeness
declaration or control custody access. The observed last business date is
descriptive coverage evidence only.

## Completeness authority: required contract and current state

IDFL_V1 requires an explicit source-object completeness authority. The
requirement is separate from source-record timestamps, label visibility, and
the observed maximum date.

```text
SOURCE_OBJECT_COMPLETENESS_AUTHORITY_REQUIRED=true
SOURCE_COMPLETE_THROUGH_BUSINESS_DATE_REQUIRED=true
SOURCE_COMPLETENESS_POLICY_VERSION_REQUIRED=true
SOURCE_COMPLETENESS_EVIDENCE_HASH_REQUIRED=true

SOURCE_COMPLETE_THROUGH_BUSINESS_DATE=NOT_ISSUED
SOURCE_COMPLETENESS_POLICY_VERSION=NOT_ISSUED
SOURCE_COMPLETENESS_EVIDENCE_HASH=NOT_ISSUED
SOURCE_002_COMPLETENESS_AUTHORITY_ACCEPTED=false
SOURCE_002_COMPLETENESS_GATE=BLOCKED

MAX_OBSERVED_DATE_IS_COMPLETENESS_WATERMARK=false
EXPORT_DATE_IS_COMPLETENESS_WATERMARK=false
LATE_ENTRY_NOT_APPLICABLE_IS_COMPLETENESS_PROOF=false
NO_RECORD_BUSINESS_INTERPRETATION_IS_COMPLETENESS_PROOF=false
ROW_COUNT_IS_COMPLETENESS_PROOF=false
SOURCE_HASH_IS_COMPLETENESS_PROOF=false
SCHEMA_VALIDATION_IS_COMPLETENESS_PROOF=false

SOURCE_COMPLETENESS_WATERMARK_AS_SOURCE_RECORDED_AT=false
SOURCE_COMPLETENESS_WATERMARK_AS_SOURCE_AVAILABLE_AT=false
SOURCE_COMPLETENESS_WATERMARK_AS_LABEL_VISIBILITY_TIME=false
SOURCE_COMPLETENESS_WATERMARK_AS_FINALIZED_AT=false
EXPORT_TIME_AS_SOURCE_RECORDED_AT=false
```

### Candidate completeness-authority semantics

For a specified immutable source object, `SOURCE_COMPLETE_THROUGH_BUSINESS_DATE`
would mean that, through and including the declared business date, all valid
records that belong to the governed source scope and should normally be in
that object have been included under the formal completeness policy. It is a
source-object completeness watermark, not a record-event time or visibility
time.

The watermark is not any of the following:

- the maximum date observed in the export;
- the file creation date or export timestamp;
- Git commit time, import time, or database commit time;
- `source_recorded_at`, `source_available_at`, or `finalized_at`;
- a label-observation cutoff.

For every included IDFL label date, the future accepted authority must support:

```text
HARVEST_BUSINESS_DATE <= SOURCE_COMPLETE_THROUGH_BUSINESS_DATE
```

The comparison is valid only after the watermark is formally issued and
bound to the immutable source object or source snapshot authority.

## Required completeness policy package

The following policy is required before a formal completeness authority can be
issued. The policy identity and substantive answers are not provided by this
preparation task.

```text
SOURCE_COMPLETENESS_POLICY_VERSION=NOT_ISSUED
COMPLETENESS_DECLARATION_EVENT=NOT_PROVIDED
COMPLETENESS_DECLARATION_OWNER_ROLE=NOT_PROVIDED
LATE_RECORD_HANDLING_POLICY=NOT_PROVIDED
COMPLETENESS_REPLACEMENT_POLICY=NOT_PROVIDED
```

The future policy must define:

1. Source scope: the source system, dataset, immutable source version or
   snapshot, covered business dates, and covered farm/subfarm/variety scope.
2. Completion event: the real business or operational condition that permits
   a date to be declared complete.
3. Declaration authority: the role authorized to make that declaration,
   distinguished from the recorded source-owner role where applicable.
4. Late-arriving records: what happens if an omission is discovered after a
   completeness declaration, including whether the object is withdrawn or a
   replacement object is issued.
5. Replacement: the requirement that an incomplete or erroneous source
   object is not silently edited in place; its status is versioned, a
   replacement receives a new identity and hash, and downstream dependencies
   are invalidated or regenerated.

Examples such as daily close, a data-owner check, or post-season
reconciliation are possible business processes only. None is selected as the
formal completion event by this workpaper.

## Minimum completeness evidence package

The future evidence record must contain at least:

```text
SOURCE_COMPLETENESS_EVIDENCE_FIELDS=
source_system,
source_dataset,
source_version,
source_snapshot_reference,
source_object_sha256,
source_complete_through_business_date,
source_completeness_policy_version,
completeness_declaration_owner_role,
completeness_declaration_status,
completeness_effective_at,
known_completeness_exceptions,
source_completeness_evidence_hash

COMPLETENESS_DECLARATION_STATUS=NOT_ISSUED
KNOWN_COMPLETENESS_EXCEPTIONS=NOT_ISSUED
SOURCE_COMPLETENESS_EVIDENCE_HASH=NOT_ISSUED
```

No future hash may be fabricated from the existing source hash. The source
object hash identifies the object; the completeness evidence hash identifies
the governed declaration and its canonicalized evidence.

## Business and governance evidence request: completeness

```text
BUSINESS_AND_GOVERNANCE_EVIDENCE_REQUEST=PREPARED
BUSINESS_AND_GOVERNANCE_EVIDENCE_REQUEST_SENT=false
```

Only the following unresolved completeness questions remain. Previously
confirmed business rules are not repeated.

### Q1 — Complete-through date

For the fixed Source 002 export object, can the responsible authority formally
confirm through which business date, inclusive, the data is complete?

Required answer format:

```text
YYYY-MM-DD
```

or:

```text
NOT_CONFIRMED
```

The question must be answered from the real completeness process. It does not
presuppose the observed maximum date.

### Q2 — Completeness determination rule

What actual business or operational process was used to determine that the
declared date and all earlier in-scope data had entered this export object?
The answer should describe the real process, not merely repeat that the file
has a maximum observed date. Examples such as daily close, data-owner review,
or post-season reconciliation are prompts only, not prefilled answers.

### Q3 — Completeness authority role

Which job role is authorized to formally declare that this Source 002 object
is complete through a specified business date? This role must be distinguished
from `SOURCE_OWNER_ROLE` if the governance responsibilities differ.

### Q4 — Exception handling

If a missing or omitted record is discovered after completeness has been
declared, what formal business process applies to the original export object?
The answer must distinguish, for example, withdrawal and re-export, issuance
of a new version, another formal process, or the current absence of a formal
rule.

## Custody record: current state and required fields

```text
SOURCE_002_CUSTODY_RECORD_STATUS=NOT_ISSUED
SOURCE_002_CUSTODY_ACCEPTED=false
CUSTODY_RECORD_HASH=NOT_ISSUED
CUSTODY_POLICY_VERSION=NOT_ISSUED
WITHDRAWAL_POLICY_VERSION=NOT_ISSUED
VOID_PROPAGATION_POLICY_VERSION=NOT_ISSUED
EXTERNAL_OBJECT_BINDING_HASH=NOT_ISSUED
```

The future governed custody record must contain policy identities and
non-sensitive bindings only:

```text
CUSTODY_RECORD_FIELDS=
custody_policy_version,
storage_type,
access_owner_role,
source_owner_role,
approved_usage_purpose,
least_privilege_scope,
authorized_role_set,
credential_reference_policy,
retention_policy_version,
retention_period_or_rule,
withdrawal_policy_version,
void_propagation_policy_version,
downstream_propagation_targets,
external_object_binding_hash,
custody_record_hash
```

The custody record is a source-object governance record. It is not the source
object hash, a source attestation hash, a cohort manifest hash, or a row-level
lineage manifest.

## Custody evidence boundary

The custody preparation may retain storage type, role names, policy identity,
opaque governed references, and SHA-256 hashes. It must not retain or request
specific locators or credentials.

```text
REAL_DATA_ALLOWED_IN_GIT=false
PLAINTEXT_STORAGE_LOCATOR_ALLOWED=false
CREDENTIAL_ALLOWED_IN_GIT=false
PERSONAL_IDENTITY_REQUIRED=false
```

The following are prohibited from this workpaper and any future Git evidence:

- local, NAS, Windows-drive, bucket, or other storage paths;
- signed or private URLs;
- usernames, passwords, tokens, or connection strings;
- personal names or personal accounts.

## Business and governance evidence request: custody

```text
CUSTODY_EVIDENCE_REQUEST=PREPARED
CUSTODY_EVIDENCE_REQUEST_SENT=false
```

### C1 — Storage type

What type of storage system or medium currently preserves the fixed Source 002
export object? A type such as managed file storage, enterprise drive, object
storage, controlled local archive, or another category is sufficient. No path
or URL is requested.

### C2 — Access owner role

Which job role controls access permissions for this source object? A role is
required; no personal name or account is requested.

```text
ACCESS_OWNER_ROLE=NOT_PROVIDED
```

### C3 — Authorized role set

Which job roles may read this source object for the blueberry production
forecasting project? Roles are required; no personal names or credentials are
requested.

```text
AUTHORIZED_ROLE_SET=NOT_PROVIDED
```

### C4 — Approved purpose

Is the approved use of this fixed source object the governed management of
historical actual-harvest labels and model evaluation for blueberry production
forecasting?

```text
APPROVED_USAGE_PURPOSE=NOT_PROVIDED
```

This is a governance question, not an accepted purpose statement.

### C5 — Retention

How long must this fixed source object be retained, or what retention rule
governs it?

```text
RETENTION_POLICY_VERSION=NOT_ISSUED
RETENTION_PERIOD_OR_RULE=NOT_PROVIDED
```

### C6 — Withdrawal and replacement

If the export object is found to be erroneous or incomplete, which role may
declare it withdrawn, and how is the replacement object produced? The answer
must state whether the original is withdrawn and versioned, whether the
replacement receives a new identity, and how downstream users are notified or
invalidated.

Business-record immutability does not imply that a source object can never be
withdrawn or replaced.

## Candidate withdrawal and replacement governance

The following rules are a future candidate policy only. They are defined for
review and are not accepted custody rules in this workpaper.

```text
WITHDRAWAL_REPLACEMENT_CANDIDATE_RULES=DEFINED
SOURCE_OBJECT_WITHDRAWAL_REPLACEMENT_GOVERNANCE_REQUIRED=true
SOURCE_OBJECT_REPLACEMENT_REQUIRES_NEW_IDENTITY=true
SOURCE_OBJECT_REPLACEMENT_REQUIRES_NEW_HASH=true
SOURCE_OBJECT_REPLACEMENT_IN_PLACE=false
SOURCE_OBJECT_REPLACEMENT_REQUIRES_DOWNSTREAM_INVALIDATION=true
SOURCE_OBJECT_WITHDRAWAL_REQUIRES_STATUS_RECORD=true
SOURCE_OBJECT_WITHDRAWAL_SILENT_DELETE_ALLOWED=false
```

If an object is withdrawn, the future status propagation must cover any source
cohort, source authority acceptance, row-lineage manifest, IDFL label snapshot,
split artifact, or evaluation artifact that depends on it. The affected gate
becomes blocked and accepted artifacts are not rewritten in place. This task
performs no invalidation because no Source 002 downstream formal artifact is
accepted or generated here.

## External-object binding and hash separation

Future custody may bind an external preserved object through an opaque,
non-sensitive `EXTERNAL_OBJECT_BINDING_HASH`. This workpaper does not issue
that binding.

```text
SOURCE_OBJECT_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
EXTERNAL_OBJECT_BINDING_HASH=NOT_ISSUED
CUSTODY_RECORD_HASH=NOT_ISSUED
```

The following identities must remain distinct:

```text
SOURCE_OBJECT_SHA256 != EXTERNAL_OBJECT_BINDING_HASH
EXTERNAL_OBJECT_BINDING_HASH != CUSTODY_RECORD_HASH
SOURCE_OBJECT_SHA256 != CUSTODY_RECORD_HASH
```

## Relationship to formal source authority

Completeness authority and custody record are necessary components of a future
Source 002 formal source-authority decision, but neither is the full source
attestation.

```text
SOURCE_002_FORMAL_ATTESTATION_STATUS=NOT_ISSUED
SOURCE_002_SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_002_SOURCE_COHORT_ACCEPTED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
```

The existing business-source attestation draft remains historical preparation
evidence. This task does not modify it, create a schema-valid attestation, or
upgrade business statements into formal authority.

## Independent downstream gates remain separate

### Missing-day semantics

The recorded business statement about no records is reused as context only. It
does not issue a formal zero-imputation rule.

```text
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
MISSING_DAY_NUMERIC_IMPUTATION_ALLOWED=false
FORMAL_MISSING_DAY_RULE_STATUS=PENDING
NO_RECORD_TO_ZERO_MAPPING_STATUS=BLOCKED_PENDING_SOURCE_COMPLETENESS_EVIDENCE
SOURCE_COMPLETENESS_ACCEPTANCE_IS_NOT_MISSING_DAY_ACCEPTANCE=true
```

Completeness evidence is a necessary input to the formal missing-day decision,
but even accepted completeness would not by itself authorize mapping an absent
row to numeric zero.

### July unmapped date

Completeness and season assignment are separate gates. This preparation does
not use a completeness declaration to resolve the July boundary.

```text
UNMAPPED_DATE_POLICY=PENDING
JULY_AUTOMATIC_SEASON_ASSIGNMENT=false
UNMAPPED_DATE_AUTO_ASSIGNMENT_ALLOWED=false
UNMAPPED_FIRST_DATE=2025-07-22
SOURCE_002_UNMAPPED_DATE_GATE=BLOCKED
```

The July date is not automatically assigned, deleted, or discarded here.

### Q2C

```text
Q2C_ACCEPTED=false
IDFL_DOES_NOT_SELECT_Q2C_TARGET=true
IDFL_TARGET_BINDING_STATUS=BLOCKED_PENDING_Q2C_ACCEPTANCE
```

This workpaper does not choose `OBSERVED_FARM_PICK_QUANTITY` or
`VERSIONED_Q2C_TRANSFORMATION`.

### Row lineage

Completeness and custody preparation do not materialize row-level lineage.

```text
SOURCE_002_ROW_LINEAGE_GATE=BLOCKED
SOURCE_ROW_LINEAGE_MANIFEST_HASH=NOT_ISSUED
SOURCE_OBJECT_BOUND_ROW_LINEAGE_MATERIALIZATION_THIS_TASK=false
```

Object identity and custody do not substitute for the future
source-object-bound row-lineage manifest.

## Current gate matrix

### A. Available for preparation

| Gate | Current status |
| --- | --- |
| `SOURCE_SYSTEM_IDENTITY` | `AVAILABLE` |
| `SOURCE_DATASET_IDENTITY` | `AVAILABLE` |
| `SOURCE_VERSION_IDENTITY` | `AVAILABLE` |
| `SOURCE_SNAPSHOT_REFERENCE` | `AVAILABLE` |
| `SOURCE_OBJECT_SHA256` | `AVAILABLE` |
| `SOURCE_OWNER_ROLE_BUSINESS_STATEMENT` | `AVAILABLE` |
| `SOURCE_SCHEMA_EVIDENCE` | `AVAILABLE` |

### B. Completeness preparation

| Gate | Current status |
| --- | --- |
| `SOURCE_COMPLETENESS_SEMANTIC_CONTRACT` | `DEFINED` |
| `SOURCE_COMPLETENESS_REQUIRED_FIELDS` | `DEFINED` |
| `SOURCE_COMPLETENESS_EVIDENCE_REQUEST` | `PREPARED` |
| `SOURCE_COMPLETE_THROUGH_BUSINESS_DATE` | `NOT_ISSUED` |
| `SOURCE_COMPLETENESS_POLICY_VERSION` | `NOT_ISSUED` |
| `SOURCE_COMPLETENESS_EVIDENCE_HASH` | `NOT_ISSUED` |
| `SOURCE_002_COMPLETENESS_GATE` | `BLOCKED` |

### C. Custody preparation

| Gate | Current status |
| --- | --- |
| `CUSTODY_REQUIRED_FIELDS` | `DEFINED` |
| `CUSTODY_EVIDENCE_REQUEST` | `PREPARED` |
| `WITHDRAWAL_REPLACEMENT_CANDIDATE_RULES` | `DEFINED` |
| `SOURCE_002_CUSTODY_RECORD_STATUS` | `NOT_ISSUED` |
| `SOURCE_002_CUSTODY_ACCEPTED` | `false` |
| `CUSTODY_RECORD_HASH` | `NOT_ISSUED` |

### D. Separate blockers

| Gate | Current status |
| --- | --- |
| `SOURCE_AUTHORITY` | `BLOCKED` |
| `SOURCE_COHORT` | `BLOCKED` |
| `ROW_LINEAGE` | `BLOCKED` |
| `Q2C` | `BLOCKED` |
| `MISSING_DAY_RULE` | `BLOCKED` |
| `UNMAPPED_DATE_POLICY` | `BLOCKED` |
| `MAPPING_POLICY` | `BLOCKED` |
| `INCLUSION_EXCLUSION` | `BLOCKED` |

## No-real-data and fail-closed governance boundary

```text
REAL_SOURCE_EXPORT_READ_THIS_TASK=false
REAL_BUSINESS_ROW_LEVEL_DATA_READ_THIS_TASK=false
SOURCE_002_RE_READ_THIS_TASK=false
EXTERNAL_SOURCE_SYSTEM_ACCESSED_THIS_TASK=false
REAL_BUSINESS_ROW_LEVEL_DATA_IMPORTED=false
DATABASE_WRITE=false
REAL_SNAPSHOT_CREATED=false
ROW_LEVEL_DERIVED_ARTIFACT_CREATED=false
FUTURE_REAL_DATA_ACCESS_AUTHORIZED=false

SOURCE_002_IDFL_V1_SOURCE_SPECIFIC_ELIGIBILITY=false
CURRENT_SOURCE_IDFL_V1_ELIGIBILITY=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
SOURCE_002_COMPLETENESS_GATE=BLOCKED
SOURCE_002_CUSTODY_ACCEPTED=false
SOURCE_002_ROW_LINEAGE_GATE=BLOCKED
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
UNMAPPED_DATE_POLICY=PENDING
S1_VISIBILITY_GATE_CLOSED=false
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
PHYSICALLY_ALIGNED_BACKTEST_ALLOWED=false
MODEL_QUALITY_CLAIM_ALLOWED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

## Preparation conclusion

This workpaper prepares the minimum business and governance evidence request
needed to issue, in a later reviewed decision, a completeness authority and a
custody record for the fixed Source 002 object. It does not answer the
unresolved business questions, issue either authority, or alter the existing
IDFL contract.

```text
SOURCE_002_COMPLETENESS_AND_CUSTODY_PREPARATION_READY=true
SOURCE_002_COMPLETENESS_AUTHORITY_ISSUED=false
SOURCE_002_CUSTODY_RECORD_ISSUED=false
SOURCE_002_SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_002_SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
```

The next action is to collect the six minimum completeness/custody business
and governance answers through an explicitly authorized channel, without
requesting source rows, real record IDs, real timestamps, storage paths, or
credentials.
