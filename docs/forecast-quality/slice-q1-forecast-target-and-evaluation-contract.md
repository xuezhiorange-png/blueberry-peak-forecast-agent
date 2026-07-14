# Slice Q1 — Forecast Target and Evaluation Contract

| Field | Value |
|---|---|
| Document ID | `slice-q1-forecast-target-and-evaluation-contract` |
| Document version | v1.1 (Q1 P0 fixup per review 4694771522) |
| Document status | `DRAFT — Q1 P0 fixup applied, awaiting Charles re-review` |
| Tracking Issue | `#102` (OPEN) — `[P0 Epic] Blueberry forecast quality validation and historical backtest loop` |
| Q1 authorization comment | `IC_kwDOS_gTTs8AAAABKDOkiQ` (id `4969440393`) on Issue #102 |
| Q1 P0 fixup review | `4694771522` (verdict `PR103_SLICE_Q1_REVIEW_P0_FIXUP_REQUIRED`) |
| Working base | `origin/main` at `2e860511dd9279d0aa3c64dd760bea8531fad458` |
| Working branch | `docs/issue-102-slice-q1-forecast-evaluation-contract` |
| Working worktree | `/tmp/issue-102-slice-q1-forecast-evaluation-contract` |
| Companion documents | `docs/forecast-quality/slice-q1-data-coverage-audit.md`; `docs/forecast-quality/slice-q1-decision-table.md` |
| Q1 implementation | NOT AUTHORIZED in this document |
| Q2 design authorization | NOT AUTHORIZED in this document |
| Q2 implementation authorization | NOT AUTHORIZED in this document |
| Q3 / Q4 / Q5 / Q6 / Q7 | NOT AUTHORIZED in this document |
| Model change | NOT AUTHORIZED in this document |
| Backtest runner implementation | NOT AUTHORIZED in this document |
| Sustained 7-day peak production implementation | NOT AUTHORIZED in this document |
| 3-day production field reinterpretation | NOT AUTHORIZED in this document |
| Naive baseline implementation | NOT AUTHORIZED in this document |
| Ready / merge / Issue closure | NOT AUTHORIZED in this document |
| TASK-013 C2 resumption | NOT AUTHORIZED in this document |

> Q1 is a **design, source-definition, and data-inventory round only**. Q1 does not modify any production code, any test, any Golden, any migration, any schema, any model, any parameter inference, or any persistence path. Q1 is a docs-only round. v1.1 (this document) applies the P0 fixup requested in review `4694771522`. v1.1 does not introduce any new mutation; v1.1 only corrects design-level errors identified by the review.

---

## §1 Scope and non-scope

### §1.1 In scope

Q1 freezes:

1. the primary forecast target and the distinction among eight physical quantities (`natural_maturity_quantity`, `mature_inventory_quantity`, `harvestable_quantity`, `actual_harvest_quantity`, `unharvested_backlog_quantity`, `arrival_quantity`, `final_corrected_arrival_quantity`, `season_cumulative_quantity`);
2. the **dual time-cutoff model** for forecast quality evaluation: `forecast_cutoff_at` (gates model inputs) and `label_observation_cutoff_at` (gates which actual-label revisions are visible when scoring);
3. the canonical actual-label contract, including grain, unit, event date semantics, recorded-at, revised-at, point-in-time visibility, duplicate handling, missing-day handling, late-revision handling, zero-day handling, and `label_observation_cutoff_at`-based revision resolution;
4. the evaluation grain;
5. the full metric contract: daily, cumulative, single-day peak, sustained 7-day peak, quantile calibration, interval width, pinball loss, with explicit signed/absolute relative-error separation;
6. the sustained 7-day peak contract and the migration boundary from the existing 3-day production contract (additive coexistence, no silent 3-day-to-7-day reinterpretation);
7. a reproducible, aggregate-only data-coverage report (with truthful `NOT_VERIFIED` reporting when a reachable database has no data).

### §1.2 Out of scope (explicit exclusions)

Q1 does NOT authorize and does NOT produce:

1. Any modification of `backend/app/**` production code.
2. Any modification of `backend/tests/**` or `backend/tests/integration/**`.
3. Any modification of `backend/alembic/**` or any new migration.
4. Any HTTP API endpoint, CLI command, frontend widget, Golden file, or fixture.
5. Any LLM call, prompt, or free-form natural-language generation.
6. Any model change, parameter inference change, residual correction change, maturity curve change, weather adjustment change, or harvest-state equation change.
7. Any TASK-008 / TASK-009 / TASK-010 numerical semantic change.
8. Any production backtest runner, point-in-time backtest runner, or model-vs-baseline comparison runner.
9. Any sustained 7-day peak production implementation, even as an additive field.
10. Any naive baseline implementation.
11. Any silent reinterpretation of the 3-day production field as a 7-day field.
12. Any change to the existing 3-day production field semantics, including its name, its default, its units, its hash, or its Golden value.
13. Any TASK-013 C2 resumption.
14. Any closure of Issue #99 or Issue #102.
15. Any Ready, merge, or auto-merge on any Draft PR.
16. Any deletion of any branch, worktree, or untracked file.
17. Any output of sensitive real business data (farm names, subfarm names, variety names that are not in the public `dim_variety` table, operator names, exact daily quantities, exact forecast outputs, exact row counts on real data).

### §1.3 Companion documents

- `docs/forecast-quality/slice-q1-forecast-target-and-evaluation-contract.md` — this document (target, label, dual-cutoff, metric, peak contract).
- `docs/forecast-quality/slice-q1-data-coverage-audit.md` — the data-coverage audit and 3-day production contract inventory.
- `docs/forecast-quality/slice-q1-decision-table.md` — the explicit decision table required by §12 of the round instruction.

The three documents are mutually consistent and cross-referenced. The decision table is the canonical state summary; the contract and audit documents are the supporting detail.

---

## §2 Project priority context

```
P0 = FORECAST_ACCURACY_AND_HISTORICAL_BACKTEST
P1 = THIN_FORECAST_TRIAL_ENTRY
P2 = DETERMINISTIC_FORECAST_EXPLANATION
P3 = OPERATIONAL_RECOMMENDATIONS
TASK013_SLICE_C_C2 = PAUSED
```

The current P0 mainline is the validation of forecast accuracy and the establishment of a historical backtest loop. PR #101 has been closed without merge; Issue #102 has been opened as the P0 Epic; Issue #99 has received a project-priority-reset comment (id `4969389577`).

Q1 is the first slice in the suggested implementation order Q1..Q7 of Issue #102. Q1 is a design and data-inventory slice. Q1 does not implement any backtest runner; that is Q2 (which itself is decomposed into Q2A and Q2B per the v1.1 fixup).

---

## §3 Business core question (frozen)

> Given a farm, a subfarm-or-plot, a variety, a planting area, a forecast season, and a forecast cutoff time, the system must reliably answer:
> - how many kilograms of blueberry can be picked each day in the future;
> - on which date the single-day peak occurs;
> - which future continuous 7-day window has the largest cumulative pick;
> - how large the sustained 7-day cumulative pick is;
> - what the current forecast error is;
> - whether a new model is genuinely more accurate than the previous one.

The Q1 design-freeze answers the design-level question of **what physical quantity** the system is actually answering this core question for, **at what time the answer is generated**, and **at what later time the answer is scored**. Q1 also freezes the **actual-label** against which the answer is validated, and the **two independent time cutoffs** that gate model input visibility and label visibility respectively.

### §3.1 Hard exclusion of proxy-conflation

The system MUST NOT silently treat any of the following as a synonym for "actual harvest":

- `natural_maturity_quantity_kg` (model output of natural maturation);
- `closing_mature_inventory_kg` (model state);
- `unharvested_backlog_kg` (model state);
- `arrival_quantity_kg` (model output of arrival before weather correction);
- `final_corrected_arrival_quantity_kg` (model output of arrival after weather correction);
- `harvested_quantity_kg` on `ForecastDailyRow` (model output, not a user-entered actual);
- any `fact_receipt_daily.weight_kg` (operator-entered receipt / arrival at the factory, not the pick at the orchard).

If the system uses a proxy as a stand-in for the actual label, the proxy MUST be marked as such, and the Q1 design-freeze classifies each candidate below.

### §3.2 Hard exclusion of dual-cutoff conflation

The system MUST NOT use a single time cutoff for both model input visibility and actual-label visibility for scoring. The two time cutoffs are independent; they are defined separately in §4. The single-cutoff conflation would make the backtest structurally unable to score future forecasts (the future target date has not yet occurred at the forecast cutoff). Q1 freezes the two-cutoff model as the only correct anti-leakage boundary.

---

## §4 Dual time-cutoff model (frozen per review 4694771522 P0-1)

### §4.1 `forecast_cutoff_at` (frozen)

```
forecast_cutoff_at = the latest information time the model is permitted to see
                       when generating a historical forecast
```

The model input visibility boundary. It constrains:

- training data;
- feature data;
- parameters;
- weather forecast;
- weather observation;
- management events;
- maturity observations;
- Task 8–12 authorities;
- model artifacts;
- data snapshots;
- upstream revisions;
- every model input.

Hard rule:

```
for every model input row r:
    r.MODEL_INPUT_AVAILABLE_AT <= forecast_cutoff_at
```

The actual label MUST NOT enter the model input by any path. Specifically:

- `actual_harvest_quantity` records whose `recorded_at` is after `forecast_cutoff_at` MUST NOT be readable as a feature.
- The model implementation MUST NOT query a `latest` / `current` / `most_recent` actual row to fill in a feature. The only valid path is the persisted, time-bound authority at `MODEL_INPUT_AVAILABLE_AT <= forecast_cutoff_at`.

### §4.2 `label_observation_cutoff_at` (frozen, new in v1.1)

```
label_observation_cutoff_at = the latest actual-label revision time
                                the evaluator is permitted to see
                                when scoring a historical forecast
```

The label visibility boundary for evaluation. It is independent of `forecast_cutoff_at`. The actual label is allowed to be:

- recorded after the forecast cutoff;
- entered on or after the target date;
- revised after the forecast cutoff;
- finalized after the forecast cutoff.

The actual label is only usable for scoring if its revision is visible at `label_observation_cutoff_at`.

### §4.3 Canonical relationship (frozen)

For a future forecast, the canonical time order is:

```
forecast_cutoff_at < forecast_target_date_end <= label_observation_cutoff_at
```

For a same-day forecast, the canonical time order is:

```
forecast_cutoff_at < label_observation_cutoff_at (typically forecast_target_date = forecast_cutoff_at)
```

For a historical replay, the relationship is:

