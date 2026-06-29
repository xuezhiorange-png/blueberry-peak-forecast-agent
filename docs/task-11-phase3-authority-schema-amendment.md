# Task 11 P0-6 - Historical Task 9 Authority Schema and Replay Contract Freeze

**Status**: Design under review. Implementation not started.

**Date**: 2026-06-29
**Repository**: `xuezhiorange-png/blueberry-peak-forecast-agent`
**Branch**: `codex/task-11-rolling-backtest-orchestration`
**Current baseline HEAD**: `6ea240edb2f1d7b83df1dcde10c263cc476483b0`
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
- **Version/status fields**: inherited from parent definition, but copied into child columns for exclusion enforcement only
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
  - `initial_inventory_snapshot_id x stable_cohort_key`
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
| `initial_inventory_cohorts` | `task9_initial_inventory_snapshot` + `task9_initial_inventory_cohort` | snapshot x stable cohort key | `available_at_local_date` | `opening_state_date` | see Section 10 | snapshot hash + cohort hashes | `INITIAL_INVENTORY_SNAPSHOT` refs | `INITIAL_INVENTORY_AUTHORITY_MISSING` |
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

### 10.0 Historical as-of consumability lifecycle

All independent status authority header/value rows must carry:

- `consumable_from_local_date DATE NOT NULL` — the business-local date from which the row becomes visible to historical resolvers
- `consumable_to_local_date DATE NULL` — the business-local date at which the row ceases to be consumable (NULL while open)

Half-open interval:

- `[consumable_from_local_date, consumable_to_local_date)`

Applicable tables (independent status authorities):

- `task9_capacity_pool_definition`
- `task9_daily_capacity_authority`
- `task9_holiday_calendar_version`
- `task9_weather_rule_config_version`
- `task9_run_parameter_package`
- `task9_initial_inventory_snapshot`
- `task9_mature_inventory_loss_authority`

Child tables inherit parent consumability interval:

- `task9_capacity_pool_member`: inherits parent consumability interval
- `task9_holiday_calendar_date`: inherits parent consumability interval
- `task9_initial_inventory_cohort`: inherits parent consumability interval

Children do **not** independently maintain lifecycle intervals.

#### Equality rule

Frozen:

- `node.as_of_local_date == consumable_from_local_date` → visible and consumable
- `node.as_of_local_date == consumable_to_local_date` → **not** consumable

i.e. `[from, to)`.

#### Activation

When a draft authority is first activated:

- `consumable_from_local_date` must be set
- Frozen rule: `consumable_from_local_date = the authority activation business-local date`
- Must satisfy: `consumable_from_local_date >= available_at_local_date`
- If business allows pre-publish / future-effective, `available_at_local_date` and `consumable_from_local_date` may differ; do not assume they are always equal

#### Supersession

Same business scope: A is replaced by B:

- `A.consumable_to_local_date = B.consumable_from_local_date`
- Therefore: `date < B.from → A`; `date >= B.from → B`
- No gap, no overlap, no same-cutoff double selection

#### Retirement and cancellation

Must distinguish semantics. Frozen:

- `active → retired`: close consumability interval at retirement business-local date; no replacement required; `superseded_by_id` remains NULL
- `draft → cancelled`: never becomes consumable; consumability interval must remain absent/unopened
- `active → cancelled`: only allowed if cancellation has an explicit effective local date; close consumability interval at that date

If active cancellation is not allowed, remove from transition matrix. Must not retain ambiguous semantics.

#### Lifecycle interval immutability

Frozen:

- `consumable_from_local_date`: immutable after first activation
- `consumable_to_local_date`: NULL while open; set exactly once when lifecycle closes; immutable after being set

Forbidden:

- move cutoff forward
- move cutoff backward
- reopen closed interval
- rewrite history through interval modification

Any attempt must return: `AUTHORITY_CONSUMABILITY_INTERVAL_CONFLICT`

#### Current status vs historical status responsibilities

Frozen:

- `status`: current operational state
- `consumability interval`: historical as-of selection authority

Current operational queries may use:

```sql
status = 'active'
AND consumable_to_local_date IS NULL
```

Historical resolution must use:

```sql
node.as_of_local_date ∈ consumability interval
```

Even if authority is currently `superseded` or `retired`, as long as the historical cutoff falls within its past consumability interval, it must be selectable by first-time historical resolver.

#### Persisted replay vs first-time resolution

Must distinguish:

- **Persisted exact replay**: load exact persistent reference; recompute and verify hash; do not re-resolve
- **First-time historical resolution**: select authority by visibility + historical consumability + effective applicability

Both paths must fail closed, but semantics differ.

#### Frozen selection rules

**Current operational requirement:**

- `status = 'active'`
- `consumable_to_local_date IS NULL`

**Historical as-of requirement:**

- `status IN ('active', 'superseded', 'retired')`
- `consumable_from_local_date <= :node_as_of_local_date`
- `(:node_as_of_local_date < consumable_to_local_date) OR (consumable_to_local_date IS NULL)`

Status does **not** enter semantic payload hashes. It only participates in SQL selection and consumability validation.

### 10.1 Frozen status transition matrix

- `draft -> active`
- `draft -> cancelled`
- `active -> superseded`
- `active -> retired`
- `active -> cancelled` (only allowed if cancellation has an explicit effective local date and interval closure is defined)
- `superseded` → **terminal** (no transition out)
- `retired` → **terminal** (no transition out)
- `cancelled` → **terminal** (no transition out)

Forbidden transitions:

- `superseded -> active`
- `superseded -> retired` — **removed**: superseded is terminal; clearing `superseded_by_id` would lose lineage
- `superseded -> cancelled`
- `retired -> active`
- `retired -> cancelled`
- `cancelled -> active`
- `cancelled -> retired`

### 10.2 Immutable business payload vs mutable metadata

