# Slice Q1 — Forecast Target and Evaluation Contract

| Field | Value |
|---|---|
| Document ID | `slice-q1-forecast-target-and-evaluation-contract` |
| Document version | v1.2 (Q1 final contract docs-only fixup per review 4695151631) |
| Document status | `DRAFT — Q1 final fixup applied, awaiting Charles re-review` |
| Tracking Issue | `#102` (OPEN) — `[P0 Epic] Blueberry forecast quality validation and historical backtest loop` |
| Q1 authorization comment | `IC_kwDOS_gTTs8AAAABKDOkiQ` (id `4969440393`) on Issue #102 |
| Q1 P0 fixup review | `4694771522` (verdict `PR103_SLICE_Q1_REVIEW_P0_FIXUP_REQUIRED`) |
| Q1 final review | `4695151631` (verdict `PR103_SLICE_Q1_P0_FIXUP_MAJORITY_CLOSED` + `FINAL_CONTRACT_FIXUP_REQUIRED`) |
| Working base | `origin/main` at `2e860511dd9279d0aa3c64dd760bea8531fad458` |
| Working branch | `docs/issue-102-slice-q1-forecast-evaluation-contract` |
| Working worktree | `/tmp/issue-102-slice-q1-forecast-evaluation-contract` |
| Companion documents | `docs/forecast-quality/slice-q1-data-coverage-audit.md`; `docs/forecast-quality/slice-q1-decision-table.md` |
| Q1 implementation | NOT AUTHORIZED in this document |
| Q2A / Q2B / Q3 / Q4 / Q5 / Q6 / Q7 | NOT AUTHORIZED in this document |
| Model change | NOT AUTHORIZED in this document |
| Backtest runner implementation | NOT AUTHORIZED in this document |
| Sustained 7-day peak production implementation | NOT AUTHORIZED in this document |
| 3-day production field reinterpretation | NOT AUTHORIZED in this document |
| Naive baseline implementation | NOT AUTHORIZED in this document |
| Ready / merge / Issue closure | NOT AUTHORIZED in this document |
| TASK-013 C2 resumption | NOT AUTHORIZED in this document |

> Q1 v1.2 is a final docs-only fixup on the same branch and PR #103. v1.2 does not introduce any new mutation; v1.2 only corrects four contract contradictions (P0-1..4) and two compatibility-policy issues (P1-1, P1-2) identified by review `4695151631`. v1.2 preserves all v1.1 P0 fixes (dual-cutoff, six-field inventory, aggregate grain, etc.) and adds the final unified decision table per round §十一.

---

## §1 Scope and non-scope

### §1.1 In scope

Q1 freezes:

1. the primary forecast target and the distinction among eight physical quantities (`natural_maturity_quantity`, `mature_inventory_quantity`, `harvestable_quantity`, `actual_harvest_quantity`, `unharvested_backlog_quantity`, `arrival_quantity`, `final_corrected_arrival_quantity`, `season_cumulative_quantity`);
2. the **dual time-cutoff model** (`forecast_cutoff_at` gates model inputs; `label_observation_cutoff_at` gates actual-label revision visibility for evaluation);
3. the historical-replay time model: `forecast_cutoff_at < forecast_target_date_or_window_end <= label_observation_cutoff_at <= replay_executed_at`;
4. the canonical actual-label contract, including grain, unit, event date semantics, recorded-at, revised-at, point-in-time visibility, duplicate handling, missing-day handling, late-revision handling, zero-day handling, and the **fail-closed revision-lineage policy** (unique visible terminal revision on one explicit supersession chain);
5. the evaluation grain;
6. the full metric contract: daily, cumulative, single-day peak, sustained 7-day peak, quantile calibration, interval width, pinball loss, with explicit signed/absolute relative-error separation;
7. the sustained 7-day peak contract and the **3-day = legacy compatibility / 7-day = primary business target** compatibility policy;
8. a reproducible, aggregate-only data-coverage report (with truthful `NOT_VERIFIED` reporting when a reachable database has no data).

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
18. Any silent promotion of `fact_receipt_daily` (arrival / receipt) to the `actual_harvest_quantity` (orchard pick) primary label. The arrival proxy is a `DESIGN_OPTION` for arrival evaluation, not a primary-label backstop.
19. Any claim that the 3-day production metric is the first-stage primary sustained metric. The 3-day metric is a `LEGACY_COMPATIBILITY_METRIC` only; the primary sustained metric is the 7-day peak, which is `NOT_YET_COMPUTABLE` until Q3 + Q2C.
20. Any future deletion of the 3-day production field without a separate compatibility amendment. Q1 freezes `THREE_DAY_RETENTION_STATUS = PRESERVED_FOR_CURRENT_COMPATIBILITY_HORIZON` and `THREE_DAY_REMOVAL = REQUIRES_SEPARATE_COMPATIBILITY_AMENDMENT`.

### §1.3 Companion documents

- `docs/forecast-quality/slice-q1-forecast-target-and-evaluation-contract.md` — this document (target, label, dual-cutoff, historical-replay time model, fail-closed revision lineage, metric, peak contract).
- `docs/forecast-quality/slice-q1-data-coverage-audit.md` — the data-coverage audit and 3-day production contract inventory.
- `docs/forecast-quality/slice-q1-decision-table.md` — the explicit decision table required by round §十二.

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

The Q1 design-freeze answers the design-level question of **what physical quantity** the system is actually answering this core question for, **at what time the answer is generated**, **at what later time the answer is scored**, and **at what time the actual-label revision is visible to the evaluator**. Q1 also freezes the **actual-label** against which the answer is validated, and the **two independent time cutoffs** that gate model input visibility and label visibility respectively.

### §3.1 Hard exclusion of proxy-conflation

The system MUST NOT silently treat any of the following as a synonym for "actual harvest":

- `natural_maturity_quantity_kg` (model output of natural maturation);
- `closing_mature_inventory_kg` (model state);
- `unharvested_backlog_kg` (model state);
- `arrival_quantity_kg` (model output of arrival before weather correction);
- `final_corrected_arrival_quantity_kg` (model output of arrival after weather correction);
- `harvested_quantity_kg` on `ForecastDailyRow` (model output, not a user-entered actual);
- any `fact_receipt_daily.weight_kg` (operator-entered receipt / arrival at the factory, not the pick at the orchard).

If the system uses a proxy as a stand-in for the actual label, the proxy MUST be marked as such, and the Q1 design-freeze classifies each candidate below. In particular, the `fact_receipt_daily` proxy is `ARRIVAL_PROXY_EVALUATION_ALLOWED = DESIGN_OPTION` for arrival evaluation; it is NOT the primary `actual_harvest_quantity` label.

### §3.2 Hard exclusion of dual-cutoff conflation

The system MUST NOT use a single time cutoff for both model input visibility and actual-label visibility for scoring. The two time cutoffs are independent; they are defined separately in §4. The single-cutoff conflation would make the backtest structurally unable to score future forecasts (the future target date has not yet occurred at the forecast cutoff). Q1 freezes the two-cutoff model as the only correct anti-leakage boundary.

---

## §4 Dual time-cutoff model (frozen per review 4694771522 P0-1, preserved in v1.2)

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

### §4.3 Canonical time order (frozen per review 4695151631 P0-1)

The four time boundaries are independent. Q1 freezes the canonical time order:

```
forecast_cutoff_at
< forecast_target_date_or_window_end
<= label_observation_cutoff_at
<= replay_executed_at
```

Definitions:

- `forecast_cutoff_at` — the simulated historical forecast generation time; the model is permitted to see information up to this point.
- `forecast_target_date_or_window_end` — the calendar date (or end of a continuous window) being predicted.
- `label_observation_cutoff_at` — the label visibility boundary for evaluation; the evaluator is permitted to see label revisions up to this point.
- `replay_executed_at` — the actual execution timestamp of the historical replay task. The replay may run today (`replay_executed_at = today`), but the simulated `forecast_cutoff_at` MUST remain a historical timestamp; the replay MUST NOT be allowed to push `forecast_cutoff_at` forward to the target date.

For the four time-pattern templates (future forecast, same-day forecast, historical replay, final adjudicated), Q1 freezes the following:

