# Source 002 missing coverage formula policy decision

## 1. Decision scope

```text
TASK=V0_3_S1_SOURCE_002_MISSING_COVERAGE_FORMULA_POLICY_DECISION
TASK_CLASS=DOCS_ONLY_BUSINESS_OWNER_GOVERNANCE_DECISION
BASE_SHA=add07592b4eab0a247d5a8c8887fdd37f0843e19
BUSINESS_FORMULA_POLICY_DECISION_AUTHORIZED=true
```

This decision records the BUSINESS_OWNER acceptance of the exact formula-policy package proposed after the authority model was frozen in PR #207.

It does not read Source 002, issue source-owner expected-recording evidence, issue a completeness declaration, calculate either schema value, issue a final Source Owner Attestation, mutate any canonical gate, authorize S1 Remaining06, or authorize V0.3 S2.

## 2. Authority basis

The frozen authority model assigns:

```text
FORMULA_POLICY_AUTHORITY_ROLE=BUSINESS_OWNER
SOURCE_EVIDENCE_AUTHORITY_ROLE=农场数据负责人
JOINT_CONCURRENCE_REQUIRED_FOR_COMPUTABLE_FORMULA=true
```

The BUSINESS_OWNER therefore may accept the business semantics of the formula, but may not invent Source 002 completeness or expected-recording facts.

The source-evidence authority remains responsible for governed evidence identifying which canonical group-days were expected to produce a Source 002 record.

## 3. Accepted formula policy

```text
SELECTED_CANDIDATE_OPTION=AUTHORITY_DECLARED_EXPECTED_HARVEST_DAY
SELECTED_CANDIDATE_STATUS=ACCEPTED_AS_BUSINESS_FORMULA_POLICY

EXPECTED_DATE_UNIVERSE_POLICY=AUTHORITY_DECLARED_EXPECTED_RECORDING_DAYS
EXPECTED_CANONICAL_GROUP_UNIVERSE_POLICY=AUTHORITY_DECLARED_CANONICAL_GROUP_DAYS
MISSING_DAY_SEMANTIC_UNIT=AUTHORITY_DECLARED_GROUP_DAY
```

A canonical group-day enters the denominator only if the source-evidence authority independently declares that a governed Source 002 record was expected for that canonical group-day.

Row absence alone does not create an expected day and does not prove missing data.

## 4. Accepted formulas

```text
MISSING_DAY_COUNT_FORMULA=
count(authority-declared expected canonical group-days with no governed in-scope Source 002 row)

MISSING_DATA_PROPORTION_NUMERATOR=missing_expected_group_days
MISSING_DATA_PROPORTION_DENOMINATOR=total_authority_declared_expected_group_days

MISSING_DATA_PROPORTION_FORMULA=
missing_expected_group_days / total_authority_declared_expected_group_days
```

These formulas are accepted as business policy only. They are not executable until the required source-owner expected-recording universe evidence exists.

## 5. July denominator policy

The previously governed Source 002 boundary remains:

```text
UNMAPPED_DATE=2025-07-22
UNMAPPED_ROW_COUNT=2
RAW_ROWS_RETAINED=true
CANONICAL_S1_COHORT_INCLUDED=false
AUTOMATIC_SEASON_ASSIGNMENT=false
```

The BUSINESS_OWNER now accepts:

```text
JULY_DENOMINATOR_TREATMENT=EXCLUDE_2025_07_22_FROM_CANONICAL_S1_DENOMINATOR
```

This does not silently assign the two July rows to a season and does not remove them from the immutable raw source object.

## 6. Zero-denominator policy

Accepted:

```text
ZERO_DENOMINATOR_POLICY=BLOCK_AND_UNRESOLVED
```

If the authority-declared expected group-day universe is empty, no numeric `missing_data_proportion` is emitted.

The result remains unresolved rather than coercing the proportion to zero or inventing a not-applicable numeric identity.

## 7. Decimal identity

Accepted:

```text
DECIMAL_PRECISION_POLICY=FIXED_8_DECIMAL_HALF_EVEN
DECIMAL_SCALE=8
ROUNDING_MODE=ROUND_HALF_EVEN
OUTPUT_REPRESENTATION=DECIMAL_STRING
BINARY_FLOATING_POINT_GOVERNANCE_IDENTITY_ALLOWED=false
```

When a future authorized calculation has a non-zero governed denominator, the exact integer numerator/denominator ratio is quantized to eight decimal places using half-even rounding and serialized as a decimal string.

No such calculation is performed in this task.

## 8. UNKNOWN_NOT_ZERO boundary

The existing semantic remains unchanged:

```text
CURRENT_MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
MISSING_DAY_NUMERIC_IMPUTATION_ALLOWED=false
```

Mandatory distinctions remain:

```text
NO_ROW != PROVEN_MISSING_DATA
NO_ROW != ZERO_HARVEST
NO_ROW != PROVEN_NO_HARVEST
NO_ROW != SOURCE_COMPLETENESS_FAILURE
```

The accepted policy deliberately requires an independent expected-recording declaration before row absence can contribute to the missingness numerator.

## 9. Source-owner dependency

