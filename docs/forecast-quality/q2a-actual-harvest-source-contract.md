# Slice Q2A — Actual-Harvest Source Contract

> **Issue:** #102
> **Slice:** Q2A — Actual-harvest source, label snapshot, prediction alignment
> **Type:** Docs-only design freeze
> **Authorization:** Issue #102 comment ID `4975150023`
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

## 2. Candidate source inventory (exhaustive read-only audit)

### 2.1 Repository schema inventory (production code)

| source_name | source_type | repository_path | business_meaning | quantity_field | unit | business_date_field | farm_identity | subfarm_or_plot | variety_identity | direct_or_proxy | production_wired |
|---|---|---|---|---|---|---|---|---|---|---|---|
| HarvestStateDailyMemberRowModel.harvested_quantity_kg | MODEL_OUTPUT | `backend/app/models/domain/production_path/harvest_state/harvest_state_daily_member_row.py` | Model's harvested-output quantity per member per state_date | harvested_quantity_kg | kg | state_date | farm_id + subfarm_identity_key | subfarm_identity_key (no plot) | variety_id | MODEL_OUTPUT | production |
| HarvestStateDailyMemberRowModel.harvestable_mature_quantity_kg | DERIVED_STATE | `backend/app/models/domain/production_path/harvest_state/harvest_state_daily_member_row.py` | Mature-but-unpicked inventory state | harvestable_mature_quantity_kg | kg | state_date | farm_id + subfarm_identity_key | subfarm_identity_key | variety_id | DERIVED_STATE | production |
| ForecastDailyRow.harvested_quantity_kg | MODEL_OUTPUT | `backend/app/models/domain/forecast/forecast_daily_row.py` | Agent aggregate forecast output | harvested_quantity_kg | kg | forecast_date | farm_id | subfarm_id (nullable) | variety_id | MODEL_OUTPUT | production |
| fact_receipt_daily.weight_kg | ARRIVAL_OR_RECEIPT_PROXY | `backend/app/models/domain/production/fact_receipt_daily.py` | Factory receipt weight at gate | weight_kg | kg | receipt_date | farm_id (implied via supplier) | NOT captured | NOT captured | ARRIVAL_OR_RECEIPT_PROXY | production |

### 2.2 Test fixture inventory (NOT production wired)

| source_name | source_type | repository_path | business_meaning | production_wired_or_fixture_only |
|---|---|---|---|---|
| test_harvest_quality_data.actual_harvest_quantity_kg | UNKNOWN_REQUIRES_CONFIRMATION | `backend/tests/fixtures/harvest_quality_data.py` | Test fixture field name | fixture_only |
| production_path scheme_run scheme_candidate aggregate | UNKNOWN_REQUIRES_CONFIRMATION | `backend/tests/production_path/scheme_candidate_aggregate_acceptance.py` | Test factory field | fixture_only |
| production_path conftest aggregate | UNKNOWN_REQUIRES_CONFIRMATION | `backend/tests/production_path/conftest.py` | Test factory field | fixture_only |

### 2.3 Database discovery

Read-only inspection of schema inventory, repository-defined source databases, and migrations:

| domain | findings |
|---|---|
| tables with "actual_harvest" in name | **0 production tables; 3 fixture-only references** |
| migrations creating actual-harvest table | **0 alembic migrations** |
| alembic versions inspected | `backend/alembic/versions/*.py` (full directory) — **0 actual-harvest migration** |
| production PostgreSQL configured | PostgreSQL DSN configured in `backend/app/settings/...` — empty in dev; no row-level access attempted |
| SQLite development database | none checked in to repo |
| import manifests / CSV / Excel / JSON / Parquet | none checked in |

### 2.4 Source exports

**Not applicable** — no checked-in source exports found. No database dump metadata. No import manifests.

## 3. Canonical source fields (DESIGN CANDIDATE — not yet implemented)

The following are **design candidates** for a future direct actual-harvest table. They do NOT exist in production schema as of Q2A design freeze.

