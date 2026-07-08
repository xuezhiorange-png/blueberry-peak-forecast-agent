"""Compatibility shim for ``backend.tests.concurrency_isolation_helpers``.

Per the Batch 5 design freeze (PR #68 / Issue #53) §7 commit 2,
this module is preserved as a thin re-export during the transition
from ``backend/tests/concurrency_isolation_helpers.py`` to
``backend/tests/db/concurrency.py``. Future removal of this shim is a
separate authorization (design §7 commit 7).
"""

from __future__ import annotations

import warnings

from backend.tests.db.concurrency import (  # noqa: F401  (re-export)
    CONCURRENCY_ISOLATED_DB_NAME_PREFIX,
    CONCURRENCY_MAX_ISOLATED_DB_NAME_LEN,
    ISOLATED_JOB_NAME,
    assert_safe_concurrency_isolated_db_name,
    resolve_concurrency_isolated_db_name,
)

warnings.warn(
    "backend.tests.concurrency_isolation_helpers has moved to "
    "backend.tests.db.concurrency. The top-level shim will be removed in a "
    "future round; update imports.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "ISOLATED_JOB_NAME",
    "CONCURRENCY_ISOLATED_DB_NAME_PREFIX",
    "CONCURRENCY_MAX_ISOLATED_DB_NAME_LEN",
    "resolve_concurrency_isolated_db_name",
    "assert_safe_concurrency_isolated_db_name",
]