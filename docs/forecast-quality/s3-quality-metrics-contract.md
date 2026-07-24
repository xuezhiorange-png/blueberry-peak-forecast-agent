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
rules, quantile-coverage semantics, breakdown contract, decimal arithmetic,
aggregation / duplication rules, and canonical identity to the S2 frozen
binding output. It does not implement the calculator, schema, API, task queue
or front-end. It is a design-only freeze.

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

## 2. S2 daily row set authority — F-01 close

The terms below are bound and are NOT interchangeable.

```text
forecast_horizon_days
  = the lead time between forecast_cutoff_at and the target_date of a single
    binding row. Currently frozen by S2 at 7, 14, or 21.

evaluation_window_days
  = the length of the continuous target-date window required for a cumulative,
    single-day peak, or sustained 7-day peak metric. Currently S3 freezes this
    as 7, 14, or 21 days depending on the requested horizon.

forecast_target_date
  = the calendar business date a single binding row is comparing against.
Requested horizons are 7, 14, 21 — these are NOT continuous 7/14/21 calendar
days of daily curves. They are three sparse target dates per forecast cut.
```

The S2 binding contract `docs/forecast-quality/q2b-point-in-time-backtest-runner-contract.md`
exposes sparse target-date rows under the grain
`CORE_FORECAST_RUN x DATE x FARM_ID x SUBFARM_ID x VARIETY_ID x FORECAST_QUANTILE`,
with `horizon_days ∈ {7, 14, 21}` enforced by S2 schema validation. S2 does
not currently expose a continuous daily curve covering every calendar day
between forecast_cutoff_at and forecast_target_date.

S3 MUST NOT assume that any complete daily row set covering every calendar
day in the evaluation window is available from current S2 binding. S3 MUST
freeze the following readiness state:

```text
S3_COMPLETE_DAILY_ROW_SET_STATUS=NOT_AVAILABLE_FROM_CURRENT_S2_BINDING
S2_TO_S3_DAILY_ROWSET_AMENDMENT_REQUIRED=true
SEASON_CUMULATIVE_METRICS_IMPLEMENTATION_STATUS=BLOCKED
SINGLE_DAY_PEAK_OVER_WINDOW_IMPLEMENTATION_STATUS=BLOCKED
SUSTAINED_7DAY_PEAK_IMPLEMENTATION_STATUS=BLOCKED
COMPLETE_HORIZON_METRICS_IMPLEMENTATION_STATUS=BLOCKED
```

The unimplemented cumulative, single-day-peak, sustained-7-day-peak, and
complete-horizon metrics are blocked until the S2 amendment is accepted. The
metric contract below is the **target** contract that will activate after the
S2 amendment is accepted. Without the S2 amendment, all of §5, §7.1, §7.2,
and the COMPLETE_HORIZON_METRICS section publish `metric_status=NOT_COMPUTABLE`
with `reason_code=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING`.

When the S2 amendment is accepted, S3 MUST additionally bind the following
identities on the daily row set. Until the S2 amendment is accepted, every
field is bound to an explicit sentinel value so that no machine-readable
field is empty.

```text
S3_DAILY_ROW_SET_AUTHORITY=NOT_AVAILABLE_PENDING_S2_AMENDMENT
S3_DAILY_ROW_SET_IDENTITY=NOT_AVAILABLE_PENDING_S2_AMENDMENT
S3_DAILY_ROW_SET_HASH=NOT_AVAILABLE_PENDING_S2_AMENDMENT
S3_DAILY_ROW_SET_START_DATE=NOT_AVAILABLE_PENDING_S2_AMENDMENT
S3_DAILY_ROW_SET_END_DATE=NOT_AVAILABLE_PENDING_S2_AMENDMENT
S3_DAILY_ROW_SET_EXPECTED_DAY_COUNT=NOT_AVAILABLE_PENDING_S2_AMENDMENT
S3_DAILY_ROW_SET_ACTUAL_DAY_COUNT=NOT_AVAILABLE_PENDING_S2_AMENDMENT
S3_DAILY_ROW_SET_COMPLETENESS_STATUS=BLOCKED_BY_S2_COMPLETE_DAILY_ROW_SET_AUTHORITY
```

The future amendment MUST prove that within each evaluation instance, every
`(season, farm, subfarm, variety, model, forecast_cutoff, quantile)` cell
contains contiguous, deduplicated, no-missing-day daily rows for the
requested evaluation window.

