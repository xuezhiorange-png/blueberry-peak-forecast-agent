# V0.2-S3 Round C comparison authorization freeze

DOCUMENT_STATUS=PROPOSED_AWAITING_INDEPENDENT_REVIEW
BASE_SHA=36e196d3742e8efaaa449230d86777335a337b8e
PREVIOUS_REVIEW_ID=4784117810

ROUND_C_AUTHORIZATION_DOCUMENT_COMPLETE=true
ROUND_C_IMPLEMENTATION_AUTHORIZED=false
ROUND_C_SCHEMA_CHANGE_AUTHORIZED=false
ROUND_C_MIGRATION_CHANGE_AUTHORIZED=false
ROUND_C_PRODUCTION_CODE_CHANGE_AUTHORIZED=false
ROUND_C_TEST_CHANGE_AUTHORIZED=false

READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
REAL_DATA_OPENED=false
ISSUE102_CLOSE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true

This document is the sole Round C authorization artifact. It freezes the comparison contract and the exact future implementation path union. It authorizes no implementation, schema, migration, CI, production, test, data, API, frontend, Ready transition, merge, or Issue #102 action.

## 1. Frozen requirements and boundary

ROUND_C_REQUIREMENTS=S3R-24A_DAILY_POINT_HEAD_TO_HEAD,S3R-24C_BASELINE_QUANTILE_AND_INTERVAL_HEAD_TO_HEAD,S3R-25_COMPARISON_DELTA_SEMANTICS

ROUND_C_AUTHORIZATION_DOCUMENT=true
ROUND_C_IMPLEMENTATION=false
PRODUCTION_CODE_CHANGE=false
TEST_CODE_CHANGE=false
SCHEMA_CHANGE=false
MIGRATION_CHANGE=false
CI_CHANGE=false
REAL_DATA_OPENED=false
BACKTEST_EXECUTED=false
ISSUE102_CLOSED=false

Round C is restricted to S3R-24A daily point head-to-head comparison, S3R-24C blocked baseline quantile and interval comparison, and S3R-25 comparison delta semantics. S3R-24B remains blocked. The future implementation path union remains exactly 14 paths.

## 2. Round C-only symbol ownership

ROUND_C_SYMBOL_OWNER_FROZEN=true
COMPARISON_POLICY_VERSION=v0.2-s3-comparison-policy-v1
COMPARISON_RESULT_SCHEMA_VERSION=v0.2-s3-comparison-result-v1

The only owner of the following Round C-only internal symbols is `backend/app/forecast_quality/comparison.py`:

| Symbol | Sole owner |
| --- | --- |
| `ComparisonName` | `backend/app/forecast_quality/comparison.py` |
| `ComparisonResult` | `backend/app/forecast_quality/comparison.py` |
| `ComparisonInputRow` | `backend/app/forecast_quality/comparison.py` |
| `ComparisonBaselineRecord` | `backend/app/forecast_quality/comparison.py` |
| `COMPARISON_POLICY_VERSION` | `backend/app/forecast_quality/comparison.py` |
| `COMPARISON_RESULT_SCHEMA_VERSION` | `backend/app/forecast_quality/comparison.py` |
| `compute_model_baseline_comparisons` | `backend/app/forecast_quality/comparison.py` |

`ComparisonAvailability`, `MetricStatus`, and `ReasonCode` continue to reuse the existing `enums.py` definitions. No second status vocabulary or reason-code vocabulary may be introduced. Future `persistence.py` may import and re-export compatibility names, but it is not an owner of the comparison domain symbols.

## 3. Frozen comparison input function

The exact future function signature is:

```python
def compute_model_baseline_comparisons(
    *,
    evaluation_input: S3EvaluationInput,
    breakdown_spec: BreakdownSpec,
    baseline_records: Sequence[ComparisonBaselineRecord],
) -> tuple[ComparisonResult, ...]:
    ...
```

`ComparisonBaselineRecord` is exactly:

```python
@dataclass(frozen=True)
class ComparisonBaselineRecord:
    request: BaselineRequest
    snapshot: BaselineSourceSnapshot
    result: BaselineResult
```

Input authority is frozen:

```text
model/current-actual authority = S3EvaluationInput.rows
baseline authority = BaselineRequest + BaselineSourceSnapshot + BaselineResult
```

The function must reject or fail closed for all of the following association methods:

- positional `zip` association;
- database row-order association;
- latest-baseline fallback;
- caller-provided arbitrary join key;
- persisted aggregate metric rows used as common-set row authority.

The comparison function consumes the explicit S3 model/current-actual rows and the explicit three-part baseline evidence record. It does not discover a different baseline through persistence lookup.

## 4. P50 and daily join contract

MODEL_QUANTILE=P50
BASELINE_QUANTILE=P50

Round C daily point comparison permits P50 on both sides only. Each baseline record matches a current model row only when every condition below is true:

```text
BaselineRequest.current_target_date
== S3BindingRow.forecast_target_date

BaselineRequest.current_forecast_cutoff_at
== S3BindingRow.forecast_cutoff_at

farm_business_key equal
subfarm_business_key equal
variety_business_key equal

metric_policy_version equal
baseline_policy_version equal

current_target_date inside declared current season
```

`breakdown_spec` is the sole source of the current model breakdown projection and must exactly constrain:

```text
season_business_key
farm_business_key
subfarm_business_key
variety_business_key
model_identity
forecast_horizon_days
```

The baseline may not invent model identity, forecast horizon, or season identity. Those projections come from the current model breakdown cell. A baseline record whose identity conflicts with the current model breakdown fails closed.

The same baseline semantic key appearing with more than one different evidence record is:

```text
STRUCTURAL_FAILURE
```

The implementation must not choose the first record, last record, or latest record.

## 5. Baseline member identity set

