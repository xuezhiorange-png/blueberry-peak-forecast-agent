# Area forecast immutable runs and history — P1

TASK_ID=NEXT_VERSION_AREA_FORECAST_RUN_PERSISTENCE_AND_HISTORY_P1

Base main: `f4f2bf03eff802a0c9259bd4bd2d9d12b7dcbf72`. This is an explicit persistence boundary for `AREA_YIELD_B1_V1`, not a forecast-method change. No research, refit, weather, future-plan input, Global fallback, MCP history tools, UI or deployment is included.

## Existing patterns reused

- EXISTING_PERSISTENCE_PATTERN_REUSED: [Core repository](../../backend/app/core_forecast/persistence.py) completed immutable runs, canonical reload, execution identity, lineage and normalized children; separate area tables retain the distinct product contract.
- EXISTING_TRANSACTION_PATTERN_REUSED: [Core application](../../backend/app/core_forecast/application.py) caller-owned transaction. The new repository only adds, flushes and reloads inside a savepoint. HTTP/CLI own commit/rollback; a child-write or canonical-reload failure rolls back the complete savepoint.
- EXISTING_CANONICAL_HASH_PATTERN_REUSED: [area canonical digest](../../backend/app/area_yield/data.py) and the unchanged product result hash. No parallel forecast computation was introduced.

The actual previous Alembic head was `0033_empirical_maturity_authority`. The new migration is [0034_area_forecast_runs](../../backend/alembic/versions/0034_area_forecast_runs.py). Existing tests asserting the current head advance to 0034; historical migration-specific tests and historical evidence are not rewritten.

## Execution and immutability

[execute_area_forecast_run](../../backend/app/area_yield/run_application.py) loads and validates authority once, hashes the request and uses that same in-memory snapshot through the existing product service. The execution hash includes `AREA_RUN_EXECUTION_V1`, product policy, canonical request snapshot and authority payload hash. There is no second authority load between identity and prediction.

`request_hash` is the unique execution identity. `result_hash` is the unchanged product output identity, indexed but deliberately **not unique**: alias-equivalent requests can have different request snapshots and the same result. Same execution returns the existing run; a conflicting snapshot fails closed. A changed request or authority may create a new run with `rerun_of_run_id`; unchanged identity reuses the old run even when rerun is requested.

Tables are `area_forecast_run` and `area_forecast_daily_row`. Child rows have zero-based contiguous indices, unique run/date and run/index, and nonnegative quantities/shares. Parent metadata stores peaks, mass balance, source hashes and the rest of the public result **without daily rows**. Typed parent fields support filtering and summaries. Exact numeric shares also retain their original canonical string in `share_text`, preserving existing product serialization rather than rounding or redefining its hash. SQLite uses lossless decimal text; PostgreSQL uses NUMERIC.

Database triggers reject UPDATE/DELETE and out-of-calendar child inserts. There is no public update/delete operation. Migration downgrade is allowed on empty area tables, but refuses populated history with `AREA_RUN_DATA_PREVENTS_DOWNGRADE`. This is a safeguard, not a history-deletion workflow.

Every get/daily/history operation rebuilds and verifies saved child rows: count, indices, dates, range, exact quantities, shares, total, mass balance, peaks, parent fields, source hashes, execution identity and product hash. It does not load current authority or rerun a model. Missing/tampered rows or malformed snapshots produce `AREA_FORECAST_PERSISTENCE_INTEGRITY_FAILED`; identity conflict produces `AREA_FORECAST_PERSISTENCE_CONFLICT`. Product request/history errors remain distinct from authority unavailable and database write failures. Responses do not expose private paths or raw authority.

## Explicit interfaces

| Operation | HTTP | Existing CLI framework |
| --- | --- | --- |
| Create/reuse | POST `/api/v1/area-forecast-runs` | `area-forecast-run create --input request.json` |
| Read full run | GET `/api/v1/area-forecast-runs/{run_id}` | `area-forecast-run get --run-id 1` |
| History | GET `/api/v1/area-forecast-runs` | `area-forecast-run list --farm "保山杨柳农场"` |
| Daily rows | GET `/api/v1/area-forecast-runs/{run_id}/daily` | `area-forecast-run daily --run-id 1` |

Invoke the CLI as `python -m backend.app.cli` followed by the listed subcommand. Create accepts the existing area request plus optional `rerun_of_run_id`, never authority/model/yield overrides. HTTP reuses server-owned Trial actor create/read permissions; no new permission platform or tenant model is introduced. Normal database configuration is required. Only create needs the existing hash-pinned authority environment; reads do not.

History filters are `canonical_farm`, `target_season`, `forecast_policy_version`. Limit defaults to 20 and is capped at 100. Ordering is `created_at DESC, id DESC`; opaque keyset cursors continue it deterministically. List items are summaries, not 207-row payloads (integrity is still checked before returning them). Daily rows are ascending by date. CLI wraps its daily output in `daily_forecast`; HTTP returns the typed list.

The existing stateless HTTP forecast, CLI `area-forecast`, Python `forecast_area_product`, and MCP `forecast_blueberry_by_area` remain side-effect-free. MCP create/get/history tools and Doubao registration require a separate task.

## Real Yangliu acceptance

Normal application HTTP with a server-configured nonproduction actor and PostgreSQL was used, without dependency overrides. An isolated local acceptance database retains run **1**. It is not a production deployment.

Request: 保山杨柳农场, 393.4 mu, target 2026-2027, 2026-10-15 through 2027-05-09, as-of 2026-09-12.

- Yield: `1232.338729` kg/mu; total: `484802.055989` kg; children: **207**.
- Product result hash: `6d406e8a4a436b2c9bf347dca5f52b3f9b048ea4fb1602405225fc4f2ac39d1b` (unchanged).
- Execution hash: `1523fdbcd9f5ff702ff5462acc6baeca15f7987bc9cfa9924c811fd6989c0b89`.
- Second identical POST returned run 1 with `reused_existing_run=true`, still 207 children.
- Fresh-session HTTP get/daily and fresh-process CLI get matched the saved product after removing the current authority path from the calling environment.
- Daily sum `484802.055987`, difference `-0.000002`, tolerance `0.000103984802055989`: PASS.

Controlled artifacts remain outside Git under `blueberry-area-yield-artifacts/run-persistence-p1/`: `request.json`, `saved-run.json`, `yangliu-persistence-parity.json`. Parity evidence SHA256: `73bc7c80596898fc4f6dbd5c1d868b147e9bddc8b09ee9106a50d6721de1b0a4`. No raw XLS, authority payload, credentials or model artifact is committed.

## Verification and review boundary

Tests cover SQLite roundtrip/corruption/conflict/atomicity, PostgreSQL roundtrip/concurrent reuse/immutability, empty migration downgrade-upgrade and populated downgrade refusal, request-authority pinning, lineage, filtered cursor history, authority-independent reads, stateless transport parity and existing forecast/Agent/CLI/MCP regressions. Full Alembic base-to-head and last-revision downgrade/upgrade were run against isolated PostgreSQL databases before saving acceptance history.

Local command and exact results are in the [evidence](evidence/area-forecast-run-persistence-p1.json). GitHub remains the final exact-head verification, including full-suite-canary; its terminal run is recorded on the PR, never substituted with an earlier PR's CI. No full-suite result is claimed from local targeted regressions.

READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
RELEASE_AUTHORIZED=false
FINAL_STOP_GATE=COORDINATOR_AREA_FORECAST_RUN_PERSISTENCE_AND_HISTORY_P1_REVIEW
