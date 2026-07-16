# V0.1-S5 Core Forecast CLI and Full-Season Acceptance

## Boundary

S5 is a thin unified-entry adapter over the completed S2, S3, and S4
application boundaries. It does not implement a second curve algorithm,
metric algorithm, persistence model, migration, API, or Agent integration.

The command is:

    uv run python -m backend.app.cli core-forecast \
      --fixture backend/tests/fixtures/v0_1_complete_season_case_01/input.json

The adapter strictly validates the complete-season fixture, creates the
frozen S4 request and retention-policy snapshot, and calls the existing
execute_core_forecast_run application service. The database session and
outer transaction remain owned by the CLI/application boundary; the S4
repository only flushes and reloads canonical state.

## Execution and output

The production sequence is:

1. Load and strictly validate the complete 90-day fixture.
2. Resolve the explicit Task 8 and Task 9 authority identities.
3. Compose the S2 effective_marketable_quantity_kg curve.
4. Compute S3 single-day, rolling cumulative seven-day, and season metrics.
5. Persist the completed S4 run, 1,080 daily rows, and three metrics.
6. Reload the run through the S4 integrity gate.
7. Emit a stable JSON summary.

The summary contains the run ID, request/result/curve/metrics hashes, date
range, row and metric counts, and P50/P80/P90 metric values. Timestamps,
credentials, connection strings, and environment snapshots are not emitted.
The --output-json option writes the same canonical JSON that is printed to
stdout.

## Idempotency and rerun

Repeating the same complete request uses S4 request-hash idempotency and
returns the existing physical run. --rerun-of requires the same complete
season scope/date/factory and a complete changed input, such as a changed
retention policy. The parent is immutable and the child stores
rerun_of_run_id; unchanged reruns are blocked.

Blocked S2/S3 execution returns a non-zero CLI exit code and does not call
S4 persistence. No run, daily row, or metric fragment is written.

## Acceptance evidence

The canonical fixture has 90 dates, four scopes, three quantiles, and exactly
1,080 daily rows. The PostgreSQL E2E uses the existing production Task 8/Task
9 authority seed, then proves first execution, reload parity, idempotent
reuse, explicit rerun lineage, and blocked zero-write behavior. Frozen S2 and
S3 curve/metrics hashes are compared without changing the fixture.

## Exclusions

S5 does not add or change Alembic migrations, ORM tables, S2/S3 mathematics,
S4 persistence semantics, API endpoints, CLI frameworks, frontends, actual
harvest imports, routing, backtesting, or recommendation logic. V0.1-S5 does
not authorize Ready, Merge, auto-merge, cleanup, or post-V0.1 work.
