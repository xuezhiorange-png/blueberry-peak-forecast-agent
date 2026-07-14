# Slice Q1 — Forecast Target and Evaluation Contract

| Field | Value |
|---|---|
| Document ID | `slice-q1-forecast-target-and-evaluation-contract` |
| Document version | v1 (design freeze, no implementation) |
| Document status | `DRAFT — Q1 design-only, awaiting Charles re-review` |
| Tracking Issue | `#102` (OPEN) — `[P0 Epic] Blueberry forecast quality validation and historical backtest loop` |
| Q1 authorization comment | `IC_kwDOS_gTTs8AAAABKDOkiQ` (id `4969440393`) on Issue #102 |
| Working base | `origin/main` at `2e860511dd9279d0aa3c64dd760bea8531fad458` |
| Working branch | `docs/issue-102-slice-q1-forecast-evaluation-contract` |
| Working worktree | `/tmp/issue-102-slice-q1-forecast-evaluation-contract` |
| Companion document | `docs/forecast-quality/slice-q1-data-coverage-audit.md` |
| Q1 implementation | NOT AUTHORIZED in this document |
| Model change | NOT AUTHORIZED in this document |
| Backtest runner implementation | NOT AUTHORIZED in this document |
| Sustained 7-day peak production implementation | NOT AUTHORIZED in this document |
| 3-day production field reinterpretation | NOT AUTHORIZED in this document |
| Naive baseline implementation | NOT AUTHORIZED in this document |
| Ready / merge / Issue closure | NOT AUTHORIZED in this document |
| TASK-013 C2 resumption | NOT AUTHORIZED in this document |

> Q1 is a **design, source-definition, and data-inventory round only**. It freezes the forecast target, the actual-label contract, the evaluation contract, the sustained 7-day peak contract, the 3-day production compatibility audit, and a reproducible data-coverage audit. Q1 does not modify any production code, any test, any Golden, any migration, any schema, any model, any parameter inference, or any persistence path. Q1 is a docs-only round.

---

## §1 Scope and non-scope

### §1.1 In scope

Q1 freezes:

1. the primary forecast target and the distinction among eight physical quantities (`natural_maturity_quantity`, `mature_inventory_quantity`, `harvestable_quantity`, `actual_harvest_quantity`, `unharvested_backlog_quantity`, `arrival_quantity`, `final_corrected_arrival_quantity`, `season_cumulative_quantity`);
2. the canonical actual-label contract, including grain, unit, event date semantics, recorded-at, revised-at, point-in-time visibility, duplicate handling, missing-day handling, late-revision handling, and zero-day handling;
3. the evaluation grain;
4. the full metric contract: daily, cumulative, single-day peak, sustained 7-day peak, quantile calibration, interval width, pinball loss;
5. the sustained 7-day peak contract and the migration boundary from the existing 3-day production contract;
6. a reproducible, aggregate-only data-coverage report.

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

- `docs/forecast-quality/slice-q1-forecast-target-and-evaluation-contract.md` — this document (target, label, metric, peak contract).
- `docs/forecast-quality/slice-q1-data-coverage-audit.md` — the data-coverage audit and 3-day production contract inventory.
- `docs/forecast-quality/slice-q1-decision-table.md` — the explicit decision table required by §12 of the round instruction.

The three documents are mutually consistent and cross-referenced.

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

Q1 is the first slice in the suggested implementation order Q1..Q7 of Issue #102. Q1 is a design and data-inventory slice. Q1 does not implement any backtest runner; that is Q2.

---

## §3 Business core question (frozen)

> Given a farm, a subfarm-or-plot, a variety, a planting area, a forecast season, and a forecast cutoff time, the system must reliably answer:
> - how many kilograms of blueberry can be picked each day in the future;
> - on which date the single-day peak occurs;
> - which future continuous 7-day window has the largest cumulative pick;
> - how large the sustained 7-day cumulative pick is;
> - what the current forecast error is;
> - whether a new model is genuinely more accurate than the previous one.

The Q1 design-freeze answers the design-level question of **what physical quantity** the system is actually answering this core question for. Q1 also freezes the **actual-label** against which the answer is validated.

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

---

## §4 Forecast-object contracts

### §4.1 Eight physical quantities (canonical)

For each `(farm, subfarm_or_plot, variety, season, calendar_date)`, the project distinguishes the following eight physical quantities. Each row below is the frozen Q1 contract; no row is interpreted, computed, or persisted outside this contract.

