# V0.2-S3 Forecast Quality Metrics Contract

> Target: V0.2-S3 (FORECAST_QUALITY_METRICS_AND_ONE_NAIVE_BASELINE)
> Slice index: 3 of 5 in V0.2
> Scope: design freeze only — no implementation, no schema, no migration, no API
> Base: `b873dd63fc0d5b6375f94674abbd24a94d915f3c`
> Source authority: `docs/forecast-quality/q2b-point-in-time-backtest-runner-contract.md` (frozen S2 binding + manifest)

```text
V0_2_S3_DESIGN_FREEZE_AUTHORIZED=true
S3_IMPLEMENTATION_AUTHORIZED=false
PRODUCTION_CODE_CHANGE_AUTHORIZED=false
TEST_CHANGE_AUTHORIZED=false
SCHEMA_CHANGE_AUTHORIZED=false
MIGRATION_CHANGE_AUTHORIZED=false
WORKFLOW_CHANGE_AUTHORIZED=false
DEPENDENCY_CHANGE_AUTHORIZED=false
REAL_DATA_OPEN_AUTHORIZED=false
REAL_DATA_BACKTEST_AUTHORIZED=false
DATA_IMPORT_AUTHORIZED=false
MODEL_CHANGE_AUTHORIZED=false
ISSUE102_CLOSE_AUTHORIZED=false
DRAFT_PR_AUTHORIZED=true
MARK_READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
BUSINESS_ATTESTATION_REQUIRED_FOR_S3_SYNTHETIC_IMPLEMENTATION=false
BUSINESS_ATTESTATION_REQUIRED_FOR_REAL_DATA_ACCEPTANCE=true
```

## 1. Purpose

This document freezes the quality-metrics contract for V0.2-S3. It binds the
metric formulas, denominator-zero policies, peak-detection rules, sustained-window
rules, quantile-coverage semantics, breakdown contract and canonical identity to
the S2 frozen binding output. It does not implement the calculator, schema, API,
task queue or front-end. It is a design-only freeze.

S3 consumes the S2 frozen comparison-ready binding and manifest as its single
source of truth. S3 MUST NOT re-query the latest forecast, the latest actual,
current master data, unbound Task 8 / Task 9 / Task 10 outputs, or factory-receipt
or arrival-proxy data. All metric inputs come from the S2 immutable binding rows.

```text
S3_INPUT_AUTHORITY=S2_IMMUTABLE_BACKTEST_BINDING
S3_INPUT_ROW_STATUS_ALLOWED=COMPARABLE
EXCLUDED_ROWS_USED_IN_METRICS=false
NOT_COMPUTABLE_ROWS_USED_IN_METRICS=false
MISSING_ACTUAL_TREATED_AS_ZERO=false
```

## 2. Comparable / excluded / not-computable status

The S2 binding row already carries a row status. S3 consumes only rows whose
status is `COMPARABLE`. Rows with any other status are reported separately and
never enter a metric numerator or denominator.

```text
COMPARABLE_ROW_BUCKET=included in metric numerators and denominators
EXCLUDED_ROW_BUCKET=reported count only, NEVER enters metric value
NOT_COMPUTABLE_ROW_BUCKET=reported count only, NEVER enters metric value
MISSING_ACTUAL_TREATED_AS_ZERO=false
```

Every S3 result binds the following three counters, in addition to the metric
value:

```text
comparable_row_count
excluded_row_count
not_computable_row_count
coverage_ratio = comparable_row_count / (comparable_row_count + excluded_row_count + not_computable_row_count)
```

A metric result is never published with `excluded_row_count = 0` and
`not_computable_row_count = 0` assumed; both counters are mandatory.

## 3. Metric identity binding

Every metric result MUST carry the following identity:

```text
s2_run_identity         — exact S2 backtest run identity
s2_manifest_identity    — exact S2 manifest identity
s2_binding_row_set_hash — sha256 of the S2 row set consumed by the metric
metric_policy_version   — frozen metric formula version
baseline_policy_version — frozen baseline formula version
breakdown_dimensions    — the breakdown axes for this metric value
comparable_row_count
excluded_row_count
not_computable_row_count
```

The canonical hash of the metric result over these fields is the byte-identity
gate for any downstream persistence. Identity does NOT carry any of:

```text
database numeric IDs
insertion timestamps
runtime host or worker IDs
database row order
unbounded raw business rows
credentials or connection strings
```

