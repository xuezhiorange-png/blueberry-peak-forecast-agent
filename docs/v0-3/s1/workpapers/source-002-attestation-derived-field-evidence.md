# Source 002 attestation-derived field evidence

## 1. Task and authorization boundary

```text
TASK=V0_3_S1_SOURCE_002_ATTESTATION_READ_ONLY_DERIVATION
TASK_CLASS=AUTHORIZED_FIXED_SOURCE_READ_ONLY_GOVERNANCE_DERIVATION
BASE_SHA=87db0e5fc85ddae0db4e008f053ae7c0ee20240e
SOURCE_002_READ_AUTHORIZED=true
SOURCE_002_RAW_READ_AUTHORIZED=true
SOURCE_002_ROW_LEVEL_READ_AUTHORIZED=true
SOURCE_002_MUTATION_AUTHORIZED=false
FINAL_SOURCE_ATTESTATION_AUTHORIZED=false
SOURCE_AUTHORITY_ACCEPTANCE_AUTHORIZED=false
CANONICAL_GATE_MUTATION_AUTHORIZED=false
```

This workpaper records a read-only derivation from the already frozen Source
002 object. It does not issue a business-source attestation, accept Source
Authority, mutate a canonical gate, or enter S1-REMAINING-06 or V0.3-S2.

Only the nine authorized schema-required source-derived paths were considered:
the three coverage identity arrays, two coverage-scope dates, two harvest-date
summary fields, `missing_day_count`, and `missing_data_proportion`.

## 2. Fixed Source 002 identity verification

The authorized fixed object was opened read-only outside the repository. Its
identity matched the frozen authority:

| Identity | Verified value |
| --- | --- |
| Source system | `扫码称重系统` |
| Source dataset | `田间商品果每日采摘净重汇总` |
| Source version | `scan-weight-export:v0_3_s1:002` |
| Snapshot reference | `snapshot:v0_3_s1:002` |
| Source SHA-256 | `fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a` |
| Byte count | `28,668,416` |
| Source row count | `233,171` |
| Observed schema version | `observed-source-schema-v1` |
| Observed schema SHA-256 | `919e63c4d3b4d00b304a045f63bfb050d4eb9abec3b0a318186b7ca2e7276867` |
| Sheet count | `4` |

The seven observed headers matched the fixed observed schema. No source
locator, credential, workbook, row-level extract, or database export is
stored in Git.

## 3. Governed scope and date boundary

The derivation applied the approved `2025~2026` mapped season and the D-003
July boundary. The two raw rows dated `2025-07-22` remain in the immutable raw
source and are excluded from the canonical S1 cohort. They were not deleted,
edited, silently reassigned, or converted to zero.

```text
JULY_UNMAPPED_ROW_COUNT=2
JULY_UNMAPPED_ROWS_RAW_RETAINED=true
JULY_UNMAPPED_ROWS_CANONICAL_INCLUDED=false
JULY_AUTO_ASSIGNMENT=false
SILENT_REASSIGNMENT=false
KNOWN_BUSINESS_EXCLUSIONS_AT_S1_SOURCE_SCOPE=NO_KNOWN_BUSINESS_EXCLUSIONS_AT_S1_SOURCE_SCOPE
```

The locally observed raw date range was `2025-07-22` through `2026-04-16`.
The governed canonical S1 in-scope date range was `2025-08-05` through
`2026-04-16`, across `233,169` in-scope rows. The latter range, rather than
the raw July-inclusive range, supplies the four date fields below.

`2026-04-16` is an observed last date only. It is not a completeness
watermark, and no `SOURCE_COMPLETE_THROUGH_BUSINESS_DATE` value was inferred
or issued.

## 4. Identity-array derivation

The identity arrays were derived from the approved canonical S1 rows using
the existing raw identity columns, without aliasing, spelling correction,
identity merging, null replacement, or silent reassignment. Values were
deterministically sorted and hashed as UTF-8 compact JSON arrays with
`ensure_ascii=false` using SHA-256.

Full arrays are intentionally omitted from both this workpaper and the JSON
evidence. They exist only in the external derived-value package identified in
Section 7.

| Field | Count | SHA-256 | Full array in Git |
| --- | ---: | --- | --- |
| `coverage_scope.farms` | 84 | `2daf09d38efb41bada5a1b493974c569e64b63abdd322e5ab4dacc206edb0381` | false |
| `coverage_scope.subfarms` | 192 | `921a56006d1a75f683c62c8a930e913fc39cabf2dcffec88b16549ed95945e13` | false |
| `coverage_scope.varieties` | 20 | `fe6274775796193318fa3ad504ba8cc4e2196b8c58dd8f795cec80cc22c26209` | false |

All three counts and all three array hashes matched the frozen identity
authority. No full identity array was printed in the review summary, commit
message, or PR body.