## 3. S2 status counters — F-02 close

The S2 binding row already carries a row status. S3 preserves the S2 status
counters and adds metric-specific counters. The S2 status counters are the
S2-row-level ground truth; S3 never reclassifies a row's S2 status.

```text
s2_comparable_row_count
  = count of binding rows whose S2 status == COMPARABLE
s2_excluded_row_count
  = count of binding rows whose S2 status is in {EXCLUDED, NOT_COMPARABLE}
    (S2-level exclusion reasons, NOT a metric-level reclassification)
s2_not_computable_row_count
  = count of binding rows whose S2 status is NOT_COMPUTABLE
```

`excluded_row_count` retains the S2 upstream exclusion semantics. S3 MUST
NOT reclassify any row into S2's `excluded_row_count` for a metric-internal
reason. The metric-internal reclassification goes into the metric-specific
counter, not the S2 counter.

```text
ZERO_ACTUAL_COMPARABLE_ROW_MOVED_TO_S2_EXCLUDED_COUNT=false
```

### 3.1 MAPE-specific counters and formula — F-02 close

```text
mape_eligible_row_count
  = count(binding row where S2 status == COMPARABLE AND actual_i > 0)
mape_zero_actual_row_count
  = count(binding row where S2 status == COMPARABLE AND actual_i == 0)
```

The `daily_mape` formula is:

```text
daily_mape
  = sum(absolute_error_i / actual_i where S2 status == COMPARABLE AND actual_i > 0)
    / mape_eligible_row_count
```

When `mape_eligible_row_count == 0`:

```text
MAPE_NO_ELIGIBLE_ROWS_STATUS=NOT_COMPUTABLE
MAPE_NO_ELIGIBLE_ROWS_REASON=NO_MAPE_ELIGIBLE_ROWS
```

`daily_mape` MUST NOT divide by `comparable_row_count` (the S2 status counter):

```text
MAPE_DIVIDES_BY_ALL_COMPARABLE_ROWS=false
```

