# Area forecast persisted-run MCP tools — P1

TASK_ID=NEXT_VERSION_AREA_FORECAST_PERSISTED_RUN_MCP_TOOLS_P1

Base main: `c44628a0f935d90eb485d52a68e95d2a5f4caf3d` (merged #619). This adds four operation adapters to the existing `blueberry-area-forecast` stdio server. `AREA_YIELD_B1_V1`, persistence/schema/migration, legacy HTTP/CLI and the original stateless tool's input/output/error/result-hash contract are unchanged.

## Reused architecture

[Existing MCP server](../../backend/app/mcp/area_forecast.py) still owns SDK discovery, stdio lifecycle and the structured-content/JSON-text envelope. [Persisted adapters](../../backend/app/mcp/persisted_runs.py) validate transport input and call [execute_area_forecast_run](../../backend/app/area_yield/run_application.py) or [AreaForecastRunRepository](../../backend/app/area_yield/run_persistence.py). They do not calculate forecasts, execution/result hashes, lineage scope, pagination, or reload integrity.

The normal `backend.app.db.session.AsyncSessionMaker` is initialized once through repository settings. It creates independent sessions per call, not engines per tool. Connections are acquired only by persisted operations. Each call owns its transaction; create returns only after successful commit. Repository savepoint/flush behavior is unchanged. No migration is run by the server. No extra DB URL, authority path/hash or model selectors are accepted from callers.

## Five-tool contract

| Tool | Input | Output | Read-only |
| --- | --- | --- | --- |
| `forecast_blueberry_by_area` | Existing six-field product input | Existing `AreaDrivenForecastResult` | true |
| `create_blueberry_area_forecast_run` | `CreateAreaForecastRun`, fixed method discriminator hidden | `SavedAreaForecastRun` | false |
| `get_blueberry_area_forecast_run` | Positive integer `run_id` | `SavedAreaForecastRun` | true |
| `list_blueberry_area_forecast_runs` | Optional canonical farm, target season, policy, limit, cursor | `AreaRunHistory` summaries | true |
| `get_blueberry_area_forecast_daily` | Positive integer `run_id` | `{run_id, daily_forecast: DailyAreaForecast[]}` | true |

All five tools declare destructive=false, idempotent=true, open-world=false. Create is explicitly a write, never read-only. Its idempotency means the same request/policy/authority execution reuses a saved run. History reflects the database snapshot at call time. Discovery declares each tool's input/output schema and annotations; the original stateless schema hash remains `5d0054933e148a95bf33c5d4f3a4029f3ea00267dee62c445b666b5d776b3d93`. New four-tool combined schema/annotation hash: `9370ffdb47c00345c73a45ae980d11a5cfc5e6b504dda0615fa7e641e73abfef` (sorted compact JSON, pinned in tests).

Create requires farm, Decimal-string productive area and target season. Optional fields are season_start, season_end, as_of and rerun_of_run_id. Product validation and the immediate-prior/no-Global-fallback policy remain authoritative. Explicit rerun parent validation happens before idempotent reuse and requires the same canonical farm, target season and resolved window. Area/as-of/authority changes remain allowed only within that scope.

History forwards filters and cursor unchanged to the repository: default limit 20, max 100, `created_at DESC, id DESC`, opaque keyset pagination. It does not include daily rows. Daily output is ascending by date and passes the repository's full canonical integrity gate. No historical operation loads authority or recomputes a forecast.

## Errors

All tool execution failures use the existing MCP `isError=true` and `{status: "error", code, reason}` structured/text envelope. No raw exception, SQL, credentials, filesystem path or authority payload is exposed.

- Product request and unsupported history preserve `AREA_FORECAST_REQUEST_INVALID` / `AREA_FORECAST_UNSUPPORTED_FARM_HISTORY` and their sanitized reasons.
- Authority failure remains `AREA_FORECAST_AUTHORITY_UNAVAILABLE`, affecting forecast/create only.
- Persisted typed errors preserve `AREA_FORECAST_RUN_NOT_FOUND`, `AREA_FORECAST_PERSISTENCE_CONFLICT`, `AREA_FORECAST_RERUN_SCOPE_MISMATCH`, `AREA_FORECAST_PERSISTENCE_INTEGRITY_FAILED`, `AREA_FORECAST_WRITE_FAILURE`. Persisted errors use their code as the sanitized reason, matching the existing CLI vocabulary.
- Database/connection/commit or unexpected saved-operation infrastructure failures use `AREA_FORECAST_WRITE_FAILURE` with `PERSISTENCE_SERVICE_UNAVAILABLE`, including reads. The historical name is retained rather than globally redesigning errors. They are not authority errors.

## Operator launch and handoff

```bash
python -m backend.app.mcp.area_forecast
```

Keep the existing pinned MCP SDK/runtime. The trusted local host configures standard `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` through the existing settings mechanism. The operator applies existing migration head `0034_area_forecast_runs` beforehand. Configure `AREA_YIELD_AUTHORITY_PATH` and `AREA_YIELD_AUTHORITY_SHA256` only for forecast/create; history remains usable without them. Never place these values in tool inputs or public documentation/artifacts. Stdout remains MCP protocol, not application logging.

Stdio trust is the local host/process/OS boundary; these tools do not introduce remote authentication or expose a public endpoint. The local host can discover five tools and distinguish preview (stateless) from explicit saving (create). This is not evidence of Doubao registration or an assertion about Doubao's supported transport/configuration fields. No HTTP/SSE MCP, OAuth, UI, credentials acquisition or online registration was performed.

Example create arguments (the same product request as accepted previously):

```json
{"farm":"保山杨柳农场","productive_area_mu":"393.4","target_season":"2026-2027","season_start":"2026-10-15","season_end":"2027-05-09","as_of":"2026-09-12"}
```

Get/daily use `{"run_id":1}`; list may use `{"canonical_farm":"保山杨柳农场","limit":20}`. Returned cursors are forwarded verbatim. There are no update/delete tools.

## Actual acceptance

Actual SDK stdio processes, normal configured PostgreSQL sessions and a nonproduction HTTP actor were used with the accepted private Yangliu authority. No dependency override was used for real acceptance. Run **1** was created in an isolated local acceptance database, not production.

- Total `484802.055989` kg; 207 daily rows.
- Product result hash `6d406e8a4a436b2c9bf347dca5f52b3f9b048ea4fb1602405225fc4f2ac39d1b`.
- Execution hash `1523fdbcd9f5ff702ff5462acc6baeca15f7987bc9cfa9924c811fd6989c0b89`.
- Repeated MCP, HTTP and CLI create reused the same run; parent count 1, child count 207.
- After authority configuration was removed, a fresh stdio process get/daily/list matched HTTP and fresh CLI process output. List did not include daily payload.
- Stateless MCP/Python/HTTP/CLI results matched; stateless MCP did not increase run count.

Private artifacts remain under `blueberry-area-yield-artifacts/mcp-persisted-runs-p1/`: parity.json (`cd1210ee2eda6da1bbb2a83c163bada99df5ef0ecbd9b1485900ccc08d1fcc53`), saved-run.json, schemas.json. Only aggregate results and hashes are public. Prior evidence/authority/model artifacts are unchanged.

Tests also exercise two concurrent creates through one actual stdio client against PostgreSQL: same run ID, one original, one reuse and 207 rows. Disposable synthetic DBs are isolated from acceptance history. SQLite fixture corruption checks missing/modified children, bad parent hash and cross-scope lineage through both MCP read tools. Transport tests check matching history filters/cursors, error redaction, and outer transaction rollback.

Local and exact-head verification are recorded in the [evidence](evidence/area-forecast-persisted-mcp-tools-p1.json) and PR final CI comment. Required full-suite-canary is not skipped or replaced by local tests.

MCP_LOCAL_INTEGRATION_SURFACE_COMPLETE=true
DOUBAO_RUNTIME_REGISTRATION=NOT_EXECUTED
DOUBAO_WORK_ASSISTANT_READY=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
RELEASE_AUTHORIZED=false
FINAL_STOP_GATE=COORDINATOR_AREA_FORECAST_PERSISTED_RUN_MCP_TOOLS_P1_REVIEW
