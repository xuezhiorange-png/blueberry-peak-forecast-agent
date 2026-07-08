"""Slice 1 — shared PostgreSQL test support: identity validation and identity logging.

Carried forward from Batch 3 Slice 1 (per PR #47 / Issue #23 sub-area 1).
This submodule is the **profile resolution + validation** layer for
the test suite's DB identifier contract (per design §4.3).

It provides (re-exported from :mod:`backend.tests.db.safety`, which is
the canonical home for the safety predicates):

- :data:`FORBIDDEN_DATABASE_NAMES` — explicit dev-DB name set
- :data:`FORBIDDEN_DATABASE_PORTS` — explicit dev-DB port set
- :data:`PRODUCTION_APP_ENVS` — explicit APP_ENV values that must never
  appear in a test profile
- :data:`SAFE_TEST_APP_ENVS` — explicit APP_ENV values that mark a
  profile as safe-for-test
- :data:`DEFAULT_TEST_DB_NAME` / :data:`DEFAULT_TEST_DB_PORT` /
  :data:`DEFAULT_TEST_APP_ENV` / :data:`DEFAULT_TEST_DB_USER` /
  :data:`DEFAULT_TEST_DB_HOST` — safe-default fallback values
- :class:`PostgresTestIdentity` — dataclass with parsed components
  (database_name, port, app_env, database_user, host, worker_id,
  used_defaults) — no tokens / passwords stored
- :func:`resolve_postgres_test_identity` — pure resolver that reads
  ``os.environ`` and returns a :class:`PostgresTestIdentity` dataclass.
  Never imports from ``backend.app`` so it is hermetic.
- :func:`validate_postgres_test_identity` — pure validator that takes
  an identity (or env) and raises ``ValueError`` on any unsafe profile.
  Never connects to a database. Never echoes passwords.
- :func:`assert_safe_postgres_test_identity` — fail-closed wrapper that
  invokes the validator and is intended for use from safety tests,
  shell scripts, Makefile guards, and the pytest session-start log.
- :func:`format_postgres_test_identity` — deterministic one-line
  summary suitable for log output (no secrets, no passwords).

This module is preserved as the **public namespace** for the test
suite's DB identifier profile contract per design §4.3 (typed factory
contract). All public symbols are re-exported here from
:mod:`backend.tests.db.safety` so that
``from backend.tests.db.profile import DEFAULT_TEST_APP_ENV`` (used by
the legacy ``backend.tests.postgres_test_support`` shim) works.

Design discipline
-----------------

* File location: ``backend/tests/db/profile.py`` (carried forward from
  the original ``backend/tests/postgres_test_support.py``). No
  production-code mutation.
* No DB / network IO (in the validator itself). The validator is pure
  Python over ``os.environ`` so it can be exercised from CI without a
  live PostgreSQL.
* No token / password echo. The summary function never includes the
  ``DATABASE_URL`` value — only its parsed components.
"""

from __future__ import annotations

from backend.tests.db.safety import (  # noqa: F401  (re-export)
    DEFAULT_TEST_APP_ENV,
    DEFAULT_TEST_DB_HOST,
    DEFAULT_TEST_DB_NAME,
    DEFAULT_TEST_DB_PORT,
    DEFAULT_TEST_DB_USER,
    FORBIDDEN_DATABASE_NAMES,
    FORBIDDEN_DATABASE_PORTS,
    PRODUCTION_APP_ENVS,
    SAFE_TEST_APP_ENVS,
    PostgresTestIdentity,
    assert_safe_postgres_test_identity,
    format_postgres_test_identity,
    resolve_postgres_test_identity,
    validate_postgres_test_identity,
)

__all__ = [
    "FORBIDDEN_DATABASE_NAMES",
    "FORBIDDEN_DATABASE_PORTS",
    "PRODUCTION_APP_ENVS",
    "SAFE_TEST_APP_ENVS",
    "DEFAULT_TEST_DB_NAME",
    "DEFAULT_TEST_DB_PORT",
    "DEFAULT_TEST_APP_ENV",
    "DEFAULT_TEST_DB_USER",
    "DEFAULT_TEST_DB_HOST",
    "PostgresTestIdentity",
    "resolve_postgres_test_identity",
    "validate_postgres_test_identity",
    "assert_safe_postgres_test_identity",
    "format_postgres_test_identity",
]
