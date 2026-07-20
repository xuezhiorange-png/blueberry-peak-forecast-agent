# Q2A-I7 Label Snapshot and Revision Winner Contract

> **Issue:** #102
> **Contract acceptance comment:** `5018974606`
> **Contract base:** `91249fbfed8d8c250d79b495236b15374bac667d`
> **Scope:** `I7_LABEL_SNAPSHOT_AND_REVISION_WINNER`
> **Status:** `ACCEPTED_DESIGN_NOT_IMPLEMENTED`
> **Implementation authorized:** `NO`
> **Backtest authorized:** `NO`

## 1. Authority and precedence

This document is the accepted authority for Q2A-I7 cutoff-bound actual-label snapshots and revision-winner selection.

Where it conflicts with earlier status or design-candidate text, this document supersedes the conflicting portions of:

- `q2a-label-snapshot-and-revision-contract.md`;
- `q2a-import-validation-revision-and-commit-contract.md`;
- `q2a-user-supplied-actual-harvest-import-contract.md`;
- `q2a-prediction-label-alignment-decision.md`.

Historical design records remain useful for provenance. Their stale status blocks do not override this accepted contract.

```text
V0_2_S2_I7_CONTRACT_ACCEPTED=true
I5_LINEAGE_CONTRACT_HARDENING_ACCEPTED=true
I7_DESIGN_CONTRACT_FREEZE_ACCEPTED=true
NO_STEP_IMPLIES_THE_NEXT=true
```

## 2. Current source status

V0.2-S1 implemented the committed actual-harvest source boundary:

- committed import batches;
- immutable sealed records;
- deterministic commit manifests;
- commit-manifest bindings to validation, mapping, lineage, and source evidence;
- caller-owned atomic commit.

Therefore this historical status is no longer current:

```text
DIRECT_ACTUAL_HARVEST_SOURCE_NOT_FOUND_IN_CURRENT_REPOSITORY
```

The current status is:

```text
ACTUAL_HARVEST_COMMITTED_SOURCE_STATUS=IMPLEMENTED
PRIMARY_ACTUAL_HARVEST_LABEL_READY=false
PRIMARY_LABEL_BLOCKER=IMMUTABLE_LABEL_SNAPSHOT_NOT_IMPLEMENTED
```

A committed source record is evidence. It is not by itself an evaluation label.

## 3. I7 boundary

I7 includes exactly:

```text
COMMITTED_SOURCE_SELECTION=true
CUTOFF_VISIBILITY=true
REVISION_WINNER_SELECTION=true
REVISION_FIRST_AGGREGATION=true
IMMUTABLE_LABEL_SNAPSHOT=true
COVERAGE_AND_EXCLUSION_REPORT=true
```

I7 excludes:

```text
PUBLIC_HTTP_API=false
FORECAST_RUN_SELECTION=false
FORECAST_LABEL_BINDING=false
BACKTEST_RUNNER=false
QUALITY_METRICS=false
NAIVE_BASELINE=false
FRONTEND=false
MODEL_CHANGE=false
```

V0.2-S2 is broader than I7. The S2 backtest portion requires separate authorization.

## 4. Canonical label grain

The v1 label grain is:

```text
SEASON
X FARM
X SUBFARM
X VARIETY
X HARVEST_BUSINESS_DATE
```

Canonical status:

```text
CANONICAL_LABEL_GRAIN=SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_HARVEST_BUSINESS_DATE
PLOT_SUPPORTED=false
SUBFARM_ONLY_PLOT_REJECTED=true
```

`SUBFARM_OR_PLOT` in earlier generic design text is superseded for I7 v1. Plot input must not be silently converted to a subfarm.

## 5. Source-family boundary

One label snapshot contains one source family only.

```text
SOURCE_FAMILY_IDENTITY=source_system
SINGLE_SOURCE_SYSTEM_PER_SNAPSHOT=true
CROSS_SOURCE_AGGREGATION=false
SOURCE_PRIORITY=false
```

No source-priority order is authorized. Cross-source conflicts fail closed.

## 6. Four-time model

The inherited ordering remains:

```text
forecast_cutoff_at
< forecast_target_date_or_window_end
<= label_observation_cutoff_at
<= replay_executed_at
```

I7 owns `label_observation_cutoff_at` as part of the canonical snapshot request and immutable snapshot header.

`forecast_cutoff_at` remains prediction-side evidence and must not be replaced by label timestamps.

## 7. Source visibility

### 7.1 AS_OF_EVALUATION

A revision is historically visible only when all conditions hold:

```text
batch_status=COMMITTED
matching_commit_manifest_exists=true
source_system=request.source_system
source_recorded_at_authority_status=TRUSTED_SOURCE_TIMESTAMP
source_recorded_at IS NOT NULL
source_recorded_at<=label_observation_cutoff_at
record_is_within_request_scope=true
```

Forbidden visibility fallbacks:

```text
import_received_at
 ingested_at
 committed_at
 harvest_business_date
 database_row_order
 latest_batch
 largest_revision_number
 lexical_hash
```

### 7.2 FINAL_ADJUDICATED

Final adjudication uses the complete selected committed source universe and requires a unique eligible finalized terminal.

```text
label_observation_cutoff_at=NULL
record_status=FINALIZED
finalized_at IS NOT NULL
finalized_at<=snapshot_executed_at
```

Final adjudication is not a substitute for historical point-in-time replay.

## 8. Lineage authority and winner eligibility

The lineage graph and record status have separate responsibilities:

```text
LINEAGE_GRAPH_ROLE_IS_TERMINAL_AUTHORITY=true
RECORD_STATUS_IS_WINNER_ELIGIBILITY_FILTER=true
I5_WINNER_SELECTION_IMPLEMENTED=false
I7_WINNER_SELECTION_REQUIRED=true
```

The graph determines whether a node is terminal. Status determines whether that terminal can become a winner.

No winner may be selected by latest timestamp, largest revision, database ID, import order, batch order, or arbitrary priority.

## 9. Status rules

### 9.1 ACTIVE

- may be an AS_OF winner when it is the unique visible terminal;
- may become non-terminal when a later explicit successor is visible;
- a committed parent is not mutated when a successor is added.

### 9.2 CORRECTED

`CORRECTED` is non-terminal and never a winner.

```text
CORRECTED_SUCCESSOR_COUNT=EXACTLY_ONE
CORRECTED_WITHOUT_SUCCESSOR=STRUCTURAL_FAILURE
CORRECTED_WITH_MULTIPLE_SUCCESSORS=STRUCTURAL_FAILURE
```

Allowed examples:

```text
CORRECTED -> CORRECTED -> ACTIVE
CORRECTED -> CORRECTED -> FINALIZED
CORRECTED -> VOID
```

### 9.3 FINALIZED

`FINALIZED` is terminal and final.

```text
FINALIZED_HAS_SUCCESSOR=STRUCTURAL_FAILURE
FINALIZED_REQUIRES_FINALIZED_AT=true
```

For AS_OF evaluation:

```text
record_status=FINALIZED
AND finalized_at<=label_observation_cutoff_at
=> FINALIZED winner eligible
```

For:

```text
record_status=FINALIZED
AND finalized_at>label_observation_cutoff_at
```

the record is not reinterpreted as `ACTIVE`.

```text
AS_OF_STATUS_NOT_VISIBLE_AT_CUTOFF=EXCLUSION
AS_OF_FINALIZED_AFTER_CUTOFF_DOWNGRADE_TO_ACTIVE=false
```

### 9.4 VOID

A terminal `VOID` may be a valid lineage-ending evidence node, but it never becomes a winner or label.

```text
TERMINAL_VOID_ALLOWED_AS_LINEAGE_END=true
TERMINAL_VOID_WINNER_ELIGIBLE=false
VOID_HAS_SUCCESSOR=STRUCTURAL_FAILURE
```

A terminal `VOID` produces a deterministic coverage exclusion.

## 10. Visible-chain invariants

For each:

```text
(source_system, external_logical_record_id)
```

I7 constructs the visible graph and requires:

- one explicit predecessor chain;
- every visible non-root node has its visible predecessor;
- logical-record identity is stable across the chain;
- revision numbers are continuous;
- each node has at most one successor;
- no cycle;
- no more than one visible terminal;
- `CORRECTED` has exactly one successor;
- `FINALIZED` and `VOID` have no successor.

Lineage corruption halts the complete snapshot. It is not downgraded to a coverage exclusion.

## 11. Frozen mapping authority

I7 must use mapping evidence bound to the winner's committed validation run.

Required mappings per winner:

```text
SEASON
FARM
SUBFARM
VARIETY
```

Required frozen evidence includes:

- stable resolved business key;
- stable parent business key when applicable;
- resolved master-record hash;
- mapping-policy version;
- season-resolver version;
- registry-entry hash where applicable;
- mapping-snapshot hash;
- resolved-identity-snapshot hash;
- registry-content hash.

```text
LIVE_MASTER_DATA_REMAPPING=false
FROZEN_VALIDATION_MAPPING_EVIDENCE_REQUIRED=true
```

Database IDs may be retained as foreign keys. They are not canonical identity authority and do not enter canonical hashes.

## 12. Revision-first aggregation

