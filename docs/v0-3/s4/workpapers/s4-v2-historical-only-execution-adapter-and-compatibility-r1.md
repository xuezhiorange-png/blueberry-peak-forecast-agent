# Workpaper — S4 V2 historical-only execution adapter and compatibility R1

```text
TASK_ID=V0_3_S4_V2_HISTORICAL_ONLY_EXECUTION_ADAPTER_AND_COMPATIBILITY_R1
BASE_MAIN_SHA=219d72399e0d23dbe57e35169a2196b37a990a49
BASE_MAIN_TREE=834875e61de8542487f91ff801acc973131da817
TASK_CLASS=IMPLEMENTATION_AND_EXECUTION_READINESS
```

## 1. Scope and safety decision

This work closes the missing V2-bound execution-readiness layer. It is not a
candidate execution. The implementation deliberately has no database session,
budget-journal write, execution callback, TEST reader, or scoring entry point.
The final compatibility decision is `NEXT_EXECUTABLE_CANDIDATE=NONE`.

The reason is evidence-based: no audited candidate currently satisfies both
conditions required by the V2 gate:

```text
HISTORICAL_ONLY_INPUT_COMPATIBLE=true
PARAMETER_REACHES_ACTUAL_SCORING_PATH=true
PARAMETER_CHANGE_CAN_CHANGE_PREDICTION=true
V2_BOUND_SCORING_PATH_EXISTS=true
```

The current V2 adapter reports the first two facts separately so a future
manifest cannot mistake a compatible input policy for an executable scorer.

## 2. V1/V2 identity reconciliation

`backend/app/s4_experiment.py` retains the V1 constants and
`canonical_guardrail_policy()` unchanged. The new
`canonical_guardrail_policy_v2()` starts from the same metric/comparison
preimage, then binds the V2 plan and adds an explicit historical-only overlay.
This produces a new deterministic V2 guardrail hash while preserving the old
hash's replayability.

Observed identities:

```text
V1_PLAN_HASH=9e223a02a1b38c028c230a45eb1fa8323f3c2247bb85e7b439f3351e51042500
V1_GUARDRAIL_POLICY_HASH=74ecd47339572955e654cf61c38ee6b0546ba51a36e67f80f6ad4dd4519f1ff8
V2_PLAN_HASH=c2bfab4ec38b4ca640f62d061494961c5b49afe5b52fa675326aa80fdf5f8ad9
V2_GUARDRAIL_POLICY_VERSION=v0.3-s4-guardrail-policy-v2
V2_GUARDRAIL_POLICY_HASH=8bdf09c983b11c66547f4c684dcf851ead39952b2b569532c00fa2501301e5c9
```

The overlay freezes no new model formula. It binds the absence of weather,
production plan, Task8/Task9, prospective capture, and wall-clock waiting;
the horizon set is exactly `(7, 14, 21)`. C01 remains forbidden from rerun,
and C06/C08 remain ineligible.

## 3. Historical data authority

`load_frozen_engineering_dataset()` already verifies the exact SOURCE-002
TRAIN and VALIDATION bytes and row counts. The new V2 authority constructor
adds the execution-specific checks:

1. TEST count must remain zero.
2. The cutoff is `max(TRAIN.harvest_business_date)`.
3. The cutoff must be strictly before the first VALIDATION date.
4. Only VALIDATION targets at exact offsets 7, 14, and 21 are selected.
5. All three requested offsets must be represented; a partial set is not
   silently treated as complete.
6. Training rows are returned from the original TRAIN tuple only.

The current verified result is:

```text
TRAIN_ROWS=16224
VALIDATION_ROWS=8006
TRAIN_END_DERIVED=2026-01-30
VALIDATION_START=2026-01-31
EVALUATION_TARGET_ROWS=688
OBSERVED_HORIZONS=7,14,21
```

The authority exposes SHA-256 identities for the train dataset, validation
dataset, actual label set, derived cutoff policy, horizon set, business grain,
and common comparable target set. Its public `payload()` intentionally omits
the row tuples; rows remain internal inputs to a future separately authorized
scorer rather than being copied into governance evidence.

Feature-date validation rejects any non-`date` value and any feature date
after the derived cutoff. It does not infer missing feature values or use
held-out labels as features.

## 4. Metric boundary

Daily WAPE, daily MAE, and interval coverage are marked as computable only
after a lawful historical-only scorer exists. This adapter does not calculate
them. Cumulative absolute error, single-day peak, and sustained seven-day
peak remain `COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE`, because sparse
7/14/21 targets do not establish a continuous daily rowset. The inherited
S4-B policy therefore remains blocked where those metrics are required. No
zero-fill or artificial complete-window claim was introduced.

## 5. Candidate audit work

The audit implementation in
`backend/app/s4_v2_historical_only_execution.py` records actual code paths,
data domains, parameter reachability, and V2-path existence in a fixed order:

```text
01_parameter_calibration
02_quantile_calibration
03_phenology_offset
04_yield_parameter
05_marketable_rate
07_harvest_efficiency
```

### C01

The existing local replay reads SOURCE-002 TRAIN/VALIDATION and its curve
configuration, and its curve parameters reach local prediction math. It is
nevertheless not a V2 execution path because the frozen C01 policy permanently
forbids rerun. The adapter never calls `run_local_replay()`.

### C02

`compute_upper_quantile_coverage()` is a metric-only function over an S3
binding contract. There is no V2-bound historical prediction/quantile
calibration path. The audit therefore records no parameter reachability and
does not infer execution eligibility from the candidate manifest.

### C03

`offset.maximum_abs_shift_days` is a real parameter in the legacy maturity
service path. That path is not a V2 historical-only scorer: it depends on
production-plan, weather, and Task8/Task9 runtime authority. The C01 local
scorer does not consume the offset. Wiring the legacy service into V2 would
violate the frozen input basis, so the adapter records:

```text
C03_HISTORICAL_ONLY_SCORING_PATH_EXISTS=false
C03_CURRENT_V0_3_EXECUTION_ELIGIBLE=false
REASON=C03_NO_SOURCE_002_ONLY_SCORING_PATH
```

### C04/C05/C07

The current repository has no bound candidate-specific historical scorer for
these registered parameter hypotheses. Their input-policy shape can be
historical, but no actual function currently makes the parameter change a
prediction result. They remain fail-closed.

### C06/C08

C06 is blocked by the explicit weather requirement. C08 is blocked because no
V2-bound SOURCE-002-only feature manifest exists. They are represented in the
V2 policy overlay, not smuggled into the six-candidate audit.

## 6. Baseline and later lanes

The farm-total baseline estimator remains a separate TRAIN-only median
reference. Its identity and semantics are not promoted to the selected V0.3
model, and this work does not invent baseline quantiles. TEST remains sealed;
no candidate is selected, no model is approved for pilot, and S5/S6 are not
started.

```text
LEGACY_RECONCILED_VALIDATION_DEBIT=4
CANONICAL_STARTED_COUNT=0
EFFECTIVE_CONSUMED=4
REMAINING=28
BUDGET_DELTA=0
CANDIDATE_EXECUTION_PERFORMED=false
VALIDATION_SCORING_PERFORMED=false
TEST_ACCESS_REQUESTED=false
TEST_EVALUATION_PERFORMED=false
SELECTED_CANDIDATE_ID=NOT_ISSUED
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The next valid governance step is a coordinator review of this compatibility
evidence. A future candidate run needs a separately bound V2 manifest and
execution authorization; this readiness adapter does not imply either.
