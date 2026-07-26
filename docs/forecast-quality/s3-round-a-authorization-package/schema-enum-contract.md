# Round A Schema and Enum Contract

This file freezes the public domain shape for the future Round A
implementation. It does not create an application schema or database table.
All types below are Python domain types; database numeric IDs, persistence
models, migrations, and HTTP models are out of scope.

## Exact public schemas

`ActualPhysicalRecord` is exactly three fields:

| field | type | required | canonical | identity | validation | owner |
|---|---|---|---|---|---|---|
| `physical_key` | `str` | yes | yes | yes | non-empty stable physical grain | `schemas.py` |
| `stable_actual_identity` | `str` | yes | yes | yes | non-empty immutable identity | `schemas.py` |
| `actual_value_kg` | `Decimal` | yes | yes | yes | finite, six-place, non-negative business quantity | `schemas.py` |

```text
ActualPhysicalRecord_FIELDS=physical_key,stable_actual_identity,actual_value_kg
ActualPhysicalRecord_FIELD_COUNT=3
```

`S3EvaluationInput` is exactly six fields. `breakdown_spec` is a separate
argument to the daily calculator. `source_snapshot` is a separate argument
to the baseline resolver. `coverage_ratio` is an output/audit field and is
not an input field.

| field | type | required | canonical | identity | validation | owner |
|---|---|---|---|---|---|---|
| `rows` | `Sequence[S3BindingRow]` | yes | yes | through row-set hash | deterministic input ordering before hash | `schemas.py` |
| `s2_run_identity` | `str` | yes | yes | yes | non-empty exact S2 identity | `schemas.py` |
| `s2_manifest_identity` | `str` | yes | yes | yes | non-empty exact S2 manifest identity | `schemas.py` |
| `s2_binding_row_set_hash` | `str` | yes | yes | yes | lowercase SHA-256 | `schemas.py` |
| `metric_policy_version` | `FrozenVersion` | yes | yes | yes | frozen S3 metric policy | `schemas.py` |
| `baseline_policy_version` | `FrozenVersion` | yes | yes | yes | frozen baseline policy | `schemas.py` |

```text
S3EvaluationInput_FIELDS=rows,s2_run_identity,s2_manifest_identity,s2_binding_row_set_hash,metric_policy_version,baseline_policy_version
S3EvaluationInput_FIELD_COUNT=6
S3_EVALUATION_INPUT_FORBIDDEN_FIELDS=coverage_ratio,breakdown_spec,metric_input_mask_policy_version,baseline_snapshot
```

`S3BindingRow` is the domain projection of one frozen S2 binding row. Its
required semantic fields are:

```text
S3_BINDING_ROW_FIELDS=
forecast_business_key,actual_physical_key,stable_actual_identity,
forecast_value_kg,actual_value_kg,forecast_quantile,forecast_horizon_days,
forecast_target_date,forecast_cutoff_at,s2_status,
season_business_key,farm_business_key,subfarm_business_key,
variety_business_key,model_identity,actual_visibility_timestamp
```

The actual fields may be nullable only for an upstream non-comparable row;
the calculator must not turn that row into a zero. A comparable row requires
an exact actual pair. Numeric business quantities are `Decimal`; dates are
`date`; cutoffs and visibility timestamps are timezone-aware `datetime`.
All business-key, quantile, target-date, cutoff, status, and authority fields
participate in the row-set identity or its validated source evidence.

Other domain schemas:

| schema | required fields | canonical/identity rule | owner |
|---|---|---|---|
| `FarmDailyActualAggregate` | `season_business_key`, `farm_business_key`, `variety_business_key`, `target_date`, `actual_value_kg`, `unique_actual_physical_rows` | exact deduplicated physical rows; no max-single-subfarm substitution | `schemas.py` |
| `FarmDailyForecastAggregate` | `season_business_key`, `farm_business_key`, `variety_business_key`, `target_date`, `forecast_cutoff_at`, `model_identity`, `forecast_quantile`, `forecast_horizon_days`, `forecast_value_kg`, `source_forecast_business_keys` | exact deduplicated subfarm forecast sum grouped by every listed forecast identity axis | `schemas.py` |
| `MetricValueCell` | `metric_value`, `metric_status`, `reason_code` | status/reason is always present; value is null only when contract says not computable | `schemas.py` |
| `DailyMetricResult` | S2 identities, policy versions, six-axis breakdown, four S2 counters, `coverage_ratio`, mask identity, input count/quantile, unique actual count, MAPE counters, metric cells | all identity and audit fields bind canonical hash; no database IDs | `schemas.py` |
| `BreakdownSpec` | `forecast_horizon_days`, `farm_business_key`, `subfarm_business_key`, `variety_business_key`, `season_business_key`, `model_identity` | six required axes; separate calculator argument | `schemas.py` |
| `BaselineRequest` | current target date, current season identity, prior season identity, farm/subfarm/variety keys, current forecast cutoff, requested quantile, policy versions | current cutoff controls source visibility; P50 is point-only and P80/P90 are explicitly non-computable | `schemas.py` |
| `BaselineSourceSnapshot` | snapshot identity/hash, row-set hash, visibility manifest hash, visibility cutoff, `actual_rows` with prior season/date/grain/value/revision visibility fields | independent source snapshot; never reuse model S2 row set | `schemas.py` |
| `BaselineResult` | point forecast value, requested/baseline quantile, source snapshot identities, analog date, comparison availability, status, reason code, canonical hash | P50 computes a point result; P80/P90 return BLOCKED, NOT_COMPUTABLE, BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED, and null point value | `schemas.py` |

