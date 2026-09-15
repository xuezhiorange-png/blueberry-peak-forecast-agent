# V0.5-S6 operational peak product path

S6 exposes the frozen `OPERATIONAL_PEAK_POLICY_V1` as a versioned application
path. It does not retrain or refit the S5 baseline. The domain function remains
the single owner of forecast math; REST, CLI, and MCP are transport adapters.

## Frozen authority boundary

The application loads one server-owned `OPERATIONAL_PEAK_AUTHORITY_V1` snapshot
per create execution. The configured file is checked against
`OPERATIONAL_PEAK_AUTHORITY_SHA256`, then its canonical `authority_hash`, base
registry payload hash, registry file hash, reference-profile fold/hash, policy,
baseline, and `weather_used=false` are checked before prediction.

Callers cannot provide registry/profile payloads, model paths, authority paths,
authority hashes, or policy overrides. Authority failures are fail-closed and do
not write a run.

The operator configures only:

```text
OPERATIONAL_PEAK_AUTHORITY_PATH=/private/operator/path/operational_peak_authority_v1.json
OPERATIONAL_PEAK_AUTHORITY_SHA256=<sha256-of-the-file>
```

The approved development snapshot used for the Yangliu acceptance was checked
as follows:

```text
authority file SHA256: 49dbacd7c3dba8c520b48dbd81019a728b8efccaa9579837f7a03b28b0ff04b6
authority canonical hash: 1ec9d27375915b37d0e1a9d77bcc315cddd8eff54f7f0b7bf923053dad0d5917
```

These values identify the private operator artifact; the registry and reference
profile payloads are not committed to the repository.

## Application and persistence

`execute_operational_peak_forecast_run` owns the create boundary:

1. load and validate one authority snapshot;
2. build the request-plus-authority execution identity;
3. validate an optional rerun parent within the same base/season/origin scope;
4. return an existing completed run for the same execution identity, or call the
   frozen S5 function;
5. persist one immutable parent and normalized daily child rows;
6. reload through the canonical integrity gate before returning.

The repository flushes only. The API, CLI, or MCP application boundary owns the
transaction. Historical reads use persisted state and never reforecast, so they
remain available if the current authority file changes or is unavailable.

S6 uses the independent `operational_peak_forecast_run` and
`operational_peak_forecast_daily` tables, migration `0035_operational_peak_forecast_runs`.
Execution identity is unique. Daily rows are unique by run/index and run/date;
the parent and child tables are immutable.

## Interfaces

REST:

```text
POST /api/v1/operational-peak-forecast-runs
GET  /api/v1/operational-peak-forecast-runs/{run_id}
GET  /api/v1/operational-peak-forecast-runs
GET  /api/v1/operational-peak-forecast-runs/{run_id}/daily
```

CLI (existing CLI framework):

```text
python -m backend.app.cli operational-peak-run create --input request.json
python -m backend.app.cli operational-peak-run get --run-id <id>
python -m backend.app.cli operational-peak-run list
python -m backend.app.cli operational-peak-run daily --run-id <id>
```

The existing `area-forecast` CLI, stateless area API, and existing MCP tools are
unchanged. S6's four persisted-run tools are added to the same MCP server and
share the application/repository implementation; MCP does not duplicate peak,
window, hash, or authority logic.

## Acceptance snapshot

For `base_a96b297b126a8cab67c4755f`, `2026-2027`, origin `2027-03-31`, the
frozen S5 result remains:

```text
productive_area_mu: 394.000000
forecast_7d.total_kg: 25113.209490
forecast_15d.total_kg: 58748.531480
result_hash: 20ee0152fbcce9ab84daa0aa24aef9a532d3c5bc2fe47c28b72bdfea56f4f138
```

Repeated create calls with the same request and authority return the same run
and do not add child rows. This is an engineering integration acceptance, not a
claim of universal model accuracy or production authorization.
