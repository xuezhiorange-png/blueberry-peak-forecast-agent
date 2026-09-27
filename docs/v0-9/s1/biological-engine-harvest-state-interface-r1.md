# V0.9-S1 Biological Engine ↔ Harvest State Interface

**Interface version:** `V0_9_S1_R1`  
**Boundary:** biological maturity is not harvesting, and harvesting is not factory arrival.

## 1. Ownership

The biological engine owns plant phenology, bloom/fruit cohort lineage, fruit development state, and newly mature fruit supply. It may emit `daily_newly_mature_quantity` or a versioned quantile/distribution representation of that quantity.

The existing Harvest State engine owns mature-fruit inventory and operational harvest flow. It consumes the biological output and combines it with opening mature inventory, mature loss, effective harvest capacity, and its own authorized state to produce harvested quantity and closing mature inventory.

```text
BIOLOGICAL_ENGINE
  → daily_newly_mature_quantity (or declared distribution)
  → HARVEST_STATE_ENGINE
  → harvested_quantity + closing_mature_inventory
```

Factory arrival, routing, factory capacity, and harvest scheduling are downstream/out of scope. S1 does not modify the existing Harvest State implementation.

## 2. Biological output contract

Each output carries `output_id`, `date_or_interval`, `farm_id`, `subfarm_id`, `cultivar_id`, `production_system`, `quantity_value`, `quantity_unit`, `quantity_representation`, `cohort_lineage`, `state_as_of`, `model_or_observation_authority`, `source_signature`, `parameter_version_refs`, and `quality_status`.

The preferred physical unit is kg per declared scope per calendar day when supported by source/calibration authority. An index/count representation is allowed only when explicitly typed and cannot be passed to a kg inventory ledger without an authorized conversion. Unknown, partial, or latent quantities remain marked as such; they are not zero-filled by this interface.

The biological output is newly mature supply for a date/window. It is not total mature inventory, harvested quantity, arrival quantity, or a production plan.

## 3. Harvest State input/output boundary

Harvest State accepts the typed biological output plus its own state and operational inputs. Its owned state includes:

* opening mature inventory;
* mature-fruit loss;
* effective harvest capacity;
* harvested quantity; and
* closing mature inventory.

No biological contract may set `effective_harvest_capacity`, scheduling, routing, opening inventory, or actual harvest. No harvest-state result may be written back as a biological maturity observation without a separate evidence mapping.

## 4. Reconciliation and provenance

Implementations must preserve cohort/date/scope lineage and distinguish observed, derived, latent, and model-output values. If the biological output is a distribution, the consuming engine must declare which summary or scenario it uses. Daily summation/reconciliation rules, losses, and capacity constraints belong to Harvest State's own frozen contract, not to this biological interface.

S0 claim `C026` supports the architectural separation as an accepted plausible model abstraction. This interface is contract-ready, not evidence that the present engine already implements or validates it.

## 5. Versioning

`BIOLOGICAL_HARVEST_INTERFACE_VERSION=V0_9_S1_R1`. Any change in unit/grain, newly-mature definition, lineage, or ownership boundary requires an interface revision and compatibility review.
