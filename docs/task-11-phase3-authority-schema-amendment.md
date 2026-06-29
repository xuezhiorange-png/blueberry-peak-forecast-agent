# Task 11 P0-6 - Historical Task 9 Authority Schema and Replay Contract Freeze

**Status**: Design under review. Implementation not started.

**Date**: 2026-06-29
**Repository**: `xuezhiorange-png/blueberry-peak-forecast-agent`
**Branch**: `codex/task-11-rolling-backtest-orchestration`
**Current baseline HEAD**: `b0bc11443e78e7d985e34364385ae016409293f5`
**Related PR / Issue**: PR #22 (Draft), Issue #21
**Accepted predecessor**: P0-5 review `4589381607`

---

## 1. Baseline

Task 11 Phase 3 already resolves historical Task 6, Task 7, and Task 8 inputs with typed availability rules and fail-closed integrity checks. Task 9 retrospective replay is still intentionally blocked because two loader paths remain authority-incomplete:

- `_load_capacity_inputs_typed()`
- `_load_task9_run_parameters_typed()`

At current HEAD, those loaders correctly return `task9_replay_input_incomplete` instead of inventing:

- capacity values
- run parameters
- holiday packages
- weather rules
- initial mature inventory
- mature inventory loss

This document freezes the historical authority contract required to unblock Task 9 replay later. It does **not** create migrations, ORM, repositories, or resolver code.

---

## 2. Current Gaps

### 2.1 Missing historical authority domains

The current schema has no independent replay authority for:

- capacity pool definitions as historical business objects
- daily capacity values
- harvest bucket anchor time
- harvest-to-arrival lag
- factory timezone authority
- versioned holiday calendar package
- versioned weather efficiency rule package
- initial mature inventory snapshot
- initial inventory cohorts
- mature inventory loss inputs

### 2.2 Downstream snapshots are not authority

The following **must not** be used as upstream authority:

- `HarvestStateRun.input_snapshot`
- `HarvestStateRun.resolved_parameter_snapshot`

Reason:

`Task 11 resolves Task 9 inputs -> Task 9 executes -> HarvestStateRun stores consumed/derived snapshots`

Reversing that path would create a circular authority chain and would allow downstream persisted output to masquerade as historical input provenance.

### 2.3 Existing real models that matter

Current ORM inspection confirms:

- `FarmSeasonVarietyPlan` has:
  - `effective_from`
  - `effective_to`
  - `available_at`
  - `row_hash`
  - farm/subfarm/season/variety scope
- `LocationReference` has geospatial identity and `source_row_hash`, but no timezone
- `LocationWeatherMapping` has:
  - `mapping_version`
  - `config_hash`
  - `available_at`
  - `valid_from`
  - `valid_to`
  - `row_hash`
- `WeatherDailyObservation` has:
  - `weather_source_location_id`
  - `observation_date`
  - `available_at` as `DATE`
  - `source_version`
  - `row_hash`
- `WeatherSourceLocation` has:
  - `timezone_name`
  - `source_version`
  - `row_hash`
- `BaseTemperatureSearchRun` has:
  - `config_hash`
  - `feature_version`
  - `source_signature`
  - `status`
  - `finished_at`
