# V0.2-S3 Implementation Readiness Matrix

> Target: V0.2-S3 (FORECAST_QUALITY_METRICS_AND_ONE_NAIVE_BASELINE)
> Companion: `docs/forecast-quality/s3-quality-metrics-contract.md`
> Companion: `docs/forecast-quality/s3-naive-baseline-decision.md`
> Document status: S3 design-freeze readiness authority
> Latest consistency review addressed: F32–F35
> Source base: `b873dd63fc0d5b6375f94674abbd24a94d915f3c`
> Source authority: `docs/forecast-quality/q2b-point-in-time-backtest-runner-contract.md` (S2 binding + manifest)
> Round 5 fixup scope: F32–F35 closure (PR131 round 5)

```text
S3_IMPLEMENTATION_AUTHORIZED=false
S3_READINESS_MATRIX_DOCUMENTS_BLOCKERS=true
READY=NO
MERGE=NO
ISSUE102_CLOSE=NO
NO_STEP_IMPLIES_THE_NEXT=true
NO_OTHER_OPEN_BLOCKERS=false
```

## 1. Purpose

This document freezes the per-requirement implementation readiness matrix for
S3 using a single readiness model of one ready state plus four governance
classes. It records the design status, the candidate implementation owner
path, the candidate test owner path, the database requirement, the
concurrency requirement, the migration requirement, the readiness value,
and the acceptance test for each requirement. S3 implementation is NOT
authorized in this round. The matrix is the contract for a future
`S3_IMPLEMENTATION_AUTHORIZED_ONLY` round that introduces the calculator,
internal application service, schema, migration, persistence and tests.

```text
PUBLIC_APPLICATION_API=false
HTTP_API=false
FRONTEND_API=false
S4_API_SCOPE_PREEMPTED=false
INTERNAL_PYTHON_APPLICATION_SERVICE_ALLOWED=true
INTERNAL_DOMAIN_SERVICE_ALLOWED=true
```

S3 may expose an internal Python application/service interface for use
inside the backend process. Public HTTP/application API ownership remains
exclusively in V0.2-S4.

The matrix does NOT create the implementation files. It does NOT
pre-allocate any path under `backend/app/`, `backend/alembic/versions/`,
`backend/tests/` or `backend/docs/`. The candidate paths are descriptive
shapes for a future implementation round, not a green light to create
those files.

## 2. Readiness model (frozen)

The matrix classifies every requirement into exactly one of five
readiness values: one ready state and four governance classes. The
ready state and the four governance classes are disjoint; every
requirement picks exactly one value. The vocabulary is closed.

```text
READINESS_MODEL=FOUR_GOVERNANCE_CLASSES_PLUS_READY_STATE
READY_STATE=READY_PENDING_IMPLEMENTATION_AUTHORIZATION
READY_STATE_COUNT=1
GOVERNANCE_CLASSES=BLOCKED_BY_EXTERNAL_AUTHORITY, IMPLEMENTATION_OBLIGATION, FROZEN_NOT_COMPUTABLE_LIMITATION, CLOSED_CONTRACT_ALIGNMENT
GOVERNANCE_CLASS_COUNT=4
TOTAL_READINESS_VALUE_COUNT=5
READINESS_COLUMN_CONTAINS=ONE_READY_STATE_OR_ONE_OF_FOUR_GOVERNANCE_CLASSES
```

Definitions:

```text
READY_PENDING_IMPLEMENTATION_AUTHORIZATION = design is frozen and no external authority blocks implementation, but implementation still requires Charles's separate authorization
BLOCKED_BY_EXTERNAL_AUTHORITY = cannot be implemented or published until an upstream authority gap is independently closed
IMPLEMENTATION_OBLIGATION = frozen design behavior that the future authorized S3 implementation round must implement and test
FROZEN_NOT_COMPUTABLE_LIMITATION = intentional v1 boundary represented by explicit status and reason code
CLOSED_CONTRACT_ALIGNMENT = contract alignment already resolved and no longer an open blocker
```

Frozen enumeration of blockers, obligations, limitations and closed
alignments across the three S3 documents:

