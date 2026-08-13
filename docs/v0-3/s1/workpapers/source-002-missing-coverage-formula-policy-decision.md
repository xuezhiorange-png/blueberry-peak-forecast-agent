# Source 002 missing coverage formula policy decision — corrected business semantics

## 1. Correction scope

```text
TASK=V0_3_S1_SOURCE_002_MISSING_COVERAGE_FORMULA_POLICY_DECISION_CORRECTION
TASK_CLASS=DOCS_ONLY_BUSINESS_OWNER_GOVERNANCE_DECISION_CORRECTION
BASE_SHA=add07592b4eab0a247d5a8c8887fdd37f0843e19
BUSINESS_FORMULA_POLICY_CORRECTION_AUTHORIZED=true
```

This correction supersedes the unmerged v1 policy in PR #208.

The BUSINESS_OWNER clarified the governing business fact:

```text
NO_SOURCE_ROW=NO_HARVEST
NO_SOURCE_ROW_IS_MISSING_DATA=false
```

Therefore the prior `AUTHORITY_DECLARED_EXPECTED_HARVEST_DAY` policy is not the correct business interpretation and is superseded before merge.

This correction does not read Source 002, calculate either schema field, issue source-loss evidence, issue a completeness declaration, issue a final Source Owner Attestation, mutate canonical acceptance, authorize S1 Remaining06, or authorize V0.3 S2.

## 2. Corrected business semantics

Accepted:

```text
ROW_ABSENCE_SEMANTICS=NO_HARVEST
ROW_ABSENCE_IS_MISSING_DATA=false
ROW_ABSENCE_REQUIRES_EXPECTED_RECORDING_DECLARATION=false
EXPECTED_RECORDING_UNIVERSE_REQUIRED=false
EXPECTED_HARVEST_DAY_LIST_REQUIRED=false
```

A missing Source 002 row is interpreted as no harvest activity for that canonical entity/date.

It is not treated as:

```text
MISSING_DATA
ZERO_KG_RECORDED_ROW
SOURCE_COMPLETENESS_FAILURE
EXPECTED_BUT_UNRECORDED_HARVEST
```

No numeric 0 kg row is fabricated. “No harvest” is a business-state interpretation of row absence, not an inserted measurement.

## 3. What counts as missing data

Missing data is limited to explicit, governed evidence of Source 002 data loss.

Accepted policy:

```text
MISSING_DAY_POLICY=EXPLICIT_SOURCE_DATA_LOSS_ONLY
MISSING_DAY_SEMANTIC_UNIT=SOURCE_WIDE_CANONICAL_CALENDAR_DAY
```

A canonical S1 calendar day contributes to `missing_day_count` only when governed evidence explicitly proves Source 002 data loss for that day.

Examples of qualifying evidence may include:

```text
SYSTEM_OR_EXPORT_FAILURE_EXPLICITLY_RECORDED
FILE_OR_SNAPSHOT_INCOMPLETENESS_EXPLICITLY_DECLARED
OTHER_GOVERNED_SOURCE_DATA_LOSS_EVIDENCE
```

Row absence by itself never qualifies.

## 4. Corrected formulas

Accepted business-policy formulas:

```text
MISSING_DAY_COUNT_FORMULA=
count(canonical S1 calendar days explicitly proven by governed source-loss evidence
      to have Source 002 data loss)

MISSING_DATA_PROPORTION_NUMERATOR=
explicitly_proven_source_loss_days

MISSING_DATA_PROPORTION_DENOMINATOR=
total_governed_canonical_s1_calendar_days

MISSING_DATA_PROPORTION_FORMULA=
explicitly_proven_source_loss_days / total_governed_canonical_s1_calendar_days
```

These are policy definitions only. No numeric calculation is performed in this correction.

## 5. Important zero-result boundary

The BUSINESS_OWNER statement means ordinary row absence is not missingness. It does **not** by itself prove that the governed source suffered zero explicit data-loss incidents.

Therefore:

```text
ABSENCE_OF_SOURCE_LOSS_EVIDENCE_PROVES_ZERO_MISSING_DAYS=false
MISSING_DAY_COUNT=UNRESOLVED
MISSING_DATA_PROPORTION=UNRESOLVED
```

A numeric zero may be emitted only after governed source-loss status evidence establishes that there were no known Source 002 data-loss days in the governed scope.

This avoids converting “we have not checked for system/export loss” into a false completeness claim.

## 6. Source-owner evidence dependency

The previous dependency on a daily expected-harvest/expected-recording universe is removed.

