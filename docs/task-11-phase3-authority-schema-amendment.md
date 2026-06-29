# Task 11 Phase 3 Authority Schema Amendment — P0-6 Design Document

**Status**: Design-phase only. P0-6 implementation NOT started — this document is design-phase only.

**Date**: 2026-06-29
**Branch**: `codex/task-11-rolling-backtest-orchestration`
**Related**: PR #22, Issue #21, `docs/task-11-phase3-design-amendment.md`

---

## 1. Purpose

This document identifies a **critical gap** in the Phase 3 rolling backtest orchestration: seventeen Task 9 input parameters lack an independent, historically-visible authority source in the database schema. Without these authorities, `_load_capacity_inputs_typed()` and `_load_task9_run_parameters_typed()` must remain blocked (they currently fail closed — see `orchestration.py:2256-2343`), making retrospective replay of Task 9 infeasible.

This document:
- Inventories existing models that might plausibly serve as authority
- Audits all 17 parameters against the `ParameterCode` enum
- Clarifies why `HarvestStateRun.input_snapshot` / `resolved_parameter_snapshot` are **downstream snapshots, not upstream authority**
- Proposes two minimal authority models (capacity + run-parameter) and their schema
- Recommends a migration path

---

## 2. Existing Models Inventory

### 2.1 ParameterLibraryVersion / ParameterObservation
**File**: `backend/app/models/planning.py:187-362`

| Field | Value |
|---|---|
| `parameter_type` enum | `yield_kg_per_mu`, `marketable_rate`, `first_harvest_offset_days`, `maturity_peak_offset_days`, `maturity_width_days`, `maturity_skewness`, `harvest_realization_rate` |
| `scalar_value` | `NUMERIC(18,6)` |
| `sample_weight` | `NUMERIC(18,6)` |
| `source_level` | `Text` (farm/variety/climate_zone etc.) |
| `historical_mape` | `NUMERIC(12,10)` |
| `valid_from` / `valid_to` | `Date` |
| `available_at` | `Date` |

**Assessment**: This table is designed for **agronomic/maturity parameters** (yield, marketable rate, harvest offsets). It does NOT cover **operational capacity parameters** (picker count, labor ratio, efficiency ratio, direct nominal capacity) or **run configuration parameters** (timezone, anchor time, arrival lag, weather rules). Expanding the `parameter_type` CHECK constraint to include capacity codes would be a schema change with uncertain semantic compatibility (the table assumes scalar `scalar_value`, but capacity parameters are often date-scoped, pool-scoped, or composite).

**Verdict**: ❌ Does not serve as capacity/run-parameter authority without substantial schema redesign.

### 2.2 FarmSeasonVarietyPlan
**File**: `backend/app/models/production_plan.py:27-182`

Key columns: `farm_id`, `subfarm_id`, `season_id`, `variety_id`, `planted_area_mu`, `expected_yield_kg_per_mu`, `marketable_rate`, `version`, `effective_from`, `effective_to`, `available_at`, `row_hash`.

**Assessment**: Already serves as the **plan authority** (Task 6, `TASK6_PLAN_VERSION` availability source type). It provides **pool membership identity** (which farms/varieties belong together) but does NOT carry capacity values. The current `_load_capacity_inputs_typed()` uses `FarmSeasonVarietyPlan` rows to construct `CapacityPoolInput` objects (pool membership only), then blocks because it cannot populate `DailyCapacityInput` fields.

**Verdict**: ✅ Serves pool membership (partially) but ❌ does NOT serve capacity values.

### 2.3 Weather Models
**Files**: `backend/app/models/weather.py`

- `WeatherSourceLocation` — weather station/grid metadata with `timezone_name`
- `WeatherDailyObservation` — daily observations with `available_at` (visibility-gated)
- `LocationWeatherMapping` — farm-to-weather-source binding with `available_at`
- `WeatherFeatureRun` — computed weather features with `source_signature`
- `BaseTemperatureSearchRun` — base temperature search results

**Assessment**: Already serves as the **weather observation authority** (Task 7, `TASK7_WEATHER_OBSERVATION`). `WeatherSourceLocation.timezone_name` could serve as the **farm timezone authority** (if mapped through `LocationWeatherMapping` → `LocationReference` → `Farm`). `WeatherDailyObservation` rows are used by `_load_weather_inputs_typed()` to produce `DailyWeatherFeatureInput` with `ParameterSourceRef(parameter_code="WEATHER_FEATURE_OBSERVATION")`.

