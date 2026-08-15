# Coverage and Data-Quality Threshold Evidence Status

## Current evidence state

    EVIDENCE_RECORD_ID=V0_3_S1_THRESHOLD_DECISION_EVIDENCE
    CURRENT_MAIN_REVALIDATED_SHA=74a42136b29d6c43780f92c84e59fd6f8ac26558
    EVIDENCE_RECORD_STATUS=DATA_QUALITY_THRESHOLD_POLICY_ACCEPTED_CANONICAL_GATE_CLOSED
    CURRENT_MINIMUM_COVERAGE_THRESHOLD_STATUS=PASS
    CURRENT_DATA_QUALITY_THRESHOLD_STATUS=PASS
    MINIMUM_COVERAGE_THRESHOLD_DECISION=ISSUED_AND_INDEPENDENTLY_REVIEWED
    MINIMUM_COVERAGE_THRESHOLD_VALUE=0.900000
    DATA_QUALITY_THRESHOLD_DECISION=ISSUED_AND_INDEPENDENTLY_REVIEWED
    DATA_QUALITY_PRIMARY_VALID_COVERAGE_THRESHOLD=1.000000
    DATA_QUALITY_MISSING_PROPORTION_THRESHOLD=0.000000
    THRESHOLD_POLICY_VERSION=v0-3-s1-minimum-coverage-threshold-v1
    THRESHOLD_ARTIFACT_HASH=a9361145eaa04e93e6b7bc3a4e4faa7a42c542b29de4978988658f53fa11f692
    INDEPENDENT_REVIEW_STATUS=PASS
    INDEPENDENT_REVIEW_ID=4937929668
    INDEPENDENT_REVIEWED_HEAD=5775e908cfe072fa962c99e822901b7157128418
    EXACT_HEAD_CI_RUN_ID=31806575112
    EXACT_HEAD_CI_STATUS=completed
    EXACT_HEAD_CI_CONCLUSION=success
    DATA_QUALITY_POLICY_VERSION=v0-3-s1-data-quality-threshold-policy-v1
    DATA_QUALITY_OWNER_DECISION_SHA256=11e810f4385965f173c6a269d08a1469f6eb4f6173610d272b4ecc09b2171969
    DATA_QUALITY_INDEPENDENT_REVIEW_ID=4943327077
    DATA_QUALITY_REVIEWED_HEAD=a7bdff6101d724d3413b0fa3d097c240b236326f
    DATA_QUALITY_EXACT_HEAD_CI_RUN_ID=31872490353
    DATA_QUALITY_EXACT_HEAD_CI_STATUS=completed
    DATA_QUALITY_EXACT_HEAD_CI_CONCLUSION=success
    MINIMUM_COVERAGE_POLICY_IS_DATA_QUALITY_POLICY=false
    S3_REPORTING_FLOOR_IS_DATA_QUALITY_THRESHOLD=false
    SOURCE_002_STATISTICS_USED_TO_INFER_DATA_QUALITY_POLICY=false

The S1 minimum-coverage policy is supplied by its own versioned owner decision
record and independently reviewed on the exact PR #219 head. The separate
data-quality policy is now also issued, payload-bound, independently reviewed,
and accepted for its standalone canonical gate. No Source 002 rowset or
data-quality measurement result has been executed or inferred from repository
fixtures, code, or S3 reporting behavior.

The following is an existing S3 reporting fact only and is not an S1
acceptance threshold:

    MIN_COMPARABLE_ROWS_FOR_REPORTING=10
    MIN_COMPARABLE_ROWS_IS_S3_REPORTING_FLOOR=true
    MIN_COMPARABLE_ROWS_IS_S1_MINIMUM_COVERAGE_THRESHOLD=false

## Fail-closed rule

The minimum-coverage and data-quality gates are closed only because each has
its own versioned owner policy, payload hash, independent review, and
exact-head CI evidence. Closing the data-quality policy gate means the policy
is accepted; it does not mean Source 002 has passed that policy. This record
does not authorize metric execution.

## Authority

    AUTHORITY_CONTRACT=docs/v0-3/s1/metric-coverage-and-quality-contract.md
    S3_AUTHORITY=docs/forecast-quality/s3-quality-metrics-contract.md
