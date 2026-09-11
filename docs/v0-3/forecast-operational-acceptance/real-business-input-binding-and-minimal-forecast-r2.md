# V0.3 existing data binding and minimal Forecast path recovery R2

TASK_ID=V0_3_EXISTING_DATA_BINDING_AND_MINIMAL_FORECAST_PATH_RECOVERY_R2
TASK_CLASS=EXISTING_DATA_ASSET_RECONCILIATION_AND_OPERATIONAL_FORECAST_PATH_RECOVERY
PR_NUMBER=606
BASE_MAIN_SHA=d704cc9338efda2e7aa80499b53622ae42f83fd6
PREVIOUS_HEAD_SHA=4dba5a0f9fdfe45c48df0c35bff8834d6d17cef7
RESULT=EXACT_EXTERNAL_FACT_GAP_AND_PUSHED

## Current conclusion

R1 collapsed several different observations into a source-absence conclusion.
R2 separates them:

1. The repository contains two row-bearing historical receipt workbooks.
2. The previously supplied CSV asset names are not mounted as row-bearing files
   in the current Codex runtime. The same-named repository files are
   header-only templates.
3. The current acceptance runtime is operational, but its business and
   parameter-authority tables are empty.
4. No current minimal Forecast scope row is available. The minimum row needs a
   location, a variety lookup, and planted_area_mu.

This is not a claim that the user never supplied data, and it is not a claim
that business data is globally absent.

R1_SOURCE_ABSENCE_INTERPRETATION_SUPERSEDED=true
USER_DATA_ABSENCE_CLAIM_ISSUED=false
REPOSITORY_HISTORICAL_RECEIPT_DATA_PRESENT=true
PREVIOUSLY_PROVIDED_ASSET_STATUS=MIXED
PREVIOUSLY_PROVIDED_ASSET_RUNTIME_STATUS=NOT_MOUNTED_IN_CODEX_RUNTIME
PREVIOUSLY_PROVIDED_ASSET_CONTENT_STATUS=FOUND_SCHEMA_ONLY
CURRENT_ACCEPTANCE_RUNTIME_BUSINESS_INPUT_DATA_MISSING=true
FIRST_BROKEN_STAGE=MINIMAL_INPUT_SCOPE_ROW_BINDING
MISSING_EXTERNAL_BUSINESS_FACTS=CURRENT_SCOPE_LOCATION,CURRENT_SCOPE_VARIETY_LOOKUP,CURRENT_SCOPE_PLANTED_AREA_MU
CURRENT_REAL_FORECAST_CAPABILITY=BLOCKED_EXACT_EXTERNAL_FACT
V0_3_CLOSEOUT_FORECAST_CAPABILITY_GATE=FAIL
NEXT_REQUIRED_ACTION=LOAD_ONE_CURRENT_MINIMAL_SCOPE_ROW_WITH_LOCATION_VARIETY_PLANTED_AREA_MU

## Asset and source reconciliation

| Asset class | Current finding | Permitted interpretation | Used as current Forecast input |
| --- | --- | --- | --- |
| data/raw/2024_2025_receipts.xls | Present, 27,880,960 bytes, SHA-256 a55cbf259f52e6a20e30d646b43d2aa0f104f60786d725dbc051e46c76b390d5 | Row-bearing historical receipt fact source | No |
| data/raw/2025_2026_receipts.xls | Present, 33,155,072 bytes, SHA-256 66c4de6ddab4d8e3962eaaba0aab1b6ddcefff9f2605b36c950af3848e2a9c0b | Row-bearing historical receipt fact source | No |
| Previously supplied location/planting/phenology/weather/labor CSVs | Not mounted as row-bearing files in this runtime | Previously provided asset identity is retained; current runtime cannot consume rows | No |
| Same-named data/templates CSVs | Header-only schemas with no business rows | Template/schema only | No |
| data/templates/parameter_observations.csv | Header-only parameter-observation schema | Never real parameter evidence | No |

The raw workbooks remain historical receipts. They may participate in a
separately governed historical-fact-to-parameter construction flow, but they do
not by themselves establish current location, current planted area, active
production-plan authority, or an active marketable policy. No raw rows were
copied into evidence and no raw file was changed.

## Minimal input contract and audited path

