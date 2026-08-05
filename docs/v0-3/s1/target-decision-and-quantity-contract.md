# S1 Target Decision and Quantity Contract

## Contract identity

```text
CONTRACT_ID=V0_3_S1_TARGET_AND_QUANTITY_CONTRACT
Q2C_AUTHORITY=docs/forecast-quality/q2c-physical-target-equivalence-contract.md
Q2C_AUTHORITY_STATUS=ACCEPTED_DESIGN_NOT_IMPLEMENTED
CURRENT_TARGET_DECISION=UNRESOLVED_PENDING_INDEPENDENT_REVIEW
PROPOSED_TARGET_DECISION=NOT_PROPOSED
```

This document fixes the decision procedure. It does not select a business
source and does not assert that a source satisfies the procedure.

## Existing forecast vocabulary

The existing forecast contract distinguishes the following quantities:

| Quantity | Meaning | S1 treatment |
| --- | --- | --- |
| `actual_harvest_quantity_kg` | Quantity physically picked from plants on the farm-local harvest business date. | Current observed-label candidate; must be evidenced by Q2C. |
| `effective_marketable_quantity_kg` | Post-pick quantity after the accepted marketability and post-harvest boundary. | Current core forecast output; not silently treated as observed farm-pick weight. |
| `factory_received_quantity_kg` | Quantity recorded at factory receipt. | Receipt proxy; cannot be substituted for the farm-pick target. |
| `model_harvested_marketable_quantity_kg` | Model-side harvested marketable quantity in the V0.1 forecast chain. | Candidate comparison quantity only; not an observed label. |

The current physical boundary is explicit:

```text
CURRENT_OBSERVED_LABEL=actual_harvest_quantity_kg
CURRENT_OBSERVED_LABEL_PHYSICAL_BOUNDARY=FARM_PICK
CURRENT_OBSERVED_LABEL_MEASUREMENT=OBSERVED_WEIGHT
CURRENT_OBSERVED_LABEL_UNIT=KG
CURRENT_CORE_FORECAST_OUTPUT=effective_marketable_quantity_kg
PHYSICAL_EQUIVALENCE_ASSUMED=false
SILENT_TARGET_SUBSTITUTION_ALLOWED=false
```

## Q2C six-dimensional decision matrix

Each dimension must be closed by evidence from the same source cohort and
attestation. A field name, model output, receipt row, or unsigned narrative is
not evidence of closure.

| Dimension | Required closure | Current status | Blocking condition |
| --- | --- | --- | --- |
| Physical event | `FARM_PICK` | `BLOCKED` | No formal source attestation supplied. |
| Quantity basis | `OBSERVED_WEIGHT` | `BLOCKED` | Weighing point and measurement authority not supplied. |
| Marketability boundary | Explicit all-picked versus marketable definition | `BLOCKED` | Business boundary and rejection rule not supplied. |
| Sorting boundary | Field, packhouse, and rejected-fruit rules | `BLOCKED` | Sorting stages and exclusions not supplied. |
| Post-harvest boundary | Loss, storage, transport, and receipt treatment | `BLOCKED` | Post-pick treatment is not evidenced. |
| Time and grain | Farm-local business date and canonical grain | `BLOCKED` | Source time authority, mapping, and cohort evidence not supplied. |

The canonical evaluation grain is fixed by the accepted Q2A/I7 and Q2C design:

```text
CANONICAL_EVALUATION_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
PLOT_SUPPORTED=false
```

`SUBFARM_OR_PLOT` in physical-source language does not authorize a plot-level
evaluation grain. If a source cannot map to the canonical grain, the result is
`BLOCKED_BY_GRAIN_OR_DATE_MISMATCH`.

## Allowed decision outcomes

The decision must use one of the Q2C outcomes:

```text
PROVEN_EXACT
PROVEN_AFTER_VERSIONED_TRANSFORMATION
BLOCKED_BY_MISSING_BUSINESS_ATTESTATION
BLOCKED_BY_SEMANTIC_MISMATCH
BLOCKED_BY_TRANSFORMATION_AUTHORITY
BLOCKED_BY_GRAIN_OR_DATE_MISMATCH
```

The currently applicable state is:

```text
CURRENT_Q2C_PHYSICAL_ALIGNMENT_STATUS=BLOCKED
CURRENT_Q2C_OUTCOME=BLOCKED_BY_MISSING_BUSINESS_ATTESTATION
```

The outcome must be recomputed from the accepted evidence package. It must not
be copied from the name of a source table or from a successful import.

## Candidate target paths

### Candidate A: observed farm-pick target

This path is eligible only when the source attestation proves `FARM_PICK`,
`OBSERVED_WEIGHT`, `KG`, farm-local harvest business date, the canonical grain,
and all marketability/sorting/post-harvest boundaries. It would bind
`actual_harvest_quantity_kg` directly.

```text
WHEN_Q2C_PROVEN_EXACT:
  TARGET_BINDING=OBSERVED_FARM_PICK_QUANTITY
  TARGET_TRANSFORMATION=NONE
```

The `WHEN_` block is conditional documentation, not a current decision.

### Candidate B: versioned Q2C transformation

This path is eligible only when the accepted source is not the target boundary
and an independently governed transformation authority defines the event/unit/
grain mapping, formula, parameter versions, scope, Decimal behavior, residual,
and deterministic transformation hash.

```text
WHEN_Q2C_PROVEN_AFTER_VERSIONED_TRANSFORMATION:
  TARGET_BINDING=VERSIONED_Q2C_TRANSFORMATION
  TARGET_TRANSFORMATION=VERSIONED_AND_HASHED
```

No universal conversion is assumed. Without transformation authority the path
is `BLOCKED_BY_TRANSFORMATION_AUTHORITY`.

## Fail-closed rules

- `factory_received_quantity_kg` must never be used as a silent farm-pick
  target.
- Missing observations remain missing; they are not converted to zero.
- A quantity that is not computably mapped has a null result and a non-empty
  reason, not a numeric placeholder.
- Decimal values follow the authoritative S1/S3 precision and rounding rules;
  binary floating-point aggregation is not a target contract.
- No target decision is valid until the attestation, source cohort, mapping,
  visibility, and independent review records are complete.

## Acceptance prerequisites

```text
S1_ACCEPTANCE_REQUIRES_EXACT_OR_VERSIONED_Q2C_OUTCOME=true
S1_ACCEPTANCE_REQUIRES_NO_SILENT_TARGET_SUBSTITUTION=true
S1_ACCEPTANCE_REQUIRES_CANONICAL_GRAIN_MATCH=true
S1_ACCEPTANCE_REQUIRES_MEASUREMENT_UNIT_AND_DECIMAL_POLICY=true
S1_ACCEPTANCE_REQUIRES_INDEPENDENT_REVIEW=true
```

Until these requirements are met, `PROPOSED_TARGET_DECISION=NOT_PROPOSED` and
`CURRENT_S1_TARGET_DECISION=UNRESOLVED_PENDING_INDEPENDENT_REVIEW` remain in
force.
