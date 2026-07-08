"""Test factories composing test data via production canonical implementations.

This package composes **factory objects** for the test suite. Per
the Batch 5 design freeze (PR #68 / Issue #53), factories MUST call
production canonical / hash / key / ID implementations under
``backend.app.**`` rather than reimplementing them locally. Test
fixtures may compose factory objects and pass typed inputs, but
they MUST NOT replicate canonical logic.

Submodule boundary (per design §5):
- ``factories/`` MAY import from ``backend.app.**`` (production
  canonical) and ``backend.tests.db`` (DB profile / session).
- ``factories/`` MUST NOT import from ``assertions/``.
- ``factories/`` MUST NOT import from ``backend.tests.db`` to
  assert invariants — DB helpers are concerned only with
  connection / isolation / profile.

Public re-exports of the typed identity dataclass live in
``backend.tests.factories.identity``.
"""