| Pattern | Time order |
|---|---|
| future forecast | `forecast_cutoff_at < forecast_target_date_or_window_end <= label_observation_cutoff_at <= replay_executed_at` |
| same-day forecast | `forecast_target_local_date = local_date(forecast_cutoff_at, farm_timezone)`; the local-day boundary and the timezone are part of the contract; cutoff-after data is forbidden as a model input; actual label can be evaluated at a later `label_observation_cutoff_at` |
| historical replay | `forecast_target_date_or_window_end <= label_observation_cutoff_at <= replay_executed_at`; the simulated `forecast_cutoff_at` is historical; the replay executes today |
| final adjudicated | `forecast_target_date_or_window_end <= finalized_at <= label_observation_cutoff_at <= replay_executed_at`; if `finalized_at = label_observation_cutoff_at`, this is recorded explicitly |

The earlier v1.1 wording `forecast_target_date < forecast_cutoff_at (in-simulation)` is **removed**. The earlier v1.1 wording `forecast_target_date = forecast_cutoff_at` is **removed**. The new wording is `forecast_target_local_date = local_date(forecast_cutoff_at, farm_timezone)`, which uses an aware datetime and an explicit timezone conversion, not a direct `date` comparison.

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

### §4.5 Revision lineage policy (frozen per review 4695151631 P0-2)

#### §4.5.1 Canonical rule

The valid winner is the **unique visible terminal revision on one valid explicit supersession chain** within the same source family. Specifically:

```
candidate revisions =
    revisions visible at label_observation_cutoff_at
    within one explicit source-family supersession graph

winner =
    the unique visible terminal revision
    on one valid explicit supersession chain
```

#### §4.5.2 Field roles (frozen)

| Field | Allowed role | Disallowed role |
|---|---|---|
| `recorded_at` | visibility: whether the revision is visible at `label_observation_cutoff_at` | winner selection |
| `revision_number` | chain-continuity validation within one supersession chain | winner selection |
| `supersedes_record_id` | building the explicit parent-child relationship | winner selection |

None of these fields may determine the winner alone. A winner is selected only when one valid explicit supersession chain has a unique visible terminal revision.

#### §4.5.3 Fail-closed conditions (frozen)

The following conditions MUST block the evaluation and report a typed `Blocker`:

| Condition | `Blocker.code` |
|---|---|
| multiple visible terminal revisions on the same supersession chain | `MULTIPLE_VISIBLE_TERMINAL_REVISIONS` |
| the supersession graph has a fork (one parent with multiple children) | `SUPERSESSION_CHAIN_FORK` |
| the supersession graph has a cycle (A → B → A) | `SUPERSESSION_CHAIN_CYCLE` |
| a non-void revision has a parent that is missing | `MISSING_SUPERSEDED_PARENT` |
| two visible terminal revisions come from different source families | `CROSS_SOURCE_FAMILY_CONFLICT` |
| the `revision_number` is non-monotonic on a single chain | `REVISION_NUMBER_DISCONTINUITY` |
| a `is_deleted_or_voided = true` revision has child revisions | `INVALID_VOID_LINEAGE` |

The fail-closed block is the correct behavior. The following fallbacks are forbidden:

- `latest timestamp fallback` (the latest `recorded_at` wins);
- `largest revision-number fallback` (the highest `revision_number` wins);
- `current/latest row fallback`;
- `hash lexical winner` (lexicographic hash comparison);
- arbitrary selection of one branch when multiple terminal revisions exist.

When any fail-closed condition holds, the affected evaluation slice is `BLOCKED`. The blocker is reported through `blocker_dependencies`. The Q1 v1.1 wording that "later `recorded_at` wins" or that "higher `revision_number` wins" is removed.

#### §4.5.4 Void semantics (frozen)

- A valid `void` revision terminates a lineage. After the void revision, the business key has no valid actual at any later cutoff.
- A void revision cannot be reverted to an earlier non-void revision.
- A subsequent restoration requires a new explicit lineage and a business rule. The system does not auto-restore a voided value.

### §4.6 What the dual-cutoff model forbids

Q1 forbids:

- using `forecast_cutoff_at` as the label visibility boundary (the model could never score a future forecast);
- using `label_observation_cutoff_at` as the model input boundary (the model would leak the actual label);
- conflating training-feature visibility and label visibility;
- scoring with `latest` / `current` / `most_recent` actual row;
- using a final adjudicated label as a model input;
- using `replay_executed_at` (today) as `forecast_cutoff_at` (the simulated historical forecast cutoff must remain historical);
- using `forecast_target_date = forecast_cutoff_at` (the types are different; use `forecast_target_local_date = local_date(forecast_cutoff_at, farm_timezone)`).

Q1 permits:

- the actual label being recorded after the forecast cutoff;
- the actual label being revised after the forecast cutoff;
- the actual label being entered on a future target date;
- the actual label being visible to the evaluator at a later `label_observation_cutoff_at`;
- the historical replay executing today while keeping `forecast_cutoff_at` historical.

This is the only correct anti-leakage boundary.

---

## §5 Forecast-object contracts

### §5.1 Eight physical quantities (canonical, three-grain split per review 4695151631 P0-3)

For each `(farm, subfarm_or_plot, variety, season, calendar_date)`, the project distinguishes the following eight physical quantities. Each row below is the frozen Q1 contract; no row is interpreted, computed, or persisted outside this contract. The three-grain split separates the **conceptual** business grain, the **current Agent output grain** (which is downstream aggregate, not first-class member), and the **upstream member grain** (which lives on Task 9 member rows, not on the Agent aggregate row).