- business payload columns are immutable after insert
- mutable metadata is limited to:
  - `status`
  - `status_changed_at`
  - `superseded_by_id` on rows that enter `superseded`
- `superseded_by_id`:
  - set once during `active → superseded`
  - never cleared
  - never changed
  - superseded permanently retains replacement lineage
- direct retirement (`active → retired`):
  - no replacement
  - `superseded_by_id IS NULL`
  - sets `consumable_to_local_date`
  - historical interval is preserved

### 10.3 Parent/member synchronization

`task9_capacity_pool_member` is not an independent status authority.

Frozen child-row status rules:

- child `status` exists only because exclusion and composite-FK enforcement need copied parent fields
- child `status` is copied from parent only
- child does not own independent `status_changed_at`
- child does not own independent `superseded_by_id`
- `task9_capacity_pool_member`: has copied parent status; copied status is `draft` through parent binding
- `task9_holiday_calendar_date`: no independent status
- `task9_initial_inventory_cohort`: no independent status

Must not assign `draft` status to children that have no status column. Must not invent status for children that do not own it.

Parent/member synchronization is database-driven:

- parent status update uses composite FK with `ON UPDATE CASCADE`
- child copied `status` follows parent automatically
- repository must not issue separate parent-status and child-status mutations

### 10.4 Active replacement transaction

Replacement of one active authority row with a new active row must occur as:

1. lock current active row
2. insert replacement authority row as `draft`
3. insert immutable child rows under the draft parent, when the authority has child rows
4. update current active row to:
   - `status = 'superseded'`
   - `superseded_by_id = replacement.id`
   - `status_changed_at = transaction timestamp`
5. let `ON UPDATE CASCADE` propagate copied member status on the old pool
6. update replacement row to:
   - `status = 'active'`
   - `status_changed_at = transaction timestamp`
7. let `ON UPDATE CASCADE` propagate copied member status on the replacement pool
8. commit atomically
- replacement is inserted as `draft` first so it:
  - does not participate in active-only unique indexes
  - does not participate in active-only exclusion constraints
  - already exists as a valid self-FK target for `superseded_by_id`
- any failure rolls back the entire transaction; no draft orphan, partial supersession, or parent/member divergence is allowed
- immediate self-FKs are retained; no deferred constraints are introduced
- repository implementation must lock the current active row before replacement insert/update

Only `active` rows participate in exclusion constraints. `superseded`, `retired`, and `cancelled` rows do not.

### 10.5 Supersession integrity

Independent status authorities support `superseded_by_id` only on header/value rows:

- `task9_capacity_pool_definition`
- `task9_daily_capacity_authority`
- `task9_holiday_calendar_version`
- `task9_weather_rule_config_version`
- `task9_run_parameter_package`
- `task9_initial_inventory_snapshot`
- `task9_mature_inventory_loss_authority`

Child tables do not support independent supersession metadata:

- `task9_capacity_pool_member`
- `task9_holiday_calendar_date`
- `task9_initial_inventory_cohort`

Database rules:

- self-FK on `superseded_by_id`
- `superseded_by_id <> id`
- `status = 'superseded'` iff `superseded_by_id IS NOT NULL`

Repository integrity rules must also validate same-scope replacement:

- capacity pool definition:
  - same `season_id + destination_factory_id + capacity_pool_code`
- daily capacity:
  - same `capacity_pool_definition_id + capacity_date`
- holiday calendar:
  - same `season_id + calendar_code`
- weather rule:
  - same `rule_code`
- run parameter package:
  - same `season_id + destination_factory_id + farm_scope_key`
- initial inventory:
  - same `season_id + destination_factory_id + opening_state_date`
- mature loss:
  - same `season_id + destination_factory_id + state_date + capacity_pool_code + forecast_quantile`

Scope mismatch must fail with blocker:

- `AUTHORITY_SUPERSESSION_SCOPE_CONFLICT`

Supersession interval consistency must be validated:

- `old.superseded_by_id = new.id`
- `old.consumable_to_local_date = new.consumable_from_local_date`
- old and new have same frozen business scope

Failure must return:

- `AUTHORITY_SUPERSESSION_SCOPE_CONFLICT` (scope mismatch)
- `AUTHORITY_CONSUMABILITY_INTERVAL_CONFLICT` (interval mismatch)

### 10.6 Selection matrix

| Authority | Visibility predicate | Historical consumability predicate | Effective/applicable predicate | Current operational status | Expected cardinality | Tie-break / ORDER BY | Ambiguity blocker |
|---|---|---|---|---|---:|---|---|
| capacity pool definition | scope + available_at ≤ as_of | from ≤ as_of AND (to IS NULL OR as_of < to) | effective interval contains as_of | `active` + `consumable_to IS NULL` | 0..1 per pool code | none; uniqueness/exclusion yields 0..1 | `CAPACITY_POOL_AUTHORITY_AMBIGUOUS` |
| daily capacity | parent visible/effective + capacity_date in window | from ≤ as_of AND (to IS NULL OR as_of < to) | capacity_date ∈ forecast window | parent `active` + parent `consumable_to IS NULL` | 0..1 per pool/date after highest revision | `revision DESC, available_at_local_date DESC, row_hash ASC` | `CAPACITY_VALUE_AUTHORITY_AMBIGUOUS` |
| run-parameter package | scope + available_at ≤ as_of | from ≤ as_of AND (to IS NULL OR as_of < to) | effective interval contains as_of | `active` + `consumable_to IS NULL` | 0..1 | none; overlap exclusion yields 0..1 | `RUN_PARAMETER_AUTHORITY_AMBIGUOUS` |
| holiday calendar | exact FK load from selected run package | from ≤ as_of AND (to IS NULL OR as_of < to) | — | `active` + `consumable_to IS NULL` (current) **or** historically consumable at original cutoff (first-time) | exactly 1 referenced row | none; FK target exact load | `HOLIDAY_CALENDAR_REFERENCE_INVALID` |
| weather rule config | exact FK load from selected run package | from ≤ as_of AND (to IS NULL OR as_of < to) | — | `active` + `consumable_to IS NULL` (current) **or** historically consumable at original cutoff (first-time) | exactly 1 referenced row | none; FK target exact load | `WEATHER_RULE_REFERENCE_INVALID` |
| initial inventory snapshot | scope + available_at ≤ as_of + opening_state_date | from ≤ as_of AND (to IS NULL OR as_of < to) | opening_state_date | `active` + `consumable_to IS NULL` | 0..1 per opening state date | `revision DESC, available_at_local_date DESC, row_hash ASC` | `INITIAL_INVENTORY_AUTHORITY_AMBIGUOUS` |
| mature inventory loss | scope + available_at ≤ as_of + state_date | from ≤ as_of AND (to IS NULL OR as_of < to) | state_date | `active` + `consumable_to IS NULL` | 0..1 per date/pool/quantile | `revision DESC, available_at_local_date DESC, row_hash ASC` | `MATURE_INVENTORY_LOSS_AUTHORITY_AMBIGUOUS` |

