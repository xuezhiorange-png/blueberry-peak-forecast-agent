# V0.3 post-S4 business-pilot remaining scope and execution plan

TASK_ID=V0_3_POST_S4_BUSINESS_PILOT_REMAINING_SCOPE_AND_EXECUTION_PLAN_R1
TASK_CLASS=CURRENT_MAIN_READ_ONLY_STATUS_INVENTORY
BASE_MAIN_SHA=82d174e450e9e9d7bb9a04964185e0d45d91b9c1
PR592_MERGE_IN_BASE=true
DOCUMENT_SCOPE_ONLY=true

## Decision summary

The current main branch contains the PR #592 terminal prospective-dependency
closeout. V0.3 has completed the accepted S1/S2 data foundation, the S3
engineering implementation and historical-PIT disposition, and the S4
governance, durable-retention, and execution-control implementation. It has
not completed a live prospective S4 validation, model approval, S5 pilot
operations, or S6 real-season business acceptance.

The historical S3-C question remains terminally NOT_COMPUTABLE. The current
S4 wait is not an open recovery bug: the existing retention path has not yet
been proven to contain a real normal-production forecast capture together with
the corresponding post-TEST actual labels. No further authority-store
discovery, PostgreSQL reconnect, Docker recovery, DSN search, seeding,
backfill, or prospective rescan is authorized or required before that
external trigger exists.

The one task that can be started now is a documentation-only S5-A pilot
operations-readiness contract and runtime-gap plan. It does not implement S5,
authorize a model, consume validation budget, open TEST, or change the S4
plan.

## Current live governance state

The following values are the current live disposition, not a reconstruction
from an old planning snapshot:

    CURRENT_V0_3_S1_COMPLETE=true
    CURRENT_V0_3_S2_COMPLETE=true
    CURRENT_V0_3_S3_COMPLETE=true
    V0_3_S3_ENGINEERING_IMPLEMENTATION_COMPLETE=true
    S3_C_HISTORICAL_PIT_STATUS=NOT_COMPUTABLE
    HISTORICAL_VALIDATION_TERMINAL=true
    HISTORICAL_PIT_REASON=HISTORICAL_INCUMBENT_DAILY_FORECAST_AUTHORITY_NOT_DURABLY_RETAINED
    CURRENT_V0_3_S4_COMPLETE=false
    CURRENT_S4_EXECUTION_STATUS=WAITING_FOR_REAL_PROSPECTIVE_FORECAST_AUTHORITY
    CURRENT_S4_BLOCKER=REAL_PROSPECTIVE_FORECAST_AUTHORITY_NOT_YET_AVAILABLE
    FURTHER_PROSPECTIVE_AUTHORITY_STORE_DISCOVERY_REQUIRED=false
    FURTHER_POSTGRES_RECONNECT_REQUIRED=false
    FURTHER_DOCKER_VOLUME_RECOVERY_REQUIRED=false
    FURTHER_DSN_SEARCH_REQUIRED=false
    PROSPECTIVE_SCAN_BEFORE_TRIGGER=false
    CANDIDATE_EXECUTION_BEFORE_TRIGGER=false
    VALIDATION_SCORING_BEFORE_TRIGGER=false
    TEST_REMAINS_SEALED=true
    LEGACY_RECONCILED_VALIDATION_DEBIT=4
    CANONICAL_STARTED_COUNT=0
    EFFECTIVE_CONSUMED=4
    REMAINING=28
    BUDGET_DELTA=0

The old S4-A plan remains immutable at
v0.3-experiment-plan-v1 with hash
9e223a02a1b38c028c230a45eb1fa8323f3c2247bb85e7b439f3351e51042500.
This task does not amend it.

## 1. Where V0.3 is complete

### Data and authority foundation

- S1 is accepted and S2 is accepted for the governed SOURCE-002
  TRAIN/VALIDATION materialization.
- SOURCE-002 is available and attested; the accepted materialized dataset
  identity is
  f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785.
- The actual-harvest import and label-snapshot pipeline exists, with
  immutable snapshot semantics and AS_OF_EVALUATION visibility enforcement.
- This proves an accepted historical data foundation. It does not prove that
  future post-TEST labels already exist.

### Forecast and persistence engineering

- The production forecast service and the Core Forecast persistence/query
  path exist.
- DefaultTrialApplicationService.create_forecast captures the base forecast
  authority immediately after successful forecast completion, before later
  Task10 extension work.
