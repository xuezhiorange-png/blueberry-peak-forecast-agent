# Q2C Physical Alignment Evidence Status

## Current evidence state

    EVIDENCE_RECORD_ID=V0_3_S1_Q2C_PHYSICAL_ALIGNMENT_EVIDENCE
    EVIDENCE_RECORD_STATUS=ISSUED_PENDING_INDEPENDENT_REVIEW
    CURRENT_Q2C_PHYSICAL_ALIGNMENT_STATUS=PROVEN_EXACT_PENDING_INDEPENDENT_REVIEW
    CURRENT_Q2C_OUTCOME=PROVEN_EXACT
    Q2C_DECISION_STATUS=ISSUED_PENDING_INDEPENDENT_REVIEW
    Q2C_DECISION_HASH=c7feccd6791b6e9879f82c034552e53d5cc96922314cffa4d21fe5ee1e5d0e18
    INDEPENDENT_REVIEW_STATUS=NOT_STARTED
    BUSINESS_SOURCE_ATTESTATION_VERSION=source-002-q2c-business-source-attestation-v1
    BUSINESS_SOURCE_ATTESTATION_HASH=09a1ccc02036d353ab1fb8cd7a25edcdc0458a736fec510cd1c3711f51137be2

Business-provided physical facts are reconciled from the Q2C and measurement
workpapers and are now bound by the issued Q2C attestation and decision. The
issuance remains pending independent review:

```text
BUSINESS_PHYSICAL_FACT_PRESENT=true
FORMAL_Q2C_ATTESTATION_MISSING=false
Q2C_DECISION_NOT_ISSUED=false
FORMAL_Q2C_ATTESTATION_ISSUED=true
FORMAL_Q2C_DECISION_ISSUED=true
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
Q2C_ACCEPTED=false
CANONICAL_Q2C_GATE_STATUS=BLOCKED
SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=true
CURRENT_CANONICAL_GATE_PASS_COUNT=4
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=13
```

The following fields are now populated and bound by the issued Q2C package:

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
    TRANSFORMATION_AUTHORITY=NONE_REQUIRED
    TRANSFORMATION_HASH=NOT_APPLICABLE

## Fail-closed interpretation

This status record records the issued target decision and PROVEN_EXACT outcome;
it does not constitute independent acceptance or canonical gate closeout. The V0.3 profile
does not require reconstructing a theoretical pre-weigh farm-pick weight;
transport, storage, post-harvest, tare-method and device-metrology details are
optional evidence for this label profile. Missing observations remain missing
and no numeric or percentage value is issued.

The six-dimensional decision was recomputed from one governed source
attestation and cohort package. The current Q2C state is issued pending
independent review; the canonical Q2C gate remains BLOCKED and this record does
not convert the state to accepted, FAIL, NOT_FEASIBLE, or NOT_APPLICABLE.

## Authority

    Q2C_AUTHORITY=docs/forecast-quality/q2c-physical-target-equivalence-contract.md
    Q2C_AUTHORITY_STATUS=ACCEPTED_DESIGN_NOT_IMPLEMENTED
    REQUIRED_CANONICAL_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
    PLOT_SUPPORTED=false