The current Task 5 contract is reusable:

MINIMAL_INPUT_CONTRACT_VERIFIED=true
MINIMAL_INPUT_REQUIRES_LOCATION=true
MINIMAL_INPUT_REQUIRES_VARIETY_AREA=true
MINIMAL_INPUT_REQUIRES_YIELD_FROM_USER=false
MINIMAL_INPUT_REQUIRES_MARKETABLE_RATE_FROM_USER=false
MINIMAL_INPUT_REQUIRES_TASK8_FROM_USER=false
MINIMAL_INPUT_REQUIRES_TASK9_FROM_USER=false

The canonical API is POST /planning/tasks, implemented by
backend.app.planning.service.create_minimal_planning_task. Its server-owned
flow is:

location (address OR latitude+longitude OR location_reference_id)
  plus variety lookup plus planted_area_mu
  -> location resolution
  -> active/retired ParameterLibraryVersion selection
  -> visible ParameterObservation lookup
  -> configured Task 5 inference
  -> persisted planning task/result

There is no safe payload to send in this task because no row-bearing current
scope exists. MINIMAL_PLANNING_EXECUTED=false is fail-closed behavior, not a
decision to use historical receipts as a current scope.

## Historical data and parameter-library audit

The historical importer exists at
backend.app.etl.history.importer.import_source and writes historical receipt
facts. The parameter-library importer exists at
backend.app.planning.importers.import_parameter_library_csv, with the wrapper
scripts/import_parameter_library.py. The audit found no repository-owned
builder that converts historical receipt facts into the versioned
ParameterObservation rows required by Task 5.

PARAMETER_LIBRARY_IMPORT_PATH_EXISTS=true
HISTORICAL_TO_PARAMETER_OBSERVATION_PATH_EXISTS=false
PARAMETER_LIBRARY_READY=false
PARAMETER_LIBRARY_SOURCE=NONE_IN_CURRENT_ACCEPTANCE_RUNTIME
SYNTHETIC_PARAMETER_LIBRARY_USED=false
TEMPLATE_PARAMETER_OBSERVATION_USED_AS_REAL=false

This is an internal data-binding/materialization gap after the minimal scope
gate. It is not a reason to ask for weather, Task8, Task9, or fabricated
parameter values. Creating a historical-to-observation algorithm requires an
additional authority decision for parameter semantics and is not a safe
connection-only repair.

The repository source manifest also names legacy workbook paths that do not
match the current raw filenames. This is recorded as a historical-ingestion
binding finding only; changing that manifest would not create a current
minimal scope or a parameter library and was not included in R2.

## Downstream normal Forecast path

The normal path is implemented but cannot be reached with the current runtime
state:

POST /planning/tasks
  -> inferred parameter results
  -> FarmSeasonVarietyPlan / production-plan authority
  -> active marketable policy and scoped entries
  -> completed Task8 maturity authority
  -> completed Task9 harvest-state authority
  -> Trial input-authority resolver
  -> POST /api/v1/trial/forecasts
  -> execute_core_forecast_run
  -> capture_production_forecast_base_authority
  -> forecast_authority_capture + forecast_authority_daily

| Stage | Code capability | Current acceptance state | Disposition |
| --- | --- | --- | --- |
| Minimal input validation/inference | backend.app.planning.service.create_minimal_planning_task | No current scope row; no parameter library rows | Not executed; blocked at scope binding |
| Parameter library | ParameterLibraryVersion / ParameterObservation and CSV importer | 0 rows in current acceptance database; no historical-to-observation builder | Internal materialization gap |
| Production plan | backend.app.planning.plan_importer.import_production_plans_csv and production-plan API | Requires explicit plan fields and persisted master data | Not loaded |
| Marketable policy | Read path in backend.app.core_forecast.repository | Schema/read path exists; no operational writer identified; no policy rows | Not available |
| Task8 | Maturity authority path exists | No materialized run | System output not materialized |
| Task9 | Harvest-state authority path exists | No materialized run | System output not materialized |
| Trial/Core Forecast | Normal API, core persistence, and natural capture exist | Input authority resolver has no items | Not executed |

Task8 and Task9 are system outputs. They are not user-upload fields and must
not be represented as missing user data.

## Acceptance runtime observation

