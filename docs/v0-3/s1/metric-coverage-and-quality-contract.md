# S1 Metric, Coverage, and Data-Quality Contract

## Authority and current state

```text
METRIC_CONTRACT_AUTHORITY=docs/forecast-quality/s3-quality-metrics-contract.md
V0_3_METRIC_CONTRACT_VERSION=v0.3-metric-contract-v1
METRIC_INPUT_MASK_POLICY_VERSION=v0.2-s3-metric-input-mask-v1

S1_CONTRACT_READINESS_STATUS=BLOCKED
S1_CONTRACT_BLOCK_REASON=BLOCKED_BY_MISSING_SOURCE_AUTHORITY
CURRENT_METRIC_EXECUTION_STATUS=NOT_EXECUTED
CURRENT_METRIC_RESULT_REASON_CODE=NOT_ISSUED
CURRENT_METRIC_RESULT_REASON_CODE_STATUS=NOT_S3_RESULT

CURRENT_S3_DAILY_ROWSET_CONTRACT_STATUS=NOT_AVAILABLE_FROM_CURRENT_S2_BINDING
CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_STATUS=BLOCKED_BY_S2_COMPLETE_DAILY_ROW_SET_AUTHORITY
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_P50_SEMANTICS_VERIFIED=false
CURRENT_P80_SEMANTICS_VERIFIED=false
CURRENT_P90_SEMANTICS_VERIFIED=false
CURRENT_P50_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P90_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_COVERAGE_COMPUTABLE=false
CURRENT_P90_COVERAGE_COMPUTABLE=false
CURRENT_BASELINE_P80_COMPUTABLE=false
CURRENT_BASELINE_P90_COMPUTABLE=false
CURRENT_BASELINE_P80_STATUS=NOT_COMPUTABLE
CURRENT_BASELINE_P90_STATUS=NOT_COMPUTABLE
CURRENT_BASELINE_P80_P90_REASON=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
CURRENT_QUANTILE_CALIBRATION_STATUS=NOT_VERIFIED
CURRENT_MINIMUM_COVERAGE_THRESHOLD_STATUS=PASS
CURRENT_DATA_QUALITY_THRESHOLD_STATUS=BLOCKED
```

`CURRENT_METRIC_RESULT_REASON_CODE=NOT_ISSUED` is an S1 current-state
sentinel. It is not an S3 metric result reason code. No S3 metric result is
issued before the source, target, visibility, rowset, and execution gates are
accepted.

The current state is fail-closed. Existing V0.2 fields named P50, P80, and P90
do not prove that the S3 semantics of those values have been verified.

## Future acceptance prerequisites

```text
S1_ACCEPTANCE_REQUIRES_S3_METRIC_CONTRACT_VERSION=true
S1_ACCEPTANCE_REQUIRES_DAILY_ROWSET_AMENDMENT_COMPLETE=true
S1_ACCEPTANCE_REQUIRES_DAILY_ROWSET_COMPLETENESS_VERIFIED=true
S1_ACCEPTANCE_REQUIRES_P50_SEMANTICS_VERIFIED=true
S1_ACCEPTANCE_REQUIRES_P80_SEMANTICS_VERIFIED=true
S1_ACCEPTANCE_REQUIRES_P90_SEMANTICS_VERIFIED=true
S1_ACCEPTANCE_REQUIRES_COVERAGE_THRESHOLD_ACCEPTED=true
S1_ACCEPTANCE_REQUIRES_DATA_QUALITY_THRESHOLD_ACCEPTED=true
S1_ACCEPTANCE_REQUIRES_BASELINE_COMPARISON_POLICY=true
S1_ACCEPTANCE_REQUIRES_PEAK_AND_ROLLING_ROWSET_GATE=true
```

Until these requirements are accepted:

```text
P80_COVERAGE_RELEASE_ELIGIBLE=false
P90_COVERAGE_RELEASE_ELIGIBLE=false
BASELINE_P80_COMPARISON_RELEASE_ELIGIBLE=false
BASELINE_P90_COMPARISON_RELEASE_ELIGIBLE=false
QUANTILE_CALIBRATION_ACCEPTANCE_ELIGIBLE=false
```

These are release-eligibility invariants, not evidence that a future gate has
passed.

## Canonical S3 metric registry

