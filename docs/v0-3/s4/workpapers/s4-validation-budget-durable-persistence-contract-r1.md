# Workpaper — S4 validation budget durable persistence contract R1

## Decision

This workpaper freezes the persistence contract required to close the PR #587 tail-truncation gap. It records a design decision only. No production code, test code, migration, schema, runner, or scoring execution was performed.

The current JSONL event journal is cryptographically chained, but its final accepted suffix can be deleted while leaving a valid prefix. Therefore JSONL cannot be the canonical validation-budget authority.

The future canonical authority is a PostgreSQL event ledger plus a PostgreSQL monotonic head row, updated in one transaction with compare-and-swap semantics.

## Repository survey

The survey was performed from the task-start origin/main at:

CONTRACT_BASE_MAIN_SHA=77e3d8ac63d794babfe0c8549fd34d0467f0d57e

Relevant findings:

| Area | Finding | Contract consequence |
| --- | --- | --- |
| S4 validation budget | No existing S4 budget authority or canonical DB event ledger was found. | A later implementation must add the explicitly approved persistence contract. |
| Forecast Authority | Owns prospective forecast captures and daily forecast rows. | Cross-domain reuse is forbidden. |
| Quality Evaluation | Owns completed quality metric artifacts. | It is not a validation invocation ledger or global budget head. |
| Rolling Backtest | Owns backtest runs, nodes, attempts, and stage events. | It is not the S4 candidate budget authority. |
| SQLAlchemy transactions | Existing repositories use transactions and selected row locks. | The future adapter may reuse this transaction style. |
| CAS | No existing S4-compatible authority CAS was found. | The future implementation must provide DB-level CAS. |
| Alembic | Existing schema changes are Alembic-owned. | Any later schema implementation requires a separate authorization. |

The correct result is not to repurpose a similarly named table. The authority must own the S4 validation budget domain and must atomically own both events and the accepted head.

## Frozen bootstrap

The historical C01 debit remains an unledgered, evidence-backed debit:

SOURCE_PR=587
SOURCE_PR_HEAD_SHA=ffc5dd31bfb5ea9f036d0e27d3c4d9566ce1a69d
SOURCE_REVIEW_ID=5139541424
CURRENT_CANONICAL_EVENT_COUNT=0
CURRENT_CANONICAL_STARTED_COUNT=0
LEGACY_UNLEDGERED_C01_STARTED_EVALUATION_COUNT=4
LEGACY_RECONCILED_VALIDATION_DEBIT=4
EFFECTIVE_VALIDATION_EVALUATIONS_CONSUMED=4
REMAINING_EFFECTIVE_VALIDATION_BUDGET=28
LEGACY_ROWS_BACKFILLED=false
HISTORICAL_LEDGER_FABRICATION=false

The first implementation must create an authority row at version zero with a GENESIS head. It must not create four fake STARTED rows and must not reduce the legacy debit to zero.

## Frozen transaction protocol

The future implementation must persist a STARTED event and advance the head in one PostgreSQL transaction. The model evaluation is permitted only after that transaction commits and the committed state is read back successfully.

This eliminates both split-brain sequences:

- JSONL append, commit, then DB head update;
- DB head update, commit, then JSONL append.

The accepted operation is:

candidate/run preflight -> authority CAS check -> STARTED event insert -> monotonic head/version advance -> PostgreSQL commit -> committed-head verification -> model evaluation

A CAS conflict, head mismatch, counter regression, event-chain mismatch, or budget exhaustion blocks closed. A process crash after the STARTED commit does not refund the debit. If model evaluation fails or terminal persistence fails, the STARTED debit remains consumed and the STARTED event is never deleted or refunded.

## Tail truncation cases

The implementation must compare the database event history with the accepted authority row. If the authority records run2 as the accepted head but storage only returns the run1 prefix, it must return:

STATUS=BLOCKED
REASON=VALIDATION_LEDGER_TAIL_TRUNCATION_DETECTED

It must not report the shortened prefix as a new valid budget state. This applies both to deletion of a final STARTED event and deletion of the final STARTED plus TERMINAL suffix.

## Review checklist for the next implementation task

- [ ] Authority row is scoped to V0_3_S4_VALIDATION_BUDGET.
- [ ] Authority and event rows are PostgreSQL durable state.
- [ ] Event insert and head advance commit atomically.
- [ ] CAS checks version, event count, started count, head hash, and last ordinal.
- [ ] Accepted event rows cannot be updated or deleted by the application path.
- [ ] Started ordinals and evaluation identities are unique within the scope.
- [ ] 4 legacy + canonical started remains the budget formula.
- [ ] No legacy rows are fabricated.
- [ ] JSONL is derived/audit only.
- [ ] Model evaluation cannot begin before durable STARTED commit.
- [ ] Tail truncation is a distinct fail-closed reason.
- [ ] Concurrency and crash semantics have focused tests.
- [ ] TEST remains sealed and no candidate is executed.

## Boundary

This workpaper does not authorize the implementation task or change PR #587. PR #587 remains blocked on its existing head-authority finding. The next permitted step is a separately authorized implementation after this contract PR is reviewed and merged.

CONTRACT_ONLY=true
PRODUCTION_CODE_CHANGED=false
TEST_CODE_CHANGED=false
SCHEMA_CHANGED=false
MIGRATION_ADDED=false
CANDIDATE_01_RERUN_PERFORMED=false
CANDIDATE_02_EXECUTION_PERFORMED=false
NEW_VALIDATION_SCORING_CALL_COUNT=0
TEST_EVALUATION_PERFORMED=false
IMPLEMENTATION_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_S4_DURABLE_PERSISTENCE_CONTRACT_REVIEW