```
forecast_target_date < forecast_cutoff_at (in-simulation)
   < label_observation_cutoff_at (the replay evaluation timestamp)
```

For a final adjudicated evaluation, the relationship is:

```
forecast_target_date <<< label_observation_cutoff_at (any finalization timestamp)
```

Q1 freezes the four time-pattern templates; Q1 does not require that every report uses the same template.

### §4.4 Two evaluation modes (frozen)

Q1 freezes the following two evaluation-label modes. Every report MUST declare which mode it uses.

#### §4.4.1 `AS_OF_EVALUATION`

```
evaluation_label_mode = AS_OF_EVALUATION
```

Visibility:

```
recorded_at <= label_observation_cutoff_at
revision visible at label_observation_cutoff_at
```

Use cases:

- reproduce a specific historical report;
- prevent later corrections from rewriting earlier scores;
- compare a model change against a fixed label snapshot.

#### §4.4.2 `FINAL_ADJUDICATED`

```
evaluation_label_mode = FINAL_ADJUDICATED
```

The label is the final, business-adjudicated actual. The report MUST record:

- `finalized_at` — the timestamp at which the label was finalized;
- `label_snapshot_hash` — the SHA-256 of the canonical JSON of the adjudicated label set;
- `adjudication_policy_version` — the version of the business adjudication rule.

Use cases:

- end-of-season model quality report;
- formal precision comparison between models.

Hard rule: the `FINAL_ADJUDICATED` label MUST NOT be used as a model input at any forecast cutoff. The dual-cutoff separation forbids feeding the adjudicated label back into the model.

### §4.5 Revision resolution (frozen per review 4694771522 P0-1 / P1-1)

The valid revision at `label_observation_cutoff_at` is:

```
winner = the valid revision visible at label_observation_cutoff_at
         according to explicit supersession lineage
```

The explicit supersession lineage is:

- each label row has `recorded_at` and `effective_at`;
- each label row has `supersedes_record_id` if it is a revision;
- the revision is valid for `recorded_at <= label_observation_cutoff_at`;
- among multiple valid revisions, the one with the latest `recorded_at` wins;
- among multiple valid revisions with the same `recorded_at`, the one with the higher `revision_number` wins;
- the chosen revision must not be `is_deleted_or_voided = true` at `label_observation_cutoff_at`.

Forbidden rules:

```
latest timestamp always wins  (forbidden)
largest revision number always wins  (forbidden unless same source family)
current/latest row fallback  (forbidden)
```

`recorded_at` and `revision_number` are explicit supersession-lineage properties; they are not auto-promoted to authority. A later `recorded_at` does NOT win unless it is part of an explicit supersession lineage.

### §4.6 What the dual-cutoff model forbids

Q1 forbids:

- using `forecast_cutoff_at` as the label visibility boundary (the model could never score a future forecast);
- using `label_observation_cutoff_at` as the model input boundary (the model would leak the actual label);
- conflating training-feature visibility and label visibility;
- scoring with `latest` / `current` / `most_recent` actual row;
- using a final adjudicated label as a model input.

Q1 permits:

- the actual label being recorded after the forecast cutoff;
- the actual label being revised after the forecast cutoff;
- the actual label being entered on a future target date;
- the actual label being visible to the evaluator at a later `label_observation_cutoff_at`.

This is the only correct anti-leakage boundary.

---

## §5 Forecast-object contracts

### §5.1 Eight physical quantities (canonical)

For each `(farm, subfarm_or_plot, variety, season, calendar_date)`, the project distinguishes the following eight physical quantities. Each row below is the frozen Q1 contract; no row is interpreted, computed, or persisted outside this contract.

| # | object_name | business_definition | physical_meaning | unit | grain | event_date_semantics | source_task | schema_path | persistence_table | current_production_status | actual_or_forecast | proxy_or_direct_observation | can_be_primary_label | can_be_feature | point_in_time_visibility | known_limitations |
|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `natural_maturity_quantity` | The model-predicted daily natural maturation of blueberry on the orchard, in the absence of weather and harvest-state effects. | A biological-physical quantity produced by the TASK-008 maturity model. It is not a human-observed quantity. | kg | (farm × subfarm × variety × calendar_date) | the calendar date on which maturation occurs | TASK-008 | `backend/app/agent/schemas.py::ForecastDailyRow.natural_maturity_quantity_kg: DailyQuantiles` | n/a (forecast output) | `RESOLVED_BY_MERGED_AUTHORITY` for schema; `NOT_VERIFIED` for production use in Q1 scope | forecast | `MODEL_OUTPUT` | NO | YES | n/a (forecast) | not a label; do not use for backtest |
| 2 | `mature_inventory_quantity` | The model-predicted closing mature inventory on a calendar date, after natural maturation and harvest-state update. | A derived state. | kg | same as #1 | the calendar date on which the closing inventory is reported | TASK-008 / TASK-009 | `ForecastDailyRow.closing_mature_inventory_kg: DailyQuantiles` | n/a (forecast output) | same as #1 | forecast | `DERIVED_STATE` | NO | YES (as feature) | n/a (forecast) | derived; cannot be a label |
| 3 | `harvestable_quantity` | The model-predicted daily harvestable quantity (the portion of mature inventory that is operationally ready to be picked). | Currently NOT a first-class schema field in `origin/main`. Q1 explicitly marks this object as `NOT_CURRENTLY_AVAILABLE` as a first-class field. Q1 forbids any formula derivation (in particular, `harvestable_quantity = harvested_quantity - unharvested_backlog` is `FORMULA_NOT_AUTHORIZED` because `harvested_quantity` is a flow and `unharvested_backlog` is a stock, and the two physical dimensions do not justify direct subtraction). | kg (target unit) | same as #1 | the calendar date | n/a | **NOT in `origin/main` schema** | none | `NOT_CURRENTLY_AVAILABLE` / `FORMULA_NOT_AUTHORIZED` | n/a | n/a (no field, no formula) | NO | n/a | n/a | Q2 must add a first-class `harvestable_quantity_kg` field with explicit physical authority, or leave the object as `NOT_CURRENTLY_AVAILABLE` indefinitely |
| 4 | `actual_harvest_quantity` | The user-entered or operator-entered daily quantity of blueberry actually picked at the orchard. This is the primary business target for Q1. | A direct observation. The most reliable source today is `fact_receipt_daily.weight_kg` interpreted as **arrival at the factory**, not pick at the orchard. There is **no first-class `actual_harvest_quantity` table in `origin/main`**. | kg (target unit) | (farm × subfarm × variety × season × harvest_date) | the calendar date on which the pick occurred | n/a (no dedicated table) | **NOT in `origin/main` schema** | `fact_receipt_daily` is the closest first-class fact but it stores **arrival**, not pick. | `SCHEMA_GAP` / `SOURCE_GAP` | actual (intended) | `DIRECT_OBSERVATION` (when a dedicated table exists) / currently **no first-class table** | YES (intended primary label) | NO (label, not feature) | `POINT_IN_TIME_GAP` (current `fact_receipt_daily` lacks `recorded_at`, `effective_at`, `revised_at`) | Q2A must add a dedicated `actual_harvest_daily` table, or accept `fact_receipt_daily` as a `PROXY_LABEL` with explicit disclosure |
| 5 | `unharvested_backlog_quantity` | The model-predicted daily unharvested backlog. | A derived state. | kg | same as #1 | the calendar date | TASK-008 / TASK-009 | `ForecastDailyRow.unharvested_backlog_kg: DailyQuantiles` | n/a (forecast output) | same as #1 | forecast | `DERIVED_STATE` | NO | YES (as feature) | n/a (forecast) | derived; cannot be a label |
| 6 | `arrival_quantity` | The model-predicted daily quantity arriving at the factory gate, before weather correction. | A model output. | kg | (factory × variety × calendar_date) | the calendar date of arrival at the factory gate | TASK-008 / TASK-009 | `ForecastDailyRow.arrival_quantity_kg: DailyQuantiles` | n/a (forecast output) | same as #1 | forecast | `MODEL_OUTPUT` (proxy for actual arrival, not for actual harvest) | NO | YES (as feature) | n/a (forecast) | proxy for arrival; not a harvest label |
| 7 | `final_corrected_arrival_quantity` | The model-predicted daily quantity arriving at the factory gate, after weather correction. | A model output. | kg | same as #6 | the calendar date | TASK-009 | `ForecastDailyRow.final_corrected_arrival_quantity_kg: DailyQuantiles` | n/a (forecast output) | same as #1 | forecast | `MODEL_OUTPUT` (proxy for actual arrival, not for actual harvest) | NO | YES (as feature) | n/a (forecast) | corrected proxy; not a harvest label |
| 8 | `season_cumulative_quantity` | The model-predicted or actual cumulative quantity from the season start through the calendar date. | A derived aggregate. | kg | (farm × subfarm × variety × season × calendar_date) | the calendar date through which the cumulative is computed | TASK-008 / TASK-009 (forecast); operator (actual) | **NOT in `origin/main` schema as a first-class field** | none | `NOT_CURRENTLY_AVAILABLE` as a first-class schema field | both | `DERIVED_STATE` (cumulative over daily rows) | YES (actual cumulative is the canonical label for cumulative metrics) | YES (forecast cumulative) | depends on daily row visibility | Q2A must define the season-cumulative schema field |

### §5.2 First-class vs derived

The eight quantities are split into two groups:

- **First-class schema fields on `ForecastDailyRow`**: #1, #2, #5, #6, #7. These are persisted fields of the model output. The Q1 design-freeze treats them as `RESOLVED_BY_MERGED_AUTHORITY` for schema. Their use as features in a backtest is permitted; their use as the actual-harvest label is forbidden.
- **Not first-class in `origin/main`**: #3, #4, #8. `harvestable_quantity` and `actual_harvest_quantity` and `season_cumulative_quantity` are not first-class fields today. Q1 marks them as `NOT_CURRENTLY_AVAILABLE` and proposes Q2A / Q3 design work to define them.

### §5.3 The ForecastDailyRow field count (corrected per review 4694771522 P0-2)

`ForecastDailyRow` contains exactly **six `DailyQuantiles` quantity fields**:

```
natural_maturity_quantity_kg: DailyQuantiles
harvested_quantity_kg: DailyQuantiles
closing_mature_inventory_kg: DailyQuantiles
unharvested_backlog_kg: DailyQuantiles
arrival_quantity_kg: DailyQuantiles
final_corrected_arrival_quantity_kg: DailyQuantiles
```

`per_variety_contribution: list[VarietyContribution]` is a nested contribution list, NOT a seventh `DailyQuantiles` quantity field. The Q1 v1 mistakenly reported "seven quantity fields"; v1.1 corrects this to six.

