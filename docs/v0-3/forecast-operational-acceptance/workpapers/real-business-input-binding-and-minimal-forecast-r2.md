# Workpaper — existing data binding and minimal Forecast path recovery R2

## Control boundary

This workpaper continues Draft PR #606 at base
d704cc9338efda2e7aa80499b53622ae42f83fd6 and previous head
4dba5a0f9fdfe45c48df0c35bff8834d6d17cef7. It is an evidence and binding
audit. It does not reopen S4, run a candidate, score VALIDATION, access TEST,
or create a database.

The old R1 phrase REAL_BUSINESS_INPUT_NOT_PROVIDED is superseded as a current
interpretation. The retained R1 observation is limited to what that runtime
could locate:

R1_SOURCE_ABSENCE_INTERPRETATION_SUPERSEDED=true
USER_DATA_ABSENCE_CLAIM_ISSUED=false

## Asset inventory

The current checkout has two row-bearing historical receipt workbooks:

| Path | Bytes | SHA-256 | Role |
| --- | ---: | --- | --- |
| data/raw/2024_2025_receipts.xls | 27,880,960 | a55cbf259f52e6a20e30d646b43d2aa0f104f60786d725dbc051e46c76b390d5 | Historical receipt facts |
| data/raw/2025_2026_receipts.xls | 33,155,072 | 66c4de6ddab4d8e3962eaaba0aab1b6ddcefff9f2605b36c950af3848e2a9c0b | Historical receipt facts |

The five previously supplied CSV asset names are not mounted as row-bearing
files in this Codex runtime. The repository copies under data/templates are
header-only schemas; parameter_observations.csv is also header-only. The
result is:

PREVIOUSLY_PROVIDED_ASSET_STATUS=MIXED
ROW_BEARING_EXISTING_ASSETS=REPOSITORY_HISTORICAL_RECEIPT_XLS_ONLY
SCHEMA_ONLY_EXISTING_ASSETS=data/templates/farm_location_master.csv,data/templates/season_variety_planting.csv,data/templates/phenology_history.csv,data/templates/weather_history.csv,data/templates/labor_history.csv,data/templates/parameter_observations.csv

Historical receipts are not a current location/variety/area scope. They were
not promoted to current business authority, and no raw row was copied to Git
evidence.

## Minimal input gate

docs/07_minimal_input_parameter_inference.md,
backend/app/schemas/planning.py, and backend/app/planning/service.py agree on
the minimal contract:

location = address OR latitude+longitude OR location_reference_id
variety = variety_id OR variety_code OR variety_name
planted_area_mu > 0

The server owns yield, marketable-rate, maturity, and realization inference;
the user does not supply those values in minimal mode. But no current
location/variety/area scope exists, so sending a guessed request would be an
invented business input.

FIRST_BROKEN_STAGE=MINIMAL_INPUT_SCOPE_ROW_BINDING
MISSING_EXTERNAL_BUSINESS_FACTS=CURRENT_SCOPE_LOCATION,CURRENT_SCOPE_VARIETY_LOOKUP,CURRENT_SCOPE_PLANTED_AREA_MU
NEXT_REQUIRED_ACTION=LOAD_ONE_CURRENT_MINIMAL_SCOPE_ROW_WITH_LOCATION_VARIETY_PLANTED_AREA_MU
MINIMAL_PLANNING_EXECUTED=false

## Parameter authority audit

The repository contains a CSV importer for already prepared parameter
observations:

backend.app.planning.importers.import_parameter_library_csv
scripts/import_parameter_library.py

It does not contain a builder from FactReceiptRaw historical receipts to the
seven versioned Task 5 parameter types. The current acceptance database also
has zero parameter_library_version and parameter_observation rows.

PARAMETER_LIBRARY_IMPORT_PATH_EXISTS=true
HISTORICAL_TO_PARAMETER_OBSERVATION_PATH_EXISTS=false
PARAMETER_LIBRARY_READY=false
SYNTHETIC_PARAMETER_LIBRARY_USED=false
TEMPLATE_PARAMETER_OBSERVATION_USED_AS_REAL=false

This is an internal materialization gap, not a reason to ask the user for
weather, Task8, Task9, or numeric defaults. A builder would need an explicit
parameter-semantics authority.

## Downstream binding evidence

The production-plan importer is present, but
backend.app.planning.plan_service._prepare_plan_inputs requires explicit
expected_yield_kg_per_mu and marketable_rate. The minimal Task 5 API does not
automatically materialize a FarmSeasonVarietyPlan.

The core forecast repository has a marketable-policy read path, but no
operational production writer was identified. The Trial resolver requires a
persisted plan, active policy and entries, master-data relationships, completed
Task8, completed Task9, and an active factory before normal core execution.
The current acceptance database has zero rows in those authority tables. Task8
and Task9 are system outputs, not user-provided input fields.

The implemented normal chain remains:

minimal scope
 -> Task 5 inference
 -> production-plan authority
 -> marketable policy
 -> Task8
 -> Task9
 -> Trial input authority
 -> Core Forecast
 -> natural forecast-authority capture

## Runtime observation

The inspected runtime is PostgreSQL 16.15 on port 55437, at Alembic head
0032_s4_validation_budget_durable_persistence. It is a non-production
acceptance runtime, not the default local database and not a production source.
Its relevant counts were all zero for master data, plans, parameter library,
marketable policy, and forecast-authority capture. This proves only that the
current acceptance runtime is empty; it does not prove global absence of the
user's data.

No database was created, written, seeded, backfilled, or used for Forecast.

## Final disposition

RESULT=EXACT_EXTERNAL_FACT_GAP_AND_PUSHED
INTERNAL_SOFTWARE_BLOCKER=PARAMETER_LIBRARY_MATERIALIZATION_PATH_MISSING
CURRENT_REAL_FORECAST_CAPABILITY=BLOCKED_EXACT_EXTERNAL_FACT
V0_3_CLOSEOUT_FORECAST_CAPABILITY_GATE=FAIL
REAL_NORMAL_FORECAST_EXECUTED=false
FORECAST_AUTHORITY_CAPTURED=false
CURRENT_V0_3_S4_COMPLETE=true
CURRENT_S4_EXECUTION_STATUS=CLOSED_NO_ADMISSIBLE_REPLACEMENT_SELECTED
S4_REOPEN_AUTHORIZED=false
BUDGET_STATE_CLASS=LAST_ACCEPTED_DURABLE_BUDGET_SNAPSHOT
LAST_ACCEPTED_EFFECTIVE_CONSUMED=8
LAST_ACCEPTED_REMAINING=24
BUDGET_DELTA=0
TEST_ACCESS_REQUESTED=false
TEST_BYTES_READ=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_EXISTING_DATA_BINDING_R2_REVIEW
