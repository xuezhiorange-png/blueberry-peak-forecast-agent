"""Session/engine placeholder for the Batch 5 ``db`` package.

Per the Batch 5 design freeze (PR #68 / Issue #53) §4.1 / §13, this
submodule is the **canonical location** for future PG session /
engine / URL resolution helpers. The actual session-management
codebase lives in production modules under ``backend.app.db.session``
and is reused by the application via standard SQLAlchemy patterns.

This module currently exposes only a re-export of the production
``SessionLocal`` factory so that integration tests can wire it via
``backend.tests.db.session`` rather than reaching into production
namespaces directly. Any further session-helper logic (e.g. test
fixtures that open per-test sessions and roll back) lands here in
future rounds, scoped to the design §5 import-boundary rules
(``db/`` may import from ``backend.app.**`` but MUST NOT import
from ``factories/`` or ``assertions/``).
"""

from __future__ import annotations

# Re-export the production SessionLocal factory so integration tests
# Re-export the production AsyncSessionMaker factory so integration tests
# can wire it via the ``db/`` namespace without reaching into production
# code paths directly. This is the only allowed import-boundary crossing
# from ``db/`` to ``backend.app.**`` for session plumbing.
try:
    from backend.app.db.session import AsyncSessionMaker  # noqa: F401
except ImportError:  # pragma: no cover (production module may not import cleanly)
    AsyncSessionMaker = None  # type: ignore[assignment]


__all__ = ["AsyncSessionMaker"]
