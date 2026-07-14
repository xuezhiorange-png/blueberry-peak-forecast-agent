# Slice Q1 — Data Coverage Audit (Companion to Q1 Contract)

| Field | Value |
|---|---|---|
| Document ID | `slice-q1-data-coverage-audit` |
| Document version | v1.2 (Q1 final contract docs-only fixup per review 4695151631) |
| Document status | `DRAFT — Q1 final fixup applied, awaiting Charles re-review` |
| Tracking Issue | `#102` (OPEN) |
| Working base | `origin/main` at `2e860511dd9279d0aa3c64dd760bea8531fad458` |
| Working branch | `docs/issue-102-slice-q1-forecast-evaluation-contract` |
| Working worktree | `/tmp/issue-102-slice-q1-forecast-evaluation-contract` |
| Companion document | `docs/forecast-quality/slice-q1-forecast-target-and-evaluation-contract.md` |
| Audit type | Read-only against `origin/main` and against the configured PostgreSQL. No live mutation. |

> This document is the Q1 read-only audit of the data sources, the schema, the migrations, the fixtures, the Goldens, the tests, and the production-wired surfaces in `origin/main` at `2e86051`. The audit also includes a live-database discovery result against the configured PostgreSQL. Where the audit cannot access data (or where the data is empty), the row is marked `NOT_VERIFIED_EMPTY_DATABASE` with explicit evidence. The audit also tracks the actual-harvest label and arrival proxy separation per review 4695151631 P0-4.

---

## §A. Migration history (against `origin/main`)

The 15 migrations on `origin/main`:

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

Total: 15 migrations.

The full migration list is verified by `git ls-tree -r --name-only origin/main backend/alembic/versions/`.

---

## §B. 3-day production contract inventory (against round §9, preserved in v1.2)

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
THREE_DAY_METRIC_STATUS = LEGACY_COMPATIBILITY_METRIC
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

Q1 v1.2 does not modify any of these. The 3-day field semantics are preserved verbatim. The migration to a 7-day field is a separate Q3 round. The 3-day field is `LEGACY_COMPATIBILITY_METRIC` for the current compatibility horizon; removal requires a separate compatibility amendment.

### §B.8 7-day peak references (preserved from v1.1)

The grep `grep -rn "sustained_7day\|7day_peak\|seven_day" backend/ docs/ origin/main:` on `origin/main` (excluding `__pycache__` and the Q1 v1.2 design document) returns no production-code matches. The 7-day peak field is not yet first-class in `origin/main`.

The Q1 v1.2 design document itself contains the frozen 7-day contract (§7) and the additive-coexistence policy (§8.3). These are design only; they are not implemented in `origin/main`.

---

## §C. Schema inventory (against `origin/main`, v1.2 per review 4695151631 P0-3)

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

### §C.3 Forecast-output schema (v1.2: six quantity fields, three-grain split)

`ForecastDailyRow` contains **exactly six `DailyQuantiles` quantity fields**:

| Class | File | Field | Quantity count | Verified |
|---|---|---|---:|---|
| `ForecastDailyRow` | `schemas.py` | `natural_maturity_quantity_kg: DailyQuantiles` | 1 | YES |
| `ForecastDailyRow` | `schemas.py` | `harvested_quantity_kg: DailyQuantiles` | 2 | YES |
| `ForecastDailyRow` | `schemas.py` | `closing_mature_inventory_kg: DailyQuantiles` | 3 | YES |
| `ForecastDailyRow` | `schemas.py` | `unharvested_backlog_kg: DailyQuantiles` | 4 | YES |
| `ForecastDailyRow` | `schemas.py` | `arrival_quantity_kg: DailyQuantiles` | 5 | YES |
| `ForecastDailyRow` | `schemas.py` | `final_corrected_arrival_quantity_kg: DailyQuantiles` | 6 | YES |
| `ForecastDailyRow` | `schemas.py` | `per_variety_contribution: list[VarietyContribution]` | (nested list, NOT a 7th `DailyQuantiles` field) | YES |
| `ForecastDailyRow` | `schemas.py` | `weather_tags: tuple[str, ...]` | (metadata) | YES |
| `ForecastDailyRow` | `schemas.py` | `spring_festival_phase: SpringFestivalPhase` | (metadata) | YES |
| `ForecastDailyRow` | `schemas.py` | `agent_daily_row_hash: SHA256Hex` | (hash) | YES |
| `ForecastDailyRow` | `schemas.py` | `date: date` | (key) | YES |

