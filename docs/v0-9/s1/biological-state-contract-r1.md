# V0.9-S1 Biological State Contract

**Contract:** `BIOLOGICAL_STATE_CONTRACT_VERSION=V0_9_S1_R1`  
**Scientific authority:** V0.9-S0 only; pinned by `s1-biological-state-and-management-event-contract-r1.json`.  
**Status:** structural contract only; not a calibrated or executable biological model.

## 1. Purpose and non-goals

This contract gives biological state, observations, derived values, latent states, management events, environment drivers, parameters, priors, business inputs, and model outputs distinct meanings and storage roles. A value must not be moved between these roles without an explicit transformation and provenance record.

This contract does not assert that the project currently observes any field, choose a proxy for deployment, estimate a parameter, or define a yield response equation. Enterprise availability is S2 scope. Parameter identifiability and calibration are later scope.

## 2. Semantic classes

| Class | Meaning | Contract rule |
|---|---|---|
| `BIOLOGICAL_STATE` | Plant/process condition at a time or over a declared interval | State is not inferred from one environmental exposure unless a versioned rule and provenance exist. |
| `OBSERVED_VARIABLE` | Direct measurement or explicitly recorded observation | Preserve timestamp, unit, method, scope, source, and quality. |
| `DERIVED_VARIABLE` | Deterministic transformation of named observations | Store formula/version, input lineage, unit, and missingness; do not disguise as direct observation. |
| `LATENT_STATE` | Biologically meaningful but not directly observed state | Keep nullable/unbound; never fabricate precision. |
| `MANAGEMENT_EVENT` | Dated intervention with target, scope, intensity representation, source, and authority | An event changes eligible state pathways; it is not itself a state or a yield multiplier. |
| `ENVIRONMENT_DRIVER` | Time-indexed environment input | Preserve source priority and QC; do not substitute nearest weather silently for sensor observations. |
| `MODEL_PARAMETER` | Versioned numerical or categorical value used by a model | Must carry authority, applicability scope, calibration status, and hash. |
| `LITERATURE_PRIOR` | Literature-observed value or candidate prior | Not a production parameter; no implicit promotion. |
| `BUSINESS_INPUT` | User/business-confirmed operational fact or scope | Must carry its own authority and scope; not inferred from literature. |
| `MODEL_OUTPUT` | Explicit output of a versioned engine | Keep biological maturity output separate from harvest and arrival outputs. |

`chill_accumulation` is an `ENVIRONMENT_DRIVER`/`DERIVED_VARIABLE`; `DORMANCY_RELEASED` is a `BIOLOGICAL_STATE`. Flower number, effective flower load, fruit number, crop load, mature quantity, harvested quantity, and arrival quantity are distinct quantities and grains.

## 3. PlantState

`PlantState(t)` is a versioned container for the declared farm/subfarm/cultivar scope at an observation time. The canonical fields and metadata are in `biological-state-registry-r1.json`. State field definitions below specify semantic meaning, unit, nullability, authority role, observability class, production-system applicability, and cultivar dependence.

| Group | Contract fields | Meaning / boundary |
|---|---|---|
| Structural | `plant_density`, `cane_age_structure`, `productive_shoot_density`, `fruiting_wood_index`, `pruning_state` | Plant population, cane-age distribution, productive shoots, declared fruiting-wood measure, and event-derived pruning condition. `fruiting_wood_index` has no universal scale. |
| Vegetative | `leaf_area_proxy`, `canopy_retention_ratio`, `shoot_growth_state`, `vegetative_vigor_proxy`, `carbohydrate_reserve_proxy` | Canopy/leaf and growth condition. A proxy must name representation and method. The reserve proxy is latent unless directly assayed. |
| Reproductive | `flower_bud_density`, `flower_number_proxy`, `effective_flower_load`, `pollination_state`, `fruit_set_ratio`, `fruit_number_proxy`, `crop_load_index` | Bud count, flower count, effective reproductive load, pollination/fertilization status, set ratio, fruit count representation, and declared crop-load index are distinct. None is interchangeable with season yield. |
| Phenology | `phenology_stage`, `dormancy_state`, `chill_accumulation`, `forcing_accumulation`, `bloom_progress` | State, exposure/derived accumulations, and bloom observation. Accumulations never themselves assert a biological transition. |
| Fruit | `green_fruit_quantity_proxy`, `color_break_quantity_proxy`, `mean_berry_weight_proxy`, `berry_size_proxy`, `ripe_quantity` | Stage-scoped cohort quantities and sampled fruit traits. Every value carries a declared count/mass/index representation, unit, cohort, maturity stage, and method. |

All fields are nullable unless a scope-specific collection contract declares otherwise. Missing, not measured, not applicable, unresolved, and measured zero are distinct statuses. Field values never imply that a full plant, member, or season is covered.

