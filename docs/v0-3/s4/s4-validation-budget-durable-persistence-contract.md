# S4 validation budget durable persistence contract v1

## Status and scope

This document freezes the persistence contract required before any future S4 validation execution. It is a contract-only artifact. It does not add a SQLAlchemy model, repository, migration, runner, workflow, or scoring call.

The source finding is the tail-truncation gap recorded by PR #587:

VALIDATION_LEDGER_DURABLE_HEAD_AUTHORITY_UNAVAILABLE

The current JSONL journal has a cryptographic event chain, but the journal and its filesystem are one mutable durability boundary. A deletion of the final accepted event leaves a valid prefix, so the budget can incorrectly move from 4 legacy + 2 canonical = 6 back to 4 legacy + 1 canonical = 5.

The contract therefore establishes one future canonical authority:

CANONICAL_VALIDATION_EXECUTION_AUTHORITY=POSTGRESQL
CANONICAL_DB_EVENT_LEDGER_REQUIRED=true
DURABLE_MONOTONIC_HEAD_REQUIRED=true
GENESIS_IS_HUMAN_READABLE_LABEL_ONLY=true
GENESIS_PERSISTED_FIELD_VALUE_IS_ALL_ZERO_SHA256=true

No candidate is executed by this contract. TEST remains sealed.

## Source and current state

TASK_ID=V0_3_S4_VALIDATION_BUDGET_DURABLE_PERSISTENCE_CONTRACT_R1
CONTRACT_VERSION=v0.3-s4-validation-budget-durable-persistence-contract-v1
SOURCE_PR=587
SOURCE_PR_HEAD_SHA=ffc5dd31bfb5ea9f036d0e27d3c4d9566ce1a69d
SOURCE_PR_BASE_SHA=77e3d8ac63d794babfe0c8549fd34d0467f0d57e
SOURCE_REVIEW_ID=5139541424
SOURCE_BLOCKER=VALIDATION_LEDGER_DURABLE_HEAD_AUTHORITY_UNAVAILABLE
CONTRACT_OR_PERSISTENCE_AMENDMENT_REQUIRED=true

The legacy C01 debit is a separate historical fact. It is not represented as four fabricated canonical events:

CURRENT_CANONICAL_STARTED_COUNT=0
LEGACY_UNLEDGERED_C01_STARTED_EVALUATION_COUNT=4
LEGACY_RECONCILED_VALIDATION_DEBIT=4
LEGACY_ROWS_BACKFILLED=false
HISTORICAL_LEDGER_FABRICATION=false
LEGACY_NUMERIC_EVIDENCE_SELECTION_AUTHORITY=false
CURRENT_EFFECTIVE_VALIDATION_EVALUATIONS_CONSUMED=4
CURRENT_REMAINING_EFFECTIVE_VALIDATION_BUDGET=28

## Architecture decision

The repository survey found no existing S4 validation-budget authority, validation event table, or application-level CAS authority. Existing Forecast Authority, Quality Evaluation, and Rolling Backtest persistence objects own different business domains and must not be repurposed merely because they are durable. Existing SQLAlchemy transactions and row locks are reusable implementation patterns, but they are not an existing S4 CAS store.

EXISTING_S4_VALIDATION_BUDGET_AUTHORITY_FOUND=false
EXISTING_REUSABLE_CAS_PATTERN_FOUND=false
EXISTING_REUSABLE_TRANSACTION_PATTERN_FOUND=true
CROSS_DOMAIN_AUTHORITY_REUSE_FORBIDDEN=true

The future implementation must create one PostgreSQL transaction boundary for the canonical event and its accepted head. JSONL may remain an audit export, debug mirror, or human-readable evidence projection, but it cannot be used to recover or reduce the DB budget.

POSTGRESQL_IS_DURABLE_VALIDATION_LEDGER_AUTHORITY=true
JSONL_IS_PRIMARY_DURABILITY_AUTHORITY=false
JSONL_BUDGET_AUTHORITY=false
JSONL_DERIVED_FROM_DATABASE=true
JSON_SIDECAR_DURABLE_HEAD_AUTHORITY=false
PROCESS_MEMORY_IS_BUDGET_AUTHORITY=false

## Authority object

The implementation must persist one singleton or explicitly scoped authority row:

AUTHORITY_TYPE=S4_VALIDATION_BUDGET
AUTHORITY_SCOPE=V0_3_S4
AUTHORITY_KEY=V0_3_S4_VALIDATION_BUDGET

The authority row must contain, at minimum:

- authority_key: primary key, fixed to V0_3_S4_VALIDATION_BUDGET for this scope.
- authority_version: non-negative monotonic version, initially 0.
- accepted_event_count: number of committed canonical events, initially 0.
- accepted_started_count: number of committed budget-counted STARTED events, initially 0.
- accepted_head_event_hash: lowercase SHA-256; for the empty ledger it is the
  64-character all-zero SHA-256 sentinel.