`ForecastDailyRow` does NOT carry first-class `farm_id` / `subfarm_id` / `variety_id` / `season_id` columns. The row is a downstream aggregate of one resolved agent request. The farm/subfarm identity is carried by `NormalizedAgentRequest.normalized_location` and the resolved-location authority. The season identity is carried by the resolved forecast-season identity. The variety identity is carried by the request's `variety` list and the nested `per_variety_contribution`.

The six `DailyQuantiles` fields are first-class serialized output-schema fields. Q1 v1.2 does not claim they are persisted to a database table on their own; the reconstruction of the same field set from upstream TASK-008 / TASK-009 forecast runs is a separate persistence question.

| Class | File | Field | Verified |
|---|---|---|---|
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

### §C.4 7-day peak fields — NOT present in `origin/main`

The 7-day peak field is not yet first-class in `origin/main`. The Q1 v1.2 design document freezes the additive-coexistence policy (§8.3 of the Q1 contract document). The migration is a Q3 round.

### §C.5 `harvested_quantity_kg` is the `model_harvested_quantity` mapping (v1.2)

The merged `ForecastDailyRow.harvested_quantity_kg: DailyQuantiles` field is the model-predicted flow. It is NOT the `actual_harvest_quantity` business object. The two MUST NOT be conflated or renamed into each other. The Q1 v1.2 mapping table in the Q1 contract document §5.3 names the `harvested_quantity_kg` field as `model_harvested_quantity` with the qualifier `MODEL_OUTPUT / NOT_DIRECT_OBSERVATION / NOT_PRIMARY_ACTUAL_LABEL`.

---

## §D. Actual-label candidate audit (v1.2 per review 4695151631 P0-4)

### §D.1 First-class operator-entered daily fact: `fact_receipt_daily` (arrival proxy)

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

### §D.2 ACTUAL_LABEL_STATUS verdict (v1.2)

```
ACTUAL_LABEL_STATUS = SCHEMA_GAP / SOURCE_GAP / POINT_IN_TIME_GAP / REVISION_HISTORY_GAP
PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO
ARRIVAL_PROXY_EVALUATION_ALLOWED = DESIGN_OPTION
ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET = YES
PRIMARY_TARGET_ACCURACY_REPORTING_WITH_PROXY = FORBIDDEN
ACTUAL_LABEL_SUPPORTED_GRAIN = fact_receipt_daily at (build_run_id, season_id, factory_id, receipt_date, farm_key, subfarm_key, variety_id, weight_kg > 0) — arrival / receipt at the factory, NOT pick at the orchard
```

### §D.3 What `fact_receipt_daily` is and is not (v1.2)

- IS: an operator-entered daily receipt / arrival fact at the factory gate, with a build-run identity and a unique-constraint grain, with a positive-only weight CHECK. It is the closest available first-class fact.
- IS NOT: a daily actual-harvest fact at the orchard. The physical meaning is "arrival at the factory gate", not "pick at the orchard". `ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET = YES`.
- IS NOT: a fact with point-in-time visibility. There is no `recorded_at`, `effective_at`, `revised_at`, `revision_number`, `supersedes_record_id`, or `is_deleted_or_voided`.
- IS NOT: a fact with row-level revision. The only revision mechanism is re-build, which is an analytics concept, not a row-level revision.
- IS NOT: a daily-actual-harvest primary label for the P0 evaluation contract. It is the closest available fact, but it is `PROXY_LABEL` for `actual_harvest_quantity`. `PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO`. `PRIMARY_TARGET_ACCURACY_REPORTING_WITH_PROXY = FORBIDDEN`.

