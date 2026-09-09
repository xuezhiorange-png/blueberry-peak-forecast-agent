# Workpaper — V0.3 post-S4 business-pilot remaining scope

TASK_ID=V0_3_POST_S4_BUSINESS_PILOT_REMAINING_SCOPE_AND_EXECUTION_PLAN_R1
REPOSITORY=xuezhiorange-png/blueberry-peak-forecast-agent
AUDIT_MODE=CURRENT_MAIN_READ_ONLY
BASE_MAIN_SHA=82d174e450e9e9d7bb9a04964185e0d45d91b9c1
PR592_MERGE_COMMIT=82d174e450e9e9d7bb9a04964185e0d45d91b9c1
PR592_MERGE_IN_BASE=true

## Scope and controls

This workpaper records a current-main inventory. It does not perform authority
store discovery, database reconnect, Docker or volume recovery, DSN search,
seeding, backfill, forecast reconstruction, prospective scan, candidate
execution, validation scoring, TEST access, model/parameter changes, S1/S4
plan changes, or production implementation.

The only permitted repository mutation is this documentation package and an
append-only current pointer in development-plan.md. The JSON evidence is a
planning record and is not a live budget or authority source.

## Baseline verification

The checkout was synchronized to origin/main. The fetched origin/main and the
local main both resolved to:

    82d174e450e9e9d7bb9a04964185e0d45d91b9c1

This commit is the PR #592 merge commit. The starting main worktree was clean.

The current S4 terminal pointer in the development plan and the PR #592
machine-readable evidence agree on:

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

## Audit findings

### S1/S2/S3/S4 boundary

S1 and S2 are accepted for the governed SOURCE-002 historical
TRAIN/VALIDATION foundation. S3 is complete as an engineering stage, but its
historical incumbent PIT question is terminally NOT_COMPUTABLE because daily
incumbent forecast authority was not durably retained. This is not a failed
backtest and no historical forecast values may be inferred.

S4-A and S4-B are frozen. Durable PostgreSQL budget and forecast-authority
retention paths are implemented and verified. The S4 prospective path is
contractually available, but the current scan record proves no existing real
production authority store with pre-existing forecast writes. Therefore S4
candidate validation has not started and the budget remains 4/28.

### Business source and actuals

SOURCE-002, its accepted materialization, and the actual-harvest pipeline
provide a valid historical engineering/data foundation. The label service
supports immutable AS_OF_EVALUATION snapshots. That does not prove that
post-TEST actual labels for a future prospective cohort are currently
available.

### Forecast path

The production trial/Core Forecast path exists. The normal forecast completion
boundary captures the base forecast authority before later Task10 extension
work. The retention module provides immutable complete daily P50/P80/P90
authority and a PIT-visible reader that validates cutoff, hashes, lineage,
scope, and completeness.

The implementation is therefore future-replay capable by contract. It must
not be confused with proof that a real production capture already exists in
the current runtime.

### API and frontend

The backend exposes actual-harvest, forecast-input-authority, forecast create,
forecast read, daily curve, export, and quality-report endpoints. The
frontend exposes engineering Forecast and Quality routes with browser
evidence. The current quality surface includes a persisted naive-baseline
comparison, but the repository evidence does not establish the complete S5
surface of current/previous approved-model comparison, structured
evidence-derived explanations, adoption/non-adoption records, or manual
adjustment reasons.

### Runtime and operations

The repository has local compose files, a basic live/ready health surface,
request/idempotency identifiers, and persisted lineage/audit hashes. It does
not prove a production deployment target, external secret/configuration
binding, backup/restore operation, production authority readiness checks,
telemetry/alerts, incident runbook, or operating ownership. These are
remaining pilot-readiness concerns, not reasons to reopen the closed S4
authority-store recovery.

## S4 waiting semantics

The earliest missing input for current prospective S4 execution is not a
missing historical master table, missing local Docker volume, or a missing
recovery PR. It is the external prospective event:

    A_REAL_NORMAL_PRODUCTION_FORECAST_HAS_BEEN_CAPTURED_BY_THE_EXISTING_FORECAST_AUTHORITY_RETENTION_PATH_AND_CORRESPONDING_POST_TEST_ACTUAL_LABELS_HAVE_LATER_BECOME_AVAILABLE