The comparison contract uses a baseline member set, not a single baseline
authority. `ComparisonResult` has these two fields instead:

```text
baseline_member_identity_set
baseline_member_set_hash
```

`baseline_member_identity_set` is a JSON array sorted by canonical daily key. Each member has exactly these fields:

```text
comparison_daily_key
baseline_request_hash
baseline_result_hash
baseline_source_snapshot_identity
baseline_source_snapshot_hash
baseline_source_row_set_hash
visibility_manifest_hash
baseline_policy_version
```

`comparison_daily_key` has exactly these fields:

```text
current_target_date
current_forecast_cutoff_at
farm_business_key
subfarm_business_key
variety_business_key
metric_policy_version
baseline_policy_version
```

The member set contains no database ID, timestamp outside the semantic cutoff, worker identity, row order, connection data, or raw baseline row. Missing, extra, duplicate, or incorrectly mapped members fail closed.

```text
BASELINE_MEMBER_SET_SCHEMA_VERSION=v0.2-s3-comparison-baseline-member-set-v1

baseline_member_set_payload = {
  "members": "member array ordered by comparison_daily_key canonical bytes",
  "schema_version": "v0.2-s3-comparison-baseline-member-set-v1"
}

baseline_member_set_hash =
  SHA256(canonical_json_bytes(baseline_member_set_payload))
```

The member array is canonicalized before hashing, so changing input order does not change the hash. Every baseline member must correspond to exactly one `naive_baseline_run` row under the owning `quality_evaluation_run`. The matching projections are:

```text
baseline_request_hash
baseline_result_hash
baseline_source_snapshot_identity
baseline_source_snapshot_hash
baseline_source_row_set_hash
visibility_manifest_hash
baseline_policy_version
```

The database must reject a member that is absent, belongs to another evaluation run, has a mismatched baseline projection, is duplicated, or produces a mismatched member-set hash. This enforcement is through a PostgreSQL trigger or equivalent database-level enforcement; application-only checks are insufficient.

## 6. Stable common-set classification

The implementation first constructs a stable candidate union, removes no evidence, deduplicates by canonical semantic key, and sorts by canonical key. A semantic daily key must enter exactly one of these classes:

```text
COMMON_COMPARABLE
MODEL_ONLY
BASELINE_ONLY
EXCLUDED
NOT_COMPUTABLE
```

Classification priority is frozen:

1. duplicate or contradictory identity -> `STRUCTURAL_FAILURE`;
2. model S2 `EXCLUDED` or `NOT_COMPARABLE` -> `EXCLUDED`;
3. model S2 `NOT_COMPUTABLE` -> `NOT_COMPUTABLE`;
4. matching baseline status `NOT_COMPUTABLE` -> `NOT_COMPUTABLE`;
5. model and baseline numeric evidence plus current actual -> `COMMON_COMPARABLE`;
6. valid model/current actual without matching baseline -> `MODEL_ONLY`;
7. valid baseline without matching model/current actual -> `BASELINE_ONLY`.

The closure invariant is:

```text
union_row_count =
    common_comparable_row_count
    + model_only_row_count
    + baseline_only_row_count
    + excluded_row_count
    + not_computable_row_count
```

The counter bounds are:

```text
common_comparable_row_count <= model_input_row_count
common_comparable_row_count <= baseline_input_row_count
```

`model_input_row_count` is the count of distinct model candidate keys. `baseline_input_row_count` is the count of distinct baseline candidate keys. All seven counters are included in the canonical payload.

### 6.1 Hand-computed classification example

The following six-key example has five model candidates, five baseline candidates, two common rows, one model-only row, one baseline-only row, one excluded row, and one not-computable row:

| Key | Model evidence | Baseline evidence | Model state | Frozen class |
| --- | --- | --- | --- | --- |
| `d01` | valid P50 and current actual | valid P50 | numeric | `COMMON_COMPARABLE` |
| `d02` | valid P50 and current actual | valid P50 | numeric | `COMMON_COMPARABLE` |
| `d03` | valid P50 and current actual | absent | numeric | `MODEL_ONLY` |
| `d04` | absent | valid P50 | n/a | `BASELINE_ONLY` |
| `d05` | present | valid P50 | S2 `EXCLUDED` | `EXCLUDED` |
| `d06` | present | valid P50 | S2 `NOT_COMPUTABLE` | `NOT_COMPUTABLE` |

```text
model candidates=5: d01,d02,d03,d05,d06
baseline candidates=5: d01,d02,d04,d05,d06
common=2: d01,d02
model_only=1: d03
baseline_only=1: d04
excluded=1: d05
not_computable=1: d06
union=6
2 + 1 + 1 + 1 + 1 = 6
```

The example proves that a key is counted once and that model-only, baseline-only, excluded, and not-computable evidence are not erased to manufacture a larger common set.

## 7. Recompute both metrics on the same common set

The comparison implementation must not directly compare persisted `DailyMetricResult` rows, because a model metric mask can contain rows unavailable to the baseline. Both sides must be recomputed on exactly the same `COMMON_COMPARABLE_SET`.

The implementation may create two temporary, non-persistent calculation inputs inside `comparison.py`:

```text
MODEL_COMMON_INPUT:
  forecast = model P50 forecast
  actual = current actual

BASELINE_COMMON_INPUT:
  forecast = baseline P50 point forecast
  actual = the same current actual
```

Both inputs must have:

- the same semantic daily keys;
- the same current actual values;
- row-order-independent identity;
- the same Decimal-only arithmetic policy.

The implementation reuses the existing Round A daily metric algorithms and Decimal rules. It must not maintain a second independent formula set. Baseline prior-season actual is never the current comparison actual.

## 7. S3R-24A record status rules

Every comparison cell always produces these six S3R-24A records:

```text
daily_mae_delta
daily_wape_delta
daily_smape_delta
daily_mape_delta
absolute_bias_magnitude_delta
signed_bias_delta
```

The delta semantics remain:

```text
loss_delta = model_loss - baseline_loss
positive = model worse
negative = model better
zero = tie

absolute_bias_magnitude_delta = abs(model_bias) - abs(baseline_bias)
positive = model worse
negative = model better
zero = tie

signed_bias_delta = model_signed_bias - baseline_signed_bias
direction only; not an improvement score
```

### 7.1 Zero common rows

When `common_comparable_row_count=0`, all six S3R-24A records are:

```text
metric_status=NOT_COMPUTABLE
reason_code=NO_S2_BINDING_ROWS
model_value=null
baseline_value=null
delta_value=null
comparison_availability=AVAILABLE
external_blocker=null
frozen_limitation=null
```

### 7.2 Metric-specific non-computability

```text
WAPE denominator zero:
  daily_wape_delta.metric_status=NOT_COMPUTABLE
  daily_wape_delta.reason_code=WAPE_DENOMINATOR_ZERO
  daily_wape_delta.comparison_availability=AVAILABLE
  daily_wape_delta.external_blocker=null
  daily_wape_delta.frozen_limitation=null
  all values=null

MAPE has no eligible row:
  daily_mape_delta.metric_status=NOT_COMPUTABLE
  daily_mape_delta.reason_code=NO_MAPE_ELIGIBLE_ROWS
  daily_mape_delta.comparison_availability=AVAILABLE
  daily_mape_delta.external_blocker=null
  daily_mape_delta.frozen_limitation=null
  all values=null
```

### 7.3 Insufficient sample

For one through nine common rows, when the particular metric is numerically computable, the result is:

```text
metric_status=INSUFFICIENT_SAMPLE
reason_code=BELOW_MINIMUM
comparison_availability=AVAILABLE
model_value non-null
baseline_value non-null
delta_value non-null
```

For at least ten common rows, when the metric is numerically computable:

```text
loss/magnitude:
  metric_status=COMPUTED
  reason_code=NONE
  comparison_availability=AVAILABLE

signed bias:
  metric_status=COMPARED
  reason_code=SIGNED_DIRECTION_ONLY
  comparison_availability=AVAILABLE
```

The state priority is:

```text
NOT_COMPUTABLE condition
>
INSUFFICIENT_SAMPLE
>
COMPUTED / COMPARED
```

The conditional-nullability matrix therefore includes `INSUFFICIENT_SAMPLE + BELOW_MINIMUM` with three non-null numeric values, in addition to the `COMPUTED`, `COMPARED`, and `NOT_COMPUTABLE` cases.

## 8. S3R-24C, S3R-24B, and child cardinality

S3R24A_RECORD_COUNT=6
S3R24C_RECORD_COUNT=4
S3R24B_RECORD_COUNT=0
TOTAL_RECORD_COUNT_PER_CELL=10

The four S3R-24C records are always:

| `comparison_name` | `comparison_availability` | `metric_status` | `reason_code` | `external_blocker` | `frozen_limitation` |
| --- | --- | --- | --- | --- | --- |
| `p80_coverage_delta` | `BLOCKED` | `NOT_COMPUTABLE` | `BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` | null | `BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` |
| `p90_coverage_delta` | `BLOCKED` | `NOT_COMPUTABLE` | `BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` | null | `BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` |
| `baseline_p80_p90_peak_comparison` | `BLOCKED` | `NOT_COMPUTABLE` | `BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` | null | `BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` |
| `interval_width_delta` | `BLOCKED` | `NOT_COMPUTABLE` | `PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE` | null | `PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE` |

For all four, `model_value`, `baseline_value`, and `delta_value` are null. `external_blocker` is null and `frozen_limitation == reason_code`. P50 may not substitute for P80 or P90, and zero may not represent missing interval evidence.

The Round C truth table is:

| Surface | `comparison_availability` | `external_blocker` | `frozen_limitation` |
| --- | --- | --- | --- |
| All S3R-24A records, including zero common rows and denominator failures | `AVAILABLE` | null | null |
| `p80_coverage_delta` | `BLOCKED` | null | `BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` |
| `p90_coverage_delta` | `BLOCKED` | null | `BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` |
| `baseline_p80_p90_peak_comparison` | `BLOCKED` | null | `BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` |
| `interval_width_delta` | `BLOCKED` | null | `PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE` |

`BLOCKED` is reserved for S3R-24C frozen limitations and a future external-authority-blocked surface. A frozen limitation is never written into `external_blocker`.

COMPLETE_WINDOW_COMPARISON_RECORD_WRITE=false
COMPLETE_WINDOW_COMPARISON_RECORD_COUNT=0

S3R-24B remains a contract assertion only. It contributes no comparison child to the persisted set.

```text
comparison_result_count = comparison_cell_count * 10
```

The manifest must contain all of these relational projections:

```text
comparison_policy_version
comparison_result_schema_version
comparison_cell_count
comparison_result_count
comparison_result_set_hash
```

## 9. Comparison result contract and Decimal rules

The Round C-only symbols and versions are owned by `comparison.py`:

```text
COMPARISON_POLICY_VERSION=v0.2-s3-comparison-policy-v1
COMPARISON_RESULT_SCHEMA_VERSION=v0.2-s3-comparison-result-v1
```

The internal `ComparisonResult` contains:

| Field | Contract |
| --- | --- |
| `schema_version` | `v0.2-s3-comparison-result-v1` for new comparison children |
| `comparison_policy_version` | `v0.2-s3-comparison-policy-v1` |
| `comparison_name` | one frozen S3R-24A or S3R-24C name |
| `comparison_availability` | `AVAILABLE` or `BLOCKED` |
| `metric_status` | existing `MetricStatus` value |
| `reason_code` | existing `ReasonCode` value |
| `model_identity` | normalized `BreakdownSpec.model_identity` text |
| `baseline_member_identity_set` | canonical JSON array of exact baseline member identities |
| `baseline_member_set_hash` | SHA-256 of the canonical baseline member-set payload |
| `normalized_breakdown_identity` | exact six-key identity object below |
| `forecast_horizon_days` | projection from `breakdown_spec`, positive integer |
| `model_value` | Decimal with six-place HALF_EVEN semantics or null |
| `baseline_value` | Decimal with six-place HALF_EVEN semantics or null |
| `delta_value` | Decimal with six-place HALF_EVEN semantics or null |
| `model_input_row_count` | nonnegative integer |
| `baseline_input_row_count` | nonnegative integer |
| `common_comparable_row_count` | nonnegative integer |
| `model_only_row_count` | nonnegative integer |
| `baseline_only_row_count` | nonnegative integer |
| `excluded_row_count` | nonnegative integer |
| `not_computable_row_count` | nonnegative integer |
| `external_blocker` | nullable string; null for all current Round C records |
| `frozen_limitation` | nullable string; null for S3R-24A and equal to `reason_code` for S3R-24C |
| `canonical_payload` | deterministic payload containing semantic identity, status/reason, values, and counters |
| `canonical_hash` | SHA-256 of the canonical payload |

All Decimal arithmetic is frozen:

```text
DECIMAL_SCALE=6
ROUNDING=ROUND_HALF_EVEN
NATIVE_FLOAT_ALLOWED=false
```

Conditional nullability is frozen:

```text
COMPUTED or COMPARED or INSUFFICIENT_SAMPLE:
  model_value non-null
  baseline_value non-null
  delta_value non-null

COMPUTED:
  reason_code=NONE

COMPARED:
  reason_code=SIGNED_DIRECTION_ONLY

INSUFFICIENT_SAMPLE:
  reason_code=BELOW_MINIMUM

NOT_COMPUTABLE:
  reason_code non-NONE
  model_value=null
  baseline_value=null
  delta_value=null

S3R-24A NOT_COMPUTABLE:
  comparison_availability=AVAILABLE
  external_blocker=null
  frozen_limitation=null

S3R-24C NOT_COMPUTABLE:
  comparison_availability=BLOCKED
  external_blocker=null
  frozen_limitation=reason_code
```

## 10. Identity JSON shapes and projection equality

`model_identity` is not an arbitrary JSON object. It is the exact `BreakdownSpec.model_identity` text and the relational column is:

```text
model_identity TEXT NOT NULL
```

`normalized_breakdown_identity` is a JSON object with exactly these six keys and no additional key:

```text
forecast_horizon_days
farm_business_key
subfarm_business_key
variety_business_key
season_business_key
model_identity
```

The database and replay checks must enforce:

```text
model_identity column
== normalized_breakdown_identity.model_identity

forecast_horizon_days column
== normalized_breakdown_identity.forecast_horizon_days
```

`baseline_member_identity_set` is the exact JSON array defined in Section 5.
Each member has exactly these seven projection fields and no additional field:

```text
comparison_daily_key
baseline_request_hash
baseline_result_hash
baseline_source_snapshot_identity
baseline_source_snapshot_hash
baseline_source_row_set_hash
visibility_manifest_hash
baseline_policy_version
```

`baseline_member_set_hash` is the SHA-256 of the canonical member-set
payload, not the hash of a single baseline row. Neither the member set nor its
daily key contains database IDs, timestamps outside the semantic cutoff,
worker identity, row order, connection data, or raw baseline rows. There is no
legacy single-row lookup authority in the Round C contract.

## 11. Database schema decision and 0025 contract

ROUND_C_SCHEMA_DECISION=OPTION_A
PREFERRED_SCHEMA_DECISION=OPTION_A
ALEMBIC_0025_REQUIRED=true
ALEMBIC_REVISION=0025_s3_model_baseline_comparison
ALEMBIC_DOWN_REVISION=0024_s3_forecast_quality_persistence
ALEMBIC_HEAD_COUNT=1
NEW_TABLE_COUNT=0

OPTION_A alters the existing `model_baseline_comparison` table through migration 0025 and adds deterministic relational projections. OPTION_B, in which `canonical_payload` is the sole arithmetic authority while existing columns remain ambiguous, is rejected because it cannot provide the required queryability, conditional-nullability enforcement, corruption detection, idempotent projections, or future S4 read contract.

### 11.1 0025 relational columns

Migration 0025 must first verify that the pre-0025
`model_baseline_comparison` row count is zero. It must then drop the legacy
single-baseline relationship:

```text
DROP CONSTRAINT fk_model_baseline_comparison_baseline
DROP COLUMN naive_baseline_run_id
```

It must rename existing `comparison_status` to `metric_status`, add the
baseline member set and v2 projections, add nullable
`comparison_policy_version` to `quality_evaluation_run`, and preserve the
six-table Round B schema while making v1/v2 checks explicit. It creates no
seventh table. A baseline membership trigger (or equivalent database
enforcement) locks the owning run and rejects a missing member, a member from
a foreign run, a mismatched projection, a duplicate member, or a member-set
hash that does not match the canonical array.

