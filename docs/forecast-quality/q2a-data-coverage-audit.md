# Slice Q2A — Aggregate-Only Data Coverage Audit

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
> - `q2a-prediction-label-alignment-decision.md`

---

## 1. Scope

This document records an **aggregate-only** read-only audit of all candidate actual-harvest sources identified in `q2a-actual-harvest-source-contract.md`. The audit is **scope-limited**: it is performed only against the current repository and checked-in local artifacts. Live database and external business sources are explicitly NOT executed.

This document is corrected in v1.1 (comment `4975425033`) to remove over-broad claims about "no source exists globally" and to add explicit discovery-scope statuses (P0-2 fix).

## 2. Audit method

### 2.1 Allowed queries (aggregate only)

- `row_count` — total row count
- `distinct season count` — number of distinct seasons
- `distinct farm count` — number of distinct farms
- `distinct subfarm_or_plot count` — number of distinct subfarms or plots
- `distinct variety count` — number of distinct varieties
- `min business date` — earliest business date
- `max business date` — latest business date
- `null identity count` — rows with null farm/subfarm/variety
- `zero quantity count` — rows with quantity = 0
- `negative quantity count` — rows with quantity < 0
- `duplicate business-key count` — duplicate (farm × subfarm/plot × variety × business_date)
- `revision count` — distinct revision numbers
- `void count` — record_status = VOID
- `late-arrival count` — recorded_at > label_observation_cutoff_at
- `missing-day count` — missing business days per (farm × subfarm/plot × variety)
- `unknown-day count` — unknown status
- `source overlap count` — same business-key across source families

### 2.2 Forbidden outputs

The following are **never** emitted from this audit:

- row-level harvest records;
- farm-level daily weight detail;
- personnel information;
- personally identifiable information;
- credentials;
- tokens;
- full DSN strings;
- unsanitized file contents;
- real operational sensitive samples.

## 3. Audit scope (P0-2 corrected)

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

- **Completed:** full search of `backend/app/models/**`, `backend/app/schemas/**`, `backend/app/services/**`, `backend/app/repositories/**`, `backend/alembic/versions/**`, `backend/tests/**`, `docs/**`, fixtures, Goldens, import/export adapters, ETL code;
- **Completed:** all alembic migrations reviewed for actual-harvest table creation;
- **Completed:** checked-in source exports — none found.

### 3.2 What this audit did NOT cover (explicit non-coverage)

