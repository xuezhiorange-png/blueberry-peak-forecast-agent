# V0.2-S5 Frontend Implementation Authorization Freeze

## 1. Freeze status

This is an authorization-freeze and readiness audit. It is not an
implementation authorization.

```text
VERSION=0.2.0
SLICE=V0.2-S5
SLICE_NAME=TWO_PAGE_RESPONSIVE_TRIAL_FRONTEND_AND_BROWSER_E2E
REPOSITORY=xuezhiorange-png/blueberry-peak-forecast-agent
BASE_SHA=1f0221133fea0e887ea47c0a98206928c47003cf
BRANCH=docs/v0-2-s5-frontend-implementation-authorization
WORKTREE=/private/tmp/v0-2-s5-frontend-implementation-authorization

S1=ACTUAL_HARVEST_ATOMIC_COMMIT
S2=POINT_IN_TIME_ACTUAL_LABELS_AND_HISTORICAL_BACKTEST
S3=FORECAST_QUALITY_METRICS_AND_ONE_NAIVE_BASELINE
S4=FRONTEND_APPLICATION_API
S5=TWO_PAGE_RESPONSIVE_TRIAL_FRONTEND_AND_BROWSER_E2E
V0_2_S1_COMPLETE=true
V0_2_S2_COMPLETE=true
V0_2_S3_COMPLETE=true
V0_2_S4_COMPLETE=true
V0_2_S5_COMPLETE=false

S5_AUTHORIZATION_DOCUMENT_DRAFTED=true
S5_AUTHORIZATION_DOCUMENT_ACCEPTED=false
S5_IMPLEMENTATION_AUTHORIZED=false
DEPENDENCY_INSTALL_AUTHORIZED=false
FRONTEND_CODE_AUTHORIZED=false
BACKEND_GAP_FIX_AUTHORIZED=false
CI_CHANGE_AUTHORIZED=false
COMMIT_AUTHORIZED=false
PUSH_AUTHORIZED=false
PR_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
V0_2_RELEASE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

No frontend dependency was installed, no package manifest was created, and no
frontend, backend, test, migration, workflow, Docker, database, or CI file was
changed by this audit.

## 2. S4 completion evidence

| Evidence | Value |
| --- | --- |
| S4 feature PR | PR #139, merge `f3d314507c29902f25750a1e15ed38e528b35d4e` |
| First isolation fix | PR #140, merge `3ba167557803f8d412fa8fd760bda92bed80505e` |
| Second isolation fix | PR #141, merge `1f0221133fea0e887ea47c0a98206928c47003cf` |
| Final main | `1f0221133fea0e887ea47c0a98206928c47003cf` |
| Final post-merge CI | run `30466781142`, success |
| Final full suite | 3255 passed, 0 failed, 3 skipped |
| Issue closeout | Issue #102 remains open; comment `5120337076` |

S4 is the thin Trial application API. S5 does not create a new model, data
source, forecast formula, operations, admin, or governance slice.

## 3. Current frontend baseline

The repository has a pre-existing tracked `frontend/.gitkeep` placeholder only.
It is not a frontend application and is not removed by this audit.

```text
EXISTING_FRONTEND_DIRECTORY=true
EXISTING_FRONTEND_TRACKED_PATHS=frontend/.gitkeep
EXISTING_PACKAGE_MANIFEST_COUNT=0
EXISTING_LOCKFILE_COUNT=0
EXISTING_JS_TS_PATH_COUNT=0
EXISTING_NODE_CI_JOB_COUNT=0
EXISTING_BROWSER_E2E_COUNT=0
EXISTING_VITE_CONFIG_COUNT=0
EXISTING_PLAYWRIGHT_CONFIG_COUNT=0
```

Only `.github/workflows/ci.yml` exists. It owns eight pull-request Python/
PostgreSQL jobs and one non-pull-request `full-suite-canary`; it has no Node
setup, frontend job, browser job, or Playwright artifact contract.
`ci-shard-manifest.yml` is absent and is not created or changed here.

## 4. Product boundary and routes

Exactly two product pages are frozen:

| Page | Route | Scope |
| --- | --- | --- |
| Forecast | `/trial/forecast` | Inputs, forecast submission, curve, peaks, inventory/backlog, gaps, versions, CSV |
| Forecast versus actual | `/trial/quality` | Import lifecycle, point-in-time quality report, comparison, metrics, overlay when available, CSV |

One shared shell may provide loading, not-found, fatal-error, authorization,
conflict, and export-failure states. These are not third product pages. No
admin, login-management, dashboard, settings, user-management, data-governance,
model-management, or operational-recommendation page is in S5.

## 5. Frozen technical stack

Exact versions were read with `npm view <package> version engines dist-tags
--json` on 2026-07-30. No package was installed.

```text
NODE_VERSION=24.18.0
NODE_RELEASE_LINE=24_KRYPTON_LTS
PACKAGE_MANAGER=npm
PACKAGE_MANAGER_VERSION=11.16.0
SELECTED_NODE_VERSION=24.18.0
SELECTED_PACKAGE_MANAGER=npm 11.16.0
LOCKFILE=frontend/package-lock.json
INSTALL_COMMAND=npm ci
SPA_FRAMEWORK=React 19.2.8 with react-dom 19.2.8
SELECTED_SPA_FRAMEWORK=React 19.2.8
BUILD_TOOL=Vite 8.1.5 with @vitejs/plugin-react 6.0.4
SELECTED_BUILD_TOOL=Vite 8.1.5
TYPESCRIPT_VERSION=7.0.2
SELECTED_TYPESCRIPT_VERSION=7.0.2
ROUTER_PACKAGE=react-router
ROUTER_VERSION=7.18.1
ROUTER_MODE=DECLARATIVE_BROWSER_SPA
SELECTED_ROUTER=react-router 7.18.1
ROUTER=react-router 7.18.1
SERVER_STATE_LIBRARY=NONE
FORM_LIBRARY=NONE
SCHEMA_VALIDATION_LIBRARY=zod 4.4.3
CHART_LIBRARY_OR_STRATEGY=NATIVE_SVG
SELECTED_CHART_STRATEGY=NATIVE_SVG
CSS_STRATEGY=CSS Modules plus shared token CSS; no UI mega-framework
UNIT_TEST_RUNNER=Vitest 4.1.10
DOM_TEST_LIBRARY=@testing-library/react 16.3.2 with jsdom 30.0.1
SELECTED_UNIT_TEST_STACK=Vitest 4.1.10 + Testing Library 16.3.2 + jsdom 30.0.1
BROWSER_E2E_FRAMEWORK=@playwright/test 1.62.0
SELECTED_E2E_STACK=Playwright 1.62.0
LINT=eslint 10.8.0 plus typescript-eslint 8.65.0
FORMAT=prettier 3.9.6
REACT_TYPES=@types/react 19.2.17 and @types/react-dom 19.2.3
```

The future package manifest must use these exact versions, not `latest`, a
range, wildcard, or floating workspace version. React/Vite keep the two-page
SPA small; no global state or form library is needed; Zod is only for the
untrusted transport boundary; native SVG avoids client metric computation.
The DOM compatibility re-export package (react-router&#45;dom) is not selected
because the v7 package is a compatibility re-export for upgraded applications;
this repository is creating a new frontend application.

## 6. Frontend architecture

The future source namespaces are:

```text
frontend/src/app
frontend/src/pages
frontend/src/features/forecast
frontend/src/features/actualHarvest
frontend/src/features/quality
frontend/src/api
frontend/src/components
frontend/src/lib
frontend/src/test
frontend/e2e
```

The API client calls only `/api/v1/trial/*`. It never calls internal
actual-harvest, planning, master-data, or database endpoints. It does not
receive database IDs. Public `run_id`, `import_id`, and `report_id` may enter
URL/session state only through Trial responses.

The frontend does not copy forecast, quality, baseline, single-day peak,
sustained-seven-day peak, or CSV/XLSX parsing logic. Decimal values remain
strings at the transport edge; dates and RFC3339 timestamps remain distinct.
One helper owns idempotency-key generation and persistence. Error-code to copy
mapping is centralized; raw exception text, stacks, paths, secrets, and
environment variables never enter the UI.

## 7. S4 Trial API matrix

`backend/app/main.py` registers the router under `/api/v1/trial`.
`backend/app/api/trial.py` exposes exactly these 11 endpoints:

```text
S4_ENDPOINT_COUNT=11
```

| # | Method and route | Request | Response / status | ID, auth, lifecycle | Error and browser owner |
| --- | --- | --- | --- | --- | --- |
| 1 | POST `/api/v1/trial/forecasts` | `TrialForecastCreateRequest` | `TrialForecastSummaryResponse`, 200 | `run_id`; `TrialActorDep`; `status` | 422 invalid, 409 replay, 503 unavailable, 500 safe internal; Forecast submit |
| 2 | GET `/api/v1/trial/forecasts/{run_id}` | path `run_id` | `TrialForecastSummaryResponse`, 200 | `run_id`; `TrialActorDep`; `status` | 404 concealment, 503/500; Forecast summary |
| 3 | GET `/api/v1/trial/forecasts/{run_id}/daily-curve` | path `run_id` | `TrialForecastDailyCurveResponse`, 200 | `run_id`; `TrialActorDep`; row status | 404/503/500; daily curve |
| 4 | GET `/api/v1/trial/forecasts/{run_id}/export.csv` | path `run_id` | CSV bytes, 200 | `run_id`; `TrialActorDep`; export result | `text/csv`, attachment header, `x-request-id`; Forecast export |
| 5 | POST `/api/v1/trial/actual-harvest/imports` | `ActualHarvestApiCreateImportRequest` | `TrialActualHarvestImportCreateResponse`, 200 | `import_id`; `may_create`; import status | 422/403/404/503; metadata only, no file bytes; create import |
| 6 | GET `/api/v1/trial/actual-harvest/imports/{import_id}` | path `import_id` | `TrialActualHarvestImportStatusResponse`, 200 | `import_id`; `may_preview`; lifecycle status/counts | 404 concealment; status polling |
| 7 | POST `/api/v1/trial/actual-harvest/imports/{import_id}/commit` | `ActualHarvestApiCommitRequest` | `TrialActualHarvestCommitResponse`, 200 | `import_id`; `may_commit`; committed/blocked | 409 not-ready/conflict/concurrency, 404/503; commit |
| 8 | POST `/api/v1/trial/quality-reports` | `TrialQualityReportCreateRequest` | `TrialQualityReportResponse`, 200 | `report_id`; `TrialActorDep`; computability | 422/404/409/503; quality create |
| 9 | GET `/api/v1/trial/quality-reports/{report_id}` | path `report_id` | `TrialQualityReportResponse`, 200 | `report_id`; `TrialActorDep`; computability | 404/503/500; quality report |
| 10 | GET `/api/v1/trial/quality-reports/{report_id}/comparison` | path `report_id` | `TrialQualityComparisonResponse`, 200 | `report_id`; `TrialActorDep`; comparison state | 404/503/500; baseline comparison |
| 11 | GET `/api/v1/trial/quality-reports/{report_id}/export.csv` | path `report_id` | CSV bytes, 200 | `report_id`; `TrialActorDep`; export result | `text/csv`, attachment header, `x-request-id`; quality export |

JSON success responses use the listed DTOs. Decimal fields are canonical JSON
Decimal values, aware timestamps are required, and CSV uses canonical Decimal,
date, UTC timestamp, newline, and formula-injection-safe serialization. The
CSV handlers return `content-disposition` and `x-request-id`.

`TrialErrorResponse` is `{request_id,status,code,message_template_id,retryable,details}`.
Trial validation is 422 `TRIAL_REQUEST_INVALID`; resource concealment is 404;
mapped known errors include `IMPORT_NOT_READY_FOR_COMMIT`,
`CONFLICTING_REPLAY`, `CONCURRENCY_CONFLICT`, and
`TRIAL_AUTHORIZATION_UNAVAILABLE`. Unexpected errors become safe 500
`TRIAL_INTERNAL_ERROR`.

The default service is fail-closed for forecast authority/read/daily/export and
quality persistence/read/comparison/export. S4 tests use a deterministic
synthetic service seam; that is contract evidence, not production readiness.

## 8. Browser action mapping

The required 42 actions are mapped below. Frontend adapters do not compensate
for missing backend capabilities.

| Page | Action | Classification |
| --- | --- | --- |
| Forecast | enter farm; enter variety | SUPPORTED_WITH_FRONTEND_ADAPTER_ONLY |
| Forecast | enter planting area; optional flowering date; optional maturity stage; optional already-picked quantity | MISSING_BACKEND_CAPABILITY |
| Forecast | enter season; enter forecast date | SUPPORTED_WITH_FRONTEND_ADAPTER_ONLY |
| Forecast | create forecast; read summary; read daily curve | MISSING_BACKEND_CAPABILITY |
| Forecast | view P50/P80/P90; single-day peak; cumulative; mature inventory; backlog; gaps/blockers; model/parameter versions; export CSV | SUPPORTED_BY_S4 |
| Forecast | view sustained seven-day peak | AMBIGUOUS_CONTRACT |
| Quality | choose CSV; choose XLSX; create import; choose historical cutoff | SUPPORTED_WITH_FRONTEND_ADAPTER_ONLY |
| Quality | upload bytes; append file content; trigger validation; view invalid-record result; create quality report; read quality report; read comparison; view daily overlay; view 7/14/21 metrics | MISSING_BACKEND_CAPABILITY |
| Quality | poll import status; commit import; view excluded/not-computable reasons; export quality CSV | SUPPORTED_BY_S4 |
| Quality | choose farm/variety/season; view daily metrics; peak metrics; P80/P90 coverage; interval metrics | AMBIGUOUS_CONTRACT |

Expanded evidence:

- Farm/variety/season are public business keys in the request, but there is no
  Trial lookup surface. Until an authority is frozen, use labeled business-key
  input only; do not query internal tables.
- Planting area, flowering date, maturity stage, and already-picked quantity
  are absent from `TrialForecastCreateRequest`.
- The Trial import route creates metadata, but has no file bytes, filename, MIME
  type, append, validation trigger, or invalid-row response.
- The internal `/api/v1/actual-harvest/*` append/preview/validate/errors routes
  are not valid S5 frontend dependencies.
- `TrialQualityReportResponse` has aggregate/status fields but no daily forecast
  and actual series. Aggregate metrics are not a daily overlay.
- `TrialQualityComparisonResponse` exists, but the default comparison adapter
  is fail-closed and synthetic comparison is blocked.

```text
S5_BROWSER_ACTION_COUNT=42
SUPPORTED_ACTION_COUNT=12
ADAPTER_ONLY_ACTION_COUNT=8
MISSING_BACKEND_CAPABILITY_COUNT=16
AMBIGUOUS_CONTRACT_COUNT=6
OUT_OF_V0_2_SCOPE_COUNT=0
```

## 9. Capability verdicts and gap ledger

### 9.1 Upload and validation

The repository has internal `parse_csv` and `parse_xlsx` functions, but the
Trial API has no file transport. The non-Trial actual-harvest API accepts JSON
metadata and JSON records and exposes append, preview, seal, validate, errors,
and commit routes. Those routes are outside the permitted frontend boundary.
The Trial create DTO rejects server-owned file metadata and has no bytes,
filename, MIME type, or content hash field.

```text
FILE_BYTES_TRANSPORT=missing_from_trial_api
FILE_NAME=missing_from_trial_api
MIME_TYPE=missing_from_trial_api
CSV_PARSING=internal_only
XLSX_PARSING=internal_only
BATCH_RECORD_APPEND=internal_non_trial_only
VALIDATION_TRIGGER=internal_non_trial_only
VALIDATION_STATUS_READBACK=trial_status_only_without_full_summary
INVALID_ROW_SUMMARY=internal_non_trial_only
UPLOAD_API_READINESS=BLOCKED
S5_BLOCKER_UPLOAD_API=TRIAL_FILE_BYTES_FILENAME_MIME_APPEND_VALIDATE_AND_INVALID_ROW_SURFACE_MISSING
```

The frontend must not call internal routes, parse files to replace the backend,
write to the database, or fabricate a committed import.

### 9.2 Forecast input authority

The Trial request accepts public business keys for season, farm, subfarm, and
variety plus model/parameter/policy identity. It does not accept planting area,
flowering date, maturity stage, or already-picked quantity. There is no Trial
lookup endpoint for farm, variety, or season.

```text
FORECAST_INPUT_AUTHORITY_READINESS=BLOCKED
S5_BLOCKER_FORECAST_INPUT_AUTHORITY=REQUIRED_PRODUCT_INPUTS_AND_LOOKUP_SURFACE_NOT_IN_TRIAL_CONTRACT
```

### 9.3 Forecast/actual overlay

`TrialQualityReportResponse` has `daily_metrics`, status fields, breakdowns,
baseline result, reason codes, coverage counts, and excluded row counts. It has
no daily forecast series and no daily actual series for an overlay.

```text
DAILY_OVERLAY_READINESS=BLOCKED
S5_BLOCKER_DAILY_FORECAST_ACTUAL_OVERLAY=QUALITY_RESPONSE_HAS_NO_DAILY_FORECAST_AND_ACTUAL_SERIES
```

### 9.4 Comparison and export

The comparison endpoint and DTO exist, but the default adapter is fail-closed,
synthetic comparison is blocked, and the required horizon and interval metric
semantics are not fully typed.

```text
QUALITY_COMPARISON_READINESS=BLOCKED
S5_BLOCKER_QUALITY_COMPARISON=QUALITY_ADAPTER_AND_METRIC_SEMANTICS_NOT_READY
CSV_EXPORT_READINESS=READY
```

CSV export is ready at the S4 transport-contract level: both routes return
`text/csv`, attachment headers, request correlation, canonical Decimal/date/time
serialization, and formula-injection-safe values. Full product execution still
depends on the missing forecast and quality provider adapters.

### 9.5 Blocking ledger

```text
S5_BLOCKER_COUNT=10
S5_BLOCKERS=
S5_BLOCKER_UPLOAD_API_MISSING,
S5_BLOCKER_FORECAST_INPUT_AUTHORITY_MISSING,
S5_BLOCKER_FORECAST_AUTHORITY_ADAPTER_MISSING,
S5_BLOCKER_FORECAST_READ_ADAPTER_MISSING,
S5_BLOCKER_DAILY_CURVE_ADAPTER_MISSING,
S5_BLOCKER_QUALITY_ADAPTERS_MISSING,
S5_BLOCKER_DAILY_FORECAST_ACTUAL_OVERLAY_MISSING,
S5_BLOCKER_QUALITY_COMPARISON_SEMANTICS_MISSING,
S5_BLOCKER_HORIZON_METRIC_SHAPE_MISSING,
S5_BLOCKER_TRIAL_ACTOR_AUTHORIZATION_UNAVAILABLE
```

## 10. Data, error, and lifecycle policy

### 10.1 Decimal, time, identity, and errors

- Keep Decimal quantities as strings at the transport edge; format only for
  display and never accumulate native floats.
- Keep business dates distinct from timezone-aware RFC3339 timestamps.
- One helper owns idempotency-key generation and persistence. Exact replay and
  conflicting replay remain different states.
- `request_id` is correlation only, never a business, run, report, ordering, or
  idempotency identity.
- A centralized error catalog maps `code` and `retryable` to user copy. Raw
  exception text, stacks, paths, secrets, and environment variables are never
  rendered.
- 404 is concealed not-found behavior, not an authorization or database leak.
  401/403 are authorization states. Retry only retryable 503/network outcomes.
- CSV downloads are opaque server bytes with the server-provided filename.

### 10.2 UI states

Every async resource distinguishes:

```text
IDLE -> SUBMITTING -> PENDING -> COMPLETED
                       |          |
                       v          v
                    BLOCKED    EMPTY
                       |
                       v
                     ERROR
```

Actual import lifecycle is displayed precisely:

```text
RECEIVED -> UPLOADING -> SEALED -> PARSING -> VALIDATING -> VALIDATED -> COMMITTED
                              \-> BLOCKED
                              \-> CANCELLED
```

The exact DTO state names remain authoritative. `NOT_COMPUTABLE`,
`INSUFFICIENT_COVERAGE`, `SEMANTICS_UNVERIFIED`, and
`LOWER_BOUND_UNAVAILABLE` are never displayed as zero. Sustained seven-day
peak is rendered from the backend state/value only; no frontend window is
recomputed.

The shell must cover loading skeleton, empty, partial result, validation error,
authorization concealment, conflicting replay, timeout, retryable/non-retryable
error, export failure, stale polling, and navigation-away behavior. Polling
stops on navigation away and cannot create a second mutation request.

## 11. Responsive and accessibility boundary

```text
PC_PRIMARY=true
MOBILE_VIEWABLE=true
PAGE_COUNT=2
MULTI_LEVEL_DASHBOARD=false
DESKTOP_MIN_WIDTH=1024px
MOBILE_MIN_WIDTH=360px
BREAKPOINTS=768px,1024px,1280px
TOUCH_TARGET_MINIMUM=44px
```

- Desktop is the dense analysis layout; mobile supports status review,
  submission, and export.
- Forms stack below 768px. Tables become labeled cards below 768px.
- Charts use a horizontally scrollable chart region, never page-wide overflow.
- Mobile submit/export actions may be sticky inside the safe-area inset and may
  not hide focused fields or the keyboard.
- All actions are keyboard reachable; focus follows visual order and is visible.
- Reduced-motion users receive no animated polling or chart motion.
- Visual direction is a professional agricultural forecasting tool: states,
  peaks, blockers, and charts lead; decorative AI gradients and card walls do
  not.

## 12. Browser E2E freeze

```text
E2E_BACKEND=REAL_FASTAPI_PROCESS
E2E_DATABASE=ISOLATED_POSTGRESQL_16
E2E_DATA=DETERMINISTIC_SYNTHETIC_FIXTURES
E2E_NETWORK_MOCKING_ALLOWED=false
E2E_BROWSER=Chromium only
E2E_VIEWPORTS=1440x900 desktop and 390x844 mobile
E2E_ARTIFACTS=screenshot,trace,video,junit
```

E2E-A, Forecast:

```text
open /trial/forecast
-> enter minimum contract-supported inputs
-> submit forecast
-> inspect P50/P80/P90 daily curve
-> inspect single-day peak
-> inspect sustained seven-day state without recomputation
-> inspect cumulative, inventory, backlog, gaps, blockers, and versions
-> export forecast CSV
```

E2E-B, Forecast versus actual:

```text
open /trial/quality
-> choose deterministic CSV or XLSX fixture
-> upload through public Trial file transport
-> inspect validation lifecycle and invalid-record result
-> commit import
-> create point-in-time quality report
-> inspect forecast-versus-actual daily overlay
-> inspect daily, peak, 7/14/21 horizon, P80/P90, interval, and exclusion metrics
-> inspect naive-baseline comparison
-> export quality CSV
```

E2E-B is blocked until Round A supplies the public file transport, validation
result, invalid-row result, quality metric shape, and daily overlay. Full
network mocks may not be used to claim the product flow.

## 13. Test plan

Future unit tests cover transport serialization, error mapping, idempotency,
state transitions, Decimal/time formatting, responsive state selection, and
the no-client-recomputation rule. DOM tests cover both pages, loading/empty/
blocked/not-computable states, keyboard focus, mobile card transformation, and
export failure.

Backend contract tests are required for each Round A surface and use the
existing Trial dependency seam. Browser tests use a real FastAPI process,
isolated PostgreSQL 16, deterministic synthetic fixtures, and no network
interception. No real business data is permitted in CI fixtures.

## 14. CI ownership freeze

```text
CI_OPTION=OPTION_A_ADD_DEDICATED_FRONTEND_PR_JOBS
CHANGED_PATH_FILTERS_ALLOWED=false
CI_SHARD_MANIFEST_UPDATE_REQUIRED=false
```

No path filter is used for dedicated jobs; they run on every pull request and
every push to `main`, so backend Trial contract changes cannot silently skip
frontend checks. Existing Python jobs and `full-suite-canary` retain ownership.

| Job | Trigger | Responsibility |
| --- | --- | --- |
| `frontend-static` | pull_request and main push | npm cache, `npm ci`, ESLint, Prettier check, TypeScript check, Vite build |
| `frontend-unit` | pull_request and main push | Vitest, Testing Library, JUnit |
| `frontend-e2e` | pull_request and main push after Round A | Playwright Chromium with FastAPI and PostgreSQL 16 |

CI freeze:

- Node is exact `24.18.0` in the `24_KRYPTON_LTS` release line; npm is exact
  `11.16.0`; lockfile is required.
- npm `11.16.0` is the npm version bundled with the frozen Node.js `24.18.0`
  runtime. CI must not globally upgrade npm before running `npm ci`.
- npm cache key is `frontend-npm-${{ runner.os }}-node24.18.0-${{ hashFiles('frontend/package-lock.json') }}`.
- Playwright cache is keyed by OS, Node, lockfile hash, and exact browser
  package version.
- E2E creates/drops a unique PostgreSQL 16 database, starts FastAPI on a
  run-specific port, waits on readiness, and starts the frontend preview on a
  distinct port.
- JUnit is `frontend/test-results/playwright-junit.xml`; screenshots, traces,
  videos, and failed-step logs are uploaded from `frontend/test-results/`.
- Every job writes failed test identifiers, commands, versions, and artifacts
  to `GITHUB_STEP_SUMMARY`.
- `full-suite-canary` remains the backend full pytest gate; it is not replaced
  by `frontend-e2e`. S5 closeout requires both.
- No `ci-shard-manifest.yml` update is needed because frontend jobs do not own
  Python pytest nodes, and the absent file must not be created.

No workflow file is changed by this audit.

## 15. Future changed-path allowlist

The following is the complete future S5 implementation allowlist. Any path not
listed is forbidden unless a new authorization explicitly changes this freeze.

### CREATE_PATHS

~~~text
frontend/package.json
frontend/package-lock.json
frontend/index.html
frontend/tsconfig.json
frontend/vite.config.ts
frontend/eslint.config.mjs
frontend/prettier.config.mjs
frontend/playwright.config.ts
frontend/src/main.tsx
frontend/src/app/App.tsx
frontend/src/app/routes.tsx
frontend/src/app/app.css
frontend/src/pages/ForecastPage.tsx
frontend/src/pages/QualityPage.tsx
frontend/src/pages/NotFoundState.tsx
frontend/src/features/forecast/index.ts
frontend/src/features/forecast/forecastApi.ts
frontend/src/features/forecast/forecastSchemas.ts
frontend/src/features/forecast/ForecastForm.tsx
frontend/src/features/forecast/ForecastResult.tsx
frontend/src/features/actualHarvest/index.ts
frontend/src/features/actualHarvest/importApi.ts
frontend/src/features/actualHarvest/ImportLifecycle.tsx
frontend/src/features/quality/index.ts
frontend/src/features/quality/qualityApi.ts
frontend/src/features/quality/qualitySchemas.ts
frontend/src/features/quality/QualityReport.tsx
frontend/src/features/quality/QualityOverlay.tsx
frontend/src/api/trialClient.ts
frontend/src/api/errorCatalog.ts
frontend/src/lib/idempotency.ts
frontend/src/lib/formatters.ts
frontend/src/components/AsyncState.tsx
frontend/src/components/ErrorState.tsx
frontend/src/components/ExportButton.tsx
frontend/src/components/StatusBadge.tsx
frontend/src/components/PeakSummary.tsx
frontend/src/components/DailyCurve.tsx
frontend/src/test/setup.ts
frontend/src/test/ForecastPage.test.tsx
frontend/src/test/QualityPage.test.tsx
frontend/src/test/trialClient.test.ts
frontend/e2e/forecast-flow.spec.ts
frontend/e2e/quality-flow.spec.ts
frontend/e2e/fixtures/actual-harvest.csv
frontend/e2e/fixtures/actual-harvest.xlsx
~~~

### MODIFY_PATHS

~~~text
.github/workflows/ci.yml
backend/app/api/trial.py
backend/app/trial.py
backend/app/main.py
backend/app/actual_harvest_import/api_schemas.py
backend/app/actual_harvest_import/api_auth.py
backend/app/actual_harvest_import/api_errors.py
backend/app/api/actual_harvest_imports.py
backend/tests/trial/test_api.py
backend/tests/trial/test_contract.py
backend/tests/trial/test_upload_contract.py
~~~

Round A may use only the explicitly listed backend files and Trial tests.
backend/tests/trial/test_upload_contract.py is a future creation path, not an
existing file. No migration or data model path is allowed.

### FORBIDDEN_PATHS

~~~text
frontend/.gitkeep
ci-shard-manifest.yml
docker-compose.yml
docker-compose.override.yml
pyproject.toml
uv.lock
backend/alembic/**
backend/app/forecast_quality/**
backend/app/models/**
backend/app/analytics/**
backend/app/recommendations/**
backend/tests/integration/**
backend/tests/rolling_backtest/**
docs/v0-2/s5-frontend-implementation-authorization.md
Issue #102 content or state
all branches, worktrees, and remote refs
~~~

Directory rules are subordinate to the explicit file lists. No generic
backend/**, docs/**, .github/**, or "files as needed" authority exists.

~~~text
FUTURE_CHANGED_FILE_CEILING=57
FUTURE_BACKEND_CHANGE_CEILING=11
FUTURE_WORKFLOW_CHANGE_CEILING=1
~~~

The file ceiling is a hard maximum across CREATE_PATHS and MODIFY_PATHS. The
backend ceiling is the eleven explicitly listed backend paths. The workflow
ceiling is exactly one file.

## 16. S5 implementation rounds

The audit found blocking Trial/API gaps, so the delivery rounds are:

~~~text
S5_ROUND_A=BLOCKING_S4_API_GAP_CLOSURE
S5_ROUND_A_REQUIRED=true
S5_ROUND_B=FRONTEND_FOUNDATION_AND_FORECAST_PAGE
S5_ROUND_C=QUALITY_PAGE_AND_BROWSER_E2E
S5_IMPLEMENTATION_ROUND_COUNT=3
~~~

Round A must close public file bytes/name/MIME transport, append/validate/
invalid-row readback, forecast input authority, quality metric shape, daily
overlay, comparison semantics, and actor authorization. Round B may not start
until Round A passes its backend gates. Round C may not claim E2E-B success
until the real import and overlay path is available.

## 17. Acceptance commands and gates

These are future acceptance commands and were not executed by this audit:

~~~text
# Backend Round A
uv run pytest -q backend/tests/trial
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/app
git diff --check

# Frontend static and unit
npm ci --prefix frontend
npm --prefix frontend run lint
npm --prefix frontend run format:check
npm --prefix frontend run typecheck
npm --prefix frontend run test:unit -- --run
npm --prefix frontend run build

# PostgreSQL 16 browser E2E
alembic -c backend/alembic.ini upgrade head
npm --prefix frontend run test:e2e
~~~

Acceptance requires the two routes only, no internal API calls, no client
metric recomputation, all error/lifecycle states, desktop and mobile viewports,
Trial backend contract tests, frontend static/unit gates, a real FastAPI
process, isolated PostgreSQL 16, deterministic fixtures, and JUnit/Playwright
artifacts. E2E-B remains blocked until Round A is implemented and tested.

## 18. Rollback boundary

Before any future implementation authorization, rollback means removing only an
authorized S5 commit or reverting only its explicitly allowed paths. It must
not reset main, rewrite history, remove unrelated worktrees, delete evidence,
alter S4 commits, modify Issue #102, or remove migrations. Every Round A
backend change must be independently reviewable and reversible before Round B.

## 19. Explicit non-scope

S5 does not authorize a new slice, frontend data-source discovery, model
training or optimization, parameter changes, forecast formula changes, actual
data ingestion outside the public Trial contract, production database access,
admin or IAM product work, recommendation/operations pages, dashboard
expansion, migration changes, database model changes, real business data, or
workflow changes in this audit.

## 20. Governance stop block

~~~text
S5_AUTHORIZATION_DOCUMENT_DRAFTED=true
S5_AUTHORIZATION_DOCUMENT_ACCEPTED=false
S5_IMPLEMENTATION_AUTHORIZED=false
DEPENDENCY_INSTALL_AUTHORIZED=false
FRONTEND_CODE_AUTHORIZED=false
BACKEND_GAP_FIX_AUTHORIZED=false
CI_CHANGE_AUTHORIZED=false
COMMIT_AUTHORIZED=false
PUSH_AUTHORIZED=false
PR_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
V0_2_RELEASE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true

FRONTEND_IMPLEMENTED=false
FRONTEND_DIRECTORY_CREATED=false
DEPENDENCY_INSTALLED=false
PACKAGE_MANIFEST_CREATED=false
LOCKFILE_CREATED=false
BACKEND_CHANGED=false
TEST_CHANGED=false
WORKFLOW_CHANGED=false
DATABASE_CHANGED=false
MIGRATION_CHANGED=false
COMMIT_PERFORMED=false
PUSH_PERFORMED=false
PR_CREATED=false
CI_TRIGGERED=false
ISSUE102_UPDATED=false
ISSUE102_CLOSED=false
MANDATORY_STOP=true
~~~
