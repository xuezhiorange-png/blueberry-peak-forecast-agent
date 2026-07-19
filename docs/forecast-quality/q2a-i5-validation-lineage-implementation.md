# Q2A-I5 exact mapping and revision lineage validation

## Scope

This slice is based on `7e65b9c89e9b881b3ff18e958bda6056d8a3ce45` and uses
branch `codex/issue-102-q2a-i5-validation-lineage`. It owns the validation
boundary only:

- `POST /api/v1/actual-harvest/imports/{import_id}/validate`;
- `GET /api/v1/actual-harvest/imports/{import_id}/errors`;
- validation summary fields on preview;
- cancellation from `VALIDATED` and `VALIDATION_FAILED`.

Q2A-I4 remains the owner of create, append, get, preview base behavior, seal,
and the original cancel behavior. I5 does not implement commit, atomic source
activation, winner selection, aggregation, active labels, cutoff snapshots,
backtesting, identity creation, or model behavior.

## State and identity

The state transitions are:

```text
SEALED -> VALIDATING -> VALIDATED
SEALED -> VALIDATING -> VALIDATION_FAILED
VALIDATED -> VALIDATING       (only after committed-basis drift)
VALIDATION_FAILED -> VALIDATING (only after committed-basis drift)
VALIDATED -> CANCELLED
VALIDATION_FAILED -> CANCELLED
```

`VALIDATING` cannot be cancelled. `COMMITTING` and `COMMITTED` cannot be
cancelled. A validation request identity is
`(import_id, seal_manifest_hash, mapping_policy_version,
validation_policy_version, season_resolver_version)`. An immutable validation
instance adds the `committed_lineage_basis_hash` and the same resolver version.
A batch has at most one current instance; older instances remain evidence and
are superseded, not overwritten.

Validation attempts carry a generation, fencing token, heartbeat and lease.
Stale reclaim locks the batch and run, abandons the old attempt, increments the
generation, creates a new token, and commits before work starts. Final evidence
requires the active attempt, unexpired lease, `VALIDATING` batch, unchanged seal,
registry hash, record manifest, and committed basis. Drift returns the batch to
`SEALED` without final evidence and requires a new validation. Long record
processing renews the lease every 100 records in addition to the stage-boundary
renewals.

## Mapping authority

The registry is the only source-code authority. It is append-only and changes
through an internal controlled master-data operation, never through the
actual-harvest HTTP API. Registry versions move `DRAFT -> SEALED`; sealing
locks the version and records entry count plus `registry_content_hash`.
Validation requires a sealed registry and exact `mapping_policy_version`.

Registry entries explicitly identify source field, source code, target type and
stable target business key. Display names are not inferred as source codes.
I5 v1 is `SUBFARM_ONLY_PLOT_REJECTED`; plot input cannot be silently mapped to a
subfarm. Farm, subfarm, variety and season targets are resolved by exact,
case-sensitive business keys against existing master data. Missing season codes
use the farm-local harvest date against an inclusive season range and require
exactly one candidate. Hashes use stable business values, never database IDs.

The resolver policy is the code constant
`ACTUAL_HARVEST_SEASON_RESOLVER_VERSION = actual-harvest-season-resolver-v1`.
It is persisted on the validation run, mapping snapshot, result and every
season resolution evidence row. Each mapped current-batch record stores one
immutable evidence row per source field for `SEASON`, `FARM`, `SUBFARM` and
`VARIETY`. Evidence includes the registry entry hash, target type, stable target
and parent identity, a resolved master record hash, and a restricted foreign key
to the resolved `dim_*` row. `resolved_identity_snapshot_hash` excludes those
database IDs and includes the resolver version. It is bound into the mapping
snapshot, validation result and current validation run. Changing the resolver
version creates a new request and instance identity; an old result is not
replayed under a new version.

The 0019 migration adds database guards as well as service checks: a sealed
registry and its entries reject direct update, delete and insert operations.

Each validation stores an immutable mapping snapshot and its deterministic hash.
Registry hash drift, a missing version, an unsealed registry, unknown mapping,
ambiguous mapping, or unsupported target type fails closed.

## Lineage authority and validation order

The authority universe is the current sealed batch plus committed source
revision history for the same source system and logical-record identities.
Other uncommitted batches are not read or locked. History is referenced by
stable business identity and canonical hash; it is never copied or mutated.

The deterministic validation order is:

1. sealed-batch completeness;
2. canonical field and source-semantics validation;
3. quantity, date, timezone and source-time authority validation;
4. exact farm/subfarm/variety/season mapping;
5. canonical-grain validation;
6. revision lineage graph validation;
7. point-in-time metadata eligibility checks without cutoff winner selection;
8. hash/idempotency validation;
9. batch result validation.

Lineage validates logical and revision keys, predecessor continuity, missing
predecessors, logical-record mismatches, duplicate/conflicting revision
identity, multiple successors, cycles, status legality, corrected records
without successors, and terminal uniqueness. I5 does not choose a cutoff winner
or aggregate a grain.

`committed_lineage_basis_hash` binds the ordered committed history, canonical
revision hashes, predecessor edges, status, revision number, source-time
authority metadata, source provenance and authority policy. It excludes
database IDs, runtime values, query order, attempt identity and fencing data.

`validation_result_hash` binds the seal, mapping snapshot, resolved-identity
snapshot, resolver version, policy versions, and ordered tuples of
`(source_system, external_logical_record_id, revision_number,
external_revision_id, canonical_record_hash)`, plus mapping outcomes, ordered
lineage nodes and edges, errors/warnings/counts, committed basis and lineage
graph. It excludes cutoff, winner, aggregation, runtime, database IDs and
pagination values. Reassociating a record hash with another stable record key
changes the result hash.

## Evidence schema

Migration `0019_actual_harvest_validation_evidence` adds exactly:

- `actual_harvest_mapping_policy_registry`;
- `actual_harvest_mapping_registry_entry`;
- `actual_harvest_mapping_snapshot`;
- `actual_harvest_validation_run`;
- `actual_harvest_validation_attempt`;
- `actual_harvest_validation_result`;
- `actual_harvest_validation_record`;
- `actual_harvest_validation_mapping_evidence`;
- `actual_harvest_validation_error`;
- `actual_harvest_validation_lineage_node`;
- `actual_harvest_validation_lineage_edge`;
- `actual_harvest_validation_lineage_basis`;
- `actual_harvest_validation_lineage_basis_member`.

All evidence foreign keys use `ON DELETE RESTRICT`. No aggregation,
commit-activation, active-label, or cutoff-snapshot table is introduced.

Errors use stable code, severity, record index, logical/revision identity,
field path, message template ID and bounded sanitized details. The errors
endpoint uses deterministic keyset pagination bound to validation instance
identity. Responses never expose raw rows, SQL, traceback, credentials or
database IDs.

## HTTP behavior

Validate accepts only `{}` with `application/json`, and errors uses bounded
keyset pagination. Preview adds validation status, validation instance/result
hashes, mapping snapshot hash, committed basis hash and counts. It does not
return cutoff winners, aggregation, contributing winner manifests or labels.
Cancel from `VALIDATED` or `VALIDATION_FAILED` preserves seal, mapping,
validation, error, lineage and basis evidence. `CANCELLED` is not active data.

## Tests and exclusions

The I5 test set covers the restored I1 contract suite, registry sealing and
rejection, exact mapping, deterministic season resolution, resolved identity
evidence, replay, lineage errors, validation error pagination, preview summary,
cancellation evidence preservation, elapsed lease renewal and stale-attempt
fencing. The following PostgreSQL node IDs are assigned to the existing
`postgres-domain-1` shard. Their pass/fail status is established only by the
exact-head CI artifact, not by local SQLite execution:

