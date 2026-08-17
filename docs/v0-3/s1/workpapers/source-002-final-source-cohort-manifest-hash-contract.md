# Source002 Final Source Cohort Manifest Hash Contract

TASK_ID=SOURCE_002_FINAL_SOURCE_COHORT_MANIFEST_HASH_CONTRACT_FORMALIZATION
TASK_AUTHORIZED=true
ARTIFACT_ID=V0_3_S1_SOURCE_002_FINAL_SOURCE_COHORT_MANIFEST_HASH_CONTRACT
ARTIFACT_VERSION=source-002-final-source-cohort-manifest-hash-contract-v1
ARTIFACT_STATUS=FORMALIZED_FOR_INDEPENDENT_REVIEW
BASE_MAIN_SHA=caef6448593c35bceb6c9beb7fc824a5db92a659

## Contract identity

HASH_CONTRACT_VERSION=source-002-final-source-cohort-manifest-hash-contract-v1
HASH_ALGORITHM=SHA-256
MANIFEST_HASH_SCOPE=FULL_ISSUED_SCHEMA_VALID_FINAL_SOURCE_COHORT_MANIFEST_EXCLUDING_ONLY_manifest_hash
MANIFEST_HASH_FIELD_EXCLUDED_FROM_ITS_OWN_HASH_INPUT=true
ONLY_EXCLUDED_SCHEMA_FIELD=manifest_hash
MANIFEST_HASH_PRESENT_IN_FINAL_OBJECT=true
manifest_version_INCLUDED=true
attestation_version_INCLUDED=true
attestation_effective_at_INCLUDED=true
attestation_status_INCLUDED=true
coverage_scope_concrete_arrays_INCLUDED=true
OPTIONAL_SCHEMA_FIELDS_IF_PRESENT_INCLUDED=true

The final Source Cohort Manifest is first constructed as a complete object that
passes `docs/v0-3/s1/schemas/source-cohort-manifest.schema.json`. The final
object contains `manifest_hash`. The hash input is a copy of that object with
only the top-level `manifest_hash` field removed. Every other field actually
present in the issued schema-valid object participates in the hash, including
the governed seasons, farms, subfarms, varieties, and known-scope-boundary
arrays in their original governed order.

This contract formalizes serialization only. It does not create a final Source
Cohort Manifest, accept Source Cohort, or change any canonical gate.

## Canonicalization

