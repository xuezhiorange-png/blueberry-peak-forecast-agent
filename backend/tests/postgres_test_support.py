"""Compatibility shim for ``backend.tests.postgres_test_support``.

Per the Batch 5 design freeze (PR #68 / Issue #53) §7 commit 2,
this module is preserved as a thin re-export during the transition
from ``backend/tests/postgres_test_support.py`` to
``backend/tests/db/profile.py``. Future removal of this shim is a
separate authorization (design §7 commit 7).
"""

from __future__ import annotations

import warnings

from backend.tests.db.profile import (  # noqa: F401  (re-export)
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

warnings.warn(
    "backend.tests.postgres_test_support has moved to backend.tests.db.profile. "
    "The top-level shim will be removed in a future round; update imports.",
    DeprecationWarning,
    stacklevel=2,
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
