# Workpaper — V0.3 real business input and first Forecast R1

## Task and baseline

```text
TASK_ID=V0_3_REAL_BUSINESS_INPUT_MATERIALIZATION_AND_FIRST_FORECAST_R1
BASE_MAIN_SHA=d704cc9338efda2e7aa80499b53622ae42f83fd6
BASE_MAIN_EXPECTED_CONTAINS=true
GIT_STATUS_CLEAN_AT_START=true
PRODUCTION_CODE_CHANGED=false
DATABASE_SCHEMA_CHANGED=false
MIGRATION_CHANGED=false
MODEL_CHANGED=false
PARAMETERS_CHANGED=false
```

The independent checkout was freshly fetched from the repository remote and
verified at the expected main commit. No changes were made before the
docs-only result was determined.

## Source gate

The source gate was evaluated before any Forecast execution:

1. Repository `data/raw` was inventoried as historical receipt material. It was
   not accepted as current forward-looking input.
2. Repository `data/templates` was inventoried as template/schema material. It
   was not accepted as a current business plan or authority source.
3. Authorized local filesystem names were inspected only for source discovery;
   candidate-looking files lacked positive current-source provenance and were
   not opened, copied, reconstructed, or imported.
4. Existing local PostgreSQL runtimes were classified by their explicit task,
   test, acceptance, or demo scope. The acceptance runtime was not treated as
   production. Its relevant business tables were empty, so it cannot provide
   the required current input authority.

Therefore:

```text
CURRENT_REAL_BUSINESS_SOURCE_FOUND=false
CURRENT_REAL_BUSINESS_SOURCE_CLASS=NOT_LOCATED_IN_AUTHORIZED_ENVIRONMENT
GLOBAL_REAL_BUSINESS_INPUT_ABSENCE_CLAIM_ISSUED=false
CURRENT_ACCEPTANCE_RUNTIME_BUSINESS_INPUT_DATA_MISSING=true
```

No raw business file was committed. No secret, credential, raw row, actual
label, forecast row, or prediction was added to Git.

## DAG verification notes

The following code paths were checked read-only and are the canonical normal
execution boundary:

| Stage | Current path | Result |
| --- | --- | --- |
| Actor | `backend.app.actual_harvest_import.api_auth.get_actual_harvest_actor` | Existing server-owned actor contract. |
| Input authority | `DefaultTrialApplicationService._load_forecast_authority_snapshot` | Requires master, plan, active policy, factory, and scope relationships. |
| Trial API | `backend.app.api.trial` | GET authority and POST Forecast routes exist. |
| Core run | `backend.app.core_forecast.application.execute_core_forecast_run` | Existing normal execution path. |
| Task8 | `backend.app.maturity.service` | Requires completed maturity/model and current input lineage. |
| Task9 | `backend.app.harvest_state.application.execute_harvest_state_run` | Requires Task8, operational capacity/weather inputs, and authority-bound request. |
| Capture | `backend.app.forecast_authority.retention.capture_production_forecast_base_authority` | Existing natural completion boundary. |
| PIT readback | `backend.app.forecast_authority.retention.load_pit_visible_forecast_authority` | Existing fresh-session readback contract. |

The DAG is implemented, but the first required node—an authorized current
business source—was not available. The correct result is to stop before the
input-authority resolver can return a usable item.

## Why templates and historical data cannot be promoted

The production-plan template contains fields such as farm, season, variety,
planted area, expected yield, marketable rate, version, effective dates, and
availability. Those fields describe a shape; they do not establish a current
owner-authorized record. Likewise, historical receipt workbooks contain
outcomes and cannot be used as a forward-looking operational plan or as a
prospective authority replacement. Using either would turn a missing-source
condition into synthetic business input.

The active marketable retention policy is a separate persisted authority. A
plan `marketable_rate` is not a substitute for the policy header and scoped
sorting/postharvest retention entries required by the core Forecast path.

## Required coordinator handoff

The coordinator must provide or bind a real current input package and its owner
authorization. The full field list is recorded in
`real-business-input-required-manifest-r1.md`; the non-negotiable downstream
proof is:

```text
resolved input authority item > 0
normal POST /api/v1/trial/forecasts
completed daily P50/P80/P90 output
natural forecast_authority_capture and forecast_authority_daily persistence
fresh load_pit_visible_forecast_authority readback
```

No direct call to retention and no database seed/backfill is permitted.

## Non-execution ledger

```text
REAL_NORMAL_FORECAST_EXECUTED=false
FORECAST_RESULT_PERSISTED=false
FORECAST_AUTHORITY_CAPTURED=false
FRESH_SESSION_PIT_READBACK=false
S4_CANDIDATE_EXECUTION_PERFORMED=false
VALIDATION_SCORING_PERFORMED=false
PROSPECTIVE_SCAN_PERFORMED=false
NEW_VALIDATION_LEDGER_EVENT_COUNT=0
TEST_ACCESS_REQUESTED=false
TEST_BYTES_READ=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
```

## Terminal disposition

```text
RESULT=REAL_BUSINESS_INPUT_REQUIRED
CURRENT_REAL_FORECAST_CAPABILITY=BLOCKED_REAL_BUSINESS_INPUT_NOT_PROVIDED
V0_3_CLOSEOUT_FORECAST_CAPABILITY_GATE=FAIL
NEXT_REQUIRED_ACTION=COORDINATOR_PROVIDE_CURRENT_BUSINESS_INPUT_PACKAGE
FINAL_STOP_GATE=COORDINATOR_REAL_BUSINESS_INPUT_AND_FIRST_FORECAST_REVIEW
```
