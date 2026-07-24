# V0.2-S3 Implementation Readiness Matrix

> Target: V0.2-S3 (FORECAST_QUALITY_METRICS_AND_ONE_NAIVE_BASELINE)
> Companion: `docs/forecast-quality/s3-quality-metrics-contract.md`
> Companion: `docs/forecast-quality/s3-naive-baseline-decision.md`
> Scope: per-requirement implementation readiness + owner path + acceptance test
> Base: `b873dd63fc0d5b6375f94674abbd24a94d915f3c`
> Source authority: `docs/forecast-quality/q2b-point-in-time-backtest-runner-contract.md` (S2 binding + manifest)

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

## 2. Open blockers — authoritative list

The matrix below records every open blocker that must be resolved before
any requirement is implementation-ready. The previously-claimed single
blocker `P80_P90_SEMANTICS_VERIFICATION` is no longer authoritative. The
current authoritative set of open blockers is:

```text
OB-01 S2_COMPLETE_DAILY_ROW_SET_AUTHORITY
  - S2 binding row set is sparse (t+7 / t+14 / t+21 target dates),
    not a continuous daily curve
  - S3 contract §2 freezes S3_COMPLETE_DAILY_ROW_SET_STATUS=
    NOT_AVAILABLE_FROM_CURRENT_S2_BINDING
  - Resolution: S2 contract amendment exposing a complete daily row set
    covering every calendar day in the evaluation window

OB-02 MAPE_COUNTER_SEMANTICS
  - S2 status counters and MAPE-specific counters must be separate
  - S3 contract §3 freezes mape_eligible_row_count and
    mape_zero_actual_row_count as metric-specific counters
  - Resolution: implementation must wire both counter families

OB-03 BASELINE_SEASON_ANALOG_MAPPING
  - Season day index mapping, leap-day policy, unequal season length,
    and season boundary policy must be defined
  - S3 contract §4 freezes
    SEASON_ANALOG_MAPPING_POLICY_VERSION=v0.2-s3-season-analog-mapping-v1
  - Resolution: implement deterministic_season_day_index and
    resolve_prior_season_analog_date per the frozen policy

OB-04 BASELINE_SOURCE_VISIBILITY_AUTHORITY
  - Prior-season actual label revision must be visible at or before
    current forecast_cutoff_at
  - The rejected phrasing "prior_season_forecast_cutoff = current forecast
    cutoff minus one season" is forbidden
  - Resolution: implement source-visibility semantics with
    baseline_source_snapshot_identity / baseline_source_visibility_manifest_hash

OB-05 BASELINE_SOURCE_SNAPSHOT_IDENTITY
  - The baseline must bind its own source snapshot identity, source
    snapshot hash, row set hash, visibility manifest hash, and
    visibility cutoff
  - S3 contract MUST NOT reuse the model S2 binding row set as the
    baseline historical source
  - Resolution: implement baseline source snapshot binding

OB-06 BASELINE_QUANTILE_DISTRIBUTION
  - The baseline is point-only; P80 / P90 are NOT_COMPUTABLE
  - S3 contract §15 freezes NAIVE_BASELINE_P80_STATUS=NOT_COMPUTABLE
  - Resolution: publish NOT_COMPUTABLE for p80 / p90 / interval deltas
    with reason_code=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED

OB-07 P50_P80_P90_SEMANTICS_VERIFICATION
  - P50 / P80 / P90 quantile semantics are not verified
  - Coverage, pinball loss, and interval width are gated on
    QUANTILE_SEMANTICS_VERIFICATION
  - Resolution: separate contract amendment or evidence-collection round

OB-08 PINBALL_UPSTREAM_CONTRACT_ALIGNMENT
  - S2 frozen contract preserves conditional pinball loss
  - S3 contract must preserve the conditional pinball loss
    (UPSTREAM_CONTRACT_AMENDMENT_ACCEPTED=false; PINBALL_LOSS_REMOVED_FROM_S3=false)
  - Resolution: implementation must publish pinball-loss-NOT_COMPUTABLE
    gated on the same quantile-semantics verification

OB-09 SUBFARM_TO_FARM_AGGREGATION_POLICY
  - Subfarm-to-farm aggregation must be explicit; max-single-subfarm
    must not become farm daily peak
  - S3 contract §11.4 freezes
    MAX_SINGLE_SUBFARM_ROW_AS_FARM_DAILY_PEAK=false
  - Resolution: implement FARM_DAILY_AGGREGATE_FORMULA = sum(subfarm_q_i,
    exact_deduped_actual_rows)

OB-10 CROSS_QUANTILE_ACTUAL_DEDUP_POLICY
  - One actual label per physical grain; P50 / P80 / P90 forecast rows
    join to the SAME actual identity
  - S3 contract §11.1 freezes ACTUAL_LABEL_COUNTED_ONCE_PER_PHYSICAL_GRAIN
  - Resolution: implement physical-grain-level actual dedup
```

