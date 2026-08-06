# V0.3-S1 Business Source Attestation Draft

## Workpaper identity and status

```text
WORKPAPER_ID=V0_3_S1_BUSINESS_SOURCE_ATTESTATION_DRAFT
BASE_MAIN_SHA=0d4aa3f6dc90f9014bbcf43aa73e2bb2248d16aa
DRAFT_STATUS=INCOMPLETE_NOT_SCHEMA_VALID
BUSINESS_SOURCE_ATTESTATION_JSON=NOT_CREATED
SOURCE_AUTHORITY_STATUS=NOT_ISSUED
SOURCE_ATTESTATION_STATUS=NOT_ISSUED
CURRENT_SOURCE_AUTHORITY_BINDING_STATUS=BLOCKED
CURRENT_SOURCE_COHORT_FREEZE_STATUS=BLOCKED
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

## Source authority fields not yet issued

```text
SOURCE_VERSION=NOT_PROVIDED
SOURCE_SNAPSHOT_REFERENCE=NOT_ISSUED
SCHEMA_VERSION=NOT_PROVIDED
SCHEMA_HASH=NOT_ISSUED
ATTESTATION_VERSION=NOT_PROVIDED
ATTESTATION_EFFECTIVE_AT=NOT_PROVIDED
ATTESTATION_HASH=NOT_ISSUED

TARE_POLICY=NOT_PROVIDED
SCALE_PRECISION=NOT_PROVIDED
SCALE_CALIBRATION_AUTHORITY=NOT_PROVIDED
DECIMAL_PRECISION_AND_ROUNDING=NOT_PROVIDED

SEASON_EXACT_DATE_BOUNDARIES=NOT_PROVIDED
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
FORMAL_FINAL_CONFIRMATION_RULE=NOT_PROVIDED
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
policy identity is signed or calculated by this draft.
