"""Slice 4 — isolated PostgreSQL test-database profile for concurrency / real-commit tests.

This module is a **thin job-name-agnostic wrapper** over the
:mod:`backend.tests.migration_isolation_helpers` pure helpers
introduced by Slice 3. It binds the same resolver / fail-closed guard
to the ``postgres_concurrency`` job name so that the
``postgres-concurrency`` CI job can run its
``@pytest.mark.postgres_concurrency`` tests against a per-run isolated
database instead of the service container's literal ``blueberry_peak``
DB.

Design notes
------------

* The resolver / guard logic is **not** duplicated here. Slice 3's
  :func:`backend.tests.migration_isolation_helpers.resolve_isolated_db_name`
  and :func:`backend.tests.migration_isolation_helpers.assert_safe_isolated_db_name`
  are pure, job-name-agnostic, and already cover every property this
  slice needs. The wrapper here only pins the canonical job name for
  the ``postgres-concurrency`` CI job and re-exports the Slice 3
  primitives under names that read naturally at the concurrency call
  site.
* The CI step that creates / drops the actual database lives in
  ``.github/workflows/ci.yml`` (``postgres-concurrency`` job). This
  module is the test-only contract that the CI step honours and that
  the safety tests assert against.
* Slice 1's dev-DB safeguard
  (:func:`backend.tests.postgres_test_support.validate_postgres_test_identity`)
  is the authoritative rejecter; the wrapper routes through Slice 3
  which routes through Slice 1.
* The ``ISOLATED_JOB_NAME`` constant is the canonical job name used by
  both this module and the ``postgres-concurrency`` CI step. Any
  change here must be paired with a change in ``.github/workflows/ci.yml``.

Scope
-----

* In scope: isolated database **name** resolution and validation for
  concurrency / real-commit tests in the ``postgres-concurrency`` CI
  job.
* Out of scope:

  - ordinary integration-test schema isolation (deferred to Slice 5);
  - CI structure / diagnostics cleanup (deferred to Slice 6);
  - production semantics changes (never in scope for Batch 3);
  - Alembic version changes (never in scope for Batch 3);
  - any cross-job database name uniqueness requirement (Slice 4 is
    single-job; the ``run_id`` + ``run_attempt`` prefix makes the name
    unique even when multiple jobs run concurrently).
"""

from __future__ import annotations

from backend.tests.migration_isolation_helpers import (
    ISOLATED_DB_NAME_PREFIX,
    MAX_ISOLATED_DB_NAME_LEN,
)
from backend.tests.migration_isolation_helpers import (
    assert_safe_isolated_db_name as _assert_safe_isolated_db_name,
)
from backend.tests.migration_isolation_helpers import (
    resolve_isolated_db_name as _resolve_isolated_db_name,
)

#: Canonical CI job name used by both this module and the
#: ``postgres-concurrency`` step in ``.github/workflows/ci.yml``.
#:
#: This name is appended to the resolved isolated DB name as the
#: ``<job>`` segment. It must satisfy
#: :data:`backend.tests.migration_isolation_helpers._SEGMENT_RE`
#: (``[A-Za-z0-9_-]+``) and must be distinct from the Slice 3
#: ``postgres_migration`` job name so the two jobs never share an
#: isolated database even on the same run / attempt.
ISOLATED_JOB_NAME: str = "postgres_concurrency"

# Re-export Slice 3 constants under slice-4 names for call-site clarity.
CONCURRENCY_ISOLATED_DB_NAME_PREFIX: str = ISOLATED_DB_NAME_PREFIX
CONCURRENCY_MAX_ISOLATED_DB_NAME_LEN: int = MAX_ISOLATED_DB_NAME_LEN


def resolve_concurrency_isolated_db_name(
    github_run_id: int | str,
    github_run_attempt: int | str,
) -> str:
    """Return the canonical isolated database name for the ``postgres-concurrency`` job.

    Thin job-name-agnostic wrapper over
    :func:`backend.tests.migration_isolation_helpers.resolve_isolated_db_name`
    that pins the job segment to :data:`ISOLATED_JOB_NAME`. The
    returned name has the form
    ``blueberry_peak_test_<run_id>_<attempt>_postgres_concurrency``.

    Parameters
    ----------
    github_run_id:
        The numeric GitHub Actions ``GITHUB_RUN_ID`` of the workflow
        invocation. Accepted as ``int`` or numeric ``str``; non-numeric
        values raise :class:`ValueError`.
    github_run_attempt:
        The numeric ``GITHUB_RUN_ATTEMPT`` of the current attempt
        (1-based). Same validation as ``github_run_id``.

    Returns
    -------
    str
        A name of length at most
        :data:`MAX_ISOLATED_DB_NAME_LEN` (63 chars, the PostgreSQL
        identifier limit with a safety margin).

    Raises
    ------
    ValueError
        Propagated from
        :func:`backend.tests.migration_isolation_helpers.resolve_isolated_db_name`
        on any invalid input.
    """
    return _resolve_isolated_db_name(
        github_run_id=github_run_id,
        github_run_attempt=github_run_attempt,
        job_name=ISOLATED_JOB_NAME,
    )


def assert_safe_concurrency_isolated_db_name(db_name: str) -> None:
    """Fail-closed guard for the ``postgres-concurrency`` isolated DB name.

    Thin wrapper over
    :func:`backend.tests.migration_isolation_helpers.assert_safe_isolated_db_name`
    that exists so the concurrency call site reads symmetrically with
    :func:`resolve_concurrency_isolated_db_name`. Both functions route
    through the same Slice 3 / Slice 1 fail-closed chain.

    Raises
    ------
    ValueError
        Propagated from
        :func:`backend.tests.migration_isolation_helpers.assert_safe_isolated_db_name`
        on any unsafe name. The error message never includes a
        password, token, or full ``DATABASE_URL`` value.
    """
    _assert_safe_isolated_db_name(db_name)


__all__ = [
    "ISOLATED_JOB_NAME",
    "CONCURRENCY_ISOLATED_DB_NAME_PREFIX",
    "CONCURRENCY_MAX_ISOLATED_DB_NAME_LEN",
    "resolve_concurrency_isolated_db_name",
    "assert_safe_concurrency_isolated_db_name",
]