| # | object_name | business_definition | CONCEPTUAL_PHYSICAL_GRAIN | CURRENT_AGENT_OUTPUT_GRAIN | UPSTREAM_MEMBER_GRAIN | physical_meaning | unit | event_date_semantics | source_task | schema_path | persistence_table | current_production_status | actual_or_forecast | proxy_or_direct_observation | can_be_primary_label | can_be_feature | point_in_time_visibility | known_limitations |
|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `natural_maturity_quantity` | The model-predicted daily natural maturation of blueberry on the orchard, in the absence of weather and harvest-state effects. | `(farm × subfarm_or_plot × variety × calendar_date)` | `RESOLVED_REQUEST_AGGREGATE_X_DATE` (carried on `ForecastDailyRow` as a non-persisted Agent output field; no first-class `farm` / `subfarm` / `variety` identity on the row) | `FARM_X_SUBFARM_X_VARIETY_X_DATE_X_QUANTILE` (carried on `harvest_state_daily_member_row`; the Agent aggregate row does not have member identity) | A biological-physical quantity produced by the TASK-008 maturity model. It is not a human-observed quantity. | kg | the calendar date on which maturation occurs | TASK-008 | `backend/app/agent/schemas.py::ForecastDailyRow.natural_maturity_quantity_kg: DailyQuantiles` | n/a (Agent output field, not persisted directly; reconstructed from upstream TASK-008 forecast runs) | `RESOLVED_BY_MERGED_AUTHORITY` for schema; `NOT_VERIFIED` for production use in Q1 scope | forecast | `MODEL_OUTPUT` (not a direct observation; not a proxy for actual harvest) | NO | YES | n/a (forecast) | not a label; do not use for backtest |
| 2 | `mature_inventory_quantity` | The model-predicted closing mature inventory on a calendar date, after natural maturation and harvest-state update. | `(farm × subfarm_or_plot × variety × calendar_date)` | `RESOLVED_REQUEST_AGGREGATE_X_DATE` | `FARM_X_SUBFARM_X_VARIETY_X_DATE_X_QUANTILE` | A derived state. | kg | the calendar date on which the closing inventory is reported | TASK-008 / TASK-009 | `ForecastDailyRow.closing_mature_inventory_kg: DailyQuantiles` | n/a | same as #1 | forecast | `DERIVED_STATE` | NO | YES (as feature) | n/a (forecast) | derived; cannot be a label |
| 3 | `harvestable_quantity` | The model-predicted daily harvestable quantity (the portion of mature inventory that is operationally ready to be picked). | `(farm × subfarm_or_plot × variety × calendar_date)` | `NOT_CURRENTLY_AVAILABLE` (not first-class on `ForecastDailyRow`; `harvested_quantity_kg` is the closest Agent field, but it is a flow not a stock) | `FARM_X_SUBFARM_X_VARIETY_X_DATE_X_QUANTILE` (could live on a future TASK-009 member-grain field) | Currently NOT a first-class schema field in `origin/main`. Q1 explicitly marks this object as `NOT_CURRENTLY_AVAILABLE` as a first-class field. Q1 forbids any formula derivation (in particular, `harvestable_quantity = harvested_quantity - unharvested_backlog` is `FORMULA_NOT_AUTHORIZED` because `harvested_quantity` is a flow and `unharvested_backlog` is a stock, and the two physical dimensions do not justify direct subtraction). | kg (target unit) | the calendar date | n/a | **NOT in `origin/main` schema** | none | `NOT_CURRENTLY_AVAILABLE` / `FORMULA_NOT_AUTHORIZED` | n/a | n/a (no field, no formula) | NO | n/a | n/a | Q2A must add a first-class `harvestable_quantity_kg` field with explicit physical authority, or leave the object as `NOT_CURRENTLY_AVAILABLE` indefinitely |
| 4 | `model_harvested_quantity` (alias for `ForecastDailyRow.harvested_quantity_kg`) | The model-predicted daily quantity of blueberry the model expects to be picked on the orchard. | `(farm × subfarm_or_plot × variety × calendar_date)` | `RESOLVED_REQUEST_AGGREGATE_X_DATE` (carried on `ForecastDailyRow.harvested_quantity_kg` as a non-persisted Agent output field) | `FARM_X_SUBFARM_X_VARIETY_X_DATE_X_QUANTILE` (could live on a future TASK-009 member-grain field) | A model output, NOT a direct observation. The `harvested_quantity_kg` field on `ForecastDailyRow` is explicitly mapped to a model-predicted flow. It is NOT the `actual_harvest_quantity` business object. The two MUST NOT be conflated or renamed into each other. | kg | the calendar date | TASK-008 / TASK-009 | `ForecastDailyRow.harvested_quantity_kg: DailyQuantiles` | n/a (Agent output field) | `RESOLVED_BY_MERGED_AUTHORITY` for schema; `MODEL_OUTPUT` semantics; `NOT_DIRECT_OBSERVATION`; `NOT_PRIMARY_ACTUAL_LABEL` | forecast | `MODEL_OUTPUT` | NO | YES (as feature) | n/a (forecast) | model-predicted flow; not a label; do not confuse with `actual_harvest_quantity` |
| 5 | `actual_harvest_quantity` | The user-entered or operator-entered daily quantity of blueberry actually picked at the orchard. This is the primary business target for Q1. | `(farm × subfarm_or_plot × variety × calendar_date)` | `NOT_CURRENTLY_AVAILABLE` (no first-class Agent field for the actual; the Agent does not output a direct observation) | `FARM_X_SUBFARM_X_VARIETY_X_DATE` (would live on a dedicated `actual_harvest_daily` table, not on any current Agent field) | A direct observation. The most reliable source today is `fact_receipt_daily.weight_kg` interpreted as **arrival at the factory**, not pick at the orchard. There is **no first-class `actual_harvest_quantity` table in `origin/main`**. | kg (target unit) | the calendar date on which the pick occurred | n/a (no dedicated table) | **NOT in `origin/main` schema** | `fact_receipt_daily` is the closest first-class fact but it stores **arrival**, not pick. | `SCHEMA_GAP` / `SOURCE_GAP` / `PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO` | actual (intended) | `DIRECT_OBSERVATION` (when a dedicated table exists) / currently **no first-class table** | YES (intended primary label) | NO (label, not feature) | `POINT_IN_TIME_GAP` (current `fact_receipt_daily` lacks `recorded_at`, `effective_at`, `revised_at`) | Q2A must add a dedicated `actual_harvest_daily` table; `fact_receipt_daily` is an arrival proxy, not the primary label |
| 6 | `unharvested_backlog_quantity` | The model-predicted daily unharvested backlog. | `(farm × subfarm_or_plot × variety × calendar_date)` | `RESOLVED_REQUEST_AGGREGATE_X_DATE` | `FARM_X_SUBFARM_X_VARIETY_X_DATE_X_QUANTILE` | A derived state. | kg | the calendar date | TASK-008 / TASK-009 | `ForecastDailyRow.unharvested_backlog_kg: DailyQuantiles` | n/a | same as #1 | forecast | `DERIVED_STATE` | NO | YES (as feature) | n/a (forecast) | derived; cannot be a label |
| 7 | `arrival_quantity` | The model-predicted daily quantity arriving at the factory gate, before weather correction. | `(factory × variety × calendar_date)` | `RESOLVED_REQUEST_AGGREGATE_X_DATE` | `FARM_X_SUBFARM_X_VARIETY_X_DATE_X_QUANTILE` (with factory-level aggregation) | A model output. | kg | the calendar date of arrival at the factory gate | TASK-008 / TASK-009 | `ForecastDailyRow.arrival_quantity_kg: DailyQuantiles` | n/a | same as #1 | forecast | `MODEL_OUTPUT` (proxy for actual arrival, not for actual harvest) | NO (not a harvest label) | YES (as feature) | n/a (forecast) | proxy for arrival; not a harvest label |
| 8 | `final_corrected_arrival_quantity` | The model-predicted daily quantity arriving at the factory gate, after weather correction. | `(factory × variety × calendar_date)` | `RESOLVED_REQUEST_AGGREGATE_X_DATE` | `FARM_X_SUBFARM_X_VARIETY_X_DATE_X_QUANTILE` (with factory-level aggregation) | A model output. | kg | the calendar date | TASK-009 | `ForecastDailyRow.final_corrected_arrival_quantity_kg: DailyQuantiles` | n/a | same as #1 | forecast | `MODEL_OUTPUT` (proxy for actual arrival, not for actual harvest) | NO | YES (as feature) | n/a (forecast) | corrected proxy; not a harvest label |
| 9 | `season_cumulative_quantity` | The model-predicted or actual cumulative quantity from the season start through the calendar date. | `(farm × subfarm_or_plot × variety × season × calendar_date)` | `DERIVED_EVALUATION_METRIC` (no first-class Agent field; computed from the daily rows at evaluation time) | `FARM_X_SUBFARM_X_VARIETY_X_DATE_X_SEASON` (computed from the member-grain daily rows) | A derived aggregate. | kg | the calendar date through which the cumulative is computed | TASK-008 / TASK-009 (forecast); operator (actual) | **NOT in `origin/main` schema as a first-class field** | none | `NOT_CURRENTLY_AVAILABLE` as a first-class schema field; `DERIVED_EVALUATION_METRIC`; `NO_FIRST_CLASS_PRODUCTION_FIELD_REQUIRED_BY_Q1` | both | `DERIVED_STATE` (cumulative over daily rows) | YES (actual cumulative is the canonical label for cumulative metrics) | YES (forecast cumulative) | depends on daily row visibility | Q1 does not require a first-class `season_cumulative_quantity` field; the cumulative is a derived evaluation metric. Q2A may add a first-class field only if a separate persistence, API, or replay identity requirement is justified. |

### §5.2 First-class vs derived (v1.2 naming change per review 4695151631 P0-3)

Q1 v1.1 used the phrase "persisted fields of the model output" for `ForecastDailyRow`. v1.2 replaces this phrase with **"first-class serialized output-schema fields"** (or "non-persisted Agent output fields"). The Agent `ForecastDailyRow` is a serialized output schema; the fields are not persisted to a database table on their own. The reconstruction of the same field set from upstream TASK-008 / TASK-009 forecast runs is a separate persistence question.

The eight quantities are split into:

- **First-class serialized output-schema fields on `ForecastDailyRow`**: #1 (`natural_maturity_quantity_kg`), #2 (`closing_mature_inventory_kg`), #4 (`harvested_quantity_kg`, under the alias `model_harvested_quantity`), #6 (`unharvested_backlog_kg`), #7 (`arrival_quantity_kg`), #8 (`final_corrected_arrival_quantity_kg`). These are six `DailyQuantiles` fields. The Q1 v1.2 explicitly names the seventh, `harvested_quantity_kg`, as `model_harvested_quantity` (or equivalently, the existing `ForecastDailyRow.harvested_quantity_kg` field) with the qualifier `MODEL_OUTPUT` / `NOT_DIRECT_OBSERVATION` / `NOT_PRIMARY_ACTUAL_LABEL`. The Q1 v1.1 statement that the field "is not a direct observation" is preserved; v1.2 adds the explicit mapping table.
- **Not first-class in `origin/main`**: #3 (`harvestable_quantity`), #5 (`actual_harvest_quantity`), #9 (`season_cumulative_quantity`). Q1 marks them as `NOT_CURRENTLY_AVAILABLE` and proposes Q2A / Q3 design work to define them. Q1 does NOT require a first-class `season_cumulative_quantity` field (§5.4 below).

### §5.3 Mapping table: business object → current schema field

Per review 4695151631 P0-3 §6.3, Q1 v1.2 freezes a mapping table for the six first-class fields:

| Business object | Current schema field (on `ForecastDailyRow`) | Mapping qualifier |
|---|---|---|
| `natural_maturity_quantity` | `natural_maturity_quantity_kg: DailyQuantiles` | `MODEL_OUTPUT` |
| `mature_inventory_quantity` | `closing_mature_inventory_kg: DailyQuantiles` | `DERIVED_STATE` |
| `harvestable_quantity` | (no first-class field) | `NOT_CURRENTLY_AVAILABLE` / `FORMULA_NOT_AUTHORIZED` |
| `model_harvested_quantity` (alias for `harvested_quantity_kg`) | `harvested_quantity_kg: DailyQuantiles` | `MODEL_OUTPUT` / `NOT_DIRECT_OBSERVATION` / `NOT_PRIMARY_ACTUAL_LABEL` |
| `actual_harvest_quantity` | (no first-class field) | `NOT_CURRENTLY_AVAILABLE` / `PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO` |
| `unharvested_backlog_quantity` | `unharvested_backlog_kg: DailyQuantiles` | `DERIVED_STATE` |
| `arrival_quantity` | `arrival_quantity_kg: DailyQuantiles` | `MODEL_OUTPUT` (proxy for arrival) |
| `final_corrected_arrival_quantity` | `final_corrected_arrival_quantity_kg: DailyQuantiles` | `MODEL_OUTPUT` (corrected proxy) |
| `season_cumulative_quantity` | (no first-class field) | `DERIVED_EVALUATION_METRIC` / `NO_FIRST_CLASS_PRODUCTION_FIELD_REQUIRED_BY_Q1` |

`model_harvested_quantity` and `actual_harvest_quantity` are two distinct business objects. `ForecastDailyRow.harvested_quantity_kg` is the model-predicted flow (the former); the actual pick is a direct observation (the latter, not first-class on `origin/main`). Q1 forbids any conflation, rename, or silent substitution.

### §5.4 `season_cumulative_quantity` is a derived metric (v1.2 correction per review 4695151631 P0-3 §6.4)

Q1 v1.1 wrote: "Q2A must add a first-class `season_cumulative_quantity` field". v1.2 corrects this:

- The cumulative quantity is computed from valid daily rows at evaluation time.
- There is no separate persistence, API, or replay identity requirement for a first-class `season_cumulative_quantity` field, beyond the daily rows.
- The cumulative is a `DERIVED_EVALUATION_METRIC`.
- The status is `NO_FIRST_CLASS_PRODUCTION_FIELD_REQUIRED_BY_Q1`.
- Q2A may add a first-class field only if a separate persistence, API, or replay identity requirement is justified. Without such a requirement, the derived evaluation metric is sufficient.

### §5.5 Forbidden proxy-formula for `harvestable_quantity`

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

### §5.6 Proxy discipline (v1.2 per review 4695151631 P0-4)

Q1 forbids any silent reclassification of a model output as an actual observation. In particular, the `fact_receipt_daily` table is a first-class operator-entered daily fact, but it is **arrival at the factory**, not **pick at the orchard**. The Q1 v1.2 explicitly classifies `fact_receipt_daily.weight_kg` as an arrival proxy, not as the primary `actual_harvest_quantity` label. See §6 for the actual-label contract and §11 for the primary-vs-arrival separation.

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

### §6.4 Current actual-label status (v1.2, per review 4695151631 P0-4)

```
ACTUAL_LABEL_STATUS = SCHEMA_GAP / SOURCE_GAP / POINT_IN_TIME_GAP / REVISION_HISTORY_GAP
PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO
ARRIVAL_PROXY_EVALUATION_ALLOWED = DESIGN_OPTION
ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET = YES
PRIMARY_TARGET_ACCURACY_REPORTING_WITH_PROXY = FORBIDDEN
ACTUAL_LABEL_SUPPORTED_GRAIN = fact_receipt_daily at (build_run_id, season_id, factory_id, receipt_date, farm_key, subfarm_key, variety_id, weight_kg > 0) — arrival / receipt at the factory, NOT pick at the orchard
```

Each gap is a separate blocker:

- `SCHEMA_GAP` — no `actual_harvest_daily` table.
- `SOURCE_GAP` — the only operator-entered daily fact is `fact_receipt_daily`, which is **arrival** at the factory, not **pick** at the orchard. The physical meaning is different. `fact_receipt_daily` is `ARRIVAL_PROXY_EVALUATION_ALLOWED = DESIGN_OPTION`, but the proxy DOES NOT SATISFY the primary target. `PRIMARY_TARGET_ACCURACY_REPORTING_WITH_PROXY = FORBIDDEN`.
- `POINT_IN_TIME_GAP` — `fact_receipt_daily` does not carry `recorded_at`, `effective_at`, `revised_at`, `revision_number`, or `supersedes_record_id`. The Q1 contract requires these fields to enforce point-in-time visibility.
- `REVISION_HISTORY_GAP` — `fact_receipt_daily` is bound to a `build_run_id`; the build-run sequence is the only revision mechanism. This is a re-build mechanism, not a row-level revision. Q2A design must decide whether to keep the build-run model or to introduce row-level revision.

### §6.5 Point-in-time visibility contract

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
| `duplicate` | two rows with the same canonical-grain identity and overlapping effective window | resolved by the explicit supersession lineage and `revision_number`; never silently merged |
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

### §7.7 Primary vs legacy status (v1.2 per review 4695151631 P1-1)

The 7-day sustained peak is the **primary business sustained-peak target** for the project. The 3-day sustained peak is a **legacy compatibility metric** for the current compatibility horizon only. The 7-day metric is `NOT_YET_COMPUTABLE` until Q3 + Q2C implement the 7-day production field. Before that:

- `PRIMARY_SUSTAINED_PEAK_WINDOW_DAYS = 7`
- `PRIMARY_SUSTAINED_PEAK_QUALITY_STATUS = NOT_YET_COMPUTABLE`
- `THREE_DAY_METRIC_STATUS = LEGACY_COMPATIBILITY_METRIC`
- `SEVEN_DAY_METRIC_STATUS = PRIMARY_BUSINESS_SUSTAINED_PEAK_TARGET`

Q2B may evaluate the 3-day legacy compatibility metric for the current compatibility horizon, but the 3-day result:

- MUST NOT be cited as the first-stage primary sustained metric;
- MUST NOT replace the 7-day metric;
- MUST NOT enter any "core prediction target verified" conclusion;
- MUST NOT be used to unblock Q3 or Q2C.

---

## §8 Existing 3-day production contract audit (v1.2 per review 4695151631 P1-2)

