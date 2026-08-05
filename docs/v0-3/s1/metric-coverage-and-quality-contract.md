# S1 Metric, Coverage, and Data-Quality Contract

## Authority and status

```text
METRIC_AUTHORITY=docs/forecast-quality/s3-quality-metrics-contract.md
CURRENT_METRIC_CONTRACT_STATUS=BLOCKED
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
CURRENT_MINIMUM_COVERAGE_THRESHOLD_STATUS=BLOCKED
```

The current status is deliberately fail-closed. V0.2 output fields named P50,
P80, and P90 do not prove that their S3 semantics have been verified.

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

## Metric registry binding

Each row below binds a metric to the authoritative S3 status and reason-code
semantics. `authority_section` uses the section names in the S3 contract so a
future acceptance record can cite the exact contract location without creating
a new reason code.

| `metric_id` | Computability prerequisite | Unverified status | Not-computable status | Primary authoritative reason code | Authority section | Current state |
| --- | --- | --- | --- | --- | --- | --- |
| `daily_mae` | Accepted comparable daily labels and metric inputs | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `NO_APPROVED_REAL_DATA` | Daily point metrics and comparable-row input | `BLOCKED` |
| `daily_wape` | Accepted comparable daily labels and metric inputs | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `NO_APPROVED_REAL_DATA` | Daily point metrics and comparable-row input | `BLOCKED` |
| `daily_smape` | Accepted comparable daily labels and metric inputs | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `NO_APPROVED_REAL_DATA` | Daily point metrics and comparable-row input | `BLOCKED` |
| `daily_bias_kg` | Accepted comparable daily labels and metric inputs | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `NO_APPROVED_REAL_DATA` | Daily point metrics and comparable-row input | `BLOCKED` |
| `daily_absolute_error_sum_kg` | Accepted comparable daily labels and metric inputs | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `NO_APPROVED_REAL_DATA` | Daily point metrics and comparable-row input | `BLOCKED` |
| `cumulative_error_kg` | Complete comparable daily rowset for the requested range | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | Complete daily row set and cumulative metrics | `BLOCKED` |
| `single_day_peak` | Complete comparable daily rowset and deterministic tie rule | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | Peak metrics | `BLOCKED` |
| `sustained_7_day_peak` | Complete consecutive calendar-day rowset | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | Peak metrics and complete horizon | `BLOCKED` |
| `p80_coverage` | P80 semantics verified, upper interval mask, and eligible labels | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `QUANTILE_SEMANTICS_NOT_VERIFIED` | P80 coverage | `BLOCKED` |
| `p90_coverage` | P90 semantics verified, upper interval mask, and eligible labels | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `QUANTILE_SEMANTICS_NOT_VERIFIED` | P90 coverage | `BLOCKED` |
| `p80_spread` | P80 and P50 semantics verified and both values present | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `QUANTILE_SEMANTICS_NOT_VERIFIED` | Quantile spread semantics | `BLOCKED` |
| `p90_spread` | P90 and P50 semantics verified and both values present | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `QUANTILE_SEMANTICS_NOT_VERIFIED` | Quantile spread semantics | `BLOCKED` |
| `baseline_point_forecast` | Prior-season analog point labels and comparable scope | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `NO_APPROVED_REAL_DATA` | Naive baseline definition | `BLOCKED` |
| `baseline_p80` | A baseline quantile distribution contract, not only a point forecast | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` | Naive baseline P80/P90 | `BLOCKED` |
| `baseline_p90` | A baseline quantile distribution contract, not only a point forecast | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` | Naive baseline P80/P90 | `BLOCKED` |
| `quantile_calibration` | P50/P80/P90 semantics, coverage masks, and thresholds verified | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `QUANTILE_SEMANTICS_NOT_VERIFIED` | Quantile calibration | `BLOCKED` |
| `rolling_backtest_comparison` | Complete daily rowset, point-in-time labels, and same scope for model/baseline | `NOT_VERIFIED` | `NOT_COMPUTABLE` | `COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING` | Rolling backtest comparison | `BLOCKED` |

The orchestration authority may add `BELOW_MINIMUM` when the S3 reporting
minimum is not met (`MIN_COMPARABLE_ROWS_FOR_REPORTING=10`). That reason is a
sample-size result, not a replacement for a missing semantic or rowset gate.

## Exact semantic boundaries

- `P80_coverage` and `P90_coverage` use the upper-coverage masks defined by the
  S3 contract; they are not generic interval coverage.
- `p80_spread` is `P80 - P50`, and `p90_spread` is `P90 - P50`; they are not
  lower/upper interval widths.
- The naive baseline is
  `PRIOR_SEASON_ANALOG_DAY_ACTUAL` and is a point forecast. Its P80 and P90 are
  `NOT_COMPUTABLE` until a baseline quantile distribution is formally defined.
- Peak metrics require complete consecutive calendar days and use the
  authoritative earliest-date tie rule. Missing days are not silently filled
  with zero.
- Aggregation uses Decimal values, six-place precision, and final-boundary
  `ROUND_HALF_EVEN` as specified by S3; native floating-point accumulation is
  not accepted.
- Every result carries metric status and, when not computable, a non-empty
  authoritative reason code. `NOT_VERIFIED` is not `PASS`; `NOT_COMPUTABLE` is
  not zero.

## Coverage and quality threshold freeze

Numeric coverage and data-quality thresholds must be frozen before acceptance
and must cite their authority. A threshold cannot be inferred from a test
fixture, CI seed, or an unreviewed planning value.

```text
CURRENT_COVERAGE_THRESHOLD_STATUS=BLOCKED
CURRENT_DATA_QUALITY_THRESHOLD_STATUS=BLOCKED
S1_ACCEPTANCE_REQUIRES_EXPLICIT_COVERAGE_THRESHOLD=true
S1_ACCEPTANCE_REQUIRES_EXPLICIT_DATA_QUALITY_THRESHOLD=true
S1_ACCEPTANCE_REQUIRES_THRESHOLD_PROVENANCE=true
```

## Fail-closed publication rule

No coverage, baseline-quantile superiority, or quantile-calibration pass
statement may be published until the corresponding semantics, daily-rowset,
threshold, and independent-review gates are accepted. A failed prerequisite is
reported with its status and reason, never replaced by zero or omission.
