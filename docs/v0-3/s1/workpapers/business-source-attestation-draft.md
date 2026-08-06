# V0.3-S1 Business Source Attestation Draft

## Workpaper identity and status

```text
WORKPAPER_ID=V0_3_S1_BUSINESS_SOURCE_ATTESTATION_DRAFT
BASE_MAIN_SHA=91fff1fb976cfdbbdc59807537e40dde37364b75
DRAFT_STATUS=INCOMPLETE_NOT_SCHEMA_VALID
BUSINESS_SOURCE_ATTESTATION_JSON=NOT_CREATED
SOURCE_AUTHORITY_STATUS=NOT_ISSUED
SOURCE_ATTESTATION_STATUS=NOT_ISSUED
SOURCE_MEASUREMENT_BUSINESS_RULES_STATUS=CONFIRMED
SOURCE_FINALIZATION_BUSINESS_RULES_STATUS=CONFIRMED
SEASON_CALENDAR_BUSINESS_RULE_STATUS=CONFIRMED
SOURCE_SNAPSHOT_METADATA_STATUS=PENDING
SOURCE_SNAPSHOT_METADATA_ENTRY_MODE=MACHINE_GENERATED
MANUAL_BUSINESS_USER_ENTRY_REQUIRED=false
CURRENT_SOURCE_AUTHORITY_BINDING_STATUS=BLOCKED
CURRENT_SOURCE_COHORT_FREEZE_STATUS=BLOCKED
CURRENT_V0_3_S1_COMPLETE=false
CURRENT_V0_3_S1_ACCEPTANCE_STATUS=BLOCKED
V0_3_S1_ACCEPTED=false
BUSINESS_SOURCE_ATTESTATION_JSON_CREATED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

This is a Markdown preparation workpaper only. It is not the governed
`business-source-attestation.json`, is intentionally incomplete, and must not
be treated as a schema-valid attestation or an accepted source identity.

## Confirmed source identity statements

```text
SOURCE_SYSTEM=扫码称重系统
SOURCE_DATASET=田间商品果每日采摘净重汇总
SOURCE_OWNER_ROLE=农场数据负责人
SOURCE_EFFECTIVE_SEASON=2024~2025产季起
SPREADSHEET_IS_INDEPENDENT_SOURCE=false
SPREADSHEET_ROLE=扫码系统导出、汇总或整理副本
```

The spreadsheet role is a provenance statement: a spreadsheet is an export,
summary, or整理副本 of the scan-and-weigh system, not an independent source.
This workpaper does not contain a spreadsheet, scan record, source row, or
source file.

## Confirmed measurement and finalization business rules

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
```

These are confirmed business statements recorded for the draft workpaper. They
do not issue a formal scale certificate, tare policy, technical write-control
proof, correction policy, void policy, or accepted source attestation. “补录不存在”
applies only to the current business-reported scenario and must not be expanded
into an absolute software or database capability claim.

## Confirmed season calendar reference

```text
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

This calendar reference is a confirmed business rule for the draft only. July
ownership, automatic exclusion, overlap priority, and exception-date
correction remain pending.

## Source authority fields and remaining evidence status

```text
SOURCE_VERSION=NOT_PROVIDED
SOURCE_SNAPSHOT_REFERENCE=NOT_ISSUED
SCHEMA_VERSION=NOT_PROVIDED
SCHEMA_HASH=NOT_ISSUED
ATTESTATION_VERSION=NOT_PROVIDED
ATTESTATION_EFFECTIVE_AT=NOT_PROVIDED
ATTESTATION_HASH=NOT_ISSUED

SCALE_PRECISION=BUSINESS_CONFIRMED_0.01_KG
SCALE_CALIBRATION_AUTHORITY=NOT_COLLECTED_OUTSIDE_CURRENT_PREDICTION_SCOPE
DECIMAL_PRECISION_AND_ROUNDING=BUSINESS_CONFIRMED_2_DECIMAL_PLACES_NO_INTEGER_ROUNDING
TARE_POLICY=BUSINESS_CONFIRMED_TARE_ALREADY_DEDUCTED_METHOD_NOT_PROVIDED

SEASON_EXACT_DATE_BOUNDARIES=BUSINESS_CONFIRMED_08-01_TO_06-30_INCLUSIVE
```

The known owner role and source descriptions are not a substitute for formal
owner attestation, source version identity, schema identity, snapshot binding,
or a governed hash.

## Business-reported error scenarios

```text
BUSINESS_REPORTED_ERROR_SCENARIO=NOT_OBSERVED
BUSINESS_REPORTED_DUPLICATE_SCENARIO=CONTROLLED_BY_QR_WORKFLOW
BUSINESS_REPORTED_LATE_ENTRY_SCENARIO=NOT_APPLICABLE
MISSING_DAY_RULE=当日无记录表示当日无采摘
FORMAL_CORRECTION_POLICY=NOT_PROVIDED
FORMAL_VOID_POLICY=NOT_PROVIDED
FORMAL_FINAL_CONFIRMATION_RULE=BUSINESS_CONFIRMED_SCAN_COMPLETE_IMMEDIATE_FORMAL_EVIDENCE_PENDING
POST_CONFIRMATION_MODIFICATION_ALLOWED=false
POST_CONFIRMATION_DELETION_ALLOWED=false
CORRECTION_AFTER_CONFIRMATION_SUPPORTED=false
VOID_AFTER_CONFIRMATION_SUPPORTED=false
```

`NOT_OBSERVED` and the QR-workflow statement are business-reported context
only. They do not prove that errors or duplicates are impossible and do not
replace formal correction, void, late-entry, revision, or final-confirmation
rules.

## Coverage and custody evidence still missing

```text
COVERAGE_SCOPE=NOT_PROVIDED
COVERAGE_SEASON_COUNT=NOT_PROVIDED
COVERAGE_FARM_COUNT=NOT_PROVIDED
COVERAGE_SUBFARM_COUNT=NOT_PROVIDED
COVERAGE_VARIETY_COUNT=NOT_PROVIDED
FIRST_HARVEST_BUSINESS_DATE=NOT_PROVIDED
LAST_HARVEST_BUSINESS_DATE=NOT_PROVIDED
SOURCE_ROW_COUNT=NOT_PROVIDED
MISSING_DAY_COUNT=NOT_PROVIDED
MISSING_DATA_PROPORTION=NOT_PROVIDED

REVISION_POLICY_VERSION=NOT_PROVIDED
WITHDRAWAL_POLICY_VERSION=NOT_PROVIDED
VOID_PROPAGATION_POLICY_VERSION=NOT_PROVIDED
```

No source snapshot, schema hash, attestation hash, coverage statistic, or
policy identity is signed or calculated by this draft. Source export time,
file name or export ID, file hash, row count, date bounds, coverage counts, and
missing-day count remain pending machine-generated snapshot metadata and are not
manually entered here. The confirmed measurement, finalization, and calendar
business rules do not change the blocked source-authority and cohort statuses.
