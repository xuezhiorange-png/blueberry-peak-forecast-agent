# S1 Minimum Coverage Threshold Policy Decision

## Current result

```text
TASK=V0_3_S1_MINIMUM_COVERAGE_THRESHOLD_POLICY_DECISION
RESULT=POLICY_DECISION_ISSUED_PENDING_INDEPENDENT_REVIEW
BASE_MAIN_SHA=b96fc39fcee50c2447e7bcc90580745b090d8646
GATE_ID=S1-MINIMUM-COVERAGE
POLICY_VERSION=v0-3-s1-minimum-coverage-threshold-v1
```

This task freezes the first versioned S1 minimum-coverage policy without reading Source 002 raw rows, executing a backtest, materializing TRAIN/VALIDATION/TEST rowsets, or changing the canonical S1 acceptance record.

## Contract alignment

The S3 quality-metrics contract already defines the coverage ratio as:

```text
coverage_ratio = s2_comparable_binding_row_count / s2_total_binding_row_count
```

It also defines `MIN_COMPARABLE_ROWS_FOR_REPORTING=10` only as an S3 small-sample reporting floor. The S1 acceptance package explicitly states that this S3 reporting floor is not an S1 minimum-coverage threshold. This decision therefore does not copy or reinterpret the value 10 as S1 threshold authority.

The S3 contract separately requires complete, contiguous daily rowsets for cumulative and peak/window metrics. This S1 coverage policy does not relax those stronger completeness rules.

## Decision

```text
DECISION_ID=S1_MINIMUM_COVERAGE_THRESHOLD_POLICY
POLICY_VERSION=v0-3-s1-minimum-coverage-threshold-v1
THRESHOLD_TYPE=COMPARABLE_BINDING_ROW_COVERAGE_RATIO
THRESHOLD_OPERATOR=GREATER_THAN_OR_EQUAL
THRESHOLD_VALUE=0.900000
NUMERATOR=s2_comparable_binding_row_count
DENOMINATOR=s2_total_binding_row_count
ZERO_DENOMINATOR_POLICY=FAIL_CLOSED_NOT_ELIGIBLE
```

A governed evaluation breakdown cell is coverage-eligible for S1 only when:

```text
s2_total_binding_row_count > 0
AND
coverage_ratio >= 0.900000
```

The threshold is a ratio threshold, not an absolute sample-count threshold. Small-sample signaling remains governed independently by the S3 reporting-floor rule.

## Scope and grain

The policy applies to every S1 evaluation breakdown cell emitted under the frozen S3 breakdown contract. The required axes remain:

```text
forecast_horizon_days
farm_business_key
subfarm_business_key
variety_business_key
season_business_key
model_identity
```

The underlying calculation-base grain remains the S3 contract grain:

```text
SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_TARGET_DATE_X_FORECAST_CUTOFF_X_MODEL_IDENTITY_X_FORECAST_QUANTILE
```

The minimum-coverage threshold is evaluated after the applicable breakdown selection and before S1 acceptance/release eligibility is claimed for that cell.

## Horizon and partition policy

```text
REQUIRED_HORIZONS_DAYS=7,14,21
EVALUATION_PARTITIONS=TRAIN,VALIDATION,TEST
THRESHOLD_VARIES_BY_HORIZON=false
THRESHOLD_VARIES_BY_PARTITION=false
```

The same 90% threshold is used across 7-, 14-, and 21-day horizons and across TRAIN, VALIDATION, and TEST. A lower threshold for a difficult horizon or partition is not allowed because that would make acceptance dependent on the observed weakness of the data and would reduce cross-horizon comparability.

## Failure semantics

If `s2_total_binding_row_count == 0`, the cell is fail-closed and cannot satisfy S1 minimum coverage.

If `coverage_ratio < 0.900000`:

```text
S1_COVERAGE_STATUS=BELOW_MINIMUM
S1_ACCEPTANCE_ELIGIBLE=false
S1_RELEASE_ELIGIBLE=false
METRIC_CELL_DROPPED=false
METRIC_VALUE_REWRITTEN=false
```

The metric cell remains visible for auditability. This policy governs acceptance/release eligibility only; it does not mutate the metric value or reclassify upstream S2 row statuses.

## Independent rules preserved

The 90% policy does not override any of the following:

- S2 `COMPARABLE` / `EXCLUDED` / `NOT_COMPUTABLE` row-status semantics;
- S3 structural duplicate failures;
- exact actual-pair requirements for quantile coverage;
- P50/P80/P90 semantic-verification gates;
- complete daily-rowset requirements for cumulative and peak/window metrics;
- complete seven-day-window requirements for sustained-peak metrics;
- the S3 small-sample reporting floor.

A cell may satisfy the 90% coverage ratio and still remain blocked or not computable under any stronger independent contract rule.

## Decision identity

The canonical decision payload is SHA-256 bound as:

```text
DECISION_PAYLOAD_SHA256=1ae1cb2c13f2e9552eeccb1f47330e1ac3a7764b3099ecce7391d9e8335ff94e
```

The hash covers the sorted canonical JSON payload containing the threshold identity, numerator, denominator, scope, horizons, partitions, failure semantics, and non-override rules.

## Current gate boundary

```text
POLICY_DECISION_ISSUED=true
POLICY_INDEPENDENTLY_REVIEWED=false
S1_MINIMUM_COVERAGE_GATE_PASS=false
CANONICAL_ACCEPTANCE_RECORD_CHANGED=false
SOURCE_002_RAW_READ=false
SOURCE_002_ROW_LEVEL_READ=false
BACKTEST_EXECUTED=false
MODEL_TRAINING_EXECUTED=false
TEST_DATA_ACCESS=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
```

The policy decision is issued for independent review only. This task does not itself turn `S1-MINIMUM-COVERAGE` to PASS and does not imply the data-quality threshold decision or any later gate.

```text
NEXT_GATE=S1_MINIMUM_COVERAGE_THRESHOLD_POLICY_EXACT_HEAD_INDEPENDENT_REVIEW
NEXT_GATE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```
