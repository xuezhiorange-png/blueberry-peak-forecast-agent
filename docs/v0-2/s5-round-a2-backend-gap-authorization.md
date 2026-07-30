# V0.2-S5 Round A2 Backend Gap Authorization Freeze

## 1. Document identity and stop state

This document is a read-only audit of the remaining S5 Round A2 backend gaps.
It freezes future authorization boundaries. It does not authorize the
implementation described below.

```text
VERSION=0.2.0
SLICE=V0.2-S5
ROUND=S5_ROUND_A2
REPOSITORY=xuezhiorange-png/blueberry-peak-forecast-agent
BASE_SHA=96fd95b8fdf03040329b1294ab7fbad9371dc3b3
BRANCH=docs/v0-2-s5-round-a2-authorization
DOCUMENT_PATH=docs/v0-2/s5-round-a2-backend-gap-authorization.md

S5_ROUND_A1_COMPLETE=true
S5_ROUND_A2_AUTHORIZATION_DRAFTED=true
S5_ROUND_A2_AUTHORIZATION_ACCEPTED=false
S5_ROUND_A2_IMPLEMENTATION_AUTHORIZED=false
S5_ROUND_B_AUTHORIZED=false
S5_ROUND_C_AUTHORIZED=false
V0_2_RELEASE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
MANDATORY_STOP=true
```
The audit below distinguishes existing production evidence from a public Trial
adapter. Existing domain calculators, persistence tables, fixtures, and test
seams are not treated as a completed Trial capability.

## 2. A1 closure evidence

```text
S5_ROUND_A1_COMPLETE=true
S5_ROUND_A1_PR=143
S5_ROUND_A1_MERGE_SHA=96fd95b8fdf03040329b1294ab7fbad9371dc3b3
S5_ROUND_A1_POST_MERGE_CI_RUN=30550548393
S5_ROUND_A1_POST_MERGE_CI=success
S5_ROUND_A1_POST_MERGE_CI_EVENT=push
S5_ROUND_A1_POST_MERGE_FULL_SUITE=true
```

The post-merge run completed successfully with its full-suite-canary job
successful. A1 is closed for the following capabilities:

- Trial CSV and XLSX raw-byte file transport;
- safe filename and MIME validation;
- bounded request-body reads;
- append, seal, and validate lifecycle delegation;
- invalid-row readback;
- server-configured fail-closed Trial actor authorization;
- concealed owner, source, and channel scope failures;
- persisted-batch and upload-channel equality.

A1 does not make any Forecast or Quality production adapter available.

## 3. Audit result

Readiness in this table means readiness of the public `/api/v1/trial/*`
surface, not merely availability of an internal calculator or a synthetic
test double.

