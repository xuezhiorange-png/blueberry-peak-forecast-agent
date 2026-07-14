# Slice Q1 — Data Coverage Audit (Companion to Q1 Contract)

| Field | Value |
|---|---|
| Document ID | `slice-q1-data-coverage-audit` |
| Document version | v1 (Q1 design-only, read-only audit) |
| Document status | `DRAFT — Q1 design-only, awaiting Charles re-review` |
| Tracking Issue | `#102` (OPEN) |
| Q1 authorization comment | `IC_kwDOS_gTTs8AAAABKDOkiQ` (id `4969440393`) on Issue #102 |
| Working base | `origin/main` at `2e860511dd9279d0aa3c64dd760bea8531fad458` |
| Working branch | `docs/issue-102-slice-q1-forecast-evaluation-contract` |
| Working worktree | `/tmp/issue-102-slice-q1-forecast-evaluation-contract` |
| Companion document | `docs/forecast-quality/slice-q1-forecast-target-and-evaluation-contract.md` |
| Audit type | Read-only. No live database access in this round. |

> This document is the Q1 read-only audit of the data sources, the schema, the migrations, the fixtures, the Goldens, the tests, and the production-wired surfaces in `origin/main` at `2e86051`. The audit does not access a live database, a staging database, a local development database, or any fixture for the purpose of fabricating real-data coverage. Where the audit cannot access a live database, the row is marked `BLOCKED_BY_DATA`.

---

## §A. Migration history (against `origin/main`)

The 16 migrations on `origin/main`:

| Revision | Description (as authored) | Status |
|---|---|---|
| `0001_task0_baseline.py` | TASK-0 baseline | `RESOLVED_BY_MERGED_AUTHORITY` |
| `0002_master_data.py` | Master-data dim tables (season, factory, farm, subfarm, variety, grade, holiday) | `RESOLVED_BY_MERGED_AUTHORITY` |
| `0003_historical_ingest.py` | ETL raw (ingest_file, fact_receipt_raw) | `RESOLVED_BY_MERGED_AUTHORITY` |
| `0004_daily_facts_peak_metrics.py` | analytics_build_run, fact_receipt_daily, factory_season_peak_metric | `RESOLVED_BY_MERGED_AUTHORITY` |
| `0005_baseline_backtest.py` | baseline-backtest supporting tables | `RESOLVED_BY_MERGED_AUTHORITY` |
| `0006_minimal_input_parameters.py` | minimal-input parameter inference supporting tables | `RESOLVED_BY_MERGED_AUTHORITY` |
| `0007_prod_plan_phenology.py` | production plan and phenology | `RESOLVED_BY_MERGED_AUTHORITY` |
| `0008_weather_timeline.py` | weather timeline | `RESOLVED_BY_MERGED_AUTHORITY` |
| `0009_natural_maturity_curve.py` | TASK-008 natural maturity curve | `RESOLVED_BY_MERGED_AUTHORITY` |
| `0010_harvest_state_persistence.py` | TASK-009 harvest-state persistence | `RESOLVED_BY_MERGED_AUTHORITY` |
| `0011_residual_model.py` | TASK-010 residual model | `RESOLVED_BY_MERGED_AUTHORITY` |
| `0012_rolling_backtest.py` | TASK-011 rolling backtest | `RESOLVED_BY_MERGED_AUTHORITY` |
| `0013_rolling_backtest_orchestration.py` | TASK-011 orchestration | `RESOLVED_BY_MERGED_AUTHORITY` |
| `0014_task9_historical_authority.py` | TASK-009 historical authority | `RESOLVED_BY_MERGED_AUTHORITY` |
| `0015_task11_phase3_schema_gap.py` | TASK-011 phase 3 schema gap (5 typed nullable replay-marking columns on `harvest_state_run` + `harvest_state_replay_source_visibility_audit`) | `RESOLVED_BY_MERGED_AUTHORITY` |

Total: 15 migrations (note: the file listing in `git ls-tree` shows 16 entries, of which 1 is `__pycache__`; there are 15 actual migration files).

The full migration list is verified by `git ls-tree -r --name-only origin/main backend/alembic/versions/`.

---

## §B. 3-day production contract inventory (against round §9)

This section is the full inventory of every `sustained_3day` / `strict_three_day_window` / `sustained_window_days` / `peak_window_cumulative_quantity` / `rolling_3day` reference in `origin/main`.

### §B.1 `sustained_3day` references

