# Source 002 derived-package controlled rederivation readiness

## Purpose and authorization boundary

```text
TASK=SOURCE_002_DERIVED_VALUE_PACKAGE_CONTROLLED_REDERIVATION_READINESS
TASK_CLASS=DOCS_ONLY_CONTROLLED_REDERIVATION_READINESS
BASE_MAIN_SHA=db5d096ce94c4106bb3486cad740730820ddcf48
TARGET_GATE_ID=S1-SOURCE-AUTHORITY
RESULT=READY_WITH_EXECUTION_PRECONDITIONS
```

This task determines whether a later, separately authorized controlled rederivation may read the exact frozen Source002 object and recreate the missing derived-value content needed for the three concrete identity arrays. It does not itself read Source002, access row-level business data, reconstruct Source002 from repository evidence, create a derived package, bind final fields, issue a final attestation, accept Source Authority, mutate a canonical gate, enter S1 Remaining06, or start V0.3 S2.

```text
SOURCE_002_READ_AUTHORIZED=false
SOURCE_002_RAW_READ_AUTHORIZED=false
SOURCE_002_ROW_LEVEL_READ_AUTHORIZED=false
SOURCE_002_RECONSTRUCTION_AUTHORIZED=false
DERIVED_PACKAGE_REDERIVATION_AUTHORIZED=false
IDENTITY_ARRAY_VALUES_ACCESSED=false
FINAL_BINDING_AUTHORIZED=false
SOURCE_AUTHORITY_ACCEPTANCE_AUTHORIZED=false
CANONICAL_GATE_MUTATION_AUTHORIZED=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
```

## Frozen source identity

A future controlled execution may use only the already frozen Source002 object matching all of the following identities:

```text
SOURCE_SYSTEM=扫码称重系统
SOURCE_DATASET=田间商品果每日采摘净重汇总
SOURCE_VERSION=scan-weight-export:v0_3_s1:002
SOURCE_SNAPSHOT_REFERENCE=snapshot:v0_3_s1:002
SOURCE_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
SOURCE_BYTE_COUNT=28668416
SOURCE_ROW_COUNT=233171
OBSERVED_SCHEMA_VERSION=observed-source-schema-v1
SCHEMA_SHA256=919e63c4d3b4d00b304a045f63bfb050d4eb9abec3b0a318186b7ca2e7276867
SHEET_COUNT=4
RAW_SOURCE_IMMUTABLE=true
```

The governed custody record places Source002 on an enterprise server and assigns access administration to `IT_DEPARTMENT_AUTHORIZED_DATA_ACCESS_ADMINISTRATOR`. The private source locator is intentionally absent from Git. That absence is not permission to guess, reconstruct, or substitute a source object.

A future controlled execution must obtain the private locator out of band from the authorized access owner, open the source read-only, and verify the complete frozen identity before any row-level derivation begins.

```text
PRIVATE_LOCATOR_RESOLUTION_REQUIRED_AT_EXECUTION=true
PRIVATE_LOCATOR_IN_GIT_ALLOWED=false
SOURCE_OBJECT_READ_ONLY_REQUIRED=true
IDENTITY_VERIFICATION_BEFORE_DERIVATION_REQUIRED=true
ALTERNATE_SOURCE_SUBSTITUTION_ALLOWED=false
REPOSITORY_EVIDENCE_SOURCE_RECONSTRUCTION_ALLOWED=false
PRODUCTION_DATABASE_READ_ALLOWED=false
```

## Historical package is reference evidence only

The missing package remains unrecovered:

```text
HISTORICAL_PACKAGE_ID=source-002-attestation-derived-values-v1
HISTORICAL_PACKAGE_SHA256=5b362513ae4ffb9279ba978c64c566f75bc2cda12d10fb0f4bab1a5c445f3fe9
HISTORICAL_PACKAGE_LOCATOR_RECOVERED=false
HISTORICAL_PACKAGE_BYTES_RECOVERED=false
HISTORICAL_PACKAGE_COMMITTED_TO_GIT=false
FULL_IDENTITY_ARRAYS_IN_HISTORICAL_PACKAGE_ONLY=true
RAW_ROWS_IN_HISTORICAL_PACKAGE=false
```

Because the original package bytes and locator are unavailable, a later task must not claim that newly created bytes are the recovered v1 package merely because their logical values match. The historical v1 ID and SHA-256 remain immutable reference evidence.

## Deterministic content parity contract

The later execution may derive only the previously governed Source002 scope/date content. The canonical S1 scope is the mapped `2025~2026` season. The two rows dated `2025-07-22` remain outside the canonical S1 cohort.

```text
CANONICAL_SCOPE_ROW_COUNT=233169
UNMAPPED_JULY_DATE=2025-07-22
UNMAPPED_JULY_ROW_COUNT=2
UNMAPPED_JULY_ROWS_CANONICAL_INCLUDED=false
```

Identity arrays must be derived from the approved raw identity columns of the canonical rows only. No aliasing, spelling correction, identity merging, null replacement, or silent reassignment is permitted. Values must use deterministic Unicode lexical sort and the existing array hash rule: SHA-256 of UTF-8 compact canonical JSON with `ensure_ascii=false`.

Expected content identities are:

