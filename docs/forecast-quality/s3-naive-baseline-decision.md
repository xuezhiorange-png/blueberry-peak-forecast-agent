# V0.2-S3 Single Naive Baseline Decision

> Target: V0.2-S3 (FORECAST_QUALITY_METRICS_AND_ONE_NAIVE_BASELINE)
> Companion: `docs/forecast-quality/s3-quality-metrics-contract.md`
> Scope: single naive baseline selection and frozen point-forecast formula
> Base: `b873dd63fc0d5b6375f94674abbd24a94d915f3c`
> Source authority: `docs/forecast-quality/q2b-point-in-time-backtest-runner-contract.md` (S2 binding + manifest)

```text
NAIVE_BASELINE_COUNT=1
NAIVE_BASELINE_NAME=PRIOR_SEASON_ANALOG_DAY_ACTUAL
NAIVE_BASELINE_TYPE=POINT_FORECAST
NAIVE_BASELINE_POINT_FORECAST_ONLY=true
NAIVE_BASELINE_POLICY_VERSION=v0.2-s3-naive-baseline-policy-v1
MODEL_RETRAINING=false
MODEL_PARAMETER_TUNING=false
UPSTREAM_CONTRACT_AMENDMENT_ACCEPTED=false
```

## 1. Single baseline freeze

```text
NAIVE_BASELINE_COUNT=1
```

S3 publishes exactly one naive baseline. Multi-baseline comparison is
**not** part of the S3 contract. The single baseline is the only naive
signal used to compare the model against.

```text
NAIVE_BASELINE_NAME=PRIOR_SEASON_ANALOG_DAY_ACTUAL
NAIVE_BASELINE_TYPE=POINT_FORECAST
NAIVE_BASELINE_POINT_FORECAST_ONLY=true
```

The frozen baseline is the prior-season analog-day actual. The baseline
predicts the target date with the **exact** prior-season actual label at
the same `(farm_business_key, subfarm_business_key, variety_business_key)`
grain on the **analog day** defined by the season-day index mapping.

```text
BASELINE_POINT_FORECAST_SEMANTIC=P50_COMPARISON_POINT_ONLY
NAIVE_BASELINE_P80_STATUS=NOT_COMPUTABLE
NAIVE_BASELINE_P90_STATUS=NOT_COMPUTABLE
NAIVE_BASELINE_P80_P90_REASON=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
```

The baseline is point-only. The same point value MUST NOT be copied into
P80 / P90. The S3 bundle reports `metric_status=NOT_COMPUTABLE` and
`reason_code=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` for any
head-to-head comparison that requires a baseline P80 / P90 forecast.

```text
BASELINE_P80_COVERAGE_COMPARISON=BLOCKED
BASELINE_P90_COVERAGE_COMPARISON=BLOCKED
BASELINE_P80_P90_PEAK_COMPARISON=BLOCKED
BASELINE_INTERVAL_WIDTH_COMPARISON=BLOCKED
PUBLIC_APPLICATION_API=false
INTERNAL_PYTHON_APPLICATION_SERVICE_ALLOWED=true
```

## 2. Rejected candidates

The audit compares four candidate baselines. The frozen choice is the
only one that survives.

| candidate | uses post-cutoff data | horizon support | cold-start | replay | comment |
|---|---|---|---|---|---|
| LAST_VISIBLE_ACTUAL | false | partial | fails | deterministic | leaks the most-recent-known value; horizon-blind |
| TRAILING_VISIBLE_MEAN | false | partial | degrades | deterministic | window-blind; no horizon awareness |
| SEASON_TO_DATE_VISIBLE_MEAN | false | partial | partial | deterministic | in-season bias; promotes the latest view |
| PRIOR_SEASON_ANALOG_DAY_ACTUAL | false | full | fail-closed | deterministic | fail-closed on missing prior analog; deterministic per-grain | **frozen** |

## 3. Frozen formula

