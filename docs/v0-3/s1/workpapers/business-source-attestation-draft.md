# V0.3-S1 Business Source Attestation Draft

## Workpaper identity and status

```text
WORKPAPER_ID=V0_3_S1_BUSINESS_SOURCE_ATTESTATION_DRAFT
BASE_MAIN_SHA=91fff1fb976cfdbbdc59807537e40dde37364b75
DRAFT_STATUS=INCOMPLETE_NOT_SCHEMA_VALID
BUSINESS_SOURCE_ATTESTATION_SCHEMA_ALIGNMENT_STATUS=ALIGNED_AFTER_TARGETED_CORRECTION_PENDING_INDEPENDENT_REVIEW
BUSINESS_SOURCE_ATTESTATION_JSON=NOT_CREATED
SOURCE_AUTHORITY_STATUS=NOT_ISSUED
SOURCE_ATTESTATION_STATUS=NOT_ISSUED
SOURCE_MEASUREMENT_BUSINESS_RULES_STATUS=CONFIRMED
SOURCE_FINALIZATION_BUSINESS_RULES_STATUS=CONFIRMED
SEASON_CALENDAR_BUSINESS_RULE_STATUS=CONFIRMED
SOURCE_SNAPSHOT_METADATA_STATUS=PREPARED_SOURCE_002_AGGREGATE_ONLY_PENDING_FORMAL_ATTESTATION
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

The formal source-authority identity uses `source_owner_role` as its canonical
owner field. The aligned Schema also requires the source schema identity,
opaque snapshot reference, applicability effective time, coverage scope,
revision policy, and withdrawal/void policy. This alignment does not create an
attestation, issue any source value or hash, or change the blocked evidence
status. The targeted correction also makes the attestation and cohort opaque
reference primitives reject URL, drive-letter, relative, absolute, and other
slash-delimited storage locators while retaining non-sensitive governed
identities. The correction remains pending independent review.

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
QUANTITY_BASIS=商品果净重
TARE_DEDUCTION_RESULT=筐重已扣除
TARE_DEDUCTION_METHOD=NOT_PROVIDED

SCALE_PRECISION=0.001 kg
SCALE_PRECISION_BUSINESS_RULE_STATUS=CONFIRMED
SCALE_PRECISION_FORMAL_EVIDENCE_STATUS=PENDING
DECIMAL_PLACES=3
INTEGER_ROUNDING=false
ROUNDING_RULE=保留三位小数，不取整
SCALE_VERIFICATION_STATUS=BUSINESS_CONFIRMED
SCALE_VERIFICATION_STATEMENT=称重设备均已检定
SCALE_CALIBRATION_AUTHORITY=NOT_COLLECTED_OUTSIDE_CURRENT_PREDICTION_SCOPE
CALIBRATION_CERTIFICATE_CUSTODY_ROLE=OUT_OF_SCOPE

BUSINESS_REPORTED_LATE_ENTRY_SCENARIO=NOT_APPLICABLE
BUSINESS_REPORTED_NO_RECORD_INTERPRETATION=当日无记录表示当日无采摘
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
MISSING_DAY_NUMERIC_IMPUTATION_ALLOWED=false
NO_RECORD_TO_ZERO_MAPPING_STATUS=BLOCKED_PENDING_SOURCE_COMPLETENESS_EVIDENCE
FORMAL_MISSING_DAY_RULE_STATUS=PENDING
FINAL_CONFIRMATION_EVENT=扫码称重完成
FINAL_CONFIRMATION_TIMING=IMMEDIATE
BUSINESS_RULE_POST_CONFIRMATION_MODIFICATION_ALLOWED=false
BUSINESS_RULE_POST_CONFIRMATION_DELETION_ALLOWED=false
BUSINESS_RULE_CORRECTION_AFTER_CONFIRMATION_SUPPORTED=false
BUSINESS_RULE_VOID_AFTER_CONFIRMATION_SUPPORTED=false
```

These are confirmed business statements recorded for the draft workpaper. They
do not issue a formal scale certificate, tare policy, technical write-control
proof, correction policy, void policy, missing-day policy, or accepted source
attestation. “补录不存在” applies only to the current business-reported
scenario and must not be expanded into an absolute software or database
capability claim. The prefixed `BUSINESS_RULE_` fields are business statements,
not database permissions, interface capabilities, administrator authority, or
formal correction, void, or revision policy.

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

DECIMAL_PRECISION_AND_ROUNDING=BUSINESS_CONFIRMED_3_DECIMAL_PLACES_NO_INTEGER_ROUNDING
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
FORMAL_CORRECTION_POLICY=NOT_PROVIDED
FORMAL_VOID_POLICY=NOT_PROVIDED
FORMAL_REVISION_POLICY=NOT_PROVIDED
FORMAL_FINAL_CONFIRMATION_RULE=BUSINESS_CONFIRMED_SCAN_COMPLETE_IMMEDIATE_FORMAL_EVIDENCE_PENDING
```

`NOT_OBSERVED` and the QR-workflow statement are business-reported context
only. They do not prove that errors or duplicates are impossible and do not
replace formal correction, void, late-entry, revision, missing-day, or
final-confirmation rules. The `BUSINESS_RULE_` post-confirmation fields remain
business statements only; they do not establish technical write controls or
administrative permissions. `MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO` is the
fail-closed interpretation until source completeness evidence is available.

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
