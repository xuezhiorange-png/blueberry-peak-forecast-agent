# Slice Q2A — Aggregate-Only Data Coverage Audit

> **Issue:** #102
> **Slice:** Q2A — Actual-harvest source, label snapshot, prediction alignment
> **Type:** Docs-only design freeze
> **Authorization:** Issue #102 comment ID `4975150023`
> **Status:** PENDING_REVIEW
> **Companion documents:**
> - `q2a-actual-harvest-source-contract.md`
> - `q2a-label-snapshot-and-revision-contract.md`
> - `q2a-prediction-label-alignment-decision.md`

---

## 1. Scope

This document records an **aggregate-only** read-only audit of all candidate actual-harvest sources identified in `q2a-actual-harvest-source-contract.md`. Aggregate-only means row-level data is never inspected; only counts, distinct values, and date ranges.

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

## 3. Per-source aggregate-only audit

### 3.1 HarvestStateDailyMemberRowModel (MODEL_OUTPUT — not actual harvest)

| metric | value | source |
|---|---|---|
| production table | YES | `backend/app/models/domain/production_path/harvest_state/harvest_state_daily_member_row.py` |
| row_count | not inspected (out of scope for actual-harvest audit) | n/a — model output, not actual harvest |
| business_meaning | model-derived harvested-output quantity | design |
| direct_or_proxy | MODEL_OUTPUT | classification |
| actual_harvest_candidate | NO | by definition |

This source is excluded from actual-harvest aggregate audit because it is a model output, not an observation.

### 3.2 HarvestStateDailyMemberRowModel.harvestable_mature_quantity_kg (DERIVED_STATE — not actual harvest)

| metric | value | source |
|---|---|---|
| production table | YES | same as §3.1 |
| business_meaning | mature-but-unpicked inventory state | design |
| direct_or_proxy | DERIVED_STATE | classification |
| actual_harvest_candidate | NO | by definition |

Excluded from actual-harvest aggregate audit (mature inventory ≠ picked quantity).

### 3.3 ForecastDailyRow.harvested_quantity_kg (MODEL_OUTPUT — Agent aggregate)

| metric | value | source |
|---|---|---|
| production table | YES | `backend/app/models/domain/forecast/forecast_daily_row.py` |
| business_meaning | Agent aggregate forecast output | design |
| direct_or_proxy | MODEL_OUTPUT | classification |
| actual_harvest_candidate | NO | by definition |

Excluded from actual-harvest aggregate audit (agent output ≠ observation).

### 3.4 fact_receipt_daily.weight_kg (ARRIVAL_OR_RECEIPT_PROXY — proxy only)

| metric | value | source |
|---|---|---|
| production table | YES | `backend/app/models/domain/production/fact_receipt_daily.py` |
| business_meaning | factory gate receipt weight | design |
| direct_or_proxy | ARRIVAL_OR_RECEIPT_PROXY | classification |
| actual_harvest_candidate | NO | by definition |
| PRIMARY_TARGET_ACCURACY_REPORTING | FORBIDDEN | see `q2a-actual-harvest-source-contract.md` §5.2 |

Aggregate audit of receipt data is out of scope for the primary actual-harvest label. Aggregate-only diagnostics may be performed separately and must be flagged as receipt-proxy diagnostics.

### 3.5 Test fixture `actual_harvest_quantity_kg` (fixture-only)

| metric | value | source |
|---|---|---|
| production table | NO | fixture-only in `backend/tests/fixtures/harvest_quality_data.py` and `backend/tests/production_path/conftest.py` and `backend/tests/production_path/scheme_candidate_aggregate_acceptance.py` |
| business_meaning | test factory field | fixture |
| direct_or_proxy | UNKNOWN_REQUIRES_CONFIRMATION | classification |
| actual_harvest_candidate | NO | by production_wired = fixture_only |

Excluded from actual-harvest aggregate audit because production_wired = fixture_only.

## 4. Migration / schema coverage

| domain | coverage finding |
|---|---|
| `backend/alembic/versions/*.py` (full directory) | 0 actual-harvest migrations |
| `backend/app/models/domain/production_path/**` | 0 actual-harvest tables |
| `backend/app/models/domain/production/**` | 0 actual-harvest tables |
| `backend/app/models/domain/forecast/**` | 0 actual-harvest tables |
| `backend/app/models/domain/harvest/**` | directory absent |
| `backend/app/models/domain/actual/**` | directory absent |

## 5. Database discovery

| database | coverage finding |
|---|---|
| PostgreSQL DSN configured | yes (via `backend/app/settings/...`); not connected from audit |
| SQLite development database | not checked in |
| repository-defined source database | none checked in |
| locally imported source files | none found |
| import manifests | none found |
| CSV / Excel / JSON / Parquet | none checked in |

## 6. Coverage status (FINAL)

### `NOT_VERIFIED_SOURCE_UNAVAILABLE`

The candidate actual-harvest source pool is **empty** in production schema and migrations. There is no production-wired table, view, or ingestion that observes physical pick events from farm/subfarm/plot during a harvest business date.

Aggregate-only audit cannot be performed because there is no production table to aggregate over.

## 7. Why `NOT_VERIFIED_SOURCE_UNAVAILABLE` and not a coverage-verified status

Per §12.3 of the Q2A design authorization:

> Coverage-verified status cannot be asserted solely because schema exists.

In Q2A's case, **the schema does not even exist** for actual-harvest observation. Schema absence precludes any coverage-verified status. The correct status is `NOT_VERIFIED_SOURCE_UNAVAILABLE` because the source itself is absent — not because coverage is bad, but because there is nothing to cover.

## 8. Conclusion (FINAL)

- `REAL_DATA_COVERAGE_STATUS = NOT_VERIFIED_SOURCE_UNAVAILABLE`
- `REAL_DATA_AGGREGATE_EVIDENCE = NONE` (no aggregate query was issued because no production table exists)
- `BLOCKED_BY_IDENTITY_GAP = NO` (the gap is upstream — no table)
- `BLOCKED_BY_REVISION_GAP = NO` (same)
- `BLOCKED_BY_TIME_GAP = NO` (same)

This audit is **read-only**. No row-level data was inspected; no DSN was opened; no external system was queried.

---

## §X. Change log

- **v1.0** (Q2A design round): record aggregate-only audit outcome; report `NOT_VERIFIED_SOURCE_UNAVAILABLE` because no production table exists.

---

## §X.1 Q2A final decision table (cross-document consistency block)

These status values are emitted by this document and must be identical in the companion documents `q2a-actual-harvest-source-contract.md`, `q2a-label-snapshot-and-revision-contract.md`, and `q2a-prediction-label-alignment-decision.md`.

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