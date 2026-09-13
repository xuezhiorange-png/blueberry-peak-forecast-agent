# Area-driven product integration P1

Task: `NEXT_VERSION_AREA_DRIVEN_FORECAST_PRODUCT_INTEGRATION_P1`.
Base main: `ecee9474ea4ed60fda325fc0c8403055ceb5bf21`.

## Decision, not another experiment

`VALIDATION_RESULT=NO_CLEAR_WINNER` remains unchanged.
`PRODUCT_ENGINEERING_POLICY=B1`, `FORECAST_POLICY_VERSION=AREA_YIELD_B1_V1`.
Prior-season yield supplies scale; frozen Global Ridge supplies shape. This is an
explicit engineering decision, not a statistical winner, accuracy approval or
production release. No fitting, evaluation, selector, shifts, weather, future plan
or model search occurs here. Historical R1–R7B evidence is not edited.

## One calculation, existing transports

`backend.app.area_yield.product.forecast_by_area(request, authority)` owns all
calculations. The server wrapper validates an operator-configured private bundle.
The existing `POST /api/v1/trial/forecasts` accepts the new request alongside both
legacy request types. Existing actor permission checks remain mandatory (including
the existing 404 unauthorized-resource hiding contract).

`AgentOrchestrator.forecast_by_area(request)` and existing CLI
`python -m backend.app.cli area-forecast --input request.json --output result.json`
call the same wrapper. The Python method is not the final Agent/MCP integration.
The intended architecture is capability → tool → MCP → 豆包工作助手.
`CORE_PRODUCT_FORECAST_PATH_READY=true`, `PYTHON_PRODUCT_METHOD_INTEGRATED=true`,
`MCP_TOOL_INTEGRATED=false`, `DOUBAO_WORK_ASSISTANT_INTEGRATION_READY=false`,
`AGENT_INTEGRATION_READY=false`.
`NEXT_INTEGRATION_STEP=AREA_FORECAST_MCP_TOOL_ADAPTER` requires separate authorization.
No new MCP stack is invented here. The legacy Slice B tool
allowlist is unchanged; the Agent exposes a separate explicit typed product method.

Example request (Decimal strings, not a claim of a future planting plan):

```json
{
  "forecast_method": "AREA_DRIVEN_B1",
  "farm": "保山杨柳农场",
  "productive_area_mu": "393.4",
  "target_season": "2026-2027",
  "season_start": "2026-10-15",
  "season_end": "2027-05-09",
  "as_of": "2026-09-12"
}
```

This path is deterministic/stateless: HTTP returns the complete result and hash;
CLI can save it. It does not create a legacy database run or pretend that the old
GET-by-run-ID endpoint persists these new results. Deployment, durable product
run storage and a new UI are not claimed. The old persisted v0.3 path remains intact.

## Authority and leakage boundaries

Private artifacts remain outside Git. Operator configuration:

```text
AREA_YIELD_AUTHORITY_PATH=/controlled/path/authority.json
AREA_YIELD_AUTHORITY_SHA256=<actual file SHA256>
```

The request cannot supply a model/path/hash override. Missing or corrupt authority
fails closed with HTTP503 `AREA_FORECAST_AUTHORITY_UNAVAILABLE`. Unreadable files,
missing configuration, outer SHA mismatch, payload hash mismatch and malformed
authority are server faults, not user-input422 errors. Error details expose a
non-sensitive reason, never a private filesystem path.

Invalid business requests return422: window/as-of violations use
`AREA_FORECAST_REQUEST_INVALID`; unsupported farm/prior history uses
`AREA_FORECAST_UNSUPPORTED_FARM_HISTORY`. Request-schema validation retains the
existing framework422 response. CLI uses these machine-readable codes/reasons
and exit2 for requests, exit3 for unavailable authority. Python raises the same
typed product errors. Existing legacy error behavior is unchanged.

Prepare the reviewed initial snapshot without training or scoring:

```bash
python -m scripts.build_area_product_authority \
  --artifact-root /controlled/blueberry-area-yield-artifacts \
  --available-on 2026-09-12 \
  --output /controlled/new-authority.json
```