| # | object_name | business_definition | physical_meaning | unit | grain | event_date_semantics | source_task | schema_path | persistence_table | current_production_status | actual_or_forecast | proxy_or_direct_observation | can_be_primary_label | can_be_feature | point_in_time_visibility | known_limitations |
|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `natural_maturity_quantity` | The model-predicted daily natural maturation of blueberry on the orchard, in the absence of weather and harvest-state effects. | A biological-physical quantity produced by the TASK-008 maturity model. It is not a human-observed quantity. | kg | (farm × subfarm × variety × calendar_date) | the calendar date on which maturation occurs | TASK-008 | `backend/app/agent/schemas.py::ForecastDailyRow.natural_maturity_quantity_kg: DailyQuantiles` | n/a (forecast output, not persisted directly; reconstructed from upstream TASK-008 forecast runs) | `RESOLVED_BY_MERGED_AUTHORITY` for schema; `NOT_VERIFIED` for production use in Q1 scope | forecast | `MODEL_OUTPUT` (not a direct observation; not a proxy for actual harvest) | NO | YES | n/a (forecast) | not an actual-harvest label; do not use for backtest label |
| 2 | `mature_inventory_quantity` | The model-predicted closing mature inventory on a calendar date, after natural maturation and harvest-state update. | A derived state. | kg | same as #1 | the calendar date on which the closing inventory is reported | TASK-008 / TASK-009 | `ForecastDailyRow.closing_mature_inventory_kg: DailyQuantiles` | n/a (forecast output) | `RESOLVED_BY_MERGED_AUTHORITY` for schema; `NOT_VERIFIED` for production use in Q1 scope | forecast | `DERIVED_STATE` | NO | YES (as feature) | n/a (forecast) | derived; cannot be a label |
| 3 | `harvestable_quantity` | The model-predicted daily harvestable quantity (the portion of mature inventory that is operationally ready to be picked). | Currently NOT a first-class schema field in `origin/main`. Q1 explicitly marks this object as `NOT_CURRENTLY_AVAILABLE` as a first-class field. | kg (target unit) | same as #1 | the calendar date | n/a | **NOT in `origin/main` schema** | none | `NOT_CURRENTLY_AVAILABLE` | n/a | n/a (no field) | NO | n/a | n/a | Q2 must decide whether to add a `harvestable_quantity_kg` field or to derive it from `harvested_quantity_kg - unharvested_backlog_kg` |
| 4 | `actual_harvest_quantity` | The user-entered or operator-entered daily quantity of blueberry actually picked at the orchard. This is the primary business target for Q1. | A direct observation. The most reliable source today is `fact_receipt_daily.weight_kg` interpreted as **arrival at the factory**, not pick at the orchard. There is **no first-class `actual_harvest_quantity` table in `origin/main`**. | kg (target unit) | (farm × subfarm × variety × season × harvest_date) | the calendar date on which the pick occurred | n/a (no dedicated table) | **NOT in `origin/main` schema** | `fact_receipt_daily` is the closest first-class fact but it stores **arrival**, not pick. | `SCHEMA_GAP` / `SOURCE_GAP` | actual (intended) | `DIRECT_OBSERVATION` (when a dedicated table exists) / currently **no first-class table** | YES (intended primary label) | NO (label, not feature) | `POINT_IN_TIME_GAP` | Q2 must decide whether (a) to add a dedicated `actual_harvest_daily` table, or (b) to accept `fact_receipt_daily` as a proxy label with explicit `PROXY_LABEL` marking |
| 5 | `unharvested_backlog_quantity` | The model-predicted daily unharvested backlog. | A derived state. | kg | same as #1 | the calendar date | TASK-008 / TASK-009 | `ForecastDailyRow.unharvested_backlog_kg: DailyQuantiles` | n/a (forecast output) | `RESOLVED_BY_MERGED_AUTHORITY` for schema; `NOT_VERIFIED` for production use in Q1 scope | forecast | `DERIVED_STATE` | NO | YES (as feature) | n/a (forecast) | derived; cannot be a label |
| 6 | `arrival_quantity` | The model-predicted daily quantity arriving at the factory gate, before weather correction. | A model output. | kg | (factory × variety × calendar_date) | the calendar date of arrival at the factory gate | TASK-008 / TASK-009 | `ForecastDailyRow.arrival_quantity_kg: DailyQuantiles` | n/a (forecast output) | `RESOLVED_BY_MERGED_AUTHORITY` for schema; `NOT_VERIFIED` for production use in Q1 scope | forecast | `MODEL_OUTPUT` (proxy for actual arrival, not for actual harvest) | NO (not a harvest label) | YES (as feature) | n/a (forecast) | proxy for arrival; not a harvest label |
| 7 | `final_corrected_arrival_quantity` | The model-predicted daily quantity arriving at the factory gate, after weather correction. | A model output. | kg | same as #6 | the calendar date | TASK-009 | `ForecastDailyRow.final_corrected_arrival_quantity_kg: DailyQuantiles` | n/a (forecast output) | `RESOLVED_BY_MERGED_AUTHORITY` for schema; `NOT_VERIFIED` for production use in Q1 scope | forecast | `MODEL_OUTPUT` (proxy for actual arrival, not for actual harvest) | NO | YES (as feature) | n/a (forecast) | corrected proxy; not a harvest label |
| 8 | `season_cumulative_quantity` | The model-predicted or actual cumulative quantity from the season start through the calendar date. | A derived aggregate. | kg | (farm × subfarm × variety × season × calendar_date) | the calendar date through which the cumulative is computed | TASK-008 / TASK-009 (forecast); operator (actual) | **NOT in `origin/main` schema as a first-class field** | none | `NOT_CURRENTLY_AVAILABLE` as a first-class schema field | both | `DERIVED_STATE` (cumulative over daily rows) | YES (actual cumulative is the canonical label for cumulative metrics) | YES (forecast cumulative) | depends on daily row visibility | Q2 must define the season-cumulative schema field |

