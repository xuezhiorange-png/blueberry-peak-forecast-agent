"""Compatibility shim for ``backend.tests.migration_isolation_helpers``.

Per the Batch 5 design freeze (PR #68 / Issue #53) §7 commit 2,
this module is preserved as a thin re-export during the transition
from ``backend/tests/migration_isolation_helpers.py`` to
``backend/tests/db/migration.py``. Future removal of this shim is a
separate authorization (design §7 commit 7).
"""

from __future__ import annotations

import warnings

from backend.tests.db.migration import (  # noqa: F401  (re-export)
    ISOLATED_DB_NAME_PREFIX,
    MAX_ISOLATED_DB_NAME_LEN,
    assert_safe_isolated_db_name,
    resolve_isolated_db_name,
)

warnings.warn(
    "backend.tests.migration_isolation_helpers has moved to "
    "backend.tests.db.migration. The top-level shim will be removed in a "
    "future round; update imports.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "ISOLATED_DB_NAME_PREFIX",
    "MAX_ISOLATED_DB_NAME_LEN",
    "assert_safe_isolated_db_name",
    "resolve_isolated_db_name",
]