**Verdict**: ✅ Serves weather features with provenance. Partially could serve farm timezone but not factory timezone or capacity parameters.

### 2.4 LocationReference
**File**: `backend/app/models/planning.py:110-184`

Key columns: `farm_id`, `subfarm_id`, `latitude`, `longitude`, `altitude_m`, `climate_zone_id`, `valid_from`, `valid_to`, `source_row_hash`.

**Assessment**: Already serves as the **location authority** for farm/subfarm geolocation. Does NOT carry timezone, capacity, or run parameters.

**Verdict**: ✅ Serves geolocation authority but ❌ not capacity/run parameters.

### 2.5 Holiday (dim_holiday)
**File**: `backend/app/models/master_data.py:125-159`

Key columns: `season_id`, `code`, `name`, `start_date`, `end_date`, `region_name`, `active`.

**Assessment**: Provides holiday dates per season. However, Task 9's `Task9ARequest` expects `holiday_calendar_version`, `holiday_calendar_hash`, and `holiday_dates` — a **versioned calendar package** with a deterministic hash. The `dim_holiday` table has no version, no hash, and no `available_at` visibility column. It is a mutable reference table, not a versioned authority.

**Verdict**: ⚠️ Provides raw holiday data but lacks versioning/hashing/visibility for authority use.

### 2.6 HarvestStateRun (DOWNSTREAM — NOT authority)
**File**: `backend/app/models/harvest_state.py:108-207`

Key columns: `input_snapshot` (JSONB), `resolved_parameter_snapshot` (JSONB, nullable).

**Critical distinction**: These are **downstream snapshots** captured at Task 9 execution time. They represent "what was used" — not "what was the authoritative source at that time." Using them as authority would create a circular dependency:
1. Task 11 resolves Task 9 authority → queries `HarvestStateRun.resolved_parameter_snapshot`
2. But `resolved_parameter_snapshot` was itself derived from parameters provided to Task 9
3. Those parameters had to come from *somewhere* — and that somewhere is the missing authority

**Verdict**: ❌ Downstream snapshot, explicitly excluded from authority chain. Using it would be circular and break the "visible at as-of-date" constraint.

### 2.7 RollingBacktestResolvedInput
**File**: `backend/app/models/rolling_backtest.py`

**Assessment**: This table stores **resolution results** for upstream sources (Task 8 model run, Task 7 weather, Task 6 plan). It captures which upstream source was selected for a given node — it does NOT hold the parameter values themselves.

**Verdict**: ✅ Records resolution decisions but ❌ does not store parameter values.

---

## 3. Parameter Authority Audit

The `ParameterCode` enum (`harvest_state/enums.py:38-51`) defines 12 parameter codes. Below, each parameter is audited against existing database sources.

### 3.1 Capacity Parameters

| # | Parameter Code / Field | Used In | Authority Exists? | Notes |
|---|---|---|---|---|
| P0 | `PLANNED_PICKER_COUNT` | `DailyCapacityInput.planned_picker_count` | ❌ NONE | Required when `capacity_input_mode=LABOR_DERIVED`. No table holds historical picker counts per farm/date/pool. |
| P0 | `PICKER_PRODUCTIVITY` | `DailyCapacityInput.kg_per_person_per_day` | ❌ NONE | required when `capacity_input_mode=LABOR_DERIVED`. No table holds historical productivity values. |
| P0 | `DIRECT_NOMINAL_CAPACITY` | `DailyCapacityInput.direct_nominal_capacity_kg_per_day` | ❌ NONE | Required when `capacity_input_mode=DIRECT_CAPACITY`. No table holds historical direct capacity values. |
| P1 | `LABOR_AVAILABILITY_RATIO` | `DailyCapacityInput.labor_availability_ratio` | ❌ NONE | Always required. Ratio ∈ [0,1]. No independent source — currently hardcoded or derived. |
| P1 | `OPERATIONAL_EFFICIENCY_RATIO` | `DailyCapacityInput.operational_efficiency_ratio` | ❌ NONE | Always required. Ratio ∈ [0,1]. No independent source. |
| P2 | Capacity pool membership | `CapacityPoolInput.members` | ⚠️ PARTIAL | Pool composition can be inferred from `FarmSeasonVarietyPlan` (which farms/sublocks/varieties exist), but formal membership and pool grain rules have no dedicated authority. |
| P6 | `MATURE_INVENTORY_LOSS` | `MatureInventoryLossInput` | ❌ NONE | Daily loss quantity per pool. No table holds historical loss estimates. |