### §4.2 First-class vs derived

The eight quantities are split into two groups:

- **First-class schema fields on `ForecastDailyRow`**: #1, #2, #5, #6, #7. These are persisted fields of the model output. The Q1 design-freeze treats them as `RESOLVED_BY_MERGED_AUTHORITY` for schema. Their use as features in a backtest is permitted; their use as the actual-harvest label is forbidden.
- **Not first-class in `origin/main`**: #3, #4, #8. `harvestable_quantity` and `actual_harvest_quantity` and `season_cumulative_quantity` are not first-class fields today. Q1 marks them as `NOT_CURRENTLY_AVAILABLE` and proposes Q2 / Q3 design work to define them.

### §4.3 Proxy discipline

Q1 forbids any silent reclassification of a model output as an actual observation. If the project uses `fact_receipt_daily.weight_kg` as a stand-in for the actual harvest label, the design MUST mark it as `PROXY_LABEL` and disclose the proxy in every report that uses it. Q1 does not yet adopt this proxy; the adoption decision is a Q2 / Q3 design question, and the actual-label gap is reported in §12.

### §4.4 The actual-arrival label candidate

`fact_receipt_daily.weight_kg` is the only first-class operator-entered daily fact in `origin/main`. It is bound to a build-run identity and a unique constraint `(build_run_id, season_id, factory_id, receipt_date, farm_key, subfarm_key, variety_id)`, with `CheckConstraint("weight_kg > 0")`. The CHECK excludes zero-receipt days; this means the table cannot directly represent an explicit zero-receipt day (an explicit zero would be a missing row, not a zero row). This structural fact must be reported in the data-coverage audit and is a Q2 / Q3 design input.

---

## §5 Primary forecast target and target-output alignment

### §5.1 Primary business target (frozen)

```
PRIMARY_BUSINESS_TARGET = daily actual harvest quantity in kg
                          at (farm × subfarm_or_plot × variety × calendar_date)
```

This is the Q1 frozen answer to "what is the system trying to predict". The system answers the project's core question by predicting the daily actual harvest quantity at the canonical grain.

### §5.2 Current model primary output (audit result)

The current `origin/main` model output is:

- `ForecastDailyRow` with seven quantity fields: `natural_maturity_quantity_kg`, `harvested_quantity_kg`, `closing_mature_inventory_kg`, `unharvested_backlog_kg`, `arrival_quantity_kg`, `final_corrected_arrival_quantity_kg`, plus `per_variety_contribution: list[VarietyContribution]`, plus `weather_tags`, plus `spring_festival_phase`, plus `agent_daily_row_hash`.
- `ForecastPeakOutput` with `single_day_peak: dict[ForecastQuantile, SingleDayPeakEntry]` and `sustained_3day_peak: dict[ForecastQuantile, SustainedPeakEntry]`, plus `peak_window_cumulative_quantity_kg`, `peak_duration_days`, `high_load_threshold`, `dominant_variety`, `peak_formation_explanation_ref`, `blockers`.
- `ParameterEstimate` with `p50 / p80_lower / p80_upper / source_level / confidence / sample_count / season_count / farm_count / source_observation_ids / prior_version / distribution_kind / citation`.

```
CURRENT_MODEL_PRIMARY_OUTPUT = forecast_daily_row with seven quantity fields per (farm × subfarm × variety × calendar_date),
                              each with DailyQuantiles (p50 / p80 / p90),
                              plus single-day peak and sustained-3-day peak per quantile,
                              plus ParameterEstimate at the (parameter_name, variety_id) grain.
```

### §5.3 Target-output alignment

```
TARGET_OUTPUT_ALIGNMENT = NOT_PROVEN_EQUIVALENT
```

The current model output is NOT proven equivalent to the primary business target. The `harvested_quantity_kg` field on `ForecastDailyRow` is a model output, not an actual-harvest observation. The actual-harvest quantity is not yet a first-class schema field in `origin/main`. The design does not contain a documented, audit-traceable mapping from the model output to the primary business target.

Q1 marks this as `NOT_PROVEN_EQUIVALENT` and `TARGET_OUTPUT_ALIGNMENT_GAP`. The mapping is a Q2 / Q3 / Q5 design question and is part of the model-improvement acceptance gate.

### §5.4 What "NOT_PROVEN_EQUIVALENT" forbids

Until the alignment is proven, Q1 forbids:

- using `harvested_quantity_kg` as a stand-in for `actual_harvest_quantity` in a backtest label;
- using `fact_receipt_daily.weight_kg` as a stand-in for `actual_harvest_quantity` in a backtest label without a `PROXY_LABEL` disclosure;
- reporting any "forecast accuracy" against a quantity that is not the primary business target;
- reporting any "model improvement" without a before-and-after comparison on the same target.

---

## §6 Actual-label contract

### §6.1 Canonical grain (target)

```
DESIRED_GRAIN = (farm_id, subfarm_or_plot_id, variety_id, forecast_season_id, harvest_date)
```