| Capability | Status | Existing evidence | Blocking gap |
| --- | --- | --- | --- |
| `FORECAST_INPUT_AUTHORITY` | MISSING | `core_forecast.repository.SqlAlchemyCoreForecastRepository.resolve_business_identity` resolves identity from internal IDs; `planning` has partial business-key lookups | No single Trial read-only authority surface; no persisted marketable-retention policy authority; optional Trial inputs are not mapped into the Core request |
| `FORECAST_CREATE_PRODUCTION_ADAPTER` | MISSING | `core_forecast.application.execute_core_forecast_run` performs authority-bound execution and request-hash replay | `DefaultTrialApplicationService.create_forecast` is fail-closed and the Trial request cannot compose the complete Core request |
| `FORECAST_READ_PRODUCTION_ADAPTER` | MISSING | `CoreForecastRunRepository.get_run_by_request_hash` and canonical reload exist | No Trial public identity mapping, actor-scoped read, or typed projection |
| `FORECAST_DAILY_CURVE_PRODUCTION_ADAPTER` | MISSING | `CoreForecastRunRepository.list_daily_rows` reloads persisted rows | No Trial projection; the current method is fail-closed |
| `FORECAST_EXPORT_PRODUCTION_ADAPTER` | MISSING | Core persistence contains canonical daily rows and metrics | No Trial canonical CSV projection; the current method is fail-closed |
| `QUALITY_REPORT_CREATE_PRODUCTION_ADAPTER` | MISSING | `forecast_quality.persistence.persist_quality_evaluation` persists complete evidence | No Trial composition from committed import, S2 binding, and forecast snapshot; the current method is fail-closed |
| `QUALITY_REPORT_READ_PRODUCTION_ADAPTER` | MISSING | Quality run, child evidence, and manifest tables exist | No public load-by-instance-hash function and no Trial typed readback |
| `QUALITY_COMPARISON_PRODUCTION_ADAPTER` | MISSING | `forecast_quality.comparison.compute_model_baseline_comparisons` and V2 persistence exist | No Trial readback of persisted comparison evidence; the current method is fail-closed |
| `QUALITY_EXPORT_PRODUCTION_ADAPTER` | MISSING | Persisted quality evidence is canonical | No Trial export projection; the current method is fail-closed |
| `DAILY_FORECAST_ACTUAL_OVERLAY` | MISSING | S2 rows persist forecast and actual evidence by date, quantile, horizon, and status | No public backend projection; frontend must not join rows |
| `DAILY_METRIC_SHAPE` | AMBIGUOUS | `DailyMetricResult` is typed internally | `TrialQualityReportResponse.daily_metrics` is `tuple[dict[str, object], ...]` |
| `PEAK_METRIC_SHAPE` | AMBIGUOUS | Core Forecast persists typed single-day and sustained-seven-day metrics | Trial peak fields are untyped dictionaries and Quality peak status has no value/provenance shape |
| `HORIZON_7_14_21_METRIC_SHAPE` | AMBIGUOUS | S2 enforces horizons `7`, `14`, and `21` and Quality metrics carry horizon breakdowns | No explicit typed Trial horizon object with nullability and reason codes |
| `P80_P90_COVERAGE_SHAPE` | AMBIGUOUS | Quality metric and comparison evidence carries coverage/status fields | No typed Trial P80/P90 coverage response |
| `INTERVAL_METRIC_SHAPE` | AMBIGUOUS | Comparison vocabulary explicitly records unavailable lower-bound semantics | No complete Trial interval DTO; unavailable values must remain null |
| `COMPARISON_SEMANTICS` | READY | S3 comparison calculator, baseline evidence, V2 policy, result, and result-set hashes are persisted by migration `0025` | Public Trial adapter is still missing; no frontend readiness follows from this status |

## 4. Forecast input authority

### 4.1 Field source contract

| Field | Source | Public Trial expression | Current state |
| --- | --- | --- | --- |
| `farm` | `dim_farm` business name, resolved inside the server | exact `farm_business_key`; no internal ID | Existing master table; no single Trial authority response |
| `subfarm` | `dim_subfarm` name scoped by resolved farm | exact `subfarm_business_key` | Existing master table; cross-farm ambiguity must be concealed |
| `variety` | `dim_variety.code` | exact `variety_business_key` | Existing master table; no free-form lookup bypass |
| `season` | `dim_season.code` | exact `season_business_key` | Existing unique business key |
| `forecast_date` | server-derived from the accepted cutoff and selected authority period | `forecast_date: date` in response/authority DTO | Current request exposes only an aware `forecast_cutoff_at` |
| `planting_area` | user-submitted canonical quantity, then bound to the selected farm/subfarm/variety/season authority | `planting_area_mu: canonical decimal string` | Current Trial request does not expose it |
| `flowering_date` | optional user input only when a frozen domain override consumes it; otherwise a typed blocker | `flowering_date_or_null: date` | Current Core request has no consumer |
| `maturity_stage` | optional typed domain value from a frozen authority/override | bounded enum/string, never arbitrary text | Current Core request has no consumer |
| `already_picked_quantity` | optional canonical quantity from an accepted actual-harvest authority or explicit supported override | `already_picked_quantity_kg_or_null` | Current Core request has no consumer |
| `model_identity` | persisted maturity model run/artifact plus Core code authority | server-owned public identity/hash | Existing authority evidence is internal and not Trial-projected |
| `parameter_identity` | `ParameterLibraryVersion`, parameter observations/inference, and Task 9 parameter package | server-owned version/hash | Existing parameter infrastructure; selection policy must be explicit |
| `policy_identity` | persisted marketable-retention policy snapshot | server-owned version/hash | Missing as a queryable production authority; current CLI accepts fixture policy input |