### 3.2 Run Configuration Parameters

| # | Parameter Code / Field | Used In | Authority Exists? | Notes |
|---|---|---|---|---|
| P3 | `HARVEST_BUCKET_ANCHOR_TIME` | `Task9ARequest.harvest_bucket_anchor_local_time` | ❌ NONE | No table. Currently a hardcoded input to Task 9. |
| P3 | `HARVEST_TO_ARRIVAL_LAG` | `Task9ARequest.harvest_to_arrival_lag_days` | ❌ NONE | No table. Currently a hardcoded input. |
| P3 | `TIMEZONE_CONFIG` | `Task9ARequest.farm_timezone`, `destination_factory_timezone` | ⚠️ PARTIAL | `WeatherSourceLocation.timezone_name` provides weather station timezone. `LocationReference` has no timezone column. Factory timezone has no authority. Farm timezone could be derived from location → mapping → weather source but not formalized. |
| P4 | `HOLIDAY_CALENDAR` | `Task9ARequest.holiday_calendar_version`, `holiday_calendar_hash`, `holiday_dates` | ⚠️ PARTIAL | `dim_holiday` has dates but no version/hash/visibility. Needs a versioned calendar snapshot table. |
| P5 | `WEATHER_RULE_CONFIG` | `Task9ARequest.weather_rule_config` | ❌ NONE | `WeatherEfficiencyRuleConfig` is a Pydantic model with version, feature rules, combination method. No database table stores historical weather rule configs. |
| P6 | `MATURE_INVENTORY_LOSS` | (see above) | ❌ NONE | |
| — | `WEATHER_FEATURE_OBSERVATION` | `DailyWeatherFeatureInput` | ✅ EXISTS | Already wired via `_load_weather_inputs_typed()` → `WeatherDailyObservation` rows with `ParameterSourceRef`. |
| — | Initial mature inventory | `Task9ARequest.initial_opening_mature_inventory_kg` | ❌ NONE | No table holds historical opening inventory estimates. |
| — | Initial inventory cohorts | `Task9ARequest.initial_inventory_cohorts` | ❌ NONE | No table holds historical cohort snapshots. |

### 3.3 Summary of Unsupported Parameter Codes

The following `ParameterCode` values have **no independent authority table** and cannot be resolved for retrospective replay:

| Priority | Count | Codes |
|---|---|---|
| **P0** (blocks all capacity) | 3 | `PLANNED_PICKER_COUNT`, `PICKER_PRODUCTIVITY`, `DIRECT_NOMINAL_CAPACITY` |
| **P1** (blocks capacity derivation) | 2 | `LABOR_AVAILABILITY_RATIO`, `OPERATIONAL_EFFICIENCY_RATIO` |
| **P2** (blocks pool construction) | 1 | Capacity pool membership |
| **P3** (blocks time/lag) | 3 | `HARVEST_BUCKET_ANCHOR_TIME`, `HARVEST_TO_ARRIVAL_LAG`, `TIMEZONE_CONFIG` |
| **P4** (blocks holiday) | 1 | `HOLIDAY_CALENDAR` |
| **P5** (blocks weather rules) | 1 | `WEATHER_RULE_CONFIG` |
| **P6** (blocks inventory) | 2 | `MATURE_INVENTORY_LOSS`, initial mature inventory |

**Total**: 13 unsupported parameter codes across 6 priority tiers (plus 4 additional fields: initial inventory, initial cohorts, pool membership — these are not `ParameterCode` enum members but are required `Task9ARequest` fields).

---

## 4. Downstream Snapshot Exclusion: Why `HarvestStateRun` Cannot Be Authority

The `HarvestStateRun` table stores two JSONB columns that superficially resemble authority:

| Column | Content | Why NOT Authority |
|---|---|---|
| `input_snapshot` | Full serialized `Task9ARequest` at execution time | This is a **record of consumption**, not a **source of truth**. It was built from upstream authorities that may or may not have been properly versioned. Using it as authority would mean "Task 11 replay trusts whatever Task 9 wrote" — which defeats the purpose of authority chain validation. |
| `resolved_parameter_snapshot` | `ResolvedParameterSnapshot` with resolved nominal/effective capacity per pool/day | This is a **derived computation product**. It represents the output of parameter resolution, not the input authority. The resolution process itself used sources that should be independently verifiable. |

**Design rule**: The authority chain must be **acyclic**. Task 9's output cannot serve as its own input authority. The source of every parameter must be traceable to a table that:
1. Has `available_at` or `authoritative_timestamp` visibility gating
2. Has a stable `row_hash` or `source_row_hash`
3. Is versioned (supports "what was known as of date X" queries)
4. Is populated independently of Task 9 execution

---

## 5. Proposed Authority Models

### 5.1 Capacity Authority

Two tables are needed: a **capacity pool definition table** and a **daily capacity value table**.

#### 5.1.1 `capacity_pool_definition`

**Purpose**: Define which farms/sublocks/varieties belong to which capacity pool, what grain the pool operates at, and the capacity input mode.

**Grain**: `season_id × applicable_date × destination_factory_id × capacity_pool_id`

```sql
CREATE TABLE capacity_pool_definition (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,

    -- Business key
    season_id BIGINT NOT NULL REFERENCES dim_season(id) ON DELETE RESTRICT,
    capacity_pool_id TEXT NOT NULL,
    capacity_pool_grain TEXT NOT NULL
        CHECK (capacity_pool_grain IN ('SUBFARM_VARIETY', 'SUBFARM', 'FARM')),
    destination_factory_id BIGINT NOT NULL,

    -- Capacity mode (mutually exclusive branches)
    capacity_input_mode TEXT NOT NULL
        CHECK (capacity_input_mode IN ('LABOR_DERIVED', 'DIRECT_CAPACITY')),

    -- Visibility / versioning
    applicable_from DATE NOT NULL,
    applicable_to DATE,
    authoritative_available_at DATE NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    status TEXT NOT NULL CHECK (status IN ('active', 'retired')),
    source_system TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    source_version TEXT NOT NULL,
    source_row_hash TEXT NOT NULL CHECK (length(source_row_hash) = 64),

    -- Audit
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Constraints
    UNIQUE (season_id, destination_factory_id, capacity_pool_id, version),
    CHECK (applicable_to IS NULL OR applicable_to > applicable_from)
);

CREATE INDEX ix_capacity_pool_def_season_factory
    ON capacity_pool_definition(season_id, destination_factory_id);
CREATE INDEX ix_capacity_pool_def_available_at
    ON capacity_pool_definition(authoritative_available_at);
```

#### 5.1.2 `capacity_pool_member`

**Purpose**: Define which farm/subfarm/variety combinations belong to a pool definition.

**Grain**: `capacity_pool_definition_id × farm_id × subfarm_id × variety_id`

```sql
CREATE TABLE capacity_pool_member (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    capacity_pool_definition_id BIGINT NOT NULL
        REFERENCES capacity_pool_definition(id) ON DELETE RESTRICT,
    farm_id BIGINT NOT NULL REFERENCES dim_farm(id) ON DELETE RESTRICT,
    subfarm_id BIGINT REFERENCES dim_subfarm(id) ON DELETE RESTRICT,
    variety_id BIGINT NOT NULL REFERENCES dim_variety(id) ON DELETE RESTRICT,
    source_row_hash TEXT NOT NULL CHECK (length(source_row_hash) = 64),
    UNIQUE (capacity_pool_definition_id, farm_id, subfarm_id, variety_id)
);

CREATE INDEX ix_capacity_pool_member_def_id
    ON capacity_pool_member(capacity_pool_definition_id);
```

**Semantic identity rules**:
- A member's `(farm_id, subfarm_id, variety_id)` must be consistent with the pool's `capacity_pool_grain`:
  - `FARM`: `subfarm_id IS NULL`, `variety_id` is the only varying dimension
  - `SUBFARM`: `variety_id` is ignored (or NULL), `subfarm_id` varies
  - `SUBFARM_VARIETY`: both `subfarm_id` and `variety_id` vary