Selection logic must distinguish three paths:

- **First-time historical run**: use historical consumability predicate; status may be `active`, `superseded`, or `retired` as long as the historical cutoff falls within the consumability interval
- **Persisted exact replay**: load exact persistent reference and verify hash; do not re-resolve; verify that the referenced row was historically consumable at the original cutoff
- **Current resolution**: use current operational status (`active` + open interval)

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

- Capacity pool definitions may not have overlapping consumability intervals for the same:
  - `season_id`
  - `destination_factory_id`
  - `capacity_pool_code`
- Capacity members may not belong to overlapping consumable pools for the same:
  - `season_id`
  - `destination_factory_id`
  - `farm_id`
  - `subfarm_id`
  - `variety_id`
- Run-parameter packages may not have overlapping consumability intervals for the same:
  - `season_id`
  - `destination_factory_id`
  - `farm_scope_key`
- Daily capacity rows are unique per:
  - `capacity_pool_definition_id`
  - `capacity_date`
  - `revision`
- Daily capacity rows may not have overlapping consumability intervals for the same:
  - `capacity_pool_definition_id`
  - `capacity_date`
- Initial inventory snapshots are unique per:
  - `season_id`
  - `destination_factory_id`
  - `opening_state_date`
  - `snapshot_version`
  - `revision`
- Initial inventory snapshots may not have overlapping consumability intervals for the same:
  - `season_id`
  - `destination_factory_id`
  - `opening_state_date`
- Mature inventory loss rows are unique per:
  - `season_id`
  - `destination_factory_id`
  - `state_date`
  - `capacity_pool_code`
  - `forecast_quantile`
  - `loss_version`
  - `revision`
- Mature inventory loss rows may not have overlapping consumability intervals for the same:
  - `season_id`
  - `destination_factory_id`
  - `state_date`
  - `capacity_pool_code`
  - `forecast_quantile`
- Holiday calendar versions may not have overlapping consumability intervals for the same:
  - `season_id`
  - `calendar_code`
- Weather rule config versions may not have overlapping consumability intervals for the same:
  - `rule_code`

PostgreSQL strategy for consumability non-overlap:

- generated `daterange` over `consumable_from/to`:
  ```sql
  consumability_range DATERANGE GENERATED ALWAYS AS (
      daterange(
          consumable_from_local_date,
          CASE
              WHEN consumable_to_local_date IS NULL THEN 'infinity'::date
              ELSE consumable_to_local_date
          END,
          '[)'
      )
  ) STORED
  ```
- `EXCLUDE USING gist` for overlapping consumable intervals
- Generated-column rule continues: no generated column may reference another generated column
- Same-date replacement: the old row must have at least one consumable date; if same-day creation-and-replacement is allowed, the interval `[date, date+1)` is valid

Current one-active indexes may be retained, but must document:

- current active uniqueness ≠ historical as-of non-overlap
- both are required; they serve different purposes

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
  - `effective_to_exclusive DATE GENERATED ALWAYS AS (CASE WHEN effective_to IS NULL THEN 'infinity'::date ELSE effective_to + 1 END) STORED`
- parent and child both generate `effective_to_exclusive` and `effective_range` independently from the same base columns:
  - base columns are `effective_from` and `effective_to`
  - `effective_range` must not reference `effective_to_exclusive`, because PostgreSQL 16 does not allow generated-column chaining
- parent gets composite uniqueness on:
  - `(id, season_id, destination_factory_id, effective_from, effective_to_exclusive, status)`
- child stores copied `effective_from`, nullable `effective_to`, copied `status`, and generates its own `effective_to_exclusive` from the same expression
- child gets composite FK on:
  - `(capacity_pool_definition_id, season_id, destination_factory_id, effective_from, effective_to_exclusive, status)`
- composite FK uses `ON UPDATE CASCADE`
- child and parent must reject divergent normalized ends; a child row with different `effective_to` cannot match the parent composite key
- exclusion constraints continue to use `effective_range`, but that range must be generated directly from `effective_from` and `effective_to`
- no triggers

Open-ended interval rules:

- open-ended rows use PostgreSQL `infinity` date, not a finite sentinel such as `9999-12-31`
- both parent and child must enforce:
  - `effective_to IS NULL OR (effective_to >= effective_from AND effective_to < 'infinity'::date)`

### 11.5 One-active invariants

Revision-inclusive uniqueness is not enough to guarantee a single consumable authority row. The design freezes partial unique indexes for all independently versioned value/header tables that can be resolver-selected:

- `uq_task9_daily_capacity_one_active`
  - `(capacity_pool_definition_id, capacity_date)` where `status = 'active'`
- `uq_task9_initial_inventory_one_active`
  - `(season_id, destination_factory_id, opening_state_date)` where `status = 'active'`
- `uq_task9_mature_loss_one_active`
  - `(season_id, destination_factory_id, state_date, capacity_pool_code, forecast_quantile)` where `status = 'active'`
