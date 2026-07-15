# Slice Q2A — Actual-Harvest Source Contract (FIXUP)

> **Issue:** #102
> **Slice:** Q2A — Actual-harvest source, label snapshot, prediction alignment
> **Type:** Docs-only design freeze (P0 fixup round)
> **Authorization:** Issue #102 comment ID `4975150023`
> **Re-review:** Issue #102 comment ID `4975425033`
> **Status:** PENDING_REVIEW
> **Implementation authorized:** NO
> **Q2B authorized:** NO
> **Q3 authorized:** NO

---

## 1. Business event definition (FROZEN)

**actual harvest** = physical blueberry quantity actually picked from plants during one defined farm-local harvest business day.

This is a primary business observation: a picker physically removes ripe fruit from a plant at a defined farm/subfarm/plot during a defined harvest business date.

### 1.1 Explicit exclusions (FROZEN)

The following are **NOT** actual harvest and must not be classified as such:

| Excluded concept | Reason |
|---|---|
| predicted harvest | forward-looking forecast, not observed |
| harvest capacity | theoretical/operational capacity, not observed quantity |
| harvestable maturity | mature-but-unpicked inventory state, not picked |
| closing inventory | end-of-period stock, not pick event |
| backlog | pending work, not pick event |
| arrival | arrival at factory gate, post-pick event |
| receipt | factory receipt/weigh-in, post-pick event |
| corrected receipt | revised receipt, post-pick event |
| processing input | factory intake, post-pick event |
| production plan | forward-looking plan, not observed |

### 1.2 Distinguishing direct observation vs proxy

A "harvest" word in a field name or column comment is **not** sufficient. Classification requires the full semantic check (§1.3).

### 1.3 Required evidence for `DIRECT_ACTUAL_HARVEST_OBSERVATION`

To qualify as direct actual harvest, a source must simultaneously satisfy all of:

1. business event = physical pick from plants;
2. quantity = actual weight (kg), not predicted/estimated;
3. business date = farm-local harvest business date;
4. identity = farm + variety + (subfarm or plot);
5. recorded at or auditable batch available;
6. revision semantics expressible (ACTIVE/VOID/CORRECTED/FINALIZED);
7. business owner or formal documentation proves meaning;
8. production wired (not fixture-only, not test-only).

## 2. Candidate source inventory (REPOSITORY-ONLY — see §3 scope)

This section lists candidate sources found **within the audited scope** (current repository and checked-in local artifacts). It does NOT claim that no source exists in external farm systems, ERP systems, picking logs, weighing systems, spreadsheets, or unconnected production databases.

### 2.1 HarvestStateDailyMemberRowModel (MODEL_OUTPUT — not actual harvest)

**Repository path (verified at origin/main `9427bc6`):** `backend/app/models/harvest_state.py`

**Class:** `HarvestStateDailyMemberRowModel` (table `harvest_state_daily_member_row`)

