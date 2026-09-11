# Banna first forecast R4 — partial calibration, execution not completed

TASK_ID=V0_3_BANNA_FIRST_REAL_FORECAST_CALIBRATION_AND_EXECUTION_R4

## Current result

The authorized arrival-equals-harvest rule is implemented. The pinned historical
source was actually processed by `scripts/probe_banna_harvest_baseline_r4.py`.
The new code aggregates harvest quantities deterministically and emits the two
authorized baseline policies. It does **not** establish a complete parameter
library, Task8 artifact or normal forecast. The requested end-to-end result has
not been achieved.

R1/R2/R3 evidence remains unchanged. R4 supersedes R3's rejection of receipts as
harvest calibration and of the two explicit policy rates. It does not claim all
seven parameters must be independent measured observations.

## Frozen calibration rule

For `版纳勐旺农场 / Dx / 勐旺加工厂`:

- `historical_harvest_quantity_kg = historical_arrival_quantity_kg`.
- `marketable_rate = 1.000000`, `BASELINE_POLICY`: avoid double-discounting
  harvested usable quantity. This is not observed 100% marketability.
- `harvest_realization_rate = 1.000000`, `BASELINE_POLICY`: no additional
  realization discount. Existing Task9 capacity/inventory/loss constraints remain.
- Yield calculation is implemented as historical total / matching historical
  planted area, using Decimal and the existing planning canonical hash. Current
  acceptance area is not silently made a historical denominator.
- No transport factor, new discount, subfarm allocation, coordinates, raw-source
  edits, or missing-day fabrication is introduced.

## Actual source execution

Only `data/raw/2024_2025_receipts.xls` was read, after checking SHA256
`a55cbf259f52e6a20e30d646b43d2aa0f104f60786d725dbc051e46c76b390d5`.
Exact farm, variety source label `蓝莓原果Dx`, and destination factory are checked.
There are 3,420 rows, 181 observed dates, total **968113.233000 kg**.
The full source window is 2024-10-15 through 2025-05-09, containing 26 calendar
dates without rows. These are not filled with zero. Raw earliest tied peak is
2025-04-28, **15117.032000 kg**. This is not a smoothed maturity peak.

The complete daily aggregate is hashed but not committed. Reproduction:
`uv run python -m scripts.probe_banna_harvest_baseline_r4`.
Visibility/as-of is this acceptance's 2026-09-11 source verification, not a claim
of historical PIT capture. No 2025–2026 XLS, VALIDATION or TEST partition was read.

736 mu remains the accepted current farm-level aggregate. R2/R3 did not establish
it as this historical window's denominator; the described matched-relationship
analysis is not a recovered source-hash-verified area file. R4 therefore leaves
the actual yield authority null, while unit-testing the authorized division
formula with explicitly bound historical area. No new business-fact request is
issued, and the historical harvest source is accepted, not rejected.

## First internal model-interface discontinuity

This is a code-path finding, not a request for seven independent truths:

1. `backend/app/planning/service.py` returns peak/width/skewness scalar estimates.
2. `backend/app/maturity/model.py::fit_shared_curve` fits `SplineTransformer`
   plus Ridge and returns a normalized density vector. Its inputs are relative
   days, shares, weights, support, spline degree/knots and regularization. There
   is no width or skewness parameter to invert.
3. `backend/app/maturity/schemas.py::GroupCurveArtifact` stores density and peak,
   not Task5 width/skewness. Searching the maturity and Core implementation finds
   no consumption of those Task5 scalar fields.
4. `forecast_natural_maturity` requires an existing model artifact and effective
   plan. It reads `artifact_payload['anchor_event']`, then the corresponding plan
   date. It does not define a universal January 1 anchor. It also requires actual
   location/climate/weather/base-temperature bindings. No such artifact or plan
   exists in the acceptance DB (read-only count verified again).
5. Canonical training uses `analysis_dates` (January–April) and `smooth_series`.
   Relabeling the full October–May harvest window, inventing width/skewness as
   moments, or manufacturing an artifact would not be a thin inverse of this
   implemented model. No such substitution was made.

`TASK5_SCALAR_MATURITY_PARAMETERS_NOT_CONSUMED_BY_TASK8_SPLINE` is the internal
path blocker. The absence of the selected model anchor/artifact is also concrete.
No model redesign, arbitrary anchor, fake geography or unsupported model artifact
has been introduced to bypass it. No Task8/Task9/Forecast run is claimed.

## Actual application probe

The same nonproduction acceptance DB on port 55437 has a unique Alembic head
`0032_s4_validation_budget_durable_persistence`. Its library, observation, plan
and maturity-artifact tables each have zero rows. No database write was made.
The stopped API process was restarted on 127.0.0.1:8007 with the existing binding.
`GET /health/ready` returned 200. Normal `POST /planning/tasks` using farm_id=1,
Dx, 736.000000 mu and as_of=2026-09-11 returned **422** with
`parameter library version not found`. No dependency override or synthetic actor
was used. An initial proxy-routed curl 502 and direct connection failure preceded
restart; neither is interpreted as business authority evidence.

## Verification and boundaries

Targeted tests cover source row aggregation, deterministic hashes, no duplicate
rows, Decimal/finite/nonnegative checks, source/fact visibility, matched historical
area, no implicit current-area substitution, policy authority labels, no invented
offsets/width/skewness, and no library-ready claim from partial calibration.
Planning/maturity/harvest-state/Trial regressions run using test fixtures only.
Exact-head CI is recorded in the PR body and final report, not as a self-referential
commit hash here. No S4 execution, model retraining, TEST access or budget writes.

Budget is the last accepted durable snapshot, not a new readback: consumed 8,
remaining 24; this task's delta is 0. PR607 stays Draft. No Ready or Merge.

FINAL_STOP_GATE=COORDINATOR_FIRST_REAL_FORECAST_R4_REVIEW
