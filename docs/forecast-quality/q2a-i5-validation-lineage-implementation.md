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
validation_policy_version)`. An immutable validation instance adds the
`committed_lineage_basis_hash`. A batch has at most one current instance;
older instances remain evidence and are superseded, not overwritten.

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

The resolver policy is
`actual-harvest-season-resolver-v1`. Each mapped current-batch record stores
one immutable evidence row per source field for `SEASON`, `FARM`, `SUBFARM` and
`VARIETY`. Evidence includes the registry entry hash, target type, stable target
and parent identity, a resolved master record hash, and a restricted foreign key
to the resolved `dim_*` row. `resolved_identity_snapshot_hash` excludes those
database IDs and is bound into the mapping snapshot, validation result and
current validation run.

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
snapshot, policy versions, and ordered tuples of
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
fencing. The following PostgreSQL nodes are assigned to the existing
`postgres-domain-1` shard and are not claimed as locally passed:

- `test_postgres_i5_identical_validate_replays_immutable_result`;
- `test_postgres_i5_validate_cancel_race_has_one_serialized_outcome`;
- `test_postgres_i5_cancel_validated_preserves_validation_evidence`;
- `test_postgres_i5_validation_failed_cancel_preserves_all_evidence`;
- `test_postgres_i5_heartbeat_renewal_and_expired_attempt_cannot_finalize`;
- `test_postgres_i5_old_worker_cannot_demote_new_attempt_state`;
- `test_postgres_i5_committed_history_predecessor_is_in_validation_basis`;
- `test_postgres_i5_uncommitted_batch_is_excluded_from_lineage_basis`;
- `test_postgres_i5_validation_errors_use_bounded_keyset_pagination`;
- `test_postgres_i5_draft_registry_is_rejected`;
- `test_postgres_i5_sealed_registry_entry_mutation_is_rejected`.

Existing I1-I4, core, agent and Alembic tests remain regression gates. Local
PostgreSQL status is reported separately and is never inferred from SQLite.

## Local verification

At implementation time the local results were:

- `uv lock --check`: passed;
- Ruff check and format check: passed;
- `uv run mypy app`: passed;
- `uv run pytest backend/tests/actual_harvest_import -q`: 217 passed, 16 skipped;
- core forecast and V0.1-S1: 154 passed;
- agent: 359 passed;
- API/lifespan and actual-harvest routes: 25 passed;
- Alembic contract regression: 6 passed;
- local PostgreSQL: not run because Docker is unavailable.

The exact-head PR CI is the acceptance source for PostgreSQL execution. Its
run ID, JUnit counts, node IDs and artifact digests are recorded in the PR
body after the new Head completes; no local SQLite result is represented as
PostgreSQL evidence.

## Exact-head CI evidence

Code-fix exact-head run `29650514335` was a `pull_request` run for Head
`2c8a5a8210e85e0343ac34b94235249e487e25e8` and completed successfully. All
eight PR jobs passed; `full-suite-canary` was skipped by pull-request design.
The downloaded JUnit artifacts report `3277 total / 3252 passed / 0 failures /
0 errors / 25 skipped`.

The `postgres-domain-1` artifact executed these 11 I5 nodes successfully:

- `test_postgres_i5_identical_validate_replays_immutable_result`;
- `test_postgres_i5_cancel_validated_preserves_validation_evidence`;
- `test_postgres_i5_validate_cancel_race_has_one_serialized_outcome`;
- `test_postgres_i5_validation_failed_cancel_preserves_all_evidence`;
- `test_postgres_i5_draft_registry_is_rejected`;
- `test_postgres_i5_sealed_registry_entry_mutation_is_rejected`;
- `test_postgres_i5_heartbeat_renewal_and_expired_attempt_cannot_finalize`;
- `test_postgres_i5_old_worker_cannot_demote_new_attempt_state`;
- `test_postgres_i5_committed_history_predecessor_is_in_validation_basis`;
- `test_postgres_i5_uncommitted_batch_is_excluded_from_lineage_basis`;
- `test_postgres_i5_validation_errors_use_bounded_keyset_pagination`.

Artifacts, all unexpired and bound to this exact Head:

- `postgres-domain-1-results`: `8431366795`, `sha256:6a451a0a801603391234647bb5e48c81f0c7c76683f3b664a6d2778a4664dfd3`;
- `postgres-domain-2-results`: `8431408941`, `sha256:b6368ba963a4ef9b4f9e7f5a30a89c1424d792fcd03c6bc86b65a7553ab7ec8c`;
- `postgres-migration-results`: `8431335826`, `sha256:f4401b9e999b147ef5590d50adb9a7d56b25dbb3926ccbaec7fe0d62abca7b7c`;
- `postgres-task11-results`: `8431345577`, `sha256:3753e0f237f1937539354bf1b1b909fc718a984d86021a62e493fa1cee8bb452`;
- `postgres-concurrency-results`: `8431335874`, `sha256:e4a1a308e2fdfe14b48d8d0571f344cbd8b97612a1ac80687d5bd44a4793689c`;
- `unit-contract-golden-results`: `8431359643`, `sha256:69c00b11aaf41b8dc8d8facf97f0ad3581898436296e84e7bb8b2a7d16d63755`.

Hard exclusions are Q2A-I6 atomic commit, Q2A-I7 cutoff winner/aggregation/
label snapshot, Q2A-I8 integration acceptance, Q2B, Q3, TASK-013 Slice C C2,
spreadsheet orchestration, public mapping-admin API, frontend and model code.