## 4. Daily point-forecast metrics

Daily point-forecast metrics use P50 unless an existing frozen contract
explicitly requires a different quantile. The current frozen contracts do not
name any other daily quantile, so:

```text
POINT_METRIC_QUANTILE=P50_ONLY
```

Index `i` ranges over `comparable_row_count` rows. Forecast and actual quantities
are `Decimal` with six decimal places. No native float participates in canonical
business arithmetic.

```text
error_i = forecast_p50_i - actual_i
absolute_error_i = abs(error_i)
```

The frozen daily metric values are:

```text
daily_mae            = sum(absolute_error_i) / comparable_row_count
daily_wape           = sum(absolute_error_i) / sum(actual_i)
daily_smape_i        = 2 * absolute_error_i / (abs(forecast_p50_i) + abs(actual_i))
daily_smape          = sum(daily_smape_i) / comparable_row_count
daily_mape_i         = absolute_error_i / actual_i
daily_mape           = sum(daily_mape_i) / comparable_row_count
daily_bias_kg        = sum(error_i) / comparable_row_count
daily_relative_bias  = sum(error_i) / sum(actual_i)
daily_absolute_error_sum_kg = sum(absolute_error_i)
```

## 5. Season cumulative metrics

Cumulative metrics aggregate over the full comparable set per breakdown.

```text
season_cumulative_forecast_kg = sum(forecast_p50_i)
season_cumulative_actual_kg   = sum(actual_i)
cumulative_signed_error_kg    = season_cumulative_forecast_kg - season_cumulative_actual_kg
cumulative_absolute_error_kg  = abs(cumulative_signed_error_kg)
cumulative_signed_relative_error   = cumulative_signed_error_kg / season_cumulative_actual_kg
cumulative_absolute_relative_error = abs(cumulative_signed_error_kg) / season_cumulative_actual_kg
```

Cumulative relative error is well-defined only when `season_cumulative_actual_kg > 0`.
The denominator-zero policy is in §6.

## 6. Denominator-zero and zero-safety policies

```text
ACTUAL_ZERO_ROW_REMOVED_FROM_MAE=false
ACTUAL_ZERO_ROW_REMOVED_FROM_BIAS=false
ACTUAL_ZERO_ROW_REMOVED_FROM_SMAPE=false
ACTUAL_ZERO_ROW_REMOVED_FROM_MASE_OR_OTHER_UNAUTHORIZED_METRICS=true
WAPE_DENOMINATOR_ZERO=NOT_COMPUTABLE
RELATIVE_BIAS_DENOMINATOR_ZERO=NOT_COMPUTABLE
CUMULATIVE_RELATIVE_ERROR_DENOMINATOR_ZERO=NOT_COMPUTABLE
```

When the denominator is zero, the metric value is `NOT_COMPUTABLE` and the
metric cell is reported as `metric_status=NOT_COMPUTABLE` with a `reason_code`
that names the denominator and the bound that failed. The metric row stays in
the result bundle with `metric_value=null` and `reason_code` set.

`MAPE` denominator-zero policy is fixed as:

```text
MAPE_ZERO_POLICY=EXCLUDE_ZERO_ACTUAL_WITH_EXPLICIT_COUNT
```

Rationale: MAPE is a per-row relative error; the S3 contract preserves the
zero-actual rows as a separate counted bucket (`excluded_row_count`) so the
audit trail is not silently lossy. The metric definition uses
`daily_mape_i = absolute_error_i / actual_i` only when `actual_i > 0`. Rows
with `actual_i = 0` contribute to `excluded_row_count` and a dedicated
`reason_code=MAPE_DENOMINATOR_ZERO`. `daily_mape` is the mean over
non-excluded rows. The exposed count makes the bias visible; not silently
dropping the row preserves the audit trail.

`smape` double-zero policy is fixed as:

```text
SMAPE_DOUBLE_ZERO_POLICY=ROW_CONTRIBUTES_ZERO_BOTH_FORECAST_AND_ACTUAL_ZERO
```

When both `forecast_p50_i = 0` and `actual_i = 0`, the row contributes
`daily_smape_i = 0` to the mean. The double-zero case is not `NOT_COMPUTABLE`
because both quantities are exactly defined and their relative error is zero.
Other zero combinations (e.g. `forecast_p50_i = 0` and `actual_i > 0`) are
computed normally and produce `daily_smape_i = 2 * abs(actual_i) / abs(actual_i)
= 2`.

