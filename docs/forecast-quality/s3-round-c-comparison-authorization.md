# V0.2-S3 Round C comparison authorization freeze

DOCUMENT_STATUS=PROPOSED_AWAITING_INDEPENDENT_REVIEW
BASE_SHA=36e196d3742e8efaaa449230d86777335a337b8e

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

This document is the sole Round C authorization artifact. It freezes the comparison contract and the exact future implementation path union. It authorizes no implementation, schema, migration, CI, production, test, data, API, or frontend change.

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

Round C compares the persisted S3 model evidence with the persisted baseline evidence. The comparison domain is restricted to S3R-24A, S3R-24C, and S3R-25 below. No unrelated metric, model, task, or public API is authorized by this document.

## 2. S3R-24A daily point head-to-head

POINT_HEAD_TO_HEAD_OVER=COMMON_COMPARABLE_SET

The comparison input is the intersection of model and baseline comparable semantic rows. A model-only row and a baseline-only row remain in audit counters; neither is silently deleted, imputed, or treated as a common row. The comparison implementation must construct the common set explicitly and preserve all seven audit counts:

| Audit counter | Frozen meaning | Type |
| --- | --- | --- |
| `model_input_row_count` | Model rows entering the comparison after the declared input filters | nonnegative integer |
| `baseline_input_row_count` | Baseline rows entering the comparison after the declared input filters | nonnegative integer |
| `common_comparable_row_count` | Semantic intersection used for numeric head-to-head values | nonnegative integer |
| `model_only_row_count` | Model rows without a baseline counterpart | nonnegative integer |
| `baseline_only_row_count` | Baseline rows without a model counterpart | nonnegative integer |
| `excluded_row_count` | Rows excluded by the frozen comparability rules | nonnegative integer |
| `not_computable_row_count` | Rows with insufficient evidence for a numeric result | nonnegative integer |

The six authorized daily point outputs are:

| `comparison_name` | `model_value` | `baseline_value` | `delta_value` | Status | Reason |
| --- | --- | --- | --- | --- | --- |
| `daily_mae_delta` | model daily MAE | baseline daily MAE | model minus baseline | `COMPUTED` | `NONE` |
| `daily_wape_delta` | model daily WAPE | baseline daily WAPE | model minus baseline | `COMPUTED` | `NONE` |
| `daily_smape_delta` | model daily sMAPE | baseline daily sMAPE | model minus baseline | `COMPUTED` | `NONE` |
| `daily_mape_delta` | model daily MAPE | baseline daily MAPE | model minus baseline | `COMPUTED` | `NONE` |
| `absolute_bias_magnitude_delta` | absolute model bias | absolute baseline bias | `abs(model_bias) - abs(baseline_bias)` | `COMPUTED` | `NONE` |
| `signed_bias_delta` | model signed bias | baseline signed bias | `model_signed_bias - baseline_signed_bias` | `COMPARED` | `SIGNED_DIRECTION_ONLY` |

For every loss or magnitude delta:

```text
loss_delta = model_loss - baseline_loss
positive = model worse
negative = model better
zero = tie
```

For the absolute bias magnitude delta:

```text
absolute_bias_magnitude_delta = abs(model_bias) - abs(baseline_bias)
positive = model worse
negative = model better
zero = tie
```

`signed_bias_delta` is directional information only. It is not an improvement score and must not be assigned the positive-is-worse or negative-is-better loss interpretation.

The model-only and baseline-only rows must remain represented in the audit counters. Removing either side to force an apparent common set is forbidden.

## 3. S3R-24C non-computable outputs

No baseline P80 or P90 distribution may be invented. P50 may not replace P80 or P90, and zero may not replace an unavailable value. The following outputs are persisted only as blocked comparison records with null numeric values:

| `comparison_name` | `comparison_availability` | `metric_status` | `reason_code` | `external_blocker` |
| --- | --- | --- | --- | --- |
| `p80_coverage_delta` | `BLOCKED` | `NOT_COMPUTABLE` | `BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` | `none` |
| `p90_coverage_delta` | `BLOCKED` | `NOT_COMPUTABLE` | `BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` | `none` |
| `baseline_p80_p90_peak_comparison` | `BLOCKED` | `NOT_COMPUTABLE` | `BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` | `none` |
| `interval_width_delta` | `BLOCKED` | `NOT_COMPUTABLE` | `PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE` | `none` |

