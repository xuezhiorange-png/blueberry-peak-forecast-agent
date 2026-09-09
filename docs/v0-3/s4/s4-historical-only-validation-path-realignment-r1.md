# V0.3 S4 historical-only validation path realignment R1

This is an append-only governance correction. It does not rewrite PR #591–#595
evidence and does not execute a candidate, score VALIDATION, or access TEST.

## Current decision

The current V0.3 S4 validation authority is the accepted historical SOURCE-002
TRAIN/VALIDATION partition. The 7/14/21 horizons are offline offsets, not
wall-clock waiting windows:

```text
V0_3_FORECAST_INPUT_BASIS=HISTORICAL_DATA_ONLY
FORECAST_HORIZONS_DAYS=7,14,21
HORIZONS_ARE_OFFLINE_EVALUATION_OFFSETS=true
CURRENT_WEATHER_INPUT_REQUIRED=false
CURRENT_PRODUCTION_PLAN_INPUT_REQUIRED=false
CURRENT_REAL_FORWARD_LOOKING_BUSINESS_INPUT_REQUIRED=false
CURRENT_REAL_PROSPECTIVE_CAPTURE_REQUIRED_FOR_S4=false
CURRENT_WALL_CLOCK_WAIT_REQUIRED=false
CURRENT_TASK8_TASK9_LEGACY_FORECAST_CHAIN_REQUIRED=false
```

The lawful evaluation boundary is: fit only from historical TRAIN, evaluate
against held-out historical VALIDATION outcomes, and keep TEST sealed. A
historical cutoff/horizon may be derived deterministically from the governed
split and target dates. It must not use validation target values as features,
TEST values, or post-cutoff features. A retained historical production forecast
row is not a prerequisite for this offline evaluation.

## Frozen data authority

```text
SOURCE=SOURCE_002
MATERIALIZED_DATASET_IDENTITY=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_ROWS=16224
TRAIN_CONTENT_SHA256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
VALIDATION_ROWS=8006
VALIDATION_CONTENT_SHA256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
TEST_REMAINS_SEALED=true
```

## Plan versioning

The prior plan remains immutable historical authority:

```text
EXPERIMENT_PLAN_V1=v0.3-experiment-plan-v1
EXPERIMENT_PLAN_V1_HASH=9e223a02a1b38c028c230a45eb1fa8323f3c2247bb85e7b439f3351e51042500
EXPERIMENT_PLAN_V1_MUTATED_IN_PLACE=false
```

This correction freezes a new canonical object:

```text
EXPERIMENT_PLAN_V2=v0.3-experiment-plan-v2
EXPERIMENT_PLAN_V2_HASH=c2bfab4ec38b4ca640f62d061494961c5b49afe5b52fa675326aa80fdf5f8ad9
EXPERIMENT_PLAN_V2_HISTORICAL_DATA_ONLY=true
EXPERIMENT_PLAN_V2_REAL_PROSPECTIVE_AUTHORITY_REQUIRED=false
EXPERIMENT_PLAN_V2_WEATHER_REQUIRED=false
EXPERIMENT_PLAN_V2_PRODUCTION_PLAN_REQUIRED=false
EXPERIMENT_PLAN_V2_TEST_SEALED=true
```

The V2 object preserves all eight IDs, their order, family, hypothesis, and
registered four-run limits. It adds a fail-closed historical-only eligibility
overlay; it is not an execution authorization.

## Candidate historical-only audit

| candidate | historical-only compatible | current V0.3 execution eligible | disposition |
| --- | --- | --- | --- |
| `01_parameter_calibration` | true | true | Historical parameter manifest still required; separately authorize before execution. |
| `02_quantile_calibration` | true | true | Historical quantile calibration can use TRAIN/VALIDATION; separately authorize before execution. |
| `03_phenology_offset` | true | true | Rebind the owner-selected training-time shift-bound contract to V2; do not reuse the V1 manifest. |
| `04_yield_parameter` | true | true | Historical parameter manifest still required; no current-season input is named. |
| `05_marketable_rate` | true | true | Historical parameter manifest still required; no current-season input is named. |
| `06_weather_response` | false | false | `DEFERRED_TO_FUTURE_PRODUCT_VERSION`; weather authority is outside the current input policy. |
| `07_harvest_efficiency` | true | true | Historical parameter manifest still required; no current-season input is named. |
| `08_residual_feature` | false | false | No V2-bound source-002-only feature manifest exists; current residual registry spans TASK9/WEATHER domains. |

“Eligible” means eligible for a future, separately authorized historical-only
manifest. It does not mean registered, preflighted, started, scored, selected,
or approved.

## Execution and TEST boundary

```text
CURRENT_S4_EXECUTION_STATUS=READY_FOR_SEPARATELY_AUTHORIZED_HISTORICAL_OFFLINE_CANDIDATE_VALIDATION
CURRENT_S4_EXECUTION_STATUS_CLASS=READY_FOR_HISTORICAL_OFFLINE_VALIDATION_PATH
CURRENT_S4_BLOCKER=NONE_AFTER_HISTORICAL_ONLY_REALIGNMENT
NEXT_VALIDATION_AUTHORITY_PATH=ACCEPTED_SOURCE_002_TRAIN_VALIDATION_OFFLINE
CURRENT_V2_BOUND_EXECUTION_ADAPTER_IMPLEMENTED=false
SEPARATE_CANDIDATE_AUTHORIZATION_REQUIRED=true
CANDIDATE_EXECUTION_AUTHORIZED=false
VALIDATION_SCORING_PERFORMED=false
SELECTED_CANDIDATE_ID=NOT_ISSUED
MODEL_APPROVED_FOR_PILOT=false
```

The existing C03 manifest is V1-bound and must not be executed directly. A
future C03 task must create a V2-bound manifest and obtain separate
authorization. The current prospective retention/runtime work remains
reusable for a future online pilot, but it is not an S4 prerequisite.

```text
PILOT_RUNTIME_EXISTS=true
PILOT_RUNTIME_IS_CURRENT_S4_PREREQUISITE=false
REAL_SEASON_PILOT_DOES_NOT_BLOCK_CURRENT_S4_VALIDATION=true
PROSPECTIVE_POST_TEST_AUTHORITY_ONLY=false
WAITING_FOR_REAL_PROSPECTIVE_FORECAST_AUTHORITY=false
```

The preserved budget is:

```text
LEGACY_RECONCILED_VALIDATION_DEBIT=4
CANONICAL_STARTED_COUNT=0
EFFECTIVE_CONSUMED=4
REMAINING=28
BUDGET_DELTA=0
```

TEST remains sealed. No candidate, model, parameter, or metric execution was
performed by this correction.

See the machine-readable canonical plan and candidate audit in
`evidence/s4-historical-only-validation-path-realignment-r1.json` and the
execution reasoning in the companion workpaper.

```text
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S4_HISTORICAL_ONLY_REALIGNMENT_REVIEW
```