- `uq_task9_holiday_calendar_one_active`
  - `(season_id, calendar_code)` where `status = 'active'`
- `uq_task9_weather_rule_one_active`
  - `(rule_code)` where `status = 'active'`

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
- `AUTHORITY_SUPERSESSION_SCOPE_CONFLICT`
- `AUTHORITY_HASH_CONFLICT`
- `AUTHORITY_VERSION_CONFLICT`
- `AUTHORITY_STATUS_NOT_CONSUMABLE`
- `AUTHORITY_CONSUMABILITY_INTERVAL_INVALID`
- `AUTHORITY_CONSUMABILITY_INTERVAL_OVERLAP`
- `AUTHORITY_CONSUMABILITY_INTERVAL_CONFLICT`
- `AUTHORITY_NOT_CONSUMABLE_AT_CUTOFF`

These are in addition to existing Task 6 / Task 7 / Task 8 / Task 9 blocker families.

Frozen semantic definitions for new consumability blockers:

- `AUTHORITY_CONSUMABILITY_INTERVAL_INVALID`: from/to format or ordering is invalid
- `AUTHORITY_CONSUMABILITY_INTERVAL_OVERLAP`: same business scope intervals overlap
- `AUTHORITY_CONSUMABILITY_INTERVAL_CONFLICT`: lifecycle transition attempts to rewrite or inconsistently close history
- `AUTHORITY_NOT_CONSUMABLE_AT_CUTOFF`: exact referenced row was not consumable at the requested historical cutoff

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
| `HOLIDAY_CALENDAR` | `task9_holiday_calendar_version` | season x calendar_version x revision | `task9_historical_authority` | `holiday-calendar:{season_id}:{calendar_code}:{calendar_version}:{revision}` | `calendar_version` | holiday header `row_hash` | holiday `available_at_local_date` | node `as_of_date` | unique holiday header row | all modes | none | exactly one |
| `WEATHER_RULE_CONFIG` | `task9_weather_rule_config_version` | rule_version x revision | `task9_historical_authority` | `weather-rule:{rule_code}:{rule_version}:{revision}` | `rule_version` | weather-rule `row_hash` | rule `available_at_local_date` | node `as_of_date` | unique weather-rule row | all modes | none | exactly one |
| `HARVEST_TO_ARRIVAL_LAG` | `task9_run_parameter_package` | run package row | `task9_historical_authority` | `run-package:{season_id}:{destination_factory_id}:{farm_scope_key}:{package_version}:{revision}` | `package_version` | run-package `row_hash` | package `available_at_local_date` | node `as_of_date` | shared run-package row | all modes | none | exactly one |
| `TIMEZONE_CONFIG` | `task9_run_parameter_package` | run package row | `task9_historical_authority` | `run-package:{season_id}:{destination_factory_id}:{farm_scope_key}:{package_version}:{revision}` | `package_version` | run-package `row_hash` | package `available_at_local_date` | node `as_of_date` | shared run-package row | all modes | none | exactly one |
| `HARVEST_BUCKET_ANCHOR_TIME` | `task9_run_parameter_package` | run package row | `task9_historical_authority` | `run-package:{season_id}:{destination_factory_id}:{farm_scope_key}:{package_version}:{revision}` | `package_version` | run-package `row_hash` | package `available_at_local_date` | node `as_of_date` | shared run-package row | all modes | none | exactly one |

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

- `daily-capacity:{capacity_pool_code}:{capacity_pool_version}:{capacity_date}:{revision}`

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

- `daily-capacity:{capacity_pool_code}:{capacity_pool_version}:{capacity_date}:{revision}`

Capacity refs may share one authority row hash, but each parameter code still requires its own `ParameterSourceRef`.

### 12A.4 Mature loss

| parameter_code | authority table | source_system | source_record_key format | source_version | source_row_hash | available_at | as_of_date | exactly-one rule |
|---|---|---|---|---|---|---|---|---|
| `MATURE_INVENTORY_LOSS` | `task9_mature_inventory_loss_authority` | `task9_historical_authority` | `mature-loss:{season_id}:{destination_factory_id}:{capacity_pool_code}:{state_date}:{forecast_quantile}:{loss_version}:{revision}` | `loss_version` | mature-loss `row_hash` | mature-loss `available_at_local_date` | node `as_of_date` | exactly one per state_date x pool x quantile |

### 12A.5 Frozen authority-family prefixes

Every new Task 9 historical authority row must use a globally unambiguous `source_record_key` under the shared `source_system = task9_historical_authority`.

Frozen prefixes:

- run package:
  - `run-package:{season_id}:{destination_factory_id}:{farm_scope_key}:{package_version}:{revision}`
- daily capacity:
  - `daily-capacity:{capacity_pool_code}:{capacity_pool_version}:{capacity_date}:{revision}`
- holiday calendar:
  - `holiday-calendar:{season_id}:{calendar_code}:{calendar_version}:{revision}`
- weather rule:
  - `weather-rule:{rule_code}:{rule_version}:{revision}`
- initial inventory snapshot:
  - `initial-inventory:{season_id}:{destination_factory_id}:{opening_state_date}:{snapshot_version}:{revision}`
- mature loss:
  - `mature-loss:{season_id}:{destination_factory_id}:{capacity_pool_code}:{state_date}:{forecast_quantile}:{loss_version}:{revision}`

Prohibited in `source_record_key`:

- table row IDs
- UUIDs
- repository/runtime identities

---

## 12B. Run-package dependency lifecycle

Frozen invariant:

- an active `task9_run_parameter_package` must always reference:
  - one active `task9_holiday_calendar_version`
  - one active `task9_weather_rule_config_version`

This invariant is enforced by repository transaction ordering plus load-time integrity validation. A plain database FK only proves existence, not consumable status.

### 12B.1 Dependency-aware replacement order