The current-main acceptance runtime is a non-production runtime at PostgreSQL
port 55437, PostgreSQL 16.15, and Alembic head
0032_s4_validation_budget_durable_persistence. A read-only inspection found
zero rows in dim_farm, dim_variety, farm_season_variety_plan,
parameter_library_version, parameter_observation,
core_forecast_marketable_policy, and forecast_authority_capture.

CURRENT_ACCEPTANCE_RUNTIME_BOUND=true
CURRENT_ACCEPTANCE_RUNTIME_OPERATIONAL=true
TASK_ISOLATED_DATABASE_IS_PRODUCTION=false
ACCEPTANCE_RUNTIME_IS_PRODUCTION=false
CURRENT_ACCEPTANCE_RUNTIME_BUSINESS_INPUT_DATA_MISSING=true
FORECAST_INPUT_AUTHORITY_AVAILABLE=false
FORECAST_INPUT_AUTHORITY_ITEM_COUNT=0
DATABASE_WRITE=false
FORECAST_EXECUTION=false

An empty acceptance database proves only that this runtime has not been loaded;
it is not evidence that the user's data does not exist elsewhere. No database
was created, seeded, backfilled, or promoted.

## Why no code change is safe in R2

The evidence supports a precise next action but not a legitimate code rewrite:

- without a current scope row, the API cannot be called lawfully;
- without a versioned parameter source, Task 5 must return unavailable rather
  than use defaults;
- the historical receipts do not define the semantics of all seven inferred
  parameters and cannot be turned into current authority by guess;
- the production-plan API requires explicit values and does not automatically
  materialize a plan from Task 5 results;
- the marketable-policy read path has no identified production writer.

Accordingly R2 makes no production-code, schema, migration, model, or
parameter change. Once one current minimal scope row is loaded through an
authorized source, the next execution must first resolve whether the
parameter-library materialization gap has an approved source path; it must not
silently skip that gate.

## Protected state and non-execution proof

CURRENT_V0_3_S4_COMPLETE=true
CURRENT_S4_EXECUTION_STATUS=CLOSED_NO_ADMISSIBLE_REPLACEMENT_SELECTED
CURRENT_S4_BLOCKER=NONE_CURRENT_PLAN_TERMINAL
S4_REOPEN_AUTHORIZED=false
S4_CANDIDATE_EXECUTION_PERFORMED=false
VALIDATION_SCORING_PERFORMED=false
PROSPECTIVE_SCAN_PERFORMED=false
BUDGET_STATE_CLASS=LAST_ACCEPTED_DURABLE_BUDGET_SNAPSHOT
LAST_ACCEPTED_CANONICAL_STARTED_COUNT=4
LAST_ACCEPTED_EFFECTIVE_CONSUMED=8
LAST_ACCEPTED_REMAINING=24
REMAINING_VALIDATION_BUDGET_UNUSED=24
BUDGET_DELTA=0
TEST_ACCESS_REQUESTED=false
TEST_BYTES_READ=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
V0_3_S5_AUTHORIZED=false
S5_IMPLEMENTATION_STARTED=false
PRODUCTION_RELEASE_APPROVED=false
REAL_NORMAL_FORECAST_EXECUTED=false
FORECAST_RESULT_PERSISTED=false
FORECAST_AUTHORITY_CAPTURED=false

The next action is one bounded data-loading action, not a request for a broad
business package:

NEXT_REQUIRED_ACTION=LOAD_ONE_CURRENT_MINIMAL_SCOPE_ROW_WITH_LOCATION_VARIETY_PLANTED_AREA_MU

That row must enter through an authorized source path. No weather, Task8,
Task9, historical actual outcome, template row, or synthetic default is an
acceptable substitute.

## Stop gate

RESULT=EXACT_EXTERNAL_FACT_GAP_AND_PUSHED
REAL_BUSINESS_INPUT_WAS_CREATED=false
FORECAST_REQUEST_SENT=false
FORECAST_AUTHORITY_ROWS_CREATED=0
ACCURACY_VALIDATION_PERFORMED=false
MODEL_QUALITY_CLAIM_ISSUED=false
MODEL_APPROVED_FOR_PILOT=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_EXISTING_DATA_BINDING_R2_REVIEW
