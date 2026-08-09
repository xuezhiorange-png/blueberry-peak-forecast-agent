# V0.3-S1 Actual-Harvest Label Lifecycle and Point-in-Time Authority Preparation

## Preparation identity and boundary

```text
PREPARATION_ID=V0_3_S1_ACTUAL_HARVEST_LABEL_LIFECYCLE_AND_PTI_AUTHORITY_PREPARATION
BASELINE_MAIN_SHA=eb930cd710bcd696fd45c7c1f16041461d55dfbb
SOURCE_CLASS=ACTUAL_HARVEST_LABEL
SOURCE_SYSTEM=扫码称重系统
SOURCE_DATASET=田间商品果每日采摘净重汇总
DOCUMENT_STATUS=PREPARATION_ONLY_PENDING_EXTERNAL_EVIDENCE_AND_INDEPENDENT_REVIEW

REAL_SOURCE_EXPORT_READ_THIS_TASK=false
REAL_BUSINESS_ROW_LEVEL_DATA_READ_THIS_TASK=false
EXTERNAL_SOURCE_SYSTEM_ACCESSED_THIS_TASK=false
DATABASE_MUTATION_THIS_TASK=false
S2_STARTED=false
BACKTEST_STARTED=false
```

This workpaper prepares the actual-harvest-label lifecycle authority only. It
does not implement a new lifecycle, issue an attestation, freeze a cohort, or
close the complete S1 visibility gate. `AREA`, `YIELD_PLAN`, `PHENOLOGY`,
`WEATHER_OBSERVATION`, `HISTORICAL_WEATHER_FORECAST`, `PICKER_COUNT`,
`HARVEST_EFFICIENCY`, and `MARKETABLE_RATE` remain outside this package.

The governing contracts are:

- `docs/forecast-quality/q2a-i7-label-snapshot-and-revision-winner-contract.md`;
- `docs/v0-3/s1/visibility-inclusion-revision-contract.md`;
- `docs/v0-3/s1/source-authority-and-cohort-manifest.md`.

Q2A/I7 is authority for source-recorded-time visibility, lineage terminal
selection, status eligibility, and revision-first aggregation. This document
does not create a second winner algorithm.

## Reused business-rule evidence

The following merged business facts are reused without asking the business
owner to repeat them:

```text
FINAL_CONFIRMATION_EVENT=扫码称重完成
FINAL_CONFIRMATION_TIMING=IMMEDIATE
BUSINESS_RULE_POST_CONFIRMATION_MODIFICATION_ALLOWED=false
BUSINESS_RULE_POST_CONFIRMATION_DELETION_ALLOWED=false
BUSINESS_RULE_CORRECTION_AFTER_CONFIRMATION_SUPPORTED=false
BUSINESS_RULE_VOID_AFTER_CONFIRMATION_SUPPORTED=false
BUSINESS_REPORTED_LATE_ENTRY_SCENARIO=NOT_APPLICABLE
```

These are business statements. They do not prove that the source system has no
administrator path, no technical correction path, no historical mutation, or
no late-entry capability. They also do not prove that historical visibility
can be reconstructed.

The business immutability statement is therefore prepared as a candidate
record-level rule:

```text
ACTUAL_HARVEST_BUSINESS_POST_CONFIRMATION_IMMUTABILITY_RULE=ADVANCED_CANDIDATE
FORMAL_CORRECTION_POLICY=ADVANCED_CANDIDATE_PENDING_SOURCE_SYSTEM_EVIDENCE
FORMAL_VOID_POLICY=ADVANCED_CANDIDATE_PENDING_SOURCE_SYSTEM_EVIDENCE
```

## Three-layer evidence separation

| Layer | What is available | What it can prove | What it cannot prove |
| --- | --- | --- | --- |
| `BUSINESS_RULE_EVIDENCE` | Immediate confirmation and post-confirmation business prohibitions listed above | Intended business meaning and policy direction | Source-system fields, technical capabilities, database permissions, or historical replayability |
| `REPOSITORY_IMPORT_LAYER_EVIDENCE` | Import staging, validation evidence, committed manifests, lineage tables, and I7 snapshot tables in current main | The shapes, constraints, validation rules, and fail-closed behavior implemented for repository-managed committed records | That the external scan-and-weigh system produces or preserves the same fields |
| `EXTERNAL_SOURCE_SYSTEM_EVIDENCE` | No independent scan-system technical evidence is present in the repository or supplied in this task | Not yet available | Source-record identity, source times, status transitions, correction/void behavior, and late-entry behavior |