### §D.4 First-class `actual_harvest_daily` table — NOT present

There is no first-class `actual_harvest_daily` table in `origin/main`. The Q1 design-freeze proposes the canonical fields in §6.3 of the Q1 contract document; Q2A design and implementation must decide whether to add the table (Result A) or accept `fact_receipt_daily` as a proxy (Result B).

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

`harvest_state_daily_pool_row.harvested_quantity_kg` and `harvest_state_daily_member_row.harvested_quantity_kg` are TASK-009 model output, not user-entered actual harvest. The `harvest_state_daily_member_row` carries first-class `farm_id` / `subfarm_id` / `variety_id` / `state_date` / `harvested_quantity_kg` at the member grain (the upstream member grain referenced in §5 of the Q1 contract document).

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

Q1 does not modify the production-wired surface. Q2B must add a point-in-time backtest runner to the production-wired surface.

---

## §H. Live-database discovery result (preserved from v1.1)

Q1 v1.1 performed a read-only live-database discovery on the configured PostgreSQL (`POSTGRES_HOST=localhost`, `POSTGRES_PORT=5432`, `POSTGRES_DB=blueberry_peak`, `POSTGRES_USER=blueberry_app`).

### §H.1 Discovery steps and evidence

| Step | Command | Result |
|---|---|---|
| 1 | `which psql` | `/usr/bin/psql` (PostgreSQL 16.14) |
| 2 | `which docker` | `/usr/bin/docker` |
| 3 | `docker ps` | container `c2-pg` (image `pgvector/pgvector:pg16`, port `0.0.0.0:55432->5432`, ~4 hours old at discovery time) |
| 4 | `cat .env` | `POSTGRES_HOST=localhost`, `POSTGRES_PORT=5432`, `POSTGRES_DB=blueberry_peak`, `POSTGRES_USER=blueberry_app`, `POSTGRES_PASSWORD= NO len=3>` |
| 5 | `psql -c "SELECT 1;"` | `1` (connection OK) |
| 6 | `psql -c "SELECT now();"` | `2026-07-14 13:40:47+00` |
| 7 | `psql -c "SELECT version_num FROM alembic_version;"` | `0013_rolling_backtest_orch` (0014 and 0015 NOT applied) |
| 8 | `psql -c "\d harvest_state_replay_source_visibility_audit"` | "Did not find any relation" (confirms 0015 NOT applied) |
| 9 | `psql -c "SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'public';"` | 54 tables, 53 with 0 rows, `alembic_version` with 1 row |

The database is configured, discoverable, reachable, and has a working PostgreSQL 16.14 backend. The Docker container `c2-pg` was created ~4 hours before Q1 v1.1; the alembic is at `0013_rolling_backtest_orch`, which means migrations 0014 and 0015 (TASK-009 historical authority and TASK-011 phase 3 schema gap) have NOT been applied to this database. The `harvest_state_replay_source_visibility_audit` table does not exist, confirming 0015 has not been applied.

### §H.2 Aggregate coverage query result

All queries are read-only. The output is aggregate counts; no row-level data is returned. The queries follow the §7.2 of the round instruction:

| Query | Result | Note |
|---|---|---|
| `SELECT COUNT(*) FROM dim_farm` | 0 | |
| `SELECT COUNT(*) FROM dim_subfarm` | 0 | |
| `SELECT COUNT(*) FROM dim_variety` | 0 | |
| `SELECT COUNT(*) FROM dim_grade` | 0 | |
| `SELECT COUNT(*) FROM dim_season` | 0 | |
| `SELECT COUNT(*) FROM dim_factory` | 0 | |
| `SELECT COUNT(*) FROM dim_holiday` | 0 | |
| `SELECT COUNT(*) FROM fact_receipt_daily` | 0 | |
| `SELECT COUNT(*) FROM fact_receipt_raw` | 0 | |
| `SELECT COUNT(*) FROM analytics_build_run` | 0 | |
| `SELECT COUNT(*) FROM factory_season_peak_metric` | 0 | |
| `SELECT COUNT(*) FROM harvest_state_run` | 0 | |
| `SELECT COUNT(*) FROM harvest_state_daily_pool_row` | 0 | |
| `SELECT COUNT(*) FROM harvest_state_daily_member_row` | 0 | |
| `SELECT COUNT(*) FROM harvest_state_cohort_transition_row` | 0 | |
| `SELECT COUNT(*) FROM harvest_state_future_arrival_row` | 0 | |
| `farm_count` (from `dim_farm`) | 0 | |
| `subfarm_count` (from `dim_subfarm`) | 0 | |
| `variety_count` (from `dim_variety`) | 0 | |
| `season_count` (from `dim_season`) | 0 | |
| `daily_row_count` (from `fact_receipt_daily`) | 0 | |
| `positive_day_count` (from `fact_receipt_daily` where `weight_kg > 0`) | 0 | |
| `explicit_zero_day_count` (from `fact_receipt_daily` where `weight_kg = 0`) | 0 | |
| `missing_day_count` (derived) | 0 | (no daily row count) |
| `duplicate_key_count` (from `fact_receipt_daily` unique constraint) | 0 | (no daily row count; the unique constraint would force 0 in any case) |
| `build_run_count` (from `fact_receipt_daily.build_run_id`) | 0 | |
| `date_min` (from `fact_receipt_daily.receipt_date`) | NULL | (no rows) |
| `date_max` (from `fact_receipt_daily.receipt_date`) | NULL | (no rows) |
| `sum(weight_kg)` (from `fact_receipt_daily` where `weight_kg > 0`) | NULL | (no rows) |
| `avg(weight_kg)` (from `fact_receipt_daily` where `weight_kg > 0`) | NULL | (no rows) |
| `min(weight_kg)` (from `fact_receipt_daily` where `weight_kg > 0`) | NULL | (no rows) |
| `max(weight_kg)` (from `fact_receipt_daily` where `weight_kg > 0`) | NULL | (no rows) |
| `total_series_count` (per season × farm × variety) | 0 | (no rows) |
| `series_with_>=7_distinct_dates` | 0 | |
| `series_with_<7_distinct_dates` | 0 | |
| `series_with_>=14_distinct_dates` | 0 | |
| `series_with_>=21_distinct_dates` | 0 | |

### §H.3 Verdict

```
REAL_DATA_SOURCE_DISCOVERY = POSTGRES_DOCKER_CONTAINER_C2_PG (pgvector/pgvector:pg16, port 55432->5432)
REAL_DATA_COVERAGE_STATUS = NOT_VERIFIED_EMPTY_DATABASE
Q1_DATA_COVERAGE_AUDIT_STATUS = PARTIAL
```

The live PostgreSQL is discoverable and reachable. The schema is up-to-date with the merged C1 contract (54 tables, including the 33 first-class Q1-relevant tables, the 15 migrated tables, and the 6 additional tables not in §C.2). However, the live database is empty. The 0-row aggregate means that the real-data coverage matrix cannot be populated with non-zero values. Q1 reports this as `NOT_VERIFIED_EMPTY_DATABASE`, not as `COMPLETE` / `READY` / `VERIFIED`.

Q1 does NOT claim that the real-data coverage is verified. Q1 reports the truthful result of a real read-only query: 0 rows in every table. The status is `NOT_VERIFIED_EMPTY_DATABASE` because there is no data to verify against.

### §H.4 Read-only discipline (per §7.1 of the round instruction)

The Q1 live-database discovery performed the following:

- no DDL (no `CREATE`, `ALTER`, `DROP`, `TRUNCATE`);
- no DML (no `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `VACUUM`, `REINDEX`, `CLUSTER`);
- no migration;
- no schema mutation;
- no `SELECT ... FOR UPDATE` / `FOR SHARE` (no row-level locking).

The discovery queries were `SELECT ... FROM <table> WHERE <predicate> GROUP BY ... ORDER BY ... LIMIT ...`. The output is aggregate counts; no row-level data is returned. No farm name, no subfarm name, no variety name, no operator name, no exact daily quantity, no exact forecast output, and no exact row count on real data is reported.

The Q1 v1.1 discovery did not read or echo the `POSTGRES_PASSWORD` value. The output of any `psql` command was filtered to mask the password when it would otherwise appear in the output (the password is used as a connection parameter, not as a query result, so it does not appear in query output).

### §H.5 Arrival proxy vs primary actual-harvest label (v1.2 per review 4695151631 P0-4)

The `fact_receipt_daily` table is an **arrival proxy**, not the **primary actual-harvest label**. The Q1 v1.2 separation is:

- `PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO`
- `ARRIVAL_PROXY_EVALUATION_ALLOWED = DESIGN_OPTION`
- `ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET = YES`
- `PRIMARY_TARGET_ACCURACY_REPORTING_WITH_PROXY = FORBIDDEN`

The 0-row aggregate for `fact_receipt_daily` means the arrival proxy itself is empty. The proxy does not satisfy the primary target even when populated. The primary target backtest remains blocked until either (a) a dedicated `actual_harvest_daily` table is added (Result A) or (b) Charles explicitly changes the primary business target.

---

## §I. Backtest usability gate (recap)

A series is `usable_backtest_series` if and only if all of the following hold:

- grain identity is complete;
- date-continuity rule is explicit;
- actual label is not a proxy, or the proxy is explicitly accepted and disclosed;
- unit is consistent (kg);
- no unresolved duplicate;
- point-in-time visibility is verifiable for the chosen `label_observation_cutoff_at`;
- `forecast_cutoff_at` and `label_observation_cutoff_at` are both bindable to a specific replay identity;
- at least one full 7-day target window is present (per §7 of the Q1 contract document);
- the actual label and the forecast output are alignable at the same grain.

The current `fact_receipt_daily` does not satisfy the grain identity (no `subfarm_or_plot_id`), the point-in-time visibility (no `recorded_at`, `effective_at`, `revised_at`, `revision_number`, `supersedes_record_id`), the explicit-zero handling (structurally excluded), or the row-level revision (re-build only). The `usable_backtest_series_count` against `fact_receipt_daily` is `0` by the Q1 gate.

```
USABLE_BACKTEST_SERIES_COUNT_AGAINST_FACT_RECEIPT_DAILY = 0 (by the Q1 gate; re-build mechanism is not row-level revision; explicit zero days are missing rows; subfarm_or_plot_id is not a column)
```

---

## §J. Forbidden action evidence (against Q1 hard exclusions)

The Q1 v1.2 round ran the following forbidden-action verification:

| Forbidden action | Verification command | Result |
|---|---|---|
| modify any production code under `backend/app/**` | `git diff --name-only origin/main -- backend/app/` | empty |
| modify any test under `backend/tests/**` | `git diff --name-only origin/main -- backend/tests/` | empty |
| add or modify any migration under `backend/alembic/**` | `git diff --name-only origin/main -- backend/alembic/` | empty |
| modify any Golden file | `git diff --name-only origin/main -- '**/golden/**'` | empty |
| modify any frontend, dependency, or workflow | `git diff --name-only origin/main -- frontend/ .github/ pyproject.toml requirements.txt` | empty |
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
| claim 7-day peak is implemented | the Q1 contract document and this audit document both state `SUSTAINED_7DAY_IMPLEMENTED = NO` and `PRIMARY_SUSTAINED_PEAK_QUALITY_STATUS = NOT_YET_COMPUTABLE` | compliant |
| claim forecast accuracy has improved | the Q1 contract document and this audit document both state `MODEL_CHANGE_NOT_AUTHORIZED` | compliant |
| fabricate real-data coverage | the live-database query result is recorded as 0 rows for all tables; the audit does not substitute fixtures or Goldens for real data | compliant |
| report `Q2_READINESS = READY` | the Q1 v1.2 decision table reports `Q2_READINESS = BLOCKED_BY_Q1_GAPS` and `Q2_IMPLEMENTATION_READY = NO` | compliant |
| report `REAL_DATA_COVERAGE_STATUS = COMPLETE` or `READY` or `VERIFIED` | the Q1 v1.2 decision table reports `REAL_DATA_COVERAGE_STATUS = NOT_VERIFIED_EMPTY_DATABASE` | compliant |
| use a single `relative_error` field with a signed formula | the Q1 v1.2 metric contract separates signed and absolute relative errors into distinct fields | compliant |
| leave a sustained 7-day window `NOT_COMPUTABLE or partial` | the Q1 v1.2 missing-window policy freezes a single canonical rule (excluded from peak competition) | compliant |
| report `ForecastDailyRow` as having 7 quantity fields | the Q1 v1.2 schema inventory reports exactly 6 `DailyQuantiles` quantity fields | compliant |
| report `ForecastDailyRow` as first-class `(farm × subfarm × variety × date)` | the Q1 v1.2 schema inventory reports the row as a downstream aggregate (CURRENT_AGENT_OUTPUT_GRAIN = RESOLVED_REQUEST_AGGREGATE_X_DATE) | compliant |
| use `harvestable_quantity = harvested - backlog` as a formula | the Q1 v1.2 §5.5 forbids this formula and marks `harvestable_quantity` as `NOT_CURRENTLY_AVAILABLE` / `FORMULA_NOT_AUTHORIZED` | compliant |
| cite the 3-day production metric as the first-stage primary sustained metric | the Q1 v1.2 §7.7 and §8.3 classify the 3-day metric as `LEGACY_COMPATIBILITY_METRIC`; the 7-day metric is `PRIMARY_BUSINESS_SUSTAINED_PEAK_TARGET` and `PRIMARY_SUSTAINED_PEAK_QUALITY_STATUS = NOT_YET_COMPUTABLE` | compliant |
| promote `fact_receipt_daily` to the primary `actual_harvest_quantity` label | the Q1 v1.2 §11 freezes `PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO` and `ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET = YES` | compliant |
| use `forecast_target_date < forecast_cutoff_at` (in-simulation) | the Q1 v1.2 §4.3 removes this wording and freezes the four-time-bound canonical order | compliant |
| use `latest timestamp wins` for the revision winner | the Q1 v1.2 §4.5 freezes the fail-closed policy; `latest timestamp fallback` is forbidden | compliant |
| use `largest revision-number wins` for the revision winner | the Q1 v1.2 §4.5 freezes the fail-closed policy; `largest revision-number fallback` is forbidden | compliant |
| describe Q1 as accepted before Charles signs off | the Q1 v1.2 sign-off section reports `PENDING_RE_REVIEW` and `Q1_NOT_YET_ACCEPTED` | compliant |

---

## §K. Test and CI evidence

The Q1 v1.2 round does not add, modify, or run any test. The Q1 v1.2 round does not run CI. The Q1 v1.2 round does not modify any CI workflow. The Q1 v1.2 round does not access any CI artifact.

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

## §L. Change log

| Date | Round | Author | Change |
|---|---|---|---|
| 2026-07-14 | v1 (Q1) | Charles-authorized Q1 design-only round | Initial creation. Migration history (15 files on `origin/main`). 3-day production contract inventory (full file-by-file mapping). Schema inventory (ForecastDailyRow + ForecastPeakOutput + ParameterEstimate). Actual-label candidate audit (fact_receipt_daily as closest first-class fact, with structural zero-day and point-in-time gaps). Data-coverage matrix template. Forbidden-action evidence. |
| 2026-07-14 | v1.1 (Q1 P0 fixup) | Charles-authorized Q1 P0 fixup (review 4694771522) | Live-database discovery result. `REAL_DATA_COVERAGE_STATUS = NOT_VERIFIED`. Q1_DATA_COVERAGE_AUDIT_STATUS = PARTIAL. `ForecastDailyRow` quantity-field count corrected from 7 to 6. Grain corrected. `harvestable_quantity` marked `NOT_CURRENTLY_AVAILABLE` / `FORMULA_NOT_AUTHORIZED`. Q2 readiness decomposed into `Q2_DESIGN_CAN_START = YES` / `Q2_IMPLEMENTATION_READY = NO` / `Q2_READINESS = BLOCKED_BY_Q1_GAPS`. Acyclic slice ordering. 3-day/7-day coexistence policy frozen to additive (both fields present). Signed and absolute relative errors separated. Missing-window policy frozen to a single canonical rule. Per-quantile single-day peak metrics frozen. |
| 2026-07-14 | v1.2 (Q1 final contract fixup) | Charles-authorized Q1 final fixup (review 4695151631) | (1) Historical-replay time model: `forecast_cutoff_at < forecast_target_date_or_window_end <= label_observation_cutoff_at <= replay_executed_at`. The v1.1 wording `forecast_target_date < forecast_cutoff_at` is removed. The same-day wording uses `forecast_target_local_date = local_date(forecast_cutoff_at, farm_timezone)`. (2) Fail-closed revision lineage policy: the unique visible terminal revision on one valid explicit supersession chain within one source family. The `latest timestamp wins` and `largest revision-number wins` rules are removed. Fail-closed conditions are listed as typed blockers. Void semantics are explicit. (3) Three-grain split on the physical-quantity table. The "persisted fields" phrase is replaced with "first-class serialized output-schema fields". `harvested_quantity_kg` is mapped to `model_harvested_quantity`. `season_cumulative_quantity` is `DERIVED_EVALUATION_METRIC` / `NO_FIRST_CLASS_PRODUCTION_FIELD_REQUIRED_BY_Q1`. (4) Actual-harvest label and arrival proxy separation: `PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO`, `ARRIVAL_PROXY_EVALUATION_ALLOWED = DESIGN_OPTION`, `ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET = YES`, `PRIMARY_TARGET_ACCURACY_REPORTING_WITH_PROXY = FORBIDDEN`. Proxy report names restricted. Q2A two-result split (Result A dedicated table; Result B proxy). (5) 3-day is `LEGACY_COMPATIBILITY_METRIC`; 7-day is `PRIMARY_BUSINESS_SUSTAINED_PEAK_TARGET`; primary status is `NOT_YET_COMPUTABLE` until Q3 + Q2C. (6) Slice ordering wording corrected: `Q2A_DESIGN_ELIGIBLE_AFTER_Q1_ACCEPTANCE = YES` separated from `Q2A_CURRENTLY_AUTHORIZED=NO` and `Q2_IMPLEMENTATION_READY = NO`. (7) Decision table unified. Sign-off no longer pre-fills `ACCEPTED`; the state is `PENDING_RE_REVIEW` and `Q1_NOT_YET_ACCEPTED`. |

---

## §M. Sign-off (to be completed by Charles upon acceptance)

```text
SLICE_Q1_DATA_COVERAGE_AUDIT_V1_2_PENDING_RE_REVIEW
MIGRATION_HISTORY_VERIFIED
3DAY_PRODUCTION_CONTRACT_INVENTORY_VERIFIED
LIVE_DATABASE_DISCOVERY_VERIFIED_EMPTY
REAL_DATA_COVERAGE_STATUS_NOT_VERIFIED_EMPTY_DATABASE
Q1_DATA_COVERAGE_AUDIT_STATUS_PARTIAL
PRIMARY_ACTUAL_HARVEST_LABEL_READY_NO
ARRIVAL_PROXY_EVALUATION_ALLOWED_DESIGN_OPTION
ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET_YES
SEVEN_DAY_PRIMARY_TARGET_CONFIRMED_AS_DESIGN
THREE_DAY_LEGACY_COMPATIBILITY_METRIC_CONFIRMED
Q2A_CURRENTLY_AUTHORIZED=NO
Q2_IMPLEMENTATION_READY=NO
```

(Charles to amend the above with explicit `ACCEPTED` or `REVISED` markers.)
