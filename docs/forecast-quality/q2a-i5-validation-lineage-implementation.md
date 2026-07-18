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
`SEALED` without final evidence and requires a new validation.

## Mapping authority

The registry is the only source-code authority. It is append-only and changes
through an internal controlled master-data operation, never through the
actual-harvest HTTP API. Registry versions move `DRAFT -> SEALED`; sealing
locks the version and records entry count plus `registry_content_hash`.
Validation requires a sealed registry and exact `mapping_policy_version`.

Registry entries explicitly identify source field, source code, target type and
stable target business key. Display names are not inferred as source codes.
I5 v1 is `SUBFARM_ONLY_PLOT_REJECTED`; plot input cannot be silently mapped to a
subfarm. Farm, subfarm, variety and season targets are resolved by exact
business keys against existing master data. Hashes use stable business values,
never database IDs.

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

`validation_result_hash` binds the seal, mapping snapshot, policy versions,
canonical record hashes, mapping outcomes, ordered lineage nodes and edges,
errors/warnings/counts, committed basis and lineage graph. It excludes cutoff,
winner, aggregation, runtime, database and pagination values.

## Evidence schema

Migration `0019_actual_harvest_validation_evidence` adds exactly:

- `actual_harvest_mapping_policy_registry`;
- `actual_harvest_mapping_registry_entry`;
- `actual_harvest_mapping_snapshot`;
- `actual_harvest_validation_run`;
- `actual_harvest_validation_attempt`;
- `actual_harvest_validation_result`;
- `actual_harvest_validation_record`;
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

The I5 test set covers registry sealing and rejection, exact mapping, replay,
lineage errors, validation error pagination, preview summary, cancellation
evidence preservation and stale-attempt fencing. The PostgreSQL shard covers
concurrent validation replay and cancellation evidence preservation. Existing
I1-I4, core, agent and Alembic tests remain regression gates. Local PostgreSQL
status is reported separately and is never inferred from SQLite.

## Local verification

At implementation time the local results were:

- `uv lock --check`: passed;
- Ruff check and format check: passed;
- `uv run mypy app`: passed;
- `uv run pytest backend/tests/actual_harvest_import -q`: 184 passed, 7 skipped;
- core forecast: 143 passed;
- agent: 359 passed;
- API/lifespan regression: 58 passed;
- Alembic regression: 28 passed;
- local PostgreSQL: not run because Docker is unavailable.

The exact-head PR CI is the acceptance source for PostgreSQL execution and
will be recorded here after the Draft PR run completes.

Hard exclusions are Q2A-I6 atomic commit, Q2A-I7 cutoff winner/aggregation/
label snapshot, Q2A-I8 integration acceptance, Q2B, Q3, TASK-013 Slice C C2,
spreadsheet orchestration, public mapping-admin API, frontend and model code.
