# Workpaper — sparse horizon guardrail alignment R1

## Scope

The accepted V2 historical surface has 688 sparse target rows at horizons 7,
14, and 21. It is not a complete continuous daily curve. The previous V2
guardrail aggregation treated complete-window metrics as selection-blocking,
which made every lawful sparse candidate fail closed even when all sparse
selection evidence was valid.

This correction introduces a separate V3 policy. The V1 and V2 canonical
preimages and hashes are intentionally untouched:

```text
V1_GUARDRAIL_POLICY_HASH=74ecd47339572955e654cf61c38ee6b0546ba51a36e67f80f6ad4dd4519f1ff8
V2_GUARDRAIL_POLICY_HASH=65ad056b3085b7ff41d25e1a7a86b990ac0f837270d62f6fd84ce5938843c793
V3_GUARDRAIL_POLICY_HASH=004be89a726ea4afd90ac895ea10f885f749b2f222e0fca5a67d57ba4e2bd3e0
```

## V3 surface admission

The evaluator and gate require all of the following, with no defaults:

```text
V3_EVALUATION_SURFACE_ID=V0_3_S4_SOURCE002_SPARSE_HORIZON_7_14_21_V1
FORECAST_HORIZONS=(7,14,21)
COMPLETE_DAILY_ROWSET_AUTHORITY=false
MISSING_DAY_ZERO_FILL=false
```

Missing surface identity, a different surface identity, a different horizon
set, an ambiguous rowset flag, or a request to fill missing days is blocked.

## V3 guardrails

The required selection set is `daily_wape`, `daily_mae`, P80, P90, and the
existing coverage/data-quality gate. Primary WAPE remains strict improvement;
daily MAE remains zero-tolerance non-regression. All required breakdown axes,
minimum comparable rows, complete included-group coverage, zero missing-data
proportion, and no-silent-exclusion remain enforced.

The only non-blocking metrics are the three complete-window metrics below.
They are required as explicit paired `NOT_COMPUTABLE` diagnostics and are
never converted to zero:

```text
cumulative_absolute_error_kg
single_day_peak_quantity_absolute_error_kg_q
sustained_7day_quantity_absolute_error_kg_q
```

This is a selection-policy alignment, not metric fabrication. A sparse result
cannot claim a continuous daily curve, and no synthetic interpolation is
introduced.

## C04 binding

C04 is rebound to V3 without touching the approved parameter derivation:

```text
C04_PARAMETER_VALUES=3.802757,4.961884,5.182238,4.152099
C04_PARAMETER_DERIVATION_POLICY=TRAIN_ONLY_LATEST_LEGAL_PSEUDO_CUTOFF_GROUP_HORIZON_AMPLITUDE_CALIBRATION_V3
C04_CALIBRATION_CUTOFF=2026-01-09
C04_PARAMETER_MANIFEST_VERSION=v0.3-s4-c04-yield-parameter-manifest-v2
C04_PARAMETER_MANIFEST_HASH=1e3433b9216f8ebe63db44ba0bc1353e1d4664cef3c1cc3f2a57bb794fe280ee
C04_PARAMETER_VALUES_UNCHANGED=true
```

The implementation commit bound into that manifest is
`d219a3d99da3a1766ace75dcbf6a99b82d66f2a4`. The old V2 manifest hash
`555a8b53253c3bfce917b41ddac771f7df82e6add0f005fcd2c2b33e624be22f` remains
superseded audit history and is not used as the current execution binding.

## Safety checks performed

The synthetic suite proves deterministic V3 hashing, V1/V2 replay, exact
surface admission, sparse pass/fail/block cases, non-blocking diagnostic
metrics, zero-fill rejection, V3 gate routing, C01/C06/C08 restrictions, and
no-budget-mutation readiness. The C04 regression suite proves that the four
approved values and derivation remain unchanged and that its gate request now
contains the V3 policy and sparse surface identity.

No candidate execution, VALIDATION scoring, TEST read, or durable budget event
was performed.
