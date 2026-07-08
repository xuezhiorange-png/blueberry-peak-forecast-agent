"""Assertion helpers and matchers for the test suite.

Per the Batch 5 design freeze (PR #68 / Issue #53), this package
provides **assertion helpers** that compare observed values against
production-computed expected values. Assertions MUST NOT construct
fixtures or open DB sessions.

Submodule boundary (per design §5):
- ``assertions/`` MAY import from ``backend.app.**`` (production
  canonical) when computing expected values.
- ``assertions/`` MUST NOT import from ``factories/``.
- ``assertions/`` MUST NOT import from ``db/``.

The boundary ensures assertions remain pure functions that take
values as arguments; they do not pull fixtures from a global
state and do not open DB sessions.
"""