The grep `grep -rn "sustained_3day" backend/ docs/` on `origin/main` (excluding `__pycache__`) returns the following matches. Each row is verified by `git grep -n` on `origin/main`.

| File | Line | Context | Classification |
|---|---:|---|---|
| `backend/app/agent/schemas.py` | ~981 | `sustained_3day_peak: dict[ForecastQuantile, SustainedPeakEntry]` | `CURRENT_PRODUCTION_CONTRACT` (schema field) |
| `backend/app/agent/schemas.py` | ~1016 | `sustained_3day_daily_average_delta_kg_per_day: ScenarioDeltaQuantiles` | `CURRENT_PRODUCTION_CONTRACT` (scenario delta) |
| `backend/app/agent/schemas.py` | ~1017 | `sustained_3day_cumulative_delta_kg: ScenarioDeltaQuantiles` | `CURRENT_PRODUCTION_CONTRACT` (scenario delta) |
| `backend/app/agent/adapters/peak.py` | ~11 | docstring: `sustained_3day_peak[q] = maximum rolling three-day arithmetic mean` | `CURRENT_PRODUCTION_CONTRACT` (adapter docstring) |
| `backend/app/agent/adapters/peak.py` | ~103 | `def _sustained_3day_peak(...)` | `CURRENT_PRODUCTION_CONTRACT` (adapter function) |
| `backend/app/agent/adapters/peak.py` | ~318 | `sustained_3day: dict[ForecastQuantile, SustainedPeakEntry] = {}` | `CURRENT_PRODUCTION_CONTRACT` (adapter body) |
| `backend/app/agent/adapters/peak.py` | ~339 | `sus = _sustained_3day_peak(...)` | `CURRENT_PRODUCTION_CONTRACT` (adapter call) |
| `backend/app/agent/adapters/peak.py` | ~349 | `sustained_3day[q] = sus` | `CURRENT_PRODUCTION_CONTRACT` (adapter body) |
| `backend/app/agent/adapters/peak.py` | ~390 | `"sustained_3day_peak": { ... }` (output JSON) | `CURRENT_PRODUCTION_CONTRACT` (adapter output) |
| `backend/app/agent/adapters/peak.py` | ~397 | iteration over `sustained_3day.items()` | `CURRENT_PRODUCTION_CONTRACT` (adapter output) |
| `backend/app/agent/adapters/peak.py` | ~423 | `sustained_3day_peak=sustained_3day` (return) | `CURRENT_PRODUCTION_CONTRACT` (adapter return) |
| `backend/app/agent/adapters/scenario.py` | ~30 | docstring | `CURRENT_PRODUCTION_CONTRACT` (scenario docstring) |
| `backend/app/agent/adapters/scenario.py` | ~31 | docstring | `CURRENT_PRODUCTION_CONTRACT` (scenario docstring) |
| `backend/app/agent/adapters/scenario.py` | ~32 | docstring: `never outputs a single scalar sustained_3day_delta` | `CURRENT_PRODUCTION_CONTRACT` (scenario docstring) |
| `backend/app/agent/adapters/scenario.py` | ~356 | `sus = peak_output.sustained_3day_peak` | `CURRENT_PRODUCTION_CONTRACT` (scenario body) |
| `backend/app/agent/slice_c/engine.py` (PR #100) | n/a (exact line not verified in this audit) | C1 contract references `sustained_3day_peak` via the ForecastPeakOutput schema | `CURRENT_PRODUCTION_CONTRACT` (C1 contract) |
| `backend/tests/agent/golden/task013_slice_c_output.json` | n/a | golden key `sustained_3day_peak` | `CURRENT_PRODUCTION_CONTRACT` (C1 Golden) |
| `backend/tests/agent/golden/task013_composed_agent_output.json` | n/a | composed Golden | `CURRENT_PRODUCTION_CONTRACT` (C1 composed Golden) |
| `backend/tests/integration/agent/test_slice_c_orchestration_postgres.py` | n/a | PostgreSQL acceptance | `CURRENT_PRODUCTION_CONTRACT` (PostgreSQL acceptance) |

### §B.2 `strict_three_day_window` references

| File | Line | Context | Classification |
|---|---:|---|---|
| `backend/app/agent/schemas.py` | ~843 | `strict_three_day_window: Literal[True] = True` | `CURRENT_PRODUCTION_CONTRACT` (policy field) |
| `backend/app/agent/schemas.py` | ~846 | `@model_validator def _enforce_strict_three_day_window(self)` | `CURRENT_PRODUCTION_CONTRACT` (validator) |
| `backend/app/agent/schemas.py` | ~847 | `if self.strict_three_day_window and self.sustained_window_days != 3:` | `CURRENT_PRODUCTION_CONTRACT` (validator body) |
| `backend/app/agent/schemas.py` | ~848 | `raise ValueError("strict_three_day_window=True forces sustained_window_days == 3")` | `CURRENT_PRODUCTION_CONTRACT` (validator body) |
| `backend/app/agent/adapters/peak.py` | ~308 | `if policy.strict_three_day_window and policy.sustained_window_days != 3:` | `CURRENT_PRODUCTION_CONTRACT` (adapter body) |
| `backend/app/agent/adapters/peak.py` | ~312 | `message=("strict_three_day_window=True requires sustained_window_days == 3")` | `CURRENT_PRODUCTION_CONTRACT` (adapter body) |

### §B.3 `sustained_window_days` references

| File | Line | Context | Classification |
|---|---:|---|---|
| `backend/app/agent/schemas.py` | ~836 | `sustained_window_days: int = Field(ge=1)` | `CURRENT_PRODUCTION_CONTRACT` (policy field) |
| `backend/app/agent/schemas.py` | ~846–848 | validator enforcing `sustained_window_days == 3` when `strict_three_day_window` is True | `CURRENT_PRODUCTION_CONTRACT` (validator) |
| `backend/app/agent/schemas.py` | ~980 | `sustained_window_days: int = Field(ge=1)` (in `ForecastPeakOutput`) | `CURRENT_PRODUCTION_CONTRACT` (output field) |
| `backend/app/agent/adapters/peak.py` | ~308–312 | adapter enforcing `sustained_window_days == 3` | `CURRENT_PRODUCTION_CONTRACT` (adapter) |
| `backend/app/agent/adapters/peak.py` | ~411 | `"sustained_window_days": policy.sustained_window_days` (output JSON) | `CURRENT_PRODUCTION_CONTRACT` (adapter output) |
| `backend/app/agent/adapters/peak.py` | ~422 | `sustained_window_days=policy.sustained_window_days` (return) | `CURRENT_PRODUCTION_CONTRACT` (adapter return) |

### §B.4 `peak_window_cumulative_quantity` references

| File | Line | Context | Classification |
|---|---:|---|---|
| `backend/app/agent/schemas.py` | ~984 | `peak_window_cumulative_quantity_kg: dict[ForecastQuantile, DecimalString]` | `CURRENT_PRODUCTION_CONTRACT` (output field, three-day sum inside the peak window) |

### §B.5 `rolling_3day` references

No matches found on `origin/main` (excluding `__pycache__`).

### §B.6 `3-day peak` / `连续 3 天` / `三日峰值` references

No matches found in code on `origin/main`. The matches in `docs/task-013-minimal-input-deterministic-agent-orchestration-design.md` are `DOCUMENTATION_ONLY` (legacy design).

### §B.7 Total count and downstream consumers

```
CURRENT_3DAY_CONTRACT_REFERENCE_COUNT = (see §B.1 + §B.2 + §B.3 + §B.4; total is 25+)
```

Downstream consumers of the 3-day field:

- `ForecastPeakOutput` (schema) — `CURRENT_PRODUCTION_CONTRACT`.
- `SimulateScenarioDelta` (schema) — `CURRENT_PRODUCTION_CONTRACT`.
- `peak.py` adapter — `CURRENT_PRODUCTION_CONTRACT`.
- `scenario.py` adapter — `CURRENT_PRODUCTION_CONTRACT`.
- `slice_c/engine.py` (C1 contract) — `CURRENT_PRODUCTION_CONTRACT`.
- C1 Golden `task013_slice_c_output.json` — `CURRENT_PRODUCTION_CONTRACT`.
- C1 composed Golden `task013_composed_agent_output.json` — `CURRENT_PRODUCTION_CONTRACT`.
- C1 PostgreSQL acceptance `test_slice_c_orchestration_postgres.py` — `CURRENT_PRODUCTION_CONTRACT`.

Q1 does not modify any of these. The 3-day field semantics are preserved verbatim. The migration to a 7-day field is a separate Q3 round.

---

## §C. Schema inventory (against `origin/main`)

This section lists the first-class tables and first-class schema fields that are relevant to the Q1 contract. Each row is verified by `git show origin/main:...` and by `git ls-tree -r --name-only origin/main backend/app/models/`.

### §C.1 Master-data dim tables

| Table | File | Migration | Verified |
|---|---|---|---|
| `dim_season` | `backend/app/models/master_data.py` | `0002_master_data.py` | YES |
| `dim_factory` | `backend/app/models/master_data.py` | `0002_master_data.py` | YES |
| `dim_farm` | `backend/app/models/master_data.py` | `0002_master_data.py` | YES |
| `dim_subfarm` | `backend/app/models/master_data.py` | `0002_master_data.py` | YES |
| `dim_variety` | `backend/app/models/master_data.py` | `0002_master_data.py` | YES |
| `dim_grade` | `backend/app/models/master_data.py` | `0002_master_data.py` | YES |
| `dim_holiday` | `backend/app/models/master_data.py` | `0002_master_data.py` | YES |

### §C.2 Fact tables

| Table | File | Migration | Verified |
|---|---|---|---|
| `ingest_file` | `backend/app/models/historical_import.py` | `0003_historical_ingest.py` | YES |
| `fact_receipt_raw` | `backend/app/models/historical_import.py` | `0003_historical_ingest.py` | YES |
| `analytics_build_run` | `backend/app/models/analytics.py` | `0004_daily_facts_peak_metrics.py` | YES |
| `fact_receipt_daily` | `backend/app/models/analytics.py` | `0004_daily_facts_peak_metrics.py` | YES |
| `factory_season_peak_metric` | `backend/app/models/analytics.py` | `0004_daily_facts_peak_metrics.py` | YES |
| `harvest_state_run` | `backend/app/models/harvest_state.py` | `0010_harvest_state_persistence.py` | YES |
| `harvest_state_replay_source_visibility_audit` | `backend/app/models/harvest_state.py` | `0015_task11_phase3_schema_gap.py` | YES |
| `harvest_state_daily_pool_row` | `backend/app/models/harvest_state.py` | `0010_harvest_state_persistence.py` | YES |
| `harvest_state_daily_member_row` | `backend/app/models/harvest_state.py` | `0010_harvest_state_persistence.py` | YES |
| `harvest_state_cohort_transition_row` | `backend/app/models/harvest_state.py` | `0010_harvest_state_persistence.py` | YES |
| `harvest_state_future_arrival_row` | `backend/app/models/harvest_state.py` | `0010_harvest_state_persistence.py` | YES |

### §C.3 Forecast-output schema (not persisted; produced by `AgentOrchestrator`)

| Class | File | Field | Verified |
|---|---|---|---|
| `ForecastDailyRow` | `schemas.py` | `natural_maturity_quantity_kg: DailyQuantiles` | YES |
| `ForecastDailyRow` | `schemas.py` | `harvested_quantity_kg: DailyQuantiles` | YES |
| `ForecastDailyRow` | `schemas.py` | `closing_mature_inventory_kg: DailyQuantiles` | YES |
| `ForecastDailyRow` | `schemas.py` | `unharvested_backlog_kg: DailyQuantiles` | YES |
| `ForecastDailyRow` | `schemas.py` | `arrival_quantity_kg: DailyQuantiles` | YES |
| `ForecastDailyRow` | `schemas.py` | `final_corrected_arrival_quantity_kg: DailyQuantiles` | YES |
| `ForecastDailyRow` | `schemas.py` | `per_variety_contribution: list[VarietyContribution]` | YES |
| `ForecastDailyRow` | `schemas.py` | `weather_tags: tuple[str, ...]` | YES |
| `ForecastDailyRow` | `schemas.py` | `spring_festival_phase: SpringFestivalPhase = "NONE"` | YES |
| `ForecastDailyRow` | `schemas.py` | `agent_daily_row_hash: SHA256Hex` | YES |
| `ForecastPeakOutput` | `schemas.py` | `peak_metric_policy_version: str` | YES |
| `ForecastPeakOutput` | `schemas.py` | `peak_metric_policy_config_hash: SHA256Hex` | YES |
| `ForecastPeakOutput` | `schemas.py` | `agent_peak_hash: SHA256Hex` | YES |
| `ForecastPeakOutput` | `schemas.py` | `single_day_peak: dict[ForecastQuantile, SingleDayPeakEntry]` | YES |
| `ForecastPeakOutput` | `schemas.py` | `sustained_window_days: int = Field(ge=1)` | YES |
| `ForecastPeakOutput` | `schemas.py` | `sustained_3day_peak: dict[ForecastQuantile, SustainedPeakEntry]` | YES |
| `ForecastPeakOutput` | `schemas.py` | `peak_window_days_before: int = Field(ge=0)` | YES |
| `ForecastPeakOutput` | `schemas.py` | `peak_window_days_after: int = Field(ge=0)` | YES |
| `ForecastPeakOutput` | `schemas.py` | `peak_window_cumulative_quantity_kg: dict[ForecastQuantile, DecimalString]` | YES |
| `ForecastPeakOutput` | `schemas.py` | `peak_duration_days: dict[ForecastQuantile, int]` | YES |
| `ForecastPeakOutput` | `schemas.py` | `high_load_threshold: dict[ForecastQuantile, DecimalString]` | YES |
| `ForecastPeakOutput` | `schemas.py` | `dominant_variety: dict[ForecastQuantile, DominantVarietyEntry]` | YES |
| `ForecastPeakOutput` | `schemas.py` | `peak_formation_explanation_ref: str \| None` | YES |
| `ForecastPeakOutput` | `schemas.py` | `blockers: list[Blocker]` | YES |
| `PeakMetricPolicy` | `schemas.py` | `sustained_window_days: int = Field(ge=1)` | YES |
| `PeakMetricPolicy` | `schemas.py` | `sustained_metric: Literal["ROLLING_DAILY_AVERAGE"]` | YES |
| `PeakMetricPolicy` | `schemas.py` | `tie_break: Literal["EARLIEST_START_DATE"]` | YES |
| `PeakMetricPolicy` | `schemas.py` | `peak_window_days_before: int = Field(ge=0)` | YES |
| `PeakMetricPolicy` | `schemas.py` | `peak_window_days_after: int = Field(ge=0)` | YES |
| `PeakMetricPolicy` | `schemas.py` | `high_load_reference: Literal["SINGLE_DAY_PEAK"]` | YES |
| `PeakMetricPolicy` | `schemas.py` | `high_load_threshold_ratio: DecimalString` | YES |
| `PeakMetricPolicy` | `schemas.py` | `strict_three_day_window: Literal[True] = True` | YES |
| `ParameterEstimate` | `schemas.py` | `parameter_name: str` | YES |
| `ParameterEstimate` | `schemas.py` | `variety_id: str` | YES |
| `ParameterEstimate` | `schemas.py` | `p50 / p80_lower / p80_upper` | YES |
| `ParameterEstimate` | `schemas.py` | `source_level: int = Field(ge=1, le=5)` | YES |
| `ParameterEstimate` | `schemas.py` | `confidence / confidence_score` | YES |
| `ParameterEstimate` | `schemas.py` | `sample_count / season_count / farm_count` | YES |
| `ParameterEstimate` | `schemas.py` | `source_observation_ids / fallback_below_minimum / missing_evidence` | YES |
| `ParameterEstimate` | `schemas.py` | `prior_version / distribution_kind / citation` | YES |

### §C.4 7-day peak fields — NOT present

The grep `grep -rn "sustained_7day\|7day_peak\|7_day_peak\|seven_day" backend/ docs/ origin/main:` on `origin/main` (excluding `__pycache__`) returns no production-code matches. The only matches are in the Q1 design document and in the audit report. The 7-day peak field is not yet first-class.

---

## §D. Actual-label candidate audit

### §D.1 First-class operator-entered daily fact: `fact_receipt_daily`

`fact_receipt_daily` is the only first-class operator-entered daily fact in `origin/main`. Its schema is:

```
UniqueConstraint("uq_fact_receipt_daily_build_grain"):
    (build_run_id, season_id, receipt_date, factory_id, farm_key, subfarm_key, variety_id)
CheckConstraint("ck_fact_receipt_daily_weight_positive"):
    weight_kg > 0
CheckConstraint("ck_fact_receipt_daily_source_row_count_positive"):
    source_row_count > 0
Index("ix_fact_receipt_daily_season_factory_date"):
    (season_id, factory_id, receipt_date)
```

The CHECK `weight_kg > 0` is structurally significant: an explicit zero-receipt day is NOT a row in `fact_receipt_daily`. A zero-receipt day is a missing row.

The schema does not carry `recorded_at`, `effective_at`, `revised_at`, `revision_number`, `supersedes_record_id`, or `is_deleted_or_voided`. The only revision mechanism is the `analytics_build_run` re-build sequence.

### §D.2 ACTUAL_LABEL_STATUS verdict

```
ACTUAL_LABEL_STATUS = SCHEMA_GAP / SOURCE_GAP / POINT_IN_TIME_GAP / REVISION_HISTORY_GAP
ACTUAL_LABEL_SUPPORTED_GRAIN = fact_receipt_daily at (build_run_id, season_id, factory_id, receipt_date, farm_key, subfarm_key, variety_id, weight_kg > 0) — receipt, not pick
```

### §D.3 What `fact_receipt_daily` is and is not

- IS: an operator-entered daily receipt / arrival fact at the factory gate, with a build-run identity and a unique-constraint grain, with a positive-only weight CHECK.
- IS NOT: a daily actual-harvest fact at the orchard. The physical meaning is "arrival at the factory gate", not "pick at the orchard".
- IS NOT: a fact with point-in-time visibility. There is no `recorded_at`, `effective_at`, `revised_at`, `revision_number`, `supersedes_record_id`, or `is_deleted_or_voided`.
- IS NOT: a fact with row-level revision. The only revision mechanism is re-build, which is an analytics concept, not a row-level revision.
- IS NOT: a daily-actual-harvest primary label for the P0 evaluation contract. It is the closest available fact, but it is `PROXY_LABEL` for `actual_harvest_quantity`. The Q1 design does not adopt the proxy.

### §D.4 First-class `actual_harvest_daily` table — NOT present

There is no first-class `actual_harvest_daily` table in `origin/main`. The Q1 design-freeze proposes the canonical fields in §6.3 of the Q1 contract document; Q2 / Q3 design and implementation must decide whether to add the table.

---

## §E. Harvest-state schema audit (against `origin/main`)

The TASK-009 harvest-state schema consists of 6 tables:

| Table | File | Migration | Verified |
|---|---|---|---|
| `harvest_state_run` | `backend/app/models/harvest_state.py` | `0010_harvest_state_persistence.py` | YES |
| `harvest_state_replay_source_visibility_audit` | `backend/app/models/harvest_state.py` | `0015_task11_phase3_schema_gap.py` | YES |
| `harvest_state_daily_pool_row` | `backend/app/models/harvest_state.py` | `0010_harvest_state_persistence.py` | YES |
| `harvest_state_daily_member_row` | `backend/app/models/harvest_state.py` | `0010_harvest_state_persistence.py` | YES |
| `harvest_state_cohort_transition_row` | `backend/app/models/harvest_state.py` | `0010_harvest_state_persistence.py` | YES |
| `harvest_state_future_arrival_row` | `backend/app/models/harvest_state.py` | `0010_harvest_state_persistence.py` | YES |

The 5 typed nullable replay-marking columns on `harvest_state_run` are added in `0015_task11_phase3_schema_gap.py`.

`harvest_state_daily_pool_row.harvested_quantity_kg` and `harvest_state_daily_member_row.harvested_quantity_kg` are TASK-009 model output, not user-entered actual harvest.

---

## §F. Fixture and Golden audit

| File | Classification | Source | Notes |
|---|---|---|---|
| `backend/tests/agent/golden/task013_slice_c_output.json` | `STATIC_GOLDEN` (C1 contract) | PR #100 | contains 3-day peak field; does not contain 7-day peak field |
| `backend/tests/agent/golden/task013_composed_agent_output.json` | `STATIC_GOLDEN` (C1 contract) | PR #100 | contains 3-day peak field; does not contain 7-day peak field |
| `backend/tests/agent/golden/...` (other goldens) | various | various | per-repo audit required for Q2 / Q5 |

Q1 does not audit other goldens. Q2 / Q5 must extend the Golden audit.

---

## §G. Production-wired surface audit

The production-wired surface is `AgentOrchestrator.execute(...)` in `backend/app/agent/orchestration.py`. The C1 production-wired acceptance is in `backend/tests/integration/agent/test_slice_c_orchestration_postgres.py`. The acceptance proves the Slice B → C1 chain through real PostgreSQL.

Q1 does not modify the production-wired surface. Q2 must add a point-in-time backtest runner to the production-wired surface.

---

## §H. Real-data coverage report

### §H.1 Data sources

This Q1 audit does not access:

- a live database;
- a staging database;
- a local development database;
- a configured PostgreSQL database;
- any CSV / JSON import;
- any fixture for the purpose of fabricating real-data coverage;
- any `ingest_file` or `fact_receipt_raw` content;
- any `fact_receipt_daily` content;
- any `harvest_state_run` content;
- any actual harvest observation;
- any arrival observation;
- any weather observation;
- any maturity observation.

This Q1 audit is a **static code audit** of `origin/main` at `2e86051`. The audit reads files; the audit does not run any query, any DDL, any DML, any migration, or any external service.

### §H.2 Aggregate-only coverage matrix (template)

The Q1 design-freeze proposes the following coverage matrix. Q2 / Q5 must populate this matrix against a real database.

| Field | Source | Status | Notes |
|---|---|---|---|
| `farm_count` | `dim_farm` | `PENDING_REAL_DATABASE_QUERY` | Q2 / Q5 must query |
| `subfarm_or_plot_count` | `dim_subfarm` | `PENDING_REAL_DATABASE_QUERY` | Q2 / Q5 must query |
| `variety_count` | `dim_variety` | `PENDING_REAL_DATABASE_QUERY` | Q2 / Q5 must query |
| `season_count` | `dim_season` | `PENDING_REAL_DATABASE_QUERY` | Q2 / Q5 must query |
| `date_min` | `fact_receipt_daily.receipt_date` | `PENDING_REAL_DATABASE_QUERY` | Q2 / Q5 must query |
| `date_max` | `fact_receipt_daily.receipt_date` | `PENDING_REAL_DATABASE_QUERY` | Q2 / Q5 must query |
| `daily_row_count` | `fact_receipt_daily` | `PENDING_REAL_DATABASE_QUERY` | Q2 / Q5 must query |
| `nonzero_day_count` | `fact_receipt_daily` (implicit: `weight_kg > 0`) | `PENDING_REAL_DATABASE_QUERY` | Q2 / Q5 must query |
| `explicit_zero_day_count` | `fact_receipt_daily` (structurally 0 because of `weight_kg > 0` CHECK) | `STRUCTURAL_ZERO` | the CHECK forces all rows to be `weight_kg > 0`; explicit-zero days are missing rows |
| `missing_day_count` | derived from `season` × `date_min..date_max` minus `daily_row_count` | `PENDING_REAL_DATABASE_QUERY` | Q2 / Q5 must compute |
| `duplicate_key_count` | `fact_receipt_daily` (unique constraint enforces 0) | `STRUCTURAL_ZERO` | the unique constraint `uq_fact_receipt_daily_build_grain` enforces 0 duplicates |
| `revision_count` | n/a (no `revised_at` column) | `NOT_AVAILABLE` | `fact_receipt_daily` does not carry row-level revision |
| `late_revision_count` | n/a (no `revised_at` column) | `NOT_AVAILABLE` | same as `revision_count` |
| `records_with_recorded_at` | n/a (no `recorded_at` column) | `NOT_AVAILABLE` | `fact_receipt_daily` does not carry `recorded_at` |
| `records_with_revised_at` | n/a (no `revised_at` column) | `NOT_AVAILABLE` | same |
| `usable_backtest_series_count` | derived from the gate in Q1 contract §6.7 | `PENDING_REAL_DATABASE_QUERY` | Q2 / Q5 must compute |

### §H.3 Backtest usability gate (recap)

A series is `usable_backtest_series` if and only if all of the following hold:

- grain identity is complete;
- date-continuity rule is explicit;
- actual label is not a proxy, or the proxy is explicitly accepted and disclosed;
- unit is consistent (kg);
- no unresolved duplicate;
- point-in-time visibility is verifiable for the chosen forecast-cutoff `T`;
- forecast cutoff `T` is bindable to a specific replay identity;
- at least one full 7-day target window is present;
- the actual label and the forecast output are alignable at the same grain.

The current `fact_receipt_daily` does not satisfy the grain identity (no `subfarm_or_plot_id`), the point-in-time visibility (no `recorded_at`, `effective_at`, `revised_at`, `revision_number`, `supersedes_record_id`), the explicit-zero handling (structurally excluded), or the row-level revision (re-build only). The `usable_backtest_series_count` against `fact_receipt_daily` is `0` by the Q1 gate.

```
REAL_DATA_COVERAGE_STATUS = BLOCKED_BY_DATA (this round is docs-only; no live database access)
USABLE_BACKTEST_SERIES_COUNT_AGAINST_FACT_RECEIPT_DAILY = 0 (by the Q1 gate; re-build mechanism is not row-level revision; explicit zero days are missing rows; subfarm_or_plot_id is not a column)
```

### §H.4 Desensitization note

The Q1 design-freeze does not output any sensitive real business data. No farm name, no subfarm name, no variety name (other than the public `dim_variety` table), no operator name, no exact daily quantity, no exact forecast output, and no exact row count on real data is reported. The Q2 / Q5 report must apply the same desensitization policy.

---

## §I. Forbidden action evidence (against Q1 hard exclusions)

The Q1 round ran the following forbidden-action verification:

| Forbidden action | Verification command | Result |
|---|---|---|
| modify any production code under `backend/app/**` | `git diff --name-only origin/main -- backend/app/` | empty |
| modify any test under `backend/tests/**` | `git diff --name-only origin/main -- backend/tests/` | empty |
| add or modify any migration under `backend/alembic/**` | `git diff --name-only origin/main -- backend/alembic/` | empty |
| modify any Golden file | `git diff --name-only origin/main -- '**/golden/**'` | empty |
| modify any frontend, dependency, or workflow | `git diff --name-only origin/main -- frontend/ .github/` | empty |
| modify dependency files | `git diff --name-only origin/main -- 'pyproject.toml' 'requirements*.txt' 'package.json' 'package-lock.json'` | empty |
| modify any database file or script under `scripts/` | `git diff --name-only origin/main -- scripts/ backend/app/db/ '**/database/**'` | empty |
| modify TASK-013 C2 document on PR #101 branch | `git -C /tmp/task-013-c2-source-definition status` | the PR #101 worktree is not modified by Q1 |
| modify the prototype branch | `git -C /tmp/task-013-c2-concept-ui-v1 status` | the prototype worktree is not modified by Q1 |
| close Issue #99 | `gh issue view 99 --json state` | OPEN |
| close Issue #102 | `gh issue view 102 --json state` | OPEN |
| re-open PR #101 | `gh pr view 101 --json state` | CLOSED |
| mark the Q1 Draft PR as Ready | (Q1 has not pushed the Draft PR yet; this is verified in the final report) | not yet pushed |
| merge the Q1 Draft PR | (Q1 has not pushed the Draft PR yet) | not yet pushed |
| delete the PR #101 branch | `git ls-remote origin refs/heads/docs/task-013-slice-c-c2-business-source-definition` | present |
| delete the PR #101 worktree | `git worktree list` | present |
| delete the Q1 worktree | `git worktree list` | the Q1 worktree is created in Q1, preserved |
| delete the prototype worktree | `git worktree list` | present |
| delete any untracked file in the main worktree | `git -C /root/blueberry-peak-forecast-agent status --short` | 4 untracked files present |
| output sensitive real business data | this document does not contain any farm name, subfarm name, variety name, operator name, exact daily quantity, or exact forecast output | compliant |
| claim 7-day peak is implemented | the Q1 contract document and this audit document both state `SUSTAINED_7DAY_IMPLEMENTED = NO` | compliant |
| claim forecast accuracy has improved | the Q1 contract document and this audit document both state `MODEL_CHANGE_NOT_AUTHORIZED` | compliant |
| fabricate real-data coverage | the data-coverage matrix in §H.2 is explicitly marked `PENDING_REAL_DATABASE_QUERY`; the audit does not access a live database | compliant |

---

## §J. Test and CI evidence

The Q1 round does not add, modify, or run any test. The Q1 round does not run CI. The Q1 round does not modify any CI workflow. The Q1 round does not access any CI artifact.

The CI for the Q1 Draft PR, when pushed, will be the standard PR CI defined in `.github/workflows/ci.yml`. The Q1 Draft PR is expected to satisfy:

- `compose-config` (job)
- `frontend` (job)
- `postgres-domain-1` (job)
- `postgres-domain-2` (job)
- `backend-sqlite` (job)
- `backend-postgresql` (job)
- `unit-contract-golden` (job)
- `full-suite-canary` (skipped by PR-event design)

Q1 does not claim any of these jobs is green until the CI report is observed.

---

## §K. Change log

| Date | Round | Author | Change |
|---|---|---|---|
| 2026-07-14 | v1 (Q1) | Charles-authorized Q1 design-only round | Initial creation. Migration history (15 files). 3-day production contract inventory (full). Schema inventory (ForecastDailyRow + ForecastPeakOutput + ParameterEstimate). Actual-label candidate audit (fact_receipt_daily as closest first-class fact, with structural zero-day and point-in-time gaps). Data-coverage matrix template. Forbidden-action evidence. |

---

## §L. Sign-off (to be completed by Charles upon acceptance)

```text
SLICE_Q1_DATA_COVERAGE_AUDIT_ACCEPTED
MIGRATION_HISTORY_VERIFIED
3DAY_PRODUCTION_CONTRACT_INVENTORY_VERIFIED
ACTUAL_LABEL_CANDIDATE_AUDIT_VERIFIED
REAL_DATA_COVERAGE_BLOCKED_BY_DATA
Q2_REAL_DATA_COVERAGE_QUERY_REQUIRED
```

(Charles to amend the above with explicit `ACCEPTED` or `REVISED` markers.)