```text
EXTERNAL_PREIMPLEMENTATION_BLOCKERS = S2_COMPLETE_DAILY_ROW_SET_AUTHORITY, P50_P80_P90_SEMANTICS_VERIFICATION
IMPLEMENTATION_OBLIGATIONS = MAPE_COUNTER_WIRING, SEASON_ANALOG_MAPPING_IMPLEMENTATION, BASELINE_SOURCE_VISIBILITY_ENFORCEMENT, BASELINE_SOURCE_SNAPSHOT_BINDING, SUBFARM_TO_FARM_AGGREGATION_IMPLEMENTATION, CROSS_QUANTILE_ACTUAL_DEDUP_IMPLEMENTATION, DECIMAL_ONLY_METRIC_IMPLEMENTATION, CANONICAL_IDENTITY_IMPLEMENTATION, PERSISTENCE_AND_IDEMPOTENCY_IMPLEMENTATION
FROZEN_NOT_COMPUTABLE_LIMITATIONS = BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED, PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE
CLOSED_CONTRACT_ALIGNMENT = PINBALL_UPSTREAM_CONTRACT_ALIGNMENT
```

Specific impact mapping:

```text
S2_COMPLETE_DAILY_ROW_SET_AUTHORITY_BLOCKS = complete-window cumulative metrics; single-day peak over a complete requested window; sustained 7-day peak; complete-window comparison outputs
P50_P80_P90_SEMANTICS_VERIFICATION_BLOCKS = quantile coverage publication; pinball-loss publication; any interpretation requiring verified quantile semantics
```

The matrix `READINESS_VALUE` (column header `READINESS_CLASS`) for any
requirement MUST contain one of the five values above; no other token
may appear in that column.

Daily point-forecast metrics are NOT gated on the S2 daily-row-set
amendment. Their readiness is recorded separately:

```text
DAILY_POINT_METRICS_IMPLEMENTATION_BLOCKED_BY_DAILY_ROW_SET = false
DAILY_POINT_METRICS_IMPLEMENTATION_READINESS = READY_PENDING_SEPARATE_S3_IMPLEMENTATION_AUTHORIZATION
```

`PINBALL_UPSTREAM_CONTRACT_ALIGNMENT` is the only item in
`CLOSED_CONTRACT_ALIGNMENT`. It MUST NOT appear in any open-blocker
list.

## 3. Requirement matrix

