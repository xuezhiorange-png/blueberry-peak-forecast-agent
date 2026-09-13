# Area forecast rerun scope — review fix R1

TASK_ID=NEXT_VERSION_AREA_FORECAST_RUN_PERSISTENCE_AND_HISTORY_P1_REVIEW_FIX_R1

PR #619, previous head `dd8cd8be7d3f2b54453685607149c5e2f8b0204f`.

The previous application accepted an arbitrary existing parent, and its idempotent early return skipped parent validation entirely. Seven new regression cases failed against that implementation, including unrelated-parent reuse and tampered-lineage reload.

## Frozen contract

The [shared scope predicate](../../backend/app/area_yield/run_schemas.py) compares exactly `canonical_farm`, `target_season`, `season_start`, `season_end`. Area, as-of and authority may change. Identity uses only the existing validated authority alias map; omitted dates resolve with the existing product season calendar. No fuzzy matching, fallback or extra forecast invocation is introduced.

The [application](../../backend/app/area_yield/run_application.py) loads authority once, reads and canonically verifies any explicit parent, checks scope, then allows idempotent reuse or a single forecast/save. Mismatch raises `AREA_FORECAST_RERUN_SCOPE_MISMATCH`, a persistence conflict returned as HTTP 409 and the same machine-readable CLI code. Missing parents and corrupt parents also fail before reuse. Existing HTTP/CLI exception handling is reused without changing those transports.

The [reload gate](../../backend/app/area_yield/run_persistence.py) verifies the persisted parent and the same scope predicate, in addition to the existing parent existence/earlier-ID constraints. A tampered cross-scope pointer produces `AREA_FORECAST_PERSISTENCE_INTEGRITY_FAILED`. Reads use only saved state, never current authority or a new forecast.

## Verification

Tests cover different farms, target seasons, either window bound, unrelated parent with an already-existing execution, absent/corrupt parents, authorized aliases, default-versus-explicit resolved windows, as-of changes, tampered pointers and HTTP/CLI 409 parity. Existing tests retain allowed area/authority changes and identical valid-parent reuse. PostgreSQL additionally verifies rejected unrelated-parent reuse followed by valid area-change persistence and fresh-session lineage reload.

Real Yangliu acceptance used normal HTTP/application/actor configuration without dependency overrides in a new isolated local PostgreSQL database. Run 1 was created and then reused both without a parent and with itself as valid parent. Saved total remains `484802.055989`, 207 children, product hash `6d406e8a4a436b2c9bf347dca5f52b3f9b048ea4fb1602405225fc4f2ac39d1b`. Authority-independent get/daily readback passed. This is not a production deployment.

Private evidence: `blueberry-area-yield-artifacts/run-persistence-p1/yangliu-scope-fix-parity.json`, SHA256 `20d23ae51a9770f10e877e92a954c1534bd2457ff6cffd0c40b7c7191e031edf`. Prior acceptance evidence is preserved. [Review evidence](evidence/area-forecast-rerun-scope-fix-r1.json) records local validation; the PR final verification comment records the new exact-head CI and full-suite-canary, not the preceding run.

Forecast mathematics, policy `AREA_YIELD_B1_V1`, migration `0034_area_forecast_runs`, model/schema, legacy stateless HTTP/CLI and MCP are unchanged. No new model work or integration phase is authorized.

READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
RELEASE_AUTHORIZED=false
FINAL_STOP_GATE=COORDINATOR_AREA_FORECAST_RUN_PERSISTENCE_AND_HISTORY_P1_FIX_REVIEW