The processing order is fixed:

```text
committed source universe
-> cutoff-visible graph
-> unique eligible terminal per logical record
-> frozen mapping identities
-> canonical-grain grouping
-> exact Decimal SUM
```

Rules:

- multiple logical records may share one canonical grain;
- same grain is not a duplicate;
- explicit zero remains zero;
- a missing date remains missing and does not create a zero row;
- all sums use exact Decimal arithmetic;
- contributing winners use stable deterministic ordering;
- API, CSV, and XLSX records with identical canonical content aggregate identically.

Contributing-winner evidence is represented by normalized winner rows and an ordered winner-hash set. Unbounded opaque JSON is not canonical authority.

## 13. Snapshot request and idempotency

The snapshot idempotency namespace is independent from import-batch idempotency.

Required request fields include:

```text
snapshot_idempotency_key
source_system
visibility_mode
label_observation_cutoff_at_or_null
harvest_date_start
harvest_date_end
season_business_keys
farm_business_keys_or_empty_for_all
variety_business_keys_or_empty_for_all
snapshot_policy_version
winner_policy_version
aggregation_policy_version
```

Canonical lists are sorted and unique.

Persistence must enforce:

```text
UNIQUE(source_system, snapshot_idempotency_key)
```

Replay semantics:

```text
same key + same request identity hash
=> return original snapshot
=> zero write

same key + different request identity hash
=> deterministic idempotency conflict
```

A new idempotency key may create a refreshed snapshot against a newly observed source universe.

## 14. Snapshot identity and hashes

Required identity fields:

```text
snapshot_idempotency_key
label_snapshot_request_identity_hash
label_snapshot_instance_identity_hash
source_commit_manifest_set_hash
winner_manifest_hash
label_row_set_hash
exclusion_manifest_hash
label_snapshot_hash
```

### 14.1 Request identity

`label_snapshot_request_identity_hash` binds the canonical request and all policy versions.

### 14.2 Source universe

The source universe is the canonically ordered list of observed committed manifests.

```text
SNAPSHOT_SOURCE_MANIFEST_SET_IS_CANONICALLY_ORDERED=true
```

The list contains stable source identity and `commit_manifest_hash`; it does not use database row order.

### 14.3 Instance identity

`label_snapshot_instance_identity_hash` binds:

- request identity;
- database-authoritative `snapshot_executed_at`;
- canonically ordered source manifest set;
- source-universe hash.

### 14.4 Final snapshot hash

`label_snapshot_hash` binds:

- instance identity;
- ordered winner rows;
- ordered aggregated label rows;
- ordered exclusion rows;
- coverage counts;
- policy versions.

Canonical hashes exclude database-generated IDs, runtime hosts, processes, query order, temporary paths, and nondeterministic iteration.

## 15. Structural failures

The complete snapshot fails on:

```text
SOURCE_EVIDENCE_DRIFT
MAPPING_EVIDENCE_MISSING
MAPPING_EVIDENCE_DRIFT
MISSING_SUPERSEDED_PARENT
VISIBLE_CHILD_WITH_INVISIBLE_PARENT
SUPERSESSION_CHAIN_FORK
SUPERSESSION_CHAIN_CYCLE
REVISION_NUMBER_DISCONTINUITY
MULTIPLE_VISIBLE_TERMINAL_REVISIONS
CORRECTED_WITHOUT_SUCCESSOR
FINALIZED_HAS_SUCCESSOR
VOID_HAS_SUCCESSOR
FINALIZED_AT_REQUIRED
SOURCE_SYSTEM_SCOPE_CONFLICT
IDEMPOTENCY_CONFLICT
```

`CORRECTED_WITHOUT_SUCCESSOR` is the accepted I7 contract name. Existing I5 implementations may map the condition to the legacy `INVALID_RECORD_STATUS` code until implementation hardening is separately authorized.

## 16. Coverage exclusions

A snapshot may succeed while reporting:

```text
SOURCE_TIME_UNTRUSTED
SOURCE_TIME_MISSING
SOURCE_TIME_AFTER_CUTOFF
NO_VISIBLE_REVISION_AT_CUTOFF
TERMINAL_VOID
STATUS_NOT_VISIBLE_AT_CUTOFF
OUTSIDE_REQUEST_SCOPE
```

Evaluation order is frozen:

```text
OUTSIDE_REQUEST_SCOPE evaluated before visibility
STATUS_NOT_VISIBLE_AT_CUTOFF applies only to in-scope records
```

The two reasons are mutually exclusive for one record.

Every exclusion has one deterministic row hash. The ordered row hashes form `exclusion_manifest_hash`.

`TERMINAL_CORRECTED` is not a coverage exclusion. It is a structural lineage error.