## 5. Nine authorized field results

| Schema path | Result | Derived value or evidence |
| --- | --- | --- |
| `coverage_scope.farms` | RESOLVED | Count `84`; SHA-256 recorded above; full value external only |
| `coverage_scope.subfarms` | RESOLVED | Count `192`; SHA-256 recorded above; full value external only |
| `coverage_scope.varieties` | RESOLVED | Count `20`; SHA-256 recorded above; full value external only |
| `coverage_scope.business_date_start` | RESOLVED | `2025-08-05` |
| `coverage_scope.business_date_end` | RESOLVED | `2026-04-16` |
| `coverage_summary.first_harvest_business_date` | RESOLVED | `2025-08-05` |
| `coverage_summary.last_harvest_business_date` | RESOLVED | `2026-04-16`; observed date, not a completeness watermark |
| `coverage_summary.missing_day_count` | UNRESOLVED | No unique formal denominator/date-universe authority |
| `coverage_summary.missing_data_proportion` | UNRESOLVED | No unique formal formula/denominator/precision authority |

The first seven paths are resolved from the fixed object and the approved
scope/date boundary. The remaining two are deliberately not assigned a
numeric or string value.

## 6. Missing-day authority remains unresolved

Current-main contracts establish:

```text
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
MISSING_DAY_NUMERIC_IMPUTATION_ALLOWED=false
```

They do not provide one unique answer for all of the following required
inputs:

- whether the date universe is source-scope calendar days or expected
  canonical group-days;
- the expected canonical group universe and its eligibility rules;
- whether the denominator is calendar days, expected group-days,
  eligible group-days, or another governed universe;
- the exact `missing_data_proportion` numerator and denominator;
- required precision and rounding.

The repository's `DESCRIPTIVE_CALENDAR_GAP_COUNT=31455` is explicitly marked
as descriptive-only and not a formal missing-day count. It is not used here.
No missing day was converted to `0 kg`, and no zero row was manufactured.

```text
MISSING_DAY_FORMULA_AUTHORITY_RESOLVED=false
MISSING_DATA_PROPORTION_FORMULA_AUTHORITY_RESOLVED=false
MISSING_DAY_COUNT=UNRESOLVED
MISSING_DATA_PROPORTION=UNRESOLVED
SOURCE_COMPLETENESS_WATERMARK_INFERRED=false
```

This is a fail-closed partial derivation: seven of nine fields are resolved,
but a final schema-valid attestation cannot be assembled from this package.

## 7. External derived-value package

The complete identity arrays and the seven resolved values are held only in
the external package below. The package contains no raw rows and is not a Git
artifact.

```text
DERIVED_VALUE_PACKAGE_ID=source-002-attestation-derived-values-v1
DERIVED_VALUE_PACKAGE_STATUS=PARTIAL_DERIVATION_MISSING_DAY_FORMULA_AUTHORITY
DERIVED_VALUE_PACKAGE_SHA256=5b362513ae4ffb9279ba978c64c566f75bc2cda12d10fb0f4bab1a5c445f3fe9
DERIVED_VALUE_PACKAGE_COMMITTED_TO_GIT=false
RAW_ROWS_IN_PACKAGE=false
FULL_IDENTITY_ARRAYS_IN_GIT=false
```

The package hash is the SHA-256 of the UTF-8 recursively sorted compact
canonical JSON package excluding its self-hash field.

## 8. Governance and safety invariants

```text
SOURCE_OWNER_ATTESTATION_ISSUED=false
FINAL_ATTESTATION_ISSUANCE_READY=false
SOURCE_AUTHORITY_ACCEPTED=false
S1_SOURCE_AUTHORITY_STATUS=BLOCKED
S1_SOURCE_AUTHORITY_CANONICAL_GATE_PASS=false
CURRENT_CANONICAL_GATE_PASS_COUNT=0
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=17
CANONICAL_GATE_STATUS_CHANGED=false
CANONICAL_ACCEPTANCE_RECORD_CHANGED=false

SOURCE_002_MUTATION=false
PRODUCTION_DATABASE_READ=false
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

V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

## 9. Review boundary

This task produces evidence only. It does not issue final Source Owner
Attestation, accept Source Authority, close any canonical gate, authorize
S1-REMAINING-06, or authorize V0.3-S2.

```text
TASK_RESULT=BLOCKED
PARTIAL_DERIVATION_COMPLETED=true
ALL_9_SOURCE_DERIVED_FIELDS_RESOLVED=false
NEXT_RECOMMENDED_ACTION=RUN_SOURCE_002_ATTESTATION_DERIVATION_EXACT_HEAD_INDEPENDENT_REVIEW
NO_STEP_IMPLIES_THE_NEXT=true
```