The actual-harvest label, when adopted, will be defined at this grain.

### §6.2 Supported grain (audit result on `origin/main`)

The closest first-class operator-entered fact today is `fact_receipt_daily` with grain:

```
SUPPORTED_GRAIN = (build_run_id, season_id, factory_id, receipt_date, farm_key, subfarm_key, variety_id)
```

The supported grain is at the receipt / factory level, not at the orchard / subfarm level. `farm_key` and `subfarm_key` are recorded as foreign keys / values, but `weight_kg > 0` is enforced by CHECK, so explicit zero-receipt days are structurally excluded. There is no dedicated `actual_harvest_daily` table. There is no `subfarm_or_plot_id` table in the public dim set; the closest is `dim_subfarm` and `dim_farm`.

```
SUPPORTED_GRAIN = (build_run_id, season_id, factory_id, receipt_date, farm_key, subfarm_key, variety_id, weight_kg > 0)
DESIRED_GRAIN  = (farm_id, subfarm_or_plot_id, variety_id, forecast_season_id, harvest_date, actual_harvest_quantity_kg)
GRAIN_GAP       = YES (no dedicated actual_harvest_daily table; fact_receipt_daily is receipt not pick; explicit zero missing)
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
- `REVISION_HISTORY_GAP` — `fact_receipt_daily` is bound to a `build_run_id`; the build-run sequence is the only revision mechanism. This is a re-build mechanism, not a row-level revision. Q2 / Q3 design must decide whether to keep the build-run model or to introduce row-level revision.

### §6.5 Point-in-time visibility contract

For a backtest at forecast cutoff `T`, the actual-label query MUST return only rows that satisfy:

- `recorded_at <= T`
- `effective_at <= T`
- the row is visible at `T` (no future-recorded correction supersedes it at `T`)
- the row is not `is_deleted_or_voided`

The query MUST NOT return:

- rows with `recorded_at > T` (late-arriving records);
- rows with `effective_at > T` (effective date in the future);
- the latest `supersedes` value (the `current_data` / `latest` / `most_recent` fallback is forbidden);
- post-cutoff corrections;
- post-cutoff management events;
- target-date-after data.

The contract is identical to the `replay_trained_filtering.py` rules for training data; the same rules apply to the actual-label query.

### §6.6 Special-day semantics

| Concept | Definition | Distinguishing property |
|---|---|---|
| `late_arriving_record` | a row whose `recorded_at > harvest_date` | reported separately; never silently used as if `recorded_at = harvest_date` |
| `correction` | a row whose `supersedes_record_id` is non-null | a later revision of an earlier row; the earlier row remains valid for `recorded_at < correction.recorded_at` |
| `void` | a row whose `is_deleted_or_voided = true` | excluded from backtest, regardless of `recorded_at` |
| `duplicate` | two rows with the same canonical-grain identity and overlapping effective window | resolved by `recorded_at` and `revision_number`; never silently merged |
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
- point-in-time visibility is verifiable for the chosen forecast-cutoff `T`;
- forecast cutoff `T` is bindable to a specific replay identity;
- at least one full 7-day target window is present;
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

The sustained peak window is fixed to **7 consecutive calendar days**. For a forecast target object (one of the eight objects in §4) and a quantile `q ∈ {P50, P80, P90}`:

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

### §7.3 Boundary semantics (frozen)

| Boundary | Rule |
|---|---|
| forecast horizon < 7 full calendar days | `NOT_COMPUTABLE` |
| any window contains a `missing_day` | not auto-filled with 0; the window is `NOT_COMPUTABLE` (or the metric policy reports the window as `partial` with a documented handling rule) |
| explicit `zero_harvest_day` | can be used as 0 in the sum |
| duplicate dates | resolved by the actual-label revision contract; the later `recorded_at` wins |
| multiple same-value windows | `EARLIEST_START_DATE` wins |
| negative quantity | `INVALID`; the run fails closed |
| unit | all quantities in kg |
| rounding order | sum the raw `Decimal` values first, then apply the metric-policy `quantize`; never round the daily values before the sum |
| forecast-vs-actual | both actual and forecast use the same window algorithm and the same tie-break |

### §7.4 Separation of forecast horizon and sustained peak window

Two distinct dimensions. The Q1 design-freeze treats them as disjoint concepts:

- `FORECAST_HORIZON_DAYS ∈ {7, 14, 21}` — distance from forecast generation to the forecast target date.
- `SUSTAINED_PEAK_WINDOW_DAYS = 7` — fixed rolling-window length for the cumulative peak.

Q1 forbids naming, documentation, or test-plan conventions that conflate the two. The forecast-horizon breakdown is a metric report dimension; the sustained-peak window is a quantity contract.

### §7.5 Pre-window summation rule

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

### §8.3 7-day migration boundary (design only, not implemented in Q1)

The 7-day migration is a separate design and implementation round. Q1 freezes the migration boundary but does not implement it. The migration design is:

- A new `sustained_7day_peak: dict[ForecastQuantile, SustainedPeakEntry]` field is added to `ForecastPeakOutput` (or a new `ForecastPeakOutputV2` schema version).
- The new field uses the existing `SustainedPeakEntry` schema, which already has `start_date`, `end_date`, `rolling_daily_average_kg_per_day`, `cumulative_quantity_kg`. No new field shape is required.
- The new field is gated by a `sustained_peak_window_version: Literal["3day-v1", "7day-v1"]` policy field; the output contains the field for the active version only.
- The 3-day field is preserved as a deprecation field with a defined sunset window.
- The Golden migration is explicit: both fields are emitted during the deprecation window; the Golden contains both 3-day and 7-day fields; the test plan includes both 3-day and 7-day assertions during the deprecation window.
- The API migration is explicit: the API returns both 3-day and 7-day fields during the deprecation window; the consumer chooses one based on the policy version.
- The 3-day field is not renamed; the 3-day field is not reinterpreted; the 3-day field is not deleted; the 3-day field is not aliased to the 7-day field.

```
7DAY_MIGRATION_REQUIRED = YES (separate design and implementation round, not in Q1)
SUSTAINED_7DAY_IMPLEMENTED = NO
7DAY_TARGET_CONTRACT_FROZEN = YES (this document §7)
```

### §8.4 Forbidden silent 3-day → 7-day reinterpretation

Q1 forbids:

- renaming `sustained_3day_peak` to `sustained_7day_peak` without an additive migration;
- changing the meaning of `sustained_window_days = 3` to `7` without a versioned policy field;
- aliasing `peak_window_cumulative_quantity_kg` to a 7-day window without a new field;
- changing the Golden's 3-day value to a 7-day value;
- changing the test assertion from "sustained_3day_peak" to "sustained_7day_peak" without a deprecation window.

### §8.5 3-day production semantics preserved

The 3-day field continues to mean "the maximum rolling 3-day arithmetic mean / cumulative quantity of the forecast at the quantile". The 7-day field, when added, will mean "the maximum rolling 7-day arithmetic mean / cumulative quantity". The two fields are independent and additive.

---

## §9 Evaluation metric contract

### §9.1 Evaluation grain (frozen)

All metrics in this section use the same evaluation slice:

```
EVALUATION_GRAIN = (farm_id, subfarm_or_plot_id, variety_id, season_id, forecast_cutoff, forecast_target_date, forecast_horizon_days, model_version, data_snapshot)
```

`forecast_horizon_days ∈ {7, 14, 21}`. The Q1 design-freeze does not restrict the horizon to a single value; the metrics are reported per horizon.

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

### §9.3 Cumulative metrics (frozen)

| Metric | Definition | Notes |
|---|---|---|
| `season_cumulative_actual_kg` | `sum(actual)` from season start through the last day in the slice | unit: kg |
| `season_cumulative_forecast_kg` | `sum(forecast_p50)` from season start through the last day in the slice | unit: kg |
| `cumulative_absolute_error_kg` | `abs(season_cumulative_forecast_kg - season_cumulative_actual_kg)` | unit: kg |
| `cumulative_relative_error` | `(season_cumulative_forecast_kg - season_cumulative_actual_kg) / season_cumulative_actual_kg` | unit: fraction; if `season_cumulative_actual_kg = 0` → `NOT_COMPUTABLE` |

### §9.4 Single-day peak metrics (frozen)

| Metric | Definition | Notes |
|---|---|---|
| `actual_single_day_peak_date` | the calendar date of the maximum actual daily value in the season | tie-break: `EARLIEST_DATE` |
| `actual_single_day_peak_quantity_kg` | the maximum actual daily value in the season | unit: kg |
| `forecast_single_day_peak_date` | the calendar date of the maximum forecast `forecast_p50` daily value in the season | tie-break: `EARLIEST_DATE` |
| `forecast_single_day_peak_quantity_kg` | the maximum forecast `forecast_p50` daily value in the season | unit: kg |
| `single_day_peak_date_signed_error_days` | `forecast_single_day_peak_date - actual_single_day_peak_date` | positive → forecast peak is later than actual; negative → earlier |
| `single_day_peak_date_absolute_error_days` | `abs(single_day_peak_date_signed_error_days)` | unit: days |
| `single_day_peak_quantity_absolute_error_kg` | `abs(forecast_single_day_peak_quantity_kg - actual_single_day_peak_quantity_kg)` | unit: kg |
| `single_day_peak_quantity_relative_error` | `(forecast - actual) / actual` | unit: fraction; if `actual = 0` → `NOT_COMPUTABLE` |

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
| `sustained_7day_peak_start_date_signed_error_days_q` | `forecast - actual` for the start date | positive → forecast peak is later |
| `sustained_7day_peak_start_date_absolute_error_days_q` | `abs(signed_error_days)` | unit: days |
| `sustained_7day_peak_cumulative_absolute_error_kg_q` | `abs(forecast_cumulative - actual_cumulative)` | unit: kg |
| `sustained_7day_peak_cumulative_relative_error_q` | `(forecast - actual) / actual` | if `actual = 0` → `NOT_COMPUTABLE` |
| `sustained_7day_peak_daily_average_absolute_error_kg_per_day_q` | `abs(forecast_daily_average - actual_daily_average)` | unit: kg / day |

### §9.6 Quantile calibration (frozen)

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
P50_SEMANTICS = PENDING_VERIFICATION (Q2 / Q5 must verify on origin/main)
P80_SEMANTICS = PENDING_VERIFICATION
P90_SEMANTICS = PENDING_VERIFICATION
QUANTILE_COVERAGE_STATUS = PENDING_VERIFICATION
P80_P90_SEMANTICS_STATUS = PENDING_VERIFICATION
```

