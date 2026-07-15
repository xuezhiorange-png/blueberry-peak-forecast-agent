# Slice Q2A — Prediction-Label Alignment Decision

> **Issue:** #102
> **Slice:** Q2A — Actual-harvest source, label snapshot, prediction alignment
> **Type:** Docs-only design freeze (Final fixup round)
> **Authorizations:**
> - Issue #102 comment ID `4975150023` (initial design authorization)
> - Issue #102 comment ID `4975425033` (re-review with P0 fixups)
> **Status:** PENDING_REVIEW
> **Companion documents:**
> - `q2a-actual-harvest-source-contract.md`
> - `q2a-label-snapshot-and-revision-contract.md`
> - `q2a-data-coverage-audit.md`

---

## 1. Scope

This document:

1. evaluates Path A (TASK-009 member rows) and Path B (Agent aggregate) prediction sources against the **current main** schema facts;
2. emits a single alignment decision;
3. corrects the previous framing of "comparing model output with actual harvest conflates prediction with label" — that framing was conceptually incorrect (see P0-3).

---

## 2. P0-3 — Prediction-vs-label conceptual correction

### 2.1 What was wrong

The previous version of this document stated that comparing model output with actual harvest would "conflate prediction with label". This is incorrect.

### 2.2 Correct conceptual model

A forecast evaluation **necessarily** compares model prediction output against an independent observed label. Prediction-side model output is **expected and valid**; evaluation is precisely this comparison.

The current blocker is **not** that Path A or Path B is model output. Both prediction paths are model output by design and are structurally eligible to participate in evaluation.

The current blocker is **the absence of an accepted independent primary actual-harvest label source and associated alignment contract**.

### 2.3 Corrected alignment blocker framing

```
ALIGNMENT_DECISION = ALIGNMENT_BLOCKED_BY_MISSING_PRIMARY_LABEL
ALIGNMENT_BLOCKER  = MISSING_PRIMARY_ACTUAL_HARVEST_LABEL
```

The blocker is not the prediction side; it is the label side.

---

## 3. Path A — TASK-009 member rows (P0-1 / P0-4 corrected)

### 3.1 Source schema (current main)

`HarvestStateDailyMemberRowModel` from `backend/app/models/harvest_state.py`:

| field | type | role |
|---|---|---|
| id | BIGINT | primary key |
| harvest_state_run_id | BIGINT | forecast run identifier (FK to `harvest_state_run.id`) |
| state_date | Date | forecast business date |
| forecast_quantile | Text | quantile band, values `P50 | P80 | P90` |
| capacity_pool_id | Text | capacity pool identifier (NOT UUID, NOT a documented FK) |
| capacity_pool_grain | Text | one of `SUBFARM_VARIETY | SUBFARM | FARM` |
| capacity_pool_membership_hash | Text | SHA-256 membership hash |
| farm_id | BIGINT | farm identifier (FK to `dim_farm.id`) |
| subfarm_id | BIGINT, nullable | subfarm identifier (FK to `dim_subfarm.id`) |
| subfarm_identity_key | Text | canonical subfarm identity |
| variety_id | BIGINT | variety identifier (FK to `dim_variety.id`) |
| destination_factory_id | BIGINT | factory identifier (FK to `dim_factory.id`) |
| opening_mature_inventory_kg | Numeric(18,3) | derived state (opening inventory) |
| natural_maturity_supply_kg | Numeric(18,3) | derived state (new supply) |
| available_mature_quantity_kg | Numeric(18,3) | derived state |
| mature_inventory_loss_quantity_kg | Numeric(18,3) | derived state (loss) |
| harvestable_mature_quantity_kg | Numeric(18,3) | **DERIVED STATE** (mature inventory, not picked) |
| allocated_harvest_capacity_kg | Numeric(18,3) | derived state (capacity allocation) |
| harvested_quantity_kg | Numeric(18,3) | **MODEL OUTPUT** (forecast's harvested output) |
| closing_mature_inventory_kg | Numeric(18,3) | derived state |
| unharvested_backlog_kg | Numeric(18,3) | derived state |
| arrival_quantity_kg | Numeric(18,3) | derived state (predicted arrival) |
| opening_cohort_count / closing_cohort_count | BIGINT | cohort counts |
| cohort_source_ref_hashes | JSONB list | source reference hashes |

All identifiers are BIGINT; no UUID claims.

### 3.2 Business-key uniqueness (from production schema)

The production schema declares a unique constraint on:

- `harvest_state_run_id`
- `state_date`
- `capacity_pool_id`
- `farm_id`
- `subfarm_identity_key`
- plus quantile band (verified separately in CHECK)

This defines the **production row grain** for Path A.

### 3.3 Quantile contract

`forecast_quantile` is `P50 | P80 | P90`. There is **no P10**.

The check constraint is:

```
forecast_quantile in ('P50', 'P80', 'P90')
```

### 3.4 Path A direct grain (corrected)

```
HARVEST_STATE_RUN
X STATE_DATE
X CAPACITY_POOL
X FARM
X SUBFARM_IDENTITY_KEY
X VARIETY
X FORECAST_QUANTILE
```

This grain is **production-verified** (the schema's unique constraint).

### 3.5 Path A season and forecast cutoff context (P0-1 / P0-4 corrected)

The member row **does not carry first-class `forecast_season_id` or `forecast_effective_cutoff_at`**. These are available through the parent `HarvestStateRun`:

- `HarvestStateRun.forecast_season_id` (BIGINT, nullable, FK to `dim_season.id`)
- `HarvestStateRun.forecast_effective_cutoff_at` (DateTime, nullable)
- `HarvestStateRun.forecast_start_date` / `forecast_end_date` (Date)
- `HarvestStateRun.replay_executed_at` (DateTime, nullable, replay-only)
- `HarvestStateRun.is_replay` (Boolean, nullable)

**Corrected status (replaces "season identity unavailable / cutoff binding absent"):**

```
PATH_A_SEASON_CONTEXT          = AVAILABLE_VIA_PARENT_RUN_PENDING_BINDING_PROOF
PATH_A_FORECAST_CUTOFF_CONTEXT = AVAILABLE_VIA_PARENT_RUN_PENDING_BINDING_PROOF
```

The fields exist on the parent run; Q2A has not yet proven the **accepted run-selection** and **prediction-label snapshot binding contract** that would use them.

### 3.6 Path A open risks (preserved)

The following risks remain open and must be addressed before Path A can be `ACCEPTED`:

- capacity-pool partition (Path A row is partitioned by `capacity_pool_id`; actual-harvest row is not);
- destination-factory partition (Path A row is partitioned by `destination_factory_id`);
- member row grain vs actual-label grain equality;
- subfarm vs plot identity difference (`subfarm_identity_key` is canonical, but no `plot_id` exists);
- parent run selection (which `HarvestStateRun.id` to use as the evaluation root);
- historical cutoff binding (how to pick `forecast_effective_cutoff_at` from the parent);
- season binding (which `forecast_season_id` is in scope);
- potential duplicate aggregation when aggregating across pools/factories;
- quantile handling (P50/P80/P90 vs point-observation label);
- source visibility (which sources were visible at forecast time);
- replay authority (replay-only metadata vs historical-observed partition).

### 3.7 Path A verdict

```
PATH_A_STATUS                       = AVAILABLE_MODEL_OUTPUT
PATH_A_PREDICTION_SIDE_ELIGIBILITY  = STRUCTURALLY_ELIGIBLE_PENDING_LABEL_AND_GRAIN_PROOF
PATH_A_ACCEPTANCE_STATUS            = NOT_ACCEPTED_MISSING_LABEL_AND_ALIGNMENT_PROOF
```

Path A's prediction source is production-wired with verified schema facts (BIGINT IDs, P50/P80/P90 quantile enum, capacity-pool grain, member-row uniqueness). It is structurally eligible to participate in evaluation **once** an accepted label-side contract exists.

---

## 4. Path B — Agent aggregate output (P0-5 corrected)

### 4.1 Source schema (current main)

`ForecastDailyRow` from `backend/app/agent/schemas.py`:

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

`DailyQuantiles`:

```
class DailyQuantiles(_StrictBase):
    p50: DecimalString
    p80: DecimalString
    p90: DecimalString
```

Three quantiles, **no P10**.

### 4.2 Path B direct grain (P0-5 corrected)

`ForecastDailyRow` does **not** carry first-class `farm_id`, `subfarm_id`, or `variety_id` fields. Its direct grain is:

```
RESOLVED_REQUEST_AGGREGATE_X_DATE
```

This is **NOT** the previous claim of `farm × subfarm × variety × forecast_date`.

Identity is carried by the **enclosing context**:

- `request_id` (from the parent Agent request)
- `normalized_request`
- `resolved_location`
- resolved season identity (from request context)
- daily row `date`
- nested `per_variety_contribution` (variety identity appears here, not as a first-class row identity)

### 4.3 Path B quantity semantics (P0-5 corrected)

`harvested_quantity_kg` is **not a point estimate**. It is a `DailyQuantiles` record containing P50, P80, and P90. The previous framing as "decimal point estimate" is incorrect.

```
PATH_B_QUANTILE_STATUS = P50_P80_P90_AVAILABLE
```

### 4.4 Path B first-class member identities (P0-5 corrected)

```
PATH_B_MEMBER_IDENTITIES = NOT_FIRST_CLASS_ON_DAILY_ROW
```

`farm_id`, `subfarm_id`, `variety_id` are **not** first-class fields on `ForecastDailyRow`. They appear through enclosing request/location/season context and nested `per_variety_contribution`.

### 4.5 Path B open risks (preserved)

The following risks remain open and must be addressed before Path B can be `ACCEPTED`:

- request membership (which `request_id` is in scope);
- location membership (which `resolved_location` is in scope);
- season binding (which season identity is in scope);
- variety contribution aggregation semantics (how to fold `per_variety_contribution` to row-level identity);
- aggregation completeness check (no missing members);
- duplicate prevention (dedup rule for business-key duplicates);
- member exclusion (how to exclude non-harvesting members);
- missing actual members (behavior when label member absent from prediction);
- zero / missing semantics (zero-day / missing-day policy);
- output provenance (aggregation provenance must be auditable);
- quantile evaluation contract (P50/P80/P90 vs point observation — see §6).

### 4.6 Path B verdict

```
PATH_B_STATUS                       = AVAILABLE_MODEL_OUTPUT
PATH_B_QUANTILE_STATUS              = P50_P80_P90_AVAILABLE
PATH_B_DIRECT_ROW_GRAIN             = RESOLVED_REQUEST_AGGREGATE_X_DATE
PATH_B_MEMBER_IDENTITIES            = NOT_FIRST_CLASS_ON_DAILY_ROW
PATH_B_PREDICTION_SIDE_ELIGIBILITY  = STRUCTURALLY_ELIGIBLE_PENDING_LABEL_AGGREGATION_CONTRACT
PATH_B_ACCEPTANCE_STATUS            = NOT_ACCEPTED_MISSING_LABEL_AND_AGGREGATION_PROOF
```

Path B's prediction source is production-wired with verified schema facts (`date`, not `forecast_date`; `DailyQuantiles`, not point estimate; no first-class member IDs). It is structurally eligible to participate in evaluation **once** an accepted label-side aggregation contract exists.

---

## 5. Alignment dimensions (P0 correction — independent evaluation)

### 5.1 `PHYSICAL_QUANTITY_ALIGNMENT`

```
PHYSICAL_QUANTITY_ALIGNMENT = NOT_PROVEN_MISSING_LABEL
```

Both Path A and Path B produce physical quantities in kg. The alignment cannot be **proven** because there is no independent primary label to compare against.

### 5.2 `GRAIN_ALIGNMENT`

```
GRAIN_ALIGNMENT = NOT_PROVEN_MISSING_LABEL_AND_MEMBERSHIP_CONTRACT
```

Path A grain is `harvest_state_run × state_date × capacity_pool × farm × subfarm_identity_key × variety × quantile`. Path B grain is `resolved_request_aggregate × date`. The actual-harvest grain is `farm × subfarm_or_plot × variety × harvest_business_date`. None of these is currently proven equal.

### 5.3 `IDENTITY_ALIGNMENT`

```
IDENTITY_ALIGNMENT = NOT_PROVEN_MISSING_LABEL_IDENTITY_SOURCE
```

Identity keys differ across paths and are not currently proven equal to label identity keys.

### 5.4 `TIME_ALIGNMENT`

```
TIME_ALIGNMENT = NOT_PROVEN_MISSING_LABEL_BUSINESS_DATE_SOURCE
```

Time fields differ: `state_date` (Path A), `date` (Path B), vs `harvest_business_date` (label, DESIGN_CANDIDATE_ONLY).

### 5.5 `REVISION_ALIGNMENT`

```
REVISION_ALIGNMENT = NOT_PROVEN_MISSING_LABEL_REVISION_SOURCE
```

Prediction runs are run-level artifacts; revision semantics exist on the label side (see Doc 2 §4-5).

### 5.6 `QUANTILE_ALIGNMENT` (corrected)

```
QUANTILE_ALIGNMENT = PREDICTION_QUANTILES_AVAILABLE_LABEL_IS_POINT_OBSERVATION
```

This is **not a fail-closed state**. It is the **expected** shape:

- prediction side: P50/P80/P90 (Path A and Path B both);
- label side: point observation (kg);
- comparison type: quantile coverage / calibration (P80/P90 coverage rates, etc.).

A point observation is a normal label for quantile coverage / calibration evaluation. The previous framing of "no quantile in label" as a blocker is incorrect. P80/P90 coverage requires a point-observation label, not a label with quantiles.

### 5.7 `COVERAGE_ALIGNMENT`

```
COVERAGE_ALIGNMENT = NOT_PROVEN_MISSING_LABEL_SOURCE
```

Coverage cannot be proven because there is no production label source.

---

## 6. Decision rule (FINAL, P0-3 corrected)

```
ALIGNMENT_DECISION = ALIGNMENT_BLOCKED_BY_MISSING_PRIMARY_LABEL
ALIGNMENT_BLOCKER  = MISSING_PRIMARY_ACTUAL_HARVEST_LABEL
```

### 6.1 Rationale

1. **No primary actual-harvest label source exists** (`DIRECT_ACTUAL_HARVEST_SOURCE_NOT_FOUND_IN_CURRENT_REPOSITORY`, see Doc 1 §5).
2. Without a label, no alignment dimension can be **proven**, even though prediction-side grains are now verified against current-main schema facts.
3. Both prediction paths are production-wired with corrected schema facts; both are **structurally eligible** to participate in evaluation once a label exists.
4. The block is on the **label** side, not the prediction side.
5. Receipt (`FactReceiptDaily`) is a **proxy**; see Doc 1 §5.2.

### 6.2 Why this is not "Path A preferred" or "Path B preferred"

A status asserting preference without a label is forbidden (Q2A design §10.4). With no label, neither `PATH_A_ACCEPTED` nor `PATH_B_ACCEPTED` is justified. The only honest decision is `ALIGNMENT_BLOCKED_BY_MISSING_PRIMARY_LABEL`.

---

## 7. Conclusion (FINAL)

```
TASK9_MEMBER_PREDICTION_STATUS     = AVAILABLE_MODEL_OUTPUT
AGENT_AGGREGATE_PREDICTION_STATUS  = AVAILABLE_MODEL_OUTPUT
ARRIVAL_PROXY_STATUS               = NON_PRIMARY_PROXY
PATH_A_STATUS                      = AVAILABLE_MODEL_OUTPUT
PATH_B_STATUS                      = AVAILABLE_MODEL_OUTPUT
PATH_A_PREDICTION_SIDE_ELIGIBILITY = STRUCTURALLY_ELIGIBLE_PENDING_LABEL_AND_GRAIN_PROOF
PATH_B_PREDICTION_SIDE_ELIGIBILITY = STRUCTURALLY_ELIGIBLE_PENDING_LABEL_AGGREGATION_CONTRACT
ALIGNMENT_DECISION                 = ALIGNMENT_BLOCKED_BY_MISSING_PRIMARY_LABEL
ALIGNMENT_BLOCKER                  = MISSING_PRIMARY_ACTUAL_HARVEST_LABEL
PHYSICAL_QUANTITY_ALIGNMENT        = NOT_PROVEN_MISSING_LABEL
GRAIN_ALIGNMENT                    = NOT_PROVEN_MISSING_LABEL_AND_MEMBERSHIP_CONTRACT
QUANTILE_ALIGNMENT                 = PREDICTION_QUANTILES_AVAILABLE_LABEL_IS_POINT_OBSERVATION
```

Q2A implementation is **not authorized**. Alignment is blocked because no production actual-harvest source has been found within the audited scope (see Doc 1 §5 / Doc 4 §6).

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

## §X. Change log

- **v1.0** (Q2A design round): evaluate Path A and Path B; emit `ALIGNMENT_BLOCKED` due to missing label source.
- **v1.1** (Q2A final fixup round, comment `4975425033`):
  - **P0-1 / P0-4**: correct Path A schema facts — real path `backend/app/models/harvest_state.py`, BIGINT IDs (not UUID), P50/P80/P90 quantile (not P10), correct grain, correct season/cutoff context (available via parent `HarvestStateRun` pending binding proof).
  - **P0-1 / P0-5**: correct Path B schema facts — real path `backend/app/agent/schemas.py`, `date` (not `forecast_date`), `DailyQuantiles` P50/P80/P90 (not point estimate), direct grain `RESOLVED_REQUEST_AGGREGATE_X_DATE` (not `farm × subfarm × variety × forecast_date`), no first-class member IDs on the row.
  - **P0-3**: correct prediction-vs-label conceptual framing — model output is expected and valid; the blocker is the missing label, not the prediction side. Both paths are structurally eligible.
  - **§5.6**: correct `QUANTILE_ALIGNMENT` — P50/P80/P90 prediction vs point-observation label is the expected coverage/calibration shape, not a fail-closed state.