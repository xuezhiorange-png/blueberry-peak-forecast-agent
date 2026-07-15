# Complete-Season Fixture Contract

## Identity and date matrix

| Item | Frozen value |
| --- | --- |
| `fixture_id` | `v0_1_complete_season_case_01` |
| season | `2026-DEMO` |
| forecast range | `2026-03-01` through `2026-05-29` |
| calendar days | 90, inclusive and gap-free |
| farm | synthetic `farm_id=101` |
| subfarms | synthetic `1101`, `1102` |
| varieties | synthetic `2101`, `2102` |
| destination factories | one logical `9101` |
| quantiles | `P50`, `P80`, `P90` |
| primary date | `HARVEST_BUSINESS_DATE` |

The fixture uses names such as `fixture-farm-alpha` only as non-sensitive test
identities. It contains no real farm, worker, customer or production record.

## File schema

- `manifest.json` declares the fixture identity, range, scope cardinalities,
  file set, canonicalization and row ordering.
- `input.json` contains season/master data, production-plan inputs, Task 8 and
  Task 9 authority references, four explicit retention-policy rows and 1,080
  Task 9-shaped daily input rows.
- `expected_daily.json` contains 90 dates x 4 scope rows x 3 quantiles = 1,080
  deterministic output rows.
- `expected_metrics.json` contains per-quantile single-day, seven-day and
  season-cumulative metrics plus event and tie-break evidence.
- `rerun_input.json` changes only `labor_availability_ratio` during the
  capacity-dip dates and records the expected affected outputs.
- `checksums.json` hashes the canonical JSON value of every file except itself.

## Input field matrix

| Group | Fields | Unit/type | Nullability | Source/version/hash |
| --- | --- | --- | --- | --- |
| plan | `planting_area_mu`, `expected_yield_kg_per_mu`, `marketable_rate`, `expected_total_marketable_kg` | Decimal strings | non-null in fixture | synthetic plan / `fixture-plan-v1` / SHA-256 |
| plan | `tree_age_years` | Decimal string | non-null in fixture | synthetic plan |
| plan | phenology/effective dates | ISO dates | effective dates non-null | synthetic plan |
| Task 8 | run, model, artifact and config identities | identity/hash strings | non-null | existing Task 8 service contract / fixture authority |
| Task 9 | run/result identity | identity/hash strings | non-null | existing Task 9 service contract / fixture authority |
| retention | sorting/post-harvest rates | Decimal strings in `[0,1]` | non-null | explicit per season/farm/subfarm/variety row |
| daily input | supply, inventory, loss, capacity, harvest and closing fields | Decimal strings in kg | non-null | Task 8/Task 9 fixture authority |
| daily input | labor, operational and weather ratios | Decimal strings in `[0,1]` | non-null | Task 9 parameter references |
| daily input | `destination_factory_id` | identity | non-null | one fixed logical destination |

No field stores a binary float. `marketable_rate` is retained as a Task 8
production-plan input and is intentionally absent from expected daily rows.
It is not applied a second time after Task 9 harvested marketable quantity.

## Expected output matrix

Each output row contains every field in the V0.1 daily row contract:
`date`, `forecast_quantile`, `farm_id`, `subfarm_id`, `variety_id`,
`natural_maturity_supply_kg`, `opening_mature_inventory_kg`,
`available_mature_quantity_kg`, `mature_inventory_loss_quantity_kg`,
`harvestable_mature_quantity_kg`, `effective_harvest_capacity_kg`,
`model_harvested_marketable_quantity_kg`, `closing_mature_inventory_kg`,
`unharvested_backlog_kg`, `sorting_retention_rate`,
`postharvest_retention_rate`, `effective_marketable_quantity_kg`, the Task 8
and Task 9 authority identities/hashes, marketable policy version/hash and
`row_hash`.

Rows sort by `date ASC`, `farm_id ASC`, `subfarm_id ASC`, `variety_id ASC` and
quantile order `P50`, `P80`, `P90`. Scope fields are always explicit.

## Event schedule

| Event | Dates | Expected evidence |
| --- | --- | --- |
| explicit zero and maturity rise | 2026-03-01; 2026-03-02 to 2026-03-10 | zero harvest followed by increasing supply/harvest |
| natural maturity peak | 2026-03-25 | highest natural maturity supply |
| first seven-day peak window | 2026-03-15 to 2026-03-21 | complete rolling cumulative window |
| second tied seven-day window | 2026-04-05 to 2026-04-11 | same cumulative quantity as first window |
| capacity dip/backlog build | 2026-04-18 to 2026-04-22 | labor ratio `0.200000`, lower capacity, non-zero closing backlog |
| capacity recovery/backlog release | 2026-04-23 to 2026-04-29 | labor ratio returns to `1.000000`, harvest releases inventory |
| non-zero mature loss | 2026-03-25 through 2026-05-29 | loss field is positive |
| incomplete tail policy | any range shorter than seven dates | `NO_COMPLETE_7DAY_WINDOW` by contract |

## Metric and invariant contract

For every scope and quantile:

```text
opening_mature_inventory_kg + natural_maturity_supply_kg
  = mature_inventory_loss_quantity_kg
  + model_harvested_marketable_quantity_kg
  + closing_mature_inventory_kg

available_mature_quantity_kg
  = opening_mature_inventory_kg + natural_maturity_supply_kg

effective_marketable_quantity_kg
  = model_harvested_marketable_quantity_kg
  * sorting_retention_rate
  * postharvest_retention_rate
```

The test computes seven-day windows from daily rows, not from the expected
metric file. For example, P50's first and second windows are both explicitly
shown as seven daily values in `expected_metrics.json` and each is manually
summed to `585.465120` kg. The first start date wins.

The season metric is the sum of all daily effective marketable quantities for
each quantile. Single-day ties use the earliest date. No arrival/receipt field
is substituted for the harvest-business-date curve.

## Rerun scenario

`rerun_input.json` changes exactly one input parameter,
`labor_availability_ratio`, from `0.200000` to `0.800000` during the five
capacity-dip dates. The scenario must change effective capacity and downstream
inventory while preserving Task 8 authority and the retention policy. S1
records the scenario and its expected dependency boundary; it does not execute
an S2-S5 production recalculation.

## Acceptance checks

The fixture-only test verifies:

1. exactly 90 gap-free dates and the frozen scope cardinalities;
2. deterministic row order and P50/P80/P90 coverage;
3. Decimal-string quantities/rates, non-negative values and finite inputs;
4. unique scope/date/quantile keys and 89 cross-day inventory transitions for
   each of the 12 series;
5. all frozen Task 9 daily state relations and both conservation equations;
6. the no-double-`marketable_rate` rule;
7. independent strict-calendar seven-day cumulative windows and earliest-start
   tie-break;
8. independent SHA-256 row-hash recomputation for all 1,080 rows, including
   one-field tamper detection and exclusion of `row_hash` from its own preimage;
9. six-place `ROUND_HALF_EVEN` seven-day averages for every quantile;
10. season cumulative sums and explicit event evidence;
11. canonical checksums for all fixture files;
12. the one-parameter rerun boundary.

The test is a contract test only. It does not claim V0.1 production E2E.
