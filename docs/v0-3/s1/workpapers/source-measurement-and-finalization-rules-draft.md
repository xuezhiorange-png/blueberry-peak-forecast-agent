# V0.3-S1 Source Measurement and Finalization Rules Draft

## Workpaper identity and status

```text
WORKPAPER_ID=V0_3_S1_SOURCE_MEASUREMENT_AND_FINALIZATION_RULES_DRAFT
BASE_MAIN_SHA=91fff1fb976cfdbbdc59807537e40dde37364b75
WORKPAPER_STATUS=DRAFT_ONLY
SOURCE_MEASUREMENT_BUSINESS_RULES_STATUS=CONFIRMED
SOURCE_FINALIZATION_BUSINESS_RULES_STATUS=CONFIRMED
SOURCE_SNAPSHOT_METADATA_STATUS=PENDING
SOURCE_SNAPSHOT_METADATA_ENTRY_MODE=MACHINE_GENERATED
MANUAL_BUSINESS_USER_ENTRY_REQUIRED=false

CURRENT_Q2C_PHYSICAL_ALIGNMENT_STATUS=BLOCKED
CURRENT_SOURCE_AUTHORITY_BINDING_STATUS=BLOCKED
CURRENT_SOURCE_COHORT_FREEZE_STATUS=BLOCKED
CURRENT_V0_3_S1_COMPLETE=false
CURRENT_V0_3_S1_ACCEPTANCE_STATUS=BLOCKED
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

This is a Markdown workpaper for confirmed business-rule input only. It is not
the formal source attestation, source snapshot, cohort manifest, or an accepted
Q2C decision. It contains no source export, source row, or source hash.

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
FORECAST_SIDE_TARGET_BINDING_CHANGED=false
```

The recorded net weight is the V0.3 actual-label business truth. The profile
does not reconstruct a theoretical pre-weigh plant-removal weight. The
`*_REQUIRED_FOR_LABEL_ELIGIBILITY=false` values mean
`NOT_REQUIRED_FOR_V0_3_RECORDED_LABEL_ELIGIBILITY`; they do not assert that an
unknown process, tare method, or device property is false or nonexistent.

## Confirmed physical event and quantity

```text
PHYSICAL_EVENT=田间采收点首次有效扫码称重
TARGET_QUANTITY=商品果净重
QUANTITY_UNIT=kg
TARE_ALREADY_DEDUCTED=true
QUANTITY_BASIS=商品果净重
TARE_DEDUCTION_RESULT=筐重已扣除
TARE_DEDUCTION_METHOD=NOT_PROVIDED
TARE_METHOD_STATUS=NOT_REQUIRED_FOR_V0_3_RECORDED_LABEL_ELIGIBILITY
```

The confirmed business meaning is the first valid scan-and-weigh event at the
field harvest point. The quantity is marketable fruit net weight after the
business-reported tare deduction. No fixed basket weight, tare algorithm,
per-basket deduction value, or other field procedure is inferred.

## Source quantity representation and weighing-device evidence

```text
SOURCE_QUANTITY_PRECISION=0.001 kg
SOURCE_QUANTITY_PRECISION_STATUS=BUSINESS_CONFIRMED_AND_SOURCE_002_OBSERVED
SOURCE_QUANTITY_PRECISION_GAP=false
SOURCE_QUANTITY_DECIMAL_PLACES=3
SOURCE_QUANTITY_INTEGER_ROUNDING=false
SOURCE_QUANTITY_ROUNDING_RULE=保留三位小数，不取整

SCALE_DEVICE_PRECISION=NOT_PROVIDED
SCALE_DEVICE_PRECISION_BUSINESS_RULE_STATUS=NOT_CONFIRMED
SCALE_DEVICE_PRECISION_FORMAL_EVIDENCE_STATUS=PENDING
SCALE_DEVICE_PRECISION_ELIGIBILITY_STATUS=OPTIONAL_METROLOGY_EVIDENCE

SCALE_VERIFICATION_STATUS=BUSINESS_CONFIRMED
SCALE_VERIFICATION_STATEMENT=称重设备均已检定
SCALE_CALIBRATION_AUTHORITY=NOT_COLLECTED_OUTSIDE_CURRENT_PREDICTION_SCOPE
SCALE_CALIBRATION_AUTHORITY_ELIGIBILITY_STATUS=OPTIONAL_METROLOGY_EVIDENCE
CALIBRATION_CERTIFICATE_CUSTODY_ROLE=OUT_OF_SCOPE
```

The source quantity fields describe the exported `入库公斤数` representation;
they do not describe scale resolution, minimum division, calibration precision,
or weighing-device precision. The verification statement is a confirmed
business statement, not a certificate or formal source-attestation record. This
workpaper does not invent an inspection institution, certificate number,
inspection date, validity period, custodian, or storage location. The absence
of a device precision value does not weaken the observed three-decimal source
quantity evidence, and the pending device evidence does not mean that the
business verification statement is revoked. Device precision, calibration
authority, tare method, and pre-weigh process details remain optional
provenance/metrology evidence for this V0.3 recorded-label profile; they are not
hard label-eligibility blockers.

## Confirmation, missing-day, and post-confirmation rules

```text
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

“补录不存在” is recorded only as the current business confirmation that the
scenario is not applicable. It is not a claim that the software technically
cannot write a late record, that a database has no write path, that an
administrator has no correction authority, or that a historical anomaly can
never occur. Formal technical evidence for correction, void, revision,
missing-day, and visibility remains pending. The `BUSINESS_RULE_` fields are
business statements only, not database permissions, interface capabilities,
administrator authority, or formal correction, void, or revision policy.
`MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO` prevents a no-record business
interpretation from becoming an automatic numeric zero.

## Source-snapshot metadata boundary

The following metadata is deliberately not read or filled in this workpaper:
source export time, source file name or export ID, source file SHA-256, source
row count, first or last harvest date, farm/subfarm/variety counts, and missing
day count. In a separately authorized source-snapshot preparation stage, a
machine-controlled process will calculate those fields from a governed export.
They are not delayed to S2, are not currently frozen, and do not require manual
business-user entry.

## Formal evidence and authorization boundary

```text
BUSINESS_SOURCE_ATTESTATION_JSON_CREATED=false
SOURCE_VERSION=NOT_PROVIDED
SOURCE_SNAPSHOT_REFERENCE=NOT_ISSUED
SCHEMA_VERSION=NOT_PROVIDED
SCHEMA_HASH=NOT_ISSUED
ATTESTATION_VERSION=NOT_PROVIDED
ATTESTATION_EFFECTIVE_AT=NOT_PROVIDED
ATTESTATION_HASH=NOT_ISSUED
Q2C_DECISION_HASH=NOT_ISSUED
FORMAL_CORRECTION_POLICY=NOT_PROVIDED
FORMAL_VOID_POLICY=NOT_PROVIDED
FORMAL_REVISION_POLICY=NOT_PROVIDED

REAL_BUSINESS_ROW_LEVEL_DATA_READ=false
REAL_BUSINESS_ROW_LEVEL_DATA_IMPORTED=false
SOURCE_EXPORT_FILE_READ=false
SOURCE_HASH_CALCULATION=false
TEST_DATA_ACCESSED=false
EXTERNAL_HOLDOUT_DATA_ACCESSED=false
PRODUCTION_DATABASE_ACCESSED=false
LOCAL_BUSINESS_DATABASE_ACCESSED=false
```

The confirmed business rules do not close Q2C, bind a source authority, freeze
a source cohort, authorize S1 acceptance, authorize S2, or create a formal
attestation.
