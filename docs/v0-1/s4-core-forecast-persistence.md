# V0.1-S4 Core Forecast Persistence

V0.1-S4 persists a completed composition of the S2 daily marketable curve and
the S3 canonical peak and season metrics. It is an immutable, read-only query
boundary; it does not add an API, CLI, Agent integration, or a new forecasting
algorithm.

## Architecture Boundary

The application service calls the existing authorities in this order:

1. `compose_complete_daily_marketable_curve()` produces the complete S2 curve.
2. `compute_core_forecast_metrics()` produces the S3 metrics.
3. `CoreForecastRunRepository` stores the completed curve and the three
   quantile metric rows in one caller-owned transaction.

The only persisted daily quantity authority is
`effective_marketable_quantity_kg`, and the date basis is
`HARVEST_BUSINESS_DATE`. S4 does not recalculate Task 8 or Task 9 state and
does not use the legacy Agent peak adapter.

## Three Tables

`core_forecast_run` stores the completed request, lineage, canonical hashes,
counts, and optional `rerun_of_run_id`. `core_forecast_daily_row` stores every
formal S2 row. `core_forecast_metric` stores exactly one P50, P80, and P90 row
for each run. All parent-child foreign keys are `ON DELETE RESTRICT`; update
and delete repository methods are intentionally absent.

The migration creates the run table first, then daily rows, then metrics. The
downgrade removes metrics, daily rows, and the run in reverse order. The S4
migration is `0017_core_forecast_run_persistence` over the verified
`0016_task9_forecast_season_identity` head. The unmerged actual-harvest
migration is not copied or modified.

## Canonical Hashes

The retention-policy snapshot is sorted by season, farm, subfarm, and variety
identity and includes every policy field. The forecast input hash includes the
canonical request scope and policy snapshot. The request hash adds the optional
rerun parent identity. The result hash includes only schema/version, request
and input identity, S2 curve hash, S3 metrics hash, and row counts; database
IDs and timestamps are excluded.

S2 curve and S3 metrics hash preimages are unchanged. S4 stores and rechecks
both hashes rather than replacing their semantics.

## Completed-Only Persistence

Blocked S2 or S3 execution returns no run, no curve, and no metrics and writes
zero S4 rows. A save uses a nested savepoint but never commits, rolls back, or
closes the caller-owned session. The caller owns the outer transaction.

The parent and all daily and metric children are flushed in one savepoint. A
child failure cannot leave a completed parent or partial children. A duplicate
request hash is reused only after full canonical reload and parity checking;
the hash alone is never trusted.

## Rerun Rules

Reruns require a complete new curve request and complete new retention-policy
snapshot. S4 does not support `latest`, `current`, implicit authority lookup,
or partial policy overrides. The parent scope, season, date range, and factory
must remain identical. Task 8/Task 9 identities and policy values may change.
An unchanged forecast input is blocked, and a successful rerun stores the
immutable parent relation without modifying the parent run.

## Load Integrity Gate

Loading a run reconstructs the request and policy through Pydantic, recomputes
all request hashes, revalidates every daily row, checks business-key and
calendar completeness, rechecks state equations and cross-day continuity,
recomputes the retention formula, recomputes the S2 curve hash, recomputes S3
metrics, compares all persisted metric fields, and finally recomputes the S4
result hash. Any mismatch raises a deterministic persistence integrity error;
partial results are not returned.

## S1-S3 Preservation and S5 Exclusions

The complete-season fixture and its checksums remain authoritative. S4 does
not change S1 fixture data, S2 row/hash behavior, or S3 metric/hash behavior.
S5 unified entry, API, CLI, Agent orchestration, full-season command, and
production end-to-end workflow remain outside this slice and require separate
authorization.
