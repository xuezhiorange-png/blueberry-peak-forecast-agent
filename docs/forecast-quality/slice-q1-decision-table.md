# Slice Q1 — Decision Table (Q1 §11 / Round §12, v1.1)

| Field | Value |
|---|---|
| Document ID | `slice-q1-decision-table` |
| Document version | v1.1 (Q1 P0 fixup per review 4694771522) |
| Tracking Issue | `#102` (OPEN) |

This document is the explicit Q1 decision table required by round §12. Every decision has one of the explicit values: `CONFIRMED` / `CONFIRMED_DEFINITION_ONLY` / `PARTIAL` / `NOT_IMPLEMENTED` / `NOT_AVAILABLE` / `NOT_VERIFIED` / `NOT_CURRENTLY_AVAILABLE` / `NOT_PROVEN_EQUIVALENT` / `NOT_ALIGNED` / `FORMULA_NOT_AUTHORIZED` / `BLOCKED_BY_DATA` / `BLOCKED_BY_SCHEMA` / `BLOCKED_BY_POINT_IN_TIME_GAP` / `BLOCKED_BY_Q1_GAPS` / `CURRENT_PRODUCTION_CONTRACT` / `DESIGN_CANDIDATES` / `CANDIDATE_ALIGNMENT_PATH` / `NOT_YET_ACCEPTED` / `NOT_YET_IMPLEMENTATION_AUTHORITY` / `PENDING_RE_REVIEW`. No fuzzy wording. The state is consistent across the three Q1 documents.

---

## §1 Decision table (canonical, single source)