```text
FARM_COUNT=84
FARMS_ARRAY_SHA256=2daf09d38efb41bada5a1b493974c569e64b63abdd322e5ab4dacc206edb0381
SUBFARM_COUNT=192
SUBFARMS_ARRAY_SHA256=921a56006d1a75f683c62c8a930e913fc39cabf2dcffec88b16549ed95945e13
VARIETY_COUNT=20
VARIETIES_ARRAY_SHA256=fe6274775796193318fa3ad504ba8cc4e2196b8c58dd8f795cec80cc22c26209

coverage_scope.business_date_start=2025-08-05
coverage_scope.business_date_end=2026-04-16
coverage_summary.first_harvest_business_date=2025-08-05
coverage_summary.last_harvest_business_date=2026-04-16
```

`coverage_summary.missing_day_count` and `coverage_summary.missing_data_proportion` remain unresolved under current authority. The controlled rederivation must not manufacture numeric values for them and must not infer a source-completeness watermark.

## Replacement package plan

The recommended execution output is a new controlled replacement package, not a false recovery claim for v1:

```text
CANDIDATE_REDERIVED_PACKAGE_ID=source-002-attestation-derived-values-v2-rederived
CANDIDATE_REDERIVED_PACKAGE_ID_STATUS=PROPOSED_FOR_SEPARATELY_AUTHORIZED_EXECUTION
CANDIDATE_REDERIVED_PACKAGE_SHA256=TO_BE_COMPUTED_AT_EXECUTION
PACKAGE_HASH_RULE=SHA-256 of UTF-8 recursively sorted compact canonical JSON excluding the package_sha256 self-field
RAW_ROWS_IN_PACKAGE=false
FULL_IDENTITY_ARRAYS_IN_GIT=false
```

The actual replacement package hash must be computed from the newly created package during execution. The historical v1 SHA-256 must not be copied onto different bytes.

To prevent another locator-loss cycle, successful execution must complete a durable external-custody handoff before the task can report success. The external package may contain the concrete arrays but no raw rows. Git may record package ID, package SHA-256, array counts/hashes, validation state, and a non-sensitive opaque custody reference; it must not record a plaintext private path, URL, credential, or the full identity arrays.

```text
DURABLE_EXTERNAL_LOCATOR_REQUIRED=true
EXTERNAL_CUSTODY_HANDOFF_REQUIRED=true
OPAQUE_NON_SENSITIVE_CUSTODY_REFERENCE_IN_GIT_REQUIRED=true
PLAINTEXT_PRIVATE_LOCATOR_IN_GIT_ALLOWED=false
```

## Mandatory stop conditions

A future execution must stop fail-closed if any of the following occurs:

- the private Source002 locator cannot be resolved by the authorized access owner;
- source SHA-256, byte count, row count, schema SHA-256, or sheet count differs from the frozen identity;
- the canonical scope no longer reproduces the governed `233169` rows and July exclusion;
- any farm/subfarm/variety count or array SHA-256 differs from the governed identity;
- any of the four date fields differs from the governed value;
- producing parity would require aliasing, spelling correction, identity merging, null replacement, or silent reassignment;
- the replacement package cannot be handed off to durable controlled external custody.

No mismatch may be repaired by substituting a different source, using repository counts/hashes as concrete arrays, reconstructing Source002, or silently changing business rules.

## Readiness decision

The governance inputs are sufficient to define a safe separately authorized execution: exact source identity, read-only custody rules, deterministic array derivation, expected content identities, four governed date values, unresolved missing-day semantics, package-hash rules, and fail-closed stop conditions are all available.

The readiness result is therefore conditional on runtime source access, not evidence that the source is currently accessible:

```text
CONTROLLED_REDERIVATION_READINESS=READY_WITH_EXECUTION_PRECONDITIONS
GOVERNANCE_CONTRACT_COMPLETE_ENOUGH_FOR_SEPARATE_EXECUTION_AUTHORIZATION=true
SOURCE_ACCESS_AVAILABLE_PROVEN_NOW=false
SOURCE_ACCESS_MUST_BE_RESOLVED_AT_EXECUTION=true
ACTUAL_REDERIVATION_PERFORMED=false
PACKAGE_BYTES_CREATED=false
FIELD_STATE_CHANGED=false
```

The existing business state remains unchanged:

```text
READY_FOR_FINAL_FIELD_BINDING_COUNT=4
BLOCKED_FINAL_FIELD_BINDING_COUNT=3
ALL_7_FIELDS_READY=false
SOURCE_AUTHORITY_ACCEPTED=false
CURRENT_CANONICAL_GATE_PASS_COUNT=0
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=17
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
```

## Next gate and review boundary

Only after this readiness PR passes exact-head CI, exact-head independent review, separately authorized Ready, and separately authorized Merge may the next business gate be considered:

```text
NEXT_BUSINESS_GATE=SOURCE_002_DERIVED_VALUE_PACKAGE_CONTROLLED_REDERIVATION
NEXT_BUSINESS_GATE_AUTHORIZED=false
SOURCE_002_READ_AUTHORIZED=false
DERIVED_PACKAGE_REDERIVATION_AUTHORIZED=false
FINAL_BINDING_AUTHORIZED=false

EXACT_HEAD_CI_REQUIRED=true
EXACT_HEAD_INDEPENDENT_REVIEW_REQUIRED=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```