```text
SOURCE_OWNER_EXPECTED_RECORDING_UNIVERSE_EVIDENCE_REQUIRED=false
EXPECTED_HARVEST_DAY_LIST_REQUIRED=false
```

The remaining evidence need is much narrower:

```text
NEXT_GATE=SOURCE_OWNER_EXPLICIT_SOURCE_DATA_LOSS_STATUS_EVIDENCE
REQUIRED_ROLE=农场数据负责人
SOURCE_LOSS_STATUS_EVIDENCE_ISSUED=false
```

The evidence only needs to establish whether the governed Source 002 scope has known explicit source-data-loss days and, if yes, identify them under governed evidence.

It does not require a day-by-day harvest expectation list.

## 7. July boundary

The prior governed July boundary is preserved:

```text
UNMAPPED_DATE=2025-07-22
UNMAPPED_ROW_COUNT=2
RAW_ROWS_RETAINED=true
CANONICAL_S1_COHORT_INCLUDED=false
AUTOMATIC_SEASON_ASSIGNMENT=false
CANONICAL_MISSINGNESS_DENOMINATOR_INCLUDED=false
```

The two July rows remain raw-retained and canonical-excluded. Nothing in this correction silently assigns them to a season.

## 8. Decimal and zero-denominator policy

Preserved:

```text
ZERO_DENOMINATOR_POLICY=BLOCK_AND_UNRESOLVED
DECIMAL_PRECISION_POLICY=FIXED_8_DECIMAL_HALF_EVEN
DECIMAL_SCALE=8
ROUNDING_MODE=ROUND_HALF_EVEN
OUTPUT_REPRESENTATION=DECIMAL_STRING
BINARY_FLOATING_POINT_GOVERNANCE_IDENTITY_ALLOWED=false
```

If the governed canonical S1 day denominator is zero, no numeric proportion is emitted.

## 9. Current computation state

```text
BUSINESS_FORMULA_POLICY_DECISION_ISSUED=true
BUSINESS_FORMULA_POLICY_CORRECTED=true
BUSINESS_FORMULA_POLICY_ACCEPTED=true
SELECTED_POLICY=EXPLICIT_SOURCE_DATA_LOSS_ONLY

ROW_ABSENCE_SEMANTICS=NO_HARVEST

MISSING_DAY_COUNT=UNRESOLVED
MISSING_DATA_PROPORTION=UNRESOLVED

DESCRIPTIVE_CALENDAR_GAP_COUNT=31455
DESCRIPTIVE_CALENDAR_GAP_COUNT_IS_FORMAL_MISSING_DAY_COUNT=false

COVERAGE_SCOPE_START=2025-08-05
COVERAGE_SCOPE_END=2026-04-16
COVERAGE_END_IS_COMPLETENESS_WATERMARK=false
```

The prior descriptive `31455` value remains descriptive only and is not promoted to a missingness result.

## 10. Governance state

```text
SOURCE_LOSS_STATUS_EVIDENCE_ISSUED=false
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

This correction does not close `S1-SOURCE-AUTHORITY` or any other canonical S1 gate.

## 11. Safety boundary

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

## 12. Correction provenance and hash

```text
DECISION_AUTHORITY_ROLE=BUSINESS_OWNER
CORRECTION_EVENT=EXPLICIT_BUSINESS_OWNER_ROW_ABSENCE_SEMANTIC_CORRECTION
CORRECTION_AT=2026-08-13T08:21:00+08:00
DECISION_TIMEZONE_OFFSET=+08:00
PERSONAL_IDENTITY_RECORDED=false

DECISION_HASH_ALGORITHM=SHA256
DECISION_HASH_CANONICALIZATION=UTF8_JSON_SORT_KEYS_RECURSIVELY_COMPACT_SEPARATORS_ENSURE_ASCII_FALSE
DECISION_HASH_SCOPE=FULL_DECISION_RECORD_EXCLUDING_FIELD_decision_record_sha256
DECISION_RECORD_SHA256=fffb05946c744839120220c99994a90de0eeec7b46690574916c6b80b82fc3fe
```

## 13. Stop boundary

PR #208 must receive new exact-head CI after this correction.

```text
INDEPENDENT_REVIEW_STATUS=PENDING_EXACT_HEAD_CI_AND_SEPARATE_AUTHORIZATION
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false

NEXT_GATE=SOURCE_OWNER_EXPLICIT_SOURCE_DATA_LOSS_STATUS_EVIDENCE
NEXT_GATE_AUTHORIZED=false

NO_STEP_IMPLIES_THE_NEXT=true
```

The correction stops here. It does not authorize independent review, Ready, Merge, source-loss evidence issuance, numeric calculation, final attestation, Remaining06, or S2.