## 3. Requirement matrix

```text
REQUIREMENT                                                             | DESIGN_STATUS | IMPLEMENTATION_OWNER_PATH                              | TEST_OWNER_PATH                                       | POSTGRES_REQUIRED | CONCURRENCY_REQUIRED | MIGRATION_REQUIRED | OPEN_BLOCKER | ACCEPTANCE_TEST
----------------------------------------------------------------------|---------------|-------------------------------------------------------|-------------------------------------------------------|-------------------|----------------------|--------------------|--------------|---------------
S3R-01 daily point-forecast metrics (daily_mae, daily_wape, daily_smape,
         daily_mape, daily_bias_kg, daily_relative_bias,
         daily_absolute_error_sum_kg)                                    | FROZEN        | backend/app/forecast_quality/calculator_daily.py       | backend/tests/forecast_quality/test_calculator_daily.py| yes               | no                   | no                 | OB-01        | pytest measure over 50+ hand-computed comparable rows
S3R-02 season cumulative metric set (forecast_kg, actual_kg,
         signed_error_kg, absolute_error_kg, signed_relative_error,
         absolute_relative_error)                                      | FROZEN        | backend/app/forecast_quality/calculator_cumulative.py  | backend/tests/forecast_quality/test_calculator_cumulative.py| yes          | no                   | no                 | OB-01        | pytest sum over hand-picked rows
S3R-03 denominator-zero policy (NOT_COMPUTABLE + reason_code)          | FROZEN        | backend/app/forecast_quality/calculator_daily.py       | backend/tests/forecast_quality/test_zero_policy.py     | yes               | no                   | no                 | none         | pytest zero-division negative tests
S3R-04 MAPE counter semantics (mape_eligible_row_count,
         mape_zero_actual_row_count, EXCLUDE_ZERO_ACTUAL)             | FROZEN        | backend/app/forecast_quality/calculator_daily.py       | backend/tests/forecast_quality/test_mape.py            | yes               | no                   | no                 | OB-02        | pytest zero-actual rows counted in mape_zero_actual_row_count
S3R-05 smape double-zero policy (ROW_CONTRIBUTES_ZERO)                  | FROZEN        | backend/app/forecast_quality/calculator_daily.py       | backend/tests/forecast_quality/test_smape.py           | yes               | no                   | no                 | none         | pytest double-zero rows contribute 0
S3R-06 single-day peak per quantile (P50, P80, P90) with earliest tie-break | FROZEN    | backend/app/forecast_quality/peak.py                  | backend/tests/forecast_quality/test_peak.py             | yes               | no                   | no                 | OB-01        | pytest tied dates select earliest
S3R-07 sustained 7-day peak with NO zero-fill missing days             | FROZEN        | backend/app/forecast_quality/peak.py                  | backend/tests/forecast_quality/test_peak_7day.py       | yes               | no                   | no                 | OB-01        | pytest incomplete windows rejected
S3R-08 single naive baseline (PRIOR_SEASON_ANALOG_DAY_ACTUAL, point)  | FROZEN        | backend/app/forecast_quality/baseline.py              | backend/tests/forecast_quality/test_baseline.py        | yes               | no                   | no                 | OB-03, OB-04, OB-05 | pytest prior-season analog-day actual against hand-computed
S3R-09 baseline cold-start (FAIL_CLOSED + NOT_COMPUTABLE)               | FROZEN        | backend/app/forecast_quality/baseline.py              | backend/tests/forecast_quality/test_baseline_cold.py   | yes               | no                   | no                 | OB-03        | pytest no prior season → NOT_COMPUTABLE
S3R-10 baseline visibility rule (visible at or before current
         forecast_cutoff_at), separate baseline source snapshot         | FROZEN        | backend/app/forecast_quality/baseline.py              | backend/tests/forecast_quality/test_baseline_visibility.py| yes          | no                   | no                 | OB-04, OB-05 | pytest prior-season future target dates not used
S3R-11 baseline prohibits post-cutoff / latest / model / receipt / zero | FROZEN        | backend/app/forecast_quality/baseline.py              | backend/tests/forecast_quality/test_baseline_red.py    | yes               | no                   | no                 | OB-04, OB-05 | pytest each prohibited source flagged
S3R-12 baseline point-only (P80/P90 NOT_COMPUTABLE)                    | FROZEN        | backend/app/forecast_quality/baseline.py              | backend/tests/forecast_quality/test_baseline_quantile.py| yes            | no                   | no                 | OB-06        | pytest p80 / p90 deltas → NOT_COMPUTABLE; status=BLOCKED
S3R-13 breakdown contract (horizon / farm / variety / season / model)   | FROZEN        | backend/app/forecast_quality/breakdown.py             | backend/tests/forecast_quality/test_breakdown.py       | yes               | no                   | no                 | OB-01        | pytest breakdown cells match the axes
S3R-14 INSUFFICIENT_SAMPLE below MIN_COMPARABLE_ROWS_FOR_REPORTING=10  | FROZEN        | backend/app/forecast_quality/breakdown.py             | backend/tests/forecast_quality/test_breakdown_min.py   | yes               | no                   | no                 | none         | pytest small-sample cells flagged, not dropped
S3R-15 cross-quantile actual-label dedup (one actual per physical grain;
         P50/P80/P90 forecast rows join to SAME actual)                  | FROZEN        | backend/app/forecast_quality/canonical.py             | backend/tests/forecast_quality/test_actual_dedup.py    | yes               | no                   | no                 | OB-10        | pytest single actual label per physical grain, reused across quantiles
S3R-16 subfarm-to-farm aggregation (sum of subfarm_q_i over exact
         deduped actual rows; max-single-subfarm is NOT farm peak)      | FROZEN        | backend/app/forecast_quality/aggregation.py           | backend/tests/forecast_quality/test_aggregation.py     | yes               | no                   | no                 | OB-09        | pytest farm-level peak equals sum of subfarm-level amounts
S3R-17 duplicate policy (forecast business key, actual physical key,
         target date after aggregation = STRUCTURAL_FAILURE)            | FROZEN        | backend/app/forecast_quality/canonical.py             | backend/tests/forecast_quality/test_dedup.py           | yes               | no                   | no                 | none         | pytest duplicate rejected with STRUCTURAL_FAILURE
S3R-18 canonical identity binding (s2_run, s2_manifest, row_set_hash,
         metric_policy_version, baseline_policy_version, breakdown;
         baseline_source_snapshot_identity, baseline_source_visibility_manifest_hash) | FROZEN | backend/app/forecast_quality/canonical.py | backend/tests/forecast_quality/test_canonical.py       | yes               | no                   | no                 | OB-05        | pytest canonical hash byte-identical across replay
S3R-19 persistence: QualityEvaluationRun, QualityMetricResult,
         QualityBreakdownResult, NaiveBaselineRun, ModelBaselineComparison,
         QualityEvaluationManifest                                      | FROZEN        | backend/app/forecast_quality/persistence.py           | backend/tests/forecast_quality/test_persistence.py     | yes               | yes                  | yes                | none         | alembic upgrade head + pytest round-trip + pytest concurrent
S3R-20 idempotent persistence (EXACT_REPLAY_ZERO_WRITE,
         CONFLICTING_REPLAY_REJECTED, PARTIAL_METRIC_PERSISTENCE_FORBIDDEN) | FROZEN | backend/app/forecast_quality/persistence.py           | backend/tests/forecast_quality/test_idempotency.py     | yes               | yes                  | yes                | none         | pytest replay same inputs → no second row; conflicting inputs → reject
S3R-21 Decimal + 1e-6 + ROUND_HALF_EVEN canonical payload emit;
         DECIMAL_ONLY_CANONICAL_ARITHMETIC=true; native float /
         numpy float / binary float NOT allowed at any intermediate
         step                                                            | FROZEN        | backend/app/forecast_quality/canonical.py             | backend/tests/forecast_quality/test_decimal.py         | yes               | no                   | no                 | none         | pytest canonical payload bytes match `str(Decimal(1e-6))`; no float intermediate
S3R-22 P50 / P80 / P90 coverage gated on QUANTILE_SEMANTICS_VERIFICATION | FROZEN        | backend/app/forecast_quality/quantile.py              | backend/tests/forecast_quality/test_quantile.py        | yes               | no                   | no                 | OB-07        | pytest coverage not published until semantic verified
S3R-23 pinball loss preserved (NOT_COMPUTABLE gated on
         QUANTILE_SEMANTICS_VERIFICATION;
         UPSTREAM_CONTRACT_AMENDMENT_ACCEPTED=false)                   | FROZEN        | backend/app/forecast_quality/quantile.py              | backend/tests/forecast_quality/test_pinball.py         | yes               | no                   | no                 | OB-07, OB-08 | pytest pinball loss NOT_COMPUTABLE until semantic verified
S3R-24 head-to-head comparison over COMMON_COMPARABLE_SET              | FROZEN        | backend/app/forecast_quality/comparison.py            | backend/tests/forecast_quality/test_comparison.py      | yes               | no                   | no                 | OB-06        | pytest deltas respect common vs model-only vs baseline-only
S3R-25 comparison delta semantics (loss_delta, signed_delta,
         absolute-bias-magnitude_delta)                                | FROZEN        | backend/app/forecast_quality/comparison.py            | backend/tests/forecast_quality/test_comparison_delta.py| yes              | no                   | no                 | none         | pytest loss_delta positive=worse; signed_delta direction only; magnitude_delta positive=worse
S3R-26 Slice Q2B / Q2C / Q2D / Q2E / Q2F governance dependencies untouched | FROZEN (boundary) | backend/app/forecast_quality/(none)               | backend/tests/forecast_quality/(none)                  | n/a               | n/a                  | n/a                | none         | n/a
```

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