| REQUIREMENT | DESIGN_STATUS | IMPLEMENTATION_OWNER_PATH | TEST_OWNER_PATH | POSTGRES_REQUIRED | CONCURRENCY_REQUIRED | MIGRATION_REQUIRED | READINESS_CLASS | EXTERNAL_BLOCKER | CONTRACT_ALIGNMENT | ACCEPTANCE_TEST |
|-------------|---------------|---------------------------|-----------------|-------------------|----------------------|--------------------|-----------------|------------------|--------------------|-----------------|
| S3R-01 daily point-forecast metrics (daily_mae, daily_wape, daily_smape, daily_mape, daily_bias_kg, daily_relative_bias, daily_absolute_error_sum_kg) | FROZEN | backend/app/forecast_quality/calculator_daily.py | backend/tests/forecast_quality/test_calculator_daily.py | yes | no | no | READY_PENDING_IMPLEMENTATION_AUTHORIZATION | none |  | pytest measure over 50+ hand-computed comparable rows |
| S3R-02 complete-window cumulative metrics (forecast_kg, actual_kg, signed_error_kg, absolute_error_kg, signed_relative_error, absolute_relative_error) | FROZEN | backend/app/forecast_quality/calculator_cumulative.py | backend/tests/forecast_quality/test_calculator_cumulative.py | yes | no | no | BLOCKED_BY_EXTERNAL_AUTHORITY | S2_COMPLETE_DAILY_ROW_SET_AUTHORITY |  | pytest sum over hand-picked rows |
| S3R-03 denominator-zero policy (NOT_COMPUTABLE + reason_code) | FROZEN | backend/app/forecast_quality/calculator_daily.py | backend/tests/forecast_quality/test_zero_policy.py | yes | no | no | IMPLEMENTATION_OBLIGATION | none |  | pytest zero-division negative tests |
| S3R-04 MAPE counter semantics (mape_eligible_row_count, mape_zero_actual_row_count, EXCLUDE_ZERO_ACTUAL) | FROZEN | backend/app/forecast_quality/calculator_daily.py | backend/tests/forecast_quality/test_mape.py | yes | no | no | IMPLEMENTATION_OBLIGATION | none |  | pytest zero-actual rows counted in mape_zero_actual_row_count |
| S3R-05 smape double-zero policy (ROW_CONTRIBUTES_ZERO) | FROZEN | backend/app/forecast_quality/calculator_daily.py | backend/tests/forecast_quality/test_smape.py | yes | no | no | IMPLEMENTATION_OBLIGATION | none |  | pytest double-zero rows contribute 0 |
| S3R-06 complete-window single-day peak (P50, P80, P90) with earliest tie-break | FROZEN | backend/app/forecast_quality/peak.py | backend/tests/forecast_quality/test_peak.py | yes | no | no | BLOCKED_BY_EXTERNAL_AUTHORITY | S2_COMPLETE_DAILY_ROW_SET_AUTHORITY |  | pytest tied dates select earliest |
| S3R-07 sustained 7-day peak with NO zero-fill missing days | FROZEN | backend/app/forecast_quality/peak.py | backend/tests/forecast_quality/test_peak_7day.py | yes | no | no | BLOCKED_BY_EXTERNAL_AUTHORITY | S2_COMPLETE_DAILY_ROW_SET_AUTHORITY |  | pytest incomplete windows rejected |
| S3R-08 single naive baseline (PRIOR_SEASON_ANALOG_DAY_ACTUAL, point) | FROZEN | backend/app/forecast_quality/baseline.py | backend/tests/forecast_quality/test_baseline.py | yes | no | no | IMPLEMENTATION_OBLIGATION | none |  | pytest prior-season analog-day actual against hand-computed |
| S3R-09 baseline cold-start (FAIL_CLOSED + NOT_COMPUTABLE) | FROZEN | backend/app/forecast_quality/baseline.py | backend/tests/forecast_quality/test_baseline_cold.py | yes | no | no | IMPLEMENTATION_OBLIGATION | none |  | pytest no prior season → NOT_COMPUTABLE |
| S3R-10 baseline visibility rule (visible at or before current forecast_cutoff_at), separate baseline source snapshot | FROZEN | backend/app/forecast_quality/baseline.py | backend/tests/forecast_quality/test_baseline_visibility.py | yes | no | no | IMPLEMENTATION_OBLIGATION | none |  | BASELINE_VISIBILITY_ACCEPTANCE_TEST=ALLOW_PRIOR_ANALOG_ACTUAL_VISIBLE_BY_CURRENT_CUTOFF_AND_REJECT_LATER_REVISION |
| S3R-11 baseline prohibits post-cutoff / latest / model / receipt / zero | FROZEN | backend/app/forecast_quality/baseline.py | backend/tests/forecast_quality/test_baseline_red.py | yes | no | no | IMPLEMENTATION_OBLIGATION | none |  | pytest each prohibited source flagged |
| S3R-12 baseline point-only (P80/P90 NOT_COMPUTABLE) | FROZEN | backend/app/forecast_quality/baseline.py | backend/tests/forecast_quality/test_baseline_quantile.py | yes | no | no | FROZEN_NOT_COMPUTABLE_LIMITATION | none |  | pytest p80 / p90 deltas → comparison_availability=BLOCKED, metric_status=NOT_COMPUTABLE, reason_code=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED |
| S3R-13 breakdown contract (horizon / farm / subfarm / variety / season / model) | FROZEN | backend/app/forecast_quality/breakdown.py | backend/tests/forecast_quality/test_breakdown.py | yes | no | no | IMPLEMENTATION_OBLIGATION | none |  | BREAKDOWN_ACCEPTANCE_TEST=all six required axes produce deterministic breakdown cells |
| S3R-14 INSUFFICIENT_SAMPLE below MIN_COMPARABLE_ROWS_FOR_REPORTING=10 | FROZEN | backend/app/forecast_quality/breakdown.py | backend/tests/forecast_quality/test_breakdown_min.py | yes | no | no | IMPLEMENTATION_OBLIGATION | none |  | pytest small-sample cells flagged, not dropped |
| S3R-15 cross-quantile actual-label dedup (one actual per physical grain; P50/P80/P90 forecast rows join to SAME actual) | FROZEN | backend/app/forecast_quality/canonical.py | backend/tests/forecast_quality/test_actual_dedup.py | yes | no | no | IMPLEMENTATION_OBLIGATION | none |  | pytest single actual label per physical grain, reused across quantiles |
| S3R-16 subfarm-to-farm aggregation (sum of subfarm_q_i over exact deduped actual rows; max-single-subfarm is NOT farm peak) | FROZEN | backend/app/forecast_quality/aggregation.py | backend/tests/forecast_quality/test_aggregation.py | yes | no | no | IMPLEMENTATION_OBLIGATION | none |  | pytest farm-level peak equals sum of subfarm-level amounts |
| S3R-17 duplicate policy (forecast business key, actual physical key, target date after aggregation = STRUCTURAL_FAILURE) | FROZEN | backend/app/forecast_quality/canonical.py | backend/tests/forecast_quality/test_dedup.py | yes | no | no | IMPLEMENTATION_OBLIGATION | none |  | pytest duplicate rejected with STRUCTURAL_FAILURE |
| S3R-18 canonical identity binding (s2_run, s2_manifest, row_set_hash, metric_policy_version, baseline_policy_version, breakdown; baseline_source_snapshot_identity, baseline_source_visibility_manifest_hash) | FROZEN | backend/app/forecast_quality/canonical.py | backend/tests/forecast_quality/test_canonical.py | yes | no | no | IMPLEMENTATION_OBLIGATION | none |  | pytest canonical hash byte-identical across replay |
| S3R-19 persistence: QualityEvaluationRun, QualityMetricResult, QualityBreakdownResult, NaiveBaselineRun, ModelBaselineComparison, QualityEvaluationManifest | FROZEN | backend/app/forecast_quality/persistence.py | backend/tests/forecast_quality/test_persistence.py | yes | yes | yes | IMPLEMENTATION_OBLIGATION | none |  | alembic upgrade head + pytest round-trip + pytest concurrent |
| S3R-20 idempotent persistence (EXACT_REPLAY_ZERO_WRITE, CONFLICTING_REPLAY_REJECTED, PARTIAL_METRIC_PERSISTENCE_FORBIDDEN) | FROZEN | backend/app/forecast_quality/persistence.py | backend/tests/forecast_quality/test_idempotency.py | yes | yes | yes | IMPLEMENTATION_OBLIGATION | none |  | pytest replay same inputs → no second row; conflicting inputs → reject |
| S3R-21 Decimal + 1e-6 + ROUND_HALF_EVEN canonical payload emit; DECIMAL_ONLY_CANONICAL_ARITHMETIC=true; native float / numpy float / binary float NOT allowed at any intermediate step | FROZEN | backend/app/forecast_quality/canonical.py | backend/tests/forecast_quality/test_decimal.py | yes | no | no | IMPLEMENTATION_OBLIGATION | none |  | pytest canonical payload bytes match `str(Decimal(1e-6))`; no float intermediate |
| S3R-22 P50 / P80 / P90 coverage gated on QUANTILE_SEMANTICS_VERIFICATION | FROZEN | backend/app/forecast_quality/quantile.py | backend/tests/forecast_quality/test_quantile.py | yes | no | no | BLOCKED_BY_EXTERNAL_AUTHORITY | P50_P80_P90_SEMANTICS_VERIFICATION |  | pytest coverage not published until semantic verified |
| S3R-23 pinball loss preserved (NOT_COMPUTABLE gated on QUANTILE_SEMANTICS_VERIFICATION; UPSTREAM_CONTRACT_AMENDMENT_ACCEPTED=false) | FROZEN | backend/app/forecast_quality/quantile.py | backend/tests/forecast_quality/test_pinball.py | yes | no | no | BLOCKED_BY_EXTERNAL_AUTHORITY | P50_P80_P90_SEMANTICS_VERIFICATION | PINBALL_UPSTREAM_CONTRACT_ALIGNMENT_CLOSED | pytest pinball loss NOT_COMPUTABLE until semantic verified |
| S3R-24A_DAILY_POINT_HEAD_TO_HEAD daily point head-to-head comparison over COMMON_COMPARABLE_SET (daily_mae_delta, daily_wape_delta, daily_smape_delta, daily_mape_delta, absolute_bias_magnitude_delta, signed_bias_delta) | FROZEN | backend/app/forecast_quality/comparison.py | backend/tests/forecast_quality/test_comparison_point.py | yes | no | no | IMPLEMENTATION_OBLIGATION | none |  | POINT_HEAD_TO_HEAD_OVER=COMMON_COMPARABLE_SET; daily-point loss/magnitude deltas (daily_mae_delta, daily_wape_delta, daily_smape_delta, daily_mape_delta, absolute_bias_magnitude_delta) publish metric_status=COMPUTED, reason_code=NONE; signed_bias_delta publishes metric_status=COMPARED, reason_code=SIGNED_DIRECTION_ONLY; pytest daily point deltas computed over COMMON_COMPARABLE_SET without deleting model-only or baseline-only rows |
| S3R-24B_COMPLETE_WINDOW_HEAD_TO_HEAD complete-window head-to-head (absolute_cumulative_bias_magnitude_delta, signed_cumulative_error_delta, single_day_peak_date_absolute_error_delta_q, single_day_peak_quantity_absolute_error_delta_q, sustained_7day_start_date_absolute_error_delta_q, sustained_7day_quantity_absolute_error_delta_q) | FROZEN | backend/app/forecast_quality/comparison.py | backend/tests/forecast_quality/test_comparison_window.py | yes | no | no | BLOCKED_BY_EXTERNAL_AUTHORITY | S2_COMPLETE_DAILY_ROW_SET_AUTHORITY |  | COMPLETE_WINDOW_HEAD_TO_HEAD_STATUS_BEFORE_AMENDMENT=NOT_COMPUTABLE; COMPLETE_WINDOW_HEAD_TO_HEAD_REASON_BEFORE_AMENDMENT=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING; signed_cumulative_error_delta publishes comparison_availability=BLOCKED, metric_status=NOT_COMPUTABLE, reason_code=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING, external_blocker=S2_COMPLETE_DAILY_ROW_SET_AUTHORITY |
| S3R-24C_BASELINE_QUANTILE_AND_INTERVAL_HEAD_TO_HEAD baseline quantile and interval head-to-head (p80_coverage_delta, p90_coverage_delta, interval_width_delta, baseline_p80_p90_peak_comparison) | FROZEN | backend/app/forecast_quality/comparison.py | backend/tests/forecast_quality/test_comparison_quantile.py | yes | no | no | FROZEN_NOT_COMPUTABLE_LIMITATION | none |  | p80_coverage_delta + p90_coverage_delta + baseline_p80_p90_peak_comparison publish reason_code=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED, external_blocker=none, frozen_limitation=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED; interval_width_delta publishes reason_code=PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE, external_blocker=none, frozen_limitation=PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE |
| S3R-25 comparison delta semantics (loss_delta, signed_delta, absolute-bias-magnitude_delta) | FROZEN | backend/app/forecast_quality/comparison.py | backend/tests/forecast_quality/test_comparison_delta.py | yes | no | no | IMPLEMENTATION_OBLIGATION | none |  | pytest loss_delta positive=worse; signed_delta direction only; magnitude_delta positive=worse |
| S3R-26 Slice Q2B / Q2C / Q2D / Q2E / Q2F governance dependencies untouched | FROZEN (boundary) | backend/app/forecast_quality/(none) | backend/tests/forecast_quality/(none) | n/a | n/a | n/a | CLOSED_CONTRACT_ALIGNMENT | none | PINBALL_UPSTREAM_CONTRACT_ALIGNMENT_CLOSED | n/a |