### §9.7 Interval width (frozen)

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

### §9.8 Pinball loss (frozen, definition only)

For a quantile `q ∈ (0, 1)`, an actual value `a`, and a forecast value `f_q`:

```
pinball_loss(q, a, f_q) =
    max( q * (a - f_q), (q - 1) * (a - f_q) )
```

Q1 freezes the definition. The Q2 / Q5 design must:

- verify that P50, P80, P90 are true quantiles (not point estimates or interval labels);
- if verified, define `pinball_loss_p50`, `pinball_loss_p80`, `pinball_loss_p90` as Q1 frozen functions of `pinball_loss`;
- if not verified, mark the metric as `QUANTILE_SEMANTICS_NOT_VERIFIED` and `PINBALL_LOSS_NOT_COMPUTABLE`.

### §9.9 Forbidden metric patterns

- "Tests pass" is not a substitute for a forecast-accuracy metric.
- `forecast - actual` (a single difference) is not a metric; metrics are aggregates over rows.
- `mean(forecast - actual)` is the bias; `mean(abs(forecast - actual))` is the MAE; conflating the two is a metric-pattern error.
- Using a single `mape` to summarize is forbidden; the metric must report `mape_eligible_row_count`, `zero_actual_row_count`, `excluded_row_count`.
- Using a `epsilon` to avoid `0 / 0` in MAPE is forbidden; the metric must explicitly handle the zero case and report the row count.
- Using `forecast_p90 - forecast_p50` as the prediction interval width is forbidden.