For all four records, `model_value`, `baseline_value`, and `delta_value` are null. The record remains auditable through its semantic identity, status, reason, and counters.

## 4. S3R-24B remains blocked

COMPLETE_WINDOW_HEAD_TO_HEAD_AUTHORIZED=false
COMPLETE_WINDOW_COMPARISON_VALUE_WRITE=false
BLOCKER=S2_COMPLETE_DAILY_ROW_SET_AUTHORITY
STATUS=NOT_COMPUTABLE
REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING

The following outputs remain blocked and may not receive comparison values:

- `absolute_cumulative_bias_magnitude_delta`
- `signed_cumulative_error_delta`
- `single_day_peak_date_absolute_error_delta_q`
- `single_day_peak_quantity_absolute_error_delta_q`
- `sustained_7day_start_date_absolute_error_delta_q`
- `sustained_7day_quantity_absolute_error_delta_q`

## 5. Comparison result internal contract

The future implementation must produce one internal Python comparison record with exactly this contract. Database identifiers, timestamps, worker identity, and connection identity are persistence metadata and are not part of the semantic record.

| Field | Contract |
| --- | --- |
| `schema_version` | non-null version string |
| `comparison_policy_version` | non-null frozen policy string |
| `comparison_name` | non-null value from the frozen comparison-name vocabulary in this document |
| `comparison_availability` | `AVAILABLE` for computable outputs or `BLOCKED` for frozen non-computable outputs |
| `metric_status` | existing `MetricStatus` vocabulary only |
| `reason_code` | existing `ReasonCode` vocabulary only |
| `model_identity` | normalized model identity object |
| `baseline_identity` | normalized baseline canonical identity object; includes the baseline canonical evidence identity and no database ID |
| `normalized_breakdown_identity` | normalized six-axis identity object |
| `forecast_horizon_days` | positive integer |
| `model_value` | Decimal with six-place HALF_EVEN semantics when computable; null otherwise |
| `baseline_value` | Decimal with six-place HALF_EVEN semantics when computable; null otherwise |
| `delta_value` | Decimal with six-place HALF_EVEN semantics when computable; null otherwise |
| `model_input_row_count` | nonnegative integer |
| `baseline_input_row_count` | nonnegative integer |
| `common_comparable_row_count` | nonnegative integer |
| `model_only_row_count` | nonnegative integer |
| `baseline_only_row_count` | nonnegative integer |
| `excluded_row_count` | nonnegative integer |
| `not_computable_row_count` | nonnegative integer |
| `canonical_payload` | deterministic JSON object containing the semantic identity, status/reason, computable values, and all seven audit counters |
| `canonical_hash` | SHA-256 of the canonical JSON payload |

Conditional nullability is frozen as follows:

```text
COMPUTED:
  model_value is non-null
  baseline_value is non-null
  delta_value is non-null
  reason_code = NONE

COMPARED + SIGNED_DIRECTION_ONLY:
  model_value is non-null
  baseline_value is non-null
  delta_value is non-null
  reason_code = SIGNED_DIRECTION_ONLY

NOT_COMPUTABLE:
  model_value is null
  baseline_value is null
  delta_value is null
  reason_code is non-NONE
  comparison_availability = BLOCKED
```

All Decimal arithmetic is frozen:

```text
DECIMAL_SCALE=6
ROUNDING=ROUND_HALF_EVEN
NATIVE_FLOAT_ALLOWED=false
```

The implementation must quantize model values, baseline values, and delta values to six places before canonical serialization. Native binary floats, NaN, and infinity are not valid comparison values.

## 6. Database schema decision

ROUND_C_SCHEMA_DECISION=OPTION_A
PREFERRED_SCHEMA_DECISION=OPTION_A
ALEMBIC_0025_REQUIRED=true
ALEMBIC_REVISION=0025_s3_model_baseline_comparison
ALEMBIC_DOWN_REVISION=0024_s3_forecast_quality_persistence
ALEMBIC_HEAD_COUNT=1
NEW_TABLE_COUNT=0

### 6.1 Decision comparison