- **NOT EXECUTED**: live PostgreSQL connection — no row-level query issued;
- **NOT AUTHORIZED, NOT EXECUTED**: external business sources (farm ERP systems, picking logs, weighing systems, spreadsheets, unconnected production databases, Charles's local-only data directories).

The audit does **not** prove that no source exists in these unchecked locations. It proves only that no source was found **within the audited scope**.

## 4. Per-source aggregate-only audit

### 4.1 `HarvestStateDailyMemberRowModel` (`backend/app/models/harvest_state.py`)

- Production table: YES (`harvest_state_daily_member_row`)
- Identifier types: BIGINT for all FK columns (`harvest_state_run_id`, `farm_id`, `subfarm_id`, `variety_id`, `destination_factory_id`)
- Quantile contract: `P50 | P80 | P90` (CHECK constraint)
- Business-key uniqueness: unique on `(harvest_state_run_id, state_date, capacity_pool_id, farm_id, subfarm_identity_key, ...)`
- Classification: `MODEL_OUTPUT` (the `harvested_quantity_kg` field is the model's harvested-output quantity; not actual pick event)

Aggregate audit of production rows not performed because the audit was limited to schema-level discovery (no live DB query).

### 4.2 `ForecastDailyRow` (`backend/app/agent/schemas.py`)

- Production schema: YES (Pydantic schema)
- Date field: `date: date` (NOT `forecast_date`)
- Quantities: `DailyQuantiles` with P50/P80/P90 (NOT point estimates)
- Identity fields: none first-class (`farm_id`, `subfarm_id`, `variety_id` are NOT carried on the row)
- Direct row grain: `RESOLVED_REQUEST_AGGREGATE_X_DATE`
- Classification: `MODEL_OUTPUT` (Agent aggregate forecast output)

### 4.3 `FactReceiptDaily` (`backend/app/models/analytics.py`)

- Production table: YES
- Identity fields: `farm_key` (Text), `subfarm_key` (Text), `variety_id` (BIGINT), `factory_id` (BIGINT), `season_id` (BIGINT), `build_run_id` (BIGINT), `receipt_date` (Date), `weight_kg` (Numeric(18,6)), `source_row_count` (Integer), `created_at` (DateTime)
- Identity grain: `SEASON_X_RECEIPT_DATE_X_FACTORY_X_FARM_KEY_X_SUBFARM_KEY_X_VARIETY`
- Physical event: `FACTORY_RECEIPT_NOT_FARM_PICK` (proxy, NOT direct actual harvest)
- Primary-label status: `FORBIDDEN`

Even though `FactReceiptDaily` carries a relatively complete identity set (farm/subfarm/variety), it is a **factory-receipt** proxy, not a farm-pick event. It MUST NOT substitute for the primary actual-harvest label.

### 4.4 Test fixture `actual_harvest_quantity_kg`

- Production wired: NO (fixture-only)
- Production wired or fixture only: `fixture_only`
- Classification: `UNKNOWN_REQUIRES_CONFIRMATION` (no production source identified)
- Locations: `backend/tests/fixtures/harvest_quality_data.py`, `backend/tests/production_path/conftest.py`, `backend/tests/production_path/scheme_candidate_aggregate_acceptance.py`

Excluded from the actual-harvest audit because `production_wired = fixture_only`.

## 5. Coverage status (FINAL, P0-2 corrected)

```
REAL_DATA_COVERAGE_STATUS          = NOT_VERIFIED_SOURCE_UNAVAILABLE
REAL_DATA_COVERAGE_SCOPE           = CURRENT_REPOSITORY_ONLY
LIVE_DATA_COVERAGE_QUERY_EXECUTED  = NO
```

### 5.1 Why `NOT_VERIFIED_SOURCE_UNAVAILABLE` and not a coverage-verified status

Per the Q2A design authorization §12.3:

> Coverage-verified status cannot be asserted solely because schema exists.

In Q2A's case, the schema for actual-harvest observation **does not exist** in the audited scope. The schema absence precludes any coverage-verified status.

### 5.2 What this status does and does not claim

| claim | status |
|---|---|
| 0 repository-defined direct actual-harvest production tables found | **CLAIMED** (verified by `REPOSITORY_MODEL_DISCOVERY_STATUS = COMPLETED`) |
| 0 migrations creating such a table found | **CLAIMED** (verified by `REPOSITORY_MIGRATION_DISCOVERY_STATUS = COMPLETED`) |
| 0 production rows in actual-harvest tables | **NOT CLAIMED** (live DB NOT EXECUTED) |
| 0 production tables globally | **NOT CLAIMED** (external sources NOT AUTHORIZED, NOT EXECUTED) |
| 0 actual-harvest source exists in any external system | **NOT CLAIMED** (external systems NOT AUDITED) |

The audit's evidence boundary is **precise**: it covers only the current repository and checked-in local artifacts. The audit does **not** assert anything about external farm ERP systems, picking logs, weighing systems, spreadsheets, or unconnected production databases.

### 5.3 What is required to upgrade the coverage status

To move from `NOT_VERIFIED_SOURCE_UNAVAILABLE` to a verified status, at least one of the following would be required (and would itself be a separate authorization round):

- a documented production actual-harvest table or ingestion adapter added to the repository;
- an authorized live database connection with a documented actual-harvest table;
- an authorized external business source artifact (e.g. Charles-supplied picking-log dataset with documented business semantics).

## 6. Conclusion (FINAL)

- `REAL_DATA_COVERAGE_STATUS = NOT_VERIFIED_SOURCE_UNAVAILABLE`
- `REAL_DATA_COVERAGE_SCOPE = CURRENT_REPOSITORY_ONLY`
- `LIVE_DATA_COVERAGE_QUERY_EXECUTED = NO`
- `REAL_DATA_AGGREGATE_EVIDENCE = NONE` (no aggregate query was issued because no production table exists **within the audited scope**)
- `BLOCKED_BY_IDENTITY_GAP = NO`
- `BLOCKED_BY_REVISION_GAP = NO`
- `BLOCKED_BY_TIME_GAP = NO`

The block on downstream evaluation is structural: there is no production actual-harvest table in the audited scope. The audit's scope is explicitly bounded by `SOURCE_DISCOVERY_SCOPE`.

This audit is **read-only**. No row-level data was inspected; no DSN was opened; no external system was queried.

---



- **v1.0** (Q2A design round): record aggregate-only audit outcome; report `NOT_VERIFIED_SOURCE_UNAVAILABLE` because no production table exists.
- **v1.1** (Q2A final fixup round, comment `4975425033`):
  - **P0-2**: scope-limit the source-discovery conclusion. Replace any implicit "no source exists" claim with explicit `DIRECT_ACTUAL_HARVEST_SOURCE_NOT_FOUND_IN_CURRENT_REPOSITORY`. Add `SOURCE_DISCOVERY_SCOPE`, `LIVE_DATABASE_SOURCE_DISCOVERY_STATUS`, `EXTERNAL_BUSINESS_SOURCE_DISCOVERY_STATUS`, `REAL_DATA_COVERAGE_SCOPE`, `LIVE_DATA_COVERAGE_QUERY_EXECUTED` to make the evidence boundary precise.
  - **P0-1**: correct `FactReceiptDaily` schema facts — real path `backend/app/models/analytics.py`; carries `farm_key`, `subfarm_key`, `variety_id`, `receipt_date`, `weight_kg`, plus `build_run_id`, `season_id`, `factory_id`; identity grain `SEASON_X_RECEIPT_DATE_X_FACTORY_X_FARM_KEY_X_SUBFARM_KEY_X_VARIETY`; physical event `FACTORY_RECEIPT_NOT_FARM_PICK`; primary-label status `FORBIDDEN`.

---





- **v1.2** (mechanical contract-block repair under Issue #102 comment `4976151116`): fix malformed authorization keys, remove duplicated status-table copy, and preserve all accepted Q2A substantive decisions.

## §X.1 Q2A final decision table (cross-document consistency block)

These status values are emitted by this document and are byte-for-byte identical in the companion documents.

```text
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
Q2B_AUTHORIZED = NO
Q3_AUTHORIZED = NO
MODEL_CHANGE_AUTHORIZED = NO
```