---

## §10 Data coverage audit (read-only, see companion document)

The full data-coverage audit, including the 3-day production contract inventory, the actual-label grain audit, the harvest-state schema audit, the migration-history audit, and the table-inventory audit, is in `docs/forecast-quality/slice-q1-data-coverage-audit.md`. This document is the single source of truth for the read-only data audit.

Q1 does not access a live database, a staging database, a local development database, or any fixture. Q1 reports the data-coverage status as `BLOCKED_BY_DATA` (no live database access in this round) for all rows that require a live database to populate. Q1 does not fabricate real-data coverage; Q1 reports the gap explicitly.

```
REAL_DATA_COVERAGE_STATUS = BLOCKED_BY_DATA (this round is docs-only; no live database access)
```

---

## §11 Decision table (per round §12)

The Q1 decision table is in `docs/forecast-quality/slice-q1-decision-table.md`. The table is reproduced here for convenience:

| Decision | Value |
|---|---|
| `PRIMARY_BUSINESS_TARGET` | `daily actual harvest quantity in kg at (farm × subfarm_or_plot × variety × calendar_date)` |
| `CURRENT_MODEL_PRIMARY_OUTPUT` | `ForecastDailyRow with seven quantity fields per (farm × subfarm × variety × calendar_date), each with DailyQuantiles (p50 / p80 / p90), plus single-day peak and sustained-3-day peak per quantile, plus ParameterEstimate at (parameter_name, variety_id)` |
| `TARGET_OUTPUT_ALIGNMENT` | `NOT_PROVEN_EQUIVALENT` |
| `ACTUAL_LABEL_STATUS` | `SCHEMA_GAP / SOURCE_GAP / POINT_IN_TIME_GAP / REVISION_HISTORY_GAP` |
| `ACTUAL_LABEL_SUPPORTED_GRAIN` | `fact_receipt_daily at (build_run_id, season_id, factory_id, receipt_date, farm_key, subfarm_key, variety_id, weight_kg > 0) — receipt, not pick` |
| `POINT_IN_TIME_STATUS` | `GAP (no first-class actual_harvest_daily table; fact_receipt_daily lacks recorded_at, effective_at, revised_at; build_run_id is re-build only, not row-level revision)` |
| `P50_SEMANTICS` | `PENDING_VERIFICATION` |
| `P80_SEMANTICS` | `PENDING_VERIFICATION` |
| `P90_SEMANTICS` | `PENDING_VERIFICATION` |
| `QUANTILE_COVERAGE_STATUS` | `PENDING_VERIFICATION` |
| `SUSTAINED_7DAY_PEAK_CONTRACT` | `FROZEN (definition only, no implementation in Q1)` |
| `CURRENT_3DAY_CONTRACT_STATUS` | `CURRENT_PRODUCTION_CONTRACT` |
| `7DAY_MIGRATION_REQUIRED` | `YES (separate design and implementation round, not in Q1)` |
| `REAL_DATA_COVERAGE_STATUS` | `BLOCKED_BY_DATA (this round is docs-only; no live database access)` |
| `Q2_READINESS` | `READY (Q1 freeze is complete; Q2 design and implementation requires separate Charles authorization)` |

---

