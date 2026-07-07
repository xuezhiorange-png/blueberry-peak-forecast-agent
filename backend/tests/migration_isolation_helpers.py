"""Slice 3 — isolated PostgreSQL test-database profile for migration round-trip.

This module provides pure (no-I/O) helpers that generate and validate a
per-run isolated database name for the ``postgres-migration`` CI job
(``alembic upgrade head`` / ``downgrade 0010_harvest_state_persistence``
/ ``upgrade head``). The destructive round-trip is bound to a database
name that is:

* globally unique per GitHub Actions run (``run_id`` + ``run_attempt``
  + ``job_name``);
* recognizably a *test* database (contains the literal ``_test_``);
* never one of the dev / production / cluster-default names enforced
  by :mod:`backend.tests.postgres_test_support` (for example
  ``blueberry_peak``, ``blueberry_peak_dev``,
  ``blueberry_peak_production``, ``postgres``).

Design notes
------------

* The helpers here are **pure**: they perform no network I/O, no
  subprocess, no mutation of the process environment, and never print
  passwords / tokens / full ``DATABASE_URL`` values.
* The CI step that creates / drops the actual database lives in
  ``.github/workflows/ci.yml`` (``postgres-migration`` job). This
  module is the test-only contract that the CI step honours and that
  the safety tests assert against.
* Slice 1's dev-DB safeguard
  (:func:`backend.tests.postgres_test_support.validate_postgres_test_identity`)
  is the authoritative rejecter; :func:`assert_safe_isolated_db_name`
  in this module routes the resolved name through that safeguard so
  the CI profile is fail-closed by the same rule the rest of the test
  suite uses.

Scope
-----

* In scope: isolated database **name** resolution and validation for
  the destructive migration round-trip.
* Out of scope: ordinary integration-test schema isolation (deferred
  to Slice 5), concurrency / real-commit isolation (Slice 4), and
  cross-job database name uniqueness (Slice 3 is single-job; the
  ``run_id`` + ``run_attempt`` prefix makes the name unique even when
  multiple jobs run concurrently).
"""

from __future__ import annotations

import re

from backend.tests.postgres_test_support import (
    DEFAULT_TEST_APP_ENV,
    FORBIDDEN_DATABASE_NAMES,
    PostgresTestIdentity,
    validate_postgres_test_identity,
)

#: Prefix for every Slice 3 isolated database name.
#:
#: The ``_test_`` substring is required by
#: :func:`backend.tests.postgres_test_support.validate_postgres_test_identity`
#: so a name like ``blueberry_peak`` (which contains ``blueberry_peak`` but
#: no ``_test``) is rejected by the existing safeguard.
ISOLATED_DB_NAME_PREFIX: str = "blueberry_peak_test_"

#: Maximum length of the resolved database name.
#:
#: PostgreSQL truncates identifiers at 63 bytes; we keep a safety margin.
MAX_ISOLATED_DB_NAME_LEN: int = 63

#: Regex for the variable-length portion of the name. Each component is
#: restricted to ``[A-Za-z0-9_-]`` so the resulting name is portable
#: across all PostgreSQL configurations and shell-safe in CI env vars.
_SEGMENT_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_-]+$")