Only after that event may the coordinator authorize the single read-only
prospective scan. A READY result may support a versioned cohort and plan
amendment. It does not itself authorize a candidate or TEST evaluation.

## S5/S6 authority check

Current V0.3 S5 and S6 definitions do exist in development-plan.md sections
4.7 and 4.8. They are not imported from V0.1 or V0.2:

    V0_3_S5_CURRENT_DEFINITION_EXISTS=true
    V0_3_S6_CURRENT_DEFINITION_EXISTS=true
    V0_3_S5_AUTHORIZED=false
    V0_3_S6_AUTHORIZED=false
    CURRENT_V0_3_S5_COMPLETE=false
    CURRENT_V0_3_S6_COMPLETE=false

S5 is the operations/explanation/continuous-evaluation slice. S6 is the
real-season pilot and technical/model/business acceptance slice, with a
minimum of two farms and two varieties plus fixed cadence and complete actual
feedback. Production release is explicitly outside V0.3.

## Remaining work classification

The detailed nine-field task records are in the companion plan and JSON
evidence. The decision categories are:

1. S4 prospective scan/cohort: WAITING_EXTERNAL_TRIGGER.
2. S4 candidate validation: WAITING_FOR_COHORT_AND_AUTHORIZATION.
3. S4 locked TEST/model approval: WAITING_FOR_VALIDATION_AND_TEST_AUTHORIZATION.
4. S5-A operations readiness: DEFINED_BUT_NOT_AUTHORIZED.
5. S5-B frontend comparisons/explanations: DEFINED_BUT_NOT_AUTHORIZED.
6. S5-C continuous evaluation/adoption: DEFINED_BUT_NOT_AUTHORIZED and also
   requires actual feedback.
7. S6 real-season pilot: NOT_STARTED.
8. S6 business acceptance/release boundary: NOT_STARTED.
9. Production runtime/operational readiness: PARTIAL_LOCAL_ENGINEERING_ONLY.
10. S5-A contract and runtime-gap plan: CAN_START_AS_DOCUMENTATION_ONLY.

The tenth item is deliberately a planning task, not an authorization to start
S5 implementation. It is the only immediate next task selected by this audit.

## Sole next task

    NEXT_EXECUTABLE_TASK=V0_3_S5_A_PILOT_OPERATIONS_READINESS_CONTRACT_AND_RUNTIME_GAP_PLAN_R1

The next task should remain docs-only: define the S5-A operation/run
identity, comparison/history/export, quality-notice, feedback/adoption,
runtime, owner, and acceptance-evidence contracts. It must explicitly depend
on future MODEL_APPROVED_FOR_PILOT for implementation and must not touch S4
plan identity, validation budget, production code, TEST, or the S1 split.

## No-longer-needed work

Historical incumbent recovery, historical C01/frozen-S1/C03 reruns, repeated
prospective store discovery, PostgreSQL reconnect, Docker volume recovery,
DSN search, replacement authority-store creation, seeding, backfill, and
forecast synthesis are closed or forbidden. Existing historical workpapers
remain immutable provenance.

Unrelated routing, factory allocation/optimization, automatic dispatch,
transport scheduling, ERP/IoT integration, complex RBAC, LLM chat, and
production release are outside the current V0.3 scope.

## Return-to-S4 checklist

Return to S4 only after:

1. A real normal production Forecast has completed through the existing
   retention path.
2. Its complete daily authority, cutoff, lineage, and hashes are readable by
   the existing PIT reader.
3. Corresponding post-TEST actual labels are available with
   AS_OF_EVALUATION visibility.
4. The coordinator separately authorizes the one read-only scan.
5. The scan proves exact business-grain pairing, full 7/14/21 horizons,
   coverage, and all five real identity hashes.

At that point, a new coordinator decision may consider prospective cohort
freezing and candidate-validation authorization. No step implies the next.

FINAL_STOP_GATE=COORDINATOR_V0_3_POST_S4_BUSINESS_PILOT_REMAINING_SCOPE_REVIEW
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
