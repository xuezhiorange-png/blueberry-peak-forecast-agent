# V0.3 pilot runtime and first prospective capture

TASK_ID=V0_3_CRITICAL_PATH_PILOT_RUNTIME_AND_FIRST_REAL_PROSPECTIVE_CAPTURE_R1
TASK_CLASS=CRITICAL_PATH_PILOT_RUNTIME_AND_FIRST_REAL_PROSPECTIVE_CAPTURE
BASE_MAIN_SHA=70af4d7dc0ba84947d439206b59425e4505d3d8c
PR594_MERGE_IN_BASE=true

## Terminal outcome

The first persistent V0.3 business-pilot runtime was established outside the
repository and is not a test, CI, task-isolated, or historical-recovery
database. The runtime is ready for a real normal Forecast, but no current
forward-looking business input authority is present in that runtime.

Therefore the task stops at the explicitly allowed second outcome:

    PILOT_RUNTIME_READY_FOR_REAL_FORECAST=true
    REAL_PROSPECTIVE_CAPTURE_PERFORMED=false
    REAL_PROSPECTIVE_CAPTURE_STATUS=BLOCKED_REAL_FORWARD_LOOKING_BUSINESS_INPUT_NOT_AVAILABLE
    PROSPECTIVE_CLOCK_STARTED=false

No Forecast request was fabricated or replayed. No forecast-authority row was
seeded, backfilled, reconstructed, or manually inserted.

## Runtime binding

The pilot runtime is a native PostgreSQL 16.15 instance with a persistent
data directory outside the repository:

    PILOT_RUNTIME_ESTABLISHED=true
    PILOT_RUNTIME_PERSISTENT=true
    PILOT_RUNTIME_TEST_ENVIRONMENT=false
    TASK_ISOLATED_DATABASE_IS_PRODUCTION=false
    PILOT_RUNTIME_IS_HISTORICAL_AUTHORITY_REPLACEMENT=false
    HISTORICAL_AUTHORITY_RECOVERY_PERFORMED=false
    FORECAST_AUTHORITY_SEED_PERFORMED=false
    FORECAST_AUTHORITY_BACKFILL_PERFORMED=false

Sanitized binding:

    HOST=127.0.0.1
    PORT=55436
    DATABASE=blueberry_peak_v03_pilot
    APPLICATION_USER=blueberry_pilot_app
    ALEMBIC_HEAD_COUNT=1
    ALEMBIC_HEAD=0032_s4_validation_budget_durable_persistence
    DATABASE_AT_CURRENT_HEAD=true
    SECRET_EXTERNALIZED=true
    SECRET_COMMITTED=false
    RUNTIME_BINDING_FINGERPRINT=33afc063ac161c792016abb8c3f10db7ee4b19476ffb745cec6526b05cb7b87b

The password is held outside Git in the local credential store and is not
included in this evidence or in the repository.

Readiness evidence:

    /health/live=HTTP_200
    /health/ready=HTTP_200
    FORECAST_AUTHORITY_CAPTURE_TABLES_PRESENT=true
    FORECAST_AUTHORITY_DAILY_TABLE_PRESENT=true
    FORECAST_AUTHORITY_TASK10_EXTENSION_TABLE_PRESENT=true
    S4_BUDGET_TABLES_PRESENT=true

The normal Trial Forecast route is bound to the application and reaches the
database-backed forecast-input authority boundary. The empty pilot database
returned RESOURCE_NOT_FOUND for the input-authority probe; this is evidence
that the runtime has no currently bound business input, not permission to
seed one.

## Normal Forecast and retention boundary

The audited normal path is:

    POST /api/v1/trial/forecasts
      -> DefaultTrialApplicationService.create_forecast
      -> execute_core_forecast_run
      -> capture_production_forecast_base_authority
      -> forecast_authority_capture / forecast_authority_daily
      -> fresh-session load_pit_visible_forecast_authority

The implementation already freezes the base authority at Forecast completion,
before any later Task10 extension. This task did not call the retention
function directly and did not bypass the normal application path.

Because no real business input was available, no POST Forecast was issued:

    REAL_BUSINESS_INPUT=true                         NOT_REACHED
    FORWARD_LOOKING=true                             NOT_REACHED
    OUTCOME_UNKNOWN_AT_FORECAST_CUTOFF=true          NOT_REACHED
    NORMAL_FORECAST_PATH_EXECUTED=false
    REAL_NORMAL_PRODUCTION_FORECAST_EXECUTED=false
    REAL_PROSPECTIVE_FORECAST_AUTHORITY_CAPTURED=false
    FORECAST_AUTHORITY_CAPTURE_ROWS=0
    FORECAST_AUTHORITY_DAILY_ROWS=0
    PIT_READBACK=NOT_APPLICABLE_NO_CAPTURE

## Prospective handoff

The prospective horizons remain fixed at 7, 14, and 21 days. No maturation
manifest was created because a capture identity does not exist yet, and no
actual label values were prefilled:

    REQUIRED_HORIZONS=7,14,21
    MATURATION_MANIFEST_CREATED=false
    ACTUAL_LABELS_PREPOPULATED=false
    PROSPECTIVE_SCAN_PERFORMED=false

After a real normal Forecast is captured by this runtime, the existing
retention path must provide the capture identity and cutoff. Only then may a
future handoff record the three target windows with
ACTUAL_LABEL_REQUIRED=true and ACTUAL_LABEL_CURRENTLY_AVAILABLE=false.
Later actuals must arrive through the existing actual-harvest import,
validation, immutable snapshot, and AS_OF_EVALUATION path.

## Unchanged governance boundaries

    CURRENT_V0_3_S4_COMPLETE=false
    CURRENT_S4_EXECUTION_STATUS=WAITING_FOR_REAL_PROSPECTIVE_FORECAST_AUTHORITY
    CURRENT_S4_BLOCKER=REAL_PROSPECTIVE_FORECAST_AUTHORITY_NOT_YET_AVAILABLE
    PROSPECTIVE_SCAN_PERFORMED=false
    CANDIDATE_EXECUTION_PERFORMED=false
    VALIDATION_SCORING_PERFORMED=false
    EFFECTIVE_CONSUMED=4
    REMAINING=28
    BUDGET_DELTA=0
    TEST_REMAINS_SEALED=true
    V0_3_S5_AUTHORIZED=false
    S5_IMPLEMENTATION_STARTED=false
    S5_A_IMPLEMENTATION_AUTHORIZED=false
    PRODUCTION_RELEASE_IN_V0_3_SCOPE=false
    CURRENT_PRODUCTION_RELEASE_APPROVED=false

The next operational trigger is external and concrete:

    A_REAL_NORMAL_PRODUCTION_FORECAST_HAS_BEEN_CAPTURED_BY_THE_EXISTING_FORECAST_AUTHORITY_RETENTION_PATH

No historical authority recovery, replacement production store, seed,
backfill, candidate execution, S4 scoring, S4 plan mutation, or TEST access
is implied by this runtime establishment.

FINAL_STOP_GATE=COORDINATOR_V0_3_FIRST_REAL_PROSPECTIVE_CAPTURE_REVIEW