The policy is now accepted, but the joint-concurrence condition is not yet satisfied:

```text
SOURCE_OWNER_EXPECTED_RECORDING_UNIVERSE_EVIDENCE_REQUIRED=true
SOURCE_OWNER_EXPECTED_RECORDING_UNIVERSE_EVIDENCE_ISSUED=false
SOURCE_COMPLETENESS_DECLARATION_ISSUED=false
SOURCE_COMPLETE_THROUGH_BUSINESS_DATE=NOT_ISSUED
JOINT_CONCURRENCE_SATISFIED=false
JOINT_COMPUTABLE_FORMULA_READY=false
BLOCKING_REASON=SOURCE_OWNER_EXPECTED_RECORDING_UNIVERSE_EVIDENCE_NOT_ISSUED
```

The BUSINESS_OWNER decision does not authorize ChatGPT, Codex, repository code, or any other actor to manufacture the source-owner declaration.

## 10. Computation state

```text
BUSINESS_FORMULA_POLICY_DECISION_ISSUED=true
BUSINESS_FORMULA_POLICY_ACCEPTED=true
SELECTED_OPTION=AUTHORITY_DECLARED_EXPECTED_HARVEST_DAY
FORMULA_POLICY_READY_FOR_SOURCE_EVIDENCE_BINDING=true

MISSING_DAY_COUNT=UNRESOLVED
MISSING_DATA_PROPORTION=UNRESOLVED

DESCRIPTIVE_CALENDAR_GAP_COUNT=31455
DESCRIPTIVE_CALENDAR_GAP_COUNT_IS_FORMAL_MISSING_DAY_COUNT=false

COVERAGE_SCOPE_START=2025-08-05
COVERAGE_SCOPE_END=2026-04-16
COVERAGE_END_IS_COMPLETENESS_WATERMARK=false
SOURCE_COMPLETE_THROUGH_BUSINESS_DATE=NOT_ISSUED
```

`31455` is not promoted to the formal missing-day result and `2026-04-16` is not promoted to a completeness watermark.

## 11. Governance state

```text
SOURCE_OWNER_EXPECTED_RECORDING_EVIDENCE_ISSUED=false
SOURCE_COMPLETENESS_DECLARATION_ISSUED=false
SOURCE_OWNER_ATTESTATION_ISSUED=false
FINAL_ATTESTATION_ISSUANCE_READY=false
SOURCE_AUTHORITY_ACCEPTED=false

CURRENT_CANONICAL_GATE_PASS_COUNT=0
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=17
CANONICAL_GATE_STATUS_CHANGED=false
CANONICAL_ACCEPTANCE_RECORD_CHANGED=false

V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

Acceptance of this formula policy is not acceptance of `S1-SOURCE-AUTHORITY` and does not close any canonical gate by itself.

## 12. Safety boundary

```text
SOURCE_002_READ=false
SOURCE_002_RAW_READ=false
SOURCE_002_ROW_LEVEL_READ=false
REAL_BUSINESS_DATA_READ=false
PRODUCTION_DATABASE_READ=false
PRODUCTION_DATABASE_WRITE=false
SOURCE_002_MUTATION=false

MISSING_DAY_CALCULATION_PERFORMED=false
MISSING_DATA_PROPORTION_CALCULATION_PERFORMED=false

BACKTEST_EXECUTED=false
MODEL_TRAINING_EXECUTED=false
METRIC_EXECUTION_PERFORMED=false
PRODUCTION_CODE_CHANGED=false
TEST_CODE_CHANGED=false
DATABASE_SCHEMA_CHANGED=false
MIGRATION_CREATED=false
MODEL_CHANGED=false
```

## 13. Decision provenance and hash

```text
DECISION_AUTHORITY_ROLE=BUSINESS_OWNER
DECISION_EVENT=EXPLICIT_BUSINESS_OWNER_FORMULA_POLICY_AUTHORIZATION_IN_GOVERNANCE_SESSION
DECISION_AT=2026-08-13T08:02:00+08:00
DECISION_TIMEZONE_OFFSET=+08:00
PERSONAL_IDENTITY_RECORDED=false

DECISION_HASH_ALGORITHM=SHA256
DECISION_HASH_CANONICALIZATION=UTF8_JSON_SORT_KEYS_RECURSIVELY_COMPACT_SEPARATORS_ENSURE_ASCII_FALSE
DECISION_HASH_SCOPE=FULL_DECISION_RECORD_EXCLUDING_FIELD_decision_record_sha256
DECISION_RECORD_SHA256=74b6aa7c94581407a555e89127c0fd3a2a081241846489f4f8f671ff74ae35a9
```

## 14. Stop boundary

The next required governance input is:

```text
NEXT_GATE=SOURCE_OWNER_EXPECTED_RECORDING_UNIVERSE_EVIDENCE
REQUIRED_ROLE=农场数据负责人
NEXT_GATE_AUTHORIZED=false
```

This task stops after the formal decision record Draft PR and exact-head CI.

It does not request or issue that evidence, calculate the two fields, issue a final attestation, mutate canonical acceptance, start Remaining06, or start S2.

```text
INDEPENDENT_REVIEW_REQUIRED=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```
