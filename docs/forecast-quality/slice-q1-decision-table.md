# Slice Q1 — Decision Table (Q1 §11 / Round §十二, v1.2)

| Field | Value |
|---|---|
| Document ID | `slice-q1-decision-table` |
| Document version | v1.2 (Q1 final contract docs-only fixup per review 4695151631) |
| Tracking Issue | `#102` (OPEN) |

This document is the explicit Q1 decision table required by round §十二. Every decision has one of the explicit values: `CONFIRMED` / `CONFIRMED_DEFINITION_ONLY` / `PARTIAL` / `NOT_IMPLEMENTED` / `NOT_AVAILABLE` / `NOT_VERIFIED` / `NOT_VERIFIED_EMPTY_DATABASE` / `NOT_CURRENTLY_AVAILABLE` / `NOT_PROVEN_EQUIVALENT` / `NOT_ALIGNED` / `FORMULA_NOT_AUTHORIZED` / `BLOCKED_BY_DATA` / `BLOCKED_BY_SCHEMA` / `BLOCKED_BY_POINT_IN_TIME_GAP` / `BLOCKED_BY_Q1_GAPS` / `CURRENT_PRODUCTION_CONTRACT` / `LEGACY_COMPATIBILITY_METRIC` / `DESIGN_CANDIDATES` / `CANDIDATE_ALIGNMENT_PATH` / `NOT_YET_ACCEPTED` / `NOT_YET_IMPLEMENTATION_AUTHORITY` / `PENDING_RE_REVIEW`. No fuzzy wording. The state is consistent across the three Q1 documents.

---

## §1 Decision table (canonical, single source, v1.2)