- `Holiday` only has seasonal dates and `active`; it does **not** have version, hash, or visibility
- `Factory` has no timezone column
- `Task9ARequest` currently requires the full typed surface described in [Section 8](#8-task9arequest-complete-field-mapping)

---

## 3. Existing-Model Inventory and Fit Assessment

| Existing model | Can serve authority? | Scope |
|---|---:|---|
| `FarmSeasonVarietyPlan` | Partial | Pool membership seed only; not daily capacity authority |
| `LocationReference` | Partial | Location identity only; not timezone authority |
| `LocationWeatherMapping` | Yes, existing | Task 7 mapping authority only |
| `WeatherDailyObservation` | Yes, existing | Task 7 observation authority only |
| `WeatherSourceLocation` | Partial | Can support farm timezone chain only through explicit mapping |
| `BaseTemperatureSearchRun` | Yes, existing | Task 8 / Task 9 upstream authority already modeled |
| `Holiday` | No | Lacks version/hash/available_at |
| `HarvestStateRun.input_snapshot` | No | Downstream consumption snapshot |
| `HarvestStateRun.resolved_parameter_snapshot` | No | Downstream derived snapshot |
| `ParameterLibraryVersion` / `ParameterObservation` | No | Agronomic parameter library, not operational Task 9 authority |

Conclusion: P0-6 needs new historical authority tables. Existing models are insufficient and must not be stretched beyond their current semantics.

---

## 4. Final Authority Model Decisions

The frozen minimal authority set for Task 9 replay is:

1. `task9_capacity_pool_definition`
2. `task9_capacity_pool_member`
3. `task9_daily_capacity_authority`
4. `task9_run_parameter_package`
5. `task9_holiday_calendar_version`
6. `task9_holiday_calendar_date`
7. `task9_weather_rule_config_version`
8. `task9_initial_inventory_snapshot`
9. `task9_initial_inventory_cohort`
10. `task9_mature_inventory_loss_authority`

This remains the minimum set that:

- preserves Task 9 typed request semantics
- keeps authority acyclic
- avoids a generic JSONB dumping table for unrelated concepts
- supports historical visibility and replay determinism
- supports deterministic source refs, hashes, and blocker attribution

### 4.1 `task9_capacity_pool_definition`

- **Purpose**: versioned pool identity, grain, destination factory, capacity mode
- **Business grain**:
  - `season_id x destination_factory_id x capacity_pool_code x capacity_pool_version`
- **Primary key**: surrogate `id`
- **Business key**:
  - `(season_id, destination_factory_id, capacity_pool_code, capacity_pool_version)`
- **Scope fields**:
  - `season_id`
  - `destination_factory_id`
  - `capacity_pool_code`
  - `capacity_pool_grain`
  - `capacity_input_mode`
- **Value fields**: none beyond grain/mode identity
- **Visibility fields**:
  - `available_at_local_date`
- **Effective interval**:
  - `effective_from`
  - `effective_to`
- **Version/status fields**:
  - `capacity_pool_version TEXT`
  - `revision INTEGER`
  - `status`
- **Canonical payload**:
  - season, factory, pool code, grain, mode, business version, revision, effective interval, source provenance
- **Row hash**:
  - canonical SHA-256 of full typed payload

### 4.2 `task9_capacity_pool_member`

- **Purpose**: immutable membership rows per pool definition
- **Business grain**:
  - `capacity_pool_definition_id x farm_id x subfarm_id x variety_id`
- **Primary key**: surrogate `id`
- **Business key**:
  - `(capacity_pool_definition_id, farm_id, subfarm_id, variety_id)`
- **Scope fields**:
  - `farm_id`
  - `subfarm_id`
  - `variety_id`
- **Value fields**: none
- **Visibility fields**: inherited from parent definition
- **Effective interval**: inherited from parent definition, but copied into child columns for exclusion enforcement
- **Version/status fields**: inherited from parent definition, but copied into child columns for exclusion enforcement
- **Canonical payload**:
  - parent semantic identity plus member scope
- **Row hash**:
  - canonical SHA-256 of full typed member payload

### 4.3 `task9_daily_capacity_authority`

- **Purpose**: historically visible daily capacity values per pool
- **Business grain**:
  - `capacity_pool_definition_id x capacity_date x revision`
- **Primary key**: surrogate `id`
- **Business key**:
  - `(capacity_pool_definition_id, capacity_date, revision)`
- **Scope fields**:
  - `capacity_pool_definition_id`
  - `capacity_date`
- **Value fields**:
  - `planned_picker_count`
  - `kg_per_person_per_day`
  - `direct_nominal_capacity_kg_per_day`
  - `labor_availability_ratio`
  - `operational_efficiency_ratio`
- **Visibility fields**:
  - `available_at_local_date`
- **Effective interval**:
  - `capacity_date` is the applicable date
- **Version/status fields**:
  - parent `capacity_pool_version`
  - `revision`
  - row `status`
- **Canonical payload**:
  - pool identity, date, business version, revision, capacity mode, all typed values, provenance
- **Row hash**:
  - canonical SHA-256 of full typed payload

### 4.4 `task9_run_parameter_package`

- **Purpose**: run-level scalar parameters that must move together
- **Business grain**:
  - `season_id x destination_factory_id x farm_scope_key x package_version`
- **Primary key**: surrogate `id`
- **Business key**:
  - `(season_id, destination_factory_id, farm_scope_key, package_version)`
- **Scope fields**:
  - `season_id`
  - `destination_factory_id`
  - `farm_scope_key`
- **Value fields**:
  - `farm_timezone`
  - `destination_factory_timezone`
  - `harvest_bucket_anchor_local_time`
  - `harvest_to_arrival_lag_days`
  - `holiday_calendar_version_id`
  - `weather_rule_config_version_id`
- **Visibility fields**:
  - `available_at_local_date`
- **Effective interval**:
  - `effective_from`
  - `effective_to`
- **Version/status fields**:
  - `package_version TEXT`
  - `revision INTEGER`
  - `status`
- **Canonical payload**:
  - scalar run parameters + referenced package semantic identities
- **Row hash**:
  - canonical SHA-256 of full typed payload

`farm_scope_key` is frozen as a deterministic string over the sorted farm IDs in the replay node scope. If multiple farms imply multiple farm timezones, replay must block instead of guessing.

### 4.5 `task9_holiday_calendar_version`

- **Purpose**: immutable holiday package header
- **Business grain**:
  - `season_id x calendar_code x calendar_version`
- **Value fields**:
  - `calendar_hash`
  - `region_scope`
- **Visibility fields**:
  - `available_at_local_date`
- **Effective interval**:
  - season-bound; dates live in child table
- **Version/status fields**:
  - `calendar_version TEXT`
  - `revision INTEGER`
  - `status`
- **Canonical payload**:
  - full authority payload hash over header + sorted child rows + provenance
- **Important distinction**:
  - `calendar_hash` is the Task 9 request business hash only
  - `row_hash` / `canonical_payload_hash` is the full authority payload hash

### 4.6 `task9_holiday_calendar_date`

- **Purpose**: normalized holiday dates
- **Business grain**:
  - `holiday_calendar_version_id x holiday_date x holiday_code`
- **Value fields**:
  - `holiday_code`
  - `holiday_name`

### 4.7 `task9_weather_rule_config_version`

- **Purpose**: immutable database authority for `WeatherEfficiencyRuleConfig`
- **Business grain**:
  - `rule_code x rule_version`
- **Value fields**:
  - `combination_method`
  - `minimum_ratio`
  - `maximum_ratio`
  - `required_feature_ids`
  - `feature_rules_json`
  - `config_hash`
- **Visibility fields**:
  - `available_at_local_date`
- **Effective interval**:
  - `effective_from`
  - `effective_to`
- **Version/status fields**:
  - `rule_version TEXT`
  - `revision INTEGER`
  - `status`
- **Canonical payload**:
  - exact typed config content, not a lossy summary

### 4.8 `task9_initial_inventory_snapshot`

- **Purpose**: authoritative opening mature inventory snapshot header
- **Business grain**:
  - `season_id x destination_factory_id x opening_state_date x snapshot_version x revision`
- **Value fields**:
  - `initial_opening_mature_inventory_kg`
- **Visibility fields**:
  - `available_at_local_date`
- **Effective interval**:
  - `opening_state_date`
- **Version/status fields**:
  - `snapshot_version TEXT`
  - `revision INTEGER`
  - `status`

### 4.9 `task9_initial_inventory_cohort`

- **Purpose**: normalized opening cohort rows tied to one inventory snapshot
- **Business grain**:
  - `initial_inventory_snapshot_id x stable_cohort_key x forecast_quantile`
- **Value fields**:
  - `forecast_quantile`
  - `cohort_date`
  - `farm_id`
  - `subfarm_id`
  - `variety_id`
  - `remaining_quantity_kg`

### 4.10 `task9_mature_inventory_loss_authority`

- **Purpose**: authoritative mature inventory loss per state date / pool / quantile
- **Business grain**:
  - `season_id x destination_factory_id x state_date x capacity_pool_code x forecast_quantile x loss_version`
- **Value fields**:
  - `mature_inventory_loss_quantity_kg`
- **Visibility fields**:
  - `available_at_local_date`
- **Effective interval**:
  - `state_date`
- **Version/status fields**:
  - `loss_version TEXT`
  - `revision INTEGER`
  - `status`

---

## 5. Rejected Alternatives

### 5.1 One generic `run_parameter_authority(parameter_code, parameter_value JSONB)`

Rejected because:

- capacity values, holiday packages, weather rules, inventory cohorts, and scalar run parameters have different grains
- overlap/uniqueness constraints differ materially
- JSONB-only shape would make semantic parity and conflict handling too loose
- replay blockers would be less precise

### 5.2 Reusing `FarmSeasonVarietyPlan.expected_total_marketable_kg` as capacity

Rejected because it changes Task 9 business semantics. Seasonal marketable quantity is not daily harvest capacity.

### 5.3 Reusing `HarvestStateRun.input_snapshot` or `resolved_parameter_snapshot`

Rejected because they are downstream snapshots, not upstream authority.

### 5.4 Deriving factory timezone from weather station timezone

Rejected because:

- `Factory` currently has no timezone column
- weather station timezone is not factory timezone authority
- silent substitution would hide historical inconsistency

### 5.5 Using `Holiday` directly as replay authority

Rejected because `Holiday` lacks:

- business version string
- request `calendar_hash`
- full authority row hash
- authoritative visibility
- immutable semantic package identity

---

## 6. Frozen Authority Contracts

### 6.1 Capacity pool contract

- `capacity_pool_grain` vocabulary:
  - `FARM`
  - `SUBFARM`
  - `SUBFARM_VARIETY`
- `capacity_input_mode` vocabulary:
  - `LABOR_DERIVED`
  - `DIRECT_CAPACITY`
- Pool identity uses:
  - `capacity_pool_code`
  - `capacity_pool_version`
  - `revision`
- A pool definition is immutable after insert.
- Membership is stored in child rows, not embedded JSON.
- A member may belong to **at most one** consumable pool for the same:
  - season
  - destination factory
  - overlapping effective range
- A pool may not mix farms.
- A pool may not be singleton when Task 9 rules reject singleton pools.
- Historical change is modeled by new rows; no in-place mutation.

### 6.2 Daily capacity contract

Units:

- `planned_picker_count`: non-negative decimal, scale 3, no implicit rounding
- `kg_per_person_per_day`: `kg/person/day`
- `direct_nominal_capacity_kg_per_day`: `kg/day`
- `labor_availability_ratio`: `[0,1]`
- `operational_efficiency_ratio`: `[0,1]`

Mode rules:

- `LABOR_DERIVED` requires:
  - `planned_picker_count`
  - `kg_per_person_per_day`
  - `labor_availability_ratio`
  - `operational_efficiency_ratio`
  - `direct_nominal_capacity_kg_per_day IS NULL`
- `DIRECT_CAPACITY` requires:
  - `direct_nominal_capacity_kg_per_day`
  - `labor_availability_ratio`
  - `operational_efficiency_ratio`
  - `planned_picker_count IS NULL`
  - `kg_per_person_per_day IS NULL`

Revision rules:

- business version string comes from the parent pool definition
- `revision` is an immutable per-date capacity revision
- same pool + date + revision + same payload -> idempotent
- same pool + date + revision + different payload -> `AUTHORITY_VERSION_CONFLICT`
- same pool + date + newer revision -> new immutable row

No defaulting is allowed for missing capacity values.

### 6.3 Run-parameter contract

Frozen run-level scalar parameters:

- `farm_timezone`
- `destination_factory_timezone`
- `harvest_bucket_anchor_local_time`
- `harvest_to_arrival_lag_days`

Frozen package references:

- `holiday_calendar_version_id`
- `weather_rule_config_version_id`

Rules:

- `farm_timezone` and `destination_factory_timezone` must be IANA timezone names
- `harvest_bucket_anchor_local_time` is a local business time, not UTC
- `harvest_to_arrival_lag_days >= 0`
- no implicit `09:00`
- no implicit lag
- no implicit calendar/version/hash
- package identity uses `package_version TEXT` plus `revision INTEGER`

### 6.4 Holiday contract

- Holiday replay authority is a versioned package, not `dim_holiday`
- `calendar_version` is the Task 9 business version string
- `revision` is the immutable authority-row revision and is distinct from `calendar_version`
- `calendar_hash` is the request business hash only and must be byte-compatible with:

```python
make_holiday_calendar_hash(
    holiday_calendar_version=calendar_version,
    holiday_dates=sorted(unique_holiday_dates),
)
```

- canonical request-hash payload is exactly:

```json
{
  "holiday_calendar_version": "<calendar_version>",
  "holiday_dates": ["<sorted dates>"]
}
```

- `calendar_hash` must not include:
  - `season_id`
  - `region_scope`
  - `calendar_code`
  - `holiday_code`
  - `holiday_name`
  - provenance
  - database ID
  - status
  - `available_at_local_date`
- full authority payload hash is separate and becomes:
  - `row_hash`
  - `canonical_payload_hash`
  - `semantic_payload_hash`
- Duplicate `(holiday_date, holiday_code)` rows within one package are rejected.
- Same `holiday_date` with different `holiday_code` is allowed in full authority rows.
- Task 9 request `holiday_dates` is the sorted unique date set only.
- Ordering is canonical by `holiday_date`, then `holiday_code`.

### 6.5 Weather rule contract

Replay authority must exactly reconstruct `WeatherEfficiencyRuleConfig`:

- `version`
- `required_feature_ids`
- `feature_rules`
- `combination_method`
- `minimum_ratio`
- `maximum_ratio`
- `missing_feature_policy`

Version rules:

- `rule_version TEXT` is the Task 9 business version string
- `revision INTEGER` is the immutable authority-row revision
- `rule_version` must reconstruct `WeatherEfficiencyRuleConfig.version` exactly

The database authority row must hash the full typed content, not a summary.

### 6.6 Initial mature inventory / cohort contract

- Opening inventory header and cohort rows are separate authorities.
- Zero opening inventory is represented explicitly as `0`, not by absence.
- Snapshot header does **not** contain `forecast_quantile`.
- Cohort child rows must contain `forecast_quantile IN ('P50', 'P80', 'P90')`.
- Scalar reconciliation is frozen as:
  - `sum(all cohort.remaining_quantity_kg across P50/P80/P90) == initial_opening_mature_inventory_kg`
- Missing cohorts when opening total is non-null are blocked.
- Empty cohorts are allowed only when opening total is exactly zero.
- Non-zero opening inventory requires non-empty cohort rows.
- Cross-table reconciliation cannot be enforced by plain `CHECK`; it must be enforced by:
  - repository write-time integrity validation
  - load-time integrity validation
  - blocker `INITIAL_INVENTORY_COHORT_MISMATCH`
  - atomic header + cohort transaction

### 6.7 Mature inventory loss contract

- Loss authority is per:
  - `state_date`
  - `capacity_pool_code`
  - `forecast_quantile`
- No default zero loss when authority is missing.
- Quantity must be non-negative.

---

## 7. Visibility and Effective-Interval Matrix

| Authority | Visibility field | Type | Effective field(s) | Cutoff rule |
|---|---|---|---|---|
| `task9_capacity_pool_definition` | `available_at_local_date` | `DATE` | `effective_from`, `effective_to` | visible iff `available_at_local_date <= node.as_of_local_date` |
| `task9_capacity_pool_member` | inherited | n/a | inherited | parent must be visible and effective |
| `task9_daily_capacity_authority` | `available_at_local_date` | `DATE` | `capacity_date` | visible iff `available_at_local_date <= node.as_of_local_date`; applicable iff `capacity_date` in forecast window |
| `task9_run_parameter_package` | `available_at_local_date` | `DATE` | `effective_from`, `effective_to` | visible iff `available_at_local_date <= node.as_of_local_date` |
| `task9_holiday_calendar_version` | `available_at_local_date` | `DATE` | season-bound | visible iff `available_at_local_date <= node.as_of_local_date` |
| `task9_weather_rule_config_version` | `available_at_local_date` | `DATE` | `effective_from`, `effective_to` | visible iff `available_at_local_date <= node.as_of_local_date` |
| `task9_initial_inventory_snapshot` | `available_at_local_date` | `DATE` | `opening_state_date` | visible iff `available_at_local_date <= node.as_of_local_date` |
| `task9_initial_inventory_cohort` | inherited | n/a | inherited from snapshot | parent must be visible |
| `task9_mature_inventory_loss_authority` | `available_at_local_date` | `DATE` | `state_date` | visible iff `available_at_local_date <= node.as_of_local_date` |

Frozen rules:

- Local-date authorities compare against `node.as_of_local_date`, not server-local `forecast_cutoff_at.date()`.
- Equality is visible: `available_at_local_date == node.as_of_local_date` passes.
- Future dates fail closed.
- SQL must filter visibility and effective range before candidate selection.

---

## 8. Task9ARequest Complete Field Mapping

| Task9ARequest field | Authority model | Authority grain | Visibility field | Effective field | Status requirement | Semantic identity / hash | Source ref form | Missing blocker |
|---|---|---|---|---|---|---|---|---|
| `as_of_date` | Task 11 node | n/a | n/a | n/a | n/a | node signature | none | n/a |
| `forecast_start_date` | Task 11 node | n/a | n/a | n/a | n/a | node signature | none | n/a |
| `forecast_end_date` | Task 11 node | n/a | n/a | n/a | n/a | node signature | none | n/a |
| `forecast_quantiles` | Task 9 schema constant | n/a | n/a | n/a | n/a | fixed canonical tuple | none | n/a |
| `destination_factory_id` | `task9_run_parameter_package` | season x factory x farm_scope x package_version | `available_at_local_date` | `effective_from/to` | see Section 10 | package row hash | `PARAMETER_SOURCE(TIMEZONE_CONFIG)` package ref | `RUN_PARAMETER_AUTHORITY_MISSING` |
| `farm_timezone` | `task9_run_parameter_package` | same | same | same | see Section 10 | package row hash | `PARAMETER_SOURCE(TIMEZONE_CONFIG)` package ref | `TIMEZONE_AUTHORITY_INVALID` |
| `destination_factory_timezone` | `task9_run_parameter_package` | same | same | same | see Section 10 | package row hash | `PARAMETER_SOURCE(TIMEZONE_CONFIG)` package ref | `TIMEZONE_AUTHORITY_INVALID` |
| `harvest_bucket_anchor_local_time` | `task9_run_parameter_package` | same | same | same | see Section 10 | package row hash | `PARAMETER_SOURCE(HARVEST_BUCKET_ANCHOR_TIME)` | `RUN_PARAMETER_AUTHORITY_MISSING` |
| `harvest_to_arrival_lag_days` | `task9_run_parameter_package` | same | same | same | see Section 10 | package row hash | `PARAMETER_SOURCE(HARVEST_TO_ARRIVAL_LAG)` | `RUN_PARAMETER_AUTHORITY_MISSING` |
| `holiday_calendar_version` | `task9_holiday_calendar_version` | season x calendar x calendar_version | `available_at_local_date` | season-bound | see Section 10 | full authority row hash plus request `calendar_hash` | `PARAMETER_SOURCE(HOLIDAY_CALENDAR)` | `HOLIDAY_CALENDAR_AUTHORITY_MISSING` |
| `holiday_calendar_hash` | `task9_holiday_calendar_version` | same | same | same | see Section 10 | exact `make_holiday_calendar_hash(...)` output | `PARAMETER_SOURCE(HOLIDAY_CALENDAR)` | `HOLIDAY_CALENDAR_AUTHORITY_MISSING` |
| `holiday_dates` | `task9_holiday_calendar_date` | holiday package x date | inherited | season-bound | see Section 10 | request `calendar_hash` over sorted unique dates | `PARAMETER_SOURCE(HOLIDAY_CALENDAR)` | `HOLIDAY_CALENDAR_AUTHORITY_MISSING` |
| `weather_rule_config` | `task9_weather_rule_config_version` | rule code x rule_version | `available_at_local_date` | `effective_from/to` | see Section 10 | config hash + canonical payload hash | `PARAMETER_SOURCE(WEATHER_RULE_CONFIG)` | `WEATHER_RULE_AUTHORITY_MISSING` |
| `run_parameter_source_refs` | package + holiday + weather rule rows | mixed | mixed | mixed | see Section 10 | source row hashes only | `ParameterSourceRef[]` | `RUN_PARAMETER_AUTHORITY_MISSING` |
| `capacity_pools` | `task9_capacity_pool_definition` + `task9_capacity_pool_member` | see Sections 4.1-4.2 | parent `available_at_local_date` | `effective_from/to` | see Section 10 | definition + sorted membership hashes | none in field, refs appear in daily capacity | `CAPACITY_POOL_AUTHORITY_MISSING` |
| `daily_capacity_inputs` | `task9_daily_capacity_authority` | pool x date x revision | `available_at_local_date` | `capacity_date` | see Section 10 | row hash | `ParameterSourceRef[]` | `CAPACITY_VALUE_AUTHORITY_MISSING` |
| `daily_weather_features` | existing Task 7 authority | mapping + observation | existing Task 7 visibility | observation date | existing statuses | existing row hashes/signatures | existing `PARAMETER_SOURCE(WEATHER_FEATURE_OBSERVATION)` | existing Task 7 blockers |
| `task8_daily_predictions` | existing Task 8 authority | daily prediction x quantile | existing Task 8 visibility | prediction date | completed chain | existing signatures / hashes | existing `TASK8_DAILY_PREDICTION` refs | existing Task 8 blockers |
| `initial_inventory_cohorts` | `task9_initial_inventory_snapshot` + `task9_initial_inventory_cohort` | snapshot x stable cohort key x quantile | `available_at_local_date` | `opening_state_date` | see Section 10 | snapshot hash + cohort hashes | `INITIAL_INVENTORY_SNAPSHOT` refs | `INITIAL_INVENTORY_AUTHORITY_MISSING` |
| `initial_opening_mature_inventory_kg` | `task9_initial_inventory_snapshot` | season x factory x opening_state_date x snapshot_version | `available_at_local_date` | `opening_state_date` | see Section 10 | snapshot hash | `INITIAL_INVENTORY_SNAPSHOT` ref | `INITIAL_INVENTORY_AUTHORITY_MISSING` |
| `mature_inventory_loss_inputs` | `task9_mature_inventory_loss_authority` | date x pool x quantile x loss_version | `available_at_local_date` | `state_date` | see Section 10 | row hash | `PARAMETER_SOURCE(MATURE_INVENTORY_LOSS)` | `MATURE_INVENTORY_LOSS_AUTHORITY_MISSING` |

### Fields without authority

After `0014`, none of the Task9ARequest business fields remain authority-unmapped.

### 8.1 Run-package-first load order

Frozen request reconstruction order:

1. select exactly one consumable `task9_run_parameter_package`
2. load holiday row by `run_parameter_package.holiday_calendar_version_id`
3. load weather rule row by `run_parameter_package.weather_rule_config_version_id`
4. validate both referenced rows:
   - exists
   - `status = 'active'`
   - visible at `node.as_of_local_date`
   - scope compatible
   - row hash valid
   - `calendar_hash` / `config_hash` recomputation valid
   - business version valid
5. reconstruct `Task9ARequest`

Holiday and weather rule resolution must not independently select "latest" rows once the run package is chosen.

### Downstream snapshots excluded

Explicitly excluded from mapping:

- `HarvestStateRun.input_snapshot`
- `HarvestStateRun.resolved_parameter_snapshot`

They remain valid only for:

- integrity reload
- audit comparison
- replay-result parity
- tamper detection

---

## 9. Semantic Identity and Canonical Hash Matrix

| Authority | semantic_payload_hash | config_hash | canonical_payload_hash | business_version | revision | persistent reference in semantic hash? |
|---|---|---|---|---|---|---:|
| `task9_capacity_pool_definition` | full typed definition payload hash | none | same | `capacity_pool_version` | yes | No |
| `task9_capacity_pool_member` | full typed member payload hash | none | same | parent `capacity_pool_version` | inherited | No |
| `task9_daily_capacity_authority` | full typed capacity row payload hash | none | same | parent `capacity_pool_version` | yes | No |
| `task9_run_parameter_package` | full typed package payload hash | none | same | `package_version` | yes | No |
| `task9_holiday_calendar_version` | full authority payload hash over header + sorted date rows + provenance | none | same | `calendar_version` | yes | No |
| `task9_holiday_calendar_version` request contract | exact `calendar_hash` request payload hash | none | n/a | `calendar_version` | n/a | No |
| `task9_weather_rule_config_version` | full typed rule payload hash | `config_hash` from rule row | payload hash | `rule_version` | yes | No |
| `task9_initial_inventory_snapshot` | full snapshot payload hash | none | same | `snapshot_version` | yes | No |
| `task9_initial_inventory_cohort` | full typed cohort payload hash | none | same | parent `snapshot_version` | inherited | No |
| `task9_mature_inventory_loss_authority` | full loss row payload hash | none | same | `loss_version` | yes | No |

Frozen semantic rules:

- database IDs never enter semantic hashes
- random UUIDs never enter semantic hashes
- `NULL` and field absence are distinct
- collections are canonicalized:
  - pool members sorted by `(farm_id, subfarm_id nulls-first, variety_id)`
  - holiday dates sorted by `(holiday_date, holiday_code)`
  - cohorts sorted by stable cohort key
- Decimal formatting must reuse existing canonical decimal rules
- local dates remain dates; they must not be converted into fabricated UTC instants

Conflict rules:

- same business key + same canonical payload -> idempotent
- same business key + different canonical payload -> conflict
- same hash + different canonical payload -> hash conflict
- `calendar_hash` and full authority row hash are separate and both must validate

---

## 10. Status and Consumability

Frozen status vocabulary for new authority tables:

- `draft`
- `active`
- `superseded`
- `retired`
- `cancelled`

Frozen replay selection rule:

- resolver selects only `active`
- `draft` is never consumable
- `cancelled` is never consumable
- `retired` is not selected by new resolution
- `superseded` is not selected by new resolution

Historical replay of older selected rows is handled by persisted resolved-input references, not by asking the resolver to reselect superseded rows.

Status does **not** enter semantic payload hashes. It only participates in SQL selection and consumability validation.

### 10.1 Frozen status transition matrix

- `draft -> active`
- `draft -> cancelled`
- `active -> superseded`
- `active -> retired`
- `active -> cancelled`
- `superseded -> retired`
- `retired -> no transition`
- `cancelled -> no transition`

Forbidden transitions:

- `superseded -> active`
- `retired -> active`
- `cancelled -> active`

### 10.2 Immutable business payload vs mutable metadata

- business payload columns are immutable after insert
- mutable metadata is limited to:
  - `status`
  - `status_changed_at`
  - `superseded_by_id` on rows that enter `superseded`

### 10.3 Parent/member synchronization

When a pool definition status changes, all member assignment rows must be updated in the same repository transaction:

- deterministic row-lock order
- parent update + child updates in one transaction
- rollback on any failure

### 10.4 Active replacement transaction

Replacement of one active authority row with a new active row must occur as:

1. lock current active row
2. transition current row from `active` to `superseded`
3. insert or activate replacement row
4. commit atomically

Only `active` rows participate in exclusion constraints. `superseded`, `retired`, and `cancelled` rows do not.

### 10.5 Selection matrix

| Authority | SQL WHERE | Consumable statuses | ORDER BY | Expected cardinality | Ambiguity blocker |
|---|---|---|---|---:|---|
| capacity pool definition | scope + visible + effective | `active` | none; uniqueness/exclusion must yield 0..1 row | 0..1 per pool code | `CAPACITY_POOL_AUTHORITY_AMBIGUOUS` |
| daily capacity | parent visible/effective + `capacity_date` in window + visible | `active` | `revision DESC, available_at_local_date DESC, row_hash ASC` | 0..1 per pool/date after highest revision uniqueness | `CAPACITY_VALUE_AUTHORITY_AMBIGUOUS` |
| run-parameter package | scope + visible + effective | `active` | none; overlap exclusion must yield 0..1 row | 0..1 | `RUN_PARAMETER_AUTHORITY_AMBIGUOUS` |
| holiday calendar | exact FK load from selected run package | `active` | none; FK target exact load | exactly 1 referenced row | `HOLIDAY_CALENDAR_REFERENCE_INVALID` |
| weather rule config | exact FK load from selected run package | `active` | none; FK target exact load | exactly 1 referenced row | `WEATHER_RULE_REFERENCE_INVALID` |
| initial inventory snapshot | scope + visible + opening_state_date | `active` | `revision DESC, available_at_local_date DESC, row_hash ASC` | 0..1 per opening state date | `INITIAL_INVENTORY_AUTHORITY_AMBIGUOUS` |
| mature inventory loss | scope + visible + state_date | `active` | `revision DESC, available_at_local_date DESC, row_hash ASC` | 0..1 per date/pool/quantile after highest revision uniqueness | `MATURE_INVENTORY_LOSS_AUTHORITY_AMBIGUOUS` |

---

## 11. Overlap, Uniqueness, and Concurrency

Project PostgreSQL version is frozen as 16 for this design round. Therefore the document chooses explicit PostgreSQL 16 features and does not leave alternative branches.

### 11.1 Required PostgreSQL protections

- `UNIQUE NULLS NOT DISTINCT` for nullable business keys
- `CREATE EXTENSION IF NOT EXISTS btree_gist`
- stored `daterange` columns for effective overlap checks
- stored `normalized_subfarm_id` for NULL-safe cross-pool exclusion
- `EXCLUDE USING gist` for overlapping consumable intervals
- database-enforced parent/child copied-field parity through composite FK
- transactional create-or-load behavior for exact same payload
- reject conflicting payload on same business key

### 11.2 Frozen overlap rules

- Capacity pool definitions may not have overlapping consumable effective intervals for the same:
  - `season_id`
  - `destination_factory_id`
  - `capacity_pool_code`
- Capacity members may not belong to overlapping consumable pools for the same:
  - `season_id`
  - `destination_factory_id`
  - `farm_id`
  - `subfarm_id`
  - `variety_id`
- Run-parameter packages may not have overlapping consumable effective intervals for the same:
  - `season_id`
  - `destination_factory_id`
  - `farm_scope_key`
- Daily capacity rows are unique per:
  - `capacity_pool_definition_id`
  - `capacity_date`
  - `revision`
- Initial inventory snapshots are unique per:
  - `season_id`
  - `destination_factory_id`
  - `opening_state_date`
  - `snapshot_version`
  - `revision`
- Mature inventory loss rows are unique per:
  - `season_id`
  - `destination_factory_id`
  - `state_date`
  - `capacity_pool_code`
  - `forecast_quantile`
  - `loss_version`
  - `revision`

### 11.3 NULL-safe member exclusion

Frozen rule:

- all real dimension IDs are positive
- `0` is reserved and cannot be a valid `subfarm_id`
- `subfarm_id IS NULL` is normalized to `normalized_subfarm_id = 0`

This normalized value is used only for exclusion semantics; it is not a business identifier.

### 11.4 Parent-child copied-field binding

The member table redundantly stores:

- `season_id`
- `destination_factory_id`
- `effective_from`
- `effective_to`
- `status`

These are copied solely so PostgreSQL can enforce cross-pool exclusion at child granularity. They must be bound to the parent by database constraint, not by trigger.

Frozen binding strategy:

- parent stores non-null normalized effective end:
  - `effective_to_exclusive DATE GENERATED ALWAYS AS (COALESCE(effective_to + 1, DATE '9999-12-31')) STORED`
- parent gets composite uniqueness on:
  - `(id, season_id, destination_factory_id, effective_from, effective_to_exclusive, status)`
- child stores the same normalized field copied from parent
- child gets composite FK on:
  - `(capacity_pool_definition_id, season_id, destination_factory_id, effective_from, effective_to_exclusive, status)`
- no triggers

---

## 12. Blocker Taxonomy

Frozen blocker set for future implementation:

- `CAPACITY_POOL_AUTHORITY_MISSING`
- `CAPACITY_POOL_AUTHORITY_AMBIGUOUS`
- `CAPACITY_POOL_GRAIN_INVALID`
- `CAPACITY_POOL_MEMBERSHIP_CONFLICT`
- `CAPACITY_POOL_EFFECTIVE_OVERLAP`
- `CAPACITY_VALUE_AUTHORITY_MISSING`
- `CAPACITY_VALUE_AUTHORITY_AMBIGUOUS`
- `CAPACITY_MODE_FIELDS_INVALID`
- `CAPACITY_AUTHORITY_AFTER_CUTOFF`
- `CAPACITY_VALUE_HASH_CONFLICT`
- `RUN_PARAMETER_AUTHORITY_MISSING`
- `RUN_PARAMETER_AUTHORITY_AMBIGUOUS`
- `RUN_PARAMETER_AUTHORITY_AFTER_CUTOFF`
- `RUN_PARAMETER_SCOPE_CONFLICT`
- `TIMEZONE_AUTHORITY_INVALID`
- `HOLIDAY_CALENDAR_AUTHORITY_MISSING`
- `HOLIDAY_CALENDAR_AUTHORITY_AMBIGUOUS`
- `HOLIDAY_CALENDAR_REFERENCE_INVALID`
- `HOLIDAY_CALENDAR_HASH_MISMATCH`
- `WEATHER_RULE_AUTHORITY_MISSING`
- `WEATHER_RULE_AUTHORITY_AMBIGUOUS`
- `WEATHER_RULE_REFERENCE_INVALID`
- `WEATHER_RULE_CONFIG_HASH_MISMATCH`
- `INITIAL_INVENTORY_AUTHORITY_MISSING`
- `INITIAL_INVENTORY_AUTHORITY_AMBIGUOUS`
- `INITIAL_INVENTORY_COHORT_MISMATCH`
- `MATURE_INVENTORY_LOSS_AUTHORITY_MISSING`
- `MATURE_INVENTORY_LOSS_AUTHORITY_AMBIGUOUS`
- `AUTHORITY_HASH_CONFLICT`
- `AUTHORITY_VERSION_CONFLICT`
- `AUTHORITY_STATUS_NOT_CONSUMABLE`

These are in addition to existing Task 6 / Task 7 / Task 8 / Task 9 blocker families.

---

## 12A. ParameterSourceRef Matrix

All `ParameterSourceRef` rows in Task 9 replay must use deterministic values and must not use database surrogate IDs inside `source_record_key`.

Frozen `source_system`:

- `task9_historical_authority`

Frozen sort order for emitted refs:

- `parameter_code ASC`
- `source_row_hash ASC`

### 12A.1 Run-parameter codes

| parameter_code | authority table | authority grain | source_system | source_record_key format | source_version | source_row_hash | available_at | as_of_date | shared-row behavior | required mode | forbidden mode | exactly-one rule |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `HOLIDAY_CALENDAR` | `task9_holiday_calendar_version` | season x calendar_version x revision | `task9_historical_authority` | `{season_id}:{calendar_code}:{calendar_version}:{revision}` | `calendar_version` | holiday header `row_hash` | holiday `available_at_local_date` | node `as_of_date` | unique holiday header row | all modes | none | exactly one |
| `WEATHER_RULE_CONFIG` | `task9_weather_rule_config_version` | rule_version x revision | `task9_historical_authority` | `{rule_code}:{rule_version}:{revision}` | `rule_version` | weather-rule `row_hash` | rule `available_at_local_date` | node `as_of_date` | unique weather-rule row | all modes | none | exactly one |
| `HARVEST_TO_ARRIVAL_LAG` | `task9_run_parameter_package` | run package row | `task9_historical_authority` | `{season_id}:{destination_factory_id}:{farm_scope_key}:{package_version}:{revision}` | `package_version` | run-package `row_hash` | package `available_at_local_date` | node `as_of_date` | shared run-package row | all modes | none | exactly one |
| `TIMEZONE_CONFIG` | `task9_run_parameter_package` | run package row | `task9_historical_authority` | `{season_id}:{destination_factory_id}:{farm_scope_key}:{package_version}:{revision}` | `package_version` | run-package `row_hash` | package `available_at_local_date` | node `as_of_date` | shared run-package row | all modes | none | exactly one |
| `HARVEST_BUCKET_ANCHOR_TIME` | `task9_run_parameter_package` | run package row | `task9_historical_authority` | `{season_id}:{destination_factory_id}:{farm_scope_key}:{package_version}:{revision}` | `package_version` | run-package `row_hash` | package `available_at_local_date` | node `as_of_date` | shared run-package row | all modes | none | exactly one |

The three run-package codes may share:

- `source_record_key`
- `source_version`
- `source_row_hash`

But they must still emit three distinct `ParameterSourceRef` rows because `parameter_code` differs.

### 12A.2 `LABOR_DERIVED` capacity mode

Required codes:

- `PLANNED_PICKER_COUNT`
- `PICKER_PRODUCTIVITY`
- `LABOR_AVAILABILITY_RATIO`
- `OPERATIONAL_EFFICIENCY_RATIO`

Forbidden code:

- `DIRECT_NOMINAL_CAPACITY`

Authority table:

- `task9_daily_capacity_authority`

Source-record-key format:

- `{capacity_pool_code}:{capacity_pool_version}:{capacity_date}:{revision}`

Additional frozen ref fields:

- `source_system = task9_historical_authority`
- `source_version = capacity_pool_version`
- `available_at = daily_capacity.available_at_local_date`
- `as_of_date = node.as_of_date`

### 12A.3 `DIRECT_CAPACITY` mode

Required codes:

- `DIRECT_NOMINAL_CAPACITY`
- `LABOR_AVAILABILITY_RATIO`
- `OPERATIONAL_EFFICIENCY_RATIO`

Forbidden codes:

- `PLANNED_PICKER_COUNT`
- `PICKER_PRODUCTIVITY`

Authority table:

- `task9_daily_capacity_authority`

Source-record-key format:

- `{capacity_pool_code}:{capacity_pool_version}:{capacity_date}:{revision}`

Capacity refs may share one authority row hash, but each parameter code still requires its own `ParameterSourceRef`.

### 12A.4 Mature loss

| parameter_code | authority table | source_system | source_record_key format | source_version | source_row_hash | available_at | as_of_date | exactly-one rule |
|---|---|---|---|---|---|---|---|---|
| `MATURE_INVENTORY_LOSS` | `task9_mature_inventory_loss_authority` | `task9_historical_authority` | `{season_id}:{destination_factory_id}:{capacity_pool_code}:{state_date}:{forecast_quantile}:{loss_version}:{revision}` | `loss_version` | mature-loss `row_hash` | mature-loss `available_at_local_date` | node `as_of_date` | exactly one per state_date x pool x quantile |

---

## 13. DDL Draft

The following SQL is a design draft for `0014`. It is intentionally not applied in this round.

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE task9_capacity_pool_definition (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    season_id BIGINT NOT NULL REFERENCES dim_season(id) ON DELETE RESTRICT,
    destination_factory_id BIGINT NOT NULL REFERENCES dim_factory(id) ON DELETE RESTRICT,
    capacity_pool_code TEXT NOT NULL,
    capacity_pool_version TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    capacity_pool_grain TEXT NOT NULL
        CHECK (capacity_pool_grain IN ('FARM', 'SUBFARM', 'SUBFARM_VARIETY')),
    capacity_input_mode TEXT NOT NULL
        CHECK (capacity_input_mode IN ('LABOR_DERIVED', 'DIRECT_CAPACITY')),
    effective_from DATE NOT NULL,
    effective_to DATE,
    effective_to_exclusive DATE GENERATED ALWAYS AS (
        COALESCE(effective_to + 1, DATE '9999-12-31')
    ) STORED,
    effective_range DATERANGE GENERATED ALWAYS AS (
        daterange(effective_from, COALESCE(effective_to + 1, NULL), '[)')
    ) STORED,
    available_at_local_date DATE NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
    status_changed_at TIMESTAMPTZ NOT NULL,
    source_system TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    source_version TEXT NOT NULL,
    row_hash TEXT NOT NULL
        CONSTRAINT ck_task9_capacity_pool_definition_row_hash_sha256
        CHECK (row_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (season_id, destination_factory_id, capacity_pool_code, capacity_pool_version, revision),
    UNIQUE (id, season_id, destination_factory_id, effective_from, effective_to_exclusive, status),
    CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

CREATE TABLE task9_capacity_pool_member (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    capacity_pool_definition_id BIGINT NOT NULL
        REFERENCES task9_capacity_pool_definition(id) ON DELETE RESTRICT,
    season_id BIGINT NOT NULL REFERENCES dim_season(id) ON DELETE RESTRICT,
    destination_factory_id BIGINT NOT NULL REFERENCES dim_factory(id) ON DELETE RESTRICT,
    farm_id BIGINT NOT NULL REFERENCES dim_farm(id) ON DELETE RESTRICT,
    subfarm_id BIGINT REFERENCES dim_subfarm(id) ON DELETE RESTRICT,
    normalized_subfarm_id BIGINT GENERATED ALWAYS AS (COALESCE(subfarm_id, 0)) STORED,
    variety_id BIGINT NOT NULL REFERENCES dim_variety(id) ON DELETE RESTRICT,
    effective_from DATE NOT NULL,
    effective_to DATE,
    effective_to_exclusive DATE NOT NULL,
    effective_range DATERANGE GENERATED ALWAYS AS (
        daterange(effective_from, COALESCE(effective_to + 1, NULL), '[)')
    ) STORED,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
    status_changed_at TIMESTAMPTZ NOT NULL,
    superseded_by_id BIGINT NULL,
    row_hash TEXT NOT NULL
        CONSTRAINT ck_task9_capacity_pool_member_row_hash_sha256
        CHECK (row_hash ~ '^[0-9a-f]{64}$'),
    UNIQUE NULLS NOT DISTINCT (
        capacity_pool_definition_id,
        farm_id,
        subfarm_id,
        variety_id
    ),
    CHECK (farm_id > 0),
    CHECK (variety_id > 0),
    CHECK (subfarm_id IS NULL OR subfarm_id > 0),
    FOREIGN KEY (
        capacity_pool_definition_id,
        season_id,
        destination_factory_id,
        effective_from,
        effective_to_exclusive,
        status
    )
    REFERENCES task9_capacity_pool_definition (
        id,
        season_id,
        destination_factory_id,
        effective_from,
        effective_to_exclusive,
        status
    )
    ON DELETE RESTRICT
);

CREATE TABLE task9_daily_capacity_authority (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    capacity_pool_definition_id BIGINT NOT NULL
        REFERENCES task9_capacity_pool_definition(id) ON DELETE RESTRICT,
    capacity_date DATE NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    planned_picker_count NUMERIC(18, 3),
    kg_per_person_per_day NUMERIC(18, 3),
    direct_nominal_capacity_kg_per_day NUMERIC(18, 3),
    labor_availability_ratio NUMERIC(12, 6) NOT NULL
        CHECK (labor_availability_ratio >= 0 AND labor_availability_ratio <= 1),
    operational_efficiency_ratio NUMERIC(12, 6) NOT NULL
        CHECK (operational_efficiency_ratio >= 0 AND operational_efficiency_ratio <= 1),
    available_at_local_date DATE NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
    status_changed_at TIMESTAMPTZ NOT NULL,
    superseded_by_id BIGINT NULL,
    source_system TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    source_version TEXT NOT NULL,
    row_hash TEXT NOT NULL
        CONSTRAINT ck_task9_daily_capacity_authority_row_hash_sha256
        CHECK (row_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (capacity_pool_definition_id, capacity_date, revision),
    CHECK (
        (
            planned_picker_count IS NOT NULL
            AND kg_per_person_per_day IS NOT NULL
            AND direct_nominal_capacity_kg_per_day IS NULL
        ) OR (
            direct_nominal_capacity_kg_per_day IS NOT NULL
            AND planned_picker_count IS NULL
            AND kg_per_person_per_day IS NULL
        )
    )
);

CREATE TABLE task9_holiday_calendar_version (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    season_id BIGINT NOT NULL REFERENCES dim_season(id) ON DELETE RESTRICT,
    calendar_code TEXT NOT NULL,
    calendar_version TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    region_scope TEXT,
    calendar_hash TEXT NOT NULL
        CONSTRAINT ck_task9_holiday_calendar_version_calendar_hash_sha256
        CHECK (calendar_hash ~ '^[0-9a-f]{64}$'),
    available_at_local_date DATE NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
    status_changed_at TIMESTAMPTZ NOT NULL,
    superseded_by_id BIGINT NULL,
    source_system TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    source_version TEXT NOT NULL,
    row_hash TEXT NOT NULL
        CONSTRAINT ck_task9_holiday_calendar_version_row_hash_sha256
        CHECK (row_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (season_id, calendar_code, calendar_version, revision)
);

CREATE TABLE task9_holiday_calendar_date (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    holiday_calendar_version_id BIGINT NOT NULL
        REFERENCES task9_holiday_calendar_version(id) ON DELETE RESTRICT,
    holiday_date DATE NOT NULL,
    holiday_code TEXT NOT NULL,
    holiday_name TEXT NOT NULL,
    UNIQUE (holiday_calendar_version_id, holiday_date, holiday_code)
);

CREATE TABLE task9_weather_rule_config_version (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    rule_code TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    combination_method TEXT NOT NULL,
    minimum_ratio NUMERIC(12, 6) NOT NULL CHECK (minimum_ratio >= 0 AND minimum_ratio <= 1),
    maximum_ratio NUMERIC(12, 6) NOT NULL CHECK (maximum_ratio >= 0 AND maximum_ratio <= 1),
    required_feature_ids JSONB NOT NULL,
    feature_rules_json JSONB NOT NULL,
    missing_feature_policy TEXT NOT NULL CHECK (missing_feature_policy = 'BLOCK'),
    config_hash TEXT NOT NULL
        CONSTRAINT ck_task9_weather_rule_config_version_config_hash_sha256
        CHECK (config_hash ~ '^[0-9a-f]{64}$'),
    available_at_local_date DATE NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    effective_to_exclusive DATE GENERATED ALWAYS AS (
        COALESCE(effective_to + 1, DATE '9999-12-31')
    ) STORED,
    effective_range DATERANGE GENERATED ALWAYS AS (
        daterange(effective_from, COALESCE(effective_to + 1, NULL), '[)')
    ) STORED,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
    status_changed_at TIMESTAMPTZ NOT NULL,
    superseded_by_id BIGINT NULL,
    source_system TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    source_version TEXT NOT NULL,
    row_hash TEXT NOT NULL
        CONSTRAINT ck_task9_weather_rule_config_version_row_hash_sha256
        CHECK (row_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (rule_code, rule_version, revision),
    CHECK (maximum_ratio >= minimum_ratio),
    CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

CREATE TABLE task9_run_parameter_package (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    season_id BIGINT NOT NULL REFERENCES dim_season(id) ON DELETE RESTRICT,
    destination_factory_id BIGINT NOT NULL REFERENCES dim_factory(id) ON DELETE RESTRICT,
    farm_scope_key TEXT NOT NULL,
    package_version TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    farm_timezone TEXT NOT NULL,
    destination_factory_timezone TEXT NOT NULL,
    harvest_bucket_anchor_local_time TIME NOT NULL,
    harvest_to_arrival_lag_days INTEGER NOT NULL CHECK (harvest_to_arrival_lag_days >= 0),
    holiday_calendar_version_id BIGINT NOT NULL
        REFERENCES task9_holiday_calendar_version(id) ON DELETE RESTRICT,
    weather_rule_config_version_id BIGINT NOT NULL
        REFERENCES task9_weather_rule_config_version(id) ON DELETE RESTRICT,
    available_at_local_date DATE NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    effective_to_exclusive DATE GENERATED ALWAYS AS (
        COALESCE(effective_to + 1, DATE '9999-12-31')
    ) STORED,
    effective_range DATERANGE GENERATED ALWAYS AS (
        daterange(effective_from, COALESCE(effective_to + 1, NULL), '[)')
    ) STORED,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
    status_changed_at TIMESTAMPTZ NOT NULL,
    superseded_by_id BIGINT NULL,
    source_system TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    source_version TEXT NOT NULL,
    row_hash TEXT NOT NULL
        CONSTRAINT ck_task9_run_parameter_package_row_hash_sha256
        CHECK (row_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (season_id, destination_factory_id, farm_scope_key, package_version, revision),
    CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

CREATE TABLE task9_initial_inventory_snapshot (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    season_id BIGINT NOT NULL REFERENCES dim_season(id) ON DELETE RESTRICT,
    destination_factory_id BIGINT NOT NULL REFERENCES dim_factory(id) ON DELETE RESTRICT,
    opening_state_date DATE NOT NULL,
    snapshot_version TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    initial_opening_mature_inventory_kg NUMERIC(18, 6) NOT NULL
        CHECK (initial_opening_mature_inventory_kg >= 0),
    available_at_local_date DATE NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
    status_changed_at TIMESTAMPTZ NOT NULL,
    superseded_by_id BIGINT NULL,
    source_system TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    source_version TEXT NOT NULL,
    row_hash TEXT NOT NULL
        CONSTRAINT ck_task9_initial_inventory_snapshot_row_hash_sha256
        CHECK (row_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (
        season_id,
        destination_factory_id,
        opening_state_date,
        snapshot_version,
        revision
    )
);

CREATE TABLE task9_initial_inventory_cohort (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    initial_inventory_snapshot_id BIGINT NOT NULL
        REFERENCES task9_initial_inventory_snapshot(id) ON DELETE RESTRICT,
    stable_cohort_key TEXT NOT NULL,
    forecast_quantile TEXT NOT NULL CHECK (forecast_quantile IN ('P50', 'P80', 'P90')),
    cohort_date DATE NOT NULL,
    farm_id BIGINT NOT NULL REFERENCES dim_farm(id) ON DELETE RESTRICT,
    subfarm_id BIGINT REFERENCES dim_subfarm(id) ON DELETE RESTRICT,
    variety_id BIGINT NOT NULL REFERENCES dim_variety(id) ON DELETE RESTRICT,
    remaining_quantity_kg NUMERIC(18, 6) NOT NULL CHECK (remaining_quantity_kg >= 0),
    row_hash TEXT NOT NULL
        CONSTRAINT ck_task9_initial_inventory_cohort_row_hash_sha256
        CHECK (row_hash ~ '^[0-9a-f]{64}$'),
    UNIQUE (initial_inventory_snapshot_id, stable_cohort_key, forecast_quantile)
);

CREATE TABLE task9_mature_inventory_loss_authority (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    season_id BIGINT NOT NULL REFERENCES dim_season(id) ON DELETE RESTRICT,
    destination_factory_id BIGINT NOT NULL REFERENCES dim_factory(id) ON DELETE RESTRICT,
    state_date DATE NOT NULL,
    capacity_pool_code TEXT NOT NULL,
    forecast_quantile TEXT NOT NULL CHECK (forecast_quantile IN ('P50', 'P80', 'P90')),
    loss_version TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    mature_inventory_loss_quantity_kg NUMERIC(18, 6) NOT NULL
        CHECK (mature_inventory_loss_quantity_kg >= 0),
    available_at_local_date DATE NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
    status_changed_at TIMESTAMPTZ NOT NULL,
    superseded_by_id BIGINT NULL,
    source_system TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    source_version TEXT NOT NULL,
    row_hash TEXT NOT NULL
        CONSTRAINT ck_task9_mature_inventory_loss_authority_row_hash_sha256
        CHECK (row_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (
        season_id,
        destination_factory_id,
        state_date,
        capacity_pool_code,
        forecast_quantile,
        loss_version,
        revision
    )
);

CREATE INDEX ix_task9_capacity_pool_def_available
    ON task9_capacity_pool_definition(available_at_local_date);
CREATE INDEX ix_task9_daily_capacity_available
    ON task9_daily_capacity_authority(available_at_local_date);
CREATE INDEX ix_task9_run_parameter_package_available
    ON task9_run_parameter_package(available_at_local_date);
CREATE INDEX ix_task9_holiday_calendar_available
    ON task9_holiday_calendar_version(available_at_local_date);
CREATE INDEX ix_task9_weather_rule_available
    ON task9_weather_rule_config_version(available_at_local_date);
CREATE INDEX ix_task9_initial_inventory_available
    ON task9_initial_inventory_snapshot(available_at_local_date);
CREATE INDEX ix_task9_mature_loss_available
    ON task9_mature_inventory_loss_authority(available_at_local_date);

ALTER TABLE task9_capacity_pool_definition
    ADD CONSTRAINT ex_task9_capacity_pool_definition_overlap
    EXCLUDE USING gist (
        season_id WITH =,
        destination_factory_id WITH =,
        capacity_pool_code WITH =,
        effective_range WITH &&
    )
    WHERE (status = 'active');

ALTER TABLE task9_capacity_pool_member
    ADD CONSTRAINT ex_task9_capacity_pool_member_overlap
    EXCLUDE USING gist (
        season_id WITH =,
        destination_factory_id WITH =,
        farm_id WITH =,
        normalized_subfarm_id WITH =,
        variety_id WITH =,
        effective_range WITH &&
    )
    WHERE (status = 'active');

ALTER TABLE task9_run_parameter_package
    ADD CONSTRAINT ex_task9_run_parameter_package_overlap
    EXCLUDE USING gist (
        season_id WITH =,
        destination_factory_id WITH =,
        farm_scope_key WITH =,
        effective_range WITH &&
    )
    WHERE (status = 'active');
```

---

## 14. Migration 0014 Boundary

### 14.1 Migration name

Frozen target:

- `0014_task9_historical_authority`

### 14.2 Objects to create

- `task9_capacity_pool_definition`
- `task9_capacity_pool_member`
- `task9_daily_capacity_authority`
- `task9_run_parameter_package`
- `task9_holiday_calendar_version`
- `task9_holiday_calendar_date`
- `task9_weather_rule_config_version`
- `task9_initial_inventory_snapshot`
- `task9_initial_inventory_cohort`
- `task9_mature_inventory_loss_authority`

### 14.3 Constraints and indexes to create

- `btree_gist` extension: **YES**
- generated range columns:
  - `task9_capacity_pool_definition.effective_range`
  - `task9_capacity_pool_member.effective_range`
  - `task9_capacity_pool_member.normalized_subfarm_id`
  - `task9_weather_rule_config_version.effective_range`
  - `task9_run_parameter_package.effective_range`
- `UNIQUE NULLS NOT DISTINCT`:
  - `task9_capacity_pool_member(capacity_pool_definition_id, farm_id, subfarm_id, variety_id)`
- exclusion constraints:
  - `ex_task9_capacity_pool_definition_overlap`
  - `ex_task9_capacity_pool_member_overlap`
  - `ex_task9_run_parameter_package_overlap`
- triggers: `NONE`
- no new rolling_backtest tables

### 14.4 Existing-table alterations

Frozen list:

- none

If later implementation proves an existing-table alteration is required, that is a new design change and must not be silently added to `0014`.

### 14.5 Upgrade order

1. `btree_gist` extension
2. holiday calendar header/date tables
3. weather rule config table
4. run parameter package table
5. capacity pool definition/member tables
6. daily capacity table
7. initial inventory snapshot/cohort tables
8. mature inventory loss table
9. indexes and exclusion constraints

### 14.6 Downgrade order

Exact reverse of upgrade order.

### 14.7 Backfill

Frozen decision:

- no automatic backfill
- historical replay remains blocked until explicit authority rows are imported

---

## 15. Future Implementation Phases

### P0-7A - authority ORM/schema contracts

- Scope:
  - SQLAlchemy models
  - Pydantic typed authority schemas
  - canonical payload builders
- Prohibited:
  - replay execution wiring
  - service orchestration changes

### P0-7B - Alembic 0014 and PostgreSQL constraints

- Scope:
  - migration
  - FK / unique / check / exclusion constraints
- Prohibited:
  - loading logic

### P0-7C - authority repositories and canonical hashing

- Scope:
  - create/load repositories
  - idempotency
  - conflict handling
  - semantic hash validation
- Prohibited:
  - Task 11 orchestration wiring

### P0-7D - Task 11 availability/resolver adapters

- Scope:
  - replay authority queries
  - visibility filtering
  - blocker mapping
- Prohibited:
  - Task 9 execution

### P0-7E - Task 9 request loaders

- Scope:
  - `_load_capacity_inputs_typed()`
  - `_load_task9_run_parameters_typed()`
  - source ref construction
- Prohibited:
  - Task 10 replay

### P0-7F - persistence, replay, and E2E integrity

- Scope:
  - real Task9ARequest success path
  - execute/reload parity
  - PostgreSQL replay E2E
- Prohibited:
  - Task 12 work

---

## 16. Acceptance Checklist

- [x] Pure design document only
- [x] No migration created
- [x] No ORM changed
- [x] No production code changed
- [x] No tests changed
- [x] Existing-model inventory completed against current HEAD
- [x] Final authority model set revised under review
- [x] Rejected alternatives documented
- [x] Full Task9ARequest mapping completed
- [x] Visibility / cutoff matrix frozen
- [x] Semantic identity / hash matrix revised
- [x] Holiday request hash vs authority payload hash split
- [x] Business version string vs revision split
- [x] Daily capacity revision frozen
- [x] PostgreSQL 16 constraint strategy chosen
- [x] Blocker taxonomy revised
- [x] DDL draft included
- [x] `0014` boundary frozen
- [x] Downstream snapshots explicitly excluded
- [x] Initial inventory header quantile removed
- [x] Initial inventory cohort quantile added
- [x] SHA-256 regex constraints applied in DDL draft
- [x] NULL-safe subfarm exclusion frozen
- [x] Parent-child copied-field binding frozen
- [x] Status transition matrix frozen
- [x] Run-package-first holiday/weather FK load frozen
- [x] Lexical business-version ordering removed from selection
- [x] ParameterSourceRef matrix frozen
- [x] Holiday duplicate-date semantics frozen

---

## 17. Unresolved Questions

- Awaiting review confirmation that the composite FK parent-child binding on nullable `effective_to` is acceptable for `0014`, or whether the final migration should normalize `effective_to` into a non-null stored column before FK binding.
- Awaiting review confirmation that `status_changed_at` should be mandatory on every authority table in `0014`, rather than introduced in a later status-audit follow-up.