## 9. Blockers-vs-requirement cross-reference

```text
OB-01 S2_COMPLETE_DAILY_ROW_SET_AUTHORITY
  - S3R-01 daily point-forecast metrics (depends on a complete daily row
    set for cumulative and peak computations)
  - S3R-02 season cumulative metric set
  - S3R-06 single-day peak per quantile
  - S3R-07 sustained 7-day peak
  - S3R-13 breakdown contract

OB-02 MAPE_COUNTER_SEMANTICS
  - S3R-04 MAPE counter semantics

OB-03 BASELINE_SEASON_ANALOG_MAPPING
  - S3R-08 single naive baseline
  - S3R-09 baseline cold-start

OB-04 BASELINE_SOURCE_VISIBILITY_AUTHORITY
  - S3R-08 single naive baseline
  - S3R-10 baseline visibility rule
  - S3R-11 baseline prohibits post-cutoff / latest / model / receipt / zero

OB-05 BASELINE_SOURCE_SNAPSHOT_IDENTITY
  - S3R-08 single naive baseline
  - S3R-10 baseline visibility rule
  - S3R-11 baseline prohibits post-cutoff / latest / model / receipt / zero
  - S3R-18 canonical identity binding

OB-06 BASELINE_QUANTILE_DISTRIBUTION
  - S3R-12 baseline point-only
  - S3R-24 head-to-head comparison

OB-07 P50_P80_P90_SEMANTICS_VERIFICATION
  - S3R-22 P50 / P80 / P90 coverage
  - S3R-23 pinball loss

OB-08 PINBALL_UPSTREAM_CONTRACT_ALIGNMENT
  - S3R-23 pinball loss

OB-09 SUBFARM_TO_FARM_AGGREGATION_POLICY
  - S3R-16 subfarm-to-farm aggregation

OB-10 CROSS_QUANTILE_ACTUAL_DEDUP_POLICY
  - S3R-15 cross-quantile actual-label dedup
```