| Decision | Value | Evidence |
|---|---|---|
| `PRIMARY_BUSINESS_TARGET` | `DAILY_ACTUAL_HARVEST_QUANTITY_KG` (at `(farm_id, subfarm_or_plot_id, variety_id, season_id, harvest_date)`) | Q1 contract §3 / §5.1 |
| `PRIMARY_ACTUAL_HARVEST_LABEL_READY` | `NO` (per review 4695151631 P0-4) | Q1 contract §11.1 |
| `ARRIVAL_PROXY_EVALUATION_ALLOWED` | `DESIGN_OPTION` (per review 4695151631 P0-4) | Q1 contract §11.1 |
| `ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET` | `YES` (per review 4695151631 P0-4) | Q1 contract §11.1 |
| `CURRENT_MODEL_PRIMARY_OUTPUT` | `AGGREGATED_FORECAST_DAILY_ROW_WITH_6_QUANTITY_FIELDS` (downstream aggregate, per resolved agent request × calendar_date, with nested per-variety contribution) | Q1 contract §5.1 / §5.3 |
| `CURRENT_OUTPUT_GRAIN` | `RESOLVED_REQUEST_AGGREGATE_X_DATE` (no first-class farm/subfarm/variety identity on `ForecastDailyRow`) | Q1 contract §5.4 |
| `UPSTREAM_MEMBER_GRAIN` | `FARM_X_SUBFARM_X_VARIETY_X_DATE_X_QUANTILE` (carried on `harvest_state_daily_member_row`) | Q1 contract §5.1 |
| `DESIRED_ACTUAL_LABEL_GRAIN` | `FARM_X_SUBFARM_OR_PLOT_X_VARIETY_X_DATE` | Q1 contract §6.1 |
| `TARGET_PHYSICAL_QUANTITY_ALIGNMENT` | `NOT_PROVEN_EQUIVALENT` (current `harvested_quantity_kg` is a model output, not a direct observation) | Q1 contract §5.5 |
| `TARGET_GRAIN_ALIGNMENT` | `NOT_ALIGNED` (current aggregate grain vs desired member grain) | Q1 contract §5.5 |
| `ACTUAL_LABEL_STATUS` | `SCHEMA_GAP_SOURCE_GAP_POINT_IN_TIME_GAP_REVISION_HISTORY_GAP` | Q1 contract §6.4 |
| `FORECAST_CUTOFF_MODEL` | `CONFIRMED` (gates model input visibility) | Q1 contract §4.1 |
| `LABEL_OBSERVATION_CUTOFF_MODEL` | `CONFIRMED_DESIGN_ONLY` (gates actual-label visibility for evaluation; not yet implemented in production) | Q1 contract §4.2 |
| `HISTORICAL_REPLAY_TIME_MODEL` | `CONFIRMED_DESIGN_ONLY` (`forecast_cutoff_at < forecast_target_date_or_window_end <= label_observation_cutoff_at <= replay_executed_at`; per review 4695151631 P0-1) | Q1 contract §4.3 |
| `REVISION_LINEAGE_POLICY` | `EXPLICIT_UNIQUE_TERMINAL_FAIL_CLOSED` (per review 4695151631 P0-2) | Q1 contract §4.5 |
| `REVISION_CONFLICT_BEHAVIOR` | `FAIL_CLOSED_ON_FORK_CYCLE_MULTIPLE_TERMINAL_CROSS_SOURCE_FAMILY` | Q1 contract §4.5.3 |
| `REAL_DATA_COVERAGE_STATUS` | `NOT_VERIFIED_EMPTY_DATABASE` (live PG discoverable, but all 33 tables 0 rows) | Q1 contract §10.1 + Q1 audit §H.3 |
| `Q1_DATA_COVERAGE_AUDIT_STATUS` | `PARTIAL` (DB discovery done; data is empty; coverage matrix is 0) | Q1 contract §10.1 + Q1 audit §H.3 |
| `P50_SEMANTICS` | `NOT_VERIFIED` (Q2 / Q5 must verify on `origin/main`) | Q1 contract §9.7 |
| `P80_SEMANTICS` | `NOT_VERIFIED` (Q2 / Q5 must verify on `origin/main`) | Q1 contract §9.7 |
| `P90_SEMANTICS` | `NOT_VERIFIED` (Q2 / Q5 must verify on `origin/main`) | Q1 contract §9.7 |
| `QUANTILE_COVERAGE_STATUS` | `NOT_VERIFIED` (gated by quantile semantics verification) | Q1 contract §9.7 |
| `P80_P90_SEMANTICS_STATUS` | `NOT_VERIFIED` | Q1 contract §9.7 |
| `SUSTAINED_7DAY_PEAK_CONTRACT` | `CONFIRMED_DEFINITION_ONLY` (definition frozen, no implementation) | Q1 contract §7 |
| `PRIMARY_SUSTAINED_PEAK_WINDOW_DAYS` | `7` | Q1 contract §7.1 |
| `PRIMARY_SUSTAINED_PEAK_QUALITY_STATUS` | `NOT_YET_COMPUTABLE` (until Q3 + Q2C) | Q1 contract §7.7 |
| `SUSTAINED_7DAY_MISSING_WINDOW_POLICY` | `INCOMPLETE_WINDOW_EXCLUDED_FROM_PEAK_COMPETITION` (single canonical rule; no `or partial` ambiguity) | Q1 contract §7.3 |
| `CURRENT_3DAY_CONTRACT_STATUS` | `CURRENT_PRODUCTION_CONTRACT` (preserved verbatim) | Q1 contract §8 |
| `THREE_DAY_METRIC_STATUS` | `LEGACY_COMPATIBILITY_METRIC` (per review 4695151631 P1-1) | Q1 contract §7.7 / §8 |
| `SEVEN_DAY_METRIC_STATUS` | `PRIMARY_BUSINESS_SUSTAINED_PEAK_TARGET` | Q1 contract §7.7 / §8 |
| `THREE_DAY_RETENTION_STATUS` | `PRESERVED_FOR_CURRENT_COMPATIBILITY_HORIZON` (per review 4695151631 P1-2) | Q1 contract §8.3 |
| `THREE_DAY_REMOVAL` | `REQUIRES_SEPARATE_COMPATIBILITY_AMENDMENT` | Q1 contract §8.3 |
| `SEVEN_DAY_PRIMARY_SELECTION` | `REQUIRED_ONCE_IMPLEMENTED` | Q1 contract §8.3 |
| `THREE_DAY_SEVEN_DAY_COEXISTENCE_POLICY` | `ADDITIVE_BOTH_FIELDS_PRESENT` | Q1 contract §8.3 |
| `SINGLE_DAY_PEAK_QUANTILE_POLICY` | `PER_QUANTILE_P50_P80_P90` (no silent P50-only collapse) | Q1 contract §9.4 |
| `RELATIVE_ERROR_POLICY` | `SIGNED_ABSOLUTE_SEPARATED` (signed and absolute are distinct fields, plus denominator counts) | Q1 contract §9.3 / §9.4 / §9.5 |
| `FORECAST_DAILY_QUANTITY_FIELD_COUNT` | `6` (six `DailyQuantiles` quantity fields; `per_variety_contribution` is a nested list, not a 7th field) | Q1 contract §5.3 |
| `CURRENT_3DAY_CONTRACT_REFERENCE_COUNT` | `25+` (full inventory in Q1 audit §B) | Q1 audit §B |
| `ACTUAL_HARVEST_DAILY_TABLE` | `NOT_CURRENTLY_AVAILABLE` (no first-class table; `fact_receipt_daily` is the closest but is arrival, not pick) | Q1 contract §5.1 / §6.4 |
| `HARVESTABLE_MEMBER_OUTPUT_STATUS` | `AVAILABLE_AS_TASK9_HARVESTABLE_MATURE_QUANTITY` (member row `harvest_state_daily_member_row.harvestable_mature_quantity_kg` exists in `origin/main`) | Q1 contract §5.7 / §5.1 (review 4695538593) |
| `HARVESTABLE_AGENT_AGGREGATE_FIELD_STATUS` | `NOT_CURRENTLY_AVAILABLE` (`ForecastDailyRow` does NOT carry a first-class `harvestable_quantity_kg` field) | Q1 contract §5.7 / §5.1 (review 4695538593) |
| `HARVESTABLE_FORMULA_STATUS` | `NO_DERIVED_FORMULA_REQUIRED` (the member-row field is first-class; the Agent aggregate layer is not derived from a formula) | Q1 contract §5.7 / §5.5 (review 4695538593) |
| `HARVESTABLE_MINUS_BACKLOG_FORMULA` | `FORBIDDEN` (`harvested - backlog` has no physical authority; the result can be negative) | Q1 contract §5.5 |
| `MODEL_HARVESTED_MEMBER_OUTPUT_STATUS` | `AVAILABLE_AS_TASK9_HARVESTED_QUANTITY` (member row `harvest_state_daily_member_row.harvested_quantity_kg` exists in `origin/main`) | Q1 contract §5.7 / §5.1 (review 4695538593) |
| `MODEL_HARVESTED_AGENT_AGGREGATE_STATUS` | `AVAILABLE_AS_FORECAST_DAILY_ROW_AGGREGATE` (`ForecastDailyRow.harvested_quantity_kg: DailyQuantiles` exists in `origin/main`) | Q1 contract §5.7 / §5.1 (review 4695538593) |
| `MODEL_HARVESTED_DIRECT_ACTUAL_OBSERVATION` | `NO` (both member-row and Agent aggregate are model outputs) | Q1 contract §5.7 (review 4695538593) |
| `MODEL_HARVESTED_PRIMARY_ACTUAL_LABEL` | `NO` (member-row availability does NOT promote the field to a label) | Q1 contract §5.7 (review 4695538593) |
| `OBJECT_COUNT` | `9` (nine forecast/evaluation objects: natural_maturity / mature_inventory / harvestable / model_harvested / actual_harvest / unharvested_backlog / arrival / final_corrected_arrival / season_cumulative) | Q1 contract §5.1 (review 4695538593) |
| `OBJECT_SECTION_TITLE` | `Nine forecast/evaluation objects` (replaces v1.2 "Eight physical quantities") | Q1 contract §5.1 (review 4695538593) |
| `SEASON_CUMULATIVE_QUANTITY` | `NOT_CURRENTLY_AVAILABLE` as first-class field; `DERIVED_EVALUATION_METRIC`; `NO_FIRST_CLASS_PRODUCTION_FIELD_REQUIRED_BY_Q1` (per review 4695151631 P0-3) | Q1 contract §5.4 |
| `ALIGNMENT_CONTRACT` | `DESIGN_CANDIDATES` (Path A and Path B; Q1 does NOT select) | Q1 contract §11 |
| `Q2_DESIGN_CAN_START` | `YES` (Q1 acceptance precondition only) | Q1 contract §12.2 |
| `Q2A_DESIGN_ELIGIBLE_AFTER_Q1_ACCEPTANCE` | `YES` | Q1 contract §12.2 |
| `Q2A_CURRENTLY_AUTHORIZED=NO` | Q1 contract §12.2 |
| `Q2B_IMPLEMENTATION_READY` | `NO` | Q1 contract §12.2 |
| `Q2_IMPLEMENTATION_READY` | `NO` | Q1 contract §12.2 |
| `Q3_CURRENTLY_AUTHORIZED=NO` | Q1 contract §12.2 |
| `Q2_READINESS` | `BLOCKED_BY_Q1_GAPS` (7 listed blockers) | Q1 contract §12.2 |
| `ACYCLIC_SLICE_ORDERING` | `Q1 / Q2A / Q2B / Q3 / Q2C / Q4 / Q5 / Q6 / Q7` | Q1 contract §12.1 |
| `Q1_STATUS` | `PENDING_RE_REVIEW` (Q1 v1.2 awaits re-review) | this document / sign-off |
| `MODEL_CHANGE_NOT_AUTHORIZED` | `NOT_AUTHORIZED` | round §十六 |
| `BACKTEST_RUNNER_IMPLEMENTATION_NOT_AUTHORIZED` | `NOT_AUTHORIZED` | round §十六 |
| `NAIVE_BASELINE_IMPLEMENTATION_NOT_AUTHORIZED` | `NOT_AUTHORIZED` | round §十六 |
| `READY_NOT_AUTHORIZED` | `NOT_AUTHORIZED` | round §十六 |
| `MERGE_NOT_AUTHORIZED` | `NOT_AUTHORIZED` | round §十六 |
| `ISSUE99_REMAINS_OPEN` | `OPEN` | round §十六 |
| `ISSUE102_REMAINS_OPEN` | `OPEN` | round §十六 |
| `TASK013_C2_REMAINS_PAUSED` | `PAUSED` | round §十六 |
| `PR101_REMAINS_CLOSED_NOT_MERGED` | `CLOSED` | round §十六 |