| field | type | business_semantics |
|---|---|---|
| actual_harvest_record_id | uuid | primary key |
| source_system | text | originating system identifier |
| source_dataset | text | originating dataset/table name |
| source_record_id | text | source-native identifier |
| source_version | text | source schema/snapshot version |
| season_id | uuid | FK to season |
| farm_id | uuid | FK to farm |
| subfarm_id_or_null | uuid nullable | FK to subfarm if present |
| plot_id_or_null | uuid nullable | FK to plot if present |
| subfarm_or_plot_identity_key | text | canonical identity string |
| variety_id | uuid | FK to variety |
| harvest_business_date | date | farm-local business date |
| farm_timezone | text | IANA TZ for date boundary |
| actual_harvest_quantity_kg | decimal(18,6) | observed weight in kg |
| recorded_at | timestamptz | first source-recorded timestamp |
| revised_at_or_null | timestamptz nullable | latest revision timestamp |
| finalized_at_or_null | timestamptz nullable | final-adjudicated timestamp |
| revision_number | int | monotonically increasing per source_record_id |
| supersedes_record_id_or_null | uuid nullable | lineage pointer |
| record_status | enum | ACTIVE / VOID / CORRECTED / FINALIZED |
| source_batch_id | text | ingestion batch identifier |
| source_artifact_hash | text | SHA-256 of source artifact |
| source_row_hash | text | SHA-256 of source row |

These fields are **design only**. No claim of schema existence is made.

## 4. Required semantics

### 4.1 Record status (FROZEN)

- `ACTIVE` — current effective record
- `VOID` — explicitly invalidated
- `CORRECTED` — superseded by a newer record in same lineage chain
- `FINALIZED` — reached final business adjudication; no further revisions allowed

### 4.2 Business-day semantics (FROZEN)

- `zero_harvest_day` — recorded weight = 0 (legitimate)
- `missing_day` — no record for a business day that should have one
- `unknown_day` — record exists but identity/quantity unknown
- `plant_not_operating_day` — no operation; equivalent to `zero_harvest_day` if recorded, otherwise `missing_day`

### 4.3 Failure cases (fail-closed)

- `duplicate` — multiple records for same business-key (farm × subfarm/plot × variety × harvest_business_date)
- `late_arriving_record` — recorded_at > label_observation_cutoff_at
- `cross_source_conflict` — same business-key with different quantities across source families
- `negative_quantity` — physically impossible
- `unit_mismatch` — non-kg unit, no conversion
- `timezone_mismatch` — ambiguous farm-local date
- `identity_mismatch` — subfarm/plot identity inconsistent across rows

## 5. Source outcome (FINAL)

### `DIRECT_ACTUAL_HARVEST_SOURCE_NOT_FOUND`

**Evidence summary:**

| aspect | finding |
|---|---|
| production tables with actual-harvest semantics | **NONE** |
| migrations creating actual-harvest table | **NONE** |
| production wired source observing physical pick event | **NONE** |
| fixture-only references with name `actual_harvest_quantity_kg` | 3 (test code only) |
| repository-defined actual-harvest ingestion | **NONE** |

### 5.1 What is NOT direct actual harvest