Q1 does not silently reinterpret any 3-day field as a 7-day field. The 3-day production contract remains the production contract for the current compatibility horizon; the 7-day contract is an additive, versioned, separate contract.

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
CURRENT_3DAY_CONTRACT_STATUS = CURRENT_PRODUCTION_CONTRACT (for the current compatibility horizon)
CURRENT_3DAY_CONTRACT_REFERENCE_COUNT = (see Q1 data-coverage audit §B for the full count)
THREE_DAY_METRIC_STATUS = LEGACY_COMPATIBILITY_METRIC
```

The 3-day field semantics are preserved verbatim for the current compatibility horizon. Q1 does not change any 3-day field semantics.

### §8.3 7-day coexistence policy (v1.2 per review 4695151631 P1-2)

Q1 v1.2 freezes a single canonical coexistence policy. The earlier v1.1 wording that "both fields are present; the policy decides the primary display window, not the field presence" is preserved. The earlier v1.1 references to a "deprecation window" or "sunset window" are removed.

```
THREE_DAY_RETENTION_STATUS = PRESERVED_FOR_CURRENT_COMPATIBILITY_HORIZON
THREE_DAY_REMOVAL          = REQUIRES_SEPARATE_COMPATIBILITY_AMENDMENT
SEVEN_DAY_PRIMARY_SELECTION = REQUIRED_ONCE_IMPLEMENTED
```

- `sustained_7day_peak` is the primary business metric when implemented (Q3 + Q2C).
- `sustained_3day_peak` remains a legacy compatibility field for the current compatibility horizon.
- Q1 does not promise permanent retention of the 3-day field.
- Q1 does not authorize deletion of the 3-day field.
- Any future removal of the 3-day field requires a separate compatibility amendment.
- The compatibility amendment must include:
  1. consumer inventory (which downstream code reads `sustained_3day_peak`);
  2. API compatibility audit (which API surface exposes the field);
  3. Golden migration plan (which tests reference the field);
  4. deprecation timeline with explicit dates, not open-ended;
  5. CHARLES-APPROVED deprecation contract signed before the field is removed.

Q1 freezes the additive migration principle:

- Q3 first implementation: both fields exist;
- 7-day is the primary business metric;
- 3-day is the legacy compatibility metric;
- future removal of the 3-day field requires a separate compatibility amendment;
- Q1 does not contain any open-ended "permanent coexistence", "deprecation window", "sunset window", or "never removed" wording.

### §8.4 7-day migration boundary (design only, not implemented in Q1)

The 7-day migration is a separate design and implementation round. Q1 freezes the migration boundary but does not implement it. The migration design is:

- A new `sustained_7day_peak: dict[ForecastQuantile, SustainedPeakEntry]` field is added to `ForecastPeakOutput` (or a new `ForecastPeakOutputV2` schema version).
- The new field uses the existing `SustainedPeakEntry` schema, which already has `start_date`, `end_date`, `rolling_daily_average_kg_per_day`, `cumulative_quantity_kg`. No new field shape is required.
- The new field is gated by the `sustained_peak_schema_version` policy field; the output contains the field for every window in `supported_sustained_peak_window_days`.
- The 3-day field is preserved as a permanent co-existing field for the current compatibility horizon; it is not deprecated and not removed in Q1.
- The Golden migration is explicit: both fields are emitted; the Golden contains both 3-day and 7-day fields; the test plan includes both 3-day and 7-day assertions.
- The API migration is explicit: the API returns both 3-day and 7-day fields; the consumer chooses one based on the policy version.

```
7DAY_MIGRATION_REQUIRED = YES (separate design and implementation round, not in Q1)
SUSTAINED_7DAY_IMPLEMENTED = NO
7DAY_TARGET_CONTRACT_FROZEN = YES (this document §7)
THREE_DAY_SEVEN_DAY_COEXISTENCE_POLICY = ADDITIVE_BOTH_FIELDS_PRESENT (frozen in v1.1)
PRIMARY_SUSTAINED_PEAK_WINDOW_DAYS = 7
PRIMARY_SUSTAINED_PEAK_QUALITY_STATUS = NOT_YET_COMPUTABLE (until Q3 + Q2C)
```

### §8.5 Forbidden silent 3-day → 7-day reinterpretation

Q1 forbids:

- renaming `sustained_3day_peak` to `sustained_7day_peak` without an additive migration;
- changing the meaning of `sustained_window_days = 3` to `7` without a versioned policy field;
- aliasing `peak_window_cumulative_quantity_kg` to a 7-day window without a new field;
- changing the Golden's 3-day value to a 7-day value;
- changing the test assertion from "sustained_3day_peak" to "sustained_7day_peak" without a deprecation window.
- citing the 3-day metric as the first-stage primary sustained metric (it is `LEGACY_COMPATIBILITY_METRIC` only).
- using the 3-day result to unblock Q3 or Q2C.

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
                    replay_executed_at,
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
| `season_cumulative_actual_kg` | `sum(actual)` from season start through the last day in the slice | unit: kg; `season_cumulative` is a `DERIVED_EVALUATION_METRIC` (no first-class Agent field required) |
| `season_cumulative_forecast_kg` | `sum(forecast_p50)` from season start through the last day in the slice | unit: kg; same derivation |
| `cumulative_absolute_error_kg` | `abs(season_cumulative_forecast_kg - season_cumulative_actual_kg)` | unit: kg |
| `cumulative_signed_relative_error` | `(season_cumulative_forecast_kg - season_cumulative_actual_kg) / season_cumulative_actual_kg` | unit: fraction; if `season_cumulative_actual_kg = 0` → `NOT_COMPUTABLE` |
| `cumulative_absolute_relative_error` | `abs(season_cumulative_forecast_kg - season_cumulative_actual_kg) / abs(season_cumulative_actual_kg)` | unit: fraction; if `abs(season_cumulative_actual_kg) = 0` → `NOT_COMPUTABLE` |
| `zero_denominator_count` | rows in the slice with `abs(actual) = 0` | must be reported alongside any relative metric |
| `eligible_denominator_count` | rows in the slice with `abs(actual) > 0` | must be reported alongside any relative metric |
| `excluded_denominator_count` | rows in the slice excluded from the relative metric | must be reported alongside any relative metric |

### §9.4 Single-day peak metrics (frozen per review 4694771522 P1-2)

The Q1 v1.1 froze per-quantile single-day peak metrics consistent with `ForecastPeakOutput.single_day_peak: dict[ForecastQuantile, SingleDayPeakEntry]`.

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

The actual single-day peak is one row per season. The forecast single-day peak is per quantile. The error metrics are per quantile. P50 may be the primary point-forecast for display, but P80 and P90 MUST be reported independently and MUST NOT be silently dropped.

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
- Citing a proxy result (e.g. `fact_receipt_daily.weight_kg`) as `actual_harvest_accuracy` or `harvest_forecast_accuracy` or `primary_target_accuracy` is forbidden. A proxy result is named `arrival_proxy_evaluation` or `factory_receipt_forecast_evaluation`.
- Citing the 3-day production metric as the first-stage primary sustained metric is forbidden. The 3-day metric is a `LEGACY_COMPATIBILITY_METRIC` only.

---

## §10 Data coverage audit (read-only, see companion document)

The full data-coverage audit, including the 3-day production contract inventory, the actual-label grain audit, the harvest-state schema audit, the migration-history audit, the table-inventory audit, and the live-database discovery result, is in `docs/forecast-quality/slice-q1-data-coverage-audit.md`. This document is the single source of truth for the read-only data audit.

### §10.1 Live-database discovery result (v1.1, preserved in v1.2)

Q1 v1.1 performed a read-only live-database discovery on the configured PostgreSQL (`POSTGRES_HOST=localhost`, `POSTGRES_PORT=5432`, `POSTGRES_DB=blueberry_peak`, `POSTGRES_USER=blueberry_app`).

Discovery result:

- DB discoverable: **YES** (the `.env` and `docker-compose.yml` declare the connection; `psql` connects successfully; `SELECT now()` returns the current timestamp).
- DB reachable: **YES** (`psql -c "SELECT 1;"` returns `1`; a Docker container `c2-pg` is running on the local network).
- DB has data: **NO** (all 33 public-schema tables report 0 rows; `alembic_version` reports `0013_rolling_backtest_orch`, indicating that migrations 0014 and 0015 have not been applied to this DB; `harvest_state_replay_source_visibility_audit` does not exist, confirming 0015 has not been applied).
- Data source: configured PostgreSQL via Docker container `c2-pg` (image `pgvector/pgvector:pg16`, port 55432→5432).
- No fabrication: the 0-row aggregate is the truthful result of the discovery query; no fixture, no Golden, no sample data was substituted for real data.

```
REAL_DATA_SOURCE_DISCOVERY = POSTGRES_DOCKER_CONTAINER_C2_PG
REAL_DATA_COVERAGE_STATUS = NOT_VERIFIED (live DB discoverable but EMPTY; coverage = 0 for every entry)
Q1_DATA_COVERAGE_AUDIT_STATUS = PARTIAL (DB discovery done; data is empty; coverage matrix is 0 for every entry)
```

The 0-row aggregate means that the real-data coverage matrix cannot be populated with non-zero values. Q1 reports this as `NOT_VERIFIED_EMPTY_DATABASE` (per round §十一), not as `COMPLETE` / `READY` / `VERIFIED`.

### §10.2 Read-only query evidence (per §7.2 of the round instruction)

Q1 ran the following read-only queries on the live PostgreSQL. The output is included in the companion data-coverage audit. No query mutated data, no query created a table, no query altered a schema. The queries are aggregate-only; they do not return row-level data.

Queries executed (per Q1 v1.1):

1. `SELECT COUNT(*) FROM <each_table>;` for 16 tables.
2. `SELECT COUNT(*) FILTER (...), MIN(receipt_date), MAX(receipt_date), COUNT(DISTINCT ...) FROM fact_receipt_daily;`
3. `SELECT SUM(weight_kg), AVG(weight_kg), MIN(weight_kg), MAX(weight_kg) FROM fact_receipt_daily WHERE weight_kg > 0;`
4. `SELECT (series-level aggregation over season × farm × variety from fact_receipt_daily);`
5. `SELECT (dim-table count) from dim_farm, dim_subfarm, dim_variety, dim_season;`
6. `SELECT version_num FROM alembic_version;`
7. `SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'public';`

No query returned a `farm name`, `subfarm name`, `operator name`, `customer name`, `exact daily quantity`, `exact forecast output`, or `exact row count` on real data. All outputs are aggregate counts.

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
USABLE_BACKTEST_SERIES_COUNT_AGAINST_FACT_RECEIPT_DAILY = 0 (by the Q1 gate)
```

