"""Slice 3 — isolated PostgreSQL test-database profile for migration round-trip.

Carried forward from Batch 3 Slice 3 (per Issue #51). Provides pure
(no-I/O) helpers that generate and validate a per-run isolated
database name for the ``postgres-migration`` CI job.

The helpers here are **pure**: they perform no network I/O, no
subprocess, no mutation of the process environment, and never print
passwords / tokens / full ``DATABASE_URL`` values.

Per the Batch 5 design freeze (PR #68 / Issue #53), this module
lives under ``backend/tests/db/migration.py`` rather than the legacy
``backend/tests/migration_isolation_helpers.py``. The legacy module
remains a thin compatibility shim during the transition.
"""

from __future__ import annotations

import re

from backend.tests.db.safety import (
    DEFAULT_TEST_DB_PORT,
    FORBIDDEN_DATABASE_NAMES,
    PostgresTestIdentity,
    validate_postgres_test_identity,
)

#: Prefix for every Slice 3 isolated database name.
#:
#: The ``_test_`` substring is required by
#: :func:`backend.tests.db.safety.validate_postgres_test_identity` so
#: a name like ``blueberry_peak`` (which contains ``blueberry_peak``
#: but no ``_test``) is rejected by the existing safeguard.
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

    if not run_id_str or not run_id_str.isdigit() or int(run_id_str) < 1:
        raise ValueError(
            f"resolve_isolated_db_name: github_run_id must be a positive "
            f"integer, got {github_run_id!r}"
        )
    if not attempt_str or not attempt_str.isdigit() or int(attempt_str) < 1:
        raise ValueError(
            f"resolve_isolated_db_name: github_run_attempt must be a positive "
            f"integer (github_run_attempt must be >= 1), got {github_run_attempt!r}"
        )
    if not job_name_clean:
        raise ValueError("resolve_isolated_db_name: job_name must be a non-empty string")
    if not _SEGMENT_RE.fullmatch(job_name_clean):
        raise ValueError(
            f"resolve_isolated_db_name: job_name must match "
            f"{_SEGMENT_RE.pattern!r}, got {job_name_clean!r}"
        )

    name = f"{ISOLATED_DB_NAME_PREFIX}{run_id_str}_{attempt_str}_{job_name_clean}"
    if len(name) > MAX_ISOLATED_DB_NAME_LEN:
        raise ValueError(
            f"resolve_isolated_db_name: composed name length {len(name)} "
            f"exceeds PostgreSQL identifier limit of "
            f"{MAX_ISOLATED_DB_NAME_LEN}"
        )
    return name


def assert_safe_isolated_db_name(db_name: str) -> None:
    """Fail-closed guard for an isolated DB name.

    Routes the name through :func:`backend.tests.db.safety.resolve_postgres_test_identity`
    (with the isolated name as the database) and
    :func:`backend.tests.db.safety.validate_postgres_test_identity` so the
    Slice 3 / Slice 4 chain shares the same fail-closed predicate that
    the dev-DB safeguard uses.

    In addition, the name MUST start with the isolated DB prefix
    :data:`ISOLATED_DB_NAME_PREFIX` (per design §4.3 + Batch 5 PR #69
    P0-2 fix). This is the per-run isolation guarantee — without it,
    a CI run could land on the service container's literal
    ``blueberry_peak`` DB.

    Raises
    ------
    ValueError
        If the name is empty, in the forbidden database name set,
        does not start with :data:`ISOLATED_DB_NAME_PREFIX`, or
        otherwise fails the test profile validation.

    The error messages are pinned to specific substrings by the
    regression tests in
    ``backend/tests/test_alembic_round_trip_isolated.py``:
    ``"non-empty string"`` for the empty check,
    ``"refusing isolated DB name"`` for the forbidden-prefix check,
    and ``"FORBIDDEN_DATABASE_NAMES"`` for the forbidden-list check.

    Security note: the input ``db_name`` is **never echoed verbatim**
    in the error message. ``db_name`` may carry credentials (a CI
    misconfiguration can pass a password-bearing string here), and
    echoing it would leak the secret into logs. The error message
    only carries the prefix requirement / set membership.
    """
    if not db_name or not isinstance(db_name, str):
        raise ValueError("assert_safe_isolated_db_name: db_name must be a non-empty string")
    if db_name in FORBIDDEN_DATABASE_NAMES:
        raise ValueError(
            "assert_safe_isolated_db_name: refusing isolated DB name: "
            "input is present in FORBIDDEN_DATABASE_NAMES "
            "(input redacted for safety)"
        )
    if not db_name.startswith(ISOLATED_DB_NAME_PREFIX):
        # Note: the message intentionally contains BOTH the new strict
        # phrasing ("input does not start with required isolated prefix")
        # pinned by the ``backend/tests/test_alembic_round_trip_isolated.py``
        # regression suite AND the legacy phrasing
        # ("must start with the slice-3 isolated profile marker") pinned
        # by the pre-PR-69 ``test_concurrency_isolation_helpers.py``
        # suite. ``pytest.raises(..., match=...)`` uses regex
        # ``re.search``, so both substrings satisfy either test.
        # The input ``db_name`` is intentionally redacted — it may
        # carry a password / token / full DATABASE_URL.
        raise ValueError(
            "assert_safe_isolated_db_name: refusing isolated DB name: "
            "input does not start with required isolated prefix; "
            "must start with the slice-3 isolated profile marker "
            f"{ISOLATED_DB_NAME_PREFIX!r} (input redacted for safety)"
        )
    identity = PostgresTestIdentity(
        database_name=db_name,
        port=DEFAULT_TEST_DB_PORT,
        app_env="test",
        database_user="postgres",
        host="localhost",
    )
    validate_postgres_test_identity(identity)


__all__ = [
    "ISOLATED_DB_NAME_PREFIX",
    "MAX_ISOLATED_DB_NAME_LEN",
    "resolve_isolated_db_name",
    "assert_safe_isolated_db_name",
]
