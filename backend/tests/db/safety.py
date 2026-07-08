"""Slice 1 (continued) — public re-export of safety predicates.

This module re-exports the safety predicates from
:mod:`backend.tests.db._safety_predicates` so the
``backend.tests.db.safety`` namespace is the canonical import
location for the dev-DB safeguard machinery.

The legacy ``backend.tests.postgres_test_support`` module remains
a thin compatibility shim during the transition (see commit 2 of
design §7).
"""

from __future__ import annotations

from backend.tests.db._safety_predicates import (  # noqa: F401  (re-export)
    DEFAULT_TEST_APP_ENV,
    DEFAULT_TEST_DB_HOST,
    DEFAULT_TEST_DB_NAME,
    DEFAULT_TEST_DB_PORT,
    DEFAULT_TEST_DB_USER,
    FORBIDDEN_DATABASE_NAMES,
    FORBIDDEN_DATABASE_PORTS,
    PostgresTestIdentity,
    PRODUCTION_APP_ENVS,
    SAFE_TEST_APP_ENVS,
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