### §10.4 Desensitization note

The Q1 design-freeze does not output any sensitive real business data. No farm name, no subfarm name, no variety name (other than the public `dim_variety` table), no operator name, no exact daily quantity, no exact forecast output, and no exact row count on real data is reported. The Q2 / Q5 report must apply the same desensitization policy.

---

## §11 Actual-harvest label and arrival proxy separation (v1.2 per review 4695151631 P0-4)

Q1 v1.2 freezes a strict separation between the primary `actual_harvest_quantity` label (orchard pick) and the `fact_receipt_daily` proxy (factory arrival).

### §11.1 Frozen states

```
PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO
ARRIVAL_PROXY_EVALUATION_ALLOWED = DESIGN_OPTION
ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET = YES
PRIMARY_TARGET_ACCURACY_REPORTING_WITH_PROXY = FORBIDDEN
```

### §11.2 Proxy evaluation naming

If a future round accepts `fact_receipt_daily` as a proxy, the report MUST be named:

- `ARRIVAL_PROXY_EVALUATION`
- or `FACTORY_RECEIPT_FORECAST_EVALUATION`

The report MUST NOT be named:

- `ACTUAL_HARVEST_ACCURACY`
- `HARVEST_FORECAST_ACCURACY`
- `PRIMARY_TARGET_ACCURACY`

### §11.3 Q2A two-result split

Q2A may proceed as a design round, but Q2A has two distinct results that MUST be tracked separately:

**Result A — Dedicated actual-harvest source**: Q2A may add a dedicated `actual_harvest_daily` table with full row-level revision, point-in-time visibility, and the dual-cutoff semantics. Until Result A is implemented, the primary actual-harvest backtest is blocked. Result A unlocks the primary target evaluation.

**Result B — Receipt proxy accepted**: Q2A may accept `fact_receipt_daily` as a proxy. Result B unlocks only the `ARRIVAL_PROXY_EVALUATION` report. Result B does NOT unlock the primary target backtest. With Result B, the `TARGET_PHYSICAL_QUANTITY_ALIGNMENT` remains `NOT_PROVEN_EQUIVALENT`. To change the primary business target from "actual harvest" to "arrival", Charles must explicitly change the primary business target.

### §11.4 Q2A design and authorization

```
Q2A_DESIGN_ELIGIBLE_AFTER_Q1_ACCEPTANCE = YES
Q2A_CURRENTLY_AUTHORIZED = NO
Q2A_IMPLEMENTATION_READY = NO
Q2B_IMPLEMENTATION_READY = NO
Q3_CURRENTLY_AUTHORIZED = NO
```

Q2A design may begin after Q1 acceptance. Q2A implementation, Q2B implementation, and Q3 implementation are each separately unauthorized in this round.

---

## §12 Slice ordering (frozen, acyclic per review 4695151631 P0-3 + v1.1)

Q1 v1.1 froze an acyclic slice ordering. v1.2 preserves the same ordering and adds the Q2A-eligibility / Q2A-currently-authorized / Q2A-implementation-ready separation per round §十.

### §12.1 Slice ordering (acyclic)