The rows below use canonical S3 metric identities. Every row carries the
contract version, authority path, exact authority section, and reason-code
status. Until execution, `current_metric_status=NOT_ISSUED` and
`current_metric_reason_code=NOT_ISSUED` are S1 sentinels, not S3 result values.

| metric_id | metric_contract_version | authority_path | authority_section | computability_prerequisite | current_metric_status | current_metric_reason_code | reason_code_status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `daily_mae` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§6` | accepted comparable P50 daily labels and metric inputs | `NOT_ISSUED` | `NOT_ISSUED` | `NOT_ISSUED_CURRENT_STATE` |
| `daily_wape` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§6` | accepted comparable P50 daily labels and non-zero denominator | `NOT_ISSUED` | `NOT_ISSUED` | `NOT_ISSUED_CURRENT_STATE` |
| `daily_smape` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§6` | accepted comparable P50 daily labels and zero-safety policy | `NOT_ISSUED` | `NOT_ISSUED` | `NOT_ISSUED_CURRENT_STATE` |
| `daily_mape` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§3.1; §6` | accepted P50 mask, positive-actual eligibility rule, and `mape_eligible_row_count` denominator | `NOT_ISSUED` | `NOT_ISSUED` | `NOT_ISSUED_CURRENT_STATE` |
| `daily_bias_kg` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§6` | accepted comparable P50 daily labels | `NOT_ISSUED` | `NOT_ISSUED` | `NOT_ISSUED_CURRENT_STATE` |
| `daily_relative_bias` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§6` | accepted comparable labels and non-zero actual denominator | `NOT_ISSUED` | `NOT_ISSUED` | `NOT_ISSUED_CURRENT_STATE` |
| `daily_absolute_error_sum_kg` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§6` | accepted comparable P50 daily labels | `NOT_ISSUED` | `NOT_ISSUED` | `NOT_ISSUED_CURRENT_STATE` |
| `cumulative_signed_error_kg` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§7` | complete daily rowset for requested horizon | `NOT_ISSUED` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | `VERIFIED_FORMAL_S3_CONTRACT` |
| `cumulative_absolute_error_kg` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§7` | complete daily rowset for requested horizon | `NOT_ISSUED` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | `VERIFIED_FORMAL_S3_CONTRACT` |
| `cumulative_signed_relative_error` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§7-§8` | complete daily rowset and non-zero cumulative actual denominator | `NOT_ISSUED` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | `VERIFIED_FORMAL_S3_CONTRACT` |
| `cumulative_absolute_relative_error` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§7-§8` | complete daily rowset and non-zero cumulative actual denominator | `NOT_ISSUED` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | `VERIFIED_FORMAL_S3_CONTRACT` |
| `single_day_peak_date_signed_error_days_q` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§9.1` | complete daily rowset and earliest-date tie rule | `NOT_ISSUED` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | `VERIFIED_FORMAL_S3_CONTRACT` |
| `single_day_peak_date_absolute_error_days_q` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§9.1` | complete daily rowset and earliest-date tie rule | `NOT_ISSUED` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | `VERIFIED_FORMAL_S3_CONTRACT` |
| `single_day_peak_quantity_signed_error_kg_q` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§9.1` | complete daily rowset and earliest-date tie rule | `NOT_ISSUED` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | `VERIFIED_FORMAL_S3_CONTRACT` |
| `single_day_peak_quantity_absolute_error_kg_q` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§9.1` | complete daily rowset and earliest-date tie rule | `NOT_ISSUED` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | `VERIFIED_FORMAL_S3_CONTRACT` |
| `sustained_7day_start_date_signed_error_days_q` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§9.2` | complete daily rowset and complete 7-day window | `NOT_ISSUED` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | `VERIFIED_FORMAL_S3_CONTRACT` |
| `sustained_7day_start_date_absolute_error_days_q` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§9.2` | complete daily rowset and complete 7-day window | `NOT_ISSUED` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | `VERIFIED_FORMAL_S3_CONTRACT` |
| `sustained_7day_quantity_signed_error_kg_q` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§9.2` | complete daily rowset and complete 7-day window | `NOT_ISSUED` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | `VERIFIED_FORMAL_S3_CONTRACT` |
| `sustained_7day_quantity_absolute_error_kg_q` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§9.2` | complete daily rowset and complete 7-day window | `NOT_ISSUED` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | `VERIFIED_FORMAL_S3_CONTRACT` |
| `P50_UPPER_COVERAGE` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§10` | P50 semantics, upper mask, exact-paired labels, valid denominator | `NOT_ISSUED` | `QUANTILE_SEMANTICS_NOT_VERIFIED` | `VERIFIED_FORMAL_S3_CONTRACT` |
| `P80_UPPER_COVERAGE` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§10` | P80 semantics, upper mask, exact-paired labels, valid denominator | `NOT_ISSUED` | `QUANTILE_SEMANTICS_NOT_VERIFIED` | `VERIFIED_FORMAL_S3_CONTRACT` |
| `P90_UPPER_COVERAGE` | `v0.3-metric-contract-v1` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§10` | P90 semantics, upper mask, exact-paired labels, valid denominator | `NOT_ISSUED` | `QUANTILE_SEMANTICS_NOT_VERIFIED` | `VERIFIED_FORMAL_S3_CONTRACT` |

