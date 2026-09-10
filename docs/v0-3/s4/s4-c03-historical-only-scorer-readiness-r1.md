# V0.3 S4 C03 historical-only scorer readiness R1

## Decision

`03_phenology_offset` now has a separate V2/V4 historical-only prediction
adapter. This is a readiness change only: no candidate evaluation was started,
no validation metric was calculated, and no durable budget row was written.

The owner decision remains authoritative:

- semantic: `TRAINING_TIME_LEARNED_SHIFT_MODEL_BOUND`
- allowed parameter: `offset.maximum_abs_shift_days`
- excluded parameter: `forecast.observed_phase_adjustment_max_days`
- frozen values: `14, 18, 24, 28`
- incumbent value: `21`

The old `v0.3-s4-c03-phenology-offset-manifest-v1` remains historical audit
material. The current manifest is
`v0.3-s4-c03-phenology-offset-manifest-v2-historical-only`, bound to the V2
experiment plan, V4 guardrail policy, the frozen sparse surface, and the code
commit recorded in the evidence JSON.

## Historical-only prediction boundary

The adapter consumes the accepted SOURCE-002 TRAIN rows and uses validation
rows only as masked projection identities when a future caller constructs the
evaluation surface. Before model construction, every projection row's actual
quantity is replaced by `Decimal("0")`; the model builder receives TRAIN
quantities only. It has no TEST reader, database dependency, durable execution
authority, scorer callback, weather input, production-plan input, Task8/Task9
input, current-season input, prospective capture input, or wall-clock wait.

The training path is:

1. group and variety curves are built from canonical
   `season × farm × subfarm × variety × harvest_business_date` TRAIN rows;
2. the existing `fit_shared_curve` maturity primitive fits normalized curves;
3. a learned group peak delta against the variety parent curve is retained in
   a `ShiftModelArtifact`-shaped shift model;
4. the candidate bound is applied as the artifact's symmetric
   `(-maximum_abs_shift_days, +maximum_abs_shift_days)` bound;
5. the bounded shift is applied through the production-compatible interpolation,
   clipping, normalization, and curve-share projection semantics.

Thus the parameter enters the training-time learned shift model and then the
prediction math. The adapter does not call
`backend.app.maturity.service.forecast_natural_maturity`, whose operational
resolver requires forward-looking plan/weather/Task8/Task9 authorities.

The readiness proof is intentionally a prediction-identity proof, not a metric
or validation proof. On a synthetic TRAIN-derived projection fixture, all four
frozen values produce deterministic identities different from the incumbent
21-day bound. The frozen incumbent value produces a deterministic replay
identity. No claim is made about candidate quality.

## Current compatibility audit

The current V2 audit now distinguishes historical compatibility from the
current V4 runnable overlay:

| Candidate | Historical-only input | Real path/effect | Current V4 status | Reason |
| --- | --- | --- | --- | --- |
| 01 | yes | old local path only; rerun forbidden | blocked | `CANDIDATE_01_RERUN_FORBIDDEN` |
| 02 | yes | metric-only path; no prediction mutation | blocked | `NO_V2_BOUND_PREDICTION_QUANTILE_PATH` |
| 03 | yes | dedicated SOURCE-002 TRAIN scorer; bound changes prediction identity | ready | `C03_HISTORICAL_ONLY_SCORER_READY` |
| 04 | yes | historical scorer exists, but current evidence closure is exhausted | blocked | `C04_EXHAUSTED_EVIDENCE_INSUFFICIENT` |
| 05 | yes | no bound candidate scorer | blocked | `NO_BOUND_CANDIDATE_05_SCORING_PATH` |
| 06 | no | weather dependency | blocked | `C06_WEATHER_OUTSIDE_V2_HISTORICAL_POLICY` |
| 07 | yes | no bound candidate scorer | blocked | `NO_BOUND_CANDIDATE_07_SCORING_PATH` |
| 08 | no | Task9/weather feature dependency | blocked | `V2_HISTORICAL_ONLY_FEATURE_MANIFEST_REQUIRED` |

Accordingly, the audit's sole current next executable candidate is
`03_phenology_offset`. This is not execution authorization.

## V4 gate and future evidence

The C03 gate request is pure and binds:

- V2 experiment plan and its canonical hash;
- V4 guardrail policy and its canonical hash;
- sparse surface `V0_3_S4_SOURCE002_SPARSE_HORIZON_7_14_21_V1`;
- all pairing identities and the frozen C03 manifest/run hashes;
- candidate registry, run ordinal, code commit, and fixed seed;
- `test_access_requested=false` and `test_sealed=true`.

The request is checked by the shared version-aware gate. It never calls
`S4CandidateExecutionAuthority.execute`. Future real evidence can reuse the
merged R5 coverage-quality contract: six required axes and cell-level
`cell_id`, `comparable_rows`, `metric_status`, `reason_code`,
`reporting_status`, `reporting_reason`, and `selection_blocking`. A synthetic
round trip through the canonical serializer/parser passed without reading
validation data.

## Budget and stop boundary

The live PostgreSQL readback at readiness time was authority version 8 with
four canonical STARTED events (all C04), eight accepted events, last canonical
ordinal 4, and legacy reconciled debit 4. Therefore the derived current state
is effective consumed `8` and remaining `24`; there are zero C03 STARTED events.
The readiness adapter performed no ledger write. C04 remains
`EXHAUSTED_EVIDENCE_INSUFFICIENT`, C01 rerun remains forbidden, C06/C08 remain
blocked, and TEST remains sealed.

`C03_HISTORICAL_ONLY_SCORING_PATH_EXISTS=true` and
`C03_READY_FOR_REAL_VALIDATION=true` mean only that a future separately
authorized V4 request has a lawful scorer path. They do not authorize a run,
selection, TEST, promotion, Ready, or Merge.