The ForecastDailyRow also carries:

- `date: date`
- `weather_tags: tuple[str, ...]`
- `spring_festival_phase: SpringFestivalPhase`
- `agent_daily_row_hash: SHA256Hex`

These are not quantity fields; they are metadata.

### §5.4 The ForecastDailyRow grain (corrected per review 4694771522 P0-2)

`ForecastDailyRow` is a **downstream aggregate** of one resolved agent request. It does NOT carry first-class `farm_id`, `subfarm_id`, `variety_id`, or `season_id` columns. The Q1 v1 mistakenly described the row as `(farm × subfarm × variety × calendar_date)`. v1.1 corrects this.

The real grain of `ForecastDailyRow` is:

```
CURRENT_OUTPUT_GRAIN = (one resolved agent request, one resolved location, one resolved season) × calendar_date
                       with nested per_variety_contribution carrying per-variety identity
```

Where:

- `farm` / `subfarm` / `location` identity is carried by `NormalizedAgentRequest.normalized_location` and the upstream resolved-location authority.
- `season` identity is carried by the resolved forecast-season identity (per `task-013-persisted-forecast-season-identity-design-amendment.md`).
- `variety` identity is carried by the request's `variety` list and the nested `per_variety_contribution: list[VarietyContribution]`.
- `Task 9 HarvestStateDailyMemberRowModel` carries first-class `farm_id` / `subfarm_id` / `variety_id` (member-grain); the `Agent ForecastDailyRow` is a downstream aggregate over the member rows.

The Q1 design-freeze names this as:

```
DESIRED_ACTUAL_LABEL_GRAIN = (farm_id, subfarm_or_plot_id, variety_id, season_id, harvest_date)
```

The gap between the two grains is:

```
TARGET_GRAIN_ALIGNMENT = NOT_ALIGNED
```

The grain reconciliation is a Q2A design and implementation task.

### §5.5 Physical quantity alignment (separate from grain alignment)

The gap between the current model output's physical quantity (`harvested_quantity_kg` is a model output) and the primary business target (`actual_harvest_quantity` is a direct observation) is:

```
TARGET_PHYSICAL_QUANTITY_ALIGNMENT = NOT_PROVEN_EQUIVALENT
```

The grain alignment (`TARGET_GRAIN_ALIGNMENT = NOT_ALIGNED`) and the physical-quantity alignment (`TARGET_PHYSICAL_QUANTITY_ALIGNMENT = NOT_PROVEN_EQUIVALENT`) are independent. Either or both can be unresolved.

### §5.6 Forbidden proxy-formula for `harvestable_quantity`

Q1 explicitly forbids any formula of the form:

```
harvestable_quantity := harvested_quantity - unharvested_backlog
```

This formula is forbidden because:

- `harvested_quantity` is a daily flow (kg picked today);
- `unharvested_backlog` is a daily closing stock (kg of mature berries still on the plant at end of day);
- the two have different physical dimensions even though both are expressed in kg;
- direct subtraction has no business or model authority;
- the result can be negative or nonsensical.

`harvestable_quantity` remains `NOT_CURRENTLY_AVAILABLE` and `FORMULA_NOT_AUTHORIZED` until a first-class `harvestable_quantity_kg` field is added by Q2A with explicit physical authority.

### §5.7 Proxy discipline

Q1 forbids any silent reclassification of a model output as an actual observation. If the project uses `fact_receipt_daily.weight_kg` as a stand-in for the actual harvest label, the design MUST mark it as `PROXY_LABEL` and disclose the proxy in every report that uses it. Q1 does not yet adopt this proxy; the adoption decision is a Q2A design question, and the actual-label gap is reported in §6.

### §5.8 The actual-arrival label candidate

`fact_receipt_daily.weight_kg` is the only first-class operator-entered daily fact in `origin/main`. It is bound to a build-run identity and a unique constraint `(build_run_id, season_id, factory_id, receipt_date, farm_key, subfarm_key, variety_id)`, with `CheckConstraint("weight_kg > 0")`. The CHECK excludes zero-receipt days; this means the table cannot directly represent an explicit zero-receipt day (an explicit zero would be a missing row, not a zero row). This structural fact must be reported in the data-coverage audit and is a Q2A design input.

---

## §6 Actual-label contract

### §6.1 Canonical grain (target)

```
DESIRED_ACTUAL_LABEL_GRAIN = (farm_id, subfarm_or_plot_id, variety_id, season_id, harvest_date)
```

The actual-harvest label, when adopted, will be defined at this grain.

### §6.2 Supported grain (audit result on `origin/main`)

The closest first-class operator-entered fact today is `fact_receipt_daily` with grain:

```
SUPPORTED_GRAIN = (build_run_id, season_id, factory_id, receipt_date, farm_key, subfarm_key, variety_id)
```

The supported grain is at the receipt / factory level, not at the orchard / subfarm level. `farm_key` and `subfarm_key` are recorded as values, but `weight_kg > 0` is enforced by CHECK, so explicit zero-receipt days are structurally excluded. There is no dedicated `actual_harvest_daily` table. There is no `subfarm_or_plot_id` table in the public dim set; the closest is `dim_subfarm` and `dim_farm`.

```
SUPPORTED_GRAIN = (build_run_id, season_id, factory_id, receipt_date, farm_key, subfarm_key, variety_id, weight_kg > 0)
DESIRED_GRAIN  = (farm_id, subfarm_or_plot_id, variety_id, forecast_season_id, harvest_date, actual_harvest_quantity_kg)
GRAIN_GAP       = YES (no dedicated actual_harvest_daily table; fact_receipt_daily is receipt not pick; explicit zero missing; subfarm_or_plot_id not a column)
```

### §6.3 Canonical fields (target)

The actual-harvest label row, when adopted, will contain the following fields. The fields are frozen by Q1. Q1 does NOT add a table or migration; Q1 freezes the contract only.

| Field | Type | Meaning | Frozen status |
|---|---|---|---|
| `actual_harvest_record_id` | primary key, opaque | row identity | `FROZEN` (contract only) |
| `farm_id` | FK to `dim_farm.id` | farm identity | `FROZEN` (contract only) |
| `subfarm_or_plot_id` | FK to `dim_subfarm.id` | subfarm or plot identity | `FROZEN` (contract only) |
| `variety_id` | FK to `dim_variety.id` | variety identity | `FROZEN` (contract only) |
| `forecast_season_id` | FK to `dim_season.id` | season identity | `FROZEN` (contract only; matches `task-013-persisted-forecast-season-identity-design-amendment.md` §2.1) |
| `harvest_date` | `date` | the calendar date on which the pick occurred | `FROZEN` (contract only) |
| `actual_harvest_quantity_kg` | `Numeric(18, 3)` | the picked quantity in kilograms | `FROZEN` (contract only) |
| `source_system` | non-empty `str` | which operator system recorded the row | `FROZEN` (contract only) |
| `source_record_id` | non-empty `str` | the source system's record id | `FROZEN` (contract only) |
| `recorded_at` | `datetime` (tz-aware) | when the row was first recorded | `FROZEN` (contract only) |
| `effective_at` | `datetime` (tz-aware) | the earliest forecast-cutoff at which the row is visible | `FROZEN` (contract only) |
| `revised_at` | `datetime` (tz-aware) | when the row was last revised (NULL if no revision) | `FROZEN` (contract only) |
| `revision_number` | non-negative `int` | revision counter, 0 for the first record | `FROZEN` (contract only) |
| `supersedes_record_id` | nullable FK to `actual_harvest_daily.actual_harvest_record_id` | the row this revises (NULL for the first record) | `FROZEN` (contract only) |
| `is_deleted_or_voided` | `bool` | whether the row is logically deleted | `FROZEN` (contract only) |
| `quality_status` | enum (`OK`, `SUSPECT`, `REJECTED`, `LATE_CORRECTION`) | data-quality flag | `FROZEN` (contract only) |
| `canonical_row_hash` | `sha256` | canonical row hash, computed over the canonical JSON of all other fields | `FROZEN` (contract only; `SHA256Hex` like other canonical-row hashes) |

### §6.4 Current actual-label status (audit result)

```
ACTUAL_LABEL_STATUS = SCHEMA_GAP / SOURCE_GAP / POINT_IN_TIME_GAP / REVISION_HISTORY_GAP
ACTUAL_LABEL_SUPPORTED_GRAIN = fact_receipt_daily at (build_run_id, season_id, factory_id, receipt_date, farm_key, subfarm_key, variety_id, weight_kg > 0) — receipt, not pick
```

Each gap is a separate blocker:

- `SCHEMA_GAP` — no `actual_harvest_daily` table.
- `SOURCE_GAP` — the only operator-entered daily fact is `fact_receipt_daily`, which is **receipt** at the factory, not **pick** at the orchard. The physical meaning is different.
- `POINT_IN_TIME_GAP` — `fact_receipt_daily` does not carry `recorded_at`, `effective_at`, `revised_at`, `revision_number`, or `supersedes_record_id`. The Q1 contract requires these fields to enforce point-in-time visibility.
- `REVISION_HISTORY_GAP` — `fact_receipt_daily` is bound to a `build_run_id`; the build-run sequence is the only revision mechanism. This is a re-build mechanism, not a row-level revision. Q2A design must decide whether to keep the build-run model or to introduce row-level revision.

### §6.5 Point-in-time visibility contract (corrected per review 4694771522 P0-1)

For a backtest at `label_observation_cutoff_at = T_label`, the actual-label query MUST return only rows that satisfy:

- `recorded_at <= T_label`
- the row is the valid revision visible at `T_label` per the explicit supersession lineage (§4.5)
- the row is not `is_deleted_or_voided`

The query MUST NOT return:

- rows with `recorded_at > T_label` (late-arriving records are visible to the evaluator at a later `T_label`, not before);
- the latest `supersedes` value (the `current_data` / `latest` / `most_recent` fallback is forbidden);
- post-cutoff corrections for an earlier `T_label`;
- post-cutoff management events;
- target-date-after data when `T_label < target_date_end` and the row was not yet entered.

The actual-label visibility contract is **independent of** the training-feature visibility contract (§4.1). The two contracts use two different time boundaries. The actual-label visibility uses `label_observation_cutoff_at`; the model input visibility uses `forecast_cutoff_at`.

The contract for the model input side is the same as the `replay_trained_filtering.py` rules for training data. The contract for the label side is the explicit supersession lineage at `label_observation_cutoff_at`.

### §6.6 Special-day semantics