- The forecast-authority retention envelope durably retains complete daily
  P50/P80/P90 values, cutoff, lineage, and canonical hashes. The
  load_pit_visible_forecast_authority reader fails closed on cutoff, hash,
  lineage, scope, and completeness violations.
- The actual-harvest, trial forecast, daily-curve, CSV export, and quality
  report APIs exist.

These are implemented capabilities and accepted engineering evidence. The
current environment still does not prove a real production authority-store
cohort for the next prospective S4 evaluation.

### S4 control plane

- S4-A froze the finite eight-candidate plan and S4-B froze the gate,
  metrics, guardrails, budget, and TEST boundary.
- PostgreSQL durable validation-budget persistence and the #587 execution
  authority integration are implemented, including append-only events,
  CAS, readback, and no JSONL live authority.
- Historical C01/C03 paths are closed or retired as audit-only/non-computable
  history. No historical run may be silently rerun.
- PR #592 made the absence of a proven real prospective production store a
  terminal current dependency state rather than a new recovery queue.

## 2. Business-pilot capability inventory

| Capability | Current status | What is proven | What is not proven |
| --- | --- | --- | --- |
| Real business source | AVAILABLE_FOR_ACCEPTED_S1_S2_BASELINE | SOURCE-002 identity, rebuild parity, and accepted TRAIN/VALIDATION materialization | A current real-season pilot feed and owner/cadence boundary |
| Actual-harvest pipeline | IMPLEMENTED | Import, validation, seal/commit, immutable label snapshots, AS_OF_EVALUATION contract | Corresponding future post-TEST actual labels for a prospective cohort |
| Forecast execution | IMPLEMENTED_ENGINEERING_PATH | Trial/Core Forecast production path and persisted daily results | A live prospective cohort captured in the current environment |
| Forecast authority retention | IMPLEMENTED_AND_VERIFIED | Base capture, Task10 extension, PIT reader, hashes, immutability, fresh-session evidence | Existing real production rows available to scan now |
| Persistence/query | IMPLEMENTED_ENGINEERING_PATH | PostgreSQL-owned forecast authority and API readback/export paths | Deployment-specific production database binding and operational SLO evidence |
| API | IMPLEMENTED_ENGINEERING_SURFACE | Actual-harvest, trial forecast, daily curve, export, and quality report endpoints | S5 operations package and model-approved pilot workflow |
| Frontend/browser workflow | ENGINEERING_FLOW_PRESENT | Forecast and quality pages plus browser/unit evidence | S5 comparison, warning, explanation, adoption, and pilot-acceptance surfaces |
| Business pilot operation | NOT_STARTED | S5 definition and dependency order exist | Operating cadence, user roles, adoption records, and real-season run evidence |
| Deployment/runtime prerequisites | PARTIAL_LOCAL_ENGINEERING_ONLY | Local compose and basic live/ready health endpoints | Production deployment binding, external secret/config management, backup/restore, runbook, and operational ownership |
| Observability/audit | PARTIAL_AUDITABILITY | Request/idempotency identifiers, lineage, hashes, and persisted evidence | Production telemetry, alerting, dashboards, incident procedures, and pilot operating review |
| Release/pilot acceptance | NOT_STARTED | S6 acceptance contract exists; production release is explicitly out of V0.3 scope | Model approval, real-season acceptance, rollback decision, or release approval |

The frontend and API facts above describe engineering capability, not S5 or
S6 acceptance. In particular, the current quality flow does not by itself
establish current/previous approved-model comparison, a continuous adoption
ledger, or a real business pilot.

## 3. Why S4 must wait

The S4 historical S1 validation path is permanently closed as:

    C03_HISTORICAL_VALIDATION_RESULT=NOT_COMPUTABLE
    FROZEN_S1_VALIDATION_PAIRED_S4_EXECUTABLE=false
    HISTORICAL_AUTHORITY_RECOVERY_REQUIRED=false
    HISTORICAL_AUTHORITY_RECOVERY_ALLOWED=false

The prospective path is contractually implemented, but PR #592 proved only
that the current execution environment could not establish an existing store
with pre-existing real production forecast writes. The next S4 scan is
therefore gated on an external business event:

    A_REAL_NORMAL_PRODUCTION_FORECAST_HAS_BEEN_CAPTURED_BY_THE_EXISTING_FORECAST_AUTHORITY_RETENTION_PATH_AND_CORRESPONDING_POST_TEST_ACTUAL_LABELS_HAVE_LATER_BECOME_AVAILABLE

