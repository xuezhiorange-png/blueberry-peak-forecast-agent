# V0.9-S1 Management Event Contract

**Contract:** `MANAGEMENT_EVENT_CONTRACT_VERSION=V0_9_S1_R1`  
**Scientific authority:** pinned V0.9-S0 claims only.  
**Status:** event vocabulary and causal targets; no intervention-response coefficients.

## 1. Generic event record

Every `ManagementEvent` uses the fields below. The full enumerations and event-specific targets are machine-readable in `management-event-registry-r1.json`.

| Field | Contract |
|---|---|
| `event_id` | Stable unique identifier; immutable after issuance. |
| `event_type` | One canonical registered type. Do not collapse pruning and reproductive thinning. |
| `event_date` | Local civil date when only date precision is known; no invented time. |
| `start_datetime`, `end_datetime` | Optional timezone-aware interval; both absent for a date-only event. |
| `farm_id`, `subfarm_id`, `cultivar_id` | Explicit scope identifiers; nullable only when source grain is broader and scope is recorded as unresolved. |
| `production_system` | One of the registered production systems or `UNBOUND`; never inferred from event timing. |
| `target_state` | Registered state/driver target(s); no free-form yield target. |
| `intensity_mode` | `OBSERVED_VALUE`, `BUSINESS_GRADE`, `PRESENCE_ONLY`, or `PLANNED_VALUE`. |
| `intensity_value`, `intensity_unit` | Nullable. Numeric intensity requires a source, unit, method, denominator, and scope. `LIGHT/MODERATE/HEAVY` is a business grade, not a universal numeric scale. |
| `source_type`, `source_reference` | Origin and stable evidence pointer. |
| `authority_level` | Explicit authority status; not a model confidence score. |
| `observed_or_planned` | `OBSERVED`, `PLANNED`, or `UNKNOWN`; planned work is not actual history. |
| `notes` | Optional non-authoritative context; must not override typed fields. |

An event record with missing intensity remains a valid event if its type/date/scope/source are supported; it does not acquire an assumed intensity. Event intervals must be ordered, and quantities must identify whether the measure is per plant, area, row, or whole scoped unit.

## 2. Registered event types and targets

| Event type | Primary target(s) | Not permitted as a direct shortcut |
|---|---|---|
| `PRUNING` | `fruiting_wood`, `flower_bud_potential`, `canopy_structure`, `future_shoot_growth` | `yield *= pruning_factor` |
| `POSTHARVEST_PRUNING` | Same structural targets; postharvest timing retained | Fixed next-season penalty |
| `SUMMER_PRUNING` | Canopy structure, shoot growth, light environment | Fixed ripening-date offset |
| `WINTER_PRUNING` | Fruiting wood, potential buds, canopy structure | Universal crop-load ratio |
| `DORMANT_PRUNING` | Dormant-period structural and reproductive potential | Assumption that all systems have dormancy |
| `CANE_RENEWAL` | Cane-age structure, future productive shoots, fruiting wood | Immediate yield multiplier |
| `FRUITING_WOOD_THINNING` | Fruiting wood and potential reproductive sites | Flower-thinning semantics |
| `FLOWER_BUD_THINNING` | Flower-bud potential / reproductive sink | Removal of vegetative structure unless separately recorded |
| `FLOWER_REMOVAL` | Effective flower load | Pruning / fruiting-wood removal |
| `FLOWER_THINNING` | Effective flower load | Direct proportional yield reduction |
| `FRUITLET_THINNING` | Young fruit load / sink demand | Flower-bud or canopy change by implication |
| `FRUIT_THINNING` | Fruit number / sink demand | Exact berry-weight increase without calibration |
| `GREENHOUSE_CLOSE` | Environment state; temperature/humidity/light exposure | `HARVEST_DATE_SHIFT` |
| `GREENHOUSE_OPEN` | Environment state and exposure interval | Direct harvest output |
| `HEATING_START` | Environment/forcing driver | Assumed chill satisfaction |
| `HEATING_STOP` | Environment/forcing driver | Fixed end of phenology |
| `DORMANCY_BREAK_TREATMENT` | Dormancy/phenology pathway as a distinct intervention | Equivalent-to-chill accumulation or guaranteed release |
| `SHADE_START` | Radiation/light and canopy environment | Direct yield scalar |
| `SHADE_STOP` | Radiation/light and canopy environment | Automatic recovery assumption |
| `SHADE_APPLICATION` | Radiation/light environment | Same semantics as heating or dormancy treatment |
| `LEAF_RETENTION_MANAGEMENT` | Canopy-retention/vegetative state | `EVERGREEN` system assignment by itself |
| `DEFOLIATION` | Canopy retention and vegetative state | Assumed dormancy or zero chill requirement |
| `POLLINATION_WINDOW_START` | Pollination-state observation window | Successful fertilization assertion |
| `POLLINATION_WINDOW_END` | Pollination-state observation window | Fruit-set assertion |
| `POLLINATION_START` | Pollination state / event window | Bee-optimization decision |
| `POLLINATION_END` | Pollination state / event window | Fruit-set assertion |
| `POLLINATOR_INTRODUCTION` | Pollination opportunity and event history | Pollination success inferred from presence alone |
| `IRRIGATION_STRESS` | Water/environment state and source capacity context | Exact fruit-drop or yield coefficient |
| `NUTRITION_INTERVENTION` | Nutritional/environment context | Exact source-capacity or yield coefficient |