def resolve_isolated_db_name(
    github_run_id: int | str,
    github_run_attempt: int | str,
    job_name: str,
) -> str:
    """Return the canonical isolated database name for one CI job run.

    Parameters
    ----------
    github_run_id:
        The numeric GitHub Actions ``GITHUB_RUN_ID`` of the workflow
        invocation. Accepted as ``int`` or numeric ``str``; non-numeric
        values raise :class:`ValueError`.
    github_run_attempt:
        The numeric ``GITHUB_RUN_ATTEMPT`` of the current attempt
        (1-based). Same validation as ``github_run_id``.
    job_name:
        The CI job name (e.g. ``"postgres_migration"``). Must match
        :data:`_SEGMENT_RE`.

    Returns
    -------
    str
        A name of the form
        ``blueberry_peak_test_<run_id>_<attempt>_<job_name>`` whose
        length is at most :data:`MAX_ISOLATED_DB_NAME_LEN`.

    Raises
    ------
    ValueError
        If any component is empty, non-numeric (for the run / attempt
        fields), contains characters outside ``[A-Za-z0-9_-]``, or if
        the composed name would exceed the PostgreSQL identifier
        length limit.
    """

    run_id_str = str(github_run_id).strip()
    attempt_str = str(github_run_attempt).strip()
    job_name_clean = job_name.strip()

    if not run_id_str or not run_id_str.isdigit():
        raise ValueError(
            f"resolve_isolated_db_name: github_run_id must be a positive "
            f"integer, got {github_run_id!r}"
        )
    if not attempt_str or not attempt_str.isdigit():
        raise ValueError(
            f"resolve_isolated_db_name: github_run_attempt must be a positive "
            f"integer, got {github_run_attempt!r}"
        )
    if not job_name_clean:
        raise ValueError("resolve_isolated_db_name: job_name must be a non-empty string")
    if not _SEGMENT_RE.match(job_name_clean):
        raise ValueError(
            "resolve_isolated_db_name: job_name must match "
            f"{_SEGMENT_RE.pattern!r}, got {job_name!r}"
        )
    if int(attempt_str) < 1:
        raise ValueError(
            f"resolve_isolated_db_name: github_run_attempt must be >= 1, got {github_run_attempt!r}"
        )

    name = f"{ISOLATED_DB_NAME_PREFIX}{run_id_str}_{attempt_str}_{job_name_clean}"

    if len(name) > MAX_ISOLATED_DB_NAME_LEN:
        raise ValueError(
            f"resolve_isolated_db_name: composed name {name!r} is "
            f"{len(name)} chars, exceeds PostgreSQL identifier limit "
            f"({MAX_ISOLATED_DB_NAME_LEN})"
        )

    return name


def assert_safe_isolated_db_name(db_name: str) -> None:
    """Fail-closed guard for an isolated database name.

    The guard enforces three rules:

    1. The name is **not** in :data:`FORBIDDEN_DATABASE_NAMES` (the
       slice-1 authority, including the cluster-default ``postgres``
       database and the dev / production literals).
    2. The name starts with :data:`ISOLATED_DB_NAME_PREFIX` (so it is
       recognizably a *test* database name, not a dev / prod /
       cluster-default name).
    3. Routing through
       :func:`backend.tests.postgres_test_support.validate_postgres_test_identity`
       with a minimal :class:`PostgresTestIdentity` succeeds. The
       identity uses :data:`DEFAULT_TEST_APP_ENV` (``"test"``) so the
       validator's APP_ENV rule is satisfied.

    The error message **never** includes a password, token, or
    full ``DATABASE_URL`` value (the guard never sees one — the
    caller passes only the name).

    Raises
    ------
    ValueError
        With a short, name-only reason if any rule fails.
    """
    if not isinstance(db_name, str) or not db_name:
        raise ValueError("assert_safe_isolated_db_name: db_name must be a non-empty string")

    # Order matters: the FORBIDDEN_DATABASE_NAMES check is the
    # strongest, fail-closed gate (it covers the slice-1 authority
    # such as the PostgreSQL cluster-default ``postgres`` database).
    # It must run before the prefix check so a forbidden name like
    # ``postgres`` is rejected with the FORBIDDEN reason (and not
    # the more generic "must start with" reason).
    #
    # The error messages intentionally do NOT echo the offending
    # name back to the caller: the safety contract for this guard
    # is that no caller-controlled input (which may include a
    # password or token by mistake) ever appears in the error
    # message. The slice-1 safeguard (``validate_postgres_test_identity``)
    # honours the same contract.
    if db_name in FORBIDDEN_DATABASE_NAMES:
        raise ValueError(
            "refusing isolated DB name: matches a "
            "FORBIDDEN_DATABASE_NAMES entry. Use a *_test_* suffixed name."
        )

    if not db_name.startswith(ISOLATED_DB_NAME_PREFIX):
        raise ValueError(
            "refusing isolated DB name: must start with the slice-3 isolated profile marker."
        )

    # The slice-1 safeguard is the authoritative rejecter. We feed it a
    # minimal identity that satisfies its APP_ENV and worker_id
    # requirements so the only thing actually being checked is the
    # database name itself.
    identity = PostgresTestIdentity(
        database_name=db_name,
        database_host="localhost",
        database_port="55432",
        app_env=DEFAULT_TEST_APP_ENV,
        worker_id="postgres_migration",
    )
    validate_postgres_test_identity(identity)


__all__ = [
    "ISOLATED_DB_NAME_PREFIX",
    "MAX_ISOLATED_DB_NAME_LEN",
    "assert_safe_isolated_db_name",
    "resolve_isolated_db_name",
]
