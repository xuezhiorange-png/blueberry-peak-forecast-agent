"""Slice 4 — isolated PostgreSQL test-database profile for concurrency / real-commit tests.

Carried forward from Batch 3 Slice 4 (per Issue #51). This submodule
is a **thin job-name-agnostic wrapper** over
:mod:`backend.tests.db.migration`. It binds the same resolver /
fail-closed guard to the ``postgres_concurrency`` job name so that
the ``postgres-concurrency`` CI job can run its
``@pytest.mark.postgres_concurrency`` tests against a per-run
isolated database instead of the service container's literal
``blueberry_peak`` DB.

Per the Batch 5 design freeze (PR #68 / Issue #53), this module lives
under ``backend/tests/db/concurrency.py`` rather than the legacy
``backend/tests/concurrency_isolation_helpers.py``. The legacy module
remains a thin compatibility shim during the transition.
"""

from __future__ import annotations

from backend.tests.db.migration import (  # noqa: F401  (re-export)
    ISOLATED_DB_NAME_PREFIX,
    MAX_ISOLATED_DB_NAME_LEN,
    assert_safe_isolated_db_name as _assert_safe_isolated_db_name,
    resolve_isolated_db_name as _resolve_isolated_db_name,
)

#: Canonical CI job name used by both this module and the
#: ``postgres-concurrency`` step in ``.github/workflows/ci.yml``.
#:
#: This name is appended to the resolved isolated DB name as the
#: ``<job>`` segment. It must satisfy
#: :data:`backend.tests.db.migration._SEGMENT_RE`
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
    :func:`backend.tests.db.migration.resolve_isolated_db_name` that
    pins the job segment to :data:`ISOLATED_JOB_NAME`.
    """
    return _resolve_isolated_db_name(
        github_run_id=github_run_id,
        github_run_attempt=github_run_attempt,
        job_name=ISOLATED_JOB_NAME,
    )


def assert_safe_concurrency_isolated_db_name(db_name: str) -> None:
    """Fail-closed guard for the ``postgres-concurrency`` isolated DB name."""
    _assert_safe_isolated_db_name(db_name)


__all__ = [
    "ISOLATED_JOB_NAME",
    "CONCURRENCY_ISOLATED_DB_NAME_PREFIX",
    "CONCURRENCY_MAX_ISOLATED_DB_NAME_LEN",
    "resolve_concurrency_isolated_db_name",
    "assert_safe_concurrency_isolated_db_name",
]