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
| `actual_harvest_quantity_kg` | V0.3 recorded-business-label quantity: governed marketable net weight recorded at the first valid field scan-and-weigh event for the harvest business date. | Current observed-label candidate; must be evidenced by Q2C/source authority. It is not a reconstructed pre-weigh theoretical plant-removal weight. |
| `effective_marketable_quantity_kg` | Post-pick quantity after the accepted marketability and post-harvest boundary. | Current core forecast output; not silently treated as observed farm-pick weight. |
| `factory_received_quantity_kg` | Quantity recorded at factory receipt. | Receipt proxy; cannot be substituted for the governed field scan-weigh label. |
| `model_harvested_marketable_quantity_kg` | Model-side harvested marketable quantity in the V0.1 forecast chain. | Candidate comparison quantity only; not an observed label. |

The historical Q2C vocabulary remains available for compatibility, but the
V0.3 recorded-label profile narrows the current actual-label boundary to the
governed measurement record. This profile does not rewrite the accepted
historical Q2C design in `docs/forecast-quality/q2c-physical-target-
equivalence-contract.md`.

```text
CURRENT_OBSERVED_LABEL=actual_harvest_quantity_kg
HISTORICAL_Q2C_LABEL_PHYSICAL_BOUNDARY=FARM_PICK
RECORDED_LABEL_BUSINESS_BOUNDARY_EXPLICIT=true
V0_3_ACTUAL_LABEL_MODE=RECORDED_BUSINESS_LABEL
V0_3_ACTUAL_LABEL_BUSINESS_EVENT=HARVEST
V0_3_ACTUAL_LABEL_MEASUREMENT_EVENT=VALID_FIELD_SCAN_WEIGH_RECORD
V0_3_ACTUAL_LABEL_MEASUREMENT_BOUNDARY=RECORDED_VALID_FIELD_SCAN_WEIGH
V0_3_ACTUAL_LABEL_QUANTITY_BASIS=RECORDED_MARKETABLE_NET_WEIGHT
V0_3_ACTUAL_LABEL_SOURCE_OF_TRUTH=GOVERNED_SCAN_WEIGHT_RECORD
V0_3_ACTUAL_LABEL_MEASUREMENT=RECORDED_MARKETABLE_NET_WEIGHT
V0_3_ACTUAL_LABEL_PHYSICAL_BOUNDARY=RECORDED_VALID_FIELD_SCAN_WEIGH
V0_3_ACTUAL_LABEL_UNIT=KG
CURRENT_CORE_FORECAST_OUTPUT=effective_marketable_quantity_kg
PHYSICAL_EQUIVALENCE_ASSUMED=false
SILENT_TARGET_SUBSTITUTION_ALLOWED=false
RECORDED_NET_WEIGHT_IS_BUSINESS_TRUTH=true
PRE_MEASUREMENT_WEIGHT_RECONSTRUCTION_REQUIRED=false
PRE_WEIGH_TRANSPORT_REQUIRED_FOR_LABEL_ELIGIBILITY=false
PRE_WEIGH_STORAGE_REQUIRED_FOR_LABEL_ELIGIBILITY=false
PRE_WEIGH_POSTHARVEST_LOSS_REQUIRED_FOR_LABEL_ELIGIBILITY=false
TARE_METHOD_REQUIRED_FOR_LABEL_ELIGIBILITY=false
SCALE_DEVICE_PRECISION_REQUIRED_FOR_LABEL_ELIGIBILITY=false
SCALE_CALIBRATION_AUTHORITY_REQUIRED_FOR_LABEL_ELIGIBILITY=false
V0_3_RECORDED_LABEL_PROFILE_OVERRIDES_STRICT_PRE_WEIGH_RECONSTRUCTION=true
```

For this V0.3 profile, actual label means the formally recorded marketable
net weight at the first valid scan-and-weigh event at the field harvest point.
Transport, storage, natural loss, post-harvest process history, and tare
method before that governed record are upstream history of the recorded
business label; they are not reconstructed into a different label value.
Missing metrology details remain optional provenance evidence rather than hard
prerequisites for recorded-label eligibility. `NOT_REQUIRED_FOR_V0_3_RECORDED_
LABEL_ELIGIBILITY` means that a field is not required for this label
eligibility decision; it does not assert `FALSE`, `ZERO`, or that the process
or device detail does not exist.

