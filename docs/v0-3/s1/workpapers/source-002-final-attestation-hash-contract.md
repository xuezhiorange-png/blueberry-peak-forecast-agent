# Source002 Final Attestation Hash Contract

TASK_ID=FINAL_ATTESTATION_HASH_CONTRACT_FORMALIZATION
TASK_AUTHORIZED=true
ARTIFACT_ID=V0_3_S1_SOURCE_002_FINAL_ATTESTATION_HASH_CONTRACT
ARTIFACT_VERSION=source-002-final-attestation-hash-contract-v1
ARTIFACT_STATUS=FORMALIZED_FOR_INDEPENDENT_REVIEW
BASE_MAIN_SHA=3f533cea706c3253fbf1b5d2963dc4e6afe72667
HASH_CONTRACT_AUTHORITY_EVENT=EXPLICIT_GOVERNANCE_AUTHORIZATION
HASH_CONTRACT_AUTHORITY_AT=2026-08-16T22:08:00+08:00

## Contract identity

HASH_CONTRACT_VERSION=source-002-final-attestation-hash-contract-v1
HASH_ALGORITHM=SHA-256
ATTESTATION_HASH_SCOPE=FULL_ISSUED_SCHEMA_VALID_FINAL_ATTESTATION_OBJECT_EXCLUDING_ONLY_attestation_hash
ATTESTATION_HASH_FIELD_EXCLUDED_FROM_ITS_OWN_HASH_INPUT=true
ONLY_EXCLUDED_SCHEMA_FIELD=attestation_hash
attestation_version_INCLUDED=true
attestation_effective_at_INCLUDED=true
attestation_status_INCLUDED=true
coverage_scope_concrete_arrays_INCLUDED=true
OPTIONAL_SCHEMA_FIELDS_IF_PRESENT_INCLUDED=true

The final object is first constructed as a complete schema-valid attestation.
The top-level `attestation_hash` field remains present in that final object. The
hash input is a copy of that object with only the top-level
`attestation_hash` field removed. Every other field actually present in the
issued object participates in the hash, including optional schema fields when
they are present.

## Canonicalization

ATTESTATION_HASH_CANONICALIZATION=UTF8_JSON_SORT_KEYS_RECURSIVELY_COMPACT_SEPARATORS_ENSURE_ASCII_FALSE
UTF8_ENCODING=true
UTF8_BOM=false
TRAILING_NEWLINE=false
OBJECT_KEYS_SORTED_RECURSIVELY=true
ARRAY_ORDER_PRESERVED=true
ARRAY_SORTING=false
ARRAY_DEDUPLICATION=false
COMPACT_SEPARATOR_COMMA=,
COMPACT_SEPARATOR_COLON=:
ENSURE_ASCII=false
ALLOW_NAN=false
STRING_TRIMMING=false
CASE_FOLDING=false
UNICODE_NORMALIZATION=false
DECIMAL_VALUES_REMAIN_CANONICAL_DECIMAL_STRINGS=true
DECIMAL_STRING_TO_FLOAT_CONVERSION=false
HASH_OUTPUT_ENCODING=LOWERCASE_HEX
HASH_OUTPUT_LENGTH=64

Equivalent implementation:

```python
canonical_bytes = json.dumps(
    hash_input,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
).encode("utf-8")
attestation_hash = hashlib.sha256(canonical_bytes).hexdigest()
```

Object keys are sorted recursively. Governed array order is preserved exactly;
arrays are neither sorted nor deduplicated. Strings are not trimmed, case-folded,
or Unicode-normalized. Decimal values remain canonical decimal strings and are
never converted to floating point. The output is lowercase hexadecimal with 64
characters.

## Existing contract reconciliation

The current Source Authority contract at
`docs/v0-3/s1/source-authority-and-cohort-manifest.md` already fixes
`HASH_ALGORITHM=SHA-256`,
`CANONICALIZATION=VERSIONED_CANONICAL_JSON_WITH_DECIMAL_STRINGS`, and coverage
of the canonical attestation object while excluding transport metadata and
personal data. Q2F also fixes UTF-8 encoding, sorted JSON keys, RFC3339
timestamps, and SHA-256. This artifact supplies the source-002-specific,
replayable serialization details and the only-field self-reference exclusion;
it does not change the existing hashing principle.

SOURCE_AUTHORITY_CONTRACT_PATH=docs/v0-3/s1/source-authority-and-cohort-manifest.md
SOURCE_AUTHORITY_HASH_ALGORITHM=SHA-256
SOURCE_AUTHORITY_CANONICALIZATION=VERSIONED_CANONICAL_JSON_WITH_DECIMAL_STRINGS
SOURCE_AUTHORITY_HASH_SUBJECT=CANONICAL_ATTESTATION_OBJECT_EXCLUDING_TRANSPORT_METADATA_AND_PERSONAL_DATA
Q2F_CONTRACT_PATH=docs/forecast-quality/q2f-attestation-intake-template.md
Q2F_CANONICAL_ENCODING=UTF-8
Q2F_CANONICAL_JSON_KEYS=SORTED
Q2F_HASH_ALGORITHM=SHA-256
ALIGNMENT_WITH_EXISTING_SOURCE002_DETERMINISTIC_HASH_PRACTICE=true