## 4. Schema dependencies

The schema is a candidate shape only. The implementation round must write
the actual Alembic migration and the actual ORM models. The candidate
shape is:

```text
QualityEvaluationRun       — one row per S3 evaluation
QualityMetricResult        — one row per metric value (per breakdown cell)
QualityBreakdownResult     — one row per breakdown cell with comparable/excluded/not-computable counts
NaiveBaselineRun           — one row per baseline evaluation
ModelBaselineComparison    — one row per head-to-head delta
QualityEvaluationManifest  — one row per S3 evaluation manifest
```

The schema shape is bound to the canonical identity contract:

```text
semantic_business_identity  — present on every row
database_lookup_identity   — present where needed for FK / lookup
canonical_hash             — present on every row, covers schema_version + business identity + breakdown
```

The canonical hash payload MUST NOT contain any of:

```text
database numeric IDs
insertion timestamps
runtime host or worker IDs
database row order
unbounded raw business rows
credentials or connection strings
```

## 5. Persistence governance

```text
CALLER_OWNED_TRANSACTION=true
IMMUTABLE_RESULT=true
EXACT_REPLAY_ZERO_WRITE=true
CONFLICTING_REPLAY_REJECTED=true
PARTIAL_METRIC_PERSISTENCE_FORBIDDEN=true
```

