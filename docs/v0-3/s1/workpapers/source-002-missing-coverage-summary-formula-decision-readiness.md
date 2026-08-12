# Source 002 missing coverage-summary formula decision readiness

## 1. Scope and non-authorizations

```text
TASK=V0_3_S1_SOURCE_002_MISSING_COVERAGE_SUMMARY_FORMULA_DECISION_READINESS
TASK_CLASS=DOCS_ONLY_GOVERNANCE_DECISION_READINESS
BASE_SHA=13971067cc0c741d7b4daece26f28635737db499
SOURCE_002_READ=false
SOURCE_002_RAW_READ=false
SOURCE_002_ROW_LEVEL_READ=false
REAL_BUSINESS_DATA_READ=false
PRODUCTION_DATABASE_READ=false
FORMULA_DECISION_AUTHORIZED=false
FORMULA_ACCEPTANCE_AUTHORIZED=false
MISSING_DAY_CALCULATION_AUTHORIZED=false
FINAL_SOURCE_ATTESTATION_AUTHORIZED=false
CANONICAL_GATE_MUTATION_AUTHORIZED=false
```

This package prepares a decision interface for the two unresolved schema
required fields:

- `coverage_summary.missing_day_count`
- `coverage_summary.missing_data_proportion`

It does not open Source 002, calculate either field, select a candidate,
accept a formula, issue a Source Owner Attestation, or mutate any canonical
gate.

## 2. Current-main facts and authority

The package only cites current-main aggregate and governance evidence. The
frozen facts relevant to the decision are:

| Fact | Current-main value |
| --- | --- |
| Source | `扫码称重系统` / `田间商品果每日采摘净重汇总` |
| Source version | `scan-weight-export:v0_3_s1:002` |
| Snapshot | `snapshot:v0_3_s1:002` |
| Source row count | `233171` |
| Mapped season | `2025~2026` |
| Raw-retained unmapped date | `2025-07-22`, `2` rows |
| Canonical S1 scope | `2025-08-05` through `2026-04-16` |
| Canonical identity counts | `84` farms, `192` subfarms, `20` varieties |
| Mapped canonical group count | `529` |
| Missing-day semantics | `UNKNOWN_NOT_ZERO` |
| Numeric imputation | `false` |
| Descriptive calendar gap count | `31455` |
| Formal missing-day interpretation of 31455 | `false` |
| Completeness watermark | `SOURCE_COMPLETE_THROUGH_BUSINESS_DATE=NOT_ISSUED` |

Supporting current-main sources include the existing derived-field evidence,
the business-owner decision record, the governed-snapshot evidence, the
formalization gap matrix, the cohort candidate, the inclusion/exclusion
manifest, the custody record, and the acceptance package. The existing
attestation schema confirms that both fields are schema-required: the count is
a non-negative integer and the proportion is a decimal string in `[0, 1]`.

The current source-owner role is recorded as `农场数据负责人` for the source
and completeness boundary. The current business decision record also records
`BUSINESS_OWNER` as its decision authority role. Current-main artifacts do not
uniquely establish which role may accept the missingness universe and formula;
that authority boundary is therefore itself a required decision input.

## 3. Critical semantic boundary

The following statements are deliberately distinct:

```text
NO_ROW_ON_DATE != PROVEN_MISSING_DATA
NO_ROW_ON_DATE != ZERO_HARVEST
NO_ROW_ON_DATE != PROVEN_NO_HARVEST
NO_ROW_ON_DATE != SOURCE_COMPLETENESS_FAILURE
```

`UNKNOWN_NOT_ZERO` means that an absent record cannot be silently converted to
`0 kg`. It does not mean every date without a Source 002 row is a data
failure. A defensible formula needs a separately authorized expected date or
expected recording universe that can distinguish observed row absence,
business no-harvest days, source-data missing days, and source-completeness
failure.

## 4. Decision status and authority template

```text
DECISION_STATUS=DECISION_REQUIRED
DECISION_AUTHORITY_ROLE=UNRESOLVED
DECISION_AUTHORITY_RESOLUTION_REQUIRED=true
RECOMMENDATION_IS_NOT_DECISION=true
SELECTED_OPTION=null
ACCEPTED_VALUE=null
DECISION_EVENT=null
DECISION_AT=null
DECISION_RECORD_HASH=null
```

The current-main provenance for `农场数据负责人` is the D-005/source
completeness declaration boundary. That evidence is sufficient to identify a
possible source-owner participant, but it does not by itself prove that the
role can accept the missing-day semantic unit, denominator, formula,
precision, or rounding policy. The final decision record must resolve this
responsibility explicitly and preserve its own event time and hash.

