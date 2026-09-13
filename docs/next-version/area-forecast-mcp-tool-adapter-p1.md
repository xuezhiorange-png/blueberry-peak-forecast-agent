# Area forecast MCP tool adapter P1

TASK_ID=NEXT_VERSION_AREA_FORECAST_MCP_TOOL_ADAPTER_P1

Base main: `6432b21e29182c726e9bc26484f5daeb78983a2c` (merged #617).
Policy remains `AREA_YIELD_B1_V1`: immediate same-farm prior yield × requested
area × frozen Global Ridge shape. This is a transport adapter, not model research.

## Infrastructure audit and implementation

The inspected main had no MCP server, MCP transport, discovery contract, or
Doubao/Feishu adapter. `backend/app/agent/enums.py` has a legacy internal logical
tool enum, not an MCP registry; it remains unchanged.

The only new runtime boundary is `backend.app.mcp.area_forecast`: one tool,
`forecast_blueberry_by_area`, on server `blueberry-area-forecast` version `1.0.0`.
It uses the pinned official `mcp==2.2.0` SDK for discovery, initialization and
stdio lifecycle. No new HTTP listener, general Agent framework or registry is
introduced. SDK usage follows the [official low-level server contract](https://py.sdk.modelcontextprotocol.io/v2/advanced/low-level-server/)
and [MCP tools protocol](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

Reused components:

- `backend/app/area_yield/product.py`: request and complete result schemas.
- `backend/app/area_yield/product_authority.py`: `forecast_area_product` and
  server-owned authority loading/hash validation.
- `backend/app/area_yield/product_errors.py`: typed error classification.
- Existing HTTP, CLI and Python routes: unchanged, used for parity acceptance.

The adapter constructs `AreaDrivenForecastRequest` and delegates exactly once.
It performs no XLS access, fitting, yield/shape/peak calculation, fallback choice
or independent result hashing. Success structured content is the product result
itself, also serialized as a JSON text block for MCP client compatibility.

## Tool contract

Required: `farm`, `productive_area_mu` (positive finite Decimal string),
`target_season` (consecutive years). Optional: `season_start`, `season_end`,
`as_of`, retaining product validation. Both bounds must be supplied together.
All other keys are forbidden, including authority path/hash, method override,
yield override, selectors, weather and future plans.

```json
{
  "farm": "保山杨柳农场",
  "productive_area_mu": "393.4",
  "target_season": "2026-2027",
  "season_start": "2026-10-15",
  "season_end": "2027-05-09",
  "as_of": "2026-09-12"
}
```

Output schema is exactly `AreaDrivenForecastResult.model_json_schema()`, including
all daily rows, peaks, balance, limitations, provenance and result hash. Discovery
does not require authority availability. Combined canonical input/output schema
SHA256 is pinned in the regression test and evidence (sorted compact JSON).

Tool execution errors use MCP `isError=true` plus structured content and JSON text:

```json
{"status":"error","code":"AREA_FORECAST_UNSUPPORTED_FARM_HISTORY","reason":"PRIOR_SEASON_HISTORY_MISSING"}
```

Request errors remain `AREA_FORECAST_REQUEST_INVALID`; schema failures report
`INVALID_REQUEST_DOCUMENT` without echoing inputs. Unsupported canonical farms
and unavailable/incomplete/unauthorized immediate-prior history preserve specific
product reasons. Authority configuration, file, outer hash and payload errors
remain `AREA_FORECAST_AUTHORITY_UNAVAILABLE`, never request errors. Unexpected
exceptions fail closed with a sanitized authority error. MCP has no HTTP status;
HTTP counterparts retain 422/503 and CLI retains request/authority exit codes 2/3.
Unknown farms never fall back; older history never substitutes for immediate prior.

## Operator launch and Doubao handoff

Install the repository's constrained dependencies in its Python environment:

```bash
python -m pip install -c backend/constraints-ci.txt -e '.[dev]'
python -m backend.app.mcp.area_forecast
```

The trusted local MCP host launches this module from the repository root (or an
installed package), using the absolute interpreter of that environment. Configure
these **server process environment** names, never tool arguments:

- `AREA_YIELD_AUTHORITY_PATH`: operator-controlled readable authority artifact.
- `AREA_YIELD_AUTHORITY_SHA256`: approved outer file SHA256.

The artifact also has its existing internal payload hash. Pin both through the
existing product authority, do not generate new model authority in this adapter.
Keep paths/values in private host configuration; none belong in public Git or
tool responses. Stdout is MCP protocol only. Stdio relies on the trusted local
host/OS boundary and is not an unauthenticated remote deployment.

Doubao integration handoff: server name above, stdio command above, discover the
single tool with `tools/list`, then invoke it with `tools/call` and the six-field
contract. A host that supports local MCP processes can use these launch settings.
This document does **not** assert Doubao currently accepts stdio or invent its
platform registration fields. If the deployment requires remote MCP transport,
hosting/authentication and platform registration need separate authorization.
No credentials or Doubao runtime configuration were supplied or used.

`MCP_TOOL_READY_FOR_DOUBAO_INTEGRATION=true` means the local tool contract and
client invocation are verified. `DOUBAO_RUNTIME_REGISTRATION=NOT_EXECUTED` and
`DOUBAO_WORK_ASSISTANT_READY=false` remain explicit; no online integration claim.

## Acceptance evidence

An actual SDK stdio client discovered and called the server. With the existing
private Yangliu authority, full Python/HTTP/CLI/MCP JSON payloads were identical:

- Yield: 1232.338729 kg/mu; total: 484802.055989 kg; 207 rows.
- Single-day peak: 2027-04-18, 6450.429844 kg.
- Seven-day cumulative peak: 2027-04-15..2027-04-21, 45110.003741 kg.
- Daily sum: 484802.055987 kg; difference: -0.000002 kg, within existing tolerance.
- Result hash: `6d406e8a4a436b2c9bf347dca5f52b3f9b048ea4fb1602405225fc4f2ac39d1b`.

Private artifacts are under the authorized local artifact root,
`mcp-tool-adapter-p1/`: `four-way-parity.json`, `mcp-result.json`, `schemas.json`.
Only aggregate acceptance and hashes are committed; no raw data or authority.
See [machine-readable evidence](evidence/area-forecast-mcp-tool-adapter-p1.json).

Local commands:

```bash
python -m pytest backend/tests/mcp backend/tests/area_yield backend/tests/agent backend/tests/trial backend/tests/core_forecast backend/tests/planning/test_empirical_forecast.py backend/tests/planning/test_empirical_maturity.py backend/tests/test_harvest_state_cli.py -q --disable-warnings
ruff check .
ruff format --check .
mypy backend/app
git diff --check
```

Tests exercise discovery/schema pinning, actual stdio, synthetic four-way parity,
determinism, Decimal input rejection, missing prior, unknown farm, authority
failure redaction, and typed HTTP/CLI/MCP error parity. CI evidence belongs to the
new PR's exact final HEAD, not #617. No workflow or required-check bypass.

Final local run: 884 passed (including 18 MCP tests), 139 warnings. Ruff check,
format check, mypy (432 source files), lock, JSON/reference/hash and diff checks
passed. All 179 prior artifact hashes checked against the retained manifest
remain unchanged. Existing locked package versions were not upgraded; the lock
adds only the MCP SDK dependency closure and its platform resolution markers.

## Stop boundary

No forecast math, model refit/tuning, historical evidence, persistence, legacy
v0.3 contract, weather, future plan or UI changes. No Ready, Merge, Release or
Doubao deployment authorization. Final stop:
`COORDINATOR_AREA_FORECAST_MCP_TOOL_ADAPTER_P1_REVIEW`.