The client submits business keys and the allowed user input quantities/dates.
The server resolves all internal IDs, Task 8 and Task 9 run references, model,
parameter, code, and policy identities. No client field may contain an internal
database ID. A missing or ambiguous business key is a fail-closed typed error;
cross-scope resources are concealed as `404 RESOURCE_NOT_FOUND`.

Business-key strings are exact identifiers, not arbitrary search text. No Trial
client may query `dim_*`, planning, Task 8, Task 9, or parameter tables
directly. The one public authority surface is:

```text
GET /api/v1/trial/forecast-input-authority
```

It returns typed seasons, farms, subfarms, varieties, allowed relationships,
display labels, authority version, and authority hash. It returns no database
IDs and is unavailable with `503 TRIAL_AUTHORITY_UNAVAILABLE` when the server
cannot prove a complete authority snapshot.

The adapter must not silently discard `flowering_date_or_null`,
`maturity_stage_or_null`, or `already_picked_quantity_kg_or_null`. If the
authoritative Core service cannot consume a submitted optional field, the
request fails with a typed blocker and does not execute a forecast.

No forecast formula, model training rule, parameter value, or maturity
algorithm changes as part of this contract.

### 4.2 Existing Forecast authority chain

The existing production chain is:

```text
CoreForecastScope and CompleteDailyMarketableCurveRequest
  -> SqlAlchemyCoreForecastRepository.load_task8_authority
  -> SqlAlchemyCoreForecastRepository.load_task9_authority
  -> SqlAlchemyCoreForecastRepository.resolve_business_identity
  -> execute_core_forecast_run
  -> compose_complete_daily_marketable_curve
  -> compute_core_forecast_metrics
  -> CoreForecastRunRepository.save_completed_run
  -> CoreForecastRunRepository.get_run_by_request_hash
  -> list_daily_rows / list_metrics
```

The Core execution already enforces completed Task 9, cutoff equality, code
authority availability at the Task 9 cutoff, canonical input/request/result
hashes, and exact replay. `CoreForecastRunModel` persists Task 8 and Task 9
references, policy hash, code authority hash, curve hash, metric hash, and
result hash. `CoreForecastDailyRowModel` and `CoreForecastMetricModel` persist
the daily and peak evidence.

The current gap is composition, not a second forecast algorithm. The Trial
adapter must resolve the complete authority bundle, call
`execute_core_forecast_run` once, and project only its persisted result. The
public `run_id` is the canonical Core `request_hash` (lowercase SHA-256), not
`CoreForecastRunModel.id`. GET and export resolve the request hash through the
repository and never re-run the forecast.

The existing `core_forecast.cli` policy loader is a fixture/CLI boundary and is
not a production authority. It cannot be called by Trial as a fallback.

## 5. Quality production authority

### 5.1 Existing persisted chain

The existing production evidence chain is:

```text
committed actual-harvest import
  -> point-in-time label visibility and cutoff authority
  -> S2HistoricalBacktestRequest
  -> run_s2_historical_binding / build_s2_binding_rows
  -> RollingBacktestRun
  -> RollingBacktestManifest
  -> RollingBacktestBindingRow
  -> S3EvaluationInput
  -> compute_daily_metrics / breakdown / baseline / comparison
  -> persist_quality_evaluation
  -> QualityEvaluationRunModel
  -> QualityMetricResultModel
  -> QualityBreakdownResultModel
  -> NaiveBaselineRunModel
  -> ModelBaselineComparisonModel
  -> QualityEvaluationManifestModel
```