| Decision criterion | OPTION_A: alter `model_baseline_comparison` with migration 0025 | OPTION_B: retain existing columns and make `canonical_payload` the sole arithmetic authority |
| --- | --- | --- |
| Queryability | Relational projections are directly queryable by comparison name, status, horizon, identity, values, and counters | Every consumer must parse JSON for ordinary filters and numeric reads |
| Canonical authority | `canonical_payload` remains the hash authority while projections are checked against it | JSON is the only authority and relational corruption is harder to detect |
| Constraint enforcement | PostgreSQL can enforce vocabulary, conditional nullability, counter ranges, horizon, six-axis shape, and Decimal scale | Conditional and numeric rules cannot be enforced completely through existing columns |
| Conditional nullability | `CHECK` constraints directly reject invalid computable and blocked rows | Application checks can be bypassed by direct SQL |
| Idempotent replay | Semantic key and canonical hash projections support exact replay and conflict classification | Replay requires JSON extraction and cannot enforce the full identity contract relationally |
| Corruption detection | Stored projections can be rebuilt from canonical payload and compared during replay | A payload-only read cannot detect missing relational projections because none are present |
| Migration compatibility | One forward-only 0025 migration can rename `comparison_status` to `metric_status`, add projections, and reverse them on downgrade | Existing schema ambiguity remains and future S4 reads inherit the ambiguity |
| Future S4 reads | Stable relational columns provide bounded, typed read inputs without exposing raw rows | S4 must depend on an unbounded JSON shape as its read contract |

OPTION_A is selected because it preserves canonical authority while making the required projections queryable and database-enforceable. OPTION_B is rejected for the comparison contract.

### 6.2 Option A exact table decision

Migration `0025_s3_model_baseline_comparison` alters the existing `model_baseline_comparison` table. It does not create a seventh table. Existing `comparison_status` is renamed to `metric_status` as a compatibility-preserving projection change; the migration must preserve existing rows and reverse the rename on downgrade.

| Column | PostgreSQL type | Nullability/default | Check or key rule | Canonical inclusion | ORM owner | Test owner |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | NOT NULL, generated primary key | primary key | excluded | `ModelBaselineComparisonModel` | postgres-migration |
| `quality_evaluation_run_id` | `BIGINT` | NOT NULL | FK `fk_model_baseline_comparison_run` | excluded | `ModelBaselineComparisonModel` | postgres-migration |
| `naive_baseline_run_id` | `BIGINT` | NOT NULL | FK `fk_model_baseline_comparison_baseline` | excluded | `ModelBaselineComparisonModel` | postgres-migration |
| `schema_version` | `TEXT` | NOT NULL | non-empty version check | included | `ModelBaselineComparisonModel` | postgres-migration |
| `comparison_key_hash` | `TEXT` | NOT NULL | SHA-256 format check; unique with owning run | derived from included identity; not re-input | `ModelBaselineComparisonModel` | postgres-migration |
| `comparison_policy_version` | `TEXT` | NOT NULL | non-empty version check | included | `ModelBaselineComparisonModel` | postgres-migration |
| `comparison_name` | `TEXT` | NOT NULL | exact frozen comparison-name check | included | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `comparison_availability` | `TEXT` | NOT NULL | `AVAILABLE` or `BLOCKED` | included | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `metric_status` | `TEXT` | NOT NULL | existing `MetricStatus` vocabulary check | included | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `reason_code` | `TEXT` | NOT NULL | existing `ReasonCode` vocabulary check | included | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `model_identity` | `JSONB` | NOT NULL | JSON object check | included | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `baseline_identity` | `JSONB` | NOT NULL | normalized baseline canonical identity object check | included | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `normalized_breakdown_identity` | `JSONB` | NOT NULL | exact six-axis object check | included | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `forecast_horizon_days` | `INTEGER` | NOT NULL | greater than zero | included | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `model_value` | `NUMERIC(20,6)` | NULL | conditional nullability check | included when computable | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `baseline_value` | `NUMERIC(20,6)` | NULL | conditional nullability check | included when computable | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `delta_value` | `NUMERIC(20,6)` | NULL | conditional nullability check | included when computable | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `model_input_row_count` | `BIGINT` | NOT NULL | nonnegative | included | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `baseline_input_row_count` | `BIGINT` | NOT NULL | nonnegative | included | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `common_comparable_row_count` | `BIGINT` | NOT NULL | nonnegative and bounded by both inputs | included | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `model_only_row_count` | `BIGINT` | NOT NULL | nonnegative | included | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `baseline_only_row_count` | `BIGINT` | NOT NULL | nonnegative | included | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `excluded_row_count` | `BIGINT` | NOT NULL | nonnegative | included | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `not_computable_row_count` | `BIGINT` | NOT NULL | nonnegative | included | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `canonical_payload` | `JSONB` | NOT NULL | canonical object check | authority payload | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `canonical_hash` | `TEXT` | NOT NULL | SHA-256 format check; unique with owning run | derived from payload | `ModelBaselineComparisonModel` | postgres-domain-1 |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | immutable timestamp | excluded | `ModelBaselineComparisonModel` | postgres-migration |
| `completed_at` | `TIMESTAMPTZ` | NOT NULL | immutable timestamp | excluded | `ModelBaselineComparisonModel` | postgres-migration |

