# V0.3-S1 Q2C Target Decision Draft

## Workpaper identity and status

```text
WORKPAPER_ID=V0_3_S1_Q2C_TARGET_DECISION_DRAFT
BASE_MAIN_SHA=91fff1fb976cfdbbdc59807537e40dde37364b75
WORKPAPER_STATUS=DRAFT_ONLY
SOURCE_MEASUREMENT_BUSINESS_RULES_STATUS=CONFIRMED
SOURCE_FINALIZATION_BUSINESS_RULES_STATUS=CONFIRMED
SEASON_CALENDAR_BUSINESS_RULE_STATUS=CONFIRMED
SOURCE_SNAPSHOT_METADATA_STATUS=PENDING
SOURCE_SNAPSHOT_METADATA_ENTRY_MODE=MACHINE_GENERATED
MANUAL_BUSINESS_USER_ENTRY_REQUIRED=false
CURRENT_Q2C_PHYSICAL_ALIGNMENT_STATUS=BLOCKED
CURRENT_V0_3_S1_ACCEPTANCE_STATUS=BLOCKED
CURRENT_V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
BUSINESS_SOURCE_ATTESTATION_JSON_CREATED=false
Q2C_DECISION_STATUS=NOT_ISSUED
Q2C_DECISION_HASH=NOT_ISSUED
```

This workpaper records only the business information confirmed in the current
planning conversation. It is not a signed source attestation, does not issue a
Q2C decision, and does not close any S1 Gate.

## Draft target and physical meaning

```text
TARGET_PHYSICAL_EVENT=田间商品果完成有效称重
QUANTITY_BASIS=商品果净重
QUANTITY_UNIT=kg
WEIGHING_POINT=田间采摘点
MARKETABILITY_BOUNDARY=仅统计商品果
FIELD_SORTING_RULE=田间剔除的非商品果不计入
PACKHOUSE_SORTING_RULE=加工厂后续分选不追溯调整
REJECTED_FRUIT_RULE=加工厂拒收或退货不追溯调整
FARM_TIMEZONE=Asia/Shanghai
```

The draft target is the field-side marketable-fruit weighing event. Factory
receipt, later packhouse sorting, factory rejection, and returned fruit are not
used to retroactively change this field-side quantity in this draft.

The draft does not assert that the source system has already proven the event,
weighing point, marketability boundary, or post-harvest treatment. Those facts
remain subject to formal source authority and Q2C evidence.

## Confirmed measurement and finalization inputs

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

These inputs are confirmed business statements for this draft only. They do
not issue a formal source attestation, scale certificate, tare method, or
technical proof that the system can never receive a late entry or historical
exception. Formal correction, void, revision, and source-visibility evidence
remains pending.

## Canonical evaluation grain

```text
CANONICAL_GRAIN=
SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE

PLOT_SUPPORTED=false
```

The `果径` source dimension is not part of this target grain. It is retained as
a source dimension for the conversion step described below and is aggregated
before the canonical target quantity is formed.

## Season handling draft

```text
SOURCE_EFFECTIVE_SEASON=2024~2025产季起
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

The calendar rule is a confirmed draft business rule: the start and end dates
are inclusive and later seasons use the same cross-year pattern. July is not
automatically assigned. This workpaper does not decide July ownership,
automatic exclusion, overlap priority, or exception-date correction.

## Q2C closure boundary

The following remain unresolved and prevent a formal Q2C decision:

- formal source authority and attestation;
- formal calibration certificate custody and tare-method evidence where needed;
- formal correction, void, technical late-entry, and source-visibility rules;
- source snapshot, schema, attestation, and decision identities or hashes;
- aggregate coverage and data-quality evidence.

```text
CURRENT_Q2C_PHYSICAL_ALIGNMENT_STATUS=BLOCKED
Q2C_DECISION_STATUS=NOT_ISSUED
Q2C_DECISION_HASH=NOT_ISSUED
SOURCE_SNAPSHOT_METADATA_STATUS=PENDING
SOURCE_SNAPSHOT_METADATA_ENTRY_MODE=MACHINE_GENERATED
MANUAL_BUSINESS_USER_ENTRY_REQUIRED=false
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```