S2 binding rows are persisted. `RollingBacktestBindingRow.canonical_payload`
contains the typed `S2HistoricalBindingRow`, including target date, forecast
quantile, horizon, forecast value, actual value, cutoff, row status, and
reason code. `RollingBacktestManifest` seals the request/instance/coverage,
exclusion, and authority hashes. `_load_s2_logical_run_with_integrity` reloads
and verifies the persisted rows before returning the logical run.

Quality persistence is also present at the current head. Migration `0024`
created the quality evidence tables and migration `0025_s3_model_baseline_comparison`
added the comparison policy/result closure and hash guards. The write path
`persist_quality_evaluation` is idempotent by evaluation request hash and
rejects missing or drifting child evidence during replay classification.

The missing operation is a public, complete readback by
`evaluation_instance_hash`. It must load the run, manifest, all metric and
breakdown rows, every baseline row, and every comparison row; verify all
canonical hashes and policy/schema versions; and reject any partial or drifted
evidence. The Trial async service must call the synchronous Quality persistence
readback through `AsyncSession.run_sync`.

The public `report_id` is exactly `evaluation_instance_hash`, a lowercase
64-character SHA-256. Internal `run_id` and `manifest_id` values never cross
the Trial response boundary.

### 5.2 Overlay and provenance

The backend, not the frontend, must project the persisted S2 binding rows into
the following typed shape:

```text
TrialQualityDailyOverlayRow:
  business_date: date
  forecast_p50: canonical decimal string or null
  forecast_p80: canonical decimal string or null
  forecast_p90: canonical decimal string or null
  actual_quantity: canonical decimal string or null
  actual_available: boolean
  exclusion_reason_codes: tuple[string, ...]
  coverage_state: AVAILABLE | EXCLUDED | NOT_COMPUTABLE
```

The projection groups the persisted rows by their exact business grain and
date, preserving quantile and horizon identities. It does not infer a daily
actual from aggregate metrics, and it does not perform a client-side join.
Missing or excluded actuals remain `null` with explicit reason codes.

The typed report must also expose:

- daily metrics with status, value-or-null, numerator/denominator, and reason codes;
- cumulative metrics;
- single-day peak status/value/date;
- sustained-seven-day peak status/value/window;
- separate 7-day, 14-day, and 21-day horizon objects;
- P80 coverage and P90 coverage objects;
- interval metrics with explicit lower-bound availability;
- excluded and not-computable counts;
- persisted model identity, baseline identity, policy versions, and evidence hashes.

`compute_daily_metrics`, baseline functions, and
`compute_model_baseline_comparisons` remain the only calculator authorities.
The Trial GET and export adapters only read and serialize persisted evidence.
No unavailable value is represented by numeric zero.

## 6. Public Trial API freeze

All public endpoints remain under `/api/v1/trial/*`.