After that event, and only then, the coordinator may authorize the single
prospective read-only scan. A READY scan can freeze a prospective cohort and
version a future S4 plan; it still does not authorize candidate execution.
Until then, prospective cohort feasibility is not proven, candidate
validation cannot start, TEST remains sealed, and the durable budget remains
4 consumed of 32 with 28 remaining.

These are waiting conditions, not new engineering blockers to be repackaged
as another recovery PR.

## 4. Current S5 and S6 definitions

Current V0.3 definitions do exist in
docs/v0-3/development-plan.md:

    V0_3_S5_CURRENT_DEFINITION_EXISTS=true
    V0_3_S6_CURRENT_DEFINITION_EXISTS=true

S5 is defined in section 4.7 as business forecast operations, explanation,
history/export, comparison, data-quality notices, and continuous
forecast-to-actual/adoption records. Section 4.7 freezes the S5 slice and its
required capabilities, but it does not freeze a formal S5-A/S5-B/S5-C
subtask decomposition. The three names used by this planning package are
proposals only:

    CURRENT_V0_3_S5_SLICE_DEFINITION_EXISTS=true
    CURRENT_V0_3_S5_FORMAL_SUBTASK_DECOMPOSITION_EXISTS=false
    PROPOSED_S5_EXECUTION_DECOMPOSITION_SOURCE=PR593_PLANNING_PROPOSAL
    PROPOSED_S5_EXECUTION_DECOMPOSITION_AUTHORIZED=false
    PROPOSED_S5_EXECUTION_DECOMPOSITION_IMPLEMENTED=false

    PROPOSED_S5_EXECUTION_DECOMPOSITION=[
      S5-A PILOT_OPERATIONS_READINESS,
      S5-B FRONTEND_COMPARISON_WARNINGS_AND_STRUCTURED_EXPLANATION,
      S5-C CONTINUOUS_EVALUATION_AND_ADOPTION_RECORDS
    ]

S6 is defined in section 4.8 as the real-season business pilot and acceptance
slice. Its minimum scope is at least two farms and two varieties, fixed
forecast cadence, complete actual-result feedback, technical/model/business
acceptance, and explicit pilot accepted/failed disposition. Production
release is explicitly outside V0.3 scope.

Therefore:

    V0_3_S5_AUTHORIZED=false
    V0_3_S6_AUTHORIZED=false
    CURRENT_V0_3_S5_COMPLETE=false
    CURRENT_V0_3_S6_COMPLETE=false
    S5_IMPLEMENTATION_STARTED=false
    S6_IMPLEMENTATION_STARTED=false

The older freeze-time false fields and historical workpapers remain immutable
snapshots. They are not mass-rewritten; the current task adds only this
current-main inventory and an append-only pointer.

## 5. Remaining task inventory

Each entry below uses the required decision fields. CAN_EXECUTE_NOW means that
the named task itself can start under a separately scoped authorization; it
does not imply authorization for a dependent implementation or execution lane.

### 01 — S4 prospective trigger scan and cohort freeze

TASK_NAME=S4_PROSPECTIVE_TRIGGERED_SCAN_AND_COHORT_FREEZE

WHY_NEEDED=Establish the lawful prospective forecast/actual pairing authority
needed before any future S4 candidate validation.

CURRENT_STATUS=WAITING_FOR_EXTERNAL_PROSPECTIVE_AUTHORITY_TRIGGER

BLOCKER=No proven real normal-production forecast capture plus corresponding
post-TEST actual labels in the existing retention path.

CAN_EXECUTE_NOW=false

DEPENDENCY=The exact PR #592 trigger must occur first; no further store
discovery, reconnect, Docker recovery, DSN search, seed, or backfill.

PROPOSED_STAGE=V0.3-S4 continuation

ESTIMATED_SCOPE=One read-only scanner invocation; if READY, freeze a new
prospective cohort version and prepare a new plan version without writing
forecast/label authority or consuming budget.

ACCEPTANCE_CRITERIA=The scanner is run once only after the trigger; if READY,
all five cohort hashes are real and bound, every included grain has complete
7/14/21 horizons, TEST has no overlap, S1 is unchanged, and the budget is
still 4/28.

### 02 — S4 prospective candidate validation

TASK_NAME=S4_PROSPECTIVE_CANDIDATE_VALIDATION

WHY_NEEDED=Evaluate registered candidates against the frozen prospective
cohort under the S4-B fairness, metric, guardrail, and durable-ledger rules.

CURRENT_STATUS=NOT_STARTED_NOT_AUTHORIZED