When holiday and/or weather-rule authority changes together with the run package, the replacement transaction must occur as:

1. lock the current active run package
2. lock the currently referenced active holiday row
3. lock the currently referenced active weather-rule row
4. insert the replacement holiday row as `draft`
5. insert replacement holiday-date child rows (immutable under draft parent)
6. insert the replacement weather-rule row as `draft`
7. insert the replacement run package as `draft`, referencing the new draft holiday/weather rows
8. supersede the old active run package and set `superseded_by_id`
9. supersede the old holiday row and set `superseded_by_id`
10. supersede the old weather-rule row and set `superseded_by_id`
11. activate the replacement holiday row
12. activate the replacement weather-rule row
13. activate the replacement run package
14. commit atomically

Interval actions during replacement:

- old holiday: set `consumable_to_local_date = replacement boundary`
- old weather-rule: set `consumable_to_local_date = replacement boundary`
- old run package: set `consumable_to_local_date = replacement boundary`
- new holiday: set `consumable_from_local_date = replacement boundary`
- new weather-rule: set `consumable_from_local_date = replacement boundary`
- new run package: set `consumable_from_local_date = replacement boundary`

Frozen invariant:

- old package and old dependencies close at the same boundary
- new package and new dependencies open at the same boundary
- historically: before boundary → old package + old dependencies valid; at/after boundary → new package + new dependencies valid
- no cross-version combination is possible

Why the old run package is superseded first:

- an active run package must never point at a superseded holiday row
- an active run package must never point at a superseded weather-rule row
- therefore the active package must exit `active` before the old dependencies do

### 12B.2 Standalone dependency supersession

If a caller attempts to supersede, retire, or cancel a holiday or weather-rule row on its own:

1. query active run packages referencing that row
2. if any active package remains outside the current replacement transaction, reject the transition

Frozen blockers:

- `RUN_PARAMETER_DEPENDENCY_STATUS_CONFLICT`
  - loaded run package references a dependency whose status is not active
- `AUTHORITY_STILL_REFERENCED_BY_ACTIVE_PACKAGE`
  - holiday or weather-rule supersession/retirement/cancellation is attempted while still referenced by an active run package

### 12B.3 Load integrity

Loading an active run package must verify:

- holiday target exists
- weather target exists
- holiday target `status = 'active'` (current resolution) **or** historically consumable at node cutoff (first-time historical)
- weather target `status = 'active'` (current resolution) **or** historically consumable at node cutoff (first-time historical)
- holiday target consumability interval covers node local cutoff
- weather target consumability interval covers node local cutoff
- scope compatibility holds
- row/config hashes recompute successfully

Persisted exact replay: load exact row and verify that its historical lifecycle proves it was consumable at the original cutoff; does not require it to be currently active.