## §2 Q2_READINESS blockers (7)

The 7 listed Q1 gaps that block Q2 implementation:

1. `ACTUAL_LABEL_SOURCE_UNRESOLVED` (Q2A must resolve)
2. `ACTUAL_LABEL_SCHEMA_UNRESOLVED` (Q2A must resolve)
3. `LABEL_OBSERVATION_CUTOFF_NOT_IMPLEMENTED` (Q2A must implement the dual-cutoff snapshot)
4. `TARGET_OUTPUT_GRAIN_NOT_ALIGNED` (Q2A must resolve the path A / path B choice)
5. `QUANTILE_SEMANTICS_NOT_VERIFIED` (Q2B must verify on `origin/main`)
6. `REAL_DATA_COVERAGE_NOT_VERIFIED` (Q2B must verify on a real data source with non-zero rows; the current live DB is empty)
7. `SUSTAINED_7DAY_NOT_IMPLEMENTED` (Q3 must implement)

Q2A DESIGN work (Q2A actual-label source decision, Q2B backtest runner contract, Q2C extension for 7-day scoring) may begin once Q1 is accepted by Charles. Q2 IMPLEMENTATION requires the Q2 readiness items to be resolved. Q3 implementation is separately unauthorized.

## §3 Forbidden-action check (Q1 §13)

