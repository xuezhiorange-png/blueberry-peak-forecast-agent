# Q2A-I5 post-merge canary isolation hotfix

## Incident

The failed main push run was `29675052814`, job `full-suite-canary`, for
`bac49e98bb11a26a43ef32946c7f739a84d7f2d3`. The downstream failure was:

```text
backend/tests/integration/agent/test_orchestration_postgres.py::test_slice_b_orchestration_uses_real_postgres_session
```

with a duplicate `pk_dim_farm` error for primary key `1`.

The root cause is test fixture ownership, not production behavior:

```text
I5 PostgreSQL tests commit master data
-> sealed-registry cleanup returns without deletion
-> dim_farm id=1 remains visible
-> Slice B inserts dim_farm id=1
-> transactional_pg_session skips the pre-test truncate
-> shared full-suite database collides
```

## Fix boundary

This hotfix is test isolation only. The I5 PostgreSQL module owns cleanup of
its committed fixture data through a module-scoped, test-only fixture. It runs
both before collection execution and after the module completes, using a new
session and a committed transaction. The cleanup is fail-closed behind:

- `APP_ENV=test`;
- `RUN_POSTGRES_INTEGRATION=1`;
- `assert_safe_postgres_test_identity`.

It uses PostgreSQL `TRUNCATE ... RESTART IDENTITY CASCADE` for the I5 batch,
mapping registry, and master-data root tables. This does not disable, drop, or
bypass sealed-registry triggers. Repeating cleanup is an explicit no-op.

The acceptance test commits a sealed registry, master data, and validation
evidence, proves the rows are removed, reuses `Farm(id=1)`,
`Subfarm(id=1, farm_id=1)`, `Season(id=1)`, and `Variety(id=101)`, then proves
the sealed-registry trigger and function identities still reject direct
mutation. The downstream Slice B test remains unchanged and is the consumer
of the released IDs in the shared database.

## Evidence procedure

The normal PostgreSQL shard must collect the actual-harvest module and the
Slice B PostgreSQL test in the same database environment, in that order. The
`postgres-domain-1` command lists `test_lifecycle_postgres.py` immediately
before `test_orchestration_postgres.py`. After pytest succeeds, the job parses
the actual JUnit testcase sequence and fails unless every I5 module testcase,
including `test_postgres_i5_module_cleanup_releases_master_ids_for_downstream_suites`,
precedes `test_slice_b_orchestration_uses_real_postgres_session`. The assertion
also rejects skipped, failed, or errored reproducer nodes and writes the node
indices to the job summary.

Both modules use the one isolated database created by the job; the database is
not recreated between them. The PR exact-head CI result is the implementation
evidence; a PR canary skip does not prove the main post-merge canary. A
subsequent main push run after this hotfix merges is required for that proof.

The final evidence order is:

```text
test isolation changes and tests
-> commit
-> push
-> exact-head PR CI
-> verify JUnit and artifacts
-> update Draft PR body only
```

No exact-head CI identifiers are stored in this tracked document because
updating it changes the reviewed commit. Authoritative final CI evidence is
recorded in the Draft PR body and the corresponding formal review.

## Exclusions

No production application code, API behavior, validation semantics, lineage,
hashing, authorization, migration, schema, trigger, or function was changed.
PR #116 remains merged. This hotfix does not close Issue #102 or #99 and does
not authorize Ready, Merge, cleanup, Q2A-I6 through I8, Q2B, or Q3.