The packager verifies pinned R7/R7B manifest and file hashes, extracts only observed
complete total facts (not predicted totals or daily labels), checks the area/yield
correspondence and loads the unchanged R7 Ridge. It represents each farm once,
not once per comparison model. Initial history: two complete 2526 business totals;
shape: existing 2425-trained Global Ridge, alpha10/two harmonics. No new Ridge fit.
Availability is the actual operator publication date, not a fabricated historical
PIT timestamp. This snapshot intentionally cannot serve backdated forecasts before
publication. Runtime selects only complete, area-authorized, available history
ending before the requested business season and with an earlier season identity.

Registered canonical farms must have the **immediate prior season**:2026-2027
requires2025-2026;2027-2028 requires2026-2027. Requested area alone multiplies yield.
There is no default Global fallback, no cross-farm substitution and no search
backward to an older complete season. Missing prior history, incomplete history,
unauthorized area or history unavailable at cutoff each fail closed with explicit
`PRIOR_SEASON_HISTORY_MISSING`, `PRIOR_SEASON_HISTORY_INCOMPLETE`,
`PRIOR_SEASON_AREA_UNAUTHORIZED` or `PRIOR_SEASON_HISTORY_UNAVAILABLE_AT_CUTOFF`.
Global total remains research code only, outside `AREA_YIELD_B1_V1` product dispatch.

Identity is exact-label normalization plus the already authorized Nanzhuang alias.
Unknown labels fail closed with `UNSUPPORTED_CANONICAL_FARM`; they are not
silently registered, bound to another Farm or guessed from a similar name.

## Calendar and quantities

Target years must be consecutive. Explicit start/end define a business-season
window, not a sub-window query for a previously computed season. Without explicit
bounds the existing July–June calendar is used with `FORECAST_ASSUMPTION` (including
leap years, not a fixed365-day loop). No future Apr15 rule is invented. Both bounds
must lie in the target season and contain at least seven calendar days. Shape is
cropped and normalized to the requested business window; total stays unchanged.

All totals and final daily quantities use existing six-decimal half-even rounding.
Daily-sum tolerance is the existing component rule: `0.0000005 × days + total × 1e-12`.
Peak and canonical seven-day sum come from final rounded daily rows, with the
existing earliest tie break. No extra marketable/realization/transport discount.
Uncertainty is uncalibrated point-only; area scaling is a business assumption.

## Actual acceptance

Local private directory:
`/Users/charles/Documents/blueberry-area-yield-artifacts/product-integration-p1/`.
The real source snapshot was loaded in fresh CLI processes for393.4/100/500/1000mu;
normal HTTP ASGI requests (no dependency override) and the Agent method returned
identical result hashes for each request. No network deployment is claimed.

Yangliu393.4mu, explicit example window2026-10-15..2027-05-09:

- Historical yield source season:2025-2026; yield1232.338729kg/mu; fallback:false.
- Predicted total:484802.055989kg;207daily rows.
- Single-day peak:2027-04-18,6450.429844kg.
- Canonical7day peak:2027-04-15..2027-04-21,45110.003741kg.
- Daily sum:484802.055987kg; difference:-0.000002kg; mass balance:PASS.

This is a product execution example, not new accuracy evidence. Unknown-farm
rejection is validated with an explicitly synthetic unit fixture, never added to
real business authority. Existing empirical/planning, Python, trial/API, Core and
CLI regression tests run locally. Required GitHub CI/full-suite-canary remains
unchanged and must verify the final exact head; no Ready/Merge/Release authorized.

Review correction task: `NEXT_VERSION_AREA_DRIVEN_FORECAST_PRODUCT_INTEGRATION_P1_REVIEW_FIX_R1`.
Pre-fix head `2d8152f62078b175041401ff94feba89e990f21c` and its successful CI
`34702331025` remain revision history, not final revised-head verification.
The accepted Yangliu example still has the required immediate prior and keeps
unchanged prediction mathematics, quantities, dates and result metadata.
Review-fix local verification:866tests passed; Ruff/format/Mypy passed. Real393.4,
100,500,1000mu outputs remain exactly equal to their pre-fix outputs through
fresh-process CLI, HTTP and Python, including result hashes. The393.4mu hash
remains `6d406e8a4a436b2c9bf347dca5f52b3f9b048ea4fb1602405225fc4f2ac39d1b`.
Private review parity evidence SHA256:
`b0aafcbd4a56606c012ebc120cee5c5c579d3a3ee64734f39fc2dc75d302a9bf`.
179historical artifact hashes plus the R7B manifest remain unchanged.

Stop gate: `COORDINATOR_PRODUCT_INTEGRATION_P1_FIX_REVIEW`.