Exact FK loading remains required. Resolver logic must not repair broken references by independently selecting a "latest" holiday or weather row.

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
        CASE
            WHEN effective_to IS NULL THEN 'infinity'::date
            ELSE effective_to + 1
        END
    ) STORED,
    effective_range DATERANGE GENERATED ALWAYS AS (
        daterange(
            effective_from,
            CASE
                WHEN effective_to IS NULL THEN 'infinity'::date
                ELSE effective_to + 1
            END,
            '[)'
        )
    ) STORED,
    available_at_local_date DATE NOT NULL,
    consumable_from_local_date DATE,
    consumable_to_local_date DATE,
    consumability_range DATERANGE GENERATED ALWAYS AS (
        daterange(
            COALESCE(consumable_from_local_date, 'infinity'::date),
            CASE
                WHEN consumable_to_local_date IS NULL THEN 'infinity'::date
                ELSE consumable_to_local_date
            END,
            '[)'
        )
    ) STORED,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
    status_changed_at TIMESTAMPTZ NOT NULL,
    source_system TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    source_version TEXT NOT NULL,
    row_hash TEXT NOT NULL
        CONSTRAINT ck_task9_capacity_pool_definition_row_hash_sha256
        CHECK (row_hash ~ '^[0-9a-f]{64}$'),
    superseded_by_id BIGINT NULL
        REFERENCES task9_capacity_pool_definition(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (season_id, destination_factory_id, capacity_pool_code, capacity_pool_version, revision),
    UNIQUE (id, season_id, destination_factory_id, effective_from, effective_to_exclusive, status),
    CHECK (effective_to IS NULL OR (effective_to >= effective_from AND effective_to < 'infinity'::date)),
    CHECK (superseded_by_id IS NULL OR superseded_by_id <> id),
    CHECK (
        (status = 'superseded' AND superseded_by_id IS NOT NULL)
        OR (status <> 'superseded' AND superseded_by_id IS NULL)
    ),
    CHECK (
        (status = 'draft' AND consumable_from_local_date IS NULL)
        OR (status IN ('active', 'superseded', 'retired') AND consumable_from_local_date IS NOT NULL)
        OR (status = 'cancelled' AND consumable_from_local_date IS NULL)
    ),
    CHECK (
        consumable_to_local_date IS NULL
        OR consumable_to_local_date > consumable_from_local_date
    )
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
    effective_to_exclusive DATE GENERATED ALWAYS AS (
        CASE
            WHEN effective_to IS NULL THEN 'infinity'::date
            ELSE effective_to + 1
        END
    ) STORED,
    effective_range DATERANGE GENERATED ALWAYS AS (
        daterange(
            effective_from,
            CASE
                WHEN effective_to IS NULL THEN 'infinity'::date
                ELSE effective_to + 1
            END,
            '[)'
        )
    ) STORED,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
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
    CHECK (effective_to IS NULL OR (effective_to >= effective_from AND effective_to < 'infinity'::date)),
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
    ON UPDATE CASCADE
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
    consumable_from_local_date DATE,
    consumable_to_local_date DATE,
    consumability_range DATERANGE GENERATED ALWAYS AS (
        daterange(
            COALESCE(consumable_from_local_date, 'infinity'::date),
            CASE
                WHEN consumable_to_local_date IS NULL THEN 'infinity'::date
                ELSE consumable_to_local_date
            END,
            '[)'
        )
    ) STORED,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
    status_changed_at TIMESTAMPTZ NOT NULL,
    superseded_by_id BIGINT NULL
        REFERENCES task9_daily_capacity_authority(id) ON DELETE RESTRICT,
    source_system TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    source_version TEXT NOT NULL,
    row_hash TEXT NOT NULL
        CONSTRAINT ck_task9_daily_capacity_authority_row_hash_sha256
        CHECK (row_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (capacity_pool_definition_id, capacity_date, revision),
    CHECK (superseded_by_id IS NULL OR superseded_by_id <> id),
    CHECK (
        (status = 'superseded' AND superseded_by_id IS NOT NULL)
        OR (status <> 'superseded' AND superseded_by_id IS NULL)
    ),
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
    ),
    CHECK (
        (status = 'draft' AND consumable_from_local_date IS NULL)
        OR (status IN ('active', 'superseded', 'retired') AND consumable_from_local_date IS NOT NULL)
        OR (status = 'cancelled' AND consumable_from_local_date IS NULL)
    ),
    CHECK (
        consumable_to_local_date IS NULL
        OR consumable_to_local_date > consumable_from_local_date
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
    consumable_from_local_date DATE,
    consumable_to_local_date DATE,
    consumability_range DATERANGE GENERATED ALWAYS AS (
        daterange(
            COALESCE(consumable_from_local_date, 'infinity'::date),
            CASE
                WHEN consumable_to_local_date IS NULL THEN 'infinity'::date
                ELSE consumable_to_local_date
            END,
            '[)'
        )
    ) STORED,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
    status_changed_at TIMESTAMPTZ NOT NULL,
    superseded_by_id BIGINT NULL
        REFERENCES task9_holiday_calendar_version(id) ON DELETE RESTRICT,
    source_system TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    source_version TEXT NOT NULL,
    row_hash TEXT NOT NULL
        CONSTRAINT ck_task9_holiday_calendar_version_row_hash_sha256
        CHECK (row_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (season_id, calendar_code, calendar_version, revision),
    CHECK (superseded_by_id IS NULL OR superseded_by_id <> id),
    CHECK (
        (status = 'superseded' AND superseded_by_id IS NOT NULL)
        OR (status <> 'superseded' AND superseded_by_id IS NULL)
    ),
    CHECK (
        (status = 'draft' AND consumable_from_local_date IS NULL)
        OR (status IN ('active', 'superseded', 'retired') AND consumable_from_local_date IS NOT NULL)
        OR (status = 'cancelled' AND consumable_from_local_date IS NULL)
    ),
    CHECK (
        consumable_to_local_date IS NULL
        OR consumable_to_local_date > consumable_from_local_date
    )
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
    consumable_from_local_date DATE,
    consumable_to_local_date DATE,
    consumability_range DATERANGE GENERATED ALWAYS AS (
        daterange(
            COALESCE(consumable_from_local_date, 'infinity'::date),
            CASE
                WHEN consumable_to_local_date IS NULL THEN 'infinity'::date
                ELSE consumable_to_local_date
            END,
            '[)'
        )
    ) STORED,
    effective_from DATE NOT NULL,
    effective_to DATE,
    effective_to_exclusive DATE GENERATED ALWAYS AS (
        CASE
            WHEN effective_to IS NULL THEN 'infinity'::date
            ELSE effective_to + 1
        END
    ) STORED,
    effective_range DATERANGE GENERATED ALWAYS AS (
        daterange(
            effective_from,
            CASE
                WHEN effective_to IS NULL THEN 'infinity'::date
                ELSE effective_to + 1
            END,
            '[)'
        )
    ) STORED,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
    status_changed_at TIMESTAMPTZ NOT NULL,
    superseded_by_id BIGINT NULL
        REFERENCES task9_weather_rule_config_version(id) ON DELETE RESTRICT,
    source_system TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    source_version TEXT NOT NULL,
    row_hash TEXT NOT NULL
        CONSTRAINT ck_task9_weather_rule_config_version_row_hash_sha256
        CHECK (row_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (rule_code, rule_version, revision),
    CHECK (maximum_ratio >= minimum_ratio),
    CHECK (effective_to IS NULL OR (effective_to >= effective_from AND effective_to < 'infinity'::date)),
    CHECK (superseded_by_id IS NULL OR superseded_by_id <> id),
    CHECK (
        (status = 'superseded' AND superseded_by_id IS NOT NULL)
        OR (status <> 'superseded' AND superseded_by_id IS NULL)
    ),
    CHECK (
        (status = 'draft' AND consumable_from_local_date IS NULL)
        OR (status IN ('active', 'superseded', 'retired') AND consumable_from_local_date IS NOT NULL)
        OR (status = 'cancelled' AND consumable_from_local_date IS NULL)
    ),
    CHECK (
        consumable_to_local_date IS NULL
        OR consumable_to_local_date > consumable_from_local_date
    )
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
    consumable_from_local_date DATE,
    consumable_to_local_date DATE,
    consumability_range DATERANGE GENERATED ALWAYS AS (
        daterange(
            COALESCE(consumable_from_local_date, 'infinity'::date),
            CASE
                WHEN consumable_to_local_date IS NULL THEN 'infinity'::date
                ELSE consumable_to_local_date
            END,
            '[)'
        )
    ) STORED,
    effective_from DATE NOT NULL,
    effective_to DATE,
    effective_to_exclusive DATE GENERATED ALWAYS AS (
        CASE
            WHEN effective_to IS NULL THEN 'infinity'::date
            ELSE effective_to + 1
        END
    ) STORED,
    effective_range DATERANGE GENERATED ALWAYS AS (
        daterange(
            effective_from,
            CASE
                WHEN effective_to IS NULL THEN 'infinity'::date
                ELSE effective_to + 1
            END,
            '[)'
        )
    ) STORED,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
    status_changed_at TIMESTAMPTZ NOT NULL,
    superseded_by_id BIGINT NULL
        REFERENCES task9_run_parameter_package(id) ON DELETE RESTRICT,
    source_system TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    source_version TEXT NOT NULL,
    row_hash TEXT NOT NULL
        CONSTRAINT ck_task9_run_parameter_package_row_hash_sha256
        CHECK (row_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (season_id, destination_factory_id, farm_scope_key, package_version, revision),
    CHECK (effective_to IS NULL OR (effective_to >= effective_from AND effective_to < 'infinity'::date)),
    CHECK (superseded_by_id IS NULL OR superseded_by_id <> id),
    CHECK (
        (status = 'superseded' AND superseded_by_id IS NOT NULL)
        OR (status <> 'superseded' AND superseded_by_id IS NULL)
    ),
    CHECK (
        (status = 'draft' AND consumable_from_local_date IS NULL)
        OR (status IN ('active', 'superseded', 'retired') AND consumable_from_local_date IS NOT NULL)
        OR (status = 'cancelled' AND consumable_from_local_date IS NULL)
    ),
    CHECK (
        consumable_to_local_date IS NULL
        OR consumable_to_local_date > consumable_from_local_date
    )
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
    consumable_from_local_date DATE,
    consumable_to_local_date DATE,
    consumability_range DATERANGE GENERATED ALWAYS AS (
        daterange(
            COALESCE(consumable_from_local_date, 'infinity'::date),
            CASE
                WHEN consumable_to_local_date IS NULL THEN 'infinity'::date
                ELSE consumable_to_local_date
            END,
            '[)'
        )
    ) STORED,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
    status_changed_at TIMESTAMPTZ NOT NULL,
    superseded_by_id BIGINT NULL
        REFERENCES task9_initial_inventory_snapshot(id) ON DELETE RESTRICT,
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
    ),
    CHECK (superseded_by_id IS NULL OR superseded_by_id <> id),
    CHECK (
        (status = 'superseded' AND superseded_by_id IS NOT NULL)
        OR (status <> 'superseded' AND superseded_by_id IS NULL)
    ),
    CHECK (
        (status = 'draft' AND consumable_from_local_date IS NULL)
        OR (status IN ('active', 'superseded', 'retired') AND consumable_from_local_date IS NOT NULL)
        OR (status = 'cancelled' AND consumable_from_local_date IS NULL)
    ),
    CHECK (
        consumable_to_local_date IS NULL
        OR consumable_to_local_date > consumable_from_local_date
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
    UNIQUE (initial_inventory_snapshot_id, stable_cohort_key)
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
    consumable_from_local_date DATE,
    consumable_to_local_date DATE,
    consumability_range DATERANGE GENERATED ALWAYS AS (
        daterange(
            COALESCE(consumable_from_local_date, 'infinity'::date),
            CASE
                WHEN consumable_to_local_date IS NULL THEN 'infinity'::date
                ELSE consumable_to_local_date
            END,
            '[)'
        )
    ) STORED,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
    status_changed_at TIMESTAMPTZ NOT NULL,
    superseded_by_id BIGINT NULL
        REFERENCES task9_mature_inventory_loss_authority(id) ON DELETE RESTRICT,
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
    ),
    CHECK (superseded_by_id IS NULL OR superseded_by_id <> id),
    CHECK (
        (status = 'superseded' AND superseded_by_id IS NOT NULL)
        OR (status <> 'superseded' AND superseded_by_id IS NULL)
    ),
    CHECK (
        (status = 'draft' AND consumable_from_local_date IS NULL)
        OR (status IN ('active', 'superseded', 'retired') AND consumable_from_local_date IS NOT NULL)
        OR (status = 'cancelled' AND consumable_from_local_date IS NULL)
    ),
    CHECK (
        consumable_to_local_date IS NULL
        OR consumable_to_local_date > consumable_from_local_date
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

CREATE UNIQUE INDEX uq_task9_daily_capacity_one_active
    ON task9_daily_capacity_authority(capacity_pool_definition_id, capacity_date)
    WHERE (status = 'active');
CREATE UNIQUE INDEX uq_task9_initial_inventory_one_active
    ON task9_initial_inventory_snapshot(season_id, destination_factory_id, opening_state_date)
    WHERE (status = 'active');
CREATE UNIQUE INDEX uq_task9_mature_loss_one_active
    ON task9_mature_inventory_loss_authority(
        season_id,
        destination_factory_id,
        state_date,
        capacity_pool_code,
        forecast_quantile
    )
    WHERE (status = 'active');
CREATE UNIQUE INDEX uq_task9_holiday_calendar_one_active
    ON task9_holiday_calendar_version(season_id, calendar_code)
    WHERE (status = 'active');
CREATE UNIQUE INDEX uq_task9_weather_rule_one_active
    ON task9_weather_rule_config_version(rule_code)
    WHERE (status = 'active');

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

-- Historical consumability interval exclusion constraints
-- These prevent overlapping consumability intervals for the same business scope.

ALTER TABLE task9_capacity_pool_definition
    ADD CONSTRAINT ex_task9_capacity_pool_consumability_overlap
    EXCLUDE USING gist (
        season_id WITH =,
        destination_factory_id WITH =,
        capacity_pool_code WITH =,
        consumability_range WITH &&
    );

ALTER TABLE task9_daily_capacity_authority
    ADD CONSTRAINT ex_task9_daily_capacity_consumability_overlap
    EXCLUDE USING gist (
        capacity_pool_definition_id WITH =,
        capacity_date WITH =,
        consumability_range WITH &&
    );

ALTER TABLE task9_holiday_calendar_version
    ADD CONSTRAINT ex_task9_holiday_calendar_consumability_overlap
    EXCLUDE USING gist (
        season_id WITH =,
        calendar_code WITH =,
        consumability_range WITH &&
    );

ALTER TABLE task9_weather_rule_config_version
    ADD CONSTRAINT ex_task9_weather_rule_consumability_overlap
    EXCLUDE USING gist (
        rule_code WITH =,
        consumability_range WITH &&
    );

ALTER TABLE task9_run_parameter_package
    ADD CONSTRAINT ex_task9_run_parameter_consumability_overlap
    EXCLUDE USING gist (
        season_id WITH =,
        destination_factory_id WITH =,
        farm_scope_key WITH =,
        consumability_range WITH &&
    );

ALTER TABLE task9_initial_inventory_snapshot
    ADD CONSTRAINT ex_task9_initial_inventory_consumability_overlap
    EXCLUDE USING gist (
        season_id WITH =,
        destination_factory_id WITH =,
        opening_state_date WITH =,
        consumability_range WITH &&
    );

ALTER TABLE task9_mature_inventory_loss_authority
    ADD CONSTRAINT ex_task9_mature_loss_consumability_overlap
    EXCLUDE USING gist (
        season_id WITH =,
        destination_factory_id WITH =,
        state_date WITH =,
        capacity_pool_code WITH =,
        forecast_quantile WITH =,
        consumability_range WITH &&
    );
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
- generated effective-bound and range columns:
  - `task9_capacity_pool_definition.effective_to_exclusive`
  - `task9_capacity_pool_definition.effective_range`
  - `task9_capacity_pool_member.effective_to_exclusive`
  - `task9_capacity_pool_member.effective_range`
  - `task9_capacity_pool_member.normalized_subfarm_id`
  - `task9_weather_rule_config_version.effective_to_exclusive`
  - `task9_weather_rule_config_version.effective_range`
  - `task9_run_parameter_package.effective_to_exclusive`
  - `task9_run_parameter_package.effective_range`
- generated consumability range columns:
  - `task9_capacity_pool_definition.consumability_range`
  - `task9_daily_capacity_authority.consumability_range`
  - `task9_holiday_calendar_version.consumability_range`
  - `task9_weather_rule_config_version.consumability_range`
  - `task9_run_parameter_package.consumability_range`
  - `task9_initial_inventory_snapshot.consumability_range`
  - `task9_mature_inventory_loss_authority.consumability_range`
- lifecycle CHECK constraints:
  - status-consumability alignment: `draft`/`cancelled` → NULL from; `active`/`superseded`/`retired` → NOT NULL from
  - range validity: `consumable_to IS NULL OR consumable_to > consumable_from`
- historical consumability exclusion constraints:
  - `ex_task9_daily_capacity_consumability_overlap`
  - `ex_task9_initial_inventory_consumability_overlap`
  - `ex_task9_mature_loss_consumability_overlap`
  - `ex_task9_holiday_calendar_consumability_overlap`
  - `ex_task9_weather_rule_consumability_overlap`
  - `ex_task9_capacity_pool_consumability_overlap`
  - `ex_task9_run_parameter_consumability_overlap`
- superseded-is-terminal CHECK:
  - `superseded -> retired` removed from transition matrix
- generated-column rule:
  - each generated expression references base columns only
  - no generated column may reference another generated column
- `UNIQUE NULLS NOT DISTINCT`:
  - `task9_capacity_pool_member(capacity_pool_definition_id, farm_id, subfarm_id, variety_id)`
- partial unique one-active indexes:
  - `uq_task9_daily_capacity_one_active`
  - `uq_task9_initial_inventory_one_active`
  - `uq_task9_mature_loss_one_active`
  - `uq_task9_holiday_calendar_one_active`
  - `uq_task9_weather_rule_one_active`
- exclusion constraints:
  - `ex_task9_capacity_pool_definition_overlap`
  - `ex_task9_capacity_pool_member_overlap`
  - `ex_task9_run_parameter_package_overlap`
- draft-first supersession lifecycle:
  - required
  - immediate self-FKs retained
  - no deferred constraints
- run-package dependency lifecycle:
  - active package requires active holiday target
  - active package requires active weather-rule target
  - dependency replacement is transactional
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
- [x] Composite FK update path made executable with `ON UPDATE CASCADE`
- [x] Parent/child normalized effective-end expression unified
- [x] Stable cohort key uniqueness restored without redundant quantile suffix
- [x] Supersession self-FKs and same-scope integrity rules frozen
- [x] One-active partial unique indexes frozen
- [x] `status_changed_at` frozen as mandatory on all independent status authorities
- [x] Authority-family `source_record_key` prefixes frozen
- [x] Run-package-first holiday/weather FK load frozen
- [x] Lexical business-version ordering removed from selection
- [x] ParameterSourceRef matrix frozen
- [x] Holiday duplicate-date semantics frozen
- [x] Historical as-of consumability lifecycle fields frozen
- [x] Half-open interval `[from, to)` equality rules frozen
- [x] Activation / supersession / retirement / cancellation interval rules frozen
- [x] Lifecycle immutability frozen (from immutable after activation; to set once)
- [x] Current operational vs historical as-of selection separated
- [x] First-time historical resolution vs persisted exact replay distinguished
- [x] Superseded is terminal; `superseded -> retired` removed
- [x] `superseded_by_id` set-once / never-cleared / never-changed frozen
- [x] Direct retirement (`active -> retired` without replacement) frozen
- [x] Selection matrix revised with historical consumability predicates
- [x] Child-row wording corrected (immutable under draft parent; no invented draft for children without status)
- [x] Run-package dependency interval synchronization frozen
- [x] Historical consumability exclusion constraints added to DDL draft
- [x] Consumability range generated columns added to DDL draft
- [x] Lifecycle CHECK constraints added to DDL draft
- [x] Consumability blocker taxonomy added
- [x] `Migration 0014` boundary updated for consumability objects

---

## 17. Unresolved Questions

NONE