`daily_mape` MUST NOT silently move zero-actual rows into `excluded_row_count`
(S2's bucket). Zero-actual rows stay in `s2_comparable_row_count` and are
counted in `mape_zero_actual_row_count`.

## 4. Comparable status semantics

S3 consumes only rows whose S2 status is `COMPARABLE`. Rows with any other
status are reported separately and never enter a metric numerator or denominator.

```text
COMPARABLE_ROW_BUCKET=included in metric numerators and denominators
EXCLUDED_ROW_BUCKET=reported count only, NEVER enters metric value
NOT_COMPUTABLE_ROW_BUCKET=reported count only, NEVER enters metric value
MISSING_ACTUAL_TREATED_AS_ZERO=false
```

Every S3 result binds the following counters, in addition to the metric value:

```text
s2_comparable_row_count
s2_excluded_row_count
s2_not_computable_row_count
coverage_ratio = s2_comparable_row_count / (s2_comparable_row_count + s2_excluded_row_count + s2_not_computable_row_count)
mape_eligible_row_count       (where applicable)
mape_zero_actual_row_count    (where applicable)
```

A metric result is never published with implicit-zero exclusion assumptions; the
S2 status counters and the metric-specific counters are mandatory.

## 5. Metric identity binding

Every metric result MUST carry the following identity:

```text
s2_run_identity         — exact S2 backtest run identity
s2_manifest_identity    — exact S2 manifest identity
s2_binding_row_set_hash — sha256 of the S2 row set consumed by the metric
metric_policy_version   — frozen metric formula version
baseline_policy_version — frozen baseline formula version
breakdown_dimensions    — the breakdown axes for this metric value
s2_comparable_row_count
s2_excluded_row_count
s2_not_computable_row_count
mape_eligible_row_count        (when MAPE is published)
mape_zero_actual_row_count     (when MAPE is published)
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

## 6. Daily point-forecast metrics

Daily point-forecast metrics use P50 unless an existing frozen contract
explicitly requires a different quantile. The current frozen contracts do not
name any other daily quantile, so:

```text
POINT_METRIC_QUANTILE=P50_ONLY
```

Index `i` ranges over `s2_comparable_row_count` rows. Forecast and actual
quantities are `Decimal` with six decimal places. No native float participates
in canonical business arithmetic.

```text
error_i = forecast_p50_i - actual_i
absolute_error_i = abs(error_i)
```

The frozen daily metric values are:

```text
daily_mae            = sum(absolute_error_i) / s2_comparable_row_count
daily_wape           = sum(absolute_error_i) / sum(actual_i)
daily_smape_i        = 2 * absolute_error_i / (abs(forecast_p50_i) + abs(actual_i))
daily_smape          = sum(daily_smape_i) / s2_comparable_row_count
daily_mape           = sum(absolute_error_i / actual_i where actual_i > 0)
                        / mape_eligible_row_count
daily_bias_kg        = sum(error_i) / s2_comparable_row_count
daily_relative_bias  = sum(error_i) / sum(actual_i)
daily_absolute_error_sum_kg = sum(absolute_error_i)
```

## 7. Season cumulative metrics

Cumulative metrics aggregate over the full comparable set per breakdown. They
require a complete daily row set covering the full requested horizon; they are
blocked until the S2 amendment is accepted.

```text
season_cumulative_forecast_kg = sum(forecast_p50_i)
season_cumulative_actual_kg   = sum(actual_i)
cumulative_signed_error_kg    = season_cumulative_forecast_kg - season_cumulative_actual_kg
cumulative_absolute_error_kg  = abs(cumulative_signed_error_kg)
cumulative_signed_relative_error   = cumulative_signed_error_kg / season_cumulative_actual_kg
cumulative_absolute_relative_error = abs(cumulative_signed_error_kg) / season_cumulative_actual_kg
```

Cumulative relative error is well-defined only when `season_cumulative_actual_kg > 0`.
The denominator-zero policy is in §8.

## 8. Denominator-zero and zero-safety policies

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

```text
MAPE_ZERO_POLICY=EXCLUDE_ZERO_ACTUAL_WITH_EXPLICIT_COUNT
```

Rationale: MAPE is a per-row relative error; the S3 contract preserves the
zero-actual rows as a separate counted bucket (`mape_zero_actual_row_count`)
so the audit trail is not silently lossy. The metric definition uses
`daily_mape_i = absolute_error_i / actual_i` only when `actual_i > 0`. Rows
with `actual_i = 0` contribute to `mape_zero_actual_row_count` and a dedicated
`reason_code=MAPE_DENOMINATOR_ZERO`. `daily_mape` is the mean over
mape-eligible rows. The exposed count makes the bias visible; not silently
dropping the row preserves the audit trail.

```text
SMAPE_DOUBLE_ZERO_POLICY=ROW_CONTRIBUTES_ZERO_BOTH_FORECAST_AND_ACTUAL_ZERO
```

When both `forecast_p50_i = 0` and `actual_i = 0`, the row contributes
`daily_smape_i = 0` to the mean. The double-zero case is not `NOT_COMPUTABLE`
because both quantities are exactly defined and their relative error is zero.
Other zero combinations (e.g. `forecast_p50_i = 0` and `actual_i > 0`) are
computed normally and produce `daily_smape_i = 2 * abs(actual_i) / abs(actual_i)
= 2`.

## 9. Peak metrics

### 9.1 Single-day peak

The single-day peak is the maximum daily value inside the breakdown window
(once a complete daily row set is available from S2).

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

The relative-error divisions use the same denominator-zero policy as §8.

```text
SINGLE_DAY_PEAK_OVER_WINDOW_IMPLEMENTATION_STATUS=BLOCKED
SINGLE_DAY_PEAK_OVER_WINDOW_BLOCKER_REASON=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
```

### 9.2 Sustained 7-day peak

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

```text
SUSTAINED_7DAY_PEAK_IMPLEMENTATION_STATUS=BLOCKED
SUSTAINED_7DAY_PEAK_BLOCKER_REASON=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
```

## 10. Quantile coverage (P80 / P90) — F-05 alignment

The S3 contract must verify the actual semantic of P50 / P80 / P90 before
publishing coverage metrics. The current frozen state is:

```text
P50_SEMANTICS=NOT_VERIFIED
P80_SEMANTICS=NOT_VERIFIED
P90_SEMANTICS=NOT_VERIFIED
```

The coverage computation is therefore **frozen but gated** on the semantics
verification:

```text
P50_UPPER_COVERAGE = count(actual <= forecast_p50) / s2_comparable_row_count
P80_UPPER_COVERAGE = count(actual <= forecast_p80) / s2_comparable_row_count
P90_UPPER_COVERAGE = count(actual <= forecast_p90) / s2_comparable_row_count
```

Coverage is published only when `P50_SEMANTICS=VERIFIED_TRUE_UPPER_QUANTILE`,
`P80_SEMANTICS=VERIFIED_TRUE_UPPER_QUANTILE`,
`P90_SEMANTICS=VERIFIED_TRUE_UPPER_QUANTILE`. Until that verification is
done, the bundle reports `metric_status=NOT_VERIFIED` and
`reason_code=QUANTILE_SEMANTICS_NOT_VERIFIED`.

```text
P80_INTERVAL_WIDTH=NOT_COMPUTABLE_LOWER_BOUND_UNAVAILABLE
P90_INTERVAL_WIDTH=NOT_COMPUTABLE_LOWER_BOUND_UNAVAILABLE
IS_PREDICTION_INTERVAL_WIDTH=false
```

### 10.1 Pinball loss — F-05 revert

The S3 contract preserves the conditional pinball-loss contract from the S2
frozen upstream contract. S3 does not delete it; it is gated on the same
quantile-semantics verification.

```text
PINBALL_LOSS_P50_STATUS=NOT_COMPUTABLE
PINBALL_LOSS_P80_STATUS=NOT_COMPUTABLE
PINBALL_LOSS_P90_STATUS=NOT_COMPUTABLE
PINBALL_LOSS_REASON=QUANTILE_SEMANTICS_NOT_VERIFIED
```

The conditional pinball-loss formula is:

```text
pinball_loss_q
  = mean(
      max(
        q * (actual - forecast_q),
        (q - 1) * (actual - forecast_q)
      )
    )
```

`q` is the quantile level expressed as a fraction in `[0, 1]`. The formula
is the standard pinball-loss formula. The branch assignment is explicitly
frozen as:

```text
PINBALL_UNDER_PREDICTION_CONDITION=actual >= forecast_q
PINBALL_UNDER_PREDICTION_TERM=q * (actual - forecast_q)
PINBALL_OVER_PREDICTION_CONDITION=actual < forecast_q
PINBALL_OVER_PREDICTION_TERM=(q - 1) * (actual - forecast_q)
```

Hand-computed examples:

```text
CASE_A:
  q=0.8
  actual=10
  forecast=8
  actual >= forecast_q -> under-prediction branch
  loss = q * (actual - forecast_q) = 0.8 * (10 - 8) = 1.6

CASE_B:
  q=0.8
  actual=8
  forecast=10
  actual < forecast_q -> over-prediction branch
  loss = (q - 1) * (actual - forecast_q) = (0.8 - 1) * (8 - 10) = 0.4
```

The prior wording `q * (actual - forecast_q)` for over-prediction and
`(q - 1) * (actual - forecast_q)` for under-prediction is REVERSED under
the frozen branch assignment and is rejected. The branches are bound to
sign(retention-on-the-correct-side), not to convenience.
Pinball loss is published only when the corresponding quantile semantics is
verified as `VERIFIED_TRUE_UPPER_QUANTILE`.

```text
UPSTREAM_CONTRACT_AMENDMENT_ACCEPTED=false
PINBALL_LOSS_REMOVED_FROM_S3=false
```

## 11. Calculation grain, aggregation, and dedup — F-07 close

The minimum calculation grain for point, peak, and breakdown metrics is:

```text
CALCULATION_BASE_GRAIN=SEASON x farm x subfarm x variety x target_date x forecast_cutoff x model_identity x forecast_quantile
  x variety
  x target_date
  x forecast_cutoff
  x model_identity
  x forecast_quantile
```

### 11.1 Cross-quantile actual-label dedup

The S2 binding row stores one actual-label per physical grain. P50, P80, P90
forecast rows join to the SAME actual identity; the actual is not duplicated
per quantile.

```text
ACTUAL_LABEL_PHYSICAL_ROW_REUSED_ACROSS_QUANTILES=true
ACTUAL_LABEL_COUNTED_ONCE_PER_PHYSICAL_GRAIN=true
QUANTILE_FORECAST_ROWS_JOIN_TO_SAME_ACTUAL_IDENTITY=true
```

### 11.2 P50 point metric mask

```text
POINT_METRIC_FORECAST_QUANTILE=P50
POINT_METRIC_ROW_COUNT_COUNTS_P50_ROWS_ONLY=true
```

`daily_mae`, `daily_wape`, `daily_smape`, `daily_mape`, `daily_bias_kg`,
`daily_relative_bias`, `daily_absolute_error_sum_kg` are computed over the
P50 forecast row only. The result count is `count(P50 forecast rows)`.

### 11.3 P80 / P90 coverage mask

```text
P80_COVERAGE_MASK=P80_FORECAST_ROW_PAIRED_WITH_EXACT_ACTUAL
P90_COVERAGE_MASK=P90_FORECAST_ROW_PAIRED_WITH_EXACT_ACTUAL
```

`P80_UPPER_COVERAGE` uses the P80 forecast row paired with the exact same
physical actual-label rendered for the P50 join. The same applies to P90.

### 11.4 Subfarm → farm aggregation

When the breakdown axes include `farm_business_key`, the farm-level daily
forecast and actual aggregates are:

```text
FARM_DAILY_FORECAST_Q = sum(subfarm forecast_q_i for exact farm / date / variety scope)
FARM_DAILY_ACTUAL   = sum(unique physical actual rows for exact farm / date / variety scope)
```

Farm-level aggregates are an explicit choice. The S3 contract either
publishes farm-level aggregates using the formula above, OR explicitly does
not publish them. The contract MUST NOT take the maximum single-subfarm row
as the farm daily peak.

```text
MAX_SINGLE_SUBFARM_ROW_AS_FARM_DAILY_PEAK=false
FARM_DAILY_AGGREGATE_FORMULA=sum(subfarm_q_i, exact_deduped_actual_rows)
```

### 11.5 Duplicate policy

```text
DUPLICATE_FORECAST_BUSINESS_KEY=STRUCTURAL_FAILURE
DUPLICATE_ACTUAL_PHYSICAL_KEY=STRUCTURAL_FAILURE
DUPLICATE_TARGET_DATE_AFTER_AGGREGATION=STRUCTURAL_FAILURE
```

A duplicate forecast business key, a duplicate actual physical key, or a
duplicate target date after farm aggregation is a structural failure. The
metric row is not emitted; the run fails closed.

## 12. Breakdown contract

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
s2_comparable_row_count
s2_excluded_row_count
s2_not_computable_row_count
coverage_ratio
metric_status
reason_code
```

```text
MIN_COMPARABLE_ROWS_FOR_REPORTING=10
BELOW_MINIMUM_STATUS=INSUFFICIENT_SAMPLE
```

A breakdown cell with `s2_comparable_row_count < MIN_COMPARABLE_ROWS_FOR_REPORTING`
is reported with `metric_status=INSUFFICIENT_SAMPLE` and
`reason_code=BELOW_MINIMUM`. The cell is NOT silently dropped. The metric
value is still recorded, but the status makes the small-sample nature visible.

## 13. Decimal arithmetic — F-06 close

```text
DECIMAL_ONLY_CANONICAL_ARITHMETIC=true
NATIVE_FLOAT_INTERMEDIATE_ALLOWED=false
NUMPY_FLOAT_ALLOWED=false
BINARY_FLOAT_ALLOWED=false
METRIC_QUANTUM=0.000001
METRIC_ROUNDING=ROUND_HALF_EVEN
ROUNDING_APPLIED_AT_FINAL_METRIC_BOUNDARY=true
```

All canonical quantities in the metric payload are `Decimal` with six
decimal places. The metric calculator MUST NOT use native `float`, NumPy
float, or binary float at any intermediate computation step. The
`ROUND_HALF_EVEN` ("banker's rounding") policy is applied at the final
metric boundary, after the full arithmetic. The canonical payload emits
`str(decimal_value)` for all quantities. The canonical hash is computed
over the textual emission.

## 14. Idempotency and integrity

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

## 15. Single naive baseline interface

The S3 contract consumes a single naive baseline. The baseline name, type,
formula, cutoff, and policy version are frozen in
`docs/forecast-quality/s3-naive-baseline-decision.md`. The S3 contract
preserves the model-vs-baseline comparison identity required by §16.

```text
NAIVE_BASELINE_NAME=PRIOR_SEASON_ANALOG_DAY_ACTUAL
NAIVE_BASELINE_TYPE=POINT_FORECAST
NAIVE_BASELINE_POINT_FORECAST_ONLY=true
NAIVE_BASELINE_P80_STATUS=NOT_COMPUTABLE
NAIVE_BASELINE_P90_STATUS=NOT_COMPUTABLE
NAIVE_BASELINE_P80_P90_REASON=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
```

The baseline is point-only. The baseline P80 / P90 forecasts are
`NOT_COMPUTABLE`. The S3 bundle reports `metric_status=NOT_COMPUTABLE` and
`reason_code=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` for any
head-to-head comparison that requires a baseline P80 / P90 forecast.

```text
FARM_BREAKDOWN_REQUIRED=true
```

```text
BASELINE_P80_COVERAGE_COMPARISON=BLOCKED
BASELINE_P90_COVERAGE_COMPARISON=BLOCKED
BASELINE_P80_P90_PEAK_COMPARISON=BLOCKED
BASELINE_INTERVAL_WIDTH_COMPARISON=BLOCKED
```

## 16. Comparison delta semantics — F-08 close

### 16.1 Non-negative loss deltas

For non-negative loss metrics (lower is better), the comparison delta is:

```text
loss_delta = model_loss - baseline_loss
positive = model is worse than baseline
negative = model is better than baseline
zero = tie
```

This convention applies to:

```text
MAE, WAPE, sMAPE, MAPE,
absolute peak errors
absolute cumulative errors
```

The S3 bundle publishes the following non-negative loss deltas:

```text
daily_mae_delta
daily_wape_delta
daily_smape_delta
daily_mape_delta
single_day_peak_date_absolute_error_delta_q
single_day_peak_quantity_absolute_error_delta_q
sustained_7day_start_date_absolute_error_delta_q
sustained_7day_quantity_absolute_error_delta_q
```

### 16.2 Signed deltas

Signed deltas express direction only. They MUST NOT be used to claim
"better" or "worse".

```text
signed_bias_delta = model_signed_bias - baseline_signed_bias
signed_cumulative_error_delta = model_signed_cumulative_error - baseline_signed_cumulative_error
```

The S3 bundle publishes the signed deltas with `metric_status=COMPARED`
and `reason_code=SIGNED_DIRECTION_ONLY`. A reader MUST NOT interpret the
sign of `signed_bias_delta` as "better" or "worse" without converting to
absolute magnitude.

### 16.3 Absolute-bias magnitude deltas

```text
absolute_bias_magnitude_delta = abs(model_signed_bias) - abs(baseline_signed_bias)
absolute_cumulative_bias_magnitude_delta = abs(model_signed_cumulative_error) - abs(baseline_signed_cumulative_error)
```

The S3 bundle publishes these magnitude deltas. The same better/worse
convention as §16.1 applies:

```text
positive = model is worse than baseline (on absolute magnitude)
negative = model is better than baseline
zero = tie
```

### 16.4 Coverage and interval deltas

```text
p80_coverage_delta = model_p80_coverage - baseline_p80_coverage
p90_coverage_delta = model_p90_coverage - baseline_p90_coverage
interval_width_delta = model_interval_width - baseline_interval_width
```

The S3 bundle publishes these deltas. Both `p80_coverage_delta`,
`p90_coverage_delta`, and `interval_width_delta` are gated on the
quantile-semantics verification; until then the bundle reports
`metric_status=NOT_COMPUTABLE` and the corresponding `reason_code`.

### 16.5 Mandatory comparison fields

The S3 bundle MUST publish every field below; missing fields are not
allowed. Some fields are always computable; others are gated on upstream
verification.

```text
daily_mae_delta
daily_wape_delta
daily_smape_delta
daily_mape_delta
single_day_peak_date_absolute_error_delta_q
single_day_peak_quantity_absolute_error_delta_q
sustained_7day_start_date_absolute_error_delta_q
sustained_7day_quantity_absolute_error_delta_q
p80_coverage_delta
p90_coverage_delta
interval_width_delta
absolute_bias_magnitude_delta
absolute_cumulative_bias_magnitude_delta
signed_bias_delta
signed_cumulative_error_delta
```

For each field that cannot be computed, the bundle publishes:

```text
metric_status=NOT_COMPUTABLE
reason_code=<specific reason from the table above>
```

The S3 bundle NEVER silently omits a comparison field.

## 17. What S3 does NOT include

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
