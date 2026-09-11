# Workpaper — remaining V0.3 S4 candidate viability audit R1

## Scope and method

This workpaper records a read-only inspection of the current `origin/main` at
`b0257192bb27097f30f279dcc735d6cc9da812bd`. The commit is the merge commit for
PR #601. The audit is limited to the three candidates that remain registered
after the C01 rerun prohibition, C03 canonical-shift blocker, and C04
exhausted-evidence closure:

```text
02_quantile_calibration
05_marketable_rate
07_harvest_efficiency
```

The testable requirement is conjunctive:

```text
historical_only_compatible
AND
real_candidate_scoring_path_exists
AND
parameter_or_feature_reaches_prediction_math
AND
parameter_change_can_change_prediction
```

No row loader, prediction function, metric evaluator, PostgreSQL repository,
TEST reader, or S4 execution-authority method was called. The audit module is
pure evidence construction and cannot create a `STARTED` event.

## Frozen authority

The audit is bound to:

```text
EXPERIMENT_PLAN_VERSION=v0.3-experiment-plan-v2
EXPERIMENT_PLAN_HASH=c2bfab4ec38b4ca640f62d061494961c5b49afe5b52fa675326aa80fdf5f8ad9
GUARDRAIL_POLICY_VERSION=v0.3-s4-guardrail-policy-v4-breakdown-reporting-floor
GUARDRAIL_POLICY_HASH=f2b5c808d5a72170f055f891422f4253834a977cd5c74b450c8e4546653f46d2
SOURCE_002_TRAIN_ROWS=16224
SOURCE_002_VALIDATION_ROWS=8006
FORECAST_HORIZONS=7,14,21
TEST_REMAINS_SEALED=true
```

The plan eligibility overlay is deliberately not rewritten. Candidates 02, 05,
and 07 remain registered and `REGISTERED_AND_GUARDRAIL_ELIGIBLE`; this audit
only reports whether the current implementation can lawfully run them under
V4.

## C02 inspection — quantile calibration

The registered controls are `intervals.p80_quantile` and
`intervals.p90_quantile`. The only concrete function identified for these
controls is the empirical coverage calculator:

```text
backend.app.forecast_quality.quantile_coverage.compute_upper_quantile_coverage
```

Its implementation receives paired forecast/actual rows and computes a
coverage cell. It does not construct the V2 candidate P50/P80/P90 prediction
surface. The V2 compatibility audit explicitly records this as
`NO_V2_BOUND_PREDICTION_QUANTILE_PATH`.

Consequences:

```text
parameter_reaches_prediction_math=false
parameter_change_can_change_prediction=false
historical_only_execution_compatible=false
currently_runnable_under_v4=false
```

Even if a future adapter made the input source historical-only, the frozen V4
primary is strict lower `daily_wape`, which is a point/P50 metric. A change
that only affects interval coverage cannot satisfy the primary relation. The
candidate is therefore structurally unselectable under the current V4 policy,
not merely missing an implementation.

No C02 P50 mutation, quantile proxy, V5 policy, or policy amendment was made.

## C05 inspection — marketable rate

The current production-shaped core path is:

```text
backend.app.core_forecast.application.execute_core_forecast_run
  -> backend.app.core_forecast.service.compose_complete_daily_marketable_curve
```

The service reads persisted Task8 and Task9 authorities, validates their
relationship, and applies persisted sorting/post-harvest retention policy to
the daily harvested quantity. Separately, the planning model and planning
documentation define a `marketable_rate` formula. Neither inspection provides
a V2-bound candidate scorer that consumes an unambiguous SOURCE-002 historical
marketable-rate authority and applies it to candidate prediction math.

The audit therefore marks the current canonical path as requiring production
plan/Task8/Task9-style authority and marks the SOURCE-002-only path absent:

```text
source_002_only_candidate_path_exists=false
historical_only_input_compatible=false
parameter_reaches_prediction_math=false
parameter_change_can_change_prediction=false
historical_only_execution_compatible=false
currently_runnable_under_v4=false
```

The audit does not equate harvest quantity with marketable quantity, use a
default rate, or substitute the C04 amplitude multiplier. Such an action would
be a new candidate semantic, not an audit finding.

## C07 inspection — harvest efficiency

The concrete harvest-state path is:

```text
backend.app.harvest_state.service.run_harvest_state_model
```

The current implementation resolves effective capacity from nominal capacity,
`labor_availability_ratio`, `weather_harvest_efficiency_ratio`, and
`operational_efficiency_ratio`. The weather ratio is computed from weather
feature bands. The corresponding Task9 authority schema/model persists these
fields. No C07 V2 candidate scorer or SOURCE-002-only derivation of these
canonical inputs is present.

The audit intentionally does not invent a harvest-efficiency label, peak
proxy, labor proxy, or weather-free substitute. It consequently reports:

```text
source_002_only_candidate_path_exists=false
uses_weather=true
uses_Task9=true
historical_only_input_compatible=false
parameter_reaches_prediction_math=false
parameter_change_can_change_prediction=false
historical_only_execution_compatible=false
currently_runnable_under_v4=false
```

## All-candidate closure

The current V4 runnability facts are:

| candidate | plan eligibility | V4 runnable | reason |
| --- | ---: | ---: | --- |
| 01 | true | false | rerun forbidden |
| 02 | true | false | quantile-only path cannot strictly improve point primary |
| 03 | true | false | canonical training shift not separable from forward-looking authority |
| 04 | true | false | exhausted evidence insufficient |
| 05 | true | false | SOURCE-002 marketable-rate authority unavailable |
| 06 | false | false | weather outside V2 historical policy |
| 07 | true | false | SOURCE-002 harvest-efficiency authority unavailable |
| 08 | false | false | historical-only feature manifest required |

The closure is not a candidate selection. It only establishes:

```text
NEXT_EXECUTABLE_CANDIDATE=NONE
CURRENT_FROZEN_PLAN_HAS_NO_REMAINING_EXECUTABLE_CANDIDATE=true
S4_NEXT_DECISION_REQUIRED=COORDINATOR_CHOICE_BETWEEN_INCUMBENT_CLOSURE_OR_NEW_EXPERIMENT_PLAN_AUTHORIZATION
```

No incumbent closure, TEST opening, new plan version, or new candidate was
issued.

## Budget and TEST reconciliation

This audit did not touch the durable ledger or any validation data:

```text
LEGACY_RECONCILED_VALIDATION_DEBIT=4
CANONICAL_STARTED_COUNT=4
EFFECTIVE_CONSUMED=8
REMAINING=24
BUDGET_DELTA=0
NEW_STARTED_EVENT_COUNT=0
NEW_TERMINAL_EVENT_COUNT=0
VALIDATION_DATA_REREAD=false
VALIDATION_SCORING_PERFORMED=false
CANDIDATE_EXECUTION_PERFORMED=false
TEST_ACCESS_REQUESTED=false
TEST_BYTES_READ=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
```

The farm-total baseline remains a TRAIN-only median comparison/reference
component. It is not a selected model and does not gain unsupported interval
outputs.

## Review disposition

```text
RESULT=AUDITED_AND_PUSHED
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S4_REMAINING_CANDIDATE_VIABILITY_REVIEW
```

The coordinator must choose between incumbent-oriented S4 closure and a
separately authorized experiment-plan change before any new candidate work is
started. This workpaper does not authorize either choice.
