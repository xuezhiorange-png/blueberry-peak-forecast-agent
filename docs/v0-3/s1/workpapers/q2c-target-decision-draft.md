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
CURRENT_SOURCE_AUTHORITY_BINDING_STATUS=BLOCKED
CURRENT_SOURCE_COHORT_FREEZE_STATUS=BLOCKED
CURRENT_V0_3_S1_ACCEPTANCE_STATUS=BLOCKED
CURRENT_V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
BUSINESS_SOURCE_ATTESTATION_JSON_CREATED=false
Q2C_DECISION_STATUS=NOT_ISSUED
Q2C_DECISION_HASH=NOT_ISSUED
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
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

## V0.3 recorded-business-label boundary correction

```text
BUSINESS_DECISION_ID=V0_3_RECORDED_HARVEST_LABEL_BOUNDARY
V0_3_RECORDED_LABEL_PROFILE=RECORDED_BUSINESS_LABEL
V0_3_ACTUAL_LABEL_BUSINESS_EVENT=HARVEST
V0_3_ACTUAL_LABEL_MEASUREMENT_EVENT=VALID_FIELD_SCAN_WEIGH_RECORD
V0_3_ACTUAL_LABEL_MEASUREMENT_BOUNDARY=RECORDED_VALID_FIELD_SCAN_WEIGH
V0_3_ACTUAL_LABEL_QUANTITY_BASIS=RECORDED_MARKETABLE_NET_WEIGHT
V0_3_ACTUAL_LABEL_SOURCE_OF_TRUTH=GOVERNED_SCAN_WEIGHT_RECORD
V0_3_ACTUAL_LABEL_UNIT=KG
RECORDED_NET_WEIGHT_IS_BUSINESS_TRUTH=true
PRE_MEASUREMENT_WEIGHT_RECONSTRUCTION_REQUIRED=false
PRE_WEIGH_TRANSPORT_REQUIRED_FOR_LABEL_ELIGIBILITY=false
PRE_WEIGH_STORAGE_REQUIRED_FOR_LABEL_ELIGIBILITY=false
PRE_WEIGH_POSTHARVEST_LOSS_REQUIRED_FOR_LABEL_ELIGIBILITY=false
TARE_METHOD_RECONSTRUCTION_REQUIRED=false
TARE_METHOD_REQUIRED_FOR_LABEL_ELIGIBILITY=false
SCALE_DEVICE_PRECISION_REQUIRED_FOR_LABEL_ELIGIBILITY=false
SCALE_CALIBRATION_AUTHORITY_REQUIRED_FOR_LABEL_ELIGIBILITY=false
V0_3_RECORDED_LABEL_BOUNDARY_CORRECTION_APPLIED=true
FORECAST_SIDE_TARGET_BINDING_CHANGED=false
Q2C_ACCEPTED=false
FACTORY_SORTING_RETROACTIVE_ADJUSTMENT=false
FACTORY_REJECTION_RETROACTIVE_ADJUSTMENT=false
FACTORY_RETURN_RETROACTIVE_ADJUSTMENT=false
```

The recorded net weight at the first valid field scan-and-weigh event is the
V0.3 actual-label business truth. Transport, storage, natural loss, and other
pre-record history are not reconstructed into a theoretical plant-removal
weight. The `*_REQUIRED_FOR_LABEL_ELIGIBILITY=false` fields mean
`NOT_REQUIRED_FOR_V0_3_RECORDED_LABEL_ELIGIBILITY`; they do not assert that an
unknown process, method, or device property is false or nonexistent.

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
TARE_ALREADY_DEDUCTED=true
TARE_DEDUCTION_RESULT=筐重已扣除
TARE_DEDUCTION_METHOD=NOT_PROVIDED
TARE_METHOD_REQUIRED_FOR_LABEL_ELIGIBILITY=false
TARE_METHOD_STATUS=NOT_REQUIRED_FOR_V0_3_RECORDED_LABEL_ELIGIBILITY

SOURCE_QUANTITY_PRECISION=0.001 kg
SOURCE_QUANTITY_PRECISION_STATUS=BUSINESS_CONFIRMED_AND_SOURCE_002_OBSERVED
SOURCE_QUANTITY_PRECISION_GAP=false
SOURCE_QUANTITY_DECIMAL_PLACES=3
SOURCE_QUANTITY_INTEGER_ROUNDING=false
SOURCE_QUANTITY_ROUNDING_RULE=保留三位小数，不取整

SCALE_DEVICE_PRECISION=NOT_PROVIDED
SCALE_DEVICE_PRECISION_BUSINESS_RULE_STATUS=NOT_CONFIRMED
SCALE_DEVICE_PRECISION_FORMAL_EVIDENCE_STATUS=PENDING
SCALE_DEVICE_PRECISION_REQUIRED_FOR_LABEL_ELIGIBILITY=false
SCALE_DEVICE_PRECISION_ELIGIBILITY_STATUS=OPTIONAL_METROLOGY_EVIDENCE
SCALE_VERIFICATION_STATUS=BUSINESS_CONFIRMED
SCALE_VERIFICATION_STATEMENT=称重设备均已检定
SCALE_CALIBRATION_AUTHORITY=NOT_COLLECTED_OUTSIDE_CURRENT_PREDICTION_SCOPE
SCALE_CALIBRATION_AUTHORITY_REQUIRED_FOR_LABEL_ELIGIBILITY=false
SCALE_CALIBRATION_AUTHORITY_ELIGIBILITY_STATUS=OPTIONAL_METROLOGY_EVIDENCE
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

These inputs are confirmed business statements for this draft only. The source
quantity precision describes the exported quantity representation and must not
be read as weighing-device precision or scale resolution. They do not issue a
formal source attestation, scale certificate, tare method, or technical proof
that the system can never receive a late entry or historical exception. Formal
correction, void, revision, missing-day, and source-visibility evidence
remains pending. The prefixed `BUSINESS_RULE_` fields are business statements,
not database permissions, interface capabilities, administrator authority, or
formal correction, void, or revision policy.

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
- formal source, coverage, visibility and governance evidence;
- formal correction, void, technical late-entry, and source-visibility rules;
- formal missing-day and no-record completeness evidence;
- source snapshot, schema, attestation, and decision identities or hashes;
- aggregate coverage and data-quality evidence.

The V0.3 recorded-label profile does not make pre-weigh transport, storage,
post-harvest reconstruction, tare method, scale-device precision, or scale
calibration authority hard prerequisites for label eligibility. Those fields
remain optional provenance/metrology evidence when supplied. This correction
does not issue the Q2C decision or bind a forecast-side target.

These unresolved items keep the current Q2C status `BLOCKED` and the decision
status `NOT_ISSUED`.

The business post-confirmation flags are not database or interface capability
claims. Formal policy identities remain unresolved:

```text
FORMAL_CORRECTION_POLICY=NOT_PROVIDED
FORMAL_VOID_POLICY=NOT_PROVIDED
FORMAL_REVISION_POLICY=NOT_PROVIDED
SOURCE_SNAPSHOT_REFERENCE=NOT_ISSUED
SCHEMA_HASH=NOT_ISSUED
ATTESTATION_HASH=NOT_ISSUED
```
