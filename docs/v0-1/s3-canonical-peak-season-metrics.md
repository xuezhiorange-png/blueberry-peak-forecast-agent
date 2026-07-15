# V0.1-S3 Canonical Peak and Season Metrics

## Boundary

S3 is a pure, synchronous, deterministic, read-only projection over a
completed S2 `CompleteDailyMarketableCurveResult`. It does not open a
database session, perform network I/O, read a clock, use randomness, persist
metrics, or modify upstream authorities. The production entry point is
`backend.app.core_forecast.metrics.compute_core_forecast_metrics`.

The only metric quantity authority is each S2 row's
`effective_marketable_quantity_kg`. The only date authority is the row's
`date`, whose semantic basis is `HARVEST_BUSINESS_DATE`. Arrival, receipt,
actual-harvest, maturity-supply, and model-harvested quantities are not S3
metric inputs.

## Canonicalization and validation

`backend.app.core_forecast.canonical.compute_daily_curve_hash` centralizes
the S2 curve hash preimage without changing the S2 schema version or row
payload. It uses the repository `canonical_json_dumps`, UTF-8, and lowercase
SHA-256. S3 independently verifies every row hash and the source curve hash
before aggregation. Its metrics hash uses this preimage, in fixed P50/P80/P90
order:

```json
{
  "schema_version": "v0.1-core-forecast-metrics-v1",
  "date_basis": "HARVEST_BUSINESS_DATE",
  "source_curve_hash": "<verified S2 curve hash>",
  "metrics": ["<P50>", "<P80>", "<P90>"]
}
```

All metric quantities are fixed six-place decimal strings matching
`^(?:0|[1-9]\\d*)\\.\\d{6}$`. Calculation uses `Decimal`, quantization
`Decimal("0.000001")`, and `ROUND_HALF_EVEN`; native floats, booleans,
non-finite values, negative zero, scientific notation, and negative values
are rejected.

## Aggregation and metrics

Rows are aggregated independently at `date x forecast_quantile` across all
farm, subfarm, and variety scopes. No retention rate or marketable rate is
applied again.

The single-day peak is the maximum daily effective-marketable total. Equal
maxima select the earliest date (`EARLIEST_DATE`). The sustained peak is the
maximum sum over a strict seven-calendar-day rolling window:

```text
window_days=7
metric=ROLLING_CUMULATIVE
date_continuity=STRICT_CALENDAR_DAYS
tie_break=EARLIEST_START_DATE
```

Only complete seven-day windows participate. Equal cumulative windows select
the earliest start date. The seven-day average is display-only and is derived
after selection as `cumulative / Decimal("7")`, quantized to six places with
`ROUND_HALF_EVEN`; it never selects the window. Season cumulative is the sum
of every daily effective-marketable total across the complete input range,
including zero, loss, capacity-dip, backlog-release, and tail dates.

## Fail-closed behavior

S3 returns either all three quantile metrics or a blocked result with no
partial metrics. The result schema enforces this XOR. Invalid status, rows,
row hashes, curve hash, business keys, scope/date/quantile completeness,
calendar continuity, or Decimal values produce deterministic blockers such
as `DAILY_CURVE_ROW_HASH_MISMATCH`, `DAILY_CURVE_HASH_MISMATCH`,
`DAILY_CURVE_DECIMAL_INVALID`, `DAILY_CURVE_DUPLICATE_KEY`,
`DAILY_CURVE_INCOMPLETE_SERIES`, and `NO_COMPLETE_7DAY_WINDOW`.

Expected validation, Decimal, quantization, and schema errors are mapped at
the composition boundary. No broad exception handler hides programming
defects, and no malformed input can yield partial quantile output.

## Fixture evidence and compatibility

`backend/tests/core_forecast/test_metrics.py` builds typed S2 rows from the
unchanged complete-season fixture and calls the production metrics function.
It compares all accepted output fields against `expected_metrics.json` without
copying expected values into production code. The fixture has 1,080 rows,
12 complete series, and 90 daily totals for each of P50, P80, and P90. S3
does not modify the fixture or its expected metrics checksum.

The legacy Agent peak adapter, its `sustained_3day_peak`, ±7-day context,
high-load fields, and legacy hashes remain untouched. S3 does not call the
legacy adapter and does not rename or reinterpret its three-day contract.

## Exclusions

S3 does not implement S4 run persistence, metrics storage, query/retrieval,
recalculation lineage, migration, S5 unified entry, Agent orchestration, API,
CLI, full-season commands, PostgreSQL end-to-end execution, actual-harvest
import, CSV/XLSX parsing, Q2A-I3+, backtesting, actual labels, multi-factory
routing, capacity balancing, peak shaving, high-load thresholds, peak
duration, dominant variety, frontend, dashboard, or reports.

```text
V0_1_S4_NOT_AUTHORIZED
V0_1_S5_NOT_AUTHORIZED
READY_NOT_AUTHORIZED
MERGE_NOT_AUTHORIZED
```