- `HarvestStateDailyMemberRowModel.harvested_quantity_kg` is **model output** (forecast's harvested-output quantity); the name contains "harvested" but the semantic is model-derived.
- `HarvestStateDailyMemberRowModel.harvestable_mature_quantity_kg` is **derived state** (mature inventory).
- `ForecastDailyRow.harvested_quantity_kg` is **agent aggregate forecast output**.
- `fact_receipt_daily.weight_kg` is **arrival/receipt proxy** (factory gate weight, not pick event).

### 5.2 Proxy authority for primary target

`fact_receipt_daily.weight_kg`:

- `ARRIVAL_OR_RECEIPT_PROXY_STATUS = NON_PRIMARY_PROXY`
- `ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET = YES`
- `PRIMARY_TARGET_ACCURACY_REPORTING_WITH_PROXY = FORBIDDEN`

Receipt weight can be used for **secondary diagnostics** but **must not** be substituted for the primary actual-harvest label.

### 5.3 Why no fallback to receipt proxy

Receipt weight measures factory gate intake, which is downstream of:

- pick loss (berries picked but not delivered);
- pick sorting (unsold/seconds separated before weigh-in);
- transport loss;
- multiple-pick consolidation.

Receipt ≠ harvest. Substituting receipt for harvest violates the business event definition in §1.

## 6. Pending source authority (Charles decision required)

**No source candidate qualifies for `SOURCE_CANDIDATE_REQUIRES_CHARLES_CONFIRMATION`** — because no candidate exists in production schema or migrations. The "candidate" pool is empty.

The repository's test fixtures include a field named `actual_harvest_quantity_kg`, but:

- the field is **fixture-only**;
- the field name does not, by itself, prove the field represents a real business event in production;
- production source of these fixture values is **not documented in the repository**.

## 7. Conclusion (FINAL)

- `DIRECT_ACTUAL_HARVEST_SOURCE_STATUS = DIRECT_ACTUAL_HARVEST_SOURCE_NOT_FOUND`
- `PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO`
- `ALIGNMENT_DECISION = ALIGNMENT_BLOCKED`
- `ACTUAL_LABEL_CANONICAL_GRAIN = FARM_X_SUBFARM_OR_PLOT_X_VARIETY_X_HARVEST_DATE`
- `ACTUAL_LABEL_UNIT = KG`
- `LABEL_REVISION_POLICY = EXPLICIT_UNIQUE_TERMINAL_FAIL_CLOSED`

Q2A implementation is **not authorized**. The lack of a production-wired direct actual-harvest source blocks Q2A implementation and downstream Q2B until Charles authorizes a source ingestion path or explicitly waives the direct-source requirement.

---

## §X. Change log

- **v1.0** (Q2A design round): freeze contract; document `DIRECT_ACTUAL_HARVEST_SOURCE_NOT_FOUND` outcome; block alignment.

---

## §X.1 Q2A final decision table (cross-document consistency block)

These status values are emitted by this document and must be identical in the companion documents `q2a-label-snapshot-and-revision-contract.md`, `q2a-prediction-label-alignment-decision.md`, and `q2a-data-coverage-audit.md`.

```
DIRECT_ACTUAL_HARVEST_SOURCE_STATUS = DIRECT_ACTUAL_HARVEST_SOURCE_NOT_FOUND
PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO
ACTUAL_LABEL_CANONICAL_GRAIN = FARM_X_SUBFARM_OR_PLOT_X_VARIETY_X_HARVEST_DATE
ACTUAL_LABEL_UNIT = KG
FORECAST_CUTOFF_MODEL = CONFIRMED
LABEL_OBSERVATION_CUTOFF_MODEL = CONFIRMED_DESIGN_ONLY
LABEL_REVISION_POLICY = EXPLICIT_UNIQUE_TERMINAL_FAIL_CLOSED
TASK9_MEMBER_PREDICTION_STATUS = AVAILABLE_MODEL_OUTPUT
AGENT_AGGREGATE_PREDICTION_STATUS = AVAILABLE_MODEL_OUTPUT
ARRIVAL_PROXY_STATUS = NON_PRIMARY_PROXY
ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET = YES
PHYSICAL_QUANTITY_ALIGNMENT = NOT_PROVEN
GRAIN_ALIGNMENT = NOT_ALIGNED
ALIGNMENT_DECISION = ALIGNMENT_BLOCKED
REAL_DATA_COVERAGE_STATUS = NOT_VERIFIED_SOURCE_UNAVAILABLE
Q2A_STATUS = PENDING_REVIEW
Q2A_IMPLEMENTATION_READY = NO
Q2B_AUTHORIZED = NO
Q3_AUTHORIZED = NO
MODEL_CHANGE_AUTHORIZED = NO
```