Repository implementation evidence is documented below only as repository
capability. It must not be relabeled as external source-system support.

## Source 002 export boundary

Previously accepted Source 002 evidence observed the following headers only:

```text
时间,链路,农场,分场,品种,果径,入库公斤数
```

This supports the previously recorded business-date, farm, subfarm, variety,
chain-provenance, fruit-size aggregation, and quantity facts. It does not
evidence any of the following lifecycle fields:

```text
SOURCE_RECORD_ID
SOURCE_RECORDED_AT
SOURCE_AVAILABLE_AT
SOURCE_REVISED_AT
SOURCE_FINALIZED_AT
SOURCE_CANCELLED_AT
REVISION_NUMBER
SUPERSEDED_PARENT
RECORD_STATUS
```

All of the lifecycle fields above remain:

```text
SOURCE_002_LIFECYCLE_FIELDS_STATUS=NOT_EVIDENCED_FROM_SOURCE_002
```

No source file, row, record ID, farm name, timestamp, or external system was
read in this preparation task.

## Repository technical capability crosswalk

The current repository contains the following relevant implementation
surfaces:

- `backend/alembic/versions/0018_actual_harvest_import_staging.py` and
  `backend/app/actual_harvest_import/models.py` persist
  `external_logical_record_id`, `external_revision_id`, `source_recorded_at`,
  its authority status, `revision_number`, `record_status`,
  `supersedes_external_revision_id`, `revised_at`, and `finalized_at`.
- `backend/alembic/versions/0019_actual_harvest_validation_evidence.py` and
  `backend/app/actual_harvest_import/validation_models.py` persist mapping,
  validation, lineage nodes, lineage edges, and immutable lineage-basis
  members.
- `backend/alembic/versions/0020_actual_harvest_commit_manifest.py` and
  `backend/app/actual_harvest_import/commit_models.py` bind committed batches
  to validation, mapping, lineage, and source evidence hashes and reject
  mutation after sealing/commit.
- `backend/alembic/versions/0021_actual_harvest_label_snapshot.py` and
  `backend/app/actual_harvest_labels/` provide the four-table immutable I7
  snapshot shape and cutoff/winner service path for committed repository
  records.
- `backend/tests/actual_harvest_import/test_i7_label_snapshot.py` and
  `test_i7_label_snapshot_postgres.py` exercise cutoff equality, trusted
  source-time requirements, lineage failures, terminal status rules,
  finalization timing, immutable persistence, and replay behavior.

The repository has no `source_available_at`, `source_cancelled_at`, or
`source_record_id` field in the actual-harvest import path. Batch
`CANCELLED` is an import-batch lifecycle state and is not evidence that an
individual source record was voided. A `VOID` record status and lineage rule
exist, but external source-system production of that status and its event time
are not evidenced here.

## Actual-label lifecycle policy candidates

These identities are candidates for a future versioned policy package. They
are not accepted policy identities in this preparation:

```text
ACTUAL_HARVEST_LIFECYCLE_POLICY_VERSION=v0.3-s1-actual-harvest-lifecycle-v1
ACTUAL_HARVEST_REVISION_POLICY_VERSION=v0.3-s1-actual-harvest-revision-v1
ACTUAL_HARVEST_VISIBILITY_POLICY_VERSION=v0.3-s1-actual-harvest-visibility-v1
CANDIDATE_POLICY_VERSION_STATUS=PENDING_EXTERNAL_EVIDENCE_AND_INDEPENDENT_REVIEW
FORMAL_REVISION_POLICY_ACCEPTED=false
VISIBILITY_POLICY_ACCEPTED=false
```

The candidates preserve the existing authority:

1. A source record must have a stable source identity and an explicit logical
   revision identity; repository surrogate IDs are not source authority.