- accepted_last_global_evaluation_ordinal: non-negative monotonic ordinal, initially 0.
- legacy_reconciled_validation_debit: frozen at 4; never silently reclassified.
- created_at and updated_at: database timestamps owned by the authority store.

Required authority invariants:

AUTHORITY_VERSION_MONOTONIC=true
EVENT_COUNT_MONOTONIC=true
STARTED_COUNT_MONOTONIC=true
GLOBAL_EVALUATION_ORDINAL_MONOTONIC=true
HEAD_HASH_REGRESSION_FORBIDDEN=true
LEGACY_RECONCILED_VALIDATION_DEBIT=4

The authority row must reject negative counters, a head hash with the wrong format, accepted_started_count greater than accepted_event_count, and an effective budget above MAX_VALIDATION_EVALUATIONS=32.

## Canonical event ledger

The implementation must persist the canonical events in a PostgreSQL event table with the authority row in the same database. The business role is fixed as S4_VALIDATION_EVENT; the physical table name may follow repository naming conventions.

The event table must support exactly these event types: EVALUATION_STARTED and EVALUATION_TERMINAL.

Each event must bind these fields: authority_key, event_sequence, event_type, evaluation_id, candidate_id, event_payload, previous_event_hash, event_hash, and created_at.

An EVALUATION_STARTED event additionally requires candidate_run_ordinal, global_evaluation_ordinal, invocation_type, counted_toward_budget, and budget_count_reason. A STARTED event must satisfy:

STARTED_CANDIDATE_RUN_ORDINAL_MIN=1
STARTED_CANDIDATE_RUN_ORDINAL_MAX=4
STARTED_GLOBAL_EVALUATION_ORDINAL_MIN=1

An EVALUATION_TERMINAL event must bind to the one existing EVALUATION_STARTED event with the same authority_key and evaluation_id. Its candidate_id must equal the STARTED candidate_id. A terminal event is not a second STARTED invocation and never consumes additional budget.

The started contract is immutable:

STARTED_COUNTED_TOWARD_BUDGET=true
STARTED_BUDGET_COUNT_REASON=STARTED_INVOCATION
TERMINAL_ADDITIONAL_BUDGET_DEBIT=0
TERMINAL_COUNTED_TOWARD_BUDGET=false
ORPHAN_TERMINAL_FORBIDDEN=true
TERMINAL_REQUIRES_EXISTING_STARTED=true
TERMINAL_STARTED_BINDING_SCOPE=AUTHORITY_KEY_X_EVALUATION_ID
TERMINAL_CANDIDATE_ID_MUST_MATCH_STARTED=true
DUPLICATE_TERMINAL_FORBIDDEN=true
TERMINAL_NEVER_INCREMENTS_ACCEPTED_STARTED_COUNT=true

The event schema must freeze these database constraints:

- primary key authority_key plus event_sequence;
- foreign key from event authority scope to the authority row;
- unique authority_key plus event_hash;
- unique authority_key plus evaluation_id plus event_type;
- partial unique started global_evaluation_ordinal within the authority scope;
- partial unique started candidate_id plus candidate_run_ordinal within the authority scope;
- STARTED global_evaluation_ordinal is at least 1; only the empty authority sentinel may have last ordinal 0;
- STARTED candidate_run_ordinal is in the inclusive range 1..4;
- positive event sequence;
- started-only fields required for STARTED and absent or neutral for TERMINAL;
- SHA-256 fields exactly 64 lowercase hexadecimal characters;
- TERMINAL requires an existing STARTED in the same authority scope and evaluation_id;
- TERMINAL candidate_id must match the bound STARTED candidate_id;
- at most one TERMINAL exists for each authority_key plus evaluation_id;
- no UPDATE or DELETE of accepted events;
- no event sequence gap can be accepted by the head advance transaction.

For PostgreSQL, started-ordinal uniqueness must be represented with partial unique indexes or equivalent constraints:

UNIQUE (authority_key, global_evaluation_ordinal) WHERE event_type = 'EVALUATION_STARTED'
UNIQUE (authority_key, candidate_id, candidate_run_ordinal) WHERE event_type = 'EVALUATION_STARTED'

The second constraint must include candidate_id, so the same run ordinal is allowed for different candidates while duplicate runs for one candidate are rejected. Terminal rows do not occupy either STARTED-only ordinal constraint.

## Hash chain

The event chain remains part of the contract:

GENESIS_EVENT_HASH=0000000000000000000000000000000000000000000000000000000000000000
GENESIS_IS_HUMAN_READABLE_LABEL_ONLY=true
GENESIS_PERSISTED_FIELD_VALUE_IS_ALL_ZERO_SHA256=true

The symbolic label `GENESIS` is documentation-only. The only persisted
`accepted_head_event_hash` value for the empty ledger is the 64-character
all-zero SHA-256 sentinel above.

The canonical preimage is the repository canonical JSON representation of the event type, event payload, and previous event hash. The event hash must be computed as SHA-256 of event_type plus canonical event payload plus previous_event_hash.

For every new event:

- previous_event_hash equals the current durable accepted_head_event_hash;
- event_sequence equals current accepted_event_count plus 1.

The implementation must verify the full DB chain when reading. A valid chain is necessary but not sufficient: the DB head counters and hash are the independent evidence that a tail has not been removed from the event history.

## Atomic append and CAS

The event insert and head advance must be one PostgreSQL transaction:

EVENT_INSERT_AND_HEAD_ADVANCE_SAME_DB_TRANSACTION=true
COMPARE_AND_SWAP_REQUIRED=true
CONCURRENT_WRITER_FAILS_CLOSED=true

The semantic operation is equivalent to updating the authority row only when authority_key, authority_version, accepted_event_count, accepted_started_count, accepted_head_event_hash, and accepted_last_global_evaluation_ordinal all equal the expected values. The update increments authority_version and writes the new event count, started count, head hash, last ordinal, and updated_at.

If the affected row count is not exactly one, the transaction must roll back and return:

VALIDATION_BUDGET_AUTHORITY_CAS_CONFLICT

The implementation must not silently retry the same evaluation identity after a CAS conflict. A new operator-triggered invocation requires a new evaluation_id and is counted as a new invocation when it commits.

## STARTED transaction boundary

Every future validation invocation must follow this order:

1. Resolve the frozen candidate and run authority.
2. Start a PostgreSQL transaction and resolve the scoped budget authority.
3. Lock or CAS the current authority state.
4. Verify that the remaining effective budget is positive and the candidate run count is within its limit.
5. Construct the exact canonical EVALUATION_STARTED payload.
6. Insert the canonical STARTED event.
7. Advance the durable head, counters, and version using the expected state.
8. Commit the PostgreSQL transaction.
9. Read back and verify the committed STARTED authority.
10. Only then allow model evaluation to start.

MODEL_EVALUATION_BEFORE_DURABLE_STARTED_COMMIT=false

If any step before commit fails, the event and head update must both be absent and model evaluation must not start. If commit succeeds and the process crashes before model evaluation, the STARTED debit remains consumed. If model evaluation fails or terminal persistence fails, the STARTED debit remains consumed and the STARTED event is never deleted or refunded.

## Budget and candidate semantics

The R3 formula is frozen:

canonical_started = durable DB accepted_started_count
effective = LEGACY_RECONCILED_VALIDATION_DEBIT + canonical_started
remaining = MAX_VALIDATION_EVALUATIONS - effective

MAX_VALIDATION_EVALUATIONS=32
MAX_RUNS_PER_CANDIDATE=4
LEGACY_RECONCILED_VALIDATION_DEBIT=4

Expected forward states:

| Canonical started | Effective consumed | Remaining |
| ---: | ---: | ---: |
| 0 | 4 | 28 |
| 1 | 5 | 27 |
| 2 | 6 | 26 |
| 28 | 32 | 0 |

At effective 32, the next STARTED transaction must fail closed before model evaluation. Candidate-level run count remains independent from the global effective count; for example, two C02 starts mean candidate count 2, global canonical started count 2, and effective count 6 after the legacy debit.

## Tail truncation and readback

The DB authority is the accepted prefix boundary. A reader must compare the event history with the accepted authority row before calculating budget.

If the authority says accepted_event_count=4, accepted_started_count=2, and accepted_head_event_hash is the terminal-run2 hash, but the event table reads only the run1 prefix, the result is:

STATUS=BLOCKED
REASON=VALIDATION_LEDGER_TAIL_TRUNCATION_DETECTED

It must not recompute effective consumption as 5 and continue. A mismatch at the accepted boundary uses VALIDATION_LEDGER_HEAD_MISMATCH. Counter mismatches use VALIDATION_LEDGER_EVENT_COUNT_MISMATCH or VALIDATION_LEDGER_STARTED_COUNT_MISMATCH. Hash-chain failures use VALIDATION_EVENT_HASH_CHAIN_MISMATCH.

## Bootstrap and legacy binding

The first implementation migration or initialization must not create legacy events. It must create one authority row only when the authority does not exist:

AUTHORITY_EXISTS_BEFORE=false
AUTHORITY_VERSION=0
ACCEPTED_EVENT_COUNT=0
ACCEPTED_STARTED_COUNT=0
ACCEPTED_HEAD_EVENT_HASH=0000000000000000000000000000000000000000000000000000000000000000
ACCEPTED_LAST_GLOBAL_EVALUATION_ORDINAL=0
AUTHORITY_EMPTY_LAST_GLOBAL_ORDINAL=0
LEGACY_RECONCILED_VALIDATION_DEBIT=4

If the row already exists, initialization must validate it and never reset, overwrite, or reduce counters. The debit source is frozen to:

SOURCE_PR=587
SOURCE_PR_HEAD_SHA=ffc5dd31bfb5ea9f036d0e27d3c4d9566ce1a69d
SOURCE_REVIEW_ID=5139541424
LEGACY_DEBIT_RECLASSIFICATION_AUTHORIZED=false

## Failure vocabulary

At minimum, implementation must expose these stable reason codes:

- VALIDATION_BUDGET_AUTHORITY_MISSING
- VALIDATION_BUDGET_AUTHORITY_INVALID
- VALIDATION_BUDGET_AUTHORITY_CAS_CONFLICT
- VALIDATION_LEDGER_HEAD_MISMATCH
- VALIDATION_LEDGER_EVENT_COUNT_MISMATCH
- VALIDATION_LEDGER_STARTED_COUNT_MISMATCH
- VALIDATION_LEDGER_TAIL_TRUNCATION_DETECTED
- VALIDATION_GLOBAL_ORDINAL_REGRESSION
- VALIDATION_EVENT_HASH_CHAIN_MISMATCH
- VALIDATION_BUDGET_EXHAUSTED
- VALIDATION_CANDIDATE_RUN_LIMIT_EXCEEDED
- VALIDATION_CANDIDATE_RUN_ORDINAL_DUPLICATE
- VALIDATION_CANDIDATE_RUN_ORDINAL_INVALID
- VALIDATION_TERMINAL_WITHOUT_STARTED
- VALIDATION_TERMINAL_CANDIDATE_MISMATCH
- VALIDATION_DUPLICATE_TERMINAL
- LEGACY_VALIDATION_DEBIT_MISMATCH

## Security and trust boundary

The trusted durability boundary is the authoritative PostgreSQL persistence store. This contract protects against application/process and filesystem failure modes: journal rollback, partial writes, concurrent runners, stale runner state, and a deleted event suffix inconsistent with the accepted DB head. It does not claim to protect against a malicious administrator or root operator who rewrites the entire trusted database.

## Required implementation acceptance tests

The subsequent implementation task must provide at least these tests:

- test_bootstrap_is_zero_canonical_plus_four_legacy
- test_first_started_commits_five_of_thirty_two
- test_second_started_commits_six_of_thirty_two
- test_started_commit_precedes_model_execution
- test_committed_started_survives_process_failure
- test_failed_scoring_does_not_refund_started_budget
- test_terminal_does_not_increment_budget
- test_delete_last_started_is_detected
- test_delete_last_started_and_terminal_suffix_is_detected
- test_head_hash_regression_is_rejected
- test_event_count_regression_is_rejected
- test_started_count_regression_is_rejected
- test_global_ordinal_regression_is_rejected
- test_stale_cas_writer_is_rejected
- test_two_concurrent_runners_cannot_consume_same_ordinal
- test_budget_32_blocks_next_started
- test_candidate_fifth_run_is_rejected
- test_duplicate_started_candidate_run_ordinal_is_rejected
- test_started_candidate_run_ordinal_zero_is_rejected
- test_started_candidate_run_ordinal_five_is_rejected
- test_same_run_ordinal_is_allowed_for_different_candidates
- test_orphan_terminal_is_rejected
- test_terminal_candidate_id_must_match_started
- test_duplicate_terminal_is_rejected
- test_terminal_same_authority_and_evaluation_binds_exact_started
- test_terminal_does_not_increment_started_count_or_budget
- test_no_legacy_fake_events_are_created
- test_jsonl_is_not_budget_authority

## Explicit boundary

This contract does not authorize implementation, migration, schema change, runner change, candidate execution, scoring, TEST access, model change, or parameter change. A later implementation task must be separately authorized after this contract is reviewed and merged.

IMPLEMENTATION_AUTHORIZED=false
MIGRATION_AUTHORIZED=false
SCHEMA_CHANGE_AUTHORIZED=false
SCORING_AUTHORIZED=false
TEST_ACCESS_AUTHORIZED=false
TEST_MUST_REMAIN_SEALED=true
PR587_MUTATION_AUTHORIZED=false
PR587_READY_AUTHORIZED=false
PR587_MERGE_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_PR588_CONTRACT_CORRECTION_REVIEW