- A pool must have at least 2 members (singleton pools are invalid per `BlockerCode.INVALID_SINGLETON_POOL`)
- Members must belong to the same `farm_id` (cross-farm pools blocked per `BlockerCode.CROSS_FARM_CAPACITY_POOL`)
- A member must not appear in multiple pools for the same season/factory (`BlockerCode.MEMBER_ASSIGNED_TO_MULTIPLE_POOLS`)

#### 5.1.3 `daily_capacity_value`

**Purpose**: Store daily capacity values per pool. This is the historical authority for picker count, productivity, direct capacity, labor ratio, and operational efficiency ratio.

**Grain**: `capacity_pool_definition_id × applicable_date`

```sql
CREATE TABLE daily_capacity_value (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    capacity_pool_definition_id BIGINT NOT NULL
        REFERENCES capacity_pool_definition(id) ON DELETE RESTRICT,
    applicable_date DATE NOT NULL,

    -- Capacity input mode values (mutually exclusive per pool definition mode)
    -- LABOR_DERIVED branch:
    planned_picker_count NUMERIC(18,3),
    kg_per_person_per_day NUMERIC(18,3),
    -- DIRECT_CAPACITY branch:
    direct_nominal_capacity_kg_per_day NUMERIC(18,3),

    -- Always-required ratios
    labor_availability_ratio NUMERIC(12,6) NOT NULL
        CHECK (labor_availability_ratio >= 0 AND labor_availability_ratio <= 1),
    operational_efficiency_ratio NUMERIC(12,6) NOT NULL
        CHECK (operational_efficiency_ratio >= 0 AND operational_efficiency_ratio <= 1),

    -- Visibility / provenance
    authoritative_available_at DATE NOT NULL,
    source_system TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    source_version TEXT NOT NULL,
    source_row_hash TEXT NOT NULL CHECK (length(source_row_hash) = 64),

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (capacity_pool_definition_id, applicable_date),

    -- Mode-consistency check: LABOR_DERIVED pools must have picker count + productivity,
    -- DIRECT_CAPACITY pools must have direct capacity
    CHECK (
        (planned_picker_count IS NOT NULL AND kg_per_person_per_day IS NOT NULL
         AND direct_nominal_capacity_kg_per_day IS NULL)
        OR
        (direct_nominal_capacity_kg_per_day IS NOT NULL
         AND planned_picker_count IS NULL AND kg_per_person_per_day IS NULL)
    )
);

CREATE INDEX ix_daily_capacity_value_pool_date
    ON daily_capacity_value(capacity_pool_definition_id, applicable_date);
CREATE INDEX ix_daily_capacity_value_available_at
    ON daily_capacity_value(authoritative_available_at);
```

**Visibility query for replay**:
```sql
SELECT dcv.*
FROM daily_capacity_value dcv
JOIN capacity_pool_definition cpd ON dcv.capacity_pool_definition_id = cpd.id
WHERE cpd.season_id = :season_id
  AND cpd.destination_factory_id = :factory_id
  AND dcv.authoritative_available_at <= :as_of_date
  AND dcv.applicable_date BETWEEN :forecast_start AND :forecast_end
ORDER BY cpd.capacity_pool_id, dcv.applicable_date;
```

### 5.2 Run Parameter Authority

A single typed parameter registry table for run-level configuration parameters.

#### 5.2.1 `run_parameter_authority`

**Purpose**: Store historically-visible values for run-level parameters: timezone, harvest bucket anchor time, arrival lag, holiday calendar, weather rule config, mature inventory loss, initial mature inventory.

**Grain**: `season_id × destination_factory_id × parameter_code × effective_date`