BLOCKER=Requires an accepted prospective cohort/plan version and a separate
candidate-execution authorization; TEST remains sealed until the later gate.

CAN_EXECUTE_NOW=false

DEPENDENCY=Task 01 READY result, exact plan/cohort identity, paired data,
verified PostgreSQL budget state, and explicit candidate authorization.

PROPOSED_STAGE=V0.3-S4 continuation

ESTIMATED_SCOPE=Finite registered candidate invocations with durable STARTED
and TERMINAL records, paired incumbent comparison, honest metric/guardrail
outcomes, and append-only budget reconciliation.

ACCEPTANCE_CRITERIA=No hidden retries or candidates, all data/policy hashes
match, every started invocation is durably recorded before scoring, all
NOT_COMPUTABLE outcomes remain explicit, and no selection or promotion is
issued automatically.

### 03 — S4 locked TEST and model approval

TASK_NAME=S4_LOCKED_TEST_AND_MODEL_APPROVAL

WHY_NEEDED=Convert an eligible prospective validation result into a
one-time locked TEST evaluation and a coordinator-reviewed pilot model
approval/rollback manifest.

CURRENT_STATUS=NOT_ISSUED_NOT_STARTED

BLOCKER=Requires completed prospective candidate validation, a locked
selection-eligible result, and separate TEST authorization.

CAN_EXECUTE_NOW=false

DEPENDENCY=Task 02 accepted; all selection and guardrail prerequisites
resolved; explicit TEST authorization.

PROPOSED_STAGE=V0.3-S4-D

ESTIMATED_SCOPE=Lock candidate and incumbent identities, execute the separately
authorized TEST evaluation once, issue a selection decision only under the
frozen rules, and record approval/rollback evidence.

ACCEPTANCE_CRITERIA=TEST access is separately authorized and sealed before
use, no TEST-after tuning occurs, one immutable result is recorded, selection
is traceable, and MODEL_APPROVED_FOR_PILOT is explicitly decided rather than
inferred.

### 04 — Proposed S5-A pilot operations readiness

TASK_NAME=S5_A_PILOT_OPERATIONS_READINESS

WHY_NEEDED=Turn the approved model into a repeatable, auditable pilot
operations workflow rather than a one-off engineering forecast.

CURRENT_STATUS=PROPOSED_NOT_AUTHORIZED

BLOCKER=MODEL_APPROVED_FOR_PILOT and accepted S4 completion are required for
implementation and operations acceptance.

CAN_EXECUTE_NOW=false

DEPENDENCY=Task 03 approval, an independently authorized S5-A scope, and
runtime/owner/security prerequisites.

PROPOSED_STAGE=V0.3-S5-A

ESTIMATED_SCOPE=Versioned forecast run records, current/previous comparison,
forecast-to-actual and naive-baseline views, history/readback/export,
quality/data-gap notices, and operational feedback hooks.

ACCEPTANCE_CRITERIA=An operations-readiness package proves immutable run
records, version and lineage display, comparison/readback/export behavior,
quality notices, and explicit S5-A review acceptance.

### 05 — Proposed S5-B frontend comparison and explanation

TASK_NAME=S5_B_FRONTEND_COMPARISON_WARNINGS_AND_STRUCTURED_EXPLANATION

WHY_NEEDED=Give business users evidence-derived comparison, warnings, and
explanation surfaces without client-side calculation or invented causes.

CURRENT_STATUS=PROPOSED_NOT_AUTHORIZED

BLOCKER=Requires accepted S5-A operations contracts and records.

CAN_EXECUTE_NOW=false

DEPENDENCY=Task 04 accepted; an independently authorized S5-B scope; real
persisted evidence for all displayed claims.

PROPOSED_STAGE=V0.3-S5-B

ESTIMATED_SCOPE=Browser/API workflow for forecast/model/version comparison,
data-quality warnings, structured evidence-backed explanations, and
version-aware display.

ACCEPTANCE_CRITERIA=Browser evidence covers the frozen flows; explanations
reference recorded input/version/result differences; no unsupported LLM
cause, client-side formula, or TEST access is introduced.

### 06 — Proposed S5-C continuous evaluation and adoption records

TASK_NAME=S5_C_CONTINUOUS_EVALUATION_AND_ADOPTION_RECORDS

WHY_NEEDED=Close the operating loop with repeated forecast-to-actual
evaluation, adoption/non-adoption reasons, and manual-adjustment audit.

CURRENT_STATUS=PROPOSED_NOT_AUTHORIZED

BLOCKER=Requires accepted S5-A and S5-B plus future actual labels.