## §12 Subsequent slice recommendations (Q1 does NOT implement)

Q1 recommends the following slice ordering, all of which require separate Charles authorization:

### §12.1 Slice Q2 — point-in-time backtest runner

The Q2 design and implementation depends on the Q1 contract. The Q2 minimum entry conditions are:

1. The Q1 design-freeze is accepted by Charles.
2. The actual-label question is resolved: either (a) a dedicated `actual_harvest_daily` table is added, or (b) `fact_receipt_daily` is accepted as a proxy with explicit `PROXY_LABEL` disclosure.
3. The quantile semantics on `origin/main` are verified (P50, P80, P90 are true quantiles or not).
4. The replay identity is accepted as the binding identity for forecast-cutoff.
5. The 7-day peak is added as an additive field with a deprecation window for the 3-day field (or a separate round).

The Q2 deliverables are:

- point-in-time backtest runner that consumes the actual-label contract, the forecast-output contract, the replay identity, and the metric contract;
- multi-farm, multi-variety, multi-season coverage;
- 7 / 14 / 21-day horizon breakdown;
- `previous_model` and `naive_baseline` comparators (the comparators are part of Q2 because they need a backtest runner to operate);
- PostgreSQL production-chain acceptance.

### §12.2 Slice Q3 — sustained 7-day peak migration

The Q3 design and implementation depends on the Q1 contract. The Q3 minimum entry conditions are:

1. The Q1 design-freeze is accepted by Charles.
2. The 7-day peak contract is accepted by Charles.
3. The additive 3-day / 7-day field coexistence policy is decided.
4. The Golden migration plan is decided.
5. The API migration plan is decided.

The Q3 deliverables are:

- a new `sustained_7day_peak` field on `ForecastPeakOutput` (or a versioned V2);
- a `sustained_peak_window_version: Literal["3day-v1", "7day-v1"]` policy field;
- the Golden migration (both fields during the deprecation window);
- the API migration (both fields during the deprecation window);
- the PostgreSQL production-chain acceptance.

### §12.3 Slice Q4 — naive baseline

Q4 depends on the Q2 backtest runner. The Q4 minimum entry condition is Q2 acceptance. The Q4 deliverable is at least one repeatable naive baseline (for example, "previous-season same-relative-day" or "area × historical yield curve"), compared with the current model on the same data, the same cutoff, the same actual label, the same metric, and the same 7-day peak definition.

### §12.4 Slice Q5 — forecast quality report

Q5 depends on Q2 and Q3. The Q5 minimum entry conditions are Q2 acceptance and Q3 acceptance. The Q5 deliverables are the report rows in §12 of Issue #102.

### §12.5 Slice Q6 — model improvement

Q6 depends on Q1..Q5. The Q6 minimum entry conditions are Q1..Q5 acceptance. The Q6 deliverable is at least one model change that improves the metric deltas in §3 of Issue #102. Q6 is gated by the slice-Q5 forecast-quality report.

### §12.6 Slice Q7 — thin trial UI

Q7 depends on Q1..Q5. The Q7 minimum entry conditions are Q1..Q5 acceptance. The Q7 deliverables are the two pages (forecast page, forecast-vs-actual page) with CSV / Excel import-export.

---

## §13 Forbidden actions in Q1

Q1 forbids the following actions in this round. Each forbidden action is paired with the rationale and the verification check.

| Forbidden action | Rationale | Verification check |
|---|---|---|
| modify any production code under `backend/app/**` | Q1 is docs-only | `git diff --name-only origin/main` excludes `backend/app/` |
| modify any test under `backend/tests/**` | Q1 is docs-only | `git diff --name-only origin/main` excludes `backend/tests/` |
| add or modify any migration under `backend/alembic/**` | Q1 freezes the contract; it does not implement | `git diff --name-only origin/main` excludes `backend/alembic/` |
| modify any Golden file | Q1 freezes the contract; it does not change Goldens | `git diff --name-only origin/main` excludes any `golden/` |
| modify any frontend, dependency, or workflow | Q1 is docs-only | `git diff --name-only origin/main` excludes `frontend/`, `.github/`, dependency files |
| implement the 7-day peak production code | Q1 freezes the contract; Q3 implements | the new commit does not add any `sustained_7day_peak` field to `backend/app/agent/schemas.py` |
| implement the backtest runner | Q1 freezes the contract; Q2 implements | the new commit does not add any backtest runner file |
| implement the naive baseline | Q1 freezes the contract; Q4 implements | the new commit does not add any baseline file |
| silently rename `sustained_3day_peak` to `sustained_7day_peak` | Q1 forbids silent reinterpretation | the new commit does not modify the 3-day field semantics |
| close Issue #99 | Issue #99 remains open for the P0 mainline | `gh issue view 99 --json state` is `OPEN` |
| close Issue #102 | Issue #102 remains open for Q1 acceptance and subsequent slices | `gh issue view 102 --json state` is `OPEN` |
| re-open PR #101 | PR #101 is closed without merge | `gh pr view 101 --json state` is `CLOSED` |
| re-start TASK-013 C2 | TASK-013 C2 is paused | no commit on the PR #101 branch |
| mark the PR Draft as Ready | Q1 only authorizes a Draft PR | the Draft PR is in `OPEN / Draft / NOT MERGED` state |
| merge the PR | Q1 only authorizes a Draft PR | the PR is not merged |
| delete the PR branch | Q1 only authorizes a Draft PR | the branch is preserved |
| delete the PR worktree | Q1 only authorizes a Draft PR | the worktree is preserved |
| delete any untracked file | Q1 only authorizes a Draft PR | the 4 untracked files in the main worktree are preserved |
| output sensitive real business data | Q1 forbids real-data output | the data-coverage audit reports `BLOCKED_BY_DATA` for live-database access |
| claim the 7-day peak is implemented | Q1 only freezes the contract | the report explicitly states `SUSTAINED_7DAY_IMPLEMENTED = NO` |
| claim the forecast accuracy has improved | Q1 does not change any model | the report explicitly states `MODEL_CHANGE_NOT_AUTHORIZED` |

