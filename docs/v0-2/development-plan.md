# Blueberry Peak Forecast Agent V0.2 Development Plan

## 1. Version identity and final objective

```text
VERSION=0.2.0
VERSION_NAME=FORECAST_QUALITY_TRIAL
PRIMARY_EPIC=ISSUE_102
V0_2_TOTAL_SLICES=5
FRONTEND_IN_V0_2=true
V0_2_BACKEND_ONLY=false
V0_2_USER_TRIAL_RELEASE=true
```

V0.2 turns the completed V0.1 forecast engine into a small, directly usable product trial.

The release must close one complete user-visible loop:

```text
create a forecast
→ inspect the daily curve and peak metrics
→ import approved actual-harvest data
→ bind point-in-time actual labels
→ compare forecast versus actual
→ inspect quality metrics and a naive baseline
→ export the result
```

V0.2 is complete only when this flow works in a browser without requiring the trial user to operate the CLI.

## 2. Frozen version boundary

V0.2 contains exactly five slices:

1. **S1 — Actual-harvest atomic commit**
2. **S2 — Point-in-time actual labels and historical backtest**
3. **S3 — Forecast-quality metrics and one naive baseline**
4. **S4 — Frontend application API**
5. **S5 — Two-page responsive trial frontend and browser E2E**

```text
NO_ADDITIONAL_SLICE_WITHOUT_VERSION_REPLAN=true
PROJECT_BACKLOG_DOES_NOT_EXTEND_VERSION_SCOPE=true
ISSUE_99_REMAINS_PAUSED=true
MODEL_CHANGE_IN_V0_2=false
OPERATIONAL_RECOMMENDATIONS_IN_V0_2=false
```

An open Issue or an already merged post-V0.1 foundation does not automatically become a V0.2 release requirement. Any addition requires an explicit version-plan amendment.

## 3. Current implementation baseline

Current planning base:

```text
PLANNING_BASE_SHA=7002b8f5ae078e130f2e34316165431656f73403
V0_1_RELEASE_BOUNDARY_SHA=235bde1407bdd0b86f2b31ad75ba1c3b8dc5ba61
CURRENT_APPLICATION_VERSION=0.1.0
```

The repository already contains post-V0.1 foundations for actual-harvest schema, staging persistence, CSV/XLSX parsing, batch lifecycle, sealing, validation, exact mapping, season resolution, and revision-lineage validation.

These foundations reduce V0.2 implementation work, but they do not change the frozen V0.1 scope and they do not by themselves satisfy any V0.2 release slice.

## 4. V0.2-S1 — Actual-harvest atomic commit

### Objective

Promote one fully validated import batch into immutable committed actual-harvest source revisions.

### Execution model

V0.2 uses a synchronous, caller-owned, single-database-transaction commit model.

```text
VALIDATED
→ lock batch
→ recheck authorization and validation evidence
→ insert committed revisions
→ insert immutable commit manifest
→ update batch to COMMITTED
→ commit transaction
```

### Required guarantees

```text
COMMIT_FROM_VALIDATED_ONLY=true
FULL_BATCH_ATOMIC=true
PARTIAL_COMMIT_FORBIDDEN=true
EXACT_REPLAY_RETURNS_ORIGINAL=true
CONFLICTING_REPLAY_REJECTED=true
COMMITTED_REVISIONS_IMMUTABLE=true
CALLER_OWNED_TRANSACTION=true
```

Any failure must roll back committed revisions, manifest writes, and the final batch-state update together.

### Explicit exclusions

```text
BACKGROUND_COMMIT_WORKER=false
COMMIT_ATTEMPT_LEDGER=false
LEASE=false
HEARTBEAT=false
STALE_RECLAIM=false
COMMIT_FENCING=false
REVISION_WINNER_SELECTION=false
CUTOFF_LABEL_SNAPSHOT=false
AGGREGATION=false
```

S1 must not depend on an aggregation manifest, label snapshot, or cutoff winner.

### Acceptance gate

- one physical commit manifest per batch;
- no manifest without all committed revisions;
- no committed revisions without the manifest;
- exact replay is zero-write and returns the original result;
- conflicting evidence produces a deterministic conflict;
- PostgreSQL concurrency acceptance proves one serialized outcome.

## 5. V0.2-S2 — Point-in-time actual labels and historical backtest

### Objective

Build immutable actual-label snapshots and bind them to historical forecasts without future-data leakage.

### Processing order

```text
committed source revisions
→ cutoff visibility
→ deterministic terminal-revision selection
→ revision-first daily aggregation
→ evaluation-grain actual labels
→ immutable label snapshot
→ historical forecast binding
→ point-in-time backtest manifest
```

### Required dimensions

- farm;
- subfarm or plot, according to the frozen evaluation-grain policy;
- variety;
- season;
- forecast generation time;
- forecast target date;
- forecast horizon days;
- model and parameter version;
- actual-label snapshot identity.

### Required horizons

