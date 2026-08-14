# Coverage and Data-Quality Threshold Evidence Status

## Current evidence state

    EVIDENCE_RECORD_ID=V0_3_S1_THRESHOLD_DECISION_EVIDENCE
    CURRENT_MAIN_REVALIDATED_SHA=e77aff78f74740dde0d9b0e612e661afb0e6e0db
    EVIDENCE_RECORD_STATUS=PARTIAL_DATA_QUALITY_THRESHOLD_REMAINING
    CURRENT_MINIMUM_COVERAGE_THRESHOLD_STATUS=PASS
    CURRENT_DATA_QUALITY_THRESHOLD_STATUS=BLOCKED
    MINIMUM_COVERAGE_THRESHOLD_DECISION=ISSUED_AND_INDEPENDENTLY_REVIEWED
    MINIMUM_COVERAGE_THRESHOLD_VALUE=0.900000
    DATA_QUALITY_THRESHOLD_DECISION=NOT_ISSUED
    DATA_QUALITY_THRESHOLD_VALUE=NOT_PROVIDED
    THRESHOLD_POLICY_VERSION=v0-3-s1-minimum-coverage-threshold-v1
    THRESHOLD_ARTIFACT_HASH=a9361145eaa04e93e6b7bc3a4e4faa7a42c542b29de4978988658f53fa11f692
    INDEPENDENT_REVIEW_STATUS=PASS
    INDEPENDENT_REVIEW_ID=4937929668
    INDEPENDENT_REVIEWED_HEAD=5775e908cfe072fa962c99e822901b7157128418
    EXACT_HEAD_CI_RUN_ID=31806575112
    EXACT_HEAD_CI_STATUS=completed
    EXACT_HEAD_CI_CONCLUSION=success

The S1 minimum-coverage policy is now supplied by the versioned owner decision
record and independently reviewed on the exact PR #219 head. The data-quality
threshold policy remains unissued and blocked. No percentage, count, quality
conclusion, or acceptance threshold is inferred from repository fixtures, code,
or S3 reporting behavior.

The following is an existing S3 reporting fact only and is not an S1
acceptance threshold:

    MIN_COMPARABLE_ROWS_FOR_REPORTING=10
    MIN_COMPARABLE_ROWS_IS_S3_REPORTING_FLOOR=true
    MIN_COMPARABLE_ROWS_IS_S1_MINIMUM_COVERAGE_THRESHOLD=false

## Fail-closed rule

The minimum-coverage gate is closed only because its owner policy, payload
hash, independent review, and exact-head CI evidence are present. The
data-quality gate remains BLOCKED until its own approved policy and review are
available. This record does not authorize metric execution.

## Authority

    AUTHORITY_CONTRACT=docs/v0-3/s1/metric-coverage-and-quality-contract.md
    S3_AUTHORITY=docs/forecast-quality/s3-quality-metrics-contract.md