| Column | PostgreSQL type | Nullability/default | Frozen rule |
| --- | --- | --- | --- |
| `id` | `BIGINT` | NOT NULL generated primary key | internal only |
| `quality_evaluation_run_id` | `BIGINT` | NOT NULL | FK `fk_model_baseline_comparison_run` |
| `schema_version` | `TEXT` | NOT NULL | `v0.2-s3-quality-persistence-v2` only |
| `comparison_key_hash` | `TEXT` | NOT NULL | SHA-256; unique with owning run |
| `comparison_policy_version` | `TEXT` | NOT NULL | `v0.2-s3-comparison-policy-v1` |
| `comparison_name` | `TEXT` | NOT NULL | exact S3R-24A/S3R-24C vocabulary |
| `comparison_availability` | `TEXT` | NOT NULL | `AVAILABLE` or `BLOCKED` |
| `metric_status` | `TEXT` | NOT NULL | existing `MetricStatus` vocabulary |
| `reason_code` | `TEXT` | NOT NULL | existing `ReasonCode` vocabulary |
| `external_blocker` | `TEXT` | NULL | null for current Round C; never a frozen limitation |
| `frozen_limitation` | `TEXT` | NULL | null for S3R-24A; equals `reason_code` for S3R-24C |
| `model_identity` | `TEXT` | NOT NULL | exact `BreakdownSpec.model_identity` |
| `baseline_member_identity_set` | `JSONB` | NOT NULL | exact non-empty member array and exact member shape |
| `baseline_member_set_hash` | `TEXT` | NOT NULL | lowercase SHA-256 of canonical member-set payload |
| `normalized_breakdown_identity` | `JSONB` | NOT NULL | exact six keys, no extra key |
| `forecast_horizon_days` | `INTEGER` | NOT NULL | equals six-axis projection and greater than zero |
| `model_value` | `NUMERIC(20,6)` | NULL | conditional-nullability check |
| `baseline_value` | `NUMERIC(20,6)` | NULL | conditional-nullability check |
| `delta_value` | `NUMERIC(20,6)` | NULL | conditional-nullability check |
| `model_input_row_count` | `BIGINT` | NOT NULL | nonnegative |
| `baseline_input_row_count` | `BIGINT` | NOT NULL | nonnegative |
| `common_comparable_row_count` | `BIGINT` | NOT NULL | nonnegative and bounded by both inputs |
| `model_only_row_count` | `BIGINT` | NOT NULL | nonnegative |
| `baseline_only_row_count` | `BIGINT` | NOT NULL | nonnegative |
| `excluded_row_count` | `BIGINT` | NOT NULL | nonnegative |
| `not_computable_row_count` | `BIGINT` | NOT NULL | nonnegative |
| `canonical_payload` | `JSONB` | NOT NULL | v2 payload and projection equality |
| `canonical_hash` | `TEXT` | NOT NULL | SHA-256; unique with owning run |
| `created_at` | `TIMESTAMPTZ` | NOT NULL default `now()` | immutable |
| `completed_at` | `TIMESTAMPTZ` | NOT NULL | immutable |

The exact named constraints are:

- `uq_model_baseline_comparison_run_key` on `(quality_evaluation_run_id, comparison_key_hash)`;
- `uq_model_baseline_comparison_run_canonical_hash` on `(quality_evaluation_run_id, canonical_hash)`;
- `ck_model_baseline_comparison_key_sha256`;
- `ck_model_baseline_comparison_canonical_sha256`;
- `ck_model_baseline_comparison_schema_version_v2`;
- `ck_model_baseline_comparison_policy_version_v2`;
- `ck_model_baseline_comparison_name_vocabulary`;
- `ck_model_baseline_comparison_availability_vocabulary`;
- `ck_model_baseline_comparison_metric_status_vocabulary`;
- `ck_model_baseline_comparison_reason_code_vocabulary`;
- `ck_model_baseline_comparison_forecast_horizon_positive`;
- `ck_model_baseline_comparison_counters_nonnegative`;
- `ck_model_baseline_comparison_counter_bounds`;
- `ck_model_baseline_comparison_identity_projection`;
- `ck_model_baseline_comparison_six_axis_identity`;
- `ck_model_baseline_comparison_baseline_member_set_array`;
- `ck_model_baseline_comparison_baseline_member_set_nonempty`;
- `ck_model_baseline_comparison_baseline_member_set_hash_sha256`;
- `ck_model_baseline_comparison_baseline_member_shape`;
- `ck_model_baseline_comparison_external_blocker_vocabulary`;
- `ck_model_baseline_comparison_frozen_limitation_vocabulary`;
- `ck_model_baseline_comparison_blocker_limitation_consistency`;
- `ck_model_baseline_comparison_conditional_values`.

### 11.2 0025 manifest columns and projections

Migration 0025 adds these columns to the existing
`quality_evaluation_manifest`; it does not add a table:

| Column | PostgreSQL type | Nullability/default | Frozen rule |
| --- | --- | --- | --- |
| `comparison_policy_version` | `TEXT` | NULL | null for v1; `v0.2-s3-comparison-policy-v1` for v2 |
| `comparison_result_schema_version` | `TEXT` | NULL | null for v1; `v0.2-s3-comparison-result-v1` for v2 |
| `comparison_result_set_schema_version` | `TEXT` | NOT NULL | v1 or `v0.2-s3-comparison-result-set-v2` according to run version |
| `comparison_cell_count` | `BIGINT` | NOT NULL | nonnegative; v2 is the distinct normalized identity count |
| `comparison_result_count` | `BIGINT` | NOT NULL | nonnegative; v2 equals `comparison_cell_count * 10` |
| `comparison_result_set_hash` | `TEXT` | NOT NULL, retained | exact versioned result-set payload hash |

The v1 manifest projection is frozen as:

```text
schema_version=v0.2-s3-quality-persistence-v1
comparison_policy_version=null
comparison_result_schema_version=null
comparison_result_set_schema_version=v0.2-s3-comparison-result-set-v1
comparison_cell_count=0
comparison_result_count=0
comparison_result_set_hash=Round B explicit-empty comparison set hash
```

The v2 manifest projection is frozen as:

```text
schema_version=v0.2-s3-quality-persistence-v2
comparison_policy_version=v0.2-s3-comparison-policy-v1
comparison_result_schema_version=v0.2-s3-comparison-result-v1
comparison_result_set_schema_version=v0.2-s3-comparison-result-set-v2
comparison_cell_count=count(distinct normalized_breakdown_identity in owning run)
comparison_result_count=comparison_cell_count * 10
comparison_result_set_hash=exact v2 hash rebuilt from database child canonical hashes
```

For v2, `comparison_result_count` must equal the owning run's database child
row count, and the rebuilt child-hash payload must equal the stored manifest
hash. The named constraints are:

```text
ck_quality_manifest_comparison_versions
ck_quality_manifest_comparison_counts_nonnegative
ck_quality_manifest_comparison_count_closure
ck_quality_manifest_v1_comparison_projection
ck_quality_manifest_v2_comparison_projection
```

The ORM, persistence replay path, and isolated direct PostgreSQL probes must
all verify these projections and reject version, count, child-set, or hash
mismatches. The manifest remains the last insert and seals the owning run.

### 11.3 Six-table v1/v2 schema-version checks

The six Round B persistence tables (`quality_evaluation_run`, `quality_metric_result`, `quality_breakdown_result`, `naive_baseline_run`, `model_baseline_comparison`, and `quality_evaluation_manifest`) must accept the historical v1 schema version and the new v2 schema version where a schema-version projection exists:

```text
LEGACY_PERSISTENCE_SCHEMA_VERSION=v0.2-s3-quality-persistence-v1
ROUND_C_PERSISTENCE_SCHEMA_VERSION=v0.2-s3-quality-persistence-v2
```

`model_baseline_comparison` rows are v2-only. Existing v1 rows in the other five tables remain valid and immutable. Every v2 child canonical payload contains the v2 schema version, separating v2 canonical hashes from historical v1 hashes.

## 12. Round B v1 and Round C v2 lifecycle

### 12.1 Historical Round B v1

```text
LEGACY_PERSISTENCE_SCHEMA_VERSION=v0.2-s3-quality-persistence-v1
comparison_policy_version=null
comparison record count=0
comparison_result_set_hash=Round B explicit-empty hash
```

Historical v1 runs remain valid, immutable, and non-partial. Their explicit-empty comparison set hash is not reinterpreted as corruption. Comparison rows may not be appended to a sealed v1 run. A sealed v1 run may not be backfilled in place, and its manifest may not be rewritten.

### 12.2 New Round C v2

```text
ROUND_C_PERSISTENCE_SCHEMA_VERSION=v0.2-s3-quality-persistence-v2
comparison_policy_version=v0.2-s3-comparison-policy-v1
comparison records are part of the initial complete write
manifest inserted after comparison rows
```

The Round C evaluation request payload must add exactly these fields:

```text
persistence_schema_version
comparison_policy_version
comparison_result_schema_version
comparison_contract_enabled=true
```

The v2 request identity therefore differs from v1:

```text
v1 evaluation_request_hash != v2 evaluation_request_hash
```

The same S3 source inputs under Round C create an independent v2 evaluation because the request identity is different. V1 data is not rewritten as v2 data.

## 13. 0025 upgrade and downgrade policy

Migration 0025 must fail closed before changing schema when either precondition below is false:

```text
pre-0025 model_baseline_comparison row count == 0
all discovered comparison rows are absent
```

If any pre-0025 comparison row exists, upgrade is rejected. No row is silently transformed, deleted, or projected into the v2 shape.

0025 downgrade is allowed only when both conditions hold:

```text
no v2 quality_evaluation_run rows exist
model_baseline_comparison row count == 0
```

If any v2 evaluation or comparison row exists, downgrade is rejected fail closed. Data is not deleted, truncated, or projected back into 0024. The clean database path must pass:

```text
0024 -> 0025 -> 0024 -> 0025
```

The future implementation must not claim that existing Round C rows are preserved through downgrade; v2 data explicitly blocks downgrade.

## 14. Comparison unique transition

Migration 0025 must perform this exact transition:

```text
DROP uq_model_baseline_comparison_canonical_hash

CREATE uq_model_baseline_comparison_run_canonical_hash
ON (quality_evaluation_run_id, canonical_hash)
```

`uq_model_baseline_comparison_run_key` remains unchanged. The database must allow identical valid canonical comparison evidence in two different v2 evaluation runs, while rejecting identical canonical comparison evidence twice in one run.

## 15. Simplified comparison key identity

`comparison_key_hash` has exactly these canonical inputs:

```text
comparison_result_schema_version
comparison_policy_version
comparison_name
baseline_member_set_hash
normalized_breakdown_identity
```

The complete `baseline_member_identity_set` is included in the comparison
canonical payload, but the key uses only its deterministic
`baseline_member_set_hash`. No single-row baseline identity or lookup foreign
key is a comparison-contract field. `model_identity` and
`forecast_horizon_days` are not repeated as independent comparison-key inputs
because they are already contained in `normalized_breakdown_identity`. The
independent relational columns remain and must equal the corresponding
canonical identity projections exactly.

The comparison canonical payload contains the key identity, status/reason, values where computable, all seven counters, and the v2 schema/policy versions. It excludes database numeric IDs, timestamps, worker or host identity, database row order, connection information, and unbounded raw rows.

```text
canonical_hash = SHA256(canonical_json(canonical_payload))
comparison_result_set_hash = hash(sorted explicit comparison canonical hashes)
```

The manifest comparison set hash is inserted only after all comparison rows have been written. Exact replay requires equality of key projections, baseline projections, six-axis projections, canonical payload/hash, counters, child set, and manifest projections. Conflicting valid evidence is rejected. Partial, orphaned, extra, missing, or self-contradictory evidence fails closed.

## 16. Exact comparison result-set payload

COMPARISON_RESULT_SET_SCHEMA_VERSION=v0.2-s3-comparison-result-set-v2

The v2 comparison result-set payload is exactly:

```json
{
  "record_count": "comparison canonical hash count",
  "records": "lowercase SHA-256 strings sorted in ascending text order",
  "schema_version": "v0.2-s3-comparison-result-set-v2"
}
```

The hash is:

```text
comparison_result_set_hash =
  SHA256(canonical_json_bytes(comparison_result_set_payload))
```

The payload must satisfy:

```text
record_count == len(records)
records contains no duplicate
every records element is lowercase SHA-256 text
records exactly equals the owning run comparison child canonical-hash set
```

Hashing a Python set, bare list, database row order, concatenated strings, or Round B's explicit-empty set is forbidden. Reordering database rows cannot change the v2 result-set hash.

## 18. Exact future implementation path union

The following remains the complete and only authorized future Round C implementation union. This document fixup does not expand it.

FUTURE_IMPLEMENTATION_PATH_COUNT=14
FUTURE_CREATE_PATH_COUNT=5
FUTURE_MODIFY_PATH_COUNT=9
FUTURE_DELETE_PATH_COUNT=0
FUTURE_UNAUTHORIZED_PATH_COUNT=0

| Path | Operation | Fixed owner or responsibility |
| --- | --- | --- |
| `backend/app/forecast_quality/comparison.py` | CREATE | Sole owner of Round C-only symbols, input join, common-set classification, recalculation, Decimal rules, and result construction |
| `backend/app/forecast_quality/persistence.py` | MODIFY | Caller-owned v2 persistence, replay, projection validation, result-set hash, and manifest-last seal |
| `backend/app/models/forecast_quality.py` | MODIFY | ORM owner for v2 comparison and run projections |
| `backend/alembic/versions/0025_s3_model_baseline_comparison.py` | CREATE | 0025 upgrade, preconditions, downgrade guards, constraints, and v1/v2 checks |
| `backend/tests/forecast_quality/test_comparison_point.py` | CREATE | Point join, common-set, daily metric, and sign contract tests; owner `postgres-domain-1` |
| `backend/tests/forecast_quality/test_comparison_quantile.py` | CREATE | P50-only and S3R-24C blocked output tests; owner `postgres-domain-1` |
| `backend/tests/forecast_quality/test_comparison_delta.py` | CREATE | Delta, cardinality, identity projection, and canonical tests; owner `postgres-domain-1` |
| `backend/tests/forecast_quality/test_persistence.py` | MODIFY | 0025 migration, schema, database constraint, ordering, and v1/v2 persistence tests; owner `postgres-migration` |
| `backend/tests/forecast_quality/test_idempotency.py` | MODIFY | Non-concurrency v2 replay tests owned by `postgres-domain-1`; marked concurrency nodes owned by `postgres-concurrency` |
| `backend/tests/forecast_quality/test_blocked_surfaces.py` | MODIFY | Non-implementation boundary tests; owner `unit-contract-golden` |
| `backend/tests/actual_harvest_import/alembic_cases.py` | MODIFY | 0025 lineage and single-head helper assertions; exercised by `postgres-migration` |
| `backend/tests/test_historical_backtest_alembic.py` | MODIFY | 0024/0025 clean round-trip and fail-closed transition tests; owner `postgres-migration` |
| `ci-shard-manifest.yml` | MODIFY | Existing shard ownership entries for the three comparison test files; no new job |
| `.github/workflows/ci.yml` | MODIFY | Existing shard pytest argument entries for the three comparison test files; no job/event/service change |

`schemas.py` modification is not required. `enums.py` modification is not required. `calculator_daily.py` modification is not required. Round C-only dataclasses and constants are owned by `comparison.py`, existing enums are reused, and the existing daily calculator is reused without numerical modification. If an implementation audit proves one of those three paths is required for compilation, document authoring must stop; it may not be added to this union by inference.

## 19. CI ownership freeze

CI_OWNERSHIP_FROZEN=true
CI_JOB_COUNT_CHANGE=0
CI_EVENT_CHANGE=0
CI_POSTGRES_SERVICE_CHANGE=0
CI_FULL_SUITE_CANARY_ON_PULL_REQUEST=false
DUPLICATE_EXECUTION_NODE_COUNT=0
UNOWNED_TEST_NODE_COUNT=0

| Test node class | Unique owner | Rule |
| --- | --- | --- |
| `test_comparison_point.py` | `postgres-domain-1` | Explicit domain-1 file argument only |
| `test_comparison_quantile.py` | `postgres-domain-1` | Explicit domain-1 file argument only |
| `test_comparison_delta.py` | `postgres-domain-1` | Explicit domain-1 file argument only |
| `test_persistence.py` | `postgres-migration` | Explicit migration file argument only |
| `test_historical_backtest_alembic.py` | `postgres-migration` | Explicit migration file argument only |
| Non-concurrency `test_idempotency.py` nodes | `postgres-domain-1` | Domain-1 argument with `not postgres_concurrency` |
| `postgres_concurrency` `test_idempotency.py` nodes | `postgres-concurrency` | Concurrency argument with `postgres_concurrency` |
| `test_blocked_surfaces.py` nodes | `unit-contract-golden` | Marker-residual unit selector |

Each test node has one owner. No new job, required job name, event trigger, PostgreSQL service version, port, credential, or PR canary behavior is authorized.

## 20. Acceptance matrix

The future implementation is incomplete until every item below has a passing test in its unique owner:

| # | Frozen acceptance |
| ---: | --- |
| 1 | Hand-computed daily point comparison oracle |
| 2 | Positive delta means model worse for loss and magnitude |
| 3 | Negative delta means model better for loss and magnitude |
| 4 | Zero delta is a tie |
| 5 | Signed bias is direction only with `COMPARED` and `SIGNED_DIRECTION_ONLY` |
| 6 | Common-set exact join positive matrix |
| 7 | Cutoff mismatch rejection |
| 8 | P50/P80 mismatch rejection |
| 9 | Duplicate baseline semantic key rejection |
| 10 | The same current actual is used by both sides |
| 11 | Baseline prior-season actual is not used as current actual |
| 12 | Model-only and baseline-only audit counts are preserved |
| 13 | Common-set closure and counter bounds are enforced |
| 14 | Zero common rows produce six `AVAILABLE` S3R-24A records with null blocker and limitation |
| 15 | WAPE denominator zero produces `WAPE_DENOMINATOR_ZERO` |
| 16 | MAPE without an eligible row produces `NO_MAPE_ELIGIBLE_ROWS` |
| 17 | One through nine common rows produce `INSUFFICIENT_SAMPLE + BELOW_MINIMUM` when numerically computable |
| 18 | At least ten common rows produce `COMPUTED` or `COMPARED` when numerically computable |
| 19 | Exactly ten comparison records are produced per cell |
| 20 | Four S3R-24C records remain blocked and S3R-24B produces zero comparison rows |
| 21 | Exact replay performs zero writes |
| 22 | Conflicting replay is rejected |
| 23 | Partial comparison persistence is rejected |
| 24 | Manifest comparison result-set hash equals the explicit sorted child set |
| 25 | V2 comparison rows are inserted before the manifest |
| 26 | Comparison rows are immutable |
| 27 | Child insert after manifest seal is rejected |
| 28 | PostgreSQL concurrent identical comparison persistence converges to one result |
| 29 | PostgreSQL concurrent conflicting comparison persistence has one conflict and no partial result |
| 30 | Historical v1 manifest remains valid and immutable |
| 31 | A v1 run cannot receive a comparison child |
| 32 | The same source inputs create a separate v2 request identity |
| 33 | Identical valid comparison evidence is allowed across two v2 runs |
| 34 | Identical comparison evidence twice in one run is rejected |
| 35 | Any pre-0025 comparison row blocks upgrade without transformation |
| 36 | Any v2 evaluation or comparison row blocks downgrade without deletion |
| 37 | Clean `0024 -> 0025 -> 0024 -> 0025` round trip succeeds |
| 38 | Model and six-axis identity projection equality is enforced |
| 39 | Baseline member identity exact-key and relational projection equality is enforced |
| 40 | Malformed SHA-256, FK, unique, vocabulary, nullability, counter, horizon, and identity probes are real isolated PostgreSQL rejection probes |
| 41 | Multi-day baseline member set success |
| 42 | Baseline member order independence preserves the member-set hash |
| 43 | Duplicate baseline member is rejected |
| 44 | Missing baseline member is rejected |
| 45 | Foreign-run baseline member is rejected |
| 46 | Baseline member-set hash mismatch is rejected |
| 47 | Daily zero-common availability remains `AVAILABLE` |
| 48 | Daily WAPE-zero availability remains `AVAILABLE` |
| 49 | Daily MAPE-no-eligible availability remains `AVAILABLE` |
| 50 | Every S3R-24A record has null `external_blocker` and null `frozen_limitation` |
| 51 | Every S3R-24C limitation has exact `frozen_limitation == reason_code` and null `external_blocker` |
| 52 | Writing a frozen limitation as an external blocker is rejected |
| 53 | Exact v2 comparison result-set payload oracle passes |
| 54 | Bare-list result-set hash is rejected |
| 55 | Database-row-order result-set hash is rejected |
| 56 | Duplicate result hash in the result-set payload is rejected |
| 57 | Historical v1 manifest projection remains compatible and immutable |
| 58 | V2 manifest version projection is enforced |
| 59 | V2 result count equals `comparison_cell_count * 10` |
| 60 | V2 result count equals the database comparison-child count |
| 61 | Manifest result-set hash is rebuilt exactly from database child hashes |

The negative probes must leave no committed test pollution. Metadata-only constraint-name checks are insufficient; illegal writes must be attempted and rejected by PostgreSQL.

## 21. Explicit non-scope

```text
REAL_DATA=false
REAL_DATA_BACKTEST=false
DATA_IMPORT=false
BUSINESS_ATTESTATION_COLLECTION=false

S3R-24B=false
S3R-22_QUANTILE_PUBLICATION=false
S3R-23_PINBALL_PUBLICATION=false

HTTP_API=false
PUBLIC_APPLICATION_API=false
FRONTEND=false
S4=false
S5=false

MODEL_RETRAINING=false
MODEL_PARAMETER_CHANGE=false
TASK8_NUMERICAL_CHANGE=false
TASK9_NUMERICAL_CHANGE=false
TASK10_NUMERICAL_CHANGE=false

ISSUE102_CLOSE=false
```

## 22. Review and handoff gates

Independent review must verify:

1. Only `docs/forecast-quality/s3-round-c-comparison-authorization.md` changed in this fixup.
2. The path union remains exactly 14 future paths with 5 creates, 9 modifies, and 0 deletes.
3. `comparison.py` is the sole owner of Round C-only symbols and versions.
4. The exact function signature, three-part baseline record, P50 join, stable classification, closure, and common-set recalculation contracts are present.
5. S3R-24A, S3R-24C, and the continued S3R-24B block are preserved.
6. V1 historical validity and V2 request identity are separated.
7. 0025 upgrade and downgrade guards fail closed as specified.
8. The global comparison canonical unique is replaced by the owning-run unique.
9. CI ownership has zero duplicate and zero unowned nodes.
10. The Draft PR head equals the new fast-forward commit head.

ROUND_C_AUTHORIZATION_DOCUMENT_ACCEPTED=false
ROUND_C_IMPLEMENTATION_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
REAL_DATA_OPENED=false
ISSUE102_CLOSED=false
STOPPED_AWAITING_EXACT_HEAD_REREVIEW=true
NO_STEP_IMPLIES_THE_NEXT=true