## 7. Peak metrics

### 7.1 Single-day peak

The single-day peak is the maximum daily value inside the breakdown window.

```text
forecast_single_day_peak_quantity_kg_q = max(forecast_q_i) over comparable rows
forecast_single_day_peak_date_q      = arg max date(forecast_q_i) over comparable rows
actual_single_day_peak_quantity_kg    = max(actual_i) over comparable rows
actual_single_day_peak_date           = arg max date(actual_i) over comparable rows
```

```text
PEAK_TIE_BREAK=EARLIEST_DATE
```

When multiple rows tie under the max, the earliest date wins. `q` is one of
`P50`, `P80`, `P90` and the peak is computed independently per quantile.

Peak errors are:

```text
single_day_peak_date_signed_error_days_q      = (forecast_single_day_peak_date_q - actual_single_day_peak_date).days
single_day_peak_date_absolute_error_days_q    = abs(single_day_peak_date_signed_error_days_q)
single_day_peak_quantity_signed_error_kg_q    = forecast_single_day_peak_quantity_kg_q - actual_single_day_peak_quantity_kg
single_day_peak_quantity_absolute_error_kg_q  = abs(single_day_peak_quantity_signed_error_kg_q)
single_day_peak_quantity_signed_relative_error_q   = single_day_peak_quantity_signed_error_kg_q / actual_single_day_peak_quantity_kg
single_day_peak_quantity_absolute_relative_error_q = abs(single_day_peak_quantity_signed_error_kg_q) / actual_single_day_peak_quantity_kg
```

The relative-error divisions use the same denominator-zero policy as §6.

### 7.2 Sustained 7-day peak

```text
SUSTAINED_PEAK_WINDOW_DAYS=7
WINDOW_TYPE=CONTINUOUS_CALENDAR_DAYS
MISSING_DAY_ZERO_FILL=false
TIE_BREAK=EARLIEST_START_DATE
```

The sustained peak is the maximum total kg over any 7 consecutive calendar
days of comparable rows. Windows must be **complete 7 consecutive calendar
days** of comparable rows; if any of the 7 calendar days lacks a comparable
row, the window is rejected. `MISSING_DAY_ZERO_FILL=false`, so the
`SUSTAINED_7DAY_WINDOW_POLICY=REJECT_INCOMPLETE_WINDOW` is the only policy
frozen. The runner does not substitute zeros for missing days.

```text
forecast_sustained_7day_peak_start_date_q = start date of the max 7-day window for forecast_q
forecast_sustained_7day_peak_end_date_q   = end date = start_date + 6 days
forecast_sustained_7day_peak_quantity_kg_q = sum(forecast_q_i) over the max window
actual_sustained_7day_peak_start_date     = start date of the max 7-day window for actual
actual_sustained_7day_peak_end_date       = end date = start_date + 6 days
actual_sustained_7day_peak_quantity_kg    = sum(actual_i) over the max window
```

```text
sustained_7day_start_date_signed_error_days_q   = (forecast_sustained_7day_peak_start_date_q - actual_sustained_7day_peak_start_date).days
sustained_7day_start_date_absolute_error_days_q = abs(sustained_7day_start_date_signed_error_days_q)
sustained_7day_quantity_signed_error_kg_q       = forecast_sustained_7day_peak_quantity_kg_q - actual_sustained_7day_peak_quantity_kg
sustained_7day_quantity_absolute_error_kg_q     = abs(sustained_7day_quantity_signed_error_kg_q)
sustained_7day_quantity_signed_relative_error_q   = sustained_7day_quantity_signed_error_kg_q / actual_sustained_7day_peak_quantity_kg
sustained_7day_quantity_absolute_relative_error_q = abs(sustained_7day_quantity_signed_error_kg_q) / actual_sustained_7day_peak_quantity_kg
```

When the breakdown contains no complete 7-day window, the metric cell is
`metric_status=NOT_COMPUTABLE` and `reason_code=NO_COMPLETE_7DAY_WINDOW`.

## 8. Quantile coverage (P80 / P90)

The S3 contract must verify the actual semantic of P80 / P90 before publishing
coverage metrics. The current frozen contract has:

```text
P80_SEMANTICS=NOT_VERIFIED
P90_SEMANTICS=NOT_VERIFIED
```