## 17. Persistence boundary

I7 persistence contains exactly four logical tables:

```text
actual_harvest_label_snapshot
actual_harvest_label_snapshot_winner
actual_harvest_label_snapshot_label
actual_harvest_label_snapshot_exclusion
```

The future migration is based on:

```text
DOWN_REVISION=0020_actual_harvest_commit_manifest
```

All four tables require:

```text
UPDATE_FORBIDDEN=true
DELETE_FORBIDDEN=true
ON_DELETE_RESTRICT=true
DATABASE_IMMUTABILITY_GUARD=true
```

Creation is synchronous and atomic:

```text
SYNCHRONOUS_SINGLE_DATABASE_TRANSACTION=true
CALLER_OWNED_TRANSACTION=true
SINGLE_TRANSACTION_CREATION=true
PARTIAL_SNAPSHOT_FORBIDDEN=true
BACKGROUND_WORKER=false
ATTEMPT_LEDGER=false
LEASE=false
```

Header and all child rows are committed or rolled back together.

## 18. Reproducibility and concurrency

A snapshot records the exact ordered source-manifest set observed inside its database transaction.

A source commit concurrent with that transaction is either inside or outside the observed database snapshot; it must never produce a partially observed source universe.

Same request and same source universe reproduce the same canonical winner rows, label rows, exclusions, and hashes.

## 19. Acceptance-test contract

Future implementation acceptance must cover:

- parent visible before successor cutoff;
- successor visible after cutoff;
- no future-revision leakage;
- trusted source timestamp boundary equality;
- untrusted and missing source-time exclusions;
- missing visible predecessor failure;
- fork, cycle, discontinuity, and multiple-terminal failures;
- `CORRECTED` successor cardinality;
- `FINALIZED_HAS_SUCCESSOR` and `VOID_HAS_SUCCESSOR`;
- `FINALIZED_AT_REQUIRED`;
- terminal `VOID` exclusion;
- frozen mapping evidence despite later master-data changes;
- SUBFARM-only grain and plot rejection;
- multiple logical records in one grain;
- exact Decimal sum;
- explicit zero versus missing date;
- input-order independence;
- snapshot idempotent replay and conflict;
- source-manifest-set determinism;
- immutable UPDATE/DELETE rejection in PostgreSQL;
- injected persistence failures with complete rollback;
- concurrent identical snapshot creation with one physical result.

SQLite results do not substitute for PostgreSQL acceptance evidence.

## 20. Cross-document synchronized status

The accepted current status is:

```text
ACTUAL_HARVEST_COMMITTED_SOURCE_STATUS=IMPLEMENTED
PRIMARY_ACTUAL_HARVEST_LABEL_READY=false
PRIMARY_LABEL_BLOCKER=IMMUTABLE_LABEL_SNAPSHOT_NOT_IMPLEMENTED
ACTUAL_LABEL_CANONICAL_GRAIN=SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_HARVEST_BUSINESS_DATE
ACTUAL_LABEL_UNIT=KG
PLOT_SUPPORTED=false
LABEL_OBSERVATION_CUTOFF_MODEL=ACCEPTED_DESIGN_NOT_IMPLEMENTED
LABEL_REVISION_POLICY=EXPLICIT_UNIQUE_TERMINAL_FAIL_CLOSED
I5_LINEAGE_CONTRACT_HARDENING_ACCEPTED=true
I7_DESIGN_CONTRACT_FREEZE_ACCEPTED=true
Q2A_I7_CONTRACT_STATUS=ACCEPTED
Q2A_I7_IMPLEMENTATION_READY=CONTRACT_READY_NOT_AUTHORIZED
```

Prediction-label alignment remains blocked by the missing immutable label snapshot and forecast-binding implementation, not by the absence of a committed actual-harvest source.

## 21. Governance

This document sync is docs-only.

```text
REPOSITORY_DOCS_UPDATED=true
V0_2_S2_I7_CONTRACT_ACCEPTED=true
V0_2_S2_IMPLEMENTATION_AUTHORIZED=false
BACKTEST_AUTHORIZED=false
MODEL_CHANGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

This contract does not authorize branch creation for implementation, worktree creation, migration implementation, production code, tests, push of implementation code, implementation PR creation, Ready transition, merge, backtest, S3, S4, or S5.

## 22. Change log

- **v1.0 — 2026-07-20:** accepted I7 contract synchronized against `main@91249fbfed8d8c250d79b495236b15374bac667d`; supersedes stale source-status, `_OR_PLOT` grain, lineage/status, snapshot-identity, and alignment-blocker statements in earlier Q2A design documents. Implementation remains unauthorized.