The metric result is append-only. A replay with the same inputs MUST
produce the same canonical hash and MUST NOT create a second row. A
replay with different inputs that yields the same canonical hash is
rejected with `CONFLICTING_REPLAY_REJECTED`. Partial metric persistence
is forbidden; the result is all-or-nothing.

## 6. Real data and Issue #102

```text
REAL_DATA_OPENED=false
REAL_DATA_BACKTEST_EXECUTED=false
DATA_IMPORTED=false
MODEL_CHANGED=false
BUSINESS_ATTESTATION_COLLECTION=false
ISSUE102_CLOSE_AUTHORIZED=false
```

S3 is design-only. Real data, real backtest, business attestation
collection, and Issue #102 close are all out of scope. The S3 contract
allows synthetic-path implementation without business attestation, but
real-data acceptance still requires business attestation.

## 7. Out-of-scope

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

S3 is a design freeze. Implementation, S4 API, S5 frontend, and Issue #102
close are explicitly out of scope.

## 8. Implementation authorization gate

```text
S3_IMPLEMENTATION_AUTHORIZED=false
```

The implementation round must be a separate authorization round with
explicit `S3_IMPLEMENTATION_AUTHORIZED_ONLY` authorization. The matrix
above is the contract for that future round. The implementation round
MUST NOT begin before this authorization is granted. The implementation
round MUST NOT silently expand to S4 or S5.

