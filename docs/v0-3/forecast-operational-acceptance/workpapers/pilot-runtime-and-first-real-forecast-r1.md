# Workpaper: current real Forecast operational acceptance R1

TASK_ID=V0_3_CURRENT_REAL_FORECAST_OPERATIONAL_ACCEPTANCE_R1  
REPOSITORY=xuezhiorange-png/blueberry-peak-forecast-agent  
BASE_MAIN_SHA=8de8b54c1dd0476aac903e80a45a6cd1d997c78a

## Guarded procedure

1. Freshly cloned the repository from the canonical GitHub remote, fetched
   `origin/main`, and confirmed the exact expected base commit. The checkout
   was clean and a task branch was created from that commit.
2. Audited the current-main normal Forecast route, the input-authority
   resolver, core execution, authority capture, PIT reader, API response
   projection, health endpoints, and the two browser pages.
3. Performed read-only host probes. A persistent PostgreSQL process exists on
   port 55436, but no current-main application process is bound to it. The
   running application on port 8000 is the old V0.2 public-trial process; it
   is not current main, its readiness check is HTTP 503, and its database
   binding is the old demo runtime on port 55432.
4. Did not create or reconnect a database, alter credentials, start a new
   runtime, seed rows, backfill rows, or create a business-input authority.
5. Did not issue `POST /api/v1/trial/forecasts`. No valid current business
   input authority was available, and repository historical data/fixtures
   cannot be substituted for a forward-looking business request.
6. Did not call retention directly, invoke a candidate or validation scorer,
   open TEST, or create a validation ledger event.

## Input-authority finding

The normal service requires a persisted join across:

```text
FarmSeasonVarietyPlan
Farm
Season
Variety
Subfarm
Factory
CoreForecastMarketablePolicyEntryModel
CoreForecastMarketablePolicyModel (ACTIVE)
```

This is visible in `backend/app/trial.py` in
`_load_forecast_authority_snapshot`. The service returns an unavailable
authority result when the join produces no rows and the create path resolves
the submitted scope against that snapshot. Therefore a JSON payload assembled
from a fixture, old workbook, or guessed plan row would not be a lawful
current business input.

## Runtime and evidence classification

The old pilot-runtime document in
`docs/v0-3/pilot-runtime/evidence/pilot-runtime-and-first-prospective-capture-r1.json`
is retained as historical provenance only. It is not used to assert that the
current checkout has a ready runtime. The current observation is:

```text
ACCEPTANCE_RUNTIME_IS_PRODUCTION=false
CURRENT_MAIN_APP_RUNTIME_BOUND=false
PERSISTENT_POSTGRES_PROCESS_PRESENT=true
PERSISTENT_POSTGRES_IS_PRODUCTION=false
RUNTIME_AVAILABLE=false
DATABASE_AT_CURRENT_HEAD=NOT_VERIFIED
```

The local development compose profile uses port 5432 and a credential
placeholder. The test compose profile uses PostgreSQL 15 on port 55432 and is
explicitly TEST-only. Neither can establish production/current business
authority.

## Code capability versus operational acceptance

The code supports the desired business output contract: immutable forecast
completion, forecast-authority capture, PIT readback, daily P50/P80/P90,
single-day and seven-day peaks, cumulative quantity, mature inventory/backlog,
and CSV export. The Forecast page reads the persisted summary and daily curve;
the Quality page reads persisted forecast/actual evidence and comparisons.

Those are reusable implementation capabilities. The missing proof is the
external runtime/input binding and one completed real normal Forecast. No
accuracy or business-quality conclusion is made.

## Protected state