This boundary correction does not select a forecast-side target, prove exact
equivalence to `effective_marketable_quantity_kg` or
`model_harvested_marketable_quantity_kg`, issue Q2C acceptance, or change the
canonical gate status.

## Q2C six-dimensional decision matrix

Each dimension must be closed by evidence from the same source cohort and
attestation. A field name, model output, receipt row, or unsigned narrative is
not evidence of closure.

| Dimension | Required closure | Current status | Blocking condition |
| --- | --- | --- | --- |
| Physical event | V0.3 `HARVEST` business event measured by a governed valid field scan/weigh record | `BLOCKED` | Formal source attestation and independent review are not supplied. |
| Quantity basis | V0.3 `RECORDED_MARKETABLE_NET_WEIGHT` in `KG` | `BLOCKED` | Formal source attestation and target decision are not issued. |
| Marketability boundary | Explicit all-picked versus marketable definition | `BLOCKED` | Business boundary and rejection rule not supplied. |
| Sorting boundary | Field, packhouse, and rejected-fruit rules | `BLOCKED` | Sorting stages and exclusions not supplied. |
| Post-harvest boundary | Recorded-label profile treats pre-record upstream history as part of the recorded label; no retroactive factory adjustment | `BLOCKED` | Formal source attestation, coverage and governance are not supplied; pre-weigh reconstruction is not a label-eligibility prerequisite. |
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

## V0.3 recorded-label profile closure boundary

The following six-dimensional interpretation applies only to the V0.3
`RECORDED_BUSINESS_LABEL` profile:

```text
BUSINESS_EVENT=HARVEST
RECORDED_LABEL_MEASUREMENT_EVENT=VALID_FIELD_SCAN_WEIGH_RECORD
RECORDED_LABEL_QUANTITY=RECORDED_MARKETABLE_NET_WEIGHT
RECORDED_LABEL_UNIT=KG
RECORDED_LABEL_SOURCE_OF_TRUTH=GOVERNED_SCAN_WEIGHT_RECORD
PRE_WEIGH_TRANSPORT_LOSS_RECONSTRUCTION_REQUIRED=false
PRE_WEIGH_STORAGE_LOSS_RECONSTRUCTION_REQUIRED=false
PRE_WEIGH_POSTHARVEST_LOSS_RECONSTRUCTION_REQUIRED=false
TARE_METHOD_RECONSTRUCTION_REQUIRED=false
SCALE_DEVICE_PRECISION_REQUIRED_FOR_LABEL_ELIGIBILITY=false
SCALE_CALIBRATION_AUTHORITY_REQUIRED_FOR_LABEL_ELIGIBILITY=false
```

Eligibility therefore requires evidence that the record is governed, is a
formal marketable-fruit net quantity in kilograms, has a determinable
business date and canonical grain, and has frozen source identity, coverage,
visibility and governance. It does not require reconstructing a theoretical
weight at plant removal before the scan-weigh record.

## Candidate target paths

### Candidate A: observed target (not selected by this correction)

This path remains a conditional target path and is not selected by this
boundary correction. Its exact target binding requires a separately reviewed
Q2C decision over the V0.3 recorded-label profile, including `KG`, farm-local
harvest business date, canonical grain, and marketability/sorting boundaries.
It would bind `actual_harvest_quantity_kg` directly only after that decision.

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
V0_3_RECORDED_LABEL_PROFILE_REQUIRES_GOVERNED_SCAN_WEIGHT_RECORD=true
V0_3_RECORDED_LABEL_PROFILE_REQUIRES_PRE_WEIGH_RECONSTRUCTION=false
FORECAST_SIDE_TARGET_BINDING_CHANGED=false
```

Until these requirements are met, `PROPOSED_TARGET_DECISION=NOT_PROPOSED` and
`CURRENT_S1_TARGET_DECISION=UNRESOLVED_PENDING_INDEPENDENT_REVIEW` remain in
force.