| Decision | Value | Evidence |
|---|---|---|
| `PRIMARY_BUSINESS_TARGET` | `DAILY_ACTUAL_HARVEST_QUANTITY_KG` (at `(farm_id, subfarm_or_plot_id, variety_id, season_id, harvest_date)`) | Q1 contract §3 / §5.1 |
| `CURRENT_MODEL_PRIMARY_OUTPUT` | `AGGREGATED_FORECAST_DAILY_ROW_WITH_6_QUANTITY_FIELDS` (downstream aggregate, per resolved agent request × calendar_date, with nested per-variety contribution) | Q1 contract §5.3 / §5.4 |
| `CURRENT_OUTPUT_GRAIN` | `RESOLVED_REQUEST_AGGREGATE_X_DATE` (no first-class farm/subfarm/variety identity on `ForecastDailyRow`) | Q1 contract §5.4 |
| `DESIRED_ACTUAL_LABEL_GRAIN` | `FARM_X_SUBFARM_OR_PLOT_X_VARIETY_X_DATE` | Q1 contract §6.1 |
| `TARGET_PHYSICAL_QUANTITY_ALIGNMENT` | `NOT_PROVEN_EQUIVALENT` (current `harvested_quantity_kg` is a model output, not a direct observation) | Q1 contract §5.5 |
| `TARGET_GRAIN_ALIGNMENT` | `NOT_ALIGNED` (current aggregate grain vs desired member grain) | Q1 contract §5.5 |
| `ACTUAL_LABEL_STATUS` | `SCHEMA_GAP_SOURCE_GAP_POINT_IN_TIME_GAP_REVISION_HISTORY_GAP` | Q1 contract §6.4 |
| `FORECAST_CUTOFF_MODEL` | `CONFIRMED` (gates model input visibility) | Q1 contract §4.1 |
| `LABEL_OBSERVATION_CUTOFF_MODEL` | `CONFIRMED_DESIGN_ONLY` (gates actual-label visibility for evaluation; not yet implemented in production) | Q1 contract §4.2 |
| `EVALUATION_LABEL_MODES` | `AS_OF_EVALUATION` / `FINAL_ADJUDICATED` (frozen, not yet implemented) | Q1 contract §4.4 |
| `REAL_DATA_SOURCE_DISCOVERY` | `POSTGRES_DOCKER_CONTAINER_C2_PG` (pgvector/pgvector:pg16, port 55432→5432, ~4 hours old) | Q1 audit §H.1 |
| `REAL_DATA_COVERAGE_STATUS` | `NOT_VERIFIED` (live DB discoverable and reachable, but all 33 public-schema tables report 0 rows; alembic at `0013_rolling_backtest_orch`; 0014 and 0015 not applied) | Q1 audit §H.2 / §H.3 |
| `Q1_DATA_COVERAGE_AUDIT_STATUS` | `PARTIAL` (DB discovery done; data is empty; coverage matrix is 0 for every entry) | Q1 audit §H.3 |
| `P50_SEMANTICS` | `NOT_VERIFIED` (Q2 / Q5 must verify on `origin/main`) | Q1 contract §9.7 |
| `P80_SEMANTICS` | `NOT_VERIFIED` (Q2 / Q5 must verify on `origin/main`) | Q1 contract §9.7 |
| `P90_SEMANTICS` | `NOT_VERIFIED` (Q2 / Q5 must verify on `origin/main`) | Q1 contract §9.7 |
| `QUANTILE_COVERAGE_STATUS` | `NOT_VERIFIED` (gated by quantile semantics verification) | Q1 contract §9.7 |
| `P80_P90_SEMANTICS_STATUS` | `NOT_VERIFIED` | Q1 contract §9.7 |
| `SUSTAINED_7DAY_PEAK_CONTRACT` | `CONFIRMED_DEFINITION_ONLY` (definition frozen, no implementation) | Q1 contract §7 |
| `SUSTAINED_7DAY_MISSING_WINDOW_POLICY` | `INCOMPLETE_WINDOW_EXCLUDED_FROM_PEAK_COMPETITION` (single canonical rule; no `or partial` ambiguity) | Q1 contract §7.3 |
| `CURRENT_3DAY_CONTRACT_STATUS` | `CURRENT_PRODUCTION_CONTRACT` (preserved verbatim; 25+ references inventoried) | Q1 contract §8 |
| `THREE_DAY_SEVEN_DAY_COEXISTENCE_POLICY` | `ADDITIVE_BOTH_FIELDS_PRESENT` (policy decides primary display window, not field presence) | Q1 contract §8.3 |
| `SUSTAINED_7DAY_IMPLEMENTED` | `NO` | Q1 contract §8.4 |
| `7DAY_MIGRATION_REQUIRED` | `YES` (separate Q3 round) | Q1 contract §8.4 |
| `SINGLE_DAY_PEAK_QUANTILE_POLICY` | `PER_QUANTILE_P50_P80_P90` (no silent P50-only collapse) | Q1 contract §9.4 |
| `RELATIVE_ERROR_POLICY` | `SIGNED_ABSOLUTE_SEPARATED` (signed and absolute are distinct fields, plus denominator counts) | Q1 contract §9.3 / §9.4 / §9.5 |
| `FORECAST_DAILY_QUANTITY_FIELD_COUNT` | `6` (six `DailyQuantiles` quantity fields; `per_variety_contribution` is a nested list, not a 7th field) | Q1 contract §5.3 |
| `CURRENT_3DAY_CONTRACT_REFERENCE_COUNT` | `25+` (full inventory in Q1 audit §B) | Q1 audit §B |
| `ACTUAL_HARVEST_DAILY_TABLE` | `NOT_CURRENTLY_AVAILABLE` (no first-class table; `fact_receipt_daily` is the closest but is receipt, not pick) | Q1 contract §5.1 / §6.4 |
| `HARVESTABLE_QUANTITY` | `NOT_CURRENTLY_AVAILABLE` / `FORMULA_NOT_AUTHORIZED` (no first-class field; the `harvested - backlog` formula is forbidden) | Q1 contract §5.1 / §5.6 |
| `SEASON_CUMULATIVE_QUANTITY` | `NOT_CURRENTLY_AVAILABLE` (no first-class field; computed aggregate only) | Q1 contract §5.1 |
| `ALIGNMENT_CONTRACT` | `DESIGN_CANDIDATES` (Path A and Path B; Q1 does NOT select) | Q1 contract §11 |
| `Q2_DESIGN_CAN_START` | `YES` | Q1 contract §12.2 |
| `Q2_IMPLEMENTATION_READY` | `NO` | Q1 contract §12.2 |
| `Q2_READINESS` | `BLOCKED_BY_Q1_GAPS` (7 listed blockers) | Q1 contract §12.2 |
| `ACYCLIC_SLICE_ORDERING` | `Q1 / Q2A / Q2B / Q3 / Q2C / Q4 / Q5 / Q6 / Q7` | Q1 contract §12.1 |
| `MODEL_CHANGE_NOT_AUTHORIZED` | `NOT_AUTHORIZED` | round §16 |
| `BACKTEST_RUNNER_IMPLEMENTATION_NOT_AUTHORIZED` | `NOT_AUTHORIZED` | round §16 |
| `NAIVE_BASELINE_IMPLEMENTATION_NOT_AUTHORIZED` | `NOT_AUTHORIZED` | round §16 |
| `READY_NOT_AUTHORIZED` | `NOT_AUTHORIZED` | round §16 |
| `MERGE_NOT_AUTHORIZED` | `NOT_AUTHORIZED` | round §16 |
| `ISSUE99_REMAINS_OPEN` | `OPEN` | round §16 |
| `ISSUE102_REMAINS_OPEN` | `OPEN` | round §16 |
| `TASK013_C2_REMAINS_PAUSED` | `PAUSED` | round §16 |
| `PR101_REMAINS_CLOSED_NOT_MERGED` | `CLOSED` | round §16 |