| Method and endpoint | Request DTO | Response DTO | Success | Required errors |
| --- | --- | --- | --- | --- |
| `GET /api/v1/trial/forecast-input-authority` | none | `TrialForecastInputAuthorityResponse` | `200` | `404 TRIAL_RESOURCE_NOT_FOUND` for concealed scope; `503 TRIAL_AUTHORITY_UNAVAILABLE` |
| `POST /api/v1/trial/forecasts` | expanded `TrialForecastCreateRequest` | `TrialForecastSummaryResponse` | `200` | `422 TRIAL_REQUEST_INVALID`; `404 TRIAL_RESOURCE_NOT_FOUND`; `409 CONFLICTING_REPLAY`; `503 TRIAL_AUTHORITY_UNAVAILABLE` |
| `GET /api/v1/trial/forecasts/{run_id}` | path public request hash | typed `TrialForecastSummaryResponse` | `200` | `404 TRIAL_RESOURCE_NOT_FOUND`; `409 CONCURRENCY_CONFLICT`; `503 TRIAL_SERVICE_UNAVAILABLE` |
| `GET /api/v1/trial/forecasts/{run_id}/daily-curve` | path public request hash | typed `TrialForecastDailyCurveResponse` | `200` | same read errors; no recomputation |
| `GET /api/v1/trial/forecasts/{run_id}/export.csv` | path public request hash | canonical CSV bytes | `200` | same read errors; `text/csv` only |
| `POST /api/v1/trial/quality-reports` | `TrialQualityReportCreateRequest` | typed `TrialQualityReportResponse` | `200` | `422 TRIAL_REQUEST_INVALID`; `404 TRIAL_RESOURCE_NOT_FOUND`; `409 CONFLICTING_REPLAY`; `503 QUALITY_AUTHORITY_UNAVAILABLE` |
| `GET /api/v1/trial/quality-reports/{report_id}` | path evaluation instance hash | typed `TrialQualityReportResponse` | `200` | `404 TRIAL_RESOURCE_NOT_FOUND`; `409 EVIDENCE_CONFLICT`; `503 QUALITY_PERSISTENCE_UNAVAILABLE` |
| `GET /api/v1/trial/quality-reports/{report_id}/comparison` | path evaluation instance hash | typed `TrialQualityComparisonResponse` | `200` | `404 TRIAL_RESOURCE_NOT_FOUND`; `409 EVIDENCE_CONFLICT`; `503 QUALITY_PERSISTENCE_UNAVAILABLE` |
| `GET /api/v1/trial/quality-reports/{report_id}/export.csv` | path evaluation instance hash | canonical CSV bytes | `200` | same read errors; `text/csv` only |

The existing A1 actual-harvest endpoints remain the only upload and commit
surface. A2 must not call `/api/v1/actual-harvest/*`, internal planning routes,
internal master-data routes, or internal forecast-quality routes from a
frontend or Trial client.

## 7. Database and migration decision

```text
A2_SCHEMA_CHANGE_REQUIRED=true
CURRENT_ALEMBIC_HEAD=0025_s3_model_baseline_comparison
CURRENT_ALEMBIC_HEAD_COUNT=1
```

The existing schema is sufficient for Core run, daily curve, peak metrics, S2
binding, Quality evidence, baseline, comparison, and integrity manifests. It
is not sufficient for a production Trial authority lookup because no persisted
marketable-retention policy authority stores both retention rates with an
effective scope, source identity, policy version, availability timestamp, and
canonical row-set identity.

`FarmSeasonVarietyPlan.marketable_rate` and the parameter library are related
production inputs, but neither is the Core
`MarketableRetentionPolicySnapshot`: they do not provide the required paired
sorting/postharvest rates and policy identity for an authority-bound Core run.
The CLI fixture policy is not a production source.

The separate schema-authority sub-round must add, without changing any formula:

```text
core_forecast_marketable_policy
  public_policy_hash, policy_version, season_id, factory_id,
  source_system, source_record_key, available_at, effective_from,
  effective_to, status, row_set_hash, created_at

core_forecast_marketable_policy_entry
  policy_id, farm_id, subfarm_id, variety_id,
  sorting_retention_rate NUMERIC(24,6),
  postharvest_retention_rate NUMERIC(24,6),
  source_version, row_hash
```

Required constraints are lowercase SHA-256 checks, positive foreign keys,
rates in `[0,1]`, one unique entry per policy and business scope, one unique
policy hash, and indexes on policy/scope and policy/effective date. The
rollback is deterministic: drop policy entries, then policy headers and their
indexes/constraints; do not rewrite existing Core, S2, or Quality evidence.

The schema sub-round is a prerequisite to production Forecast create. It is
not authorized by accepting this document.

## 8. Exact future changed-path allowlist

The following paths are the complete future ceiling for the A2 authorization
program. A future implementation must still use separate commits for the
schema, Forecast, and Quality sub-rounds.

