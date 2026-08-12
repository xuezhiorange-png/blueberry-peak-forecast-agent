# Source 002 missing coverage formula authority model freeze

## 1. Scope and hard boundary

```text
TASK=V0_3_S1_SOURCE_002_MISSING_COVERAGE_FORMULA_AUTHORITY_MODEL_FREEZE
TASK_CLASS=DOCS_ONLY_GOVERNANCE_AUTHORITY_MODEL_FREEZE
BASE_SHA=110b2e8c5a5a452a2b85ae1740a31e65ccfffed3
AUTHORITY_MODEL_FREEZE_AUTHORIZED=true
FORMULA_SELECTION_AUTHORIZED=false
FORMULA_ACCEPTANCE_AUTHORIZED=false
MISSING_DAY_CALCULATION_AUTHORIZED=false
SOURCE_002_READ=false
SOURCE_002_RAW_READ=false
SOURCE_002_ROW_LEVEL_READ=false
REAL_BUSINESS_DATA_READ=false
PRODUCTION_DATABASE_READ=false
SOURCE_COMPLETENESS_DECLARATION_AUTHORIZED=false
FINAL_SOURCE_ATTESTATION_AUTHORIZED=false
SOURCE_AUTHORITY_ACCEPTANCE_AUTHORIZED=false
CANONICAL_GATE_MUTATION_AUTHORIZED=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
```

This workpaper freezes only the authority partition for the two unresolved
schema-required fields:

- `coverage_summary.missing_day_count`
- `coverage_summary.missing_data_proportion`

It does not select a candidate, calculate either value, accept a formula,
issue completeness evidence, issue a Source Owner Attestation, or mutate a
canonical gate. It relies only on current-main governance artifacts; Source
002 itself, raw rows, row-level data, and production databases were not read.

## 2. Current-main authority basis

The current-main readiness artifact records both fields as unresolved and
recommends `NOT_COMPUTABLE_FROM_SOURCE_002_ALONE` only as a fail-closed
candidate. The current-main business-owner decision record identifies
`BUSINESS_OWNER` as the business decision authority and records
`农场数据负责人` as the source/completeness role under D-005. The existing
schema requires both fields, while the current evidence does not issue a
formal completeness watermark or formula decision.

This new artifact freezes the responsibility boundary prospectively. It does
not rewrite the historical readiness artifact, whose unresolved authority
role remains historical evidence of the prior state.

## 3. Frozen authority matrix

| Authority layer | Role | May decide or provide | Explicit limit |
| --- | --- | --- | --- |
| Business formula policy | `BUSINESS_OWNER` | Expected date universe, expected canonical-group universe, missingness unit, both formula policies, July treatment, zero-denominator policy, precision, rounding | Must not invent or assert undocumented Source 002 completeness facts |
| Expected-recording evidence | `农场数据负责人` | Evidence that a group-day was expected to have a governed record; expected-recording universe evidence | Must not redefine the business meaning of the metric |
| Source completeness declaration | `农场数据负责人` | Source completeness declaration and source-fact confirmation | Does not unilaterally choose the formula policy or semantic unit |
| Final Source Attestation binding | `农场数据负责人` | Binding the final source facts and attestation event | Cannot issue a final attestation while required values or policies remain unresolved |

The following invariants are frozen:

```text
BUSINESS_OWNER_MAY_DEFINE_BUSINESS_FORMULA_POLICY=true
BUSINESS_OWNER_MAY_INVENT_SOURCE_COMPLETENESS=false
SOURCE_OWNER_MAY_CONFIRM_SOURCE_FACTS=true
SOURCE_OWNER_MAY_ISSUE_SOURCE_COMPLETENESS_DECLARATION=true
SOURCE_OWNER_MAY_UNILATERALLY_CHANGE_BUSINESS_SEMANTICS=false
JOINT_CONCURRENCE_REQUIRED_FOR_COMPUTABLE_FORMULA=true
```

## 4. Joint computability contract

A computable formula requires both components:

```text
COMPUTABLE_FORMULA=
  ACCEPTED_BUSINESS_FORMULA_POLICY
  +
  SUFFICIENT_SOURCE_OWNER_EXPECTED_RECORDING_OR_COMPLETENESS_EVIDENCE
```

Neither business policy alone nor source evidence alone is sufficient. The
current state is:

```text
CURRENT_STATUS=NOT_COMPUTABLE
CURRENT_FAIL_CLOSED_OPTION=NOT_COMPUTABLE_FROM_SOURCE_002_ALONE
CURRENT_FAIL_CLOSED_OPTION_IS_FINAL_DECISION=false
FORMULA_DECISION_ISSUED=false
FORMULA_ACCEPTED=false
SELECTED_OPTION=null
```

Here `NOT_COMPUTABLE` means that governance prerequisites are incomplete; it
is not an accepted final formula value and does not populate either schema
field.

## 5. Candidate options remain unaccepted

The five current-main candidates remain decision inputs only:

| Option | Role in the decision interface | Status |
| --- | --- | --- |
| `GLOBAL_CALENDAR_DAY` | Global source-wide calendar-day gap metric | `CANDIDATE_NOT_ACCEPTED` |
| `FULL_CANONICAL_GROUP_DAY` | Full canonical group-day universe | `CANDIDATE_NOT_ACCEPTED` |
| `ACTIVE_GROUP_SPAN_DAY` | Group-specific observed active-span heuristic | `CANDIDATE_NOT_ACCEPTED` |
| `AUTHORITY_DECLARED_EXPECTED_HARVEST_DAY` | Independent expected-recording authority universe | `CANDIDATE_NOT_ACCEPTED` |
| `NOT_COMPUTABLE_FROM_SOURCE_002_ALONE` | Fail-closed result when the two authority components are incomplete | `FAIL_CLOSED_CANDIDATE_NOT_ACCEPTED` |

```text
CANDIDATE_OPTION_COUNT=5
ALL_CANDIDATE_OPTIONS_ACCEPTED=false
SELECTED_OPTION=null
```

No sixth option is introduced and no existing option is silently renamed.

## 6. July and completeness boundary

Current governed facts remain:

```text
UNMAPPED_DATE=2025-07-22
UNMAPPED_ROW_COUNT=2
RAW_ROWS_RETAINED=true
CANONICAL_S1_COHORT_INCLUDED=false
AUTOMATIC_SEASON_ASSIGNMENT=false
JULY_DENOMINATOR_TREATMENT_DECISION_REQUIRED=true
JULY_DENOMINATOR_TREATMENT_ACCEPTED=false
```

The prior readiness recommendation to exclude the unmapped July date from a
canonical S1 denominator remains only a decision input. This task does not
accept that treatment.

The descriptive canonical interval is:

```text
COVERAGE_SCOPE_START=2025-08-05
COVERAGE_SCOPE_END=2026-04-16
COVERAGE_END_IS_COMPLETENESS_WATERMARK=false
SOURCE_COMPLETE_THROUGH_BUSINESS_DATE=NOT_ISSUED
SOURCE_COMPLETENESS_DECLARATION_ISSUED=false
```

`2026-04-16` is not a completeness watermark. The current descriptive gap
metadata is preserved without promotion:

```text
DESCRIPTIVE_CALENDAR_GAP_COUNT=31455
DESCRIPTIVE_CALENDAR_GAP_COUNT_IS_FORMAL_MISSING_DAY_COUNT=false
```

## 7. Missing-day semantic boundary

```text
CURRENT_MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
MISSING_DAY_NUMERIC_IMPUTATION_ALLOWED=false
```

The following distinctions are mandatory:

```text
NO_ROW_ON_DATE != PROVEN_MISSING_DATA
NO_ROW_ON_DATE != ZERO_HARVEST
NO_ROW_ON_DATE != PROVEN_NO_HARVEST
NO_ROW_ON_DATE != SOURCE_COMPLETENESS_FAILURE
```

`UNKNOWN_NOT_ZERO` prevents absent data from being silently converted to
`0 kg`; it does not itself establish an expected recording universe or prove
source completeness.

## 8. Required decision architecture

### A. Formula policy decision

```text
DECISION_ID=SOURCE_002_MISSING_COVERAGE_FORMULA_POLICY
DECISION_AUTHORITY_ROLE=BUSINESS_OWNER
DECISION_STATUS=AUTHORIZED_AUTHORITY_MODEL_ONLY
POLICY_VALUE_SELECTED=false
```

This object establishes who may decide the policy, not which policy is
accepted. Its decision event, decision time, and decision-record hash remain
unset.

### B. Expected-recording and completeness evidence