## 4. ProductionSystem

The registry freezes three distinct systems:

* `DECIDUOUS_NATURAL`: deciduous adaptation/dormancy, cultivar-bound chill assessment, dormancy release, then forcing and bud development.
* `DECIDUOUS_FORCING`: deciduous dormancy/chill path plus explicitly dated forcing/greenhouse events and measured or sourced microclimate. Forcing is not a calendar offset.
* `EVERGREEN`: independent leaf-retention/continued-activity path. It may bypass a complete dormancy/chill-satisfied sequence where S0 evidence supports that system, but it is **not** encoded as `chill_requirement=0`. Dormancy/chill status may remain unknown or latent.

System assignment is an explicit business/observed input with source and validity scope. It is not inferred from latitude, an early harvest date, cultivar name alone, or an observed missing chill value. System-specific allowed paths and invalid transitions are machine-listed in the registry and state-machine document.

## 5. BloomCohort and FruitCohort

`BloomCohort` is the lineage-bearing reproductive event/cohort. It records `cohort_id`, `origin_date` or interval, farm/subfarm/cultivar, production system, flower and effective-flower quantities, representation (`ABSOLUTE_COUNT`, `AREA_NORMALIZED_INDEX`, `PROPORTIONAL_SHARE`, `OBSERVATION_SCORE`, or `LATENT_ESTIMATE`), pollination state, fruit-set ratio, resulting fruit quantity representation, source reference, and authority hash. A cohort can exist without an absolute flower count.

`FruitCohort` must reference its `origin_bloom_cohort_id`. It records fruit-set date/interval, quantity representation, development state, thermal age with a declared thermal model and units, source-sink modifier reference (not an unapproved formula), expected maturity distribution, ripe quantity representation, authority, and provenance. Expected maturity distribution is a future model output only when emitted by a versioned model; it is not a literature default.

## 6. InterSeasonState

`InterSeasonState` carries `postharvest_vigor_proxy`, `carbohydrate_reserve_proxy`, and `next_season_flower_bud_potential` from season N to N+1. These may be `LATENT`; their values remain nullable and must not be manufactured by summing member areas, yields, or literature coefficients. Links preserve prior-season crop-load and plant-state lineage.

## 7. SourceSinkState

`SourceSinkState` contains `source_capacity_proxy`, `sink_demand_proxy`, and `source_sink_balance_index`. Source capacity is not leaf area alone; sink demand is not fruit number alone. These are composite biological concepts with method-specific proxies. S1 authorizes no exact ratio/equation (`SOURCE_SINK_EXACT_FORMULA=UNBOUND`, `SOURCE_SINK_STATUS=SIMPLIFIED_PROXY_CONTRACT`). Every proxy declares representation/version and scope; missing components do not become zero.

## 8. EnvironmentInput and observability

Supported input variables are hourly/datetime `air_temperature`, `min_temperature`, `max_temperature`, `relative_humidity`, `root_zone_temperature`, and `radiation_or_light_proxy`; optional moisture, EC, and irrigation may be represented without being required by this contract. Each observation stores `timestamp`, `source`, `source_priority`, `quality_status`, `missing_status`, and `unit`.

Source precedence is `GREENHOUSE_SENSOR > FARM_LOCAL_SENSOR > EXTERNAL_WEATHER_SOURCE`. Precedence chooses among valid observations for the same variable/scope/time; it does not authorize filling a gap with a lower-priority source without an explicit derivation record. `DIRECT_OBSERVATION`, `DERIVED`, `PROXY`, `LATENT`, and `UNBOUND` describe theoretical observability class only. They do not claim current enterprise availability.

## 9. Evidence admission and limits

S1 admits the 24 S0 mechanisms already marked ready for a state, event, causal, interface, or explicitly abstract contract. `ESTABLISHED_MECHANISM` supports qualitative state edges only; `SUPPORTED_BUT_CONTEXT_DEPENDENT` edges retain cultivar/system/climate scope; accepted `PLAUSIBLE_MODEL_ABSTRACTION` entries are labeled as abstractions, not facts. The six S0 not-ready mechanisms remain quarantined; see the evidence JSON and causal-edge registry.

No S1 contract supplies exact pruning yield multipliers, thinning-to-weight effects, chill-to-bloom dates, GDD-to-ripe dates, source/sink drop percentages, or crop-load carryover penalties. Those numerical mappings remain unbound.

## 10. Version and serialization

`BIOLOGICAL_STATE_CONTRACT_VERSION=V0_9_S1_R1`. Registry serialization is UTF-8 JSON, deterministic field/key ordering, finite JSON values only, LF line endings, and a final newline. The parameter hash rule is defined in `parameter-authority-contract-r1.md`. A change to a field meaning, unit, path applicability, or lineage requirement requires a new contract revision; it must not silently rewrite S0 evidence.
