# V0.3-S1 Source Schema Field Map and Gap Register

## Workpaper identity and status

```text
WORKPAPER_ID=V0_3_S1_SOURCE_SCHEMA_FIELD_MAP_AND_GAP_REGISTER
BASE_MAIN_SHA=91fff1fb976cfdbbdc59807537e40dde37364b75
WORKPAPER_STATUS=DRAFT_ONLY
SOURCE_MEASUREMENT_BUSINESS_RULES_STATUS=CONFIRMED
SOURCE_FINALIZATION_BUSINESS_RULES_STATUS=CONFIRMED
SEASON_CALENDAR_BUSINESS_RULE_STATUS=CONFIRMED
SOURCE_SNAPSHOT_METADATA_STATUS=PENDING
SOURCE_SNAPSHOT_METADATA_ENTRY_MODE=MACHINE_GENERATED
MANUAL_BUSINESS_USER_ENTRY_REQUIRED=false
CURRENT_SOURCE_AUTHORITY_BINDING_STATUS=BLOCKED
CURRENT_SOURCE_COHORT_FREEZE_STATUS=BLOCKED
CURRENT_Q2C_PHYSICAL_ALIGNMENT_STATUS=BLOCKED
CURRENT_V0_3_S1_COMPLETE=false
CURRENT_V0_3_S1_ACCEPTANCE_STATUS=BLOCKED
V0_3_S1_ACCEPTED=false
BUSINESS_SOURCE_ATTESTATION_JSON_CREATED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

This map describes the intended source-to-target roles from the confirmed
business information. It does not read or include source rows and does not
issue a source schema, source snapshot, cohort manifest, or Q2C result.

## Confirmed source field map

| Source field | Confirmed business meaning | Draft target or handling role | Grain treatment |
| --- | --- | --- | --- |
| 时间 | 采摘日期 | `HARVEST_BUSINESS_DATE` candidate | Enters the canonical date dimension after season matching. |
| 链路 | 旗舰公司名称 | Source provenance and traceability | Does not enter the canonical target grain. |
| 农场 | 农场 | `FARM` | Enters the canonical grain. |
| 分场 | 分场 | `SUBFARM` | Enters the canonical grain. |
| 品种 | 品种 | `VARIETY` | Enters the canonical grain. |
| 果径 | 来源维度 | Source dimension for aggregation | Does not enter the canonical target grain. |
| 入库公斤数 | 田间扫码称重形成的、已扣除筐重的商品果净重 | `QUANTITY_BASIS=已扣除筐重的商品果净重`, unit `kg` | Aggregated before the canonical target quantity is formed. |

The source label `入库公斤数` is mapped according to the confirmed business
meaning above; this workpaper does not infer any additional warehouse or
factory event from the label.

## Conversion draft

```text
1. 按采摘日期匹配产季
2. 同一产季、农场、分场、品种、采摘日期下，对各果径公斤数求和
3. 链路仅用于旗舰公司来源追溯，不进入目标粒度
```

The resulting draft grain is:

```text
SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
PLOT_SUPPORTED=false
```

## Confirmed measurement, finalization, and calendar inputs

```text
PHYSICAL_EVENT=田间采收点首次有效扫码称重
TARGET_QUANTITY=商品果净重
QUANTITY_UNIT=kg
TARE_ALREADY_DEDUCTED=true
QUANTITY_BASIS=已扣除筐重的商品果净重
TARE_DEDUCTION_METHOD=NOT_PROVIDED

SCALE_PRECISION=0.01 kg
DECIMAL_PLACES=2
INTEGER_ROUNDING=false
ROUNDING_RULE=保留两位小数，不取整
SCALE_VERIFICATION_STATUS=BUSINESS_CONFIRMED
SCALE_VERIFICATION_STATEMENT=称重设备均已检定
SCALE_CALIBRATION_AUTHORITY=NOT_COLLECTED_OUTSIDE_CURRENT_PREDICTION_SCOPE
CALIBRATION_CERTIFICATE_CUSTODY_ROLE=OUT_OF_SCOPE

BUSINESS_REPORTED_LATE_ENTRY_SCENARIO=NOT_APPLICABLE
MISSING_DAY_RULE=当日无记录表示当日无采摘
FINAL_CONFIRMATION_EVENT=扫码称重完成
FINAL_CONFIRMATION_TIMING=IMMEDIATE
POST_CONFIRMATION_MODIFICATION_ALLOWED=false
POST_CONFIRMATION_DELETION_ALLOWED=false
CORRECTION_AFTER_CONFIRMATION_SUPPORTED=false
VOID_AFTER_CONFIRMATION_SUPPORTED=false