## §2 Q2_READINESS blockers (7)

The 7 listed Q1 gaps that block Q2 implementation:

1. `ACTUAL_LABEL_SOURCE_UNRESOLVED` (Q2A must resolve)
2. `ACTUAL_LABEL_SCHEMA_UNRESOLVED` (Q2A must resolve)
3. `LABEL_OBSERVATION_CUTOFF_NOT_IMPLEMENTED` (Q2A must implement the dual-cutoff snapshot)
4. `TARGET_OUTPUT_GRAIN_NOT_ALIGNED` (Q2A must resolve the path A / path B choice)
5. `QUANTILE_SEMANTICS_NOT_VERIFIED` (Q2B must verify on `origin/main`)
6. `REAL_DATA_COVERAGE_NOT_VERIFIED` (Q2B must verify on a real data source with non-zero rows)
7. `SUSTAINED_7DAY_NOT_IMPLEMENTED` (Q3 must implement)

Q2 DESIGN work (Q2A actual-label source decision, Q2B backtest runner contract, Q2C extension for 7-day scoring) may begin once Q1 is accepted by Charles. Q2 IMPLEMENTATION requires the Q2 readiness items to be resolved.

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
| use a single time cutoff for both model input and label visibility | `NOT_EXECUTED` | the new commit defines `forecast_cutoff_at` and `label_observation_cutoff_at` as two distinct timestamps |
| describe `ForecastDailyRow` as having 7 quantity fields | `NOT_EXECUTED` | the new commit lists 6 fields |
| describe `ForecastDailyRow` as first-class `(farm × subfarm × variety × date)` | `NOT_EXECUTED` | the new commit describes the row as a downstream aggregate |
| use `harvestable_quantity = harvested - backlog` as a formula | `NOT_EXECUTED` | the new commit marks `harvestable_quantity` as `NOT_CURRENTLY_AVAILABLE` / `FORMULA_NOT_AUTHORIZED` |
| claim `Q2_READINESS = READY` | `NOT_EXECUTED` | the new commit sets `Q2_READINESS = BLOCKED_BY_Q1_GAPS` |
| report `REAL_DATA_COVERAGE_STATUS = COMPLETE / READY / VERIFIED` | `NOT_EXECUTED` | the new commit sets `REAL_DATA_COVERAGE_STATUS = NOT_VERIFIED` |
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
| output sensitive real business data | `NOT_EXECUTED` | the Q1 v1.1 documents do not contain any farm name, subfarm name, variety name, operator name, exact daily quantity, or exact forecast output |
| claim the 7-day peak is implemented | `NOT_EXECUTED` | the Q1 v1.1 contract and audit documents both state `SUSTAINED_7DAY_IMPLEMENTED = NO` |
| claim the forecast accuracy has improved | `NOT_EXECUTED` | the Q1 v1.1 documents both state `MODEL_CHANGE_NOT_AUTHORIZED` |
| fabricate real-data coverage | `NOT_EXECUTED` | the live-database query result is recorded as 0 rows for all tables; the audit does not substitute fixtures or Goldens for real data |
| describe Q1 as accepted | `NOT_EXECUTED` | the Q1 v1.1 sign-off section reports `Q1_NOT_YET_ACCEPTED` and `PENDING_RE_REVIEW` |

---

## §4 Sign-off (to be completed by Charles upon acceptance)

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

(Charles to amend the above with explicit `ACCEPTED` or `REVISED` markers.)