2. `AS_OF_EVALUATION` requires a trusted, non-null
   `source_recorded_at <= label_observation_cutoff_at`. It cannot fall back to
   `harvest_business_date`, `import_received_at`, `ingested_at`,
   `committed_at`, database order, or the latest row.
3. `FINAL_ADJUDICATED` additionally requires a finalized terminal and a
   non-null `finalized_at <= snapshot_executed_at`.
4. `CORRECTED` is non-terminal and requires exactly one successor;
   `FINALIZED` and `VOID` cannot have successors; `VOID` is never a winner.
5. Revision numbers, predecessor links, source-system scope, and lineage
   terminal uniqueness are structural evidence, not sorting heuristics.
6. A source-system policy-null value is not an automatic pass for an absent
   time or status field. The policy must explicitly authorize the null case.

`WITHDRAWAL_POLICY_VERSION`, `VOID_PROPAGATION_POLICY_VERSION`, and the
source-object withdrawal rule remain custody-level concerns. They must not be
closed by a record-level correction or void statement.

## Technical crosswalk

| Requirement | Q2A/I7 requirement | Business-rule evidence status | Repository implementation status | External source-system evidence status | Source 002 export support | Formalization status | Block reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SOURCE_RECORD_IDENTITY` | Stable source logical identity and revision identity | Not supplied as a business rule | Partial: `external_logical_record_id` + `external_revision_id` | Missing | Not present | Blocked | No external identity field or source-system binding |
| `SOURCE_RECORDED_AT` | Trusted, non-null source-recorded time for AS_OF | Not supplied | Implemented as optional field plus authority-status validation | Missing | Not present | Blocked | No source-system timestamp evidence |
| `SOURCE_AVAILABLE_AT` | Required by source policy or explicitly policy-null | Not supplied | Not implemented in actual-harvest import/label models | Missing | Not present | Blocked | No availability-time field or approved policy-null rule |
| `SOURCE_REVISED_AT` | Revision visibility must be reconstructable | Business correction is disallowed after confirmation | Optional `revised_at` field exists | Missing | Not present | Advanced candidate | External revision event semantics are unknown |
| `SOURCE_FINALIZED_AT` | Required for FINAL_ADJUDICATED | Confirmation is immediate, but no formal finalization evidence | `finalized_at` is persisted and used by I7 final mode | Missing | Not present | Blocked | Repository shape cannot prove source-system finalization |
| `SOURCE_CANCELLED_AT` | Cancellation/void event must be reconstructable | Business void is disallowed after confirmation | No cancellation timestamp; `VOID` status exists | Missing | Not present | Blocked | No event-time field or policy-null authority |
| `RECORD_STATUS` | Status filters winner eligibility | Business post-confirmation rules are confirmed | `ACTIVE/CORRECTED/VOID/FINALIZED` enum and lineage validation exist | Missing | Not present | Advanced candidate | External status production and history are unproven |
| `REVISION_NUMBER` | Continuous revision identity in each logical chain | Not supplied | Positive, unique, and lineage-validated | Missing | Not present | Advanced candidate | Source system has not evidenced numbering |
| `SUPERSEDED_PARENT` | Explicit predecessor link for each successor | Not supplied | `supersedes_external_revision_id` and lineage edges exist | Missing | Not present | Advanced candidate | Source system has not evidenced parent links |
| `LINEAGE_TERMINAL_RULE` | One valid visible terminal; no fork/cycle/discontinuity | Not supplied | Implemented and tested in I5/I7 validation/snapshot services | Missing | Not present | Advanced candidate | External source lineage remains unbound |
| `CORRECTION_RULE` | Correction is a lineage event, never silent replacement | Business correction unsupported after confirmation | `CORRECTED` structural rules exist | Missing | Not present | Advanced candidate | Technical correction capability and event lineage unknown |
| `VOID_RULE` | Terminal void is excluded and never a winner | Business void unsupported after confirmation | `VOID` terminal and successor rejection exist | Missing | Not present | Advanced candidate | Source-system void semantics and timing unknown |
| `LATE_ENTRY_RULE` | Late records use source-recorded visibility, not business date | Business scenario marked `NOT_APPLICABLE` | Source-time validation exists; no source capability proof | Missing | Only business date is present | Blocked | Technical late-entry behavior is not evidenced |
| `FINALIZATION_RULE` | Final mode requires a finalized terminal and finalized time | Confirmation event/timing is business-confirmed | I7 final eligibility uses `finalized_at` | Missing | Not present | Blocked | Immediate confirmation is not finalized-time evidence |
| `AS_OF_VISIBILITY` | Source-recorded time must be visible at label cutoff | Not supplied | Cutoff predicate and exclusions are implemented/tested | Missing | Not present | Blocked | No trusted Source 002 recorded-time field |
| `FINAL_ADJUDICATED_VISIBILITY` | Source-recorded and finalized times bound to snapshot execution | Not supplied | Finalized-time predicate is implemented/tested | Missing | Not present | Blocked | No Source 002 finalized-time evidence |
| `REVISION_WINNER_COMPATIBILITY` | Q2A/I7 explicit unique terminal winner | Business rules do not select winners | Repository winner path is compatible for committed records | Missing | Not present | Advanced, not closed | External source identity/time/lineage remains missing |

## Eligibility and lifecycle status

```text
ACTUAL_LABEL_AS_OF_EVALUATION_ELIGIBILITY=BLOCKED
ACTUAL_LABEL_FINAL_ADJUDICATED_ELIGIBILITY=BLOCKED
ACTUAL_LABEL_REVISION_WINNER_COMPATIBILITY=ADVANCED_REPOSITORY_ONLY_BLOCKED_EXTERNAL_EVIDENCE

