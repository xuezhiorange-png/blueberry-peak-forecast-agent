# Slice Q2A — Prediction-Label Alignment Decision

> **Issue:** #102
> **Slice:** Q2A — Actual-harvest source, label snapshot, prediction alignment
> **Type:** Docs-only design freeze
> **Authorization:** Issue #102 comment ID `4975150023`
> **Status:** PENDING_REVIEW
> **Companion documents:**
> - `q2a-actual-harvest-source-contract.md`
> - `q2a-label-snapshot-and-revision-contract.md`
> - `q2a-data-coverage-audit.md`

---

## 1. Scope

This document evaluates two candidate paths for the **prediction side** of an eventual alignment against actual-harvest labels, and emits a single decision:

- `PATH_A_ACCEPTED`
- `PATH_B_ACCEPTED`
- `ALIGNMENT_BLOCKED`

## 2. Path A — TASK-009 member rows

### 2.1 Source schema

`HarvestStateDailyMemberRowModel` from `backend/app/models/domain/production_path/harvest_state/harvest_state_daily_member_row.py`:

| field | type | role |
|---|---|---|
| harvest_state_run_id | uuid | forecast run identifier |
| state_date | date | forecast business date |
| forecast_quantile | text | quantile band (e.g. p10/p50/p90) |
| capacity_pool_id | uuid | capacity pool FK |
| farm_id | uuid | farm FK |
| subfarm_id | uuid | subfarm FK |
| subfarm_identity_key | text | canonical subfarm identity |
| variety_id | uuid | variety FK |
| destination_factory_id | uuid | factory FK |
| harvested_quantity_kg | decimal | **model output** (not observation) |
| harvestable_mature_quantity_kg | decimal | **derived state** (mature inventory) |

### 2.2 Strengths

- closest grain to actual-label target (farm × subfarm × variety × date);
- farm/subfarm/variety/date/quantile all explicit;
- avoids reversing member allocation from Agent aggregate.

### 2.3 Verification required (each dimension)

| dimension | finding | verified? |
|---|---|---|
| season identity | not present in member row; must be derived from run/harvest_state | NOT_PROVEN |
| forecast cutoff binding | `harvest_state_run_id` references run, but cutoff binding needs to be checked against run metadata | NOT_PROVEN |
| point-in-time replay | `state_date` is present; replayability depends on run immutability | NOT_PROVEN |
| member row from accepted historical authority | depends on run provenance; needs source audit | NOT_PROVEN |
| physical quantity comparable to actual harvest | `harvested_quantity_kg` is model output, semantically NOT actual pick weight | NOT_PROVEN |
| subfarm/plot identity sufficiency | `subfarm_identity_key` present, no `plot_id` | NOT_PROVEN |
| capacity pool duplication | `capacity_pool_id` may introduce many-to-many across pools | NOT_PROVEN |
| destination factory grain impact | `destination_factory_id` partitions member rows by destination; affects grouping | NOT_PROVEN |
| aggregation double-count | potential double-count if multiple pools or destinations produce same business key | NOT_PROVEN |

### 2.4 Verdict (Path A)

`PATH_A_STATUS = AVAILABLE_MODEL_OUTPUT`

Path A's prediction source is production-wired and structurally close to the label grain, but **every alignment dimension is NOT_PROVEN** because:

1. season identity is not intrinsic to the member row;
2. `harvested_quantity_kg` is **model output**, not observation — comparing it to actual-harvest kg conflates prediction with label;
3. capacity-pool and destination-factory partitioning is not proven grain-compatible with actual-harvest business-key (which is farm × subfarm/plot × variety × date, not factory-partitioned).

## 3. Path B — Agent aggregate output

### 3.1 Source schema

`ForecastDailyRow` from `backend/app/models/domain/forecast/forecast_daily_row.py`:

| field | type | role |
|---|---|---|
| harvested_quantity_kg | decimal | Agent aggregate forecast output |
| forecast_date | date | business date |
| farm_id / subfarm_id / variety_id | uuids | identity |

### 3.2 Required aggregation (label side, hypothetical)

To align aggregate prediction with hypothetical actual-harvest label, label must aggregate to:

- resolved request
- × resolved location
- × resolved season
- × calendar date

### 3.3 Verification required (each dimension)

| dimension | finding | verified? |
|---|---|---|
| request membership | membership source needed; cutoff policy needed | NOT_PROVEN |
| location membership | location resolution needed; subfarm vs plot policy | NOT_PROVEN |
| season | season binding via forecast run | NOT_PROVEN |
| variety contribution | variety aggregation semantics | NOT_PROVEN |
| aggregation completeness | completeness check (no missing members) | NOT_PROVEN |
| duplicate prevention | dedup rule for duplicate business-keys | NOT_PROVEN |
| member exclusion | how to exclude non-harvesting members | NOT_PROVEN |
| missing actual members | behavior when label member absent from prediction | NOT_PROVEN |
| zero / missing semantics | zero-day / missing-day policy | NOT_PROVEN |
| output provenance | aggregation provenance must be auditable | NOT_PROVEN |

### 3.4 Verdict (Path B)

`PATH_B_STATUS = AVAILABLE_MODEL_OUTPUT`

Path B's prediction source is production-wired, but every aggregation dimension is NOT_PROVEN because:

1. aggregation membership semantics require Q1/Q2A label-side definition that does not yet exist (no actual-harvest source);
2. `harvested_quantity_kg` is aggregate forecast, not member-level — comparing aggregate prediction to per-farm aggregate label requires aggregate-label definition.

## 4. Alignment dimensions (independent evaluation)

### 4.1 Physical quantity alignment

