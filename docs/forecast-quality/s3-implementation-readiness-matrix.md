# V0.2-S3 Implementation Readiness Matrix

> Target: V0.2-S3 (FORECAST_QUALITY_METRICS_AND_ONE_NAIVE_BASELINE)
> Companion: `docs/forecast-quality/s3-quality-metrics-contract.md`
> Companion: `docs/forecast-quality/s3-naive-baseline-decision.md`
> Scope: per-requirement implementation readiness + owner path + acceptance test
> Base: `b873dd63fc0d5b6375f94674abbd24a94d915f3c`
> Source authority: `docs/forecast-quality/q2b-point-in-time-backtest-runner-contract.md` (S2 binding + manifest)

```text
S3_IMPLEMENTATION_AUTHORIZED=false
S3_READINESS_MATRIX_OUT_OF_SCOPE_FOR_NOW=true
READY=NO
MERGE=NO
ISSUE102_CLOSE=NO
NO_STEP_IMPLIES_THE_NEXT=true
```

## 1. Purpose

This document freezes the per-requirement implementation readiness matrix for
S3. It records the design status, the candidate implementation owner path,
the candidate test owner path, the database requirement, the concurrency
requirement, the migration requirement, the open blocker, and the
acceptance test for each requirement. S3 implementation is NOT authorized
in this round. The matrix is the contract for a future
`S3_IMPLEMENTATION_AUTHORIZED_ONLY` round that introduces the calculator,
schema, migration, API and tests.

The matrix does NOT create the implementation files. It does NOT
pre-allocate any path under `backend/app/`, `backend/alembic/versions/`,
`backend/tests/` or `backend/docs/`. The candidate paths are descriptive
shapes for a future implementation round, not a green light to create
those files.

## 2. Requirement matrix