- `test_postgres_i5_identical_validate_replays_immutable_result`;
- `test_postgres_i5_validate_cancel_race_has_one_serialized_outcome`;
- `test_postgres_i5_cancel_validated_preserves_validation_evidence`;
- `test_postgres_i5_validation_failed_cancel_preserves_all_evidence`;
- `test_postgres_i5_heartbeat_renewal_and_expired_attempt_cannot_finalize`;
- `test_postgres_i5_old_worker_cannot_demote_new_attempt_state`;
- `test_postgres_i5_committed_history_predecessor_is_in_validation_basis`;
- `test_postgres_i5_uncommitted_batch_is_excluded_from_lineage_basis`;
- `test_postgres_i5_registry_seal_and_validate_are_serialized`;
- `test_postgres_i5_lineage_rejection_matrix[missing_predecessor-REVISION_PREDECESSOR_MISSING]`;
- `test_postgres_i5_lineage_rejection_matrix[validated_predecessor-REVISION_PREDECESSOR_MISSING]`;
- `test_postgres_i5_lineage_rejection_matrix[cancelled_predecessor-REVISION_PREDECESSOR_MISSING]`;
- `test_postgres_i5_lineage_rejection_matrix[duplicate_revision_number-REVISION_NUMBER_CONFLICT]`;
- `test_postgres_i5_lineage_rejection_matrix[revision_number_discontinuity-REVISION_NUMBER_CONFLICT]`;
- `test_postgres_i5_lineage_rejection_matrix[multiple_successors-REVISION_MULTIPLE_SUCCESSORS]`;
- `test_postgres_i5_lineage_rejection_matrix[lineage_cycle-REVISION_LINEAGE_CYCLE]`;
- `test_postgres_i5_lineage_rejection_matrix[logical_record_mismatch-REVISION_LOGICAL_RECORD_MISMATCH]`;
- `test_postgres_i5_lineage_rejection_matrix[multiple_structural_terminals-MULTIPLE_TERMINAL_REVISIONS]`;
- `test_postgres_i5_lineage_rejection_matrix[multiple_finalized_terminals-MULTIPLE_TERMINAL_REVISIONS]`;
- `test_postgres_i5_lineage_rejection_matrix[corrected_without_successor-INVALID_RECORD_STATUS]`;
- `test_postgres_i5_same_revision_identity_different_payload_is_rejected_atomically`;
- `test_postgres_i5_validation_errors_use_bounded_keyset_pagination`;
- `test_postgres_i5_error_pagination_is_bounded_ordered_and_instance_bound`;
- `test_postgres_i5_0019_catalog_and_registry_contract_is_exact`;
- `test_postgres_i5_attempt_fencing_and_drift_matrix[wrong_fencing_token_cannot_finalize]`;
- `test_postgres_i5_attempt_fencing_and_drift_matrix[wrong_attempt_generation_cannot_finalize]`;
- `test_postgres_i5_attempt_fencing_and_drift_matrix[expired_attempt_cannot_finalize_without_reclaim]`;
- `test_postgres_i5_attempt_fencing_and_drift_matrix[committed_basis_drift_rejects_finalization]`;
- `test_postgres_i5_attempt_fencing_and_drift_matrix[registry_hash_drift_rejects_finalization]`;
- `test_postgres_i5_attempt_fencing_and_drift_matrix[record_manifest_drift_rejects_finalization]`;
- `test_postgres_i5_attempt_fencing_and_drift_matrix[seal_manifest_drift_rejects_finalization]`;
- `test_postgres_i5_injected_finalization_failure_writes_no_partial_evidence`.
- `test_postgres_i5_injected_evidence_failure_rolls_back_all_evidence[mapping]`;
- `test_postgres_i5_injected_evidence_failure_rolls_back_all_evidence[lineage]`.
- `test_postgres_i5_draft_registry_is_rejected`;
- `test_postgres_i5_sealed_registry_entry_mutation_is_rejected`.

Existing I1-I4, core, agent and Alembic tests remain regression gates. Local
PostgreSQL status is reported separately and is never inferred from SQLite.

## Local verification

The local verification commands are:

- `uv lock --check`: passed;
- Ruff check and format check: passed;
- `uv run mypy app`: passed;
- `uv run pytest tests/actual_harvest_import -q`;
- core forecast and V0.1-S1 contract regressions;
- agent regression;
- API/lifespan and actual-harvest routes;
- Alembic contract regression;
- local PostgreSQL: not run when Docker is unavailable.

The exact-head PR CI is the acceptance source for PostgreSQL execution. Its
run ID, JUnit counts, node IDs and artifact digests are recorded in the PR
body after the final Head completes; no local SQLite result is represented as
PostgreSQL evidence.

## Exact-head CI evidence procedure

The final verification order is:

```text
code_tests_docs_commit
-> push
-> exact_head_ci
-> verify_artifacts
-> update_pr_body_only
-> no_further_git_commit
```

Authoritative exact-head CI evidence is recorded in the PR body
and exact-head formal review comment after the final code commit.
It is intentionally not embedded in this tracked document because
updating the document changes the reviewed commit.

The final PR body records the exact Head, CI run, JUnit totals, PostgreSQL
node IDs, artifact IDs and digests only after that exact-head run completes.

Hard exclusions are Q2A-I6 atomic commit, Q2A-I7 cutoff winner/aggregation/
label snapshot, Q2A-I8 integration acceptance, Q2B, Q3, TASK-013 Slice C C2,
spreadsheet orchestration, public mapping-admin API, frontend and model code.