```text
CREATE_PATHS=
backend/alembic/versions/0026_s5_round_a2_marketable_policy_authority.py

MODIFY_PATHS=
backend/app/api/trial.py
backend/app/trial.py
backend/app/core_forecast/repository.py
backend/app/forecast_quality/persistence.py
backend/app/models/core_forecast.py
backend/app/rolling_backtest/persistence.py
backend/tests/trial/test_api.py
backend/tests/trial/test_contract.py
backend/tests/forecast_quality/test_idempotency.py
backend/tests/forecast_quality/test_persistence.py
backend/tests/integration/test_core_forecast_persistence_postgres.py
backend/tests/integration/test_rolling_backtest_historical_binding.py
backend/tests/integration/test_rolling_backtest_persistence.py
backend/tests/rolling_backtest/test_persistence_contracts.py

FORBIDDEN_PATHS=
docs/v0-2/s5-frontend-implementation-authorization.md
ci-shard-manifest.yml
.github/workflows/ci.yml
frontend/
pyproject.toml
uv.lock
backend/app/core_forecast/application.py
backend/app/core_forecast/service.py
backend/app/core_forecast/metrics.py
backend/app/forecast_quality/calculator_daily.py
backend/app/forecast_quality/comparison.py
backend/app/forecast_quality/aggregation.py
backend/app/forecast_quality/baseline.py
backend/app/agent/
backend/app/maturity/
backend/app/harvest_state/
backend/app/actual_harvest_import/
backend/app/models/ (except backend/app/models/core_forecast.py)
backend/alembic/ (except the exact 0026 file above)
backend/tests/ (except the exact test files above)

A2_CREATE_PATH_COUNT=1
A2_MODIFY_PATH_COUNT=14
A2_CHANGED_FILE_CEILING=15
A2_BACKEND_APP_FILE_CEILING=6
A2_TEST_FILE_CEILING=8
A2_WORKFLOW_FILE_CEILING=0
A2_MIGRATION_FILE_CEILING=1
```

The existing `ci-shard-manifest.yml` already owns `backend/tests/trial/`,
`backend/tests/core_forecast/`, `backend/tests/forecast_quality/`, and the
existing PostgreSQL integration files. No manifest or workflow change is
authorized by this document.

## 9. Delivery plan

```text
A2_DELIVERY_PLAN=
A2_S_SCHEMA_AUTHORITY_PERSISTENCE,
A2_F_FORECAST_AUTHORITY_AND_ADAPTERS,
A2_Q_QUALITY_ADAPTERS_OVERLAY_AND_METRICS
```

The order is strict:

1. `A2_S_SCHEMA_AUTHORITY_PERSISTENCE` adds and verifies the retention-policy
   authority table and migration. It is independently reviewable, testable,
   and revertible.
2. `A2_F_FORECAST_AUTHORITY_AND_ADAPTERS` resolves business-key authority,
   consumes the persisted policy, wires Core execution, and exposes typed
   create/read/daily/export behavior. It must not change Core algorithms.
3. `A2_Q_QUALITY_ADAPTERS_OVERLAY_AND_METRICS` adds complete Quality readback,
   creates reports from committed import and S2 evidence, projects overlay and
   typed metrics, and exposes persisted comparison/export behavior.

Each sub-round requires its own commit, targeted tests, PostgreSQL tests, and
rollback review. A failed Quality sub-round must not require reverting the
schema authority or Forecast adapter. No sub-round authorizes Round B.

## 10. Test and acceptance gates

### 10.1 Forecast gates

- business-key authority lookup returns no internal IDs;
- duplicate, missing, inactive, and cross-scope authority values fail closed;
- retention policy is selected by explicit effective/availability policy, not
  by an implicit latest-row query;
- Core Task 8 and Task 9 completed runs are selected by frozen authority
  references;
- code, model, parameter, and policy identities are persisted in the public
  result provenance;
- `planting_area_mu` accepts only canonical decimal strings greater than zero;
- optional date, stage, and already-picked inputs are consumed or rejected by a
  typed blocker, never ignored;
- exact replay returns the same public request hash;
- conflicting replay returns `409 CONFLICTING_REPLAY`;
- GET does not execute Forecast again;
- internal integer IDs never appear in any Trial response;
- Decimal, `date`, and timezone-aware timestamp behavior is tested explicitly;
- daily curve, peaks, cumulative quantity, inventory, backlog, and blockers are
  projections of persisted Core evidence.

