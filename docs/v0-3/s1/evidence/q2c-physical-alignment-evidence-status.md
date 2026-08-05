# Q2C Physical Alignment Evidence Status

## Current evidence state

    EVIDENCE_RECORD_ID=V0_3_S1_Q2C_PHYSICAL_ALIGNMENT_EVIDENCE
    EVIDENCE_RECORD_STATUS=BLOCKED
    CURRENT_Q2C_PHYSICAL_ALIGNMENT_STATUS=BLOCKED
    CURRENT_Q2C_OUTCOME=BLOCKED_BY_MISSING_BUSINESS_ATTESTATION
    Q2C_DECISION_STATUS=NOT_ISSUED
    Q2C_DECISION_HASH=NOT_ISSUED
    INDEPENDENT_REVIEW_STATUS=NOT_STARTED

No source owner, attestation, source version, measurement record, or source
cohort was supplied. The following fields therefore remain absent rather than
being inferred:

    PHYSICAL_EVENT=NOT_PROVIDED
    QUANTITY_BASIS=NOT_PROVIDED
    QUANTITY_UNIT=NOT_PROVIDED
    WEIGHING_POINT=NOT_PROVIDED
    MARKETABILITY_BOUNDARY=NOT_PROVIDED
    FIELD_SORTING_RULE=NOT_PROVIDED
    PACKHOUSE_SORTING_RULE=NOT_PROVIDED
    REJECTED_FRUIT_RULE=NOT_PROVIDED
    POST_HARVEST_BOUNDARY=NOT_PROVIDED
    FARM_LOCAL_TIME_POLICY=NOT_PROVIDED
    CANONICAL_GRAIN=NOT_PROVIDED
    TRANSFORMATION_AUTHORITY=NOT_PROVIDED
    TRANSFORMATION_HASH=NOT_ISSUED

## Fail-closed interpretation

This status record does not select a target, prove Q2C equivalence, or
substitute factory receipt for farm-pick quantity. Missing observations remain
missing and no numeric or percentage value is issued.

The six-dimensional decision must be recomputed from one governed source
attestation and cohort package. Until that package is supplied, the only
current state is BLOCKED; this record does not convert the state to FAIL,
NOT_FEASIBLE, or NOT_APPLICABLE.

## Authority

    Q2C_AUTHORITY=docs/forecast-quality/q2c-physical-target-equivalence-contract.md
    Q2C_AUTHORITY_STATUS=ACCEPTED_DESIGN_NOT_IMPLEMENTED
    REQUIRED_CANONICAL_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
    PLOT_SUPPORTED=false