| Concept | Definition | Distinguishing property |
|---|---|---|
| `late_arriving_record` | a row whose `recorded_at > harvest_date` | reported separately; never silently used as if `recorded_at = harvest_date`; visible to the evaluator at `T_label >= recorded_at` |
| `correction` | a row whose `supersedes_record_id` is non-null | a later revision of an earlier row; the earlier row remains valid for `T_label < correction.recorded_at` |
| `void` | a row whose `is_deleted_or_voided = true` | excluded from backtest, regardless of `T_label` |
| `duplicate` | two rows with the same canonical-grain identity and overlapping effective window | resolved by `revision_number` and `recorded_at`; never silently merged |
| `missing_day` | a calendar date for which no row exists in the supported grain | NOT a zero; reported separately as `missing` |
| `zero_harvest_day` | a calendar date for which a row exists with `actual_harvest_quantity_kg = 0` | a real observation; can be used in backtest |
| `plant_not_operating_day` | a calendar date for which the plant is closed (season boundary, holiday, operator note) | reported separately; the day is a planned non-operation, not a zero |
| `unknown_day` | a calendar date for which observation status is not resolvable | reported as `UNKNOWN`; not used in backtest without resolution |

`0` and `missing` are distinct semantics and MUST NOT be conflated. `0` is an observation; `missing` is an absence; `plant_not_operating` is a planned closure; `unknown` is an unresolved status.

### §6.7 Backtest usability gate

A series is `usable_backtest_series` if and only if all of the following hold:

- grain identity is complete (`farm_id`, `subfarm_or_plot_id`, `variety_id`, `season_id` are not null);
- date-continuity rule is explicit (every calendar date in the season is either observed or marked `missing` or `plant_not_operating`);
- actual label is not a proxy, or the proxy is explicitly accepted and disclosed;
- unit is consistent (kg throughout the series);
- no unresolved duplicate;
- point-in-time visibility is verifiable for the chosen `label_observation_cutoff_at`;
- the `forecast_cutoff_at` and the `label_observation_cutoff_at` are both bindable to a specific replay identity;
- at least one full 7-day target window is present (see §7 for the missing-window policy);
- the actual label and the forecast output are alignable at the same grain.

```
POINT_IN_TIME_STATUS = GAP (no first-class actual_harvest_daily table;
                            fact_receipt_daily lacks recorded_at, effective_at, revised_at;
                            re-build via build_run_id is the only revision mechanism,
                            but build_run_id is an analytics concept, not an
                            actual-harvest revision concept)
```

---

## §7 Sustained 7-day peak contract

### §7.1 Definition (frozen)

The sustained peak window is fixed to **7 consecutive calendar days**. For a forecast target object (one of the eight objects in §5) and a quantile `q ∈ {P50, P80, P90}`:

```
rolling_7day_cumulative_quantity_kg(q, start_date) =
    sum( daily_quantity_kg[q, start_date + offset]
         for offset in 0..6 )
```

```
sustained_7day_peak(q) =
    argmax( rolling_7day_cumulative_quantity_kg(q, start_date) )
```

Tie-break: `EARLIEST_START_DATE` (deterministic).

P50, P80, P90 are computed **independently** for each quantile. Cross-quantile mixing is forbidden.

### §7.2 Output fields (frozen)

For each quantile `q`, the sustained 7-day peak row contains:

| Field | Type | Meaning |
|---|---|---|
| `quantile` | `ForecastQuantile` | the quantile this row is for (`P50` / `P80` / `P90`) |
| `window_start_date` | `date` | the start of the 7-day window |
| `window_end_date` | `date` | `window_start_date + 6 calendar days` (computed, not stored) |
| `window_days` | `int == 7` | frozen constant |
| `cumulative_quantity_kg` | `Numeric(18, 3)` | the sum of the 7 daily values at quantile `q` |
| `rolling_daily_average_kg_per_day` | `Numeric(18, 3)` | `cumulative_quantity_kg / 7` (computed, not stored) |

### §7.3 Missing-window policy (frozen per review 4694771522 P1-1)

```
A sustained-7-day candidate window is eligible only when
all seven calendar dates contain valid, resolved observations/predictions.
```

If any one of the seven calendar dates is `missing`, `unknown`, `unresolved duplicate`, or `invalid`, the window is:

- `INCOMPLETE`
- `EXCLUDED_FROM_PEAK_COMPETITION`

Q1 does NOT permit a partial-window metric to compete with complete windows. An optional partial-window metric MAY be added in a future round, with these rules:

- the metric MUST use a different name (e.g. `partial_7day_rolling_sum_for_diagnostic_only`);
- the metric MUST NOT be called `sustained 7-day peak`;
- the metric MUST NOT participate in the `argmax` peak competition;
- the metric MUST NOT appear in any report that compares models on the sustained 7-day peak.

Q1 also requires the following counts in any report that emits sustained 7-day peak metrics:

```
total_candidate_window_count
complete_window_count
incomplete_window_count
excluded_missing_day_window_count
excluded_unknown_day_window_count
excluded_duplicate_window_count
```

If the entire horizon has no complete 7-day window:

```
SUSTAINED_7DAY_NOT_COMPUTABLE
```

The Q1 v1 said `NOT_COMPUTABLE or partial`; v1.1 freezes the missing-window policy to the single canonical rule above. The `or partial` is removed.

### §7.4 Boundary semantics (frozen)

| Boundary | Rule |
|---|---|
| forecast horizon < 7 full calendar days | `NOT_COMPUTABLE` |
| any window contains a `missing_day` | the window is `INCOMPLETE` and `EXCLUDED_FROM_PEAK_COMPETITION` (per §7.3) |
| explicit `zero_harvest_day` | can be used as 0 in the sum |
| duplicate dates | resolved by the actual-label revision contract (§4.5); the valid revision at `label_observation_cutoff_at` wins |
| multiple same-value windows | `EARLIEST_START_DATE` wins |
| negative quantity | `INVALID`; the run fails closed |
| unit | all quantities in kg |
| rounding order | sum the raw `Decimal` values first, then apply the metric-policy `quantize`; never round the daily values before the sum |
| forecast-vs-actual | both actual and forecast use the same window algorithm and the same tie-break |

### §7.5 Separation of forecast horizon and sustained peak window

Two distinct dimensions. The Q1 design-freeze treats them as disjoint concepts:

- `FORECAST_HORIZON_DAYS ∈ {7, 14, 21}` — distance from forecast generation to the forecast target date.
- `SUSTAINED_PEAK_WINDOW_DAYS = 7` — fixed rolling-window length for the cumulative peak.

Q1 forbids naming, documentation, or test-plan conventions that conflate the two. The forecast-horizon breakdown is a metric report dimension; the sustained-peak window is a quantity contract.

### §7.6 Pre-window summation rule

The sum of the 7 daily values is computed on the canonical `Decimal` values, not on rounded display values. The display rounding is applied once at the end of the sum. This rule prevents the "double rounding" error that would otherwise occur if each daily value were first rounded and then summed.

---

## §8 Existing 3-day production contract audit

Q1 does not silently reinterpret any 3-day field as a 7-day field. The 3-day production contract remains the production contract; the 7-day contract is an additive, versioned, separate contract.

### §8.1 3-day contract inventory (against `origin/main`)

The Q1 audit searched `origin/main` for the following tokens and recorded each match. The full inventory is in `docs/forecast-quality/slice-q1-data-coverage-audit.md` §B; this section is the high-level summary.

| Token | Match count in `origin/main` (excluding `origin/main` docs/calendar scripts) | Classification |
|---|---:|---|
| `sustained_3day` | 4 (1 schema, 1 adapter, 1 scenario, 1 documentation) | `CURRENT_PRODUCTION_CONTRACT` |
| `rolling_3day` | 0 | n/a |
| `strict_three_day_window` | 4 (1 schema, 1 adapter, 2 test) | `CURRENT_PRODUCTION_CONTRACT` |
| `sustained_window_days` | 6 (1 schema, 1 adapter, 4 test) | `CURRENT_PRODUCTION_CONTRACT` |
| `peak_window_cumulative_quantity` | 1 (schema field) | `CURRENT_PRODUCTION_CONTRACT` |
| `3-day peak` | 0 (text only in `docs/`) | `DOCUMENTATION_ONLY` |
| `连续 3 天` | 0 | n/a |
| `三日峰值` | 0 | n/a |

The 3-day production contract is referenced in:

- `backend/app/agent/schemas.py::ForecastPeakOutput.sustained_3day_peak` — `CURRENT_PRODUCTION_CONTRACT`.
- `backend/app/agent/schemas.py::SimulateScenarioDelta.sustained_3day_daily_average_delta_kg_per_day`, `sustained_3day_cumulative_delta_kg` — `CURRENT_PRODUCTION_CONTRACT`.
- `backend/app/agent/schemas.py::PeakMetricPolicy.sustained_window_days`, `strict_three_day_window` — `CURRENT_PRODUCTION_CONTRACT`.
- `backend/app/agent/adapters/peak.py:: _sustained_3day_peak`, `peak.py:: PeakMetricPolicy.sustained_window_days` — `CURRENT_PRODUCTION_CONTRACT`.
- `backend/app/agent/adapters/scenario.py` — `sustained_3day_*` deltas — `CURRENT_PRODUCTION_CONTRACT`.
- `backend/app/agent/slice_c/engine.py` (PR #100) — C1 contract — `CURRENT_PRODUCTION_CONTRACT`.
- `backend/tests/agent/golden/task013_slice_c_output.json` — `CURRENT_PRODUCTION_CONTRACT` Golden.
- `backend/tests/agent/golden/task013_composed_agent_output.json` — `CURRENT_PRODUCTION_CONTRACT` composed Golden.
- `backend/tests/integration/agent/test_slice_c_orchestration_postgres.py` — `CURRENT_PRODUCTION_CONTRACT` PostgreSQL acceptance.
- `docs/task-013-minimal-input-deterministic-agent-orchestration-design.md` — `LEGACY_CONTRACT` (frozen design, pre-C1).
- `docs/forecast-quality/slice-q1-forecast-target-and-evaluation-contract.md` (this document) and `docs/forecast-quality/slice-q1-data-coverage-audit.md` — `DOCUMENTATION_ONLY` (Q1 design).

### §8.2 3-day production contract status

```
CURRENT_3DAY_CONTRACT_STATUS = CURRENT_PRODUCTION_CONTRACT
CURRENT_3DAY_CONTRACT_REFERENCE_COUNT = (see Q1 data-coverage audit §B for the full count)
```

The 3-day field semantics are preserved verbatim. Q1 does not change any 3-day field.

### §8.3 7-day coexistence policy (corrected per review 4694771522 P1-4)

The Q1 v1 was internally inconsistent: it said the active version emits only the active field, then said both fields are emitted during the deprecation window. v1.1 freezes a single canonical policy.

```
sustained_3day_peak        — always present when 3-day is a supported window
sustained_7day_peak        — always present when 7-day is a supported window
primary_sustained_peak_window_days — 3 or 7; the default display, default explanation, and default downstream primary selection
supported_sustained_peak_window_days — list, default [3, 7]
```

Both fields are present in the same output; the policy does not decide field presence, it decides default selection.

Q1 freezes the following candidate contract:

```
sustained_peak_schema_version: Literal["sustained-peak-v1"]
primary_sustained_peak_window_days: Literal[3, 7]
supported_sustained_peak_window_days: list[Literal[3, 7]]
```

The candidate contract is not yet implemented. Q1 marks it as `DESIGN_CANDIDATES` and `NOT_YET_IMPLEMENTATION_AUTHORITY`. The candidate does not specify which schema class the new field is added to; both `additive field on ForecastPeakOutput` and `new ForecastPeakOutputV2` are design alternatives. The candidate does not modify production, Golden, or API.

The candidate contract forbids:

- the active-version-only policy that removes the inactive field;
- the inactive-field-absent policy that hides the inactive field;
- any silent rename of `sustained_3day_peak` to `sustained_7day_peak`;
- any silent semantic change to either field.

### §8.4 7-day migration boundary (design only, not implemented in Q1)

The 7-day migration is a separate design and implementation round. Q1 freezes the migration boundary but does not implement it. The migration design is:

- A new `sustained_7day_peak: dict[ForecastQuantile, SustainedPeakEntry]` field is added to `ForecastPeakOutput` (or a new `ForecastPeakOutputV2` schema version).
- The new field uses the existing `SustainedPeakEntry` schema, which already has `start_date`, `end_date`, `rolling_daily_average_kg_per_day`, `cumulative_quantity_kg`. No new field shape is required.
- The new field is gated by the `sustained_peak_schema_version` policy field; the output contains the field for every window in `supported_sustained_peak_window_days`.
- The 3-day field is preserved as a permanent co-existing field; it is not deprecated and not removed.
- The Golden migration is explicit: both fields are emitted; the Golden contains both 3-day and 7-day fields; the test plan includes both 3-day and 7-day assertions.
- The API migration is explicit: the API returns both 3-day and 7-day fields; the consumer chooses one based on the policy version.
- The 3-day field is not renamed; the 3-day field is not reinterpreted; the 3-day field is not deleted; the 3-day field is not aliased to the 7-day field.

```
7DAY_MIGRATION_REQUIRED = YES (separate design and implementation round, not in Q1)
SUSTAINED_7DAY_IMPLEMENTED = NO
7DAY_TARGET_CONTRACT_FROZEN = YES (this document §7)
THREE_DAY_SEVEN_DAY_COEXISTENCE_POLICY = ADDITIVE_BOTH_FIELDS_PRESENT (frozen in v1.1)
```

### §8.5 Forbidden silent 3-day → 7-day reinterpretation

Q1 forbids:

- renaming `sustained_3day_peak` to `sustained_7day_peak` without an additive migration;
- changing the meaning of `sustained_window_days = 3` to `7` without a versioned policy field;
- aliasing `peak_window_cumulative_quantity_kg` to a 7-day window without a new field;
- changing the Golden's 3-day value to a 7-day value;
- changing the test assertion from "sustained_3day_peak" to "sustained_7day_peak" without a deprecation window.

### §8.6 3-day production semantics preserved

The 3-day field continues to mean "the maximum rolling 3-day arithmetic mean / cumulative quantity of the forecast at the quantile". The 7-day field, when added, will mean "the maximum rolling 7-day arithmetic mean / cumulative quantity". The two fields are independent and additive.

---

## §9 Evaluation metric contract

### §9.1 Evaluation grain (frozen)

All metrics in this section use the same evaluation slice:

```
EVALUATION_GRAIN = (farm_id, subfarm_or_plot_id, variety_id, season_id,
                    forecast_cutoff_at, forecast_target_date, forecast_horizon_days,
                    label_observation_cutoff_at, evaluation_label_mode,
                    model_version, data_snapshot)
```

`forecast_horizon_days ∈ {7, 14, 21}`. The Q1 design-freeze does not restrict the horizon to a single value; the metrics are reported per horizon.

`evaluation_label_mode ∈ {AS_OF_EVALUATION, FINAL_ADJUDICATED}` per §4.4.

### §9.2 Daily metrics (frozen)

| Metric | Definition | Notes |
|---|---|---|
| `daily_mae` | `mean(abs(forecast_p50 - actual))` over the rows in the slice | unit: kg |
| `daily_wape` | `sum(abs(forecast_p50 - actual)) / sum(abs(actual))` over the rows in the slice | unit: fraction; if `sum(abs(actual)) = 0` → `NOT_COMPUTABLE`; never returns 0 or infinity |
| `daily_smape` | `mean( 2 * abs(forecast - actual) / (abs(actual) + abs(forecast)) )` | when both `actual = 0` and `forecast = 0`, the row's `smape = 0`; when `abs(actual) + abs(forecast) = 0` and the row is not a both-zero case, the row's `smape = NOT_COMPUTABLE` |
| `daily_mape` | `mean( abs(forecast_p50 - actual) / actual )` over rows with `actual > 0` | unit: fraction; the metric MUST report `mape_eligible_row_count`, `zero_actual_row_count`, `excluded_row_count`; never uses a hidden epsilon |
| `daily_bias` | `mean(forecast_p50 - actual)` over the rows in the slice | unit: kg |
| `daily_relative_bias` | `sum(forecast - actual) / sum(actual)` over the rows in the slice | unit: fraction; if `sum(actual) = 0` → `NOT_COMPUTABLE` |

The Q1 design-freeze does not implement these metrics; the metrics are frozen as definitions for Q5.

### §9.3 Cumulative metrics (frozen, with signed/absolute separation)

| Metric | Definition | Notes |
|---|---|---|
| `season_cumulative_actual_kg` | `sum(actual)` from season start through the last day in the slice | unit: kg |
| `season_cumulative_forecast_kg` | `sum(forecast_p50)` from season start through the last day in the slice | unit: kg |
| `cumulative_absolute_error_kg` | `abs(season_cumulative_forecast_kg - season_cumulative_actual_kg)` | unit: kg |
| `cumulative_signed_relative_error` | `(season_cumulative_forecast_kg - season_cumulative_actual_kg) / season_cumulative_actual_kg` | unit: fraction; if `season_cumulative_actual_kg = 0` → `NOT_COMPUTABLE` |
| `cumulative_absolute_relative_error` | `abs(season_cumulative_forecast_kg - season_cumulative_actual_kg) / abs(season_cumulative_actual_kg)` | unit: fraction; if `abs(season_cumulative_actual_kg) = 0` → `NOT_COMPUTABLE` |
| `zero_denominator_count` | rows in the slice with `abs(actual) = 0` | must be reported alongside any relative metric |
| `eligible_denominator_count` | rows in the slice with `abs(actual) > 0` | must be reported alongside any relative metric |
| `excluded_denominator_count` | rows in the slice excluded from the relative metric | must be reported alongside any relative metric |

Q1 v1 used a single field `cumulative_relative_error` with a signed formula. v1.1 separates the signed and absolute variants and renames the signed field to `cumulative_signed_relative_error`. v1.1 also adds the absolute variant `cumulative_absolute_relative_error` and the denominator counts.

### §9.4 Single-day peak metrics (frozen per review 4694771522 P1-2)

The Q1 v1 froze a single forecast single-day peak. v1.1 freezes the quantile-shaped single-day peak consistent with `ForecastPeakOutput.single_day_peak: dict[ForecastQuantile, SingleDayPeakEntry]`.

| Metric | Definition | Notes |
|---|---|---|
| `actual_single_day_peak_date` | the calendar date of the maximum actual daily value in the season | tie-break: `EARLIEST_DATE` |
| `actual_single_day_peak_quantity_kg` | the maximum actual daily value in the season | unit: kg |
| `forecast_single_day_peak_date_q` | the calendar date of the maximum forecast daily value at quantile `q` | tie-break: `EARLIEST_DATE`; `q ∈ {P50, P80, P90}` |
| `forecast_single_day_peak_quantity_kg_q` | the maximum forecast daily value at quantile `q` | unit: kg; `q ∈ {P50, P80, P90}` |
| `single_day_peak_date_signed_error_days_q` | `forecast - actual` for the date at quantile `q` | positive → forecast peak is later; negative → earlier |
| `single_day_peak_date_absolute_error_days_q` | `abs(signed_error_days)` at quantile `q` | unit: days |
| `single_day_peak_quantity_absolute_error_kg_q` | `abs(forecast_q - actual)` at quantile `q` | unit: kg |
| `single_day_peak_quantity_signed_relative_error_q` | `(forecast_q - actual) / actual` at quantile `q` | if `actual = 0` → `NOT_COMPUTABLE`; report `zero_denominator_count`, `eligible_denominator_count`, `excluded_denominator_count` |
| `single_day_peak_quantity_absolute_relative_error_q` | `abs(forecast_q - actual) / abs(actual)` at quantile `q` | if `abs(actual) = 0` → `NOT_COMPUTABLE`; same denominator counts |

The actual single-day peak is one row per season (one `actual_single_day_peak_date`, one `actual_single_day_peak_quantity_kg`). The forecast single-day peak is per quantile. The error metrics are per quantile. P50 may be the primary point-forecast for display, but P80 and P90 MUST be reported independently and MUST NOT be silently dropped.

### §9.5 Sustained 7-day peak metrics (frozen)

| Metric | Definition | Notes |
|---|---|---|
| `actual_sustained_7day_peak_start_date` | the start date of the actual sustained 7-day peak window | tie-break: `EARLIEST_DATE` |
| `actual_sustained_7day_peak_end_date` | `actual_sustained_7day_peak_start_date + 6 calendar days` | computed |
| `actual_sustained_7day_cumulative_quantity_kg` | the cumulative actual quantity in the 7-day window | unit: kg |
| `actual_sustained_7day_daily_average_kg_per_day` | `cumulative_quantity_kg / 7` | computed |
| `forecast_sustained_7day_peak_start_date_q` | the start date of the forecast sustained 7-day peak window at quantile `q` | tie-break: `EARLIEST_DATE` |
| `forecast_sustained_7day_peak_end_date_q` | `forecast_sustained_7day_peak_start_date_q + 6 calendar days` | computed |
| `forecast_sustained_7day_cumulative_quantity_kg_q` | the cumulative forecast quantity in the 7-day window at quantile `q` | unit: kg |
| `forecast_sustained_7day_daily_average_kg_per_day_q` | `cumulative_quantity_kg_q / 7` | computed |
| `sustained_7day_peak_start_date_signed_error_days_q` | `forecast - actual` for the start date at quantile `q` | positive → forecast peak is later |
| `sustained_7day_peak_start_date_absolute_error_days_q` | `abs(signed_error_days)` at quantile `q` | unit: days |
| `sustained_7day_peak_cumulative_absolute_error_kg_q` | `abs(forecast_cumulative_q - actual_cumulative)` at quantile `q` | unit: kg |
| `sustained_7day_peak_cumulative_signed_relative_error_q` | `(forecast_q - actual) / actual` at quantile `q` | if `actual = 0` → `NOT_COMPUTABLE`; report denominator counts |
| `sustained_7day_peak_cumulative_absolute_relative_error_q` | `abs(forecast_q - actual) / abs(actual)` at quantile `q` | if `abs(actual) = 0` → `NOT_COMPUTABLE`; same denominator counts |
| `sustained_7day_peak_daily_average_absolute_error_kg_per_day_q` | `abs(forecast_daily_average_q - actual_daily_average)` | unit: kg / day |

### §9.6 Missing-window counts (frozen)

Q1 requires the following counts in any report that emits sustained 7-day peak metrics:

```
total_candidate_window_count
complete_window_count
incomplete_window_count
excluded_missing_day_window_count
excluded_unknown_day_window_count
excluded_duplicate_window_count
```

If the entire horizon has no complete 7-day window:

```
SUSTAINED_7DAY_NOT_COMPUTABLE
```

### §9.7 Quantile calibration (frozen)

Q1 freezes the calibration contract conditionally on the quantile semantics being verifiable. If the quantile field is a true upper quantile, then:

```
P50_coverage = mean(actual <= forecast_p50)
P80_coverage = mean(actual <= forecast_p80)
P90_coverage = mean(actual <= forecast_p90)
```

If the quantile field is not a true upper quantile — for example, if it is a point estimate, an interval label, or a scenario label — then:

```
QUANTILE_SEMANTICS_NOT_VERIFIED
COVERAGE_NOT_COMPUTABLE
```

Q1 does not implement calibration. Q1 freezes the contract only. The Q2 / Q5 design must verify the quantile semantics on `origin/main` and document the result.

```
P50_SEMANTICS = NOT_VERIFIED (Q2 / Q5 must verify on origin/main)
P80_SEMANTICS = NOT_VERIFIED
P90_SEMANTICS = NOT_VERIFIED
QUANTILE_COVERAGE_STATUS = NOT_VERIFIED
P80_P90_SEMANTICS_STATUS = NOT_VERIFIED
```

### §9.8 Interval width (frozen)

If the forecast output has both a lower quantile and an upper quantile, then:

```
interval_width_mean = mean(forecast_upper - forecast_lower)
interval_width_median = median(forecast_upper - forecast_lower)
```

If the forecast output has only an upper quantile, then:

```
INTERVAL_WIDTH_NOT_COMPUTABLE
LOWER_BOUND_NOT_AVAILABLE
```

Q1 forbids using `P90 - P50` as a stand-in for the prediction interval width. The two values are at different quantiles; the difference is not a coverage interval. A separate metric `upper_spread_p90_minus_p50 = forecast_p90 - forecast_p50` is permitted and MUST be reported as such; it is not an interval width.

### §9.9 Pinball loss (frozen, definition only)

For a quantile `q ∈ (0, 1)`, an actual value `a`, and a forecast value `f_q`:

```
pinball_loss(q, a, f_q) =
    max( q * (a - f_q), (q - 1) * (a - f_q) )
```

Q1 freezes the definition. The Q2 / Q5 design must:

- verify that P50, P80, P90 are true quantiles (not point estimates or interval labels);
- if verified, define `pinball_loss_p50`, `pinball_loss_p80`, `pinball_loss_p90` as Q1 frozen functions of `pinball_loss`;
- if not verified, mark the metric as `QUANTILE_SEMANTICS_NOT_VERIFIED` and `PINBALL_LOSS_NOT_COMPUTABLE`.

### §9.10 Forbidden metric patterns

- "Tests pass" is not a substitute for a forecast-accuracy metric.
- `forecast - actual` (a single difference) is not a metric; metrics are aggregates over rows.
- `mean(forecast - actual)` is the bias; `mean(abs(forecast - actual))` is the MAE; conflating the two is a metric-pattern error.
- Using a single `mape` to summarize is forbidden; the metric must report `mape_eligible_row_count`, `zero_actual_row_count`, `excluded_row_count`.
- Using a `epsilon` to avoid `0 / 0` in MAPE is forbidden; the metric must explicitly handle the zero case and report the row count.
- Using `forecast_p90 - forecast_p50` as the prediction interval width is forbidden.
- Using a single `relative_error` field with an unsigned interpretation when the formula is signed is forbidden; signed and absolute must be separate fields.

---

## §10 Data coverage audit (read-only, see companion document)

The full data-coverage audit, including the 3-day production contract inventory, the actual-label grain audit, the harvest-state schema audit, the migration-history audit, the table-inventory audit, and the live-database discovery result, is in `docs/forecast-quality/slice-q1-data-coverage-audit.md`. This document is the single source of truth for the read-only data audit.

### §10.1 Live-database discovery result (v1.1, per review 4694771522 P0-4)

Q1 v1.1 performed a read-only live-database discovery on the configured PostgreSQL (`POSTGRES_HOST=localhost`, `POSTGRES_PORT=5432`, `POSTGRES_DB=blueberry_peak`, `POSTGRES_USER=blueberry_app`).

Discovery result:

- DB discoverable: **YES** (the `.env` and `docker-compose.yml` declare the connection; `psql` connects successfully; `SELECT now()` returns the current timestamp).
- DB reachable: **YES** (`psql -c "SELECT 1;"` returns `1`; a Docker container `c2-pg` is running on the local network).
- DB has data: **NO** (all 33 public-schema tables report 0 rows; `alembic_version` reports `0013_rolling_backtest_orch`, indicating that migrations 0014 and 0015 have not been applied to this DB; `harvest_state_replay_source_visibility_audit` does not exist, confirming 0015 has not been applied).
- Data source: configured PostgreSQL via Docker container `c2-pg` (image `pgvector/pgvector:pg16`, port 55432→5432, ~4 hours old at discovery time).
- No fabrication: the 0-row aggregate is the truthful result of the discovery query; no fixture, no Golden, no sample data was substituted for real data.

```
REAL_DATA_SOURCE_DISCOVERY = POSTGRES_DOCKER_CONTAINER_C2_PG
REAL_DATA_COVERAGE_STATUS = NOT_VERIFIED
Q1_DATA_COVERAGE_AUDIT_STATUS = PARTIAL
```

The 0-row aggregate means that the real-data coverage matrix cannot be populated with non-zero values. The matrix entries are:

- `farm_count` (from `dim_farm`): 0
- `subfarm_count` (from `dim_subfarm`): 0
- `variety_count` (from `dim_variety`): 0
- `season_count` (from `dim_season`): 0
- `daily_row_count` (from `fact_receipt_daily`): 0
- `positive_day_count` (from `fact_receipt_daily` where `weight_kg > 0`): 0
- `explicit_zero_day_count` (from `fact_receipt_daily` where `weight_kg = 0`): 0
- `missing_day_count`: 0 (no daily row count)
- `duplicate_key_count`: 0 (no daily row count; the unique constraint would force 0 in any case)
- `build_run_count` (from `fact_receipt_daily.build_run_id`): 0
- `series_with_at_least_7_days`: 0

Q1 reports these as the truthful result of a real read-only query. Q1 does NOT claim the real-data coverage is `COMPLETE` / `READY` / `VERIFIED`. The status is `NOT_VERIFIED` because there is no data to verify against.

### §10.2 Read-only query evidence (per §7.2 of the round instruction)

Q1 ran the following read-only queries on the live PostgreSQL. The output is included in the companion data-coverage audit. No query mutated data, no query created a table, no query altered a schema. The queries are aggregate-only; they do not return row-level data.

Queries executed:

1. `SELECT COUNT(*) FROM <each_table>;` for 16 tables.
2. `SELECT COUNT(*) FILTER (...), MIN(receipt_date), MAX(receipt_date), COUNT(DISTINCT ...) FROM fact_receipt_daily;`
3. `SELECT SUM(weight_kg), AVG(weight_kg), MIN(weight_kg), MAX(weight_kg) FROM fact_receipt_daily WHERE weight_kg > 0;`
4. `SELECT (series-level aggregation over season × farm × variety from fact_receipt_daily);`
5. `SELECT (dim-table count) from dim_farm, dim_subfarm, dim_variety, dim_season;`
6. `SELECT version_num FROM alembic_version;`
7. `SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'public';`

No query returned a `farm name`, `subfarm name`, `operator name`, `customer name`, `exact daily quantity`, `exact forecast output`, or `exact row count` on real data. All outputs are aggregate counts (`COUNT(*)`, `MIN`, `MAX`, `SUM`, `AVG`, `COUNT(DISTINCT)`, `n_live_tup`).

### §10.3 Backtest usability gate (recap)

A series is `usable_backtest_series` if and only if all of the following hold:

- grain identity is complete;
- date-continuity rule is explicit;
- actual label is not a proxy, or the proxy is explicitly accepted and disclosed;
- unit is consistent (kg);
- no unresolved duplicate;
- point-in-time visibility is verifiable for the chosen `label_observation_cutoff_at`;
- `forecast_cutoff_at` and `label_observation_cutoff_at` are both bindable to a specific replay identity;
- at least one full 7-day target window is present (per §7);
- the actual label and the forecast output are alignable at the same grain.

The current `fact_receipt_daily` does not satisfy the grain identity (no `subfarm_or_plot_id`), the point-in-time visibility (no `recorded_at`, `effective_at`, `revised_at`, `revision_number`, `supersedes_record_id`), the explicit-zero handling (structurally excluded), or the row-level revision (re-build only). The `usable_backtest_series_count` against `fact_receipt_daily` is `0` by the Q1 gate.

```
USABLE_BACKTEST_SERIES_COUNT_AGAINST_FACT_RECEIPT_DAILY = 0 (by the Q1 gate; re-build mechanism is not row-level revision; explicit zero days are missing rows; subfarm_or_plot_id is not a column)
```

### §10.4 Desensitization note

The Q1 design-freeze does not output any sensitive real business data. No farm name, no subfarm name, no variety name (other than the public `dim_variety` table), no operator name, no exact daily quantity, no exact forecast output, and no exact row count on real data is reported. The Q2 / Q5 report must apply the same desensitization policy.

---

## §11 Alignment contract (frozen, design only)

Q1 freezes the alignment contract for matching the current aggregate forecast output to a farm/subfarm/variety actual label. Q1 does NOT implement the alignment; Q1 freezes two candidate paths.

### §11.1 Path A — Member-grain forecast evaluation

Path A uses the upstream Task 9 `harvest_state_daily_member_row` table. The member row has first-class `farm_id` / `subfarm_id` / `variety_id` / `state_date` and a per-state `harvested_quantity_kg` and `arrival_quantity_kg`. Path A aligns member rows to the same-grain actual label.

Status:

```
CANDIDATE_ALIGNMENT_PATH
NOT_YET_ACCEPTED
```

### §11.2 Path B — Aggregate-level evaluation

Path B aggregates the actual label by the same member set and date that the agent request used, and compares the aggregate to `ForecastDailyRow`. The aggregation function is frozen by Q1 as a candidate:

- member set = the request's `variety` list intersected with the location's effective variety set;
- location identity = the resolved `NormalizedAgentRequest.normalized_location`;
- variety set = the request's `variety` list;
- aggregation function = `sum(per-member actual)` over the member set and the date;
- missing-member behavior = the absent member is treated as a `missing_day` per §6.6;
- duplicate behavior = the revision contract per §4.5;
- unit = kg;
- snapshot identity = the `model_version`, `data_snapshot`, and `label_snapshot_hash` triple;
- canonical member-set hash = `sha256(canonical JSON of (member_set, date))`.

Status:

```
CANDIDATE_ALIGNMENT_PATH
NOT_YET_ACCEPTED
```

### §11.3 Q1 freeze

Q1 does NOT select Path A or Path B as the final production contract. The selection requires Q2A design and implementation, with separate Charles authorization.

---

## §12 Slice ordering (frozen, acyclic per review 4694771522 P0-3)

Q1 v1 had a non-acyclic dependency between Q2 and Q3: Q2 required the 7-day production field, but Q3 is ordered after Q2; Q2 also bundled a naive-baseline comparator while Q4 is the dedicated naive-baseline slice. v1.1 freezes an acyclic slice ordering with explicit dependency on the dual-cutoff model and on the actual-label source decision.

### §12.1 Slice ordering (acyclic)

| Slice | Goal | Predecessor | Status |
|---|---|---|---|
| Q1 | forecast target + evaluation contract + dual-cutoff model + sustained 7-day target contract + 3-day coexistence policy | (none) | design (this PR #103) |
| Q2A | actual-label source decision + dedicated table or accepted proxy + schema/migration + revision lineage + `label_observation_cutoff_at` evaluation-snapshot foundation + aggregate data-coverage query | Q1 | NOT AUTHORIZED |
| Q2B | point-in-time backtest runner for currently supported outputs (the outputs that exist on `origin/main` after Q2A's accepted proxy, at the accepted grain) | Q2A | NOT AUTHORIZED |
| Q3 | additive sustained 7-day production migration (new field, 3-day coexistence, schema version, Golden/API compatibility, production acceptance) | Q1 | NOT AUTHORIZED |
| Q2C | extend Q2B with sustained 7-day scoring | Q2B + Q3 | NOT AUTHORIZED |
| Q4 | naive baseline (one repeatable baseline, compared with the current model on the same data, the same cutoff, the same actual label, the same metric, the same 7-day peak definition) | Q2B | NOT AUTHORIZED |
| Q5 | consolidated forecast-quality report (Q2B + Q2C + Q4 outputs aggregated into the report rows of Issue #102 §3) | Q2B + Q2C + Q4 | NOT AUTHORIZED |
| Q6 | model improvement (allowed only after Q1..Q5 are accepted) | Q1..Q5 | NOT AUTHORIZED |
| Q7 | thin trial UI (two pages: forecast page, forecast-vs-actual page) | Q5 | NOT AUTHORIZED |

### §12.2 Q2 readiness

```
Q2_DESIGN_CAN_START = YES
Q2_IMPLEMENTATION_READY = NO
Q2_READINESS = BLOCKED_BY_Q1_GAPS
```

Q2 implementation is blocked by the following Q1 gaps:

- `ACTUAL_LABEL_SOURCE_UNRESOLVED` (Q2A must resolve)
- `ACTUAL_LABEL_SCHEMA_UNRESOLVED` (Q2A must resolve)
- `LABEL_OBSERVATION_CUTOFF_NOT_IMPLEMENTED` (Q2A must implement the dual-cutoff snapshot)
- `TARGET_OUTPUT_GRAIN_NOT_ALIGNED` (Q2A must resolve the path A / path B choice)
- `QUANTILE_SEMANTICS_NOT_VERIFIED` (Q2B must verify)
- `REAL_DATA_COVERAGE_NOT_VERIFIED` (Q2B must verify on a real data source)
- `SUSTAINED_7DAY_NOT_IMPLEMENTED` (Q3 must implement)

Q2 DESIGN work (the design of the Q2A actual-label source decision, the Q2B backtest runner contract, the Q2C extension for 7-day scoring) may begin once Q1 is accepted by Charles. Q2 IMPLEMENTATION requires the Q2 readiness items to be resolved.

### §12.3 Subsequent slice recommendations (Q1 does NOT implement)

Q1 recommends the following slice ordering, all of which require separate Charles authorization:

#### §12.3.1 Slice Q2A — actual-label source and evaluation-snapshot foundation

The Q2A minimum entry conditions are:

1. The Q1 design-freeze is accepted by Charles.
2. The actual-label source decision: either (a) a dedicated `actual_harvest_daily` table is added, or (b) `fact_receipt_daily` is accepted as a proxy with explicit `PROXY_LABEL` disclosure.
3. The dual-cutoff snapshot identity is accepted: `forecast_cutoff_at` and `label_observation_cutoff_at` are two distinct fields.
4. The aggregation path (Path A or Path B) is accepted.

The Q2A deliverables are:

- the actual-label source decision recorded in a design document;
- the schema or the proxy acceptance;
- the migration (if a new table is added);
- the revision lineage contract;
- the `label_observation_cutoff_at` evaluation-snapshot identity;
- the aggregate data-coverage query runner that returns `farm_count`, `subfarm_count`, `variety_count`, `season_count`, `date_min`, `date_max`, `daily_row_count`, `positive_day_count`, `explicit_zero_day_count`, `missing_day_count`, `duplicate_key_count`, `build_run_count`, `series_with_at_least_7_days` against a real data source.

Q2A does NOT modify any model. Q2A does NOT change TASK-008 / TASK-009 / TASK-010 numerical semantics.

#### §12.3.2 Slice Q2B — point-in-time backtest runner

The Q2B minimum entry conditions are Q2A acceptance. The Q2B deliverable is the point-in-time backtest runner that:

- consumes the actual-label contract (from Q2A);
- consumes the forecast-output contract (from Q2A's accepted aggregation path);
- consumes the replay identity;
- consumes the metric contract;
- supports the dual-cutoff model;
- reports per-evaluation-slice metrics;
- supports `AS_OF_EVALUATION` and `FINAL_ADJUDICATED` modes.

Q2B does NOT require the 7-day production field. Q2B may use the existing 3-day production field as the primary sustained-peak metric in the first stage.

#### §12.3.3 Slice Q3 — sustained 7-day peak production migration

The Q3 minimum entry conditions are Q1 acceptance. The Q3 deliverable is the additive 7-day field, with the additive-coexistence policy (§8.3), the migration, the Golden migration, the API migration, and the PostgreSQL production-chain acceptance.

#### §12.3.4 Slice Q2C — extend the runner with 7-day scoring

Q2C depends on Q2B + Q3. The Q2C deliverable is the extension of the Q2B runner to emit the sustained 7-day peak metrics.

#### §12.3.5 Slice Q4 — naive baseline

Q4 depends on Q2B. The Q4 deliverable is at least one repeatable naive baseline (for example, "previous-season same-relative-day" or "area × historical yield curve"), compared with the current model on the same data, the same cutoff, the same actual label, the same metric, the same 7-day peak definition.

#### §12.3.6 Slice Q5 — forecast quality report

Q5 depends on Q2B + Q2C + Q4. The Q5 deliverable is the consolidated report rows of Issue #102 §3.

#### §12.3.7 Slice Q6 — model improvement

Q6 depends on Q1..Q5. The Q6 deliverable is at least one model change that improves the metric deltas in Issue #102 §3. Q6 is gated by the Q5 forecast-quality report.

#### §12.3.8 Slice Q7 — thin trial UI

Q7 depends on Q5. The Q7 deliverable is the two pages (forecast page, forecast-vs-actual page) with CSV / Excel import-export.

---

## §13 Forbidden actions in Q1 (v1.1, per review)

Q1 v1.1 forbids the following actions in this round. Each forbidden action is paired with the rationale and the verification check.

| Forbidden action | Rationale | Verification check |
|---|---|---|
| modify any production code under `backend/app/**` | Q1 is docs-only | `git diff --name-only origin/main` excludes `backend/app/` |
| modify any test under `backend/tests/**` | Q1 is docs-only | `git diff --name-only origin/main` excludes `backend/tests/` |
| add or modify any migration under `backend/alembic/**` | Q1 freezes the contract; it does not implement | `git diff --name-only origin/main` excludes `backend/alembic/` |
| modify any Golden file | Q1 freezes the contract; it does not change Goldens | `git diff --name-only origin/main` excludes any `golden/` |
| modify any frontend, dependency, or workflow | Q1 is docs-only | `git diff --name-only origin/main` excludes `frontend/`, `.github/`, dependency files |
| implement the 7-day peak production code | Q1 freezes the contract; Q3 implements | the new commit does not add any `sustained_7day_peak` field to `backend/app/agent/schemas.py` |
| implement the backtest runner | Q1 freezes the contract; Q2B implements | the new commit does not add any backtest runner file |
| implement the naive baseline | Q1 freezes the contract; Q4 implements | the new commit does not add any baseline file |
| silently rename `sustained_3day_peak` to `sustained_7day_peak` | Q1 forbids silent reinterpretation | the new commit does not modify the 3-day field semantics |
| use a single time cutoff for both model input and label visibility | the dual-cutoff model is the only correct anti-leakage boundary | the new commit defines `forecast_cutoff_at` and `label_observation_cutoff_at` as two distinct timestamps |
| describe `ForecastDailyRow` as having 7 quantity fields | the merged schema has exactly 6 `DailyQuantiles` quantity fields | the new commit lists 6 fields |
| describe `ForecastDailyRow` as first-class `(farm × subfarm × variety × date)` | the merged schema does not carry first-class farm/subfarm/variety identity | the new commit describes the row as a downstream aggregate |
| use `harvestable_quantity = harvested - backlog` as a formula | the formula has no physical authority and can be negative | the new commit marks `harvestable_quantity` as `NOT_CURRENTLY_AVAILABLE` / `FORMULA_NOT_AUTHORIZED` |
| claim `Q2_READINESS = READY` | the same document reports Q1 gaps | the new commit sets `Q2_READINESS = BLOCKED_BY_Q1_GAPS` |
| report `REAL_DATA_COVERAGE_STATUS = COMPLETE / READY / VERIFIED` | the live database is empty | the new commit sets `REAL_DATA_COVERAGE_STATUS = NOT_VERIFIED` |
| set `Q2_READINESS = READY` while the same decision table says `Q2_IMPLEMENTATION_READY = NO` | the two must be consistent | the new commit keeps the three Q2 states distinct |
| use signed and absolute relative error under a single field | the two have different meanings | the new commit names signed and absolute variants separately |
| leave a sustained 7-day window `NOT_COMPUTABLE or partial` | this is ambiguous | the new commit names a single canonical rule (excluded from peak competition) |
| report single-day peak metrics at only P50 | the production output is per quantile | the new commit defines per-quantile forecast peak metrics |
| close Issue #99 | Issue #99 remains open for the P0 mainline | `gh issue view 99 --json state` is `OPEN` |
| close Issue #102 | Issue #102 remains open for Q1 acceptance and subsequent slices | `gh issue view 102 --json state` is `OPEN` |
| re-open PR #101 | PR #101 is closed without merge | `gh pr view 101 --json state` is `CLOSED` |
| mark the PR Draft as Ready | Q1 only authorizes a Draft PR | the Draft PR is in `OPEN / Draft / NOT MERGED` state |
| merge the PR | Q1 only authorizes a Draft PR | the PR is not merged |
| delete the PR #101 branch | Q1 only authorizes a Draft PR | the branch is preserved |
| delete the PR #101 worktree | Q1 only authorizes a Draft PR | the worktree is preserved |
| delete the Q1 worktree | Q1 only authorizes a Draft PR | the worktree is preserved |
| delete the prototype worktree | Q1 only authorizes a Draft PR | the worktree is preserved |
| delete any untracked file | Q1 only authorizes a Draft PR | the 4 untracked files in the main worktree are preserved |
| output sensitive real business data | Q1 forbids real-data output | the data-coverage audit reports `NOT_VERIFIED` for live-database access |
| claim the 7-day peak is implemented | Q1 only freezes the contract | the report explicitly states `SUSTAINED_7DAY_IMPLEMENTED = NO` |
| claim the forecast accuracy has improved | Q1 does not change any model | the report explicitly states `MODEL_CHANGE_NOT_AUTHORIZED` |
| fabricate real-data coverage | the audit reports `NOT_VERIFIED` for live-database access | the live-database query result is recorded as 0 rows for all tables |

---

## §14 Validation checklist (against round §14)

Q1 v1.1 ran the following validation checks:

1. `git diff --check` — clean.
2. `git diff --name-only origin/main` — only `docs/forecast-quality/` files.
3. forbidden-files exact set — empty (no `backend/`, `alembic/`, `frontend/`, `.github/`, dependency, Golden, fixture, or database file modified).
4. no backend changes — verified by `git diff --name-only origin/main -- backend/`.
5. no frontend changes — verified by `git diff --name-only origin/main -- frontend/`.
6. no test changes — verified by `git diff --name-only origin/main -- backend/tests/`.
7. no migration changes — verified by `git diff --name-only origin/main -- backend/alembic/`.
8. no workflow changes — verified by `git diff --name-only origin/main -- .github/`.
9. no Golden changes — verified by `git diff --name-only origin/main -- '**/golden/**'`.
10. `ForecastDailyRow` quantity-field exact count = 6 — verified by `git show origin/main:backend/app/agent/schemas.py | grep -E "DailyQuantiles"`.
11. `ForecastDailyRow` has no first-class `farm_id` / `subfarm_id` / `variety_id` — verified by `git show origin/main:backend/app/agent/schemas.py | grep -E "forecast_daily_row|ForecastDailyRow"`.
12. no `harvested - backlog` derivation remains — verified by `grep -nE "harvestable.*harvested.*backlog|harvested.*-.*unharvested" docs/forecast-quality/*.md` returning no derivation.
13. `forecast_cutoff_at` and `label_observation_cutoff_at` both defined — verified by the dual-cutoff model in §4.
14. no actual-label rule requires label visibility at forecast cutoff — verified by §4.5 and §6.5.
15. no statement that training and label visibility are identical — verified by §4.1 and §4.2.
16. no `Q2_READINESS = READY` — verified by the decision table.
17. no circular Q2/Q3/Q4 dependency — verified by the acyclic slice ordering in §12.1.
18. no sustained-7-day `NOT_COMPUTABLE or partial` ambiguity — verified by §7.3.
19. no "later recorded_at wins" — verified by §4.5 and §6.5.
20. signed and absolute relative errors both defined — verified by §9.3, §9.4, §9.5.
21. 3-day/7-day coexistence wording consistent — verified by §8.3.
22. P50/P80/P90 single-day peak fields consistent — verified by §9.4.
23. no claim that real-data coverage was verified — verified by §10.1.
24. no claim that Q1 is accepted — verified by the sign-off section (§16) which says `Q1_NOT_YET_ACCEPTED` and `RE_REVIEW_REQUIRED`.
25. internal Markdown links valid — every `(\#…)` anchor is verified by the Q1 author and matches a section heading in the same document or in the companion document.
26. document line counts — reported in the final report.
27. SHA-256 for all three files — reported in the final report.
28. live-database discovery result — recorded in §10.1.

---

## §15 Change log

| Date | Round | Author | Change |
|---|---|---|---|
| 2026-07-14 | v1 (Q1) | Charles-authorized Q1 design-only round | Initial creation. Frozen forecast-object contract (8 objects). Frozen actual-label contract (canonical grain, canonical fields, point-in-time visibility, special-day semantics). Frozen sustained 7-day peak contract. 3-day production contract audited and preserved verbatim. Data-coverage audit reported `BLOCKED_BY_DATA`. |
| 2026-07-14 | v1.1 (Q1 P0 fixup) | Charles-authorized Q1 P0 fixup (review 4694771522) | (1) Two-cutoff model: `forecast_cutoff_at` (gates model inputs) and `label_observation_cutoff_at` (gates label revisions for evaluation). Two evaluation modes: `AS_OF_EVALUATION` and `FINAL_ADJUDICATED`. Revision resolution by explicit supersession lineage, not by `latest timestamp`. (2) `ForecastDailyRow` quantity-field count corrected from 7 to 6. Grain corrected from `(farm × subfarm × variety × calendar_date)` to `(one resolved agent request, one resolved location, one resolved season) × calendar_date` with nested per-variety contribution. (3) `TARGET_OUTPUT_ALIGNMENT` split into `TARGET_PHYSICAL_QUANTITY_ALIGNMENT = NOT_PROVEN_EQUIVALENT` and `TARGET_GRAIN_ALIGNMENT = NOT_ALIGNED`. (4) `harvestable_quantity = harvested - backlog` formula removed; `harvestable_quantity` marked `NOT_CURRENTLY_AVAILABLE` / `FORMULA_NOT_AUTHORIZED`. (5) Q2 readiness corrected: `Q2_DESIGN_CAN_START = YES`; `Q2_IMPLEMENTATION_READY = NO`; `Q2_READINESS = BLOCKED_BY_Q1_GAPS` with 7 listed blockers. (6) Acyclic slice ordering: Q1 / Q2A / Q2B / Q3 / Q2C / Q4 / Q5 / Q6 / Q7. Q2 decomposed into Q2A (actual-label source) and Q2B (point-in-time runner). Q2C extends with 7-day after Q3. (7) Live-database discovery: configured PostgreSQL on `localhost:5432` (`c2-pg` Docker container, image `pgvector/pgvector:pg16`) is discoverable and reachable; all 33 public-schema tables report 0 rows; alembic at `0013_rolling_backtest_orch` (0014 and 0015 not applied). `REAL_DATA_COVERAGE_STATUS = NOT_VERIFIED`. `Q1_DATA_COVERAGE_AUDIT_STATUS = PARTIAL`. (8) Missing-window policy frozen to a single canonical rule: an incomplete 7-day window is `INCOMPLETE` and `EXCLUDED_FROM_PEAK_COMPETITION`. The `or partial` wording is removed. (9) Per-quantile single-day peak metrics frozen: `forecast_single_day_peak_date_q`, `forecast_single_day_peak_quantity_kg_q`, the four errors per quantile. (10) Signed and absolute relative errors separated: `cumulative_signed_relative_error` / `cumulative_absolute_relative_error`; `single_day_peak_quantity_signed_relative_error_q` / `single_day_peak_quantity_absolute_relative_error_q`; `sustained_7day_peak_cumulative_signed_relative_error_q` / `sustained_7day_peak_cumulative_absolute_relative_error_q`; plus denominator counts. (11) 3-day/7-day coexistence frozen to additive policy: both fields are present; the policy decides the primary display window, not the field presence. (12) The sign-off section is no longer pre-filled with `ACCEPTED`; the state is `PENDING_RE_REVIEW`. |

---

## §16 Sign-off (to be completed by Charles upon acceptance)

```text
PR103_SLICE_Q1_FIXUP_PENDING_RE_REVIEW
Q1_NOT_YET_ACCEPTED
Q1_P0_FIXUP_APPLIED
DUAL_CUTOFF_MODEL_FROZEN
CURRENT_OUTPUT_GRAIN_RECONCILED
SUSTAINED_7DAY_TARGET_CONTRACT_CORRECTED
REAL_DATA_COVERAGE_STATUS_REPORTED_TRUTHFULLY
ACYCLIC_SLICE_ORDERING_FROZEN
Q2_DESIGN_CAN_START
Q2_IMPLEMENTATION_NOT_READY
Q2_READINESS_BLOCKED_BY_Q1_GAPS
READY_NOT_AUTHORIZED
MERGE_NOT_AUTHORIZED
ISSUE99_REMAINS_OPEN
ISSUE102_REMAINS_OPEN
TASK013_C2_REMAINS_PAUSED
PR101_REMAINS_CLOSED_NOT_MERGED
```

(Charles to amend the above with explicit `ACCEPTED` or `REVISED` markers and post the result as an Issue #102 comment.)