```sql
CREATE TABLE run_parameter_authority (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    season_id BIGINT NOT NULL REFERENCES dim_season(id) ON DELETE RESTRICT,
    destination_factory_id BIGINT NOT NULL,

    -- Typed parameter registry
    parameter_code TEXT NOT NULL CHECK (parameter_code IN (
        'HARVEST_BUCKET_ANCHOR_TIME',
        'HARVEST_TO_ARRIVAL_LAG',
        'TIMEZONE_CONFIG',
        'HOLIDAY_CALENDAR',
        'WEATHER_RULE_CONFIG',
        'MATURE_INVENTORY_LOSS',
        'INITIAL_MATURE_INVENTORY',
        'INITIAL_INVENTORY_COHORTS'
    )),

    -- Parameter value (type varies by parameter_code)
    -- Complex types stored as JSONB with parameter_code-specific schema validation
    parameter_value JSONB NOT NULL,

    -- Visibility / versioning
    effective_from DATE NOT NULL,
    effective_to DATE,
    authoritative_available_at DATE NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    status TEXT NOT NULL CHECK (status IN ('active', 'retired')),

    -- Provenance
    source_system TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    source_version TEXT NOT NULL,
    source_row_hash TEXT NOT NULL CHECK (length(source_row_hash) = 64),

    -- Content hash for integrity
    parameter_value_hash TEXT NOT NULL CHECK (length(parameter_value_hash) = 64),

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (season_id, destination_factory_id, parameter_code, version),
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE INDEX ix_run_param_auth_season_factory_code
    ON run_parameter_authority(season_id, destination_factory_id, parameter_code);
CREATE INDEX ix_run_param_auth_available_at
    ON run_parameter_authority(authoritative_available_at);
CREATE INDEX ix_run_param_auth_effective
    ON run_parameter_authority(season_id, destination_factory_id, parameter_code, effective_from);
```

**Parameter value JSONB schemas** (per `parameter_code`):

| `parameter_code` | `parameter_value` JSONB structure | Notes |
|---|---|---|
| `HARVEST_BUCKET_ANCHOR_TIME` | `{"local_time": "06:00:00"}` | `time` as HH:MM:SS string |
| `HARVEST_TO_ARRIVAL_LAG` | `{"lag_days": 1}` | Integer days |
| `TIMEZONE_CONFIG` | `{"farm_timezone": "Asia/Shanghai", "factory_timezone": "Asia/Shanghai"}` | IANA timezone names |
| `HOLIDAY_CALENDAR` | `{"version": "cn-2026-v1", "hash": "<sha256>", "dates": ["2026-01-28", ...]}` | Versioned calendar with hash |
| `WEATHER_RULE_CONFIG` | `{"version": "wx-rule-v1", "required_feature_ids": [...], "feature_rules": [...], "combination_method": "MULTIPLY", "minimum_ratio": 0.0, "maximum_ratio": 1.0, "missing_feature_policy": "BLOCK"}` | Full `WeatherEfficiencyRuleConfig` serialized |
| `MATURE_INVENTORY_LOSS` | `[{"state_date": "2026-03-16", "capacity_pool_id": "pool_1", "forecast_quantile": "P50", "quantity_kg": "100.0"}, ...]` | Array of loss records |
| `INITIAL_MATURE_INVENTORY` | `{"quantity_kg": "5000.0"}` | Scalar opening inventory |
| `INITIAL_INVENTORY_COHORTS` | `[{"cohort_date": "2026-03-15", "farm_id": 1, "subfarm_id": null, "variety_id": 2, "remaining_quantity_kg": "500.0", ...}, ...]` | Array of cohort records |

**Visibility query for replay**:
```sql
SELECT DISTINCT ON (parameter_code) rpa.*
FROM run_parameter_authority rpa
WHERE rpa.season_id = :season_id
  AND rpa.destination_factory_id = :factory_id
  AND rpa.status = 'active'
  AND rpa.authoritative_available_at <= :as_of_date
  AND rpa.effective_from <= :as_of_date
  AND (rpa.effective_to IS NULL OR rpa.effective_to >= :as_of_date)
ORDER BY rpa.parameter_code, rpa.version DESC;
```

### 5.3 Visibility Columns (Common Across Both Models)

All proposed authority tables share these visibility columns:

| Column | Type | Purpose |
|---|---|---|
| `authoritative_available_at` | `DATE NOT NULL` | The calendar date when this parameter row became visible/known. Query filter: `<= as_of_date` prevents future information leakage. |
| `effective_from` / `effective_to` | `DATE NOT NULL` / `DATE` | The business time window when this parameter value is applicable. `effective_to IS NULL` means "currently effective." |
| `version` | `INTEGER NOT NULL` | Monotonically increasing version within the same business key. Enables "latest known version as of date X" queries. |
| `status` | `TEXT NOT NULL` (`active`, `retired`) | Lifecycle status. Only `active` rows participate in resolution. |
| `source_row_hash` | `TEXT NOT NULL` (64-char hex) | SHA-256 of the canonical source payload. Enables deduplication and tamper detection. |
| `parameter_value_hash` | `TEXT NOT NULL` (64-char hex) | SHA-256 of `canonical_json_value(parameter_value)`. Enables content-addressed retrieval. |