The formal reason-code set used by this contract is limited to codes established
by the S3 authority:

```text
QUANTILE_SEMANTICS_NOT_VERIFIED
BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
NO_COMPLETE_7DAY_WINDOW
BELOW_MINIMUM
SIGNED_DIRECTION_ONLY
```

`NO_COMPLETE_7DAY_WINDOW` is evaluated only after a daily rowset is available.
When the rowset itself is unavailable, the result remains bound to
`COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING`.

## Computability mapping for planning results

The following mapping keeps planning aliases distinct from S3 canonical metric
IDs. `unverified_status` and `not_computable_status` are S3 result-state
values; the current S1 package still reports `NOT_ISSUED` and does not issue a
result reason code.

| metric_id | computability_prerequisite | unverified_status | not_computable_status | authoritative_reason_code | authority_path | authority_section |
| --- | --- | --- | --- | --- | --- | --- |
| `P80_COVERAGE` | P80 semantics, Q2C alignment, exact-paired rows, valid denominator | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `QUANTILE_SEMANTICS_NOT_VERIFIED` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§10` |
| `P90_COVERAGE` | P90 semantics, Q2C alignment, exact-paired rows, valid denominator | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `QUANTILE_SEMANTICS_NOT_VERIFIED` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§10` |
| `P80_UPPER_QUANTILE_SPREAD` | verified P80 and P50 upper-quantile semantics with the same comparison scope | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `QUANTILE_SEMANTICS_NOT_VERIFIED` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§10` |
| `P90_UPPER_QUANTILE_SPREAD` | verified P90 and P50 upper-quantile semantics with the same comparison scope | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `QUANTILE_SEMANTICS_NOT_VERIFIED` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§10` |
| `BASELINE_P80` | point-only baseline must first define a quantile distribution | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§15` |
| `BASELINE_P90` | point-only baseline must first define a quantile distribution | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§15` |
| `QUANTILE_CALIBRATION` | verified P50/P80/P90 semantics and the applicable quantile evaluation contract | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `QUANTILE_SEMANTICS_NOT_VERIFIED` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§10` |
| `SINGLE_DAY_PEAK` | complete daily rowset for the requested window and S3 peak tie rule | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§9.1` |
| `SUSTAINED_7DAY_PEAK` | complete daily rowset with a complete seven-day window | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§9.2` |
| `ROLLING_COMPARISON` | complete daily rowset for complete-window comparison fields | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | `docs/forecast-quality/s3-quality-metrics-contract.md` | `§16.5` |

`P80_UPPER_QUANTILE_SPREAD` and `P90_UPPER_QUANTILE_SPREAD` are planning
aliases only and mean `P80-P50` and `P90-P50`, respectively. They are not
prediction-interval widths and have no independent S3 canonical metric ID.

## V0.3 planning crosswalk

Planning aliases are retained as planning identities only. They are not S3
canonical metric IDs.

```text
V0_3_PLAN_METRIC_ID=P80_COVERAGE
S3_AUTHORITY_METRIC_ID=P80_UPPER_COVERAGE

V0_3_PLAN_METRIC_ID=P90_COVERAGE
S3_AUTHORITY_METRIC_ID=P90_UPPER_COVERAGE

V0_3_PLAN_METRIC_ID=P80_UPPER_QUANTILE_SPREAD
S3_AUTHORITY_METRIC_ID=NOT_A_CANONICAL_S3_METRIC_ID
S3_AUTHORITY_FORMULA=P80-P50

