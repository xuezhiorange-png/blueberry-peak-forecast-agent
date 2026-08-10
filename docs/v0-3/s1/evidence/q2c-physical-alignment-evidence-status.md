# Q2C Physical Alignment Evidence Status

## Current evidence state

    EVIDENCE_RECORD_ID=V0_3_S1_Q2C_PHYSICAL_ALIGNMENT_EVIDENCE
    EVIDENCE_RECORD_STATUS=BLOCKED
    CURRENT_Q2C_PHYSICAL_ALIGNMENT_STATUS=BLOCKED
    CURRENT_Q2C_OUTCOME=BLOCKED_BY_MISSING_BUSINESS_ATTESTATION
    Q2C_DECISION_STATUS=NOT_ISSUED
    Q2C_DECISION_HASH=NOT_ISSUED
    INDEPENDENT_REVIEW_STATUS=NOT_STARTED

Business-provided physical facts are now reconciled from the Q2C and
measurement workpapers. They remain draft/business facts rather than a formal
Q2C attestation or decision:

```text
BUSINESS_PHYSICAL_FACT_PRESENT=true
FORMAL_Q2C_ATTESTATION_MISSING=true
Q2C_DECISION_NOT_ISSUED=true
STATUS_RECONCILIATION_APPLIED=true
FACT_LAYER_RECONCILED_FROM=docs/v0-3/s1/workpapers/q2c-target-decision-draft.md;docs/v0-3/s1/workpapers/source-measurement-and-finalization-rules-draft.md
V0_3_RECORDED_LABEL_PROFILE=RECORDED_BUSINESS_LABEL
BUSINESS_DECISION_ID=V0_3_RECORDED_HARVEST_LABEL_BOUNDARY
RECORDED_NET_WEIGHT_IS_BUSINESS_TRUTH=true
V0_3_ACTUAL_LABEL_MEASUREMENT_EVENT=VALID_FIELD_SCAN_WEIGH_RECORD
V0_3_ACTUAL_LABEL_QUANTITY_BASIS=RECORDED_MARKETABLE_NET_WEIGHT
V0_3_ACTUAL_LABEL_UNIT=KG
PRE_WEIGH_RECONSTRUCTION_REQUIRED=false
PRE_WEIGH_TRANSPORT_REQUIRED_FOR_LABEL_ELIGIBILITY=false
PRE_WEIGH_STORAGE_REQUIRED_FOR_LABEL_ELIGIBILITY=false
PRE_WEIGH_POSTHARVEST_LOSS_REQUIRED_FOR_LABEL_ELIGIBILITY=false
TARE_METHOD_REQUIRED_FOR_LABEL_ELIGIBILITY=false
SCALE_DEVICE_PRECISION_REQUIRED_FOR_LABEL_ELIGIBILITY=false
SCALE_CALIBRATION_AUTHORITY_REQUIRED_FOR_LABEL_ELIGIBILITY=false
FORECAST_SIDE_TARGET_BINDING_CHANGED=false
```

The following fields are now populated at the business-fact layer; the formal Q2C artifact remains absent:

    PHYSICAL_EVENT=田间采收点首次有效扫码称重
    QUANTITY_BASIS=商品果净重
    QUANTITY_UNIT=kg
    WEIGHING_POINT=田间采摘点
    MARKETABILITY_BOUNDARY=仅统计商品果
    FIELD_SORTING_RULE=田间剔除的非商品果不计入
    PACKHOUSE_SORTING_RULE=加工厂后续分选不追溯调整
    REJECTED_FRUIT_RULE=加工厂拒收或退货不追溯调整
    POST_HARVEST_BOUNDARY=加工厂后续分选、拒收或退货不追溯调整
    FARM_LOCAL_TIME_POLICY=Asia/Shanghai
    CANONICAL_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
    TRANSFORMATION_AUTHORITY=NOT_FORMALIZED
    TRANSFORMATION_HASH=NOT_ISSUED

## Fail-closed interpretation

This status record does not select a target, prove Q2C equivalence, or
substitute factory receipt for the governed recorded label. The V0.3 profile
does not require reconstructing a theoretical pre-weigh farm-pick weight;
transport, storage, post-harvest, tare-method and device-metrology details are
optional evidence for this label profile. Missing observations remain missing
and no numeric or percentage value is issued.

The six-dimensional decision must be recomputed from one governed source
attestation and cohort package. Until that package is supplied, the only
current state is BLOCKED; this record does not convert the state to FAIL,
NOT_FEASIBLE, or NOT_APPLICABLE.

## Authority

    Q2C_AUTHORITY=docs/forecast-quality/q2c-physical-target-equivalence-contract.md
    Q2C_AUTHORITY_STATUS=ACCEPTED_DESIGN_NOT_IMPLEMENTED
    REQUIRED_CANONICAL_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
    PLOT_SUPPORTED=false