```text
FORECAST_HORIZONS_DAYS=7,14,21
MULTI_FARM=true
MULTI_VARIETY=true
MULTI_SEASON=true
```

### Leakage controls

```text
FUTURE_REVISION_LEAKAGE=false
POST_CUTOFF_CORRECTION_LEAKAGE=false
LATEST_ROW_FALLBACK=false
DATABASE_ROW_ORDER_DEPENDENCE=false
UNVERSIONED_AUTHORITY_FALLBACK=false
```

The same snapshot and backtest request must reproduce the same canonical hashes and rows.

### Outputs

- immutable label snapshot and hash;
- coverage and exclusion report;
- cutoff and source-evidence manifest;
- forecast/actual binding rows;
- leakage-audit result;
- deterministic backtest-run hash.

## 6. V0.2-S3 — Forecast-quality metrics and one naive baseline

### Objective

Measure V0.1 forecast quality on the S2 point-in-time bindings and compare it with one frozen, repeatable naive baseline.

### Required daily metrics

- MAE;
- WAPE;
- sMAPE;
- MAPE with an explicit zero policy;
- cumulative absolute error;
- cumulative relative error.

### Required peak metrics

- single-day peak date absolute error;
- single-day peak quantity absolute error;
- single-day peak quantity relative error;
- sustained seven-day peak start-date absolute error;
- sustained seven-day cumulative absolute error;
- sustained seven-day cumulative relative error.

### Required interval metrics

- P80 coverage and interval width;
- P90 coverage and interval width.

### Required breakdowns

- forecast horizon;
- farm;
- variety;
- season;
- model version.

### Baseline boundary

```text
NAIVE_BASELINE_COUNT=1
BASELINE_FORMULA_MUST_BE_FROZEN_BEFORE_IMPLEMENTATION=true
BASELINE_USES_ONLY_PRE_CUTOFF_DATA=true
BASELINE_AND_MODEL_USE_IDENTICAL_LABELS_AND_METRICS=true
```

V0.2 measures quality. It does not modify the forecasting model, maturity curve, residual correction, weather adjustment, or harvest-state equations.

### Comparison outputs

- current model versus naive baseline;
- MAE, WAPE, and sMAPE deltas;
- single-day peak date and quantity deltas;
- sustained seven-day peak date and quantity deltas;
- P80/P90 coverage deltas;
- interval-width deltas.

## 7. V0.2-S4 — Frontend application API

### Objective

Provide a stable page-oriented API so the browser client does not need to understand internal manifests, revision graphs, database identifiers, or validation-worker mechanics.

### Required forecast surface

```text
POST /api/v1/trial/forecasts
GET  /api/v1/trial/forecasts/{run_id}
GET  /api/v1/trial/forecasts/{run_id}/daily-curve
```

The page response must provide:

- daily P50/P80/P90 chart series;
- single-day peak card data;
- sustained seven-day peak card data;
- season cumulative quantity;
- mature-inventory or backlog data already produced by the forecast authority;
- data-gap and blocker summaries;
- model and parameter version evidence;
- export-ready data.

### Required actual and quality surface

```text
POST /api/v1/trial/actual-harvest/imports
GET  /api/v1/trial/actual-harvest/imports/{import_id}
POST /api/v1/trial/actual-harvest/imports/{import_id}/commit
POST /api/v1/trial/quality-reports
GET  /api/v1/trial/quality-reports/{report_id}
GET  /api/v1/trial/quality-reports/{report_id}/comparison
```

The API must expose sanitized, user-facing lifecycle states and deterministic errors. It must not expose SQL, stack traces, private database identifiers, raw internal exception text, or hidden authority records.

### API acceptance gate

- OpenAPI contracts are stable and tested;
- page payloads contain all data required by S5;
- authorization and concealment rules are enforced;
- CSV export is supported;
- no frontend-only recomputation of forecast or quality metrics is allowed.

## 8. V0.2-S5 — Two-page responsive trial frontend

### Objective

Deliver a browser-based trial with exactly two product pages.

### Frontend foundation

```text
FRONTEND_DIRECTORY=frontend
FRONTEND_LANGUAGE=TypeScript
FRONTEND_ARCHITECTURE=responsive_single_page_application
PC_PRIMARY=true
MOBILE_VIEWABLE=true
PAGE_COUNT=2
```

The implementation authorization for S5 must freeze the exact framework and dependency versions. The version plan does not authorize dependency installation yet.

### Page 1 — Forecast

Inputs:

- farm;
- variety;
- planting area;
- forecast season;
- forecast date;
- optional flowering date;
- optional maturity stage;
- optional already-picked quantity.

Outputs:

- daily P50/P80/P90 curve;
- single-day peak date and quantity;
- sustained seven-day peak interval and cumulative quantity;
- season cumulative quantity;
- mature-inventory or backlog summary;
- data gaps and blockers;
- current model version;
- CSV export.

Primary interaction:

```text
enter minimum forecast inputs
→ run forecast
→ inspect the complete-season curve and peak metrics
```

### Page 2 — Forecast versus actual

Functions:

- upload CSV or XLSX actual-harvest data;
- show import, validation, and commit status;
- select farm, variety, season, and historical forecast cutoff;
- overlay forecast and actual daily curves;
- display daily, peak, horizon, coverage, and interval metrics;
- compare the current model with the naive baseline;
- export the quality report.

Primary interaction:

```text
actual harvest
versus historical forecast
versus naive baseline
```

### User-experience boundary

```text
NO_CLI_REQUIRED_FOR_TRIAL_USER=true
COMPLEX_ADMIN=false
MULTI_LEVEL_DASHBOARD=false
LLM_CHAT=false
OPERATIONAL_RECOMMENDATIONS=false
STAFFING_RECOMMENDATIONS=false
PROCESSING_CAPACITY_RECOMMENDATIONS=false
CROSS_PLANT_DISPATCH=false
```

### Browser acceptance gate

A browser E2E test must prove the complete path:

```text
open application
→ submit forecast inputs
→ inspect curve and peaks
→ upload actual-harvest data
→ complete validation and commit
→ create point-in-time quality report
→ inspect forecast/actual/baseline comparison
→ export results
```

The layout must remain usable on desktop and readable on a mobile viewport.

## 9. V0.2 explicit non-scope

```text
MODEL_FORMULA_CHANGE=false
PARAMETER_TUNING=false
RESIDUAL_MODEL_CHANGE=false
MATURITY_CURVE_CHANGE=false
WEATHER_ADJUSTMENT_CHANGE=false
HARVEST_STATE_EQUATION_CHANGE=false
FORECAST_EXPLANATION=false
OPERATIONAL_RECOMMENDATIONS=false
PERSONNEL_CONFIGURATION=false
PROCESSING_CAPACITY_PLANNING=false
RECEIVING_CAPACITY_PLANNING=false
CROSS_PLANT_DISPATCH=false
LLM=false
DIALOGUE=false
MULTI_AGENT_EXPANSION=false
COMPLEX_FRONTEND_ADMIN=false
```

Issue #99 remains paused for V0.2.

## 10. Real-data acceptance requirement

V0.2 must use at least one approved historical dataset.

```text
ONE_APPROVED_HISTORICAL_DATASET=true
ONE_COMPLETE_SEASON_PREFERRED=true
```

The final report must state:

- covered farms, varieties, seasons, and dates;
- missing-data proportion;
- excluded records and reasons;
- which metrics are not representative because of insufficient coverage.

A narrow dataset must not be presented as global forecast accuracy.

## 11. Release acceptance gate

V0.2 may be released only when all gates are true:

```text
V0_2_S1_COMPLETE=true
V0_2_S2_COMPLETE=true
V0_2_S3_COMPLETE=true
V0_2_S4_COMPLETE=true
V0_2_S5_COMPLETE=true

ACTUAL_HARVEST_COMMIT_ATOMIC=true
POINT_IN_TIME_LABEL_SNAPSHOT_COMPLETE=true
HISTORICAL_BACKTEST_REPRODUCIBLE=true
LEAKAGE_AUDIT_PASSED=true
QUALITY_METRICS_COMPLETE=true
NAIVE_BASELINE_COMPARISON_COMPLETE=true
REAL_DATA_ACCEPTANCE_COMPLETE=true
POSTGRESQL_E2E_PASSED=true
FRONTEND_E2E_PASSED=true
BROWSER_FORECAST_FLOW_PASSED=true
BROWSER_FORECAST_VS_ACTUAL_FLOW_PASSED=true
NO_CLI_REQUIRED_FOR_TRIAL_USER=true
UNIQUE_ALEMBIC_HEAD=true
FULL_SUITE_CI_PASSED=true
```

Final release marker:

```text
BLUEBERRY_FORECAST_AGENT_V0_2_FORECAST_QUALITY_TRIAL_COMPLETE
```

## 12. Delivery and authorization order

Each slice requires an independent implementation authorization after the preceding slice is accepted.

```text
S1_ACCEPTED → S2_MAY_BE_AUTHORIZED
S2_ACCEPTED → S3_MAY_BE_AUTHORIZED
S3_ACCEPTED → S4_MAY_BE_AUTHORIZED
S4_ACCEPTED → S5_MAY_BE_AUTHORIZED
```

No acceptance automatically authorizes the next slice.

The current planning round authorizes documentation only:

```text
V0_2_PLAN_FROZEN=true
V0_2_IMPLEMENTATION_AUTHORIZED=false
V0_2_S1_IMPLEMENTATION_AUTHORIZED=false
BRANCH_FOR_S1_AUTHORIZED=false
MIGRATION_FOR_S1_AUTHORIZED=false
PRODUCTION_CODE_CHANGE_AUTHORIZED=false
FRONTEND_DEPENDENCY_INSTALL_AUTHORIZED=false
```
