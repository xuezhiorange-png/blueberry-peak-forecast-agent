"""Isolation placeholder for the Batch 5 ``db`` package.

Per the Batch 5 design freeze (PR #68 / Issue #53) §4.1 / §13, this
submodule is the **canonical location** for the transaction +
savepoint + rollback isolation helpers carried forward from Batch 3
Slice 2 (per Issue #51).

The actual savepoint-based isolation logic is application-side
(``backend.app.db.session`` and the per-test fixtures under
``backend/tests/harvest_state/conftest.py``); the test-side
``backend.tests.db.isolation`` namespace is reserved for future
import-boundary-safe helpers that need to introspect or assert the
isolation level.

Future rounds may add pure functions here that take an open
``Session`` and return the effective isolation level
(``"READ COMMITTED"`` / ``"SERIALIZABLE"``) without mutating the
session. Per design §5, ``db/`` MUST NOT import from
``factories/`` or ``assertions/``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def effective_isolation_level(session: "Session") -> str:
    """Return the effective isolation level for a SQLAlchemy session.

    Pure introspection; does not mutate the session. Returns
    ``"READ COMMITTED"`` as a safe default when the binding is not
    available (e.g. in unit tests that mock the session).
    """
    bind = session.get_bind()
    if bind is None:
        return "READ COMMITTED"
    try:
        isolation = bind.dialect.default_isolation_level
    except AttributeError:
        isolation = None
    return isolation or "READ COMMITTED"


__all__ = ["effective_isolation_level"]