CAN_EXECUTE_NOW=false

DEPENDENCY=Tasks 04 and 05 accepted, actual-result feedback availability,
and an independently authorized S5-C scope.

PROPOSED_STAGE=V0.3-S5-C

ESTIMATED_SCOPE=Append-only continuous evaluation records, metric updates,
adoption/non-adoption ledger, and reasoned manual-adjustment records.

ACCEPTANCE_CRITERIA=Every record is attributable to forecast/actual
identities, updates are append-only, missing data is explicit, adoption
decisions are distinct from business acceptance, and S5-C review passes.

### 07 — S6 real-season pilot scope and execution

TASK_NAME=S6_REAL_SEASON_PILOT_SCOPE_AND_EXECUTION

WHY_NEEDED=Exercise the pilot-approved model with real business users and
operating cadence across the minimum governed pilot scope.

CURRENT_STATUS=NOT_STARTED

BLOCKER=Requires model approval, S5 acceptance, owner/security/scope
authorization, real business source, and actual-result feedback.

CAN_EXECUTE_NOW=false

DEPENDENCY=Tasks 03–06 as applicable, at least two farms and two varieties,
fixed cadence, documented source owner and measurement boundary.

PROPOSED_STAGE=V0.3-S6

ESTIMATED_SCOPE=Real-season run plan, scheduled forecast operations, actual
feedback, technical traceability, and business-use evidence.

ACCEPTANCE_CRITERIA=The scope is authorized before data import; fixed cadence
and minimum farms/varieties are met; forecast, feedback, and audit records are
complete; no production command or unrelated automation is introduced.

### 08 — S6 business acceptance and release boundary

TASK_NAME=S6_BUSINESS_ACCEPTANCE_AND_RELEASE_BOUNDARY

WHY_NEEDED=Make an explicit pilot accepted/failed decision from technical,
model, and business evidence while preserving the V0.3 release boundary.

CURRENT_STATUS=NOT_STARTED

BLOCKER=Requires a completed S6 real-season pilot and complete business
acceptance evidence.

CAN_EXECUTE_NOW=false

DEPENDENCY=Task 07 complete, owner/business acceptance roles, and rollback or
non-adoption decision evidence.

PROPOSED_STAGE=V0.3-S6

ESTIMATED_SCOPE=Acceptance review of early-peak usefulness, preparation
impact, user understanding, false-positive/false-negative acceptability,
adoption, non-adoption, rollback, and larger-pilot recommendation.

ACCEPTANCE_CRITERIA=V0_3_BUSINESS_PILOT_ACCEPTED or FAILED is explicitly
issued with evidence; production release remains false because release is
outside V0.3 scope.

### 09 — Production runtime and operational readiness

TASK_NAME=PRODUCTION_RUNTIME_AND_OPERATIONAL_READINESS

WHY_NEEDED=Provide the deployment, security, resilience, health, telemetry,
and operational ownership needed for a real business pilot.

CURRENT_STATUS=PARTIAL_LOCAL_ENGINEERING_ONLY

BLOCKER=Actual deployment target, owner, security requirements, backup/restore
policy, and operational SLO/incident requirements are not frozen in the
current evidence.

CAN_EXECUTE_NOW=false

DEPENDENCY=Separate runtime-readiness authorization and a defined pilot
environment; it must not use the task-isolated #591 databases as production.

PROPOSED_STAGE=S5 ENABLER / TECHNICAL ACCEPTANCE

ESTIMATED_SCOPE=Production configuration and secret binding, migrations,
backup/restore, health/readiness including authority checks, telemetry,
alerts, runbook, and exact runtime evidence.

ACCEPTANCE_CRITERIA=The target environment is identified; non-default secrets
are externalized; restore is tested; health and authority readiness are
observable; alerts/runbook/ownership are reviewed; no TEST or validation
budget is touched.

### 10 — Immediate documentation-only S5-A contract and runtime-gap plan

TASK_NAME=V0_3_S5_A_PILOT_OPERATIONS_READINESS_CONTRACT_AND_RUNTIME_GAP_PLAN_R1

WHY_NEEDED=Translate the already-defined S5-A objective into an executable
proposal for an executable scope, evidence schema, and dependency checklist
while S4 waits for its external prospective trigger.

CURRENT_STATUS=CAN_START_AS_DOCUMENTATION_ONLY

BLOCKER=No blocker for the planning artifact itself. S5-A implementation
still depends on MODEL_APPROVED_FOR_PILOT and separate authorization.

