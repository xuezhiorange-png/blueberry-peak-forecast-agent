# V0.2-S3 Single Naive Baseline Decision

> Target: V0.2-S3 (FORECAST_QUALITY_METRICS_AND_ONE_NAIVE_BASELINE)
> Companion: `docs/forecast-quality/s3-quality-metrics-contract.md`
> Scope: single naive baseline selection and frozen formula
> Base: `b873dd63fc0d5b6375f94674abbd24a94d915f3c`
> Source authority: `docs/forecast-quality/q2b-point-in-time-backtest-runner-contract.md` (S2 binding + manifest)

```text
NAIVE_BASELINE_COUNT=1
NAIVE_BASELINE_NAME=PRIOR_SEASON_SAME_GRAIN_SAME_WINDOW_MEAN
NAIVE_BASELINE_POLICY_VERSION=v0.2-s3-naive-baseline-policy-v1
MODEL_RETRAINING=false
MODEL_PARAMETER_TUNING=false
```

## 1. Single baseline freeze

```text
NAIVE_BASELINE_COUNT=1
```

S3 publishes exactly one naive baseline. Multi-baseline comparison is
**not** part of the S3 contract. The single baseline is the only naive
signal used to compare the model against.

```text
NAIVE_BASELINE_NAME=PRIOR_SEASON_SAME_GRAIN_SAME_WINDOW_MEAN
```

The frozen baseline is the prior-season same-grain same-window mean. The
baseline predicts the target date by taking the mean of the prior season's
actual value on the same `(season_business_key, farm_business_key,
subfarm_business_key, variety_business_key, target_date)` grain over the
prior season's analogous window.

## 2. Rejected candidates

The audit compares four candidate baselines. The frozen choice is the only
one that survives.

| candidate | uses post-cutoff data | horizon support | cold-start | replay | comment |
|---|---|---|---|---|---|
| LAST_VISIBLE_ACTUAL | false | partial | fails | deterministic | leaks the most-recent-known value; horizon-blind |
| TRAILING_VISIBLE_MEAN | false | partial | degrades | deterministic | window-blind; no horizon awareness |
| SEASON_TO_DATE_VISIBLE_MEAN | false | partial | partial | deterministic | in-season bias; promotes the latest view |
| PRIOR_SEASON_SAME_GRAIN | false | full | correct | deterministic | cold-start safe; horizon-aware via same grain | **frozen** |

```text
NAIVE_BASELINE_FORMULA=mean(actual_prior_season_i) over the same (farm_business_key, subfarm_business_key, variety_business_key, target_date) grain
```

```text
BASELINE_LOOKBACK_WINDOW=PRIOR_SEASON_ANALOGOUS_DATE
BASELINE_VISIBILITY_CUTOFF_RULE=AT_FORECAST_CUTOFF_FOR_PRIOR_SEASON
BASELINE_GRAIN=SEASON x FARM x SUBFARM x VARIETY x DATE
BASELINE_HORIZON_RULE=SAME_GRAIN_SAME_DATE_OFFSET
BASELINE_COLD_START_POLICY=FAIL_CLOSED_NO_HISTORY_NO_PREDICTION
BASELINE_MISSING_HISTORY_POLICY=NOT_COMPUTABLE
BASELINE_DECIMAL_POLICY=Decimal_one_e_minus_six_ROUND_HALF_EVEN
```

## 3. Hard prohibitions

```text
BASELINE_USES_POST_CUTOFF_DATA=false
BASELINE_USES_CURRENT_LATEST_ROWS=false
BASELINE_USES_MODEL_FORECAST_AS_INPUT=false
BASELINE_USES_RECEIPT_PROXY=false
BASELINE_FALLS_BACK_TO_ZERO=false
```

The baseline MUST NOT use any data after the forecast cutoff of the prior
season's bound. The baseline MUST NOT use the current latest-rows snapshot
even for cold-start. The baseline MUST NOT use the model forecast as a
naive signal. The baseline MUST NOT use factory receipt or arrival proxy
data. The baseline MUST NOT fall back to zero when history is missing —
it MUST report `NOT_COMPUTABLE` and `reason_code=NO_PRIOR_SEASON_HISTORY`.

## 4. Forecasting horizons

The baseline supports all frozen S3 horizons:

```text
SUPPORTED_HORIZONS_DAYS=7,14,21
```

The baseline's predicted value for a target date `t` is the mean of the
prior season's actual value on the same `t'` where `t'` is the prior
season's analogous date (same season-day offset). This distinguishes `t=7d`
from `t=14d` from `t=21d` because the prior-season same-grain date is
different for each horizon.

## 5. Cold-start and missing-history policy

```text
BASELINE_COLD_START_POLICY=FAIL_CLOSED_NO_HISTORY_NO_PREDICTION
BASELINE_MISSING_HISTORY_POLICY=NOT_COMPUTABLE
```