MANIFEST_HASH_CANONICALIZATION=UTF8_JSON_SORT_KEYS_RECURSIVELY_COMPACT_SEPARATORS_ENSURE_ASCII_FALSE
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
manifest_hash = hashlib.sha256(canonical_bytes).hexdigest()
```

Object keys are sorted recursively. Governed array order is preserved exactly;
arrays are neither sorted nor deduplicated. Strings are not trimmed,
case-folded, or Unicode-normalized. Decimal values remain canonical decimal
strings and are never converted to floating point. The output is lowercase
hexadecimal with 64 characters. No UTF-8 BOM or trailing newline participates
in canonical bytes.

## Schema reconciliation

SCHEMA_PATH=docs/v0-3/s1/schemas/source-cohort-manifest.schema.json
SCHEMA_REQUIRED_TOP_LEVEL_FIELD_COUNT=36
MANIFEST_HASH_REQUIRED=true
MANIFEST_HASH_SCHEMA_CONSTRAINT=sha256_lowercase_hex_64
FULL_SCHEMA_VALID_MANIFEST_REQUIRED_BEFORE_HASHING=true
COVERAGE_SCOPE_CONCRETE_ARRAYS_INCLUDED=true
OPTIONAL_SCHEMA_FIELDS_IF_PRESENT_INCLUDED=true
FINAL_SOURCE_COHORT_MANIFEST_CREATED=false
SOURCE_COHORT_ACCEPTED=false

The contract does not place counts or array hashes in schema array fields and
does not commit a final manifest. Concrete scope arrays, when present in a
future issued manifest, participate as governed values in their existing order.

## Existing contract reconciliation

SOURCE_AUTHORITY_CONTRACT_PATH=docs/v0-3/s1/source-authority-and-cohort-manifest.md
SOURCE_AUTHORITY_HASH_ALGORITHM=SHA-256
SOURCE_AUTHORITY_CANONICALIZATION=VERSIONED_CANONICAL_JSON_WITH_DECIMAL_STRINGS
SOURCE_AUTHORITY_MANIFEST_HASH_PRINCIPLE_PRESERVED=true
ALIGNMENT_WITH_EXISTING_SOURCE002_DETERMINISTIC_HASH_PRACTICE=true

The existing Source Authority contract's SHA-256 and versioned canonical JSON
principles remain unchanged. This source-002-specific contract supplies the
replayable serialization details and the only-field self-reference exclusion
for a future final Source Cohort Manifest.

## Contract hash payload and replay

The contract hash is separate from any future `manifest_hash`.

```json
{"allow_nan":false,"array_deduplication":false,"array_order_policy":"PRESERVE_GOVERNED_SOURCE_COHORT_MANIFEST_ARRAY_ORDER","array_sorting":false,"canonicalization":"UTF8_JSON_SORT_KEYS_RECURSIVELY_COMPACT_SEPARATORS_ENSURE_ASCII_FALSE","case_folding":false,"compact_separator_colon":":","compact_separator_comma":",","decimal_policy":"DECIMAL_VALUES_REMAIN_CANONICAL_DECIMAL_STRINGS","decimal_string_to_float_conversion":false,"ensure_ascii":false,"excluded_fields":["manifest_hash"],"hash_algorithm":"SHA-256","hash_contract_version":"source-002-final-source-cohort-manifest-hash-contract-v1","hash_output_encoding":"LOWERCASE_HEX","hash_output_length":64,"manifest_hash_field_excluded_from_its_own_hash_input":true,"manifest_hash_scope":"FULL_ISSUED_SCHEMA_VALID_FINAL_SOURCE_COHORT_MANIFEST_EXCLUDING_ONLY_manifest_hash","object_key_order":"SORT_KEYS_RECURSIVELY","string_trimming":false,"trailing_newline":false,"unicode_normalization":false,"utf8_bom":false,"utf8_encoding":true}
```

FINAL_SOURCE_COHORT_MANIFEST_HASH_CONTRACT_SHA256=343f12c8bacdc5879917a0a53bb4d9fd9e3772091fe7958b2341e02455672116
FINAL_SOURCE_COHORT_MANIFEST_HASH_CONTRACT_SHA256_REPLAY=PASS
HASH_CONTRACT_SHA_IS_MANIFEST_HASH=false

## Current governance state

CURRENT_MAIN_SOURCE_COHORT_MANIFEST_HASH_CONTRACT_ISSUED=false
FINAL_SOURCE_COHORT_MANIFEST_CREATED=false
SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
CURRENT_CANONICAL_GATE_PASS_COUNT=3
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=14
CANONICAL_GATE_STATUS_CHANGED=false
CANONICAL_ACCEPTANCE_RECORD_CHANGED=false

## Authorization boundary

SOURCE_COHORT_MANIFEST_HASH_CONTRACT_FORMALIZATION_AUTHORIZED=true
FINAL_SOURCE_COHORT_MANIFEST_ISSUANCE_AUTHORIZED=false
INDEPENDENT_REVIEW=false
READY=false
MERGE=false
SOURCE_AUTHORITY_ACCEPTANCE=false
SOURCE_COHORT_ACCEPTANCE=false
CANONICAL_GATE_MUTATION=false
S1_REMAINING_06=false
V0_3_S2=false
INDEPENDENT_REVIEW_PERFORMED=false
READY_PERFORMED=false
MERGE_PERFORMED=false
NO_STEP_IMPLIES_THE_NEXT=true

## Validation evidence

JSON_SYNTAX=PASS
JSON_MARKDOWN_PARITY=PASS
HASH_SCOPE_SELF_REFERENCE_EXCLUSION=PASS
CANONICALIZATION_UNAMBIGUOUS=PASS
ARRAY_ORDER_POLICY_UNAMBIGUOUS=PASS
DECIMAL_STRING_POLICY_UNAMBIGUOUS=PASS
UNICODE_POLICY_UNAMBIGUOUS=PASS
CONTRACT_HASH_REPLAY=PASS
NO_FINAL_SOURCE_COHORT_MANIFEST_ISSUANCE=PASS
NO_CANONICAL_GATE_MUTATION=PASS
CHANGED_FILE_SCOPE=PASS
GIT_DIFF_CHECK=PASS
