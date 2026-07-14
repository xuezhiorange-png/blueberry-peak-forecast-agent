# Slice Q1 — Decision Table (Q1 §11 / Round §12)

| Field | Value |
|---|---|
| Document ID | `slice-q1-decision-table` |
| Document version | v1 |
| Tracking Issue | `#102` (OPEN) |

This document is the explicit Q1 decision table required by round §12. Every decision has one of the explicit values: `CONFIRMED` / `PARTIAL` / `NOT_IMPLEMENTED` / `NOT_AVAILABLE` / `NOT_VERIFIED` / `BLOCKED_BY_DATA` / `BLOCKED_BY_SCHEMA` / `BLOCKED_BY_POINT_IN_TIME_GAP`. No fuzzy wording.

---

## §1 Primary-target and target-output alignment

| Decision | Value | Evidence |
|---|---|---|
| `PRIMARY_BUSINESS_TARGET` | `daily actual harvest quantity in kg at (farm × subfarm_or_plot × variety × calendar_date)` | Q1 contract §5.1 (frozen by Issue #102 §1 acceptance) |
| `CURRENT_MODEL_PRIMARY_OUTPUT` | `ForecastDailyRow with seven quantity fields per (farm × subfarm × variety × calendar_date), each with DailyQuantiles (p50 / p80 / p90), plus single-day peak and sustained-3-day peak per quantile, plus ParameterEstimate at (parameter_name, variety_id)` | Q1 contract §5.2 (audit on `origin/main:backend/app/agent/schemas.py`) |
| `TARGET_OUTPUT_ALIGNMENT` | `NOT_PROVEN_EQUIVALENT` | Q1 contract §5.3 — the current model output is not a first-class `actual_harvest_quantity`; the closest fact is `fact_receipt_daily` which is receipt not pick |
| `ACTUAL_LABEL_STATUS` | `BLOCKED_BY_SCHEMA / BLOCKED_BY_POINT_IN_TIME_GAP` | Q1 contract §6.4 — no first-class `actual_harvest_daily` table; `fact_receipt_daily` lacks `recorded_at`, `effective_at`, `revised_at`, `revision_number`, `supersedes_record_id` |
| `ACTUAL_LABEL_SUPPORTED_GRAIN` | `fact_receipt_daily at (build_run_id, season_id, factory_id, receipt_date, farm_key, subfarm_key, variety_id, weight_kg > 0) — receipt, not pick` | Q1 contract §6.2 + audit doc §D.1 |
| `POINT_IN_TIME_STATUS` | `BLOCKED_BY_POINT_IN_TIME_GAP` | Q1 contract §6.5 + audit doc §D.2 |
| `P50_SEMANTICS` | `NOT_VERIFIED` | Q1 contract §9.6 — the audit cannot verify on `origin/main` whether `p50` is a true quantile or a point estimate; the field is `DecimalString` and the schema does not declare it as an upper quantile |
| `P80_SEMANTICS` | `NOT_VERIFIED` | same as `P50_SEMANTICS` |
| `P90_SEMANTICS` | `NOT_VERIFIED` | same as `P50_SEMANTICS` |
| `QUANTILE_COVERAGE_STATUS` | `BLOCKED_BY_POINT_IN_TIME_GAP` (cannot compute coverage without quantile semantics) | Q1 contract §9.6 |
| `SUSTAINED_7DAY_PEAK_CONTRACT` | `CONFIRMED` (definition only, no implementation) | Q1 contract §7 |
| `CURRENT_3DAY_CONTRACT_STATUS` | `CONFIRMED` (current production contract) | Q1 contract §8 + audit doc §B |
| `7DAY_MIGRATION_REQUIRED` | `YES` (separate Q3 round) | Q1 contract §8.3 |
| `REAL_DATA_COVERAGE_STATUS` | `BLOCKED_BY_DATA` (this round is docs-only; no live database access) | Q1 contract §10 + audit doc §H |
| `Q2_READINESS` | `READY` (Q1 freeze is complete; Q2 design and implementation requires separate Charles authorization) | Q1 contract §12.1 |

---

## §2 Forbidden-action check (Q1 §13)

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
| silently rename `sustained_3day_peak` to `sustained_7day_peak` | `NOT_EXECUTED` | the new commit does not modify the 3-day field |
| close Issue #99 | `NOT_EXECUTED` | `gh issue view 99 --json state` is `OPEN` |
| close Issue #102 | `NOT_EXECUTED` | `gh issue view 102 --json state` is `OPEN` |
| re-open PR #101 | `NOT_EXECUTED` | `gh pr view 101 --json state` is `CLOSED` |
| mark the Q1 Draft PR as Ready | `NOT_EXECUTED` | the Q1 Draft PR is in `OPEN / Draft / NOT MERGED` state |
| merge the Q1 Draft PR | `NOT_EXECUTED` | the Q1 Draft PR is `NOT MERGED` |
| delete the PR #101 branch | `NOT_EXECUTED` | the branch `docs/task-013-slice-c-c2-business-source-definition` is preserved on `origin` |
| delete the PR #101 worktree | `NOT_EXECUTED` | the worktree `/tmp/task-013-c2-source-definition` is preserved |
| delete the Q1 worktree | `NOT_EXECUTED` | the worktree `/tmp/issue-102-slice-q1-forecast-evaluation-contract` is preserved |
| delete the prototype worktree | `NOT_EXECUTED` | the worktree `/tmp/task-013-c2-concept-ui-v1` is preserved |
| delete any untracked file in the main worktree | `NOT_EXECUTED` | the 4 untracked files in the main worktree are preserved (`.config/`, `.hermes/`, `.venv-3.12/`, `pr90-p0-fix-final-report-2026-07-10.md`) |
| output sensitive real business data | `NOT_EXECUTED` | the Q1 documents do not contain any farm name, subfarm name, variety name, operator name, exact daily quantity, or exact forecast output |
| claim the 7-day peak is implemented | `NOT_EXECUTED` | the Q1 contract document and this audit document both state `SUSTAINED_7DAY_IMPLEMENTED = NO` |
| claim the forecast accuracy has improved | `NOT_EXECUTED` | the Q1 contract document and this audit document both state `MODEL_CHANGE_NOT_AUTHORIZED` |
| fabricate real-data coverage | `NOT_EXECUTED` | the data-coverage matrix is explicitly marked `PENDING_REAL_DATABASE_QUERY`; the audit does not access a live database |

---

## §3 Sign-off (to be completed by Charles upon acceptance)

```text
SLICE_Q1_DECISION_TABLE_ACCEPTED
PRIMARY_FORECAST_TARGET_CONFIRMED
CURRENT_MODEL_PRIMARY_OUTPUT_CONFIRMED
TARGET_OUTPUT_ALIGNMENT_NOT_PROVEN_EQUIVALENT
ACTUAL_LABEL_STATUS_BLOCKED_BY_SCHEMA_AND_POINT_IN_TIME_GAP
ACTUAL_LABEL_SUPPORTED_GRAIN_FACT_RECEIPT_DAILY_RECEIPT_NOT_PICK
POINT_IN_TIME_STATUS_BLOCKED_BY_POINT_IN_TIME_GAP
P50_P80_P90_SEMANTICS_NOT_VERIFIED
QUANTILE_COVERAGE_STATUS_BLOCKED_BY_POINT_IN_TIME_GAP
SUSTAINED_7DAY_PEAK_CONTRACT_CONFIRMED_DEFINITION_ONLY
CURRENT_3DAY_CONTRACT_STATUS_CONFIRMED
7DAY_MIGRATION_REQUIRED_YES_Q3_ROUND
REAL_DATA_COVERAGE_STATUS_BLOCKED_BY_DATA
Q2_READINESS_READY_PENDING_SEPARATE_CHARLES_AUTHORIZATION
```

(Charles to amend the above with explicit `ACCEPTED` or `REVISED` markers.)