---

## §14 Validation checklist (against round §14)

Q1 ran the following validation checks:

1. `git diff --check` — clean.
2. `git diff --name-only origin/main` — only `docs/forecast-quality/` files.
3. forbidden-files exact set — empty (no `backend/`, `alembic/`, `frontend/`, `.github/`, dependency, Golden, fixture, or database file modified).
4. no backend changes — verified by `git diff --name-only origin/main -- backend/`.
5. no frontend changes — verified by `git diff --name-only origin/main -- frontend/`.
6. no test changes — verified by `git diff --name-only origin/main -- backend/tests/`.
7. no migration changes — verified by `git diff --name-only origin/main -- backend/alembic/`.
8. no workflow changes — verified by `git diff --name-only origin/main -- .github/`.
9. no Golden changes — verified by `git diff --name-only origin/main -- '**/golden/**'`.
10. all documented production fields verified against `origin/main` — the 8 physical quantities in §4 and the 3-day production contract in §8.1 are sourced from `git show origin/main:backend/app/agent/schemas.py` and the model files; no field is invented.
11. all 3-day contract references inventoried — see `docs/forecast-quality/slice-q1-data-coverage-audit.md` §B for the full count and the file-by-file mapping.
12. no silent 3-day-to-7-day reinterpretation — verified by the explicit policy in §8.4 and the absence of any commit that renames the 3-day field.
13. no claim that 7-day is implemented — the report explicitly states `SUSTAINED_7DAY_IMPLEMENTED = NO`.
14. no claim that forecast accuracy improved — the report explicitly states `MODEL_CHANGE_NOT_AUTHORIZED`.
15. no fabricated real-data coverage — the report explicitly states `REAL_DATA_COVERAGE_STATUS = BLOCKED_BY_DATA`.
16. internal Markdown links valid — every `(\#…)` anchor is verified by the Q1 author and matches a section heading in the same document or in the companion document.
17. document line counts — reported in the final report.
18. document SHA-256 — reported in the final report.
19. data-audit report SHA-256 — reported in the final report.
20. Issue #102 body formatting verification — `e1a17ac7...` (before) → `d6ee055c...` (after); only the outer fence removed; 167 lines of substantive content unchanged.

---

## §15 Change log

| Date | Round | Author | Change |
|---|---|---|---|
| 2026-07-14 | v1 (Q1) | Charles-authorized Q1 design-only round | Initial creation. Frozen forecast-object contract (8 objects). Frozen actual-label contract (canonical grain, canonical fields, point-in-time visibility, special-day semantics). Frozen sustained 7-day peak contract (definition, output fields, boundary semantics, separation from forecast horizon). Frozen evaluation metric contract (daily, cumulative, single-day peak, sustained 7-day peak, quantile calibration, interval width, pinball loss). 3-day production contract audited and preserved verbatim. Data-coverage audit reports `BLOCKED_BY_DATA`. Q2 / Q3 / Q4 / Q5 / Q6 / Q7 minimum entry conditions and deliverables specified. |

---

## §16 Sign-off (to be completed by Charles upon acceptance)

```text
SLICE_Q1_DESIGN_AND_DATA_AUDIT_ACCEPTED
PRIMARY_FORECAST_TARGET_FROZEN
ACTUAL_LABEL_CONTRACT_FROZEN
SUSTAINED_7DAY_PEAK_CONTRACT_FROZEN
EVALUATION_METRIC_CONTRACT_FROZEN
CURRENT_3DAY_PRODUCTION_CONTRACT_PRESERVED
REAL_DATA_COVERAGE_BLOCKED_BY_DATA
Q2_READY_FOR_DESIGN
Q3_READY_FOR_DESIGN
Q4_PENDING_Q2
Q5_PENDING_Q2_AND_Q3
Q6_PENDING_Q1_THROUGH_Q5
Q7_PENDING_Q1_THROUGH_Q5
READY_NOT_AUTHORIZED
MERGE_NOT_AUTHORIZED
ISSUE102_REMAINS_OPEN
TASK013_C2_REMAINS_PAUSED
```

(Charles to amend the above with explicit `ACCEPTED` or `REVISED` markers and post the result as an Issue #102 comment.)