| Slice | Goal | Predecessor | Status |
|---|---|---|---|
| Q1 | forecast target + evaluation contract + dual-cutoff model + sustained 7-day target contract + 3-day coexistence policy + actual-harvest vs arrival-proxy separation | (none) | design (this PR #103) |
| Q2A | actual-label source decision + dedicated table or accepted proxy + schema/migration + revision lineage + `label_observation_cutoff_at` evaluation-snapshot foundation + aggregate data-coverage query | Q1 | `Q2A_CURRENTLY_AUTHORIZED = NO` |
| Q2B | point-in-time backtest runner for currently supported outputs (the outputs that exist on `origin/main` after Q2A's accepted proxy, at the accepted grain); the 3-day legacy compatibility metric may be reported; the 7-day metric is `NOT_YET_COMPUTABLE` until Q3 + Q2C | Q2A | `Q2B_IMPLEMENTATION_READY = NO` |
| Q3 | additive sustained 7-day production migration (new field, 3-day coexistence, schema version, Golden/API compatibility, production acceptance) | Q1 | `Q3_CURRENTLY_AUTHORIZED = NO` |
| Q2C | extend Q2B with sustained 7-day scoring | Q2B + Q3 | not yet authorized |
| Q4 | naive baseline (one repeatable baseline, compared with the current model on the same data, the same cutoff, the same actual label, the same metric, the same 7-day peak definition) | Q2B | not yet authorized |
| Q5 | consolidated forecast-quality report (Q2B + Q2C + Q4 outputs aggregated into the report rows of Issue #102 §3) | Q2B + Q2C + Q4 | not yet authorized |
| Q6 | model improvement (allowed only after Q1..Q5 are accepted) | Q1..Q5 | not yet authorized |
| Q7 | thin trial UI (two pages: forecast page, forecast-vs-actual page) | Q5 | not yet authorized |

### §12.2 Q2 readiness

```
Q2_DESIGN_CAN_START = YES
Q2A_DESIGN_ELIGIBLE_AFTER_Q1_ACCEPTANCE = YES
Q2A_CURRENTLY_AUTHORIZED = NO
Q2A_IMPLEMENTATION_READY = NO
Q2B_IMPLEMENTATION_READY = NO
Q2_IMPLEMENTATION_READY = NO
Q3_CURRENTLY_AUTHORIZED = NO
Q2_READINESS = BLOCKED_BY_Q1_GAPS
```

Q2A design may begin after Q1 is accepted by Charles. Q2A implementation, Q2B implementation, and Q3 implementation are each separately unauthorized in this round. The blockers are:

1. `ACTUAL_LABEL_SOURCE_UNRESOLVED` (Q2A must resolve)
2. `ACTUAL_LABEL_SCHEMA_UNRESOLVED` (Q2A must resolve)
3. `LABEL_OBSERVATION_CUTOFF_NOT_IMPLEMENTED` (Q2A must implement the dual-cutoff snapshot)
4. `TARGET_OUTPUT_GRAIN_NOT_ALIGNED` (Q2A must resolve the path A / path B choice)
5. `QUANTILE_SEMANTICS_NOT_VERIFIED` (Q2B must verify)
6. `REAL_DATA_COVERAGE_NOT_VERIFIED` (Q2B must verify on a real data source with non-zero rows)
7. `SUSTAINED_7DAY_NOT_IMPLEMENTED` (Q3 must implement)

Q2 DESIGN work (the design of the Q2A actual-label source decision, the Q2B backtest runner contract, the Q2C extension for 7-day scoring) may begin once Q1 is accepted by Charles. Q2 IMPLEMENTATION requires the Q2 readiness items to be resolved.

### §12.3 Subsequent slice recommendations (Q1 does NOT implement)

Q1 recommends the following slice ordering, all of which require separate Charles authorization:

#### §12.3.1 Slice Q2A — actual-label source and evaluation-snapshot foundation

The Q2A minimum entry conditions are:

1. The Q1 design-freeze is accepted by Charles.
2. The actual-label source decision: either (a) a dedicated `actual_harvest_daily` table is added (Result A), or (b) `fact_receipt_daily` is accepted as a proxy (Result B).
3. The dual-cutoff snapshot identity is accepted: `forecast_cutoff_at` and `label_observation_cutoff_at` are two distinct fields.
4. The aggregation path (Path A or Path B of §11 / v1.1) is accepted.

The Q2A deliverables are:

- the actual-label source decision recorded in a design document;
- the schema or the proxy acceptance;
- the migration (if a new table is added);
- the revision lineage contract (with the fail-closed policy from §4.5);
- the `label_observation_cutoff_at` evaluation-snapshot identity;
- the aggregate data-coverage query runner.

Q2A does NOT modify any model. Q2A does NOT change TASK-008 / TASK-009 / TASK-010 numerical semantics. Q2A does NOT change the primary business target. Q2A does NOT promote `fact_receipt_daily` to the primary actual-harvest label.

#### §12.3.2 Slice Q2B — point-in-time backtest runner

The Q2B minimum entry conditions are Q2A acceptance. The Q2B deliverable is the point-in-time backtest runner that:

- consumes the actual-label contract (from Q2A);
- consumes the forecast-output contract (from Q2A's accepted aggregation path);
- consumes the replay identity;
- consumes the metric contract;
- supports the dual-cutoff model (including the four-time-bound time order);
- supports the fail-closed revision lineage;
- supports `AS_OF_EVALUATION` and `FINAL_ADJUDICATED` modes;
- reports per-evaluation-slice metrics;
- reports the 3-day legacy compatibility metric (per §7.7);
- does NOT report the 7-day sustained peak as a primary metric (it is `NOT_YET_COMPUTABLE` until Q3 + Q2C).

Q2B does NOT require the 7-day production field. Q2B may use the existing 3-day production field as a `LEGACY_COMPATIBILITY_METRIC` in the first stage.

#### §12.3.3 Slice Q3 — sustained 7-day peak production migration

The Q3 minimum entry conditions are Q1 acceptance. The Q3 deliverable is the additive 7-day field, with the additive-coexistence policy (§8.3), the migration, the Golden migration, the API migration, and the PostgreSQL production-chain acceptance. Q3 is `Q3_CURRENTLY_AUTHORIZED = NO`.

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

## §13 Forbidden actions in Q1 (v1.2, per review 4694771522 / 4695151631)

Q1 v1.2 forbids the following actions in this round. Each forbidden action is paired with the rationale and the verification check.

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
| cite the 3-day production metric as the first-stage primary sustained metric | Q1 v1.2 freezes the 3-day metric as `LEGACY_COMPATIBILITY_METRIC` only | the new commit classifies the 3-day metric as `LEGACY_COMPATIBILITY_METRIC` |
| use a single time cutoff for both model input and label visibility | the dual-cutoff model is the only correct anti-leakage boundary | the new commit defines `forecast_cutoff_at` and `label_observation_cutoff_at` as two distinct timestamps, plus the four-time-bound canonical order including `replay_executed_at` |
| use `replay_executed_at` (today) as `forecast_cutoff_at` | the historical replay must keep `forecast_cutoff_at` historical | the new commit freezes the four-time-bound canonical order |
| use `forecast_target_date = forecast_cutoff_at` | the types differ; use `forecast_target_local_date = local_date(forecast_cutoff_at, farm_timezone)` | the new commit uses the local-date form |
| use `forecast_target_date < forecast_cutoff_at` (in-simulation) | the v1.1 wording is removed | the new commit removes the wording |
| use `latest timestamp wins` for the revision winner | the fail-closed policy forbids this | the new commit freezes the fail-closed policy |
| use `largest revision-number wins` for the revision winner | the fail-closed policy forbids this | the new commit freezes the fail-closed policy |
| use `current/latest row fallback` for the revision winner | the fail-closed policy forbids this | the new commit freezes the fail-closed policy |
| use `hash lexical winner` for the revision winner | the fail-closed policy forbids this | the new commit freezes the fail-closed policy |
| describe `ForecastDailyRow` as having 7 quantity fields | the merged schema has exactly 6 `DailyQuantiles` quantity fields | the new commit lists 6 fields and names `harvested_quantity_kg` as `model_harvested_quantity` |
| describe `ForecastDailyRow` as first-class `(farm × subfarm × variety × date)` | the merged schema does not carry first-class farm/subfarm/variety identity | the new commit uses three-grain split with `CURRENT_AGENT_OUTPUT_GRAIN = RESOLVED_REQUEST_AGGREGATE_X_DATE` |
| describe `ForecastDailyRow` fields as "persisted fields" | the Agent output is a serialized schema, not a database row | the new commit uses "first-class serialized output-schema fields" |
| use `harvestable_quantity = harvested - backlog` as a formula | the formula has no physical authority and can be negative | the new commit marks `harvestable_quantity` as `NOT_CURRENTLY_AVAILABLE` / `FORMULA_NOT_AUTHORIZED` |
| require Q2A to add a first-class `season_cumulative_quantity` field | the cumulative is a `DERIVED_EVALUATION_METRIC` | the new commit marks `season_cumulative_quantity` as `NO_FIRST_CLASS_PRODUCTION_FIELD_REQUIRED_BY_Q1` |
| promote `fact_receipt_daily` to the primary `actual_harvest_quantity` label | the arrival proxy does not satisfy the primary target | the new commit freezes `PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO`, `ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET = YES`, `PRIMARY_TARGET_ACCURACY_REPORTING_WITH_PROXY = FORBIDDEN` |
| cite a proxy result as `ACTUAL_HARVEST_ACCURACY` or `HARVEST_FORECAST_ACCURACY` or `PRIMARY_TARGET_ACCURACY` | the proxy is arrival, not harvest | the new commit restricts proxy report names to `ARRIVAL_PROXY_EVALUATION` or `FACTORY_RECEIPT_FORECAST_EVALUATION` |
| claim `Q2_DESIGN_CAN_START = YES` to imply current authorization | the state is a Q1-acceptance precondition only | the new commit keeps `Q2A_CURRENTLY_AUTHORIZED = NO` separate |
| claim `Q2_READINESS = READY` | the same document reports Q1 gaps | the new commit sets `Q2_READINESS = BLOCKED_BY_Q1_GAPS` |
| report `REAL_DATA_COVERAGE_STATUS = COMPLETE / READY / VERIFIED` | the live database is empty | the new commit sets `REAL_DATA_COVERAGE_STATUS = NOT_VERIFIED_EMPTY_DATABASE` |
| set `Q2_READINESS = READY` while `Q2_IMPLEMENTATION_READY = NO` | the two must be consistent | the new commit keeps the three Q2 states distinct |
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
| output sensitive real business data | Q1 forbids real-data output | the data-coverage audit reports `NOT_VERIFIED_EMPTY_DATABASE` for live-database access |
| claim the 7-day peak is implemented | Q1 only freezes the contract | the report explicitly states `SUSTAINED_7DAY_IMPLEMENTED = NO` and `PRIMARY_SUSTAINED_PEAK_QUALITY_STATUS = NOT_YET_COMPUTABLE` |
| claim the forecast accuracy has improved | Q1 does not change any model | the report explicitly states `MODEL_CHANGE_NOT_AUTHORIZED` |
| fabricate real-data coverage | the audit reports `NOT_VERIFIED_EMPTY_DATABASE` for live-database access | the live-database query result is recorded as 0 rows for all tables; the audit does not substitute fixtures or Goldens for real data |
| describe Q1 as accepted | Q1 awaits re-review | the Q1 v1.2 sign-off section reports `PENDING_RE_REVIEW` and `Q1_NOT_YET_ACCEPTED` |

---

## §14 Validation checklist (against round §十三)

Q1 v1.2 ran the following validation checks:

1. `git diff --check` — clean.
2. `git diff --name-only origin/main` — only `docs/forecast-quality/` files.
3. forbidden-files exact set — empty (no `backend/`, `alembic/`, `frontend/`, `.github/`, dependency, Golden, fixture, or database file modified).
4. no backend changes — verified by `git diff --name-only origin/main -- backend/`.
5. no frontend changes — verified by `git diff --name-only origin/main -- frontend/`.
6. no test changes — verified by `git diff --name-only origin/main -- backend/tests/`.
7. no migration changes — verified by `git diff --name-only origin/main -- backend/alembic/`.
8. no workflow changes — verified by `git diff --name-only origin/main -- .github/`.
9. no Golden changes — verified by `git diff --name-only origin/main -- '**/golden/**'`.
10. no model changes — verified by the absence of any `backend/app/` mutation.
11. historical replay order matches `forecast_cutoff_at < forecast_target_date_or_window_end <= label_observation_cutoff_at <= replay_executed_at` — verified by §4.3.
12. no `forecast_target_date < forecast_cutoff_at` (in-simulation) — verified by §4.3.
13. no latest-timestamp winner — verified by §4.5.
14. no largest-revision fallback — verified by §4.5.
15. fork / cycle / multiple-terminal fail-closed — verified by §4.5.3.
16. physical table contains three separate grain columns — verified by §5.1.
17. no Agent aggregate field described as member-grain — verified by §5.1.
18. no unsupported "persisted field" claim — verified by §5.2.
19. all six `ForecastDailyRow` quantity fields mapped — verified by §5.3.
20. `harvested_quantity_kg` explicitly remains model output — verified by §5.1 and §5.3.
21. actual harvest and receipt proxy status separated — verified by §11.
22. no proxy result called actual-harvest accuracy — verified by §11.2.
23. 3-day classified only as legacy compatibility — verified by §7.7 and §8.3.
24. 7-day classified as primary business metric — verified by §7.7 and §8.3.
25. no undefined deprecation-window wording — verified by §8.3.
26. no permanent-retention promise — verified by §8.3.
27. no `Q2_READINESS = READY` — verified by §12.2.
28. no Q1 accepted claim — verified by §15.
29. three document line counts — reported in the final report.
30. three document SHA-256 — reported in the final report.
31. PR body Head equals final PR Head — verified by the PR body update (or by the `NOT EXECUTED` reporting when token is lost).
32. PR body hashes equal final file hashes — verified by the PR body update.
33. PR body does not mention seven quantity fields — verified by the PR body update.
34. PR body does not use stale old Head — verified by the PR body update.
35. local/remote/PR Head equality — verified by the 3-way verify.
36. exact-head CI result — recorded in the final report.

---

## §15 Change log

| Date | Round | Author | Change |
|---|---|---|---|
| 2026-07-14 | v1 (Q1) | Charles-authorized Q1 design-only round | Initial creation. |
| 2026-07-14 | v1.1 (Q1 P0 fixup) | Charles-authorized Q1 P0 fixup (review 4694771522) | Dual-cutoff model; six-field inventory; aggregate output grain; 3-day coexistence policy; signed/absolute relative-error split; real-data coverage reporting. |
| 2026-07-14 | v1.2 (Q1 final contract fixup) | Charles-authorized Q1 final fixup (review 4695151631) | (1) Historical-replay time model: `forecast_cutoff_at < forecast_target_date_or_window_end <= label_observation_cutoff_at <= replay_executed_at`. The v1.1 wording `forecast_target_date < forecast_cutoff_at` is removed. The same-day wording uses `forecast_target_local_date = local_date(forecast_cutoff_at, farm_timezone)`. (2) Fail-closed revision lineage policy: the unique visible terminal revision on one valid explicit supersession chain within one source family. The `latest timestamp wins` and `largest revision-number wins` rules are removed. Fail-closed conditions are listed as typed blockers. Void semantics are explicit. (3) Three-grain split on the physical-quantity table: `CONCEPTUAL_PHYSICAL_GRAIN`, `CURRENT_AGENT_OUTPUT_GRAIN`, `UPSTREAM_MEMBER_GRAIN`. The "persisted fields" phrase is replaced with "first-class serialized output-schema fields". `harvested_quantity_kg` is mapped to `model_harvested_quantity` with the qualifier `MODEL_OUTPUT / NOT_DIRECT_OBSERVATION / NOT_PRIMARY_ACTUAL_LABEL`. `season_cumulative_quantity` is `DERIVED_EVALUATION_METRIC / NO_FIRST_CLASS_PRODUCTION_FIELD_REQUIRED_BY_Q1`. (4) Actual-harvest label and arrival proxy separation: `PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO`, `ARRIVAL_PROXY_EVALUATION_ALLOWED = DESIGN_OPTION`, `ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET = YES`, `PRIMARY_TARGET_ACCURACY_REPORTING_WITH_PROXY = FORBIDDEN`. Proxy report names restricted to `ARRIVAL_PROXY_EVALUATION` or `FACTORY_RECEIPT_FORECAST_EVALUATION`. Q2A two-result split (Result A dedicated table; Result B proxy). (5) 3-day is `LEGACY_COMPATIBILITY_METRIC`; 7-day is `PRIMARY_BUSINESS_SUSTAINED_PEAK_TARGET`; primary status is `NOT_YET_COMPUTABLE` until Q3 + Q2C. The "permanent coexistence" and "deprecation window" wording are removed. The compatibility amendment process is explicit. (6) Slice ordering wording corrected: `Q2A_DESIGN_ELIGIBLE_AFTER_Q1_ACCEPTANCE = YES` separated from `Q2A_CURRENTLY_AUTHORIZED = NO`. (7) Decision table unified across the three Q1 documents. Sign-off no longer pre-fills `ACCEPTED`; the state is `PENDING_RE_REVIEW` and `Q1_NOT_YET_ACCEPTED`. |

---

## §16 Sign-off (to be completed by Charles upon acceptance)

```text
PR103_SLICE_Q1_FINAL_FIXUP_PENDING_RE_REVIEW
Q1_NOT_YET_ACCEPTED
Q1_FINAL_FIXUP_APPLIED
HISTORICAL_REPLAY_TIME_MODEL_FROZEN
REVISION_LINEAGE_FAIL_CLOSED_POLICY_FROZEN
THREE_GRAIN_SPLIT_FROZEN
ACTUAL_HARVEST_LABEL_SEPARATED_FROM_ARRIVAL_PROXY
SUSTAINED_7DAY_CONFIRMED_AS_PRIMARY_BUSINESS_TARGET
THREE_DAY_RECLASSIFIED_AS_LEGACY_COMPATIBILITY_METRIC
ACYCLIC_SLICE_ORDERING_FROZEN
Q2A_CURRENTLY_AUTHORIZED=NO
Q2B_IMPLEMENTATION_READY=NO
Q3_CURRENTLY_AUTHORIZED=NO
READY_NOT_AUTHORIZED
MERGE_NOT_AUTHORIZED
ISSUE99_REMAINS_OPEN
ISSUE102_REMAINS_OPEN
TASK013_C2_REMAINS_PAUSED
PR101_REMAINS_CLOSED_NOT_MERGED
```

(Charles to amend the above with explicit `ACCEPTED` or `REVISED` markers and post the result as an Issue #102 comment.)