SEASON_START_MONTH_DAY=08-01
SEASON_END_MONTH_DAY=06-30
BOUNDARY_INCLUSIVITY=起止日期均包含
SEASON_START_YEAR=产季名称中的前一年
SEASON_END_YEAR=产季名称中的后一年
2024~2025产季=2024-08-01至2025-06-30
2025~2026产季=2025-08-01至2026-06-30
JULY_AUTOMATIC_SEASON_ASSIGNMENT=false
UNMAPPED_DATE_POLICY=PENDING
```

These are confirmed business inputs for the workpaper. Tare method, formal
correction/void policy, and technical system capability are not inferred from
these statements.

## Season handling draft

```text
SOURCE_EFFECTIVE_SEASON=2024~2025产季起
SEASON_EXACT_DATE_BOUNDARIES=BUSINESS_CONFIRMED_08-01_TO_06-30_INCLUSIVE
```

The same inclusive cross-year rule is applied to later seasons. July remains
unmapped and its assignment or exception correction is pending.

## Evidence gap register

| Gap or decision field | Current draft state | Required later evidence |
| --- | --- | --- |
| `SOURCE_VERSION` | `NOT_PROVIDED` | Governed source version identity. |
| `SOURCE_SNAPSHOT_REFERENCE` | `NOT_ISSUED` | Immutable, non-sensitive snapshot identity. |
| `SCHEMA_VERSION` | `NOT_PROVIDED` | Source schema version. |
| `SCHEMA_HASH` | `NOT_ISSUED` | Non-sensitive schema hash. |
| `ATTESTATION_VERSION` | `NOT_PROVIDED` | Versioned source attestation. |
| `ATTESTATION_EFFECTIVE_AT` | `NOT_PROVIDED` | Attestation effective timestamp. |
| `ATTESTATION_HASH` | `NOT_ISSUED` | Hash of the governed attestation. |
| `TARE_ALREADY_DEDUCTED` | `BUSINESS_CONFIRMED=true` | Formal tare method remains `NOT_PROVIDED`. |
| `TARE_POLICY` | `BUSINESS_CONFIRMED_TARE_ALREADY_DEDUCTED_METHOD_NOT_PROVIDED` | Formal tare handling evidence if required. |
| `SCALE_PRECISION` | `BUSINESS_CONFIRMED_0.01_KG` | Formal source-attestation binding. |
| `SCALE_CALIBRATION_AUTHORITY` | `NOT_COLLECTED_OUTSIDE_CURRENT_PREDICTION_SCOPE` | Outside current prediction scope; no certificate details are collected. |
| `DECIMAL_PLACES` | `BUSINESS_CONFIRMED=2` | Formal decimal evidence if required. |
| `INTEGER_ROUNDING` | `BUSINESS_CONFIRMED=false` | Formal rounding evidence if required. |
| `DECIMAL_PRECISION_AND_ROUNDING` | `BUSINESS_CONFIRMED_2_DECIMAL_PLACES_NO_INTEGER_ROUNDING` | Formal source-attestation binding. |
| `BUSINESS_REPORTED_LATE_ENTRY_SCENARIO` | `BUSINESS_CONFIRMED=NOT_APPLICABLE` | Technical late-entry and visibility rule remains unprovided. |
| `LATE_ENTRY_RULE` | `BUSINESS_REPORTED_NOT_APPLICABLE_TECHNICAL_RULE_NOT_PROVIDED` | Technical late-entry and visibility evidence. |
| `MISSING_DAY_RULE` | `BUSINESS_CONFIRMED=当日无记录表示当日无采摘` | Formal missing-day evidence. |
| `MISSING_DAY_RULE_EVIDENCE` | `BUSINESS_CONFIRMED_FORMAL_EVIDENCE_PENDING` | Formal source and visibility evidence. |
| `CORRECTION_RULE` | `NOT_PROVIDED` | Formal correction rule. |
| `VOID_RULE` | `NOT_PROVIDED` | Formal void rule. |
| `FINAL_CONFIRMATION_EVENT` | `BUSINESS_CONFIRMED=扫码称重完成` | Formal final-confirmation evidence. |
| `FINAL_CONFIRMATION_TIMING` | `BUSINESS_CONFIRMED=IMMEDIATE` | Formal final-confirmation evidence. |
| `FINAL_CONFIRMATION_RULE` | `BUSINESS_CONFIRMED_EVENT_AND_TIMING_FORMAL_EVIDENCE_PENDING` | Formal confirmation rule. |
| `POST_CONFIRMATION_MODIFICATION_ALLOWED` | `BUSINESS_CONFIRMED=false` | Technical capability evidence remains pending. |
| `POST_CONFIRMATION_DELETION_ALLOWED` | `BUSINESS_CONFIRMED=false` | Technical capability evidence remains pending. |
| `CORRECTION_AFTER_CONFIRMATION_SUPPORTED` | `BUSINESS_CONFIRMED=false` | Technical capability evidence remains pending. |
| `VOID_AFTER_CONFIRMATION_SUPPORTED` | `BUSINESS_CONFIRMED=false` | Technical capability evidence remains pending. |
| `REVISION_POLICY_VERSION` | `NOT_PROVIDED` | Versioned revision policy. |
| `WITHDRAWAL_POLICY_VERSION` | `NOT_PROVIDED` | Versioned withdrawal policy. |
| `VOID_PROPAGATION_POLICY_VERSION` | `NOT_PROVIDED` | Versioned void propagation policy. |
| `SEASON_BOUNDARY_RULE` | `BUSINESS_CONFIRMED_08-01_TO_06-30_INCLUSIVE` | Formal calendar-rule binding. |
| `SEASON_EXACT_DATE_BOUNDARIES` | `BUSINESS_CONFIRMED_08-01_TO_06-30_INCLUSIVE` | Formal calendar-rule binding. |
| `JULY_AUTOMATIC_SEASON_ASSIGNMENT` | `BUSINESS_CONFIRMED=false` | No automatic July assignment. |
| `UNMAPPED_DATE_POLICY` | `PENDING` | Separately authorized July/exception-date decision. |
| `COVERAGE_SEASON_COUNT` | `NOT_PROVIDED` | Aggregate coverage statistic. |
| `COVERAGE_FARM_COUNT` | `NOT_PROVIDED` | Aggregate coverage statistic. |
| `COVERAGE_SUBFARM_COUNT` | `NOT_PROVIDED` | Aggregate coverage statistic. |
| `COVERAGE_VARIETY_COUNT` | `NOT_PROVIDED` | Aggregate coverage statistic. |
| `FIRST_HARVEST_BUSINESS_DATE` | `NOT_PROVIDED` | Aggregate coverage boundary. |
| `LAST_HARVEST_BUSINESS_DATE` | `NOT_PROVIDED` | Aggregate coverage boundary. |
| `SOURCE_ROW_COUNT` | `NOT_PROVIDED` | Declared source metadata only; not S2 accepted row count. |
| `MISSING_DAY_COUNT` | `NOT_PROVIDED` | Aggregate quality statistic. |
| `MISSING_DATA_PROPORTION` | `NOT_PROVIDED` | Aggregate quality statistic. |

The source export time, file name or export ID, file hash, row count, first and
last harvest dates, coverage counts, and missing-day count remain pending
machine-generated snapshot metadata. They are not delayed to S2 and do not
require manual business-user entry.

The following identities are deliberately not issued or calculated:

```text
Q2C_DECISION_HASH=NOT_ISSUED
SCHEMA_HASH=NOT_ISSUED
SOURCE_SNAPSHOT_HASH=NOT_ISSUED
ATTESTATION_HASH=NOT_ISSUED
```

## Current boundary and authorization

```text
BUSINESS_REPORTED_ERROR_SCENARIO=NOT_OBSERVED
BUSINESS_REPORTED_DUPLICATE_SCENARIO=CONTROLLED_BY_QR_WORKFLOW
BUSINESS_REPORTED_LATE_ENTRY_SCENARIO=NOT_APPLICABLE
FORMAL_CORRECTION_POLICY=NOT_PROVIDED
FORMAL_VOID_POLICY=NOT_PROVIDED
SOURCE_SNAPSHOT_METADATA_STATUS=PENDING
SOURCE_SNAPSHOT_METADATA_ENTRY_MODE=MACHINE_GENERATED
MANUAL_BUSINESS_USER_ENTRY_REQUIRED=false

REAL_BUSINESS_ROW_LEVEL_DATA_READ=false
REAL_BUSINESS_ROW_LEVEL_DATA_IMPORTED=false
TEST_DATA_ACCESSED=false
EXTERNAL_HOLDOUT_DATA_ACCESSED=false
PRODUCTION_DATABASE_ACCESSED=false
LOCAL_BUSINESS_DATABASE_ACCESSED=false
```

The business-reported statements are not formal correction or void evidence.
This gap register does not authorize S1 acceptance, S2, TEST, external holdout,
or any production change.
