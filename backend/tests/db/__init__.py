"""DB connection, isolation profile, and test-identity helpers.

Per the Batch 5 design freeze (PR #68 / Issue #53), this package
provides **DB helpers** for the test suite. DB helpers are concerned
only with connection management, isolation profile resolution, and
test-identity bookkeeping at the connection layer.

Submodule boundary (per design §5):
- ``db/`` MAY import from ``backend.app.**`` for typed DB identifier
  contracts and canonical hashing when used by assertions like
  "DB name encodes the run-id hash".
- ``db/`` MUST NOT import from ``factories/`` or ``assertions/``.

Public surface (submodules are imported on demand):
- ``backend.tests.db.profile`` — APP_ENV=test / port 55432 / db_name
  resolution.
- ``backend.tests.db.isolation`` — transaction + savepoint + rollback
  isolation helpers (carries forward Batch 3 Slice 2 mechanics).
- ``backend.tests.db.concurrency`` — concurrency-isolation helpers
  (carries forward Batch 3 Slice 4 mechanics).
- ``backend.tests.db.migration`` — migration-isolation helpers
  (carries forward Batch 3 Slice 3 mechanics).
- ``backend.tests.db.safety`` — safety predicates used by the
  dev-DB safeguard (carries forward Batch 3 Slice 1 mechanics).
- ``backend.tests.db.session`` — PG session / engine / URL
  resolution.

The top-level ``backend.tests.concurrency_isolation_helpers``,
``backend.tests.migration_isolation_helpers``, and
``backend.tests.postgres_test_support`` modules become thin
compatibility shims that re-export from this package during the
transition (commit 2 of design §7). They are not removed in this
implementation round (commit 7 — shim removal — is a separate
authorization).
"""
