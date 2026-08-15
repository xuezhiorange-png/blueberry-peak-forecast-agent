# Coverage and Data-Quality Threshold Evidence Status

## Current evidence state

    EVIDENCE_RECORD_ID=V0_3_S1_THRESHOLD_DECISION_EVIDENCE
    CURRENT_MAIN_REVALIDATED_SHA=74a42136b29d6c43780f92c84e59fd6f8ac26558
    EVIDENCE_RECORD_STATUS=PARTIAL_METRIC_CONTRACT_AND_DOWNSTREAM_REMAINING
    CURRENT_MINIMUM_COVERAGE_THRESHOLD_STATUS=PASS
    CURRENT_DATA_QUALITY_THRESHOLD_STATUS=PASS
    MINIMUM_COVERAGE_THRESHOLD_DECISION=ISSUED_AND_INDEPENDENTLY_REVIEWED
    MINIMUM_COVERAGE_THRESHOLD_VALUE=0.900000
    MINIMUM_COVERAGE_THRESHOLD_POLICY_VERSION=v0-3-s1-minimum-coverage-threshold-v1
    MINIMUM_COVERAGE_THRESHOLD_ARTIFACT_HASH=a9361145eaa04e93e6b7bc3a4e4faa7a42c542b29de4978988658f53fa11f692
    MINIMUM_COVERAGE_INDEPENDENT_REVIEW_ID=4937929668
    MINIMUM_COVERAGE_INDEPENDENT_REVIEWED_HEAD=5775e908cfe072fa962c99e822901b7157128418
    MINIMUM_COVERAGE_EXACT_HEAD_CI_RUN_ID=31806575112
    MINIMUM_COVERAGE_EXACT_HEAD_CI_STATUS=completed
    MINIMUM_COVERAGE_EXACT_HEAD_CI_CONCLUSION=success
    DATA_QUALITY_THRESHOLD_DECISION=ISSUED_AND_INDEPENDENTLY_REVIEWED
    DATA_QUALITY_THRESHOLD_VALUE=1.000000
    DATA_QUALITY_THRESHOLD_POLICY_VERSION=v0-3-s1-data-quality-threshold-policy-v1
    DATA_QUALITY_THRESHOLD_ARTIFACT_HASH=11e810f4385965f173c6a269d08a1469f6eb4f6173610d272b4ecc09b2171969
    DATA_QUALITY_INDEPENDENT_REVIEW_ID=4943325699
    DATA_QUALITY_INDEPENDENT_REVIEWED_HEAD=a7bdff6101d724d3413b0fa3d097c240b236326f
    DATA_QUALITY_EXACT_HEAD_CI_RUN_ID=31872490353
    DATA_QUALITY_EXACT_HEAD_CI_STATUS=completed
    DATA_QUALITY_EXACT_HEAD_CI_CONCLUSION=success

The S1 minimum-coverage and data-quality threshold policies are distinct,
versioned owner decisions with separate payload hashes and independent reviews.
Minimum coverage was reviewed on PR #219 head `5775e908cfe072fa962c99e822901b7157128418`
under review `4937929668`. Data quality was reviewed on PR #222 head
`a7bdff6101d724d3413b0fa3d097c240b236326f` under review `4943325699`. No
percentage, count, quality conclusion, or acceptance threshold is inferred from
repository fixtures, code, or S3 reporting behavior.

The following is an existing S3 reporting fact only and is not an S1
acceptance threshold:

    MIN_COMPARABLE_ROWS_FOR_REPORTING=10
    MIN_COMPARABLE_ROWS_IS_S3_REPORTING_FLOOR=true
    MIN_COMPARABLE_ROWS_IS_S1_MINIMUM_COVERAGE_THRESHOLD=false

## Fail-closed rule

Each threshold gate is closed only because its own owner policy, payload hash,
independent review, and exact-head CI evidence are present. The minimum-coverage
and data-quality policies remain distinct and must not be conflated. This record
does not authorize metric execution.

## Authority

    AUTHORITY_CONTRACT=docs/v0-3/s1/metric-coverage-and-quality-contract.md
    S3_AUTHORITY=docs/forecast-quality/s3-quality-metrics-contract.md