The exact named constraints are frozen:

- `uq_model_baseline_comparison_run_key` on `(quality_evaluation_run_id, comparison_key_hash)`.
- `uq_model_baseline_comparison_run_canonical_hash` on `(quality_evaluation_run_id, canonical_hash)`; the same valid canonical evidence may be reused by a different owning run.
- `ck_model_baseline_comparison_key_sha256` and `ck_model_baseline_comparison_canonical_sha256`.
- `ck_model_baseline_comparison_name_vocabulary`.
- `ck_model_baseline_comparison_availability_vocabulary`.
- `ck_model_baseline_comparison_metric_status_vocabulary`.
- `ck_model_baseline_comparison_reason_code_vocabulary`.
- `ck_model_baseline_comparison_forecast_horizon_positive`.
- `ck_model_baseline_comparison_counters_nonnegative`.
- `ck_model_baseline_comparison_counter_bounds`.
- `ck_model_baseline_comparison_six_axis_identity`.
- `ck_model_baseline_comparison_conditional_values`.

## 7. Canonical identity and manifest projections

### 7.1 Comparison key identity

`comparison_key_hash` is the SHA-256 hash of a canonical JSON identity object with exactly these semantic inputs:

```text
comparison_schema_version
comparison_policy_version
comparison_name
model_identity
baseline canonical identity
normalized six-axis breakdown identity
forecast_horizon_days
```

The baseline canonical identity is the baseline evidence identity, not `naive_baseline_run.id`. The normalized breakdown identity is the exact six-axis object from the Round B contract:

```text
forecast_horizon_days
farm_business_key
subfarm_business_key
variety_business_key
season_business_key
model_identity
```

No database numeric ID, timestamp, worker or host identity, database row order, connection information, or unbounded raw row is an input to `comparison_key_hash`.

### 7.2 Comparison canonical payload

`canonical_payload` contains the semantic identity, comparison availability, metric status, reason code, model identity, baseline identity, normalized six-axis identity, horizon, all non-null computable values, and all seven audit counters. It excludes database numeric IDs, timestamps, worker or host identity, database row order, connection information, and unbounded raw rows.

`canonical_hash=SHA256(canonical_json(canonical_payload))`. Canonical JSON key order, Decimal rendering, null handling, and six-place HALF_EVEN quantization are fixed implementation inputs. Relational projections must be rebuilt from this payload and compared during replay.

### 7.3 Result-set hash

The comparison result-set hash is:

```text
hash(canonical explicit set of sorted comparison canonical hashes)
```

The sorted set is explicit and contains every comparison child for the owning evaluation run. After Round C, the implementation must not use Round B's explicit-empty comparison set hash for a run containing comparison records or for a comparison contract that has been authorized to produce records.

The manifest `comparison_result_set_hash` must equal the rebuilt explicit set hash. A missing, extra, orphaned, reordered, or mismatched comparison child fails closed.

### 7.4 Replay and seal behavior

EXACT_REPLAY_ZERO_WRITE=true
CONFLICTING_REPLAY_REJECTED=true
PARTIAL_COMPARISON_PERSISTENCE_FORBIDDEN=true
MANIFEST_INSERTED_LAST=true
CHILD_AFTER_SEAL_FORBIDDEN=true
CALLER_OWNED_TRANSACTION=true

Exact replay requires equality of semantic key projection, canonical payload/hash, relational projections, audit counters, and the manifest comparison set hash. Same semantic identity with different valid evidence is a conflict. Missing, extra, orphaned, partial, or self-contradictory evidence is a partial result. The function must not commit, rollback, or create a session owned by the caller.

## 8. Exact future implementation path union

The following is the complete and only authorized future Round C implementation union. It is not an authorization to modify these paths now.

FUTURE_IMPLEMENTATION_PATH_COUNT=14
FUTURE_CREATE_PATH_COUNT=5
FUTURE_MODIFY_PATH_COUNT=9
FUTURE_DELETE_PATH_COUNT=0
FUTURE_UNAUTHORIZED_PATH_COUNT=0

