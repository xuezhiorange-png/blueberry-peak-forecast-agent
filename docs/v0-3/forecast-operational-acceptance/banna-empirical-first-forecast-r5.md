# Banna empirical maturity authority and first forecast R5

The normal forecast API completed a real, non-production acceptance run for
版纳勐旺农场 / Dx / 736 mu, destination 勐旺加工厂. This is a reproducible empirical
baseline forecast, not an accuracy result, physiological maturity observation,
calibrated quantile model, S4 reopening, or pilot-model approval.

## Frozen authority

Arrival quantity equals harvest quantity for this acceptance. The pinned
2024–2025 receipt ledger SHA-256 is
`a55cbf259f52e6a20e30d646b43d2aa0f104f60786d725dbc051e46c76b390d5`.
Only exact farm/factory/Dx facts from this file are used. No 2025–2026 source,
VALIDATION partition, or TEST bytes are loaded.

The coordinator explicitly authorizes 736 mu as this acceptance calibration
denominator, not a claim about historical agronomic acreage. Historical harvest
968113.233000 / 736.000000 gives yield 1315.371240 kg/mu rounded to six places.
Marketable and realization rates are baseline policies of 1.000000: no duplicate
discount, arrival conversion, transport loss, or inferred 100% observed rate.

## Distinct maturity paths

The existing Task8 spline/model path remains available and unchanged. The new
`HISTORICAL_CALIBRATION` discriminator identifies a separately persisted empirical
authority, not a Task8 model or artifact. Task5 peak/width/skewness scalars are
`NOT_REQUIRED_FOR_EMPIRICAL_MATURITY_AUTHORITY`; their existing model-path gates
are not relaxed. No dummy parameter library, model run, or spline artifact is created.

207 calendar days (2024-10-15 through 2025-05-09) contain 181 observed receipt
dates and 26 zero-harvest dates under the explicitly authorized complete-ledger
semantics. No interpolation is used. This is not a change to S4 sparse-row rules.
Daily shares sum to one; deterministic rounding residue is reconciled on the
largest positive day. Task9 retains its 0.001 kg precision: the area/yield product
968113.232640 becomes total supply 968113.233 kg.

`empirical_maturity.py` owns pure calibration. `empirical_authority.py` validates
and replays persisted authority. `empirical_forecast.py` builds the server-owned
Task9 request; Task9 verifies the complete request against the persisted authority
before executing its existing FIFO, capacity, continuity, and mass-balance logic.
Migration 0033 adds separate append-only authority and forecast tables, with
UPDATE/DELETE rejection. Task8 IDs are not fabricated.

## Baseline operations and dates

Read-only checks found no capacity, weather, initial-inventory, or mature-loss
authority in the acceptance runtime. The registration tool refuses replacement
when these existing operational tables contain rows. Explicit neutral policies
use labor/weather/operations multipliers of one, empty opening inventory and no
additional loss. They are not observations. Capacity is the historical maximum
15117.032 kg/day, not infinity and not a lower peak-shaving threshold.

The explicit date policy maps the historical start month/day to the next future
start after the 2026-09-11 acceptance as-of, then preserves relative day indices:
2026-10-15 through 2027-05-09. The season is a baseline policy window, not a
phenological event. Coordinates and subfarm area allocation are unnecessary.

Task9's P50/P80/P90 scenarios all receive the same point supply. Their recorded
uncertainty status is `NOT_CALIBRATED_IDENTICAL_POINT_SCENARIOS`; no nominal
coverage or probabilistic confidence is claimed.

## Actual execution

Normal server-owned actor configuration (no override) authorized
`POST /api/v1/trial/forecasts` with the empirical authority hash. HTTP 200 returned
COMPLETED, empirical forecast run 1 and Task9 run 1. The new discriminated
application branch does not masquerade as a legacy Core/Task8 model run.

Fresh-session `GET /api/v1/trial/empirical-forecasts/1` reloaded authority,
validated the curve and forecast hashes, and verified the persisted Task9 result.
207 rows passed mass balance and capacity; all arrival quantities equal harvest,
and all closing inventory is zero.

| Quantity | Historical | Forecast |
|---|---:|---:|
| Total kg | 968113.233000 | 968113.233000 |
| Single-day peak date | 2025-04-28 | 2027-04-28 |
| Single-day peak kg | 15117.032000 | 15117.032000 |

Existing canonical 7-day cumulative metrics give 88757.236000 kg for
2027-04-26 through 2027-05-02. This helper is shared with Core; no metric formula
or legacy selection policy was invented. Similarity to history is expected for
this empirical baseline and is only a sanity check, never accuracy validation.

## Verification and stop

1226 targeted planning, maturity, harvest-state, Core, trial, and agent tests passed.
Tests include synthetic persistence/fresh-session round trip, immutable migration,
source replay/tamper rejection, 181+26 calendar semantics, yield rounding, canonical
metrics, and existing Task8 golden regressions. Ruff, format, mypy, and diff check
passed. Final exact-head CI is recorded in the PR body to avoid self-referential
commit hashes. Full-suite canary is skipped for PRs by repository CI contract.

R1–R4 evidence is preserved. S4 is closed; budget values remain the last accepted
snapshot (8 consumed, 24 remaining), not a new database readback. No validation
budget, TEST access, Ready, Merge, or pilot approval follows this execution.

FINAL_STOP_GATE=COORDINATOR_FIRST_REAL_FORECAST_R5_REVIEW