RECORD_LEVEL_CORRECTION_POLICY_STATUS=ADVANCED_CANDIDATE_PENDING_EXTERNAL_EVIDENCE
RECORD_LEVEL_VOID_POLICY_STATUS=ADVANCED_CANDIDATE_PENDING_EXTERNAL_EVIDENCE
SOURCE_OBJECT_WITHDRAWAL_POLICY_STATUS=BLOCKED_PENDING_CUSTODY_POLICY

ACTUAL_LABEL_VISIBILITY_CLOSED=false
S1_VISIBILITY_GATE_CLOSED=false
S1_VISIBILITY_FULL_CLOSURE_NOT_CLAIMED=true
```

`FINAL_CONFIRMATION_TIMING=IMMEDIATE` must not be used as
`SOURCE_FINALIZED_AT`, and `HARVEST_BUSINESS_DATE` must not be used as
`SOURCE_RECORDED_AT` or `SOURCE_AVAILABLE_AT`.

## Formalization progress without false closure

The following gaps are advanced only to candidate-policy/preparation status:

```text
FORMALIZATION_GAPS_ADVANCED=
FORMAL_CORRECTION_POLICY,
FORMAL_VOID_POLICY,
FORMAL_REVISION_POLICY,
REVISION_POLICY_VERSION,
POINT_IN_TIME_VISIBILITY_RULE,
LATE_ENTRY_RULE,
FINAL_CONFIRMATION_FORMAL_EVIDENCE,
REVISION_WINNER_COMPATIBILITY

FORMALIZATION_GAPS_CLOSED=NONE
FROZEN_MATRIX_GAP_COUNT=21
EFFECTIVE_REMAINING_S1_GAP_COUNT=26
CANONICAL_S1_GATE_COUNT=17
```

The count `26` remains a working inventory and is not the canonical gate
count. No source authority, cohort, Q2C, S1, or S2 state is promoted by this
preparation.

## Governance state

```text
FORMAL_ATTESTATION_CREATED=false
FORMAL_COHORT_MANIFEST_CREATED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
V0_3_S1_ACCEPTANCE_STATUS=BLOCKED
PHYSICALLY_ALIGNED_BACKTEST_ALLOWED=false
MODEL_QUALITY_CLAIM_ALLOWED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

The minimum external capability questions are recorded separately in
`actual-harvest-label-source-system-evidence-request.md`. This package does
not ask for source rows, record IDs, farm names, timestamps, or a new source
export.