| Forbidden action | Status | Verification |
|---|---|---|
| modify any production code under `backend/app/**` | `NOT_EXECUTED` | `git diff --name-only origin/main -- backend/app/` is empty |
| modify any test under `backend/tests/**` | `NOT_EXECUTED` | `git diff --name-only origin/main -- backend/tests/` is empty |
| add or modify any migration under `backend/alembic/**` | `NOT_EXECUTED` | `git diff --name-only origin/main -- backend/alembic/` is empty |
| modify any Golden file | `NOT_EXECUTED` | `git diff --name-only origin/main -- '**/golden/**'` is empty |
| modify any frontend, dependency, or workflow | `NOT_EXECUTED` | `git diff --name-only origin/main -- frontend/ .github/ pyproject.toml requirements.txt` is empty |
| implement the 7-day peak production code | `NOT_EXECUTED` | the new commit does not add any `sustained_7day_peak` field to `backend/app/agent/schemas.py` |
| implement the backtest runner | `NOT_EXECUTED` | the new commit does not add any backtest runner file |
| implement the naive baseline | `NOT_EXECUTED` | the new commit does not add any baseline file |
| silently rename `sustained_3day_peak` to `sustained_7day_peak` | `NOT_EXECUTED` | the new commit does not modify the 3-day field semantics |
| cite the 3-day production metric as the first-stage primary sustained metric | `NOT_EXECUTED` | the new commit classifies the 3-day metric as `LEGACY_COMPATIBILITY_METRIC` |
| use a single time cutoff for both model input and label visibility | `NOT_EXECUTED` | the new commit defines `forecast_cutoff_at` and `label_observation_cutoff_at` as two distinct timestamps, plus the four-time-bound canonical order including `replay_executed_at` |
| use `replay_executed_at` (today) as `forecast_cutoff_at` | `NOT_EXECUTED` | the new commit freezes the four-time-bound canonical order |
| use `forecast_target_date = forecast_cutoff_at` | `NOT_EXECUTED` | the new commit uses the local-date form |
| use `forecast_target_date < forecast_cutoff_at` (in-simulation) | `NOT_EXECUTED` | the new commit removes the wording |
| use `latest timestamp wins` for the revision winner | `NOT_EXECUTED` | the new commit freezes the fail-closed policy |
| use `largest revision-number wins` for the revision winner | `NOT_EXECUTED` | the new commit freezes the fail-closed policy |
| use `current/latest row fallback` for the revision winner | `NOT_EXECUTED` | the new commit freezes the fail-closed policy |
| use `hash lexical winner` for the revision winner | `NOT_EXECUTED` | the new commit freezes the fail-closed policy |
| describe `ForecastDailyRow` as having 7 quantity fields | `NOT_EXECUTED` | the new commit lists 6 fields and names `harvested_quantity_kg` as `model_harvested_quantity` |
| describe `ForecastDailyRow` as first-class `(farm × subfarm × variety × date)` | `NOT_EXECUTED` | the new commit uses three-grain split with `CURRENT_AGENT_OUTPUT_GRAIN = RESOLVED_REQUEST_AGGREGATE_X_DATE` |
| describe `ForecastDailyRow` fields as "persisted fields" | `NOT_EXECUTED` | the new commit uses "first-class serialized output-schema fields" |
| use `harvestable_quantity = harvested - backlog` as a formula | `NOT_EXECUTED` | the new commit marks `harvestable_quantity` as `NOT_CURRENTLY_AVAILABLE` / `FORMULA_NOT_AUTHORIZED` |
| require Q2A to add a first-class `season_cumulative_quantity` field | `NOT_EXECUTED` | the new commit marks `season_cumulative_quantity` as `NO_FIRST_CLASS_PRODUCTION_FIELD_REQUIRED_BY_Q1` |
| promote `fact_receipt_daily` to the primary `actual_harvest_quantity` label | `NOT_EXECUTED` | the new commit freezes `PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO`, `ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET = YES`, `PRIMARY_TARGET_ACCURACY_REPORTING_WITH_PROXY = FORBIDDEN` |
| cite a proxy result as `ACTUAL_HARVEST_ACCURACY` or `HARVEST_FORECAST_ACCURACY` or `PRIMARY_TARGET_ACCURACY` | `NOT_EXECUTED` | the new commit restricts proxy report names to `ARRIVAL_PROXY_EVALUATION` or `FACTORY_RECEIPT_FORECAST_EVALUATION` |
| claim `Q2_DESIGN_CAN_START = YES` to imply current authorization | `NOT_EXECUTED` | the new commit keeps `Q2A_CURRENTLY_AUTHORIZED=NO` separate |
| claim `Q2_READINESS = READY` | `NOT_EXECUTED` | the new commit sets `Q2_READINESS = BLOCKED_BY_Q1_GAPS` |
| report `REAL_DATA_COVERAGE_STATUS = COMPLETE / READY / VERIFIED` | `NOT_EXECUTED` | the new commit sets `REAL_DATA_COVERAGE_STATUS = NOT_VERIFIED_EMPTY_DATABASE` |
| set `Q2_READINESS = READY` while `Q2_IMPLEMENTATION_READY = NO` | `NOT_EXECUTED` | the new commit keeps the three Q2 states distinct |
| use signed and absolute relative error under a single field | `NOT_EXECUTED` | the new commit names signed and absolute variants separately |
| leave a sustained 7-day window `NOT_COMPUTABLE or partial` | `NOT_EXECUTED` | the new commit names a single canonical rule (excluded from peak competition) |
| report single-day peak metrics at only P50 | `NOT_EXECUTED` | the new commit defines per-quantile forecast peak metrics |
| close Issue #99 | `NOT_EXECUTED` | `gh issue view 99 --json state` is `OPEN` |
| close Issue #102 | `NOT_EXECUTED` | `gh issue view 102 --json state` is `OPEN` |
| re-open PR #101 | `NOT_EXECUTED` | `gh pr view 101 --json state` is `CLOSED` |
| mark the Q1 Draft PR as Ready | `NOT_EXECUTED` | the Q1 Draft PR is in `OPEN / Draft / NOT MERGED` state |
| merge the Q1 Draft PR | `NOT_EXECUTED` | the Q1 Draft PR is `NOT MERGED` |
| delete the PR #101 branch | `NOT_EXECUTED` | the branch `docs/task-013-slice-c-c2-business-source-definition` is preserved on `origin` |
| delete the PR #101 worktree | `NOT_EXECUTED` | the worktree `/tmp/task-013-c2-source-definition` is preserved |
| delete the Q1 worktree | `NOT_EXECUTED` | the worktree `/tmp/issue-102-slice-q1-forecast-evaluation-contract` is preserved |
| delete the prototype worktree | `NOT_EXECUTED` | the worktree `/tmp/task-013-c2-concept-ui-v1` is preserved |
| delete any untracked file in the main worktree | `NOT_EXECUTED` | the 4 untracked files in the main worktree are preserved |
| output sensitive real business data | `NOT_EXECUTED` | the Q1 v1.2 documents do not contain any farm name, subfarm name, variety name, operator name, exact daily quantity, or exact forecast output |
| claim the 7-day peak is implemented | `NOT_EXECUTED` | the Q1 v1.2 contract and audit documents both state `SUSTAINED_7DAY_IMPLEMENTED = NO` and `PRIMARY_SUSTAINED_PEAK_QUALITY_STATUS = NOT_YET_COMPUTABLE` |
| claim the forecast accuracy has improved | `NOT_EXECUTED` | the Q1 v1.2 documents both state `MODEL_CHANGE_NOT_AUTHORIZED` |
| fabricate real-data coverage | `NOT_EXECUTED` | the live-database query result is recorded as 0 rows for all tables; the audit does not substitute fixtures or Goldens for real data |
| describe Q1 as accepted | `NOT_EXECUTED` | the Q1 v1.2 sign-off section reports `PENDING_RE_REVIEW` and `Q1_NOT_YET_ACCEPTED` |

---

## §4 Sign-off (to be completed by Charles upon acceptance)

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
Q2...rles to amend the above with explicit `ACCEPTED` or `REVISED` markers.)