| Path | Operation | Fixed future responsibility |
| --- | --- | --- |
| `backend/app/forecast_quality/comparison.py` | CREATE | S3R-24A/S3R-24C/S3R-25 comparison calculation, common-set construction, Decimal contract, canonical identity, and blocked-output contract |
| `backend/app/forecast_quality/persistence.py` | MODIFY | Caller-owned comparison persistence, exact replay classification, relational projection validation, result-set hash, manifest-last seal, and zero-write rules |
| `backend/app/models/forecast_quality.py` | MODIFY | ORM owner for the Option A comparison projections and named constraints |
| `backend/alembic/versions/0025_s3_model_baseline_comparison.py` | CREATE | Forward-only 0025 schema alteration, constraint creation, downgrade, and re-upgrade compatibility |
| `backend/tests/forecast_quality/test_comparison_point.py` | CREATE | PostgreSQL S3R-24A hand-computed point oracle, sign semantics, tie semantics, common-set intersection, and audit counters; owner `postgres-domain-1` |
| `backend/tests/forecast_quality/test_comparison_quantile.py` | CREATE | PostgreSQL S3R-24C blocked quantile and interval outputs; owner `postgres-domain-1` |
| `backend/tests/forecast_quality/test_comparison_delta.py` | CREATE | PostgreSQL S3R-25 delta semantics, signed-bias direction-only semantics, and projection/canonical checks; owner `postgres-domain-1` |
| `backend/tests/forecast_quality/test_persistence.py` | MODIFY | PostgreSQL 0025 migration round trip, comparison table projections, nullability, FK, unique, hash, and direct SQL rejection probes; owner `postgres-migration` |
| `backend/tests/forecast_quality/test_idempotency.py` | MODIFY | Non-concurrency exact replay/conflict/partial/immutability tests owned by `postgres-domain-1`; nodes marked `postgres_concurrency` and `concurrency` owned by `postgres-concurrency` |
| `backend/tests/forecast_quality/test_blocked_surfaces.py` | MODIFY | Pure contract assertions that S3R-24B, S3R-22, S3R-23, HTTP API, frontend, S4, and S5 remain blocked; owner `unit-contract-golden` |
| `backend/tests/actual_harvest_import/alembic_cases.py` | MODIFY | 0025 revision/down-revision and single-head lineage helper assertions; exercised by `postgres-migration` |
| `backend/tests/test_historical_backtest_alembic.py` | MODIFY | 0024-to-0025 migration compatibility and upgrade/downgrade/re-upgrade historical assertions; owner `postgres-migration` |
| `ci-shard-manifest.yml` | MODIFY | Add the three new comparison test files to the existing `postgres-domain-1` ownership and record the exact marker precedence; no new job |
| `.github/workflows/ci.yml` | MODIFY | Add the three new comparison test files to the existing `postgres-domain-1` pytest argument list; no new job, event, service, port, credential, or canary change |

The two CI files are included because the current workflow uses explicit pytest file lists and the current manifest does not collect the three new comparison test paths. Their modification is therefore required for collection and ownership proof, while job names, job count, event triggers, PostgreSQL service configuration, and `full-suite-canary` policy remain unchanged.

No second local branch, seventh table, public API, production data path, or path outside this 14-path union is authorized for the future implementation.

## 9. CI ownership freeze

CI_OWNERSHIP_FROZEN=true
CI_JOB_COUNT_CHANGE=0
CI_EVENT_CHANGE=0
CI_POSTGRES_SERVICE_CHANGE=0
CI_FULL_SUITE_CANARY_ON_PULL_REQUEST=false

| Test path or node class | Unique PR CI owner | Collection rule |
| --- | --- | --- |
| `backend/tests/forecast_quality/test_comparison_point.py` | `postgres-domain-1` | Explicit file argument in domain-1; no other PR job includes the file |
| `backend/tests/forecast_quality/test_comparison_quantile.py` | `postgres-domain-1` | Explicit file argument in domain-1; no other PR job includes the file |
| `backend/tests/forecast_quality/test_comparison_delta.py` | `postgres-domain-1` | Explicit file argument in domain-1; no other PR job includes the file |
| `backend/tests/forecast_quality/test_persistence.py` | `postgres-migration` | Existing explicit migration argument; no other PR job includes the file |
| `backend/tests/test_historical_backtest_alembic.py` | `postgres-migration` | Existing explicit migration argument; no other PR job includes the file |
| Non-concurrency nodes in `backend/tests/forecast_quality/test_idempotency.py` | `postgres-domain-1` | Existing explicit domain-1 argument plus `-m "not postgres_concurrency"` |
| `postgres_concurrency` nodes in `backend/tests/forecast_quality/test_idempotency.py` | `postgres-concurrency` | Existing explicit concurrency argument plus `-m postgres_concurrency` |
| `backend/tests/forecast_quality/test_blocked_surfaces.py` | `unit-contract-golden` | Marker-residual unit selector; file remains without PostgreSQL markers |

