# Workpaper — S4 validation budget durable persistence contract R1

## Decision

This workpaper freezes the persistence contract required to close the PR #587 tail-truncation gap. It records a design decision only. No production code, test code, migration, schema, runner, or scoring execution was performed.

The current JSONL event journal is cryptographically chained, but its final accepted suffix can be deleted while leaving a valid prefix. Therefore JSONL cannot be the canonical validation-budget authority.

The future canonical authority is a PostgreSQL event ledger plus a PostgreSQL monotonic head row, updated in one transaction with compare-and-swap semantics.

The event ledger has one semantic source of truth. The stored `event_payload` is
the canonical event body used by the hash preimage; typed database columns are
validated projections for indexing, constraints, querying, and budget
reconciliation. They are never an independent authority.

CANONICAL_EVENT_BODY_IS_SINGLE_SOURCE_OF_TRUTH=true
TYPED_COLUMNS_ARE_CANONICAL_EVENT_BODY_PROJECTIONS=true
TYPED_COLUMNS_INDEPENDENT_SEMANTIC_AUTHORITY=false
TYPED_COLUMN_PAYLOAD_MISMATCH_FORBIDDEN=true
EVENT_HASH_COVERS_ALL_CANONICAL_EVENT_SEMANTICS=true
TYPED_PROJECTION_VALIDATION_REQUIRED_BEFORE_COMMIT=true
TYPED_PROJECTION_VALIDATION_REQUIRED_ON_READBACK=true
HASH_REPLAY_USES_STORED_CANONICAL_EVENT_BODY=true

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

The first implementation must create an authority row at version zero with the
all-zero SHA-256 head sentinel. The symbolic label `GENESIS` is human-readable
documentation only and is not a persisted field value. It must not create four
fake STARTED rows and must not reduce the legacy debit to zero.

GENESIS_IS_HUMAN_READABLE_LABEL_ONLY=true
GENESIS_PERSISTED_FIELD_VALUE_IS_ALL_ZERO_SHA256=true
ACCEPTED_HEAD_EVENT_HASH=0000000000000000000000000000000000000000000000000000000000000000
AUTHORITY_EMPTY_LAST_GLOBAL_ORDINAL=0

## Frozen transaction protocol

The future implementation must persist a STARTED event and advance the head in one PostgreSQL transaction. The model evaluation is permitted only after that transaction commits and the committed state is read back successfully.

This eliminates both split-brain sequences:

- JSONL append, commit, then DB head update;
- DB head update, commit, then JSONL append.

The accepted operation is:

candidate/run preflight -> authority CAS check -> STARTED event insert -> monotonic head/version advance -> PostgreSQL commit -> committed-head verification -> model evaluation

A CAS conflict, head mismatch, counter regression, event-chain mismatch, or budget exhaustion blocks closed. A process crash after the STARTED commit does not refund the debit. If model evaluation fails or terminal persistence fails, the STARTED debit remains consumed and the STARTED event is never deleted or refunded.

## Candidate/run and terminal binding constraints

STARTED candidate/run identity is a persistence-level constraint, not only an
application preflight check:

UNIQUE_STARTED_GLOBAL_EVALUATION_ORDINAL_PER_AUTHORITY=true
UNIQUE_STARTED_CANDIDATE_RUN_ORDINAL_PER_AUTHORITY=true
STARTED_GLOBAL_EVALUATION_ORDINAL_MIN=1
STARTED_CANDIDATE_RUN_ORDINAL_MIN=1
STARTED_CANDIDATE_RUN_ORDINAL_MAX=4

The required partial uniqueness is:

UNIQUE (authority_key, global_evaluation_ordinal)
WHERE event_type = 'EVALUATION_STARTED'

UNIQUE (authority_key, candidate_id, candidate_run_ordinal)
WHERE event_type = 'EVALUATION_STARTED'

Therefore the same run ordinal is valid for different candidates, but a
candidate cannot reuse its own run ordinal. The empty authority may retain
last global ordinal 0; no STARTED event may use global ordinal 0.

Terminal events have an exact immutable parent binding:

ORPHAN_TERMINAL_FORBIDDEN=true
TERMINAL_REQUIRES_EXISTING_STARTED=true
TERMINAL_STARTED_BINDING_SCOPE=AUTHORITY_KEY_X_EVALUATION_ID
TERMINAL_CANDIDATE_ID_MUST_MATCH_STARTED=true
DUPLICATE_TERMINAL_FORBIDDEN=true
TERMINAL_COUNTED_TOWARD_BUDGET=false
TERMINAL_NEVER_INCREMENTS_ACCEPTED_STARTED_COUNT=true

The terminal must bind to the one STARTED event with the same authority_key and
evaluation_id, and its candidate_id must match. Terminal persistence never
creates another budget debit or occupies a STARTED-only ordinal constraint.

## Canonical event body and typed projection binding

The physical `event_payload` stores the canonical event body. For STARTED, the
body includes evaluation_id, experiment_plan_version, candidate_id,
candidate_run_ordinal, global_evaluation_ordinal, invocation_type,
trigger_source, started_at, finished_at, execution_status,
metric_result_status, dataset_hash, validation_split_hash, code_commit_sha,
parameter_manifest_hash, random_seed, retry_of_evaluation_id,
counted_toward_budget, and budget_count_reason.

The hash preimage is:

event_hash = SHA256(canonical_json({event_type, canonical_event_body, previous_event_hash}))

For every persisted STARTED row, typed governance columns must equal the
corresponding stored body fields:

STARTED_TYPED_EVALUATION_ID_EQUALS_BODY=true
STARTED_TYPED_CANDIDATE_ID_EQUALS_BODY=true
STARTED_TYPED_CANDIDATE_RUN_ORDINAL_EQUALS_BODY=true
STARTED_TYPED_GLOBAL_EVALUATION_ORDINAL_EQUALS_BODY=true
STARTED_TYPED_INVOCATION_TYPE_EQUALS_BODY=true
STARTED_TYPED_COUNTED_TOWARD_BUDGET_EQUALS_BODY=true
STARTED_TYPED_BUDGET_COUNT_REASON_EQUALS_BODY=true

For TERMINAL rows, the same rule applies to the available typed fields:

TERMINAL_TYPED_EVALUATION_ID_EQUALS_BODY=true
TERMINAL_TYPED_CANDIDATE_ID_EQUALS_BODY=true
TERMINAL_TYPED_FINISHED_AT_EQUALS_BODY=true
TERMINAL_TYPED_EXECUTION_STATUS_EQUALS_BODY=true
TERMINAL_TYPED_METRIC_RESULT_STATUS_EQUALS_BODY=true

If a future schema does not expose a typed column for a field, that field stays
only in the canonical body; it is not duplicated with another assignable
value. Neither side overrides the other:

COLUMN_VALUE_OVERRIDES_EVENT_BODY=false
EVENT_BODY_OVERRIDES_MISMATCHED_COLUMN=false
MISMATCH_RESULT=BLOCKED
PROJECTION_MISMATCH_REASON=VALIDATION_EVENT_PROJECTION_MISMATCH

Projection equality is required before commit and on readback. Hash replay
reads the stored canonical body, verifies projections first, recomputes the
hash from that body, and then verifies the previous-event-hash chain. It must
not reconstruct the body from typed columns.

Hostile examples are fail-closed. `candidate_id=03_candidate` in a typed
column versus `candidate_id=02_candidate` in the body is blocked with
`VALIDATION_EVENT_PROJECTION_MISMATCH`; a typed
`candidate_run_ordinal=2` versus body ordinal 1 is blocked; and
`counted_toward_budget=false` versus body `true` is blocked. The implementation
must not choose one side, silently reduce the budget, or continue.

BUDGET_RECONCILIATION_REQUIRES_VERIFIED_EVENT_PROJECTIONS=true
BUDGET_RECONCILIATION_REQUIRES_VERIFIED_HASH_CHAIN=true
BUDGET_RECONCILIATION_REQUIRES_ACCEPTED_HEAD_MATCH=true

RETRY_COUNTS_AS_NEW_CANDIDATE_RUN=true
RETRY_REQUIRES_NEW_EVALUATION_ID=true

The implementation acceptance contract must add these focused tests:

- `test_started_typed_columns_must_match_hashed_event_body`
- `test_terminal_typed_columns_must_match_hashed_event_body`
- `test_candidate_id_cannot_diverge_between_column_and_event_body`
- `test_candidate_run_ordinal_cannot_diverge_between_column_and_event_body`
- `test_global_evaluation_ordinal_cannot_diverge_between_column_and_event_body`
- `test_evaluation_id_cannot_diverge_between_column_and_event_body`
- `test_counted_toward_budget_cannot_diverge_between_column_and_event_body`
- `test_budget_reconciliation_blocks_on_projection_mismatch`
- `test_hash_replay_uses_stored_canonical_event_body`

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
- [ ] Started candidate/run ordinal uniqueness is a partial persistence constraint including candidate_id.
- [ ] Started candidate/run ordinals are restricted to 1..4 and started global ordinals start at 1.
- [ ] Terminal events require the exact existing STARTED parent in the same authority/evaluation scope.
- [ ] Terminal candidate identity matches STARTED and duplicate terminals are rejected.
- [ ] Typed columns are validated projections of the hashed canonical event body.
- [ ] STARTED and TERMINAL projection mismatches fail closed before commit and on readback.
- [ ] Hash replay uses the stored canonical event body, not a body reconstructed from columns.
- [ ] Budget reconciliation verifies projections, the hash chain, and the accepted head first.
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
GENESIS_CANONICAL_VALUE_CORRECTED=true
STARTED_CANDIDATE_RUN_UNIQUENESS_FROZEN=true
TERMINAL_TO_STARTED_BINDING_FROZEN=true
IMPLEMENTATION_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_PR588_PAYLOAD_BINDING_CORRECTION_REVIEW

## Correction R2 addendum

Review ID 5140022893 required three contract-level clarifications without
changing the approved architecture. The corrected contract now uses only the
64-character all-zero SHA-256 value for a persisted empty-ledger head; keeps
`GENESIS` as a documentation label; requires STARTED candidate/run uniqueness
on `(authority_key, candidate_id, candidate_run_ordinal)` with candidate run
ordinal 1..4; and requires every TERMINAL to bind to the existing STARTED with
the same authority_key and evaluation_id and matching candidate_id.

OLD_CONTRACT_HASH=1b492fa3efa1205288d6288843b700122f74f96fecbb8bc12b3afe947d12810a
NEW_CONTRACT_HASH=85f54c6160282eddc7ebdc6eb847d21d996a3147e8c6a9e84783444e77916561

The follow-up implementation acceptance contract must include duplicate,
zero, five, and cross-candidate candidate-run ordinal cases, plus orphan,
candidate-mismatch, duplicate-terminal, exact-parent-binding, and
no-additional-budget-debit terminal cases. This task adds no test code and
does not authorize implementation, migration, scoring, TEST access, Ready, or
Merge.

GENESIS_CANONICAL_VALUE_CORRECTED=true
STARTED_CANDIDATE_RUN_UNIQUENESS_FROZEN=true
TERMINAL_TO_STARTED_BINDING_FROZEN=true
IMPLEMENTATION_AUTHORIZED=false
MIGRATION_AUTHORIZED=false
SCHEMA_CHANGE_AUTHORIZED=false
TEST_ACCESS_AUTHORIZED=false
TEST_MUST_REMAIN_SEALED=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_PR588_CONTRACT_CORRECTION_REVIEW

## Correction R3 addendum

Review correction R3 closes the remaining typed-column versus hashed-payload
binding gap without authorizing implementation or schema work. The persisted
canonical event body is the sole semantic authority; typed columns are
validated projections, and any mismatch blocks both commit and readback.

OLD_CONTRACT_HASH=85f54c6160282eddc7ebdc6eb847d21d996a3147e8c6a9e84783444e77916561
NEW_CONTRACT_HASH=a7c7c5eac5550f531836968b5001bfd487218960f31e56ad5a1c5c175169410f
CANONICAL_EVENT_BODY_IS_SINGLE_SOURCE_OF_TRUTH=true
TYPED_COLUMN_PAYLOAD_BINDING_FROZEN=true
PROJECTION_MISMATCH_FAILS_CLOSED=true
IMPLEMENTATION_AUTHORIZED=false
MIGRATION_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_PR588_PAYLOAD_BINDING_CORRECTION_REVIEW
