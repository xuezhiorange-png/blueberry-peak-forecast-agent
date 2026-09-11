# V0.3 real business input materialization and first Forecast R1

```text
TASK_ID=V0_3_REAL_BUSINESS_INPUT_MATERIALIZATION_AND_FIRST_FORECAST_R1
TASK_CLASS=CURRENT_REAL_BUSINESS_INPUT_MATERIALIZATION_AND_FIRST_END_TO_END_FORECAST
BASE_MAIN_SHA=d704cc9338efda2e7aa80499b53622ae42f83fd6
RESULT=REAL_BUSINESS_INPUT_REQUIRED
```

## Terminal outcome

The current authorized environment does not contain a source that can be
positively identified as a current, forward-looking business input package.
The repository contains historical receipt data and plan/templates, but those
are not current business authority and were not imported. The available
acceptance/task runtimes are not production and contain no business authority
rows. No Forecast request was sent.

```text
CURRENT_REAL_BUSINESS_SOURCE_FOUND=false
CURRENT_REAL_BUSINESS_SOURCE_CLASS=NOT_LOCATED_IN_AUTHORIZED_ENVIRONMENT
FORECAST_AUTHORITY_DEPENDENCY_DAG_VERIFIED=true
MASTER_DATA_READY=false
PRODUCTION_PLAN_LOADED=false
SUBFARM_AUTHORITY_RESOLVED=false
MARKETABLE_POLICY_READY=false
MARKETABLE_POLICY_OPERATIONAL_INGESTION_PATH_AVAILABLE=false
TASK8_CURRENT_FORECAST_AVAILABLE=false
TASK8_FORECAST_RUN_ID=NONE
TASK9_CURRENT_RUN_AVAILABLE=false
TASK9_RUN_ID=NONE
FORECAST_INPUT_AUTHORITY_AVAILABLE=false
FORECAST_INPUT_AUTHORITY_ITEM_COUNT=0
REAL_NORMAL_FORECAST_EXECUTED=false
FORECAST_RUN_ID=NONE
FORECAST_RUN_STATUS=NOT_EXECUTED
DAILY_FORECAST_ROWS=0
P50_AVAILABLE=false
P80_AVAILABLE=false
P90_AVAILABLE=false
FORECAST_RESULT_PERSISTED=false
FORECAST_AUTHORITY_CAPTURED=false
FRESH_SESSION_PIT_READBACK=false
UI_REAL_FORECAST_OPERATIONAL=NOT_TESTED
CURRENT_REAL_FORECAST_CAPABILITY=BLOCKED_REAL_BUSINESS_INPUT_NOT_PROVIDED
V0_3_CLOSEOUT_FORECAST_CAPABILITY_GATE=FAIL
NEXT_REQUIRED_ACTION=COORDINATOR_PROVIDE_CURRENT_BUSINESS_INPUT_PACKAGE
```

This is a source-availability blocker, not a claim that real business data is
globally absent. It records only what could be established in the authorized
repository/runtime environment at this task boundary.

## Discovery and source decision

### Repository data

The fresh main checkout contains two raw receipt workbooks under `data/raw` and
several small CSV files under `data/templates`, including a production-plan
template. The raw workbooks are historical receipt sources, and the template
files are schemas/examples rather than an authorized current plan. Neither
category satisfies the forward-looking business-input requirement.

The historical objects were not opened, transformed, or imported for this
task. No repository raw row, SOURCE-002 partition, validation actual, TEST
payload, or synthetic value was used.

### Authorized external/runtime discovery

Read-only filesystem and runtime inspection found candidate-looking local files
without positive provenance proving that any is the current V0.3 business
source. They were not read or imported. The acceptance runtime on port 55437
was identified as a non-production, task/acceptance runtime; its relevant
business tables were empty. It is not evidence of global business-input
absence, and it was not promoted to a source.

The repository default local PostgreSQL profile (`localhost:5432`) and the
explicit test profile (`55432`) are not production authority. No database was
created, reconnected, seeded, backfilled, or changed.

## Forecast-authority dependency DAG

The code-level dependency DAG was audited read-only:

```text
authorized current business source
  -> master data and FarmSeasonVarietyPlan
  -> active marketable retention policy + scoped entries
  -> completed Task8 maturity authority
  -> completed Task9 harvest-state authority
  -> Trial forecast-input authority snapshot
  -> POST /api/v1/trial/forecasts
  -> execute_core_forecast_run
  -> capture_production_forecast_base_authority
  -> forecast_authority_capture + forecast_authority_daily
  -> load_pit_visible_forecast_authority
```

The implementation exists for the downstream edges, but the upstream current
business source and persisted authorities are unavailable in the authorized
environment. The DAG is therefore verified as a fail-closed implementation
boundary, not reported as an operational Forecast success.