The event registry declares each type's S0 claim IDs, applicable production systems, intensity policy, and `numeric_response_authorized=false`. A specific event can target more than one state, but each target is listed and traceable. Management events are not an extra causal route to a model output unless an admitted, versioned state transition represents that route.

## 3. Pruning is a structural intervention

Pruning may remove fruiting wood and potential buds while changing cane-age distribution, productive shoots, canopy structure/light, and later vegetative renewal. Record event timing, type, target, scope, intensity representation, and—if actually measured—fruiting-wood removed ratio and bud removed ratio. Ratios require an explicit denominator and observation protocol.

The S0 evidence supports distinct structural and reproductive pathways, not a universal signed yield effect. Timing-specific cross-year effect sizes are quarantined under claim `C005`; no pruning multiplier is admitted.

Optional measured attributes are `fruiting_wood_removed_ratio` and `flower_bud_removed_ratio`. Each requires an explicit before/after denominator, sample/scope, method, unit (`ratio_0_1`), and source; the absence of either is null/unknown, not zero.

## 4. Flower and fruit thinning are sink interventions

Flower-bud thinning, flower removal, flower thinning, fruitlet thinning, and fruit thinning remain separately typed by the developmental stage at intervention. They primarily change reproductive sink/load. S0 supports separating these from pruning; any downstream compensation in berry weight, size, quality, or maturation remains cultivar/load/context dependent and has no S1 coefficient.

## 5. Protected cultivation and pollination

Greenhouse closure/opening, heating, shading, defoliation, and leaf-retention management are events with time intervals and source lineage. They first affect environment, phenology, or vegetative state; the event itself never sets a harvest date.

Pollination window and pollinator introduction are event records. Presence or activity is not equivalent to compatible pollen transfer, fertilization, seed set, or fruit set. Those are separate observed/derived/latent states with separate evidence.

## 6. Event authority and lifecycle

An observed event and a planned event are never interchangeable. Direct observation, business confirmation, user report, derived event, and unverified note are distinct source/authority classes. Later calibration may estimate effect parameters but cannot retroactively change the event itself. Literature values remain priors and never become event values or production parameters automatically.

## 7. Versioning

`MANAGEMENT_EVENT_CONTRACT_VERSION=V0_9_S1_R1`. The registry's stable `event_type` IDs and target semantics are frozen for this revision. New event types, changed target semantics, or a new intensity scale require a new revision and explicit migration; no silent aliases are permitted.