```text
CURRENT_V0_3_S4_COMPLETE=false
CURRENT_S4_EXECUTION_STATUS=CLOSED_NO_ADMISSIBLE_REPLACEMENT_SELECTED
CURRENT_S4_BLOCKER=NONE_CURRENT_PLAN_TERMINAL
S4_CANDIDATE_EXECUTION_PERFORMED=false
VALIDATION_SCORING_PERFORMED=false
PROSPECTIVE_SCAN_PERFORMED=false
LEGACY_RECONCILED_VALIDATION_DEBIT=4
LAST_ACCEPTED_CANONICAL_STARTED_COUNT=4
LAST_ACCEPTED_EFFECTIVE_CONSUMED=8
LAST_ACCEPTED_REMAINING=24
BUDGET_DELTA=0
TEST_ACCESS_REQUESTED=false
TEST_BYTES_READ=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
```

No current acceptance runtime rows or forecast-authority rows were created by
this task. The final status is:

```text
RESULT=BLOCKED
BLOCKER=CURRENT_BUSINESS_FORECAST_INPUT_AUTHORITY_UNAVAILABLE
REAL_NORMAL_PRODUCTION_FORECAST_EXECUTED=false
REAL_PROSPECTIVE_FORECAST_AUTHORITY_CAPTURED=false
PROSPECTIVE_CLOCK_STARTED=false
```

FINAL_STOP_GATE=COORDINATOR_CURRENT_REAL_FORECAST_OPERATIONAL_ACCEPTANCE_REVIEW

## R2 continuation: current-main runtime and input probe

R2 corrected the stale S4 top-level conclusion without reopening S4. The
current terminal state is `CURRENT_V0_3_S4_COMPLETE=true` with
`CURRENT_S4_EXECUTION_STATUS=CLOSED_NO_ADMISSIBLE_REPLACEMENT_SELECTED` and
`CURRENT_S4_BLOCKER=NONE_CURRENT_PLAN_TERMINAL`.

The previously observed 55436 PostgreSQL process was not safely identifiable:
it required SCRAM authentication and no authorized credentials were available.
It was not reconnected to or changed. A separate current-main acceptance
runtime was started on PostgreSQL 16.15 port 55437, upgraded to
`0032_s4_validation_budget_durable_persistence`, and bound to the current-main
application on port 18005. `/health/live` and `/health/ready` both returned
HTTP 200. The database was empty by construction and is not production, TEST,
CI, or a task-isolated production authority.

The live current-main call to
`GET /api/v1/trial/forecast-input-authority` returned HTTP 503 with
`TRIAL_AUTHORIZATION_UNAVAILABLE`. The relevant master-data, production-plan,
active marketable-policy, factory, and retained-authority row counts were all
zero. This is a verified operationally available runtime with no real
business input loaded, not a claim that a production authority was found.

The legitimate next input route was audited at
`backend.app.planning.plan_importer.import_production_plans_csv`. A real
operator-provided plan must include the farm, season, variety, planted area,
expected yield, marketable rate, version, and valid effective/availability
metadata; a subfarm is required for a concrete Trial Forecast scope. R2 did
not construct or import any row.

No `POST /api/v1/trial/forecasts` was sent because the authority endpoint was
unavailable. Consequently there was no forecast, capture, daily authority, or
PIT readback. No S4 ledger event or validation/candidate scorer call occurred,
and TEST remained sealed. The permitted R2 outcome is:

```text
RESULT=REAL_INPUT_NOT_LOADED_AND_PUSHED
CURRENT_MAIN_RUNTIME_OPERATIONAL=true
FORECAST_INPUT_AUTHORITY_AVAILABLE=false
ENGINEERING_FORECAST_PATH_PROVEN=true
REAL_BUSINESS_FORECAST_NOT_EXECUTED=true
NEXT_REQUIRED_ACTION=LOAD_CURRENT_BUSINESS_FORECAST_INPUT
BUDGET_STATE_CLASS=LAST_ACCEPTED_DURABLE_BUDGET_SNAPSHOT
LAST_ACCEPTED_EFFECTIVE_CONSUMED=8
LAST_ACCEPTED_REMAINING=24
BUDGET_DELTA=0
TEST_REMAINS_SEALED=true
FINAL_STOP_GATE=COORDINATOR_CURRENT_REAL_FORECAST_R2_REVIEW
```