When the prior season has no `COMPARABLE` row on the same
`(farm_business_key, subfarm_business_key, variety_business_key, target_date)`
grain, the baseline is `NOT_COMPUTABLE` for that breakdown cell. The cell
is reported with `metric_status=NOT_COMPUTABLE` and
`reason_code=NO_PRIOR_SEASON_HISTORY`. The baseline never silently
substitutes a zero, a global mean, or any leakage source.

This cold-start policy is intentional: the contract binds the audit to
"fail closed" rather than to "synthesize a baseline". A new farm, new
variety, or new season MUST surface as `NOT_COMPUTABLE` until the prior
season completes with at least one comparable row.

## 6. Decimal arithmetic

```text
BASELINE_DECIMAL_POLICY=Decimal_one_e_minus_six_ROUND_HALF_EVEN
```

The baseline mean is computed in `Decimal` with six decimal places,
quantized to `METRIC_QUANTUM=1e-6` and rounded `ROUND_HALF_EVEN`. The
result is emitted as `str(decimal_value)`. No native `float` participates
in canonical business arithmetic.

## 7. Canonical identity

The canonical hash of the baseline bind is computed over:

```text
BASELINE_CANONICAL_HASH_PAYLOAD={
  schema_version,
  s2_run_identity,
  s2_manifest_identity,
  s2_binding_row_set_hash,
  baseline_policy_version,
  baseline_grain,
  baseline_horizon_rule,
  baseline_cutoff,
  breakdown_dimensions,
  per_breakdown_cell: { mean_decimal, comparable_row_count, excluded_row_count, not_computable_row_count, metric_status, reason_code }
}
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

## 8. Fair comparison with the model

The model and the baseline MUST use the same inputs and outputs:

```text
IDENTICAL_S2_BINDING_ROWS=true
IDENTICAL_ACTUAL_LABELS=true
IDENTICAL_METRIC_POLICY=true
IDENTICAL_BREAKDOWN_POLICY=true
```

The model and the baseline MUST be evaluated on the **same S2 binding row
set** with the **same metric formulas** and the **same breakdown axes**.
The S3 bundle publishes both model metrics and baseline metrics per
breakdown cell. The difference is that the model's underlying forecast is
the model's raw P50 / P80 / P90; the baseline's underlying forecast is
the prior-season same-grain same-date mean.

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

## 9. Cutoff re-derivation

The baseline prior-season cutoff is the same calendar date as the S2
forecast cutoff, MINUS one season. The re-derivation is strict:

```text
prior_season_forecast_cutoff = season_start_date_offset(forecast_cutoff, -1)
```

The baseline only reads `COMPARABLE` rows whose `label_visibility_cutoff_at`
is at or before `prior_season_forecast_cutoff`. The baseline never reads
the current season's rows when computing the prior-season mean.

## 10. Integration with S3 quality metrics

The baseline produces the same payload shape as the model at the canonical
hash boundary:

```text
-
  metric: quality_metric_name             (e.g. daily_mae, daily_wape, daily_smape, daily_mape, daily_bias_kg, daily_relative_bias, season_cumulative_*)
  baseline_name: PRIOR_SEASON_SAME_GRAIN_SAME_WINDOW_MEAN
  baseline_policy_version: v0.2-s3-naive-baseline-policy-v1
  forecast_value: <Decimal>
  actual_value: <Decimal>
  ...
```

The S3 quality metrics bundle (per `s3-quality-metrics-contract.md`)
publishes one `NaiveBaselineRun` and one `ModelBaselineComparison` per
breakdown cell. The head-to-head deltas are:

```text
delta_daily_mae             = model_daily_mae - baseline_daily_mae
delta_daily_wape            = model_daily_wape - baseline_daily_wape
delta_daily_smape           = model_daily_smape - baseline_daily_smape
delta_daily_mape            = model_daily_mape - baseline_daily_mape
delta_daily_bias_kg         = model_daily_bias_kg - baseline_daily_bias_kg
delta_season_cumulative_signed_error_kg = model_cumulative_signed_error_kg - baseline_cumulative_signed_error_kg
```

A positive delta means the model is **worse** than the baseline on the
metric; a negative delta means the model is **better**. The delta is
exactly `model - baseline`; the sign is documented and never re-flipped.

## 11. What S3 does NOT include

```text
MULTI_BASELINE_COMPARISON=false
BASELINE_USES_MODEL_FORECAST=false
BASELINE_TUNING=false
PRIOR_SEASON_REPLAY=false
```

Multi-baseline comparison is out of scope. The baseline never uses the
model forecast as an input. The baseline is not tuned on the comparison
result. The prior season is not replayed; the baseline reads the S2
binding rows as-is.