### 10.2 Quality gates

- a committed import is the only actual-label source;
- point-in-time forecast and label cutoffs are checked independently;
- S2 manifest and binding row hashes are verified before Quality calculation;
- persisted report readback rejects missing manifest, partial child sets,
  policy/version drift, and every hash mismatch;
- `AsyncSession.run_sync` is used for synchronous Quality persistence access;
- `report_id` equals the verified evaluation instance hash;
- create projection equals subsequent GET projection;
- overlay rows preserve forecast quantile, actual availability, status, and
  reason codes;
- 7/14/21 horizon metrics, peak metrics, coverage, and interval values are
  typed and null when not computable;
- baseline comparison is read from persisted comparison evidence, not recomputed
  by GET or export;
- CSV export uses the same verified readback object as JSON GET;
- actor scope and concealed 404 behavior apply to report create/read,
  comparison, and export;
- no client-side equivalent of metric, peak, join, or comparison computation
  is permitted.

### 10.3 Commands

The implementation review must run the targeted suites and static gates:

```text
uv run pytest -q backend/tests/trial
uv run pytest -q backend/tests/core_forecast
uv run pytest -q backend/tests/forecast_quality
uv run pytest -q backend/tests/rolling_backtest
uv run pytest -q backend/tests/integration/test_core_forecast_persistence_postgres.py
uv run pytest -q backend/tests/integration/test_rolling_backtest_historical_binding.py
uv run pytest -q backend/tests/integration/test_rolling_backtest_persistence.py
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/app
uv run alembic -c backend/alembic.ini heads
git diff --check
```

PostgreSQL 16 is required for the full suite and migration round-trip. The
Alembic check must return exactly one head. The current audit head is
`0025_s3_model_baseline_comparison`; after the separately authorized schema
sub-round the expected single head is the exact `0026` migration listed above.
No local environment without PostgreSQL may be reported as a passing database
acceptance result.

## 11. Round B stop condition

```text
S5_ROUND_B_AUTHORIZED=false
```

Round B requires a separate authorization after all of the following are true:

- A2 schema, Forecast, and Quality commits are merged;
- A2 post-merge PostgreSQL 16 full suite passes;
- Forecast production input authority and create/read/daily/export paths are
  ready;
- Quality production create/read/comparison/export paths are ready;
- daily forecast/actual overlay is ready;
- 7/14/21, peak, coverage, interval, and comparison semantics are frozen and
  tested;
- no backend blocker remains;
- no adapter uses a fixture, in-memory production store, client-side join, or
  client-side recomputation.

## 12. Governance stop block

```text
S5_ROUND_A1_COMPLETE=true

S5_ROUND_A2_AUTHORIZATION_DRAFTED=true
S5_ROUND_A2_AUTHORIZATION_ACCEPTED=false
S5_ROUND_A2_IMPLEMENTATION_AUTHORIZED=false

BACKEND_CODE_AUTHORIZED=false
FRONTEND_CODE_AUTHORIZED=false
DEPENDENCY_INSTALL_AUTHORIZED=false
MODEL_CHANGE_AUTHORIZED=false
MIGRATION_CHANGE_AUTHORIZED=false
WORKFLOW_CHANGE_AUTHORIZED=false

COMMIT_AUTHORIZED_FOR_DOCUMENT_ONLY=true
PUSH_AUTHORIZED_FOR_DOCUMENT_ONLY=true
DRAFT_PR_AUTHORIZED_FOR_DOCUMENT_ONLY=true

READY_AUTHORIZED=false
MERGE_AUTHORIZED=false

S5_ROUND_B_AUTHORIZED=false
S5_ROUND_C_AUTHORIZED=false
V0_2_RELEASE_AUTHORIZED=false

NO_STEP_IMPLIES_THE_NEXT=true
MANDATORY_STOP=true
```
