# V0.3 S4 sparse-horizon guardrail alignment R1

This package adds a versioned V3 selection policy for the frozen SOURCE-002
sparse historical evaluation surface. It does not alter the replayable V1 or
V2 policy preimages, recompute C04 parameters, create a durable STARTED event,
score VALIDATION, or access TEST.

## Frozen V3 authority

```text
TASK_ID=V0_3_S4_SPARSE_HORIZON_GUARDRAIL_ALIGNMENT_R1
BASE_MAIN_SHA=f9f9c0644c73a4f2d1c28eb33241b898b44f6ead
EXPERIMENT_PLAN_VERSION=v0.3-experiment-plan-v2
EXPERIMENT_PLAN_HASH=c2bfab4ec38b4ca640f62d061494961c5b49afe5b52fa675326aa80fdf5f8ad9
V3_GUARDRAIL_POLICY_VERSION=v0.3-s4-guardrail-policy-v3-sparse-horizon
V3_GUARDRAIL_POLICY_HASH=004be89a726ea4afd90ac895ea10f885f749b2f222e0fca5a67d57ba4e2bd3e0
V3_EVALUATION_SURFACE_ID=V0_3_S4_SOURCE002_SPARSE_HORIZON_7_14_21_V1
FORECAST_HORIZONS=7,14,21
COMPLETE_DAILY_ROWSET_AUTHORITY=false
MISSING_DAY_ZERO_FILL=false
```

V3 accepts only the exact surface identity, exact ordered horizons, an
explicitly incomplete daily-rowset authority, and an explicit prohibition on
zero-filling. Missing or mismatched surface metadata blocks eligibility.

## Selection policy

The sparse surface requires the following selection evidence:

* `daily_wape` is lower-is-better and must be strictly less than the
  incumbent; equality is `NOT_IMPROVED` and fails.
* `daily_mae` is lower-is-better and must be less than or equal to the
  incumbent.
* P80/P90 distance-to-nominal, coverage ratio, included canonical-group
  coverage, required breakdown axes, minimum comparable rows, and
  `no_silent_exclusion` remain mandatory.

The three complete-window metrics remain honest evidence:

```text
cumulative_absolute_error_kg=NOT_COMPUTABLE
single_day_peak_quantity_absolute_error_kg_q=NOT_COMPUTABLE
sustained_7day_quantity_absolute_error_kg_q=NOT_COMPUTABLE
reason=COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE
selection_blocking=false
diagnostic_only=true
```

This disposition is scoped only to the exact V3 sparse surface. It does not
change the metric contract, interpolate missing days, or weaken V1/V2 policy
replay.

## C04 rebinding

Candidate 04 keeps the already reviewed TRAIN-only values and derivation:

```text
C04_PARAMETER_DERIVATION_POLICY=TRAIN_ONLY_LATEST_LEGAL_PSEUDO_CUTOFF_GROUP_HORIZON_AMPLITUDE_CALIBRATION_V3
C04_CALIBRATION_CUTOFF=2026-01-09
C04_PARAMETER_VALUES=3.802757,4.961884,5.182238,4.152099
C04_PARAMETER_VALUES_UNCHANGED=true
C04_PARAMETER_DERIVATION_POLICY_UNCHANGED=true
C04_CALIBRATION_CUTOFF_UNCHANGED=true
```

Only the current execution binding changes from the superseded V2 manifest to:

```text
C04_PARAMETER_MANIFEST_VERSION=v0.3-s4-c04-yield-parameter-manifest-v2
C04_PARAMETER_MANIFEST_HASH=1e3433b9216f8ebe63db44ba0bc1353e1d4664cef3c1cc3f2a57bb794fe280ee
C04_CODE_COMMIT_BINDING=d219a3d99da3a1766ace75dcbf6a99b82d66f2a4
C04_GUARDRAIL_POLICY_VERSION=v0.3-s4-guardrail-policy-v3-sparse-horizon
C04_GUARDRAIL_POLICY_HASH=004be89a726ea4afd90ac895ea10f885f749b2f222e0fca5a67d57ba4e2bd3e0
C04_EVALUATION_SURFACE_ID=V0_3_S4_SOURCE002_SPARSE_HORIZON_7_14_21_V1
```

The prior V2 manifest remains historical audit evidence; it is not the current
execution manifest. This rebinding still does not authorize a C04 run.

## Execution and budget boundary

V3 dispatch is explicit in both the pure execution gate and the durable
preflight request. C01 remains forbidden, and C06/C08 remain blocked. Gate
readiness is pure and does not append an event or call a scorer.

```text
LEGACY_RECONCILED_VALIDATION_DEBIT=4
CANONICAL_STARTED_COUNT=0
EFFECTIVE_CONSUMED=4
REMAINING=28
BUDGET_DELTA=0
EVALUATION_STARTED_CREATED=false
CANDIDATE_EXECUTION_PERFORMED=false
VALIDATION_SCORING_PERFORMED=false
TEST_ACCESS_REQUESTED=false
TEST_BYTES_READ=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The next action, if separately authorized, is a real C04 VALIDATION execution
review. This package itself is only policy alignment and readiness evidence.
