# S1 Visibility, Inclusion, and Revision Contract

## Authority and current state

Historical labels must be reconstructed at the requested observation cutoff,
not from the current database state. This document binds to the accepted Q2A/I7
visibility and winner contract and does not implement it.

```text
VISIBILITY_AUTHORITY=docs/forecast-quality/q2a-i7-label-snapshot-and-revision-winner-contract.md
CURRENT_SOURCE_POINT_IN_TIME_ELIGIBLE=false
CURRENT_LABEL_SNAPSHOT_CONTRACT_STATUS=BLOCKED
CURRENT_REVISION_WINNER_RULE_STATUS=BLOCKED
CURRENT_INCLUSION_POLICY_STATUS=BLOCKED
```

## Canonical time order

The following relation is mandatory for a historical replay:

```text
forecast_cutoff_at < forecast_target_date_or_window_end
<= label_observation_cutoff_at <= replay_executed_at
```

`source_recorded_at` is the trusted business visibility time. Import receipt,
ingestion time, database commit time, harvest date alone, and row order cannot
replace it. The source-recorded-time authority and timezone must be fixed in
the business attestation and source manifest.

## Visibility modes

| Mode | Required state | Winner rule | Current status |
| --- | --- | --- | --- |
| `AS_OF_EVALUATION` | Committed source batch, manifest present, source-system scope matches, trusted source time is non-null and at or before the cutoff. | Eligible visible revision with a valid lineage terminal. | `BLOCKED` |
| `FINAL_ADJUDICATED` | Finalized record and `finalized_at` at or before snapshot execution. | Finalized winner under the same lineage and scope rules. | `BLOCKED` |

The mode, cutoff, source universe, mapping manifest, and execution timestamp are
part of the immutable snapshot request identity.

## Revision graph and winner rules

The source record identity and lineage graph are authoritative. The following
rules are fixed by Q2A/I7:

- `CORRECTED` records are non-terminal and must have exactly one valid
  successor;
- `FINALIZED` and `VOID` records cannot have a successor;
- `VOID` is never a winner;
- a visible child whose parent is not visible is a structural failure;
- a fork, cycle, discontinuity, missing parent, or multiple visible terminal
  revisions is a structural failure;
- a finalized record requires `finalized_at` at the required boundary;
- one source family is used per snapshot; no source-priority merge or
  cross-source aggregation is allowed.

Relevant structural reason codes are preserved exactly:

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
UNSUPPORTED_LABEL_GRAIN
```

## Inclusion and exclusion

The evaluation first checks request scope and frozen mapping evidence, then
visibility, then lineage and winner eligibility. Missing or excluded data is
not silently imputed as zero.

Allowed exclusion reason codes include:

```text
SOURCE_TIME_UNTRUSTED
SOURCE_TIME_MISSING
SOURCE_TIME_AFTER_CUTOFF
NO_VISIBLE_REVISION_AT_CUTOFF
TERMINAL_VOID
STATUS_NOT_VISIBLE_AT_CUTOFF
OUTSIDE_REQUEST_SCOPE
```

Partial mapping evidence is a structural failure (`MAPPING_EVIDENCE_MISSING`),
not an ordinary coverage exclusion. Unsupported grain is a structural failure,
not a coercion opportunity.

Missing business dates are reported as unknown and remain missing. The
`UNKNOWN_NOT_ZERO` rule applies to all label and coverage calculations.

## Snapshot identity and replay

An immutable label snapshot must persist, at minimum:

```text
snapshot_request_identity
source_commit_manifest_set
frozen_mapping_manifest
winner_manifest
label_row_set_identity
exclusion_manifest
snapshot_hash
```

The same request and source universe must produce the same identities and
hashes. A different request, source universe, mapping version, or revision
graph must not reuse the previous snapshot identity. Persistence is atomic; a
partial snapshot is invalid.

## Acceptance requirements

```text
S1_ACCEPTANCE_REQUIRES_TRUSTED_SOURCE_RECORDED_TIME=true
S1_ACCEPTANCE_REQUIRES_FROZEN_MAPPING_EVIDENCE=true
S1_ACCEPTANCE_REQUIRES_REVISION_GRAPH_VALIDATION=true
S1_ACCEPTANCE_REQUIRES_EXPLICIT_EXCLUSION_MANIFEST=true
S1_ACCEPTANCE_REQUIRES_IMMUTABLE_SNAPSHOT_HASH=true
S1_ACCEPTANCE_REQUIRES_IDEMPOTENT_REPLAY=true
S1_ACCEPTANCE_REQUIRES_NO_CURRENT_STATE_FALLBACK=true
```

Until the source authority and cohort manifest are accepted, the current
visibility and winner statuses remain `BLOCKED`.
