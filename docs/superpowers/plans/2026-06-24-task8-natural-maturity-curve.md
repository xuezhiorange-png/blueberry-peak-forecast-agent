# Task 8 Natural Maturity Curve Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic Task 8 natural maturity curve training/forecast pipeline with persistence, API, CLI, reports, and anti-leakage guarantees, while stopping before Task 9 arrival-state logic.

**Architecture:** Reuse Task 5/6/7 upstream contracts and add a new `backend/app/maturity/` module. The model stores a canonical training manifest, a JSONB artifact for shared spline curves plus fallback/shrinkage metadata, and forecast runs that scale non-negative density curves to `expected_marketable_total_kg`. Training and forecast signatures include all upstream visible versions that can change the result.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, Decimal/NUMERIC, scikit-learn spline/linear tooling, pytest, PostgreSQL integration tests.

---

## File Map

**Create**
- `backend/app/maturity/__init__.py`
- `backend/app/maturity/config.py`
- `backend/app/maturity/schemas.py`
- `backend/app/maturity/repository.py`
- `backend/app/maturity/features.py`
- `backend/app/maturity/model.py`
- `backend/app/maturity/calibration.py`
- `backend/app/maturity/service.py`
- `backend/app/maturity/reporting.py`
- `backend/app/models/maturity.py`
- `backend/app/api/maturity.py`
- `backend/app/schemas/maturity.py`
- `backend/alembic/versions/0009_natural_maturity_curve.py`
- `backend/tests/maturity/test_model.py`
- `backend/tests/maturity/test_service.py`
- `backend/tests/integration/test_maturity_curve.py`
- `configs/maturity_curve.yaml`
- `data/templates/maturity_curve_training_manifest.csv`
- `scripts/train_maturity_curve.py`
- `scripts/forecast_natural_maturity.py`
- `docs/13_natural_maturity_curve.md`

**Modify**
- `backend/app/main.py`
- `backend/app/models/__init__.py`
- `backend/tests/integration/conftest.py`
- `sql/schema.sql`
- `docs/03_database_design.md`
- `README.md`
- `CODEX_TASKS.md`
- `.github/workflows/ci.yml`

## Planned task groups

### Task 1: Add Task 8 config, schemas, and persistence contracts
- [ ] Add failing unit tests for canonical config loading, schema status preservation, and canonical JSON artifact payload rules.
- [ ] Add `configs/maturity_curve.yaml` with version, spline, pooling, interval, and tolerance settings.
- [ ] Add `backend/app/maturity/config.py` and `backend/app/maturity/schemas.py`.
- [ ] Add `backend/app/models/maturity.py`, `0009_natural_maturity_curve.py`, and `sql/schema.sql` updates.
- [ ] Run focused tests for config/schema serialization.

### Task 2: Build training manifest parsing and upstream input resolution
- [ ] Add failing tests for manifest order independence, include=false participation in source signature, blocker behavior when plan/weather/base-temp dependencies are missing, and future-data rejection.
- [ ] Implement manifest loader and upstream resolution in `backend/app/maturity/features.py` and `repository.py`.
- [ ] Reuse Task 6/7 repositories for effective plan, weather mapping, observation fingerprint, and base-temperature search lookup.
- [ ] Implement deterministic training manifest fingerprint and input snapshot generation.
- [ ] Run unit tests for manifest resolution and signature behavior.

### Task 3: Implement shared curve, partial pooling, and shift model
- [ ] Add failing tests for non-negative normalized density, P50 mass reconciliation, hierarchy fallback, shrinkage metadata, offset bounds, unknown facility handling, and fixed-seed reproducibility.
- [ ] Implement spline basis/shared curve model in `backend/app/maturity/model.py`.
- [ ] Implement partial pooling fallback logic and interpretable shift model in `model.py`.
- [ ] Add calibration helpers in `backend/app/maturity/calibration.py` for pointwise intervals and conservative fallback widening.
- [ ] Run `backend/tests/maturity/test_model.py`.

### Task 4: Implement training service and artifact persistence
- [ ] Add failing tests for train-run idempotency, visible-weather revision sensitivity, manifest-weight sensitivity, unavailable/failed status preservation, and canonical JSON artifact storage.
- [ ] Implement `train_maturity_curve()` in `backend/app/maturity/service.py`.
- [ ] Persist `maturity_model_run` and `maturity_model_artifact` via `repository.py`.
- [ ] Generate JSON/Markdown reports in `reporting.py`.
- [ ] Run maturity unit tests and focused integration tests.

### Task 5: Implement forecast service and daily prediction persistence
- [ ] Add failing tests for forecast idempotency, plan-version sensitivity, weather/base-temp dependency tracing, P50 total reconciliation, rehydrate type consistency, and calendar proxy interval widening.
- [ ] Implement `forecast_natural_maturity()` in `service.py`.
- [ ] Persist `maturity_forecast_run` and `maturity_daily_prediction`.
- [ ] Implement `completed/failed/unavailable/dry_run` behavior with canonical payload rehydrate.
- [ ] Run focused maturity unit/integration tests.

### Task 6: Add API, CLI, docs, and golden synthetic coverage
- [ ] Add failing API tests for train/forecast POST+GET roundtrip and failed-run state preservation.
- [ ] Add CLI help/smoke tests and golden synthetic integration tests.
- [ ] Wire `backend/app/api/maturity.py`, `backend/app/schemas/maturity.py`, and `backend/app/main.py`.
- [ ] Add `scripts/train_maturity_curve.py` and `scripts/forecast_natural_maturity.py`.
- [ ] Update README/database docs/CI migration roundtrip.
- [ ] Run full verification suite and prepare the Draft PR final summary.

## Verification target

- `env UV_CACHE_DIR=.uv-cache uv run ruff check .`
- `env UV_CACHE_DIR=.uv-cache uv run mypy backend/app`
- `env UV_CACHE_DIR=.uv-cache uv run pytest backend/tests/maturity -q`
- `env UV_CACHE_DIR=.uv-cache uv run pytest -m "not integration" -q`
- `RUN_POSTGRES_INTEGRATION=1 env UV_CACHE_DIR=.uv-cache uv run pytest -m integration -vv --tb=long --maxfail=1 --timeout=120 --timeout-method=thread`
- `env UV_CACHE_DIR=.uv-cache uv run pytest -q`
- `alembic -c backend/alembic.ini upgrade head`
- `alembic -c backend/alembic.ini downgrade 0008_weather_timeline`
- `alembic -c backend/alembic.ini upgrade head`
- `docker compose config`
- `docker compose up -d db && docker compose down -v`
- `env UV_CACHE_DIR=.uv-cache uv run python scripts/train_maturity_curve.py --help`
- `env UV_CACHE_DIR=.uv-cache uv run python scripts/forecast_natural_maturity.py --help`