`FarmDailyForecastAggregate` is a public Round A schema. Its forecast value is
the sum of exact, non-duplicated subfarm forecast business keys. P50, P80 and
P90 rows remain separate, as do forecast cutoffs, model identities and
horizons. A repeated forecast business key is a structural failure; selecting
the maximum subfarm row or silently merging quantiles is forbidden.

## Baseline canonical payload field sets

The root payload is exactly the following 26 fields, with
`per_breakdown_cell` as its one container field:

```text
BASELINE_CANONICAL_ROOT_FIELDS=
schema_version,s2_run_identity,s2_manifest_identity,s2_binding_row_set_hash,
baseline_source_snapshot_identity,baseline_source_snapshot_hash,
baseline_source_row_set_hash,baseline_source_visibility_manifest_hash,
baseline_source_visibility_cutoff_at,baseline_policy_version,
season_analog_mapping_policy_version,prior_season_identity,baseline_grain,
baseline_horizon_rule,breakdown_dimensions,s2_total_binding_row_count,
s2_comparable_binding_row_count,s2_excluded_binding_row_count,
s2_not_computable_binding_row_count,coverage_ratio,
metric_input_mask_policy_version,metric_input_mask_hash,metric_input_row_count,
metric_input_quantile,unique_actual_physical_row_count,per_breakdown_cell
BASELINE_CANONICAL_ROOT_FIELD_COUNT=26
```

Each `per_breakdown_cell` payload is exactly these 15 fields:

```text
BASELINE_CANONICAL_CELL_FIELDS=
baseline_point_forecast_kg,s2_total_binding_row_count,
s2_comparable_binding_row_count,s2_excluded_binding_row_count,
s2_not_computable_binding_row_count,coverage_ratio,
metric_input_mask_policy_version,metric_input_mask_hash,metric_input_row_count,
metric_input_quantile,unique_actual_physical_row_count,mape_eligible_row_count,
mape_zero_actual_row_count,metric_status,reason_code
BASELINE_CANONICAL_CELL_FIELD_COUNT=15
BASELINE_ROOT_FIELD_SET_EQUALITY=true
BASELINE_CELL_FIELD_SET_EQUALITY=true
BASELINE_CANONICAL_FIELD_NAME_DRIFT_COUNT=0
```

## Public enums

The contract explicitly closes these values:

```text
MetricStatus={COMPUTED,COMPARED,NOT_COMPUTABLE,NOT_VERIFIED,INSUFFICIENT_SAMPLE}
ComparisonAvailability={AVAILABLE,BLOCKED}
SupportedQuantile={P50,P80,P90}
CrossQuantileInputSource={S2_IMMUTABLE_BACKTEST_BINDING}
FrozenVersion={METRIC_INPUT_MASK_V1,NAIVE_BASELINE_POLICY_V1,SEASON_ANALOG_MAPPING_V1}
METRIC_INPUT_MASK_V1=v0.2-s3-metric-input-mask-v1
NAIVE_BASELINE_POLICY_V1=v0.2-s3-naive-baseline-policy-v1
SEASON_ANALOG_MAPPING_V1=v0.2-s3-season-analog-mapping-v1
```

The current contract documents 16 distinct public reason tokens. The package
uses their explicit union as the closed `ReasonCode` set so no token is
silently dropped:

```text
ReasonCode={
NONE,
NO_MAPE_ELIGIBLE_ROWS,
MAPE_DENOMINATOR_ZERO,
WAPE_DENOMINATOR_ZERO,
RELATIVE_BIAS_DENOMINATOR_ZERO,
NO_COMPLETE_7DAY_WINDOW,
QUANTILE_SEMANTICS_NOT_VERIFIED,
BELOW_MINIMUM,
BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED,
COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING,
SIGNED_DIRECTION_ONLY,
PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE,
NO_PRIOR_SEASON_ANALOG_DAY,
NO_PRIOR_SEASON_ANALOG_ACTUAL,
BASELINE_SOURCE_NOT_VISIBLE_AT_CURRENT_FORECAST_CUTOFF,
NO_S2_BINDING_ROWS
}
ReasonCode_MEMBER_COUNT=16
PUBLIC_REASON_CODE_CLOSED_SET_EQUALITY=true
```

No internal reason enum is needed by the frozen domain contract. Structural
failures are public exceptions and ordinary non-computable states are public
`ReasonCode` values. Therefore:

```text
InternalReasonCode={}
INTERNAL_REASON_CODE_PRESENT=false
INTERNAL_REASON_CODE_MEMBER_COUNT=0
PUBLIC_INTERNAL_REASON_CODE_DISJOINT=true
```

If a future implementation needs an internal-only diagnostic enum, it must
be proposed separately, must never be serialized as `ReasonCode`, and must
be added to this package by an independent review.

## Exceptions and forbidden substitutes

The only public exception hierarchy is:

```text
ForecastQualityError
  S3StructuralDuplicateError
  S3DecimalAssertionError
  S3CanonicalIdentityConflictError
  S3ContractInvariantViolationError
```

Do not add `S3BaselineNotComputableError` or
`S3BreakdownInsufficientSampleError`; those are status/reason outcomes.
Do not use a database ID, latest row, receipt, arrival, model output, zero
fill, native float, or implicit timezone as canonical domain evidence.