```text
DECISION_ID=SOURCE_002_EXPECTED_RECORDING_AND_COMPLETENESS_EVIDENCE
EVIDENCE_AUTHORITY_ROLE=农场数据负责人
DECISION_STATUS=EVIDENCE_REQUIRED
EVIDENCE_ISSUED=false
SOURCE_COMPLETENESS_DECLARATION_ISSUED=false
```

The source owner may provide or attest the source-side evidence needed for a
formula, but this task does not request, generate, or issue that evidence.

### C. Joint computability determination

```text
DECISION_ID=SOURCE_002_MISSING_COVERAGE_COMPUTABILITY
REQUIRES_BUSINESS_POLICY_ACCEPTANCE=true
REQUIRES_SOURCE_OWNER_EVIDENCE=true
JOINT_CONCURRENCE_REQUIRED=true
CURRENT_STATUS=NOT_COMPUTABLE
NOT_COMPUTABLE_IS_AN_ACCEPTED_FINAL_FORMULA=false
```

## 9. Proportion policy remains unresolved

The following decisions remain required and unaccepted:

```text
PROPORTION_NUMERATOR_DECISION_REQUIRED=true
PROPORTION_DENOMINATOR_DECISION_REQUIRED=true
PROPORTION_PRECISION_DECISION_REQUIRED=true
PROPORTION_ROUNDING_DECISION_REQUIRED=true
ZERO_DENOMINATOR_POLICY_DECISION_REQUIRED=true
```

Precision candidates remain `EXACT_DECIMAL_RATIO_STRING`,
`FIXED_6_DECIMAL_HALF_EVEN`, and `FIXED_8_DECIMAL_HALF_EVEN`. Zero-denominator
candidates remain `BLOCK_AND_UNRESOLVED`, `ZERO`, and `NOT_APPLICABLE`;
`BLOCK_AND_UNRESOLVED` is only a recommendation. No candidate is accepted,
and binary floating point is not a governance identity.

## 10. Current formula and governance state

```text
MISSING_DAY_COUNT=UNRESOLVED
MISSING_DATA_PROPORTION=UNRESOLVED
MISSING_DAY_FORMULA_AUTHORITY_RESOLVED=false
MISSING_DATA_PROPORTION_FORMULA_AUTHORITY_RESOLVED=false
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

Even after a future formula decision and derivation, final Source Attestation
would still require the other unresolved source-owner, later-authority, and
issuance-process fields. This artifact is not final-attestation-ready.

## 11. Safety and validation boundary

```text
SOURCE_002_READ=false
SOURCE_002_RAW_READ=false
SOURCE_002_ROW_LEVEL_READ=false
REAL_BUSINESS_DATA_READ=false
PRODUCTION_DATABASE_READ=false
PRODUCTION_DATABASE_WRITE=false
SOURCE_002_MUTATION=false
TEST_DATA_ACCESS=false
EXTERNAL_HOLDOUT_DATA_ACCESS=false
BACKTEST_EXECUTED=false
MODEL_TRAINING_EXECUTED=false
METRIC_EXECUTION_PERFORMED=false
PRODUCTION_CODE_CHANGED=false
TEST_CODE_CHANGED=false
DATABASE_SCHEMA_CHANGED=false
MIGRATION_CREATED=false
MODEL_CHANGED=false
```

The artifact validation must establish the exact-base match, both authority
roles, the joint-concurrence rule, unresolved fields, non-promotion of 31455,
non-watermark treatment of 2026-04-16, unchanged canonical gate state, and a
two-file repository diff.

## 12. Stop boundary

```text
CHANGED_FILE_COUNT=2
CHANGED_FILES=
docs/v0-3/s1/evidence/source-002-missing-coverage-formula-authority-model.json,
docs/v0-3/s1/workpapers/source-002-missing-coverage-formula-authority-model.md
NEXT_RECOMMENDED_ACTION=RUN_MISSING_COVERAGE_FORMULA_AUTHORITY_MODEL_EXACT_HEAD_INDEPENDENT_REVIEW
NO_STEP_IMPLIES_THE_NEXT=true
```

This task stops after the Draft PR and exact-head CI. It does not mark the PR
Ready, merge it, select or accept a formula, issue completeness evidence,
issue a Source Owner Attestation, authorize Remaining06, or authorize S2.