```text
current_target_season_day_index = deterministic_season_day_index(
    current_target_date,
    current_season_calendar_authority
)

prior_target_date = resolve_prior_season_analog_date(
    prior_season_identity,
    current_target_season_day_index,
    season_analog_mapping_policy_version
)

baseline_point_forecast_kg = exact prior-season actual label at
    (
      prior_season_identity,
      same farm_business_key,
      same subfarm_business_key,
      same variety_business_key,
      prior_target_date
    )
```

The baseline is a single point value (one actual label). It is NOT a
mean over a window. The S3 contract does not retain a single-day mean
as a baseline candidate.

```text
BASELINE_FORMULA_TYPE=POINT_FORECAST
WINDOW_START_OFFSET_DAYS=N/A
WINDOW_END_OFFSET_DAYS=N/A
WINDOW_REQUIRED_DAY_COUNT=1
BASELINE_WINDOW_MISSING_DAY_POLICY=NOT_APPLICABLE_POINT_FORECAST
```

## 4. Season-analog mapping policy

```text
SEASON_ANALOG_MAPPING_POLICY_VERSION=v0.2-s3-season-analog-mapping-v1
SEASON_DAY_INDEX_AUTHORITY=current_season_calendar_authority
```

The mapping from a current target date to a prior-season target date uses
the current-season calendar day index. The day index is computed by
`deterministic_season_day_index(current_target_date, current_season_calendar_authority)`.

### 4.1 Leap-day policy — F-17 round 2 close

```text
LEAP_DAY_POLICY=MAP_FEB29_TO_PRIOR_FEB28
SEARCH_EARLIER_LEAP_SEASON=false
DATE_SKEW_REASON=LEAP_DAY_ADJUSTED
```

```text
WHEN_CURRENT_TARGET_DATE_IS_FEB29=resolve the immediately prior season analog date as Feb 28 when that prior season has no Feb 29
WHEN_PRIOR_SEASON_HAS_FEB29=map Feb 29 to Feb 29
SEARCH_AN_EARLIER_LEAP_SEASON=false
```

The prior policy `LEAP_DAY_POLICY=SKIP_BUT_MAP_TO_LEAP_ADJUSTED_DAY_INDEX`
combined a "skip non-leap prior seasons" rule with a "map to the prior
season's Feb 28" rule. The two clauses are mutually exclusive for a
single prior season. The frozen policy is the "map to prior Feb 28"
rule only. The prior season is never skipped; the mapping lands on
the prior Feb 28 when the prior season is not a leap year.

```text
UNEQUAL_SEASON_LENGTH_POLICY=TRUNCATE_TO_SHORTER_SEASON_DAY_COUNT
```