V0_3_PLAN_METRIC_ID=P90_UPPER_QUANTILE_SPREAD
S3_AUTHORITY_METRIC_ID=NOT_A_CANONICAL_S3_METRIC_ID
S3_AUTHORITY_FORMULA=P90-P50

P80_UPPER_QUANTILE_SPREAD=P80-P50
P90_UPPER_QUANTILE_SPREAD=P90-P50
P80_UPPER_QUANTILE_SPREAD_IS_PREDICTION_INTERVAL_WIDTH=false
P90_UPPER_QUANTILE_SPREAD_IS_PREDICTION_INTERVAL_WIDTH=false
LOWER_QUANTILE_BOUND_REQUIRED=false
```

The naive baseline is a point forecast under the S3 baseline contract. Its
quantile status is represented by the authoritative status fields, not by a
new canonical metric ID:

```text
V0_3_PLAN_METRIC_ID=BASELINE_P80
S3_AUTHORITY_STATUS_FIELD=NAIVE_BASELINE_P80_STATUS
S3_AUTHORITY_METRIC_ID=NOT_A_CANONICAL_METRIC_ID

V0_3_PLAN_METRIC_ID=BASELINE_P90
S3_AUTHORITY_STATUS_FIELD=NAIVE_BASELINE_P90_STATUS
S3_AUTHORITY_METRIC_ID=NOT_A_CANONICAL_METRIC_ID

CURRENT_BASELINE_P80_STATUS=NOT_COMPUTABLE
CURRENT_BASELINE_P90_STATUS=NOT_COMPUTABLE
CURRENT_BASELINE_P80_P90_REASON=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
```

The planning rolling-comparison alias maps to the S3 comparison-group field
set, not to a fabricated single metric:

```text
V0_3_PLAN_METRIC_ID=ROLLING_COMPARISON
S3_AUTHORITY_FIELD_SET=§16.5_COMPARISON_GROUP_FIELDS
S3_AUTHORITY_METRIC_ID=NOT_A_CANONICAL_SINGLE_METRIC_ID
```

## Rowset computability boundary

```text
COVERAGE_REQUIRES_COMPLETE_DAILY_ROW_SET=false
PEAK_AND_COMPLETE_HORIZON_METRICS_MAY_REQUIRE_COMPLETE_DAILY_ROW_SET=true
```

Coverage may be computed on valid exact-paired sparse rows only after P50/P80/P90
semantics, Q2C alignment, exact pairing, and a valid denominator are accepted.
Cumulative metrics, single-day peak, sustained-seven-day peak, and
complete-window comparison require a complete daily rowset. The complete rowset
must be contiguous, deduplicated, and free of missing days for the requested
window.

`NO_COMPLETE_7DAY_WINDOW` is evaluated only after the daily rowset is available.
If the rowset is unavailable, the result cannot be rewritten as that reason.

## Thresholds and fail-closed publication

```text
CURRENT_MINIMUM_COVERAGE_THRESHOLD_STATUS=PASS
CURRENT_DATA_QUALITY_THRESHOLD_STATUS=BLOCKED
MIN_COMPARABLE_ROWS_FOR_REPORTING=10
MIN_COMPARABLE_ROWS_IS_S3_REPORTING_FLOOR=true
MIN_COMPARABLE_ROWS_IS_S1_MINIMUM_COVERAGE_THRESHOLD=false
MINIMUM_COVERAGE_THRESHOLD_POLICY_VERSION=v0-3-s1-minimum-coverage-threshold-v1
MINIMUM_COVERAGE_THRESHOLD_VALUE=0.900000
MINIMUM_COVERAGE_THRESHOLD_OWNER_DECISION_SHA256=a9361145eaa04e93e6b7bc3a4e4faa7a42c542b29de4978988658f53fa11f692
MINIMUM_COVERAGE_THRESHOLD_INDEPENDENT_REVIEW_ID=4937929668
```

`MIN_COMPARABLE_ROWS_FOR_REPORTING=10` is the S3 reporting floor. It is not an
S1 minimum coverage acceptance threshold, and this package invents no coverage
percentage or data-quality threshold.

All metric results use Decimal arithmetic, six-place precision, and the final
boundary rounding policy specified by S3. `NOT_VERIFIED` is not `PASS`,
`NOT_COMPUTABLE` is not zero, and an unexecuted metric has no S3 result reason
code. No coverage, baseline-quantile superiority, or calibration pass statement
may be published before the corresponding prerequisites and independent review
are accepted.