### Code evidence

- `backend/app/api/trial.py` registers
  `GET /api/v1/trial/forecast-input-authority` and
  `POST /api/v1/trial/forecasts`.
- `backend/app/trial.py` implements
  `DefaultTrialApplicationService.get_forecast_input_authority`,
  `_load_forecast_authority_snapshot`, and `create_forecast`. The resolver
  requires persisted master data, a concrete subfarm scope, an active factory,
  `FarmSeasonVarietyPlan`, an active marketable policy, and the required
  relationships; an empty result fails closed.
- `backend/app/core_forecast/application.py` implements the normal core run
  and immutable completed persistence.
- `backend/app/forecast_authority/retention.py` owns natural production
  capture and `load_pit_visible_forecast_authority` readback.
- `backend/app/planning/plan_importer.py` provides the legitimate production
  plan CSV ingestion path. It does not by itself create all Forecast
  authority.
- `backend/app/maturity/service.py` and
  `backend/app/harvest_state/application.py` consume the Task8/Task9 authority
  contracts; they are not populated by this task.

### Capability versus current acceptance

| Capability | Code status | Current task evidence |
| --- | --- | --- |
| Normal Trial Forecast API | Implemented | Not executed; input authority unavailable. |
| Core Forecast calculation/persistence | Implemented | Not reached. |
| Production authority capture | Implemented | No capture rows created. |
| PIT readback | Implemented | Not applicable because no capture exists. |
| Plan ingestion | Available via importer | No current plan loaded. |
| Active marketable-policy ingestion | No current operational writer identified | Policy read path exists; no policy row is available. |
| Frontend Forecast/readback/export workflow | Implemented in current main | Not smoke-tested against real business data. |
| Real business Forecast | Not proven | Blocked by missing current input package. |

## Exact required next package

The complete field-level contract is in
`real-business-input-required-manifest-r1.md`. In summary, the coordinator
must provide an authorized current source with content identity and owner
provenance, resolvable farm/subfarm/season/variety/factory master data, a
current `FarmSeasonVarietyPlan`, an active marketable retention policy with
scoped entries, and the completed/current Task8 and Task9 authority inputs
required by the normal path. The package must be loaded through the normal
server-owned paths; no direct table insertion is permitted.

## Protected governance state

```text
CURRENT_V0_3_S4_COMPLETE=true
S4_FINAL_STATUS=CLOSED_NO_ADMISSIBLE_REPLACEMENT_SELECTED
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
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

## Stop gate

```text
RESULT=REAL_BUSINESS_INPUT_REQUIRED
REAL_BUSINESS_INPUT_WAS_CREATED=false
FORECAST_REQUEST_SENT=false
FORECAST_AUTHORITY_ROWS_CREATED=0
ACCURACY_VALIDATION_PERFORMED=false
MODEL_QUALITY_CLAIM_ISSUED=false
MODEL_APPROVED_FOR_PILOT=false
FINAL_STOP_GATE=COORDINATOR_REAL_BUSINESS_INPUT_AND_FIRST_FORECAST_REVIEW
```

## R2 current-live interpretation correction (append-only)

The original R1 source lookup observation is retained for audit, but its
interpretation as a current user-data absence claim is superseded. The current
R2 evidence distinguishes repository historical receipts, header-only
templates, unmounted previously supplied assets, and an empty acceptance
runtime. It reports the first actionable gap as a missing current minimal
scope row, not as proof that the user never supplied data.

R1_SOURCE_ABSENCE_INTERPRETATION_SUPERSEDED=true
USER_DATA_ABSENCE_CLAIM_ISSUED=false
PREVIOUSLY_PROVIDED_ASSET_STATUS=MIXED
CURRENT_RUNTIME_ASSET_STATUS=NOT_MOUNTED_IN_CODEX_RUNTIME
REPOSITORY_HISTORICAL_RECEIPT_DATA_PRESENT=true
FIRST_BROKEN_STAGE=MINIMAL_INPUT_SCOPE_ROW_BINDING
MISSING_EXTERNAL_BUSINESS_FACTS=CURRENT_SCOPE_LOCATION,CURRENT_SCOPE_VARIETY_LOOKUP,CURRENT_SCOPE_PLANTED_AREA_MU
CURRENT_REAL_FORECAST_CAPABILITY=BLOCKED_EXACT_EXTERNAL_FACT
NEXT_REQUIRED_ACTION=LOAD_ONE_CURRENT_MINIMAL_SCOPE_ROW_WITH_LOCATION_VARIETY_PLANTED_AREA_MU

See real-business-input-binding-and-minimal-forecast-r2.md and its evidence
JSON for the current-live binding audit.