When the prior season is shorter than the current season (e.g. a season
ending earlier than the current season's last day), the mapping
truncates to the shorter season's day count. Rows mapping to days
beyond the prior season's last day are `NOT_COMPUTABLE`.

```text
SEASON_BOUNDARY_POLICY=PRIOR_SEASON_TARGET_DATE_REQUIRED
```

The prior season MUST have a target date at the mapped day index.
If the prior season has no day at that index, the cell is
`NOT_COMPUTABLE` with `reason_code=NO_PRIOR_SEASON_ANALOG_DAY`.

```text
MISSING_ANALOG_DATE_POLICY=NOT_COMPUTABLE
```

When the prior season has no actual label at the analog date, the cell
is `NOT_COMPUTABLE` with `reason_code=NO_PRIOR_SEASON_ANALOG_ACTUAL`.

## 5. Baseline source visibility — F-07 close

The baseline visibility rule is bound to a separate timeline. The visible
horizon for the prior-season source is the current forecast_cutoff_at.
The prior-season actual label revision must be visible at or before
the current forecast_cutoff_at.

## 5. Baseline source visibility — F-11 round 2 close

The baseline visibility reference is bound to the **current** forecast
cutoff, not the prior-season forecast cutoff. The prior-season forecast
cutoff is not relevant to the current baseline's visibility decision.

```text
BASELINE_VISIBILITY_REFERENCE=CURRENT_FORECAST_CUTOFF
BASELINE_SOURCE_VISIBILITY_RULE=PRIOR_ANALOG_ACTUAL_REVISION_VISIBLE_AT_OR_BEFORE_CURRENT_FORECAST_CUTOFF
PRIOR_ANALOG_ACTUAL_ALLOWED_IF=revision_visibility_timestamp <= current_forecast_cutoff_at
VISIBILITY_RELATIVE_TO_PRIOR_SEASON_FORECAST_CUTOFF=NOT_RELEVANT
```

The prior wording

```text
The baseline MUST NOT use the prior-season future target dates
as visible at the current forecast_cutoff_at.
```

was over-restrictive. The correct explanation is:

```text
A prior-season analog target may have been future relative to the
prior-season forecast cutoff, but it is eligible for the current
baseline when its actual-label revision was already visible at or
before the current forecast_cutoff_at.
```

```text
BASELINE_PRIOR_SEASON_ANALOG_ACTUAL_VISIBILITY=ALLOWED_WHEN_VISIBLE_BY_CURRENT_FORECAST_CUTOFF
BASELINE_PRIOR_SEASON_OLD_FORECAST_CUTOFF_CHECK_REQUIRED=false
BASELINE_VISIBILITY_ACCEPTANCE_TEST=ALLOW_PRIOR_ANALOG_ACTUAL_VISIBLE_BY_CURRENT_CUTOFF_AND_REJECT_LATER_REVISION
```

Frozen acceptance test cases (the baseline visibility decision is made
against the current forecast_cutoff_at, NOT against whether the
analog target was future relative to the prior-season forecast cutoff):

```text
CASE_VISIBLE:
  prior-season analog actual
  revision_visibility_timestamp <= current_forecast_cutoff_at
  expected=ALLOWED

CASE_NOT_VISIBLE:
  prior-season analog actual
  revision_visibility_timestamp > current_forecast_cutoff_at
  expected=REJECTED
  reason_code=BASELINE_SOURCE_NOT_VISIBLE_AT_CURRENT_FORECAST_CUTOFF
```

The baseline binds the following identities:

```text
baseline_source_snapshot_identity
baseline_source_snapshot_hash
baseline_source_row_set_hash
baseline_source_visibility_manifest_hash
baseline_source_visibility_cutoff_at
prior_season_identity
season_analog_mapping_policy_version
baseline_policy_version
```

The baseline MUST NOT reuse the model-evaluation S2 binding row set as
its historical source. The baseline has its own visibility timeline and
its own source snapshot.

```text
BASELINE_REUSES_MODEL_S2_BINDING_ROWSET=false
```

## 6. Forecasting horizons

The baseline supports all frozen S3 horizons:

```text
SUPPORTED_HORIZONS_DAYS=7,14,21
```

The baseline's predicted value for a target date `t` is the prior
season's actual label at the analog date. The analog date is distinct
for each current target date `t`, so the horizon is encoded in the
target date and the analog mapping respects the horizon.

## 7. Cold-start and missing-history policy

```text
BASELINE_COLD_START_POLICY=FAIL_CLOSED_NO_HISTORY_NO_PREDICTION
BASELINE_COLD_START_SAFE=false
BASELINE_COLD_START_FAILS_CLOSED=true
BASELINE_COLD_START_OUTPUT=NOT_COMPUTABLE
BASELINE_MISSING_HISTORY_POLICY=NOT_COMPUTABLE
```

When the prior season has no `actual` label at the analog date, the
baseline is `NOT_COMPUTABLE` for that breakdown cell. The cell is
reported with `metric_status=NOT_COMPUTABLE` and `reason_code=
NO_PRIOR_SEASON_ANALOG_ACTUAL`. The baseline never silently substitutes
a zero, a global mean, the current latest row, or any leakage source.

```text
BASELINE_FALLS_BACK_TO_ZERO=false
BASELINE_USES_LATEST_ROWS=false
BASELINE_USES_MODEL_FORECAST=false
BASELINE_USES_RECEIPT_PROXY=false
```

This cold-start policy is intentional: the contract binds the audit to
"fail closed" rather than to "synthesize a baseline". A new farm, new
variety, or new season MUST surface as `NOT_COMPUTABLE` until the prior
season completes with at least one actual label at the analog date.

## 8. Decimal arithmetic

```text
BASELINE_DECIMAL_POLICY=Decimal_one_e_minus_six_ROUND_HALF_EVEN
```

The baseline value is copied from the prior-season actual label, which
is itself a `Decimal` with six decimal places. The canonical payload
emits `str(decimal_value)`. No native `float`, NumPy float, or binary
float participates in the canonical business arithmetic.

## 9. Canonical identity

The canonical hash of the baseline bind is computed over:

```text
BASELINE_METRIC_INPUT_MASK_POLICY_VERSION=v0.2-s3-metric-input-mask-v1
BASELINE_METRIC_INPUT_QUANTILE=P50
BASELINE_POINT_METRIC_MASK=S2_STATUS_COMPARABLE_AND_FORECAST_QUANTILE_P50 AND BASELINE_POINT_FORECAST_COMPUTABLE
BASELINE_METRIC_INPUT_MASK_HASH_REQUIRED=true
BASELINE_UNIQUE_ACTUAL_PHYSICAL_ROW_COUNT_REQUIRED=true
BASELINE_CANONICAL_MASK_IDENTITY_ALIGNED_WITH_METRIC_CONTRACT=true
BASELINE_CANONICAL_S2_STATUS_COUNTER_COUNT=5
BASELINE_CANONICAL_MASK_IDENTITY_RETAINED=true
METRIC_MASK_REPLACES_S2_STATUS_COUNTERS=false
S2_STATUS_COUNTERS_RETAINED_WITH_METRIC_MASK=true

S2_STATUS_COUNTER_ROLE = audit the complete upstream binding population and its row statuses
METRIC_INPUT_MASK_ROLE = identify the exact metric-specific subset used in calculation

PAYLOAD_ROOT_S2_COUNTER_SCOPE = FULL_BASELINE_EVALUATION_INPUT
PER_BREAKDOWN_CELL_S2_COUNTER_SCOPE = EXACT_BREAKDOWN_CELL_INPUT

S2_TOTAL_BINDING_ROW_COUNT_ZERO_STATUS=NOT_COMPUTABLE
S2_TOTAL_BINDING_ROW_COUNT_ZERO_REASON=NO_S2_BINDING_ROWS

metric_input_mask_hash covers:
  metric_input_mask_policy_version
  S2 status predicate
  P50 quantile predicate
  baseline computable predicate
  breakdown identity
  S2 source row-set identity
  baseline source snapshot identity
  baseline source row-set hash

BASELINE_CANONICAL_HASH_PAYLOAD={
  schema_version,
  s2_run_identity,
  s2_manifest_identity,
  s2_binding_row_set_hash,
  baseline_source_snapshot_identity,
  baseline_source_snapshot_hash,
  baseline_source_row_set_hash,
  baseline_source_visibility_manifest_hash,
  baseline_source_visibility_cutoff_at,
  baseline_policy_version,
  season_analog_mapping_policy_version,
  prior_season_identity,
  baseline_grain,
  baseline_horizon_rule,
  breakdown_dimensions,
  s2_total_binding_row_count,
  s2_comparable_binding_row_count,
  s2_excluded_binding_row_count,
  s2_not_computable_binding_row_count,
  coverage_ratio,
  metric_input_mask_policy_version,
  metric_input_mask_hash,
  metric_input_row_count,
  metric_input_quantile,
  unique_actual_physical_row_count,
  per_breakdown_cell: {
    baseline_point_forecast_kg,
    s2_total_binding_row_count,
    s2_comparable_binding_row_count,
    s2_excluded_binding_row_count,
    s2_not_computable_binding_row_count,
    coverage_ratio,
    metric_input_mask_policy_version,
    metric_input_mask_hash,
    metric_input_row_count,
    metric_input_quantile,
    unique_actual_physical_row_count,
    mape_eligible_row_count,
    mape_zero_actual_row_count,
    metric_status,
    reason_code
  }
}
```

The baseline canonical hash payload binds both the upstream S2 status
counters (audit the complete upstream binding population) and the
metric input mask identity (identify the exact metric-specific subset).
The two field groups serve different roles and MUST both be present at
payload root and at the per-breakdown-cell level.

```text
coverage_ratio = s2_comparable_binding_row_count / s2_total_binding_row_count
```

The baseline canonical hash payload MUST bind the metric input mask
identity at both the payload root and at the per-breakdown-cell level,
so the baseline can never be replayed against a different metric input
mask than the metric contract.

```text
BASELINE_METRIC_INPUT_MASK_AT_PAYLOAD_ROOT=true
BASELINE_METRIC_INPUT_MASK_AT_PER_BREAKDOWN_CELL=true
```

The hash payload does NOT carry:

```text
database numeric IDs
insertion timestamps
runtime host or worker IDs
database row order
unbounded raw business rows
credentials or connection strings
```

The baseline canonical hash uses the same hash algorithm as the S3
metrics contract.

## 10. Fair comparison with the model

The model and the baseline MUST use the same inputs and outputs:

```text
REQUIRED_BREAKDOWN_AXES=forecast_horizon_days, farm_business_key, subfarm_business_key, variety_business_key, season_business_key, model_identity
REQUIRED_BREAKDOWN_AXIS_COUNT=6
BASELINE_DECISION_REQUIRED_BREAKDOWN_AXIS_COUNT=6
BASELINE_BREAKDOWN_AXES_ALIGNED_WITH_METRIC_CONTRACT=true
QUALITY_CONTRACT_REQUIRED_BREAKDOWN_AXIS_COUNT=6
READINESS_MATRIX_REQUIRED_BREAKDOWN_AXIS_COUNT=6
BREAKDOWN_AXIS_SET_IDENTITY=true

IDENTICAL_S2_BINDING_ROWS=true
IDENTICAL_ACTUAL_LABELS=true
IDENTICAL_METRIC_POLICY=true
IDENTICAL_BREAKDOWN_POLICY=true
```

The model and the baseline MUST be evaluated on the **same S2 binding row
set** with the **same metric formulas** and the **same breakdown axes**.
The breakdown axes used for both the model evaluation and the baseline
evaluation are the six-axis set above; the baseline does not silently
use a different breakdown axes set than the metric contract. The S3
bundle publishes both model metrics and baseline metrics per breakdown
cell. The difference is that the model's underlying forecast is
the model's raw P50 / P80 / P90; the baseline's underlying forecast is
the prior-season analog-day actual.

When the prior season has fewer comparable rows than the model, the S3
bundle reports two distinct counts:

```text
COMMON_COMPARABLE_SET=rows where BOTH model and baseline are COMPUTABLE
MODEL_ONLY_COMPARABLE_SET=rows where model is COMPUTABLE but baseline is NOT_COMPUTABLE
```

The model metrics are reported over the **model-evaluated row set**.
The baseline metrics are reported over the **baseline-evaluated row
set**. The head-to-head comparison metric is reported over the
**COMMON_COMPARABLE_SET** only. The bundle does NOT delete the model's
rows because the baseline cannot score them. The contract binds
"include, do not drop" — the model and the baseline each have their own
auditable coverage.

```text
MODEL_EVALUATED_OVER=model_evaluated_row_set
BASELINE_EVALUATED_OVER=baseline_evaluated_row_set
HEAD_TO_HEAD_OVER=COMMON_COMPARABLE_SET
MODEL_ONLY_DELETION_FOR_BASELINE=false
```

## 11. Comparison deltas — F-08 close

The S3 contract preserves the model-vs-baseline comparison identity
required by §16 of `s3-quality-metrics-contract.md`. Comparison fields
are split into three groups, each with its own
`comparison_availability`, `metric_status`, `reason_code`, and
`external_blocker`. The baseline decision document freezes the
baseline-side classification for all three groups.

```text
DAILY_POINT_COMPARISON_FIELDS=daily_mae_delta, daily_wape_delta, daily_smape_delta, daily_mape_delta, absolute_bias_magnitude_delta, signed_bias_delta
DAILY_POINT_COMPARISON_READINESS=READY_PENDING_SEPARATE_S3_IMPLEMENTATION_AUTHORIZATION
BASELINE_DAILY_POINT_COMPARISON_STATUS=IMPLEMENTATION_OBLIGATION
DAILY_POINT_COMPARISON_AVAILABILITY=AVAILABLE
DAILY_POINT_COMPARISON_EXTERNAL_BLOCKER=none

DAILY_POINT_LOSS_DELTA_FIELDS=daily_mae_delta, daily_wape_delta, daily_smape_delta, daily_mape_delta, absolute_bias_magnitude_delta
DAILY_POINT_LOSS_DELTA_COMPARISON_AVAILABILITY=AVAILABLE
DAILY_POINT_LOSS_DELTA_METRIC_STATUS=COMPUTED
DAILY_POINT_LOSS_DELTA_REASON_CODE=NONE
DAILY_POINT_LOSS_DELTA_EXTERNAL_BLOCKER=none
DAILY_POINT_LOSS_DELTA_SEMANTICS=positive=model worse, negative=model better, zero=tie

DAILY_POINT_SIGNED_DELTA_FIELDS=signed_bias_delta
DAILY_POINT_SIGNED_DELTA_COMPARISON_AVAILABILITY=AVAILABLE
DAILY_POINT_SIGNED_DELTA_METRIC_STATUS=COMPARED
DAILY_POINT_SIGNED_DELTA_REASON_CODE=SIGNED_DIRECTION_ONLY
DAILY_POINT_SIGNED_DELTA_EXTERNAL_BLOCKER=none
SIGNED_BIAS_DELTA_BETTER_WORSE_INTERPRETATION_ALLOWED=false
SIGNED_BIAS_DELTA_DIRECTION_ONLY=true

COMPLETE_WINDOW_COMPARISON_FIELDS=absolute_cumulative_bias_magnitude_delta, signed_cumulative_error_delta, single_day_peak_date_absolute_error_delta_q, single_day_peak_quantity_absolute_error_delta_q, sustained_7day_start_date_absolute_error_delta_q, sustained_7day_quantity_absolute_error_delta_q
COMPLETE_WINDOW_COMPARISON_READINESS=BLOCKED_BY_S2_COMPLETE_DAILY_ROW_SET_AUTHORITY
BASELINE_COMPLETE_WINDOW_COMPARISON_STATUS=BLOCKED_BY_S2_COMPLETE_DAILY_ROW_SET_AUTHORITY
COMPLETE_WINDOW_COMPARISON_AVAILABILITY=BLOCKED
COMPLETE_WINDOW_COMPARISON_METRIC_STATUS=NOT_COMPUTABLE
COMPLETE_WINDOW_COMPARISON_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
COMPLETE_WINDOW_COMPARISON_EXTERNAL_BLOCKER=S2_COMPLETE_DAILY_ROW_SET_AUTHORITY

SIGNED_CUMULATIVE_ERROR_DELTA_COMPARISON_AVAILABILITY=BLOCKED
SIGNED_CUMULATIVE_ERROR_DELTA_METRIC_STATUS=NOT_COMPUTABLE
SIGNED_CUMULATIVE_ERROR_DELTA_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
SIGNED_CUMULATIVE_ERROR_DELTA_EXTERNAL_BLOCKER=S2_COMPLETE_DAILY_ROW_SET_AUTHORITY

BASELINE_QUANTILE_INTERVAL_COMPARISON_FIELDS=p80_coverage_delta, p90_coverage_delta, interval_width_delta, baseline_p80_p90_peak_comparison
BASELINE_QUANTILE_INTERVAL_COMPARISON_READINESS=FROZEN_NOT_COMPUTABLE_LIMITATION
BASELINE_QUANTILE_INTERVAL_COMPARISON_STATUS=FROZEN_NOT_COMPUTABLE_LIMITATION
BASELINE_QUANTILE_INTERVAL_COMPARISON_AVAILABILITY=BLOCKED
BASELINE_QUANTILE_INTERVAL_COMPARISON_METRIC_STATUS=NOT_COMPUTABLE
BASELINE_QUANTILE_INTERVAL_COMPARISON_REASON_CODE=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED, PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE
BASELINE_QUANTILE_INTERVAL_COMPARISON_EXTERNAL_BLOCKER=none
BASELINE_QUANTILE_INTERVAL_COMPARISON_LIMITATIONS=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED, PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE

BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED_CLASS=FROZEN_NOT_COMPUTABLE_LIMITATION
PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE_CLASS=FROZEN_NOT_COMPUTABLE_LIMITATION
BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED_IS_EXTERNAL_BLOCKER=false
PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE_IS_EXTERNAL_BLOCKER=false

MODEL_QUANTILE_PUBLICATION_EXTERNAL_GATE=P50_P80_P90_SEMANTICS_VERIFICATION
BASELINE_QUANTILE_HEAD_TO_HEAD_LIMITATION=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
BASELINE_INTERVAL_HEAD_TO_HEAD_LIMITATION=PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE

P80_COVERAGE_DELTA_COMPARISON_AVAILABILITY=BLOCKED
P80_COVERAGE_DELTA_METRIC_STATUS=NOT_COMPUTABLE
P80_COVERAGE_DELTA_REASON_CODE=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
P80_COVERAGE_DELTA_EXTERNAL_BLOCKER=none
P80_COVERAGE_DELTA_FROZEN_LIMITATION=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED

P90_COVERAGE_DELTA_COMPARISON_AVAILABILITY=BLOCKED
P90_COVERAGE_DELTA_METRIC_STATUS=NOT_COMPUTABLE
P90_COVERAGE_DELTA_REASON_CODE=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
P90_COVERAGE_DELTA_EXTERNAL_BLOCKER=none
P90_COVERAGE_DELTA_FROZEN_LIMITATION=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED

BASELINE_P80_P90_PEAK_COMPARISON_AVAILABILITY=BLOCKED
BASELINE_P80_P90_PEAK_COMPARISON_METRIC_STATUS=NOT_COMPUTABLE
BASELINE_P80_P90_PEAK_COMPARISON_REASON_CODE=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
BASELINE_P80_P90_PEAK_COMPARISON_EXTERNAL_BLOCKER=none
BASELINE_P80_P90_PEAK_COMPARISON_FROZEN_LIMITATION=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED

INTERVAL_WIDTH_DELTA_COMPARISON_AVAILABILITY=BLOCKED
INTERVAL_WIDTH_DELTA_METRIC_STATUS=NOT_COMPUTABLE
INTERVAL_WIDTH_DELTA_REASON_CODE=PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE
INTERVAL_WIDTH_DELTA_EXTERNAL_BLOCKER=none
INTERVAL_WIDTH_DELTA_FROZEN_LIMITATION=PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE

SECTION_16_WHOLE_SECTION_UNBLOCKED=false
SECTION_16_READINESS_DEFINED_PER_COMPARISON_GROUP=true
```

The bundle publishes `comparison_availability` and `metric_status`
together for every comparison field; "blocked" is expressed as
`comparison_availability=BLOCKED`, never as a `metric_status` value.

A delta that requires a baseline P80 / P90 forecast is published with
`metric_status=NOT_COMPUTABLE` and `reason_code=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED`,
not silently dropped.

For non-negative loss deltas, the convention is:

```text
loss_delta = model_loss - baseline_loss
positive = model worse
negative = model better
zero = tie
```

For signed deltas, the bundle reports direction only:

```text
signed_bias_delta = model_signed_bias - baseline_signed_bias
signed_cumulative_error_delta = model_signed_cumulative_error - baseline_signed_cumulative_error
```

For absolute-bias magnitude deltas, the same convention as non-negative
loss deltas applies, but only after `abs(...)` is applied.

## 12. What S3 does NOT include

```text
MULTI_BASELINE_COMPARISON=false
BASELINE_USES_MODEL_FORECAST=false
BASELINE_TUNING=false
PRIOR_SEASON_REPLAY=false
BASELINE_P80_QUALIFIER=false
BASELINE_P90_QUALIFIER=false
```

Multi-baseline comparison is out of scope. The baseline never uses the
model forecast as an input. The baseline is not tuned on the comparison
result. The prior season is not replayed; the baseline reads the
prior-season source rows as-is. The baseline does not provide a
P80 / P90 qualifier; only P50-equivalent point comparison is supported.
