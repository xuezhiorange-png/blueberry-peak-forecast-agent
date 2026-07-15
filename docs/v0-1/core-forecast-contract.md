# V0.1-S1 Core Forecast Contract

This document freezes the V0.1 core physical quantities and the complete-season
fixture contract. It is a source-definition artifact only. V0.1-S2 through S5
remain outside this change.

## Quantity-basis evidence

The current code establishes the quantity basis without changing production
code:

- `backend/app/maturity/service.py:920-921` derives the Task 8 total as
  `planted_area_mu * expected_yield_kg_per_mu * marketable_rate` when an
  explicit `expected_total_marketable_kg` is absent.
- `backend/app/maturity/service.py:2596-2605` resolves that value as
  `expected_marketable_total_kg`, and `:2773-2818` allocates it into the P50,
  P80 and P90 daily maturity predictions.
- `backend/app/harvest_state/schemas.py:287-300` defines Task 9 daily supply,
  harvested quantity and arrival quantity as the same state-model quantity
  family.
- `backend/app/harvest_state/service.py:1727-1783` allocates the available
  mature cohorts to `harvested_quantity_kg` and assigns
  `arrival_quantity_kg = harvested_quantity`; `:1787-1800` validates the
  opening + supply - loss - harvest = closing transition.

Therefore the frozen basis is:

```text
TASK8_EXPECTED_TOTAL_BASIS=MARKETABLE
TASK9_MODEL_HARVESTED_BASIS=MARKETABLE
model_harvested_marketable_quantity_kg = Task 9 harvested_quantity_kg
```

V0.1 does not multiply this value by `marketable_rate` again. The production
plan rate is already consumed when Task 8 resolves its marketable total. A
second application would be a double-counting reduction.

## Main daily curve

The V0.1 primary curve is indexed by `harvest_business_date` and uses the
following physical quantity:

```text
effective_marketable_quantity_kg
  = model_harvested_marketable_quantity_kg
  * sorting_retention_rate
  * postharvest_retention_rate
```

`sorting_retention_rate` represents the retained marketable quantity after
sorting. `postharvest_retention_rate` represents the retained quantity after
post-harvest handling. Both are explicit Decimal strings in `[0, 1]`, with
source, version and hash at the `season x farm x subfarm x variety` grain.
There are no production defaults or implicit inheritance rules.

`factory_arrival_date`, `receipt_date` and `processing_date` are not V0.1
primary curve dates. Task 9 arrival scheduling remains reusable evidence, but
the forecast physical quantity is attributed to the harvest business date.

V0.1 uses one explicit logical destination factory. This satisfies the Task 9
request shape without implementing factory selection, routing, allocation or
capacity balancing.

## Daily row contract

Every expected row is sorted by date, farm, subfarm, variety and then
`P50 < P80 < P90`. Quantities and rates are canonical Decimal strings; no
binary float is accepted.

| Field | Unit/type | Required | Authority or meaning |
| --- | --- | --- | --- |
| `date` | ISO date | yes | `HARVEST_BUSINESS_DATE` |
| `forecast_quantile` | enum | yes | P50, P80 or P90 |
| `farm_id`, `subfarm_id`, `variety_id` | integer identity | yes | fixture scope |
| `natural_maturity_supply_kg` | Decimal kg | yes | Task 8 daily supply |
| `opening_mature_inventory_kg` | Decimal kg | yes | Task 9 state |
| `available_mature_quantity_kg` | Decimal kg | yes | opening + natural supply |
| `mature_inventory_loss_quantity_kg` | Decimal kg | yes | Task 9 loss authority |
| `harvestable_mature_quantity_kg` | Decimal kg | yes | available - loss |
| `effective_harvest_capacity_kg` | Decimal kg/day | yes | fixed-factory Task 9 capacity |
| `model_harvested_marketable_quantity_kg` | Decimal kg | yes | Task 9 `harvested_quantity_kg` |
| `closing_mature_inventory_kg` | Decimal kg | yes | Task 9 closing state |
| `unharvested_backlog_kg` | Decimal kg | yes | remaining unharvested state |
| `sorting_retention_rate` | Decimal ratio | yes | explicit retention policy |
| `postharvest_retention_rate` | Decimal ratio | yes | explicit retention policy |
| `effective_marketable_quantity_kg` | Decimal kg | yes | frozen V0.1 main curve |
| `task8_forecast_run_id` | identity | yes | Task 8 authority reference |
| `task9_harvest_state_run_id` | identity | yes | Task 9 authority reference |
| `task8_artifact_hash` | SHA-256 | yes | Task 8 artifact |
| `task9_result_hash` | SHA-256 | yes | Task 9 output |
| `marketable_policy_version` | string | yes | retention policy version |
| `marketable_policy_hash` | SHA-256 | yes | retention policy identity |
| `row_hash` | SHA-256 | yes | deterministic row payload hash |

The legacy names `arrival_quantity_kg`, `final_corrected_arrival_quantity_kg`
and `actual_harvest_quantity_kg` are not renamed into the V0.1 effective
marketable field.

## Peak metrics

The single-day peak is calculated independently for each quantile:

```text
single_day_peak[q] = max(effective_marketable_quantity_kg[q])
```

Equal maxima select the earliest date.

The primary sustained peak is a strict rolling seven-calendar-day cumulative
metric:

```text
sustained_7day_peak_cumulative_kg[q]
  = max(sum(effective_marketable_quantity_kg[q] for seven complete dates))
```

The window is exactly seven consecutive calendar days, with
`end_date = start_date + 6 days`. Ties select the earliest start date. The
daily average is only a derived display value and never replaces the cumulative
primary metric:

```text
daily_average_kg_per_day = cumulative_quantity_kg / Decimal("7")
scale=6
rounding=ROUND_HALF_EVEN
```

A range shorter than seven complete calendar dates produces
`NO_COMPLETE_7DAY_WINDOW`; edge fragments do not form a window.

The existing three-day metric remains a legacy compatibility field:

```text
sustained_3day_peak=LEGACY_COMPATIBILITY
```

S1 does not rename, delete, reimplement or alter its existing units or hash.
Season cumulative output is the sum of every daily effective marketable value
for the selected quantile.

## Fixture replay boundary

`v0_1_complete_season_case_01` is a deterministic, synthetic contract fixture.
It contains 90 complete dates, two subfarms, two varieties, one logical
destination factory and P50/P80/P90 rows. It includes maturity rise and peak,
a capacity dip with backlog, recovery and release, non-zero loss, an explicit
zero, a retention rate below one, two equal seven-day windows, and a single
parameter rerun input. The contract test independently recomputes conservation,
retention, seven-day windows and checksums; it does not call an S2-S5 adapter.

No production data, API, CLI, persistence implementation, migration, routing,
multi-factory allocation, peak-shaving rule, frontend or model change is part
of V0.1-S1.