## 5. Candidate option matrix

All options below are candidates only. None is selected or accepted.

| Option | Expected universe | Missing-day meaning | Main strength | Main risk | Status |
| --- | --- | --- | --- | --- | --- |
| `GLOBAL_CALENDAR_DAY` | All local calendar dates from `2025-08-05` through `2026-04-16` | Source-wide date with zero canonical S1 rows | Simple source-wide day-gap metric | A day with one row hides other group absence; no-harvest remains indistinguishable | NOT_ACCEPTED |
| `FULL_CANONICAL_GROUP_DAY` | `529` canonical groups × the full canonical date interval | Group-day without a governed row | Exposes canonical-grain row absence | Pre/post lifecycle days can be overcounted; field unit becomes `GROUP_DAY` | NOT_ACCEPTED |
| `ACTIVE_GROUP_SPAN_DAY` | Each group’s first observed through last observed date | Empty date inside a group active span | Avoids counting all lifecycle dates | An empty active-span date may be normal no-harvest, not missing data | NOT_ACCEPTED |
| `AUTHORITY_DECLARED_EXPECTED_HARVEST_DAY` | Independently declared expected recording days | Expected group-day without a governed row | Strongest true-missingness semantics | Requires an independent expected-harvest/recording authority | NOT_ACCEPTED |
| `NOT_COMPUTABLE_FROM_SOURCE_002_ALONE` | No universe until independent authority exists | Keep both fields unresolved | Correct fail-closed result | Blocks final attestation issuance | NOT_ACCEPTED |

### Option A — GLOBAL_CALENDAR_DAY

```text
EXPECTED_DATE_UNIVERSE=all local calendar dates from 2025-08-05 through 2026-04-16 inclusive
MISSING_DAY_COUNT=count(expected dates with zero governed canonical S1 rows across the source scope)
MISSING_DATA_PROPORTION=missing_global_calendar_days / total_expected_calendar_days
SEMANTIC_UNIT=SOURCE_WIDE_CALENDAR_DAY
```

This option describes source-wide complete-day gaps only. It does not claim
canonical-grain completeness or true missingness.

### Option B — FULL_CANONICAL_GROUP_DAY

```text
EXPECTED_GROUP_DAY_UNIVERSE=529 canonical groups x all canonical S1 dates
MISSING_DAY_COUNT=count(expected group-days with no governed Source 002 row)
MISSING_DATA_PROPORTION=missing_group_days / all_expected_group_days
SEMANTIC_UNIT=GROUP_DAY
```

The semantic reinterpretation of `missing_day_count` as `GROUP_DAY` requires
explicit authority. Group lifecycle boundaries can otherwise produce a
systematic overcount.

### Option C — ACTIVE_GROUP_SPAN_DAY

```text
EXPECTED_ACTIVE_GROUP_DAY_UNIVERSE=each group first observed date through last observed date
MISSING_DAY_COUNT=sum(active-group dates with no governed row)
MISSING_DATA_PROPORTION=sum(active-group missing group-days) / sum(active-group span days)
SEMANTIC_UNIT=ACTIVE_GROUP_DAY
```

This is a structural heuristic, not proof of missing source data. An empty
date inside an active span can still be a normal no-harvest day.

### Option D — AUTHORITY_DECLARED_EXPECTED_HARVEST_DAY

```text
EXPECTED_GROUP_DAY_UNIVERSE=authority-declared expected recording days for canonical groups
MISSING_DAY_COUNT=count(expected group-days without a governed Source 002 row)
MISSING_DATA_PROPORTION=missing expected group-days / all authority-declared expected group-days
SEMANTIC_UNIT=AUTHORITY_DECLARED_GROUP_DAY
```

This is the strongest semantic option if an independent expected-harvest or
expected-recording authority exists. Source 002 row presence cannot create
that denominator on its own.

### Fail-closed option — NOT_COMPUTABLE_FROM_SOURCE_002_ALONE

Until a separate expected-recording or completeness authority exists, both
fields remain unresolved. This is the current recommendation, not an
acceptance decision.

```text
RECOMMENDED_OPTION=NOT_COMPUTABLE_FROM_SOURCE_002_ALONE
OPTION_C_ACCEPTED=false
OPTION_D_ACCEPTED=false
```

## 6. July boundary and coverage interval

Every candidate must answer whether `2025-07-22` enters its denominator. The
current canonical scope says its two rows are raw-retained but excluded from
the canonical S1 cohort. The readiness recommendation is therefore:

```text
JULY_DENOMINATOR_TREATMENT_DECISION_REQUIRED=true
RECOMMENDED_JULY_TREATMENT=exclude 2025-07-22 from the canonical S1 missingness denominator
RECOMMENDATION_IS_NOT_ACCEPTANCE=true
```

The candidate interval is:

```text
CANDIDATE_COVERAGE_START=2025-08-05
CANDIDATE_COVERAGE_END=2026-04-16
COVERAGE_END_IS_NOT_COMPLETENESS_WATERMARK=true
```

`2026-04-16` is only the observed canonical S1 coverage end. It must not be
issued or described as `SOURCE_COMPLETE_THROUGH_2026-04-16`.

```text
DESCRIPTIVE_CALENDAR_GAP_COUNT=31455
DESCRIPTIVE_CALENDAR_GAP_COUNT_IS_FORMAL_MISSING_DAY_COUNT=false
```

## 7. Missing-data proportion decision inputs

The proportion requires an independently accepted contract for each item:

```text
MISSING_DATA_PROPORTION_NUMERATOR_DECISION_REQUIRED=true
MISSING_DATA_PROPORTION_DENOMINATOR_DECISION_REQUIRED=true
MISSING_DATA_PROPORTION_ZERO_DENOMINATOR_POLICY_DECISION_REQUIRED=true
MISSING_DATA_PROPORTION_PRECISION_DECISION_REQUIRED=true
MISSING_DATA_PROPORTION_ROUNDING_DECISION_REQUIRED=true
```

Precision candidates are:

```text
EXACT_DECIMAL_RATIO_STRING
FIXED_6_DECIMAL_HALF_EVEN
FIXED_8_DECIMAL_HALF_EVEN
```

Binary floating point is not a governance identity. The final schema value
must be a decimal string within `0 <= value <= 1`.

If the accepted expected-universe count is zero, the authority must choose
one of:

```text
A=BLOCK_AND_UNRESOLVED
B=ZERO
C=NOT_APPLICABLE
RECOMMENDED_ZERO_DENOMINATOR_POLICY=BLOCK_AND_UNRESOLVED
```

No `0 / 0 = 0` assumption is made.

## 8. Decision records to be issued later

Two decision records are required, one for each unresolved schema path:

| Decision ID | Gate | Status | Recommended option | Selected | Accepted |
| --- | --- | --- | --- | --- | --- |
| `SOURCE_002_MISSING_DAY_COUNT_SEMANTICS` | `S1-SOURCE-AUTHORITY` | `DECISION_REQUIRED` | `NOT_COMPUTABLE_FROM_SOURCE_002_ALONE` | null | null |
| `SOURCE_002_MISSING_DATA_PROPORTION_FORMULA` | `S1-SOURCE-AUTHORITY` | `DECISION_REQUIRED` | `NOT_COMPUTABLE_FROM_SOURCE_002_ALONE` | null | null |

Each later record must include an authority role and basis, selected option,
accepted value/formula, event, decision time, and decision-record hash. Until
then:

```text
coverage_summary.missing_day_count=UNRESOLVED
coverage_summary.missing_data_proportion=UNRESOLVED
MISSING_DAY_FORMULA_AUTHORITY_RESOLVED=false
MISSING_DATA_PROPORTION_FORMULA_AUTHORITY_RESOLVED=false
FORMULA_DECISION_ISSUED=false
FORMULA_ACCEPTED=false
```

## 9. Remaining attestation blockers

Even after a future formula decision and derivation, final attestation cannot
be issued until the other schema-required authority boundaries are closed:

- source-owner confirmation pending fields;
- `withdrawal_and_void_policy.withdrawal_status_rule`;
- `withdrawal_and_void_policy.void_status_rule`;
- `revision_policy.winner_and_lineage_rule`;
- `late_entry_rule`;
- `visibility_boundary`;
- issuance-process-derived attestation metadata.

This package is not final-attestation-ready.

## 10. Governance invariants

```text
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

No Source 002 object, raw row, production database, TEST data, or external
holdout was accessed by this task.

## 11. Review boundary

```text
TASK_RESULT=PASS
DECISION_READINESS_COMPLETE=true
FORMULA_DECISION_STATUS=DECISION_REQUIRED
RECOMMENDATION_IS_NOT_DECISION=true
NEXT_RECOMMENDED_ACTION=RUN_MISSING_COVERAGE_FORMULA_DECISION_READINESS_EXACT_HEAD_INDEPENDENT_REVIEW
NO_STEP_IMPLIES_THE_NEXT=true
```

This `PASS` means only that the decision-readiness package is complete. It
does not mean either formula is accepted or either missing field is resolved.
