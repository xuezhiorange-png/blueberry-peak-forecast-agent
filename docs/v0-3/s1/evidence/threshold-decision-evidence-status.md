# Coverage and Data-Quality Threshold Evidence Status

## Current evidence state

    EVIDENCE_RECORD_ID=V0_3_S1_THRESHOLD_DECISION_EVIDENCE
    EVIDENCE_RECORD_STATUS=BLOCKED
    CURRENT_MINIMUM_COVERAGE_THRESHOLD_STATUS=BLOCKED
    CURRENT_DATA_QUALITY_THRESHOLD_STATUS=BLOCKED
    MINIMUM_COVERAGE_THRESHOLD_DECISION=NOT_ISSUED
    MINIMUM_COVERAGE_THRESHOLD_VALUE=NOT_PROVIDED
    DATA_QUALITY_THRESHOLD_DECISION=NOT_ISSUED
    DATA_QUALITY_THRESHOLD_VALUE=NOT_PROVIDED
    THRESHOLD_POLICY_VERSION=NOT_PROVIDED
    THRESHOLD_ARTIFACT_HASH=NOT_ISSUED
    INDEPENDENT_REVIEW_STATUS=NOT_STARTED

No approved S1 minimum-coverage or data-quality threshold authority was
provided. No percentage, count, quality conclusion, or acceptance threshold
is inferred from repository fixtures, code, or S3 reporting behavior.

The following is an existing S3 reporting fact only and is not an S1
acceptance threshold:

    MIN_COMPARABLE_ROWS_FOR_REPORTING=10
    MIN_COMPARABLE_ROWS_IS_S3_REPORTING_FLOOR=true
    MIN_COMPARABLE_ROWS_IS_S1_MINIMUM_COVERAGE_THRESHOLD=false

## Fail-closed rule

Until an approved threshold decision is supplied and independently reviewed,
the minimum-coverage and data-quality gates remain BLOCKED. This record does
not issue a pass/fail result and does not authorize metric execution.

## Authority

    AUTHORITY_CONTRACT=docs/v0-3/s1/metric-coverage-and-quality-contract.md
    S3_AUTHORITY=docs/forecast-quality/s3-quality-metrics-contract.md