**Semantic identity rules**:
- For capacity tables: `(season_id, destination_factory_id, capacity_pool_id, version)` is the unique identity
- For run parameters: `(season_id, destination_factory_id, parameter_code, version)` is the unique identity
- The `ParameterSourceRef` in `Task9ARequest.run_parameter_source_refs` and `DailyCapacityInput.capacity_parameter_source_refs` references these rows by `source_system + source_record_key + source_version + source_row_hash`
- `authoritative_available_at` MUST be `<= node.as_of_local_date` during replay resolution
- `effective_from` MUST be `<= node.as_of_local_date` and `effective_to` MUST be `NULL` or `>= node.as_of_local_date`

---

## 6. Migration Recommendation

### 6.1 Option A: Amend Unmerged 0013 Migration

**Approach**: Add the new tables to the existing (unmerged) `0013_rolling_backtest_orchestration.py` migration.

**Pros**:
- Single migration for all Phase 3 schema changes
- Avoids migration chain complexity
- The 0013 migration is still draft (on branch `codex/task-11-rolling-backtest-orchestration`, PR #22)
- No production database has applied 0013 yet

**Cons**:
- Violates single-responsibility principle (0013 already adds 3 changes: attempt node ownership, stage events, orchestration snapshot)
- Makes rollback testing more complex
- If 0013 is partially reviewed, adding tables mid-review creates churn

### 6.2 Option B: New Subsequent Migration (0014)

**Approach**: Create `0014_phase3_authority_schema.py` that revises `0013_rolling_backtest_orch`.

**Pros**:
- Clean separation of concerns: 0013 = orchestration infrastructure, 0014 = authority data
- Easier to review independently
- Can be merged after 0013 without blocking the orchestration work
- Allows 0013 to be finalized while authority design is still evolving

**Cons**:
- Adds another migration link in the chain
- Slightly more files to manage

### 6.3 Recommendation: **Option B — New Subsequent Migration (0014)**

**Rationale**:

1. **0013 is already large** (282 lines, 3 schema changes). Adding capacity + run-parameter authority tables would add ~150-200 more lines and a fundamentally different concern (data authority vs. execution tracking).

2. **Independent merge cadence**: 0013's orchestration infrastructure (attempt ownership, stage events, outcome snapshots) is logically complete and could be merged independently. The authority tables are a separate feature that has its own design review cycle.

3. **Current state evidence**:
   - `orchestration.py:2256-2343` explicitly documents that `_load_capacity_inputs_typed()` and `_load_task9_run_parameters_typed()` fail closed — they are designed to be unblocked when authority tables exist
   - The `_load_capacity_inputs_typed()` function already has the structure to query authority tables (it reads `FarmSeasonVarietyPlan` for pool membership and would extend to read `daily_capacity_value`)
   - The `ParameterCode` enum already defines all 12 codes — the schema just needs tables to store them
   - `ParameterSourceRef` in `harvest_state/schemas.py:102-111` already has the fields (`source_system`, `source_record_key`, `source_version`, `source_row_hash`, `available_at`, `as_of_date`) that map to the proposed authority tables

4. **Migration numbering**: `0014_phase3_authority_schema.py` revises `0013_rolling_backtest_orch`.

**Migration file structure**:
```
backend/alembic/versions/
├── 0013_rolling_backtest_orchestration.py   (existing, unchanged)
└── 0014_phase3_authority_schema.py          (new — creates capacity + run-parameter tables)
```

---

## 7. Out of Scope (Explicitly)

The following are **NOT** addressed in this design document and are deferred to future tasks:

| Item | Reason |
|---|---|
| Actual SQL migration code | This is a design document, not implementation |
| Data import/CSV templates for authority tables | Separate Task 5/6/9 concern |
| `ParameterLibraryVersion` expansion to include capacity codes | Architectural decision — the existing table is for agronomic parameters; mixing operational capacity parameters would violate single-responsibility |
| Holiday calendar versioning table | Implicitly covered by `run_parameter_authority` with `parameter_code='HOLIDAY_CALENDAR'` storing calendar as JSONB |
| Weather rule config storage | Covered by `run_parameter_authority` with `parameter_code='WEATHER_RULE_CONFIG'` |
| Initial inventory / cohort snapshot storage | Covered by `run_parameter_authority` with `parameter_code='INITIAL_MATURE_INVENTORY'` and `'INITIAL_INVENTORY_COHORTS'` |
| Factory timezone authority (separate from weather station timezone) | Needs `dim_factory.timezone_name` column or `run_parameter_authority` entry |
| Pool member validation rules implementation | Business logic, not schema design |

---

## 8. Relationship to Existing Design Documents

- **`docs/task-11-phase3-design-amendment.md`** (Decisions 1-4): Covers attempt ownership, stage history, Task 9 authority PATH (through envelope output), and minimal 0013 migration. This document extends that by defining the **upstream authority schema** that feeds into the Task 9 authority path.
- **`docs/07_minimal_input_parameter_inference.md`**: Covers automatic parameter inference from `ParameterLibraryVersion`. This document addresses the gap that those parameters are agronomic, not operational.
- **`CODEX_TASKS.md` Task 9**: "春节、用工与积压状态模型" — the capacity/run parameters defined here are the inputs Task 9 needs but currently lacks authority for.

---

## 9. Status Declaration

**P0-6 implementation NOT started — this document is design-phase only.**

No code has been written, no migrations have been created, and no tests have been modified for the authority schema proposed in this document. The `_load_capacity_inputs_typed()` and `_load_task9_run_parameters_typed()` functions in `orchestration.py` continue to fail closed with diagnostic messages referencing the missing authority sources.

---

## Appendix A: Quick Reference — All 17 Unsupported Inputs

| # | Field / Concept | Priority | Proposed Authority Table |
|---|---|---|---|
| 1 | `planned_picker_count` | P0 | `daily_capacity_value.planned_picker_count` |
| 2 | `kg_per_person_per_day` (picker productivity) | P0 | `daily_capacity_value.kg_per_person_per_day` |
| 3 | `direct_nominal_capacity_kg_per_day` | P0 | `daily_capacity_value.direct_nominal_capacity_kg_per_day` |
| 4 | `labor_availability_ratio` | P1 | `daily_capacity_value.labor_availability_ratio` |
| 5 | `operational_efficiency_ratio` | P1 | `daily_capacity_value.operational_efficiency_ratio` |
| 6 | Capacity pool definition (grain, mode, members) | P2 | `capacity_pool_definition` + `capacity_pool_member` |
| 7 | `harvest_bucket_anchor_local_time` | P3 | `run_parameter_authority` (`HARVEST_BUCKET_ANCHOR_TIME`) |
| 8 | `harvest_to_arrival_lag_days` | P3 | `run_parameter_authority` (`HARVEST_TO_ARRIVAL_LAG`) |
| 9 | `farm_timezone` | P3 | `run_parameter_authority` (`TIMEZONE_CONFIG`) or `dim_factory` |
| 10 | `destination_factory_timezone` | P3 | `run_parameter_authority` (`TIMEZONE_CONFIG`) or `dim_factory` |
| 11 | `holiday_calendar_version` + `holiday_calendar_hash` + `holiday_dates` | P4 | `run_parameter_authority` (`HOLIDAY_CALENDAR`) |
| 12 | `weather_rule_config` | P5 | `run_parameter_authority` (`WEATHER_RULE_CONFIG`) |
| 13 | `mature_inventory_loss_inputs` | P6 | `run_parameter_authority` (`MATURE_INVENTORY_LOSS`) |
| 14 | `initial_opening_mature_inventory_kg` | P6 | `run_parameter_authority` (`INITIAL_MATURE_INVENTORY`) |
| 15 | `initial_inventory_cohorts` | P6 | `run_parameter_authority` (`INITIAL_INVENTORY_COHORTS`) |
| 16 | `capacity_pool_membership_hash` | P2 | Derived from `capacity_pool_member` rows |
| 17 | `capacity_input_mode` per pool | P2 | `capacity_pool_definition.capacity_input_mode` |