| field | SQL type | role |
|---|---|---|
| id | BIGINT | primary key |
| harvest_state_run_id | BIGINT | FK to `harvest_state_run.id` |
| state_date | Date | forecast business date |
| forecast_quantile | Text | enum `('P50', 'P80', 'P90')` (CHECK constraint) |
| capacity_pool_id | Text | capacity-pool identifier (NOT UUID, NOT FK) |
| capacity_pool_grain | Text | enum `('SUBFARM_VARIETY', 'SUBFARM', 'FARM')` |
| capacity_pool_membership_hash | Text | SHA-256 of pool membership |
| farm_id | BIGINT | farm identifier (BIGINT, not UUID) |
| subfarm_id | BIGINT, nullable | subfarm identifier (BIGINT, not UUID) |
| subfarm_identity_key | Text | canonical subfarm identity |
| variety_id | BIGINT | variety identifier (BIGINT, not UUID) |
| destination_factory_id | BIGINT | factory identifier (BIGINT, not UUID) |
| opening_mature_inventory_kg | Numeric(18,3) | derived state |
| natural_maturity_supply_kg | Numeric(18,3) | derived state |
| available_mature_quantity_kg | Numeric(18,3) | derived state |
| mature_inventory_loss_quantity_kg | Numeric(18,3) | derived state |
| harvestable_mature_quantity_kg | Numeric(18,3) | **DERIVED_STATE** (mature inventory, not picked) |
| allocated_harvest_capacity_kg | Numeric(18,3) | derived state |
| harvested_quantity_kg | Numeric(18,3) | **MODEL_OUTPUT** (forecast's harvested output) |
| closing_mature_inventory_kg | Numeric(18,3) | derived state |
| unharvested_backlog_kg | Numeric(18,3) | derived state |
| arrival_quantity_kg | Numeric(18,3) | derived state (predicted arrival) |
| opening_cohort_count / closing_cohort_count | BIGINT | cohort counts |
| cohort_source_ref_hashes | JSONB list | source reference hashes |

**Quantile contract:** `forecast_quantile ∈ {P50, P80, P90}`. **No P10.** This is enforced by check constraint `ck_harvest_state_daily_member_quantile`.

**Identifier types:** all IDs in this model are BIGINT (integer). `capacity_pool_id` is **Text** (not UUID, not foreign key). No claim of UUID semantics is made.

**Business-key uniqueness (from production schema):** unique on `(harvest_state_run_id, state_date, capacity_pool_id, farm_id, subfarm_identity_key, ...)`.

**Direct grain:**
```
HARVEST_STATE_RUN X STATE_DATE X CAPACITY_POOL X FARM X SUBFARM_IDENTITY_KEY X VARIETY X FORECAST_QUANTILE
```

This is a production-verified grain.

**Classification:** `MODEL_OUTPUT`. The `harvested_quantity_kg` field is the model's harvested-output quantity; it is **not** the observed actual pick weight. Despite the field name containing "harvested", this is a forecast output, not a primary actual-harvest label.

### 2.2 ForecastDailyRow (MODEL_OUTPUT — Agent aggregate)

**Repository path (verified at origin/main `9427bc6`):** `backend/app/agent/schemas.py`

**Class:** `ForecastDailyRow` (Pydantic, serialized Agent aggregate row)

| field | type | role |
|---|---|---|
| `date` | date | forecast business date |
| `natural_maturity_quantity_kg` | DailyQuantiles | P50/P80/P90 |
| `harvested_quantity_kg` | **DailyQuantiles** (P50/P80/P90) | Agent aggregate forecast output |
| `closing_mature_inventory_kg` | DailyQuantiles | derived state |
| `unharvested_backlog_kg` | DailyQuantiles | derived state |
| `arrival_quantity_kg` | DailyQuantiles | derived state |
| `final_corrected_arrival_quantity_kg` | DailyQuantiles | derived state |
| `per_variety_contribution` | `list[VarietyContribution]` | nested variety contributions |
| `weather_tags` | tuple[str, ...] | weather context |
| `spring_festival_phase` | `SpringFestivalPhase` | spring-festival phase |
| `agent_daily_row_hash` | SHA256Hex | row hash |

**DailyQuantiles fields (verified):** `p50: DecimalString, p80: DecimalString, p90: DecimalString`. **No p10.**

**Identity fields:** `ForecastDailyRow` does **not** carry first-class `farm_id`, `subfarm_id`, or `variety_id` fields. Identity is carried by the enclosing request/location/season context and the nested `per_variety_contribution` (variety identity appears there, not as a first-class row identity).

**Direct row grain (corrected, P0-5):**
```
RESOLVED_REQUEST_AGGREGATE_X_DATE
```

This is **not** `farm × subfarm × variety × forecast_date`. The previous framing of `forecast_date` is corrected to `date`.

**Classification:** `MODEL_OUTPUT`. The `harvested_quantity_kg` field is the Agent aggregate's harvested output. It is not the observed actual pick weight.

### 2.3 FactReceiptDaily (ARRIVAL_OR_RECEIPT_PROXY — not actual harvest)

**Repository path (verified at origin/main `9427bc6`):** `backend/app/models/analytics.py`

**Class:** `FactReceiptDaily`

| field | SQL type | role |
|---|---|---|
| id | BIGINT | primary key |
| build_run_id | BIGINT | FK to analytics build run |
| season_id | BIGINT | FK to `dim_season.id` |
| receipt_date | Date | factory receipt date |
| factory_id | BIGINT | FK to `dim_factory.id` |
| farm_key | Text | farm identity key (Text, not UUID) |
| subfarm_key | Text | subfarm identity key (Text, not UUID) |
| variety_id | BIGINT | FK to `dim_variety.id` |
| weight_kg | Numeric(18,6) | factory gate receipt weight (kg) |
| source_row_count | Integer | source row count for this record |
| holiday_codes | list[str] | holiday tags |
| is_spring_festival | bool | spring-festival flag |
| created_at | DateTime | record creation timestamp |

**Identity grain (verified):**
```
SEASON_X_RECEIPT_DATE_X_FACTORY_X_FARM_KEY_X_SUBFARM_KEY_X_VARIETY
```

**Physical event (verified):**
```
FACTORY_RECEIPT_NOT_FARM_PICK
```

This is a **factory-receipt** event, not a farm-pick event. The weight is post-pick factory intake, including pick loss, sorting loss, transport loss, and multi-pick consolidation.

**Receipt proxy status:**
```
RECEIPT_PROXY_STATUS                  = NON_PRIMARY_PROXY
RECEIPT_PROXY_PRIMARY_LABEL_STATUS    = FORBIDDEN
ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET = YES
```

Even though `FactReceiptDaily` carries a relatively complete identity set (farm/subfarm/variety/factory/season), it is a **proxy**. It MUST NOT substitute for the primary actual-harvest label. Receipt can be used for **secondary diagnostics** but is not the primary target.

### 2.4 Test fixture `actual_harvest_quantity_kg` (FIXTURE_ONLY)

Locations:
- `backend/tests/fixtures/harvest_quality_data.py`
- `backend/tests/production_path/conftest.py`
- `backend/tests/production_path/scheme_candidate_aggregate_acceptance.py`

**Production wired:** NO (fixture-only).
**Classification:** `UNKNOWN_REQUIRES_CONFIRMATION`.

Excluded from the actual-harvest audit because `production_wired = fixture_only`.

## 3. Audit scope (P0-2)

This audit is bounded by the following explicit discovery-scope statuses:

```
SOURCE_DISCOVERY_SCOPE                  = CURRENT_REPOSITORY_AND_CHECKED_LOCAL_ARTIFACTS_ONLY
REPOSITORY_MODEL_DISCOVERY_STATUS       = COMPLETED
REPOSITORY_MIGRATION_DISCOVERY_STATUS   = COMPLETED
CHECKED_LOCAL_EXPORT_DISCOVERY_STATUS   = NO_AUTHORIZED_SOURCE_ARTIFACT_FOUND
LIVE_DATABASE_SOURCE_DISCOVERY_STATUS   = NOT_EXECUTED
EXTERNAL_BUSINESS_SOURCE_DISCOVERY_STATUS = NOT_AUTHORIZED_NOT_EXECUTED
```

### 3.1 What this audit covered

- full search of `backend/app/models/**`, `backend/app/schemas/**`, `backend/app/services/**`, `backend/app/repositories/**`, `backend/alembic/versions/**`, `backend/tests/**`, `docs/**`, fixtures, Goldens, import/export adapters, ETL code;
- all alembic migrations reviewed for actual-harvest table creation;
- checked-in source exports — none found.

### 3.2 What this audit did NOT cover

- live PostgreSQL connection (NOT EXECUTED);
- external business sources (farm ERP systems, picking logs, weighing systems, spreadsheets, unconnected production databases, Charles's local-only data directories) (NOT AUTHORIZED, NOT EXECUTED).

The audit does **not** prove that no source exists in these unchecked locations. It proves only that no source was found **within the audited scope**.

## 4. Canonical source fields (DESIGN CANDIDATE — not yet implemented)

The following are **design candidates** for a future direct actual-harvest table. They do NOT exist in production schema as of Q2A design freeze.

| field | type | business_semantics |
|---|---|---|
| actual_harvest_record_id | BIGINT | primary key |
| source_system | Text | originating system identifier |
| source_dataset | Text | originating dataset/table name |
| source_record_id | Text | source-native identifier |
| source_version | Text | source schema/snapshot version |
| season_id | BIGINT | FK to season |
| farm_id | BIGINT | FK to farm |
| subfarm_id_or_null | BIGINT, nullable | FK to subfarm if present |
| plot_id_or_null | BIGINT, nullable | FK to plot if present |
| subfarm_or_plot_identity_key | Text | canonical identity string |
| variety_id | BIGINT | FK to variety |
| harvest_business_date | Date | farm-local business date |
| farm_timezone | Text | IANA TZ for date boundary |
| actual_harvest_quantity_kg | Numeric(18,6) | observed weight in kg |
| recorded_at | DateTime | first source-recorded timestamp |
| revised_at_or_null | DateTime, nullable | latest revision timestamp |
| finalized_at_or_null | DateTime, nullable | final-adjudicated timestamp |
| revision_number | Integer | monotonically increasing per source_record_id |
| supersedes_record_id_or_null | BIGINT, nullable | lineage pointer |
| record_status | enum | ACTIVE / VOID / CORRECTED / FINALIZED |
| source_batch_id | Text | ingestion batch identifier |
| source_artifact_hash | Text | SHA-256 of source artifact |
| source_row_hash | Text | SHA-256 of source row |

These fields are **design only**. No claim of schema existence is made.

**Source schema realization status:**

- `record_status` column, lineage pointers, and revision_number semantics: **DESIGN_CANDIDATE_ONLY** / **NOT_IMPLEMENTED** / **NOT_VALIDATED_AGAINST_REAL_SOURCE**.

## 5. Source outcome (FINAL, P0-2 corrected)

### 5.1 Result

```
DIRECT_ACTUAL_HARVEST_SOURCE_STATUS = DIRECT_ACTUAL_HARVEST_SOURCE_NOT_FOUND_IN_CURRENT_REPOSITORY
PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO
ALIGNMENT_DECISION                 = ALIGNMENT_BLOCKED_BY_MISSING_PRIMARY_LABEL
ACTUAL_LABEL_CANONICAL_GRAIN       = FARM_X_SUBFARM_OR_PLOT_X_VARIETY_X_HARVEST_DATE
ACTUAL_LABEL_UNIT                  = KG
```

**Evidence summary:**

| aspect | finding |
|---|---|
| production tables with actual-harvest semantics | **NONE** (within audited scope) |
| migrations creating actual-harvest table | **NONE** (within audited scope) |
| production wired source observing physical pick event | **NONE** (within audited scope) |
| fixture-only references with name `actual_harvest_quantity_kg` | 3 (test code only) |

The audit's evidence boundary is **precise**: it covers only the current repository and checked-in local artifacts. The audit does **not** assert anything about external farm ERP systems, picking logs, weighing systems, spreadsheets, or unconnected production databases.

### 5.2 What is NOT direct actual harvest

- `HarvestStateDailyMemberRowModel.harvested_quantity_kg` is **MODEL OUTPUT** (forecast's harvested-output quantity); the name contains "harvested" but the semantic is model-derived.
- `HarvestStateDailyMemberRowModel.harvestable_mature_quantity_kg` is **DERIVED STATE** (mature inventory).
- `ForecastDailyRow.harvested_quantity_kg` is **MODEL OUTPUT** (Agent aggregate).
- `fact_receipt_daily.weight_kg` is **ARRIVAL/RECEIPT PROXY** (factory gate weight, not pick event).

### 5.3 Receipt proxy authority for primary target

```
RECEIPT_PROXY_IDENTITY_GRAIN                = SEASON_X_RECEIPT_DATE_X_FACTORY_X_FARM_KEY_X_SUBFARM_KEY_X_VARIETY
RECEIPT_PROXY_PHYSICAL_EVENT               = FACTORY_RECEIPT_NOT_FARM_PICK
RECEIPT_PROXY_PRIMARY_LABEL_STATUS          = FORBIDDEN
ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET = YES
PRIMARY_TARGET_ACCURACY_REPORTING_WITH_PROXY = FORBIDDEN
```

Receipt weight can be used for **secondary diagnostics** but **must not** be substituted for the primary actual-harvest label.

### 5.4 Why no fallback to receipt proxy

Receipt weight measures factory gate intake, which is downstream of:

- pick loss (berries picked but not delivered);
- pick sorting (unsold/seconds separated before weigh-in);
- transport loss;
- multiple-pick consolidation.

Receipt ≠ harvest. Substituting receipt for harvest violates the business event definition in §1.

## 6. Conclusion (FINAL)

- `DIRECT_ACTUAL_HARVEST_SOURCE_STATUS = DIRECT_ACTUAL_HARVEST_SOURCE_NOT_FOUND_IN_CURRENT_REPOSITORY`
- `PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO`
- `ALIGNMENT_DECISION = ALIGNMENT_BLOCKED_BY_MISSING_PRIMARY_LABEL`
- `ACTUAL_LABEL_CANONICAL_GRAIN = FARM_X_SUBFARM_OR_PLOT_X_VARIETY_X_HARVEST_DATE`
- `ACTUAL_LABEL_UNIT = KG`
- `LABEL_REVISION_POLICY = EXPLICIT_UNIQUE_TERMINAL_FAIL_CLOSED`

Q2A implementation is **not authorized**. The lack of a production-wired direct actual-harvest source in the current repository blocks Q2A implementation and downstream Q2B until Charles authorizes a source ingestion path, a live-database inspection, or an external business-system source.

---

## §X. Change log

- **v1.0** (Q2A design round): freeze contract; document `DIRECT_ACTUAL_HARVEST_SOURCE_NOT_FOUND_IN_CURRENT_REPOSITORY` outcome; block alignment.
- **v1.1** (Q2A re-review fixup round, Issue #102 comment `4975425033`): correct repository paths to current-main truth; scope source-discovery to current-repository evidence; reconcile identifier types (BIGINT not UUID) and quantile contract (P50/P80/P90, no P10); separate receipt proxy identity capture from primary-label prohibition.

---

## §X.1 Q2A final decision table (cross-document consistency block)

These status values are emitted by this document and must be byte-for-byte identical in the companion documents `q2a-actual-harvest-source-contract.md`, `q2a-label-snapshot-and-revision-contract.md`, `q2a-prediction-label-alignment-decision.md`, and `q2a-data-coverage-audit.md`.

```
DIRECT_ACTUAL_HARVEST_SOURCE_STATUS = DIRECT_ACTUAL_HARVEST_SOURCE_NOT_FOUND_IN_CURRENT_REPOSITORY
SOURCE_DISCOVERY_SCOPE = CURRENT_REPOSITORY_AND_CHECKED_LOCAL_ARTIFACTS_ONLY
LIVE_DATABASE_SOURCE_DISCOVERY_STATUS = NOT_EXECUTED
EXTERNAL_BUSINESS_SOURCE_DISCOVERY_STATUS = NOT_AUTHORIZED_NOT_EXECUTED
PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO
ACTUAL_LABEL_CANONICAL_GRAIN = FARM_X_SUBFARM_OR_PLOT_X_VARIETY_X_HARVEST_DATE
ACTUAL_LABEL_UNIT = KG
FORECAST_CUTOFF_MODEL = CONFIRMED
LABEL_OBSERVATION_CUTOFF_MODEL = CONFIRMED_DESIGN_ONLY
LABEL_REVISION_POLICY = EXPLICIT_UNIQUE_TERMINAL_FAIL_CLOSED
TASK9_MEMBER_PREDICTION_STATUS = AVAILABLE_MODEL_OUTPUT
TASK9_MEMBER_SCHEMA_PATH = backend/app/models/harvest_state.py
PATH_A_PREDICTION_SIDE_ELIGIBILITY = STRUCTURALLY_ELIGIBLE_PENDING_LABEL_AND_GRAIN_PROOF
AGENT_AGGREGATE_PREDICTION_STATUS = AVAILABLE_MODEL_OUTPUT
AGENT_DAILY_SCHEMA_PATH = backend/app/agent/schemas.py
PATH_B_DIRECT_ROW_GRAIN = RESOLVED_REQUEST_AGGREGATE_X_DATE
PATH_B_QUANTILE_STATUS = P50_P80_P90_AVAILABLE
PATH_B_PREDICTION_SIDE_ELIGIBILITY = STRUCTURALLY_ELIGIBLE_PENDING_LABEL_AGGREGATION_CONTRACT
ARRIVAL_PROXY_STATUS = NON_PRIMARY_PROXY
ARRIVAL_PROXY_SCHEMA_PATH = backend/app/models/analytics.py
ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET = YES
PHYSICAL_QUANTITY_ALIGNMENT = NOT_PROVEN_MISSING_LABEL
GRAIN_ALIGNMENT = NOT_PROVEN_MISSING_LABEL_AND_MEMBERSHIP_CONTRACT
ALIGNMENT_DECISION = ALIGNMENT_BLOCKED_BY_MISSING_PRIMARY_LABEL
REAL_DATA_COVERAGE_STATUS = NOT_VERIFIED_SOURCE_UNAVAILABLE
REAL_DATA_COVERAGE_SCOPE = CURRENT_REPOSITORY_ONLY
Q2A_STATUS = PENDING_REVIEW
Q2A_IMPLEMENTATION_READY = NO
Q2B_AUTHORIZED=*** = NO
Q3_AUTHORIZED=*** = NO
MODEL_CHANGE_AUTHORIZED=*** = NO
```
DIRECT_ACTUAL_HARVEST_SOURCE_STATUS = DIRECT_ACTUAL_HARVEST_SOURCE_NOT_FOUND_IN_CURRENT_REPOSITORY
SOURCE_DISCOVERY_SCOPE = CURRENT_REPOSITORY_AND_CHECKED_LOCAL_ARTIFACTS_ONLY
LIVE_DATABASE_SOURCE_DISCOVERY_STATUS = NOT_EXECUTED
EXTERNAL_BUSINESS_SOURCE_DISCOVERY_STATUS = NOT_AUTHORIZED_NOT_EXECUTED
PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO
ACTUAL_LABEL_CANONICAL_GRAIN = FARM_X_SUBFARM_OR_PLOT_X_VARIETY_X_HARVEST_DATE
ACTUAL_LABEL_UNIT = KG
FORECAST_CUTOFF_MODEL = CONFIRMED
LABEL_OBSERVATION_CUTOFF_MODEL = CONFIRMED_DESIGN_ONLY
LABEL_REVISION_POLICY = EXPLICIT_UNIQUE_TERMINAL_FAIL_CLOSED
TASK9_MEMBER_PREDICTION_STATUS = AVAILABLE_MODEL_OUTPUT
TASK9_MEMBER_SCHEMA_PATH = backend/app/models/harvest_state.py
PATH_A_PREDICTION_SIDE_ELIGIBILITY = STRUCTURALLY_ELIGIBLE_PENDING_LABEL_AND_GRAIN_PROOF
AGENT_AGGREGATE_PREDICTION_STATUS = AVAILABLE_MODEL_OUTPUT
AGENT_DAILY_SCHEMA_PATH = backend/app/agent/schemas.py
PATH_B_DIRECT_ROW_GRAIN = RESOLVED_REQUEST_AGGREGATE_X_DATE
PATH_B_QUANTILE_STATUS = P50_P80_P90_AVAILABLE
PATH_B_PREDICTION_SIDE_ELIGIBILITY = STRUCTURALLY_ELIGIBLE_PENDING_LABEL_AGGREGATION_CONTRACT
ARRIVAL_PROXY_STATUS = NON_PRIMARY_PROXY
ARRIVAL_PROXY_SCHEMA_PATH = backend/app/models/analytics.py
ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET = YES
PHYSICAL_QUANTITY_ALIGNMENT = NOT_PROVEN_MISSING_LABEL
GRAIN_ALIGNMENT = NOT_PROVEN_MISSING_LABEL_AND_MEMBERSHIP_CONTRACT
ALIGNMENT_DECISION = ALIGNMENT_BLOCKED_BY_MISSING_PRIMARY_LABEL
REAL_DATA_COVERAGE_STATUS = NOT_VERIFIED_SOURCE_UNAVAILABLE
REAL_DATA_COVERAGE_SCOPE = CURRENT_REPOSITORY_ONLY
Q2A_STATUS = PENDING_REVIEW
Q2A_IMPLEMENTATION_READY = NO
Q2B_AUTHORIZED=*** = NO
Q3_AUTHORIZED=*** = NO
MODEL_CHANGE_AUTHORIZED=*** = NO
```