| dimension | Path A | Path B | verdict |
|---|---|---|---|
| PHYSICAL_QUANTITY_ALIGNMENT | prediction in kg, label must be in kg | prediction in kg, label must be in kg | both NOT_PROVEN because label side is `DIRECT_ACTUAL_HARVEST_SOURCE_NOT_FOUND` |

`PHYSICAL_QUANTITY_ALIGNMENT = NOT_PROVEN`

### 4.2 Grain alignment

| dimension | Path A | Path B | verdict |
|---|---|---|---|
| GRAIN_ALIGNMENT | farm × subfarm × variety × state_date (no factory partition, no plot) | farm × subfarm × variety × forecast_date | both NOT_ALIGNED because: (a) prediction dates may not align with harvest business date, (b) subfarm vs plot inconsistency, (c) destination-factory partition missing |

`GRAIN_ALIGNMENT = NOT_ALIGNED`

### 4.3 Identity alignment

| dimension | Path A | Path B | verdict |
|---|---|---|---|
| IDENTITY_ALIGNMENT | subfarm_id + subfarm_identity_key + variety_id + farm_id | farm_id + subfarm_id + variety_id | both NOT_ALIGNED without label-side identity proof |

`IDENTITY_ALIGNMENT = NOT_PROVEN`

### 4.4 Time alignment

| dimension | Path A | Path B | verdict |
|---|---|---|---|
| TIME_ALIGNMENT | state_date vs harvest_business_date | forecast_date vs harvest_business_date | both NOT_PROVEN because label side has no business-date semantics for actual harvest |

`TIME_ALIGNMENT = NOT_PROVEN`

### 4.5 Revision alignment

| dimension | Path A | Path B | verdict |
|---|---|---|---|
| REVISION_ALIGNMENT | harvest_state_run is a run-level artifact; member rows within a run are immutable; no record-level revision semantics | forecast runs are also run-level; no record-level revision | NOT_APPLICABLE because prediction runs are run-level, not record-level |

`REVISION_ALIGNMENT = NOT_APPLICABLE_PREDICTION_RUN_LEVEL`

### 4.6 Quantile alignment

| dimension | Path A | Path B | verdict |
|---|---|---|---|
| QUANTILE_ALIGNMENT | `forecast_quantile` present (p10/p50/p90); label is point estimate | aggregate forecast typically a point estimate | Path A offers quantile band; Path B does not |

`QUANTILE_ALIGNMENT = NOT_PROVEN`

### 4.7 Coverage alignment

| dimension | Path A | Path B | verdict |
|---|---|---|---|
| COVERAGE_ALIGNMENT | prediction covers a forecast horizon | prediction covers a forecast horizon | NOT_PROVEN because label coverage is empty (no actual-harvest source) |

`COVERAGE_ALIGNMENT = NOT_PROVEN`

## 5. Decision rule (FINAL)

Per §10.4 of the Q2A design authorization, the decision is:

- `ALIGNMENT_DECISION = ALIGNMENT_BLOCKED`

### 5.1 Rationale

1. **No actual-harvest source exists** (`DIRECT_ACTUAL_HARVEST_SOURCE_NOT_FOUND`, see `q2a-actual-harvest-source-contract.md` §5).
2. Without a label, no alignment is provable on any dimension.
3. Both prediction paths are production-wired and structurally close, but their physical-quantity semantic is **model output**, not observation — comparing model output to actual pick weight would conflate prediction with label.
4. The single structural fact available is that `fact_receipt_daily.weight_kg` is `ARRIVAL_OR_RECEIPT_PROXY` and **must not be used as primary label** (see `q2a-actual-harvest-source-contract.md` §5.2).

### 5.2 Why no `PATH_A_ACCEPTED` decision

A status asserting "Path A is preferred" **without** an alignment decision is forbidden by the Q2A design authorization §10.4 (不得以模糊优先表达代替最终状态). The only accepted end states are `PATH_A_ACCEPTED`, `PATH_B_ACCEPTED`, or `ALIGNMENT_BLOCKED`. With no label, neither `PATH_A_ACCEPTED` nor `PATH_B_ACCEPTED` is justified — the only honest decision is `ALIGNMENT_BLOCKED`.

## 6. Conclusion (FINAL)

- `TASK9_MEMBER_PREDICTION_STATUS = AVAILABLE_MODEL_OUTPUT`
- `AGENT_AGGREGATE_PREDICTION_STATUS = AVAILABLE_MODEL_OUTPUT`
- `ARRIVAL_PROXY_STATUS = NON_PRIMARY_PROXY`
- `PATH_A_STATUS = AVAILABLE_MODEL_OUTPUT`
- `PATH_B_STATUS = AVAILABLE_MODEL_OUTPUT`
- `ALIGNMENT_DECISION = ALIGNMENT_BLOCKED`
- `PHYSICAL_QUANTITY_ALIGNMENT = NOT_PROVEN`
- `GRAIN_ALIGNMENT = NOT_ALIGNED`
- `TIME_ALIGNMENT = NOT_PROVEN`
- `REVISION_ALIGNMENT = NOT_APPLICABLE_PREDICTION_RUN_LEVEL`

Q2A implementation is **not authorized**. Alignment is blocked because no production actual-harvest source exists.

---

## §X. Change log

- **v1.0** (Q2A design round): evaluate Path A and Path B; emit `ALIGNMENT_BLOCKED` due to missing label source.

---

## §X.1 Q2A final decision table (cross-document consistency block)

These status values are emitted by this document and must be identical in the companion documents `q2a-actual-harvest-source-contract.md`, `q2a-label-snapshot-and-revision-contract.md`, and `q2a-data-coverage-audit.md`.

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