```text
NO_STEP_IMPLIES_THE_NEXT=true
```

## 9. Readiness class cross-reference (replaces blockers-vs-requirement)

```text
S2_COMPLETE_DAILY_ROW_SET_AUTHORITY
  - S3R-02 complete-window cumulative metrics
  - S3R-06 complete-window single-day peak
  - S3R-07 sustained 7-day peak

P50_P80_P90_SEMANTICS_VERIFICATION
  - S3R-22 P50 / P80 / P90 coverage
  - S3R-23 pinball loss

S2_COMPLETE_DAILY_ROW_SET_AUTHORITY
  - S3R-24B_COMPLETE_WINDOW_HEAD_TO_HEAD complete-window head-to-head

BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
  - S3R-12 baseline point-only
  - S3R-24C baseline quantile and interval head-to-head

PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE
  - S3R-24C baseline quantile and interval head-to-head

DAILY_POINT_HEAD_TO_HEAD_BLOCKED_BY_DAILY_ROW_SET=false
DAILY_POINT_HEAD_TO_HEAD_NOT_COMPUTABLE=false
COMPLETE_WINDOW_HEAD_TO_HEAD_BLOCKED=true
COMPLETE_WINDOW_HEAD_TO_HEAD_BLOCKER=S2_COMPLETE_DAILY_ROW_SET_AUTHORITY
COMPLETE_WINDOW_HEAD_TO_HEAD_STATUS_BEFORE_AMENDMENT=NOT_COMPUTABLE
COMPLETE_WINDOW_HEAD_TO_HEAD_REASON_BEFORE_AMENDMENT=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
BASELINE_QUANTILE_HEAD_TO_HEAD_NOT_COMPUTABLE=true
BASELINE_QUANTILE_HEAD_TO_HEAD_REASON=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
PREDICTION_INTERVAL_HEAD_TO_HEAD_NOT_COMPUTABLE=true
PREDICTION_INTERVAL_HEAD_TO_HEAD_REASON=PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE

MODEL_QUANTILE_PUBLICATION_GATE=P50_P80_P90_SEMANTICS_VERIFICATION
BASELINE_QUANTILE_COMPARISON_LIMITATION=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED

PINBALL_UPSTREAM_CONTRACT_ALIGNMENT_CLOSED
  - S3R-23 pinball loss (alignment closed; only quantile-semantics verification remains)
  - S3R-26 Slice Q2B / Q2C / Q2D / Q2E / Q2F governance
```