```text
REQUIREMENT                                                             | DESIGN_STATUS | IMPLEMENTATION_OWNER_PATH                              | TEST_OWNER_PATH                                       | POSTGRES_REQUIRED | CONCURRENCY_REQUIRED | MIGRATION_REQUIRED | OPEN_BLOCKER | ACCEPTANCE_TEST
----------------------------------------------------------------------|---------------|-------------------------------------------------------|-------------------------------------------------------|-------------------|----------------------|--------------------|--------------|---------------
S3R-01 quality metric calculator (daily_mae, daily_wape, daily_smape,
         daily_mape, daily_bias_kg, daily_relative_bias,
         daily_absolute_error_sum_kg) on comparable rows               | FROZEN        | backend/app/forecast_quality/calculator.py            | backend/tests/forecast_quality/test_calculator.py      | yes               | no                   | no                 | none         | pytest measure over 50+ hand-computed comparable rows
S3R-02 season cumulative metric set (forecast_kg, actual_kg,
         signed_error_kg, absolute_error_kg, signed_relative_error,
         absolute_relative_error)                                      | FROZEN        | backend/app/forecast_quality/calculator.py            | backend/tests/forecast_quality/test_calculator.py      | yes               | no                   | no                 | none         | pytest sum over hand-picked rows
S3R-03 denominator-zero policy (NOT_COMPUTABLE + reason_code)          | FROZEN        | backend/app/forecast_quality/calculator.py            | backend/tests/forecast_quality/test_zero_policy.py     | yes               | no                   | no                 | none         | pytest zero-division negative tests
S3R-04 MAPE zero policy (EXCLUDE_ZERO_ACTUAL_WITH_EXPLICIT_COUNT)      | FROZEN        | backend/app/forecast_quality/calculator.py            | backend/tests/forecast_quality/test_mape.py            | yes               | no                   | no                 | none         | pytest zero-actual rows counted in excluded_row_count
S3R-05 smape double-zero policy (ROW_CONTRIBUTES_ZERO)                  | FROZEN        | backend/app/forecast_quality/calculator.py            | backend/tests/forecast_quality/test_smape.py           | yes               | no                   | no                 | none         | pytest double-zero rows contribute 0
S3R-06 single-day peak per quantile (P50, P80, P90) with earliest tie-break | FROZEN    | backend/app/forecast_quality/peak.py                  | backend/tests/forecast_quality/test_peak.py             | yes               | no                   | no                 | none         | pytest tied dates select earliest
S3R-07 sustained 7-day peak with NO zero-fill missing days             | FROZEN        | backend/app/forecast_quality/peak.py                  | backend/tests/forecast_quality/test_peak_7day.py       | yes               | no                   | no                 | none         | pytest incomplete windows rejected
S3R-08 single naive baseline (PRIOR_SEASON_SAME_GRAIN_SAME_WINDOW_MEAN) | FROZEN      | backend/app/forecast_quality/baseline.py              | backend/tests/forecast_quality/test_baseline.py        | yes               | no                   | no                 | none         | pytest prior-season mean against hand-computed
S3R-09 baseline cold-start (FAIL_CLOSED + NOT_COMPUTABLE)               | FROZEN        | backend/app/forecast_quality/baseline.py              | backend/tests/forecast_quality/test_baseline_cold.py   | yes               | no                   | no                 | none         | pytest no prior season → NOT_COMPUTABLE
S3R-10 baseline prohibits post-cutoff / latest / model / receipt / zero | FROZEN        | backend/app/forecast_quality/baseline.py              | backend/tests/forecast_quality/test_baseline_red.py    | yes               | no                   | no                 | none         | pytest each prohibited source flagged
S3R-11 breakdown contract (horizon / farm / variety / season / model)   | FROZEN        | backend/app/forecast_quality/breakdown.py             | backend/tests/forecast_quality/test_breakdown.py       | yes               | no                   | no                 | none         | pytest breakdown cells match the axes
S3R-12 INSUFFICIENT_SAMPLE below MIN_COMPARABLE_ROWS_FOR_REPORTING=10  | FROZEN        | backend/app/forecast_quality/breakdown.py             | backend/tests/forecast_quality/test_breakdown_min.py   | yes               | no                   | no                 | none         | pytest small-sample cells flagged, not dropped
S3R-13 canonical identity binding (s2_run, s2_manifest, row_set_hash,
         metric_policy_version, baseline_policy_version, breakdown)   | FROZEN        | backend/app/forecast_quality/canonical.py             | backend/tests/forecast_quality/test_canonical.py       | yes               | no                   | no                 | none         | pytest canonical hash byte-identical across replay
S3R-14 persistence: QualityEvaluationRun, QualityMetricResult,
         QualityBreakdownResult, NaiveBaselineRun, ModelBaselineComparison,
         QualityEvaluationManifest                                      | FROZEN        | backend/app/forecast_quality/persistence.py           | backend/tests/forecast_quality/test_persistence.py     | yes               | yes                  | yes                | none         | alembic upgrade head + pytest round-trip + pytest concurrent
S3R-15 idempotent persistence (EXACT_REPLAY_ZERO_WRITE,
         CONFLICTING_REPLAY_REJECTED, PARTIAL_METRIC_PERSISTENCE_FORBIDDEN) | FROZEN | backend/app/forecast_quality/persistence.py           | backend/tests/forecast_quality/test_idempotency.py     | yes               | yes                  | yes                | none         | pytest replay same inputs → no second row; conflicting inputs → reject
S3R-16 Decimal + 1e-6 + ROUND_HALF_EVEN canonical payload emit          | FROZEN        | backend/app/forecast_quality/canonical.py             | backend/tests/forecast_quality/test_decimal.py         | yes               | no                   | no                 | none         | pytest canonical payload bytes match `str(Decimal(1e-6))`
S3R-17 P80 / P90 coverage gated on QUANTILE_SEMANTICS verification     | FROZEN        | backend/app/forecast_quality/quantile.py              | backend/tests/forecast_quality/test_quantile.py        | yes               | no                   | no                 | P80_P90_SEMANTICS_VERIFICATION | pytest coverage not published until semantic verified
S3R-18 head-to-head comparison over COMMON_COMPARABLE_SET              | FROZEN        | backend/app/forecast_quality/comparison.py            | backend/tests/forecast_quality/test_comparison.py      | yes               | no                   | no                 | none         | pytest deltas respect common vs model-only vs baseline-only
S3R-19 pinball loss absent (NOT a default S3 deliverable)              | FROZEN        | backend/app/forecast_quality/(none)                   | backend/tests/forecast_quality/(none)                  | n/a               | n/a                  | n/a                | none         | n/a (no implementation in this slice)
S3R-20 Slice Q2B / Q2C / Q2D / Q2E / Q2F governance dependencies untouched | FROZEN (boundary) | backend/app/forecast_quality/(none)               | backend/tests/forecast_quality/(none)                  | n/a               | n/a                  | n/a                | none         | n/a
```

## 3. Schema dependencies

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

## 4. Persistence governance

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

## 5. Real data and Issue #102

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

## 6. Open blockers

```text
P80_P90_SEMANTICS_VERIFICATION — open
  - P80_SEMANTICS=NOT_VERIFIED
  - P90_SEMANTICS=NOT_VERIFIED
  - Coverage metrics are gated on the semantic verification
  - Resolution requires a separate contract amendment or a separate
    evidence-collection round
```

No other requirements have open blockers. All `OPEN_BLOCKER` cells in the
matrix are `none` except `S3R-17` which is `P80_P90_SEMANTICS_VERIFICATION`.

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