The ownership proof is frozen at node level:

```text
DUPLICATE_EXECUTION_NODE_COUNT=0
UNOWNED_TEST_NODE_COUNT=0
```

Every new PostgreSQL node appears in one explicit owning shard only. The marker sharp selector sends concurrency nodes to `postgres-concurrency`; domain-1 excludes those nodes. The new pure blocked-surface nodes remain in the unit residual selector and carry no PostgreSQL marker.

## 10. Frozen acceptance matrix

The future implementation is incomplete until every row below has a passing test in its unique owner.

| # | Required acceptance | Required owner |
| ---: | --- | --- |
| 1 | Hand-computed daily point comparison oracle | `postgres-domain-1` |
| 2 | Positive delta means model worse for loss and magnitude outputs | `postgres-domain-1` |
| 3 | Negative delta means model better for loss and magnitude outputs | `postgres-domain-1` |
| 4 | Zero delta is a tie | `postgres-domain-1` |
| 5 | Signed bias is direction only and uses `COMPARED` plus `SIGNED_DIRECTION_ONLY` | `postgres-domain-1` |
| 6 | Common comparable set is the semantic intersection | `postgres-domain-1` |
| 7 | Model-only and baseline-only audit counts are preserved | `postgres-domain-1` |
| 8 | Baseline quantile comparison remains `NOT_COMPUTABLE` with the frozen reason | `postgres-domain-1` |
| 9 | Interval width remains `NOT_COMPUTABLE` with the frozen reason | `postgres-domain-1` |
| 10 | Complete-window comparisons remain blocked with the S2 authority reason | `unit-contract-golden` and `postgres-domain-1` |
| 11 | Exact replay performs zero writes | `postgres-domain-1` |
| 12 | Conflicting replay is rejected | `postgres-domain-1` |
| 13 | Partial comparison result is rejected | `postgres-domain-1` |
| 14 | Manifest comparison set hash equals the exact rebuilt set | `postgres-domain-1` and `postgres-migration` |
| 15 | Comparison rows are immutable | `postgres-domain-1` |
| 16 | Child insert after manifest seal is rejected | `postgres-domain-1` |
| 17 | PostgreSQL concurrent identical comparison persistence converges to one result | `postgres-concurrency` |
| 18 | PostgreSQL concurrent conflicting comparison persistence has one conflict and no partial result | `postgres-concurrency` |
| 19 | 0025 upgrade, downgrade, and re-upgrade preserve the single head | `postgres-migration` |
| 20 | Malformed hash, FK, unique, conditional-nullability, vocabulary, horizon, counter, and six-axis rejection probes are real database probes | `postgres-migration` |

The acceptance matrix requires isolation for negative probes and zero committed test pollution. A direct SQL rejection probe must execute the illegal write against PostgreSQL and observe database rejection; metadata-only constraint-name inspection is insufficient.

## 11. Explicit non-scope

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

This authorization does not authorize marking the PR ready, merging the PR, deleting the branch, cleaning the worktree, opening real data, executing a backtest, or closing Issue #102.

## 12. Review and handoff gates

The document itself is complete only as a proposed authorization artifact. Independent review must verify:

1. The document is the only changed repository path.
2. The implementation path union is exactly 14 paths with 5 creates, 9 modifies, and 0 deletes.
3. Option A and migration `0025_s3_model_baseline_comparison` are explicitly selected.
4. The three Round C requirements and the continued S3R-24B block are preserved.
5. CI ownership has zero duplicate and zero unowned test nodes.
6. The Draft PR head equals the committed document head.
7. Exact-head CI completes successfully without enabling `full-suite-canary` on pull requests.

ROUND_C_AUTHORIZATION_DOCUMENT_ACCEPTED=false
STOPPED_AWAITING_INDEPENDENT_REVIEW=true
NO_STEP_IMPLIES_THE_NEXT=true