## Contract hash payload and replay

The contract hash is separate from any future final attestation hash.

```json
{"allow_nan":false,"array_deduplication":false,"array_order_policy":"PRESERVE_GOVERNED_PACKAGE_ORDER","array_sorting":false,"attestation_hash_scope":"FULL_ISSUED_SCHEMA_VALID_FINAL_ATTESTATION_OBJECT_EXCLUDING_ONLY_attestation_hash","canonicalization":"UTF8_JSON_SORT_KEYS_RECURSIVELY_COMPACT_SEPARATORS_ENSURE_ASCII_FALSE","case_folding":false,"compact_separator_colon":":","compact_separator_comma":",","decimal_policy":"DECIMAL_VALUES_REMAIN_CANONICAL_DECIMAL_STRINGS","decimal_string_to_float_conversion":false,"ensure_ascii":false,"excluded_fields":["attestation_hash"],"hash_algorithm":"SHA-256","hash_contract_version":"source-002-final-attestation-hash-contract-v1","hash_output_encoding":"LOWERCASE_HEX","hash_output_length":64,"object_key_order":"SORT_KEYS_RECURSIVELY","string_trimming":false,"trailing_newline":false,"unicode_normalization":false,"utf8_bom":false,"utf8_encoding":true}
```

FINAL_ATTESTATION_HASH_CONTRACT_SHA256=c17e94b4dea7a833d03a884de3e7953db034e70fbba69856c508827c07470a39
FINAL_ATTESTATION_HASH_CONTRACT_SHA256_REPLAY=PASS
HASH_CONTRACT_SHA_IS_ATTESTATION_HASH=false

## Current state and boundary

PREVIOUS_BLOCKER=CONCRETE_SCOPE_ARRAY_VALUES_UNAVAILABLE_FOR_SCHEMA_VALID_FINAL_ATTESTATION
PREVIOUS_BLOCKER_RESOLVED=true
CURRENT_BLOCKER=FINAL_ATTESTATION_HASH_CONTRACT_UNRESOLVED
CURRENT_BLOCKER_RESOLVED_BY_THIS_ARTIFACT=true
CURRENT_MAIN_FINAL_ATTESTATION_HASH_CONTRACT_ISSUED=false
FINAL_ATTESTATION_ISSUANCE_READY_AFTER_HASH_CONTRACT_MERGE=true
PROSPECTIVE_OUTCOME_REQUIRES_THIS_PR_TO_MERGE=true

FINAL_SOURCE_OWNER_CONFIRMATION_OCCURRED=true
FINAL_ATTESTATION_CONSTRUCTED=false
FINAL_ATTESTATION_ISSUED=false
ATTESTATION_HASH=NOT_ISSUED
SOURCE_OWNER_ATTESTATION_INDEPENDENTLY_ACCEPTED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
CURRENT_CANONICAL_GATE_PASS_COUNT=2
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=15
CANONICAL_GATE_STATUS_CHANGED=false
CANONICAL_ACCEPTANCE_RECORD_CHANGED=false

## Validation evidence

JSON_SYNTAX=PASS
JSON_MARKDOWN_PARITY=PASS
HASH_SCOPE_SELF_REFERENCE_EXCLUSION=PASS
CANONICALIZATION_UNAMBIGUOUS=PASS
ARRAY_ORDER_POLICY_UNAMBIGUOUS=PASS
DECIMAL_STRING_POLICY_UNAMBIGUOUS=PASS
UNICODE_POLICY_UNAMBIGUOUS=PASS
CONTRACT_HASH_REPLAY=PASS
NO_FINAL_ATTESTATION_ISSUANCE=PASS
NO_CANONICAL_GATE_MUTATION=PASS
CHANGED_FILE_SCOPE=PASS
GIT_DIFF_CHECK=PASS

## Authorization boundary

FINAL_SOURCE_OWNER_ATTESTATION_ISSUANCE=false
INDEPENDENT_REVIEW=false
READY=false
MERGE=false
SOURCE_AUTHORITY_ACCEPTANCE=false
SOURCE_COHORT_ACCEPTANCE=false
S1_REMAINING_06=false
V0_3_S2=false
INDEPENDENT_REVIEW_PERFORMED=false
READY_PERFORMED=false
MERGE_PERFORMED=false
NO_STEP_IMPLIES_THE_NEXT=true
