# Task 4 Baseline Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Task 4 baseline models, historical oracle backtest persistence, CLI, reports, and validation on top of Task 3 analytics tables.

**Architecture:** Build a new `backend.app.baseline` package that reads selected Task 3 `completed` build runs, assembles per-season/per-factory static samples from persisted `factory_season_peak_metric`, runs deterministic baselines and Ridge LOSO/factory-holdout evaluation, persists run/result audit tables, and emits JSON/Markdown/CSV reports. Keep Task 4 explicitly benchmark-only by tagging every run/report as `historical_oracle` and `production_eligible=false`.

**Tech Stack:** Python 3.12, Pydantic v2, SQLAlchemy 2, Alembic, scikit-learn, numpy, pytest, PostgreSQL 16.

---

### Task 1: Model config and pure evaluation logic

**Files:**
- Create: `backend/app/baseline/config.py`
- Create: `backend/app/baseline/metrics.py`
- Create: `backend/app/baseline/signature.py`
- Create: `backend/tests/baseline/test_config.py`
- Create: `backend/tests/baseline/test_metrics.py`
- Create: `backend/tests/baseline/test_signature.py`

- [ ] Add failing tests for config validation, source signature stability, exclusion rules, MAPE/MdAPE/WMAPE, negative prediction handling, and leakage-audit trigger.
- [ ] Implement strict Pydantic config parsing for `configs/baseline_model.yaml`, stable config hashing, and source-signature hashing.
- [ ] Implement pure metric utilities and leakage-audit helpers without any database dependency.
- [ ] Run targeted tests until green.

### Task 2: Baseline formulas and fold builders

**Files:**
- Create: `backend/app/baseline/schemas.py`
- Create: `backend/app/baseline/dataset.py`
- Create: `backend/app/baseline/baselines.py`
- Create: `backend/app/baseline/ridge.py`
- Create: `backend/tests/baseline/test_baselines.py`
- Create: `backend/tests/baseline/test_ridge.py`

- [ ] Add failing tests for previous-season pairing by `start_date`, previous-season exclusion, volume×concentration formula, strict Ridge feature list, and LOSO/factory-holdout split hygiene.
- [ ] Implement in-memory sample structures backed only by persisted Task 3 metrics/build runs.
- [ ] Implement `BaselinePreviousSeasonPeak`, `BaselineVolumePreviousConcentration`, and `BaselineRidgeStructure`.
- [ ] Implement LOSO and leave-one-factory-out evaluators with training-only scaler fit and minimum-row exclusion.
- [ ] Run targeted tests until green.

### Task 3: Persistence, ORM, and migration

**Files:**
- Modify: `backend/app/models/analytics.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0005_baseline_backtest.py`
- Modify: `sql/schema.sql`
- Modify: `docs/03_database_design.md`
- Create: `backend/tests/integration/test_baseline_backtest.py`

- [ ] Add failing integration tests for build-run selection, mixed Task 3 config rejection, run/result uniqueness, skipped/running/failed audit behavior, dry-run zero writes, and migration roundtrip to `0005_baseline_backtest`.
- [ ] Extend ORM with `BaselineBacktestRun` and `BaselineBacktestResult`.
- [ ] Add Alembic migration with constraints, indexes, and partial unique index for running/completed runs.
- [ ] Keep failure auditing on pure IDs/values only; no rollback-time access to expired ORM instances.
- [ ] Run targeted integration tests where possible; rely on CI PostgreSQL for full execution.

### Task 4: Service orchestration, CLI, and reports

**Files:**
- Create: `backend/app/baseline/service.py`
- Create: `backend/app/baseline/reporting.py`
- Create: `scripts/run_baseline_backtest.py`
- Create: `configs/baseline_model.yaml`
- Modify: `.gitignore`
- Create: `backend/tests/baseline/test_service.py`

- [ ] Add failing tests for dry-run zero writes, skipped completed runs, running conflict fallback, deterministic result rows, and JSON/Markdown/CSV report content.
- [ ] Implement Task 3 build-run selection (explicit and default) with config/aggregation consistency checks.
- [ ] Implement run orchestration, persistence, idempotent skip/running fallback, and report generation.
- [ ] Add CLI flags for season selection, build-run overrides, dry-run, and output directory.
- [ ] Run targeted tests until green.

### Task 5: Documentation, README, dependencies, and CI

**Files:**
- Create: `docs/06_baseline_backtest.md`
- Modify: `README.md`
- Modify: `CODEX_TASKS.md` (only if wording drift must be corrected)
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `.github/workflows/ci.yml`

- [ ] Add failing checks if dependency or CI wiring is missing.
- [ ] Add `numpy` and `scikit-learn` to project dependencies and refresh `uv.lock`.
- [ ] Update CI migration roundtrip target to `0005_baseline_backtest` and preserve JUnit artifact behavior.
- [ ] Document oracle-benchmark limitations, CLI usage, leakage audit, and non-production status.
- [ ] Run final verification suite and push the Task 4 branch before opening/updating the Draft PR.
