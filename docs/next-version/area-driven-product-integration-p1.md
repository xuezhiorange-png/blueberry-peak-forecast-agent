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
call the same wrapper. No standalone MCP server/tool contract exists in the
inspected repository; no new MCP stack is invented. The legacy Slice B tool
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
fails closed; this is distinct from missing *same-farm* history, which succeeds via
explicit Global fallback when eligible global history exists.

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

Known farms use their latest eligible prior history; requested area alone multiplies
yield. Global fallback uses equal-farm median from the latest available eligible
history season, never volume weighting or future labels. Reasons distinguish no
prior season, incomplete history, invalid area history and other unavailability.
If no eligible global samples exist, the service refuses to invent yield.

Identity is exact-label normalization plus the already authorized Nanzhuang alias.
An unknown label stays distinct and is explicitly marked `UNREGISTERED_EXACT_LABEL`;
it is not silently bound to another database Farm or guessed from a similar name.

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
fallback is validated with an explicitly synthetic unit fixture, never added to
real business authority. Existing empirical/planning, Agent, trial/API, Core and
CLI regression tests run locally. Required GitHub CI/full-suite-canary remains
unchanged and must verify the final exact head; no Ready/Merge/Release authorized.

Stop gate: `COORDINATOR_PRODUCT_INTEGRATION_P1_REVIEW`.