CAN_EXECUTE_NOW=true

DEPENDENCY=Current V0.3 S5 definition, current API/retention evidence, and
runtime audit; it must not amend the S4 experiment plan or authorize S5.

PROPOSED_STAGE=S5-A PROPOSAL PRE-AUTHORIZATION PLANNING

ESTIMATED_SCOPE=Docs-only contract for pilot run identity, comparison/history/
export, quality notices, feedback/adoption records, runtime prerequisites,
owners, acceptance evidence, and a gap-to-implementation map.

ACCEPTANCE_CRITERIA=One reviewed contract names the exact S5-A boundary and
dependencies; acceptance evidence is machine-readable; implementation paths
remain unauthorized; no production code, parameters, model, database,
budget, S1 split, S4 plan, or TEST state changes.

This is the only immediate next task named by this inventory. It is a
governance/planning task that would freeze the S5-A proposal for review; it is
not an existing formal S5-A authority and does not claim that S5 has started.

    NEXT_EXECUTABLE_TASK_IS_PR593_PROPOSED_DECOMPOSITION=true
    NEXT_EXECUTABLE_TASK_IS_EXISTING_S5_FORMAL_SUBTASK=false
    NEXT_EXECUTABLE_TASK_SCOPE=DOCUMENTATION_ONLY
    NEXT_EXECUTABLE_TASK_DOES_NOT_AUTHORIZE_S5=true

## 6. Work that is no longer needed or is explicitly out of scope

- Historical S3-C incumbent forecast recovery is terminally closed as
  NOT_COMPUTABLE. No additional historical master/plan/weather/Task8/Core/
  Task10 recovery task is needed or allowed.
- Repeated prospective authority-store discovery, PostgreSQL reconnect,
  Docker-volume recovery, and DSN search are explicitly closed by PR #592.
- Creating a replacement production authority store, seeding it, backfilling
  forecasts, or synthesizing labels/forecasts is prohibited.
- Re-running historical C01 or frozen S1/C03 validation is not a remaining
  product task. Its evidence is audit-only or terminally non-computable.
- Multi-factory routing, factory allocation/optimization, automatic dispatch,
  vehicle/transport scheduling, ERP/IoT integration, complex RBAC, LLM chat,
  and cold-storage design optimization remain outside V0.3.
- Production release approval is not a hidden final step of S6; the current
  V0.3 definition explicitly keeps production release out of scope.

## 7. Exact condition for returning to S4

Return to S4 only when all of the following are true in the real production
authority path:

1. A normal production Forecast execution has completed through the existing
   forecast-authority retention path.
2. Its production capture is durably readable by the existing PIT reader,
   including complete daily authority, cutoff, lineage, and hashes.
3. The corresponding actual-harvest labels become available after the
   declared TEST interval with AS_OF_EVALUATION visibility.
4. The coordinator authorizes the one read-only prospective scan.

The scan must then prove the full 7/14/21 horizon cohort, exact business
grain, coverage, and all five identity hashes. Only after a READY result may
the coordinator consider a versioned prospective cohort/plan and a separate
candidate-validation authorization. No step implies the next.

## Evidence basis

- docs/v0-3/s1/evidence/s1-acceptance-record.json
- docs/v0-3/s2/evidence/s2-slice-complete-registry-closeout.json
- docs/v0-3/s3/evidence/s3-final-closeout-and-s4-entry-authorization-r1.json
- docs/v0-3/s4/evidence/s4-a-experiment-plan-and-candidate-registry-freeze-r1.json
- docs/v0-3/s4/evidence/s4-b-guardrail-policy-and-validation-execution-gate-freeze-r1.json
- docs/v0-3/s4/evidence/s4-prospective-post-test-authority-scan-r1.json
- docs/v0-3/development-plan.md sections 4.7, 4.8, and the EOF-appended
  PR #592 terminal prospective-dependency pointer
- backend/app/actual_harvest_labels/service.py
- backend/app/api/actual_harvest_imports.py
- backend/app/api/trial.py
- backend/app/trial.py
- backend/app/forecast_authority/retention.py
- backend/app/core_forecast/application.py
- backend/app/api/health.py
- frontend/src/app/routes.tsx
- frontend/src/pages/ForecastPage.tsx
- frontend/src/pages/QualityPage.tsx
- docker-compose.yml and docker-compose.test.yml

FINAL_STOP_GATE=COORDINATOR_V0_3_POST_S4_BUSINESS_PILOT_REMAINING_SCOPE_REVIEW
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