The coverage computation is therefore **frozen but gated** on the semantics
verification:

```text
P80_UPPER_COVERAGE = count(actual <= forecast_p80) / comparable_row_count
P90_UPPER_COVERAGE = count(actual <= forecast_p90) / comparable_row_count
```

Coverage is published only when `P80_SEMANTICS=VERIFIED_TRUE_UPPER_QUANTILE`
and `P90_SEMANTICS=VERIFIED_TRUE_UPPER_QUANTILE`. Until that verification is
done, the bundle reports `metric_status=NOT_VERIFIED` and
`reason_code=QUANTILE_SEMANTICS_NOT_VERIFIED`.

```text
P80_INTERVAL_WIDTH=NOT_COMPUTABLE_LOWER_BOUND_UNAVAILABLE
P90_INTERVAL_WIDTH=NOT_COMPUTABLE_LOWER_BOUND_UNAVAILABLE
IS_PREDICTION_INTERVAL_WIDTH=false
```

Pinball loss is **not** part of the S3 contract. Pinball loss is conditional
on a future contract amendment; it is not a default S3 deliverable.

## 9. Breakdown contract

S3 MUST publish the following breakdown axes:

```text
forecast_horizon_days  (REQUIRED_HORIZONS_DAYS=7,14,21)
farm_business_key      (MULTI_FARM=true)
variety_business_key   (MULTI_VARIETY=true)
season_business_key    (MULTI_SEASON=true)
model_identity         (one or more model identities being evaluated)
```

For each breakdown, the bundle publishes:

```text
comparable_row_count
excluded_row_count
not_computable_row_count
coverage_ratio
metric_status
reason_code
```

```text
MIN_COMPARABLE_ROWS_FOR_REPORTING=10
BELOW_MINIMUM_STATUS=INSUFFICIENT_SAMPLE
```

A breakdown cell with `comparable_row_count < MIN_COMPARABLE_ROWS_FOR_REPORTING`
is reported with `metric_status=INSUFFICIENT_SAMPLE` and
`reason_code=BELOW_MINIMUM`. The cell is NOT silently dropped. The metric
value is still recorded, but the status makes the small-sample nature visible.

## 10. Decimal and rounding

All canonical quantities in metric payload are `Decimal` with six decimal
places. No native `float` participates in canonical business arithmetic. The
final metric value is rounded to a frozen `METRIC_QUANTUM` per metric family.
The rounding policy is `ROUND_HALF_EVEN` ("banker's rounding"), applied after
the full arithmetic at the quantum boundary.

```text
METRIC_QUANTUM=1e-6
METRIC_ROUNDING=ROUND_HALF_EVEN
```

The implementation may choose a different decimal representation in memory
(NumPy, `numpy.float64`, etc.) for intermediate computation, but the canonical
metric payload bytes MUST be `Decimal` quantized to `1e-6` and emitted in
`str(decimal_value)` form. The canonical hash is computed over the textual
emission, not the in-memory representation.

## 11. Idempotency and integrity

```text
CALLER_OWNED_TRANSACTION=true
IMMUTABLE_RESULT=true
EXACT_REPLAY_ZERO_WRITE=true
CONFLICTING_REPLAY_REJECTED=true
PARTIAL_METRIC_PERSISTENCE_FORBIDDEN=true
```

The metric result is append-only. A replay with the same inputs MUST produce
the same canonical hash and MUST NOT create a second row. A replay with
different inputs that yields the same canonical hash is rejected with
`CONFLICTING_REPLAY_REJECTED`. Partial metric persistence (some metrics
written, others not) is forbidden; the result is all-or-nothing.

## 12. What S3 does NOT include

```text
MODEL_RETRAINING=false
MODEL_PARAMETER_TUNING=false
TASK8_NUMERICAL_CHANGE=false
TASK9_NUMERICAL_CHANGE=false
TASK10_NUMERICAL_CHANGE=false
REAL_DATA_ACCEPTANCE=false
REAL_DATA_BACKTEST=false
BUSINESS_ATTESTATION_COLLECTION=false
PUBLIC_API=false
FRONTEND=false
BROWSER_E2E=false
OPERATIONAL_RECOMMENDATION=false
ISSUE102_CLOSE=false
```

S3 is a design freeze. S3 implementation, S4 API, S5 frontend, and Issue #102
close are explicitly out of scope.
